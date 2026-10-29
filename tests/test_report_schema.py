"""Report schema 2 and its one reader (retrorecomp/report_schema.py).

The fixtures are synthetic. Each one is built from reading its writer's code
(core.py, gameboy.py, nes.py, console16.py, neogeo_conversion.py,
cps1_conversion.py, x68000_conversion.py) and the fields batch.py adds after
the conversion; none is copied from an export or from a player's data.

The summary parity is checked against a replica of the expressions of
batch.py (convert_one) and gui.py (_prepare_path), which are inline in
methods that need a window or a whole conversion and cannot be called. Their
text is checked in the sources (test_replicated_expressions_are_still_in_the_callers)
so that the replica cannot drift unnoticed.
"""
import copy
import json
import tempfile
import unittest
from pathlib import Path

import retrorecomp
from retrorecomp import report_schema
from retrorecomp.compilation_inputs import INTERFACE_MODULES
from tools.gui_patching import gui_source
from retrorecomp.report_schema import (MEASURES, REQUIRED_KEYS, SCHEMA_VERSION, ReportShapeError,
                                       fallback_summary, read_report)
from retrorecomp.snes_chips import device_entry, device_summary, main_interpreted

SHA = 'ab' * 32


def route(name, frames, index):
    return {'scenario': name, 'seed': f'x-long:{SHA[:8]}:{index}', 'index': index, 'frames': frames, 'steps': 40,
            'continues_from': None, 'generator': 'random_routes.long_route'}


# ---------------------------------------------------------------- one fixture per writer shape

def sms_report(system_id='sms', *, cycles=0, banked=True):
    """core.py: Master System and Game Gear. interpreter_percent comes from the probe's log."""
    total = 60_000_000
    rows = [{'requested_frames': 3600, 'exit_code': 0, 'wall_seconds': 1.5, 'completed_frames': 3600,
             'dispatch_misses': 0, 'interpreter_percent': round(100 * cycles / total, 6),
             'static_percent': 99.0, 'strict': False, 'scripted_input': [], 'reference': False, 'passed': True,
             'interpreter_calls': 3 if cycles else 0, 'interpreter_cycles': cycles, 'total_cycles': total,
             'scenario': name} for name in ('demo', 'play')]
    validation = {'policy': 'banked-release-v2-raster', 'passed': True, 'hardware_accuracy': False,
                  'full_game': False,
                  'scenarios': [{'passed': True, 'checks': {'completed': True, 'final_cpu': True, 'vdp_trace': True},
                                 'missing_or_invalid_evidence': [], 'scenario': row['scenario'], 'reference': {}}
                                for row in rows]} if banked else None
    return {'tool': 'Retro-Recomp', 'version': '1.5.5', 'created_utc': '2026-10-27T10:00:00+00:00',
            'runtime_data': {'directory': 'datas', 'library_identity': SHA,
                             'runtime_feedback': {'fingerprint': 'f' * 8}},
            'backend': 'banked' if banked else 'functions', 'target': 'windows-x86_64', 'scan_level': 'standard',
            'long_routes': [route('long-1', 7200, 1)], 'native_coverage': {'compiled_positions': 10, 'rom_positions': 12},
            'native_validation': validation, 'input_players': 1 if system_id == 'gg' else 2,
            'game_states': {'supported': banked, 'save_key': 'F8', 'load_key': 'F9', 'slots': 1, 'schema': 1,
                            'machine': 1, 'rom_identity': 'sha256', 'legacy_and_reference_supported': False},
            'system': {'id': system_id, 'name': 'Game Gear' if system_id == 'gg' else 'Master System'},
            'video_model': {'name': 'mode4', 'standard': 'ntsc', 'visible_pixels': [256, 192]},
            'peripheral': {'type': 'joypad', 'hardware_accuracy_validated': False},
            'conversion_wall_seconds': 120.5, 'build_executable': 'C:/build/game.exe', 'toolchain': {'kind': 'llvm-mingw'},
            'rom': {'name': 'game.sms', 'bytes': 262144, 'sha256': SHA, 'system_id': system_id},
            'engine_revision': 'abc', 'executable': 'Game.exe', 'latency_ms': None,
            'hardware_accuracy_validated': False, 'full_game_validated': False,
            'reference_vdp_trace_match': True, 'reference_scope': 'CPU comparison with interpreter over the SAME runtime',
            'reference_final_ram_match': True, 'reference_final_cpu_match': True, 'reference_final_png_match': True,
            'strict_checks': [], 'final_checks': rows, 'history': list(rows), 'build_directory': 'C:/build',
            'learning': {'before': {}, 'after': {}}}


def gb_report(*, cycles=0, instructions=0):
    """gameboy.py: cycles and instructions, but no denominator for a percentage."""
    rows = [{'scenario': name, 'input_script': None, 'frames': 600, 'interpreter_handoffs': 1 if cycles else 0,
             'interpreter_entries': 1 if cycles else 0, 'interpreter_instructions': instructions,
             'interpreter_cycles': cycles, 'interpreter_percent': None, 'fallback_sites': 0,
             'fallback_sites_dropped': 0, 'fallback_details': [], 'trace_entries_bytes': 0} for name in ('boot', 'play')]
    cpu = [{'scenario': row['scenario'], 'frames': 600, 'input_script': None,
            'result': '[DIFF] Matched generated and interpreter execution for 90000 steps / 600 frames',
            'wall_seconds': 2.0} for row in rows]
    return {'tool': 'Retro-Recomp', 'version': '1.5.5', 'system': {'id': 'gb', 'name': 'Game Boy'},
            'scan_level': 'standard', 'long_routes': [], 'rom': {'name': 'g.gb', 'sha256': SHA, 'system_id': 'gb'},
            'backend': 'gb-recompiled-sm83', 'compiler': {'revision': 'r1', 'license': 'MIT'},
            'native_coverage': {'translated_functions': 40, 'percent': None},
            'generated_build': {'shared_bodies': 1}, 'final_checks': rows, 'history': rows,
            'native_validation': {'passed': True, 'cpu_differential': cpu[0]['result'], 'mode': 'standard',
                                  'scenarios': cpu, 'frames': 30, 'hardware_accuracy': False, 'full_game': False},
            'reference_vdp_trace_match': None,
            'video_model': {'standard': 'dmg', 'visible_pixels': [160, 144], 'hardware_accuracy_validated': False},
            'input_players': 1, 'game_states': {'supported': True, 'save_key': 'F8', 'load_key': 'F9', 'slots': 1,
                                                'rom_identity': 'sha256'},
            'runtime_feedback': {'fingerprint': 'f' * 8}, 'library_identity': SHA,
            'host_timing': {'apu_sample_rate': 44100, 'physical_latency_measured': False},
            'build_executable': 'C:/b/g.exe', 'executable': 'G.exe', 'toolchain': {'kind': 'llvm-mingw'},
            'build_directory': 'C:/b', 'stage_seconds': {'build': 10.0}, 'conversion_wall_seconds': 33.0}


