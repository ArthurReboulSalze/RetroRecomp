"""A software update also installs the base copy of the same release.

The release carries `Retro-Recomp-base.zip` beside the executable; the update
checks it like the executable (size, SHA-256), places it beside the converter
under the same name and rolls it back with the executable if anything fails.
A release without that asset updates the executable alone, as before.
"""
from dataclasses import replace
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from retrorecomp.updater import (BASE_ASSET, Update, _install_files, apply_update, finish_update,
                                 prepare_update, select_update)


def base_zip(label=b'new'):
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, 'w') as archive:
        archive.writestr('manifest.json', json.dumps({'format': 2, 'version': 414}))
        archive.writestr('index.json', b'{}')
        archive.writestr('entries/' + label.decode() + '.json', b'{}')
    return payload.getvalue()


def asset(name, data, **fields):
    return {'name': name, 'state': 'uploaded', 'size': len(data),
            'digest': 'sha256:' + hashlib.sha256(data).hexdigest(), **fields}


class BaseAssetTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.exe = self.root / 'Retro-Recomp.exe'
        self.exe.write_bytes(b'MZold converter')
        self.executable_data = b'MZnew converter'
        self.base_data = base_zip()

    def update(self, with_base=True):
        return Update('1.5.5', 'https://example.test/Retro-Recomp.exe', 'https://example.test/tag',
                      hashlib.sha256(self.executable_data).hexdigest(), len(self.executable_data), 'windows-x86_64', '',
                      'https://example.test/' + BASE_ASSET if with_base else '',
                      hashlib.sha256(self.base_data).hexdigest() if with_base else '',
                      len(self.base_data) if with_base else 0)

    def served(self, base=None):
        downloads = []
        def respond(request, *args, **kwargs):
            url = request.full_url
            downloads.append(url)
            data = (base if base is not None else self.base_data) if url.endswith(BASE_ASSET) else self.executable_data
            response = io.BytesIO(data)
            response.headers = {}
            return response
        return patch('retrorecomp.updater.urllib.request.urlopen', side_effect=respond), downloads

    def prepare(self, update=None, base=None):
        opener, downloads = self.served(base)
        with opener:
            result = prepare_update(update or self.update(), self.exe)
        return result, downloads

    # --- choosing the release -------------------------------------------

    def release(self, version, with_base=True, base_name=BASE_ASSET):
        assets = [asset('Retro-Recomp.exe', self.executable_data)]
        if with_base:
            assets.append(asset(base_name, self.base_data))
        return {'tag_name': version, 'draft': False, 'assets': assets}

    def test_the_base_asset_of_the_chosen_release_is_offered_with_its_own_digest(self):
        update = select_update([self.release('v1.5.5')], current='1.5.4', target='windows-x86_64')
        self.assertEqual(update.base_url, 'https://github.com/ArthurReboulSalze/RetroRecomp/releases/download/v1.5.5/'
                                          + BASE_ASSET)
        self.assertEqual((update.base_digest, update.base_size),
                         (hashlib.sha256(self.base_data).hexdigest(), len(self.base_data)))

    def test_a_release_without_the_asset_updates_as_before(self):
        for releases in ([self.release('v1.5.5', with_base=False)],
                         [self.release('v1.5.5', base_name='base.zip')]):
            update = select_update(releases, current='1.5.4', target='windows-x86_64')
            self.assertEqual((update.version, update.base_url, update.base_digest, update.base_size),
                             ('1.5.5', '', '', 0))

    def test_the_base_comes_from_the_offered_release_not_from_an_older_one(self):
        releases = [self.release('v1.5.5', with_base=False), self.release('v1.5.6', with_base=False),
                    self.release('v1.5.7')]
        releases[2]['draft'] = True
        update = select_update(releases, current='1.5.4', target='windows-x86_64')
        self.assertEqual((update.version, update.base_url), ('1.5.6', ''))

    def test_a_base_asset_with_a_bad_digest_or_size_is_not_offered(self):
        for broken in ({'digest': 'sha256:xyz'}, {'digest': None}, {'size': 0}, {'size': 600 * 1024 * 1024},
                       {'state': 'starter'}):
            release = self.release('v1.5.5')
            release['assets'][1].update(broken)
            update = select_update([release], current='1.5.4', target='windows-x86_64')
            self.assertEqual(update.base_url, '', broken)

    # --- staging ----------------------------------------------------------

    def test_both_files_are_downloaded_checked_and_staged_read_only(self):
        (job_dir, _), downloads = self.prepare()
        self.assertEqual(downloads, ['https://example.test/Retro-Recomp.exe', 'https://example.test/' + BASE_ASSET])
        self.assertEqual((job_dir / 'files' / BASE_ASSET).read_bytes(), self.base_data)
        self.assertFalse(os.access(job_dir / 'files' / BASE_ASSET, os.W_OK))
        files = json.loads((job_dir / 'job.json').read_text())['files']
        self.assertEqual(files, {'Retro-Recomp.exe': hashlib.sha256(self.executable_data).hexdigest(),
                                 BASE_ASSET: hashlib.sha256(self.base_data).hexdigest()})
        self.assertEqual(self.exe.read_bytes(), b'MZold converter')
        self.assertEqual(sorted(path.name for path in self.root.iterdir() if path != job_dir), ['Retro-Recomp.exe'])

    def test_a_release_without_the_asset_stages_the_executable_alone(self):
        (job_dir, _), downloads = self.prepare(self.update(with_base=False))
        self.assertEqual(downloads, ['https://example.test/Retro-Recomp.exe'])
        self.assertEqual(set(json.loads((job_dir / 'job.json').read_text())['files']), {'Retro-Recomp.exe'})
        self.assertEqual([path.name for path in (job_dir / 'files').iterdir()], ['Retro-Recomp.exe'])

    def test_a_base_with_a_wrong_checksum_or_that_is_not_a_zip_stops_everything(self):
        wrong = replace(self.update(), base_digest='f' * 64)
        with self.assertRaisesRegex(ValueError, 'base checksum'):
            self.prepare(wrong)
        self.base_data = b'not an archive at all'
        with self.assertRaisesRegex(ValueError, 'base archive'):
            self.prepare()
        # The executable was already staged: all of it is removed again.
        self.assertEqual(list(self.root.iterdir()), [self.exe])
        self.assertEqual(self.exe.read_bytes(), b'MZold converter')

    # --- installing -------------------------------------------------------

    def staged(self):
        (job_dir, token), _ = self.prepare()
        return job_dir, token, json.loads((job_dir / 'job.json').read_text())['files']

    def test_the_new_base_replaces_the_old_one_beside_the_executable(self):
        old = self.root / BASE_ASSET
        old.write_bytes(base_zip(b'old'))
        old.chmod(stat.S_IREAD)          # the installer's copy is read only
        job_dir, _, files = self.staged()
        _install_files(job_dir, self.exe, files)
        self.assertEqual(self.exe.read_bytes(), b'MZnew converter')
        self.assertEqual(old.read_bytes(), self.base_data)
        self.assertEqual((job_dir / 'backup' / BASE_ASSET).read_bytes(), base_zip(b'old'))

    def test_a_missing_old_base_is_simply_added(self):
        job_dir, _, files = self.staged()
        _install_files(job_dir, self.exe, files)
        self.assertEqual((self.root / BASE_ASSET).read_bytes(), self.base_data)

    def test_a_failure_puts_back_the_executable_and_the_old_base(self):
        old_data = base_zip(b'old')
        old = self.root / BASE_ASSET
        old.write_bytes(old_data)
        job_dir, _, files = self.staged()
        real = os.replace
        def fail_executable(source, target):
            if Path(source) == job_dir / 'files/Retro-Recomp.exe':
                raise OSError('installation interrupted')
            return real(source, target)
        with patch('retrorecomp.updater.os.replace', side_effect=fail_executable), \
                self.assertRaisesRegex(OSError, 'interrupted'):
            _install_files(job_dir, self.exe, files)
        self.assertEqual(self.exe.read_bytes(), b'MZold converter')
        self.assertEqual(old.read_bytes(), old_data)

    def test_a_failure_removes_a_base_that_was_not_there_before(self):
        job_dir, _, files = self.staged()
        real = os.replace
        def fail_executable(source, target):
            if Path(source) == job_dir / 'files/Retro-Recomp.exe':
                raise OSError('installation interrupted')
            return real(source, target)
        with patch('retrorecomp.updater.os.replace', side_effect=fail_executable), \
                self.assertRaisesRegex(OSError, 'interrupted'):
            _install_files(job_dir, self.exe, files)
        self.assertFalse((self.root / BASE_ASSET).exists())
        self.assertEqual(self.exe.read_bytes(), b'MZold converter')

    def test_a_failed_restart_rolls_back_both_files(self):
        old_data = base_zip(b'old')
        (self.root / BASE_ASSET).write_bytes(old_data)
        (job_dir, token), _ = self.prepare()
        with patch('retrorecomp.updater._wait_for_process'), \
                patch('retrorecomp.updater.subprocess.Popen', side_effect=OSError('restart failed')):
            self.assertEqual(apply_update(job_dir, token), 1)
        self.assertEqual(self.exe.read_bytes(), b'MZold converter')
        self.assertEqual((self.root / BASE_ASSET).read_bytes(), old_data)

    def test_the_restarted_app_cleans_up_even_with_a_read_only_backup(self):
        old = self.root / BASE_ASSET
        old.write_bytes(base_zip(b'old'))
        old.chmod(stat.S_IREAD)
        (job_dir, token), _ = self.prepare()
        with patch('retrorecomp.updater._wait_for_process'), patch('retrorecomp.updater.subprocess.Popen'):
            self.assertEqual(apply_update(job_dir, token), 0)
            self.assertIsNone(finish_update(job_dir, token, 1))
        self.assertFalse(job_dir.exists())
        self.assertEqual(old.read_bytes(), self.base_data)

    def test_only_the_executable_and_its_base_may_be_installed(self):
        job_dir, _, files = self.staged()
        (job_dir / 'files/other.dll').write_bytes(b'x')
        with self.assertRaisesRegex(ValueError, 'manifest'):
            _install_files(job_dir, self.exe, {**files, 'other.dll': hashlib.sha256(b'x').hexdigest()})
        with self.assertRaisesRegex(ValueError, 'manifest'):
            _install_files(job_dir, self.exe, {BASE_ASSET: files[BASE_ASSET]})
        self.assertEqual(self.exe.read_bytes(), b'MZold converter')


if __name__ == '__main__':
    unittest.main()
