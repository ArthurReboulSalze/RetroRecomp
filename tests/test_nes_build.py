from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from smsrecomp.core import ConversionError
from smsrecomp.nes_build import prepare_native, preserve_inputs, stage_native


class NesBuildTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name)
        header = bytearray(b'NES\x1a' + bytes(12));header[4] = 1
        data = bytes(header) + bytes([0xEA]) * 16384
        self.rom = SimpleNamespace(data=data, sha256='a'*64, nes2=False)
        (self.project/'rom.nes').write_bytes(data)
        self.compiler = self.project/'compiler.exe';self.compiler.write_bytes(b'authored compiler identity')
        self.calls = 0

    def emit(self, command, *, cwd, **kwargs):
        self.calls += 1
        generated = cwd/'generated';generated.mkdir()
        seed = Path(command[command.index('--cycle-seed-file')+1]).read_text()
        (generated/'game_cyc.c').write_text('/* RR_NES_RAM_GUARD_BEGIN */\nold\n/* RR_NES_RAM_GUARD_END */\n'+seed)
        (generated/'game_cyc_dense_000.c').write_text('authored unchanged ROM bodies\n')
        (generated/'game_cyc_live.c').write_text('authored unchanged live bodies\n')
        return 'Native PRG ROM positions: 16384/16384\n'

    def prepare(self, entries=None, guards=None):
        with patch('smsrecomp.nes_build.run',side_effect=self.emit), \
                patch('smsrecomp.nes_ram.opcode_sources',return_value={0xEA:16}):
            return prepare_native(self.project,self.compiler,self.rom,entries or set(),guards or set())

    def test_ram_discovery_updates_only_umbrella_and_preserves_rom_body_paths(self):
        first=self.prepare();self.assertFalse(first['raw_generation_reused'])
        directory=self.project/'cycle/native/generated'
        times={p.name:p.stat().st_mtime_ns for p in directory.glob('*.c')}
        result=self.prepare(guards={(0x300,0xEA)})
        self.assertEqual(self.calls,1)
        self.assertTrue(result['raw_generation_reused'])
        self.assertEqual(result['changed_sources'],['game_cyc.c'])
        self.assertEqual(result['compiled_ram_guards'],1)
        for name in ('game_cyc_dense_000.c','game_cyc_live.c'):
            self.assertEqual((directory/name).stat().st_mtime_ns,times[name])
        self.assertFalse(result['qualification_reused'])
        result=self.prepare(guards={(0x300,0xEA)})
        self.assertEqual(result['changed_sources'],[])
        self.assertIn('cycle/native/generated/game_cyc.c',(self.project/'cycle/sources.cmake').read_text())

    def test_rom_entries_and_compiler_identity_regenerate_without_rewriting_equal_bodies(self):
        self.prepare();path=self.project/'cycle/native/generated/game_cyc_dense_000.c'
        before=path.stat().st_mtime_ns
        result=self.prepare({'4k:0:8000'})
        self.assertEqual(self.calls,2);self.assertFalse(result['raw_generation_reused'])
        self.assertEqual(path.stat().st_mtime_ns,before)
        self.compiler.write_bytes(b'updated compiler identity')
        self.prepare({'4k:0:8000'});self.assertEqual(self.calls,3)

    def test_corrupted_receipt_raw_body_or_active_source_is_not_trusted(self):
        self.prepare();raw=self.project/'cycle/raw';active=self.project/'cycle/native/generated'
        (raw/'generation.json').write_text('broken JSON')
        self.prepare();self.assertEqual(self.calls,2)
        (raw/'generated/game_cyc_dense_000.c').write_text('corrupted raw body')
        self.prepare();self.assertEqual(self.calls,3)
        (active/'game_cyc_live.c').write_text('corrupted active body')
        result=self.prepare();self.assertEqual(self.calls,3)
        self.assertEqual(result['changed_sources'],['game_cyc_live.c'])

    def test_failed_generation_keeps_last_active_code_and_receipt(self):
        self.prepare();active=self.project/'cycle/native/generated/game_cyc.c'
        original=active.read_bytes();manifest=(self.project/'cycle/sources.cmake').read_bytes()
        with patch('smsrecomp.nes_build.run',side_effect=ConversionError('authored emitter failure')):
            with self.assertRaises(ConversionError):
                prepare_native(self.project,self.compiler,self.rom,{'4k:1:9000'},set())
        self.assertEqual(active.read_bytes(),original)
        self.assertEqual((self.project/'cycle/sources.cmake').read_bytes(),manifest)

    def test_incomplete_generation_cannot_replace_last_active_sources(self):
        self.prepare();active=self.project/'cycle/native/generated/game_cyc.c'
        original=active.read_bytes()
        def incomplete(command,**kwargs):
            result=self.emit(command,**kwargs)
            (kwargs['cwd']/'generated/game_cyc_live.c').unlink()
            return result
        with patch('smsrecomp.nes_build.run',side_effect=incomplete):
            with self.assertRaises(ConversionError):
                prepare_native(self.project,self.compiler,self.rom,{'4k:1:9000'},set())
        self.assertEqual(active.read_bytes(),original)

    def test_host_inputs_and_native_headers_keep_only_identical_contents(self):
        host=self.project/'cyc_host.c';host.write_bytes(b'original')
        old=host.stat().st_mtime_ns
        with preserve_inputs(self.project):host.write_bytes(b'original')
        self.assertEqual(host.stat().st_mtime_ns,old)
        with preserve_inputs(self.project):host.write_bytes(b'updated')
        self.assertEqual(host.read_bytes(),b'updated')
        assets=self.project/'assets';assets.mkdir();(assets/'retro_nes.h').write_bytes(b'header')
        native=stage_native(self.project,assets);stamp=(native/'retro_nes.h').stat().st_mtime_ns
        stage_native(self.project,assets);self.assertEqual((native/'retro_nes.h').stat().st_mtime_ns,stamp)
        (assets/'retro_nes.h').write_bytes(b'new header');stage_native(self.project,assets)
        self.assertEqual((native/'retro_nes.h').read_bytes(),b'new header')


if __name__=='__main__':unittest.main()
