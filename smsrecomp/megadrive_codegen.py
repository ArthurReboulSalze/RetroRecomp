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
from .platforms import build_executable, cmake_target_args, build_jobs
from .library import atomic_json
from .m68000 import (_masked, operation_bodies, mnemonic_names,
                     adapt_cycle_estimates, instruction_literal, adapt_semantics)


@serialized_setup
def decoder_tool(engine: Path) -> Path:
    project = ROOT / '.build/megadrive-step-decoder'
    project.mkdir(parents=True, exist_ok=True)
    from .library import entry_lock
    # The thread lock covers one batch process. Independent validation tools
    # and a second converter instance must not write the same MSVC objects.
    with entry_lock(project):
        return _decoder_tool_locked(engine,project)


def _decoder_tool_locked(engine: Path,project: Path) -> Path:
    source = adapt_cycle_estimates((engine / 'runner/m68k_interp.c').read_text(encoding='utf-8'))
    timing = source[source.index('static int interp_popcount16('):
                    source.index('static void interp_account_cycles(')]
    timing = timing[:timing.rfind('/* The emit_cycle_accounting')]
    write_changed(project/'md_cycle_estimate.h',timing)
    for name in ('md_decode_dump.c','md_exception_decode.h'):
        write_changed(project/name,(ASSETS/'native'/name).read_text(encoding='utf-8'))
    prefix = engine.as_posix()
    from .gun16_runtime import replace
    parser=replace((engine/'recompiler/src/rom_parser.c').read_text(encoding='utf-8'),
                   '#include "rom_parser.h"',
                   '#include "rom_parser.h"\n#undef GENESIS_ROM_MAX_SIZE\n#define GENESIS_ROM_MAX_SIZE 0x800000')
    write_changed(project/'md_rom_parser.c',parser)
    write_changed(project/'CMakeLists.txt',f'''cmake_minimum_required(VERSION 3.20)
project(RetroMdDecode LANGUAGES C)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
add_executable(md_decode md_decode_dump.c "{prefix}/recompiler/src/m68k_decoder.c"
  "{prefix}/recompiler/src/m68k_validator.c" md_rom_parser.c)
target_include_directories(md_decode PRIVATE . "{prefix}/recompiler/src")
if(MSVC)
  target_compile_options(md_decode PRIVATE /utf-8 /wd4996)
endif()
''')
    cmake, generator = toolchain()
    run([cmake, '-S', project, '-B', project / 'build', '-G', generator, *cmake_target_args()],
        log=project / 'build.log')
    run([cmake, '--build', project / 'build', '--config', 'Release', '--parallel', build_jobs()],
        log=project / 'build.log')
    return build_executable(project / 'build','md_decode')


def jump_table_entries(data: bytes, reached: set[int], examined: set[int] | None = None) -> set[int]:
    """Expand reached runs of ROM jump stubs; never scan arbitrary pointers.

    Public function tables can contain adjacent JMP (d16,PC), JMP abs.l or
    BRA.w instructions. One reached slot anchors a run of at least three
    equal-width jumps. Every displacement must address aligned ROM code.
    Other data, indirect targets and RAM still need observed execution.
    """
    examined = set() if examined is None else examined
    size, result = len(data), set()

    def thunk(pc, opcode, stride):
        if pc < 0x200 or pc + stride > size or data[pc:pc + 2] != opcode:
            return False
        target = (int.from_bytes(data[pc + 2:pc + 6], 'big') if stride == 6 else
                  pc + 2 + int.from_bytes(data[pc + 2:pc + 4], 'big', signed=True)) & 0xffffff
        return 0x200 <= target < size and not target & 1

    for pc in sorted(reached - examined):
        examined.add(pc)
        if pc < 0x200 or pc & 1 or pc + 4 > size:
            continue
        opcode = data[pc:pc + 2]
        if opcode not in (b'\x4e\xfa', b'\x4e\xf9', b'\x60\x00'):
            continue
        stride = 6 if opcode == b'\x4e\xf9' else 4
        if not thunk(pc, opcode, stride):
            continue
        first = last = pc
        count = 1
        while count < 256 and thunk(first - stride, opcode, stride):
            first -= stride; count += 1
        while count < 256 and thunk(last + stride, opcode, stride):
            last += stride; count += 1
        if count >= 3:
            slots = set(range(first, last + 1, stride))
            examined.update(slots)
            result.update(slots)
    return result


