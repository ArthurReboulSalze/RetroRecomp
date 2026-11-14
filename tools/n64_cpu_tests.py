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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--tests', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--only', nargs='*', default=[])
    parser.add_argument('--frames', type=int, default=600)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    roms = sorted(p for p in args.tests.rglob('*') if p.suffix.lower() == '.n64')
    if args.only:
        roms = [p for p in roms if any(p.parent.relative_to(args.tests).as_posix().startswith(o) for o in args.only)]
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
