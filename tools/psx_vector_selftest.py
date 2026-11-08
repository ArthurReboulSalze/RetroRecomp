"""Independent vectors against the PlayStation's R3000A and GTE (gate G10).

`tools/fetch_psx_vectors.py` keeps the pinned suites in a folder of your choice (outside the repository). This prepares the pinned
Beetle PSX exactly as a conversion does (`psx_beetle.adapt`), writes one native step per opcode of the suite with the converter's own
generator (`psx_native.write`), builds native/psx_vector_checks/psx_vectors.c with them and runs, one instruction at a time, every
vector through the core's interpreter (the fallback of a converted game) and through the native step of its opcode (the code a game
runs), then the GTE vectors.

Registers, HI, LO, PC, the next PC, the branch delay state, the pending load, EPC, TAR, CAUSE and the data bytes are compared. Not
compared: cycles, the shape of a bus access, COP0 instructions and exceptions of the BIOS (the suite has none). What the vectors
are: SingleStepTests/r3000 says what ares's model of the R3000 does, not hardware; the GTE vectors' expected values come from a
console according to their author. This is independent CPU evidence against one other implementation (and, for the GTE, one
console's values as recorded), and says nothing about hardware fidelity or gameplay.

    python tools/psx_vector_selftest.py run --vectors FOLDER [--baseline FILE]    build, run, write the report
    python tools/psx_vector_selftest.py compare REPORT BASELINE                   compare a report with a baseline, nothing is built

The work folder (default `.build/psx-vector-selftest`, `--work` to change) holds the build, the raw log and `report.json`. A
`--baseline` is recorded the first time and compared afterwards: more failures of a file, path or field is a regression (exit 1).
"""
from __future__ import annotations

import argparse
import json
import re
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))
import fetch_psx_vectors as corpus  # noqa: E402

SCHEMA = 1
DEFAULT_WORK = ROOT / '.build' / 'psx-vector-selftest'
GTE_RECORD = struct.Struct('<129I')             # 64 inputs, the command, 64 outputs
GTE_NO_COMMAND = 0xFFFFFFFF
STEP_SPACING = 8                                # addresses of the steps: never consecutive, so each is one instruction
MODEL_STATEMENT = ('SingleStepTests/r3000 is generated from ares\'s interpreter (a model of the R3000, MIT), not from hardware, and holds no '
                   'COP0 or GTE instruction. The GTE vectors (JaCzekanski/ps1-tests, MIT) hold values its author recorded from a console. '
                   'Independent CPU evidence against one other implementation; nothing about hardware fidelity, gameplay or latency.')
_ENTRY = re.compile(r'\.input\s*=\s*\{(.*?)\},\s*\.opcode\s*=\s*(0x[0-9a-fA-F]+)\s*,[^\n]*\n\s*\.output\s*=\s*\{(.*?)\}', re.S)
_VALUE = re.compile(r'^\s*(0x[0-9a-fA-F]+)\s*,', re.M)


def gte_records(tests_c: str) -> list[tuple]:
    """(inputs, command, outputs) of each vector of `tests.c`."""
    out = []
    for inputs, opcode, outputs in _ENTRY.findall(tests_c):
        before = [int(v, 16) for v in _VALUE.findall(inputs)]
        after = [int(v, 16) for v in _VALUE.findall(outputs)]
        if len(before) != 64 or len(after) != 64:
            raise ValueError('a GTE vector does not hold 64 registers')
        out.append((before, int(opcode, 16), after))
    return out


def opcodes_of(path: Path) -> list[int]:
    """The opcodes of one file of the suite (its transcode_json.py layout)."""
    data = Path(path).read_bytes()
    count = struct.unpack_from('<i', data, 0)[0]
    at, out = 4, []
    state = 128 + 24 + 12 + 8
    for _ in range(count):
        out.append(struct.unpack_from('<I', data, at + 51)[0])
        at += 51 + 8 + state * 2
        cycles = struct.unpack_from('<I', data, at)[0]
        at += 4 + cycles * 24
    return out


