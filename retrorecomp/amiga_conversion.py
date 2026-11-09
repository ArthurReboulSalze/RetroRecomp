"""Commodore Amiga conversion (experimental): a WHDLoad install becomes a standalone game (MIT).

Every conversion starts from a fresh reference run: the install (the slave and its data files, read from the player's archive)
runs on vAmiga's Core with every 68000 instruction on Moira's interpreter, and the instructions it runs from RAM are recorded.
Those become native code (`amiga_codegen`), per opcode: translated C for the forms the translator knows (`amiga_translate`, the bus functions staying the machine's), Moira's
code specialised for the others, each counted, chained from instruction to instruction behind the opcode the CPU has latched; anything not seen stays on the counted
interpreter; beyond the routes a sweep over images of memory adds more of the same, counted apart when it runs. The game executable (install, steps, the machine and the host kit) is then replayed headless, copied alone, and
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
import re
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
# Moira (MIT), SDL and the host kit's parts.
NOTICE_FILES = ('LICENSE', 'licenses/vamiga.md', 'licenses/SDL2.md', 'licenses/xbr.md',
                'licenses/Noto.md', 'licenses/UPX.md', 'licenses/llvm-mingw.md')
NOTICE_RESOURCE = 203
# The player's Kickstart in the player's own export (decision D1, 6 November 2026): 1.x images (256 KiB) only, for now.
KICKSTART_RESOURCE = 298
KICKSTART_1X_SIZE = 0x40000
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


# The menu keys of a long route, Amiga raw codes: Return, Space, Y, 1, 2.
LONG_ROUTE_KEYS = (0x44, 0x40, 0x15, 0x01, 0x02)


def long_route(identity: str, index: int, frames: int, key_exit: int) -> list[tuple[int, int, str, int, int]]:
    """A long varied route (extended level and above), fully determined by the exact install; never the slave's quit key. It does not finish a game."""
    from .computer_routes import long_events
    return long_events(f'amiga-long:{identity}:{index}', frames, tuple(key for key in LONG_ROUTE_KEYS if key != key_exit))


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
    # The vAmiga Core is about 280 files: an hour, as for the CPS-1, so a slower PC (a 2-core Linux laptop took over ten
    # minutes) finishes it instead of timing out.
    run([cmake, '--build', build, '--config', 'Release', '--parallel', build_jobs(), '--target', *targets], log=build / 'build.log',
        timeout=3600)
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
    custom = amiga_whdload.custom_options(blob, install)
    lines = ['slave game.slave', f'ntsc {int(ntsc_install(source))}',
             *(f'custom {k + 1} {value}' for k, value in enumerate(custom) if value)]
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
    return {'install': install, 'slave': slave, 'files': names, 'custom': custom}


def display_window(results) -> tuple[int, int, int, int] | None:
    """The union of the display windows the reference runs saw (their reports' `view`: x, y, w, h in picture columns and
    lines), which the exported game shows instead of the overscan border; None when no run opened one."""
    boxes = [r['view'] for r in results if r.get('view')]
    if not boxes:
        return None
    x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
    x1, y1 = max(b[0] + b[2] for b in boxes), max(b[1] + b[3] for b in boxes)
    return x0, y0, x1 - x0, y1 - y0


def payload(project: Path, source, extracted: dict, folder: Path, title: str, mouse_game: bool, artwork,
            view: tuple[int, int, int, int] | None = None, kickstart: Path | None = None) -> dict:
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
    if kickstart is not None:
        resources[KICKSTART_RESOURCE] = kickstart
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
              '#define RR_AMIGA_CUSTOM {' + ','.join(f'{value}u' for value in extracted['custom']) + '}',
              *(f'#define RR_AMIGA_VIEW_{axis} {value}' for axis, value in zip('XYWH', view or (0, 0, 0, 0))),
              '#define RR_AMIGA_SLAVE_RESOURCE 300',
              *([f'#define RR_AMIGA_KICKSTART_RESOURCE {KICKSTART_RESOURCE}'] if kickstart is not None else []),
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


