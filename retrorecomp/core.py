from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import csv
import unicodedata
import zlib
import time
from functools import wraps
from threading import Event, Lock, RLock
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from .library import GameMemory, entry_lock, library_root, read_observations, write_manifest, write_code_patterns
from .report_schema import write_report
from .conversion_common import (check_run_budget, convert_single, prepare_game_icon, probe_environment, replace_counted,
                                resolve_scan_level, spawn)
from .paths import ROOT, ASSETS, games_directory, games_root, data_directory
from . import __version__, hostkit, timings
from .i18n import log_text
from .publishing import publish_executable
from .cpu import prepare_cpu_headers, prepare_reference
from .peripherals import light_phaser_game, game_tags
from .validation import compare_execution, vdp_states
from .systems import MASTER_SYSTEM, archive_rom, profile_for_path
from .platforms import build_executable, cmake_target_args, build_jobs, target_id, claim_cache, sdl_install, sdl_library
from .toolchain import active as active_toolchain, suffix, describe as toolchain_description

ENGINE_REV = "224d5bb2c150a2c295033d35dec629ef9ee42940"
SDL_REV = "5d249570393f7a37e037abf22cd6012a4cc56a71"
_SHARED_SETUP_LOCK = RLock()
_SHARED_SETUP_DEPTH = 0


def serialized_setup(function):
    """Protect shared setup across threads and independent converter processes.

    Setup functions can call one another. The RLock and depth counter keep
    those calls reentrant without trying to acquire the same file range twice.
    ROM analysis, game compilation and validation run outside this short gate.
    """
    @wraps(function)
    def wrapper(*args, **kwargs):
        global _SHARED_SETUP_DEPTH
        with _SHARED_SETUP_LOCK:
            if _SHARED_SETUP_DEPTH:
                return function(*args, **kwargs)
            with entry_lock(ROOT / '.deps/shared-setup', timeout=1800):
                _SHARED_SETUP_DEPTH += 1
                try:
                    return function(*args, **kwargs)
                finally:
                    _SHARED_SETUP_DEPTH -= 1
    return wrapper


class ConversionError(RuntimeError):
    pass


class StopRequested(ConversionError):
    """The player pressed Stop: the running step was killed on purpose."""


# Stop, from the window: every build or validation process of the batch is
# registered while it runs, so it can be killed at once rather than finishing
# a conversion that may last minutes. Nothing is published before the end of a
# conversion, so an earlier export is never left half replaced.
_STOP = Event()
_PROCESSES: set[subprocess.Popen] = set()
_PROCESSES_LOCK = Lock()


def reset_stop() -> None:
    _STOP.clear()


def stop_requested() -> bool:
    return _STOP.is_set()


def stop_processes() -> int:
    """Kill the registered processes; later run_process calls raise at once."""
    _STOP.set()
    with _PROCESSES_LOCK:
        running = list(_PROCESSES)
    for process in running:
        try:
            process.kill()
        except OSError:
            pass
    return len(running)


def run_process(args, *, timeout=None, capture_output=False, input=None, **kwargs) -> subprocess.CompletedProcess:
    """subprocess.run for the conversion path, interruptible by Stop."""
    if _STOP.is_set():
        raise StopRequested('Arrêt demandé.')
    if capture_output:
        kwargs['stdout'] = kwargs['stderr'] = subprocess.PIPE
    with subprocess.Popen(args, **kwargs) as process:
        with _PROCESSES_LOCK:
            _PROCESSES.add(process)
        try:
            out, err = process.communicate(input, timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            raise
        finally:
            with _PROCESSES_LOCK:
                _PROCESSES.discard(process)
    if _STOP.is_set():
        raise StopRequested('Arrêt demandé.')
    return subprocess.CompletedProcess(args, process.returncode, out, err)


def module_fingerprint(name: str) -> str:
    """Hash compiler inputs even when PyInstaller stores code without .py files."""
    from types import CodeType
    from .compilation_inputs import code_fingerprint
    module = sys.modules[name]
    path = getattr(module, '__file__', None)
    if path and Path(path).is_file() and Path(path).suffix == '.py':
        code = compile(Path(path).read_bytes(), '', 'exec', dont_inherit=True, optimize=0)
    else:
        loader = getattr(module, '__loader__', None)
        code = loader.get_code(name) if loader and hasattr(loader, 'get_code') else None
    if not isinstance(code, CodeType):
        raise ConversionError(f'Cannot verify the bundled compiler module: {name}.')
    # PyInstaller extraction folders vary on each launch. Neither they nor a
    # developer's source path or the loader's constant interning may invalidate
    # otherwise identical caches and runtime state identities.
    return code_fingerprint(code)


@dataclass(frozen=True)
class Rom:
    path: Path
    data: bytes
    crc32: int
    sha256: str
    copier_header: bool
    header_offset: int | None
    region: int | None
    system_id: str = "sms"

    def metadata(self) -> dict:
        return {"name": self.path.name, "bytes": len(self.data),
                "crc32": f"{self.crc32:08X}", "sha256": self.sha256,
                "copier_header_removed": self.copier_header,
                "header_offset": self.header_offset, "region": self.region,
                "system_id": self.system_id}


def _read_rom(path: Path, system_id: str) -> Rom:
    path = path.resolve()
    suffix = ".gg" if system_id == "gg" else ".sms"
    if path.suffix.lower() not in ('.sms', '.gg', '.zip', '.bin', '.rom'):
        raise ConversionError(f"Choisis une ROM au format {suffix}.")
    if path.suffix.lower() == '.zip':
        archived_suffix, data = archive_rom(path)
        if archived_suffix not in ('.sms', '.gg', '.bin', '.rom'):
            raise ConversionError(f"Ce ZIP ne contient pas de ROM {suffix}.")
        source_suffix = archived_suffix
    else:
        data = path.read_bytes()
        source_suffix = path.suffix.lower()
    copier = len(data) % 16384 == 512
    if copier:
        data = data[512:]
    if len(data) < 8192 or len(data) > 4 * 1024 * 1024 or len(data) % 8192:
        raise ConversionError("Taille de ROM non prise en charge (8 Ko à 4 Mo, multiple de 8 Ko).")
    header = next((offset for offset in (0x7FF0, 0x3FF0, 0x1FF0)
                   if data[offset:offset + 8] == b"TMR SEGA"), None)
    region = data[header + 15] >> 4 if header is not None else None
    if system_id == "sms" and region in (5, 6, 7):
        raise ConversionError("Cette ROM est identifiée comme Game Gear ; cette version cible la Master System.")
    if system_id == "gg" and region in (3, 4):
        raise ConversionError("L'en-tête indique une ROM Master System, pas Game Gear.")
    if (source_suffix in ('.sms', '.gg') and source_suffix != suffix
            and region not in ((5, 6, 7) if system_id == 'gg' else (3, 4))):
        raise ConversionError(f"Choisis une ROM au format {suffix} : aucun en-tête ne confirme la console.")
    return Rom(path, data, zlib.crc32(data), hashlib.sha256(data).hexdigest(), copier, header, region, system_id)


def read_rom(path: Path) -> Rom:
    return _read_rom(path, "sms")


def read_game_gear_rom(path: Path) -> Rom:
    return _read_rom(path, "gg")


def video_standard(rom: Rom) -> str:
    """Compatibility wrapper for the Master System console profile."""
    return MASTER_SYSTEM.default_video_mode(rom.path)


def set_video_standard(config: str, standard: str) -> str:
    """Set one profile's [video] timing while preserving its other sections."""
    if standard not in MASTER_SYSTEM.video_modes:
        raise ConversionError("Le profil vidéo doit préciser ntsc ou pal.")
    import tomllib
    parsed = tomllib.loads(config)
    if "video" in parsed and not isinstance(parsed["video"], dict):
        raise ConversionError("Section [video] invalide dans le profil.")
    lines = config.splitlines(keepends=True)
    section_start = section_end = None
    for index, line in enumerate(lines):
        if re.match(r"^\s*\[video\]\s*(?:#.*)?$", line.strip()):
            section_start = index
            continue
        if section_start is not None and section_end is None and re.match(r"^\s*\[", line):
            section_end = index
            break
    if section_start is None:
        if "video" in parsed:
            raise ConversionError("Le profil vidéo doit utiliser la section [video].")
        result = config.rstrip("\r\n") + f'\n\n[video]\nstandard = "{standard}"\n'
    else:
        end = section_end if section_end is not None else len(lines)
        matches = [i for i in range(section_start + 1, end)
                   if re.match(r"^\s*standard\s*=", lines[i])]
        if len(matches) > 1:
            raise ConversionError("Le profil vidéo contient plusieurs valeurs standard.")
        if matches:
            lines[matches[0]] = f'standard = "{standard}"\n'
        else:
            lines.insert(section_start + 1, f'standard = "{standard}"\n')
        result = "".join(lines)
    if tomllib.loads(result).get("video", {}).get("standard") != standard:
        raise ConversionError("Impossible d'enregistrer le profil vidéo.")
    return result


def slug(title: str) -> str:
    value = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    value = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")[:60]
    if not value or value[0].isdigit():
        value = "Game_" + value
    if value.upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        value = "Game_" + value
    return value


def executable_name(title: str, *, suffix: str = '') -> str:
    """Keep the readable title, removing only Windows filename restrictions."""
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', title).strip().rstrip(' .')
    if not value:
        value = 'Game'
    if value.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}:
        value = '_' + value
    # Reserve the collision suffix *before* truncating. Otherwise long titles
    # produce the same filename for (2), (3), ... and name reservation never ends.
    value = value[:max(1, 150 - len(suffix))]
    if os.name == 'nt':
        value = value.encode('utf-16-le')[:max(2, 300 - len(suffix.encode('utf-16-le')))].decode('utf-16-le', errors='ignore')
    else:
        value = value.encode('utf-8')[:max(1, 240 - len(suffix.encode('utf-8')))].decode('utf-8', errors='ignore')
    return (value.rstrip(' .') or 'Game') + suffix + ('.exe' if os.name == 'nt' else '')


