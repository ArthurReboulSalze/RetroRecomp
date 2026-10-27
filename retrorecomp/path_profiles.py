"""CPU-keyed path schema, version 3: profiles, integer codecs, validator, adapters.

STATUS: defined and tested, NOT USED YET. No other module imports this one.
Release code still reads and writes schema 1 (`knowledge.FIELDS`, and Neo Geo's
own record in `neogeo_knowledge`); a later stage switches them over.

A path is a number about a ROM (an offset, a position, a mask), never ROM bytes.
Schema 3 keys a game record by CPU instead of by console:

    {"schema": 3, "game": "md:<64 hex>",
     "identity": {"system": "md", "sources": {"rom": {"bytes": N}}, "layout": {}},
     "cpus": {"m68k": {"map": "md", "core": "<40 hex>",
                       "paths": {"entries": [block], "ram_code": [block]}},
              "z80":  {"map": "md-sound", "core": "<40 hex>", "paths": {...}}},
     "devices": {}}

A block names its shape (the columns of a row), its source(s) and a payload:
a column-wise table (`encode_table`) or, for two shapes, groups. Every shape
maps to exactly one schema 1 field, so `to_legacy(to_v3(...))` gives the same
record back, row order included, for every record the old validators accept
(and for most they refuse: the adapters only refuse what schema 1 cannot hold).

Bounds are data (`PROFILES`), per CPU and memory map. Where the shared validator
of schema 1 is looser than the local code that uses the hints, the profile
holds the stricter, local value: see `STRICTER_THAN_V2`.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from math import gcd
import hashlib
import json
import re

SCHEMA = 3
U32 = 0xffffffff
SYSTEMS = ('sms', 'gg', 'gb', 'nes', 'md', 'snes', 'ng', 'cps1', 'x68')
GAME_KEY = re.compile('(?:' + '|'.join(SYSTEMS) + '):[0-9a-f]{64}')
HEX40 = re.compile('[0-9a-f]{40}')
HEX64 = re.compile('[0-9a-f]{64}')
SOURCE_NAME = re.compile('[a-z][a-z0-9]{0,15}')
GAMES_PER_SYSTEM = 4096


# --- Integer-sequence codecs --------------------------------------------------
#
# One lossless codec for every column of every path kind. `encode_seq` keeps
# the exact sequence (order and repeats included) and picks the smallest JSON
# among the encodings that can hold it:
#   list     {"enc": "list", "v": [...]}
#   const    {"enc": "const", "v": x, "n": count}
#   delta    {"enc": "delta", "first": a, "gaps": [...], ["step": k]}  non-decreasing
#   sdelta   {"enc": "sdelta", "first": a, "gaps": [...]}              signed gaps
#   ranges   {"enc": "ranges", "v": [[first, last], ...]}              strictly increasing
#   bitmap32 {"enc": "bitmap32", "v": [[base, mask], ...]}             strictly increasing
# `step` divides every gap (Mega Drive entries are all even).

SEQ_ENCODINGS = ('list', 'const', 'delta', 'sdelta', 'ranges', 'bitmap32')
_SEQ_KEYS = {'list': {'enc', 'v'}, 'const': {'enc', 'v', 'n'}, 'sdelta': {'enc', 'first', 'gaps'},
             'ranges': {'enc', 'v'}, 'bitmap32': {'enc', 'v'}}


def _is_int(value) -> bool:
    return type(value) is int


def _json_size(value) -> int:
    return len(json.dumps(value, separators=(',', ':')))


def encode_seq(values, only: str | None = None) -> dict:
    """The smallest encoding (`only` forces one, ValueError when it cannot hold the values)."""
    values = list(values)
    if not all(type(v) is int for v in values):
        raise ValueError('An integer sequence holds integers only.')
    candidates = [{'enc': 'list', 'v': values}]
    count = len(values)
    if count and values.count(values[0]) == count:
        candidates.append({'enc': 'const', 'v': values[0], 'n': count})
    if count:
        gaps = [b - a for a, b in zip(values, values[1:])]
        low = min(gaps, default=0)
        if low >= 0:
            step = gcd(*gaps) if gaps else 1
            step = step if step > 1 else 1
            entry = {'enc': 'delta', 'first': values[0], 'gaps': [g // step for g in gaps]}
            if step > 1:
                entry['step'] = step
            candidates.append(entry)
        candidates.append({'enc': 'sdelta', 'first': values[0], 'gaps': gaps})
        if low > 0:
            runs, start = [], 0
            for index, gap in enumerate(gaps):
                if gap != 1:
                    runs.append([values[start], values[index]]); start = index + 1
            runs.append([values[start], values[-1]])
            candidates.append({'enc': 'ranges', 'v': runs})
            bitmaps = []
            for value in values:
                base = value & ~31
                if bitmaps and bitmaps[-1][0] == base:
                    bitmaps[-1][1] |= 1 << (value & 31)
                else:
                    bitmaps.append([base, 1 << (value & 31)])
            candidates.append({'enc': 'bitmap32', 'v': bitmaps})
    if only is not None:
        matches = [c for c in candidates if c['enc'] == only]
        if not matches:
            raise ValueError('This encoding cannot hold these integers.')
        return matches[0]
    return min(candidates, key=_json_size)


def seq_count(encoded) -> int:
    """How many integers an encoding holds, checked without expanding it."""
    if not isinstance(encoded, dict) or encoded.get('enc') not in SEQ_ENCODINGS:
        raise ValueError('Unknown integer sequence encoding.')
    kind = encoded['enc']
    if kind == 'delta':
        if set(encoded) - {'step'} != {'enc', 'first', 'gaps'}:
            raise ValueError('Invalid delta sequence.')
        if (not _is_int(encoded['first']) or not isinstance(encoded['gaps'], list)
                or ('step' in encoded and (not _is_int(encoded['step']) or encoded['step'] < 2))):
            raise ValueError('Invalid delta sequence.')
        return 1 + len(encoded['gaps'])
    if set(encoded) != _SEQ_KEYS[kind]:
        raise ValueError('Invalid integer sequence.')
    if kind == 'sdelta':
        if not _is_int(encoded['first']) or not isinstance(encoded['gaps'], list):
            raise ValueError('Invalid delta sequence.')
        return 1 + len(encoded['gaps'])
    if kind == 'const':
        if not _is_int(encoded['v']) or not _is_int(encoded['n']) or encoded['n'] < 1:
            raise ValueError('Invalid constant sequence.')
        return encoded['n']
    if not isinstance(encoded['v'], list):
        raise ValueError('Invalid integer sequence.')
    if kind == 'list':
        return len(encoded['v'])
    total = 0
    for item in encoded['v']:
        if not isinstance(item, list) or len(item) != 2 or not _is_int(item[0]) or not _is_int(item[1]):
            raise ValueError('Invalid integer sequence run.')
        if kind == 'ranges':
            if item[1] < item[0]:
                raise ValueError('Invalid integer range.')
            total += item[1] - item[0] + 1
        else:
            if item[0] & 31 or not 0 < item[1] <= U32:
                raise ValueError('Invalid integer bitmap.')
            total += item[1].bit_count()
    return total


def decode_seq(encoded, limit: int) -> list:
    """The integers of an encoding; `limit` bounds the count before expansion."""
    count = seq_count(encoded)
    if count > limit:
        raise ValueError('Integer sequence exceeds its bound.')
    kind = encoded['enc']
    if kind == 'list':
        values = list(encoded['v'])
    elif kind == 'const':
        values = [encoded['v']] * count
    elif kind in ('delta', 'sdelta'):
        step = encoded.get('step', 1)
        values, current = [encoded['first']], encoded['first']
        for gap in encoded['gaps']:
            if not _is_int(gap) or (kind == 'delta' and gap < 0):
                raise ValueError('Invalid sequence gap.')
            current += gap * step
            values.append(current)
    elif kind == 'ranges':
        values = [n for first, last in encoded['v'] for n in range(first, last + 1)]
    else:
        values = []
        for base, mask in encoded['v']:
            while mask:
                bit = mask & -mask
                values.append(base + bit.bit_length() - 1)
                mask ^= bit
    if not all(type(v) is int for v in values):
        raise ValueError('Integer sequences hold integers only.')
    return values


def encode_table(rows, width: int) -> dict:
    """Rows of `width` integers, column by column. `{"n": 0}` when empty."""
    rows = list(rows)
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) != width:
            raise ValueError('A path row has the wrong width.')
    if not rows:
        return {'n': 0}
    return {'n': len(rows), 'cols': [encode_seq([row[c] for row in rows]) for c in range(width)]}


def table_count(table, width: int, limit: int) -> int:
    if not isinstance(table, dict) or not _is_int(table.get('n')) or not 0 <= table['n'] <= limit:
        raise ValueError('Invalid path table.')
    if table['n'] == 0:
        if set(table) != {'n'}:
            raise ValueError('Invalid empty path table.')
        return 0
    if set(table) != {'n', 'cols'} or not isinstance(table['cols'], list) or len(table['cols']) != width:
        raise ValueError('Invalid path table columns.')
    return table['n']


def decode_table(table, width: int, limit: int, *, unsigned: bool = True) -> list:
    count = table_count(table, width, limit)
    if count == 0:
        return []
    columns = []
    for encoded in table['cols']:
        if seq_count(encoded) != count:
            raise ValueError('A path column has the wrong length.')
        column = decode_seq(encoded, count)
        if unsigned and (min(column) < 0 or max(column) > U32):
            raise ValueError('Path numbers are unsigned 32-bit values.')
        columns.append(column)
    return [list(row) for row in zip(*columns)]


# --- Profiles ------------------------------------------------------------------

@dataclass(frozen=True)
class Profile:
    """Bounds of one CPU on one memory map. All numbers come from today's code."""
    cpu: str
    map: str
    systems: tuple
    roles: tuple                    # source roles its pointers may use
    caps: dict                      # shape -> most rows (blocks, for `phys_deltas`)
    entry_align: int = 1            # `phys` entries
    entry_min: int = 0
    entry_tail: int = 1             # bytes an entry needs after its offset
    unit: int = 0                   # bank unit of mapped entries
    pc_window: tuple = (0, 0)       # mapped entries: inclusive pc range
    upper_base: int = 0             # first pc of banks >= 1 when derived (Game Boy)
    pc_below: int = 0               # `sega5`: pc < this
    windows: tuple = ()             # RAM address or pc windows, [low, high)
    contained: bool = False         # a RAM instruction ends inside its window
    address_base: int = 0           # schema 1 stores address - base (Neo Geo work RAM)
    length: tuple = (0, 0)          # RAM instruction length, inclusive
    length_align: int = 1
    offset_align: int = 1           # source offset of a RAM instruction
    address_align: int = 1          # RAM address (after `address_base`)
    span_max: int = 0               # longest `span`
    guard: str = 'full'             # full | derived | mask | first
    budget: int = 0                 # decoded positions per game (SPC700)


