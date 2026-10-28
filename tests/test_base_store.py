"""The local base of paths: the installer's copy, updates by difference, the split.

One base outside the executable: the installer's copy beside the program is only
read; updates add a newer index and the entries the copy lacks. These tests use
a fake service that serves a format-2 manifest, difference archives and a
complete base at a direct address (tests/test_shared_base.py), and a temporary
application folder holding the installer's copy.
"""
import hashlib
import json
import os
import time
import unittest
import zipfile
from unittest.mock import patch

from retrorecomp import knowledge, knowledge_exchange, online
from tests.test_shared_base import (ENGINE, IDENTITY, KEY, OTHER_ENGINE, OTHER_KEY, BaseHarness, base_archive, entry,
                                    part, qualified)
from tests.test_shared_ng import GAME_KEY as NG_KEY, IDENTITY as NG_IDENTITY, ng_record
from tests.test_shared_sync import sms_record


def bank_record(system, identity):
    """The qualified bank's record for one game ({} when none)."""
    return knowledge_exchange.read_qualified_bank().get(system, {}).get(identity, {})


class StoreTests(BaseHarness):
    def entries_on_disk(self):
        folder = self.store / 'entries'
        return sorted(path.name for path in folder.iterdir()) if folder.exists() else []

    # --- The installer's copy ---------------------------------------------------

    def test_the_first_run_on_the_installer_copy_points_at_it_without_copying(self):
        built = entry(part(5, 'extended', (0x100,)), qualified=[qualified((0x300,), level='thorough')])
        self.install(4, {KEY: (built[0], [5])}, [built])
        with patch.dict(os.environ, {'RETRO_RECOMP_SERVICE': ''}):
            prepared = online.prepare_batch([KEY])
        base = prepared['base']
        self.assertEqual((base['version'], base['origin'], base['offline'], base['update'], base['games']),
                         (4, 'installer', False, None, 1))
        state = json.loads((self.store / 'state.json').read_text(encoding='utf-8'))
        self.assertEqual((state['version'], state['origin']), (4, 'installer'))
        self.assertFalse((self.store / 'index.json').exists(), 'the index is read from the copy')
        self.assertEqual(self.entries_on_disk(), [], 'and so are the entries')
        self.assertEqual(self.server.hits, [], 'no service, no request')
        self.assertEqual(bank_record('sms', IDENTITY)['rom_entries'], [[0x300, 0, 0, 0, 1]])
        self.assertEqual(knowledge.imported_record('sms', IDENTITY)['rom_entries'], [[0x100, 0, 0, 0, 1]])
        self.assertEqual(prepared['paths'], {KEY: {'level': 'thorough', 'records': 2}})
        # The copy is left as it was.
        self.assertEqual(self.installer.read_bytes(), base_archive(4, {KEY: (built[0], [5])}, {built[0]: built[1]}))

    def test_stored_and_deflated_archives_read_alike(self):
        built = entry(part(5, 'standard', (0x100,)))
        games = {KEY: (built[0], [5])}
        for compression in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            with self.subTest(compression):
                knowledge_exchange._installer_head.cache_clear()
                self.installer.parent.mkdir(parents=True, exist_ok=True)
                self.installer.write_bytes(base_archive(4, games, {built[0]: built[1]}, compression=compression))
                self.assertEqual(knowledge_exchange.local_base()['version'], 4)
                with knowledge_exchange.BaseEntries() as entries:
                    self.assertEqual(entries.text(built[0]), knowledge_exchange.canonical_bytes(built[1]))
        # A downloaded difference or complete base may be stored as well.
        self.publish(6, games, entries=[built])
        blob = base_archive(6, games, {built[0]: built[1]}, compression=zipfile.ZIP_STORED)
        self.server.base['downloads']['retro-recomp-base3-6.zip'] = blob
        self.server.base['manifest']['full'].update(sha256=hashlib.sha256(blob).hexdigest(), bytes=len(blob))
        self.installer.unlink()
        knowledge_exchange._installer_head.cache_clear()
        self.assertEqual(online.update_base()['version'], 6)

    def test_an_entry_is_looked_up_in_the_local_folder_before_the_copy(self):
        built = entry(part(5, 'standard', (0x100,)))
        self.install(4, {KEY: (built[0], [5])}, [built])
        (self.store / 'entries').mkdir(parents=True)
        (self.store / 'entries' / f'{built[0]}.json').write_bytes(b'from the folder')
        with knowledge_exchange.BaseEntries() as entries:
            self.assertEqual(entries.text(built[0]), b'from the folder')
            self.assertEqual(entries.text('0' * 64), None)
            self.assertIsNone(entries.text('../' + 'a' * 61), 'only hashes name entries')
        (self.store / 'entries' / f'{built[0]}.json').unlink()
        with knowledge_exchange.BaseEntries() as entries:
            self.assertEqual(entries.text(built[0]), knowledge_exchange.canonical_bytes(built[1]))

    def test_without_a_copy_or_a_connection_the_batch_is_discovered_in_full(self):
        self.stop_server()
        prepared = online.prepare_batch([KEY])
        base = prepared['base']
        self.assertEqual((base['version'], base['offline'], prepared['paths']), (None, True, {}))
        self.assertIsInstance(base['error'], online.ServiceConnectionError)
        # No service at all says the same; with the option off nothing is said.
        with patch.dict(os.environ, {'RETRO_RECOMP_SERVICE': ''}):
            self.assertTrue(online.prepare_batch([KEY])['base']['offline'])
            self.assertIsNone(online.prepare_batch([KEY], enabled=False)['base'])

    def test_a_copy_and_no_connection_say_the_local_base_is_used(self):
        built = entry(part(5, 'standard', (0x100,)))
        self.install(4, {KEY: (built[0], [5])}, [built])
        self.stop_server()
        base = online.prepare_batch([KEY])['base']
        self.assertEqual((base['version'], base['offline'], base['origin']), (4, True, 'installer'))
        self.assertEqual(base['update']['error'], 'offline')
        self.assertEqual(online.shared_paths([KEY]), {KEY: {'level': 'standard', 'records': 1}})

    def test_a_newer_copy_replaces_the_download_and_the_entries_nothing_names_are_removed(self):
        old = entry(part(1, 'standard', (0x100,)))
        self.publish(3, {KEY: (old[0], [1])}, entries=[old])
        online.update_base()
        self.assertEqual(self.entries_on_disk(), [f'{old[0]}.json'])
        # A program update lays a newer copy: it takes over, the download is dropped.
        newer = entry(part(1, 'standard', (0x100,)), part(2, 'standard', (0x200,)))
        self.install(5, {KEY: (newer[0], [1, 2])}, [newer])
        self.assertEqual((knowledge_exchange.local_base()['version'], knowledge_exchange.local_base()['origin']),
                         (5, 'installer'))
        base = knowledge_exchange.settle_local_base(self.url)
        self.assertEqual(base['origin'], 'installer')
        self.assertEqual(knowledge_exchange.read_base_state()['origin'], 'installer')
        self.assertEqual(self.entries_on_disk(), [])
        self.assertFalse((self.store / 'index.json').exists())
        # The download is newer than a stale copy: it stays.
        self.publish(9, {KEY: (newer[0], [1, 2])}, entries=[newer])
        online.update_base()
        self.assertEqual((knowledge_exchange.local_base()['version'], knowledge_exchange.local_base()['origin']),
                         (9, 'download'))

    def test_a_damaged_download_falls_back_on_the_copy(self):
        built = entry(part(1, 'standard', (0x100,)))
        self.install(2, {KEY: (built[0], [1])}, [built])
        newer = entry(part(1, 'standard', (0x100,)), part(2, 'standard', (0x200,)))
        self.publish(2, {KEY: (built[0], [1])}, entries=[built])
        self.publish(3, {KEY: (newer[0], [1, 2])}, entries=[newer])
        self.assertEqual(online.update_base()['version'], 3)
        (self.store / 'index.json').write_text('{}', encoding='utf-8')
        self.assertEqual(knowledge_exchange.local_base()['version'], 2)
        self.assertEqual(online.local_base_version(), 2)

    # --- Updates ----------------------------------------------------------------

    def test_a_difference_from_the_copys_version_carries_only_the_new_entries(self):
        first = entry(part(1, 'standard', (0x100,)))
        second = entry(part(2, 'standard', (0x200,)), identity='cd' * 32)
        games = {KEY: (first[0], [1])}
        self.publish(5, games, entries=[first])
        self.install(5, games, [first])
        grown = {**games, OTHER_KEY: (second[0], [2])}
        self.publish(6, grown, entries=[second])
        self.server.hits.clear()
        result = online.update_base()
        self.assertEqual({name: result[name] for name in ('version', 'previous', 'source', 'error')},
                         {'version': 6, 'previous': 5, 'source': 'delta', 'error': None})
        self.assertGreater(result['downloaded_bytes'], 0)
        self.assertEqual(self.gets(), ['base3', 'base3/files/retro-recomp-base3-5-6.zip'])
        self.assertEqual(self.entries_on_disk(), [f'{second[0]}.json'], 'what the copy lacks, nothing else')
        base = knowledge_exchange.local_base()
        self.assertEqual((base['version'], base['origin'], base['games']), (6, 'download', 2))
        with knowledge_exchange.BaseEntries() as entries:
            self.assertIsNotNone(entries.text(first[0]), 'still read from the copy')
        summary = online.sync_base([KEY, OTHER_KEY])
        self.assertEqual((summary['games'], summary['error'], summary['update']), (2, None, None))
        self.assertEqual(online.update_base()['source'], None, 'up to date: nothing is downloaded')

    def test_a_complete_base_then_the_difference_that_leads_on_from_it(self):
        one = entry(part(1, 'standard', (0x100,)))
        two = entry(part(1, 'standard', (0x100,)), part(2, 'standard', (0x200,)))
        three = entry(part(1, 'standard', (0x100,)), part(2, 'standard', (0x200,)), part(3, 'extended', (0x300,)))
        self.publish(1, {KEY: (one[0], [1])}, entries=[one], full=False)
        self.publish(2, {KEY: (two[0], [1, 2])}, entries=[two], full=False)
        # The latest complete base published is version 2, the current one is 3.
        self.publish(3, {KEY: (three[0], [1, 2, 3])}, entries=[three], cursor=77, full=2)
        self.server.hits.clear()
        seen = []
        result = online.update_base(progress=lambda stage, done, total: seen.append((stage, done, total)))
        self.assertEqual((result['version'], result['previous'], result['source'], result['error']),
                         (3, None, 'full', None))
        self.assertEqual(self.gets(), ['base3', 'dl/retro-recomp-base3-2.zip', 'base3/files/retro-recomp-base3-2-3.zip'])
        self.assertEqual(knowledge_exchange.local_base()['cursor'], 77)
        self.assertEqual(knowledge_exchange.local_base()['version'], 3)
        self.assertTrue(seen and seen[0][0] == 'full' and seen[-1][1] == seen[-1][2], seen)
        self.assertEqual({stage for stage, _, _ in seen}, {'full', 'delta'})
        self.assertEqual(self.entries_on_disk(), [f'{three[0]}.json'], 'the entries version 3 does not name are gone')
        # An older client with a difference for its version takes that one.
        self.assertEqual(online.update_base()['source'], None)

    def test_the_full_download_follows_a_redirect_to_a_safe_place_only(self):
        built = entry(part(1, 'standard', (0x100,)))
        self.server.base['redirect'] = True
        self.publish(1, {KEY: (built[0], [1])}, entries=[built])
        self.assertEqual(online.update_base()['error'], None)
        self.assertEqual(self.gets(), ['base3', 'redirect/retro-recomp-base3-1.zip', 'dl/retro-recomp-base3-1.zip'])
        # A redirect to another host is refused.
        for path in list(self.store.glob('*')):
            if path.is_file():
                path.unlink()
        self.server.base['redirect_to'] = 'https://elsewhere.example/base.zip'
        result = online.update_base()
        self.assertEqual((result['error'], result['source']), ('service', None))
        self.assertFalse(list(self.store.glob('download-*')), 'no scratch file is left behind')

    def test_direct_addresses_are_limited_to_the_release_files_of_the_project(self):
        good = 'https://github.com/ArthurReboulSalze/RetroRecomp/releases/download/v1.5.4/Retro-Recomp-base-412.zip'
        self.assertTrue(online._direct_ok(good))
        self.assertTrue(online._direct_ok('https://github.com/ArthurReboulSalze/RetroRecomp-base/releases/download/b412/'
                                          'retro-recomp-base-412.zip'))
        for bad in ('https://api.github.com/repos/ArthurReboulSalze/RetroRecomp/releases/assets/1',
                    'https://github.com/someone/else/releases/download/v1/x.zip',
                    'https://github.com/ArthurReboulSalze/RetroRecomp/archive/main.zip',
                    'http://github.com/ArthurReboulSalze/RetroRecomp/releases/download/v1/x.zip',
                    'https://user:pw@github.com/ArthurReboulSalze/RetroRecomp/releases/download/v1/x.zip',
                    'https://objects.githubusercontent.com/some/file.zip', 'https://example.com/x.zip',
                    'ftp://github.com/x.zip', 'file:///C:/x.zip', 'not a url'):
            with self.subTest(bad):
                self.assertFalse(online._direct_ok(bad))
        # GitHub sends its downloads on to its own storage hosts, and to nothing else.
        self.assertTrue(online._direct_ok('https://objects.githubusercontent.com/some/file.zip', redirected=True))
        self.assertTrue(online._direct_ok('https://release-assets.githubusercontent.com/a/b', redirected=True))
        self.assertFalse(online._direct_ok('https://example.com/x.zip', redirected=True))
        self.assertFalse(online._direct_ok('http://objects.githubusercontent.com/x', redirected=True))
        # A plain address on this computer only works with a test service on this computer.
        self.assertTrue(online._direct_ok(f'{self.url}/dl/x.zip'))
        with patch.dict(os.environ, {'RETRO_RECOMP_SERVICE': 'https://retro-recomp.com'}):
            self.assertFalse(online._direct_ok(f'{self.url}/dl/x.zip'))

    def test_a_download_that_is_not_what_the_manifest_says_is_refused_and_the_base_stays(self):
        one = entry(part(1, 'standard', (0x100,)))
        two = entry(part(1, 'standard', (0x100,)), part(2, 'standard', (0x200,)))
        self.publish(1, {KEY: (one[0], [1])}, entries=[one])
        self.assertEqual(online.update_base()['version'], 1)
        self.publish(2, {KEY: (two[0], [1, 2])}, entries=[two])
        manifest = self.server.base['manifest']
        delta = manifest['deltas']['1']
        name = delta['file']
        good = self.server.base['files'][name]
        def attempt(label, mutate_manifest=None, blob=None):
            self.server.base['manifest'] = json.loads(json.dumps(manifest))
            if mutate_manifest:
                mutate_manifest(self.server.base['manifest']['deltas']['1'])
            self.server.base['files'][name] = blob if blob is not None else good
            result = online.update_base()
            self.assertEqual((result['error'], result['version'], result['source']), ('verify', 1, None), label)
            self.assertEqual(knowledge_exchange.local_base()['version'], 1, label)
            self.assertEqual(self.entries_on_disk(), [f'{one[0]}.json'], label)
            self.assertFalse(list(self.store.glob('download-*')), label)
        attempt('a wrong hash', lambda item: item.update(sha256='f' * 64))
        attempt('a wrong size', lambda item: item.update(bytes=item['bytes'] + 1))
        attempt('bytes changed on the way', blob=good[:-20] + bytes(20))
        # Right hash and size, but not a base archive.
        rubbish = b'this is not a zip file'
        attempt('not an archive', lambda item: item.update(sha256=hashlib.sha256(rubbish).hexdigest(),
                                                           bytes=len(rubbish)), blob=rubbish)
        # An archive of the wrong version, or whose index is not the one its manifest names.
        wrong = base_archive(7, {KEY: (two[0], [1, 2])}, {two[0]: two[1]})
        attempt('another version', lambda item: item.update(sha256=hashlib.sha256(wrong).hexdigest(), bytes=len(wrong)),
                blob=wrong)
        tampered = self.rewrite(good, lambda members: members.update({'index.json': members['index.json'] + b' '}))
        attempt('another index', lambda item: item.update(sha256=hashlib.sha256(tampered).hexdigest(),
                                                          bytes=len(tampered)), blob=tampered)
        # An entry whose text is not the one its name says.
        forged = self.rewrite(good, lambda members: members.update(
            {f'entries/{two[0]}.json': knowledge_exchange.canonical_bytes(one[1])}))
        attempt('a forged entry', lambda item: item.update(sha256=hashlib.sha256(forged).hexdigest(), bytes=len(forged)),
                blob=forged)
        # An index that names an entry nothing holds.
        missing = self.rewrite(good, lambda members: members.pop(f'entries/{two[0]}.json'))
        attempt('an entry nobody holds', lambda item: item.update(sha256=hashlib.sha256(missing).hexdigest(),
                                                                  bytes=len(missing)), blob=missing)
        # And the good one still goes through afterwards.
        self.server.base['manifest'] = manifest
        self.server.base['files'][name] = good
        self.assertEqual(online.update_base()['version'], 2)

    def rewrite(self, blob, change):
        """An archive's bytes with its members changed by `change` (a dict of name: bytes)."""
        import io
        with zipfile.ZipFile(io.BytesIO(blob)) as source:
            members = {info.filename: source.read(info) for info in source.infolist()}
        change(members)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as target:
            for name, data in members.items():
                target.writestr(name, data)
        return buffer.getvalue()

    def test_an_archive_beyond_the_bounds_is_refused(self):
        one = entry(part(1, 'standard', (0x100,)))
        self.publish(1, {KEY: (one[0], [1])}, entries=[one])
        with patch.object(knowledge_exchange, 'BASE_ENTRY_LIMIT', 16):
            self.assertEqual(online.update_base()['error'], 'verify')
        with patch.object(knowledge_exchange, 'BASE_ZIP_MEMBERS', 2):
            self.assertEqual(online.update_base()['error'], 'verify')
        with patch.object(knowledge_exchange, 'BASE_UNPACKED_LIMIT', 10):
            self.assertEqual(online.update_base()['error'], 'verify')
        # The manifest's own sizes are bounded too: a huge difference is not even asked for.
        manifest = self.server.base['manifest']
        manifest['full']['bytes'] = online.BASE_FULL_LIMIT + 1
        self.assertEqual(online.update_base()['error'], 'no_path')
        self.assertEqual(self.gets().count('dl/retro-recomp-base3-1.zip'), 3)

    def test_the_old_base_stays_when_writing_the_new_one_fails_halfway(self):
        one = entry(part(1, 'standard', (0x100,)))
        two = entry(part(1, 'standard', (0x100,)), part(2, 'standard', (0x200,)))
        self.publish(1, {KEY: (one[0], [1])}, entries=[one])
        online.update_base()
        self.publish(2, {KEY: (two[0], [1, 2])}, entries=[two])
        with patch.object(knowledge_exchange, 'write_base_state', side_effect=OSError('disk full')):
            result = online.update_base()
        self.assertEqual((result['error'], result['version']), ('disk', 1))
        self.assertEqual(knowledge_exchange.local_base()['version'], 1)
        result = online.update_base()
        self.assertEqual((result['error'], knowledge_exchange.local_base()['version']), (None, 2))
        self.assertEqual(self.entries_on_disk(), [f'{two[0]}.json'])

    def test_what_update_base_says_when_it_cannot_update(self):
        keys = ('version', 'previous', 'downloaded_bytes', 'source', 'error')
        # No base published yet.
        result = online.update_base()
        self.assertEqual(result, {'version': None, 'previous': None, 'downloaded_bytes': 0, 'source': None,
                                  'error': 'no_base'})
        built = entry(part(1, 'standard', (0x100,)))
        self.publish(1, {KEY: (built[0], [1])}, entries=[built], format=4)
        result = online.update_base()
        self.assertEqual((result['error'], result['source']), ('format', None))
        self.assertEqual(sorted(result), sorted(keys))
        # A version no difference leads from and no complete base is newer than.
        self.publish(1, {KEY: (built[0], [1])}, entries=[built])
        self.assertEqual(online.update_base()['version'], 1)
        self.publish(2, {KEY: (built[0], [1])}, entries=[built], full=False)
        self.server.base['manifest']['deltas'] = {}
        result = online.update_base()
        self.assertEqual((result['error'], result['version'], result['previous']), ('no_path', 1, 1))
        self.server.base['fail'] = True
        self.assertEqual(online.update_base()['error'], 'service')
        self.stop_server()
        self.assertEqual(online.update_base()['error'], 'offline')
        with patch.dict(os.environ, {'RETRO_RECOMP_SERVICE': ''}):
            self.assertEqual(online.update_base()['error'], 'unavailable')

    # --- The batch: once a day, only with the option ----------------------------------

    def test_a_batch_updates_at_most_once_a_day_and_only_with_the_option(self):
        built = entry(part(1, 'standard', (0x100,)))
        self.publish(1, {KEY: (built[0], [1])}, entries=[built])
        with patch.object(online, '_run_update', wraps=online._run_update) as run:
            online.prepare_batch([KEY], enabled=False)
            self.assertEqual(run.call_count, 0)
            online.prepare_batch([KEY])
            online.prepare_batch([KEY])
            online.prepare_batch([KEY], now=time.time() + online.BASE_UPDATE_EVERY - 120)
            self.assertEqual(run.call_count, 1)
            online.prepare_batch([KEY], now=self.later())
            self.assertEqual(run.call_count, 2)
            online.prepare_batch([KEY], now=self.later() + 60)
            self.assertEqual(run.call_count, 2, 'the day counts from the last update')
            online.prepare_batch([KEY], now=self.later(2) + 60)
            self.assertEqual(run.call_count, 3)

    # --- Looking only ---------------------------------------------------------------------

    def test_checking_reads_the_manifest_only_and_downloads_nothing(self):
        old = entry(part(1, 'standard', (0x100,)))
        games = {KEY: (old[0], [1])}
        self.publish(3, games, entries=[old])
        self.install(3, games, [old])
        new = entry(part(1, 'standard', (0x100,)), part(2, 'standard', (0x200,)))
        self.publish(5, {KEY: (new[0], [1, 2])}, entries=[new])
        before = sorted(path.name for path in self.folder.rglob('*'))
        self.assertEqual(online.check_base(), {'local': 3, 'latest': 5, 'newer': True, 'error': None})
        self.assertEqual(self.gets(), ['base3'])
        self.assertEqual(self.entries_on_disk(), [])
        self.assertEqual(knowledge_exchange.local_base()['version'], 3)
        self.assertEqual(sorted(path.name for path in self.folder.rglob('*')), sorted(before + ['base', 'site.json']))
        # Within six hours: from the file, no request. Forced or later: the manifest again.
        self.server.hits.clear()
        self.assertEqual(online.check_base(now=time.time() + online.BASE_CHECK_EVERY - 60)['latest'], 5)
        self.assertEqual(self.server.hits, [])
        self.assertEqual(online.check_base(force=True)['latest'], 5)
        self.assertEqual(online.check_base(now=time.time() + online.BASE_CHECK_EVERY + 60)['latest'], 5)
        self.assertEqual(self.gets(), ['base3', 'base3'])
        # The local base is the latest: nothing newer.
        online.update_base()
        self.assertEqual(online.check_base(force=True), {'local': 5, 'latest': 5, 'newer': False, 'error': None})

    def test_checking_is_silent_when_the_service_cannot_be_reached(self):
        built = entry(part(1, 'standard', (0x100,)))
        # No base anywhere and none published: nothing to offer.
        self.assertEqual(online.check_base(), {'local': None, 'latest': None, 'newer': False, 'error': None})
        self.publish(2, {KEY: (built[0], [1])}, entries=[built])
        self.assertEqual(online.check_base(force=True), {'local': None, 'latest': 2, 'newer': True, 'error': None})
        self.server.base['fail'] = True
        self.assertEqual(online.check_base(force=True)['error'], 'service')
        self.server.base['fail'] = False
        self.publish(2, {KEY: (built[0], [1])}, entries=[built], format=4)
        self.assertEqual(online.check_base(force=True)['error'], 'format')
        self.publish(2, {KEY: (built[0], [1])}, entries=[built])
        self.stop_server()
        # Offline: no error raised, what was last seen is still reported.
        result = online.check_base(force=True)
        self.assertEqual((result['error'], result['local'], result['latest']), ('offline', None, 2))
        with patch.dict(os.environ, {'RETRO_RECOMP_SERVICE': ''}):
            self.assertEqual(online.check_base(force=True)['error'], None)

    def test_the_manifest_read_by_a_check_brings_the_revocations_to_the_next_batch(self):
        built = entry(part(47, 'standard', (0x100,)), part(52, 'standard', (0x180,)))
        self.publish(1, {KEY: (built[0], [47, 52])}, entries=[built])
        online.sync_base([KEY])
        self.assertEqual(len(knowledge.imported_record('sms', IDENTITY)['rom_entries']), 2)
        self.publish(1, {KEY: (built[0], [47, 52])}, entries=[built], revoked=[47])
        online.check_base(force=True)
        # The batch is within its day, so it asks nothing, yet the revocation applies.
        self.server.hits.clear()
        summary = online.sync_base([KEY])
        self.assertEqual((self.server.hits, summary['discarded']), ([], 1))
        self.assertEqual(knowledge.imported_record('sms', IDENTITY)['rom_entries'], [[0x180, 0, 0, 0, 1]])


