"""The Game Boy Advance's shared paths on authored cartridges: numbers only, no game, no ROM byte, no engine, no BIOS."""
import hashlib
import json
import os
import random
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from retrorecomp import (gba_analysis as analysis, gba_build as build, gba_conversion, gba_knowledge as gk, gba_patches, knowledge, knowledge_exchange,
                         path_profiles as pp)
from retrorecomp.core import ConversionError
from tests.test_gba_profile import synthetic_cartridge

# The SHA-256 of the patches that touch the recompiler's generated code or the engine's ARM core (`gba_knowledge.pinned_patches`: file, anchor, replacement).
# THE ENGINE REVISION RULE (docs/COMPILATION_LIBRARY.md): the patch set is not part of the `cores` of a shared path. This test is what keeps that honest.
# When it fails you changed, added or removed such a patch. Decide in the same change whether a path could notice it (does the generator accept other roots,
# are RAM copies read differently, does the decoder decode a function entry otherwise?): if so raise `gba_knowledge.PATH_REVISION` (every qualified row
# of the base then goes back to pending until a conversion of the new revision reaches it), and in both cases write the new digest here.
PINNED_PATCHES_SHA256 = '5f7fd5168a9cd53d5f1baa3ff5402940ca47c815d6b5d110b802ac9b3274f357'
PINNED_PATCH_COUNT = 24         # the recompiler's and the core's patches, and the four of the probe that hold a recorder

ROM = random.Random(1).randbytes(0x4000)
IDENTITY = hashlib.sha256(ROM).hexdigest()
OTHER = hashlib.sha256(random.Random(2).randbytes(0x4000)).hexdigest()
ROOTS = [0x100, 0x201, 0x3000, 0x3F01]                                 # ARM, Thumb, ARM, Thumb
SPANS = [(0x03000100, 0x400, 0x40), (0x02001001, 0x800, 0x100)]        # IWRAM ARM, EWRAM Thumb


def record(roots=ROOTS, spans=SPANS, rom=ROM, core=None):
    return gk.make_record(hashlib.sha256(rom).hexdigest(), rom, roots, spans, core=core)


def observations(roots=(), spans=()):
    return analysis.Observations(set(roots), set(spans))