def nes_report(*, cycles=0):
    """nes.py: cycles, with the share of the cycle total in interpreter_percent."""
    total = 29_780 * 600
    rows = [{'scenario': name, 'frames': 600, 'cycles': total, 'native_cycles': total - cycles - 5,
             'native_percent': 100.0, 'interpreter_rom_cycles': cycles, 'interpreter_ram_cycles': 0,
             'interpreter_other_cycles': 0, 'interpreter_cycles': cycles, 'interpreter_percent': 100 * cycles / total,
             'non_dispatch_cycles': 5, 'internal_differential': True, 'audio_pcm_match': True,
             'audio_samples': 48000, 'audio_pcm_sha256': 'c' * 64} for name in ('boot', 'play_right')]
    return {'tool': 'Retro-Recomp', 'version': '1.5.5', 'created_utc': '2026-10-27T10:00:00+00:00',
            'system': {'id': 'nes', 'name': 'Nintendo Entertainment System'}, 'scan_level': 'extended',
            'rom': {'name': 'g.nes', 'sha256': SHA, 'mapper': 0}, 'backend': 'nesrecomp-cycle-accurate',
            'compiler': {'revision': 'r', 'license': 'PolyForm Noncommercial 1.0.0'},
            'native_coverage': {'imported_entries': 3, 'tested_scenarios': ['boot', 'play_right']},
            'final_checks': rows, 'history': rows, 'build_passes': [],
            'native_validation': {'passed': True, 'method': 'internal interpreter frame hashes and exact PCM',
                                  'scenarios': copy.deepcopy(rows), 'independent_cpu_oracle': False,
                                  'hardware_accuracy': False, 'full_game': False},
            'reference_vdp_trace_match': None,
            'video_model': {'standard': 'ntsc', 'timing_source': 'header', 'visible_pixels': [256, 240],
                            'hardware_accuracy_validated': False},
            'input_players': 2, 'zapper': None, 'game_states': {'supported': True, 'compatibility': 'same ROM'},
            'runtime_feedback': {'fingerprint': 'f' * 8}, 'library_identity': SHA,
            'advanced_scan': {'enabled': True, 'level': 'extended', 'scenarios': ['boot'],
                              'scenario_frames': {'boot': 600}, 'long_routes': [route('long-1', 7200, 1)],
                              'deterministic_inputs': True, 'full_game': False},
            'host_audio': {'sample_rate': 48000}, 'physical_latency_measured': False,
            'build_executable': 'C:/b/g.exe', 'executable': 'G.exe', 'toolchain': {'kind': 'llvm-mingw'},
            'build_directory': 'C:/b', 'conversion_wall_seconds': 40.0}


def console16_report(system_id='md', *, main=0, audio=0, device=None, stored_device=True):
    """console16.py: Mega Drive and Super Nintendo. Opcode counts for the CPUs, cycles for the sound CPU too."""
    rows = []
    for name in ('demo', 'play'):
        row = {'scenario': name, 'frames': 3600, 'native_entries': 900_000 - main, 'interpreted_opcodes': main,
               'audio_native_opcodes': 500_000 - audio, 'audio_interpreted_opcodes': audio,
               'audio_native_cycles': 2_000_000 - 4 * audio, 'audio_interpreted_cycles': 4 * audio,
               'audio_cpu': 'hybrid' if audio else 'native', 'native_counter_unit': 'main CPU opcodes'}
        if system_id == 'md':
            row['retired_interpreted_opcodes'] = main
        else:
            # The Super Nintendo's interpreted_opcodes also counts the cartridge device.
            row.update(main_interpreted_opcodes=main, interpreted_opcodes=main + (device or 0),
                       cartridge_chip='superfx' if device is not None else 'none',
                       coprocessor_mode='interpreted' if device is not None else 'not_run',
                       coprocessor_instructions=device or 0, coprocessor_commands=0, coprocessor_failed=0)
        rows.append(row)
    report = {'tool': 'Retro-Recomp', 'version': '1.5.5', 'status': 'supported',
              'created_utc': '2026-10-27T10:00:00+00:00', 'system': {'id': system_id, 'name': system_id.upper()},
              'scan_level': 'thorough', 'rom': {'name': 'g.bin', 'sha256': SHA, 'system_id': system_id},
              'cartridge_profile': {'source': 'cartridge', 'id': None, 'catalogue_required': False, 'limitations': []},
              'compiler': {'repository': 'x/y', 'revision': 'r', 'license': 'PolyForm Noncommercial 1.0.0'},
              'final_checks': rows, 'passes': [], 'reference_vdp_trace_match': None,
              'advanced_scan': {'enabled': True, 'level': 'thorough', 'scenario_frames': {'advanced': 4000},
                                'long_routes': [route('long-1', 9000, 1)],
                                'authored_routes': [{'scenario': 'authored', 'kind': 'authored', 'frames': 5000,
                                                     'steps': 30, 'script_sha256': 'd' * 64, 'continues_from': None}],
                                'reference_before_learning': True},
              'native_validation': {'passed': True, 'visible_sequence_match': True, 'audio_pcm_match': True,
                                    'comparisons': [{'scenario': row['scenario'], 'frames': 3600, 'differences': []}
                                                    for row in rows],
                                    'reference_frames': 3600, 'reference_kind': 'internal_shared_semantics',
                                    'cpu_fidelity_validated': False, 'hardware_fidelity_validated': False,
                                    'full_game_validated': False},
              'video_model': {'standard': 'ntsc', 'visible_pixels': [320, 224], 'console_version': None},
              'audio_cpu': rows[-1]['audio_cpu'], 'audio_counter_unit': 'sound CPU cycles',
              'audio_native_percentage': [100.0, 100.0], 'native_percentage': [100.0, 100.0], 'peripheral': None,
              'game_states': {'supported': True, 'save_key': 'F8', 'load_key': 'F9', 'slots': 1,
                              'compatibility': 'same ROM, video standard and runtime ABI'},
              'cartridge_memory': {'kind': 'sram', 'bytes': 8192}, 'runtime_feedback': {'fingerprint': 'f' * 8},
              'physical_latency_measured': False, 'executable': 'G.exe', 'build_executable': 'C:/b/g.exe',
              'toolchain': {'kind': 'llvm-mingw'}, 'build_directory': 'C:/b', 'conversion_wall_seconds': 90.123}
    if system_id == 'snes' and stored_device and (entry := device_entry(rows)):
        report['cartridge_device'] = entry
    return report


