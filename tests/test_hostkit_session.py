"""The host kit's multiplayer session through its real loop (tools/hostkit_session_selftest.py): alone as before, delay with four
ports, rollback with silent frames, a guest, pause for everyone, a refused option, the pipe lost, F8 refused, no session in a
test run. Runs when a C compiler and the pinned SDL2 build are available, and skips cleanly otherwise. No ROM, no visible window,
no sound device, no network: the two pipes are anonymous and local."""
import importlib.util
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / 'native/hostkit'
spec = importlib.util.spec_from_file_location('hostkit_session_selftest', ROOT / 'tools' / 'hostkit_session_selftest.py')
selftest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selftest)


class SessionThroughTheLoopTests(unittest.TestCase):
    def test_alone_delay_rollback_guest_pause_refusal_and_lost_pipe(self):
        reason = selftest.ready()
        if reason:
            self.skipTest(reason)
        code, output, seconds = selftest.run_checks(ROOT / '.build/hostkit-session-selftest')
        self.assertEqual(code, 0, output)
        self.assertIn('PASS: 18 scenarios', output)       # restart alone, host, guest, unknown flag (ABI 2); chat x2 (ABI 3);
                                                         # the match's state: host, guest, a load with nothing saved (ABI 4)
        self.assertLess(seconds, 120, output)     # a hang, not a speed


class SoloPathTests(unittest.TestCase):
    """Alone, the game reads its controls and runs its frames as before: the session is reached through one flag."""

    def test_the_pad_word_asks_the_session_only_in_a_session(self):
        text = (KIT / 'shell/rrhk_input.c').read_text(encoding='utf-8')
        self.assertIn('if (rrhk_session_on) return rrhk_session_port(p);\n    return rrhk_local_pad_word(p, frame);', text)

    def test_the_session_starts_only_from_the_converter_s_pipes(self):
        text = (KIT / 'shell/rrhk_session.inc').read_text(encoding='utf-8')
        self.assertIn('if (!value || !*value) return true;                 /* alone: nothing changes */', text)
        # the game never touches the network: no socket call anywhere in the session
        self.assertNotRegex(text, r'\b(socket|connect|bind|sendto|recvfrom)\s*\(')

    def test_the_session_file_is_included_not_listed(self):
        from retrorecomp import hostkit
        self.assertNotIn('shell/rrhk_session.inc', hostkit.SHELL)
        self.assertIn('shell/rrhk_session.inc', hostkit.SHELL_INCLUDED)
        main = (KIT / 'shell/rrhk_main.c').read_text(encoding='utf-8')
        self.assertTrue(main.rstrip().endswith('#include "rrhk_session.inc"'))

    def test_the_restart_is_the_solo_one_without_a_session(self):
        # Shift+F1 and the pad combination restart at once alone, exactly as before; the session's request is reached only
        # through rrhk_session_on (and answers false without it). The selftest's "restart alone" runs it through the loop.
        events = (KIT / 'shell/rrhk_events.c').read_text(encoding='utf-8')
        self.assertIn('if (rrhk_session_on) rrhk_session_restart();\n            else { m->reset(); rrhk_audio_pause_output(run); }',
                      events)
        main = (KIT / 'shell/rrhk_main.c').read_text(encoding='utf-8')
        self.assertIn('if (!rrhk_session_on) { m->reset(); rrhk_audio_pause_output(r); rrhk.menu = 0; }', main)
        session = (KIT / 'shell/rrhk_session.inc').read_text(encoding='utf-8')
        self.assertIn('bool rrhk_session_restart(void) {\n    if (!rrhk_session_on) return false;', session)

    def test_the_abi_is_versioned(self):
        header = (KIT / 'hostkit_session.h').read_text(encoding='utf-8')
        self.assertRegex(header, r'#define RRHK_SESSION_ABI \d+')
        self.assertTrue(re.search(r'RRHK_MSG_HELLO = 1, .*u16 abi', header))


if __name__ == '__main__':
    unittest.main()
