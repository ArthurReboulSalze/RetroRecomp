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
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from .library import GameMemory, read_observations, write_manifest, write_code_patterns
from .artwork import ArtworkError, prepare_icon
from .paths import ROOT, ASSETS, games_directory, data_directory
from . import __version__
from .i18n import log_text
from .publishing import publish_executable
from .cpu import prepare_cpu_headers, prepare_reference
from .validation import compare_execution, vdp_states

ENGINE_REV = "224d5bb2c150a2c295033d35dec629ef9ee42940"
SDL_REV = "98d1f3a45aae568ccd6ed5fec179330f47d4d356"


class ConversionError(RuntimeError):
    pass


@dataclass(frozen=True)
class Rom:
    path: Path
    data: bytes
    crc32: int
    sha256: str
    copier_header: bool
    header_offset: int | None
    region: int | None

    def metadata(self) -> dict:
        return {"name": self.path.name, "bytes": len(self.data),
                "crc32": f"{self.crc32:08X}", "sha256": self.sha256,
                "copier_header_removed": self.copier_header,
                "header_offset": self.header_offset, "region": self.region}


def read_rom(path: Path) -> Rom:
    path = path.resolve()
    if path.suffix.lower() != ".sms":
        raise ConversionError("Choisis une ROM Master System au format .sms.")
    data = path.read_bytes()
    copier = len(data) % 16384 == 512
    if copier:
        data = data[512:]
    if len(data) < 8192 or len(data) > 4 * 1024 * 1024 or len(data) % 8192:
        raise ConversionError("Taille de ROM non prise en charge (8 Ko à 4 Mo, multiple de 8 Ko).")
    header = next((offset for offset in (0x7FF0, 0x3FF0, 0x1FF0)
                   if data[offset:offset + 8] == b"TMR SEGA"), None)
    region = data[header + 15] >> 4 if header is not None else None
    if region in (5, 6, 7):
        raise ConversionError("Cette ROM est identifiée comme Game Gear ; cette version cible la Master System.")
    return Rom(path, data, zlib.crc32(data), hashlib.sha256(data).hexdigest(), copier, header, region)


def slug(title: str) -> str:
    value = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    value = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")[:60]
    if not value or value[0].isdigit():
        value = "Game_" + value
    if value.upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        value = "Game_" + value
    return value


def executable_name(title: str) -> str:
    """Keep the readable title, removing only Windows filename restrictions."""
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', title).strip().rstrip(' .')[:150].rstrip(' .')
    if not value:
        value = 'Game'
    if value.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}:
        value = '_' + value
    return value + '.exe'


