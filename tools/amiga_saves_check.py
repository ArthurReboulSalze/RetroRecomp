"""Show, on a real Amiga game, what happens to a file the game saves: written, read back, kept at relaunch and across a reconversion.

    python tools/amiga_saves_check.py <install.lha> --output .build/saves-<name> [--frames 6000] [--kickstart FOLDER]

Evidence for gate G7 (saves) of docs/QUALIFICATION.md; a developer tool, never part of a conversion. The game must write a file on the
standard exploration route by itself (5th Gear saves its high scores), or on the route given with --events (a file of the routes'
"begin end kind code value" lines: the inputs a player gives to make the game save, e.g. Panza Kick Boxing's OPTIONS, save, MAINTENANT);
nothing is forced. With --events, the runs that read the kept file play the same route for --read-frames frames (stop it before the
route's own save). The steps, all in --output (the conversion library
too: RETRO_RECOMP_LIBRARY_DIR is set below it, a different one for each conversion):

  1. convert the game, copy its player to a play folder and run it headless with the exploration route: a file must appear under
     datas/games/amiga-<identity>/saves;
  2. run the same player again for a moment, and once more with the file moved aside: the machine's RAM must differ between the two, so the
     game really read the kept file, and the file must be the one the first run left (when the game saved what its install already holds, the
     read is shown through a copy with one byte changed, and the result says so: `saved_equals_install_file`, `changed_byte`);
  3. a quick state saved before the game wrote the file, loaded by a fresh process: the kept file is not rolled back;
  4. damaged saves: cut to half, empty, a folder in its place: the game must still start and run (the file stays the player's); then a
     disk that refuses a save (a folder where the file goes): the game is told (a NoError slave stops there with the message, as WHDLoad
     does), the file is untouched and no temporary file stays;
  5. convert a second time (a new library, a new build folder), put that player in the same play folder and run it: the file must still be
     the one the first run left, in the same single data folder.

Only sizes, names and digests are printed, never the game's bytes. The folder holds executables with the game embedded: delete it after use.
Exit status 0 only when every check holds.
"""
import argparse
from collections import Counter
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


def refused_save_handled(save_calls, stopped_there, message, kept_name, ran_to_the_end, temporaries, still_a_folder):
    """Step 4b's verdict. A slave that stops at the refused save (WHDLoad's NoError) must stop on a refused call that names the kept file;
    a game may have saved other files before it (Panza Kick Boxing writes boxer.00i, then boxer.00A). A slave that goes on must have had
    no successful save at all. In both cases no temporary file stays and the folder where the file goes is untouched."""
    if not save_calls or temporaries or not still_a_folder:
        return False
    if stopped_there:
        named = message.rsplit('(', 1)[-1].rstrip(')').rsplit('/', 1)[-1]        # "... DOS error 221 (b/boxer.00A)": the file's own name
        return save_calls[-1] == 'abort' and named.lower() == kept_name.lower()
    return ran_to_the_end and 'ok' not in save_calls


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ram_column(trace):
    lines = Path(trace).read_text(encoding='ascii').splitlines()
    index = lines[0].split('\t').index('ram')
    return [line.split('\t')[index] for line in lines[1:]]


def install_file(lha, name):
    """The bytes of the install's own data file of that name (case-insensitive), or None."""
    from retrorecomp import amiga_lha, amiga_whdload
    blob = Path(lha).read_bytes()
    install = amiga_whdload.install(blob)
    member = next((m for rel, m in install.files.items() if rel.lower() == name.lower()), None)
    return amiga_lha.extract(blob, member) if member is not None else None


