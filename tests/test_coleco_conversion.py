"""The ColecoVision conversion (retrorecomp/coleco_conversion.py): its refusals, its standard from the file name, its report, and a
ROM-free end-to-end proof on an AUTHORED cartridge and an AUTHORED stand-in BIOS (no game byte and no BIOS byte in the repository,
tools/coleco_authored.py): the translated program equals the reference interpreter on every route, nothing runs on the interpreter after
learning, the game is built and delivered (replayed headless on every route, quick states checked in a fresh process), and the report says so
while claiming no hardware fidelity, gameplay or latency.

The end-to-end test builds the Z80 generator and the programs with the portable llvm toolchain: it takes minutes and runs only when
RR_COLECO_END_TO_END=1 is set and the toolchain and the pinned engine are in the tree (RETRO_RECOMP_TOOLCHAIN=llvm, and a scratch
RETRO_RECOMP_LIBRARY_DIR as every test conversion).
"""
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from retrorecomp import coleco_bios, coleco_build as build, coleco_conversion
from retrorecomp.core import ConversionError, ROOT, executable_name
from retrorecomp.notices import notice_files
from retrorecomp.systems.coleco import COLECO
from tools import coleco_authored as authored

KIB = 1024
BIOS = authored.authored_bios()
BIOS_SHA256 = hashlib.sha256(BIOS).hexdigest()


def toolchain_ready() -> bool:
    if not os.environ.get('RR_COLECO_END_TO_END') or not (ROOT / '.deps' / 'smsggrecomp').is_dir():
        return False
    try:
        from retrorecomp import toolchain
        os.environ.setdefault('RETRO_RECOMP_TOOLCHAIN', 'llvm')
        return bool(toolchain.tools_directory())
    except Exception:
        return False


# The keypad as MAME 0.289's ColecoVision controller reads it in keypad mode: key -> (the lines it pulls, the byte read). Recorded on
# 22 November 2026 with a private MAME run (tools of .build, never in the repository); the machine's own ports give the same bytes.
MAME_KEYPAD = {'0': (0x05, 0x7A), '1': (0x02, 0x7D), '2': (0x08, 0x77), '3': (0x03, 0x7C), '4': (0x0D, 0x72), '5': (0x0C, 0x73),
               '6': (0x01, 0x7E), '7': (0x0A, 0x75), '8': (0x0E, 0x71), '9': (0x04, 0x7B), '#': (0x09, 0x76), '*': (0x06, 0x79)}


class AuthoredBiosCase(unittest.TestCase):
    """The converter accepts one BIOS by its digest: the checks stand the authored one in for it (the table only, nothing else changes)."""
    def setUp(self):
        patch = mock.patch.object(coleco_bios, 'KNOWN', {BIOS_SHA256: 'authored stand-in BIOS'})
        patch.start()
        self.addCleanup(patch.stop)


class RefusalTests(AuthoredBiosCase):
    def convert(self, name: str, data: bytes, **options):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / name
            path.write_bytes(data)
            bios = Path(folder) / 'bios.rom'
            bios.write_bytes(BIOS)
            output = Path(folder) / 'out'
            options.setdefault('coleco_bios', str(bios))
            try:
                return COLECO.convert(path, output=output, emit=lambda _message: None, **options)
            finally:
                self.assertFalse(output.exists() and any(output.iterdir()), 'a refused conversion wrote something')

    def test_an_oversized_cartridge_is_refused_with_a_sentence(self):
        with self.assertRaisesRegex(ConversionError, 'larger than 32 KiB'):
            self.convert('big.col', bytes(64 * KIB))

    def test_a_size_that_is_not_whole_kilobytes_is_refused(self):
        with self.assertRaisesRegex(ConversionError, 'whole number of kilobytes'):
            self.convert('odd.col', bytes(8 * KIB + 3))

    def test_a_file_that_is_not_a_cartridge_name_is_refused(self):
        with self.assertRaisesRegex(ConversionError, 'not a ColecoVision cartridge name'):
            self.convert('game.nes', bytes(8 * KIB))

    def test_a_missing_or_wrong_bios_is_refused_before_anything_is_built(self):
        with self.assertRaisesRegex(ConversionError, 'choose your own copy in Options'):
            self.convert('game.col', authored.authored_cartridge(), coleco_bios=None)
        with tempfile.TemporaryDirectory() as folder:
            other = Path(folder) / 'other.rom'
            other.write_bytes(bytes(coleco_bios.BIOS_BYTES))
            with self.assertRaisesRegex(ConversionError, 'not the ColecoVision BIOS'):
                self.convert('game.col', authored.authored_cartridge(), coleco_bios=str(other))

    def test_a_scan_level_that_does_not_exist_is_refused(self):
        with self.assertRaises(ConversionError):
            self.convert('game.col', authored.authored_cartridge(), scan_level='endless')

    def test_a_run_budget_outside_its_range_is_refused(self):
        with self.assertRaisesRegex(ConversionError, '1 to 10 learning passes'):
            self.convert('game.col', authored.authored_cartridge(), passes=11)
        with self.assertRaisesRegex(ConversionError, '1 to 10,000 frames'):
            self.convert('game.col', authored.authored_cartridge(), frames=10001)

    def test_an_invalid_title_is_refused(self):
        with self.assertRaisesRegex(ConversionError, 'Invalid ColecoVision game title'):
            self.convert('game.col', authored.authored_cartridge(), title='bad\ntitle')


