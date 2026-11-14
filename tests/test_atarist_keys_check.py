"""The keys held across a quick state (Atari ST): the check's scripts, and the two places that make a load right (the adapted Hatari releases the keys a snapshot holds down; the adapter presses
again the keys still held once the restore is over). No game, no TOS: the games are the player's."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def tool():
    spec = importlib.util.spec_from_file_location('atarist_keys_check', ROOT / 'tools' / 'atarist_keys_check.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ScriptTests(unittest.TestCase):
    def test_the_pad_holds_cover_fire_a_direction_and_the_left_button_over_the_same_frames(self):
        holds = tool().pad_holds(900, 1300)
        self.assertEqual({(begin, end) for begin, end, *_ in holds}, {(900, 1300)})
        self.assertEqual({(kind, code) for _, _, kind, code, _ in holds}, {('joy', 4), ('joy', 3), ('mouse', 2)})

    def test_the_key_is_held_until_the_save_frame_or_beyond_it(self):
        module = tool()
        for until in (module.KEY_SAVE, 2100):
            held = [event for event in module.key_script(until) if event[3] == module.KEY_N]
            self.assertEqual(held, [(1700, until, 'key', module.KEY_N, 1)])
        self.assertLess(1700, module.KEY_SAVE < 2100 and module.KEY_SAVE)

    def test_without_arguments_the_tool_says_how_to_use_it(self):
        self.assertEqual(tool().main([]), 2)


class RestoreTests(unittest.TestCase):
    def test_the_adapted_hatari_releases_the_held_keys_before_the_restore_flag_falls(self):
        from retrorecomp import atarist_hatari
        text = ''.join(new for rel, _, new in atarist_hatari.REPLACEMENTS if rel == 'src/memorySnapShot.c')
        released = text.index('IKBD_PressSTKey ( (uint8_t)rr_scan , false )')
        self.assertIn('Keyboard.KeyStates[rr_scan] = false', text)
        self.assertLess(released, text.index('rr_snapshot_restoring = 0;'))

    def test_the_adapter_waits_after_a_load_and_then_presses_the_held_keys_again(self):
        text = (ROOT / 'native' / 'hostkit' / 'adapters' / 'rrhk_atarist.inc').read_text(encoding='utf-8')
        self.assertIn('sa.settle = 3;', text)
        self.assertIn('if (sa.settle && !--sa.settle) memset(sa.held, 0, sizeof sa.held);', text)
        self.assertLess(text.index('memset(sa.held, 0, sizeof sa.held)'), text.index('rr_st_key(session, n, held[n])'))


if __name__ == '__main__':
    unittest.main()
