"""Conversion report schema 2, and the one reader of every report shape.

Seven converters write ``conversion-report.json`` in seven different shapes
(Master System and Game Gear, Game Boy, NES, Mega Drive and Super Nintendo,
Neo Geo, CPS-1, X68000). This module is the only place that knows them all.
``read_report`` turns any of them into the schema-2 document described below;
``fallback_summary`` is the one-line interpreter summary the batch result and
the window both compute from a report. Nothing here writes a report: the
writers switch to schema 2 later, and until then the reader is the bridge.

Rules the reader keeps (docs/STANDARDS.md, rules 6 to 8):

* A field the report does not carry is ``None`` (or an empty list), never
  invented, never zero. Zero means a writer measured zero.
* A count is never converted from one unit to another. Interpreted counts are
  held in one unit, **instructions**, per CPU and per scenario; when a writer
  only counted cycles (Master System, Game Gear, Game Boy, NES) the cycles are
  kept beside them under ``cycles`` and the instruction count stays ``None``
  unless the writer measured it too (Game Boy does).
* The five measures (native code, CPU fidelity, hardware fidelity, gameplay,
  latency) are five sibling objects under ``validation``. None is derived from
  another, each carries a ``claim`` string, and no claim is stronger than the
  flag the writer stored.
* Main CPU, sound CPU and cartridge devices are separate sections; their
  counters are never added together.
* A shape the reader does not know raises ``ReportShapeError``. A schema number
  it does not know raises it too, so a newer document is never misread.

Schema 2 (every key is always present; see ``REQUIRED_KEYS``)::

    schema        {'name': 'retro-recomp-report', 'version': 2}
    read_from     {'schema_version': 1 | 2, 'writer': 'core' | 'gameboy' | ...}
    tool, version, created_utc, target     as written, else None
    system        {'id', 'name', 'status'}  status as the writer stored it
    rom           the writer's ROM record; source_identity (X68000) beside it
    scan          {'level', 'enabled', 'scenario_frames', 'routes': [...]}
    cpus          [{'id': 'main' | 'audio', 'arch', 'role', 'unit': 'instructions',
                    'original_unit': 'instructions' | 'cycles', 'mode',
                    'reported_label', 'fallback_present',
                    'scenarios': [{'name', 'frames', 'native', 'interpreted',
                                   'interpreted_percent', 'cycles', ...}]}]
    devices       [{'id', 'kind': 'cartridge_coprocessor', 'unit', 'mode',
                    'failed', 'fallback_present', 'scenarios': [...]}]
    validation    {'native_code', 'cpu_fidelity', 'hardware_fidelity',
                   'gameplay', 'latency'}
    honesty       the writer's own claim flags, as stored (None when absent)
    packed        {'packer', ..., 'unpacked', 'published', 'replay'} | None
    states        {'supported', 'save_key', 'load_key', 'slots', ...} | None
    saves         {'supported', 'reason', 'scope', 'path', 'validation',
                   'cartridge_memory'} | None
    runtime       {'input_players', 'video_model', 'peripheral',
                   'host_timing', 'runtime_feedback'}
    knowledge     {'record', 'learning', 'library_identity', 'shared_paths',
                   'bundled_paths'}
    build         {'executable', 'build_executable', 'toolchain', ...}
    upgrade, export_receipt                 as written, else None
    legacy        keys of the old shapes with no schema-2 home yet
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path

SCHEMA_NAME = 'retro-recomp-report'
SCHEMA_VERSION = 2

REQUIRED_KEYS = ('schema', 'read_from', 'tool', 'version', 'created_utc', 'target', 'system', 'rom', 'scan',
                 'cpus', 'devices', 'validation', 'honesty', 'packed', 'states', 'saves', 'runtime',
                 'knowledge', 'build', 'upgrade', 'export_receipt', 'legacy')
MEASURES = ('native_code', 'cpu_fidelity', 'hardware_fidelity', 'gameplay', 'latency')


class ReportShapeError(ValueError):
    """The document is not a report any known writer produces (or not a known schema)."""


@dataclass(frozen=True)
class _Shape:
    writer: str         # the module that writes this shape
    marker: str         # a top-level key only this writer emits
    main_arch: str
    audio_arch: str | None
    main_unit: str      # unit of the writer's own main CPU counters


_SHAPES = {
    'sms': _Shape('core', 'strict_checks', 'z80', None, 'cycles'),
    'gg': _Shape('core', 'strict_checks', 'z80', None, 'cycles'),
    'gb': _Shape('gameboy', 'generated_build', 'sm83', None, 'cycles'),
    'nes': _Shape('nes', 'host_audio', '6502', None, 'cycles'),
    'md': _Shape('console16', 'native_percentage', 'm68000', 'z80', 'instructions'),
    'snes': _Shape('console16', 'native_percentage', '65816', 'spc700', 'instructions'),
    'ng': _Shape('neogeo_conversion', 'prepared_cartridge', 'm68000', 'z80', 'instructions'),
    'cps1': _Shape('cps1_conversion', 'native_analysis', 'm68000', 'z80', 'instructions'),
    'x68': _Shape('x68000_conversion', 'exploration_checks', 'm68000', None, 'instructions'),
}
_AUDIO_KEYS = ('audio_native_opcodes', 'audio_interpreted_opcodes', 'audio_native_cycles', 'audio_interpreted_cycles')
_AUDIO_MODES = ('native', 'hybrid', 'interpreted')


# ---------------------------------------------------------------- helpers

def _dict(value):
    return value if isinstance(value, dict) else {}


def _copy(value):
    return copy.deepcopy(value)


def _count(value):
    """A measured number, else None (booleans and text are not counts)."""
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _flag(value):
    return value if isinstance(value, bool) else None


def _claim(flag, yes, no='not validated'):
    """A claim string that is never stronger than the stored flag."""
    return 'not reported' if flag is None else yes if flag else no


def _first(*values):
    return next((value for value in values if value is not None), None)


# ---------------------------------------------------------------- scenarios

def _scenario_name(row):
    return _first(row.get('scenario'), row.get('name'), row.get('route'))


def _main_scenario(writer, row):
    """One final-check row as a main-CPU scenario, in the one unit (instructions)."""
    name, frames = _scenario_name(row), _count(row.get('frames'))
    cycles, native, interpreted, extra = None, None, None, {}
    if writer == 'core':
        frames = _count(row.get('requested_frames'))
        cycles = {'native': None, 'interpreted': _count(row.get('interpreter_cycles')),
                  'total': _count(row.get('total_cycles'))}
    elif writer == 'gameboy':
        interpreted = _count(row.get('interpreter_instructions'))
        cycles = {'native': None, 'interpreted': _count(row.get('interpreter_cycles')), 'total': None}
    elif writer == 'nes':
        cycles = {'native': _count(row.get('native_cycles')), 'interpreted': _count(row.get('interpreter_cycles')),
                  'total': _count(row.get('cycles')), 'interpreted_rom': _count(row.get('interpreter_rom_cycles')),
                  'interpreted_ram': _count(row.get('interpreter_ram_cycles')),
                  'interpreted_other': _count(row.get('interpreter_other_cycles'))}
    else:
        native = _count(row.get('native_entries'))
        # The 65816 count, never the cartridge device's (snes_chips.main_interpreted).
        interpreted = _count(_first(row.get('main_interpreted_opcodes'), row.get('interpreted_opcodes')))
        if row.get('retired_interpreted_opcodes') is not None:
            extra['retired_interpreted'] = _count(row.get('retired_interpreted_opcodes'))
    return {'name': name, 'frames': frames, 'native': native, 'interpreted': interpreted,
            'interpreted_percent': _count(row.get('interpreter_percent')), 'cycles': cycles, **extra}


def _audio_scenario(row):
    cycles = None
    if row.get('audio_native_cycles') is not None or row.get('audio_interpreted_cycles') is not None:
        cycles = {'native': _count(row.get('audio_native_cycles')),
                  'interpreted': _count(row.get('audio_interpreted_cycles')), 'total': None}
    return {'name': _scenario_name(row), 'frames': _count(row.get('frames')),
            'native': _count(row.get('audio_native_opcodes')),
            'interpreted': _count(row.get('audio_interpreted_opcodes')),
            'interpreted_percent': None, 'cycles': cycles}


def _fallback_state(scenarios):
    """True when any scenario interpreted something, False when every one measured none, else None."""
    values = []
    for scenario in scenarios:
        values.append([scenario.get('interpreted'), _dict(scenario.get('cycles')).get('interpreted')])
    if any(v is not None and v > 0 for pair in values for v in pair):
        return True
    if values and all(any(v is not None for v in pair) for pair in values):
        return False
    return None


def _cpus(shape, data, rows):
    main = {'id': 'main', 'arch': shape.main_arch, 'role': 'main', 'unit': 'instructions',
            'original_unit': shape.main_unit, 'mode': None, 'reported_label': None,
            'scenarios': [_main_scenario(shape.writer, row) for row in rows]}
    main['fallback_present'] = _fallback_state(main['scenarios'])
    cpus = [main]
    if shape.audio_arch and ('audio_cpu' in data or any(key in row for row in rows for key in _AUDIO_KEYS)):
        label = data.get('audio_cpu')
        audio = {'id': 'audio', 'arch': shape.audio_arch, 'role': 'audio', 'unit': 'instructions',
                 'original_unit': 'instructions',
                 # The Mega Drive and Super Nintendo store a mode; Neo Geo and CPS-1 store the CPU's name.
                 'mode': label if label in _AUDIO_MODES else None, 'reported_label': label,
                 'scenarios': [_audio_scenario(row) for row in rows]}
        audio['fallback_present'] = _fallback_state(audio['scenarios'])
        cpus.append(audio)
    return cpus


def _device(data, rows):
    """The cartridge device apart from the CPUs (the logic of snes_chips.device_entry, without the import)."""
    stored = data.get('cartridge_device')
    if stored:
        if not isinstance(stored, dict) or not isinstance(stored.get('scenarios'), list):
            return None
        chip, mode = stored.get('chip'), stored.get('mode')
        unit, failed = stored.get('counter_unit'), stored.get('failed')
        entries = [{'name': row.get('scenario'), 'frames': _count(row.get('frames')),
                    'interpreted': _count(row.get('interpreted_instructions')),
                    'per_frame': _count(row.get('interpreted_per_frame')), 'commands': _count(row.get('commands'))}
                   for row in stored['scenarios'] if isinstance(row, dict)]
    else:
        chip = next((row['cartridge_chip'] for row in rows
                     if row.get('cartridge_chip') not in (None, 'none')), None)
        if chip is None:
            return None
        mode, unit = rows[-1].get('coprocessor_mode', 'not_run'), 'device instructions'
        failed = any(row.get('coprocessor_failed') for row in rows)
        entries = []
        for row in rows:
            count, frames = int(row.get('coprocessor_instructions') or 0), int(row.get('frames') or 0)
            entries.append({'name': row.get('scenario'), 'frames': frames, 'interpreted': count,
                            'per_frame': round(count / max(1, frames), 3),
                            'commands': int(row.get('coprocessor_commands') or 0)})
    if chip is None:
        return None
    device = {'id': chip, 'kind': 'cartridge_coprocessor', 'unit': unit or 'device instructions', 'mode': mode,
              'failed': _flag(failed), 'scenarios': entries}
    device['fallback_present'] = _fallback_state([{'interpreted': entry['interpreted']} for entry in entries])
    return device


# ---------------------------------------------------------------- scan

def _route(entry, kind):
    entry = _dict(entry)
    return {'name': _first(entry.get('scenario'), entry.get('name')), 'kind': _first(entry.get('kind'), kind),
            'frames': _count(entry.get('frames')), 'steps': _count(entry.get('steps')),
            'continues_from': entry.get('continues_from'), 'script_sha256': entry.get('script_sha256')}


def _scan(shape, data, rows):
    advanced = _dict(data.get('advanced_scan'))
    routes = [_route(entry, 'long') for entry in _first(data.get('long_routes'), advanced.get('long_routes')) or ()]
    routes += [_route(entry, 'authored') for entry in advanced.get('authored_routes') or ()]
    for name, entry in _dict(data.get('qualification_extra_routes')).items():
        routes.append(_route({'name': name, **_dict(entry)}, 'qualification_extra'))
    if shape.writer == 'x68000_conversion':
        routes += [_route({'name': row.get('route'), 'frames': row.get('frames')}, 'exploration')
                   for row in _dict_rows(data.get('exploration_checks'))]
    if shape.writer == 'cps1_conversion':
        routes += [_route(row, 'validation') for row in rows]
    return {'level': _first(data.get('scan_level'), advanced.get('level')), 'enabled': _flag(advanced.get('enabled')),
            'scenario_frames': _copy(advanced.get('scenario_frames')), 'routes': routes}


def _dict_rows(value):
    return [row for row in value or () if isinstance(row, dict)]


# ---------------------------------------------------------------- validation

def _cpu_scenarios(shape, data, rows):
    """Per-scenario agreement with the writer's own reference."""
    validation = _dict(data.get('native_validation'))
    writer = shape.writer
    if writer == 'core':
        return [{'name': item.get('scenario'), 'frames': None, 'match': _flag(item.get('passed')),
                 'checks': _copy(item.get('checks')), 'hashes': None}
                for item in _dict_rows(validation.get('scenarios'))]
    if writer == 'gameboy':
        return [{'name': item.get('scenario'), 'frames': _count(item.get('frames')),
                 'match': True if 'Matched' in str(item.get('result')) else None, 'checks': None, 'hashes': None}
                for item in _dict_rows(validation.get('scenarios'))]
    if writer == 'nes':
        return [{'name': item.get('scenario'), 'frames': _count(item.get('frames')),
                 'match': True if item.get('internal_differential') is True and item.get('audio_pcm_match') is True
                 else None, 'checks': None, 'hashes': {'pcm': item.get('audio_pcm_sha256')}}
                for item in _dict_rows(validation.get('scenarios'))]
    if writer == 'console16':
        return [{'name': item.get('scenario'), 'frames': _count(item.get('frames')),
                 'match': (not item['differences']) if isinstance(item.get('differences'), list) else None,
                 'checks': None, 'hashes': None, 'differences': _copy(item.get('differences'))}
                for item in _dict_rows(validation.get('comparisons'))]
    keys = {'cpu': 'cpu_hash', 'ram': 'ram_hash', 'image': 'image_hash', 'pcm': 'pcm_hash',
            'hardware': 'hardware_hash', 'z80': 'z80_hash'}
    return [{'name': _scenario_name(row), 'frames': _count(row.get('frames')), 'match': _flag(row.get('reference_match')),
             'checks': None, 'hashes': {name: row[key] for name, key in keys.items() if key in row}}
            for row in rows]


