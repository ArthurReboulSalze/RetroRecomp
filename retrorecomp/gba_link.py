"""The Game Boy Advance link cable in a multiplayer match: every cartridge may use it, and the roots a reviewed cartridge adds to make it native.

A cable match runs every console of the cable on every PC (the engine's own session, `GbaMultiplayerSession`: `native/gba_machine.cpp`). The code the
games run only while linked (a serial callback reached through a table, the code of the link menu) is never reached by a single-player run, so the
converter's own observation does not find it. Inside a session, an address with no generated function is run by the engine's interpreter one instruction
at a time and counted (the game's log line "link cable coverage: native entries missed N ... interpreted instructions M"); it does not stop the match.
So **every cartridge may use the cable** (two consoles); a reviewed row only raises the share of native code, it is no longer a condition.

This table is the reviewed answer, as data keyed by the cartridge's SHA-256 (never a condition on a game in code, docs/STANDARDS.md): the offsets
(| 1 for Thumb) of the function entries a two-console run found missing, and what that run proved.

A cartridge is **reviewed** when it is in this table: its roots are added to every conversion of it, the exported game says how many consoles the review
ran with (`RR_GBA_LINK_SEATS`) and its report says "link: ready" with the evidence. A cartridge that is not in it has the status "fallback" in its report:
the cable is available, its link-only code is interpreted and counted at match time, and nothing about it is claimed as proven. Nothing here is ROM
content: addresses and numbers only.

A row is made by the recipe of docs/GAME_BOY_ADVANCE.md ("The link cable in a match"): the generated code is built into the engine's own
two-console probe, run on a route, and every "native dispatch entry is missing" is added as a root until the route runs to its end with no miss and no
interpreted instruction. The evidence stored is that run's final cycle count (the engine's author documents the same figure for his own build of the game).
"""
from __future__ import annotations

from dataclasses import dataclass

THUMB = 1
ROM_BASE = 0x08000000
FALLBACK_SEATS = 2                 # the consoles any cartridge may put on the cable through the counted fallback (the profile's netplay_link_seats)


@dataclass(frozen=True)
class LinkSeed:
    """One cartridge's reviewed link data."""
    title: str                     # for the report only
    roots: tuple[int, ...]         # function entries as ROM offset | 1 for Thumb (the schema of `Observations.roots`)
    seats_tested: int              # the most consoles a run of the route had on the cable
    route: str                     # what the run reached, in words
    frames: int                    # frames of the route
    cycles: int                    # the guest cycle count the route ended on, on every console (the evidence)
    interpreted: int = 0           # interpreted instructions in that run (a row is accepted at 0 only)


def _roots(*addresses: int) -> tuple[int, ...]:
    """ARM-bus addresses of Thumb entries, as the ROM offsets with the Thumb flag."""
    return tuple(sorted((address - ROM_BASE) | THUMB for address in addresses))


# SHA-256 of the cartridge image (the key of every GBA record: gba_knowledge).
SEEDS: dict[str, LinkSeed] = {
    # Mario Kart: Super Circuit (USA), 9d327c03...: the two-console route of the engine's author (cold boot, Multi-Pak link, 50cc Mario GP, Toad and Yoshi, Mushroom Cup,
    # about twenty seconds of race) with empty Flash512 chips. 0802DB5C is the serial callback the engine's author found too (its descriptor pointer is at 080DE1B4).
    'aadc8b9f3c947ff6f610b6c8d7fddaaa9bea98b4bd43576df84f26c457ae1f90': LinkSeed(
        'Mario Kart: Super Circuit', _roots(0x0802DB5C, 0x0805F80C, 0x0805A790, 0x0805A758, 0x0805A79C, 0x0805A7AC, 0x080503B4, 0x080505D8),
        seats_tested=2, route='Multi-Pak link, 50cc Mario GP, two characters, Mushroom Cup, the first twenty seconds of the race',
        frames=4845, cycles=1360941120),
}


def seed(sha256: str) -> LinkSeed | None:
    return SEEDS.get(sha256)


def roots(sha256: str) -> set[int]:
    """The link roots of this cartridge (a set of offset | Thumb), empty when it is not reviewed."""
    found = SEEDS.get(sha256)
    return set(found.roots) if found else set()


def seats(sha256: str) -> int:
    """The REVIEWED seats: the consoles a run of the route had on the cable, 0 when the cartridge has no row. It is the game's `RR_GBA_LINK_SEATS`
    (what was reviewed), not what the cable allows: see `link_seats_allowed`."""
    found = SEEDS.get(sha256)
    return found.seats_tested if found else 0


def link_seats_allowed(sha256: str) -> int:
    """The consoles a match of this cartridge may put on the cable: two for any cartridge (the counted fallback), more when its review ran with more."""
    return max(FALLBACK_SEATS, seats(sha256))


def report(sha256: str) -> dict:
    """The conversion report's link entry: what is claimed, what it rests on and what is not claimed (the five measures stay apart)."""
    found = SEEDS.get(sha256)
    if not found:
        return {'status': 'fallback', 'seats': link_seats_allowed(sha256), 'roots_added': 0,
                'reason': 'the link cable is available through the counted interpreter fallback: no two-console route has been reviewed on this cartridge',
                'native_code': 'no route reviewed: the code only the cable runs is interpreted and counted at match time, shown in the game\'s log line '
                               '"link cable coverage: native entries missed N ... interpreted instructions M"',
                'cpu_fidelity': 'not established for this cartridge (the engine\'s own link model; the interpreter fallback is not compared with a reference here)',
                'hardware_fidelity': 'a model of the cable only (multiplayer and normal modes; no UART, no JOY bus, no radio); cable timing and errors unverified',
                'gameplay_validation': 'not established: no two-console route of this cartridge has been run',
                'physical_latency': 'unmeasured (a match plays on the delay tier)'}
    return {'status': 'ready', 'seats': link_seats_allowed(sha256), 'roots_added': len(found.roots),
            'native_code': {'route_frames': found.frames, 'interpreted_instructions': found.interpreted, 'dispatch_misses': 0,
                            'note': 'counted on the route only; code the route never reached is interpreted and counted at match time'},
            'cpu_fidelity': 'the engine\'s own link model (compared with mGBA by its author); not compared again here',
            'hardware_fidelity': 'a model of the cable only (multiplayer and normal modes; no UART, no JOY bus, no radio); cable timing and errors unverified',
            'gameplay_validation': 'the route reached ' + found.route + '; no play trial of ours yet',
            'physical_latency': 'unmeasured (a match plays on the delay tier)',
            'route_cycles': found.cycles}