# The Kickstart code a game runs: its addresses only (never a byte) are kept, in the private memory beside the observations of
# that image. The words of each instruction come from this conversion's own runs (`<observations>.kick`, as they stand, a slave's
# patches included) and from the player's own image, both in the private work folder, when the steps are written, so the generated
# source and the game built from it belong to that player's image alone.
KICK_ADDRESSES = 'converter-kickstart-addresses.txt'
# The window a 256 KiB Kickstart (1.x) runs in, the one the machine's writable-ROM alias covers; the authored boot ROM below it is
# not the Kickstart.
KICK_WINDOW = (0xFC0000, 0x1000000)


def read_kick_addresses(path: Path) -> set[int]:
    """The Kickstart addresses of an observation (`<observations>.kick`, or the private memory): one hex address a line."""
    found = set()
    for line in Path(path).read_text(encoding='ascii').splitlines():
        pc = int(line, 16)
        if pc & 1 or not KICK_WINDOW[0] <= pc < KICK_WINDOW[1]:
            raise ValueError('Unsupported Kickstart address.')
        found.add(pc)
        if len(found) > 262144:
            raise ConversionError('Amiga Kickstart observation bound exceeded.')
    return found


def read_kick_observation(path: Path) -> set[tuple[int, str]]:
    """(address, words) of a run's `<observations>.kick`, in the private work folder: the Kickstart's instructions as they stood."""
    found = set()
    for line in Path(path).read_text(encoding='ascii').splitlines():
        address, words = line.split()
        pc = int(address, 16)
        if pc & 1 or not KICK_WINDOW[0] <= pc < KICK_WINDOW[1]:
            raise ValueError('Unsupported Kickstart address.')
        if not re.fullmatch('(?:[0-9a-f]{4}){1,8}', words):
            raise ValueError('Invalid Kickstart words.')
        found.add((pc, words))
        if len(found) > 262144:
            raise ConversionError('Amiga Kickstart observation bound exceeded.')
    return found


