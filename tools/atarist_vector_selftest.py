"""Independent MC68000 vectors replayed through the Atari ST's 68000 (gate G10, independent CPU evidence).

    python -B tools/atarist_vector_selftest.py [fixture ...]        (default: every fixture; needs a compiler, no ROM, no TOS, no disk)

The vectors are the pinned SingleStepTests/m68000 fixtures of the repository (`tests/fixtures`, MIT, generated with MAME, not
recorded from hardware; synthetic instruction data), read as `tools/x68000_vector_selftest.py` reads them. The code under test is
the ST's own CPU: Hatari's cycle-exact 68000 (WinUAE's) as the session configures it for a plain ST (`native/atarist_machine/
atarist_session.c`), linked into the harness `native/atarist_machine/atarist_vector_checks.c`. The harness opens a session on a tiny
authored TOS image and a blank floppy image, both built in memory, runs one frame so that Hatari builds its CPU tables and enters
its cycle-exact loop, then loads each vector straight into Hatari's registers and RAM and executes ONE instruction the way the loop
does: `(*cpufunctbl_noret[opcode])(opcode)`. It also runs the native step the converter's own generator writes for the opcode
(`retrorecomp/atarist_codegen.py`, from the opcode table the harness takes from Hatari: a function that calls Hatari's handler of the
opcode by its name, as a game's steps do) and checks that it gives the same registers, RAM and clocks as the table's call.

What is replayed, and what is left out (each category is counted, never hidden):
  * outside the ST's memory: a vector whose RAM bytes are not all in the ST's RAM (4,096 KiB here) above its 8-byte ROM mirror, or
    that touches the system area below $800 from user mode (a bus error on an ST), runs in the second pass (`flat`) only;
  * the two authored vectors whose point is the trace exception delivered after the instruction: Hatari delivers it from its CPU
    loop, not from the handler this harness calls (the other vectors with the trace bit set run; the oracle does not deliver it either);
  * the fixtures already exclude odd-address and bus errors, TAS, TRAPV and interrupt acknowledge (docs/CPU_68000.md).
Two passes per fixture: `st` keeps the ST's memory map (what a game sees); `flat` replaces every bank by a flat 24-bit RAM, which
isolates the CPU from the machine's map and runs every vector.

Registers, SR (under the vector's mask), PC, the stopped state and every byte of RAM are compared with the vector's final state.
Hatari's clocks are compared apart. The ST rounds every bus access up to a multiple of 4 cycles, so each vector's clocks are measured
twice: on the ST's bus, and on a plain 16-bit bus (the banks Hatari uses for its ROM and I/O, which have no slot). A difference with
the vector that disappears on the plain bus is the ST's rounding, not a CPU timing disagreement (`cycle_bus`); one that remains is the
core's own (`cycle_other`). Where the fixture lists the vector's bus transactions, they are also replayed on 4-cycle slots, and the
ST-bus clocks are compared with that model (`model_ok` of `model_checked`): it also counts as the ST's rounding, because Hatari's
exception sequences keep two extra clocks on a plain bus too. A difference the plain bus does not remove in a fixture without a
transaction list (`md-exceptions`) cannot be explained or refuted: it is `undecided` (`cycle_unmodelled`). State, clocks, the native
step and the interpreter are separate counts. This shows CPU behaviour against a MAME-made oracle; it does not show the ST's
hardware, gameplay or latency.

The few differences with the vectors that remain are recorded below (`RECORDED_STATE`, `RECORDED_CLOCKS`) with their reason; a
difference that is not recorded, or a recorded one whose count changed, makes the run fail.
"""
from __future__ import annotations
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FIXTURES = ('m68k-groups', 'm68k-shifts', 'md-prefetch', 'md-exceptions')
WORK = ROOT / '.build' / 'atarist-vectors'
HATARI = ROOT / '.build' / 'atarist-hatari'
RAM_END = 0x400000        # the harness opens the session with 4,096 KiB of ST RAM
ROM_MIRROR = 8            # the first 8 bytes of an ST read the TOS ROM and cannot be written
SYSTEM_AREA = 0x800       # below it, the ST answers a user-mode access with a bus error
SUPERVISOR = 0x2000
# State differences with the vectors, by (fixture, pass) and group: Hatari saves N after DIVU and Z after DIVS by zero in the exception
# frame's SR, where the authored Motorola-based vectors keep them clear; N, Z, V and C after a divide by zero are undefined on a 68000.
RECORDED_STATE = {('md-prefetch', 'flat'): {'authored-variable': 2}}
# Clock differences the vector's bus transactions on 4-cycle slots do not explain (`cycle_other`), by (fixture, pass) and group: 14
# CHK-phases vectors take 4 more clocks in Hatari's CHK exception than the vector's transactions give on 4-cycle slots (44 where the
# model says 40, 48 where it says 44, 52 where it says 48...).
RECORDED_CLOCKS = {('md-prefetch', 'flat'): {'CHK-phases': 14}}
TRACE_DELIVERY = 'post-instruction trace'    # the name of the two authored vectors that expect the trace exception after the instruction
ALIGN = 4                 # the ST's bus: every CPU access starts on a multiple of 4 cycles
REGS = [*(f'd{i}' for i in range(8)), *(f'a{i}' for i in range(7)), 'usp', 'ssp', 'sr', 'pc']


