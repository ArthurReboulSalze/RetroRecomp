"""The ROM-free, MAME-free parts of tools/pce_mame_compare.py: authored pictures, signals and cards only."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import wave

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('pce_mame_compare', ROOT / 'tools' / 'pce_mame_compare.py')
compare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compare)

try:
    import numpy
except ImportError:                                        # the comparison itself needs it
    numpy = None


def authored(width, height, seed):
    """A picture of the game (height, width, 3) of authored levels, written with the game's table of the 8 levels of a channel."""
    levels = numpy.random.default_rng(seed + 1000).integers(0, 8, (height, width, 3))
    return levels, numpy.array(compare.LEVELS['game'], dtype=numpy.uint8)[levels]


def mame_frame(levels, dots, left, top, border=(0, 0, 0)):
    """The same picture as MAME writes it: its own table of levels, each pixel `dots` dots wide, inside a border, in 1088 x 242."""
    table = numpy.array(compare.LEVELS['mame'], dtype=numpy.uint8)
    frame = numpy.empty((compare.MAME_HEIGHT, compare.MAME_WIDTH, 3), dtype=numpy.uint8)
    frame[:] = border
    height, width = levels.shape[:2]
    wide = numpy.repeat(table[levels], dots, axis=1)
    first, last = max(0, -top), min(height, compare.MAME_HEIGHT - top)
    frame[first + top:last + top, left:left + dots * width] = wide[first:last]
    return frame


def bgra(rgb):
    """The raw bytes MAME's `screen:pixels()` gives for an RGB frame."""
    out = numpy.empty(rgb.shape[:2] + (4,), dtype=numpy.uint8)
    out[..., 0], out[..., 1], out[..., 2], out[..., 3] = rgb[..., 2], rgb[..., 1], rgb[..., 0], 255
    return out.tobytes()


@unittest.skipIf(numpy is None, 'numpy is needed')
class LevelTests(unittest.TestCase):
    def test_each_side_maps_its_own_values_to_the_same_eight_levels(self):
        for name in ('mame', 'game'):
            table = compare.level_table(name)
            self.assertEqual([int(table[v]) for v in compare.LEVELS[name]], list(range(8)))

    def test_the_two_tables_that_differ_by_one_are_the_same_level(self):
        game, mame = compare.level_table('game'), compare.level_table('mame')
        for ours, theirs in zip(compare.LEVELS['game'], compare.LEVELS['mame']):
            self.assertEqual(game[ours], mame[theirs])
        self.assertNotEqual(compare.LEVELS['game'], compare.LEVELS['mame'])


