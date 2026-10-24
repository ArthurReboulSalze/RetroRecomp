"""The converter updater downloads and replaces one verified executable."""
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import os
import subprocess
import sys

from retrorecomp.gui import update_error_text
from retrorecomp.updater import (Update, UpdateConnectionError, UpdateServiceError,
                               _install_files, apply_update, check_for_update,
                               discard_update, finish_update, prepare_update, select_update)
from retrorecomp.updater import _wait_for_process


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
        with patch("retrorecomp.updater.urllib.request.urlopen", return_value=io.BytesIO(data)):
            return prepare_update(update, self.exe)

    def test_selects_newest_executable_and_ignores_drafts_and_zips(self):
        def release(version, name="Retro-Recomp.exe", draft=False):
            return {"tag_name": version, "draft": draft, "prerelease": True,
                    "assets": [{"name": name, "state": "uploaded", "size": 25,
                                "digest": "sha256:" + "a" * 64}]}
        releases = [release("v0.14.2"), release("v0.14.3", draft=True),
                    release("v0.15.0", name="RetroRecomp-v0.15.0-windows-x64.zip")]
        update = select_update(releases, current="0.14.1", target='windows-x86_64')
        self.assertEqual(update.version, "0.14.2")
        self.assertTrue(update.url.endswith("/Retro-Recomp.exe"))
        self.assertIsNone(select_update(releases, current="0.14.2", target='windows-x86_64'))

    def test_firewall_block_uses_a_plain_localized_message(self):
        raw = urllib.error.URLError(PermissionError(13, "raw access denied 10013"))
        with patch("retrorecomp.updater.urllib.request.urlopen", side_effect=raw):
            with self.assertRaises(UpdateConnectionError) as caught:
                check_for_update()
        self.assertIs(caught.exception.__cause__, raw)
        english = update_error_text(caught.exception, "en")
        french = update_error_text(caught.exception, "fr")
        self.assertIn("internet connection or firewall", english)
        self.assertIn("connexion Internet ou ton pare-feu", french)
        self.assertNotIn("10013", english + french)

        update = Update("0.14.3", "https://github.com/example/Retro-Recomp.exe",
                        "page", "0" * 64, 123)
        with patch("retrorecomp.updater.urllib.request.urlopen", side_effect=raw):
            with self.assertRaises(UpdateConnectionError):
                prepare_update(update, self.exe)
        self.assertEqual(list(self.root.iterdir()), [self.exe])

    def test_http_service_error_is_not_reported_as_a_firewall_block(self):
        raw = urllib.error.HTTPError("https://github.com/example", 503,
                                     "Service Unavailable", {}, None)
        self.addCleanup(raw.close)
        with patch("retrorecomp.updater.urllib.request.urlopen", side_effect=raw):
            with self.assertRaises(UpdateServiceError) as caught:
                check_for_update()
        english = update_error_text(caught.exception, "en")
        self.assertIn("try again later", english)
        self.assertNotIn("firewall", english)

    def test_connection_failure_while_reading_response_is_friendly(self):
        class BlockedResponse(io.BytesIO):
            def read(self, _size=-1):
                raise PermissionError(13, "raw read access denied")

        with patch("retrorecomp.updater.urllib.request.urlopen", return_value=BlockedResponse()):
            with self.assertRaises(UpdateConnectionError) as caught:
                check_for_update()
        self.assertNotIn("raw read", update_error_text(caught.exception, "en"))

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
        with patch("retrorecomp.updater.urllib.request.urlopen", return_value=io.BytesIO(data)):
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

        with patch("retrorecomp.updater.os.replace", side_effect=fail_exe):
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
        with patch("retrorecomp.updater._wait_for_process"), \
             patch("retrorecomp.updater.subprocess.Popen", side_effect=OSError("restart failed")):
            self.assertEqual(apply_update(job_dir, token), 1)
        self.assertEqual(self.exe.read_bytes(), b"MZold converter")
        self.assertIn("restart failed", (job_dir / "job.json").read_text())

    def test_detached_helper_restarts_and_new_app_cleans_stage(self):
        job_dir, token = self._prepare()
        with patch("retrorecomp.updater._wait_for_process") as wait, \
             patch("retrorecomp.updater.subprocess.Popen") as restart:
            self.assertEqual(apply_update(job_dir, token), 0)
            self.assertEqual(self.exe.read_bytes(), b"MZnew converter")
            self.assertEqual(restart.call_args.args[0][1:3],
                             ["_finish-update", str(job_dir)])
            self.assertIsNone(finish_update(job_dir, token, 12345))
            self.assertEqual(wait.call_count, 2)
        self.assertFalse(job_dir.exists())


