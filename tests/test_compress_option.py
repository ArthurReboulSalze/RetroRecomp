"""The player's option "Compress games" (preference `compress_games`, command line `--no-compress`).

It exists because Windows Defender sometimes mistakes a freshly built, UPX-packed game for a threat (a false positive).
With the option off, UPX is never run: the game is published exactly as built and validated, the conversion log and the
report say so, and the packed replay of gate G5 names an unpacked delivered file. Nothing here starts UPX, converts a game
or touches the real preferences (the window's `save_preferences` and `load_preferences` are replaced).
"""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import MagicMock, patch

from retrorecomp import packing
from retrorecomp.delivery_evidence import deliver_packed
from retrorecomp.gui import Application
from retrorecomp.gui_common import INTERFACE_PREFERENCES
from retrorecomp.i18n import STRINGS, tr
from retrorecomp.languages import LANGUAGES
from retrorecomp.publishing import publish_executable
from tools.gui_patching import patch_gui


def no_upx(*args, **options):
    raise AssertionError(f'UPX was run: {args}')


class CompressionStateTests(unittest.TestCase):
    """The setting of the process: on unless turned off, and what the saved preference means."""

    def setUp(self):
        self.addCleanup(packing.set_compression, packing.compression_enabled())
        self.addCleanup(packing._UNPACKED_REASONS.clear)

    def test_games_are_compressed_by_default(self):
        packing.set_compression(True)
        self.assertTrue(packing.compression_enabled())
        packing.set_compression(False)
        self.assertFalse(packing.compression_enabled())

    def test_the_saved_preference_defaults_to_on_and_only_false_turns_it_off(self):
        self.assertTrue(packing.compression_from_preferences({}))
        self.assertTrue(packing.compression_from_preferences({'compress_games': True}))
        self.assertFalse(packing.compression_from_preferences({'compress_games': False}))
        # A damaged file never switches the compression off by accident.
        for junk in (None, 0, 'no', [], {}):
            self.assertTrue(packing.compression_from_preferences({'compress_games': junk}), junk)


class UncompressedPublicationTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.built = self.root / 'built.exe'
        self.built.write_bytes(b'MZ' + bytes(range(200)) + b'native game')
        self.addCleanup(packing.set_compression, packing.compression_enabled())
        self.addCleanup(packing._UNPACKED_REASONS.clear)
        packing.set_compression(False)

    def test_no_packer_runs_the_file_is_untouched_and_the_notice_goes_to_the_log(self):
        before = self.built.read_bytes()
        log = []
        with patch('retrorecomp.packing.subprocess.run', side_effect=no_upx), \
                patch('retrorecomp.packing.compact_windows', side_effect=no_upx), \
                patch('retrorecomp.packing.compact_linux', side_effect=no_upx):
            outcome = packing.compact_executable(self.built, log.append)
        self.assertEqual(outcome, {'notice': packing.UNCOMPRESSED_NOTICE})
        self.assertEqual(log, [packing.UNCOMPRESSED_NOTICE])
        self.assertIn('Published uncompressed', packing.UNCOMPRESSED_NOTICE)
        self.assertIn('Compress games', packing.UNCOMPRESSED_NOTICE)
        self.assertEqual(self.built.read_bytes(), before)

    def test_without_a_log_the_notice_goes_to_stderr_once(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), patch('retrorecomp.packing.subprocess.run', side_effect=no_upx):
            packing.compact_executable(self.built)
        self.assertEqual(stderr.getvalue().count(packing.UNCOMPRESSED_NOTICE), 1)

    def test_turning_the_option_on_again_goes_back_to_the_packer(self):
        packing.set_compression(True)
        called = []
        which = 'compact_windows' if os.name == 'nt' else 'compact_linux'
        with patch(f'retrorecomp.packing.{which}', side_effect=lambda path: called.append(path)):
            self.assertIsNone(packing.compact_executable(self.built, MagicMock()))
        self.assertEqual(called, [self.built])

    def test_publication_publishes_the_build_as_it_is(self):
        target = self.root / 'out' / 'Game.exe'
        target.parent.mkdir()
        log = []
        with patch('retrorecomp.packing.subprocess.run', side_effect=no_upx):
            pending = publish_executable(self.built, target, start_worker=False, compact=True, emit=log.append)
        self.assertFalse(pending)
        self.assertEqual(target.read_bytes(), self.built.read_bytes())
        self.assertEqual(log, [packing.UNCOMPRESSED_NOTICE])

    def test_the_report_says_unpacked_and_why(self):
        unpacked = packing.file_identity(self.built)
        target = self.root / 'Game.exe'
        with patch('retrorecomp.packing.subprocess.run', side_effect=no_upx):
            publish_executable(self.built, target, start_worker=False, compact=True, emit=lambda text: None)
        record = packing.packing_record(unpacked, target)
        self.assertIs(record['packed'], False)
        self.assertEqual(record['unpacked_reason'], packing.UNCOMPRESSED_NOTICE)
        self.assertEqual(record['published'], unpacked)
        self.assertEqual(record['size_ratio'], 1.0)
        self.assertEqual(record['compared_on'], 'unpacked build executable')
        # A machine that replayed its delivered file does not claim a packed copy was replayed.
        replayed = packing.packing_record(unpacked, target, packed_replayed=True)
        self.assertNotIn('packed copy', replayed['compared_on'])
        self.assertIn('also unpacked', replayed['compared_on'])
        self.assertIn('not compressed', replayed['packed_validation'])

    def test_the_gate_g5_copy_is_delivered_unpacked_without_packing(self):
        copy = self.root / 'packed-game.exe'
        said = []
        with patch('retrorecomp.packing.subprocess.run', side_effect=no_upx):
            delivered = deliver_packed(self.built, copy, 'Test', said.append)
        self.assertEqual(delivered.kind, 'unpacked')
        self.assertEqual(delivered.notice, {'notice': packing.UNCOMPRESSED_NOTICE})
        self.assertEqual(said, [packing.UNCOMPRESSED_NOTICE,
                                'Test: comparing the unpacked executable with the fresh reference.'])
        self.assertEqual(copy.read_bytes(), self.built.read_bytes())
        self.assertEqual(delivered.sha256, hashlib.sha256(self.built.read_bytes()).hexdigest())

    def test_with_the_option_on_the_same_copy_goes_through_the_packer(self):
        packing.set_compression(True)
        copy = self.root / 'packed-game.exe'
        which = 'compact_windows' if os.name == 'nt' else 'compact_linux'
        with patch(f'retrorecomp.packing.{which}', return_value=None) as packer:
            delivered = deliver_packed(self.built, copy, 'Test', lambda text: None)
        packer.assert_called_once_with(copy)
        self.assertEqual(delivered.kind, 'packed')


