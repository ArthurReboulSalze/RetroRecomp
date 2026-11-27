"""ROM-free check of the TMS9918A's « sprite flicker reduction » (native/tms9918, the player's F5 on the SG-1000 and the ColecoVision):
native/tms9918_sprite_checks.c proves that off the picture is the chip's four sprites a line, that on the others are drawn behind them,
and that the status byte and everything the program reads are the same either way. Nothing is written outside .build/tms9918-sprites.

    python -B tools/tms9918_sprite_selftest.py
"""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))

import z80_costs_selftest as costs_check  # noqa: E402  (the portable compiler)


def main() -> int:
    build = ROOT / '.build' / 'tms9918-sprites'
    build.mkdir(parents=True, exist_ok=True)
    exe = build / ('tms9918_sprite_checks.exe' if os.name == 'nt' else 'tms9918_sprite_checks')
    costs_check._compile([ROOT / 'native' / 'tms9918_sprite_checks.c', ROOT / 'native' / 'tms9918' / 'tms9918.c'], ROOT / 'native' / 'tms9918', exe)
    ran = subprocess.run([str(exe)], capture_output=True, encoding='utf-8', errors='replace', timeout=120, creationflags=costs_check.FLAGS)
    print(ran.stdout, end='')
    return ran.returncode


if __name__ == '__main__':
    sys.exit(main())
