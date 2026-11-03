"""Authored SA-1 cartridge: synchronisation of the S-CPU and the SA-1, message and IRQ in both directions, BW-RAM.

One 32 KiB cartridge (map $23, type $35, 8 KiB of BW-RAM). The S-CPU copies a small program into the SA-1's I-RAM,
releases the SA-1 and checks, in order:
  * the SA-1 runs (a 16-bit counter in I-RAM moves);
  * a message and an IRQ from the S-CPU reach the SA-1 (message nibble, IRQ flag cleared, handler run once);
  * an IRQ and a message from the SA-1 reach the S-CPU (handler run once, message nibble, flag cleared);
  * both CPUs read what the other wrote in BW-RAM ($6000 for the S-CPU, $40:0000 for the SA-1).
The verdict is the program counter the S-CPU spins on (PASS or FAIL). The run must also show a coprocessor that is never
behind the S-CPU when the S-CPU reaches it, and a rate of one SA-1 instruction per ten master clocks for its two-instruction
counter loop (INC dp on 16 bits, 7 cycles, and BRA, 3 cycles, at one cycle per two master clocks). The native run must equal
the fully interpreted one. This checks the adapter, not independent hardware accuracy.
"""
from __future__ import annotations
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp import supernintendo  # noqa: E402
from retrorecomp.cartridge16 import read_snes_rom  # noqa: E402
from retrorecomp.console16 import prepare16, probe16, reference_differences  # noqa: E402
from retrorecomp.library import atomic_json  # noqa: E402
from tools.console16_state_selftest import check as state_check  # noqa: E402

SA1_CODE_AT, SA1_COPY = 0x8200, 0xc0
COUNTER_LOOP_MASTER_CLOCKS_PER_INSTRUCTION = 10


class Asm:
    """Just enough 65816 for the fixture: bytes, labels and 8-bit relative branches."""
    def __init__(self, origin):
        self.origin, self.data, self.labels, self.fixups, self.jumps = origin, bytearray(), {}, [], []

    def raw(self, *values):
        self.data.extend(values)

    def mark(self, name):
        self.labels[name] = self.origin + len(self.data)

    def branch(self, opcode, name):
        self.data.append(opcode)
        self.fixups.append((len(self.data), name))
        self.data.append(0)

    def jump(self, name):
        self.data.append(0x4c)
        self.jumps.append((len(self.data), name))
        self.data.extend((0, 0))

    def fail_if_ne(self, name):
        """BEQ over a JMP: a failure label may be further than a relative branch reaches."""
        self.raw(0xf0, 3)
        self.jump(name)

    def fail_if_eq(self, name):
        self.raw(0xd0, 3)
        self.jump(name)

    def lda(self, value): self.raw(0xa9, value)
    def sta(self, address): self.raw(0x8d, address & 255, address >> 8)
    def finish(self):
        for position, name in self.fixups:
            offset = self.labels[name] - (self.origin + position + 1)
            assert -128 <= offset <= 127, (name, offset)
            self.data[position] = offset & 255
        for position, name in self.jumps:
            self.data[position:position + 2] = self.labels[name].to_bytes(2, 'little')
        return bytes(self.data)


def sa1_program():
    a = Asm(0x0100)
    a.raw(0x18, 0xfb)                       # CLC, XCE: native mode
    a.raw(0xe2, 0x20)                       # SEP #$20: 8-bit A for the registers
    a.lda(0xff); a.sta(0x222a)              # CIWP: the SA-1 may write all of I-RAM (protected after a reset)
    a.lda(0x90); a.sta(0x220a)              # SIE: the S-CPU's IRQ and NMI may interrupt the SA-1
    a.lda(0x80); a.sta(0x2227)              # BW-RAM write enable (SA-1 side)
    a.raw(0x58)                             # CLI
    a.raw(0xc2, 0x20)                       # REP #$20: 16-bit A, the counter loop
    a.mark('loop'); a.raw(0xe6, 0x00)       # INC $00 (16-bit in I-RAM)
    a.branch(0x80, 'loop')                  # BRA loop
    code = a.finish()
    h = Asm(0x0140)                         # the SA-1's IRQ handler
    h.raw(0xe2, 0x30)                       # SEP #$30
    h.raw(0xad, 0x01, 0x23)                 # LDA $2301: SFR, message nibble from the S-CPU
    h.raw(0x29, 0x0f); h.raw(0x85, 0x02)    # AND #$0F, STA $02
    h.lda(0x80); h.sta(0x220b)              # SIC: clear the S-CPU-to-SA-1 IRQ flag
    h.raw(0xe6, 0x04)                       # INC $04: handled once
    h.raw(0xaf, 0x00, 0x00, 0x40)           # LDA $400000: BW-RAM as the S-CPU left it
    h.raw(0x85, 0x06)                       # STA $06
    h.lda(0x5a); h.raw(0x8f, 0x01, 0x00, 0x40)   # STA $400001: BW-RAM write by the SA-1
    h.lda(0x87); h.sta(0x2209)              # SCNT: IRQ to the S-CPU, message 7
    h.raw(0x40)                             # RTI
    n = Asm(0x0180)                         # the SA-1's NMI handler (an edge: once per 0 to 1 of CCNT bit 4)
    n.raw(0xe2, 0x30)                       # SEP #$30
    n.lda(0x10); n.sta(0x220b)              # SIC: clear the S-CPU-to-SA-1 NMI flag
    n.raw(0xe6, 0x08)                       # INC $08: handled once per edge
    n.raw(0x40)                             # RTI
    image = bytearray(SA1_COPY)
    image[:len(code)] = code
    handler = h.finish()
    image[0x40:0x40 + len(handler)] = handler
    nmi = n.finish()
    image[0x80:0x80 + len(nmi)] = nmi
    return bytes(image)