def fixture_tests(name: str) -> list[dict]:
    """Every vector of a fixture, as the other machines' replays read it (the Mega Drive prefetch fixture adds its authored cases)."""
    tests = list(json.loads((ROOT / 'tests/fixtures' / name / 'cases.json').read_text(encoding='utf-8'))['tests'])
    if name == 'md-prefetch':
        tests += json.loads((ROOT / 'tests/fixtures/md-prefetch/authored.json').read_text(encoding='utf-8'))['tests']
    return tests


def cycles_of(test: dict) -> int:
    return test.get('length', test.get('cycles'))


def stops(test: dict) -> int:
    """1 when the vector ends with the CPU stopped (a STOP in supervisor mode: the fixtures give it 4 clocks)."""
    return int(test['group'] == 'STOP' and cycles_of(test) == 4)


def final_pc_offset(test: dict) -> int:
    """SingleStepTests PCs include the two prefetched words (4 bytes). The vectors of a stopped STOP perform no new prefetch, so their
    final PC already is the following instruction (the other machines' replays use offset 0 for them). Hatari's STOP leaves PC on
    the STOP instruction while the CPU is stopped (it is run again until an interrupt arrives), which is the vector's PC minus the
    two prefetched words like every other instruction: the offset is always 4, and the stopped state is compared on its own."""
    return 4


def architectural_pc(pc: int, offset: int = 4) -> int:
    """The address of the instruction (or of the next one) on the 24-bit bus: the vector's PC minus its prefetched words."""
    return (pc - offset) & 0xffffff


def state_values(state: dict, pc_offset: int = 4) -> list[int]:
    """d0-d7, a0-a6, usp, ssp, sr, pc (architectural)."""
    return [state[key] if key != 'pc' else architectural_pc(state[key], pc_offset) for key in REGS]


def ram_addresses(test: dict) -> set[int]:
    return {address & 0xffffff for stage in ('initial', 'final') for address, _ in test[stage]['ram']}


def classify(test: dict, flat: bool = False, ram_end: int = RAM_END) -> str:
    """Why a vector does not run in a pass, or 'run'. The ST's map: RAM from 8 to the end of RAM, the system area below $800 reserved
    to the supervisor; the flat pass takes every address of the 24-bit bus."""
    if TRACE_DELIVERY in test['name']:
        return 'trace_delivery'
    addresses = ram_addresses(test)
    if flat:
        return 'run'
    if any(address >= ram_end for address in addresses):
        return 'beyond_ram'
    if any(address < ROM_MIRROR for address in addresses):
        return 'rom_mirror'
    if any(address < SYSTEM_AREA for address in addresses) and not test['initial']['sr'] & SUPERVISOR:
        return 'user_system_area'
    return 'run'


