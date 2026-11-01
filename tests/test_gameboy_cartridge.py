"""The cartridge facts the Game Boy report gives (retrorecomp/gameboy_cartridge.py), on synthetic headers: no ROM."""
import unittest

from retrorecomp import gameboy_cartridge as cartridge
from retrorecomp.report_schema import read_report
from tests.test_report_schema import gb_report


def rom(kind, ram=0x00, size=0x8000, tail=b''):
    data = bytearray(size)
    data[0x147], data[0x149] = kind, ram
    data[0x4000:0x4000 + len(tail)] = tail
    return bytes(data)


class CartridgeRecordTests(unittest.TestCase):
    def test_a_battery_mbc1_with_ram(self):
        record = cartridge.cartridge_record(rom(0x03, 0x02, 0x20000))
        self.assertEqual((record['mapper'], record['header_type'], record['ram_bytes'], record['battery'], record['real_time_clock']),
                         ('MBC1', '03', 0x2000, True, False))
        self.assertEqual((record['rom_banks_16k'], record['mapper_modelled_by_runtime']), (8, True))

    def test_mbc2_has_its_own_512_cells_of_four_bits(self):
        record = cartridge.cartridge_record(rom(0x06, 0x00))
        self.assertEqual((record['mapper'], record['ram_bytes'], record['ram_cell_bits'], record['battery']), ('MBC2', 512, 4, True))

    def test_mbc3_with_a_clock_and_without_ram(self):
        record = cartridge.cartridge_record(rom(0x0F, 0x00))
        self.assertEqual((record['real_time_clock'], record['battery'], record['ram_bytes']), (True, True, 0))
        memory = cartridge.cartridge_memory(record)
        self.assertEqual((memory['battery_ram'], memory['real_time_clock'], memory['files']),
                         (False, True, ['<title>-<ROM sha256 prefix>.rtc']))

    def test_mbc3_with_a_clock_and_ram_keeps_two_files(self):
        memory = cartridge.cartridge_memory(cartridge.cartridge_record(rom(0x10, 0x03)))
        self.assertEqual(len(memory['files']), 2)
        self.assertEqual(memory['ram_bytes'], 0x8000)

    def test_mbc5_with_a_rumble_motor(self):
        record = cartridge.cartridge_record(rom(0x1E, 0x04))
        self.assertEqual((record['rumble'], record['battery'], record['ram_bytes']), (True, True, 0x20000))

    def test_a_cartridge_without_battery_keeps_nothing(self):
        memory = cartridge.cartridge_memory(cartridge.cartridge_record(rom(0x02, 0x02)))
        self.assertEqual((memory['battery_ram'], memory['files']), (False, []))

    def test_mappers_the_runtime_does_not_model_are_said_so(self):
        for kind in (0x0B, 0x20, 0x22, 0xFC, 0xFD, 0xFE, 0xFF, 0x77):
            record = cartridge.cartridge_record(rom(kind))
            self.assertFalse(record['mapper_modelled_by_runtime'], hex(kind))
            self.assertEqual(cartridge.device_entries(record)[0]['mode'], 'not_modelled')

    def test_the_runtime_lists_are_the_runtime_lists(self):
        self.assertEqual(sorted(cartridge.BATTERY), [0x03, 0x06, 0x09, 0x0D, 0x0F, 0x10, 0x13, 0x1B, 0x1E, 0x22, 0xFF])
        self.assertEqual(sorted(cartridge.CLOCK), [0x0F, 0x10])
        self.assertEqual(sorted(cartridge.BANKED), [1, 2, 3, 5, 6, 15, 16, 17, 18, 19, 25, 26, 27, 28, 29, 30])

    def test_wisdom_tree_is_found_by_its_words_in_a_rom_only_header(self):
        data = rom(0x00, 0x00, 0x10000, b'WISDOM xx TREE')
        record = cartridge.cartridge_record(data)
        self.assertEqual((record['mapper'], record['mapper_modelled_by_runtime'], record['ram_bytes']), ('Wisdom Tree', True, 0))
        self.assertFalse(cartridge.is_wisdom_tree(rom(0x00, 0x00, 0x10000, b'WISDOM only')))
        self.assertFalse(cartridge.is_wisdom_tree(rom(0x00, 0x00, 0x8000, b'WISDOM TREE')))      # 32 KiB: not larger
        self.assertFalse(cartridge.is_wisdom_tree(rom(0x01, 0x00, 0x10000, b'WISDOM TREE')))     # a real mapper in the header

    def test_a_rom_only_cartridge_is_modelled_without_a_mapper(self):
        record = cartridge.cartridge_record(rom(0x00))
        self.assertEqual((record['mapper'], record['mapper_modelled_by_runtime']), ('none', True))


class ReportDevicesTests(unittest.TestCase):
    def report(self, data):
        report = gb_report()
        report.update(hardware_devices=cartridge.device_entries(data), cartridge_memory=cartridge.cartridge_memory(data))
        return read_report(report)

    def test_the_mapper_and_the_sound_unit_are_devices_without_a_counter(self):
        document = self.report(cartridge.cartridge_record(rom(0x03, 0x02)))
        self.assertEqual([(d['id'], d['kind']) for d in document['devices']], [('MBC1', 'cartridge_mapper'), ('apu', 'audio_unit')])
        for device in document['devices']:
            self.assertIsNone(device['fallback_present'])
            self.assertIsNone(device['unit'])
            self.assertEqual(device['scenarios'], [])
            self.assertFalse(device['details']['translated_from_rom'])
            self.assertFalse(device['details']['hardware_fidelity_validated'])

    def test_they_change_neither_the_native_code_verdict_nor_the_summary(self):
        plain = read_report(gb_report())
        document = self.report(cartridge.cartridge_record(rom(0x03, 0x02)))
        self.assertEqual(document['validation']['native_code'], plain['validation']['native_code'])
        from retrorecomp.report_schema import fallback_summary
        self.assertEqual(fallback_summary(document), fallback_summary(plain))
        self.assertIsNone(fallback_summary(document)['device'])

    def test_the_memory_layout_is_in_the_saves_section(self):
        document = self.report(cartridge.cartridge_record(rom(0x03, 0x02)))
        self.assertTrue(document['saves']['cartridge_memory']['battery_ram'])

    def test_an_entry_of_another_shape_is_dropped(self):
        report = gb_report()
        report['hardware_devices'] = [{'id': 'x', 'kind': 'unknown_kind'}, {'kind': 'audio_unit'}, 'text',
                                      {'id': 'apu', 'kind': 'audio_unit'}]
        self.assertEqual([d['id'] for d in read_report(report)['devices']], ['apu'])


if __name__ == '__main__':
    unittest.main()
