"""Prepare and audit public sources and converter releases; never upload them."""
from __future__ import annotations

import argparse
import hashlib
import json
import marshal
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.15.0"
PUBLIC_FILES = tuple("""
.gitattributes .gitignore .github/workflows/checks.yml
README.md LICENSE CONTRIBUTING.md THIRD_PARTY_NOTICES.md
RetroRecomp.py requirements.txt
docs/ARCHITECTURE.md docs/BUILDING.md docs/COMPATIBILITY.md
docs/CONTROLS.md docs/ROADMAP.md docs/RELEASE_NOTES.md docs/SYSTEM_PROFILES.md docs/GAME_GEAR.md docs/GAME_BOY.md docs/NES.md
MEDIAS/RetroRecomp_logo.png MEDIAS/RetroRecomp_ban.png
MEDIAS/RetroRecomp_UI.png MEDIAS/RC_Windows_Screen.png
MEDIAS/TAG_SHOOTING.png assets/tag-shooting.png
profiles/example.sms.toml
assets/Retro-Recomp-banner.png assets/Retro-Recomp.ico
assets/Retro-Recomp-icon-16.png assets/Retro-Recomp-icon-20.png
assets/Retro-Recomp-icon-24.png assets/Retro-Recomp-icon-32.png
assets/Retro-Recomp-icon-40.png assets/Retro-Recomp-icon-48.png
assets/Retro-Recomp-icon-64.png assets/Retro-Recomp-icon-128.png
assets/Retro-Recomp-icon-256.png
assets/tools/upx.exe
licenses/z80-recomp-core.md licenses/superzazu-z80.md licenses/SDL2.md
licenses/gb-recompiled.md licenses/dear-imgui.md licenses/nesrecomp.md licenses/emu2413.md
licenses/UPX.md
licenses/upx-5.2.1-src.tar.xz
licenses/SingleStepTests-z80.md licenses/Python.md licenses/Tcl-Tk.md
licenses/Pillow.md licenses/PyInstaller.md licenses/PyInstaller-hooks.md
licenses/OpenSSL.md licenses/zlib.md licenses/zlib-ng.md
smsrecomp/__init__.py smsrecomp/artwork.py smsrecomp/batch.py
smsrecomp/core.py smsrecomp/cpu.py smsrecomp/gui.py smsrecomp/i18n.py smsrecomp/updater.py
smsrecomp/library.py smsrecomp/paths.py smsrecomp/publishing.py smsrecomp/packing.py
smsrecomp/tooltips.py smsrecomp/validation.py smsrecomp/windows.py
smsrecomp/peripherals.py
smsrecomp/metadata.py tests/test_metadata.py
smsrecomp/systems/__init__.py smsrecomp/systems/master_system.py
smsrecomp/systems/game_gear.py smsrecomp/systems/game_boy.py
smsrecomp/gameboy.py smsrecomp/gameboy_runtime.py
smsrecomp/gameboy_timing.py
smsrecomp/gameboy_coverage.py tests/test_gameboy_coverage.py
smsrecomp/nes.py smsrecomp/nes_runtime.py smsrecomp/systems/nes.py tests/test_nes.py
native/CMakeLists.txt native/banked_cpu_checks.c native/banked_dispatch.c
native/banked_emitter.inc native/banked_runtime.inc native/banked_vectors.c
native/controls.c native/controls.h native/host.c native/host_checks.c
native/host_control.h native/icon.c native/icon.h native/icon_checks.c
native/input_checks.c native/launcher.c native/learning.c native/learning.h
native/manifest.inc native/paths.c native/paths.h native/ui.c native/ui.h
native/retro_menu.c native/retro_menu.h native/gb_menu.inc
native/nes_host_ui.c
native/gb_input_refresh.inc
native/gb_latency_checks.cpp tools/gameboy_latency_selftest.py
native/video_frame.h native/video_mode4.inc native/video_checks.c native/video_probe.c
native/lightphaser.c native/lightphaser.h native/lightphaser_checks.c
native/frame_stop_checks.c
native/gamestate.h native/gamestate.inc native/state_io.h native/psg_state.inc
native/gamestate_checks.c tools/gamestate_selftest.py docs/GAME_STATES.md
native/lazy_data_checks.c tools/lazy_data_selftest.py
native/presentation_checks.c tools/presentation_selftest.py
tests/test_artwork.py tests/test_batch.py tests/test_i18n.py
tests/test_library.py tests/test_publishing.py tests/test_updater.py tests/test_rom.py
tests/test_validation.py tests/test_publication.py
tests/test_peripherals.py
tools/banked_cpu_selftest.py tools/banked_selftest.py
tools/banked_vector_selftest.py tools/banked_verify.py tools/cpu_selftest.py
tools/data_selftest.py tools/fetch_z80_vectors.py tools/gui_smoke.py
tools/host_selftest.py tools/icon_selftest.py tools/install_converter.py
tools/learning_selftest.py tools/package.ps1 tools/player2_selftest.py
tools/prepare_logo.py tools/publishing_selftest.py tools/prepare_publication.py
tools/lightphaser_selftest.py tools/video_selftest.py docs/LIGHT_PHASER.md docs/VIDEO.md
tools/frame_stop_selftest.py
tests/test_game_gear.py tests/test_game_boy.py
""".split())
PUBLIC_SET = frozenset(PUBLIC_FILES)
BUNDLED_FILES = frozenset(p for p in PUBLIC_FILES
                          if p.startswith(("native/", "assets/", "profiles/"))
                          or (p.startswith("licenses/") and p.endswith(".md"))
                          or p in {"LICENSE", "THIRD_PARTY_NOTICES.md"})