def aligned_cycles(test: dict) -> int:
    """The vector's clocks with every bus access started on a multiple of 4 cycles (-1 when the fixture has no transaction list): an
    idle period ('n') takes its clocks, a read or write waits for the next slot and takes its own clocks (4 on a 68000)."""
    if 'transactions' not in test:
        return -1
    clock = 0
    for transaction in test['transactions']:
        if transaction[0] != 'n':
            clock = -(-clock // ALIGN) * ALIGN
        clock += transaction[1]
    return clock


def vector_line(test: dict) -> str:
    """One line of the file the harness reads: name, group, clocks, aligned clocks, SR mask, stopped flag, the two prefetched words,
    the initial and final states (decimal), then the initial and final RAM as address/value pairs."""
    initial, final = test['initial'], test['final']
    fields = [f"{test['group']}:{test['name']}".replace(' ', '_'), test['group'].replace(' ', '_'), cycles_of(test), aligned_cycles(test),
              test.get('sr_mask', 0xffff), stops(test), initial['prefetch'][0], initial['prefetch'][1],
              *state_values(initial), *state_values(final, final_pc_offset(test))]
    for stage in (initial, final):
        pairs = stage['ram']
        fields.append(len(pairs))
        for address, value in pairs:
            fields.extend((address & 0xffffff, value))
    return ' '.join(str(field) for field in fields)


def selection(name: str, flat: bool) -> tuple[list[dict], dict]:
    """(the vectors that run, the count of every other category) for one fixture and pass."""
    tests, left = fixture_tests(name), {}
    run = []
    for test in tests:
        reason = classify(test, flat)
        if reason == 'run':
            run.append(test)
        else:
            left[reason] = left.get(reason, 0) + 1
    return run, left


# ------------------------------------------------------------------------------------------------------------------ build
def ensure_hatari() -> tuple[Path, Path]:
    """The adapted Hatari tree and its build with `libretro-hatari.a` (built when missing: the adaptation of the pinned checkout)."""
    from retrorecomp import atarist_hatari
    from retrorecomp.core import run, toolchain
    from retrorecomp.platforms import build_jobs, cmake_target_args
    tree, build = HATARI / 'hatari', HATARI / 'build'
    library = build / 'src' / 'libretro-hatari.a'
    if not (tree / 'src' / 'retro' / 'main_retro.c').exists() or not library.exists() or not (build / 'src' / 'cpu' / 'cputbl.h').exists():
        tree = atarist_hatari.adapt(atarist_hatari.source(), HATARI)
        build.mkdir(parents=True, exist_ok=True)
        cmake, generator = toolchain()
        run([cmake, '-S', tree, '-B', build, '-G', generator, *cmake_target_args(),
             *atarist_hatari.configure_arguments(ROOT / 'native' / 'atarist_machine' / 'libretro')], log=HATARI / 'configure.log')
        run([cmake, '--build', build, '--parallel', build_jobs(), '--target', 'retro-hatari'], log=HATARI / 'build.log', timeout=3600)
    return tree, build


def compile_harness(folder: Path, tree: Path, build: Path, steps: Path | None) -> Path:
    """The harness against the adapted Hatari: with the generated native steps (`steps`: a folder holding steps.c and step_semantics.h)
    or without."""
    from retrorecomp.core import run, toolchain
    from retrorecomp.platforms import build_executable, build_jobs, cmake_target_args
    machine = (ROOT / 'native' / 'atarist_machine').as_posix()
    folder.mkdir(parents=True, exist_ok=True)
    sources = f'"{machine}/atarist_vector_checks.c" "{machine}/atarist_session.c"' + (f' "{steps.as_posix()}/steps.c"' if steps else '')
    steps_include = f'"{steps.as_posix()}"' if steps else ''
    steps_define = 'target_compile_definitions(checks PRIVATE RR_VECTOR_STEPS=1)' if steps else ''
    (folder / 'CMakeLists.txt').write_text(f"""cmake_minimum_required(VERSION 3.20)
project(RetroAtariSTVectors C)
set(CMAKE_C_STANDARD 11)
set(RR_HATARI_TREE "{tree.as_posix()}")
set(RR_HATARI_BUILD "{build.as_posix()}")
find_library(RR_HATARI_CORE NAMES retro-hatari libretro-hatari PATHS "${{RR_HATARI_BUILD}}/src" NO_DEFAULT_PATH REQUIRED)
add_executable(checks {sources})
target_include_directories(checks PRIVATE "{machine}" "{machine}/libretro" {steps_include} "${{RR_HATARI_BUILD}}"
    "${{RR_HATARI_TREE}}/src/includes" "${{RR_HATARI_TREE}}/src/cpu" "${{RR_HATARI_TREE}}/src/cpu/softfloat" "${{RR_HATARI_TREE}}/src/debug"
    "${{RR_HATARI_TREE}}/src/falcon" "${{RR_HATARI_TREE}}/src" "${{RR_HATARI_TREE}}" "${{RR_HATARI_BUILD}}/src/cpu")
{steps_define}
target_link_libraries(checks PRIVATE "${{RR_HATARI_CORE}}")
if(NOT WIN32)
  target_link_libraries(checks PRIVATE m)
else()
  target_link_libraries(checks PRIVATE ws2_32)
endif()
target_compile_options(checks PRIVATE -O2 -fno-fast-math)
""", encoding='utf-8', newline='\n')
    cmake, generator = toolchain()
    run([cmake, '-S', folder, '-B', folder / 'build', '-G', generator, *cmake_target_args(), '-DCMAKE_BUILD_TYPE=Release'], log=folder / 'build.log')
    run([cmake, '--build', folder / 'build', '--parallel', build_jobs()], log=folder / 'build.log', timeout=1800)
    return build_executable(folder / 'build', 'checks')


def step_opcodes(names) -> list[int]:
    """The opcode word of every vector of the fixtures: the steps are generated for these."""
    return sorted({test['initial']['prefetch'][0] for name in names for test in fixture_tests(name)})


def write_steps(opcodes, map_file: Path, build: Path, folder: Path) -> int:
    """The native steps of the opcodes, written by the converter's own ST generator (`retrorecomp/atarist_codegen.py`) from the opcode
    table the harness wrote (an opcode Hatari's table sends to its illegal-instruction handlers gets no step, as in a conversion).
    Returns how many steps were written."""
    from retrorecomp import atarist_codegen
    atarist_codegen.load_opcode_map(map_file, build / 'src' / 'cpu' / 'cpustbl.c')
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'step_semantics.h').write_text(atarist_codegen._semantics('', None), encoding='utf-8', newline='\n')
    text, table = [atarist_codegen.STEPS_HEAD, 'typedef struct { uint16_t opcode; void (*run)(uint32_t opcode); } VectorStep;\n'], []
    for opcode in opcodes:
        if atarist_codegen._MAP.get(opcode, '-') == '-':
            continue
        definition, _ = atarist_codegen._step(f'rr_vector_step_{opcode:04x}', {'words': [opcode]}, '', '')
        text.append(definition)
        table.append(f'    {{0x{opcode:04x}, rr_vector_step_{opcode:04x}}},')
    text.append('const VectorStep rr_vector_steps[] = {\n' + '\n'.join(table) + '\n};\n')
    text.append(f'const unsigned rr_vector_step_count = {len(table)};\n')
    (folder / 'steps.c').write_text(''.join(text), encoding='utf-8', newline='\n')
    return len(table)


