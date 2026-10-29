"""Conversion report schema 2: the one builder every writer goes through, and the one reader of every shape.

Seven converters write ``conversion-report.json`` (Master System and Game Gear,
Game Boy, NES, Mega Drive and Super Nintendo, Neo Geo, CPS-1, X68000). They
used to write seven different shapes; this module is the only place that reads
them all, and the profile of each machine (``report_shape``, ``cpus``) says which
writer and which CPUs a report has. ``read_report`` turns any of them into the schema-2 document
described below; ``fallback_summary`` is the one-line interpreter summary the
batch result and the window both compute from a report.

The writers write schema 2 **beside** their own keys for one version
(``with_schema_v2``, ``write_report``): every old key is kept with the value it
had, so the readers written for the old shapes and the website read a new
report as before, and the schema-2 sections are added to the same document.
``batch.py`` adds its fields after the conversion and writes again through the
same builder, which derives the sections anew. A later version drops the old
keys; ``read_report`` already returns only the schema-2 keys of a document.

Rules the reader keeps (docs/STANDARDS.md, rules 6 to 8):

* A field the report does not carry is ``None`` (or an empty list), never
  invented, never zero. Zero means a writer measured zero.
* A count is never converted from one unit to another. Interpreted counts are
  held in one unit, **instructions**, per CPU and per scenario; when a writer
  only counted cycles (Master System, Game Gear, NES) the cycles are kept
  beside them under ``cycles`` and the instruction count stays ``None`` unless
  the writer measured it too (Game Boy does).
* The five measures (native code, CPU fidelity, hardware fidelity, gameplay,
  latency) are five sibling objects under ``validation``. None is derived from
  another, each carries a ``claim`` string, and no claim is stronger than the
  flag the writer stored.
* Main CPU, sound CPU and cartridge devices are separate sections; their
  counters are never added together.
* ``timings`` was added to schema 2 in 1.6.2 without a new schema number: it is optional on disk, a report
  from before it reads ``None``, and a value that is not a ``{phase: seconds}`` object reads ``None`` too.
  It is the wall time of each phase of the conversion at 0.1 s (retrorecomp/timings.py names the phases;
  ``total`` is the whole conversion of the game and is not one of the phases); the batch writes it. It is
  a measure of this run on this machine, not of the game, and no claim of the report depends on it.
* A shape the reader does not know raises ``ReportShapeError``. A schema number
  it does not know raises it too, so a newer document is never misread.

Schema 2 (every key is always present in what ``read_report`` returns; see
``REQUIRED_KEYS``; on disk the keys listed in ``OPTIONAL_ON_DISK`` may be
missing, because the old readers take a null for a value)::

    schema        {'name': 'retro-recomp-report', 'version': 2}
    read_from     {'schema_version': 1 | 2, 'writer': 'core' | 'gameboy' | ...}
    tool, version, created_utc, target     as written, else None
    system        {'id', 'name', 'status'}  status as the writer stored it
    rom           the writer's ROM record; source_identity (X68000) beside it
    scan          {'level', 'enabled', 'scenario_frames', 'routes': [...]}
    cpus          [{'id': 'main' | 'audio', 'arch', 'role', 'unit': 'instructions',
                    'original_unit': 'instructions' | 'cycles', 'mode',
                    'reported_label', 'fallback_present', 'ram_single_step_present',
                    'scenarios': [{'name', 'frames', 'native', 'interpreted',
                                   'interpreted_percent', 'cycles', ...,
                                   'ram_single_step': {'stub_instructions', 'stub_cycles',
                                                       'single_step_instructions', 'single_step_cycles'}
                                                      (Game Boy: WRAM/HRAM code run one instruction at a
                                                       time; neither native nor interpreted)}]}]
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
    timings       {phase: seconds, ..., 'total': seconds} | None
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
                 'knowledge', 'build', 'timings', 'upgrade', 'export_receipt', 'legacy')
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


def _shape_of(profile):
    """The shape of a profile's report, from its ``report_shape`` and its CPUs; None for a machine with no report."""
    spec = profile.report_shape
    main = next((cpu for cpu in profile.cpus if cpu.role == 'main'), None)
    if spec is None or main is None:
        return None
    sound = next((cpu for cpu in profile.cpus if cpu.role == 'sound'), None)
    return _Shape(spec.writer, spec.marker, main.arch, sound.arch if sound else None, main.unit)