class RecordTests(unittest.TestCase):
    def test_a_record_passes_the_schema_3_validator_with_an_empty_layout(self):
        value = record()
        pp.validate_game(value)
        self.assertEqual(gk.validate_record(value, IDENTITY), value)
        self.assertEqual(value['identity']['layout'], {})
        self.assertEqual(value['identity']['sources'], {'rom': {'bytes': len(ROM), 'sha256': IDENTITY}})
        self.assertEqual(gk.rows(value), (sorted(ROOTS), sorted(SPANS)))

    def test_record_rules_state_what_validate_record_enforces(self):
        """RECORD_RULES is what the site's builder reads, so it must say what the converter enforces: an interpreter of the rules (the one `paths3.php` has) and
        `validate_record` accept and refuse the same records, among records the schema and the profile accept (windows, lengths, offsets' halfword alignment)."""
        from retrorecomp import path_profiles
        rules = gk.RECORD_RULES

        def accepted_by_rules(value) -> bool:
            identity = value['identity']
            sources = identity['sources']
            if list(identity['layout']) != rules['layout'] or set(sources) - set(rules['sources']['only']) or set(rules['sources']['required']) - set(sources):
                return False
            if rules['sources']['hashed'] and not all('sha256' in source for source in sources.values()):
                return False
            if value['game'] != gk.SYSTEM + ':' + sources[rules['sources']['game']]['sha256']:
                return False
            for cpu, section in value['cpus'].items():
                for kind, blocks in section['paths'].items():
                    rule = rules['paths'][cpu][kind]
                    for block in blocks:
                        if block['src'] != rule['src']:
                            return False
                        for row in path_profiles.decode_table(block['table'], 1 if block['shape'] == 'phys' else 3, 1 << 20):
                            for index in ((0, 1) if block['shape'] == 'span' else (0,)):
                                if not (row[0] & 1 or row[index] % rule['even_align'] == 0):
                                    return False
            return True

        def with_rows(roots, spans, game=IDENTITY, sha=IDENTITY):
            value = gk.build_record(sha, len(ROM), gk.engine(), roots, spans)
            value['game'] = f'{gk.SYSTEM}:{game}'
            return value

        cases = [
            (with_rows(ROOTS, SPANS), True),
            (with_rows([0x100], []), True), (with_rows([0x102], []), False), (with_rows([0x103], []), True), (with_rows([0x104], []), True),
            (with_rows([], [(0x03000100, 0x400, 0x40)]), True), (with_rows([], [(0x03000102, 0x400, 0x40)]), False),
            (with_rows([], [(0x03000100, 0x402, 0x40)]), False), (with_rows([], [(0x03000103, 0x402, 0x40)]), True),
            (with_rows([], [(0x03007FFE, 0, 2)]), False),
            (with_rows([], [(0x02000000, 2 * number, 0x100) for number in range(1, 5)]), False),
            (with_rows(ROOTS, SPANS, game=OTHER), False),
        ]
        for number, (value, expected) in enumerate(cases):
            with self.subTest(case=number):
                try:
                    gk.validate_record(value)
                    enforced = True
                except ValueError:
                    enforced = False
                self.assertEqual(enforced, expected)
                self.assertEqual(accepted_by_rules(value), expected)
        self.assertEqual(rules['layout'], [])
        self.assertEqual(set(rules['paths'][gk.CPU]), {'entries', 'spans'})

    def test_the_players_own_store_and_the_shared_record_have_one_writer(self):
        self.assertEqual(analysis.record(IDENTITY, len(ROM), gk.engine(), observations(ROOTS, SPANS)), record())

    def test_a_record_holds_numbers_about_the_cartridge_and_no_byte_of_it(self):
        roots = [value & ~3 for value in random.Random(5).sample(range(0, len(ROM) - 2), 300)]
        spans = [(0x03000000 + 0x40 * n, 0x40 * n + 0x400, 0x40) for n in range(100)]
        text = json.dumps(record(roots, spans))
        for start in range(0, len(ROM) - 16, 16):
            self.assertNotIn(ROM[start:start + 16].hex(), text)
        for key in ('data', 'bytes_of', 'live', 'sample', 'bios'):
            self.assertNotIn(key, text.replace('"bytes"', ''))

    def test_equal_paths_give_equal_documents_whatever_their_order(self):
        self.assertEqual(record(), record(list(reversed(ROOTS)), list(reversed(SPANS))))

    def test_an_empty_record_is_valid_and_is_the_nothing_to_learn_case(self):
        value = record([], [])
        self.assertEqual(value['cpus']['arm7tdmi']['paths'], {})
        self.assertEqual(gk.rows(gk.validate_record(value, IDENTITY)), ([], []))
        self.assertEqual(gk.entry_set(value), set())

    def test_the_names_of_the_paths_are_the_ones_entry_set_gives_and_the_ceilings_the_profiles(self):
        names = {name for name, _ in gk.entry_set(record())}
        self.assertEqual(names, set(gk.PATH_CAPS))
        profile = pp.PROFILES[('arm7tdmi', 'gba')]
        self.assertEqual(gk.PATH_CAPS, {'gba_root': profile.caps['phys'], 'gba_span': profile.caps['span']})
        self.assertEqual(gk.PATH_CAPS, {'gba_root': 262144, 'gba_span': 4096})

    def test_rebuild_and_merge_keep_the_paths(self):
        value = record()
        self.assertEqual(gk.rebuild(value, gk.entry_set(value)), value)
        self.assertEqual(gk.rows(gk.rebuild(value, set())), ([], []))
        first, second = record(ROOTS[:2], SPANS[:1]), record(ROOTS[2:], SPANS[1:])
        self.assertEqual(gk.merged(IDENTITY, first, second), value)
        self.assertEqual(gk.merged(IDENTITY, {}, second), second)

    def test_records_of_another_engine_or_cartridge_never_mix(self):
        current, old = record(ROOTS[:1], []), record(ROOTS[1:], [], core='0' * 40)
        self.assertEqual(gk.merged(IDENTITY, current, old), current)
        self.assertEqual(gk.merged(IDENTITY, old, current), current)
        other = random.Random(2).randbytes(0x4000)
        self.assertEqual(gk.merged(IDENTITY, current, record(ROOTS[1:], [], rom=other)), current)

    def test_the_rules_beyond_the_schema_are_refused(self):
        def tampered(change):
            value = json.loads(json.dumps(record()))
            change(value)
            return value
        entries = lambda value: value['cpus']['arm7tdmi']['paths']['entries'][0]
        refused = {
            'an ARM root that is not a multiple of 4': lambda v: entries(v).update(table=pp.encode_table([[0x102]], 1)),
            'a root past the cartridge': lambda v: entries(v).update(table=pp.encode_table([[len(ROM)]], 1)),
            'a RAM copy outside work RAM': lambda v: v['cpus']['arm7tdmi']['paths']['spans'][0].update(table=pp.encode_table([[0x04000000, 0x400, 0x40]], 3)),
            'a RAM copy with an odd cartridge offset': lambda v: v['cpus']['arm7tdmi']['paths']['spans'][0].update(table=pp.encode_table([[0x03000100, 0x401, 0x40]], 3)),
            'a RAM copy past the cartridge': lambda v: v['cpus']['arm7tdmi']['paths']['spans'][0].update(table=pp.encode_table([[0x03000100, len(ROM) - 2, 0x40]], 3)),
            'a RAM copy leaving its memory': lambda v: v['cpus']['arm7tdmi']['paths']['spans'][0].update(table=pp.encode_table([[0x03007FF0, 0x400, 0x40]], 3)),
            'an extra field': lambda v: v['cpus']['arm7tdmi'].update(extra=1),
            'bytes in the sources': lambda v: v['identity']['sources']['rom'].update(data='00'),
            'a table of raw bytes': lambda v: entries(v).update(table={'n': 1, 'cols': [{'raw': '00'}]}),
            'a source without its hash': lambda v: v['identity']['sources']['rom'].pop('sha256'),
            'a layout': lambda v: v['identity'].update(layout={'format': 1}),
            'a second source': lambda v: v['identity']['sources'].update(disk={'bytes': 4}),
            'a device': lambda v: v.update(devices={'gsu': {'core': '0' * 40, 'paths': {}}}),
            'a source that is not the key': lambda v: v['identity']['sources']['rom'].update(sha256=OTHER),
            'a block into the wrong image': lambda v: entries(v).update(src='bios'),
        }
        for name, change in refused.items():
            with self.subTest(name), self.assertRaises(ValueError):
                gk.validate_record(tampered(change))
            self.assertIsNone(gk.salvaged_record(IDENTITY, tampered(change)), name)
        with self.assertRaises(ValueError):
            gk.validate_record(record(), OTHER)                                 # a record of another cartridge
        for value in (None, [], {}, 'x', {'schema': 3}):
            with self.assertRaises(ValueError):
                gk.validate_record(value)

    def test_the_rules_beyond_the_schema_are_accepted_where_the_schema_allows_them(self):
        gk.validate_record(record([0x0, 0x1, len(ROM) - 4, len(ROM) - 1], [(0x03007FC0, 0x0, 0x40), (0x02000000, 0x0, 2)]))

    def test_a_record_the_writer_cannot_hold_is_a_bug_not_a_truncation(self):
        odd = record([0x102])                                                    # the player's own store writes what the runs saw (the schema accepts it)...
        with self.assertRaises(ValueError):
            gk.validate_record(odd)                                              # ...a record that travels must follow the module's own rule too
        with mock.patch.object(gk, 'ROOT_LIMIT', 2):
            with self.assertRaises(ValueError):
                record(ROOTS)

    def test_the_digest_names_a_record_and_moves_with_a_row(self):
        self.assertEqual(gk.record_digest(record()), gk.record_digest(record()))
        self.assertNotEqual(gk.record_digest(record()), gk.record_digest(record(ROOTS[:3])))