class SplitTests(BaseHarness):
    """Qualified paths of this converter's engine go to the qualified bank; the
    rest to the imported banks, checked again by every conversion."""

    def games(self, *entries_, version=1):
        games = {key: (value[0], sources) for (key, sources), value in entries_}
        self.publish(version, games, entries=[value for _, value in entries_])

    def test_the_qualified_elements_of_the_engine_go_to_the_qualified_bank_and_the_rest_to_the_imported_ones(self):
        built = entry(part(47, 'extended', (0x100,), [[1, 0x300, 0, 2, 0x10]]),
                      qualified=[qualified((0x200, 0x240), level='extended', by='maintainer'),
                                 qualified((0x900,), engine=OTHER_ENGINE, level='thorough')])
        self.games(((KEY, [47]), built))
        prepared = online.prepare_batch([KEY])
        self.assertEqual((prepared['base']['games'], prepared['base']['qualified']), (1, 1))
        self.assertEqual(bank_record('sms', IDENTITY),
                         {**sms_record(0x200, 0x240), 'engine': ENGINE}, 'the validated record of the engine')
        self.assertEqual(knowledge_exchange.qualified_bank_path(), knowledge.imported_path().with_name('qualified.json.gz'))
        imported = knowledge.imported_record('sms', IDENTITY)
        self.assertEqual(sorted(row[0] for row in imported['rom_entries']), [0x100, 0x900],
                         'the pending part and the other engine\'s qualified paths, not this engine\'s')
        self.assertEqual(knowledge.imported_observations('sms', IDENTITY), [[1, 0x300, 0, 2, 0x10]])
        # The level of the other engine's paths counts, and so does the engine's own.
        self.assertEqual(prepared['paths'], {KEY: {'level': 'thorough', 'records': 3}})
        use = self.state('base-use.json')[KEY]
        self.assertEqual((use['qualified'], use['engine_id'], use['sources'], use['level'], use['records']),
                         ({'engine': ENGINE, 'level': 'extended', 'by': 'maintainer'}, ENGINE, [47], 'thorough', 2))

    def test_the_qualified_bank_merges_per_game_and_keeps_the_others(self):
        first = entry(qualified=[qualified((0x100,))])
        second = entry(qualified=[qualified((0x200,))], identity='cd' * 32)
        self.games(((KEY, []), first), ((OTHER_KEY, []), second))
        online.prepare_batch([KEY])
        self.assertEqual(sorted(knowledge_exchange.read_qualified_bank()['sms']), [IDENTITY])
        online.prepare_batch([OTHER_KEY])
        bank = knowledge_exchange.read_qualified_bank()['sms']
        self.assertEqual(sorted(bank), sorted([IDENTITY, 'cd' * 32]))
        self.assertEqual(bank[IDENTITY]['rom_entries'], [[0x100, 0, 0, 0, 1]])
        # A newer entry replaces that game's record, whatever it held; a game that leaves the base leaves the bank.
        grown = entry(qualified=[qualified((0x100, 0x140))])
        self.publish(2, {KEY: (grown[0], []), OTHER_KEY: (second[0], [])}, entries=[grown])
        online.prepare_batch([KEY, OTHER_KEY], now=self.later())
        bank = knowledge_exchange.read_qualified_bank()['sms']
        self.assertEqual(len(bank[IDENTITY]['rom_entries']), 2)
        self.assertEqual(bank['cd' * 32]['rom_entries'], [[0x200, 0, 0, 0, 1]])
        self.publish(3, {OTHER_KEY: (second[0], [])})
        online.prepare_batch([KEY, OTHER_KEY], now=self.later(2))
        self.assertEqual(sorted(knowledge_exchange.read_qualified_bank()['sms']), ['cd' * 32])
        self.assertEqual(online.shared_paths([KEY]), {})

    def test_the_qualified_bank_is_bounded_and_validated(self):
        built = entry(qualified=[qualified((0x100,))])
        self.games(((KEY, []), built))
        online.prepare_batch([KEY])
        self.assertIn([0x100, 0, 0, 0, 1], bank_record('sms', IDENTITY)['rom_entries'])
        # A record schema 3 refuses (the base builds none, but a damaged entry could carry one) is not written.
        broken = entry(qualified=[qualified(record={'engine': ENGINE, 'rom_bytes': 'many'})], identity='cd' * 32)
        self.publish(2, {KEY: (built[0], []), OTHER_KEY: (broken[0], [])}, entries=[broken])
        online.prepare_batch([KEY, OTHER_KEY], now=self.later())
        self.assertEqual(bank_record('sms', 'cd' * 32), {})
        # A full bank (per console) takes no new game; that game's paths are imported to be checked.
        full = entry(qualified=[qualified((0x700,))], identity='ee' * 32)
        self.publish(3, {KEY: (built[0], []), 'sms:' + 'ee' * 32: (full[0], [])}, entries=[full])
        with patch.object(knowledge_exchange, 'CONSOLE_LIMIT', 1):
            online.prepare_batch([KEY, 'sms:' + 'ee' * 32], now=self.later(2))
        self.assertEqual(bank_record('sms', 'ee' * 32), {})
        self.assertEqual(knowledge.imported_record('sms', 'ee' * 32)['rom_entries'], [[0x700, 0, 0, 0, 1]])
        self.assertTrue(bank_record('sms', IDENTITY))

    def test_a_new_engine_turns_the_qualified_paths_into_paths_to_check_with_their_level(self):
        built = entry(part(47, 'standard', (0x100,)), qualified=[qualified((0x200,), level='extended')])
        other = entry(qualified=[qualified((0x300,), level='thorough')], identity='cd' * 32)
        self.games(((KEY, [47]), built), ((OTHER_KEY, []), other))
        online.prepare_batch([KEY, OTHER_KEY])
        self.assertEqual(sorted(knowledge_exchange.read_qualified_bank()['sms']), sorted([IDENTITY, 'cd' * 32]))
        self.assertEqual(online.shared_paths([KEY, OTHER_KEY]),
                         {KEY: {'level': 'extended', 'records': 2}, OTHER_KEY: {'level': 'thorough', 'records': 1}})
        # The converter now has another engine revision.
        self.engines['sms'] = 'e' * 40
        prepared = online.prepare_batch([KEY])
        # The game of the batch: its old qualified paths are now paths to check, with their level.
        self.assertEqual(bank_record('sms', IDENTITY), {})
        imported = knowledge.imported_record('sms', IDENTITY)
        self.assertEqual(sorted(row[0] for row in imported['rom_entries']), [0x100, 0x200])
        use = self.state('base-use.json')[KEY]
        self.assertEqual((use['qualified'], use['engine_id'], use['level'], use['records']), (None, 'e' * 40, 'extended', 2))
        self.assertEqual(prepared['paths'][KEY], {'level': 'extended', 'records': 2})
        # The game of no batch loses its stale record too, but is not imported until a batch asks for it.
        self.assertEqual(knowledge_exchange.read_qualified_bank().get('sms', {}).get('cd' * 32), None)
        self.assertEqual(knowledge.imported_record('sms', 'cd' * 32), {})
        online.prepare_batch([OTHER_KEY])
        self.assertEqual(knowledge.imported_record('sms', 'cd' * 32)['rom_entries'], [[0x300, 0, 0, 0, 1]])
        self.assertEqual(online.shared_paths([OTHER_KEY]), {OTHER_KEY: {'level': 'thorough', 'records': 1}})

    def test_an_element_whose_record_was_not_built_with_its_engine_does_not_qualify(self):
        liar = entry(qualified=[qualified(engine=ENGINE, record={**sms_record(0x100), 'engine': OTHER_ENGINE})])
        self.games(((KEY, []), liar))
        online.prepare_batch([KEY])
        self.assertEqual(bank_record('sms', IDENTITY), {})
        self.assertEqual(knowledge.imported_record('sms', IDENTITY)['rom_entries'], [[0x100, 0, 0, 0, 1]])

    def test_a_deleted_qualified_bank_is_filled_again(self):
        built = entry(qualified=[qualified((0x100,))])
        self.games(((KEY, []), built))
        online.prepare_batch([KEY])
        knowledge_exchange.qualified_bank_path().unlink()
        online.prepare_batch([KEY])
        self.assertTrue(bank_record('sms', IDENTITY))
        # Or a bank that lost the game.
        knowledge_exchange.write_qualified_bank({'sms': {'cd' * 32: {**sms_record(0x500)}}})
        online.prepare_batch([KEY])
        self.assertTrue(bank_record('sms', IDENTITY))

    def test_revoking_or_quarantining_a_source_leaves_the_qualified_paths_alone(self):
        built = entry(part(47, 'standard', (0x100,)), qualified=[qualified((0x200,))])
        self.games(((KEY, [47]), built))
        online.prepare_batch([KEY])
        self.publish(1, {KEY: (built[0], [47])}, entries=[built], revoked=[47], quarantined=[[47, KEY]])
        summary = online.sync_base([KEY], now=self.later())
        self.assertEqual(summary['discarded'], 1)
        self.assertEqual(knowledge.imported_record('sms', IDENTITY), {})
        self.assertEqual(bank_record('sms', IDENTITY)['rom_entries'], [[0x200, 0, 0, 0, 1]])
        self.assertEqual(online.shared_paths([KEY]), {KEY: {'level': 'standard', 'records': 1}})

    def test_a_rejection_sets_the_imported_paths_aside_and_keeps_the_qualified_ones(self):
        built = entry(part(47, 'standard', (0x100,)), qualified=[qualified((0x200,)), qualified((0x900,), engine=OTHER_ENGINE)])
        self.games(((KEY, [47]), built))
        online.prepare_batch([KEY])
        knowledge.discard_imported('sms', IDENTITY, 'conversion broke')
        online.forget_shared([KEY])
        use = self.state('base-use.json')[KEY]
        self.assertEqual((use['rejected'], use['sources'], use['records']), ([built[0]], [], 0))
        self.assertEqual(online.shared_paths([KEY]), {KEY: {'level': 'standard', 'records': 1}},
                         'only the qualified paths remain')
        online.sync_base([KEY], now=self.later())
        self.assertEqual(knowledge.imported_record('sms', IDENTITY), {}, 'nothing of the entry is imported again')
        self.assertTrue(bank_record('sms', IDENTITY))
        # A game with only qualified paths has nothing to reject.
        only = entry(qualified=[qualified((0x300,))], identity='cd' * 32)
        self.publish(2, {KEY: (built[0], [47]), OTHER_KEY: (only[0], [])}, entries=[only])
        online.prepare_batch([OTHER_KEY], now=self.later(2))
        online.forget_shared([OTHER_KEY])
        self.assertEqual(self.state('base-use.json')[OTHER_KEY]['rejected'], [])

    def test_without_the_option_the_qualified_paths_still_apply_but_no_pending_path_comes_in(self):
        built = entry(part(47, 'standard', (0x100,)), qualified=[qualified((0x200,))])
        self.games(((KEY, [47]), built))
        online.update_base()
        self.server.hits.clear()
        prepared = online.prepare_batch([KEY], enabled=False)
        self.assertEqual(self.server.hits, [])
        self.assertEqual(bank_record('sms', IDENTITY)['rom_entries'], [[0x200, 0, 0, 0, 1]])
        self.assertEqual(knowledge.imported_record('sms', IDENTITY), {})
        self.assertEqual(prepared['paths'], {KEY: {'level': 'standard', 'records': 1}})
        self.assertEqual(prepared['base']['version'], 1)
        # Turning the option on later brings the pending part in.
        online.prepare_batch([KEY])
        self.assertEqual(knowledge.imported_record('sms', IDENTITY)['rom_entries'], [[0x100, 0, 0, 0, 1]])

    def test_a_neo_geo_element_qualifies_by_engine_and_loader_together(self):
        from retrorecomp.neogeo_build import GEOLITH_REV, LITHOGEN_REV
        from retrorecomp.neogeo_knowledge import compact_record, entry_set
        current = {'engine': f'{GEOLITH_REV}:{LITHOGEN_REV}', 'level': 'extended', 'by': 'players',
                   'record': compact_record(NG_IDENTITY, ng_record(rom=((1, 2), (1, 4)), ram=(), z80=()))}
        newer_loader = ng_record(rom=((1, 8),), ram=(), z80=(), loader='9' * 40)
        stale = {'engine': f'{GEOLITH_REV}:{"9" * 40}', 'level': 'thorough', 'by': 'players',
                 'record': compact_record(NG_IDENTITY, newer_loader)}
        built = entry(identity=NG_IDENTITY, system='ng', qualified=[current, stale])
        self.publish(1, {NG_KEY: (built[0], [])}, entries=[built])
        prepared = online.prepare_batch([NG_KEY])
        self.assertEqual(prepared['base']['qualified'], 1)
        kept = knowledge_exchange.read_qualified_bank()['ng'][NG_IDENTITY]
        self.assertEqual((kept['engine'], kept['loader']), (GEOLITH_REV, LITHOGEN_REV))
        self.assertEqual({row for name, row in entry_set(kept) if name == 'rom_entries'}, {(1, 2), (1, 4)})
        # The same emulator core with another loader is another engine: its paths are only to check.
        imported = knowledge.imported_record('ng', NG_IDENTITY)
        self.assertEqual({row for name, row in entry_set(imported) if name == 'rom_entries'}, {(1, 8)})
        self.assertEqual(prepared['paths'], {NG_KEY: {'level': 'thorough', 'records': 2}})
        # With the loader changed, the qualified record turns into one to check, level kept.
        self.engines['ng'] = f'{GEOLITH_REV}:{"7" * 40}'
        online.prepare_batch([NG_KEY])
        self.assertEqual(knowledge_exchange.read_qualified_bank().get('ng', {}), {})
        self.assertEqual(self.state('base-use.json')[NG_KEY]['qualified'], None)
        self.assertEqual(online.shared_paths([NG_KEY]), {NG_KEY: {'level': 'thorough', 'records': 2}})
        self.assertEqual(knowledge_exchange.record_engine('ng', kept), f'{GEOLITH_REV}:{LITHOGEN_REV}')
        self.assertEqual(knowledge_exchange.record_engine('sms', sms_record()), ENGINE)
        self.assertEqual(knowledge_exchange.record_engine('sms', 'nothing'), '')


