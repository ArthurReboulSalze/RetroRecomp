"""Differential execution of an authored ROM: LDIR must refresh R each repeat.

No commercial ROM is needed. The expected RAM result exposes a real CPU
semantic property rather than mirroring the C generator's implementation.
"""
from pathlib import Path
import json
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from retrorecomp.core import ROOT, convert


def main():
    directory = ROOT / ".build/cpu-selftest"
    directory.mkdir(parents=True, exist_ok=True)
    os.environ["SMSRECOMP_LIBRARY_DIR"] = str(directory / "learning")
    os.environ["RETRO_RECOMP_STILL_ROUTE_OK"] = "1"   # these programs have a result in RAM and no picture: the liveness refusal does not apply
    data = bytearray([0xC9] * 8192)
    data[:3] = bytes.fromhex("C3 00 01")  # JP $0100
    # DI; LD SP,$DFF0; LD HL,$0200; LD DE,$C100; LD BC,3; LDIR;
    # LD A,R; LD ($C000),A; HALT; JP $0114 (stay halted with IRQ disabled).
    program = bytes.fromhex("F3 31 F0 DF 21 00 02 11 00 C1 01 03 00 ED B0 ED 5F 32 00 C0 76 C3 14 01")
    data[0x100:0x100 + len(program)] = program
    data[0x200:0x203] = b"ABC"
    rom = directory / "Refresh_register_test.sms"
    rom.write_bytes(data)
    executable = convert(rom, title="CPU_Refresh_Test", output=directory / "output", backend="functions", passes=1, frames=3, online_cover=False)
    report = json.loads((executable.parent / "conversion-report.json").read_text())
    build = Path(report["build_directory"])
    native = (build / "checks/pass1_demo/frame.png.ram").read_bytes()
    reference = (build / "checks/reference/frame.png.ram").read_bytes()
    assert native[0] == reference[0] == 14, (native[0], reference[0])
    assert native[0x100:0x103] == reference[0x100:0x103] == b"ABC"
    assert all(check["passed"] for check in report["strict_checks"])
    print("PASS: LDIR copies ABC, refresh R=14 matches the reference; strict execution passes.")
    # "functions" engine, control flow the plain C call stack cannot follow (the Z80 semantics decide the expected bytes).
    # 1. A routine pushes a continuation, jumps into a shared tail and a conditional RET there pops that continuation: the Z80
    #    continues at the continuation, then its own RET returns to the caller.
    # 2. A call pages another bank into slot 2, then a jump goes to slot 2: the bytes of the new bank run.
    push_data = bytearray([0xC9] * 8192)
    push_data[:3] = bytes.fromhex("C3 00 01")
    # DI; LD SP,$DFF0; CALL $0120; LD A,$11; LD ($C000),A; HALT; JP $010C
    push_data[0x100:0x110] = bytes.fromhex("F3 31 F0 DF CD 20 01 3E 11 32 00 C0 76 C3 0C 01")
    # $0120: LD HL,$0130; PUSH HL; XOR A; JP $0140   $0130: LD A,$22; LD ($C001),A; RET   $0140: RET Z; LD A,$33; LD ($C001),A; RET
    push_data[0x120:0x128] = bytes.fromhex("21 30 01 E5 AF C3 40 01")
    push_data[0x130:0x136] = bytes.fromhex("3E 22 32 01 C0 C9")
    push_data[0x140:0x147] = bytes.fromhex("C8 3E 33 32 01 C0 C9")
    push_rom = directory / "Push_continuation_test.sms"
    push_rom.write_bytes(push_data)
    push_exe = convert(push_rom, title="CPU_Push_Continuation_Test", output=directory / "push-output", backend="functions", passes=1, frames=3, online_cover=False)
    push_report = json.loads((push_exe.parent / "conversion-report.json").read_text())
    push_build = Path(push_report["build_directory"])
    native = (push_build / "checks/pass1_demo/frame.png.ram").read_bytes()
    reference = (push_build / "checks/reference/frame.png.ram").read_bytes()
    assert native[0:2] == reference[0:2] == bytes([0x11, 0x22]), (native[0:2], reference[0:2])
    assert push_report["reference_final_ram_match"] is True and push_report["reference_vdp_trace_match"] is True
    print("PASS: a conditional RET that pops a pushed continuation continues there (native RAM equals the reference).")
    # 3. A routine reads the byte that follows its CALL (EX (SP),HL; LD A,(HL); INC HL; EX (SP),HL; RET): the RET goes to the instruction
    #    after the inline byte, not to the byte (INC B, which would leave B = 1 in $C002). The 1.6.9 call sites compare the address
    #    the callee popped with the one they pushed.
    inline_data = bytearray([0xC9] * 8192)
    inline_data[:3] = bytes.fromhex("C3 00 01")
    # DI; LD SP,$DFF0; LD B,0; CALL $0120; DB $04; LD A,$11; LD ($C000),A; LD A,B; LD ($C002),A; HALT; JP $0113
    inline_data[0x100:0x117] = bytes.fromhex("F3 31 F0 DF 06 00 CD 20 01 04 3E 11 32 00 C0 78 32 02 C0 76 C3 13 01")
    inline_data[0x120:0x128] = bytes.fromhex("E3 7E 23 E3 32 01 C0 C9")
    inline_rom = directory / "Inline_data_test.sms"
    inline_rom.write_bytes(inline_data)
    inline_exe = convert(inline_rom, title="CPU_Inline_Data_Test", output=directory / "inline-output", backend="functions", passes=1, frames=3, online_cover=False)
    inline_report = json.loads((inline_exe.parent / "conversion-report.json").read_text())
    inline_build = Path(inline_report["build_directory"])
    native = (inline_build / "checks/pass1_demo/frame.png.ram").read_bytes()
    reference = (inline_build / "checks/reference/frame.png.ram").read_bytes()
    assert native[0:3] == reference[0:3] == bytes([0x11, 0x04, 0x00]), (native[0:3], reference[0:3])
    assert inline_report["reference_final_ram_match"] is True and inline_report["reference_vdp_trace_match"] is True
    print("PASS: a RET that returns past the byte after its CALL continues after that byte (native RAM equals the reference).")
    # 3b. DD 76 and FD 76 are a HALT behind a prefix that does nothing. The static walk also decodes the bytes a branch skips: here
    #     they are dead code, and the generated C used to name an `ea` nobody declares, so the build failed (Shining Force II).
    prefixed_data = bytearray([0xC9] * 8192)
    prefixed_data[:3] = bytes.fromhex("C3 00 01")
    # DI; LD SP,$DFF0; XOR A; JR Z,+4; DD 76; FD 76; LD A,$55; LD ($C000),A; HALT; JP $0111
    prefixed_data[0x100:0x112] = bytes.fromhex("F3 31 F0 DF AF 28 04 DD 76 FD 76 3E 55 32 00 C0 76 C3")
    prefixed_data[0x112:0x114] = bytes.fromhex("11 01")
    prefixed_rom = directory / "Prefixed_halt_in_dead_code_test.sms"
    prefixed_rom.write_bytes(prefixed_data)
    prefixed_exe = convert(prefixed_rom, title="CPU_Prefixed_Halt_Test", output=directory / "prefixed-output", backend="functions", passes=1, frames=3, online_cover=False)
    prefixed_report = json.loads((prefixed_exe.parent / "conversion-report.json").read_text())
    prefixed_build = Path(prefixed_report["build_directory"])
    native = (prefixed_build / "checks/pass1_demo/frame.png.ram").read_bytes()
    assert native[0] == 0x55 and prefixed_report["reference_final_ram_match"] is True, native[0]
    print("PASS: a DD 76 and an FD 76 in code the walk reaches build and the program runs on (native RAM equals the reference).")
    bank_data = bytearray([0xC9] * 65536)
    bank_data[:3] = bytes.fromhex("C3 00 01")
    # DI; LD SP,$DFF0; CALL $0200; JP $8010   $0200: LD A,3; LD ($FFFF),A; RET (slot 2 now shows bank 3)
    bank_data[0x100:0x10A] = bytes.fromhex("F3 31 F0 DF CD 00 02 C3 10 80")
    bank_data[0x200:0x206] = bytes.fromhex("3E 03 32 FF FF C9")
    for bank, marker in ((2, 0xAA), (3, 0xBB)):
        base = bank * 0x4000 + 0x10
        bank_data[base:base + 9] = bytes([0x3E, marker, 0x32, 0x02, 0xC0, 0x76, 0xC3, 0x15, 0x80])
    bank_rom = directory / "Jump_after_bank_write_test.sms"
    bank_rom.write_bytes(bank_data)
    bank_exe = convert(bank_rom, title="CPU_Bank_Jump_Test", output=directory / "bank-output", backend="functions", passes=1, frames=3, online_cover=False)
    bank_report = json.loads((bank_exe.parent / "conversion-report.json").read_text())
    bank_build = Path(bank_report["build_directory"])
    native = (bank_build / "checks/pass1_demo/frame.png.ram").read_bytes()
    reference = (bank_build / "checks/reference/frame.png.ram").read_bytes()
    assert native[2] == reference[2] == 0xBB, (native[2], reference[2])
    assert bank_report["reference_final_ram_match"] is True and bank_report["reference_vdp_trace_match"] is True
    print("PASS: a jump into a slot paged by a call runs the new bank's bytes (native RAM equals the reference).")
    # 3. BIT n,(HL) takes its X and Y flags from the high byte of WZ (MEMPTR), here the return address of the RET just before it
    #    ($2803, high byte $28 = X and Y), not from H ($C1). Expected F = Z|H|P|X|Y = $7C (it would be $54 with H).
    wz_data = bytearray([0xC9] * 16384)
    wz_data[:3] = bytes.fromhex("C3 00 01")
    wz_data[0x100:0x107] = bytes.fromhex("F3 31 F0 DF C3 00 28")
    # $2800: CALL $0200; XOR A (A and carry clear: the reset values of the two CPUs differ); LD HL,$C100; BIT 0,(HL); PUSH AF; POP BC;
    # LD A,C; LD ($C000),A; HALT; JP $280F     $0200: RET
    wz_data[0x2800:0x2800 + 19] = bytes.fromhex("CD 00 02 AF 21 00 C1 CB 46 F5 C1 79 32 00 C0 76 C3 0F 28")
    wz_rom = directory / "BIT_HL_after_RET_test.sms"
    wz_rom.write_bytes(wz_data)
    wz_exe = convert(wz_rom, title="CPU_BIT_WZ_Test", output=directory / "wz-output", backend="functions", passes=1, frames=3, online_cover=False)
    wz_report = json.loads((wz_exe.parent / "conversion-report.json").read_text())
    wz_build = Path(wz_report["build_directory"])
    native = (wz_build / "checks/pass1_demo/frame.png.ram").read_bytes()
    reference = (wz_build / "checks/reference/frame.png.ram").read_bytes()
    assert native[0] == reference[0] == 0x7C, (native[0], reference[0])
    assert wz_report["reference_final_ram_match"] is True and wz_report["reference_vdp_trace_match"] is True
    print("PASS: BIT n,(HL) after a RET takes X and Y from WZ (native flags equal the reference).")
    # 4. Learning from the counted interpreter: the routine at $0200 is reached by a computed jump the static walk cannot follow
    #    (HL is loaded from RAM), so it runs in the interpreter; the routines it CALLs ($0300, $0320) used to stay unknown until the
    #    next pass found them one by one. They are now recorded in the same pass.
    learn_data = bytearray([0xC9] * 8192)
    learn_data[:3] = bytes.fromhex("C3 00 01")
    # DI; LD SP,$DFF0; XOR A; LD ($C100),A; LD A,2; LD ($C101),A; LD HL,($C100); JP (HL)
    learn_data[0x100:0x112] = bytes.fromhex("F3 31 F0 DF AF 32 00 C1 3E 02 32 01 C1 2A 00 C1 E9 00")
    # $0200: CALL $0300; CALL $0320; HALT; JP $0209    $0300: LD A,1; LD ($C000),A; RET    $0320: LD A,2; LD ($C001),A; RET
    learn_data[0x200:0x20C] = bytes.fromhex("CD 00 03 CD 20 03 76 C3 09 02 00 00")
    learn_data[0x300:0x306] = bytes.fromhex("3E 01 32 00 C0 C9")
    learn_data[0x320:0x326] = bytes.fromhex("3E 02 32 01 C0 C9")
    learn_rom = directory / "Interpreter_call_targets_test.sms"
    learn_rom.write_bytes(learn_data)
    learn_exe = convert(learn_rom, title="CPU_Learn_Targets_Test", output=directory / "learn-output", backend="functions", passes=1, frames=3, online_cover=False)
    learn_report = json.loads((learn_exe.parent / "conversion-report.json").read_text())
    learn_build = Path(learn_report["build_directory"])
    # What the first pass itself observed (its learning journal), before any later pass or the static walk could find the callees.
    journal = next((learn_build / "checks/pass1_demo/learning").glob("*/observations.log"))
    learned = {int(line.split()[0], 16) for line in journal.read_text().splitlines() if line.strip()}
    assert {0x0200, 0x0300, 0x0320} <= learned, sorted(hex(a) for a in learned)
    native = (learn_build / "checks/pass1_demo/frame.png.ram").read_bytes()
    assert native[0:2] == bytes([1, 2]), native[0:2]
    print("PASS: the call targets run by the interpreter are learned in the same (only) pass ($0200, $0300, $0320).")
    # Execute an authored RAM loop that cannot be compiled from ROM. A frame
    # limit exits from inside its interpreter call, exercising the in-flight
    # tally and strict rejection rather than only completed fallback routines.
    ram_data = bytearray([0xC9] * 8192)
    ram_data[:3] = bytes.fromhex("C3 00 01")
    ram_program = bytes.fromhex("F3 31 F0 DF 3E 18 32 00 C1 3E FE 32 01 C1 21 00 C1 E9")
    ram_data[0x100:0x100 + len(ram_program)] = ram_program
    ram_rom = directory / "RAM_loop_test.sms"
    ram_rom.write_bytes(ram_data)
    ram_exe = convert(ram_rom, title="CPU_RAM_Loop_Test", output=directory / "ram-output", backend="functions", passes=1, frames=3, online_cover=False)
    ram_report = json.loads((ram_exe.parent / "conversion-report.json").read_text())
    assert all(c["interpreter_percent"] > 99.0 for c in ram_report["final_checks"])
    assert all(c["exit_code"] == 3 and not c["passed"] for c in ram_report["strict_checks"])
    print("PASS: in-flight RAM interpreter usage is counted; strict mode rejects the missing code.")


if __name__ == "__main__":
    main()
