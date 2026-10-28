"""The scan level a report carries: every writer of 1.6.0 writes `scan_level` (and the schema-2 `scan.level`);
the `advanced_scan.level` that the reports of 1.5.x held alone is no longer read for the collection."""
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from retrorecomp.compiled_games import Game, Inventory, report_level

SHA = 'ab' * 32


def console16_report(level, top=False):
    return {'tool': 'Retro-Recomp', 'system': 'md', 'rom': {'sha256': SHA},
            **({'scan_level': level} if top else {}),
            'advanced_scan': {'enabled': level != 'standard', 'level': level, 'scenarios': []}}


class ReportLevel(unittest.TestCase):
    def test_the_level_of_the_top_key_the_scan_section_and_an_upgraded_export_counts(self):
        for level in ('standard', 'extended', 'thorough'):
            self.assertEqual(report_level(console16_report(level, top=True)), level)
            self.assertEqual(report_level({'scan': {'level': level}}), level)
        # A quick check of an upgraded export keeps the discovery's level.
        upgraded = {**console16_report('quick'), 'scan_level': 'quick',
                    'upgrade': {'discovery': {'scan_level': 'thorough'}}}
        self.assertEqual(report_level(upgraded), 'thorough')
        self.assertEqual(report_level({'scan_level': 'extended'}), 'extended')
        self.assertEqual(report_level({'advanced_scan': True}), 'standard')
        self.assertEqual(report_level(None), 'standard')

    def test_a_report_of_1_5_x_with_the_level_only_under_advanced_scan_reads_as_standard(self):
        self.assertEqual(report_level(console16_report('thorough')), 'standard')


class CollectionLevels(unittest.TestCase):
    def test_rows_keep_their_saved_level_and_the_keys_of_the_old_migrations_are_not_written(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / 'compiled-games.json'
            rows = [Game(str(root / f'{system}.exe'), system, SHA, system, level='standard').__dict__
                    for system in ('md', 'snes', 'nes', 'sms')]
            path.write_text(json.dumps({'schema': 1, 'base': str(root), 'games': rows}), encoding='utf-8')
            inventory = Inventory(path, base=root)
            self.assertEqual({game.system: game.level for game in inventory.snapshot()},
                             {'md': 'standard', 'snes': 'standard', 'nes': 'standard', 'sms': 'standard'})
            inventory.save()
            saved = json.loads(path.read_text(encoding='utf-8'))
            self.assertNotIn('levels', saved)
            self.assertNotIn('legacy_paths', saved)


class ForgetShared(unittest.TestCase):
    def test_only_the_named_games_of_the_channel_are_forgotten(self):
        from retrorecomp import knowledge_exchange
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'shared.json'
            path.write_text(json.dumps({'account': {'md:1': {'hints': 'x'}, 'md:2': {'hints': 'y'}},
                                        'file': {'md:1': {'hints': 'x'}}}), encoding='utf-8')
            with patch.object(knowledge_exchange, '_shared_path', return_value=path):
                knowledge_exchange.forget_shared('account', ['md:1'])
            data = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(data, {'account': {'md:2': {'hints': 'y'}}, 'file': {'md:1': {'hints': 'x'}}})


if __name__ == '__main__':
    unittest.main()