class EngineIdentityTests(unittest.TestCase):
    def test_the_cores_string_is_the_revision_of_our_use_and_the_two_pins(self):
        self.assertEqual(gk.engine(), hashlib.sha1(f'gba:{gk.PATH_REVISION}:{gba_conversion.ENGINE_REV}:{gba_conversion.ARM_CORE_REV}'.encode()).hexdigest())
        self.assertRegex(gk.engine(), '^[0-9a-f]{40}$')
        self.assertEqual(gk.record_engine(record()), gk.engine())
        self.assertEqual(gk.record_engine({}), '')

    def test_it_moves_with_the_path_revision_and_with_each_pin(self):
        base = gk.engine()
        with mock.patch.object(gk, 'PATH_REVISION', gk.PATH_REVISION + 1):
            self.assertNotEqual(gk.engine(), base)
        with mock.patch.object(gba_conversion, 'ENGINE_REV', '0' * 40):
            self.assertNotEqual(gk.engine(), base)
        with mock.patch.object(gba_conversion, 'ARM_CORE_REV', '0' * 40):
            self.assertNotEqual(gk.engine(), base)

    def test_it_does_not_move_with_the_patch_set_or_our_stamp(self):
        base = gk.engine()
        shipped = gba_patches.PATCHES
        added = shipped + (('src/recompile/ram_templates.cpp', 'a', 'b', 'a patch that did not exist'),)
        with mock.patch.object(gba_patches, 'PATCHES', added):
            self.assertEqual(gk.engine(), base)
            self.assertNotEqual(gk.patch_pin(), gk.patch_pin(shipped))                  # ...but the pin of the recompiler's patches sees it

    def test_the_recompiler_side_patches_are_pinned_a_change_needs_a_decision_about_the_path_revision(self):
        pinned = gk.pinned_patches()
        self.assertEqual(len(pinned), PINNED_PATCH_COUNT)
        self.assertTrue(all(file.startswith(gk.PINNED_PATCH_PREFIXES) or any(marker in new for marker in gk.RECORDER_MARKERS) for file, _, new in pinned))
        self.assertEqual(gk.patch_pin(), PINNED_PATCHES_SHA256,
                         'A patch of the Game Boy Advance engine that touches src/recompile, src/armv4t or external/arm-recomp-core was changed. Decide whether '
                         'gba_knowledge.PATH_REVISION must be raised (could a shared path notice the change?), then pin the new digest in this test.')

    def test_the_patches_of_the_bus_the_probe_and_the_player_seam_are_not_pinned(self):
        files = {file for file, _, _ in gk.pinned_patches()}
        self.assertFalse({file for file in files if file.startswith('src/gba/')})              # the bus is not pinned; the probe's recorders are
        outside = [patch for patch in gba_patches.PATCHES if not (patch[0].startswith(gk.PINNED_PATCH_PREFIXES) or any(m in patch[2] for m in gk.RECORDER_MARKERS))]
        self.assertEqual(len(outside) + PINNED_PATCH_COUNT, len(gba_patches.PATCHES))
        self.assertEqual(gk.patch_pin(), gk.patch_pin(tuple(patch[:3] + ('another note',) if patch in gba_patches.PATCHES[:1] else patch
                                                           for patch in gba_patches.PATCHES)))      # the notes are prose


