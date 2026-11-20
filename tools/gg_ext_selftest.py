"""ROM-free checks of the Game Gear EXT port and the Gear-to-Gear cable model (native/gg_ext.h).

Builds native/gg_ext_checks.c with the portable clang (or the first C compiler found) and runs it: two contexts, an authored
sequence of port accesses at given cycles, and what the other end must see and when (serial timing, the receive NMI, the
swapped parallel lines, the PC6 NMI, the named-field state). No ROM, no window, nothing written outside .build/.
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


def main() -> int:
    build = ROOT / '.build' / 'gg-ext-selftest'
    build.mkdir(parents=True, exist_ok=True)
    exe = build / ('gg_ext_checks.exe' if os.name == 'nt' else 'gg_ext_checks')
    command = [compiler(), '-std=c11', '-Wall', '-Wextra', '-Werror', '-O1', '-I', str(ROOT / 'native'),
               str(ROOT / 'native' / 'gg_ext_checks.c'), '-o', str(exe)]
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    built = subprocess.run(command, capture_output=True, encoding='utf-8', errors='replace', creationflags=flags)
    if built.returncode:
        print(built.stdout + built.stderr)
        return 1
    ran = subprocess.run([str(exe)], capture_output=True, encoding='utf-8', errors='replace', timeout=60, creationflags=flags)
    print(ran.stdout.strip())
    return ran.returncode


if __name__ == '__main__':
    sys.exit(main())
