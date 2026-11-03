"""The delay of EI on a cartridge authored for it, in the delivered executable: an interrupt that is already pending when EI runs.

On the console IME is set after the instruction that follows EI (Pan Docs, "Interrupts"): `EI` then `INC B` runs INC B before the
interrupt is taken, `EI` then `DI` takes no interrupt, and `EI` `EI` takes it right after the second. The pinned runtime of 1.6.6 set IME
when EI itself completed, but its interrupt test lagged by one instruction, so ordinary flow already gave these answers; since 1.6.7
(`gameboy_runtime.adapt_ei_delay`) IME is set one instruction later, which is what the vectors see, and these cases guard that the answers
do not move. The program runs nine cases with the vertical-blank flag raised by hand and the screen off (so nothing else raises it):
ROM code, code copied to WRAM and to HRAM (the paths of the generated code, of the one-instruction RAM executors and of the interpreter) and
an EI at the end of a block; the results are left in work RAM. The delivered file is then also run in lockstep against the reference
interpreter, which must agree.

    python tools/gameboy_ei_check.py [--work FOLDER] [--reuse]

No byte of any ROM is involved: the cartridge is written here. Nothing here says anything about the timing of the interrupt dispatch itself.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gameboy_saves_check as saves                      # noqa: E402

ROOT = saves.ROOT
NAME = 'eicheck'
RESULTS = 0xC100                                         # work RAM: one byte per case
ISR_COUNT, ISR_B, ISR_D = 0xC00F, 0xC020, 0xC021         # what the interrupt routine leaves

# case name -> (index of the result byte, what the console gives). The pinned runtime of 1.6.6 gave the same seven answers (measured
# on this cartridge: [1, 1, 0, 2, 1, 1, 5, 1]): its interrupt test, which ran inside gb_tick before the pending flag was promoted,
# put the interrupt after the instruction that follows EI in ordinary flow. These cases guard that the change keeps it.
CASES = [
    ('EI ; INC B  (ROM): the INC runs before the interrupt, B seen by the routine', 0, 1),
    ('EI ; DI     (ROM): no interrupt is taken, routines run so far', 1, 1),
    ('EI ; EI ; INC D (ROM): the interrupt comes before the INC, D seen by the routine', 2, 0),
    ('after those: routines run in all', 3, 2),
    ('EI ; INC B ; NOP ; RET called in WRAM: B seen by the routine', 4, 1),
    ('same called in HRAM: B seen by the routine', 5, 1),
    ('after those: routines run in all', 6, 5),
    ('EI as the last instruction of a block, falling into a call target (ROM): B seen by the routine', 7, 1),
    ('EI ; HALT with an interrupt already pending and IME off (not the HALT bug): the routine ran once more', 8, 6),
    ('... and the stack is balanced: SP is $FFFC inside the CALL (low byte)', 9, 0xFC),
    ('... (high byte)', 10, 0xFF),
]


def program() -> tuple[bytes, dict[int, bytes]]:
    a = saves.Assembler(0x150)
    a.emit(0x31, 0xFE, 0xFF)                                          # LD SP,$FFFE
    a.emit(0xAF, 0xE0, 0x40)                                          # XOR A ; LDH ($40),A : screen off
    a.ld_a(1); a.emit(0xE0, 0xFF)                                     # IE = vertical blank
    a.emit(0xAF); a.ld_nn_a(ISR_COUNT)
    for destination, label in ((0xC200, 'wram'), (0xFF90, 'hram')):   # the routine EI ; INC B ; NOP ; RET, copied to RAM
        a.ld_hl(0x1000); a.ld_de(destination); a.ld_c(4)
        a.label(f'copy_{label}')
        a.ld_a_hli(); a.ld_de_a(); a.inc_de(); a.emit(0x0D); a.jr('nz', f'copy_{label}')

    def pending():                                                    # IF = vertical blank, as if it had just been raised
        a.ld_a(1); a.emit(0xE0, 0x0F)

    def store(address, source):                                       # (RESULTS + address) = what the routine saw / counted
        a.ld_a_nn(source); a.ld_nn_a(RESULTS + address)

    a.emit(0xAF, 0xE0, 0x0F); a.ld_b(0)                               # case 0
    pending(); a.emit(0xFB, 0x04, 0x00, 0x00, 0xF3); store(0, ISR_B)  # EI ; INC B ; NOP ; NOP ; DI
    pending(); a.emit(0xFB, 0xF3, 0x00, 0x00)                         # case 1: EI ; DI
    a.emit(0xAF, 0xE0, 0x0F); store(1, ISR_COUNT)
    a.emit(0x16, 0x00); pending(); a.emit(0xFB, 0xFB, 0x14, 0x00, 0xF3)   # case 2: EI ; EI ; INC D
    store(2, ISR_D); store(3, ISR_COUNT)
    a.ld_b(0); pending(); a.emit(0xCD, 0x00, 0xC2, 0x00, 0x00, 0xF3); store(4, ISR_B)   # case 4: the routine in WRAM
    a.ld_b(0); pending(); a.emit(0xCD, 0x90, 0xFF, 0x00, 0x00, 0xF3); store(5, ISR_B)   # case 5: the routine in HRAM
    # case 7: EI is the last instruction of a block and the next address is a call target (called once first, so that the generated
    # code makes it an entry of its own): 0x02FF EI, 0x0300 INC B ; NOP ; RET. The dispatch loop is back in charge between the two.
    a.emit(0xCD, 0x00, 0x03)                                          # CALL $0300 (no interrupt pending, IME off)
    a.ld_b(0); pending()
    after = len(a.code)
    a.ld_hl(0)                                                        # LD HL,after : patched below to the address of the NOP
    a.emit(0xE5, 0xC3, 0xFF, 0x02)                                    # PUSH HL ; JP $02FF
    a.code[after + 1:after + 3] = (a.origin + len(a.code)).to_bytes(2, 'little')
    a.emit(0x00, 0xF3); store(7, ISR_B)                               # NOP ; DI
    store(6, ISR_COUNT)
    a.emit(0xCD, 0x00, 0x04)                                          # case 8: CALL $0400, EI ; HALT with the interrupt already pending
    a.label('done'); a.jr('', 'done')
    isr = bytes.fromhex('F5 FA0FC0 3C EA0FC0 78 EA20C0 7A EA21C0 F1 D9')   # PUSH AF ; count ; save B and D ; POP AF ; RETI
    return a.finish(), {0x40: bytes.fromhex('C30002'), 0x200: isr, 0x1000: bytes.fromhex('FB0400C9'),
                               0x2FF: bytes.fromhex('FB'), 0x300: bytes.fromhex('0400C9'),
                               # 0400: IF = vertical blank ; EI ; HALT ; NOP ; DI ; the count of routines run, then SP, to work RAM ; RET
                               0x400: bytes.fromhex('3E01E00F FB 76 00 F3 FA0FC0 EA08C1 0809C1 C9'.replace(' ', ''))}


def authored_rom() -> bytes:
    code, extra = program()
    return saves.build_rom('RREI CHECK', 0x00, 0x00, code, extra)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--work', type=Path, default=ROOT / '.build' / 'gb-ei-check')
    parser.add_argument('--reuse', action='store_true', help='use the executable already converted in the work folder')
    args = parser.parse_args()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    executable = work / f'out_{NAME}' / 'Game Boy' / f'{NAME}.exe'
    if not (args.reuse and executable.is_file()):
        executable = saves.convert(NAME, work, authored_rom())
    folder = work / 'run'
    folder.mkdir(exist_ok=True)
    state = folder / 'state.json'
    state.unlink(missing_ok=True)
    result = subprocess.run([str(executable), '--headless', '--limit-frames', '3', '--dump-state', str(state)],
                            env=saves.environment(), capture_output=True, text=True, timeout=300, cwd=folder)
    wram = json.loads(state.read_text(encoding='utf-8'))['wram_bank_0_c000_cfff']
    failures: list[str] = []
    print(f'exit {result.returncode}')
    for text, index, expected in CASES:
        got = wram[RESULTS - 0xC000 + index]
        saves.check(got == expected, f'{text}: {got} (console {expected})', failures)
    lockstep = subprocess.run([str(executable), '--differential', '--differential-frames', '3'], env=saves.environment(),
                              capture_output=True, text=True, timeout=300, cwd=folder)
    from retrorecomp.gameboy import CPU_MATCH
    saves.check(bool(CPU_MATCH.search(lockstep.stdout + lockstep.stderr)),
                'the generated code and the reference interpreter agree for the whole program', failures)
    (work / 'results.json').write_text(json.dumps({'ram': wram[RESULTS - 0xC000:RESULTS - 0xC000 + 11], 'failures': failures}, indent=1) + '\n',
                                       encoding='utf-8')
    print(f'{len(failures)} failure(s)')
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