def neogeo_report(*, main=0, audio=0):
    """neogeo_conversion.py: rows built by check_routes; keys appended after the literal."""
    rows = [{'name': name, 'frames': 7200, 'native_entries': 1_000_000, 'interpreted_opcodes': main,
             'audio_native_opcodes': 300_000, 'audio_interpreted_opcodes': audio,
             'interpreter_percent': round(100 * main / (1_000_000 + main), 6), 'reference_match': True,
             'cpu_hash': '1' * 16, 'ram_hash': '2' * 16, 'hardware_hash': '3' * 16, 'z80_hash': '4' * 16,
             'image_hash': '5' * 16, 'pcm_hash': '6' * 16} for name in ('play', 'aes-play')]
    return {'tool': 'Retro-Recomp', 'version': '1.5.5', 'status': 'experimental' if main or audio else 'completed',
            'created_utc': '2026-10-27T10:00:00+00:00', 'system': {'id': 'ng', 'name': 'Neo Geo'},
            'rom': {'console': 'ng', 'set': 'game', 'sha256': SHA}, 'prepared_cartridge': {'ngh': 1},
            'bios': {'mvs': 'x'}, 'compiler': {'repository': 'libretro/geolith-libretro', 'revision': 'r'},
            'final_checks': rows,
            'native_validation': {'passed': True, 'packed_reference_match': True, 'reference_before_learning': True,
                                  'reference_kind': 'internal Geolith hardware family', 'cpu_agreement': True,
                                  'hardware_fidelity_validated': False, 'full_game_validated': False},
            'video_model': {'standard': 'mvs', 'region': 'eu', 'visible_pixels': [320, 224]},
            'audio_cpu': 'Z80', 'counter_unit': 'retired instructions', 'runtime_learning': True,
            'runtime_feedback': {'fingerprint': 'f' * 8}, 'physical_latency_measured': False,
            'game_states': {'supported': True, 'save_key': 'F8', 'load_key': 'F9', 'compatibility': 'exact',
                            'validation': {'fresh_process': True, 'invalid_rejected': 2}},
            'ordinary_saves': {'supported': True, 'scope': 'game-scoped MVS NVRAM', 'path': 'datas/saves/x.rrsave',
                               'validation': {'survived': True}},
            'knowledge': {'use': {'imported': 0}, 'observations': 3}, 'executable': 'G.exe',
            'build_executable': 'C:/b/g.exe', 'toolchain': {'kind': 'llvm-mingw'}, 'build_directory': 'C:/b',
            'packed_candidate_sha256': 'e' * 64, 'conversion_wall_seconds': 600.5,
            'conversion_phases_seconds': {'packed_replays': 20.0}, 'validation_workers': 4, 'scan_level': 'extended',
            'qualification_scope': {'system': 'MVS', 'hardware_specification_checks': 136,
                                    'universal_zero_fallback_claim': False},
            'qualification_extra_routes': {'long-1': {'frames': 9000, 'script_sha256': 'f' * 64}}}


def cps1_report(*, main=0, audio=0):
    """cps1_conversion.py: native_coverage is a bool, every route is a validation row."""
    rows = [{'name': name, 'frames': 3600, 'native_entries': 2_000_000, 'interpreted_opcodes': main,
             'audio_native_opcodes': 400_000, 'audio_interpreted_opcodes': audio,
             'interpreter_percent': round(100 * main / (2_000_000 + main), 6), 'reference_match': True,
             'cpu_hash': '1' * 16, 'ram_hash': '2' * 16, 'image_hash': '5' * 16, 'pcm_hash': '6' * 16,
             'nonzero_samples': 100, 'trace_sha256': '7' * 64, 'script_sha256': '8' * 64}
            for name in ('boot', 'play')]
    return {'tool': 'Retro-Recomp', 'version': '1.5.5', 'status': 'experimental' if main or audio else 'completed',
            'created_utc': '2026-10-27T10:00:00+00:00', 'system': {'id': 'cps1', 'name': 'Capcom CPS-1'},
            'rom': {'console': 'cps1', 'set': 'game', 'sha256': SHA},
            'compiler': {'mame_revision': 'm', 'ymfm_revision': 'y'},
            'native_analysis': {'m68000': {'decoded': 1}, 'z80': {'decoded': 2}}, 'final_checks': rows,
            'native_validation': {'passed': True, 'packed_reference_match': True, 'reference_before_learning': True,
                                  'reference_kind': 'same board model with every instruction interpreted',
                                  'cpu_agreement': True, 'hardware_fidelity_validated': False,
                                  'full_game_validated': False,
                                  'mame_comparison': 'board model compared with MAME on development sets only'},
            'native_coverage': not (main or audio),
            'video_model': {'standard': 'arcade', 'visible_pixels': [384, 224], 'hz': 59.6, 'rotation': 0},
            'audio_cpu': 'Z80', 'counter_unit': 'retired instructions', 'runtime_feedback': {'fingerprint': 'f' * 8},
            'physical_latency_measured': False, 'latency_ms': None,
            'game_states': {'supported': True, 'save_key': 'F8', 'load_key': 'F9', 'compatibility': 'exact',
                            'validation': {'fresh_process': True}},
            'ordinary_saves': {'supported': False, 'reason': 'standard CPS-1 boards keep no non-volatile memory'},
            'executable': 'G.exe', 'build_executable': 'C:/b/g.exe', 'toolchain': {}, 'build_directory': 'C:/b',
            'packed_candidate_sha256': 'e' * 64, 'scan_level': 'standard', 'validation_workers': 4,
            'conversion_phases_seconds': {'packed_replays': 5.0}, 'conversion_wall_seconds': 300.0,
            'qualification_scope': {'universal_zero_fallback_claim': False}}


