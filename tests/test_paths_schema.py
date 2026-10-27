"""Schema 3 of the compilation paths (CPU-keyed): lossless adapters, parity, codecs.

`retrorecomp.path_profiles` is the module `knowledge` delegates to since 1.6.0 (stage B3);
the exchange, the shared base and the service client use its schema 3 half. These tests pin
what it must keep true:

  a. `to_legacy(to_v3(r)) == r` for every record shape, on fixtures and on the
     maintainer snapshot (a deterministic sample by default; every record when
     RETRO_RECOMP_PATHS_FULL=1, about a minute and a half and 1.2 GB of memory);
  b. `validate_game` accepts and rejects what `knowledge.validate_payload` and
     `neogeo_knowledge.validate_record` do, on a mutation corpus, except for
     the documented places where schema 1's shared validator is looser than the
     local code (`path_profiles.STRICTER_THAN_V2`);
  c. the integer codecs are lossless, bounded before expansion, and the size
     against schema 1 is printed (never asserted).
"""
import copy
from functools import lru_cache
import gzip
import itertools
import json
import os
from pathlib import Path
import random
import re
import unittest

from retrorecomp import compilation_inputs, knowledge, neogeo_knowledge, path_profiles as pp

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / 'assets' / 'compilation-knowledge.json.gz'
FULL = os.environ.get('RETRO_RECOMP_PATHS_FULL') == '1'
U32 = 0xffffffff
SHA, ENGINE = '1' * 64, 'a' * 40
CART, BIOS, LOADER = 'a' * 64, 'b' * 64, 'c' * 40
NG_IDENTITY = neogeo_knowledge.key(CART, BIOS)


def ng_record(**fields):
    record = {'engine': ENGINE, 'loader': LOADER, 'cart': CART, 'bios': BIOS, 'rom_bytes': 200000,
              'p_bytes': 4096, 'bios_bytes': 131072, 'm1_bytes': 65536, 'sm1_bytes': 131072,
              # Regions interleaved and unsorted on purpose: order must survive.
              'rom_entries': [[2, 8], [1, 0], [1, 2], [2, 0]],
              'ram_refs': [[0xfc00, 2, 6, 4], [0x10, 1, 2, 2], [0xfc00, 1, 8, 6]],
              'z80_refs': [[0xfffd, 4, 10, 1], [0xf800, 3, 0, 15], [0xf801, 4, 2, 7]]}
    return {**record, **fields}


# One valid record of every shape, deliberately unsorted or repeated where it can be.
FIXTURES = {
    'sms': ('sms', SHA, {'engine': ENGINE, 'rom_bytes': 262144,
                         'rom_entries': [[1448, 0, 1, 130, 412644236], [1508, 0, 1, 130, 3689887089]],
                         'pattern_refs': [[100], [96], [100]]}),
    'gg': ('gg', SHA, {'engine': ENGINE, 'rom_bytes': 131072, 'rom_entries': [[0x100, 0, 0, 0, 7]],
                       'pattern_refs': []}),
    'gb': ('gb', SHA, {'engine': ENGINE, 'rom_bytes': 65536,
                       'rom_entries': [[0, 0x100], [1, 0x4200], [3, 0x7ff0], [1, 0x4000]]}),
    # Bank 0 with a pc in the switchable window: valid in schema 1, not derivable from the offset.
    'gb-window': ('gb', SHA, {'engine': ENGINE, 'rom_bytes': 65536, 'rom_entries': [[0, 0x4100], [2, 0x4100]]}),
    'nes': ('nes', SHA, {'engine': ENGINE, 'rom_bytes': 131072,
                         'rom_entries': [[0, 0x8000], [3, 0xc123], [3, 0xc123]],
                         'ram_opcode_refs': [[0x300, 5], [0x6100, 6], [0x300, 5]]}),
    'md': ('md', SHA, {'engine': ENGINE, 'rom_bytes': 1048576,
                       'rom_entries': [[0x200], [0x3a4], [0x3a6], [0x100000 - 8]],
                       'ram_refs': [[0xff0002, 4096, 8], [0xff0000, 4096, 2]],
                       'z80_refs': [[0x20, 5, 4], [0x100, 2100, 4], [0x100, 2048, 4], [0x1fff, 9, 4]]}),
    'snes': ('snes', SHA, {'engine': ENGINE, 'rom_bytes': 1048576,
                           'ram_refs': [[0x7e0100, 512, 4], [0x7e0000, 4, 4]],
                           'ram_opcode_refs': [[0x7e0200, 9], [0x100, 3], [0x7e0200, 9]],
                           'spc_refs': [[0x300, 7], [0x200, 7]], 'spc_ranges': [[0x400, 0x40f, 11]],
                           'spc_bitmaps': [[0x500, 0b1011, 12]], 'spc_deltas': [[13, [0x600, 2, 1]], [14, [0]]]}),
    'ng': ('ng', NG_IDENTITY, ng_record()),
    'ng-deltas': ('ng', NG_IDENTITY, ng_record(rom_entries=[[1, 6]], rom_deltas=[[2, 0, 2, 4], [1, 4, 2, 2, 8]])),
    # Fields present but empty are not fields that are absent.
    'md-empty': ('md', SHA, {'engine': ENGINE, 'rom_bytes': 8192, 'rom_entries': [], 'ram_refs': [], 'z80_refs': []}),
    'md-none': ('md', SHA, {'engine': ENGINE, 'rom_bytes': 8192}),
    'snes-none': ('snes', SHA, {'engine': ENGINE, 'rom_bytes': 8192}),
    'ng-empty': ('ng', NG_IDENTITY, ng_record(rom_entries=[], ram_refs=[], z80_refs=[], rom_deltas=[])),
}


def legacy_accepts(system, identity, record) -> bool:
    try:
        knowledge.validate_payload({'schema': 1, 'consoles': {system: {identity: record}}})
        if system == 'ng':
            neogeo_knowledge.validate_record(identity, record)
        return True
    except ValueError:
        return False


def v3_accepts(system, identity, record) -> bool:
    try:
        pp.validate_game(pp.to_v3(system, identity, record))
        return True
    except ValueError:
        return False


def numbers_only(test, value, path='$'):
    """A record is numbers and names: strings are keys, shape names or hex digests."""
    if isinstance(value, dict):
        for key, item in value.items():
            test.assertIsInstance(key, str)
            numbers_only(test, item, path + '.' + key)
    elif isinstance(value, list):
        for item in value:
            numbers_only(test, item, path + '[]')
    elif isinstance(value, str):
        test.assertRegex(value, r'^(?:[0-9a-f]{40}|[0-9a-f]{64}|[a-z0-9_-]{1,24}|[a-z0-9]+:[0-9a-f]{64})$', path)
    else:
        test.assertIs(type(value), int, path)


