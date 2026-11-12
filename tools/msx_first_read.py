"""MSX first read: the player's own cartridges on the reference machine (C-BIOS, reference Z80 interpreter), headless.

Nothing is converted. Each ROM is read in place from the player's library (a zip member is read into memory and passed
to the runner on its standard input: no copy of the ROM is written anywhere). For each game: the mapper guess, then
runs of the attract mode (pictures after 300, 600 and 1,200 frames) and one run that presses SPACE and joystick 1's
trigger A at frame 600 (picture after 1,200 frames). Written under .build/msx-first-read/<game>/: the pictures as PNG,
a report. Pictures of commercial games stay local: never commit or publish them.

    python -B tools/msx_first_read.py --library <the folder holding msx1/, msx2/> [--game "msx1/Road Fighter (Japan).zip"]...
"""
from __future__ import annotations

import argparse
import array
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import msx_reference  # noqa: E402
import msx_rom  # noqa: E402

PANEL = ('msx1/Road Fighter (Japan).zip', 'msx1/Knightmare - Majou Densetsu (Japan).zip',
         'msx1/Nemesis (Japan, Europe).zip', 'msx1/Salamander (Japan).zip')
OUT = ROOT / '.build' / 'msx-first-read'


def read_rom(path: Path) -> bytes:
    if path.suffix.lower() == '.zip':
        with zipfile.ZipFile(path) as bundle:
            names = [n for n in bundle.namelist() if n.lower().endswith(('.rom', '.mx1', '.mx2'))]
            if len(names) != 1:
                raise ValueError(f'{path.name}: {len(names)} cartridge members')
            return bundle.read(names[0])
    return path.read_bytes()


def run(exe: Path, image: bytes, *args: str) -> dict:
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    result = subprocess.run([str(exe), *args, '--cart', '-'], input=image, capture_output=True, timeout=600,
                            creationflags=flags)
    if result.returncode:
        raise SystemExit(f'reference run failed: {result.stderr.decode(errors="replace").strip()}')
    return json.loads(result.stdout)


def sound(path: Path) -> dict:
    samples = array.array('h')
    samples.frombytes(path.read_bytes())
    tail = samples[-44100 * 5:] or samples
    mean = sum(tail) / len(tail)
    rms = math.sqrt(sum((s - mean) ** 2 for s in tail) / len(tail))
    return {'seconds': round(len(samples) / 44100, 2), 'rms_last_5s': round(rms, 1), 'distinct_values': len(set(tail))}


def slug(name: str) -> str:
    return re.sub(r'[^A-Za-z0-9]+', '-', Path(name).stem).strip('-').lower()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--library', type=Path, required=True, help="the player's ROM folder, read in place")
    parser.add_argument('--game', action='append')
    args = parser.parse_args()
    roms = msx_reference.cbios()
    exe = msx_reference.build()
    bios = ['--main', str(roms / 'cbios_main_msx1.rom'), '--logo', str(roms / 'cbios_logo_msx1.rom')]
    summary = {}
    for name in args.game or PANEL:
        image = read_rom(args.library / name)
        guess = msx_rom.guess(image)
        folder = OUT / slug(name)
        folder.mkdir(parents=True, exist_ok=True)
        report = {'file': name, 'size': len(image), 'guess': guess.mapper, 'base': f'{guess.base:04X}',
                  'reason': guess.reason, 'candidates': list(guess.candidates), 'runs': {}}
        print(f'{name}: {len(image) // 1024} KB, guess {guess.mapper} ({guess.reason})', flush=True)
        plans = {f'attract-{n}': (n, []) for n in (300, 600, 1200)}
        plans['start-1200'] = (1200, ['--event', '600:key:8:0:1', '--event', '610:key:8:0:0',
                                      '--event', '660:joy:0:2F', '--event', '670:joy:0:3F'])
        for label, (frames, events) in plans.items():
            dump, audio = folder / f'{label}.bin', folder / f'{label}.raw'
            result = run(exe, image, *bios, *guess.arguments(), '--frames', str(frames), *events,
                         '--frame', str(dump), '--audio', str(audio))
            msx_reference.png(dump, folder / f'{label}.png')
            result['sound'] = sound(audio)
            dump.unlink()
            audio.unlink()
            report['runs'][label] = {k: result[k] for k in ('frames', 'interrupts', 'pc', 'pc_slot', 'halted', 'iff1',
                                                             'unmapped_reads', 'dropped_writes', 'vdp_regs',
                                                             'frame_fnv', 'audio_samples', 'sound')}
            r = report['runs'][label]
            print(f'  {label}: PC {r["pc"]:04X}h slot {r["pc_slot"]:02X}h, {r["interrupts"]} interrupts, '
                  f'R#0/R#1 {r["vdp_regs"][0]:02X}h/{r["vdp_regs"][1]:02X}h, picture {r["frame_fnv"]:08X}h, '
                  f'sound RMS {r["sound"]["rms_last_5s"]} ({r["sound"]["distinct_values"]} levels), '
                  f'unmapped reads {r["unmapped_reads"]}, dropped writes {r["dropped_writes"]}', flush=True)
        (folder / 'report.json').write_text(json.dumps(report, indent=1), encoding='utf-8')
        summary[name] = report
        del image
    (OUT / 'summary.json').write_text(json.dumps(summary, indent=1), encoding='utf-8')
    return 0


if __name__ == '__main__':
    sys.exit(main())
