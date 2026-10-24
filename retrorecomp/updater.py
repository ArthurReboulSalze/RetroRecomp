"""User-initiated, platform-specific portable converter updates from GitHub."""
from __future__ import annotations

from dataclasses import dataclass
import ctypes
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import uuid
import select

from . import __version__
from .platforms import target_id


REPOSITORY = "ArthurReboulSalze/RetroRecomp"
API_URL = f"https://api.github.com/repos/{REPOSITORY}/releases?per_page=100"
RELEASE_BASE = f"https://github.com/{REPOSITORY}/releases"
VERSION_PATTERN = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
MAX_ARCHIVE_BYTES = 200 * 1024 * 1024
UPDATE_PREFIX = ".RetroRecomp-update-"


class UpdateConnectionError(Exception):
    """The release server could not be reached through the current network."""


class UpdateServiceError(Exception):
    """The release server responded, but could not serve the request."""


def _open_release_url(request: urllib.request.Request, timeout: int):
    try:
        return urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.HTTPError as error:
        if error.code in (401, 403, 407):
            raise UpdateConnectionError() from error
        raise UpdateServiceError() from error
    except OSError as error:
        raise UpdateConnectionError() from error


def _read_release_bytes(response, size: int) -> bytes:
    try:
        return response.read(size)
    except (OSError, http.client.IncompleteRead) as error:
        raise UpdateConnectionError() from error


@dataclass(frozen=True)
class Update:
    version: str
    url: str
    page: str
    digest: str
    size: int
    target: str = 'windows-x86_64'
    # Plain-text release notes of every version newer than the installed one,
    # newest first, so a skipped version's changes are shown too.
    notes: str = ''


NOTES_LIMIT = 12000


def release_notes(body, limit: int = NOTES_LIMIT) -> str:
    """The GitHub release body as readable plain text.

    The notes are written in Markdown and hard-wrapped; a dialog wraps them
    itself. Headings, emphasis, code marks and link targets are dropped, the
    lines of one paragraph or bullet are joined, and the text is bounded."""
    if not isinstance(body, str) or not body.strip():
        return ''
    text = body.replace('\r\n', '\n')[:limit * 2]
    text = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'(\*\*|__|`)', '', text)
    blocks, current = [], []
    def flush():
        if current:
            blocks.append(' '.join(part.strip() for part in current))
            current.clear()
    for line in text.split('\n'):
        stripped = line.strip()
        if not stripped or stripped == '---':
            flush()
            continue
        if stripped.startswith('#'):
            flush()
            blocks.append(stripped.lstrip('#').strip())
            continue
        if re.match(r'^[-*+]\s+', stripped):
            flush()
            current.append('• ' + stripped[1:].strip())
            continue
        current.append(stripped)
    flush()
    result = '\n\n'.join(block for block in blocks if block)
    if len(result) > limit:
        cut = result[:limit].rsplit('\n', 1)[0].rstrip()
        result = cut + '\n…'
    return result


def release_asset(target: str) -> str:
    names = {'windows-x86_64': 'Retro-Recomp.exe',
             'linux-x86_64': 'Retro-Recomp-linux-x86_64'}
    if target not in names:
        raise ValueError('No compatible converter update is available for this platform.')
    return names[target]


def _target_platform(executable: Path) -> str:
    if executable.name.casefold() == 'retro-recomp.exe':
        return 'windows-x86_64'
    if executable.name in ('Retro-Recomp', 'Retro-Recomp-linux-x86_64'):
        return 'linux-x86_64'
    raise ValueError('Update is only available in the packaged converter')


def _version(value: str) -> tuple[int, int, int] | None:
    match = VERSION_PATTERN.fullmatch(value)
    return tuple(map(int, match.groups())) if match else None


def select_update(releases: list[dict], current: str = __version__, *, target: str | None = None) -> Update | None:
    target = target or target_id()
    wanted = release_asset(target)
    installed = _version("v" + current)
    if installed is None:
        raise ValueError("Invalid installed version")
    candidates = []
    notes = []
    for release in releases:
        tag = release.get("tag_name", "")
        number = _version(tag)
        if not number or number <= installed or release.get("draft"):
            continue
        text = release_notes(release.get("body"))
        if text:
            notes.append((number, f"{tag[1:]}\n\n{text}" if not text.startswith(tag[1:]) else text))
        # Pre-releases are intentional in this project; GitHub's /latest omits them.
        for asset in release.get("assets", []):
            name = asset.get("name")
            digest = asset.get("digest", "")
            size = asset.get("size", 0)
            if (name == wanted and asset.get("state") == "uploaded"
                    and re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest)
                    and isinstance(size, int) and 0 < size <= MAX_ARCHIVE_BYTES):
                candidates.append((number, tag, name, digest[7:].lower(), size))
    if not candidates:
        return None
    number, tag, name, digest, size = max(candidates, key=lambda item: item[0])
    # Only versions up to the offered one; newest first, bounded as a whole.
    text = "\n\n".join(entry for n, entry in sorted(notes, reverse=True) if n <= number)
    if len(text) > NOTES_LIMIT:
        text = text[:NOTES_LIMIT].rsplit("\n", 1)[0].rstrip() + "\n…"
    return Update(tag[1:], f"{RELEASE_BASE}/download/{tag}/{name}",
                  f"{RELEASE_BASE}/tag/{tag}", digest, size, target, text)


