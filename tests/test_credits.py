import json
from pathlib import Path
import random
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from retrorecomp.credits_demo import ScrollState, PercussionMotion, EffectsGovernor
from retrorecomp.credits_music import TRACKS, MusicSession, MusicPlayer, choose_track, percussion_map
from retrorecomp.compilation_inputs import INTERFACE_MODULES


def run_frames(governor, fps, seconds, start=0.):
    """Feed evenly spaced frames; return the stages seen and the end time."""
    stages, now = [], start
    for _ in range(int(seconds*fps)):
        now += 1/fps
        stages.append(governor.frame(now))
    return stages, now


class CreditsTests(unittest.TestCase):
    def test_effects_shed_in_stages_and_never_return_in_the_same_opening(self):
        governor = EffectsGovernor('full')
        stages,_ = run_frames(governor, 30, 20)
        self.assertEqual(set(stages), {'full'})
        governor = EffectsGovernor('full')
        stages,now = run_frames(governor, 18, 8)
        self.assertEqual(stages[0], 'full')
        self.assertEqual(governor.stage, 'light')  # 18 fps is below 20 but above 15
        self.assertLess(stages.index('light')/18, 3.5)  # one warm-up second and one window
        self.assertEqual(stages, sorted(stages, key=('full','light','minimal').index))
        stages,_ = run_frames(governor, 60, 20, now)
        self.assertEqual(set(stages), {'light'})  # faster later, but no flicker back
        governor = EffectsGovernor('full')
        stages,_ = run_frames(governor, 12, 10)
        self.assertEqual(governor.stage, 'minimal')
        self.assertEqual([s for i,s in enumerate(stages) if i == 0 or s != stages[i-1]], ['full','light','minimal'])
        stages,_ = run_frames(EffectsGovernor('light'), 12, 10)
        self.assertEqual(stages[-1], 'minimal')

    def test_warm_up_and_hidden_time_are_not_measured(self):
        governor = EffectsGovernor('full')
        stages,now = run_frames(governor, 5, 1)  # the first second is always ignored
        stages,now = run_frames(governor, 30, 6, now)
        self.assertEqual(set(stages), {'full'})
        governor.reset(now+30)  # minimized for half a minute, then shown again
        stages,_ = run_frames(governor, 30, 6, now+30)
        self.assertEqual(set(stages), {'full'})

    def test_remembered_stage_is_upgraded_once_when_the_machine_is_comfortable(self):
        governor = EffectsGovernor('light')
        stages,now = run_frames(governor, 24, 20)
        self.assertEqual(set(stages), {'light'})  # fine, but not comfortably so
        governor = EffectsGovernor('light')
        stages,now = run_frames(governor, 30, 20)
        self.assertEqual(governor.stage, 'full')
        self.assertGreater(stages.index('full')/30, 4)  # several strong seconds first
        stages,now = run_frames(governor, 18, 10, now)
        self.assertEqual(governor.stage, 'light')  # the richer stage proved too slow
        stages,_ = run_frames(governor, 60, 20, now)
        self.assertEqual(set(stages), {'light'})  # tried once per opening only
        governor = EffectsGovernor('minimal')
        run_frames(governor, 30, 20)
        self.assertEqual(governor.stage, 'light')  # one stage richer, not two
        self.assertEqual(EffectsGovernor('bogus').stage, 'full')
        self.assertEqual(EffectsGovernor(None).stage, 'full')

    def test_percussion_roles_exclude_melodic_samples(self):
        root = Path(__file__).resolve().parents[1]/'MEDIAS/trackers_chiploom'
        for track in TRACKS:
            roles = percussion_map((root/track).read_bytes())
            expected = bytes((1,2,4)) if track.startswith('pocket') else bytes((1,2,4,5,6))
            self.assertEqual(roles[:len(expected)],expected)
            self.assertFalse(any(roles[len(expected):]))

    def test_percussion_motion_uses_new_hits_and_mute_consumes_them(self):
        motion = PercussionMotion()
        motion.update(0)
        motion.update(.03,(1,0,0,64,0,0),True)
        self.assertGreater(motion.height[0],0)
        self.assertEqual(motion.height[1],0)
        for i in range(1,121): motion.update(.03+i/60,(1,0,0,64,0,0),True)
        self.assertEqual(motion.height,[0.,0.]) # a held voice does not retrigger
        motion.update(2.1,(2,2,3,64,64,64),False)
        motion.update(2.13,(2,2,3,64,64,64),True)
        self.assertEqual(motion.height,[0.,0.])
        motion.update(2.16,(2,3,4,64,64,64),True)
        self.assertEqual(motion.height[0],0.)
        self.assertGreater(motion.height[1],0.)
        self.assertEqual(motion.shimmer,1.)

    def test_random_choice_never_repeats_and_reaches_all_tracks(self):
        last = None
        seen = set()
        rng = random.Random(33)
        for _ in range(500):
            current = choose_track(last, rng)
            self.assertNotEqual(current, last)
            seen.add(current)
            last = current
        self.assertEqual(seen, set(TRACKS))

    def test_choice_and_mute_survive_a_new_application(self):
        with tempfile.TemporaryDirectory() as folder, patch('retrorecomp.credits_music.MusicPlayer'):
            path = Path(folder)/'datas/credits.json'
            previous = None
            for _ in range(20):
                session = MusicSession(path)
                session.open()
                self.assertNotEqual(session.previous, previous)
                session.set_muted(True)
                previous = session.previous
            self.assertEqual(session.effects, 'full')
            session.set_effects('light')
            session = MusicSession(path)
            self.assertTrue(session.muted)
            self.assertEqual(session.previous, previous)
            self.assertEqual(session.effects, 'light')
            self.assertLess(path.stat().st_size, 200)

    def test_invalid_saved_state_is_nonfatal(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'state.json'
            for state in ('{bad', '[]', 'null', '{"muted": "yes"}', '{"effects": 3}'):
                path.write_text(state)
                self.assertFalse(MusicSession(path).muted)
                self.assertEqual(MusicSession(path).effects, 'full')

    def test_scrolling_resumes_after_interaction_and_holds_while_dragging(self):
        state = ScrollState()
        state.maximum = 500
        state.wait = 0
        state.tick(1)
        self.assertEqual(state.position, 20)
        state.manual(180)
        state.tick(1)
        self.assertEqual(state.position, 180)
        state.tick(1, hovering=True)
        self.assertEqual(state.position, 180)
        state.tick(1)
        self.assertEqual(state.position, 180)
        state.tick(1)
        self.assertEqual(state.position, 200)
        state.manual(900)
        self.assertEqual(state.position, 500)
        state.manual(-50)
        self.assertEqual(state.position, 0)

    def test_last_credit_pauses_then_reverses_without_jumping(self):
        state = ScrollState()
        state.maximum, state.position, state.wait = 500, 490, 0
        state.tick(1)
        self.assertEqual(state.position, 500)
        state.tick(4)
        self.assertEqual(state.position, 500)
        state.tick(1)
        state.tick(.1)
        self.assertEqual(state.position, 478)
        self.assertEqual(state.direction, -1)
        state.position = 3
        state.tick(1)
        self.assertEqual(state.position, 0)
        self.assertEqual(state.direction, 1)

    def test_missing_player_does_not_leave_a_thread_or_crash_ui(self):
        with patch('retrorecomp.credits_music.Decoder', side_effect=OSError('no device')):
            player = MusicPlayer(TRACKS[0])
            player.thread.join(3)
            self.assertFalse(player.thread.is_alive())
            self.assertEqual(player.status, 'unavailable')
            player.close()

    def test_close_while_loading_never_starts_late_audio(self):
        entered, release = threading.Event(), threading.Event()
        calls = []

        class SlowDecoder:
            def __init__(self, data):
                entered.set()
                release.wait(3)
            def start(self): calls.append('start')
            def close(self): calls.append('close')

        with patch('retrorecomp.credits_music.Decoder', SlowDecoder):
            player = MusicPlayer(TRACKS[0])
            self.assertTrue(entered.wait(2))
            player.close()
            release.set()
            player.thread.join(3)
            self.assertFalse(player.thread.is_alive())
            self.assertEqual(calls, ['close'])

    def test_player_shutdown_is_serialized_on_rapid_reopen(self):
        opened = []
        active = []

        class FakeDecoder:
            def __init__(self, data): pass
            def start(self):
                active.append(self)
                opened.append(len(active))
            def mute(self, value): pass
            def info(self): return (0,)*10
            def beats(self): return (0,)*6
            def close(self):
                time.sleep(.03)
                if self in active: active.remove(self)

        with patch('retrorecomp.credits_music.Decoder', FakeDecoder):
            first = MusicPlayer(TRACKS[0])
            limit = time.monotonic()+2
            while first.status != 'playing' and time.monotonic()<limit: time.sleep(.01)
            self.assertEqual(first.status, 'playing')
            first.close()
            second = MusicPlayer(TRACKS[1])
            limit = time.monotonic()+2
            while second.status != 'playing' and time.monotonic()<limit: time.sleep(.01)
            second.close()
            first.thread.join(3); second.thread.join(3)
        self.assertEqual(opened, [1, 1])
        self.assertFalse(active)

    def test_converter_ui_does_not_invalidate_game_profiles(self):
        self.assertTrue({'credits_demo','credits_music','dialogs'} <= INTERFACE_MODULES)
