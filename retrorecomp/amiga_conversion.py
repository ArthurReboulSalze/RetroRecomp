"""Commodore Amiga conversion (experimental): a WHDLoad install becomes a standalone game (MIT).

Every conversion starts from a fresh reference run: the install (the slave and its data files, read from the player's archive)
runs on vAmiga's Core with every 68000 instruction on Moira's interpreter, and the instructions it runs from RAM are recorded.
Those become guarded native steps (the shared generator `m68k_observed` with the Amiga's Moira hooks, `amiga_codegen`): each
calls the very Moira template the interpreter would run, behind a live-word guard, and anything not seen stays on the counted
interpreter. The game executable (install, steps, the machine and the host kit) is then replayed headless, copied alone, and
its trace (picture, sound, RAM, CPU registers of every frame) must equal the reference's; so must the compressed copy that is
delivered, and a quick state saved by it must continue the same timeline in a fresh process. Nothing is claimed beyond those
bounded routes: the hardware fidelity is vAmiga's, unmeasured here, and the routes are scripts, not play.

The private memory of this machine lives under `<library>/amiga/<game>/` (the archive's SHA-256): `compilation.json` and the
observations of the last conversion, which help the next one and never replace its fresh reference.
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
from .conversion_common import check_exit, resolve_scan_level, spawn
from .conversion_gates import continuation_difference, require, require_same_file
from .core import ConversionError, executable_name, run, toolchain
from .delivery_evidence import FrameRow, deliver_packed, liveness_summary, replay_packed, report_fields, require_moving_picture, same_trace
from .library import atomic_json, entry_lock, file_sha256, library_root
from .paths import ASSETS, ROOT, boxart_cache_directory
from .platforms import build_executable, build_jobs, cmake_target_args, sdl_install, target_id
from .report_schema import write_report
from .systems import get_profile
from .toolchain import describe as toolchain_description, suffix as toolchain_suffix

PLAYER = 'RetroRecomp-Amiga'
# The notices every exported Amiga game carries (resource 203, as on the other machines): the vAmiga Core (MPL-2.0 per file) and
# Moira (MIT), the 68000 decoder of m68k-recomp-core compiled into the index of native steps, SDL and the host kit's parts.
NOTICE_FILES = ('LICENSE', 'licenses/vamiga.md', 'licenses/segagenesisrecomp.md', 'licenses/SDL2.md', 'licenses/xbr.md',
                'licenses/Noto.md', 'licenses/UPX.md', 'licenses/llvm-mingw.md')
NOTICE_RESOURCE = 203
OBSERVATIONS = 'converter-observations.txt'
# The liveness keys of the report, from the common record of delivery_evidence.
LIVENESS_FIELDS = {'frames': 'frames', 'distinct_pictures': 'distinct_pictures', 'distinct_audio_blocks': 'distinct_sound_blocks',
                   'distinct_ram_states': 'distinct_ram_states', 'distinct_program_counters': 'distinct_program_counters'}


def sdk_stamp(part: str | None = None) -> str:
    """The identity of the Amiga's build inputs (its stamped files and the vAmiga adaptation); part='game' leaves the shell out."""
    from .compilation_inputs import engine_stamp, role_stamps
    from .amiga_vamiga import adaptation_digest
    value = hashlib.sha256(b'amiga-sdk-v1\0')
    value.update((role_stamps('amiga')['game'] if part == 'game' else engine_stamp('amiga')).encode())
    value.update(b'\0' + adaptation_digest().encode())
    return value.hexdigest()


def ntsc_install(source) -> bool:
    """An install made for an NTSC machine says so in its archive's name (WHDLoad's own default is the PAL machine)."""
    return 'ntsc' in source.path.stem.casefold()