def check_for_update() -> Update | None:
    request = urllib.request.Request(API_URL, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"RetroRecomp/{__version__}",
    })
    with _open_release_url(request, timeout=15) as response:
        payload = _read_release_bytes(response, 2 * 1024 * 1024 + 1)
    if len(payload) > 2 * 1024 * 1024:
        raise ValueError("GitHub release response is too large")
    releases = json.loads(payload)
    if not isinstance(releases, list):
        raise ValueError("Invalid GitHub release response")
    return select_update(releases)


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


def prepare_update(update: Update, executable: Path) -> tuple[Path, str]:
    """Download only after a click; stage on the install volume without touching games."""
    executable = executable.resolve()
    if _target_platform(executable) != update.target:
        raise ValueError('Downloaded update targets a different platform.')
    job_dir = Path(tempfile.mkdtemp(prefix=UPDATE_PREFIX, dir=executable.parent)).resolve()
    archive_path = job_dir / "download"
    try:
        request = urllib.request.Request(update.url, headers={"User-Agent": f"RetroRecomp/{__version__}"})
        digest = hashlib.sha256()
        size = 0
        with _open_release_url(request, timeout=60) as response, archive_path.open("wb") as output:
            while chunk := _read_release_bytes(response, 1024 * 1024):
                size += len(chunk)
                if size > MAX_ARCHIVE_BYTES:
                    raise ValueError("Release download is too large")
                output.write(chunk)
                digest.update(chunk)
        if size != update.size or digest.hexdigest() != update.digest:
            raise ValueError("Downloaded release checksum does not match GitHub")
        staged = job_dir / 'files' / executable.name
        staged.parent.mkdir(parents=True)
        archive_path.replace(staged)
        with staged.open("rb") as candidate:
            header = candidate.read(20)
            if update.target == 'windows-x86_64' and header[:2] != b"MZ":
                raise ValueError("Release does not contain a Windows executable")
            if update.target == 'linux-x86_64' and (len(header) < 20 or
                    header[:7] != b'\x7fELF\x02\x01\x01' or header[18:20] != b'\x3e\x00'
                    or int.from_bytes(header[16:18], 'little') not in (2, 3)):
                raise ValueError('Release does not contain a Linux x86-64 executable')
        if update.target == 'linux-x86_64':
            staged.chmod((executable.stat().st_mode & 0o777) | 0o100)
        files = {executable.name: update.digest}
        if getattr(sys, "frozen", False):
            environment = os.environ.copy()
            environment["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
            subprocess.run([str(staged), "_verify-update", update.version],
                           cwd=job_dir, env=environment, stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                           timeout=45, check=True)
        token = uuid.uuid4().hex
        job = {"token": token, "version": update.version, "target": str(executable),
               "parent_pid": os.getpid(), "files": files}
        (job_dir / "job.json").write_text(json.dumps(job), encoding="utf-8")
        shutil.copy2(executable, job_dir / ('updater-helper.exe' if update.target.startswith('windows') else 'updater-helper'))
        return job_dir, token
    except BaseException:
        _remove_job_dir(job_dir, executable)
        raise


def start_update_helper(job_dir: Path, token: str) -> None:
    job, target = _read_job(job_dir, token)
    helper = job_dir / ('updater-helper.exe' if _target_platform(target).startswith('windows') else 'updater-helper')
    environment = os.environ.copy()
    environment["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    subprocess.Popen([str(helper), "_apply-update", str(job_dir), token],
                     cwd=job_dir, env=environment, stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                     close_fds=True, start_new_session=os.name != 'nt')


def _read_job(job_dir: Path, token: str) -> tuple[dict, Path]:
    job = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
    target = Path(job["target"]).resolve()
    _target_platform(target)
    if (job.get("token") != token
            or _safe_job_dir(job_dir, target) != job_dir.resolve()):
        raise ValueError("Invalid update job")
    return job, target


def _wait_for_process(pid: int, timeout_ms: int = 120000) -> None:
    if os.name != "nt":
        if not isinstance(pid, int) or pid <= 0 or pid == os.getpid():
            raise ValueError('Invalid update process identity')
        try:
            descriptor = os.pidfd_open(pid)
        except ProcessLookupError:
            return
        try:
            if not select.select([descriptor], [], [], timeout_ms/1000)[0]:
                raise TimeoutError('The previous converter did not close')
        finally:
            os.close(descriptor)
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
    """Replace only the converter; reverse the change if installation fails."""
    staged = job_dir / "files"
    backup = job_dir / "backup"
    _target_platform(target)
    if set(files) != {target.name}:
        raise ValueError("Invalid update manifest")
    changed = []
    try:
        for relative, expected in files.items():
            source = staged / relative
            if hashlib.sha256(source.read_bytes()).hexdigest() != expected:
                raise ValueError("Staged update changed after verification")
        # The previous EXE remains recoverable until the restarted app cleans up.
        for relative in sorted(files):
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
                         close_fds=True, start_new_session=os.name != 'nt')
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


