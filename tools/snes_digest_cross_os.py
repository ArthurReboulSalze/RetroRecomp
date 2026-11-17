"""Super Nintendo: the multiplayer digest of one game on two systems, frame by frame (Windows against Linux).

    python -B tools/snes_digest_cross_os.py trace ROM.sfc --frames 3000 --out TRACE.txt
    python -B tools/snes_digest_cross_os.py compare A.txt B.txt

`trace` converts the ROM with this source tree, builds the checks of the adapter in place of the game's main
(native/snes_cpu/machine_checks.c, mode `trace`) and keeps what it prints: for every frame of a scripted two-pad route, the digest
(rr16_snes_digest) and its seven partitions (cpu, wram, apu, ppu, ppu ports, dma, cartridge). Only hashes: no ROM byte and no
picture. Run it once on each system from the same commit, each with its own scratch library; `compare` says whether the two are
identical and, if not, the first frame and the partitions that differ.
"""
from pathlib import Path
import argparse
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
LINE = re.compile(r'^(\d+) ([0-9a-f]{16})((?: [0-9a-f]{16}){7})$')
PARTS = ('cpu', 'wram', 'apu', 'ppu', 'ppu-ports', 'dma', 'cartridge')


def trace(rom: Path, frames: int, out: Path) -> None:
    from retrorecomp.console16 import prepare16
    from retrorecomp.core import run, toolchain
    work = ROOT / '.build/snes-digest-cross-os'
    work.mkdir(parents=True, exist_ok=True)
    exe = prepare16(rom, 'snes', emit=lambda _: None)
    project = next(parent for parent in exe.parents if (parent / 'CMakeLists.txt').is_file())
    (project / 'console16_main.c').write_text((ROOT / 'native/snes_cpu/machine_checks.c').read_text(), encoding='utf-8')
    cmake, _ = toolchain()
    run([cmake, '--build', project / 'build', '--config', 'Release', '--parallel', '4'], log=work / (rom.stem + '-build.log'))
    text = run([exe, 'trace', str(frames)], cwd=work)
    lines = [line.strip() for line in text.splitlines() if LINE.match(line.strip())]
    if len(lines) != frames:
        raise SystemExit(f'{len(lines)} frames traced instead of {frames}')
    out.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'{rom.stem}: {frames} frames traced to {out}')


def compare(first: Path, second: Path) -> int:
    a = first.read_text(encoding='utf-8').replace('\r\n', '\n').split()
    b = second.read_text(encoding='utf-8').replace('\r\n', '\n').split()
    rows_a = [line for line in first.read_text(encoding='utf-8').replace('\r\n', '\n').splitlines() if line]
    rows_b = [line for line in second.read_text(encoding='utf-8').replace('\r\n', '\n').splitlines() if line]
    if len(rows_a) != len(rows_b):
        print(f'different lengths: {len(rows_a)} and {len(rows_b)} frames')
        return 1
    for row_a, row_b in zip(rows_a, rows_b):
        if row_a != row_b:
            fields_a, fields_b = row_a.split(), row_b.split()
            names = [PARTS[i] for i in range(7) if fields_a[2 + i] != fields_b[2 + i]]
            print(f'first difference at frame {fields_a[0]}: digest {fields_a[1]} / {fields_b[1]}; partitions that differ: {", ".join(names) or "none"}')
            return 1
    print(f'identical: {len(rows_a)} frames, every digest and partition equal')
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    t = sub.add_parser('trace')
    t.add_argument('rom', type=Path)
    t.add_argument('--frames', type=int, default=3000)
    t.add_argument('--out', type=Path, required=True)
    c = sub.add_parser('compare')
    c.add_argument('first', type=Path)
    c.add_argument('second', type=Path)
    args = parser.parse_args()
    if args.command == 'trace':
        trace(args.rom, args.frames, args.out)
        return 0
    return compare(args.first, args.second)


if __name__ == '__main__':
    sys.exit(main())
