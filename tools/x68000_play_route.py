"""Convert one X68000 game with its authored play route as the main route (evidence for G8, see x68000_play_routes.py).

    python tools/x68000_play_route.py <disk or .m3u> --ipl iplrom.dat --cgrom cgrom.dat --output .build/play-<name>

Nothing is written outside --output (the conversion library too: RETRO_RECOMP_LIBRARY_DIR defaults to <output>/library).
The result is the conversion report's liveness record for the delivered file, and the last picture it showed
(<output>/play-last-frame.ppm). The output folder holds an executable with the game embedded: delete it after use.
"""
import argparse
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('rom', type=Path)
    parser.add_argument('--ipl', type=Path, required=True)
    parser.add_argument('--cgrom', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    options = parser.parse_args(argv)
    from retrorecomp.x68000 import read_input
    from tools.x68000_play_routes import ROUTES
    source = read_input(options.rom)
    route = ROUTES.get(source.sha256)
    if route is None:
        parser.error(f'No play route is written for this exact disk set ({source.sha256}).')
    output = options.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault('RETRO_RECOMP_LIBRARY_DIR', str(output / 'library'))
    os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
    os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
    from retrorecomp.x68000_conversion import convert
    convert(options.rom, x68_ipl=options.ipl, x68_cgrom=options.cgrom, output=output, scan_level='quick', frames=route.frames,
            use_cover=False, online_cover=False, qualification_events=route.events, emit=print)
    report = json.loads((output / 'conversion-report.json').read_text(encoding='utf-8'))
    liveness = [row for row in report['liveness'] if row['route'] == 'main'][0]
    last = Path(report['qualification_directory']) / 'packed/main/frame.ppm'
    shutil.copy2(last, output / 'play-last-frame.ppm')
    print(json.dumps({'game': route.title, 'identity': source.sha256, 'route_frames': route.frames,
                      'packed_reference_match': report['native_validation']['packed_reference_match'],
                      'interpreted_opcodes': [row['interpreted_opcodes'] for row in report['final_checks']],
                      'liveness': liveness, 'reaches': route.reaches, 'last_picture': str(output / 'play-last-frame.ppm')}, indent=1))


if __name__ == '__main__':
    main()
