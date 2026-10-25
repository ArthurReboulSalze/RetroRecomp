"""The shared-base client: sign-in by code, uploads, and marking only after success."""
import gzip
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from retrorecomp import knowledge, knowledge_exchange, online

SHA = '0123456789abcdef' * 4
OTHER = 'fedcba9876543210' * 4


def collected(rows=None, games=None):
    """A collect_knowledge result with raw observations only."""
    games = games or {SHA: 'Super Mario Land'}
    observations = {'gb': {identity: rows or [[2, 0x4000, 1, 3, 0x1234]] for identity in games}}
    return {'games': len(games), 'consoles': {'gb': len(games)}, 'discoveries': len(games), 'omitted': {},
            'observations': observations, 'observation_count': len(games),
            'payload': {'schema': 1, 'consoles': {}}, 'titles': {'gb': dict(games)}}


LEVELS = ('quick', 'standard', 'extended', 'thorough')


class FakeService(BaseHTTPRequestHandler):
    """Just enough of the PHP API; behaviour switched through `server.mode`
    (uploads), `server.claims` ('ok', 'missing' as on an older server, 'busy')
    and `server.store` ({'system:sha256': [{'id', 'record', 'rows', 'level'}]},
    what knowledge/fetch serves)."""
    def log_message(self, *args):
        pass

    def answer(self, status, payload, compress=False):
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        if compress:
            data = gzip.compress(data)
            self.send_header('Content-Encoding', 'gzip')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def claims(self, data):
        mode = getattr(self.server, 'claims', 'ok')
        if mode == 'missing':
            self.answer(404, {'error': 'not_found'})
        elif mode == 'busy':
            self.answer(503, {'error': 'busy'})
        elif mode == 'refused':   # the contribution was found invalid
            self.answer(409, {'error': 'refused'})
        else:
            games = json.loads(data)['games']
            paths = sum(len(game['hints']) + len(game['observations']) for game in games)
            self.answer(200, {'games': len(games), 'paths': paths, 'new': paths})

    def fetch(self, data):
        self.server.encodings.append(self.headers.get('Accept-Encoding'))
        served = {}
        for key, cursor in json.loads(data)['roms'].items():
            # As on the site: at most 64 stored records per ROM in one answer.
            entries = sorted((entry for entry in getattr(self.server, 'store', {}).get(key, [])
                              if entry['id'] > cursor), key=lambda entry: entry['id'])[:64]
            if entries:
                levels = [entry['level'] for entry in entries if entry.get('level')]
                served[key] = {'cursor': max(entry['id'] for entry in entries),
                               'level': max(levels, key=LEVELS.index) if levels else None,
                               'records': [entry['record'] for entry in entries if entry.get('record')],
                               'observations': [row for entry in entries for row in entry.get('rows', [])]}
        # PHP writes an empty object as an empty list.
        self.answer(200, {'roms': served or []}, compress='gzip' in (self.headers.get('Accept-Encoding') or ''))

    def body(self):
        return self.rfile.read(int(self.headers.get('Content-Length') or 0))

    def do_GET(self):
        self.answer(200, {'service': 'retro-recomp', 'api': 1, 'accepting': True})

    def do_DELETE(self):
        self.server.calls.append(('DELETE', self.path, self.headers.get('Authorization')))
        self.answer(200, {'signed_out': True})

    def do_POST(self):
        data = self.body()
        if self.headers.get('Content-Encoding') == 'gzip':
            data = gzip.decompress(data)
            self.server.packed = getattr(self.server, 'packed', []) + [self.path]
        self.server.calls.append(('POST', self.path, self.headers.get('Authorization'), data))
        mode = self.server.mode
        if self.path.endswith('/auth/code'):
            self.answer(202, {'sent': True})
        elif self.path.endswith('/auth/token'):
            if json.loads(data)['code'] != '123456':
                self.answer(400, {'error': 'invalid_code'})
            else:
                self.answer(200, {'token': 'rr1_' + 'a' * 43, 'account': {'email': 'p@example.test', 'pseudonym': None}})
        elif self.path.endswith('/levels'):
            self.answer(200, {'levels': len(json.loads(data)['levels'])})
        elif self.path.endswith('/claims'):
            self.claims(data)
        elif self.path.endswith('/knowledge/fetch'):
            self.fetch(data)
        elif self.path.endswith('/reports') and mode in ('limited', 'large', 'invalid'):
            status, reason = {'limited': (429, 'rate_limited'), 'large': (413, 'too_large'),
                              'invalid': (400, 'invalid_report')}[mode]
            self.answer(status, {'error': reason})
        elif mode == 'fail':
            self.answer(500, {'error': 'server'})
        elif mode == 'revoked':
            self.answer(401, {'error': 'unauthorized'})
        else:
            self.answer(201, {'id': 7, 'status': 'received'})


class OnlineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data = Path(self.temp.name) / 'datas'
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), FakeService)
        self.server.calls, self.server.mode, self.server.claims = [], 'ok', 'ok'
        self.server.store, self.server.encodings = {}, []
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f'http://127.0.0.1:{self.server.server_address[1]}'
        bank = self.data / 'knowledge/imported.json.gz'
        self.patches = [patch.dict(os.environ, {'RETRO_RECOMP_SERVICE': self.url}),
                        patch('retrorecomp.paths.data_directory', return_value=self.data),
                        patch('retrorecomp.knowledge.imported_path', return_value=bank),
                        patch('retrorecomp.knowledge_exchange.imported_path', return_value=bank)]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in self.patches:
            item.stop()
        self.server.shutdown()
        self.server.server_close()
        self.temp.cleanup()

    def sign_in(self):
        online.request_code('p@example.test', 'fr')
        return online.sign_in('p@example.test', '123456', 'Retro-Recomp test')

    def test_the_public_service_by_default_and_an_empty_value_turns_it_off(self):
        self.assertEqual(online.DEFAULT_SERVICE, 'https://retro-recomp.com')
        with patch.dict(os.environ):
            os.environ.pop('RETRO_RECOMP_SERVICE', None)
            self.assertEqual(online.service_url(), 'https://retro-recomp.com')
        with patch.dict(os.environ, {'RETRO_RECOMP_SERVICE': ''}):
            self.assertFalse(online.sending_available())
            with self.assertRaises(online.ServiceError):
                online.status()
        with patch.dict(os.environ, {'RETRO_RECOMP_SERVICE': 'file:///etc'}):
            self.assertFalse(online.sending_available())
        self.assertTrue(online.sending_available())
        self.assertTrue(online.status()['accepting'])

    def test_a_large_first_send_leaves_as_several_files(self):
        games = {('%064x' % number): f'Game {number}' for number in range(6)}
        rows = [[2, 0x4000 + n, 1, 3, 0x1234 + n] for n in range(400)]
        everything = collected(rows=rows, games=games)
        self.sign_in()
        with patch.object(online, 'PART_BYTES', 30000):
            result = online.send(online.pending(everything))
        uploads = [call for call in self.server.calls if call[1].endswith('/contributions')]
        self.assertGreater(len(uploads), 1)
        self.assertEqual(result['games'], 6)
        self.assertEqual(result['files'], len(uploads))
        sent = set()
        for call in uploads:
            document = json.loads(gzip.decompress(call[3]))
            self.assertLess(len(gzip.decompress(call[3])), 30000 * 2)
            sent |= set(document['titles']['gb'])
        self.assertEqual(sent, set(games))
        self.assertEqual(online.pending(everything)['games'], 0)

    def test_player_corner_is_cached_and_the_portrait_downloaded_once(self):
        self.sign_in()
        calls = []
        portrait = {'url': '/avatars/' + 'a' * 32 + '.webp'}
        def profile():
            calls.append('profile')
            return {'pseudonym': 'Pat', 'avatar': {'state': 'approved', 'url': portrait['url']}}
        def board(period='all'):
            calls.append('board')
            return {'you': {'rank': 2, 'total': 40, 'pending': 1}, 'entries': []}
        def avatar():
            calls.append('avatar')
            return b'RIFF portrait'
        with patch.object(online, 'profile', side_effect=profile), \
                patch.object(online, 'board', side_effect=board), \
                patch.object(online, 'avatar', side_effect=avatar):
            first = online.player(now=1000)
            self.assertEqual(calls, ['profile', 'board', 'avatar'])
            self.assertEqual(first['avatar'], b'RIFF portrait')
            # Reopening within 30 minutes: no request at all.
            again = online.player(now=1000 + 60)
            self.assertEqual(calls, ['profile', 'board', 'avatar'])
            self.assertEqual((again['profile']['pseudonym'], again['avatar']), ('Pat', b'RIFF portrait'))
            self.assertEqual(online.cached_player()['board']['you']['rank'], 2)
            # Stale: profile and score again, but the same portrait is not downloaded.
            online.player(now=1000 + online.PLAYER_REFRESH + 1)
            self.assertEqual(calls[3:], ['profile', 'board'])
            # A new portrait on the site (new public name): downloaded once more.
            portrait['url'] = '/avatars/' + 'b' * 32 + '.webp'
            online.player(force=True, now=9999)
            self.assertEqual(calls[5:], ['profile', 'board', 'avatar'])
        online.sign_out()
        self.assertIsNone(online.cached_player())
        self.assertFalse((self.data / online.AVATAR_NAME).exists())

    def test_plain_http_only_for_a_local_test_service(self):
        for url, kept in (('https://retro-recomp.com', True), ('http://127.0.0.1:8080', True),
                          ('http://192.168.1.13:8080', True), ('http://beta.test', True),
                          ('http://retro-recomp.com', False), ('http://8.8.8.8', False),
                          ('ftp://retro-recomp.com', False), ('https://', False)):
            with patch.dict(os.environ, {'RETRO_RECOMP_SERVICE': url}):
                self.assertEqual(bool(online.service_url()), kept, url)

    def test_the_token_never_follows_a_redirect(self):
        class Redirect(FakeService):
            def do_GET(self):
                self.server.calls.append(('GET', self.path, self.headers.get('Authorization')))
                self.send_response(302)
                self.send_header('Location', 'http://127.0.0.1:9/api/v1/account')
                self.send_header('Content-Length', '0')
                self.end_headers()
        server = ThreadingHTTPServer(('127.0.0.1', 0), Redirect)
        server.calls = []
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        with patch.dict(os.environ, {'RETRO_RECOMP_SERVICE': f'http://127.0.0.1:{server.server_address[1]}'}), \
                patch.object(online, 'account', return_value={'token': 'rr1_' + 'b' * 43, 'service': ''}):
            with self.assertRaises(online.ServiceError):
                online.profile()
        self.assertEqual(len(server.calls), 1)

    def test_sign_in_keeps_a_token_bound_to_its_service(self):
        with self.assertRaises(online.ServiceError) as caught:
            online.sign_in('p@example.test', '000000')
        self.assertEqual(caught.exception.reason, 'invalid_code')
        self.assertIsNone(online.account())
        self.sign_in()
        request = json.loads(self.server.calls[1][3])
        self.assertEqual(request, {'email': 'p@example.test', 'language': 'fr', 'accept_terms': True})
        self.assertEqual(online.account()['email'], 'p@example.test')
        with patch.dict(os.environ, {'RETRO_RECOMP_SERVICE': 'https://other.example.test'}):
            self.assertIsNone(online.account())
        online.sign_out()
        self.assertEqual(self.server.calls[-1][0], 'DELETE')
        self.assertEqual(self.server.calls[-1][2], 'Bearer rr1_' + 'a' * 43)
        self.assertIsNone(online.account())
        self.assertFalse((self.data / 'account.json').exists())

    def test_upload_is_the_rom_free_file_and_marks_only_after_success(self):
        self.sign_in()
        found = collected()
        self.assertEqual(online.pending(found)['games'], 1)
        self.server.mode = 'fail'
        with self.assertRaises(online.ServiceError):
            online.send(online.pending(found))
        self.assertEqual(online.pending(found)['games'], 1, 'a failed upload stays pending')
        self.server.mode = 'ok'
        result = online.send(online.pending(found))
        self.assertEqual((result['games'], result['id']), (1, 7))
        sent = [call for call in self.server.calls if call[1].endswith('/contributions')][-1]
        self.assertEqual(sent[2], 'Bearer rr1_' + 'a' * 43)
        path = Path(self.temp.name) / 'sent.rrknowledge'
        path.write_bytes(sent[3])
        document = knowledge_exchange.read_exchange(path)
        self.assertEqual(document['observations'], {'gb': {SHA: [[2, 0x4000, 1, 3, 0x1234]]}})
        self.assertEqual(document['titles'], {'gb': {SHA: 'Super Mario Land'}})
        self.assertEqual(online.pending(found)['games'], 0)
        self.assertEqual(knowledge_exchange.pending_since_shared('file', found), [f'gb:{SHA}'],
                         'sending does not count as a file export')
        self.assertFalse(list((self.data / 'knowledge').glob('upload-*')), 'no temporary file left')
        # Only what changed goes next time.
        more = collected(games={SHA: 'Super Mario Land', OTHER: 'Tetris'})
        self.assertEqual(sorted(online.pending(more)['titles']['gb']), [OTHER])

    def test_claims_follow_the_upload_with_its_scan_levels(self):
        self.sign_in()
        found = collected()
        found['levels'] = {'gb': {SHA: 'thorough'}, 'md': {OTHER: 'quick'}}
        pending = online.pending(found)
        self.assertEqual(pending['levels'], {'gb': {SHA: 'thorough'}}, 'only the games sent')
        result = online.send(pending)
        upload, claims = self.server.calls[-2], self.server.calls[-1]
        self.assertTrue(upload[1].endswith('/contributions'))
        self.assertTrue(claims[1].endswith('/contributions/7/claims'))
        self.assertEqual(claims[2], 'Bearer rr1_' + 'a' * 43)
        # The claimed keys are those of the exact file sent, as the maintainer reads it.
        path = Path(self.temp.name) / 'sent.rrknowledge'
        path.write_bytes(upload[3])
        paths = knowledge_exchange.discovery_paths(knowledge_exchange.read_exchange(path))
        self.assertEqual(json.loads(claims[3]), {'games': [{
            'system': 'gb', 'identity': SHA, 'known': False, 'level': 'thorough', 'hints': [],
            'observations': paths[('gb', SHA)]['observations']}]})
        self.assertEqual(result['claims'], {'games': 1, 'paths': 1, 'new': 1})
        self.assertFalse(any(call[1].endswith('/levels') for call in self.server.calls))
        self.assertNotIn(b'thorough', gzip.decompress(upload[3]), 'the shared file keeps its format')

    def test_an_older_server_without_claims_still_gets_the_scan_levels(self):
        self.sign_in()
        self.server.claims = 'missing'
        found = collected()
        found['levels'] = {'gb': {SHA: 'thorough'}}
        result = online.send(online.pending(found))
        claims, levels = self.server.calls[-2], self.server.calls[-1]
        self.assertTrue(claims[1].endswith('/contributions/7/claims'))
        self.assertTrue(levels[1].endswith('/contributions/7/levels'))
        self.assertEqual(json.loads(levels[3]), {'levels': {f'gb:{SHA}': 'thorough'}})
        self.assertIsNone(result['claims'])
        self.assertEqual(online.waiting_claims(), 0, 'nothing waits for a server without claims')
        self.assertEqual(online.pending(found)['games'], 0)

    def test_offline_and_revoked_uploads(self):
        self.sign_in()
        self.server.mode = 'revoked'
        with self.assertRaises(online.ServiceError):
            online.send(online.pending(collected()))
        self.assertIsNone(online.account(), 'a revoked token is forgotten')
        self.sign_in()
        self.server.shutdown()
        self.server.server_close()
        with self.assertRaises(online.ServiceConnectionError):
            online.send(online.pending(collected()))
        self.assertEqual(online.pending(collected())['games'], 1)
        online.sign_out()   # still forgets the token while offline
        self.assertIsNone(online.account())
        # tearDown stops a running server.
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), FakeService)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def test_send_requires_an_account(self):
        with self.assertRaises(online.ServiceError) as caught:
            online.send(collected())
        self.assertEqual(caught.exception.status, 401)

    def test_file_export_without_channel_marks_nothing(self):
        found = collected()
        knowledge_exchange.write_knowledge(found, Path(self.temp.name) / 'x.rrknowledge', channel=None)
        self.assertEqual(knowledge_exchange.pending_since_shared('file', found), [f'gb:{SHA}'])
        knowledge_exchange.write_knowledge(found, Path(self.temp.name) / 'y.rrknowledge')
        self.assertEqual(knowledge_exchange.pending_since_shared('file', found), [])


if __name__ == '__main__':
    unittest.main()
