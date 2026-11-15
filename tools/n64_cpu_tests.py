"""Independent CPU evidence for the Nintendo 64 (gate G10): krom's CPU test programs (PeterLemon/N64, public domain), each converted
like a game, its native blocks checked against the core's interpreter by the conversion itself, and each test's own verdict read on
the delivered program's last picture.

    python tools/n64_cpu_tests.py --tests <PeterLemon/N64 checkout>/CPUTest --output .build/g10 [--only CPU/ADD ...] [--frames 600]

Every `.N64` under --tests is converted at the Quick level (main route, --frames frames, no input needed: the tests run by themselves)
into a scratch library of its own under --output. A conversion that succeeds has replayed its compressed program against a fresh run
on the core's pure interpreter, frame by frame (picture, sound, RDRAM, CPU registers): that is the native-equals-interpreter check.
The test's verdict is read on the compressed program's last picture: krom's programs write PASS in green and FAIL in red in their
"Test Result" column, so a test passes when that column holds green and no red. The counts are written to --output/summary.json, one
row per program: converted, native share, guard misses, green and red pixels, verdict. Only counts are printed, never the programs'
bytes; krom's programs carry a boot code of unverified provenance and are never copied into the repository.
Exit status 0 when every program converted; the verdicts are evidence, not a gate (a failing test is named, with its reason, in
docs/QUALIFICATION.md).
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_ppm(path: Path):
    data = path.read_bytes()
    parts = data.split(b'\n', 3)
    w, h = map(int, parts[1].split())
    return w, h, parts[3]


def verdict(path: Path) -> dict:
    """Green and red pixels of the "Test Result" column (the right eighth of the picture, below the header line)."""
    w, h, pix = read_ppm(path)
    green = red = 0
    for y in range(h * 12 // 240, h):
        for x in range(w * 520 // 640, w * 610 // 640):
            r, g, b = pix[(y * w + x) * 3:(y * w + x) * 3 + 3]
            if g >= 100 and r < 60 and b < 60:
                green += 1
            elif r >= 100 and g < 60 and b < 60:
                red += 1
    return {'green': green, 'red': red, 'pass': green > 0 and red == 0}


def read_png(path: Path):
    """(width, height, rows of RGB bytes) of an 8-bit PNG (greyscale, RGB, palette or RGBA), with the five row filters (stdlib only)."""
    import struct
    import zlib
    data = path.read_bytes()
    pos, chunks, palette = 8, b'', None
    while pos < len(data):
        length, kind = struct.unpack('>I4s', data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        if kind == b'IHDR':
            w, h, depth, ctype = struct.unpack('>IIBB', body[:10])
        elif kind == b'PLTE':
            palette = body
        elif kind == b'IDAT':
            chunks += body
        pos += 12 + length
    if depth != 8:
        raise ValueError('only 8-bit PNG')
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    raw, stride, rows, prev = zlib.decompress(chunks), w * channels, [], bytearray(w * channels)
    for y in range(h):
        f, line = raw[y * (stride + 1)], bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - channels] if i >= channels else 0
            b, c = prev[i], prev[i - channels] if i >= channels else 0
            if f == 1:
                line[i] = (line[i] + a) & 255
            elif f == 2:
                line[i] = (line[i] + b) & 255
            elif f == 3:
                line[i] = (line[i] + (a + b) // 2) & 255
            elif f == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        prev = line
        rgb = bytearray()
        for x in range(w):
            px = line[x * channels:(x + 1) * channels]
            if ctype == 3:
                rgb += palette[px[0] * 3:px[0] * 3 + 3]
            elif channels <= 2:
                rgb += bytes((px[0],) * 3)
            else:
                rgb += px[:3]
        rows.append(bytes(rgb))
    return w, h, rows


def cell_colours(get, width: int, height: int, cw: int, ch: int) -> list[str]:
    """The dominant colour of each cw x ch cell: 'r'ed, 'g'reen, 'w'hite or '.' (dark), from get(x, y) -> (r, g, b)."""
    cells = []
    for cy in range(0, height - ch + 1, ch):
        for cx in range(0, width - cw + 1, cw):
            counts = {'r': 0, 'g': 0, 'w': 0}
            for y in range(cy, cy + ch):
                for x in range(cx, cx + cw):
                    r, g, b = get(x, y)
                    if r > 150 and g > 150 and b > 150:
                        counts['w'] += 1
                    elif r >= 100 and g < 80 and b < 80:
                        counts['r'] += 1
                    elif g >= 100 and r < 80 and b < 80:
                        counts['g'] += 1
            best = max(counts, key=counts.get)
            cells.append(best if counts[best] >= 3 else '.')
    return cells


def matches_reference(picture: Path, reference: Path) -> dict:
    """The test's picture against krom's reference picture, cell by cell (8 x 8 there, 8 x 4 in ours: one field of 240 lines)."""
    w, h, pix = read_ppm(picture)
    rw, rh, rows = read_png(reference)
    scale = rh // h if h and rh % h == 0 else 1
    ours = cell_colours(lambda x, y: tuple(pix[(y * w + x) * 3:(y * w + x) * 3 + 3]), min(w, rw), h, 8, 8 // scale)
    theirs = cell_colours(lambda x, y: tuple(rows[y][x * 3:x * 3 + 3]), min(w, rw), rh, 8, 8)
    # The two pictures are not framed alike (offsets, scaling), so their cells are compared as proportions, not one by one: the share of
    # red among the coloured cells (a FAIL more, or a PASS less, moves it; a matrix of results equal to the reference keeps it).
    def red_share(cells):
        red, green = cells.count('r'), cells.count('g')
        return red / (red + green) if red + green else None
    o, t = red_share(ours), red_share(theirs)
    return {'red_share': None if o is None else round(o, 3), 'reference_red_share': None if t is None else round(t, 3),
            'matches_reference': o is not None and t is not None and abs(o - t) <= 0.02}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--tests', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--only', nargs='*', default=[])
    parser.add_argument('--frames', type=int, default=600)
    parser.add_argument('--reference', type=Path, help='the generic reference player: every program runs on the core\'s pure interpreter '
                        '(no conversion), its verdict read on its picture after --frames frames')
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    roms = sorted(p for p in args.tests.rglob('*') if p.suffix.lower() == '.n64')
    if args.only:
        roms = [p for p in roms if any(p.parent.relative_to(args.tests).as_posix().startswith(o) for o in args.only)]
    if args.reference:
        # The core's interpreter against each test's own expectations: what G10 asks of the CPU the native blocks reproduce.
        none = out / 'no-input.txt'
        none.write_text('', encoding='ascii')
        verdicts = {}
        for rom in roms:
            name = rom.parent.relative_to(args.tests).as_posix() + ('/' + rom.stem if len([r for r in roms if r.parent == rom.parent]) > 1 else '')
            picture = out / (name.replace('/', '_') + '.ppm')
            run = subprocess.run([str(args.reference), '--headless', '--rom', str(rom), '--frames', str(args.frames), '--input-events', str(none),
                                  '--capture', str(picture)], capture_output=True, timeout=300)
            verdicts[name] = {'exit': run.returncode, **(verdict(picture) if picture.is_file() else {'pass': None})}
            reference = rom.with_suffix('.png')
            if picture.is_file() and reference.is_file():
                verdicts[name].update(matches_reference(picture, reference))
        (out / 'interpreter.json').write_text(json.dumps(verdicts, indent=1, sort_keys=True), encoding='utf-8')
        print(f'{len(verdicts)} programs on the interpreter, {sum(1 for v in verdicts.values() if v.get("pass"))} pass, '
              f'failing: {sorted(k for k, v in verdicts.items() if not v.get("pass"))}')
        return 0
    summary_path = out / 'summary.json'
    summary = json.loads(summary_path.read_text(encoding='utf-8')) if summary_path.is_file() else {}
    converted_all = True
    for rom in roms:
        name = rom.parent.relative_to(args.tests).as_posix()
        folder = out / name.replace('/', '_')
        env = dict(os.environ, RETRO_RECOMP_LIBRARY_DIR=str(folder / 'library'), RETRO_RECOMP_TOOLCHAIN=os.environ.get('RETRO_RECOMP_TOOLCHAIN', 'llvm'))
        (folder / 'games').mkdir(parents=True, exist_ok=True)
        with (folder / 'convert.log').open('wb') as log:
            code = subprocess.run([sys.executable, '-B', str(ROOT / 'RetroRecomp.py'), 'batch', '--system', 'n64', '--scan-level', 'quick',
                                   '--frames', str(args.frames), '--no-cover', '--no-online-cover', '--keep-build', '--output',
                                   str(folder / 'games'), str(rom)], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT).returncode
        row = {'converted': False, 'exit': code}
        reports = list(folder.glob('games/*/datas/reports/*/conversion-report.json'))
        if code == 0 and reports:
            report = json.loads(reports[0].read_text(encoding='utf-8'))
            check = report['final_checks'][0]
            picture = Path(report['qualification_directory']) / 'packed' / 'main' / 'frame.ppm'
            row = {'converted': True, 'native_percent': round(100 - check['interpreter_percent'], 2), 'guard_misses': check['guard_misses'],
                   'interpreted_classes': check.get('interpreted_classes'), 'packed_reference_match': check.get('packed_reference_match'),
                   **(verdict(picture) if picture.is_file() else {'pass': None})}
        converted_all &= row['converted']
        summary[name] = row
        summary_path.write_text(json.dumps(summary, indent=1, sort_keys=True), encoding='utf-8')
    passed = sum(1 for r in summary.values() if r.get('pass'))
    print(f'{len(summary)} programs, {sum(1 for r in summary.values() if r["converted"])} converted, {passed} pass, '
          f'failing: {sorted(k for k, r in summary.items() if r.get("pass") is False)}')
    return 0 if converted_all else 1


if __name__ == '__main__':
    sys.exit(main())
