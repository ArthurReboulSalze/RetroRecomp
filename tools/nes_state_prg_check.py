"""Quick states keep the mapper's PRG register: authored cartridges, one per board that keeps its PRG bank in `m.prg`.

    python tools/nes_state_prg_check.py [--work DIR] [--root CHECKOUT] [--boards mmc1 vrc6 bandai mmc2]

Each cartridge is written here (no ROM of anyone's): 128 KiB of PRG whose banks begin with different bytes, and a program in the
fixed bank that selects bank 3 once, then, every frame, adds the first byte of the switchable window to a counter, gives the
backdrop that colour and keeps it in work RAM. The bank register is never written again, so a state that loses it loads the
other bank and the picture and memory of the continuation differ at once. The tool converts each cartridge with the batch command
line (the conversion itself runs the fresh-process state check on the delivered file) and then runs the same check again here
at two save points. A converter whose states drop the register refuses the cartridge or fails the second check.
`--root` names the checkout whose converter is used (default: this one), to run the tool on an older source.
Everything goes under `.build/nes-state-prg-check` (or --work).
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0

# board: (iNES mapper, flags 6, flags 7, bytes of a switchable window, where the fixed code is in the CPU map, the bank register's write)
BOARDS = {
    'mmc1': {'mapper': 1, 'window': 0x4000, 'fixed': 0xC000},
    'vrc6': {'mapper': 24, 'window': 0x4000, 'fixed': 0xE000},
    'bandai': {'mapper': 16, 'window': 0x4000, 'fixed': 0xC000},
    'mmc2': {'mapper': 9, 'window': 0x2000, 'fixed': 0xE000},
}
BANK = 3
PRG_SIZE = 0x20000


def sta(address: int) -> bytes:
    return bytes([0x8D, address & 0xFF, address >> 8])


def select_bank(board: str) -> bytes:
    """The writes that make bank BANK the switchable window of the board."""
    if board == 'mmc1':
        def serial(address: int, value: int) -> bytes:   # five writes of the low bit, the register fills from the bottom
            return bytes([0xA9, value]) + (sta(address) + bytes([0x4A])) * 5
        return serial(0x8000, 0x0E) + serial(0xE000, BANK)   # control: last bank fixed, 16 KiB switchable; then the bank
    return {'vrc6': bytes([0xA9, BANK]) + sta(0x8000), 'bandai': bytes([0xA9, BANK]) + sta(0x8008),
            'mmc2': bytes([0xA9, BANK]) + sta(0xA000)}[board]


def authored_cartridge(board: str) -> bytes:
    spec = BOARDS[board]
    start = spec['fixed']
    prelude = bytes([0x78, 0xD8, 0xA2, 0xFF, 0x9A]) + select_bank(board)   # SEI, CLD, LDX #$FF, TXS
    loop = start + len(prelude)
    body = (bytes([0xAD, 0x02, 0x20, 0x10, 0xFB])                          # loop: LDA $2002, BPL loop (wait for vblank)
            + bytes([0xA9, 0x3F]) + sta(0x2006) + bytes([0xA9, 0x00]) + sta(0x2006)
            + bytes([0xA5, 0x00, 0x18, 0x6D, 0x00, 0x80, 0x29, 0x3F])     # LDA $00, CLC, ADC $8000, AND #$3F
            + sta(0x2007) + bytes([0x85, 0x10])                            # STA $2007 (the backdrop), STA $10
            + bytes([0xA9, 0x3F]) + sta(0x2006) + bytes([0xA9, 0x00]) + sta(0x2006)
            + bytes([0xE6, 0x00])                                          # INC $00: the picture moves every frame
            + bytes([0x4C, loop & 0xFF, loop >> 8]))
    prg = bytearray([0xEA]) * PRG_SIZE
    for index in range(PRG_SIZE // spec['window']):
        prg[index * spec['window']] = 0x10 + 5 * index                     # what a window shows first, per bank
    fixed_offset = PRG_SIZE - (0x10000 - start)
    prg[fixed_offset:fixed_offset + len(prelude) + len(body)] = prelude + body
    for vector in (0xFFFA, 0xFFFC, 0xFFFE):
        offset = PRG_SIZE - (0x10000 - vector)
        prg[offset:offset + 2] = bytes([start & 0xFF, start >> 8])
    mapper = spec['mapper']
    header = bytes([0x4E, 0x45, 0x53, 0x1A, PRG_SIZE // 0x4000, 1, (mapper & 15) << 4, mapper & 0xF0]) + bytes(8)
    return header + bytes(prg) + bytes(0x2000)


def run(command, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run([str(part) for part in command], creationflags=NO_WINDOW, **kwargs)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--work', type=Path, default=ROOT / '.build' / 'nes-state-prg-check')
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--boards', nargs='*', choices=sorted(BOARDS), default=sorted(BOARDS))
    args = parser.parse_args()
    work = args.work.resolve()
    env = os.environ.copy()
    env.update(SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy', PYINSTALLER_SUPPRESS_SPLASH_SCREEN='1', PYTHONDONTWRITEBYTECODE='1')
    from retrorecomp.nes_checks import check_states
    failed = 0
    for board in args.boards:
        folder = work / board
        shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir(parents=True)
        rom = folder / f'PRG Check {board}.nes'
        rom.write_bytes(authored_cartridge(board))
        command = [sys.executable, '-B', 'RetroRecomp.py', 'batch', rom, '--output', folder / 'Games', '--jobs', '1', '--force',
                   '--no-shared-base', '--no-online-cover', '--system', 'nes']
        done = run(command, cwd=args.root, env=env, capture_output=True, text=True)
        games = list((folder / 'Games' / 'Nintendo NES').glob('*.exe'))
        if done.returncode or len(games) != 1:
            record = folder / 'Games' / 'datas' / 'Retro-Recomp-batch.json'
            message = [line for line in record.read_text(encoding='utf-8').splitlines() if '"message"' in line] if record.is_file() else []
            print(f'{board}: the conversion refused the cartridge: {message[0].strip() if message else done.stdout[-200:]}', flush=True)
            failed += 1
            continue
        results = []
        for save_after in (300, 900):
            try:
                check_states(games[0], 180, save_after=save_after)
                results.append(f'save at {save_after}: the continuation is identical')
            except Exception as error:   # the check names what differs
                results.append(f'save at {save_after}: {error}')
                failed += 1
        print(f'{board}: converted; ' + '; '.join(results), flush=True)
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
