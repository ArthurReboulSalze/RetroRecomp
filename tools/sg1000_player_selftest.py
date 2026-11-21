"""ROM-free self-test of the delivered SG-1000 game (native/sg1000_machine/sg1000_player.c, the host-kit adapter
native/hostkit/adapters/rrhk_sg1000.inc and the quick states of sg1000_state_file.inc).

It builds, from an AUTHORED cartridge (no ROM, nothing of a commercial game), the same files the converter's packaging writes (it calls
retrorecomp/sg1000_build.py project_cmake and retrorecomp/sg1000_conversion.py prepare_game, with only the probe's files added): the
generated bodies of the shared banked Z80 chain, the reference runner, the headless native check and the game (its own resources, the
host kit, SDL2). Then it proves, and says exactly what each proof covers:

  (a) the game's `--headless` replay of a route equals the native check's, on every field of the report and on the per-frame rows, the
      sound and the dumps (byte for byte); and the check equals the reference interpreter on the common fields. NTSC and PAL.
  (b) a quick state saved near the end of a route is loaded by a FRESH process, which continues the same frames for 600 frames (rows
      and final state equal); a missing, damaged, cut, extended, foreign (another game, standard, schema, build) or crafted-but-CRC-valid
      state is refused (exit 4), the file is left as it was, nothing is created; and in a WINDOWED game F8 saves, F9 loads, and a refused
      F9 (missing, damaged, foreign) leaves the frames exactly as a run that never asked.
  (c) the game run WINDOWED (SDL offscreen video, dummy audio, a hidden window; RETRORECOMP_HOST_TEST_FRAMES frames) exits 0, presents a
      picture every frame, which is not blank, and answers the keyboard: a held direction and button reach the cartridge through the
      pads, the Pause key raises its /NMI. The sound of the window is NOT checked (the dummy device plays nothing): the sound is proved by
      (a), the stream the machine makes, which the window hands to the kit unchanged.

What it does not prove: nothing about a real cartridge, a real controller or a real display; no timing against a console (the five measures
stay separate: native code, CPU fidelity, hardware fidelity, gameplay validation and physical latency are not claimed by this test).

    python -B tools/sg1000_player_selftest.py [--work DIR] [--reuse-build]

The work folder (default .build/sg1000-player-selftest) holds generated sources and executables only; no window is shown (hidden
window, offscreen video driver, dummy audio) and every run is bounded. The windowed runs use a test double of the game (`game_probe`):
the same sources, with the kit's picture upload and keyboard state renamed to a probe that records the picture of every frame and pushes
the test's key presses; the double is console-subsystem so that its standard error is readable. The shipped `game` is the one run
headless and compared. A windowed run is paced in real time (about a second per sixty frames).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('RETRO_RECOMP_TOOLCHAIN', 'llvm')
os.environ.setdefault('RETRO_RECOMP_BUILD_JOBS', '4')

TITLE = 'Authored SG-1000 Test'
BUILD_TIMEOUT = 2 * 3600
NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

# Fields that are cumulative counters of the PROCESS, not of the machine: a process that loaded a state has not seen the frames before it.
PROCESS_FIELDS = ('engine', 'interrupts', 'nmi', 'audio_samples', 'audio_fnv', 'native_steps', 'halt_steps', 'fallback_steps',
                  'guarded_steps', 'fallback_cycles', 'fallback_at')
NATIVE_ONLY = ('native_steps', 'halt_steps', 'fallback_steps', 'guarded_steps', 'fallback_cycles', 'fallback_at')

# The route every run replays: pad 1 right, release, pad 2 up + button 1, Pause, both buttons, Pause... then events after the saved frame.
ROUTE = ['20:pad:0:08', '60:pad:0:00', '90:pad:1:11', '120:pause', '130:pad:0:30', '200:pause', '230:pad:0:00', '300:pad:0:04',
         '330:pad:1:40', '336:pad:1:00', '400:pause', '500:pad:0:21', '700:pad:0:00', '760:pause']      # 330: Pause pressed as a bit of seat 2's word
WATCH = ['C000', 'C001', 'C002', 'C003']


# ---- the authored cartridge: Z80 bytes assembled here, 8 KiB, no ROM ----
def vdp_reg(reg: int, value: int) -> bytes:
    return bytes([0x3E, value, 0xD3, 0xBF, 0x3E, 0x80 | reg, 0xD3, 0xBF])            # LD A,v; OUT (BF),A; LD A,80h|r; OUT (BF),A


def vdp_address(address: int) -> bytes:
    return bytes([0x3E, address & 0xFF, 0xD3, 0xBF, 0x3E, (address >> 8) | 0x40, 0xD3, 0xBF])   # VRAM write address


def vdp_data(value: int) -> bytes:
    return bytes([0x3E, value, 0xD3, 0xBE])


def psg_byte(value: int) -> bytes:
    return bytes([0x3E, value, 0xD3, 0x7F])


def authored_cartridge() -> bytes:
    """Graphics 1, a checker tile on the top third, a tone, the frame counter at C000, the Pause (/NMI) count at C001, the pads read into
    C002 (port DC) and C003 (port DD); each frame's interrupt sets the backdrop colour from the directions held and writes the Pause
    count into the last cell of the name table (so a held key and a Pause show in the picture); a three-instruction routine copied to RAM
    and called every frame is the counted interpreter fallback (LD B,6Dh; LD C,B; RET, four bytes the ROM never holds)."""
    image = bytearray(b'\xFF' * 0x2000)

    def put(at: int, *parts: bytes) -> int:
        data = b''.join(parts)
        image[at:at + len(data)] = data
        return at + len(data)

    put(0x0000, bytes([0xF3, 0x31, 0x00, 0xC4, 0xC3, 0x00, 0x01]))                    # DI; LD SP,C400h; JP 0100h
    put(0x0038, bytes([0xC3, 0x00, 0x02]))                                            # /INT: JP 0200h
    put(0x0066, bytes([0xF5, 0x3A, 0x01, 0xC0, 0x3C, 0x32, 0x01, 0xC0, 0xF1, 0xED, 0x45]))   # /NMI: the Pause count at C001; RETN
    put(0x0100,
        bytes([0xED, 0x56]),                                                          # IM 1
        bytes([0x21, 0x00, 0xC1, 0x36, 0x06, 0x23, 0x36, 0x6D, 0x23, 0x36, 0x48, 0x23, 0x36, 0xC9]),   # LD HL,C100h and the four bytes
                                                                              # LD B,6Dh; LD C,B; RET into RAM
        vdp_reg(0, 0x00), vdp_reg(1, 0xE0), vdp_reg(2, 0x00), vdp_reg(3, 0x80), vdp_reg(4, 0x01), vdp_reg(7, 0x04),
        vdp_address(0x0808), *(vdp_data(v) for v in (0xAA, 0x55) * 4),               # the pattern of tile 1: a checker
        vdp_address(0x2000), vdp_data(0xA0),                                          # colours of tiles 0-7: yellow on the backdrop
        vdp_address(0x0000), bytes([0x06, 0x00, 0x3E, 0x01, 0xD3, 0xBE, 0x10, 0xFC]),  # 256 name-table cells = tile 1
        psg_byte(0x8E), psg_byte(0x0F), psg_byte(0x90),                               # tone 0, loudest
        bytes([0xFB, 0x76, 0x18, 0xFD]))                                              # EI; HALT; JR HALT
    put(0x0200,
        bytes([0xF5, 0xCD, 0x00, 0xC1,                                                # PUSH AF; CALL C100h (code run from RAM: fallback)
               0xDB, 0xBF,                                                            # IN A,(BF): the frame flag is read and cleared
               0x3A, 0x00, 0xC0, 0x3C, 0x32, 0x00, 0xC0,                              # the frame counter
               0xDB, 0xDC, 0x32, 0x02, 0xC0,                                          # IN A,(DC): pad 1 (active low) into C002
               0x2F, 0xE6, 0x0F, 0xEE, 0x04,                                          # CPL; AND 0Fh; XOR 04h: the backdrop from the directions held
               0xD3, 0xBF, 0x3E, 0x87, 0xD3, 0xBF,                                    # R#7 = it
               0xDB, 0xDD, 0x32, 0x03, 0xC0,                                          # IN A,(DD): pad 2 into C003
               0x3E, 0xFF, 0xD3, 0xBF, 0x3E, 0x42, 0xD3, 0xBF,                        # VRAM write address 02FFh (the last name-table cell)
               0x3A, 0x01, 0xC0, 0xD3, 0xBE,                                          # the Pause count as a tile
               0xF1, 0xFB, 0xED, 0x4D]))                                              # POP AF; EI; RETI
    return bytes(image)


PROBE_SOURCE = r'''/* Test double of the SG-1000 game's host: the kit's picture upload and keyboard state, renamed to these (the self-test's CMake file does
 * it for two copies of the kit's files only). Records the picture of every frame (a hash, the colours, the pixels that are not black)
 * and plays the keys the test asks for. SGPROBE_OUT: the file; SGPROBE_SCRIPT: items separated by ';', "Key@frame" (a key press) or
 * "hold:Key+Key@from-to" (keys held for the frames from..to-1). Never part of a game. */
#include <SDL.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct { int hold; SDL_Scancode keys[4]; int count; unsigned from, to; } Item;
static Item items[64];
static int item_count, loaded;
static unsigned frame;
static FILE *out;
static Uint8 state[SDL_NUM_SCANCODES];

static void load(void)
{
    if (loaded) return;
    loaded = 1;
    const char *path = getenv("SGPROBE_OUT"), *script = getenv("SGPROBE_SCRIPT");
    out = path ? fopen(path, "w") : NULL;
    char text[1024];
    snprintf(text, sizeof text, "%s", script ? script : "");
    for (char *item = text; item && *item && item_count < 64; ) {       /* items by hand: strtok cannot nest */
        char *end = strchr(item, ';');
        if (end) *end = 0;
        Item *it = &items[item_count];
        char *at = strchr(item, '@');
        if (at) {
            *at++ = 0;
            it->hold = !strncmp(item, "hold:", 5);
            char *names = it->hold ? item + 5 : item;
            while (names && *names && it->count < 4) {
                char *plus = strchr(names, '+');
                if (plus) *plus = 0;
                it->keys[it->count++] = SDL_GetScancodeFromName(names);
                names = plus ? plus + 1 : NULL;
            }
            it->from = (unsigned)strtoul(at, &at, 10);
            it->to = *at == '-' ? (unsigned)strtoul(at + 1, NULL, 10) : it->from + 1;
            ++item_count;
        }
        item = end ? end + 1 : NULL;
    }
}

int sgprobe_UpdateTexture(SDL_Texture *texture, const SDL_Rect *rect, const void *pixels, int pitch)
{
    load();
    ++frame;
    if (out && rect && pixels) {
        unsigned hash = 2166136261u, distinct = 0, nonblack = 0;
        Uint32 seen[32];
        for (int y = 0; y < rect->h; ++y) {
            const Uint32 *row = (const Uint32 *)((const Uint8 *)pixels + (size_t)y * pitch);
            for (int x = 0; x < rect->w; ++x) {
                Uint32 p = row[x];
                hash = (hash ^ p) * 16777619u;
                if (p != 0xFF000000u) ++nonblack;
                unsigned k = 0;
                while (k < distinct && seen[k] != p) ++k;
                if (k == distinct && distinct < 32) seen[distinct++] = p;
            }
        }
        fprintf(out, "%u %08x %u %u %d %d\n", frame, hash, distinct, nonblack, rect->w, rect->h);
        fflush(out);
    }
    for (int i = 0; i < item_count; ++i)
        if (!items[i].hold && items[i].from == frame) {
            SDL_Event e;
            memset(&e, 0, sizeof e);
            e.type = SDL_KEYDOWN;
            e.key.state = SDL_PRESSED;
            e.key.keysym.scancode = items[i].keys[0];
            e.key.keysym.sym = SDL_GetKeyFromScancode(items[i].keys[0]);
            SDL_PushEvent(&e);
            e.type = SDL_KEYUP;
            e.key.state = SDL_RELEASED;
            SDL_PushEvent(&e);
        }
    return SDL_UpdateTexture(texture, rect, pixels, pitch);
}

const Uint8 *sgprobe_GetKeyboardState(int *numkeys)
{
    load();
    memset(state, 0, sizeof state);
    for (int i = 0; i < item_count; ++i)
        if (items[i].hold && frame >= items[i].from && frame < items[i].to)
            for (int k = 0; k < items[i].count; ++k) state[items[i].keys[k]] = 1;
    if (numkeys) *numkeys = SDL_NUM_SCANCODES;
    return state;
}
'''


def project_cmake(version: str) -> str:
    """The game's CMake project: the converter's own (retrorecomp/sg1000_build.py project_cmake, the reference, the check and the game),
    plus the test double `game_probe`: the same sources, two copies of the kit's files with two SDL calls renamed, the probe; a console
    program."""
    from retrorecomp import hostkit, sg1000_build
    machine = ' '.join((*sg1000_build.MACHINE_SOURCES, *sg1000_build.SHARED_SOURCES))
    kit = hostkit.sources('sg1000')
    probe_kit = ' '.join(f'hostkit/shell/probe_{Path(n).name}' if Path(n).name in ('rrhk_video.c', 'rrhk_input.c') else n for n in kit)
    return sg1000_build.project_cmake(game=True, version=version) + '\n'.join([
        f'add_executable(game_probe sg1000_player.c sg1000_probe.c {machine} runtime_reference.c retro_menu.c platform_io.c '
        f'runtime_feedback.c {probe_kit}',
        '  $<TARGET_OBJECTS:sg1000_bodies>)',
        'set_source_files_properties(hostkit/shell/probe_rrhk_video.c PROPERTIES COMPILE_DEFINITIONS "SDL_UpdateTexture=sgprobe_UpdateTexture")',
        'set_source_files_properties(hostkit/shell/probe_rrhk_input.c PROPERTIES COMPILE_DEFINITIONS "SDL_GetKeyboardState=sgprobe_GetKeyboardState")',
        'target_include_directories(game_probe PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}" "${CMAKE_CURRENT_SOURCE_DIR}/generated" "${CMAKE_CURRENT_SOURCE_DIR}/hostkit/shell")',
        'if(WIN32)', '  target_sources(game_probe PRIVATE content.rc)', '  target_link_libraries(game_probe PRIVATE shell32 user32 gdi32)',
        'else()', '  target_sources(game_probe PRIVATE embedded_resources.c embedded_resources.S)', '  target_link_libraries(game_probe PRIVATE m)', 'endif()',
        'target_link_libraries(game_probe PRIVATE SDL2::SDL2-static)',
        f'target_compile_definitions(game_probe PRIVATE SDL_MAIN_HANDLED SMSRECOMP_BANKED_AOT _CRT_SECURE_NO_WARNINGS [[RR_RECOMP_VERSION="{version}"]])',
    ]) + '\n'


def stage(work: Path, cartridge: bytes, standard: str) -> None:
    """Everything of the game's project beside the generated bodies: the converter's own packaging (sg1000_conversion.prepare_game, with
    the sources it stages and the resources), plus the probe's files."""
    from retrorecomp import sg1000_conversion, z80_chain_build
    sg1000_conversion.prepare_game(work, hashlib.sha256(cartridge).hexdigest(), (work / 'rom.sms').read_bytes(), TITLE, standard)
    write = z80_chain_build.write_if_changed
    write(work / 'sg1000_probe.c', PROBE_SOURCE.encode('utf-8'))
    for name in ('rrhk_video.c', 'rrhk_input.c'):
        write(work / 'hostkit' / 'shell' / f'probe_{name}', (work / 'hostkit' / 'shell' / name).read_bytes())


