"""Authored ROM gun checks on both CPU backends, or private real-game probes.

Everything written by this tool stays under .build; no network-source writes.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from smsrecomp.core import ROOT, ASSETS, convert, dependencies, run


def check(report_path, directory, frames=None):
    report = json.loads(report_path.read_text(encoding="utf-8"))
    game = Path(report["build_directory"])
    engine, sdl, cmake, generator = dependencies()
    source = ROOT / ".build/native-source"
    source.mkdir(parents=True, exist_ok=True)
    for file in (ASSETS / "native").iterdir():
        if file.is_file():
            shutil.copy2(file, source / file.name)
    build = directory / "build"
    run([cmake, "-S", source, "-B", build, "-G", generator, "-A", "x64",
         f"-DENGINE_DIR={engine.as_posix()}", f"-DGAME_DIR={game.as_posix()}",
         f"-DSMSRECOMP_BANKED_AOT={'ON' if report['backend'] == 'banked' else 'OFF'}",
         f"-DCMAKE_PREFIX_PATH={sdl.as_posix()}", "-DGAME_NAME=PhaserProof", "-DSMSRECOMP_PHASER_CHECKS=ON"])
    run([cmake, "--build", build, "--config", "Release", "--target", "smsrecomp_phaser_checks", "--parallel", "4"])
    env = os.environ.copy()
    env["SMSRECOMP_LIBRARY_DIR"] = str(directory / "learning")
    env["SMSRECOMP_STRICT"] = "1"
    args = [str(build / "Release/smsrecomp_phaser_checks.exe")]
    if frames:
        args += ["--game", str(frames)]
    result = subprocess.run(args, cwd=directory, env=env, capture_output=True, timeout=120)
    (directory / "checks.log").write_bytes(result.stdout + result.stderr)
    print(result.stdout.decode("utf-8", errors="replace"))
    if result.returncode:
        raise RuntimeError(f"Gun checks failed: {result.returncode}; see {directory / 'checks.log'}")
    return {"backend": report["backend"], "passed": True, "frames": frames, "native_fallback_cycles": 0}


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path)
    parser.add_argument("--frames", type=int, default=900)
    args = parser.parse_args()
    directory = ROOT / ".build/lightphaser-selftest"
    directory.mkdir(parents=True, exist_ok=True)
    if args.report:
        report = json.loads(args.report.read_text(encoding="utf-8"))
        target = directory / Path(report["executable"]).stem
        target.mkdir(parents=True, exist_ok=True)
        result = check(args.report, target, args.frames)
        (target / "verification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        return
    data = bytearray([0xC9] * 8192)
    data[:3] = bytes.fromhex("C3 00 01")
    program = bytes.fromhex("F3 31 F0 DF 3E FF D3 3F AF 32 03 C0 "
                            "DB DC 32 00 C0 DB DD CB 77 20 F5 "
                            "DB 7E 32 01 C0 DB 7F 32 02 C0 3E 01 32 03 C0 C3 0C 01")
    data[0x100:0x100+len(program)] = program
    rom = directory / "Authored gun CPU proof.sms"
    rom.write_bytes(data)
    os.environ["RETRO_RECOMP_LIBRARY_DIR"] = str(directory / "library")
    results = []
    for backend in ("functions", "banked"):
        target = directory / backend
        target.mkdir(parents=True, exist_ok=True)
        exe = convert(rom, title=f"Gun_CPU_Proof_{backend}", output=target / "export",
                      backend=backend, passes=1, frames=2, use_cover=False, online_cover=False)
        results.append(check(exe.parent / "conversion-report.json", target))
    (directory / "verification.json").write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
