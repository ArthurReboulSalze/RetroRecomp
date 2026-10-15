"""Cover settings commit atomically without persisting plaintext credentials."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from smsrecomp import cover_settings as settings
from smsrecomp.cover_keyring import KeyringError


class CoverKeyringTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = {}
        for name, function in (
            ('read', lambda key: self.store[key]),
            ('write', lambda key, raw: self.store.__setitem__(key, raw)),
            ('remove', lambda key: self.store.pop(key, None)),
        ):
            context = patch.object(settings.cover_keyring, name, side_effect=function)
            context.start(); self.addCleanup(context.stop)
        # Patch just the module's OS view; do not change pathlib's host platform.
        context = patch.object(settings, 'os', wraps=settings.os)
        self.os = context.start(); self.os.name = 'posix'
        self.addCleanup(context.stop)
        self.value = settings.defaults()
        self.value['accounts']['igdb']['client_secret'] = 'synthetic-secret'

    def test_roundtrip_replacement_and_explicit_removal(self):
        settings.save_settings(self.value, self.root)
        first = next(iter(self.store))
        self.assertNotIn('synthetic-secret', (self.root/settings.CONFIG_NAME).read_text())
        self.assertEqual(settings.load_settings(self.root)['accounts'], self.value['accounts'])
        settings.save_settings(self.value, self.root)
        self.assertNotIn(first, self.store)
        self.assertEqual(len(self.store), 1)
        settings.save_settings(settings.defaults(), self.root)
        self.assertFalse(self.store)

    def test_locked_wallet_preserves_accounts_when_only_style_changes(self):
        settings.save_settings(self.value, self.root)
        identity = next(iter(self.store))
        with patch.object(settings.cover_keyring, 'read', side_effect=KeyringError('locked')):
            value = settings.load_settings(self.root)
            self.assertTrue(value['credential_error'])
            value['box_3d'] = True
            settings.save_settings(value, self.root)
        self.assertEqual(set(self.store), {identity})
        restored = settings.load_settings(self.root)
        self.assertTrue(restored['box_3d'])
        self.assertEqual(restored['accounts'], self.value['accounts'])

    def test_failed_settings_commit_preserves_previous_secret_and_file(self):
        settings.save_settings(self.value, self.root)
        before = (self.root/settings.CONFIG_NAME).read_bytes()
        identities = set(self.store)
        with patch.object(settings, '_save_record', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                settings.save_settings(self.value, self.root)
        self.assertEqual((self.root/settings.CONFIG_NAME).read_bytes(), before)
        self.assertEqual(set(self.store), identities)

    def test_unavailable_service_creates_no_plaintext_file(self):
        with patch.object(settings.cover_keyring, 'write', side_effect=KeyringError('unavailable')):
            with self.assertRaises(KeyringError):
                settings.save_settings(self.value, self.root)
        self.assertFalse((self.root/settings.CONFIG_NAME).exists())
