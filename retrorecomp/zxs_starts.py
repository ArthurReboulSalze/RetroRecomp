"""Reviewed start data of ZX Spectrum snapshots (MIT): what the generic start variants of retrorecomp/zxs_routes.py cannot find, keyed by
the snapshot's SHA-256 (the file as read, ZIP member or not: zxs_snapshot.Snapshot.sha256). Numbers and key names about inputs only,
never bytes of a game. Each entry was found on the reference interpreter and is checked by the conversion like any route: the play
route must stay alive and equal the reference.

STARTS: the presses that start the game, (frame, key name) pairs with the names of zxs_routes.KEYS and FIRE for pad 1's fire; they
replace the search of the start variants, and the report names them (route_start.rule).

ROUTE_STOPS: snapshots whose routes are known to stop short of play for a reason no input changes; the report carries the note
(route_stop), and nothing is hidden: the routes are played and compared as usual.

JOYSTICKS: the joystick interface a game's own menu uses when the snapshot's header says another; the conversion reads the
snapshot with it (pads, routes, the Kempston port), and the report names it (zxs_checks.joystick_rule).

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
    # Match Day II (1987, Ocean), 22 November 2026: ENTER leaves the title for « Select joystick » (Keys, Kempston, Fuller). A held
    # key moves the cursor at once, then about every ten frames: these three SPACE holds move it 3, 2 and 2 places, seven in all,
    # to « Kempston joystick » (JOYSTICKS below; seen on the reference, which is deterministic), then ENTER three times (the
    # choice, « 1 Player Matchday », « First half ») starts a match. The variant search keeps the menu reached by two ENTERs:
    # the match's walk shows few pictures the run without input does not, the menu more.
    'b4b188edc2c5b03aef01bd593721f8807aa403510c439df14d66dcd4e5820c86': {
        'presses': ((150, 'ENTER'), (390, 'SPACE'), (510, 'SPACE'), (630, 'SPACE'), (780, 'ENTER'), (930, 'ENTER'),
                    (1080, 'ENTER')),
        'why': 'ENTER, three SPACE holds to the Kempston joystick, then ENTER three times reaches a match (the choice, 1 Player '
               'Matchday, First half); the search keeps the menu',
    },
}

JOYSTICKS: dict[str, dict] = {
    # The joystick interface a game's own menu uses when the snapshot's header says another (zxs_snapshot.JOYSTICKS): the pads and
    # the routes then go to that interface, and a Kempston answers at port 1Fh. Found on the reference by holding each key and each
    # Kempston bit in play and comparing the pictures with the run without it.
    # Head over Heels (1987, Ocean, 128K), 22 November 2026: the header says cursor, but in play the game reads 6 7 8 9 0 as
    # left, right, down, up and fire (Interface 2, the 6-0 port) beside Q A O P and SPACE; on the cursor keys the pad's left (5)
    # does nothing and its down (6) turns left.
    'cc3d3e80e971f6d3392d07a80dd384d067b564894a3f625568a3bfa2cd034e01': {
        'joystick': 'sinclair-right',
        'why': 'in play the game reads 6-0 as Interface 2 (6 left, 7 right, 8 down, 9 up, 0 fire); the header says cursor',
    },
    # Match Day II (1987, Ocean), 22 November 2026: its start data picks « Kempston joystick » in the game's menu; without a
    # Kempston answering at port 1Fh the menu reads every direction held and waits for ever.
    'b4b188edc2c5b03aef01bd593721f8807aa403510c439df14d66dcd4e5820c86': {
        'joystick': 'kempston',
        'why': 'the start data picks the Kempston joystick in the game\'s menu; the header says cursor (keys)',
    },
}

ROUTE_STOPS: dict[str, str] = {
    # Elite (1985, Firebird), 21 November 2026: the snapshot starts inside the game's own decryption (LDI chains, interrupts off);
    # about 50 frames in, the program halts with interrupts disabled and never runs again, on the reference as natively, so its
    # « Press Space, Commander » never animates. Suspected at first: a protection on the machine's timing; on 22 November 2026,
    # with the ULA's contention modelled, it halts the same way (40,981 instructions), and again with the floating bus: the cause
    # is neither. Open: a snapshot taken inside the loader's decryption (another dump to try).
    '72980b5cdf6057ec112536b376fe64878d55d761bc19875f0535a92c216a7b7b':
        'the program halts with interrupts disabled about 50 frames after the snapshot, inside its own decryption, with or '
        'without the ULA contention and the floating bus; open: a snapshot taken inside the loader; the routes stay on its '
        'title',
}


def start_for(identity: str):
    """The reviewed presses of the snapshot `identity` (a tuple of (frame, key)) and why, or None."""
    entry = STARTS.get(identity)
    return (tuple(entry['presses']), entry['why']) if entry else None


def joystick_for(identity: str):
    """The reviewed joystick interface of the snapshot `identity` (one of zxs_snapshot.JOYSTICKS) and why, or None."""
    entry = JOYSTICKS.get(identity)
    return (entry['joystick'], entry['why']) if entry else None


def route_stop(identity: str) -> str | None:
    """The reviewed note of a snapshot whose routes stop short of play, or None."""
    return ROUTE_STOPS.get(identity)