def step_pairs(opcodes) -> dict[int, int]:
    """Word -> the address of its one-instruction step, in the order first seen."""
    pairs: dict[int, int] = {}
    for word in opcodes:
        pairs.setdefault(word, len(pairs) * STEP_SPACING)
    return pairs


def parse_log(text: str) -> dict:
    """The JSON lines of the checks program, as totals per path and file, the failures shown and the GTE result."""
    report = {'interpreter': {}, 'native': {}, 'failures': [], 'gte': None, 'gte_failures': []}
    for line in text.splitlines():
        if not line.startswith('{'):
            continue
        row = json.loads(line)
        if 'file' in row:
            report[row['path']][row['file']] = {k: row[k] for k in ('total', 'passed', 'skipped', 'fields')}
        elif 'failure' in row:
            report['failures'].append(row)
        elif 'gte' in row:
            report['gte'] = row['gte']
        elif 'gte_failure' in row:
            report['gte_failures'].append(row)
    return report


def summarise(files: dict) -> dict:
    fields: dict[str, int] = {}
    for row in files.values():
        for name, value in row['fields'].items():
            fields[name] = fields.get(name, 0) + value
    total = sum(r['total'] for r in files.values())
    passed = sum(r['passed'] for r in files.values())
    return {'files': len(files), 'total': total, 'passed': passed, 'failed': total - passed,
            'skipped': sum(r['skipped'] for r in files.values()), 'fields': {k: v for k, v in fields.items() if v}}


def regressions(report: dict, baseline: dict) -> list[str]:
    """What fails more than in the baseline, in words."""
    out = []
    for path in ('interpreter', 'native'):
        for name, row in report.get(path, {}).items():
            before = baseline.get(path, {}).get(name)
            if before is None:
                out.append(f'{path} {name}: not in the baseline')
                continue
            if row['total'] - row['passed'] > before['total'] - before['passed']:
                out.append(f"{path} {name}: {row['total'] - row['passed']} failures, {before['total'] - before['passed']} in the baseline")
    gte, old = report.get('gte') or {}, baseline.get('gte') or {}
    if gte.get('total', 0) - gte.get('passed', 0) > old.get('total', 0) - old.get('passed', 0):
        out.append(f"GTE: {gte.get('total', 0) - gte.get('passed', 0)} failures, {old.get('total', 0) - old.get('passed', 0)} in the baseline")
    return out


def cmake_project(checks: Path, tree: Path, sources: list[str]) -> str:
    cpu = '${RR_BEETLE_TREE}/mednafen/psx/cpu.c'
    return '\n'.join((
        'cmake_minimum_required(VERSION 3.20)',
        'project(PsxVectors LANGUAGES C)',
        'set(CMAKE_C_STANDARD 99)',
        f'set(RR_BEETLE_TREE "{Path(tree).as_posix()}")',
        'include("${RR_BEETLE_TREE}/rr_sources.cmake")',
        f'list(REMOVE_ITEM RR_BEETLE_SOURCES "{cpu}")',
        'add_library(rr_beetle STATIC ${RR_BEETLE_SOURCES})',
        'target_include_directories(rr_beetle PUBLIC ${RR_BEETLE_INCLUDES})',
        'target_compile_definitions(rr_beetle PUBLIC ${RR_BEETLE_DEFINES})',
        'target_compile_options(rr_beetle PRIVATE -O2 -w -fwrapv -fno-strict-aliasing -fno-fast-math)',
        f'add_executable(psx_vectors "{(Path(checks) / "psx_vectors.c").as_posix()}" ' + ' '.join(sources) + ')',
        'target_include_directories(psx_vectors PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}")',
        'target_compile_definitions(psx_vectors PRIVATE RR_PSX_NATIVE)',
        'target_compile_options(psx_vectors PRIVATE -O2 -w -fwrapv -fno-strict-aliasing -fno-fast-math)',
        'target_link_libraries(psx_vectors PRIVATE rr_beetle)',
        'if(NOT WIN32)', '  target_link_libraries(psx_vectors PRIVATE m)', 'endif()',
    )) + '\n'