class RoundTripTests(unittest.TestCase):
    def test_every_record_shape_round_trips_exactly(self):
        for name, (system, identity, record) in FIXTURES.items():
            with self.subTest(name):
                document = pp.to_v3(system, identity, record)
                self.assertEqual(pp.validate_game(document), document)
                numbers_only(self, document)
                self.assertEqual(pp.to_legacy(document), (system, identity, record))
                # Through JSON as a file would carry it, and without re-validating.
                again = json.loads(json.dumps(document))
                self.assertEqual(pp.to_legacy(again, validate=False), (system, identity, record))
                self.assertEqual(document['game'], f'{system}:{identity}')

    def test_input_records_are_not_modified(self):
        for name, (system, identity, record) in FIXTURES.items():
            copied = copy.deepcopy(record)
            pp.to_v3(system, identity, record)
            self.assertEqual(copied, record, name)

    def test_banks_round_trip_and_validate(self):
        # Distinct identities inside a console: one hex key per fixture (Neo Geo's key is its own).
        payload = {'schema': 1, 'consoles': {}}
        for index, (system, identity, record) in enumerate(FIXTURES.values()):
            if system == 'ng':
                payload['consoles'].setdefault('ng', {}).setdefault(identity, record)
            else:
                payload['consoles'].setdefault(system, {})[f'{index:064x}'] = record
        bank = pp.bank_to_v3(payload)
        self.assertEqual(pp.validate_games(bank), bank)
        self.assertEqual(pp.bank_to_legacy(bank), payload)
        self.assertEqual(knowledge.validate_payload(copy.deepcopy(payload)), payload)

    def test_games_per_system_are_bounded_like_schema_1(self):
        system, _, record = FIXTURES['md-none']
        games = {}
        for index in range(4097):
            document = pp.to_v3(system, f'{index:064x}', record)
            games[document['game']] = document
        with self.assertRaises(ValueError):
            pp.validate_games({'schema': 3, 'games': games})
        games.pop(next(iter(games)))
        pp.validate_games({'schema': 3, 'games': games})
        with self.assertRaises(ValueError):
            pp.validate_games({'schema': 3, 'games': {'md:' + '0' * 64: next(iter(games.values()))}})

    def test_what_schema_1_cannot_hold_is_refused(self):
        # CPS-1 and X68000 have no schema 1 form; two cores or a device do not either.
        document = cps1_document()
        with self.assertRaises(ValueError):
            pp.to_legacy(document)
        document = pp.to_v3(*FIXTURES['md'])
        document['cpus']['z80']['core'] = 'b' * 40
        with self.assertRaises(ValueError):
            pp.to_legacy(document)
        document = pp.to_v3(*FIXTURES['snes'])
        document['devices'] = {'gsu': {'core': ENGINE, 'paths': {}}}
        with self.assertRaises(ValueError):
            pp.to_legacy(document)
        document = pp.to_v3(*FIXTURES['md'])
        document['cpus']['z80']['paths']['ram_code'][0]['table'] = pp.encode_table([[0, 0, 4, 1]], 4)
        document['cpus']['z80']['paths']['ram_code'][0]['shape'] = 'insn_masked'
        with self.assertRaises(ValueError):
            pp.to_legacy(document, validate=False)

    def test_the_maintainer_snapshot_sample_round_trips(self):
        if not SNAPSHOT.is_file():
            self.skipTest('The maintainer snapshot is not in this checkout.')
        sample = snapshot_sample()
        self.assertEqual({system for system, _, _ in sample}, {'gb', 'gg', 'md', 'nes', 'ng', 'sms', 'snes'})
        for system, identity, record in sample:
            with self.subTest(system=system, identity=identity[:8]):
                document = pp.to_v3(system, identity, record)
                pp.validate_game(document)
                self.assertEqual(pp.to_legacy(document, validate=False), (system, identity, record))

    @unittest.skipUnless(FULL, 'Set RETRO_RECOMP_PATHS_FULL=1 for the whole snapshot (about a minute and a half).')
    def test_the_whole_snapshot_round_trips(self):
        data = json.loads(gzip.open(SNAPSHOT, 'rb').read())
        count = 0
        for system, games in data['consoles'].items():
            for identity, record in games.items():
                document = pp.to_v3(system, identity, record)
                pp.validate_game(document)
                self.assertEqual(pp.to_legacy(document, validate=False), (system, identity, record), (system, identity))
                count += 1
        self.assertEqual(count, 1609)
        print('\n' + size_report(data['consoles'].items(), 'whole snapshot'))


