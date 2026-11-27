import os
import ssl
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from retrorecomp import tls_roots


def layout(root: Path, *names):
    """A fake distribution: only the named bundle files exist, under root."""
    for name in names:
        target = root / name.lstrip('/')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('-----BEGIN CERTIFICATE-----\n', encoding='utf-8')
    return tuple(str(root / name.lstrip('/')) for name in tls_roots.BUNDLE_PATHS)


class FindBundleTests(unittest.TestCase):
    def check(self, family, present, expected):
        with tempfile.TemporaryDirectory() as folder:
            paths = layout(Path(folder), *present)
            found = tls_roots.find_bundle(paths)
            self.assertEqual(found, str(Path(folder) / expected.lstrip('/')), family)

    def test_each_distribution_family(self):
        self.check('debian', ['/etc/ssl/certs/ca-certificates.crt'], '/etc/ssl/certs/ca-certificates.crt')
        self.check('fedora and bazzite', ['/etc/pki/tls/certs/ca-bundle.crt',
                                          '/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem'],
                   '/etc/pki/tls/certs/ca-bundle.crt')
        self.check('fedora extracted only', ['/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem'],
                   '/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem')
        self.check('opensuse', ['/etc/ssl/ca-bundle.pem'], '/etc/ssl/ca-bundle.pem')
        self.check('alpine', ['/etc/ssl/cert.pem'], '/etc/ssl/cert.pem')

    def test_nothing_found_and_empty_files_ignored(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = layout(Path(folder))
            self.assertIsNone(tls_roots.find_bundle(paths))
            empty = Path(paths[0])
            empty.parent.mkdir(parents=True)
            empty.write_text('', encoding='utf-8')
            self.assertIsNone(tls_roots.find_bundle(paths))


class EnsureTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.paths = layout(Path(self.folder.name), '/etc/pki/tls/certs/ca-bundle.crt')

    def test_windows_is_never_touched(self):
        env = {}
        self.assertIsNone(tls_roots.ensure('win32', env, self.paths))
        self.assertEqual(env, {})

    def test_linux_without_default_store_uses_the_fedora_bundle(self):
        env = {}
        with mock.patch.object(tls_roots, '_default_store_works', return_value=False), \
                mock.patch.dict(tls_roots._state, {'done': False}):
            # A private environ: the default store is only consulted for the real one, so
            # exercise the real path through a patched os.environ.
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop('SSL_CERT_FILE', None)
                os.environ.pop('SSL_CERT_DIR', None)
                found = tls_roots.ensure('linux', None, self.paths)
                self.assertEqual(found, self.paths[1])
                self.assertEqual(os.environ['SSL_CERT_FILE'], self.paths[1])
        self.assertEqual(env, {})

    def test_the_players_own_setting_is_kept(self):
        mine = Path(self.folder.name) / 'mine.pem'
        mine.write_text('x', encoding='utf-8')
        env = {'SSL_CERT_FILE': str(mine)}
        self.assertIsNone(tls_roots.ensure('linux', env, self.paths))
        self.assertEqual(env['SSL_CERT_FILE'], str(mine))
        env = {'SSL_CERT_DIR': '/somewhere'}
        self.assertIsNone(tls_roots.ensure('linux', env, self.paths))
        self.assertNotIn('SSL_CERT_FILE', env)

    def test_a_working_default_store_is_kept(self):
        with mock.patch.object(tls_roots, '_default_store_works', return_value=True), \
                mock.patch.dict(tls_roots._state, {'done': False}), \
                mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop('SSL_CERT_FILE', None)
            os.environ.pop('SSL_CERT_DIR', None)
            self.assertIsNone(tls_roots.ensure('linux', None, self.paths))
            self.assertNotIn('SSL_CERT_FILE', os.environ)

    def test_a_stale_setting_is_replaced(self):
        env = {'SSL_CERT_FILE': '/nowhere/missing.pem'}
        self.assertEqual(tls_roots.ensure('linux', env, self.paths), self.paths[1])
        self.assertEqual(env['SSL_CERT_FILE'], self.paths[1])


class FailureNoteTests(unittest.TestCase):
    def test_verification_failure_is_recognised_through_wrappers(self):
        import urllib.error
        inner = ssl.SSLCertVerificationError(1, 'certificate verify failed')
        self.assertTrue(tls_roots.is_verification_failure(urllib.error.URLError(inner)))
        wrapped = RuntimeError('x')
        wrapped.__cause__ = urllib.error.URLError(inner)
        self.assertTrue(tls_roots.is_verification_failure(wrapped))
        self.assertFalse(tls_roots.is_verification_failure(ConnectionRefusedError()))
        self.assertFalse(tls_roots.is_verification_failure(None))

    def test_the_note_is_said_once_and_only_for_certificates(self):
        said = []
        with mock.patch.dict(tls_roots._state, {'warned': False}):
            self.assertFalse(tls_roots.note_failure(ConnectionRefusedError(), said.append))
            error = ssl.SSLCertVerificationError(1, 'bad')
            self.assertTrue(tls_roots.note_failure(error, said.append))
            self.assertFalse(tls_roots.note_failure(error, said.append))
        self.assertEqual(len(said), 1)
        self.assertIn('certificate', said[0])


if __name__ == '__main__':
    unittest.main()
