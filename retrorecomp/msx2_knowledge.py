"""Numeric, ROM-free MSX2 paths for one exact cartridge (the MSX2's module of the shared base of paths).

The logic is the MSX's (`msx_knowledge`, whose functions take the machine as their `system` keyword): this module binds the MSX2 and exposes the
interface the sharing code reads of every schema 3 machine (`knowledge.schema3_module`). The MSX2 is in the experimental tier of the base, like
the MSX, and the whole sharing is withdrawn with one line (`path_profiles.EXPERIMENTAL_SHARED`).
"""
from __future__ import annotations

from functools import partial

from . import msx_knowledge as _family

SYSTEM = 'msx2'
CPU, ROM, BIOS, SHAPE, ROW_LIMIT, PATH_CAPS, RECORD_RULES = (_family.CPU, _family.ROM, _family.BIOS, _family.SHAPE, _family.ROW_LIMIT,
                                                             _family.PATH_CAPS, _family.RECORD_RULES)
UnknownFormat = _family.UnknownFormat

# What is the same for every machine of the family.
record_engine, record_digest, rows, entry_set, same_images = (_family.record_engine, _family.record_digest, _family.rows,
                                                              _family.entry_set, _family.same_images)
source_facts, words, text_of, received_words = _family.source_facts, _family.words, _family.text_of, _family.received_words

# What names the machine: the same functions with `system='msx2'`.
engine = partial(_family.engine, SYSTEM)
make_record = partial(_family.make_record, system=SYSTEM)
validate_record = partial(_family.validate_record, system=SYSTEM)
rebuild = partial(_family.rebuild, system=SYSTEM)
merged = partial(_family.merged, system=SYSTEM)
salvaged_record = partial(_family.salvaged_record, system=SYSTEM)
promote = partial(_family.promote, system=SYSTEM)
shared_rows = partial(_family.shared_rows, system=SYSTEM)
library_record = partial(_family.library_record, system=SYSTEM)
