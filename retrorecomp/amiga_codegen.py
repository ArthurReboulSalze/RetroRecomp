"""Amiga native code (MIT), one routine per opcode, chained from instruction to instruction.

The Amiga's reference machine is vAmiga, whose CPU is Moira (MIT, pinned with vAmiga). Native code must make the same bus accesses at the same cycles as the
reference (chip-RAM contention). A *form* is the code of one opcode, in one of two kinds, counted apart: translated (`amiga_translate`: the instruction written out as C, calling
the machine's bus functions), or Moira's code specialised (Moira's own handler compiled for that opcode, with the opcode as a literal and its code inlined). Either reads its
extension words on the bus, as the interpreter does.

That is why the guard is one comparison. A form is correct for its opcode at any address and with any extension words, so all that decides whether it
may run is the opcode the CPU has latched: a word rewritten in memory, by anything, needs no tracking. An *instruction* (one per address and opcode
observed, `rr_amiga_at_<pc>_<opcode>`) runs its form, counts, and goes straight on to the instruction it knows comes next when the CPU is there with
that opcode latched and nothing is pending for Moira's or the Amiga's run loop; anything else returns to the run loop, whose checks then see exactly what
they would have seen. `rr_amiga_lookup` is the way in, from the interpreter and after a jump the generator could not know.

Beyond what was observed, `sweep` goes outward from it over images of memory: what a branch not taken on a route leads to, what follows it, and the rest of the pages where
code ran. Those instructions become
native code too, with the same guard, and count apart when they run (`rr_amiga_swept_total`): a sweep guesses, so a report never presents one as proved on a route. A wrong guess
(data read as code, code that a later load replaces) can only be a compiled routine that never runs, or an opcode that does not match and goes to the interpreter.

A player's own record (`walk_records`) adds windows of bytes at instructions that ran on the interpreter in a real session. The first instruction of a window ran there; those a walk finds after it may not have, since
walking can reach bytes the game never executed. Both become native code with the same guard and count apart when they run (`rr_amiga_learned_total`, `rr_amiga_walked_total`): no route proves them.

The Blitter's copy blits get a specialised routine per shape (`blit_shapes`, `_blitter_source`): vAmiga's own microprogram compiled for BLTCON0 and BLTCON1 without their shift fields
(`amiga_vamiga.blitter_shape_header`), one step per bus slot, reading everything else live. A specialised routine, not a translated program. It checks its shape at every slot, since a
game may change BLTCON during a blit. Line blits and rare shapes stay in vAmiga's microprogram; both are counted by shape.

`opcode_map` is read from the table a small tool linked with the adapted Moira writes at conversion time (`<opcode hex> <handler> <Instr> <Mode> <Size> <words>`,
the words being what Moira's disassembler consumes); nothing of Moira is copied here.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from . import amiga_translate, amiga_vamiga, m68k_observed
from .megadrive_codegen import write_changed

FORMAT = 7
# Moira's template parameter for the CPU of the machine.
CORE = 'C68000'
PARTS = 16
# How far a sweep goes, instructions per conversion: a bound on the build, not on what is right.
SWEEP_LIMIT = 150000
SWEEP_PAGE_BITS = 12
# Blitter shapes compiled per conversion, the most words first; the others stay in vAmiga's microprogram, counted.
BLIT_SHAPE_LIMIT = 64
# Handlers after which the next word is not the next instruction.
_NO_FALL_THROUGH = frozenset(('Bra', 'Jmp', 'Rts', 'Rte', 'Rtr', 'Stop', 'Illegal', 'LineA', 'LineF'))
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
            'extern "C" {\nextern uint64_t rr_amiga_native_total, rr_amiga_translated_total, rr_amiga_swept_total, rr_amiga_learned_total, rr_amiga_walked_total, rr_amiga_kick_total;\nextern const uint32_t *rr_amiga_run_flags;\n'
            'extern uint32_t rr_amiga_kick_base, rr_amiga_kick_size;\n}\n'
            'namespace vamiga::moira {\nusing namespace Flag;\n'
            '#ifdef RR_AMIGA_FORMS\n'
            '#include "MoiraInit_cpp.h"\n#include "MoiraALU_cpp.h"\n#include "MoiraDataflow_cpp.h"\n#include "MoiraExceptions_cpp.h"\n#include "MoiraExec_cpp.h"\n'
            '#endif\n'
            'struct RrAmigaSteps {\n' + forwarders +
            '    // A translated form (retrorecomp/amiga_translate.py), a member of the struct Moira declares its friend.\n'
            '    template <int OPCODE> static void translated(Moira &m);\n'
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


def _translated(opcode: int) -> str | None:
    handler, _, mode, size = _MAP[opcode]
    return amiga_translate.translate(opcode, handler, mode, size, core=CORE)


def _form(symbol: str, opcode: int) -> str:
    handler, instr, mode, size = _MAP[opcode]
    body = _translated(opcode)
    if body is not None:
        return (f'namespace vamiga::moira {{\ntemplate <> inline void RrAmigaSteps::translated<0x{opcode:04x}>(Moira &m) {{\n    [[maybe_unused]] auto &r = m.reg;\n'
                f'    [[maybe_unused]] auto &q = m.queue;\n{body}}}\n}}\n'
                f'extern "C" RR_AMIGA_FORM void {symbol}(void *m) {{ vamiga::moira::RrAmigaSteps::translated<0x{opcode:04x}>(*static_cast<vamiga::moira::Moira *>(m)); }}\n')
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


def _instruction(prefix: str, pc: int, form: tuple, following: list, origin: str = '') -> str:
    """`origin` is 'swept', 'learned' or 'walked' for an instruction no route ran: it counts apart when it runs."""
    chain = ''.join(f'    if (S::at(m, 0x{next_pc:x}, 0x{opcode:04x})) RR_AMIGA_NEXT {_symbol(prefix, next_pc, opcode)}(p);\n' for next_pc, opcode in following)
    translated = (' rr_amiga_translated_total++;' if _translated(form[1]) is not None else '') + (f' rr_amiga_{origin}_total++;' if origin else '')
    return (f'extern "C" void {_symbol(prefix, pc, form[1])}(void *p) {{\n    auto &m = *static_cast<vamiga::moira::Moira *>(p);\n    {form[0]}(p);\n'
            f'    rr_amiga_native_total++;{translated}{_count(pc)}\n    if (S::pending(m)) return;\n{chain}}}\n')


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


def _word(image: tuple, address: int) -> int | None:
    start, data = image
    at = address - start
    return data[at] << 8 | data[at + 1] if 0 <= at and at + 1 < len(data) else None


def sweep(samples: list, images: list, *, observed, rom_images: list = (), limit: int = SWEEP_LIMIT, cut: dict | None = None) -> list:
    """(pc, words in hex) of the instructions reached from the observed ones over images of memory, each a list of (start address, bytes) regions, and not observed themselves.
    Only where an image still holds the observed opcode does the walk start from it, following branches and what falls through them. Then, in RAM images, every even address of a
    4 KiB page where code was observed that holds a legal opcode: a subroutine called through a pointer is reached by nothing else, and a guess that is not code never runs. Bounded:
    `cut`, when given, receives what the bound left out (sweep_cut), never silently."""
    seen = {(pc, int(text[:4], 16)) for pc, text in samples}
    found: dict[tuple[int, int], str] = {}
    left_walk = left_fill = 0
    by_address = sorted(set(samples))
    pages = sorted({pc >> SWEEP_PAGE_BITS for pc, _ in by_address})
    for regions, fill in [(image, True) for image in images] + [(image, False) for image in rom_images]:
        def read(address):
            return next((value for value in (_word(region, address) for region in regions) if value is not None), None)

        def add(pc):
            """The words of a legal instruction at this address, recorded unless observed."""
            opcode = read(pc)
            if opcode is None or _MAP[opcode][0] in ('Illegal', 'LineA', 'LineF'):
                return None
            words = [read(pc + 2 * n) for n in range(_WORDS[opcode])]
            if None in words:
                return None
            text = ''.join(f'{word:04x}' for word in words)
            try:
                observed.check_sample(pc, text)
            except ValueError:
                return None
            if (pc, opcode) not in seen:
                found.setdefault((pc, opcode), text)
            return words
        visited: set[int] = set()
        queue: list[int] = []

        def follow(pc, words):
            target = _target(pc, words)
            places = [] if target is None else [target & 0xffffff]
            if _MAP[words[0]][0] not in _NO_FALL_THROUGH:
                places.append((pc + 2 * _WORDS[words[0]]) & 0xffffff)
            queue.extend(place for place in places if not place & 1)
        for pc, text in by_address:
            if read(pc) == int(text[:4], 16):
                follow(pc, [int(text[n:n + 4], 16) for n in range(0, len(text) - 3, 4)])
        position = 0
        while position < len(queue) and len(found) < limit:
            pc = queue[position]
            position += 1
            if pc in visited:
                continue
            visited.add(pc)
            words = add(pc)
            if words is not None:
                follow(pc, words)
        if len(found) >= limit:
            left_walk += len({pc for pc in queue[position:] if pc not in visited})
        if fill:
            for number, page in enumerate(pages):
                end = (page + 1) << SWEEP_PAGE_BITS
                for pc in range(page << SWEEP_PAGE_BITS, end, 2):
                    if len(found) >= limit:
                        left_fill += (end - pc) // 2 + sum(1 << (SWEEP_PAGE_BITS - 1) for _ in pages[number + 1:])
                        break
                    add(pc)
                else:
                    continue
                break
    if cut is not None:
        # What the bound left out, per image: the places a branch walk had queued and not reached (each could lead further), and the
        # even addresses of observed pages not tried. Candidates, not instructions: most addresses hold no code.
        cut.update(limit=limit, instructions=len(found), reached=len(found) >= limit, walk_places_left=left_walk, page_addresses_left=left_fill)
    return sorted((pc, text) for (pc, _), text in found.items())


def walk_records(records: list, *, observed) -> tuple[list, list]:
    """From a player's record, windows of (pc, bytes), the (pc, words in hex) of the instructions each first ran there and of those a walk through the rest of the window finds. A walk goes on past a jump, because
    the recorder relies on it for what follows in the window; it stops at what cannot be an instruction. A guess that is not code is only a routine that never runs. Nothing here says the walked ones ran."""
    started: dict[tuple[int, int], str] = {}
    walked: dict[tuple[int, int], str] = {}
    for pc, data in records:
        at = 0
        while at + 2 <= len(data):
            opcode = data[at] << 8 | data[at + 1]
            if _MAP[opcode][0] in ('Illegal', 'LineA', 'LineF'):
                break
            text = data[at:at + 2 * _WORDS[opcode]].hex()
            text = text[:len(text) // 4 * 4]
            try:
                observed.check_sample(pc + at, text)
            except ValueError:
                break
            (started if at == 0 else walked).setdefault((pc + at, opcode), text)
            at += 2 * _WORDS[opcode]
    return (sorted((pc, text) for (pc, _), text in started.items()),
            sorted((key[0], text) for key, text in walked.items() if key not in started))


def blit_shapes(reports, limit: int = BLIT_SHAPE_LIMIT) -> list:
    """The copy shapes the runs of these reports saw (their `blitter`), as (BLTCON0, BLTCON1) without the shift fields: the most words first, up to the limit, in a stable order. Line blits have no routine."""
    words: dict[tuple[int, int], int] = {}
    for report in reports:
        for con0, con1, _, _, native_words, _, interpreted_words in (report.get('blitter') or {}).get('shapes', ()):
            if not con1 & 1:
                words[(con0, con1)] = words.get((con0, con1), 0) + native_words + interpreted_words
    return sorted(sorted(words, key=lambda shape: (-words[shape], shape))[:limit])


def _blit_symbol(prefix: str, con0: int, con1: int) -> str:
    return f'{prefix}blit_{con0:03x}_{con1:02x}'


def _blitter_source(prefix: str, shapes: list) -> str:
    """steps/blitter.cpp: the routines of these shapes. Nothing to compile for a game without a blit."""
    if not shapes:
        return '// This game has no Blitter shape of its own.\n'
    for con0, con1 in shapes:
        if con0 & ~amiga_vamiga.SHAPE_CON0_MASK or con1 & ~amiga_vamiga.SHAPE_CON1_MASK or con1 & 1:
            raise ValueError('Not a copy-blit shape.')
    return ('#include "RrBlitterShape.h"\n#if defined(__GNUC__) || defined(__clang__)\n#define RR_AMIGA_BLIT __attribute__((flatten))\n#else\n#define RR_AMIGA_BLIT\n#endif\n'
            + ''.join(f'extern "C" RR_AMIGA_BLIT void {_blit_symbol(prefix, con0, con1)}(void *blitter) {{ static_cast<vamiga::Blitter *>(blitter)->rrRun<0x{con0:03x}, 0x{con1:02x}>(); }}\n'
                      for con0, con1 in shapes))


def _blit_table(prefix: str, shapes: list) -> str:
    """The table the session reads, in C (`RrAmigaCode` is declared before it)."""
    return ('typedef struct {uint16_t con0,con1;RrAmigaCode run;} RrAmigaBlitShape;\n'
            + ''.join(f'void {_blit_symbol(prefix, con0, con1)}(void *);\n' for con0, con1 in shapes)
            + 'const RrAmigaBlitShape rr_amiga_blit_shapes[]={'
            + (','.join(f'{{0x{con0:03x},0x{con1:02x},{_blit_symbol(prefix, con0, con1)}}}' for con0, con1 in shapes) or '{0,0,NULL}') + '};\n'
            + f'const unsigned rr_amiga_blit_shape_count={len(shapes)};\n')


def write_steps(project: Path, samples: list, *, observed, swept: list = (), shapes: list = (), learned: list = (), walked: list = ()) -> dict:
    """From the observed instructions (pc, their words in hex) and the swept ones, write the forms (`steps/partNN.cpp`), the instructions in address order (`steps/chainNN.cpp`)
    and the index that finds an instruction from a pc and an opcode (`steps/index.c`); from the Blitter's shapes, their routines (`steps/blitter.cpp`) and their table in the index."""
    prefix = observed.prefix
    words = set()
    observed_samples = set(samples)
    # What may follow each (pc, opcode): the targets its variants name first (a loop's branch), then where they fall through.
    following: dict[tuple[int, int], list] = {}
    for pc, text in sorted(set(samples) | set(swept) | set(learned) | set(walked)):
        seen = [int(text[n:n + 4], 16) for n in range(0, len(text) - 3, 4)]
        count = _WORDS[seen[0]]
        seen = seen[:count]
        if (pc, text) in observed_samples:
            words.add((pc, tuple(seen)))
        places = following.setdefault((pc, seen[0]), [[], []])
        target = _target(pc, seen)
        if target is not None and not target & 1 and target & 0xffffff not in places[0]:
            places[0].append(target & 0xffffff)
        fall = (pc + 2 * count) & 0xffffff
        if fall not in places[1]:
            places[1].append(fall)
    instructions = sorted(following)
    was_seen = {(pc, int(text[:4], 16)) for pc, text in samples}
    was_learned = {(pc, int(text[:4], 16)) for pc, text in learned} - was_seen
    was_walked = {(pc, int(text[:4], 16)) for pc, text in walked} - was_seen - was_learned

    def origin(key):
        return '' if key in was_seen else 'learned' if key in was_learned else 'walked' if key in was_walked else 'swept'

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
            text.append(_instruction(prefix, pc, (forms[opcode], opcode), chain, origin((pc, opcode))))
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
              'uint64_t rr_amiga_native_total,rr_amiga_translated_total,rr_amiga_swept_total,rr_amiga_learned_total,rr_amiga_walked_total,rr_amiga_kick_total;\nconst uint32_t *rr_amiga_run_flags;\nuint32_t rr_amiga_kick_base,rr_amiga_kick_size;\n',
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
    source.append(_blit_table(prefix, list(shapes)))
    write_changed(steps / f'index{INDEX_EXTENSION}', ''.join(source))
    write_changed(steps / f'blitter{observed.source_extension}', _blitter_source(prefix, list(shapes)))
    return {'samples': len(samples), 'blitter_shapes': len(shapes), 'instructions': len(words), 'native_instructions': len(instructions), 'forms': len(forms), 'pcs': len(groups),
            'swept_instructions': sum(origin(key) == 'swept' for key in instructions),
            'learned_instructions': sum(origin(key) == 'learned' for key in instructions), 'walked_instructions': sum(origin(key) == 'walked' for key in instructions),
            'translated_forms': sum(_translated(opcode) is not None for opcode in forms),
            'translated_instructions': sum(_translated(opcode) is not None for _, opcode in instructions)}