def _reference_kind(shape, data):
    validation = _dict(data.get('native_validation'))
    return _first(validation.get('reference_kind'), validation.get('method'), validation.get('scope'),
                  data.get('reference_scope'))


def _cpu_fidelity(shape, data, rows):
    validation = _dict(data.get('native_validation'))
    passed = _flag(validation.get('passed'))
    oracle = _flag(validation.get('independent_cpu_oracle'))
    evidence = None
    if shape.writer == 'core':
        # Comparisons against the interpreter over the same video, audio and memory runtime.
        evidence = {key: data.get(key) for key in ('reference_vdp_trace_match', 'reference_final_ram_match',
                                                   'reference_final_cpu_match', 'reference_final_png_match')
                    if key in data}
    if passed is None:
        claim = 'not reported'
    elif not passed:
        claim = 'did not pass'
    elif oracle:
        claim = 'agreement with a reference the writer reports as independent, on the tested scenarios'
    else:
        claim = 'agreement with the project\'s own reference on the tested scenarios; no independent CPU oracle'
    return {'passed': passed, 'reference': _reference_kind(shape, data),
            'validated_flag': _flag(validation.get('cpu_fidelity_validated')),
            'independent_cpu_oracle': oracle, 'agreement': _flag(validation.get('cpu_agreement')),
            'scenarios': _cpu_scenarios(shape, data, rows) if validation else [],
            'evidence': evidence, 'claim': claim}


