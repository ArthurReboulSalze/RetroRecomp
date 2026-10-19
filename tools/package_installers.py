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
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def payload_files(executable: Path, version: str, target: str) -> dict[str, bytes]:
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('Expected a three-part release version')
    raw = executable.read_bytes()
    if target == 'windows' and raw[:2] != b'MZ':
        raise ValueError('Expected a Windows converter')
    if target == 'linux' and (raw[:7] != b'\x7fELF\x02\x01\x01' or raw[18:20] != b'\x3e\x00'):
        raise ValueError('Expected a Linux x86-64 converter')
    # Verify the actual version; do not relabel a converter with an installer flag.
    subprocess.run([str(executable.resolve()), '_verify-update', version], check=True, timeout=45)
    common = {
        'LICENSE.txt': (ROOT / 'LICENSE').read_bytes(),
        'THIRD_PARTY_NOTICES.md': (ROOT / 'THIRD_PARTY_NOTICES.md').read_bytes(),
        'INSTALL.txt': (f'Retro-Recomp {version}\n\n'
            'Open Retro-Recomp from your applications menu.\n'
            'Use Check for updates inside the app to install newer versions.\n'
            'Updates replace only the converter; your games and private data are kept.\n\n'
            'Your settings, collection, covers and learning data are in datas beside\n'
            'the converter. Generated games default to Games in the same folder.\n'
            'Uninstall keeps these folders and your compiler caches.\n'
            'Close the app and any conversions before installing or uninstalling.\n\n'
            + ('Uninstall through Windows Settings or the Start menu entry.\n' if target == 'windows' else
               'Uninstall by running uninstall.sh in this installation folder, without sudo.\n')
            + '\nSupply your own ROMs and BIOS. Conversion requires native build tools;\n'
            'playing generated games requires no development tools.\n\n'
            'Installation, migration and build-tool guide:\n'
            'https://github.com/ArthurReboulSalze/RetroRecomp/blob/main/docs/INSTALLING.md\n').encode('utf-8'),
    }
    if target == 'windows':
        return common | {'Retro-Recomp.exe': raw, 'Retro-Recomp.ico': (ROOT / 'assets/Retro-Recomp.ico').read_bytes()}
    return common | {'Retro-Recomp': raw,
                     'Retro-Recomp.png': (ROOT / 'assets/Retro-Recomp-icon-256.png').read_bytes(),
                     'uninstall.sh': (ROOT / 'tools/installers/linux_uninstall.sh').read_bytes().replace(b'\r\n', b'\n')}


def linux_archive(files: dict[str, bytes]) -> bytes:
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode='w', format=tarfile.USTAR_FORMAT) as tar:
        for name, raw in sorted(files.items()):
            info = tarfile.TarInfo(name)
            info.size = len(raw)
            info.mode = 0o755 if name in ('Retro-Recomp', 'uninstall.sh') else 0o644
            info.mtime = 0
            tar.addfile(info, io.BytesIO(raw))
    return gzip.compress(archive.getvalue(), compresslevel=6, mtime=0)


def build(executable: Path, version: str, target: str, output: Path, *,
          iscc: Path | None = None, application_id: str | None = None) -> Path:
    files = payload_files(executable, version, target)
    output.mkdir(parents=True, exist_ok=True)
    if target == 'linux':
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
    parser.add_argument('--target', choices=('windows', 'linux'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--iscc', type=Path)
    parser.add_argument('--application-id', help='Use a separate registration identity for isolated installer tests')
    args = parser.parse_args()
    print(build(args.executable, args.version, args.target, args.output,
                iscc=args.iscc, application_id=args.application_id))


if __name__ == '__main__':
    main()
