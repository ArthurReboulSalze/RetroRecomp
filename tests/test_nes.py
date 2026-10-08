from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from smsrecomp.batch import identify
from smsrecomp.core import ConversionError, run, toolchain
from smsrecomp.nes import _probe, _write_probe_scripts, read_nes_rom
from smsrecomp.nes_codegen import prepare_compiler
from smsrecomp.nes_catalog import zapper_game
from smsrecomp.metadata import game_metadata
from smsrecomp.paths import ROOT
from smsrecomp.systems import profile_for_path


def cartridge(*, nes2=False, timing=0, battery=False):
    header = bytearray(16)
    header[:4] = b'NES\x1a'
    header[4] = 2
    header[5] = 1
    if nes2:
        header[7] = 0x08
        header[12] = timing
    if battery:
        header[6] |= 0x02
    return bytes(header) + bytes(2 * 16384 + 8192)


class NesProfileTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()

    def test_nes_zip_detected_without_writing_beside_source(self):
        source = self.root / 'Sample.zip'
        with ZipFile(source, 'w') as archive:
            archive.writestr('Sample.nes', cartridge())
        before = source.read_bytes()
        self.assertEqual(profile_for_path(source).id, 'nes')
        self.assertEqual(identify(source).system, 'nes')
        self.assertEqual(read_nes_rom(source).mapper, 0)
        self.assertEqual(source.read_bytes(), before)
        self.assertEqual(list(self.root.iterdir()), [source])

    def test_headered_bin_and_nes2_timing_are_separate_from_game_boy(self):
        source = self.root / 'Sample.bin'
        source.write_bytes(cartridge(nes2=True, timing=1))
        self.assertEqual(profile_for_path(source).id, 'nes')
        self.assertEqual(identify(source).video_hint, 'pal')
        self.assertEqual(read_nes_rom(source).video_standard, 'pal')

    def test_size_mismatch_is_rejected_before_compilation(self):
        source = self.root / 'Broken.nes'
        source.write_bytes(cartridge()[:-1])
        with self.assertRaisesRegex(ConversionError, 'declares'):
            read_nes_rom(source)

    def test_nes_timing_priority_and_uncertainty(self):
        cases = [('Sample (Europe).nes', cartridge(), 'pal', 'filename_region'),
                 ('Sample (USA, Europe).nes', cartridge(), 'ntsc', 'filename_region'),
                 ('Sample.nes', cartridge(), 'ntsc', 'default_guess'),
                 ('Sample (Europe).nes', cartridge(nes2=True), 'ntsc', 'nes2_header'),
                 ('Sample.nes', cartridge(nes2=True,timing=2), 'multi', 'nes2_header'),
                 ('Sample.nes', cartridge(nes2=True,timing=3), 'dendy', 'nes2_header')]
        for name, data, standard, origin in cases:
            with self.subTest(name=name, standard=standard, origin=origin):
                path=self.root/name; path.write_bytes(data)
                rom=read_nes_rom(path)
                self.assertEqual((rom.video_standard,rom.timing_source),(standard,origin))
        data=bytearray(cartridge()); data[9]=1
        path=self.root/'Sample (USA).nes'; path.write_bytes(data)
        self.assertEqual(read_nes_rom(path).timing_source,'ines_header')
        self.assertEqual(read_nes_rom(path).video_standard,'pal')

    def test_zapper_catalogue_exact_names_header_and_metadata(self):
        for name in ('Duck Hunt (World).zip', "Hogan's Alley.nes", 'Super Mario Bros. + Duck Hunt (USA).nes'):
            self.assertTrue(zapper_game(cartridge(),name))
        for name in ('Super Mario Bros.nes','Duck Tales.nes','Duck Hunt Fan Sequel.nes'):
            self.assertFalse(zapper_game(cartridge(),name))
        data=bytearray(cartridge(nes2=True));data[15]=8
        self.assertTrue(zapper_game(bytes(data),'Unlabelled.nes'))
        data[15]=9  # Dual Zapper is a separate, unsupported accessory.
        self.assertFalse(zapper_game(bytes(data),'Unlabelled.nes'))
        info=game_metadata('Duck Hunt',False,'pal','nes',zapper=True)
        self.assertIn('Nintendo NES PAL',info['FileDescription'])
        self.assertIn('Zapper',info['Controls'])

    def test_probe_accepts_zero_fallback_and_counts_other_interpretation(self):
        executable = self.root / 'game.exe'
        seed = self.root / 'seeds.trace'
        with patch('smsrecomp.nes.run', return_value='mode=native frames=1 cycles=100 native_cycles=100 (100.0%)'):
            self.assertEqual(_probe(executable, self.root, 'boot', 1, seed)['interpreter_cycles'], 0)
        output = ('mode=native frames=1 cycles=100 native_cycles=90 (90.0%)\n'
                  '  interpreted: ROM 2 (2.0%)  RAM 3 (3.0%)  $2000-$7FFF 4 (4.0%)\n')
        with patch('smsrecomp.nes.run', return_value=output):
            result = _probe(executable, self.root, 'boot', 1, seed)
            self.assertEqual(result['interpreter_cycles'], 9)
            self.assertEqual(result['non_dispatch_cycles'], 1)

    def test_all_banks_have_native_entries_with_live_boundary_operands(self):
        engine = ROOT / '.deps/nesrecomp'
        if not (engine / 'recompiler/src/cyc_codegen.c').is_file():
            self.skipTest('Pinned NESRecomp checkout unavailable')
        cmake, generator = toolchain()
        compiler = prepare_compiler(engine, cmake, generator, lambda _message: None)
        config = self.root / 'game.toml'
        config.write_text('[game]\n', encoding='ascii')
        seeds = self.root / 'seeds.trace'
        seeds.write_text('4k:00:8FFE\n4k:01:9FFF\n4k:07:FFFE\n', encoding='ascii')
        for mapper, prg_banks in ((0, 2), (0, 1), (2, 2)):
            with self.subTest(mapper=mapper, prg_banks=prg_banks):
                header = bytearray(16)
                header[:4] = b'NES\x1a'
                header[4], header[5], header[6] = prg_banks, 1, mapper << 4
                prg = bytearray([0xEA] * (16384 * prg_banks))
                prg[0x0FFE:0x1001] = b'\x4c\xfe\x8f'  # JMP $8FFE, operand crosses $9000.
                prg[0x1FFF:0x2001] = b'\xa9\x42'  # LDA #$42, operand crosses $A000.
                prg[-6:] = b'\xfe\x8f' * 3  # NMI, reset, IRQ vectors.
                rom = self.root / f'mapper{mapper}-{prg_banks}.nes'
                rom.write_bytes(header + prg + bytes(8192))
                out = self.root / f'mapper{mapper}-{prg_banks}'
                out.mkdir()
                log = run([compiler, rom, '--game', config, '--cycle-accurate',
                           '--cycle-seed-file', seeds, '--output-prefix', 'game'], cwd=out)
                generated = '\n'.join(path.read_text(encoding='utf-8')
                                      for path in (out / 'generated').glob('game_cyc_b*.c'))
                for address in ('8FFE', '9FFF'):
                    if mapper == 0:
                        self.assertIn(f'case 0x{address}:', generated)
                    else:
                        self.assertNotIn(f'case 0x{address}:', generated)
                # Unobserved positions now use compact native bodies. They do
                # not require an address-specific hot block or another pass.
                self.assertTrue('case 0x8123:' not in generated)
                self.assertNotIn('case 0xFFFE:', generated)
                self.assertIn(f'Native PRG ROM positions: {len(prg)}/{len(prg)}', log)
                dense = '\n'.join(path.read_text(encoding='utf-8')
                                  for path in (out / 'generated').glob('game_cyc_dense_*.c'))
                self.assertIn('cpu_fetch_rom(pc, 0xA9)', dense)
                self.assertIn('cpu_read((uint16_t)(pc + 1)', dense)
                self.assertNotIn('cpu_interp_step', dense)
                self.assertNotIn('switch (opcode)', dense)

    def test_gameplay_probes_keep_exercising_inputs_without_repeated_start(self):
        for frames in (12, 1800):
            for name, path in _write_probe_scripts(self.root, frames).items():
                if path is None:
                    continue
                with self.subTest(frames=frames, scenario=name):
                    events = [(int(line.split()[0]), set(line.split()[1].split('+')))
                              for line in path.read_text().splitlines()]
                    self.assertTrue(all(0 <= frame < frames for frame, _keys in events))
                    self.assertLessEqual(sum('START' in keys for _frame, keys in events), 1)
                    self.assertTrue(all(not {'LEFT', 'RIGHT'} <= keys for _frame, keys in events))
                    if frames == 1800:
                        tail = [keys for frame, keys in events if frame >= frames - 128]
                        self.assertTrue(any('A' in keys for keys in tail))
                        self.assertTrue(any('A' not in keys for keys in tail))
                        self.assertTrue(all('LEFT' in keys or 'RIGHT' in keys for keys in tail))


if __name__ == '__main__':
    unittest.main()