def run(args: list[str | Path], *, cwd: Path = ROOT, log: Path | None = None,
        emit: Callable[[str], None] = print, timeout: int = 600) -> str:
    command = [str(arg) for arg in args]
    result = subprocess.run(command, cwd=cwd, stdout=subprocess.PIPE,
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
        raise ConversionError("Retro-Recomp construit actuellement des exécutables Windows x64.")
    vswhere = Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Microsoft Visual Studio/Installer/vswhere.exe"
    installations = []
    if vswhere.exists():
        installations = json.loads(run([vswhere, "-all", "-products", "*", "-requires",
            "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-format", "json"]))
    for major, generator in ((17, "Visual Studio 17 2022"), (18, "Visual Studio 18 2026")):
        for install in installations:
            if not install["installationVersion"].startswith(f"{major}."):
                continue
            cmake = Path(install["installationPath"]) / "Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/cmake.exe"
            candidate = shutil.which("cmake")
            if not cmake.exists() and candidate:
                cmake = Path(candidate)
            if cmake.exists():
                return cmake, generator
    raise ConversionError("Il faut Visual Studio Build Tools (C++ x64 et CMake). Aucun compilateur compatible trouvé.")


def dependencies(emit: Callable[[str], None] = print) -> tuple[Path, Path, Path, str]:
    cmake, generator = toolchain()
    dep = ROOT / ".deps"
    dep.mkdir(exist_ok=True)
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
    generator_source = (engine / "recompiler/src/code_generator.c").read_text(encoding="utf-8")
    generator_source = replace_once(generator_source,
        '    fprintf(o,"        do {\\n");',
        '''    fprintf(o,"        int sms_block_first = 1;\\n        do {\\n");
    fprintf(o,"            if (!sms_block_first) s->r = (uint8_t)((s->r & 0x80) | ((s->r + 2) & 0x7f));\\n");
    fprintf(o,"            sms_block_first = 0;\\n");''')
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
    generator_source += "\n" + (ASSETS / "native/banked_emitter.inc").read_text(encoding="utf-8")
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
    recomp = dep / "recompiler-build/Release/SmsRecomp.exe"
    compiled_marker = dep / "recompiler-build/compiled.sha256"
    if patch_changed or not recomp.exists() or not compiled_marker.exists() or compiled_marker.read_text() != expected:
        emit("Compilation du traducteur Z80 → C…")
        run([cmake, "-S", source, "-B", dep / "recompiler-build", "-G", generator, "-A", "x64"], log=log)
        run([cmake, "--build", dep / "recompiler-build", "--config", "Release", "--parallel", "4"], log=log)
        compiled_marker.write_text(expected)
    prefix = sdl / "install"
    if not (prefix / "lib/SDL2-static.lib").exists():
        emit("Compilation de SDL2 statique (première utilisation)…")
        run([cmake, "-S", sdl, "-B", sdl / "build", "-G", generator, "-A", "x64",
            "-DSDL_SHARED=OFF", "-DSDL_STATIC=ON", "-DSDL_TEST=OFF", "-DSDL_TESTS=OFF",
            "-DSDL_FORCE_STATIC_VCRT=ON", f"-DCMAKE_INSTALL_PREFIX={prefix.as_posix()}"], log=log)
        run([cmake, "--build", sdl / "build", "--config", "Release", "--parallel", "4"], log=log)
        run([cmake, "--install", sdl / "build", "--config", "Release"], log=log)
    return engine, prefix, cmake, generator


def replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ConversionError(f"L'interface du moteur a changé ; adaptation nécessaire : {old[:90]!r}")
    return source.replace(old, new, 1)


def prepare_runtime(game: Path, rom: Rom, title: str, engine: Path) -> None:
    header = '''#include <stdint.h>\n#include <stddef.h>\nextern const uint8_t sms_rom[];
extern const size_t sms_rom_size;\nextern const uint32_t sms_rom_crc32;
extern const char sms_game_title[];\nint smsrecomp_interpreter_active(void);
extern const char sms_rom_sha256[];
extern const char sms_game_slug[];
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
    prepare_cpu_headers(game, engine)
    prepare_reference(game, engine)
    glue = (engine / "runner/glue.c").read_text(encoding="utf-8")
    glue = replace_once(glue, '#include "external/superzazu/z80.h"', '#include "runtime_reference.h"')
    glue = replace_once(glue, 'static bool g_hz_init;', 'static bool g_hz_init;\nstatic uint64_t reference_cycle_base;')
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
        'FILE *f = retro_game_file(L"-dispatch-misses.log", L"a");')
    glue = replace_once(glue, 'remove(g_miss_path);',
        'retro_game_file_reset(L"-dispatch-misses.log");')
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
    glue = replace_once(glue, "        z80_step(&g_hz); g_frame_ic++;\n        advance_vdp(base + g_hz.cyc);", """        uint32_t previous_cycles = g_hz.cyc;
        z80_step(&g_hz); g_frame_ic++;
        g_hybrid_cyc += g_hz.cyc - previous_cycles;
        advance_vdp(base + g_hz.cyc);""")
    glue = replace_once(glue,
        "    g_hybrid_cyc += g_hz.cyc;            /* cycles this routine spent in the interpreter */\n    g_hybrid_calls++;",
        "    smsrecomp_interp_depth--;")
    # Count in-flight interpreter work too: a frame limit can longjmp out of a
    # routine before it returns, so upstream's end-of-routine tally misses it.
    glue = replace_once(glue, "static void advance_vdp(uint64_t cyc){", """static uint64_t smsrecomp_total_cycles;
static void advance_vdp(uint64_t cyc){
    smsrecomp_total_cycles = cyc;""")
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
    glue = '''#ifdef SMSRECOMP_BANKED_AOT
static int banked_last_interpreted;
static void smsrecomp_banked_run(void);
static void smsrecomp_banked_fallback(unsigned short addr);
static void smsrecomp_banked_stats(void);
#endif
static void smsrecomp_cpu_record(void);
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
    glue += "\n" + (ASSETS / "native/banked_runtime.inc").read_text(encoding="utf-8")
    # A reset exits through the runtime's existing longjmp, discarding all
    # generated C continuations. Also reset every execution/callback state that
    # upstream initialized only once per process, before entering reset again.
    glue = replace_once(glue, "void glue_init(bool is_gg, uint64_t frame_limit){", """void glue_init(bool is_gg, uint64_t frame_limit){
    g_frame_ic = g_irq_taken = g_irq_reentrant = 0;
    g_sync_depth = g_sync_maxdepth = 0;
    g_running = false;
    g_frame_cb = NULL; g_input_cb = NULL; g_audio_sink = NULL;
    g_dump_frame = (uint64_t)-1; g_dump_path = NULL;
    glue_set_vdp_trace(NULL); glue_psg_log_close();
    memset(g_io_out_count, 0, sizeof(g_io_out_count));
    memset(g_io_in_count, 0, sizeof(g_io_in_count));
    memset(g_fb, 0, sizeof(g_fb));
    memset(&g_hz, 0, sizeof(g_hz)); g_hz_init = false;
    smsrecomp_interp_depth = 0; smsrecomp_total_cycles = 0;
    g_mb_pos = 0; memset(g_interp_cyc, 0, sizeof(g_interp_cyc));
    g_in_diff = 0; g_diff_freeze = g_diff_active = 0; g_diff_icount = 0;
    g_enter_pos = 0; g_dbg_pc = 0;
    memset(g_enter_ring, 0, sizeof(g_enter_ring));
""")
    (game / "runtime_glue.c").write_text(glue, encoding="utf-8")
    video = (engine / "runner/video/sms_vdp.c").read_text(encoding="utf-8")
    # Blanking is the final pixel mux: sprites must not overwrite the masked
    # column. Adapt a local copy; the pinned dependency stays untouched.
    blank_column = '''    /* mask leftmost 8 pixels with backdrop (reg0 bit5) */
    if (r0 & 0x20)
        for (int y = 0; y < SMS_SCREEN_H; y++)
            for (int x = 0; x < 8; x++)
                fb[y * SMS_SCREEN_W + x] = backdrop;
'''
    video = replace_once(video, blank_column, '')
    video = '#include "video_frame.h"\n' + video
    video = replace_once(video, 'void vdp_render_frame(uint32_t *fb){', '''static int frame_left_border;
int smsrecomp_frame_left_border(void) { return frame_left_border; }

void vdp_render_frame(uint32_t *fb){''')
    video = replace_once(video, '    const uint8_t r0 = g_vdp.reg[0], r1 = g_vdp.reg[1];', '''    const uint8_t r0 = g_vdp.reg[0], r1 = g_vdp.reg[1];
    frame_left_border = !g_vdp.is_gg && (r0 & 0x24) == 0x24 ? 8 : 0;''')
    closing = video.rfind('\n}')
    blank_column = blank_column.replace('if (r0 & 0x20)', 'if ((r0 & 0x24) == 0x24)')
    video = video[:closing] + '\n' + blank_column + video[closing:]
    (game / "runtime_video.c").write_text(video, encoding="utf-8")
    main = (engine / "runner/main.c").read_text(encoding="utf-8")
    main = replace_once(main, '#include "host_sdl.h"', '#include "host_sdl.h"\n#include "host_control.h"')
    main = replace_once(main, '    glue_set_pad1(host_get_pad1());     /* push this frame\'s keyboard state to the CPU */',
        '    glue_set_pad1(host_get_pad1());\n    glue_set_pad2(host_get_pad2());')
    main = replace_once(main, 'is_gg ? "Sonic (GG) - recompiled" : "Sonic 1 (SMS) - recompiled"', "sms_game_title")
    main = '#include "embedded_rom.h"\n' + main
    main = replace_once(main, "int main(int argc, char **argv){", """int main(int argc, char **argv){
    g_press_n = 0;
    g_audio_live = false;
    _putenv_s("SMSRECOMP_REFERENCE", "");
""")
    main = replace_once(main, "    if (interp){", '    if (interp){\n        _putenv_s("SMSRECOMP_REFERENCE", "1");')
    main = replace_once(main, 'fprintf(stderr,"[runner] SDL window init failed; running headless\\n");',
        '{ fprintf(stderr,"[runner] SDL window init failed\\n"); return 2; }')
    (game / "runtime_main.c").write_text(main, encoding="utf-8")


def default_config(rom: Rom) -> str:
    known = ASSETS / "profiles" / f"alex_kidd_{rom.crc32:08x}.toml"
    if known.exists():
        import tomllib
        config = known.read_text(encoding="utf-8")
        if tomllib.loads(config).get("game", {}).get("sha256") == rom.sha256:
            return config
    return f'''# Experimental discovery profile; compatibility unverified.
[game]
output_prefix = "game"
platform = "sms"
rom = "rom.sms"
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
    directory.mkdir(parents=True, exist_ok=True)
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
    env = os.environ.copy()
    env.pop("SMSRECOMP_STRICT", None)
    # Automated/reference probes stay isolated from the user's library. Their
    # verified observations are imported deliberately by convert(), not by the
    # reference interpreter or diagnostic launches.
    env["SMSRECOMP_LIBRARY_DIR"] = str(directory / "learning")
    env["RETRO_RECOMP_LIBRARY_DIR"] = str(directory / "learning")
    started = time.perf_counter()
    result = subprocess.run(args, cwd=directory, env=env, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, timeout=60, creationflags=subprocess.CREATE_NO_WINDOW)
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
    digest = hashlib.sha256()
    for source in [game / "runtime_glue.c", game / "runtime_main.c", game / "runtime_video.c", game / "game.toml",
                   game / "runtime_reference.c", game / "runtime_reference.h", game / "sms_runtime.h", game / "z80_ops.h",
                   *sorted((game / "generated").glob("*.c")), ROOT / ".deps/recompiler-src/src/rom_parser.c",
                   ROOT / ".deps/recompiler-src/src/code_generator.c", ROOT / ".deps/recompiler-src/src/main_sms.c",
                   game / "game_resources.rc", game / "game.ico",
                   *sorted((ASSETS / "native").glob("*"))]:
        if source.is_file():
            digest.update(source.name.encode()); digest.update(source.read_bytes())
    digest.update(ENGINE_REV.encode()); digest.update(SDL_REV.encode())
    return digest.hexdigest()


def convert(rom_path: Path, *, title: str | None = None, output: Path | None = None,
            profile: Path | None = None, passes: int = 3, frames: int = 1200,
            backend: str = "banked", language: str = "en",
            cover: Path | None = None, boxart_dir: Path | None = None,
            online_cover: bool = True, use_cover: bool = True,
            emit: Callable[[str], None] = print) -> Path:
    if output is None:
        # Single-ROM exports use the same names, reports and replacement policy
        # as the GUI/batch. The batch invokes this compiler with an explicit
        # report directory, so compilation itself is unchanged.
        from .batch import identify, convert_batch
        item = identify(rom_path)
        if title:
            item.title = title
        item.cover = cover
        result = convert_batch([item], games_directory(), profile=profile,
            passes=passes, frames=frames, backend=backend, language=language,
            boxart_dir=boxart_dir, online_cover=online_cover, use_cover=use_cover,
            emit=emit)['games'][0]
        if result['status'] != 'success':
            raise ConversionError(result['message'])
        return Path(result['executable'])
    original_emit = emit
    emit = lambda text: original_emit(log_text(text, language))
    if backend not in ("functions", "banked"):
        raise ConversionError("Backend inconnu : functions ou banked attendu.")
    if not 1 <= passes <= 10 or not 1 <= frames <= 10000:
        raise ConversionError("Choisis 1 à 10 passes et 1 à 10000 images par test.")
    banked = backend == "banked"
    rom = read_rom(rom_path)
    title = title or re.sub(r"\s*\([^)]*\)", "", rom.path.stem).strip()
    name = slug(title)
    destination = output.resolve()
    game = ROOT / ".build" / (f"{name}_{rom.crc32:08X}_{rom.sha256[:12]}" + ("_banked" if banked else ""))
    game.mkdir(parents=True, exist_ok=True)
    destination.mkdir(parents=True, exist_ok=True)
    log = game / "build.log"
    emit(f"ROM : {title}, {len(rom.data) // 1024} Ko, CRC32 {rom.crc32:08X}")
    try:
        artwork = prepare_icon(game, rom.path, title, (boxart_dir or ROOT / "BoxArt").resolve(),
            explicit=cover, online=online_cover, enabled=use_cover, cache_directory=data_directory() / 'BoxArt', emit=emit)
    except (ArtworkError, OSError) as exc:
        raise ConversionError(str(exc)) from exc
    engine, sdl, cmake, generator = dependencies(emit)
    memory = GameMemory(rom)
    imported = import_previous(rom, destination, memory)
    saved_manifest = ASSETS / "profiles" / f"{rom.crc32:08x}.manifest"
    if saved_manifest.exists():
        memory.import_manifest(saved_manifest)
    memory_before = memory.summary()
    emit(f"Mémoire du jeu : {memory_before['rom_entries']} entrées ROM vérifiées, "
         f"{memory_before['ram_entries']} observations RAM ; {imported} importées des anciennes parties.")
    (game / "rom.sms").write_bytes(rom.data)
    if profile:
        import tomllib
        config = profile.read_text(encoding="utf-8")
        parsed = tomllib.loads(config)
        if parsed.get("game", {}).get("crc32") != rom.crc32:
            raise ConversionError("Le profil ne correspond pas au CRC32 de cette ROM.")
        if parsed["game"].get("sha256", rom.sha256) != rom.sha256:
            raise ConversionError("Le profil ne correspond pas au SHA256 de cette ROM.")
        if parsed["game"].get("output_prefix") != "game" or parsed["game"].get("rom") != "rom.sms":
            raise ConversionError('Le profil doit utiliser output_prefix="game" et rom="rom.sms".')
    else:
        config = memory.recipe(ENGINE_REV) or default_config(rom)
        if memory.recipe(ENGINE_REV):
            emit("Profil de compilation reconnu dans la bibliothèque.")
    import tomllib
    parsed = tomllib.loads(config)
    if (parsed.get("game", {}).get("crc32") != rom.crc32 or parsed["game"].get("sha256", rom.sha256) != rom.sha256 or
        parsed["game"].get("output_prefix") != "game" or parsed["game"].get("rom") != "rom.sms"):
        raise ConversionError("Profil mémorisé incompatible avec cette ROM ; choisis un profil explicite.")
    if banked and parsed.get("mapper", {}).get("kind", "sega") != "sega":
        raise ConversionError("La couverture native étendue prend en charge le mapper Sega uniquement.")
    (game / "game.toml").write_text(config, encoding="utf-8")
    # Rebuild seeds from byte-verified facts, never from stale .build contents.
    write_manifest(game / "dispatch_manifest.txt", memory.seeds())
    prepare_runtime(game, rom, title, engine)
    # A onefile GUI extracts ASSETS to a different temporary directory on every
    # launch. CMake must always see a stable source path, also when switching
    # between Python source and the packaged converter.
    native_source = ROOT / ".build/native-source"
    native_source.mkdir(parents=True, exist_ok=True)
    for source in (ASSETS / "native").iterdir():
        if not source.is_file():
            continue
        target = native_source / source.name
        if not target.exists() or target.read_bytes() != source.read_bytes():
            shutil.copy2(source, target)
    build = game / "build-native"
    executable = build / "Release" / f"{name}.exe"
    scenarios = [("demo", []), ("play", ["120:B", "125:", "240:R", "360:RA", "390:R", "600:"])]
    history = []
    compilation_started = time.perf_counter()
    coverage = None
    profile_history = []
    for iteration in range(max(1, passes)):
        compiled_seeds = set() if banked else read_observations(game / "dispatch_manifest.txt")
        emit(f"Passe {iteration + 1}/{passes} : couverture native ROM et variantes RAM…" if banked else
             f"Passe {iteration + 1}/{passes} : traduction Z80 et compilation native…")
        if banked:
            compiled_patterns = memory.code_patterns()
            write_code_patterns(game / "native.patterns", compiled_patterns)
            for stale in (game / "generated").glob("game_banked_ops_*.c"):
                stale.unlink()
        result = run([ROOT / ".deps/recompiler-build/Release/SmsRecomp.exe", "--game", game / "game.toml",
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
        run([cmake, "-S", native_source, "-B", build, "-G", generator, "-A", "x64",
            f"-DENGINE_DIR={engine.as_posix()}", f"-DGAME_DIR={game.as_posix()}",
            f"-DSMSRECOMP_BANKED_AOT={'ON' if banked else 'OFF'}",
            f"-DGAME_NAME={name}", f"-DCMAKE_PREFIX_PATH={sdl.as_posix()}"], log=log)
        run([cmake, "--build", build, "--config", "Release", "--parallel", "4"], log=log)
        added = 0
        patterns_added = 0
        for scenario, inputs in scenarios:
            emit(f"Vérification {scenario} : {frames} images…")
            directory = game / "checks" / f"pass{iteration + 1}_{scenario}"
            check = probe(executable, directory, frames, press=inputs)
            check["scenario"] = scenario
            history.append(check)
            if not check["passed"]:
                raise ConversionError(f"Le test {scenario} n'a pas atteint {frames} images. Consulte {directory / 'runtime.log'}")
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
                "interpreter_cycles": [c.get("interpreter_cycles") for c in history[-2:]]})
            if not patterns_added or all(c.get("interpreter_cycles") == 0 for c in history[-2:]):
                break
            if iteration + 1 < passes:
                emit(f"{patterns_added} nouvelles variantes observées : compilation et nouveau contrôle.")
        elif not added:
            break
        else:
            emit(f"{added} nouvelles entrées repérées : recompilation à la passe suivante.")
    final_checks = history[-2:]
    if banked:
        profile_stop = ("zero_fallback_on_tested_scenarios" if all(c.get("interpreter_cycles") == 0 for c in final_checks)
            else "pass_budget" if patterns_added and len(profile_history) == passes else "no_new_patterns")
        emit("Seuil atteint : aucun cycle de secours sur les deux parcours testés." if
            profile_stop == "zero_fallback_on_tested_scenarios" else
            f"Boucle arrêtée ({profile_stop}) : du secours reste présent sur les parcours testés.")
    emit("Vérification du mode strict…")
    strict_checks = [probe(executable, game / "checks" / f"strict_{scenario}", frames,
        strict=True, press=inputs) for scenario, inputs in scenarios]
    # Shared-runtime differential check: useful for CPU translation, not proof of hardware accuracy.
    emit("Comparaison avec le processeur de référence…")
    reference_dir = game / "checks/reference"
    reference = probe(executable, reference_dir, frames, reference=True)
    final_demo = game / "checks" / f"pass{len(history) // 2}_demo" / "vdp.csv"
    reference_trace = reference_dir / "vdp.csv"
    # The upstream CSV also appends RAM and SP columns despite its shorter
    # header. Compare the VDP columns explicitly: an interpreter does not update
    # the generated-code register file, so its SP column cannot be compared.
    a = vdp_states(final_demo)
    b = vdp_states(reference_trace)
    mismatched_frames = [int(x[0]) for x, y in zip(a, b) if x != y]
    matched = reference["passed"] and len(a) == len(b) and not mismatched_frames
    ram_path = game / "checks" / f"pass{len(history) // 2}_demo/frame.png.ram"
    reference_ram = reference_dir / "frame.png.ram"
    ram_match = reference["passed"] and ram_path.read_bytes() == reference_ram.read_bytes()
    cpu_match = (final_checks[0].get("final_cpu") == reference.get("final_cpu")) if banked else None
    cpu_differences = ({key: {"native": value, "reference": reference.get("final_cpu", {}).get(key)}
        for key, value in final_checks[0].get("final_cpu", {}).items()
        if value != reference.get("final_cpu", {}).get(key)} if banked else None)
    validation = None
    if banked:
        reference_play = probe(executable, game / 'checks/reference_play', frames,
                               reference=True, press=scenarios[1][1])
        comparisons = []
        for index, ref in enumerate((reference, reference_play)):
            scenario = scenarios[index][0]
            result = compare_execution(final_checks[index], ref,
                game / f'checks/pass{len(history) // 2}_{scenario}',
                reference_dir if index == 0 else game / 'checks/reference_play')
            result.update(scenario=scenario, reference=ref)
            # A zero-fallback claim is valid only if the very same scenario
            # also finishes with the fallback explicitly disabled.
            strict = strict_checks[index]
            result['checks']['strict_accounting'] = (strict['passed'] if final_checks[index].get('interpreter_cycles') == 0
                                                    else strict['exit_code'] == 3)
            result['passed'] = all(result['checks'].values())
            comparisons.append(result)
        validation = {'policy': 'banked-release-v1', 'passed': all(c['passed'] for c in comparisons),
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
            "log": f"datas/games/{name}-{rom.sha256[:12]}/{name}-last-run.log",
            "library_identity": rom.sha256, "library": "datas/library/<nom-du-jeu>-<SHA256>"},
        "backend": backend, "native_coverage": coverage, "native_validation": validation, "input_players": 2,
        "ui_languages": ["en", "fr"], "default_language": "en",
        "artwork": artwork,
        "conversion_wall_seconds": round(time.perf_counter() - compilation_started, 6),
        "executable_bytes": executable.stat().st_size,
        "build_executable": str(executable),
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
        "reference_final_png_match": (game / "checks" / f"pass{len(history) // 2}_demo/frame.png").read_bytes()
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
    (destination / "conversion-report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    if artwork["embedded"]:
        exported_art = destination / "artwork"
        exported_art.mkdir(parents=True, exist_ok=True)
        shutil.copy2(game / "game.ico", exported_art / f"{name}.ico")
        shutil.copy2(game / "game-icon.png", exported_art / f"{name}-icon.png")
    for scenario, _ in scenarios:
        src = game / "checks" / f"pass{len(history) // 2}_{scenario}"
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
    pending = publish_executable(executable, final_executable)
    if pending:
        emit(f"Nouvelle version prête ; remplacement à la fermeture du jeu : {final_executable}")
    else:
        emit(f"Exécutable créé : {final_executable}")
    emit(f"Comparaison CPU/VDP de référence : {'identique' if matched else 'divergence à examiner'}.")
    return final_executable
