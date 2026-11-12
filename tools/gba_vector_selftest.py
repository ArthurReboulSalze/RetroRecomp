"""Independent ARM7TDMI vectors (SingleStepTests/ARM7TDMI) against the engine's interpreter and its generated code (gate G10).

`tools/fetch_gba_vectors.py` keeps the pinned suite in a folder of your choice (outside the repository). This stages the pinned
Game Boy Advance engine exactly as a conversion does (`gba_engine.stage` with `gba_patches.PATCHES`, so the numbers are those of the
patched engine the converter builds), builds the engine's ARM library, compiles native/gba_vector_checks/ against it and runs, one
instruction at a time:

  * the interpreter (`Interpreter::step`, the fallback of a converted game) over EVERY vector of the folder, and
  * the code the engine generates for one instruction (`ArmCodegen::emit_instr`, the call its recompiler makes) over an evenly
    spaced sample (`--stride`, `--max-per-file`).

R0-R15, every register bank, CPSR, the SPSRs and the ordered data reads and writes are compared. Not compared: instruction
fetches, cycle counts, bus conflicts, prefetch. The vectors are the behaviour of NanoBoyAdvance's model of the ARM7TDMI, not
hardware, so this is independent CPU evidence against one other implementation and says nothing about hardware fidelity.

Each failure is put in one category, from its opcode and its failing words (`classify`), so that a change moves a named number:
the coprocessor families (generated code does not implement them, the interpreter reports them undefined), the carry flag after
a multiply (not defined by the architecture, a modelling choice of the suite), encodings with R15 as an operand (mostly
unpredictable), and everything else, the tail that is not explained. `--baseline FILE` records the per-file counts the first time
and compares against them afterwards: more failures in any file and category than the baseline is a regression (exit 1).

    python tools/gba_vector_selftest.py run --vectors FOLDER [--stride 50] [--max-per-file 1000] [--baseline FILE]
    python tools/gba_vector_selftest.py build                       stage the engine, build the library and the checks
    python tools/gba_vector_selftest.py report                      rebuild the report from the logs of the last run
    python tools/gba_vector_selftest.py compare REPORT BASELINE     compare a report with a baseline, nothing is built

The work folder (default `.build/gba-vector-selftest`, `--work` to change) holds the build, the raw logs of both checks, the report
(`report.json`) and the baseline when it is recorded there. Nothing of the suite or of any ROM is ever copied into the repository.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))
import fetch_gba_vectors as corpus  # noqa: E402

SCHEMA = 1
DEFAULT_WORK = ROOT / '.build' / 'gba-vector-selftest'
DEFAULT_STRIDE = 50
DEFAULT_MAX_PER_FILE = 1000
PATHS = ('interpreter', 'generated')
SOURCES = ('ss_common.h', 'ss_gen.cpp', 'ss_run.cpp', 'ss_interp.cpp')       # under native/gba_vector_checks/
MODEL_STATEMENT = ('The vectors are generated from NanoBoyAdvance\'s model of the ARM7TDMI (SingleStepTests/ARM7TDMI, MIT), not '
                   'recorded from hardware: this is agreement with one other implementation, one instruction at a time. It is not '
                   'hardware fidelity, not cycle accuracy and not gameplay validation.')

# The categories of failure, and why each is expected to differ. A failure goes to the first that applies.
COPROCESSOR = 'coprocessor'
MULTIPLY_CARRY = 'multiply_carry'
R15_OPERAND = 'r15_operand'
BLOCK_USER_WRITEBACK = 'block_user_writeback'
THUMB_EMPTY_LIST = 'thumb_empty_list'
OTHER = 'other'
CATEGORIES = (COPROCESSOR, MULTIPLY_CARRY, R15_OPERAND, BLOCK_USER_WRITEBACK, THUMB_EMPTY_LIST, OTHER)
EXPLANATIONS = {
    COPROCESSOR: 'CDP, MRC/MCR, LDC/STC: the ARM7TDMI of the console has no coprocessor and traps them as undefined instructions; the '
                 'generated code reports them as unimplemented and the interpreter as undefined (the caller takes the trap), where the '
                 'vectors model the instruction as executed.',
    MULTIPLY_CARRY: 'The carry flag after MUL, MLA, MULL, MLAL and Thumb MUL (the only difference being C): unpredictable on ARMv4, the '
                    'suite models a value.',
    R15_OPERAND: 'An ARM encoding whose register fields name R15 (or an LDM/STM list holding it): mostly architecturally unpredictable. '
                 'The test is the opcode fields alone, so it also catches an encoding whose field is 15 for another reason.',
    BLOCK_USER_WRITEBACK: 'ARM LDM or STM with the S bit (the user-bank form) and write-back: architecturally unpredictable, and only seen in a '
                          'banked mode (FIQ, IRQ, supervisor, abort, undefined), where the suite models one choice of the base register and of '
                          'the registers written back. Found by decoding the 247 + 7 failures that were unexplained on 6 November 2026: all of them.',
    THUMB_EMPTY_LIST: 'Thumb LDMIA or POP with an empty register list (a load of R15 only). The model keeps bit 0 of the loaded word in R15, which it '
                      'does not do for a non-empty POP {PC} (it clears it in all 6,360 vectors where the word is odd); the engine clears it, as '
                      'for every other load of the PC, and dispatching on an odd PC would not be safe. The stores of an empty list (STMIA, PUSH: the '
                      'value stored is the instruction address + 6) agreed after the patch of 12 November 2026: a failing store is now unexplained.',
    OTHER: 'Everything else: not explained. A change here is the signal; the baseline guards it.',
}
CARRY_BIT = 0x20000000
EXAMPLES_PER_FILE = 3
TOP_CAUSES = 10


# --- parsing and classification (no vectors or compilers needed) ---------------------------------------------------------------

def parse_line(line: str):
    """One line of a check's output as a dict, or None for a line that is not a FILE or FAIL record."""
    parts = line.split()
    if len(parts) == 4 and parts[0] == 'FILE':
        return {'type': 'FILE', 'name': parts[1], 'ran': int(parts[2]), 'passed': int(parts[3])}
    if len(parts) == 9 and parts[0] == 'FAIL':
        return {'type': 'FAIL', 'name': parts[1], 'index': int(parts[2]), 'opcode': int(parts[3], 16), 'thumb': parts[4] == '1',
                'mode': int(parts[5], 16), 'kind': parts[6], 'cpsr_xor': int(parts[7], 16),
                'causes': [] if parts[8] == '-' else parts[8].split(',')}
    return None