@unittest.skipIf(numpy is None, 'numpy is needed')
class GeometryTests(unittest.TestCase):
    def test_a_256_pixel_picture_is_found_at_four_dots_a_pixel_with_the_top_rows_cut_off(self):
        levels, game = authored(256, 40, 1)
        mame = compare.mame_rgb(bgra(mame_frame(levels, 4, 32, -2)))
        found, share = compare.find_geometry(game, mame)
        self.assertEqual(found, compare.Geometry(4, 32, -2))
        self.assertEqual(share, 1.0)
        result = compare.measure(game, mame, found)
        self.assertEqual((result['equal'], result['pixels'], result['hidden_rows']), (38 * 256, 38 * 256, 2))
        self.assertEqual(result['rows'], (2, 40))
        self.assertTrue(0 < result['exact'] < result['pixels'])      # the tables differ at 3 levels of 8: levels are equal, 24-bit colours are not

    def test_the_other_dot_clocks_and_a_picture_placed_lower_are_found(self):
        for width, height, dots, left, top in ((352, 24, 3, 20, 7), (512, 24, 2, 33, -2), (320, 16, 3, 61, 3), (256, 24, 3, 9, 4)):
            levels, game = authored(width, height, width)
            mame = compare.mame_rgb(bgra(mame_frame(levels, dots, left, top)))
            found = compare.find_geometry(game, mame)
            self.assertEqual(found[0], compare.Geometry(dots, left, top), (width, height))

    def test_a_picture_of_one_colour_cannot_be_placed_and_a_different_picture_is_not_found(self):
        mame = compare.mame_rgb(bgra(mame_frame(authored(64, 40, 2)[0], 4, 32, -2)))
        self.assertIsNone(compare.find_geometry(numpy.full((40, 64, 3), 72, dtype=numpy.uint8), mame))
        self.assertIsNone(compare.find_geometry(authored(64, 40, 3)[1], mame))

    def test_a_geometry_that_does_not_hold_the_picture_measures_nothing(self):
        _, game = authored(256, 40, 4)
        mame = compare.mame_rgb(bgra(mame_frame(authored(256, 40, 4)[0], 4, 32, -2)))
        self.assertIsNone(compare.measure(game, mame, compare.Geometry(4, 900, -2)))
        self.assertIsNone(compare.measure(game, mame, compare.Geometry(5, 0, 0)))
        self.assertIsNone(compare.measure(game, mame, compare.Geometry(4, 32, 600)))

    def test_a_column_that_cuts_the_groups_of_dots_in_two_is_not_chosen(self):
        levels, game = authored(256, 40, 5)
        mame = compare.mame_rgb(bgra(mame_frame(levels, 4, 32, -2)))
        theirs = compare.MAME_LUT[mame]
        rows = (2, 40)
        self.assertEqual(compare.grouped(theirs, compare.Geometry(4, 32, -2), 256, rows, -2), 1.0)
        self.assertLess(compare.grouped(theirs, compare.Geometry(4, 33, -2), 256, rows, -2), 0.5)