def _p(**fields) -> Profile:
    return Profile(**fields)


PROFILES = {
    ('m68k', 'md'): _p(cpu='m68k', map='md', systems=('md',), roles=('rom',),
                       caps={'phys': 65536, 'insn': 2048},
                       entry_align=2, entry_min=0x200, entry_tail=8,
                       windows=((0xe00000, 0x1000000),), contained=True,
                       length=(2, 16), length_align=2, address_align=2),
    ('m68k', 'ng'): _p(cpu='m68k', map='ng', systems=('ng',), roles=('p', 'bios'),
                       caps={'phys': 262144, 'phys_deltas': 2, 'insn': 4096},
                       entry_align=2, entry_tail=2,
                       windows=((0x100000, 0x110000),), contained=True, address_base=0x100000,
                       length=(2, 16), length_align=2, offset_align=2, address_align=2),
    ('m68k', 'cps1'): _p(cpu='m68k', map='cps1', systems=('cps1',), roles=('maincpu',),
                         caps={'insn': 4096},
                         windows=((0xff0000, 0x1000000),), contained=True,
                         length=(2, 16), length_align=2, offset_align=2, address_align=2),
    ('m68k', 'x68'): _p(cpu='m68k', map='x68', systems=('x68',), roles=('ipl', 'disk'),
                        caps={'insn': 65536, 'span': 4096},
                        windows=((0, 0xc00000), (0xe00000, 0xe80000), (0xea0000, 0xea2000),
                                 (0xfc0000, 0xfffffe)),
                        contained=True, length=(2, 16), length_align=2, offset_align=2, address_align=2,
                        span_max=131072),
    ('z80', 'sms'): _p(cpu='z80', map='sms', systems=('sms', 'gg'), roles=('rom',),
                       caps={'sega5': 65536, 'window4': 4096}, pc_below=0xbf01),
    ('z80', 'md-sound'): _p(cpu='z80', map='md-sound', systems=('md',), roles=('rom',),
                            caps={'insn': 32768},
                            windows=((0, 0x4000), (0x8000, 0x10000)),
                            length=(4, 4), guard='derived'),
    ('z80', 'ng-sound'): _p(cpu='z80', map='ng-sound', systems=('ng',), roles=('m1', 'sm1'),
                            caps={'insn_masked': 32768},
                            windows=((0xf800, 0x10000),), length=(4, 4), guard='mask'),
    ('z80', 'cps1-sound'): _p(cpu='z80', map='cps1-sound', systems=('cps1',), roles=('audiocpu',),
                              caps={'insn_masked': 4096},
                              windows=((0xd000, 0xd800),), length=(4, 4), guard='mask'),
    ('sm83', 'gb'): _p(cpu='sm83', map='gb', systems=('gb',), roles=('rom',),
                       caps={'gb_offsets': 65536, 'gb_rows': 65536},
                       unit=0x4000, pc_window=(0, 0x7fff), upper_base=0x4000),
    ('mos6502', 'nes'): _p(cpu='mos6502', map='nes', systems=('nes',), roles=('rom',),
                           caps={'nes_rows': 65536, 'opcode_ptr': 65536},
                           unit=0x1000, pc_window=(0x8000, 0xffff),
                           windows=((0, 0x2000), (0x6000, 0x10000)), guard='first'),
    ('w65c816', 'snes'): _p(cpu='w65c816', map='snes', systems=('snes',), roles=('rom',),
                            caps={'insn': 16384, 'opcode_ptr': 16384},
                            windows=((0, 0x1000000),), length=(4, 4), guard='first'),
    ('spc700', 'snes'): _p(cpu='spc700', map='snes', systems=('snes',), roles=('rom',),
                           caps={'spc_refs': 262144, 'spc_ranges': 262144, 'spc_bitmaps': 262144,
                                 'spc_deltas': 262144},
                           windows=((0, 0xf0), (0x100, 0x10000)), guard='first', budget=262144),
}

