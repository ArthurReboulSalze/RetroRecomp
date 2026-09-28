"""Compact validated Windows game builds before they become public exports."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess

from .paths import ASSETS


UPX_SHA256 = "d20ebe0b7b22b6be968c8c34be61f94ddea12cb11462e2cec27f548ef9574df8"


def compact_executable(path: Path) -> None:
    """Pack a disposable staged copy; raise before replacing an existing game."""
    tool = ASSETS / "assets/tools/upx.exe"
    if not tool.is_file() or hashlib.sha256(tool.read_bytes()).hexdigest() != UPX_SHA256:
        raise RuntimeError("Bundled UPX 5.2.1 is missing or failed its integrity check.")
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    for args in (("--best", "--compress-resources=0", "--compress-icons=0", str(path)),
                 ("-t", str(path))):
        try:
            result = subprocess.run((str(tool), *args), capture_output=True, text=True,
                                    timeout=120, creationflags=flags)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError(f"UPX could not compact or verify {path.name}: {exc}") from exc
        if result.returncode:
            detail = (result.stderr or result.stdout).strip().splitlines()
            raise RuntimeError(f"UPX could not compact or verify {path.name}: "
                               f"{detail[-1] if detail else 'unknown error'}")