class CommandLineTests(unittest.TestCase):
    """`--compress` / `--no-compress` on convert and batch, with the saved option as the default."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.addCleanup(packing.set_compression, packing.compression_enabled())

    def run_main(self, command, flag, preference):
        import RetroRecomp
        from retrorecomp.batch import BatchItem
        rom = self.root / 'game.sms'
        rom.write_bytes(b'rom')
        item = BatchItem(path=rom, system='sms', sha256='0' * 64, title='Game')
        seen = []
        result = {'games': [{'status': 'success', 'system': 'sms', 'sha256': item.sha256,
                             'executable': str(self.root / 'game')}],
                  'succeeded': 1, 'requested': 1, 'failed': 0, 'current': 0, 'existing': 0, 'pending': 0}

        def convert(*args, **options):
            seen.append(packing.compression_enabled())   # what the publication of this batch would see
            return result
        argv = ['RetroRecomp.py', command, str(rom), '--output', str(self.root / 'out')] + ([flag] if flag else [])
        outcome = {'paths': {}, 'summary': None, 'error': None, 'base': None}
        with patch('sys.argv', argv), patch('RetroRecomp.load_preferences', return_value=preference), \
                patch('RetroRecomp.identify', return_value=item), patch('RetroRecomp.convert_batch', side_effect=convert), \
                patch('RetroRecomp.save_game_language'), patch('retrorecomp.shared_batch.prepare', return_value=outcome), \
                patch('retrorecomp.online.forget_shared'), patch('sys.stdout'), patch('sys.stderr'):
            self.assertEqual(RetroRecomp.main(), 0)
        return seen

    def test_the_switch_and_the_saved_option_decide_what_the_batch_publishes(self):
        for command in ('batch', 'convert'):
            for flag, preference, expected in ((None, {}, True), ('--no-compress', {}, False),
                                               (None, {'compress_games': False}, False),
                                               ('--compress', {'compress_games': False}, True),
                                               ('--no-compress', {'compress_games': True}, False)):
                with self.subTest(command=command, flag=flag, preference=preference):
                    packing.set_compression(not expected)   # whatever an earlier run left is replaced
                    self.assertEqual(self.run_main(command, flag, preference), [expected])

    def test_the_help_says_why_the_switch_exists(self):
        import RetroRecomp
        for command in ('batch', 'convert'):
            out = io.StringIO()
            with patch('sys.argv', ['RetroRecomp.py', command, '--help']), contextlib.redirect_stdout(out), \
                    self.assertRaises(SystemExit):
                RetroRecomp.main()
            text = ' '.join(out.getvalue().split())
            self.assertIn('--no-compress', text, command)
            self.assertIn('Windows Defender', text, command)


class WindowOptionTests(unittest.TestCase):
    """The option in the window: saved with the preferences, never passed to a converter, applied when a batch starts."""

    def test_it_is_an_interface_preference_and_applied_by_both_conversion_paths(self):
        self.assertIn('compress_games', INTERFACE_PREFERENCES)
        from tools.gui_patching import gui_source
        self.assertEqual(gui_source().count("set_compression(options.get('compress_games', True))"), 2)

    def test_a_started_batch_sets_the_compression_of_its_publications(self):
        self.addCleanup(packing.set_compression, packing.compression_enabled())
        window = MagicMock()
        window.busy = window.updating = window.importing = False
        window.table.get_children.return_value = ['row']
        window.table.selection.return_value = ['row']
        window.items = {'row': MagicMock(system='sms', error=None)}
        window.output.get.return_value = '  Games  '
        for enabled in (False, True):
            window.preferences.return_value = {
                'passes': 3, 'frames': 100, 'jobs': 1, 'output': 'Games', 'compress_games': enabled,
                'use_shared_base': False}
            packing.set_compression(not enabled)
            window.busy = False   # the first start leaves the window busy
            with patch('retrorecomp.gui_conversion.save_preferences'), \
                    patch('retrorecomp.gui_conversion.threading.Thread'), \
                    patch('retrorecomp.gui_conversion.messagebox'):
                from retrorecomp.gui_conversion import ConversionMixin
                ConversionMixin.start(window)
            self.assertEqual(packing.compression_enabled(), enabled)

    def test_every_language_has_the_label_and_the_explanation(self):
        for key in ('compress_games', 'compress_games_note'):
            self.assertIn(key, STRINGS)
            for code in LANGUAGES:
                self.assertTrue(tr(key, code).strip(), (key, code))
        note = tr('compress_games_note', 'en')
        self.assertIn('Windows Defender', note)
        self.assertIn('false positive', note)
        for code in LANGUAGES:
            self.assertIn('Windows Defender', tr('compress_games_note', code), code)


@unittest.skipUnless(os.environ.get('DISPLAY') or os.name == 'nt', 'needs a Tk display (kept hidden)')
class RealWindowTests(unittest.TestCase):
    """The real widgets, in a window that is never shown. Preferences are read from a dict and never written."""

    def open(self, preferences=None):
        folder = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        for item in (patch_gui('load_preferences', return_value=preferences or {}),
                     patch_gui('preferred_games_root', return_value=(folder / 'exports', False)),
                     patch_gui('data_directory', return_value=folder),
                     patch('retrorecomp.compiled_games.data_directory', return_value=folder),
                     patch_gui('save_preferences'),
                     patch_gui('save_cover_settings')):
            item.start()
            self.addCleanup(item.stop)
        try:
            root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(str(error))
        root.withdraw()
        window = Application(root)
        self.addCleanup(self.close, root)
        root.update_idletasks()
        for name in ('deiconify', 'grab_set'):
            patcher = patch.object(tk.Toplevel, name)
            patcher.start()
            self.addCleanup(patcher.stop)
        return root, window

    @staticmethod
    def close(root):
        def widgets(parent):
            yield parent
            for child in parent.winfo_children():
                yield from widgets(child)
        owners = {name: widget for widget in widgets(root) for name in (widget._tclCommands or [])}
        for job in root.tk.call('after', 'info'):
            command = root.tk.call('after', 'info', job)[0]
            owners.get(command, root).after_cancel(job)
        root.destroy()

    @staticmethod
    def walk(widget):
        for child in widget.winfo_children():
            yield child
            yield from RealWindowTests.walk(child)

    def test_on_by_default_and_saved_with_the_preferences(self):
        _, window = self.open({})
        self.assertTrue(window.compress_games.get())
        self.assertIs(window.preferences()['compress_games'], True)

    def test_a_saved_choice_comes_back(self):
        _, window = self.open({'compress_games': False})
        self.assertFalse(window.compress_games.get())
        self.assertIs(window.preferences()['compress_games'], False)
        window.compress_games.set(True)
        self.assertIs(window.preferences()['compress_games'], True)

    def test_the_option_sits_in_options_common_with_its_explanation(self):
        root, window = self.open({})
        window.show_options()
        root.update_idletasks()
        boxes = [w for w in self.walk(window.options_panel) if isinstance(w, ttk.Checkbutton)
                 and w.cget('text') == window.tr('compress_games')]
        self.assertEqual(len(boxes), 1)
        notes = [w for w in self.walk(window.options_panel) if isinstance(w, ttk.Label)
                 and w.cget('text') == window.tr('compress_games_note')]
        self.assertEqual(len(notes), 1)
        self.assertEqual(str(boxes[0].master), str(notes[0].master))   # the same list as the other common options
        boxes[0].invoke()
        self.assertIs(window.preferences()['compress_games'], False)
        with patch_gui('save_preferences') as saved:
            window.close_options()
        self.assertIs(saved.call_args.args[0]['compress_games'], False)


if __name__ == '__main__':
    unittest.main()
