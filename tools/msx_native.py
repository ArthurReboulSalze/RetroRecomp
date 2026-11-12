"""MSX stage 2: native code. The cartridge and the BIOS translated ahead of time by the shared banked Z80 chain, run
headless, compared with the reference interpreter state for state.

The MSX machine on the chain (it moves into the MSX profile at stage 5): a region map of eight 8 KB regions, two sources
(the cartridge, then the BIOS: C-BIOS 0.29a's main ROM and logo ROM as one 48 KB image), one wait state per M1 cycle,
/INT read at the end of each instruction, its own generator folders. For each cartridge the tool writes a work folder
(.build/msx-native/<name>/: the cartridge as rom.sms, the BIOS image, banked.sources, game.toml), runs the generator
(--banked-step), builds the native runner (native/msx_machine/msx_native_main.c with the generated bodies, the step
loop rendered for the MSX and the counted fallback on the reference CPU), runs it and the reference runner with the same
options, and compares: CPU registers, RAM, VRAM, the picture, the sound, frames, cycles and interrupts. A development
check: nothing here makes a game.

    python -B tools/msx_native.py [--frames 300] [--only NAME]...
    python -B tools/msx_native.py --library <ROM folder> --game "msx1/Road Fighter (Japan).zip" ...

With --game the player's cartridges are converted the same way: the zip member is read into memory; the work folder
holds it only while the generator runs (then it is deleted; the runs read it on their standard input). Generated bodies
and pictures of a commercial game stay under .build, never committed.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import msx_reference  # noqa: E402
import msx_rom  # noqa: E402
from retrorecomp.z80_chain import Z80Machine, Z80RegionMap, banked_runtime  # noqa: E402

MSX_MACHINE = Z80Machine('msx', Z80RegionMap(region_bits=13, sources=('cartridge', 'bios'), bank_values=256,
                                             scope='msx-cartridge-region-map'),
                         m1_wait=1, irq_sample='instruction_end', generator_tag='-msx')
WORK = ROOT / '.build' / 'msx-native'
# The fields the native run must give exactly as the reference does.
COMPARED = ('frames', 'cycles', 'interrupts', 'pc', 'sp', 'af', 'bc', 'de', 'hl', 'ix', 'iy', 'af2', 'bc2', 'de2', 'hl2',
            'i', 'r', 'im', 'iff1', 'iff2', 'wz', 'halted', 'primary', 'secondary', 'vdp_regs', 'vdp_status', 'vram_fnv',
            'ram_fnv', 'frame_fnv', 'frame_trace', 'audio_samples', 'audio_fnv', 'psg', 'psg_latch', 'port_c', 'blocks',
            'watch')


def _loop_cartridge(code: bytes) -> bytes:
    image = bytearray(b'\xFF' * 0x4000)
    image[0:16] = b'AB' + (0x4010).to_bytes(2, 'little') + bytes(12)
    image[0x10:0x10 + len(code)] = code
    return bytes(image)


def cartridge_prefix_io() -> bytes:
    """VDP register 7 (the border) written through OUT (C),A behind a redundant DD prefix, forever: the I/O of a prefix
    chain must happen at the chain's start, as the reference runs the chain as one instruction."""
    code = bytes([0x0E, 0x99,                          # 4010h: LD C,99h
                  0x3E, 0x01, 0xDD, 0xED, 0x79,        # 4012h: loop: LD A,1;   DD OUT (C),A
                  0x3E, 0x87, 0xDD, 0xED, 0x79,        #        LD A,87h; DD OUT (C),A   (R#7 = 1)
                  0x3E, 0x0F, 0xDD, 0xED, 0x79,        #        LD A,0Fh; DD OUT (C),A
                  0x3E, 0x87, 0xDD, 0xED, 0x79,        #        LD A,87h; DD OUT (C),A   (R#7 = 15)
                  0x18, 0xEA])                         # 4026h: JR loop (4028h - 22 = 4012h)
    return _loop_cartridge(code)


def cartridge_ei_ex() -> bytes:
    """EI; EX (SP),IX; JR back, forever: an interrupt is accepted after the EX, never right after the EI; the run must
    stop at the frame limit on the same instruction boundary as the reference."""
    return _loop_cartridge(bytes([0xFB, 0xDD, 0xE3, 0x18, 0xFB]))


def padded(image: bytes) -> bytes:
    """The cartridge as the machine sees it: whole banks (16 KB for ASCII 16, else 8 KB), padded with FFh. The generator
    keys positions modulo the image size, so it must get exactly this image."""
    unit = 0x4000 if msx_rom.guess(image).mapper == 'ascii16' else 0x2000
    return image + b'\xFF' * (-len(image) % unit)
