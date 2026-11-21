"""The SG-1000 conversion (retrorecomp/sg1000_conversion.py): its refusals, its standard from the file name, its report, and a
ROM-free end-to-end proof on an AUTHORED cartridge (no game byte in the repository): the translated program equals the reference
interpreter on every route, nothing runs on the interpreter after learning, the game is built and delivered (replayed headless on every
route, quick states checked in a fresh process), and the report says so while claiming no hardware fidelity, gameplay or latency.

The end-to-end test builds the Z80 generator and the programs with the portable llvm toolchain: it takes minutes and runs only when
RR_SG1000_END_TO_END=1 is set and the toolchain and the pinned engine are in the tree (RETRO_RECOMP_TOOLCHAIN=llvm, and a scratch
RETRO_RECOMP_LIBRARY_DIR as every test conversion).
"""
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from retrorecomp import sg1000_build as build, sg1000_conversion
from retrorecomp.core import ConversionError, ROOT, executable_name
from retrorecomp.notices import notice_files
from retrorecomp.systems.sg1000 import SG1000

KIB = 1024


def authored_cartridge() -> bytes:
    """A 8 KiB program written for this test: it sets the VDP registers, plays a PSG tone, counts the VDP /INT in RAM (C000h) and
    the Pause NMI (C001h), and colours the backdrop from that count xor the pad (so that the picture moves, and answers the pad)."""
    cart = bytearray(b'\xFF' * 0x2000)

    def put(at: int, data: list) -> None:
        cart[at:at + len(data)] = bytes(data)
    put(0x0000, [0xF3, 0x31, 0x00, 0xC4, 0xC3, 0x00, 0x01])                    # DI, LD SP,C400h, JP 0100h
    put(0x0038, [0xF5, 0xDB, 0xBF,                                              # PUSH AF, IN A,(BFh): acknowledge the /INT
                 0x3A, 0x00, 0xC0, 0x3C, 0x32, 0x00, 0xC0,                      # the frame count in RAM
                 0x47, 0xDB, 0xDC, 0xA8, 0xE6, 0x0F,                            # B = count, A = pad 1 xor count, low nibble
                 0xD3, 0xBF, 0x3E, 0x87, 0xD3, 0xBF,                            # VDP register 7 (the backdrop colour)
                 0xF1, 0xFB, 0xED, 0x4D])                                       # POP AF, EI, RETI
    put(0x0066, [0xF5, 0x3A, 0x01, 0xC0, 0x3C, 0x32, 0x01, 0xC0, 0xF1, 0xED, 0x45])   # the Pause NMI: count it, RETN
    put(0x0100, [0xED, 0x56, 0x3E, 0xE0, 0xD3, 0xBF, 0x3E, 0x81, 0xD3, 0xBF,   # IM 1, VDP register 1: display and /INT on
                 0x3E, 0x8E, 0xD3, 0x7F, 0x3E, 0x0F, 0xD3, 0x7F, 0x3E, 0x90, 0xD3, 0x7F,   # PSG: a tone on channel 0, full volume
                 0xFB, 0x76, 0x18, 0xFD])                                       # EI, HALT, JR to the HALT
    return bytes(cart)


def toolchain_ready() -> bool:
    if not os.environ.get('RR_SG1000_END_TO_END') or not (ROOT / '.deps' / 'smsggrecomp').is_dir():
        return False
    try:
        from retrorecomp import toolchain
        os.environ.setdefault('RETRO_RECOMP_TOOLCHAIN', 'llvm')
        return bool(toolchain.tools_directory())
    except Exception:
        return False


