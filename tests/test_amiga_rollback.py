"""The Amiga's multiplayer session (rollback): the authored slave of tools/amiga_rollback_selftest.py reads as a WHDLoad slave, and the
adapter gives the kit its snapshot, digest and session hooks. The check itself (it builds against vAmiga) is the self-test."""
import struct
import sys
import unittest
from pathlib import Path

from retrorecomp import amiga_whdload as W
from retrorecomp import amiga_vamiga

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import amiga_rollback_selftest as selftest  # noqa: E402


class AuthoredSlaveTests(unittest.TestCase):
    def test_the_slave_is_a_version_10_slave_whose_loader_copies_the_program(self):
        body = selftest.program()
        blob = selftest.slave(body)
        header = W.slave_header(W.hunks(blob))
        self.assertEqual(header.version, 10)
        self.assertEqual(header.current_dir, 'data/')
        code = W.hunks(blob)[0].data
        self.assertEqual(code[4:12], b'WHDLOADS')
        loader = header.game_loader
        self.assertEqual(struct.unpack_from('>H', code, loader)[0], 0x43FA)                 # lea body(pc),a1
        self.assertEqual(code[loader + 2 + struct.unpack_from('>h', code, loader + 2)[0]:][:len(body)], body)
        self.assertEqual(struct.unpack_from('>H', code, loader + 12)[0] + 1, len(body) // 2)  # move.w #words-1,d1

    def test_the_program_saves_between_the_two_loads(self):
        self.assertLess(selftest.FIRST_LOAD_AT, selftest.SAVE_AT)
        self.assertLess(selftest.SAVE_AT, selftest.LOAD_AT)
        body = selftest.program()
        self.assertEqual(body.count(bytes.fromhex('4ead000c')), 1)     # jsr resload_SaveFile(a5)
        self.assertEqual(body.count(bytes.fromhex('4ead0008')), 2)     # jsr resload_LoadFile(a5)


class AdapterTests(unittest.TestCase):
    def test_the_adapter_gives_the_session_hooks(self):
        text = (ROOT / 'native' / 'hostkit' / 'adapters' / 'rrhk_amiga.inc').read_text(encoding='utf-8')
        for hook in ('snap_bound', 'snap_save', 'snap_load', 'digest', 'side_effects', 'session_option', 'session_begin'):
            self.assertIn(f'machine.{hook} = a_', text)
        # The CPU's speed changes the run: its row is the kit's run-changing row, refused in a session.
        self.assertIn('rrhk_option_row_run(rows, A_ROW_CPU', text)

    def test_vamiga_gains_a_checksum_free_save_and_load(self):
        changed = {rel for rel, _, new in amiga_vamiga.REPLACEMENTS if 'rrSave(u8 *' in new or 'rrSaveAudioTo(' in new}
        self.assertEqual(changed, {'Infrastructure/CoreComponent.h', 'Infrastructure/CoreComponent.cpp', 'Ports/AudioPort.h'})


if __name__ == '__main__':
    unittest.main()
