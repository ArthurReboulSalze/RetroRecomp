"""Prove an authored ROM's missing dynamic jump becomes native next generation.

The target address is built through byte writes to RAM, not a direct CALL/JP
that static discovery could follow. Generation one must fall back; generation
two uses only the byte-verified game memory, under another name/output folder.
"""
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from smsrecomp.core import ROOT, convert, read_rom, probe
from smsrecomp.library import GameMemory, entry_lock


def main():
    directory = ROOT / ".build/learning-selftest"
    directory.mkdir(parents=True, exist_ok=True)
    # Each test invocation gets a fresh isolated library. The user's actual
    # observations, executables and preferences are untouched.
    import tempfile
    with tempfile.TemporaryDirectory(dir=directory) as temp:
        library = Path(temp) / "library"
        os.environ["SMSRECOMP_LIBRARY_DIR"] = str(library)
        data = bytearray([0xC9] * 8192)
        data[:3] = bytes.fromhex("C3 00 01")
        program = bytes.fromhex("F3 31 F0 DF 3E 00 32 00 C0 3E 02 32 01 C0 2A 00 C0 E9")
        data[0x100:0x100+len(program)] = program
        data[0x200:0x209] = bytes.fromhex("3E A5 32 10 C0 76 C3 05 02")
        rom_path = Path(temp) / "Learn_a_dynamic_ROM_jump.sms"
        rom_path.write_bytes(data)
        first = convert(rom_path, title="Learning_First", output=Path(temp)/"first", backend="functions", passes=1, frames=3, online_cover=False)
        a = json.loads((first.parent / "conversion-report.json").read_text(encoding="utf-8"))
        assert any(c["interpreter_percent"] > 0 for c in a["final_checks"])
        assert not any(c["passed"] for c in a["strict_checks"])
        memory = GameMemory(read_rom(rom_path))
        assert memory.summary()["rom_entries"] >= 1

        # A copied, renamed standalone game (no conversion-report or ROM beside
        # it) must write to its embedded identity, in a Unicode library root.
        standalone = Path(temp)/"shared/renamed.exe"; standalone.parent.mkdir()
        shutil.copy2(first, standalone)
        env = os.environ.copy()
        env["SMSRECOMP_LIBRARY_DIR"] = str(Path(temp)/"mémoire native")
        native_log = Path(temp)/"native.log"
        native_memory = GameMemory(read_rom(rom_path), Path(env["SMSRECOMP_LIBRARY_DIR"]))
        with entry_lock(native_memory.directory):
            process = subprocess.Popen([str(standalone), "--headless", "--frames", "3", "--log", str(native_log)],
                                       cwd=standalone.parent, env=env)
            until = time.monotonic() + 3
            while time.monotonic() < until:
                if native_log.exists() and "loaded embedded.sms" in native_log.read_text(errors="replace"):
                    break
                time.sleep(.02)
            else:
                raise RuntimeError("Native process did not reach the held library lock.")
            time.sleep(.05)
            assert process.poll() is None, "Native app must respect the converter's library lock"
        assert process.wait(timeout=10) == 0
        assert native_memory.summary()["rom_entries"] >= 1

        second = convert(rom_path, title="Learning_Renamed", output=Path(temp)/"different-output", backend="functions", passes=2, frames=3, online_cover=False)
        b = json.loads((second.parent / "conversion-report.json").read_text(encoding="utf-8"))
        assert b["learning"]["recipe_reused"] and b["learning"]["reused_rom_entries"] >= 1
        assert all(c["passed"] and c["interpreter_percent"] == 0 for c in b["strict_checks"] + b["final_checks"])
        build = Path(b["build_directory"])
        native = (build/"checks/pass1_demo/frame.png.ram").read_bytes()
        reference = (build/"checks/reference/frame.png.ram").read_bytes()
        assert native[0x10] == reference[0x10] == 0xA5
        assert GameMemory(read_rom(rom_path)).summary()["generations"] == 2
        print("PASS: missing ROM target learned -> zero interpreter and strict pass next generation; RAM output matches reference.")
        print("PASS: game identity survives rename/output changes; standalone native appends in a Unicode library.")
        print("PASS: native observation writer respects the Python converter's shared file lock.")


if __name__ == "__main__":
    main()
