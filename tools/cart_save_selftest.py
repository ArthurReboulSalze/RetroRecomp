"""ROM-free checks of the cartridge save file the Mega Drive, the Super Nintendo and the PC Engine share (native/cart_save.c).

Each machine's own entry points (md_battery.c, snes_battery.c, pce_backup.c) are built with native/cart_save_checks.c over a
stand-in memory, with the project's toolchain, and run in a scratch folder: a fresh save, a reload, every kind of file that is not
a good one (empty, short, long, another cartridge, a changed byte...), a folder where the file should be, a file where a folder
should be, read-only files, the ninety-nine names taken, the cases where saving is off. The program checks the files against its
own writer of the format and prints a log of every observable result and every byte left on disk.

    python tools/cart_save_selftest.py                  # the tree as it is
    python tools/cart_save_selftest.py --against REV    # the same, then the sources of REV (for example HEAD): the logs must be equal

Windows only (the checks use the Win32 file calls). Nothing is written outside .build/cart-save-selftest."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

WORK = ROOT / '.build/cart-save-selftest'
# What each machine's save is made of: the machine's own file and, once it exists, the shared one (a revision before the shared
# file leaves it out).
SOURCES = {'md': ('md_battery.c', 'cart_save.c'), 'snes': ('snes_battery.c', 'cart_save.c'), 'pce': ('pce_backup.c', 'cart_save.c')}
HEADERS = ('md_battery.h', 'snes_battery.h', 'pce_backup.h', 'cart_save.h')
DEFINE = {'md': 'CS_MD', 'snes': 'CS_SNES', 'pce': 'CS_PCE'}

STUBS = {
    'retro16_state_config.h': '#pragma once\n#define RR16_STATE_NAME "Authored Cartridge"\n#define RR16_STATE_ROM "' + 'ab' * 32 + '"\n',
    'video/genesis_bus.h': '''#pragma once
#include <stdint.h>
typedef struct GenesisBus {
    uint8_t  sram[0x10000];
    uint32_t sram_base, sram_end, sram_size;
    uint8_t  sram_present, sram_enabled, sram_stride, sram_battery;
} GenesisBus;
''',
    'snes/cart.h': '''#pragma once
#include <stdint.h>
typedef struct Cart { int type; uint8_t *ram; uint32_t ramSize; } Cart;
''',
    'pce_machine.h': '''#pragma once
#include <stdint.h>
#define PCE_BACKUP_BYTES 2048u
const uint8_t *pce_machine_backup(void);
void pce_machine_set_backup(const uint8_t data[PCE_BACKUP_BYTES]);
''',
}


def revision_sources(revision: str, folder: Path) -> Path:
    """The save files of one revision, taken from git (the ones that exist there)."""
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    for name in {*(n for names in SOURCES.values() for n in names), *HEADERS}:
        shown = subprocess.run(['git', 'show', f'{revision}:native/{name}'], cwd=ROOT, capture_output=True)
        if shown.returncode == 0:
            (folder / name).write_bytes(shown.stdout)
    return folder


def build(label: str, sources: Path, only: tuple) -> dict:
    """One program per machine from `sources` (the tree's native folder or a revision's files)."""
    from retrorecomp.core import run, toolchain
    from retrorecomp.platforms import build_executable, cmake_target_args
    project = WORK / label
    shutil.rmtree(project, ignore_errors=True)
    for name, text in STUBS.items():
        (project / 'stubs' / name).parent.mkdir(parents=True, exist_ok=True)
        (project / 'stubs' / name).write_bytes(text.encode('ascii'))
    shutil.copy2(ROOT / 'native/cart_save_checks.c', project / 'cart_save_checks.c')
    lines = ['cmake_minimum_required(VERSION 3.20)', 'project(CartSaveChecks C)', 'set(CMAKE_C_STANDARD 11)']
    for machine in only:
        files = [name for name in SOURCES[machine] if (sources / name).is_file()]
        listed = ' '.join(f'"{(sources / name).as_posix()}"' for name in files)
        lines += [f'add_executable(checks_{machine} cart_save_checks.c {listed})',
                  f'target_compile_definitions(checks_{machine} PRIVATE {DEFINE[machine]}=1)',
                  f'target_include_directories(checks_{machine} PRIVATE stubs "{sources.as_posix()}" "{(ROOT / "native").as_posix()}")']
    (project / 'CMakeLists.txt').write_text('\n'.join(lines) + '\n', encoding='ascii', newline='\n')
    cmake, generator = toolchain()
    run([cmake, '-S', project, '-B', project / 'build', '-G', generator, *cmake_target_args()], log=project / 'build.log')
    run([cmake, '--build', project / 'build', '--config', 'Release', '--parallel', '4'], log=project / 'build.log')
    return {machine: build_executable(project / 'build', f'checks_{machine}') for machine in only}


def execute(executable: Path) -> tuple:
    with tempfile.TemporaryDirectory(prefix='rr-cart-save-') as temp:
        done = subprocess.run([str(executable), temp], capture_output=True, text=True, timeout=600)
    return done.returncode, done.stdout


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--against', metavar='REV', help='also build the save files of this revision and require the same log')
    parser.add_argument('--machine', choices=sorted(SOURCES), action='append', help='only these machines (default: all)')
    args = parser.parse_args()
    if sys.platform != 'win32':
        print(json.dumps({'skipped': 'the checks use the Win32 file calls'}))
        return 0
    machines = tuple(args.machine or sorted(SOURCES))
    WORK.mkdir(parents=True, exist_ok=True)
    runs = {'tree': build('tree', ROOT / 'native', machines)}
    if args.against:
        runs[args.against] = build('revision', revision_sources(args.against, WORK / 'revision-sources'), machines)
    result, logs, failed = {}, {}, False
    for label, executables in runs.items():
        for machine, executable in executables.items():
            code, log = execute(executable)
            logs[label, machine] = log
            entry = result.setdefault(machine, {})
            entry[label] = {'exit_code': code, 'log_lines': len(log.splitlines()), 'log_sha256': hashlib.sha256(log.encode()).hexdigest()}
            if code != 0 or 'CHECK FAILED' in log:
                failed = True
                print(f'--- {machine} built from {label}, exit code {code}\n{log}')
    if args.against:
        for machine in machines:
            same = logs['tree', machine] == logs[args.against, machine]
            result[machine]['same_log_as_' + args.against] = same
            if not same:
                failed = True
                old, new = logs[args.against, machine].splitlines(), logs['tree', machine].splitlines()
                for number, (before, after) in enumerate(zip(old, new), 1):
                    if before != after:
                        print(f'{machine}: line {number} differs\n  {args.against}: {before}\n  tree: {after}')
                        break
    print(json.dumps(result, indent=2))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
