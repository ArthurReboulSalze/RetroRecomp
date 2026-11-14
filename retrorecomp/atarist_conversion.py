"""Atari ST conversion (experimental): a game's floppy images become a standalone game (MIT; the executable it builds is linked with
Hatari, GPL-2.0, and is distributed under the GPL: licenses/hatari.md).

Every conversion starts from a fresh reference run: the game (its disks and the TOS, the player's own or EmuTOS) runs on Hatari,
its 68000 on Hatari's cycle-exact interpreter, every instruction counted. The game executable (the disks, the TOS, the machine and
the host kit) is then replayed headless, copied alone, and its trace (picture, sound, RAM, CPU registers of every frame) must equal
the reference's; so must the compressed copy that is delivered, and a quick state saved by it is loaded by a fresh process.
The instructions the reference runs are observed (pc and words, from RAM, the TOS ROM and the cartridge area) and become native
code (`atarist_codegen`): Hatari's own handler of each opcode compiled for that opcode, chained from instruction to instruction,
guarded by the opcode the CPU has latched, and anything not seen or illegal stays on the
counted interpreter. Nothing is claimed beyond those bounded routes: the hardware fidelity is Hatari's, unmeasured here, and the
routes are scripts, not play.

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
NOTICE_RESOURCE = 203
SOURCES_RESOURCE = 297     # EmuTOS's complete source archive, in a game that boots EmuTOS
TOS_RESOURCE = 298
MARKER_RESOURCE = 299
FIRST_DISK_RESOURCE = 300
OBSERVATIONS = 'converter-observations.txt'
LIVENESS_FIELDS = {'frames': 'frames', 'distinct_pictures': 'distinct_pictures', 'distinct_audio_blocks': 'distinct_sound_blocks',
                   'distinct_ram_states': 'distinct_ram_states', 'distinct_program_counters': 'distinct_program_counters',
                   'picture_changes': 'picture_changes', 'last_picture_change_frame': 'last_picture_change_frame'}
# The chips of the machine, all run by Hatari (no native code, no counter of their own: the report's devices, gate G2). The video and the
# sound unit are the report's own kinds; the others are named in `machine.other_devices`.
HARDWARE_DEVICES = (
    {'id': 'shifter_glue_mmu', 'kind': 'video_unit', 'mode': 'emulated',
     'details': {'by': "Hatari (src/video.c)", 'what': 'the Shifter, the GLUE and the MMU: video timing, the picture and the video counter'}},
    {'id': 'ym2149', 'kind': 'audio_unit', 'mode': 'emulated',
     'details': {'by': "Hatari (src/psg.c, src/sound.c)", 'what': 'the YM2149 sound chip and its port A (drive select, side) and B'}})
OTHER_DEVICES = (
    {'id': 'mfp_68901', 'mode': 'emulated', 'by': 'Hatari (src/mfp.c)', 'what': 'interrupts and the four timers (timer D: machine.timer_d)'},
    {'id': 'ikbd', 'mode': 'emulated', 'by': 'Hatari (src/ikbd.c, src/acia.c)',
     'what': "the keyboard processor's protocol, joysticks and mouse: Hatari's model of the HD6301's commands, not its own program"},
    {'id': 'wd1772_dma', 'mode': 'emulated', 'by': 'Hatari (src/fdc.c; the image readers: floppy.disks and floppy.reader)', 'what': 'the floppy controller and its DMA, with its timing model (fast loading off)'})
MACHINE = 'st'
MEMORY_KB = 1024
# The MFP's timer D (docs/ATARI_ST.md, known limits): Hatari's patch of the TOS's own start of the timer is chosen per game. On `auto`
# the fresh references run with it and run again without it when code outside the TOS shows a sign of using the timer as the TOS
# left it (the detector of the adapted Hatari: signs A, B and C; D is counted and never chooses).
TIMER_D_MODES = ('patched', 'exact')
TIMER_D_CHOICES = ('auto',) + TIMER_D_MODES
TIMER_D_SIGNS = {'A': 'a read of the timer D data register (TDDR)',
                 'B': "timer D's interrupt left enabled and unmasked while the code never wrote TDDR or started the timer",
                 'C': 'timer D started by a write of TCDCR before any write of TDDR',
                 'D': 'a read of TCDCR (counted, never a sign alone)'}
TIMER_D_DECIDING_SIGNS = ('A', 'B', 'C')
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


def long_route(identity: str, index: int, frames: int, disks: int) -> list[tuple[int, int, str, int, int]]:
    """A long varied route (extended level and above), fully determined by the exact game: joystick phases with the fire held at
    times, taps, menu keys, mouse moves and clicks and, in the second route of a game of several disks, one change to the next disk
    (frame 9,000) followed by the keys a player presses when a game asks for it: a route cannot tell when a game asks, and a disk
    changed under a game that did not ask can crash it (Lethal Xcess did), so the first route never changes disk. The model is the
    X68000's (x68000_scan.long_routes); a route does not finish a game."""
    import random
    rng = random.Random(f'atarist-long:{identity}:{index}')
    events = []
    frame = 300
    next_disk, disk = (9000 if index == 1 and disks > 1 else 10 ** 9), 0
    while frame < frames - 200:
        if disks > 1 and frame >= next_disk:
            disk = (disk + 1) % disks
            events.append((frame, frame + 1, 'disk', disk, 0))
            for offset, key in ((30, KEY_SPACE), (90, KEY_RETURN)):
                events.append((frame + offset, frame + offset + 6, 'key', key, 1))
            frame += 200
            next_disk = 10 ** 9
        roll = rng.random()
        if roll < 0.5:                             # move, often firing
            length = rng.randint(20, 160)
            events.append((frame, frame + length, 'joy', rng.choice((0, 1, 2, 3, 3)), 1))
            if rng.random() < 0.6:
                events.append((frame, frame + length, 'joy', 4, 1))
        elif roll < 0.72:                          # fire taps
            events.append((frame, frame + rng.randint(3, 12), 'joy', 4, 1))
        elif roll < 0.84:                          # menu keys: Return, Space, Y, the first digits
            events.append((frame, frame + 6, 'key', rng.choice((KEY_RETURN, KEY_SPACE, 121, 49, 50)), 1))
        else:                                      # mouse move and click
            events.append((frame, frame + 20, 'mouse', rng.choice((0, 1)), rng.choice((-6, -2, 2, 6))))
            if rng.random() < 0.5:
                events.append((frame + 22, frame + 28, 'mouse', 2, 1))
        frame += rng.randint(30, 120)
    return sorted(events)


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


