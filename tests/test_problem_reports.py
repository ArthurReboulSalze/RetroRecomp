"""Problem reports: what is scrubbed, how much is sent, who may send, the body.

A local fake service stands in for the site (tests/test_online.py); the
contract is the `POST reports` body of Retro-Recomp 1.5.2.
"""
from http.server import ThreadingHTTPServer
import gzip
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from retrorecomp import __version__, online
from tests.test_online import SHA, FakeService

# The drive is spelled apart: the publication check refuses a literal private path.
DRIVE = 'C' + ':'
HOME = DRIVE + '\\Users\\Zelda Player'
GAMES = 'D:\\Retro\\Export\\Games'
ROMS = '\\\\nas\\roms\\snes'
ROOTS = (('<games>', GAMES), ('<rom>', ROMS))


class PrivateData(unittest.TestCase):
    def setUp(self):
        for item in (patch('pathlib.Path.home', return_value=Path(HOME)),
                     patch.dict(os.environ, {'USERNAME': 'zeldaplayer', 'USER': 'zeldaplayer',
                                             'LOGNAME': 'zeldaplayer', 'LNAME': 'zeldaplayer'})):
            item.start()
            self.addCleanup(item.stop)

    def test_home_user_paths_and_emails_become_placeholders(self):
        text = '\n'.join((
            f'open {HOME}\\AppData\\Local\\Temp\\build.log failed',
            DRIVE.lower() + '/users/zelda player/Documents/rom.sfc (lower case, forward slashes)',
            f"repr: '{HOME.replace(chr(92), chr(92) * 2)}\\\\x.c'",
            f'{GAMES}\\Super Nintendo\\Mario.exe and {GAMES.replace(chr(92), "/")}/Super Nintendo/datas',
            f'{ROMS}\\Mario (USA).sfc',
            'also \\\\other\\share\\file.bin, D:\\Elsewhere\\notes.txt, /home/zelda/x.log, /mnt/nas/rom.sms.',
            'player zeldaplayer wrote to zelda.player+rr@example.com and ZELDA@Mail.Example.org',
            'kept: https://retro-recomp.com/api/v1/reports, a/b relative, ratio 3:4, /frame/12'))
        clean = online.scrub(text, ROOTS)
        for secret in ('Zelda Player', 'zelda player', 'zeldaplayer', 'zelda.player', 'ZELDA@', 'D:\\Retro',
                       'D:/Retro', 'nas\\roms', '\\\\other', 'D:\\Elsewhere', '/home/zelda', '/mnt/nas',
                       'example.com', 'example.org', 'C:\\Users'):
            self.assertNotIn(secret, clean, secret)
        for placeholder in ('<home>', '<games>', '<rom>', '<path>', '<email>', '<user>'):
            self.assertIn(placeholder, clean, placeholder)
        self.assertIn('<games>\\Super Nintendo\\Mario.exe', clean)
        self.assertIn('<rom>\\Mario (USA).sfc', clean)
        # What is not private stays readable.
        self.assertIn('https://retro-recomp.com/api/v1/reports', clean)
        self.assertIn('ratio 3:4', clean)
        self.assertIn('/frame/12', clean)
        self.assertIn('<path>/file.bin', clean, 'the file name of an unknown path helps and stays')

    def test_nested_data_is_scrubbed_in_values_and_keys(self):
        data = {'rom': {'name': 'Mario (USA).sfc', 'path': f'{ROMS}\\Mario.sfc'},
                'checks': [{'log': f'{HOME}\\x', 'frames': 3600, 'ok': True, 'none': None}],
                f'{HOME}\\key': 'value'}
        clean = online.scrub(data, ROOTS)
        self.assertEqual(clean['rom'], {'name': 'Mario (USA).sfc', 'path': '<rom>\\Mario.sfc'})
        self.assertEqual(clean['checks'], [{'log': '<home>\\x', 'frames': 3600, 'ok': True, 'none': None}])
        self.assertEqual(clean['<home>\\key'], 'value')
        self.assertNotIn('Zelda', json.dumps(clean))

    def test_a_short_user_name_is_not_replaced_in_the_text(self):
        with patch.dict(os.environ, {'USERNAME': 'al', 'USER': 'al', 'LOGNAME': 'al', 'LNAME': 'al'}), \
                patch('pathlib.Path.home', return_value=Path('C:\\Users\\al')):
            self.assertEqual(online.scrub('al al-Z80 ball'), 'al al-Z80 ball')


