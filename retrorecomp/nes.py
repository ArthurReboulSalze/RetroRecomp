"""NES conversion using the pinned NESRecomp cycle backend.

The dependency is PolyForm Noncommercial, independently of RetroRecomp's MIT
code. Each generated game retains the exact license in a Windows resource.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import re
import shutil
import tempfile
import time
import zlib
import wave
from typing import Callable

from . import __version__, timings
from .conversion_common import (check_run_budget, convert_single, prepare_game_icon, resolve_scan_level,
                                write_if_changed)
from .core import ConversionError, dependencies, executable_name, run, serialized_setup, slug, toolchain
from .toolchain import describe as toolchain_description
from .library import atomic_text, entry_lock, library_root
from .report_schema import write_report
from .nes_build import object_stamps, prepare_native, preserve_inputs
from .knowledge import record_for
from .metadata import write_game_metadata
from .nes_codegen import prepare_compiler
from .nes_runtime import prepare_host
from .nes_catalog import zapper_game
from .nes_ram import read_sites as ram_sites, shared_sites, trace_text
from .paths import ROOT, ASSETS, data_directory, games_root, boxart_cache_directory
from .systems import archive_rom

ENGINE_URL = "https://github.com/mstan/nesrecomp.git"
ENGINE_REV = "1b0c621a927db17afa9723bf456a89ad15809907"
MAX_ROM_BYTES = 128 * 1024 * 1024 + 528
SEED = re.compile(r"^4k:([0-9A-Fa-f]{1,4}):([89A-Fa-f][0-9A-Fa-f]{3})(?:\s|$)", re.I)
SUMMARY = re.compile(r"mode=native frames=(\d+) cycles=(\d+) native_cycles=(\d+)")
INTERPRETED = re.compile(r"interpreted: ROM (\d+) .*?RAM (\d+)")
OTHER = re.compile(r"\$2000-\$7FFF (\d+)")


@dataclass(frozen=True)
class NesRom:
    path: Path
    data: bytes
    crc32: int
    sha256: str
    mapper: int
    nes2: bool
    video_standard: str
    timing_source: str = 'default_guess'
    system_id: str = "nes"

    def metadata(self) -> dict:
        return {"name": self.path.name, "bytes": len(self.data),
                "crc32": f"{self.crc32:08X}", "sha256": self.sha256,
                "mapper": self.mapper, "nes2": self.nes2,
                "video_standard": self.video_standard, "timing_source": self.timing_source,
                "system_id": self.system_id}


def _nes_size(low: int, high: int, unit: int) -> int:
    if high == 15:
        return (1 << (low >> 2)) * ((low & 3) * 2 + 1)
    return ((high << 8) | low) * unit


def read_nes_rom(path: Path) -> NesRom:
    path = path.resolve()
    suffix = path.suffix.casefold()
    if suffix == '.zip':
        archived_suffix, data = archive_rom(path)
        if archived_suffix not in ('.nes', '.bin', '.rom'):
            raise ConversionError('This ZIP contains no NES cartridge.')
    elif suffix in ('.nes', '.bin', '.rom'):
        with path.open('rb') as source:
            data = source.read(MAX_ROM_BYTES + 1)
    else:
        raise ConversionError('Choose a NES .nes, .bin, .rom or single-ROM ZIP.')
    if len(data) < 16 or len(data) > MAX_ROM_BYTES or data[:4] != b'NES\x1a':
        raise ConversionError('Not a valid iNES/NES 2.0 cartridge header or ROM too large.')
    header = data[:16]
    nes2 = (header[7] & 12) == 8
    if nes2:
        prg = _nes_size(header[4], header[9] & 15, 16384)
        chr_ = _nes_size(header[5], header[9] >> 4, 8192)
    else:
        prg, chr_ = header[4] * 16384, header[5] * 8192
    expected = 16 + (512 if header[6] & 4 else 0) + prg + chr_
    if not prg or expected != len(data):
        raise ConversionError(f'NES header declares {expected} bytes; file contains {len(data)}.')
    mapper = (header[6] >> 4) | (header[7] & 0xF0)
    if nes2:
        mapper |= (header[8] & 15) << 8
    if nes2:
        standard = {0: 'ntsc', 1: 'pal', 2: 'multi', 3: 'dendy'}[header[12] & 3]
        timing_source = 'nes2_header'
    elif header[9] == 1 and not any(header[10:16]):
        standard, timing_source = 'pal', 'ines_header'
    else:
        # A zero in an old iNES timing byte often means unspecified. Region
        # tags are a useful hint, not a verified cartridge database identity.
        tags = ' '.join(a or b for a, b in re.findall(r'\(([^)]*)\)|\[([^]]*)\]', path.stem))
        pal = re.search(r'\b(Europe|Australia|France|Germany|Italy|Spain|Sweden|Finland|PAL)\b', tags, re.I)
        ntsc = re.search(r'\b(USA|Japan|Canada|NTSC|World)\b', tags, re.I)
        standard = 'pal' if pal and not ntsc else 'ntsc'
        timing_source = 'filename_region' if pal or ntsc else 'default_guess'
    return NesRom(path, data, zlib.crc32(data), hashlib.sha256(data).hexdigest(),
                  mapper, nes2, standard, timing_source)


@serialized_setup
def _dependencies(emit: Callable[[str], None]) -> tuple[Path, Path, Path, Path, str]:
    from .platforms import require_backend
    require_backend('nes')
    cmake, generator = toolchain()
    from .platforms import sdl_install, sdl_library
    sdl = sdl_install()
    if not (sdl / sdl_library()).is_file():
        _, sdl, cmake, generator = dependencies(emit)
    engine = ROOT / '.deps/nesrecomp'
    if not engine.exists():
        emit('Downloading pinned NESRecomp (PolyForm Noncommercial)…')
        run(['git', 'clone', ENGINE_URL, engine], timeout=600)
    if run(['git', '-C', engine, 'status', '--porcelain', '--untracked-files=no']).strip():
        raise ConversionError('The cached NES engine has local changes; refusing to replace them.')
    revision = run(['git', '-C', engine, 'rev-parse', 'HEAD']).strip()
    if revision != ENGINE_REV:
        emit('Checking out the pinned NESRecomp revision…')
        run(['git', '-C', engine, 'fetch', '--depth', '1', 'origin', ENGINE_REV], timeout=600)
        run(['git', '-C', engine, 'checkout', '--detach', ENGINE_REV])
    if run(['git', '-C', engine, 'rev-parse', 'HEAD']).strip() != ENGINE_REV:
        raise ConversionError('Unexpected NESRecomp revision.')
    compiler = prepare_compiler(engine, cmake, generator, emit)
    return engine, compiler, sdl, cmake, generator


def _seed_sites(path: Path) -> set[str]:
    try:
        if path.stat().st_size > 16 * 1024 * 1024:
            raise ConversionError('NES entry trace exceeds its size limit.')
        with path.open(encoding='ascii') as stream:
            return {f'4k:{int(match[1], 16):X}:{int(match[2], 16):04X}' for line in stream
                    if (match := SEED.match(line))}
    except FileNotFoundError:
        return set()


def _record_sites(rom, record: dict) -> tuple[set[str], set[tuple[int, int]]]:
    return ({f'4k:{bank:X}:{address:04X}' for bank, address in record.get('rom_entries', [])
             if bank < len(rom.data) // 4096 and 0x8000 <= address <= 0xffff},
            shared_sites(rom, record))


def _row_sites(rom, rows) -> tuple[set[str], set[tuple[int, int]]]:
    """feedback.nes_sites for the given rows only."""
    entries, guards = set(), set()
    prg_start = 16 + (512 if rom.data[6] & 4 else 0)
    prg_bytes = _nes_size(rom.data[4], rom.data[9] & 15, 16384) if rom.nes2 else rom.data[4]*16384
    for row in rows:
        pc, bank = row.address, row.auxiliary
        if row.kind == 3 and 0x8000 <= pc <= 0xffff and len(row.data) == 1:
            offset = bank*4096 + (pc & 4095)
            if offset < prg_bytes and prg_start + offset < len(rom.data) and rom.data[prg_start+offset:prg_start+offset+1] == row.data:
                entries.add(f'4k:{bank:X}:{pc:04X}')
        if row.kind == 4 and (pc < 0x2000 or 0x6000 <= pc <= 0xffff) and len(row.data) == 1:
            guards.add((pc, row.data[0]))
    return entries, guards


def _offered_only(rom, previous: Path) -> tuple[set[str], set[tuple[int, int]]]:
    """Sites that only other players offer this ROM (imported bank, shared
    observations): neither this player's library or gameplay rows nor the
    qualified bank. They guide the conversion; the library keeps them only
    once a conversion observes them."""
    from .feedback import Observation, records
    from .knowledge import bundled_record, imported_observations, imported_record
    rows = [Observation(kind, address, auxiliary, bytes(rom.data[offset:offset + length]))
            for kind, address, auxiliary, length, offset in imported_observations('nes', rom.sha256)]
    rom_sites, ram = _record_sites(rom, imported_record('nes', rom.sha256))
    observed = _row_sites(rom, rows)
    own = _row_sites(rom, records('nes', rom.sha256))
    bundled = _record_sites(rom, bundled_record('nes', rom, ENGINE_REV))
    return ((rom_sites | observed[0]) - own[0] - bundled[0] - _seed_sites(previous),
            (ram | observed[1]) - own[1] - bundled[1] - ram_sites(previous))


def _remember_seed(seed: Path, previous: Path, offered=(frozenset(), frozenset())) -> None:
    # Other conversions may have learned additional paths since this one began.
    # Merge under the same per-ROM lock, then replace only the complete trace.
    # Hints only offered by other players stay out unless this player had them already.
    incoming_rom, incoming_ram = _seed_sites(seed) - offered[0], ram_sites(seed) - offered[1]
    with entry_lock(previous.parent):
        rom_entries = _seed_sites(previous) | incoming_rom
        ram_entries = ram_sites(previous) | incoming_ram
        from .nes_ram import MAX_GUARDS
        if len(ram_entries) > MAX_GUARDS:
            raise ConversionError('Too many NES guarded RAM entry variants.')
        text = trace_text(rom_entries, ram_entries)
        if len(text) > 16 * 1024 * 1024:
            raise ConversionError('NES entry trace exceeds its size limit.')
        atomic_text(previous, text)


def _generated_source(project: Path) -> Path:
    cycle = project / 'cycle'
    manifest = (cycle / 'sources.cmake').read_text(encoding='utf-8')
    generated = next((path for path in cycle.glob('*/generated/game_cyc.c')
                      if path.as_posix() in manifest), None)
    if generated is None:
        raise ConversionError('NES compiler generated no selected native source.')
    return generated


def _native_rom_positions(project: Path, mapper: int) -> tuple[int, int] | None:
    generated = _generated_source(project)
    log = (generated.parent.parent / 'codegen.log').read_text(encoding='utf-8')
    coverage = re.search(r'Native PRG ROM positions: (\d+)/(\d+)', log)
    if coverage is None:
        raise ConversionError('NES compiler did not report bank-independent ROM coverage.')
    return int(coverage[1]), int(coverage[2])


def memory_summary(rom: NesRom) -> dict:
    directory = library_root('nes') / rom.sha256 / ENGINE_REV
    return {'system': 'nes', 'sha256': rom.sha256,
            'engine_revision': ENGINE_REV,
            'observed_rom_entries': len(_seed_sites(directory / 'cycle-seeds.trace')),
            'guarded_ram_entries': len(ram_sites(directory / 'cycle-seeds.trace')),
            'directory': str(directory)}


def list_memory() -> list[dict]:
    root = library_root('nes')
    rows = []
    for directory in root.glob('*/' + ENGINE_REV):
        if len(directory.parent.name) != 64:
            continue
        entries = len(_seed_sites(directory / 'cycle-seeds.trace'))
        if entries:
            rows.append({'sha256': directory.parent.name, 'entries': entries})
    return sorted(rows, key=lambda row: row['sha256'])


def _run_probe(command: list[str | Path], work: Path) -> str:
    # The standalone host stores battery RAM beside its EXE, regardless of cwd.
    # Each invocation needs a clean cartridge, including the reference run.
    # Copying into a private directory also leaves any existing saves untouched
    # and works for mapper-specific NVRAM without guessing its layout here.
    with tempfile.TemporaryDirectory(prefix='nes-probe-', dir=work) as temporary:
        executable = Path(temporary) / Path(command[0]).name
        shutil.copy2(command[0], executable)
        return run([executable, *command[1:]], cwd=work,
                   log=work / 'validation.log', timeout=600)


def _probe(exe: Path, work: Path, scenario: str, frames: int, seed: Path,
           script: Path | None = None, *, differential: bool = False) -> dict:
    command: list[str | Path] = [exe, '--frames', str(frames)]
    if script:
        command += ['--input', script]
    command += ['--miss-log', seed]
    if differential:
        # Exercise synthesis as well as CPU state. Both runs start fresh and
        # use the same clock/rate; delivery to the sound device is separate.
        for kind in ('native', 'reference'):
            for suffix in ('hash', 'wav'):
                (work / f'{scenario}-{kind}.{suffix}').unlink(missing_ok=True)
        command += ['--hash-out', work / f'{scenario}-native.hash',
                    '--wav-out', work / f'{scenario}-native.wav']
    output = _run_probe(command, work)
    summary, interpreted = SUMMARY.search(output), INTERPRETED.search(output)
    if not summary or int(summary[1]) != frames:
        raise ConversionError(f'NES {scenario} probe did not complete {frames} frames.\n{output[-1000:]}')
    total, native = int(summary[2]), int(summary[3])
    if not interpreted and native != total:
        raise ConversionError(f'NES {scenario} did not report its interpreted cycles.')
    rom_cycles, ram_cycles = (int(interpreted[1]), int(interpreted[2])) if interpreted else (0, 0)
    other = OTHER.search(output)
    other_cycles = int(other[1]) if other else 0
    interpreter_cycles = rom_cycles + ram_cycles + other_cycles
    non_dispatch_cycles = total - native - interpreter_cycles
    if non_dispatch_cycles < 0:
        raise ConversionError(f'NES {scenario} reported inconsistent native/interpreter cycle totals.')
    if differential:
        reference_command: list[str | Path] = [exe, '--frames', str(frames), '--interp-only',
            '--hash-out', work / f'{scenario}-reference.hash',
            '--wav-out', work / f'{scenario}-reference.wav']
        if script:
            reference_command += ['--input', script]
        _run_probe(reference_command, work)
        native_hash = (work / f'{scenario}-native.hash').read_bytes()
        reference_hash = (work / f'{scenario}-reference.hash').read_bytes()
        if native_hash != reference_hash or len(native_hash.splitlines()) != frames:
            raise ConversionError(f'NES {scenario}: native and internal interpreter frame states differ.')
        captures = []
        for kind in ('native', 'reference'):
            path = work / f'{scenario}-{kind}.wav'
            try:
                with wave.open(str(path), 'rb') as wav:
                    if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getcomptype()) != (1, 2, 48000, 'NONE'):
                        raise ValueError('Unexpected NES PCM format')
                    pcm = wav.readframes(wav.getnframes())
                    if not pcm or len(pcm) != wav.getnframes() * 2:
                        raise ValueError('Empty or truncated NES PCM')
                    captures.append(pcm)
            except (OSError, EOFError, ValueError, wave.Error) as exc:
                raise ConversionError(f'NES {scenario}: missing or invalid {kind} audio capture.') from exc
        if captures[0] != captures[1]:
            raise ConversionError(f'NES {scenario}: native and internal interpreter audio samples differ.')
        # Keep the numeric evidence, not megabytes of successful game audio.
        for kind in ('native', 'reference'):
            (work / f'{scenario}-{kind}.wav').unlink()
    return {'scenario': scenario, 'frames': frames, 'cycles': total,
            'native_cycles': native, 'native_percent': 100 * native / total if total else 0,
            'interpreter_rom_cycles': rom_cycles, 'interpreter_ram_cycles': ram_cycles,
            'interpreter_other_cycles': other_cycles,
            'interpreter_cycles': interpreter_cycles,
            'interpreter_percent': 100 * interpreter_cycles / total if total else 0,
            'non_dispatch_cycles': non_dispatch_cycles,
            'internal_differential': differential,
            'audio_pcm_match': True if differential else None,
            'audio_samples': len(captures[0]) // 2 if differential else None,
            'audio_pcm_sha256': hashlib.sha256(captures[0]).hexdigest() if differential else None}


def _write_probe_scripts(project: Path, frames: int, *, advanced: bool = False, play_left: bool = True,
                         long_routes=()) -> dict[str, Path | None]:
    """Keep exercising inputs after boot instead of idling for most of a test.

    ``long_routes`` are reproducible pseudo-random routes (``random_routes``)
    written with their own frame budget; see ``_scenario_frames``."""
    scripts: dict[str, Path | None] = {'boot': None}
    # Different Start timings cover titles that need a few seconds to become
    # interactive. Never pulse Start repeatedly: many games use it to pause.
    for name, direction, start in (('play_right', 'RIGHT', 180),
                                    ('play_left', 'LEFT', 20)):
        if name == 'play_left' and not play_left:
            continue
        move = start + 120
        held = direction + '+B'
        events = {start: 'START', start + 12: '-', move: held}
        for frame in range(move + 60, frames, 64):
            events[frame] = held + '+A'
            events[frame + 20] = held
        script = project / (name.replace('_', '-') + '.input')
        script.write_text(''.join(f'{frame} {keys}\n' for frame, keys in sorted(events.items())
                                  if frame < frames), encoding='ascii')
        scripts[name] = script
    if advanced:
        sequences = {
            'menu_confirm': {60: 'START', 72: '-', 240: 'A', 252: '-'},
            'select_confirm': {120: 'SELECT', 132: '-', 180: 'START', 192: '-'},
            'varied_play': {20: 'START', 32: '-'},
        }
        for name, events in sequences.items():
            if name == 'varied_play':
                patterns = ('RIGHT+B', 'RIGHT+A+B', 'RIGHT', 'UP+A', 'LEFT+B',
                            'DOWN', 'RIGHT+A', '-', 'B', 'A')
                for i, frame in enumerate(range(180, frames, 90)):
                    events[frame] = patterns[i % len(patterns)]
                    events[frame + 24] = 'RIGHT+B' if i % 3 == 0 else '-'
            else:
                # Released confirmations/cancellations and vertical choices
                # reach menu/dialogue paths missed by held right/left input.
                for i, frame in enumerate(range(360, frames, 120)):
                    events[frame] = ('A', 'DOWN', 'A', 'UP', 'B', 'RIGHT')[i % 6]
                    events[frame + 16] = '-'
                if name == 'select_confirm':
                    # Player 2 gets separate input; simultaneous opposing
                    # directions are never submitted to either controller.
                    second = {240: '2:START', 252: '2:-', 480: '2:RIGHT+B',
                              960: '2:A', 984: '2:-'}
                    extra = ''.join(f'{frame} {keys}\n' for frame, keys in second.items() if frame < frames)
                else:
                    extra = ''
            script = project / (name.replace('_', '-') + '.input')
            rows = [f'{frame} {keys}\n' for frame, keys in events.items() if frame < frames]
            if name == 'select_confirm':
                rows += extra.splitlines(keepends=True)
            rows.sort(key=lambda row: int(row.split()[0]))
            script.write_text(''.join(rows), encoding='ascii')
            scripts[name] = script
    if long_routes:
        from .random_routes import write_route
        for route in long_routes:
            scripts[route.name.replace('-', '_')] = write_route(route, project)
    return scripts


def _scenario_frames(scripts: dict, frames: int, long_routes=()) -> dict[str, int]:
    """Frame budget per scenario: the shared limit, or a long route's own."""
    budgets = {name: frames for name in scripts}
    for route in long_routes:
        budgets[route.name.replace('-', '_')] = route.frames
    return budgets


