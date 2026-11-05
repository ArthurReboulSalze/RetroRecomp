"""What the Master System / Game Gear conversion records about the delivered file: liveness (gate G8) and the packed replay (gate G5).

The shared steps are `delivery_evidence` (docs/QUALIFICATION.md, "Shared evidence helper"); this module is what is the Sega
consoles': how a line of the runner's `--vdp-trace` is read, which report keys the numbers go into, which route must show a
moving picture, and the text of the refusals. Nothing here runs a game itself: `core.convert` hands in the callback that starts the
delivered file on a route.

The trace (`runtime_glue.c`, `--vdp-trace FILE`) has one line per frame, with a header
`frame,vram_h,cram_h,reg_h,ram_h,r8,r9,r0,r1,sp,pixels_h,psg_h,psg_nz`. The picture is the hash of the frame as it is drawn
(`pixels_h`), the sound block is the hash of the PSG's stereo samples of the frame (`psg_h`), a frame is audible when the PSG
produced a non-zero sample in it (`psg_nz`), the RAM state is `ram_h`. The Z80 program counter is not in the trace, so the record
has no `distinct_program_counters` (None, never 0). A trace without the sound columns (an old build) gives None for the sound keys.

Only the `play` route must show a moving picture: it is the route that presses the buttons. The `demo` route presses none, and a game
that waits for a button on a still title shows one picture on it. A frozen `play` route means the game never started or is stuck.
Sound keeps the rule it had: a silent route is reported (`audible_frames`, `last_audible_frame`), never refused. The record is
evidence that the picture and the sound change on a route; it says nothing about what the picture shows or how far into the game the
route goes, and nothing about hardware fidelity or latency.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Iterator

from .core import ConversionError
from .delivery_evidence import (FrameRow, deliver_packed, liveness_summary, replay_packed, report_fields,
                                require_moving_picture)

# The report keys of a route's liveness, from the common record of delivery_evidence.
LIVENESS_FIELDS = {'frames': 'frames', 'distinct_pictures': 'distinct_pictures', 'picture_changes': 'picture_changes',
                   'last_picture_change_frame': 'last_picture_change_frame', 'audible_frames': 'audible_frames',
                   'last_audible_frame': 'last_audible_frame', 'distinct_sound_blocks': 'distinct_sound_blocks',
                   'distinct_ram_states': 'distinct_ram_states'}
MAIN_ROUTE = 'play'
TRACE_COLUMNS = ('frame', 'pixels_h', 'psg_h', 'psg_nz', 'ram_h')


def trace_rows(trace: Path) -> Iterator[FrameRow]:
    """The per-frame rows of a route's trace, for `delivery_evidence.liveness_summary`."""
    lines = Path(trace).read_text(encoding='ascii').splitlines()
    if not lines:
        return
    header = lines[0].split(',')
    column = {name: header.index(name) for name in TRACE_COLUMNS if name in header}
    for name in ('frame', 'pixels_h'):
        if name not in column:
            raise ConversionError(f'Sega trace {Path(trace).name} has no {name} column.')
    for line in lines[1:]:
        fields = line.split(',')
        if len(fields) != len(header) or not fields[column['frame']].isdigit():
            continue
        sound = fields[column['psg_h']] if 'psg_h' in column else None
        audible = None
        if 'psg_nz' in column and fields[column['psg_nz']].isdigit():
            audible = int(fields[column['psg_nz']]) > 0
        ram = fields[column['ram_h']] if 'ram_h' in column else None
        yield FrameRow(int(fields[column['frame']]), fields[column['pixels_h']], sound=sound, audible=audible, ram=ram)


def route_liveness(trace: Path) -> dict:
    """Picture and sound activity of one route, read from its trace (see the module text for what it does not say)."""
    return report_fields(liveness_summary(trace_rows(trace)), LIVENESS_FIELDS)


STILL_ROUTE_OK = 'RETRO_RECOMP_STILL_ROUTE_OK'


