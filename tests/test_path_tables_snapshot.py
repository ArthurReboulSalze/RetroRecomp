"""The path tables, the route tables and the knowledge lists are read from the machines' profiles; their values
did not move.

Before 1.6.3 package P2, `path_profiles` (SYSTEMS, SYSTEM_SECTIONS, PROFILES, SOURCE_BOUNDS, REQUIRED_SOURCES,
HASHED_SOURCES, the shared-knowledge lists), `random_routes` (CONSOLES and the script writers),
`knowledge_build.SYSTEMS` and `compiled_games_view.SHARED_CONSOLES` each held their own literal table. This file
holds those tables as they were then (taken on the 1.6.2 tree with the P1 profile fields, before the change) and
the digest of the random routes that every console generates for fixed seeds, so the derivation from the
`SystemProfile` fields is proved to give identical results. Only numbers and names are stored, no ROM byte.
The tables are pinned for these nine consoles only: a machine registered later brings its own rows through its profile
and adds nothing here (docs/NEW_MACHINE.md); `only` leaves its rows out of the comparison.
"""
import hashlib
import json
import tempfile
import unittest
import re
from dataclasses import asdict, is_dataclass, replace
from pathlib import Path

from retrorecomp import compiled_games_view, knowledge_build, path_profiles as pp, random_routes as rr
from retrorecomp.systems import ALL_PROFILES

# --- Expected data, as the literal tables of 1.6.2 held them ------------------------------------------------

NINE = ('sms', 'gg', 'gb', 'nes', 'md', 'snes', 'ng', 'cps1', 'x68')
SYSTEMS = ['sms', 'gg', 'gb', 'nes', 'md', 'snes', 'ng', 'cps1', 'x68']
SYSTEM_SECTIONS = {'sms': [['z80', 'sms']],
 'gg': [['z80', 'sms']],
 'gb': [['sm83', 'gb']],
 'nes': [['mos6502', 'nes']],
 'md': [['m68k', 'md'], ['z80', 'md-sound']],
 'snes': [['w65c816', 'snes'], ['spc700', 'snes']],
 'ng': [['m68k', 'ng'], ['z80', 'ng-sound']],
 'cps1': [['m68k', 'cps1'], ['z80', 'cps1-sound']],
 'x68': [['m68k', 'x68']]}
SOURCE_BOUNDS = {'sms': {'rom': [8192, 134218256]},
 'gg': {'rom': [8192, 134218256]},
 'gb': {'rom': [8192, 134218256]},
 'nes': {'rom': [8192, 134218256]},
 'md': {'rom': [8192, 134218256]},
 'snes': {'rom': [8192, 134218256]},
 'ng': {'cart': [4096, 536870912],
        'p': [512, 16777216],
        'bios': [131072, 131072],
        'm1': [65536, 524288],
        'sm1': [131072, 131072]},
 'cps1': {'maincpu': [4096, 4194304], 'audiocpu': [32768, 1048576]},
 'x68': {'ipl': [1, 1048576], 'disk': [1, 1073741824]}}
REQUIRED_SOURCES = {'ng': ['cart', 'p', 'bios', 'm1', 'sm1'],
 'cps1': ['maincpu', 'audiocpu'],
 'sms': ['rom'],
 'gg': ['rom'],
 'gb': ['rom'],
 'nes': ['rom'],
 'md': ['rom'],
 'snes': ['rom']}
HASHED_SOURCES = {'ng': ['cart', 'bios'], 'cps1': ['maincpu', 'audiocpu']}
STABLE_SHARED = ['sms', 'gg', 'gb', 'nes', 'md', 'snes', 'ng']
EXPERIMENTAL_SHARED = ['cps1']
SHARED_SYSTEMS = ['sms', 'gg', 'gb', 'nes', 'md', 'snes', 'ng', 'cps1']
WITHDRAWABLE = ['cps1']
WITHDRAWN = []
SCHEMA3_ONLY = ['cps1']
LEGACY_FIELDS = {'sms': {'rom_entries': [5, 65536], 'pattern_refs': [1, 4096]},
 'gg': {'rom_entries': [5, 65536], 'pattern_refs': [1, 4096]},
 'gb': {'rom_entries': [2, 65536]},
 'nes': {'rom_entries': [2, 65536], 'ram_opcode_refs': [2, 65536]},
 'md': {'rom_entries': [1, 65536], 'ram_refs': [3, 2048], 'z80_refs': [3, 32768]},
 'snes': {'ram_refs': [3, 16384],
          'ram_opcode_refs': [2, 16384],
          'spc_refs': [2, 262144],
          'spc_ranges': [3, 262144],
          'spc_bitmaps': [3, 262144],
          'spc_deltas': [2, 262144]},
 'ng': {'rom_entries': [2, 262144], 'ram_refs': [4, 4096], 'z80_refs': [4, 32768]}}
