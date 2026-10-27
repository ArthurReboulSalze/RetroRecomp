"""Game Boy (DMG) conversion using a pinned SM83 static recompiler."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import os
import re
import time
import zlib
from typing import Callable

from . import __version__
from .artwork import ArtworkError, prepare_icon
from .core import ConversionError, dependencies, executable_name, run, serialized_setup, slug
from .gameboy_runtime import adapt_generated_project
from .gameboy_build import preserve_unchanged_sources, share_native_bodies, compact_generated_dispatch
from .gameboy_boundary import adapt_bank_boundaries
from .gameboy_coverage import (ProbeScenario, TRACE_LIMIT, branch_entries, cpu_validation_scenarios,
                               probe_scenarios, read_entries, write_entries, entries_text)
from .library import atomic_json, atomic_text, entry_lock, library_root
from .knowledge import bundled_record, record_for
from .metadata import write_game_metadata
from .paths import ROOT, ASSETS, data_directory, games_root, boxart_cache_directory
from .systems import archive_rom
from .platforms import build_executable, cmake_target_args, build_jobs, target_id, available_cpus
from .toolchain import describe as toolchain_description


ENGINE_URL = "https://github.com/arcanite24/gb-recompiled.git"
ENGINE_REV = "9150f87d82fa98abcb6ea22329170463f9702eb8"
MAX_ROM_BYTES = 8 * 1024 * 1024
SUMMARY = re.compile(r"\[INTERP\] Summary: fallbacks=(\d+) interpreter_entries=(\d+) "
                     r"interpreter_instructions=(\d+) interpreter_cycles=(\d+)")
INVENTORY = re.compile(r"\[INTERP\] Fallback inventory: sites=(\d+) dropped=(\d+) complete=(yes|no)")
CPU_MATCH = re.compile(r"\[DIFF\] Matched generated and interpreter execution for (\d+) steps / (\d+) frames")
FALLBACK_SITE = re.compile(r"\[INTERP\] Fallback site #\d+ ([0-9A-Fa-f]+):([0-9A-Fa-f]+) "
                          r"reason=(\w+) entries=(\d+) instructions=(\d+) cycles=(\d+)")


@dataclass(frozen=True)
class GameBoyRom:
    path: Path
    data: bytes
    crc32: int
    sha256: str
    header_title: str
    cgb_flag: int
    system_id: str = "gb"

    def metadata(self) -> dict:
        return {"name": self.path.name, "bytes": len(self.data),
                "crc32": f"{self.crc32:08X}", "sha256": self.sha256,
                "header_title": self.header_title, "cgb_flag": f"{self.cgb_flag:02X}",
                "system_id": self.system_id}


def read_game_boy_rom(path: Path) -> GameBoyRom:
    path = path.resolve()
    if path.suffix.casefold() == ".zip":
        suffix, data = archive_rom(path)
        if suffix not in (".gb", ".bin", ".rom"):
            raise ConversionError("This ZIP does not contain a Game Boy .gb cartridge.")
    elif path.suffix.casefold() in (".gb", ".bin", ".rom"):
        with path.open("rb") as source:
            data = source.read(MAX_ROM_BYTES + 1)
    else:
        raise ConversionError("Choose a Game Boy .gb cartridge or single-ROM ZIP.")
    if not 0x8000 <= len(data) <= MAX_ROM_BYTES or len(data) % 0x4000:
        raise ConversionError("Invalid Game Boy cartridge size (expected 32 KiB to 8 MiB in 16 KiB banks).")
    cgb_flag = data[0x143]
    if cgb_flag == 0xC0:
        raise ConversionError("This cartridge requires Game Boy Color; the current profile targets original Game Boy.")
    title = data[0x134:0x143].split(b"\0", 1)[0].decode("ascii", errors="replace").strip()
    return GameBoyRom(path, data, zlib.crc32(data), hashlib.sha256(data).hexdigest(), title, cgb_flag)


@serialized_setup
def _dependencies(emit: Callable[[str], None]) -> tuple[Path, Path, Path, Path, str]:
    from .platforms import require_backend
    require_backend('gb')
    # Reuse the already-pinned SDL2 static build. The Game Boy compiler and
    # runtime remain separate from the Master System/ Game Gear CPU backend.
    _, sdl, cmake, generator = dependencies(emit)
    engine = ROOT / ".deps/gb-recompiled"
    if not engine.exists():
        emit("Downloading pinned Game Boy recompiler…")
        run(["git", "clone", ENGINE_URL, engine], timeout=600)
    current = run(["git", "-C", engine, "rev-parse", "HEAD"]).strip()
    if run(["git", "-C", engine, "status", "--porcelain"]).strip():
        raise ConversionError("The cached Game Boy compiler has local changes; refusing to use or replace them.")
    if current != ENGINE_REV:
        run(["git", "-C", engine, "fetch", "--depth", "1", "origin", ENGINE_REV], timeout=600)
        run(["git", "-C", engine, "checkout", "--detach", ENGINE_REV])
    if run(["git", "-C", engine, "rev-parse", "HEAD"]).strip() != ENGINE_REV:
        raise ConversionError("Unexpected Game Boy compiler revision.")
    build = engine / ('build-retrorecomp' if os.name == 'nt' else 'build-retrorecomp-' + target_id())
    compiler = build_executable(build / 'bin', 'gbrecomp')
    stamp = build / "retro-recomp-revision.txt"
    if not compiler.is_file() or not stamp.is_file() or stamp.read_text(encoding="ascii").strip() != ENGINE_REV:
        emit("Building the pinned Game Boy recompiler…")
        run([cmake, "-S", engine, "-B", build, "-G", generator, *cmake_target_args(),
             f"-DCMAKE_PREFIX_PATH={sdl.as_posix()}", "-DBUILD_TESTS=OFF"], timeout=600)
        run([cmake, "--build", build, "--config", "Release", "--target", "gbrecomp", "--parallel", build_jobs()],
            timeout=1800)
        if not compiler.is_file():
            raise ConversionError("Game Boy recompiler build produced no executable.")
        stamp.write_text(ENGINE_REV + "\n", encoding="ascii")
    return engine, compiler, sdl, cmake, generator


def _probe(executable: Path, build: Path, frames: int, trace: Path,
           scenario: ProbeScenario = ProbeScenario('boot')) -> dict:
    trace.unlink(missing_ok=True)
    command = [executable, "--headless", "--limit-frames", str(frames),
               "--report-interpreter-hotspots", "--trace-entries", trace]
    if scenario.input_script:
        command += ['--input', scenario.input_script]
    output = run(command,
                 cwd=build, log=build / "validation.log", timeout=600)
    if f'[LIMIT] Reached frame limit {frames}' not in output:
        raise ConversionError('Game Boy probe ended before the requested frame limit.')
    inventory = INVENTORY.search(output)
    if not inventory or inventory.group(3) != "yes":
        raise ConversionError("Game Boy fallback inventory is missing or incomplete.")
    match = SUMMARY.search(output)
    if match:
        fallback, entries, instructions, cycles = map(int, match.groups())
    elif "[INTERP] No interpreter fallback recorded." in output:
        fallback = entries = instructions = cycles = 0
    else:
        raise ConversionError("Game Boy interpreter use could not be measured.")
    sites = [{"bank": int(bank, 16), "address": address.upper(), "reason": reason,
              "entries": int(count), "instructions": int(ops), "cycles": int(ticks)}
             for bank, address, reason, count, ops, ticks in FALLBACK_SITE.findall(output)]
    return {"scenario": scenario.name, "input_script": scenario.input_script,
            "frames": frames, "interpreter_handoffs": fallback,
            "interpreter_entries": entries, "interpreter_instructions": instructions,
            "interpreter_cycles": cycles, "interpreter_percent": None,
            "fallback_sites": int(inventory.group(1)), "fallback_sites_dropped": int(inventory.group(2)),
            "fallback_details": sites,
            "trace_entries_bytes": trace.stat().st_size if trace.is_file() else 0}


def _cpu_compare(executable: Path, build: Path, frames: int,
                 scenario: ProbeScenario = ProbeScenario('boot')) -> str:
    command = [executable, "--differential", "--differential-frames", str(frames)]
    if scenario.input_script:
        command += ['--input', scenario.input_script]
    output = run(command,
                 cwd=build, log=build / f"validation-cpu-{scenario.name}.log", timeout=600)
    match = CPU_MATCH.search(output)
    if not match or int(match.group(2)) != frames:
        raise ConversionError("Game Boy CPU comparison did not report a completed match.")
    return match.group(0)


def _gb_parallelism(parallel_games: int) -> tuple[int, int]:
    """Bound compiler processes and independent CPU checks during batch work."""
    per_game = max(1, available_cpus() // parallel_games)
    return min(int(build_jobs()), per_game), 3 if per_game >= 6 else 2 if per_game >= 4 else 1


def _verified_trace(rom: GameBoyRom) -> Path | None:
    folder = library_root("gb") / rom.sha256
    try:
        record = json.loads((folder / 'trace.json').read_text(encoding="utf-8"))
        return _trace_from_record(folder, record, rom.sha256)
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return None


def _trace_from_record(folder: Path, record: dict, identity: str) -> Path | None:
    if record.get('rom_sha256') != identity or record.get('engine_revision') != ENGINE_REV:
        return None
    # A stop between trace replacement and manifest commit must not discard
    # the last verified library. The backup is bounded and only kept until
    # the new pair is committed; it is never trusted without its old checksum.
    for name in ('entries.trace', 'entries.trace.previous'):
        path = folder / name
        try:
            if (path.stat().st_size <= TRACE_LIMIT and
                    _trace_digest(path) == record.get('trace_sha256')):
                return path
        except OSError:
            pass
    return None


def _trace_digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _remember_trace(rom: GameBoyRom, trace: Path) -> None:
    incoming = read_entries(trace, len(rom.data))
    if not incoming:
        return
    folder = library_root("gb") / rom.sha256
    with entry_lock(folder):
        verified = _verified_trace(rom)
        previous = read_entries(verified, len(rom.data))
        entries = previous | incoming
        if entries == previous:
            return
        target = folder / "entries.trace"
        backup = folder / 'entries.trace.previous'
        if verified is not None and verified != backup:
            # Preserve exact old line endings for existing Windows checksums.
            with verified.open(encoding='ascii', newline='') as stream:
                atomic_text(backup, stream.read())
        atomic_text(target, entries_text(entries))
        atomic_json(folder / "trace.json", {"rom_sha256": rom.sha256,
            "title": rom.path.stem,
            "engine_revision": ENGINE_REV,
            "trace_sha256": _trace_digest(target),
            "entry_count": len(entries), "kind": "headless_observed_entries"})
        try:
            backup.unlink(missing_ok=True)
        except OSError:
            pass  # A reader can still hold it on Windows; next write retries.


def _known_entries(rom: GameBoyRom, *, imported: bool = True) -> set[tuple[int, int]]:
    """Entries a conversion starts from. Without `imported`, only this player's
    library and gameplay rows and the qualified bank: hints from other
    players guide a conversion but are remembered only once it observes them."""
    from .feedback import gb_entries, records
    if imported:
        own = gb_entries(rom)
        shared = record_for('gb', rom, ENGINE_REV).get('rom_entries', [])
    else:
        own = set()
        for row in records('gb', rom.sha256, 2):
            pc, bank = row.address, row.auxiliary
            offset = bank*0x4000 + (pc & 0x3fff)
            span = min(len(row.data), 0x4000 - (pc & 0x3fff))
            if (pc < 0x8000 and bank < len(rom.data)//0x4000 and
                    row.data and rom.data[offset:offset+span] == row.data[:span]):
                own.add((bank, pc))
        shared = bundled_record('gb', rom, ENGINE_REV).get('rom_entries', [])
    return own | read_entries(_verified_trace(rom), len(rom.data)) | {
        (bank, address) for bank, address in shared
        if bank < len(rom.data) // 0x4000 and address < 0x8000}


def memory_summary(rom: GameBoyRom) -> dict:
    trace = _verified_trace(rom)
    return {"sha256": rom.sha256, "directory": str(library_root("gb") / rom.sha256),
            "trace_bytes": trace.stat().st_size if trace else 0,
            "known": bool(_known_entries(rom)),
            "bundled_rom_entries": len(record_for('gb', rom, ENGINE_REV).get('rom_entries', [])),
            "kind": "headless_observed_entries"}


def list_memory() -> list[dict]:
    result = []
    for folder in sorted(library_root("gb").glob("*")):
        if not folder.is_dir() or not re.fullmatch(r"[0-9a-f]{64}", folder.name):
            continue
        try:
            record = json.loads((folder / "trace.json").read_text(encoding="utf-8"))
            trace = _trace_from_record(folder, record, folder.name)
            if trace is None or not trace.stat().st_size:
                continue
            result.append({"title": record.get("title") or "Game Boy", "sha256": folder.name,
                           "trace_bytes": trace.stat().st_size, "directory": str(folder)})
        except (OSError, ValueError, TypeError, AttributeError):
            continue
    return result


def convert_game_boy(rom_path: Path, *, title: str | None = None, output: Path | None = None,
                     profile: Path | None = None, passes: int = 3, frames: int = 3600,
                     backend: str = "banked", language: str = "en", cover: Path | None = None,
                     boxart_dir: Path | None = None, online_cover: bool = True,
                     use_cover: bool = True, icon_tags: bool = True,
                     gb_deep_validation: bool = True,
                     gb_parallel_games: int = 1,
                     standard_override: str | None = None,
                     scan_level: str | None = None,
                     emit: Callable[[str], None] = print) -> Path:
    from .batch import convert_batch, identify
    from .scan_levels import LEVELS, gameboy_budget
    level = scan_level or 'standard'
    if level not in LEVELS:
        raise ConversionError(f'Unknown scan level: {level!r}.')
    scan = gameboy_budget(level)
    if output is None:
        item = identify(rom_path)
        if title:
            item.title = title
        item.cover = cover
        record = convert_batch([item], games_root(), profile=profile,
            passes=passes, frames=frames, backend=backend, language=language,
            boxart_dir=boxart_dir, online_cover=online_cover, use_cover=use_cover,
            icon_tags=icon_tags, gb_deep_validation=gb_deep_validation, scan_level=level,
            standard_override=standard_override, emit=emit)
        if record["failed"]:
            raise ConversionError(record["games"][0]["message"])
        return Path(record["games"][0]["executable"])
    if profile is not None:
        raise ConversionError("Game Boy does not use Master System TOML profiles.")
    if standard_override not in (None, "dmg"):
        raise ConversionError("This Game Boy profile supports original DMG hardware only.")
    if not 1 <= passes <= 10 or not 1 <= frames <= 10000:
        raise ConversionError("Choose 1–10 passes and 1–10000 frames per test.")
    if not 1 <= gb_parallel_games <= 8:
        raise ConversionError("Concurrent games must be between 1 and 8.")
    compile_jobs, cpu_workers = _gb_parallelism(gb_parallel_games)
    started = time.perf_counter()
    stage_seconds = dict(setup=0.0, discovery=0.0, translation=0.0, build=0.0,
                         coverage_probes=0.0, cpu_validation=0.0)
    rom = read_game_boy_rom(rom_path)
    title = title or re.sub(r"\s*\([^)]*\)", "", rom.path.stem).strip()
    name = slug(title)
    storage_id = f"{name}-{rom.sha256[:12]}"
    project = ROOT / ".build" / f"gb_{name}_{rom.sha256[:12]}_{ENGINE_REV[:8]}"
    project.mkdir(parents=True, exist_ok=True)
    destination = output.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    from .feedback import ingest
    gameplay_feedback = ingest('gb', rom.sha256, destination, emit=emit)
    emit(f"ROM: {title}, {len(rom.data) // 1024} KB, CRC32 {rom.crc32:08X}; Game Boy DMG.")
    if gb_deep_validation:
        emit("Game Boy deep CPU validation enabled: extra instruction-by-instruction play checks "
             "add conversion time depending on the game. Native discovery is unchanged.")
    try:
        artwork = prepare_icon(project, rom.path, title,
            (boxart_dir or ROOT / "BoxArt/Game Boy").resolve(), explicit=cover,
            online=online_cover, enabled=use_cover,
            cache_directory=boxart_cache_directory('gb'),
            tags=(), system_id="gb", emit=emit)
    except (ArtworkError, OSError) as exc:
        raise ConversionError(str(exc)) from exc
    engine, compiler, sdl, cmake, generator = _dependencies(emit)
    (project / "rom.gb").write_bytes(rom.data)
    metadata = write_game_metadata(project, title, executable_name(title),
                                   light_phaser=False, icon=artwork["embedded"],
                                   standard="dmg", system_id="gb")
    notice = "Game Boy executable: retained component license notices.\n\n"
    for component, filename in (("RetroRecomp", "LICENSE"),
                                ("gb-recompiled", "licenses/gb-recompiled.md"),
                                ("Dear ImGui", "licenses/dear-imgui.md"),
                                ("xBR", "licenses/xbr.md"),
                                ("Noto fonts", "licenses/Noto.md"),
                                ("SDL2", "licenses/SDL2.md"),
                                ("Portable compiler runtime", "licenses/llvm-mingw.md")):
        notice += f"## {component}\n\n" + (ASSETS / filename).read_text(encoding="utf-8") + "\n\n"
    (project / "game_legal.md").write_text(notice, encoding="utf-8")
    (project / 'game_identity.bin').write_bytes(b'[Retro-Recomp]\0' + rom.sha256.encode('ascii') + b'\0')
    from .resources import embed_resources
    embed_resources(project, {102:project/'game_legal.md',104:project/'game_identity.bin'})
    with (project / "game_resources.rc").open("a", encoding="utf-8") as resource:
        resource.write('102 RCDATA "game_legal.md"\n')
    stage_seconds['setup'] = time.perf_counter() - started
    stage_started = time.perf_counter()
    trace_input = _verified_trace(rom)
    observed_entries = _known_entries(rom)
    static_entries = branch_entries(rom.data)
    imported_entries = len(observed_entries)
    if imported_entries:
        emit("Verified ROM-specific Game Boy entry trace found in the converter library.")
    emit(f"Game Boy extended discovery: {len(static_entries)} ROM branch entries; "
         f"{imported_entries} previously observed entries.")
    trace_input = project / 'compilation-entries.trace'
    # Quick skips the varied replay and the deep CPU comparison; extended and
    # thorough add reproducible pseudo-random routes seeded from the exact ROM.
    gb_deep_validation = bool(gb_deep_validation and scan['deep_allowed'])
    long_routes = ()
    if scan['route_count']:
        from .random_routes import long_routes as pseudo_random_routes
        long_routes = pseudo_random_routes('gb', rom.sha256, count=scan['route_count'],
                                           frames=scan['route_frames'], two_players=False)
        emit(f"Game Boy scan level {level}: {len(long_routes)} reproducible pseudo-random routes of "
             f"{long_routes[0].frames} frames.")
    scenarios = probe_scenarios(frames, varied=scan['varied'], long_routes=long_routes)
    stage_seconds['discovery'] = time.perf_counter() - stage_started
    checks: list[dict] = []
    final_checks: list[dict] = []
    executable = build_executable(project / 'build', 'game')
    trace_out = project / "observed.trace"
    # Entries the probes themselves reached: imported hints join the library
    # only from here, never because they were offered.
    reached: set[tuple[int, int]] = set()
    for number in range(1, passes + 1):
        compilation_entries = observed_entries | static_entries
        write_entries(trace_input, compilation_entries)
        emit(f"Game Boy pass {number}/{passes}: static SM83 translation and build…")
        command: list[str | Path] = [compiler, project / "rom.gb", "-o", project,
            "--runtime-dir", engine / "runtime", "--output-prefix", "game", "--no-comments",
            "--progress-json", project / "progress.jsonl"]
        if compilation_entries:
            command += ["--use-trace", trace_input]
        stage_started = time.perf_counter()
        with preserve_unchanged_sources(project):
            run(command, log=project / "build.log", timeout=1800)
            adapt_generated_project(project, storage_id, rom.sha256, title)
            boundary = adapt_bank_boundaries(project)
            shared_bodies = share_native_bodies(project)
            compact_dispatch = compact_generated_dispatch(project)
        stage_seconds['translation'] += time.perf_counter() - stage_started
        stage_started = time.perf_counter()
        run([cmake, "-S", project, "-B", project / "build", "-G", generator, *cmake_target_args(),
             "-DGBRECOMP_GENERATED_OPT_LEVEL=2",
             f"-DGBRECOMP_GENERATED_COMPILE_JOBS={compile_jobs}",
             f"-DCMAKE_PREFIX_PATH={sdl.as_posix()}"],
            log=project / "build.log", timeout=600)
        run([cmake, "--build", project / "build", "--config", "Release", "--parallel", str(compile_jobs)],
            log=project / "build.log", timeout=1800)
        if not executable.is_file():
            raise ConversionError("Game Boy generated project produced no executable.")
        stage_seconds['build'] += time.perf_counter() - stage_started
        final_checks = []
        for scenario in scenarios:
            scenario_trace = project / f'observed-{scenario.name}.trace'
            stage_started = time.perf_counter()
            check = _probe(executable, project, scenario.frames or frames, scenario_trace, scenario)
            check['wall_seconds'] = round(time.perf_counter() - stage_started, 6)
            stage_seconds['coverage_probes'] += check['wall_seconds']
            check['pass'] = number
            final_checks.append(check)
            checks.append(check)
            found = read_entries(scenario_trace, len(rom.data))
            reached |= found
            observed_entries.update(found)
            emit(f"Game Boy {scenario.name}: {check['interpreter_cycles']} fallback cycles, "
                 f"{check['fallback_sites']} sites in {frames} tested frames.")
        write_entries(trace_out, observed_entries)
        if all(check['interpreter_cycles'] == 0 for check in final_checks):
            emit('Game Boy: zero fallback cycles across all tested scenarios.')
            break
        if number == passes:
            break
        new_entries = observed_entries - compilation_entries
        if not new_entries:
            emit("No new ROM entries to compile; remaining fallback stays reported.")
            break
        emit(f"Game Boy: adding {len(new_entries)} observed ROM entries to the next pass.")
    validation_mode = 'deep' if gb_deep_validation else 'standard'
    emit(f"Comparing generated execution with the reference CPU ({validation_mode})…")
    comparison_scenarios = cpu_validation_scenarios(frames, deep=gb_deep_validation)
    for scenario, comparison_frames in comparison_scenarios:
        emit(f"Game Boy CPU {scenario.name}: comparing {comparison_frames} frames "
             "instruction by instruction…")

    def compare_one(item: tuple[ProbeScenario, int]) -> dict:
        scenario, comparison_frames = item
        check_started = time.perf_counter()
        cpu_comparison = _cpu_compare(executable, project, comparison_frames, scenario)
        return {'scenario': scenario.name, 'frames': comparison_frames,
                'input_script': scenario.input_script, 'result': cpu_comparison,
                'wall_seconds': round(time.perf_counter() - check_started, 6)}

    stage_started = time.perf_counter()
    if gb_deep_validation and cpu_workers > 1 and len(comparison_scenarios) > 1:
        with ThreadPoolExecutor(max_workers=cpu_workers) as executor:
            cpu_checks = list(executor.map(compare_one, comparison_scenarios))
    else:
        cpu_checks = [compare_one(item) for item in comparison_scenarios]
    stage_seconds['cpu_validation'] += time.perf_counter() - stage_started
    for check in cpu_checks:
        emit(f"Game Boy CPU {check['scenario']}: matching for {check['frames']} frames.")
    remembered = project / 'remembered.trace'
    write_entries(remembered, _known_entries(rom, imported=False) | reached)
    _remember_trace(rom, remembered)
    generated = json.loads((project / "game_metadata.json").read_text(encoding="utf-8"))
    report = {"tool": "Retro-Recomp", "version": __version__, "system": {"id": "gb", "name": "Game Boy"},
        "scan_level": level, "long_routes": [route.metadata() for route in long_routes],
        "rom": rom.metadata(), "backend": "gb-recompiled-sm83", "compiler": {"url": ENGINE_URL,
            "revision": ENGINE_REV, "license": "MIT"},
        "native_coverage": {"translated_functions": len(generated.get("functions", [])),
            "static_scan": "all_banks_and_short_branches", "percent": None,
            "static_branch_entries": len(static_entries), "imported_entries": imported_entries,
            "observed_rom_entries": len(observed_entries)},
        "generated_build": {"shared_bodies": shared_bodies, "dispatch": compact_dispatch,
                            "bank_boundaries": boundary, "reuse_identical_sources": True},
        "writable_native_helpers": {"guard": "live instruction signature per added instruction; data operands remain live",
            "scope": "WRAM/HRAM store-and-increment, unrolled copies, LCD-safe copy/fill and HRAM interrupt/DMA page-selection helpers; unknown/changed code keeps fallback"},
        "final_checks": final_checks, "history": checks,
        "native_validation": {"passed": True, "cpu_differential": cpu_checks[0]['result'],
            "mode": validation_mode, "scenarios": cpu_checks,
            "frames": min(frames, 30), "hardware_accuracy": False, "full_game": False},
        "reference_vdp_trace_match": None,
        "video_model": {"standard": "dmg", "visible_pixels": [160, 144],
            "palette": "monochrome grayscale by default; F5 switches directly to/from classic green",
            "hardware_accuracy_validated": False},
        "hardware_adaptations": {"apu": ["live_envelope_mix", "pulse_retrigger_duty_phase", "noise_shift_14_15_clock_stop"],
            "state_layout_changed": False, "independent_full_hardware_validation": False},
        "input_players": 1, "game_states": {"supported": True, "save_key": "F8", "load_key": "F9",
            "slots": 1, "rom_identity": "sha256"},
        "artwork": artwork, "windows_metadata": metadata,
        "game_tags": [], "peripheral": {"type": "joypad", "hardware_accuracy_validated": False},
        "runtime_learning": True, "runtime_feedback": gameplay_feedback, "library_identity": rom.sha256,
        "host_timing": {"audio_backlog_target_ms_default": 20, "audio_callback_frames_requested": 256,
            "audio_startup": "one_device_period_plus_10ms", "audio_native_format": True,
            "apu_sample_rate": 44100,
            "input_before_cpu_slice": True, "live_joyp_refresh_interval_us": 1000,
            "generated_optimization_level": 2, "physical_latency_measured": False},
        "build_executable": str(executable), "executable": executable.name, "toolchain": toolchain_description(),
        "build_directory": str(project),
        "stage_seconds": {key: round(value, 6) for key, value in stage_seconds.items()},
        "conversion_wall_seconds": round(time.perf_counter() - started, 6)}
    atomic_json(destination / "conversion-report.json", report)
    emit("Game Boy CPU comparisons passed. Hardware and full gameplay remain unverified.")
    emit(f"Game Boy conversion: {report['conversion_wall_seconds']:.1f}s total; "
         f"translation {stage_seconds['translation']:.1f}s, build {stage_seconds['build']:.1f}s, "
         f"coverage tests {stage_seconds['coverage_probes']:.1f}s, "
         f"CPU validation {stage_seconds['cpu_validation']:.1f}s ({validation_mode}).")
    return executable
