"""Nintendo 64 conversion (experimental): a cartridge image becomes a standalone game (MIT; the executable it builds is linked with
Mupen64Plus-Next and is GPL-3.0 as a whole: licenses/mupen64plus-next.md).

Every conversion starts from a fresh reference run: the game runs on Mupen64Plus with the ParaLLEl RDP (Vulkan, deterministic
command recording) and the ParaLLEl RSP, its VR4300 on the core's pure interpreter, every instruction counted, and the code it
runs is observed (native/n64_machine/n64_cpu.c). The observation becomes guarded native blocks (retrorecomp/n64_native.py): C
that calls the core's own instruction functions with constant opcodes, keyed by address and code identity. The game executable
(the cartridge, the machine, the blocks and the host kit) is replayed headless, copied alone, and its trace (picture, sound, RDRAM
and CPU registers of every frame) must equal the reference's; so must the compressed copy that is delivered, and a quick state
saved by it is loaded by a fresh process. A game with no block runs the core's cached interpreter (Fable review, condition 4),
checked against a fresh reference of that interpreter. Nothing is claimed beyond those bounded routes: the hardware fidelity is
Mupen64Plus's and ParaLLEl's, unmeasured here, and the routes are scripts, not play.

The private memory of this machine lives under `<library>/n64/<game>/` (the SHA-256 of the big-endian image): `compilation.json`
and the observations of the conversions so far.
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
from .platforms import build_executable, build_jobs, cmake_target_args, require_backend, sdl_install, target_id
from .report_schema import write_report
from .systems import get_profile
from .toolchain import describe as toolchain_description, suffix as toolchain_suffix

PLAYER = 'RetroRecomp-N64'
# The notices every exported N64 game carries (resource 203, as on the other machines): Retro-Recomp's licence, Mupen64Plus-Next
# and its parts (GPL-2.0-or-later core, MIT ParaLLEl, LGPL-3.0-or-later Lightning, the GPL-3.0 text and where the corresponding
# source is), SDL and the host kit's parts.
NOTICE_FILES = ('LICENSE', 'licenses/mupen64plus-next.md', 'licenses/SDL2.md', 'licenses/xbr.md', 'licenses/Noto.md', 'licenses/UPX.md',
                'licenses/llvm-mingw.md')
NOTICE_RESOURCE = 203
ROM_RESOURCE = 298
MARKER_RESOURCE = 299
OBSERVATIONS = 'converter-observations.txt'
LIVENESS_FIELDS = {'frames': 'frames', 'distinct_pictures': 'distinct_pictures', 'distinct_audio_blocks': 'distinct_sound_blocks',
                   'distinct_ram_states': 'distinct_ram_states', 'distinct_program_counters': 'distinct_program_counters'}
# Bits of the session's pad (n64_session.h).
PAD_A, PAD_B, PAD_L, PAD_START, PAD_UP, PAD_DOWN, PAD_LEFT, PAD_RIGHT = 0, 1, 2, 3, 4, 5, 6, 7
PAD_CDOWN, PAD_CUP, PAD_CLEFT, PAD_CRIGHT, PAD_Z, PAD_R = 8, 9, 10, 11, 12, 13
STICK_X, STICK_Y = 0, 1


def sdk_stamp(part: str | None = None) -> str:
    """The identity of the N64's build inputs (its stamped files and the core's adaptation); part='game' leaves the shell out."""
    from .compilation_inputs import engine_stamp, role_stamps
    from .n64_core import adaptation_digest
    from .n64_native import FORMAT
    value = hashlib.sha256(b'n64-sdk-v1\0')
    value.update((role_stamps('n64')['game'] if part == 'game' else engine_stamp('n64')).encode())
    value.update(b'\0' + adaptation_digest().encode() + b'\0' + str(FORMAT).encode())
    return value.hexdigest()


# ------------------------------------------------------------------------------------------------------------- the routes
def main_route(frames: int) -> list[tuple[int, int, str, int, int]]:
    """A bounded script for every game: after the boot logos it presses Start and A at a steady pace (title screens, file
    selections and intros are left behind with what a player presses first), then moves the stick in each direction, with B, Z and
    the C buttons at times. Presses last 8 frames (a game that reads its pad at 20 Hz still sees each). Frames are the machine's."""
    events = []
    for start in range(300, min(frames - 20, 1500), 120):
        events.append((start, start + 8, 'pad', PAD_START if (start // 120) % 2 else PAD_A, 0))
    for start, length, axis, value in ((1500, 120, STICK_Y, -30000), (1700, 90, STICK_X, 30000), (1850, 90, STICK_X, -30000),
                                       (2000, 150, STICK_Y, -30000), (2250, 60, STICK_Y, 30000), (2400, 120, STICK_X, 30000),
                                       (2600, 200, STICK_Y, -30000), (2900, 100, STICK_X, -30000), (3100, 150, STICK_Y, -30000)):
        if start + length < frames:
            events.append((start, start + length, 'stick', axis, value))
    for start, bit in ((1550, PAD_A), (1760, PAD_B), (2050, PAD_A), (2300, PAD_Z), (2450, PAD_CUP), (2500, PAD_CUP),
                       (2700, PAD_A), (2950, PAD_B), (3200, PAD_A), (3300, PAD_START), (3400, PAD_START)):
        if start + 8 < frames:
            events.append((start, start + 8, 'pad', bit, 0))
    return sorted(events)


def explore_route(frames: int) -> list[tuple[int, int, str, int, int]]:
    """A second, denser script (standard level and above): Start and A through the menus, then long pushes of the stick in turn
    with A and B pressed during them."""
    events = []
    for start in range(300, min(frames - 20, 1200), 90):
        events.append((start, start + 8, 'pad', PAD_A if (start // 90) % 3 else PAD_START, 0))
    t, n = 1200, 0
    directions = ((STICK_Y, -30000), (STICK_X, 30000), (STICK_Y, 30000), (STICK_X, -30000))
    while t + 130 < frames:
        axis, value = directions[n % 4]
        events.append((t, t + 120, 'stick', axis, value))
        events.append((t + 30, t + 38, 'pad', PAD_A if n % 2 else PAD_B, 0))
        t += 140
        n += 1
    return sorted(events)


def _presses(start: int, stop: int, every: int, bit: int, length: int = 6) -> list:
    return [(t, t + length, 'pad', bit, 0) for t in range(start, stop, every)]


def _sm64_pal() -> tuple[int, list]:
    """Super Mario 64 (PAL, NSMP): Start at the title, Return on the sound selection the PAL game opens first, file A, the
    letter and Lakitu's words, then Mario runs, turns, jumps and punches in the castle grounds (play from about frame 3,900)."""
    events = [(1050, 1058, 'pad', PAD_START, 0),
              (1200, 1241, 'stick', STICK_X, 20000), (1200, 1241, 'stick', STICK_Y, 20000), (1260, 1268, 'pad', PAD_A, 0),
              (1340, 1384, 'stick', STICK_X, -20000), (1340, 1384, 'stick', STICK_Y, -20000), (1400, 1408, 'pad', PAD_A, 0),
              *_presses(3200, 3801, 50, PAD_A),
              (3900, 4100, 'stick', STICK_Y, -30000), (4100, 4400, 'stick', STICK_X, 30000), (4200, 4206, 'pad', PAD_A, 0),
              (4300, 4306, 'pad', PAD_A, 0), (4400, 4700, 'stick', STICK_Y, 30000), (4500, 4506, 'pad', PAD_B, 0),
              (4700, 5000, 'stick', STICK_X, -30000), (4800, 4806, 'pad', PAD_A, 0), (4900, 4906, 'pad', PAD_A, 0),
              (5000, 5400, 'stick', STICK_Y, -30000), (5150, 5156, 'pad', PAD_B, 0), (5400, 5800, 'stick', STICK_X, 30000),
              (5500, 5506, 'pad', PAD_A, 0), (5600, 5606, 'pad', PAD_Z, 0)]
    return 6000, sorted(events)


def _oot_pal() -> tuple[int, list]:
    """The Legend of Zelda: Ocarina of Time (PAL, NZLP): file 1 created with the name "A" (the cursor goes to END along the right
    column), opened, the intro's words advanced with A, then Link walks around his house (play from about frame 15,600)."""
    events = [(600, 608, 'pad', PAD_START, 0), (700, 708, 'pad', PAD_START, 0), (900, 908, 'pad', PAD_A, 0),
              (1300, 1308, 'pad', PAD_A, 0), (1400, 1408, 'pad', PAD_A, 0)]
    t = 1430
    for _ in range(12):
        events.append((t, t + 8, 'stick', STICK_X, 30000))
        t += 16
    for _ in range(5):
        events.append((t, t + 8, 'stick', STICK_Y, 30000))
        t += 20
    events += [(t + 10 + k, t + 18 + k, 'pad', PAD_A, 0) for k in (0, 100, 200, 300)]
    events += _presses(2200, 15601, 40, PAD_A)
    events += [(15700, 16000, 'stick', STICK_Y, 30000), (16000, 16200, 'stick', STICK_X, 30000), (16200, 16500, 'stick', STICK_Y, -30000)]
    return 16800, sorted(events)


# Routes that reach play, per game, by its game code (numbers about the cartridge, never its bytes), tuned on the dumps named in
# docs/NINTENDO_64.md. Played at the Extended and Thorough levels (route depth, gate G9). Mario Kart 64's main route already races.
PLAY_ROUTES = {'NSMP': _sm64_pal, 'NZLP': _oot_pal}


def play_route(game_code: str) -> tuple[int, list] | None:
    maker = PLAY_ROUTES.get(game_code)
    return maker() if maker else None


def write_events(path: Path, events) -> Path:
    if len(events) > 8192:
        raise ConversionError('Too many Nintendo 64 route events.')
    path.write_text(''.join(f'{b} {e} {kind} {code} {value}\n' for b, e, kind, code, value in events), encoding='ascii')
    return path


# --------------------------------------------------------------------------------------------------------- building
def sdl_ready(emit) -> None:
    from .platforms import sdl_library
    if not (sdl_install() / sdl_library()).is_file():
        from .core import dependencies
        dependencies(emit)


def configure(build: Path, tree: Path, *, core: Path | None = None, generated: Path | None = None, payload: Path | None = None,
              stamp: str = '') -> list:
    cmake, generator = toolchain()
    return [cmake, '-S', ASSETS / 'native/n64_machine', '-B', build, '-G', generator, *cmake_target_args(),
            f'-DRR_N64_TREE={tree.as_posix()}', f'-DRR_N64_PREBUILT_CORE={core.as_posix() if core else ""}',
            f'-DCMAKE_PREFIX_PATH={sdl_install().as_posix()}', '-DCMAKE_BUILD_TYPE=Release',
            f'-DRR_N64_GENERATED={generated.as_posix() if generated else ""}',
            f'-DRR_N64_PAYLOAD_DIR={payload.as_posix() if payload else ""}', f'-DRR_N64_STATE_INPUT={stamp}',
            f'-DRR_RECOMP_VERSION={__version__}']


def machine_core(toolchain_root: Path, emit) -> tuple[Path, Path]:
    """The adapted core tree and the machine library built from it (Mupen64Plus, the RSP plugins, ParaLLEl-RDP, our glue), done
    once per adaptation and toolchain: a game compiles only its own objects against it."""
    from . import n64_core
    digest = n64_core.adaptation_digest()
    base = toolchain_root / ('core-' + digest[:12])
    base.mkdir(parents=True, exist_ok=True)
    with entry_lock(base / 'core-lock', timeout=7200):
        tree = n64_core.adapt(n64_core.source(emit), base)
        build = base / 'build'
        ready = build / 'rr-ready.json'
        glue = hashlib.sha256()
        for name in ('glue/parallel_glue.cpp', 'glue/parallel.h', 'glue/libretro_private.h', 'glue/libretro_memory.h',
                     'glue/osal_export.h', 'glue/GLideN64_libretro.h', 'n64_stubs.c', 'CMakeLists.txt'):
            glue.update(name.encode() + b'\0' + (ASSETS / 'native/n64_machine' / name).read_bytes() + b'\0')
        identity = {'adaptation': digest, 'glue': glue.hexdigest()}
        library = build / 'librr_n64_core.a'
        try:
            if json.loads(ready.read_text(encoding='utf-8')) == identity and library.is_file():
                return tree, library
        except (OSError, ValueError):
            pass
        emit('Nintendo 64: building the machine (Mupen64Plus, ParaLLEl-RSP, ParaLLEl-RDP); once per core revision.')
        build.mkdir(parents=True, exist_ok=True)
        cmake, _ = toolchain()
        with timings.phase('compile'):
            run(configure(build, tree), log=build / 'build.log')
            run([cmake, '--build', build, '--parallel', build_jobs(), '--target', 'rr_n64_core'], log=build / 'build.log', timeout=7200)
        if not library.is_file():
            raise ConversionError('Nintendo 64: the machine library was not built.')
        atomic_json(ready, identity)
        return tree, library


def cmake_build(build: Path, tree: Path, core: Path, *, generated: Path | None = None, payload: Path | None = None,
                stamp: str = '') -> Path:
    cmake, _ = toolchain()
    run(configure(build, tree, core=core, generated=generated, payload=payload, stamp=stamp), log=build / 'build.log')
    run([cmake, '--build', build, '--parallel', build_jobs(), '--target', 'n64_player'], log=build / 'build.log', timeout=3600)
    return build_executable(build, PLAYER)


def reference_build(base: Path, tree: Path, core: Path, stamp: str, emit) -> Path:
    """The generic reference player (no game embedded, no native block), built once per SDK stamp."""
    folder = base / 'reference'
    with entry_lock(base / 'reference-lock', timeout=3600):
        ready = folder / 'ready.json'
        try:
            done = json.loads(ready.read_text(encoding='utf-8'))
            if done.get('sdk') == stamp and Path(done['player']).is_file():
                return Path(done['player'])
        except (OSError, ValueError, KeyError):
            pass
        emit('Nintendo 64: building the reference player.')
        folder.mkdir(parents=True, exist_ok=True)
        with timings.phase('compile'):
            player = cmake_build(folder / 'build', tree, core, stamp=stamp)
        atomic_json(ready, {'sdk': stamp, 'player': str(player)})
        return player


def notice_files() -> tuple[str, ...]:
    return NOTICE_FILES


def payload(project: Path, source, title: str, native: bool) -> dict:
    """The resources of the exported game: its cartridge image (big-endian, as an embedded file), the notices and the Windows
    metadata."""
    from .metadata import write_game_metadata
    from .resources import embed_resources
    project.mkdir(parents=True, exist_ok=True)
    resources = {}
    marker = b'[Retro-Recomp]\0' + source.sha256.encode() + b'\0'
    (project / 'export-marker.bin').write_bytes(marker)
    resources[MARKER_RESOURCE] = project / 'export-marker.bin'
    notices = project / 'notices.txt'
    notices.write_text('\n\n'.join((ASSETS / name).read_text(encoding='utf-8') for name in notice_files()), encoding='utf-8')
    resources[NOTICE_RESOURCE] = notices
    (project / 'cartridge.bin').write_bytes(source.data())
    resources[ROM_RESOURCE] = project / 'cartridge.bin'
    header = ['#ifndef RR_N64_PAYLOAD_H', '#define RR_N64_PAYLOAD_H',
              '#define RR_N64_GAME_TITLE ' + json.dumps(title, ensure_ascii=True),
              '#define RR_N64_SOURCE_IDENTITY ' + json.dumps(source.sha256),
              f'#define RR_N64_ROM_RESOURCE {ROM_RESOURCE}',
              '#define RR_N64_CPU_DEFAULT ' + ('RR_N64_CPU_NATIVE' if native else 'RR_N64_CPU_CACHED'),
              'static const volatile unsigned char rr_n64_export_marker[]={' + ','.join(str(c) for c in marker) + '};', '#endif']
    (project / 'n64_payload.h').write_text('\n'.join(header) + '\n', encoding='utf-8')
    if not (project / 'game.ico').is_file():
        shutil.copy2(ASSETS / 'assets/Retro-Recomp.ico', project / 'game.ico')
    metadata = write_game_metadata(project, title, executable_name(title), light_phaser=False, icon=True,
                                   standard='pal' if source.header.pal else 'ntsc', system_id='n64')
    (project / 'game_metadata.rc').write_bytes((project / 'game_resources.rc').read_bytes())
    if os.name == 'nt':
        lines = ['#pragma code_page(65001)'] + [f'{identifier} RCDATA ' + json.dumps(path.as_posix(), ensure_ascii=False)
                                                for identifier, path in resources.items()]
        (project / 'game_resources.rc').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    else:
        embed_resources(project, resources)
    return metadata


# ---------------------------------------------------------------------------------------------------------- replays
def replay(binary: Path, folder: Path, frames: int, events: Path, *, rom: Path | None = None, cpu: str | None = None,
           observe: bool = False, extra=()) -> dict:
    folder.mkdir(parents=True, exist_ok=True)
    args = [str(binary), '--headless', '--frames', str(frames), '--report', str(folder / 'result.json'),
            '--trace', str(folder / 'trace.tsv'), '--input-events', str(events), '--capture', str(folder / 'frame.ppm')]
    if rom is not None:
        args += ['--rom', str(rom)]
    if cpu:
        args += ['--cpu', cpu]
    if observe:
        args += ['--observations', str(folder / 'observations.txt')]
    args += [str(value) for value in extra]
    with (folder / 'stdout.log').open('wb') as out, (folder / 'stderr.log').open('wb') as err:
        result = spawn(args, cwd=folder, timeout=max(900, frames // 2), stdout=out, stderr=err)
    if result.returncode not in (0, 2):
        raise ConversionError('Nintendo 64 replay failed: ' + (folder / 'stderr.log').read_text(encoding='utf-8', errors='replace')[-2000:])
    report = json.loads((folder / 'result.json').read_text(encoding='utf-8'))
    if report.get('stopped'):
        raise ConversionError(f'Nintendo 64: the machine stopped at frame {report.get("frames")}: {report.get("error")}')
    if report.get('frames') != frames:
        raise ConversionError('Nintendo 64 validation returned an incomplete run.')
    return report


def trace_rows(path: Path):
    with path.open('r', encoding='ascii', newline='') as stream:
        next(stream)
        for line in stream:
            values = line.rstrip('\r\n').split('\t')
            yield FrameRow(int(values[0]), values[1], sound=values[2], ram=values[3], pc=values[5])


def trace_digests(path: Path) -> dict:
    """One digest per kind of evidence of a route's trace (CPU registers, RDRAM, picture, sound), over its frames in order."""
    rows = [line.split('\t') for line in Path(path).read_text(encoding='ascii').splitlines()]
    header, body = rows[0], rows[1:]
    columns = {'cpu_hash': [header.index('cpu'), header.index('PC')], 'ram_hash': [header.index('ram')],
               'image_hash': [header.index('video')], 'pcm_hash': [header.index('pcm')]}
    return {name: hashlib.sha256('\n'.join(' '.join(row[i] for i in indexes) for row in body).encode('ascii')).hexdigest()
            for name, indexes in columns.items()}


# The only thing a resumed process may differ on: the core's state leaves out the libretro audio resampler, so the samples after a
# load differ (on every frame compared, and in number by under 0.05 %). A difference in the machine (CPU, RDRAM, picture) refuses
# the conversion.
CONTINUATION_IGNORED = ('pcm', 'samples')


def continuation(timeline: Path, resumed: Path) -> dict:
    """How a fresh process that loaded the state continues the timeline: the rows of the same frames compared column by column;
    it continues when every column but CONTINUATION_IGNORED is equal."""
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


def require_continuation(resumed: dict) -> None:
    """A quick state that does not continue the machine is not delivered, as on the other machines."""
    if not resumed['matches']:
        differing = [name for name in resumed['differing_columns'] if name not in CONTINUATION_IGNORED]
        raise ConversionError('Nintendo 64 F9 continuation differs from its saved timeline '
                              f'({", ".join(differing) or "frames missing from the timeline"}); existing export preserved.')


def game_entry(source) -> Path:
    return library_root('n64') / source.game_key


# -------------------------------------------------------------------------------------------------------- conversion
def convert(path, *, title=None, output=None, cover=None, use_cover=True, online_cover=True, passes=3, frames=3600, scan_level=None,
            emit=print, qualification_events=None, **unused):
    from .n64 import converter_available, read_input
    from . import n64_native
    if not converter_available():
        raise ConversionError('The Nintendo 64 converter files are missing from this installation.')
    require_backend('n64')
    if unused.get('standard_override') not in (None, 'native', 'auto', 'ntsc', 'pal'):
        raise ConversionError('Nintendo 64 timing follows the cartridge\'s country; overrides do not apply.')
    started = time.perf_counter()
    level = resolve_scan_level(scan_level)
    source = read_input(path)
    title = title or source.title
    if any(ord(c) < 32 for c in title) or len(title) > 160:
        raise ConversionError('Invalid Nintendo 64 game title.')
    stamp = sdk_stamp()
    base = ROOT / '.build/n64' / (('win' + toolchain_suffix()) if os.name == 'nt' else 'linux') / stamp[:12]
    base.mkdir(parents=True, exist_ok=True)
    if not output:
        from .paths import games_directory
        output = games_directory(system_id='n64') / 'datas/reports' / source.sha256
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    h = source.header
    emit(f'Nintendo 64: {h.name or "cartridge"} ({h.game_code}, {"PAL" if h.pal else "NTSC"}, {source.size // 1048576} MiB, '
         f'{source.order} byte order).')
    sdl_ready(emit)
    tree, core = machine_core(base.parent, emit)
    reference_player = reference_build(base, tree, core, stamp, emit)
    work = base / source.sha256[:16]
    with entry_lock(work / 'lock', timeout=3600):
        checks = Path(tempfile.mkdtemp(prefix='qa-', dir=work))
        count = max(1200, min(int(frames or 3600), 36000))
        routes = [('main', count, main_route(count) if qualification_events is None else list(qualification_events))]
        if level != 'quick':
            routes.append(('explore', count, explore_route(count)))
        play = play_route(h.game_code) if level in ('extended', 'thorough') and qualification_events is None else None
        if play:
            routes.append(('play', *play))
        scripts = {name: write_events(work / f'inputs-{name}.txt', events) for name, _, events in routes}
        # The ROM is read in place by the reference player (its own byte order is put right in memory); nothing is copied.
        lengths = ', '.join(f'{name} {frames_}' for name, frames_, _ in routes)
        emit(f'Nintendo 64: fresh reference runs (routes and frames: {lengths}; VR4300 on the pure interpreter, observed).')
        expected = {}
        with timings.phase('reference_runs'):
            for name, frames_, _ in routes:
                expected[name] = replay(reference_player, checks / f'reference-{name}', frames_, scripts[name], rom=source.path,
                                        observe=True)
        if not expected['main']['nonblack_frames']:
            raise ConversionError('Nintendo 64: the reference run never showed a picture (no Vulkan 1.1 device, or the game did not boot).')
        variants = n64_native.read_observations([checks / f'reference-{name}' / 'observations.txt' for name, _, _ in routes])
        fresh_variants = len(variants)
        memory = game_entry(source)
        remembered = memory / OBSERVATIONS
        if remembered.is_file():
            try:
                n64_native.read_observations([remembered], variants)
            except (OSError, ConversionError):
                emit('Nintendo 64: the remembered observations are unreadable; this conversion uses its own only.')
        project = work / 'native'
        with timings.phase('code_generation'):
            generation = n64_native.generate(variants, project)
        native = generation['blocks'] > 0
        from .artwork import prepare_icon
        payload_dir = work / 'payload'
        payload_dir.mkdir(parents=True, exist_ok=True)
        artwork = prepare_icon(payload_dir, source.path, title, payload_dir, explicit=Path(cover) if cover else None, online=online_cover,
                               enabled=use_cover, system_id='n64', cache_directory=boxart_cache_directory('n64'), emit=emit)
        metadata = payload(payload_dir, source, title, native)
        if native:
            emit(f'Nintendo 64: {generation["blocks"]} native blocks ({generation["instructions"]} instructions) at '
                 f'{generation["addresses"]} addresses; compiling the game.')
        else:
            # Condition 4 of the review: a game without blocks runs the cached interpreter, checked against its own reference.
            emit('Nintendo 64: no native block; the game runs the core\'s cached interpreter (counted).')
            with timings.phase('reference_runs'):
                for name, frames_, _ in routes:
                    expected[name] = replay(reference_player, checks / f'reference-{name}', frames_, scripts[name], rom=source.path,
                                            cpu='cached')
        with timings.phase('compile'):
            candidate = cmake_build(work / 'build', tree, core, generated=project if native else None, payload=payload_dir, stamp=stamp)
        results = {}
        with timings.phase('native_runs'):
            for name, frames_, _ in routes:
                folder = checks / 'native' / name
                folder.mkdir(parents=True, exist_ok=True)
                exported = folder / candidate.name
                shutil.copy2(candidate, exported)
                results[name] = replay(exported, folder, frames_, scripts[name])
                require_same_file(folder / 'trace.tsv', checks / f'reference-{name}' / 'trace.tsv',
                                  lambda: ConversionError(f'Nintendo 64 {name}: the game and the fresh reference diverged; existing export preserved.'))
        # The delivered file: the compressed copy is replayed on every route against the same fresh reference; the main route
        # saves a quick state on the way (a capture leaves the machine as it was: the trace must still equal the reference).
        packed = work / ('packed-game.exe' if os.name == 'nt' else 'packed-game')
        delivered = deliver_packed(candidate, packed, 'Nintendo 64', emit)
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
                                           mismatch=lambda run_: ConversionError(f'Nintendo 64 {run_[0]}: the compressed executable differs from the fresh reference; existing export preserved.'))
        liveness = [dict(route=name, **report_fields(liveness_summary(trace_rows(folder / 'trace.tsv')), LIVENESS_FIELDS),
                         nonblack_frames=result['nonblack_frames'], audible_frames=result['audible_frames'])
                    for (name, folder, _, _, _), result in zip(packed_runs, packed_results)]
        require_moving_picture(liveness[0], lambda: ConversionError('Nintendo 64 main route: the picture never changed.'))
        # The quick state, loaded by a genuinely fresh process of the delivered file, continues the machine or the export is refused.
        restart = checks / 'restart'
        restart.mkdir()
        fresh = restart / candidate.name
        shutil.copy2(packed, fresh)
        with timings.phase('state_checks'):
            replay(fresh, restart, 400, scripts['main'], extra=['--state-load-start', '--state-slot', checks / 'packed' / 'main' / 'quick.rrstate'])
        resumed = continuation(checks / 'packed' / 'main' / 'trace.tsv', restart / 'trace.tsv')
        require_continuation(resumed)
        rows = []
        for (name, frames_, events), result in zip(routes, packed_results):
            done = results[name]
            folder = checks / 'packed' / name
            # native_entries / interpreted_opcodes are the keys the common report (report_schema, v2) reads for the main CPU: here
            # VR4300 instructions, a jump and its delay slot counted as one by both.
            rows.append({'route': name, 'frames': frames_, 'native_instructions': done['native'], 'interpreted_instructions': done['interpreted'],
                         'native_entries': done['native'], 'interpreted_opcodes': done['interpreted'],
                         'interpreter_percent': 100 * done['interpreted'] / max(1, done['native'] + done['interpreted']),
                         'block_entries': done['block_entries'], 'guard_misses': done['guard_misses'], 'reference_match': True,
                         'packed_reference_match': True, 'reference_interpreted_instructions': expected[name]['interpreted'],
                         'trace_sha256': file_sha256(folder / 'trace.tsv'), **trace_digests(folder / 'trace.tsv'),
                         'steps': len(events), 'script_sha256': file_sha256(scripts[name]),
                         **({'state_saved_at': state_frame, 'state_restart_match': resumed['matches']} if name == 'main' else {})})
        sound_routes = [name for (name, _, _), result in zip(routes, packed_results) if result['audible_frames']]
        report = {
            'tool': 'Retro-Recomp', 'version': __version__, 'created_utc': datetime.now(timezone.utc).isoformat(),
            'system': {'id': 'n64', 'name': 'Nintendo 64'}, 'status': get_profile('n64').status, 'private_development_only': False,
            'target': target_id(), 'rom': source.metadata(), 'source_identity': source.sha256, 'qualification_directory': str(checks),
            'source_rom': str(source.path), 'executable': executable_name(title), 'build_executable': str(candidate),
            'toolchain': toolchain_description(),
            'cartridge': {'internal_name': h.name, 'game_code': h.game_code, 'region': 'PAL' if h.pal else 'NTSC', 'revision': h.revision,
                          'size': source.size, 'byte_order_of_the_file': source.order, 'embedded': 'big-endian image (resource)',
                          'identity': 'SHA-256 of the big-endian image', 'saves': 'the save type the core\'s built-in ROM database '
                          'gives the game (EEPROM, SRAM or Flash), kept with the controller paks in the game\'s data folder'},
            'machine': {'model': 'Nintendo 64 with the Expansion Pak (8 MiB RDRAM), a controller pak in every pad',
                        'reference': 'Mupen64Plus-Next (libretro core) at its pinned revision, adapted at build time: Mupen64Plus core '
                                     '(pure interpreter as the reference), ParaLLEl-RSP (LLE, its own recompiler), ParaLLEl-RDP '
                                     '(LLE, Vulkan compute, commands recorded on the emulation thread for deterministic output)',
                        'gpu': results['main'].get('gpu'), 'region': 'PAL' if h.pal else 'NTSC', 'fps': results['main'].get('fps')},
            'embedded_rom': True, 'static_sdl': True, 'no_external_firmware_required_after_export': True,
            'native_validation': {'passed': True, **delivered.validation_fields(), 'sound_heard': bool(sound_routes), 'sound_routes': sound_routes,
                                  'scope': 'fresh same-machine reference (' + ('pure' if native else 'cached') + ' interpreter): picture, '
                                           'sound, RDRAM and CPU registers of every frame, on bounded pad and stick scripts',
                                  'cpu_mode': 'native blocks, the pure interpreter for the rest' if native else 'cached interpreter (no block)',
                                  'generation': generation, 'fresh_observed_variants': fresh_variants},
            'native_coverage': 'observed straight runs of KSEG0 code as guarded native blocks that call the core\'s own instruction '
                               'functions with constant opcodes (no fetch, no decode, blocks chained, guarded by their words); the '
                               'rest on the core\'s interpreter, counted. The RSP\'s microcode runs on ParaLLEl-RSP and the RDP on the '
                               'GPU: neither is VR4300 code and neither is counted as native',
            'final_checks': rows, **delivered.report_fields(), 'liveness': liveness, 'scan_level': level,
            'game_states': {'supported': True, 'save_key': 'F8', 'load_key': 'F9', 'fresh_process_verified': resumed['matches'], 'slots': 1,
                            'compatibility': 'the exact game and build that wrote the state; refused between builds',
                            'schema': 'RRN64QS2', 'machine': 'n64', 'rom_identity': source.sha256,
                            'validation': {'process': 'fresh', 'compressed_copy': True, 'saved_at_frame': state_frame,
                                           'continuation_frames': resumed['frames'], 'continuation_matches': resumed['matches'],
                                           'equal_frames': resumed['equal_frames'], 'differing_columns': resumed['differing_columns'],
                                           'saving_leaves_the_timeline': True,
                                           'compared': 'CPU registers, RDRAM and picture of every frame; not the sound samples'}},
            'ordinary_saves': {'supported': True, 'scope': 'EEPROM, SRAM, Flash and the four controller paks, one file in the game\'s '
                                                           'data folder (written when they change during play)', 'validated': False},
            'input_players': 4, 'peripheral': {'pads': 4, 'stick': 'analog (a gamepad\'s left stick; arrows on the keyboard)',
                                               'c_buttons': 'buttons and the right stick', 'rumble': 'Rumble Pak when chosen (memory pak by default)'},
            'video_model': {'standard': 'PAL' if h.pal else 'NTSC', 'frameskip': False, 'fps': packed_results[0]['fps'],
                            'renderer': 'ParaLLEl-RDP (Vulkan 1.1); integrated graphics unverified'},
            'runtime_data': {'directory': 'datas', 'shared_config': 'datas/Retro-Recomp.ini', 'game_directory': 'datas/games/n64-' + source.sha256},
            'artwork': artwork, 'windows_metadata': metadata,
            'hardware_accuracy_validated': False, 'full_game_validated': False, 'latency_ms': None, 'real_time_claimed': False,
            'licence': {'executable': 'GPL-3.0 (Mupen64Plus GPL-2.0-or-later with GNU Lightning LGPL-3.0-or-later and the MIT ParaLLEl '
                                      'parts; Retro-Recomp\'s own files keep their MIT notice)', 'notices': list(notice_files()),
                        'excluded': ['angrylion (no commercial use)', 'GLideN64 renderer (GPL-2.0-only)']},
            'qualification_scope': {'controls': 'bounded pad and stick scripts', 'media': 'cartridge images (.z64, .v64, .n64)',
                                    'universal_zero_fallback_claim': False},
            'conversion_wall_seconds': round(time.perf_counter() - started, 3)}
        write_report(output / 'conversion-report.json', report)
        # The private memory: the observations of this conversion (with those remembered), for the next one.
        memory.mkdir(parents=True, exist_ok=True)
        with entry_lock(memory, timeout=1800):
            n64_native.write_observations(memory / (OBSERVATIONS + '.tmp'), variants)
            os.replace(memory / (OBSERVATIONS + '.tmp'), remembered)
            atomic_json(memory / 'compilation.json', {'schema': 1, 'title': title, 'system': 'n64', 'game': source.game_key,
                                                      'rom_sha256': source.sha256, 'game_code': h.game_code, 'guarded_variants': len(variants),
                                                      'blocks': generation['blocks'], 'sdk': stamp,
                                                      'observations_sha256': file_sha256(remembered), 'private_development_only': True,
                                                      'fresh_reference_passed': True})
        emit('Nintendo 64: validated standalone game ready.')
        return candidate
