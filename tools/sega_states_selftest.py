"""Gate G6 for the Master System and the Game Gear: quick states across processes, on the shell of an export (no ROM is stored).

    python tools/sega_states_selftest.py EXE WORK        EXE: the export built against the harness (tools/hostkit_ab.py build-sms)

It runs the harness (dummy SDL drivers, no window) five times and judges them on what each one presented, frame by frame:
  1. a first process plays, saves with F8 and plays on: the state file is written;
  2. a FRESH process started with that datas folder loads it with F9 and plays on: its pictures from the load on are the first
     process's pictures after the save, frame for frame (hash of every presented picture) - the machine resumed what followed
     the save;
  3. a state with one byte changed, 4. a truncated one, 5. one of another cartridge (the ROM identity changed): F9 refuses them,
     the process goes on as if F9 had not been pressed (same pictures as a process that never pressed it) and the damaged file
     is left as it was;
  6. F9 with nothing saved creates nothing (the same files, the same pictures, as a process that never pressed it).
Nothing here says anything about hardware, play beyond the frames run, or latency."""
from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.hostkit_ab import collect, play  # noqa: E402

SAVE_AT, LOAD_AT, END = 300, 60, 700
NOTICE = 150   # iterations during which a notice (saved, loaded, refused) is drawn over the picture, and a margin


def script(path: Path, lines: list[str]) -> Path:
    path.write_text('\n'.join(lines) + '\n', encoding='ascii')
    return path


def pictures(out: Path) -> list[tuple[int, str]]:
    """(iteration, picture hash) of every picture the run presented."""
    rows = []
    for line in (out / 'frames.log').read_text(encoding='ascii').splitlines():
        part = line.split()
        if len(part) >= 3 and part[0] == 'P':
            rows.append((int(part[1]), part[2]))
    return rows


def state_files(out: Path) -> dict:
    return {name: data for name, data in collect(out).items() if name.endswith('.state')}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('exe', type=Path)
    parser.add_argument('work', type=Path)
    args = parser.parse_args()
    work = args.work
    work.mkdir(parents=True, exist_ok=True)
    save = script(work / 'save.txt', [f'{SAVE_AT} press F8', f'{END} quit'])
    load = script(work / 'load.txt', [f'{LOAD_AT} press F9', f'{END} quit'])
    never = script(work / 'never.txt', [f'{END} quit'])

    first = work / 'run-save'
    if play(args.exe, save, first, 900):
        sys.exit('the first run failed')
    saved = state_files(first)
    assert len(saved) == 1, f'F8 must write exactly one state file, found {sorted(saved)}'
    name, data = next(iter(saved.items()))
    print(f'PASS: F8 wrote {name} ({len(data)} bytes).')

    # 2. a fresh process loads it.
    resumed = work / 'run-load'
    if play(args.exe, load, resumed, 900, seed_datas=first / 'box' / 'datas'):
        sys.exit('the loading run failed')
    # The notice of the save (and of the load) is drawn over the pictures that follow it: compare after it.
    after_save = [h for i, h in pictures(first) if i >= SAVE_AT + NOTICE]
    after_load = [h for i, h in pictures(resumed) if i >= LOAD_AT + NOTICE]
    count = min(len(after_save), len(after_load)) - 5
    shift = next((s for s in range(0, 6) if after_load[s:s + count] == after_save[:count]), None)
    assert shift is not None and count >= 200, f'the fresh process does not resume the saved machine (compared {count} pictures)'
    print(f'PASS: a fresh process resumed the saved machine: {count} presented pictures identical to the first process after its '
          f'save (offset {shift}).')

    # the reference of a process that never presses F9, for the refusals and the missing state
    control = work / 'run-control'
    if play(args.exe, never, control, 900):
        sys.exit('the control run failed')
    baseline = [h for i, h in pictures(control) if i >= LOAD_AT + NOTICE]

    # 3-5. damaged states are refused and left as they were
    relative = Path(name.split('datas/', 1)[1])
    damages = {'one byte changed': lambda d: d[:len(d) // 2] + bytes([d[len(d) // 2] ^ 0xFF]) + d[len(d) // 2 + 1:],
               'truncated': lambda d: d[:len(d) // 2],
               'another cartridge': lambda d: d[:8] + bytes(b ^ 0x5A for b in d[8:40]) + d[40:]}
    for label, damage in damages.items():
        seeded = work / ('datas-' + label.replace(' ', '-'))
        if seeded.exists():
            shutil.rmtree(seeded)
        shutil.copytree(first / 'box' / 'datas', seeded)
        target = seeded / relative
        target.write_bytes(damage(target.read_bytes()))
        damaged_bytes = target.read_bytes()
        run = work / ('run-' + label.replace(' ', '-'))
        if play(args.exe, load, run, 900, seed_datas=seeded):
            sys.exit(f'the run with the {label} state failed')
        assert [h for i, h in pictures(run) if i >= LOAD_AT + NOTICE] == baseline, f'the {label} state changed the run: F9 did not refuse it'
        kept = (run / 'box' / 'datas' / relative).read_bytes()
        assert kept == damaged_bytes, f'the {label} state file was modified'
        print(f'PASS: a state with {label} is refused: same pictures as a run without F9 once its notice is gone, file left as it was.')

    # 6. F9 with nothing saved creates nothing
    nothing = work / 'run-nothing'
    if play(args.exe, load, nothing, 900):
        sys.exit('the run without a state failed')
    assert [h for i, h in pictures(nothing) if i >= LOAD_AT + NOTICE] == baseline, 'F9 with nothing saved changed the run'
    files_control = sorted(k for k in collect(control) if k.startswith('datas/'))
    files_nothing = sorted(k for k in collect(nothing) if k.startswith('datas/'))
    assert files_nothing == files_control, f'F9 created files: {sorted(set(files_nothing) - set(files_control))}'
    assert not state_files(nothing), 'F9 with nothing saved created a state file'
    print('PASS: F9 with nothing saved creates nothing and changes nothing.')
    digest = hashlib.sha256(data).hexdigest()[:16]
    print(f'Evidence for this export: state {digest}, {len(after_save)} pictures after the save, run lengths {END} iterations.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
