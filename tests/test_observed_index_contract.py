"""Contract of the shared observed-code generator (retrorecomp/m68k_observed.py): for every machine that declares an `ObservedCode`, the index of
native steps it writes compiles, warnings as errors, in the language its extension names (`index_extension`, else `source_extension`).

The index is C: its page tables use array designators, which C++ refuses or warns about. A machine whose steps are C++ (the Amiga's Moira templates)
keeps its index in C with `index_extension = '.c'`. No ROM: the decoder tool is replaced by a canned answer on authored instructions. The index head
is the machine's own when it is self-contained (the Amiga's); the X68000's needs its machine runtime, so a neutral C head with the same step type
stands for it here, and its real index is compiled by its own build.
"""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from retrorecomp import amiga_codegen, m68k_observed
from retrorecomp.systems import ALL_PROFILES

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / '.deps' / 'segagenesisrecomp'
DECODER = ENGINE / 'external' / 'm68k-recomp-core' / 'common' / 'm68k_decoder.h'
PARSER = ENGINE / 'recompiler' / 'src'          # rom_parser.h, which the decoder's header includes
NAMES = ['MN_OTHER', 'MN_NOP']


def instruction(addr, first_word):
    return {'mnemonic': 1, 'size': 1, 'addr': addr, 'words': [first_word], 'word_count': 1, 'byte_length': 2, 'src_ea': 0, 'dst_ea': 0, 'reg': 0,
            'imm32': 0, 'target_addr': 0, 'has_target': 0, 'dst_is_ea': 0, 'predec_mem_form': 0, 'mem_shift': 0}


def neutral_hooks(observed):
    """A C head with the machine's step type for the Musashi-shaped steps (the X68000's signature)."""
    head = ('#include <stddef.h>\n#include <stdint.h>\n#include <string.h>\n#include "m68k_decoder.h"\ntypedef int M68kiStatus;\n'
            f'typedef struct {observed.step_type} {{ M68KInstr instruction; M68kiStatus (*run)(const M68KInstr *, uint32_t *); }} {observed.step_type};\n')
    view = 'static const uint8_t *code_view(uint32_t pc, uint32_t *available) { (void)pc; *available = 0; return NULL; }\n'
    bodies = m68k_observed.InstructionBodies(NAMES, {'MN_NOP': 'return 0;'}, '', '', 'f' * 64)
    return head, view, lambda links: '', bodies


def amiga_table(folder):
    table = folder / 'moira-map.txt'
    table.write_text(''.join(f'{op:04x} {"Nop" if op == 0x4e71 else "Illegal"} 1 0 0 1\n' for op in range(65536)), encoding='ascii')
    amiga_codegen.load_opcode_map(table)


def declarations():
    return [(profile.id, profile.observed_code) for profile in ALL_PROFILES if profile.observed_code is not None]


def cmake_tool():
    """(cmake, generator, configure arguments): the converter's toolchain when it is installed, else the CMake of the PATH and its default compiler."""
    try:
        from retrorecomp.core import toolchain
        from retrorecomp.platforms import cmake_target_args
        cmake, generator = toolchain()
        return cmake, generator, [a for a in cmake_target_args() if not a.startswith('-DCMAKE_EXE_LINKER_FLAGS')]
    except Exception:
        found = shutil.which('cmake')
        return (Path(found), None, []) if found else (None, None, [])


class ObservedIndexContract(unittest.TestCase):
    def test_every_declaration_names_the_language_of_its_index(self):
        for name, observed in declarations():
            with self.subTest(name):
                self.assertIn(observed.source_extension, ('.c', '.cpp'))
                self.assertIn(observed.index_extension, (None, '.c', '.cpp'))
                # The page tables of the index are C designators: a machine with C++ steps keeps its index in C.
                self.assertEqual(observed.index_extension or observed.source_extension, '.c')

    def write_index(self, folder, name, observed):
        decoded = [instruction(0x6000, 0x4e71), instruction(0x6002, 0x4e71), instruction(0x7000, 0x4e71)]
        project = folder / name
        samples = [(0x6000, '4e71'), (0x6002, '4e71'), (0x7000, '4e71')]

        def fake_run(command, log=None):
            Path(command[2]).write_text(json.dumps(decoded), encoding='utf-8')
        project.mkdir()
        if name == 'amiga':     # Its own writer: Moira's code per opcode, chained; no decoder at all.
            amiga_table(folder)
            amiga_codegen.write_steps(project, samples, observed=observed)
        else:
            head, view, tail, bodies = neutral_hooks(observed)
            with patch.object(m68k_observed, 'run', fake_run):
                m68k_observed.write_steps(project, samples, observed=observed, bodies=bodies, decode_tool=Path('decode'), diagnostic=[],
                                          alias=lambda text: text, form_body=lambda body: body, descriptor=lambda ins, mnemonic: ins,
                                          index_head=head, code_view=view, index_tail=tail)
        index = project / 'steps' / ('index' + (observed.index_extension or observed.source_extension))
        self.assertTrue(index.is_file())
        return index

    def test_the_index_of_every_machine_compiles_in_its_language(self):
        if not DECODER.is_file():
            self.skipTest('the pinned recompiler is not fetched')
        cmake, generator, arguments = cmake_tool()
        if not cmake:
            self.skipTest('CMake unavailable')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            targets = []
            for name, observed in declarations():
                index = self.write_index(root, name, observed)
                targets.append(f'add_library(index_{name} OBJECT "{index.as_posix()}")\n'
                               f'if(CMAKE_C_COMPILER_ID MATCHES "Clang|GNU")\n  target_compile_options(index_{name} PRIVATE -Werror)\nendif()\n')
            (root / 'CMakeLists.txt').write_text(
                'cmake_minimum_required(VERSION 3.20)\nproject(ObservedIndexContract C CXX)\nset(CMAKE_CXX_STANDARD 20)\n'
                f'include_directories("{DECODER.parent.as_posix()}" "{PARSER.as_posix()}")\n' + ''.join(targets), encoding='utf-8')
            configure = [str(cmake), '-S', str(root), '-B', str(root / 'build')] + (['-G', generator] if generator else []) + arguments
            result = subprocess.run(configure, capture_output=True, text=True, timeout=300)
            if result.returncode:
                self.skipTest('no working C and C++ compiler: ' + result.stdout[-300:])
            result = subprocess.run([str(cmake), '--build', str(root / 'build'), '--config', 'Release'], capture_output=True, text=True, timeout=300)
            self.assertEqual(result.returncode, 0, result.stdout[-4000:] + result.stderr[-2000:])


if __name__ == '__main__':
    unittest.main()
