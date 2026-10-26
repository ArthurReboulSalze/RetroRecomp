"""Wrap audited, already built converters in per-user installers.

No ROM, cache or local data directory is collected. The embedded executable is
copied byte for byte, retaining the existing platform-specific in-app updater.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def release_notes_text(version: str, notes: Path | None) -> bytes:
    """What the Windows installer shows before installing: the release notes
    as plain text (English, as published), or a pointer to them."""
    from retrorecomp.updater import release_notes
    text = release_notes(notes.read_text(encoding='utf-8')) if notes else ''
    if not text:
        text = (f'Retro-Recomp {version}\n\nRelease notes:\n'
                f'https://github.com/ArthurReboulSalze/RetroRecomp/releases/tag/v{version}')
    return (text.replace('\r\n', '\n').replace('\n', '\r\n') + '\r\n').encode('utf-8')


BASE_NAME = 'Retro-Recomp-base.zip'   # the base of paths beside the converter (updater.BASE_ASSET)


def payload_files(executable: Path, version: str, target: str, notes: Path | None = None,
                  base: Path | None = None) -> dict[str, bytes]:
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('Expected a three-part release version')
    raw = executable.read_bytes()
    if target == 'windows' and raw[:2] != b'MZ':
        raise ValueError('Expected a Windows converter')
    if target == 'linux' and (raw[:7] != b'\x7fELF\x02\x01\x01' or raw[18:20] != b'\x3e\x00'):
        raise ValueError('Expected a Linux x86-64 converter')
    # Verify the actual version; do not relabel a converter with an installer flag.
    subprocess.run([str(executable.resolve()), '_verify-update', version], check=True, timeout=45)
    extra = {}
    if base is not None:
        # The full base of paths of this release, laid read only beside the converter.
        data = base.read_bytes()
        if data[:4] != b'PK\x03\x04' or not zipfile.is_zipfile(base):
            raise ValueError('Expected the base archive (Retro-Recomp-base.zip)')
        extra[BASE_NAME] = data
    common = {
        'LICENSE.txt': (ROOT / 'LICENSE').read_bytes(),
        'THIRD_PARTY_NOTICES.md': (ROOT / 'THIRD_PARTY_NOTICES.md').read_bytes(),
        'INSTALL.txt': (f'Retro-Recomp {version}\n\n'
            'Open Retro-Recomp from your applications menu.\n'
            'Use Check for updates inside the app to install newer versions.\n'
            'Updates replace only the converter and its base of paths (Retro-Recomp-base.zip);\n'
            'your games and private data are kept.\n\n'
            'Your settings, collection, covers and learning data are in datas beside\n'
            'the converter. Generated games default to Games in the same folder.\n'
            'Uninstall keeps these folders, and asks whether to also remove the build\n'
            'tools and compiler caches installed beside the converter.\n'
            'Close the app and any conversions before installing or uninstalling.\n\n'
            + ('Uninstall through Windows Settings or the Start menu entry.\n' if target == 'windows' else
               'Uninstall by running uninstall.sh in this installation folder, without sudo.\n')
            + '\nSupply your own ROMs and BIOS. Conversion requires native build tools;\n'
            'playing generated games requires no development tools.\n\n'
            'Installation, migration and build-tool guide:\n'
            'https://github.com/ArthurReboulSalze/RetroRecomp/blob/main/docs/INSTALLING.md\n').encode('utf-8'),
    }
    common |= extra
    if target == 'windows':
        return common | {'Retro-Recomp.exe': raw, 'Retro-Recomp.ico': (ROOT / 'assets/Retro-Recomp.ico').read_bytes(),
                         'RELEASE_NOTES.txt': release_notes_text(version, notes)}
    return common | {'Retro-Recomp': raw,
                     'Retro-Recomp.png': (ROOT / 'assets/Retro-Recomp-icon-256.png').read_bytes(),
                     'uninstall.sh': (ROOT / 'tools/installers/linux_uninstall.sh').read_bytes().replace(b'\r\n', b'\n')}


def linux_archive(files: dict[str, bytes]) -> bytes:
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode='w', format=tarfile.USTAR_FORMAT) as tar:
        for name, raw in sorted(files.items()):
            info = tarfile.TarInfo(name)
            info.size = len(raw)
            info.mode = 0o755 if name in ('Retro-Recomp', 'uninstall.sh') else 0o444 if name == BASE_NAME else 0o644
            info.mtime = 0
            tar.addfile(info, io.BytesIO(raw))
    return gzip.compress(archive.getvalue(), compresslevel=6, mtime=0)


APP_ID = 'io.github.ArthurReboulSalze.RetroRecomp'
DEB_MAINTAINER = 'Arthur Reboul Salze <22814805+ArthurReboulSalze@users.noreply.github.com>'


def deb_tree(files: dict[str, bytes], version: str, root: Path) -> None:
    """The Debian package's files under `root`: the application in
    /opt/retro-recomp, a launcher in /usr/bin that runs each user's private
    copy (settings and games stay beside it, updates keep working), a menu
    entry and an icon. Removing the package keeps every user's data."""
    def put(relative: str, data: bytes, mode: int = 0o644) -> None:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        path.chmod(mode)
    for name in ('Retro-Recomp', 'Retro-Recomp.png', 'LICENSE.txt', 'THIRD_PARTY_NOTICES.md', 'INSTALL.txt'):
        put(f'opt/retro-recomp/{name}', files[name], 0o755 if name == 'Retro-Recomp' else 0o644)
    if BASE_NAME in files:
        put(f'opt/retro-recomp/{BASE_NAME}', files[BASE_NAME], 0o444)
    put('opt/retro-recomp/VERSION', (version + '\n').encode('ascii'))
    launcher = (ROOT / 'tools/installers/deb_launcher.sh').read_bytes().replace(b'\r\n', b'\n')
    put('usr/bin/retro-recomp', launcher, 0o755)
    put(f'usr/share/applications/{APP_ID}.desktop', '\n'.join((
        '[Desktop Entry]', 'Type=Application', 'Version=1.0', 'Name=Retro-Recomp',
        'Comment=Convert your retro games into native executables', 'Exec=retro-recomp',
        f'Icon={APP_ID}', 'Terminal=false', 'Categories=Game;Utility;', 'StartupNotify=true',
        'StartupWMClass=Retro-Recomp', '')).encode('utf-8'))
    put(f'usr/share/icons/hicolor/256x256/apps/{APP_ID}.png', files['Retro-Recomp.png'])
    put('usr/share/doc/retro-recomp/copyright', files['LICENSE.txt'] + b'\n' + files['THIRD_PARTY_NOTICES.md'])
    size = sum(path.stat().st_size for path in root.rglob('*') if path.is_file())
    put('DEBIAN/control', '\n'.join((
        'Package: retro-recomp', f'Version: {version}', 'Architecture: amd64', 'Section: games',
        'Priority: optional', f'Maintainer: {DEB_MAINTAINER}', 'Depends: libc6 (>= 2.41)',
        f'Installed-Size: {(size + 1023) // 1024}', 'Homepage: https://retro-recomp.com',
        'Description: retro game recompiler into native executables',
        ' Retro-Recomp converts your own Master System, Game Gear, Game Boy, NES,',
        ' Mega Drive, Super Nintendo, Neo Geo, CPS-1 and X68000 games into native',
        ' Linux executables. Each user gets a private copy in ~/.local/opt that keeps',
        ' its settings and games and updates itself; removing the package keeps them.', '')).encode('utf-8'))
    for path in [root, *root.rglob('*')]:
        if path.is_dir():
            path.chmod(0o755)   # never group-writable, whatever the build host's umask
        os.utime(path, (0, 0))