def cmake_build(build: Path, tree: Path, hatari_build: Path, *, generated: Path | None = None, payload: Path | None = None,
                stamp: str = '') -> Path:
    cmake, generator = toolchain()
    run([cmake, '-S', ASSETS / 'native/atarist_machine', '-B', build, '-G', generator, *cmake_target_args(),
         f'-DRR_HATARI_TREE={tree.as_posix()}', f'-DRR_HATARI_BUILD={hatari_build.as_posix()}',
         f'-DCMAKE_PREFIX_PATH={sdl_install().as_posix()}', '-DCMAKE_BUILD_TYPE=Release',
         f'-DRR_ST_GENERATED={generated.as_posix() if generated else ""}',
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


EMUTOS_NOTICE = ('licenses/emutos.md',)


def notice_files(emutos: bool) -> tuple[str, ...]:
    from . import notices
    return (notices.OWN_LICENCE, *notices.notice_files('atarist', EMUTOS_NOTICE if emutos else ()))


FEEDBACK_KIND = 24       # The Atari ST's kind in native/runtime_feedback.h and its profile's feedback_kinds.
TOS_BASE = 0xFC0000      # where a 192 KiB TOS (1.00 to 1.04, EmuTOS's 192 KiB image) sits
MEMORY_IMAGE = 'memory.bin'   # the RAM a reference run leaves at its last frame, for the sweep


def tos_tag(tos: Path) -> str:
    """The TOS a record was made on: the first 32 bits of the image's SHA-256, in hexadecimal (a record of another TOS is not used: the memory differs)."""
    return file_sha256(tos)[:8]


def record_windows(rows, tos: Path, observed) -> tuple[list, dict]:
    """The windows of a player's own record that this conversion may use: made on this TOS, inside the machine's apertures, and, from the TOS ROM, still the bytes of this image.
    RAM windows cannot be checked against a source (loaded or unpacked code): the guard on the latched opcode decides at run time, so a stale one is a routine that never runs."""
    tag = int(tos_tag(tos), 16)
    image = tos.read_bytes()
    kept, counts = [], {'records_read': len(rows), 'kept': 0, 'dropped_other_tos': 0, 'dropped_outside_apertures': 0, 'dropped_rom_mismatch': 0}
    for row in rows:
        pc, data = row.address & 0xffffff, bytes(row.data)
        if row.auxiliary != tag:
            counts['dropped_other_tos'] += 1
            continue
        try:
            observed.check_sample(pc, data[:2].hex())
        except ValueError:
            counts['dropped_outside_apertures'] += 1
            continue
        if pc >= TOS_BASE and image[pc - TOS_BASE:pc - TOS_BASE + len(data)] != data:
            counts['dropped_rom_mismatch'] += 1
            continue
        if 0xFA0000 <= pc < TOS_BASE:      # the cartridge area: no cartridge in this machine
            counts['dropped_outside_apertures'] += 1
            continue
        kept.append((pc, data))
    counts['kept'] = len(kept)
    return kept, counts


def knowledge_block(record, promotion, used, received, sharing: bool) -> dict:
    """The report's `knowledge` section. `shared` says whether the Atari ST is in the sharing at all (`path_profiles.EXPERIMENTAL_SHARED`), not that this conversion shared anything.
    `received`: what the received paths gave (`m68k_media_knowledge.received_use`)."""
    from . import atarist_knowledge
    block = {'machine_status': get_profile('atarist').status, 'shared': sharing, 'record_format': atarist_knowledge.FORMAT, 'cores': atarist_knowledge.engine(),
             'source': 'fresh reference runs of this conversion', 'use': dict(used), 'received': received, 'raw_words_stored': False, 'fresh_validation_required': True}
    if promotion:
        block.update(record_sha256=atarist_knowledge.record_digest(record), paths=promotion['paths'],
                     promotion={key: promotion[key] for key in ('ram', 'other_windows', 'malformed', 'tos', 'truncated')})
    return block


def payload(project: Path, source, disks: list[Path], tos: Path, title: str, mouse_game: bool, sources: Path | None = None,
            autostart: str | None = None, timer_d: str = 'patched') -> dict:
    """The resources of the exported game: its disks and its TOS (as embedded files), the notices and the Windows metadata; with
    EmuTOS, its complete source archive too (`sources`), which the game writes out with --write-sources."""
    from .metadata import write_game_metadata
    from .resources import embed_resources
    project.mkdir(parents=True, exist_ok=True)
    resources = {}
    marker = b'[Retro-Recomp]\0' + source.sha256.encode() + b'\0'
    (project / 'export-marker.bin').write_bytes(marker)
    resources[MARKER_RESOURCE] = project / 'export-marker.bin'
    notices = project / 'notices.txt'
    from .notices import notice_text
    notices.write_text(notice_text('atarist', optional=EMUTOS_NOTICE if sources is not None else ()), encoding='utf-8')
    resources[NOTICE_RESOURCE] = notices
    shutil.copyfile(tos, project / 'tos.bin')
    resources[TOS_RESOURCE] = project / 'tos.bin'
    (project / 'sources.bin').unlink(missing_ok=True)
    if sources is not None:
        shutil.copyfile(sources, project / 'sources.bin')
        resources[SOURCES_RESOURCE] = project / 'sources.bin'
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
              f'#define RR_ST_SOURCES_RESOURCE {SOURCES_RESOURCE if sources is not None else 0}',
              '#define RR_ST_SOURCES_NAME ' + json.dumps(sources.name if sources is not None else ''),
              '#define RR_ST_MACHINE ' + json.dumps(MACHINE), f'#define RR_ST_MEMORY_KB {MEMORY_KB}',
              '#define RR_ST_AUTOSTART ' + json.dumps(autostart or ''), f'#define RR_ST_TIMER_D_EXACT {int(timer_d == "exact")}',
              f'#define RR_ST_TOS_TAG 0x{tos_tag(tos)}u',
              'typedef struct {const char *name;unsigned resource;} RrStPayloadDisk;',
              'static const RrStPayloadDisk rr_st_disks[]={', *rows, '{0,0}};',
              f'#define RR_ST_DISK_COUNT {len(rows)}u',
              'static const volatile unsigned char rr_st_export_marker[]={' + ','.join(str(c) for c in marker) + '};', '#endif']
    (project / 'atarist_payload.h').write_text('\n'.join(header) + '\n', encoding='utf-8')
    # The player's own record (native/runtime_feedback.c): which game it belongs to.
    (project / 'runtime_feedback_config.h').write_text(f'#define RR_FEEDBACK_SYSTEM "atarist"\n#define RR_FEEDBACK_IDENTITY "{source.sha256}"\n', encoding='ascii')
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


def read_observations(path: Path) -> list[tuple[int, str]]:
    """The (pc, words) of an observation file, every one checked against the ST's apertures."""
    observed = get_profile('atarist').observed_code
    samples = set()
    for line in Path(path).read_text(encoding='ascii').splitlines():
        pc, words = line.split()
        pc = int(pc, 16)
        observed.check_sample(pc, words)
        samples.add((pc, words))
        if len(samples) > 1048576:
            raise ConversionError('Atari ST instruction observation bound exceeded.')
    return sorted(samples)


def decoder_lengths(project: Path) -> tuple[Path, Path]:
    """The 68000 decoder of the generator, built once per conversion folder, and its instruction-length table (65,536 opcodes,
    in words): the observations keep each instruction's own words by it."""
    from . import m68k_observed
    engine = ROOT / '.deps/segagenesisrecomp'
    project.mkdir(parents=True, exist_ok=True)
    decode = m68k_observed.build_decoder(project, engine, source=ASSETS / 'native/x68000_native/decode.c', root=ROOT,
                                         target='atarist_decode', name='RetroAtariSTDecode')
    lengths = project / 'opcode-lengths.bin'
    run([decode, '--lengths', lengths], log=project / 'decode.log')
    if len(lengths.read_bytes()) != 65536:
        raise ConversionError('Atari ST: the 68000 instruction length table is invalid.')
    return decode, lengths


def opcode_map(player: Path, folder: Path, disks: list[Path], tos: Path, timer_d: str = 'patched') -> Path:
    """The opcode -> handler table of Hatari's cycle-exact 68000, written by the reference player after one frame."""
    folder.mkdir(parents=True, exist_ok=True)
    table = folder / 'opcode-map.txt'
    events = write_events(folder / 'none.txt', [])
    replay(player, folder, 2, events, disks=disks, tos=tos, extra=['--reference-cpu', '--opcode-map', table], timer_d=timer_d)
    return table


def sweep_images(folders: list, tos: Path) -> list:
    """The images of memory the sweep walks, one per route in the routes' order: the RAM the reference run left at its last frame (`memory.bin`, deleted once read: it is the game's and
    the player's bytes, never kept) and the TOS ROM, as (start address, bytes) regions. A run that wrote no image leaves none."""
    rom = tos.read_bytes()
    images = []
    for folder in folders:
        dump = Path(folder) / MEMORY_IMAGE
        if dump.is_file():
            images.append([(0, dump.read_bytes()), (TOS_BASE, rom)])
            dump.unlink()
    return images


def generate(project: Path, samples: list, table: Path, hatari_build: Path, windows: list = (), lengths: Path | None = None, images: list = ()) -> dict:
    """The native code of these observations (`atarist_codegen`: an instruction per address and opcode, on Hatari's handlers), of the windows of a player's own record, and of what a
    sweep over the images of memory at the routes' end reaches from them."""
    from . import atarist_codegen, m68k_observed
    engine = ROOT / '.deps/segagenesisrecomp'
    observed = get_profile('atarist').observed_code
    atarist_codegen.load_opcode_map(table, hatari_build / 'src/cpu/cpustbl.c')
    project.mkdir(parents=True, exist_ok=True)
    decode = m68k_observed.build_decoder(project, engine, source=ASSETS / 'native/x68000_native/decode.c', root=ROOT,
                                         target='atarist_decode', name='RetroAtariSTDecode')
    bodies = observed.load_bodies(engine)
    m68k_observed.write_step_semantics(project, bodies, observed.prefix, lambda text: text)
    usable = atarist_codegen.native_samples(samples)
    learned, walked = atarist_codegen.walk_records(windows, observed=observed, lengths=lengths.read_bytes()) if windows and lengths else ([], [])
    swept, sweep_info = atarist_codegen.sweep(usable + learned, images, observed=observed, lengths=lengths.read_bytes(), known=walked) if images and lengths else ([], {})
    steps = atarist_codegen.write_steps(project, usable, observed=observed, decode_tool=decode, learned=learned, walked=walked, swept=swept)
    return {'samples': len(samples), 'with_handler': len(usable), 'instructions': steps['instructions'], 'native_instructions': steps['native_instructions'],
            'learned_instructions': steps['learned_instructions'], 'walked_instructions': steps['walked_instructions'], 'swept_instructions': steps['swept_instructions'], 'sweep': sweep_info,
            'forms': steps['forms'], 'pcs': steps['pcs'], 'opcode_table_sha256': file_sha256(table)}


# ---------------------------------------------------------------------------------------------------------- replays
def replay(binary: Path, folder: Path, frames: int, events: Path, *, disks: list[Path] | None = None, tos: Path | None = None,
           observe: bool = False, lengths: Path | None = None, autostart: str | None = None, extra=(), timer_d: str = 'patched') -> dict:
    """One headless run. `timer_d` is the machine's mode this run must have: the reference player is told it, a game's own binary has
    it fixed by its payload, and the run's report must say it."""
    folder.mkdir(parents=True, exist_ok=True)
    args = [str(binary), '--headless', '--frames', str(frames), '--report', str(folder / 'result.json'),
            '--trace', str(folder / 'trace.tsv'), '--input-events', str(events), '--capture', str(folder / 'frame.ppm')]
    if tos is not None:
        args += ['--tos', str(tos), '--machine', MACHINE, '--memory', str(MEMORY_KB), '--reference-cpu']
        for disk in disks or ():
            args += ['--disk', str(disk)]
        if autostart:
            args += ['--autostart', autostart]
        args += ['--timer-d', timer_d]
    if observe:
        args += ['--observations', str(folder / 'observations.txt')]
        if lengths is not None:
            args += ['--opcode-lengths', str(lengths)]
    args += [str(value) for value in extra]
    with (folder / 'stdout.log').open('wb') as out, (folder / 'stderr.log').open('wb') as err:
        result = spawn(args, cwd=folder, timeout=max(600, frames // 4), stdout=out, stderr=err)
    if result.returncode not in (0, 2):
        raise ConversionError('Atari ST replay failed: ' + (folder / 'stderr.log').read_text(encoding='utf-8', errors='replace')[-2000:])
    report = json.loads((folder / 'result.json').read_text(encoding='utf-8'))
    # The reference, the native game and its packed copy are one machine: the comparison cannot see an option that all of them share, so each says what Hatari has set.
    if report.get('timer_d_patch') is not (timer_d == 'patched'):
        raise ConversionError(f"Atari ST: a run whose timer D is not {timer_d}; the reference and the game must run the same machine.")
    if report.get('stopped'):
        raise ConversionError(f'Atari ST: the machine stopped at frame {report.get("frames")}: {report.get("error")}')
    if report.get('frames') != frames:
        raise ConversionError('Atari ST validation returned an incomplete run.')
    return report


def interpreted_sites(result: dict) -> dict:
    """Where the interpreted instructions of a run of the delivered file ran (its report with --interpreted-sites): the sites, most run first,
    each {pc, opcode, count}; how many distinct (pc, opcode) there were; and the instructions beyond the player's table of sites, counted
    without a pc. The counts add up to the run's `interpreted` (gate G3: each interpreted instruction listed with its count)."""
    sites = [{'pc': f'0x{pc:06x}', 'opcode': f'0x{opcode:04x}', 'count': count} for pc, opcode, count in result.get('interpreted_sites') or ()]
    return {'interpreted_sites': sites, 'interpreted_sites_distinct': result.get('interpreted_sites_distinct'),
            'interpreted_sites_unlisted': result.get('interpreted_sites_unlisted'),
            'interpreted_sites_complete': (sum(site['count'] for site in sites) + (result.get('interpreted_sites_unlisted') or 0)
                                           == result.get('interpreted'))}


def timer_d_signs(reports: dict) -> dict:
    """The detector's signs of each route's run report: {route: {letter: {count, frame, pc}}}, the pc as a hexadecimal string."""
    out = {}
    for route, report in reports.items():
        seen = report.get('timer_d_signs') or {}
        out[route] = {letter: {'count': int(seen.get(letter, {}).get('count', 0)), 'frame': int(seen.get(letter, {}).get('frame', 0)),
                               'pc': '0x%06x' % int(seen.get(letter, {}).get('pc', 0))} for letter in TIMER_D_SIGNS}
    return out


def timer_d_decision(choice: str, signs: dict) -> tuple[str, str]:
    """The machine's mode for a game, and why: `patched` and `exact` as asked; `auto` is `exact` when a deciding sign (A, B or C) was
    seen on any route of the references that ran with the patch (the earliest one is named), else `patched`."""
    if choice in TIMER_D_MODES:
        return choice, 'chosen in Options'
    seen = sorted(((entry['frame'], route, letter, entry) for route, letters in signs.items() for letter in TIMER_D_DECIDING_SIGNS
                   for entry in (letters[letter],) if entry['count']), key=lambda item: (item[0], item[1], item[2]))
    if not seen:
        return 'patched', ('no sign that code outside the TOS uses timer D as the TOS left it, on the routes that ran (code they never reach is not looked at)')
    frame, route, letter, entry = seen[0]
    return 'exact', f'sign {letter} ({TIMER_D_SIGNS[letter]}), first at frame {frame}, pc {entry["pc"]}, route {route}'


TIMER_D_LIMITS = {
    'patched': ('when TOS starts the MFP timer D, Hatari starts it far slower than TOS asks (its interrupt is off). A game that uses this timer as TOS left it '
                'sees another rhythm; a game that sets the timer itself is not touched. The frame comparison cannot see this: the reference has the patch too. '
                'The detector looked at the routes that ran only: code they never reach is not looked at.'),
    'exact': ('timer D runs as TOS starts it, at a very high rate with its interrupt off, which costs the host one event every couple of instructions: '
              'the game runs slower on the host than with the patch (1.3 to 1.8 times the host cycles of a main route on the panel, docs/ATARI_ST.md). The detector looked at the '
              'routes that ran only: code they never reach is not looked at.'),
}


def timer_d_report(choice: str, mode: str, reason: str, first_mode: str, signs: dict, final_signs: dict | None) -> dict:
    """`machine.timer_d` of the report: the mode the reference, the native game and its compressed copy ran, why, and the detector's
    signs by route (measured on the first references; when they ran again, on the final machine too)."""
    return {'hatari_option': 'hatari_timerd', 'mode': mode, 'patched': mode == 'patched', 'choice': choice, 'reason': reason,
            'signs': {'measured_on': first_mode, 'routes': signs, 'meaning': TIMER_D_SIGNS, 'deciding': list(TIMER_D_DECIDING_SIGNS)},
            **({'signs_on_final_machine': final_signs} if final_signs is not None else {}),
            'runs_with_it': 'the reference, the native game and its packed copy', 'limit': TIMER_D_LIMITS[mode]}


def trace_rows(path: Path):
    with path.open('r', encoding='ascii', newline='') as stream:
        next(stream)
        for line in stream:
            values = line.rstrip('\r\n').split('\t')
            yield FrameRow(int(values[0]), values[1], sound=values[2], ram=values[3], pc=values[4])


# What every conversion on EmuTOS says (in its report and its messages): no signal tells a game that waits on a still screen from
# a game that EmuTOS cannot run (both stop on one instruction loop with an almost still RAM), so the statement is the same for all.
EMUTOS_NOTE = ('EmuTOS is not Atari\'s TOS: some games written for Atari\'s TOS do not run on it (EmuTOS\'s doc/incompatible.txt '
               'lists the known ones, Turrican II among them). If this game stops, choose your own TOS 1.04 in Options > Atari ST.')


def trace_digests(path: Path) -> dict:
    """One digest per kind of evidence of a route's trace (CPU registers, RAM, picture, sound), over its frames in order."""
    rows = [line.split('\t') for line in Path(path).read_text(encoding='ascii').splitlines()]
    header, body = rows[0], rows[1:]
    registers = [i for i, name in enumerate(header) if name in ('PC', 'SR') or (name[:1] in ('D', 'A') and name[1:].isdigit())]
    columns = {'cpu_hash': registers, 'ram_hash': [header.index('ram')], 'image_hash': [header.index('video')], 'pcm_hash': [header.index('pcm')]}
    return {name: hashlib.sha256('\n'.join(' '.join(row[i] for i in indexes) for row in body).encode('ascii')).hexdigest()
            for name, indexes in columns.items()}


# What a resumed process is not compared on: nothing since the adapted Hatari keeps the sound's own memory in a state (the YM
# filters and the mixing buffer) and the floppy drives' rotation through a restore.
CONTINUATION_IGNORED = ()


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
    """The private memory of a game, one per TOS (the player's image, its SHA-256's first 16 digits, or EmuTOS and its version)."""
    return library_root('atarist') / source.game_key / f'tos-{tos_key}'


# -------------------------------------------------------------------------------------------------------- conversion
def convert(path, *, title=None, output=None, cover=None, use_cover=True, online_cover=True, passes=3, frames=3000, scan_level=None,
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
    from . import atarist_emutos
    try:
        tos = atarist_tos.require(unused.get('atarist_tos')) or atarist_emutos.require(emit)
    except ValueError as exc:
        raise ConversionError(str(exc)) from None
    title = title or source.title
    if any(ord(c) < 32 for c in title) or len(title) > 160:
        raise ConversionError('Invalid Atari ST game title.')
    choice = unused.get('atarist_timer_d') or 'auto'
    if choice not in TIMER_D_CHOICES:
        raise ConversionError(f'Atari ST: timer D is {", ".join(TIMER_D_CHOICES)}, not {choice}.')
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
    dependencies16('md', emit)   # SDL, and the shared 68000 decoder that tells the length and the target of an observed instruction during the conversion
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
        from .scan_levels import LONG_ROUTES, LONG_ROUTE_FRAMES
        for index in range(LONG_ROUTES.get(level, 0)):
            routes.append((f'long-{index + 1}', LONG_ROUTE_FRAMES, long_route(source.sha256, index, LONG_ROUTE_FRAMES, len(source.disks))))
        scripts = {name: write_events(work / f'inputs-{name}.txt', events) for name, _, events in routes}
        emit(f'Atari ST: fresh reference runs ({len(routes)} route(s) of {count} frames, interpreted 68000).')
        expected = {}
        project = work / 'native'
        _, lengths = decoder_lengths(project)
        # A boot that reaches the GEM desktop waits there for its program: the desktop starts the only program of disk 1 by the
        # TOS's own autostart line (atarist_disk). Kept only when the main reference run shows that the boot reached the desktop;
        # otherwise the references run again without it, so a disk that starts by itself runs exactly as without the feature.
        from .atarist_disk import autostart_decision
        desktop = autostart_decision(disks[0].read_bytes(), disks[0].suffix, title)
        autostart, autostart_reason = desktop['program'], desktop['reason']
        candidate_program = autostart
        if autostart and tos.player_supplied and tos.version < 0x0104:
            autostart, autostart_reason = None, f'TOS {tos.version_text()} has no autostart line (TOS 1.04 and EmuTOS have one)'
        start_autostart, start_reason = autostart, autostart_reason

        def reference_runs(mode):
            """Every route's fresh reference on the machine in `mode`; the autostart is dropped (and the run redone) on a route whose boot never reached the desktop."""
            program, reason, results = start_autostart, start_reason, {}
            for name, frames_, _ in routes:
                dump = ['--ram-dump-at', frames_, '--ram-dump', checks / f'reference-{name}' / MEMORY_IMAGE]
                results[name] = replay(reference_player, checks / f'reference-{name}', frames_, scripts[name], disks=disks,
                                       tos=media / 'tos.img', observe=True, lengths=lengths, autostart=program, timer_d=mode, extra=dump)
                if program and not results[name].get('desktop_started'):
                    program, reason = None, 'the boot never reached the desktop (the disk starts by itself)'
                    results[name] = replay(reference_player, checks / f'reference-{name}', frames_, scripts[name], disks=disks,
                                           tos=media / 'tos.img', observe=True, lengths=lengths, timer_d=mode, extra=dump)
            return results, program, reason
        # The machine's timer D (docs/ATARI_ST.md): the references first run with Hatari's patch (or without it when it was asked
        # for); on `auto` they run again without it when code outside the TOS shows a sign of using the timer as the TOS left it.
        first_mode = 'exact' if choice == 'exact' else 'patched'
        with timings.phase('reference_runs'):
            expected, autostart, autostart_reason = reference_runs(first_mode)
            signs = timer_d_signs(expected)
            timer_d, timer_d_reason = timer_d_decision(choice, signs)
            final_signs = None
            if timer_d != first_mode:
                emit(f'Atari ST: timer D runs as the machine has it, without the Hatari patch of it: {timer_d_reason}; the references run again.')
                for name, _, _ in routes:
                    shutil.move(checks / f'reference-{name}', checks / f'reference-patched-{name}')
                    (checks / f'reference-patched-{name}' / MEMORY_IMAGE).unlink(missing_ok=True)   # the game's memory is never kept
                expected, autostart, autostart_reason = reference_runs(timer_d)
                final_signs = timer_d_signs(expected)
        if autostart:
            emit(f'Atari ST: the boot reaches the desktop; the desktop starts {autostart}.')
        samples = set()
        for name, _, _ in routes:
            samples |= set(read_observations(checks / f'reference-{name}' / 'observations.txt'))
        fresh_samples = len(samples)
        fresh_observed = set(samples)
        memory = game_entry(source, tos.key)
        remembered = memory / OBSERVATIONS
        if remembered.is_file():
            try:
                samples |= set(read_observations(remembered))
            except (OSError, ValueError):
                emit('Atari ST: the remembered observations are unreadable; this conversion uses its own only.')
        table = opcode_map(reference_player, checks / 'opcode-map', disks, media / 'tos.img', timer_d=timer_d)
        # The player's own record: windows of what a real session ran on the interpreter, private to this player, never shared. They carry the same guard and count apart; the routes
        # below prove the game as usual.
        from .feedback import ingest, records
        feedback = ingest('atarist', source.sha256, output, emit=emit)
        windows, record_counts = record_windows(records('atarist', source.sha256, FEEDBACK_KIND), media / 'tos.img', get_profile('atarist').observed_code)
        if windows:
            emit(f'Atari ST: {len(windows)} windows of the player\'s own record are used.')
        # The routes' end: images of memory for the sweep (read now, the files deleted: nothing of the game's memory is kept).
        images = sweep_images([checks / f'reference-{name}' for name, _, _ in routes], media / 'tos.img')
        # The shared knowledge of this game (`atarist_knowledge`): rows into the player's own TOS and the standard sectors of the player's own disks, from the bank other players' paths
        # reached, the library's own record and the imported bank. They join the instructions the generator is given, never the observations kept; the native code they make has the same
        # guard as any other, and `knowledge.received` counts them apart (offered, reached by this conversion's own fresh runs, added).
        from . import atarist_knowledge, knowledge, path_profiles
        tos_bytes = (media / 'tos.img').read_bytes()
        disk_bytes = atarist_knowledge.disk_content([(disk.format, data) for disk, data in zip(source.disks, source.disk_data())])
        sharing = 'atarist' in path_profiles.SHARED_SYSTEMS
        received_rows, shared_info = atarist_knowledge.shared_rows(source.game_key, disk_bytes, tos_bytes, qualified=knowledge.qualified_game('atarist', source.game_key),
                                                                   imported=knowledge.imported_game('atarist', source.game_key),
                                                                   library=atarist_knowledge.library_record(source.game_key)) if sharing else ([], {'qualified': 0, 'library': 0, 'imported': 0, 'ignored': {}})
        received = set(received_rows)
        if received:
            emit(f"Atari ST: {len(received)} instructions named by shared or library paths are made native too ({shared_info['qualified']} qualified, {shared_info['imported']} imported, {shared_info['library']} from this library).")
        mouse_game = False
        from .artwork import prepare_icon
        payload_dir = work / 'payload'
        payload_dir.mkdir(parents=True, exist_ok=True)
        artwork = prepare_icon(payload_dir, source.path, title, payload_dir, explicit=Path(cover) if cover else None, online=online_cover,
                               enabled=use_cover, system_id='atarist', cache_directory=boxart_cache_directory('atarist'), emit=emit)
        metadata = payload(payload_dir, source, disks, media / 'tos.img', title, mouse_game,
                           sources=None if tos.player_supplied else tos.source, autostart=autostart, timer_d=timer_d)
        candidate = generation = None
        results = {}
        for attempt in range(max(1, min(int(passes or 3), 10))):
            timings.begin_pass(attempt + 1)
            with timings.phase('code_generation'):
                generation = generate(project, sorted(samples | received), table, hatari_build, windows=windows, lengths=lengths, images=images)
            emit(f'Atari ST: {generation["native_instructions"]} instructions in {generation["forms"]} native forms ({generation["learned_instructions"] + generation["walked_instructions"]} from the player record, '
                 f'{generation["swept_instructions"]} swept); compiling the game.')
            if generation['sweep'].get('capped'):
                emit(f'Atari ST: the sweep stopped at its limit of {generation["sweep"]["limit"]} instructions ({generation["sweep"]["left_at_cap"]} places left unvisited).')
            with timings.phase('compile'):
                candidate = cmake_build(work / 'build', tree, hatari_build, generated=project if generation['native_instructions'] else None,
                                        payload=payload_dir, stamp=stamp)
            run_dir = checks / f'native-{attempt + 1}'
            results = {}
            more = set()
            with timings.phase('native_runs'):
                for name, frames_, _ in routes:
                    folder = run_dir / name
                    folder.mkdir(parents=True, exist_ok=True)
                    exported = folder / candidate.name
                    shutil.copy2(candidate, exported)
                    results[name] = replay(exported, folder, frames_, scripts[name], observe=True, lengths=lengths, timer_d=timer_d)
                    require_same_file(folder / 'trace.tsv', checks / f'reference-{name}' / 'trace.tsv',
                                      lambda: ConversionError(f'Atari ST {name}: the native game and the fresh reference diverged; existing export preserved.'))
                    more |= set(read_observations(folder / 'observations.txt'))
            if not results['main']['nonblack_frames']:
                raise ConversionError('Atari ST validation did not produce a usable picture.')
            interpreted = sum(result['interpreted'] for result in results.values())
            if not interpreted or not (more - samples - received):
                break
            emit(f'Atari ST: {interpreted} instructions still interpreted; extending the native coverage.')
            samples |= more
        timings.end_passes()
        # The delivered file: the compressed copy is replayed on every route against the same fresh reference; the main route
        # saves a quick state on the way (a capture leaves the machine as it was: the trace must still equal the reference).
        packed = work / ('packed-game.exe' if os.name == 'nt' else 'packed-game')
        delivered = deliver_packed(candidate, packed, 'Atari ST', emit)
        state_frame = count - 600
        # Each route of the delivered file also lists where its interpreted instructions ran (pc, opcode, count: gate G3).
        packed_runs = [(name, checks / 'packed' / name, checks / f'reference-{name}', frames_,
                        ['--interpreted-sites', *(['--state-save-at', str(state_frame), '--state-slot', str(checks / 'packed' / name / 'quick.rrstate')]
                                                  if name == 'main' else [])])
                       for name, frames_, _ in routes]

        def replay_copy(run_):
            name, folder, _, frames_, extra = run_
            shutil.rmtree(folder, ignore_errors=True)
            folder.mkdir(parents=True)
            target = folder / candidate.name
            shutil.copy2(packed, target)
            if os.name != 'nt':
                target.chmod(0o755)
            return replay(target, folder, frames_, scripts[name], extra=extra, timer_d=timer_d)
        with timings.phase('packed_replays'):
            packed_results = replay_packed(delivered, packed_runs, replay_copy,
                                           same=lambda run_, result: same_trace(run_[1] / 'trace.tsv', run_[2] / 'trace.tsv'),
                                           mismatch=lambda run_: ConversionError(f'Atari ST {run_[0]}: the compressed executable differs from the fresh reference; existing export preserved.'))
        liveness = [dict(route=name, **report_fields(liveness_summary(trace_rows(folder / 'trace.tsv')), LIVENESS_FIELDS),
                         nonblack_frames=result['nonblack_frames'], audible_frames=result['audible_frames'])
                    for (name, folder, _, _, _), result in zip(packed_runs, packed_results)]
        require_moving_picture(liveness[0], lambda: ConversionError('Atari ST main route: the picture never changed.'))
        from .sega_evidence import route_warnings
        from .atarist_notes import route_stops
        warnings = route_warnings([{'scenario': entry['route'], 'liveness': entry} for entry in liveness]) + route_stops(source.sha256)
        hint = None if tos.player_supplied else EMUTOS_NOTE
        if hint:
            emit('Atari ST: ' + hint)
        # The quick state, loaded by a genuinely fresh process of the delivered file: how it continues is measured and reported
        # (reported, not refused, while experimental).
        restart = checks / 'restart'
        restart.mkdir()
        fresh = restart / candidate.name
        shutil.copy2(packed, fresh)
        with timings.phase('state_checks'):
            replay(fresh, restart, 400, scripts['main'], extra=['--state-load-start', '--state-slot', checks / 'packed' / 'main' / 'quick.rrstate'], timer_d=timer_d)
        resumed = continuation(checks / 'packed' / 'main' / 'trace.tsv', restart / 'trace.tsv')
        rows = []
        for (name, frames_, events), result in zip(routes, packed_results):
            native = results[name]['native']
            interpreted = results[name]['interpreted']
            folder = checks / 'packed' / name
            rows.append({'route': name, 'frames': frames_, 'native_entries': native, 'interpreted_opcodes': interpreted, 'chain_entries': results[name].get('chain_entries'),
                         'native_learned': results[name].get('native_learned'), 'native_walked': results[name].get('native_walked'), 'native_swept': results[name].get('native_swept'),
                         'interpreter_percent': 100 * interpreted / max(1, native + interpreted), 'reference_match': True,
                         'packed_reference_match': True, 'reference_interpreted_opcodes': expected[name]['interpreted'],
                         'trace_sha256': file_sha256(folder / 'trace.tsv'), **trace_digests(folder / 'trace.tsv'),
                         'steps': len(events), 'script_sha256': file_sha256(scripts[name]),
                         **interpreted_sites(result),
                         **({'state_saved_at': state_frame, 'state_restart_match': resumed['matches']} if name == 'main' else {})})
        sound_routes = [name for (name, _, _), result in zip(routes, packed_results) if result['audible_frames']]
        record, promotion = atarist_knowledge.promote(source.game_key, disk_bytes, tos_bytes, sorted(fresh_observed), previous=atarist_knowledge.library_record(source.game_key)) if sharing else (None, None)
        from .m68k_media_knowledge import received_use
        knowledge_report = knowledge_block(record, promotion, shared_info, received_use(received, fresh_observed), sharing)
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
                        'build time, its cycle-exact 68000 mode and its floppy timing model (fast loading off), borders shown; accuracy against hardware '
                        'is not measured here',
                        'timer_d': timer_d_report(choice, timer_d, timer_d_reason, first_mode, signs, final_signs),
                        'other_devices': [dict(entry) for entry in OTHER_DEVICES],
                        'tos': {'used': tos.label(), 'version': tos.version_text(), 'country': tos.country,
                                'pal': tos.pal, 'sha256': tos.sha256, 'player_supplied': tos.player_supplied, 'stored_in_library': False,
                                'shared': False, 'embedded_in_export': True,
                                **({} if tos.player_supplied else
                                   {'fetched_from': 'the EmuTOS project (SourceForge), pinned size and SHA-256',
                                    'source_embedded': atarist_emutos.SOURCE[0], 'source_sha256': atarist_emutos.SOURCE[2],
                                    'licence': 'GPL-2.0-or-later'}),
                                'native': 'its instructions seen running become native code like the RAM code; positions in the '
                                          'TOS are not kept in any shared path'}},
            'tos_note': hint,
            'desktop_autostart': {'program': autostart, 'candidate': candidate_program, 'candidates': desktop['candidates'],
                                  'rule': desktop['rule'], 'reason': autostart_reason,
                                  'mechanism': 'the TOS\'s own autostart line (#Z) in a desktop file Hatari serves in memory; the disk '
                                               'image is not changed' if autostart else None},
            'embedded_rom': True, 'static_sdl': True, 'no_external_firmware_required_after_export': True,
            'native_validation': {'passed': True, 'independent_cpu_oracle': False, **delivered.validation_fields(), 'sound_heard': bool(sound_routes), 'sound_routes': sound_routes,
                                  'scope': 'fresh same-machine reference (interpreted 68000): picture, sound, RAM and CPU registers of every frame, '
                                           'on bounded joystick, mouse and keyboard scripts',
                                  'generation': generation, 'fresh_observed_instructions': fresh_samples},
            'runtime_learning': True, 'runtime_feedback': feedback,
            'player_record': {**record_counts, 'learned_instructions': generation['learned_instructions'], 'walked_instructions': generation['walked_instructions'],
                              'learned_means': "an instruction a player's own session ran on the interpreter: the same guard, no route proves it; on the routes the count is 0 by construction, as what a route runs is observed",
                              'walked_means': 'found by walking a 16-byte window a session noted: it may never have run there, and no route proves it (final_checks.native_walked is 0 on the routes by construction)',
                              'private': True, 'shared': False},
            'knowledge': knowledge_report,
            'sweep': {**generation['sweep'], 'swept_instructions': generation['swept_instructions'], 'page_fill': False,
                      'swept_means': 'reached by a sweep over images of memory taken at the end of the routes, not seen running: the same guard on the latched opcode; on the routes the count is 0 by '
                                     'construction, as what a route runs is observed (final_checks.native_swept)',
                      'private': True, 'shared': False},
            'native_coverage': 'observed instructions (RAM, TOS ROM, cartridge area), those of the player record and those a sweep over the memory at the end of the routes reaches, the last two counted apart, as native code chained from instruction to instruction, guarded by the opcode the CPU has latched: the handler of '
                               'Hatari\'s cycle-exact table for their opcode; the rest on Hatari\'s interpreter, counted',
            'hardware_devices': [dict(entry, details=dict(entry['details'])) for entry in HARDWARE_DEVICES],
            'final_checks': rows, **delivered.report_fields(), 'liveness': liveness, 'route_warnings': warnings, 'scan_level': level,
            'game_states': {'supported': True, 'save_key': 'F8', 'load_key': 'F9', 'fresh_process_verified': resumed['matches'], 'slots': 1,
                            'compatibility': 'the exact game, TOS and build that wrote the state; refused between builds',
                            'schema': 'RRATARIST-STATE-1', 'machine': 'atarist', 'rom_identity': source.sha256,
                            'validation': {'process': 'fresh', 'compressed_copy': True, 'saved_at_frame': state_frame,
                                           'continuation_frames': resumed['frames'], 'continuation_matches': resumed['matches'],
                                           'equal_frames': resumed['equal_frames'], 'differing_columns': resumed['differing_columns'],
                                           'saving_leaves_the_timeline': True,
                                           'compared': 'CPU registers, RAM, picture and sound samples of every frame'}},
            'ordinary_saves': {'supported': True, 'scope': 'the sectors a game writes to its floppy, whatever the image format, are kept in '
                               'datas/games/atarist-<game>/disk-writes.bin beside the quick state; the image is never changed; a format (write '
                               'track) is not kept', 'routes_with_writes': {name: result.get('disk_writes', 0) for (name, _, _), result in
                                                                            zip(routes, packed_results) if result.get('disk_writes')}},
            'input_players': 2, 'peripheral': {'joystick_ports': 2, 'mouse': 'port 0, captured on a click',
                                               'keyboard': 'guest keyboard (Ctrl+Alt+K for full typing)'},
            'video_model': {'standard': 'PAL' if tos.pal else 'NTSC', 'frameskip': False, 'fps': packed_results[0]['fps']},
            'runtime_data': {'directory': 'datas', 'shared_config': 'datas/Retro-Recomp.ini', 'game_directory': 'datas/games/atarist-' + source.sha256},
            'artwork': artwork, 'windows_metadata': metadata,
            'hardware_accuracy_validated': False, 'full_game_validated': False, 'latency_ms': None,
            'licence': {'executable': 'GPL-2.0 (linked with Hatari; Retro-Recomp\'s own files keep their MIT notice)',
                        'notices': list(notice_files(not tos.player_supplied))},
            'qualification_scope': {'controls': 'bounded joystick, mouse and keyboard scripts', 'media': 'floppy images (IPF, STX, MSA, ST)',
                                    'universal_zero_fallback_claim': False},
            'conversion_wall_seconds': round(time.perf_counter() - started, 3)}
        write_report(output / 'conversion-report.json', report)
        # The private memory: the observations of this conversion's own runs (fresh reference and native), for the next one.
        memory.mkdir(parents=True, exist_ok=True)
        with entry_lock(memory, timeout=1800):
            (memory / (OBSERVATIONS + '.tmp')).write_text(''.join(f'{pc:06x} {words}\n' for pc, words in sorted(samples)), encoding='ascii')
            os.replace(memory / (OBSERVATIONS + '.tmp'), remembered)
            atomic_json(memory / 'compilation.json', {'schema': 1, 'title': title, 'system': 'atarist', 'game': source.game_key,
                                                      'rom_sha256': source.sha256, 'tos_sha256': tos.sha256, 'tos': tos.label(),
                                                      'guarded_variants': len(samples),
                                                      'sdk': stamp, 'observations_sha256': file_sha256(remembered), 'private_development_only': True, 'fresh_reference_passed': True,
                                                      **({'record': record, 'record_format': atarist_knowledge.FORMAT, 'cores': atarist_knowledge.engine(), 'record_source': 'fresh reference runs'} if record else {})})
        emit('Atari ST: validated standalone game ready.')
        return candidate
