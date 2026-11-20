"""Simulation identity of real conversions, with an authored Master System program; no commercial game.

Converts one small authored program several times through the ordinary conversion (`RetroRecomp.py convert`),
each time with a library of its own under .build/simulation-identity-selftest, and compares the
`simulation_identity` of the reports (retrorecomp/simulation_identity.py):

  a. the same inputs twice (another folder, another library): the same identity;
  b. another title and a cover instead of none: the same identity, while the export's request differs
     (its host part; the request's game part leaves the title and the cover out too, but holds the target
     system, the search settings and the knowledge stamp, and not the generated code);
  c. the PAL standard instead of NTSC (a run-changing option): another identity.

`--expect <identity>` compares conversion a with an identity computed elsewhere (the other system: Windows
against Linux). Nothing is shown: the conversions run headless. The result is printed as JSON and written to
.build/simulation-identity-selftest/result.json.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY))


def authored_program() -> bytes:
    """A 32 KiB Master System program written for this check: mode 4, display on, a frame interrupt that counts
    frames, and a main loop that waits for it and writes the count to two palette entries, so the picture
    changes at every frame; one tone on the sound chip."""
    data = bytearray(32768)
    data[:3] = bytes.fromhex('C3 00 01')                                       # JP 0100h
    # 0038h: acknowledge the frame interrupt, count it at C001h, EI, RETI.
    handler = bytes.fromhex('F5 DB BF 3A 01 C0 3C 32 01 C0 F1 FB ED 4D')
    data[0x38:0x38 + len(handler)] = handler
    init = bytes.fromhex('31 F0 DF ED 56'                                      # LD SP,DFF0h ; IM 1
                         '3E 04 D3 BF 3E 80 D3 BF'                             # register 0: mode 4
                         '3E 60 D3 BF 3E 81 D3 BF'                             # register 1: display on, frame interrupt
                         '3E FF D3 BF 3E 82 D3 BF'                             # register 2: name table
                         '3E FF D3 BF 3E 85 D3 BF'                             # register 5: sprite table
                         '3E 00 D3 BF 3E 87 D3 BF'                             # register 7: backdrop colour 0
                         '3E 8E D3 7F 3E 01 D3 7F 3E 90 D3 7F'                 # tone 0, full volume
                         'AF 32 01 C0 FB')                                     # count = 0 ; EI
    loop = bytes.fromhex('76 3A 01 C0 47'                                      # HALT ; B = count
                         '3E 00 D3 BF 3E C0 D3 BF 78 D3 BE'                    # palette entry 0 = count
                         '3E 10 D3 BF 3E C0 D3 BF 78 D3 BE')                   # palette entry 16 = count
    start = 0x100 + len(init)
    data[0x100:start] = init
    data[start:start + len(loop)] = loop
    data[start + len(loop):start + len(loop) + 3] = bytes([0xC3, start & 255, start >> 8])   # JP loop
    return bytes(data)


def authored_cover(path: Path) -> None:
    """A picture drawn here, to stand for a player's box art."""
    from PIL import Image, ImageDraw
    image = Image.new('RGB', (256, 352), (24, 60, 140))
    draw = ImageDraw.Draw(image)
    for step in range(8):
        draw.rectangle((16 + step * 12, 40 + step * 20, 240 - step * 12, 60 + step * 20), fill=(230, 200 - step * 20, 40 + step * 20))
    image.save(path)


def convert(work: Path, name: str, *, title: str, cover: Path | None = None, standard: str = 'auto',
            library: str | None = None) -> dict:
    """One conversion in a folder and a library of its own; returns what the comparison needs of its report."""
    folder = work / name
    shutil.rmtree(folder, ignore_errors=True)
    (folder / 'rom').mkdir(parents=True)
    rom = folder / 'rom' / 'authored-identity.sms'
    rom.write_bytes(authored_program())
    environment = dict(os.environ)
    environment.pop('RETRO_RECOMP_KEEP_BUILD', None)
    environment.update(RETRO_RECOMP_LIBRARY_DIR=str(work / (library or name) / 'library'),
                       SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy')
    if os.name == 'nt':
        environment.setdefault('RETRO_RECOMP_TOOLCHAIN', 'llvm')
    command = [sys.executable, '-B', str(REPOSITORY / 'RetroRecomp.py'), 'convert', str(rom), '--title', title,
               '--output', str(folder / 'games'), '--no-online-cover', '--no-compress', '--frames', '600', '--passes', '2',
               '--video-standard', standard, *(['--cover', str(cover)] if cover else ['--no-cover'])]
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    done = subprocess.run(command, cwd=REPOSITORY, env=environment, capture_output=True, text=True, encoding='utf-8',
                          errors='replace', creationflags=flags)
    (folder / 'conversion.log').write_text(done.stdout + done.stderr, encoding='utf-8')
    if done.returncode:
        raise SystemExit(f'{name}: the conversion failed; see {folder / "conversion.log"}\n' + done.stderr[-2000:])
    reports = sorted((folder / 'games').rglob('conversion-report.json'))
    if len(reports) != 1:
        raise SystemExit(f'{name}: expected one conversion report, found {len(reports)}')
    from retrorecomp.report_schema import read_report
    document = json.loads(reports[0].read_text(encoding='utf-8'))
    record = read_report(document)['simulation_identity']
    receipt = document.get('export_receipt') or {}
    return {'name': name, 'title': title, 'cover': bool(cover), 'standard': standard, 'record': record,
            'request': receipt.get('request'), 'request_game_part': receipt.get('game'),
            'request_host_part': receipt.get('host'), 'artwork_embedded': (document.get('artwork') or {}).get('embedded'),
            'target': document.get('target')}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--expect', help='The identity of conversion a computed on another system.')
    parser.add_argument('--only-first', action='store_true', help='Run conversion a only (with --expect).')
    args = parser.parse_args()
    from retrorecomp.paths import ROOT
    from retrorecomp.simulation_identity import same_simulation
    work = ROOT / '.build' / 'simulation-identity-selftest'
    work.mkdir(parents=True, exist_ok=True)
    cover = work / 'authored-cover.png'
    authored_cover(cover)
    first = convert(work, 'a', title='Authored Identity')
    runs, checks = [first], {}
    identity = (first['record'] or {}).get('identity')
    checks['a_has_identity'] = isinstance(identity, str) and len(identity) == 64
    if not args.only_first:
        again = convert(work, 'a2', title='Authored Identity')
        other = convert(work, 'b', title='Another Name For It', cover=cover)
        pal = convert(work, 'c', title='Authored Identity', standard='pal')
        runs += [again, other, pal]
        checks['a_same_inputs_same_identity'] = same_simulation(first['record'], again['record'])
        checks['b_cover_and_title_same_identity'] = same_simulation(first['record'], other['record'])
        # The cover really was embedded and the request really differs: the equality above is not an accident.
        checks['b_cover_embedded'] = other['artwork_embedded'] is True and not first['artwork_embedded']
        checks['b_request_differs'] = all(first[part] and other[part] and first[part] != other[part]
                                          for part in ('request', 'request_host_part'))
        checks['c_pal_other_identity'] = (isinstance((pal['record'] or {}).get('identity'), str)
                                          and not same_simulation(first['record'], pal['record']))
    if args.expect:
        checks['d_same_identity_as_expected'] = identity == args.expect
    result = {'commercial_rom_used': False, 'identity': identity, 'checks': checks, 'passed': all(checks.values()), 'runs': runs}
    (work / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
