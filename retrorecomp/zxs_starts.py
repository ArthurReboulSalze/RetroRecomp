"""Reviewed start data of ZX Spectrum snapshots (MIT): what the generic start variants of retrorecomp/zxs_routes.py cannot find, keyed by
the snapshot's SHA-256 (the file as read, ZIP member or not: zxs_snapshot.Snapshot.sha256). Numbers and key names about inputs only,
never bytes of a game. Each entry was found on the reference interpreter and is checked by the conversion like any route: the play
route must stay alive and equal the reference.

STARTS: the presses that start the game, (frame, key name) pairs with the names of zxs_routes.KEYS and FIRE for pad 1's fire; they
replace the search of the start variants, and the report names them (route_start.rule).

ROUTE_STOPS: snapshots whose routes are known to stop short of play for a reason no input changes; the report carries the note
(route_stop), and nothing is hidden: the routes are played and compared as usual.

Add an entry only after the generic variants were tried (docs/ZX_SPECTRUM.md, section 4), with the date and what was seen.
"""
from __future__ import annotations

STARTS: dict[str, dict] = {
    # Robocop (1988, Ocean, 128K), 21 November 2026: a key turns the high scores into the control menu (1 Keyboard, 2 Sinclair,
    # 3 Kempston, 4 Define keys); 3 again picks the Kempston (the snapshot's joystick) and starts the « Prime Directives » screen,
    # which takes SPACE only once its text is typed (from about frame 1,000); the street level follows.
    'a2771bb47fe6dc0fe470797023a5476ea8f919a4caa5da62b7ceb6e5d8897214': {
        'presses': ((150, '3'), (390, '3'), (1040, 'SPACE')),
        'why': 'the control menu wants its joystick key twice, then SPACE once the Prime Directives are typed',
    },
    # Arkanoid (1987, Imagine), 22 November 2026: ENTER leaves the title, fire starts the story, which ends by itself on Round 1. The
    # variant search keeps ENTER alone: on Round 1 the ball waits for fire, which the walk's first part never presses, so the
    # picture stops and the rule takes the moving demo instead.
    '258b36fb1de2c44110975289f60798790217d01e1f291101681971ade52d8d44': {
        'presses': ((150, 'ENTER'), (390, 'FIRE')),
        'why': 'ENTER leaves the title, fire starts the story, Round 1 follows; the ball then waits for fire, so the search keeps the demo',
    },
    # Match Day II (1987, Ocean), 22 November 2026: ENTER four times (title, joystick choice, « 1 Player Matchday », « First half »)
    # starts a match. The variant search keeps the menu reached by two: the match's walk shows few pictures the run without
    # input does not, the menu more.
    'b4b188edc2c5b03aef01bd593721f8807aa403510c439df14d66dcd4e5820c86': {
        'presses': ((150, 'ENTER'), (390, 'ENTER'), (630, 'ENTER'), (870, 'ENTER')),
        'why': 'ENTER four times reaches a match (title, joystick, 1 Player Matchday, First half); the search keeps the menu',
    },
}

ROUTE_STOPS: dict[str, str] = {
    # Elite (1985, Firebird), 21 November 2026: the snapshot starts inside the game's own decryption (LDI chains, interrupts off);
    # about 50 frames in, the program halts with interrupts disabled and never runs again, on the reference as natively, so its
    # « Press Space, Commander » never animates. Suspected: a protection that depends on the machine's timing (the ULA's
    # contention is not modelled yet); to be checked again once it is.
    '72980b5cdf6057ec112536b376fe64878d55d761bc19875f0535a92c216a7b7b':
        'the program halts with interrupts disabled about 50 frames after the snapshot, inside its own decryption: suspected '
        'timing-dependent protection (ULA contention is not modelled yet); the routes stay on its title',
}


def start_for(identity: str):
    """The reviewed presses of the snapshot `identity` (a tuple of (frame, key)) and why, or None."""
    entry = STARTS.get(identity)
    return (tuple(entry['presses']), entry['why']) if entry else None


def route_stop(identity: str) -> str | None:
    """The reviewed note of a snapshot whose routes stop short of play, or None."""
    return ROUTE_STOPS.get(identity)