class PromotionTests(unittest.TestCase):
    def test_promote_keeps_the_previous_paths_of_this_cartridge_and_engine_and_says_what_it_did(self):
        first, _ = gk.promote(IDENTITY, ROM, observations(ROOTS[:2], SPANS[:1]))
        second, counts = gk.promote(IDENTITY, ROM, observations(ROOTS[2:], SPANS[1:]), previous=first, private={'ram_code_addresses': 3})
        self.assertEqual(gk.rows(second), (sorted(ROOTS), sorted(SPANS)))
        self.assertEqual(counts['paths'], {'roots': 4, 'ram_copies': 2})
        self.assertEqual(counts['private'], {'ram_code_addresses': 3})
        self.assertFalse(counts['truncated'])
        self.assertFalse(counts['raw_bytes_stored'])
        self.assertEqual(gk.validate_record(second, IDENTITY), second)

    def test_a_previous_record_of_another_engine_or_cartridge_is_not_kept(self):
        old = record(ROOTS[:1], [], core='0' * 40)
        value, _ = gk.promote(IDENTITY, ROM, observations(ROOTS[1:2]), previous=old)
        self.assertEqual(gk.rows(value), ([ROOTS[1]], []))
        other = random.Random(2).randbytes(0x4000)
        value, _ = gk.promote(IDENTITY, ROM, observations(ROOTS[1:2]), previous=record(ROOTS[:1], [], rom=other))
        self.assertEqual(gk.rows(value), ([ROOTS[1]], []))

    def test_a_row_that_breaks_a_rule_is_refused_and_counted_not_shared(self):
        value, counts = gk.promote(IDENTITY, ROM, observations([0x102, 0x100, len(ROM) + 8], [(0x04000000, 0x400, 0x40), SPANS[0]]))
        self.assertEqual(gk.rows(value), ([0x100], [SPANS[0]]))
        self.assertEqual(counts['refused'], {'roots': 2, 'spans': 1})

    def test_the_bounds_keep_a_deterministic_subset_and_say_so(self):
        with mock.patch.object(gk, 'ROOT_LIMIT', 3):
            value, counts = gk.promote(IDENTITY, ROM, observations([0x400, 0x100, 0x300, 0x200, 0x500]))
        self.assertEqual(gk.rows(value)[0], [0x100, 0x200, 0x300])
        self.assertTrue(counts['truncated'])
        self.assertEqual(counts['left_out_by_the_bounds'], {'roots': 2, 'ram_copies': 0})
        with mock.patch.object(gk, 'SPAN_LIMIT', 1):
            value, counts = gk.promote(IDENTITY, ROM, observations([], SPANS))
        self.assertEqual(gk.rows(value)[1], [SPANS[1]])                                        # sorted: the lowest address first is EWRAM
        self.assertEqual(counts['left_out_by_the_bounds']['ram_copies'], 1)

    def test_a_nothing_to_learn_conversion_still_promotes_an_empty_valid_record(self):
        value, counts = gk.promote(IDENTITY, ROM, observations())
        self.assertEqual(gk.rows(value), ([], []))
        self.assertEqual(counts['paths'], {'roots': 0, 'ram_copies': 0})

    def test_the_key_is_the_cartridge_and_nothing_else(self):
        with self.assertRaises(ValueError):
            gk.promote(OTHER, ROM, observations(ROOTS))


