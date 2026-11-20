"""What a launched game says, kept (retrorecomp/game_logs.py), and the room log's line on how each match ended
(the lead's GO of 20 Nov 2026, after Mario Kart: Super Circuit's link close left no trace on either PC)."""
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from retrorecomp import game_logs
from retrorecomp.netplay import room_worker
from retrorecomp.netplay.room_log import RoomLog
from retrorecomp.netplay.session_game import SessionGame


class GameLogFiles(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name) / 'games'

    def test_a_new_log_per_launch_and_only_the_twenty_most_recent_are_kept(self):
        self.folder.mkdir()
        for index in range(25):
            path = self.folder / f'old-{index:02d}.log'
            path.write_text('x', encoding='utf-8')
            os.utime(path, (1_700_000_000 + index, 1_700_000_000 + index))
        path = game_logs.new_game_log(Path('C:/games/Mario Kart - Super Circuit.exe'), self.folder)
        self.assertTrue(path.name.startswith('Mario Kart - Super Circuit-'))
        self.assertEqual(path.parent, self.folder)
        path.write_text('[host] started\n', encoding='utf-8')
        logs = sorted(p.name for p in self.folder.glob('*.log'))
        self.assertEqual(len(logs), game_logs.KEEP_FILES)
        self.assertNotIn('old-05.log', logs)                    # the oldest went
        self.assertIn('old-24.log', logs)
        again = game_logs.new_game_log(Path('Mario Kart - Super Circuit.exe'), self.folder)
        self.assertNotEqual(again, path)                        # two launches in one second: two files

    def test_a_long_log_is_cut_to_its_last_64_kb_from_a_line_start(self):
        self.folder.mkdir()
        path = self.folder / 'long.log'
        lines = [f'[host] frame {index}\n' for index in range(20000)]
        path.write_text(''.join(lines), encoding='utf-8')
        game_logs.cut(path)
        text = path.read_text(encoding='utf-8')
        self.assertLessEqual(len(text.encode()), game_logs.KEEP_BYTES + 100)
        self.assertTrue(text.startswith('[log] the start of this log was cut'))
        self.assertTrue(text.splitlines()[1].startswith('[host] frame '))     # a whole line, never half of one
        self.assertTrue(text.endswith('[host] frame 19999\n'))
        game_logs.cut(path)                                     # already small: unchanged
        self.assertEqual(path.read_text(encoding='utf-8'), text)

    def test_the_reason_line_is_the_one_that_says_why_the_game_stopped(self):
        self.folder.mkdir()
        path = self.folder / 'game.log'
        path.write_text('[host] renderer=software\n'
                        '[session] started: seat 1, 2 ports\n'
                        '[host] the link cable stopped: multiplayer native dispatch entry is missing: 0x080a1234\n'
                        '[session] stopped by Retro-Recomp (3)\n'
                        '[host] audio produced=2663036 played=2663036\n', encoding='utf-8')
        self.assertEqual(game_logs.reason_line(path), '[session] stopped by Retro-Recomp (3)')
        path.write_text('[host] the link cable stopped: multiplayer native dispatch entry is missing: 0x080a1234\n'
                        '[host] audio produced=1\n', encoding='utf-8')
        self.assertIn('dispatch entry is missing: 0x080a1234', game_logs.reason_line(path))
        path.write_text('[session] started: seat 2\n[host] audio produced=447746 missing=326 trimmed=0\n', encoding='utf-8')
        self.assertEqual(game_logs.reason_line(path), '[host] audio produced=447746 missing=326 trimmed=0')  # a counter: no reason
        path.write_text('[host] audio produced=1\nsomething else\n', encoding='utf-8')
        self.assertEqual(game_logs.reason_line(path), '[host] audio produced=1')     # no reason: its last own line
        self.assertEqual(game_logs.reason_line(None), '')
        self.assertEqual(game_logs.reason_line(self.folder / 'missing.log'), '')

    def test_the_folder_is_datas_logs(self):
        with patch('retrorecomp.paths.data_directory', lambda root=None: Path('D:/x/datas')):
            self.assertEqual(game_logs.logs_folder(), Path('D:/x/datas/logs'))


