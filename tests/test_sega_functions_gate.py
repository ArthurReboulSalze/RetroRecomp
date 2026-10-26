"""The functions backend meets the reference gate of the banked backend and
converts without other players' hints."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from retrorecomp import knowledge
from retrorecomp.core import ConversionError
from retrorecomp.systems.game_gear import GAME_GEAR
from retrorecomp.systems.master_system import MASTER_SYSTEM, REFERENCE_CHECKS

MATCHING = {name: True for name in REFERENCE_CHECKS}


class FunctionsGateTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.output = Path(folder.name)
        self.seen = []

    def converter(self, report):
        def convert(path, **options):
            self.seen.append((options, (MASTER_SYSTEM.id, 'a' * 64) in knowledge._SET_ASIDE))
            (self.output / 'conversion-report.json').write_text(json.dumps(report), encoding='utf-8')
            return self.output / 'build.exe'
        return convert

    def run_with(self, report, **options):
        rom = SimpleNamespace(sha256='a' * 64)
        with patch('retrorecomp.core.convert', side_effect=self.converter(report)), \
             patch.object(type(MASTER_SYSTEM), 'read_rom', return_value=rom):
            return MASTER_SYSTEM.convert(Path('game.sms'), output=self.output, **options)

    def test_a_divergence_fails_like_banked(self):
        report = {**MATCHING, 'reference_vdp_trace_match': False, 'reference_final_ram_match': False}
        with self.assertRaisesRegex(ConversionError, 'vdp_trace_match, final_ram_match'):
            self.run_with(report, backend='functions', publish_result=False)

    def test_imported_hints_are_set_aside_only_for_functions(self):
        self.assertEqual(self.run_with(MATCHING, backend='functions', publish_result=False),
                         self.output / 'build.exe')
        self.assertTrue(self.seen[-1][1])
        self.assertEqual(self.seen[-1][0]['publish_result'], False)
        self.assertNotIn((MASTER_SYSTEM.id, 'a' * 64), knowledge._SET_ASIDE)
        # banked is unchanged: no set-aside, no extra check of the report.
        self.run_with({}, backend='banked', publish_result=False)
        self.assertFalse(self.seen[-1][1])

    def test_a_batch_retry_keeps_its_own_set_aside(self):
        with knowledge.imported_set_aside(MASTER_SYSTEM.id, 'a' * 64):
            self.run_with(MATCHING, backend='functions', publish_result=False)
            self.assertIn((MASTER_SYSTEM.id, 'a' * 64), knowledge._SET_ASIDE)

    def test_game_gear_uses_the_same_gate(self):
        rom = SimpleNamespace(sha256='b' * 64)
        with patch('retrorecomp.core.convert', side_effect=self.converter({})), \
             patch.object(type(GAME_GEAR), 'read_rom', return_value=rom):
            with self.assertRaises(ConversionError):
                GAME_GEAR.convert(Path('game.gg'), output=self.output, backend='functions', publish_result=False)


if __name__ == '__main__':
    unittest.main()