class ReceivedRowsTests(unittest.TestCase):
    def test_a_qualified_row_of_this_engine_is_qualified_by_the_base_and_an_imported_one_is_pending(self):
        used, info = gk.shared_rows(IDENTITY, len(ROM), qualified=record(ROOTS[:2], SPANS[:1]), imported=record(ROOTS[2:], SPANS[1:]))
        self.assertEqual((used.roots, used.spans), (set(ROOTS), set(SPANS)))
        self.assertEqual((info['qualified_by_the_base'], info['pending'], info['used_roots'], info['used_ram_copies']), (3, 3, 4, 2))
        self.assertEqual(info['records'], {'qualified': 1, 'imported': 1})
        self.assertEqual(info['ignored'], {})

    def test_a_qualified_record_of_another_engine_is_pending_not_ignored(self):
        old = record(core='0' * 40)
        used, info = gk.shared_rows(IDENTITY, len(ROM), qualified=old)
        self.assertEqual((len(used.roots), len(used.spans)), (4, 2))
        self.assertEqual((info['qualified_by_the_base'], info['pending'], info['pending_from_another_cores']), (0, 6, 6))

    def test_a_row_both_banks_hold_counts_as_qualified_once(self):
        used, info = gk.shared_rows(IDENTITY, len(ROM), qualified=record(ROOTS[:1], []), imported=record(ROOTS[:2], []))
        self.assertEqual((used.roots, info['qualified_by_the_base'], info['pending']), (set(ROOTS[:2]), 1, 1))

    def test_what_the_player_already_found_is_not_received_again(self):
        used, info = gk.shared_rows(IDENTITY, len(ROM), imported=record(), own=observations(ROOTS[:2], SPANS[:1]))
        self.assertEqual((used.roots, used.spans), (set(ROOTS[2:]), set(SPANS[1:])))
        self.assertEqual((info['received_roots'], info['received_ram_copies'], info['already_known']), (4, 2, 3))

    def test_another_cartridge_or_a_broken_record_is_ignored_and_the_reason_counted(self):
        other = random.Random(2).randbytes(0x4000)
        used, info = gk.shared_rows(IDENTITY, len(ROM), imported=record(rom=other))
        self.assertEqual((used.size(), info['records']['imported']), (0, 0))
        self.assertIn('imported', info['ignored'])
        used, info = gk.shared_rows(IDENTITY, len(ROM) + 2, imported=record())            # the same hash cannot have another size; a lying record is refused too
        self.assertEqual(used.size(), 0)
        self.assertIn('another cartridge image', info['ignored']['imported'])
        used, info = gk.shared_rows(IDENTITY, len(ROM), qualified={'schema': 3}, imported=None)
        self.assertEqual((used.size(), 'qualified' in info['ignored']), (0, True))

    def test_received_spans_cannot_use_up_the_mirrors_of_one_address_and_an_arm_copy_is_word_aligned(self):
        spans = [(0x03000100, 0x1000 + number * 0x100, 0x40) for number in range(30)]
        used, info = gk.shared_rows(IDENTITY, len(ROM), imported=record([], spans), cap=16)
        self.assertEqual((len(used.spans), info['left_out_by_the_cap']['ram_copies']), (gk.SPAN_VERSIONS_PER_ADDRESS, 30 - gk.SPAN_VERSIONS_PER_ADDRESS))
        self.assertFalse(gk.span_valid((0x03000102, 0x1000, 0x40), len(ROM)))           # ARM, not word aligned in RAM
        self.assertFalse(gk.span_valid((0x03000100, 0x1002, 0x40), len(ROM)))           # ARM, not word aligned in the cartridge
        self.assertTrue(gk.span_valid((0x03000103, 0x1002, 0x40), len(ROM)))            # Thumb: the halfword is enough

    def test_a_generator_that_loops_on_a_received_root_is_stopped_and_the_conversion_is_tried_again_without_the_rows(self):
        import subprocess
        from unittest import mock
        from retrorecomp import gba_build
        from retrorecomp.core import ConversionError
        timed_out = subprocess.TimeoutExpired(['gba_recompile'], 300)
        with mock.patch.object(gba_build, 'run', side_effect=timed_out):
            with self.assertRaises(ConversionError) as caught:
                gba_build.generate_game(Path('gba_recompile'), Path('rom'), Path('game.toml'), Path(tempfile.mkdtemp()), lambda text: None, timeout=300)
        self.assertIn('300 seconds', str(caught.exception))                                 # an error the conversion's retry catches, never a raw timeout
        self.assertLess(gba_build.RECEIVED_GENERATION_TIMEOUT, gba_build.GENERATION_TIMEOUT)

    def test_a_conversion_that_fails_with_received_rows_is_converted_again_without_them(self):
        from unittest import mock
        from retrorecomp import gba_conversion
        from retrorecomp.core import ConversionError
        calls = []

        def fake(path, *, use_shared=True, set_aside='', _state=None, **arguments):
            calls.append((use_shared, set_aside))
            if use_shared:
                _state['received_rows'] = 3
                raise ConversionError('the generator refused a root')
            return 'converted'

        with mock.patch.object(gba_conversion, '_convert', fake):
            self.assertEqual(gba_conversion.convert(Path('x.gba'), emit=lambda text: None), 'converted')
        self.assertEqual(calls, [(True, ''), (False, 'the generator refused a root')])
        calls.clear()

        def without_received(path, *, _state=None, **arguments):
            calls.append('once')
            raise ConversionError('a real failure')

        with mock.patch.object(gba_conversion, '_convert', without_received):
            with self.assertRaises(ConversionError):
                gba_conversion.convert(Path('x.gba'), emit=lambda text: None)
        self.assertEqual(calls, ['once'])                                                 # no received row: no second conversion

    def test_pending_roots_are_capped_and_the_rest_counted_as_left_out_while_qualified_rows_never_are(self):
        pending = [value * 4 for value in range(100, 140)]                                  # 40 roots
        used, info = gk.shared_rows(IDENTITY, len(ROM), qualified=record([0x40], []), imported=record(pending + [0x40], []), cap=16)
        self.assertEqual(len(used.roots), 17)                                                # 16 pending, 1 qualified
        self.assertIn(0x40, used.roots)                                                      # the qualified one is always used
        again, _ = gk.shared_rows(IDENTITY, len(ROM), qualified=record([0x40], []), imported=record(pending + [0x40], []), cap=16)
        self.assertEqual(sorted(again.roots), sorted(used.roots))                            # a deterministic subset, in the order of a hash (not the lowest offsets)
        self.assertNotEqual(sorted(used.roots)[1:], [value * 4 for value in range(100, 116)])
        self.assertEqual((info['pending'], info['qualified_by_the_base'], info['left_out_by_the_cap']['roots'], info['pending_root_cap']), (16, 1, 24, 16))
        used, info = gk.shared_rows(IDENTITY, len(ROM), qualified=record(pending, []), cap=16)
        self.assertEqual((len(used.roots), info['left_out_by_the_cap']['roots']), (40, 0))
        self.assertEqual(gk.PENDING_ROOT_CAP, 16384)

    def test_nothing_is_marked_qualified_by_this_converter_and_the_proof_is_only_the_own_misses(self):
        used, info = gk.shared_rows(IDENTITY, len(ROM), imported=record())
        proof = gk.reached(used, observations(ROOTS[:1] + [0x900], SPANS[:1]))
        self.assertEqual(proof, {'received_rows_used': 6, 'reached_by_own_misses': 2, 'not_proven': 4})
        shared = gk.shared_paths_report(info, proof)
        self.assertEqual(shared['qualified_by_this_converter'], 0)
        self.assertEqual(shared['pending'], 6)
        self.assertIn('marks none qualified', shared['note'])
        self.assertEqual(gk.reached(observations(), observations(ROOTS)), {'received_rows_used': 0, 'reached_by_own_misses': 0, 'not_proven': 0})


