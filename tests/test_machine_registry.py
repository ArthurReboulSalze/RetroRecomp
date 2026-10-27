"""A machine declared in the profiles must be present in every registry a machine needs.

The registries of the converter that still hold their own console list (the E4 dry run of a tenth machine
found them; docs/NEW_MACHINE.md orders them) are checked here, so that a future machine cannot forget one.
Two tiers, because the lifecycle has two stages (docs/NEW_MACHINE.md, "Experimental, then supported"):

* **Every machine, experimental ones included**: it is identified, converted or refused cleanly, reported,
  fingerprinted, translated, shown in the interface and in the documents, and listed in the verification
  tools. Anything it cannot do yet is said by its status and its qualification column, never by a gap.
* **A `supported` machine only**: what docs/QUALIFICATION.md and docs/STANDARDS.md require before the word
  "supported" (Linux witness, shared knowledge, a panel of risk cases, a qualification record without a
  failed gate). An experimental machine is not asked for these.

`registry_problems(profile)` returns the missing registries of one profile, as sentences. The tests run it on
the profiles of the converter (no problem expected) and on synthetic profiles (every gap must be found).
"""
import ast
import json
import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'tools'))

from retrorecomp import hostkit, path_profiles, random_routes, report_schema, scan_levels, stamp_inputs  # noqa: E402
from retrorecomp import compilation_inputs, feedback  # noqa: E402
from retrorecomp.i18n import STRINGS, catalog  # noqa: E402
from retrorecomp.languages import LANGUAGES  # noqa: E402
from retrorecomp.systems import (ALL_PROFILES, ROM_CANDIDATE_EXTENSIONS, STATUSES, Cpu,  # noqa: E402
                                 SystemProfile, system_ids)
import campaign  # noqa: E402
import release_check  # noqa: E402
import status_lint  # noqa: E402
import std_baseline  # noqa: E402

# The first three consoles named their options tab by what it shows; every later machine uses `options_<id>`.
LEGACY_TAB_KEYS = {'sms': 'options_master_system', 'gg': 'options_game_gear', 'gb': 'options_game_boy'}

# Registries a machine may decline, listed here with the reason so that declining is a visible, reviewed
# decision (a new machine adds itself here, in the same change, only with a sentence saying why).
DECLINED = {
    # Random long routes: the X68000 plays routes of its own (x68000_scan.long_routes), in its own script format.
    'random_routes': {'x68'},
    # Libretro-thumbnails folders and the shared box-art provider tables (retrorecomp/artwork.py): no repository
    # was ever chosen for the arcade board.
    'artwork': {'cps1'},
    # Per-console reader of the local library for the memory window (retrorecomp/memory_view.py).
    'memory_view': {'cps1'},
}

QUALIFICATION_CELLS = set('YPN?-')


def _text(path: str) -> str:
    return (REPO / path).read_text(encoding='utf-8')


def _qualification_matrix() -> dict:
    """{console id: {gate: cell}} from the status matrix of docs/QUALIFICATION.md."""
    lines = _text('docs/QUALIFICATION.md').splitlines()
    header = next(i for i, line in enumerate(lines) if line.startswith('| Gate |'))
    ids = [cell.strip() for cell in lines[header].strip('|').split('|')][1:]
    matrix = {system: {} for system in ids}
    for line in lines[header + 2:]:
        if not line.startswith('| G'):
            break
        cells = [cell.strip() for cell in line.strip('|').split('|')]
        for system, cell in zip(ids, cells[1:]):
            matrix[system][cells[0]] = cell
    return matrix


def _gui_builds_the_tab(source: str, system: str) -> bool:
    """The options panel of gui.py builds a tab for this console (a call or a loop over a tuple of ids)."""
    quoted = r"""['"]%s['"]""" % re.escape(system)
    call = re.search(r'build_scan_options\([^)\n]*' + quoted + r'[^)\n]*\)', source)
    loop = re.search(r'for \w+ in \([^)\n]*' + quoted + r'[^)\n]*\)\s*:', source)
    return bool(call or loop)


