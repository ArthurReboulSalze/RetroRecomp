"""C-BIOS for the MSX (BSD-2-Clause, licenses/cbios.md): the BIOS a cartridge boots when the player gives none.

C-BIOS is not part of Retro-Recomp's files. The first conversion that needs it fetches the official release archive of its
pinned version from the C-BIOS project on SourceForge into the converter's dependency folder. The archive's size and SHA-256,
and those of every image the machine uses, are pinned here and checked on every use, so a changed or truncated file is
refused and fetched again. C-BIOS runs cartridges only (no MSX-BASIC, no disk, no cassette); a game it cannot run plays with
the player's own BIOS (docs/MSX.md, "Known C-BIOS failures"). An exported game that boots C-BIOS embeds the images and the
licence text.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import zipfile

VERSION = '0.29a'
RETRY_SECONDS = 3
URL = 'https://downloads.sourceforge.net/project/cbios/cbios/0.29/cbios-0.29a.zip'
ARCHIVE = ('cbios-0.29a.zip', 269374, 'c585a2f4a10b397e460a95043d59ac79cf4442fbb45a6e14a1e27ef9febaed73')
# The images used, from the archive's roms/ folder (size, SHA-256), recorded at the first fetch on 12 Nov 2026.
MEMBERS = {
    'cbios_main_msx1.rom': (32768, '921d35edf143f1fde8e53570f92f85e05854610d6a5ea76cce881f2f9040cd9c'),
    'cbios_main_msx1_eu.rom': (32768, 'ad114c0d8d1c8eae408fb6876a16ddadd8e336699c53eb04661bda8ebbc4aeab'),
    'cbios_logo_msx1.rom': (16384, '8ad88a4653e26bdbd4c38329fe0a115846e9aa0866b0ac1fe1dd2c260c9932b3'),
    # The MSX2 (stage 6, 12 Nov 2026): main ROMs, the logo ROM and the sub-ROM.
    'cbios_main_msx2.rom': (32768, '8767fca1a1ca5928496bb6185a0e951c66d68f65361305134a25f7912085766b'),
    'cbios_main_msx2_eu.rom': (32768, '625a740ba093e2987acc6c995825724feaba6200b2ecc845820cd8bd5447515a'),
    'cbios_logo_msx2.rom': (16384, 'a6ecf0bee1d1aeae4a2df4ace1d711b8c5883cbed50f7d6c8c524f6b19f03ef4'),
    'cbios_sub.rom': (16384, '95db258195d1dea673b3826a8ef3d4b747f87f93587ae66e137acd2e39c3c0f1'),
    # The MSX2+ (13 Nov 2026): its main ROMs and logo ROM, from the same archive; the sub-ROM is the MSX2's.
    'cbios_main_msx2+.rom': (32768, 'f65adce74b52836f1e2a54d2f7e269859baa688b61c18bafbcf7496adfb440e3'),
    'cbios_main_msx2+_eu.rom': (32768, '594c4067cd80c929930bac40b24987746d906d0fe8ad4005fe4a262160728156'),
    'cbios_logo_msx2+.rom': (16384, 'cc89b76cbf87ee87ab6c84dbd26e3bad014d8bd30a1f1bbe0629d2f39a1ab87b'),
}
LIMIT = 4 * 1024 * 1024


def directory() -> Path:
    from .paths import ROOT
    return ROOT / '.deps' / f'cbios-{VERSION}'


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _checked(path: Path, size: int, digest: str) -> bool:
    try:
        return path.stat().st_size == size and _sha256(path) == digest
    except OSError:
        return False


def fetch(emit=print) -> Path:
    """The folder holding the pinned C-BIOS images, fetched and checked on first use."""
    from .library import entry_lock
    folder = directory()
    # Up to eight conversions run at once: one fetches and unpacks, the others wait and find the checked files.
    with entry_lock(folder, timeout=900):
        _fetch_locked(folder, emit)
    return folder


def _fetch_locked(folder: Path, emit) -> None:
    archive = folder / ARCHIVE[0]
    if not _checked(archive, ARCHIVE[1], ARCHIVE[2]):
        from .updater import download_pinned
        folder.mkdir(parents=True, exist_ok=True)
        partial = archive.with_name(archive.name + '.part')
        emit(f'MSX: fetching C-BIOS {VERSION} ({ARCHIVE[1] // 1024} KiB) from the C-BIOS project.')
        try:
            mismatch = f'{ARCHIVE[0]}: the downloaded file is not the pinned one.'
            download_pinned(URL, partial, ARCHIVE[1], ARCHIVE[2], LIMIT, mismatch, wait=RETRY_SECONDS)
            partial.replace(archive)
        except Exception as exc:  # noqa: BLE001 - every failure is the same sentence for the player
            partial.unlink(missing_ok=True)
            raise ValueError(f'C-BIOS {VERSION} could not be fetched ({exc.__class__.__name__}): choose your own MSX BIOS in '
                             'Options, or try again once online.') from None
    with zipfile.ZipFile(archive) as bundle:
        for name, (size, digest) in MEMBERS.items():
            target = folder / name
            if _checked(target, size, digest):
                continue
            data = bundle.read(f'cbios-{VERSION}/roms/{name}')
            if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
                raise ValueError(f'{name}: not the pinned C-BIOS image.')
            partial = target.with_name(target.name + '.part')
            partial.write_bytes(data)
            partial.replace(target)


def image(standard: str = 'ntsc', emit=print, model: str = 'msx1') -> bytes:
    """The BIOS source the machine boots. MSX1: 48 KiB, the main ROM (international 60 Hz, or European 50 Hz) and the logo
    ROM. MSX2: 64 KiB, the MSX2 main ROM, its logo ROM and the sub-ROM (msx_setup_msx2's layout); MSX2+ the same with the
    MSX2+ main and logo ROMs."""
    folder = fetch(emit)
    if model == 'msx2plus':
        main = 'cbios_main_msx2+_eu.rom' if standard == 'pal' else 'cbios_main_msx2+.rom'
        return b''.join((folder / name).read_bytes() for name in (main, 'cbios_logo_msx2+.rom', 'cbios_sub.rom'))
    if model == 'msx2':
        main = 'cbios_main_msx2_eu.rom' if standard == 'pal' else 'cbios_main_msx2.rom'
        return b''.join((folder / name).read_bytes() for name in (main, 'cbios_logo_msx2.rom', 'cbios_sub.rom'))
    main = 'cbios_main_msx1_eu.rom' if standard == 'pal' else 'cbios_main_msx1.rom'
    return (folder / main).read_bytes() + (folder / 'cbios_logo_msx1.rom').read_bytes()


def licence_text() -> str:
    """The notice an exported game carries when it embeds C-BIOS (licenses/cbios.md)."""
    from .paths import ASSETS
    return (ASSETS / 'licenses' / 'cbios.md').read_text(encoding='utf-8')
