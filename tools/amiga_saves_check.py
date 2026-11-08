"""Show, on a real Amiga game, what happens to a file the game saves: written, read back, kept at relaunch and across a reconversion.

    python tools/amiga_saves_check.py <install.lha> --output .build/saves-<name> [--frames 6000] [--kickstart FOLDER]

Evidence for gate G7 (saves) of docs/QUALIFICATION.md; a developer tool, never part of a conversion. The game must write a file on the
standard exploration route by itself (5th Gear saves its high scores); nothing is forced. The steps, all in --output (the conversion library
too: RETRO_RECOMP_LIBRARY_DIR is set below it, a different one for each conversion):

  1. convert the game, copy its player to a play folder and run it headless with the exploration route: a file must appear under
     datas/games/amiga-<identity>/saves;
  2. run the same player again for a moment, and once more with the file moved aside: the machine's RAM must differ between the two, so the
     game really read the kept file, and the file must be the one the first run left;
  3. a quick state saved before the game wrote the file, loaded by a fresh process: the kept file is not rolled back;
  4. damaged saves: cut to half, empty, a folder in its place: the game must still start and run (the file stays the player's);
  5. convert a second time (a new library, a new build folder), put that player in the same play folder and run it: the file must still be
     the one the first run left, in the same single data folder.

Only sizes, names and digests are printed, never the game's bytes. The folder holds executables with the game embedded: delete it after use.
Exit status 0 only when every check holds.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def run_player(player, frames, *extra, allow_stop=False):
    command = [str(player), '--headless', '--frames', str(frames), *map(str, extra)]
    done = subprocess.run(command, cwd=player.parent, capture_output=True, timeout=1800,
                          env=dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy'),
                          creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if done.returncode and not allow_stop:
        raise SystemExit(f'The player stopped with status {done.returncode}: {done.stderr.decode(errors="replace")[-400:]}')
    return done.returncode


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ram_column(trace):
    lines = Path(trace).read_text(encoding='ascii').splitlines()
    index = lines[0].split('\t').index('ram')
    return [line.split('\t')[index] for line in lines[1:]]


def saved_files(folder):
    return sorted(p for p in folder.rglob('*') if p.is_file()) if folder.is_dir() else []


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('lha', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--frames', type=int, default=6000)
    parser.add_argument('--kickstart', default=None)
    options = parser.parse_args(argv)
    from retrorecomp import amiga_whdload
    from retrorecomp.amiga_conversion import convert, explore_route, write_events
    output = options.output.resolve()
    shutil.rmtree(output, ignore_errors=True)
    output.mkdir(parents=True)
    key_exit = amiga_whdload.install(options.lha.read_bytes()).slave.key_exit
    events = write_events(output / 'inputs.txt', explore_route(options.frames, key_exit))
    play = output / 'play'
    play.mkdir()
    name = 'Game.exe' if os.name == 'nt' else 'Game'

    def build(number):
        os.environ['RETRO_RECOMP_LIBRARY_DIR'] = str(output / f'library-{number}')
        made = convert(options.lha, output=output / f'out-{number}', scan_level='quick', use_cover=False, online_cover=False,
                       emit=lambda message: None, amiga_kickstart=options.kickstart)
        target = play / name
        shutil.copy2(made, target)
        if os.name != 'nt':
            target.chmod(0o755)
        return target, sha(made)

    result = {'game': options.lha.stem, 'frames': options.frames}
    player, first_build = build(1)
    run_player(player, options.frames, '--input-events', events)
    folders = sorted((play / 'datas/games').iterdir())
    saves = folders[0] / 'saves'
    files = saved_files(saves)
    result['files_written'] = [{'name': p.name, 'bytes': p.stat().st_size} for p in files]
    if not files:
        print(json.dumps(result, indent=1))
        raise SystemExit('The game wrote no file on this route: choose a game that saves by itself.')
    kept = files[0]
    written = sha(kept)

    # 2. The fresh process reads it: the machine differs with and without the file.
    run_player(player, 1500, '--trace', output / 'with.tsv')
    result['kept_at_relaunch'] = sha(kept) == written
    aside = output / 'aside.bin'
    shutil.move(kept, aside)
    run_player(player, 1500, '--trace', output / 'without.tsv')
    (saved_files(saves)[0].unlink() if saved_files(saves) else None)
    kept.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(aside, kept)
    differ = [a != b for a, b in zip(ram_column(output / 'with.tsv'), ram_column(output / 'without.tsv'))]
    result['game_read_the_file'] = any(differ)
    result['first_frame_it_shows'] = differ.index(True) + 1 if any(differ) else None

    # 3. A quick state saved before the file exists does not roll it back. The state comes from a run without the file, stopped early.
    shutil.move(kept, aside)
    state = output / 'early.rrstate'
    run_player(player, 300, '--state-save-at', 200, '--state-slot', state)
    for extra in saved_files(saves):
        extra.unlink()
    kept.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(aside, kept)
    run_player(player, 100, '--state-load-start', '--state-slot', state)
    result['state_does_not_roll_back_the_file'] = sha(kept) == written

    # 4. Damaged saves never block the game.
    data = aside.read_bytes()
    damage = {}
    for label, change in (('cut to half', lambda: kept.write_bytes(data[:len(data) // 2])), ('empty', lambda: kept.write_bytes(b'')),
                          ('a folder in its place', lambda: (kept.unlink(), kept.mkdir()))):
        change()
        status = run_player(player, 600, '--report', output / 'damaged.json', allow_stop=True)
        report = json.loads((output / 'damaged.json').read_text(encoding='utf-8'))
        damage[label] = {'status': status, 'frames': report['frames'], 'error': report['error'][:120]}
        if kept.is_dir():
            kept.rmdir()
        shutil.copy2(aside, kept)
    result['damaged_saves'] = damage
    result['damaged_saves_ran'] = all(entry['frames'] == 600 for entry in damage.values())

    # 5. A second conversion finds the same folder and the same file.
    player, second_build = build(2)
    result['second_build_differs_from_first_file'] = first_build != second_build
    run_player(player, 400)
    result['kept_after_reconversion'] = sha(kept) == written
    result['data_folders'] = len(list((play / 'datas/games').iterdir()))
    print(json.dumps(result, indent=1))
    good = (result['kept_at_relaunch'] and result['game_read_the_file'] and result['state_does_not_roll_back_the_file'] and
            result['damaged_saves_ran'] and result['kept_after_reconversion'] and result['data_folders'] == 1)
    return 0 if good else 1


if __name__ == '__main__':
    raise SystemExit(main())
