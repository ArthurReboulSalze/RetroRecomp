"""Guarded native code for the 68000 instructions a machine was seen running from RAM: the generator every 68000 computer shares.

A computer (the Sharp X68000, the Commodore Amiga...) loads its programs into RAM from a disk, so the code it runs is not known before it runs. A conversion
observes it on a fresh interpreted reference run, turns the observed instructions into native code that guards itself with a live comparison of the
instruction words (a changed word falls back to the counted interpreter), and checks the result against the reference. What is the same for every such
machine lives here; what is the machine's own is declared by its profile (`SystemProfile.observed_code`, an `ObservedCode`) or passed in by its generator:

* what the machine's code can look like: the apertures of its address space (`ObservedCode.apertures`), checked on every observed sample;
* where the body of an instruction comes from: an entry point named by the profile (`ObservedCode.bodies`, "module:function"), which answers an
  `InstructionBodies` for an engine checkout and the machine's C prefix. `recompiler_bodies` is the chain the Sharp X68000 uses (the Mega Drive recompiler's
  interpreter semantics with the shared state rules, executed by Musashi); the Amiga names its own (Moira) without a line of this module changing;
* the bus: the C that reads the bytes of an aperture (`code_view`), the machine's includes, and how a native step reaches its successor.

Nothing here knows a machine by name. The text this module writes for a machine is the text its generator wrote before it was moved here, byte for byte
(tests/test_m68k_observed.py and the A/B of UPGRADES.md).
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Callable

from .core import run, toolchain
from .m68000 import adapt_semantics, instruction_literal, mnemonic_names, operation_bodies
from .m68000_state_rules import adapt_state_rules
from .megadrive_codegen import write_changed
from .neogeo_codegen import decoder_tool, structural_body, structural_key
from .platforms import build_executable, cmake_target_args
from .systems.specs import ObservedCode  # noqa: F401  (the declaration a profile makes)


@dataclass(frozen=True)
class InstructionBodies:
    """Where the instructions of a machine get their C bodies: the mnemonic names by number, the body of each operation, the support text the bodies
    use (`helper`: sizes and masks, `timing`: the cycle helpers) and the digest of the semantics they come from (recorded in the generation record)."""
    names: list
    bodies: dict
    helper: str
    timing: str
    semantics_sha256: str


def recompiler_bodies(engine: Path, prefix: str) -> InstructionBodies:
    """The chain of the Sharp X68000: the interpreter semantics of the Mega Drive recompiler, the shared state rules, executed by Musashi."""
    names = mnemonic_names(engine)
    semantics = adapt_state_rules(adapt_semantics((engine / 'runner/m68k_interp.c').read_text(encoding='utf-8'), hook_prefix=prefix.rstrip('_')))
    bodies = operation_bodies(semantics)
    bodies['MN_RESET'] = f'''if(!(g_cpu.SR&SR_S))return {prefix}instruction_exception(next_pc,8,ins->addr,34);
        {prefix}reset_instruction();return M68KI_OK;'''
    helper = semantics[semantics.index('static uint32_t szmask('):semantics.index('static uint8_t *s_exec_cov')]
    helper = helper[:helper.rfind('/* =====')]
    timing = semantics[semantics.index('static int interp_popcount16('):semantics.index('static void interp_account_cycles(')]
    timing = timing[:timing.rfind('/* The emit_cycle_accounting')]
    return InstructionBodies(names, bodies, helper, timing, hashlib.sha256(semantics.encode()).hexdigest())


def build_decoder(project: Path, engine: Path, *, source: Path, root: Path, target: str, name: str) -> Path:
    """The qualified decoder of the recompiler as a tool: `source` is the machine's driver (its snapshot format), `target` the name of the executable."""
    decoder_tool(engine)  # Qualified decoder, exception normalizer and cycle helpers.
    directory = project / 'decoder'
    directory.mkdir(exist_ok=True)
    write_changed(directory / 'CMakeLists.txt', f'''cmake_minimum_required(VERSION 3.20)
project({name} LANGUAGES C)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
add_executable({target} "{source.as_posix()}"
 "{engine.as_posix()}/recompiler/src/m68k_decoder.c"
 "{engine.as_posix()}/recompiler/src/m68k_validator.c"
 "{engine.as_posix()}/recompiler/src/rom_parser.c")
target_include_directories({target} PRIVATE "{(root / '.build/megadrive-step-decoder').as_posix()}"
 "{engine.as_posix()}/recompiler/src")
if(MSVC)
 target_compile_options({target} PRIVATE "$<$<C_COMPILER_ID:MSVC>:/utf-8;/wd4996>")
endif()
''')
    cmake, generator = toolchain()
    run([cmake, '-S', directory, '-B', directory / 'build', '-G', generator, *cmake_target_args()], log=project / 'build.log')
    run([cmake, '--build', directory / 'build', '--config', 'Release', '--parallel', '4'], log=project / 'build.log')
    return build_executable(directory / 'build', target)