def write_all_translated_forms(project: Path, *, observed) -> list:
    """For the self-test: every opcode the translator knows, in the files of the forms, and a table of them by opcode. Returns the opcodes."""
    opcodes = sorted(opcode for opcode in _MAP if _translated(opcode) is not None)
    steps = project / 'steps'
    steps.mkdir(parents=True, exist_ok=True)
    chunks = [[] for _ in range(PARTS)]
    for opcode in opcodes:
        chunks[(opcode >> 1) % PARTS].append(_form(f'{observed.prefix}form_{opcode:04x}', opcode))
    for n, chunk in enumerate(chunks):
        write_changed(steps / f'part{n:02}{observed.source_extension}', '#define RR_AMIGA_FORMS 1\n' + observed.steps_head + ''.join(chunk))
    declarations = ''.join(f'void {observed.prefix}form_{opcode:04x}(void *);\n' for opcode in opcodes)
    entries = ','.join(f'[0x{opcode:04x}]={observed.prefix}form_{opcode:04x}' for opcode in opcodes)
    write_changed(steps / f'forms_table{INDEX_EXTENSION}', f'{declarations}void (*const rr_amiga_all_forms[65536])(void *)={{{entries}}};\n')
    return opcodes


SOURCE_EXTENSION = '.cpp'
INDEX_EXTENSION = '.c'
