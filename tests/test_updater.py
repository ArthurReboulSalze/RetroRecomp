"""The converter updater downloads and replaces one verified executable."""
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from smsrecomp.updater import (Update, _install_files, apply_update,
                               discard_update, finish_update, prepare_update, select_update)


class UpdaterTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.exe = self.root / "Retro-Recomp.exe"
        self.exe.write_bytes(b"MZold converter")

    def _prepare(self, data=b"MZnew converter"):
        update = Update("0.14.2", "https://github.com/example/Retro-Recomp.exe",
                        "https://github.com/example/tag", hashlib.sha256(data).hexdigest(), len(data))
        with patch("smsrecomp.updater.urllib.request.urlopen", return_value=io.BytesIO(data)):
            return prepare_update(update, self.exe)

    def test_selects_newest_executable_and_ignores_drafts_and_zips(self):
        def release(version, name="Retro-Recomp.exe", draft=False):
            return {"tag_name": version, "draft": draft, "prerelease": True,
                    "assets": [{"name": name, "state": "uploaded", "size": 25,
                                "digest": "sha256:" + "a" * 64}]}
        releases = [release("v0.14.2"), release("v0.14.3", draft=True),
                    release("v0.15.0", name="RetroRecomp-v0.15.0-windows-x64.zip")]
        update = select_update(releases, current="0.14.1")
        self.assertEqual(update.version, "0.14.2")
        self.assertTrue(update.url.endswith("/Retro-Recomp.exe"))
        self.assertIsNone(select_update(releases, current="0.14.2"))

    def test_verified_update_stages_only_executable_beside_converter(self):
        job_dir, token = self._prepare()
        self.assertEqual((job_dir / "files/Retro-Recomp.exe").read_bytes(), b"MZnew converter")
        self.assertEqual((job_dir / "updater-helper.exe").read_bytes(), b"MZold converter")
        self.assertEqual(json.loads((job_dir / "job.json").read_text())["token"], token)
        self.assertEqual(self.exe.read_bytes(), b"MZold converter")
        self.assertEqual(set(path.name for path in (job_dir / "files").iterdir()),
                         {"Retro-Recomp.exe"})
        discard_update(job_dir, self.exe)
        self.assertFalse(job_dir.exists())

    def test_bad_download_or_non_exe_leaves_old_converter_untouched(self):
        data = b"MZnew converter"
        update = Update("0.14.2", "https://github.com/example/Retro-Recomp.exe", "page",
                        "0" * 64, len(data))
        with patch("smsrecomp.updater.urllib.request.urlopen", return_value=io.BytesIO(data)):
            with self.assertRaisesRegex(ValueError, "checksum"):
                prepare_update(update, self.exe)
        with self.assertRaisesRegex(ValueError, "Windows executable"):
            self._prepare(b"invalid")
        self.assertEqual(list(self.root.iterdir()), [self.exe])

    def test_install_failure_restores_old_converter(self):
        job_dir, _ = self._prepare()
        files = json.loads((job_dir / "job.json").read_text())["files"]
        real_replace = __import__("os").replace

        def fail_exe(source, target):
            if source == job_dir / "files/Retro-Recomp.exe":
                raise OSError("installation interrupted")
            return real_replace(source, target)

        with patch("smsrecomp.updater.os.replace", side_effect=fail_exe):
            with self.assertRaisesRegex(OSError, "installation interrupted"):
                _install_files(job_dir, self.exe, files)
        self.assertEqual(self.exe.read_bytes(), b"MZold converter")

    def test_successful_install_preserves_games_and_settings(self):
        game = self.root / "Games/Master System/Example.exe"
        game.parent.mkdir(parents=True)
        game.write_bytes(b"saved game")
        settings = self.root / "datas/Retro-Recomp.json"
        settings.parent.mkdir()
        settings.write_bytes(b"saved settings")
        job_dir, _ = self._prepare()
        files = json.loads((job_dir / "job.json").read_text())["files"]
        _install_files(job_dir, self.exe, files)
        self.assertEqual(self.exe.read_bytes(), b"MZnew converter")
        self.assertEqual((job_dir / "backup/Retro-Recomp.exe").read_bytes(), b"MZold converter")
        self.assertEqual(game.read_bytes(), b"saved game")
        self.assertEqual(settings.read_bytes(), b"saved settings")

    def test_restart_failure_rolls_back_to_old_converter(self):
        job_dir, token = self._prepare()
        with patch("smsrecomp.updater._wait_for_process"), \
             patch("smsrecomp.updater.subprocess.Popen", side_effect=OSError("restart failed")):
            self.assertEqual(apply_update(job_dir, token), 1)
        self.assertEqual(self.exe.read_bytes(), b"MZold converter")
        self.assertIn("restart failed", (job_dir / "job.json").read_text())

    def test_detached_helper_restarts_and_new_app_cleans_stage(self):
        job_dir, token = self._prepare()
        with patch("smsrecomp.updater._wait_for_process") as wait, \
             patch("smsrecomp.updater.subprocess.Popen") as restart:
            self.assertEqual(apply_update(job_dir, token), 0)
            self.assertEqual(self.exe.read_bytes(), b"MZnew converter")
            self.assertEqual(restart.call_args.args[0][1:3],
                             ["_finish-update", str(job_dir)])
            self.assertIsNone(finish_update(job_dir, token, 12345))
            self.assertEqual(wait.call_count, 2)
        self.assertFalse(job_dir.exists())


if __name__ == "__main__":
    unittest.main()