# ------------------------------------------------------------------------------------------------------------- the routes
def main_route(frames: int, key_exit: int) -> list[tuple[int, int, str, int, int]]:
    """A bounded script for every install: it waits, then presses the joystick's fire, moves it, clicks and moves the mouse and
    taps Space and Return, so that title screens and menus are left and the first moments of play are run. Never the slave's
    quit key. Frames are the machine's own."""
    events = []
    for start in range(250, frames - 20, 150):
        events.append((start, start + 8, 'joy', 4, 1))                     # fire
    for start, length, bit in ((900, 60, 3), (1100, 60, 2), (1300, 30, 0), (1400, 30, 1), (1600, 120, 3), (1900, 90, 2),
                               (2200, 60, 0), (2400, 120, 3), (2700, 60, 2)):
        if start + length < frames:
            events.append((start, start + length, 'joy', bit, 1))
    for start in (320, 1220, 2120):
        if start + 6 < frames:
            events.append((start, start + 6, 'mouse', 2, 1))                # left click
    if 1040 < frames:
        events.append((1000, 1040, 'mouse', 0, 3))
        events.append((1000, 1040, 'mouse', 1, 2))
    for start, key in ((500, 0x40), (800, 0x44), (1700, 0x40)):
        if key != key_exit and start + 6 < frames:
            events.append((start, start + 6, 'key', key, 1))
    return sorted(events)


def explore_route(frames: int, key_exit: int) -> list[tuple[int, int, str, int, int]]:
    """A second, denser script (standard level and above): long holds of each direction with the fire held at times."""
    events = []
    t, bits = 200, (3, 2, 0, 1)
    n = 0
    while t + 100 < frames:
        events.append((t, t + 90, 'joy', bits[n % 4], 1))
        if n % 2:
            events.append((t + 20, t + 50, 'joy', 4, 1))
        t += 110
        n += 1
    for start in range(400, frames - 10, 600):
        if key_exit != 0x40:
            events.append((start, start + 4, 'key', 0x40, 1))
    return sorted(events)


def write_events(path: Path, events) -> Path:
    if len(events) > 4096:
        raise ConversionError('Too many Amiga route events.')
    path.write_text(''.join(f'{b} {e} {kind} {code} {value}\n' for b, e, kind, code, value in events), encoding='ascii')
    return path


# --------------------------------------------------------------------------------------------------------- building
def machine_core(base: Path, emit) -> Path:
    from . import amiga_vamiga
    with entry_lock(base / 'vamiga-lock', timeout=1800):
        return amiga_vamiga.adapt(amiga_vamiga.source(emit), base / 'vamiga')


def cmake_build(build: Path, core: Path, *, emit, generated: Path | None = None, payload: Path | None = None, tools: bool = False,
                stamp: str = '') -> Path:
    cmake, generator = toolchain()
    targets = ['amiga_player'] + (['amiga_moira_map'] if tools else [])
    run([cmake, '-S', ASSETS / 'native/amiga_machine', '-B', build, '-G', generator, *cmake_target_args(),
         f'-DRR_VAMIGA_CORE={core.as_posix()}', f'-DCMAKE_PREFIX_PATH={sdl_install().as_posix()}',
         f'-DRR_AMIGA_GENERATED={generated.as_posix() if generated else ""}',
         f'-DRR_AMIGA_PAYLOAD_DIR={payload.as_posix() if payload else ""}', f'-DRR_AMIGA_TOOLS={"ON" if tools else "OFF"}',
         f'-DRR_AMIGA_STATE_INPUT={stamp}', f'-DRR_RECOMP_VERSION={__version__}'], log=build / 'build.log')
    run([cmake, '--build', build, '--config', 'Release', '--parallel', build_jobs(), '--target', *targets], log=build / 'build.log')
    return build_executable(build, PLAYER)


def reference_build(base: Path, core: Path, stamp: str, emit) -> tuple[Path, Path]:
    """The generic reference player (no game, no native step) and the opcode table of the 68000, built once per SDK stamp."""
    folder = base / 'reference'
    with entry_lock(base / 'reference-lock', timeout=3600):
        ready = folder / 'ready.json'
        try:
            done = json.loads(ready.read_text(encoding='utf-8'))
            if done.get('sdk') == stamp and Path(done['player']).is_file() and Path(done['map']).is_file():
                return Path(done['player']), Path(done['map'])
        except (OSError, ValueError, KeyError):
            pass
        emit('Amiga: building the reference machine (vAmiga Core, interpreted 68000).')
        folder.mkdir(parents=True, exist_ok=True)
        with timings.phase('compile'):
            player = cmake_build(folder / 'build', core, emit=emit, tools=True, stamp=stamp)
        tool = build_executable(folder / 'build', 'amiga_moira_map')
        table = folder / 'moira-map-68000.txt'
        result = spawn([tool, table], cwd=folder, timeout=120, capture_output=True)
        check_exit(result, lambda _: ConversionError('Amiga: the opcode table of the 68000 could not be written.'))
        atomic_json(ready, {'sdk': stamp, 'player': str(player), 'map': str(table)})
        return player, table


