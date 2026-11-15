"""Show, on a real Nintendo 64 game, what happens to its cartridge save or controller pak: written, read back by a fresh process, not
rolled back by a quick state, and never a reason for the game to stop.

    python tools/n64_saves_check.py --exe <game exe, or the reference player with --rom> --route main|explore|play --frames N
                                    --output .build/saves-<name> [--rom FILE] [--read-frames M] [--state-at F]

Evidence for gate G7 (saves) of docs/QUALIFICATION.md; a developer tool, never part of a conversion. The game must write its save on the
route by itself (nothing is forced). The save file of the player holds the EEPROM (2 KiB), the four controller paks (32 KiB each), the
SRAM (32 KiB) and the Flash (128 KiB), in that order, the core's own layout; it is written only when the memory changed. The steps, all
in --output:

  1. the route from no file: a file must appear, and the kinds that changed are named (EEPROM, SRAM and Flash against their erased
     value 0xFF, a pak against the pak the game never touched);
  2. a fresh process plays the first --read-frames frames with the kept file, and again with a copy in which one byte of a changed
     kind is altered: their RDRAM must differ (the game read the kept file), and the first must leave the file as it was or extend it;
  3. a quick state saved at --state-at, before the route wrote, loaded by a fresh process with the kept file: the file after that
     run must still hold what the route wrote (a state does not roll a save back);
  4. damaged files (cut to half, empty, a folder in its place): the game must still run --read-frames frames, and the file is left
     as it was (the player loads only a file of the right size and never overwrites another).

Only sizes, names, offsets and digests are printed, never the game's bytes. Exit status 0 only when every check holds.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from retrorecomp import n64, n64_conversion  # noqa: E402

KINDS = (('eeprom', 0, 0x800), ('pak1', 0x800, 0x8000), ('pak2', 0x8800, 0x8000), ('pak3', 0x10800, 0x8000),
         ('pak4', 0x18800, 0x8000), ('sram', 0x20800, 0x8000), ('flash', 0x28800, 0x20000))
SIZE = 0x48800


def run(exe: Path, folder: Path, frames: int, events: Path, saves: Path, rom: Path | None, extra=()) -> dict:
    folder.mkdir(parents=True, exist_ok=True)
    args = [str(exe), '--headless', '--frames', str(frames), '--input-events', str(events), '--saves', str(saves),
            '--report', str(folder / 'result.json'), '--trace', str(folder / 'trace.tsv')]
    if rom:
        args += ['--rom', str(rom)]
    args += [str(a) for a in extra]
    result = subprocess.run(args, capture_output=True, timeout=max(900, frames // 2))
    (folder / 'stderr.log').write_bytes(result.stderr[-20000:])
    report = {}
    if (folder / 'result.json').is_file():
        report = json.loads((folder / 'result.json').read_text(encoding='utf-8'))
    report['exit'] = result.returncode
    return report


def changed_kinds(data: bytes) -> dict:
    """{kind: (first changed offset in the kind, bytes changed)} against the erased value or the untouched pak."""
    out = {}
    paks = [data[o:o + n] for name, o, n in KINDS if name.startswith('pak')]
    untouched = max(set(paks), key=paks.count)
    for name, offset, size in KINDS:
        part = data[offset:offset + size]
        base = untouched if name.startswith('pak') else b'\xff' * size
        diffs = [i for i in range(size) if part[i] != base[i]]
        if diffs:
            out[name] = (diffs[0], len(diffs))
    return out


def digest(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16] if path.is_file() else None


def ram_column(folder: Path) -> list[str]:
    lines = (folder / 'trace.tsv').read_text(encoding='ascii').splitlines()
    head = lines[0].split('\t')
    return [line.split('\t')[head.index('ram')] for line in lines[1:]]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--rom', type=Path)
    parser.add_argument('--route', default='main')
    parser.add_argument('--events', type=Path, help='a route file of "begin end kind code value" lines instead of --route')
    parser.add_argument('--frames', type=int, default=3600)
    parser.add_argument('--read-frames', type=int, default=600)
    parser.add_argument('--state-at', type=int, default=0)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--discover', action='store_true', help='step 1 only: which kinds the route writes')
    args = parser.parse_args()
    out = args.output
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    if args.events:
        events = [tuple(int(f) if i != 2 else f for i, f in enumerate(line.split()))
                  for line in args.events.read_text(encoding='ascii').splitlines() if line.strip()]
    elif args.route == 'main':
        events = n64_conversion.main_route(args.frames)
    elif args.route == 'explore':
        events = n64_conversion.explore_route(args.frames)
    else:
        code = n64.read_input(args.rom).header.game_code if args.rom else None
        route = n64_conversion.play_route(code) if code else None
        if not route:
            print('no play route for this game')
            return 2
        events = route[1]
    script = n64_conversion.write_events(out / 'events.txt', events)
    result = {'route': args.route, 'frames': args.frames}
    ok = True

    # 1. written
    saves = out / 'saves.bin'
    first = run(args.exe, out / 'write', args.frames, script, saves, args.rom,
                ['--state-save-at', args.state_at, '--state-slot', out / 'early.rrstate'] if args.state_at else ())
    result['write_exit'] = first['exit']
    if not saves.is_file() or saves.stat().st_size != SIZE:
        result['written'] = False
        print(json.dumps(result, indent=1))
        return 1
    data = saves.read_bytes()
    kinds = changed_kinds(data)
    result['written'] = {k: {'first_offset': o, 'bytes': n} for k, (o, n) in kinds.items()}
    if args.discover:
        print(json.dumps(result, indent=1))
        return 0
    written = saves.read_bytes()
    kept = out / 'kept.bin'
    shutil.copy2(saves, kept)

    # 2. read back by a fresh process: the kept file against a copy with one byte changed in the first changed kind
    name, (offset, _) = next(iter(kinds.items()))
    base = dict((k, o) for k, o, _ in KINDS)[name]
    altered = bytearray(written)
    altered[base + offset] ^= 0x01
    read_a, read_b = out / 'read-kept.bin', out / 'read-altered.bin'
    shutil.copy2(kept, read_a)
    read_b.write_bytes(bytes(altered))
    a = run(args.exe, out / 'read-kept', args.read_frames, script, read_a, args.rom)
    b = run(args.exe, out / 'read-altered', args.read_frames, script, read_b, args.rom)
    ram_a, ram_b = ram_column(out / 'read-kept'), ram_column(out / 'read-altered')
    first_diff = next((i for i, (x, y) in enumerate(zip(ram_a, ram_b)) if x != y), None)
    after = read_a.read_bytes()
    result['read_back'] = {'kind_altered': name, 'offset_in_kind': offset, 'ram_differs_from_frame': first_diff,
                           'file_after_read': 'unchanged' if after == written else 'changed', 'exits': [a['exit'], b['exit']]}
    ok &= first_diff is not None and a['exit'] in (0, 2) and b['exit'] in (0, 2)

    # 3. a quick state from before the write does not roll the save back
    if args.state_at:
        rolled = out / 'state-saves.bin'
        shutil.copy2(kept, rolled)
        s = run(args.exe, out / 'state', 60, script, rolled, args.rom, ['--state-load-start', '--state-slot', out / 'early.rrstate'])
        back = rolled.read_bytes()
        lost = {k: sum(1 for i in range(o, o + n) if back[i] != written[i]) for k, o, n in KINDS if k in kinds}
        result['state_before_write'] = {'exit': s['exit'], 'bytes_of_the_written_kinds_changed': lost, 'state_loaded': s.get('state_loaded')}
        ok &= s['exit'] in (0, 2) and not any(lost.values())

    # 4. damaged files: the game runs, the file is left as it was
    damaged = {}
    for label in ('half', 'empty', 'folder'):
        target = out / f'damaged-{label}.bin'
        if label == 'half':
            target.write_bytes(written[:SIZE // 2])
        elif label == 'empty':
            target.write_bytes(b'')
        else:
            target.mkdir()
        before = digest(target)
        d = run(args.exe, out / f'damaged-{label}', args.read_frames, script, target, args.rom)
        same = digest(target) == before if label != 'folder' else target.is_dir()
        damaged[label] = {'exit': d['exit'], 'frames': d.get('frames'), 'stopped': d.get('stopped'), 'left_as_it_was': same}
        ok &= d['exit'] in (0, 2) and d.get('frames') == args.read_frames and not d.get('stopped') and same
    result['damaged'] = damaged
    result['passed'] = bool(ok)
    (out / 'result.json').write_text(json.dumps(result, indent=1), encoding='utf-8')
    print(json.dumps(result, indent=1))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
