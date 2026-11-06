"""Numeric, ROM-free CPS-2 paths for one exact romset (the CPS-2's module of the shared base of paths).

The logic is the CPS-1's (`cps1_knowledge`, which takes the board as its `system` keyword): the 68000 program is translated whole, so the only
paths a game has are the instructions it ran from work RAM and from sound RAM, turned into numbers about the player's own images. The CPS-2's
68000 rows point into the **decrypted** program image (the one the translated code is built from); the decryption key is the player's own and is
never part of a record. This module binds the board and exposes the interface the sharing code reads of every schema 3 machine
(`knowledge.schema3_module`): the CPS-2 is in the experimental tier of the base, like the CPS-1 and the X68000, and the whole sharing is
withdrawn with one line (`path_profiles.EXPERIMENTAL_SHARED`).
"""
from __future__ import annotations

from functools import partial

from . import cps1_knowledge as _board

SYSTEM = 'cps2'
FORMAT, FORMATS, ROW_LIMIT, PATH_CAPS = _board.FORMAT, _board.FORMATS, _board.ROW_LIMIT, _board.PATH_CAPS
UnknownFormat = _board.UnknownFormat

# What is the same for both boards.
record_engine, record_digest, rows, entry_set, same_images = (_board.record_engine, _board.record_digest, _board.rows, _board.entry_set,
                                                              _board.same_images)
source_facts, translate, text_digest = _board.source_facts, _board.translate, _board.text_digest

# What names the board: the same functions with `system='cps2'`.
engine = partial(_board.engine, SYSTEM)
engine_parts = partial(_board.engine_parts, SYSTEM)
images_from_board = partial(_board.images_from_board, system=SYSTEM)
make_record = partial(_board.make_record, system=SYSTEM)
validate_record = partial(_board.validate_record, system=SYSTEM)
rebuild = partial(_board.rebuild, system=SYSTEM)
merged = partial(_board.merged, system=SYSTEM)
salvaged_record = partial(_board.salvaged_record, system=SYSTEM)
promote = partial(_board.promote, system=SYSTEM)
expanded_rows = partial(_board.expanded_rows, system=SYSTEM)
shared_rows = partial(_board.shared_rows, system=SYSTEM)
library_record = partial(_board.library_record, system=SYSTEM)
