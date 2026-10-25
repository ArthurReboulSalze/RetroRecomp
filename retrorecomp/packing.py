"""Compact validated game builds before they become public exports.

Windows and Linux x86-64 games are packed with the bundled, unmodified UPX
5.2.1 (licenses/UPX.md), then tested by UPX itself. This is how a game is
built, not what it does: a build input (compilation_inputs.BUILD_MODULES).
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile

from .paths import ASSETS


UPX_SHA256 = "d20ebe0b7b22b6be968c8c34be61f94ddea12cb11462e2cec27f548ef9574df8"
# Official upx-5.2.1-amd64_linux.tar.xz (SHA-256 402162aa...1b91657), its upx file.
UPX_LINUX = "assets/tools/upx-amd64_linux"
UPX_LINUX_SHA256 = "287b3dffe9dcafd8e366e162ac4ab41e5cf45a3c6768970256af0869288d84a1"
# Linux exports not yet run compressed stay as built. X68000 games are known by
# the private payload table every X68000 player embeds (x68000_conversion.payload).
LINUX_AS_BUILT = (b'system/keropi/iplrom.dat\0',)
# Large Mega Drive and Super Nintendo ELFs take longer than PEs to pack at -9.
LINUX_TIMEOUT = 300


def compact_executable(path: Path) -> None:
    """Pack a disposable staged copy; raise before replacing an existing game."""
    if os.name != 'nt':
        compact_linux(path)
        return
    tool = ASSETS / "assets/tools/upx.exe"
    if not tool.is_file() or hashlib.sha256(tool.read_bytes()).hexdigest() != UPX_SHA256:
        raise RuntimeError("Bundled UPX 5.2.1 is missing or failed its integrity check.")
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    # The exhaustive --best search can spend minutes on large native ROM-PC
    # tables. Level 9 retains the same transparent loader and most of the
    # size reduction with a bounded conversion time.
    for args in (("-9", "--compress-resources=0", "--compress-icons=0", str(path)),
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


def _contains(path: Path, needles) -> bool:
    carry, overlap = b'', max(len(n) for n in needles) - 1
    with path.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            data = carry + chunk
            if any(needle in data for needle in needles):
                return True
            carry = data[-overlap:] if overlap else b''
    return False


def _linux_tool(folder: Path) -> tuple[Path, Path | None]:
    """The verified packer, and a private copy to delete when the bundled one
    is not executable (a converter unpacked without file modes)."""
    tool = ASSETS / UPX_LINUX
    data = tool.read_bytes() if tool.is_file() else b''
    if hashlib.sha256(data).hexdigest() != UPX_LINUX_SHA256:
        raise RuntimeError("Bundled UPX 5.2.1 is missing or failed its integrity check.")
    if os.access(tool, os.X_OK):
        return tool, None
    # Beside the game being published: that volume must already allow programs.
    private = Path(tempfile.mkdtemp(prefix='.upx-', dir=folder))
    copy = private / 'upx'
    with copy.open('xb') as stream:
        stream.write(data)
    copy.chmod(0o700)
    return copy, private


def compact_linux(path: Path) -> None:
    """Pack a native Linux x86-64 game; leave other ELFs as built."""
    with path.open('rb') as stream:
        header = stream.read(20)
    if header[:4] != b'\x7fELF':
        raise RuntimeError('Expected a native Linux ELF executable.')
    # 64-bit little-endian x86-64 only: the bundled UPX is an x86-64 program.
    if (header[4:6] != b'\x02\x01' or int.from_bytes(header[18:20], 'little') != 62
            or platform.machine().lower() not in ('x86_64', 'amd64')):
        return
    if _contains(path, LINUX_AS_BUILT):
        return
    tool, private = _linux_tool(path.parent)
    try:
        # Same level as Windows; PE-only resource options do not apply to ELF.
        for args in (("-9", "-q", str(path)), ("-t", "-q", str(path))):
            try:
                result = subprocess.run((str(tool), *args), capture_output=True, text=True,
                                        timeout=LINUX_TIMEOUT)
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise RuntimeError(f"UPX could not compact or verify {path.name}: {exc}") from exc
            if result.returncode:
                detail = (result.stderr or result.stdout).strip().splitlines()
                raise RuntimeError(f"UPX could not compact or verify {path.name}: "
                                   f"{detail[-1] if detail else 'unknown error'}")
    finally:
        if private:
            shutil.rmtree(private, ignore_errors=True)