class StandardTests(unittest.TestCase):
    def test_a_name_labelled_europe_alone_proposes_pal(self):
        for name in ('Game (Europe).col', 'Game (Europe, Australia).col', 'Game (Australia).zip', 'Game (PAL).col'):
            self.assertEqual(coleco_conversion.proposed_standard(name), 'pal', name)

    def test_the_other_names_are_ntsc_and_a_release_for_the_usa_too_is_the_ntsc_consoles(self):
        for name in ('Game (Japan).col', 'Game (USA).col', 'Game (USA, Europe).col', 'Game (Japan, Europe).col', 'Europe Racer.col', 'Game.col'):
            self.assertEqual(coleco_conversion.proposed_standard(name), 'ntsc', name)


class ReportShapeTests(unittest.TestCase):
    def test_the_devices_are_two_models_without_a_fallback_counter(self):
        devices = coleco_conversion.hardware_devices()
        self.assertEqual([(d['id'], d['kind'], d['mode']) for d in devices],
                         [('tms9928a', 'video_unit', 'c_model'), ('sn76489a', 'audio_unit', 'c_model')])
        for device in devices:
            self.assertFalse(device['details']['hardware_fidelity_validated'])

    def test_the_delivery_note_keeps_the_five_measures_apart(self):
        note = coleco_conversion.DELIVERY_NOTE
        self.assertIn('developer only, experimental', note)
        self.assertIn('no player has played it', note)
        self.assertIn('for its owner only', note)                                        # it holds the player's BIOS
        for measure in ('hardware', 'gameplay', 'latency'):
            self.assertIn(measure, note)
        for word in ('exact', 'zero latency', 'validated'):
            self.assertNotIn(word, note)


class QuickStateTests(unittest.TestCase):
    STATE = bytes(range(256)) * 400

    def test_every_damage_is_a_different_file_and_none_is_the_good_one(self):
        damaged = coleco_conversion.damaged_states(self.STATE)
        self.assertEqual(len(set(damaged.values())), len(damaged))
        self.assertNotIn(self.STATE, damaged.values())
        for label in ('empty', 'header-cut', 'magic', 'schema', 'machine', 'identity', 'length', 'crc', 'binding', 'payload', 'body-cut'):
            self.assertIn(label, damaged)

    def test_the_check_drives_the_game_with_the_route_and_the_state_options(self):
        calls = []
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            expected = folder / 'play-packed.csv'
            rows = ['frame,cpu,ram,picture,sound,samples,audible,pc'] + [f'{n},a,b,c{n},d,735,1,0100' for n in range(1, 2001)]
            expected.write_text('\n'.join(rows) + '\n', encoding='ascii')

            def run_game(game, options, report):
                calls.append(list(options))
                state = Path(options[options.index('--save-state') + 1]) if '--save-state' in options else None
                if state is not None:
                    state.write_bytes(self.STATE)
                if '--load-state' in options:
                    count = int(options[options.index('--frames') + 1])
                    (report.parent / 'load.csv').write_text('\n'.join(rows[:1] + rows[1:][1140:count]) + '\n', encoding='ascii')
                return {}

            def exit_code(game, options):
                target = Path(options[options.index('--load-state') + 1])
                return 4 if not target.is_file() or target.read_bytes() != self.STATE else 0
            with mock.patch.object(build, 'run_game', run_game), mock.patch.object(build, 'game_exit_code', exit_code):
                result = coleco_conversion.check_states(Path('game.exe'), folder / 'states', 'play', 1800, ['--script', 'x'], expected)
        self.assertEqual(result['saved_at'], 1140)                    # 600 frames and a margin before the route's end
        self.assertEqual(result['continued_frames'], coleco_conversion.STATE_SETTLE)
        self.assertTrue(result['fresh_process_match'] and result['missing_state_creates_nothing'])
        self.assertEqual(len(result['damaged_states_refused']), len(coleco_conversion.damaged_states(self.STATE)))
        self.assertEqual(calls[0][:2], ['--frames', '1141'])
        self.assertEqual(calls[0][-4:], ['--save-state', calls[0][-3], '--save-at', '1140'])
        self.assertEqual(calls[1][:2], ['--frames', '1740'])
        self.assertIn('--load-state', calls[1])
        self.assertNotIn('--pal', calls[0])                           # the standard is the game's own (its header), not an option

    def test_a_game_that_loads_a_different_continuation_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            expected = folder / 'play-packed.csv'
            expected.write_text('frame,cpu,ram,picture,sound,samples,audible,pc\n' + ''.join(f'{n},a,b,c,d,735,1,0100\n' for n in range(1, 1801)),
                                encoding='ascii')

            def run_game(game, options, report):
                if '--save-state' in options:
                    Path(options[options.index('--save-state') + 1]).write_bytes(self.STATE)
                else:
                    (report.parent / 'load.csv').write_text('frame,cpu,ram,picture,sound,samples,audible,pc\n' + '1,a,b,WRONG,d,735,1,0100\n' * 600,
                                                            encoding='ascii')
                return {}
            with mock.patch.object(build, 'run_game', run_game):
                with self.assertRaisesRegex(ConversionError, 'F9 continuation differs'):
                    coleco_conversion.check_states(Path('game.exe'), folder / 'states', 'play', 1800, [], expected)


