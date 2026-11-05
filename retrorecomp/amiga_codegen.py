"""Amiga native steps on Moira's instruction templates (MIT): the hooks the shared observed-code generator calls.

The Amiga's reference machine is vAmiga, whose CPU is Moira (MIT, pinned with vAmiga). A native step must make the same
bus accesses at the same cycles as the reference (chip-RAM contention), so it calls the very template Moira dispatches
the opcode to, with the opcode as a literal, instead of going through Moira's jump table: no table and no decoding at
run time; the extension words still come through Moira's prefetch, as on the bus. The shared generator
(`m68k_observed.write_steps`) groups the observed instructions into forms by the decoder's structural key, which starts
with the opcode word, so every form has exactly one Moira template. The live-word guard of the shared index keeps a
changed instruction on the counted interpreter.

`opcode_map` is read from the table a small tool linked with the adapted Moira writes at conversion time
(`<opcode hex> <handler> <Instr> <Mode> <Size>`); nothing of Moira is copied here.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from . import m68k_observed
from .m68000 import mnemonic_names

FORMAT = 1
_MAP: dict[int, tuple[str, int, int, int]] = {}
_MAP_SHA256 = ''


def load_opcode_map(path: Path) -> dict[int, tuple[str, int, int, int]]:
    """The opcode -> (handler, Instr, Mode, Size) table of the 68000 core; every one of the 65,536 opcodes must be there."""
    global _MAP, _MAP_SHA256
    table = {}
    text = Path(path).read_text(encoding='ascii')
    for line in text.splitlines():
        code, name, instr, mode, size = line.split()
        if not name.isidentifier():
            raise ValueError('Invalid Moira handler name: ' + name)
        table[int(code, 16)] = (name, int(instr), int(mode), int(size))
    if len(table) != 65536:
        raise ValueError('The Moira opcode table is incomplete.')
    _MAP, _MAP_SHA256 = table, hashlib.sha256(text.encode()).hexdigest()
    return table


def _semantics(prefix: str, alias) -> str:
    """step_semantics.h: the adapted Moira and one forwarder per handler inside the struct Moira declares its friend."""
    handlers = sorted({entry[0] for entry in _MAP.values()})
    forwarders = ''.join(
        f'    template <Core C, Instr I, Mode M, Size S> static void run_{name}(Moira &m, u16 op) {{ m.exec{name}<C, I, M, S>(op); }}\n'
        for name in handlers)
    return ('#pragma once\n#include "vaconfig.h"\n#include "Moira.h"\n#include <cstdint>\n'
            'namespace vamiga::moira {\nstruct RrAmigaSteps {\n' + forwarders + '};\n}\n')


def _step(symbol: str, ins: dict, name: str, body: str) -> tuple[str, str]:
    opcode = ins['words'][0]
    handler, instr, mode, size = _MAP[opcode]
    signature = f'void {symbol}(vamiga::moira::Moira &m, uint16_t op)'
    call = (f'vamiga::moira::RrAmigaSteps::run_{handler}<vamiga::moira::Core::C68000, (vamiga::moira::Instr){instr}, '
            f'(vamiga::moira::Mode){mode}, (vamiga::moira::Size){size}>(m, op);')
    return f'{signature} {{ {call} }}\n', f'{signature};\n'


def moira_bodies(engine: Path, prefix: str) -> m68k_observed.InstructionBodies:
    """The `ObservedCode.bodies` entry point of the Amiga: every decoded mnemonic is accepted (Moira handles them all);
    the steps and their header come from the hooks. Call `load_opcode_map` first."""
    if not _MAP:
        raise ValueError('Load the Moira opcode table first.')
    names = mnemonic_names(engine)
    return m68k_observed.InstructionBodies(names, {name: '' for name in names}, '', '', _MAP_SHA256,
                                           step_text=_step, semantics_text=_semantics)


# The index of the Amiga steps (C++): the decoder's instruction type, the step type, and the guard's word reader. vAmiga
# keeps memory big-endian, so the guard reads words through the machine (MSB_FIRST branch of the shared guard).
INDEX_HEAD = '''#include "step_semantics.h"
#include <cstddef>
#include <cstring>
extern "C" {
#include "m68k_decoder.h"
}
#define MSB_FIRST 1
struct RrAmigaStep { M68KInstr instruction; void (*run)(vamiga::moira::Moira &, uint16_t); };
bool rr_amiga_code_word(uint32_t pc, uint16_t *word);
'''
# Unused on the MSB_FIRST branch of the shared guard (the words come from rr_amiga_code_word).
CODE_VIEW = '[[maybe_unused]] static const uint8_t *code_view(uint32_t, uint32_t *) { return nullptr; }\n'


def index_tail(links: list) -> str:
    """After the lookup: the accessor the machine's dispatch uses (the step type stays inside the index)."""
    return ('void (*rr_amiga_step_of(const RrAmigaStep *s))(vamiga::moira::Moira &, uint16_t) { return s->run; }\n')
STEPS_HEAD = '#include "step_semantics.h"\n'
