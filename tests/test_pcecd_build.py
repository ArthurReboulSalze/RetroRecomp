"""The build of a PC Engine CD game, without a compiler: its CMake project, its generated header, and the disc a game holds after its program."""
from __future__ import annotations

import hashlib
import re
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from retrorecomp import pce_build, pcecd_build  # noqa: E402


class CMakeTests(unittest.TestCase):
    def test_a_disc_game_links_libchdr_and_defines_its_switch_and_a_card_game_does_not(self):
        disc = pce_build.game_cmake(None, '9.9.9', disc=True, family='pcecd')
        card = pce_build.game_cmake(None, '9.9.9')
        self.assertIn('RR_PCE_DISC=1', disc)
        self.assertIn('chdr-static', disc)
        self.assertIn('pcecd_disc.cpp pcecd_pack.c', disc)
        self.assertIn('hostkit/adapters/rrhk_pcecd.c', disc)
        self.assertIn('BUILD_SHARED_LIBS OFF', disc)
        self.assertNotIn('RR_PCE_DISC', card)
        self.assertNotIn('chdr', card)
        self.assertIn('hostkit/adapters/rrhk_pce.c', card)
        # the rest of the project is the same text: five lines for libchdr
        self.assertEqual(len(card.splitlines()) + 5, len(disc.splitlines()))
        self.assertIn('libchdr', disc)

    def test_the_libchdr_pin_is_the_one_the_engine_names(self):
        self.assertRegex(pcecd_build.LIBCHDR_REV, r'^[0-9a-f]{40}$')
        self.assertTrue(pcecd_build.LIBCHDR_URL.endswith('/libchdr.git'))
        lines = '\n'.join(pcecd_build.libchdr_cmake_lines(Path('/x/libchdr')))
        self.assertIn('CHDR_WANT_TESTS OFF', lines)
        self.assertIn('add_subdirectory("/x/libchdr" libchdr EXCLUDE_FROM_ALL)', lines)

    def test_the_cd_hash_of_the_state_changes_with_its_disc_files(self):
        class Disc:
            sha256 = 'a' * 64
        plain = pce_build.state_config(Disc(), 'Game')
        with_disc = pce_build.state_config(Disc(), 'Game', pcecd_build.GAME_FILES)
        self.assertNotEqual(plain, with_disc)


class HeldDiscTests(unittest.TestCase):
    def test_the_disc_follows_the_program_and_its_trailer_says_where(self):
        with tempfile.TemporaryDirectory(prefix='rr-pcecd-pack-') as temp:
            folder = Path(temp)
            program = folder / 'game.exe'
            program.write_bytes(b'MZ' + bytes(range(256)) * 20)
            disc = folder / 'disc.iso'
            disc.write_bytes(bytes([7]) * 4096)
            sha = hashlib.sha256(disc.read_bytes()).hexdigest()
            before = program.stat().st_size
            offset, length = pcecd_build.append_disc(program, disc, sha)
            self.assertEqual((offset, length), (before, 4096))
            blob = program.read_bytes()
            self.assertEqual(blob[offset:offset + length], disc.read_bytes())
            trailer = blob[-88:]
            self.assertEqual(trailer[:64].decode('ascii'), sha)
            self.assertEqual(struct.unpack('<QQ', trailer[64:80]), (offset, length))
            self.assertEqual(trailer[80:], b'RRPCECD1')

    def test_a_cue_set_is_refused_until_it_is_packed(self):
        with tempfile.TemporaryDirectory(prefix='rr-pcecd-pack-') as temp:
            program = Path(temp) / 'game.exe'
            program.write_bytes(b'MZ')
            with self.assertRaises(pcecd_build.PcecdBuildError):
                pcecd_build.append_disc(program, Path(temp) / 'game.cue', '0' * 64)


if __name__ == '__main__':
    unittest.main()