class PackagingTests(unittest.TestCase):
    def prepare(self, folder: Path, standard: str = 'ntsc', title: str = 'Test Game'):
        cartridge = bytes(range(256)) * 32
        identity = hashlib.sha256(cartridge).hexdigest()
        prepared = coleco_conversion.prepare_game(folder, identity, cartridge, BIOS, BIOS_SHA256, title, standard, lambda _message: None)
        return cartridge, identity, prepared

    def test_the_game_gets_its_resources_header_and_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            cartridge, identity, prepared = self.prepare(work, 'pal')
            self.assertEqual((work / 'cartridge.rom').read_bytes(), cartridge)
            self.assertEqual((work / 'bios.rom').read_bytes(), BIOS)
            self.assertEqual((work / 'export-identity.bin').read_bytes(), b'[Retro-Recomp]\0' + identity.encode('ascii') + b'\0')
            notices = (work / 'notices.txt').read_text(encoding='utf-8')
            for name in ('smsggrecomp', 'z80-recomp-core', 'superzazu-z80'):         # the profile's notice files
                self.assertIn(name, notices)
            self.assertIn(f'#define RR_FEEDBACK_IDENTITY "{identity}"', (work / 'runtime_feedback_config.h').read_text(encoding='ascii'))
            self.assertIn('#define RR_FEEDBACK_SYSTEM "coleco"', (work / 'runtime_feedback_config.h').read_text(encoding='ascii'))
            rc = (work / 'content.rc').read_text(encoding='utf-8')
            for line in ('103 RCDATA "cartridge.rom"', '104 RCDATA "bios.rom"', '203 RCDATA "notices.txt"', '205 RCDATA "export-identity.bin"',
                         '#include "game_resources.rc"'):
                self.assertIn(line, rc)
            header = (work / 'coleco_game.h').read_text(encoding='ascii')
            self.assertIn('#define RR_CV_PAL 1', header)
            self.assertIn('#define RR_CV_TITLE "Test Game"', header)
            self.assertIn(f'0x{build.state_binding("pal", len(cartridge), BIOS_SHA256)[0]:02X}', header)
            self.assertEqual(prepared['artwork'], {'embedded': False, 'source': 'disabled'})
            for name in ('coleco_player.c', 'coleco_state_file.inc', 'coleco_machine.c', 'retro_menu.c', 'game_resources.rc'):
                self.assertTrue((work / name).is_file(), name)
            self.assertTrue((work / 'hostkit' / 'shell' / 'rrhk_main.c').is_file())
            self.assertTrue((work / 'hostkit' / 'adapters' / 'rrhk_keypad.inc').is_file())
            if os.name != 'nt':
                self.assertTrue((work / 'embedded_resources.c').is_file())

    def test_preparing_again_touches_nothing_that_did_not_change(self):
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            self.prepare(work)
            names = ('cartridge.rom', 'bios.rom', 'notices.txt', 'coleco_game.h', 'content.rc', 'coleco_player.c')
            before = {name: (work / name).stat().st_mtime_ns for name in names}
            self.prepare(work)
            self.assertEqual({name: (work / name).stat().st_mtime_ns for name in names}, before)
            self.prepare(work, 'pal')                                                 # the standard is part of the game: the header moves
            self.assertIn('#define RR_CV_PAL 1', (work / 'coleco_game.h').read_text(encoding='ascii'))
            self.assertEqual((work / 'cartridge.rom').stat().st_mtime_ns, before['cartridge.rom'])

    def test_an_explicit_cover_becomes_the_games_icon_as_on_the_other_machines(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder) / 'work'
            work.mkdir()
            cover = Path(folder) / 'authored-cover.png'
            Image.new('RGBA', (96, 128), (200, 40, 40, 255)).save(cover)        # an authored picture: no commercial art in the tests
            cartridge = bytes(range(256)) * 32
            presentation = {'rom_path': Path(folder) / 'game.col', 'cover': cover, 'use_cover': True, 'online_cover': False,
                            'boxart_dir': Path(folder) / 'no-boxart'}
            identity = hashlib.sha256(cartridge).hexdigest()
            prepared = coleco_conversion.prepare_game(work, identity, cartridge, BIOS, BIOS_SHA256, 'Test Game', 'ntsc',
                                                      lambda _message: None, presentation=presentation)
            self.assertTrue(prepared['artwork']['embedded'])
            self.assertIn('101 ICON "game.ico"', (work / 'game_resources.rc').read_text(encoding='utf-8'))
            self.assertTrue((work / 'game.ico').is_file())
            declined = coleco_conversion.prepare_game(work, identity, cartridge, BIOS, BIOS_SHA256, 'Test Game', 'ntsc',
                                                      lambda _message: None, presentation=dict(presentation, use_cover=False))
            self.assertFalse(declined['artwork']['embedded'])                   # "no cover" is honoured: the icon is left out again
            self.assertNotIn('101 ICON', (work / 'game_resources.rc').read_text(encoding='utf-8'))

    def test_a_title_with_quotes_and_accents_is_a_valid_c_string(self):
        with tempfile.TemporaryDirectory() as folder:
            self.prepare(Path(folder), title='Flicky "é"')
            self.assertIn('#define RR_CV_TITLE "Flicky \\"\\303\\251\\""', (Path(folder) / 'coleco_game.h').read_text(encoding='ascii'))


