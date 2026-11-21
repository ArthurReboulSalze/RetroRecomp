"""The ZX Spectrum on the banked Z80 chain: the machine image a converted snapshot starts from (docs/ZX_SPECTRUM.md).

The image is what native/zxs_machine/zxs_machine.c loads (`zxs_load_image`): a 64-byte header (the model, the ports, the
CPU's registers, the T-state within the frame) and the eight RAM banks of 16 KiB. It is built from the snapshot alone; the ROM
is the machine's other input (retrorecomp/zxs_roms.py). The generated bodies, the project and the runs come with the
conversion of stage 2.
"""
from __future__ import annotations

import struct

from .zxs_snapshot import JOYSTICKS, PAGE, Snapshot

IMAGE_HEADER = 64
IMAGE_BYTES = IMAGE_HEADER + 8 * PAGE
# The T-state a snapshot that does not say starts at: the end of the /INT pulse (32 T on the 48K, 36 T on the 128K), so that a
# snapshot taken in its interrupt handler is not interrupted again at once.
INT_END = {'16k': 32, '48k': 32, '128k': 36}
MODEL_BYTE = {'16k': 0, '48k': 0, '128k': 1}
REGISTERS = ('af', 'bc', 'de', 'hl', 'af_', 'bc_', 'de_', 'hl_', 'ix', 'iy', 'sp', 'pc')


def zxs_image(snapshot: Snapshot) -> bytes:
    """The machine image of `snapshot` (IMAGE_BYTES), as zxs_load_image reads it."""
    regs = snapshot.registers
    joystick = JOYSTICKS.index(snapshot.joystick) if snapshot.joystick in JOYSTICKS else 0xFF
    ay = snapshot.ay_registers or (0,) * 16
    header = bytearray(IMAGE_HEADER)
    header[0:4] = b'ZXS1'
    header[4] = MODEL_BYTE[snapshot.model]
    header[5] = 1 if snapshot.model == '16k' else 0
    header[6] = joystick
    header[7] = snapshot.border & 7
    header[8] = snapshot.port_7ffd or 0
    header[9] = (snapshot.ay_select or 0) & 15
    header[10:26] = bytes(value & 0xFF for value in ay)
    header[26:31] = bytes((regs['im'] & 3, regs['iff1'] & 1, regs['iff2'] & 1, regs['i'] & 0xFF, regs['r'] & 0xFF))
    header[32:56] = struct.pack('<12H', *(regs[name] & 0xFFFF for name in REGISTERS))
    tstates = snapshot.tstates if snapshot.tstates is not None else INT_END[snapshot.model]
    header[56:60] = struct.pack('<I', tstates)
    banks = b''.join(snapshot.banks.get(bank, bytes(PAGE)) for bank in range(8))
    return bytes(header) + banks


# ---- the build (stage 2) -------------------------------------------------------------------------------------------------------
# The fields a native run must give exactly as the reference does: the CPU (main and shadow registers, I, R, IM, IFF, WZ, HALT),
# time and interrupts, the RAM, the picture of the last frame and a running hash of every frame, the sound, the ports and the AY.
COMPARED = ('frames', 'cycles', 'interrupts', 'af', 'bc', 'de', 'hl', 'ix', 'iy', 'sp', 'pc', 'af2', 'bc2', 'de2', 'hl2', 'i', 'r',
            'im', 'iff1', 'iff2', 'halted', 'wz', 'port_7ffd', 'border', 'out_fe', 'ay_latch', 'ay', 'ram_fnv', 'frame_fnv',
            'frame_trace', 'audio_samples', 'audio_fnv', 'rows')