def is_coprocessor(opcode: int, thumb: bool) -> bool:
    return not thumb and (opcode >> 24) & 0xF in (0xC, 0xD, 0xE)


def is_multiply(opcode: int, thumb: bool) -> bool:
    if thumb:
        return opcode & 0xFFC0 == 0x4340                                   # MUL Rd, Rs
    return opcode & 0x0FC000F0 == 0x00000090 or opcode & 0x0F8000F0 == 0x00800090     # MUL, MLA; UMULL, UMLAL, SMULL, SMLAL


def has_r15_operand(opcode: int, thumb: bool) -> bool:
    """The register fields of an ARM opcode (Rd, Rn, Rm, Rs) naming R15, or a block transfer whose list holds it."""
    if thumb:
        return False
    return (opcode >> 12 & 15 == 15 or opcode >> 16 & 15 == 15 or opcode & 15 == 15 or opcode >> 8 & 15 == 15
            or (opcode >> 25 & 7 == 4 and bool(opcode & 0x8000)))


def classify(record: dict) -> str:
    """The category of one failure record (see EXPLANATIONS): the first that applies."""
    opcode, thumb = record['opcode'], record['thumb']
    if is_coprocessor(opcode, thumb):
        return COPROCESSOR
    if record['causes'] == ['CPSR'] and record['cpsr_xor'] == CARRY_BIT and is_multiply(opcode, thumb):
        return MULTIPLY_CARRY
    if has_r15_operand(opcode, thumb):
        return R15_OPERAND
    if not thumb and opcode >> 25 & 7 == 4 and opcode & (1 << 22) and opcode & (1 << 21):
        return BLOCK_USER_WRITEBACK
    if thumb and opcode & 0xFF == 0 and (opcode & 0xF800 == 0xC800 or opcode == 0xBC00):          # LDMIA Rb!,{} and POP {}: loads only
        return THUMB_EMPTY_LIST
    return OTHER


