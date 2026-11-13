"""Atari ST: what the routes of a conversion are known to stop on, for the games where the stop is not the converter's (MIT).

A route that reaches a copy protection, or a game that EmuTOS cannot run, shows a picture that stays still. The conversion reports that
generically (`route_warnings`: the picture stopped changing early); this table says why for the dumps that were looked at, keyed by the
SHA-256 of the dump (the report's `source_identity`), each sentence something the reference run showed on the panel boots of 13 November
2026. It changes nothing a conversion does: no protection is answered, skipped or patched, and no route is chosen from it. Words about a
game, never its bytes.
"""
from __future__ import annotations

ROUTE_STOPS: dict[str, str] = {
    '996d23479230da6190cf749bb2752d0c844965b99deaadf84cd92f7b2bb37694':
        "Another World: the routes end on the game's own code-wheel check, a black screen that says ERROR after the entry the route makes; the answer is on the wheel that came "
        "with the game and no route gives it",
    '54da61f4622b4f5929f3dd6f8d4cff4ef37401bd0c128597bfc77132c2bfbcb5':
        "Carrier Command: the routes end on its manual-word protection, a screen that blanks after three wrong entries; the word is in the game's manual and no route gives it",
    '1b43d862698dc62fde2e2bd118ad860f8285f883c44d90aa47a42ead74685d8c':
        "Elite: the routes stop on its 'Novella Protection', which asks for a word of the Space Trader's Flight Training Manual (page 34, paragraph 4, line 1, word 1 on the "
        "routes of the panel run); the word is in the manual and no route gives it",
    '5cbe66c5d16e57c24b8e9102389605c9db6bbfba353e9c4b34d9869f567c02f1':
        "Operation Stealth: the routes stop on its colour-code check, which asks to refer to the card of colour codes; the answer is on that card and no route gives it",
    'c362193fffbcaf06b5b4c2af77effbfac01740c31ac0911599a4c6538ce507e9':
        "Leader Board: it starts by itself, shows its title and waits on 'INSERT SECURITY KEY', a hardware-key protection (the same with TOS 1.04 and with EmuTOS); "
        "the converter does not answer or skip it",
    '1f204778eb5298535821944c74f2cc2d1f853bdfbfad33de63924ba8abb77805':
        "Metro-Cross: on EmuTOS the screen stays blank; the game starts its own title with the player's own TOS 1.04 (Options > Atari ST)",
    '407ada38c7050f5d86557464a484f10149e7a279b35f0be8d5b398906bf0613c':
        "Trinity: the game says that its screen resolution is too low and exits; it asks for a higher resolution than the low-resolution colour screen this machine starts in",
    '1d04ed8256e85f30930c20cd9f9c4f07a8bf4aa89339cef334d8f14a22e93219':
        "Pharaoh III: on EmuTOS its program ends in a 'Panic: Bus Error'; it starts its menu with the player's own TOS 1.04 (Options > Atari ST)",
}


def route_stops(source_identity: str) -> list[str]:
    """The known stop of a dump, as the words `route_warnings` carries: [] for a dump that is not in the table."""
    note = ROUTE_STOPS.get(source_identity)
    return [f'known stop (panel of 13 November 2026): {note}'] if note else []