def extract_install(source, folder: Path) -> dict:
    """The slave and the data files, extracted from the archive into `folder` with an `install.txt` the reference player reads."""
    from . import amiga_lha, amiga_whdload
    blob = source.data()
    install = amiga_whdload.install(blob)
    if folder.exists():
        shutil.rmtree(folder)
    (folder / 'files').mkdir(parents=True)
    slave = amiga_lha.extract(blob, next(m for m in amiga_lha.members(blob) if m.name == install.slave_path))
    (folder / 'game.slave').write_bytes(slave)
    lines = ['slave game.slave', f'ntsc {int(ntsc_install(source))}']
    names = {}
    for n, (name, member) in enumerate(sorted(install.files.items())):
        if '\t' in name or '\n' in name:
            raise ConversionError(f'Amiga: an install file name the player cannot carry: {name!r}.')
        data = amiga_lha.extract(blob, member)
        stored = f'files/{n:05d}.bin'
        (folder / stored).write_bytes(data)
        names[name] = stored
        lines.append(f'file {name}\t{stored}')
    (folder / 'install.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return {'install': install, 'slave': slave, 'files': names}


def payload(project: Path, source, extracted: dict, folder: Path, title: str, mouse_game: bool, artwork) -> dict:
    """The resources of the exported game: its install (as embedded files) and the Windows metadata."""
    from .metadata import write_game_metadata
    from .resources import embed_resources
    project.mkdir(parents=True, exist_ok=True)
    resources = {}
    marker = b'[Retro-Recomp]\0' + source.sha256.encode() + b'\0'
    branding = project / 'export-marker.bin'
    branding.write_bytes(marker)
    resources[299] = branding
    notices = project / 'notices.txt'
    notices.write_text('\n\n'.join((ASSETS / name).read_text(encoding='utf-8') for name in NOTICE_FILES), encoding='utf-8')
    resources[NOTICE_RESOURCE] = notices
    slave = project / 'blob-300.bin'
    slave.write_bytes(extracted['slave'])
    resources[300] = slave
    rows = []
    for n, (name, stored) in enumerate(sorted(extracted['files'].items())):
        identifier = 301 + n
        path = project / f'blob-{identifier:03d}.bin'
        shutil.copyfile(folder / stored, path)
        resources[identifier] = path
        rows.append('{' + json.dumps(name, ensure_ascii=True) + f',{identifier}' + '},')
    header = ['#ifndef RR_AMIGA_PAYLOAD_H', '#define RR_AMIGA_PAYLOAD_H',
              '#define RR_AMIGA_GAME_TITLE ' + json.dumps(title, ensure_ascii=True),
              '#define RR_AMIGA_SOURCE_IDENTITY ' + json.dumps(source.sha256),
              f'#define RR_AMIGA_NTSC {int(ntsc_install(source))}', f'#define RR_AMIGA_MOUSE_GAME {int(mouse_game)}',
              '#define RR_AMIGA_SLAVE_RESOURCE 300',
              'typedef struct {const char *name;unsigned resource;} RrAmigaPayloadFile;',
              'static const RrAmigaPayloadFile rr_amiga_files[]={', *rows, '{0,0}};',
              f'#define RR_AMIGA_FILE_COUNT {len(rows)}u',
              'static const volatile unsigned char rr_amiga_export_marker[]={' + ','.join(str(c) for c in marker) + '};', '#endif']
    (project / 'amiga_payload.h').write_text('\n'.join(header) + '\n', encoding='utf-8')
    if not (project / 'game.ico').is_file():
        shutil.copy2(ASSETS / 'assets/Retro-Recomp.ico', project / 'game.ico')
    metadata = write_game_metadata(project, title, executable_name(title), light_phaser=False, icon=True, standard='native', system_id='amiga')
    (project / 'game_metadata.rc').write_bytes((project / 'game_resources.rc').read_bytes())
    if os.name == 'nt':
        lines = ['#pragma code_page(65001)'] + [f'{identifier} RCDATA ' + json.dumps(path.as_posix(), ensure_ascii=False)
                                                for identifier, path in resources.items()]
        (project / 'game_resources.rc').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    else:
        embed_resources(project, resources)
    return metadata


def read_observations(path: Path) -> list[tuple[int, str]]:
    """The (pc, words) of an observation file, every one checked against the Amiga's apertures."""
    observed = get_profile('amiga').observed_code
    samples = set()
    for line in path.read_text(encoding='ascii').splitlines():
        pc, words = line.split()
        pc = int(pc, 16)
        observed.check_sample(pc, words)
        samples.add((pc, words))
        if len(samples) > 1048576:
            raise ConversionError('Amiga instruction observation bound exceeded.')
    return sorted(samples)


def generate(project: Path, samples: list, table: Path) -> dict:
    """The guarded native steps of these observations (the shared generator with the Amiga's Moira hooks)."""
    from . import amiga_codegen, m68k_observed
    from .megadrive_codegen import write_changed
    engine = ROOT / '.deps/segagenesisrecomp'
    observed = get_profile('amiga').observed_code
    amiga_codegen.load_opcode_map(table)
    project.mkdir(parents=True, exist_ok=True)
    decode = m68k_observed.build_decoder(project, engine, source=ASSETS / 'native/x68000_native/decode.c', root=ASSETS,
                                         target='amiga_decode', name='RetroAmigaDecode')
    bodies = observed.load_bodies(engine)
    m68k_observed.write_step_semantics(project, bodies, observed.prefix, lambda text: text)
    write_changed(project / 'm68k_decoder.h', (engine / 'external/m68k-recomp-core/common/m68k_decoder.h').read_text(encoding='utf-8'))
    write_changed(project / 'rom_parser.h', (engine / 'recompiler/src/rom_parser.h').read_text(encoding='utf-8'))
    steps = m68k_observed.write_steps(project, samples, observed=observed, bodies=bodies, decode_tool=decode, diagnostic=[],
                                      alias=lambda text: text, form_body=lambda body: body, descriptor=lambda ins, name: ins,
                                      index_head=amiga_codegen.INDEX_HEAD, code_view=amiga_codegen.CODE_VIEW,
                                      index_tail=amiga_codegen.index_tail)
    return {'samples': len(samples), 'instructions': len(steps.instructions), 'forms': len(steps.forms), 'pcs': len(steps.groups),
            'opcode_table_sha256': file_sha256(table)}


# ---------------------------------------------------------------------------------------------------------- replays
def replay(binary: Path, folder: Path, frames: int, events: Path, *, install: Path | None = None, reference: bool = False,
           observe: bool = False, extra=()) -> dict:
    folder.mkdir(parents=True, exist_ok=True)
    args = [str(binary), '--headless', '--frames', str(frames), '--report', str(folder / 'result.json'), '--trace', str(folder / 'trace.tsv'),
            '--input-events', str(events), '--resload-log', str(folder / 'resload.log'), '--capture', str(folder / 'frame.ppm')]
    if install:
        args += ['--install', str(install), '--saves', str(folder / 'saves')]
    if reference:
        args.append('--reference-cpu')
    if observe:
        args += ['--observations', str(folder / 'observations.txt')]
    args += [str(value) for value in extra]
    with (folder / 'stdout.log').open('wb') as out, (folder / 'stderr.log').open('wb') as err:
        result = spawn(args, cwd=folder, timeout=max(600, frames // 4), stdout=out, stderr=err)
    if result.returncode not in (0, 2):
        raise ConversionError('Amiga replay failed: ' + (folder / 'stderr.log').read_text(encoding='utf-8', errors='replace')[-2000:])
    report = json.loads((folder / 'result.json').read_text(encoding='utf-8'))
    if report.get('stopped'):
        raise ConversionError(f'Amiga: the install stopped at frame {report.get("frames")}: {report.get("error")}')
    if report.get('frames') != frames:
        raise ConversionError('Amiga validation returned an incomplete run.')
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


# What a resumed process is not compared on: vAmiga's snapshot leaves out the state of its audio output (the samplers are reset
# on load, the resampler's phase and the output filters are not saved), so the samples of the frames after a load differ while
# the machine (CPU, RAM, picture) continues the same timeline. Reported as such (`game_states.validation`).
CONTINUATION_IGNORED = ('pcm',)


def continues(timeline: Path, resumed: Path) -> bool:
    """A fresh process that loaded the state continues the timeline: its rows (frame numbers included, they are the machine's)
    equal the timeline's rows of the same frames, on every column but CONTINUATION_IGNORED."""
    def rows(path):
        lines = Path(path).read_text(encoding='ascii').splitlines()
        header = lines[0].split('\t')
        keep = [i for i, name in enumerate(header) if name not in CONTINUATION_IGNORED]
        return [tuple(line.split('\t')[i] for i in keep) for line in lines[1:]]
    later = rows(resumed)
    earlier = {row[0]: row for row in rows(timeline)}
    return bool(later) and all(earlier.get(row[0]) == row for row in later)


def game_entry(source) -> Path:
    return library_root('amiga') / source.game_key


# -------------------------------------------------------------------------------------------------------- conversion
def convert(path, *, title=None, output=None, cover=None, use_cover=True, online_cover=True, passes=3, frames=3000, scan_level=None,
            emit=print, qualification_events=None, **unused):
    from .amiga import developer_available, read_input
    from . import amiga_whdload
    if not developer_available():
        raise ConversionError('The Amiga converter files are missing from this installation.')
    if unused.get('standard_override') not in (None, 'native', 'auto'):
        raise ConversionError('Amiga timing follows the install (PAL, or NTSC when its archive says so); PAL/NTSC overrides do not apply.')
    started = time.perf_counter()
    level = resolve_scan_level(scan_level)
    source = read_input(path)
    if source.kickemu:
        raise ConversionError('This install needs a Kickstart (KickEmu): the Amiga profile does not run those yet.')
    title = title or source.title
    if any(ord(c) < 32 for c in title) or len(title) > 160:
        raise ConversionError('Invalid Amiga game title.')
    stamp = sdk_stamp()
    base = ROOT / '.build/amiga' / (('win' + toolchain_suffix()) if os.name == 'nt' else 'linux') / stamp[:12]
    base.mkdir(parents=True, exist_ok=True)
    if not output:
        from .paths import games_directory
        output = games_directory(system_id='amiga') / 'datas/reports' / source.sha256
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    emit('Amiga: reading the WHDLoad install (slave and data files).')
    from .console16 import dependencies16
    dependencies16('md', emit)   # SDL and the shared 68000 decoder of the generator
    core = machine_core(base, emit)
    reference_player, table = reference_build(base, core, stamp, emit)
    work = base / source.sha256[:16]
    with entry_lock(work / 'lock', timeout=3600):
        checks = Path(tempfile.mkdtemp(prefix='qa-', dir=work))
        extracted = extract_install(source, work / 'install')
        slave: amiga_whdload.Slave = extracted['install'].slave
        count = max(1000, min(int(frames or 3000), 36000))
        routes = [('main', count, main_route(count, slave.key_exit) if qualification_events is None else list(qualification_events))]
        if level != 'quick':
            routes.append(('explore', count, explore_route(count, slave.key_exit)))
        scripts = {name: write_events(work / f'inputs-{name}.txt', events) for name, _, events in routes}
        emit(f'Amiga: fresh reference runs ({len(routes)} route(s) of {count} frames, interpreted 68000).')
        expected = {}
        with timings.phase('reference_runs'):
            for name, frames_, _ in routes:
                expected[name] = replay(reference_player, checks / f'reference-{name}', frames_, scripts[name], install=work / 'install',
                                        reference=True, observe=True)
        samples = set()
        for name, _, _ in routes:
            samples |= set(read_observations(checks / f'reference-{name}' / 'observations.txt'))
        fresh_samples = len(samples)
        memory = game_entry(source)
        remembered = memory / OBSERVATIONS
        if remembered.is_file():
            try:
                samples |= set(read_observations(remembered))
            except (OSError, ValueError):
                emit('Amiga: the remembered observations are unreadable; this conversion uses its own only.')
        mouse_game = False
        from .artwork import prepare_icon
        payload_dir = work / 'payload'
        payload_dir.mkdir(parents=True, exist_ok=True)
        artwork = prepare_icon(payload_dir, source.path, title, payload_dir, explicit=Path(cover) if cover else None, online=online_cover,
                               enabled=use_cover, system_id='amiga', cache_directory=boxart_cache_directory('amiga'), emit=emit)
        metadata = payload(payload_dir, source, extracted, work / 'install', title, mouse_game, artwork)
        project = work / 'native'
        candidate = generation = None
        results = {}
        for attempt in range(max(1, min(int(passes), 10))):
            timings.begin_pass(attempt + 1)
            with timings.phase('code_generation'):
                generation = generate(project, sorted(samples), table)
            emit(f'Amiga: {generation["instructions"]} observed instructions in {generation["forms"]} native forms; compiling the game.')
            with timings.phase('compile'):
                candidate = cmake_build(work / 'build', core, emit=emit, generated=project, payload=payload_dir, stamp=stamp)
            run_dir = checks / f'native-{attempt + 1}'
            results = {}
            more = set()
            with timings.phase('native_runs'):
                for name, frames_, _ in routes:
                    folder = run_dir / name
                    folder.mkdir(parents=True, exist_ok=True)
                    exported = folder / candidate.name
                    shutil.copy2(candidate, exported)
                    results[name] = replay(exported, folder, frames_, scripts[name], observe=True)
                    require_same_file(folder / 'trace.tsv', checks / f'reference-{name}' / 'trace.tsv',
                                      lambda: ConversionError(f'Amiga {name}: the native game and the fresh reference diverged; existing export preserved.'))
                    require_same_file(folder / 'resload.log', checks / f'reference-{name}' / 'resload.log',
                                      lambda: ConversionError(f'Amiga {name}: the resload calls differ from the reference; existing export preserved.'))
                    more |= set(read_observations(folder / 'observations.txt'))
            if not results['main']['nonblack_frames']:
                raise ConversionError('Amiga validation did not produce a usable picture.')
            interpreted = sum(result['interpreted'] for result in results.values())
            if not interpreted or not (more - samples):
                break
            emit(f'Amiga: {interpreted} instructions still interpreted; extending the native coverage.')
            samples |= more
        timings.end_passes()
        # The delivered file: the compressed copy is replayed on every route against the same fresh reference.
        packed = work / ('packed-game.exe' if os.name == 'nt' else 'packed-game')
        delivered = deliver_packed(candidate, packed, 'Amiga', emit)
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
                                           mismatch=lambda run_: ConversionError(f'Amiga {run_[0]}: the compressed executable differs from the fresh reference; existing export preserved.'))
        liveness = [dict(route=name, **report_fields(liveness_summary(trace_rows(folder / 'trace.tsv')), LIVENESS_FIELDS),
                         nonblack_frames=result['nonblack_frames'], audible_frames=result['audible_frames'])
                    for (name, folder, _, _, _), result in zip(packed_runs, packed_results)]
        require_moving_picture(liveness[0], lambda: ConversionError('Amiga main route: the picture never changed.'))
        # The quick state, loaded by a genuinely fresh process of the delivered file, continues the saved timeline.
        restart = checks / 'restart'
        restart.mkdir()
        fresh = restart / candidate.name
        shutil.copy2(packed, fresh)
        with timings.phase('state_checks'):
            replay(fresh, restart, 400, scripts['main'], extra=['--state-load-start', '--state-slot', checks / 'packed' / 'main' / 'quick.rrstate'])
        require(continues(checks / 'packed' / 'main' / 'trace.tsv', restart / 'trace.tsv'),
                lambda: ConversionError('Amiga: the quick state does not continue its saved timeline.'))
        rows = []
        for (name, frames_, events), result in zip(routes, packed_results):
            native = results[name]['native']
            interpreted = results[name]['interpreted']
            folder = checks / 'packed' / name
            rows.append({'route': name, 'frames': frames_, 'native_entries': native, 'interpreted_opcodes': interpreted,
                         'interpreter_percent': 100 * interpreted / max(1, native + interpreted), 'reference_match': True,
                         'packed_reference_match': True, 'resload_match': True, 'resload_calls': result['resload_calls'],
                         'trace_sha256': file_sha256(folder / 'trace.tsv'), **trace_digests(folder / 'trace.tsv'),
                         'steps': len(events), 'script_sha256': file_sha256(scripts[name]),
                         **({'state_restart_match': True, 'state_frame': state_frame} if name == 'main' else {})})
        sound_routes = [name for (name, _, _), result in zip(routes, packed_results) if result['audible_frames']]
        report = {
            'tool': 'Retro-Recomp', 'version': __version__, 'created_utc': datetime.now(timezone.utc).isoformat(),
            'system': {'id': 'amiga', 'name': 'Commodore Amiga'}, 'status': get_profile('amiga').status, 'private_development_only': True,
            'target': target_id(), 'rom': source.metadata(), 'source_identity': source.sha256, 'qualification_directory': str(checks),
            'source_rom': str(source.path), 'executable': executable_name(title), 'build_executable': str(candidate),
            'toolchain': toolchain_description(),
            'whdload': {'slave': source.slave_path, 'slave_version': slave.version, 'flags': list(slave.flag_names), 'base_mem': slave.base_mem,
                        'exp_mem': slave.exp_mem, 'kickstart_required': False, 'whdload_used': False,
                        'resload': 'Retro-Recomp MIT resload layer (native/amiga_whdload)', 'video': 'NTSC' if ntsc_install(source) else 'PAL',
                        'data_files': len(extracted['files'])},
            'machine': {'model': 'Amiga 500 (ECS, 68000)', 'reference': 'vAmiga Core (MPL-2.0) at its pinned revision, adapted at build time',
                        'boot_rom': 'authored boot ROM (no Kickstart)'},
            'embedded_rom': True, 'static_sdl': True, 'no_external_firmware_required_after_export': True,
            'native_validation': {'passed': True, **delivered.validation_fields(), 'sound_heard': bool(sound_routes), 'sound_routes': sound_routes,
                                  'scope': 'fresh same-machine reference (interpreted 68000): picture, sound, RAM and CPU registers of every frame, '
                                           'and the resload calls, on bounded joystick, mouse and keyboard scripts',
                                  'generation': generation, 'fresh_observed_instructions': fresh_samples},
            'native_coverage': 'observed RAM instructions as guarded native steps calling the Moira templates of the reference CPU',
            'final_checks': rows, **delivered.report_fields(), 'liveness': liveness, 'scan_level': level,
            'game_states': {'supported': True, 'save_key': 'F8', 'load_key': 'F9', 'fresh_process_verified': True, 'slots': 1,
                            'compatibility': 'the exact install and the build that wrote the state; refused between builds',
                            'schema': 'RRAMIGA-STATE-1', 'machine': 'amiga500', 'rom_identity': source.sha256,
                            'validation': {'process': 'fresh', 'compressed_copy': True, 'saved_at_frame': state_frame,
                                           'continuation_frames': 400, 'continuation_matches': True,
                                           'compared': 'CPU registers, RAM and picture of every frame; not the sound samples (vAmiga does '
                                                       'not save the state of its audio resampler and filters)'}},
            'ordinary_saves': {'supported': True, 'scope': 'files the install writes through resload_SaveFile, kept beside the game',
                               'path': 'datas/games/amiga-' + source.sha256 + '/saves',
                               'validation': {'checked_in_this_conversion': False, 'evidence': 'tests/test_amiga_resload.py (SaveFile, the save callback)'}},
            'input_players': 1, 'peripheral': {'joystick_ports': 1, 'mouse': 'port 1, captured on a click', 'keyboard': 'guest keyboard (Ctrl+Alt+K for full typing)'},
            'video_model': {'standard': 'NTSC' if ntsc_install(source) else 'PAL', 'frameskip': False, 'fps': packed_results[0]['fps']},
            'runtime_data': {'directory': 'datas', 'shared_config': 'datas/Retro-Recomp.ini', 'game_directory': 'datas/games/amiga-' + source.sha256},
            'artwork': artwork, 'windows_metadata': metadata,
            'hardware_accuracy_validated': False, 'full_game_validated': False, 'latency_ms': None,
            'qualification_scope': {'controls': 'bounded joystick, mouse and keyboard scripts', 'media': 'WHDLoad installs without Kickstart',
                                    'universal_zero_fallback_claim': False},
            'conversion_wall_seconds': round(time.perf_counter() - started, 3)}
        write_report(output / 'conversion-report.json', report)
        # The private memory: the observations of this conversion's own runs (fresh reference and native), for the next one.
        memory.mkdir(parents=True, exist_ok=True)
        with entry_lock(memory, timeout=1800):
            text = ''.join(f'{pc:06x} {words}\n' for pc, words in sorted(samples))
            (memory / (OBSERVATIONS + '.tmp')).write_text(text, encoding='ascii')
            os.replace(memory / (OBSERVATIONS + '.tmp'), remembered)
            atomic_json(memory / 'compilation.json', {'schema': 1, 'title': title, 'system': 'amiga', 'game': source.game_key,
                                                      'rom_sha256': source.sha256, 'guarded_variants': len(samples), 'sdk': stamp,
                                                      'observations_sha256': file_sha256(remembered), 'private_development_only': True,
                                                      'fresh_reference_passed': True})
        emit('Amiga: validated standalone game ready.')
        return candidate