def new_file(name: str) -> dict:
    return {'name': name, 'ran': None, 'passed': None, 'failures': {category: 0 for category in CATEGORIES},
            'r15_operand_proxy': 0, 'causes': Counter(), 'examples': []}


def read_output(lines) -> dict:
    """The per-file results of one check from its output lines: {name: {ran, passed, failed, failures by category, ...}}.
    A file whose failures do not add up to ran - passed (a crash in the middle of a file) is an error, not a number."""
    files: dict = {}
    for line in lines:
        record = parse_line(line)
        if record is None:
            continue
        entry = files.setdefault(record['name'], new_file(record['name']))
        if record['type'] == 'FILE':
            entry['ran'], entry['passed'] = record['ran'], record['passed']
            continue
        category = classify(record)
        entry['failures'][category] += 1
        entry['r15_operand_proxy'] += has_r15_operand(record['opcode'], record['thumb'])
        if category == OTHER:
            entry['causes'][record['causes'][0] if record['causes'] else record['kind']] += 1
            if len(entry['examples']) < EXAMPLES_PER_FILE:
                entry['examples'].append({key: record[key] for key in ('index', 'opcode', 'thumb', 'mode', 'kind', 'causes')})
    for entry in files.values():
        failed = sum(entry['failures'].values())
        if entry['ran'] is None or entry['ran'] - entry['passed'] != failed:
            raise ValueError(f'{entry["name"]}: the output is incomplete or inconsistent (ran {entry["ran"]}, passed {entry["passed"]}, '
                             f'{failed} failure records)')
        entry['failed'] = failed
    return files


def summarise(files: dict) -> dict:
    """The totals of the per-file results of one path."""
    ran = sum(entry['ran'] for entry in files.values())
    passed = sum(entry['passed'] for entry in files.values())
    causes = Counter()
    for entry in files.values():
        causes.update(entry['causes'])
    return {'files': len(files), 'ran': ran, 'passed': passed, 'failed': ran - passed,
            'passed_percent': round(100 * passed / ran, 2) if ran else None,
            'failures': {category: sum(entry['failures'][category] for entry in files.values()) for category in CATEGORIES},
            'r15_operand_proxy': sum(entry['r15_operand_proxy'] for entry in files.values()),
            'other_causes': dict(causes.most_common(TOP_CAUSES))}


def file_rows(files: dict) -> dict:
    return {name: {'ran': entry['ran'], 'passed': entry['passed'], 'failed': entry['failed'],
                   'failures': dict(entry['failures']), 'r15_operand_proxy': entry['r15_operand_proxy'],
                   'other_causes': dict(entry['causes'].most_common(TOP_CAUSES)), 'other_examples': entry['examples']}
            for name, entry in sorted(files.items())}


def build_report(results: dict, meta: dict) -> dict:
    """The report: what was run (`meta`), the statement about the vectors, and per path the totals and the files."""
    report = {'schema': SCHEMA, 'statement': MODEL_STATEMENT, 'categories': EXPLANATIONS, **meta}
    for path in PATHS:
        if path in results:
            report[path] = {'totals': summarise(results[path]), 'files': file_rows(results[path])}
    return report


# --- the baseline ----------------------------------------------------------------------------------------------------------------

def baseline_from_report(report: dict) -> dict:
    """What a later run is compared with: per path and file, the vectors run and the failures per category (zero ones omitted)."""
    baseline = {'schema': SCHEMA, 'vectors': report['vectors'], 'sample': report['sample'], 'engine': report['engine'], 'paths': {}}
    for path in PATHS:
        if path in report:
            baseline['paths'][path] = {name: {'ran': row['ran'], 'failures': {c: n for c, n in row['failures'].items() if n}}
                                       for name, row in report[path]['files'].items()}
    return baseline