# --- Build tools ------------------------------------------------------------
# Converting a game compiles its generated C code on this computer (the ROM
# never leaves it), so conversion needs a C/C++ toolchain; playing does not.
# The converter installs the smallest set itself, with the user's consent:
# on Windows a portable Git and the portable compiler (llvm-mingw, CMake and
# Ninja, about 400 MB, no administrator rights; see toolchain.py), on
# Debian/Ubuntu the apt packages below. This lives beside the converter
# updater, which is interface code: it never changes a generated game.

MINGIT_URL = ('https://github.com/git-for-windows/git/releases/download/'
              'v2.56.0.windows.3/MinGit-2.56.0.3-64-bit.zip')
MINGIT_SHA256 = '2e5619966e588fde5f8122c5557cad50c0fbafcaed736689f40ec1dfb1d78ea7'
MINGIT_BYTES = 39854943
# Debian 13 / Ubuntu: what a conversion and the pinned SDL2 build use.
LINUX_PACKAGES = ('build-essential', 'cmake', 'ninja-build', 'pkg-config', 'git', 'curl',
                  'libx11-dev', 'libxext-dev', 'libxrandr-dev', 'libxcursor-dev', 'libxi-dev',
                  'libxinerama-dev', 'libxss-dev', 'libxfixes-dev', 'libxkbcommon-dev', 'libwayland-dev',
                  'libasound2-dev', 'libpulse-dev', 'libudev-dev', 'libgl-dev', 'libegl-dev', 'libgles-dev',
                  'libdrm-dev', 'libgbm-dev', 'libdbus-1-dev')


class ToolInstallError(Exception):
    """A build tool could not be installed; the message is for the user."""


def tools_directory() -> Path:
    from .toolchain import tools_directory as directory
    return directory()


def use_installed_tools() -> None:
    """Put the converter's own portable tools first on PATH (call at start)."""
    git = tools_directory() / 'mingit' / 'cmd'
    if os.name == 'nt' and (git / 'git.exe').is_file():
        entries = os.environ.get('PATH', '').split(os.pathsep)
        if str(git) not in entries:
            os.environ['PATH'] = os.pathsep.join([str(git), *entries])
    if os.name == 'nt':
        from .toolchain import ToolchainError, select
        try:
            select()   # puts llvm-mingw, CMake and Ninja on PATH when installed
        except ToolchainError:
            pass


def _windows_compiler() -> bool:
    try:
        from .core import ConversionError, toolchain
        toolchain()
        return True
    except (ConversionError, OSError, ValueError, KeyError, subprocess.SubprocessError):
        return False