def build_harness(names=FIXTURES) -> tuple[Path, int]:
    """(the harness with the generated steps, how many steps). Two builds: the first writes Hatari's opcode table, which the converter's
    generator needs to name the handlers; the second has the steps of every opcode the fixtures use."""
    from retrorecomp.core import run
    tree, build = ensure_hatari()
    first = compile_harness(WORK / 'map', tree, build, None)
    map_file = WORK / 'opcode-map.txt'
    run([first, '--opcode-map', map_file], cwd=WORK)    # Hatari creates an empty log file named `stderr` in the working folder
    count = write_steps(step_opcodes(names), map_file, build, WORK / 'generated')
    return compile_harness(WORK / 'native', tree, build, WORK / 'generated'), count


def replay(name: str, flat: bool, program: Path) -> dict:
    from retrorecomp.core import run
    tests, left = selection(name, flat)
    mode = 'flat' if flat else 'st'
    path = WORK / f'{name}-{mode}.vectors'
    path.write_text('\n'.join(vector_line(test) for test in tests) + '\n', encoding='ascii', newline='\n')
    output = run([program, *(['--flat'] if flat else []), path], cwd=WORK)
    result = json.loads(next(line for line in output.splitlines() if line.startswith('{')))
    result.update(fixture=name, mode=mode, total=len(fixture_tests(name)), selected=len(tests), left_out=left)
    return result