def _hardware_flag(data):
    validation = _dict(data.get('native_validation'))
    return _flag(_first(data.get('hardware_accuracy_validated'), validation.get('hardware_fidelity_validated'),
                        validation.get('hardware_accuracy'),
                        _dict(data.get('video_model')).get('hardware_accuracy_validated')))


def _full_game_flag(data):
    validation = _dict(data.get('native_validation'))
    return _flag(_first(data.get('full_game_validated'), validation.get('full_game_validated'),
                        validation.get('full_game'), _dict(data.get('advanced_scan')).get('full_game')))


def _latency(data):
    measured = _flag(_first(data.get('physical_latency_measured'),
                            _dict(data.get('host_timing')).get('physical_latency_measured')))
    figure = _count(data.get('latency_ms'))
    # A writer that stores latency_ms null has no figure: that is "not measured", not a zero.
    if measured is None and 'latency_ms' in data and figure is None:
        measured = False
    return measured, figure


def _validation(shape, data, rows, cpus, devices):
    sections = [*cpus, *devices]
    states = [section['fallback_present'] for section in sections]
    present = True if any(state is True for state in states) else False if states and all(
        state is False for state in states) else None
    hardware, full_game = _hardware_flag(data), _full_game_flag(data)
    measured, figure = _latency(data)
    scope = _dict(data.get('qualification_scope'))
    evidence = []
    if data.get('native_validation') and _dict(data['native_validation']).get('mame_comparison'):
        evidence.append({'kind': 'mame_comparison', 'note': data['native_validation']['mame_comparison']})
    if scope.get('hardware_specification_checks') is not None:
        evidence.append({'kind': 'hardware_specification_checks', 'count': scope['hardware_specification_checks']})
    coverage = data.get('native_coverage')
    return {
        'native_code': {
            'fallback_present': present,
            'zero_fallback_on_tested_scenarios': None if present is None else not present,
            'scenarios_checked': len(rows),
            'coverage': _copy(coverage) if isinstance(coverage, dict) else None,
            'coverage_note': coverage if isinstance(coverage, str) else None,
            'claim': 'native code on the tested scenarios only'},
        'cpu_fidelity': _cpu_fidelity(shape, data, rows),
        'hardware_fidelity': {'validated': hardware, 'evidence': evidence,
                              'claim': _claim(hardware, 'validated, as the writer reports')},
        'gameplay': {'validated': full_game, 'scenarios_run': len(rows) if rows else None, 'owner_acceptance': None,
                     'claim': 'tested routes only' if rows else 'not reported'},
        'latency': {'measured': measured, 'ms': figure,
                    'claim': _claim(measured, 'measured, as the writer reports', 'not measured')},
    }