ROM_BOUNDS = [8192, 134218256]
GAME_KEY = '(?:sms|gg|gb|nes|md|snes|ng|cps1|x68):[0-9a-f]{64}'
PROFILE_SYSTEMS = {'m68k/md': ['md'],
 'm68k/ng': ['ng'],
 'm68k/cps1': ['cps1'],
 'm68k/x68': ['x68'],
 'z80/sms': ['sms', 'gg'],
 'z80/md-sound': ['md'],
 'z80/ng-sound': ['ng'],
 'z80/cps1-sound': ['cps1'],
 'sm83/gb': ['gb'],
 'mos6502/nes': ['nes'],
 'w65c816/snes': ['snes'],
 'spc700/snes': ['snes']}
PROFILE_ORDER = ['m68k/md', 'm68k/ng', 'm68k/cps1', 'm68k/x68', 'z80/sms', 'z80/md-sound', 'z80/ng-sound',
 'z80/cps1-sound', 'sm83/gb', 'mos6502/nes', 'w65c816/snes', 'spc700/snes']
PROFILES_SHA256 = '17ddc4ce725fbe489d28fced9611cd3b50becbd1af8b70faca1c24ec924493a9'
OTHER_NAMES = ['DEVICES', 'GAMES_PER_SYSTEM', 'HEX40', 'HEX64', 'KINDS', 'LEGACY_WIDTHS', 'NG_CPU_SOURCES',
               'NG_IDENTITY_FIELDS', 'NG_REGIONS', 'SCHEMA', 'SEQ_ENCODINGS', 'SHAPES', 'SOURCE_NAME', 'SPAN_BYTES',
               'STRICTER_THAN_V2', 'U32']
OTHER_SHA256 = 'def27882984f32150cc47293d8b7ae27f43730808c81f6920a42c5d9a6898257'
KNOWLEDGE_BUILD_SYSTEMS = ['sms', 'gg', 'gb', 'nes', 'md', 'snes']
SHARED_CONSOLES = ['sms', 'gg', 'gb', 'nes', 'md', 'snes', 'ng']
ROUTE_CONSOLES = {'md': {'main': ['a', 'b', 'c'], 'extra': ['x', 'y', 'z'], 'select': None, 'opening': 240},
 'snes': {'main': ['a', 'b', 'x', 'y'], 'extra': ['l', 'r'], 'select': 'select', 'opening': 240},
 'nes': {'main': ['a', 'b'], 'extra': [], 'select': 'select', 'opening': 180},
 'ng': {'main': ['a', 'b', 'c', 'd'], 'extra': [], 'select': None, 'opening': 2400},
 'cps1': {'main': ['b1', 'b2', 'b3'], 'extra': ['b4', 'b5', 'b6'], 'select': None, 'opening': 720},
 'gb': {'main': ['a', 'b'], 'extra': [], 'select': 'select', 'opening': 180},
 'sms': {'main': ['a', 'b'], 'extra': [], 'select': None, 'opening': 240, 'start': False},
 'gg': {'main': ['a', 'b'], 'extra': [], 'select': None, 'opening': 240}}
ROUTE_DIGESTS = {'md': 'e9d0f411d78ca5b09c8e9736d36a831c5ede02ff82d6ad027fb183c88629888c',
 'snes': 'b58f32b5d4922409c14dc8f1deb85ce6da76d8fac78b0dc31622a7bcc58dcbbb',
 'nes': 'a8c2a7eb1242a591226f87527536d8ed3ed8e15c09f3680ed8a5e04d761f1f00',
 'ng': 'b6f0f0bb35186b1c891211a395a3e7663ef0ef4fdc1fc0ad5fd20c5043550b68',
 'cps1': 'c58c9f0e953a86ad2e8b5fec42599cc008f6548bdc5d5c5dc208d145f0366735',
 'gb': '5ece36484e81900215d366b671bdf2b2af58038401cd716896e3941e64cd82ad',
 'sms': 'c3eb4e463a27496a1229405a841139f298533c2c2c2113b56d67e904860acec4',
 'gg': '3abe8a59b53370ca30530efbd898770183af28ba4602b372474bbdb538c1b5da'}
ROUTE_ERRORS = {'x68': ["ValueError:No random route vocabulary for console 'x68'."],
 'zx': ["ValueError:No random route vocabulary for console 'zx'."]}



# --- Reading the live modules the same way ------------------------------------------------------------------

