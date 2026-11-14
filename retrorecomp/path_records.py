"""What every schema 3-only machine does with its path records, whatever the machine: one copy.

A machine of the experimental tier of the base keeps its paths as schema 3 documents (`path_profiles`): numbers about the player's own
images, never their bytes. Checking a document against the machine's own rules, assembling one from rows and reading its rows back are the
machine's; naming a record by its canonical text, comparing two records, uniting them, keeping the one built by the current engine, reading
the player's library record and gathering the received records of the three banks are the same for every machine, and are here.

A machine either builds one `PathRecords` with its names and three functions of its own, `validate_record(record, identity)`,
`assemble(identity, sources, hints, core)` and `hints(record)` (every path as `(kind name, row)`, the form `entry_set` gives), and binds the
methods in its knowledge module (the interface `knowledge.schema3_module` reads); or subclasses it and overrides those methods, and the few
steps where its records have more to say (`_union`, `rebuild`): the 68000 computers' `m68k_media_knowledge.MediaKnowledge` does, for its
firmware rows. Nothing below names a machine. Written on 14 November 2026; the other schema 3 machines keep their own copies until they move
here with identical results (a follow-up).
"""
from __future__ import annotations

import hashlib
import json
from typing import Callable, Iterable

from .path_profiles import UnknownFormat

LIBRARY_RECORD_BYTES = 16 * 1024 * 1024


def record_digest(record) -> str:
    """SHA-256 of a record's canonical text: how a report names the record a conversion made."""
    return hashlib.sha256(json.dumps(record, sort_keys=True, separators=(',', ':')).encode('ascii')).hexdigest()


class PathRecords:
    """The schema 3 records of one machine. `primary` is the source whose facts (size and SHA-256) say two records are about the same images,
    or a function giving those facts from a record's sources (a machine whose images are a cartridge or a set of disks); `cpu` the section
    whose `core` is the engine a record was built with; `engine()` the current engine of this converter. The three functions may be left
    out by a subclass that overrides the methods of the same names."""

    def __init__(self, *, system: str, cpu: str, primary: str | Callable[[dict], object], engine: Callable[[], str],
                 validate_record: Callable | None = None, assemble: Callable | None = None, hints: Callable | None = None):
        self.system, self.cpu, self.primary = system, cpu, primary
        self._engine, self._validate, self._assemble_record, self._hints = engine, validate_record, assemble, hints

    # --- What the machine supplies -------------------------------------------------------------------------

    def engine(self) -> str:
        return self._engine()

    def validate_record(self, record, identity: str | None = None) -> dict:
        """The machine's strict check (the schema 3 validator, then its own rules), or ValueError."""
        return self._validate(record, identity)

    def assemble(self, identity: str, sources: dict, hints: Iterable, core: str) -> dict:
        """The document of `identity` with these sources holding exactly `hints` (`(kind name, row)` pairs), built by `core`."""
        return self._assemble_record(identity, sources, hints, core)

    def hints(self, record) -> Iterable:
        """Every path of a validated record as `(kind name, row)`."""
        return self._hints(record)

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
            return set(self.hints(record))
        except (KeyError, TypeError, ValueError):
            return set()

    def same_images(self, first: dict, second: dict) -> bool:
        """Two records of the same game point into the very same images, with the same layout."""
        one, two = first['identity'], second['identity']
        images = self.primary if callable(self.primary) else (lambda sources: sources.get(self.primary))
        return (first['game'] == second['game'] and one.get('layout') == two.get('layout')
                and images(one['sources']) == images(two['sources']))

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
        return self._union(identity, first, second)

    def _union(self, identity: str, first: dict, second: dict) -> dict:
        """The union of two records of the same images and engine (`merged` has checked that)."""
        return self.validate_record(self.assemble(identity, first['identity']['sources'], self.entry_set(first) | self.entry_set(second),
                                                  self.record_engine(first)), identity)

    def salvaged_record(self, identity: str, record) -> dict | None:
        """A received record, or None. A record is all or nothing: it is checked as a whole (its rows are numbers about images whose hashes
        it states, there is no row worth saving from a record that fails)."""
        try:
            return self.validate_record(record, identity)
        except (ValueError, TypeError, KeyError, AttributeError):
            return None

    def gathered_rows(self, identity: str, expand: Callable[[dict], tuple[list, dict]], *, qualified=None, imported=None, library=None,
                      validate: bool = True, unique: bool = True) -> tuple[list, dict]:
        """(rows, info): what the qualified bank (used only for the engine that qualified it), the player's own library record and the
        imported bank (other players' paths, whatever their engine, which guide discovery and are rechecked like everything else) give for
        this game, each record turned into build input by the machine's `expand`, which reads the player's own images and returns
        (rows, left): `left` names what of the record it could not use and why. `expand` raises ValueError when the record is not for these
        images (`UnknownFormat` for a format this converter cannot read). With `validate`, each record is checked first (else `expand`
        checks it); with `unique`, each row is kept once. The rows are build input only, in that order: never added to the private
        observations a conversion keeps. `info` says what each source gave and what was ignored and why."""
        rows_out, seen = [], set()
        info = {'qualified': 0, 'library': 0, 'imported': 0, 'ignored': {}}
        current = self.engine()
        for name, record in (('qualified', qualified), ('library', library), ('imported', imported)):
            if not record:
                continue
            try:
                if name == 'qualified' and self.record_engine(record) != current:
                    info['ignored'][name] = 'another engine revision'
                    continue
                if validate:
                    record = self.validate_record(record, identity)
                expanded, left = expand(record)
            except UnknownFormat:
                info['ignored'][name] = 'unknown record format'
                continue
            except ValueError as error:
                info['ignored'][name] = str(error)[:120]
                continue
            for key, reason in left.items():
                info['ignored'][f'{name}_{key}'] = reason
            info[name] = len(expanded)
            for row in expanded:
                if not unique:
                    rows_out.append(row)
                elif row not in seen:
                    seen.add(row)
                    rows_out.append(row)
        return rows_out, info

    def library_record(self, identity: str, name: str = 'compilation.json') -> dict | None:
        """This player's own record: the paths that fresh, verified conversions reached (the machine's conversion writes it into the game's
        summary, `<library>/<system>/<game>/compilation.json`, or into the file `name` of that folder), or None."""
        from .library import library_root
        path = library_root(self.system) / identity / name
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