class SharingTests(unittest.TestCase):
    def test_the_machine_is_in_the_experimental_tier_and_withdrawn_with_it(self):
        self.assertIn('gba', pp.EXPERIMENTAL_SHARED)
        self.assertIn('gba', pp.SCHEMA3_ONLY)
        self.assertIn('gba', pp.WITHDRAWABLE)
        self.assertIs(knowledge.schema3_module('gba'), gk)
        with mock.patch.object(pp, 'SHARED_SYSTEMS', tuple(s for s in pp.SHARED_SYSTEMS if s != 'gba')):
            self.assertIsNone(knowledge.schema3_module('gba'))
        from retrorecomp.systems import get_profile
        declared = get_profile('gba').shared_knowledge
        self.assertEqual((declared.tier, declared.withdrawable, declared.quick_check_from_shared, declared.module), ('experimental', True, False, 'gba_knowledge'))

    def test_the_exchange_reads_the_record_as_a_version_3_file_and_compares_its_rows(self):
        value = record()
        knowledge_exchange.validate_mixed_payload({'schema': 1, 'consoles': {'gba': {IDENTITY: value}}})
        with self.assertRaises(ValueError):
            knowledge_exchange.validate_mixed_payload({'schema': 1, 'consoles': {'gba': {OTHER: value}}})
        self.assertEqual(knowledge_exchange.unknown_hints('gba', value), 6)
        self.assertEqual(knowledge_exchange.unknown_hints('gba', value, record(ROOTS[:1], [])), 5)
        self.assertEqual(knowledge_exchange.record_engine('gba', value), gk.engine())
        self.assertEqual(knowledge_exchange._current_engines()['gba'], gk.engine())

    def test_a_side_bank_holds_the_record_for_its_cartridge(self):
        with tempfile.TemporaryDirectory() as folder:
            bank = Path(folder) / 'imported-v3.json.gz'
            knowledge.write_side_bank(bank, {'gba:' + IDENTITY: record()})
            self.assertEqual(knowledge.read_side_bank(bank), {'gba:' + IDENTITY: record()})
            with self.assertRaises(ValueError):
                knowledge.write_side_bank(bank, {'gba:' + OTHER: record()})

    def test_the_library_reads_only_a_record_a_passed_conversion_wrote(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            with mock.patch('retrorecomp.library.library_root', lambda system: folder):
                self.assertIsNone(gk.library_record(IDENTITY))
                (folder / IDENTITY).mkdir()
                summary = folder / IDENTITY / 'compilation.json'
                summary.write_text(json.dumps({'system': 'gba', 'game': IDENTITY, 'fresh_reference_passed': False, 'record': record()}), encoding='utf-8')
                self.assertIsNone(gk.library_record(IDENTITY))
                summary.write_text(json.dumps({'system': 'gba', 'game': IDENTITY, 'fresh_reference_passed': True, 'record': record()}), encoding='utf-8')
                self.assertEqual(gk.library_record(IDENTITY), record())
                summary.write_text(json.dumps({'system': 'gba', 'game': OTHER, 'fresh_reference_passed': True, 'record': record()}), encoding='utf-8')
                self.assertIsNone(gk.library_record(IDENTITY))

    def test_the_report_block_names_the_record_and_never_claims_a_reached_row(self):
        value, promotion = gk.promote(IDENTITY, ROM, observations(ROOTS, SPANS), private={'unresolved_misses': 2})
        block = gk.knowledge_block(value, promotion, {'pending': 0})
        self.assertEqual((block['record_sha256'], block['cores'], block['shared'], block['machine_status']), (gk.record_digest(value), gk.engine(), True, 'experimental'))
        self.assertFalse(block['raw_bytes_stored'])
        self.assertFalse(block['raw_bytes_stored'])
        self.assertEqual(block['promotion']['private'], {'unresolved_misses': 2})


class ConversionWiringTests(unittest.TestCase):
    """`gba_conversion.convert` with the engine, the toolchain and the probe faked: the wiring of the received rows and of the promoted record."""
    SIZE = 0x2000

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.cartridge = self.root / 'Authored (World).gba'
        self.cartridge.write_bytes(synthetic_cartridge(size=self.SIZE, save=b'SRAM_V113'))
        self.sha = hashlib.sha256(self.cartridge.read_bytes()).hexdigest()
        self.bios = self.root / 'gba_bios.bin'
        self.bios.write_bytes(bytes(16384))
        self.configs, self.passes_seen = [], []
        self.misses = {1: '[[extra_func]]\naddr = 0x08000100\nmode = "thumb"\n'}        # pass 1 reaches a function the engine's analysis did not find
        self.reference_differs = False
        environment = {name: value for name, value in os.environ.items()
                       if name not in ('RETRO_RECOMP_LIBRARY_DIR', 'SMSRECOMP_LIBRARY_DIR', 'RETRO_RECOMP_BUNDLED_KNOWLEDGE')}
        self.datas = self.root / 'datas'
        knowledge._side_games.cache_clear()
        self.addCleanup(knowledge._side_games.cache_clear)
        for item in (mock.patch.dict(os.environ, environment, clear=True), mock.patch('retrorecomp.paths.data_directory', return_value=self.datas),
                     mock.patch('retrorecomp.library.library_root', side_effect=lambda system='sms': self.root / 'library' / system),
                     mock.patch('retrorecomp.paths.ROOT', self.root), mock.patch('retrorecomp.gba.bios_status', return_value='known'),
                     mock.patch('retrorecomp.platforms.require_backend'), mock.patch('retrorecomp.core.toolchain', return_value=(None, 'Ninja')),
                     mock.patch('retrorecomp.gba_engine.checkout', return_value=self.root),
                     mock.patch('retrorecomp.gba_engine.stage', return_value=(self.root, [])), mock.patch.object(build, 'recompiler', return_value=self.root),
                     mock.patch.object(build, 'generate_bios', return_value=self.root), mock.patch.object(build, 'generate_game', side_effect=self.generate),
                     mock.patch.object(build, 'host_project'), mock.patch.object(build, 'build_host', return_value=self.root / 'probe.exe'),
                     mock.patch.object(build, 'run_scenario', side_effect=self.run_scenario)):
            item.start()
            self.addCleanup(item.stop)

    def generate(self, recompile, rom_path, config, out, emit, timeout=None):
        self.configs.append(Path(config).read_text(encoding='utf-8'))
        return {'functions': 10 + len(self.configs), 'arm': 5, 'thumb': 5, 'shards': 1}

    def run_scenario(self, host, rom_file, sha1, bios, runs, name, frames, script, timeout=None, reference=False):
        number = len(self.configs)
        misses = '' if reference else self.misses.get(number, '')
        interpreted = 0 if reference or not misses else 40
        different = reference and self.reference_differs
        return build.Run(name, frames, 0, '', {'interpreted_insns': interpreted, 'coverage': 'NOT_STATIC' if interpreted else 'FULLY_STATIC', 'distinct_misses': 1 if misses else 0},
                         misses, None, '', 'picture' if not different else 'other', 1000, 'memory', 'registers')

    def receive(self, roots=(0x200, 0x301), spans=((0x03000100, 0x400, 0x40),), core=None):
        rom = self.cartridge.read_bytes()
        knowledge.write_side_bank(self.datas / 'knowledge' / 'imported-v3.json.gz', {'gba:' + self.sha: gk.make_record(self.sha, rom, roots, spans, core=core)})
        knowledge._side_games.cache_clear()

    def convert(self, **options):
        return gba_conversion.convert(self.cartridge, passes=2, frames=60, gba_bios=str(self.bios), player=False, emit=lambda text: None, **options)

    def report(self):
        projects = list((self.root / '.build').glob('gba_*'))
        self.assertEqual(len(projects), 1)
        return json.loads((projects[0] / 'conversion-report.json').read_text(encoding='utf-8'))

    def library(self):
        return self.root / 'library' / 'gba' / self.sha

    def test_without_received_rows_the_record_is_the_conversions_own_misses_and_the_report_says_none_were_received(self):
        self.convert()
        self.assertEqual(len(self.configs), 2)
        report = self.report()
        shared = report['native_coverage']['shared_paths']
        self.assertEqual((shared['used_roots'], shared['used_ram_copies'], shared['qualified_by_this_converter']), (0, 0, 0))
        stored = analysis.observations_of(json.loads((self.library() / gba_conversion.ENGINE_REV / 'paths.json').read_text(encoding='utf-8')))
        self.assertEqual(stored.roots, {0x101})
        promoted = gk.library_record(self.sha)
        self.assertEqual(gk.rows(promoted), ([0x101], []))
        self.assertEqual(report['knowledge']['record_sha256'], gk.record_digest(promoted))
        self.assertEqual(report['knowledge']['cores'], gk.engine())

    def test_received_rows_are_build_input_kept_apart_counted_pending_and_never_saved_or_shared(self):
        self.receive()
        self.convert()
        first, last = self.configs
        for text in (first, last):                                                  # built from the first pass on, with the player's own rows added after
            self.assertIn('addr = 0x08000200\nmode = "arm"', text)
            self.assertIn('addr = 0x08000300\nmode = "thumb"', text)
            self.assertIn('runtime_start = 0x03000100', text)
        self.assertNotIn('0x08000100', first)
        self.assertIn('addr = 0x08000100\nmode = "thumb"', last)
        stored = analysis.observations_of(json.loads((self.library() / gba_conversion.ENGINE_REV / 'paths.json').read_text(encoding='utf-8')))
        self.assertEqual((stored.roots, stored.spans), ({0x101}, set()))             # the player's paths hold none of the received rows
        promoted = gk.library_record(self.sha)
        self.assertEqual(gk.rows(promoted), ([0x101], []))                           # neither does the record this conversion shares
        report = self.report()
        shared = report['native_coverage']['shared_paths']
        self.assertEqual((shared['used_roots'], shared['used_ram_copies'], shared['pending'], shared['qualified_by_the_base'], shared['qualified_by_this_converter']),
                         (2, 1, 3, 0, 0))
        self.assertEqual((shared['left_out_by_the_cap'], shared['pending_root_cap']), ({'roots': 0, 'ram_copies': 0}, 16384))
        self.assertEqual((shared['reached_by_own_misses'], shared['not_proven']), (0, 3))
        self.assertEqual((report['native_coverage']['built_rom_roots'], report['native_coverage']['rom_roots']), (3, 1))
        self.assertNotIn('received_rows_never_in_the_record', report['knowledge'])      # a received row a conversion reaches by its own misses is the player's own

    def test_a_row_only_the_last_pass_learned_was_never_built_and_is_not_shared(self):
        total = 2 + gba_conversion.SETTLING_PASSES                                   # a game that teaches something at every pass runs them all
        self.misses = {n: f'[[extra_func]]\naddr = 0x{0x08000000 + 0x100 * n:08X}\nmode = "thumb"\n' for n in range(1, total + 1)}
        self.convert()
        self.assertEqual(len(self.configs), total)
        stored = analysis.observations_of(json.loads((self.library() / gba_conversion.ENGINE_REV / 'paths.json').read_text(encoding='utf-8')))
        self.assertEqual(stored.roots, {0x100 * n | 1 for n in range(1, total + 1)})   # the player's own store keeps all of them, as before
        self.assertEqual(gk.rows(gk.library_record(self.sha)), ([0x100 * n | 1 for n in range(1, total)], []))   # the shared record: what a build of this conversion held

    def test_a_conversion_that_differs_from_the_interpreter_raises_and_shares_nothing(self):
        self.receive()
        self.reference_differs = True
        with self.assertRaises(ConversionError) as caught:
            self.convert()
        self.assertIn('interpreter', str(caught.exception))
        self.assertIsNone(gk.library_record(self.sha))
        self.assertFalse((self.library() / 'compilation.json').exists())

    def test_the_received_roots_are_capped_and_counted(self):
        self.receive(roots=[value * 4 for value in range(64, 84)], spans=())
        with mock.patch.object(gk, 'PENDING_ROOT_CAP', 5):
            self.convert()
        shared = self.report()['native_coverage']['shared_paths']
        self.assertEqual((shared['used_roots'], shared['left_out_by_the_cap']['roots'], shared['pending_root_cap']), (5, 15, 5))
        self.assertEqual(self.configs[0].count('observed by Retro-Recomp'), 5)


if __name__ == '__main__':
    unittest.main()