GAME_TOML = '''# MSX: the cartridge is source 0 of the region map; the BIOS is named in banked.sources.
[game]
output_prefix = "game"
platform = "sms"
rom = "rom.sms"
crc32 = 0x00000000
[mapper]
kind = "sega"
[functions]
extra = []
blacklist = []
'''


def generator() -> tuple[Path, Path, str]:
    """The MSX machine's own Z80 -> C generator (built once, in its own folders), the engine, cmake and generator."""
    from retrorecomp import core
    from retrorecomp.platforms import build_executable
    engine, _, cmake, kind = core.dependencies(lambda text: print(text, flush=True), MSX_MACHINE)
    from retrorecomp.toolchain import suffix
    return build_executable(ROOT / '.deps' / (MSX_MACHINE.generator_build + suffix()), 'SmsRecomp'), engine, kind


def build(name: str, image: bytes, bios_image: bytes, keep_rom: bool = True) -> Path:
    from retrorecomp import toolchain
    from retrorecomp.cpu import prepare_cpu_headers, prepare_reference
    from retrorecomp.paths import ASSETS
    from retrorecomp.platforms import build_executable, cmake_target_args
    tool, engine, kind = generator()
    game = WORK / name
    (game / 'generated').mkdir(parents=True, exist_ok=True)
    for stale in (game / 'generated').glob('game_banked_ops_*.c'):
        stale.unlink()
    (game / 'rom.sms').write_bytes(image)
    (game / 'bios.rom').write_bytes(bios_image)
    (game / 'banked.sources').write_text(str((game / 'bios.rom').resolve()) + '\n', encoding='utf-8', newline='\n')
    (game / 'game.toml').write_text(GAME_TOML, encoding='utf-8', newline='\n')
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    log = game / 'build.log'
    with log.open('w', encoding='utf-8') as out:
        result = subprocess.run([str(tool), '--game', str(game / 'game.toml'), '--banked-step'], stdout=out,
                                stderr=subprocess.STDOUT, timeout=900, creationflags=flags)
    if result.returncode:
        raise SystemExit(f'generator failed, see {log}')
    if not keep_rom:
        (game / 'rom.sms').unlink()             # a player's ROM: the runs read it on their standard input
    prepare_cpu_headers(game, engine)
    prepare_reference(game, engine, m1_counter=MSX_MACHINE.counts_m1)
    (game / 'msx_banked_loop.inc').write_text(banked_runtime(MSX_MACHINE, ASSETS), encoding='utf-8', newline='\n')
    native = (ROOT / 'native' / 'msx_machine').as_posix()
    (game / 'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.21)
project(MsxNative C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded")
file(GLOB bodies "generated/game_banked_ops_*.c")
add_executable(msx_native "{native}/msx_native_main.c" "{native}/msx_machine.c" "{native}/msx_video.c"
               "{native}/msx_psg.c" "{native}/msx_cart.c" generated/game_banked_index.c ${{bodies}} runtime_reference.c)
target_include_directories(msx_native PRIVATE "${{CMAKE_CURRENT_SOURCE_DIR}}" "${{CMAKE_CURRENT_SOURCE_DIR}}/generated" "{native}")
target_compile_definitions(msx_native PRIVATE SMSRECOMP_BANKED_AOT _CRT_SECURE_NO_WARNINGS)
if(NOT WIN32)
  target_link_libraries(msx_native PRIVATE m)
endif()
''', encoding='utf-8', newline='\n')
    selection = toolchain.select()
    with log.open('a', encoding='utf-8') as out:
        for step in ([str(selection.cmake), '-S', str(game), '-B', str(game / 'build'), '-G', selection.generator,
                      '-DCMAKE_BUILD_TYPE=Release', *cmake_target_args()],
                     [str(selection.cmake), '--build', str(game / 'build'), '--config', 'Release']):
            result = subprocess.run(step, stdout=out, stderr=subprocess.STDOUT, timeout=1800, creationflags=flags)
            if result.returncode:
                raise SystemExit(f'native build failed, see {log}')
    return build_executable(game / 'build', 'msx_native')


def run(exe: Path, args: list[str], image: bytes | None = None) -> dict:
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    result = subprocess.run([str(exe), *args, *(['--cart', '-'] if image is not None else [])], input=image,
                            capture_output=True, timeout=900, creationflags=flags)
    if result.returncode:
        raise SystemExit(f'{exe.name} failed: {result.stderr.decode(errors="replace").strip()[-500:]}')
    return json.loads(result.stdout)


def compare(name: str, image: bytes | None, args: list[str], reference_exe: Path, bios_image: bytes,
            keep_rom: bool = True) -> dict:
    """Build the native runner for this cartridge, learn the code the interpreter ran from RAM (at most three passes,
    as a conversion does: it stops when nothing fell back or nothing new was seen), then compare a run with the
    reference."""
    game = WORK / name
    patterns = game / 'native.patterns'
    patterns.unlink(missing_ok=True)
    passes = []
    for _ in range(3):
        native_exe = build(name, padded(image) if image is not None else b'\xFF' * 0x2000, bios_image, keep_rom)
        learned = game / 'learned.txt'
        learned.unlink(missing_ok=True)
        trial = run(native_exe, [*args, '--learn', str(learned)], image)
        passes.append(trial['fallback_steps'])
        if not trial['fallback_steps'] or not learned.is_file():
            break
        known = set(patterns.read_text(encoding='utf-8').split()) if patterns.is_file() else set()
        seen = set(learned.read_text(encoding='utf-8').split())
        if seen <= known:
            break
        patterns.write_text(''.join(f'{line}\n' for line in sorted(known | seen)), encoding='utf-8', newline='\n')
    reference = run(reference_exe, args, image)
    native = run(native_exe, args, image)
    native['passes'] = passes
    differences = {key: (native.get(key), reference.get(key)) for key in COMPARED
                   if key not in native or key not in reference or native[key] != reference[key]}
    executed = native['native_steps'] + native['fallback_steps']           # instructions, HALT cycles apart
    return {'native': native, 'reference': reference, 'differences': differences,
            'native_share': native['native_steps'] / max(1, executed)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--frames', type=int, default=300)
    parser.add_argument('--only', action='append')
    parser.add_argument('--json', type=Path)
    parser.add_argument('--library', type=Path, help="the player's ROM folder, read in place (with --game)")
    parser.add_argument('--game', action='append', help='a cartridge of the library, e.g. "msx1/Road Fighter (Japan).zip"')
    args = parser.parse_args()
    roms = msx_reference.cbios()
    reference_exe = msx_reference.build()
    bios_image = (roms / 'cbios_main_msx1.rom').read_bytes() + (roms / 'cbios_logo_msx1.rom').read_bytes()
    bios = ['--main', str(roms / 'cbios_main_msx1.rom'), '--logo', str(roms / 'cbios_logo_msx1.rom')]
    frames = ['--frames', str(args.frames)]
    watch = [w for a in (0xE000, 0xE001, 0xE002, 0xE003, 0xFC9E, 0xFC9F) for w in ('--watch', f'{a:04X}')]
    cases = {'no-cartridge': None, 'authored16': msx_reference.cartridge_16k(), 'authored32': msx_reference.cartridge_32k(),
             'polling': msx_reference.cartridge_polling(), 'sound': msx_reference.cartridge_sound(),
             'odd-size-12k': msx_reference.cartridge_16k()[:0x3000], 'prefix-io': cartridge_prefix_io(),
             'ei-ex': cartridge_ei_ex()}
    for kind in msx_reference.MAPPER_CARTRIDGES:
        cases[f'mapper-{kind}'] = msx_reference.cartridge_mapper(kind)
    players = set()
    if args.game:
        import msx_first_read
        cases = {}
        for game in args.game:
            name = msx_first_read.slug(game)
            cases[name] = msx_first_read.read_rom(args.library / game)
            players.add(name)
    results, failures = {}, []
    for name, image in cases.items():
        if args.only and name not in args.only:
            continue
        extra = msx_rom.guess(image).arguments() if image is not None else []
        print(f'{name}: building and running', flush=True)
        start = (['--event', '600:key:8:0:1', '--event', '610:key:8:0:0', '--event', '660:joy:0:2F',
                  '--event', '670:joy:0:3F'] if name in players else [])
        result = compare(name, image, [*bios, *extra, *frames, *watch, *start], reference_exe, bios_image,
                         name not in players)
        results[name] = result
        n = result['native']
        print(f"  passes (fallback steps) {n['passes']}; native {n['native_steps']} + halt {n['halt_steps']} steps, fallback {n['fallback_steps']} steps "
              f"({n['fallback_cycles']} cycles) at {n['fallback_at']}; translated share of executed instructions {result['native_share']:.4%}")
        if result['differences']:
            failures.append(name)
            for key, (got, want) in result['differences'].items():
                print(f'  DIFFERS {key}: native {got}, reference {want}')
        else:
            print(f'  equal to the reference on {len(COMPARED)} fields (frame trace included) after {n["frames"]} frames')
    if args.json:
        args.json.write_text(json.dumps(results, indent=1), encoding='utf-8')
    print('MSX native:', 'PASS' if not failures else f'{len(failures)} differ: {", ".join(failures)}')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
