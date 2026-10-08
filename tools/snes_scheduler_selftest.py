"""Authored interrupt/WAI fixtures exercising the real SNES frame scheduler."""
from pathlib import Path
import json
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from smsrecomp import supernintendo
from smsrecomp.cartridge16 import read_snes_rom
from smsrecomp.console16 import prepare16, probe16, reference_differences
from smsrecomp.library import atomic_json


def cartridge(handler):
    rom = bytearray([0xea] * 0x8000)
    # Native mode, 8-bit registers, stack in WRAM, enable NMI, WAI/BRA.
    reset = bytes.fromhex('78 18 fb c2 30 a2 ff 1f 9a e2 30 a9 80 8d 00 21 a9 81 8d 00 42 cb 80 fd')
    rom[:len(reset)] = reset
    rom[0x100:0x100 + len(handler)] = handler
    rom[0x7fc0:0x7fd5] = b'RR SCHEDULER FIXTURE'.ljust(21, b' ')
    rom[0x7fd5:0x7fdc] = bytes((0x20, 0, 5, 0, 1, 0, 0))
    rom[0x7fdc:0x7fe0] = bytes.fromhex('cb ed 34 12')
    rom[0x7fea:0x7fec] = bytes.fromhex('00 81')
    rom[0x7ffc:0x7ffe] = bytes.fromhex('00 80')
    return rom


def main():
    work = ROOT / '.build/snes-scheduler-selftest'
    work.mkdir(parents=True, exist_ok=True)
    results = []
    for name, handler in (
        ('wai-in-interrupt', bytes.fromhex('ee 00 00 cb 40')),
        ('long-interrupt', bytes.fromhex('ee 00 00 ea 80 fd')),
        # Rewrite the real interrupt return frame to resume another thread.
        # With S=$1FFB, PCL/PCH live at $1FFD/$1FFE. No host-PC shortcut may
        # discard the destination restored by RTI.
        ('rti-thread-switch', bytes.fromhex('a9 00 8d fd 1f a9 82 8d fe 1f 40')),
    ):
        folder = work / name
        folder.mkdir(exist_ok=True)
        path = folder / 'authored.sfc'
        authored = cartridge(handler)
        if name == 'rti-thread-switch':
            authored[0x200:0x207] = bytes.fromhex('ee 01 00 cb 80 fa ea')
        path.write_bytes(authored)
        rom = read_snes_rom(path)
        profile = {'id': 'fixture-' + name, 'title': name, 'legacy_functions': False}
        # Only this ROM-free test opts into its authored fixture; no fixture
        # identity is added to the application's cartridge catalogue.
        with patch.dict(supernintendo.PROFILES, {rom.sha256: profile}):
            exe = prepare16(path, 'snes', title=name, emit=lambda text: None)
        native = probe16(exe, folder, 40)
        reference = probe16(exe, folder, 40, reference=True)
        differences = reference_differences('snes', native, reference)
        assert not differences, (name, differences)
        # The first field ends at V=225, followed by 39 full fields. There is
        # no DMA in either fixture, so only an instruction's bus overshoot is
        # allowed. The old interrupt loop ran to its step cap instead.
        expected = 225 * 1364 + 39 * 262 * 1364
        assert abs(native['master_cycles'] - expected) < 64, (name, native['master_cycles'], expected)
        # None of these authored cartridges reads or writes an APU port.
        # Its independent clock must still run for every completed frame,
        # including time parked in WAI, from power-on rather than first I/O.
        apu_expected = 40 * 17088
        assert apu_expected <= native['apu_cycles'] < apu_expected + 64, (name, native['apu_cycles'])
        assert not native['audio_output_underflows'] and not native['audio_ring_dropped'], name
        assert not native['interpreted_opcodes'], name
        assert 0 < native['native_entries'] < 1000000, name
        if name == 'wai-in-interrupt':
            assert native['native_entries'] < 300, name  # parked ticks aren't retired instructions
            assert native['cpu_pc'] == 0x8104, name  # the instruction after WAI
        if name == 'rti-thread-switch':
            assert native['cpu_pc'] == 0x8204, name  # restored guest destination
        results.append({'fixture': name, 'frames': 40, 'differences': differences,
            'expected_master_cycles': expected, 'master_cycles': native['master_cycles'],
            'native_entries': native['native_entries'], 'interpreted_opcodes': native['interpreted_opcodes'],
            'cpu_pc': native['cpu_pc'], 'apu_cycles': native['apu_cycles'],
            'apu_without_port_io': True, 'passed': True})
    atomic_json(work / 'results.json', results)
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
