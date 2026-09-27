"""Authored ROMs exercise paging, cross-bank instructions and guest returns.

The fixtures are not commercial games, and their expected RAM effects follow
the Z80 program, not the generated C. All learning/output is isolated.
"""
import json
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from smsrecomp.core import ROOT, convert


def run_case(directory, name, data, expected, *, fallback=False, minimum_interp=0, passes=1):
    path = directory / f"{name}.sms"
    path.write_bytes(data)
    exe = convert(path, title=name, backend="banked", output=directory / name,
                  frames=5, passes=passes, online_cover=False)
    report = json.loads((exe.parent / "conversion-report.json").read_text())
    build = Path(report["build_directory"])
    final_pass = len(report["history"]) // 2
    ram = (build / f"checks/pass{final_pass}_demo/frame.png.ram").read_bytes()
    ref = (build / "checks/reference/frame.png.ram").read_bytes()
    for offset, value in expected.items():
        assert ram[offset:offset+len(value)] == ref[offset:offset+len(value)] == value, (name, offset, ram[offset:offset+len(value)], ref[offset:offset+len(value)])
    assert report["reference_final_ram_match"], name
    assert report["reference_vdp_trace_match"], name
    if fallback:
        assert all(c["banked"]["fallback_steps"] > 0 for c in report["final_checks"])
        assert all(c["exit_code"] == 3 for c in report["strict_checks"])
        assert all(c["interpreter_percent"] > minimum_interp for c in report["final_checks"])
    else:
        assert all(c["passed"] for c in report["strict_checks"]), report["strict_checks"]
        assert all(c["banked"]["fallback_steps"] == 0 for c in report["final_checks"])
        native_cpu = report["final_checks"][0]["final_cpu"]
        reference_cpu = report["reference_check"]["final_cpu"]
        assert native_cpu == reference_cpu, (native_cpu, reference_cpu)
    print(f"PASS {name}: expected RAM, reference frames, {'strict rejection of RAM fallback' if fallback else 'strict native execution and architectural CPU state'}")
    return report


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    directory = ROOT / ".build/banked-selftest"
    directory.mkdir(parents=True, exist_ok=True)
    learning = Path(tempfile.mkdtemp(prefix="learning-run-", dir=directory))
    os.environ["SMSRECOMP_LIBRARY_DIR"] = str(learning)
    # Output exports intentionally seed later conversions. Clear only the
    # authored fixtures' pattern exports so each full test starts cold.
    for pattern_name in ("native.patterns", "native-patterns.txt"):
        for previous in directory.glob("Banked_*/" + pattern_name):
            previous.unlink()
    reports = []
    data = bytearray([0xC9] * 65536)
    def put(bank, offset, hexdata):
        code = bytes.fromhex(hexdata)
        data[bank*0x4000+offset:bank*0x4000+offset+len(code)] = code
    put(0, 0, "C3 00 01")
    # Computed call to bank 3 in slot 1; it replaces itself with bank 2.
    put(0, 0x100, "F3 31 F0 DF 3E 83 32 FE FF 21 00 40 CD 00 02 3E 81 32 FD FF C3 FF 03")
    put(0, 0x200, "E9")
    put(3, 0, "3E A3 32 00 C1 3E 82 32 FE FF")
    put(2, 0xA, "3E A2 32 01 C1 C9")
    # The fixed 1KB region ends between the opcode and its operand.
    put(0, 0x3FF, "3E")
    put(0, 0x400, "22")  # wrong bank would load 0x22
    put(1, 0x400, "11 32 03 C1 C3 80 02")
    put(0, 0x280, "C3 FF 3F")
    put(1, 0x3FFF, "3E")
    put(2, 0, "5A 32 04 C1 C3 A0 02")
    put(0, 0x2A0, "3E 81 32 FF FF C3 FF 7F")
    put(2, 0x3FFF, "21")
    put(1, 0, "34 12 22 05 C1 C3 C0 02")
    # Repeating block refresh, indexed CB, and a modified return address.
    put(0, 0x2C0, "21 00 03 11 10 C1 01 03 00 ED B0 DD 21 20 C1 DD 36 01 80 DD CB 01 06 CD 20 03 3E EE 3E 55 32 07 C1 76")
    put(0, 0x300, "41 42 43")
    put(0, 0x320, "E1 23 23 E5 C9")  # skip LD A,$EE at the return PC
    reports.append(run_case(directory, "Banked_Paging_Seams_Returns", data,
        {0x100: bytes.fromhex("A3 A2"), 0x103: bytes.fromhex("11 5A 34 12 55"),
         0x110: b"ABC", 0x121: b"\x01"}))
    # 24KB cartridges require modulo byte addressing: bank 2 mirrors to 8KB,
    # rather than bank 0 as a ceil(size/16KB) bank-count calculation would do.
    data = bytearray([0xC9] * 24576)
    data[:3] = bytes.fromhex("C3 00 01")
    program = bytes.fromhex("F3 31 F0 DF 3E 02 32 FE FF 21 00 40 E9")
    data[0x100:0x100+len(program)] = program
    program = bytes.fromhex("3E 42 32 00 C1 76")
    data[8192:8192+len(program)] = program
    reports.append(run_case(directory, "Banked_Partial_Bank_Mirror", data, {0x100: b"\x42"}))
    # A generated RAM instruction is captured on a cold pass, then compiled
    # for the next generation. Strict mode must still reject the cold miss.
    data = bytearray([0xC9] * 8192)
    data[:3] = bytes.fromhex("C3 00 01")
    program = bytes.fromhex("F3 31 F0 DF 3E 18 32 00 C1 3E FE 32 01 C1 21 00 C1 E9")
    data[0x100:0x100+len(program)] = program
    reports.append(run_case(directory, "Banked_Dynamic_RAM", data, {0x100: bytes.fromhex("18 FE")}, fallback=True, minimum_interp=99))
    reports.append(run_case(directory, "Banked_Dynamic_RAM", data, {0x100: bytes.fromhex("18 FE")}))
    # IRQ entry/return uses guest PC and SP, including EI's acceptance delay.
    data = bytearray([0xC9] * 8192)
    data[:3] = bytes.fromhex("C3 00 01")
    irq = bytes.fromhex("F5 DB BF 3A 00 C1 3C 32 00 C1 F1 FB ED 4D")
    data[0x38:0x38+len(irq)] = irq
    program = bytes.fromhex("F3 31 F0 DF ED 56 3E 20 D3 BF 3E 81 D3 BF FB 76 18 FD")
    data[0x100:0x100+len(program)] = program
    reports.append(run_case(directory, "Banked_IRQ_EI_HALT", data, {0x100: b"\x05"}))
    # The superseded DD prefix is an interrupt-inhibited native fragment;
    # FD selects IY for the completed instruction, including its immediate.
    data = bytearray([0xC9] * 8192)
    data[:3] = bytes.fromhex("C3 00 01")
    program = bytes.fromhex("F3 31 F0 DF DD FD 21 34 12 FD 22 00 C1 76")
    data[0x100:0x100+len(program)] = program
    reports.append(run_case(directory, "Banked_Repeated_Prefix", data, {0x100: bytes.fromhex("34 12")}))
    # Mixed/repeated prefixes at the fixed area and both bank boundaries,
    # followed by a long stream. The final index prefix wins; ED ignores it.
    data = bytearray([0xC9] * 65536)
    def code(address, text):
        value = bytes.fromhex(text)
        data[address:address+len(value)] = value
    code(0, 'C3 00 01')
    code(0x100, 'F3 31 F0 DF 01 55 33 C3 FE 03')
    code(0x3FE, 'DD FD DD FD 21 11 11 FD 22 00 C1 C3 FE 3F')
    code(0x3FFE, 'DD FD DD 21 22 22 DD 22 02 C1 C3 FE 7F')
    code(0x7FFE, 'FD DD ED 43 04 C1 C3 00 81')
    data[0x8100:0x9100] = bytes([0xDD]) * 4096
    code(0x9100, 'FD 21 44 44 FD 22 06 C1 76')
    reports.append(run_case(directory, 'Banked_Prefix_Seams_Long', data,
        {0x100: bytes.fromhex('11 11 22 22 55 33 44 44')}))
    # An already asserted IRQ must wait for ALL prefixes and the instruction
    # following EI. The ISR sees the new SP, after its return PC was pushed.
    data = bytearray([0xC9] * 8192)
    code(0, 'C3 00 01')
    code(0x38, 'ED 73 00 C1 F3 76')
    code(0x100, 'F3 31 F0 DF ED 56 3E 20 D3 BF 3E 81 D3 BF DB 7E FE C1 20 FA FB DD FD DD 31 00 D0 76')
    reports.append(run_case(directory, 'Banked_Prefix_IRQ_Delay', data,
        {0x100: bytes.fromhex('FE CF')}))
    for mode, init in ((0, 'ED 46'), (2, 'AF 32 00 C3 3E 38 32 FF C2 3E C2 ED 47 ED 5E')):
        data = bytearray([0xC9] * 8192)
        code(0, 'C3 00 01')
        code(0x38, 'ED 73 00 C1 F3 76')
        code(0x100, f'F3 31 F0 DF {init} 3E 20 D3 BF 3E 81 D3 BF DB 7E FE C1 20 FA FB DD FD DD 31 00 D0 76')
        reports.append(run_case(directory, f'Banked_Prefix_IRQ_IM{mode}', data,
            {0x100: bytes.fromhex('FE CF')}))
    # The opcode at BFFF is immutable but the byte just after it is mutable.
    # A prefix fragment may run only while that second byte is another prefix.
    data = bytearray([0xC9] * 49152)
    code(0, 'C3 00 01')
    code(0x100, 'F3 31 F0 DF 21 00 10 11 00 C0 01 07 00 ED B0 C3 FF BF')
    code(0x1000, 'FD 21 34 12 C3 00 02')
    # The changed immediate makes IX=1234, then jumps to 0200 again. Replace
    # that RAM jump so the second pass terminates at another marker.
    code(0x200, 'FD 22 00 C1 3E 21 32 00 C0 3E 03 32 06 C0 C3 FF BF')
    code(0x300, 'DD 22 02 C1 76')
    code(0x1200, 'DD FD 21 34 12 DD 21 21 34')
    # DD FD 21 34 12 becomes DD 21 21 34 12: native guard must miss the
    # original fragment and load IX=3421 (12 then stores A through DE).
    data[-1] = 0xDD
    reports.append(run_case(directory, 'Banked_Prefix_Mutable_Seam', data,
        {0x100: bytes.fromhex('34 12 21 34')}, passes=3))
    # An immediate crossing from ROM into RAM is guarded against the live byte.
    # One cold miss is captured, then the next pass covers it natively.
    data = bytearray([0xC9] * 8192)
    data[:3] = bytes.fromhex("C3 00 01")
    program = bytes.fromhex("F3 31 F0 DF 21 00 10 11 00 C0 01 07 00 ED B0 21 FF BF E9")
    data[0x100:0x100+len(program)] = program
    data[0x1000:0x1007] = bytes.fromhex("77 32 00 C1 C3 01 C0")
    data[-1] = 0x3E
    reports.append(run_case(directory, "Banked_ROM_RAM_Seam", data, {0x100: b"\x77"}, passes=3))
    assert reports[-1]["history"][0]["banked"]["fallback_steps"] > 0
    assert reports[-1]["final_checks"][0]["banked"]["guarded_native_steps"] > 0
    # Same RAM address, changed immediate. A stale PC-only cache would loop at
    # $0300; exact guards must learn the new target and reach the $0400 marker.
    data = bytearray([0xC9] * 8192)
    data[:3] = bytes.fromhex("C3 00 01")
    program = bytes.fromhex("F3 31 F0 DF 21 00 12 11 00 C1 01 03 00 ED B0 C3 00 C1")
    data[0x100:0x100+len(program)] = program
    program = bytes.fromhex("3E 04 32 02 C1 C3 00 C1")
    data[0x300:0x300+len(program)] = program
    program = bytes.fromhex("3E 99 32 00 C2 76")
    data[0x400:0x400+len(program)] = program
    data[0x1200:0x1203] = bytes.fromhex("C3 00 03")
    reports.append(run_case(directory, "Banked_Mutating_RAM_Guard", data, {0x200: b"\x99"}, fallback=True))
    reports.append(run_case(directory, "Banked_Mutating_RAM_Guard", data, {0x200: b"\x99"}))
    # A failed equivalence check must not replace an already delivered binary.
    # Inject a reference mismatch into the actual conversion path, after build.
    import hashlib
    from unittest.mock import patch
    from smsrecomp import core
    output = directory / 'Banked_Mutating_RAM_Guard'
    exported = output / 'Banked_Mutating_RAM_Guard.exe'
    before = hashlib.sha256(exported.read_bytes()).hexdigest()
    real_probe = core.probe
    def wrong_reference(*args, **kwargs):
        result = real_probe(*args, **kwargs)
        if kwargs.get('reference'):
            result['final_cpu']['wz'] ^= 1
        return result
    with patch.object(core, 'probe', side_effect=wrong_reference):
        try:
            convert(directory / 'Banked_Mutating_RAM_Guard.sms', title='Banked_Mutating_RAM_Guard',
                    output=output, frames=5, passes=1, online_cover=False)
        except core.ConversionError as error:
            assert 'Native validation failed' in str(error), error
        else:
            raise AssertionError('Mismatched CPU candidate was published')
    assert hashlib.sha256(exported.read_bytes()).hexdigest() == before
    print('PASS publication gate: rejected changed WZ, previous executable preserved')
    (directory / "results.json").write_text(json.dumps(reports, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
