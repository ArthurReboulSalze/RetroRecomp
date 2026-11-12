"""Stage 3 of the Game Boy Advance profile, without the engine and without a ROM: the pieces of the conversion loop.

The cartridge and the RAM image are authored here as bytes with no meaning; nothing is downloaded, built or run.
"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from retrorecomp import gba, gba_analysis as analysis, gba_build as build, gba_conversion, gba_engine as engine, \
    path_profiles, report_schema
from retrorecomp.core import ConversionError
from tests.test_gba_profile import synthetic_cartridge


def pseudo_random(length: int, seed: int) -> bytes:
    """Bytes with no repeated stretch (a linear congruential stream)."""
    value, out = seed, bytearray()
    for _ in range(length):
        value = (value * 1103515245 + 12345) & 0x7fffffff
        out.append(value >> 16 & 0xff)
    return bytes(out)


def seen_bytes(count, seed):
    return pseudo_random(count, seed)


class AnalysisTests(unittest.TestCase):
    def test_a_miss_proposal_is_read(self):
        text = ('# header\n[[extra_func]]\naddr = 0x030015D8\nmode = "arm"\n'
                'note = "proposed from self-heal miss-log; bridged x3606"\n\n'
                '[[extra_func]]\naddr = 0x08000578\nmode = "thumb"\nnote = "proposed; bridged x319 near gf_tfunc_08000568"\n'
                '[[extra_func]]\naddr = 0x08002168\nmode = "thumb"\n')
        self.assertEqual(analysis.parse_misses(text), [analysis.Miss(0x030015D8, False, 3606),
                                                       analysis.Miss(0x08000578, True, 319),
                                                       analysis.Miss(0x08002168, True, 0)])

    def test_the_cartridge_bytes_a_ram_image_came_from_are_found(self):
        rom = bytearray(pseudo_random(0x4000, 1))
        live = bytearray(pseudo_random(0x1000, 99))            # IWRAM: other data
        live[0x200:0x300] = rom[0x1230:0x1330]                 # a routine copied from the cartridge
        start, source, length = analysis.find_source(bytes(rom), bytes(live), analysis.IWRAM[0], 0x240)
        self.assertEqual((start, source), (0x200, 0x1230))
        self.assertGreaterEqual(length, 0x100)
        self.assertEqual(live[start:start + length], rom[source:source + length])

    def test_a_stretch_the_cartridge_holds_twice_is_one_source_and_unknown_bytes_are_left_to_the_interpreter(self):
        rom = bytearray(pseudo_random(0x2000, 7))
        rom[0x1000:0x1100] = rom[0x100:0x200]                  # the same code twice: whichever copy the game read
        live = bytearray(pseudo_random(0x400, 5))
        live[0x40:0x140] = rom[0x100:0x200]
        start, source, length = analysis.find_source(bytes(rom), bytes(live), analysis.IWRAM[0], 0x80)
        self.assertEqual((start, source), (0x40, 0x100))       # the lowest address of equal copies
        self.assertEqual(live[start:start + length], rom[source:source + length])
        for copy in range(5):                                  # more copies than are read as one source: ambiguous
            rom[0x1200 + copy * 0x100:0x1300 + copy * 0x100] = rom[0x100:0x200]
        self.assertIsNone(analysis.find_source(bytes(rom), bytes(live), analysis.IWRAM[0], 0x80))
        live[0x40:0x140] = pseudo_random(0x100, 31)            # written at run time
        self.assertIsNone(analysis.find_source(bytes(rom), bytes(live), analysis.IWRAM[0], 0x80))
        self.assertIsNone(analysis.find_source(bytes(rom), bytes(0x400), analysis.IWRAM[0], 0x80))

    def test_misses_become_roots_and_ram_routines(self):
        rom = bytearray(pseudo_random(0x6000, 3))
        iwram = bytearray(0x8000)
        iwram[0x1518:0x1600] = rom[0x4A00:0x4AE8]
        misses = [analysis.Miss(0x08000578, True), analysis.Miss(0x08001000, False),
                  analysis.Miss(0x03001518, False), analysis.Miss(0x02001000, True), analysis.Miss(0x03007000, False)]
        learned, left = analysis.observations_from_misses(misses, bytes(rom), bytes(iwram))
        self.assertEqual(learned.roots, {0x578 | 1, 0x1000})
        self.assertEqual(learned.spans, {(0x03001518, 0x4A00, 0xE8)})
        self.assertEqual([item.address for item in left], [0x02001000, 0x03007000])   # EWRAM, and zeros

    def test_a_routine_copied_to_work_ram_is_found_in_either_ram_and_by_the_bytes_seen_at_the_miss(self):
        rom = bytearray(pseudo_random(0x6000, 3))
        ewram = bytearray(0x40000)
        ewram[0x8000:0x8100] = rom[0x2000:0x2100]                        # an overlay stored uncompressed
        iwram = bytearray(0x8000)                                        # the IWRAM at the end of the run: another routine took the place
        iwram[0x100:0x200] = pseudo_random(0x100, 77)
        seen = pseudo_random(0x100, 5)
        rom[0x3000:0x3100] = seen                                        # the routine that stood at 0x03000100 when it was first reached
        samples = ((0x03000100, seen),)
        misses = [analysis.Miss(0x02008020, True), analysis.Miss(0x03000100, False), analysis.Miss(0x02010000, True)]
        learned, left = analysis.observations_from_misses(misses, bytes(rom), bytes(iwram), bytes(ewram), samples)
        self.assertEqual(learned.spans, {(0x02008020 | 1, 0x2020, 0xE0), (0x03000100, 0x3000, 0x100)})
        self.assertEqual([item.address for item in left], [0x02010000])
        self.assertEqual(analysis.why_unresolved(misses[0], bytes(rom), bytes(iwram), bytes(ewram)), 'copy')
        self.assertEqual(analysis.why_unresolved(misses[1], bytes(rom), bytes(iwram), bytes(ewram), samples), 'copy')
        self.assertEqual(analysis.why_unresolved(misses[1], bytes(rom), bytes(iwram), bytes(ewram)), 'no copy')
        self.assertEqual(analysis.why_unresolved(misses[2], bytes(rom), bytes(iwram), bytes(ewram)), 'zero')
        self.assertEqual(analysis.why_unresolved(misses[0], bytes(rom), bytes(iwram), None), 'no dump')
        self.assertEqual(analysis.why_unresolved(analysis.Miss(0x04000000, False), bytes(rom), None, None), 'not in the cartridge or work RAM')
        ewram[0x8000:0x8100] = pseudo_random(0x100, 11)                  # made at run time: no source
        self.assertEqual(analysis.why_unresolved(misses[0], bytes(rom), bytes(iwram), bytes(ewram)), 'no copy')

    def test_the_configuration_carries_identity_roots_and_copies(self):
        seen = analysis.Observations(roots={0x578 | 1, 0x1000}, spans={(0x03001518 | 1, 0x4A00, 0xE8)})
        text = analysis.config_text('Authored', 'ab' * 20, 0x400000, seen)
        for line in ('size = 0x00400000', 'sha1 = "' + 'ab' * 20 + '"', 'runtime_start = 0x03001518',
                     'source_start = 0x08004A00', 'size = 0xE8', 'addr = 0x08000578', 'mode = "thumb"',
                     'addr = 0x08001000', 'mode = "arm"', 'source_addr = 0x08004A00'):
            self.assertIn(line, text)
        self.assertEqual(text.count('[[code_copy]]'), 1)
        self.assertEqual(text.count('[[extra_func]]'), 3)

    def test_adjacent_stretches_with_one_bias_are_one_copy(self):
        spans = {(0x03000100, 0x1100, 0x40), (0x03000140, 0x1140, 0x20), (0x03000200, 0x1500, 0x20)}
        self.assertEqual(analysis._copies(spans), [(0x03000100, 0x1100, 0x60), (0x03000200, 0x1500, 0x20)])

    def test_the_paths_record_is_validated_and_round_trips(self):
        seen = analysis.Observations(roots={0x578 | 1, 0x1000}, spans={(0x03001518 | 1, 0x4A00, 0xE8)})
        document = analysis.record('cd' * 32, 0x400000, 'e' * 40, seen)
        again = analysis.observations_of(document)
        self.assertEqual((again.roots, again.spans), (seen.roots, seen.spans))
        document['identity']['sources']['rom']['bytes'] = 0x100        # smaller than the span: refused
        with self.assertRaises(ValueError):
            path_profiles.validate_game(document)

    def test_code_the_cartridge_does_not_hold_becomes_ram_code_in_memory_only(self):
        rom = pseudo_random(0x6000, 3)
        seen = pseudo_random(0x400, 21)                                     # made at run time: no copy in the cartridge
        other = pseudo_random(0x400, 22)
        samples = ((0x02008030, seen), (0x02008030, other), (0x02008030, seen), (0x02008200, seen[0x1D0:]),
                   (0x03000828, bytes(0x400)), (0x03000900, b'\x01\x02'))
        ram_code = analysis.RamCode()
        misses = [analysis.Miss(0x02008031, True), analysis.Miss(0x02008200, True), analysis.Miss(0x03000828, False),
                  analysis.Miss(0x03000900, False), analysis.Miss(0x04000000, False)]
        added = [ram_code.take(item, samples) for item in misses]
        self.assertEqual(added, [2, 1, 0, 0, 0])                           # two versions at the first address; zeros, a stub and an I/O address are not code
        self.assertTrue(ram_code.has(0x02008030, True))
        self.assertFalse(ram_code.has(0x02008030, False))
        self.assertEqual(ram_code.take(misses[0], samples), 0)             # nothing new the second time
        image, entries, ranges = analysis.generator_image(rom, ram_code)
        self.assertEqual(ranges, [])
        self.assertEqual(image[:len(rom)], rom)
        self.assertEqual(len(entries), 3)
        for entry in entries:
            source = entry.source - analysis.ROM_BASE
            self.assertEqual(source % 4, entry.address % 4)                # the literal-pool alignment is kept
        by_address = {(entry.address, entry.thumb): [] for entry in entries}
        for entry in entries:
            by_address[(entry.address, entry.thumb)].append(entry)
        first, second = by_address[(0x02008030, True)]
        self.assertEqual(image[first.source - analysis.ROM_BASE:][:0x400], seen)
        self.assertEqual(image[second.source - analysis.ROM_BASE:][:0x400], other)
        inside = by_address[(0x02008200, True)][0]                          # the same bytes as a block already placed: read from it
        self.assertEqual(inside.source, first.source + 0x1D0)
        self.assertLess(len(image), len(rom) + 0x4000 + 0x1000)
        text = analysis.config_text('Authored', 'ab' * 20, len(image), analysis.Observations(), entries)
        self.assertIn('size = 0x%08X' % len(image), text)
        self.assertEqual(text.count('[[extra_func]]'), 3)
        self.assertEqual(text.count('source_addr = 0x'), 3)
        self.assertIn('addr = 0x02008030', text)
        self.assertIn('addr = 0x02048030', text)                            # the second version is named at the mirror of the address
        self.assertIn('mode = "thumb"', text)
        # nothing of it reaches the paths: the record keeps numbers about the cartridge only
        document = analysis.record('cd' * 32, len(rom), 'e' * 40, analysis.Observations(roots={1}))
        self.assertNotIn(seen.hex(), str(document))
        # no RAM code: the generator reads the cartridge itself; an image that would not fit the cartridge window is not built
        self.assertEqual(analysis.generator_image(rom, analysis.RamCode()), (rom, [], []))
        self.assertEqual(analysis.generator_image(bytes(analysis.IMAGE_MAX - 0x100), ram_code), (bytes(analysis.IMAGE_MAX - 0x100), [], []))

    def test_a_routine_that_keeps_its_arguments_in_its_literal_pool_is_one_version_with_declared_parameter_words(self):
        base = pseudo_random(0x100, 31)
        shape_b = bytearray(base)
        shape_b[0:4] = bytes([0xAA, 0xBB, 0xCC, 0xDD])                      # a second code shape
        versions = []
        for call in range(40):                                              # the caller writes two words at offsets 0x40 and 0x44 at every call
            for shape in (base, bytes(shape_b)):
                live = bytearray(shape)
                live[0x40:0x48] = (0x1000 + call).to_bytes(4, 'little') + (0x08000000 + 7 * call).to_bytes(4, 'little')
                versions.append(bytes(live))
        address = 0x03000828
        self.assertEqual(analysis.parameter_words(address, versions), [0x40, 0x44])
        self.assertEqual(analysis.parameter_words(address, versions[:5]), [])           # too few versions to tell code from arguments
        representatives, words = analysis.shapes(address, versions)
        self.assertEqual((len(representatives), words), (2, [0x40, 0x44]))
        ram_code = analysis.RamCode(variants={(address, 0): versions})
        image, entries, ranges = analysis.generator_image(bytes(0x1000), ram_code)
        self.assertEqual(len(entries), 2)
        self.assertEqual(len(ranges), 4)                                                 # two words in each of the two placed shapes
        first = entries[0].source
        self.assertIn((first + 0x40, first + 0x44), ranges)
        text = analysis.config_text('Authored', 'ab' * 20, len(image), analysis.Observations(), entries, ranges)
        self.assertEqual(text.count('[[data_range]]'), 4)
        self.assertEqual(text.count('note = "RAM parameter word"'), 4)

    def test_the_versions_of_one_routine_are_known_at_the_mirrors_of_its_address(self):
        self.assertEqual([analysis.mirror_address(0x03000828, number) for number in (0, 1, 2)], [0x03000828, 0x03008828, 0x03010828])
        self.assertEqual([analysis.mirror_address(0x02008031, number) for number in (0, 1)], [0x02008031, 0x02048031])
        self.assertIsNone(analysis.mirror_address(0x03000828, 512))
        self.assertIsNone(analysis.mirror_address(0x02008030, 64))
        self.assertIsNone(analysis.mirror_address(0x08000000, 0))

    def test_copies_of_one_address_from_different_cartridge_offsets_are_versions_at_mirrors(self):
        spans = {(0x03002000, 0x1000, 0x40), (0x03002000, 0x1000, 0x9C), (0x03002000, 0x2400, 0x80), (0x03002001 + 0x100, 0x3000, 0x20)}
        rows, counts = analysis._versions(spans)
        self.assertEqual(rows, [(0x03002000, 0x1000, 0x9C), (0x0300A000, 0x2400, 0x80), (0x03002101, 0x3000, 0x20)])
        self.assertEqual(counts, {(0x03002000, 0): 2, (0x03002100, 1): 1})
        text = analysis.config_text('Authored', 'ab' * 20, 0x400000, analysis.Observations(spans=spans))
        self.assertEqual(text.count('[[extra_func]]'), 3)
        self.assertIn('addr = 0x0300A000', text)
        self.assertIn('source_addr = 0x08002400', text)
        # a version made at run time takes the next mirror after the ones from the cartridge
        entry = analysis.RamEntry(0x03002000, False, analysis.ROM_BASE + 0x500000)
        self.assertIn('addr = 0x03012000', analysis.config_text('Authored', 'ab' * 20, 0x600000, analysis.Observations(spans=spans), [entry]))

    def test_the_caps_are_counted_not_silent(self):
        ram_code = analysis.RamCode()
        miss = analysis.Miss(0x02008030, True)
        samples = tuple((0x02008030, seen_bytes(0x100, 1000 + index)) for index in range(analysis.MAX_VARIANTS + 5))
        self.assertEqual(ram_code.take(miss, samples), analysis.MAX_VARIANTS)
        self.assertEqual(ram_code.refused, 5)                                   # versions beyond the cap are counted
        entry = analysis.RamEntry(0x03002000, False, analysis.ROM_BASE + 0x500000)
        stats = {}
        analysis.config_text('Authored', 'ab' * 20, 0x600000, analysis.Observations(spans={(0x03002000, number * 0x100, 0x40) for number in range(600)}),
                             [entry], (), stats)
        self.assertEqual(stats, {'versions_without_mirror': 1})                 # 600 cartridge versions fill the 512 mirrors of the IWRAM
        big = analysis.RamCode(variants={(0x02008030, 0): [seen_bytes(0x400, 1)]})
        self.assertEqual(analysis.generator_image(bytes(analysis.IMAGE_MAX - 0x100), big)[1], [])
        self.assertTrue(big.image_overflow)
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / 'miss-bytes.txt'
        path.write_text('03000828 ' + '00' * 8 + chr(10) + 'CAPPED 03000828 256' + chr(10) + 'CAPPED zz 1' + chr(10), encoding='ascii')
        self.assertEqual(build._capped(path), ((0x03000828, 256),))
        self.assertEqual(len(build._samples(path)), 1)                          # the CAPPED line is not a sample

    def test_merging_counts_what_is_new(self):
        known = analysis.Observations(roots={1, 2})
        self.assertEqual(known.merge(analysis.Observations(roots={2, 3}, spans={(0x03000000, 0, 4)})), 2)
        self.assertEqual(known.size(), 4)


class StagingTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.engine = self.root / 'engine'
        (self.engine / 'src').mkdir(parents=True)
        (self.engine / 'docs').mkdir()
        (self.engine / '.git').mkdir()
        (self.engine / 'src/a.cpp').write_text('int a() { return 1; }\nint b() { return 2; }\n', encoding='utf-8')
        (self.engine / 'src/b.cpp').write_text('int c() { return 3; }\n', encoding='utf-8')
        (self.engine / 'docs/x.md').write_text('notes', encoding='utf-8')
        (self.engine / '.git/HEAD').write_text('ref', encoding='utf-8')
        self.patches = (('src/a.cpp', 'return 1;', 'return 10;', 'one to ten'),
                        ('src/a.cpp', 'return 2;', 'return 20;', 'two to twenty'))

    def test_the_copy_is_patched_skips_what_a_build_never_reads_and_is_stable(self):
        target, notes = engine.stage(self.root / 'stage', self.engine, self.patches)
        self.assertEqual((target / 'src/a.cpp').read_text(encoding='utf-8'),
                         'int a() { return 10; }\nint b() { return 20; }\n')
        self.assertEqual(notes, ['one to ten', 'two to twenty'])
        self.assertFalse((target / 'docs').exists() or (target / '.git').exists())
        before = {path: path.stat().st_mtime_ns for path in target.rglob('*') if path.is_file()}
        engine.stage(self.root / 'stage', self.engine, self.patches)
        self.assertEqual(before, {path: path.stat().st_mtime_ns for path in target.rglob('*') if path.is_file()})

    def test_a_windows_checkout_with_crlf_stages_the_same_bytes_as_a_linux_one(self):
        (self.engine / 'src/a.cpp').write_bytes(b'int a() { return 1; }\r\nint b() { return 2; }\r\n')
        (self.engine / 'src/c.png').write_bytes(b'\x89PNG\r\n\x1a\n')
        target, _ = engine.stage(self.root / 'stage', self.engine, self.patches)
        self.assertEqual((target / 'src/a.cpp').read_bytes(), b'int a() { return 10; }\nint b() { return 20; }\n')
        self.assertFalse((target / 'src/c.png').exists())

    def test_an_engine_whose_text_moved_is_refused(self):
        for patches in ((('src/a.cpp', 'return 99;', 'x', 'moved'),),                    # absent
                        (('src/a.cpp', 'int', 'long', 'twice'),),                             # not unique
                        (('src/missing.cpp', 'a', 'b', 'file'),)):                            # no such file
            with self.subTest(patches[0][3]), self.assertRaises(ConversionError):
                engine.stage(self.root / 'stage2', self.engine, patches)

    def test_the_digest_names_the_patch_set(self):
        self.assertEqual(engine.patch_digest(self.patches), engine.patch_digest(list(self.patches)))
        self.assertNotEqual(engine.patch_digest(self.patches), engine.patch_digest(self.patches[:1]))
        self.assertEqual(len(engine.patch_digest(())), 64)

    def test_the_shipped_patches_are_well_formed(self):
        from retrorecomp import gba_patches
        self.assertGreaterEqual(len(gba_patches.PATCHES), 1)
        for file, old, new, note in gba_patches.PATCHES:
            self.assertTrue(file and old and old != new and note, note)
            self.assertNotIn('\r', old + new, note)                     # the staged copy is LF

    def test_every_shipped_anchor_is_found_once_in_the_pinned_engine_when_it_is_cached(self):
        from retrorecomp import gba_patches
        from retrorecomp.paths import ROOT
        cached = ROOT / '.deps' / 'gbarecomp'
        if not (cached / 'CMakeLists.txt').is_file():
            self.skipTest('the pinned engine is not cached on this machine')
        with tempfile.TemporaryDirectory() as folder:
            _, notes = engine.stage(Path(folder), cached, gba_patches.PATCHES)
        self.assertEqual(len(notes), len(gba_patches.PATCHES))


class BuildTests(unittest.TestCase):
    def test_the_scripts_are_deterministic_and_in_the_engines_format(self):
        boot, generic = build.input_script(600, 'boot'), build.input_script(3600, 'generic')
        self.assertEqual(boot, '# frame,keyinput_active_low\n0,0x03ff\n')
        self.assertEqual(generic, build.input_script(3600, 'generic'))
        frames = [int(line.split(',')[0]) for line in generic.splitlines()[1:]]
        self.assertEqual(frames, sorted(frames))
        self.assertTrue(all(line.split(',')[1].startswith('0x') for line in generic.splitlines()[1:]))
        self.assertIn(',0x03fe', generic)                                   # A alone is pressed at frame 0

    def test_the_host_project_is_written_once_and_names_the_game_and_the_bios(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder) / 'game'
            host = build.host_project(project, Path(folder) / 'stage', Path(folder) / 'generated', Path(folder) / 'bios')
            text = (host / 'CMakeLists.txt').read_text(encoding='utf-8')
            self.assertIn((Path(folder) / 'stage/engine').as_posix(), text)
            self.assertIn((Path(folder) / 'generated').as_posix(), text)
            self.assertIn((Path(folder) / 'bios').as_posix(), text)
            self.assertIn('run_game', (host / 'main.cpp').read_text(encoding='utf-8'))
            stamp = (host / 'CMakeLists.txt').stat().st_mtime_ns
            build.host_project(project, Path(folder) / 'stage', Path(folder) / 'generated', Path(folder) / 'bios')
            self.assertEqual(stamp, (host / 'CMakeLists.txt').stat().st_mtime_ns)

    def test_a_scenario_collects_what_the_host_reports(self):
        class Done:
            returncode, stdout = 3, 'runtime_arm: generated call-return stack overflow at return_pc=0x0805FB7A\n' \
                                    'final_pc=0x08000532 cycles=62191750 ppu_vcount=211\n' \
                                    'vblank_snapshot frame=600 cycles=168538800 mem=00112233445566ff cpu=aabbccdd00112233\n'

        def fake_spawn(command, **options):
            work = Path(options['cwd'])
            (work / 'coverage.json').write_text('{"coverage": "NOT_STATIC", "interpreted_insns": 12, "distinct_misses": 2}',
                                                encoding='utf-8')
            (work / 'miss.toml.frag').write_text('[[extra_func]]\naddr = 0x08000578\nmode = "thumb"\n', encoding='utf-8')
            (work / 'iwram.bin').write_bytes(bytes(32))
            (work / 'frame.png').write_bytes(b'png')
            forced.append('GBARECOMP_FORCE_INTERP' in options['env'])
            return Done()
        forced = []
        with tempfile.TemporaryDirectory() as folder, patch.object(build, 'spawn', fake_spawn):
            outcome = build.run_scenario(Path('host.exe'), Path('rom.gba'), 'ab' * 20, Path('bios.bin'), Path(folder),
                                         'generic', 600, Path('script.txt'))
            reference = build.run_scenario(Path('host.exe'), Path('rom.gba'), 'ab' * 20, Path('bios.bin'), Path(folder),
                                           'generic', 600, Path('script.txt'), reference=True)
        self.assertEqual((outcome.returncode, outcome.cycles, outcome.coverage['interpreted_insns']), (3, 168538800, 12))        # the snapshot's cycles, not the idle counter of the final line
        self.assertEqual((outcome.mem_hash, outcome.cpu_hash), ('00112233445566ff', 'aabbccdd00112233'))
        self.assertIn('overflow', outcome.aborted)
        self.assertEqual(len(outcome.frame_sha256), 64)
        self.assertEqual(len(outcome.iwram), 32)
        self.assertTrue(analysis.parse_misses(outcome.misses))
        self.assertIsNot(outcome, reference)
        self.assertEqual(forced, [False, True])           # only the reference run asks for the engine's interpreter alone


class ConversionTests(unittest.TestCase):
    def test_the_agreement_of_a_run_with_the_engines_interpreter(self):
        make = lambda sha, cycles, code=0, mem='m', cpu='c': build.Run('s', 10, code, '', {}, '', None, '', sha, cycles, mem, cpu)
        self.assertTrue(gba_conversion._matches(make('a', 5), make('a', 5)))
        self.assertFalse(gba_conversion._matches(make('a', 5), make('b', 5)))
        self.assertTrue(gba_conversion._matches(make('a', 5), make('a', 6)))
        self.assertFalse(gba_conversion._matches(make('a', 5), make('a', 5 + gba_conversion.CYCLE_TOLERANCE + 1)))
        self.assertFalse(gba_conversion._matches(make('a', 5), make('a', 5, mem='other')))       # the memories differ
        self.assertFalse(gba_conversion._matches(make('a', 5), make('a', 5, cpu='other')))       # the CPU registers differ
        self.assertFalse(gba_conversion._matches(make('a', 5, mem=''), make('a', 5, mem='')))    # no snapshot: no agreement claimed
        self.assertIsNone(gba_conversion._matches(make('a', 5), None))
        self.assertIsNone(gba_conversion._matches(make('a', 5, 3), make('a', 5)))
        self.assertIsNone(gba_conversion._matches(make('', None), make('', None, 1)))

    def test_a_conversion_whose_native_run_failed_or_differs_is_refused(self):
        make = lambda code=0, aborted='': build.Run('s', 10, code, '', {}, '', None, aborted, 'sha', 1, 'm', 'c')
        row = lambda name, match: {'scenario': name, 'reference_match': match}
        good = {'boot': make(), 'generic': make()}
        self.assertEqual(gba_conversion.validation_failures([row('boot', True), row('generic', True)], good), [])
        failures = gba_conversion.validation_failures([row('boot', True), row('generic', False)], good)
        self.assertEqual(len(failures), 1)
        self.assertIn('generic', failures[0])
        self.assertIn('different states', failures[0])
        broken = {'boot': make(3, 'bridge stopped'), 'generic': make()}                       # an errored native run used to be left out of the verdict
        failures = gba_conversion.validation_failures([row('boot', None), row('generic', True)], broken)
        self.assertEqual(len(failures), 1)
        self.assertIn('exit code 3', failures[0])
        self.assertIn('bridge stopped', failures[0])
        failures = gba_conversion.validation_failures([row('boot', None), row('generic', None)], good)
        self.assertEqual(len(failures), 2)                                                      # nothing compared is not a pass either

    def test_a_report_with_measured_rows_goes_through_the_common_builder(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'Authored.gba'
            path.write_bytes(synthetic_cartridge(save=b'FLASH_V126'))
            source = gba.read_rom(path)
            rows = [gba_conversion._row('boot', 600, None, 0, coverage='FULLY_STATIC', distinct_misses=0),
                    gba_conversion._row('generic', 3600, None, 4173616, coverage='NOT_STATIC', distinct_misses=10,
                                        aborted='generated call-return stack overflow')]
            rows[0]['reference_match'] = True
            document = gba_conversion.report_of(source, 'standard', rows,
                                                validation={'passed': None, 'scope': 'unit test',
                                                            'cpu_fidelity_validated': False, 'independent_cpu_oracle': False},
                                                coverage={'observed_entries': 3},
                                                compiler={'revision': gba_conversion.ENGINE_REV})
            report_schema.write_report(Path(folder) / 'r.json', document)
            report = report_schema.read_report(Path(folder) / 'r.json')
        scenarios = report['cpus'][0]['scenarios']
        self.assertEqual([row['interpreted'] for row in scenarios], [0, 4173616])
        self.assertIsNone(scenarios[0]['interpreted_percent'])            # no native count: none invented
        self.assertFalse(report['validation']['hardware_fidelity']['validated'])
        self.assertFalse(report['validation']['gameplay']['validated'])
        self.assertEqual(report_schema.fallback_summary(report)['main_interpreted_opcodes'], 4173616)

    def test_a_conversion_needs_the_players_own_bios(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'Authored.gba'
            path.write_bytes(synthetic_cartridge())
            with self.assertRaises(ConversionError) as caught:
                gba_conversion.convert(path, gba_bios=str(Path(folder) / 'none.bin'), emit=lambda text: None)
            self.assertIn('BIOS', str(caught.exception))
            stranger = Path(folder) / 'gba_bios.bin'
            stranger.write_bytes(bytes(gba.BIOS_BYTES))
            with self.assertRaises(ConversionError) as caught:
                gba_conversion.convert(path, gba_bios=str(stranger), emit=lambda text: None)
            self.assertIn('not the 16 KiB image', str(caught.exception))

    def test_the_pins_are_the_ones_the_engine_records(self):
        self.assertEqual(len({gba_conversion.ENGINE_REV, gba_conversion.ARM_CORE_REV, gba_conversion.NET_REV,
                              gba_conversion.RBENGINE_REV}), 4)
        self.assertEqual([path for path, _ in engine.SUBMODULES],
                         ['external/arm-recomp-core', 'external/recomp-net', 'external/rbengine'])


if __name__ == '__main__':
    unittest.main()