def forget_unfound_sdl(*folders: Path) -> None:
    """A build folder whose CMake cache remembers « SDL2_DIR-NOTFOUND » (an earlier configure ran without the SDL2 install in its prefix path)
    is configured again from scratch: the converter's own helper (z80_chain_build.build_project) passes the pinned install by CMAKE_PREFIX_PATH on
    every configure, and nothing else in the folder is worth keeping."""
    for folder in folders:
        cache = folder / 'build' / 'CMakeCache.txt'
        try:
            if 'SDL2_DIR:PATH=SDL2_DIR-NOTFOUND' in cache.read_text(encoding='utf-8', errors='replace'):
                shutil.rmtree(folder / 'build')
        except OSError:
            pass


def build_all(work: Path, cartridge: bytes) -> dict[str, Path]:
    from retrorecomp import __version__, sg1000_build, z80_chain_build
    work.mkdir(parents=True, exist_ok=True)
    forget_unfound_sdl(work, work.parent / (work.name + '-pal'))
    sg1000_build.generate(work, sg1000_build.padded(cartridge))
    stage(work, cartridge, 'ntsc')
    exes = z80_chain_build.build_project(work, ('sg1000_reference', 'sg1000_check', 'game', 'game_probe'), project_cmake(__version__),
                                         sdl=True)
    # The PAL game: the same bodies and sources, another header (the standard is part of the game, as the converter writes it).
    pal = work.parent / (work.name + '-pal')
    pal.mkdir(parents=True, exist_ok=True)
    for path in work.iterdir():
        if path.name != 'build' and path.is_file():
            z80_chain_build.write_if_changed(pal / path.name, path.read_bytes())
    for folder in ('generated', 'hostkit'):
        shutil.copytree(work / folder, pal / folder, dirs_exist_ok=True)
    stage(pal, cartridge, 'pal')
    exes_pal = z80_chain_build.build_project(pal, ('game', 'game_probe'), project_cmake(__version__), sdl=True)
    exes['game_pal'] = exes_pal['game']
    exes['game_probe_pal'] = exes_pal['game_probe']
    return exes