def convert_nes(rom_path: Path, *, title: str | None = None, output: Path | None = None,
                profile: Path | None = None, passes: int = 3, frames: int = 3600,
                backend: str = 'banked', language: str = 'en', cover: Path | None = None,
                boxart_dir: Path | None = None, online_cover: bool = True,
                use_cover: bool = True, icon_tags: bool = True,
                nes_advanced_scan: bool = False, scan_level: str | None = None,
                standard_override: str | None = None,
                emit: Callable[[str], None] = print) -> Path:
    from .scan_levels import legacy_level, nes_budget
    level = resolve_scan_level(scan_level, legacy_level('nes', nes_advanced_scan=bool(nes_advanced_scan)))
    if output is None:
        return convert_single(rom_path, games_root(), title=title, cover=cover, profile=profile, passes=passes,
            frames=frames, backend=backend, language=language, boxart_dir=boxart_dir,
            online_cover=online_cover, use_cover=use_cover, icon_tags=icon_tags,
            scan_level=level,
            standard_override=standard_override, emit=emit)
    if profile is not None:
        raise ConversionError('NES uses verified ROM traces, not Sega TOML profiles.')
    check_run_budget(passes, frames, 'Choose 1–10 passes and 1–10000 frames per test.')
    started = time.perf_counter()
    rom = read_nes_rom(rom_path)
    if rom.video_standard == 'dendy' or standard_override not in (None, 'ntsc', 'pal'):
        raise ConversionError('Choose NTSC or PAL for NES; Dendy timing is not supported.')
    standard = standard_override or ('ntsc' if rom.video_standard == 'multi' else rom.video_standard)
    gun = zapper_game(rom.data, rom.path.name)
    title = title or re.sub(r'\s*\([^)]*\)', '', rom.path.stem).strip()
    project = ROOT / '.build' / f'nes_{slug(title)}_{rom.sha256[:12]}_{ENGINE_REV[:8]}_{standard}'
    project.mkdir(parents=True, exist_ok=True)
    destination = output.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    from .feedback import ingest, nes_sites
    gameplay_feedback = ingest('nes', rom.sha256, destination, emit=emit)
    feedback_rom, feedback_ram = nes_sites(rom)
    emit(f'NES ROM: {title}, {len(rom.data) // 1024} KB, mapper {rom.mapper}, CRC32 {rom.crc32:08X}.')
    emit(f'NES video timing: {standard.upper()} ({"manual" if standard_override else rom.timing_source}).')
    if gun:
        emit('NES Zapper enabled: mouse aim and trigger on controller port 2.')
    artwork = prepare_game_icon(project, rom.path, title,
        boxart_dir or ROOT / 'BoxArt/Nintendo NES', explicit=cover,
        online=online_cover, enabled=use_cover, cache_directory=boxart_cache_directory('nes'),
        tags=('shooting',) if gun and icon_tags else (), system_id='nes', emit=emit)
    engine, compiler, sdl, cmake, generator = _dependencies(emit)
    write_if_changed(project / 'rom.nes', rom.data)
    with preserve_inputs(project):
        prepare_host(project, engine, rom.sha256, title, standard=standard, zapper=gun, mapper=rom.mapper)
        metadata = write_game_metadata(project, title, executable_name(title), light_phaser=False,
            icon=artwork['embedded'], standard=standard, system_id='nes', zapper=gun)
        notice = 'NES executable: component license notices.\n\n'
        for component, source in [('RetroRecomp', ASSETS / 'LICENSE'),
                                  ('NESRecomp', engine / 'LICENSE'),
                                  ('emu2413', engine / 'runner/cyc/vendor/emu2413/LICENSE'),
                                  ('xBR', ASSETS / 'licenses/xbr.md'), ('Noto fonts', ASSETS / 'licenses/Noto.md'),
                                  ('SDL2', ASSETS / 'licenses/SDL2.md'),
                                  ('Portable compiler runtime', ASSETS / 'licenses/llvm-mingw.md')]:
            notice += f'## {component}\n\n' + source.read_text(encoding='utf-8') + '\n\n'
        (project / 'game_legal.md').write_text(notice, encoding='utf-8')
        (project / 'game_identity.bin').write_bytes(b'[Retro-Recomp]\0' + rom.sha256.encode('ascii') + b'\0')
        with (project / 'game_resources.rc').open('a', encoding='utf-8') as resource:
            resource.write('102 RCDATA "game_legal.md"\n103 RCDATA "rom.nes"\n'
                           '104 RCDATA "game_identity.bin"\n')
    from .resources import embed_resources
    embed_resources(project, {102:project/'game_legal.md',103:project/'rom.nes',104:project/'game_identity.bin'})
    library = library_root('nes') / rom.sha256 / ENGINE_REV
    previous = library / 'cycle-seeds.trace'
    seed = project / 'cycle-seeds.trace'
    shared_record = record_for('nes', rom, ENGINE_REV)
    shared = shared_record.get('rom_entries', [])
    entries = _seed_sites(previous) | {f'4k:{bank:X}:{address:04X}'
        for bank, address in shared if bank < len(rom.data) // 4096 and 0x8000 <= address <= 0xffff}
    # A stopped/failed build may have already observed safe entry/opcode pairs.
    # They remain local candidates in this exact-ROM/region build directory;
    # normal full RAM differentials still gate their export and promotion.
    # Offered-only sites a stopped/failed build wrote into its seed are not its
    # observations: a retry without the imported hints must not inherit them.
    sidecar = seed.with_name('cycle-seeds.offered')
    stale_ram = ram_sites(sidecar)
    offered = _offered_only(rom, previous)
    atomic_text(sidecar, trace_text(*offered))
    ram_entries = ram_sites(previous) | (ram_sites(seed) - stale_ram) | shared_sites(rom, shared_record)
    entries |= feedback_rom
    ram_entries |= feedback_ram
    seed.write_text(trace_text(entries, ram_entries), encoding='ascii')
    imported = len(_seed_sites(seed))
    emit(f'NES converter library: {imported} observed ROM entries and {len(ram_entries)} guarded RAM entries from previous runs.')
    scan = nes_budget(level)
    nes_advanced_scan = scan['advanced']
    long_routes = ()
    if scan['route_count']:
        # Reproducible pseudo-random play seeded from the exact ROM; the same
        # script drives the native run and its reference comparison.
        from .random_routes import long_routes as pseudo_random_routes
        long_routes = pseudo_random_routes('nes', rom.sha256, count=scan['route_count'], frames=scan['route_frames'])
    scripts = _write_probe_scripts(project, frames, advanced=nes_advanced_scan, play_left=scan['play_left'],
                                   long_routes=long_routes)
    budgets = _scenario_frames(scripts, frames, long_routes)
    if long_routes:
        emit(f"NES scan level {level}: {len(long_routes)} reproducible pseudo-random routes of "
             f"{long_routes[0].frames} frames join the authored replays.")
    from .platforms import build_executable, cmake_target_args, build_jobs
    executable = build_executable(project / 'build', 'game')
    history: list[dict] = []
    final_checks: list[dict] = []
    native_rom_positions: tuple[int, int] | None = None
    build_passes = []
    compared_executable_sha = None
    for number in range(1, passes + 1):
        timings.begin_pass(number)
        prior = _seed_sites(seed)
        prior_ram = ram_sites(seed)
        emit(f'NES pass {number}/{passes}: generating and compiling native 6502 paths…')
        phase = time.perf_counter()
        with timings.phase('code_generation'):
            cache = prepare_native(project, compiler, rom, prior, prior_ram)
        generation_seconds = time.perf_counter() - phase
        compiled_ram_guards = cache['compiled_ram_guards']
        emit(f"NES native source cache: {cache['unchanged_sources']}/{cache['source_files']} unchanged; "
             f"{len(cache['changed_sources'])} updated.")
        emit(f'NES guarded RAM entry variants: {compiled_ram_guards}; operands remain live.')
        native_rom_positions = _native_rom_positions(project, rom.mapper)
        if native_rom_positions:
            emit(f'NES native physical PRG entry positions: '
                 f'{native_rom_positions[0]}/{native_rom_positions[1]}.')
        previous_objects = object_stamps(project / 'build')
        from .nes_optimization import build_game
        optimization = build_game(project, cmake, generator, sdl, scripts.get('play_right'), emit)
        configure_seconds = optimization['configure_seconds']
        build_seconds = optimization['build_seconds']
        current_objects = object_stamps(project / 'build')
        build_passes.append({'pass': number, **cache,
            'generation_seconds': round(generation_seconds, 6),
            'configure_seconds': round(configure_seconds, 6),
            'build_seconds': round(build_seconds, 6),
            'hardware_profile_guided': optimization['hardware_profile_guided'],
            'profile_training_seconds': round(optimization['profile_training_seconds'], 6),
            'objects_rebuilt': sum(previous_objects.get(p) != stamp for p, stamp in current_objects.items()),
            'objects_reused': sum(previous_objects.get(p) == stamp for p, stamp in current_objects.items())})
        if not executable.is_file():
            raise ConversionError('NES build produced no executable.')
        final_checks = []
        compared_executable_sha = hashlib.sha256(executable.read_bytes()).hexdigest()
        for scenario, script in scripts.items():
            with timings.phase('native_runs'):
                check = _probe(executable, project, scenario, budgets[scenario], seed, script,
                               differential=nes_advanced_scan)
            check['executable_sha256'] = compared_executable_sha
            check['input_sha256'] = hashlib.sha256(script.read_bytes()).hexdigest() if script else None
            check['pass'] = number
            final_checks.append(check)
            history.append(check)
            emit(f"NES {scenario}: {check['native_percent']:.4f}% native; "
                 f"{check['interpreter_cycles']} interpreted CPU cycles in {budgets[scenario]} frames.")
        new = _seed_sites(seed) - prior
        new_ram = ram_sites(seed) - prior_ram
        if all(check['interpreter_cycles'] == 0 for check in final_checks):
            emit('NES: no fallback cycles on the tested scenarios.')
            break
        if not new and not new_ram:
            emit('NES: no new ROM/RAM entry variants; remaining fallback stays reported.')
            break
        emit(f'NES: {len(new)} new ROM entries and {len(new_ram)} guarded RAM variants for the next pass.')
    timings.end_passes()
    # Validate the final generated code against the reference interpreter in
    # the same runtime. This is a CPU/runtime differential, not independent
    # hardware or full-game validation.
    cpu_checks = []
    if nes_advanced_scan:
        # All coverage scenarios already ran their complete reference/PCM
        # comparison in this pass. Bind that fresh evidence to this exact
        # artifact; never reuse a preceding pass/conversion's qualification.
        if hashlib.sha256(executable.read_bytes()).hexdigest() != compared_executable_sha:
            raise ConversionError('NES executable changed during its reference validation.')
        cpu_checks = [dict(check) for check in final_checks]
    for scenario, script in (() if nes_advanced_scan else scripts.items()):
        # Include input-driven execution after the delayed Start; 120 frames
        # alone would compare only boot for the late-start gameplay scenario.
        comparison_frames = budgets[scenario] if nes_advanced_scan or compiled_ram_guards or (rom.mapper in (1, 153, 155) and rom.data[4] > 16) else min(budgets[scenario], 600 if script else 120)
        with timings.phase('reference_runs'):
            comparison = _probe(executable, project, scenario, comparison_frames, seed,
                                script, differential=True)
        cpu_checks.append(comparison)
        emit(f'NES {scenario}: internal CPU/visible-state/audio comparison matches '
             f"for {comparison['frames']} frames.")
    _remember_seed(seed, previous, offered)
    created_utc = datetime.now(timezone.utc).isoformat()
    report = {'tool': 'Retro-Recomp', 'version': __version__,
        'created_utc': created_utc,
        'system': {'id': 'nes', 'name': 'Nintendo Entertainment System'},
        'scan_level': level, 'rom': rom.metadata(), 'backend': 'nesrecomp-cycle-accurate',
        'compiler': {'url': ENGINE_URL, 'revision': ENGINE_REV,
                     'license': 'PolyForm Noncommercial 1.0.0',
                     'adapter': 'bank-independent ROM bodies, guarded RAM entries and fetch-time unstable-mapper dispatch'},
        'native_coverage': {'imported_entries': imported, 'observed_entries': len(_seed_sites(seed)),
                            'imported_ram_guards': len(ram_entries), 'compiled_ram_guards': compiled_ram_guards,
                            'observed_ram_guards': len(ram_sites(seed)),
                            'position_unit': 'physical PRG byte, shared across CPU slots',
                            'tested_scenarios': list(scripts),
                            'precompiled_rom_positions': native_rom_positions[0] if native_rom_positions else None,
                            'rom_address_positions': native_rom_positions[1] if native_rom_positions else None},
        'final_checks': final_checks, 'history': history, 'build_passes': build_passes,
        'native_validation': {'passed': True, 'method': 'internal interpreter frame hashes and exact PCM',
                              'scenarios': cpu_checks, 'independent_cpu_oracle': False,
                              'hardware_accuracy': False, 'full_game': False},
        'reference_vdp_trace_match': None,
        'video_model': {'standard': standard, 'timing_source': 'manual' if standard_override else rom.timing_source,
                        'visible_pixels': [256, 240],
                        'hardware_accuracy_validated': False},
        'input_players': 2, 'zapper': gun,
        'game_states': {'supported': True, 'compatibility': 'same ROM, region and runtime ABI'},
        'artwork': artwork, 'windows_metadata': metadata,
        'runtime_learning': True, 'runtime_feedback': gameplay_feedback, 'library_identity': rom.sha256,
        'advanced_scan': {'enabled': bool(nes_advanced_scan), 'level': level, 'scenarios': list(scripts),
                          'scenario_frames': budgets,
                          'long_routes': [route.metadata() for route in long_routes],
                          'deterministic_inputs': True, 'full_game': False},
        'host_audio': {'sample_rate': 48000, 'callback_frames_requested': 256,
                       'startup': 'one_device_period_plus_30ms', 'native_s16_or_float': True,
                       'bounded_pcm_ring': True},
        'physical_latency_measured': False,
        'build_executable': str(executable), 'executable': executable.name, 'toolchain': toolchain_description(),
        'build_directory': str(project),
        'conversion_wall_seconds': round(time.perf_counter() - started, 6)}
    write_report(destination / 'conversion-report.json', report)
    emit('NES export validated on tested paths; gameplay and hardware fidelity remain unverified.')
    return executable
