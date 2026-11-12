"""Numeric, ROM-free Game Boy Advance paths for one exact cartridge: no ROM byte, no RAM byte, no code, nothing of the BIOS.

The Game Boy Advance shares its paths as the experimental tier of the base (like the CPS-1, the CPS-2, the X68000 and the PC Engine): a path is
qualified only for the `cores` that validated it, and the whole sharing can be withdrawn with one line (`path_profiles.EXPERIMENTAL_SHARED`).

What is shared (docs/GAME_BOY_ADVANCE.md, "Paths"). Both kinds already exist in schema 3 and are the ones `gba_analysis` keeps in the player's own store, so
`path_profiles`, which every console's game stamp hashes, is not edited; `identity.layout` is empty, as for the PC Engine and the CPS-2:

* a ROM root, a `phys` row of the `entries` kind: the offset of a function entry in the cartridge file, bit 0 set for a Thumb entry. An ARM entry is a multiple
  of 4 (the schema cannot say so, this module does);
* a RAM copy, a `span` row of the `spans` kind: `[RAM address | Thumb flag, cartridge offset, length]` in IWRAM or EWRAM, the stretch where the work RAM was seen
  equal to the cartridge.

Each is a position and a length about a cartridge the receiver must own: the record states the cartridge's SHA-256 and size, a record of another image is
refused, and the receiver reads the bytes from its own file. The generated code that uses a RAM copy compares the live bytes with the cartridge's before
entering it.

What never travels, and stays in the conversion's private memory and project: the bytes of RAM code the cartridge does not hold (`gba_analysis.RamCode`), the
versions and parameter words computed from them, anything derived from the BIOS, the work RAM dumps and miss samples, titles, file names and the save.

The key of a record is the cartridge's SHA-256; `cores` (the qualification scope) is the SHA-1 of `PATH_REVISION`, the engine pin and the ARM core pin. The patch
set (`gba_patches`) is deliberately NOT in it: a patch that fixes a hardware behaviour does not decide whether an offset is a function entry. The patches a path
could notice (`PINNED_PATCH_PREFIXES`) are pinned by a test (tests/test_gba_knowledge.py): changing one fails it until the person who changes it has decided
whether `PATH_REVISION` must be raised.

A record is made only from the misses a conversion's own runs reached (`gba_conversion`), built, and checked against the engine's interpreter; never from the
paths it received. A received row is used and counted as pending. This converter cannot yet show that a received row was reached (the engine reports misses
only), so it marks none of them qualified.
"""
from __future__ import annotations

import hashlib
import json

from . import path_profiles as pp

SYSTEM = 'gba'
ROM = 'rom'
CPU = 'arm7tdmi'
MAP = 'gba'
# Raise this by hand when our use of the engine's identities changes in a way a path could notice (see the head of this module and the pin test).
PATH_REVISION = 1
_PROFILE = pp.PROFILES[(CPU, MAP)]
ROOT_LIMIT = _PROFILE.caps['phys']        # 262,144 roots a cartridge (the profile's cap)
SPAN_LIMIT = _PROFILE.caps['span']        # 4,096 RAM copies
SPAN_LENGTH = _PROFILE.span_max           # the longest copy
# The ceiling of each kind of path, by the name `entry_set` gives it (the form every schema 3 module exposes: the site's base builder reads it).
PATH_CAPS = {'gba_root': ROOT_LIMIT, 'gba_span': SPAN_LIMIT}
# The most pending ROM roots (received, not yet reached by a conversion that received them) one conversion builds for a cartridge; the rest is counted as left out.
# Qualified rows and the player's own rows are not capped.
PENDING_ROOT_CAP = 16384
# The patches whose target a path could notice: the recompiler's generated code and its ARM core (the engine's interpreter and code generator). The bus, the
# probe host and the player seam (`src/gba/`, `src/runtime/`) cannot make an offset a function entry or not.
PINNED_PATCH_PREFIXES = ('src/recompile/', 'src/armv4t/', 'external/arm-recomp-core/')
# ... and the patches of the probe host that decide which roots a conversion learns: the recorder of the bridge's computed jumps and of the RAM code.
RECORDER_MARKERS = ('rr_bridge_callee', 'rr_sample_ram_bytes', 'rr_returned')
# The most versions of one RAM address a received record can bring (own versions come first; the mirrors of the work RAM are not unlimited).
SPAN_VERSIONS_PER_ADDRESS = 8