# Every shape: (kind, row columns). A block that lists several sources has a
# leading `src` column (an index into its `srcs`).
SHAPES = {
    'sega5': ('entries', ('pc', 'b0', 'b1', 'b2', 'crc')),
    'phys': ('entries', ('offset',)),
    'phys_deltas': ('entries', None),
    'gb_offsets': ('entries', ('offset',)),
    'gb_rows': ('entries', ('offset', 'pc')),
    'nes_rows': ('entries', ('offset', 'pc')),
    'window4': ('windows', ('offset',)),
    'insn': ('ram_code', ('address', 'offset', 'length')),
    'insn_masked': ('ram_code', ('address', 'offset', 'length', 'guard')),
    'opcode_ptr': ('ram_code', ('pc', 'offset')),
    'spc_refs': ('ram_code', ('pc', 'offset')),
    'spc_ranges': ('ram_code', ('first', 'last', 'offset')),
    'spc_bitmaps': ('ram_code', ('first', 'mask', 'offset')),
    'spc_deltas': ('ram_code', None),
    'span': ('spans', ('address', 'offset', 'length')),
    'pair': ('targets', ('site', 'target')),
}
KINDS = ('entries', 'windows', 'ram_code', 'spans')

SYSTEM_SECTIONS = {
    'sms': (('z80', 'sms'),), 'gg': (('z80', 'sms'),), 'gb': (('sm83', 'gb'),),
    'nes': (('mos6502', 'nes'),), 'md': (('m68k', 'md'), ('z80', 'md-sound')),
    'snes': (('w65c816', 'snes'), ('spc700', 'snes')), 'ng': (('m68k', 'ng'), ('z80', 'ng-sound')),
    'cps1': (('m68k', 'cps1'), ('z80', 'cps1-sound')), 'x68': (('m68k', 'x68'),),
}

# Cartridge devices have no path kind of their own yet but the GSU's indirect
# jump pairs (planned, see docs/SNES_SUPERFX.md); sites and targets are 24-bit.
DEVICES = {'gsu': {'systems': ('snes',), 'kinds': {'targets': 65536}},
           'cx4': {'systems': ('snes',), 'kinds': {}},
           'dsp1': {'systems': ('snes',), 'kinds': {}}}

SPAN_BYTES = 4 << 20
ROM_BOUNDS = (8192, 128 * 1024 * 1024 + 528)
# (minimum, maximum) bytes of every source, per system and source role. Neo Geo
# are the bounds of `neogeo_knowledge.SIZE_BOUNDS`; CPS-1 and X68000 are new and
# provisional (nothing stores them yet).
SOURCE_BOUNDS = {
    **{system: {'rom': ROM_BOUNDS} for system in ('sms', 'gg', 'gb', 'nes', 'md', 'snes')},
    'ng': {'cart': (4096, 512 << 20), 'p': (512, 16 << 20), 'bios': (0x20000, 0x20000),
           'm1': (0x10000, 512 << 10), 'sm1': (0x20000, 0x20000)},
    'cps1': {'maincpu': (1, 32 << 20), 'audiocpu': (1, 1 << 20)},
    'x68': {'ipl': (1, 1 << 20), 'disk': (1, 1 << 30)},
}
REQUIRED_SOURCES = {'ng': ('cart', 'p', 'bios', 'm1', 'sm1'),
                    **{system: ('rom',) for system in ('sms', 'gg', 'gb', 'nes', 'md', 'snes')}}
