"""What a game writes to its disks survives, and states are refused when they should be (gates G7 and G6 of the Atari ST).

    python -B tools/atarist_saves_check.py        (needs a compiler, no ROM, no TOS, no game)

Everything here is authored: a tiny TOS image whose program reads sector 3 of track 0 through the machine's real DMA and WD1772
registers, adds one to its first byte, writes the sector back and reads it again, and two floppy images written by this tool for
the purpose: an IPF (the format of the player's library, read by Hatari's IPF path) and a plain .st image (Hatari's sector path).
It runs on the conversion's own reference player, in separate processes, the way a game restarted by a player would:

  1. a first run from the disk as it is written here gives 0x41; the file of the disk's writes appears;
  2. a second process with that file reads 0x41 and writes 0x42 (the save survived without F8/F9);
  3. the image itself never changed, byte for byte;
  4. a damaged file is kept aside as <name>.unusable-1 and the program starts from the disk again (0x41), the game is not blocked;
  5. no file, no --disk-writes: the session keeps the write for itself and leaves nothing behind;
  6. a state saved after the write brings the written sector back in a fresh process (a state holds the disks as they were);
  7. a missing state stops the run with a message and creates nothing; a damaged state and a state of another build are refused.

It shows the persistence of the session and of the controller's write path, not any game's own use of it.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

WORK = ROOT / '.build' / 'atarist-saves-check'
TOS_BYTES = 196608
SECTOR_TRACK, SECTOR_NUMBER = 0, 3
ORIGINAL = 0x40
RESULT = 0x20000       # the program's results in RAM: first byte read back, then the three status registers, then 'D'
FRAMES = 1500
STATE_FRAME = 1400


# ------------------------------------------------------------------------------------------------- the authored program
def _word(*values) -> bytes:
    return b''.join(struct.pack('>H', v & 0xffff) for v in values)


def _long(value: int) -> bytes:
    return struct.pack('>I', value & 0xffffffff)


def move_b(value: int, address: int) -> bytes:
    return _word(0x13fc, value) + _long(address)        # MOVE.B #value,address.L


def move_w(value: int, address: int) -> bytes:
    return _word(0x33fc, value) + _long(address)        # MOVE.W #value,address.L


DMA_DATA, DMA_MODE = 0xff8604, 0xff8606
GPIP = 0xfffa01


def wait_irq() -> bytes:
    """The controller's interrupt line, on the MFP's GPIP bit 5 (low when pending)."""
    return _word(0x0839, 5) + _long(GPIP) + _word(0x66f6)    # BTST #5,$FFFFFA01.L; BNE.S back


def dma_address(address: int) -> bytes:
    return move_b(address >> 16, 0xff8609) + move_b(address >> 8, 0xff860b) + move_b(address, 0xff860d)


def status_to(address: int) -> bytes:
    return move_w(0x080, DMA_MODE) + _word(0x33f9) + _long(DMA_DATA) + _long(address)    # MOVE.W $FF8604.L,address.L


def read_sector(buffer: int) -> bytes:
    return (dma_address(buffer) + move_w(0x190, DMA_MODE) + move_w(0x090, DMA_MODE) + move_w(1, DMA_DATA) +
            move_w(0x084, DMA_MODE) + move_w(SECTOR_NUMBER, DMA_DATA) + move_w(0x080, DMA_MODE) + move_w(0x80, DMA_DATA) + wait_irq())


def write_sector(buffer: int) -> bytes:
    return (dma_address(buffer) + move_w(0x090, DMA_MODE) + move_w(0x190, DMA_MODE) + move_w(1, DMA_DATA) +
            move_w(0x184, DMA_MODE) + move_w(SECTOR_NUMBER, DMA_DATA) + move_w(0x180, DMA_MODE) + move_w(0xa0, DMA_DATA) + wait_irq())


def program() -> bytes:
    buffer, verify = 0x10000, 0x11000
    code = move_b(0x05, 0xff8001)                                           # memory configuration (two banks of 512 KiB), as a TOS does first
    code += _word(0x46fc, 0x2700)                                           # no interrupts: the program polls
    code += _word(0x2e7c) + _long(0x8000)                                   # a stack
    code += move_b(14, 0xff8800) + move_b(5, 0xff8802)                      # drive A, side 0
    code += move_w(0x080, DMA_MODE) + move_w(0x00, DMA_DATA) + wait_irq()   # RESTORE
    code += read_sector(buffer) + status_to(RESULT + 2)
    code += _word(0x0639, 1) + _long(buffer)                                # ADD.B #1,buffer
    code += write_sector(buffer) + status_to(RESULT + 4)
    code += read_sector(verify) + status_to(RESULT + 6)
    code += _word(0x13f9) + _long(verify) + _long(RESULT)                   # MOVE.B verify,result: what the disk now holds
    code += move_b(ord('D'), RESULT + 8)
    code += _word(0x60fe)                                                   # BRA.S *
    return code


def authored_tos() -> bytes:
    tos = bytearray(TOS_BYTES)
    tos[0:4] = bytes((0x60, 0x1e, 0x01, 0x04))              # a branch, TOS version 1.04
    tos[4:8] = _long(0x00fc0020)                            # reset program counter
    tos[8:12] = _long(0x00fc0000)                           # the ROM's base
    code = program()
    tos[0x20:0x20 + len(code)] = code
    return bytes(tos)


# ------------------------------------------------------------------------------------------------- the authored floppies
def _sector_data(track: int, sector: int) -> bytes:
    data = bytearray((track * 3 + sector * 7 + n) & 0xff for n in range(512))
    if (track, sector) == (SECTOR_TRACK, SECTOR_NUMBER):
        data[0] = ORIGINAL
    return bytes(data)


def st_image() -> bytes:
    """Two sides of 80 tracks of 9 sectors; a boot sector with a BPB so that Hatari takes the geometry from it."""
    disk = bytearray(80 * 2 * 9 * 512)
    for track in range(160):
        for sector in range(1, 10):
            disk[track * 9 * 512 + (sector - 1) * 512:track * 9 * 512 + sector * 512] = _sector_data(track // 2 if not track % 2 else 200, sector)
    boot = bytearray(disk[:512])
    boot[11:19] = struct.pack('<HBHBH', 512, 2, 1, 2, 112)
    boot[19:21] = struct.pack('<H', 1440)
    boot[22:28] = struct.pack('<HHH', 5, 9, 2)
    disk[:512] = boot
    return bytes(disk)


def crc_ccitt(data: bytes) -> int:
    crc = 0xffff
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021 if crc & 0x8000 else crc << 1) & 0xffff
    return crc


def _element(kind: int, payload: bytes) -> bytes:
    """A data element of an IPF block: its type, the length in bytes in as few bytes as needed, the bytes."""
    n = len(payload)
    width = 1 if n < 0x100 else 2 if n < 0x10000 else 3
    return bytes(((width << 5) | kind,)) + n.to_bytes(width, 'big') + payload


SYNC, DATA, GAP = 1, 2, 3
A1_CELLS = bytes((0x44, 0x89)) * 3


def _track_blocks(track: int, side: int) -> list[bytes]:
    """The nine sectors of a track, one block each; each element's cells add up to the block's size."""
    blocks = []
    for sector in range(1, 10):
        ident = bytes((0xfe, track, side, sector, 2))
        ident += crc_ccitt(b'\xa1\xa1\xa1' + ident).to_bytes(2, 'big')
        body = b'\xfb' + _sector_data(track if not side else 200, sector)
        body += crc_ccitt(b'\xa1\xa1\xa1' + body).to_bytes(2, 'big')
        tail = b'\x4e' * (850 if sector == 9 else 0)
        blocks.append(_element(GAP, b'\x4e' * 50) + _element(SYNC, A1_CELLS) + _element(DATA, ident) + _element(GAP, b'\x4e' * 22) +
                      _element(SYNC, A1_CELLS) + _element(DATA, body) + (_element(GAP, tail) if tail else b'') + b'\0')
    return blocks


def _cells(track_block: bytes) -> int:
    pos, cells = 0, 0
    while track_block[pos]:
        header = track_block[pos]
        width, kind = header >> 5, header & 0x1f
        n = int.from_bytes(track_block[pos + 1:pos + 1 + width], 'big')
        pos += 1 + width + n
        cells += n * 8 if kind == SYNC else n * 16
    return cells


def _tag(name: bytes, body: bytes) -> bytes:
    size = 12 + len(body)
    head = name + struct.pack('>II', size, 0)
    crc = zlib.crc32(head + body) & 0xffffffff
    return name + struct.pack('>II', size, crc) + body


def ipf_image(cylinders: int = 2) -> bytes:
    """An IPF written for this check (SPS encoder records, as a preservation image has them): two sides, a few cylinders."""
    info = struct.pack('>21I', 1, 2, 1, 0, 0, 0, 0, cylinders - 1, 0, 1, 20261108, 0, 4, 0, 0, 0, 0, 0, 0, 0, 0)
    out = _tag(b'CAPS', b'') + _tag(b'INFO', info)
    for key, (track, side) in enumerate((c, s) for c in range(cylinders) for s in range(2)):
        blocks = _track_blocks(track, side)
        descriptors, offset = [], 32 * len(blocks)
        for block in blocks:
            descriptors.append(struct.pack('>8I', _cells(block), 0, 0, 1, 1, 0, 0, offset))
            offset += len(block)
        payload = b''.join(descriptors) + b''.join(blocks)
        total = sum(_cells(block) for block in blocks)
        out += _tag(b'IMGE', struct.pack('>17I', track, side, 2, 1, (total + 7) // 8, 0, 0, total, 0, total, len(blocks), 0, 0, key + 1, 0, 0, 0))
        crc = zlib.crc32(payload) & 0xffffffff
        data_tag = _tag(b'DATA', struct.pack('>4I', len(payload), len(payload) * 8, crc, key + 1))
        out += data_tag + payload
    # Hatari sizes the disk from the file's length (Floppy_FindDiskDetails, in its controller's track bound): an unknown record, which
    # its reader skips, makes the file as long as a real image.
    return out + _tag(b'PADS', bytes(737280 - len(out) - 12))


# ------------------------------------------------------------------------------------------------------------- the runs
def reference_player() -> Path:
    from retrorecomp.atarist_conversion import machine_core, reference_build, sdk_stamp
    from retrorecomp.platforms import target_id
    from retrorecomp.toolchain import suffix as toolchain_suffix
    from retrorecomp.console16 import dependencies16
    stamp = sdk_stamp()
    base = ROOT / '.build/atarist' / (('win' + toolchain_suffix()) if os.name == 'nt' else 'linux') / stamp[:12]
    base.mkdir(parents=True, exist_ok=True)
    dependencies16('md', print)
    tree, hatari_build = machine_core(base.parent, print)
    return reference_build(base, tree, hatari_build, stamp, print)


def run_once(player: Path, tos: Path, disk: Path, folder: Path, *extra, frames: int = FRAMES, dump_at: int | None = None, expect_exit: int = 0) -> dict:
    folder.mkdir(parents=True, exist_ok=True)
    dump = folder / 'ram.bin'
    env = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy')
    args = [str(player), '--headless', '--frames', str(frames), '--tos', str(tos), '--disk', str(disk), '--machine', 'st', '--memory', '1024',
            '--reference-cpu', '--report', str(folder / 'report.json'), '--ram-dump-at', str(dump_at or frames - 10), '--ram-dump', str(dump), *map(str, extra)]
    done = subprocess.run(args, cwd=folder, env=env, capture_output=True, text=True, timeout=600)
    if done.returncode != expect_exit:
        raise AssertionError(f'{folder.name}: exit {done.returncode} (expected {expect_exit}): {done.stderr[-400:]}')
    if expect_exit:
        return {'stderr': done.stderr}
    ram = dump.read_bytes()
    return {'value': ram[RESULT], 'status': (ram[RESULT + 3], ram[RESULT + 5], ram[RESULT + 7]), 'done': ram[RESULT + 8] == ord('D'),
            'report': json.loads((folder / 'report.json').read_text(encoding='utf-8')), 'stderr': done.stderr}


def check_format(player: Path, tos: Path, name: str, image: bytes) -> list[str]:
    folder = WORK / name
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    disk = folder / f'disk.{name}'
    disk.write_bytes(image)
    writes = folder / 'disk-writes.bin'
    lines = []

    def require(ok: bool, what: str) -> None:
        lines.append(f'{name}: {"ok  " if ok else "FAIL"} {what}')
        if not ok:
            raise AssertionError(f'{name}: {what}')

    first = run_once(player, tos, disk, folder / 'first', '--disk-writes', writes)
    require(first['done'], f"the program finished (status read {first['status'][0]:02x}, write {first['status'][1]:02x}, read back {first['status'][2]:02x})")
    require(first['status'] == (first['status'][0] & ~0x18 & 0xff, first['status'][1] & ~0x18 & 0xff, first['status'][2] & ~0x18 & 0xff),
            'the controller reports neither a missing record nor a CRC error')
    require(first['value'] == ORIGINAL + 1, f'first run: the sector reads back {first["value"]:02x}')
    require(writes.is_file(), 'the file of the disk writes exists')
    second = run_once(player, tos, disk, folder / 'second', '--disk-writes', writes)
    require(second['value'] == ORIGINAL + 2, f'a new process finds the write and adds one: {second["value"]:02x}')
    require(disk.read_bytes() == image, 'the image itself is unchanged')
    # no file asked: nothing is left behind, and the write still reads back within the run
    plain = run_once(player, tos, disk, folder / 'plain')
    require(plain['value'] == ORIGINAL + 1, f'without a file the run starts from the disk: {plain["value"]:02x}')
    require(not list((folder / 'plain').glob('*writes*')), 'without a file nothing is written')
    # a damaged file never blocks the game
    damaged = bytearray(writes.read_bytes())
    damaged[len(damaged) // 2] ^= 0xff
    writes.write_bytes(damaged)
    after = run_once(player, tos, disk, folder / 'damaged', '--disk-writes', writes)
    require(after['value'] == ORIGINAL + 1, f'a damaged file: the program starts from the disk ({after["value"]:02x})')
    require(writes.with_name(writes.name + '.unusable-1').is_file(), 'the damaged file is kept aside')
    # states
    slot = folder / 'state.rrstate'
    saved = run_once(player, tos, disk, folder / 'save', '--state-slot', slot, '--state-save-at', STATE_FRAME)
    require(saved['done'] and slot.is_file(), 'a state is saved after the write')
    resumed_writes = folder / 'resumed-writes.bin'
    loaded = run_once(player, tos, disk, folder / 'load', '--state-slot', slot, '--state-load-start', '--disk-writes', resumed_writes, frames=40, dump_at=STATE_FRAME + 20)
    require(loaded['value'] == ORIGINAL + 1 and resumed_writes.is_file(), 'a state brings the written sector back in a fresh process')
    missing = folder / 'missing.rrstate'
    gone = run_once(player, tos, disk, folder / 'missing', '--state-slot', missing, '--state-load-start', expect_exit=1)
    require('could not be loaded' in gone['stderr'] and not missing.exists(), 'a missing state is refused and creates nothing')
    blob = bytearray(slot.read_bytes())
    blob[len(blob) // 2] ^= 0xff
    bad = folder / 'bad.rrstate'
    bad.write_bytes(blob)
    bad_run = run_once(player, tos, disk, folder / 'bad', '--state-slot', bad, '--state-load-start', expect_exit=1)
    require('could not be loaded' in bad_run['stderr'], 'a damaged state is refused before the machine is touched')
    other = bytearray(slot.read_bytes())
    first_line = other.index(b'\n') + 1
    other[first_line] ^= 1      # another build's identity
    foreign = folder / 'foreign.rrstate'
    foreign.write_bytes(other)
    foreign_run = run_once(player, tos, disk, folder / 'foreign', '--state-slot', foreign, '--state-load-start', expect_exit=1)
    require('could not be loaded' in foreign_run['stderr'], "a state of another build is refused")
    return lines


def main() -> int:
    os.environ.setdefault('RETRO_RECOMP_TOOLCHAIN', 'llvm')
    player = reference_player()
    WORK.mkdir(parents=True, exist_ok=True)
    tos = WORK / 'tos.img'
    tos.write_bytes(authored_tos())
    failed = False
    for name, image in (('ipf', ipf_image()), ('st', st_image())):
        try:
            for line in check_format(player, tos, name, image):
                print(line)
        except AssertionError as error:
            print('FAIL', error)
            failed = True
    print('FAILED' if failed else 'OK')
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
