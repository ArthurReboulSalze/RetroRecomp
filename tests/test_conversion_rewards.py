"""The converter's side of the conversion rewards and of the pseudonym asked at
sign-in (26 October 2026; the server side is web/lib/rewards.php of the site).

A game the bundled snapshot knows is rebuilt from its paths and brings nothing
new; each successful conversion made while signed in is noted, and the next
send carries the noted games (a record without hints when nothing is new) and
claims them as converted, with their level. A local fake service stands in
for the site (tests/test_online.py).
"""
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from retrorecomp import knowledge_exchange, online
from retrorecomp.compiled_games import Game, report_level
from tests.test_online import OTHER, SHA, FakeService, collected

ENGINE = 'd' * 40


class RewardService(FakeService):
    """FakeService plus the account's pseudonym, GET explored and claims that
    count the games said converted."""
    def do_GET(self):
        self.server.calls.append(('GET', self.path, self.headers.get('Authorization')))
        if self.path.endswith('/explored'):
            self.answer(200, {'games': {f'gb:{SHA}': {'by': 'Deep_Diver'}, 'bogus': {'by': 'x'}},
                              'explorer': 60, 'depth': {'extended': 20, 'thorough': 40}})
        else:
            super().do_GET()

    def do_PATCH(self):
        data = self.body()
        self.server.calls.append(('PATCH', self.path, self.headers.get('Authorization'), data))
        name = json.loads(data)['pseudonym']
        if name == 'Taken_Name':
            self.answer(409, {'error': 'pseudonym_taken'})
        else:
            self.answer(200, {'email': 'p@example.test', 'pseudonym': name, 'pseudonym_chosen': True})

    def do_POST(self):
        if self.path.endswith('/auth/token'):
            data = self.body()
            self.server.calls.append(('POST', self.path, None, data))
            name = json.loads(data).get('pseudonym')
            if name == 'Taken_Name':
                self.answer(409, {'error': 'pseudonym_taken'})
            else:
                self.answer(200, {'token': 'rr1_' + 'a' * 43, 'account': {
                    'email': 'p@example.test', 'pseudonym': name or 'RetroPlayer_123456', 'pseudonym_chosen': bool(name)}})
            return
        super().do_POST()

    def claims(self, data):
        games = json.loads(data)['games']
        paths = sum(len(game['hints']) + len(game['observations']) for game in games)
        self.answer(200, {'games': len(games), 'paths': paths, 'new': paths,
                          'converted': sum(1 for game in games if game.get('converted') is True)})


def known_game(identity, level='standard', title='Known Game'):
    return {'engine': ENGINE, 'rom_bytes': 0x8000, 'level': level, 'title': title}


class ConversionRewardTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.data = self.root / 'datas'
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), RewardService)
        self.server.calls, self.server.mode, self.server.claims = [], 'ok', 'ok'
        self.server.store, self.server.encodings = {}, []
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        bank = self.data / 'knowledge/imported.json.gz'
        for item in (patch.dict(os.environ, {'RETRO_RECOMP_SERVICE': f'http://127.0.0.1:{self.server.server_address[1]}'}),
                     patch('retrorecomp.paths.data_directory', return_value=self.data),
                     patch('retrorecomp.knowledge.imported_path', return_value=bank),
                     patch('retrorecomp.knowledge_exchange.imported_path', return_value=bank)):
            item.start()
            self.addCleanup(item.stop)

    def calls(self, suffix):
        return [call for call in self.server.calls if call[1].endswith(suffix)]

    # --- The pseudonym at sign-in ------------------------------------------------

    def test_the_pseudonym_goes_with_the_code_and_a_taken_one_is_refused(self):
        with self.assertRaises(online.ServiceError) as raised:
            online.sign_in('p@example.test', '123456', 'test', pseudonym='Taken_Name')
        self.assertEqual((raised.exception.status, raised.exception.reason), (409, 'pseudonym_taken'))
        self.assertIsNone(online.account())
        data = online.sign_in('p@example.test', '123456', 'test', pseudonym='  My   Name ')
        self.assertEqual(json.loads(self.calls('/auth/token')[-1][3])['pseudonym'], 'My   Name')
        self.assertEqual((data['pseudonym'], data['pseudonym_chosen']), ('My   Name', True))

    def test_without_one_the_server_generates_it_and_it_can_be_chosen_later(self):
        data = online.sign_in('p@example.test', '123456', 'test')
        self.assertNotIn('pseudonym', json.loads(self.calls('/auth/token')[-1][3]), 'a 1.5.2 request')
        self.assertFalse(data['pseudonym_chosen'])
        self.assertFalse(online.pseudonym_chosen({'pseudonym_chosen': False}))
        self.assertTrue(online.pseudonym_chosen({}), 'an older server says nothing: nothing is asked')
        with self.assertRaises(online.ServiceError):
            online.set_pseudonym('Taken_Name')
        details = online.set_pseudonym('Chosen  One')
        self.assertEqual(json.loads(self.calls('/account')[-1][3]), {'pseudonym': 'Chosen One'})
        self.assertEqual((details['pseudonym'], online.account()['pseudonym'], online.account()['pseudonym_chosen']),
                         ('Chosen One', 'Chosen One', True))

    def test_the_proposed_pseudonym_follows_the_server_rules(self):
        proposed = online.suggested_pseudonym()
        self.assertRegex(proposed, r'^RetroPlayer_\d{4}$')
        self.assertTrue(online.valid_pseudonym(proposed))
        for bad in ('ab', '<script>', '_edge', 'x' * 33, 'end.'):
            self.assertFalse(online.valid_pseudonym(bad), bad)
        self.assertTrue(online.valid_pseudonym('Élodie 2'))

    # --- Conversions noted, then sent and claimed ------------------------------

    def test_a_known_game_converted_travels_as_a_record_without_hints_and_is_claimed(self):
        self.assertFalse(online.note_conversion('gb', SHA), 'nothing without an account')
        online.sign_in('p@example.test', '123456', 'test')
        self.assertTrue(online.note_conversion('gb', SHA))
        self.assertFalse(online.note_conversion('x68', SHA), 'a console the service does not take')
        self.assertEqual(online.noted_conversions(), [f'gb:{SHA}'])
        found = {**collected(games={OTHER: 'Tetris'}), 'levels': {},
                 'converted': {'gb': {SHA: known_game(SHA, 'thorough', 'Super Mario Land')}}}
        pending = online.pending(found)
        self.assertEqual((pending['games'], pending['converted_keys']), (2, [f'gb:{SHA}']))
        self.assertEqual(pending['payload']['consoles']['gb'][SHA], {'engine': ENGINE, 'rom_bytes': 0x8000})
        result = online.send(pending)
        upload, claims = self.calls('/contributions')[-1], self.calls('/claims')[-1]
        path = self.root / 'sent.rrknowledge'
        path.write_bytes(upload[3])
        document = knowledge_exchange.read_exchange(path)
        self.assertEqual(document['titles']['gb'][SHA], 'Super Mario Land')
        games = {game['identity']: game for game in json.loads(claims[3])['games']}
        self.assertEqual(games[SHA], {'system': 'gb', 'identity': SHA, 'known': False, 'level': 'thorough',
                                      'hints': [], 'observations': [], 'converted': True})
        self.assertNotIn('converted', games[OTHER])
        self.assertEqual(result['claims']['converted'], 1)
        self.assertEqual(online.noted_conversions(), [], 'sent once')
        self.assertEqual(online.pending(found)['games'], 0)

    def test_a_noted_game_with_new_hints_is_flagged_and_a_send_is_bounded(self):
        online.sign_in('p@example.test', '123456', 'test')
        found = collected(games={OTHER: 'Tetris'})
        found['payload'] = {'schema': 1, 'consoles': {'gb': {SHA: {'engine': ENGINE, 'rom_bytes': 0x8000,
                                                                    'rom_entries': [[0, 0x150]]}}}}
        found['titles']['gb'][SHA] = 'Super Mario Land'
        found['levels'] = {'gb': {SHA: 'extended'}}
        online.note_conversion('gb', SHA)
        online.note_conversion('gb', OTHER)
        pending = online.pending(found)
        self.assertEqual(pending['converted_keys'], [f'gb:{SHA}'],
                         'a record with new hints is flagged; raw observations alone are no conversion')
        online.send(pending)
        games = {game['identity']: game for game in json.loads(self.calls('/claims')[-1][3])['games']}
        self.assertEqual((games[SHA]['converted'], games[SHA]['level']), (True, 'extended'))
        self.assertEqual(online.noted_conversions(), [f'gb:{OTHER}'], 'a game not sent stays noted')
        identities = [f'{number:064x}' for number in range(online.CONVERTED_PER_SEND + 5)]
        for identity in identities:
            online.note_conversion('md', identity)
        found = {**collected(), 'converted': {'md': {identity: known_game(identity) for identity in identities}}}
        pending = online.pending(found)
        self.assertEqual(len(pending['payload']['consoles']['md']), online.CONVERTED_PER_SEND)
        online.send(pending)
        self.assertEqual(len([key for key in online.noted_conversions() if key.startswith('md:')]), 5,
                         'the rest waits for the next send')

    def test_a_refused_upload_keeps_the_notes(self):
        online.sign_in('p@example.test', '123456', 'test')
        online.note_conversion('gb', SHA)
        self.server.mode = 'fail'
        with self.assertRaises(online.ServiceError):
            online.send(online.pending({**collected(games={OTHER: 'Tetris'}),
                                        'converted': {'gb': {SHA: known_game(SHA)}}}))
        self.assertEqual(online.noted_conversions(), [f'gb:{SHA}'])

    # --- Games to explore ---------------------------------------------------------

    def test_explored_games_are_asked_at_most_every_half_hour(self):
        first = online.explored(now=100)
        self.assertEqual(first['games'], {f'gb:{SHA}': 'Deep_Diver'})
        self.assertEqual((first['explorer'], first['depth']), (60, {'extended': 20, 'thorough': 40}))
        self.assertEqual(online.explored(now=100 + online.SHOP_REFRESH - 1)['games'], first['games'])
        self.assertEqual(len(self.calls('/explored')), 1)
        online.explored(now=100 + online.SHOP_REFRESH + 1)
        self.assertEqual(len(self.calls('/explored')), 2)
        with patch.object(online, '_call', side_effect=online.ServiceConnectionError()):
            self.assertEqual(online.explored(force=True)['games'], first['games'], 'offline: the last answer')

    def test_report_levels_count_only_discoveries(self):
        self.assertEqual(report_level({'scan_level': 'thorough'}), 'thorough')
        self.assertEqual(report_level({'scan_level': 'quick', 'shared_paths': {'level': 'thorough', 'quick': True}}),
                         'standard', 'a quick check from shared paths is not a Thorough discovery')
        self.assertEqual(report_level({'scan_level': 'quick', 'upgrade': {'discovery': {'scan_level': 'extended'}}}),
                         'extended', 'an upgraded export keeps the discovery it inherits')
        self.assertEqual(report_level({}), 'standard')
        self.assertEqual(Game('x', 'gb', SHA, 'T').level, '')


if __name__ == '__main__':
    unittest.main()
