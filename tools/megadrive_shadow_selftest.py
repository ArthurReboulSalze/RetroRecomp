"""Mega Drive shadow/highlight on the adapted VDP, against the chip's rules; an authored pattern, no ROM.

One sequence of VDP port writes draws a grid: sixteen columns cross plane A and plane B, each absent, transparent with
its priority bit, opaque low or opaque high; sixteen bands of sprites cross colours, colour 14 of palettes 0-2,
shadow and highlight operators of either priority, and operators stacked over or under another sprite. The expected
(colour, intensity) of every cell comes from `expected()`, written from MAME's 315-5313 and Genesis Plus GX (they
agree). The pinned VDP, adapted as a game builds it, renders the same writes three ways (batched SSE2, batched scalar,
unbatched scalar); all three must match the rules.

`--rom PATH` also writes the same sequence as a tiny authored 68000 program (no game code, no Sega data) so an
independent emulator can render it: `mame genesis -cart PATH`. It is a development aid, never kept in the repository.
"""
from pathlib import Path
import argparse
import json
import shutil
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BANDS = 16
COLUMNS = 16
NORMAL, SHADOW, HIGHLIGHT = 'normal', 'shadow', 'highlight'
COLOURS = {  # CRAM index: 9-bit BGR, (B, G, R) levels 0-7 doubled into the word
    0: (0, 0, 6), 2: (0, 6, 0), 17: (6, 0, 0), 35: (0, 6, 6),
    14: (6, 0, 6), 30: (6, 6, 0), 46: (6, 6, 6), 47: (2, 4, 6),
}
# Pattern tiles: plane tiles 1 (colour 1) and 2 (colour 2); sprite tiles in runs of four (sprites are 4 cells wide).
PLANE_TILES = {1: 1, 2: 2}
SPRITE_TILES = {3: 8, 14: 12, 15: 16}
A_CELLS = (0x0000, 0x8000, 0x2001, 0xA001)   # none, transparent high, opaque low (palette 1), opaque high
B_CELLS = (0x0000, 0x8000, 0x0002, 0x8002)   # same on plane B (palette 0)


def sprite(palette, colour, high):
    return {'palette': palette, 'colour': colour, 'high': high}


# Each band lists its sprites first to last (the first one drawn wins a pixel).
SPRITE_BANDS = [
    [],
    [sprite(2, 3, False)], [sprite(2, 3, True)],
    [sprite(0, 14, False)], [sprite(0, 14, True)], [sprite(1, 14, False)], [sprite(2, 14, False)],
    [sprite(2, 15, False)],
    [sprite(3, 15, False)], [sprite(3, 15, True)], [sprite(3, 14, False)], [sprite(3, 14, True)],
    [sprite(3, 15, False), sprite(2, 3, False)],
    [sprite(3, 14, True), sprite(2, 3, False)],
    [sprite(3, 14, False), sprite(2, 3, True)],
    [sprite(2, 3, False), sprite(3, 15, True)],
]


def vram_write(address):
    return [('ctrl', 0x4000 | (address & 0x3FFF)), ('ctrl', (address >> 14) & 3)]


