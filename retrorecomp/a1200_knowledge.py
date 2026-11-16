"""Numeric, ROM-free Amiga 1200 paths for one exact WHDLoad install (the Amiga 1200's module of the shared base of paths).

The logic is the Amiga 500's (`amiga_knowledge`, the common part `m68k_media_knowledge`): spans of the install's files where the observed RAM
code sits as it is, and instructions of the player's own Kickstart, as numbers about the player's own images, never a byte. What is the Amiga
1200's: its section (`m68k` on the `a1200` map), the 68EC020's instruction lengths, and its Kickstart 3.x (512 KiB at $F80000). The
paths come from the fresh reference runs of a conversion that passed and from the instructions the player's own game ran on the
interpreter during play (F12, kind 22) that the same conversion made native (`amiga_conversion.promoted_record`).

This module binds the Amiga 1200's knowledge (`amiga_knowledge.KNOWLEDGE_A1200`) and exposes the interface the sharing code reads of every
schema 3 machine (`knowledge.schema3_module`). The Amiga 1200 is in the experimental tier of the base from 1.7.9 (the owner's decision of
16 November 2026), withdrawn with the rest of that tier by one line (`path_profiles.EXPERIMENTAL_SHARED`).
"""
from __future__ import annotations

from functools import partial

from . import amiga_knowledge as _amiga

SYSTEM = _amiga.SYSTEM_A1200
KNOWLEDGE = _amiga.KNOWLEDGE_A1200
FORMAT, FORMATS, PATH_CAPS, RECORD_FILE = _amiga.FORMAT, _amiga.FORMATS, dict(_amiga.PATH_CAPS), _amiga.RECORD_FILE
INSTALL, KICKSTART = _amiga.INSTALL, _amiga.KICKSTART
UnknownFormat = _amiga.UnknownFormat
# The engine identity is the Amiga 500's (`amiga_knowledge.engine`): one vAmiga pin, one set of native files, one GENERATOR_REVISION for both models.
engine, text_digest, record_digest = _amiga.engine, _amiga.text_digest, _amiga.record_digest

# What the site's builder reads (`amiga_knowledge.RECORD_RULES` has the keys): the Amiga 500's rules with the Amiga 1200's Kickstart window.
RECORD_RULES = {
    'layout': [],
    'sources': {'only': [INSTALL, KICKSTART], 'required': [INSTALL], 'hashed': True, 'game': None},
    'paths': {'m68k': {'spans': {'src': INSTALL, 'window': [0, _amiga.RAM_LIMIT], 'requires': INSTALL},
                       'ram_code': {'src': KICKSTART, 'window': list(_amiga.KICKSTART_3X_WINDOW), 'requires': KICKSTART}}},
}

record_engine, source_facts = KNOWLEDGE.record_engine, KNOWLEDGE.source_facts
make_record, validate_record, rows, entry_set = KNOWLEDGE.make_record, KNOWLEDGE.validate_record, KNOWLEDGE.rows, KNOWLEDGE.entry_set
same_images, rebuild, merged, salvaged_record = KNOWLEDGE.same_images, KNOWLEDGE.rebuild, KNOWLEDGE.merged, KNOWLEDGE.salvaged_record
translate, promote, expanded_rows, shared_rows = KNOWLEDGE.translate, KNOWLEDGE.promote, KNOWLEDGE.expanded_rows, KNOWLEDGE.shared_rows
library_record = partial(_amiga.library_record, system=SYSTEM)