def _module_leaf(profile: SystemProfile) -> str:
    return type(profile).__module__.rsplit('.', 1)[-1]


def registry_problems(profile: SystemProfile) -> list[str]:
    """What this profile lacks. Tier one for every machine; tier two only when its status is `supported`."""
    system, problems = profile.id, []
    add = problems.append

    # --- the profile itself -------------------------------------------------------------------
    if profile.status not in STATUSES:
        add(f'status {profile.status!r} is not one of {STATUSES}')
    cpus = list(profile.cpus)
    if sum(cpu.role == 'main' for cpu in cpus) != 1:
        add('the profile must declare exactly one main CPU')
    if not profile.extensions or not set(profile.extensions) <= ROM_CANDIDATE_EXTENSIONS:
        add('extensions missing from systems.ROM_CANDIDATE_EXTENSIONS (discover_roms would skip them)')
    if not profile.video_modes or not profile.feedback_kinds or not profile.quick_state_family:
        add('video_modes, feedback_kinds and quick_state_family must be declared')
    if profile.linux not in ('witnessed', 'pending'):
        add('linux must be "witnessed" or "pending"')
    if system not in system_ids():
        add('not in systems.ALL_PROFILES / system_ids()')
        return problems  # the registries below derive from it; nothing more can be said

    # --- derived registries must follow the profile (they are lists today, data tomorrow) -------
    for name, listed in (('scan_levels.CONSOLES', scan_levels.CONSOLES), ('scan_levels.DEFAULT_FRAMES', scan_levels.DEFAULT_FRAMES),
                         ('scan_levels.QUICK_FRAMES', scan_levels.QUICK_FRAMES), ('feedback.KINDS', feedback.KINDS),
                         ('compilation_inputs.SYSTEMS', compilation_inputs.SYSTEMS)):
        if system not in listed:
            add(f'{name} does not list the console')

    # --- paths, schema 3 -----------------------------------------------------------------------
    sections = path_profiles.SYSTEM_SECTIONS.get(system)
    if system not in path_profiles.SYSTEMS or not path_profiles.GAME_KEY.fullmatch(f'{system}:' + '0' * 64):
        add('path_profiles.SYSTEMS (and so GAME_KEY) does not list the console')
    if not sections:
        add('path_profiles.SYSTEM_SECTIONS has no CPU section for the console')
    else:
        for section in sections:
            known = path_profiles.PROFILES.get(section)
            if known is None or system not in known.systems:
                add(f'path_profiles.PROFILES has no {section} profile naming the console')
    if system not in path_profiles.SOURCE_BOUNDS:
        add('path_profiles.SOURCE_BOUNDS has no source bounds for the console')

    # --- reports -------------------------------------------------------------------------------
    shape = report_schema._SHAPES.get(system)
    if shape is None:
        add('report_schema._SHAPES has no entry (read_report would refuse the console)')
    elif cpus:
        main = next((cpu for cpu in cpus if cpu.role == 'main'), None)
        sound = next((cpu for cpu in cpus if cpu.role == 'sound'), None)
        if main and (shape.main_arch, shape.main_unit) != (main.arch, main.unit):
            add('report_schema._SHAPES disagrees with the profile on the main CPU (a copy that must not drift)')
        if (sound.arch if sound else None) != shape.audio_arch:
            add('report_schema._SHAPES disagrees with the profile on the sound CPU')

    # --- fingerprints --------------------------------------------------------------------------
    try:
        names = compilation_inputs.manifest_names(system)
        if f'retrorecomp.systems.{_module_leaf(profile)}' not in names:
            add('stamp_inputs.INPUTS does not list the profile module for the console')
        if set(compilation_inputs.role_stamps(system)) != {'game', 'host', 'build'}:
            add('role_stamps did not return game, host and build')
    except (ValueError, KeyError, OSError) as error:
        add(f'the stamps cannot be computed: {error}')
    if profile.quick_state_family == 'rr16':
        if system not in hostkit.ADAPTERS:
            add('quick_state_family "rr16" needs an adapter in hostkit.ADAPTERS')
        elif f'native/{"hostkit/" + hostkit.ADAPTERS[system]}' not in compilation_inputs.manifest_names(system):
            add('the host-kit adapter is not listed for the console in stamp_inputs.INPUTS')

    # --- firmware the user supplies: one option per firmware, in the command line, the saved paths and the window
    for firmware in profile.firmware:
        option = f'{system}_{firmware}'
        if option not in profile.option_key_names:
            add(f'the profile declares the firmware {firmware!r} but no option_keys entry {option!r}')
        for where, source in (('RetroRecomp.py', _text('RetroRecomp.py')), ('retrorecomp/paths.py', _text('retrorecomp/paths.py')),
                              ('retrorecomp/gui.py', _text('retrorecomp/gui.py'))):
            token = '--' + option.replace('_', '-') if where == 'RetroRecomp.py' else option
            if token not in source:
                add(f'{where} does not carry {token!r} (firmware option of the console)')

    # --- interface: tab, scan note, translations in every language -------------------------------
    tab = LEGACY_TAB_KEYS.get(system, 'options_' + system)
    for key in (tab, 'scan_note_' + system):
        if key not in STRINGS:
            add(f'i18n.STRINGS has no {key!r}')
        else:
            for code in LANGUAGES[2:]:
                if not catalog(code).get('ui', {}).get(key):
                    add(f'assets/locales/{code}.json has no {key!r}')
    if not _gui_builds_the_tab(_text('retrorecomp/gui.py'), system):
        add('gui.py builds no options tab for the console (build_scan_options)')

    # --- documents and lints -------------------------------------------------------------------
    if system not in dict(status_lint.CONSOLES) or system not in status_lint.ALIASES:
        add('tools/status_lint.py (CONSOLES, ALIASES) does not know the console')
    names = status_lint.ALIASES.get(system, (profile.name,))
    pattern = re.compile(r'\b(?:' + '|'.join(re.escape(name) for name in names) + r')\b')
    if not pattern.search(status_lint.readme_section(_text('README.md'))):
        add('README.md "Console support" does not name the console')
    if not pattern.search(_text('docs/COMPATIBILITY.md')):
        add('docs/COMPATIBILITY.md does not name the console')
    matrix = _qualification_matrix()
    if system not in matrix:
        add('docs/QUALIFICATION.md has no column for the console in its status matrix')
    elif not all(cell in QUALIFICATION_CELLS for cell in matrix[system].values()) or len(matrix[system]) != 16:
        add('docs/QUALIFICATION.md: the console column must hold G1..G16, each one of Y P N ? -')
    if f'retrorecomp/systems/{_module_leaf(profile)}.py' not in _public_files():
        add('tools/prepare_publication.py PUBLIC_FILES does not list the profile module')

    # --- verification tools --------------------------------------------------------------------
    if system not in release_check.CONSOLES or not callable(release_check.READERS.get(system)):
        add('tools/release_check.py (CONSOLES, READERS) does not know the console')
    # A romset console is read from ZIPs whatever its own extension (Neo Geo also reads .neo).
    read = set(profile.extensions) | ({'.zip'} if 'romset' in profile.media_kinds else set())
    if system not in campaign.DEFAULT_FOLDERS or not set(campaign.EXTENSIONS.get(system, ())) & read:
        add('tools/campaign.py (DEFAULT_FOLDERS, EXTENSIONS) does not know the console')
    cases = json.loads(_text('tools/campaign-risk-cases.json'))['consoles']
    if system not in cases:
        add('tools/campaign-risk-cases.json has no list for the console (an empty list is allowed for an experimental one)')
    if system not in std_baseline.SYSTEMS or system not in std_baseline.CONSOLE_OPTIONS:
        add('tools/std_baseline.py (SYSTEMS, CONSOLE_OPTIONS) does not know the console')

    # --- registries a machine may decline, on the record --------------------------------------
    from retrorecomp import artwork, memory_view
    if system not in random_routes.CONSOLES and system not in DECLINED['random_routes']:
        add('random_routes.CONSOLES has no pad layout (or list the console in DECLINED["random_routes"] with the reason)')
    if system not in artwork.REPOSITORIES and system not in DECLINED['artwork']:
        add('artwork.REPOSITORIES has no box-art repository (or decline it in DECLINED["artwork"])')
    if f"'{system}':" not in Path(memory_view.__file__).read_text(encoding='utf-8') and system not in DECLINED['memory_view']:
        add('memory_view.summaries has no library pattern (or decline it in DECLINED["memory_view"])')

    # --- tier two: only a `supported` machine -------------------------------------------------
    if profile.status == 'supported':
        if profile.linux != 'witnessed':
            add('supported: the conversion must be witnessed on Linux (linux = "witnessed")')
        if system not in path_profiles.SHARED_SYSTEMS:
            add('supported: shared knowledge (gate G16) needs the console in path_profiles.SHARED_SYSTEMS')
        # Arthur, 27 Oct 2026: four or five risk cases a console, plus two random games.
        if len(cases.get(system, [])) < 4:
            add('supported: tools/campaign-risk-cases.json needs at least four risk cases')
        column = matrix.get(system, {})
        if any(cell == 'N' for cell in column.values()):
            add('supported: docs/QUALIFICATION.md records a failed gate (N)')
        if any(column.get(gate) not in ('Y', 'P') for gate in ('G1', 'G2', 'G4')):
            add('supported: gates G1 (status), G2 (report) and G4 (CPU fidelity) must be at least partial')
    return problems