def write_word_counts(project: Path, decode_tool: Path, prefix: str) -> None:
    """`opcode_lengths.h`: the number of words of an instruction from its first word, the table the decoder writes."""
    lengths = project / 'opcode-lengths.bin'
    run([decode_tool, '--lengths', lengths], log=project / 'decode.log')
    sizes = lengths.read_bytes()
    if len(sizes) != 65536 or any(not 1 <= n <= 8 for n in sizes):
        raise ValueError('Invalid MC68000 opcode length table.')
    write_changed(project / 'opcode_lengths.h', f'static const unsigned char {prefix}word_counts[65536]={{\n' +
                  '\n'.join(','.join(map(str, sizes[n:n + 128])) + ',' for n in range(0, 65536, 128)) + '\n};\n')


def write_step_semantics(project: Path, bodies: InstructionBodies, prefix: str, alias: Callable[[str], str]) -> None:
    write_changed(project / 'step_semantics.h', '#pragma once\n#include "m68kcpu.h"\n'
                  '#include "cpu.h"\n#include <stddef.h>\n'
                  f'#define s_illegal_ea {prefix}illegal_ea\nstatic int interp_ea_read_cost(int,M68KSize);\n'
                  'static int game_instruction_hook_site(uint32_t pc){(void)pc;return 0;}\n'
                  'static int genesis_game_instruction_hook(uint32_t pc){(void)pc;return 0;}\n'
                  'static void discover(uint32_t pc){(void)pc;}\n' + alias(bodies.helper + '\n' + bodies.timing))


# The page table walk and the live-word guard of every address group: the same for every machine of a 24-bit bus. __P__ is the machine's prefix, __STEP__ its
# step type; the bytes of an aperture (`code_view`) and, on a big-endian build, `__P__code_word` are the machine's own.
GUARDED = '''/* The live-word guard of one address group: the first variant whose words
 * all match the current code bytes. */
static const __STEP__ *guarded(unsigned group,uint32_t pc) {
#ifndef MSB_FIRST
    /* Little-endian hosts keep each 68000 word as a host 16-bit value. */
    uint32_t available;
    const uint8_t *code=code_view(pc,&available);
    if(!code)return NULL;
    for(unsigned k=0;k<groups[group].count;++k) {
        const __STEP__ *s=&entries[groups[group].start+k];
        unsigned count=(unsigned)s->instruction.word_count,n=0;
        if(count*2u>available)continue;
        for(;n<count;++n) {uint16_t word;memcpy(&word,code+n*2u,2);if(word!=s->instruction.words[n])break;}
        if(n==count)return s;
    }
#else
    for(unsigned k=0;k<groups[group].count;++k) {
        const __STEP__ *s=&entries[groups[group].start+k];int same=1;
        for(unsigned n=0;n<(unsigned)s->instruction.word_count;++n) {
            uint16_t word;
            if(!__P__code_word(pc+n*2,&word) || word!=s->instruction.words[n]){same=0;break;}
        }
        if(same)return s;
    }
#endif
    return NULL;
}
const __STEP__ *__P__lookup(uint32_t pc) {
    pc&=0xffffffu;
    if(pc&1u)return NULL;
    const uint16_t *slots=pages[pc>>12].slots;
    if(!slots)return NULL;
    unsigned slot=slots[(pc&0xfffu)>>1];
    if(!slot)return NULL;
    return guarded(pages[pc>>12].base+slot-1u,pc);
}
'''


@dataclass
class Steps:
    instructions: list
    forms: dict
    groups: list
    links: list


