"""Game Boy Advance conversion (docs/GAME_BOY_ADVANCE.md): the engine, our patches, the observation loop, the report.

The engine is `mstan/gbarecomp` (PolyForm Noncommercial 1.0.0, the author's permission held by the maintainer), pinned by
commit like the other machines' engines, downloaded at its pinned revision on the first conversion and never copied into
this repository; our fixes are carried as anchored patches on a staged copy (`gba_patches`, docs/UPSTREAMS.md). Its CPU
core is the engine's own submodule `arm-recomp-core` (MIT), kept at the revision the engine records.

What a conversion does, in this stage (the machine stays experimental and developer-only):

1. checks the cartridge and the player's BIOS (the one image the engine knows, by SHA-1);
2. builds the engine's recompiler once per patch set, and generates the BIOS code from the player's own file (private);
3. generates the cartridge's code from the engine's analysis plus what earlier runs learned (`gba_analysis`);
4. builds the engine's headless probe host with that code and runs it on bounded, scripted scenarios;
5. turns every PC that fell to the interpreter into paths (ROM roots, RAM routines copied from the cartridge) and repeats;
6. replays the scenarios with the engine's own interpreter alone and compares the final picture and cycle count;
7. writes the report through the common builder. The interpreter fallback is counted, never hidden.

It produces no player: the probe host has no window and no sound. The player is a host-kit adapter (a later stage).
The five measures stay apart: native code (counted fallback), CPU fidelity (agreement with the engine's own interpreter
on the scenarios, not an independent oracle), hardware fidelity, gameplay validation and physical latency (the last
three are not claimed).
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .core import ConversionError
from .gba import read_rom
from .platforms import target_id
from .report_schema import write_report

ENGINE_URL = 'https://github.com/mstan/gbarecomp.git'
# mstan/gbarecomp, 31 Oct 2026 (merge of release/final-gba-prs-20261101), read on 4-5 Nov 2026 (docs/GAME_BOY_ADVANCE.md).
ENGINE_REV = 'c1a5fda36fb41c2fcba6c901692006ac69d50555'
# The revision of external/arm-recomp-core the pinned engine records (not the head of that repository).
ARM_CORE_REV = '63dd32dd210a8bf18bbd11933393a7b87f9b3bf6'
# The two other submodules the engine records (netplay: built by nothing of ours; kept so the tree is what upstream tested).
NET_REV = '8c76fb643339144a3a84d5ba8f5defe6250dcd26'
RBENGINE_REV = '2a03e73693acee0fb78076ea058642c931bef12e'
LICENSE = 'PolyForm Noncommercial 1.0.0'
BOOT_FRAMES = 600
# The engine stops a run on a frame and the generated code and the interpreter account the cycles of the last instruction
# one apart (seen on every cartridge: the picture is identical and the counts differ by exactly one); more than this is a
# real difference in where the two ran.
CYCLE_TOLERANCE = 2


def _row(name, frames, native, interpreted, **extra) -> dict:
    percent = None if native is None or interpreted is None else 100 * interpreted / max(1, native + interpreted)
    return {'scenario': name, 'frames': frames, 'native_entries': native, 'interpreted_opcodes': interpreted,
            'interpreter_percent': percent, 'reference_match': None, **extra}


def report_of(source, level: str, rows: list, *, validation: dict | None = None, coverage=None, compiler=None,
              extra=None) -> dict:
    """The conversion report's own keys (the common builder adds the rest). Nothing here claims more than was measured."""
    document = {'tool': 'Retro-Recomp', 'version': __version__, 'created_utc': datetime.now(timezone.utc).isoformat(),
                'system': {'id': 'gba', 'name': 'Game Boy Advance'}, 'status': 'experimental', 'target': target_id(),
                'rom': source.metadata(), 'scan_level': level,
                'native_validation': validation or {'passed': None, 'scope': 'nothing was compared',
                                                    'cpu_fidelity_validated': False, 'independent_cpu_oracle': False},
                'native_coverage': coverage or 'not measured', 'final_checks': rows, 'gba_checks': rows,
                'game_states': {'supported': False, 'save_key': 'F8', 'load_key': 'F9', 'fresh_process_verified': False},
                'hardware_accuracy_validated': False, 'full_game_validated': False, 'latency_ms': None,
                'physical_latency_measured': False}
    if compiler:
        document['compiler'] = compiler
    document.update(extra or {})
    return document


def skeleton_report(source, scenarios, level='standard') -> dict:
    """A report for scenarios run elsewhere, `(name, frames, native, interpreted)` each; nothing is measured here."""
    rows = [_row(name, frames, native, interpreted) for name, frames, native, interpreted in scenarios]
    return report_of(source, level, rows, validation={'passed': None, 'scope': 'skeleton: nothing was compared',
                                                      'cpu_fidelity_validated': False, 'independent_cpu_oracle': False})


def write_skeleton_report(path, source, scenarios, level='standard') -> dict:
    return write_report(path, skeleton_report(source, scenarios, level))


