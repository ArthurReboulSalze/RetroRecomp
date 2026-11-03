"""State rules of the MC68000 steps that the Neo Geo, the CPS-1 and the X68000 build from the pinned `m68k_interp.c`.

The Mega Drive corrected three instructions of that text that the independent vectors of `tests/fixtures/m68k-groups`
showed wrong (`retrorecomp/megadrive_rules.py`, 1.6.7). The Neo Geo, the CPS-1 and the X68000 translate the same text into
their native steps, so they differed from the vectors on the same instructions. They apply the same three rules, taken from
that module (one copy of the text, not a second one): `LINK A7` pushes the value A7 had before the decrement, `UNLK A7` ends
with the long it popped, and `NEGX` leaves Z alone when the result is zero. The Mega Drive's own rules are not touched, so its
stamp and its generated code do not move. The other half of `LINK A7` is Musashi, their reference path
(`retrorecomp/musashi_fixes.py`): both must agree, or a game that runs the instruction would be refused.

Applied after `m68000.adapt_semantics`, by the three machines' generators; each profile lists the group `m68000_state_rules`.
"""
from __future__ import annotations

from .conversion_common import replace_counted
from .core import ConversionError
from .megadrive_rules import STATE_RULES

# STATE_RULES = (RTR, LINK A7, UNLK A7, NEGX): the RTR rule is not applied here, those machines run RTR on Musashi.
RULES = {'LINK A7': STATE_RULES[1], 'UNLK A7': STATE_RULES[2], 'NEGX': STATE_RULES[3]}


def adapt_state_rules(source: str) -> str:
    """`source` (the pinned interpreter text after `adapt_semantics`) with the three state rules; a text that moved raises."""
    for what, (old, new) in RULES.items():
        source = replace_counted(source, old, new, error=lambda old, what=what: ConversionError(
            f'Pinned 68000 interpreter changed; the {what} state rule is refused ({old.strip().splitlines()[0][:60]}).'))
    return source