def _public_files() -> set:
    import prepare_publication
    return set(prepare_publication.PUBLIC_FILES)


class RegistryTests(unittest.TestCase):
    def test_every_declared_machine_is_in_every_registry_it_needs(self):
        for profile in ALL_PROFILES:
            with self.subTest(profile.id):
                self.assertEqual(registry_problems(profile), [], profile.id)

    def test_the_tiers_exist_and_experimental_machines_are_not_asked_for_supported_gates(self):
        statuses = {profile.id: profile.status for profile in ALL_PROFILES}
        self.assertIn('experimental', statuses.values())
        self.assertIn('supported', statuses.values())
        # An experimental machine may have no risk case, no shared knowledge and no Linux witness yet.
        cases = json.loads(_text('tools/campaign-risk-cases.json'))['consoles']
        for profile in ALL_PROFILES:
            if profile.status == 'experimental':
                self.assertFalse([p for p in registry_problems(profile) if p.startswith('supported:')], profile.id)
        self.assertTrue(all(isinstance(cases[profile.id], list) for profile in ALL_PROFILES))

    def test_the_declined_registries_name_known_machines_and_are_still_true(self):
        from retrorecomp import artwork
        ids = set(system_ids())
        for registry, declined in DECLINED.items():
            self.assertLessEqual(declined, ids, registry)
        self.assertTrue(DECLINED['random_routes'].isdisjoint(random_routes.CONSOLES))
        self.assertTrue(DECLINED['artwork'].isdisjoint(artwork.REPOSITORIES))

    def test_the_qualification_matrix_has_one_column_per_machine_and_no_stranger(self):
        self.assertEqual(set(_qualification_matrix()), set(system_ids()))

    def test_the_lints_and_tools_list_exactly_the_machines_of_the_profiles(self):
        ids = set(system_ids())
        self.assertEqual({system for system, _ in status_lint.CONSOLES}, ids)
        self.assertEqual(set(status_lint.ALIASES), ids)
        self.assertEqual(set(release_check.CONSOLES), ids)
        self.assertEqual(set(release_check.READERS), ids)
        self.assertEqual(set(campaign.DEFAULT_FOLDERS), ids)
        self.assertEqual(set(std_baseline.SYSTEMS), ids)
        self.assertEqual(set(path_profiles.SYSTEMS), ids)
        self.assertEqual(set(report_schema._SHAPES), ids)
        self.assertEqual(set(path_profiles.SYSTEM_SECTIONS), ids)
        self.assertLessEqual(set(path_profiles.SHARED_SYSTEMS), ids)
        self.assertLessEqual(set(hostkit.ADAPTERS), ids)