class RefusalTests(unittest.TestCase):
    def convert(self, name: str, data: bytes, **options):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / name
            path.write_bytes(data)
            output = Path(folder) / 'out'
            try:
                return SG1000.convert(path, output=output, emit=lambda _message: None, **options)
            finally:
                self.assertFalse(output.exists() and any(output.iterdir()), 'a refused conversion wrote something')

    def test_an_oversized_cartridge_is_refused_with_a_sentence(self):
        with self.assertRaisesRegex(ConversionError, 'larger than 48 KiB'):
            self.convert('big.sg', bytes(64 * KIB))

    def test_a_size_that_is_not_whole_kilobytes_is_refused(self):
        with self.assertRaisesRegex(ConversionError, 'whole number of kilobytes'):
            self.convert('odd.sg', bytes(8 * KIB + 3))

    def test_a_file_that_is_not_a_cartridge_name_is_refused(self):
        with self.assertRaisesRegex(ConversionError, 'not an SG-1000 cartridge name'):
            self.convert('game.nes', bytes(8 * KIB))

    def test_a_scan_level_that_does_not_exist_is_refused(self):
        with self.assertRaises(ConversionError):
            self.convert('game.sg', authored_cartridge(), scan_level='endless')

    def test_a_run_budget_outside_its_range_is_refused(self):
        with self.assertRaisesRegex(ConversionError, '1 to 10 learning passes'):
            self.convert('game.sg', authored_cartridge(), passes=11)
        with self.assertRaisesRegex(ConversionError, '1 to 10,000 frames'):
            self.convert('game.sg', authored_cartridge(), frames=10001)

    def test_an_invalid_title_is_refused(self):
        with self.assertRaisesRegex(ConversionError, 'Invalid SG-1000 game title'):
            self.convert('game.sg', authored_cartridge(), title='bad\ntitle')


class StandardTests(unittest.TestCase):
    def test_a_name_labelled_europe_proposes_pal(self):
        for name in ('Game (Europe).sg', 'Game (Japan, Europe).sg', 'Game (Australia).zip', 'Game (PAL).sg'):
            self.assertEqual(sg1000_conversion.proposed_standard(name), 'pal', name)

    def test_the_other_names_are_ntsc(self):
        for name in ('Game (Japan).sg', 'Game (USA).sg', 'Europe Racer.sg', 'Game.sg'):
            self.assertEqual(sg1000_conversion.proposed_standard(name), 'ntsc', name)


class ReportShapeTests(unittest.TestCase):
    def test_the_devices_are_two_models_without_a_fallback_counter(self):
        devices = sg1000_conversion.hardware_devices()
        self.assertEqual([(d['id'], d['kind'], d['mode']) for d in devices],
                         [('tms9918a', 'video_unit', 'c_model'), ('sn76489a', 'audio_unit', 'c_model')])
        for device in devices:
            self.assertFalse(device['details']['hardware_fidelity_validated'])

    def test_the_delivery_note_keeps_the_five_measures_apart(self):
        note = sg1000_conversion.DELIVERY_NOTE
        self.assertIn('developer only, experimental', note)
        self.assertIn('no player has played it', note)
        for measure in ('hardware', 'gameplay', 'latency'):
            self.assertIn(measure, note)
        for word in ('exact', 'zero latency', 'validated'):
            self.assertNotIn(word, note)


class QuickStateTests(unittest.TestCase):
    STATE = bytes(range(256)) * 400

    def test_every_damage_is_a_different_file_and_none_is_the_good_one(self):
        damaged = sg1000_conversion.damaged_states(self.STATE)
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
            from retrorecomp import sg1000_build
            with mock.patch.object(sg1000_build, 'run_game', run_game), mock.patch.object(sg1000_build, 'game_exit_code', exit_code):
                result = sg1000_conversion.check_states(Path('game.exe'), folder / 'states', 'play', 1800, ['--script', 'x'], expected)
        self.assertEqual(result['saved_at'], 1140)                    # 600 frames and a margin before the route's end
        self.assertEqual(result['continued_frames'], sg1000_conversion.STATE_SETTLE)
        self.assertTrue(result['fresh_process_match'] and result['missing_state_creates_nothing'])
        self.assertEqual(len(result['damaged_states_refused']), len(sg1000_conversion.damaged_states(self.STATE)))
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
            from retrorecomp import sg1000_build
            with mock.patch.object(sg1000_build, 'run_game', run_game):
                with self.assertRaisesRegex(ConversionError, 'F9 continuation differs'):
                    sg1000_conversion.check_states(Path('game.exe'), folder / 'states', 'play', 1800, [], expected)


