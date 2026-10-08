"""Static 68000 instruction translation without a C-call guest-stack model.

The pinned upstream semantic helpers retain their licence. At conversion time,
each decoded ROM instruction selects one operation body, with literal operands.
Covered ROM execution never calls the interpreter or its opcode decoder. The
separate reference path continues to fetch and decode live bytes independently.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import shutil

from .core import ConversionError, run, serialized_setup, toolchain
from .paths import ROOT, ASSETS
from .library import atomic_json


def _masked(source: str) -> str:
    """Preserve offsets while hiding C comments and quoted literals."""
    pattern = r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\''
    return re.sub(pattern, lambda m: ''.join('\n' if c == '\n' else ' ' for c in m[0]), source)


def operation_bodies(source: str) -> dict[str, str]:
    start = source.index('switch (ins->mnemonic)', source.index('static M68kiStatus exec_one('))
    masked = _masked(source)
    opening = masked.index('{', start)
    level = 1
    cursor = opening + 1
    labels = []
    case_label = re.compile(r'(?:case\s+(MN_\w+)|default)\s*:')
    while level:
        label = case_label.match(masked, cursor) if level == 1 else None
        if label:
            labels.append((label[1], cursor, cursor + len(label[0])))
            cursor += len(label[0]); continue
        level += (masked[cursor] == '{') - (masked[cursor] == '}')
        cursor += 1
    bodies = {}
    pending = []
    for i, (name, _, end) in enumerate(labels):
        if name is None:
            continue
        pending.append(name)
        stop = labels[i + 1][1] if i + 1 < len(labels) else cursor - 1
        if not masked[end:stop].strip():
            continue
        body = source[end:stop].strip()
        for item in pending:
            bodies[item] = body
        pending.clear()
    if pending or len(bodies) < 60:
        raise ConversionError('Pinned 68000 semantics changed; operation extraction refused.')
    return bodies


def mnemonic_names(engine: Path) -> list[str]:
    header = (engine / 'external/m68k-recomp-core/common/m68k_decoder.h').read_text(encoding='utf-8')
    block = _masked(header).split('MN_OTHER', 1)[1].split('} M68KMnemonic', 1)[0]
    return ['MN_OTHER'] + re.findall(r'\bMN_\w+\b', block)


@serialized_setup
def decoder_tool(engine: Path) -> Path:
    project = ROOT / '.build/megadrive-step-decoder'
    project.mkdir(parents=True, exist_ok=True)
    source = (engine / 'runner/m68k_interp.c').read_text(encoding='utf-8')
    timing = source[source.index('static int interp_popcount16('):
                    source.index('static void interp_account_cycles(')]
    timing = timing[:timing.rfind('/* The emit_cycle_accounting')]
    (project / 'md_cycle_estimate.h').write_text(timing, encoding='utf-8')
    shutil.copy2(ASSETS / 'native/md_decode_dump.c', project / 'md_decode_dump.c')
    prefix = engine.as_posix()
    (project / 'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.20)
project(RetroMdDecode LANGUAGES C)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
add_executable(md_decode md_decode_dump.c "{prefix}/recompiler/src/m68k_decoder.c"
  "{prefix}/recompiler/src/m68k_validator.c" "{prefix}/recompiler/src/rom_parser.c")
target_include_directories(md_decode PRIVATE . "{prefix}/recompiler/src")
target_compile_options(md_decode PRIVATE /utf-8 /wd4996)
''', encoding='utf-8')
    cmake, generator = toolchain()
    run([cmake, '-S', project, '-B', project / 'build', '-G', generator, '-A', 'x64'],
        log=project / 'build.log')
    run([cmake, '--build', project / 'build', '--config', 'Release', '--parallel', '4'],
        log=project / 'build.log')
    return project / 'build/Release/md_decode.exe'


def decode(engine: Path, project: Path, rom_file: Path, addresses: set[int], ram_variants=(),
           *, follow_flow=True) -> list[dict]:
    listing = project / 'instruction-pcs.txt'
    ram = sorted({(item['address'], item['bytes']) for item in ram_variants})
    listing.write_text(''.join(f'{pc:06x}\n' for pc in sorted(addresses)) +
                       ''.join(f'{pc:06x}:{raw}\n' for pc, raw in ram), encoding='ascii')
    run([decoder_tool(engine), rom_file, listing, project / 'decoded-instructions.json',
         *(['--follow-flow'] if follow_flow else [])],
        cwd=project, log=project / 'decode.log')
    decoded = json.loads((project / 'decoded-instructions.json').read_text(encoding='utf-8'))
    return sorted(decoded, key=lambda ins: (ins['addr'], ins['words']))


def instruction_literal(ins: dict, name: str) -> str:
    words = ','.join(f'0x{word:04x}u' for word in ins['words'])
    tail = ','.join(str(ins[key]) for key in ('word_count', 'byte_length', 'src_ea',
        'dst_ea', 'reg', 'imm32', 'target_addr', 'has_target', 'dst_is_ea', 'predec_mem_form', 'mem_shift'))
    return f'{{0x{ins["addr"]:06x}u,{name},(M68KSize){ins["size"]},{{{words}}},{tail}}}'


def translated_body(ins: dict, name: str, body: str) -> str:
    # Only the selected operation is emitted. Substitute every operand read;
    # helper calls receive a compile-time constant descriptor, never a decoder.
    literals = {**ins, 'mnemonic': name}
    def replace(m):
        key, index = m[1], m[2]
        value = ins['words'][int(index)] if key == 'words' else literals[key]
        return f'({value})' if isinstance(value, int) else value
    body = re.sub(r'ins->(\w+)(?:\[(\d+)\])?', replace, body)
    return (f'    static const M68KInstr decoded = {instruction_literal(ins, name)};\n'
        '    const M68KInstr *ins = &decoded;\n'
        '    ExtR er; er_init(&er, ins);\n'
        f'    const uint32_t fall = 0x{ins["addr"] + ins["byte_length"]:06x}u;\n'
        '    *next_pc = fall;\n'
        f'    const M68KSize sz = (M68KSize){ins["size"]};\n'
        f'    const int dir = {(ins["words"][0] >> 8) & 1}, cc = {(ins["words"][0] >> 8) & 15};\n'
        '    ' + body + '\n')


def operation_name(ins: dict) -> str:
    suffix = ('_' + ''.join(f'{word:04x}' for word in ins['words'][:ins['word_count']])
              if ins['addr'] >= 0xff0000 else '')
    return f'rr_md_op_{ins["addr"]:06x}{suffix}'


def adapt_semantics(source: str) -> str:
    # MC68000 TRAP #n is a vectored exception, not a host C-function call.
    # Games install RAM IRQ stubs using it; RTE must see the nested 6-byte
    # SR/PC frame on SSP, including a trap from user mode. The existing CPU
    # layout keeps the active A7 and inactive stack slot together in snapshots.
    anchor = '    case MN_NOP:\n        return M68KI_OK;'
    trap = '''    case MN_TRAP: {
        uint16_t saved_sr = g_cpu.SR;
        rr_md_exception_frame(saved_sr, fall, (uint16_t)((saved_sr & ~0x8000u) | 0x2000u));
        *next_pc = m68k_read32((32u + (ins->words[0] & 15u)) * 4u);
        return M68KI_OK;
    }

'''
    if source.count(anchor) != 1:
        raise ConversionError('Pinned 68000 instruction semantics changed; TRAP adaptation refused.')
    stop = '''    case MN_STOP:
        if (!(g_cpu.SR & SR_S)) return M68KI_HALT_UNIMPL;
        rr_md_set_sr((uint16_t)ins->imm32);
        rr_md_cpu_stopped = 1;
        return M68KI_OK;

'''
    source = source.replace(anchor, trap + stop + anchor, 1)
    old_rte = '''        g_cpu.SR = pop16() & 0xA71Fu;     /* mask to valid SR bits (T,S,I,CCR) */
        *next_pc = pop32();'''
    if source.count(old_rte) != 1:
        raise ConversionError('Pinned 68000 RTE operation changed; stack-mode adaptation refused.')
    source = source.replace(old_rte, '''        if (!(g_cpu.SR & SR_S)) return M68KI_HALT_UNIMPL;
        uint16_t restored_sr = pop16();
        *next_pc = pop32(); /* Read the entire frame on SSP, then select A7. */
        rr_md_set_sr(restored_sr);''', 1)
    old_move = 'if (!ins->dst_is_ea) g_cpu.SR = (uint16_t)(read_ea(ins, ins->src_ea, M68K_SIZE_W, &er) & 0xA71Fu);'
    if source.count(old_move) != 1:
        raise ConversionError('Pinned 68000 MOVE to SR changed; stack-mode adaptation refused.')
    source = source.replace(old_move, '''if (!ins->dst_is_ea) {
            if (!(g_cpu.SR & SR_S)) return M68KI_HALT_UNIMPL;
            uint16_t value = (uint16_t)read_ea(ins, ins->src_ea, M68K_SIZE_W, &er);
            rr_md_set_sr(value);
        }''', 1)
    for mnemonic, operator in (('ORI', '|'), ('ANDI', '&'), ('EORI', '^')):
        pattern = rf'case MN_{mnemonic}_TO_SR:[^\n]+'
        body = (f'case MN_{mnemonic}_TO_SR:\n'
                '        if (!(g_cpu.SR & SR_S)) return M68KI_HALT_UNIMPL;\n'
                f'        rr_md_set_sr((uint16_t)(g_cpu.SR {operator} ins->imm32)); return M68KI_OK;')
        source, matches = re.subn(pattern, body, source)
        if matches != 1:
            raise ConversionError('Pinned 68000 SR operation changed; stack-mode adaptation refused.')
    source = source.replace('    case MN_MOVE_USP:\n',
        '    case MN_MOVE_USP:\n        if (!(g_cpu.SR & SR_S)) return M68KI_HALT_UNIMPL;\n', 1)
    # Byte accesses via A7 still move the stack by a word on MC68000.
    source = source.replace('int mode = (ea >> 3) & 7, reg = ea & 7, sb = szbytes(sz);',
        'int mode = (ea >> 3) & 7, reg = ea & 7, sb = szbytes(sz);\n'
        '    if (sz == M68K_SIZE_B && reg == 7) sb = 2;')
    source = source.replace('g_cpu.A[ay] += sb;',
        'g_cpu.A[ay] += (sz == M68K_SIZE_B && ay == 7) ? 2 : sb;')
    source = source.replace('g_cpu.A[ax] += sb;',
        'g_cpu.A[ax] += (sz == M68K_SIZE_B && ax == 7) ? 2 : sb;')
    return source


def generate_steps(engine: Path, project: Path, rom, addresses: set[int], ram_variants=(),
                   *, follow_flow=True) -> dict:
    source = adapt_semantics((engine / 'runner/m68k_interp.c').read_text(encoding='utf-8'))
    bodies, names = operation_bodies(source), mnemonic_names(engine)
    helper = source[source.index('static uint32_t szmask('):source.index('static uint8_t *s_exec_cov')]
    helper = helper[:helper.rfind('/* =====')]  # remove coverage section heading
    helper = ('/* Upstream semantic helpers: see embedded GenesisRecomp notices. */\n'
        '#pragma once\n#include "md_native_steps.h"\n#include <stddef.h>\n'
        '#define s_illegal_ea rr_md_illegal_ea\nstatic void discover(uint32_t pc) {(void)pc;}\n' + helper)
    write_changed(project / 'md_step_semantics.h', helper)
    decoded = decode(engine, project, project / 'cartridge.bin', addresses, ram_variants,
                     follow_flow=follow_flow)
    instructions = [ins for ins in decoded if names[ins['mnemonic']] in bodies]
    if not instructions:
        raise ConversionError('No supported 68000 operations found for native translation.')
    generated = project / 'steps'
    generated.mkdir(exist_ok=True)
    # Use stable address partitions so a few new observations only rebuild
    # the translation units they touch. Avoid unnecessary MSVC recompilation.
    chunks = [[] for _ in range(32)]
    for ins in instructions:
        name = names[ins['mnemonic']]
        function = (f'M68kiStatus {operation_name(ins)}(uint32_t *next_pc) {{\n' +
                    translated_body(ins, name, bodies[name]) + '}\n')
        chunks[(ins['addr'] >> 1) % 32].append(function)
    for index, chunk in enumerate(chunks):
        write_changed(generated / f'md_step_part{index:02d}.c',
            '#include "md_step_semantics.h"\n' + '\n'.join(chunk))
    declarations = ''.join(f'extern M68kiStatus {operation_name(ins)}(uint32_t *);\n'
                           for ins in instructions)
    table = 'static const RrMdNativeStep entries[] = {\n' + ',\n'.join(
        '{' + instruction_literal(ins, names[ins['mnemonic']]) +
        f',{max(4, ins["cycles"])}u,{operation_name(ins)}' + '}' for ins in instructions) + '\n};\n'
    # O(1) two-level lookup: empty ROM pages cost only one small index.
    pages = {}; count = (len(rom.data) + 255) // 256
    for index, ins in enumerate(instructions, 1):
        if ins['addr'] >= len(rom.data):
            continue
        pages.setdefault(ins['addr'] >> 8, [0] * 128)[(ins['addr'] & 255) >> 1] = index
    ordered = sorted(pages)
    offsets = {page: index + 1 for index, page in enumerate(ordered)}
    mapping = (f'static const unsigned short page_map[{count}] = {{' +
               ','.join(str(offsets.get(page, 0)) for page in range(count)) + '};\n')
    mapping += 'static const unsigned slots[][128] = {\n' + ',\n'.join(
        '{' + ','.join(map(str, pages[page])) + '}' for page in ordered) + '\n};\n'
    ram_indices = [index for index, ins in enumerate(instructions) if ins['addr'] >= 0xff0000]
    ram = ''
    if ram_indices:
        ram = ('static const unsigned ram_entries[] = {' + ','.join(map(str, ram_indices)) + '};\n' +
               f'''static const RrMdNativeStep *ram_lookup(uint32_t pc) {{
    unsigned low = 0, high = {len(ram_indices)};
    while (low < high) {{
        unsigned mid = low + (high - low) / 2;
        if (entries[ram_entries[mid]].instruction.addr < pc) low = mid + 1;
        else high = mid;
    }}
    for (unsigned i = low; i < {len(ram_indices)} && entries[ram_entries[i]].instruction.addr == pc; ++i) {{
        const RrMdNativeStep *op = &entries[ram_entries[i]];
        int matches = 1;
        for (int n = 0; n < op->instruction.word_count; ++n) {{
            unsigned offset = (pc + n * 2) & 0xffffu;
            unsigned word = ((unsigned)g_ram[offset] << 8) | g_ram[(offset + 1) & 0xffffu];
            if (word != op->instruction.words[n]) {{ matches = 0; break; }}
        }}
        if (matches) return op;
    }}
    return NULL;
}}
''')
    lookup = f'''const RrMdNativeStep *rr_md_native_lookup(uint32_t pc) {{
    {'if (!(pc & 1u) && pc >= 0xff0000u) return ram_lookup(pc);' if ram_indices else ''}
    if ((pc & 1u) || pc >= {len(rom.data)}u) return NULL;
    unsigned page = page_map[pc >> 8];
    if (!page) return NULL;
    unsigned index = slots[page - 1][(pc & 255u) >> 1];
    return index ? &entries[index - 1] : NULL;
}}
'''
    write_changed(generated / 'md_step_index.c', '#include "md_native_steps.h"\n#include <stddef.h>\n' +
                  declarations + table + mapping + ram + lookup)
    accepted_seeds = sum(ins['addr'] in addresses or ins['addr'] >= 0xff0000 for ins in instructions)
    audit = {'schema': 2, 'translated_instructions': len(instructions),
             'guarded_ram_variants': len(ram_indices),
             'requested_rom_entries': len(addresses), 'follow_static_flow': follow_flow,
             'additional_rom_instructions': len(instructions) - accepted_seeds,
             'rejected_or_unimplemented': len(addresses) + len(ram_variants) - accepted_seeds,
             'rom_sha256': rom.sha256, 'semantics_sha256': hashlib.sha256(source.encode()).hexdigest()}
    atomic_json(project / 'step-analysis.json', audit)
    return audit


def write_changed(path: Path, source: str) -> None:
    if not path.is_file() or path.read_text(encoding='utf-8') != source:
        path.write_text(source, encoding='utf-8')


def adapt_interpreter(source: str) -> str:
    source = adapt_semantics(source)
    source = source.replace('#include "m68k_interp.h"',
        '#include "m68k_interp.h"\n#include "retro_md_game.h"\n#include "md_native_steps.h"\n'
        'extern int genesis_force_interp(void);', 1)
    source = source.replace('static int s_illegal_ea = 0;',
                            'int rr_md_illegal_ea = 0;\n#define s_illegal_ea rr_md_illegal_ea', 1)
    wrapper = '''static bool rr_md_decode(const GenesisRom *rom, uint32_t pc, M68KInstr *ins) {
    if (!genesis_force_interp()) {
        const RrMdNativeStep *op = rr_md_native_lookup(pc);
        if (op) { *ins = op->instruction; return true; }
    }
    return m68k_decode(rom, pc, ins);
}

'''
    source = source.replace('static M68kiStatus exec_one(', wrapper + 'static M68kiStatus exec_one(', 1)
    source = source.replace('    cov_mark(ins->addr);',
        '    if (!genesis_force_interp()) {\n'
        '        const RrMdNativeStep *op = rr_md_native_lookup(ins->addr);\n'
        '        if (op) return op->execute(next_pc);\n    }\n    cov_mark(ins->addr);', 1)
    source = source.replace('m68k_decode(busview(), pc, &ins)', 'rr_md_decode(busview(), pc, &ins)')
    # Only successfully retired fallback ROM instructions are learned. An IRQ
    # RTE peek and invalid/unimplemented operations do not count as coverage.
    source = source.replace('static void interp_account_cycles(const M68KInstr *ins)',
        'static void interp_account_cycles(const M68KInstr *ins, const RrMdNativeStep *retired_native)', 1)
    source = source.replace('    int cyc = -1;',
        '    if (!retired_native) {\n'
        '        rr16_note_rom_fallback(ins->addr);\n'
        '        rr16_note_ram_instruction(ins);\n    }\n'
        '    int cyc = retired_native ? (int)retired_native->cycles : -1;', 1)
    source = source.replace('M68kiStatus st = exec_one(&ins, &next);',
        'const RrMdNativeStep *retired_native = genesis_force_interp() ? NULL : rr_md_native_lookup(ins.addr);\n'
        '    M68kiStatus st = exec_one(&ins, &next);')
    source = source.replace('interp_account_cycles(&ins);', 'interp_account_cycles(&ins, retired_native);')
    source = source.replace('g_rte_pending = 1;\n            interp_account_cycles(&ins, retired_native);',
        'g_rte_pending = 1;\n            interp_account_cycles(&ins, NULL);')
    source = source.replace('if (pc >= ROM_SIZE)', 'if (!pc_fetchable(pc))')
    source = source.replace('if (depth == 0 && ins.mnemonic == MN_RTE)',
                            'if (ins.mnemonic == MN_RTE)')
    source = source.replace('M68kiStatus m68k_interp_step(void) {', '''M68kiStatus m68k_interp_step(void) {
    if (rr_md_cpu_stopped) {
        /* Advance the scheduler without fetching or retiring an instruction.
         * An unmasked IRQ selects its vector and clears STOP in the frame helper. */
        g_audio_cycle_counter += 4; g_cycle_accumulator += 4;
        if (g_cycle_accumulator >= g_vblank_threshold) glue_check_vblank();
        GEN_COSIM_TICK(4);
        return M68KI_OK;
    }''', 1)
    return source


def adapt_cpu_snapshot(source: str) -> str:
    """Include STOP in rollback/F1 state without changing the pinned CPU ABI."""
    from .gun16_runtime import replace
    start = source.index('static size_t sec_cpu_save(')
    end = source.index('static size_t sec_ram_save(', start)
    original = source[start:end]
    adapted = original.replace('sizeof g_cpu', '(sizeof g_cpu + sizeof rr_md_cpu_stopped)')
    # Copy CPU and latch separately; they are not adjacent globals.
    adapted = replace(adapted,
        '    memcpy(dst, &g_cpu, (sizeof g_cpu + sizeof rr_md_cpu_stopped));',
        '    memcpy(dst, &g_cpu, sizeof g_cpu);\n'
        '    memcpy((uint8_t *)dst + sizeof g_cpu, &rr_md_cpu_stopped, sizeof rr_md_cpu_stopped);')
    adapted = replace(adapted,
        '    memcpy(&g_cpu, src, (sizeof g_cpu + sizeof rr_md_cpu_stopped));',
        '    uint32_t stopped;\n'
        '    memcpy(&stopped, (const uint8_t *)src + sizeof g_cpu, sizeof stopped);\n'
        '    if (stopped > 1) return 0;\n'
        '    memcpy(&g_cpu, src, sizeof g_cpu);\n'
        '    rr_md_cpu_stopped = stopped;')
    return '#include "md_native_steps.h"\n' + source[:start] + adapted + source[end:]


def adapt_irq_glue(source: str) -> str:
    # Function-AOT used a scratch interrupt stack and restored all registers.
    # These games inspect the real exception frame or change the main-context
    # return address. Preserve those changes and let their RTE restore PC/SR.
    irq = '''static void rr_md_service_irq(int level, uint32_t vector, GVDP *vdp) {
    uint32_t before = g_audio_cycle_counter;
    uint32_t rebase = g_68k_stamp_rebase;
    g_68k_stamp_rebase = machine_z80_stamp() - g_audio_cycle_counter * 7u;
    uint16_t sr = g_cpu.SR;
    uint32_t pc = g_cpu.PC;
    rr_md_exception_frame(sr, pc, (uint16_t)((sr & ~0x8700u) | 0x2000u | ((unsigned)level << 8)));
    s_in_vblank_service = 1;
    uint8_t vb = vdp->in_vblank;
    if (level == 6) vdp->in_vblank = 1;
    g_audio_cycle_counter += 44; g_cycle_accumulator += 44;
    M68kiStatus status = m68k_interp_run_handler(m68k_read32(vector) & 0xffffffu);
    if (status == M68KI_OK) status = m68k_interp_step(); /* real RTE pops the exception frame */
    if (status != M68KI_OK) {
        rr16_note_fault();
        fprintf(stderr, "[68000 IRQ] HALT status=%d level=%d pc=%06x opcode=%04x\\n",
                status, level, g_m68ki_bad_pc, g_m68ki_bad_op);
    }
    s_irq_cycle_debt += g_audio_cycle_counter - before;
    if (s_irq_cycle_debt && s_irq_cycle_debt_level < level) s_irq_cycle_debt_level = level;
    s_in_vblank_service = 0;
    vdp->in_vblank = vb;
    g_68k_stamp_rebase = rebase;
    s_game_yielded_vblank = 0;
}

'''
    source = '#include "md_native_steps.h"\n' + source
    source = source.replace('static void own_deliver_vint(GVDP *vdp)\n{',
        irq + 'static void own_deliver_vint(GVDP *vdp)\n{\n    rr_md_service_irq(6, 0x78, vdp); return;', 1)
    source = source.replace('} else if (level == 4 && imask < 4) {',
        '} else if (level == 4 && imask < 4) {\n        rr_md_service_irq(4, 0x70, vdp); return;', 1)
    return source