class DetectionOfGapsTests(unittest.TestCase):
    """The check itself: a machine with no registry at all must be reported for each of them."""

    @staticmethod
    def profile(status='experimental', **attributes):
        class Fake(SystemProfile):
            id = 'zx'
            name = 'ZX Dry Run'
            extensions = ('.zxd',)
            export_folder = 'ZX'
            video_modes = ('pal',)
            cpus = (Cpu('z80', 'main', 'cycles'),)
            quick_state_family = 'rr16'
            feedback_kinds = frozenset({99})

            def read_rom(self, path):
                raise NotImplementedError

            def default_video_mode(self, path):
                return 'pal'

            def convert(self, path, **options):
                raise NotImplementedError

        Fake.status = status
        for key, value in attributes.items():
            setattr(Fake, key, value)
        return Fake()

    def test_an_unregistered_machine_is_reported_by_registry(self):
        problems = ' | '.join(registry_problems(self.profile()))
        self.assertIn('not in systems.ALL_PROFILES', problems)
        self.assertIn('ROM_CANDIDATE_EXTENSIONS', problems)

    def test_a_machine_in_the_profile_list_but_nowhere_else_misses_each_registry(self):
        from unittest.mock import patch
        fake = self.profile()
        with patch(__name__ + '.system_ids', return_value=(*system_ids(), 'zx')):
            problems = ' | '.join(registry_problems(fake))
        for expected in ('scan_levels.CONSOLES', 'feedback.KINDS', 'compilation_inputs.SYSTEMS',
                         'path_profiles.SYSTEMS', 'path_profiles.SYSTEM_SECTIONS', 'path_profiles.SOURCE_BOUNDS',
                         'report_schema._SHAPES', 'stamp_inputs.INPUTS', 'hostkit.ADAPTERS', "i18n.STRINGS has no 'options_zx'",
                         "i18n.STRINGS has no 'scan_note_zx'", 'gui.py builds no options tab', 'status_lint',
                         'README.md', 'docs/COMPATIBILITY.md', 'docs/QUALIFICATION.md has no column',
                         'prepare_publication', 'release_check', 'campaign.py', 'campaign-risk-cases', 'std_baseline',
                         'random_routes', 'artwork', 'memory_view'):
            self.assertIn(expected, problems)
        self.assertNotIn('supported:', problems)  # an experimental machine is not asked for the supported gates

    def test_a_supported_machine_is_also_asked_for_the_supported_gates(self):
        from unittest.mock import patch
        fake = self.profile('supported', linux='pending')
        with patch(__name__ + '.system_ids', return_value=(*system_ids(), 'zx')):
            problems = ' | '.join(registry_problems(fake))
        for expected in ('supported: the conversion must be witnessed on Linux', 'supported: shared knowledge',
                         'supported: tools/campaign-risk-cases.json needs at least four'):
            self.assertIn(expected, problems)

    def test_a_status_outside_the_two_known_ones_is_reported(self):
        self.assertIn("status 'beta' is not one of", ' | '.join(registry_problems(self.profile('beta'))))


if __name__ == '__main__':
    unittest.main()