TEXT_EXTENSIONS = {".py", ".md", ".c", ".cpp", ".h", ".inc", ".ps1", ".toml", ".yml"}
SENSITIVE = {
    "private drive path": re.compile(r"(?i)\b[A-Z]:[\\/](?:Users|Projects)[\\/]"),
    "private network path": re.compile(r"\\\\(?:\d{1,3}\.){3}\d{1,3}\\"),
    "GitHub credential": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    "GitHub fine-grained credential": re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,}"),
    "API credential": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{24,}"),
    "AWS credential": re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "literal password": re.compile(r"(?i)\b(?:password|api_key|access_token)\s*=\s*['\"][^'\"]{8,}['\"]"),
}


def check_public_file(name: str, data: bytes) -> None:
    """Fail with the rule name only, without printing sensitive contents."""
    if name not in PUBLIC_SET:
        raise ValueError(f"Not on the public allowlist: {name}")
    if Path(name).suffix.lower() in TEXT_EXTENSIONS or name == "LICENSE":
        content = data.decode("utf-8-sig")
        for label, pattern in SENSITIVE.items():
            if pattern.search(content):
                raise ValueError(f"{name}: {label}")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def audit_sources(root: Path) -> dict:
    entries = []
    for name in PUBLIC_FILES:
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Missing or symbolic-link public file: {name}")
        data = path.read_bytes()
        check_public_file(name, data)
        entries.append({"path": name, "bytes": len(data), "sha256": digest(data)})
    return {"files": entries, "count": len(entries)}


