"""Build and stage the separate X68000 research reference (stages 1 and 2).

This developer tool does not add an advertised converter profile. The PX68k
module is a distinct reference, without the existing PolyForm AOT backend.
Private game/firmware inputs are supplied explicitly and never downloaded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from os import environ as _environ
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp.platforms import sdl_install
from retrorecomp.x68000_media import MachineConfig, build_manifest

PX68K_URL = 'https://github.com/libretro/px68k-libretro.git'
PX68K_REV = '0ad84d7058a12b7db4f7f7a906e87fad4e2f26f6'
# Machine sources of the default runtime (tools/x68000_base74.py).
HISSORII_REV = '74ddbb37b4e12b77362a4e12f28ceb5aaa593684'
PX68K_MAX_DISKS = 10  # Pinned libretro.c MAX_DISKS; its M3U reader has a fixed array.


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def command(args, *, cwd=ROOT):
    return subprocess.run([str(a) for a in args], cwd=cwd, check=True)


def ensure_sources(source: Path) -> Path:
    source = source.resolve()
    if not source.exists():
        source.parent.mkdir(parents=True, exist_ok=True)
        command(['git', 'clone', '--no-checkout', '--filter=blob:none', PX68K_URL, source])
        command(['git', 'checkout', '--detach', PX68K_REV], cwd=source)
    actual = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source,
                                     text=True).strip()
    if actual != PX68K_REV:
        raise ValueError(f'PX68k revision differs: expected {PX68K_REV}, got {actual}')
    dirty = subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'],
                                    cwd=source, text=True).strip()
    if dirty:
        raise ValueError('PX68k reference sources contain local modifications; use a clean pinned checkout.')
    return source


def build_reference(build: Path, source: Path, sdl: Path, jobs: int = 4) -> Path:
    from retrorecomp.core import toolchain
    from retrorecomp.platforms import cmake_target_args
    source = ensure_sources(source)
    cmake, generator = toolchain()
    build = build.resolve()
    command([cmake, '-S', ROOT / 'native/x68000_reference', '-B', build,
             '-G', generator, *cmake_target_args(), f'-DPX68K_DIR={source.as_posix()}',
             f'-DCMAKE_PREFIX_PATH={sdl.resolve().as_posix()}'])
    command([cmake, '--build', build, '--config', 'Release', '--parallel', str(jobs)])
    from retrorecomp.platforms import build_executable
    executable = build_executable(build, 'RetroRecomp-X68000-Reference')
    if not executable.is_file():
        raise ValueError(f'Reference build did not produce {executable}')
    return executable


def _checked_copy(source: Path, destination: Path, expected: str, *, preserve=False):
    _safe_destination(destination)
    if destination.exists():
        if not destination.is_file():
            raise ValueError(f'Staged input is not a regular file: {destination}')
        if preserve:
            return
        if digest(destination) != expected:
            raise ValueError(f'Existing staged input differs: {destination}')
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix='.' + destination.name + '.', dir=destination.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, 'wb') as dst, source.open('rb') as src:
            shutil.copyfileobj(src, dst, length=65536)
        if digest(temporary) != expected:
            raise ValueError(f'Source changed while copying: {source}')
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def _no_links(path: Path):
    # Check before resolve(): resolution would hide a linked parent, including
    # a dangling link or a Windows directory junction.
    for part in (path, *path.parents):
        if part.is_symlink() or (hasattr(part, 'is_junction') and part.is_junction()):
            raise ValueError(f'Refusing linked reference destination: {part}')


def _safe_destination(path: Path):
    _no_links(path)
    if path.exists() and path.is_file() and path.stat().st_nlink > 1:
        raise ValueError(f'Refusing hard-linked reference destination: {path}')


def _atomic_bytes(path: Path, content: bytes, *, executable=False):
    _safe_destination(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(content)
        if executable:
            temporary.chmod(0o755)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_text(path: Path, content: str, *, executable=False):
    _atomic_bytes(path, content.encode('utf-8'), executable=executable)


def prepare_bundle(output: Path, disks: list[Path], ipl: Path, cgrom: Path,
                   executable: Path, *, title='Cho Ren Sha 68k', ram_mib=2,
                   initial_drives=None) -> Path:
    if len(disks) > PX68K_MAX_DISKS:
        raise ValueError(f'The pinned PX68k reference accepts at most {PX68K_MAX_DISKS} disks.')
    if ram_mib not in (2, 4):
        raise ValueError('This reference currently supports explicit 2 or 4 MiB configurations.')
    if (not isinstance(title, str) or not title.strip() or len(title) > 160
            or any(ord(c) < 32 or c in '/\\' for c in title)):
        raise ValueError('Reference title must be a short single-line name without path separators.')
    if initial_drives is None:
        initial_drives = (0, 1 if len(disks) > 1 else None)
    initial_drives = tuple(initial_drives)
    if initial_drives != (0, 1 if len(disks) > 1 else None):
        raise ValueError('Reference M3U currently requires first disk in FDD0 and second in FDD1.')
    manifest = build_manifest(disks, ipl, cgrom,
                              config=MachineConfig(ram_bytes=ram_mib * 1024 * 1024),
                              initial_drives=initial_drives)
    if any('\n' in str(p) or '\r' in str(p) for p in (output, executable, *disks, ipl, cgrom)):
        raise ValueError('Media paths cannot contain line breaks.')
    output = output.absolute()
    _no_links(output)
    output = output.resolve()
    # All originals live outside the working tree being created. A mistaken
    # output directory can never replace an original disk, even when writable.
    source_paths = [disk.path for disk in manifest.media] + [manifest.firmware.ipl.path,
                                                           manifest.firmware.cgrom.path]
    if any(path.resolve().is_relative_to(output) for path in source_paths):
        raise ValueError('Sources must be outside the reference output folder.')
    binary_dir = executable.resolve().parent
    module = binary_dir / ('rr_px68k_reference.dll' if os.name == 'nt' else 'rr_px68k_reference.so')
    if not executable.is_file() or not module.is_file():
        raise ValueError('Both the separate reference executable and core module are required.')
    receipt = output / 'datas/source-manifest.json'
    for relative in ('datas', 'datas/media', 'datas/original-media',
                     'datas/system/keropi', 'datas/saves', 'datas/reference-build.json',
                     'datas/media/game.m3u', 'datas/reference.cfg', 'reference-notices',
                     'README-REFERENCE.txt', executable.name, module.name,
                     f'{title}.desktop', 'datas/source-manifest.json'):
        _safe_destination(output / relative)
    if receipt.exists():
        old = json.loads(receipt.read_text(encoding='utf-8'))
        if old.get('sha256') != manifest.sha256:
            raise ValueError('This folder belongs to another exact media set/configuration.')
    elif (output / 'datas').exists() and any((output / 'datas').iterdir()):
        raise ValueError('Existing data folder has no source manifest; use a fresh prototype folder.')
    media_dir = output / 'datas/media'
    original_dir = output / 'datas/original-media'
    system_dir = output / 'datas/system/keropi'
    save_dir = output / 'datas/saves'
    for directory in (media_dir, original_dir, system_dir, save_dir):
        _no_links(directory)
        directory.mkdir(parents=True, exist_ok=True)
    staged = []
    for index, disk in enumerate(manifest.media):
        name = f'disk-{index + 1:02}.{disk.format}'
        _checked_copy(disk.path, original_dir / name, disk.sha256)
        # Keep guest writes in private copies between prototype launches.
        _checked_copy(disk.path, media_dir / name, disk.sha256, preserve=True)
        staged.append(name)
    for image, name in ((manifest.firmware.ipl, 'iplrom.dat'),
                        (manifest.firmware.cgrom, 'cgrom.dat')):
        _checked_copy(image.path, system_dir / name, image.sha256)
    # PX68k M3U inserts its first two entries into the two physical drives.
    # General ordered media remain in the manifest for later swap handling.
    _atomic_text(media_dir / 'game.m3u', '\n'.join(staged) + '\n')
    _atomic_text(output / 'datas/reference.cfg', f'ram_mib={ram_mib}\n')
    manifest.verify_sources()
    _atomic_text(receipt, json.dumps(manifest.local_record(), indent=2) + '\n')
    _atomic_text(output / 'datas/source-identity.txt', manifest.sha256 + '\n')
    target = output / executable.name
    for src in (executable, module):
        dst = output / src.name
        if dst.resolve() != src.resolve():
            _atomic_bytes(dst, src.read_bytes(), executable=os.name != 'nt')
    metadata = {'schema': 1, 'stage': 'x68000-reference-boot', 'title': title,
                'native_cpu': False, 'reference_core': _machine_revision(),
                'source_identity': manifest.sha256, 'ram_mib': ram_mib,
                'disk_count': len(manifest.media), 'initial_drives': list(initial_drives),
                'source_bytes_shared': False,
                'executable_sha256': digest(target), 'module_sha256': digest(output / module.name)}
    _atomic_text(output / 'datas/reference-build.json', json.dumps(metadata, indent=2) + '\n')
    license_dir = output / 'reference-notices'
    license_dir.mkdir(exist_ok=True)
    audit = ROOT / 'docs/X68000_REFERENCE_LICENSES.md'
    if audit.exists():
        _atomic_bytes(license_dir / audit.name, audit.read_bytes())
    if _machine_revision() == HISSORII_REV:
        # hissorii/px68k originals, unchanged, and our notice pages.
        source = ROOT / '.deps/px68k-hissorii-74ddbb3'
        notices = ('doc/kero_src.txt', 'fmgen/readme.txt')
        for page in ('x68000-machine.md', 'fmgen.md', 'musashi.md', 'segagenesisrecomp.md'):
            _atomic_bytes(license_dir / page, (Path(__file__).resolve().parents[1] / 'licenses' / page).read_bytes())
    else:
        source = ROOT / '.deps/px68k-reference'
        notices = ('COPYING', 'doc/kero_src.txt', 'fmgen/readme.txt',
                   'm68000/musashi/softfloat/README.txt')
    for relative in notices:
        original = source / relative
        if original.is_file():
            destination = license_dir / relative
            _atomic_bytes(destination, original.read_bytes())
    _atomic_text(output / 'README-REFERENCE.txt',
        f'{title} — X68000 development reference\n'
        'MC68000 10 MHz, interpreted CPU (not yet an AOT export).\n'
        'Private supplied disks and firmware; no public distribution.\n'
        'Arrows: direction; Z/X: buttons; Enter/Space: game keyboard.\n'
        'Ctrl+Alt+Enter: fullscreen; Ctrl+Alt+Q: close.\n'
        f'Default settings: {ram_mib} MiB RAM, native video cadence, no frameskip.\n'
        'Guest disk writes and SRAM remain under datas. Originals are preserved.\n'
        'CPU/hardware fidelity, full gameplay and physical latency are not qualified.\n')
    if os.name != 'nt':
        desktop = output / f'{title}.desktop'
        # Use the existing tested quoting for a path with spaces; no shell.
        from retrorecomp.linux_desktop import _argument, _value
        _atomic_text(desktop, '[Desktop Entry]\nType=Application\n'
                     f'Name={_value(title)} — X68000 reference\n'
                     f'Exec={_argument(target)}\n'
                     f'Path={_value(output)}\nTerminal=false\nCategories=Game;\n',
                     executable=True)
    return target


def _machine_revision() -> str:
    """Revision of the machine sources the converter builds (see x68000_native)."""
    base = _environ.get('RR_X68000_MACHINE_BASE', 'hissorii')
    return HISSORII_REV if base == 'hissorii' else PX68K_REV


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    build = sub.add_parser('build')
    build.add_argument('--source', type=Path, default=ROOT / '.deps/px68k-reference')
    build.add_argument('--build-dir', type=Path, default=ROOT / '.build/x68000-stage1/build')
    build.add_argument('--sdl-prefix', type=Path, default=sdl_install())
    build.add_argument('--jobs', type=int, choices=range(1, 9), default=4)
    stage = sub.add_parser('prepare')
    stage.add_argument('--disk', type=Path, action='append', required=True)
    stage.add_argument('--ipl', type=Path, required=True)
    stage.add_argument('--cgrom', type=Path, required=True)
    stage.add_argument('--executable', type=Path, required=True)
    stage.add_argument('--output', type=Path, required=True)
    stage.add_argument('--title', default='Cho Ren Sha 68k')
    stage.add_argument('--ram-mib', type=int, choices=(2, 4), default=2)
    args = parser.parse_args()
    if args.action == 'build':
        result = build_reference(args.build_dir, args.source, args.sdl_prefix, args.jobs)
    else:
        result = prepare_bundle(args.output, args.disk, args.ipl, args.cgrom,
                                args.executable, title=args.title, ram_mib=args.ram_mib)
    print(result, flush=True)


if __name__ == '__main__':
    main()