def compare_baseline(report: dict, baseline: dict):
    """(regressions, improvements) of `report` against `baseline`, as lists of sentences. A regression is more failures in a file and
    category than the baseline holds (a category it did not hold counts from zero), a file run on another number of vectors, or a
    sample that is not the baseline's. An improvement is fewer; it asks for the baseline to be recorded again."""
    regressions, improvements = [], []
    if baseline.get('schema') != SCHEMA:
        return [f'the baseline has schema {baseline.get("schema")!r}, this tool reads {SCHEMA}'], improvements
    if baseline.get('vectors', {}).get('corpus_sha256') != report['vectors'].get('corpus_sha256'):
        regressions.append('the vectors are not the baseline\'s (another corpus digest)')
    for path in PATHS:
        if path not in report or path not in baseline['paths']:
            continue
        if baseline['sample'].get(path) != report['sample'].get(path):
            regressions.append(f'{path}: the sample is {report["sample"].get(path)}, the baseline\'s is {baseline["sample"].get(path)}')
            continue
        for name, row in report[path]['files'].items():
            before = baseline['paths'][path].get(name, {'ran': row['ran'], 'failures': {}})
            if before['ran'] != row['ran']:
                regressions.append(f'{path} {name}: {row["ran"]} vectors run, the baseline ran {before["ran"]}')
                continue
            for category in CATEGORIES:
                now, then = row['failures'].get(category, 0), before['failures'].get(category, 0)
                if now > then:
                    regressions.append(f'{path} {name} {category}: {now} failures, the baseline has {then}')
                elif now < then:
                    improvements.append(f'{path} {name} {category}: {now} failures, the baseline has {then}')
    return regressions, improvements


# --- the build and the run ---------------------------------------------------------------------------------------------------------

def cmake_project(checks: Path, engine: Path, library: Path) -> str:
    """The CMake project of the checks: the three programs, linked to the engine's ARM library, against the headers of the staged engine.
    ss_run.cpp is built with the functions ss_gen writes (`ss_funcs.cpp` in the build folder), with light optimisation: there are a
    great many of them."""
    return f'''cmake_minimum_required(VERSION 3.20)
project(gba_vector_checks CXX)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    set(CMAKE_BUILD_TYPE Release)
endif()
add_library(engine_armv4t STATIC IMPORTED)
set_target_properties(engine_armv4t PROPERTIES IMPORTED_LOCATION "{library.as_posix()}")
include_directories("{checks.as_posix()}" "{(engine / 'src/armv4t').as_posix()}" "{(engine / 'src/gba').as_posix()}"
                    "{(engine / 'src/runtime').as_posix()}")
if(MSVC)
    add_compile_options(/w)
    set(GENERATED_OPTIMISATION /O1)
else()
    add_compile_options(-w)
    set(GENERATED_OPTIMISATION -O1)
endif()
set(GENERATED "${{CMAKE_CURRENT_BINARY_DIR}}/ss_funcs.cpp")
set_source_files_properties("${{GENERATED}}" PROPERTIES COMPILE_OPTIONS "${{GENERATED_OPTIMISATION}}")
add_executable(ss_interp "{(checks / 'ss_interp.cpp').as_posix()}")
add_executable(ss_gen "{(checks / 'ss_gen.cpp').as_posix()}")
add_executable(ss_run "{(checks / 'ss_run.cpp').as_posix()}" "{(engine / 'src/gba/gba_waitstates.cpp').as_posix()}" "${{GENERATED}}")
foreach(program ss_interp ss_gen ss_run)
    target_link_libraries(${{program}} PRIVATE engine_armv4t)
    if(WIN32 AND NOT MSVC)
        target_link_options(${{program}} PRIVATE -static)
    endif()
endforeach()
'''