UnknownFormat = pp.UnknownFormat

# An ARM entry or an ARM RAM copy (bit 0 of its address clear) is a multiple of this, in RAM and in the cartridge; a Thumb one needs the profile's halfword alignment only.
ARM_ALIGN = 4

# What this module's `validate_record` enforces on top of the schema 3 check, as data (the form the site's builder reads, `tools/build_web_limits.py`, so that
# `web/lib/paths3.php` and the validation corpus follow the converter instead of a copy of its rules). Keys: `layout` (the exact keys of the layout: none);
# `sources` (`only`, `required`: the names, `hashed`: each one states its SHA-256); `game` (`source`: the record's game id is `<system>:` plus the SHA-256 of that
# source, the cartridge); `paths` ({cpu: {kind: {`src`: the one image its blocks point into, `even_align`: a row whose first column is even (an ARM row) is a multiple of this,
# `even_align_columns`: and so are the rows' columns of these indexes (default: the first only; a RAM copy is `[address, offset, length]`: the address and the offset)}}}).
# The windows of a RAM copy, the lengths, the offsets' alignment, the ceilings and the formats are the profile's (`path_profiles`), read by the builder from the converter.
RECORD_RULES = {
    'layout': [],
    'sources': {'only': [ROM], 'required': [ROM], 'hashed': True},
    'game': {'source': ROM},
    'paths': {CPU: {'entries': {'src': ROM, 'even_align': ARM_ALIGN},
                    'spans': {'src': ROM, 'even_align': ARM_ALIGN, 'even_align_columns': [0, 1]}}},
}


def engine() -> str:
    """The `cores` string of the base for this converter: the revision of our use of the engine and the two pins, not our game stamp and not the patch set."""
    from .gba_conversion import ARM_CORE_REV, ENGINE_REV
    return hashlib.sha1(f'gba:{PATH_REVISION}:{ENGINE_REV}:{ARM_CORE_REV}'.encode()).hexdigest()


def record_engine(record) -> str:
    """The `cores` string a record was built with ('' when it is not a Game Boy Advance record)."""
    try:
        return record['cpus'][CPU]['core']
    except (KeyError, TypeError):
        return ''


def source_facts(rom: bytes) -> dict:
    return {ROM: {'bytes': len(rom), 'sha256': hashlib.sha256(rom).hexdigest()}}


def pinned_patches(patches=None) -> list:
    """The `(file, anchor, replacement)` of every patch whose target is under `PINNED_PATCH_PREFIXES` or whose text holds a recorder (the notes are prose and do not
    count)."""
    if patches is None:
        from .gba_patches import PATCHES as patches
    return [[file, old, new] for file, old, new, _note in patches
            if file.startswith(PINNED_PATCH_PREFIXES) or any(marker in new for marker in RECORDER_MARKERS)]


def patch_pin(patches=None) -> str:
    """SHA-256 of `pinned_patches`: what tests/test_gba_knowledge.py pins."""
    return hashlib.sha256(json.dumps(pinned_patches(patches), sort_keys=True).encode('utf-8')).hexdigest()


# --- Rows ----------------------------------------------------------------------------------------------------

def root_valid(value, size: int) -> bool:
    """A ROM root inside a cartridge of `size` bytes: bit 0 says Thumb, an ARM entry is a multiple of 4."""
    return (type(value) is int and 0 <= value and value + _PROFILE.entry_tail <= size and (value & 1 or not value % ARM_ALIGN))


