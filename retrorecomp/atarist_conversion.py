"""Atari ST conversion (experimental): a game's floppy images become a standalone game (MIT; the executable it builds is linked with
Hatari, GPL-2.0, and is distributed under the GPL: licenses/hatari.md).

Every conversion starts from a fresh reference run: the game (its disks and the TOS, the player's own or EmuTOS) runs on Hatari,
its 68000 on Hatari's cycle-exact interpreter, every instruction counted. The game executable (the disks, the TOS, the machine and
the host kit) is then replayed headless, copied alone, and its trace (picture, sound, RAM, CPU registers of every frame) must equal
the reference's; so must the compressed copy that is delivered, and a quick state saved by it is loaded by a fresh process.
Guarded native steps for the code the game runs come in the next stage: until then the report counts every instruction as
interpreted. Nothing is claimed beyond those bounded routes: the hardware fidelity is Hatari's, unmeasured here, and the routes
are scripts, not play.

The private memory of this machine lives under `<library>/atarist/<game>/` (the input's SHA-256): `compilation.json` and the
observations of the last conversion.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import time

from . import __version__, timings
from .conversion_common import resolve_scan_level, spawn
from .conversion_gates import require_same_file
from .core import ConversionError, executable_name, run, toolchain
from .delivery_evidence import FrameRow, deliver_packed, liveness_summary, replay_packed, report_fields, require_moving_picture, same_trace
from .library import atomic_json, entry_lock, file_sha256, library_root
from .paths import ASSETS, ROOT, boxart_cache_directory
from .platforms import build_executable, build_jobs, cmake_target_args, sdl_install, target_id
from .report_schema import write_report
from .systems import get_profile
from .toolchain import describe as toolchain_description, suffix as toolchain_suffix

PLAYER = 'RetroRecomp-AtariST'
# The notices every exported ST game carries (resource 203, as on the other machines): Retro-Recomp's licence, Hatari (GPL-2.0)
# with the GPL text and where its corresponding source is, the libretro API header, SDL and the host kit's parts.
NOTICE_FILES = ('LICENSE', 'licenses/hatari.md', 'licenses/SDL2.md', 'licenses/xbr.md', 'licenses/Noto.md', 'licenses/UPX.md',
                'licenses/llvm-mingw.md')
NOTICE_RESOURCE = 203
TOS_RESOURCE = 298
MARKER_RESOURCE = 299
FIRST_DISK_RESOURCE = 300
OBSERVATIONS = 'converter-observations.txt'
LIVENESS_FIELDS = {'frames': 'frames', 'distinct_pictures': 'distinct_pictures', 'distinct_audio_blocks': 'distinct_sound_blocks',
                   'distinct_ram_states': 'distinct_ram_states', 'distinct_program_counters': 'distinct_program_counters'}
MACHINE = 'st'
MEMORY_KB = 1024
# libretro key codes the routes press (Hatari maps them to ST scan codes).
KEY_SPACE, KEY_RETURN, KEY_F1 = 32, 13, 282


def sdk_stamp(part: str | None = None) -> str:
    """The identity of the ST's build inputs (its stamped files and the Hatari adaptation); part='game' leaves the shell out."""
    from .compilation_inputs import engine_stamp, role_stamps
    from .atarist_hatari import adaptation_digest
    value = hashlib.sha256(b'atarist-sdk-v1\0')
    value.update((role_stamps('atarist')['game'] if part == 'game' else engine_stamp('atarist')).encode())
    value.update(b'\0' + adaptation_digest().encode())
    return value.hexdigest()


# ------------------------------------------------------------------------------------------------------------- the routes
def main_route(frames: int) -> list[tuple[int, int, str, int, int]]:
    """A bounded script for every game: it waits for the disk to load, then presses the joystick's fire, moves it, clicks and
    moves the mouse and taps Space, Return and F1, so that title screens, menus and protection prompts are left behind or answered
    with what a player would press first. Frames are the machine's own."""
    events = []
    for start in range(250, frames - 20, 150):
        events.append((start, start + 8, 'joy', 4, 1))
    for start, length, bit in ((900, 60, 3), (1100, 60, 2), (1300, 30, 0), (1400, 30, 1), (1600, 120, 3), (1900, 90, 2),
                               (2200, 60, 0), (2400, 120, 3), (2700, 60, 2)):
        if start + length < frames:
            events.append((start, start + length, 'joy', bit, 1))
    for start in (400, 1300, 2200):
        if start + 6 < frames:
            events.append((start, start + 6, 'mouse', 2, 1))
    if 1040 < frames:
        events.append((1000, 1040, 'mouse', 0, 3))
        events.append((1000, 1040, 'mouse', 1, 2))
    for start, key in ((600, KEY_SPACE), (900, KEY_RETURN), (1700, KEY_SPACE), (2000, KEY_F1)):
        if start + 6 < frames:
            events.append((start, start + 6, 'key', key, 1))
    return sorted(events)