# Systems whose sources must carry a SHA-256 (the identity of their key).
HASHED_SOURCES = {'ng': ('cart', 'bios')}
# Neo Geo regions as schema 1 numbers them, and the section they belong to.
NG_REGIONS = {'p': 1, 'bios': 2, 'm1': 3, 'sm1': 4}
NG_CPU_SOURCES = {'m68k': ('p', 'bios'), 'z80': ('m1', 'sm1')}
# Schema 1 widths (row length of each field), checked against `knowledge.FIELDS`
# and `neogeo_knowledge.FIELDS` by tests/test_paths_schema.py.
LEGACY_WIDTHS = {
    'sms': {'rom_entries': 5, 'pattern_refs': 1}, 'gg': {'rom_entries': 5, 'pattern_refs': 1},
    'gb': {'rom_entries': 2}, 'nes': {'rom_entries': 2, 'ram_opcode_refs': 2},
    'md': {'rom_entries': 1, 'ram_refs': 3, 'z80_refs': 3},
    'snes': {'ram_refs': 3, 'ram_opcode_refs': 2, 'spc_refs': 2, 'spc_ranges': 3,
             'spc_bitmaps': 3, 'spc_deltas': None},
    'ng': {'rom_entries': 2, 'ram_refs': 4, 'z80_refs': 4},
}
NG_IDENTITY_FIELDS = ('engine', 'loader', 'cart', 'bios', 'rom_bytes', 'p_bytes', 'bios_bytes',
                      'm1_bytes', 'sm1_bytes')

# Where schema 1's shared validator accepts what the local code that uses the
# hints refuses; schema 3 follows the local code (so `validate_game` is
# stricter on exactly these). tests/test_paths_schema.py pins each one.
STRICTER_THAN_V2 = {
    'md.ram_refs.address': 'bus address 0xE00000..0xFFFFFE, even (megadrive.valid_ram_variant)',
    'md.ram_refs.length': 'even, 2..16 (hex multiple of 4), ends before 0x1000000',
    'md.z80_refs.pc': 'at most 0xFFFF and outside 0x4000..0x7FFF (megadrive_z80.valid_variant)',
    'md.z80_refs.length': 'exactly 4 (eight hex digits)',
    'snes.ram_refs.length': 'exactly 4 (eight hex digits, supernintendo.valid_ram_variant)',
    'snes.ram_refs.address': '24-bit bus address (supernintendo.valid_ram_address)',
}


def profile_table() -> dict:
    """The profiles as plain data (what a web validator is generated from)."""
    return {f'{cpu}/{name}': asdict(profile) for (cpu, name), profile in sorted(PROFILES.items())}


def ng_key(cart: str, bios: str) -> str:
    """`neogeo_knowledge.key`, pinned equal by a test until that module uses this one."""
    return hashlib.sha256(json.dumps({'cart': cart, 'bios': bios, 'system': 'mvs', 'region': 'eu'},
                                     sort_keys=True).encode()).hexdigest()


# --- Validator -------------------------------------------------------------------

def _need(condition, message='Invalid compilation paths.'):
    if not condition:
        raise ValueError(message)


def _in_window(windows, low, high) -> bool:
    return any(a <= low and high < b for a, b in windows)


def source_role(name: str, bounds=None) -> str:
    """`disk3` is a `disk`; `m1` and `sm1` are their own roles."""
    return name if bounds and name in bounds else re.sub(r'\d+$', '', name)


def validate_game(record) -> dict:
    """Strict numeric allowlist of one schema 3 game record, or ValueError."""
    try:
        return _validate_game(record)
    except (TypeError, KeyError, AttributeError, IndexError, OverflowError) as error:
        raise ValueError('Invalid compilation paths: ' + type(error).__name__) from error


def _validate_game(record) -> dict:
    _need(isinstance(record, dict) and set(record) == {'schema', 'game', 'identity', 'cpus', 'devices'})
    _need(type(record['schema']) is int and record['schema'] == SCHEMA, 'Unsupported paths schema.')
    game = record['game']
    _need(isinstance(game, str) and GAME_KEY.fullmatch(game), 'Invalid game key.')
    system = game.split(':', 1)[0]
    identity = record['identity']
    _need(isinstance(identity, dict) and set(identity) == {'system', 'sources', 'layout'}
          and identity['system'] == system, 'Invalid game identity.')
    sources = _validate_sources(system, identity['sources'])
    _validate_layout(system, identity['layout'])
    if system == 'ng':
        _need(game == 'ng:' + ng_key(sources['cart']['sha256'], sources['bios']['sha256']),
              'Neo Geo hints do not match their cart/BIOS key.')
    cpus = record['cpus']
    _need(isinstance(cpus, dict) and cpus and set(cpus) <= {c for c, _ in SYSTEM_SECTIONS[system]},
          'Invalid CPU sections.')
    for cpu, section in cpus.items():
        _need(isinstance(section, dict) and set(section) == {'map', 'core', 'paths'}
              and isinstance(section['core'], str) and HEX40.fullmatch(section['core']),
              'Invalid CPU section.')
        _need((cpu, section['map']) in SYSTEM_SECTIONS[system], 'Unknown CPU memory map.')
        _validate_paths(PROFILES[(cpu, section['map'])], system, sources, section['paths'])
    devices = record['devices']
    _need(isinstance(devices, dict) and set(devices) <= DEVICES.keys(), 'Invalid devices.')
    for name, device in devices.items():
        spec = DEVICES[name]
        _need(system in spec['systems'] and isinstance(device, dict) and set(device) == {'core', 'paths'}
              and isinstance(device['core'], str) and HEX40.fullmatch(device['core'])
              and isinstance(device['paths'], dict) and set(device['paths']) <= spec['kinds'].keys(),
              'Invalid device section.')
        for kind, blocks in device['paths'].items():
            _need(isinstance(blocks, list) and len(blocks) <= 1, 'Invalid device blocks.')
            for block in blocks:
                _need(isinstance(block, dict) and set(block) == {'shape', 'table'} and block['shape'] == 'pair',
                      'Invalid device block.')
                for site, target in decode_table(block['table'], 2, spec['kinds'][kind]):
                    _need(site <= 0xffffff and target <= 0xffffff, 'Invalid device target.')
    return record


