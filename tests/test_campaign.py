"""Campaign tooling: reproducible selection, resume, aggregation (fake reports, no ROM)."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from tools import campaign
from tools.release_check import check_report

ROOT = Path(__file__).resolve().parents[1]


def make_folder(base: Path, names: list[str]) -> Path:
    folder = base / 'roms'
    folder.mkdir()
    for name in names:
        (folder / name).write_bytes(b'not a ROM: ' + name.encode())
    return folder


def pick(folder: Path, console: str = 'nes', **options) -> dict:
    options.setdefault('count', 6)
    options.setdefault('seed', 160)
    options.setdefault('risk_entries', [])
    return campaign.select_console(console, folder, **options)


def ids(block: dict) -> list[str]:
    return [game['id'] for game in block['games']]


NAMES = [f'Game {letter} (USA).nes' for letter in 'ABCDEFGHIJKLMNOPQRST']


class TitleTests(unittest.TestCase):
    def test_titles_lose_tags_extensions_and_trailing_articles(self):
        self.assertEqual(campaign.normalize_title('Legend of Zelda, The (USA) (Rev A).zip'), 'the legend of zelda')
        self.assertEqual(campaign.normalize_title('The Legend of Zelda'), 'the legend of zelda')
        self.assertEqual(campaign.normalize_title("Mr. Gimmick (Europe).nes"), 'mr gimmick')
        self.assertEqual(campaign.normalize_title('Metal Sight (System Sacom) (Disk 1).dim'), 'metal sight')

    def test_regions_are_ranked_and_prototypes_come_last(self):
        names = ['Game (Japan).zip', 'Game (Europe).zip', 'Game (USA).zip', 'Game (USA) (Proto).zip']
        self.assertEqual(sorted(names, key=campaign.region_rank)[0], 'Game (USA).zip')
        self.assertEqual(sorted(names, key=campaign.region_rank)[-1], 'Game (USA) (Proto).zip')


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

    def test_the_same_seed_gives_the_same_games_and_another_seed_does_not(self):
        folder = make_folder(self.base, NAMES)
        first, second = pick(folder), pick(folder)
        self.assertEqual(ids(first), ids(second))
        self.assertEqual(len(ids(first)), 6)
        self.assertNotEqual(ids(first), ids(pick(folder, seed=161)))

    def test_the_draw_does_not_depend_on_the_order_files_are_listed_in(self):
        one = make_folder(self.base, NAMES)
        other = self.base / 'second'
        other.mkdir()
        for name in reversed(NAMES):
            (other / name).write_bytes(b'not a ROM: ' + name.encode())
        self.assertEqual([game['name'] for game in pick(one)['games']], [game['name'] for game in pick(other)['games']])

    def test_half_the_sample_is_risk_cases_found_by_title_and_diversified(self):
        names = NAMES + ['Zebra (Europe).nes', 'Zebra (USA).nes', 'Yak (Japan).nes', 'Yak (USA) (Proto).nes']
        entries = [{'title': 'Zebra', 'category': 'a', 'reason': 'r1'}, {'title': 'Yak', 'category': 'a', 'reason': 'r2'},
                   {'title': 'Game C', 'category': 'b', 'reason': 'r3'}, {'title': 'Missing', 'category': 'c', 'reason': 'r4'}]
        result = pick(self.base_with(names), risk_entries=entries)
        risk = [game for game in result['games'] if game['kind'] == 'risk']
        self.assertEqual([game['risk_title'] for game in risk], ['Zebra', 'Game C', 'Yak'])
        self.assertEqual(risk[0]['name'], 'Zebra (USA).nes')
        self.assertEqual(risk[2]['name'], 'Yak (Japan).nes')
        self.assertEqual(len(result['games']) - len(risk), 3)
        self.assertEqual([item['title'] for item in result['unmatched_risk']], ['Missing'])
        titles = [game['title'] for game in result['games']]
        self.assertEqual(len(titles), len(set(titles)))

    def base_with(self, names):
        folder = self.base / f'f{len(list(self.base.iterdir()))}'
        folder.mkdir()
        for name in names:
            (folder / name).write_bytes(b'x' + name.encode())
        return folder

    def test_prefer_picks_the_named_region_and_prefix_matches_longer_titles(self):
        folder = self.base_with(['Star Fox 2 (USA).sfc', 'Star Fox 2 (Japan) (Proto).sfc', 'Star Fox (USA).sfc'])
        entry = {'title': 'Star Fox 2', 'prefix': True, 'prefer': 'Japan', 'category': 'x', 'reason': 'r'}
        found = campaign.match_risk(entry, campaign.list_candidates('snes', folder))
        self.assertEqual(found.path.name, 'Star Fox 2 (Japan) (Proto).sfc')
        entry = {'title': 'Star Fox', 'category': 'x', 'reason': 'r'}
        self.assertEqual(campaign.match_risk(entry, campaign.list_candidates('snes', folder)).path.name,
                         'Star Fox (USA).sfc')

    def test_a_file_the_converter_rejects_is_replaced_and_reported(self):
        folder = self.base_with(NAMES[:8])
        refused = {'Game A (USA).nes', 'Game B (USA).nes'}
        verify = lambda c: (False, {'reason': 'Game Boy Color only'}) if c.path.name in refused else (True, {})
        result = pick(folder, count=8, verify=verify)
        self.assertEqual(len(result['games']), 6)
        self.assertTrue(refused.isdisjoint(game['name'] for game in result['games']))
        self.assertEqual({item['reason'] for item in result['rejected']}, {'Game Boy Color only'})

    def test_the_selection_holds_paths_and_hashes_but_no_rom_bytes(self):
        folder = self.base_with(NAMES[:6])
        result = pick(folder, count=3)
        text = json.dumps(result)
        for game in result['games']:
            self.assertEqual(len(game['file_sha256']), 64)
            self.assertTrue(Path(game['path']).is_absolute())
            self.assertNotIn('not a ROM', text)

    def test_hermes_marks_a_fixed_number_of_games(self):
        folder = self.base_with(NAMES)
        marked = [game['id'] for game in pick(folder, hermes=2)['games'] if game['hermes']]
        self.assertEqual(len(marked), 2)
        self.assertEqual(marked, [game['id'] for game in pick(folder, hermes=2)['games'] if game['hermes']])

    def test_arcade_sets_follow_the_catalogue_and_need_their_parent(self):
        folder = self.base_with(['neogeo.zip', 'kof98.zip', 'kof98k.zip', 'clone.zip', 'unknown.zip', 'wof.zip'])
        catalogue = {'kof98': {'parent': '', 'ok': True}, 'kof98k': {'parent': 'absent', 'ok': True},
                     'clone': {'parent': 'kof98', 'ok': True}, 'wof': {'parent': '', 'ok': False}}
        candidates = campaign.list_candidates('ng', folder, arcade=catalogue)
        self.assertEqual({c.path.stem for c in candidates if c.eligible}, {'kof98', 'clone'})
        entries = [{'title': 'Warriors of Fate', 'set': 'wof', 'category': 'qsound', 'reason': 'r', 'expect': 'refusal'},
                   {'title': 'K98', 'set': 'kof98k', 'category': 'k', 'reason': 'r'}]
        result = pick(folder, 'ng', count=4, risk_entries=entries, arcade=catalogue)
        self.assertEqual([game['name'] for game in result['games'] if game['kind'] == 'risk'], ['wof.zip'])
        self.assertEqual(result['games'][0]['expect'], 'refusal')
        self.assertEqual([item['title'] for item in result['unmatched_risk']], ['K98'])

    def test_x68_disk_sets_are_one_game_led_by_their_first_disk(self):
        folder = self.base_with(['Epic (1990)(Disk 2 of 3).dim', 'Epic (1990)(Disk 1 of 3).dim',
                                 'Epic (1990)(Disk 3 of 3).dim', 'Solo (Maker).dim', 'Other (Disk 1).dim',
                                 'Other (Disk 2).dim'])
        candidates = campaign.list_candidates('x68', folder)
        self.assertEqual(len(candidates), 3)
        epic = next(c for c in candidates if c.key.startswith('epic'))
        self.assertEqual([path.name for path in epic.files][0], 'Epic (1990)(Disk 1 of 3).dim')
        self.assertEqual(len(epic.files), 3)
        entry = {'title': 'Epic (1990)', 'category': 'disks', 'reason': 'r'}
        result = pick(folder, 'x68', count=2, risk_entries=[entry])
        game = next(g for g in result['games'] if g['kind'] == 'risk')
        self.assertEqual(len(game['files']), 3)
        self.assertEqual(game['path'], game['files'][0]['path'])


def fake_selection(root: Path, count: int = 3, hermes=()) -> dict:
    games = [{'id': f'sms-game-{n}', 'console': 'sms', 'kind': 'random', 'title': f'Game {n}',
              'path': str(root / f'rom{n}.sms'), 'files': [{'path': str(root / f'rom{n}.sms'), 'sha256': 'a' * 64,
                                                            'bytes': 100 * (count - n)}],
              'hermes': n in hermes} for n in range(count)]
    return {'schema': 1, 'version': '9.9.9', 'seed': 1, 'count': count, 'consoles': {'sms': {'games': games}}}


def journal(root: Path, game_id: str, verdict: str, console: str = 'sms') -> None:
    campaign.write_json(campaign.journal_path(root, console, game_id), {'id': game_id, 'verdict': verdict})


class ResumeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def names(self, pending):
        return [game['id'] for game in pending.get('sms', [])]

    def test_games_with_a_verdict_are_skipped_and_failures_wait_for_a_retry(self):
        selection = fake_selection(self.root, 4)
        journal(self.root, 'sms-game-0', 'pass')
        journal(self.root, 'sms-game-1', 'fail')
        journal(self.root, 'sms-game-2', 'refused')
        self.assertEqual(self.names(campaign.pending_games(selection, self.root)), ['sms-game-3'])
        self.assertEqual(self.names(campaign.pending_games(selection, self.root, retry_failed=True)),
                         ['sms-game-1', 'sms-game-3'])
        self.assertEqual(len(self.names(campaign.pending_games(selection, self.root, redo=True))), 4)

    def test_a_damaged_journal_file_runs_again(self):
        selection = fake_selection(self.root, 1)
        path = campaign.journal_path(self.root, 'sms', 'sms-game-0')
        path.parent.mkdir(parents=True)
        path.write_text('{"verdict": "pa', encoding='utf-8')
        self.assertEqual(self.names(campaign.pending_games(selection, self.root)), ['sms-game-0'])

    def test_the_hermes_subset_and_the_console_filter(self):
        selection = fake_selection(self.root, 4, hermes=(1, 3))
        self.assertEqual(self.names(campaign.pending_games(selection, self.root, subset='hermes')),
                         ['sms-game-1', 'sms-game-3'])
        self.assertEqual(campaign.pending_games(selection, self.root, consoles=['gb']), {})

    def test_smallest_keeps_only_the_lightest_games(self):
        pending = campaign.pending_games(fake_selection(self.root, 4), self.root)
        self.assertEqual(self.names(campaign.smallest_games(pending, 2)), ['sms-game-2', 'sms-game-3'])


def check_row(game: dict, problems=None) -> dict:
    return {'title': game['title'], 'console': 'sms', 'rom': game['path'], 'sha256': 'b' * 64,
            'report': game['path'] + '.json', 'shape': 'core', 'level': 'quick', 'problems': problems or [],
            'gates': {'conversion': 'pass', 'fallback': 'fail' if problems else 'pass'}, 'counts': {}}


class ChunkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.games = fake_selection(self.root, 3)['consoles']['sms']['games']
        self.args = campaign.build_parser().parse_args(['run', 'RetroRecomp.py', '--level', 'quick', '--jobs', '4'])

    def fake_check(self, outcomes, rename=False):
        """A release_check stand-in that writes what the real one writes beside --work."""
        seen = []

        def check(argv):
            seen.append(argv)
            work = Path(argv[argv.index('--work') + 1])
            games = work / 'Games' / 'datas'
            games.mkdir(parents=True)
            rows, checked = [], []
            for game, (status, problems) in zip(self.games, outcomes):
                rom = str(self.root / 'playlist.m3u') if rename else game['path']
                rows.append({'rom': rom, 'title': game['title'], 'status': status, 'report': game['path'] + '.json',
                             'message': 'unsupported cartridge' if status == 'error' else None})
                if status == 'success':
                    checked.append({**check_row(game, problems), 'rom': rom})
            (games / 'Retro-Recomp-batch.json').write_text(json.dumps({'games': rows}), encoding='utf-8')
            (work / 'release-check.json').write_text(json.dumps({'games': checked}), encoding='utf-8')
            (work / 'batch.log').write_text(f"[1/3 - Game 0] building\nunrelated\n[2/3 - Game 1] building\n",
                                            encoding='utf-8')
            return 1 if any(status != 'success' or problems for status, problems in outcomes) else 0
        return check, seen

    def test_one_journal_file_and_log_per_game_with_the_right_verdicts(self):
        check, seen = self.fake_check([('success', []), ('success', ['main: 12 interpreted']), ('error', [])])
        records = campaign.run_chunk(Path('RetroRecomp.py'), 'sms', self.games, self.root, 1, self.args, check=check)
        self.assertEqual([r['verdict'] for r in records], ['pass', 'fail', 'fail'])
        self.assertEqual(records[1]['problems'], ['main: 12 interpreted'])
        self.assertIn('conversion error: unsupported cartridge', records[2]['problems'])
        for record in records:
            self.assertEqual(campaign.read_json(campaign.journal_path(self.root, 'sms', record['id']))['verdict'],
                             record['verdict'])
        log = campaign.journal_path(self.root, 'sms', 'sms-game-0').with_suffix('.log').read_text(encoding='utf-8')
        self.assertIn('PASS Game 0', log)
        self.assertIn('[1/3 - Game 0] building', log)
        self.assertNotIn('unrelated', log)

    def test_the_converter_is_called_through_release_check_options(self):
        check, seen = self.fake_check([('success', [])] * 3)
        campaign.run_chunk(Path('RetroRecomp.py'), 'sms', self.games, self.root, 1, self.args, check=check)
        argv = seen[0]
        self.assertEqual(argv[:4], ['RetroRecomp.py', *[g['path'] for g in self.games[:3]]][:4])
        for option, value in (('--console', 'sms'), ('--level', 'quick'), ('--jobs', '3'), ('--max-fallback', '0')):
            self.assertEqual(argv[argv.index(option) + 1], value)
        self.assertEqual(argv[argv.index('--app') + 1], str(self.root / 'out' / 'app'))
        self.assertNotIn('--require-states', argv)

    def test_arcade_and_x68_consoles_ask_for_their_own_gates_and_options(self):
        args = campaign.build_parser().parse_args(['run', 'c.exe', '--ng-bios', 'C:/bios/neogeo.zip'])
        flags, extra = campaign.console_options('ng', args)
        self.assertEqual(flags, ['--require-packed', '--require-states'])
        self.assertEqual(extra, ['--ng-bios', 'C:/bios/neogeo.zip'])
        self.assertEqual(campaign.console_options('x68', args)[0], ['--require-states'])
        self.assertEqual(campaign.console_options('gb', args), ([], []))

    def test_a_grouped_set_is_matched_by_position_and_a_missing_result_fails(self):
        check, _ = self.fake_check([('success', [])] * 3, rename=True)
        records = campaign.run_chunk(Path('c.py'), 'sms', self.games, self.root, 1, self.args, check=check)
        self.assertEqual([r['status'] for r in records], ['success'] * 3)
        self.assertEqual([r['verdict'] for r in records], ['pass'] * 3)
        empty = campaign.chunk_records(self.games, None, None, chunk='c', seconds=1.0, level='quick', returncode=1)
        self.assertEqual({r['verdict'] for r in empty}, {'fail'})
        self.assertIn('no batch result', empty[0]['problems'][0])

    def test_an_expected_refusal_passes_only_when_the_converter_refuses(self):
        games = [{**self.games[0], 'expect': 'refusal'}, {**self.games[1], 'expect': 'refusal'}]
        batch = {'games': [{'rom': games[0]['path'], 'status': 'error', 'message': 'SA-1 is not supported'},
                           {'rom': games[1]['path'], 'status': 'success', 'report': 'x'}]}
        check = {'games': [{**check_row(games[1]), 'rom': games[1]['path']}]}
        records = campaign.chunk_records(games, check, batch, chunk='c', seconds=1.0, level='quick', returncode=1)
        self.assertEqual([r['verdict'] for r in records], ['refused', 'fail'])
        self.assertIn('a refusal was expected', records[1]['problems'][0])

    def test_chunk_numbers_continue_after_the_existing_folders(self):
        self.assertEqual(campaign.next_chunk_number(self.root, 'sms'), 1)
        (self.root / 'out' / 'sms' / 'chunk-004').mkdir(parents=True)
        (self.root / 'out' / 'sms' / 'notes').mkdir()
        self.assertEqual(campaign.next_chunk_number(self.root, 'sms'), 5)


def schema2_document(fallback: bool | None, device: bool = False) -> dict:
    scenario = {'name': 'demo', 'frames': 100, 'native': 10, 'interpreted': 40 if fallback else (None if fallback is None else 0),
                'interpreted_percent': None, 'cycles': None}
    cpu = {'id': 'main', 'arch': 'm68000', 'role': 'main', 'unit': 'instructions', 'original_unit': 'instructions',
           'mode': None, 'reported_label': None, 'scenarios': [scenario],
           'fallback_present': fallback}
    devices = []
    if device:
        devices = [{'id': 'GSU-1', 'kind': 'cartridge_coprocessor', 'unit': 'device instructions', 'mode': 'x',
                    'failed': False, 'fallback_present': True,
                    'scenarios': [{'name': 'demo', 'frames': 100, 'interpreted': 7, 'per_frame': 0.07}]}]
    measure = lambda **kw: {**kw}
    return {'schema': {'name': 'retro-recomp-report', 'version': 2}, 'read_from': {'schema_version': 2, 'writer': 'x'},
            'tool': 'Retro-Recomp', 'version': '9.9.9', 'created_utc': None, 'target': None,
            'system': {'id': 'md', 'name': 'Mega Drive', 'status': 'ok'}, 'rom': {'sha256': 'c' * 64},
            'scan': {'level': 'standard', 'enabled': None, 'scenario_frames': None, 'routes': []},
            'cpus': [cpu], 'devices': devices,
            'validation': {'native_code': measure(fallback_present=fallback, zero_fallback_on_tested_scenarios=None,
                                                  scenarios_checked=1, claim='native code on the tested scenarios only'),
                           'cpu_fidelity': measure(passed=True, reference='own', independent_cpu_oracle=False,
                                                   claim='agreement with the project reference'),
                           'hardware_fidelity': measure(validated=None, claim='not reported'),
                           'gameplay': measure(validated=False, scenarios_run=1, owner_acceptance=None,
                                               claim='tested routes only'),
                           'latency': measure(measured=False, ms=None, claim='not measured')},
            'honesty': {}, 'packed': None, 'states': None, 'saves': None,
            'runtime': {'video_model': {'standard': 'ntsc'}}, 'knowledge': {}, 'build': {'wall_seconds': 12.5},
            'upgrade': None, 'export_receipt': None, 'legacy': {'reference_vdp_trace_match': None}}


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.selection = fake_selection(self.root, 4)
        self.documents = {}

    def record(self, index: int, verdict: str, document=None, **extra):
        game = self.selection['consoles']['sms']['games'][index]
        path = f'doc-{index}'
        if document is not None:
            self.documents[path] = document
        campaign.write_json(campaign.journal_path(self.root, 'sms', game['id']),
                            {'id': game['id'], 'console': 'sms', 'title': game['title'], 'kind': 'risk',
                             'category': 'c', 'verdict': verdict, 'status': 'success', 'level': 'quick',
                             'problems': extra.pop('problems', []), 'report': path if document is not None else None,
                             'chunk': 'chunk-001', 'chunk_seconds': 30.0, 'chunk_games': 2, **extra})

    def load(self, path):
        return self.documents[path]

    def test_totals_count_each_verdict_and_the_games_without_one(self):
        self.record(0, 'pass', schema2_document(False))
        self.record(1, 'fail', schema2_document(True), problems=['main: 40 interpreted'])
        self.record(2, 'refused')
        summary = campaign.aggregate(self.selection, self.root, load=self.load)
        self.assertEqual(summary['totals'], {'selected': 4, 'pass': 1, 'refused': 1, 'fail': 1, 'pending': 1})
        self.assertEqual(summary['consoles']['sms']['totals']['pending'], 1)

    def test_fallback_is_kept_per_cpu_and_device_and_unknown_stays_unknown(self):
        self.record(0, 'pass', schema2_document(False))
        self.record(1, 'fail', schema2_document(True, device=True))
        self.record(2, 'pass', schema2_document(None))
        rows = campaign.aggregate(self.selection, self.root, load=self.load)['consoles']['sms']['games']
        self.assertEqual(campaign.fallback_text(rows[0]['fallback']), 'main m68000: none')
        self.assertEqual(campaign.fallback_text(rows[1]['fallback']),
                         'main m68000: YES (40 instructions); GSU-1: YES (7 device instructions)')
        self.assertEqual(campaign.fallback_text(rows[2]['fallback']), 'main m68000: not measured')
        self.assertEqual(rows[0]['seconds'], 12.5)

    def test_the_five_measures_are_copied_with_their_own_claims(self):
        self.record(0, 'pass', schema2_document(False))
        row = campaign.aggregate(self.selection, self.root, load=self.load)['consoles']['sms']['games'][0]
        self.assertEqual(set(row['measures']), set(campaign.MEASURES))
        self.assertIsNone(row['measures']['hardware_fidelity']['validated'])
        self.assertEqual(row['measures']['latency']['claim'], 'not measured')

    def test_an_unreadable_report_is_stated_not_guessed(self):
        self.record(0, 'fail', report='missing.json')
        rows = campaign.aggregate(self.selection, self.root)['consoles']['sms']['games']
        self.assertIn('missing.json', rows[0]['report_error'])
        self.assertIsNone(rows[0]['fallback'])

    def test_the_markdown_lists_every_game_and_the_limits_of_a_pass(self):
        self.record(0, 'pass', schema2_document(False))
        self.record(1, 'fail', schema2_document(True), problems=['main: 40 interpreted'])
        text = campaign.render_markdown(campaign.aggregate(self.selection, self.root, load=self.load))
        for needle in ('## sms', '| Game 0 |', 'PENDING', '- problem: main: 40 interpreted', 'YES (40 instructions)',
                       '- physical latency: measured False', 'not a claim of hardware fidelity'):
            self.assertIn(needle, text)

    def test_a_refusal_shows_the_converter_message(self):
        self.record(2, 'refused', message='SA-1 is not supported', status='error')
        text = campaign.render_markdown(campaign.aggregate(self.selection, self.root, load=self.load))
        self.assertIn('- the converter refused the cartridge: SA-1 is not supported', text)

    def test_the_upgrade_and_state_summaries_join_the_report_when_present(self):
        campaign.write_json(self.root / 'upgrade' / 'summary.json', {'games': [
            {'title': 'Old', 'console': 'md', 'from_version': '1.5.6', 'outcome': 'quick upgrade', 'verdict': 'pass'}]})
        campaign.write_json(self.root / 'states' / 'summary.json', {'limits': 'Only what it runs.', 'results': [
            {'title': 'Old', 'check': 'pairs', 'outcome': 'refused by the new export'}]})
        text = campaign.render_markdown(campaign.aggregate(self.selection, self.root, load=self.load))
        self.assertIn('| Old | md | 1.5.6 | quick upgrade | PASS |', text)
        self.assertIn('| Old | pairs | refused by the new export |', text)


class UpgradeAndStateTests(unittest.TestCase):
    def test_upgrade_outcomes_tell_a_quick_upgrade_from_a_reconversion(self):
        self.assertEqual(campaign.classify_upgrade({'status': 'current'}, None), 'already current')
        self.assertEqual(campaign.classify_upgrade({'status': 'success', 'upgraded': True}, None), 'quick upgrade')
        self.assertEqual(campaign.classify_upgrade({'status': 'success', 'upgraded': False}, {}), 'full reconversion')
        self.assertEqual(campaign.classify_upgrade({'status': 'success', 'upgraded': False}, {'upgrade': {'reason': 'x'}}),
                         'quick upgrade')
        self.assertEqual(campaign.classify_upgrade({'status': 'error'}, None), 'failed')
        self.assertEqual(campaign.classify_upgrade(None, None), 'no result')

    def test_state_checks_separate_resumed_diverged_and_refused(self):
        resumed = json.dumps({'states_resume_across_builds': True, 'same_trace_in_both_builds': True})
        self.assertEqual(campaign.classify_cross(0, resumed, '')['outcome'], 'resumed identically')
        differs = json.dumps({'states_resume_across_builds': True, 'same_trace_in_both_builds': False,
                              'same_final_guest_state': True})
        self.assertIn('same_trace_in_both_builds', campaign.classify_cross(1, differs, '')['outcome'])
        self.assertEqual(campaign.classify_cross(1, '', 'AssertionError: b.exe diverges 3 frames after')['outcome'],
                         'resumed but diverged')
        self.assertEqual(campaign.classify_cross(1, '', 'RuntimeError: restored: exit 3')['outcome'],
                         'refused by the new export')
        self.assertTrue(campaign.classify_cross(2, '', 'boom')['outcome'].startswith('error'))

    def test_run_cross_calls_the_existing_tool_one_way(self):
        calls = []

        class Done:
            returncode, stdout, stderr = 0, json.dumps({'states_resume_across_builds': True}), ''

        outcome = campaign.run_cross(Path('old.exe'), Path('new.exe'), 10, 5,
                                     runner=lambda command, **kw: calls.append(command) or Done())
        self.assertEqual(outcome['outcome'], 'resumed identically')
        self.assertIn('state16_cross.py', calls[0][2])
        self.assertIn('--one-way', calls[0])

    def test_continuations_are_compared_on_every_traced_column(self):
        rows = [{'frame': '0', 'video': 'a', 'native': '1'}, {'frame': '1', 'video': 'b', 'native': '1'}]
        same = campaign.compare_continuations(({'cpu_hash': 'x'}, rows), ({'cpu_hash': 'x'}, [dict(r, native='9') for r in rows]))
        self.assertEqual(same['outcome'], 'both builds continue identically')
        other = campaign.compare_continuations(({'cpu_hash': 'x'}, rows), ({'cpu_hash': 'y'}, rows))
        self.assertEqual(other['fields'], ['cpu_hash'])
        shifted = [rows[0], dict(rows[1], video='c')]
        self.assertEqual(campaign.compare_continuations(({}, rows), ({}, shifted))['first_mismatch'], 1)


class RiskCaseFileTests(unittest.TestCase):
    def setUp(self):
        self.cases = json.loads((ROOT / 'tools' / 'campaign-risk-cases.json').read_text(encoding='utf-8'))

    def test_every_console_has_cases_with_a_reason_and_a_document_that_exists(self):
        self.assertEqual(set(self.cases['consoles']), set(campaign.CONSOLES))
        for console, entries in self.cases['consoles'].items():
            self.assertGreaterEqual(len(entries), 6, console)
            for entry in entries:
                for key in ('title', 'category', 'reason', 'source'):
                    self.assertTrue(entry.get(key), (console, entry))
                self.assertTrue((ROOT / entry['source']).is_file(), entry['source'])
                if console in ('ng', 'cps1'):
                    self.assertTrue(entry.get('set'), entry)

    def test_a_case_names_a_title_once_per_console_and_category_coverage_is_varied(self):
        for console, entries in self.cases['consoles'].items():
            titles = [entry['title'] for entry in entries]
            self.assertEqual(len(titles), len(set(titles)), console)
            self.assertGreaterEqual(len({entry['category'] for entry in entries}), 5, console)

    def test_arcade_cases_name_sets_the_converter_catalogue_knows(self):
        for console in ('ng', 'cps1'):
            known = campaign.arcade_catalogue(console)
            for entry in self.cases['consoles'][console]:
                self.assertIn(entry['set'], known, entry)

    def test_the_tool_and_its_data_are_on_the_publication_allowlist_only_as_sources(self):
        from tools.prepare_publication import BUNDLED_FILES, PUBLIC_SET
        for name in ('tools/campaign.py', 'tools/campaign-risk-cases.json', 'tests/test_campaign.py'):
            self.assertIn(name, PUBLIC_SET)
            self.assertNotIn(name, BUNDLED_FILES)

    def test_no_private_path_is_written_in_the_tool(self):
        text = (ROOT / 'tools' / 'campaign.py').read_text(encoding='utf-8')
        self.assertNotIn('192.168.', text)


class CoreShapeTests(unittest.TestCase):
    """Master System and Game Gear write the core shape; release_check reads it."""

    @staticmethod
    def report(cycles: int = 0, passed: bool = True) -> dict:
        return {'system': {'id': 'sms', 'name': 'Master System'}, 'scan_level': 'quick', 'strict_checks': [],
                'native_validation': {'passed': True, 'scenarios': [
                    {'scenario': 'demo', 'passed': True, 'checks': {}, 'missing_or_invalid_evidence': []},
                    {'scenario': 'play', 'passed': passed, 'checks': {}, 'missing_or_invalid_evidence': []}]},
                'final_checks': [{'scenario': 'demo', 'interpreter_cycles': 0, 'total_cycles': 5},
                                 {'scenario': 'play', 'interpreter_cycles': cycles, 'total_cycles': 5}]}

    def test_a_clean_core_report_passes_and_counts_cycles(self):
        checked = check_report(self.report(), 'sms', 'quick', 0)
        self.assertEqual((checked['shape'], checked['problems']), ('core', []))

    def test_fallback_cycles_and_a_failed_comparison_are_problems(self):
        self.assertIn('play: 12 interpreted CPU cycles (limit 0)', check_report(self.report(12), 'gg', 'quick', 0)['problems'])
        self.assertIn('play: native and reference differ', check_report(self.report(passed=False), 'sms', 'quick', 0)['problems'])


if __name__ == '__main__':
    unittest.main()
