"""The hardware tests of JaCzekanski/ps1-tests on the PlayStation machine (gate G11: named behaviours, not the chips).

    python tools/psx_hardware_selftest.py FOLDER [--work DIR] [--only gpu/triangle ...]

FOLDER holds `ps1-tests-build158/tests.zip`, the suite's prebuilt release (build-158, commit 5f73d61b, MIT), whose programs and
expected results are read from the archive (the expected results were recorded on a console by the suite's authors: `vram.png`,
the whole VRAM at the end of a GPU test; `psx.log`, what a test prints). Nothing of the suite is copied into the repository or a
release; the archive's Windows tool (tools/diffvram) is never extracted.

Each program runs on Beetle PSX prepared exactly as a conversion prepares it (`psx_beetle.adapt`), interpreted, headless, through
`native/psx_vector_checks/psx_hardware.c`, with the player's BIOS (--bios). It boots as a game boots: from a small disc this tool
builds around it (`disc_for`: a licensed volume whose SYSTEM.CNF names it, with the EDC and ECC of every sector, which Beetle checks),
so it starts after the BIOS's own start-up, and the CD-ROM tests have a disc in the drive. It runs a fixed number of frames with no
input; what it prints through the BIOS and the VRAM at the end are kept. A VRAM test counts the pixels equal to the reference (5 bits a
component, the mask bit apart) in the whole VRAM and in the area the tests draw in; a log test counts the lines equal to the
reference's from the test's own first line. Tests that print cycle counts measured on the console (timers, DMA, CD-ROM timing)
differ wherever the machine's timing differs; the disc-swap test needs the lid opened, which no input here does.
The result is `FOLDER/../psx-hardware/hardware.json` (or under --work). A count is a measurement of named behaviours of the
machine against a console's output, not a statement about the chips.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ARCHIVE = 'ps1-tests-build158/tests.zip'
ARCHIVE_SHA256 = '5de0e82854c1a511697a7ade381c2d778ec4b2fff4a7d7ac79e8098c35eb859b'
ARCHIVE_BYTES = 6613816
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0
TEST_AREA = (320, 240)          # the display area every GPU test of the suite draws in, from (0, 0)
# (test folder in the archive, frames to run). Every test of the GPU, timer, DMA and CD-ROM folders that has an expected result.
TESTS = (
    ('gpu/clipping', 2400), ('gpu/clut-cache', 2400), ('gpu/lines', 2400), ('gpu/quad', 2400), ('gpu/rectangles', 2400),
    ('gpu/texture-flip', 2400), ('gpu/texture-overflow', 2400), ('gpu/transparency', 2400), ('gpu/triangle', 2400),
    ('gpu/uv-interpolation', 2400), ('gpu/vram-to-vram-overlap', 2400),
    ('gpu/bandwidth', 3600), ('gpu/gp0-e1', 2400), ('gpu/mask-bit', 2400),
    ('timers', 3600),
    ('dma/chain-looping', 2400), ('dma/chopping', 2400), ('dma/dpcr', 2400), ('dma/otc-test', 2400),
    ('cdrom/getloc', 3600), ('cdrom/disc-swap', 3600), ('cdrom/timing', 3600),
)


def cmake_project(checks: Path, tree: Path) -> str:
    cpu = '${RR_BEETLE_TREE}/mednafen/psx/cpu.c'
    return '\n'.join([
        'cmake_minimum_required(VERSION 3.20)',
        'project(RetroPsxHardware LANGUAGES C)',
        'set(CMAKE_C_STANDARD 99)',
        f'set(RR_BEETLE_TREE "{tree.as_posix()}")',
        'include("${RR_BEETLE_TREE}/rr_sources.cmake")',
        f'list(REMOVE_ITEM RR_BEETLE_SOURCES "{cpu}")',
        'add_library(rr_beetle STATIC ${RR_BEETLE_SOURCES})',
        'target_include_directories(rr_beetle PUBLIC ${RR_BEETLE_INCLUDES} "${RR_BEETLE_TREE}")',
        'target_compile_definitions(rr_beetle PUBLIC ${RR_BEETLE_DEFINES})',
        'target_compile_options(rr_beetle PRIVATE -O2 -w -fwrapv -fno-strict-aliasing -fno-fast-math)',
        f'add_library(rr_cpu_observe STATIC "{cpu}")',
        'target_link_libraries(rr_cpu_observe PUBLIC rr_beetle)',
        'target_compile_definitions(rr_cpu_observe PRIVATE RR_PSX_OBSERVE)',
        'target_compile_options(rr_cpu_observe PRIVATE -O2 -w -fwrapv -fno-strict-aliasing -fno-fast-math)',
        f'add_executable(psx_hardware "{(checks / "psx_hardware.c").as_posix()}" '
        f'"{(ROOT / "native" / "psx_machine" / "psx_session.c").as_posix()}")',
        f'target_include_directories(psx_hardware PRIVATE "{(ROOT / "native" / "psx_machine").as_posix()}")',
        'target_compile_options(psx_hardware PRIVATE -O2 -w -fno-fast-math)',
        'target_link_libraries(psx_hardware PRIVATE rr_cpu_observe rr_beetle)',
        'if(NOT WIN32)', '  target_link_libraries(psx_hardware PRIVATE m)', 'endif()',
        '']) + '\n'


def build(work: Path) -> Path:
    from retrorecomp import psx_beetle
    from retrorecomp.core import run, toolchain
    from retrorecomp.platforms import build_jobs, cmake_target_args, build_executable
    cmake, generator = toolchain()
    tree = psx_beetle.adapt(psx_beetle.source(print), work / 'machine')
    project, binary, log = work / 'project', work / 'project' / 'build', work / 'build.log'
    project.mkdir(parents=True, exist_ok=True)
    log.write_text('', encoding='utf-8')
    (project / 'CMakeLists.txt').write_text(cmake_project(ROOT / 'native' / 'psx_vector_checks', tree), encoding='utf-8')
    run([cmake, '-S', project, '-B', binary, '-G', generator, *cmake_target_args()], log=log, timeout=900)
    run([cmake, '--build', binary, '--target', 'psx_hardware', '--parallel', build_jobs()], log=log, timeout=3600)
    return build_executable(binary, 'psx_hardware')


LICENCE = b'          Licensed  by          Sony Computer Entertainment Amer  ica '


def _bcd(n: int) -> int:
    return (n // 10) << 4 | n % 10


def _dir_record(name: bytes, lba: int, size: int, directory: bool = False) -> bytes:
    length = 33 + len(name) + (len(name) + 1) % 2
    rec = bytearray(length)
    rec[0] = length
    struct.pack_into('<I', rec, 2, lba)
    struct.pack_into('>I', rec, 6, lba)
    struct.pack_into('<I', rec, 10, size)
    struct.pack_into('>I', rec, 14, size)
    rec[25] = 2 if directory else 0
    struct.pack_into('<H', rec, 28, 1)
    struct.pack_into('>H', rec, 30, 1)
    rec[32] = len(name)
    rec[33:33 + len(name)] = name
    return bytes(rec)


# The error detection and correction of a Mode 2 Form 1 sector (ECMA-130): Beetle reads the sectors it inspects itself (SYSTEM.CNF, for
# the region string the drive gives the BIOS) through a check of both, so a sector without them makes an unlicensed disc.
def _edc_table() -> list:
    table = []
    for i in range(256):
        edc = i
        for _ in range(8):
            edc = (edc >> 1) ^ (0xD8018001 if edc & 1 else 0)
        table.append(edc)
    return table


def _ecc_tables() -> tuple:
    forward, backward = [0] * 256, [0] * 256
    for i in range(256):
        j = ((i << 1) ^ (0x11D if i & 0x80 else 0)) & 0xFF
        forward[i] = j
        backward[i ^ j] = i
    return forward, backward


EDC_TABLE = _edc_table()
ECC_FORWARD, ECC_BACKWARD = _ecc_tables()


def _ecc(area: bytearray, majors: int, minors: int, major_mult: int, minor_inc: int, at: int) -> None:
    size = majors * minors
    for major in range(majors):
        index = (major >> 1) * major_mult + (major & 1)
        a = b = 0
        for _ in range(minors):
            value = area[index]
            index += minor_inc
            if index >= size:
                index -= size
            a ^= value
            b ^= value
            a = ECC_FORWARD[a]
        a = ECC_BACKWARD[ECC_FORWARD[a] ^ b]
        area[at + major] = a
        area[at + major + majors] = a ^ b


def _form1(payload: bytes) -> bytes:
    """The 2,340 bytes after the sync and the header of a Mode 2 Form 1 sector: subheader, data, EDC, P and Q parity (the header
    counts as zero for both, so every sector of the same data has the same tail)."""
    body = bytearray(4) + bytes((0, 0, 8, 0)) * 2 + payload.ljust(2048, b'\0') + bytes(4 + 276)
    edc = 0
    for value in body[4:4 + 8 + 2048]:
        edc = EDC_TABLE[(edc ^ value) & 0xFF] ^ (edc >> 8)
    struct.pack_into('<I', body, 4 + 8 + 2048, edc)
    _ecc(body, 86, 24, 2, 86, 2076 - 12)
    _ecc(body, 52, 43, 86, 88, 2248 - 12)
    return bytes(body[4:])


def disc_for(program: bytes, folder: Path) -> Path:
    """A small PlayStation disc that boots `program` the way a game boots (CUE + MODE2/2352 BIN): the licence at sector 4, the volume
    descriptor at 16 with its path table at 19, the root at 18, SYSTEM.CNF and SLUS_999.99 from 20 (a serial of the
    SLUS form: Beetle gives the drive the region string SCEA from the BOOT line, the BIOS's check of a licensed disc). The BIOS reads SYSTEM.CNF and loads
    the executable itself, so the program starts after the BIOS's own start-up, as on a console."""
    from retrorecomp.psx_disc import SECTOR, SYNC, USER
    cnf = b'BOOT = cdrom:\\SLUS_999.99;1\r\nTCB = 4\r\nEVENT = 10\r\nSTACK = 801FFFF0\r\n'
    files = [(b'SYSTEM.CNF;1', cnf), (b'SLUS_999.99;1', program)]
    sectors = {4: LICENCE}
    lba = 20
    records = [_dir_record(b'\0', 18, USER, True), _dir_record(b'\1', 18, USER, True)]
    for name, data in files:
        records.append(_dir_record(name, lba, len(data)))
        for i in range(0, len(data), USER):
            sectors[lba] = data[i:i + USER]
            lba += 1
    count = max(lba + 150, 4500)          # about a minute: a disc much shorter than any real one is not read by the BIOS
    pvd = bytearray(USER)
    pvd[0], pvd[1:6], pvd[6] = 1, b'CD001', 1
    pvd[8:40] = b'PLAYSTATION'.ljust(32)
    pvd[40:72] = b'PS1TESTS'.ljust(32)
    struct.pack_into('<I', pvd, 80, count)
    struct.pack_into('>I', pvd, 84, count)
    struct.pack_into('<H', pvd, 120, 1)
    struct.pack_into('>H', pvd, 122, 1)
    struct.pack_into('<H', pvd, 124, 1)
    struct.pack_into('>H', pvd, 126, 1)
    struct.pack_into('<H', pvd, 128, USER)
    struct.pack_into('>H', pvd, 130, USER)
    path_table = bytes((1, 0)) + struct.pack('<IH', 18, 1) + b'\0\0'
    struct.pack_into('<I', pvd, 132, len(path_table))
    struct.pack_into('>I', pvd, 136, len(path_table))
    struct.pack_into('<I', pvd, 140, 19)
    struct.pack_into('>I', pvd, 148, 19)
    pvd[156:190] = _dir_record(b'\0', 18, USER, True)
    pvd[881] = 1
    sectors[16] = bytes(pvd)
    sectors[17] = bytes((255,)) + b'CD001' + bytes((1,))
    sectors[18] = b''.join(records)
    sectors[19] = path_table
    raw = bytearray()
    tails = {}
    for n in range(count):
        frames = n + 150
        head = SYNC + bytes((_bcd(frames // 4500), _bcd(frames // 75 % 60), _bcd(frames % 75), 2))
        payload = sectors.get(n, b'')
        if payload not in tails:
            tails[payload] = _form1(payload)
        raw += head + tails[payload]
    (folder / 'test.bin').write_bytes(bytes(raw))
    cue = folder / 'test.cue'
    cue.write_text('FILE "test.bin" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n', encoding='ascii', newline='\n')
    return cue


def pack_for(program: Path, pack: Path) -> Path:
    """A pack of a disc that boots the program (`disc_for`), as a conversion packs a player's disc."""
    from retrorecomp import psx_pack
    return psx_pack.write_in_place(disc_for(program.read_bytes(), pack.parent), pack)


def vram_match(vram: bytes, png: Path) -> dict:
    from PIL import Image
    image = Image.open(png).convert('RGB')
    if image.size != (1024, 512):
        return {'error': f'reference is {image.size[0]}x{image.size[1]}'}
    reference = image.tobytes()
    equal = in_area = 0
    for i in range(1024 * 512):
        p = vram[2 * i] | vram[2 * i + 1] << 8
        r, g, b = reference[3 * i] >> 3, reference[3 * i + 1] >> 3, reference[3 * i + 2] >> 3
        same = (p & 31) == r and (p >> 5 & 31) == g and (p >> 10 & 31) == b
        equal += same
        in_area += same and i % 1024 < TEST_AREA[0] and i // 1024 < TEST_AREA[1]
    # The whole VRAM, and the area the tests draw in (what lies outside it is what the console's VRAM held before: not the test's).
    area = TEST_AREA[0] * TEST_AREA[1]
    return {'pixels': 1024 * 512, 'equal': equal, 'percent': round(100.0 * equal / (1024 * 512), 3),
            'test_area': {'pixels': area, 'equal': in_area, 'percent': round(100.0 * in_area / area, 3)}}


def log_match(printed: str, expected: str) -> dict:
    ours = [line.rstrip() for line in printed.replace('\r', '').split('\n')]
    theirs = [line.rstrip() for line in expected.replace('\r', '').split('\n')]
    while ours and not ours[-1]:
        ours.pop()
    while theirs and not theirs[-1]:
        theirs.pop()
    # Ours starts with what the BIOS prints while it boots the disc: the comparison starts at the test's own first line.
    if theirs and theirs[0] in ours:
        ours = ours[ours.index(theirs[0]):]
    equal = sum(1 for a, b in zip(ours, theirs) if a == b)
    first = next((n for n, (a, b) in enumerate(zip(ours, theirs)) if a != b), None)
    return {'lines_expected': len(theirs), 'lines_printed': len(ours), 'equal': equal,
            'first_difference': None if first is None else {'line': first + 1, 'expected': theirs[first], 'printed': ours[first]}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('folder', type=Path)
    parser.add_argument('--work', type=Path)
    parser.add_argument('--only', nargs='*')
    parser.add_argument('--bios', type=Path, help="the player's BIOS (Beetle starts a PS-X EXE through the console's BIOS)")
    arguments = parser.parse_args()
    archive = arguments.folder / ARCHIVE
    data = archive.read_bytes()
    if len(data) != ARCHIVE_BYTES or hashlib.sha256(data).hexdigest() != ARCHIVE_SHA256:
        raise SystemExit(f'{archive}: not the pinned ps1-tests build-158 archive.')
    work = (arguments.work or arguments.folder.parent / 'psx-hardware').resolve()
    work.mkdir(parents=True, exist_ok=True)
    tool = build(work)
    suite = zipfile.ZipFile(archive)
    names = set(suite.namelist())
    results = {}
    for test, frames in TESTS:
        if arguments.only and test not in arguments.only:
            continue
        folder = work / 'runs' / test.replace('/', '-')
        folder.mkdir(parents=True, exist_ok=True)
        program = folder / 'test.exe'
        program.write_bytes(suite.read(f'{test}/{test.split("/")[-1]}.exe'))
        pack = pack_for(program, folder / 'test.rrpack')
        tty, vram = folder / 'tty.txt', folder / 'vram.bin'
        bios = ['--bios', str(arguments.bios)] if arguments.bios else []
        result = subprocess.run([str(tool), '--pack', str(pack), '--frames', str(frames), '--tty', str(tty), '--vram', str(vram), *bios],
                                cwd=folder, capture_output=True, text=True, timeout=3600, creationflags=NO_WINDOW)
        row = {'frames': frames, 'exit': result.returncode, 'stderr': result.stderr.strip()[-200:]}
        if f'{test}/vram.png' in names and vram.is_file():
            (folder / 'vram.png').write_bytes(suite.read(f'{test}/vram.png'))
            row['vram'] = vram_match(vram.read_bytes(), folder / 'vram.png')
        if f'{test}/psx.log' in names and tty.is_file():
            row['log'] = log_match(tty.read_text(encoding='latin-1'), suite.read(f'{test}/psx.log').decode('latin-1'))
        results[test] = row
        print(test, json.dumps({k: v for k, v in row.items() if k != 'stderr'}), flush=True)
    (work / 'hardware.json').write_text(json.dumps({'archive_sha256': ARCHIVE_SHA256, 'tests': results}, indent=2),
                                        encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
