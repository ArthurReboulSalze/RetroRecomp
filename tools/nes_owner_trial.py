"""Prepare the owner's NES play test (gate G14): six games converted as a player would, with a checklist.

    python tools/nes_owner_trial.py --roms ROMFOLDER [--out DIR] [--games KEY ...]

Converts the chosen games one at a time with the converter of this checkout (a player's options: online covers and the
shared base on), into `.build/nes-owner-trial/` (never into the maintainer's Export), takes the last picture of the right-hand
play route of each, and writes `TRIAL.md` there: for each game, where its executable is, what it is there to show, and what to
try. The verdict and the notes are the owner's: nothing here says a game is good, only that it was converted and started.
The ROMs are read in place and never copied outside the converter's own workspace.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0

# key: (file name start, what the game is there to show, what to try)
GAMES = {
    'zelda': ('Legend of Zelda, The', 'MMC1 with a battery save and a very long game',
              'Start a game, save in the game, quit and start again: the save is there. F8 in a room, play on, F9: you are back. '
              'F8, close the game, start it again, F9.'),
    'kirby': ("Kirby's Adventure", 'MMC3 (scanline IRQ), a battery save, and the most common board',
              'Scrolling and the status bar at the bottom stay steady; save in the game and reload it; F3 cycles the picture filters.'),
    'gimmick': ('Mr. Gimmick', 'A PAL cartridge (50 Hz), FME-7 and its extra sound chip',
                'Music and effects sound right and the speed feels like a PAL game, not a 60 Hz one; the title and a first stage '
                'play; F8/F9 mid-stage.'),
    'duckhunt': ('Duck Hunt', 'The Zapper: the mouse aims, the left button shoots, the right button shoots off-screen',
                 'Aim and shoot at the ducks; the hit and miss answer as on the screen; F2, then the Zapper page, changes the '
                 'reticle (cross or dot, size, colour).'),
    'battletoads': ('Battletoads (USA)', 'Two players, AxROM, code that runs from RAM',
                    'Both pads work (the second player on the keypad or a second gamepad); play a stage with a friend; F6 '
                    'turns on autofire on a gamepad.'),
    'castlevania3': ("Castlevania III", 'MMC5 with its extra sound channels and mapped RAM',
                     'The first stage plays and sounds right (the extra pulse channels are heard in the music); F8/F9 on a stairway.'),
}

CHECKLIST = """
For every game: it starts without an error window; the keys or the gamepad answer (arrows, W and X, Enter for Start, Shift for
Select; F1 shows the help); the sound is the game's; F8 then F9 restores the picture and the sound, also after closing the game and
starting it again; F3 changes the filter, F4 the window mode; F5 toggles the extra sprites (fewer flickering objects), F7 changes
the language of the game's own menus.
"""


def find(folder: Path, start: str) -> Path | None:
    matches = sorted(path for path in folder.iterdir() if path.suffix.lower() in ('.zip', '.nes') and path.name.startswith(start))
    return matches[0] if matches else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--roms', type=Path, default=os.environ.get('RETRO_RECOMP_ROMS') and Path(os.environ['RETRO_RECOMP_ROMS']) / 'nes',
                        help='folder with the NES ROMs (default: $RETRO_RECOMP_ROMS/nes)')
    parser.add_argument('--out', type=Path, default=ROOT / '.build' / 'nes-owner-trial')
    parser.add_argument('--games', nargs='*', choices=sorted(GAMES), help='keys (default: all six)')
    args = parser.parse_args()
    if not args.roms or not args.roms.is_dir():
        raise SystemExit('give --roms (a folder of NES ROMs) or set RETRO_RECOMP_ROMS')
    out = args.out.resolve()
    if ROOT / '.build' not in out.parents and out != ROOT / '.build':
        raise SystemExit('the trial goes under .build, never into an export folder')
    out.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy', PYINSTALLER_SUPPRESS_SPLASH_SCREEN='1')
    lines = ['# NES play test: games ready for the owner', '',
             f'Prepared {time.strftime("%Y-%m-%d %H:%M")} by `tools/nes_owner_trial.py` from this checkout. The games are in',
             f'`{out}`. They are converted with the options of a player (the packed copy, the shared base, online covers). The verdict and the notes are yours.', '',
             'The pictures in `captures/<game>/play_right_03599.png` are where a scripted run of 3,600 frames ended: a game may still be on '
             'its title or an introduction there. They only say that the game starts and draws.', CHECKLIST, '',
             '| Game | Executable | Why it is here | What to try | Verdict |', '|---|---|---|---|---|']
    for key in args.games or GAMES:
        start, why, what = GAMES[key]
        rom = find(args.roms, start)
        if rom is None:
            print(f'{key}: no ROM starting with {start!r} in {args.roms}', flush=True)
            continue
        game_out = out / 'Games'
        command = [sys.executable, '-B', 'RetroRecomp.py', 'batch', str(rom), '--system', 'nes', '--jobs', '1', '--output', str(game_out)]
        before = set((game_out / 'Nintendo NES').glob('*.exe'))
        print(f'{key}: converting {rom.name} ...', flush=True)
        with (out / f'{key}.log').open('wb') as log:
            done = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, creationflags=NO_WINDOW)
        executables = sorted(path for path in (game_out / 'Nintendo NES').glob('*.exe') if path not in before)
        if done.returncode or not executables:
            print(f'{key}: the conversion failed ({done.returncode}); see {out / (key + ".log")}', flush=True)
            lines.append(f'| {key} | (the conversion failed: see `{key}.log`) | {why} | | |')
            continue
        exe = executables[0]
        captures = out / 'captures' / key
        # The player keeps its battery file and settings beside the executable: the pictures come from a private copy, so the
        # delivered game starts for the owner with no save and no preference.
        with tempfile.TemporaryDirectory(dir=out) as scratch:
            private = Path(scratch) / exe.name
            shutil.copy2(exe, private)
            subprocess.run([sys.executable, '-B', str(ROOT / 'tools' / 'nes_route_captures.py'), str(rom), str(private), '--level',
                            'standard', '--out', str(captures), '--routes', 'play_right'], cwd=ROOT, env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=NO_WINDOW)
        lines.append(f'| {key} | `{exe.relative_to(out)}` | {why} | {what} | |')
        print(f'{key}: ready, {exe.name}', flush=True)
    (out / 'TRIAL.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'checklist: {out / "TRIAL.md"}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