def scpu_program():
    a = Asm(0x8000)
    a.raw(0x78, 0x18, 0xfb)                 # SEI, CLC, XCE
    a.raw(0xc2, 0x10, 0xe2, 0x20)           # REP #$10, SEP #$20
    a.raw(0xa2, 0xff, 0x1f, 0x9a)           # LDX #$1FFF, TXS
    a.lda(0x20); a.sta(0x2200)              # CCNT: SA-1 held in reset
    a.lda(0xff); a.sta(0x2229)              # SIWP: the S-CPU may write all of I-RAM
    a.lda(0x80); a.sta(0x2226)              # BWE: the S-CPU may write BW-RAM
    a.raw(0xa2, 0x00, 0x00)                 # LDX #0
    a.mark('copy')
    a.raw(0xbf, SA1_CODE_AT & 255, SA1_CODE_AT >> 8, 0x00)   # LDA $008100,X
    a.raw(0x9d, 0x00, 0x31)                 # STA $3100,X (I-RAM)
    a.raw(0xe8, 0xe0, SA1_COPY, 0x00)       # INX, CPX #$0080
    a.branch(0xd0, 'copy')
    a.lda(0x00); a.sta(0x2203); a.lda(0x01); a.sta(0x2204)   # CRV = $0100
    a.lda(0x40); a.sta(0x2207); a.lda(0x01); a.sta(0x2208)   # CIV = $0140
    a.lda(0x80); a.sta(0x2205); a.lda(0x01); a.sta(0x2206)   # CNV = $0180
    a.lda(0x80); a.sta(0x2201)              # SIE: the SA-1's IRQ may interrupt the S-CPU
    a.lda(0xa5); a.sta(0x6000)              # BW-RAM $6000 = $A5
    a.raw(0xee, 0x20, 0x60)                 # INC $6020: a counter in the save, once per boot
    a.raw(0x9c, 0x20, 0x00, 0x9c, 0x21, 0x00)   # STZ $20, STZ $21 (message, handled count)
    a.lda(0x00); a.sta(0x2200)              # release the SA-1
    a.raw(0xa2, 0x00, 0x20)                 # LDX #$2000: let it run
    a.mark('wait1'); a.raw(0xca); a.branch(0xd0, 'wait1')
    a.raw(0xad, 0x00, 0x30, 0x0d, 0x01, 0x30)   # LDA $3000, ORA $3001: the 16-bit counter moved
    a.fail_if_eq('fail_counter')
    a.raw(0x58)                             # CLI
    a.lda(0x85); a.sta(0x2200)              # CCNT: IRQ to the SA-1, message 5
    a.raw(0xa2, 0x00, 0x40)                 # LDX #$4000
    a.mark('wait2'); a.raw(0xca); a.branch(0xd0, 'wait2')
    # An NMI from the S-CPU is an edge: one handler run for the 0 to 1 of CCNT bit 4, none while the bit stays 1, one more
    # after the bit went down and up again (before the fix of the engine the NMI entry repeated before any handler instruction).
    a.lda(0x10); a.sta(0x2200)              # CCNT bit 4: NMI to the SA-1
    a.raw(0xa2, 0x00, 0x08)                 # LDX #$0800
    a.mark('wait_nmi1'); a.raw(0xca); a.branch(0xd0, 'wait_nmi1')
    a.raw(0xad, 0x08, 0x30, 0xc9, 0x01)     # LDA $3008, CMP #1
    a.fail_if_ne('fail_sa1_nmi_once')
    a.lda(0x10); a.sta(0x2200)              # written again with the bit still 1: no new edge
    a.raw(0xa2, 0x00, 0x08)
    a.mark('wait_nmi2'); a.raw(0xca); a.branch(0xd0, 'wait_nmi2')
    a.raw(0xad, 0x08, 0x30, 0xc9, 0x01)
    a.fail_if_ne('fail_sa1_nmi_repeated_without_edge')
    a.lda(0x00); a.sta(0x2200); a.lda(0x10); a.sta(0x2200)   # down and up: a new edge
    a.raw(0xa2, 0x00, 0x08)
    a.mark('wait_nmi3'); a.raw(0xca); a.branch(0xd0, 'wait_nmi3')
    a.raw(0xad, 0x08, 0x30, 0xc9, 0x02)
    a.fail_if_ne('fail_sa1_nmi_second_edge')
    # The SA-1 returns from its handler to the counter loop: the counter still moves.
    a.raw(0xad, 0x00, 0x30, 0x8d, 0x30, 0x00)   # LDA $3000, STA $30
    a.raw(0xa2, 0x23, 0x01)                     # LDX #$0123 (not a multiple of the counter's 256-step period)
    a.mark('wait3'); a.raw(0xca); a.branch(0xd0, 'wait3')
    a.raw(0xad, 0x00, 0x30, 0xcd, 0x30, 0x00)   # LDA $3000, CMP $30
    a.fail_if_eq('fail_counter_stopped_after_irq')
    checks = (('s_cpu_irq_handled_once', 0x0021, 1), ('message_from_sa1', 0x0020, 7), ('message_to_sa1', 0x3002, 5),
              ('sa1_irq_handled_once', 0x3004, 1), ('bwram_s_cpu_to_sa1', 0x3006, 0xa5), ('bwram_sa1_to_s_cpu', 0x6001, 0x5a))
    for name, address, value in checks:
        a.raw(0xad, address & 255, address >> 8)    # LDA address
        a.raw(0xc9, value)                          # CMP #value
        a.fail_if_ne('fail_' + name)
    a.mark('pass'); a.branch(0x80, 'pass')
    for name in (('counter', 'counter_stopped_after_irq', 'sa1_nmi_once', 'sa1_nmi_repeated_without_edge',
                  'sa1_nmi_second_edge') + tuple(name for name, _, _ in checks)):
        a.mark('fail_' + name); a.branch(0x80, 'fail_' + name)
    code = a.finish()
    return code, a.labels