def find_library(build: Path) -> Path:
    """The engine's ARM library in a CMake build folder (`libgbarecomp_armv4t.a`, or `gbarecomp_armv4t.lib` of a Visual Studio build)."""
    for pattern in ('libgbarecomp_armv4t.a', 'gbarecomp_armv4t.lib'):
        found = sorted(build.rglob(pattern))
        if found:
            return found[0]
    raise SystemExit(f'The ARM library of the engine is not in {build}.')


def stage_key():
    """(patch digest, key, stage folder) of the staged engine, as `gba_conversion.convert` names them."""
    from retrorecomp import gba_engine, gba_patches
    from retrorecomp.gba_conversion import ENGINE_REV
    digest = gba_engine.patch_digest(gba_patches.PATCHES, gba_patches.ADDED_FILES)
    key = f'{ENGINE_REV[:8]}-{digest[:8]}'
    return digest, key, ROOT / '.deps' / f'gbarecomp-stage-{key}'


def build(work: Path, emit=print) -> dict:
    """Stage the patched engine, build its ARM library (in the converter's own build folder for that key, so a built one is reused),
    and build the checks. Returns where everything is."""
    from retrorecomp import gba_engine, gba_patches
    from retrorecomp.core import run, toolchain
    from retrorecomp.platforms import build_executable, build_jobs, cmake_target_args
    cmake, generator = toolchain()
    digest, key, stage_root = stage_key()
    checkout = gba_engine.checkout(emit)
    _, notes = gba_engine.stage(stage_root, checkout, gba_patches.PATCHES, gba_patches.ADDED_FILES)
    emit(f'Staged engine {key}: {len(notes)} patches.')
    engine_build = ROOT / '.deps' / f'gbarecomp-build-{key}'
    if not (engine_build / 'CMakeCache.txt').is_file():
        run([cmake, '-S', stage_root / 'engine', '-B', engine_build, '-G', generator, *cmake_target_args(),
             '-DGBARECOMP_COMPILER_CACHE=OFF'], log=engine_build.with_suffix('.log'), timeout=900)
    emit('Building the ARM library of the engine (nothing is rebuilt when it is current)…')
    run([cmake, '--build', engine_build, '--target', 'gbarecomp_armv4t', '--parallel', build_jobs()],
        log=engine_build.with_suffix('.log'), timeout=3600)
    library = find_library(engine_build)
    project, binary = work / 'project', work / 'build'
    project.mkdir(parents=True, exist_ok=True)
    (project / 'CMakeLists.txt').write_text(cmake_project(ROOT / 'native' / 'gba_vector_checks', stage_root / 'engine', library),
                                            encoding='utf-8', newline='\n')
    binary.mkdir(parents=True, exist_ok=True)
    if not (binary / 'ss_funcs.cpp').is_file():
        (binary / 'ss_funcs.cpp').write_text('// replaced by ss_gen\n', encoding='utf-8', newline='\n')
    log = work / 'build.log'
    run([cmake, '-S', project, '-B', binary, '-G', generator, *cmake_target_args()], log=log)
    emit('Building the checks…')
    run([cmake, '--build', binary, '--config', 'Release', '--target', 'ss_interp', 'ss_gen', '--parallel', build_jobs()],
        log=log, timeout=1800)
    return {'cmake': cmake, 'binary': binary, 'log': log, 'digest': digest, 'key': key, 'patches': len(notes),
            'programs': {name: build_executable(binary, name) for name in ('ss_interp', 'ss_gen', 'ss_run')}}