def _honesty(data, validation):
    native = _dict(data.get('native_validation'))
    return {'hardware_fidelity_validated': validation['hardware_fidelity']['validated'],
            'full_game_validated': validation['gameplay']['validated'],
            'physical_latency_measured': validation['latency']['measured'],
            'independent_cpu_oracle': _flag(native.get('independent_cpu_oracle')),
            'cpu_fidelity_validated': _flag(native.get('cpu_fidelity_validated')),
            'universal_zero_fallback_claim': _flag(_dict(data.get('qualification_scope')).get('universal_zero_fallback_claim'))}


# ---------------------------------------------------------------- the other sections

def _packed(shape, data, rows):
    record = _dict(data.get('packing'))
    native = _dict(data.get('native_validation'))
    replay = None
    if native.get('packed_reference_match') is not None:
        # Neo Geo and CPS-1 compare the delivered, compressed executable with the fresh reference.
        replay = {'done': True, 'routes': len(rows), 'match': _flag(native.get('packed_reference_match')),
                  'candidate_sha256': data.get('packed_candidate_sha256')}
    if not record and replay is None:
        return None
    return {'recorded': record.get('recorded', True) if record else None, 'packer': record.get('packer'),
            'version': record.get('version'), 'level': record.get('level'), 'is_packed': _flag(record.get('packed')),
            'unpacked': _copy(record.get('unpacked')), 'published': _copy(record.get('published')),
            'size_ratio': _count(record.get('size_ratio')), 'compared_on': record.get('compared_on'),
            'replay': replay}


