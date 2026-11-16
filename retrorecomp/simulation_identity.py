"""The simulation identity of a conversion: do two exports of one game compute the same frames?

Two players can only play one converted game together when their executables compute the same thing from
the same inputs. The game stamp cannot say so: `freshness.request_parts` hashes the cover, the title and the
target system with it, and the knowledge stamp leaves out the player's own library, which also shapes the
generated code. This module is the one place where the identity is computed, for every machine.

What is hashed (and nothing else):

* the **engine content** of the machine (`engine_content`), the same for every game of one source tree whatever
  Python runs the converter: the game-role inputs of the machine that are files (native/, assets, profiles; the
  manifest of `stamp_inputs`, each read through `compilation_inputs.input_bytes`, so text has LF line ends), in
  manifest order, and the pinned revisions of the upstreams the machine builds from (`upstreams.MACHINE_UPSTREAMS`),
  as text. The game stamp is not used: it fingerprints the converter's modules by their bytecode, which differs
  from one Python version to the next, and a Windows and a Linux release are not built with the same one. What a
  change of the generators does to a game is in the generated sources below;
* the **dump**, by its SHA-256 (the key the batch gives the game), never its bytes;
* the **declared run-changing options**: `COMMON_RUN_OPTIONS` and the profile's option keys marked
  `changes_run`, each with its default when the request names none;
* the **generated sources as they are compiled**: the per-game files the machine's profile lists
  (`SystemProfile.simulation_sources`), found in the game's build project, in the order of their relative
  paths, with line ends normalised to LF.

Never hashed: the cover or any picture, the title, the language, the export folder or any absolute path, a
date, the converter's version text, the target system, and everything on the host side (the files below
native/hostkit and the other host inputs are compared apart, through the host stamp). A per-game file that
mixes run settings with the title is listed with the lines to leave out (`SimulationSource.drop`), or with
the only values to take (`SimulationSource.keep`).

An identity is never weakened: when a machine that translates code has no file to show (no build project, a
profile that lists nothing, a file that cannot be read), the record says why and its `identity` is None.
Two records are the same simulation only when both identities are strings and equal.

The record written in the conversion report (`simulation_identity`, optional in report schema 2)::

    {'schema': 2, 'identity': '<sha256>' | None,
     'engine': {'files': n, 'pins': {upstream: revision, ...}, 'sha256': '<sha256>'} | None, 'rom': '<sha256>',
     'options': {name: value, ...}, 'sources': {'files': n, 'sha256': '<sha256>'} | None,
     'reason': None | '<why there is no identity>'}

This module defines the identity and is hashed by no stamp (`stamp_inputs.INTERFACE_MODULES`): `SCHEMA` is
part of what is hashed, so a change of the rules gives other identities, never a silent equality.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

SCHEMA = 2
REPORT_KEY = 'simulation_identity'
# Options of every machine that change the run: the video standard the player forces.
COMMON_RUN_OPTIONS = ('standard_override',)


def run_options(profile, options) -> dict:
    """The declared run-changing options of a request, each with its default when the request names none."""
    values = {name: options.get(name) for name in COMMON_RUN_OPTIONS}
    for key in profile.option_keys:
        if key.changes_run:
            value = options.get(key.name)
            if value is None:
                value = key.default
            # A choice is one of the profile's values, however the request spells it (256 or '256').
            values[key.name] = next((choice for choice in key.choices if str(choice) == str(value)), value)
    return values


def _text(data: bytes) -> bytes:
    # The rule of the stamps (compilation_inputs): a text input is hashed with LF line ends.
    return data.replace(b'\r\n', b'\n')


def _content(data: bytes, source) -> bytes:
    """What is hashed of one file: its text, without the lines `drop` names, or only the matches of `keep`."""
    data = _text(data)
    if source.keep:
        return b'\n'.join(match.group(0) for match in re.finditer(source.keep.encode('utf-8'), data))
    if source.drop:
        words = [word.encode('utf-8') for word in source.drop]
        data = b''.join(line for line in data.splitlines(keepends=True) if not any(word in line for word in words))
    return data


def source_entries(project: Path, sources) -> list[tuple[str, bytes]]:
    """(relative path, bytes to hash) of every file the sources name below `project`, ordered by relative path.

    Paths are relative with forward slashes whatever the system; a file two patterns name counts once, with the
    first pattern's rule. Links are not followed out of the project: only regular files below it are read."""
    project = Path(project)
    found = {}
    for source in sources:
        for path in project.glob(source.pattern):
            name = path.relative_to(project).as_posix()
            if name not in found and path.is_file():
                found[name] = _content(path.read_bytes(), source)
    # Byte order of the UTF-8 name, the same on every system.
    return sorted(found.items(), key=lambda entry: entry[0].encode('utf-8'))


def sources_digest(entries) -> str:
    value = hashlib.sha256(f'simulation-sources-v{SCHEMA}'.encode('ascii'))
    for name, data in entries:
        value.update(name.encode('utf-8') + b'\0' + hashlib.sha256(data).hexdigest().encode('ascii') + b'\0')
    return value.hexdigest()