def stage_sources(root: Path, target: Path) -> dict:
    report = audit_sources(root)
    if target == root or root.is_relative_to(target):
        raise ValueError("The public snapshot must be separate from the source root.")
    target.mkdir(parents=True, exist_ok=True)
    # Repeated preparation overwrites only approved files; never delete user data.
    for name in PUBLIC_FILES:
        dest = target / name
        if dest.is_symlink() or not dest.resolve().is_relative_to(target.resolve()):
            raise ValueError(f"Unsafe snapshot path: {name}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / name, dest)
    audit_sources(target)
    extras = [p.relative_to(target).as_posix() for p in target.rglob("*")
              if p.is_file() and p.relative_to(target).as_posix() not in PUBLIC_SET
              and not any(part in {".git", ".build", "Export", "__pycache__"}
                          for part in p.relative_to(target).parts)]
    if extras:
        raise ValueError(f"Unexpected snapshot files: {extras}")
    return report


def audit_staged(root: Path) -> dict:
    names = subprocess.check_output(["git", "diff", "--cached", "--name-only",
                                     "--diff-filter=ACMR", "-z"], cwd=root)
    paths = [p.decode("utf-8") for p in names.split(b"\0") if p]
    for name in paths:
        data = subprocess.check_output(["git", "show", f":{name}"], cwd=root)
        check_public_file(name, data)
    return {"staged_count": len(paths), "staged_files": paths}


def audit_tracked(root: Path) -> dict:
    names = subprocess.check_output(["git", "ls-files", "-z"], cwd=root)
    paths = [p.decode("utf-8") for p in names.split(b"\0") if p]
    for name in paths:
        if name not in PUBLIC_SET:
            raise ValueError(f"Not on the public allowlist: {name}")
        check_public_file(name, (root / name).read_bytes())
    return {"tracked_count": len(paths), "tracked_files": paths}


def audit_executable(executable: Path, source: Path) -> dict:
    """Inspect decompressed PyInstaller assets and our compiled Python modules."""
    from PyInstaller.archive.readers import CArchiveReader
    archive = CArchiveReader(str(executable))
    bundled = {}
    for original in archive.toc:
        name = original.replace("\\", "/")
        if name.startswith(("native/", "assets/", "profiles/", "licenses/")) or name in {
                "LICENSE", "THIRD_PARTY_NOTICES.md"}:
            if name not in BUNDLED_FILES:
                raise ValueError(f"Unexpected executable payload: {name}")
            data = archive.extract(original)
            if data != (source / name).read_bytes():
                raise ValueError(f"Executable payload differs from public source: {name}")
            bundled[name] = digest(data)
        if name.lower().endswith((".sms", ".gg", ".gb", ".nes", ".fds", ".rom", ".manifest", ".patterns")):
            raise ValueError(f"Game data in executable: {name}")
    if set(bundled) != BUNDLED_FILES:
        raise ValueError("The executable is missing public resources.")
    pyz = archive.open_embedded_archive("PYZ.pyz")
    modules = []
    for name in PUBLIC_FILES:
        if not name.startswith("smsrecomp/"):
            continue
        module = name[:-3].replace("/", ".").removesuffix(".__init__")
        actual = pyz.extract(module)
        expected = compile((source / name).read_text(encoding="utf-8-sig"),
                           actual.co_filename, "exec", dont_inherit=True, optimize=0)
        if actual != expected:
            raise ValueError(f"Frozen Python differs from public source: {module}")
        modules.append(module)
    entry = marshal.loads(archive.extract("RetroRecomp"))
    expected = compile((source / "RetroRecomp.py").read_text(encoding="utf-8-sig"),
                       entry.co_filename, "exec", dont_inherit=True, optimize=0)
    if entry != expected:
        raise ValueError("Frozen entrypoint differs from public source.")
    return {"archive_entries": len(archive.toc), "resources": bundled,
            "modules": modules, "sha256": digest(executable.read_bytes())}


def make_standalone(source: Path, executable: Path, target: Path) -> dict:
    """Publish the converter as a single EXE with linked source and bundled notices."""
    proof = audit_executable(executable, source)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix('.exe.pending')
    shutil.copyfile(executable, temporary)
    temporary.replace(target)
    sha = digest(target.read_bytes())
    return {"exe": str(target), "sha256": sha, "bytes": target.stat().st_size,
            "executable": proof}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT)
    parser.add_argument("--stage", type=Path, help="Create an allowlisted public source snapshot.")
    parser.add_argument("--staged", action="store_true", help="Audit outgoing Git index files.")
    parser.add_argument("--tracked", action="store_true", help="Audit all tracked public files (CI).")
    parser.add_argument("--exe", type=Path, help="Clean converter to inspect for --standalone.")
    parser.add_argument("--standalone", type=Path, help="Write a single-file converter.")
    parser.add_argument("--report", type=Path, help="Write a local JSON audit (never bundled).")
    args = parser.parse_args()
    root = args.source.resolve()
    report = {"version": VERSION, "source": audit_sources(root)}
    if args.staged:
        report["git"] = audit_staged(root)
    if args.tracked:
        report["tracked"] = audit_tracked(root)
    if args.stage:
        report["snapshot"] = stage_sources(root, args.stage.resolve())
    if args.standalone:
        if not args.exe:
            parser.error("--standalone requires --exe")
        report["standalone"] = make_standalone(root, args.exe.resolve(), args.standalone.resolve())
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"public_files": report["source"]["count"],
                      "snapshot": str(args.stage) if args.stage else None,
                      "staged_files": report.get("git", {}).get("staged_count"),
                      "standalone": report.get("standalone", {}).get("exe"),
                      "sha256": report.get("standalone", {}).get("sha256")}, indent=2))


if __name__ == "__main__":
    main()
