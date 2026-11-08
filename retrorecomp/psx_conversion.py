"""PlayStation conversion (experimental since 1.7.1; docs/PLAYSTATION.md). Retro-Recomp's own code, MIT.

The game executable is the Beetle PSX machine with the player's BIOS embedded (OpenBIOS when he gave none) and his disc
appended. The conversion first builds the observing machine (the interpreter alone, recording the R3000A code it runs) and plays
its routes on it: those runs are the reference. From the code they ran it writes the game's native steps (retrorecomp/psx_native.py:
the interpreter's handler bodies with each instruction word constant, its timing kept, the fetched word as guard), builds the game
with them, and plays every route again on the executable that is published (the disc inside it): each frame's picture, sound and
RAM must be the reference's. The instructions the steps do not hold run on the interpreter and are counted. It then checks F8/F9
in a fresh process and the refusal of a damaged state, and writes the report. A game that carries its disc after the program is
published as built: UPX would move the data the program reads.

An installation without the machine's files (`PLAYSTATION.available()`) refuses a conversion with `NOT_YET`. Nothing is written
beside the player's disc.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import time

from . import __version__
from .core import ConversionError
from .platforms import target_id
from .report_schema import write_report

NOT_YET = 'The PlayStation converter files are missing from this installation.'
STATE_SETTLE = 600              # frames continued after a quick state is loaded
LONG_ROUTES = {'quick': 0, 'standard': 0, 'extended': 1, 'thorough': 2}
LONG_FRAMES = 18000
BOOT_FRAMES = 1500              # the BIOS boot (logo and licence screen) before a disc's own code shows anything
LIVENESS_FIELDS = {'frames': 'frames', 'distinct_pictures': 'distinct_pictures', 'picture_changes': 'picture_changes',
                   'last_picture_change_frame': 'last_picture_change_frame', 'audible_frames': 'audible_frames',
                   'last_audible_frame': 'last_audible_frame'}
# The session's pad bits (native/psx_machine/psx_session.h): B = Cross, A = Circle.
CROSS, START, UP, DOWN, LEFT, RIGHT, CIRCLE = 0x001, 0x008, 0x010, 0x020, 0x040, 0x080, 0x100


def _script(rows) -> str:
    """'frame p1 p2' lines (hex pad words), each held from its frame on (native/psx_machine/psx_main.c)."""
    return ''.join(f'{frame} {p1:04x} {p2:04x}\n' for frame, p1, p2 in rows) or '0 0000 0000\n'


def play_rows(frames: int, seed: int) -> list:
    """Start and Cross pressed through the title screens once the BIOS has booted, then a deterministic walk: a held
    direction changing every second or so, with Cross and Circle tapped. Start is never pressed in the walk (it pauses)."""
    rows = []
    for at in range(BOOT_FRAMES, min(frames, BOOT_FRAMES + 1200), 240):
        rows += [(at, START, 0), (at + 8, 0, 0), (at + 120, CROSS, 0), (at + 128, 0, 0)]
    state = seed & 0xFFFFFFFF or 1
    directions = (RIGHT, RIGHT | UP, RIGHT | DOWN, LEFT, UP, DOWN, RIGHT)
    frame = BOOT_FRAMES + 1200
    while frame < frames:
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        held = directions[state % len(directions)]
        span = 30 + (state >> 8) % 60
        for tap in range(0, span - 4, 12):
            button = CROSS if (state >> (tap % 7)) & 1 else CIRCLE
            rows += [(frame + tap, held | button, 0), (frame + tap + 4, held, 0)]
        frame += span
    rows = [row for row in rows if row[0] < frames]
    assert all(a[0] <= b[0] for a, b in zip(rows, rows[1:])), 'route frames must not go back'
    return rows


def routes(identity: str, *, frames: int, level: str) -> list[tuple[str, int, str]]:
    """(name, frames, script): attract (no input), play, then long routes at the extended and thorough levels."""
    seed = int(identity[:8], 16)
    rows = [] if level == 'quick' else [('attract', frames, _script([]))]
    play = max(frames, BOOT_FRAMES + 2400)
    rows.append(('play', play, _script(play_rows(play, seed))))
    for index in range(LONG_ROUTES[level]):
        rows.append((f'long-{index + 1}', LONG_FRAMES, _script(play_rows(LONG_FRAMES, seed + 7919 * (index + 1)))))
    return rows


# ------------------------------------------------------------------ runs and traces

def trace_rows(trace: Path):
    from .delivery_evidence import FrameRow
    for line in Path(trace).read_text(encoding='ascii').splitlines():
        fields = line.split(',')
        if len(fields) != 7 or not fields[0].isdigit():
            continue
        yield FrameRow(int(fields[0]), fields[2], sound=fields[3], audible=fields[5] == '1')


def trace_difference(actual: Path, expected: Path) -> int | None:
    """The first frame where two traces differ (None: the same picture, sound and RAM on every frame)."""
    from .conversion_gates import first_difference
    one = Path(actual).read_text(encoding='ascii').splitlines()[1:]
    other = Path(expected).read_text(encoding='ascii').splitlines()[1:]
    return first_difference(one, other)


def route_liveness(trace: Path) -> dict:
    from .delivery_evidence import liveness_summary, report_fields
    return report_fields(liveness_summary(trace_rows(trace)), LIVENESS_FIELDS)


def run(executable: Path, folder: Path, name: str, frames: int, script: Path, *extra: str, ends_at: int | None = None) -> dict:
    from .conversion_common import check_exit, spawn
    folder.mkdir(parents=True, exist_ok=True)
    report, trace = folder / (name + '.json'), folder / (name + '.csv')
    completed = spawn([str(executable), '--headless', '--frames', str(frames), '--script', str(script),
                       '--trace', str(trace), '--report', str(report), *extra],
                      cwd=folder, timeout=max(900, frames // 3), capture_output=True, text=True)

    def failure(result):
        detail = (result.stderr or result.stdout).strip().splitlines()[-1:] or ['no output']
        return ConversionError(f'PlayStation {name} run failed ({result.returncode}): {detail[0]}')
    check_exit(completed, failure)
    result = json.loads(report.read_text(encoding='utf-8'))
    if result['frames'] != (frames if ends_at is None else ends_at) or result['save_failed']:
        raise ConversionError(f'PlayStation {name} run ended early or could not save its state.')
    result['trace'] = trace
    return result


def check_states(executable: Path, folder: Path, name: str, frames: int, script: Path, expected: Path) -> dict:
    """F8 at a frame, F9 in a fresh process: the continued timeline must match; a damaged state is refused (exit 4)."""
    from .conversion_common import spawn
    from .conversion_gates import continuation_difference, require
    at = max(60, frames - STATE_SETTLE - 60)
    state = folder / 'quick.rrstate'
    run(executable, folder, 'save', at + 1, script, '--save-state', str(state), '--save-at', str(at))
    run(executable, folder, 'load', STATE_SETTLE, script, '--load-state', str(state), ends_at=at + STATE_SETTLE)
    rows = Path(expected).read_text(encoding='ascii').splitlines()[1:]
    resumed = (folder / 'load.csv').read_text(encoding='ascii').splitlines()[1:]
    require(continuation_difference(rows, resumed, at, STATE_SETTLE) is None,
            lambda: ConversionError('PlayStation F9 continuation differs from its saved timeline; existing export preserved.'))
    invalid = folder / 'invalid.rrstate'
    invalid.write_bytes(state.read_bytes()[:-17])
    rejected = spawn([str(executable), '--headless', '--frames', '1', '--load-state', str(invalid)],
                     cwd=folder, timeout=300, capture_output=True)
    require(rejected.returncode == 4, lambda: ConversionError('PlayStation accepted a truncated quick state.'))
    return {'route': name, 'saved_at': at, 'continued_frames': STATE_SETTLE, 'fresh_process_match': True,
            'truncated_state_rejected': True, 'state_bytes': state.stat().st_size}


def check_inputs(executable: Path, folder: Path) -> dict:
    """Every control of the game's pad, pressed alone on each player's pad, must reach exactly its own button of the console
    (the adapter's table, the session's libretro inputs and the core's pad mapping together; psx_main.c --input-check)."""
    from .conversion_common import spawn
    folder.mkdir(parents=True, exist_ok=True)
    completed = spawn([str(executable), '--headless', '--input-check'], cwd=folder, timeout=300, capture_output=True, text=True)
    rows = [json.loads(line) for line in completed.stdout.splitlines() if line.startswith('{')]
    wrong = [f"player {r['player']} {r['action']}" for r in rows if not r['ok']]
    if completed.returncode not in (0, 5) or not rows:
        raise ConversionError(f'PlayStation input check could not run ({completed.returncode}).')
    if wrong or completed.returncode:
        raise ConversionError('PlayStation controls that do not reach their own button of the console: ' + ', '.join(wrong)
                              + '; existing export preserved.')
    return {'controls_checked': len(rows), 'every_control_reaches_its_button': True}


def identification_report(item, level: str = 'standard') -> dict:
    """The writer's keys for a disc that was identified and not converted: no measure is reported."""
    return {'tool': 'Retro-Recomp', 'version': __version__, 'created_utc': datetime.now(timezone.utc).isoformat(),
            'system': {'id': 'psx', 'name': 'Sony PlayStation', 'status': 'experimental'}, 'target': target_id(),
            'rom': {'name': item.path.name, 'serial': item.serial, 'region': item.region}, 'scan_level': level,
            'converted': False, 'disc': [d.metadata() for d in item.discs],
            'native_validation': {'passed': False, 'scope': 'not converted: nothing was compared',
                                  'cpu_fidelity_validated': False, 'independent_cpu_oracle': False},
            'native_coverage': 'not converted', 'final_checks': [],
            'game_states': {'supported': False, 'fresh_process_verified': False},
            'hardware_accuracy_validated': False, 'full_game_validated': False, 'latency_ms': None}


def _require_portable_toolchain() -> None:
    """Beetle's C uses declarations after labels, which Visual C refuses: the machine builds with clang or GCC only."""
    import os
    if os.name != 'nt':
        return
    from .toolchain import active
    if active() == 'msvc':
        raise ConversionError('The PlayStation needs the portable build tools of Retro-Recomp (llvm-mingw); '
                              'Visual Studio cannot build its machine.')


# ------------------------------------------------------------------ the conversion

def convert(path: Path, *, title=None, output=None, cover=None, use_cover=True, online_cover=True, boxart_dir=None,
            frames=3600, scan_level=None, standard_override=None, profile=None, psx_bios=None, emit=print, **unused) -> Path:
    from .systems.psx import PLAYSTATION
    from . import psx as psx_input
    from . import psx_beetle, psx_build, psx_native, psx_pack
    item = psx_input.read_input(path)
    if not PLAYSTATION.available():
        raise ConversionError(NOT_YET)
    _require_portable_toolchain()
    started = time.perf_counter()
    from . import timings as stages
    from .conversion_common import resolve_scan_level
    from .conversion_gates import require
    from .core import executable_name
    from .delivery_evidence import require_moving_picture
    from .library import entry_lock, file_sha256
    from .packing import refuse_compression
    from .paths import ROOT
    from .toolchain import describe as toolchain_description
    level = resolve_scan_level(scan_level)
    if profile is not None:
        raise ConversionError('PlayStation discs are read from their content; TOML cartridge profiles do not apply.')
    video_mode = psx_input.video_mode(item.path)
    if standard_override not in (None, 'auto', video_mode):
        raise ConversionError(f'This disc is {video_mode.upper()}; its standard cannot be changed.')
    title = title or item.title
    if any(ord(c) < 32 for c in title) or len(title) > 160:
        raise ConversionError('Invalid PlayStation game title.')
    emit(f'PlayStation: {item.serial or item.path.name} ({(item.region or "unknown region").upper()}, '
         f'{len(item.discs)} disc(s), {item.discs[0].container}); reading the disc to identify it.')
    sha = item.sha256
    if output is None:
        from .paths import games_directory
        output = games_directory(system_id='psx') / 'datas/reports' / sha
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    from .feedback import ingest
    feedback = ingest('psx', sha, output, emit=emit)
    bios = psx_input.bios_for(item, psx_bios)
    if psx_bios and bios is None:
        raise ConversionError(f'No known {(item.region or "").upper()} PlayStation BIOS in {psx_bios}: the disc needs a BIOS '
                              'of its own region (or no BIOS option, for the free OpenBIOS).')
    emit('PlayStation: BIOS ' + (f'{bios.model} v{bios.version} (yours, embedded in the game).' if bios
                                  else 'OpenBIOS (free BIOS, built into the machine): no BIOS option was given.'))
    plan_frames = max(BOOT_FRAMES + 600, min(int(frames or 3600), 20000))
    plan = routes(sha, frames=plan_frames, level=level)
    timings = {}
    work = ROOT / '.build' / 'psx' / sha[:12]
    with entry_lock(work, timeout=3600):
        project, checks = work / 'g', work / 'checks'
        shutil.rmtree(checks, ignore_errors=True)
        scripts = {}
        for name, count, text in plan:
            scripts[name] = checks / 'inputs' / (name + '.inputs')
            scripts[name].parent.mkdir(parents=True, exist_ok=True)
            scripts[name].write_text(text, encoding='ascii', newline='\n')
        emit(f'PlayStation: scan level {level}, routes ' + ', '.join(f'{n} ({c} frames)' for n, c, _ in plan) + '.')
        presentation = {'rom_path': Path(path), 'cover': Path(cover) if cover else None, 'use_cover': use_cover,
                        'online_cover': online_cover, 'boxart_dir': boxart_dir, 'emit': emit}
        phase = time.perf_counter()
        with stages.phase('code_generation'):
            tree = psx_beetle.adapt(psx_beetle.source(emit), work / 'machine')
            prepared = psx_build.prepare_game(project, tree, title=title, game_sha256=sha, video_mode=video_mode, bios=bios,
                                              presentation=presentation)
        emit('PlayStation: building the observing machine (the interpreter alone, recording the code it runs).')
        with stages.phase('compile'):
            observer = psx_build.build_game(project, emit, target='game_observe')
        pack = psx_pack.write_in_place(item.path, checks / 'disc.rrpack')
        timings['build'] = round(time.perf_counter() - phase, 3)
        phase = time.perf_counter()
        reference, observations = {}, []
        with stages.phase('reference_and_native_runs'):
            for name, count, _ in plan:
                emit(f'PlayStation: reference route {name} ({count} frames, interpreted and observed).')
                observations.append(checks / 'observe' / (name + '.observe'))
                observations[-1].parent.mkdir(parents=True, exist_ok=True)
                reference[name] = run(observer, checks / 'reference', name, count, scripts[name], '--pack', str(pack),
                                      '--observe', str(observations[-1]))
                if not reference[name]['nonuniform_frames']:
                    raise ConversionError(f'PlayStation {name}: no picture was produced.')
                require_moving_picture(route_liveness(reference[name]['trace']), lambda: ConversionError(
                    f'PlayStation {name}: the picture never changed during the route; the game is stuck.'))
        timings['reference_routes'] = round(time.perf_counter() - phase, 3)
        phase = time.perf_counter()
        with stages.phase('code_generation'):
            pairs, overflow = psx_native.read_observations(observations)
            from .feedback import records
            hints = psx_native.add_hints(pairs, records('psx', sha, psx_native.HINT_KIND))
            native = psx_native.write(tree / 'mednafen' / 'psx' / 'cpu.c', pairs, project)
            psx_build.set_native(project, tree, True)
        emit(f'PlayStation: {native["instructions"]} observed instructions in {native["steps"]} native steps; '
             'building the game.')
        with stages.phase('compile'):
            program = psx_build.build_game(project, emit)
        final = project / executable_name(title)
        emit('PlayStation: appending the disc to the game.')
        psx_pack.write_embedded(item.path, program, final)
        timings['native_build'] = round(time.perf_counter() - phase, 3)
        phase = time.perf_counter()
        results = {}
        with stages.phase('reference_and_native_runs'):
            for name, count, _ in plan:
                emit(f'PlayStation: route {name} on the game ({count} frames, native steps).')
                results[name] = run(final, checks / 'routes', name, count, scripts[name])
                difference = trace_difference(results[name]['trace'], reference[name]['trace'])
                require(difference is None, lambda: ConversionError(
                    f'PlayStation {name}: the native steps differ from the interpreter at frame {difference}; '
                    'existing export preserved.'))
        timings['routes'] = round(time.perf_counter() - phase, 3)
        play = next(row for row in plan if row[0] == 'play')
        phase = time.perf_counter()
        emit('PlayStation: checking F8/F9 in a fresh process and rejecting an invalid state, and the controls.')
        with stages.phase('state_checks'):
            states = check_states(final, checks / 'states', 'play', play[1], scripts['play'], results['play']['trace'])
            inputs = check_inputs(final, checks / 'inputs-check')
        timings['state_checks'] = round(time.perf_counter() - phase, 3)
    if not any(reference[name]['nonzero_samples'] for name, _, _ in plan):
        emit('PlayStation: no route produced sound (reported, not refused).')
    final_sha = file_sha256(final)
    refuse_compression(final_sha, 'A PlayStation game carries its disc after the program: it is published as built, '
                                  'uncompressed (UPX would move the data the program reads).')
    checks_rows = []
    for name, count, text in plan:
        r = results[name]
        ran = r['native_instructions'] + r['interpreted_instructions']
        checks_rows.append({'name': name, 'frames': count, 'native_entries': r['native_instructions'],
                            'interpreted_opcodes': r['interpreted_instructions'],
                            'interpreter_percent': round(100.0 * r['interpreted_instructions'] / ran, 4) if ran else 0.0,
                            'reference_interpreted_opcodes': reference[name]['interpreted_instructions'],
                            # fetches that ran no instruction (an interrupt taken, the CPU held by a DMA): neither count
                            'unrun_fetches': r['unrun_fetches'],
                            'image_hash': r['image_hash'], 'pcm_hash': r['pcm_hash'], 'nonzero_samples': r['nonzero_samples'],
                            'liveness': route_liveness(r['trace']), 'trace_sha256': file_sha256(r['trace']),
                            'script_sha256': hashlib.sha256(text.encode('ascii')).hexdigest()})
    report = {
        'tool': 'Retro-Recomp', 'version': __version__, 'created_utc': datetime.now(timezone.utc).isoformat(),
        'system': {'id': 'psx', 'name': 'Sony PlayStation', 'status': PLAYSTATION.status}, 'private_development_only': False,
        'target': target_id(),
        'rom': item.metadata(), 'converted': True,
        'disc': {'discs': [d.metadata() for d in item.discs], 'container': item.discs[0].container,
                 'carried': 'appended to the executable and read in place'},
        'bios': (bios.metadata() | {'kind': 'player'}) if bios else {'kind': 'free', 'name': 'OpenBIOS (PCSX-Redux, MIT)'},
        'compiler': {'machine': 'Beetle PSX (GPL-2.0)', 'machine_revision': psx_beetle.BEETLE_REV,
                     'adaptation': psx_beetle.adaptation_digest(),
                     'native_cpu': 'guarded native steps of the observed R3000A code (the interpreter\'s handler bodies, its '
                                   'timing kept); the rest runs on the core interpreter and is counted',
                     'native_steps': native | {'observation_overflow': overflow, 'runtime_hints_added': hints}},
        'final_checks': checks_rows,
        'native_validation': {'passed': True, 'scope': 'every route played on the published game (native steps) gives the '
                                                        'same picture, sound and RAM on every frame as the interpreter alone '
                                                        '(the observing build, another process)',
                              'reference_kind': "the core's interpreter (Beetle PSX at the same revision)",
                              'cpu_fidelity_validated': False, 'independent_cpu_oracle': False,
                              'hardware_fidelity_validated': False, 'full_game_validated': False},
        'native_coverage': 'observed main-RAM and BIOS code of the routes (up to four words per address), guarded by the fetched word',
        'video_model': {'standard': video_mode, 'renderer': 'software, native resolution', 'display_aspect': '4:3',
                        'interlaced_pictures': 'shown progressive: the GPU draws both fields of the displayed frame (Beetle\'s '
                                               '"Off" deinterlacing; drawing time kept at the console\'s), which the console '
                                               'itself does not do; weave and bob show its fields (F3)',
                        'frame_pacing': 'the core\'s own rate: 59.826 Hz progressive, 59.94 Hz interlaced (PAL 49.761 / 50)'},
        'audio_cpu': None, 'audio_model': {'kind': 'SPU of the machine (Beetle)', 'rate': 44100, 'channels': 2},
        'counter_unit': 'retired instructions', 'runtime_learning': False, 'runtime_feedback': feedback,
        'hardware_fidelity': 'not measured' + ('' if bios else '; free BIOS (OpenBIOS) instead of the console\'s own'),
        'physical_latency_measured': False, 'latency_ms': None,
        'hardware_accuracy_validated': False, 'full_game_validated': False,
        'game_states': {'supported': True, 'save_key': 'F8', 'load_key': 'F9',
                        'compatibility': 'exact disc, BIOS, machine revision and session sources', 'validation': states},
        'artwork': prepared['artwork'], 'windows_metadata': prepared['windows_metadata'],
        'executable': executable_name(title), 'build_executable': str(final), 'toolchain': toolchain_description(),
        'build_directory': str(project), 'published_compressed': False, 'executable_sha256': final_sha,
        'executable_bytes': final.stat().st_size, 'scan_level': level, 'conversion_phases_seconds': timings,
        'conversion_wall_seconds': round(time.perf_counter() - started, 3),
        'input_check': inputs,
        'qualification_scope': {'controls': 'DualShock pad (digital mode at power-on, as the console\'s pad; sticks, L2/R2 on '
                                            'the triggers, the Analog button), players 1 and 2; the validation routes drive '
                                            'player 1 with the digital buttons',
                                'universal_zero_fallback_claim': False}}
    write_report(output / 'conversion-report.json', report)
    shares = [row['interpreter_percent'] for row in checks_rows]
    emit(f'PlayStation: {title} ready (native steps; interpreter fallback {min(shares)}-{max(shares)} % of the routes\' '
         f'instructions, counted; {final.stat().st_size // 1048576} MB with the disc inside).')
    return final
