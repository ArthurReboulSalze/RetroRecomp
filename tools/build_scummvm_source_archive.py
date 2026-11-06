"""Write the corresponding-source archive of the ScummVM runtime (GPL section 6) for a release.

usage: python -B tools/build_scummvm_source_archive.py [output.tar.xz]

The archive holds, under one top folder:
  scummvm/      the ScummVM tree at the pinned commit (git archive of the .deps checkout, untouched by the patch),
  freetype/     the FreeType tree at the pinned commit,
  native/scummvm/  Retro-Recomp's patch series, LICENSE and README,
  retrorecomp/scummvm_build.py  the build script,
  BUILDING.txt  how to rebuild.
The checkouts are fetched by retrorecomp.scummvm_build if missing. Nothing of a player's game or a build output is included.
This tool is Retro-Recomp's own code (MIT); the lead attaches its output to a release, like licenses/upx-5.3.0-src.tar.xz.
"""
from __future__ import annotations

import io
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from retrorecomp import scummvm_build as build  # noqa: E402

BUILDING = """Corresponding source of the ScummVM runtime used by Retro-Recomp's adventure executables.

ScummVM {tag} (commit {rev}) and FreeType {ft_tag} (commit {ft_rev}) are unmodified in scummvm/ and freetype/.
Apply the patch series of native/scummvm/patches to scummvm/ with `git apply` (in file-name order), then build
as retrorecomp/scummvm_build.py does: FreeType static (no zlib, png, bzip2, HarfBuzz, Brotli); ScummVM's
devtools/create_project --cmake with the engines of one family, the libraries and features listed in
DISABLED_LIBRARIES and DISABLED_FEATURES disabled, SDL2 2.32 static; translations.dat rebuilt from
po/fr_FR.po de_DE.po es_ES.po it_IT.po with devtools/create_translations; fonts.dat limited to KEPT_FONTS;
dists/scummvm_rc_engine_data_big.rh emptied (no CJK fonts). Patch series SHA-256: {patch}.
"""


def _git_archive(checkout: Path, revision: str, prefix: str) -> bytes:
    return subprocess.run(['git', '-C', str(checkout), 'archive', '--format=tar', f'--prefix={prefix}/', revision],
                          check=True, capture_output=True).stdout


def main(argv: list[str]) -> int:
    log = build.build_root() / 'source-archive.log'
    log.parent.mkdir(parents=True, exist_ok=True)
    build._checkout(build.scummvm_checkout(), build.SCUMMVM_URL, build.SCUMMVM_TAG, build.SCUMMVM_REV, log, print)
    build._checkout(build.freetype_checkout(), build.FREETYPE_URL, build.FREETYPE_TAG, build.FREETYPE_REV, log, print)
    top = f'retrorecomp-scummvm-{build.SCUMMVM_TAG}-src'
    out = Path(argv[1]) if len(argv) > 1 else ROOT / '.build' / f'{top}.tar.xz'
    out.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(out, 'w:xz') as archive:
        for checkout, revision, name in ((build.scummvm_checkout(), build.SCUMMVM_REV, 'scummvm'),
                                         (build.freetype_checkout(), build.FREETYPE_REV, 'freetype')):
            with tarfile.open(fileobj=io.BytesIO(_git_archive(checkout, revision, f'{top}/{name}'))) as source:
                for member in source.getmembers():
                    archive.addfile(member, source.extractfile(member) if member.isfile() else None)
        for path in sorted((ROOT / 'native' / 'scummvm').rglob('*')):
            if path.is_file():
                archive.add(path, arcname=f'{top}/{path.relative_to(ROOT).as_posix()}')
        archive.add(ROOT / 'retrorecomp' / 'scummvm_build.py', arcname=f'{top}/retrorecomp/scummvm_build.py')
        text = BUILDING.format(tag=build.SCUMMVM_TAG, rev=build.SCUMMVM_REV, ft_tag=build.FREETYPE_TAG,
                               ft_rev=build.FREETYPE_REV, patch=build.patch_digest()).encode('utf-8')
        info = tarfile.TarInfo(f'{top}/BUILDING.txt')
        info.size = len(text)
        archive.addfile(info, io.BytesIO(text))
    print(out)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