def _linux_missing_packages() -> list[str]:
    if not shutil.which('dpkg-query'):
        return []
    try:
        result = subprocess.run(['dpkg-query', '-W', '-f', '${Package} ${db:Status-Status}\\n', *LINUX_PACKAGES],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return []
    installed = {line.split()[0] for line in result.stdout.splitlines()
                 if line.strip().endswith(' installed')}
    return [name for name in LINUX_PACKAGES if name not in installed]


def missing_build_tools() -> dict:
    """What a conversion still needs on this computer: {} when ready.

    Windows: {'git': bool, 'compiler': bool}; Linux: {'packages': [...]}
    (Debian/Ubuntu), or {'commands': [...]} on other distributions."""
    use_installed_tools()
    if os.name == 'nt':
        needs = {'git': not shutil.which('git'), 'compiler': not _windows_compiler()}
        return {key: True for key, value in needs.items() if value}
    commands = [name for name in ('cmake', 'ninja', 'cc', 'c++', 'git', 'pkg-config') if not shutil.which(name)]
    packages = _linux_missing_packages()
    if packages:
        return {'packages': packages}
    return {'commands': commands} if commands else {}


def _download(url: str, destination: Path, progress, *, limit: int, label: str) -> None:
    request = urllib.request.Request(url, headers={'User-Agent': f'RetroRecomp/{__version__}'})
    try:
        with urllib.request.urlopen(request, timeout=60) as response, destination.open('wb') as out:
            total = int(response.headers.get('Content-Length') or 0)
            done = 0
            while True:
                block = response.read(1 << 16)
                if not block:
                    break
                done += len(block)
                if done > limit:
                    raise ToolInstallError(f'{label}: unexpected download size.')
                out.write(block)
                progress(label, done, total)
    except urllib.error.URLError as error:
        raise ToolInstallError(f'{label}: download failed ({error.reason}).') from error
    except OSError as error:
        raise ToolInstallError(f'{label}: download failed ({error}).') from error


def install_git(progress) -> None:
    """Portable MinGit, pinned and hash-checked, in datas/tools/mingit."""
    import zipfile
    target = tools_directory() / 'mingit'
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent) as temp:
        archive = Path(temp) / 'mingit.zip'
        _download(MINGIT_URL, archive, progress, limit=MINGIT_BYTES + 1, label='Git')
        if hashlib.sha256(archive.read_bytes()).hexdigest() != MINGIT_SHA256:
            raise ToolInstallError('Git: the download does not match its expected checksum.')
        unpacked = Path(temp) / 'mingit'
        with zipfile.ZipFile(archive) as package:
            for member in package.infolist():
                if not (unpacked / member.filename).resolve().is_relative_to(unpacked.resolve()):
                    raise ToolInstallError('Git: unsafe archive member.')
            package.extractall(unpacked)
        if target.exists():
            shutil.rmtree(target)
        shutil.move(str(unpacked), str(target))
    use_installed_tools()


def _unpack(archive: Path, destination: Path, keep, label: str) -> None:
    """Extract only the members `keep(relative_name)` accepts, below the
    archive's single top folder (stripped when there is one)."""
    import zipfile
    root = destination.resolve()
    with zipfile.ZipFile(archive) as package:
        names = [member.filename for member in package.infolist()]
        first = names[0].split('/', 1)[0] + '/' if names and '/' in names[0] else ''
        top = first if first and all(name.startswith(first) for name in names) else ''
        for member in package.infolist():
            relative = member.filename[len(top):]
            if not relative or member.is_dir() or not keep(relative):
                continue
            target = (destination / relative).resolve()
            if not target.is_relative_to(root):
                raise ToolInstallError(f'{label}: unsafe archive member.')
            target.parent.mkdir(parents=True, exist_ok=True)
            with package.open(member) as source, target.open('wb') as out:
                shutil.copyfileobj(source, out, 1 << 20)


def _keep_llvm(name: str) -> bool:
    """x64 compiler, linker, resource compiler and libraries only: the
    32-bit, ARM, Python and debugger parts of llvm-mingw are not needed."""
    top = name.split('/', 1)[0]
    if top in ('i686-w64-mingw32', 'aarch64-w64-mingw32', 'armv7-w64-mingw32', 'python', 'busybox', 'share'):
        return False
    if name.startswith(('lib/libear/', 'lib/libscanbuild/')):
        return False
    if top == 'bin':
        leaf = name.rsplit('/', 1)[-1].lower()
        return not leaf.startswith(('lldb', 'liblldb', 'libpython', 'clangd', 'clang-tidy', 'clang-format',
                                    'git-clang', 'run-clang', 'scan-build', 'python')) \
            and not leaf.endswith(('.py', '.sh'))
    # Resource directory: Windows libraries and headers, not Linux sanitizers.
    return '/lib/linux/' not in '/' + name and '/lib/darwin/' not in '/' + name


def _keep_cmake(name: str) -> bool:
    if name.startswith(('doc/', 'man/', 'share/vim', 'share/emacs', 'share/bash-completion', 'share/aclocal')):
        return False
    if name.startswith('share/cmake-') and '/Help/' in name:
        return False
    return not (name.startswith('bin/') and name.rsplit('/', 1)[-1].lower() in ('cmake-gui.exe', 'cpack.exe', 'ctest.exe'))