def build(folder: Path, work: Path, emit=print) -> dict:
    """Prepare Beetle, write the steps and the GTE records, build the checks. Returns where everything is."""
    from retrorecomp import psx_beetle, psx_native
    from retrorecomp.core import run, toolchain
    from retrorecomp.platforms import build_executable, build_jobs, cmake_target_args
    cmake, generator = toolchain()
    tree = psx_beetle.adapt(psx_beetle.source(emit), work / 'machine')
    project = work / 'project'
    project.mkdir(parents=True, exist_ok=True)
    names = [name for name, _, _ in corpus.FILES]
    words = [w for name in names for w in opcodes_of(corpus.r3000_folder(folder) / (name + corpus.SUFFIX))]
    pairs = step_pairs(words)
    observed = {(address, word): psx_native.Observed(1, False) for word, address in pairs.items()}
    summary = psx_native.write(tree / 'mednafen' / 'psx' / 'cpu.c', observed, project)
    (project / 'steps.txt').write_text(''.join(f'{w:08x} {a:x}\n' for w, a in pairs.items()), encoding='ascii', newline='\n')
    (project / 'files.txt').write_text(''.join(n + '\n' for n in names), encoding='ascii', newline='\n')
    records = gte_records(corpus.gte_file(folder).read_text(encoding='utf-8'))
    (project / 'gte.bin').write_bytes(b''.join(GTE_RECORD.pack(*before, opcode, *after) for before, opcode, after in records))
    (project / 'CMakeLists.txt').write_text(cmake_project(ROOT / 'native' / 'psx_vector_checks', tree, summary['sources']),
                                            encoding='utf-8', newline='\n')
    emit(f"{len(words)} vectors, {len(pairs)} distinct opcodes, {summary['steps']} steps, {len(records)} GTE vectors; building.")
    binary = work / 'build'
    log = work / 'build.log'
    run([cmake, '-S', project, '-B', binary, '-G', generator, *cmake_target_args()], log=log, timeout=900)
    run([cmake, '--build', binary, '--target', 'psx_vectors', '--parallel', build_jobs()], log=log, timeout=3600)
    return {'executable': build_executable(binary, 'psx_vectors'), 'project': project, 'steps': summary,
            'vectors': len(words), 'opcodes': len(pairs), 'gte_vectors': len(records)}


def run_checks(built: dict, folder: Path, work: Path) -> dict:
    project = built['project']
    completed = subprocess.run([str(built['executable']), str(corpus.r3000_folder(folder)), str(project / 'files.txt'),
                                str(project / 'gte.bin'), str(project / 'steps.txt')],
                               capture_output=True, text=True, timeout=1800)
    (work / 'checks.log').write_text(completed.stdout + completed.stderr, encoding='utf-8')
    if completed.returncode:
        raise RuntimeError(f'the checks stopped ({completed.returncode}): {completed.stderr.strip()[-300:]}')
    return parse_log(completed.stdout)


def vector_offsets(data: bytes, count: int) -> list[int]:
    """Where the first `count` vectors of a file of the suite start."""
    at, out = 4, []
    state = 128 + 24 + 12 + 8
    for _ in range(count):
        out.append(at)
        cycles = struct.unpack_from('<I', data, at + 51 + 8 + state * 2)[0]
        at += 51 + 8 + state * 2 + 4 + cycles * 24
    return out


def corrupted(data: bytes) -> bytes:
    """A copy of a file of the suite with one expected value wrong in five of its first vectors: a register, HI, EPC, the PC, and
    the pending load (of a vector that has one: the value of no load is compared by nothing)."""
    out = bytearray(data)
    final = 51 + 8 + 128 + 24 + 12 + 8
    load = 128 + 24 + 12
    offsets = vector_offsets(data, 16)
    with_load = [at for at in offsets if 1 <= struct.unpack_from('<i', data, at + final + load)[0] <= 31][:1]
    others = [at for at in offsets if at not in with_load]
    plain = zip(others, (5 * 4, 128, 128 + 8, 128 + 20) + (() if with_load else (load + 4,)))      # r5, hi, EPC, PC
    for at, field in plain:
        out[at + final + field] ^= 0x01
    for at in with_load:
        out[at + final + load + 4] ^= 0x01
    return bytes(out)


