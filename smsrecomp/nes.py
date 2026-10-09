"""NES conversion using the pinned NESRecomp cycle backend.

The dependency is PolyForm Noncommercial, independently of RetroRecomp's MIT
code. Each generated game retains the exact license in a Windows resource.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import re
import shutil
import sys
import tempfile
import time
import zlib
from typing import Callable

from . import __version__
from .artwork import ArtworkError, prepare_icon
from .core import ConversionError, dependencies, executable_name, run, serialized_setup, slug, toolchain
from .library import atomic_json, library_root
from .knowledge import record_for
from .metadata import write_game_metadata
from .nes_codegen import prepare_compiler
from .nes_runtime import prepare_host
from .nes_catalog import zapper_game
from .paths import ROOT, ASSETS, data_directory, games_root, boxart_cache_directory
from .systems import archive_rom

ENGINE_URL = "https://github.com/mstan/nesrecomp.git"
ENGINE_REV = "1b0c621a927db17afa9723bf456a89ad15809907"
MAX_ROM_BYTES = 128 * 1024 * 1024 + 528
SEED = re.compile(r"^4k:([0-9A-Fa-f]{1,4}):([89A-Fa-f][0-9A-Fa-f]{3})(?:\s|$)")
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
    cmake, generator = toolchain()
    sdl = ROOT / '.deps/SDL/install'
    if not (sdl / 'lib/SDL2-static.lib').is_file():
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
        return {match.group(0).split()[0].upper() for line in path.read_text(encoding='ascii').splitlines()
                if (match := SEED.match(line))}
    except FileNotFoundError:
        return set()


def _native_rom_positions(project: Path, mapper: int) -> tuple[int, int] | None:
    cycle = project / 'cycle'
    manifest = (cycle / 'sources.cmake').read_text(encoding='utf-8')
    generated = next((path for path in cycle.glob('*/generated/game_cyc.c')
                      if path.as_posix() in manifest), None)
    if generated is None:
        raise ConversionError('NES compiler generated no selected native source.')
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
        command += ['--hash-out', work / f'{scenario}-native.hash']
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
            '--hash-out', work / f'{scenario}-reference.hash']
        if script:
            reference_command += ['--input', script]
        _run_probe(reference_command, work)
        native_hash = (work / f'{scenario}-native.hash').read_bytes()
        reference_hash = (work / f'{scenario}-reference.hash').read_bytes()
        if native_hash != reference_hash or len(native_hash.splitlines()) != frames:
            raise ConversionError(f'NES {scenario}: native and internal interpreter frame states differ.')
    return {'scenario': scenario, 'frames': frames, 'cycles': total,
            'native_cycles': native, 'native_percent': 100 * native / total if total else 0,
            'interpreter_rom_cycles': rom_cycles, 'interpreter_ram_cycles': ram_cycles,
            'interpreter_other_cycles': other_cycles,
            'interpreter_cycles': interpreter_cycles,
            'interpreter_percent': 100 * interpreter_cycles / total if total else 0,
            'non_dispatch_cycles': non_dispatch_cycles,
            'internal_differential': differential}


def _write_probe_scripts(project: Path, frames: int) -> dict[str, Path | None]:
    """Keep exercising inputs after boot instead of idling for most of a test."""
    scripts: dict[str, Path | None] = {'boot': None}
    # Different Start timings cover titles that need a few seconds to become
    # interactive. Never pulse Start repeatedly: many games use it to pause.
    for name, direction, start in (('play_right', 'RIGHT', 180),
                                    ('play_left', 'LEFT', 20)):
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
    return scripts


def convert_nes(rom_path: Path, *, title: str | None = None, output: Path | None = None,
                profile: Path | None = None, passes: int = 3, frames: int = 3600,
                backend: str = 'banked', language: str = 'en', cover: Path | None = None,
                boxart_dir: Path | None = None, online_cover: bool = True,
                use_cover: bool = True, icon_tags: bool = True,
                standard_override: str | None = None,
                emit: Callable[[str], None] = print) -> Path:
    if output is None:
        from .batch import convert_batch, identify
        item = identify(rom_path)
        if title:
            item.title = title
        item.cover = cover
        record = convert_batch([item], games_root(), profile=profile, passes=passes,
            frames=frames, backend=backend, language=language, boxart_dir=boxart_dir,
            online_cover=online_cover, use_cover=use_cover, icon_tags=icon_tags,
            standard_override=standard_override, emit=emit)
        if record['failed']:
            raise ConversionError(record['games'][0]['message'])
        return Path(record['games'][0]['executable'])
    if profile is not None:
        raise ConversionError('NES uses verified ROM traces, not Sega TOML profiles.')
    if not 1 <= passes <= 10 or not 1 <= frames <= 10000:
        raise ConversionError('Choose 1–10 passes and 1–10000 frames per test.')
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
    emit(f'NES ROM: {title}, {len(rom.data) // 1024} KB, mapper {rom.mapper}, CRC32 {rom.crc32:08X}.')
    emit(f'NES video timing: {standard.upper()} ({"manual" if standard_override else rom.timing_source}).')
    if gun:
        emit('NES Zapper enabled: mouse aim and trigger on controller port 2.')
    try:
        artwork = prepare_icon(project, rom.path, title,
            (boxart_dir or ROOT / 'BoxArt/Nintendo NES').resolve(), explicit=cover,
            online=online_cover, enabled=use_cover, cache_directory=boxart_cache_directory('nes'),
            tags=('shooting',) if gun and icon_tags else (), system_id='nes', emit=emit)
    except (ArtworkError, OSError) as exc:
        raise ConversionError(str(exc)) from exc
    engine, compiler, sdl, cmake, generator = _dependencies(emit)
    (project / 'rom.nes').write_bytes(rom.data)
    prepare_host(project, engine, rom.sha256, title, standard=standard, zapper=gun)
    metadata = write_game_metadata(project, title, executable_name(title), light_phaser=False,
        icon=artwork['embedded'], standard=standard, system_id='nes', zapper=gun)
    notice = 'NES executable: component license notices.\n\n'
    for component, source in [('RetroRecomp', ASSETS / 'LICENSE'),
                              ('NESRecomp', engine / 'LICENSE'),
                              ('emu2413', engine / 'runner/cyc/vendor/emu2413/LICENSE'),
                              ('SDL2', ASSETS / 'licenses/SDL2.md')]:
        notice += f'## {component}\n\n' + source.read_text(encoding='utf-8') + '\n\n'
    (project / 'game_legal.md').write_text(notice, encoding='utf-8')
    (project / 'game_identity.bin').write_bytes(b'[Retro-Recomp]\0' + rom.sha256.encode('ascii') + b'\0')
    with (project / 'game_resources.rc').open('a', encoding='utf-8') as resource:
        resource.write('102 RCDATA "game_legal.md"\n103 RCDATA "rom.nes"\n'
                       '104 RCDATA "game_identity.bin"\n')
    library = library_root('nes') / rom.sha256 / ENGINE_REV
    previous = library / 'cycle-seeds.trace'
    seed = project / 'cycle-seeds.trace'
    shared = record_for('nes', rom, ENGINE_REV).get('rom_entries', [])
    entries = _seed_sites(previous) | {f'4k:{bank:X}:{address:04X}'
        for bank, address in shared if bank < len(rom.data) // 4096 and 0x8000 <= address <= 0xffff}
    seed.write_text(''.join(e + '\n' for e in sorted(entries)), encoding='ascii')
    imported = len(_seed_sites(seed))
    emit(f'NES converter library: {imported} observed ROM entries from previous runs.')
    scripts = _write_probe_scripts(project, frames)
    executable = project / 'build/Release/game.exe'
    history: list[dict] = []
    final_checks: list[dict] = []
    native_rom_positions: tuple[int, int] | None = None
    for number in range(1, passes + 1):
        prior = _seed_sites(seed)
        emit(f'NES pass {number}/{passes}: generating and compiling native 6502 paths…')
        bridge_command = ([sys.executable, '_nes-prepare-project', engine]
                          if getattr(sys, 'frozen', False) else
                          [sys.executable, engine / 'tools/cyc/prepare_project.py'])
        run([*bridge_command,
             '--rom', project / 'rom.nes', '--recompiler', compiler,
             '--out', project / 'cycle', '--seeds', seed], cwd=project,
            log=project / 'build.log', timeout=600)
        native_rom_positions = _native_rom_positions(project, rom.mapper)
        if native_rom_positions:
            emit(f'NES native physical PRG entry positions: '
                 f'{native_rom_positions[0]}/{native_rom_positions[1]}.')
        run([cmake, '-S', project, '-B', project / 'build', '-G', generator, '-A', 'x64',
             f'-DCMAKE_PREFIX_PATH={sdl.as_posix()}'], cwd=project,
            log=project / 'build.log', timeout=600)
        run([cmake, '--build', project / 'build', '--config', 'Release', '--parallel', '4'],
            cwd=project, log=project / 'build.log', timeout=1800)
        if not executable.is_file():
            raise ConversionError('NES build produced no executable.')
        final_checks = []
        for scenario, script in scripts.items():
            check = _probe(executable, project, scenario, frames, seed, script)
            check['pass'] = number
            final_checks.append(check)
            history.append(check)
            emit(f"NES {scenario}: {check['native_percent']:.4f}% native; "
                 f"{check['interpreter_cycles']} interpreted CPU cycles in {frames} frames.")
        new = _seed_sites(seed) - prior
        if all(check['interpreter_cycles'] == 0 for check in final_checks):
            emit('NES: no fallback cycles on the tested scenarios.')
            break
        if not new:
            emit('NES: no new seedable ROM sites; remaining fallback stays reported.')
            break
        emit(f'NES: {len(new)} new ROM entry sites for the next pass.')
    # Validate the final generated code against the reference interpreter in
    # the same runtime. This is a CPU/runtime differential, not independent
    # hardware or full-game validation.
    cpu_checks = []
    for scenario, script in scripts.items():
        # Include input-driven execution after the delayed Start; 120 frames
        # alone would compare only boot for the late-start gameplay scenario.
        comparison = _probe(executable, project, scenario, min(frames, 600 if script else 120), seed,
                            script, differential=True)
        cpu_checks.append(comparison)
        emit(f'NES {scenario}: internal CPU/visible-state comparison matches '
             f"for {comparison['frames']} frames.")
    library.mkdir(parents=True, exist_ok=True)
    shutil.copy2(seed, previous)
    report = {'tool': 'Retro-Recomp', 'version': __version__,
        'system': {'id': 'nes', 'name': 'Nintendo Entertainment System'},
        'rom': rom.metadata(), 'backend': 'nesrecomp-cycle-accurate',
        'compiler': {'url': ENGINE_URL, 'revision': ENGINE_REV,
                     'license': 'PolyForm Noncommercial 1.0.0',
                     'adapter': 'bank-independent ROM-specialized native bodies with live boundary operands'},
        'native_coverage': {'imported_entries': imported, 'observed_entries': len(_seed_sites(seed)),
                            'position_unit': 'physical PRG byte, shared across CPU slots',
                            'tested_scenarios': list(scripts),
                            'precompiled_rom_positions': native_rom_positions[0] if native_rom_positions else None,
                            'rom_address_positions': native_rom_positions[1] if native_rom_positions else None},
        'final_checks': final_checks, 'history': history,
        'native_validation': {'passed': True, 'method': 'internal interpreter frame hashes',
                              'scenarios': cpu_checks, 'independent_cpu_oracle': False,
                              'hardware_accuracy': False, 'full_game': False},
        'reference_vdp_trace_match': None,
        'video_model': {'standard': standard, 'timing_source': 'manual' if standard_override else rom.timing_source,
                        'visible_pixels': [256, 240],
                        'hardware_accuracy_validated': False},
        'input_players': 2, 'zapper': gun,
        'game_states': {'supported': True, 'compatibility': 'same ROM, region and runtime ABI'},
        'artwork': artwork, 'windows_metadata': metadata,
        'runtime_learning': False, 'library_identity': rom.sha256,
        'physical_latency_measured': False,
        'build_executable': str(executable), 'executable': executable.name,
        'conversion_wall_seconds': round(time.perf_counter() - started, 6)}
    atomic_json(destination / 'conversion-report.json', report)
    emit('NES export validated on tested paths; gameplay and hardware fidelity remain unverified.')
    return executable
