"""Experimental NES conversion using the pinned NESRecomp cycle backend.

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
import time
import zlib
from typing import Callable

from . import __version__
from .artwork import ArtworkError, prepare_icon
from .core import ConversionError, dependencies, executable_name, run, serialized_setup, slug, toolchain
from .library import atomic_json, library_root
from .metadata import write_game_metadata
from .nes_runtime import prepare_host
from .paths import ROOT, data_directory, games_root
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
    system_id: str = "nes"

    def metadata(self) -> dict:
        return {"name": self.path.name, "bytes": len(self.data),
                "crc32": f"{self.crc32:08X}", "sha256": self.sha256,
                "mapper": self.mapper, "nes2": self.nes2,
                "header_timing": self.video_standard, "system_id": self.system_id}


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
    timing = header[12] & 3 if nes2 else 0
    standard = {0: 'ntsc', 1: 'pal', 2: 'multi', 3: 'dendy'}[timing]
    return NesRom(path, data, zlib.crc32(data), hashlib.sha256(data).hexdigest(),
                  mapper, nes2, standard)


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
    compiler = engine / 'build-retrorecomp/Release/NESRecomp.exe'
    if not compiler.is_file():
        emit('Building the NES 6502 recompiler…')
        run([cmake, '-S', engine / 'recompiler', '-B', engine / 'build-retrorecomp',
             '-G', generator, '-A', 'x64'], timeout=600)
        run([cmake, '--build', engine / 'build-retrorecomp', '--config', 'Release',
             '--parallel', '4'], timeout=1800)
    if not compiler.is_file():
        raise ConversionError('NESRecomp produced no compiler executable.')
    return engine, compiler, sdl, cmake, generator


def _seed_sites(path: Path) -> set[str]:
    try:
        return {match.group(0).split()[0].upper() for line in path.read_text(encoding='ascii').splitlines()
                if (match := SEED.match(line))}
    except FileNotFoundError:
        return set()


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


def _probe(exe: Path, work: Path, scenario: str, frames: int, seed: Path,
           script: Path | None = None, *, differential: bool = False) -> dict:
    command: list[str | Path] = [exe, '--frames', str(frames)]
    if script:
        command += ['--input', script]
    command += ['--miss-log', seed]
    if differential:
        command += ['--hash-out', work / f'{scenario}-native.hash']
    output = run(command, cwd=work, log=work / 'validation.log', timeout=600)
    summary, interpreted = SUMMARY.search(output), INTERPRETED.search(output)
    if not summary or int(summary[1]) != frames:
        raise ConversionError(f'NES {scenario} probe did not complete {frames} frames.\n{output[-1000:]}')
    total, native = int(summary[2]), int(summary[3])
    if not interpreted and native != total:
        raise ConversionError(f'NES {scenario} did not report its interpreted cycles.')
    rom_cycles, ram_cycles = (int(interpreted[1]), int(interpreted[2])) if interpreted else (0, 0)
    other = OTHER.search(output)
    other_cycles = int(other[1]) if other else 0
    if differential:
        reference_command: list[str | Path] = [exe, '--frames', str(frames), '--interp-only',
            '--hash-out', work / f'{scenario}-reference.hash']
        if script:
            reference_command += ['--input', script]
        run(reference_command, cwd=work, log=work / 'validation.log', timeout=600)
        native_hash = (work / f'{scenario}-native.hash').read_bytes()
        reference_hash = (work / f'{scenario}-reference.hash').read_bytes()
        if native_hash != reference_hash or len(native_hash.splitlines()) != frames:
            raise ConversionError(f'NES {scenario}: native and internal interpreter frame states differ.')
    return {'scenario': scenario, 'frames': frames, 'cycles': total,
            'native_cycles': native, 'native_percent': 100 * native / total if total else 0,
            'interpreter_rom_cycles': rom_cycles, 'interpreter_ram_cycles': ram_cycles,
            'interpreter_other_cycles': other_cycles,
            'interpreter_cycles': rom_cycles + ram_cycles + other_cycles,
            'interpreter_percent': 100 * (rom_cycles + ram_cycles + other_cycles) / total if total else 0,
            'internal_differential': differential}


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
    if rom.video_standard != 'ntsc' or standard_override not in (None, 'ntsc'):
        raise ConversionError('The current NES cycle runtime supports NTSC only; PAL/Dendy ROMs need a separate timing backend.')
    title = title or re.sub(r'\s*\([^)]*\)', '', rom.path.stem).strip()
    project = ROOT / '.build' / f'nes_{slug(title)}_{rom.sha256[:12]}_{ENGINE_REV[:8]}'
    project.mkdir(parents=True, exist_ok=True)
    destination = output.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    emit(f'NES ROM: {title}, {len(rom.data) // 1024} KB, mapper {rom.mapper}, CRC32 {rom.crc32:08X}.')
    try:
        artwork = prepare_icon(project, rom.path, title,
            (boxart_dir or ROOT / 'BoxArt/Nintendo NES').resolve(), explicit=cover,
            online=online_cover, enabled=use_cover, cache_directory=data_directory() / 'BoxArt/nes',
            tags=(), system_id='nes', emit=emit)
    except (ArtworkError, OSError) as exc:
        raise ConversionError(str(exc)) from exc
    engine, compiler, sdl, cmake, generator = _dependencies(emit)
    (project / 'rom.nes').write_bytes(rom.data)
    prepare_host(project, engine, rom.sha256, title)
    metadata = write_game_metadata(project, title, executable_name(title), light_phaser=False,
        icon=artwork['embedded'], standard='ntsc', system_id='nes')
    notice = 'NES executable: component license notices.\n\n'
    for component, source in [('RetroRecomp', ROOT / 'LICENSE'),
                              ('NESRecomp', engine / 'LICENSE'),
                              ('emu2413', engine / 'runner/cyc/vendor/emu2413/LICENSE'),
                              ('SDL2', ROOT / 'licenses/SDL2.md')]:
        notice += f'## {component}\n\n' + source.read_text(encoding='utf-8') + '\n\n'
    (project / 'game_legal.md').write_text(notice, encoding='utf-8')
    (project / 'game_identity.bin').write_bytes(b'[Retro-Recomp]\0' + rom.sha256.encode('ascii') + b'\0')
    with (project / 'game_resources.rc').open('a', encoding='utf-8') as resource:
        resource.write('102 RCDATA "game_legal.md"\n103 RCDATA "rom.nes"\n'
                       '104 RCDATA "game_identity.bin"\n')
    library = library_root('nes') / rom.sha256 / ENGINE_REV
    previous = library / 'cycle-seeds.trace'
    seed = project / 'cycle-seeds.trace'
    if previous.is_file():
        shutil.copy2(previous, seed)
    else:
        seed.write_text('', encoding='ascii')
    imported = len(_seed_sites(seed))
    emit(f'NES converter library: {imported} observed ROM entries from previous runs.')
    scripts = {'boot': None, 'play_right': project / 'play-right.input',
               'play_left': project / 'play-left.input'}
    scripts['play_right'].write_text('20 START\n22 -\n90 RIGHT\n160 RIGHT+A\n240 A\n300 -\n', encoding='ascii')
    scripts['play_left'].write_text('20 START\n22 -\n90 LEFT\n160 LEFT+B\n240 B\n300 -\n', encoding='ascii')
    executable = project / 'build/Release/game.exe'
    history: list[dict] = []
    final_checks: list[dict] = []
    for number in range(1, passes + 1):
        prior = _seed_sites(seed)
        emit(f'NES pass {number}/{passes}: generating and compiling native 6502 paths…')
        run([sys.executable, engine / 'tools/cyc/prepare_project.py',
             '--rom', project / 'rom.nes', '--recompiler', compiler,
             '--out', project / 'cycle', '--seeds', seed], cwd=project,
            log=project / 'build.log', timeout=600)
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
        if not new:
            emit('NES: no new seedable ROM sites; remaining fallback stays reported.')
            break
        if all(check['interpreter_cycles'] == 0 for check in final_checks):
            break
        emit(f'NES: {len(new)} new ROM entry sites for the next pass.')
    # Validate the final generated code against the reference interpreter in
    # the same runtime. This is a CPU/runtime differential, not independent
    # hardware or full-game validation.
    cpu_checks = []
    for scenario, script in scripts.items():
        comparison = _probe(executable, project, scenario, min(frames, 120), seed,
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
                     'license': 'PolyForm Noncommercial 1.0.0'},
        'native_coverage': {'imported_entries': imported, 'observed_entries': len(_seed_sites(seed)),
                            'tested_scenarios': list(scripts)},
        'final_checks': final_checks, 'history': history,
        'native_validation': {'passed': True, 'method': 'internal interpreter frame hashes',
                              'scenarios': cpu_checks, 'independent_cpu_oracle': False,
                              'hardware_accuracy': False, 'full_game': False},
        'reference_vdp_trace_match': None,
        'video_model': {'standard': 'ntsc', 'visible_pixels': [256, 240],
                        'hardware_accuracy_validated': False},
        'input_players': 2, 'game_states': {'supported': False},
        'artwork': artwork, 'windows_metadata': metadata,
        'runtime_learning': False, 'library_identity': rom.sha256,
        'physical_latency_measured': False,
        'build_executable': str(executable), 'executable': executable.name,
        'conversion_wall_seconds': round(time.perf_counter() - started, 6)}
    atomic_json(destination / 'conversion-report.json', report)
    emit('NES export validated on tested paths; gameplay and hardware fidelity remain unverified.')
    return executable