class EntryTests(unittest.TestCase):
    def test_only_format_3_entries_are_read_and_the_qualified_elements_must_be_there(self):
        part_ = part(5, 'quick', (0x100,))
        two_sha, two = entry(part_, qualified=[qualified((0x200,))])
        found = knowledge_exchange.base_entry(two_sha, two, 'sms', IDENTITY)
        self.assertEqual((found['sources'], len(found['qualified']), found['format']), ([5], 1, 3))
        self.assertEqual(found['qualified'][0]['engine'], ENGINE, 'handed back with the engine the rest works on')
        # Formats 1 and 2, which converters before 1.6.0 read, are not a base any more.
        for format_ in (1, 2):
            old = {**two, 'format': format_}
            if format_ == 1:
                old = {name: value for name, value in old.items() if name != 'qualified'}
            sha = hashlib.sha256(knowledge_exchange.canonical_bytes(old)).hexdigest()
            self.assertIsNone(knowledge_exchange.base_entry(sha, old, 'sms', IDENTITY))
        without = {name: value for name, value in two.items() if name != 'qualified'}
        self.assertIsNone(knowledge_exchange.base_entry(hashlib.sha256(knowledge_exchange.canonical_bytes(without)).hexdigest(),
                                                        without, 'sms', IDENTITY))
        # Malformed elements are left out one by one, whatever they hold.
        good = two['qualified'][0]
        odd = {**two, 'qualified': [good, {**good, 'cores': 'x' * 300}, {**good, 'cores': 'a' * 40, 'level': 'galactic'},
                                    {**good, 'cores': 'b' * 40, 'by': 'nobody'}, {**good, 'cores': 'c' * 40, 'record': []},
                                    {**good, 'cores': 'd' * 40, 'record': {}}, {'engine': ENGINE}, 5]}
        odd_sha = hashlib.sha256(knowledge_exchange.canonical_bytes(odd)).hexdigest()
        self.assertEqual([item['engine'] for item in knowledge_exchange.base_entry(odd_sha, odd, 'sms', IDENTITY)['qualified']],
                         [ENGINE])
        self.assertIsNone(knowledge_exchange.base_entry(two_sha, two, 'sms', 'cd' * 32))
        self.assertIsNone(knowledge_exchange.base_entry('0' * 64, two, 'sms', IDENTITY))
        current, others = knowledge_exchange.split_qualified(
            'sms', knowledge_exchange.base_entry(two_sha, two, 'sms', IDENTITY)['qualified'], ENGINE)
        self.assertEqual((current['engine'], others), (ENGINE, []))
        self.assertEqual(knowledge_exchange.split_qualified('sms', [current], None)[0], None)
        self.assertEqual(knowledge_exchange.split_qualified('sms', [current], OTHER_ENGINE), (None, [current]))


if __name__ == '__main__':
    unittest.main()
