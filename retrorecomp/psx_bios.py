"""The PlayStation BIOS the player gives, identified by its hash (Retro-Recomp's own code, MIT; no BIOS byte is stored here).

The table lists the SHA-1 of the retail BIOS images as public lists of dumps give them (MAME's `psx.cpp` ROM list, RetroArch's
`System.dat`, cross-checked; .build/psx-study/agent-media.md 4.2): hashes are numbers about a file, never its content. A file that
is not in the table is refused with its size and SHA-1, so a missing entry can be added after checking it. OpenBIOS (PCSX-Redux,
MIT) carries no fixed hash: it is recognised by its name at offset 0x78, and the core embeds its own copy, used when the player
has no BIOS (the report then says "free BIOS").

A BIOS boots discs of its own region only, so a folder of BIOS files is searched for one that matches the disc: the region's usual
image first (the names Beetle PSX looks for), then any other known image of that region.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path

BIOS_BYTES = 512 * 1024


@dataclass(frozen=True)
class KnownBios:
    sha1: str
    model: str
    version: str
    region: str           # 'ntsc-j', 'ntsc-u', 'pal'


KNOWN = (
    KnownBios('343883a7b555646da8cee54aadd2795b6e7dd070', 'SCPH-1000', '1.0', 'ntsc-j'),
    KnownBios('b06f4a861f74270be819aa2a07db8d0563a7cc4e', 'SCPH-3000', '1.1', 'ntsc-j'),
    KnownBios('e38466a4ba8005fba7e9e3c7b9efeba7205bee3f', 'SCPH-3500', '2.1', 'ntsc-j'),
    KnownBios('ffa7f9a7fb19d773a0c3985a541c8e5623d2c30d', 'SCPH-5000', '2.2', 'ntsc-j'),
    KnownBios('b05def971d8ec59f346f2d9ac21fb742e3eb6917', 'SCPH-5500', '3.0', 'ntsc-j'),
    KnownBios('77b10118d21ac7ffa9b35f9c4fd814da240eb3e9', 'SCPH-7000', '4.0', 'ntsc-j'),
    KnownBios('1b0dbdb23da9dc0776aac58d0755dc80fea20975', 'SCPH-7000W', '4.1', 'ntsc-j'),
    KnownBios('339a48f4fcf63e10b5b867b8c93cfd40945faf6c', 'SCPH-100', '4.3', 'ntsc-j'),
    KnownBios('649895efd79d14790eabb362e94eb0622093dfb9', 'DTL-H1001', '2.0', 'ntsc-u'),
    KnownBios('ca7af30b50d9756cbd764640126c454cff658479', 'DTL-H1101', '2.1', 'ntsc-u'),
    KnownBios('10155d8d6e6e832d6ea66db9bc098321fb5e8ebf', 'SCPH-1001', '2.2', 'ntsc-u'),
    KnownBios('0555c6fae8906f3f09baf5988f00e55f88e9f30b', 'SCPH-5501', '3.0', 'ntsc-u'),
    KnownBios('14df4f6c1e367ce097c11deae21566b4fe5647a9', 'SCPH-7001', '4.1', 'ntsc-u'),
    KnownBios('dcffe16bd90a723499ad46c641424981338d8378', 'SCPH-101', '4.5', 'ntsc-u'),
    KnownBios('20b98f3d80f11cbf5a7bfd0779b0e63760ecc62c', 'SCPH-1002', '2.0', 'pal'),
    KnownBios('76cf6b1b2a7c571a6ad07f2bac0db6cd8f71e2cc', 'SCPH-1002', '2.1', 'pal'),
    KnownBios('b6a11579caef3875504fcf3831b8e3922746df2c', 'SCPH-1002', '2.2', 'pal'),
    KnownBios('f6bc2d1f5eb6593de7d089c425ac681d6fffd3f0', 'SCPH-5502', '3.0', 'pal'),
    KnownBios('8d5de56a79954f29e9006929ba3fed9b6a418c1d', 'SCPH-7502', '4.1', 'pal'),
    KnownBios('beb0ac693c0dc26daf5665b3314db81480fa5c7c', 'SCPH-102', '4.4', 'pal'),
    KnownBios('dbc7339e5d85827c095764fc077b41f78fd2ecae', 'SCPH-102', '4.5', 'pal'),
)
BY_SHA1 = {k.sha1: k for k in KNOWN}
# The image Beetle PSX itself boots for each region: the most exercised path of the pinned core.
PREFERRED = {'ntsc-j': 'SCPH-5500', 'ntsc-u': 'SCPH-5501', 'pal': 'SCPH-5502'}
OPENBIOS_MARK = (0x78, b'OpenBIOS')


class BiosError(ValueError):
    pass


@dataclass(frozen=True)
class Bios:
    path: Path
    sha256: str
    sha1: str
    model: str
    version: str
    region: str | None     # None for OpenBIOS (any region)
    free: bool             # OpenBIOS

    def metadata(self) -> dict:
        return {'name': self.path.name, 'sha256': self.sha256, 'sha1': self.sha1, 'model': self.model,
                'version': self.version, 'region': self.region, 'free': self.free}

    def data(self) -> bytes:
        blob = Path(self.path).read_bytes()
        if hashlib.sha256(blob).hexdigest() != self.sha256:
            raise BiosError(f'{self.path.name} changed during the conversion.')
        return blob


def identify(path: Path) -> Bios:
    path = Path(path)
    size = path.stat().st_size
    if size != BIOS_BYTES:
        raise BiosError(f'{path.name} is {size} bytes; a PlayStation BIOS is {BIOS_BYTES} bytes.')
    blob = path.read_bytes()
    sha1 = hashlib.sha1(blob).hexdigest()
    sha256 = hashlib.sha256(blob).hexdigest()
    known = BY_SHA1.get(sha1)
    if known is not None:
        return Bios(path, sha256, sha1, known.model, known.version, known.region, False)
    offset, mark = OPENBIOS_MARK
    if blob[offset:offset + len(mark)] == mark:
        return Bios(path, sha256, sha1, 'OpenBIOS', 'open', None, True)
    raise BiosError(f'{path.name} is not a known PlayStation BIOS (SHA-1 {sha1}).')


def choose(candidates, region: str | None) -> Bios | None:
    """The BIOS for a disc of `region` among files or folders the player named (None: no match).

    Retail images of the disc's region only; the region's usual image first, then the highest version."""
    found: list[Bios] = []
    for item in candidates:
        item = Path(item)
        files = sorted(item.iterdir()) if item.is_dir() else [item]
        for f in files:
            if not f.is_file() or f.stat().st_size != BIOS_BYTES:
                continue
            try:
                found.append(identify(f))
            except (BiosError, OSError):
                continue
    retail = [b for b in found if not b.free and (region is None or b.region == region)]
    if not retail:
        return None
    preferred = PREFERRED.get(region)
    retail.sort(key=lambda b: (b.model != preferred, [-int(p) for p in b.version.split('.')], b.path.name.lower()))
    return retail[0]