def scene(n):
    """The authored picture of frame n: a scene stands for 8 frames, then changes (as a title or a menu does)."""
    return authored(64, 40, n // 8)


@unittest.skipIf(numpy is None, 'numpy is needed')
class VerdictTests(unittest.TestCase):
    FRAMES = 40

    def run_comparison(self, shift=0, alter=None):
        """A run of authored pictures: MAME frame f shows the picture of game frame f + shift; `alter(frame, mame)` may change a frame."""
        game = {n: scene(n)[1] for n in range(1, self.FRAMES + 8)}
        mame = {}
        for f in range(1, self.FRAMES + 1):
            frame = mame_frame(scene(f + shift)[0], 4, 32, -2)
            mame[f] = alter(f, frame) if alter else frame
        comparer = compare.Comparer(game.get, mame.get, self.FRAMES, self.FRAMES + 7)
        return comparer, comparer.choose_offset(), [comparer.verdict(f) for f in range(1, self.FRAMES + 1)]

    def test_equal_pictures_at_the_offset_the_sample_finds(self):
        for shift in (0, 1, -1):
            comparer, calibration, verdicts = self.run_comparison(shift)
            self.assertEqual(calibration['offset'], shift, shift)
            self.assertEqual({item['status'] for item in verdicts if item['frame'] > 8}, {'equal'})
            self.assertEqual(comparer.geometries, {(64, 40): compare.Geometry(4, 32, -2)})

    def test_a_picture_that_scrolls_a_row_a_frame_is_placed_at_the_right_offset_and_row(self):
        # At offset 0 this picture also fits one row away, on nearly all its pixels: the place and the offset must be chosen together.
        base = numpy.random.default_rng(7).integers(0, 8, (200, 64, 3))
        table = numpy.array(compare.LEVELS['game'], dtype=numpy.uint8)
        levels = {n: numpy.roll(base, n, axis=0) for n in range(1, self.FRAMES + 8)}
        game = {n: table[picture] for n, picture in levels.items()}
        mame = {f: mame_frame(levels[f + 1], 4, 32, -2) for f in range(1, self.FRAMES + 1)}
        comparer = compare.Comparer(game.get, mame.get, self.FRAMES, self.FRAMES + 7)
        calibration = comparer.choose_offset()
        self.assertEqual(calibration['offset'], 1)
        self.assertEqual(comparer.geometries, {(64, 200): compare.Geometry(4, 32, -2)})
        self.assertEqual({comparer.verdict(f)['status'] for f in range(1, self.FRAMES + 1)}, {'equal'})

    def test_a_frame_that_is_one_frame_late_is_an_offset(self):
        def alter(f, frame):
            return mame_frame(scene(f + 1)[0], 4, 32, -2) if f == 15 else frame
        _, _, verdicts = self.run_comparison(0, alter)
        item = verdicts[14]
        self.assertEqual((item['status'], item['frame']), ('offset', 15))
        self.assertIn('offset 1', item['reason'])

    def test_a_change_of_palette_keeps_the_shape_and_a_merge_of_colours_does_not(self):
        def merge(f, frame):
            if f != 20:
                return frame
            frame = frame.copy()
            frame[..., 0] = frame[..., 1]                         # the red channel shows the green one: colours merge
            return frame
        _, _, verdicts = self.run_comparison(0, merge)
        self.assertEqual(verdicts[19]['status'], 'content')
        levels = scene(20)[0].copy()
        levels[...] = numpy.where(levels == 3, 5, numpy.where(levels == 5, 3, levels))     # levels 3 and 5 swapped: one-to-one

        def swap(f, frame):
            return mame_frame(levels, 4, 32, -2) if f == 20 else frame
        _, _, verdicts = self.run_comparison(0, swap)
        self.assertEqual(verdicts[19]['status'], 'palette')

    def test_a_picture_that_differs_reports_its_share_and_its_box(self):
        def alter(f, frame):
            if f != 25:
                return frame
            frame = frame.copy()
            frame[10:20, 32 + 4 * 10:32 + 4 * 30] = 255
            return frame
        _, _, verdicts = self.run_comparison(0, alter)
        item = verdicts[24]
        self.assertEqual(item['status'], 'content')
        self.assertEqual((item['rows'], item['columns']), ([12, 21], [10, 29]))
        self.assertGreater(item['differing_share'], 0.0)

    def test_a_picture_the_game_shows_at_another_time_is_a_shift_with_its_distance(self):
        def alter(f, frame):
            return mame_frame(scene(10)[0], 4, 32, -2) if f == 30 else frame        # the scene of frames 8 to 15, shown at frame 30
        comparer, _, _ = self.run_comparison(0, alter)
        self.assertGreater(comparer.index_pictures(), 30)
        item = comparer.verdict(30)
        self.assertEqual((item['status'], item['delta']), ('shifted', -15))        # the nearest frame of the game that shows it is 15
        self.assertIn('game frame 15', item['reason'])
        self.assertEqual(comparer.verdict(29)['status'], 'equal')

    def test_a_picture_placed_elsewhere_is_a_placement_and_a_blank_mame_is_content(self):
        def alter(f, frame):
            if f == 18:
                return mame_frame(scene(18)[0], 4, 36, 1)
            if f == 19:
                return numpy.zeros_like(frame)
            return frame
        _, _, verdicts = self.run_comparison(0, alter)
        self.assertEqual(verdicts[17]['status'], 'placement')
        self.assertIn('column 36, row 1', verdicts[17]['reason'])
        self.assertEqual((verdicts[18]['status'], verdicts[18]['reason']), ('content', 'MAME is black'))

    def test_a_game_with_no_picture_yet(self):
        comparer = compare.Comparer(lambda n: numpy.zeros((0, 0, 3), dtype=numpy.uint8), lambda n: numpy.zeros((242, 1088, 3), dtype=numpy.uint8), 3, 7)
        self.assertEqual(comparer.verdict(1)['status'], 'equal')
        lit = numpy.zeros((242, 1088, 3), dtype=numpy.uint8)
        lit[5, 5] = 255
        comparer = compare.Comparer(lambda n: numpy.zeros((0, 0, 3), dtype=numpy.uint8), lambda n: lit, 3, 7)
        self.assertEqual(comparer.verdict(1)['status'], 'no_picture')

    def test_a_missing_game_frame_and_a_picture_of_one_colour_of_an_unseen_size(self):
        comparer = compare.Comparer({}.get, lambda n: numpy.zeros((242, 1088, 3), dtype=numpy.uint8), 3, 3)
        self.assertEqual(comparer.verdict(1)['status'], 'missing')
        black = numpy.zeros((224, 256, 3), dtype=numpy.uint8)
        comparer = compare.Comparer(lambda n: black, lambda n: numpy.zeros((242, 1088, 3), dtype=numpy.uint8), 3, 3)
        self.assertEqual(comparer.verdict(1)['status'], 'unplaced')
        mame = numpy.zeros((242, 1088, 3), dtype=numpy.uint8)
        mame[10:20, 10:20] = 255
        comparer = compare.Comparer(lambda n: black, lambda n: mame, 3, 3)
        self.assertEqual(comparer.verdict(1)['status'], 'content')

    def test_summary_counts_the_first_difference_and_merges_the_stretches(self):
        verdicts = [{'frame': f, 'status': 'equal', 'width': 256, 'height': 240, 'share': 1.0, 'exact': f % 2 == 0} for f in range(1, 11)]
        for f in (4, 5, 6):
            verdicts[f - 1] = {'frame': f, 'status': 'offset', 'reason': 'x', 'width': 256, 'height': 240, 'share': 0.5}
        verdicts[8] = {'frame': 9, 'status': 'content', 'reason': 'pixels differ', 'width': 256, 'height': 240, 'share': 0.9,
                       'differing_share': 0.1, 'rows': [1, 2], 'columns': [3, 4]}
        verdicts[6] = {'frame': 7, 'status': 'shifted', 'delta': -12, 'reason': 'y', 'width': 256, 'height': 240, 'share': 0.4}
        verdicts.append({'frame': 11, 'status': 'missing', 'reason': 'none'})
        summary = compare.summarize_pictures(verdicts, {'offset': 0, 'equal_on_sample': {0: 7}}, {(256, 240): compare.Geometry(4, 32, -2)})
        self.assertEqual((summary['frames_compared'], summary['equal'], summary['runs_not_equal']), (10, 5, 3))
        self.assertEqual(summary['shifted_frames'], {'count': 1, 'delta_min': -12, 'delta_median': -12, 'delta_max': -12})
        self.assertEqual(summary['first_not_equal'], {'frame': 4, 'status': 'offset', 'reason': 'x'})
        self.assertEqual([(r['first'], r['last'], r['status']) for r in summary['first_runs']], [(4, 6, 'offset'), (7, 7, 'shifted'), (9, 9, 'content')])
        self.assertEqual(summary['identical_exact'], 3)       # frames 2, 8 and 10: the exact equality of the 24-bit colours, apart (frame 7 is shifted)
        self.assertEqual(summary['geometries']['256x240'], {'dots': 4, 'column': 32, 'row': -2, 'rows_hidden_by_mame': 2})


@unittest.skipIf(numpy is None, 'numpy is needed')
class SoundTests(unittest.TestCase):
    RATE = 44100

    def tone(self, seconds, hertz=(220, 880, 3000)):
        t = numpy.arange(int(seconds * self.RATE)) / self.RATE
        return sum(numpy.sin(2 * numpy.pi * f * t) * a for f, a in zip(hertz, (1.0, 0.6, 0.3))) * 1000

    def test_a_louder_signal_on_a_dc_offset_differs_by_its_gain_alone(self):
        game = self.tone(6.1)
        mame = 3.0 * game + 8000 * numpy.minimum(1.0, numpy.arange(len(game)) / 20000)     # the offset ramps in over half a second
        result = compare.compare_channel(mame, game, self.RATE)
        self.assertTrue(result['compared'])
        self.assertAlmostEqual(result['level_difference_db_median'], 20 * numpy.log10(3.0), delta=0.15)
        self.assertLess(result['level_difference_db_spread'], 0.2)
        self.assertGreater(result['spectrum_cosine_min'], 0.98)
        self.assertGreater(result['averaged_spectrum_cosine'], 0.99)
        self.assertGreater(result['dc_offset_mame'], 7000)
        self.assertLess(abs(result['dc_offset_game']), 5)
        self.assertEqual(result['windows_compared'], 6)

    def test_silent_windows_are_counted_apart_for_each_side(self):
        loud = self.tone(3)
        silence = numpy.zeros(3 * self.RATE + self.RATE // 10)        # the first tenth of a second of each side is not compared
        both = compare.compare_channel(numpy.concatenate([silence, loud]), numpy.concatenate([silence, loud]), self.RATE)
        self.assertEqual((both['silent_both'], both['windows_compared']), (3, 3))
        lead = self.tone(3.1)
        only_game = compare.compare_channel(numpy.concatenate([lead, loud]), numpy.concatenate([silence, loud]), self.RATE)
        self.assertEqual((only_game['silent_game_only'], only_game['silent_mame_only'], only_game['windows_compared']), (3, 0, 3))
        only_mame = compare.compare_channel(numpy.concatenate([silence, loud]), numpy.concatenate([lead, loud]), self.RATE)
        self.assertEqual((only_mame['silent_game_only'], only_mame['silent_mame_only']), (0, 3))
        nothing = compare.compare_channel(silence, silence, self.RATE)
        self.assertFalse(nothing['compared'])

    def test_a_different_spectrum_is_told_by_the_cosine_and_the_bands(self):
        game = self.tone(4)
        other = self.tone(4, (440, 1760, 6000))
        result = compare.compare_channel(other, game, self.RATE)
        self.assertLess(result['averaged_spectrum_cosine'], 0.2)
        self.assertGreater(result['third_octave_max_db_below_4khz'], 20)

    def test_a_wav_and_a_pcm_file_are_compared_channel_by_channel(self):
        game = self.tone(3)
        left, right = game, 0.5 * game
        pcm = numpy.stack([left, right], axis=1).astype('<i2')
        mame = numpy.stack([2 * left + 6000, 1.0 * right + 6000], axis=1).astype('<i2')
        with tempfile.TemporaryDirectory() as folder:
            wav, raw = Path(folder) / 'mame.wav', Path(folder) / 'game.pcm'
            with wave.open(str(wav), 'wb') as stream:
                stream.setnchannels(2)
                stream.setsampwidth(2)
                stream.setframerate(self.RATE)
                stream.writeframes(mame.tobytes())
            raw.write_bytes(pcm.tobytes())
            result = compare.compare_sound(wav, raw, mame_frames=180, game_samples=[1470] * 180)
            self.assertTrue(result['compared'])
            self.assertAlmostEqual(result['left']['level_difference_db_median'], 6.02, delta=0.2)
            self.assertAlmostEqual(result['right']['level_difference_db_median'], 0.0, delta=0.2)
            self.assertEqual(result['samples_per_frame_game'], 735.0)
            self.assertAlmostEqual(result['samples_per_frame_mame'], 735.0, delta=0.5)
            with wave.open(str(wav), 'wb') as stream:             # another rate is refused, not compared
                stream.setnchannels(2)
                stream.setsampwidth(2)
                stream.setframerate(48000)
                stream.writeframes(mame.tobytes())
            self.assertFalse(compare.compare_sound(wav, raw)['compared'])


@unittest.skipIf(numpy is None, 'numpy is needed')
class FilesTests(unittest.TestCase):
    def test_a_ppm_of_the_game_is_read_and_an_empty_one_has_no_pixels(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'a.ppm'
            data = bytes(range(24))
            path.write_bytes(b'P6\n4 2\n255\n' + data)
            picture = compare.read_ppm(path)
            self.assertEqual(picture.shape, (2, 4, 3))
            self.assertEqual(picture[1, 3].tolist(), [21, 22, 23])
            path.write_bytes(b'P6\n0 0\n255\n')
            self.assertEqual(compare.read_ppm(path).shape, (0, 0, 3))
            path.write_bytes(b'P5\n1 1\n255\nx')
            with self.assertRaises(ValueError):
                compare.read_ppm(path)

    def test_mame_frames_come_from_the_file_of_their_owner(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            first, second = mame_frame(authored(256, 40, 1)[0], 4, 32, -2), mame_frame(authored(256, 40, 2)[0], 4, 32, -2)
            (folder / '000001.raw').write_bytes(bgra(first))
            (folder / '000003.raw').write_bytes(bgra(second))
            (folder / 'manifest.tsv').write_text('frame\twidth\theight\tfile\n1\t1088\t242\t1\n2\t1088\t242\t1\n3\t1088\t242\t3\n', encoding='utf-8')
            frames = compare.MameFrames(folder)
            self.assertEqual(len(frames), 3)
            self.assertTrue((frames(1) == first).all() and (frames(2) == first).all() and (frames(3) == second).all())
            with self.assertRaises(ValueError):
                compare.mame_rgb(b'\x00' * 8)

    def test_game_frames_are_numbered_from_one_and_missing_outside_the_run(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            (folder / 'frame-000001.ppm').write_bytes(b'P6\n1 1\n255\n\x01\x02\x03')
            frames = compare.GameFrames(folder, 1)
            self.assertEqual(frames(1).tolist(), [[[1, 2, 3]]])
            self.assertIsNone(frames(0))
            self.assertIsNone(frames(2))

    def test_the_trace_gives_the_samples_of_each_frame(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'trace.csv'
            path.write_text('frame,cpu,ram,image,pcm,samples\n1,a,b,c,d,1474\n2,a,b,c,d,1468\n', encoding='ascii')
            self.assertEqual(compare.trace_samples(path), [1474, 1468])


class RunTests(unittest.TestCase):
    def test_mame_runs_without_a_window_a_sound_device_or_an_input_device_and_gives_the_sound_rate_of_the_game(self):
        command = compare.mame_command(Path('mame.exe'), 'tg16', Path('card.pce'), Path('capture.lua'), Path('work'), Path('work/mame.wav'), 3000)
        self.assertEqual(command[1], 'tg16')
        for pair in (('-video', 'none'), ('-sound', 'none'), ('-keyboardprovider', 'none'), ('-joystickprovider', 'none'), ('-samplerate', '44100')):
            self.assertEqual(command[command.index(pair[0]) + 1], pair[1])
        self.assertIn('-nothrottle', command)
        self.assertNotIn('-window', command)
        self.assertTrue(Path(command[command.index('-cart') + 1]).is_absolute())
        self.assertTrue(Path(command[command.index('-wavwrite') + 1]).is_absolute())
        self.assertNotIn('-wavwrite', compare.mame_command(Path('mame.exe'), 'pce', Path('card.pce'), Path('capture.lua'), Path('work'), None, 600))

    def test_the_lua_script_is_filled_in_and_keeps_its_lua_percent_signs(self):
        text = compare.LUA % {'out': 'C:/work/mame', 'last': 3000}
        self.assertIn('local out = "C:/work/mame"', text)
        self.assertIn('local last = 3000', text)
        self.assertIn('string.format("/%06d.raw", f)', text)

    def test_the_card_reaches_mame_decoded_whatever_its_dump(self):
        rom = bytearray(0x4000)
        rom[0] = 0x78                                             # SEI at the reset vector
        rom[0x1FFE], rom[0x1FFF] = 0x00, 0xE0                     # the reset vector $E000
        rom[0x2000:0x2010] = bytes(range(16))
        reversed_ = bytes(int(f'{b:08b}'[::-1], 2) for b in rom)
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            for name, data, header, encoding in (('linear.pce', bytes(rom), 'none', 'linear'),
                                                  ('headed.pce', bytes(512) + bytes(rom), 'copier512', 'linear'),
                                                  ('reversed.pce', reversed_, 'none', 'bit-reversed')):
                card = folder / name
                card.write_bytes(data)
                target, info = compare.prepare_cartridge(card, folder / 'work')
                self.assertEqual(target.read_bytes(), bytes(rom), name)
                self.assertEqual((info['header'], info['encoding'], info['rom_bytes']), (header, encoding, 0x4000))


if __name__ == '__main__':
    unittest.main()