def decode(engine: Path, project: Path, rom_file: Path, addresses: set[int], ram_variants=(),
           *, follow_flow=True) -> list[dict]:
    listing = project / 'instruction-pcs.txt'
    ram = sorted({(item['address'], item['bytes']) for item in ram_variants})
    tool = decoder_tool(engine)
    pending, examined = set(addresses), set()
    data = rom_file.read_bytes() if follow_flow else b''
    while True:
        if follow_flow:
            pending.update(jump_table_entries(data, pending, examined))
        listing.write_text(''.join(f'{pc:06x}\n' for pc in sorted(pending)) +
                           ''.join(f'{pc:06x}:{raw}\n' for pc, raw in ram), encoding='ascii')
        run([tool, rom_file, listing, project / 'decoded-instructions.json',
             *(['--follow-flow'] if follow_flow else [])],
            cwd=project, log=project / 'decode.log')
        decoded = json.loads((project / 'decoded-instructions.json').read_text(encoding='utf-8'))
        reached = {ins['addr'] for ins in decoded if ins['addr'] < len(data)}
        extra = jump_table_entries(data, reached, examined) - reached if follow_flow else set()
        if not extra:
            break
        # Finite closure: each pass adds previously unseen ROM instruction
        # slots, with the same legal-instruction decoder and validation gates.
        pending.update(reached | extra)
    return sorted(decoded, key=lambda ins: (ins['addr'], ins['words']))


def translated_body(ins: dict, name: str, body: str, *, mapper=False) -> str:
    # Only the selected operation is emitted. Substitute every operand read;
    # helper calls receive a compile-time constant descriptor, never a decoder.
    literals = {**ins, 'mnemonic': name}
    ram = ins['addr'] >= 0xe00000 or mapper
    def replace(m):
        key, index = m[1], m[2]
        if ram and key in ('addr', 'target_addr'):
            return f'ins->{key}'
        value = ins['words'][int(index)] if key == 'words' else literals[key]
        return f'({value})' if isinstance(value, int) else value
    body = re.sub(r'ins->(\w+)(?:\[(\d+)\])?', replace, body)
    descriptor = (f'    M68KInstr decoded = {instruction_literal(ins, name)};\n'
                  '    rr_md_relocate_instruction(&decoded, g_cpu.PC & 0xffffffu);\n' if ram else
                  f'    static const M68KInstr decoded = {instruction_literal(ins, name)};\n')
    fall = f'ins->addr + {ins["byte_length"]}u' if ram else f'0x{ins["addr"] + ins["byte_length"]:06x}u'
    return (descriptor +
        '    const M68KInstr *ins = &decoded;\n'
        '    ExtR er; er_init(&er, ins);\n'
        f'    const uint32_t fall = {fall};\n'
        '    *next_pc = fall;\n'
        f'    const M68KSize sz = (M68KSize){ins["size"]};\n'
        f'    const int dir = {(ins["words"][0] >> 8) & 1}, cc = {(ins["words"][0] >> 8) & 15};\n'
        '    ' + body + '\n')


def operation_name(ins: dict) -> str:
    suffix = ('_' + ''.join(f'{word:04x}' for word in ins['words'][:ins['word_count']])
              if ins['addr'] >= 0xe00000 else '')
    return f'rr_md_op_{ins["addr"]:06x}{suffix}'