class SessionGameOutput(unittest.TestCase):
    def test_stdout_and_stderr_go_to_one_file_when_they_are_the_same(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'game.log'
            code = "import sys; print('[host] to stdout', flush=True); print('[host] the link cable stopped: x', file=sys.stderr)"
            game = SessionGame(Path(sys.executable), stdout=path, stderr=path, arguments=('-c', code))
            self.assertEqual(game.log_path, path)
            self.assertEqual(game.finish(timeout=30), 0)
            text = path.read_text(encoding='utf-8')
            self.assertIn('[host] to stdout', text)
            self.assertIn('[host] the link cable stopped: x', text)


class MatchEndLine(unittest.TestCase):
    def worker(self, folder: Path, role='host'):
        worker = room_worker.RoomWorker.__new__(room_worker.RoomWorker)
        worker.log = RoomLog(folder / 'room.log')
        worker.game_logs = folder / 'games'
        worker.role = role
        return worker

    def test_the_room_log_says_how_a_match_ended_with_the_games_reason_and_exit_code(self):
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            game_log = folder / 'games' / 'Mario Kart.log'
            game_log.parent.mkdir()
            game_log.write_text('[host] frame\n' * 10_000 + '[host] the link cable stopped: multiplayer native dispatch entry '
                                'is missing: 0x080a1234\n[host] audio produced=1\n', encoding='utf-8')
            worker = self.worker(folder)
            match = SimpleNamespace(match_id=5, session=SimpleNamespace(log_path=game_log),
                                    driver=SimpleNamespace(outcome='broke', detail='the machine stopped'))
            worker._log_end(match, {'exit_code': 0})
            line = (folder / 'room.log').read_text(encoding='utf-8').strip()
            self.assertTrue(line.endswith('match 5 over: broke (the machine stopped), exit 0 - [host] the link cable '
                                          'stopped: multiplayer native dispatch entry is missing: 0x080a1234'), line)
            self.assertLessEqual(game_log.stat().st_size, game_logs.KEEP_BYTES + 100)     # cut once the match is over

    def test_a_guest_writes_the_line_too_and_a_match_without_a_log_says_no_reason(self):
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            worker = self.worker(folder, role='guest')
            match = SimpleNamespace(match_id=2, session=SimpleNamespace(log_path=None),
                                    driver=SimpleNamespace(outcome='ended', detail=''))
            worker._log_end(match, {'exit_code': None})
            self.assertTrue((folder / 'room.log').read_text(encoding='utf-8').strip().endswith(
                'match 2 over: ended, exit unknown'))

    def test_a_started_game_gets_its_log_in_the_games_folder(self):
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            worker = self.worker(folder)
            seen = {}

            def session(executable, cwd=None, env=None, stdout=None, stderr=None, arguments=()):
                seen.update(stdout=stdout, stderr=stderr)
                return SimpleNamespace(log_path=stderr)
            with patch.object(room_worker, 'SessionGame', session):
                worker._open_game({'exe': 'C:/games/Tetris.exe'})
                self.assertEqual(seen['stdout'], seen['stderr'])
                self.assertEqual(seen['stderr'].parent, folder / 'games')
                self.assertTrue(seen['stderr'].name.startswith('Tetris-'))
                worker._open_game({'exe': 'C:/games/Tetris.exe', 'stderr': str(folder / 'given.log')})
                self.assertEqual((seen['stdout'], seen['stderr']), (None, folder / 'given.log'))   # a given file wins
                worker.game_logs = None
                worker._open_game({'exe': 'C:/games/Tetris.exe'})
                self.assertEqual((seen['stdout'], seen['stderr']), (None, None))                   # no room log: nowhere


class GuestConfig(unittest.TestCase):
    def test_a_guest_keeps_a_room_log_in_the_folder_it_is_given(self):
        from retrorecomp.netplay import invitation, lobby_client
        text = invitation.format_invitation('192.168.1.20', 24611, bytes(range(16)), tests=True)
        config = lobby_client.guest_config(text, 'Karl', Path('D:/x/datas/logs'), tests=True)
        self.assertEqual(Path(config['room']['log']), Path('D:/x/datas/logs/room.log'))


if __name__ == '__main__':
    unittest.main()