def _matches(native, reference) -> bool | None:
    """Do the engine's generated code and its own interpreter end a scenario in the same place? None when no
    reference run ended."""
    if reference is None or reference.returncode or native.returncode:
        return None
    if native.cycles is None or reference.cycles is None:
        return False
    return bool(native.frame_sha256 and native.frame_sha256 == reference.frame_sha256
                and abs(native.cycles - reference.cycles) <= CYCLE_TOLERANCE)


def convert(path: Path, *, output: Path | None = None, title: str | None = None, passes: int = 3, frames: int = 3600,
            scan_level: str | None = None, gba_bios=None, emit=print, player: bool = True, cover: Path | None = None,
            boxart_dir: Path | None = None, online_cover: bool = True, use_cover: bool = True, **options) -> Path:
    """Convert one cartridge with the pinned engine. With `output` the player is built and returned (the report goes
    to `output`, the batch publishes the executable: compaction, the games folder); `player=False`, or no `output`, returns the headless probe host (the report goes to the project)."""
    from . import gba_analysis as analysis, gba_build as build, gba_engine as engine, gba_patches, path_profiles, timings
    from .conversion_common import check_run_budget, resolve_scan_level, write_if_changed
    from .core import slug, toolchain
    from .gba import bios_status, read_bytes
    from .library import atomic_json, library_root
    from .paths import ROOT, selected_bios_path
    from .platforms import require_backend
    level = resolve_scan_level(scan_level)
    check_run_budget(passes, frames, 'Choose 1–10 passes and 1–10000 frames per test.')
    started = time.perf_counter()
    rom = read_rom(path)
    data = read_bytes(path)
    status = bios_status(gba_bios)
    if status != 'known':
        raise ConversionError('The Game Boy Advance profile needs your own BIOS (gba_bios.bin) in Options: '
                              + ('no file was chosen or found.' if status == 'missing' else
                                 'this file is not the 16 KiB image the engine supports.'))
    bios = selected_bios_path(gba_bios)
    require_backend('gba')
    cmake, generator = toolchain()
    title = title or rom.path.stem.split(' (')[0].strip() or rom.path.stem
    project = ROOT / '.build' / f'gba_{slug(title)}_{rom.sha256[:12]}_{ENGINE_REV[:8]}'
    project.mkdir(parents=True, exist_ok=True)
    emit(f'Game Boy Advance: {title}, {rom.size // 1024} KB, {rom.save_type}, CRC32 {rom.crc32:08X}.')
    checkout = engine.checkout(emit)
    digest = engine.patch_digest(gba_patches.PATCHES, gba_patches.ADDED_FILES)
    key = f'{ENGINE_REV[:8]}-{digest[:8]}'
    stage_root = ROOT / '.deps' / f'gbarecomp-stage-{key}'
    _, notes = engine.stage(stage_root, checkout, gba_patches.PATCHES, gba_patches.ADDED_FILES)
    recompile = build.recompiler(stage_root, key, cmake, generator, emit)
    bios_code = build.generate_bios(recompile, stage_root, bios, project / 'bios', emit)
    rom_file = project / 'rom.gba'
    write_if_changed(rom_file, data)
    sha1 = hashlib.sha1(data).hexdigest()
    store = library_root('gba') / rom.sha256 / ENGINE_REV / 'paths.json'
    observations = analysis.Observations()
    try:
        observations = analysis.observations_of(json.loads(store.read_text(encoding='utf-8')))
    except (OSError, ValueError):
        pass
    imported = observations.size()
    emit(f'Game Boy Advance library: {imported} observed entries from earlier runs.')
    scripts = project / 'scripts'
    scenarios = [('boot', min(frames, BOOT_FRAMES), 'boot'), ('generic', frames, 'generic')]
    paths = {}
    for name, count, kind in scenarios:
        write_if_changed(scripts / f'{name}.txt', build.input_script(count, kind).encode('ascii'))
        paths[name] = scripts / f'{name}.txt'
    rows, runs, history, generated, unresolved, host = [], {}, [], {}, [], None
    for number in range(1, passes + 1):
        timings.begin_pass(number)
        emit(f'Game Boy Advance pass {number}/{passes}: generating and compiling native ARM and Thumb code…')
        write_if_changed(project / 'game.toml', analysis.config_text(title, sha1, len(data), observations).encode('utf-8'))
        with timings.phase('code_generation'):
            generated = build.generate_game(recompile, rom_file, project / 'game.toml', project / 'generated', emit)
        emit(f"Game Boy Advance: {generated['functions']} functions in {generated['shards']} shards.")
        build.host_project(project, stage_root, project / 'generated', bios_code)
        host = build.build_host(project, cmake, generator, emit)
        runs, rows, learned, unresolved = {}, [], analysis.Observations(), []
        for name, count, _ in scenarios:
            outcome = build.run_scenario(host, rom_file, sha1, bios, project / 'runs', name, count, paths[name])
            runs[name] = outcome
            found, left = analysis.observations_from_misses(analysis.parse_misses(outcome.misses), data, outcome.iwram)
            learned.merge(found)
            unresolved += left
            interpreted = outcome.coverage.get('interpreted_insns')
            rows.append(_row(name, count, None, interpreted, coverage=outcome.coverage.get('coverage'),
                             distinct_misses=outcome.coverage.get('distinct_misses'), aborted=outcome.aborted or None,
                             exit_code=outcome.returncode, picture_sha256=outcome.frame_sha256 or None,
                             cycles_total=outcome.cycles))
            history.append({**rows[-1], 'pass': number})
            emit(f"Game Boy Advance {name}: {outcome.coverage.get('coverage', 'no coverage report')}, "
                 f"{interpreted} interpreted instructions, {outcome.coverage.get('distinct_misses')} distinct addresses"
                 + (f'; stopped: {outcome.aborted}' if outcome.aborted else '.'))
        new = observations.merge(learned)
        if all(row['interpreted_opcodes'] == 0 and not row['aborted'] for row in rows):
            emit('Game Boy Advance: no interpreted instruction on the tested scenarios.')
            break
        if not new:
            emit('Game Boy Advance: no new entry; the remaining fallback stays reported.')
            break
        emit(f'Game Boy Advance: {new} new entries for the next pass.')
    timings.end_passes()
    # What the passes learned is kept before the long replay: a conversion that is stopped there has not lost it.
    store.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(store, path_profiles.validate_game(analysis.record(rom.sha256, len(data), ARM_CORE_REV, observations)))
    emit("Game Boy Advance: replaying the scenarios with the engine's own interpreter alone…")
    for row, (name, count, _) in zip(rows, scenarios):
        if runs[name].returncode:
            continue
        reference = build.run_scenario(host, rom_file, sha1, bios, project / 'runs', name, count, paths[name],
                                       timeout=3600, reference=True)
        row['reference_match'] = _matches(runs[name], reference)
    checked = [row for row in rows if row['reference_match'] is not None]
    validation = {'passed': (all(row['reference_match'] for row in checked) if checked else None),
                  'method': "final picture and cycle count against the engine's own interpreter, same scenario",
                  'scope': "bounded scripted scenarios; the interpreter is the engine's, not an independent oracle",
                  'cpu_fidelity_validated': False, 'independent_cpu_oracle': False,
                  'scenarios': [{'scenario': row['scenario'], 'frames': row['frames'], 'match': row['reference_match']}
                                for row in rows]}
    coverage = {'imported_entries': imported, 'observed_entries': observations.size(),
                'rom_roots': len(observations.roots), 'ram_routines': len(observations.spans),
                'unresolved_misses': len(unresolved), 'generated': generated,
                'tested_scenarios': [name for name, *_ in scenarios],
                'unit': 'interpreted ARM and Thumb instructions, counted by the engine'}
    compiler = {'url': ENGINE_URL, 'revision': ENGINE_REV, 'license': LICENSE, 'arm_core_revision': ARM_CORE_REV,
                'patch_digest': digest, 'patches': notes, 'bios': "generated from the player's own system ROM, private"}
    exported = artwork = None
    if player and output is not None:
        exported, artwork = _export_player(project, stage_root, bios_code, bios, rom_file, rom, title, sha1, emit,
                                           {'rom_path': rom.path, 'cover': cover, 'boxart_dir': boxart_dir,
                                            'online_cover': online_cover, 'use_cover': use_cover, 'emit': emit})
    report = report_of(rom, level, rows, validation=validation, coverage=coverage, compiler=compiler,
                       extra={'history': history, 'backend': 'gbarecomp-player' if exported else 'gbarecomp-probe-host',
                              'executable': exported.name if exported else build.HOST_NAME,
                              'build_executable': str(exported) if exported else str(host),
                              'build_directory': str(project), 'artwork': artwork,
                              'conversion_wall_seconds': round(time.perf_counter() - started, 6),
                              'player': ('host kit: window, controls, menus, sound at 32768 Hz mono, quick state, battery save'
                                         if exported else 'none: the probe host has no window and no sound')})
    destination = (output.resolve() if output else project) / 'conversion-report.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    write_report(destination, report)
    emit('Game Boy Advance run checked on tested scenarios; gameplay and hardware fidelity remain unverified.')
    return exported or host


def _export_player(project: Path, stage_root: Path, bios_code: Path, bios: Path, rom_file: Path, rom, title: str, sha1: str,
                   emit, presentation: dict | None = None) -> tuple[Path, dict | None]:
    """Build the player of this cartridge on the host kit. The publication (compaction, the games folder) is the batch's."""
    from . import __version__, gba_player
    from .core import dependencies, executable_name, toolchain
    from .platforms import sdl_install, sdl_library
    cmake, generator = toolchain()
    sdl = sdl_install()
    if not (sdl / sdl_library()).is_file():
        _, sdl, cmake, generator = dependencies(emit)
    file_name = executable_name(title)
    player = project / 'player'
    artwork = gba_player.prepare(player, stage_root, project / 'generated', bios_code, rom_file, bios, title=title,
                       name=Path(file_name).stem, sha1=sha1, sha256=rom.sha256, version=__version__, presentation=presentation)
    built = gba_player.build(player, cmake, generator, sdl, emit)
    emit(f'Game Boy Advance player: {file_name}.')
    return built, artwork