def cartridge(pal):
    from tools.snes_scheduler_selftest import cartridge as base
    rom = base(b'', pal)
    code, labels = scpu_program()
    assert len(code) < SA1_CODE_AT - 0x8000, len(code)
    rom[0:len(code)] = code
    rom[SA1_CODE_AT - 0x8000:SA1_CODE_AT - 0x8000 + SA1_COPY] = sa1_program()
    # S-CPU IRQ handler
    h = Asm(0x8300)
    h.raw(0xad, 0x00, 0x23, 0x29, 0x0f)     # LDA $2300, AND #$0F: the SA-1's message
    h.raw(0x8d, 0x20, 0x00)                 # STA $20
    h.lda(0x80); h.sta(0x2202)              # SIC: clear the SA-1-to-S-CPU IRQ flag
    h.raw(0xee, 0x21, 0x00, 0x40)           # INC $21, RTI
    handler = h.finish()
    rom[0x300:0x300 + len(handler)] = handler
    # Header: map $23, type $35, 32 KiB, 8 KiB of BW-RAM.
    rom[0x7fc0:0x7fd5] = b'RR SA1 FIXTURE'.ljust(21, b' ')
    rom[0x7fd5:0x7fdc] = bytes((0x23, 0x35, 5, 3, 2 if pal else 1, 0, 0))
    rom[0x7ffc:0x7ffe] = bytes((0x00, 0x80))
    rom[0x7fee:0x7ff0] = bytes((0x00, 0x83))
    rom[0x7fea:0x7fec] = bytes((0x00, 0x83))
    return rom, labels


HEADER = 112   # the battery file: 112 bytes of header, then the BW-RAM