GAME_TOML = '''# ZX Spectrum: the ROM is source 0 of the region map (game.toml's rom); there is no other source.
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
MACHINE_SOURCES = ('zxs_machine.c',)
MACHINE_FILES = (*MACHINE_SOURCES, 'zxs_machine.h', 'zxs_glue.inc', 'zxs_headless.inc', 'zxs_cpu_start.inc', 'zxs_native_main.c',
                 'zxs_reference_main.c')
SHARED_MODULES = (('ay38910', ('ay38910.c',), ('ay38910.h',)),)
SHARED_SOURCES = tuple(name for _, sources, _ in SHARED_MODULES for name in sources)
CHAIN_FILES = ('z80_chain_glue.inc', 'banked_reference_state.inc')
BUILD_TIMEOUT = 2 * 3600


class ZxsBuildError(RuntimeError):
    """The generator, the build or a run failed."""


def _flags() -> int:
    import os
    import subprocess
    return subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0


def generate(work, rom: bytes, emit=print, *, keep_rom: bool = True) -> None:
    """The bodies of the ROM in `work/generated`, with the learned patterns (`native.patterns`)."""
    from . import z80_chain_build
    from .systems.zx_spectrum import ZXS_MACHINE
    z80_chain_build.generate_bodies(work, ZXS_MACHINE, ZXS_MACHINE.regions.image(rom), (), GAME_TOML, emit,
                                    loop_name='zxs_banked_loop.inc', accept='zxs_reference_accept', keep_rom=keep_rom,
                                    error=ZxsBuildError)


def stage_sources(work) -> None:
    """The machine, the glue, the mains and the shared files, copied beside the generated bodies."""
    from . import z80_chain_build
    from .paths import ASSETS
    z80_chain_build.stage_files(work, ((ASSETS / 'native' / 'zxs_machine', MACHINE_FILES),
                                       *((ASSETS / 'native' / folder, (*sources, *files)) for folder, sources, files in SHARED_MODULES),
                                       (ASSETS / 'native', CHAIN_FILES)))


def project_cmake(bodies: bool = True) -> str:
    """The project: the reference runner always; with `bodies` the generated bodies and the headless native check."""
    machine = ' '.join((*MACHINE_SOURCES, *SHARED_SOURCES))
    lines = [
        'cmake_minimum_required(VERSION 3.20)',
        'project(RetroZxs LANGUAGES C)',
        'set(CMAKE_C_STANDARD 11)',
        f'add_executable(zxs_reference zxs_reference_main.c {machine} runtime_reference.c)',
    ]
    if bodies:
        lines += [
            'file(GLOB bodies "generated/game_banked_ops_*.c")',
            'add_library(zxs_bodies OBJECT generated/game_banked_index.c ${bodies})',
            'target_include_directories(zxs_bodies PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}" "${CMAKE_CURRENT_SOURCE_DIR}/generated")',
            'target_compile_definitions(zxs_bodies PRIVATE SMSRECOMP_BANKED_AOT)',
            f'add_executable(zxs_check zxs_native_main.c {machine} runtime_reference.c $<TARGET_OBJECTS:zxs_bodies>)',
        ]
    lines += [
        f'foreach(target zxs_reference{" zxs_check" if bodies else ""})',
        '  target_include_directories(${target} PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}" "${CMAKE_CURRENT_SOURCE_DIR}/generated")',
        '  target_compile_definitions(${target} PRIVATE SMSRECOMP_BANKED_AOT _CRT_SECURE_NO_WARNINGS)',
        '  if(NOT WIN32)', '    target_link_libraries(${target} PRIVATE m)', '  endif()',
        'endforeach()',
    ]
    return '\n'.join(lines) + '\n'


def build(work, targets: tuple, emit=print) -> dict:
    """Configure and build `targets` of the project in `work`."""
    from . import core, z80_chain_build
    from .platforms import build_executable
    bodies = 'zxs_check' in targets or (work / 'generated' / 'game_banked_index.c').is_file()
    z80_chain_build.write_if_changed(work / 'CMakeLists.txt', project_cmake(bodies).encode('utf-8'))
    cmake, generator_kind = core.toolchain()
    log = work / 'build.log'
    core.run([cmake, '-S', work, '-B', work / 'build', '-G', generator_kind, *core.cmake_target_args(),
              '-DCMAKE_BUILD_TYPE=Release'], log=log, emit=emit, timeout=BUILD_TIMEOUT)
    for target in targets:
        core.run([cmake, '--build', work / 'build', '--config', 'Release', '--target', target, '--parallel',
                  core.build_jobs()], log=log, emit=emit, timeout=BUILD_TIMEOUT)
    return {target: build_executable(work / 'build', target) for target in targets}


def run(exe, rom_path, image: bytes, args: list, timeout: int = 1800) -> dict:
    """One headless run; its JSON report. The machine image reaches the program on its standard input."""
    import json
    import subprocess
    result = subprocess.run([str(exe), '--rom', str(rom_path), '--image', '-', *args], input=image, capture_output=True,
                            timeout=timeout, creationflags=_flags())
    if result.returncode:
        raise ZxsBuildError(f'{exe.name} failed: {result.stderr.decode(errors="replace").strip()[-500:]}')
    return json.loads(result.stdout)


def differences(native: dict, reference: dict) -> dict:
    """The compared fields that differ (a field missing on either side differs)."""
    return {key: (native.get(key), reference.get(key)) for key in COMPARED
            if key not in native or key not in reference or native[key] != reference[key]}


def learn(work, rom: bytes, image: bytes, runs: list, emit=print, *, passes: int = 3) -> tuple:
    """Generate, build the native check and run it with learning on every route, at most `passes` times: it stops when nothing
    fell back or nothing new was seen. Returns the check program and the fallback steps of each pass (summed over the routes)."""
    rom_path = work / 'rom.bin'
    from . import z80_chain_build
    z80_chain_build.write_if_changed(rom_path, rom)
    patterns = work / 'native.patterns'
    counts = []
    check = None
    for _ in range(passes):
        generate(work, rom, emit)
        stage_sources(work)
        check = build(work, ('zxs_check', 'zxs_reference'), emit)['zxs_check']
        seen, steps = set(), 0
        for index, args in enumerate(runs):
            learned = work / f'learned-{index}.txt'
            learned.unlink(missing_ok=True)
            result = run(check, rom_path, image, [*args, '--learn', str(learned)])
            steps += result['fallback_steps']
            if learned.is_file():
                seen |= set(learned.read_text(encoding='utf-8').split())
        counts.append(steps)
        if not steps or not seen:
            break
        known = set(patterns.read_text(encoding='utf-8').split()) if patterns.is_file() else set()
        if seen <= known:
            break
        patterns.write_text(''.join(f'{line}\n' for line in sorted(known | seen)), encoding='utf-8', newline='\n')
    else:
        generate(work, rom, emit)
        check = build(work, ('zxs_check', 'zxs_reference'), emit)['zxs_check']
    return check, counts