def _shapes():
    """``{console id: _Shape}`` of the registered machines, read from their profiles (retrorecomp/systems)."""
    from .systems import ALL_PROFILES
    shapes = {}
    for profile in ALL_PROFILES:
        shape = _shape_of(profile)
        if shape is not None:
            shapes[profile.id] = shape
    return shapes


def __getattr__(name):
    # ``_SHAPES`` is the profiles' view, computed on access so that a machine registered later is known at once.
    if name == '_SHAPES':
        return _shapes()
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')


# A report no writer produced (a hand-made or very old one) that a caller still wants to summarise: its rows are
# read by the keys they carry, whatever the console. Only the lenient reading uses it.
_GENERIC = _Shape('unknown', '', 'unknown', 'unknown', 'instructions')
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
        if 'ram_stub_instructions' in row or 'ram_single_step_instructions' in row:
            # WRAM/HRAM code run one instruction at a time (the runtime's RAM stub; the single-instruction
            # executor): neither native code nor an interpreter session, so counted in its own field.
            extra['ram_single_step'] = {
                'stub_instructions': _count(row.get('ram_stub_instructions')),
                'stub_cycles': _count(row.get('ram_stub_cycles')),
                'single_step_instructions': _count(row.get('ram_single_step_instructions')),
                'single_step_cycles': _count(row.get('ram_single_step_cycles'))}
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
        if row.get('interpreter_cycles') is not None:
            # No writer of an instruction shape stores it; a row from outside the writers might.
            cycles = {'native': None, 'interpreted': _count(row.get('interpreter_cycles')), 'total': None}
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


def _ram_single_step_state(scenarios):
    """True when any scenario ran WRAM/HRAM code one instruction at a time, False when every one measured none,
    else None (a writer that does not count it)."""
    counts = []
    for scenario in scenarios:
        step = scenario.get('ram_single_step')
        if isinstance(step, dict):
            counts.append([step.get('stub_instructions'), step.get('single_step_instructions')])
    if any(v is not None and v > 0 for pair in counts for v in pair):
        return True
    if counts and len(counts) == len(scenarios) and all(all(v is not None for v in pair) for pair in counts):
        return False
    return None