def writes():
    """The authored VDP port writes, in order: ('ctrl'|'data', word) and ('clear', 0) for 64 KB of zero VRAM."""
    out = [('ctrl', 0x8000 | reg << 8 | value) for reg, value in (
        (0, 0x04), (1, 0x04), (2, 0x30), (3, 0x2C), (4, 0x07), (5, 0x78), (7, 0x00), (10, 0xFF), (11, 0x00),
        (12, 0x89), (13, 0x3F), (15, 0x02), (16, 0x01), (17, 0x00), (18, 0x00))]
    out += vram_write(0) + [('clear', 0)]
    out += [('ctrl', 0x4000), ('ctrl', 0x0010)] + [('data', 0)] * 40           # VSRAM
    out += [('ctrl', 0xC000), ('ctrl', 0x0000)]
    for index in range(64):
        b, g, r = COLOURS.get(index, (0, 0, 0))
        out.append(('data', b << 9 | g << 5 | r << 1))
    for colour, tile in [*PLANE_TILES.items(), *[(c, t + k) for c, t in SPRITE_TILES.items() for k in range(4)]]:
        out += vram_write(tile * 32) + [('data', colour * 0x1111)] * 16
    for base, cells in ((0xC000, A_CELLS), (0xE000, B_CELLS)):
        for row in range(BANDS):
            out += vram_write(base + row * 64 * 2)
            out += [('data', cells[col >> 2] if base == 0xC000 else cells[col & 3]) for col in range(COLUMNS)]
    table = []
    for band, stack in enumerate(SPRITE_BANDS):
        for spr in stack:
            for quarter in range(4):
                tile = SPRITE_TILES[spr['colour']]
                attr = (0x8000 if spr['high'] else 0) | spr['palette'] << 13 | tile
                table.append((band * 8 + 128, 0x0C, attr, quarter * 32 + 128))
    out += vram_write(0xF000)
    for n, (y, size, attr, x) in enumerate(table):
        link = n + 1 if n + 1 < len(table) else 0
        out += [('data', y), ('data', size << 8 | link), ('data', attr), ('data', x)]
    out.append(('ctrl', 0x8144))   # display on
    return out


def expected():
    """(CRAM index, intensity) of each [band][column] cell, by the rules MAME and Genesis Plus GX share."""
    grid = []
    for stack in SPRITE_BANDS:
        row = []
        for col in range(COLUMNS):
            a, b = col >> 2, col & 3
            a_op, a_pri, b_op, b_pri = a >= 2, a in (1, 3), b >= 2, b in (1, 3)
            plane_normal = a_pri or b_pri
            plane_high = (a_op and a_pri) or (b_op and b_pri)
            top = stack[0] if stack else None   # first sprite wins, operators included
            value = top and top['palette'] * 16 + top['colour']
            operator = value in (0x3E, 0x3F)
            if top and not operator and (top['high'] or not plane_high):
                normal = top['high'] or plane_normal or value in (0x0E, 0x1E, 0x2E)
                row.append([value, NORMAL if normal else SHADOW])
                continue
            if a_op and a_pri:
                index = 17
            elif b_op and b_pri:
                index = 2
            elif a_op:
                index = 17
            elif b_op:
                index = 2
            else:
                index = 0
            level = NORMAL if plane_normal else SHADOW
            if operator and (top['high'] or not plane_high):
                level = SHADOW if value == 0x3F else (HIGHLIGHT if level == NORMAL else NORMAL)
            row.append([index, level])
        grid.append(row)
    return grid


def rom():
    """The same writes as a small authored 68000 program: vectors, a header, the writes, then a loop."""
    code = bytearray(struct.pack('>HH', 0x46FC, 0x2700))                  # move #$2700,sr
    code += struct.pack('>HI', 0x41F9, 0xC00004) + struct.pack('>HI', 0x43F9, 0xC00000)  # lea ctrl,a0 / data,a1
    for kind, word in writes():
        if kind == 'ctrl':
            code += struct.pack('>HH', 0x30BC, word)                       # move.w #w,(a0)
        elif kind == 'data':
            code += struct.pack('>HH', 0x32BC, word)                       # move.w #w,(a1)
        else:
            code += struct.pack('>HHH', 0x7000, 0x323C, 0x3FFF)           # moveq #0,d0 / move.w #$3fff,d1
            code += struct.pack('>HHH', 0x2280, 0x51C9, 0xFFFC)           # move.l d0,(a1) / dbra d1,*-2
    code += struct.pack('>H', 0x60FE)                                      # bra.s *
    image = bytearray(0x200)
    image[0:8] = struct.pack('>II', 0x00FFFE00, 0x200)
    for vector in range(2, 64):
        image[vector * 4:vector * 4 + 4] = struct.pack('>I', 0x200)
    header = b'SEGA MEGA DRIVE (C)RR   2026.NOVRETRO-RECOMP SHADOW PATTERN'
    image[0x100:0x100 + len(header)] = header
    image[0x1F0:0x1F3] = b'JUE'
    image += code
    image += bytes(-len(image) % 0x2000)
    image[0x1A0:0x1A8] = struct.pack('>II', 0, len(image) - 1)
    return bytes(image)


