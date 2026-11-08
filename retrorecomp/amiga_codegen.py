"""Amiga native code on Moira's instruction templates (MIT), one routine per opcode, chained from instruction to instruction.

The Amiga's reference machine is vAmiga, whose CPU is Moira (MIT, pinned with vAmiga). Native code must make the same bus accesses at the same
cycles as the reference (chip-RAM contention), so a *form* is Moira's own handler compiled for one opcode, with the opcode as a literal and Moira's
code inlined: "Moira's code specialised", not a translation. It reads its extension words through Moira's prefetch, on the bus, as the interpreter does.

That is why the guard is one comparison. A form is correct for its opcode at any address and with any extension words, so all that decides whether it
may run is the opcode the CPU has latched: a word rewritten in memory, by anything, needs no tracking. An *instruction* (one per address and opcode
observed, `rr_amiga_at_<pc>_<opcode>`) runs its form, counts, and goes straight on to the instruction it knows comes next when the CPU is there with
that opcode latched and nothing is pending for Moira's or the Amiga's run loop; anything else returns to the run loop, whose checks then see exactly what
they would have seen. `rr_amiga_lookup` is the way in, from the interpreter and after a jump the generator could not know.

`opcode_map` is read from the table a small tool linked with the adapted Moira writes at conversion time (`<opcode hex> <handler> <Instr> <Mode> <Size> <words>`,
the words being what Moira's disassembler consumes); nothing of Moira is copied here.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from . import m68k_observed
from .megadrive_codegen import write_changed

FORMAT = 3
# Moira's template parameter for the CPU of the machine.
CORE = 'C68000'
PARTS = 16
# Moira's Mode values (MoiraTypes.h) of the addressing modes that name a place: (####).w, (####).l, (d,PC).
MODE_AW, MODE_AL, MODE_DIPC = 7, 8, 9
_MAP: dict[int, tuple[str, int, int, int]] = {}
_WORDS: dict[int, int] = {}
_MAP_SHA256 = ''


def load_opcode_map(path: Path) -> dict[int, tuple[str, int, int, int]]:
    """The opcode -> (handler, Instr, Mode, Size) table of the 68000 core, and each opcode's number of words; every one of the 65,536 opcodes must be there."""
    global _MAP, _WORDS, _MAP_SHA256
    table = {}
    words = {}
    text = Path(path).read_text(encoding='ascii')
    for line in text.splitlines():
        code, name, instr, mode, size, count = line.split()
        if not name.isidentifier():
            raise ValueError('Invalid Moira handler name: ' + name)
        table[int(code, 16)] = (name, int(instr), int(mode), int(size))
        words[int(code, 16)] = int(count)
    if len(table) != 65536:
        raise ValueError('The Moira opcode table is incomplete.')
    _MAP, _WORDS, _MAP_SHA256 = table, words, hashlib.sha256(text.encode()).hexdigest()
    return table


def _semantics(prefix: str, alias) -> str:
    """step_semantics.h: inside the struct Moira declares its friend, one forwarder per handler and what an instruction reads of the CPU. The forms define
    RR_AMIGA_FORMS to see Moira's code and inline it, as `MoiraCore_cpp.h` compiles it for the jump table; the instructions only need the declarations."""
    handlers = sorted({entry[0] for entry in _MAP.values()})
    forwarders = ''.join(
        f'    template <Core C, Instr I, Mode M, Size S> static void run_{name}(Moira &m, u16 op) {{ m.exec{name}<C, I, M, S>(op); }}\n'
        for name in handlers)
    return ('#pragma once\n#include "vaconfig.h"\n#include "MoiraConfig.h"\n#include "Moira.h"\n#include "MoiraMacros.h"\n'
            '#include <cassert>\n#include <cstdio>\n#include <algorithm>\n#include <cmath>\n#include <bit>\n#include <vector>\n#include <stdexcept>\n#include <cstdint>\n'
            'extern "C" {\nextern uint64_t rr_amiga_native_total, rr_amiga_kick_total;\nextern const uint32_t *rr_amiga_run_flags;\n'
            'extern uint32_t rr_amiga_kick_base, rr_amiga_kick_size;\n}\n'
            'namespace vamiga::moira {\nusing namespace Flag;\n'
            '#ifdef RR_AMIGA_FORMS\n'
            '#include "MoiraInit_cpp.h"\n#include "MoiraALU_cpp.h"\n#include "MoiraDataflow_cpp.h"\n#include "MoiraExceptions_cpp.h"\n#include "MoiraExec_cpp.h"\n'
            '#endif\n'
            'struct RrAmigaSteps {\n' + forwarders +
            '    // Something is pending for a run loop: back to it. Only the interpreter\'s slow path and the Amiga\'s loop deal with those.\n'
            '    static inline bool pending(const Moira &m) { return m.flags != 0 || *rr_amiga_run_flags != 0; }\n'
            '    // The CPU is at this instruction, with this opcode latched: it starts as Moira::execute() starts it.\n'
            '    static inline bool at(Moira &m, u32 pc, u16 opcode) {\n'
            '        if (m.reg.pc0 != pc || m.queue.ird != opcode) return false;\n'
            '        m.reg.pc += 2;\n'
            '        return true;\n'
            '    }\n'
            '};\n}\n'
            '#if defined(__clang__)\n#define RR_AMIGA_NEXT [[clang::musttail]] return\n#else\n#define RR_AMIGA_NEXT return\n#endif\n'
            '#if defined(__GNUC__) || defined(__clang__)\n#define RR_AMIGA_FORM __attribute__((flatten))\n#else\n#define RR_AMIGA_FORM\n#endif\n')