class PackagingTests(unittest.TestCase):
    def prepare(self, folder: Path, standard: str = 'ntsc', title: str = 'Test Game'):
        cartridge = bytes(range(256)) * 32
        identity = hashlib.sha256(cartridge).hexdigest()
        prepared = sg1000_conversion.prepare_game(folder, identity, cartridge, title, standard, lambda _message: None)
        return cartridge, identity, prepared

    def test_the_game_gets_its_resources_header_and_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            cartridge, identity, prepared = self.prepare(work, 'pal')
            self.assertEqual((work / 'cartridge.rom').read_bytes(), cartridge)
            self.assertEqual((work / 'export-identity.bin').read_bytes(), b'[Retro-Recomp]\0' + identity.encode('ascii') + b'\0')
            notices = (work / 'notices.txt').read_text(encoding='utf-8')
            for name in ('smsggrecomp', 'z80-recomp-core', 'superzazu-z80'):         # the profile's notice files
                self.assertIn(name, notices)
            self.assertIn(f'#define RR_FEEDBACK_IDENTITY "{identity}"', (work / 'runtime_feedback_config.h').read_text(encoding='ascii'))
            self.assertIn('#define RR_FEEDBACK_SYSTEM "sg1000"', (work / 'runtime_feedback_config.h').read_text(encoding='ascii'))
            rc = (work / 'content.rc').read_text(encoding='utf-8')
            for line in ('103 RCDATA "cartridge.rom"', '203 RCDATA "notices.txt"', '205 RCDATA "export-identity.bin"', '#include "game_resources.rc"'):
                self.assertIn(line, rc)
            self.assertNotIn('104', rc)                                              # no BIOS
            header = (work / 'sg1000_game.h').read_text(encoding='ascii')
            self.assertIn('#define RR_SG_PAL 1', header)
            self.assertIn('#define RR_SG_TITLE "Test Game"', header)
            self.assertIn(f'0x{build.state_binding("pal", len(cartridge))[0]:02X}', header)
            self.assertEqual(prepared['artwork'], {'embedded': False, 'source': 'disabled'})
            for name in ('sg1000_player.c', 'sg1000_state_file.inc', 'sg1000_machine.c', 'retro_menu.c', 'game_resources.rc'):
                self.assertTrue((work / name).is_file(), name)
            self.assertTrue((work / 'hostkit' / 'shell' / 'rrhk_main.c').is_file())
            if os.name != 'nt':
                self.assertTrue((work / 'embedded_resources.c').is_file())

    def test_preparing_again_touches_nothing_that_did_not_change(self):
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            self.prepare(work)
            names = ('cartridge.rom', 'notices.txt', 'sg1000_game.h', 'content.rc', 'sg1000_player.c')
            before = {name: (work / name).stat().st_mtime_ns for name in names}
            self.prepare(work)
            self.assertEqual({name: (work / name).stat().st_mtime_ns for name in names}, before)
            self.prepare(work, 'pal')                                                 # the standard is part of the game: the header moves
            self.assertIn('#define RR_SG_PAL 1', (work / 'sg1000_game.h').read_text(encoding='ascii'))
            self.assertEqual((work / 'cartridge.rom').stat().st_mtime_ns, before['cartridge.rom'])

    def test_an_explicit_cover_becomes_the_games_icon_as_on_the_other_machines(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder) / 'work'
            work.mkdir()
            cover = Path(folder) / 'authored-cover.png'
            Image.new('RGBA', (96, 128), (200, 40, 40, 255)).save(cover)        # an authored picture: no commercial art in the tests
            cartridge = bytes(range(256)) * 32
            presentation = {'rom_path': Path(folder) / 'game.sg', 'cover': cover, 'use_cover': True, 'online_cover': False,
                            'boxart_dir': Path(folder) / 'no-boxart'}
            prepared = sg1000_conversion.prepare_game(work, hashlib.sha256(cartridge).hexdigest(), cartridge, 'Test Game', 'ntsc',
                                                      lambda _message: None, presentation=presentation)
            self.assertTrue(prepared['artwork']['embedded'])
            self.assertIn('101 ICON "game.ico"', (work / 'game_resources.rc').read_text(encoding='utf-8'))
            self.assertTrue((work / 'game.ico').is_file())
            declined = sg1000_conversion.prepare_game(work, hashlib.sha256(cartridge).hexdigest(), cartridge, 'Test Game', 'ntsc',
                                                      lambda _message: None, presentation=dict(presentation, use_cover=False))
            self.assertFalse(declined['artwork']['embedded'])                   # "no cover" is honoured: the icon is left out again
            self.assertNotIn('101 ICON', (work / 'game_resources.rc').read_text(encoding='utf-8'))

    def test_a_title_with_quotes_and_accents_is_a_valid_c_string(self):
        with tempfile.TemporaryDirectory() as folder:
            self.prepare(Path(folder), title='Flicky "é"')
            self.assertIn('#define RR_SG_TITLE "Flicky \\"\\303\\251\\""', (Path(folder) / 'sg1000_game.h').read_text(encoding='ascii'))