# ---- running ----
def run(args: list, *, env: dict | None = None, timeout: int = 600, cwd: Path | None = None) -> subprocess.CompletedProcess:
    full = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy')
    full.update(env or {})
    return subprocess.run([str(a) for a in args], capture_output=True, timeout=timeout, env=full, creationflags=NO_WINDOW,
                          cwd=str(cwd) if cwd else None)


def route_options(route: list[str]) -> list[str]:
    return [item for event in route for item in ('--event', event)] + [item for name in WATCH for item in ('--watch', name)]


class Results:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.checks = 0

    def check(self, condition: bool, text: str, detail: str = '') -> bool:
        self.checks += 1
        print(('  ok    ' if condition else '  FAIL  ') + text + (f'  [{detail}]' if detail and not condition else ''))
        if not condition:
            self.failures.append(text)
        return condition


def load_rows(path: Path) -> dict[int, str]:
    lines = path.read_text(encoding='utf-8').splitlines()
    return {int(line.split(',')[0]): line for line in lines[1:]}


def headless(exe: Path, folder: Path, name: str, frames: int, extra: list[str], route: list[str] = ROUTE, *, game: bool) -> dict:
    """One headless run of the game (its own resources) or of the check (`--cart`); the report, the rows, the sound and the dumps in `folder`."""
    folder.mkdir(parents=True, exist_ok=True)
    out = {key: folder / f'{name}.{key}' for key in ('report', 'rows', 'audio', 'frame', 'vram')}
    for path in out.values():
        path.unlink(missing_ok=True)
    args = [exe, *(['--headless'] if game else []), '--frames', frames, '--report', out['report'], '--rows', out['rows'], '--audio', out['audio'],
            '--frame', out['frame'], '--vram', out['vram'], *route_options(route), *extra]
    process = run(args)
    result = {'code': process.returncode, 'stderr': process.stderr.decode(errors='replace')[-400:], **out}
    result['json'] = json.loads(out['report'].read_text(encoding='utf-8')) if out['report'].is_file() else None
    return result


