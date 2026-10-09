"""Explicit Master System peripheral catalogue; no instruction-pattern probing.

Cartridge identities: MEKA's verified software database and Genesis Plus GX's
SMS cartridge table. See docs/LIGHT_PHASER.md for sources and scope.
"""
from dataclasses import dataclass
from pathlib import Path
import re
import unicodedata


@dataclass(frozen=True)
class LightPhaserGame:
    title: str
    crcs: tuple[int, ...]
    hcounter_offset: int = 20
    trigger_on_p2: bool = False


LIGHT_PHASER_GAMES = (
    LightPhaserGame("Assault City", (0x861B6E79,)),
    LightPhaserGame("Gangster Town", (0x5FC74D2A,), 16),
    # C5083000 is a documented, working overdump; preserve the supplied ROM.
    LightPhaserGame("Hang-On & Safari Hunt", (0xE167A561, 0xA120B77F, 0x91E93385, 0xC5083000)),
    LightPhaserGame("Laser Ghost", (0x0CA95637,), trigger_on_p2=True),
    LightPhaserGame("Marksman Shooting & Trap Shooting", (0xE8EA842C,)),
    LightPhaserGame("Marksman Shooting / Trap Shooting / Safari Hunt", (0xE8215C2E,)),
    LightPhaserGame("Missile Defense 3-D", (0xFBE5CFBB, 0x43DEF05D, 0xE79BB689), 22),
    LightPhaserGame("Operation Wolf", (0x205CAAE8, 0x23283F37)),
    LightPhaserGame("Rambo III", (0xDA5A7013,)),
    LightPhaserGame("Rescue Mission", (0x79AC8E7F,)),
    LightPhaserGame("Shooting Gallery", (0x4B051022,)),
    LightPhaserGame("Space Gun", (0xA908CFF5,)),
    LightPhaserGame("Wanted", (0x5359762D,), 16),
    LightPhaserGame("3D Gunner", (0x56DCB2D4,), 20),
    # SMS Power's peripheral catalogue and authors' manuals document these.
    # Selection is not a claim of gameplay qualification for these programs.
    LightPhaserGame("Die Hard 2", ()),  # Unreleased; no verified ROM identity yet.
    LightPhaserGame("Color & Switch Test", (0x7253C3EC,)),  # Sega diagnostic cartridge.
    LightPhaserGame("Porkpolis", ()),
    LightPhaserGame("Shootagem", ()),
    LightPhaserGame("Shooting Stars", ()),
    LightPhaserGame("SMS-A-Sketch 1.2", ()),
)


def _name(value: str) -> str:
    value = re.sub(r"\([^)]*\)|\[[^]]*\]", "", value)
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", value.lower())


def light_phaser_game(crc32: int, filename: str) -> LightPhaserGame | None:
    # The two editions have different peripherals. Identity wins over filename.
    if crc32 == 0x0BD8DA96:
        return None
    for game in LIGHT_PHASER_GAMES:
        if crc32 in game.crcs:
            return game
    stem = Path(filename).stem
    title = _name(stem)
    if title == "smsasketch":
        # Light-gun support was added in 1.2. Do not tag older/bare filenames.
        if re.search(r"\b(?:v|version\s*)?1[._]2\b", stem, re.I):
            return next(g for g in LIGHT_PHASER_GAMES if g.title == "SMS-A-Sketch 1.2")
        return None
    if title == "assaultcity":
        return LIGHT_PHASER_GAMES[0] if re.search(r"light[ _-]*phaser", stem, re.I) else None
    aliases = {"safarihunt": 2, "marksmanshooting": 4, "trapshooting": 4,
               "rambo3": 8, "shootingg": 10}
    if title in aliases:
        return LIGHT_PHASER_GAMES[aliases[title]]
    if title == "m4padchk":
        return next(g for g in LIGHT_PHASER_GAMES if g.title == "Color & Switch Test")
    return next((game for game in LIGHT_PHASER_GAMES if _name(game.title) == title), None)


def game_tags(crc32: int, filename: str) -> tuple[str, ...]:
    """Peripheral tags, not genres: ordinary pad-controlled shooters stay untagged."""
    return ("shooting",) if light_phaser_game(crc32, filename) else ()