def _pin_text(pin) -> str | None:
    """The revision one pin holds: read from the source as `upstreams.read_pin` does, else, where the sources are
    not on disk (a packaged converter), from the same constant of the imported module."""
    from . import upstreams
    from .paths import ASSETS
    value = upstreams.read_pin(pin, ASSETS) or upstreams.read_pin(pin)
    if value is None and pin.kind in ('python', 'dict') and pin.file.startswith('retrorecomp/') and pin.file.endswith('.py'):
        import importlib
        try:
            constant = getattr(importlib.import_module('.' + pin.file[len('retrorecomp/'):-3], __package__), pin.name)
            value = constant[pin.key][pin.index] if pin.kind == 'dict' else constant
        except (ImportError, AttributeError, KeyError, IndexError, TypeError):
            return None
    return value if isinstance(value, str) and value else None


def engine_pins(system: str) -> dict:
    """{upstream: pinned revision} of the upstreams one machine builds from. A submodule is left out: the tree of
    its parent's pinned revision fixes it. A pin that cannot be read is None (and then there is no identity)."""
    from . import upstreams
    return {item.key: _pin_text(item.pin) for item in upstreams.MACHINE_UPSTREAMS.get(system, ())
            if item.pin.kind != 'submodule'}


def engine_files(system: str) -> list[tuple[str, str]]:
    """(manifest name, SHA-256 of its normalised bytes) of the machine's game-role inputs that are files, in
    manifest order. Never a Python module, never a host or build input."""
    from .compilation_inputs import input_bytes, manifest_names, role
    from .paths import ASSETS
    return [(name, hashlib.sha256(input_bytes(ASSETS / name, name)).hexdigest())
            for name in manifest_names(system) if not name.startswith('retrorecomp') and role(name) == 'game']


def engine_content(system: str) -> dict:
    """The engine part of the identity: {'files', 'pins', 'sha256'}. Raises OSError or ValueError when a listed
    file is missing or a pin cannot be read."""
    files, pins = engine_files(system), engine_pins(system)
    unread = sorted(key for key, value in pins.items() if value is None)
    if unread:
        raise ValueError('unreadable upstream pin: ' + ', '.join(unread))
    value = hashlib.sha256(f'simulation-engine-v{SCHEMA}:{system}'.encode('ascii'))
    for name, digest in files:
        value.update(b'file\0' + name.encode('utf-8') + b'\0' + digest.encode('ascii') + b'\0')
    for key in sorted(pins):
        value.update(b'pin\0' + key.encode('utf-8') + b'\0' + pins[key].encode('utf-8') + b'\0')
    return {'files': len(files), 'pins': pins, 'sha256': value.hexdigest()}


def identity_of(system: str, engine: str, rom: str, options: dict, sources: str) -> str:
    """The identity itself: one hash of the five parts, in a canonical text."""
    text = json.dumps({'schema': SCHEMA, 'system': system, 'engine': engine, 'rom': rom, 'options': options,
                       'sources': sources}, sort_keys=True, separators=(',', ':'), ensure_ascii=True, default=str)
    return hashlib.sha256(b'retro-recomp-simulation-identity\0' + text.encode('ascii')).hexdigest()


def compute(profile, rom_sha256: str, options: dict, project: Path | None, *, engine: dict | None = None) -> dict:
    """The record of one conversion. `project` is the game's build project (None when the report names none);
    `engine` is `engine_content(profile.id)` unless a test gives one."""
    chosen = run_options(profile, options or {})
    record = {'schema': SCHEMA, 'identity': None, 'engine': engine, 'rom': rom_sha256, 'options': chosen,
              'sources': None, 'reason': None}
    if engine is None:
        try:
            engine = record['engine'] = engine_content(profile.id)
        except (OSError, ValueError) as error:
            record['reason'] = f'the engine content could not be read ({error})'
            return record
    emulated = bool(getattr(profile, 'emulated', ''))
    entries = []
    try:
        specs = profile.simulation_files(project) if project is not None else ()
        if specs:
            entries = source_entries(project, specs)
    except (OSError, ValueError) as error:
        record['reason'] = f'the generated sources could not be read ({type(error).__name__})'
        return record
    if not entries and not emulated:
        # A machine that translates code and shows none of it: no identity, rather than one that would
        # call two different translations equal.
        record['reason'] = ('the report names no build project' if project is None else
                            'the profile lists no generated source' if not specs else
                            'no generated source was found in the build project')
        return record
    record['sources'] = {'files': len(entries), 'sha256': sources_digest(entries)}
    record['identity'] = identity_of(profile.id, engine['sha256'], rom_sha256, chosen, record['sources']['sha256'])
    return record


def for_conversion(profile, rom_sha256: str, options: dict, report: dict, *, root: Path | None = None) -> dict:
    """The record of the conversion that has just written `report`: its build project is the one the report
    names (`build_cleanup.report_project`), read before the batch removes it."""
    from .build_cleanup import report_project
    return compute(profile, rom_sha256, options, report_project(profile.id, report, root))


def same_simulation(first, second) -> bool:
    """True only for two records of this schema that both carry an identity, the same one."""
    def identity(record):
        if not isinstance(record, dict) or record.get('schema') != SCHEMA:
            return None
        value = record.get('identity')
        return value if isinstance(value, str) and value else None
    return identity(first) is not None and identity(first) == identity(second)
