"""Gate G6 for the Game Boy: a state taken in one process continues the game in a fresh process, and a damaged or missing state is refused.

The delivered executable keeps its quick state with `gb_context_save_state_file` / `gb_context_load_state_file`, the same two functions
the F8 and F9 keys call (the keys only add the path of slot 1 under `datas`), and the headless flags `--save-state-file` and
`--load-state-file` call them too. So this check drives those flags in separate processes:

  * one run of N + M frames, dumped with `--dump-state`;
  * a run of N frames that saves a state, then a fresh process that loads it and runs M frames: its dump must equal the continuous
    one field by field (registers, cycles, work RAM, the picture and sound counters), and so must a second hop from that state;
  * a state cut short, with a wrong magic, a wrong version, another ROM's hash or a wrong memory size is refused (exit 1, the message,
    no game running) and the file is left as it was; a state that does not exist is refused and nothing is created.

The cartridge is authored here (no original bytes): the screen on, a square channel playing, a vertical-blank and a timer interrupt, and a
counter that runs in the foreground, so that registers, interrupts, the picture unit and the sound unit all move between the frames.
`--rom FILE` runs the same sequences on a game of the player's instead (convert it first or let the check do it).

    python tools/gameboy_states_check.py [--work FOLDER] [--rom FILE] [--reuse] [--frames N] [--more M]

This tests the runtime's state files in separate processes; the F8 and F9 keys themselves (and the slot path) need a window and are not
driven here. A byte changed inside a state of the right length is not detected: the file has no checksum.
"""
from __future__ import annotations

import argparse
import json
import shutil
import struct
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gameboy_saves_check as saves                      # noqa: E402  (the assembler, the ROM builder and the conversion)

ROOT = saves.ROOT
NAME = 'states'
HEADER_FIELDS = struct.Struct('<IIQ')                    # magic, version, ROM hash: the start of the runtime's state header


def ldh(a: saves.Assembler, address: int, value: int) -> None:
    a.ld_a(value)
    a.emit(0xE0, address & 0xFF)


def authored_rom() -> bytes:
    a = saves.Assembler(0x150)
    a.emit(0x31, 0xFE, 0xFF)                                          # LD SP,$FFFE
    ldh(a, 0x40, 0x00)                                                  # screen off while the tile is written
    a.ld_hl(0x8000); a.ld_b(16); a.ld_a(0xF0)                           # tile 0: vertical stripes four pixels wide
    a.label('tile')
    a.ld_hli_a(); a.dec_b(); a.jr('nz', 'tile')
    for address, value in ((0x47, 0xE4),                                # background palette
                           (0x26, 0x80), (0x24, 0x77), (0x25, 0xFF),   # sound on, volume, both sides
                           (0x11, 0x80), (0x12, 0xF3), (0x13, 0x40), (0x14, 0x87),   # square 1: duty, envelope, pitch, trigger
                           (0x07, 0x05),                                # timer on, 262,144 Hz
                           (0x40, 0x91),                                # screen and background on
                           (0xFF, 0x05)):                               # interrupts: vertical blank and timer
        ldh(a, address, value)
    a.emit(0xFB)                                                        # EI
    a.ld_hl(0xC100)
    a.label('loop')
    a.emit(0x34)                                                        # INC (HL)
    a.emit(0x7E)                                                        # LD A,(HL)
    a.emit(0xE0, 0x43)                                                  # LDH ($43),A : the scroll follows the counter
    a.jr('', 'loop')
    foreground = a.finish()
    handler = bytes.fromhex('F5 FA10C1 3C EA10C1 E013 F1 D9')          # vertical blank: counts, bends the pitch of square 1
    timer = bytes.fromhex('F5 FA11C1 3C EA11C1 F1 D9')                  # timer: counts
    return saves.build_rom('RRSTATE', 0x00, 0x00, foreground, {0x40: bytes.fromhex('C30002'), 0x50: bytes.fromhex('C31002'),
                                                                0x200: handler, 0x210: timer})


def launch(executable: Path, folder: Path, *args, timeout: int = 300) -> dict:
    result = subprocess.run([str(executable), '--headless', *map(str, args)], env=saves.environment(), capture_output=True,
                            text=True, timeout=timeout, cwd=folder)
    return {'exit': result.returncode, 'output': result.stdout + result.stderr}


def dump(executable: Path, folder: Path, tag: str, frames: int, *args) -> tuple[dict, dict | None]:
    path = folder / f'dump-{tag}.json'
    path.unlink(missing_ok=True)
    result = launch(executable, folder, '--limit-frames', frames, '--dump-state', path, *args)
    return result, json.loads(path.read_text(encoding='utf-8')) if path.is_file() else None


def trace_rows(path: Path) -> list[list[str]]:
    """The lines of a `--frame-trace` file without their frame number: picture hash, sound hash, non-zero samples, RAM hash, PC."""
    lines = path.read_text(encoding='ascii').splitlines()[1:] if path.is_file() else []
    return [line.split(',')[1:] for line in lines]


def differences(left: dict, right: dict) -> list[str]:
    return [key for key in sorted(set(left) | set(right)) if left.get(key) != right.get(key)]


def listing(folder: Path) -> dict[str, bytes]:
    return {str(path.relative_to(folder)): path.read_bytes() for path in sorted(folder.rglob('*')) if path.is_file()}


