"""The shared base around a batch: its paths fetched before, claims sent after.

A local fake service stands in for the site (tests/test_online.py). Fetched
records and observations join the imported banks and are checked again by
every conversion; a quick check replaces discovery only when the shared
level covers the level asked for the console.
"""
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
from queue import Queue
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from retrorecomp import knowledge, knowledge_exchange, online
from retrorecomp.batch import convert_batch, identify
from retrorecomp.core import ConversionError
from tests.test_online import OTHER, SHA, FakeService, collected

ENGINE = 'c' * 40
EXT = '.exe' if os.name == 'nt' else ''


def sms_record(*addresses):
    """A valid Master System record for an 8 KiB cartridge."""
    return {'engine': ENGINE, 'rom_bytes': 8192, 'rom_entries': [[address, 0, 0, 0, 1] for address in addresses]}


def calls_to(server, suffix):
    return [call for call in server.calls if call[1].endswith(suffix)]


class SharedBaseTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.data = self.root / 'datas'
        self.bank = self.data / 'knowledge/imported.json.gz'
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), FakeService)
        self.server.calls, self.server.mode, self.server.claims = [], 'ok', 'ok'
        self.server.store, self.server.encodings = {}, []
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.stop_server)
        self.url = f'http://127.0.0.1:{self.server.server_address[1]}'
        for item in (patch.dict(os.environ, {'RETRO_RECOMP_SERVICE': self.url}),
                     patch('retrorecomp.paths.data_directory', return_value=self.data),
                     patch('retrorecomp.knowledge.imported_path', return_value=self.bank),
                     patch('retrorecomp.knowledge_exchange.imported_path', return_value=self.bank),
                     # Synthetic executables are not PE files.
                     patch('retrorecomp.publishing.compact_executable')):
            item.start()
            self.addCleanup(item.stop)
        self.addCleanup(knowledge._imported_bank.cache_clear)
        self.addCleanup(knowledge._observation_bank.cache_clear)
        online.request_code('p@example.test', 'en')
        online.sign_in('p@example.test', '123456', 'Retro-Recomp test')

    def stop_server(self):
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.server = None

    def cartridge(self, value=1):
        folder = self.root / 'ROMS'
        folder.mkdir(exist_ok=True)
        path = folder / f'Shared {value} (Europe).sms'
        path.write_bytes(bytes([value]) * 8192)
        return identify(path)

    def compiler(self, path, *, output, title, **options):
        output.mkdir(parents=True, exist_ok=True)
        executable = output / ('Shared' + EXT)
        executable.write_bytes(path.read_bytes())
        (output / 'conversion-report.json').write_text(json.dumps({
            'executable': executable.name, 'rom': {'name': path.name}, 'video_model': {'standard': 'pal'},
            'final_checks': [{'interpreter_percent': 0}], 'reference_vdp_trace_match': True}))
        return executable

    def convert(self, item, compiler=None, **options):
        messages = []
        with patch('retrorecomp.systems.master_system.MasterSystemProfile.convert',
                   side_effect=compiler or self.compiler) as profile:
            record = convert_batch([item], self.root / 'Games', emit=messages.append, **options)
        report = self.root / 'Games/Master System/datas/reports' / item.key / 'conversion-report.json'
        return record, profile, json.loads(report.read_text(encoding='utf-8')) if report.is_file() else {}, messages

    # --- Before a batch ------------------------------------------------------

    def test_fetch_goes_by_128_roms_and_each_rom_keeps_its_cursor(self):
        keys = [f'sms:{number:064x}' for number in range(300)]
        self.server.store = {keys[0]: [{'id': 5, 'record': sms_record(0x100), 'level': 'standard'}],
                             keys[200]: [{'id': 9, 'rows': [[1, 0x200, 0, 3, 0x40]], 'level': 'quick'}]}
        summary = online.sync_shared(keys + ['x68:' + 'a' * 64, 'bogus'])
        fetches = calls_to(self.server, '/knowledge/fetch')
        self.assertEqual([len(json.loads(call[3])['roms']) for call in fetches], [128, 128, 44])
        self.assertEqual(sorted(key for call in fetches for key in json.loads(call[3])['roms']), keys,
                         'only the shared consoles, each ROM once')
        self.assertTrue(all(cursor == 0 for call in fetches for cursor in json.loads(call[3])['roms'].values()))
        self.assertEqual(self.server.encodings, ['gzip'] * 3, 'answers come gzipped')
        self.assertEqual({k: summary[k] for k in ('asked', 'roms', 'records', 'observations')},
                         {'asked': 300, 'roms': 2, 'records': 1, 'observations': 1})
        # Next time each ROM sends its own cursor and nothing comes back twice.
        self.server.calls.clear()
        self.assertEqual(online.sync_shared(keys)['roms'], 0)
        sent = {key: cursor for call in calls_to(self.server, '/knowledge/fetch')
                for key, cursor in json.loads(call[3])['roms'].items()}
        self.assertEqual((sent[keys[0]], sent[keys[200]], sent[keys[1]]), (5, 9, 0))
        # A newer contribution: only it is served, merged into the bank.
        self.server.store[keys[0]].append({'id': 12, 'record': sms_record(0x180), 'level': 'thorough'})
        self.assertEqual(online.sync_shared(keys[:1])['records'], 1)
        identity = keys[0].split(':')[1]
        self.assertEqual(knowledge.imported_record('sms', identity)['rom_entries'], [[0x100, 0, 0, 0, 1], [0x180, 0, 0, 0, 1]])
        self.assertEqual(online.shared_paths(keys[:1] + keys[200:201]), {
            keys[0]: {'level': 'thorough', 'records': 2}, keys[200]: {'level': 'quick', 'records': 0}})
        state = json.loads(self.bank.with_name('shared-cursors.json').read_text(encoding='utf-8'))
        self.assertEqual((state['service'], state['email'], state['roms'][keys[0]]['cursor']),
                         (self.url, 'p@example.test', 12))

    def test_a_rom_served_full_is_asked_again_from_its_new_cursor(self):
        identity = '12' * 32
        key = f'sms:{identity}'
        # 150 contributions: 64 per answer at most, so three rounds for this ROM only.
        self.server.store = {key: [{'id': n, 'record': sms_record(0x100 + n), 'level': 'thorough' if n == 3 else 'quick'}
                                   for n in range(1, 151)],
                             'sms:' + '34' * 32: [{'id': 1, 'record': sms_record(0x100), 'level': 'standard'}]}
        summary = online.sync_shared([key, 'sms:' + '34' * 32])
        rounds = [sorted(json.loads(call[3])['roms'].items()) for call in calls_to(self.server, '/knowledge/fetch')]
        self.assertEqual(rounds, [sorted({key: 0, 'sms:' + '34' * 32: 0}.items()), [(key, 64)], [(key, 128)]])
        self.assertEqual(summary['records'], 151)
        self.assertEqual(len(knowledge.imported_record('sms', identity)['rom_entries']), 150)
        # The best level of every round is kept with the last cursor.
        self.assertEqual(online.shared_paths([key]), {key: {'level': 'thorough', 'records': 150}})
        state = json.loads(self.bank.with_name('shared-cursors.json').read_text(encoding='utf-8'))
        self.assertEqual(state['roms'][key]['cursor'], 150)

    def test_large_claims_leave_in_parts_and_gzipped(self):
        games = {('%064x' % number): f'Game {number}' for number in range(5)}
        rows = [[2, 0x4000 + n, 1, 3, 0x1234 + n] for n in range(300)]
        with patch.object(online, 'CLAIM_BYTES', 12000), patch.object(online, 'GZIP_BODY', 2000):
            result = online.send_after_batch(lambda: collected(rows=rows, games=games))
        parts = calls_to(self.server, '/claims')
        self.assertGreater(len(parts), 1)
        self.assertEqual(sorted(game['identity'] for call in parts for game in json.loads(call[3])['games']),
                         sorted(games), 'each game once')
        self.assertTrue(all(len(call[3]) < 12000 * 1.2 for call in parts))
        self.assertEqual(self.server.packed, [call[1] for call in parts])
        self.assertEqual(result['claims'], {'games': 5, 'paths': 1500, 'new': 1500})

    def test_claims_refused_for_good_are_reported_not_kept(self):
        self.server.claims = 'refused'
        result = online.send_after_batch(lambda: collected())
        self.assertEqual((result['games'], result['claims'], result['claims_refused']), (1, None, ['refused']))
        self.assertEqual(online.waiting_claims(), 0)

    def test_fetched_paths_join_the_imported_banks_and_bad_ones_are_skipped(self):
        identity = 'ab' * 32
        key = f'sms:{identity}'
        self.server.store = {key: [
            {'id': 1, 'record': sms_record(0x100), 'rows': [[1, 0x300, 0, 2, 0x10], [1, 0x300, 0, 2, 0x10]]},
            {'id': 2, 'record': {'engine': 'not hex', 'rom_bytes': 8192}, 'rows': [[99, 1, 0, 2, 0], 'x']},
            {'id': 3, 'record': sms_record(0x100, 0x200), 'level': 'standard'}]}
        summary = online.sync_shared([key])
        self.assertEqual((summary['records'], summary['observations'], summary['new']), (2, 1, 1))
        self.assertEqual(knowledge.imported_record('sms', identity)['rom_entries'],
                         [[0x100, 0, 0, 0, 1], [0x200, 0, 0, 0, 1]])
        self.assertEqual(knowledge.imported_observations('sms', identity), [[1, 0x300, 0, 2, 0x10]])
        # The same file-free path as an import: nothing about titles or files.
        self.assertFalse(list(self.data.glob('knowledge/upload-*')))
        # A later manual import still merges with what the shared base gave.
        self.assertEqual(knowledge_exchange.import_fetched({key: {'records': [sms_record(0x200)]}})['unchanged'], 1)
        # One malformed row is left out alone; the record's other paths stay.
        mixed = sms_record(0x300)
        mixed['rom_entries'] += [[0xc000, 0, 0, 0, 1], [0x400, 0, 0, 'x', 1]]
        mixed['pattern_refs'] = [[8192]]
        accepted = knowledge_exchange.import_fetched({key: {'records': [mixed]}})['accepted'][key]
        self.assertEqual(accepted['records'], 1)
        self.assertEqual(knowledge.imported_record('sms', identity)['rom_entries'],
                         [[0x100, 0, 0, 0, 1], [0x200, 0, 0, 0, 1], [0x300, 0, 0, 0, 1]])
        self.assertNotIn('pattern_refs', knowledge.imported_record('sms', identity))

    def test_quick_check_only_when_the_shared_level_covers_the_asked_level(self):
        item = self.cartridge()
        key = f'sms:{item.sha256}'
        self.server.store = {key: [{'id': 4, 'record': sms_record(0x100), 'level': 'extended'}]}
        shared = online.prepare_batch([key])['paths']
        self.assertEqual(shared, {key: {'level': 'extended', 'records': 1}})
        record, profile, report, messages = self.convert(item, shared_paths=shared,
                                                         console_scan={'sms': {'level': 'standard'}})
        self.assertEqual(record['succeeded'], 1)
        options = profile.call_args.kwargs
        self.assertEqual((options['scan_level'], options['passes'], options['frames']), ('quick', 1, 1800))
        self.assertNotIn('shared_paths', options, 'never a compiler or request setting')
        self.assertEqual(report['shared_paths'], {'level': 'extended', 'records': 1, 'quick': True})
        self.assertEqual(record['games'][0]['shared_paths'], report['shared_paths'])
        self.assertTrue(any('shared paths, level extended: quick check instead of discovery' in m for m in messages))
        # A longer scan than the shared one: discovery at that level, from the shared paths.
        record, profile, report, messages = self.convert(item, shared_paths=shared,
                                                         console_scan={'sms': {'level': 'thorough'}})
        options = profile.call_args.kwargs
        self.assertEqual((options['scan_level'], options['passes']), ('thorough', 3))
        self.assertEqual(report['shared_paths'], {'level': 'extended', 'records': 1, 'quick': False})
        self.assertTrue(any('thorough discovery starting from them' in m for m in messages))
        # Forcing a conversion from the queue always rediscovers.
        record, profile, report, _ = self.convert(item, shared_paths=shared, force=True)
        self.assertNotIn('scan_level', profile.call_args.kwargs)
        self.assertFalse(report['shared_paths']['quick'])
        # Without shared paths the conversion is the usual one, with no mention.
        record, profile, report, _ = self.convert(item, force=True)
        self.assertNotIn('shared_paths', report)

    def test_a_failure_with_shared_paths_converts_again_without_them(self):
        item = self.cartridge(2)
        key = f'sms:{item.sha256}'
        self.server.store = {key: [{'id': 1, 'record': sms_record(0x100), 'level': 'standard'}]}
        shared = online.prepare_batch([key])['paths']
        seen = []

        def compiler(path, **options):
            hints = knowledge.imported_record('sms', item.sha256)
            seen.append((bool(hints), options.get('scan_level', 'standard')))
            if hints:
                raise ConversionError('reference mismatch')
            return self.compiler(path, **options)
        record, _, report, messages = self.convert(item, compiler, shared_paths=shared)
        self.assertEqual(seen, [(True, 'quick'), (False, 'standard')], 'the retry is a full discovery')
        self.assertEqual(record['succeeded'], 1)
        self.assertTrue(record['games'][0]['imported_hints_rejected'])
        self.assertNotIn('shared_paths', report)
        self.assertEqual(knowledge.imported_record('sms', item.sha256), {})
        # The window then forgets their level; the cursor keeps them from returning.
        online.forget_shared([key])
        self.assertEqual(online.shared_paths([key]), {})
        self.assertEqual(online.sync_shared([key])['roms'], 0)
        self.assertEqual(knowledge.imported_record('sms', item.sha256), {})

    def test_offline_the_batch_converts_as_before(self):
        item = self.cartridge(3)
        key = f'sms:{item.sha256}'
        self.server.store = {key: [{'id': 1, 'record': sms_record(0x100), 'level': 'standard'}]}
        online.prepare_batch([key])
        self.stop_server()
        prepared = online.prepare_batch([key])
        self.assertIsInstance(prepared['error'], online.ServiceConnectionError)
        self.assertEqual(prepared['paths'], {key: {'level': 'standard', 'records': 1}}, 'what came earlier stays')
        record, profile, report, _ = self.convert(item, shared_paths=prepared['paths'])
        self.assertEqual(record['succeeded'], 1)
        self.assertEqual(profile.call_args.kwargs['scan_level'], 'quick')
        # Offline with nothing fetched before: the usual conversion.
        other = self.cartridge(4)
        prepared = online.prepare_batch([f'sms:{other.sha256}'])
        self.assertEqual(prepared['paths'], {})
        record, profile, report, _ = self.convert(other, shared_paths=prepared['paths'])
        self.assertEqual(record['succeeded'], 1)
        self.assertNotIn('scan_level', profile.call_args.kwargs)

    # --- After a batch -------------------------------------------------------

    def test_new_discoveries_are_sent_after_a_batch_with_their_claims(self):
        found = collected()
        found['levels'] = {'gb': {SHA: 'extended'}}
        result = online.send_after_batch(lambda: found)
        self.assertEqual((result['games'], result['claims']), (1, {'games': 1, 'paths': 1, 'new': 1}))
        upload, claims = calls_to(self.server, '/contributions'), calls_to(self.server, '/claims')
        self.assertEqual((len(upload), len(claims)), (1, 1))
        game = json.loads(claims[0][3])['games'][0]
        self.assertEqual((game['system'], game['identity'], game['level'], len(game['observations'])),
                         ('gb', SHA, 'extended', 1))
        # Nothing changed since: no upload and no claim.
        self.server.calls.clear()
        self.assertEqual(online.send_after_batch(lambda: found)['games'], 0)
        self.assertEqual(self.server.calls, [])
        # Only the game whose discoveries changed leaves next time.
        online.send_after_batch(lambda: collected(games={SHA: 'Super Mario Land', OTHER: 'Tetris'}))
        sent = json.loads(calls_to(self.server, '/claims')[0][3])['games']
        self.assertEqual([game['identity'] for game in sent], [OTHER])

    def test_claims_that_could_not_go_wait_for_the_next_send(self):
        self.server.claims = 'busy'
        result = online.send_after_batch(lambda: collected())
        self.assertIsNone(result['claims'])
        self.assertEqual(online.waiting_claims(), 1)
        self.assertEqual(online.pending(collected())['games'], 0, 'the file itself was accepted')
        self.server.claims = 'ok'
        self.server.calls.clear()
        result = online.send_after_batch(lambda: collected())
        self.assertEqual(result['claims'], {'games': 1, 'paths': 1, 'new': 1})
        self.assertEqual(online.waiting_claims(), 0)
        self.assertEqual([call[1].rsplit('/', 2)[-2:] for call in self.server.calls], [['7', 'claims']])

    def test_options_off_signed_out_or_no_service_mean_no_request(self):
        key = 'sms:' + 'cd' * 32
        self.server.store = {key: [{'id': 1, 'record': sms_record(0x100), 'level': 'thorough'}]}
        collect = Mock(return_value=collected())
        self.server.calls.clear()
        self.assertEqual(online.prepare_batch([key], enabled=False), {'paths': {}, 'summary': None, 'error': None, 'base': None})
        self.assertIsNone(online.send_after_batch(collect, enabled=False))
        with patch.dict(os.environ, {'RETRO_RECOMP_SERVICE': ''}):
            self.assertEqual(online.prepare_batch([key])['paths'], {})
            self.assertIsNone(online.send_after_batch(collect))
        self.assertEqual(self.server.calls, [])
        # Signed out, the published base still answers (it needs no account), but
        # nothing is posted and no fetch is made; this service has no base.
        online.sign_out()
        self.server.calls.clear()
        self.assertEqual(online.prepare_batch([key])['paths'], {})
        self.assertIsNone(online.send_after_batch(collect))
        self.assertEqual(self.server.calls, [])
        collect.assert_not_called()
        self.assertFalse(self.bank.exists())

    def test_the_window_runs_nothing_without_its_options(self):
        from retrorecomp import gui
        owner = gui.Application.__new__(gui.Application)
        owner.messages, owner.language, owner.updating, owner.auto_sending = Queue(), 'en', False, False
        owner.send_after_batch = Mock(get=Mock(return_value=False))
        with patch('retrorecomp.gui.SENDING_AVAILABLE', True), \
                patch('retrorecomp.online.prepare_batch') as prepare, patch('retrorecomp.online.send_after_batch') as send:
            # Without the option the local base still applies (its qualified paths), but nothing is fetched.
            prepare.return_value = {'paths': {}, 'summary': None, 'error': None, 'base': None}
            self.assertEqual(owner.prepare_shared_paths(['sms:' + 'ef' * 32], False), {})
            prepare.assert_called_once_with(['sms:' + 'ef' * 32], False)
            prepare.reset_mock()
            owner.send_new_discoveries()
            prepare.assert_not_called()
            send.assert_not_called()
            self.assertFalse(owner.auto_sending)
            # A failed automatic send is one quiet log line, and is tried again later.
            owner.auto_sent(None, online.ServiceConnectionError())
            text = owner.messages.get_nowait()[1]
            self.assertIn(owner.tr('online_unreachable'), text)
            self.assertTrue(owner.messages.empty())
            # A fetch that fails leaves the batch as it would be offline.
            prepare.return_value = {'paths': {}, 'summary': None, 'error': online.ServiceError(503, 'busy'), 'base': None}
            self.assertEqual(owner.prepare_shared_paths(['sms:' + 'ef' * 32], True), {})
            self.assertIn('busy', owner.messages.get_nowait()[1])


    def test_batch_end_sends_are_spaced_and_a_waiting_one_leaves_with_the_window(self):
        from retrorecomp import gui
        owner = gui.Application.__new__(gui.Application)
        owner.app, owner.busy, owner.converting, owner.auto_sending = Mock(), False, False, False
        owner.app.after.return_value = 'later'
        sent = []
        def send():
            sent.append(True)
            owner.auto_sending = True
            owner.last_sent_at = gui.time.monotonic()
        owner.send_new_discoveries = send
        # The first batch end sends at once; one ending soon after waits for SEND_EVERY.
        owner.send_discoveries_soon()
        self.assertEqual(len(sent), 1)
        owner.auto_sending = False
        owner.send_discoveries_soon()
        owner.send_discoveries_soon()
        self.assertEqual(len(sent), 1)
        owner.app.after.assert_called_once()
        self.assertGreater(owner.app.after.call_args[0][0], (gui.SEND_EVERY - 5) * 1000)
        self.assertTrue(owner.discoveries_waiting)
        # Due while a batch runs: that batch sends; otherwise it leaves.
        owner.busy = owner.converting = True
        owner.deferred_send_due()
        self.assertEqual(len(sent), 1)
        self.assertIsNone(owner.deferred_send)
        # Due during an import, an export or a ROM search: it waits again, not dropped.
        owner.converting = False
        owner.app.after.reset_mock()
        owner.deferred_send_due()
        self.assertEqual(len(sent), 1)
        self.assertEqual(owner.app.after.call_args[0], (gui.BUSY_SEND_RETRY * 1000, owner.deferred_send_due))
        self.assertEqual(owner.deferred_send, 'later')
        owner.busy, owner.deferred_send = False, None
        owner.send_discoveries_soon()
        owner.deferred_send_due()
        self.assertEqual(len(sent), 2)
        # Closing with a send still waiting: it leaves, and the window waits for it.
        owner.auto_sending, owner.deferred_send = False, 'later'
        self.assertTrue(owner.send_before_closing())
        owner.app.after_cancel.assert_called_with('later')
        self.assertEqual(len(sent), 3)
        self.assertTrue(owner.send_before_closing())   # still sending
        owner.auto_sending = False
        self.assertFalse(owner.send_before_closing())  # done: the window closes
        # Nothing waiting: closing is immediate.
        owner.closing_send_deadline = None
        self.assertFalse(owner.send_before_closing())


if __name__ == '__main__':
    unittest.main()