def _states(data):
    states = data.get('game_states')
    if not isinstance(states, dict):
        return None
    keys = ('supported', 'save_key', 'load_key', 'slots', 'compatibility', 'schema', 'machine', 'rom_identity',
            'fresh_process_verified')
    return {**{key: _copy(states.get(key)) for key in keys}, 'validation': _copy(states.get('validation'))}


def _saves(data):
    ordinary, memory = data.get('ordinary_saves'), data.get('cartridge_memory')
    if isinstance(ordinary, dict):
        return {'supported': _flag(ordinary.get('supported')), 'reason': ordinary.get('reason'),
                'scope': ordinary.get('scope'), 'path': ordinary.get('path'),
                'validation': _copy(ordinary.get('validation')), 'cartridge_memory': None}
    if memory is not None:
        # The Mega Drive and Super Nintendo store the cartridge's memory layout, not a verdict.
        return {'supported': None, 'reason': None, 'scope': None, 'path': None, 'validation': None,
                'cartridge_memory': _copy(memory)}
    return None


def _runtime(data):
    return {'input_players': data.get('input_players'), 'video_model': _copy(data.get('video_model')),
            'peripheral': _copy(data.get('peripheral')),
            'host_timing': _copy(_first(data.get('host_timing'), data.get('host_audio'))),
            'runtime_feedback': _copy(_first(data.get('runtime_feedback'),
                                             _dict(data.get('runtime_data')).get('runtime_feedback')))}