class Limits(unittest.TestCase):
    def build(self, **parts):
        return online.build_report('conversion', game={'system': 'snes', 'identity': SHA, 'title': 'Mario'}, **parts)

    def test_error_log_message_and_fields_stay_within_their_limits(self):
        log = '\n'.join(f'line {number:06d} ' + 'x' * 70 for number in range(5000))   # about 400 KiB
        report = {'version': '1.5.1', 'status': 'ok', 'artwork': {'image': 'C:\\private\\a.png'},
                  'build_executable': 'C:\\private\\game.exe', 'published_directory': 'C:\\private',
                  'windows_metadata': {'CompanyName': 'x'},
                  'rom': {'name': 'Mario.sfc', 'sha256': SHA, 'path': 'C:\\private\\Mario.sfc'},
                  'reference_vdp_trace_match': True,
                  'history': [{'frames': number, 'text': 'h' * 100} for number in range(2000)],
                  'final_checks': [{'scenario': 'demo', 'interpreted_opcodes': 0}]}
        body = self.build(error='e' * 10000 + '\nsecond line', log=log, report=report, message='m' * 10000)
        self.assertLessEqual(len(body['error'].encode()), online.REPORT_ERROR_LIMIT)
        self.assertEqual(body['error'][:3], 'eee', 'the start of an error is kept')
        self.assertLessEqual(len(body['log'].encode()), online.REPORT_LOG_LIMIT)
        self.assertTrue(body['log'].endswith('line 004999 ' + 'x' * 70), 'the end of the log is kept')
        self.assertTrue(body['log'].startswith('line '), 'from a whole line')
        self.assertLessEqual(len(body['message'].encode()), online.REPORT_MESSAGE_LIMIT)
        fields = body['report']
        self.assertLessEqual(len(json.dumps(fields).encode()), online.REPORT_FIELDS_LIMIT)
        for private in ('artwork', 'build_executable', 'published_directory', 'windows_metadata'):
            self.assertNotIn(private, fields)
        self.assertEqual(fields['rom'], {'name': 'Mario.sfc', 'sha256': SHA})
        self.assertIs(fields['reference_vdp_trace_match'], True)
        self.assertNotIn('history', fields, 'the bulkiest field goes first')
        self.assertIn('final_checks', fields)
        self.assertLess(len(json.dumps(body).encode()), 256 * 1024)

    def test_multibyte_text_is_cut_on_a_character(self):
        body = self.build(error='é' * 5000, log='日本語\n' * 40000, message='ü' * 5000)
        for key, limit in (('error', online.REPORT_ERROR_LIMIT), ('log', online.REPORT_LOG_LIMIT),
                           ('message', online.REPORT_MESSAGE_LIMIT)):
            self.assertLessEqual(len(body[key].encode('utf-8')), limit)
            self.assertNotIn('\ufffd', body[key])

    def test_the_whole_body_fits_even_when_escaped_text_grows_it(self):
        # Emoji travel as 12 bytes of JSON escapes for 4 bytes of text: the
        # service refuses (never truncates) a body above 256 KiB.
        face = '\U0001F600'
        body = self.build(error=face * 1000, log=('x' + face * 40 + '\n') * 400,
                          report={'status': 'ok', 'history': [face * 5000], 'final_checks': [face * 5000]},
                          message=face * 1000)
        self.assertLessEqual(len(json.dumps(body, separators=(',', ':')).encode()), online.REPORT_BODY_LIMIT)
        self.assertLessEqual(len(body['error'].encode()), online.REPORT_ERROR_LIMIT)
        self.assertLessEqual(len(body['message'].encode()), online.REPORT_MESSAGE_LIMIT)
        self.assertLessEqual(len(json.dumps(body['report'], separators=(',', ':')).encode()),
                             online.REPORT_FIELDS_LIMIT, 'measured as it travels, escapes included')
        self.assertTrue(body['log'].endswith(face + '\n') or body['log'].endswith(face), 'the end of the log stays')

    def test_the_body_has_the_contract_shape(self):
        body = self.build(error='Compilation failed', log='a\nb', report={'status': 'experimental'})
        self.assertEqual(sorted(body), ['converter', 'error', 'game', 'kind', 'language', 'log', 'message',
                                        'platform', 'report'])
        self.assertEqual((body['kind'], body['converter'], body['language'], body['message']),
                         ('conversion', __version__, 'en', ''))
        self.assertIn(body['platform'], ('windows-x64', 'linux-x86_64', 'windows-arm64', 'linux-arm64'))
        self.assertEqual(body['game'], {'system': 'snes', 'identity': SHA, 'title': 'Mario'})
        self.assertEqual(body['report'], {'status': 'experimental'})

    def test_a_game_without_a_valid_identity_is_left_out_and_named_in_the_error(self):
        body = online.build_report('conversion', game={'system': '', 'identity': '', 'title': 'Unknown thing'},
                                   error='Unrecognized file')
        self.assertIsNone(body['game'])
        self.assertEqual(body['error'], 'Unknown thing: Unrecognized file')
        self.assertEqual((body['log'], body['report']), (None, None))

    def test_a_free_text_report_needs_its_message_and_may_have_no_game(self):
        with self.assertRaises(ValueError):
            online.build_report('manual', message='   ')
        body = online.build_report('manual', message='  The menu overlaps  ', language='fr')
        self.assertEqual((body['kind'], body['game'], body['error'], body['log'], body['report'], body['message'],
                          body['language']), ('manual', None, None, None, None, 'The menu overlaps', 'fr'))
        with self.assertRaises(ValueError):
            online.build_report('crash')

    def test_the_players_message_is_scrubbed_too(self):
        body = online.build_report('manual', message='write me at me@example.com')
        self.assertEqual(body['message'], 'write me at <email>')


