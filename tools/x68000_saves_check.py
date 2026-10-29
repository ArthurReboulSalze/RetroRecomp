"""Show, on a real X68000 game, what happens to a disk the game writes: written, kept at relaunch, kept across a reconversion.

    python tools/x68000_saves_check.py <disk> --ipl iplrom.dat --cgrom cgrom.dat --output .build/saves-<name> [--frames 3000]

Evidence for gate G7 (saves) of docs/QUALIFICATION.md; a developer tool, never part of a conversion. The steps, all in --output
(the conversion library too: RETRO_RECOMP_LIBRARY_DIR is set below it, a different one for each conversion):

  1. convert the game, copy its player to a play folder and run it headless for --frames frames with the standard qualification
     inputs: the disk the player keeps under datas/games/x68-<identity>/media must differ from the original (the game wrote);
  2. run the same player again, with no input: the disk must be the one the first run left, byte for byte;
  3. convert the game a second time (a new library, a new build folder), put that new player in the same play folder over the
     first one (the data folder stays) and run it: the disk must still be the one the first run left;
  4. report the bytes the game changed (positions and counts only, never the bytes of the game).

The folder holds executables with the disks embedded: delete it after use. Exit status 0 only when the three checks hold.
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


def run_player(player, frames, events=None):
    command = [str(player), '--headless', '--frames', str(frames)]
    if events:
        command += ['--input-events', str(events)]
    done = subprocess.run(command, cwd=player.parent, capture_output=True, timeout=600,
                          env=dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy'))
    if done.returncode:
        raise SystemExit(f'The player stopped with status {done.returncode}: {done.stderr.decode(errors="replace")[-400:]}')


def kept_disk(play):
    disks = sorted(play.glob('datas/games/x68-*/media/disk-01.*'))
    if len(disks) != 1:
        raise SystemExit(f'Expected one kept disk under {play}, found {len(disks)}.')
    return disks[0]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('rom', type=Path)
    parser.add_argument('--ipl', type=Path, required=True)
    parser.add_argument('--cgrom', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--frames', type=int, default=3000)
    options = parser.parse_args(argv)
    from retrorecomp.x68000 import read_input
    from retrorecomp.x68000_conversion import convert
    from tools.x68000_reference_check import cases
    source = read_input(options.rom)
    original = source.disks[0].read_bytes()
    output = options.output.resolve()
    shutil.rmtree(output, ignore_errors=True)
    output.mkdir(parents=True)
    os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
    os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
    events = output / 'inputs.tsv'
    events.write_text(''.join(' '.join(map(str, event)) + '\n' for event in cases()[2].events), encoding='ascii')
    play = output / 'play'
    play.mkdir()

    def build(number):
        os.environ['RETRO_RECOMP_LIBRARY_DIR'] = str(output / f'library-{number}')
        player = convert(options.rom, x68_ipl=options.ipl, x68_cgrom=options.cgrom, output=output / f'out-{number}', scan_level='quick',
                         use_cover=False, online_cover=False, emit=lambda message: None)
        target = play / 'Game.exe' if os.name == 'nt' else play / 'Game'
        shutil.copy2(player, target)
        if os.name != 'nt':
            target.chmod(0o755)
        return target, sha(Path(player).read_bytes())

    result = {'game': source.title, 'identity': source.sha256, 'frames': options.frames}
    player, first_build = build(1)
    run_player(player, options.frames, events)
    disk = kept_disk(play)
    written = disk.read_bytes()
    changed = [i for i in range(min(len(written), len(original))) if written[i] != original[i]]
    result['size_kept'] = len(written)
    result['size_original'] = len(original)
    result['bytes_changed_by_the_game'] = len(changed)
    result['first_and_last_changed_position'] = [changed[0], changed[-1]] if changed else None
    result['written_sha256'] = sha(written)
    run_player(player, 400)
    result['kept_at_relaunch'] = disk.read_bytes() == written
    player, second_build = build(2)
    result['second_build_differs_from_first_file'] = first_build != second_build
    run_player(player, 400)
    result['kept_after_reconversion'] = disk.read_bytes() == written
    # The reconverted player found the first one's data folder: no second folder named by the machine identity appeared.
    result['data_folders'] = sorted(path.name for path in (play / 'datas/games').iterdir())
    result['one_data_folder'] = len(result['data_folders']) == 1
    print(json.dumps(result, indent=1))
    return 0 if (changed and result['kept_at_relaunch'] and result['kept_after_reconversion'] and result['one_data_folder']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
