"""Explicit 16-bit peripheral catalogue, separate from CPU qualification.

Hardware references and validation scope are in docs/GUNS_16BIT.md.
Names identify a peripheral, never authorize another cartridge's native code.
"""
from dataclasses import dataclass
from pathlib import Path
from .peripherals import _name


DEVICES = {'menacer': 1, 'justifier': 2, 'super_scope': 3}
LABELS = {'menacer': 'Menacer', 'justifier': 'Konami Justifier',
          'super_scope': 'Super Scope'}


@dataclass(frozen=True)
class GunGame:
    system: str
    title: str
    device: str
    crcs: tuple[int, ...] = ()
    x_offset: int = 0
    y_offset: int = 0


GAMES = (
    GunGame('md', 'Menacer 6-Game Cartridge', 'menacer', (0x936B85F7,), 0x52),
    GunGame('md', 'T2 - The Arcade Game', 'menacer', (0xA1264F17,), 0x84, 8),
    GunGame('md', 'Body Count', 'menacer', (), 0x44, 16),
    GunGame('md', 'Lethal Enforcers', 'justifier', (0xCA2BF99D,), 0),
    GunGame('md', 'Lethal Enforcers II - Gun Fighters', 'justifier', (0x4BFE045C,), 0x18),
    GunGame('snes', 'Super Scope 6', 'super_scope', (0xB141EA99,)),
    GunGame('snes', "Yoshi's Safari", 'super_scope'),
    GunGame('snes', 'Yoshi no Road Hunting', 'super_scope'),
    GunGame('snes', 'Battle Clash', 'super_scope'),
    GunGame('snes', "Metal Combat - Falcon's Revenge", 'super_scope'),
    GunGame('snes', 'Bazooka Blitzkrieg', 'super_scope'),
    GunGame('snes', 'Destructive', 'super_scope'),
    GunGame('snes', 'X Zone', 'super_scope'),
    GunGame('snes', 'T2 - The Arcade Game', 'super_scope'),
    GunGame('snes', 'Tin Star', 'super_scope'),
    GunGame('snes', 'Lamborghini American Challenge', 'super_scope'),
    # SNES Justifier has a different serial protocol; catalogued only.
    GunGame('snes', 'Lethal Enforcers', 'justifier'),
)


def gun_game(system: str, crc32: int, filename: str) -> GunGame | None:
    games = [game for game in GAMES if game.system == system]
    for game in games:
        if crc32 in game.crcs:
            return game
    name = _name(Path(filename).stem)
    if system == 'md' and name in ('menacer', 'menacer6in1', 'menacer6gamecartridge'):
        return GAMES[0]
    return next((game for game in games if _name(game.title) == name), None)


def write_header(project: Path, rom) -> GunGame | None:
    game = gun_game(rom.system_id, rom.crc32, rom.path.name)
    # Qualification is performed before this; never select by ROM name alone.
    (project / 'retro_gun_game.h').write_text(
        '/* Generated cartridge peripheral, selected before compilation. */\n'
        f'#define RR16_GUN {DEVICES[game.device] if game else 0}\n'
        f'#define RR16_GUN_X_OFFSET {game.x_offset if game else 0}\n'
        f'#define RR16_GUN_Y_OFFSET {game.y_offset if game else 0}\n', encoding='ascii')
    return game