def _validate_sources(system, sources) -> dict:
    bounds = SOURCE_BOUNDS[system]
    _need(isinstance(sources, dict) and sources, 'Invalid sources.')
    for name, source in sources.items():
        role = source_role(name, bounds) if isinstance(name, str) else None
        _need(role in bounds and SOURCE_NAME.fullmatch(name), 'Unknown source.')
        _need(isinstance(source, dict) and {'bytes'} <= set(source) <= {'bytes', 'sha256'}
              and type(source['bytes']) is int and bounds[role][0] <= source['bytes'] <= bounds[role][1],
              'Invalid source size.')
        if 'sha256' in source:
            _need(isinstance(source['sha256'], str) and HEX64.fullmatch(source['sha256']), 'Invalid source hash.')
    for name in REQUIRED_SOURCES.get(system, ()):
        _need(name in sources, 'Missing source.')
    for name in HASHED_SOURCES.get(system, ()):
        _need('sha256' in sources[name], 'Missing source hash.')
    if system == 'ng':
        p, m1, cart = (sources[n]['bytes'] for n in ('p', 'm1', 'cart'))
        _need(not p & 1 and not m1 & (m1 - 1) and p + m1 <= cart, 'Inconsistent Neo Geo compilation region sizes.')
    return sources


def _validate_layout(system, layout) -> None:
    _need(isinstance(layout, dict), 'Invalid layout.')
    pin = lambda value: isinstance(value, str) and HEX40.fullmatch(value)
    if system == 'ng':
        _need(set(layout) == {'loader'} and pin(layout['loader']), 'Invalid Neo Geo layout.')
    elif system == 'cps1':
        _need(set(layout) <= {'catalogue'} and all(pin(v) for v in layout.values()), 'Invalid CPS-1 layout.')
    elif system == 'x68':
        drives = layout.get('initial_drives', [])
        _need(set(layout) <= {'ram_mib', 'initial_drives'} and type(layout.get('ram_mib', 0)) is int
              and isinstance(drives, list) and all(type(v) is int for v in drives), 'Invalid X68000 layout.')
    else:
        _need(layout == {}, 'Invalid layout.')


def _validate_paths(profile: Profile, system, sources, paths) -> None:
    _need(isinstance(paths, dict) and set(paths) <= set(KINDS), 'Invalid path kinds.')
    seen, state = set(), {'budget': 0, 'entries': 0}
    for kind, blocks in paths.items():
        _need(isinstance(blocks, list), 'Invalid path blocks.')
        for block in blocks:
            _need(isinstance(block, dict) and isinstance(block.get('shape'), str)
                  and block['shape'] in SHAPES and SHAPES[block['shape']][0] == kind
                  and block['shape'] in profile.caps, 'Unknown path shape for this CPU.')
            _need(block['shape'] not in seen, 'A path shape appears twice.')
            seen.add(block['shape'])
            _validate_block(profile, system, sources, block, state)
    _need(state['budget'] <= profile.budget, 'SPC700 compilation range budget exceeded.')
    # Neo Geo counts explicit roots and delta-coded roots against one bound.
    _need(state['entries'] <= profile.caps.get('phys', 0), 'Too many ROM entries.')


def _block_sources(profile, system, sources, shape, block) -> list:
    extra = set(block) - {'shape', 'table', 'groups'}
    if extra == {'src'}:
        names = [block['src']]
    elif extra == {'srcs'}:
        names = block['srcs']
        _need(isinstance(names, list) and len(names) >= 2 and len(set(names)) == len(names),
              'Invalid block sources.')
    else:
        _need(not extra and shape == 'sega5', 'Invalid block sources.')
        names = []
    for name in names:
        _need(isinstance(name, str) and name in sources
              and source_role(name, SOURCE_BOUNDS[system]) in profile.roles,
              'A path points into a source this CPU cannot use.')
    return names


def _validate_block(profile: Profile, system, sources, block, state) -> None:
    shape = block['shape']
    names = _block_sources(profile, system, sources, shape, block)
    sizes = [sources[n]['bytes'] for n in names]
    cols = SHAPES[shape][1]
    _need(('groups' in block) == (cols is None) and ('table' in block) == (cols is not None),
          'Invalid block payload.')
    if shape == 'phys_deltas':
        return _check_phys_deltas(profile, names, sizes, block['groups'], state)
    if shape == 'spc_deltas':
        return _check_spc_deltas(profile, sizes[0], block['groups'], state)
    if len(names) > 1:
        cols = ('src',) + cols
    rows = decode_table(block['table'], len(cols), profile.caps[shape])
    if len(names) > 1 and rows:
        _need(max(row[0] for row in rows) < len(names), 'A path names an unknown source.')
    if shape in ('gb_offsets', 'gb_rows', 'nes_rows'):
        _check_mapped(profile, shape, rows, sizes[0])
    elif shape in ('insn', 'insn_masked', 'span'):
        _check_code(profile, shape, len(names) > 1, rows, sizes)
    else:
        state['budget'] += _check_simple(profile, shape, len(names) > 1, rows, sizes)
        state['entries'] += len(rows) if shape == 'phys' else 0


def _check_simple(profile, shape, multi, rows, sizes) -> int:
    """Entries, windows and opcode pointers; returns SPC700 decoded positions."""
    positions = 0
    for row in rows:
        if shape == 'sega5':
            pc, b0, b1, b2, _crc = row
            _need(pc < profile.pc_below and b0 <= 255 and b1 <= 255 and b2 <= 255, 'Invalid ROM compilation entry.')
            continue
        size = sizes[row[0]] if multi else sizes[0]
        value = row[1:] if multi else row
        if shape == 'phys':
            offset = value[0]
            _need(not offset % profile.entry_align and profile.entry_min <= offset
                  and offset + profile.entry_tail <= size, 'Invalid ROM compilation entry.')
        elif shape == 'window4':
            _need(value[0] + 4 <= size, 'Compilation pattern outside ROM.')
        elif shape in ('opcode_ptr', 'spc_refs'):
            _need(_in_window(profile.windows, value[0], value[0]) and value[1] < size, 'Invalid opcode reference.')
            positions += shape == 'spc_refs'
        elif shape == 'spc_ranges':
            first, last, offset = value
            _need(first <= last and _in_window(profile.windows, first, last) and offset < size,
                  'Invalid SPC700 compilation range.')
            positions += last - first + 1
        else:
            first, mask, offset = value
            _need(first <= 65504 and not first & 31 and mask and offset < size, 'Invalid SPC700 compilation bitmap.')
            if not _in_window(profile.windows, first, first + 31):
                for bit in range(32):
                    _need(not mask >> bit & 1 or _in_window(profile.windows, first + bit, first + bit),
                          'Invalid SPC700 compilation bitmap.')
            positions += mask.bit_count()
    return positions


