"""Prepare the owner's X68000 play test (gate G14): five games converted as a player would, with a checklist.

    python tools/x68000_owner_trial.py --roms DISKFOLDER --ipl IPLROM.DAT --cgrom CGROM.DAT [--out DIR] [--games KEY ...]

Converts the chosen games one at a time with the converter of this checkout (a player's options: the packed copy, online covers,
the standard scan level) into a folder under a `.build` directory (never the maintainer's Export), each conversion in its own
process with a private library so the maintainer's settings and library are not touched, and writes `TRIAL.md` there: for each
game, where its executable is, what it is there to show, and what to try. The verdict and the notes are the owner's: nothing here
says a game is good, only that it was converted, replayed against its reference and delivered. The disks, the IPL and the font ROM
are read in place; they are embedded in the delivered executables, which therefore stay on the owner's machine.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0

# key: (file name start of the first disk, what the game is there to show, what to try)
GAMES = {
    'rtype': ('R-Type (Irem)', 'One disk, 15 kHz: the control game of every release check',
              'Starts without an error window; the shooter plays (arrows, W and X, Enter for Start); music and effects are the '
              "game's; F8 in play, move on, F9 goes back."),
    'metalsight': ('Metal Sight (System Sacom) (Disk 1)', 'Five disks (the largest set), 31 kHz, automatic disk changes',
                   'The five disks join as one game; the disk changes by itself at each "insert disk" request, with no key from '
                   'you, until play; F5 loads faster.'),
    'lemmings': ('Lemmings (Imagineer)', 'A mouse game that drives the mouse chip itself',
                 'The mouse is captured at launch (Ctrl+Alt+M releases it); click "1 PLAYER", then play level 1 with the mouse; '
                 'the keyboard or a gamepad also moves the pointer.'),
    'superhangon': ('Super Hang-On (1989)(Sharp - SPS)(Disk 1 of 2)', 'Two disks ejected after loading, a long load, 31 kHz',
                    'The title counts down from 99 while the game loads (about two minutes of play time; F5 loads faster); '
                    'nothing answers before it reaches 0; then Enter starts the race.'),
    'bubblebobble': ('Bubble Bobble (Dempa)', 'An arcade port whose colours were corrected in 1.6.7 (the palette intensity bit)',
                     'The colours look right (no green cast on the dark parts); two players share the keyboard and a gamepad; '
                     'F8/F9 mid-level.'),
}

CHECKLIST = """
For every game: it starts without an error window; the keys or the gamepad answer (arrows, W and X, Enter for Start; F1 shows the
help); the sound is the game's; F8 then F9 restores the picture and the sound, also after closing the game and starting it again;
F3 changes the filter, F4 the window mode. The X68000 gets its disks, IPL and font ROM from its own executable: nothing to choose.
"""


def find(folder: Path, start: str) -> Path | None:
    matches = sorted(path for path in folder.iterdir() if path.suffix.lower() == '.dim' and path.name.startswith(start))
    return matches[0] if matches else None


def summary(work: Path) -> str:
    """What the conversion's own report says, in one line: counted interpreter use, the compressed copy, the saved state."""
    reports = sorted(work.glob('Sharp X68000/datas/reports/*/conversion-report.json'))
    if not reports:
        return 'no report found'
    report = json.loads(reports[-1].read_text(encoding='utf-8'))
    checks = report.get('final_checks', [])
    interpreted = sum(check.get('interpreted_opcodes', 0) for check in checks)
    packing = report.get('packing', {})
    packed = 'compressed' if packing.get('packed') else f'delivered unpacked ({packing.get("unpacked_reason", "no reason given")})'
    state = report.get('game_states', {}).get('validation', {})
    return (f'{interpreted} interpreted opcodes on {len(checks)} routes; {packed}, replayed '
            f'{"identically" if report.get("native_validation", {}).get("packed_reference_match") else "NOT identically"}; '
            f'state resumed in a fresh process: {"yes" if state.get("continuation_matches") else "no"}')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--roms', type=Path, help='folder with the X68000 disks (DIM files)')
    parser.add_argument('--ipl', type=Path, help='your IPL ROM (128 KiB)')
    parser.add_argument('--cgrom', type=Path, help='your font ROM (768 KiB)')
    parser.add_argument('--index-only', action='store_true', help='convert nothing: rewrite TRIAL.md from the games already delivered')
    parser.add_argument('--out', type=Path, default=ROOT / '.build' / 'x68-owner-trial')
    parser.add_argument('--games', nargs='*', choices=sorted(GAMES), help='keys (default: all five)')
    args = parser.parse_args()
    if not args.index_only and not (args.roms and args.roms.is_dir() and args.ipl and args.cgrom):
        raise SystemExit('give --roms (a folder of X68000 disks), --ipl and --cgrom')
    out = args.out.resolve()
    if '.build' not in (part.lower() for part in out.parts):
        raise SystemExit('the trial goes under a .build folder, never into an export folder')
    out.mkdir(parents=True, exist_ok=True)
    lines = ['# X68000 play test: games ready for the owner', '',
             f'Prepared {time.strftime("%Y-%m-%d %H:%M")} by `tools/x68000_owner_trial.py` from this checkout. The games are in',
             f'`{out}`. They are converted with the options of a player (the packed copy, online covers, the standard scan level). '
             'The verdict and the notes are yours.', '',
             'The conversion has already replayed each game on its main, mouse and keyboard routes against a fresh reference and '
             'replayed the packed copy; that says the native code, the picture and the sound of those routes agree, nothing of '
             'complete gameplay, exact hardware or latency.', CHECKLIST, '',
             '| Game | Executable | Conversion report | Why it is here | What to try | Verdict |', '|---|---|---|---|---|---|']
    for key in args.games or GAMES:
        start, why, what = GAMES[key]
        if args.index_only:
            reports = sorted((out / 'work' / key).glob('Sharp X68000/datas/reports/*/conversion-report.json'))
            name = json.loads(reports[-1].read_text(encoding='utf-8')).get('executable') if reports else None
            exe = out / 'Games' / 'Sharp X68000' / name if name else None
            if exe is not None and exe.is_file():
                lines.append(f'| {key} | `{exe.relative_to(out)}` | {summary(out / "work" / key)} | {why} | {what} | |')
            continue
        disk = find(args.roms, start)
        if disk is None:
            print(f'{key}: no disk starting with {start!r} in {args.roms}', flush=True)
            continue
        library = out / 'library' / key
        library.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env.update(SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy', PYINSTALLER_SUPPRESS_SPLASH_SCREEN='1',
                   PYTHONIOENCODING='utf-8', PYTHONDONTWRITEBYTECODE='1', RETRO_RECOMP_LIBRARY_DIR=str(library))
        env.pop('SMSRECOMP_LIBRARY_DIR', None)
        work = out / 'work' / key        # one folder per conversion: two instances of this tool can run side by side
        shutil.rmtree(work, ignore_errors=True)
        command = [sys.executable, '-B', 'RetroRecomp.py', 'batch', str(disk), '--system', 'x68', '--x68-ipl', str(args.ipl),
                   '--x68-cgrom', str(args.cgrom), '--jobs', '1', '--output', str(work), '--compress', '--scan-level', 'standard']
        print(f'{key}: converting {disk.name} ...', flush=True)
        started = time.time()
        with (out / f'{key}.log').open('wb') as log:
            done = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, creationflags=NO_WINDOW)
        executables = sorted((work / 'Sharp X68000').glob('*.exe'))
        if done.returncode or not executables:
            print(f'{key}: the conversion failed ({done.returncode}); see {out / (key + ".log")}', flush=True)
            lines.append(f'| {key} | (the conversion failed: see `{key}.log`) | | {why} | | |')
            continue
        delivered = out / 'Games' / 'Sharp X68000'
        delivered.mkdir(parents=True, exist_ok=True)
        exe = delivered / executables[0].name
        exe.unlink(missing_ok=True)
        shutil.move(str(executables[0]), exe)
        print(f'{key}: ready, {exe.name} ({time.time() - started:.0f} s)', flush=True)
        lines.append(f'| {key} | `{exe.relative_to(out)}` | {summary(work)} | {why} | {what} | |')
    (out / 'TRIAL.md').write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
    print(f'checklist: {out / "TRIAL.md"}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
