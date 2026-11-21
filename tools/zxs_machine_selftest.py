"""ROM-free check of the ZX Spectrum machine core (native/zxs_machine/zxs_machine.c, built with native/zxs_machine/zxs_machine_checks.c).

Writes three authored machine images through the converter's own writer (retrorecomp/zxs_build.zxs_image: a 48K, a 128K with bank 3
and ROM 1 paged, a 16K), builds the checks with a C compiler and runs them: the memory map and the 128K paging with its lock, the frame
length and the /INT pulse, the keyboard half-rows, the Kempston port, the picture (border, paper, ink, bright, flash), the beeper's
samples, the AY's registers, the 16K's missing RAM. No ROM and no game: the "ROM" is a byte pattern. Nothing is written outside
.build/zxs-machine-selftest.
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def compiler() -> str:
    try:
        from retrorecomp import toolchain
        candidate = toolchain.tools_directory() / 'llvm-mingw' / 'bin' / ('clang.exe' if os.name == 'nt' else 'clang')
        if candidate.is_file():
            return str(candidate)
    except Exception:
        pass
    for name in ('clang', 'gcc', 'cc'):
        found = shutil.which(name)
        if found:
            return found
    raise SystemExit('No C compiler found.')


def authored_banks() -> dict:
    """Bank n holds n everywhere; bank 5 holds a screen with three authored cells on its first row."""
    banks = {bank: bytearray([bank]) * 0x4000 for bank in range(8)}
    screen = banks[5]
    screen[0x0000] = 0x80          # paper line 0, column 0: the leftmost pixel set
    screen[0x0100] = 0x01          # paper line 1, column 0: the rightmost pixel set
    screen[0x0001] = 0x00          # column 1: no pixel (its paper shows, bright)
    screen[0x0002] = 0xF0          # column 2: four pixels set (flash)
    screen[0x1800] = 0x2A          # ink 2, paper 5
    screen[0x1801] = 0x68          # bright, paper 5
    screen[0x1802] = 0xAA          # flash, ink 2, paper 5
    return {bank: bytes(data) for bank, data in banks.items()}


def image(model: str, port_7ffd=None) -> bytes:
    from retrorecomp.zxs_build import zxs_image
    from retrorecomp.zxs_snapshot import Snapshot
    registers = {'af': 0, 'bc': 0, 'de': 0, 'hl': 0, 'af_': 0, 'bc_': 0, 'de_': 0, 'hl_': 0, 'ix': 0, 'iy': 0,
                 'sp': 0xFF00, 'pc': 0x8000, 'i': 0x3F, 'r': 0, 'im': 1, 'iff1': 0, 'iff2': 0}
    banks = authored_banks()
    if model == '16k':
        banks = {5: banks[5]}
    elif model == '48k':
        banks = {bank: banks[bank] for bank in (5, 2, 0)}
    snapshot = Snapshot(path=Path('authored'), data=b'', sha256='', format='z80', version=3, model=model, hardware=model,
                        registers=registers, border=7, port_7ffd=port_7ffd, ay_select=None, ay_registers=None,
                        joystick='cursor', tstates=0, banks=banks)
    return zxs_image(snapshot)


def main() -> int:
    work = ROOT / '.build' / 'zxs-machine-selftest'
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    files = []
    for name, model, port in (('image48.bin', '48k', None), ('image128.bin', '128k', 0x13), ('image16.bin', '16k', None)):
        (work / name).write_bytes(image(model, port))
        files.append(str(work / name))
    source = ROOT / 'native' / 'zxs_machine'
    exe = work / ('zxs_machine_checks.exe' if os.name == 'nt' else 'zxs_machine_checks')
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    built = subprocess.run([compiler(), '-std=gnu11', '-O1', '-Wall', '-Wextra', '-I', str(source),
                            str(source / 'zxs_machine.c'), str(source / 'zxs_machine_checks.c'), '-o', str(exe)],
                           capture_output=True, encoding='utf-8', errors='replace', creationflags=flags)
    if built.returncode:
        print(built.stdout + built.stderr)
        return 2
    ran = subprocess.run([str(exe), *files], capture_output=True, encoding='utf-8', errors='replace', timeout=120,
                         creationflags=flags)
    print(ran.stdout.strip())
    return ran.returncode


if __name__ == '__main__':
    sys.exit(main())
