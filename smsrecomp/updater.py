"""User-initiated updates of the portable Windows converter from GitHub releases."""
from __future__ import annotations

from dataclasses import dataclass
import ctypes
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import uuid
import zipfile

from . import __version__


REPOSITORY = "ArthurReboulSalze/RetroRecomp"
API_URL = f"https://api.github.com/repos/{REPOSITORY}/releases?per_page=100"
RELEASE_BASE = f"https://github.com/{REPOSITORY}/releases"
VERSION_PATTERN = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
MAX_ARCHIVE_BYTES = 200 * 1024 * 1024
MAX_UNPACKED_BYTES = 400 * 1024 * 1024
MAX_MEMBERS = 100
UPDATE_PREFIX = ".RetroRecomp-update-"


@dataclass(frozen=True)
class Update:
    version: str
    url: str
    page: str
    digest: str
    size: int


def _version(value: str) -> tuple[int, int, int] | None:
    match = VERSION_PATTERN.fullmatch(value)
    return tuple(map(int, match.groups())) if match else None


def select_update(releases: list[dict], current: str = __version__) -> Update | None:
    installed = _version("v" + current)
    if installed is None:
        raise ValueError("Invalid installed version")
    candidates = []
    for release in releases:
        tag = release.get("tag_name", "")
        number = _version(tag)
        if not number or number <= installed or release.get("draft"):
            continue
        # Pre-releases are intentional in this project; GitHub's /latest omits them.
        name = f"RetroRecomp-{tag}-windows-x64.zip"
        for asset in release.get("assets", []):
            digest = asset.get("digest", "")
            size = asset.get("size", 0)
            if (asset.get("name") == name and asset.get("state") == "uploaded"
                    and re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest)
                    and isinstance(size, int) and 0 < size <= MAX_ARCHIVE_BYTES):
                candidates.append((number, Update(tag[1:],
                    f"{RELEASE_BASE}/download/{tag}/{name}",
                    f"{RELEASE_BASE}/tag/{tag}", digest[7:].lower(), size)))
                break
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def check_for_update() -> Update | None:
    request = urllib.request.Request(API_URL, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"RetroRecomp/{__version__}",
    })
    with urllib.request.urlopen(request, timeout=15) as response:
        payload = response.read(2 * 1024 * 1024 + 1)
    if len(payload) > 2 * 1024 * 1024:
        raise ValueError("GitHub release response is too large")
    releases = json.loads(payload)
    if not isinstance(releases, list):
        raise ValueError("Invalid GitHub release response")
    return select_update(releases)


def _release_member(name: str) -> str:
    path = PurePosixPath(name)
    if (path.is_absolute() or "\\" in name or not path.parts or path.parts[0] != "RetroRecomp"
            or any(part in ("", ".", "..") for part in path.parts)):
        raise ValueError("Unsafe release ZIP path")
    relative = "/".join(path.parts[1:])
    if name != "RetroRecomp/" + relative:
        raise ValueError("Unsafe release ZIP path")
    if relative in ("Retro-Recomp.exe", "LICENSE", "THIRD_PARTY_NOTICES.md"):
        return relative
    if re.fullmatch(r"licenses/[A-Za-z0-9._+-]+(?:\.md|\.tar\.xz)", relative):
        return relative
    raise ValueError("Unexpected release ZIP member")


def _safe_job_dir(job_dir: Path, target: Path) -> Path:
    root = job_dir.resolve()
    if root.parent != target.resolve().parent or not root.name.startswith(UPDATE_PREFIX):
        raise ValueError("Invalid update directory")
    return root


def _remove_job_dir(job_dir: Path, target: Path) -> None:
    root = _safe_job_dir(job_dir, target)
    shutil.rmtree(root)


def discard_update(job_dir: Path, executable: Path) -> None:
    """Remove a prepared update if its detached helper could not be started."""
    _remove_job_dir(job_dir, executable)


def _unpack(archive_path: Path, destination: Path) -> dict[str, str]:
    files = {}
    total = 0
    with zipfile.ZipFile(archive_path) as archive:
        infos = archive.infolist()
        if len(infos) > MAX_MEMBERS:
            raise ValueError("Too many release ZIP members")
        for info in infos:
            relative = _release_member(info.filename)
            if relative in files or info.is_dir() or info.flag_bits & 1:
                raise ValueError("Invalid release ZIP member")
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("Release ZIP contains a link")
            total += info.file_size
            if total > MAX_UNPACKED_BYTES:
                raise ValueError("Release ZIP is too large")
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            with archive.open(info) as source, target.open("wb") as output:
                while chunk := source.read(1024 * 1024):
                    digest.update(chunk)
                    output.write(chunk)
            files[relative] = digest.hexdigest()
    if not {"Retro-Recomp.exe", "LICENSE", "THIRD_PARTY_NOTICES.md"}.issubset(files):
        raise ValueError("Release ZIP is incomplete")
    with (destination / "Retro-Recomp.exe").open("rb") as executable:
        if executable.read(2) != b"MZ":
            raise ValueError("Release does not contain a Windows executable")
    return files


