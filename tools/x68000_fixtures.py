"""Build original MC68000 / Human68k test inputs without a cross-toolchain.

These tiny programs are authored for Retro-Recomp. They contain no firmware,
Human68k, game code, or third-party machine assets. RRHELLO.X and RRRELOC.X
require an independently supplied Human68k installation; cpu-stop-irq.bin is a
flat CPU-only memory image, NOT a bootable X68000 floppy or a replacement IPL.

Format/call references (used as documentation, not copied source):
https://github.com/erique/ghidra-human68k/blob/608cab76bbd650119ca5b1e2396e3a4485ba64da/src/main/java/human68k/Human68kXFileHeader.java
https://github.com/vampirefrog/v68/blob/9cb11c34396a298f16c674bedb5295c91cdb4916/docs/doscall.txt
The latter documents DOS _PRINT ($ff09, pointer.l on stack) and _EXIT2
($ff4c, exit-code.w on stack). These interfaces are not HLE implementations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct


MARKER = b"RETRORECOMP X68000 FIXTURE OK\r\n"
HEADER_SIZE = 0x40
CPU_ENTRY = 0x100
CPU_IRQ1_ENTRY = 0x120
CPU_UNEXPECTED_ENTRY = 0x130
CPU_STACK = 0x80000
CPU_COUNTER = 0x40000


def _x_file(text: bytes, data: bytes, relocations: bytes = b"") -> bytes:
    """Normal-load HU header with one text/data pair and no bound modules."""
    fields = (
        0, 0, len(text), len(data), 0, len(relocations), 0, 0, 0, 0,
        0, 0, 0, 0, 0,
    )
    header = struct.pack(">2sBB15I", b"HU", 0, 0, *fields)
    return header + text + data + relocations


def human68k_hello(*, relocated: bool = False) -> bytes:
    """Print a visible marker and return status zero to the Human68k shell.

    Normal variant uses PEA message(PC), so it works at any even load base.
    Relocation variant uses PEA message.L. Its delta table patches the long at
    image offset 2 with the actual load base. No external string pointers or
    absolute ROM calls are embedded. A DOS handler unexpectedly returning from
    _EXIT2 enters a self-loop, rather than executing message bytes as code.
    """
    tail = bytes.fromhex("FF09 588F 3F3C 0000 FF4C 60FE")
    # 588f = addq.l #4,sp; 3f3c 0000 = move.w #0,-(sp).
    if relocated:
        text = bytes.fromhex("4879") + struct.pack(">I", 18) + tail
        relocations = bytes.fromhex("0002")
    else:
        # PEA PC-relative base is the extension word's address (2), not the
        # next instruction (4): message at 16 therefore requires delta 14.
        text = bytes.fromhex("487A 000E") + tail
        relocations = b""
    data = MARKER + b"\0"
    if len(data) & 1:
        data += b"\0"
    return _x_file(text, data, relocations)


def cpu_stop_irq() -> bytes:
    """Reset vectors and a STOP/level-1-autovector/RTE test for a flat RAM bus.

    First run reaches STOP, D0=1, D1=0, [CPU_COUNTER]=1, SR=$2000.
    Pulse IRQ1 and clear it on acknowledgement: handler increments D1, RTE
    restores SR/PC, loop reaches STOP with D0=2, D1=1 and [CPU_COUNTER]=2.
    This does not represent X68000 peripheral IRQ routing or boot mapping.
    """
    image = bytearray(512)
    for vector in range(64):
        struct.pack_into(">I", image, vector * 4, CPU_UNEXPECTED_ENTRY)
    struct.pack_into(">II", image, 0, CPU_STACK, CPU_ENTRY)
    struct.pack_into(">I", image, (24 + 1) * 4, CPU_IRQ1_ENTRY)
    main = bytes.fromhex("7000 7200 5280 23C0")
    main += struct.pack(">I", CPU_COUNTER)
    main += bytes.fromhex("4E72 2000 60F2")
    image[CPU_ENTRY:CPU_ENTRY + len(main)] = main
    image[CPU_IRQ1_ENTRY:CPU_IRQ1_ENTRY + 4] = bytes.fromhex("5281 4E73")
    image[CPU_UNEXPECTED_ENTRY:CPU_UNEXPECTED_ENTRY + 6] = bytes.fromhex(
        "4E72 2700 60FA")
    return bytes(image)


def _hello_source(*, relocated: bool) -> bytes:
    operand = "message.l" if relocated else "message(pc)"
    return (
        "; Original Retro-Recomp MC68000 fixture; no third-party program data.\n"
        "; Build bytes and the HU header with tools/x68000_fixtures.py.\n"
        "        section text\n"
        "start:\n"
        f"        pea     {operand}\n"
        "        dc.w    $ff09           ; DOS _PRINT, pointer.l on stack\n"
        "        addq.l  #4,sp\n"
        "        move.w  #0,-(sp)\n"
        "        dc.w    $ff4c           ; DOS _EXIT2, return status 0\n"
        "hang:   bra.s   hang           ; only if exit incorrectly returns\n"
        "        section data\n"
        'message: dc.b   "RETRORECOMP X68000 FIXTURE OK",13,10,0\n'
        "        even\n"
    ).encode("ascii")


def fixtures() -> dict[str, bytes]:
    """Return deterministic outputs; generation never accesses user media."""
    expected = {
        "format": "retro-recomp.x68000-fixtures.v1",
        "authored": True,
        "bundled_firmware": False,
        "human68k": {
            "files": ["RRHELLO.X", "RRRELOC.X"],
            "stdout": MARKER.decode("ascii"),
            "exit_status": 0,
            "required_environment": "Human68k shell supplied independently",
            "coverage_claim": "DOS calls; not full X68000 hardware fidelity",
        },
        "cpu": {
            "file": "cpu-stop-irq.bin",
            "mapping": "flat RAM at address 0; CPU-only, not X68000 boot",
            "cpu": "MC68000",
            "initial_sp": CPU_STACK,
            "initial_pc": CPU_ENTRY,
            "counter_address": CPU_COUNTER,
            "first_stop": {"d0": 1, "d1": 0, "counter": 1, "sr": 0x2000},
            "after_irq1": {"d0": 2, "d1": 1, "counter": 2, "sr": 0x2000},
            "irq_protocol": "assert level 1; clear on autovector acknowledge",
        },
    }
    return {
        "RRHELLO.X": human68k_hello(),
        "RRRELOC.X": human68k_hello(relocated=True),
        "RRHELLO.s": _hello_source(relocated=False),
        "RRRELOC.s": _hello_source(relocated=True),
        "cpu-stop-irq.bin": cpu_stop_irq(),
        "expected.json": (json.dumps(expected, ensure_ascii=True, indent=2)
                          + "\n").encode("ascii"),
        "README.txt": (
            "Original Retro-Recomp X68000 fixtures. No BIOS, OS or game assets.\n"
            "Copy RRHELLO.X and RRRELOC.X into your own Human68k test disk.\n"
            "At its shell run RRHELLO, then RRRELOC. Each prints:\n"
            "RETRORECOMP X68000 FIXTURE OK\n"
            "Each returns to the shell with exit status 0.\n"
            "Do not use either X file as a floppy image or IPL ROM.\n"
            "cpu-stop-irq.bin is a flat CPU-only test, not X68000 firmware.\n"
            "See expected.json for its STOP, IRQ acknowledgement and RTE checks.\n"
            "A CPU/DOS check is not a gameplay, audio or hardware qualification.\n"
        ).encode("ascii"),
    }


def write_fixtures(output: Path) -> dict:
    """Write a fresh or identical set; never replace unrelated existing files."""
    contents = fixtures()
    manifest = {
        "format": "retro-recomp.x68000-fixture-manifest.v1",
        "authored": True,
        "files": {name: {"size": len(value),
                         "sha256": hashlib.sha256(value).hexdigest()}
                  for name, value in contents.items()},
    }
    contents["manifest.json"] = (
        json.dumps(manifest, indent=2) + "\n").encode("ascii")
    # Check every destination before creating any output, including the manifest.
    for name, value in contents.items():
        path = output / name
        if path.exists() and (not path.is_file() or path.read_bytes() != value):
            raise FileExistsError(f"Existing fixture differs; preserved: {path}")
    output.mkdir(parents=True, exist_ok=True)
    for name, value in contents.items():
        path = output / name
        if not path.exists():
            # Exclusive creation also protects against a concurrent writer.
            with path.open("xb") as stream:
                stream.write(value)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=(
        Path(__file__).resolve().parents[1] / ".build/x68000-stage1/fixtures"))
    args = parser.parse_args()
    manifest = write_fixtures(args.output)
    print(json.dumps({"output": str(args.output.resolve()), **manifest}, indent=2))


if __name__ == "__main__":
    main()
