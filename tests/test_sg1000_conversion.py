"""The SG-1000 conversion (retrorecomp/sg1000_conversion.py): its refusals, its standard from the file name, its report, and a
ROM-free end-to-end proof on an AUTHORED cartridge (no game byte in the repository): the translated program equals the reference
interpreter on every route, nothing runs on the interpreter after learning, the report is written and says nothing was delivered.

The end-to-end test builds the Z80 generator and the programs with the portable llvm toolchain: it takes minutes and runs only when
RR_SG1000_END_TO_END=1 is set and the toolchain and the pinned engine are in the tree (RETRO_RECOMP_TOOLCHAIN=llvm, and a scratch
RETRO_RECOMP_LIBRARY_DIR as every test conversion).
"""
import json
import os
import tempfile
import unittest
from pathlib import Path

from retrorecomp import sg1000_conversion
from retrorecomp.core import ConversionError, ROOT
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

    def test_the_delivery_note_says_nothing_was_delivered(self):
        self.assertIn('no game executable is delivered', sg1000_conversion.NOT_DELIVERED)


@unittest.skipUnless(toolchain_ready(), 'set RR_SG1000_END_TO_END=1 with the llvm toolchain and the pinned engine in the tree')
class EndToEndTests(unittest.TestCase):
    def test_an_authored_cartridge_converts_equal_to_the_reference_with_no_interpreter(self):
        from retrorecomp import sg1000_build, sg1000_routes
        with tempfile.TemporaryDirectory() as folder:
            os.environ.setdefault('RETRO_RECOMP_LIBRARY_DIR', str(Path(folder) / 'library'))
            path = Path(folder) / 'Authored (Europe).sg'
            path.write_bytes(authored_cartridge())
            messages = []
            output = SG1000.convert(path, output=Path(folder) / 'out', frames=1800, scan_level='extended', emit=messages.append)
            report = json.loads((output / 'conversion-report.json').read_text(encoding='utf-8'))
            self.assertEqual(report['system']['id'], 'sg1000')
            self.assertEqual(report['status'], 'experimental')
            self.assertEqual(report['sg1000_checks']['standard'], 'pal')
            self.assertFalse(report['sg1000_checks']['delivered'])
            self.assertIsNone(report['delivered_file'])
            self.assertEqual([row['name'] for row in report['final_checks']], ['attract', 'play', 'long-1'])
            for row in report['final_checks']:
                self.assertTrue(row['reference_match'] and row['frame_rows_equal'], row['name'])
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
            self.assertTrue(any('no executable was delivered' in message for message in messages))
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
            # A positive control: the comparison does see a difference (the same program on a PAL machine against an NTSC reference).
            ntsc = sg1000_build.run(work / 'build' / ('sg1000_reference.exe' if os.name == 'nt' else 'sg1000_reference'),
                                    args[1:], cart)
            self.assertIn('cycles', sg1000_build.differences(native, ntsc))


if __name__ == '__main__':
    unittest.main()
