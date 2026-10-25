"""Capcom CPS-1 native conversion through the shared batch/export contract.

Every route runs twice in the same build: once with every instruction forced
through the reference interpreters (the fresh reference) and once with the
translated 68000/Z80 code. Their per-frame CPU, RAM, image and PCM traces must
be identical, before and after compression, and quick states must continue
the saved timeline in a fresh process. Interpreted instructions that remain
are counted and reported; RAM code they ran becomes guarded native code in
the next pass. Nothing is written beside the ROMs.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from . import __version__
from .core import ConversionError, executable_name, run_process
from .library import atomic_json, entry_lock
from .paths import ROOT
from .toolchain import describe as toolchain_description

STATE_SETTLE = 600   # frames continued after a quick state is loaded


def _digest(path: Path) -> str:
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def routes(identity: str, *, frames: int, level: str, six_buttons: bool) -> list[tuple[str, int, str]]:
    """(name, frames, script): attract, a credited play route, then long routes."""
    from .random_routes import long_route, long_routes, cps1_script
    from .scan_levels import cps1_budget
    budget = cps1_budget(level)
    play = replace(long_route('cps1', identity, 1000, frames=max(frames, 1800), six_buttons=six_buttons), name='play')
    rows = [('attract', frames, '0 000 000\n')] if budget['attract'] else []
    rows.append(('play', play.frames, cps1_script(play)))
    for route in long_routes('cps1', identity, count=budget['route_count'], frames=budget['route_frames'],
                             six_buttons=six_buttons):
        rows.append((route.name, route.frames, cps1_script(route)))
    return rows


def run(executable: Path, folder: Path, name: str, frames: int, script: Path, *extra: str,
        ends_at: int | None = None) -> dict:
    folder.mkdir(parents=True, exist_ok=True)
    report, trace = folder / (name + '.json'), folder / (name + '.csv')
    completed = run_process([str(executable), '--headless', '--frames', str(frames), '--script', str(script),
                                '--trace', str(trace), '--report', str(report), *extra],
                               capture_output=True, text=True, timeout=max(300, frames // 20))
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).strip().splitlines()[-1:] or ['no output']
        raise ConversionError(f'CPS-1 {name} run failed ({completed.returncode}): {detail[0]}')
    result = json.loads(report.read_text(encoding='utf-8'))
    if result['frames'] != (frames if ends_at is None else ends_at) or result['save_failed']:
        raise ConversionError(f'CPS-1 {name} run ended early or could not save its state.')
    result['trace'] = trace
    return result


def merge(observations: dict, fallback: dict) -> bool:
    """Add newly observed work-RAM/Z80-RAM code; True when anything was new."""
    changed = False
    for key, fields in (('m68k_ram', ('offset', 'words')), ('z80_ram', ('address', 'bytes'))):
        known = {tuple(row[f] for f in fields) for row in observations.setdefault(key, [])}
        for row in fallback.get(key, ()):
            item = tuple(row[f] for f in fields)
            if item not in known:
                known.add(item); observations[key].append({f: row[f] for f in fields}); changed = True
    return changed


def learned(identity: str, memory: Path) -> dict:
    """Earlier qualified observations of this exact set and opt-in gameplay feedback."""
    from .feedback import records
    observations = {'m68k_ram': [], 'z80_ram': []}
    previous = memory / 'observations.json'
    if previous.is_file():
        try:
            merge(observations, json.loads(previous.read_text(encoding='utf-8')))
        except (OSError, ValueError, KeyError, TypeError):
            pass
    rows = {'m68k_ram': [{'offset': r.address, 'words': r.data.hex()} for r in records('cps1', identity, 15)
                         if not r.address & 1 and r.address < 0x10000 and len(r.data) % 2 == 0],
            'z80_ram': [{'address': r.address, 'bytes': r.data.hex()} for r in records('cps1', identity, 16)
                        if 0xd000 <= r.address < 0xd800 and len(r.data) == 4]}
    merge(observations, rows)
    return observations


def check_states(executable: Path, folder: Path, name: str, frames: int, script: Path, expected: Path) -> dict:
    """F8 at a frame, F9 in a fresh process: the continued timeline must match."""
    at = max(60, frames - STATE_SETTLE - 60)
    state = folder / 'quick.rrstate'
    run(executable, folder, 'save', at + 1, script, '--save-state', str(state), '--save-at', str(at))
    run(executable, folder, 'load', STATE_SETTLE, script, '--load-state', str(state), ends_at=at + STATE_SETTLE)
    rows = expected.read_text(encoding='ascii').splitlines()[1:]
    resumed = (folder / 'load.csv').read_text(encoding='ascii').splitlines()[1:]
    if resumed != rows[at:at + STATE_SETTLE]:
        raise ConversionError('CPS-1 F9 continuation differs from its saved timeline; existing export preserved.')
    invalid = folder / 'invalid.rrstate'
    invalid.write_bytes(state.read_bytes()[:-17])
    rejected = run_process([str(executable), '--headless', '--frames', '1', '--load-state', str(invalid)],
                              capture_output=True, timeout=120)
    if rejected.returncode != 4:
        raise ConversionError('CPS-1 accepted a truncated quick state.')
    return {'route': name, 'saved_at': at, 'continued_frames': STATE_SETTLE, 'fresh_process_match': True,
            'truncated_state_rejected': True, 'state_bytes': state.stat().st_size}


def convert(path: Path, *, title=None, output=None, cover=None, use_cover=True, online_cover=True,
            boxart_dir=None, passes=3, frames=3600, scan_level=None, standard_override=None, profile=None,
            emit=print, **unused) -> Path:
    started = time.perf_counter()
    from .scan_levels import LEVELS
    from .cps1 import read_set
    from . import cps1_catalogue
    from .cps1_build import prepare_game, build_game, player_count, YMFM_REVISION
    from .neogeo_build import GEOLITH_REV as GEOLITH_REVISION
    MAME_REVISION = cps1_catalogue.catalogue()['source']['revision']
    level = scan_level or 'standard'
    if level not in LEVELS:
        raise ConversionError(f'Unknown scan level: {level!r}.')
    if standard_override not in (None, 'arcade', 'auto'):
        raise ConversionError('CPS-1 timing follows its board (59.637 Hz); PAL/NTSC overrides do not apply.')
    if profile is not None:
        raise ConversionError('CPS-1 identifies romsets by CRC; TOML cartridge profiles do not apply.')
    game_set = read_set(Path(path))
    if not game_set.supported:
        raise ConversionError(f'CPS-1 set {game_set.set_name} is not supported yet: {game_set.reason}')
    game = cps1_catalogue.by_set()[game_set.set_name]
    title = title or game_set.title
    if any(ord(c) < 32 for c in title) or len(title) > 160:
        raise ConversionError('Invalid CPS-1 game title.')
    if output is None:
        from .paths import games_directory
        output = games_directory(system_id='cps1') / 'datas/reports' / game_set.sha256
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    from .feedback import ingest
    from .library import library_root
    feedback = ingest('cps1', game_set.sha256, output, emit=emit)
    memory = library_root('cps1') / game_set.sha256
    observations = learned(game_set.sha256, memory)
    six = any(name in ('button4', 'button5', 'button6') for port in game['inputs'].values()
              for _, name, _ in port.get('inputs', ()))
    plan = routes(game_set.sha256, frames=max(600, min(int(frames or 3600), 10000)), level=level, six_buttons=six)
    workers = max(1, min(4, os.cpu_count() or 1))
    timings = {}
    work = ROOT / '.build' / 'cps1' / f'{game_set.set_name}-{game_set.sha256[:12]}'
    with entry_lock(work, timeout=1800):
        project, checks = work / 'native', work / 'checks'
        shutil.rmtree(checks, ignore_errors=True)
        scripts = {}
        for name, count, text in plan:
            scripts[name] = checks / 'inputs' / (name + '.inputs')
            scripts[name].parent.mkdir(parents=True, exist_ok=True)
            scripts[name].write_text(text, encoding='ascii', newline='\n')
        emit(f'CPS-1 {game_set.set_name}: scan level {level}, routes ' +
             ', '.join(f'{name} ({count} frames)' for name, count, _ in plan) + '.')
        presentation = {'rom_path': Path(path), 'cover': Path(cover) if cover else None, 'use_cover': use_cover,
                        'online_cover': online_cover, 'boxart_dir': boxart_dir, 'emit': emit}
        reference, results, prepared = {}, {}, None
        attempts = max(1, min(int(passes or 1), 10))
        for attempt in range(attempts):
            phase = time.perf_counter()
            emit(f'CPS-1: translating the 68000 program and Z80 sound code (pass {attempt + 1}).')
            prepared = prepare_game(project, game_set, game, title=title, observations=observations,
                                    presentation=presentation)
            executable = build_game(project)
            timings[f'translate_and_build_{attempt + 1}'] = round(time.perf_counter() - phase, 3)
            phase = time.perf_counter()
            candidate = checks / f'pass-{attempt + 1}' / executable.name
            candidate.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(executable, candidate)
            jobs = []
            if not reference:
                emit('CPS-1: fresh reference runs (every instruction interpreted).')
                jobs += [('reference', name, count) for name, count, _ in plan]
            jobs += [('native', name, count) for name, count, _ in plan]
            with ThreadPoolExecutor(max_workers=workers) as pool:
                done = list(pool.map(lambda job: (job, run(candidate, checks / job[0] / f'pass-{attempt + 1}', job[1], job[2],
                                                          scripts[job[1]], *(['--reference'] if job[0] == 'reference' else []))),
                                     jobs))
            for (kind, name, _), result in done:
                (reference if kind == 'reference' else results)[name] = result
            for name, count, _ in plan:
                if results[name]['trace'].read_bytes() != reference[name]['trace'].read_bytes():
                    raise ConversionError(f'CPS-1 {name}: native and reference CPU/RAM/image/PCM traces differ; '
                                          'existing export preserved.')
                if not results[name]['nonuniform_frames']:
                    raise ConversionError(f'CPS-1 {name}: no picture was produced.')
            timings[f'routes_{attempt + 1}'] = round(time.perf_counter() - phase, 3)
            fallback = sum(results[name]['interpreted_68000'] + results[name]['interpreted_z80'] for name, _, _ in plan)
            if not fallback:
                break
            progress = False
            for name, _, _ in plan:
                progress = merge(observations, results[name]['fallback']) or progress
            if not progress or attempt + 1 == attempts:
                emit(f'CPS-1: {fallback} interpreted instructions remain; they stay counted and reported.')
                break
            emit(f'CPS-1: {fallback} interpreted instructions observed; extending guarded native code.')
        if not any(results[name]['nonzero_samples'] for name, _, _ in plan):
            raise ConversionError('CPS-1 validation produced no sound on any route.')
        phase = time.perf_counter()
        from .packing import compact_executable
        packed = project / 'packed-game.exe' if os.name == 'nt' else project / 'packed-game'
        shutil.copy2(executable, packed)
        compact_executable(packed)
        emit('CPS-1: comparing the compressed executable with the fresh reference.')
        final = {}
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for (name, _, _), result in zip(plan, pool.map(
                    lambda row: run(packed, checks / 'packed', row[0], row[1], scripts[row[0]]), plan)):
                if result['trace'].read_bytes() != reference[name]['trace'].read_bytes():
                    raise ConversionError(f'CPS-1 {name}: compressed executable differs from the reference.')
                final[name] = result
        timings['packed_replays'] = round(time.perf_counter() - phase, 3)
        phase = time.perf_counter()
        emit('CPS-1: checking F8/F9 in a fresh process and rejecting an invalid state.')
        play = next(row for row in plan if row[0] == 'play')
        states = check_states(packed, checks / 'states', 'play', play[1], scripts['play'], final['play']['trace'])
        timings['state_checks'] = round(time.perf_counter() - phase, 3)
        memory.mkdir(parents=True, exist_ok=True)
        atomic_json(memory / 'observations.json', observations)
        atomic_json(memory / 'compilation.json', {
            'schema': 1, 'system': 'cps1', 'title': title, 'set': game_set.set_name, 'source_identity': game_set.sha256,
            'guarded_ram_variants': len(observations['m68k_ram']), 'guarded_z80_ram_variants': len(observations['z80_ram']),
            'fresh_reference_passed': True, 'version': __version__})
    checks_rows = []
    for name, count, text in plan:
        native = final[name]
        main = native['native_68000'] + native['interpreted_68000']
        checks_rows.append({'name': name, 'frames': count, 'native_entries': native['native_68000'],
            'interpreted_opcodes': native['interpreted_68000'], 'audio_native_opcodes': native['native_z80'],
            'audio_interpreted_opcodes': native['interpreted_z80'],
            'interpreter_percent': round(100 * native['interpreted_68000'] / max(1, main), 6),
            'reference_match': True, 'cpu_hash': native['cpu_hash'], 'ram_hash': native['ram_hash'],
            'image_hash': native['image_hash'], 'pcm_hash': native['pcm_hash'],
            'nonzero_samples': native['nonzero_samples'], 'trace_sha256': _digest(native['trace']),
            'script_sha256': hashlib.sha256(text.encode('ascii')).hexdigest()})
    native_coverage = all(not row['interpreted_opcodes'] and not row['audio_interpreted_opcodes'] for row in checks_rows)
    from .systems.cps1 import CPS1
    analysis = prepared['analysis']
    report = {'tool': 'Retro-Recomp', 'version': __version__,
        'status': 'completed' if not CPS1.experimental and native_coverage else 'experimental',
        'created_utc': datetime.now(timezone.utc).isoformat(), 'system': {'id': 'cps1', 'name': 'Capcom CPS-1'},
        'rom': game_set.metadata(),
        'compiler': {'board': 'Retro-Recomp CPS-1 board adapted from MAME (BSD-3-Clause)', 'mame_revision': MAME_REVISION,
                     'cpu_cores_revision': GEOLITH_REVISION, 'ymfm_revision': YMFM_REVISION,
                     'native_cpu': 'guarded 68000 (static sweep of the program ROM) and guarded Z80 at every byte'},
        'native_analysis': {'m68000': {k: analysis['m68000'].get(k) for k in ('decoded', 'translated_rom_positions',
                                                                              'guarded_ram_variants')},
                            'z80': {k: v for k, v in analysis['z80'].items() if isinstance(v, (int, str))}},
        'final_checks': checks_rows,
        'native_validation': {'passed': True, 'packed_reference_match': True, 'reference_before_learning': True,
            'reference_kind': 'same board model with every instruction interpreted (Musashi, Z80 core)',
            'cpu_agreement': True, 'hardware_fidelity_validated': False, 'full_game_validated': False,
            'mame_comparison': 'board model compared with MAME on development sets only; not per conversion'},
        'native_coverage': native_coverage,
        'video_model': {'standard': 'arcade', 'visible_pixels': [384, 224], 'hz': 8000000 / (512 * 262),
                        'rotation': game_set.rotation, 'display_aspect': '3:4' if game_set.rotation else '4:3'},
        'audio_cpu': 'Z80', 'audio_model': {'chips': ['YM2151 (ymfm)', 'OKI MSM6295'], 'rate': 3579545 // 64},
        'counter_unit': 'retired instructions', 'runtime_learning': True, 'runtime_feedback': feedback,
        'physical_latency_measured': False, 'latency_ms': None,
        'game_states': {'supported': True, 'save_key': 'F8', 'load_key': 'F9',
                        'compatibility': 'exact romset, board model and runtime ABI', 'validation': states},
        'ordinary_saves': {'supported': False, 'reason': 'standard CPS-1 boards keep no non-volatile memory'},
        'artwork': prepared['artwork'], 'windows_metadata': prepared['windows_metadata'],
        'executable': executable_name(title), 'build_executable': str(executable), 'toolchain': toolchain_description(), 'build_directory': str(project),
        'packed_candidate_sha256': _digest(packed), 'scan_level': level, 'validation_workers': workers,
        'conversion_phases_seconds': timings, 'conversion_wall_seconds': round(time.perf_counter() - started, 3),
        'qualification_scope': {
            'controls': f'players 1 to {player_count(game)}: joystick, up to six buttons, Start, coin; '
                        'validation routes drive players 1 and 2',
            'dip_switches': 'catalogue defaults during validation; adjustable in play (F2)',
            'universal_zero_fallback_claim': False}}
    atomic_json(output / 'conversion-report.json', report)
    emit(f'CPS-1: {title} ready ({"native code only" if native_coverage else "interpreter fallback reported"}).')
    # Publishing compacts this same build again (UPX is deterministic).
    return executable