def check_the_check(built: dict, folder: Path, work: Path) -> dict:
    """The checks must see a wrong answer: on a corrupted copy, the five vectors touched fail on both paths and only they, and so
    does a GTE vector with one wrong output."""
    probe = work / 'corrupted'
    probe.mkdir(exist_ok=True)
    name = 'LW'
    (probe / (name + corpus.SUFFIX)).write_bytes(corrupted((corpus.r3000_folder(folder) / (name + corpus.SUFFIX)).read_bytes()))
    (probe / 'files.txt').write_text(name + '\n', encoding='ascii', newline='\n')
    gte = bytearray((built['project'] / 'gte.bin').read_bytes()[:GTE_RECORD.size * 2])
    gte[GTE_RECORD.size + 65 * 4] ^= 0x01
    (probe / 'gte.bin').write_bytes(bytes(gte))
    completed = subprocess.run([str(built['executable']), str(probe), str(probe / 'files.txt'), str(probe / 'gte.bin'),
                                str(built['project'] / 'steps.txt')], capture_output=True, text=True, timeout=600)
    result = parse_log(completed.stdout)
    seen = {path: result[path][name]['total'] - result[path][name]['passed'] for path in ('interpreter', 'native')}
    gte_seen = result['gte']['total'] - result['gte']['passed']
    return {'corrupted_vectors': 5, 'seen': seen, 'gte_corrupted': 1, 'gte_seen': gte_seen,
            'detected': seen == {'interpreter': 5, 'native': 5} and gte_seen == 1}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    go = sub.add_parser('run')
    go.add_argument('--vectors', type=Path, required=True)
    go.add_argument('--work', type=Path, default=DEFAULT_WORK)
    go.add_argument('--baseline', type=Path)
    same = sub.add_parser('compare')
    same.add_argument('report', type=Path)
    same.add_argument('baseline', type=Path)
    args = parser.parse_args()
    if args.command == 'compare':
        wrong = regressions(json.loads(args.report.read_text(encoding='utf-8')), json.loads(args.baseline.read_text(encoding='utf-8')))
        print('\n'.join(wrong) or 'no regression')
        return 1 if wrong else 0
    wrong = corpus.problems(args.vectors)
    if wrong:
        print('\n'.join(wrong), file=sys.stderr)
        return 2
    args.work.mkdir(parents=True, exist_ok=True)
    built = build(args.vectors, args.work)
    results = run_checks(built, args.vectors, args.work)
    check = check_the_check(built, args.vectors, args.work)
    print('check of the check:', json.dumps(check))
    if not check['detected']:
        print('the checks do not see corrupted answers: this run proves nothing', file=sys.stderr)
        return 3
    report = {'schema': SCHEMA, 'statement': MODEL_STATEMENT, 'r3000_revision': corpus.R3000_REVISION, 'check_of_the_check': check,
              'tests_revision': corpus.TESTS_REVISION, 'corpus_sha256': corpus.CORPUS_SHA256, 'gte_sha256': corpus.GTE_SHA256,
              'steps': {k: built['steps'][k] for k in ('steps', 'instructions', 'handler_digest')}, **results,
              'totals': {path: summarise(results[path]) for path in ('interpreter', 'native')}}
    (args.work / 'report.json').write_text(json.dumps(report, indent=1), encoding='utf-8')
    print(json.dumps({'totals': report['totals'], 'gte': {k: results['gte'][k] for k in ('total', 'passed')} if results['gte'] else None}))
    if args.baseline:
        if not args.baseline.is_file():
            args.baseline.write_text(json.dumps(report, indent=1), encoding='utf-8')
            print('baseline recorded')
            return 0
        wrong = regressions(report, json.loads(args.baseline.read_text(encoding='utf-8')))
        print('\n'.join(wrong) or 'no regression')
        return 1 if wrong else 0
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
