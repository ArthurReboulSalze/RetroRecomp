"""Build a private NESRecomp compiler with bank-independent native ROM coverage.

Hot discovered paths use upstream native blocks. Every remaining PRG position
has a ROM-specialized native body, shared across equivalent bytes and mapper
slots. Boundary operands are read on the live bus. The pinned checkout is
never edited.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import shutil

from .core import ConversionError, replace_once, run
from .paths import ROOT, ASSETS


def _replace_count(source: str, old: str, new: str, count: int) -> str:
    if source.count(old) != count:
        raise ConversionError(f'Pinned NES codegen changed around {old!r}.')
    return source.replace(old, new)


def _dense_codegen(source: str) -> str:
    # The dynamic-PC mode reuses the proven bus-cycle templates, but selects
    # the opcode and specializes operands at conversion time. It does not emit
    # or call an opcode decoder. Each body returns before remapping is possible.
    source = replace_once(source, '    uint8_t        opcode;\n} Emit;',
        '    uint8_t        opcode;\n'
        '    bool           dense;\n'
        '    uint8_t        dense_known, dense_bytes[2];\n} Emit;')
    source = replace_once(source, '#define INTERP(e) ((e)->p == NULL)',
                          '#define INTERP(e) ((e)->p == NULL || (e)->dense)')
    source = replace_once(source,
        'static void read_operand(Emit *e, int k, int f) {\n    if (INTERP(e))',
        '''static void read_operand(Emit *e, int k, int f) {
    if (e->dense && (e->dense_known & (1u << (k - 1))))
        ln(e, "b%d = cpu_read_rom((uint16_t)(pc + %d), 0x%02X, %s);",
           k, k, e->dense_bytes[k - 1], flags(f));
    else if (INTERP(e))''')
    source = replace_once(source,
        'static const char *operand(Emit *e, int k) {\n    if (INTERP(e))',
        '''static const char *operand(Emit *e, int k) {
    if (e->dense && (e->dense_known & (1u << (k - 1))))
        return str("0x%02X", e->dense_bytes[k - 1]);
    if (INTERP(e))''')
    source = replace_once(source,
        'static const char *operand16(Emit *e) {\n    if (INTERP(e))',
        '''static const char *operand16(Emit *e) {
    if (e->dense) return str("(uint16_t)(%s | %s << 8)", operand(e, 1), operand(e, 2));
    if (INTERP(e))''')
    source = replace_once(source,
        'static void emit_imm(Emit *e, const OpDef *d) {\n    if (INTERP(e))',
        '''static void emit_imm(Emit *e, const OpDef *d) {
    if (e->dense && (e->dense_known & 1))
        ln(e, "uint8_t v = cpu_read_rom((uint16_t)(pc + 1), 0x%02X, CYC_POLL | CYC_DONE);", e->dense_bytes[0]);
    else if (INTERP(e))''')
    source = replace_once(source,
        '        ln(e, "b1 = cpu_read((uint16_t)(pc + 1), CYC_POLL);");\n'
        '        ln(e, "uint16_t next = (uint16_t)(pc + 2), target = (uint16_t)(next + (int8_t)b1);");',
        '        read_operand(e, 1, POLL);\n'
        '        ln(e, "uint16_t next = (uint16_t)(pc + 2), target = (uint16_t)(next + (int8_t)%s);", operand(e, 1));')
    source = replace_once(source, 'static void emit_umbrella(',
        (ASSETS / 'native/nes_dense_codegen.inc').read_text(encoding='utf-8') + '\nstatic void emit_umbrella(')
    source = replace_once(source,
        '    for (uint32_t bank = 0; bank < p->banks; bank++)\n'
        '        for (uint32_t slot = 0; slot < SLOT_COUNT; slot++)\n'
        '            if (slot_used(p, bank, slot))',
        '    emit_dense_rom(p, f, prefix);\n\n'
        '    for (uint32_t bank = 0; bank < p->banks; bank++)\n'
        '        for (uint32_t slot = 0; slot < SLOT_COUNT; slot++)\n'
        '            if (slot_used(p, bank, slot))')
    source = replace_once(source,
        '        "    return v && ((v->bits[k >> 3] >> (k & 7)) & 1);\\n"',
        '        "    return (v && ((v->bits[k >> 3] >> (k & 7)) & 1)) || dense_has(addr);\\n"')
    source = replace_once(source,
        '        "        if (!v || !((v->bits[k >> 3] >> (k & 7)) & 1)) return;\\n"',
        '        "        if (!v || !((v->bits[k >> 3] >> (k & 7)) & 1)) {\\n"\n'
        '        "            if (!dense_has(pc)) return;\\n"\n'
        '        "            dense_step(pc); continue;\\n"\n'
        '        "        }\\n"')
    return source


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
    source = _dense_codegen(source)
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
        emit('Building NES compiler with bank-independent native ROM coverage…')
        run([cmake, '-S', source, '-B', build, '-G', generator, '-A', 'x64'], timeout=600)
        run([cmake, '--build', build, '--config', 'Release', '--parallel', '4'], timeout=1800)
    if not compiler.is_file():
        raise ConversionError('NESRecomp produced no compiler executable.')
    return compiler
