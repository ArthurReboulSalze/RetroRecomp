"""Cartridge saves of the Super Nintendo boards, on cartridges written for the purpose (G7).

One small authored cartridge per board (no ROM byte of any game): its reset code touches the board's save RAM through
24-bit long addresses (a marker at the first byte, a marker at the very last byte, and a counter that every boot adds one
to), then lets the picture change every frame so that the liveness check of the converter has something to see. For each
board the tool converts the cartridge, runs it natively and against the fully interpreted reference, and then checks:
  * a board with a battery writes its save file (112-byte header, board code, size, whole RAM), a second process reads it
    back (counter 2), and the markers at both ends of the RAM survive;
  * a board with RAM and no battery writes no file at all, and its RAM starts blank at every boot;
  * a damaged file (payload byte, cartridge identity, board code, size, version, a missing or an extra byte, an empty file)
    never stops the game: it is set aside byte for byte as <name>.unusable-N, the game starts with a blank RAM, saves a new file
    and says so in its report (`save_set_aside`); a file that cannot be set aside is left untouched and the command asking for
    the save reports it (exit 9);
  * no half-written file (`*.tmp`) is left behind, and the quick states of the same board restore in a fresh process.
This checks the adapter and the file format, not the behaviour of any commercial cartridge. The SA-1 board has its own
fixture in `snes_sa1_selftest.py`.
"""
from __future__ import annotations
import json
from pathlib import Path
import shutil
import subprocess
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp import supernintendo  # noqa: E402
from retrorecomp.cartridge16 import read_snes_rom  # noqa: E402
from retrorecomp.console16 import prepare16, probe16, reference_differences  # noqa: E402
from retrorecomp.library import atomic_json  # noqa: E402
from tools.console16_state_selftest import check as state_check  # noqa: E402

HEADER = 112          # the battery file: 112 bytes of header, then the whole RAM
CODES = {'lorom': 1, 'hirom': 2, 'superfx': 3, 'dsp1-hirom': 6, 'sdd1': 8}   # the engine's CART_* values
ROM_BYTES = 0x10000
# name, mapping, map mode, chip type, RAM exponent, battery, board code, S-CPU address of the first RAM byte,
# of the last one, bytes in the file (None: no file). A Super FX header declares no RAM in its $FFD8 byte (0 here, as on every
# real GSU cartridge): the board has 64 KiB.
BOARDS = (
    ('lorom-8k-battery',       'lorom', 0x20, 0x02, 3, True,  'lorom',      0x700000, 0x701fff, 0x2000),
    ('lorom-8k-ram-only',      'lorom', 0x20, 0x01, 3, False, 'lorom',      0x700000, 0x701fff, None),
    ('lorom-128k-battery',     'lorom', 0x20, 0x02, 7, True,  'lorom',      0x700000, 0x737fff, 0x20000),
    ('hirom-32k-battery',      'hirom', 0x21, 0x02, 5, True,  'hirom',      0x206000, 0x237fff, 0x8000),
    ('hirom-8k-ram-only',      'hirom', 0x21, 0x01, 3, False, 'hirom',      0x206000, 0x207fff, None),
    ('superfx-64k-battery',    'lorom', 0x20, 0x15, 0, True,  'superfx',    0x700000, 0x70ffff, 0x10000),
    ('superfx-64k-ram-only',   'lorom', 0x20, 0x14, 0, False, 'superfx',    0x700000, 0x70ffff, None),
    ('sdd1-8k-battery',        'lorom', 0x32, 0x45, 3, True,  'sdd1',       0x700000, 0x701fff, 0x2000),
    ('dsp1-hirom-8k-battery',  'hirom', 0x31, 0x05, 3, True,  'dsp1-hirom', 0x206000, 0x207fff, 0x2000),
)


def long_address(opcode, address):
    return bytes((opcode, address & 255, (address >> 8) & 255, address >> 16))


def program(counter, first, last):
    code = bytearray.fromhex('78 18 fb c2 10 e2 20 a2 ff 1f 9a 9c 00 42 a9 80 8d 00 21')
    code += long_address(0xaf, counter) + b'\x1a' + long_address(0x8f, counter)      # LDA long, INC A, STA long
    for value, address in ((0xa5, first), (0x5a, first + 1), (0x3c, last)):
        code += bytes((0xa9, value)) + long_address(0x8f, address)                    # LDA #value, STA long
    code += bytes.fromhex('a9 0f 8d 00 21 a9 81 8d 00 42 cb 80 fd')                   # display on, NMI on, WAI loop
    nmi = bytes.fromhex('9c 21 21 a5 10 1a 85 10 8d 22 21 9c 22 21 40')              # backdrop colour changes each frame
    return bytes(code), nmi


