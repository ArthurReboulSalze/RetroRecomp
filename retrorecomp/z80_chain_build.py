"""What every machine on the banked Z80 chain does to build its game, written once (the MSX family today; the SG-1000, the ColecoVision and
the machines after them next): the machine's own generator, the generated bodies of its sources, the corrected reference interpreter and
the step loop rendered for the machine, and the copy of its files beside the bodies.

The machine's own builder (retrorecomp/msx_build.py) keeps what is the machine's: its `game.toml`, how its media become the sources, its
project, its runs and its comparisons. The C side of the same split is native/z80_chain_glue.inc. Game role, group
`shares:z80_chain_glue` (retrorecomp/stamp_inputs.py). It imports nothing of the converter at load time.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
from typing import Callable, Iterable, Sequence

BUILD_TIMEOUT = 2 * 3600

# The interpreter runs a DD/FD prefix before an opcode that does not use the index register by executing that opcode again as
# unprefixed, and takes back the second R increment; the M1 count of a machine with wait states must be taken back with it, or
# "DD C9" costs three wait states instead of two. cpu.prepare_reference(m1_counter=True) does it; this module only checks that it did.
DDFD_R_BACK = '    // R should not be incremented twice:\n    z->r = (z->r & 0x80) | ((z->r - 1) & 0x7f);'


def write_if_changed(path: Path, data: bytes) -> None:
    """Write `data` unless the file already holds it (a rebuild must not touch what did not change)."""
    if not path.is_file() or path.read_bytes() != data:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def generator(machine, emit: Callable[[str], None] = print) -> tuple[Path, Path]:
    """The machine's own Z80 -> C generator (built once, in its own folders, `Z80Machine.generator_tag`) and the engine checkout."""
    from . import core
    from .platforms import build_executable
    from .toolchain import suffix
    engine, _, _, _ = core.dependencies(emit, machine)
    return build_executable(core.ROOT / '.deps' / (machine.generator_build + suffix()), 'SmsRecomp'), engine


def instrument_reference(path: Path, accept: str, machine, error: type = RuntimeError) -> None:
    """A machine's addition to its copy of the reference interpreter: its own interrupt acceptance exported under the name `accept`
    (behaviour unchanged; the machine's reference runner reads /INT, and /NMI if it has the pin, after each instruction, as the native
    loop does). Refuses a copy whose M1 count, for a machine with wait states, is not taken back after the DD/FD fallback."""
    source = path.read_text(encoding='utf-8')
    if 'static inline void process_interrupts(z80* const z)' not in source:
        raise error('Pinned CPU source changed: process_interrupts')
    if machine.counts_m1:
        at = source.find(DDFD_R_BACK)
        if at < 0 or '--z80_m1_fetches;' not in source[at + len(DDFD_R_BACK):at + len(DDFD_R_BACK) + 40]:
            raise error('The reference CPU copy does not take the M1 count back after the DD/FD fallback '
                        '(cpu.prepare_reference with m1_counter).')
    if accept not in source:
        source += f'\nvoid {accept}(z80* const z) {{ process_interrupts(z); }}\n'
        path.write_text(source, encoding='utf-8', newline='\n')


def prepare_machine_reference(work: Path, engine: Path, machine) -> None:
    """The reference interpreter's copy (`runtime_reference.c` and `.h`) in `work`, corrected for the machine: its M1 count, its NMI, its
    instruction costs and its 16-bit ports (`z80_chain.Z80Machine`). The one place that turns a machine into the arguments of
    `cpu.prepare_reference`: the bodies' generation and the reference runner built alone both call it, so the two copies of the same
    machine can never differ. A machine with contention also gets the evaluator (banked_timed.h, and banked_timed.c, which its
    project compiles once: retrorecomp/z80_timed.py)."""
    from .cpu import prepare_reference
    prepare_reference(work, engine, m1_counter=machine.counts_m1, nmi=machine.nmi, costs=machine.costs, port16=machine.port_bits == 16,
                      contention=machine.contention)
    if machine.contention:
        from .z80_timed import render_header, render_source
        write_if_changed(work / 'banked_timed.h', render_header().encode('utf-8'))
        write_if_changed(work / 'banked_timed.c', render_source().encode('utf-8'))