def write_steps(project: Path, samples: list, *, observed: ObservedCode, bodies: InstructionBodies, decode_tool: Path, diagnostic: list,
                alias: Callable[[str], str], form_body: Callable[[str], str], descriptor: Callable[[dict, str], dict],
                index_head: str, code_view: str, index_tail: Callable[[list], str]) -> Steps:
    """Decode the observed instructions, write one guarded native step per distinct form (`steps/partNN.c`) and the index that finds a step from a pc
    (`steps/index.c`). `diagnostic` instructions are added to the samples (authored guard fixtures); `form_body` and `descriptor` are the machine's
    hooks on a step's text and on the literal that describes it, `index_head` its includes, `code_view` its reading of an aperture and `index_tail`
    what it appends after the lookup (given the successor links)."""
    prefix = observed.prefix
    names, operations = bodies.names, bodies.bodies
    decoded = []
    if samples:
        decode_samples = sorted(set(samples + diagnostic))
        listing = project / 'snapshots.txt'
        listing.write_text(''.join(f'{pc:06x} {words}\n' for pc, words in decode_samples), encoding='ascii')
        run([decode_tool, listing, project / 'decoded.json'], log=project / 'decode.log')
        decoded = json.loads((project / 'decoded.json').read_text(encoding='utf-8'))
    unique = {}
    for ins in decoded:
        name = names[ins['mnemonic']]
        if name not in operations:
            continue
        unique[(ins['addr'], tuple(ins['words'][:ins['word_count']]))] = ins
    instructions = sorted(unique.values(), key=lambda s: (s['addr'], tuple(s['words'])))
    # Reuse existing structural specialization; source/extension descriptors and full live words remain guarded, including multiple versions per PC.
    forms = {}
    entries = []
    chunks = [[] for _ in range(16)]
    declarations = []
    for ins in instructions:
        name = names[ins['mnemonic']]
        key = structural_key(ins)
        if key not in forms:
            symbol = f'{prefix}form_{len(forms)}'
            forms[key] = symbol
            body = form_body(structural_body(ins, name, operations[name]).replace('rr_ng_', prefix))
            chunks[(ins['words'][0] >> 1) % 16].append(f'M68kiStatus {symbol}(const M68KInstr *compiled,uint32_t *next_pc) {{\n{body}}}\n')
            declarations.append(f'extern M68kiStatus {symbol}(const M68KInstr*,uint32_t*);\n')
        entries.append('{' + instruction_literal(descriptor(ins, name), name) + f',{forms[key]}' + '}')
    steps = project / 'steps'
    steps.mkdir(exist_ok=True)
    for n, chunk in enumerate(chunks):
        write_changed(steps / f'part{n:02}{observed.source_extension}', observed.steps_head + alias(''.join(chunk)))
    groups = []
    last = None
    for index, ins in enumerate(instructions):
        if ins['addr'] != last:
            groups.append([ins['addr'], index, 1])
            last = ins['addr']
        else:
            groups[-1][2] += 1
    # Direct page table: 4 KiB pages of the 24-bit space, one 16-bit slot per even address giving the group within the page. One lookup per fetch
    # instead of a binary search; the live-word guard is a single compare.
    # Successor links: the group at each entry's fallthrough and static target address (0: no compiled variant there). The live-word guard of
    # the successor is still compared; only the page-table walk is skipped.
    group_of = {pc: index for index, (pc, start, count) in enumerate(groups)}
    links = []
    for ins in instructions:
        fall = (ins['addr'] + ins['byte_length']) & 0xffffff
        taken = ins['target_addr'] & 0xffffff if ins['has_target'] else None
        links.append((group_of.get(fall, -1) + 1, group_of.get(taken, -1) + 1 if taken is not None else 0))
    pages = {}
    for index, (pc, start, count) in enumerate(groups):
        page = pages.setdefault(pc >> 12, {'base': index, 'slots': {}})
        page['slots'][(pc & 0xfff) >> 1] = index - page['base'] + 1
    source = index_head
    source += ''.join(declarations)
    source += f'static const {observed.step_type} entries[]={{' + (',\n'.join(entries) if entries else '{0}') + '};\n'
    source += 'static const struct {uint32_t pc,start,count;} groups[]={' + (','.join('{%d,%d,%d}' % tuple(g) for g in groups) if groups else '{0}') + '};\n'
    for number, page in sorted(pages.items()):
        source += f'static const uint16_t page_{number:x}[2048]={{' + ','.join(f'[{slot}]={value}' for slot, value in sorted(page['slots'].items())) + '};\n'
    source += 'static const struct {uint32_t base;const uint16_t *slots;} pages[4096]={' + ','.join(
        f'[{number}]={{{page["base"]},page_{number:x}}}' for number, page in sorted(pages.items())) + '};\n'
    source += code_view
    source += GUARDED.replace('__P__', prefix).replace('__STEP__', observed.step_type)
    source += index_tail(links)
    write_changed(steps / f'index{observed.source_extension}', source)
    return Steps(instructions, forms, groups, links)