def prove_equal_runs(res: Results, exes: dict[str, Path], cart_file: Path, folder: Path) -> None:
    print('(a) the game headless equals the native check (and the check equals the reference)')
    for standard in ('ntsc', 'pal'):
        pal = ['--pal'] if standard == 'pal' else []
        check = headless(exes['sg1000_check'], folder, f'check-{standard}', 840, ['--cart', cart_file, *pal], game=False)
        game = headless(exes['game_pal' if standard == 'pal' else 'game'], folder, f'game-{standard}', 840, [], game=True)
        reference = headless(exes['sg1000_reference'], folder, f'reference-{standard}', 840, ['--cart', cart_file, *pal], game=False)
        res.check(check['code'] == 0 and game['code'] == 0 and reference['code'] == 0, f'{standard}: the three programs ran to the end',
                  f"{check['code']} {game['code']} {reference['code']} {game['stderr']}")
        if not (check['json'] and game['json'] and reference['json']):
            continue
        c, g, r = check['json'], game['json'], reference['json']
        different = {key: (c.get(key), g.get(key)) for key in sorted(set(c) | set(g)) if key != 'engine' and c.get(key) != g.get(key)}
        res.check(not different, f'{standard}: every field of the report equal, game against check ({len(c) - 1} fields)', str(different)[:300])
        res.check(g['engine'] == 'native' and c['engine'] == 'native', f'{standard}: both report the native engine')
        for key in ('rows', 'audio', 'frame', 'vram'):
            same = check[key].read_bytes() == game[key].read_bytes()
            res.check(same and check[key].stat().st_size > 0, f'{standard}: the {key} file equal, byte for byte ({check[key].stat().st_size} bytes)')
        common = {key: (c[key], r.get(key)) for key in c if key not in ('engine', *NATIVE_ONLY) and c[key] != r.get(key)}
        res.check(not common, f'{standard}: native check equals the reference on every common field', str(common)[:300])
        res.check(check['rows'].read_bytes() == reference['rows'].read_bytes(), f'{standard}: the per-frame rows equal the reference\'s')
        res.check(c['frames'] == 840 and c['interrupts'] > 800, f'{standard}: the run is real (840 frames, {c["interrupts"]} interrupts)')
        res.check(c['audio_samples'] > 0 and any(line.split(',')[6] == '1' for line in load_rows(check['rows']).values()),
                  f'{standard}: the sound is audible (a tone, {c["audio_samples"]} samples)')
        res.check(c['watch']['C001'] == 5 and c['watch']['C000'] != 0, f'{standard}: the cartridge saw the 5 Pause presses (four events and a bit of a seat word) and counted frames',
                  str(c['watch']))
        res.check(c['fallback_steps'] > 0 and g['fallback_steps'] == c['fallback_steps'],
                  f'{standard}: the interpreter fallback is counted, the same in the game ({g["fallback_steps"]} steps, at {sorted(g["fallback_at"])})')
        res.check(c['native_steps'] > 0 and g['native_steps'] == c['native_steps'], f'{standard}: native steps counted ({g["native_steps"]})')