def generate_bodies(work: Path, machine, cartridge: bytes, sources: Sequence[tuple[str, bytes]], game_toml: str,
                    emit: Callable[[str], None] = print, *, loop_name: str, accept: str,
                    keep_rom: bool = True, error: type = RuntimeError) -> None:
    """The bodies of `cartridge` and of every further source in `work/generated`, with the learned patterns (`native.patterns`).

    `sources` are the machine's other translated sources (its BIOS), in the order of its region map's source numbers after the
    cartridge, each a file name and its bytes; they are written in `work` and named in `banked.sources`. The reference interpreter's copy
    (`runtime_reference.c`, corrected for the machine: its M1 count, its NMI) exports its acceptance as `accept`, and the step loop
    rendered for the machine is written as `loop_name`."""
    from .cpu import prepare_cpu_headers, prepare_reference
    from .paths import ASSETS
    from .z80_chain import banked_runtime
    tool, engine = generator(machine, emit)
    (work / 'generated').mkdir(parents=True, exist_ok=True)
    for stale in (work / 'generated').glob('game_banked_ops_*.c'):
        stale.unlink()
    write_if_changed(work / 'rom.sms', cartridge)
    for name, data in sources:
        write_if_changed(work / name, data)
    (work / 'banked.sources').write_text(''.join(str((work / name).resolve()) + '\n' for name, _ in sources),
                                         encoding='utf-8', newline='\n')
    (work / 'game.toml').write_text(game_toml, encoding='utf-8', newline='\n')
    log = work / 'generate.log'
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    with log.open('w', encoding='utf-8') as out:
        result = subprocess.run([str(tool), '--game', str(work / 'game.toml'), '--banked-step'], stdout=out,
                                stderr=subprocess.STDOUT, timeout=BUILD_TIMEOUT, creationflags=flags)
    if not keep_rom:
        (work / 'rom.sms').unlink(missing_ok=True)
    if result.returncode:
        raise error(f'The Z80 generator failed (see {log}).')
    prepare_cpu_headers(work, engine)
    prepare_machine_reference(work, engine, machine)
    instrument_reference(work / 'runtime_reference.c', accept, machine, error)
    (work / loop_name).write_text(banked_runtime(machine, ASSETS), encoding='utf-8', newline='\n')


def stage_files(work: Path, groups: Iterable[tuple[Path, Iterable[str]]]) -> None:
    """Copy each named file of each source folder beside the generated bodies (flat, only what changed)."""
    for folder, names in groups:
        for name in names:
            write_if_changed(work / name, (folder / name).read_bytes())


def _flags() -> int:
    return subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0


def build_project(work: Path, targets: Sequence[str], cmake_text: str, *, sdl: bool = False,
                  emit: Callable[[str], None] = print) -> dict[str, Path]:
    """Configure and build `targets` of the machine's project in `work` (`cmake_text` is its CMakeLists.txt; `sdl` gives it the SDL2 of
    the converter, for the game). Returns each target's executable."""
    from . import core
    from .platforms import build_executable, sdl_install
    write_if_changed(work / 'CMakeLists.txt', cmake_text.encode('utf-8'))
    cmake, generator_kind = core.toolchain()
    log = work / 'build.log'
    extra = [f'-DCMAKE_PREFIX_PATH={Path(sdl_install()).as_posix()}'] if sdl else []
    core.run([cmake, '-S', work, '-B', work / 'build', '-G', generator_kind, *core.cmake_target_args(),
              '-DCMAKE_BUILD_TYPE=Release', *extra], log=log, emit=emit, timeout=BUILD_TIMEOUT)
    for target in targets:
        core.run([cmake, '--build', work / 'build', '--config', 'Release', '--target', target, '--parallel', core.build_jobs()],
                 log=log, emit=emit, timeout=BUILD_TIMEOUT)
    return {target: build_executable(work / 'build', target) for target in targets}


