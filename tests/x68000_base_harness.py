"""Builds an authored C harness against files of the X68000 machine base, as tools/x68000_base74.py adapts them.

The adapted base is generated from the pinned hissorii/px68k checkout into a temporary folder (the checkout is only
read); the harness and the chosen adapted sources are compiled with the project's own toolchain. Nothing here needs a
ROM, a disk or firmware. A test that uses it skips when the pinned checkouts or the toolchain are missing.
"""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PX68K = ROOT / '.deps/px68k-hissorii'
GEOLITH = ROOT / '.deps/geolith-libretro'
MACHINE = ROOT / 'native/x68000_machine'


def parse(output):
    """Lines of "name key=value ..." printed by a harness, as {name: {key: value}}."""
    cases = {}
    for line in output.splitlines():
        name, *fields = line.split()
        cases[name] = {key: value for key, value in (field.split('=') for field in fields)}
    return cases


def build_and_run(harness, adapted, extra=()):
    """Compile tests/<harness> with the adapted base files `adapted` (like 'x68k/dmac.c'); return (temp, cases).

    The caller keeps the returned temporary folder alive for as long as it needs the build and cleans it up.
    """
    from retrorecomp.core import toolchain, ConversionError
    from retrorecomp.platforms import build_executable, cmake_target_args
    from tools import x68000_base74
    if not (PX68K / 'x68k/dmac.c').is_file() or not GEOLITH.is_dir():
        raise unittest.SkipTest('Pinned px68k-hissorii or Geolith checkout unavailable')
    try:
        cmake, generator = toolchain()
    except ConversionError as exc:
        raise unittest.SkipTest(str(exc))
    temp = tempfile.TemporaryDirectory(prefix='rr-x68000-base-')
    project = Path(temp.name)
    base = project / 'base'
    x68000_base74.generate(PX68K, PX68K, base, GEOLITH)
    sources = ' '.join(f'"{(base / name).as_posix()}"' for name in adapted)
    extra_sources = ' '.join(f'"{Path(name).as_posix()}"' for name in extra)
    (project / 'CMakeLists.txt').write_text(
        'cmake_minimum_required(VERSION 3.20)\n'
        'project(BaseFixtures LANGUAGES C)\n'
        'set(CMAKE_C_STANDARD 11)\n'
        f'add_executable(base-test "{ROOT.as_posix()}/tests/{harness}" {sources} {extra_sources}'
        f' "{MACHINE.as_posix()}/state/rr_state.c")\n'
        'target_include_directories(base-test PRIVATE\n'
        f' "{MACHINE.as_posix()}/base74/x11" "{MACHINE.as_posix()}/base74/alias"\n'
        f' "{MACHINE.as_posix()}/base74/alias/x68k" "{MACHINE.as_posix()}/base74/alias/libretro"\n'
        f' "{MACHINE.as_posix()}/base74/alias/m68000" "{MACHINE.as_posix()}/state"\n'
        f' "{base.as_posix()}/x68k" "{base.as_posix()}/m68000" "{base.as_posix()}/x11src")\n'
        'target_compile_definitions(base-test PRIVATE NO_MERCURY HAVE_MUSASHI _CRT_SECURE_NO_WARNINGS)\n'
        'if(NOT MSVC)\n'
        'target_compile_options(base-test PRIVATE -w)\n'
        'endif()\n', encoding='utf-8')
    for command in (
        [str(cmake), '-S', str(project), '-B', str(project / 'build'), '-G', generator, *cmake_target_args()],
        [str(cmake), '--build', str(project / 'build'), '--config', 'Release'],
    ):
        compiled = subprocess.run(command, capture_output=True, text=True)
        if compiled.returncode:
            temp.cleanup()
            raise RuntimeError(compiled.stdout + compiled.stderr)
    binary = build_executable(project / 'build', 'base-test')
    run = subprocess.run([str(binary)], capture_output=True, text=True, check=True)
    return temp, parse(run.stdout)
