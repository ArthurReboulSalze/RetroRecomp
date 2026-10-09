"""Reference links and cache behavior use authored images and cartridge data."""
from copy import deepcopy
import hashlib
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from smsrecomp.artwork import ArtworkError, resolve_cover
from smsrecomp.cover_references import find, load, validate_payload
from tools.prepare_publication import check_public_file


def payload():
    return {'format': 1, 'entries': [{
        'id': 'sms-authored-game', 'system_id': 'sms',
        'rom_sha256': [hashlib.sha256(b'authored cartridge fixture').hexdigest()],
        'rom_names': ['Authored Game (Europe)'], 'style': 'front',
        'image_urls': ['https://example.test/authored-front.png'],
        'source_page': 'https://example.test/authored-game',
    }]}


def png(color):
    out = BytesIO()
    Image.new('RGBA', (32, 48), color).save(out, format='PNG')
    return out.getvalue()


class CoverReferenceTests(unittest.TestCase):
    def test_schema_and_publication_reject_embedded_data_and_private_references(self):
        value = payload()
        self.assertEqual(validate_payload(value), value)
        check_public_file('assets/cover-references.json', json.dumps(value).encode())
        for key, bad in [('image', 'embedded bitmap'), ('rom_bytes', 'embedded cartridge'),
                         ('image_urls', ['https://example.test/image?api_key=private']),
                         ('image_urls', ['https://user:private@example.test/image.png']),
                         ('image_urls', ['https://192.168.0.5/image.png']),
                         ('image_urls', ['file:///local/image.png']),
                         ('rom_names', ['X:/' + 'Users/synthetic/cover']),
                         ('system_id', [])]:
            with self.subTest(key=key, bad=bad):
                unsafe = deepcopy(value)
                unsafe['entries'][0][key] = bad
                with self.assertRaises(ValueError):
                    check_public_file('assets/cover-references.json', json.dumps(unsafe).encode())

    def test_exact_identity_names_console_style_and_ambiguity(self):
        value = payload()
        digest = value['entries'][0]['rom_sha256'][0]
        with patch('smsrecomp.cover_references.load', return_value=value):
            self.assertEqual(find('sms', digest, 'renamed')['id'], 'sms-authored-game')
            self.assertIsNotNone(find('sms', None, 'Authored Game (Europe)'))
            for system, name, box3d in [('sms', 'Authored Game II (Europe)', False),
                                       ('sms', 'Authored Game (USA)', False),
                                       ('gb', 'Authored Game (Europe)', False),
                                       ('sms', 'Authored Game (Europe)', True)]:
                self.assertIsNone(find(system, None, name, prefer3d=box3d))
            other = deepcopy(value['entries'][0]); other['id'] = 'sms-another-reference'
            value['entries'].append(other)
            self.assertIsNone(find('sms', digest, 'renamed'))

    def test_invalid_or_missing_catalogue_has_no_side_effects(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            path = directory / 'absent.json'
            self.assertEqual(load(path), {'format': 1, 'entries': []})
            self.assertFalse(path.exists())
            path.write_bytes(b'{"format":1,"entries":[],"image":"not allowed"}')
            self.assertEqual(load(path)['entries'], [])

    def test_reviewed_link_replaces_wrong_saved_cover_and_survives_rename(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); rom = root / 'Authored Game (Europe).sms'
            rom.write_bytes(b'authored cartridge fixture')
            cache = root / 'cache'
            with patch('smsrecomp.cover_references.load', return_value={'format': 1, 'entries': []}), \
                 patch('smsrecomp.artwork._get', return_value=png('orange')):
                wrong = resolve_cover(rom, 'Authored Game', cache, emit=lambda text: None)
            with patch('smsrecomp.cover_references.load', return_value=payload()), \
                 patch('smsrecomp.artwork._get', return_value=png('blue')) as network:
                reviewed = resolve_cover(rom, 'Authored Game', cache, emit=lambda text: None)
            self.assertEqual(reviewed['source'], 'reference')
            self.assertNotEqual(wrong['data'], reviewed['data'])
            self.assertEqual(network.call_count, 1)
            renamed = root / 'Renamed.sms'; renamed.write_bytes(rom.read_bytes())
            with patch('smsrecomp.cover_references.load', return_value=payload()), \
                 patch('smsrecomp.artwork._get', side_effect=AssertionError('cache must avoid network')):
                reused = resolve_cover(renamed, 'Renamed', cache, emit=lambda text: None)
                self.assertEqual(reused['data'], reviewed['data'])
                self.assertEqual(reused['source'], 'reference_cache')
                # A different ROM revision with the same exact name shares the reference cache.
                rom.write_bytes(b'authored alternate revision')
                self.assertEqual(resolve_cover(rom, 'Authored Game', cache,
                    emit=lambda text: None)['data'], reviewed['data'])

    def test_reference_change_refreshes_and_manual_selection_keeps_priority(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); rom = root / 'Authored Game (Europe).sms'
            rom.write_bytes(b'authored cartridge fixture'); cache = root / 'cache'
            with patch('smsrecomp.cover_references.load', return_value=payload()), \
                 patch('smsrecomp.artwork._get', return_value=png('blue')):
                first = resolve_cover(rom, 'Authored Game', cache, emit=lambda text: None)
            update = payload(); update['entries'][0]['image_urls'] = ['https://example.test/corrected.png']
            with patch('smsrecomp.cover_references.load', return_value=update), \
                 patch('smsrecomp.artwork._get', return_value=png('green')) as network:
                second = resolve_cover(rom, 'Authored Game', cache, emit=lambda text: None)
            self.assertEqual(network.call_count, 1)
            self.assertNotEqual(first['reference_revision'], second['reference_revision'])
            manual = root / 'explicit.png'; manual.write_bytes(png('red'))
            with patch('smsrecomp.artwork._get', side_effect=AssertionError('explicit is offline')):
                self.assertEqual(resolve_cover(rom, 'Authored Game', cache, explicit=manual)['source'], 'explicit')

    def test_offline_reference_does_not_create_a_cache_or_contact_the_network(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); cache = root / 'absent'; rom = root / 'Authored Game (Europe).sms'
            rom.write_bytes(b'authored cartridge fixture')
            with patch('smsrecomp.cover_references.load', return_value=payload()), \
                 patch('smsrecomp.artwork._get', side_effect=AssertionError('offline')):
                with self.assertRaises(ArtworkError):
                    resolve_cover(rom, 'Authored Game', cache, online=False)
            self.assertFalse(cache.exists())


if __name__ == '__main__':
    unittest.main()
