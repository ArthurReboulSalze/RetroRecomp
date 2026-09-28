"""Native SDL/controller checks, plus two standalone games sharing one INI.

Uses SDL's dummy drivers, never changes desktop focus or a physical controller.
Alex Kidd must already have been converted. All artifacts stay under .build.
"""
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import argparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from smsrecomp.core import ROOT, ASSETS, dependencies, run
from smsrecomp.paths import games_directory


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=games_directory())
    parser.add_argument("--game", default="Alex Kidd in Miracle World", help="Title of the exported game to exercise")
    parser.add_argument("--native-only", action="store_true", help="Exercise the source host before regenerating exported games")
    args = parser.parse_args()
    output = args.output
    report_path = output / "conversion-report.json"
    if not report_path.exists():
        report_path = next(path for path in (output / "datas/reports").glob("*/conversion-report.json")
                           if Path(json.loads(path.read_text(encoding="utf-8"))["executable"]).stem == args.game)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    output = Path(report.get("published_directory", output))
    game = Path(report["build_directory"])
    engine, sdl, cmake, generator = dependencies()
    source = ROOT / ".build/native-source"
    for file in (ASSETS / "native").iterdir():
        if file.is_file():
            shutil.copy2(file, source / file.name)
    banked = report.get("backend") == "banked"
    build = ROOT / ".build" / ("host-checks-banked-build" if banked else "host-checks-build")
    run([cmake, "-S", source, "-B", build, "-G", generator, "-A", "x64",
         f"-DENGINE_DIR={engine.as_posix()}", f"-DGAME_DIR={game.as_posix()}",
         f"-DSMSRECOMP_BANKED_AOT={'ON' if banked else 'OFF'}",
         "-DGAME_NAME=Alex_Kidd_in_Miracle_World", f"-DCMAKE_PREFIX_PATH={sdl.as_posix()}",
         "-DSMSRECOMP_HOST_CHECKS=ON"])
    run([cmake, "--build", build, "--config", "Release", "--target", "smsrecomp_host_checks", "--parallel", "4"])
    from smsrecomp.core import slug
    artifacts = ROOT / ".build/host-checks-artifacts" / slug(args.game)
    artifacts.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy")
    env["SMSRECOMP_LIBRARY_DIR"] = str(artifacts / "learning")
    result = subprocess.run([str(build / "Release/smsrecomp_host_checks.exe"), str(artifacts / "SMSRecomp.ini")],
                            cwd=artifacts, env=env, capture_output=True, timeout=40)
    (artifacts / "native-checks.log").write_bytes(result.stdout + result.stderr)
    print(result.stdout.decode("utf-8", errors="replace"))
    if result.returncode:
        raise RuntimeError(f"Native checks failed: {result.returncode}; see {artifacts / 'native-checks.log'}")
    if args.native_only:
        return

    # The actual game must resolve its config relative to the executable,
    # regardless of cwd, filename, Unicode folder name or which game launches.
    shared = artifacts / "jeux partagés"
    shared.mkdir(exist_ok=True)
    first = shared / "Premier_jeu.exe"
    second = shared / "Deuxieme_jeu.exe"
    for path in (first, second):
        shutil.copy2(output / report["executable"], path)
    ini = shared / "datas/Retro-Recomp.ini"
    if ini.exists():
        ini.unlink()
    args = ["--headless", "--window", "3", "--frames", "2", "--strict", "--mute"]
    def launch(path, log):
        result = subprocess.run([str(path), *args, "--log", str(log)], cwd=artifacts, env=env, timeout=10)
        assert result.returncode == 0, result.returncode
    launch(first, artifacts / "shared-first.log")
    assert not ini.exists(), "Simply starting a game must not create an INI."
    ini.parent.mkdir(parents=True, exist_ok=True)
    ini.write_text('[Clavier]\r\nbouton1=C\r\n[ClavierJ2]\r\nbouton1=V\r\n[Video]\r\nfiltre=3\r\n', encoding='ascii')
    text = ini.read_text(encoding="ascii")
    assert "masquer_bord_gauche" not in text
    text = text.replace("bouton1=Z", "bouton1=C").replace("bouton1=Keypad 8", "bouton1=V").replace("filtre=0", "filtre=3")
    ini.write_text(text, encoding="ascii")
    before = ini.read_bytes()
    launch(second, artifacts / "shared-second.log")
    assert ini.read_bytes() == before
    assert not (shared / "Retro-Recomp.ini").exists()
    print("PASS: renamed games create no startup INI and preserve an explicitly saved shared INI from another cwd.")


if __name__ == "__main__":
    main()
