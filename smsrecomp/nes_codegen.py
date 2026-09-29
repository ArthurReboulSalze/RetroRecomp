"""Build a private NESRecomp compiler with full NROM native ROM coverage.

The pinned dependency checkout remains untouched. Its cycle backend treats any
instruction crossing a 4 KiB PRG slot as interpreted. For NROM, the next
slot's bank is permanently wired, so its operand bytes are known at compile
time and can use the same native instruction templates as other ROM code. NROM
also has one known byte at every CPU ROM address, so every valid instruction
start can be compiled ahead of time, including paths no scripted probe reaches.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import shutil

from .core import ConversionError, replace_once, run
from .paths import ROOT


def _replace_count(source: str, old: str, new: str, count: int) -> str:
    if source.count(old) != count:
        raise ConversionError(f'Pinned NES codegen changed around {old!r}.')
    return source.replace(old, new)


def patched_codegen(source: str) -> str:
    source = replace_once(source,
        '''/* Whether every byte of the instruction is a byte this block knows: inside
 * $8000-$FFFF (the program counter wraps from $FFFF to $0000) and inside the
 * one slot whose bank the block was generated for. An instruction that
 * reaches into the next slot reads a byte from a bank chosen at run time, so
 * neither its operand nor its length can be folded; the interpreter runs it. */
static bool fits_in_slot(const Pos *at, int len) {
    uint16_t addr = pos_addr(at);
    if ((uint32_t)addr + (uint32_t)len - 1 > 0xFFFF) return false;
    return at->k + (uint32_t)len <= SLOT_SIZE;
}
''',
        '''/* NROM wires every PRG slot permanently. Its operand bytes remain known
 * across a 4 KiB slot boundary; a bank-switched cartridge still falls back.
 * Instructions crossing $FFFF read CPU RAM and remain interpreted. */
static bool fits_in_slot(const Program *p, const Pos *at, int len) {
    uint16_t addr = pos_addr(at);
    if ((uint32_t)addr + (uint32_t)len - 1 > 0xFFFF) return false;
    if (at->k + (uint32_t)len <= SLOT_SIZE) return true;
    return p->mapper == 0 && p->fixed[at->slot + 1] >= 0;
}

/* The instruction's own byte, including an operand in NROM's next fixed
 * slot. Call only after fits_in_slot() has validated the full instruction. */
static uint8_t insn_byte(const Program *p, const Pos *at, uint32_t delta) {
    uint32_t offset = at->k + delta;
    uint32_t bank = offset < SLOT_SIZE ? at->bank : (uint32_t)p->fixed[at->slot + 1];
    return prg_byte(p, bank, offset);
}
''')
    source = replace_once(source, 'if (!fits_in_slot(&at, len)) continue;',
                          'if (!fits_in_slot(p, &at, len)) continue;')
    source = _replace_count(source, 'prg_byte(p, at.bank, at.k + 1)',
                            'insn_byte(p, &at, 1)', 3)
    source = _replace_count(source, 'prg_byte(p, at.bank, at.k + 2)',
                            'insn_byte(p, &at, 2)', 2)
    source = _replace_count(source, 'prg_byte(e->p, e->at.bank, e->at.k + 1)',
                            'insn_byte(e->p, &e->at, 1)', 2)
    source = replace_once(source, 'prg_byte(e->p, e->at.bank, e->at.k + 2)',
                          'insn_byte(e->p, &e->at, 2)')
    source = replace_once(source, 'prg_byte(e->p, e->at.bank, e->at.k + (uint32_t)k)',
                          'insn_byte(e->p, &e->at, (uint32_t)k)')
    source = replace_once(source,
                          'An instruction\'s own operand bytes. fits_in_slot() kept the whole\n * instruction inside one slot, so these are always the block\'s own bank.',
                          'An instruction\'s own operand bytes, possibly in the next NROM slot.')
    source = replace_once(source, '    discover(p, seeds, n);\n    free(seeds);',
        '''    discover(p, seeds, n);
    free(seeds);
    if (p->mapper == 0) {
        /* NROM has a permanent bank in every CPU ROM slot. The entry point
         * can be any byte, including a computed-jump target or an offset in
         * data. Compiling all positions is safe: dispatch still checks the
         * live ROM mapping and uses the same per-opcode cycle templates. */
        uint32_t covered = 0;
        for (uint32_t slot = 0; slot < SLOT_COUNT; slot++) {
            uint32_t bank = (uint32_t)p->fixed[slot];
            for (uint32_t k = 0; k < SLOT_SIZE; k++) {
                Pos at = { bank, slot, k };
                if (!fits_in_slot(p, &at, op_length(prg_byte(p, bank, k)))) continue;
                p->is_insn[POS_PACK(bank, slot, k)] = 1;
                covered++;
            }
        }
        printf("[NESRecomp] NROM native ROM positions: %u/%u\\n",
               covered, SLOT_COUNT * SLOT_SIZE);
    }''')
    return source


def prepare_compiler(engine: Path, cmake: str | Path, generator: str, emit) -> Path:
    upstream = (engine / 'recompiler/src/cyc_codegen.c').read_text(encoding='utf-8')
    patched = patched_codegen(upstream)
    revision = run(['git', '-C', engine, 'rev-parse', 'HEAD']).strip()
    identity = sha256(patched.encode('utf-8')).hexdigest()[:12]
    stage = ROOT / '.build' / 'nes-compiler' / f'{revision[:8]}-{identity}'
    source = stage / 'source'
    if not source.is_dir():
        shutil.copytree(engine / 'recompiler', source)
    common = stage / 'common'
    if not common.is_dir():
        shutil.copytree(engine / 'common', common)
    codegen = source / 'src/cyc_codegen.c'
    source_changed = not codegen.is_file() or codegen.read_text(encoding='utf-8') != patched
    if source_changed:
        codegen.write_text(patched, encoding='utf-8')
    build = stage / 'build'
    compiler = build / 'Release/NESRecomp.exe'
    if source_changed or not compiler.is_file():
        emit('Building NES compiler with full native NROM coverage…')
        run([cmake, '-S', source, '-B', build, '-G', generator, '-A', 'x64'], timeout=600)
        run([cmake, '--build', build, '--config', 'Release', '--parallel', '4'], timeout=1800)
    if not compiler.is_file():
        raise ConversionError('NESRecomp produced no compiler executable.')
    return compiler
