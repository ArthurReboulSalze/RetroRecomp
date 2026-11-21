"""The Amstrad CPC's build on the banked Z80 chain (retrorecomp/cpc_build.py): the sources it gives the generator and the files it
stages, with stand-in firmware (no ROM)."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest import mock

from retrorecomp import cpc_build, z80_chain_build
from retrorecomp.paths import ASSETS


class BuildTests(unittest.TestCase):
    def test_the_sources_are_the_system_rom_then_amsdos(self):
        system, amsdos = bytes([1]) * 0x8000, bytes([2]) * 0x4000
        first, others = cpc_build.sources(system, amsdos)
        self.assertEqual((first, others), (system, (('amsdos.rom', amsdos),)))
        for bad in ((system[:-1], amsdos), (system, amsdos + b'\0')):
            with self.assertRaises(cpc_build.CpcBuildError):
                cpc_build.sources(*bad)

    def test_generate_hands_the_chain_the_cpcs_machine_and_its_costs(self):
        from retrorecomp.systems.amstrad_cpc import CPC_MACHINE
        with mock.patch.object(z80_chain_build, 'generate_bodies') as generate:
            cpc_build.generate(Path('work'), bytes(0x8000), bytes(0x4000))
        args, kwargs = generate.call_args
        self.assertIs(args[1], CPC_MACHINE)
        self.assertEqual((kwargs['loop_name'], kwargs['accept']), ('cpc_banked_loop.inc', 'cpc_reference_accept'))
        self.assertIsNotNone(CPC_MACHINE.costs)

    def test_the_chain_passes_the_costs_to_the_reference_copy(self):
        source = (ASSETS / 'retrorecomp' / 'z80_chain_build.py').read_text(encoding='utf-8')
        self.assertIn('costs=machine.costs', source)

    def test_every_staged_file_exists_and_is_listed_for_the_stamps(self):
        from retrorecomp import compilation_inputs
        names = set(compilation_inputs.manifest_names('cpc'))
        for folder, files in (('native/cpc_machine', cpc_build.MACHINE_FILES), ('native/upd765', cpc_build.DISK_FILES)):
            for name in files:
                with self.subTest(name=name):
                    self.assertTrue((ASSETS / folder / name).is_file())
                    self.assertIn(f'{folder}/{name}', names)
        with tempfile.TemporaryDirectory() as folder:
            cpc_build.stage_sources(Path(folder))
            self.assertTrue((Path(folder) / 'cpc_glue.inc').is_file() and (Path(folder) / 'upd765.c').is_file()
                            and (Path(folder) / 'z80_chain_glue.inc').is_file())


if __name__ == '__main__':
    unittest.main()
