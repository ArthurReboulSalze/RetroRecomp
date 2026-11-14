"""What every schema 3-only machine does with its path records, whatever the machine: one copy.

A machine of the experimental tier of the base keeps its paths as schema 3 documents (`path_profiles`): numbers about the player's own
images, never their bytes. Checking a document against the machine's own rules, assembling one from rows and reading its rows back are the
machine's; naming a record by its canonical text, comparing two records, uniting them, keeping the one built by the current engine, reading
the player's library record and gathering the received records of the three banks are the same for every machine, and are here.

A machine builds one `PathRecords` (or a subclass) with its names and three functions of its own, and its knowledge module binds the methods
(the interface `knowledge.schema3_module` reads): `validate_record(record, identity)`, `assemble(identity, sources, hints, core)` and
`hints(record)` (every path as `(kind name, row)`, the form `entry_set` gives). Nothing below names a machine. Written for the MSX and the
MSX2 (14 November 2026); the other schema 3 machines keep their own copies until they move here with identical results (a follow-up).
"""
from __future__ import annotations

import hashlib
import json
from typing import Callable, Iterable

LIBRARY_RECORD_BYTES = 16 * 1024 * 1024


def record_digest(record) -> str:
    """SHA-256 of a record's canonical text: how a report names the record a conversion made."""
    return hashlib.sha256(json.dumps(record, sort_keys=True, separators=(',', ':')).encode('ascii')).hexdigest()


class PathRecords:
    """The schema 3 records of one machine. `primary` is the source whose facts (size and SHA-256) say two records are about the same images;
    `cpu` the section whose `core` is the engine a record was built with; `engine()` the current engine of this converter."""

    def __init__(self, *, system: str, cpu: str, primary: str, engine: Callable[[], str], validate_record: Callable,
                 assemble: Callable, hints: Callable):
        self.system, self.cpu, self.primary = system, cpu, primary
        self._engine, self._validate, self._assemble, self._hints = engine, validate_record, assemble, hints

    # --- What the machine supplies -------------------------------------------------------------------------

    def engine(self) -> str:
        return self._engine()

    def validate_record(self, record, identity: str | None = None) -> dict:
        """The machine's strict check (the schema 3 validator, then its own rules), or ValueError."""
        return self._validate(record, identity)

    def assemble(self, identity: str, sources: dict, hints: Iterable, core: str) -> dict:
        """The document of `identity` with these sources holding exactly `hints` (`(kind name, row)` pairs), built by `core`."""
        return self._assemble(identity, sources, hints, core)

    # --- The same for every machine ----------------------------------------------------------------------------

    def record_engine(self, record) -> str:
        """The `cores` string a record was built with ('' when it is not a record of the machine)."""
        try:
            return record['cpus'][self.cpu]['core']
        except (KeyError, TypeError):
            return ''

    def entry_set(self, record) -> set:
        """Every path of a record as comparable tuples (what the base compares between players)."""
        if not isinstance(record, dict):
            return set()
        try:
            return set(self._hints(record))
        except (KeyError, TypeError, ValueError):
            return set()

    def same_images(self, first: dict, second: dict) -> bool:
        """Two records of the same game point into the very same primary image, with the same layout."""
        one, two = first['identity'], second['identity']
        return (first['game'] == second['game'] and one.get('layout') == two.get('layout')
                and one['sources'].get(self.primary) == two['sources'].get(self.primary))

    def rebuild(self, skeleton: dict, hints, *, core: str | None = None) -> dict:
        """A record of the skeleton's images holding exactly `hints` (as `entry_set` names them)."""
        return self.validate_record(self.assemble(skeleton['game'].split(':', 1)[1], skeleton['identity']['sources'], hints,
                                                  core or self.record_engine(skeleton)))

    def merged(self, identity: str, first: dict, second: dict) -> dict:
        """Union of two records of one game. Records of another engine or other images never mix: the one built by the current engine is
        kept, else the first. ValueError when the union exceeds a bound."""
        if not second:
            return first
        if not first:
            return second
        if not self.same_images(first, second) or self.record_engine(first) != self.record_engine(second):
            current = self.engine()
            return second if self.record_engine(second) == current and self.record_engine(first) != current else first
        return self.validate_record(self.assemble(identity, first['identity']['sources'], self.entry_set(first) | self.entry_set(second),
                                                  self.record_engine(first)), identity)

    def salvaged_record(self, identity: str, record) -> dict | None:
        """A received record, or None: it is checked as a whole (its rows are numbers about images whose hashes it states)."""
        try:
            return self.validate_record(record, identity)
        except (ValueError, TypeError, KeyError, AttributeError):
            return None

    def shared_rows(self, identity: str, expand: Callable[[dict], Iterable], *, qualified=None, imported=None, library=None) -> tuple[list, dict]:
        """(rows, info): what the qualified bank (used only for the engine that qualified it), the player's own library record and the
        imported bank (other players' paths) give for this game, each record turned into build input by the machine's `expand` (which reads
        the player's own images; ValueError when the record is not for them). The rows are build input only, in that order, each once. `info`
        says what each source gave and what was ignored and why."""
        rows_out, seen = [], set()
        info = {'qualified': 0, 'library': 0, 'imported': 0, 'ignored': {}}
        current = self.engine()
        for name, record in (('qualified', qualified), ('library', library), ('imported', imported)):
            if not record:
                continue
            try:
                record = self.validate_record(record, identity)
                if name == 'qualified' and self.record_engine(record) != current:
                    info['ignored'][name] = 'another engine revision'
                    continue
                expanded = list(expand(record))
            except ValueError as error:
                info['ignored'][name] = str(error)[:120]
                continue
            info[name] = len(expanded)
            for row in expanded:
                if row not in seen:
                    seen.add(row)
                    rows_out.append(row)
        return rows_out, info

    def library_record(self, identity: str) -> dict | None:
        """This player's own record: the paths that verified conversions reached (the machine's conversion writes it into the game's summary,
        `<library>/<system>/<game>/compilation.json`), or None."""
        from .library import library_root
        path = library_root(self.system) / identity / 'compilation.json'
        try:
            with path.open('rb') as stream:
                raw = stream.read(LIBRARY_RECORD_BYTES + 1)
            if len(raw) > LIBRARY_RECORD_BYTES:
                return None
            data = json.loads(raw)
            if data.get('system') != self.system or data.get('game') != identity or not data.get('fresh_reference_passed'):
                return None
            return self.validate_record(data['record'], identity)
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            return None

    def write_library_record(self, identity: str, record: dict, **fields) -> None:
        """The game's summary in the player's library, holding `record` (written once every check of a conversion passed)."""
        from .library import atomic_json, library_root
        summary = library_root(self.system) / identity / 'compilation.json'
        summary.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(summary, {'schema': 1, 'system': self.system, 'game': identity, 'rom_sha256': identity,
                              'private_development_only': True, 'fresh_reference_passed': True, 'record': record,
                              'cores': self.engine(), **fields})