def prepare_update(update: Update, executable: Path) -> tuple[Path, str]:
    """Download only after a click; stage on the install volume without touching games."""
    executable = executable.resolve()
    if executable.name.casefold() != "retro-recomp.exe":
        raise ValueError("Update is only available in the packaged converter")
    job_dir = Path(tempfile.mkdtemp(prefix=UPDATE_PREFIX, dir=executable.parent)).resolve()
    archive_path = job_dir / "release.zip"
    try:
        request = urllib.request.Request(update.url, headers={"User-Agent": f"RetroRecomp/{__version__}"})
        digest = hashlib.sha256()
        size = 0
        with urllib.request.urlopen(request, timeout=60) as response, archive_path.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_ARCHIVE_BYTES:
                    raise ValueError("Release download is too large")
                output.write(chunk)
                digest.update(chunk)
        if size != update.size or digest.hexdigest() != update.digest:
            raise ValueError("Downloaded release checksum does not match GitHub")
        files = _unpack(archive_path, job_dir / "files")
        if getattr(sys, "frozen", False):
            environment = os.environ.copy()
            environment["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
            subprocess.run([str(job_dir / "files/Retro-Recomp.exe"), "_verify-update", update.version],
                           cwd=job_dir, env=environment, stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                           timeout=45, check=True)
        token = uuid.uuid4().hex
        job = {"token": token, "version": update.version, "target": str(executable),
               "parent_pid": os.getpid(), "files": files}
        (job_dir / "job.json").write_text(json.dumps(job), encoding="utf-8")
        shutil.copy2(executable, job_dir / "updater-helper.exe")
        return job_dir, token
    except BaseException:
        _remove_job_dir(job_dir, executable)
        raise


def start_update_helper(job_dir: Path, token: str) -> None:
    helper = job_dir / "updater-helper.exe"
    environment = os.environ.copy()
    environment["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    subprocess.Popen([str(helper), "_apply-update", str(job_dir), token],
                     cwd=job_dir, env=environment, stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                     close_fds=True)


def _read_job(job_dir: Path, token: str) -> tuple[dict, Path]:
    job = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
    target = Path(job["target"]).resolve()
    if (job.get("token") != token or target.name.casefold() != "retro-recomp.exe"
            or _safe_job_dir(job_dir, target) != job_dir.resolve()):
        raise ValueError("Invalid update job")
    return job, target


def _wait_for_process(pid: int, timeout_ms: int = 120000) -> None:
    if os.name != "nt":
        return
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel.WaitForSingleObject.restype = ctypes.c_uint32
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.OpenProcess(0x100000, False, pid)
    if not handle:
        return
    try:
        if kernel.WaitForSingleObject(handle, timeout_ms) != 0:
            raise TimeoutError("The previous converter did not close")
    finally:
        kernel.CloseHandle(handle)


def _install_files(job_dir: Path, target: Path, files: dict[str, str]) -> None:
    """Replace release-owned files only; reverse every change if installation fails."""
    staged = job_dir / "files"
    backup = job_dir / "backup"
    changed = []
    try:
        for relative, expected in files.items():
            if _release_member("RetroRecomp/" + relative) != relative:
                raise ValueError("Invalid update manifest")
            source = staged / relative
            if hashlib.sha256(source.read_bytes()).hexdigest() != expected:
                raise ValueError("Staged update changed after verification")
        # Update notices first, executable last. The previous EXE remains
        # recoverable in the job directory until the restarted app cleans up.
        for relative in sorted(files, key=lambda item: item == "Retro-Recomp.exe"):
            destination = target.parent / relative
            previous = backup / relative
            if destination.parent != target.parent and destination.parent.is_symlink():
                raise ValueError("Update target is a linked directory")
            destination.parent.mkdir(parents=True, exist_ok=True)
            previous.parent.mkdir(parents=True, exist_ok=True)
            had_previous = destination.exists()
            if had_previous:
                os.replace(destination, previous)
            changed.append((relative, had_previous))
            os.replace(staged / relative, destination)
    except BaseException:
        _rollback_files(job_dir, target, changed)
        raise


def _rollback_files(job_dir: Path, target: Path, changed: list[tuple[str, bool]]) -> None:
    for relative, had_previous in reversed(changed):
        destination = target.parent / relative
        previous = job_dir / "backup" / relative
        if destination.exists():
            os.replace(destination, job_dir / "files" / relative)
        if had_previous:
            os.replace(previous, destination)


def apply_update(job_dir: Path, token: str) -> int:
    """Run from a temporary copy of the old EXE, then restart the new one."""
    job_dir = job_dir.resolve()
    job, target = _read_job(job_dir, token)
    try:
        _wait_for_process(job["parent_pid"])
        _install_files(job_dir, target, job["files"])
    except Exception as error:
        job["error"] = str(error)
        (job_dir / "job.json").write_text(json.dumps(job), encoding="utf-8")
        if not target.is_file():
            return 1
    environment = os.environ.copy()
    environment["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    try:
        subprocess.Popen([str(target), "_finish-update", str(job_dir), token, str(os.getpid())],
                         cwd=target.parent, env=environment, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                         close_fds=True)
    except OSError as error:
        if not job.get("error"):
            _rollback_files(job_dir, target, [(name, (job_dir / "backup" / name).exists())
                                               for name in job["files"]])
        job["error"] = str(error)
        (job_dir / "job.json").write_text(json.dumps(job), encoding="utf-8")
        return 1
    return 1 if job.get("error") else 0


def finish_update(job_dir: Path, token: str, helper_pid: int) -> str | None:
    """Run in the restarted EXE; remove temporary files after the helper exits."""
    job, target = _read_job(job_dir.resolve(), token)
    _wait_for_process(helper_pid, timeout_ms=30000)
    error = job.get("error")
    try:
        _remove_job_dir(job_dir, target)
    except OSError:
        # The installed converter should still open if cleanup is briefly
        # delayed by an antivirus scanner. No games or user data are touched.
        pass
    return error