def plain(value):
    """JSON-like form of a table: tuples are lists, tuple keys 'a/b', sets sorted, regexes their pattern."""
    if is_dataclass(value):
        return plain(asdict(value))
    if isinstance(value, dict):
        return {('/'.join(key) if isinstance(key, tuple) else str(key)): plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [plain(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(plain(item) for item in value)
    if hasattr(value, 'pattern'):
        return value.pattern
    return value


def only(value):
    """The rows of the nine consoles of 1.6.2: a table keyed by console or a list of consoles, without the machines
    registered since."""
    if isinstance(value, dict):
        return {key: item for key, item in value.items() if key in NINE}
    return [item for item in value if item in NINE]


def nine_profiles() -> dict:
    """The CPU profiles the nine consoles use, each naming only those of them."""
    shown = {}
    for key, profile in pp.PROFILES.items():
        systems = tuple(system for system in profile.systems if system in NINE)
        if systems:
            shown[key] = replace(profile, systems=systems)
    return shown


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def route_digests() -> tuple[dict, dict]:
    """One digest per console of every route (metadata, script, file name and bytes) for fixed identities and
    options, and the error of the consoles that have no vocabulary."""
    digests, errors = {}, {}
    for console in list(rr.CONSOLES) + ['x68', 'zx']:
        items = []
        for identity in ('seed-a', 'sha:' + 'ab' * 32):
            for options in ({}, {'six_buttons': True}, {'two_players': False}, {'frames': 3000}):
                for chain in (False, True):
                    key = f'{console}|{identity[:6]}|{sorted(options.items())}|{chain}'
                    try:
                        routes = rr.long_routes(console, identity, chain=chain, **options)
                        hasher = hashlib.sha256()
                        for route in routes:
                            hasher.update(json.dumps(route.metadata(), sort_keys=True).encode())
                            hasher.update(rr.script_text(route).encode())
                            with tempfile.TemporaryDirectory() as folder:
                                written = rr.write_route(route, Path(folder))
                                hasher.update(written.name.encode())
                                hasher.update(written.read_bytes())
                        items.append((key, hasher.hexdigest()))
                    except ValueError as error:
                        items.append((key, type(error).__name__ + ':' + str(error)))
        if console in ('x68', 'zx'):
            errors[console] = sorted({value for _, value in items})
        elif console in NINE:
            digests[console] = hashlib.sha256(json.dumps(items).encode()).hexdigest()
    return digests, errors


class PathTablesTests(unittest.TestCase):
    def test_the_tables_of_the_schema_are_unchanged(self):
        for name, expected in (('SYSTEMS', SYSTEMS), ('SYSTEM_SECTIONS', SYSTEM_SECTIONS),
                               ('SOURCE_BOUNDS', SOURCE_BOUNDS), ('REQUIRED_SOURCES', REQUIRED_SOURCES),
                               ('HASHED_SOURCES', HASHED_SOURCES), ('LEGACY_FIELDS', LEGACY_FIELDS),
                               ('ROM_BOUNDS', ROM_BOUNDS)):
            with self.subTest(name):
                live = plain(getattr(pp, name))
                self.assertEqual(only(live) if name != 'ROM_BOUNDS' else live, expected)

    def test_the_order_of_the_schema_is_kept(self):
        # The schema lists CPS-1 before the X68000; the documents and the registration list do it the other way.
        self.assertEqual(only(list(pp.SYSTEMS)), SYSTEMS)
        self.assertEqual(only(list(pp.SYSTEM_SECTIONS)), SYSTEMS)
        self.assertEqual(only(list(pp.SOURCE_BOUNDS)), SYSTEMS)
        self.assertEqual([profile.id for profile in ALL_PROFILES if profile.id in NINE][-2:], ['x68', 'cps1'])
        alternatives = re.fullmatch(r'\(\?:(.*)\):\[0-9a-f\]\{64\}', pp.GAME_KEY.pattern).group(1).split('|')
        self.assertEqual(only(alternatives), SYSTEMS)
        self.assertEqual(GAME_KEY, '(?:' + '|'.join(SYSTEMS) + '):[0-9a-f]{64}')

    def test_the_cpu_profiles_are_unchanged_and_the_two_sega_machines_share_the_z80(self):
        # The profiles are built from the machines' `PathSpec.shapes` (registration order): the dictionary's own order
        # was never read, so it is compared as a set.
        shown = nine_profiles()
        self.assertEqual(sorted('/'.join(key) for key in shown), sorted(PROFILE_ORDER))
        self.assertEqual({'/'.join(key): list(profile.systems) for key, profile in shown.items()}, PROFILE_SYSTEMS)
        self.assertEqual(pp.PROFILES[('z80', 'sms')].systems, ('sms', 'gg'))
        self.assertEqual(digest(plain(shown)), PROFILES_SHA256)

    def test_the_shared_knowledge_lists_are_unchanged(self):
        for name, expected in (('STABLE_SHARED', STABLE_SHARED), ('EXPERIMENTAL_SHARED', EXPERIMENTAL_SHARED),
                               ('SHARED_SYSTEMS', SHARED_SYSTEMS), ('WITHDRAWABLE', WITHDRAWABLE),
                               ('WITHDRAWN', WITHDRAWN), ('SCHEMA3_ONLY', SCHEMA3_ONLY)):
            with self.subTest(name):
                self.assertEqual(only(list(getattr(pp, name))), expected)

    def test_the_names_that_stay_written_out_are_unchanged(self):
        public = sorted(name for name in dir(pp) if name.isupper() and not name.startswith('_'))
        derived = set(SYSTEMS_AND_TABLES)
        rest = {name: plain(getattr(pp, name)) for name in public if name not in derived and name != 'PROFILES'}
        self.assertEqual(sorted(rest), OTHER_NAMES)
        self.assertEqual(digest(rest), OTHER_SHA256)

    def test_the_knowledge_lists_are_unchanged(self):
        self.assertEqual(only(list(knowledge_build.SYSTEMS)), KNOWLEDGE_BUILD_SYSTEMS)
        self.assertEqual(only(list(compiled_games_view.SHARED_CONSOLES)), SHARED_CONSOLES)

    def test_each_map_is_declared_by_exactly_one_machine(self):
        # `PathSpec.shapes`: a new machine declares the maps it introduces and edits no table of path_profiles.
        declared = [(cpu, name) for profile in ALL_PROFILES if profile.path_spec is not None
                    for cpu, name, _ in profile.path_spec.shapes]
        self.assertEqual(len(declared), len(set(declared)))
        self.assertEqual(set(declared), set(pp.PROFILES))
        for profile in ALL_PROFILES:
            if profile.path_spec is not None:
                for section in profile.path_spec.sections:
                    self.assertIn(section, pp.PROFILES, profile.id)
                    self.assertIn(profile.id, pp.PROFILES[section].systems)

    def test_the_tables_follow_the_profiles(self):
        # Where each table now comes from: nothing is listed twice.
        for profile in ALL_PROFILES:
            spec = profile.path_spec
            self.assertEqual(pp.SYSTEM_SECTIONS[profile.id], spec.sections)
            self.assertEqual(pp.SOURCE_BOUNDS[profile.id], dict(spec.source_bounds))
            self.assertEqual(pp.REQUIRED_SOURCES.get(profile.id, ()), spec.required_sources)
            self.assertEqual(pp.HASHED_SOURCES.get(profile.id, ()), spec.hashed_sources)
            self.assertEqual(profile.id in pp.EXPERIMENTAL_SHARED,
                             profile.shared_knowledge is not None and profile.shared_knowledge.tier == 'experimental')
            self.assertEqual(profile.id in knowledge_build.SYSTEMS,
                             profile.shared_knowledge is not None and profile.shared_knowledge.site_builder)
            self.assertEqual(profile.id in rr.CONSOLES, profile.input_layout is not None)
        self.assertEqual(compiled_games_view.SHARED_CONSOLES, pp.STABLE_SHARED)


class RouteTablesTests(unittest.TestCase):
    def test_the_pad_tables_are_unchanged(self):
        self.assertEqual(only(plain(rr.CONSOLES)), ROUTE_CONSOLES)

    def test_every_console_generates_the_same_routes(self):
        digests, errors = route_digests()
        self.assertEqual(digests, ROUTE_DIGESTS)
        self.assertEqual(errors, ROUTE_ERRORS)

    def test_a_script_format_without_a_writer_is_refused(self):
        self.assertEqual(set(rr.SCRIPT_FORMATS.values()), set(rr.SCRIPT_WRITERS))
        route = rr.long_route('nes', 'seed-a', 0)
        rr.script_text(route)
        with self.assertRaises(ValueError):
            rr.script_text(rr.Route(**{**route.__dict__, 'console': 'x68'}))


SYSTEMS_AND_TABLES = ('SYSTEMS', 'SYSTEM_SECTIONS', 'SOURCE_BOUNDS', 'REQUIRED_SOURCES', 'HASHED_SOURCES',
                      'STABLE_SHARED', 'EXPERIMENTAL_SHARED', 'SHARED_SYSTEMS', 'WITHDRAWABLE', 'WITHDRAWN',
                      'SCHEMA3_ONLY', 'LEGACY_FIELDS', 'ROM_BOUNDS', 'GAME_KEY')


if __name__ == '__main__':
    unittest.main()
