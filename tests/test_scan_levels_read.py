"""Mega Drive, Super Nintendo and NES reports keep their scan level under
advanced_scan; 1.5.2-1.5.5 read only the top level, so their Extended and
Thorough conversions showed one star and were declared Standard (1.5.6)."""
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from retrorecomp import online
from retrorecomp.compiled_games import Game, Inventory, report_level

SHA = 'ab' * 32


def console16_report(level):
    return {'tool': 'Retro-Recomp', 'system': 'md', 'rom': {'sha256': SHA},
            'advanced_scan': {'enabled': level != 'standard', 'level': level, 'scenarios': []}}


class ReportLevel(unittest.TestCase):
    def test_the_level_under_advanced_scan_counts(self):
        for level in ('standard', 'extended', 'thorough'):
            self.assertEqual(report_level(console16_report(level)), level)
        # A quick check of an upgraded export keeps the discovery's level.
        upgraded = {**console16_report('quick'), 'upgrade': {'discovery': {'scan_level': 'thorough'}}}
        self.assertEqual(report_level(upgraded), 'thorough')
        # Consoles writing the level at the top are read as before.
        self.assertEqual(report_level({'scan_level': 'extended'}), 'extended')
        self.assertEqual(report_level({'advanced_scan': True}), 'standard')
        self.assertEqual(report_level(None), 'standard')


class CollectionLevels(unittest.TestCase):
    def test_rows_saved_before_are_read_once_more(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / 'compiled-games.json'
            rows = [Game(str(root / f'{system}.exe'), system, SHA, system, level='standard').__dict__
                    for system in ('md', 'snes', 'nes', 'sms')]
            path.write_text(json.dumps({'schema': 1, 'base': str(root), 'games': rows}), encoding='utf-8')
            inventory = self.inventory(path, root)
            levels = {game.system: game.level for game in inventory.snapshot()}
            self.assertEqual(levels, {'md': '', 'snes': '', 'nes': '', 'sms': 'standard'})
            inventory.save()
            self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['levels'], 2)
            again = self.inventory(path, root)
            for game in again.snapshot():
                game.level = game.level or 'standard'
            again.save()
            third = self.inventory(path, root)
            self.assertEqual({game.level for game in third.snapshot()}, {'standard'})

    def inventory(self, path, root):
        return Inventory(path, base=root)


class ResendDeeperLevels(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.games = []
        for system, level in (('md', 'thorough'), ('snes', 'extended'), ('nes', 'standard'), ('sms', 'extended')):
            report = self.root / f'{system}.json'
            data = console16_report(level) if system != 'sms' else {'scan_level': level}
            report.write_text(json.dumps(data), encoding='utf-8')
            self.games.append(Game(str(self.root / f'{system}.exe'), system, SHA, system, report=str(report)))
        self.patches = [patch.object(online, 'account', return_value={'service': 'https://example.test', 'email': 'a@b'}),
                        patch.object(online, 'sending_available', return_value=True),
                        patch.object(online, '_account_path', return_value=self.root / 'account.json')]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in self.patches:
            item.stop()
        self.temp.cleanup()

    def test_deeper_conversions_are_noted_once_and_their_sharing_forgotten(self):
        with patch.object(online, 'note_conversion', return_value=True) as note, \
                patch('retrorecomp.knowledge_exchange.forget_shared') as forget:
            self.assertEqual(online.resend_deeper_levels(self.games), 2)
            self.assertEqual(sorted(call.args[0] for call in note.call_args_list), ['md', 'snes'])
            forget.assert_called_once_with('account', [f'md:{SHA}', f'snes:{SHA}'])
            # Once per account.
            self.assertEqual(online.resend_deeper_levels(self.games), 0)
            self.assertEqual(note.call_count, 2)

    def test_signed_out_does_nothing(self):
        with patch.object(online, 'account', return_value=None), \
                patch.object(online, 'note_conversion') as note:
            self.assertEqual(online.resend_deeper_levels(self.games), 0)
            note.assert_not_called()


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
