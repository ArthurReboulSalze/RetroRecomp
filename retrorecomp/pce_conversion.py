"""PC Engine conversion (experimental; docs/PC_ENGINE.md).

Every route runs twice in the same build of the game: once with every instruction forced through the engine's
interpreter (`--reference`, the fresh reference) and once with the guarded native module. Their per-frame CPU, work
RAM, picture and PCM traces must be identical, before and after compression, and quick states must continue the
saved timeline in a fresh process. The native module comes from what the runs observed (the engine's code capture:
its static analysis stops at the first TAM, so a HuCard is never translated from the ROM alone). Interpreted
instructions that remain are counted and reported; the code they ran becomes guarded native code in the next pass.

An installation without the machine's native files (`PC_ENGINE.available()`) refuses a conversion with `NOT_YET`.
Nothing is written beside the ROMs.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import time

from . import __version__
from .core import ConversionError
from .pce_rom import read_hucard
from .platforms import target_id
from .report_schema import write_report

# The engine (MIT; licenses/pcenginerecomp.md), pinned by commit: it has no release or tag, and every change of its
# runtime ABI means re-emitting, rebuilding and requalifying (docs/UPSTREAMS.md). Gate of 5 November 2026 at this pin:
# .build notes of the PC Engine specialist, summarised in docs/PC_ENGINE.md.
ENGINE_REPO = 'rages4calm/pcenginerecomp'
ENGINE_REV = '81b5c231e452c6879d58585c8863012e438f1d55'
ENGINE_ABI = 29

NOT_YET = 'The PC Engine converter files are missing from this installation.'
STATE_SETTLE = 600          # frames continued after a quick state is loaded
LIVENESS_FIELDS = {'frames': 'frames', 'distinct_pictures': 'distinct_pictures', 'picture_changes': 'picture_changes',
                   'last_picture_change_frame': 'last_picture_change_frame', 'audible_frames': 'audible_frames',
                   'last_audible_frame': 'last_audible_frame'}
# Engine pad bits (native/pce_machine.h).
I, II, SELECT, RUN, UP, RIGHT, DOWN, LEFT = 0x001, 0x002, 0x004, 0x008, 0x010, 0x020, 0x040, 0x080
LONG_ROUTES = {'quick': 0, 'standard': 0, 'extended': 1, 'thorough': 2}
LONG_FRAMES = 18000
CAPTURE_IDENTITY_LIMIT = 65536      # the engine's bound on identities per capture and per module profile


def _system() -> dict:
    """The report's `system`: the profile's id and display name (one place for the name)."""
    from .systems import get_profile
    profile = get_profile('pce')
    return {'id': profile.id, 'name': profile.name}


def identification_report(card, level: str = 'standard') -> dict:
    """The writer's keys for a card that was identified and not converted: no measure is reported."""
    return {'tool': 'Retro-Recomp', 'version': __version__, 'created_utc': datetime.now(timezone.utc).isoformat(),
            'system': _system(), 'target': target_id(),
            'rom': card.metadata(), 'scan_level': level, 'converted': False,
            'native_validation': {'passed': False, 'scope': 'not converted: nothing was compared',
                                  'cpu_fidelity_validated': False, 'independent_cpu_oracle': False},
            'native_coverage': 'not converted', 'final_checks': [], 'hucard_checks': [],
            'game_states': {'supported': False, 'fresh_process_verified': False},
            'hardware_accuracy_validated': False, 'full_game_validated': False, 'latency_ms': None}


def write_identification_report(path, card, level: str = 'standard') -> dict:
    return write_report(path, identification_report(card, level))


# ------------------------------------------------------------------ routes

def _script(rows) -> str:
    """'frame p1 p2' lines (hex pad masks), each held from its frame on (native/pce_main.c)."""
    return ''.join(f'{frame} {p1:03x} {p2:03x}\n' for frame, p1, p2 in rows) or '0 000 000\n'


START_PRESSES = (1, 2, 3, 4, 6)   # the start variants a conversion tries on its play route (fresh reference runs)
PRESS_SPACING = 240              # frames between two Run presses of the start
WALK_SETTLE = 180                # frames between the last press and the walk: directions must not move a menu's cursor early
RUN_PAIR_EVERY = 900             # frames between two pairs of Run presses during the walk
QUIET_WALK = 900                 # frames of walk with directions only: no I or II, which would type into a password screen


def walk_start(presses: int) -> int:
    return max(900, PRESS_SPACING * presses + WALK_SETTLE)


def start_candidates(frames: int) -> list[int]:
    """The start variants that leave a route of `frames` at least ten seconds of walk."""
    return [presses for presses in START_PRESSES if walk_start(presses) + 600 <= frames]