def saved_files(folder):
    return sorted(p for p in folder.rglob('*') if p.is_file()) if folder.is_dir() else []


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('lha', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--frames', type=int, default=6000)
    parser.add_argument('--kickstart', default=None)
    parser.add_argument('--events', type=Path, default=None, help='a route that makes the game save, instead of the exploration route')
    parser.add_argument('--read-frames', type=int, default=1500, help='frames of the runs that read the kept file')
    options = parser.parse_args(argv)
    from retrorecomp import amiga_whdload
    from retrorecomp.amiga_conversion import convert, explore_route, write_events
    output = options.output.resolve()
    shutil.rmtree(output, ignore_errors=True)
    output.mkdir(parents=True)
    key_exit = amiga_whdload.install(options.lha.read_bytes()).slave.key_exit
    if options.events:
        events = output / 'inputs.txt'
        events.write_bytes(options.events.read_bytes())
    else:
        events = write_events(output / 'inputs.txt', explore_route(options.frames, key_exit))
    reading = ('--input-events', events) if options.events else ()
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

    # 2. The fresh process reads it: the machine differs with and without the file. A game that saves what its install already holds
    #    (a high-score table nobody beat on this route: 5th Gear) writes a file the machine cannot tell from the install's own, so the
    #    kept file is then shown through a copy with one byte changed, the first that makes the machine differ; the result says so.
    run_player(player, options.read_frames, '--trace', output / 'with.tsv', *reading)
    result['kept_at_relaunch'] = sha(kept) == written
    aside = output / 'aside.bin'
    shutil.move(kept, aside)
    run_player(player, options.read_frames, '--trace', output / 'without.tsv', *reading)
    for extra in saved_files(saves):
        extra.unlink()
    base = ram_column(output / 'without.tsv')
    data = aside.read_bytes()
    default = install_file(options.lha, kept.relative_to(saves).as_posix())
    result['saved_equals_install_file'] = default == data
    variants = [(None, data)]
    if default == data:
        variants = [(at, data[:at] + bytes([data[at] ^ 1]) + data[at + 1:]) for at in (len(data) // 2, 8, 100, 255, len(data) - 8) if 0 <= at < len(data)]
    result['game_read_the_file'], result['first_frame_it_shows'], result['changed_byte'] = False, None, None
    for at, content in variants:
        kept.parent.mkdir(parents=True, exist_ok=True)
        kept.write_bytes(content)
        run_player(player, options.read_frames, '--trace', output / 'with.tsv', *reading)
        kept.unlink()
        differ = [a != b for a, b in zip(ram_column(output / 'with.tsv'), base)]
        if any(differ):
            result['game_read_the_file'], result['first_frame_it_shows'], result['changed_byte'] = True, differ.index(True) + 1, at
            break
    kept.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(aside, kept)

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
    damaged_frames = options.read_frames if options.events else 600
    for label, change in (('cut to half', lambda: kept.write_bytes(data[:len(data) // 2])), ('empty', lambda: kept.write_bytes(b'')),
                          ('a folder in its place', lambda: (kept.unlink(), kept.mkdir()))):
        change()
        # With a route, the damaged file is offered where the game reads it (the route up to --read-frames); else 600 frames from the start.
        status = run_player(player, damaged_frames, '--report', output / 'damaged.json', *reading, allow_stop=True)
        report = json.loads((output / 'damaged.json').read_text(encoding='utf-8'))
        damage[label] = {'status': status, 'frames': report['frames'], 'error': report['error'][:120]}
        if kept.is_dir():
            kept.rmdir()
        shutil.copy2(aside, kept)
    result['damaged_saves'] = damage
    result['damaged_saves_ran'] = all(entry['frames'] == damaged_frames for entry in damage.values())

    # 4b. A disk that refuses the save: a folder where the file goes, so the replacing rename fails. The game saves on the same route as
    #     in step 1 and is told it failed (DOS error 221). A slave that sets WHDLoad's NoError flag expects no error back, so the run
    #     stops there with the message, as WHDLoad does; any other slave gets the error and may go on. Either way the save must have been
    #     refused, no temporary file may stay behind and the folder is not touched (refused_save_handled).
    kept.unlink()
    kept.mkdir()
    refused_log = output / 'refused-resload.log'
    status = run_player(player, options.frames, '--input-events', events, '--report', output / 'refused.json', '--resload-log', refused_log,
                        allow_stop=True)
    report = json.loads((output / 'refused.json').read_text(encoding='utf-8'))
    # SaveFile (0C) or SaveFileOffset (38): an install with WHDLoad's OS emulation writes through the second.
    save_calls = [line.split()[2] for line in refused_log.read_text(encoding='ascii').splitlines()[1:] if line.split()[1:2] in (['0C'], ['38'])]
    stopped_there = bool(report.get('stopped')) and report.get('error', '').startswith(('SaveFile failed with DOS error 221',
                                                                                       'SaveFileOffset failed with DOS error 221'))
    result['refused_save'] = {'frames': report['frames'], 'status': status, 'save_calls': dict(Counter(save_calls)),
                              'game_stopped_at_the_save': stopped_there, 'message': report.get('error', '')[:80],
                              'temporaries_left': [p.name for p in saves.rglob('*.tmp')], 'still_a_folder': kept.is_dir()}
    result['refused_save_handled'] = refused_save_handled(save_calls, stopped_there, report.get('error', ''), kept.name,
                                                          report['frames'] == options.frames, result['refused_save']['temporaries_left'], kept.is_dir())
    shutil.rmtree(kept, ignore_errors=True)
    shutil.copy2(aside, kept)

    # 5. A second conversion finds the same folder and the same file.
    player, second_build = build(2)
    result['second_build_differs_from_first_file'] = first_build != second_build
    run_player(player, 400)
    result['kept_after_reconversion'] = sha(kept) == written
    result['data_folders'] = len(list((play / 'datas/games').iterdir()))
    print(json.dumps(result, indent=1))
    good = (result['kept_at_relaunch'] and result['game_read_the_file'] and result['state_does_not_roll_back_the_file'] and
            result['damaged_saves_ran'] and result['refused_save_handled'] and result['kept_after_reconversion'] and result['data_folders'] == 1)
    return 0 if good else 1


if __name__ == '__main__':
    raise SystemExit(main())