def _knowledge(data):
    return {'record': _copy(data.get('knowledge')), 'learning': _copy(data.get('learning')),
            'library_identity': _first(data.get('library_identity'),
                                       _dict(data.get('runtime_data')).get('library_identity')),
            'shared_paths': _copy(data.get('shared_paths')),
            'bundled_paths': _copy(data.get('bundled_paths'))}


def _build(data):
    return {'executable': data.get('executable'), 'build_executable': data.get('build_executable'),
            'executable_bytes': data.get('executable_bytes'), 'toolchain': _copy(data.get('toolchain')),
            'backend': data.get('backend'), 'compiler': _copy(data.get('compiler')),
            'engine_revision': data.get('engine_revision'), 'sdl_revision': data.get('sdl_revision'),
            'compiler_signature': _copy(data.get('compiler_signature')),
            'wall_seconds': _count(data.get('conversion_wall_seconds')),
            'phases_seconds': _copy(_first(data.get('conversion_phases_seconds'), data.get('stage_seconds'))),
            'directory': _first(data.get('build_directory'), data.get('qualification_directory')),
            'published_directory': data.get('published_directory'), 'source_rom': data.get('source_rom')}


# ---------------------------------------------------------------- entry points

def _validate_v2(data):
    version = _dict(data.get('schema')).get('version')
    if version != SCHEMA_VERSION:
        raise ReportShapeError(f'Report schema {version!r} is not known to this version '
                               f'(it reads 1, the seven older shapes, and {SCHEMA_VERSION}).')
    missing = [key for key in REQUIRED_KEYS if key not in data]
    missing += ['validation.' + measure for measure in MEASURES if measure not in _dict(data.get('validation'))]
    if missing:
        raise ReportShapeError('Schema 2 report is incomplete: missing ' + ', '.join(missing) + '.')
    return _copy(data)


def _load(data_or_path):
    if isinstance(data_or_path, (str, Path)):
        try:
            return json.loads(Path(data_or_path).read_text(encoding='utf-8'))
        except json.JSONDecodeError as error:
            raise ReportShapeError(f'{data_or_path}: not a JSON document ({error}).') from error
    return data_or_path