def run_to_file(command, destination: Path, timeout: int) -> None:
    """Run a check with its output (the FILE and FAIL lines) in `destination`; its own summary goes to the console."""
    with destination.open('w', encoding='ascii', newline='\n') as out:
        done = subprocess.run([str(part) for part in command], stdout=out, stderr=subprocess.PIPE, text=True, timeout=timeout,
                              creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if done.returncode:
        raise SystemExit(f'{Path(command[0]).name} failed ({done.returncode}):\n{done.stderr[-4000:]}')
    print(Path(command[0]).name + ':', done.stderr.strip(), flush=True)


def selected_files(folder: Path, only) -> list:
    names = [name for name, _size, _digest in corpus.FILES if not only or any(word in name for word in only)]
    return [str(corpus.vector_dir(folder) / corpus.file_name(name)) for name in names]


def meta_for(built: dict, args, count: int) -> dict:
    from retrorecomp.gba_conversion import ENGINE_REV
    return {'vectors': {'suite': 'SingleStepTests/ARM7TDMI', 'revision': corpus.REVISION, 'corpus_sha256': corpus.CORPUS_SHA256,
                        'files': count, 'generated_from': 'NanoBoyAdvance (a model, not hardware)', 'licence': 'MIT'},
            'engine': {'revision': ENGINE_REV, 'patch_digest': built['digest'], 'patches': built['patches']},
            'sample': {'interpreter': {'stride': 1, 'max_per_file': None},
                       'generated': {'stride': args.stride, 'max_per_file': args.max_per_file}}}


def read_log(path: Path) -> dict:
    with path.open(encoding='ascii') as lines:
        return read_output(lines)


def finish(work: Path, meta: dict, args) -> int:
    """The report from the logs of a run, the baseline, the summary. Returns the exit code."""
    report = build_report({'interpreter': read_log(work / 'interpreter.log'), 'generated': read_log(work / 'generated.log')}, meta)
    (work / 'report.json').write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8', newline='\n')
    print_summary(report)
    print('Report:', work / 'report.json')
    return apply_baseline(report, args)


def print_summary(report: dict) -> None:
    print(MODEL_STATEMENT)
    for path in PATHS:
        totals = report[path]['totals']
        sample = report['sample'][path]
        what = 'every vector' if path == 'interpreter' else f'every {sample["stride"]}th, at most {sample["max_per_file"]} per file'
        print(f'{path}: {totals["passed"]} of {totals["ran"]} vectors agree ({totals["passed_percent"]} %), {what}, {totals["files"]} files')
        print('   failures: ' + ', '.join(f'{category} {totals["failures"][category]}' for category in CATEGORIES)
              + f' (R15 operand by the opcode fields, whatever the category: {totals["r15_operand_proxy"]})')
        if totals['other_causes']:
            print('   first cause of the others: ' + ', '.join(f'{cause} {count}' for cause, count in totals['other_causes'].items()))


def apply_baseline(report: dict, args) -> int:
    path = getattr(args, 'baseline', None)
    if path is None:
        return 0
    path = Path(path)
    if getattr(args, 'record_baseline', False) or not path.is_file():
        if getattr(args, 'only', None):
            print('A baseline is not recorded from a run of some of the files (--only).')
            return 2
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(baseline_from_report(report), indent=1) + '\n', encoding='utf-8', newline='\n')
        print('Baseline recorded:', path)
        return 0
    regressions, improvements = compare_baseline(report, json.loads(path.read_text(encoding='utf-8')))
    for line in improvements:
        print('better than the baseline:', line)
    if improvements and not regressions:
        print('Record the baseline again (--record-baseline) to keep the improvement.')
    for line in regressions:
        print('REGRESSION:', line)
    print('Baseline', path, 'REGRESSED' if regressions else 'holds')
    return 1 if regressions else 0