def x68_report(*, interpreted=0):
    """x68000_conversion.py: opcodes only, no audio CPU, no VDP comparison (null since 1.6.0; True before)."""
    def row(count, extra):
        return {'frames': count, 'native_entries': 5_000_000, 'interpreted_opcodes': interpreted,
                'interpreter_percent': 100 * interpreted / (5_000_000 + interpreted), 'reference_match': True, **extra}
    check = row(3000, {'state_restart_match': True, 'state_frame': 600, 'boot_frames': 200,
                       'boot_state_restart_match': True})
    exploration = [row(1200, {'route': 'mouse-1', 'trace_sha256': '9' * 64, 'automatic_disk_changes': 0,
                              'media_events': []})]
    return {'tool': 'Retro-Recomp', 'version': '1.5.5', 'created_utc': '2026-10-27T10:00:00+00:00',
            'system': {'id': 'x68', 'name': 'Sharp X68000'}, 'status': 'experimental', 'private_development_only': False,
            'target': 'windows-x86_64', 'rom': {'name': 'g.dim', 'sha256': SHA}, 'machine': {'model': 'x'},
            'source_identity': 'b' * 64, 'qualification_directory': 'C:/q', 'source_rom': 'C:/roms/g.dim',
            'executable': 'G.exe', 'build_executable': 'C:/b/g.exe', 'toolchain': {},
            'native_validation': {'passed': True, 'scope': 'fresh same-machine CPU/RAM/video/PCM reference',
                                  'generation': 2},
            'native_coverage': 'observed exact RAM encodings with live word guards',
            'final_checks': [check, *exploration], 'exploration_checks': exploration, 'scan_level': 'standard',
            'reference_vdp_trace_match': None, 'runtime_feedback': {'fingerprint': 'f' * 8},
            'game_states': {'supported': True, 'save_key': 'F8', 'load_key': 'F9', 'fresh_process_verified': True},
            'video_model': {'standard': 'native', 'frameskip': False, 'fps': 55.46},
            'hardware_accuracy_validated': False, 'full_game_validated': False, 'latency_ms': None,
            'conversion_wall_seconds': 1800.25}


def published(report, *, upgrade=None):
    """What batch.py adds after a conversion (rom.sha256, executable, packing, upgrade)."""
    report = copy.deepcopy(report)
    report.update(ui_languages=['en', 'fr'], language_switch_key='F7', published_directory='C:/out',
                  source_rom='C:/roms/g.rom', packing={'packer': 'UPX', 'version': '5.3.0', 'level': 9, 'packed': True,
                  'unpacked': {'bytes': 3000, 'sha256': '1' * 64}, 'published': {'bytes': 1200, 'sha256': '2' * 64},
                  'size_ratio': 0.4, 'compared_on': 'unpacked build executable'})
    report.setdefault('rom', {})['sha256'] = SHA
    if upgrade:
        report['upgrade'] = upgrade
    return report


FIXTURES = {
    'sms zero fallback': lambda: sms_report(),
    'sms with fallback': lambda: sms_report(cycles=1234),
    'gg functions backend': lambda: sms_report('gg', cycles=777, banked=False),
    'gb zero fallback': lambda: gb_report(),
    'gb with fallback': lambda: gb_report(cycles=5000, instructions=900),
    'nes zero fallback': lambda: nes_report(),
    'nes with fallback': lambda: nes_report(cycles=4321),
    'md zero fallback': lambda: console16_report('md'),
    'md with fallback': lambda: console16_report('md', main=17, audio=5),
    'snes no device': lambda: console16_report('snes', main=3),
    'snes superfx device': lambda: console16_report('snes', main=40, audio=2, device=6_000_000),
    'snes device rebuilt from checks': lambda: console16_report('snes', main=40, device=250, stored_device=False),
    'ng completed': lambda: neogeo_report(),
    'ng with fallback': lambda: neogeo_report(main=12, audio=3),
    'cps1 completed': lambda: cps1_report(),
    'cps1 with fallback': lambda: cps1_report(main=8, audio=1),
    'x68 zero fallback': lambda: x68_report(),
    'x68 with fallback': lambda: x68_report(interpreted=640),
}


def legacy_summary(report, hint='HINT'):
    """The expressions batch.py (convert_one) and gui.py (_prepare_path) had before they read reports through
    report_schema.fallback_summary, identical in both, on an old shape. This replica is the reference the
    summary is held to."""
    measured = [c.get('interpreter_percent') for c in report['final_checks']]
    return dict(conversion_stage=report.get('status'),
                main_interpreted_opcodes=max((main_interpreted(c) for c in report['final_checks']), default=0),
                device=device_summary(report),
                audio_cpu=report.get('audio_cpu'),
                audio_interpreted_opcodes=max((c.get('audio_interpreted_opcodes', 0) for c in report['final_checks']),
                                              default=0),
                video_standard=report.get('video_model', {}).get('standard', hint),
                interpreter_percent=max((p for p in measured if p is not None), default=None),
                interpreter_cycles=max((c.get('interpreter_cycles', 0) for c in report['final_checks']), default=0),
                reference_vdp_trace_match=report.get('reference_vdp_trace_match'))


def decided(expected, report):
    """The one difference made on purpose (stage C2): the main CPU's instruction count when the writer measured
    one. Game Boy counts instructions beside cycles; its rows keep the key interpreter_instructions, which the
    old expression never read, so the summary read 0 where the report had 900."""
    if report['system']['id'] == 'gb':
        expected = dict(expected, main_interpreted_opcodes=max(
            (c.get('interpreter_instructions') or 0 for c in report['final_checks']), default=0))
    return expected