def run(args: list[str | Path], *, cwd: Path = ROOT, log: Path | None = None,
        emit: Callable[[str], None] = print, timeout: int = 600) -> str:
    command = [str(arg) for arg in args]
    from .toolchain import reset_incompatible_cache
    reset_incompatible_cache(command, cwd)
    result = run_process(command, cwd=cwd, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, encoding="utf-8", errors="replace", timeout=timeout,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    if log:
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as out:
            out.write("\n> " + subprocess.list2cmdline(command) + "\n" + result.stdout)
    if result.returncode:
        raise ConversionError(f"Commande interrompue ({result.returncode}).\n{result.stdout[-6500:]}")
    return result.stdout


def toolchain() -> tuple[Path, str]:
    if os.name != "nt":
        try:
            target_id()
        except RuntimeError as exc:
            raise ConversionError(str(exc)) from exc
        required = ('cmake', 'ninja', 'cc', 'c++', 'git', 'pkg-config')
        missing = [name for name in required if not shutil.which(name)]
        if missing:
            raise ConversionError('Missing Linux build tools: ' + ', '.join(missing))
        return Path(shutil.which('cmake')), 'Ninja'
    from . import toolchain as selection
    try:
        chosen = selection.select()
    except selection.ToolchainError as exc:
        raise ConversionError(str(exc)) from exc
    return chosen.cmake, chosen.generator


def dependencies_ready() -> bool:
    """Whether the shared pieces every conversion needs are already built:
    the pinned engine sources, the Z80 → C translator and the static SDL2."""
    try:
        dep = ROOT / ".deps"
        return ((dep / "smsggrecomp/external/z80-recomp-core/include/sms_runtime.h").exists()
                and build_executable(dep / ('recompiler-build' + suffix()), 'SmsRecomp').exists()
                and (sdl_install() / sdl_library()).exists())
    except Exception:
        return False


@serialized_setup
def dependencies(emit: Callable[[str], None] = print) -> tuple[Path, Path, Path, str]:
    cmake, generator = toolchain()
    dep = ROOT / ".deps"
    dep.mkdir(exist_ok=True)
    claim_cache(dep)
    log = dep / "setup.log"
    engine = dep / "smsggrecomp"
    sdl = dep / "SDL"
    for path, url, revision in ((engine, "https://github.com/mstan/smsggrecomp.git", ENGINE_REV),
                                (sdl, "https://github.com/libsdl-org/SDL.git", SDL_REV)):
        if not path.exists():
            emit(f"Téléchargement de {path.name}…")
            run(["git", "clone", url, path], log=log)
            run(["git", "-C", path, "checkout", "--detach", revision], log=log)
        current = run(["git", "-C", path, "rev-parse", "HEAD"]).strip()
        if current != revision:
            raise ConversionError(f"Version inattendue de {path.name} : {current}. Attendu : {revision}.")
    if not (engine / "external/z80-recomp-core/include/sms_runtime.h").exists():
        run(["git", "-C", engine, "submodule", "update", "--init", "--recursive"], log=log)
    # The runner mirrors oversized Sega bank register values onto physical ROM.
    # Upstream discovery rejected those same values, producing empty routines in
    # Alex Kidd (which writes 0x82..0x87 to an eight-bank cartridge).
    source = dep / "recompiler-src"
    parser_source = (engine / "recompiler/src/rom_parser.c").read_text(encoding="utf-8")
    parser_source = replace_once(parser_source,
        "size_t off = (size_t)bank * SMS_BANK_SIZE + slot_off;",
        "size_t off = ((size_t)bank * SMS_BANK_SIZE + slot_off) % rom->size;")
    generator_source = patched_generator_source((engine / "recompiler/src/code_generator.c").read_text(encoding="utf-8"))
    main_source = (engine / "recompiler/src/main_sms.c").read_text(encoding="utf-8")
    main_source = replace_once(main_source, '    bool flat_step = false;', '''    bool flat_step = false;
    bool banked_step = false;''')
    main_source = replace_once(main_source, '        else if (strcmp(argv[i],"--flat-step")==0) flat_step = true;', '''        else if (strcmp(argv[i],"--flat-step")==0) flat_step = true;
        else if (strcmp(argv[i],"--banked-step")==0) banked_step = true;''')
    main_source = replace_once(main_source, '    if (flat_step) {', '''    if (banked_step) {
        extern void cg_emit_banked_step(const SmsRom *, const GameConfig *, const char *);
        char dir[260]; dirname_of(game_toml, dir, sizeof(dir));
        char gendir[300]; snprintf(gendir, sizeof(gendir), "%sgenerated", dir);
        cg_emit_banked_step(&rom, &cfg, gendir);
        rom_free(&rom); return 0;
    }
    if (flat_step) {''')
    expected = hashlib.sha256((parser_source + generator_source + main_source).encode()).hexdigest()
    marker = source / "smsrecomp-patch.sha256"
    patch_changed = not marker.exists() or marker.read_text() != expected
    if patch_changed:
        shutil.copytree(engine / "recompiler", source, dirs_exist_ok=True, ignore=shutil.ignore_patterns("build"))
        (source / "src/rom_parser.c").write_text(parser_source, encoding="utf-8")
        (source / "src/code_generator.c").write_text(generator_source, encoding="utf-8")
        (source / "src/main_sms.c").write_text(main_source, encoding="utf-8")
        marker.write_text(expected)
    recomp_build = dep / ('recompiler-build' + suffix())
    recomp = build_executable(recomp_build, 'SmsRecomp')
    compiled_marker = recomp_build / "compiled.sha256"
    if patch_changed or not recomp.exists() or not compiled_marker.exists() or compiled_marker.read_text() != expected:
        emit("Compilation du traducteur Z80 → C…")
        run([cmake, "-S", source, "-B", recomp_build, "-G", generator, *cmake_target_args()], log=log)
        run([cmake, "--build", recomp_build, "--config", "Release", "--parallel", build_jobs()], log=log)
        compiled_marker.write_text(expected)
    prefix = sdl_install()
    if not (prefix / sdl_library()).exists():
        emit("Compilation de SDL2 statique (première utilisation)…")
        sdl_build = sdl / ("build" + suffix())
        run([cmake, "-S", sdl, "-B", sdl_build, "-G", generator, *cmake_target_args(),
            "-DSDL_SHARED=OFF", "-DSDL_STATIC=ON", "-DSDL_TEST=OFF", "-DSDL_TESTS=OFF",
            *(["-DSDL_FORCE_STATIC_VCRT=ON"] if active_toolchain() == "msvc" else []),
            f"-DCMAKE_INSTALL_PREFIX={prefix.as_posix()}"], log=log)
        run([cmake, "--build", sdl_build, "--config", "Release", "--parallel", build_jobs()], log=log)
        run([cmake, "--install", sdl_build, "--config", "Release"], log=log)
    return engine, prefix, cmake, generator


@serialized_setup
def prepare_native_source() -> Path:
    """Stage the common runtime before any game's CMake build reads it."""
    native_source = ROOT / ".build/native-source"
    native_source.mkdir(parents=True, exist_ok=True)
    for source in (ASSETS / "native").iterdir():
        if not source.is_file():
            continue
        target = native_source / source.name
        if not target.exists() or target.read_bytes() != source.read_bytes():
            shutil.copy2(source, target)
    # The player shell of the Master System and the Game Gear is the host kit (one adapter for both).
    hostkit.stage(native_source, "sms")
    return native_source


def replace_once(source: str, old: str, new: str) -> str:
    return replace_counted(source, old, new, error=lambda old: ConversionError(
        f"L'interface du moteur a changé ; adaptation nécessaire : {old[:90]!r}"))


def patched_generator_source(generator_source: str) -> str:
    """The pinned Z80 generator with our patches applied (the text the unit test checks)."""
    generator_source = replace_once(generator_source,
        '    fprintf(o,"        do {\\n");',
        '''    fprintf(o,"        int sms_block_first = 1;\\n        uint16_t sms_block_pc = g_dbg_pc;\\n        do {\\n");
    fprintf(o,"            if (!sms_block_first) s->r = (uint8_t)((s->r & 0x80) | ((s->r + 2) & 0x7f));\\n");
    fprintf(o,"            sms_block_first = 0;\\n");''')
    # A repeating block instruction that goes on (BC or B not exhausted, no CPIR/CPDR match) leaves the flags of the NMOS repeat
    # cycle: X and Y from the high byte of the instruction's address (the PC is wound back to it) and, for INIR/INDR/OTIR/OTDR, H
    # and P adjusted from B. An interrupt accepted between two iterations pushes AF with them. The banked emitter and the corrected
    # reference (retrorecomp/cpu.py) already follow this rule, checked against independent vectors; the address is read once
    # from g_dbg_pc before the loop (the runner also restores g_dbg_pc after an accepted interrupt, see prepare_functions_irq).
    generator_source = replace_once(generator_source,
        "    /* post-body tick: this iteration's effect already ran (see sms_tick_post) */\n",
        '''    fprintf(o,"            if (%s) {\\n", contc);
    fprintf(o,"                s->f = (uint8_t)((s->f & ~0x28) | ((sms_block_pc >> 8) & 0x28));\\n");
    if (grp >= 2) fprintf(o,"                { uint8_t b = s->b; if (s->f & Z80_FLAG_C) { int neg = (s->f & Z80_FLAG_N) != 0; "
        "z80f_set(s, Z80_FLAG_H, (b & 15) == (neg ? 0 : 15)); b = (uint8_t)(b + (neg ? -1 : 1)); } "
        "if (!z80_parity8(b & 7)) s->f ^= Z80_FLAG_P; }\\n");
    fprintf(o,"            }\\n");
    /* post-body tick: this iteration's effect already ran (see sms_tick_post) */
''')
    # A RET that pops a slot the function pushed itself ("push continuation; jump; ret", "push de; ret"): the generated RET was
    # `sp += 2; return;`, which resumes the CALLER, while the Z80 continues at the popped address. Each function now keeps its entry
    # SP (the slot of its own return address). A RET with SP below it pops a local address: the continuation runs as a nested call
    # (a function entry, or the counted hybrid interpreter), whose own RET pops the real return address, then this function returns
    # with the SP its caller expects. A RET at the entry SP is the ordinary return, one above it unwinds several frames (the call
    # sites already propagate that). The nesting is bounded (256): beyond it the old behaviour applies.
    generator_source = replace_once(generator_source,
        '        "#include \\"%s_funcs.h\\"\\n\\n", pfx, pfx);',
        '''        "#include \\"%s_funcs.h\\"\\n"
        "static uint16_t rr_ret_nest;\\n"
        "/* A tail jump to another function: if the callee returned with SP below this function's own return slot, it consumed\\n"
        " * a continuation this function pushed, so the Z80 continues there (the popped address) and not in the caller. */\\n"
        "#define RR_TAIL(call) do { call; if ((int16_t)(g_z80.sp - _esp) < 2 && rr_ret_nest < 256) { "
        "uint16_t _p = sms_read16((uint16_t)(g_z80.sp - 2)); rr_ret_nest++; call_by_address(_p); rr_ret_nest--; } return; } while (0)\\n\\n", pfx, pfx);''')
    generator_source = replace_once(generator_source,
        '        if (nm) fprintf(o,"%s(); return; }\\n", nm);\n        else    fprintf(o,"call_by_address(0x%04X); return; }\\n", T);',
        '        if (nm) fprintf(o,"RR_TAIL(%s()); }\\n", nm);\n        else    fprintf(o,"RR_TAIL(call_by_address(0x%04X)); }\\n", T);')
    generator_source = replace_once(generator_source,
        '        if (nm) fprintf(o,"        %s(); return;\\n", nm);\n        else    fprintf(o,"        call_by_address(0x%04X); return;\\n", T);',
        '        if (nm) fprintf(o,"        RR_TAIL(%s());\\n", nm);\n        else    fprintf(o,"        RR_TAIL(call_by_address(0x%04X));\\n", T);')
    generator_source = replace_once(generator_source,
        '                    fprintf(o,"        call_by_address(%s); return;\\n", idx);            /* tail jump */',
        '                    fprintf(o,"        RR_TAIL(call_by_address(%s));\\n", idx);            /* tail jump */')
    generator_source = replace_once(generator_source,
        '    fprintf(o,"    sms_enter(0x%04X);\\n", fe->addr);',
        '    fprintf(o,"    sms_enter(0x%04X);\\n    uint16_t _esp = s->sp; (void)_esp;\\n", fe->addr);')
    generator_source = replace_once(generator_source,
        '            fprintf(o,"        s->sp = (uint16_t)(s->sp + 2); return;\\n");',
        '''            fprintf(o,"        if ((int16_t)(s->sp - _esp) < 0 && rr_ret_nest < 256) { uint16_t _p = sms_read16(s->sp); "
                      "s->sp = (uint16_t)(s->sp + 2); rr_ret_nest++; call_by_address(_p); rr_ret_nest--; return; }\\n");
            fprintf(o,"        s->sp = (uint16_t)(s->sp + 2); return;\\n");''')
    generator_source = replace_once(generator_source,
        '            fprintf(o,"        if (%s) { s->cyc += 6; s->sp = (uint16_t)(s->sp + 2); return; }\\n", cond(cc));',
        '''            fprintf(o,"        if (%s) { s->cyc += 6; "
                      "if ((int16_t)(s->sp - _esp) < 0 && rr_ret_nest < 256) { uint16_t _p = sms_read16(s->sp); "
                      "s->sp = (uint16_t)(s->sp + 2); rr_ret_nest++; call_by_address(_p); rr_ret_nest--; return; } "
                      "s->sp = (uint16_t)(s->sp + 2); return; }\\n", cond(cc));''')
    generator_source = replace_once(generator_source,
        "static void write_dispatch(const char *path, const char *pfx, const FuncList *fl){",
        "static void write_dispatch(const char *path, const char *pfx, const FuncList *fl, const SmsRom *rom){")
    generator_source = replace_once(generator_source, "write_dispatch(path, pfx, fl);", "write_dispatch(path, pfx, fl, rom);")
    generator_source = replace_once(generator_source,
        '            fprintf(d,"    case 0x%04X: %s(); return;\\n", a, fl->items[vidx[0]].name);',
        '''            int bank = fl->items[vidx[0]].bank;
            int physical = ((bank >= 0) ? bank : (a >> 14)) % rom->num_banks;
            if (a < 0x0400)
                fprintf(d,"    case 0x%04X: %s(); return;\\n", a, fl->items[vidx[0]].name);
            else
                fprintf(d,"    case 0x%04X: if ((sms_slot_bank(addr) %% %d) == %d) { %s(); return; } break;\\n", a, rom->num_banks, physical, fl->items[vidx[0]].name);''')
    generator_source = replace_once(generator_source,
        'fprintf(d,"    case 0x%04X: switch (sms_slot_bank(0x%04X)){\\n", a, a);',
        'fprintf(d,"    case 0x%04X: switch (sms_slot_bank(0x%04X) %% %d){\\n", a, a, rom->num_banks);')
    generator_source = replace_once(generator_source, "int rb = (b >= 0) ? b : (a >> 14);",
        "int rb = ((b >= 0) ? b : (a >> 14)) % rom->num_banks;")
    # A call or jump to a paged address (>= $0400) must never become a direct C
    # call: one bank variant seen by the static walk does not prove which bank
    # is mapped when the code runs. Only the fixed first KiB may be called
    # directly; every other target goes through call_by_address, whose dispatch
    # checks the bank mapped in the slot (sms_slot_bank).
    generator_source = replace_once(generator_source,
        "static const char *name_for_target(uint16_t T){",
        """static const char *name_for_target(uint16_t T){
    /* Retro-Recomp: only the fixed first KiB may be called directly; the rest
     * dispatches on the bank mapped at run time (call_by_address). */
    if (T >= 0x0400) return NULL;""")
    # HALT (functions engine only; the banked emitter handles HALT before it reaches emit_op).
    # Two defects of the pinned generator, both met on the Master System and the Game Gear:
    # 1. The interrupt that ends a HALT pushes the address AFTER the HALT, as the interpreter does.
    #    The runner pushes its breadcrumb, which is the HALT's own address, one byte lower: a
    #    different return address stayed in the stale stack bytes (Alex Kidd in Miracle World).
    # 2. An interrupt handler may drop the interrupted context (pop the saved return and the callers
    #    above it, then RET to an ancestor): the "abort N frames" idiom that the call sites already
    #    propagate. A HALT is where the interrupt arrives in a wait loop, and it is not a call site:
    #    execution went on after it with SP above its frame, the next RET unwound the whole C stack
    #    and the run ended (Factory Panic). SP above its value at the HALT now ends the function.
    generator_source = replace_once(generator_source,
        '    if (in->is_halt){ fprintf(o,"        sms_halt();\\n"); return; }',
        '''    if (in->is_halt){
        /* Retro-Recomp: the interrupt that ends a HALT pushes the address after it, and a handler
         * that dropped the halted frame (SP above its value here) ends this function. */
        fprintf(o,"        { uint16_t _hsp = s->sp; g_dbg_pc = (uint16_t)(g_dbg_pc + 1); sms_halt(); if ((int16_t)(s->sp - _hsp) > 0) return; }\\n");
        return;
    }''')
    generator_source += "\n" + (ASSETS / "native/banked_emitter.inc").read_text(encoding="utf-8")
    return generator_source


def prepare_reference_irq(glue: str) -> str:
    """Sample the shared VDP interrupt level afresh for every CPU step."""
    glue = replace_once(glue, 'static uint64_t reference_cycle_base;', '''static uint64_t reference_cycle_base;
static bool reference_sample_irq(void) {
    /* /INT is a level input. A request blocked by DI/EI must not survive a
     * later VDP status read that deasserts it. Preserve the same start-of-step
     * sampling contract as banked native execution. */
    g_hz.int_pending = 0;
    if (vdp_irq_asserted() && g_hz.iff1) {
        z80_gen_int(&g_hz, 0xFF);
        return true;
    }
    return false;
}''')
    glue = replace_once(glue,
        'if (!g_diff_freeze && vdp_irq_asserted() && g_hz.iff1 && !g_hz.int_pending){',
        'if (!g_diff_freeze && reference_sample_irq()){')
    glue = replace_once(glue,
        '            if (vdp_irq_asserted() && g_hz.iff1 && !g_hz.int_pending)\n'
        '                z80_gen_int(&g_hz, 0xFF);          /* IM1 vector 0x0038 */',
        '            reference_sample_irq();             /* IM1 vector 0x0038 */')
    return glue


def prepare_functions_irq(glue: str) -> str:
    """The functions engine accepts an interrupt where the reference CPU and the banked engine do.

    Those two sample /INT before an instruction and accept it after that instruction, with the
    return address of the one that follows. The runner of the functions engine accepted it at the
    boundary where the VDP made it visible, one instruction earlier: the pushed address, the
    register values the handler saw and the cycle count moved by one instruction in polling
    loops, so the reference comparison failed on Alex Kidd in Miracle World and Factory Panic.
    The line is now sampled at one boundary and accepted at the next. Also, a VDP port access that
    raises or clears /INT now brings the next sync to the next instruction instead of the next
    scanline (functions engine only)."""
    # A VDP port access can raise /INT (enabling the frame interrupt while its flag is pending) or
    # clear it (a status read) between two line boundaries. The next sync must come at the next
    # instruction, not at the next scanline, or the interrupt is accepted up to a line late.
    glue = replace_once(glue, 'uint8_t sms_io_in(uint8_t p){\n    if (p >= 0x40 && p < 0xC0) sync_vdp_for_io(g_z80.cyc);',
        'static uint8_t sms_io_in_body(uint8_t p){\n    if (p >= 0x40 && p < 0xC0) sync_vdp_for_io(g_z80.cyc);')
    glue = replace_once(glue, 'void sms_io_out(uint8_t p, uint8_t v){\n    if (lightphaser_enabled() && p < 0x40 && (p & 1)) {',
        'static void sms_io_out_body(uint8_t p, uint8_t v){\n    if (lightphaser_enabled() && p < 0x40 && (p & 1)) {')
    glue = replace_once(glue, '''void sms_set_sync_deadline(void){
    g_sync_deadline = vdp_irq_asserted() ? g_z80.cyc + 1 : g_next_line_cyc;
}''', '''static bool g_irq_armed;   /* /INT was sampled at the previous boundary: accepted at this one */
static void sms_io_deadline(void){
    /* The instruction is already charged: the next tick must sync, not the one after it. */
    g_sync_deadline = (vdp_irq_asserted() || g_irq_armed) ? g_z80.cyc : g_next_line_cyc;
}
uint8_t sms_io_in(uint8_t p){
    uint8_t value = sms_io_in_body(p);
    if (p >= 0x80 && p < 0xC0) sms_io_deadline();   /* VDP data/control port */
    return value;
}
void sms_io_out(uint8_t p, uint8_t v){
    sms_io_out_body(p, v);
    if (p >= 0x80 && p < 0xC0) sms_io_deadline();
}
void sms_set_sync_deadline(void){
    g_sync_deadline = (vdp_irq_asserted() || g_irq_armed) ? g_z80.cyc + 1 : g_next_line_cyc;
}''')
    glue = replace_once(glue, '''    advance_vdp(g_z80.cyc);
    if (vdp_irq_asserted() && g_z80.iff1 && !g_z80.ei_block)
        take_irq();
    sms_set_sync_deadline();''', '''    advance_vdp(g_z80.cyc);
    {
        /* Same contract as the reference CPU: sample, execute one instruction, then accept. The
         * handler's own RET ends inside this call, so the boundary after it is checked here too
         * (the last instruction of a handler is often followed by a second interrupt), with the
         * address of the interrupted instruction as the one pushed. */
        const uint16_t interrupted = g_dbg_pc;
        while (g_irq_armed && g_z80.iff1 && !g_z80.ei_block) {
            g_irq_armed = false;
            g_dbg_pc = interrupted;
            take_irq();
        }
        g_dbg_pc = interrupted;
        g_irq_armed = vdp_irq_asserted() && g_z80.iff1;
    }
    sms_set_sync_deadline();''')
    glue = replace_once(glue, '''    state_to_hz();
    g_hz.pc = addr;''', '''    g_irq_armed = false;    /* the interpreter samples from its first instruction */
    state_to_hz();
    g_hz.pc = addr;''')
    # A RET that unwinds every generated frame is the end of the C call chain, not of the program:
    # a game that reloads SP and returns into its main code ("ld sp,nn ... ret", seen on Alex Kidd:
    # The Lost Stars) continues where the Z80 does, at the address that RET popped.
    glue = replace_once(glue, '''#else
        call_by_address(0x0000);         /* reset entry; runs the game */
#endif''', '''#else
        {
            uint16_t next = 0x0000;
            uint64_t seen = g_frame;
            long idle = 0;
            for (;;) {
                call_by_address(next);
                next = sms_read16((uint16_t)(g_z80.sp - 2));
                if (g_frame != seen) { seen = g_frame; idle = 0; }
                else if (++idle > 100000) break;     /* no frame in 100000 returns: stop as before */
            }
        }
#endif''')
    return replace_once(glue, '    g_enter_pos = 0; g_dbg_pc = 0;', '    g_enter_pos = 0; g_dbg_pc = 0; g_irq_armed = false;')


def prepare_runtime(game: Path, rom: Rom, title: str, engine: Path, standard: str = "ntsc",
                    functions: bool = False) -> None:
    if standard not in ("ntsc", "pal"):
        raise ConversionError("Video standard must be 'ntsc' or 'pal'.")
    # Linux window icons use SDL, independently of PE resources or loose files.
    from io import BytesIO
    icon_data = b''
    if (game / 'game-icon.png').is_file():
        from PIL import Image
        with Image.open(game / 'game-icon.png') as image:
            buffer = BytesIO()
            image.convert('RGBA').save(buffer, format='BMP')
            icon_data = buffer.getvalue()
    legal = '\n\n'.join((ASSETS / name).read_text(encoding='utf-8') for name in
        ('THIRD_PARTY_NOTICES.md', 'licenses/SDL2.md', 'licenses/z80-recomp-core.md', 'licenses/superzazu-z80.md', 'licenses/xbr.md', 'licenses/Noto.md'))
    (game / 'embedded_icon.h').write_text('#include <stddef.h>\nextern const unsigned char rr_icon_data[];\nextern const size_t rr_icon_size;\nextern const char rr_game_legal[];\n', encoding='ascii')
    (game / 'embedded_icon.c').write_text('#include "embedded_icon.h"\nconst unsigned char rr_icon_data[]={' +
        ','.join(str(n) for n in icon_data or b'\0') + '};\nconst size_t rr_icon_size=' + str(len(icon_data)) +
        ';\nconst char rr_game_legal[]=' + json.dumps(legal, ensure_ascii=True) + ';\n', encoding='ascii')
    clocks = (engine / "runner/include/sms_clocks.h").read_text(encoding="utf-8")
    clocks = replace_once(clocks, "#define SMS_VBLANK_LINE       192", "#define SMS_VBLANK_LINE       193")
    clocks = clocks.replace("the frame (VBlank) interrupt latches at the start of line 192.",
                            "the frame (VBlank) interrupt latches at the start of line 193.")
    if standard == "pal":
        clocks = replace_once(clocks, "#define SMS_Z80_HZ            3579545u", "#define SMS_Z80_HZ            3546893u")
        clocks = replace_once(clocks, "#define SMS_LINES_PER_FRAME   262", "#define SMS_LINES_PER_FRAME   313")
        clocks = clocks.replace("Z80 clock (NTSC)", "Z80 clock (PAL)")
        clocks = clocks.replace("SMS_LINES_PER_FRAME   313        /* NTSC", "SMS_LINES_PER_FRAME   313        /* PAL ")
        clocks = clocks.replace("NTSC: 262 lines/frame, ~228 Z80 T-states/line", "PAL: 313 lines/frame, ~228 Z80 T-states/line")
        clocks = clocks.replace("SMS PAL detection is a later concern - NTSC is\n * the bring-up target (the Sonic SMS/GG titles are NTSC-timed in practice).",
                                "The PAL Master System uses 313 lines per frame and a roughly 3.547 MHz Z80.")
    (game / "sms_clocks.h").write_text(clocks, encoding="utf-8")
    header = '''#include <stdint.h>\n#include <stddef.h>\nextern const uint8_t sms_rom[];
extern const size_t sms_rom_size;\nextern const uint32_t sms_rom_crc32;
extern const char sms_game_title[];\nint smsrecomp_interpreter_active(void);
extern const char sms_rom_sha256[];
extern const char sms_game_slug[];
extern const int sms_light_phaser, sms_light_phaser_hcounter_offset, sms_light_phaser_trigger_p2;
uint64_t smsrecomp_interpreter_cycles(void);\n'''
    (game / "embedded_rom.h").write_text(header, encoding="utf-8")
    with (game / "embedded_rom.c").open("w", encoding="utf-8") as out:
        out.write('#include "embedded_rom.h"\nconst uint8_t sms_rom[] = {\n')
        for offset in range(0, len(rom.data), 24):
            out.write(",".join(f"0x{value:02X}" for value in rom.data[offset:offset + 24]) + ",\n")
        out.write(f'}};\nconst size_t sms_rom_size = sizeof(sms_rom);\nconst uint32_t sms_rom_crc32 = 0x{rom.crc32:08X}u;\n')
        out.write(f"const char sms_game_title[] = {json.dumps(title, ensure_ascii=True)};\n")
        out.write(f'const char sms_rom_sha256[] = "{rom.sha256}";\n')
        out.write(f'const char sms_game_slug[] = "{slug(title)}";\n')
        phaser = light_phaser_game(rom.crc32, rom.path.name) if rom.system_id == "sms" else None
        out.write(f'const int sms_light_phaser = {int(phaser is not None)};\n')
        out.write(f'const int sms_light_phaser_hcounter_offset = {phaser.hcounter_offset if phaser else 20};\n')
        out.write(f'const int sms_light_phaser_trigger_p2 = {int(bool(phaser and phaser.trigger_on_p2))};\n')
    prepare_cpu_headers(game, engine)
    prepare_reference(game, engine)
    glue = (engine / "runner/glue.c").read_text(encoding="utf-8")
    glue = '#include "video_frame.h"\n#include "lightphaser.h"\n#include "embedded_rom.h"\n' + glue
    glue = replace_once(glue, '#include "include/sms_clocks.h"', '#include "sms_clocks.h"')
    glue = replace_once(glue, 'uint8_t sms_io_in(uint8_t p){', '''static void advance_vdp(uint64_t cyc);
static bool smsrecomp_in_io, smsrecomp_stop_pending;
static void sync_vdp_for_io(uint64_t cyc) {
    /* Ports must see the current raster line, but a host/frame stop must not
     * unwind an unfinished IN/OUT instruction or its reference callback. */
    smsrecomp_in_io = true;
    advance_vdp(cyc);
    smsrecomp_in_io = false;
}
uint8_t sms_io_in(uint8_t p){
    if (p >= 0x40 && p < 0xC0) sync_vdp_for_io(g_z80.cyc);''')
    glue = replace_once(glue, 'void sms_io_out(uint8_t p, uint8_t v){', '''void sms_io_out(uint8_t p, uint8_t v){
    if (p >= 0x40 && p < 0xC0) sync_vdp_for_io(g_z80.cyc);''')
    glue = replace_once(glue, 'longjmp(g_quit_env, 1);      /* user closed the window */',
        'smsrecomp_stop_pending = true; /* finish the current CPU instruction */')
    glue = replace_once(glue, '''    if (g_frame_limit && g_frame >= g_frame_limit && g_running)
        longjmp(g_quit_env, 1);''', '''    if (g_frame_limit && g_frame >= g_frame_limit && g_running)
        smsrecomp_stop_pending = true;''')
    glue = replace_once(glue, '    while (cyc >= g_next_line_cyc){',
        '    while (cyc >= g_next_line_cyc && !smsrecomp_stop_pending){')
    glue = replace_once(glue, '''        if (g_vdp.line == 0) frame_completed();
    }
}''', '''        if (g_vdp.line == 0) frame_completed();
    }
    if (smsrecomp_stop_pending && g_running && !smsrecomp_in_io)
        longjmp(g_quit_env, 1); /* only at a completed CPU step */
}''')
    if glue.count('vdp_render_frame(g_fb);') != 2:
        raise ConversionError("L'interface de présentation vidéo du moteur a changé.")
    glue = glue.replace('vdp_render_frame(g_fb);', 'smsrecomp_video_present(g_fb);')
    glue = replace_once(glue, 'frame,vram_h,cram_h,reg_h,r8,r9,r0,r1\\n',
        'frame,vram_h,cram_h,reg_h,ram_h,r8,r9,r0,r1,sp,pixels_h\\n')
    glue = replace_once(glue, '%02X,%02X,%02X,%02X,%04X\\n",',
        '%02X,%02X,%02X,%02X,%04X,%016llx\\n",')
    glue = replace_once(glue, 'g_vdp.reg[8], g_vdp.reg[9], g_vdp.reg[0], g_vdp.reg[1], g_z80.sp);',
        'g_vdp.reg[8], g_vdp.reg[9], g_vdp.reg[0], g_vdp.reg[1], g_z80.sp, (unsigned long long)smsrecomp_video_hash());')
    glue = replace_once(glue, 'static uint8_t   g_pad1, g_pad2;', '''static uint8_t   g_pad1, g_pad2;
static void (*g_host_input_refresh)(void);
void smsrecomp_set_input_refresh(void (*refresh)(void)) { g_host_input_refresh = refresh; }''')
    glue = replace_once(glue, '    g_io_in_count[p]++;', '''    g_io_in_count[p]++;
    /* Only live host input opts in. Other machine ports and deterministic
     * scripted/headless runs retain their existing timing and state. */
    if ((p >= 0xC0 || (g_is_gg && p == 0x00)) && g_host_input_refresh)
        g_host_input_refresh();''')
    glue = replace_once(glue, '            return vdp_hcounter(sub);', '''            if (lightphaser_enabled()) return lightphaser_hcounter(g_z80.cyc);
            return vdp_hcounter(sub);''')
    glue = replace_once(glue, '    /* $C0-$FF controller ports, active low (0 = pressed).', '''    if (lightphaser_enabled())
        return (p & 1) ? lightphaser_dd(g_pad2, g_z80.cyc) : lightphaser_dc(g_pad1, g_pad2);
    /* $C0-$FF controller ports, active low (0 = pressed).''')
    glue = replace_once(glue, 'void sms_io_out(uint8_t p, uint8_t v){', '''void sms_io_out(uint8_t p, uint8_t v){
    if (lightphaser_enabled() && p < 0x40 && (p & 1)) {
        int sub = (int)((int64_t)g_z80.cyc - ((int64_t)g_next_line_cyc - SMS_CYC_PER_LINE));
        lightphaser_control(v, g_z80.cyc, vdp_hcounter(sub));
    }''')
    glue = replace_once(glue, '#include "external/superzazu/z80.h"', '#include "runtime_reference.h"')
    glue = replace_once(glue, 'static bool g_hz_init;', 'static bool g_hz_init;\nstatic uint64_t reference_cycle_base;')
    glue = prepare_reference_irq(glue)
    glue = replace_once(glue, 'static uint8_t hyb_in   (z80 *z, uint8_t p){ (void)z; return sms_io_in(p); }', '''static uint8_t hyb_in(z80 *z, uint8_t p){
    uint64_t saved = g_z80.cyc; g_z80.cyc = reference_cycle_base + z->cyc;
    uint8_t value = sms_io_in(p); g_z80.cyc = saved; return value;
}''')
    glue = replace_once(glue, 'static void    hyb_out  (z80 *z, uint8_t p, uint8_t v){ (void)z; sms_io_out(p, v); }', '''static void hyb_out(z80 *z, uint8_t p, uint8_t v){
    uint64_t saved = g_z80.cyc; g_z80.cyc = reference_cycle_base + z->cyc;
    sms_io_out(p, v); g_z80.cyc = saved;
}''')
    glue = replace_once(glue, 'static void state_to_hz(void){', '''static void state_to_hz(void){
    reference_cycle_base = g_z80.cyc;
    g_hz.q = g_z80.q; g_hz.p = g_z80.p;''')
    glue = replace_once(glue, 'static void state_from_hz(void){', '''static void state_from_hz(void){
    g_z80.q = g_hz.q; g_z80.p = g_hz.p;''')
    glue = replace_once(glue, 'void glue_run_interp(void){', 'void glue_run_interp(void){\n    reference_cycle_base = 0;')
    glue = '#include "paths.h"\n' + glue
    glue = replace_once(glue, 'static const char *g_miss_path = "dispatch_misses.log";', '')
    glue = replace_once(glue, 'FILE *f = fopen(g_miss_path, "a");',
        'FILE *f = NULL; /* fallback is counted/reported; no duplicate disk log */')
    glue = replace_once(glue, 'remove(g_miss_path);',
        '/* Existing logs are preserved; normal startup writes nothing. */')
    start = glue.index("typedef struct { uint16_t addr; uint8_t b0,b1,b2; uint32_t crc; } ManifestSig;")
    end = glue.index("\nstatic void mb_dump(void){", start)
    glue = glue[:start] + (ASSETS / "native/manifest.inc").read_text(encoding="utf-8") + glue[end:]
    start = glue.index("bool glue_load_rom(const char *path){")
    end = glue.index("\nvoid glue_init(", start)
    glue = glue[:start] + '''#include "embedded_rom.h"
bool glue_load_rom(const char *path){
    (void)path;
    free(g_rom);
    g_rom = (uint8_t*)malloc(sms_rom_size);
    if (!g_rom) return false;
    memcpy(g_rom, sms_rom, sms_rom_size);
    g_rom_size = sms_rom_size;
    return true;
}
''' + glue[end:]
    glue = replace_once(glue, "static void hybrid_interpret(uint16_t addr){",
        "static int smsrecomp_interp_depth;\nstatic void hybrid_interpret(uint16_t addr){\n    smsrecomp_interp_depth++;\n    g_hybrid_calls++;")
    glue = replace_once(glue,
        "        g_z80.cyc = (g_sync_deadline > g_z80.cyc) ? g_sync_deadline\n                                                  : g_z80.cyc + SMS_CYC_PER_LINE;",
        "        g_z80.cyc += 4;\n        g_z80.r = (uint8_t)((g_z80.r & 0x80) | ((g_z80.r + 1) & 0x7f));")
    glue = replace_once(glue, "        z80_step(&g_hz); g_frame_ic++;\n        advance_vdp(base + g_hz.cyc);", """        smsrecomp_feedback_at(g_hz.pc);
        uint32_t previous_cycles = g_hz.cyc;
        z80_step(&g_hz); g_frame_ic++;
        g_hybrid_cyc += g_hz.cyc - previous_cycles;
        advance_vdp(base + g_hz.cyc);""")
    glue = replace_once(glue,
        "    g_hybrid_cyc += g_hz.cyc;            /* cycles this routine spent in the interpreter */\n    g_hybrid_calls++;",
        "    smsrecomp_interp_depth--;")
    # Count in-flight interpreter work too: a frame limit can longjmp out of a
    # routine before it returns, so upstream's end-of-routine tally misses it.
    glue = replace_once(glue, "static void advance_vdp(uint64_t cyc){", """static uint64_t smsrecomp_total_cycles;
static uint64_t smsrecomp_measured_guest_cycles;
static void advance_vdp(uint64_t cyc){
    if (cyc >= smsrecomp_measured_guest_cycles)
        smsrecomp_total_cycles += cyc - smsrecomp_measured_guest_cycles;
    smsrecomp_measured_guest_cycles = cyc;""")
    glue = replace_once(glue,
        "g_z80.cyc ? 100.0 * (double)g_hybrid_cyc / (double)g_z80.cyc : 0.0,",
        "smsrecomp_total_cycles ? 100.0 * (double)g_hybrid_cyc / (double)smsrecomp_total_cycles : 0.0,")
    glue = replace_once(glue,
        "g_z80.cyc ? 100.0 * (double)(g_z80.cyc - g_hybrid_cyc) / (double)g_z80.cyc : 0.0);",
        "smsrecomp_total_cycles ? 100.0 * (double)(smsrecomp_total_cycles - g_hybrid_cyc) / (double)smsrecomp_total_cycles : 0.0);")
    glue = replace_once(glue,
        "(unsigned long long)g_hybrid_cyc, (unsigned long long)g_z80.cyc,",
        "(unsigned long long)g_hybrid_cyc, (unsigned long long)smsrecomp_total_cycles,")
    glue = replace_once(glue, "void sms_dispatch_miss(uint16_t addr){", '''void sms_dispatch_miss(uint16_t addr){
    if (getenv("SMSRECOMP_STRICT")) {
        manifest_record(addr);
        fprintf(stderr, "[Retro-Recomp] STRICT STOP: unrecompiled address %04X, banks %02X/%02X/%02X\\n",
                addr, g_bank[0], g_bank[1], g_bank[2]);
        exit(3);
    }''')
    glue += '''\nint smsrecomp_interpreter_active(void){
#ifdef SMSRECOMP_BANKED_AOT
    return banked_last_interpreted || smsrecomp_interp_depth > 0;
#else
    return smsrecomp_interp_depth > 0;
#endif
}
uint64_t smsrecomp_interpreter_cycles(void){ return g_hybrid_cyc; }\n'''
    glue += '''\nuint64_t smsrecomp_input_time_us(void) {
    return g_z80.cyc / SMS_Z80_HZ * 1000000 + g_z80.cyc % SMS_Z80_HZ * 1000000 / SMS_Z80_HZ;
}\n'''
    glue = '''#ifdef SMSRECOMP_BANKED_AOT
static int banked_last_interpreted;
static void smsrecomp_banked_run(void);
static void smsrecomp_banked_fallback(unsigned short addr);
static void smsrecomp_banked_stats(void);
#endif
static void smsrecomp_cpu_record(void);
static int smsrecomp_state_pending;
static void (*smsrecomp_state_callback)(int, int);
static void smsrecomp_state_service(void);
''' + glue
    glue = replace_once(glue, "    hybrid_interpret(addr);", '''#ifdef SMSRECOMP_BANKED_AOT
    smsrecomp_banked_fallback(addr);
#else
    hybrid_interpret(addr);
#endif''')
    glue = replace_once(glue, '        call_by_address(0x0000);         /* reset entry; runs the game */', '''#ifdef SMSRECOMP_BANKED_AOT
        smsrecomp_banked_run();
#else
        call_by_address(0x0000);         /* reset entry; runs the game */
#endif''')
    glue = replace_once(glue, '    mb_dump();                           /* bank-alias probe summary (env-gated) */', '''#ifdef SMSRECOMP_BANKED_AOT
    smsrecomp_banked_stats();
    smsrecomp_cpu_record();
#endif
    mb_dump();                           /* bank-alias probe summary (env-gated) */''')
    glue = replace_once(glue, '    fprintf(stderr, "[interp] reference run stopped after %llu frames\\n",', '''    state_from_hz(); g_z80.pc = g_hz.pc; g_z80.cyc = g_hz.cyc;
    smsrecomp_cpu_record();
    fprintf(stderr, "[interp] reference run stopped after %llu frames\\n",''')
    # The debug harness references the function-form dispatcher; it is not
    # active in this backend, whose production loop always uses the guest PC.
    glue += "\n" + (ASSETS / "native/gamestate.inc").read_text(encoding="utf-8")
    glue += "\n" + (ASSETS / "native/banked_runtime.inc").read_text(encoding="utf-8")
    # A reset exits through the runtime's existing longjmp, discarding all
    # generated C continuations. Also reset every execution/callback state that
    # upstream initialized only once per process, before entering reset again.
    glue = replace_once(glue, "void glue_init(bool is_gg, uint64_t frame_limit){", """void glue_init(bool is_gg, uint64_t frame_limit){
    g_frame_ic = g_irq_taken = g_irq_reentrant = 0;
    g_sync_depth = g_sync_maxdepth = 0;
    g_running = false;
    g_frame_cb = NULL; g_input_cb = NULL; g_audio_sink = NULL;
    g_host_input_refresh = NULL;
    lightphaser_reset(sms_light_phaser != 0, sms_light_phaser_hcounter_offset);
    g_dump_frame = (uint64_t)-1; g_dump_path = NULL;
    glue_set_vdp_trace(NULL); glue_psg_log_close();
    memset(g_io_out_count, 0, sizeof(g_io_out_count));
    memset(g_io_in_count, 0, sizeof(g_io_in_count));
    memset(g_fb, 0, sizeof(g_fb));
    memset(&g_hz, 0, sizeof(g_hz)); g_hz_init = false;
    smsrecomp_interp_depth = 0; smsrecomp_total_cycles = 0;
    smsrecomp_measured_guest_cycles = 0;
    smsrecomp_state_pending = 0; smsrecomp_state_callback = NULL;
    smsrecomp_in_io = smsrecomp_stop_pending = false;
    g_mb_pos = 0; memset(g_interp_cyc, 0, sizeof(g_interp_cyc));
    g_in_diff = 0; g_diff_freeze = g_diff_active = 0; g_diff_icount = 0;
    g_enter_pos = 0; g_dbg_pc = 0;
    memset(g_enter_ring, 0, sizeof(g_enter_ring));
""")
    # The PSG renders lazily: frames are produced in the same order and from
    # the same register values, only later. It catches up to the guest time
    # the eager timeline had reached before each PSG write, before the line
    # steps that drain it at the end of a frame, and before a quick state.
    glue = replace_once(glue, '    if (g_audio_sink && cyc > g_psg_cyc){',
                        '    if (g_audio_sink && cyc > g_psg_cyc && cyc >= g_next_line_cyc){')
    glue = replace_once(glue, 'void sms_io_out(uint8_t p, uint8_t v){', '''static uint64_t smsrecomp_measured_guest_cycles;
static void psg_catch_up(void){
    if (g_audio_sink && smsrecomp_measured_guest_cycles > g_psg_cyc){
        psg_advance((uint32_t)(smsrecomp_measured_guest_cycles - g_psg_cyc));
        g_psg_cyc = smsrecomp_measured_guest_cycles;
    }
}
void sms_io_out(uint8_t p, uint8_t v){''')
    glue = replace_once(glue, 'if (g_is_gg && p == 0x06) psg_write_stereo(v);',
                        'if (g_is_gg && p == 0x06) { psg_catch_up(); psg_write_stereo(v); }')
    glue = replace_once(glue, '        psg_write(v); return;', '        psg_catch_up(); psg_write(v); return;')
    if functions:
        glue = prepare_functions_irq(glue)
    (game / "runtime_glue.c").write_text(glue, encoding="utf-8")
    video = (engine / "runner/video/sms_vdp.c").read_text(encoding="utf-8")
    # Keep the pinned port/IRQ core. Replace its end-of-frame snapshot renderer
    # in a local copy with our raster renderer; never edit the dependency.
    marker = '/* ---- mode-4 rendering ---- */'
    if video.count(marker) != 1:
        raise ConversionError("L'interface vidéo du moteur a changé.")
    video = video[:video.index(marker)] + (ASSETS / "native/video_mode4.inc").read_text(encoding="utf-8")
    video = video.replace("Frame interrupt latches at the start of line 192", "Frame interrupt latches at the start of line 193")
    video = video.replace("/* SMS NTSC mode-4 V-counter: 0x00..0xDA, then a jump-back to 0xD5 (line 219)\n     * running to 0xFF (line 261) — total 262 lines. Matches GPGX vc_table\n     * {0xDA,0xF2}. (Active display is lines 0..191 < 0xDA, so this only changes\n     * vblank-region reads — but it's now hardware-correct everywhere.) */",
       "/* Master System mode-4 V-counter: both standards wrap in vertical blank. */")
    if standard == "pal":
        video = replace_once(video, "l <= 0xDA ? l : l - 6", "l <= 0xF2 ? l : l - 57")
    old_counter = '''    /* Line-interrupt counter: active across lines 0..192, reload otherwise. */
    if (g_vdp.line <= SMS_ACTIVE_LINES){
        if (g_vdp.line_counter == 0){
            g_vdp.line_counter = g_vdp.reg[10];
            g_vdp.line_irq = true;
        } else {
            g_vdp.line_counter--;
        }
    } else {
        g_vdp.line_counter = g_vdp.reg[10];
    }

'''
    video = replace_once(video, old_counter, "")
    video = replace_once(video, '''    if (g_vdp.line >= SMS_LINES_PER_FRAME){
        g_vdp.line = 0;
    }''', '''    if (g_vdp.line >= SMS_LINES_PER_FRAME){
        g_vdp.line = 0;
    }
''' + old_counter.rstrip())
    video = '#include "video_frame.h"\n' + video
    video = replace_once(video, '    g_vdp.line_counter = 0xFF;', '''    g_vdp.line_counter = 0xFF;
    smsrecomp_video_reset();''')
    video = replace_once(video, 'void vdp_step_line(void){', '''void vdp_step_line(void){
    smsrecomp_video_end_line(g_vdp.line);''')
    video = replace_once(video, '        g_vdp.line = 0;\n    }', '''        g_vdp.line = 0;
    }
    smsrecomp_video_begin_line(g_vdp.line);''')
    (game / "runtime_video.c").write_text(video, encoding="utf-8")
    audio = (engine / "runner/audio/sn76489.c").read_text(encoding="utf-8")
    audio = replace_once(audio, '#include "sn76489.h"', '#include "audio/sn76489.h"')
    # Render whole runs between channel events; identical samples.
    audio = replace_once(audio, 'void psg_init(void)\n{',
        (ASSETS / "native/psg_runs.inc").read_text(encoding="utf-8") + 'void psg_init(void)\n{')
    audio = replace_once(audio, '''        for (size_t i = 0; i < chunk; i++)
            sn_render_frame(&s_sn,
                            &s_scratch[(s_scratch_write + i) * 2],
                            &s_scratch[(s_scratch_write + i) * 2 + 1]);''',
        '        rr_psg_render_frames(&s_sn, &s_scratch[s_scratch_write * 2], chunk);')
    audio += "\n" + (ASSETS / "native/psg_state.inc").read_text(encoding="utf-8")
    (game / "runtime_audio.c").write_text(audio, encoding="utf-8")
    main = (engine / "runner/main.c").read_text(encoding="utf-8")
    main = replace_once(main, '#include "host_sdl.h"', '#include "host_sdl.h"\n#include "host_control.h"')
    main = replace_once(main, '    glue_set_pad1(host_get_pad1());     /* push this frame\'s keyboard state to the CPU */',
        '    glue_set_pad1(host_get_pad1());\n    glue_set_pad2(host_get_pad2());')
    main = replace_once(main, 'is_gg ? "Sonic (GG) - recompiled" : "Sonic 1 (SMS) - recompiled"', "sms_game_title")
    main = replace_once(main, '            glue_set_frame_callback(sdl_frame_cb);', '''            glue_set_frame_callback(sdl_frame_cb);
            if (!g_press_n) smsrecomp_set_input_refresh(host_refresh_input);''')
    main = '#include "runtime_feedback.h"\n#include "embedded_rom.h"\n' + main
    main = replace_once(main, '    if (interp){', '    rr_feedback_start(!interp && want_window);\n    if (interp){')
    main = replace_once(main, "int main(int argc, char **argv){", """int main(int argc, char **argv){
    g_press_n = 0;
    g_audio_live = false;
    _putenv_s("SMSRECOMP_REFERENCE", "");
""")
    main = replace_once(main, "    if (interp){", '    if (interp){\n        _putenv_s("SMSRECOMP_REFERENCE", "1");')
    main = replace_once(main, 'fprintf(stderr,"[runner] SDL window init failed; running headless\\n");',
        '{ fprintf(stderr,"[runner] SDL window init failed\\n"); return 2; }')
    if os.name != 'nt':
        main = '#define _putenv_s(k,v) ((v)[0] ? setenv(k,v,1) : unsetenv(k))\n' + main
    (game / "runtime_main.c").write_text(main, encoding="utf-8")
    from .feedback import stage
    stage(game, rom.system_id, rom.sha256, cmake=False)


def default_config(rom: Rom) -> str:
    known = ASSETS / "profiles" / f"alex_kidd_{rom.crc32:08x}.toml" if rom.system_id == "sms" else Path()
    if known.is_file():
        import tomllib
        config = known.read_text(encoding="utf-8")
        if tomllib.loads(config).get("game", {}).get("sha256") == rom.sha256:
            return config
    return f'''# Experimental discovery profile; compatibility unverified.
[game]
output_prefix = "game"
platform = "{rom.system_id}"
rom = "rom.{rom.system_id}"
crc32 = 0x{rom.crc32:08X}
[mapper]
kind = "sega"
[functions]
extra = []
blacklist = []
'''


def probe(executable: Path, directory: Path, frames: int, *, strict: bool = False,
          press: list[str] | None = None, reference: bool = False) -> dict:
    executable, directory = executable.resolve(), directory.resolve()
    log = directory / "runtime.log"
    args = [str(executable), "--headless", "--frames", str(frames), "--log", str(log),
            "--vdp-trace", str(directory / "vdp.csv"), "--dump-frame", str(frames),
            "--dump-out", str(directory / "frame.png")]
    if strict:
        args.append("--strict")
    if reference:
        args.append("--interp")
    for value in press or []:
        args.extend(["--press", value])
    # Automated/reference probes stay isolated from the user's library. Their
    # verified observations are imported deliberately by convert(), not by the
    # reference interpreter or diagnostic launches.
    env = probe_environment(("SMSRECOMP_STRICT",), SMSRECOMP_LIBRARY_DIR=str(directory / "learning"),
        RETRO_RECOMP_LIBRARY_DIR=str(directory / "learning"), RETRO_RECOMP_LEARNING="1")
    started = time.perf_counter()
    result = spawn(args, cwd=directory, env=env, timeout=max(60, frames // 15), stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, phase='reference_runs' if reference else 'native_runs')
    text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
    completed = re.search(r"stopped after (\d+) frames; dispatch misses: (\d+)", text)
    percent = re.search(r"([\d.]+)% interp / ([\d.]+)% static", text)
    output = {"requested_frames": frames, "exit_code": result.returncode,
        "wall_seconds": round(time.perf_counter() - started, 6),
        "completed_frames": int(completed[1]) if completed else None,
        "dispatch_misses": int(completed[2]) if completed else None,
        "interpreter_percent": float(percent[1]) if percent else None,
        "static_percent": float(percent[2]) if percent else None,
        "strict": strict, "scripted_input": press or [], "reference": reference}
    output["passed"] = result.returncode == 0 and output["completed_frames"] == frames
    cycles = re.search(r"\[exec\] hybrid\(interp\): (\d+) calls, (\d+) of (\d+) Z80 cyc", text)
    if cycles:
        output.update(interpreter_calls=int(cycles[1]), interpreter_cycles=int(cycles[2]), total_cycles=int(cycles[3]))
    cpu = re.search(r"\[cpu\] (\{[^\n]+\})", text)
    if cpu:
        output["final_cpu"] = json.loads(cpu[1])
    banked = re.search(r"\[banked\] native_steps=(\d+) halt_steps=(\d+) fallback_steps=(\d+) banks_seen=(\d+)/(\d+)/(\d+)", text)
    if banked:
        output["banked"] = {"native_steps": int(banked[1]), "halt_steps": int(banked[2]),
            "fallback_steps": int(banked[3]), "banks_seen": [int(banked[i]) for i in (4, 5, 6)]}
        guards = re.search(r"\[banked-guards\] native_steps=(\d+)", text)
        if guards:
            output["banked"]["guarded_native_steps"] = int(guards[1])
        prefixes = re.search(r"\[banked-prefixes\] native_fragments=(\d+)", text)
        if prefixes:
            output["banked"]["native_prefix_fragments"] = int(prefixes[1])
    (directory / "result.json").write_text(json.dumps(output, indent=2), encoding="utf-8")
    return output


def import_previous(rom: Rom, destination: Path, memory: GameMemory) -> int:
    """Migrate older outputs only when their report identifies the exact ROM."""
    candidates = {destination}
    for previous_root in (ROOT / 'output', games_directory()):
        if previous_root.exists():
            candidates.update(path.parent for path in previous_root.rglob('conversion-report.json'))
    added = 0
    # A game's portable library can live next to any output directory, including
    # flat batch exports. Import only this exact ROM and recheck all byte hashes.
    for parent in (destination, *destination.parents):
        portable = GameMemory(rom, parent / "datas/library").directory
        if portable.exists() and portable.resolve() != memory.directory.resolve():
            added += memory.import_manifest(portable / "observations.log")["added"]
            memory.import_code_patterns(portable / "native.patterns")
    for directory in candidates:
        try:
            report = json.loads((directory / "conversion-report.json").read_text(encoding="utf-8"))
            if report.get("rom", {}).get("sha256") == rom.sha256:
                added += memory.import_manifest(directory / "dispatch_manifest.txt")["added"]
                memory.import_code_patterns(directory / "native-patterns.txt")
                memory.import_code_patterns(directory / "native.patterns")
        except (OSError, ValueError, AttributeError):
            continue
    return added


def compiler_signature(game: Path) -> str:
    from .compilation_inputs import input_bytes, state_native_files
    digest = hashlib.sha256()
    # Master System and Game Gear own the same native files: the listed ones (retrorecomp/stamp_inputs.py),
    # not whatever sits in native/.
    for source in [game / "runtime_glue.c", game / "runtime_main.c", game / "runtime_video.c", game / "runtime_audio.c", game / "sms_clocks.h", game / "game.toml",
                   game / "embedded_rom.c", game / "embedded_rom.h",
                   game / "runtime_reference.c", game / "runtime_reference.h", game / "sms_runtime.h", game / "z80_ops.h",
                   *sorted((game / "generated").glob("*.c")), ROOT / ".deps/recompiler-src/src/rom_parser.c",
                   ROOT / ".deps/recompiler-src/src/code_generator.c", ROOT / ".deps/recompiler-src/src/main_sms.c",
                   game / "game_resources.rc", game / "game.ico",
                   *state_native_files("sms")]:
        if source.is_file():
            digest.update(source.name.encode()); digest.update(input_bytes(source, source.name))
    digest.update(ENGINE_REV.encode()); digest.update(SDL_REV.encode())
    return digest.hexdigest()


def convert(rom_path: Path, *, title: str | None = None, output: Path | None = None,
            profile: Path | None = None, passes: int = 3, frames: int = 1200,
            backend: str = "banked", language: str = "en",
            cover: Path | None = None, boxart_dir: Path | None = None,
            online_cover: bool = True, use_cover: bool = True, icon_tags: bool = True,
            standard_override: str | None = None,
            md_advanced_scan: bool = False,
            scan_level: str | None = None,
            publish_result: bool = True,
            emit: Callable[[str], None] = print) -> Path:
    system = profile_for_path(rom_path)
    if os.name != 'nt' and system.id not in ('sms', 'gg'):
        raise ConversionError(f'{system.name}: this Linux prototype currently qualifies Master System and Game Gear only.')
    if system.id in ('md', 'snes'):
        from .console16 import convert16
        return convert16(rom_path, system_id=system.id, title=title, output=output,
            profile=profile, passes=passes, frames=frames, backend=backend, language=language,
            cover=cover, boxart_dir=boxart_dir, online_cover=online_cover, use_cover=use_cover,
            icon_tags=icon_tags, standard_override=standard_override, md_advanced_scan=md_advanced_scan,
            scan_level=scan_level, publish_result=publish_result, emit=emit)
    if system.id == "gb":
        from .gameboy import convert_game_boy
        return convert_game_boy(rom_path, title=title, output=output, profile=profile,
            passes=passes, frames=frames, backend=backend, language=language,
            cover=cover, boxart_dir=boxart_dir, online_cover=online_cover,
            use_cover=use_cover, icon_tags=icon_tags, standard_override=standard_override,
            scan_level=scan_level, emit=emit)
    if system.id == "nes":
        from .nes import convert_nes
        return convert_nes(rom_path, title=title, output=output, profile=profile,
            passes=passes, frames=frames, backend=backend, language=language,
            cover=cover, boxart_dir=boxart_dir, online_cover=online_cover,
            use_cover=use_cover, icon_tags=icon_tags, standard_override=standard_override,
            scan_level=scan_level, emit=emit)
    if output is None:
        # Single-ROM exports use the same names, reports and replacement policy
        # as the GUI/batch. The batch invokes this compiler with an explicit
        # report directory, so compilation itself is unchanged.
        return convert_single(rom_path, games_root(), title=title, cover=cover, success_only=True, profile=profile,
            passes=passes, frames=frames, backend=backend, language=language,
            boxart_dir=boxart_dir, online_cover=online_cover, use_cover=use_cover, icon_tags=icon_tags,
            standard_override=standard_override, scan_level=scan_level,
            emit=emit)
    original_emit = emit
    emit = lambda text: original_emit(log_text(text, language))
    if backend not in ("functions", "banked"):
        raise ConversionError("Backend inconnu : functions ou banked attendu.")
    check_run_budget(passes, frames, "Choisis 1 à 10 passes et 1 à 10000 images par test.")
    banked = backend == "banked"
    from .scan_levels import sega_budget
    level = resolve_scan_level(scan_level)
    scan = sega_budget(level)
    rom = system.read_rom(rom_path)
    title = title or re.sub(r"\s*\([^)]*\)", "", rom.path.stem).strip()
    name = slug(title)
    destination = output.resolve()
    game = ROOT / ".build" / (f"{system.id}_{name}_{rom.crc32:08X}_{rom.sha256[:12]}" + ("_banked" if banked else ""))
    game.mkdir(parents=True, exist_ok=True)
    destination.mkdir(parents=True, exist_ok=True)
    log = game / "build.log"
    emit(f"ROM : {title}, {len(rom.data) // 1024} Ko, CRC32 {rom.crc32:08X}")
    default_art = ROOT / 'BoxArt' / ('Game Gear' if system.id == 'gg' else '')
    from .paths import boxart_cache_directory
    artwork = prepare_game_icon(game, rom.path, title, boxart_dir or default_art,
        explicit=cover, online=online_cover, enabled=use_cover, cache_directory=boxart_cache_directory(system.id),
        tags=game_tags(rom.crc32, rom.path.name) if icon_tags and system.id == "sms" else (),
        system_id=system.id, emit=emit)
    engine, sdl, cmake, generator = dependencies(emit)
    from .feedback import ingest
    gameplay_feedback = ingest(system.id, rom.sha256, destination, emit=emit)
    memory = GameMemory(rom, library_root(system.id) if system.id != "sms" else None)
    imported = import_previous(rom, destination, memory)
    saved_manifest = ASSETS / "profiles" / f"{rom.crc32:08x}.manifest"
    if saved_manifest.exists():
        memory.import_manifest(saved_manifest)
    memory_before = memory.summary()
    emit(f"Mémoire du jeu : {memory_before['rom_entries']} entrées ROM vérifiées, "
         f"{memory_before['ram_entries']} observations RAM ; {imported} importées des anciennes parties.")
    rom_filename = f"rom.{system.id}"
    (game / rom_filename).write_bytes(rom.data)
    saved_recipe = None
    if profile:
        import tomllib
        config = profile.read_text(encoding="utf-8")
        parsed = tomllib.loads(config)
        if parsed.get("game", {}).get("crc32") != rom.crc32:
            raise ConversionError("Le profil ne correspond pas au CRC32 de cette ROM.")
        if parsed["game"].get("sha256", rom.sha256) != rom.sha256:
            raise ConversionError("Le profil ne correspond pas au SHA256 de cette ROM.")
        if (parsed["game"].get("output_prefix") != "game" or parsed["game"].get("rom") != rom_filename or
                parsed["game"].get("platform") != system.id):
            raise ConversionError(f'Le profil doit cibler {system.name} et rom="{rom_filename}".')
    else:
        saved_recipe = memory.recipe(ENGINE_REV)
        config = saved_recipe or default_config(rom)
        if saved_recipe:
            emit("Profil de compilation reconnu dans la bibliothèque.")
    import tomllib
    parsed = tomllib.loads(config)
    if (parsed.get("game", {}).get("crc32") != rom.crc32 or parsed["game"].get("sha256", rom.sha256) != rom.sha256 or
        parsed["game"].get("output_prefix") != "game" or parsed["game"].get("rom") != rom_filename or
        parsed["game"].get("platform") != system.id):
        raise ConversionError("Profil mémorisé incompatible avec cette ROM ; choisis un profil explicite.")
    if banked and parsed.get("mapper", {}).get("kind", "sega") != "sega":
        raise ConversionError("La couverture native étendue prend en charge le mapper Sega uniquement.")
    standard = parsed.get("video", {}).get("standard")
    if standard_override is not None:
        standard = standard_override
        config = set_video_standard(config, standard)
        standard_source = "user_override"
    elif profile and standard is not None:
        standard_source = "explicit_profile"
    elif saved_recipe and standard is not None:
        standard_source = "saved_profile"
    else:
        remembered_standard = memory.video_standard() if system.id == "sms" else None
        if remembered_standard is not None:
            standard = remembered_standard
            standard_source = "saved_video_selection"
        elif standard is not None:
            standard_source = "bundled_profile"
        else:
            standard = system.default_video_mode(rom.path)
            standard_source = "filename_default"
        config = set_video_standard(config, standard)
    if standard not in system.video_modes:
        raise ConversionError(f"Unsupported {system.name} video timing: {standard}.")
    emit(f"{system.name} video timing: {standard.upper()} ({standard_source}).")
    if system.id == "gg":
        emit("Game Gear display: original LCD 160x144.")
    from .metadata import write_game_metadata
    windows_metadata = write_game_metadata(game, title, executable_name(title),
        light_phaser=system.id == "sms" and light_phaser_game(rom.crc32, rom.path.name) is not None,
        icon=artwork['embedded'], standard=standard, system_id=system.id)
    (game / "game.toml").write_text(config, encoding="utf-8")
    # Rebuild seeds from byte-verified facts, never from stale .build contents.
    write_manifest(game / "dispatch_manifest.txt", memory.seeds())
    prepare_runtime(game, rom, title, engine, standard, functions=not banked)
    # A onefile GUI extracts ASSETS to a different temporary directory on every
    # launch. CMake must always see a stable source path, also when switching
    # between Python source and the packaged converter.
    native_source = prepare_native_source()
    build = game / "build-native"
    executable = build_executable(build, name)
    scenarios = [("demo", [], frames), ("play", ["60:S", "65:", "120:B", "125:", "240:R", "360:RA", "390:R", "600:"], frames)
                 if system.id == "gg" else
                 ("play", ["120:B", "125:", "240:R", "360:RA", "390:R", "600:"], frames)]
    long_routes = ()
    if scan['route_count']:
        # Extended and thorough add reproducible pseudo-random play routes
        # seeded from the exact ROM: host pad input only, with their own frame
        # budget, learned and reference-compared like demo and play.
        from .random_routes import long_routes as pseudo_random_routes, sega_press
        long_routes = pseudo_random_routes(system.id, rom.sha256, count=scan['route_count'],
                                           frames=scan['route_frames'], two_players=False)
        scenarios += [(route.name, sega_press(route), route.frames) for route in long_routes]
        emit(f"Niveau de scan {level} : {len(long_routes)} parcours pseudo-aléatoires reproductibles de "
             f"{long_routes[0].frames} images.")
    history = []
    compilation_started = time.perf_counter()
    coverage = None
    profile_history = []
    for iteration in range(max(1, passes)):
        timings.begin_pass(iteration + 1)
        compiled_seeds = set() if banked else read_observations(game / "dispatch_manifest.txt")
        emit(f"Passe {iteration + 1}/{passes} : couverture native ROM et variantes RAM…" if banked else
             f"Passe {iteration + 1}/{passes} : traduction Z80 et compilation native…")
        if banked:
            compiled_patterns = memory.code_patterns()
            write_code_patterns(game / "native.patterns", compiled_patterns)
            for stale in (game / "generated").glob("game_banked_ops_*.c"):
                stale.unlink()
        with timings.phase('code_generation'):
            result = run([build_executable(ROOT / ('.deps/recompiler-build' + suffix()), 'SmsRecomp'), "--game", game / "game.toml",
                          *(["--banked-step"] if banked else [])], log=log)
        if "FATAL" in result:
            raise ConversionError(result[-4000:])
        for file in (("game_banked_index.c", "banked-coverage.json", "game_layout.c") if banked else
                     ("game_full.c", "game_dispatch.c", "game_layout.c")):
            if not (game / "generated" / file).exists():
                raise ConversionError(f"Sortie de recompilation manquante : {file}")
        if banked:
            coverage = json.loads((game / "generated/banked-coverage.json").read_text())
            emit(f"{coverage['compiled_positions']}/{coverage['rom_positions']} positions ROM traduites ; "
                 f"{coverage['unique_native_bodies']} corps natifs partagés.")
        with timings.phase('compile'):
            run([cmake, "-S", native_source, "-B", build, "-G", generator, *cmake_target_args(),
                f"-DENGINE_DIR={engine.as_posix()}", f"-DGAME_DIR={game.as_posix()}",
                f"-DSMSRECOMP_BANKED_AOT={'ON' if banked else 'OFF'}",
                f"-DGAME_SYSTEM={system.id}", f"-DGAME_NAME={name}",
                f"-DSMSRECOMP_BUILD_JOBS={build_jobs()}",
                f"-DRETRO_RECOMP_VERSION={__version__}",
                f"-DCMAKE_PREFIX_PATH={sdl.as_posix()}"], log=log)
            run([cmake, "--build", build, "--config", "Release", "--target", name, "--parallel", build_jobs()], log=log)
        added = 0
        patterns_added = 0
        for scenario, inputs, budget in scenarios:
            emit(f"Vérification {scenario} : {budget} images…")
            directory = game / "checks" / f"pass{iteration + 1}_{scenario}"
            check = probe(executable, directory, budget, press=inputs)
            check["scenario"] = scenario
            history.append(check)
            if not check["passed"]:
                raise ConversionError(f"Le test {scenario} n'a pas atteint {budget} images. Consulte {directory / 'runtime.log'}")
            if banked and iteration:
                previous = game / "checks" / f"pass{iteration}_{scenario}"
                previous_check = json.loads((previous / "result.json").read_text(encoding="utf-8"))
                comparisons = {filename: (previous / filename).read_bytes() == (directory / filename).read_bytes()
                    for filename in ("vdp.csv", "frame.png", "frame.png.ram")}
                before_cpu, after_cpu = previous_check.get("final_cpu", {}), check.get("final_cpu", {})
                comparisons["final_cpu"] = before_cpu == after_cpu
                check["previous_pass_equivalence"] = comparisons
                if not all(comparisons.values()):
                    raise ConversionError(f"La variante native change le résultat {scenario} : {comparisons}. "
                        f"Exécutable candidat conservé dans {build}, sortie précédente préservée.")
            journal = GameMemory(rom, directory / "learning").journal
            previous_seeds = read_observations(game / "dispatch_manifest.txt")
            memory.import_manifest(journal)
            if banked:
                patterns_added += memory.import_code_patterns(journal.parent / "native.patterns")
            new_seeds = memory.seeds()
            added += len(new_seeds - previous_seeds)
            # Remove RAM/stale entries before the next translation pass.
            write_manifest(game / "dispatch_manifest.txt", new_seeds)
            emit(f"{scenario} : {check['static_percent']} % natif, {check['interpreter_percent']} % interprété.")
        if banked:
            profile_history.append({"pass": iteration + 1, "compiled_windows": len(compiled_patterns),
                "new_windows": patterns_added,
                "interpreter_cycles": [c.get("interpreter_cycles") for c in history[-len(scenarios):]]})
            if not patterns_added or all(c.get("interpreter_cycles") == 0 for c in history[-len(scenarios):]):
                break
            if iteration + 1 < passes:
                emit(f"{patterns_added} nouvelles variantes observées : compilation et nouveau contrôle.")
        elif not added:
            break
        else:
            emit(f"{added} nouvelles entrées repérées : recompilation à la passe suivante.")
    timings.end_passes()
    final_checks = history[-len(scenarios):]
    if banked:
        profile_stop = ("zero_fallback_on_tested_scenarios" if all(c.get("interpreter_cycles") == 0 for c in final_checks)
            else "pass_budget" if patterns_added and len(profile_history) == passes else "no_new_patterns")
        emit("Seuil atteint : aucun cycle de secours sur les deux parcours testés." if
            profile_stop == "zero_fallback_on_tested_scenarios" else
            f"Boucle arrêtée ({profile_stop}) : du secours reste présent sur les parcours testés.")
    emit("Vérification du mode strict…")
    strict_checks = [probe(executable, game / "checks" / f"strict_{scenario}", budget,
        strict=True, press=inputs) for scenario, inputs, budget in scenarios]
    # Shared-runtime differential check: useful for CPU translation, not proof of hardware accuracy.
    emit("Comparaison avec le processeur de référence…")
    reference_dir = game / "checks/reference"
    reference = probe(executable, reference_dir, frames, reference=True)
    final_demo = game / "checks" / f"pass{len(history) // len(scenarios)}_demo" / "vdp.csv"
    reference_trace = reference_dir / "vdp.csv"
    # The upstream CSV also appends RAM and SP columns despite its shorter
    # header. Compare the VDP columns explicitly: an interpreter does not update
    # the generated-code register file, so its SP column cannot be compared.
    a = vdp_states(final_demo)
    b = vdp_states(reference_trace)
    mismatched_frames = [int(x[0]) for x, y in zip(a, b) if x != y]
    matched = reference["passed"] and len(a) == len(b) and not mismatched_frames
    ram_path = game / "checks" / f"pass{len(history) // len(scenarios)}_demo/frame.png.ram"
    reference_ram = reference_dir / "frame.png.ram"
    ram_match = reference["passed"] and ram_path.read_bytes() == reference_ram.read_bytes()
    cpu_match = (final_checks[0].get("final_cpu") == reference.get("final_cpu")) if banked else None
    cpu_differences = ({key: {"native": value, "reference": reference.get("final_cpu", {}).get(key)}
        for key, value in final_checks[0].get("final_cpu", {}).items()
        if value != reference.get("final_cpu", {}).get(key)} if banked else None)
    validation = None
    if banked:
        reference_runs = [(reference, reference_dir)]
        for scenario, inputs, budget in scenarios[1:]:
            run_dir = game / f'checks/reference_{scenario}'
            reference_runs.append((probe(executable, run_dir, budget, reference=True, press=inputs), run_dir))
        comparisons = []
        for index, (ref, ref_dir) in enumerate(reference_runs):
            scenario = scenarios[index][0]
            result = compare_execution(final_checks[index], ref,
                game / f'checks/pass{len(history) // len(scenarios)}_{scenario}', ref_dir)
            result.update(scenario=scenario, reference=ref)
            # A zero-fallback claim is valid only if the very same scenario
            # also finishes with the fallback explicitly disabled.
            strict = strict_checks[index]
            result['checks']['strict_accounting'] = (strict['passed'] if final_checks[index].get('interpreter_cycles') == 0
                                                    else strict['exit_code'] == 3)
            result['passed'] = all(result['checks'].values())
            comparisons.append(result)
        validation = {'policy': 'banked-release-v2-raster', 'passed': all(c['passed'] for c in comparisons),
                      'scenarios': comparisons, 'hardware_accuracy': False, 'full_game': False}
        (game / 'checks/native-validation.json').write_text(json.dumps(validation, indent=2), encoding='utf-8')
        if not validation['passed']:
            failures = {c['scenario']: [key for key, ok in c['checks'].items() if not ok] for c in comparisons if not c['passed']}
            raise ConversionError(f'Native validation failed: {failures}. Previous export preserved. Details: {game / "checks/native-validation.json"}')
    final_executable = destination / executable_name(title)
    # Publication merges again so observations appended during compilation are
    # retained. They will seed the next generation if they arrived too late.
    latest_memory = memory.summary()
    latest_memory["generations"] += 1
    signature = compiler_signature(game)
    report = {"tool": "Retro-Recomp", "version": __version__, "created_utc": datetime.now(timezone.utc).isoformat(),
        "runtime_data": {"directory": "datas", "shared_config": "datas/Retro-Recomp.ini",
            "game_directory": f"datas/games/{name}-{rom.sha256[:12]}",
            "log": None, "diagnostics": "explicit --log only", "lazy_creation": True,
            "quicksave": f"datas/games/{name}-{rom.sha256[:12]}/{name}-quicksave.state" if banked else None,
            "library_identity": rom.sha256, "runtime_learning": True,
            "runtime_feedback": gameplay_feedback},
        "backend": backend, "target": target_id(), "scan_level": level,
        "long_routes": [route.metadata() for route in long_routes],
        "native_coverage": coverage, "native_validation": validation,
        "input_players": 1 if system.id == "gg" else 2,
        "game_states": {"supported": banked, "save_key": "F8", "load_key": "F9", "slots": 1,
            "schema": 1, "machine": 3 if system.id == "gg" else 2 if standard == "pal" else 1,
            "rom_identity": "sha256", "legacy_and_reference_supported": False},
        "system": {"id": system.id, "name": system.name},
        "video_model": {"name": f"mode4-{system.id}-{standard}-scanline-v4", "standard": standard,
            "selection_source": standard_source,
            "lines_per_frame": 313 if standard == "pal" else 262,
            "visible_pixels": [256, 192] if system.id == "sms" else [160, 144],
            "palette_and_vram": "per_scanline",
            "horizontal_scroll": "line_latch", "vertical_scroll": "frame_latch",
            "sprite_limit": 8, "pixel_clock_accuracy_validated": False,
            "sprite_flicker_reduction": {"supported": system.id == "sms", "default": False,
                "toggle": "F5" if system.id == "sms" else None,
                "confirmed_reversing_list_stabilization": system.id == "sms",
                "guest_status_uses_original_limit": True}},
        "ui_languages": ["en", "fr", "it", "es", "de", "zh", "ja", "ru"], "default_language": "en",
        "artwork": artwork,
        "windows_metadata": windows_metadata,
        "game_tags": list(game_tags(rom.crc32, rom.path.name)) if system.id == "sms" else [],
        "peripheral": {"type": "light_phaser" if system.id == "sms" and light_phaser_game(rom.crc32, rom.path.name) else "joypad",
            "selection": "explicit_game_catalogue" if system.id == "sms" else "console_profile",
            "mouse_player": 1 if system.id == "sms" else None, "hardware_accuracy_validated": False},
        "conversion_wall_seconds": round(time.perf_counter() - compilation_started, 6),
        "executable_bytes": executable.stat().st_size,
        "build_executable": str(executable), "toolchain": toolchain_description(),
        "rom": rom.metadata(), "engine_revision": ENGINE_REV, "sdl_revision": SDL_REV,
        "executable": final_executable.name, "embedded_rom": True, "static_sdl": True,
        "latency_ms": None, "hardware_accuracy_validated": False,
        "full_game_validated": False, "reference_vdp_trace_match": matched,
        "reference_scope": "CPU comparison with interpreter over the SAME VDP, audio and memory runtime",
        "reference_vdp_mismatched_frames": mismatched_frames,
        "reference_final_vdp_match": bool(a and b and a[-1] == b[-1]),
        "reference_final_ram_match": ram_match, "reference_final_cpu_match": cpu_match,
        "reference_final_cpu_differences": cpu_differences,
        "reference_check": reference,
        "reference_final_png_match": (game / "checks" / f"pass{len(history) // len(scenarios)}_demo/frame.png").read_bytes()
            == (reference_dir / "frame.png").read_bytes() if reference["passed"] else False,
        "strict_checks": strict_checks, "final_checks": final_checks, "history": history,
        "build_directory": str(game), "compiler_signature": signature,
        "learning": {"before": memory_before, "after": latest_memory,
                     "imported_legacy_observations": imported,
                     "reused_rom_entries": 0 if banked else memory_before["rom_entries"],
                     "compiled_rom_entries": None if banked else len(compiled_seeds),
                     "pending_rom_entries": None if banked else len(memory.seeds() - compiled_seeds),
                     "strategy": "all_rom_positions_and_profiled_byte_guards" if banked else "verified_entry_seeds",
                     "native_profiles": {"passes": profile_history, "pass_budget": passes,
                         "stop_reason": profile_stop,
                         "reused_windows": memory_before["native_pattern_windows"],
                         "compiled_windows": len(compiled_patterns),
                         "pending_windows": len(memory.code_patterns() - compiled_patterns),
                         "zero_fallback_on_tested_scenarios": all(c.get("interpreter_cycles") == 0 for c in final_checks)} if banked else None,
                     "recipe_reused": not profile and bool(memory.recipe(ENGINE_REV)),
                     "scope": "Byte-verified ROM entries; banked RAM encodings are precompiled with exact live-byte guards"}}
    memory.remember(title, config, report, signature)
    write_report(destination / "conversion-report.json", report)
    if artwork["embedded"]:
        exported_art = destination / "artwork"
        exported_art.mkdir(parents=True, exist_ok=True)
        shutil.copy2(game / "game.ico", exported_art / f"{name}.ico")
        shutil.copy2(game / "game-icon.png", exported_art / f"{name}-icon.png")
    for scenario, _, _ in scenarios:
        src = game / "checks" / f"pass{len(history) // len(scenarios)}_{scenario}"
        target = destination / "validation" / scenario
        target.mkdir(parents=True, exist_ok=True)
        for filename in ("frame.png", "runtime.log", "result.json", "vdp.csv"):
            if (src / filename).exists():
                shutil.copy2(src / filename, target / filename)
    shutil.copy2(game / "game.toml", destination / "game.toml")
    # Export is per-ROM. Do not replace a legacy generic manifest: it may still
    # receive observations from an older running executable or another game.
    export = destination / f"{name}-{rom.sha256[:12]}.manifest"
    write_manifest(export, memory.seeds())
    if banked:
        write_code_patterns(destination / "native.patterns", memory.code_patterns())
    if not publish_result:
        return executable
    with timings.phase('publication'):
        pending = publish_executable(executable, final_executable, compact=True, emit=emit)
    if pending:
        emit(f"Nouvelle version prête ; remplacement à la fermeture du jeu : {final_executable}")
    else:
        emit(f"Exécutable créé : {final_executable}")
    emit(f"Comparaison CPU/VDP de référence : {'identique' if matched else 'divergence à examiner'}.")
    return final_executable
