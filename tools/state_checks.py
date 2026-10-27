"""Common, dependency-free pieces of the fresh-process state checks.

These helpers intentionally know nothing about build systems or individual
console state formats: the checks keep their own validation gates.
"""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import subprocess
from typing import Iterable, Mapping


GUEST_FIELDS = ('cpu_hash','ram_hash','vram_hash','cram_hash','vsram_hash',
                'sram_hash','sram_bytes','sram_base','sram_end','sram_stride','sram_battery','sram_control','sram_mapping',
                'eeprom_kind','eeprom_writes','cartridge_state_hash',
                'vdp_register_hash','z80_ram_hash','z80_cpu_hash','ym_timer_hash',
                'cpu_cycles','master_cycles','cpu_pc','cpu_sr','cpu_usp','cpu_ssp',
                'spc_pc','spc_cpu_hash','apu_state_hash','dsp_state_hash',
                'visible_width','visible_height','active_raster_height','output_row_density','field_parity',
                'cpu_stopped','cpu_prefetch_hash','oam_hash','high_oam_hash','apu_ram_hash','apu_cycles',
                'cartridge_chip','coprocessor_mode','coprocessor_state_hash','coprocessor_failed')

START_FRAMES = (180, 300, 480, 550, 660, 720)
ROUTE_REPEAT_FRAME = 800
ROUTE_REPEAT_STEP = 30
TRACE_METADATA_FIELDS = ('native', 'interpreted')


def run_report_trace(exe, output, name, frames, *args, timeout=300):
    """Run one headless build and return its JSON report and CSV trace."""
    report = output / (name + '.json')
    trace = output / (name + '.csv')
    command = [str(exe), '--frames', str(frames), '--report', str(report),
               '--trace', str(trace), *map(str, args)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f'{name}: exit {result.returncode}\n{result.stderr[-3000:]}')
    with trace.open(newline='') as file:
        rows = list(csv.DictReader(file))
    return json.loads(report.read_text()), rows


def route_controls(total: int, *, md: bool = False, player_two: int = 0) -> list[tuple[int, int, int]]:
    """The shared menu-and-gameplay route used by F8/F9 cross checks.

    The repeated controls preserve the historical fire predicate byte for byte.
    """
    start, right, fire = (128, 8, 16) if md else (8, 128, 1)
    events = {0: 0}
    for frame in START_FRAMES:
        if frame < total:
            events[frame] = start
        if frame + 2 < total:
            events[frame + 2] = 0
    for frame in range(ROUTE_REPEAT_FRAME, total, ROUTE_REPEAT_STEP):
        events[frame] = right | (fire if frame % 90 == 0 else 0)
    return [(frame, value, player_two) for frame, value in sorted(events.items())]


def controls_text(controls: Iterable[tuple[int, int, int]]) -> str:
    return ''.join(f'{frame} {player_one} {player_two}\n'
                   for frame, player_one, player_two in controls)


def write_controls(path: Path, controls: Iterable[tuple[int, int, int]]) -> Path:
    path.write_text(controls_text(controls), encoding='ascii')
    return path


def parse_two_player_script(source: Path, total: int) -> list[tuple[int, int, int]]:
    """Validate a bounded two-player script and keep events inside the run."""
    controls = []
    for line in source.read_text(encoding='ascii').splitlines():
        if not line.strip():
            continue
        fields = line.split()
        if len(fields) != 3:
            raise ValueError('Replay inputs require frame, player 1 and player 2.')
        frame, player_one, player_two = map(int, fields)
        if frame < 0 or not 0 <= player_one <= 65535 or not 0 <= player_two <= 65535:
            raise ValueError('Replay input is outside its bounded format.')
        if frame < total:
            controls.append((frame, player_one, player_two))
    if not controls or controls[0][0] != 0 or any(
            a[0] >= b[0] for a, b in zip(controls, controls[1:])):
        raise ValueError('Replay inputs must start at zero and have increasing frames.')
    return controls


def controls_before(controls: Iterable[tuple[int, int, int]], frame: int
                    ) -> list[tuple[int, int, int]]:
    return [event for event in controls if event[0] < frame]


def trace_columns(rows: Iterable[Mapping[str, object]]) -> list[str]:
    """Rows are dictionaries from csv.DictReader; at least one row is required."""
    first = next(iter(rows), None)
    if first is None:
        return []
    return [key for key in first if key not in TRACE_METADATA_FIELDS]


def first_trace_mismatch(previous, future, columns=None):
    if columns is None:
        columns = trace_columns(previous)
    return next((index for index, (a, b) in enumerate(zip(previous, future))
                 if any(a[column] != b[column] for column in columns)), None)


def guest_differences(baseline: Mapping[str, object], restored: Mapping[str, object]
                      ) -> list[str]:
    return [field for field in GUEST_FIELDS
            if field in baseline and baseline[field] != restored[field]]


def run_captured(command: Iterable[object], *, cwd: Path | None = None, timeout: int = 120):
    """Run a headless self-test child with no console window on Windows."""
    return subprocess.run([str(argument) for argument in command], cwd=cwd,
                          capture_output=True, text=True, timeout=timeout,
                          creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)


def final_json(text: str):
    """Read the JSON status line emitted by the C self-test harnesses."""
    return json.loads(text.strip().splitlines()[-1])