@lru_cache(maxsize=1)
def snapshot_sample(per_console=6):
    """A deterministic sample read without parsing the whole 120 MB: the first,
    the last, the heaviest and evenly spaced records of each console."""
    raw = gzip.open(SNAPSHOT, 'rb').read()
    marks = [(m.start(), m.group(1).decode()) for m in re.finditer(rb'"(gb|gg|md|nes|ng|sms|snes)":\{', raw)]
    keys = [(m.start(), m.group(1).decode(), m.end() - 1) for m in re.finditer(rb'"([0-9a-f]{64})":\{', raw)]
    ends = [k[0] for k in keys[1:]] + [len(raw)]
    by_console = {}
    for (start, identity, brace), end in zip(keys, ends):
        system = [name for position, name in marks if position < start][-1]
        by_console.setdefault(system, []).append((identity, brace, end - start))
    text, decoder, sample = raw.decode('ascii'), json.JSONDecoder(), []
    for system, games in sorted(by_console.items()):
        picks = {0, len(games) - 1, max(range(len(games)), key=lambda i: games[i][2])}
        picks |= {i * len(games) // per_console for i in range(per_console)}
        for index in sorted(picks):
            identity, brace, _ = games[index]
            sample.append((system, identity, decoder.raw_decode(text, brace)[0]))
    return sample


def size_report(groups, label) -> str:
    """Bytes of schema 1 against schema 3 (compact JSON, and gzip level 9)."""
    dump = lambda value: json.dumps(value, separators=(',', ':'), sort_keys=True).encode()
    lines, total = [f'Schema 3 size against schema 1 ({label}): raw JSON bytes / gzip bytes'], [0, 0, 0, 0]
    for system, games in groups:
        row = [0, 0, 0, 0]
        for identity, record in games.items():
            old, new = dump(record), dump(pp.to_v3(system, identity, record))
            row[0] += len(old); row[1] += len(new)
            row[2] += len(gzip.compress(old, 9)); row[3] += len(gzip.compress(new, 9))
        total = [a + b for a, b in zip(total, row)]
        lines.append('  %-5s %11d -> %11d   %10d -> %10d' % (system, *row))
    lines.append('  %-5s %11d -> %11d   %10d -> %10d' % ('all', *total))
    return '\n'.join(lines)


class ParityTests(unittest.TestCase):
    """validate_game against the schema 1 validators, on the same records."""

    def classify(self, label, system, identity, record, stricter, wrong):
        old, new = legacy_accepts(system, identity, record), v3_accepts(system, identity, record)
        if old == new:
            return
        if old and not new:
            stricter.setdefault((system, label.split(':')[0]), (label, record))
        else:
            wrong.append((system, label, record))

    def sweep(self, system, identity, record):
        stricter, wrong, count = {}, [], 0
        for label, mutated in mutations(system, identity, record):
            count += 1
            key = identity
            if system == 'ng' and isinstance(mutated, dict) and all(
                    isinstance(mutated.get(n), str) for n in ('cart', 'bios')) and not label.startswith('stale'):
                key = neogeo_knowledge.key(mutated['cart'], mutated['bios'])
            self.classify(label, system, key, mutated, stricter, wrong)
        self.assertEqual(wrong, [], 'validate_game accepted what schema 1 refuses')
        return stricter, count

    def test_the_mutation_corpus_agrees_with_the_schema_1_validators(self):
        # The only places schema 3 is stricter: the documented ones, and each of them is exercised.
        expected = {('md', 'ram_refs'), ('md', 'z80_refs'), ('snes', 'ram_refs')}
        found, total = set(), 0
        for name in ('sms', 'gg', 'gb', 'nes', 'md', 'snes', 'ng', 'ng-deltas'):
            system, identity, record = FIXTURES[name]
            stricter, count = self.sweep(system, identity, record)
            found |= set(stricter)
            total += count
        self.assertGreater(total, 5000)
        self.assertEqual(found, expected)

    def test_the_documented_differences_are_exactly_these(self):
        md = FIXTURES['md'][2]
        snes = FIXTURES['snes'][2]
        cases = {
            'md.ram_refs.address': ('md', 'ram_refs', [0x100, 4096, 8], md),
            'md.ram_refs.length': ('md', 'ram_refs', [0xff0000, 4096, 3], md),
            'md.z80_refs.pc': ('md', 'z80_refs', [0x4000, 5, 4], md),
            'md.z80_refs.length': ('md', 'z80_refs', [0x100, 5, 8], md),
            'snes.ram_refs.length': ('snes', 'ram_refs', [0x7e0100, 512, 8], snes),
            'snes.ram_refs.address': ('snes', 'ram_refs', [0x1000000, 512, 4], snes),
        }
        self.assertEqual(set(cases), set(pp.STRICTER_THAN_V2))
        for key, (system, field, row, base) in cases.items():
            record = copy.deepcopy(base)
            record[field] = [row]
            with self.subTest(key):
                self.assertTrue(legacy_accepts(system, SHA, record), 'schema 1 accepts it')
                self.assertFalse(v3_accepts(system, SHA, record), 'schema 3 follows the local validator')

    def test_row_caps_and_the_spc700_budget_agree(self):
        samples = {('sms', 'rom_entries'): [1448, 0, 1, 130, 7], ('sms', 'pattern_refs'): [100],
                   ('gb', 'rom_entries'): [1, 0x4200], ('nes', 'rom_entries'): [3, 0xc123],
                   ('nes', 'ram_opcode_refs'): [0x300, 5], ('md', 'rom_entries'): [0x200],
                   ('md', 'ram_refs'): [0xff0000, 4096, 8], ('md', 'z80_refs'): [0x100, 2048, 4],
                   ('snes', 'ram_refs'): [0x7e0100, 512, 4], ('snes', 'ram_opcode_refs'): [0x100, 3],
                   ('snes', 'spc_refs'): [0x300, 7], ('snes', 'spc_ranges'): [0x400, 0x400, 11],
                   ('snes', 'spc_bitmaps'): [0x500, 1, 12], ('snes', 'spc_deltas'): [13, [5]]}
        for (system, field), row in samples.items():
            cap = knowledge.FIELDS[system][field][1]
            if cap > 65536 and not FULL:
                continue    # the 262,144-row SPC700 caps run with RETRO_RECOMP_PATHS_FULL=1
            for count in (cap, cap + 1):
                record = {'engine': ENGINE, 'rom_bytes': 1048576, field: [row] * count}
                with self.subTest(system=system, field=field, rows=count):
                    self.assertEqual(legacy_accepts(system, SHA, record), count == cap)
                    self.assertEqual(v3_accepts(system, SHA, record), count == cap)
        refs = [[0x300, 7]] * 200000
        for extra, accepted in (([[0x100, 0x100 + 62143, 5]], True), ([[0x100, 0x100 + 62144, 5]], False)):
            record = {'engine': ENGINE, 'rom_bytes': 1048576, 'spc_refs': refs, 'spc_ranges': extra}
            self.assertEqual(legacy_accepts('snes', SHA, record), accepted)
            self.assertEqual(v3_accepts('snes', SHA, record), accepted)

    def test_neo_geo_entry_count_is_shared_by_roots_and_deltas(self):
        cap = neogeo_knowledge.FIELDS['rom_entries'][1]
        cases = [(cap - 1, [[1, 0]], True), (cap, [[1, 0]], False)]
        if FULL:
            cases += [(cap - 3, [[1, 0, 2, 2]], True), (cap - 2, [[1, 0, 2, 2]], False)]
        for rows, deltas, accepted in cases:
            record = ng_record(rom_entries=[[1, 0]] * rows, rom_deltas=deltas, p_bytes=16 << 20, rom_bytes=17 << 20)
            with self.subTest(rows=rows):
                self.assertEqual(legacy_accepts('ng', NG_IDENTITY, record), accepted)
                self.assertEqual(v3_accepts('ng', NG_IDENTITY, record), accepted)

    def test_the_limits_match_the_schema_1_tables(self):
        for system, fields in pp.LEGACY_WIDTHS.items():
            for field, width in fields.items():
                if system == 'ng':
                    self.assertEqual(width, neogeo_knowledge.FIELDS[field][0], field)
                elif field != 'spc_deltas':
                    self.assertEqual(width, knowledge.FIELDS[system][field][0], (system, field))
            self.assertEqual(set(fields), set(neogeo_knowledge.FIELDS if system == 'ng' else knowledge.FIELDS[system]))
        self.assertEqual(pp.SOURCE_BOUNDS['ng'], {'cart': neogeo_knowledge.SIZE_BOUNDS['rom_bytes'],
                                                  'p': neogeo_knowledge.SIZE_BOUNDS['p_bytes'],
                                                  'bios': neogeo_knowledge.SIZE_BOUNDS['bios_bytes'],
                                                  'm1': neogeo_knowledge.SIZE_BOUNDS['m1_bytes'],
                                                  'sm1': neogeo_knowledge.SIZE_BOUNDS['sm1_bytes']})
        self.assertEqual(pp.PROFILES[('m68k', 'ng')].caps['phys_deltas'], neogeo_knowledge.DELTA_BLOCKS)
        self.assertEqual(pp.NG_IDENTITY_FIELDS, tuple(sorted(neogeo_knowledge.IDENTITY_FIELDS, key=pp.NG_IDENTITY_FIELDS.index)))
        self.assertEqual(pp.ng_key(CART, BIOS), neogeo_knowledge.key(CART, BIOS))
        # Each field's row cap is the cap of the shape that holds it.
        for name in ('sms', 'gb', 'nes', 'md', 'snes', 'ng', 'ng-deltas'):
            system, identity, record = FIXTURES[name]
            document = pp.to_v3(system, identity, record)
            table = neogeo_knowledge.FIELDS if system == 'ng' else knowledge.FIELDS[system]
            for cpu, section in document['cpus'].items():
                profile = pp.PROFILES[(cpu, section['map'])]
                for blocks in section['paths'].values():
                    for block in blocks:
                        field = pp._FIELD_OF[(cpu, block['shape'])]
                        if field == 'rom_deltas':
                            continue
                        self.assertEqual(profile.caps[block['shape']], table[field][1], (system, field))


VALUES = sorted({*range(0, 20), 0x7e, 0xef, 0xf0, 0xff, 0x100, 0x1ff, 0x200, 0x201, 0x2000, 0x3fff, 0x4000, 0x5fff,
                 0x6000, 0x7fff, 0x8000, 0xbf00, 0xbf01, 0xfffe, 0xffff, 0x10000, 0x100000, 0x10ffff, 0x110000,
                 0xe00000, 0xfffffe, 0xffffff, 0x1000000, U32, U32 + 1, 2 ** 64})
BAD = [-1, True, False, '1', None, 1.5, [1], {}]
PAIR = [0, 1, 2, 4, 8, 17, 0x200, 0x4000, 0x8000, 0xffff, 0xe00000, 0xff0000, 0x1000000]


def with_row(record, field, row_index, row):
    mutated = copy.deepcopy(record)
    mutated[field][row_index] = row
    return mutated


def mutations(system, identity, record):
    """(label, record) pairs: identity, structure, then a value sweep of every column."""
    yield 'record:none', None
    yield 'record:list', []
    yield 'record:extra-key', {**record, 'extra': []}
    for name in record:
        yield f'record:without-{name}', {k: v for k, v in record.items() if k != name}
    fields = [name for name in pp.LEGACY_WIDTHS[system] if record.get(name)]
    size = record['rom_bytes']
    if system == 'ng':
        yield from ng_identity_mutations(record)
    else:
        for engine in ('A' * 40, 'a' * 39, 'a' * 41, 'g' * 40, '', None, 5, ['a' * 40]):
            yield 'record:engine', {**record, 'engine': engine}
        for rom_bytes in (8191, 8192, 8193, 128 * 1024 * 1024 + 527, 128 * 1024 * 1024 + 528, 128 * 1024 * 1024 + 529,
                          *BAD, 2 ** 40):
            yield 'record:rom_bytes', {**record, 'rom_bytes': rom_bytes}
    sizes = [size, size - 1, size - 2, size - 3, size - 4, size - 8, size - 15, size - 16, size + 1,
             size // 0x4000 - 1, size // 0x4000, size // 4096 - 1, size // 4096]
    if system == 'ng':
        sizes += [record[n] + d for n in ('p_bytes', 'bios_bytes', 'm1_bytes', 'sm1_bytes') for d in (-1, 0, 1, -4, -2)]
    for field in fields:
        rows = record[field]
        if field == 'spc_deltas':
            yield from spc_delta_mutations(record, size)
        for bad in (None, 5, 'x', {}, {'a': 1}):
            yield f'{field}:not-a-list', {**record, field: bad}
        yield f'{field}:row-not-a-list', {**record, field: [5]}
        yield f'{field}:row-tuple', {**record, field: [tuple(rows[0])]}
        if field == 'spc_deltas':
            continue
        width = len(rows[0])
        yield f'{field}:short-row', with_row(record, field, 0, rows[0][:-1])
        yield f'{field}:long-row', with_row(record, field, 0, rows[0] + [0])
        yield f'{field}:empty-row', with_row(record, field, 0, [])
        for column in range(width):
            for value in sorted({*VALUES, *sizes}) + BAD:
                row = list(rows[0]); row[column] = value
                yield f'{field}:col{column}={value!r}', with_row(record, field, 0, row)
        for first, second in itertools.combinations(range(width), 2):
            for a, b in itertools.product(PAIR + sizes[:4], PAIR + sizes[:4]):
                row = list(rows[0]); row[first], row[second] = a, b
                yield f'{field}:cols{first},{second}', with_row(record, field, 0, row)
    if system == 'ng':
        yield from ng_delta_mutations(record)


def spc_delta_mutations(record, size):
    base = record['spc_deltas']
    for offset in (-1, 0, size - 1, size, size + 1, U32, U32 + 1, True, None):
        yield 'spc_deltas:offset', {**record, 'spc_deltas': [[offset, [3]], *base[1:]]}
    for deltas in ([], [0], [1], [0xef], [0xef, 1], [0xe0, 0x10], [0xe0, 0x11], [0xfe, 2], [0xff], [0xf0],
                   [65535], [65536], [0, 65535], [1, 65535], [0, 0], [3, 0], [3, 1, 0], [-1], [True], [1.5], [None],
                   [0, 1] * 3, [1] * 65536, [1] * 65537, 'x', None, 5):
        yield 'spc_deltas:deltas', {**record, 'spc_deltas': [[13, deltas]]}
    yield 'spc_deltas:one-field', {**record, 'spc_deltas': [[13]]}
    yield 'spc_deltas:three-fields', {**record, 'spc_deltas': [[13, [1], 0]]}
    yield 'spc_deltas:duplicate-offsets', {**record, 'spc_deltas': [[13, [1]], [13, [2]]]}


def ng_identity_mutations(record):
    for name, length in neogeo_knowledge.HEX_LENGTHS.items():
        for bad in (record[name].upper() if name in ('cart', 'bios') else 'A' * length, 'a' * (length - 1), 'a' * (length + 1),
                    'g' * length, '', None, 5):
            yield f'record:{name}', {**record, name: bad}
    for name, (low, high) in neogeo_knowledge.SIZE_BOUNDS.items():
        for value in (low - 1, low, low + 1, high - 1, high, high + 1, *BAD, 3 * low):
            yield f'record:{name}', {**record, name: value}
    for p, m1, total in ((4096, 65536, 69631), (4096, 65536, 69632), (4097, 65536, 200000), (4094, 65536, 200000),
                         (4096, 0x30000, 400000), (4096, 0x20000, 200000), (4096, 0x10000, 69632)):
        yield 'record:sizes', {**record, 'p_bytes': p, 'm1_bytes': m1, 'rom_bytes': total}
    yield 'stale:key', {**record, 'cart': 'd' * 64}
    yield 'stale:bios-key', {**record, 'bios': 'd' * 64}
    yield 'record:hex-cart', {**record, 'cart': 'z' * 64}
    yield 'record:extra', {**record, 'extra': 1}
    yield 'record:loader-removed', {k: v for k, v in record.items() if k != 'loader'}


def ng_delta_mutations(record):
    base = [[1, 4, 2, 4], [2, 0, 2]]
    yield 'rom_deltas:valid', {**record, 'rom_deltas': base}
    for deltas in ([], [[1, 0]], [[1]], [[1, 0], [1, 2]], [[1, 0], [2, 0], [1, 2]], [[3, 0]], [[0, 0]], [[1, 1]],
                   [[1, 0, 1]], [[1, 0, 0]], [[1, 0, 2]], [[1, 0, 3]], [[1, 4090, 2]], [[1, 4092, 2]], [[1, 4094]],
                   [[1, 4096]], [[2, 131070]], [[2, 131072]], [[1, 0, 2, 4096]], [[1, -2]], [[1, 0, U32]],
                   [[True, 0]], [[1, 0.5]], [5], 5, None, 'x', [[1, 0], [2, 0], [1, 2]]):
        yield 'rom_deltas:variant', {**record, 'rom_deltas': deltas}
    yield 'rom_deltas:with-roots', {**record, 'rom_deltas': [[1, 0, 2]], 'rom_entries': [[1, 0], [1, 2]]}


class CodecTests(unittest.TestCase):
    SEQUENCES = [[], [5], [7, 7, 7], [0, 1, 2, 3, 10, 11, 40], [2, 4, 6, 8, 100], [5, 3, 9, 1], [9, 9, 9, 10, 10],
                 [U32, 0, U32], [0, 31, 32, 33, 64], list(range(1000, 1100)), [-5, 3, -2], [2 ** 70, 2 ** 70 + 4]]

    def test_every_encoding_round_trips_where_it_applies(self):
        for values in self.SEQUENCES:
            applied = 0
            for encoding in pp.SEQ_ENCODINGS:
                try:
                    encoded = pp.encode_seq(values, only=encoding)
                except ValueError:
                    continue
                applied += 1
                self.assertEqual(pp.seq_count(encoded), len(values), (values, encoding))
                self.assertEqual(pp.decode_seq(json.loads(json.dumps(encoded)), len(values)), values, (values, encoding))
            self.assertGreaterEqual(applied, 1)
            smallest = pp.encode_seq(values)
            self.assertEqual(pp.decode_seq(smallest, len(values)), values)

    def test_the_smallest_encoding_is_chosen_for_typical_data(self):
        self.assertEqual(pp.encode_seq(list(range(1000, 1100)))['enc'], 'ranges')
        self.assertEqual(pp.encode_seq([4] * 50)['enc'], 'const')
        self.assertEqual(pp.encode_seq([3000000, 5, 4000000, 9])['enc'], 'list')
        generator = random.Random(3)
        even = sorted({generator.randrange(0, 1 << 20) * 2 for _ in range(500)})
        encoded = pp.encode_seq(even)
        self.assertEqual(encoded['enc'], 'delta')
        self.assertEqual(encoded.get('step'), 2)
        self.assertEqual(pp.encode_seq([5, 3, 9, 1])['enc'], 'list')

    def test_random_sequences_round_trip(self):
        generator = random.Random(20261027)
        for _ in range(400):
            kind = generator.randrange(5)
            count = generator.randrange(0, 300)
            if kind == 0:
                values = [generator.randrange(U32 + 1) for _ in range(count)]
            elif kind == 1:
                values = sorted(generator.randrange(0, 1 << generator.randrange(1, 24)) for _ in range(count))
            elif kind == 2:
                values = sorted(set(generator.randrange(0, 4096) for _ in range(count)))
            elif kind == 3:
                values = [generator.choice((0, 1, 2, 2, 2, 7)) for _ in range(count)]
            else:
                start = generator.randrange(1 << 20)
                values = [start + n * generator.choice((1, 1, 1, 2, 64)) for n in range(count)]
            encoded = pp.encode_seq(values)
            self.assertEqual(pp.decode_seq(encoded, max(count, 1)), values)
            rows = [[v, v ^ 5, 4] for v in values]
            table = pp.encode_table(rows, 3)
            self.assertEqual(pp.decode_table(table, 3, max(count, 1), unsigned=False), rows)

    def test_tables_keep_row_order_and_width(self):
        rows = [[3, 9, 4], [3, 2, 4], [1, 2, 4]]
        table = pp.encode_table(rows, 3)
        self.assertEqual(pp.decode_table(table, 3, 10), rows)
        self.assertEqual(pp.encode_table([], 3), {'n': 0})
        self.assertEqual(pp.decode_table({'n': 0}, 3, 0), [])
        with self.assertRaises(ValueError):
            pp.encode_table([[1, 2]], 3)
        with self.assertRaises(ValueError):
            pp.decode_table(table, 2, 10)
        with self.assertRaises(ValueError):
            pp.decode_table(table, 3, 2)
        short = copy.deepcopy(table)
        short['cols'][1] = pp.encode_seq([1, 2])
        with self.assertRaises(ValueError):
            pp.decode_table(short, 3, 10)
        negative = pp.encode_table([[-1, 0, 0]], 3)
        with self.assertRaises(ValueError):
            pp.decode_table(negative, 3, 10)
        self.assertEqual(pp.decode_table(negative, 3, 10, unsigned=False), [[-1, 0, 0]])
        with self.assertRaises(ValueError):
            pp.encode_seq([True])

    def test_sizes_are_checked_before_anything_is_expanded(self):
        bombs = [{'enc': 'ranges', 'v': [[0, 10 ** 12]]}, {'enc': 'const', 'v': 1, 'n': 10 ** 12},
                 {'enc': 'bitmap32', 'v': [[0, U32]] * 100000}, {'enc': 'list', 'v': list(range(101))}]
        for bomb in bombs:
            with self.assertRaises(ValueError):
                pp.decode_seq(bomb, 100)
        malformed = [None, [], {}, {'enc': 'zip', 'v': []}, {'enc': 'list'}, {'enc': 'list', 'v': 5},
                     {'enc': 'list', 'v': [1], 'x': 1}, {'enc': 'list', 'v': [1.5]}, {'enc': 'list', 'v': [True]},
                     {'enc': 'const', 'v': 1, 'n': 0}, {'enc': 'const', 'v': True, 'n': 1},
                     {'enc': 'delta', 'first': 1, 'gaps': [-1]}, {'enc': 'delta', 'first': 1, 'gaps': [1], 'step': 1},
                     {'enc': 'delta', 'first': 1, 'gaps': 3}, {'enc': 'delta', 'gaps': []},
                     {'enc': 'sdelta', 'first': 'a', 'gaps': []}, {'enc': 'ranges', 'v': [[5, 4]]},
                     {'enc': 'ranges', 'v': [[1]]}, {'enc': 'bitmap32', 'v': [[1, 1]]},
                     {'enc': 'bitmap32', 'v': [[0, 0]]}, {'enc': 'bitmap32', 'v': [[0, 1 << 32]]}]
        for encoded in malformed:
            with self.subTest(encoded=encoded):
                with self.assertRaises(ValueError):
                    pp.decode_seq(encoded, 100)

    def test_size_against_schema_1_is_reported(self):
        if not SNAPSHOT.is_file():
            self.skipTest('The maintainer snapshot is not in this checkout.')
        groups = {}
        for system, identity, record in snapshot_sample():
            groups.setdefault(system, {})[identity] = record
        print('\n' + size_report(sorted(groups.items()), 'deterministic sample of the snapshot'))


def cps1_document():
    rom = {'bytes': 1 << 20, 'sha256': '3' * 64}
    return {'schema': 3, 'game': 'cps1:' + '2' * 64,
            'identity': {'system': 'cps1', 'sources': {'maincpu': rom, 'audiocpu': {'bytes': 65536}},
                         'layout': {'catalogue': 'c' * 40}},
            'cpus': {'m68k': {'map': 'cps1', 'core': ENGINE, 'paths': {'ram_code': [
                        {'shape': 'insn', 'src': 'maincpu', 'table': pp.encode_table([[0xff0010, 4096, 8]], 3)}]}},
                     'z80': {'map': 'cps1-sound', 'core': ENGINE, 'paths': {'ram_code': [
                        {'shape': 'insn_masked', 'src': 'audiocpu', 'table': pp.encode_table([[0xd010, 100, 4, 7]], 4)}]}}},
            'devices': {}}


def x68_document():
    return {'schema': 3, 'game': 'x68:' + '4' * 64,
            'identity': {'system': 'x68', 'sources': {'ipl': {'bytes': 131072, 'sha256': '5' * 64},
                                                      'disk0': {'bytes': 1261568}, 'disk1': {'bytes': 1261568}},
                         'layout': {'ram_mib': 4, 'initial_drives': [0, 1]}},
            'cpus': {'m68k': {'map': 'x68', 'core': ENGINE, 'paths': {
                'ram_code': [{'shape': 'insn', 'srcs': ['disk0', 'disk1'],
                              'table': pp.encode_table([[1, 0x2000, 4096, 6], [0, 0x2002, 4100, 2]], 4)}],
                'spans': [{'shape': 'span', 'src': 'ipl', 'table': pp.encode_table([[0xfc0000, 0, 131072]], 3)}]}}},
            'devices': {}}


class ValidatorTests(unittest.TestCase):
    def test_machines_without_a_schema_1_form_validate(self):
        pp.validate_game(cps1_document())
        pp.validate_game(x68_document())
        document = pp.to_v3(*FIXTURES['snes'])
        document['devices'] = {'gsu': {'core': ENGINE, 'paths': {'targets': [
            {'shape': 'pair', 'table': pp.encode_table([[0x8000, 0xc000], [0x8010, 0xffffff]], 2)}]}},
                               'dsp1': {'core': ENGINE, 'paths': {}}}
        pp.validate_game(document)
        numbers_only(self, document)

    def broken(self, build, mutate):
        document = build()
        mutate(document)
        with self.assertRaises(ValueError):
            pp.validate_game(document)

    def test_structure_is_refused_when_wrong(self):
        md, ng = (lambda: pp.to_v3(*FIXTURES['md'])), (lambda: pp.to_v3(*FIXTURES['ng-deltas']))
        snes, x68 = (lambda: pp.to_v3(*FIXTURES['snes'])), x68_document
        entries = lambda d: d['cpus']['m68k']['paths']['entries'][0]
        ram = lambda d: d['cpus']['m68k']['paths']['ram_code'][0]

        def column(document, value):
            ram(document)['table']['cols'][1] = pp.encode_seq(value)

        cases = {
            'schema': (md, lambda d: d.update(schema=4)),
            'schema-bool': (md, lambda d: d.update(schema=True)),
            'extra-key': (md, lambda d: d.update(extra=1)),
            'no-devices': (md, lambda d: d.pop('devices')),
            'game-system': (md, lambda d: d.update(game='zz:' + SHA)),
            'game-upper': (md, lambda d: d.update(game='md:' + 'A' * 64)),
            'game-mismatch': (md, lambda d: d['identity'].update(system='gb')),
            'sources-empty': (md, lambda d: d['identity'].update(sources={})),
            'source-name': (md, lambda d: d['identity']['sources'].update(foo={'bytes': 9000})),
            'source-small': (md, lambda d: d['identity']['sources']['rom'].update(bytes=8191)),
            'source-large': (md, lambda d: d['identity']['sources']['rom'].update(bytes=128 * 1024 * 1024 + 529)),
            'source-bool': (md, lambda d: d['identity']['sources']['rom'].update(bytes=True)),
            'source-hash': (md, lambda d: d['identity']['sources']['rom'].update(sha256='x')),
            'source-key': (md, lambda d: d['identity']['sources']['rom'].update(extra=1)),
            'source-missing': (md, lambda d: d['identity']['sources'].pop('rom')),
            'layout': (md, lambda d: d['identity']['layout'].update(loader='a' * 40)),
            'no-cpu': (md, lambda d: d.update(cpus={})),
            'cpu-unknown': (md, lambda d: d['cpus'].update(mos6502=d['cpus']['z80'])),
            'map': (md, lambda d: d['cpus']['m68k'].update(map='ng')),
            'core': (md, lambda d: d['cpus']['m68k'].update(core='A' * 40)),
            'section-key': (md, lambda d: d['cpus']['m68k'].update(extra=1)),
            'kind': (md, lambda d: d['cpus']['m68k']['paths'].update(targets=[])),
            'kind-not-list': (md, lambda d: d['cpus']['m68k']['paths'].update(entries={})),
            'shape': (md, lambda d: entries(d).update(shape='nes_rows')),
            'shape-kind': (md, lambda d: entries(d).update(shape='insn')),
            'shape-unknown': (md, lambda d: entries(d).update(shape='nope')),
            'shape-twice': (md, lambda d: d['cpus']['m68k']['paths']['entries'].append(copy.deepcopy(entries(d)))),
            'block-key': (md, lambda d: entries(d).update(extra=1)),
            'block-src': (md, lambda d: entries(d).update(src='bios')),
            'block-no-src': (md, lambda d: entries(d).pop('src')),
            'block-both': (md, lambda d: entries(d).update(srcs=['rom', 'rom'])),
            'block-groups': (md, lambda d: entries(d).update(groups=[])),
            'block-no-table': (md, lambda d: entries(d).pop('table')),
            'table-n': (md, lambda d: entries(d)['table'].update(n=65537)),
            'table-width': (md, lambda d: ram(d)['table'].update(cols=ram(d)['table']['cols'][:2])),
            'column-length': (md, lambda d: column(d, [4096])),
            'column-negative': (md, lambda d: column(d, [-1, 4096])),
            'column-large': (md, lambda d: column(d, [U32 + 1, 4096])),
            'outside-source': (md, lambda d: column(d, [1048576 - 7, 4096])),
            'align': (md, lambda d: ram(d)['table']['cols'].__setitem__(0, pp.encode_seq([0xff0001, 0xff0000]))),
            'z80-role': (ng, lambda d: d['cpus']['z80']['paths']['ram_code'][0].update(srcs=['p', 'bios'])),
            'ng-source-index': (ng, lambda d: d['cpus']['m68k']['paths']['ram_code'][0]['table']['cols'].__setitem__(
                0, pp.encode_seq([0, 2, 0]))),
            'ng-region': (ng, lambda d: d['identity']['sources']['p'].update(bytes=4097)),
            'ng-key': (ng, lambda d: d['identity']['sources']['bios'].update(sha256='d' * 64)),
            'ng-no-hash': (ng, lambda d: d['identity']['sources']['bios'].pop('sha256')),
            'ng-layout': (ng, lambda d: d['identity']['layout'].update(extra='a' * 40)),
            'ng-delta-group': (ng, lambda d: d['cpus']['m68k']['paths']['entries'][1].update(groups=[['p', pp.encode_seq([0, 1])]])),
            'ng-delta-src': (ng, lambda d: d['cpus']['m68k']['paths']['entries'][1].update(groups=[['m1', pp.encode_seq([0])]])),
            'ng-delta-twice': (ng, lambda d: d['cpus']['m68k']['paths']['entries'][1].update(
                groups=[['p', pp.encode_seq([0])], ['p', pp.encode_seq([2])]])),
            'ng-delta-three': (ng, lambda d: d['cpus']['m68k']['paths']['entries'][1].update(
                groups=[['p', pp.encode_seq([0])], ['bios', pp.encode_seq([2])], ['p', pp.encode_seq([4])]])),
            'spc-groups': (snes, lambda d: d['cpus']['spc700']['paths']['ram_code'][-1].update(groups=[[13]])),
            'device-system': (md, lambda d: d['devices'].update(gsu={'core': ENGINE, 'paths': {}})),
            'device-kind': (snes, lambda d: d['devices'].update(dsp1={'core': ENGINE, 'paths': {'targets': []}})),
            'device-target': (snes, lambda d: d['devices'].update(gsu={'core': ENGINE, 'paths': {'targets': [
                {'shape': 'pair', 'table': pp.encode_table([[0, 0x1000000]], 2)}]}})),
            'device-name': (snes, lambda d: d['devices'].update(sa1={'core': ENGINE, 'paths': {}})),
            'x68-aperture': (x68, lambda d: d['cpus']['m68k']['paths']['ram_code'][0]['table']['cols'].__setitem__(
                1, pp.encode_seq([0xd00000, 0x2002]))),
            'x68-span-long': (x68, lambda d: d['cpus']['m68k']['paths']['spans'][0].update(
                table=pp.encode_table([[0xfc0000, 0, 131073]], 3))),
            'x68-span-outside': (x68, lambda d: d['cpus']['m68k']['paths']['spans'][0].update(
                table=pp.encode_table([[0xfc0000, 1, 131072]], 3))),
            'x68-span-total': (x68, lambda d: d['cpus']['m68k']['paths']['spans'][0].update(
                src='disk0', table=pp.encode_table([[0, 0, 1261568]] * 4, 3))),
            'x68-layout': (x68, lambda d: d['identity']['layout'].update(extra=1)),
        }
        for name, (build, mutate) in cases.items():
            with self.subTest(name):
                self.broken(build, mutate)
        # Not a record at all.
        for value in (None, [], 'x', 5, {}):
            with self.assertRaises(ValueError):
                pp.validate_game(value)

    def test_profile_table_is_plain_data_for_a_web_validator(self):
        table = pp.profile_table()
        self.assertEqual(json.loads(json.dumps(table)), json.loads(json.dumps(table)))
        self.assertEqual(set(table), {f'{cpu}/{name}' for cpu, name in pp.PROFILES})
        self.assertEqual({section for sections in pp.SYSTEM_SECTIONS.values() for section in sections}, set(pp.PROFILES))
        for system, sections in pp.SYSTEM_SECTIONS.items():
            for cpu, name in sections:
                self.assertIn(system, pp.PROFILES[(cpu, name)].systems)
        self.assertEqual(set(pp.SYSTEMS), set(pp.SYSTEM_SECTIONS))
        self.assertEqual({shape for profile in pp.PROFILES.values() for shape in profile.caps} - set(pp.SHAPES), set())
        self.assertEqual(set(pp.STRICTER_THAN_V2), {'md.ram_refs.address', 'md.ram_refs.length', 'md.z80_refs.pc',
                                                    'md.z80_refs.length', 'snes.ram_refs.length', 'snes.ram_refs.address'})


class GameModuleTests(unittest.TestCase):
    """Since 1.6.0 (stage B3) the module is a game module: `knowledge` delegates to it, so it is
    in every console's game stamp (the one deliberate break of the stamps)."""

    def test_the_converter_reads_the_one_table_of_fields(self):
        self.assertIs(knowledge.FIELDS, pp.LEGACY_FIELDS)
        self.assertIs(neogeo_knowledge.FIELDS, pp.LEGACY_FIELDS['ng'])
        self.assertIs(knowledge.FIELDS['ng'], neogeo_knowledge.FIELDS)
        self.assertEqual(neogeo_knowledge.key(CART, BIOS), pp.ng_key(CART, BIOS))
        for text in ('retrorecomp/knowledge.py', 'retrorecomp/neogeo_knowledge.py'):
            self.assertIn('path_profiles', (ROOT / text).read_text(encoding='utf-8'), text)

    def test_the_stamp_definition_does_not_import_it(self):
        text = (ROOT / 'retrorecomp' / 'stamp_inputs.py').read_text(encoding='utf-8')
        self.assertNotRegex(text, r'import\s+.*path_profiles|from\s+\.path_profiles')

    def test_it_is_a_game_module_every_console_stamp_hashes(self):
        self.assertNotIn('path_profiles', compilation_inputs.INTERFACE_MODULES)
        for system in sorted(compilation_inputs.SYSTEMS):
            names = {name for name, _ in compilation_inputs._module_inputs(system)}
            self.assertIn('retrorecomp.path_profiles', names, system)
            self.assertEqual(compilation_inputs.role('retrorecomp.path_profiles'), 'game')

    def test_the_sharing_lists_and_key_patterns_follow_one_list(self):
        from retrorecomp import knowledge_build, knowledge_exchange, online
        self.assertEqual(knowledge_exchange.SYSTEMS, pp.SHARED_SYSTEMS)
        self.assertEqual(knowledge_exchange.SYSTEMS, (*knowledge_build.SYSTEMS, 'ng'))
        digest = '0123456789abcdef' * 4
        for pattern in (online._ROM_KEY, knowledge_exchange._GAME_KEY):
            for system in pp.SHARED_SYSTEMS:
                self.assertTrue(pattern.fullmatch(f'{system}:{digest}'), system)
            for system in ('cps1', 'x68', 'psx'):
                self.assertFalse(pattern.fullmatch(f'{system}:{digest}'), system)
            self.assertFalse(pattern.fullmatch('md:' + digest[:-1]))
        # Adding a console to the sharing is one name in the list.
        wider = pp.game_key((*pp.SHARED_SYSTEMS, 'cps1', 'x68'))
        self.assertTrue(wider.fullmatch(f'cps1:{digest}') and wider.fullmatch(f'x68:{digest}'))
        self.assertEqual(set(pp.SYSTEMS), set(pp.SHARED_SYSTEMS) | {'cps1', 'x68'})


class LocalBankReaderTests(unittest.TestCase):
    """The readers of a local bank accept schema 1 and schema 3 and give the same schema 1 view."""

    def banks(self):
        payload = {'schema': 1, 'consoles': {}}
        for index, (system, identity, record) in enumerate(FIXTURES.values()):
            if system == 'ng':
                payload['consoles'].setdefault('ng', {}).setdefault(identity, record)
            else:
                payload['consoles'].setdefault(system, {})[f'{index:064x}'] = record
        return payload, pp.bank_to_v3(payload)

    def test_both_schemas_give_the_same_records(self):
        payload, bank = self.banks()
        self.assertEqual(pp.read_bank(copy.deepcopy(payload)), payload)
        self.assertEqual(pp.read_bank(copy.deepcopy(bank)), payload)
        self.assertEqual(pp.bank_games(copy.deepcopy(bank)), {})
        self.assertEqual(pp.bank_games(payload), {})

    def test_a_file_of_either_schema_is_read_and_cps1_games_are_kept_apart(self):
        import tempfile
        payload, bank = self.banks()
        cps1 = cps1_document()
        bank['games'][cps1['game']] = cps1
        with tempfile.TemporaryDirectory() as folder:
            first, second = Path(folder, 'one.json.gz'), Path(folder, 'three.json.gz')
            knowledge.write_packed(first, payload)
            knowledge.write_packed(second, bank)
            self.assertEqual(knowledge.read(first), payload)
            self.assertEqual(knowledge.read(second), payload)
            self.assertEqual(knowledge.read_games(first), {})
            self.assertEqual(knowledge.read_games(second), {cps1['game']: cps1})
            with self.assertRaises(ValueError):
                knowledge.write_packed(first, {'schema': 3, 'games': {'md:' + '0' * 64: {}}})
                knowledge.read(first)

    def test_a_game_whose_projection_fails_the_schema_1_rules_is_set_aside(self):
        # The exchange reader validates the projection (paths_from_v3); the local reader does too.
        from unittest.mock import patch
        payload, bank = self.banks()
        real = pp.validate_legacy_record
        def refuse_md(system, identity, record):
            if system == 'md':
                raise ValueError('Invalid compilation knowledge entries.')
            return real(system, identity, record)
        with patch.object(pp, 'validate_legacy_record', side_effect=refuse_md):
            read = pp.read_bank(copy.deepcopy(bank))
        self.assertNotIn('md', read['consoles'])
        self.assertEqual({k: v for k, v in read['consoles'].items()},
                         {k: v for k, v in payload['consoles'].items() if k != 'md'})
        self.assertIn('md', pp.read_bank(copy.deepcopy(bank))['consoles'])

    def test_schema_1_rules_are_unchanged_by_the_move(self):
        # The schema 1 validator is path_profiles' now; knowledge.validate_payload is its name.
        _, bank = self.banks()
        with self.assertRaises(ValueError):
            knowledge.validate_payload(bank)
        with self.assertRaises(ValueError):
            pp.validate_legacy_payload({'schema': 1, 'consoles': {'cps1': {}}})
        for name in ('md', 'snes', 'ng'):
            system, identity, record = FIXTURES[name]
            self.assertEqual(pp.validate_legacy_record(system, identity, record), record)


if __name__ == '__main__':
    unittest.main()