def explore_route(frames: int) -> list[tuple[int, int, str, int, int]]:
    """A second, denser script (standard level and above): long holds of each direction with the fire held at times."""
    events = []
    t, bits, n = 200, (3, 2, 0, 1), 0
    while t + 100 < frames:
        events.append((t, t + 90, 'joy', bits[n % 4], 1))
        if n % 2:
            events.append((t + 20, t + 50, 'joy', 4, 1))
        t += 110
        n += 1
    for start in range(400, frames - 10, 600):
        events.append((start, start + 4, 'key', KEY_SPACE, 1))
    return sorted(events)


def write_events(path: Path, events) -> Path:
    if len(events) > 4096:
        raise ConversionError('Too many Atari ST route events.')
    path.write_text(''.join(f'{b} {e} {kind} {code} {value}\n' for b, e, kind, code, value in events), encoding='ascii')
    return path


# --------------------------------------------------------------------------------------------------------- building
def machine_core(toolchain_root: Path, emit) -> tuple[Path, Path]:
    """The adapted Hatari tree and its own build (the static libretro core), done once per adaptation and toolchain: our own
    modules do not enter it, so a change of the converter that leaves Hatari's adaptation alone reuses the build."""
    from . import atarist_hatari
    base = toolchain_root / ('hatari-' + atarist_hatari.adaptation_digest()[:12])
    base.mkdir(parents=True, exist_ok=True)
    with entry_lock(base / 'hatari-lock', timeout=3600):
        tree = atarist_hatari.adapt(atarist_hatari.source(emit), base / 'hatari')
        build = base / 'hatari' / 'build'
        ready = build / 'rr-ready.json'
        digest = atarist_hatari.adaptation_digest()
        try:
            if json.loads(ready.read_text(encoding='utf-8')).get('adaptation') == digest:
                return tree, build
        except (OSError, ValueError):
            pass
        emit('Atari ST: building the Hatari machine (cycle-exact 68000, libretro core).')
        build.mkdir(parents=True, exist_ok=True)
        cmake, generator = toolchain()
        libretro = ASSETS / 'native/atarist_machine/libretro'
        with timings.phase('compile'):
            run([cmake, '-S', tree, '-B', build, '-G', generator, *cmake_target_args(),
                 *atarist_hatari.configure_arguments(libretro)], log=build / 'build.log')
            run([cmake, '--build', build, '--parallel', build_jobs(), '--target', 'retro-hatari'], log=build / 'build.log', timeout=3600)
        atomic_json(ready, {'adaptation': digest})
        return tree, build


def cmake_build(build: Path, tree: Path, hatari_build: Path, *, payload: Path | None = None, stamp: str = '') -> Path:
    cmake, generator = toolchain()
    run([cmake, '-S', ASSETS / 'native/atarist_machine', '-B', build, '-G', generator, *cmake_target_args(),
         f'-DRR_HATARI_TREE={tree.as_posix()}', f'-DRR_HATARI_BUILD={hatari_build.as_posix()}',
         f'-DCMAKE_PREFIX_PATH={sdl_install().as_posix()}', '-DCMAKE_BUILD_TYPE=Release',
         f'-DRR_ST_PAYLOAD_DIR={payload.as_posix() if payload else ""}', f'-DRR_ST_STATE_INPUT={stamp}',
         f'-DRR_RECOMP_VERSION={__version__}'], log=build / 'build.log')
    run([cmake, '--build', build, '--parallel', build_jobs(), '--target', 'atarist_player'], log=build / 'build.log', timeout=1800)
    return build_executable(build, PLAYER)


