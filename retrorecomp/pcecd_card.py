"""The PC Engine CD's System Card, as the player gives it, identified by its hash (Retro-Recomp's own code, MIT; no card byte is stored here).

The System Card is the firmware of the CD-ROM² system: 256 KiB that boots the disc, with the services (CD, ADPCM, backup memory)
every game calls. The rule of every machine applies: the player's own file, checked by its hash, never shipped.

The table lists the images the converter knows by hash, with what is measured of each (`checked`): a hash is a number about a file,
never its content. A file that is not in the table is refused with its size and SHA-1, so an entry can be added after it has been
run. Nothing is inferred from a name or a size alone (the engine, too, checks only the length and never authenticates the card).
The Super System Card has 192 KiB of RAM the original card lacks; which RAM profile a game runs with is the converter's, never
read from the card.

Measured so far (docs/PC_ENGINE_CD.md): the USA 3.0 card is the one the engine's own evidence boots; the Japanese 3.0 card is the one
of the maintainer's library.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path

CARD_BYTES = 256 * 1024


@dataclass(frozen=True)
class KnownCard:
    sha1: str
    name: str
    version: str
    region: str           # 'usa' or 'japan'
    checked: str          # 'engine' (the engine's own evidence boots it), 'panel' (it booted every disc of our panel), 'untried' (known by hash only)


KNOWN = (
    # Super System Card 3.0, the TurboDuo's (the card the pinned engine's documents name: its SHA-1 and SHA-256 are in its FIRMWARE.md).
    KnownCard('d02611d99921986147c753df14c7349b31d71950', 'Super System Card', '3.0', 'usa', 'engine'),
    # Super System Card 3.0 of the PC Engine Duo (Japan), the usual `syscard3.pce` of the frontends.
    KnownCard('79f5ff55dd10187c7fd7b8daab0b3ffbd1f56a2c', 'Super System Card', '3.0', 'japan', 'panel'),
)
BY_SHA1 = {card.sha1: card for card in KNOWN}


class CardError(ValueError):
    pass


@dataclass(frozen=True)
class Card:
    path: Path
    sha256: str
    sha1: str
    name: str
    version: str
    region: str
    checked: str

    def metadata(self) -> dict:
        return {'name': self.path.name, 'sha256': self.sha256, 'sha1': self.sha1, 'card': self.name, 'version': self.version,
                'region': self.region, 'checked': self.checked}

    def data(self) -> bytes:
        blob = Path(self.path).read_bytes()
        if hashlib.sha256(blob).hexdigest() != self.sha256:
            raise CardError(f'{self.path.name} changed during the conversion.')
        return blob


# Cards the PC Engine CD does not convert with (it accepts the two 3.0 cards of BY_SHA1 only) but that a HuCard reader must still
# recognise and refuse, by SHA-1 (MAME 0.289's pce and tg16 softlists, read on 27 November 2026 by the PC Engine specialist). The Games
# Express CD Card is 32 KiB; the Arcade Card Pro carries the Japanese 3.0's bytes and is covered by BY_SHA1.
REFUSED_ONLY = {
    'a39a66da7de6ba94ab84d04eef7afeec7d4ee66a': 'CD-ROM System Card 1.0 (japan)',
    'f92ea593c8a935f58f8e1c3b2fc730951ec4fa71': 'CD-ROM System Card 2.0 (japan)',
    '88da02e2503f7c32810f5d93a34849d470742b6d': 'CD-ROM System Card 2.1 (japan)',
    '2bea3dac98f84b2f2f469fa77ea720b8770d598d': 'CD-ROM System Card 2.0 (usa)',
    '014881a959e045e00f4db8f52955200865d40280': 'Games Express CD Card',
}


def system_card_name(data: bytes) -> str | None:
    """What these bytes are when they are a System Card (a known one, or a card only refused), None otherwise: what the HuCard reader
    asks of the decoded ROM, in both bit orders, so that a card dropped as a `.pce` is not converted as a game. `identify` is the
    stricter check of the card the PC Engine CD converts with (size and BY_SHA1)."""
    digest = hashlib.sha1(data).hexdigest()
    known = BY_SHA1.get(digest) if len(data) == CARD_BYTES else None
    if known is not None:
        return f'{known.name} {known.version} ({known.region})'
    return REFUSED_ONLY.get(digest)


def identify(path: Path) -> Card:
    path = Path(path)
    size = path.stat().st_size
    if size != CARD_BYTES:
        raise CardError(f'{path.name} is {size} bytes; a System Card is {CARD_BYTES} bytes.')
    blob = path.read_bytes()
    sha1 = hashlib.sha1(blob).hexdigest()
    known = BY_SHA1.get(sha1)
    if known is None:
        raise CardError(f'{path.name} is not a known System Card (SHA-1 {sha1}).')
    return Card(path, hashlib.sha256(blob).hexdigest(), sha1, known.name, known.version, known.region, known.checked)


def choose(candidates) -> Card | None:
    """The card among the files or folders the player named (None: no known card). The one the engine's evidence boots first, then the
    highest version, then the name."""
    found: list[Card] = []
    for item in candidates:
        item = Path(item)
        files = sorted(item.iterdir()) if item.is_dir() else [item]
        for file in files:
            if not file.is_file() or file.stat().st_size != CARD_BYTES:
                continue
            try:
                found.append(identify(file))
            except (CardError, OSError):
                continue
    if not found:
        return None
    found.sort(key=lambda c: (c.checked != 'engine', [-int(p) for p in c.version.split('.')], c.path.name.lower()))
    return found[0]
