import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from smsrecomp.updater import (Update, _install_files, _unpack, apply_update,
                               discard_update, finish_update, prepare_update, select_update)


def release_zip(extra=None):
    contents = {"RetroRecomp/Retro-Recomp.exe": b"MZnew converter",
                "RetroRecomp/LICENSE": b"new license",
                "RetroRecomp/THIRD_PARTY_NOTICES.md": b"new notices",
                "RetroRecomp/licenses/example.md": b"new dependency notice"}
    contents.update(extra or {})
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, data in contents.items():
            archive.writestr(name, data)
    return output.getvalue()


class UpdaterTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.exe = self.root / "Retro-Recomp.exe"
        self.exe.write_bytes(b"MZold converter")

    def _prepare(self, data=None):
        data = release_zip() if data is None else data
        update = Update("0.14.1", "https://github.com/example/release.zip",
                        "https://github.com/example/tag", hashlib.sha256(data).hexdigest(), len(data))
        with patch("smsrecomp.updater.urllib.request.urlopen", return_value=io.BytesIO(data)):
            return prepare_update(update, self.exe)

    def test_selects_newest_compatible_prerelease_and_ignores_drafts(self):
        def release(version, *, draft=False, name=None):
            return {"tag_name": version, "draft": draft, "prerelease": True,
                    "assets": [{"name": name or f"RetroRecomp-{version}-windows-x64.zip",
                                "state": "uploaded", "size": 25,
                                "digest": "sha256:" + "a" * 64}]}
        releases = [release("v0.13.0"), release("v0.14.2", draft=True),
                    release("v0.14.1"), release("v0.15.0", name="source.zip")]
        self.assertEqual(select_update(releases, current="0.13.0").version, "0.14.1")
        self.assertIsNone(select_update(releases, current="0.14.1"))

    def test_verified_update_stages_only_release_files_beside_converter(self):
        job_dir, token = self._prepare()
        self.assertEqual((job_dir / "files/Retro-Recomp.exe").read_bytes(), b"MZnew converter")
        self.assertEqual((job_dir / "files/licenses/example.md").read_bytes(), b"new dependency notice")
        self.assertEqual((job_dir / "updater-helper.exe").read_bytes(), b"MZold converter")
        self.assertEqual(json.loads((job_dir / "job.json").read_text())["token"], token)
        self.assertEqual(self.exe.read_bytes(), b"MZold converter")
        self.assertFalse((self.root / "Games").exists())
        self.assertFalse((self.root / "datas").exists())
        discard_update(job_dir, self.exe)
        self.assertFalse(job_dir.exists())

    def test_bad_download_or_unsafe_archive_leaves_old_converter_untouched(self):
        data = release_zip()
        update = Update("0.14.1", "https://github.com/example/release.zip", "page",
                        "0" * 64, len(data))
        with patch("smsrecomp.updater.urllib.request.urlopen", return_value=io.BytesIO(data)):
            with self.assertRaisesRegex(ValueError, "checksum"):
                prepare_update(update, self.exe)
        self.assertEqual(list(self.root.iterdir()), [self.exe])
        unsafe = release_zip({"RetroRecomp/../Games/unwanted.exe": b"bad"})
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            self._prepare(unsafe)
        self.assertEqual(self.exe.read_bytes(), b"MZold converter")
        self.assertFalse((self.root / "Games").exists())

    def test_install_failure_restores_exe_and_notices(self):
        job_dir, _ = self._prepare()
        notices = self.root / "THIRD_PARTY_NOTICES.md"
        notices.write_bytes(b"old notices")
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
        self.assertEqual(notices.read_bytes(), b"old notices")
        self.assertFalse((self.root / "licenses/example.md").exists())

    def test_successful_install_replaces_only_converter_and_legal_files(self):
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
        self.assertEqual((self.root / "THIRD_PARTY_NOTICES.md").read_bytes(), b"new notices")
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
