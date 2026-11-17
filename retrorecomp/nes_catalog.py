"""NES Zapper catalogue: the NES 2.0 device byte, then exact title aliases.

No database is imported. A cartridge uses the Zapper when its NES 2.0 header says so (default expansion device 8,
https://www.nesdev.org/wiki/NES_2.0), or when its file name is the exact title of a game known to support it. The
titles are the games' own names: the nine licensed games that need the Zapper and the licensed and unlicensed ones
that support it as an option, as the compatible-games list of the Wikipedia article on the NES Zapper names them
(read on 2 November 2026; facts only, no text taken; its entry for The Hunt for Red October is not taken: no other source
says the NES game uses the gun), plus the aliases this converter already carried (regional
spellings and two translated or unlicensed releases). Before 1.6.7 the catalogue also held 122 payload CRCs taken from
MesenNesDB, a file of the GPL-3 Mesen2 repository; they are gone, and a revision, hack or translation of these games
whose file name is not one of these titles and whose header does not name the Zapper is no longer recognised (the game
then runs with the two controllers). No ROM bytes or program code are included.
"""
from pathlib import Path
import re

ZAPPER_TITLES = (
    # Licensed games that need the Zapper
    "Duck Hunt", "Hogan's Alley", "Wild Gunman", "Gumshoe", "Gotcha! The Sport!", "Shooting Range", "Freedom Force",
    "To the Earth", "Barker Bill's Trick Shooting",
    # Licensed games that support it as an option
    "Operation Wolf", "Mechanized Attack", "The Adventures of Bayou Billy", "Adventures of Bayou Billy, The",
    "Track & Field II", "Laser Invasion", "The Lone Ranger", "Lone Ranger, The", "Day Dreamin' Davey",
    # Unlicensed games that support it
    "Baby Boomer", "Chiller",
    # Aliases the converter already carried
    "Mad City", "LaserScope", "Super Mario Bros. + Duck Hunt",
    "Super Mario Bros. + Duck Hunt + World Class Track Meet",
)

def _title(value: str) -> str:
    name = Path(value).name
    if Path(name).suffix.casefold() in {'.nes', '.zip', '.bin', '.rom'}:
        name = Path(name).stem
    return re.sub(r"[^a-z0-9]", "", re.sub(r"\([^)]*\)|\[[^]]*\]", "", name).casefold())

def zapper_game(data: bytes, filename: str) -> bool:
    if len(data) < 16 or data[:4] != b"NES\x1a":
        return False
    if data[7] & 12 == 8 and data[15] & 63 == 8:
        return True
    name = _title(filename)
    return any(name == _title(title) for title in ZAPPER_TITLES)


FOUR_SCORE_TITLES = (
    # Games written for the NES Four Score / NES Satellite (two extra controllers on the two ports), by their own titles.
    # Facts only, as for the Zapper above; a revision, hack or translation whose file name is not one of these titles and whose
    # header does not name the adapter runs with two controllers, as before. The list is the one the adapter's games are known
    # by; a title is only a request for the Four Score (the game reads the signature or it does not, and then plays as ever):
    # docs/UPGRADES.md says which titles were run on a dump.
    "Bomberman II", "Danny Sullivan's Indy Heat", "Gauntlet II", "Greg Norman's Golf Power", "Harlem Globetrotters",
    "Kings of the Beach", "M.U.L.E.", "Monster Truck Rally", "NES Play Action Football", "Nintendo World Cup",
    "R.C. Pro-Am II", "Rampart", "Roundball: 2-on-2 Challenge", "Smash T.V.", "Super Off Road", "Ivan 'Ironman' Stewart's Super Off Road",
    "A Nightmare on Elm Street", "Nightmare on Elm Street, A", "Top Players' Tennis", "Championship Bowling", "Arch Rivals",
)

def four_score_game(data: bytes, filename: str) -> bool:
    """The game reads the Four Score: its NES 2.0 header names the adapter (default expansion device 2), or its file name is
    the exact title of a game known to use it. A Zapper game never is one (port 2 holds the gun)."""
    if len(data) < 16 or data[:4] != b"NES" or zapper_game(data, filename):
        return False
    if data[7] & 12 == 8 and data[15] & 63 == 2:
        return True
    name = _title(filename)
    return any(name == _title(title) for title in FOUR_SCORE_TITLES)
