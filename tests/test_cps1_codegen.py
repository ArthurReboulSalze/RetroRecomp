"""CPS-1 native code generation inputs and pinned-source adaptations."""
from pathlib import Path
import unittest

from retrorecomp import cps1_build, cps1_catalogue, cps1_codegen

ROOT = Path(__file__).resolve().parents[1]
GEOLITH = ROOT / '.deps/geolith-libretro'
YMFM = ROOT / '.deps/ymfm'


class ProgramSizeTests(unittest.TestCase):
    def test_interleaved_and_continued_loads(self):
        game = {'regions': [{'tag': 'maincpu', 'loads': [
            {'op': 'load16_byte', 'name': 'a', 'offset': 0, 'bytes': 0x20000},
            {'op': 'load16_byte', 'name': 'b', 'offset': 1, 'bytes': 0x20000},
            {'op': 'load16_word_swap', 'name': 'c', 'offset': 0x80000, 'bytes': 0x40000},
            {'op': 'continue', 'offset': 0x100000, 'bytes': 0x20000}]},
            {'tag': 'gfx', 'loads': [{'op': 'load64_word', 'name': 'g', 'offset': 0, 'bytes': 0x80000}]}]}
        self.assertEqual(cps1_codegen.program_size(game), 0x120000)

    def test_final_fight_program_is_one_megabyte(self):
        self.assertEqual(cps1_codegen.program_size(cps1_catalogue.by_set()['ffight']), 0x100000)


class RamVariantTests(unittest.TestCase):
    def test_bounds_alignment_and_duplicates(self):
        records = [{'offset': 0x10, 'words': '4e75'}, {'offset': 0x10, 'words': '4e75'},
                   {'offset': 0x11, 'words': '4e75'}, {'offset': 0xfffe, 'words': '4e754e75'},
                   {'offset': 0x20, 'words': 'zz'}, {'offset': -2, 'words': '4e75'}]
        self.assertEqual(cps1_codegen.ram_variants(records), [(0x10, bytes.fromhex('4e75'))])


@unittest.skipUnless((GEOLITH / 'src/m68k/m68kcpu.c').is_file(), 'pinned Geolith sources are not cached')
class PinnedAdaptationTests(unittest.TestCase):
    def test_musashi_entry_and_native_dispatch(self):
        reference = cps1_build.musashi_core(GEOLITH, native=False)
        native = cps1_build.musashi_core(GEOLITH, native=True)
        for text in (reference, native):
            self.assertEqual(text.count('cps1_m68k_entry = 1;'), 1)
            self.assertIn('int cps1_m68k_instruction_cycles(void)', text)
        self.assertNotIn('rr_cps1_native_run', reference)
        self.assertEqual(native.count('if(!rr_cps1_native_run())'), 1)

    def test_z80_dispatch_only_in_native_builds(self):
        self.assertNotIn('rr_cps1_z80_try', cps1_build.z80_core(GEOLITH, native=False))
        native = cps1_build.z80_core(GEOLITH, native=True)
        self.assertIn('#include "cps1_z80_steps.inc"', native)
        self.assertEqual(native.count('if(!rr_cps1_z80_try(z,&cyc))'), 1)


RELOCATE_HARNESS = r'''#include "cps1_native.h"
#include <stdio.h>
static int failures;
static void check(M68KMnemonic mnemonic, uint32_t pc, uint32_t target) {
    M68KInstr ins = {0};
    ins.mnemonic = mnemonic; ins.addr = 0x200; ins.target_addr = 0x250;
    rr_cps1_relocate_instruction(&ins, pc);
    if (ins.addr != pc || ins.target_addr != target) {
        printf("mnemonic %d pc %08x: addr %08x target %08x, expected %08x\n",
               (int)mnemonic, pc, ins.addr, ins.target_addr, target);
        ++failures;
    }
}
int main(void) {
    const M68KMnemonic branches[] = {MN_BRA, MN_BSR, MN_Bcc, MN_DBcc};
    for (unsigned n = 0; n < 4; ++n) {
        check(branches[n], 0x0004e7b6u, 0x0004e806u);   /* ordinary 24-bit PC */
        check(branches[n], 0x8004e7b6u, 0x8004e806u);   /* flagged high byte kept */
        check(branches[n], 0x00fffff0u, 0x00000040u);   /* 24-bit wrap as before */
    }
    check(MN_NOP, 0x8004e7b6u, 0x250u);                 /* other targets untouched */
    printf("%d\n", failures);
    return failures != 0;
}
'''