def cartridge(board):
    name, mapping, mode, chip, ram_exp, _battery, _code, first, last, _size = board
    hirom = mapping == 'hirom'
    rom = bytearray(ROM_BYTES)
    start = 0x8000 if hirom else 0
    code, nmi = program(first + 0x20, first, last)
    rom[start:start + len(code)] = code
    rom[start + 0x100:start + 0x100 + len(nmi)] = nmi
    header = 0xffc0 if hirom else 0x7fc0
    rom[header:header + 21] = ('RR SAVES ' + name.upper())[:21].ljust(21, ' ').encode('ascii')
    # map, type, 64 KiB ROM, RAM, NTSC, maker, version. The pinned loader takes a board for an S-DD1 only with the
    # extended-header maker byte $33 (as on every real S-DD1 cartridge).
    rom[header + 21:header + 28] = bytes((mode, chip, 6, ram_exp, 1, 0x33 if chip in (0x43, 0x45) else 0, 0))
    vectors = header
    rom[vectors + 0x2a:vectors + 0x2c] = rom[vectors + 0x2e:vectors + 0x30] = (0x8100).to_bytes(2, 'little')   # native NMI, IRQ
    rom[vectors + 0x3a:vectors + 0x3c] = (0x8100).to_bytes(2, 'little')          # emulation-mode NMI
    rom[vectors + 0x3c:vectors + 0x3e] = (0x8000).to_bytes(2, 'little')          # reset
    total = (sum(rom) - sum(rom[header + 28:header + 32]) + 0x1fe) & 0xffff
    rom[header + 28:header + 32] = ((total ^ 0xffff).to_bytes(2, 'little') + total.to_bytes(2, 'little'))
    return bytes(rom)


def boot(exe, battery, folder, tag, frames=20):
    report = folder / (tag + '.json')
    if report.exists():
        report.unlink()
    command = [str(exe), '--frames', str(frames), '--report', str(report)]
    if battery is not None:
        command += ['--cartridge-save', str(battery)]
    done = subprocess.run(command, capture_output=True, text=True, timeout=180)
    return done.returncode, (json.loads(report.read_text()) if report.exists() else None)


def battery_checks(board, exe, folder):
    _name, _mapping, _mode, _chip, _exp, _battery, board_code, first, _last, size = board
    shutil.rmtree(folder / 'persistent', ignore_errors=True)
    battery = folder / 'persistent' / 'deep' / 'cart.rrsram'      # folders that do not exist yet
    code, one = boot(exe, battery, folder, 'first')
    assert code == 0 and one['sram_battery'] == 1 and one['sram_bytes'] == size, (code, one and (one['sram_battery'], one['sram_bytes']))
    raw = battery.read_bytes()
    assert len(raw) == HEADER + size and raw[:8] == b'RRSNRA1' + bytes(1), (len(raw), raw[:8])
    assert int.from_bytes(raw[8:12], 'little') == 1 and int.from_bytes(raw[12:16], 'little') == size
    assert int.from_bytes(raw[16:20], 'little') == CODES[board_code], (int.from_bytes(raw[16:20], 'little'), board_code)

    assert raw[HEADER] == 0xa5 and raw[HEADER + 1] == 0x5a and raw[HEADER + size - 1] == 0x3c, 'markers at both ends of the RAM'
    assert raw[HEADER + 0x20] == 1, 'the counter of the first boot'
    code, two = boot(exe, battery, folder, 'second')
    assert code == 0, code
    raw = battery.read_bytes()
    assert raw[HEADER + 0x20] == 2 and raw[HEADER + size - 1] == 0x3c, 'the second process reads the first one back'
    assert one['sram_hash'] != two['sram_hash']
    # Damaged files never stop the game: each is set aside as <name>.unusable-N, byte for byte, and the game starts with a blank
    # RAM and saves a new file (counter 1). The report says so (save_set_aside).
    damages = {
        'payload byte': lambda b: b[:HEADER + 5] + bytes([b[HEADER + 5] ^ 1]) + b[HEADER + 6:],
        'last payload byte': lambda b: b[:-1] + bytes([b[-1] ^ 0x80]),
        'cartridge identity': lambda b: b[:40] + bytes([b[40] ^ 1]) + b[41:],
        'board code': lambda b: b[:16] + bytes([b[16] ^ 1]) + b[17:],
        'size field': lambda b: b[:12] + bytes([b[12] ^ 1]) + b[13:],
        'format version': lambda b: b[:8] + bytes([b[8] + 1]) + b[9:],
        'magic': lambda b: b'X' + b[1:],
        'one byte missing': lambda b: b[:-1],
        'one byte more': lambda b: b + b'\0',
        'empty file': lambda b: b'',
    }
    for label, damage in damages.items():
        for old in battery.parent.glob(battery.name + '.unusable-*'):
            old.unlink()
        broken = damage(raw)
        battery.write_bytes(broken)
        code, report = boot(exe, battery, folder, 'aside')
        aside = battery.parent / (battery.name + '.unusable-1')
        assert code == 0 and report['save_set_aside'] == 1, (label, code)
        assert aside.read_bytes() == broken, (label, 'the unusable file is kept as it was')
        fresh = battery.read_bytes()
        assert len(fresh) == HEADER + size and fresh[HEADER + 0x20] == 1 and fresh[HEADER:HEADER + 2] == bytes((0xa5, 0x5a)), (
            label, 'a blank start, and a new valid save')
    for old in battery.parent.glob(battery.name + '.unusable-*'):
        old.unlink()
    battery.write_bytes(raw)
    code, three = boot(exe, battery, folder, 'third')
    assert code == 0 and three['save_set_aside'] == 0 and battery.read_bytes()[HEADER + 0x20] == 3, 'a valid file still loads'
    # When the file cannot be set aside (all 99 names taken, the last one a folder), it is left alone and nothing is saved:
    # the game is told so and the command that asked for the save reports it (exit 9).
    broken = damages['payload byte'](raw)
    battery.write_bytes(broken)
    for n in range(1, 99):
        (battery.parent / (battery.name + f'.unusable-{n}')).write_bytes(bytes([n]))
    (battery.parent / (battery.name + '.unusable-99')).mkdir()
    code, _ = boot(exe, battery, folder, 'cannot-aside')
    assert code == 9 and battery.read_bytes() == broken, 'a file that cannot be set aside is never overwritten'
    for old in battery.parent.glob(battery.name + '.unusable-*'):
        old.rmdir() if old.is_dir() else old.unlink()
    leftovers = sorted(path.name for path in battery.parent.iterdir() if path.name != battery.name)
    assert not leftovers, leftovers
    return {'file_bytes': HEADER + size, 'board_code': CODES[board_code], 'counter_after_three_boots': 3,
            'damaged_files_set_aside_and_game_started': len(damages), 'unmovable_file_left_untouched': True,
            'leftover_files': leftovers}


