"""Packed-export qualification for one Super Nintendo game (developer tool).

A conversion compares the native build with its interpreter reference on the
*unpacked* build executable; the published game is that file packed by UPX.
This replays the report's own scenarios (demo, play, the random route, the
authored route when the report has one) on the PUBLISHED executable, native and
reference (RR_SNES_FORCE_INTERP=1), compares them field by field, applies the
activity gates, then runs the fresh-process state check of
tools/console16_state_selftest.py. It is the check the DSP-1 and CX4 campaigns
ran by hand (docs/SNES.md), kept out of the conversion because it replays the
scenarios twice more (tens of minutes at the Extended level).

    python tools/snes_packed_check.py "Export/Super Nintendo/Game.exe" [--work DIR]
        [--report conversion-report.json] [--state-warmup 7800]

The result goes to DIR/packed-validation.json (default: a folder beside the
executable's temporary copy under .build/packed-check/). Exit status 0 only when
every comparison matches and the executable carries the UPX header the report
recorded. Never writes into the export; the executable is copied first.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

STATE_REPLAY = 180
STATE_WARMUP = 7800
KEEP = ('scenario', 'frames', 'main_interpreted_opcodes', 'audio_interpreted_opcodes', 'native_entries',
        'coprocessor_instructions', 'cartridge_chip', 'coprocessor_mode', 'coprocessor_failed',
        'pcm_nonzero', 'audio_ring_dropped', 'audio_output_underflows', 'ram_observation_overflows',
        'visible_frames', 'video_standard', 'frame_hash', 'sequence_hash', 'sram_hash',
        'last_picture_change_frame', 'last_device_frame', 'last_audible_frame')


def find_report(executable: Path, explicit: Path | None) -> Path:
    if explicit:
        return explicit
    found = list((executable.parent / 'datas' / 'reports').glob('*/conversion-report.json'))
    if len(found) != 1:
        raise SystemExit(f'Expected exactly one conversion report beside the executable, found {len(found)}; use --report.')
    return found[0]


def route_scripts(report: dict, work: Path) -> dict:
    """The scripts of the report's route scenarios, regenerated from the ROM identity."""
    from retrorecomp import snes_routes
    from retrorecomp.random_routes import long_routes, write_route
    sha = report['rom']['sha256']
    scan = report.get('advanced_scan') or {}
    scripts = {}
    entries = scan.get('long_routes') or []
    if entries:
        routes = long_routes('snes', sha, count=len(entries), frames=entries[0]['frames'])
        for route, entry in zip(routes, entries):
            if route.metadata()['seed'] != entry['seed']:
                raise SystemExit(f'Route seed of {route.name} differs from the conversion; refusing to compare other inputs.')
            scripts[route.name] = write_route(route, work)
    current = {item.name: item for item in snes_routes.authored_routes(sha)}
    for entry in scan.get('authored_routes') or []:
        # An exact ROM may have several authored routes; each is matched by its scenario name.
        route = current.get(entry.get('scenario'))
        if route is None or route.script_sha256() != entry['script_sha256']:
            raise SystemExit(f"The authored route {entry.get('scenario')!r} of this converter differs "
                             'from the one in the report.')
        scripts[route.name] = write_route(route, work)
    return scripts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('executable', type=Path)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--work', type=Path)
    parser.add_argument('--state-warmup', type=int, default=STATE_WARMUP)
    parser.add_argument('--skip-state', action='store_true')
    parser.add_argument('--allow-unpacked', action='store_true',
                        help='Accept an executable without the UPX header (developer builds).')
    options = parser.parse_args()
    from retrorecomp import supernintendo
    from retrorecomp.console16 import probe16, reference_differences
    from tools.console16_state_selftest import check as state_check

    source = options.executable.resolve()
    report_path = find_report(source, options.report)
    report = json.loads(report_path.read_text(encoding='utf-8'))
    data = source.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    packed = b'UPX!' in data
    recorded = (report.get('packing') or {}).get('published', {}).get('sha256')
    if not packed and not options.allow_unpacked:
        raise SystemExit('The executable carries no UPX header: this checks published (packed) games.')
    work = (options.work or ROOT / '.build' / 'packed-check' / source.stem.replace(' ', '_')).resolve()
    work.mkdir(parents=True, exist_ok=True)
    copy = work / source.name
    shutil.copy2(source, copy)
    scripts = route_scripts(report, work)
    result = {'executable': source.name, 'bytes': len(data), 'sha256': digest, 'upx_header': packed,
              'matches_recorded_packing': None if recorded is None else recorded == digest,
              'rom_sha256': report['rom']['sha256'], 'report': str(report_path), 'checks': []}
    started = time.monotonic()
    for check in report['final_checks']:
        name, frames = check['scenario'], check['frames']
        extra = dict(play=name != 'demo', scenario=name)
        if name in scripts:
            extra['input_script'] = scripts[name]
        native = probe16(copy, work, frames, **extra)
        reference = probe16(copy, work, frames, reference=True, **extra)
        row = {key: native.get(key) for key in KEEP}
        row['differences'] = reference_differences('snes', native, reference)
        row['same_as_conversion_report'] = {key: native.get(key) == check.get(key)
                                            for key in ('frame_hash', 'sequence_hash', 'coprocessor_instructions')}
        try:
            supernintendo.validate_device_liveness([native])
            row['liveness'] = 'pass'
        except Exception as error:  # recorded, the verdict below decides
            row['liveness'] = str(error)
        result['checks'].append(row)
        print(name, frames, 'differences:', row['differences'] or 'none', 'liveness:', row['liveness'], flush=True)
    result['frame_pairs'] = sum(row['frames'] for row in result['checks'])
    scripted = max(scripts, key=lambda key: next(c['frames'] for c in report['final_checks'] if c['scenario'] == key),
                   default=None)
    total = max(row['frames'] for row in result['checks'])
    if options.skip_state:
        result['state'] = {'skipped': True}
    else:
        try:
            warmup = min(options.state_warmup, max(0, total - STATE_REPLAY))
            result['state'] = state_check(copy, work / 'state', warmup, STATE_REPLAY,
                                          input_script=scripts.get(scripted) if scripted else None)
        except Exception as error:  # recorded, never raised
            result['state'] = {'error': str(error)[:4000]}
    result['passed'] = (all(not row['differences'] and row['liveness'] == 'pass' for row in result['checks'])
                        and 'error' not in result['state'] and (packed or options.allow_unpacked)
                        and result['matches_recorded_packing'] is not False)
    result['wall_seconds'] = round(time.monotonic() - started, 1)
    (work / 'packed-validation.json').write_text(json.dumps(result, indent=1), encoding='utf-8')
    print('PASSED' if result['passed'] else 'FAILED', result['wall_seconds'], 's ->', work / 'packed-validation.json')
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
