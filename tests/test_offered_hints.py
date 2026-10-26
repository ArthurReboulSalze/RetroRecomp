"""Hints offered by other players (imported bank, shared base) guide a
conversion, but the local library keeps them, and an export shares them again,
only once a conversion of this player observed them."""
import base64
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zlib

from retrorecomp import gameboy, megadrive, megadrive_z80, nes, snes_spc, supernintendo


class OfferedHintsTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        env = patch.dict(os.environ, RETRO_RECOMP_LIBRARY_DIR=str(self.root / 'library'))
        env.start(); self.addCleanup(env.stop)

    def test_mega_drive_entries_and_ram_variants(self):
        data = bytearray(range(256)) * 16
        rom = SimpleNamespace(data=data, sha256=hashlib.sha256(data).hexdigest())
        profiles = patch.dict(megadrive.PROFILES, {rom.sha256:
            {'id': 'authored', 'title': 'Authored test', 'prefix': 'game', 'sonic': False}})
        profiles.start(); self.addCleanup(profiles.stop)
        offered = {'rom_entries': [[0x220]]}
        with patch('retrorecomp.megadrive.record_for', return_value=offered), \
             patch('retrorecomp.megadrive.shared_ram_variants',
                   return_value=[{'address': 0xff8000, 'bytes': '7071'}]):
            self.assertEqual(megadrive.read_entries(rom), {0x220})
            self.assertEqual(megadrive.read_entries(rom, imported=False), set())
            self.assertEqual(megadrive.learn_entries(rom, [{'rom_entries': [0x200]}]), 1)
            stored = json.loads(megadrive.memory_file(rom).read_text())
            self.assertEqual([item['address'] for item in stored['entries']], [0x200])
            self.assertEqual(stored['ram_variants'], [])
            # Observed now: the player's own, and not new to this conversion.
            self.assertEqual(megadrive.learn_entries(rom, [{'rom_entries': [0x220]},
                {'ram_variants': [{'address': 0xff8000, 'bytes': '7071'}]}]), 0)
            stored = json.loads(megadrive.memory_file(rom).read_text())
            self.assertEqual([item['address'] for item in stored['entries']], [0x200, 0x220])
            self.assertEqual(stored['ram_variants'], [{'address': 0xff8000, 'bytes': '7071'}])

    def test_mega_drive_z80_variants(self):
        path = self.root / 'z80.json'
        rom = SimpleNamespace(sha256='a' * 64)
        offered = [{'address': 0x102, 'bytes': '21112200'}]
        with patch.object(megadrive_z80, 'memory_file', return_value=path), \
             patch('retrorecomp.megadrive_z80.shared_ram_variants', return_value=offered):
            self.assertEqual(megadrive_z80.learn_variants(rom, [{'z80_variants': [
                {'address': 0x104, 'bytes': '3e000000'}]}]), 1)
            self.assertEqual(megadrive_z80.read_variants(rom, imported=False), [{'address': 0x104, 'bytes': '3e000000'}])
            self.assertEqual(megadrive_z80.learn_variants(rom, [{'z80_variants': offered}]), 0)
            self.assertEqual(len(megadrive_z80.read_variants(rom, imported=False)), 2)

    def test_super_nintendo_ram_variants_and_spc_masks(self):
        rom = SimpleNamespace(sha256=hashlib.sha256(b'authored cartridge').hexdigest())
        offered = [{'address': 0x7e0100, 'bytes': 'a93412ea'}]
        own = {'address': 0x7e0200, 'bytes': 'a97856ea'}
        with patch('retrorecomp.supernintendo.shared_ram_variants', return_value=offered):
            self.assertEqual(supernintendo.learn_ram_variants(rom, [{'ram_variants': [own]}]), 1)
            self.assertEqual(supernintendo.read_ram_variants(rom, imported=False), [own])
            self.assertEqual(len(supernintendo.read_ram_variants(rom)), 2)
            self.assertEqual(supernintendo.learn_ram_variants(rom, [{'ram_variants': offered}]), 0)
            self.assertEqual(len(supernintendo.read_ram_variants(rom, imported=False)), 2)
        data = bytes([0xe8] * 16)
        cartridge = SimpleNamespace(sha256=hashlib.sha256(data).hexdigest(), data=data)
        with patch('retrorecomp.snes_spc.record_for', return_value={'spc_refs': [[0x2000, 0]]}):
            self.assertEqual(snes_spc.learn(cartridge, [{'spc_variants': [{'address': 0x3000, 'opcode': 0xe8}]}]), 1)
            stored = json.loads(snes_spc.memory_file(cartridge).read_text())
            masks = zlib.decompress(base64.b64decode(stored['opcode_masks']))
            self.assertTrue(masks[0x3000 * 32 + 0xe8 // 8] & 1 << (0xe8 & 7))
            self.assertFalse(masks[0x2000 * 32 + 0xe8 // 8])
            self.assertTrue(snes_spc.read_masks(cartridge)[0x2000 * 32 + 0xe8 // 8])
            self.assertEqual(snes_spc.learn(cartridge, [{'spc_variants': [{'address': 0x2000, 'opcode': 0xe8}]}]), 0)
            self.assertTrue(snes_spc.read_masks(cartridge, imported=False)[0x2000 * 32 + 0xe8 // 8])

    def test_game_boy_known_entries_without_imported(self):
        data = bytes(0x10000)
        rom = SimpleNamespace(data=data, sha256=hashlib.sha256(data).hexdigest())
        with patch('retrorecomp.gameboy.record_for', return_value={'rom_entries': [[1, 0x4567]]}):
            self.assertEqual(gameboy._known_entries(rom), {(1, 0x4567)})
            self.assertEqual(gameboy._known_entries(rom, imported=False), set())

    def test_nes_offered_sites_stay_out_of_the_library(self):
        data = bytes(b'NES\x1a\x02\x00' + bytes(10)) + bytes(range(256)) * 128
        rom = SimpleNamespace(data=data, sha256=hashlib.sha256(data).hexdigest(), nes2=False)
        previous = self.root / 'library/nes/cycle-seeds.trace'
        previous.parent.mkdir(parents=True)
        previous.write_text('4k:1:9000\n')
        offered = {'rom_entries': [[0, 0x8000], [1, 0x9000]], 'ram_opcode_refs': [[0x300, 16]]}
        with patch('retrorecomp.knowledge.imported_record', return_value=offered):
            rom_sites, ram = nes._offered_only(rom, previous)
        self.assertEqual(rom_sites, {'4k:0:8000'})
        self.assertEqual(ram, {(0x300, 0)})
        seed = self.root / 'seed.trace'
        seed.write_text('4k:0:8000\n4k:2:A000\n# ram:0300:00\n# ram:0400:A9\n')
        nes._remember_seed(seed, previous, (rom_sites, ram))
        self.assertEqual(nes._seed_sites(previous), {'4k:1:9000', '4k:2:A000'})
        from retrorecomp.nes_ram import read_sites
        self.assertEqual(read_sites(previous), {(0x400, 0xA9)})


if __name__ == '__main__':
    unittest.main()