def generate_steps(engine: Path, project: Path, rom, addresses: set[int], ram_variants=(),
                   *, follow_flow=True) -> dict:
    write_changed(project / 'm68000_state_helpers.h',
                  (ASSETS / 'native/m68000_state_helpers.h').read_text(encoding='utf-8'))
    from .megadrive_hardware import bank_mapper
    mapper = bank_mapper(rom) is not None
    source = adapt_semantics((engine / 'runner/m68k_interp.c').read_text(encoding='utf-8'))
    bodies, names = operation_bodies(source), mnemonic_names(engine)
    helper = source[source.index('static uint32_t szmask('):source.index('static uint8_t *s_exec_cov')]
    helper = helper[:helper.rfind('/* =====')]  # remove coverage section heading
    helper = ('/* Upstream semantic helpers: see embedded GenesisRecomp notices. */\n'
        '#pragma once\n#include "md_native_steps.h"\n#include "md_prefetch.h"\n#include <stddef.h>\n'
        '#define s_illegal_ea rr_md_illegal_ea\nstatic void discover(uint32_t pc) {(void)pc;}\n' + helper)
    timing = source[source.index('static int interp_ea_read_cost('):
                    source.index('static int interp_estimate_cycles(')]
    helper += '\n' + timing
    write_changed(project / 'md_step_semantics.h', helper)
    from .megadrive import valid_ram_variant
    # One body per physical byte sequence, shared by all 32 RAM aliases.
    # Normalize only the lookup key; execution relocates to the actual PC.
    ram_variants = [{'address': addr, 'bytes': raw} for addr, raw in sorted({
        (0xe00000 | (item['address'] & 0xffff), item['bytes'].lower())
        for item in ram_variants if valid_ram_variant(item)})]
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
                    translated_body(ins, name, bodies[name], mapper=mapper) + '}\n')
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
    ram_indices = [index for index, ins in enumerate(instructions) if ins['addr'] >= 0xe00000]
    ram = ''
    if ram_indices:
        ram = ('static const unsigned ram_entries[] = {' + ','.join(map(str, ram_indices)) + '};\n' +
               f'''static const RrMdNativeStep *ram_lookup(uint32_t pc) {{
    unsigned low = 0, high = {len(ram_indices)};
    unsigned key = 0xe00000u | (pc & 0xffffu);
    while (low < high) {{
        unsigned mid = low + (high - low) / 2;
        if (entries[ram_entries[mid]].instruction.addr < key) low = mid + 1;
        else high = mid;
    }}
    for (unsigned i = low; i < {len(ram_indices)} && entries[ram_entries[i]].instruction.addr == key; ++i) {{
        const RrMdNativeStep *op = &entries[ram_entries[i]];
        if (op->instruction.byte_length > 0x1000000u - pc) continue;
        int matches = 1;
        for (int n = 0; n < op->instruction.word_count; ++n) {{
            unsigned offset = (pc + n * 2) & 0xffffu;
            unsigned word = rr_md_instruction_word(pc + n * 2u);
            if (word != op->instruction.words[n]) {{ matches = 0; break; }}
        }}
        if (matches) return op;
    }}
    return NULL;
}}
''')
    lookup = f'''const RrMdNativeStep *rr_md_native_lookup(uint32_t pc) {{
    pc &= 0xffffffu;
    {'if (!(pc & 1u) && pc >= 0xe00000u) return ram_lookup(pc);' if ram_indices else ''}
    if ((pc & 1u) || pc >= {len(rom.data)}u) return NULL;
    unsigned page = page_map[pc >> 8];
    if (!page) return NULL;
    unsigned index = slots[page - 1][(pc & 255u) >> 1];
    return index ? &entries[index - 1] : NULL;
}}
'''
    if mapper:
        lookup=f'''static const RrMdNativeStep *physical_lookup(uint32_t offset,uint32_t pc) {{
    if(offset>={len(rom.data)}u)return NULL;
    unsigned page=page_map[offset>>8];if(!page)return NULL;
    unsigned index=slots[page-1][(offset&255u)>>1];if(!index)return NULL;
    const RrMdNativeStep *op=&entries[index-1];
    for(unsigned n=0;n<(unsigned)op->instruction.word_count;++n)
        if(rr_md_instruction_word(pc+n*2u)!=op->instruction.words[n])return NULL;
    return op;
}}
const RrMdNativeStep *rr_md_native_lookup(uint32_t pc) {{
    pc&=0xffffffu;if(pc&1u)return NULL;
    {'if(pc>=0xe00000u)return ram_lookup(pc);' if ram_indices else ''}
    if(pc>=0x400000u)return NULL;
    uint32_t offset=rr_md_cart_rom_offset(pc);
    const RrMdNativeStep *op=physical_lookup(offset,pc);if(op)return op;
    /* A bank write does not flush words already in the 68000 prefetch.
     * Select another fixed translated image only after all word guards pass. */
    for(uint32_t page=0;page<{len(rom.data)}u;page+=0x80000u) {{
        uint32_t candidate=page+(pc&0x7ffffu);if(candidate==offset)continue;
        op=physical_lookup(candidate,pc);if(op)return op;
    }}
    return NULL;
}}
'''
    write_changed(generated / 'md_step_index.c', '#include "md_native_steps.h"\n#include "md_prefetch.h"\n#include <stddef.h>\n' +
                  declarations + table + mapping + ram + lookup)
    accepted_seeds = sum(ins['addr'] in addresses or ins['addr'] >= 0xe00000 for ins in instructions)
    audit = {'schema': 2, 'translated_instructions': len(instructions),
             'guarded_ram_variants': len(ram_indices),
             'physical_rom_mapper': 'sega_512k' if mapper else None,
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
    from .megadrive_memory import runtime_source
    source = runtime_source(source, 'interpreter')
    source = adapt_semantics(source)
    source = source.replace('#include "m68k_interp.h"',
        '#include "m68k_interp.h"\n#include "retro_md_game.h"\n#include "md_native_steps.h"\n'
        '#include "md_exception_decode.h"\n#include "md_bus_scheduler.h"\nunsigned rr_md_exception_cycles, rr_md_trace_suppressed;\n'
        'static int interp_ea_read_cost(int ea, M68KSize sz);\n'
        'static int interp_estimate_cycles(const M68KInstr *ins);\n'
        'extern int genesis_force_interp(void);', 1)
    source = source.replace('static int s_illegal_ea = 0;',
                            'int rr_md_illegal_ea = 0;\n#define s_illegal_ea rr_md_illegal_ea', 1)
    source = source.replace('/* A PC is fetchable',
        'static int eval_cond(int cc);\n#include "md_prefetch.inc"\n\n/* A PC is fetchable',1)
    wrapper = '''static const RrMdNativeStep *rr_prepared_native;
static bool rr_md_decode(const GenesisRom *rom, uint32_t pc, M68KInstr *ins) {
    rr_pf_begin(pc);rr_prepared_native=NULL;
    if (!genesis_force_interp()) {
        const RrMdNativeStep *op = rr_md_native_lookup(pc);
        if (op) {
            *ins = op->instruction;
            if (pc != ins->addr) rr_md_relocate_instruction(ins, pc);
            rr_prepared_native=op;
        }
    }
    GenesisRom view=*rom;view.read8_override=rr_pf_fetch8;
    if(!rr_prepared_native) {
        if (!m68k_decode(&view, pc, ins)) return false;
        rr_md_normalize_exception(ins);
    }
    rr_pf_prepare(ins);
    /* A Z80 write during an extension fetch may change the prepared image.
     * Decode that image once on the reference path and select its exact body;
     * never execute a literal operand that differs from the fetched word. */
    if(rr_md_prefetch_active()) {
        int changed=0;
        for(unsigned n=0;n<(unsigned)ins->word_count;++n) {
            if((rr_pf_image_valid&(1u<<n)) && ins->words[n]!=rr_pf_image[n]) { changed=1;break; }
        }
        if(changed) {
            if(!m68k_decode(&view,pc,ins))return false;
            rr_md_normalize_exception(ins);
        }
        if(!genesis_force_interp() && (changed || !rr_prepared_native))
            rr_prepared_native=rr_md_native_lookup(pc);
    }
    rr_md_rom_fetch_offset=rr_md_cart_code_offset(pc,ins->words,(unsigned)ins->word_count);
    return true;
}

'''
    source = source.replace('static M68kiStatus exec_one(', wrapper + 'static M68kiStatus exec_one_raw(', 1)
    # All execution callers share the retirement boundary. T is sampled before
    # execution, including an instruction which changes SR. Complete a trap
    # first, then stack trace before cycle accounting can enter IRQ/scheduler.
    retirement = '''static M68kiStatus exec_one(const M68KInstr *ins, uint32_t *next_pc) {
    unsigned trace = g_cpu.SR & 0x8000u;
    rr_md_exception_cycles = rr_md_trace_suppressed = 0;
    const RrMdNativeStep *op = rr_prepared_native;
    M68kiStatus status = op ? op->execute(next_pc) : exec_one_raw(ins, next_pc);
    if (status == M68KI_OK && !s_illegal_ea && trace && !rr_md_trace_suppressed) {
        rr_pf_finish(ins,*next_pc); /* Complete the instruction before tracing it. */
        unsigned clocks = rr_md_exception_cycles ? rr_md_exception_cycles : rr_pf_control_cycles ? rr_pf_control_cycles :
            op ? op->cycles : (unsigned)interp_estimate_cycles(ins);
        rr_md_instruction_exception(next_pc, 9, *next_pc, clocks + 34u);
    }
    rr_md_trace_suppressed = 0; /* Never retained across yields or snapshots. */
    if(status==M68KI_OK)rr_pf_finish(ins,*next_pc);
    return status;
}

'''
    account_anchor = 'static void interp_account_cycles(const M68KInstr *ins)'
    if source.count(account_anchor) != 1:
        raise ConversionError('Pinned 68000 retirement boundary changed; trace adaptation refused.')
    source = source.replace(account_anchor, retirement + account_anchor, 1)
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
        'const RrMdNativeStep *retired_native = rr_prepared_native;\n'
        '    M68kiStatus st = exec_one(&ins, &next);')
    source = source.replace('interp_account_cycles(&ins);', 'interp_account_cycles(&ins, retired_native);')
    accounting = source.index('static void interp_account_cycles(')
    source = source[:accounting] + source[accounting:].replace('    g_native_insn_count++;',
        '    if(rr_pf_control_cycles)cyc=(int)rr_pf_control_cycles;\n'
        '    if (rr_md_exception_cycles) cyc = (int)rr_md_exception_cycles;\n'
        '    rr_md_exception_cycles = 0; /* Consume before IRQs or frame yields. */\n'
        '    cyc = (int)rr_md_cpu_retire_cycles((unsigned)cyc);\n'
        '    g_native_insn_count++;', 1)
    source = source.replace('g_rte_pending = 1;\n            interp_account_cycles(&ins, retired_native);',
        'g_rte_pending = 1;\n            interp_account_cycles(&ins, NULL);')
    source = source.replace('if (pc >= ROM_SIZE)', 'if (!pc_fetchable(pc))')
    # A trap inside an IRQ handler has its own RTE. Execute nested returns and
    # stop only once the entry interrupt frame has actually been popped.
    handler_start = source.index('M68kiStatus m68k_interp_run_handler(')
    handler_end = source.index('M68kiStatus m68k_interp_run_ram_handler(', handler_start)
    handler = source[handler_start:handler_end]
    handler = handler.replace('    int depth = 0;', '    uint32_t handler_sp = g_cpu.A[7];\n    int depth = 0;', 1)
    peek = '''        if (depth == 0 && ins.mnemonic == MN_RTE)
            return M68KI_OK;                 /* handler's own return — stop, don't pop */'''
    if handler.count(peek) != 1:
        raise ConversionError('Pinned 68000 IRQ return changed; nested-frame adaptation refused.')
    handler = handler.replace(peek, '''        int handler_return = ins.mnemonic == MN_RTE &&
            (g_cpu.SR & SR_S) && g_cpu.A[7] == handler_sp;''', 1)
    handler = handler.replace('        interp_account_cycles(&ins, retired_native);',
        '        interp_account_cycles(&ins, retired_native);\n'
        '        if (handler_return) return M68KI_OK;', 1)
    source = source[:handler_start] + handler + source[handler_end:]
    source = source.replace('M68kiStatus m68k_interp_step(void) {', '''M68kiStatus m68k_interp_step(void) {
    if (rr_md_cpu_stopped) {
        /* Advance the scheduler without fetching or retiring an instruction.
         * An unmasked IRQ selects its vector and clears STOP in the frame helper. */
        unsigned idle = rr_md_cpu_stop_cycles();
        g_audio_cycle_counter += idle; g_cycle_accumulator += idle;
        if (g_cycle_accumulator >= g_vblank_threshold) glue_check_vblank();
        GEN_COSIM_TICK(idle);
        return M68KI_OK;
    }''', 1)
    return source