def problems(result: dict) -> list[str]:
    """What a pass must satisfy for the harness to be trusted (a disagreement with the vectors is reported, not a problem of the harness):
    every selected vector ran, the native step is the interpreter's handler wherever a step exists, and nothing was dropped by the C side."""
    found = []
    totals = result['totals']
    if result['outside_window'] or totals['run'] != result['selected']:
        found.append(f"{result['fixture']} ({result['mode']}): {result['selected']} vectors selected, {totals['run']} ran, {result['outside_window']} outside the window")
    if totals['paths_equal'] != totals['native_step']:
        found.append(f"{result['fixture']} ({result['mode']}): the native step differs from the interpreter for {totals['native_step'] - totals['paths_equal']} vectors")
    key = (result['fixture'], result['mode'])
    recorded_state, recorded_clocks = RECORDED_STATE.get(key, {}), RECORDED_CLOCKS.get(key, {})
    for group in result['groups']:
        name = group['group']
        for what, found_count, recorded in (('state', group['run'] - group['state_ok'], recorded_state.get(name, 0)),
                                            ('clocks', group['cycle_other'], recorded_clocks.get(name, 0))):
            if found_count != recorded:
                found.append(f"{result['fixture']} ({result['mode']}) {name}: {found_count} {what} differences with the vectors, {recorded} recorded")
    return found


def summary(result: dict) -> str:
    t = result['totals']
    left = ', '.join(f'{count} {reason}' for reason, count in sorted(result['left_out'].items())) or 'none'
    return (f"{result['fixture']:<12} {result['mode']:<4} {result['total']:>5} vectors, {result['selected']:>5} selected (left out: {left}); "
            f"state agrees {t['state_ok']:>5}/{t['run']:<5} differs {t['state_differ']:<4}; clocks equal {t['cycle_ok']:>5}, "
            f"ST bus rounding only {t['cycle_bus']:>4}, other {t['cycle_other']:>4}, undecided {t['cycle_unmodelled']:>4} (plain bus equals the vector "
            f"{t['plain_ok']:>5}; 4-cycle model {t['model_ok']}/{t['model_checked']}); "
            f"native step {t['native_step']:>5} (state agrees {t['native_state_ok']:>5}), same as interpreter {t['paths_equal']:>5}")


def main(names=None) -> int:
    program, steps = build_harness(names or FIXTURES)
    results = []
    for name in names or FIXTURES:
        for flat in (False, True):
            results.append(replay(name, flat, program))
            results[-1]['steps_generated'] = steps
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / 'results.json').write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')
    failed = 0
    for result in results:
        print(summary(result))
        for text in problems(result):
            failed += 1
            print('PROBLEM', text)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:] or None))