class SummaryParity(unittest.TestCase):
    def test_summary_equals_the_current_batch_and_window_logic_on_every_shape(self):
        for label, build in FIXTURES.items():
            for name, make in (('as written', build), ('as published', lambda: published(build()))):
                with self.subTest(fixture=label, form=name):
                    report = make()
                    expected = decided(legacy_summary(report), report)
                    got = fallback_summary(read_report(report))
                    if got['video_standard'] is None:
                        got['video_standard'] = 'HINT'
                    self.assertEqual(expected, got)

    def test_summary_takes_a_raw_report_or_a_path_too(self):
        report = published(console16_report('snes', main=40, device=250))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'conversion-report.json'
            path.write_text(json.dumps(report), encoding='utf-8')
            self.assertEqual(fallback_summary(read_report(report)), fallback_summary(report))
            self.assertEqual(fallback_summary(read_report(report)), fallback_summary(path))
            self.assertEqual(read_report(report), read_report(path))

    def test_the_callers_read_reports_through_the_summary_and_no_longer_replicate_it(self):
        folder = Path(retrorecomp.__file__).parent
        expressions = (
            "main_interpreted(c) for c in report['final_checks']",
            "device=device_summary(report)",
            "c.get('audio_interpreted_opcodes', 0) for c in report['final_checks']",
            "p for p in measured if p is not None",
            "c.get('interpreter_cycles', 0) for c in report['final_checks']",
            "reference_vdp_trace_match=report.get('reference_vdp_trace_match')")
        for module in ('batch.py', 'gui.py'):
            # gui.py stands for the whole window: gui.py and the gui_*.py modules (docs/ARCHITECTURE.md).
            source = (gui_source() if module == 'gui.py' else (folder / module).read_text(encoding='utf-8')).replace('"', "'")
            with self.subTest(module=module):
                self.assertIn('fallback_summary(report, lenient=True)', source)
                for expression in expressions:
                    self.assertNotIn(expression, source)

    def test_what_changed_on_purpose_and_what_is_kept(self):
        # Game Boy measured 900 interpreted instructions. The old expression read a key its rows never had
        # and showed 0; the summary now carries the measurement (the window still shows Game Boy in cycles).
        report = read_report(gb_report(cycles=5000, instructions=900))
        self.assertEqual(report['cpus'][0]['scenarios'][0]['interpreted'], 900)
        self.assertEqual(fallback_summary(report)['main_interpreted_opcodes'], 900)
        self.assertEqual(fallback_summary(report)['interpreter_cycles'], 5000)
        # A count a writer does not carry still reads 0 in the summary and None in the report: cycles are
        # never turned into instructions.
        sms = read_report(sms_report(cycles=10))
        self.assertIsNone(sms['cpus'][0]['scenarios'][0]['interpreted'])
        self.assertEqual(fallback_summary(sms)['main_interpreted_opcodes'], 0)
        nes = read_report(nes_report(cycles=10))
        self.assertEqual(fallback_summary(nes)['main_interpreted_opcodes'], 0)
        # The X68000 writer stores null now. An export of an earlier release stored a constant True: the
        # summary echoes what is stored, the report never turns it into a picture claim.
        self.assertIsNone(fallback_summary(x68_report())['reference_vdp_trace_match'])
        before = x68_report()
        before['reference_vdp_trace_match'] = True
        x68 = read_report(before)
        self.assertIs(fallback_summary(x68)['reference_vdp_trace_match'], True)
        self.assertIsNone(x68['validation']['cpu_fidelity']['evidence'])
        self.assertIs(x68['legacy']['reference_vdp_trace_match'], True)