def moira_bodies(engine: Path, prefix: str) -> m68k_observed.InstructionBodies:
    """The `ObservedCode.bodies` entry point of the Amiga: its code is Moira's, nothing comes from a recompiler. Call `load_opcode_map` first."""
    if not _MAP:
        raise ValueError('Load the Moira opcode table first.')
    return m68k_observed.InstructionBodies([], {}, '', '', _MAP_SHA256, semantics_text=_semantics)


def _form(symbol: str, opcode: int) -> str:
    handler, instr, mode, size = _MAP[opcode]
    return (f'extern "C" RR_AMIGA_FORM void {symbol}(void *m) {{ vamiga::moira::RrAmigaSteps::run_{handler}<vamiga::moira::Core::{CORE}, (vamiga::moira::Instr){instr}, '
            f'(vamiga::moira::Mode){mode}, (vamiga::moira::Size){size}>(*static_cast<vamiga::moira::Moira *>(m), 0x{opcode:04x}); }}\n')


def _symbol(prefix: str, pc: int, opcode: int) -> str:
    return f'{prefix}at_{pc:06x}_{opcode:04x}'


def _count(pc: int) -> str:
    """The Kickstart's instructions are counted apart: its window, or its copy in ExpMem, which is outside chip RAM and known at run time only."""
    if pc >= 0xfc0000:
        return ' rr_amiga_kick_total++;'
    if pc >= 0x200000:
        return f' if (0x{pc:x}u - rr_amiga_kick_base < rr_amiga_kick_size) rr_amiga_kick_total++;'
    return ''


def _instruction(prefix: str, pc: int, form: str, following: list) -> str:
    chain = ''.join(f'    if (S::at(m, 0x{next_pc:x}, 0x{opcode:04x})) RR_AMIGA_NEXT {_symbol(prefix, next_pc, opcode)}(p);\n' for next_pc, opcode in following)
    return (f'extern "C" void {_symbol(prefix, pc, int(form[1]))}(void *p) {{\n    auto &m = *static_cast<vamiga::moira::Moira *>(p);\n    {form[0]}(p);\n'
            f'    rr_amiga_native_total++;{_count(pc)}\n    if (S::pending(m)) return;\n{chain}}}\n')


def _signed(value: int, bits: int) -> int:
    return value - (1 << bits) if value >> (bits - 1) else value


def _target(pc: int, words: list) -> int | None:
    """The address an observed instruction names, when it names one: a guess for the chain only, which still compares the pc at run time."""
    handler, _, mode, _ = _MAP[words[0]]
    if handler in ('Bcc', 'Bra', 'Bsr'):
        displacement = words[0] & 0xff
        if displacement:
            return pc + 2 + _signed(displacement, 8)
        return pc + 2 + _signed(words[1], 16) if len(words) > 1 else None
    if handler == 'Dbcc':
        return pc + 2 + _signed(words[1], 16) if len(words) > 1 else None
    if handler in ('Jmp', 'Jsr'):
        if mode == MODE_AW and len(words) > 1:
            return _signed(words[1], 16)
        if mode == MODE_AL and len(words) > 2:
            return words[1] << 16 | words[2]
        if mode == MODE_DIPC and len(words) > 1:
            return pc + 2 + _signed(words[1], 16)
    return None