def play_rows(frames: int, seed: int, presses: int = 3) -> list:
    """Run pressed `presses` times during the title (most HuCards start on Run; stories, menus and password screens
    ask for more), then a deterministic walk: a held direction changing every second or so, I and II tapped, and now and
    then Run twice in a row. In play that is a pause and its end; on a screen that waits for Run, the way out (a story,
    a continue prompt, a game over). The first QUIET_WALK frames of the walk use directions only, so a menu or a password
    screen answers with a cursor and not with typed letters (that is what `reach` counts). One press too many pauses the
    game: `choose_start` keeps the variant that answers."""
    rows = []
    for index in range(presses):
        at = PRESS_SPACING * (index + 1)
        rows += [(at, RUN, 0), (at + 6, 0, 0)]
    state = seed & 0xFFFFFFFF or 1
    directions = (RIGHT, RIGHT | UP, RIGHT | DOWN, LEFT, UP, DOWN, RIGHT)
    frame = walk_start(presses)
    pair = frame + RUN_PAIR_EVERY
    while frame < frames:
        if frame >= pair and frame + 36 < frames:     # a pair is whole or absent
            rows += [(frame, RUN, 0), (frame + 6, 0, 0), (frame + 24, RUN, 0), (frame + 30, 0, 0)]
            frame += 36
            pair = frame + RUN_PAIR_EVERY
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        held = directions[state % len(directions)]
        span = 30 + (state >> 8) % 60
        if frame < walk_start(presses) + QUIET_WALK:
            rows.append((frame, held, 0))
        for tap in range(0, span - 4, 12):      # every release falls inside this span: frames never go back
            if frame < walk_start(presses) + QUIET_WALK:
                break
            button = I if (state >> (tap % 7)) & 1 else II
            rows += [(frame + tap, held | button, 0), (frame + tap + 4, held, 0)]
        frame += span
    rows = [row for row in rows if row[0] < frames]
    assert all(a[0] <= b[0] for a, b in zip(rows, rows[1:])), 'route frames must not go back'
    return rows


def routes(identity: str, *, frames: int, level: str, presses: int = 3) -> list[tuple[str, int, str]]:
    """(name, frames, script): attract (no input), play, then long routes at the extended and thorough levels."""
    seed = int(identity[:8], 16)
    rows = [] if level == 'quick' else [('attract', frames, _script([]))]
    play = max(frames, 1800)
    rows.append(('play', play, _script(play_rows(play, seed, presses))))
    for index in range(LONG_ROUTES[level]):
        rows.append((f'long-{index + 1}', LONG_FRAMES,
                     _script(play_rows(LONG_FRAMES, seed + 7919 * (index + 1), presses))))
    return rows


def liveness_score(liveness: dict) -> tuple:
    """How alive a route stayed: the latest picture change first, then the number of changes, then audible frames."""
    return (liveness.get('last_picture_change_frame') or 0, liveness.get('picture_changes') or 0,
            liveness.get('audible_frames') or 0)


def divergence(trace: Path, baseline: Path) -> int:
    """Frames whose picture differs from the same frame of the route without input: what the input changed on screen.
    A variant whose presses the game ignored (it kept playing its demo) has none; work RAM is not used, since the
    game's pad reader stores the input even when nothing else reacts (Bonk's Adventure, 5 November 2026)."""
    def rows(path):
        return {fields[0]: fields[3] for fields in
                (line.split(',') for line in Path(path).read_text(encoding='ascii').splitlines()[1:]) if len(fields) == 6}
    ours, theirs = rows(trace), rows(baseline)
    return sum(1 for frame, value in ours.items() if theirs.get(frame) != value)


def reach(trace: Path, baseline: Path, start: int) -> int:
    """How many distinct pictures the directions-only part of the walk (QUIET_WALK frames after `start`) showed that the same
    frames without input never showed: how much the game answers the pad. A demo, a title, a story and a paused game show the
    same pictures with or without the walk, a menu or a password screen a handful (the cursor's places), and a game in play
    hundreds of its own."""
    def pictures(path):
        found = set()
        for line in Path(path).read_text(encoding='ascii').splitlines()[1:]:
            fields = line.split(',')
            if len(fields) == 6 and fields[0].isdigit() and start <= int(fields[0]) < start + QUIET_WALK:
                found.add(fields[3])
        return found
    return len(pictures(trace) - pictures(baseline))


def choose_start(results: dict, frames: int) -> int:
    """The number of Run presses for the play route. `results` maps presses to {'liveness', 'divergence', 'reach'}.

    A variant must keep the picture moving until its last 120 frames (a press too many pauses the game); among those,
    the one whose walk reached the most pictures of its own wins, then the one the input changed the most from the demo
    (ties: the fewest presses). When none stays alive, the livelier one is kept."""
    alive = [presses for presses, result in results.items()
             if (result['liveness'].get('last_picture_change_frame') or 0) >= frames - 120]
    if alive:
        return max(sorted(alive), key=lambda presses: (results[presses]['reach'], results[presses]['divergence'], -presses))
    return max(sorted(results), key=lambda presses: (liveness_score(results[presses]['liveness']), -presses))