def require_main_route_moving(scenario: str, liveness: dict, directory: Path) -> None:
    """Refuse a conversion whose main (`play`) route showed a picture that never changed.

    Developer checks that convert a program of a few instructions (`tools/cpu_selftest.py`: it has no picture, only a result in RAM)
    set `RETRO_RECOMP_STILL_ROUTE_OK=1`; a player's conversion never does."""
    if os.environ.get(STILL_ROUTE_OK) == '1':
        return
    if scenario == MAIN_ROUTE:
        require_moving_picture(liveness, lambda: ConversionError(
            f'Master System / Game Gear {scenario}: the picture never changed during the route; the game is stuck or never '
            f'started. Previous export preserved; see {directory}.'))


def replay_delivered(executable: Path, packed: Path, directory: Path, checks: list, references: dict,
                     replay: Callable[[Path, Path, dict], dict], differences: Callable[[dict, dict], list],
                     emit: Callable[[str], None]):
    """Compress a copy of the build as publication does, replay it on every route and compare each result with the reference of
    the same route: the fresh reference run of the banked engine, or the final pass of the same build for the "functions" engine.

    `replay(packed, directory, check)` starts the copy on the route of `check` (the same arguments as the probe that made the native
    result), writing its trace in `directory`, and returns the probe's result; `differences(result, reference)` lists the checks
    that failed (empty when equal). Returns the delivered file (`validation_fields()` and `report_fields()` may be written only once
    it matched on every route) and the replay results by route, each with its `liveness`."""
    delivered = deliver_packed(executable, packed, 'Master System / Game Gear', emit)
    directory.mkdir(parents=True, exist_ok=True)
    results: dict = {}

    def run(check: dict) -> dict:
        run_directory = directory / check['scenario']
        result = replay(packed, run_directory, check)
        result['liveness'] = route_liveness(run_directory / 'vdp.csv')
        result['directory'] = str(run_directory)
        results[check['scenario']] = result
        return result

    def same(check: dict, result: dict) -> bool:
        return not differences(result, references[check['scenario']])

    def mismatch(check: dict) -> Exception:
        fields = ', '.join(differences(results[check['scenario']], references[check['scenario']])[:6])
        return ConversionError(f"Master System / Game Gear {check['scenario']}: the delivered (compressed) executable differs from "
                               f'its reference ({fields}). Previous export preserved; see {directory}.')

    replay_packed(delivered, checks, run, same=same, mismatch=mismatch)
    for check in checks:
        require_main_route_moving(check['scenario'], results[check['scenario']]['liveness'], directory)
    return delivered, results


# ---------------------------------------------------------------- the report's devices and counters (gate G2)

def codemasters_header(rom: bytes) -> bool:
    """Whether the cartridge carries a Codemasters header: the checksum word at $7FE6 and its complement at $7FE8 add up to $10000.

    A header-based reading of the dump (the Master System has no mapper register to read back); an all-zero or all-one pair does not
    count. It names the cartridge's mapper in the report. The runtime does not model the Codemasters registers (its switch stays
    off), so such a cartridge is converted and compared with the reference, but it is not a validated mapper."""
    if len(rom) < 0x8000:
        return False
    checksum = int.from_bytes(rom[0x7FE6:0x7FE8], 'little')
    inverse = int.from_bytes(rom[0x7FE8:0x7FEA], 'little')
    return checksum not in (0, 0xFFFF) and (checksum + inverse) & 0xFFFF == 0


