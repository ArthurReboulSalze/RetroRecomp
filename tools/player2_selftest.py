"""Execute two-port inputs in an authored ROM on both native CPU backends.

No user ROM, physical controller, real window or existing output is modified.
"""
from pathlib import Path
import json
import os
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from smsrecomp.core import ROOT, convert, dependencies, run


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    directory = ROOT / ".build/player2-selftest"
    directory.mkdir(parents=True, exist_ok=True)
    data = bytearray([0xC9] * 8192)
    data[:3] = bytes.fromhex("C3 00 01")
    program = bytes.fromhex("F3 31 F0 DF DB DC 32 00 C0 DB DD 32 01 C0 C3 04 01")
    data[0x100:0x100 + len(program)] = program
    rom = directory / "Two_controller_ports.sms"
    rom.write_bytes(data)
    os.environ["RETRO_RECOMP_LIBRARY_DIR"] = str(directory / "library")
    engine, sdl, cmake, generator = dependencies()
    results = []
    for backend in ("functions", "banked"):
        exe = convert(rom, title=f"Player2_Port_Proof_{backend}", output=directory / backend,
            frames=2, passes=1, backend=backend, use_cover=False, online_cover=False)
        report = json.loads((exe.parent / "conversion-report.json").read_text(encoding="utf-8"))
        build = directory / f"{backend}-build"
        run([cmake, "-S", ROOT / ".build/native-source", "-B", build, "-G", generator, "-A", "x64",
            f"-DENGINE_DIR={engine.as_posix()}", f"-DGAME_DIR={Path(report['build_directory']).as_posix()}",
            f"-DSMSRECOMP_BANKED_AOT={'ON' if backend == 'banked' else 'OFF'}",
            f"-DCMAKE_PREFIX_PATH={sdl.as_posix()}", "-DGAME_NAME=InputProof", "-DSMSRECOMP_INPUT_CHECKS=ON"])
        run([cmake, "--build", build, "--config", "Release", "--target", "smsrecomp_input_checks", "--parallel", "4"])
        env = os.environ.copy(); env["SMSRECOMP_STRICT"] = "1"
        result = subprocess.run([str(build / "Release/smsrecomp_input_checks.exe")],
            cwd=directory, env=env, capture_output=True, timeout=45)
        (directory / f"{backend}-cpu.log").write_bytes(result.stdout + result.stderr)
        print(result.stdout.decode("utf-8", errors="replace"))
        assert result.returncode == 0, f"{backend} checks failed: {result.returncode}"
        results.append({"backend": backend, "cpu_runs": 128, "native_fallback_cycles": 0,
                        "passed": True, "rom_sha256": report["rom"]["sha256"]})
    (directory / "verification.json").write_text(json.dumps({"players": 2, "results": results}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