def pattern_header():
    words = [(2 if kind == 'clear' else 1 if kind == 'data' else 0) << 16 | word for kind, word in writes()]
    body = ',\n'.join(', '.join(f'0x{w:05x}u' for w in words[i:i + 12]) for i in range(0, len(words), 12))
    return f'/* Generated by tools/megadrive_shadow_selftest.py. */\nstatic const uint32_t rr_shadow_writes[] = {{\n{body}\n}};\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--rom', type=Path, help='also write the authored program for an independent emulator')
    args = parser.parse_args()
    if args.rom:
        args.rom.write_bytes(rom())
    from retrorecomp.core import run, toolchain
    from retrorecomp.platforms import build_executable, cmake_target_args
    from retrorecomp.megadrive_runtime import timing_vdp
    project = ROOT / '.build/megadrive-shadow-selftest'
    project.mkdir(parents=True, exist_ok=True)
    engine = ROOT / '.deps/segagenesisrecomp/runner'
    (project / 'retro_md_game.h').write_text('/* Authored fixture. */\n', encoding='utf-8')
    (project / 'md_shadow_pattern.h').write_text(pattern_header(), encoding='utf-8')
    for name in ('md_timing.h', 'md_vdp_pixels.inc'):
        shutil.copy2(ROOT / 'native' / name, project / name)
    (project / 'vdp.c').write_text(timing_vdp((engine / 'video/genesis_vdp.c').read_text(encoding='utf-8')),
                                   encoding='utf-8')
    variants = {'batched': 'GENESIS_BATCHED_PLANES=1', 'batched_scalar': 'GENESIS_BATCHED_PLANES=1 RR_MD_REFERENCE_PIXELS=1',
                'scalar': 'GENESIS_BATCHED_PLANES=0'}
    lines = ['cmake_minimum_required(VERSION 3.20)', 'project(RetroMdShadowChecks C)', 'set(CMAKE_C_STANDARD 11)',
             'set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")']
    for name, defines in variants.items():
        lines += [f'add_executable({name} "{(ROOT / "native/md_shadow_checks.c").as_posix()}" vdp.c)',
                  f'target_compile_definitions({name} PRIVATE {defines})',
                  f'target_include_directories({name} PRIVATE . "{engine.as_posix()}" "{engine.as_posix()}/video" '
                  f'"{engine.as_posix()}/include")']
    (project / 'CMakeLists.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    cmake, generator = toolchain()
    log = project / 'build.log'
    run([cmake, '-S', project, '-B', project / 'build', '-G', generator, *cmake_target_args()], log=log)
    run([cmake, '--build', project / 'build', '--config', 'Release', '--parallel', '3'], log=log)
    want = expected()
    results = {'cells': BANDS * COLUMNS}
    for name in variants:
        got = json.loads(run([build_executable(project / 'build', name)], timeout=60))
        if not got['uniform']:
            raise AssertionError(f'{name}: a cell is not one colour')
        wrong = [(band, col, got['grid'][band][col], want[band][col])
                 for band in range(BANDS) for col in range(COLUMNS) if got['grid'][band][col] != want[band][col]]
        if wrong:
            raise AssertionError(f'{name}: {len(wrong)} cells differ from the chip, first {wrong[:6]}')
        results[name] = {'matching': BANDS * COLUMNS, 'sprite_collision': got['collision']}
    (project / 'result.json').write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(results))


if __name__ == '__main__':
    main()
