"""Build the small, converter-only MOD player on the current host.

Pinned, verified sources; no compiler or download is used by the packaged app.
The modules are replayed live with libxmp-lite, as used for ChipLoom checks.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
XMP_VERSION = '4.7.3'
XMP_HASH = 'b6a98797e4fb9c9a705f5d53112aa5214561857e929a644928b9e658930d9440'
MA_HASH = '7e4f3f13c8fe66df2080ac3dd12a89193e3c2463cb7f067c798abd7331cd8ee6'


def fetch(path, url, digest, limit):
    if not path.is_file():
        request = urllib.request.Request(url, headers={'User-Agent': 'Retro-Recomp-build'})
        with urllib.request.urlopen(request, timeout=45) as response:
            data = response.read(limit + 1)
        if len(data) > limit or hashlib.sha256(data).hexdigest() != digest:
            raise ValueError('Unexpected audio dependency: ' + path.name)
        path.write_bytes(data)
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError('Audio source checksum mismatch: ' + path.name)


def cmake_path():
    found = shutil.which('cmake')
    if found:
        return found
    vswhere = Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)'))
    vswhere /= 'Microsoft Visual Studio/Installer/vswhere.exe'
    if vswhere.is_file():
        paths = subprocess.check_output([str(vswhere), '-latest', '-products', '*', '-find',
            'Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/cmake.exe'], text=True)
        for candidate in paths.splitlines():
            if Path(candidate).is_file():
                return candidate
    raise RuntimeError('Install CMake and a native C compiler to build credits audio.')


def build():
    deps = ROOT / '.deps/credits-audio'
    deps.mkdir(parents=True, exist_ok=True)
    archive = deps / f'libxmp-{XMP_VERSION}.tar.gz'
    fetch(archive, f'https://github.com/libxmp/libxmp/releases/download/libxmp-{XMP_VERSION}/{archive.name}',
          XMP_HASH, 4_000_000)
    fetch(deps / 'miniaudio.h', 'https://raw.githubusercontent.com/mackron/miniaudio/0.11.23/miniaudio.h',
          MA_HASH, 5_000_000)
    source = deps / f'libxmp-{XMP_VERSION}'
    if not source.is_dir():
        with tarfile.open(archive) as package:
            package.extractall(deps, filter='data')
    stage = ROOT / '.build/credits-audio'
    cmake = cmake_path()
    config = [cmake, '-S', str(ROOT / 'tools/credits_audio'), '-B', str(stage),
              '-DCMAKE_BUILD_TYPE=Release', '-DXMP_SOURCE=' + str(source),
              '-DMINIAUDIO_INCLUDE=' + str(deps)]
    if os.name == 'nt':
        config += ['-A', 'x64']
    subprocess.run(config, check=True, stdout=sys.stderr)
    subprocess.run([cmake, '--build', str(stage), '--config', 'Release', '--target',
                    'retro_credits', '--parallel', '4'], check=True, stdout=sys.stderr)
    name = 'retro_credits.dll' if os.name == 'nt' else 'libretro_credits.so'
    built = stage / ('Release' if os.name == 'nt' else '') / name
    target = stage / 'runtime' / name
    target.parent.mkdir(exist_ok=True)
    # Never truncate a shared library mapped by a running source preview.
    # POSIX keeps its previous inode alive; Windows can reject the replacement
    # cleanly if the DLL is locked, leaving the working player intact.
    with tempfile.NamedTemporaryFile(prefix='.'+name+'.', dir=target.parent, delete=False) as tmp:
        pending = Path(tmp.name)
    try:
        shutil.copy2(built, pending)
        os.replace(pending, target)
    finally:
        pending.unlink(missing_ok=True)
    (stage / 'receipt.json').write_text(json.dumps({'xmp': XMP_HASH, 'miniaudio': MA_HASH,
        'bytes': target.stat().st_size, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest()}, indent=2)+'\n')
    return target


if __name__ == '__main__':
    print(build())
