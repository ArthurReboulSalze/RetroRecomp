"""The Super Nintendo games built for the Super Multitap, as reviewed data keyed by the dump (never by a condition in code).

A Super Multitap in console port 2 gives a game up to four pads (five on a real console; the host kit seats four players). The
engine's multitap is not transparent: with a tap in port 2 every game reads its pads another way (its automatic read comes from a
latched copy, and a game of two pads ends in another state), so a tap is plugged only for a game that is listed here, and only in
a multiplayer session of three or four seats (the player of two pads, alone or in a room of two, plays as before).

Each entry is the SHA-256 of the dump without a copier header (`Rom.sha256`), the title as the catalogue names it, the pads the game
uses with a tap (what its own menus offer; a pad the game does not read stays idle), and the source of the claim. **Evidence level:**
the players come from third-party lists of the console's games (named in `source`); nothing here was verified by playing the
game with four pads: the engine says itself that no multitap title has been run, and this project has not run one with four
people. The conversion report says so (`qualification_scope.controls`).
"""
from __future__ import annotations

MULTITAP_GAMES: dict[str, dict] = {
    # Barkley Shut Up and Jam! (USA)
    'fe1ad128313b2b9a47f89cf0d95d4c0cc2cb35a817ac5d915ee6c4d98d47d675': {
        'title': 'Barkley Shut Up and Jam!', 'pads': 4, 'source': 'a community list of Super Multitap games (MiSTer forum thread)'},
    # Capcom's Soccer Shootout (USA)
    'fd5761f9dd1f2b87ad11df6085046d0dfcdc3a79139263e47b0cff707966ba51': {
        'title': "Capcom's Soccer Shootout", 'pads': 4, 'source': 'a community list of Super Multitap games (MiSTer forum thread)'},
    # Secret of Mana (USA): three players on a multitap
    '4c15013131351e694e05f22e38bb1b3e4031dedac77ec75abecebe8520d82d5f': {
        'title': 'Secret of Mana', 'pads': 3, 'source': 'the game\'s manual and its published descriptions (three players with a multitap)'},
}


def multitap_pads(sha256: str) -> int:
    """The pads a listed game uses with a Super Multitap, 0 for a game that is not listed."""
    return int(MULTITAP_GAMES.get(sha256, {}).get('pads', 0))