def read_state(path: Path) -> bytearray:
    return bytearray(path.read_bytes())


def write_state(path: Path, data: bytes) -> None:
    path.write_bytes(bytes(data))


def refix(data: bytearray) -> bytearray:
    """Recompute the body's length and CRC-32 of the envelope (a crafted state that is whole and undamaged)."""
    body = bytes(data[88:])
    data[80:84] = len(body).to_bytes(4, 'little')
    data[84:88] = zlib.crc32(body).to_bytes(4, 'little')
    return data


# Offsets in the body (layout sg1000-state-2, native/sg1000_machine/sg1000_state_file.inc): the binding 0, the CPU 32 (43 bytes), the
# machine 75 (line 4, cycles 8, next line 8, frames 8, trace 4, /NMI edge 1, Pause latch 1, lines 4, ROM size 4), RAM 117 (1024), VRAM 1141 (16384),
# the registers 17524, status 17532, address 17533.
BODY = 88
OFFSETS = {'cpu_cyc': 32 + 35, 'next_line': 75 + 12, 'nmi_edge': 75 + 32, 'pause_latch': 75 + 33, 'vdp_address': 17534, 'ram': 117, 'vdp_latch': 17536}


def damaged_variants(good: bytes, folder: Path) -> dict[str, Path]:
    variants: dict[str, bytearray] = {}
    v = bytearray(good); v[BODY + 5000] ^= 0x55; variants['one body byte flipped (CRC)'] = v
    v = bytearray(good); variants['cut short'] = bytearray(good[:len(good) // 2])
    variants['empty'] = bytearray()
    variants['one byte more'] = bytearray(good + b'\0')
    variants['garbage'] = bytearray(os.urandom(4000))
    v = bytearray(good); v[0] ^= 1; variants['wrong magic'] = v
    v = bytearray(good); v[16] = (v[16] ^ 1); variants['another game (identity)'] = v
    v = bytearray(good); v[12] ^= 3; variants['another standard (machine field)'] = v
    v = bytearray(good); v[8] = 2; variants['another schema'] = v
    v = bytearray(good); v[BODY] ^= 1; variants['another build (binding), CRC fixed'] = refix(v)
    v = bytearray(good); v[BODY + OFFSETS['vdp_address'] + 1] = 0xFF; variants['crafted: VDP address above 3FFF, CRC fixed'] = refix(v)
    v = bytearray(good); v[BODY + OFFSETS['nmi_edge']] = 2; variants['crafted: /NMI edge 2, CRC fixed'] = refix(v)
    v = bytearray(good); v[BODY + OFFSETS['pause_latch']] = 4; variants['crafted: Pause latch 4, CRC fixed'] = refix(v)
    v = bytearray(good); v[BODY + OFFSETS['next_line']] ^= 0x04; variants['crafted: line clock off, CRC fixed'] = refix(v)
    v = bytearray(good); v[BODY + OFFSETS['cpu_cyc'] + 5] = 0x70; variants['crafted: CPU cycle far ahead of the machine, CRC fixed'] = refix(v)
    v = bytearray(good); v[BODY + OFFSETS['vdp_latch']] = 7; variants['crafted: control latch 7, CRC fixed'] = refix(v)
    paths = {}
    for index, (name, data) in enumerate(variants.items()):
        path = folder / f'damaged-{index}.rrstate'
        write_state(path, data)
        paths[name] = path
    return paths


def prove_states(res: Results, exes: dict[str, Path], folder: Path) -> Path:
    print('(b) quick states: a fresh process continues the same frames; refusals leave everything as it was')
    game = exes['game']
    state = folder / 'saved.rrstate'
    state.unlink(missing_ok=True)
    saved = headless(game, folder, 'state-a', 840, ['--save-state', state, '--save-at', '240'], game=True)
    res.check(saved['code'] == 0 and state.is_file(), f'the saving run ends 0 and writes the state ({state.stat().st_size if state.is_file() else 0} bytes)',
              saved['stderr'])
    loaded = headless(game, folder, 'state-b', 840, ['--load-state', state], game=True)
    res.check(loaded['code'] == 0, 'a FRESH process loads the state and runs to frame 840', f"{loaded['code']} {loaded['stderr']}")
    if saved['json'] and loaded['json']:
        a, b = load_rows(saved['rows']), load_rows(loaded['rows'])
        after = [frame for frame in a if frame > 240]
        res.check(len(after) == 600 and sorted(b) == sorted(after), f'the loaded run wrote rows for the 600 frames after the saved one ({len(b)})')
        res.check(len({a[frame].split(',', 1)[1] for frame in after}) > 500, 'the rows are not constant: the comparison could fail (positive control)')
        wrong = [frame for frame in after if a[frame] != b.get(frame)]
        res.check(not wrong, 'every row (CPU, RAM, picture, sound, samples, audible, PC) of the 600 frames equals the saving run\'s', str(wrong[:5]))
        ja, jb = saved['json'], loaded['json']
        different = {k: (ja[k], jb[k]) for k in ja if k not in PROCESS_FIELDS and ja[k] != jb[k]}
        res.check(not different, 'the final machine state (registers, cycles, RAM, VRAM, picture, VDP, PSG, watched bytes) equals the saving run\'s',
                  str(different)[:300])
        res.check(jb['watch']['C001'] == ja['watch']['C001'] == 5, 'the Pause already taken before the state is not taken twice (and the later ones are)',
                  str(jb['watch']))
    # PAL: the same on the PAL game; and a state of one standard is refused by the other.
    pal_state = folder / 'saved-pal.rrstate'
    pal_state.unlink(missing_ok=True)
    pa = headless(exes['game_pal'], folder, 'state-pal-a', 400, ['--save-state', pal_state, '--save-at', '150'], game=True)
    pb = headless(exes['game_pal'], folder, 'state-pal-b', 400, ['--load-state', pal_state], game=True)
    if pa['json'] and pb['json']:
        a, b = load_rows(pa['rows']), load_rows(pb['rows'])
        res.check(all(a[f] == b[f] for f in a if f > 150) and len([f for f in a if f > 150]) == len(b),
                  'PAL: a fresh process continues the same frames (250 frames)')
    for name, exe, file in (('an NTSC state in the PAL game', exes['game_pal'], state), ('a PAL state in the NTSC game', game, pal_state)):
        digest = hashlib.sha256(file.read_bytes()).hexdigest()
        refused = run([exe, '--headless', '--frames', 100, '--load-state', file])
        res.check(refused.returncode == 4 and hashlib.sha256(file.read_bytes()).hexdigest() == digest, f'{name}: refused (exit 4), the file unchanged')
    # Refusals: nothing is created, the file stays as it was, the process ends 4 without having run.
    missing = folder / 'absent' / 'nothing.rrstate'
    refused = run([game, '--headless', '--frames', 100, '--load-state', missing])
    res.check(refused.returncode == 4 and not missing.exists() and not missing.parent.exists(), 'a missing state: refused (exit 4), nothing created')
    good = state.read_bytes()
    for name, path in damaged_variants(good, folder).items():
        digest, listing = hashlib.sha256(path.read_bytes()).hexdigest(), sorted(p.name for p in folder.iterdir())
        refused = run([game, '--headless', '--frames', 100, '--load-state', path, '--report', folder / 'refused.json'])
        res.check(refused.returncode == 4 and hashlib.sha256(path.read_bytes()).hexdigest() == digest and sorted(p.name for p in folder.iterdir()) == listing
                  and not (folder / 'refused.json').exists(), f'refused (exit 4, file unchanged, nothing written, no report): {name}', str(refused.returncode))
    return state


def prove_snapshots(res: Results, exes: dict[str, Path], folder: Path) -> None:
    print('(d) multiplayer snapshots: a rollback replays the same frames, the digest is the same, a wrong size is refused')
    for label, game, at, count in (('NTSC', exes['game'], 300, 120), ('NTSC, later', exes['game'], 520, 60), ('PAL', exes['game_pal'], 300, 120)):
        process = run([game, '--headless', '--frames', at + 2 * count + 20, '--snap-probe', f'{at}:{count}', *route_options(ROUTE)])
        text = process.stderr.decode(errors='replace')
        line = next((l for l in text.splitlines() if l.startswith('snap-probe:')), '')
        folded = line.rsplit('digests ', 1)[-1] if 'digests ' in line else '?'
        res.check(process.returncode == 0 and ': PASS at' in line, f'{label}: snapshot at frame {at}, {count} frames, load, the same {count} frames, every digest equal (folded {folded})', line or text[-300:])
        if label == 'NTSC':
            size = line.split(' bytes ')[0].rsplit(' ', 1)[-1] if line else '0'
            res.check(line and 'same over other bytes 1' in line and 'wrong size refused 1' in line,
                      f'  the snapshot ({size} bytes) is the same bytes twice, fits its bound, and one byte short is refused and changes nothing')


def window(exe: Path, run_folder: Path, frames: int, script: str, *, state: Path | None = None, game: Path | None = None) -> dict:
    """One windowed run of the test double in a clean folder (hidden window, offscreen video, dummy audio); the probe's rows, the state file."""
    if run_folder.exists():
        shutil.rmtree(run_folder)
    run_folder.mkdir(parents=True)
    copy = run_folder / 'game_probe.exe'
    shutil.copyfile(exe, copy)
    identity = (game or exe).parent.parent.joinpath('sg1000_game.h').read_text(encoding='ascii').split('RR_SG_IDENTITY "')[1][:12]
    data = run_folder / 'datas' / 'games' / f'sg1000-{identity}'
    if state is not None:
        data.mkdir(parents=True)
        shutil.copyfile(state, data / 'quick.rrstate')
    probe = run_folder / 'probe.txt'
    process = run([copy], env={'SDL_VIDEODRIVER': 'offscreen', 'SDL_AUDIODRIVER': 'dummy', 'RETRORECOMP_HOST_TEST_FRAMES': str(frames),
                               'SGPROBE_OUT': str(probe), 'SGPROBE_SCRIPT': script}, timeout=300, cwd=run_folder)
    rows = [tuple(line.split()) for line in probe.read_text(encoding='ascii').splitlines()] if probe.is_file() else []
    stderr = process.stderr.decode(errors='replace')
    host = next((json.loads(line) for line in stderr.splitlines() if line.startswith('{"host_frames"')), None)
    return {'code': process.returncode, 'rows': rows, 'hashes': [r[1] for r in rows], 'stderr': stderr, 'host': host,
            'state': data / 'quick.rrstate'}


def prove_window(res: Results, exes: dict[str, Path], saved_state: Path, folder: Path) -> None:
    print('(c) the game windowed (offscreen video, dummy audio, hidden window): presents frames, answers the keys, quick states in play')
    probe = exes['game_probe']
    base = folder / 'window'
    plain = window(probe, base / 'plain', 200, '')
    res.check(plain['code'] == 0, 'the windowed game ends with exit 0 at the frame limit', f"{plain['code']} {plain['stderr'][-300:]}")
    res.check(plain['host'] is not None and plain['host']['host_frames'] == 200 and len(plain['rows']) == 201,
              'the kit ran 200 frames and presented a picture each (201: the first guest frame is shown before the kit counts)', str(plain['host']))
    rows = plain['rows']
    steady = rows[10:]
    res.check(bool(steady) and all(int(r[2]) >= 2 and int(r[3]) > 0.3 * 272 * 208 for r in steady) and all((r[4], r[5]) == ('272', '208') for r in rows),
              'every picture after the first frames is not blank: two colours or more, over 30% of the 272 x 208 pixels not black')
    res.check(len(set(r[1] for r in steady)) == 1, 'the picture is steady while nothing is pressed (one hash)', str(len(set(r[1] for r in steady))))
    idle = plain['hashes'][20]
    keys = window(probe, base / 'keys', 160, 'hold:Right+S@30-60;hold:Return@90-96')
    h = keys['hashes']
    res.check(keys['code'] == 0 and len(h) == 161, 'the run with keys ends 0 and presents 161 pictures')
    held, released, paused = set(h[40:58]), set(h[70:88]), set(h[100:160])
    res.check(h[20] == idle and len(set(h[10:28])) == 1, 'before the keys, the same picture as the plain run')
    res.check(len(held) == 1 and held != {idle}, 'RIGHT + S held: the cartridge reads them through port DC and the picture changes (backdrop)')
    res.check(released == {idle}, 'released: the picture returns to the first one')
    res.check(len(paused) == 1 and paused != {idle} and paused != held, 'the Pause key (Enter) raises /NMI: the cartridge counts it into the picture, once')
    pal = window(exes['game_probe_pal'], base / 'pal', 150, 'hold:Right@30-60')
    expected = 3579545 / (228 * 313)
    res.check(pal['code'] == 0 and pal['host'] is not None and pal['host']['host_frames'] == 150 and abs(pal['host']['target_fps'] - expected) < 0.001,
              f'PAL game windowed: 150 frames at the pace of its 313 lines ({expected:.2f} Hz), exit 0', str(pal['host']))
    res.check(len(pal['rows']) == 151 and all(int(r[2]) >= 2 and int(r[3]) > 0.3 * 272 * 208 for r in pal['rows'][10:]) and len(set(pal['hashes'][40:58])) == 1
              and pal['hashes'][40] != pal['hashes'][20], 'PAL game windowed: pictures not blank, and the held key shows')
    # F8 saves, F9 loads, in play. Sequence: F8 at 40 (the Pause count is 0), Pause at 60 (1), F9 at 90 (back to 0), Pause at 120 (1 again).
    quick = window(probe, base / 'states', 170, 'F8@40;hold:Return@60-66;F9@90;hold:Return@120-126')
    q = quick['hashes']
    res.check(quick['code'] == 0 and len(q) == 171 and quick['state'].is_file() and quick['state'].stat().st_size > 60000,
              f'F8 in play writes the quick state beside the game ({quick["state"].stat().st_size if quick["state"].is_file() else 0} bytes)')
    pause_look = set(q[70:88])
    res.check(set(q[20:38]) == {idle} and len(pause_look) == 1 and pause_look != {idle}, 'the Pause after F8 shows in the picture')
    res.check(set(q[100:118]) == {idle}, 'F9 in play loads it: the picture and the Pause count are back as they were at F8')
    res.check(set(q[130:170]) == pause_look, 'and the game goes on, live: the next Pause counts 1 (not 2), the picture is the first Pause\'s')
    # A FRESH window process loads the state another process saved, and goes on as that one did: A saves at 80 (Pause count 1) then takes a
    # Pause at 100 (count 2); B starts clean, loads at 20 and takes its Pause at 40: B's frames from 21 are A's from 81.
    carry_a = window(probe, base / 'carry-a', 170, 'hold:Return@60-66;F8@80;hold:Return@100-106')
    carry_b = window(probe, base / 'carry-b', 120, 'F9@20;hold:Return@40-46', state=carry_a['state'])
    a, b = carry_a['hashes'], carry_b['hashes']
    res.check(carry_a['code'] == 0 and carry_b['code'] == 0 and len(a) == 171 and len(b) == 121 and a[81:161] == b[21:101],
              "a fresh windowed process loads another process's quick state (F9) and shows the same 80 frames after it")
    res.check(len(set(b[21:101])) == 2 and b[30] != b[60], '  (positive control: those frames are not all alike; the Pause count came with the state)')
    # Refused F9s leave the frames as a run that never asked: the control presses Pause at 70 only.
    control = window(probe, base / 'control', 120, 'hold:Return@70-76')
    good = saved_state.read_bytes()
    bad = bytearray(good); bad[BODY + 7000] ^= 0x10
    foreign = bytearray(good); foreign[16] ^= 1
    crafted = bytearray(good); crafted[BODY + OFFSETS['vdp_address'] + 1] = 0xFF
    cases = [('missing', 'a missing', None), ('damaged', 'a damaged', bad), ('foreign', "another game's", foreign),
             ('crafted', 'a crafted (CRC valid)', refix(crafted))]
    for key, label, data in cases:
        path = None
        if data is not None:
            path = folder / f'window-{key}.rrstate'
            write_state(path, data)
        trial = window(probe, base / f'refused-{key}', 120, 'F9@50;hold:Return@70-76', state=path)
        same = trial['code'] == 0 and trial['hashes'] == control['hashes'] and len(control['hashes']) == 121
        res.check(same, f'F9 with {label} state is refused and every frame equals a run that never asked ({len(trial["hashes"])} frames)')
        if path is None:
            res.check(not trial['state'].exists(), '  a missing state creates nothing')
        else:
            res.check(trial['state'].read_bytes() == path.read_bytes(), f'  the {label} file is left as it was')


def main() -> int:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--work', type=Path, default=ROOT / '.build' / 'sg1000-player-selftest')
    parser.add_argument('--reuse-build', action='store_true', help='run the proofs on the executables already built in the work folder')
    args = parser.parse_args()
    work = args.work.resolve()
    cartridge = authored_cartridge()
    if args.reuse_build:
        exes = {'sg1000_reference': None, 'sg1000_check': None, 'game': None, 'game_probe': None}
        from retrorecomp.platforms import build_executable
        exes = {target: build_executable(work / 'build', target) for target in exes}
        exes['game_pal'] = build_executable(work.parent / (work.name + '-pal') / 'build', 'game')
        exes['game_probe_pal'] = build_executable(work.parent / (work.name + '-pal') / 'build', 'game_probe')
    else:
        exes = build_all(work, cartridge)
    results = Results()
    runs = work.parent / (work.name + '-runs')
    runs.mkdir(parents=True, exist_ok=True)
    cart_file = runs / 'authored.sg'
    cart_file.write_bytes(cartridge)
    prove_equal_runs(results, exes, cart_file, runs / 'headless')
    saved = prove_states(results, exes, runs / 'states')
    prove_window(results, exes, saved, runs)
    prove_snapshots(results, exes, runs)
    print(f'{results.checks} checks, {len(results.failures)} failed')
    for failure in results.failures:
        print('FAILED:', failure)
    return 1 if results.failures else 0


if __name__ == '__main__':
    sys.exit(main())
