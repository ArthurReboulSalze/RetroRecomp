"""What the standard routes make of the reviewed mouse sets: sound and picture on the main route and on the mouse route.

    python tools/x68000_mouse_survey.py --roms <folder of .dim> --ipl iplrom.dat --cgrom cgrom.dat --output .build/mouse-survey [title ...]

Evidence for the route rules of docs/X68000.md; a developer tool, never part of a conversion. For each set of
native/x68000_reference/mouse_games.json found in --roms (multi-disk sets grouped as the converter groups them), the interpreted
reference runs the main route (4,000 frames) and the mouse route (10,000 frames) from a fresh bundle, two sets at a time, and the
result is written to <output>/survey.json: samples that are not zero, pictures different overall and in the last 1,000 frames,
the last frame on which the picture changed. It needs the reference executable that a conversion builds (run one conversion
first, it is read from .build/x68/*/*/discovery/ready.json). No conversion runs and nothing is written outside --output.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def analyse(folder, frames):
    report = json.loads((folder / 'r.json').read_text())
    rows = (folder / 'trace.tsv').read_text().splitlines()[1:]
    video = [row.split('\t')[1] for row in rows]
    changes = [i for i in range(1, len(video)) if video[i] != video[i - 1]]
    return {'frames': frames, 'nonzero_samples': report['nonzero_samples'], 'nonblack_frames': report['nonblack_frames'],
            'distinct_pictures': len(set(video)), 'distinct_pictures_last_1000': len(set(video[-1000:])),
            'last_picture_change': changes[-1] if changes else None}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--roms', type=Path, required=True)
    parser.add_argument('--ipl', type=Path, required=True)
    parser.add_argument('--cgrom', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('titles', nargs='*', help='only the sets whose title contains one of these words')
    options = parser.parse_args(argv)
    from retrorecomp.rom_sources import disk_sets
    from retrorecomp.x68000 import automatic_disk_changes, read_input
    from retrorecomp.x68000_scan import exploration_routes
    from tools import x68000_reference as reference
    from tools.x68000_reference_check import cases
    reference.ROOT = ROOT
    ready = next(ROOT.glob('.build/x68/*/*/discovery/ready.json'), None)
    if ready is None:
        parser.error('No reference executable: convert one game first.')
    generic = Path(json.loads(ready.read_text())['executable'])
    work = options.output.resolve()
    work.mkdir(parents=True, exist_ok=True)
    listed = json.loads((ROOT / 'native/x68000_reference/mouse_games.json').read_text(encoding='utf-8'))['games']
    sets = {}
    for path in disk_sets(sorted(options.roms.glob('*.dim')), work / 'sets').paths:
        try:
            source = read_input(path)
        except ValueError:
            continue
        if source.sha256 in listed and (not options.titles or any(word.lower() in source.title.lower() for word in options.titles)):
            sets[source.sha256] = source
    mouse_route = exploration_routes(4000, mouse_controls=True)[0]
    routes = (('main', 4000, cases()[2].events), ('mouse', mouse_route.frames, mouse_route.events))
    output = work / 'survey.json'
    results = json.loads(output.read_text()) if output.exists() else {}

    def one(identity):
        if identity in results:
            return
        source = sets[identity]
        entry = {'title': source.title, 'mouse': listed[identity]['mouse'], 'disks': len(source.disks)}
        for name, frames, events in routes:
            folder = work / (identity[:12] + '-' + name)
            shutil.rmtree(folder, ignore_errors=True)
            started = time.time()
            try:
                player = reference.prepare_bundle(folder, list(source.disks), options.ipl, options.cgrom, generic, title='probe', ram_mib=2)
                script = folder / 'inputs.tsv'
                script.write_text(''.join(' '.join(map(str, event)) + '\n' for event in events), encoding='ascii')
                command = [str(player), '--headless', '--frames', str(frames), '--report', str(folder / 'r.json'), '--trace',
                           str(folder / 'trace.tsv'), '--input-events', str(script), '--reference-cpu']
                command += ['--auto-disk'] if automatic_disk_changes(source) else []
                done = subprocess.run(command, cwd=folder, capture_output=True, timeout=900,
                                      env=dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy'))
                entry[name] = {'exit': done.returncode} if done.returncode else dict(analyse(folder, frames), seconds=round(time.time() - started, 1))
            except Exception as exc:  # noqa: BLE001 - one set never stops the survey
                entry[name] = {'error': str(exc)[:160]}
            shutil.rmtree(folder, ignore_errors=True)
        results[identity] = entry
        output.write_text(json.dumps(results, indent=1), encoding='utf-8')

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(one, list(sets)))
    print(f'{len(results)} sets in {output}')


if __name__ == '__main__':
    main()