def reference_build(base: Path, tree: Path, hatari_build: Path, stamp: str, emit) -> Path:
    """The generic reference player (no game embedded, every instruction on Hatari's interpreter), built once per SDK stamp."""
    folder = base / 'reference'
    with entry_lock(base / 'reference-lock', timeout=3600):
        ready = folder / 'ready.json'
        try:
            done = json.loads(ready.read_text(encoding='utf-8'))
            if done.get('sdk') == stamp and Path(done['player']).is_file():
                return Path(done['player'])
        except (OSError, ValueError, KeyError):
            pass
        emit('Atari ST: building the reference player.')
        folder.mkdir(parents=True, exist_ok=True)
        with timings.phase('compile'):
            player = cmake_build(folder / 'build', tree, hatari_build, stamp=stamp)
        atomic_json(ready, {'sdk': stamp, 'player': str(player)})
        return player


def extract_game(source, tos_data: bytes, folder: Path) -> list[Path]:
    """The disks (in order) and the TOS, written into this conversion's private work folder for the reference player."""
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    (folder / 'tos.img').write_bytes(tos_data)
    disks = []
    for n, (disk, data) in enumerate(zip(source.disks, source.disk_data())):
        path = folder / f'disk{n + 1}.{disk.format}'
        path.write_bytes(data)
        disks.append(path)
    return disks


def payload(project: Path, source, disks: list[Path], tos: Path, title: str, mouse_game: bool) -> dict:
    """The resources of the exported game: its disks and its TOS (as embedded files), the notices and the Windows metadata."""
    from .metadata import write_game_metadata
    from .resources import embed_resources
    project.mkdir(parents=True, exist_ok=True)
    resources = {}
    marker = b'[Retro-Recomp]\0' + source.sha256.encode() + b'\0'
    (project / 'export-marker.bin').write_bytes(marker)
    resources[MARKER_RESOURCE] = project / 'export-marker.bin'
    notices = project / 'notices.txt'
    notices.write_text('\n\n'.join((ASSETS / name).read_text(encoding='utf-8') for name in NOTICE_FILES), encoding='utf-8')
    resources[NOTICE_RESOURCE] = notices
    shutil.copyfile(tos, project / 'tos.bin')
    resources[TOS_RESOURCE] = project / 'tos.bin'
    rows = []
    for n, disk in enumerate(disks):
        identifier = FIRST_DISK_RESOURCE + 1 + n
        target = project / f'blob-{identifier:03d}.bin'
        shutil.copyfile(disk, target)
        resources[identifier] = target
        rows.append('{' + json.dumps(disk.name, ensure_ascii=True) + f',{identifier}' + '},')
    header = ['#ifndef RR_ST_PAYLOAD_H', '#define RR_ST_PAYLOAD_H',
              '#define RR_ST_GAME_TITLE ' + json.dumps(title, ensure_ascii=True),
              '#define RR_ST_SOURCE_IDENTITY ' + json.dumps(source.sha256),
              f'#define RR_ST_MOUSE_GAME {int(mouse_game)}', f'#define RR_ST_TOS_RESOURCE {TOS_RESOURCE}',
              '#define RR_ST_MACHINE ' + json.dumps(MACHINE), f'#define RR_ST_MEMORY_KB {MEMORY_KB}',
              'typedef struct {const char *name;unsigned resource;} RrStPayloadDisk;',
              'static const RrStPayloadDisk rr_st_disks[]={', *rows, '{0,0}};',
              f'#define RR_ST_DISK_COUNT {len(rows)}u',
              'static const volatile unsigned char rr_st_export_marker[]={' + ','.join(str(c) for c in marker) + '};', '#endif']
    (project / 'atarist_payload.h').write_text('\n'.join(header) + '\n', encoding='utf-8')
    if not (project / 'game.ico').is_file():
        shutil.copy2(ASSETS / 'assets/Retro-Recomp.ico', project / 'game.ico')
    metadata = write_game_metadata(project, title, executable_name(title), light_phaser=False, icon=True, standard='native',
                                   system_id='atarist')
    (project / 'game_metadata.rc').write_bytes((project / 'game_resources.rc').read_bytes())
    if os.name == 'nt':
        lines = ['#pragma code_page(65001)'] + [f'{identifier} RCDATA ' + json.dumps(path.as_posix(), ensure_ascii=False)
                                                for identifier, path in resources.items()]
        (project / 'game_resources.rc').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    else:
        embed_resources(project, resources)
    return metadata