def run_program(exe: Path, args: list[str], image: bytes | None = None, timeout: int = 1800, error: type = RuntimeError) -> dict:
    """One headless run; its JSON report. The cartridge, when given, reaches the program on its standard input (`--cart -`)."""
    result = subprocess.run([str(exe), *args, *(['--cart', '-'] if image is not None else [])], input=image,
                            capture_output=True, timeout=timeout, creationflags=_flags())
    if result.returncode:
        raise error(f'{exe.name} failed: {result.stderr.decode(errors="replace").strip()[-500:]}')
    return json.loads(result.stdout)


def run_game(game: Path, options: list[str], report: Path, timeout: int = 1800, error: type = RuntimeError) -> dict:
    """The game's headless replay (`--headless`, from its own resources): its report, read from `report` (the game is linked for the
    Windows subsystem, so its standard output is not relied on)."""
    report.unlink(missing_ok=True)
    result = subprocess.run([str(game), '--headless', *options, '--report', str(report)], capture_output=True, timeout=timeout,
                            creationflags=_flags())
    if result.returncode or not report.is_file():
        raise error(f'{game.name} --headless failed (exit {result.returncode}): {result.stderr.decode(errors="replace").strip()[-300:]}')
    return json.loads(report.read_text(encoding='utf-8'))


def game_exit_code(game: Path, options: list[str], timeout: int = 120) -> int:
    """The exit code of a headless run of the game (a refused quick state ends it with 4)."""
    return subprocess.run([str(game), '--headless', *options], capture_output=True, timeout=timeout, creationflags=_flags()).returncode


def frame_rows(path: Path) -> list:
    """The rows of a --rows file as delivery_evidence.FrameRow (frame, picture, sound, audible, ram, pc)."""
    from .delivery_evidence import FrameRow
    rows = []
    for line in path.read_text(encoding='utf-8').splitlines()[1:]:
        frame, cpu, ram, picture, sound, samples, audible, pc = line.split(',')
        rows.append(FrameRow(int(frame), picture, sound=sound, audible=audible == '1', ram=ram, pc=pc))
    return rows


def differences(native: dict, reference: dict, compared: Sequence[str]) -> dict:
    """The compared fields that differ (a field missing on either side differs)."""
    return {key: (native.get(key), reference.get(key)) for key in compared
            if key not in native or key not in reference or native[key] != reference[key]}


def learn_passes(work: Path, runs: list[list[str]], *, generate: Callable[[], None], build_check: Callable[[], Path],
                 run_check: Callable[[Path, list[str], Path], int], passes: int = 3, workers: int = 1) -> tuple[Path, list[int]]:
    """Generate, build the headless check and run every route with learning, at most `passes` times: it stops when nothing fell back or
    nothing new was seen. `run_check(check, args, learned_file)` runs one route and returns its fallback steps; what the routes learned
    (the code the interpreter ran from RAM) is united in `native.patterns`, which the next generation translates with byte guards.
    Returns the check program and the fallback steps of each pass (summed over the routes)."""
    from .delivery_evidence import replay_routes
    patterns = work / 'native.patterns'
    counts: list[int] = []
    for _ in range(passes):
        generate()
        check = build_check()

        def trial(index):
            learned = work / f'learned-{index}.txt'
            learned.unlink(missing_ok=True)
            steps = run_check(check, [*runs[index], '--learn', str(learned)], learned)
            return steps, set(learned.read_text(encoding='utf-8').split()) if learned.is_file() else set()
        trials = replay_routes(range(len(runs)), trial, workers=workers)
        counts.append(sum(steps for steps, _ in trials))
        seen = set().union(*(found for _, found in trials))
        if not counts[-1] or not seen:
            break
        known = set(patterns.read_text(encoding='utf-8').split()) if patterns.is_file() else set()
        if seen <= known:
            break
        patterns.write_text(''.join(f'{line}\n' for line in sorted(known | seen)), encoding='utf-8', newline='\n')
    else:
        # The last pass still learned something: the bodies are generated once more, so the checked program (and the game built beside
        # it) hold every pattern the report counts.
        generate()
        check = build_check()
    return check, counts