def hardware_devices(system_id: str, rom: bytes) -> list:
    """The `hardware_devices` the report stores for a Master System or Game Gear cartridge: the mapper, the video chip and the sound chip.

    None of them is a CPU with a program, so none has an interpreter counter (the schema reads `fallback_present` as not applicable,
    not as zero); each says it is a C model of the runtime and that its hardware fidelity is not validated."""
    codemasters = codemasters_header(rom)
    game_gear = system_id == 'gg'
    mapper = {'id': 'codemasters' if codemasters else 'sega', 'kind': 'cartridge_mapper',
              'mode': 'not_modelled' if codemasters else 'c_model',
              'details': {'rom_bytes': len(rom), 'rom_banks_16k': -(-len(rom) // 0x4000), 'slots': 3,
                          'registers': '$FFFD-$FFFF (the Sega mapper)', 'codemasters_header_found': codemasters,
                          'codemasters_registers_modelled': False, 'cartridge_ram_modelled': False,
                          'translated_from_rom': False,
                          'interpreter': 'none: the mapper is C code in the runtime, driven by the writes the program makes',
                          'hardware_fidelity_validated': False}}
    video = {'id': 'vdp_mode4', 'kind': 'video_unit', 'mode': 'c_model',
             'details': {'display': 'mode 4, scanline renderer', 'visible_pixels': [160, 144] if game_gear else [256, 192],
                         'sprites_per_line': 8, 'translated_from_rom': False,
                         'interpreter': 'none: the video chip is C code in the runtime, not a CPU with a program',
                         'known_limits': ['no pixel-clock timing (palette changes are taken at the line)', 'no other display modes'],
                         'hardware_fidelity_validated': False}}
    sound = {'id': 'sn76489', 'kind': 'audio_unit', 'mode': 'c_model',
             'details': {'channels': 4, 'stereo_ports': game_gear, 'fm_unit_modelled': False, 'translated_from_rom': False,
                         'interpreter': 'none: the sound chip is C code in the runtime, not a CPU with a program',
                         'hardware_fidelity_validated': False}}
    return [mapper, video, sound]


def _runtime_log(report: dict, scenario: str) -> str:
    """The log of the last pass of one route, from the kept build the report names ('' when it was removed)."""
    build = Path(str(report.get('build_directory') or ''))
    final = len(report.get('history') or ()) // max(1, len(report.get('final_checks') or ()))
    try:
        return (build / 'checks' / f'pass{final}_{scenario}' / 'runtime.log').read_text(encoding='utf-8', errors='replace')
    except OSError:
        return ''


def step_counters(log: str) -> dict:
    """The banked engine's instruction counts from a run's log (`[banked] native_steps=… halt_steps=…`, `[banked-guards]`).

    `native_instructions` counts every instruction the generated code completed, byte-guarded RAM encodings included
    (`guarded_native_instructions`); `halted_steps` the steps spent halted. Empty for the "functions" engine and for a log without
    the lines: no counter is invented."""
    import re
    found = re.search(r'\[banked\] native_steps=(\d+) halt_steps=(\d+)', log)
    if not found:
        return {}
    result = {'native_instructions': int(found[1]), 'halted_steps': int(found[2])}
    guarded = re.search(r'\[banked-guards\] native_steps=(\d+)', log)
    if guarded:
        result['guarded_native_instructions'] = int(guarded[1])
    return result


STALLED_SHARE = 0.10    # a route whose picture last changed in the first tenth of its frames is reported as stalled


def route_warnings(final_checks: list) -> list:
    """Words about the routes whose picture stopped changing early (the game may never have started on them).

    The conversion refuses a main route whose picture never changes; a route that changes a few times and then stays still is
    accepted and compared with the reference like any other, and this list says so instead of leaving it to be read from the
    numbers. A threshold on the last change, not a verdict on the game: a title waiting for a button is still a start."""
    warnings = []
    for row in final_checks:
        live = row.get('liveness') or {}
        frames, last = live.get('frames'), live.get('last_picture_change_frame')
        if frames and last is not None and last < frames * STALLED_SHARE:
            warnings.append(f"{row.get('scenario')}: the picture stopped changing at frame {last} of {frames}")
    return warnings


def enrich_report(report_path: Path, system_id: str, rom: bytes) -> dict:
    """Add what the conversion's own report lacks (gate G2) and write it again through the common builder.

    `hardware_devices` for the mapper, video and sound chips, and on the banked engine the instruction counts of each final route.
    Nothing a conversion decides is touched; the keys are only added."""
    import json
    from .report_schema import write_report
    report = json.loads(Path(report_path).read_text(encoding='utf-8'))
    report['hardware_devices'] = hardware_devices(system_id, rom)
    report['route_warnings'] = route_warnings(report.get('final_checks') or [])
    if report.get('backend') == 'banked':
        for row in report.get('final_checks') or ():
            row.update(step_counters(_runtime_log(report, row.get('scenario', ''))))
    return write_report(report_path, report)