def span_valid(row, size: int) -> bool:
    """A RAM copy `(RAM address | Thumb flag, cartridge offset, length)` inside a cartridge of `size` bytes and in work RAM, as the schema bounds it."""
    try:
        address, offset, length = row
    except (TypeError, ValueError):
        return False
    if not all(type(value) is int for value in (address, offset, length)):
        return False
    return (1 <= length <= SPAN_LENGTH and not length % _PROFILE.length_align and not offset % _PROFILE.offset_align and 0 <= offset
            and offset + length <= size and any(low <= address and address + length - 1 < high for low, high in _PROFILE.windows)
            and (address & 1 or not (address % ARM_ALIGN or offset % ARM_ALIGN)))                    # an ARM copy is word aligned in RAM and in the cartridge


def _spans_fit(spans) -> list:
    """The rows of `spans` in order, while they stay within the schema's total of `SPAN_BYTES` and `SPAN_LIMIT` rows."""
    kept, total = [], 0
    for row in spans:
        if len(kept) >= SPAN_LIMIT or total + row[2] > pp.SPAN_BYTES:
            continue
        total += row[2]
        kept.append(row)
    return kept


def build_record(sha256: str, size: int, core: str, roots, spans) -> dict:
    """The schema 3 document of a cartridge's paths, sorted so that equal paths give equal documents (validated: a number that does not fit its bounds is a
    bug in the caller). The one writer of this record: the player's own store (`gba_analysis.record`) and the promoted record both use it."""
    roots, spans = sorted(set(roots)), sorted({tuple(row) for row in spans})
    if len(roots) > ROOT_LIMIT or len(spans) > SPAN_LIMIT:
        raise ValueError('A Game Boy Advance record holds too many paths.')
    paths = {}
    if roots:
        paths['entries'] = [{'shape': 'phys', 'src': ROM, 'table': pp.encode_table([[entry] for entry in roots], 1)}]
    if spans:
        paths['spans'] = [{'shape': 'span', 'src': ROM, 'table': pp.encode_table([list(row) for row in spans], 3)}]
    value = {'schema': pp.SCHEMA, 'game': f'{SYSTEM}:{sha256}',
             'identity': {'system': SYSTEM, 'sources': {ROM: {'bytes': size, 'sha256': sha256}}, 'layout': {}},
             'cpus': {CPU: {'map': MAP, 'core': core, 'paths': paths}}, 'devices': {}}
    return pp.validate_game(value)


def make_record(identity: str, rom: bytes, roots=(), spans=(), *, core: str | None = None) -> dict:
    """The schema 3 document of a cartridge: the size and hash of its image, the engine, and the rows."""
    facts = source_facts(rom)
    if facts[ROM]['sha256'] != identity:
        raise ValueError('The key of a Game Boy Advance record is the SHA-256 of its cartridge.')
    return build_record(identity, len(rom), core or engine(), roots, spans)


def rows(record) -> tuple[list, list]:
    """(roots, spans) of a validated record, sorted. ValueError when a row breaks a rule the schema does not check."""
    section = record['cpus'][CPU]
    size = record['identity']['sources'][ROM]['bytes']
    roots, spans = set(), set()
    for block in section['paths'].get('entries', ()):
        roots |= {row[0] for row in pp.decode_table(block['table'], 1, ROOT_LIMIT)}
    for block in section['paths'].get('spans', ()):
        spans |= {tuple(row) for row in pp.decode_table(block['table'], 3, SPAN_LIMIT)}
    if not all(root_valid(root, size) for root in roots) or not all(span_valid(row, size) for row in spans):
        raise ValueError('A Game Boy Advance path breaks a rule of its kind (an ARM entry is a multiple of 4).')
    return sorted(roots), sorted(spans)