@unittest.skipUnless(toolchain_ready(), 'set RR_COLECO_END_TO_END=1 with the llvm toolchain and the pinned engine in the tree')
class EndToEndTests(AuthoredBiosCase):
    def test_an_authored_cartridge_converts_equal_to_the_reference_with_no_interpreter(self):
        from retrorecomp import coleco_routes
        with tempfile.TemporaryDirectory() as folder:
            os.environ.setdefault('RETRO_RECOMP_LIBRARY_DIR', str(Path(folder) / 'library'))
            path = Path(folder) / 'Authored (Europe).col'
            path.write_bytes(authored.authored_cartridge())
            bios = Path(folder) / 'bios.rom'
            bios.write_bytes(BIOS)
            messages = []
            game = COLECO.convert(path, output=Path(folder) / 'out', frames=3600, scan_level='extended', online_cover=False,
                                  coleco_bios=str(bios), emit=messages.append)   # no catalogue is fetched: a test writes nothing outside its folders
            output = Path(folder) / 'out'
            report = json.loads((output / 'conversion-report.json').read_text(encoding='utf-8'))
            self.assertEqual(report['system']['id'], 'coleco')
            self.assertEqual(report['status'], 'experimental')
            self.assertEqual(report['coleco_checks']['standard'], 'pal')
            self.assertEqual(report['coleco_checks']['bios'], {'sha256': BIOS_SHA256, 'bytes': 8192, 'origin': 'player'})
            self.assertEqual(report['coleco_checks']['header_word'], 'direct')
            # The game is delivered: a file in the output folder under the title's name, the report names it and how it was checked.
            self.assertEqual(game, output / executable_name('Authored (Europe)'))
            self.assertTrue(game.is_file() and game.stat().st_size > 100_000)
            self.assertTrue(report['coleco_checks']['delivered'])
            self.assertIn(report['delivered_file'], ('packed', 'unpacked'))
            self.assertEqual(report['executable'], game.name)
            self.assertTrue(Path(report['build_executable']).is_file())
            self.assertIs(report['native_validation']['packed_reference_match'], True)
            self.assertEqual(len(report['packed_candidate_sha256']), 64)
            states = report['game_states']
            self.assertTrue(states['fresh_process_verified'] and states['validation']['fresh_process_match'])
            self.assertEqual(states['layout'], build.STATE_LAYOUT)
            self.assertEqual(states['validation']['continued_frames'], 600)
            self.assertTrue(states['validation']['missing_state_creates_nothing'])
            self.assertIn('damaged_states_refused', states['validation'])
            self.assertEqual(report['notices']['files'], list(notice_files('coleco')))
            self.assertEqual([row['name'] for row in report['final_checks']], ['attract', 'play', 'long-1'])
            for row in report['final_checks']:
                self.assertTrue(row['reference_match'] and row['frame_rows_equal'] and row['packed_rows_equal'], row['name'])
                self.assertEqual(row['interpreted_steps'], 0, row['name'])
                self.assertGreater(row['native_steps'], 0, row['name'])
                self.assertEqual(row['compared_fields'], list(build.COMPARED))
            for name, row in ((r['name'], r) for r in report['final_checks'] if r['name'] != 'attract'):
                self.assertGreater(row['liveness']['distinct_pictures'], 1, name)
            self.assertTrue(report['sound_routes']['play'])
            # The five measures stay apart: only native code and the agreement with the reference are measured.
            validation = report['validation']
            self.assertIs(validation['hardware_fidelity']['validated'], False)
            self.assertIs(validation['gameplay']['validated'], False)
            self.assertIs(validation['latency']['measured'], False)
            self.assertIs(validation['cpu_fidelity']['independent_cpu_oracle'], False)
            self.assertTrue(validation['native_code']['zero_fallback_on_tested_scenarios'])
            self.assertTrue(any(message.endswith('ready (no interpreter on the routes played).') for message in messages))
            # The controllers, pressed by an authored script: both programs read the same bytes, and each byte is the machine's own answer.
            work = ROOT / '.build' / 'coleco' / f'{report["rom"]["sha256"][:12]}-{BIOS_SHA256[:8]}'
            exe = lambda name: work / 'build' / (name + '.exe' if os.name == 'nt' else name)
            script = Path(folder) / 'pads.inputs'
            up, key1, key_star = routes_bits(coleco_routes)
            script.write_text(coleco_routes.script([('pad', 5, 0, up), ('pad', 100, 0, key1), ('pad', 160, 0, key_star | coleco_routes.B2),
                                                    ('pad', 200, 1, coleco_routes.B1 | coleco_routes.LEFT), ('pad', 240, 0, 0),
                                                    ('pad', 240, 1, 0)]), encoding='ascii')
            cart = build.padded(authored.authored_cartridge())
            watch = [x for address in authored.WATCH for x in ('--watch', f'{address:04X}')]
            args = ['--bios', str(bios), '--pal', '--frames', '300', *watch, '--script', str(script)]
            native = build.run(exe('coleco_check'), args, cart)
            reference = build.run(exe('coleco_reference'), args, cart)
            self.assertEqual(build.differences(native, reference), {})
            self.assertEqual(native['interrupts'], 0)                           # /INT is not wired: every frame's interrupt is an /NMI
            self.assertEqual(native['nmi'], reference['nmi'])                   # the NMIs taken are counted, on both programs
            self.assertEqual(native['watch'][f'{authored.FRAME_COUNT:04X}'], native['nmi'] % 256)   # one per frame, as the program counts them
            self.assertGreaterEqual(native['nmi'], 290)
            # Held at the end of the route they are all released: the ports read as no controller (every line high).
            self.assertEqual(native['watch'][f'{authored.STICK_1:04X}'], 0x7F)
            self.assertEqual(native['watch'][f'{authored.KEYPAD_1:04X}'], 0x7F)
            # What each controller reads while something is held, on both programs: the stick (active low, bits 0-3: up, right, down, left) and the
            # left fire button (bit 6) in joystick mode; the keypad's code and the right fire button in keypad mode; the other bits read 1.
            for frames, address, value, what in ((50, authored.STICK_1, 0x7E, 'up on controller 1'),
                                                 (140, authored.KEYPAD_1, 0x7D, 'key 1 on controller 1'),
                                                 (190, authored.KEYPAD_1, 0x39, 'key * and the right fire button on controller 1'),
                                                 (230, authored.STICK_2, 0x37, 'left and the left fire button on controller 2'),
                                                 (230, authored.KEYPAD_2, 0x7F, 'nothing on controller 2 in keypad mode')):
                held = list(args)
                held[held.index('--frames') + 1] = str(frames)
                for engine, program in (('native', 'coleco_check'), ('reference', 'coleco_reference')):
                    result = build.run(exe(program), held, cart)
                    self.assertEqual(result['watch'][f'{address:04X}'], value, f'{engine}: {what} at frame {frames}')
            # Every key of the keypad, on both controllers, against what MAME 0.289's ColecoVision controller reads (private oracle, run apart:
            # a write to 80h-9Fh then a read of FCh or FFh with the key held; the bytes are numbers, the keypad's codes active low in bits 0-3,
            # bits 4 and 5 high, bit 7 low). The key is the code of the lines it pulls in bits 6-9 of the pad word.
            for key, (lines, expected) in MAME_KEYPAD.items():
                for controller, port, address in ((0, 0, authored.KEYPAD_1), (1, 1, authored.KEYPAD_2)):
                    one = Path(folder) / f'key-{controller}.inputs'
                    one.write_text(coleco_routes.script([('pad', 5, port, lines << coleco_routes.KEY_SHIFT)]), encoding='ascii')
                    held = ['--bios', str(bios), '--pal', '--frames', '20', '--watch', f'{address:04X}', '--script', str(one)]
                    for engine, program in (('native', 'coleco_check'), ('reference', 'coleco_reference')):
                        result = build.run(exe(program), held, cart)
                        self.assertEqual(result['watch'][f'{address:04X}'], expected, f'{engine}: key {key} on controller {controller + 1}')
            # A positive control: the comparison does see a difference (the same program on a PAL machine against an NTSC reference).
            ntsc = build.run(exe('coleco_reference'), [a for a in args if a != '--pal'], cart)
            self.assertIn('cycles', build.differences(native, ntsc))
            # The DELIVERED game, replayed headless here by this test (not by the conversion), equals the reference on the pad script and on
            # every route the conversion ran, and the native check on its counts.
            run_args = [a for a in args if a not in ('--bios', str(bios), '--pal')]
            played = build.run_game(game, [*run_args, '--rows', str(Path(folder) / 'pads-game.csv')], Path(folder) / 'pads-game.json')
            self.assertEqual(build.differences(played, reference), {})
            self.assertEqual(played['engine'], 'native')
            self.assertEqual({k: played[k] for k in coleco_conversion.NATIVE_COUNTS}, {k: native[k] for k in coleco_conversion.NATIVE_COUNTS})
            self.assertIn('cycles', build.differences(played, ntsc))        # the game is the PAL one: an NTSC reference differs
            for row in report['final_checks']:
                name = row['name']
                route = ['--frames', str(row['frames']), '--script', str(work / 'routes' / f'{name}.inputs')]
                mine = build.run_game(game, [*route, '--rows', str(Path(folder) / f'{name}-game.csv')], Path(folder) / f'{name}-game.json')
                theirs = build.run(exe('coleco_reference'), ['--bios', str(bios), '--pal', *route, '--rows', str(Path(folder) / f'{name}-ref.csv')], cart)
                self.assertEqual(build.differences(mine, theirs), {}, name)
                self.assertEqual((Path(folder) / f'{name}-game.csv').read_bytes(), (Path(folder) / f'{name}-ref.csv').read_bytes(), name)
                self.assertEqual(mine['fallback_steps'], 0, name)                  # nothing runs on the interpreter after learning
                self.assertEqual(mine['native_steps'], row['native_steps'], name)
                self.assertEqual(mine['frame_trace'], row['frame_trace'], name)
            # A refused quick state: the delivered game exits 4 and writes nothing (the full set of damages is the conversion's own check).
            missing = Path(folder) / 'absent' / 'nothing.rrstate'
            self.assertEqual(build.game_exit_code(game, ['--frames', '1', '--load-state', str(missing)]), 4)
            self.assertFalse(missing.parent.exists())


def routes_bits(routes) -> tuple[int, int, int]:
    """(stick up, keypad key 1, keypad key *) as the pad word holds them."""
    return routes.UP, routes.KEY_1, 0x06 << routes.KEY_SHIFT


if __name__ == '__main__':
    unittest.main()
