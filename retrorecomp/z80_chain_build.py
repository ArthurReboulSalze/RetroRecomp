"""What every machine on the banked Z80 chain does to build its game, written once (the MSX family today; the SG-1000, the ColecoVision and
the machines after them next): the machine's own generator, the generated bodies of its sources, the corrected reference interpreter and
the step loop rendered for the machine, and the copy of its files beside the bodies.

The machine's own builder (retrorecomp/msx_build.py) keeps what is the machine's: its `game.toml`, how its media become the sources, its
project, its runs and its comparisons. The C side of the same split is native/z80_chain_glue.inc. Game role, group
`shares:z80_chain_glue` (retrorecomp/stamp_inputs.py). It imports nothing of the converter at load time.
"""
from __future__ import annotations

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
    # The machine's corrections of the copy: its M1 count, its NMI, its instruction costs and its 16-bit ports (z80_chain.Z80Machine).
    prepare_reference(work, engine, m1_counter=machine.counts_m1, nmi=machine.nmi, costs=machine.costs,
                      port16=machine.port_bits == 16)
    instrument_reference(work / 'runtime_reference.c', accept, machine, error)
    (work / loop_name).write_text(banked_runtime(machine, ASSETS), encoding='utf-8', newline='\n')


def stage_files(work: Path, groups: Iterable[tuple[Path, Iterable[str]]]) -> None:
    """Copy each named file of each source folder beside the generated bodies (flat, only what changed)."""
    for folder, names in groups:
        for name in names:
            write_if_changed(work / name, (folder / name).read_bytes())