def _cpus(shape, data, rows):
    main = {'id': 'main', 'arch': shape.main_arch, 'role': 'main', 'unit': 'instructions',
            'original_unit': shape.main_unit, 'mode': None, 'reported_label': None,
            'scenarios': [_main_scenario(shape.writer, row) for row in rows]}
    main['fallback_present'] = _fallback_state(main['scenarios'])
    main['ram_single_step_present'] = _ram_single_step_state(main['scenarios'])
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
    ram_states = [cpu.get('ram_single_step_present') for cpu in cpus]
    ram = True if any(state is True for state in ram_states) else None if any(
        state is None for state in ram_states) else False
    # The interpreter figure stays what it is; code run one instruction at a time is a third thing, and while it
    # is present the zero-fallback and native-only claims are false.
    zero = None if present is None else not present and ram is not True
    return {
        'native_code': {
            'fallback_present': present,
            'ram_single_step_present': ram,
            'zero_fallback_on_tested_scenarios': zero,
            'scenarios_checked': len(rows),
            'coverage': _copy(coverage) if isinstance(coverage, dict) else None,
            'coverage_note': coverage if isinstance(coverage, str) else None,
            'claim': ('native ROM code on the tested scenarios; some WRAM/HRAM instructions run one at a time by '
                      'counted executors (not native code)' if ram else
                      'native code on the tested scenarios only')},
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


def _timings(value):
    """The ``{phase: seconds}`` object of a report, else None. Entries that are not a number of seconds are
    left out; an object with none left, or with no ``total``, is not a timing record."""
    if not isinstance(value, dict):
        return None
    figures = {str(name): seconds for name, seconds in value.items() if _count(seconds) is not None and seconds >= 0}
    return figures if _count(figures.get('total')) is not None else None


# ---------------------------------------------------------------- entry points

# Keys only schema 2 introduces. Writers still write the old keys beside them (dual-write, one version): a
# document carrying both is read through the schema-2 sections, and the old keys stay for the readers that
# were written for the old shapes and for the website.
V2_ONLY_KEYS = ('schema', 'read_from', 'scan', 'cpus', 'devices', 'validation', 'honesty', 'packed', 'states',
                'saves', 'runtime', 'build', 'legacy')
# Schema-2 keys whose names the old shapes already use. A writer leaves out what it does not know, and old readers
# take a missing key for "absent" but a null for a value (`report.get('upgrade', {})`, `report.get('target', t)`),
# so a document on disk never carries these as null; read_report still returns them, as None.
OPTIONAL_ON_DISK = ('version', 'created_utc', 'target', 'timings', 'upgrade', 'export_receipt')
# `knowledge` is also an old key (Neo Geo writes its memory record there). On disk the two meet in one object:
# the writer's own keys stay, the schema-2 keys are added beside them.
KNOWLEDGE_KEYS = ('record', 'learning', 'library_identity', 'shared_paths', 'bundled_paths')


def _validate_v2(data):
    version = _dict(data.get('schema')).get('version')
    if version != SCHEMA_VERSION:
        raise ReportShapeError(f'Report schema {version!r} is not known to this version '
                               f'(it reads 1, the seven older shapes, and {SCHEMA_VERSION}).')
    missing = [key for key in REQUIRED_KEYS if key not in data and key not in OPTIONAL_ON_DISK]
    missing += ['validation.' + measure for measure in MEASURES if measure not in _dict(data.get('validation'))]
    if missing:
        raise ReportShapeError('Schema 2 report is incomplete: missing ' + ', '.join(missing) + '.')
    # Only the schema-2 keys: the old keys of a dual-written document are not part of the document read.
    report = {key: _copy(data.get(key)) for key in REQUIRED_KEYS}
    report['timings'] = _timings(data.get('timings'))
    if isinstance(report['knowledge'], dict):
        report['knowledge'] = {key: report['knowledge'].get(key) for key in KNOWLEDGE_KEYS}
    return report


def _load(data_or_path):
    if isinstance(data_or_path, (str, Path)):
        try:
            return json.loads(Path(data_or_path).read_text(encoding='utf-8'))
        except json.JSONDecodeError as error:
            raise ReportShapeError(f'{data_or_path}: not a JSON document ({error}).') from error
    return data_or_path


def _from_legacy(data, *, lenient=False, schema_version=1):
    """The schema-2 document of a report in the writers' own keys (no schema-2 key in it)."""
    system = _dict(data.get('system'))
    if lenient:
        shape = _shapes().get(system.get('id'), _GENERIC)
    else:
        if data.get('tool') != 'Retro-Recomp':
            raise ReportShapeError('Not a Retro-Recomp conversion report.')
        shape = _shapes().get(system.get('id'))
        if shape is None:
            raise ReportShapeError(f'Unknown console in a report: {system.get("id")!r}.')
    rows = data.get('final_checks')
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ReportShapeError(f'The {system.get("id")} report has no usable final_checks list.')
    if not lenient and shape.marker not in data:
        raise ReportShapeError(f'The {system["id"]} report does not have the shape of the {shape.writer} writer '
                               f'(no {shape.marker!r}).')
    cpus, device = _cpus(shape, data, rows), _device(data, rows)
    devices = [device] if device else []
    validation = _validation(shape, data, rows, cpus, devices)
    return {
        'schema': {'name': SCHEMA_NAME, 'version': SCHEMA_VERSION},
        'read_from': {'schema_version': schema_version, 'writer': shape.writer},
        'tool': data.get('tool'), 'version': data.get('version'), 'created_utc': data.get('created_utc'),
        'target': data.get('target'),
        'system': {'id': system.get('id'), 'name': system.get('name'), 'status': data.get('status')},
        'rom': {**_copy(_dict(data.get('rom'))), **({'source_identity': data['source_identity']}
                                                    if 'source_identity' in data else {})},
        'scan': _scan(shape, data, rows), 'cpus': cpus, 'devices': devices, 'validation': validation,
        'honesty': _honesty(data, validation), 'packed': _packed(shape, data, rows), 'states': _states(data),
        'saves': _saves(data), 'runtime': _runtime(data), 'knowledge': _knowledge(data), 'build': _build(data),
        'timings': _timings(data.get('timings')),
        'upgrade': _copy(data.get('upgrade')), 'export_receipt': _copy(data.get('export_receipt')),
        # Written by the old shapes, not yet given a schema-2 home. reference_vdp_trace_match is kept here
        # because the X68000 writer hard-coded it to True (it writes null now): it is not a measurement and
        # is never mapped to a picture claim above.
        'legacy': {'reference_vdp_trace_match': data.get('reference_vdp_trace_match'),
                   'native_coverage': _copy(data.get('native_coverage'))},
    }


def read_report(data_or_path, *, lenient=False) -> dict:
    """Any conversion report of any writer, as a schema-2 document.

    Takes the parsed dict or the path of a ``conversion-report.json``. Never
    modifies its input. Raises ``ReportShapeError`` for a document no writer
    produces, so a caller can tell an unreadable report from a game without
    fallback. A schema-2 document (also one that still carries the old keys, as
    the writers write them for one version) is validated and returned as a copy
    of its schema-2 keys.

    ``lenient`` is for the callers that only summarise the fallback of a report
    and always did so with ``.get`` on whatever the file held (an export of a
    release before the shapes settled, a report written by hand): the console and
    the shape marker are not required, only a ``final_checks`` list. Its rows are
    read by the keys they carry. The document is as complete as any other, but
    nothing in it is a claim: a console unknown to the reader has no CPU names.
    """
    data = _load(data_or_path)
    if not isinstance(data, dict):
        raise ReportShapeError('A conversion report is a JSON object.')
    if 'schema' in data:
        if _dict(data.get('schema')).get('name') != SCHEMA_NAME:
            raise ReportShapeError('Unknown report schema: ' + repr(data['schema']) + '.')
        return _validate_v2(data)
    return _from_legacy(data, lenient=lenient)


# ---------------------------------------------------------------- writing

def legacy_view(document) -> dict:
    """The writer's own keys of a report: what ``with_schema_v2`` was given.

    Drops the schema-2 sections and the schema-2 parts of the three keys the shapes share
    (``system.status``, ``rom.source_identity``, the schema-2 keys of ``knowledge``). A report that
    is not dual-written comes back as a copy.
    """
    legacy = {key: _copy(value) for key, value in document.items() if key not in V2_ONLY_KEYS}
    if isinstance(legacy.get('system'), dict):
        legacy['system'].pop('status', None)
    if isinstance(legacy.get('rom'), dict) and 'source_identity' in legacy:
        legacy['rom'].pop('source_identity', None)
    knowledge = legacy.get('knowledge')
    if isinstance(knowledge, dict) and any(key in knowledge for key in KNOWLEDGE_KEYS):
        knowledge = {key: value for key, value in knowledge.items() if key not in KNOWLEDGE_KEYS}
        if knowledge:
            legacy['knowledge'] = knowledge
        else:
            del legacy['knowledge']
    return legacy


def with_schema_v2(report) -> dict:
    """The report with every schema-2 section added to the writer's own keys (dual-write).

    The one builder every writer goes through. Each old key stays where it was with the value it had, so
    the readers written for the old shapes and the website read the document as before; the schema-2
    sections are derived from those keys by the same code that reads an old report, so a report read from
    the old shape and the same report written now give the same document. ``schema`` comes first. It can be
    applied again to its own result (``batch.py`` adds its fields after the conversion and writes again):
    the sections are derived anew from the old keys. Raises ``ReportShapeError`` for a report whose
    ``system.id`` is not a console of the reader, or that lacks the marker of its writer's shape.
    """
    legacy = legacy_view(report)
    parts = _from_legacy(legacy)
    document = {'schema': parts['schema'],
                'read_from': {'schema_version': SCHEMA_VERSION, 'writer': parts['read_from']['writer'],
                              'legacy_keys': True}}
    for key, value in legacy.items():
        if key == 'system':
            value = parts['system']
        elif key == 'rom':
            value = parts['rom']
        elif key == 'knowledge':
            if not isinstance(value, dict):
                raise ReportShapeError('The report\'s "knowledge" is not an object.')
            value = {**value, **parts['knowledge']}
        document[key] = value
    for key in REQUIRED_KEYS:
        if key not in document and key not in OPTIONAL_ON_DISK:
            document[key] = parts[key]
    return document


def _profile_of(report):
    """The registered profile of the machine a report names, else None."""
    from .systems import ALL_PROFILES
    system_id = _dict(report.get('system')).get('id')
    return next((profile for profile in ALL_PROFILES if profile.id == system_id), None)


def write_report(path, report) -> dict:
    """Write a conversion report in schema 2 beside the writer's own keys; returns the document written.

    ``created_utc`` and ``target`` are filled in when the writer did not carry them (Game Boy had no
    time; only some writers had the target, and a report with none was taken for the current
    target's). ``status`` is filled in from the machine's profile when the writer left it unset (the
    Master System, Game Gear, Game Boy and NES writers store none): the one source of "supported" or
    "experimental" is the profile (docs/STANDARDS.md). A writer that states its own status, a stage
    that depends on the cartridge (``completed``, ``experimental``), keeps it. The file is replaced
    atomically. Raises ``ReportShapeError`` before anything is written if the report has no known shape.
    """
    from datetime import datetime, timezone
    from .library import atomic_json
    from .platforms import target_id
    additions = {}
    if report.get('created_utc') is None:
        additions['created_utc'] = datetime.now(timezone.utc).isoformat()
    if report.get('target') is None:
        additions['target'] = target_id()
    if report.get('status') is None:
        profile = _profile_of(report)
        if profile is not None:
            additions['status'] = profile.status
    data = {key: value for key, value in report.items() if key not in additions}
    if additions:
        # Keep the identity keys together at the top, as the writers that carry them do.
        anchor = 'version' if 'version' in data else 'tool'
        ordered = {}
        for key, value in data.items():
            ordered[key] = value
            if key == anchor:
                ordered.update(additions)
        data = ordered
    document = with_schema_v2(data)
    atomic_json(Path(path), document)
    return document


# ---------------------------------------------------------------- the fallback summary

def _is_schema2(report):
    return (isinstance(report, dict) and report.get('schema') == {'name': SCHEMA_NAME, 'version': SCHEMA_VERSION}
            and all(key in report for key in REQUIRED_KEYS if key not in OPTIONAL_ON_DISK))


def _cpu(report, role):
    return next((cpu for cpu in report['cpus'] if cpu.get('role') == role), None)


def _ram_total(scenario, *keys):
    step = scenario.get('ram_single_step')
    return sum((step.get(key) or 0) for key in keys) if isinstance(step, dict) else 0


def fallback_summary(report, *, lenient=False) -> dict:
    """The interpreter fallback of a report, in the figures the batch result and the window show.

    Accepts a schema-2 document, with or without the old keys beside it (or anything ``read_report``
    accepts, ``lenient`` as there). Every figure is a maximum over the scenarios, never a sum, and each CPU
    and device is kept apart. These are the figures ``batch.py`` and ``gui.py`` computed from the old shapes
    before they read reports through this module (``conversion_stage``, ``main_interpreted_opcodes``,
    ``device``, ``audio_cpu``, ``audio_interpreted_opcodes``, ``interpreter_percent``,
    ``interpreter_cycles``, ``reference_vdp_trace_match``, ``video_standard``), so that a caller switched
    without changing what is displayed, with two differences made on purpose:

    * ``main_interpreted_opcodes`` is the instruction count of the main CPU whenever the writer measured one
      (Game Boy: 900 instructions read 0 before). A writer that counted cycles only (Master System, Game
      Gear, NES) still reads 0 there: a count the writer does not carry reads 0 in the summary and None in
      the report, and cycles are never turned into instructions.
    * ``reference_vdp_trace_match`` is what the report stores. The X68000 writer stores null now (it stored
      a constant True, which compared nothing).

    ``video_standard`` is None when the report has no video model; the callers supply their own default.
    """
    if not _is_schema2(report):
        report = read_report(report, lenient=lenient)
    main, audio = _cpu(report, 'main'), _cpu(report, 'audio')
    scenarios = main['scenarios'] if main else []
    percents = [s['interpreted_percent'] for s in scenarios if s['interpreted_percent'] is not None]
    device = report['devices'][0] if report['devices'] else None
    summary = {
        'conversion_stage': report['system'].get('status'),
        'main_interpreted_opcodes': max((s['interpreted'] or 0 for s in scenarios), default=0),
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
    if any('ram_single_step' in scenario for scenario in scenarios):
        # Game Boy: WRAM/HRAM instructions run one at a time (the runtime's stub and the single-instruction executor),
        # counted apart from the interpreter, a maximum over the scenarios like the other figures. The keys exist
        # only for a writer that counts them.
        summary['ram_one_by_one_instructions'] = max(
            _ram_total(s, 'stub_instructions', 'single_step_instructions') for s in scenarios)
        summary['ram_one_by_one_cycles'] = max(_ram_total(s, 'stub_cycles', 'single_step_cycles') for s in scenarios)
    return summary