def build(executable: Path, version: str, target: str, output: Path, *,
          iscc: Path | None = None, application_id: str | None = None, notes: Path | None = None,
          base: Path | None = None) -> Path:
    files = payload_files(executable, version, 'linux' if target == 'deb' else target, notes, base)
    output.mkdir(parents=True, exist_ok=True)
    if target == 'deb':
        with tempfile.TemporaryDirectory(prefix='RetroRecomp-deb-') as temp:
            root = Path(temp) / 'retro-recomp'
            deb_tree(files, version, root)
            destination = output / f'retro-recomp_{version}_amd64.deb'
            subprocess.run(['dpkg-deb', '--root-owner-group', '-Zxz', '--build', str(root), str(destination)],
                           check=True, env={**os.environ, 'SOURCE_DATE_EPOCH': '0'})
    elif target == 'linux':
        archive = linux_archive(files)
        header = (ROOT / 'tools/installers/linux_install.sh').read_text(encoding='utf-8')
        header = header.replace('@VERSION@', version).replace('@PAYLOAD_SHA256@', hashlib.sha256(archive).hexdigest())
        destination = output / f'Retro-Recomp-{version}-linux-x86_64-install.run'
        destination.write_bytes(header.encode('utf-8') + archive)
        destination.chmod(0o755)
    else:
        if iscc is None:
            raise ValueError('Pass --iscc pointing to the Inno Setup 6.7.3 compiler')
        with tempfile.TemporaryDirectory(prefix='RetroRecomp-setup-') as temp:
            payload = Path(temp)
            if BASE_NAME not in files:
                raise ValueError('Pass --base: the Windows installer lays the base beside the converter')
            for name, raw in files.items():
                (payload / name).write_bytes(raw)
            command = [str(iscc.resolve()), '/Qp', f'/DAppVersion={version}',
                       f'/DPayloadDir={payload}', f'/DOutputDir={output.resolve()}']
            if application_id:
                if not re.fullmatch(r'[A-Za-z0-9{}-]+', application_id):
                    raise ValueError('Invalid application ID')
                command.append('/DApplicationId=' + application_id)
            subprocess.run(command + [str(ROOT / 'tools/installers/windows.iss')], check=True)
        destination = output / f'Retro-Recomp-{version}-windows-x64-setup.exe'
    receipt = dict(version=version, target=target, converter_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),
                   installer_sha256=hashlib.sha256(destination.read_bytes()).hexdigest(), bytes=destination.stat().st_size,
                   payload={name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()})
    destination.with_suffix(destination.suffix + '.audit.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', type=Path, required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--target', choices=('windows', 'linux', 'deb'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--iscc', type=Path)
    parser.add_argument('--application-id', help='Use a separate registration identity for isolated installer tests')
    parser.add_argument('--notes', type=Path, help='Markdown release notes shown by the Windows installer')
    parser.add_argument('--base', type=Path, required=True,
                        help='The full base of paths of this release, laid beside the converter as ' + BASE_NAME)
    args = parser.parse_args()
    print(build(args.executable, args.version, args.target, args.output,
                iscc=args.iscc, application_id=args.application_id, notes=args.notes, base=args.base))


if __name__ == '__main__':
    main()