def chain_project_cmake(prefix: str, project: str, *, reference_main: str, native_main: str, machine_sources: Sequence[str],
                        bodies: bool = True, definitions: Sequence[str] = (), game_lines: Sequence[str] = ()) -> str:
    """The CMakeLists.txt of a machine on the banked chain (staged flat in its work folder): the reference runner `<prefix>_reference`
    always; with `bodies` the object library of the generated bodies `<prefix>_bodies` and the headless native check `<prefix>_check`.
    `machine_sources` are the machine's C files (its own and the shared modules'), compiled into every program; `definitions` are added to
    the programs' compile definitions (a machine's own switches); `game_lines` are the machine's lines for its player (they come after
    the others and may use the bodies library). Pass `bodies=True` for a game too: the player needs the bodies."""
    machine = ' '.join(machine_sources)
    programs = f'{prefix}_reference {prefix}_check' if bodies else f'{prefix}_reference'
    lines = [
        'cmake_minimum_required(VERSION 3.20)', f'project({project} LANGUAGES C)', 'set(CMAKE_C_STANDARD 11)',
        'set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")',
        'if(MSVC)', '  add_compile_options(/utf-8 /wd4996 /wd4244 /wd4267)', 'endif()',
        f'add_executable({prefix}_reference {reference_main} {machine} runtime_reference.c)',
    ]
    if bodies:
        lines += [
            'file(GLOB bodies "generated/game_banked_ops_*.c")',
            f'add_library({prefix}_bodies OBJECT generated/game_banked_index.c ${{bodies}})',
            f'target_include_directories({prefix}_bodies PRIVATE "${{CMAKE_CURRENT_SOURCE_DIR}}" "${{CMAKE_CURRENT_SOURCE_DIR}}/generated")',
            f'target_compile_definitions({prefix}_bodies PRIVATE SMSRECOMP_BANKED_AOT)',
            f'add_executable({prefix}_check {native_main} {machine} runtime_reference.c $<TARGET_OBJECTS:{prefix}_bodies>)',
        ]
    lines += [
        f'foreach(target {programs})',
        '  target_include_directories(${target} PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}" "${CMAKE_CURRENT_SOURCE_DIR}/generated")',
        f'  target_compile_definitions(${{target}} PRIVATE SMSRECOMP_BANKED_AOT _CRT_SECURE_NO_WARNINGS{"".join(" " + d for d in definitions)})',
        '  if(NOT WIN32)', '    target_link_libraries(${target} PRIVATE m)', '  endif()',
        'endforeach()',
        *game_lines,
    ]
    return '\n'.join(lines) + '\n'


def build_reference_runner(work: Path, machine, *, accept: str, stage: Callable[[Path], None],
                           build: Callable[[Path, tuple[str, ...], Callable[[str], None]], dict[str, Path]], target: str,
                           emit: Callable[[str], None] = print, error: type = RuntimeError) -> Path:
    """The machine's reference runner alone, before any body is generated (what is chosen on the reference, such as the start of a route
    or a mapper, runs it): the corrected CPU headers when the machine uses the translated register file, the reference interpreter's copy corrected
    for the machine (M1 count, NMI), its interrupt acceptance exported
    as `accept`, the machine's files staged by `stage(work)`, then `build(work, (target,), emit)` (the machine's own build function,
    which writes its project). Returns the executable."""
    from .cpu import prepare_cpu_headers
    _, engine = generator(machine, emit)
    work.mkdir(parents=True, exist_ok=True)
    if machine.reference_state:
        # A reference main that uses the translated register file (`Z80Machine.reference_state`) includes the corrected CPU headers
        # (sms_runtime.h): the bodies' generation writes them, and the runner built alone, before any body, writes them itself.
        prepare_cpu_headers(work, engine)
    prepare_machine_reference(work, engine, machine)
    instrument_reference(work / 'runtime_reference.c', accept, machine, error)
    stage(work)
    return build(work, (target,), emit)[target]
