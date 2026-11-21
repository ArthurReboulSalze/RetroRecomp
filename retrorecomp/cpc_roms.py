"""The Amstrad CPC firmware a converted disk game runs on, from a pinned, hash-checked source (docs/AMSTRAD_CPC.md, "Firmware";
licenses/amstrad-cpc-roms.md).

A CPC game is started from BASIC and calls the firmware's routines; its interrupt runs the firmware's handler: the converted game
holds the system ROM (the OS and Locomotive BASIC) and AMSDOS, translated with the game's code. The ROMs are Amstrad's copyright.
Amstrad allowed emulator authors to include their ROMs (Cliff Lawson, 1999) as long as the copyright messages stay unaltered and
nobody charges for the ROM code; Locomotive BASIC is not named in that permission. The maintainer chose on 21 November 2026 to
rely on it for the CPC as for the Spectrum: the converter fetches the 6128's system ROM and AMSDOS from a pinned source on first
use, never from this repository, and a player may give their own instead (retrorecomp/cpc_firmware.py, Options).

* The pinned source is the `rom/` folder of Caprice32 (ColinPitrat/caprice32 on GitHub), at one commit. Only the two ROM files
  are fetched: no Caprice32 code is read into the converter or a game, and Caprice32's GPL does not reach them.
* Each file is checked four ways before it is used, and a file that fails any is refused with a sentence, never guessed at: its
  size; its Git blob SHA-1 at the pinned commit; the SHA-1 MAME 0.289 lists for it (cpc_firmware.DIGESTS); its SHA-256, pinned
  here. These are numbers about the ROMs, never their bytes.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path

# ColinPitrat/caprice32, the commit the maintainer pinned on 21 November 2026.
SOURCE_REPOSITORY = 'ColinPitrat/caprice32'
SOURCE_COMMIT = '276658ae9a9e40fc899987e69c3f5653ece37693'
SOURCE_URL = f'https://raw.githubusercontent.com/{SOURCE_REPOSITORY}/{SOURCE_COMMIT}/rom/'
RETRY_SECONDS = 3
# file name in the pinned folder -> (option it fills, bytes, Git blob SHA-1 at the commit, SHA-256). The SHA-256 recorded on
# 22 November 2026 from the first download (Arthur's yes): both files are the commit's blobs and the ones MAME 0.289 lists (the
# English CPC 6128's system ROM, AMSDOS).
FILES = {
    'cpc6128.rom': ('cpc_system', 0x8000, 'fe0aba5e67ef2f21e27cc0ff15dd97940b7ead51',
                    '31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562'),
    'amsdos.rom': ('cpc_amsdos', 0x4000, 'ee61b8cb0e45ab06ad68531d4c483e5ae41a22d0',
                   'ea65e0fb44ee93ede4b6c507509b7e5ddf497fb7155023bea91ef229469fa04d'),
}


@dataclass(frozen=True)
class FirmwareSet:
    """The system ROM and AMSDOS a conversion runs on, and where each came from ('pinned' or 'player')."""
    system: bytes
    amsdos: bytes
    record: dict


def directory() -> Path:
    from .paths import ROOT
    return ROOT / '.deps' / f'cpc-roms-{SOURCE_COMMIT[:12]}'


def git_blob_sha1(data: bytes) -> str:
    """Git's name for a file's content: the SHA-1 of `blob <size>\\0` then the bytes."""
    return hashlib.sha1(b'blob %d\0' % len(data) + data).hexdigest()


def problem(name: str, data: bytes) -> str | None:
    """Why `data` is not the pinned file `name`, or None when every check passes."""
    from .cpc_firmware import DIGESTS
    option, size, blob, sha256 = FILES[name]
    if len(data) != size:
        return f'{name}: {len(data)} bytes, not {size}'
    if git_blob_sha1(data) != blob:
        return f'{name}: not the file of the pinned commit'
    known = DIGESTS.get(hashlib.sha1(data).hexdigest())
    if known is None or known[0] != option:
        return f'{name}: not the ROM MAME lists for it'
    if sha256 is None or hashlib.sha256(data).hexdigest() != sha256:
        return f'{name}: not the pinned SHA-256'
    return None


def _checked(path: Path, name: str) -> bool:
    try:
        return problem(name, path.read_bytes()) is None
    except OSError:
        return False


def fetch(emit=print) -> Path:
    """The folder holding the pinned firmware, fetched and checked on first use (up to eight conversions wait on one lock)."""
    from .library import entry_lock
    folder = directory()
    with entry_lock(folder, timeout=900):
        missing = [name for name in FILES if not _checked(folder / name, name)]
        if missing:
            from .updater import download_pinned
            folder.mkdir(parents=True, exist_ok=True)
            emit('Amstrad CPC: fetching the Amstrad firmware (the 6128 system ROM and AMSDOS, 48 KiB) from the Caprice32 '
                 'project, under Amstrad\'s permission for emulators.')
            for name in missing:
                _option, size, _blob, sha256 = FILES[name]
                target = folder / name
                partial = target.with_name(name + '.part')
                try:
                    if sha256 is None:
                        raise ValueError('no pinned SHA-256')
                    download_pinned(SOURCE_URL + name, partial, size, sha256, size, f'{name}: not the pinned ROM image.',
                                    wait=RETRY_SECONDS)
                    reason = problem(name, partial.read_bytes())
                    if reason:
                        raise ValueError(reason)
                    partial.replace(target)
                except Exception as exc:  # noqa: BLE001 - every failure is the same sentence for the player
                    partial.unlink(missing_ok=True)
                    raise ValueError(f'The Amstrad CPC firmware could not be fetched ({exc.__class__.__name__}): choose your '
                                     'own system ROM and AMSDOS ROM in Options, or try again once online.') from None
    return folder


def firmware_for(options: dict, emit=print) -> FirmwareSet:
    """The firmware a conversion uses: each of the player's own files when its option names one (checked by
    cpc_firmware.own_firmware), else the pinned file. ValueError with the reason when a file the player gave is not one."""
    from .cpc_firmware import own_firmware
    parts, record, folder = {}, {}, None
    for name, (option, _size, _blob, sha256) in FILES.items():
        if options.get(option):
            own = own_firmware(option, options[option])
            parts[option], record[option] = own.data, {'origin': 'player', 'label': own.label, 'sha256': own.sha256}
        else:
            folder = folder or fetch(emit)
            data = (folder / name).read_bytes()
            parts[option] = data
            record[option] = {'origin': 'pinned', 'source': f'{SOURCE_REPOSITORY}@{SOURCE_COMMIT[:12]}/rom/{name}',
                              'sha256': hashlib.sha256(data).hexdigest()}
    return FirmwareSet(parts['cpc_system'], parts['cpc_amsdos'], record)


def licence_text() -> str:
    """The notice every converted CPC game carries (licenses/amstrad-cpc-roms.md)."""
    from .paths import ASSETS
    return (ASSETS / 'licenses' / 'amstrad-cpc-roms.md').read_text(encoding='utf-8')