def _check_mapped(profile, shape, rows, size) -> None:
    """Banked ROM entries: offset = bank * unit + (pc mod unit)."""
    unit, banks = profile.unit, size // profile.unit
    low, high = profile.pc_window
    for row in rows:
        _need(row[0] // unit < banks, 'Invalid ROM compilation entry.')
        if shape != 'gb_offsets':
            _need(low <= row[1] <= high and (row[1] - row[0]) % unit == 0, 'Invalid ROM compilation entry.')


def _check_code(profile, shape, multi, rows, sizes) -> None:
    """RAM-resident instructions: [src,] address, offset, length [, guard]."""
    covered = 0
    low, high = (1, profile.span_max) if shape == 'span' else profile.length
    for row in rows:
        size = sizes[row[0]] if multi else sizes[0]
        value = row[1:] if multi else row
        address, offset, length = value[:3]
        _need(low <= length <= high and not length % profile.length_align and not offset % profile.offset_align
              and offset + length <= size, 'Compilation reference outside its source.')
        _need(not (address - profile.address_base) % profile.address_align
              and _in_window(profile.windows, address, address + length - 1 if profile.contained else address),
              'Invalid RAM code address.')
        if shape == 'insn_masked':
            _need(1 <= value[3] <= 15 and value[3] & 1, 'Invalid guard mask.')
        covered += length
    _need(shape != 'span' or covered <= SPAN_BYTES, 'Spans cover too much.')


def _check_phys_deltas(profile, names, sizes, groups, state) -> None:
    """Delta-coded Neo Geo roots: at most one group per region, even, strictly increasing."""
    cap = profile.caps['phys']
    _need(isinstance(groups, list) and len(groups) <= profile.caps['phys_deltas'], 'Invalid Neo Geo ROM delta blocks.')
    seen = set()
    for group in groups:
        _need(isinstance(group, list) and len(group) == 2 and isinstance(group[0], str)
              and group[0] in names and group[0] not in seen, 'Invalid Neo Geo ROM delta region.')
        seen.add(group[0])
        positions = decode_seq(group[1], cap)
        state['entries'] += len(positions)
        _need(positions and 0 <= positions[0] and positions[-1] <= U32 and not positions[0] & 1
              and all(b - a >= 2 and not b & 1 for a, b in zip(positions, positions[1:]))
              and positions[-1] + profile.entry_tail <= sizes[names.index(group[0])],
              'Invalid Neo Geo ROM delta offset.')


def _check_spc_deltas(profile, size, groups, state) -> None:
    _need(isinstance(groups, list) and len(groups) <= profile.caps['spc_deltas'],
          'Invalid SPC700 compilation deltas.')
    for group in groups:
        _need(isinstance(group, list) and len(group) == 2 and type(group[0]) is int and 0 <= group[0] < size
              and isinstance(group[1], list) and 1 <= len(group[1]) <= 65536, 'Invalid SPC700 compilation deltas.')
        state['budget'] += len(group[1])
        _need(state['budget'] <= profile.budget, 'SPC700 compilation range budget exceeded.')
        pc = 0
        for index, delta in enumerate(group[1]):
            _need(type(delta) is int and (0 if index == 0 else 1) <= delta <= 65535,
                  'Invalid SPC700 compilation delta.')
            pc += delta
            _need(_in_window(profile.windows, pc, pc), 'Invalid SPC700 compilation address.')


def validate_games(document) -> dict:
    """A schema 3 bank: {"schema": 3, "games": {game key: record}}."""
    _need(isinstance(document, dict) and set(document) == {'schema', 'games'}
          and type(document['schema']) is int and document['schema'] == SCHEMA
          and isinstance(document['games'], dict), 'Invalid compilation paths bank.')
    counts = {}
    for key, record in document['games'].items():
        validate_game(record)
        _need(isinstance(record, dict) and record['game'] == key, 'A game is filed under another key.')
        system = key.split(':', 1)[0]
        counts[system] = counts.get(system, 0) + 1
        _need(counts[system] <= GAMES_PER_SYSTEM, 'Invalid compilation knowledge catalogue.')
    return document


# --- Adapters: schema 1 <-> schema 3 ---------------------------------------------

def _legacy_rows(record: dict, field: str, width: int | None) -> list:
    rows = record[field]
    if not isinstance(rows, list):
        raise ValueError('Invalid compilation knowledge entries.')
    for row in rows:
        if width is None:
            continue
        if (not isinstance(row, list) or len(row) != width
                or any(type(n) is not int or not 0 <= n <= U32 for n in row)):
            raise ValueError('Invalid compilation knowledge entries.')
    return rows


def _table_block(shape, rows, width, source=None, sources=None) -> dict:
    block = {'shape': shape, 'table': encode_table(rows, width)}
    if sources:
        block['srcs'] = list(sources)
    elif source:
        block['src'] = source
    return block


def to_v3(system: str, identity: str, record: dict) -> dict:
    """The schema 3 form of one schema 1 record (any console, Neo Geo included).

    Total on the records the schema 1 validators accept; ValueError for what
    schema 1 itself cannot hold (a malformed shape, an unknown region).
    """
    try:
        return _to_v3(system, identity, record)
    except (TypeError, KeyError, AttributeError, IndexError, OverflowError) as error:
        raise ValueError('Invalid compilation knowledge record: ' + type(error).__name__) from error


def _to_v3(system, identity, record) -> dict:
    if system not in LEGACY_WIDTHS or not isinstance(identity, str) or not isinstance(record, dict):
        raise ValueError('Invalid compilation knowledge record.')
    if system == 'ng':
        return _ng_to_v3(identity, record)
    fields = LEGACY_WIDTHS[system]
    if (not {'engine', 'rom_bytes'} <= record.keys() or not set(record) <= {'engine', 'rom_bytes', *fields}
            or not isinstance(record['engine'], str) or type(record['rom_bytes']) is not int):
        raise ValueError('Invalid compilation knowledge identity.')
    sections = {}
    for cpu, name in SYSTEM_SECTIONS[system]:
        sections[(cpu, name)] = {'map': name, 'core': record['engine'], 'paths': {}}

    def add(cpu, name, kind, block):
        sections[(cpu, name)]['paths'].setdefault(kind, []).append(block)

    for field, width in fields.items():
        if field not in record:
            continue
        rows = _legacy_rows(record, field, width)
        if field == 'rom_entries' and system in ('sms', 'gg'):
            add('z80', 'sms', 'entries', _table_block('sega5', rows, 5))
        elif field == 'pattern_refs':
            add('z80', 'sms', 'windows', _table_block('window4', rows, 1, 'rom'))
        elif field == 'rom_entries' and system == 'gb':
            if all((r[0] == 0 and r[1] < 0x4000) or (r[0] >= 1 and 0x4000 <= r[1] < 0x8000) for r in rows):
                block = _table_block('gb_offsets', [[b * 0x4000 + (p & 0x3fff)] for b, p in rows], 1, 'rom')
            else:
                block = _table_block('gb_rows', [[b * 0x4000 + (p & 0x3fff), p] for b, p in rows], 2, 'rom')
            add('sm83', 'gb', 'entries', block)
        elif field == 'rom_entries' and system == 'nes':
            add('mos6502', 'nes', 'entries',
                _table_block('nes_rows', [[b * 0x1000 + (p & 0xfff), p] for b, p in rows], 2, 'rom'))
        elif field == 'ram_opcode_refs':
            cpu = 'mos6502' if system == 'nes' else 'w65c816'
            add(cpu, system, 'ram_code', _table_block('opcode_ptr', rows, 2, 'rom'))
        elif field == 'rom_entries':
            add('m68k', 'md', 'entries', _table_block('phys', rows, 1, 'rom'))
        elif field == 'ram_refs' and system == 'md':
            add('m68k', 'md', 'ram_code', _table_block('insn', rows, 3, 'rom'))
        elif field == 'z80_refs':
            add('z80', 'md-sound', 'ram_code', _table_block('insn', rows, 3, 'rom'))
        elif field == 'ram_refs':
            add('w65c816', 'snes', 'ram_code', _table_block('insn', rows, 3, 'rom'))
        elif field == 'spc_deltas':
            _validate_delta_rows(rows)
            add('spc700', 'snes', 'ram_code', {'shape': 'spc_deltas', 'src': 'rom', 'groups': [list(r) for r in rows]})
        else:
            add('spc700', 'snes', 'ram_code', _table_block(field, rows, width, 'rom'))
    return {'schema': SCHEMA, 'game': f'{system}:{identity}',
            'identity': {'system': system, 'sources': {'rom': {'bytes': record['rom_bytes']}}, 'layout': {}},
            'cpus': {cpu: section for (cpu, _), section in sections.items()}, 'devices': {}}


def _validate_delta_rows(rows) -> None:
    for row in rows:
        if (not isinstance(row, list) or len(row) != 2 or type(row[0]) is not int or not 0 <= row[0] <= U32
                or not isinstance(row[1], list) or any(type(d) is not int or not 0 <= d <= U32 for d in row[1])):
            raise ValueError('Invalid SPC700 compilation deltas.')


def _ng_to_v3(identity, record) -> dict:
    required = set(NG_IDENTITY_FIELDS) | {'rom_entries', 'ram_refs', 'z80_refs'}
    if not isinstance(record, dict) or not required <= set(record) <= required | {'rom_deltas'}:
        raise ValueError('Invalid Neo Geo compilation fields.')
    for name in ('engine', 'loader', 'cart', 'bios'):
        if not isinstance(record[name], str):
            raise ValueError('Invalid Neo Geo compilation identity.')
    for name in ('rom_bytes', 'p_bytes', 'bios_bytes', 'm1_bytes', 'sm1_bytes'):
        if type(record[name]) is not int:
            raise ValueError('Invalid Neo Geo compilation region size.')
    srcs = {1: 0, 2: 1}, {3: 0, 4: 1}
    base = PROFILES[('m68k', 'ng')].address_base
    m68k, z80 = {'map': 'ng', 'core': record['engine'], 'paths': {}}, {'map': 'ng-sound', 'core': record['engine'], 'paths': {}}
    rows = _legacy_rows(record, 'rom_entries', 2)
    m68k['paths']['entries'] = [_table_block('phys', [[_region(srcs[0], r), o] for r, o in rows], 2, sources=('p', 'bios'))]
    if 'rom_deltas' in record:
        if not isinstance(record['rom_deltas'], list):
            raise ValueError('Invalid Neo Geo ROM delta blocks.')
        groups = []
        for block in record['rom_deltas']:
            if (not isinstance(block, list) or len(block) < 2 or any(type(n) is not int or not 0 <= n <= U32 for n in block)
                    or block[0] not in (1, 2)):
                raise ValueError('Invalid Neo Geo ROM delta block.')
            positions, current = [block[1]], block[1]
            for gap in block[2:]:
                current += gap; positions.append(current)
            groups.append(['p' if block[0] == 1 else 'bios', encode_seq(positions)])
        m68k['paths']['entries'].append({'shape': 'phys_deltas', 'srcs': ['p', 'bios'], 'groups': groups})
    rows = _legacy_rows(record, 'ram_refs', 4)
    m68k['paths']['ram_code'] = [_table_block('insn', [[_region(srcs[0], r), base + pc, o, n] for pc, r, o, n in rows],
                                              4, sources=('p', 'bios'))]
    rows = _legacy_rows(record, 'z80_refs', 4)
    z80['paths']['ram_code'] = [_table_block('insn_masked', [[_region(srcs[1], r), pc, o, 4, mask] for pc, r, o, mask in rows],
                                             5, sources=('m1', 'sm1'))]
    sizes = {'cart': {'bytes': record['rom_bytes'], 'sha256': record['cart']},
             'p': {'bytes': record['p_bytes']}, 'bios': {'bytes': record['bios_bytes'], 'sha256': record['bios']},
             'm1': {'bytes': record['m1_bytes']}, 'sm1': {'bytes': record['sm1_bytes']}}
    return {'schema': SCHEMA, 'game': 'ng:' + identity,
            'identity': {'system': 'ng', 'sources': sizes, 'layout': {'loader': record['loader']}},
            'cpus': {'m68k': m68k, 'z80': z80}, 'devices': {}}


def _region(mapping, region) -> int:
    if region not in mapping:
        raise ValueError('Neo Geo compilation reference outside its region.')
    return mapping[region]


def to_legacy(document: dict, *, validate: bool = True) -> tuple[str, str, dict]:
    """(system, identity, schema 1 record). ValueError when schema 1 cannot hold it."""
    try:
        if validate:
            validate_game(document)
        return _to_legacy(document)
    except (TypeError, KeyError, AttributeError, IndexError, OverflowError) as error:
        raise ValueError('Invalid compilation paths: ' + type(error).__name__) from error


# Which schema 1 field a (cpu, shape) block is.
_FIELD_OF = {('z80', 'sega5'): 'rom_entries', ('z80', 'window4'): 'pattern_refs',
             ('sm83', 'gb_offsets'): 'rom_entries', ('sm83', 'gb_rows'): 'rom_entries',
             ('mos6502', 'nes_rows'): 'rom_entries', ('mos6502', 'opcode_ptr'): 'ram_opcode_refs',
             ('m68k', 'phys'): 'rom_entries', ('m68k', 'phys_deltas'): 'rom_deltas',
             ('m68k', 'insn'): 'ram_refs', ('z80', 'insn'): 'z80_refs', ('z80', 'insn_masked'): 'z80_refs',
             ('w65c816', 'insn'): 'ram_refs', ('w65c816', 'opcode_ptr'): 'ram_opcode_refs',
             **{('spc700', shape): shape for shape in ('spc_refs', 'spc_ranges', 'spc_bitmaps', 'spc_deltas')}}


def _to_legacy(document) -> tuple[str, str, dict]:
    game, identity = document['game'], document['identity']
    system, key = game.split(':', 1)
    if system not in LEGACY_WIDTHS:
        raise ValueError('This machine has no schema 1 form.')
    cores = {section['core'] for section in document['cpus'].values()}
    if len(cores) != 1 or document['devices']:
        raise ValueError('Schema 1 holds one core and no device.')
    record = {'engine': cores.pop()}
    if system == 'ng':
        sources = identity['sources']
        record.update({'loader': identity['layout']['loader'], 'cart': sources['cart']['sha256'],
                       'bios': sources['bios']['sha256'], 'rom_bytes': sources['cart']['bytes'],
                       'p_bytes': sources['p']['bytes'], 'bios_bytes': sources['bios']['bytes'],
                       'm1_bytes': sources['m1']['bytes'], 'sm1_bytes': sources['sm1']['bytes']})
    else:
        record['rom_bytes'] = identity['sources']['rom']['bytes']
    for cpu, section in document['cpus'].items():
        profile = PROFILES[(cpu, section['map'])]
        for kind, blocks in section['paths'].items():
            for block in blocks:
                shape = block['shape']
                field = _FIELD_OF.get((cpu, shape))
                if field is None or field in record:
                    raise ValueError('This path shape has no schema 1 field.')
                record[field] = _block_to_legacy(system, profile, shape, block)
    if system == 'ng':
        for field in ('rom_entries', 'ram_refs', 'z80_refs'):
            if field not in record:
                raise ValueError('Neo Geo records always list rom_entries, ram_refs and z80_refs.')
    return system, key, record


def _block_to_legacy(system, profile, shape, block) -> list:
    limit = profile.caps[shape]
    if shape == 'spc_deltas':
        return [list(group) for group in block['groups']]
    if shape == 'phys_deltas':
        out = []
        for source, encoded in block['groups']:
            positions = decode_seq(encoded, profile.caps['phys'])
            out.append([NG_REGIONS[source], positions[0], *(b - a for a, b in zip(positions, positions[1:]))])
        return out
    multi = 'srcs' in block
    cols = SHAPES[shape][1]
    rows = decode_table(block['table'], len(cols) + multi, limit, unsigned=False)
    names = block.get('srcs')
    region = (lambda row: NG_REGIONS[names[row[0]]]) if multi else None
    if multi:
        rows = [(region(row), *row[1:]) for row in rows]
    if shape in ('sega5', 'window4', 'opcode_ptr', 'spc_refs', 'spc_ranges', 'spc_bitmaps'):
        return [list(row) for row in rows]
    if shape == 'phys':
        return [list(row) for row in rows]
    if shape == 'gb_offsets':
        return [[o >> 14, o if o < 0x4000 else 0x4000 | (o & 0x3fff)] for (o,) in rows]
    if shape == 'gb_rows':
        return [[o >> 14, p] for o, p in rows]
    if shape == 'nes_rows':
        return [[o >> 12, p] for o, p in rows]
    if shape == 'insn' and multi:
        return [[a - profile.address_base, r, o, n] for r, a, o, n in rows]
    if shape == 'insn':
        return [list(row) for row in rows]
    if shape == 'insn_masked':
        if any(n != 4 for _, _, _, n, _ in rows):
            raise ValueError('Schema 1 Z80 references are four bytes.')
        return [[a, r, o, g] for r, a, o, n, g in rows]
    raise ValueError('This path shape has no schema 1 form.')


def bank_to_v3(payload: dict) -> dict:
    """{"schema": 1, "consoles": ...} -> {"schema": 3, "games": ...} (no empty console survives)."""
    games = {}
    for system, records in payload['consoles'].items():
        for identity, record in records.items():
            document = to_v3(system, identity, record)
            games[document['game']] = document
    return {'schema': SCHEMA, 'games': games}


def bank_to_legacy(document: dict, *, validate: bool = True) -> dict:
    consoles = {}
    for key, game in document['games'].items():
        system, identity, record = to_legacy(game, validate=validate)
        consoles.setdefault(system, {})[identity] = record
    return {'schema': 1, 'consoles': consoles}