@unittest.skipUnless(toolchain_ready(), 'set RR_SG1000_END_TO_END=1 with the llvm toolchain and the pinned engine in the tree')
class EndToEndTests(unittest.TestCase):
    def test_an_authored_cartridge_converts_equal_to_the_reference_with_no_interpreter(self):
        from retrorecomp import sg1000_build, sg1000_routes
        with tempfile.TemporaryDirectory() as folder:
            os.environ.setdefault('RETRO_RECOMP_LIBRARY_DIR', str(Path(folder) / 'library'))
            path = Path(folder) / 'Authored (Europe).sg'
            path.write_bytes(authored_cartridge())
            messages = []
            game = SG1000.convert(path, output=Path(folder) / 'out', frames=1800, scan_level='extended', online_cover=False,
                                emit=messages.append)       # no catalogue is fetched: a test writes nothing outside its folders
            output = Path(folder) / 'out'
            report = json.loads((output / 'conversion-report.json').read_text(encoding='utf-8'))
            self.assertEqual(report['system']['id'], 'sg1000')
            self.assertEqual(report['status'], 'experimental')
            self.assertEqual(report['sg1000_checks']['standard'], 'pal')
            # The game is delivered: a file in the output folder under the title's name, the report names it and how it was checked.
            self.assertEqual(game, output / executable_name('Authored (Europe)'))
            self.assertTrue(game.is_file() and game.stat().st_size > 100_000)
            self.assertTrue(report['sg1000_checks']['delivered'])
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
            self.assertEqual(report['notices']['files'], list(notice_files('sg1000')))
            self.assertEqual([row['name'] for row in report['final_checks']], ['attract', 'play', 'long-1'])
            for row in report['final_checks']:
                self.assertTrue(row['reference_match'] and row['frame_rows_equal'] and row['packed_rows_equal'], row['name'])
                self.assertEqual(row['interpreted_steps'], 0, row['name'])
                self.assertGreater(row['native_steps'], 0, row['name'])
                self.assertEqual(row['compared_fields'], list(sg1000_build.COMPARED))
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
            # The Pause button, pressed by an authored script (the routes never press it): both programs take the NMI alike.
            work = ROOT / '.build' / 'sg1000' / report['rom']['sha256'][:12]
            script = Path(folder) / 'pause.inputs'
            script.write_text(sg1000_routes.script([('pad', 5, 0, sg1000_routes.B1), ('pause', 100), ('pause', 150)]), encoding='ascii')
            cart = sg1000_build.padded(authored_cartridge())
            args = ['--pal', '--frames', '300', '--watch', 'C000', '--watch', 'C001', '--script', str(script)]
            native = sg1000_build.run(work / 'build' / 'sg1000_check.exe' if os.name == 'nt' else work / 'build' / 'sg1000_check', args, cart)
            reference = sg1000_build.run(work / 'build' / 'sg1000_reference.exe' if os.name == 'nt' else work / 'build' / 'sg1000_reference',
                                         args, cart)
            self.assertEqual(sg1000_build.differences(native, reference), {})
            self.assertEqual(native['watch']['C001'], 2)                       # two Pause presses, two NMIs taken
            self.assertEqual(native['watch']['C000'], native['interrupts'] % 256)   # the /INT of every frame, counted by the program
            self.assertGreaterEqual(native['interrupts'], 290)
            self.assertEqual(native['nmi'], 2)                                 # the two Pause presses, counted apart from /INT
            self.assertEqual(native['nmi'], reference['nmi'])
            # A positive control: the comparison does see a difference (the same program on a PAL machine against an NTSC reference).
            ntsc = sg1000_build.run(work / 'build' / ('sg1000_reference.exe' if os.name == 'nt' else 'sg1000_reference'),
                                    args[1:], cart)
            self.assertIn('cycles', sg1000_build.differences(native, ntsc))
            # The DELIVERED game, replayed headless here by this test (not by the conversion): on the Pause script and on every route the
            # conversion ran, it equals the reference on every compared field and every frame row, and the native check on its counts.
            played = sg1000_build.run_game(game, [x for x in args[1:] if x != '--cart'] + ['--rows', str(Path(folder) / 'pause-game.csv')],
                                           Path(folder) / 'pause-game.json')
            self.assertEqual(sg1000_build.differences(played, reference), {})
            self.assertEqual(played['watch']['C001'], 2)
            self.assertEqual(played['engine'], 'native')
            self.assertEqual({k: played[k] for k in sg1000_conversion.NATIVE_COUNTS}, {k: native[k] for k in sg1000_conversion.NATIVE_COUNTS})
            self.assertIn('cycles', sg1000_build.differences(played, ntsc))        # the game is the PAL one: an NTSC reference differs
            reference_exe = work / 'build' / ('sg1000_reference.exe' if os.name == 'nt' else 'sg1000_reference')
            for row in report['final_checks']:
                name = row['name']
                route = ['--frames', str(row['frames']), '--watch', 'C000', '--watch', 'C001', '--script', str(work / 'routes' / f'{name}.inputs')]
                mine = sg1000_build.run_game(game, [*route, '--rows', str(Path(folder) / f'{name}-game.csv')], Path(folder) / f'{name}-game.json')
                theirs = sg1000_build.run(reference_exe, ['--pal', *route, '--rows', str(Path(folder) / f'{name}-ref.csv')], cart)
                self.assertEqual(sg1000_build.differences(mine, theirs), {}, name)
                self.assertEqual((Path(folder) / f'{name}-game.csv').read_bytes(), (Path(folder) / f'{name}-ref.csv').read_bytes(), name)
                self.assertEqual(mine['fallback_steps'], 0, name)                  # nothing runs on the interpreter after learning
                self.assertEqual(mine['native_steps'], row['native_steps'], name)
                self.assertEqual(mine['frame_trace'], row['frame_trace'], name)
            # A refused quick state: the delivered game exits 4 and writes nothing (the full set of damages is the conversion's own check).
            missing = Path(folder) / 'absent' / 'nothing.rrstate'
            self.assertEqual(sg1000_build.game_exit_code(game, ['--frames', '1', '--load-state', str(missing)]), 4)
            self.assertFalse(missing.parent.exists())


if __name__ == '__main__':
    unittest.main()