def command_run(args) -> int:
    work = args.work
    work.mkdir(parents=True, exist_ok=True)
    folder = args.vectors
    if args.fetch:
        corpus.fetch(folder)
    files = selected_files(folder, args.only)
    if not files:
        print('No vector file matches --only.')
        return 2
    _good, missing, wrong = corpus.inspect(folder, check_hashes=not args.skip_hash)
    needed = {Path(file).name[:-len(corpus.SUFFIX)] for file in files}
    bad = sorted(needed & set(missing + wrong))
    if bad:
        print('The vectors are not the pinned ones (run tools/fetch_gba_vectors.py FOLDER):', ', '.join(bad))
        return 2
    built = build(work)
    programs = built['programs']
    run_to_file([programs['ss_interp'], 1, 0x7FFFFFFF, *files], work / 'interpreter.log', timeout=7200)
    functions = built['binary'] / 'ss_funcs.cpp'
    done = subprocess.run([str(programs['ss_gen']), str(functions), str(args.stride), str(args.max_per_file), *files],
                          capture_output=True, text=True, timeout=1800, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if done.returncode:
        print(done.stderr[-4000:])
        return 2
    print('ss_gen:', done.stderr.strip(), flush=True)
    from retrorecomp.core import run
    print('Building the generated functions (one compilation)…', flush=True)
    run([built['cmake'], '--build', built['binary'], '--config', 'Release', '--target', 'ss_run', '--parallel', '1'],
        log=built['log'], timeout=7200)
    run_to_file([programs['ss_run'], args.stride, args.max_per_file, *files], work / 'generated.log', timeout=7200)
    meta = meta_for(built, args, len(files))
    (work / 'meta.json').write_text(json.dumps(meta, indent=1) + '\n', encoding='utf-8', newline='\n')
    return finish(work, meta, args)


def command_build(args) -> int:
    built = build(args.work)
    for name, program in built['programs'].items():
        print(name, program if program.is_file() else '(built by `run`, after the functions exist)')
    return 0


def command_report(args) -> int:
    meta = json.loads((args.work / 'meta.json').read_text(encoding='utf-8'))
    return finish(args.work, meta, args)


def command_compare(args) -> int:
    report = json.loads(args.report.read_text(encoding='utf-8'))
    regressions, improvements = compare_baseline(report, json.loads(args.baseline_file.read_text(encoding='utf-8')))
    for line in improvements:
        print('better than the baseline:', line)
    for line in regressions:
        print('REGRESSION:', line)
    return 1 if regressions else 0


COMMANDS = {'run': command_run, 'build': command_build, 'report': command_report, 'compare': command_compare}


def parse_args(argv=None):
    """The command line. With no subcommand (or an option first) the command is `run`."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or (argv[0] not in COMMANDS and argv[0] not in ('-h', '--help')):
        argv.insert(0, 'run')
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)

    def common(p):
        p.add_argument('--work', type=Path, default=DEFAULT_WORK, help='work folder (default: .build/gba-vector-selftest)')

    def baseline(p):
        p.add_argument('--baseline', type=Path, help='record the per-file failure counts there if the file is missing, else compare')
        p.add_argument('--record-baseline', action='store_true', help='record the baseline even if the file exists')

    run_p = sub.add_parser('run', help='stage, build and run the checks')
    common(run_p)
    baseline(run_p)
    run_p.add_argument('--vectors', type=Path, required=True, help='folder of the .json.bin files (tools/fetch_gba_vectors.py)')
    run_p.add_argument('--stride', type=int, default=DEFAULT_STRIDE, help='generated code: every Nth vector (default %(default)s)')
    run_p.add_argument('--max-per-file', type=int, default=DEFAULT_MAX_PER_FILE,
                       help='generated code: at most N vectors per file (default %(default)s)')
    run_p.add_argument('--only', nargs='+', help='only the files whose name contains one of these words (no baseline is recorded)')
    run_p.add_argument('--fetch', action='store_true', help='download the vectors that FOLDER lacks first (about 920 MB)')
    run_p.add_argument('--skip-hash', action='store_true', help='check the vector files by size only')
    common(sub.add_parser('build', help='stage the engine, build its ARM library and the checks'))
    report_p = sub.add_parser('report', help='the report and the baseline check from the logs of the last run')
    common(report_p)
    baseline(report_p)
    compare_p = sub.add_parser('compare', help='compare a report with a baseline')
    compare_p.add_argument('report', type=Path)
    compare_p.add_argument('baseline_file', type=Path, metavar='baseline')
    args = parser.parse_args(argv)
    if args.command == 'run' and (args.stride < 1 or args.max_per_file < 1):
        parser.error('--stride and --max-per-file must be at least 1')
    return args


def main(argv=None) -> int:
    args = parse_args(argv)
    return COMMANDS[args.command](args)


if __name__ == '__main__':
    sys.exit(main())