def adapt_cpu_snapshot(source: str) -> str:
    """Save pointer-free STOP/prefetch state; explicitly migrate prequeue states."""
    from .gun16_runtime import replace
    start = source.index('static size_t sec_cpu_save(')
    end = source.index('static size_t sec_ram_save(', start)
    original = source[start:end]
    adapted = '''int rr_md_cpu_snapshot_size(size_t len) {
    return len==sizeof g_cpu+4 || len==sizeof g_cpu+4+sizeof(RrMdPrefetch);
}
static int rr_md_cpu_snapshot_valid(const void *src,size_t len) {
    uint32_t stopped;RrMdPrefetch queue={0};M68KState cpu;
    if(!rr_md_cpu_snapshot_size(len))return 0;
    memcpy(&cpu,src,sizeof cpu);memcpy(&stopped,(const uint8_t *)src+sizeof cpu,4);
    if(stopped>1)return 0;
    if(len>sizeof cpu+4)memcpy(&queue,(const uint8_t *)src+sizeof cpu+4,sizeof queue);
    return queue.pc<=0xffffffu && !(queue.pc&1u) &&
        (queue.valid==0 || (queue.valid==2 && queue.pc==(cpu.PC&0xffffffu) && !stopped));
}
static size_t sec_cpu_save(void *dst,size_t cap) {
    size_t need=sizeof g_cpu+4+sizeof rr_md_prefetch;
    if(!dst)return need;
    if(cap<need)return 0;
    memcpy(dst,&g_cpu,sizeof g_cpu);
    memcpy((uint8_t *)dst+sizeof g_cpu,&rr_md_cpu_stopped,4);
    memcpy((uint8_t *)dst+sizeof g_cpu+4,&rr_md_prefetch,sizeof rr_md_prefetch);
    return need;
}
static int sec_cpu_load(const void *src,size_t len) {
    if(!rr_md_cpu_snapshot_valid(src,len))return 0;
    rr_md_prefetch_reset();
    memcpy(&g_cpu,src,sizeof g_cpu);
    memcpy(&rr_md_cpu_stopped,(const uint8_t *)src+sizeof g_cpu,4);
    if(len>sizeof g_cpu+4)memcpy(&rr_md_prefetch,(const uint8_t *)src+sizeof g_cpu+4,sizeof rr_md_prefetch);
    return 1;
}

'''
    return '#include "md_native_steps.h"\n#include "md_prefetch.h"\n' + source[:start] + adapted + source[end:]


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