class Sending(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data = Path(self.temp.name) / 'datas'
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), FakeService)
        self.server.calls, self.server.mode, self.server.claims = [], 'ok', 'ok'
        self.server.store, self.server.encodings = {}, []
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f'http://127.0.0.1:{self.server.server_address[1]}'
        self.patches = [patch.dict(os.environ, {'RETRO_RECOMP_SERVICE': self.url}),
                        patch('retrorecomp.paths.data_directory', return_value=self.data)]
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
        online.sign_in('p@example.test', '123456', 'Retro-Recomp test')

    def reports(self):
        return [call for call in self.server.calls if call[1].endswith('/reports')]

    def test_sending_requires_an_account_and_sends_nothing_without_one(self):
        with self.assertRaises(online.ServiceError) as caught:
            online.send_report('manual', message='hello')
        self.assertEqual(caught.exception.status, 401)
        self.assertFalse(self.reports())

    def test_a_signed_in_player_posts_the_scrubbed_body_with_the_token(self):
        self.sign_in()
        identifier = online.send_report(
            'conversion', game={'system': 'snes', 'identity': SHA, 'title': 'Mario'},
            error=f'Build failed in {Path.home()}\\x', log='one\ntwo', report={'status': 'experimental'},
            message='It crashes at start', language='fr')
        self.assertEqual(identifier, 7)
        (call,) = self.reports()
        self.assertEqual((call[0], call[2]), ('POST', 'Bearer rr1_' + 'a' * 43))
        body = json.loads(call[3])
        self.assertEqual(body['kind'], 'conversion')
        self.assertEqual(body['language'], 'fr')
        self.assertEqual(body['message'], 'It crashes at start')
        self.assertEqual(body['game']['identity'], SHA)
        self.assertNotIn(Path.home().name, body['error'])
        self.assertIn('<home>', body['error'])
        self.assertFalse(getattr(self.server, 'packed', []), 'a small report is not compressed')

    def test_a_large_report_leaves_gzipped_within_the_service_cap(self):
        self.sign_in()
        log = '\n'.join(f'line {number:06d} ' + 'x' * 70 for number in range(5000))
        online.send_report('manual', message='long', log=log, report={'history': ['y' * 50000]})
        self.assertEqual(len(getattr(self.server, 'packed', [])), 1)
        body = json.loads(self.reports()[0][3])
        self.assertLess(len(json.dumps(body).encode()), 256 * 1024)
        self.assertLessEqual(len(body['log'].encode()), online.REPORT_LOG_LIMIT)

    def test_the_services_refusals_come_back_with_their_reasons(self):
        self.sign_in()
        for mode, status, reason in (('limited', 429, 'rate_limited'), ('large', 413, 'too_large'),
                                     ('invalid', 400, 'invalid_report')):
            self.server.mode = mode
            with self.assertRaises(online.ServiceError) as caught:
                online.send_report('manual', message='hello')
            self.assertEqual((caught.exception.status, caught.exception.reason), (status, reason))
            self.assertIsNotNone(online.account(), 'a refusal does not sign the player out')

    def test_a_revoked_token_is_forgotten(self):
        self.sign_in()
        self.server.mode = 'revoked'
        with self.assertRaises(online.ServiceError) as caught:
            online.send_report('manual', message='hello')
        self.assertEqual(caught.exception.status, 401)
        self.assertIsNone(online.account())

    def test_an_unreachable_service_is_a_connection_error(self):
        self.sign_in()
        self.server.shutdown()
        self.server.server_close()
        with self.assertRaises(online.ServiceConnectionError):
            online.send_report('manual', message='hello')


if __name__ == '__main__':
    unittest.main()