def ram_only_checks(board, exe, folder):
    shutil.rmtree(folder / 'persistent', ignore_errors=True)
    battery = folder / 'persistent' / 'cart.rrsram'
    results = []
    for tag in ('first', 'second'):
        code, report = boot(exe, battery, folder, tag)
        assert code == 0 and report['sram_battery'] == 0, (code, report and report['sram_battery'])
        assert not battery.exists() and not battery.parent.exists(), 'a board without a battery writes nothing'
        results.append(report['sram_hash'])
    assert results[0] == results[1], 'its RAM starts blank at every boot'
    return {'file_written': False, 'sram_hash_equal_across_boots': True}


def main():
    work = ROOT / '.build/snes-saves-check'
    work.mkdir(parents=True, exist_ok=True)
    wanted = set(sys.argv[1:])
    boards = [board for board in BOARDS if not wanted or board[0] in wanted]
    profiles, rows = {}, []
    for board in boards:
        folder = work / board[0]
        folder.mkdir(exist_ok=True)
        path = folder / 'authored.sfc'
        path.write_bytes(cartridge(board))
        rom = read_snes_rom(path)
        profiles[rom.sha256] = {'id': 'fixture-saves-' + board[0], 'title': 'saves', 'legacy_functions': False, 'standard': 'ntsc',
                                'mapping': board[1]}
        rows.append((board, path, folder))
    results = []
    with patch.dict(supernintendo.PROFILES, profiles):
        for board, path, folder in rows:
            exe = prepare16(path, 'snes', title='saves', emit=lambda text: None)
            native = probe16(exe, folder, 40)
            reference = probe16(exe, folder, 40, reference=True)
            differences = reference_differences('snes', native, reference)
            assert not differences, (board[0], differences)
            assert native['sram_bytes'] == (board[9] if board[5] else native['sram_bytes']), native['sram_bytes']
            assert not native['interpreted_opcodes'], native['interpreted_opcodes']
            saves = battery_checks(board, exe, folder) if board[5] else ram_only_checks(board, exe, folder)
            state = state_check(exe, folder / 'state', 13, 11)
            results.append({'board': board[0], 'passed': True, 'native_equals_reference': True, 'saves': saves, 'quick_state': state})
            print(json.dumps(results[-1]), flush=True)
    atomic_json(work / 'results.json', results)
    print(json.dumps({'boards': len(results), 'passed': all(row['passed'] for row in results)}))


if __name__ == '__main__':
    main()
