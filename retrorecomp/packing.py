"""Compact validated game builds before they become public exports.

Windows and Linux x86-64 games are packed with the bundled, unmodified UPX
5.3.0 (licenses/UPX.md), then tested by UPX itself. This is how a game is
built, not what it does: a build input (compilation_inputs.BUILD_MODULES).
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile

from . import timings
from .paths import ASSETS


UPX_VERSION = "5.3.0"
UPX_LEVEL = "-9"
UPX_SHA256 = "ff30a651c9e41a2bbb363825fac9e7e23d92871c1ac82813a264e3b8d1cd302b"
# Official upx-5.3.0-amd64_linux.tar.xz (SHA-256 79cea8a5...dc505c1), its upx file.
UPX_LINUX = "assets/tools/upx-amd64_linux"
UPX_LINUX_SHA256 = "39bbf81cb4c56ce3e2e13a1755a31ec4970e33f061db8e214e9fac59354fc9aa"
# Large Mega Drive and Super Nintendo ELFs take longer than PEs to pack at -9.
LINUX_TIMEOUT = 300
# UPX 5.2.0 and 5.2.1 can reject, with "compressed data violation", their own default (NRV) packing of a
# large ELF at `upx -t` and `upx -d` although the data are valid and the packed program runs (upx/upx
# issue 18937: the test unpacks each block in place with too little slack; fixed in UPX 5.3.0, the bundled
# release since 1.6.2). Seen on Debian with the 78 MB Neo Geo Metal Slug 3 game, in 1.5.6 as in
# 1.6.0. -1, --best, --nrv2b/d/e, --no-filter and a stripped file fail the same way. --lzma passes the test
# and is smaller (40 MB against 45 MB) but a start costs 2.7 s instead of 0.17 s on a Core i7-6600U (the
# unpacked 78 MB file starts in 0.01 s), and the Neo Geo F11 machine switch starts the file again: not
# worth it for the player, so a game UPX cannot pack and test is published unpacked, as built and validated.
# 5.3.0 fixes the known case; the fallback stays as a safety net for any other game UPX rejects.
# The reason is kept for packing_record by the SHA-256 of the unpacked bytes, and handed to the caller's
# `emit` (the conversion log that the interface and the batch command line show); with no `emit` it goes
# to stderr, once.
_UNPACKED_REASONS: dict[str, str] = {}


def file_identity(path: Path) -> dict:
    """Size and SHA-256 of one executable."""
    data = Path(path).read_bytes()
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def packing_record(unpacked: dict, published: Path, packed_replayed: bool = False) -> dict:
    """What a conversion report says about the published executable's packing.

    The conversion compares native and reference runs on the *unpacked* build
    executable; the published one is that file packed by UPX. This records both
    identities and whether the published file really carries the UPX header, so
    a packed validation (tools/snes_packed_check.py) can name the exact file it
    checked. It claims a packed replay only when the conversion says it did one
    (`packed_replayed`: Neo Geo, CPS-1 and X68000 replay a packed copy against the
    reference, `native_validation.packed_reference_match`). A Linux game that UPX
    could not pack and test is published unpacked (`packed` false) and `unpacked_reason`
    says why.
    """
    data = Path(published).read_bytes()
    packed = b'UPX!' in data
    record = {'packer': 'UPX', 'version': UPX_VERSION, 'level': UPX_LEVEL, 'packed': packed,
              'unpacked': unpacked,
              'published': {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()},
              'size_ratio': round(len(data) / max(1, unpacked['bytes']), 4),
              'compared_on': 'unpacked build executable',
              'packed_validation': 'tools/snes_packed_check.py (developer qualification, not run during conversion)'}
    if packed_replayed:
        record['compared_on'] = 'unpacked build executable and a packed copy replayed against the reference'
        record['packed_validation'] = 'packed copy replayed during conversion (native_validation.packed_reference_match)'
    reason = _UNPACKED_REASONS.get(unpacked.get('sha256'))
    if reason and not packed:
        record['unpacked_reason'] = reason
    return record


def compact_executable(path: Path, emit=None) -> dict | None:
    """``_compact_executable``, its time counted as the ``packing`` phase of the conversion (timings.py)."""
    with timings.phase('packing'):
        return _compact_executable(path, emit)


def _compact_executable(path: Path, emit=None) -> dict | None:
    """Pack a disposable staged copy; raise before replacing an existing game.

    Windows raises when UPX cannot pack and test the file. On Linux that is a last
    resort only (see compact_linux). Returns None when the file was packed as usual or
    left as built on purpose, else {'notice': text}, the reason it stays unpacked. The
    text is passed to `emit` (the conversion log) when given, else printed on stderr:
    never both, so a command line shows it once."""
    if os.name != 'nt':
        outcome = compact_linux(path)
        if outcome:
            if emit is not None:
                emit(outcome['notice'])
            else:
                print(outcome['notice'], file=sys.stderr, flush=True)
        return outcome
    tool = ASSETS / "assets/tools/upx.exe"
    if not tool.is_file() or hashlib.sha256(tool.read_bytes()).hexdigest() != UPX_SHA256:
        raise RuntimeError("Bundled UPX 5.3.0 is missing or failed its integrity check.")
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
    return None


def _linux_tool(folder: Path) -> tuple[Path, Path | None]:
    """The verified packer, and a private copy to delete when the bundled one
    is not executable (a converter unpacked without file modes)."""
    tool = ASSETS / UPX_LINUX
    data = tool.read_bytes() if tool.is_file() else b''
    if hashlib.sha256(data).hexdigest() != UPX_LINUX_SHA256:
        raise RuntimeError("Bundled UPX 5.3.0 is missing or failed its integrity check.")
    if os.access(tool, os.X_OK):
        return tool, None
    # Beside the game being published: that volume must already allow programs.
    private = Path(tempfile.mkdtemp(prefix='.upx-', dir=folder))
    copy = private / 'upx'
    with copy.open('xb') as stream:
        stream.write(data)
    copy.chmod(0o700)
    return copy, private


def _upx_attempt(tool: Path, path: Path) -> str | None:
    """Pack then test `path` in place: None when both passed, else why not. A packer
    that cannot even start (OSError) is an installation fault and stays an error."""
    for args in (("-9", "-q", str(path)), ("-t", "-q", str(path))):
        try:
            result = subprocess.run((str(tool), *args), capture_output=True, text=True,
                                    timeout=LINUX_TIMEOUT)
        except subprocess.TimeoutExpired:
            return f"UPX {args[0]} timed out after {LINUX_TIMEOUT} s"
        except OSError as exc:
            raise RuntimeError(f"UPX could not compact or verify {path.name}: {exc}") from exc
        if result.returncode:
            detail = (result.stderr or result.stdout).strip().splitlines()
            # "upx-amd64_linux: /path/packed-game.exe: Exception: compressed data violation"
            return detail[-1].replace(f"{path}: ", "").split(": ", 1)[-1] if detail else 'unknown error'
    return None


def compact_linux(path: Path) -> dict | None:
    """Pack a native Linux x86-64 game; leave other ELFs as built.

    Every console is packed. Players only use /proc/self/exe to find their
    folder; their data, X68000 disks and firmware included, is linked into the
    program (resources.embed_resources) and restored by UPX with the rest.

    The packing is the one every earlier release used, byte for byte. When UPX cannot
    pack the game or rejects its own result (see the note on UPX 5.2.0 and 5.2.1 above), the
    validated original is put back and the game is published unpacked, exactly as built,
    rather than failing the whole conversion. That is returned as {'notice': text};
    None means the game was packed and tested, or is not an x86-64 ELF."""
    with path.open('rb') as stream:
        header = stream.read(20)
    if header[:4] != b'\x7fELF':
        raise RuntimeError('Expected a native Linux ELF executable.')
    # 64-bit little-endian x86-64 only: the bundled UPX is an x86-64 program.
    if (header[4:6] != b'\x02\x01' or int.from_bytes(header[18:20], 'little') != 62
            or platform.machine().lower() not in ('x86_64', 'amd64')):
        return None
    tool, private = _linux_tool(path.parent)
    # UPX rewrites the file in place: keep the validated original beside it.
    handle, name = tempfile.mkstemp(prefix='.upx-original-', dir=path.parent)
    os.close(handle)
    original = Path(name)
    try:
        shutil.copyfile(path, original)
        failure = _upx_attempt(tool, path)
        if failure is None:
            return None
        shutil.copyfile(original, path)
        notice = (
            f"UPX {UPX_VERSION} could not pack and verify the executable ({failure}"
            f"{'; upx/upx issue 18937' if 'violation' in failure else ''}). It is published unpacked, "
            "exactly as built and validated: a larger file, the same program.")
        _UNPACKED_REASONS[hashlib.sha256(original.read_bytes()).hexdigest()] = notice
        return {'notice': notice}
    finally:
        original.unlink(missing_ok=True)
        if private:
            shutil.rmtree(private, ignore_errors=True)