def run_checks(executable: Path, work: Path, frames: int, more: int, failures: list[str]) -> dict:
    folder = work / f'run_{executable.stem}'
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    game = folder / executable.name
    shutil.copy2(executable, game)
    record: dict = {'game': executable.stem, 'frames': frames, 'more': more}
    check = lambda ok, text: saves.check(ok, text, failures)       # noqa: E731

    continuous, whole = dump(game, folder, 'continuous', frames + more, '--frame-trace', folder / 'continuous.csv')
    first, early = dump(game, folder, 'first', frames, '--save-state-file', folder / 'one.state')
    check(continuous['exit'] == 0 and first['exit'] == 0 and whole and early, 'the continuous run and the run that saves end normally')
    state = (folder / 'one.state').read_bytes() if (folder / 'one.state').is_file() else b''
    check(len(state) > 40000, f'the state file is written ({len(state)} bytes)')
    check(bool(whole and early) and differences(early, whole) != [], f'the game moves between frame {frames} and frame {frames + more}')

    second, resumed = dump(game, folder, 'resumed', more, '--load-state-file', folder / 'one.state', '--save-state-file', folder / 'two.state',
                           '--frame-trace', folder / 'resumed.csv')
    check(second['exit'] == 0 and resumed is not None and 'Loaded execution state' in second['output'],
          f'a fresh process loads the state and runs {more} more frames')
    wrong = differences(resumed, whole) if resumed and whole else ['nothing was dumped']
    check(not wrong, 'its dump equals the continuous run field by field' + (f' (differs: {wrong})' if wrong else ''))
    record['first_hop_differs'] = wrong
    rows_whole, rows_resumed = trace_rows(folder / 'continuous.csv'), trace_rows(folder / 'resumed.csv')
    tail = rows_whole[-len(rows_resumed):] if rows_resumed else []
    check(len(rows_resumed) >= more - 1 and tail == rows_resumed,
          f'the picture, the sound, the RAM and the program counter of each of its {len(rows_resumed)} frames equal the continuous run\'s')
    record['trace_rows_compared'] = len(rows_resumed)

    third, chained = dump(game, folder, 'chained', more, '--load-state-file', folder / 'two.state')
    _, long_run = dump(game, folder, 'long', frames + 2 * more)
    wrong = differences(chained, long_run) if chained and long_run else ['nothing was dumped']
    check(third['exit'] == 0 and not wrong, 'a state taken after a load continues the same way' + (f' (differs: {wrong})' if wrong else ''))
    record['second_hop_differs'] = wrong

    again, repeat = dump(game, folder, 'again', more, '--load-state-file', folder / 'one.state')
    check(repeat == resumed, 'the same state loaded again gives the same dump (nothing is left over from the earlier process)')

    before = listing(folder)
    outcomes = {}
    cases = {'cut at 0 bytes': state[:0], 'cut inside the header': state[:10], 'cut inside the body': state[:len(state) // 2],
             'one byte short': state[:-1], 'not a state': b'this is not a state file\n' * 3000}
    magic, version, rom_hash = HEADER_FIELDS.unpack_from(state, 0) if len(state) >= HEADER_FIELDS.size else (0, 0, 0)
    for label, value in (('wrong magic', (magic ^ 1, version, rom_hash)), ('wrong version', (magic, version + 1, rom_hash)),
                         ('another ROM', (magic, version, rom_hash ^ 0x100))):
        cases[label] = HEADER_FIELDS.pack(*value) + state[HEADER_FIELDS.size:] if state else b''
    if len(state) >= 28:
        size_at = HEADER_FIELDS.size + 4                            # the ROM size field follows the hash
        cases['wrong ROM size'] = state[:size_at] + struct.pack('<I', 12345) + state[size_at + 4:]
    for label, data in cases.items():
        path = folder / 'damaged.state'
        path.write_bytes(data)
        result, snapshot = dump(game, folder, 'damaged', more, '--load-state-file', path)
        check(result['exit'] != 0 and snapshot is None and 'Failed to load execution state' in result['output'],
              f'{label}: the state is refused and no game runs (exit {result["exit"]})')
        check(path.read_bytes() == data, f'{label}: the file is left as it was')
        outcomes[label] = result['exit']
    record['refused'] = outcomes

    for item in folder.glob('damaged.state'):
        item.unlink()
    for item in folder.glob('dump-damaged.json'):
        item.unlink()
    after_bad = listing(folder)
    check(set(after_bad) <= set(before), 'refusing damaged states creates no file')

    missing = folder / 'nowhere' / 'none.state'
    result, snapshot = dump(game, folder, 'missing', more, '--load-state-file', missing)
    check(result['exit'] != 0 and snapshot is None and not missing.exists() and not missing.parent.exists(),
          f'a state that does not exist is refused and nothing is created (exit {result["exit"]})')
    check(not (folder / 'datas').exists(), 'no data folder appears beside the game')
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--work', type=Path, default=ROOT / '.build' / 'gb-states')
    parser.add_argument('--rom', type=Path, help='a game of the player\'s instead of the authored cartridge')
    parser.add_argument('--reuse', action='store_true', help='use the executable already converted in the work folder')
    parser.add_argument('--frames', type=int, default=120)
    parser.add_argument('--more', type=int, default=120)
    args = parser.parse_args()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    name = args.rom.stem if args.rom else NAME
    executable = work / f'out_{name}' / 'Game Boy' / f'{name}.exe'
    if not (args.reuse and executable.is_file()):
        executable = saves.convert(name, work, args.rom.read_bytes() if args.rom else authored_rom())
    failures: list[str] = []
    record = run_checks(executable, work, args.frames, args.more, failures)
    (work / 'results.json').write_text(json.dumps({'record': record, 'failures': failures}, indent=2) + '\n', encoding='utf-8')
    print(f'{len(failures)} failure(s)')
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