def validate_record(record, identity: str | None = None) -> dict:
    """Strict numeric allowlist of one Game Boy Advance record (the schema 3 validator, then what is this machine's own), or ValueError."""
    try:
        pp.validate_game(record)
        if not isinstance(record, dict) or not record['game'].startswith(SYSTEM + ':'):
            raise ValueError('Not a Game Boy Advance record.')
        if identity is not None and record['game'] != f'{SYSTEM}:{identity}':
            raise ValueError('Game Boy Advance hints do not match their cartridge.')
        sources = record['identity']['sources']
        if record['identity']['layout'] != {} or set(sources) != {ROM} or sources[ROM].get('sha256') != record['game'].split(':', 1)[1]:
            raise ValueError('Invalid Game Boy Advance sources.')
        if set(record['cpus']) != {CPU} or record['devices'] or record['cpus'][CPU]['map'] != MAP:
            raise ValueError('A Game Boy Advance record lists the ARM7TDMI only.')
        paths = record['cpus'][CPU]['paths']
        if set(paths) - {'entries', 'spans'}:
            raise ValueError('A Game Boy Advance record lists ROM roots and RAM copies only.')
        for kind, shape in (('entries', 'phys'), ('spans', 'span')):
            for block in paths.get(kind, ()):
                if block.get('src') != ROM or block['shape'] != shape:
                    raise ValueError('A Game Boy Advance block points into the wrong image.')
        rows(record)
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError('Invalid Game Boy Advance record.') from error
    return record


def record_digest(record) -> str:
    """SHA-256 of a record's canonical text: how a report names the record a conversion made."""
    return hashlib.sha256(json.dumps(record, sort_keys=True, separators=(',', ':')).encode('ascii')).hexdigest()


def entry_set(record) -> set:
    """Every path of a record as comparable tuples (what the base compares between players)."""
    if not isinstance(record, dict):
        return set()
    try:
        roots, spans = rows(record)
    except (KeyError, TypeError, ValueError):
        return set()
    return {('gba_root', root) for root in roots} | {('gba_span', row) for row in spans}


def same_images(first: dict, second: dict) -> bool:
    """Two records point into the very same cartridge."""
    return first['game'] == second['game'] and first['identity']['sources'].get(ROM) == second['identity']['sources'].get(ROM)


def _assemble(skeleton: dict, roots, spans, core: str) -> dict:
    source = skeleton['identity']['sources'][ROM]
    return build_record(source['sha256'], source['bytes'], core, roots, spans)


def rebuild(skeleton: dict, hints, *, core: str | None = None) -> dict:
    """A record of the skeleton's cartridge holding exactly `hints` (as `entry_set` names them)."""
    return validate_record(_assemble(skeleton, [row for name, row in hints if name == 'gba_root'],
                                     [row for name, row in hints if name == 'gba_span'], core or record_engine(skeleton)))


def merged(identity: str, first: dict, second: dict) -> dict:
    """Union of two records of one cartridge. Records of another engine or another cartridge never mix: the one built by the current engine is kept, else the
    first. ValueError when the union exceeds a bound."""
    if not second:
        return first
    if not first:
        return second
    if not same_images(first, second) or record_engine(first) != record_engine(second):
        current = engine()
        return second if record_engine(second) == current and record_engine(first) != current else first
    (roots, spans), (more_roots, more_spans) = rows(first), rows(second)
    return validate_record(_assemble(first, {*roots, *more_roots}, {*spans, *more_spans}, record_engine(first)))


def salvaged_record(identity: str, record) -> dict | None:
    """A received record, or None: it is checked as a whole (its rows are numbers about a cartridge whose hash it states)."""
    try:
        return validate_record(record, identity)
    except (ValueError, TypeError, KeyError, AttributeError):
        return None


# --- The player's own paths to a record ----------------------------------------------------------------------