# ------------------------------------------------------------------ runs and traces

def trace_rows(trace: Path):
    from .delivery_evidence import FrameRow, silent_hash
    for line in trace.read_text(encoding='ascii').splitlines():
        fields = line.split(',')
        if len(fields) != 6 or not fields[0].isdigit():
            continue
        frame, image, sound, samples = int(fields[0]), fields[3], fields[4], int(fields[5])
        yield FrameRow(frame, image, sound=sound, audible=sound != silent_hash(samples))


def route_liveness(trace: Path) -> dict:
    from .delivery_evidence import liveness_summary, report_fields
    return report_fields(liveness_summary(trace_rows(trace)), LIVENESS_FIELDS)


def run(executable: Path, folder: Path, name: str, frames: int, script: Path, *extra: str,
        ends_at: int | None = None) -> dict:
    from .conversion_common import check_exit, spawn
    folder.mkdir(parents=True, exist_ok=True)
    report, trace = folder / (name + '.json'), folder / (name + '.csv')
    completed = spawn([str(executable), '--headless', '--frames', str(frames), '--script', str(script),
                       '--trace', str(trace), '--report', str(report), *extra],
                      cwd=folder, timeout=max(600, frames // 5), capture_output=True, text=True)

    def failure(result):
        detail = (result.stderr or result.stdout).strip().splitlines()[-1:] or ['no output']
        return ConversionError(f'PC Engine {name} run failed ({result.returncode}): {detail[0]}')
    check_exit(completed, failure)
    result = json.loads(report.read_text(encoding='utf-8'))
    if result['frames'] != (frames if ends_at is None else ends_at) or result['save_failed']:
        raise ConversionError(f'PC Engine {name} run ended early or could not save its state.')
    result['trace'] = trace
    return result


def damaged_states(state: bytes) -> dict[str, bytes]:
    """Damaged copies of a quick state (native/console16_state.c: magic, version, system, region, size, checksum, ROM
    identity, ABI, then the payload), by what is wrong with them: the game must refuse every one (exit 4)."""
    def flipped(offset: int) -> bytes:
        data = bytearray(state)
        data[offset] ^= 0x80
        return bytes(data)
    return {'empty': b'', 'header-cut': state[:40], 'one-byte-short': state[:-1], 'body-cut': state[:len(state) // 2],
            'magic': flipped(0), 'version': flipped(8), 'system': flipped(12), 'size': flipped(20), 'checksum': flipped(24),
            'rom': flipped(32), 'abi': flipped(96), 'payload': flipped(len(state) - 1), 'not-a-state': b'not a state.' * 4096}


def check_states(executable: Path, folder: Path, name: str, frames: int, script: Path, expected: Path) -> dict:
    """F8 at a frame, F9 in a fresh process: the continued timeline must match; every damaged state is refused (exit 4)
    and left as it was; loading a missing state is refused and creates nothing."""
    from .conversion_common import spawn
    from .conversion_gates import continuation_difference, require
    at = max(60, frames - STATE_SETTLE - 60)
    state = folder / 'quick.rrstate'
    run(executable, folder, 'save', at + 1, script, '--save-state', str(state), '--save-at', str(at))
    run(executable, folder, 'load', STATE_SETTLE, script, '--load-state', str(state), ends_at=at + STATE_SETTLE)
    rows = expected.read_text(encoding='ascii').splitlines()[1:]
    resumed = (folder / 'load.csv').read_text(encoding='ascii').splitlines()[1:]
    require(continuation_difference(rows, resumed, at, STATE_SETTLE) is None,
            lambda: ConversionError('PC Engine F9 continuation differs from its saved timeline; existing export preserved.'))
    def refused(path: Path) -> bool:
        return spawn([str(executable), '--headless', '--frames', '1', '--load-state', str(path)],
                     cwd=folder, timeout=120, capture_output=True).returncode == 4
    original = state.read_bytes()
    damaged = damaged_states(original)
    for label, data in damaged.items():
        invalid = folder / f'invalid-{label}.rrstate'
        invalid.write_bytes(data)
        require(refused(invalid), lambda: ConversionError(f'PC Engine accepted a damaged quick state ({label}).'))
        require(invalid.read_bytes() == data,
                lambda: ConversionError(f'PC Engine rewrote a quick state it refused ({label}).'))
    missing = folder / 'missing.rrstate'
    missing.unlink(missing_ok=True)
    require(refused(missing), lambda: ConversionError('PC Engine accepted a missing quick state.'))
    require(not missing.exists(), lambda: ConversionError('Loading a missing quick state created a file.'))
    return {'route': name, 'saved_at': at, 'continued_frames': STATE_SETTLE, 'fresh_process_match': True,
            'truncated_state_rejected': True, 'damaged_states_refused': sorted(damaged),
            'missing_state_creates_nothing': True, 'state_bytes': len(original)}


# ------------------------------------------------------------------ the Backup RAM file (native/pce_backup.c)

BACKUP_BYTES = 2048
BACKUP_HEADER = 112
BACKUP_MAGIC = b'RRPCEBR1'
BACKUP_FRAMES = 60          # frames of a run that only checks what a file gave the game at the start
# What the game finds with no save: the file system header as Beetle formats it on a HuCard, nothing stored.
BACKUP_FORMATTED = b'HUBM\x00\x88\x10\x80' + bytes(BACKUP_BYTES - 8)


def fnv64(data: bytes) -> int:
    value = 14695981039346656037
    for byte in data:
        value = ((value ^ byte) * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return value


def backup_file(memory: bytes, rom_sha256: str) -> bytes:
    """A Backup RAM file: magic, version 1, size, FNV-1a of the memory, reserved, the HuCard's SHA-256 in hex, reserved, the memory."""
    header = bytearray(BACKUP_HEADER)
    header[:8] = BACKUP_MAGIC
    header[8:12] = (1).to_bytes(4, 'little')
    header[12:16] = len(memory).to_bytes(4, 'little')
    header[16:24] = fnv64(memory).to_bytes(8, 'little')
    header[40:104] = rom_sha256.encode('ascii')
    return bytes(header) + memory


def damaged_backups(good: bytes) -> dict[str, bytes]:
    """Files the game cannot use, by what is wrong with them: each must be set aside whole, and the game must start formatted."""
    def flipped(offset: int) -> bytes:
        data = bytearray(good)
        data[offset] ^= 0x80
        return bytes(data)
    return {'empty': b'', 'header-cut': good[:40], 'one-byte-short': good[:-1], 'one-byte-long': good + b'\0',
            'raw-memory': good[BACKUP_HEADER:], 'magic': flipped(0), 'version': flipped(8), 'size': flipped(12),
            'hash': flipped(16), 'other-card': flipped(40), 'memory': flipped(len(good) - 1)}


def check_backup(executable: Path, folder: Path, frames: int, script: Path, rom_sha256: str) -> dict:
    """The save beside the game, in fresh processes. No file: the formatted memory, and nothing written unless the game wrote. A
    valid file reaches the game. Damaged files are set aside whole and never block it. What the play route leaves in the memory
    is there in the next process. With the same memory, the game and the interpreted reference stay equal on the play route."""
    from .conversion_gates import require, require_same_file
    from .delivery_evidence import same_trace

    def failure(text: str):
        return lambda: ConversionError(f'PC Engine Backup RAM: {text}')

    def hex64(data: bytes) -> str:
        return f'{fnv64(data):016x}'
    quiet = folder / 'quiet.inputs'
    folder.mkdir(parents=True, exist_ok=True)
    quiet.write_text(_script([]), encoding='ascii', newline='\n')
    none = folder / 'none.rrsram'
    start = run(executable, folder, 'backup-none', BACKUP_FRAMES, quiet, '--backup', str(none))
    require(start['backup_start_hash'] == hex64(BACKUP_FORMATTED) and not start['backup_notice'],
            failure('without a file the game did not find the formatted memory.'))
    require(none.exists() == (start['backup_hash'] != start['backup_start_hash']),
            failure('a file was written though the game wrote nothing, or the reverse.'))
    seeded = BACKUP_FORMATTED[:-1] + b'\x5a'
    valid = folder / 'valid.rrsram'
    good = backup_file(seeded, rom_sha256)
    valid.write_bytes(good)
    loaded = run(executable, folder, 'backup-valid', BACKUP_FRAMES, quiet, '--backup', str(valid))
    require(loaded['backup_start_hash'] == hex64(seeded) and not loaded['backup_notice'],
            failure('a valid file did not reach the game.'))
    damaged = damaged_backups(good)
    for label, data in damaged.items():
        path = folder / f'damaged-{label}.rrsram'
        path.write_bytes(data)
        result = run(executable, folder, f'backup-{label}', BACKUP_FRAMES, quiet, '--backup', str(path))
        aside = path.with_name(path.name + '.unusable-1')
        require(result['backup_notice'] == 1 and result['backup_start_hash'] == hex64(BACKUP_FORMATTED),
                failure(f'a damaged file ({label}) was used.'))
        require(aside.is_file() and aside.read_bytes() == data, failure(f'a damaged file ({label}) was not kept as it was.'))
    route = folder / 'route.rrsram'
    played = run(executable, folder, 'backup-route', frames, script, '--backup', str(route))
    changed = played['backup_hash'] != played['backup_start_hash']
    require(route.exists() == changed, failure('the file does not follow what the game wrote on the play route.'))
    if changed:
        survived = run(executable, folder, 'backup-survived', BACKUP_FRAMES, quiet, '--backup', str(route))
        require(survived['backup_start_hash'] == played['backup_hash'],
                failure('what the game wrote did not survive into a fresh process.'))
    memory = route.read_bytes() if changed else good
    native_copy, reference_copy = folder / 'same-native.rrsram', folder / 'same-reference.rrsram'
    native_copy.write_bytes(memory)
    reference_copy.write_bytes(memory)
    native = run(executable, folder, 'backup-same-native', frames, script, '--backup', str(native_copy))
    reference = run(executable, folder, 'backup-same-reference', frames, script, '--reference', '--backup', str(reference_copy))
    require(same_trace(native['trace'], reference['trace']),
            failure('with the same memory the game and the reference differ on the play route.'))
    require_same_file(native_copy, reference_copy, failure('with the same memory the two runs saved different files.'))
    return {'play_route_wrote_memory': changed, 'written_memory_survives_a_fresh_process': changed or None,
            'no_file_starts_formatted': True, 'valid_file_loaded': True, 'damaged_files_set_aside': sorted(damaged),
            'same_memory_reference_match': True, 'same_memory_was': 'the play route\'s' if changed else 'an authored file',
            'bytes_beyond_2k_on_play_route': played['backup_beyond']}


def complete_prefix(executable: Path, folder: Path, name: str, script: Path, result: dict, emit):
    """(capture, frames): a complete capture of the start of a route whose full capture lost identities, or (None, 0)."""
    frames = int(result['capture_first_drop_frame']) - 1
    for attempt in range(3):
        if frames < 60:
            emit(f'PC Engine {name}: the engine met more than {CAPTURE_IDENTITY_LIMIT} distinct code identities '
                 'within the first minute: no observation can be kept from this route.')
            return None, 0
        capture = folder / f'{name}-prefix{attempt}-capture.json'
        again = run(executable, folder, f'{name}-prefix{attempt}', frames, script, '--code-capture', str(capture))
        if not again.get('capture_dropped'):
            emit(f'PC Engine {name}: complete capture of the first {frames} of {result["frames"]} frames '
                 f'({again.get("capture_identities")} identities).')
            return capture, frames
        frames = int(again['capture_first_drop_frame']) - 1
    return None, 0


def compose_fitting(captures: list, out: Path, work: Path):
    """Compose the captures that fit one profile (the engine's union bound is 65,536 identities, never a silent
    drop): each one is tried in order, a capture that would overflow is left out. (kept, skipped)."""
    from .pce_build import PceBuildError, compose
    kept, skipped = [], []
    for capture in captures:
        trial = work / 'trial-profile.json'
        trial.unlink(missing_ok=True)
        try:
            compose([*kept, capture], trial)
        except PceBuildError as error:
            if 'capacity exceeded' not in str(error):
                raise
            skipped.append(capture)
            continue
        kept.append(capture)
    if not kept:
        raise ConversionError('No capture of this card fits one native module.')
    out.unlink(missing_ok=True)
    compose(kept, out)
    return kept, skipped


def observed(capture: Path) -> int:
    try:
        return len(json.loads(capture.read_text(encoding='utf-8')).get('observations', ()))
    except (OSError, ValueError):
        return 0


# ------------------------------------------------------------------ the conversion

def convert(path: Path, *, title=None, output=None, cover=None, use_cover=True, online_cover=True, boxart_dir=None,
            passes=3, frames=3600, scan_level=None, standard_override=None, profile=None, emit=print, **unused) -> Path:
    from .systems.pc_engine import PC_ENGINE
    card = read_hucard(path)
    if not PC_ENGINE.available():
        raise ConversionError(NOT_YET)
    started = time.perf_counter()
    from . import pce_build, timings as stages
    from .conversion_common import resolve_scan_level
    from .conversion_gates import require_same_file
    from .core import executable_name
    from .delivery_evidence import deliver_packed, replay_packed, require_moving_picture, same_trace
    from .library import entry_lock, file_sha256
    from .paths import ROOT
    from .toolchain import describe as toolchain_description
    level = resolve_scan_level(scan_level)
    if standard_override not in (None, 'ntsc', 'auto'):
        raise ConversionError('The PC Engine profile is NTSC only.')
    if profile is not None:
        raise ConversionError('PC Engine HuCards are read from their content; TOML cartridge profiles do not apply.')
    title = title or card.title
    if any(ord(c) < 32 for c in title) or len(title) > 160:
        raise ConversionError('Invalid PC Engine game title.')
    if output is None:
        from .paths import games_directory
        output = games_directory(system_id='pce') / 'datas/reports' / card.sha256
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    from .feedback import ingest
    feedback = ingest('pce', card.sha256, output, emit=emit)
    plan_frames = max(600, min(int(frames or 3600), 10000))
    plan = routes(card.sha256, frames=plan_frames, level=level)
    route_start = None
    timings = {}
    # Short folders: the engine names its module's object library after a 64-digit hash, and Visual Studio's 260-character
    # paths must still hold it under the build folder.
    work = ROOT / '.build' / 'pce' / card.sha256[:12]
    with entry_lock(work, timeout=1800):
        project, checks = work / 'n', work / 'checks'
        shutil.rmtree(checks, ignore_errors=True)
        scripts = {}
        for name, count, text in plan:
            scripts[name] = checks / 'inputs' / (name + '.inputs')
            scripts[name].parent.mkdir(parents=True, exist_ok=True)
            scripts[name].write_text(text, encoding='ascii', newline='\n')
        emit(f'PC Engine {card.board} card: scan level {level}, routes ' +
             ', '.join(f'{name} ({count} frames)' for name, count, _ in plan) + '.')
        presentation = {'rom_path': Path(path), 'cover': Path(cover) if cover else None, 'use_cover': use_cover,
                        'online_cover': online_cover, 'boxart_dir': boxart_dir, 'emit': emit}
        pce_build.ensure_engine(emit)
        reference, results, captures, module, prepared = {}, {}, [], None, None
        emitted, skipped_captures = None, 0
        attempts = max(1, min(int(passes or 1), 10))
        for attempt in range(attempts):
            stages.begin_pass(attempt + 1)
            phase = time.perf_counter()
            emit(f'PC Engine: building the game (pass {attempt + 1}, '
                 f'{"everything interpreted" if module is None else "with the guarded native module"}).')
            with stages.phase('code_generation'):
                prepared = pce_build.prepare_game(project, card, title=title, module=module, presentation=presentation)
            with stages.phase('compile'):
                executable = pce_build.build_game(project, emit)
            timings[f'translate_and_build_{attempt + 1}'] = round(time.perf_counter() - phase, 3)
            phase = time.perf_counter()
            candidate = checks / f'pass-{attempt + 1}' / executable.name
            candidate.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(executable, candidate)
            with stages.phase('reference_and_native_runs'):
                if not reference:
                    emit('PC Engine: fresh reference runs (every instruction interpreted).')
                    # The start of the play route: each variant is played on the reference against the same frames
                    # without input (choose_start), and the one kept drives play and the long routes.
                    play_count = next(count for name, count, _ in plan if name == 'play')
                    baseline = checks / 'inputs' / 'play-start0.inputs'
                    baseline.write_text(_script([]), encoding='ascii', newline='\n')
                    variants = {0: run(candidate, checks / 'reference', 'play-start0', play_count, baseline, '--reference')}
                    for presses in start_candidates(play_count):
                        script = checks / 'inputs' / f'play-start{presses}.inputs'
                        script.write_text(_script(play_rows(play_count, int(card.sha256[:8], 16), presses)),
                                          encoding='ascii', newline='\n')
                        variants[presses] = run(candidate, checks / 'reference', f'play-start{presses}', play_count,
                                                script, '--reference')
                    start = {presses: {'liveness': route_liveness(Path(result['trace'])),
                                       'divergence': divergence(result['trace'], variants[0]['trace']),
                                       'reach': reach(result['trace'], variants[0]['trace'], walk_start(presses))}
                             for presses, result in variants.items() if presses}
                    presses = choose_start(start, play_count)
                    route_start = {'run_presses': presses, 'variants': {str(k): v for k, v in start.items()},
                                   'rule': 'alive until the last 120 frames, then most pictures the walk reached that no input never showed'}
                    emit(f'PC Engine: play route starts with Run pressed {presses} time(s) '
                         f'({start[presses]["reach"]} pictures reached that no input never showed).')
                    plan = routes(card.sha256, frames=plan_frames, level=level, presses=presses)
                    for name, count, text in plan:
                        scripts[name].write_text(text, encoding='ascii', newline='\n')
                    for name, count, _ in plan:
                        # The attract route is the play route without input: the same script over the same frames is played
                        # once (play-start0) and its trace is the attract reference.
                        if name == 'attract' and count == play_count and scripts[name].read_text() == baseline.read_text():
                            reference[name] = variants[0]
                        else:
                            reference[name] = (variants[presses] if name == 'play' else
                                               run(candidate, checks / 'reference', name, count, scripts[name], '--reference'))
                for name, count, _ in plan:
                    capture = checks / 'native' / f'pass-{attempt + 1}' / (name + '-capture.json')
                    capture.parent.mkdir(parents=True, exist_ok=True)
                    results[name] = run(candidate, capture.parent, name, count, scripts[name],
                                        '--code-capture', str(capture))
                    results[name]['capture'] = capture
                    results[name]['capture_frames'] = count
                    if results[name].get('capture_dropped'):
                        # The engine keeps at most 65,536 distinct code identities (address, the eight bank registers
                        # and the bytes) per capture and drops the rest: such a capture cannot become a module. The
                        # same route is played again up to the frame before the first drop, which is complete.
                        results[name]['capture'], results[name]['capture_frames'] = complete_prefix(
                            candidate, capture.parent, name, scripts[name], results[name], emit)
            for name, _, _ in plan:
                require_same_file(results[name]['trace'], reference[name]['trace'], lambda: ConversionError(
                    f'PC Engine {name}: native and reference CPU/RAM/picture/PCM traces differ; existing export preserved.'))
                if not results[name]['nonuniform_frames']:
                    raise ConversionError(f'PC Engine {name}: no picture was produced.')
                require_moving_picture(route_liveness(Path(results[name]['trace'])), lambda: ConversionError(
                    f'PC Engine {name}: the picture never changed during the route; the game is stuck.'))
            timings[f'routes_{attempt + 1}'] = round(time.perf_counter() - phase, 3)
            fallback = sum(results[name]['interpreted_instructions'] for name, _, _ in plan)
            if not fallback:
                break
            # The play route first: it is the one that reaches the game; the others add what still fits.
            order = sorted(plan, key=lambda row: row[0] != 'play')
            captures += [results[name]['capture'] for name, _, _ in order
                         if results[name]['capture'] and observed(results[name]['capture'])]
            if attempt + 1 == attempts or not captures:
                emit(f'PC Engine: {fallback} interpreted instructions remain; they stay counted and reported.')
                break
            emit(f'PC Engine: {fallback} interpreted instructions observed; emitting guarded native code.')
            with stages.phase('code_generation'):
                profile_path = work / f'observations-{attempt + 1}.json'
                profile_path.unlink(missing_ok=True)
                kept, skipped = compose_fitting(captures, profile_path, work)
                skipped_captures += len(skipped)
                captures = kept
                new_module = work / f'module-{attempt + 1}'
                shutil.rmtree(new_module, ignore_errors=True)
                manifest = pce_build.emit_module(profile_path, new_module)
            emit(f'PC Engine: {manifest.get("native_instructions_emitted", 0)} instructions in '
                 f'{manifest.get("native_contexts", 0)} bank contexts emitted'
                 + (f' ({len(skipped)} capture(s) left out: the engine keeps at most 65,536 identities).' if skipped else '.'))
            if manifest.get('native_instructions_emitted') == emitted:
                emit('PC Engine: nothing new fits in the module; the remaining interpreted instructions stay counted.')
                break
            module, emitted = new_module, manifest.get('native_instructions_emitted')
        stages.end_passes()
        if not any(results[name]['nonzero_samples'] for name, _, _ in plan):
            emit('PC Engine: no route produced sound (reported, not refused: a silent title screen is possible).')
        phase = time.perf_counter()
        packed = project / ('packed-game.exe' if os.name == 'nt' else 'packed-game')
        delivered = deliver_packed(executable, packed, 'PC Engine', emit)
        with stages.phase('packed_replays'):
            final = {row[0]: result for row, result in zip(plan, replay_packed(
                delivered, plan, lambda row: run(packed, checks / 'packed', row[0], row[1], scripts[row[0]]),
                same=lambda row, result: same_trace(result['trace'], reference[row[0]]['trace']),
                mismatch=lambda row: ConversionError(f'PC Engine {row[0]}: compressed executable differs from the reference.')))}
        timings['packed_replays'] = round(time.perf_counter() - phase, 3)
        phase = time.perf_counter()
        emit('PC Engine: checking F8/F9 in a fresh process and rejecting an invalid state.')
        play = next(row for row in plan if row[0] == 'play')
        with stages.phase('state_checks'):
            states = check_states(packed, checks / 'states', 'play', play[1], scripts['play'], final['play']['trace'])
        timings['state_checks'] = round(time.perf_counter() - phase, 3)
        phase = time.perf_counter()
        emit('PC Engine: checking the Backup RAM file in fresh processes and setting damaged files aside.')
        with stages.phase('state_checks'):
            backup = check_backup(packed, checks / 'backup', play[1], scripts['play'], card.sha256)
        timings['backup_checks'] = round(time.perf_counter() - phase, 3)
    beyond = {name: final[name]['backup_beyond'] for name, _, _ in plan if final[name]['backup_beyond']}
    if beyond:
        emit(f'PC Engine: the game wrote past the 2 KiB of the Backup RAM on {sorted(beyond)}: reported, the chip has no cell there.')
    checks_rows = []
    for name, count, text in plan:
        native = final[name]
        total = native['native_instructions'] + native['interpreted_instructions']
        checks_rows.append({'name': name, 'frames': count, 'native_entries': native['native_instructions'],
            'interpreted_opcodes': native['interpreted_instructions'], 'guard_misses': native['guard_misses'],
            'interpreter_percent': round(100 * native['interpreted_instructions'] / max(1, total), 6),
            'reference_match': True, 'cpu_hash': native['cpu_hash'], 'ram_hash': native['ram_hash'],
            'image_hash': native['image_hash'], 'pcm_hash': native['pcm_hash'],
            'nonzero_samples': native['nonzero_samples'], 'cropped_frames': native['cropped_frames'],
            'backup_hash': native['backup_hash'], 'backup_written': native['backup_hash'] != native['backup_start_hash'],
            'backup_beyond_2k': native['backup_beyond'],
            'liveness': route_liveness(Path(native['trace'])), 'trace_sha256': file_sha256(native['trace']),
            'script_sha256': hashlib.sha256(text.encode('ascii')).hexdigest()})
    native_coverage = all(not row['interpreted_opcodes'] for row in checks_rows)
    manifest = json.loads((module / 'module.json').read_text(encoding='utf-8')) if module else {}
    report = {'tool': 'Retro-Recomp', 'version': __version__,
        'created_utc': datetime.now(timezone.utc).isoformat(), 'system': _system(),
        'rom': card.metadata(), 'converted': True,
        'compiler': {'engine': ENGINE_REPO, 'engine_revision': ENGINE_REV, 'runtime_abi': ENGINE_ABI,
                     'native_cpu': 'guarded HuC6280 instructions emitted from observed runs (full MPR context, '
                                   'physical fetch addresses and exact bytes checked before each one)'},
        'hucard_checks': {'board': card.board, 'header': card.header, 'encoding': card.encoding,
                          'rom_bytes': card.rom_bytes, 'decoded_sha256': card.decoded_sha256,
                          'native_instructions_emitted': manifest.get('native_instructions_emitted', 0),
                          'native_contexts': manifest.get('native_contexts', 0),
                          'translation_units': len(manifest.get('translation_units', ())),
                          'observation_sources': len(captures), 'captures_left_out': skipped_captures,
                          'capture_identity_limit': CAPTURE_IDENTITY_LIMIT,
                          'capture_frames': {name: results[name].get('capture_frames') for name, _, _ in plan}},
        'final_checks': checks_rows,
        'native_validation': {'passed': True, **delivered.validation_fields(), 'reference_before_learning': True,
            'reference_kind': "the same build with every instruction through the engine's interpreter",
            'cpu_agreement': True, 'cpu_fidelity_validated': False, 'independent_cpu_oracle': False,
            'hardware_fidelity_validated': False, 'full_game_validated': False},
        'native_coverage': native_coverage,
        'video_model': {'standard': 'ntsc', 'master_ticks_per_frame': 1365 * 262, 'display_aspect': '4:3'},
        'audio_cpu': None, 'audio_model': {'kind': 'PSG of the HuC6280 (the engine)', 'rate': 44100, 'channels': 2},
        'counter_unit': 'retired instructions', 'runtime_learning': False, 'runtime_feedback': feedback,
        'physical_latency_measured': False, 'latency_ms': None,
        'hardware_accuracy_validated': False, 'full_game_validated': False,
        'game_states': {'supported': True, 'save_key': 'F8', 'load_key': 'F9',
                        'compatibility': 'exact HuCard, engine revision and bridge sources', 'validation': states},
        'backup_ram': {'supported': True, 'bytes': BACKUP_BYTES, 'file': 'datas/saves/<game>-<card>.rrsram',
                       'compatibility': 'exact HuCard; survives a rebuild of the game',
                       'model': 'bank $F7 as plain RAM set by the host (no lock; 8 KiB where the chip has 2 KiB; past 2 KiB is reported)',
                       'formatted_without_a_save': 'the file system header HUBM 00 88 10 80, then zeros, as Beetle does on a HuCard',
                       'quick_state': 'holds the memory too: F9 brings it back as it was, and the file follows',
                       'validation': backup},
        'artwork': prepared['artwork'], 'windows_metadata': prepared['windows_metadata'],
        'executable': executable_name(title), 'build_executable': str(executable), 'toolchain': toolchain_description(),
        'build_directory': str(project), **delivered.report_fields(), 'scan_level': level,
        'conversion_phases_seconds': timings, 'conversion_wall_seconds': round(time.perf_counter() - started, 3),
        'route_start': route_start,
        'qualification_scope': {
            'controls': f'{prepared["pad_buttons"]}-button pads, players 1 to {prepared["players"]}; the validation '
                        'routes drive player 1',
            'universal_zero_fallback_claim': False}}
    write_report(output / 'conversion-report.json', report)
    emit(f'PC Engine: {title} ready ({"no interpreter on the routes played" if native_coverage else "interpreter fallback reported"}).')
    return executable