class SchemaShape(unittest.TestCase):
    def test_every_shape_reads_into_the_same_complete_document(self):
        for label, make in FIXTURES.items():
            with self.subTest(fixture=label):
                raw = make()
                before = copy.deepcopy(raw)
                report = read_report(raw)
                self.assertEqual(raw, before, 'the input must not be modified')
                self.assertEqual(report['schema'], {'name': 'retro-recomp-report', 'version': SCHEMA_VERSION})
                self.assertEqual(SCHEMA_VERSION, 2)
                self.assertEqual(tuple(report), REQUIRED_KEYS)
                self.assertEqual(tuple(report['validation']), MEASURES)
                json.dumps(report)
                self.assertEqual(read_report(report), report, 'a schema 2 document reads as itself')
                self.assertIsNot(read_report(report), report)
                self.assertEqual(report['system']['id'], raw['system']['id'])
                self.assertEqual(report['rom']['sha256'], SHA)

    def test_no_claim_is_stronger_than_a_stored_flag(self):
        for label, make in FIXTURES.items():
            with self.subTest(fixture=label):
                validation = read_report(make())['validation']
                for measure in validation.values():
                    self.assertNotIn('exact', measure['claim'].lower())
                self.assertIs(validation['hardware_fidelity']['validated'], False)
                self.assertEqual(validation['hardware_fidelity']['claim'], 'not validated')
                self.assertIs(validation['gameplay']['validated'], False)
                self.assertIs(validation['latency']['measured'], False)
                self.assertIsNone(validation['latency']['ms'])
                self.assertEqual(validation['latency']['claim'], 'not measured')
                self.assertIsNone(validation['gameplay']['owner_acceptance'])
                if validation['cpu_fidelity']['passed']:
                    self.assertIn('no independent CPU oracle', validation['cpu_fidelity']['claim'])

    def test_a_flag_the_writer_does_not_store_is_none_and_never_false(self):
        gb = read_report(gb_report())
        self.assertIsNone(gb['honesty']['independent_cpu_oracle'])
        self.assertIsNone(gb['honesty']['universal_zero_fallback_claim'])
        # Master System with the functions backend stores no validation record at all.
        gg = read_report(sms_report('gg', banked=False))
        self.assertIsNone(gg['validation']['cpu_fidelity']['passed'])
        self.assertEqual(gg['validation']['cpu_fidelity']['claim'], 'not reported')
        self.assertEqual(gg['validation']['cpu_fidelity']['scenarios'], [])
        self.assertIsNone(gb['created_utc'])
        self.assertIsNone(gb['target'])
        self.assertIsNone(gb['system']['status'])
        # A shape without a latency key at all says nothing instead of "not measured".
        stripped = sms_report()
        del stripped['latency_ms']
        self.assertIsNone(read_report(stripped)['validation']['latency']['measured'])
        self.assertEqual(read_report(stripped)['validation']['latency']['claim'], 'not reported')

    def test_units_and_sections_stay_separate(self):
        sms = read_report(sms_report(cycles=1234))
        self.assertEqual([cpu['id'] for cpu in sms['cpus']], ['main'])
        main = sms['cpus'][0]
        self.assertEqual((main['arch'], main['unit'], main['original_unit']), ('z80', 'instructions', 'cycles'))
        self.assertEqual(main['scenarios'][0]['cycles'], {'native': None, 'interpreted': 1234, 'total': 60_000_000})
        self.assertIsNone(main['scenarios'][0]['native'])
        self.assertIs(main['fallback_present'], True)
        nes = read_report(nes_report(cycles=4321))['cpus'][0]
        self.assertEqual((nes['arch'], nes['original_unit']), ('6502', 'cycles'))
        self.assertEqual(nes['scenarios'][0]['cycles']['interpreted'], 4321)
        gb = read_report(gb_report(cycles=5000, instructions=900))['cpus'][0]
        self.assertEqual((gb['scenarios'][0]['interpreted'], gb['scenarios'][0]['cycles']['interpreted']), (900, 5000))
        self.assertIsNone(gb['scenarios'][0]['interpreted_percent'])
        md = read_report(console16_report('md', main=17, audio=5))
        self.assertEqual([(cpu['id'], cpu['arch'], cpu['original_unit']) for cpu in md['cpus']],
                         [('main', 'm68000', 'instructions'), ('audio', 'z80', 'instructions')])
        self.assertEqual(md['cpus'][0]['scenarios'][0]['interpreted'], 17)
        self.assertEqual(md['cpus'][0]['scenarios'][0]['retired_interpreted'], 17)
        self.assertEqual(md['cpus'][1]['scenarios'][0]['interpreted'], 5)
        self.assertEqual(md['cpus'][1]['scenarios'][0]['cycles'], {'native': 2_000_000 - 20, 'interpreted': 20, 'total': None})
        self.assertEqual((md['cpus'][1]['mode'], md['cpus'][1]['reported_label']), ('hybrid', 'hybrid'))
        self.assertEqual(md['devices'], [])
        # Neo Geo and CPS-1 store the sound CPU's name, not a mode.
        ng = read_report(neogeo_report(audio=3))['cpus'][1]
        self.assertEqual((ng['arch'], ng['mode'], ng['reported_label']), ('z80', None, 'Z80'))
        self.assertEqual(len(read_report(x68_report())['cpus']), 1)
        self.assertEqual(len(read_report(gb_report())['cpus']), 1)

    def test_native_code_measure_counts_each_cpu_and_never_folds_them(self):
        zero = read_report(console16_report('md'))
        self.assertIs(zero['validation']['native_code']['fallback_present'], False)
        self.assertIs(zero['validation']['native_code']['zero_fallback_on_tested_scenarios'], True)
        audio_only = read_report(console16_report('md', audio=1))
        self.assertIs(audio_only['cpus'][0]['fallback_present'], False)
        self.assertIs(audio_only['cpus'][1]['fallback_present'], True)
        self.assertIs(audio_only['validation']['native_code']['fallback_present'], True)
        self.assertIs(audio_only['validation']['native_code']['zero_fallback_on_tested_scenarios'], False)
        # Counters the writer did not carry make the answer unknown, not zero fallback.
        unknown = sms_report()
        for row in unknown['final_checks']:
            del row['interpreter_cycles'], row['total_cycles']
        self.assertIsNone(read_report(unknown)['validation']['native_code']['fallback_present'])
        self.assertEqual(read_report(sms_report())['validation']['native_code']['claim'],
                         'native code on the tested scenarios only')

    def test_the_cartridge_device_is_its_own_section(self):
        for stored in (True, False):
            with self.subTest(stored_in_report=stored):
                raw = console16_report('snes', main=40, audio=2, device=6_000_000, stored_device=stored)
                report = read_report(raw)
                (device,) = report['devices']
                self.assertEqual((device['id'], device['kind'], device['mode']),
                                 ('superfx', 'cartridge_coprocessor', 'interpreted'))
                self.assertEqual(device['scenarios'][0]['interpreted'], 6_000_000)
                self.assertEqual(device['scenarios'][0]['per_frame'], round(6_000_000 / 3600, 3))
                self.assertIs(device['fallback_present'], True)
                # The 65816 count excludes the device's instructions.
                self.assertEqual(report['cpus'][0]['scenarios'][0]['interpreted'], 40)
                self.assertEqual(fallback_summary(report)['device'], device_summary(raw))
        self.assertEqual(read_report(console16_report('snes', main=3))['devices'], [])
        self.assertIsNone(fallback_summary(console16_report('snes', main=3))['device'])

    def test_scan_level_and_routes_come_from_where_each_writer_puts_them(self):
        levels = {'sms zero fallback': 'standard', 'gb zero fallback': 'standard', 'nes zero fallback': 'extended',
                  'md zero fallback': 'thorough', 'ng completed': 'extended', 'cps1 completed': 'standard',
                  'x68 zero fallback': 'standard'}
        for label, level in levels.items():
            with self.subTest(fixture=label):
                self.assertEqual(read_report(FIXTURES[label]())['scan']['level'], level)
        md = read_report(FIXTURES['md zero fallback']())['scan']
        self.assertEqual([(r['name'], r['kind'], r['frames']) for r in md['routes']],
                         [('long-1', 'long', 9000), ('authored', 'authored', 5000)])
        self.assertEqual(md['routes'][1]['script_sha256'], 'd' * 64)
        self.assertEqual(md['scenario_frames'], {'advanced': 4000})
        self.assertIs(md['enabled'], True)
        ng = read_report(neogeo_report())['scan']
        self.assertEqual([(r['name'], r['kind'], r['frames']) for r in ng['routes']], [('long-1', 'qualification_extra', 9000)])
        x68 = read_report(x68_report())['scan']
        self.assertEqual([(r['name'], r['kind']) for r in x68['routes']], [('mouse-1', 'exploration')])
        self.assertEqual(read_report(gb_report())['scan']['routes'], [])
        self.assertIsNone(read_report(gb_report())['scan']['enabled'])

    def test_cpu_fidelity_is_per_scenario_with_the_evidence_each_writer_has(self):
        sms = read_report(sms_report())['validation']['cpu_fidelity']
        self.assertEqual([(s['name'], s['match']) for s in sms['scenarios']], [('demo', True), ('play', True)])
        self.assertIs(sms['evidence']['reference_vdp_trace_match'], True)
        self.assertIn('SAME', sms['reference'])
        nes = read_report(nes_report())['validation']['cpu_fidelity']
        self.assertIs(nes['independent_cpu_oracle'], False)
        self.assertEqual(nes['scenarios'][0]['hashes'], {'pcm': 'c' * 64})
        self.assertEqual(read_report(gb_report())['validation']['cpu_fidelity']['scenarios'][0]['match'], True)
        md = read_report(console16_report('md'))['validation']['cpu_fidelity']
        self.assertIs(md['validated_flag'], False)
        self.assertEqual(md['reference'], 'internal_shared_semantics')
        self.assertEqual([s['match'] for s in md['scenarios']], [True, True])
        ng = read_report(neogeo_report())['validation']['cpu_fidelity']
        self.assertIs(ng['agreement'], True)
        self.assertEqual(ng['scenarios'][0]['hashes']['hardware'], '3' * 16)
        self.assertEqual(ng['scenarios'][0]['hashes']['pcm'], '6' * 16)
        cps1 = read_report(cps1_report())['validation']
        self.assertEqual(cps1['hardware_fidelity']['evidence'][0]['kind'], 'mame_comparison')
        self.assertEqual(read_report(neogeo_report())['validation']['hardware_fidelity']['evidence'],
                         [{'kind': 'hardware_specification_checks', 'count': 136}])
        broken = console16_report('md')
        broken['native_validation']['comparisons'][0]['differences'] = ['final_ram']
        failed = read_report(broken)['validation']['cpu_fidelity']
        self.assertIs(failed['scenarios'][0]['match'], False)
        self.assertEqual(failed['scenarios'][0]['differences'], ['final_ram'])

    def test_states_saves_packed_and_the_rest(self):
        sms = read_report(sms_report())
        self.assertEqual((sms['states']['save_key'], sms['states']['machine'], sms['states']['rom_identity']), ('F8', 1, 'sha256'))
        self.assertIsNone(sms['saves'])
        self.assertIsNone(sms['packed'], 'a report not yet published carries no packing record')
        self.assertEqual(sms['knowledge']['library_identity'], SHA)
        self.assertEqual(sms['runtime']['runtime_feedback'], {'fingerprint': 'f' * 8})
        self.assertEqual(sms['build']['wall_seconds'], 120.5)
        self.assertEqual(sms['build']['directory'], 'C:/build')
        nes = read_report(nes_report())
        self.assertEqual(nes['states']['compatibility'], 'same ROM')
        self.assertIsNone(nes['states']['save_key'])
        self.assertEqual(nes['runtime']['host_timing'], {'sample_rate': 48000})
        md = read_report(console16_report('md'))
        self.assertEqual(md['saves']['cartridge_memory'], {'kind': 'sram', 'bytes': 8192})
        self.assertIsNone(md['saves']['supported'])
        ng = read_report(published(neogeo_report()))
        self.assertIs(ng['saves']['supported'], True)
        self.assertEqual(ng['states']['validation'], {'fresh_process': True, 'invalid_rejected': 2})
        self.assertEqual(ng['packed']['replay'], {'done': True, 'routes': 2, 'match': True, 'candidate_sha256': 'e' * 64})
        self.assertEqual((ng['packed']['packer'], ng['packed']['version'], ng['packed']['is_packed']), ('UPX', '5.3.0', True))
        self.assertEqual(ng['packed']['published'], {'bytes': 1200, 'sha256': '2' * 64})
        self.assertEqual(ng['build']['phases_seconds'], {'packed_replays': 20.0})
        cps1 = read_report(cps1_report())
        self.assertIs(cps1['saves']['supported'], False)
        self.assertIn('no non-volatile', cps1['saves']['reason'])
        self.assertEqual(cps1['packed']['replay']['routes'], 2)
        self.assertIsNone(cps1['packed']['unpacked'])
        # A published report of a console that never replays the packed file says so by having no replay.
        self.assertIsNone(read_report(published(sms_report()))['packed']['replay'])
        self.assertIs(read_report(published(sms_report()))['packed']['is_packed'], True)
        x68 = read_report(x68_report())
        self.assertIs(x68['states']['fresh_process_verified'], True)
        self.assertEqual(x68['rom']['source_identity'], 'b' * 64)
        self.assertEqual(x68['build']['directory'], 'C:/q')
        self.assertEqual(x68['target'], 'windows-x86_64')
        self.assertEqual(x68['build']['wall_seconds'], 1800.25)
        self.assertEqual(x68['validation']['native_code']['coverage_note'], 'observed exact RAM encodings with live word guards')
        self.assertIsNone(x68['validation']['native_code']['coverage'])
        self.assertIsNone(read_report(cps1_report())['validation']['native_code']['coverage'])

    def test_upgrade_and_receipt_are_carried_as_written(self):
        discovery = {'version': '1.4.0', 'scan_level': 'thorough', 'final_checks': []}
        raw = published(sms_report(), upgrade={'check_level': 'quick', 'discovery': discovery})
        raw['export_receipt'] = {'schema': 3, 'sha256': '3' * 64}
        report = read_report(raw)
        self.assertEqual(report['upgrade'], {'check_level': 'quick', 'discovery': discovery})
        self.assertEqual(report['export_receipt'], {'schema': 3, 'sha256': '3' * 64})
        self.assertIsNone(read_report(sms_report())['upgrade'])