def promote(identity: str, rom: bytes, observations, *, previous: dict | None = None, private: dict | None = None) -> tuple[dict, dict]:
    """(record, counts) from the paths a verified conversion's own runs reached (`observations`: a `gba_analysis.Observations`). `previous` is the library's
    record of this very cartridge and engine; its rows are kept. The record holds no ROM byte, no RAM byte and no code; `private` is counted, never shared
    (what the conversion kept to itself). A row that breaks a rule of its kind is refused and counted; the schema's bounds keep a deterministic subset
    (`counts['truncated']`)."""
    size = len(rom)
    roots = {value for value in observations.roots}
    spans = {tuple(row) for row in observations.spans}
    if previous and isinstance(previous, dict):
        try:
            validate_record(previous, identity)
            if previous['identity']['sources'] == source_facts(rom) and record_engine(previous) == engine():
                old_roots, old_spans = rows(previous)
                roots |= set(old_roots)
                spans |= set(old_spans)
        except ValueError:
            pass
    refused = {'roots': sum(not root_valid(value, size) for value in roots), 'spans': sum(not span_valid(row, size) for row in spans)}
    roots = sorted(value for value in roots if root_valid(value, size))
    spans = sorted(row for row in spans if span_valid(row, size))
    kept_roots, kept_spans = roots[:ROOT_LIMIT], _spans_fit(spans)
    record = make_record(identity, rom, kept_roots, kept_spans)
    validate_record(record, identity)
    counts = {'paths': {'roots': len(kept_roots), 'ram_copies': len(kept_spans)}, 'refused': refused,
              'truncated': len(kept_roots) < len(roots) or len(kept_spans) < len(spans),
              'left_out_by_the_bounds': {'roots': len(roots) - len(kept_roots), 'ram_copies': len(spans) - len(kept_spans)},
              'private': dict(private or {}), 'raw_bytes_stored': False}
    return record, counts


# --- Received paths ------------------------------------------------------------------------------------------

def shared_rows(identity: str, size: int, *, qualified=None, imported=None, own=None, cap: int | None = None):
    """(Observations, info): the rows of the received records for this cartridge that the build adds to the player's own. Two sources, counted apart: the
    qualified side bank (rows qualified for this `cores`; a qualified record of another `cores` is used as pending) and the imported side bank (other players'
    rows, pending). A record of another cartridge or one that breaks a rule is ignored and `info` says why. `own` (a `gba_analysis.Observations`) holds what the
    player's own store already has: those rows are not received again. At most `cap` pending ROM roots are used (the lowest offsets: a deterministic subset);
    qualified rows are not capped. Nothing here is written anywhere."""
    from .gba_analysis import Observations
    cap = PENDING_ROOT_CAP if cap is None else cap
    info = {'records': {'qualified': 0, 'imported': 0}, 'received_roots': 0, 'received_ram_copies': 0, 'already_known': 0, 'qualified_by_the_base': 0,
            'pending': 0, 'pending_from_another_cores': 0, 'used_roots': 0, 'used_ram_copies': 0,
            'left_out_by_the_cap': {'roots': 0, 'ram_copies': 0}, 'pending_root_cap': cap, 'ignored': {}}
    current = engine()
    tier = {}                                                       # row -> 'qualified' | 'pending'; a qualified row stays qualified
    from_other_cores = set()                                        # rows that came from a qualified record of another `cores`
    for name, record in (('qualified', qualified), ('imported', imported)):
        if not record:
            continue
        try:
            validate_record(record, identity)
            if record['identity']['sources'][ROM] != {'bytes': size, 'sha256': identity}:
                raise ValueError('Game Boy Advance hints are for another cartridge image.')
            roots, spans = rows(record)
        except ValueError as error:
            info['ignored'][name] = str(error)[:120]
            continue
        info['records'][name] += 1
        level = 'qualified' if name == 'qualified' and record_engine(record) == current else 'pending'
        for row in [('root', value) for value in roots] + [('span', row) for row in spans]:
            if tier.get(row) != 'qualified':
                tier[row] = level
            if name == 'qualified' and level == 'pending':
                from_other_cores.add(row)
    own_roots, own_spans = (own.roots, own.spans) if own is not None else (set(), set())
    new, known = {}, 0
    for (kind, value), level in tier.items():
        info['received_roots' if kind == 'root' else 'received_ram_copies'] += 1
        if value in (own_roots if kind == 'root' else own_spans):
            known += 1
        else:
            new[(kind, value)] = level
    info['already_known'] = known
    # The pending roots kept are a deterministic subset in the order of a hash of the cartridge and the offset, not the lowest offsets: junk at low offsets cannot
    # crowd out the others.
    pending_roots = sorted((value for (kind, value), level in new.items() if kind == 'root' and level == 'pending'),
                           key=lambda value: hashlib.sha1(f'{identity}:{value}'.encode()).digest())
    over = set(pending_roots[cap:])
    versions, spans_over = {}, 0
    used = Observations()
    for (kind, value), level in new.items():
        if kind == 'root':
            if value in over:
                continue
            used.roots.add(value)
        else:
            key = (value[0] & ~1, value[0] & 1)
            versions[key] = versions.get(key, 0) + 1
            if versions[key] > SPAN_VERSIONS_PER_ADDRESS:
                spans_over += 1
                continue
            used.spans.add(value)
        info['qualified_by_the_base' if level == 'qualified' else 'pending'] += 1
        if level == 'pending' and (kind, value) in from_other_cores:
            info['pending_from_another_cores'] += 1
    info['used_roots'], info['used_ram_copies'] = len(used.roots), len(used.spans)
    info['left_out_by_the_cap']['roots'] = len(over)
    info['left_out_by_the_cap']['ram_copies'] = spans_over
    return used, info