class LinuxUpdaterTests(unittest.TestCase):
    @staticmethod
    def elf(machine=62):
        return b'\x7fELF\x02\x01\x01'+bytes(9)+b'\x03\x00'+machine.to_bytes(2,'little')+b'authored converter'

    def test_selection_keeps_platforms_separate(self):
        def asset(name):
            return dict(name=name,state='uploaded',size=100,digest='sha256:'+'a'*64)
        releases=[dict(tag_name='v1.1.0', assets=[asset('Retro-Recomp.exe'),
                  asset('Retro-Recomp-linux-x86_64'),asset('Retro-Recomp-linux.tar.gz')]),
                  dict(tag_name='v1.2.0',assets=[asset('Retro-Recomp.exe')])]
        linux=select_update(releases,current='1.0.3',target='linux-x86_64')
        self.assertEqual(linux.version,'1.1.0')
        self.assertEqual(linux.target,'linux-x86_64')
        self.assertTrue(linux.url.endswith('/Retro-Recomp-linux-x86_64'))
        self.assertEqual(select_update(releases,current='1.0.3',target='windows-x86_64').version,'1.2.0')
        self.assertIsNone(select_update(releases,current='1.1.0',target='linux-x86_64'))

    def test_linux_elf_install_permissions_and_untouched_user_data(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); exe=root/'Retro-Recomp'
            exe.write_bytes(self.elf()+b'old');exe.chmod(0o755)
            saved=root/'datas';saved.mkdir();(saved/'cover-sources.json').write_text('private reference')
            raw=self.elf()
            update=Update('1.1.0','https://example.test/update','page',hashlib.sha256(raw).hexdigest(),len(raw),'linux-x86_64')
            with patch('retrorecomp.updater.urllib.request.urlopen',return_value=io.BytesIO(raw)):
                job,token=prepare_update(update,exe)
            self.assertTrue((job/'updater-helper').exists())
            if os.name!='nt':self.assertTrue((job/'files/Retro-Recomp').stat().st_mode & 0o100)
            with patch('retrorecomp.updater._wait_for_process'),patch('retrorecomp.updater.subprocess.Popen'):
                self.assertEqual(apply_update(job,token),0)
                self.assertIsNone(finish_update(job,token,12345))
            self.assertEqual(exe.read_bytes(),raw)
            self.assertFalse(job.exists())
            self.assertEqual((saved/'cover-sources.json').read_text(),'private reference')
            if os.name!='nt':self.assertTrue(exe.stat().st_mode & 0o100)

    def test_wrong_elf_architecture_does_not_replace_converter(self):
        with tempfile.TemporaryDirectory() as temp:
            exe=Path(temp)/'Retro-Recomp';exe.write_bytes(self.elf())
            raw=self.elf(machine=183)
            update=Update('1.1.0','https://example.test/update','page',hashlib.sha256(raw).hexdigest(),len(raw),'linux-x86_64')
            with patch('retrorecomp.updater.urllib.request.urlopen',return_value=io.BytesIO(raw)):
                with self.assertRaisesRegex(ValueError,'Linux x86-64'):
                    prepare_update(update,exe)
            self.assertEqual(list(Path(temp).iterdir()),[exe])
            self.assertEqual(exe.read_bytes(),self.elf())

    @unittest.skipUnless(sys.platform=='linux','Linux pidfd process wait')
    def test_helper_waits_for_parent_exit(self):
        process=subprocess.Popen([sys.executable,'-c','import time; time.sleep(.4)'])
        try:
            with self.assertRaises(TimeoutError):_wait_for_process(process.pid,timeout_ms=10)
            _wait_for_process(process.pid,timeout_ms=5000)
            self.assertEqual(process.wait(timeout=1),0)
            _wait_for_process(process.pid,timeout_ms=10)
        finally:
            if process.poll() is None:process.kill()
            process.wait()


if __name__ == "__main__":
    unittest.main()
