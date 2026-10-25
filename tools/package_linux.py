"""Build and audit a native Linux converter; never bundle local ROMs or settings.

Run with the project's Linux venv and PyInstaller 6.22.3 installed. Outputs an
independently runnable ELF and a tar.gz with that executable and usage notes.
"""
import argparse
import importlib.metadata
import json
import os
import platform
from pathlib import Path
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.prepare_publication import BUNDLED_FILES, PACKER, audit_sources, audit_executable, write_module_hook
from retrorecomp import __version__


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'Export')
    args = parser.parse_args()
    if platform.system() != 'Linux' or platform.machine() != 'x86_64':
        parser.error('This first package is qualified on native Linux x86-64 only.')
    for name, version in [('PyInstaller','6.22.3'), ('tkinterdnd2','0.6.4'), ('SecretStorage','3.5.0')]:
        if importlib.metadata.version(name) != version:
            parser.error(f'Install {name}=={version} in the build venv.')
    audit_sources(ROOT)
    from tools.build_credits_audio import build as build_credits_audio
    credits_audio = build_credits_audio()
    from tools.build_player_gamepad import build as build_gamepad
    gamepad = build_gamepad()
    stage = ROOT/'.build/linux-package'
    hooks = stage/'hooks'
    hooks.mkdir(parents=True, exist_ok=True)
    # Include only the native Tk extension for this build, not the wheel's
    # Windows/macOS/ARM or Tcl 9 variants. No foreign executable code is loaded.
    (hooks/'hook-tkinterdnd2.py').write_text('''from pathlib import Path
import tkinter, tkinterdnd2
p = Path(tkinterdnd2.__file__).parent
variant = "linux-x64" + ("-tcl9" if tkinter.TclVersion >= 9 else "")
dest = "tkinterdnd2/tkdnd/" + variant
datas = [(str(f), dest) for f in (p/"tkdnd"/variant).glob("*.tcl")]
binaries = [(str(f), dest) for f in (p/"tkdnd"/variant).glob("*.so")]
''', encoding='utf-8')
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onefile',
        '--name', 'Retro-Recomp', '--exclude-module', 'numpy', '--exclude-module', 'pytest',
        '--splash', str(ROOT/'assets/Retro-Recomp-splash.png'),
        '--distpath', str(stage/'dist'), '--workpath', str(stage/'work'),
        '--specpath', str(stage), '--additional-hooks-dir', str(hooks),
        '--add-binary', str(credits_audio)+':credits-runtime',
        '--add-binary', str(gamepad)+':player-runtime']
    # PyInstaller restores a data file's execute bit only when the source has
    # it. The bundled UPX packs games (retrorecomp/packing.py) and must run.
    packer = ROOT/PACKER
    packer.chmod(packer.stat().st_mode | 0o755)
    for name in sorted(BUNDLED_FILES):
        command += ['--add-data', str(ROOT/name)+':'+str(Path(name).parent)]
    # Public modules no application path imports yet must still be frozen
    # (hook-retrorecomp.py in the same hooks folder).
    write_module_hook(hooks)
    # Preserve the actual dependency notices, including cryptography's bundled
    # OpenSSL notices, in the binary alongside our hand-maintained attributions.
    notices = {}
    for name in ('tkinterdnd2','SecretStorage','jeepney','cryptography','cffi','pycparser'):
        dist = importlib.metadata.distribution(name)
        count = 0
        for entry in dist.files or ():
            if '.dist-info/' not in str(entry) or not any(word in entry.name.lower() for word in ('license','copying','notice','authors')):
                continue
            path = Path(dist.locate_file(entry))
            destination = 'third-party-runtime/'+name
            command += ['--add-data', str(path)+':'+destination]
            notices[destination+'/'+path.name] = path.read_bytes()
            count += 1
        if not count:
            raise RuntimeError('Missing dependency license: '+name)
    command.append(str(ROOT/'RetroRecomp.py'))
    subprocess.run(command, cwd=ROOT, check=True)
    built = stage/'dist/Retro-Recomp'
    proof = audit_executable(built, ROOT)
    from PyInstaller.archive.readers import CArchiveReader
    archive = CArchiveReader(str(built))
    for name, contents in notices.items():
        if archive.extract(name) != contents:
            raise RuntimeError('Missing runtime notice: '+name)
    if archive.toc.get(PACKER, ('',))[-1] != 'b':
        raise RuntimeError('The bundled UPX would not be executable once unpacked.')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    # Atomic replacement preserves games, cover caches and private settings.
    destination = output/'Retro-Recomp'
    temporary = output/'.Retro-Recomp.pending'
    temporary.write_bytes(built.read_bytes())
    temporary.chmod(0o755)
    temporary.replace(destination)
    archive_path = output/f'Retro-Recomp-{__version__}-linux-x86_64.tar.gz'
    with tarfile.open(archive_path, 'w:gz') as package:
        package.add(destination, arcname='Retro-Recomp/Retro-Recomp', recursive=False)
        package.add(ROOT/'docs/LINUX.md', arcname='Retro-Recomp/README.md', recursive=False)
        package.add(ROOT/'docs/BUILDING.md', arcname='Retro-Recomp/BUILDING.md', recursive=False)
    proof.update(bytes=destination.stat().st_size, target='linux-x86_64',
                 build_glibc=platform.libc_ver(), archive=archive_path.name)
    (stage/'audit.json').write_text(json.dumps(proof, indent=2)+'\n', encoding='utf-8')
    subprocess.run([str(destination), '_install-launcher'], check=True,
                   env={**os.environ, 'PYINSTALLER_SUPPRESS_SPLASH_SCREEN': '1'})
    print(json.dumps({'executable':str(destination), 'sha256':proof['sha256'],
                      'bytes':proof['bytes'], 'archive':str(archive_path)}))


if __name__ == '__main__':
    main()
