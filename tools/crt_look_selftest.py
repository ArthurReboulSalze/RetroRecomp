"""The CRT and LCD looks (HOST_KIT D35) without a window (needs a C compiler and the pinned SDL2).

    python -B tools/crt_look_selftest.py

Builds `native/crt_look_checks.c` and runs it: the overlays' values (beams, mask, frame, LCD grid), the curve solved back,
F3's cycle with and without an LCD screen, then whole looks drawn by SDL's software renderer onto a surface, the light way and
the full way, twice each (the same picture), nothing outside the picture's rectangle, the curved corner black.
"""
from __future__ import annotations
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tools/, also when imported as tools.<name>
from selftest_build import compile_and_run


def run_checks(project: Path | None = None) -> dict:
    project = project or ROOT / '.build' / 'crt-look-selftest'
    project.mkdir(parents=True, exist_ok=True)
    output = compile_and_run(project, ROOT / 'native/crt_look_checks.c', requires_sdl=True, sdl_config=None,
                             include_dirs=(ROOT / 'native',), link_libraries=('SDL2::SDL2-static',), timeout=120)
    return json.loads(next(line for line in output.splitlines() if line.startswith('{')))


def main() -> int:
    result = run_checks()
    print(f'{result["passed"]} checks passed, {result["failed"]} failed')
    return 0 if not result['failed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
