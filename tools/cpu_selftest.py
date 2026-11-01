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
