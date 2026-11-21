"""The ZX Spectrum on the banked Z80 chain, for development: one snapshot, its reference run, the learning passes of the native check
and the comparison of the two (retrorecomp/zxs_build.py). No window: the runs are headless. The snapshot is read in place; the work
folder (.build/zxs-native/<name>/) holds the ROM and the generated bodies while it runs and is deleted at the end unless --keep.

    python -B tools/zxs_native.py SNAPSHOT [--frames 600] [--script FILE] [--keep]

The Amstrad ROM is the pinned one (retrorecomp/zxs_roms.py, fetched on first use under Amstrad's permission for emulators).
"""
import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    for stream in (sys.stdout, sys.stderr):            # the converter's messages are not all ASCII (a cp1252 console)
        if stream is not None and hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('snapshot', type=Path)
    parser.add_argument('--frames', type=int, default=600)
    parser.add_argument('--script', type=Path)
    parser.add_argument('--keep', action='store_true')
    args = parser.parse_args()
    from retrorecomp import zxs_build, zxs_roms
    from retrorecomp.zxs_snapshot import read_snapshot
    snapshot = read_snapshot(args.snapshot)
    rom = zxs_roms.pinned(snapshot.model).data
    image = zxs_build.zxs_image(snapshot)
    work = ROOT / '.build' / 'zxs-native' / snapshot.sha256[:12]
    work.mkdir(parents=True, exist_ok=True)
    route = ['--frames', str(args.frames), *(['--script', str(args.script)] if args.script else [])]
    try:
        check, counts = zxs_build.learn(work, rom, image, [route])
        reference = zxs_build.build(work, ('zxs_reference',))['zxs_reference']
        ref = zxs_build.run(reference, work / 'rom.bin', image, route)
        nat = zxs_build.run(check, work / 'rom.bin', image, route)
        differ = zxs_build.differences(nat, ref)
        summary = {'snapshot': snapshot.metadata(), 'frames': args.frames, 'learning_fallback_steps': counts,
                   'native_steps': nat.get('native_steps'), 'guarded_steps': nat.get('guarded_steps'),
                   'fallback_steps': nat.get('fallback_steps'), 'fallback_cycles': nat.get('fallback_cycles'),
                   'fallback_at': nat.get('fallback_at'), 'interrupts': ref.get('interrupts'),
                   'audio_samples': ref.get('audio_samples'), 'equal_to_reference': not differ,
                   'differences': {k: v for k, v in list(differ.items())[:12]}}
        print(json.dumps(summary, indent=1))
        return 0 if not differ else 1
    finally:
        if not args.keep:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == '__main__':
    sys.exit(main())