class NativeRelocationTests(unittest.TestCase):
    def test_branch_targets_keep_a_flagged_pc(self):
        """Native branches relocated at a PC whose high byte carries a flag keep
        it, as the reference's 32-bit PC does (Neo Geo rule)."""
        from retrorecomp.core import ConversionError, toolchain
        from retrorecomp.platforms import build_executable, cmake_target_args
        decoder = ROOT / '.deps/segagenesisrecomp/external/m68k-recomp-core/common'
        if not (decoder / 'm68k_decoder.h').is_file():
            self.skipTest('pinned m68k-recomp-core sources are not cached')
        try:
            cmake, generator = toolchain()
        except ConversionError as exc:
            self.skipTest(str(exc))
        import subprocess
        work = ROOT / '.build/cps1-native-relocate'
        work.mkdir(parents=True, exist_ok=True)
        (work / 'relocate.c').write_text(RELOCATE_HARNESS, encoding='utf-8')
        (work / 'CMakeLists.txt').write_text(
            'cmake_minimum_required(VERSION 3.20)\nproject(cps1_relocate C)\nadd_executable(relocate relocate.c)\n'
            f'target_include_directories(relocate PRIVATE "{(ROOT / "native").as_posix()}" "{decoder.as_posix()}"\n'
            f' "{(ROOT / ".deps/segagenesisrecomp/recompiler/src").as_posix()}")\n', encoding='utf-8')
        for command in ([str(cmake), '-S', str(work), '-B', str(work / 'build'), '-G', generator, *cmake_target_args()],
                        [str(cmake), '--build', str(work / 'build'), '--config', 'Release']):
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        result = subprocess.run([str(build_executable(work / 'build', 'relocate'))], capture_output=True, text=True,
                                timeout=60)
        self.assertEqual((result.returncode, result.stdout.strip()), (0, '0'), result.stdout + result.stderr)


@unittest.skipUnless((YMFM / 'src/ymfm_fm.ipp').is_file(), 'pinned ymfm sources are not cached')
class YmfmStateTests(unittest.TestCase):
    def test_restored_states_keep_the_prepare_cadence(self):
        text = cps1_build.ymfm_source('ymfm_fm.ipp', (YMFM / 'src/ymfm_fm.ipp').read_text(encoding='utf-8'))
        engine = text[text.index('fm_engine_base<RegisterType>::save_restore'):]
        engine = engine[:engine.index('\n}\n')]
        self.assertNotIn('invalidate_caches();', engine)
        for name in ('m_active_channels', 'm_modified_channels', 'm_prepare_count'):
            self.assertIn(f'state.save_restore({name});', engine)
        self.assertEqual(text.count('m_regs.cache_operator_data(m_choffs, m_opoffs, m_cache);\n}'), 1)

    def test_the_noise_lfo_waveform_is_saved(self):
        opm = cps1_build.ymfm_source('ymfm_opm.cpp', (YMFM / 'src/ymfm_opm.cpp').read_text(encoding='utf-8'))
        registers = opm[opm.index('void opm_registers::save_restore'):]
        self.assertIn('state.save_restore(m_lfo_waveform[3]);', registers[:registers.index('\n}\n')])
        header = (YMFM / 'src/ymfm_opm.h').read_text(encoding='utf-8')
        self.assertEqual(cps1_build.ymfm_source('ymfm_opm.h', header), header)


if __name__ == '__main__':
    unittest.main()
