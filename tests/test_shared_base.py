"""The published base around a batch: manifest, index, entries, revocation.

A local fake service stands in for the site (tests/test_online.py, plus the
base routes). Entries are verified by the hash that names them; their parts
join the imported banks like fetched paths and are withdrawn when the
service revokes their source or the player's conversion rejects them.
"""
import gzip
from http.server import ThreadingHTTPServer
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from retrorecomp import knowledge, knowledge_exchange, online
from tests.test_online import FakeService, collected
from tests.test_shared_sync import calls_to, sms_record

IDENTITY = 'ab' * 32
KEY = f'sms:{IDENTITY}'
OTHER_KEY = 'sms:' + 'cd' * 32


class BaseService(FakeService):
    """FakeService plus the base routes. `server.base` holds `manifest` (None
    answers 404 no_base), `indexes` ({version: gzip bytes}) and `entries`
    ({sha: value}); `server.hits` lists every GET and entries request."""

    def do_GET(self):
        path = self.path.split('?')[0]
        self.server.hits.append(('GET', path))
        base = self.server.base
        if path.endswith('/api/v1/base'):
            if base['manifest'] is None:
                self.answer(404, {'error': 'no_base'})
            elif base.get('fail'):
                self.answer(500, {'error': 'server'})
            else:
                self.answer(200, base['manifest'])
        elif '/api/v1/base/index/' in path:
            data = base['indexes'].get(int(path.rsplit('/', 1)[1]))
            if data is None:
                self.answer(404, {'error': 'not_found'})
                return
            self.send_response(200)
            self.send_header('Content-Type', 'application/gzip')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif path.endswith('/api/v1/status'):
            self.answer(200, {'service': 'retro-recomp', 'api': 1, 'accepting': True, 'min_converter': '1.5.3'})
        else:
            super().do_GET()

    def do_POST(self):
        if self.path.endswith('/base/entries'):
            asked = json.loads(self.body())['entries']
            self.server.hits.append(('POST', self.path, asked))
            entries = self.server.base['entries']
            served = {sha: entries[sha] for sha in asked if sha in entries}
            deferred = []
            # A full answer: the service keeps the rest for the next call.
            room = self.server.base.get('room')
            if room is not None and len(served) > room:
                deferred = sorted(served)[room:]
                served = {sha: served[sha] for sha in sorted(served)[:room]}
            self.answer(200, {'entries': served or [], **({'deferred': deferred} if deferred else {})},
                        compress='gzip' in (self.headers.get('Accept-Encoding') or ''))
        elif self.path.endswith('/contributions') and self.server.mode == 'outdated':
            self.body()
            minimum = getattr(self.server, 'minimum', None)
            self.answer(426, {'error': 'converter_outdated', **({'detail': minimum} if minimum else {})})
        else:
            super().do_POST()


def part(source, level='standard', addresses=(), rows=None, record=True):
    return {'source': source, 'level': level, 'record': sms_record(*addresses) if record and addresses else None,
            'observations': rows or []}


def entry(*parts, identity=IDENTITY, system='sms'):
    """(sha, value) of a game entry built the way the service names it."""
    value = {'format': 1, 'system': system, 'identity': identity, 'parts': sorted(parts, key=lambda p: p['source'])}
    return hashlib.sha256(knowledge_exchange.canonical_bytes(value)).hexdigest(), value


def calls_after(server, kind):
    return [hit for hit in server.hits if hit[0] == kind]


class PublishedBaseTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.data = self.root / 'datas'
        self.bank = self.data / 'knowledge/imported.json.gz'
        self.folder = self.bank.parent
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), BaseService)
        self.server.calls, self.server.mode, self.server.claims = [], 'ok', 'ok'
        self.server.store, self.server.encodings, self.server.hits = {}, [], []
        self.server.base = {'manifest': None, 'indexes': {}, 'entries': {}}
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.stop_server)
        self.url = f'http://127.0.0.1:{self.server.server_address[1]}'
        for item in (patch.dict(os.environ, {'RETRO_RECOMP_SERVICE': self.url}),
                     patch('retrorecomp.paths.data_directory', return_value=self.data),
                     patch('retrorecomp.knowledge.imported_path', return_value=self.bank),
                     patch('retrorecomp.knowledge_exchange.imported_path', return_value=self.bank)):
            item.start()
            self.addCleanup(item.stop)
        self.addCleanup(knowledge._imported_bank.cache_clear)
        self.addCleanup(knowledge._observation_bank.cache_clear)

    def stop_server(self):
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.server = None

    def sign_in(self):
        online.request_code('p@example.test', 'en')
        online.sign_in('p@example.test', '123456', 'Retro-Recomp test')

    def publish(self, version, games, *, revoked=(), cursor=0, format=1, entries=(), index_format=None,
                index_version=None, sha=None, size=None):
        """Serve base `version`: `games` is {key: (entry sha, [sources])}; the
        `entries` ((sha, value) pairs) join those the service holds."""
        index = {'format': index_format or format, 'version': index_version or version, 'built_utc': '2026-10-27T03:00:00+00:00',
                 'games': {key: {'entry': value[0], 'sources': value[1]} for key, value in games.items()}}
        raw = gzip.compress(knowledge_exchange.canonical_bytes(index), mtime=0)
        base = self.server.base
        base['indexes'][version] = raw
        base['entries'].update(dict(entries))
        base['manifest'] = {'format': format, 'formats': [format], 'version': version, 'built_utc': index['built_utc'],
                            'published_utc': '2026-10-27T03:01:00+00:00', 'cursor': cursor, 'min_converter': '1.5.1',
                            'games': len(games), 'index': {'sha256': sha or hashlib.sha256(raw).hexdigest(),
                                                           'bytes': size or len(raw)},
                            'revoked': list(revoked)}
        return raw

    def later(self, steps=1):
        return time.time() + steps * (online.BASE_REFRESH + 1)

    def state(self, name):
        return json.loads((self.folder / name).read_text(encoding='utf-8'))

    # --- Manifest, index, entries --------------------------------------------

    def test_the_batch_roms_come_from_the_index_with_no_account(self):
        first = entry(part(47, 'extended', (0x100,), [[1, 0x300, 0, 2, 0x10]]), part(52, 'quick', (0x180,)))
        elsewhere = entry(part(9, 'standard', (0x200,)), identity='cd' * 32)
        self.publish(7, {KEY: (first[0], [47, 52]), OTHER_KEY: (elsewhere[0], [9])}, cursor=90,
                     entries=[first, elsewhere])
        self.server.calls.clear()
        prepared = online.prepare_batch([KEY])
        self.assertEqual({name: prepared['base'][name] for name in ('version', 'games', 'discarded', 'note', 'error')},
                         {'version': 7, 'games': 1, 'discarded': 0, 'note': None, 'error': None})
        self.assertIsNone(prepared['summary'], 'no account: no per-account fetch')
        self.assertEqual(calls_to(self.server, '/knowledge/fetch'), [])
        self.assertEqual(prepared['paths'], {KEY: {'level': 'extended', 'records': 2}})
        self.assertEqual(knowledge.imported_record('sms', IDENTITY)['rom_entries'],
                         [[0x100, 0, 0, 0, 1], [0x180, 0, 0, 0, 1]])
        self.assertEqual(knowledge.imported_observations('sms', IDENTITY), [[1, 0x300, 0, 2, 0x10]])
        self.assertEqual(knowledge.imported_record('sms', 'cd' * 32), {}, 'only the batch\'s games are imported')
        # Exactly one entry was asked for, publicly.
        self.assertEqual([hit[2] for hit in calls_after(self.server, 'POST')], [[first[0]]])
        self.assertEqual(self.server.encodings, [])
        state = self.state('base-state.json')
        self.assertEqual((state['version'], state['revoked'], state['cursor'], state['service']), (7, [], 90, self.url))
        self.assertEqual(state['index_sha256'], hashlib.sha256((self.folder / 'base-index.json.gz').read_bytes()).hexdigest())
        use = self.state('base-use.json')
        self.assertEqual({name: use[KEY][name] for name in ('entry', 'sources', 'level', 'records', 'version', 'rejected')},
                         {'entry': first[0], 'sources': [47, 52], 'level': 'extended', 'records': 2, 'version': 7,
                          'rejected': []})
        self.assertNotIn(OTHER_KEY, use)

    def test_the_manifest_is_read_every_thirty_minutes_and_an_unchanged_index_is_not_downloaded_again(self):
        built = entry(part(1, 'standard', (0x100,)))
        self.publish(3, {KEY: (built[0], [1])}, entries=[built])
        online.sync_base([KEY])
        self.assertEqual([hit[1].rsplit('/api/v1/', 1)[1] for hit in calls_after(self.server, 'GET')],
                         ['base', 'base/index/3'])
        self.server.hits.clear()
        # Within BASE_REFRESH: no request at all.
        online.sync_base([KEY], now=time.time() + online.BASE_REFRESH - 60)
        self.assertEqual(self.server.hits, [])
        # Later: the manifest only (same version and hash), no index, no entry.
        online.sync_base([KEY], now=self.later())
        self.assertEqual([hit[1].rsplit('/api/v1/', 1)[1] for hit in self.server.hits], ['base'])
        # A new version downloads its index and the entry that changed, no other.
        grown = entry(part(1, 'standard', (0x100,)), part(2, 'thorough', (0x200,)))
        self.publish(4, {KEY: (grown[0], [1, 2])}, entries=[grown])
        self.server.hits.clear()
        summary = online.sync_base([KEY], now=self.later(2))
        self.assertEqual([hit[1].rsplit('/api/v1/', 1)[1] for hit in calls_after(self.server, 'GET')], ['base', 'base/index/4'])
        self.assertEqual([hit[2] for hit in calls_after(self.server, 'POST')], [[grown[0]]])
        self.assertEqual((summary['version'], summary['games']), (4, 1))
        self.assertEqual(online.shared_paths([KEY]), {KEY: {'level': 'thorough', 'records': 2}})
        self.assertEqual(self.state('base-state.json')['version'], 4)

    def test_an_index_that_is_not_the_one_announced_is_refused(self):
        built = entry(part(1, 'standard', (0x100,)))
        games = {KEY: (built[0], [1])}
        for wrong in ({'sha': 'f' * 64}, {'size': 5}):
            with self.subTest(wrong):
                self.publish(1, games, entries=[built], **wrong)
                summary = online.sync_base([KEY])
                self.assertIsInstance(summary['error'], online.ServiceError)
                self.assertIsNone(summary['version'])
                self.assertFalse((self.folder / 'base-index.json.gz').exists())
                self.assertFalse((self.folder / 'base-state.json').exists())
                self.assertEqual(knowledge.imported_record('sms', IDENTITY), {})
        # An index that is not of the announced version or format, even with the right hash.
        for odd in ({'index_version': 9}, {'index_format': 2}):
            with self.subTest(odd):
                self.publish(1, games, entries=[built], **odd)
                self.assertIsInstance(online.sync_base([KEY])['error'], online.ServiceError)
                self.assertFalse((self.folder / 'base-state.json').exists())
        # A good base is then taken, and a bad one later leaves it in use.
        self.publish(5, games, entries=[built])
        self.assertEqual(online.sync_base([KEY], now=self.later())['games'], 1)
        self.publish(6, games, entries=[built], sha='0' * 64)
        summary = online.sync_base([KEY], now=self.later(2))
        self.assertIsInstance(summary['error'], online.ServiceError)
        self.assertEqual(summary['version'], 5)
        self.assertEqual(online.shared_paths([KEY]), {KEY: {'level': 'standard', 'records': 1}})
        self.assertEqual(self.state('base-state.json')['version'], 5)

    def test_an_entry_is_checked_against_the_hash_that_named_it(self):
        good = entry(part(1, 'standard', (0x100,)))
        forged = json.loads(json.dumps(good[1]))
        forged['parts'][0]['record'] = sms_record(0x999)
        stranger = entry(part(1, 'standard', (0x100,)), identity='11' * 32)   # named by its own hash
        flawed = entry(part(1, 'standard', (0x100,)), part(2, 'thorough', rows=[[1, 0x400, 0, 2, 0x20]]),
                       part(3, 'standard', (0x300,)))
        # Part 1 is not a record at all, part 3 is not a part; part 2 has a good row among bad ones.
        flawed[1]['parts'][0]['record'] = {'engine': 'not hex', 'rom_bytes': 8192}
        flawed[1]['parts'][1]['observations'].append([99, 1, 0, 2, 0])
        flawed[1]['parts'][2]['level'] = 'galactic'
        flawed = (hashlib.sha256(knowledge_exchange.canonical_bytes(flawed[1])).hexdigest(), flawed[1])
        self.publish(1, {KEY: (good[0], [1])}, entries=[(good[0], forged)])
        summary = online.sync_base([KEY])
        self.assertEqual(summary['games'], 0, 'a text that does not hash to its name is refused')
        self.assertEqual(knowledge.imported_record('sms', IDENTITY), {})
        self.assertFalse((self.folder / 'base-use.json').exists(), 'and asked again next time')
        self.publish(1, {KEY: (stranger[0], [1])}, entries=[stranger])
        self.assertEqual(online.sync_base([KEY])['games'], 0, 'an entry for another ROM is refused')
        # Invalid parts are skipped one by one.
        self.publish(2, {KEY: (flawed[0], [1, 2, 3])}, entries=[flawed])
        summary = online.sync_base([KEY], now=self.later())
        self.assertEqual((summary['games'], summary['error']), (1, None))
        self.assertEqual(knowledge.imported_record('sms', IDENTITY), {})
        self.assertEqual(knowledge.imported_observations('sms', IDENTITY), [[1, 0x400, 0, 2, 0x20]])
        self.assertEqual(online.shared_paths([KEY]), {KEY: {'level': 'thorough', 'records': 0}})

    def test_entries_are_asked_for_by_128(self):
        games, entries = {}, []
        for number in range(130):
            identity = '%064x' % number
            built = entry(part(number + 1, 'standard', (0x100,)), identity=identity)
            games[f'sms:{identity}'] = (built[0], [number + 1])
            entries.append(built)
        self.publish(1, games, entries=entries)
        summary = online.sync_base(list(games))
        self.assertEqual(summary['games'], 130)
        self.assertEqual([len(hit[2]) for hit in calls_after(self.server, 'POST')], [128, 2])

    def test_entries_the_service_deferred_are_asked_for_again(self):
        games, entries = {}, []
        for number in range(5):
            identity = '%064x' % number
            built = entry(part(number + 1, 'standard', (0x100,)), identity=identity)
            games[f'sms:{identity}'] = (built[0], [number + 1])
            entries.append(built)
        self.publish(1, games, entries=entries)
        self.server.base['room'] = 2
        summary = online.sync_base(list(games))
        self.assertEqual(summary['games'], 5)
        self.assertEqual([len(hit[2]) for hit in calls_after(self.server, 'POST')], [5, 3, 1])

    # --- Revocation, removal, rejection ----------------------------------------

    def test_a_revoked_source_withdraws_its_part_and_the_account_cursor_starts_again(self):
        self.sign_in()
        built = entry(part(47, 'thorough', (0x100,), [[1, 0x300, 0, 2, 0x10]]), part(52, 'quick', (0x180,)))
        self.publish(1, {KEY: (built[0], [47, 52])}, cursor=40, entries=[built])
        self.server.store = {KEY: [{'id': 30, 'record': sms_record(0x100), 'level': 'thorough'}]}
        prepared = online.prepare_batch([KEY])
        self.assertEqual(prepared['paths'], {KEY: {'level': 'thorough', 'records': 2}})
        cursors = self.state('shared-cursors.json')['roms']
        self.assertEqual(cursors[KEY]['cursor'], 40, 'the base holds what the fetch would serve up to its cursor')
        self.assertEqual([json.loads(call[3])['roms'] for call in calls_to(self.server, '/knowledge/fetch')], [{KEY: 40}])
        # The service revokes upload 47 (and the rows only it brought).
        self.publish(1, {KEY: (built[0], [47, 52])}, cursor=40, revoked=[47], entries=[built])
        self.server.hits.clear()
        summary = online.sync_base([KEY], now=self.later())
        self.assertEqual((summary['discarded'], summary['games']), (1, 1))
        self.assertEqual(knowledge.imported_record('sms', IDENTITY)['rom_entries'], [[0x180, 0, 0, 0, 1]])
        self.assertEqual(knowledge.imported_observations('sms', IDENTITY), [])
        self.assertEqual(online.shared_paths([KEY]), {KEY: {'level': 'quick', 'records': 1}})
        use = self.state('base-use.json')[KEY]
        self.assertEqual((use['sources'], use['entry']), ([52], built[0]))
        rejected = json.loads((self.folder / 'imported-rejected.json').read_text(encoding='utf-8'))
        self.assertTrue(rejected[-1]['reason'].startswith('shared base: '))
        cursors = self.state('shared-cursors.json')['roms']
        self.assertEqual(cursors[KEY]['cursor'], 0, 'served again from the start, not skipped by the base cursor')
        self.assertNotIn('level', cursors[KEY])
        # The fetch of the same batch serves the game from the start again.
        self.server.calls.clear()
        self.assertEqual(online.sync_shared([KEY])['records'], 1)
        self.assertEqual([json.loads(call[3])['roms'] for call in calls_to(self.server, '/knowledge/fetch')], [{KEY: 0}])
        self.assertEqual(self.state('shared-cursors.json')['roms'][KEY]['cursor'], 30)

    def test_a_game_that_left_the_index_or_lost_a_source_is_withdrawn(self):
        first = entry(part(1, 'standard', (0x100,)), part(2, 'standard', (0x200,)))
        self.publish(1, {KEY: (first[0], [1, 2])}, entries=[first])
        online.sync_base([KEY])
        # The entry is replaced by one that lacks source 2: the game is rebuilt from the new entry.
        second = entry(part(1, 'standard', (0x100,)), part(3, 'extended', (0x300,)))
        self.publish(2, {KEY: (second[0], [1, 3])}, entries=[second])
        summary = online.sync_base([KEY], now=self.later())
        self.assertEqual((summary['discarded'], summary['games']), (1, 1))
        self.assertEqual(knowledge.imported_record('sms', IDENTITY)['rom_entries'],
                         [[0x100, 0, 0, 0, 1], [0x300, 0, 0, 0, 1]])
        # The game disappears from the index: nothing of it stays.
        self.publish(3, {OTHER_KEY: (entry(part(9, 'standard', (0x100,)), identity='cd' * 32)[0], [9])})
        summary = online.sync_base([KEY], now=self.later(2))
        self.assertEqual((summary['discarded'], summary['games']), (1, 0))
        self.assertEqual(knowledge.imported_record('sms', IDENTITY), {})
        self.assertEqual(online.shared_paths([KEY]), {})
        # An entry that only grows keeps what is there and adds the new part.
        grown = entry(part(3, 'extended', (0x300,)))
        self.publish(4, {KEY: (grown[0], [3])}, entries=[grown])
        online.sync_base([KEY], now=self.later(3))
        more = entry(part(3, 'extended', (0x300,)), part(4, 'quick', (0x400,)))
        self.publish(5, {KEY: (more[0], [3, 4])}, entries=[more])
        summary = online.sync_base([KEY], now=self.later(4))
        self.assertEqual(summary['discarded'], 0)
        self.assertEqual(len(knowledge.imported_record('sms', IDENTITY)['rom_entries']), 2)

    def test_a_rejected_entry_is_not_imported_again_until_the_index_changes_for_that_game(self):
        built = entry(part(1, 'standard', (0x100,)), part(2, 'standard', (0x200,)))
        self.publish(1, {KEY: (built[0], [1, 2])}, entries=[built])
        online.sync_base([KEY])
        # A conversion rejects the shared paths: the window discards and forgets them.
        knowledge.discard_imported('sms', IDENTITY, 'conversion broke')
        online.forget_shared([KEY])
        self.assertEqual(online.shared_paths([KEY]), {})
        use = self.state('base-use.json')[KEY]
        self.assertEqual((use['rejected'], use['rejected_sources'], use['sources']), ([built[0]], [1, 2], []))
        self.server.hits.clear()
        for step in (1, 2):
            summary = online.sync_base([KEY], now=self.later(step))
            self.assertEqual((summary['games'], summary['discarded']), (0, 0))
        self.assertEqual(calls_after(self.server, 'POST'), [])
        self.assertEqual(knowledge.imported_record('sms', IDENTITY), {})
        # The index names another entry for the game: it comes in.
        newer = entry(part(1, 'standard', (0x100,)), part(2, 'standard', (0x200,)), part(8, 'extended', (0x800,)))
        self.publish(2, {KEY: (newer[0], [1, 2, 8])}, entries=[newer])
        self.assertEqual(online.sync_base([KEY], now=self.later(3))['games'], 1)
        self.assertEqual(len(knowledge.imported_record('sms', IDENTITY)['rom_entries']), 3)
        self.assertEqual(self.state('base-use.json')[KEY]['rejected'], [built[0]])

    def test_removing_the_imported_banks_restarts_the_base_too(self):
        built = entry(part(1, 'standard', (0x100,)))
        self.publish(1, {KEY: (built[0], [1])}, entries=[built])
        online.sync_base([KEY])
        for path in self.folder.glob('imported*.json.gz'):
            path.unlink()
        self.assertEqual(online.shared_paths([KEY]), {})
        self.assertEqual(online.sync_base([KEY], now=self.later())['games'], 1)
        self.assertEqual(len(knowledge.imported_record('sms', IDENTITY)['rom_entries']), 1)

    # --- Formats, failures, accounts ----------------------------------------------

    def test_an_unknown_format_keeps_the_local_base(self):
        built = entry(part(1, 'standard', (0x100,)))
        self.publish(1, {KEY: (built[0], [1])}, entries=[built])
        online.sync_base([KEY])
        self.publish(2, {KEY: (built[0], [1])}, entries=[built], format=2)
        self.server.hits.clear()
        summary = online.sync_base([KEY], now=self.later())
        self.assertEqual((summary['note'], summary['format'], summary['version'], summary['error']), ('format', 2, 1, None))
        self.assertEqual([hit[1].rsplit('/api/v1/', 1)[1] for hit in self.server.hits], ['base'])
        self.assertEqual(self.state('base-state.json')['version'], 1)
        self.assertEqual(online.shared_paths([KEY]), {KEY: {'level': 'standard', 'records': 1}})
        self.assertEqual(len(knowledge.imported_record('sms', IDENTITY)['rom_entries']), 1)

    def test_no_base_yet_and_a_failing_service_never_stop_the_batch(self):
        summary = online.sync_base([KEY])
        self.assertEqual((summary['note'], summary['version'], summary['error']), ('no_base', None, None))
        self.assertEqual(online.prepare_batch([KEY])['paths'], {})
        built = entry(part(1, 'standard', (0x100,)))
        self.publish(1, {KEY: (built[0], [1])}, entries=[built])
        online.sync_base([KEY])
        self.server.base['fail'] = True
        prepared = online.prepare_batch([KEY], now=self.later())
        self.assertEqual(prepared['base']['error'].reason, 'server')
        self.assertEqual(prepared['base']['version'], 1, 'the base already here still applies')
        self.assertEqual(prepared['paths'], {KEY: {'level': 'standard', 'records': 1}})
        self.stop_server()
        prepared = online.prepare_batch([KEY], now=self.later(2))
        self.assertIsInstance(prepared['base']['error'], online.ServiceConnectionError)
        self.assertEqual(prepared['paths'], {KEY: {'level': 'standard', 'records': 1}})

    def test_an_entry_that_cannot_be_fetched_is_tried_again_and_keeps_the_cursor_back(self):
        self.sign_in()
        built = entry(part(1, 'standard', (0x100,)))
        self.publish(1, {KEY: (built[0], [1])}, cursor=60)   # the service lacks the entry
        prepared = online.prepare_batch([KEY, OTHER_KEY])
        self.assertEqual(prepared['paths'], {})
        cursors = self.state('shared-cursors.json')['roms']
        self.assertNotIn(KEY, cursors, 'what the base could not give stays for the fetch')
        self.assertEqual(cursors[OTHER_KEY]['cursor'], 60, 'a ROM the base does not list is covered up to its cursor')
        self.server.base['entries'][built[0]] = built[1]
        self.assertEqual(online.sync_base([KEY], now=self.later())['games'], 1)
        self.assertEqual(self.state('shared-cursors.json')['roms'][KEY]['cursor'], 60)

    def test_with_an_account_the_fetch_follows_the_base_and_without_one_it_is_skipped(self):
        built = entry(part(1, 'standard', (0x100,)))
        self.publish(1, {KEY: (built[0], [1])}, cursor=25, entries=[built])
        self.server.store = {KEY: [{'id': 20, 'record': sms_record(0x100)},
                                   {'id': 31, 'record': sms_record(0x900), 'level': 'extended'}]}
        self.sign_in()
        prepared = online.prepare_batch([KEY])
        # The fetch asks from the base's cursor: only what is newer comes.
        self.assertEqual([json.loads(call[3])['roms'] for call in calls_to(self.server, '/knowledge/fetch')], [{KEY: 25}])
        self.assertEqual(prepared['summary']['records'], 1)
        self.assertEqual(prepared['paths'], {KEY: {'level': 'extended', 'records': 2}},
                         'the base\'s paths and the fetch\'s together')
        self.assertEqual(len(knowledge.imported_record('sms', IDENTITY)['rom_entries']), 2)
        online.forget_shared([KEY])
        self.assertEqual(online.shared_paths([KEY]), {})
        online.sign_out()
        self.server.calls.clear()
        prepared = online.prepare_batch([KEY])
        self.assertEqual((prepared['summary'], prepared['error']), (None, None))
        self.assertEqual(prepared['base']['version'], 1)
        self.assertEqual(calls_to(self.server, '/knowledge/fetch'), [])

    # --- 426 converter_outdated ---------------------------------------------------

    def test_an_outdated_converter_is_told_to_update_and_its_games_stay_pending(self):
        self.sign_in()
        self.server.mode = 'outdated'
        self.server.minimum = '1.5.3'
        found = collected()
        with self.assertRaises(online.ServiceError) as caught:
            online.send(online.pending(found))
        self.assertEqual((caught.exception.status, caught.exception.reason, caught.exception.detail),
                         (426, 'converter_outdated', '1.5.3'))
        self.assertEqual(online.pending(found)['games'], 1, 'nothing was marked as shared')
        # A service that gives no detail: the minimum comes from GET status.
        self.server.minimum = None
        with self.assertRaises(online.ServiceError) as caught:
            online.send(online.pending(found))
        self.assertEqual(caught.exception.detail, '1.5.3')
        self.assertEqual(online.pending(found)['games'], 1)
        self.assertEqual(online.minimum_converter(online.ServiceError(426, 'converter_outdated', 'not a version'), ask=False), '')
        self.assertEqual(online.minimum_converter(online.ServiceError(426, 'converter_outdated', '1.6.0'), ask=False), '1.6.0')
        # The window turns it into a real message, in every language.
        from retrorecomp import gui
        from retrorecomp.i18n import tr
        from retrorecomp.languages import LANGUAGES
        owner = gui.Application.__new__(gui.Application)
        error = online.ServiceError(426, 'converter_outdated', '1.5.3')
        plain = online.ServiceError(426, 'converter_outdated')
        for code in LANGUAGES:
            owner.language = code
            message = owner.service_problem(error)
            self.assertIn('1.5.3', message, code)
            self.assertEqual(message, tr('online_outdated_min', code, minimum='1.5.3'))
            self.assertNotIn('converter_outdated', message)
            self.assertNotIn('{', owner.service_problem(plain))
            if code != 'en':
                self.assertNotEqual(message, tr('online_outdated_min', 'en', minimum='1.5.3'), code)
                self.assertNotEqual(owner.service_problem(plain), tr('online_outdated', 'en'), code)

    # --- The window's log lines ---------------------------------------------------

    def test_the_window_says_what_the_published_base_gave_in_every_language(self):
        from queue import Queue
        from retrorecomp import gui
        from retrorecomp.i18n import tr
        from retrorecomp.languages import LANGUAGES
        owner = gui.Application.__new__(gui.Application)
        owner.messages = Queue()
        def lines(base, summary=None, error=None):
            owner.log_published_base(base, summary, error)
            found = []
            while not owner.messages.empty():
                found.append(owner.messages.get_nowait()[1])
            return found
        received = {'version': 412, 'games': 3, 'asked': 5, 'note': None, 'error': None}
        for code in LANGUAGES:
            owner.language = code
            text = lines(received)
            self.assertEqual(text, [tr('shared_base_received', code, version=412, games=3)])
            self.assertIn('412', text[0])
            self.assertIn('3', text[0])
            if code != 'en':
                self.assertNotEqual(text[0], tr('shared_base_received', 'en', version=412, games=3), code)
            self.assertEqual(len(lines({**received, 'games': 0})), 1)
            self.assertEqual(lines({**received, 'games': 0}, summary={'roms': 0}), [], 'the sync of the account says it')
            self.assertEqual(len(lines({'version': 4, 'games': 0, 'asked': 1, 'note': 'format', 'format': 2, 'error': None})), 1)
            problem = lines({'version': None, 'games': 0, 'asked': 1, 'note': None, 'error': online.ServiceConnectionError()})
            self.assertEqual(problem, [tr('shared_base_unavailable', code, error=tr('online_unreachable', code))])
            self.assertEqual(lines({'version': None, 'games': 0, 'asked': 1, 'note': 'no_base', 'error': None}), [])
        self.assertEqual(lines(None), [])


if __name__ == '__main__':
    unittest.main()