def kick_samples(addresses: set[int], image: bytes) -> set[tuple[int, str]]:
    """(address, words) of those Kickstart instructions with the words of the player's own image (256 KiB, at $FC0000). Made in
    memory for the generator; never stored. No address (an install without a Kickstart): nothing."""
    if not addresses:
        return set()
    if len(image) & (len(image) - 1) or not image:
        raise ConversionError('Amiga: the Kickstart image has an unexpected size.')
    samples = set()
    for pc in addresses:
        words = image[pc & (len(image) - 1):][:12]
        words = words[:len(words) // 2 * 2]
        if words:
            samples.add((pc, words.hex()))
    return samples


def read_memory_image(path: Path) -> list:
    """The regions a route's run left in memory (`--memory-image`): (start address, bytes), in the conversion's private work folder only."""
    data = Path(path).read_bytes()
    regions, at = [], 0
    while at < len(data):
        start, size = int.from_bytes(data[at:at + 4], 'big'), int.from_bytes(data[at + 4:at + 8], 'big')
        regions.append((start, data[at + 8:at + 8 + size]))
        at += 8 + size
    return regions


def blitter_counts(report: dict) -> dict:
    """The Blitter's counters of a run: native is a specialised routine, interpreted is vAmiga's microprogram. Words of a copy blit, steps of a line blit; a line blit is always interpreted."""
    shapes = [{'bltcon0': f'{con0:03x}', 'bltcon1': f'{con1:02x}', 'line': bool(con1 & 1), 'has_routine': bool(routine), 'native_blits': native_blits, 'native_words': native_words,
               'interpreted_blits': interpreted_blits, 'interpreted_words': interpreted_words}
              for con0, con1, routine, native_blits, native_words, interpreted_blits, interpreted_words in (report.get('blitter') or {}).get('shapes', ())
              if native_blits or interpreted_blits]
    copies = [shape for shape in shapes if not shape['line']]
    lines = [shape for shape in shapes if shape['line']]
    return {'native_blits': sum(shape['native_blits'] for shape in copies), 'native_words': sum(shape['native_words'] for shape in copies),
            'interpreted_blits': sum(shape['interpreted_blits'] for shape in copies), 'interpreted_words': sum(shape['interpreted_words'] for shape in copies),
            'line_blits': sum(shape['interpreted_blits'] for shape in lines), 'line_steps': sum(shape['interpreted_words'] for shape in lines),
            'left_midway': (report.get('blitter') or {}).get('left_midway', 0), 'shapes': shapes}


def generate(project: Path, samples: list, table: Path, images: list = (), rom_images: list = (), reports=()) -> dict:
    """The native code of these observations, of what a sweep reaches from them over these images of memory, and of the Blitter shapes these reports saw (amiga_codegen)."""
    from . import amiga_codegen, m68k_observed
    observed = get_profile('amiga').observed_code
    amiga_codegen.load_opcode_map(table)
    project.mkdir(parents=True, exist_ok=True)
    m68k_observed.write_step_semantics(project, observed.load_bodies(None), observed.prefix, lambda text: text)
    steps = amiga_codegen.write_steps(project, samples, observed=observed, swept=amiga_codegen.sweep(samples, images, observed=observed, rom_images=rom_images),
                                      shapes=amiga_codegen.blit_shapes(reports))
    return {**steps, 'opcode_table_sha256': file_sha256(table)}


# ---------------------------------------------------------------------------------------------------------- replays
# A route the game ends itself (resload_Abort with TDREASON_OK: its own Quit) is a valid reference when it ran this long: every
# later run of that route (native passes, the compressed copy, the state continuation) may end the same way, and its trace and
# resload log, the final Abort included, must still equal the reference's.
MIN_ENDED_ROUTE_FRAMES = 1000


def replay(binary: Path, folder: Path, frames: int, events: Path, *, install: Path | None = None, reference: bool = False,
           observe: bool = False, extra=(), game_may_quit: bool = False) -> dict:
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
        raise ConversionError(f'Amiga replay failed (exit code {result.returncode}): ' + (folder / 'stderr.log').read_text(encoding='utf-8', errors='replace')[-2000:])
    report = json.loads((folder / 'result.json').read_text(encoding='utf-8'))
    if report.get('stopped') and game_may_quit and report.get('quit') and report.get('frames', 0) >= MIN_ENDED_ROUTE_FRAMES:
        report['ended_by_game'] = True
        return report
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


# What a resumed process is not compared on: nothing. vAmiga's snapshot leaves out the state of its sound path (the samplers' pending
# samples, the filters' memory, the sub-sample fraction, the volume ramps); the adapted core saves and restores exactly those, so the
# samples after a load equal an unbroken run's. The tuple stays for a column a later machine may have to exempt.
CONTINUATION_IGNORED = ()


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


def game_entry(source, kick=None) -> Path:
    """The private memory of a game; an install run with a Kickstart keeps its own per Kickstart (its SHA-256's first 16
    digits), so two players' different images never mix observations."""
    entry = library_root('amiga') / source.game_key
    return entry / f'kick-{kick.sha256[:16]}' if kick is not None else entry


def kickstart_fields(kick) -> dict:
    """The report's `kickstart` object: which image the install ran with, by numbers about it (never its bytes)."""
    known = kick.version or {}
    return {'used': True, 'version': known.get('version'), 'os': known.get('os'), 'model': known.get('model'), 'file': kick.file_name,
            'size': kick.size, 'crc16': kick.crc16, 'crc32': kick.crc32, 'sha256': kick.sha256, 'normalised': list(kick.normalisations),
            'player_supplied': True, 'stored_in_library': False, 'shared': False, 'embedded_in_export': True,
            'native': 'native code (Moira\'s code specialised) written from this player\'s own image in the conversion\'s private work folder; what still runs '
                      'on the interpreter is counted apart per route (final_checks.kickstart_interpreted)'}


def place_kickstart(folder: Path, kick) -> None:
    """The normalised image beside the extracted install (this conversion's private work folder), named in install.txt."""
    from . import amiga_kickstart
    (folder / 'kickstart.rom').write_bytes(amiga_kickstart.read_image(kick))
    with open(folder / 'install.txt', 'a', encoding='utf-8') as listing:
        listing.write('kickstart kickstart.rom\n')


# -------------------------------------------------------------------------------------------------------- conversion
def convert(path, **options):
    """One conversion. A conversion that fails after it merged what the library remembered of this install (earlier observations,
    Kickstart addresses) is tried once more without them, as a fresh one: remembered data only ever helps, so a file that is valid
    but wrong must not stop a game. On success the wrong data is dropped (the run's own replaces it in the library) and the report
    says so (`remembered_data`); a second failure is the failure."""
    trace: dict = {}
    try:
        return _convert_once(path, trace=trace, **options)
    except Exception as error:     # a failure anywhere after the remembered data was merged
        if not trace.get('remembered_used'):
            raise
        reason = ' '.join(str(error).split())[:240] or type(error).__name__
        options.get('emit', print)('Amiga: the conversion failed with the remembered observations (' + reason + '); '
                                   'trying once more without them.')
        return _convert_once(path, use_remembered=False, dropped_reason=reason, **options)


def load_remembered(memory: Path, kick, emit) -> tuple[set, set, list]:
    """The (instructions, Kickstart addresses, what was ignored) the library remembers of this install; a file that cannot be read
    (damaged, or past the bounds of an observation) is ignored, never a reason to stop."""
    samples: set = set()
    addresses: set = set()
    ignored: list = []
    if kick is not None and (memory / KICK_ADDRESSES).is_file():
        try:
            addresses |= read_kick_addresses(memory / KICK_ADDRESSES)
        except (OSError, ValueError, ConversionError):
            ignored.append('kickstart addresses')
            emit('Amiga: the remembered Kickstart addresses are unreadable; this conversion uses its own only.')
    if (memory / OBSERVATIONS).is_file():
        try:
            samples |= set(read_observations(memory / OBSERVATIONS))
        except (OSError, ValueError, ConversionError):
            ignored.append('observations')
            emit('Amiga: the remembered observations are unreadable; this conversion uses its own only.')
    return samples, addresses, ignored


def remembered_report(added_instructions: int, added_kick_addresses: int, dropped_reason: str | None, ignored: list | None = None) -> dict:
    """The report's `remembered_data`: what the library's memory added to this conversion, or why it was left out."""
    return {'used': bool(added_instructions or added_kick_addresses), 'added_instructions': added_instructions,
            'added_kickstart_addresses': added_kick_addresses, 'ignored_unreadable': list(ignored or []),
            'dropped_after_failure': dropped_reason is not None,
            **({'failure_with_remembered_data': dropped_reason} if dropped_reason is not None else {})}


def _convert_once(path, *, title=None, output=None, cover=None, use_cover=True, online_cover=True, passes=3, frames=3000, scan_level=None,
                  emit=print, qualification_events=None, use_remembered=True, dropped_reason=None, trace=None, **unused):
    from .amiga import converter_available, read_input
    from . import amiga_whdload
    if not converter_available():
        raise ConversionError('The Amiga converter files are missing from this installation.')
    if unused.get('standard_override') not in (None, 'native', 'auto'):
        raise ConversionError('Amiga timing follows the install (PAL, or NTSC when its archive says so); PAL/NTSC overrides do not apply.')
    started = time.perf_counter()
    level = resolve_scan_level(scan_level)
    source = read_input(path)
    # The player's own Kickstart, for an install that asks for one (slave header or resload_LoadKick): chosen from the
    # Options path by content, checked against the request, copied only into this conversion's work folder and the export.
    from . import amiga_kickstart
    try:
        kick = amiga_kickstart.require(unused.get('amiga_kickstart'), path)
    except ValueError as exc:
        raise ConversionError(str(exc)) from None
    if kick is not None and kick.size != KICKSTART_1X_SIZE:
        raise ConversionError(f'{source.title} asks for a 512 KiB Kickstart (3.x); the Amiga profile runs Kickstart 1.x installs only, for now.')
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
        if kick is not None:
            place_kickstart(work / 'install', kick)
        slave: amiga_whdload.Slave = extracted['install'].slave
        count = max(1000, min(int(frames or 3000), 36000))
        routes = [('main', count, main_route(count, slave.key_exit) if qualification_events is None else list(qualification_events))]
        if level != 'quick':
            routes.append(('explore', count, explore_route(count, slave.key_exit)))
        from .scan_levels import LONG_ROUTES, LONG_ROUTE_FRAMES
        for index in range(LONG_ROUTES.get(level, 0)):
            routes.append((f'long-{index + 1}', LONG_ROUTE_FRAMES, long_route(source.sha256, index, LONG_ROUTE_FRAMES, slave.key_exit)))
        scripts = {name: write_events(work / f'inputs-{name}.txt', events) for name, _, events in routes}
        emit(f'Amiga: fresh reference runs ({len(routes)} route(s) of {count} frames, interpreted 68000).')
        expected = {}
        with timings.phase('reference_runs'):
            for name, frames_, _ in routes:
                expected[name] = replay(reference_player, checks / f'reference-{name}', frames_, scripts[name], install=work / 'install',
                                        reference=True, observe=True, game_may_quit=True, extra=['--memory-image', checks / f'reference-{name}' / 'memory.bin'])
        ended = {name: report['frames'] for name, report in expected.items() if report.get('ended_by_game')}
        for name, frames_ in ended.items():
            emit(f'Amiga: the game ended itself after {frames_} frames of the {name} route (its own Quit): the route ends there.')
        samples = set()
        for name, _, _ in routes:
            samples |= set(read_observations(checks / f'reference-{name}' / 'observations.txt'))
        fresh_samples = len(samples)
        kick_addresses: set[int] = set()
        kick_observed: set[tuple[int, str]] = set()
        kick_image = b''
        if kick is not None:
            kick_image = (work / 'install' / 'kickstart.rom').read_bytes()
            for name, _, _ in routes:
                try:
                    kick_observed |= read_kick_observation(checks / f'reference-{name}' / 'observations.txt.kick')
                except (OSError, ValueError) as error:
                    raise ConversionError(f'Amiga {name}: the Kickstart addresses of the reference run are unreadable: {error}') from error
        memory = game_entry(source, kick)
        remembered = memory / OBSERVATIONS
        kick_addresses = {pc for pc, _ in kick_observed}
        before = (len(samples), len(kick_addresses))
        ignored: list = []
        if use_remembered:
            remembered_samples, remembered_addresses, ignored = load_remembered(memory, kick, emit)
            samples |= remembered_samples
            kick_addresses |= remembered_addresses
        added = (len(samples) - before[0], len(kick_addresses) - before[1])
        if trace is not None and any(added):
            trace['remembered_used'] = True
        if dropped_reason is not None:
            emit('Amiga: the remembered observations are left out of this conversion; its own replace them in the library.')
        mouse_game = False
        from .artwork import prepare_icon
        payload_dir = work / 'payload'
        payload_dir.mkdir(parents=True, exist_ok=True)
        artwork = prepare_icon(payload_dir, source.path, title, payload_dir, explicit=Path(cover) if cover else None, online=online_cover,
                               enabled=use_cover, system_id='amiga', cache_directory=boxart_cache_directory('amiga'), emit=emit)
        view = display_window(expected.values())
        metadata = payload(payload_dir, source, extracted, work / 'install', title, mouse_game, artwork, view,
                           kickstart=work / 'install' / 'kickstart.rom' if kick is not None else None)
        project = work / 'native'
        candidate = generation = None
        results = {}
        for attempt in range(max(1, min(int(passes), 10))):
            timings.begin_pass(attempt + 1)
            with timings.phase('code_generation'):
                images = [read_memory_image(checks / f'reference-{name}' / 'memory.bin') for name, _, _ in routes]
                rom_images = [[(0x1000000 - len(kick_image), kick_image)]] if kick is not None else []
                generation = generate(project, sorted(samples | kick_observed | kick_samples(kick_addresses, kick_image)), table, images, rom_images, expected.values())
                if kick is not None:
                    generation['kickstart_addresses'] = len(kick_addresses)
            emit(f'Amiga: {generation["instructions"]} observed instructions and {generation["swept_instructions"]} swept, in {generation["forms"]} native forms; compiling the game.')
            with timings.phase('compile'):
                candidate = cmake_build(work / 'build', core, emit=emit, generated=project, payload=payload_dir, stamp=stamp)
            run_dir = checks / f'native-{attempt + 1}'
            results = {}
            more = set()
            more_kick: set[tuple[int, str]] = set()
            with timings.phase('native_runs'):
                for name, frames_, _ in routes:
                    folder = run_dir / name
                    folder.mkdir(parents=True, exist_ok=True)
                    exported = folder / candidate.name
                    shutil.copy2(candidate, exported)
                    results[name] = replay(exported, folder, frames_, scripts[name], observe=True, game_may_quit=name in ended)
                    require_same_file(folder / 'trace.tsv', checks / f'reference-{name}' / 'trace.tsv',
                                      lambda: ConversionError(f'Amiga {name}: the native game and the fresh reference diverged; existing export preserved.'))
                    require_same_file(folder / 'resload.log', checks / f'reference-{name}' / 'resload.log',
                                      lambda: ConversionError(f'Amiga {name}: the resload calls differ from the reference; existing export preserved.'))
                    more |= set(read_observations(folder / 'observations.txt'))
                    if kick is not None:
                        try:
                            more_kick |= read_kick_observation(folder / 'observations.txt.kick')
                        except (OSError, ValueError) as error:
                            raise ConversionError(f'Amiga {name}: the Kickstart addresses of the native run are unreadable: {error}') from error
            if not results['main']['nonblack_frames']:
                raise ConversionError('Amiga validation did not produce a usable picture.')
            interpreted = sum(result['interpreted'] for result in results.values())
            if not interpreted or not ((more - samples) or (more_kick - kick_observed)):
                break
            emit(f'Amiga: {interpreted} instructions still interpreted; extending the native coverage.')
            samples |= more
            kick_observed |= more_kick
            kick_addresses |= {pc for pc, _ in more_kick}
        timings.end_passes()
        for name, _, _ in routes:       # The route's memory, the game's and the player's bytes: read for the sweep, not kept.
            (checks / f'reference-{name}' / 'memory.bin').unlink(missing_ok=True)
        # The delivered file: the compressed copy is replayed on every route against the same fresh reference.
        packed = work / ('packed-game.exe' if os.name == 'nt' else 'packed-game')
        delivered = deliver_packed(candidate, packed, 'Amiga', emit)
        state_frame = ended.get('main', routes[0][1]) - 600
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
            return replay(target, folder, frames_, scripts[name], extra=extra, game_may_quit=name in ended)
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
            replay(fresh, restart, 400, scripts['main'], extra=['--state-load-start', '--state-slot', checks / 'packed' / 'main' / 'quick.rrstate'],
                   game_may_quit='main' in ended)
        require(continues(checks / 'packed' / 'main' / 'trace.tsv', restart / 'trace.tsv'),
                lambda: ConversionError('Amiga: the quick state does not continue its saved timeline.'))
        rows = []
        for (name, frames_, events), result in zip(routes, packed_results):
            native = results[name]['native']
            interpreted = results[name]['interpreted']
            folder = checks / 'packed' / name
            rows.append({'route': name, 'frames': frames_, 'native_entries': native, 'native_translated': results[name].get('translated', 0),
                         'native_moira_specialised': native - results[name].get('translated', 0), 'native_swept': results[name].get('swept', 0),
                         'blitter': blitter_counts(results[name]),
                         'interpreted_opcodes': interpreted,
                         'interpreter_percent': 100 * interpreted / max(1, native + interpreted), 'reference_match': True,
                         **({'kickstart_interpreted': (results[name].get('kickstart') or {}).get('interpreted', 0),
                             'kickstart_native': (results[name].get('kickstart') or {}).get('native', 0)} if kick is not None else {}),
                         'packed_reference_match': True, 'resload_match': True, 'resload_calls': result['resload_calls'],
                         'trace_sha256': file_sha256(folder / 'trace.tsv'), **trace_digests(folder / 'trace.tsv'),
                         'steps': len(events), 'script_sha256': file_sha256(scripts[name]),
                         **({'ended_by_game': True, 'frames_run': ended[name]} if name in ended else {}),
                         **({'state_restart_match': True, 'state_frame': state_frame} if name == 'main' else {})})
        sound_routes = [name for (name, _, _), result in zip(routes, packed_results) if result['audible_frames']]
        report = {
            'tool': 'Retro-Recomp', 'version': __version__, 'created_utc': datetime.now(timezone.utc).isoformat(),
            'system': {'id': 'amiga', 'name': 'Commodore Amiga'}, 'status': get_profile('amiga').status, 'private_development_only': False,
            'target': target_id(), 'rom': source.metadata(), 'source_identity': source.sha256, 'qualification_directory': str(checks),
            'source_rom': str(source.path), 'executable': executable_name(title), 'build_executable': str(candidate),
            'toolchain': toolchain_description(),
            'whdload': {'slave': source.slave_path, 'slave_version': slave.version, 'flags': list(slave.flag_names), 'base_mem': slave.base_mem,
                        'exp_mem': slave.exp_mem, 'kickstart_required': kick is not None, 'whdload_used': False,
                        'resload': 'Retro-Recomp MIT resload layer (native/amiga_whdload)', 'video': 'NTSC' if ntsc_install(source) else 'PAL',
                        'data_files': len(extracted['files']), 'key_exit': slave.key_exit,
                        'custom_tooltypes': {f'CUSTOM{k + 1}': value for k, value in enumerate(extracted['custom']) if value}},
            'machine': {'model': 'Amiga 500-class (ECS, 68000), memory laid out as WHDLoad lays it out', 'reference': 'vAmiga Core (MPL-2.0) at its pinned revision, adapted at build time',
                        'boot_rom': 'authored boot ROM (no Kickstart)' if kick is None else
                                    f"authored boot ROM, then the player's Kickstart {kick.label()} in ExpMem and the ROM window (vAmiga WOM)"},
            **({'kickstart': kickstart_fields(kick)} if kick is not None else {}),
            'embedded_rom': True, 'static_sdl': True, 'no_external_firmware_required_after_export': True,
            'native_validation': {'passed': True, 'independent_cpu_oracle': False, **delivered.validation_fields(), 'sound_heard': bool(sound_routes), 'sound_routes': sound_routes,
                                  'scope': 'fresh same-machine reference (interpreted 68000): picture, sound, RAM and CPU registers of every frame, '
                                           'and the resload calls, on bounded joystick, mouse and keyboard scripts',
                                  'generation': generation, 'fresh_observed_instructions': fresh_samples},
            'remembered_data': remembered_report(*added, dropped_reason, ignored),
            'native_coverage': ("instructions seen running from RAM, and the Kickstart instructions of the player-supplied image when the install uses one, as native code per "
                                "opcode, chained, guarded by the latched opcode; anything not seen runs on the counted interpreter"),
            'native_code_is': ("translated C per opcode for the forms the translator knows, with the bus functions of the reference machine; the other forms are Moira's code "
                               "specialised, not a translation (final_checks.native_translated, native_moira_specialised)"),
            'native_forms': {'forms': generation['forms'], 'translated_forms': generation['translated_forms'], 'instructions': generation['native_instructions'],
                             'translated_instructions': generation['translated_instructions'], 'swept_instructions': generation['swept_instructions'],
                             'swept_means': 'reached by a sweep over images of memory, not seen running on a route: the same guard, no route proves them (final_checks.native_swept counts those that ran)'},
            'hardware_devices': [
                {'id': 'blitter', 'kind': 'video_unit', 'mode': 'copy blits of the shapes seen: specialised routines; line blits and other shapes: emulated',
                 'details': {'routines_are': ("vAmiga's Blitter microprogram compiled per shape (BLTCON0 and BLTCON1 without the shift fields), one step per bus slot, in the slots the reference uses: "
                                              "specialised routines, not a translated program"),
                             'shapes_with_a_routine': generation['blitter_shapes'], 'counts': 'final_checks.blitter, by shape, native and interpreted'}},
                {'id': 'agnus_copper', 'kind': 'video_unit', 'mode': 'emulated', 'details': {'by': 'vAmiga', 'copper': 'not compiled (docs/AMIGA.md)'}},
                {'id': 'denise', 'kind': 'video_unit', 'mode': 'emulated', 'details': {'by': 'vAmiga'}},
                {'id': 'paula', 'kind': 'audio_unit', 'mode': 'emulated', 'details': {'by': 'vAmiga'}}],
            'final_checks': rows, **delivered.report_fields(), 'liveness': liveness, 'scan_level': level,
            'advanced_scan': {'enabled': any(name.startswith('long-') for name, _, _ in routes), 'level': level, 'scenario_frames': {name: frames_ for name, frames_, _ in routes},
                              'full_game': False, 'long_routes': [{'scenario': name, 'frames': frames_, 'steps': len(events), 'seed': f'amiga-long:{source.sha256}:{int(name.split("-")[1]) - 1}',
                                                                   'generator': 'computer_routes.long_events'} for name, frames_, events in routes if name.startswith('long-')]},
            'game_states': {'supported': True, 'save_key': 'F8', 'load_key': 'F9', 'fresh_process_verified': True, 'slots': 1,
                            'compatibility': 'the exact install and the build that wrote the state; refused between builds',
                            'schema': 'RRAMIGA-STATE-2', 'machine': 'amiga500', 'rom_identity': source.sha256,
                            'validation': {'process': 'fresh', 'compressed_copy': True, 'saved_at_frame': state_frame,
                                           'continuation_frames': 400, 'continuation_matches': True,
                                           'compared': 'CPU registers, RAM, picture and sound samples of every frame'}},
            'ordinary_saves': {'supported': True, 'scope': 'files the install writes through resload_SaveFile, kept beside the game',
                               'path': 'datas/games/amiga-' + source.sha256 + '/saves',
                               'validation': {'checked_in_this_conversion': False, 'evidence': 'tests/test_amiga_resload.py (SaveFile, the save callback)'}},
            'display': {'shown': 'the display window the game opens (union of DIWSTRT/DIWSTOP)', 'window': list(view) if view else None,
                        'unit': 'picture columns (hires) and lines; the standard window when none was opened',
                        'measured_on': [name for name, _, _ in routes]},
            'input_players': 1, 'peripheral': {'joystick_ports': 1, 'mouse': 'port 1, captured on a click', 'keyboard': 'guest keyboard (Ctrl+Alt+K for full typing)'},
            'video_model': {'standard': 'NTSC' if ntsc_install(source) else 'PAL', 'frameskip': False, 'fps': packed_results[0]['fps'], 'fps_is': 'nominal'},
            'runtime_data': {'directory': 'datas', 'shared_config': 'datas/Retro-Recomp.ini', 'game_directory': 'datas/games/amiga-' + source.sha256},
            'artwork': artwork, 'windows_metadata': metadata,
            'hardware_accuracy_validated': False, 'full_game_validated': False, 'latency_ms': None,
            'qualification_scope': {'controls': 'bounded joystick, mouse and keyboard scripts', 'media': 'WHDLoad installs (.lha), with the player-supplied Kickstart 1.x for the installs that ask for one',
                                    'universal_zero_fallback_claim': False},
            'conversion_wall_seconds': round(time.perf_counter() - started, 3)}
        write_report(output / 'conversion-report.json', report)
        # The private memory: the observations of this conversion's own runs (fresh reference and native), for the next one.
        memory.mkdir(parents=True, exist_ok=True)
        with entry_lock(memory, timeout=1800):
            text = ''.join(f'{pc:06x} {words}\n' for pc, words in sorted(samples))
            (memory / (OBSERVATIONS + '.tmp')).write_text(text, encoding='ascii')
            os.replace(memory / (OBSERVATIONS + '.tmp'), remembered)
            if kick is not None:
                (memory / (KICK_ADDRESSES + '.tmp')).write_text(''.join(f'{pc:06x}\n' for pc in sorted(kick_addresses)), encoding='ascii')
                os.replace(memory / (KICK_ADDRESSES + '.tmp'), memory / KICK_ADDRESSES)
            atomic_json(memory / 'compilation.json', {'schema': 1, 'title': title, 'system': 'amiga', 'game': source.game_key,
                                                      'rom_sha256': source.sha256, 'guarded_variants': len(samples), 'sdk': stamp,
                                                      'observations_sha256': file_sha256(remembered), 'private_development_only': True,
                                                      'fresh_reference_passed': True})
        emit('Amiga: validated standalone game ready.')
        return candidate
