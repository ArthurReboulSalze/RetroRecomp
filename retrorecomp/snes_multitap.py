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
    # The Super Bomberman series: the original takes four players with a tap, the later ones up to five (the host kit seats four, so
    # the tap's fifth pad stays unplugged). Super Bomberman 4 is the dump of the English translation (a patched ROM, its own SHA-256).
    # Source: the Wikipedia pages of the games ("Super Bomberman", "Super Bomberman 4", "Super Bomberman 5") and the one of the Super
    # Multitap, which names Super Bomberman as the game released with it; the MiSTer thread above lists Super Bomberman 2 and 3.
    '4efab3f49cbe91ec77b6cba747ddfedfdc0b080c755a8b6ba51234f0676c000f': {
        'title': 'Super Bomberman', 'pads': 4, 'source': 'Wikipedia (the game and the Super Multitap pages)'},
    '0a4b4a783a7faf6ada3e1326ecf85de77e8c2a171659b42a78a1fae43f806ca6': {
        'title': 'Super Bomberman 2', 'pads': 4, 'source': 'a community list of Super Multitap games (MiSTer forum thread) and Wikipedia'},
    '4bc9ae0ba1313bb35e4c5b71cc7962774f599b3e09efdaf2fa1d574ba8d5e153': {
        'title': 'Super Bomberman 4 (English translation of the Japanese game)', 'pads': 4, 'source': 'Wikipedia (the game page: up to five players)'},
    'b8ea7591bd957c67cc27955e00609f1d659db9ac91a9bd321750de2ab4d1d676': {
        'title': 'Super Bomberman 5 (Japan)', 'pads': 4, 'source': 'Wikipedia (the game page: up to five players)'},
}


def multitap_pads(sha256: str) -> int:
    """The pads a listed game uses with a Super Multitap, 0 for a game that is not listed."""
    return int(MULTITAP_GAMES.get(sha256, {}).get('pads', 0))
