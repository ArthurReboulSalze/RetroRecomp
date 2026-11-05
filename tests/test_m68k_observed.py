"""The generator of guarded native code that every 68000 computer shares (retrorecomp/m68k_observed.py), and what a profile declares to use it.

No ROM, disk or firmware: the decoder tool is replaced by a canned answer, so the text the generator writes for a machine is checked on authored
instructions. The byte-for-byte A/B on real games (the generated project of three X68000 games before and after the move) is in UPGRADES.md.
"""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from retrorecomp import m68k_observed
from retrorecomp.systems import ALL_PROFILES, get_profile
from retrorecomp.systems.specs import ObservedCode

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / '.deps' / 'segagenesisrecomp'


def instruction(addr, first_word, byte_length=2):
    return {'mnemonic': 7, 'size': 1, 'addr': addr, 'words': [first_word, 0, 0, 0, 0, 0, 0, 0][:max(1, byte_length // 2)],
            'word_count': byte_length // 2, 'byte_length': byte_length, 'src_ea': 0, 'dst_ea': 0, 'reg': 0, 'imm32': 0, 'target_addr': 0,
            'has_target': 0, 'dst_is_ea': 0, 'predec_mem_form': 0, 'mem_shift': 0}


class DeclarationTests(unittest.TestCase):
    def test_the_x68000_declares_where_its_instruction_bodies_come_from(self):
        observed = get_profile('x68').observed_code
        self.assertIsInstance(observed, ObservedCode)
        self.assertEqual((observed.bodies, observed.prefix, observed.step_type), ('m68k_observed:recompiler_bodies', 'rr_x68k_', 'RrX68NativeStep'))
        module, _, function = observed.bodies.partition(':')
        self.assertTrue(callable(getattr(__import__('retrorecomp.' + module, fromlist=[function]), function)))

    def test_every_declaration_is_well_formed_and_no_other_machine_is_named_in_the_generator(self):
        for profile in ALL_PROFILES:
            observed = profile.observed_code
            if observed is None:
                continue
            with self.subTest(profile.id):
                self.assertTrue(observed.prefix.startswith('rr_') and observed.prefix.endswith('_'))
                self.assertRegex(observed.step_type, r'^Rr\w+Step$')
                last_end = -1
                for low, last, end in observed.apertures:
                    self.assertTrue(last_end <= low < last <= end)
                    last_end = end
        source = (ROOT / 'retrorecomp' / 'm68k_observed.py').read_text(encoding='utf-8')
        for name in ('x68', 'X68000', 'amiga', 'Amiga'):
            self.assertNotIn("'" + name + "'", source)
            self.assertNotIn('== "' + name + '"', source)

    def test_an_observed_sample_must_fit_an_aperture_of_the_machine(self):
        observed = get_profile('x68').observed_code
        observed.check_sample(0x6000, '4e75')
        observed.check_sample(0xfc0100, '303c1234')
        observed.check_sample(0xe00010, '4e71' * 8)
        for pc, words, message in ((0x6001, '4e75', 'aperture'), (0xd00000, '4e75', 'aperture'), ('x', '4e75', 'aperture'), (0xfffffe, '4e75', 'aperture'),
                                   (0x6000, '4e7', 'words'), (0x6000, '4E75', 'words'), (0x6000, '4e' * 40, 'words'), (0x6000, 7, 'words'),
                                   (0xbffffe, '4e754e75', 'boundary'), (0xe7fffe, '4e754e75', 'boundary'), (0xea1ffe, '4e754e75', 'boundary')):
            with self.subTest((pc, words)):
                with self.assertRaises(ValueError) as caught:
                    observed.check_sample(pc, words)
                self.assertIn(message, str(caught.exception).lower())

    def test_a_declared_entry_point_is_loaded_with_the_engine_and_the_prefix(self):
        calls = []

        def provider(engine, prefix):
            calls.append((engine, prefix))
            return 'bodies'
        declared = ObservedCode('m68k_observed:fake_provider', 'rr_fake_', 'RrFakeStep', ((0, 0x100000, 0x100000),))
        with patch.object(m68k_observed, 'fake_provider', provider, create=True):
            self.assertEqual(declared.load_bodies(Path('engine')), 'bodies')
        self.assertEqual(calls, [(Path('engine'), 'rr_fake_')])


class BodiesTests(unittest.TestCase):
    @unittest.skipUnless((ENGINE / 'runner/m68k_interp.c').is_file(), 'the pinned recompiler is not fetched')
    def test_the_recompiler_chain_answers_bodies_with_the_machines_prefix(self):
        bodies = m68k_observed.recompiler_bodies(ENGINE, 'rr_x68k_')
        self.assertRegex(bodies.semantics_sha256, '^[0-9a-f]{64}$')
        self.assertIn('MN_RESET', bodies.bodies)
        self.assertIn('rr_x68k_reset_instruction', bodies.bodies['MN_RESET'])
        self.assertNotIn('rr_amiga_', bodies.bodies['MN_RESET'])
        self.assertTrue(bodies.helper and bodies.timing and bodies.names[0] == 'MN_OTHER')
        other = m68k_observed.recompiler_bodies(ENGINE, 'rr_amiga_')
        self.assertIn('rr_amiga_reset_instruction', other.bodies['MN_RESET'])
        self.assertNotEqual(other.semantics_sha256, bodies.semantics_sha256, 'the hooks carry the prefix')


class StepsTests(unittest.TestCase):
    def generate(self, prefix='rr_test_', step='RrTestStep', **language):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        project = Path(folder.name)
        observed = ObservedCode('m68k_observed:recompiler_bodies', prefix, step, ((0, 0xc00000, 0xc00000),), **language)
        bodies = m68k_observed.InstructionBodies(['MN_OTHER', 'MN_NOP', 'MN_RTS'] + ['MN_X'] * 8, {'MN_X': 'return M68KI_OK;'}, 'HELPER', 'TIMING', 'f' * 64)
        decoded = [instruction(0x6000, 0x4e71), instruction(0x6002, 0x4e75), instruction(0x6000, 0x4e71), instruction(0x7000, 0x4e71)]
        for item in decoded:
            item['mnemonic'] = 10

        def fake_run(command, log=None):
            Path(command[2]).write_text(json.dumps(decoded), encoding='utf-8')
        calls = []
        with patch.object(m68k_observed, 'run', fake_run):
            steps = m68k_observed.write_steps(
                project, [(0x6000, '4e71'), (0x6002, '4e75'), (0x7000, '4e71')], observed=observed, bodies=bodies, decode_tool=Path('decode'),
                diagnostic=[(0xbffe00, '4e71')], alias=lambda text: text.replace('g_cpu.D[', 'REG_D['),
                form_body=lambda body: calls.append(body) or body, descriptor=lambda ins, name: ins, index_head='#include "cpu.h"\n',
                code_view='static const uint8_t *code_view(uint32_t pc,uint32_t *available){return NULL;}\n',
                index_tail=lambda links: '/* links %d */\n' % len(links))
        return project, steps, calls

    def test_the_steps_the_index_and_the_page_table_are_written_for_the_machine(self):
        project, steps, calls = self.generate()
        self.assertEqual([item['addr'] for item in steps.instructions], [0x6000, 0x6002, 0x7000], 'sorted, one per address and words')
        self.assertEqual([group[0] for group in steps.groups], [0x6000, 0x6002, 0x7000])
        self.assertEqual(len(steps.forms), 2, 'two first words, two forms; the same word at another address shares its form')
        index = (project / 'steps' / 'index.c').read_text(encoding='utf-8')
        self.assertTrue(index.startswith('#include "cpu.h"\n'))
        self.assertIn('extern M68kiStatus rr_test_form_0(const M68KInstr*,uint32_t*);', index)
        self.assertIn('static const RrTestStep entries[]=', index)
        self.assertIn('const RrTestStep *rr_test_lookup(uint32_t pc)', index)
        self.assertIn('rr_test_code_word(pc+n*2,&word)', index)
        self.assertIn('[6]={0,page_6}', index.replace(' ', ''))
        self.assertTrue(index.endswith('/* links 3 */\n'))
        self.assertNotIn('__P__', index)
        self.assertNotIn('__STEP__', index)
        self.assertEqual(len(calls), 2)
        part = ''.join((project / 'steps' / f'part{n:02}.c').read_text(encoding='utf-8') for n in range(16))
        self.assertIn('M68kiStatus rr_test_form_0(', part)
        self.assertEqual((project / 'snapshots.txt').read_text(encoding='ascii').splitlines()[0], '006000 4e71')
        self.assertIn('bffe00 4e71', (project / 'snapshots.txt').read_text(encoding='ascii'), 'the authored guard fixtures join the samples')

    def test_the_language_of_the_steps_is_the_machines(self):
        # C by default (the X68000); a machine whose bodies are C++ templates names its extension and the head of each step file.
        project, _, _ = self.generate()
        self.assertTrue((project / 'steps' / 'index.c').is_file() and (project / 'steps' / 'part00.c').is_file())
        self.assertTrue((project / 'steps' / 'part00.c').read_text(encoding='utf-8').startswith('#include "step_semantics.h"\n'))
        project, _, _ = self.generate('rr_amiga_', 'RrAmigaStep', source_extension='.cpp', steps_head='#include "moira_steps.h"\nextern "C" {\n')
        names = sorted(path.name for path in (project / 'steps').iterdir())
        self.assertEqual(names, ['index.cpp'] + [f'part{n:02}.cpp' for n in range(16)])
        self.assertTrue((project / 'steps' / 'part03.cpp').read_text(encoding='utf-8').startswith('#include "moira_steps.h"\nextern "C" {\n'))

    def test_another_machines_prefix_and_step_type_replace_every_name(self):
        project, _, _ = self.generate('rr_amiga_', 'RrAmigaStep')
        text = (project / 'steps' / 'index.c').read_text(encoding='utf-8')
        self.assertIn('const RrAmigaStep *rr_amiga_lookup(uint32_t pc)', text)
        self.assertNotIn('rr_test_', text)
        self.assertNotIn('RrX68', text)
        self.assertNotIn('rr_x68k_', text)

    def test_the_word_count_table_is_written_with_the_machines_prefix(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        project = Path(folder.name)

        def fake_run(command, log=None):
            Path(command[2]).write_bytes(bytes([1]) * 65536)
        with patch.object(m68k_observed, 'run', fake_run):
            m68k_observed.write_word_counts(project, Path('decode'), 'rr_amiga_')
        header = (project / 'opcode_lengths.h').read_text(encoding='utf-8')
        self.assertTrue(header.startswith('static const unsigned char rr_amiga_word_counts[65536]={\n'))
        with patch.object(m68k_observed, 'run', lambda command, log=None: Path(command[2]).write_bytes(b'\x01' * 10)):
            with self.assertRaises(ValueError):
                m68k_observed.write_word_counts(project, Path('decode'), 'rr_amiga_')


if __name__ == '__main__':
    unittest.main()
