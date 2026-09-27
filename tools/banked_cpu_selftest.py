"""Compare native instruction bodies to the shared reference on ROM positions.

Run after converting the chosen game with --backend banked. Every register,
including WZ and Q/P, is required to agree. No flag or I/O mismatches are masked.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from smsrecomp.core import ROOT, ASSETS, dependencies, run
from smsrecomp.paths import games_directory


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path, nargs="?", default=games_directory())
    args = parser.parse_args()
    report_path = args.output / 'conversion-report.json'
    if not report_path.exists():
        report_path = next((args.output / 'datas/reports').glob('Bubble_Bobble-*/conversion-report.json'))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["backend"] == "banked"
    game = Path(report["build_directory"])
    engine, sdl, cmake, generator = dependencies()
    source = ROOT / ".build/native-source"
    for path in (ASSETS / "native").iterdir():
        if path.is_file():
            shutil.copy2(path, source / path.name)
    build = game / "build-native"
    log = game / "cpu-checks-build.log"
    run([cmake, "-S", source, "-B", build, "-DSMSRECOMP_CPU_CHECKS=ON"], log=log)
    run([cmake, "--build", build, "--config", "Release", "--target", "smsrecomp_cpu_checks", "--parallel", "4"], log=log)
    env = os.environ.copy()
    env["SMSRECOMP_LIBRARY_DIR"] = str(game / "checks/cpu-learning")
    result = subprocess.run([str(build / "Release/smsrecomp_cpu_checks.exe")], cwd=game,
        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120,
        creationflags=subprocess.CREATE_NO_WINDOW)
    text = result.stdout.decode("utf-8", errors="replace")
    (game / "checks/cpu-native.log").write_text(text, encoding="utf-8")
    (game / "checks/cpu-reference.log").write_bytes(result.stderr)
    stats = {key.lower(): int(value) for key, value in re.findall(r"([A-Z_]+)=(\d+)", text)}
    stats.update(exit_code=result.returncode, rom_sha256=report["rom"]["sha256"], compiler_signature=report["compiler_signature"])
    (game / "checks/cpu-differential.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    print(text[-5000:])
    assert result.returncode == 0 and stats.get("failed") == 0, game / "checks/cpu-native.log"


if __name__ == "__main__":
    main()
