"""Comparison of what a vector replay saw with the recorded list of known deviations, shared by the replays of the groups fixture.

`tools/megadrive_groups_selftest.py` (per group and per kind: state, clocks, bus) and `tools/cps1_vector_selftest.py`, whose
`group_problems` the Neo Geo and the X68000 replays use too (per group: native state, reference state, paths), keep their lists as
`{group: {kind: count}}`. The list is exact: a group that differs and is not listed fails, a listed group that no longer differs
fails, and so does a count that changed in either direction, so a fix has to shrink the list and a regression is refused.
A tool of the repository only: no game, no stamp.
"""
from __future__ import annotations


def differences(observed: dict, known: dict) -> list[str]:
    """One line per group whose observed counts are not exactly the recorded ones (empty: the list is exact)."""
    found = []
    for group in sorted(set(observed) | set(known)):
        if observed.get(group, {}) != known.get(group, {}):
            found.append(f'{group}: seen {observed.get(group, {}) or "none"}, listed {known.get(group, {}) or "none"}')
    return found