class UnknownShapes(unittest.TestCase):
    def test_documents_no_writer_produces_are_refused_clearly(self):
        no_system = sms_report()
        del no_system['system']
        no_checks = sms_report()
        del no_checks['final_checks']
        bad_rows = sms_report()
        bad_rows['final_checks'] = [1, 2]
        wrong_writer = gb_report()
        wrong_writer['system'] = {'id': 'nes', 'name': 'NES'}
        cases = {
            'a list': [],
            'a number': 42,
            'not a Retro-Recomp report': {**sms_report(), 'tool': 'Other'},
            'no tool': {'system': {'id': 'sms'}, 'final_checks': []},
            'no system': no_system,
            'unknown console': {**sms_report(), 'system': {'id': 'n64', 'name': 'Nintendo 64'}},
            'no final checks': no_checks,
            'rows that are not records': bad_rows,
            'another console\'s shape': wrong_writer,
            'unknown schema name': {'schema': {'name': 'other', 'version': 2}},
            'schema as text': {'schema': 2},
        }
        for label, document in cases.items():
            with self.subTest(case=label):
                with self.assertRaises(ReportShapeError):
                    read_report(document)
                with self.assertRaises(ValueError):
                    fallback_summary(document)

    def test_a_newer_or_damaged_schema_2_document_is_refused_never_misread(self):
        report = read_report(sms_report())
        newer = copy.deepcopy(report)
        newer['schema']['version'] = 3
        with self.assertRaisesRegex(ReportShapeError, '3'):
            read_report(newer)
        incomplete = copy.deepcopy(report)
        del incomplete['cpus']
        del incomplete['validation']['latency']
        with self.assertRaisesRegex(ReportShapeError, 'cpus.*validation.latency'):
            read_report(incomplete)

    def test_a_path_that_is_not_json_is_refused_and_a_missing_one_is_an_os_error(self):
        with tempfile.TemporaryDirectory() as folder:
            broken = Path(folder) / 'conversion-report.json'
            broken.write_text('{not json', encoding='utf-8')
            with self.assertRaises(ReportShapeError):
                read_report(broken)
            with self.assertRaises(OSError):
                read_report(Path(folder) / 'absent.json')