# ---------------------------------------------------------------------------------------------------------- replays
def replay(binary: Path, folder: Path, frames: int, events: Path, *, disks: list[Path] | None = None, tos: Path | None = None,
           observe: bool = False, extra=()) -> dict:
    folder.mkdir(parents=True, exist_ok=True)
    args = [str(binary), '--headless', '--frames', str(frames), '--report', str(folder / 'result.json'),
            '--trace', str(folder / 'trace.tsv'), '--input-events', str(events), '--capture', str(folder / 'frame.ppm')]
    if tos is not None:
        args += ['--tos', str(tos), '--machine', MACHINE, '--memory', str(MEMORY_KB)]
        for disk in disks or ():
            args += ['--disk', str(disk)]
    if observe:
        args += ['--observations', str(folder / 'observations.txt')]
    args += [str(value) for value in extra]
    with (folder / 'stdout.log').open('wb') as out, (folder / 'stderr.log').open('wb') as err:
        result = spawn(args, cwd=folder, timeout=max(600, frames // 4), stdout=out, stderr=err)
    if result.returncode not in (0, 2):
        raise ConversionError('Atari ST replay failed: ' + (folder / 'stderr.log').read_text(encoding='utf-8', errors='replace')[-2000:])
    report = json.loads((folder / 'result.json').read_text(encoding='utf-8'))
    if report.get('stopped'):
        raise ConversionError(f'Atari ST: the machine stopped at frame {report.get("frames")}: {report.get("error")}')
    if report.get('frames') != frames:
        raise ConversionError('Atari ST validation returned an incomplete run.')
    return report


def trace_rows(path: Path):
    with path.open('r', encoding='ascii', newline='') as stream:
        next(stream)
        for line in stream:
            values = line.rstrip('\r\n').split('\t')
            yield FrameRow(int(values[0]), values[1], sound=values[2], ram=values[3], pc=values[4])


def trace_digests(path: Path) -> dict:
    """One digest per kind of evidence of a route's trace (CPU registers, RAM, picture, sound), over its frames in order."""
    rows = [line.split('\t') for line in Path(path).read_text(encoding='ascii').splitlines()]
    header, body = rows[0], rows[1:]
    registers = [i for i, name in enumerate(header) if name in ('PC', 'SR') or (name[:1] in ('D', 'A') and name[1:].isdigit())]
    columns = {'cpu_hash': registers, 'ram_hash': [header.index('ram')], 'image_hash': [header.index('video')], 'pcm_hash': [header.index('pcm')]}
    return {name: hashlib.sha256('\n'.join(' '.join(row[i] for i in indexes) for row in body).encode('ascii')).hexdigest()
            for name, indexes in columns.items()}


# What a resumed process is not compared on (as on the Amiga): Hatari's snapshot leaves out the state of its sound output (the YM
# mixing and resampling restart on load), so the samples of the first frames after a load differ while the machine (CPU, RAM,
# picture) continues the same timeline. Reported as such (`game_states.validation`).
CONTINUATION_IGNORED = ('pcm',)


def continuation(timeline: Path, resumed: Path) -> dict:
    """How a fresh process that loaded the state continues the timeline: the rows of the same frames (frame numbers included, they
    are the machine's) compared column by column; it continues when every column but CONTINUATION_IGNORED is equal."""
    def rows(path):
        lines = Path(path).read_text(encoding='ascii').splitlines()
        return lines[0].split('\t'), [line.split('\t') for line in lines[1:]]
    header, later = rows(resumed)
    _, earlier_rows = rows(timeline)
    earlier = {row[0]: row for row in earlier_rows}
    keep = [i for i, name in enumerate(header) if name not in CONTINUATION_IGNORED]
    exact = sum(1 for row in later if earlier.get(row[0]) == row)
    kept = sum(1 for row in later if row[0] in earlier and all(row[i] == earlier[row[0]][i] for i in keep))
    differing = sorted({header[i] for row in later if row[0] in earlier for i in range(len(header)) if row[i] != earlier[row[0]][i]})
    return {'frames': len(later), 'equal_frames': exact, 'matches': bool(later) and kept == len(later), 'differing_columns': differing}


def game_entry(source, tos_key: str) -> Path:
    """The private memory of a game, one per TOS (the player's image, its SHA-256's first 16 digits, or EmuTOS)."""
    return library_root('atarist') / source.game_key / f'tos-{tos_key}'


# -------------------------------------------------------------------------------------------------------- conversion
def convert(path, *, title=None, output=None, cover=None, use_cover=True, online_cover=True, passes=1, frames=3000, scan_level=None,
            emit=print, qualification_events=None, **unused):
    from .atarist import converter_available, read_input
    from . import atarist_tos
    if not converter_available():
        raise ConversionError('The Atari ST converter files are missing from this installation.')
    if unused.get('standard_override') not in (None, 'native', 'auto'):
        raise ConversionError('Atari ST timing follows the machine and its TOS (PAL, or NTSC with a US TOS); overrides do not apply.')
    started = time.perf_counter()
    level = resolve_scan_level(scan_level)
    source = read_input(path)
    try:
        tos = atarist_tos.require(unused.get('atarist_tos'))
    except ValueError as exc:
        raise ConversionError(str(exc)) from None
    if tos is None:
        raise ConversionError('Atari ST: choose your own TOS 1.00, 1.02 or 1.04 image in Options (EmuTOS, the default, is not '
                              'available in this build yet).')
    title = title or source.title
    if any(ord(c) < 32 for c in title) or len(title) > 160:
        raise ConversionError('Invalid Atari ST game title.')
    stamp = sdk_stamp()
    base = ROOT / '.build/atarist' / (('win' + toolchain_suffix()) if os.name == 'nt' else 'linux') / stamp[:12]
    base.mkdir(parents=True, exist_ok=True)
    if not output:
        from .paths import games_directory
        output = games_directory(system_id='atarist') / 'datas/reports' / source.sha256
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    emit(f'Atari ST: reading {len(source.disks)} floppy image(s); {tos.label()}.')
    from .console16 import dependencies16
    dependencies16('md', emit)   # SDL (and the shared 68000 decoder the native steps of the next stage use)
    tree, hatari_build = machine_core(base.parent, emit)
    reference_player = reference_build(base, tree, hatari_build, stamp, emit)
    work = base / source.sha256[:16] / tos.sha256[:16]
    with entry_lock(work / 'lock', timeout=3600):
        checks = Path(tempfile.mkdtemp(prefix='qa-', dir=work))
        media = work / 'media'
        disks = extract_game(source, tos.data(), media)
        count = max(1000, min(int(frames or 3000), 36000))
        routes = [('main', count, main_route(count) if qualification_events is None else list(qualification_events))]
        if level != 'quick':
            routes.append(('explore', count, explore_route(count)))
        scripts = {name: write_events(work / f'inputs-{name}.txt', events) for name, _, events in routes}
        emit(f'Atari ST: fresh reference runs ({len(routes)} route(s) of {count} frames, interpreted 68000).')
        expected = {}
        with timings.phase('reference_runs'):
            for name, frames_, _ in routes:
                expected[name] = replay(reference_player, checks / f'reference-{name}', frames_, scripts[name], disks=disks,
                                        tos=media / 'tos.img', observe=True)
        mouse_game = False
        from .artwork import prepare_icon
        payload_dir = work / 'payload'
        payload_dir.mkdir(parents=True, exist_ok=True)
        artwork = prepare_icon(payload_dir, source.path, title, payload_dir, explicit=Path(cover) if cover else None, online=online_cover,
                               enabled=use_cover, system_id='atarist', cache_directory=boxart_cache_directory('atarist'), emit=emit)
        metadata = payload(payload_dir, source, disks, media / 'tos.img', title, mouse_game)
        emit('Atari ST: compiling the game.')
        with timings.phase('compile'):
            candidate = cmake_build(work / 'build', tree, hatari_build, payload=payload_dir, stamp=stamp)
        results = {}
        with timings.phase('native_runs'):
            for name, frames_, _ in routes:
                folder = checks / f'game-{name}'
                folder.mkdir(parents=True, exist_ok=True)
                exported = folder / candidate.name
                shutil.copy2(candidate, exported)
                results[name] = replay(exported, folder, frames_, scripts[name])
                require_same_file(folder / 'trace.tsv', checks / f'reference-{name}' / 'trace.tsv',
                                  lambda: ConversionError(f'Atari ST {name}: the game and the fresh reference diverged; existing export preserved.'))
        if not results['main']['nonblack_frames']:
            raise ConversionError('Atari ST validation did not produce a usable picture.')
        # The delivered file: the compressed copy is replayed on every route against the same fresh reference; the main route
        # saves a quick state on the way (a capture leaves the machine as it was: the trace must still equal the reference).
        packed = work / ('packed-game.exe' if os.name == 'nt' else 'packed-game')
        delivered = deliver_packed(candidate, packed, 'Atari ST', emit)
        state_frame = count - 600
        packed_runs = [(name, checks / 'packed' / name, checks / f'reference-{name}', frames_,
                        ['--state-save-at', str(state_frame), '--state-slot', str(checks / 'packed' / name / 'quick.rrstate')] if name == 'main' else [])
                       for name, frames_, _ in routes]

        def replay_copy(run_):
            name, folder, _, frames_, extra = run_
            shutil.rmtree(folder, ignore_errors=True)
            folder.mkdir(parents=True)
            target = folder / candidate.name
            shutil.copy2(packed, target)
            if os.name != 'nt':
                target.chmod(0o755)
            return replay(target, folder, frames_, scripts[name], extra=extra)
        with timings.phase('packed_replays'):
            packed_results = replay_packed(delivered, packed_runs, replay_copy,
                                           same=lambda run_, result: same_trace(run_[1] / 'trace.tsv', run_[2] / 'trace.tsv'),
                                           mismatch=lambda run_: ConversionError(f'Atari ST {run_[0]}: the compressed executable differs from the fresh reference; existing export preserved.'))
        liveness = [dict(route=name, **report_fields(liveness_summary(trace_rows(folder / 'trace.tsv')), LIVENESS_FIELDS),
                         nonblack_frames=result['nonblack_frames'], audible_frames=result['audible_frames'])
                    for (name, folder, _, _, _), result in zip(packed_runs, packed_results)]
        require_moving_picture(liveness[0], lambda: ConversionError('Atari ST main route: the picture never changed.'))
        # The quick state, loaded by a genuinely fresh process of the delivered file: how it continues is measured and reported
        # (a state saved during a floppy transfer is not yet known to continue exactly: reported, not refused, while experimental).
        restart = checks / 'restart'
        restart.mkdir()
        fresh = restart / candidate.name
        shutil.copy2(packed, fresh)
        with timings.phase('state_checks'):
            replay(fresh, restart, 400, scripts['main'], extra=['--state-load-start', '--state-slot', checks / 'packed' / 'main' / 'quick.rrstate'])
        resumed = continuation(checks / 'packed' / 'main' / 'trace.tsv', restart / 'trace.tsv')
        rows = []
        for (name, frames_, events), result in zip(routes, packed_results):
            interpreted = expected[name]['interpreted']
            folder = checks / 'packed' / name
            rows.append({'route': name, 'frames': frames_, 'native_entries': 0, 'interpreted_opcodes': interpreted,
                         'interpreter_percent': 100.0, 'reference_match': True, 'packed_reference_match': True,
                         'observed_instructions': expected[name]['observed'],
                         'trace_sha256': file_sha256(folder / 'trace.tsv'), **trace_digests(folder / 'trace.tsv'),
                         'steps': len(events), 'script_sha256': file_sha256(scripts[name]),
                         **({'state_saved_at': state_frame, 'state_restart_match': resumed['matches']} if name == 'main' else {})})
        sound_routes = [name for (name, _, _), result in zip(routes, packed_results) if result['audible_frames']]
        report = {
            'tool': 'Retro-Recomp', 'version': __version__, 'created_utc': datetime.now(timezone.utc).isoformat(),
            'system': {'id': 'atarist', 'name': 'Atari ST'}, 'status': get_profile('atarist').status, 'private_development_only': False,
            'target': target_id(), 'rom': source.metadata(), 'source_identity': source.sha256, 'qualification_directory': str(checks),
            'source_rom': str(source.path), 'executable': executable_name(title), 'build_executable': str(candidate),
            'toolchain': toolchain_description(),
            'floppy': {'disks': [d.name for d in source.disks], 'formats': sorted({d.format for d in source.disks}),
                       'reader': "Hatari's built-in readers (IPF: src/floppies/ipf_dsk.c, BSD-3-Clause; no capsimg)",
                       'drive_a_at_start': 1, 'disk_changes': 'Ctrl+Alt+Page Up/Down in the game; none in the routes'},
            'machine': {'model': 'Atari ST (STF), 68000 at 8 MHz, 1 MiB', 'reference': 'Hatari (GPL-2.0) at its pinned revision, adapted at '
                        'build time, cycle-exact 68000, real floppy timing, borders shown',
                        'tos': {'used': tos.label(), 'version': f'{tos.version >> 8}.{tos.version & 0xff:02x}', 'country': tos.country,
                                'pal': tos.pal, 'sha256': tos.sha256, 'player_supplied': True, 'stored_in_library': False,
                                'shared': False, 'embedded_in_export': True,
                                'native': 'none: its instructions run on the interpreter like the rest, counted per route'}},
            'embedded_rom': True, 'static_sdl': True, 'no_external_firmware_required_after_export': True,
            'native_validation': {'passed': True, **delivered.validation_fields(), 'sound_heard': bool(sound_routes), 'sound_routes': sound_routes,
                                  'scope': 'fresh same-machine reference (interpreted 68000): picture, sound, RAM and CPU registers of every frame, '
                                           'on bounded joystick, mouse and keyboard scripts'},
            'native_coverage': 'none yet: every 68000 instruction runs on Hatari\'s interpreter and is counted (guarded native steps '
                               'come in the next stage)',
            'final_checks': rows, **delivered.report_fields(), 'liveness': liveness, 'scan_level': level,
            'game_states': {'supported': True, 'save_key': 'F8', 'load_key': 'F9', 'fresh_process_verified': resumed['matches'], 'slots': 1,
                            'compatibility': 'the exact game, TOS and build that wrote the state; refused between builds',
                            'schema': 'RRATARIST-STATE-1', 'machine': 'atarist', 'rom_identity': source.sha256,
                            'validation': {'process': 'fresh', 'compressed_copy': True, 'saved_at_frame': state_frame,
                                           'continuation_frames': resumed['frames'], 'continuation_matches': resumed['matches'],
                                           'equal_frames': resumed['equal_frames'], 'differing_columns': resumed['differing_columns'],
                                           'saving_leaves_the_timeline': True,
                                           'compared': 'CPU registers, RAM and picture of every frame; not the sound samples (Hatari does '
                                                       'not save the state of its sound output)'}},
            'ordinary_saves': {'supported': False, 'scope': 'saves a game writes to its floppy stay in memory for the session only (not yet kept)'},
            'input_players': 2, 'peripheral': {'joystick_ports': 2, 'mouse': 'port 0, captured on a click',
                                               'keyboard': 'guest keyboard (Ctrl+Alt+K for full typing)'},
            'video_model': {'standard': 'PAL' if tos.pal else 'NTSC', 'frameskip': False, 'fps': packed_results[0]['fps']},
            'runtime_data': {'directory': 'datas', 'shared_config': 'datas/Retro-Recomp.ini', 'game_directory': 'datas/games/atarist-' + source.sha256},
            'artwork': artwork, 'windows_metadata': metadata,
            'hardware_accuracy_validated': False, 'full_game_validated': False, 'latency_ms': None,
            'licence': {'executable': 'GPL-2.0 (linked with Hatari; Retro-Recomp\'s own files keep their MIT notice)',
                        'notices': list(NOTICE_FILES)},
            'qualification_scope': {'controls': 'bounded joystick, mouse and keyboard scripts', 'media': 'floppy images (IPF, STX, MSA, ST)',
                                    'universal_zero_fallback_claim': False},
            'conversion_wall_seconds': round(time.perf_counter() - started, 3)}
        write_report(output / 'conversion-report.json', report)
        # The private memory: the observations of this conversion's reference runs, for the native steps of the next stage.
        memory = game_entry(source, tos.sha256[:16])
        memory.mkdir(parents=True, exist_ok=True)
        with entry_lock(memory, timeout=1800):
            samples = set()
            for name, _, _ in routes:
                samples |= set((checks / f'reference-{name}' / 'observations.txt').read_text(encoding='ascii').splitlines())
            (memory / (OBSERVATIONS + '.tmp')).write_text(''.join(line + '\n' for line in sorted(samples)), encoding='ascii')
            os.replace(memory / (OBSERVATIONS + '.tmp'), memory / OBSERVATIONS)
            atomic_json(memory / 'compilation.json', {'schema': 1, 'title': title, 'system': 'atarist', 'game': source.game_key,
                                                      'rom_sha256': source.sha256, 'tos_sha256': tos.sha256, 'observed': len(samples),
                                                      'sdk': stamp, 'private_development_only': True, 'fresh_reference_passed': True})
        emit('Atari ST: validated standalone game ready.')
        return candidate