def _verify_toolchain(root: Path) -> None:
    """Compile and run one program with the unpacked tools, so a bad archive
    or a pruned file fails here, not in the middle of someone's conversion."""
    clang = root / 'llvm-mingw' / 'bin' / 'clang.exe'
    environment = {**os.environ, 'PATH': os.pathsep.join(
        [str(root / 'llvm-mingw' / 'bin'), str(root / 'cmake' / 'bin'), str(root / 'ninja'), os.environ.get('PATH', '')])}
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    with tempfile.TemporaryDirectory() as temp:
        source = Path(temp) / 'check.c'
        source.write_text('#include <stdio.h>\n#include <windows.h>\nint main(void){puts("ok");return 0;}\n', encoding='ascii')
        program = Path(temp) / 'check.exe'
        commands = [[str(clang), '-O2', '-static', str(source), '-o', str(program)], [str(program)],
                    [str(root / 'llvm-mingw' / 'bin' / 'llvm-windres.exe'), '--version'],
                    [str(root / 'cmake' / 'bin' / 'cmake.exe'), '--version'], [str(root / 'ninja' / 'ninja.exe'), '--version']]
        for command in commands:
            try:
                result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                        timeout=120, env=environment, creationflags=flags)
            except (OSError, subprocess.SubprocessError) as error:
                raise ToolInstallError(f'Build tools: {Path(command[0]).name} does not run ({error}).') from error
            if result.returncode:
                raise ToolInstallError(f'Build tools: {Path(command[0]).name} failed: {result.stdout.strip()[-300:]}')


def install_toolchain(progress) -> None:
    """Portable llvm-mingw, CMake and Ninja, pinned and hash-checked, in
    datas/tools. No administrator rights; nothing outside that folder."""
    from . import toolchain as pins
    tools = tools_directory()
    tools.mkdir(parents=True, exist_ok=True)
    packages = (('CMake', 'cmake', pins.CMAKE_URL, pins.CMAKE_SHA256, pins.CMAKE_BYTES, pins.CMAKE_VERSION, _keep_cmake),
                ('Ninja', 'ninja', pins.NINJA_URL, pins.NINJA_SHA256, pins.NINJA_BYTES, pins.NINJA_VERSION, lambda name: True),
                ('LLVM-MinGW', 'llvm-mingw', pins.LLVM_MINGW_URL, pins.LLVM_MINGW_SHA256, pins.LLVM_MINGW_BYTES,
                 pins.LLVM_MINGW_VERSION, _keep_llvm))
    with tempfile.TemporaryDirectory(dir=tools) as temp:
        staged = Path(temp) / 'staged'
        for label, folder, url, sha256, size, version, keep in packages:
            archive = Path(temp) / (folder + '.zip')
            _download(url, archive, progress, limit=size + 1, label=label)
            digest = hashlib.sha256()
            with archive.open('rb') as stream:
                for block in iter(lambda: stream.read(1 << 20), b''):
                    digest.update(block)
            if digest.hexdigest() != sha256:
                raise ToolInstallError(f'{label}: the download does not match its expected checksum.')
            _unpack(archive, staged / folder, keep, label)
            archive.unlink()
            (staged / folder / pins.STAMP).write_text(json.dumps({'version': version, 'sha256': sha256}), encoding='utf-8')
        _verify_toolchain(staged)
        # The tools move to their final folder only once everything is checked.
        for folder in ('llvm-mingw', 'cmake', 'ninja'):
            target = tools / folder
            if target.exists():
                shutil.rmtree(target)
            shutil.move(str(staged / folder), str(target))
    use_installed_tools()


def linux_install_command(packages) -> list[str]:
    return ['apt-get', 'install', '-y', '--no-install-recommends', *packages]


def install_linux_packages(packages, progress) -> None:
    """apt through pkexec (the desktop asks for the password); progress comes
    from apt's status lines."""
    if not shutil.which('pkexec'):
        raise ToolInstallError('pkexec is missing: run in a terminal: sudo '
                               + ' '.join(linux_install_command(packages)))
    command = ['pkexec', *linux_install_command(packages)[:1], '-o', 'APT::Status-Fd=1',
               *linux_install_command(packages)[1:]]
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                   env={**os.environ, 'DEBIAN_FRONTEND': 'noninteractive'})
    except OSError as error:
        raise ToolInstallError(str(error)) from error
    for line in process.stdout:
        parts = line.strip().split(':', 3)
        if len(parts) >= 3 and parts[0] in ('dlstatus', 'pmstatus'):
            try:
                percent = float(parts[2])
            except ValueError:
                continue
            label = 'Download' if parts[0] == 'dlstatus' else 'Install'
            progress(label, int(percent * 10), 1000)
    if process.wait() != 0:
        raise ToolInstallError('The packages could not be installed (apt-get stopped or the password was refused).')