def persistence_check(exe, folder, path):
    """The BW-RAM is the battery: it survives two processes, and a damaged or foreign file is refused untouched."""
    battery = folder / 'persistent' / 'sa1.rrsram'
    if battery.exists():
        battery.unlink()

    def boot(name):
        report = folder / (name + '.json')
        done = subprocess.run([str(exe), '--frames', '20', '--cartridge-save', str(battery), '--report', str(report)],
                              capture_output=True, text=True, timeout=120)
        return done.returncode, (json.loads(report.read_text()) if report.exists() else None)

    code, first = boot('first')
    assert code == 0, code
    raw = battery.read_bytes()
    assert len(raw) == HEADER + 0x2000 and raw[:8] == b'RRSNRA1' + bytes(1), (len(raw), raw[:8])
    assert int.from_bytes(raw[16:20], 'little') == 7, 'the save is bound to the SA-1 board (CART_SA1)'
    assert raw[HEADER + 0x20] == 1 and raw[HEADER] == 0xa5 and raw[HEADER + 1] == 0x5a, raw[HEADER:HEADER + 0x22]
    code, second = boot('second')
    assert code == 0, code
    raw = battery.read_bytes()
    assert raw[HEADER + 0x20] == 2, 'the counter of the first process is read back by the second'
    assert first['sram_hash'] != second['sram_hash']
    # A damaged payload, and a file made for another cartridge, never stop the game: each is set aside as it was and the game
    # starts with a blank BW-RAM (tools/snes_saves_check.py checks every board for the other forms of damage).
    for label, damage in (('payload', lambda b: b[:HEADER + 5] + bytes([b[HEADER + 5] ^ 1]) + b[HEADER + 6:]),
                          ('cartridge', lambda b: b[:40] + bytes([b[40] ^ 1]) + b[41:])):
        aside = battery.parent / (battery.name + '.unusable-1')
        if aside.exists():
            aside.unlink()
        broken = damage(raw)
        battery.write_bytes(broken)
        code, report = boot('aside-' + label)
        assert code == 0 and report['save_set_aside'] == 1 and aside.read_bytes() == broken, (label, code)
        assert battery.read_bytes()[HEADER + 0x20] == 1, 'a blank start'
    aside.unlink()
    battery.write_bytes(raw)
    return {'counter_after_two_boots': 2, 'bound_to_board': 'CART_SA1', 'damaged_payload_set_aside': True,
            'other_cartridge_set_aside': True}


def main():
    work = ROOT / '.build/snes-sa1-selftest'
    work.mkdir(parents=True, exist_ok=True)
    results, profiles, rows = [], {}, []
    for pal in (False, True):
        standard = 'pal' if pal else 'ntsc'
        folder = work / standard
        folder.mkdir(exist_ok=True)
        path = folder / 'authored.sfc'
        authored, labels = cartridge(pal)
        path.write_bytes(authored)
        rom = read_snes_rom(path)
        profiles[rom.sha256] = {'id': 'fixture-sa1-' + standard, 'title': 'sa1', 'legacy_functions': False,
                                'standard': standard}
        rows.append((pal, path, folder, labels))
    with patch.dict(supernintendo.PROFILES, profiles):
        for pal, path, folder, labels in rows:
            exe = prepare16(path, 'snes', title='sa1', emit=lambda text: None)
            native = probe16(exe, folder, 40)
            reference = probe16(exe, folder, 40, reference=True)
            differences = reference_differences('snes', native, reference)
            assert not differences, differences
            assert native['cartridge_chip'] == 'sa1' and native['coprocessor_mode'] == 'interpreted', native
            where = [name for name, pc in labels.items() if pc == native['cpu_pc']]
            assert native['cpu_pc'] == labels['pass'], ('verdict', where, hex(native['cpu_pc']))
            assert not native['interpreted_opcodes'], native['interpreted_opcodes']
            # After the synchronisation the SA-1 is never behind (by construction: the clock is the bus cycle's); it runs
            # whole instructions, so it stands ahead by part of one (a measurement on this cartridge, 14 clocks at most, kept
            # here as a regression guard, not as a bound). Before it, the SA-1 had fallen behind by up to one S-CPU access:
            # that catch-up is what the old clock of the end of the previous instruction left in the S-CPU's view.
            assert native['sa1_sync_samples'] > 1000 and native['sa1_synced_behind_max'] == 0, native
            assert native['sa1_ahead_max'] <= 40, native
            # One instruction per ten master clocks over the run (the two-instruction counter loop of 20 clocks), minus
            # the setup before the SA-1 is released and the handlers; the S-CPU's own time is the master clock.
            expected = native['master_cycles'] // COUNTER_LOOP_MASTER_CLOCKS_PER_INSTRUCTION
            assert abs(native['coprocessor_instructions'] - expected) < expected // 100 + 500, (
                native['coprocessor_instructions'], expected)
            persistence = persistence_check(exe, folder, path)
            state = state_check(exe, folder / 'state', 13, 11)
            results.append({'standard': 'pal' if pal else 'ntsc', 'passed': True, 'cpu_pc': native['cpu_pc'],
                            'master_cycles': native['master_cycles'],
                            'sa1_instructions': native['coprocessor_instructions'], 'expected_instructions': expected,
                            'sa1_sync_samples': native['sa1_sync_samples'], 'sa1_behind_max_before_sync': native['sa1_behind_max'],
                            'sa1_behind_buckets_before_sync': native['sa1_behind_buckets'],
                            'sa1_ahead_max': native['sa1_ahead_max'], 'differences': differences,
                            'battery': persistence, 'quick_state': state})
    atomic_json(work / 'results.json', results)
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