class Registration(unittest.TestCase):
    def test_the_reader_is_an_interface_module(self):
        self.assertIn('report_schema', INTERFACE_MODULES)
        self.assertEqual(report_schema.SCHEMA_VERSION, 2)
        self.assertEqual(report_schema.SCHEMA_NAME, 'retro-recomp-report')

    def test_the_shapes_are_read_from_the_profiles(self):
        from retrorecomp.systems import ALL_PROFILES
        shapes = report_schema._SHAPES
        self.assertEqual(set(shapes), {profile.id for profile in ALL_PROFILES})
        for profile in ALL_PROFILES:
            shape = shapes[profile.id]
            main = next(cpu for cpu in profile.cpus if cpu.role == 'main')
            sound = next((cpu for cpu in profile.cpus if cpu.role == 'sound'), None)
            with self.subTest(console=profile.id):
                self.assertEqual((shape.writer, shape.marker), (profile.report_shape.writer, profile.report_shape.marker))
                self.assertEqual((shape.main_arch, shape.main_unit), (main.arch, main.unit))
                self.assertEqual(shape.audio_arch, sound.arch if sound else None)

    def test_a_machine_registered_later_is_read_without_editing_the_module(self):
        from retrorecomp.systems import registry
        from retrorecomp.systems.specs import ReportShape
        from tests.test_registration_surface import SyntheticProfile

        class WithReport(SyntheticProfile):
            report_shape = ReportShape('core', 'strict_checks')

        self.assertNotIn('zz', report_schema._SHAPES)
        registry.register(WithReport())
        try:
            self.assertEqual(report_schema._SHAPES['zz'].writer, 'core')
            document = read_report(sms_report('zz'))
            self.assertEqual(document['system']['id'], 'zz')
            self.assertEqual(document['cpus'][0]['arch'], 'm68000')
        finally:
            registry.unregister('zz')
        self.assertNotIn('zz', report_schema._SHAPES)
        with self.assertRaises(ReportShapeError):
            read_report(sms_report('zz'))

    def test_a_machine_that_declines_a_report_has_no_shape(self):
        from retrorecomp.systems import registry
        from tests.test_registration_surface import SyntheticProfile
        registry.register(SyntheticProfile())
        try:
            self.assertNotIn('zz', report_schema._SHAPES)
        finally:
            registry.unregister('zz')


class RamSingleStepTests(unittest.TestCase):
    """Game Boy: WRAM/HRAM code run one instruction at a time is counted apart, and is never reported as native only."""

    @staticmethod
    def counted(report, stub=0, single=0, highmem=0):
        for rows in (report['final_checks'], report['history']):
            for row in rows:
                row.update(ram_stub_instructions=stub, ram_stub_cycles=stub * 8,
                           ram_single_step_instructions=single, ram_single_step_cycles=single * 6,
                           highmem_stub_instructions=highmem, highmem_stub_cycles=highmem * 4)
        return report

    def test_the_counts_reach_the_report_and_make_the_native_claim_false(self):
        report = read_report(self.counted(gb_report(), stub=3, single=5, highmem=2))
        scenario = report['cpus'][0]['scenarios'][0]
        self.assertEqual(scenario['ram_single_step'], {'stub_instructions': 3, 'stub_cycles': 24,
                                                       'single_step_instructions': 5, 'single_step_cycles': 30,
                                                       'highmem_stub_instructions': 2, 'highmem_stub_cycles': 8})
        # Not an interpreter session: the interpreter figures stay at zero.
        self.assertEqual(scenario['interpreted'], 0)
        self.assertFalse(report['cpus'][0]['fallback_present'])
        self.assertTrue(report['cpus'][0]['ram_single_step_present'])
        native = report['validation']['native_code']
        self.assertTrue(native['ram_single_step_present'])
        self.assertIs(native['zero_fallback_on_tested_scenarios'], False)
        self.assertNotIn('only', native['claim'].replace('one at a time', ''))
        self.assertIn('not native code', native['claim'])
        summary = fallback_summary(report)
        self.assertEqual(summary['interpreter_cycles'], 0)
        self.assertEqual((summary['ram_one_by_one_instructions'], summary['ram_one_by_one_cycles']), (10, 62))

    def test_highmem_stub_alone_counts_and_a_missing_figure_is_not_a_zero(self):
        report = read_report(self.counted(gb_report(), highmem=1))
        native = report['validation']['native_code']
        self.assertIs(report['cpus'][0]['ram_single_step_present'], True)
        self.assertIs(native['zero_fallback_on_tested_scenarios'], False)
        self.assertEqual(fallback_summary(report)['ram_one_by_one_instructions'], 1)
        # A row written before the high-memory figure existed: the other two being zero proves nothing about it.
        data = self.counted(gb_report())
        for rows in (data['final_checks'], data['history']):
            for row in rows:
                row.pop('highmem_stub_instructions', None)
                row.pop('highmem_stub_cycles', None)
        partial = read_report(data)
        self.assertIsNone(partial['cpus'][0]['ram_single_step_present'])
        self.assertIsNone(partial['validation']['native_code']['ram_single_step_present'])

    def test_zero_counts_keep_the_native_claim_and_other_writers_are_unchanged(self):
        report = read_report(self.counted(gb_report()))
        native = report['validation']['native_code']
        self.assertIs(report['cpus'][0]['ram_single_step_present'], False)
        self.assertIs(native['zero_fallback_on_tested_scenarios'], True)
        self.assertEqual(native['claim'], 'native code on the tested scenarios only')
        self.assertEqual(fallback_summary(report)['ram_one_by_one_instructions'], 0)
        # An older Game Boy report (no counts) and a writer that does not count them: not measured, no new summary keys.
        for old in (read_report(gb_report()), read_report(sms_report(cycles=0))):
            self.assertIsNone(old['cpus'][0]['ram_single_step_present'])
            self.assertIsNone(old['validation']['native_code']['ram_single_step_present'])
            self.assertNotIn('ram_one_by_one_instructions', fallback_summary(old))

    def test_a_library_entry_with_such_instructions_is_not_a_clean_game(self):
        import json
        import tempfile
        from pathlib import Path
        from retrorecomp.compiled_games import game_from_report
        with tempfile.TemporaryDirectory() as folder:
            for label, report, expected in (('clean', self.counted(gb_report()), False),
                                            ('stub', self.counted(gb_report(), stub=1), True),
                                            ('single', self.counted(gb_report(), single=2), True),
                                            ('highmem', self.counted(gb_report(), highmem=1), True)):
                path = Path(folder) / f'{label}.json'
                path.write_text(json.dumps(report), encoding='utf-8')
                game = game_from_report(path, Path(folder))
                self.assertIs(game.tested_fallback, expected, label)
                self.assertEqual(game.status, 'fallback' if expected else 'no_hints', label)


if __name__ == '__main__':
    unittest.main()
