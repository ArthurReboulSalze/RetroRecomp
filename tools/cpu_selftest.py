"""Differential execution of an authored ROM: LDIR must refresh R each repeat.

No commercial ROM is needed. The expected RAM result exposes a real CPU
semantic property rather than mirroring the C generator's implementation.
"""
from pathlib import Path
import json
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from smsrecomp.core import ROOT, convert


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
