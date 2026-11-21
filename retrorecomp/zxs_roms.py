"""The ZX Spectrum ROMs a converted snapshot runs on (docs/ZX_SPECTRUM.md, "The ROM"; licenses/zx-spectrum-roms.md).

A snapshot holds RAM only: the game calls the ROM's routines and its interrupt runs the ROM's handler at 0038h, so the
converted game holds the ROM too, translated with it. The ROMs are Amstrad's copyright. Amstrad allowed emulator authors to
include them (Cliff Lawson, 31 August 1999) as long as the copyright messages stay unaltered and nobody charges for the ROM
code; the maintainer chose on 21 November 2026 to rely on that permission: the converter fetches the 48K and 128K ROMs from a
pinned, hash-checked source on first use, never from this repository, and a player may give their own instead.

* The pinned source is the Fuse emulator's `roms/` folder (the GitHub mirror of the Fuse project), at one commit; the ROM
  files there are under the Amstrad permission, not under Fuse's GPL (its `README.copyright`). Only the ROMs are fetched:
  no Fuse code is read into the converter or a game.
* The player's own ROM (Options) is accepted when its SHA-256 is one of the images below: the 48K ROM (16 KiB), the 128K's
  pair as one 32 KiB image (the editor ROM then the 48K BASIC ROM), or the 128K editor ROM alone with the BASIC ROM's file
  beside it. Its bytes are the fetched ones, so the converted game is the same either way.

Sizes and SHA-256 recorded on 21 November 2026 from the pinned commit; their SHA-1 agree with MAME's `spectrum` and
`spec128` sets. These are numbers about the ROMs, never their bytes.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path

# fuse-emulator/fuse (GitHub mirror of the Fuse project), master on 19 November 2026.
SOURCE_REPOSITORY = 'fuse-emulator/fuse'
SOURCE_COMMIT = '089eadf7c175c54a37ff66843479235a845890fd'
SOURCE_URL = f'https://raw.githubusercontent.com/{SOURCE_REPOSITORY}/{SOURCE_COMMIT}/roms/'
RETRY_SECONDS = 3
ROM_BYTES = 0x4000
# file name in the pinned folder -> (bytes, SHA-256)
FILES = {
    '48.rom': (ROM_BYTES, 'd55daa439b673b0e3f5897f99ac37ecb45f974d1862b4dadb85dec34af99cb42'),
    '128-0.rom': (ROM_BYTES, '3ba308f23b9471d13d9ba30c23030059a9ce5d4b317b85b86274b132651d1425'),
    '128-1.rom': (ROM_BYTES, '8d93c3342321e9d1e51d60afcd7d15f6a7afd978c231b43435a7c0757c60b9a3'),
}
# The 128K pair as one image (128-0.rom then 128-1.rom), as some collections keep it.
PAIR_128_SHA256 = 'c1ff621d7910105d4ee45c31e9fd8fd0d79a545c78b66c69a562ee1ffbae8d72'
# Which files each model runs on, in the order of its ROM banks (the 128K: bank 0 the editor, bank 1 the 48K BASIC).
MODEL_FILES = {'16k': ('48.rom',), '48k': ('48.rom',), '128k': ('128-0.rom', '128-1.rom')}
# The firmware option that holds the player's own ROM for each model.
MODEL_OPTION = {'16k': 'zxs_rom48', '48k': 'zxs_rom48', '128k': 'zxs_rom128'}


@dataclass(frozen=True)
class RomSet:
    """The ROM image a model runs on (16 KiB, or 32 KiB for the 128K), its SHA-256, and where it came from."""
    model: str
    data: bytes
    sha256: str
    origin: str          # 'pinned' (fetched from SOURCE_COMMIT) or 'player' (the Options file)


def directory() -> Path:
    from .paths import ROOT
    return ROOT / '.deps' / f'zx-roms-{SOURCE_COMMIT[:12]}'


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _checked(path: Path, size: int, digest: str) -> bool:
    try:
        return path.stat().st_size == size and _sha256(path.read_bytes()) == digest
    except OSError:
        return False


def fetch(emit=print) -> Path:
    """The folder holding the pinned ROMs, fetched and checked on first use (up to eight conversions wait on one lock)."""
    from .library import entry_lock
    folder = directory()
    with entry_lock(folder, timeout=900):
        missing = [name for name, (size, digest) in FILES.items() if not _checked(folder / name, size, digest)]
        if missing:
            from .updater import download_pinned
            folder.mkdir(parents=True, exist_ok=True)
            emit('ZX Spectrum: fetching the Amstrad ROMs (48K and 128K, 48 KiB) from the Fuse project, '
                 'under Amstrad\'s permission for emulators.')
            for name in missing:
                size, digest = FILES[name]
                target = folder / name
                partial = target.with_name(name + '.part')
                try:
                    download_pinned(SOURCE_URL + name, partial, size, digest, size, f'{name}: not the pinned ROM image.',
                                    wait=RETRY_SECONDS)
                    partial.replace(target)
                except Exception as exc:  # noqa: BLE001 - every failure is the same sentence for the player
                    partial.unlink(missing_ok=True)
                    raise ValueError(f'The ZX Spectrum ROMs could not be fetched ({exc.__class__.__name__}): choose your '
                                     'own Spectrum ROM in Options, or try again once online.') from None
    return folder


def pinned(model: str, emit=print) -> RomSet:
    folder = fetch(emit)
    data = b''.join((folder / name).read_bytes() for name in MODEL_FILES[model])
    return RomSet(model, data, _sha256(data), 'pinned')


def known_digest(data: bytes) -> str | None:
    """What a file is among the ROMs this module knows ('48.rom', '128-0.rom', '128-1.rom', '128'), None otherwise."""
    digest = _sha256(data)
    if digest == PAIR_128_SHA256 and len(data) == 2 * ROM_BYTES:
        return '128'
    return next((name for name, (size, known) in FILES.items() if size == len(data) and known == digest), None)


def own_rom(value, model: str) -> RomSet | None:
    """The player's own ROM for `model` from the option's path, None when the option is empty; ValueError when the file is
    not the ROM that model runs on."""
    if not value:
        return None
    path = Path(value)
    data = path.read_bytes() if path.stat().st_size <= 2 * ROM_BYTES else b''
    name = known_digest(data)
    if model in ('16k', '48k'):
        if name != '48.rom':
            raise ValueError(f'{path.name}: not the ZX Spectrum 48K ROM (16 KiB, the SHA-256 the converter knows).')
        return RomSet(model, data, _sha256(data), 'player')
    if name == '128':
        return RomSet(model, data, _sha256(data), 'player')
    if name == '128-0.rom':
        for other in sorted(path.parent.iterdir()):
            if other != path and other.is_file() and other.stat().st_size == ROM_BYTES \
                    and known_digest(other.read_bytes()) == '128-1.rom':
                data += other.read_bytes()
                return RomSet(model, data, _sha256(data), 'player')
        raise ValueError(f'{path.name}: the 128K editor ROM; its second half (the 48K BASIC ROM of the 128K) must be '
                         'beside it, or choose one 32 KiB image of both.')
    raise ValueError(f'{path.name}: not the ZX Spectrum 128K ROM (32 KiB, or the editor ROM with the BASIC ROM beside it).')


def rom_identity(value, model: str) -> str:
    """The SHA-256 of the ROM image `model` runs on: the player's own (when it is valid) or the pinned one; they are equal
    for a genuine ROM, so the request is the same either way."""
    try:
        own = own_rom(value, model)
    except (OSError, ValueError):
        own = None
    if own is not None:
        return own.sha256
    names = MODEL_FILES[model]
    return PAIR_128_SHA256 if len(names) == 2 else FILES[names[0]][1]


def rom_for(model: str, options: dict, emit=print) -> RomSet:
    """The ROM a conversion of `model` uses: the player's own when the option names one, else the pinned images."""
    own = own_rom(options.get(MODEL_OPTION[model]), model)
    return own if own is not None else pinned(model, emit)


def licence_text() -> str:
    """The notice every converted Spectrum game carries (licenses/zx-spectrum-roms.md)."""
    from .paths import ASSETS
    return (ASSETS / 'licenses' / 'zx-spectrum-roms.md').read_text(encoding='utf-8')