def write_steps(project: Path, samples: list, *, observed) -> dict:
    """From the observed instructions (pc, their words in hex), write the forms (`steps/partNN.cpp`), the instructions in address order (`steps/chainNN.cpp`)
    and the index that finds an instruction from a pc and an opcode (`steps/index.c`)."""
    prefix = observed.prefix
    words = set()
    # What may follow each (pc, opcode): the targets its variants name first (a loop's branch), then where they fall through.
    following: dict[tuple[int, int], list] = {}
    for pc, text in sorted(set(samples)):
        seen = [int(text[n:n + 4], 16) for n in range(0, len(text) - 3, 4)]
        count = _WORDS[seen[0]]
        seen = seen[:count]
        words.add((pc, tuple(seen)))
        places = following.setdefault((pc, seen[0]), [[], []])
        target = _target(pc, seen)
        if target is not None and not target & 1 and target & 0xffffff not in places[0]:
            places[0].append(target & 0xffffff)
        fall = (pc + 2 * count) & 0xffffff
        if fall not in places[1]:
            places[1].append(fall)
    instructions = sorted(following)
    opcodes_at: dict[int, list] = {}
    for pc, opcode in instructions:
        opcodes_at.setdefault(pc, []).append(opcode)
    forms = {opcode: f'{prefix}form_{opcode:04x}' for opcode in sorted({opcode for _, opcode in instructions})}
    steps = project / 'steps'
    steps.mkdir(exist_ok=True)
    chunks = [[] for _ in range(PARTS)]
    for opcode, symbol in forms.items():
        chunks[(opcode >> 1) % PARTS].append(_form(symbol, opcode))
    for n, chunk in enumerate(chunks):
        write_changed(steps / f'part{n:02}{observed.source_extension}', '#define RR_AMIGA_FORMS 1\n' + observed.steps_head + ''.join(chunk))
    # Neighbours in memory stay in one file: a chain's jumps stay short.
    size = max(1, (len(instructions) + PARTS - 1) // PARTS)
    for n in range(PARTS):
        text, declared = [], set()
        for pc, opcode in instructions[n * size:(n + 1) * size]:
            places = following[(pc, opcode)]
            ordered = list(dict.fromkeys(places[0] + places[1]))
            chain = [(place, other) for place in ordered for other in opcodes_at.get(place, [])]
            needed = {(pc, opcode)} | set(chain)
            text.extend(f'extern "C" void {_symbol(prefix, *item)}(void *);\n' for item in sorted(needed - declared))
            declared |= needed
            if forms[opcode] not in declared:
                text.append(f'extern "C" void {forms[opcode]}(void *);\n')
                declared.add(forms[opcode])
            text.append(_instruction(prefix, pc, (forms[opcode], opcode), chain))
        write_changed(steps / f'chain{n:02}{observed.source_extension}',
                      observed.steps_head + 'using S = vamiga::moira::RrAmigaSteps;\n' + ''.join(text))
    groups = []
    for index, (pc, _) in enumerate(instructions):
        if groups and groups[-1][0] == pc:
            groups[-1][2] += 1
        else:
            groups.append([pc, index, 1])
    pages: dict[int, dict] = {}
    for index, (pc, _, _) in enumerate(groups):
        page = pages.setdefault(pc >> 12, {'base': index, 'slots': {}})
        page['slots'][(pc & 0xfff) >> 1] = index - page['base'] + 1
    source = ['#include <stddef.h>\n#include <stdint.h>\n',
              'uint64_t rr_amiga_native_total,rr_amiga_kick_total;\nconst uint32_t *rr_amiga_run_flags;\nuint32_t rr_amiga_kick_base,rr_amiga_kick_size;\n',
              'typedef void (*RrAmigaCode)(void *);\n']
    source.extend(f'void {_symbol(prefix, pc, opcode)}(void *);\n' for pc, opcode in instructions)
    source.append('static const struct {uint16_t opcode;RrAmigaCode run;} entries[]={'
                  + (',\n'.join(f'{{0x{opcode:04x},{_symbol(prefix, pc, opcode)}}}' for pc, opcode in instructions) or '{0,NULL}') + '};\n')
    source.append('static const struct {uint32_t start,count;} groups[]={' + (','.join(f'{{{start},{count}}}' for _, start, count in groups) or '{0,0}') + '};\n')
    for number, page in sorted(pages.items()):
        source.append(f'static const uint16_t page_{number:x}[2048]={{' + ','.join(f'[{slot}]={value}' for slot, value in sorted(page['slots'].items())) + '};\n')
    source.append('static const struct {uint32_t base;const uint16_t *slots;} pages[4096]={'
                  + ','.join(f'[{number}]={{{page["base"]},page_{number:x}}}' for number, page in sorted(pages.items())) + '};\n')
    source.append("""RrAmigaCode rr_amiga_lookup(uint32_t pc,uint16_t opcode) {
    pc&=0xffffffu;
    if(pc&1u)return NULL;
    const uint16_t *slots=pages[pc>>12].slots;
    if(!slots)return NULL;
    unsigned slot=slots[(pc&0xfffu)>>1];
    if(!slot)return NULL;
    unsigned group=pages[pc>>12].base+slot-1u;
    for(unsigned k=0;k<groups[group].count;++k)
        if(entries[groups[group].start+k].opcode==opcode)return entries[groups[group].start+k].run;
    return NULL;
}
""")
    write_changed(steps / f'index{INDEX_EXTENSION}', ''.join(source))
    return {'samples': len(samples), 'instructions': len(words), 'native_instructions': len(instructions), 'forms': len(forms), 'pcs': len(groups)}


SOURCE_EXTENSION = '.cpp'
INDEX_EXTENSION = '.c'