def read_report(data_or_path) -> dict:
    """Any conversion report of any writer, as a schema-2 document.

    Takes the parsed dict or the path of a ``conversion-report.json``. Never
    modifies its input. Raises ``ReportShapeError`` for a document no writer
    produces, so a caller can tell an unreadable report from a game without
    fallback. A schema-2 document is validated and returned as a copy.
    """
    data = _load(data_or_path)
    if not isinstance(data, dict):
        raise ReportShapeError('A conversion report is a JSON object.')
    if 'schema' in data:
        if _dict(data.get('schema')).get('name') != SCHEMA_NAME:
            raise ReportShapeError('Unknown report schema: ' + repr(data['schema']) + '.')
        return _validate_v2(data)
    if data.get('tool') != 'Retro-Recomp':
        raise ReportShapeError('Not a Retro-Recomp conversion report.')
    system = _dict(data.get('system'))
    shape = _SHAPES.get(system.get('id'))
    if shape is None:
        raise ReportShapeError(f'Unknown console in a report: {system.get("id")!r}.')
    rows = data.get('final_checks')
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ReportShapeError(f'The {system["id"]} report has no usable final_checks list.')
    if shape.marker not in data:
        raise ReportShapeError(f'The {system["id"]} report does not have the shape of the {shape.writer} writer '
                               f'(no {shape.marker!r}).')
    cpus, device = _cpus(shape, data, rows), _device(data, rows)
    devices = [device] if device else []
    validation = _validation(shape, data, rows, cpus, devices)
    report = {
        'schema': {'name': SCHEMA_NAME, 'version': SCHEMA_VERSION},
        'read_from': {'schema_version': 1, 'writer': shape.writer},
        'tool': data['tool'], 'version': data.get('version'), 'created_utc': data.get('created_utc'),
        'target': data.get('target'),
        'system': {'id': system['id'], 'name': system.get('name'), 'status': data.get('status')},
        'rom': {**_copy(_dict(data.get('rom'))), **({'source_identity': data['source_identity']}
                                                    if 'source_identity' in data else {})},
        'scan': _scan(shape, data, rows), 'cpus': cpus, 'devices': devices, 'validation': validation,
        'honesty': _honesty(data, validation), 'packed': _packed(shape, data, rows), 'states': _states(data),
        'saves': _saves(data), 'runtime': _runtime(data), 'knowledge': _knowledge(data), 'build': _build(data),
        'upgrade': _copy(data.get('upgrade')), 'export_receipt': _copy(data.get('export_receipt')),
        # Written by the old shapes, not yet given a schema-2 home. reference_vdp_trace_match is kept here
        # because the X68000 writer hard-codes it to True: it is not a measurement and is never mapped
        # to a picture claim above.
        'legacy': {'reference_vdp_trace_match': data.get('reference_vdp_trace_match'),
                   'native_coverage': _copy(data.get('native_coverage'))},
    }
    return report


def _is_schema2(report):
    return (isinstance(report, dict) and report.get('schema') == {'name': SCHEMA_NAME, 'version': SCHEMA_VERSION}
            and all(key in report for key in REQUIRED_KEYS))


def _cpu(report, role):
    return next((cpu for cpu in report['cpus'] if cpu.get('role') == role), None)


def fallback_summary(report) -> dict:
    """The interpreter fallback of a report, in the figures the batch result and the window show.

    Accepts a schema-2 document (or anything ``read_report`` accepts). Every figure
    is a maximum over the scenarios, never a sum, and each CPU and device is kept
    apart. These are the exact values ``batch.py`` and ``gui.py`` compute today from
    the old shapes (``conversion_stage``, ``main_interpreted_opcodes``, ``device``,
    ``audio_cpu``, ``audio_interpreted_opcodes``, ``interpreter_percent``,
    ``interpreter_cycles``, ``reference_vdp_trace_match``, ``video_standard``), so
    that a caller can switch without changing what is displayed. Two conventions of
    those callers are kept on purpose and are not measurements: a count the writer
    does not carry reads 0, and ``main_interpreted_opcodes`` is 0 for the shapes
    that count the main CPU in cycles (Master System, Game Gear, Game Boy, NES). The
    schema-2 sections hold the real ``None``. ``video_standard`` is None when the
    report has no video model; the callers supply their own default.
    """
    if not _is_schema2(report):
        report = read_report(report)
    main, audio = _cpu(report, 'main'), _cpu(report, 'audio')
    scenarios = main['scenarios'] if main else []
    percents = [s['interpreted_percent'] for s in scenarios if s['interpreted_percent'] is not None]
    device = report['devices'][0] if report['devices'] else None
    return {
        'conversion_stage': report['system'].get('status'),
        'main_interpreted_opcodes': max((s['interpreted'] or 0 for s in scenarios), default=0)
        if main and main['original_unit'] == 'instructions' else 0,
        'device': None if not device else {
            'chip': device['id'], 'mode': device['mode'],
            'instructions': max((s['interpreted'] or 0 for s in device['scenarios']), default=0),
            'per_frame': max((s['per_frame'] or 0 for s in device['scenarios']), default=0)},
        'audio_cpu': audio['reported_label'] if audio else None,
        'audio_interpreted_opcodes': max((s['interpreted'] or 0 for s in audio['scenarios']), default=0) if audio else 0,
        'video_standard': _dict(report['runtime'].get('video_model')).get('standard'),
        'interpreter_percent': max(percents, default=None),
        'interpreter_cycles': max(((s['cycles'] or {}).get('interpreted') or 0 for s in scenarios), default=0),
        'reference_vdp_trace_match': report['legacy'].get('reference_vdp_trace_match'),
    }
