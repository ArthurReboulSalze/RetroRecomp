"""A player converts with the converter's own tools (llvm-mingw, CMake, Ninja), never with an installed Visual Studio.

GitHub issue 1 (16 November 2026): beside Visual Studio the converter never offered its own tools and built with Visual
Studio, a toolchain no check runs with; the Game Boy Advance recompiler came out as a Debug build and was not found.
Visual Studio is used only when asked for by name (RETRO_RECOMP_TOOLCHAIN=msvc)."""
import os
import unittest
from pathlib import Path
from unittest import mock


@unittest.skipUnless(os.name == 'nt', 'the toolchain offer is a Windows question')
class PortableToolsOfferTests(unittest.TestCase):
    def missing(self, *, portable, studio, requested=None):
        from retrorecomp import toolchain, updater
        found = (Path('C:/vs/cmake.exe'), 'Visual Studio 17 2022') if studio else None
        with mock.patch.object(updater, 'use_installed_tools'), \
             mock.patch.object(updater.shutil, 'which', return_value='git.exe'), \
             mock.patch.object(toolchain, 'portable_installed', return_value=portable), \
             mock.patch.object(toolchain, '_prepare_path'), \
             mock.patch.object(toolchain, 'requested', return_value=requested), \
             mock.patch.object(toolchain, 'visual_studio', return_value=found):
            return updater.missing_build_tools()

    def test_an_installed_visual_studio_still_needs_the_portable_tools(self):
        self.assertEqual(self.missing(portable=False, studio=True), {'compiler': True})

    def test_the_portable_tools_installed_need_nothing(self):
        self.assertEqual(self.missing(portable=True, studio=True), {})

    def test_nothing_installed_offers_them(self):
        self.assertEqual(self.missing(portable=False, studio=False), {'compiler': True})

    def test_a_developer_asking_for_visual_studio_keeps_it(self):
        self.assertEqual(self.missing(portable=True, studio=True, requested='msvc'), {})


if __name__ == '__main__':
    unittest.main()