def reached(received, own) -> dict:
    """How many received rows this conversion's own runs showed a miss at (`own`: what its passes learned). The engine reports misses only, so a received row that
    its code ran natively leaves no trace: the others are not proven either way, and the converter marks none of them qualified."""
    total = len(received.roots) + len(received.spans)
    hits = len(received.roots & own.roots) + len(received.spans & own.spans)
    return {'received_rows_used': total, 'reached_by_own_misses': hits, 'not_proven': total - hits}


def shared_paths_report(info: dict, proof: dict) -> dict:
    """The `shared_paths` counters of a conversion's `native_coverage`: what was received, used, left out by the cap, and that this converter qualified none."""
    return {**info, **proof, 'qualified_by_this_converter': 0,
            'note': 'rows received from the base or an import are used as hints (built) and checked by the comparison with the engine\'s interpreter on the '
                    'tested scenarios; this converter cannot show that a received row was reached, so it marks none qualified and never writes them to the '
                    "player's paths or to the record it shares"}


def knowledge_block(record: dict, promotion: dict, shared: dict) -> dict:
    """The report's `knowledge` section (what the exchange collector reads: `record_sha256`). `shared` says whether the machine is in the sharing at all
    (`path_profiles.EXPERIMENTAL_SHARED`), not that this conversion shared anything."""
    from .systems import get_profile
    return {'machine_status': get_profile(SYSTEM).status, 'shared': SYSTEM in pp.SHARED_SYSTEMS, 'cores': engine(), 'path_revision': PATH_REVISION,
            'record_sha256': record_digest(record), 'paths': promotion['paths'], 'promotion': {key: promotion[key] for key in ('refused', 'truncated', 'private')},
            'source': 'the misses of this conversion\'s own runs, built and checked against the engine\'s interpreter', 'use': dict(shared),
            'raw_bytes_stored': False, 'fresh_validation_required': True}


# --- The player's library ------------------------------------------------------------------------------------

def library_record(identity: str) -> dict | None:
    """This player's own record: the paths that verified conversions reached (`gba_conversion` writes it into the game's summary,
    `<library>/gba/<sha256>/compilation.json`), or None."""
    from .library import library_root
    path = library_root(SYSTEM) / identity / 'compilation.json'
    try:
        with path.open('rb') as stream:
            raw = stream.read(16 * 1024 * 1024 + 1)
        if len(raw) > 16 * 1024 * 1024:
            return None
        data = json.loads(raw)
        if data.get('system') != SYSTEM or data.get('game') != identity or not data.get('fresh_reference_passed'):
            return None
        return validate_record(data['record'], identity)
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return None
