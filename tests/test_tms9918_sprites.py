"""The sprite flicker reduction of the SG-1000 and the ColecoVision (F5, the Master System's option on the shared TMS9918A), and of the
MSX family on its F2 row (the TMS9918A and the V9938): the anchors that need no compiler (tools/tms9918_sprite_selftest.py compiles and
checks what the switch draws on the TMS9918A, the V9938 fixtures of msx2_checks_sprites.c on the V9938; the players' self-tests press F5)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from retrorecomp import hostkit  # noqa: E402
from retrorecomp.stamp_inputs import sharing  # noqa: E402

PIECE = 'adapters/rrhk_sprite_option.inc'
MACHINES = ('sms', 'gg', 'sg1000', 'coleco', 'msx', 'msx2', 'msx2plus')


def native(name: str) -> str:
    return (ROOT / 'native' / name).read_text(encoding='utf-8')


class SharedOptionTests(unittest.TestCase):
    def test_one_text_for_the_adapters_that_offer_it(self):
        for machine in MACHINES:
            self.assertEqual(hostkit.adapter_includes(machine), [PIECE], machine)
        for adapter in ('rrhk_sms.c', 'rrhk_sg1000.inc', 'rrhk_coleco.inc'):
            text = native(f'hostkit/adapters/{adapter}')
            self.assertIn('#include "hostkit/adapters/rrhk_sprite_option.inc"', text, adapter)
            self.assertIn('RR_SPRITE_OPTION_APPLY', text, adapter)
            self.assertNotIn('"Sprite flicker reduction ON"', text, adapter)          # the words live in the shared piece
        piece = native('hostkit/adapters/rrhk_sprite_option.inc')
        for words in ('"Sprite flicker reduction ON"', '"Original console sprite limit"', '"F5 Sprite flicker reduction: %s"',
                      '"F5  Reduce sprite flicker"', 'L"reduce_sprite_flicker"'):
            self.assertIn(words, piece)

    def test_the_stamps_of_exactly_those_machines_hold_it(self):
        self.assertEqual(set(sharing('hostkit_sprite_option')), set(MACHINES))

    def test_a_machine_whose_adapter_does_not_include_it_stages_none(self):
        self.assertEqual(hostkit.adapter_includes('nes'), [])
        self.assertEqual(hostkit.adapter_includes('md'), [])


class PictureOnlyTests(unittest.TestCase):
    def test_the_switch_is_off_unless_the_player_asks_and_is_not_part_of_the_chip(self):
        chip = native('tms9918/tms9918.c')
        self.assertIn('static int tms_all_sprites;', chip)
        self.assertNotIn('tms_all_sprites', native('tms9918/tms9918.h'))                 # not a field of the state
        self.assertNotIn('all_sprites', native('sg1000_machine/sg1000_state_file.inc'))
        self.assertNotIn('all_sprites', native('coleco_machine/coleco_state_file.inc'))

    def test_the_machines_adapters_do_not_seal_it_for_a_session(self):
        # Picture only, so each player of a match chooses: no session_option, and the row is not a run-changing one.
        for adapter in ('rrhk_sg1000.inc', 'rrhk_coleco.inc'):
            text = native(f'hostkit/adapters/{adapter}')
            self.assertNotIn('session_option', text, adapter)
            self.assertIn('rr_sprite_option_row(rows, false)', text, adapter)
        self.assertIn('rr_sprite_option_row(rows, true)', native('hostkit/adapters/rrhk_sms.c'))

    def test_the_flags_are_computed_before_the_extra_sprites_are_drawn(self):
        tiles = native('tms9918/tms_tiles.inc')
        draw = tiles[tiles.index('static void tms_sprites1_line('):]
        self.assertLess(draw.index("*status |= 0x20"), draw.index('!t->show_all'))
        extra = draw[draw.index('!t->show_all'):]
        self.assertNotIn('*status', extra)
        self.assertNotIn('hit[', extra)


class MsxRowTests(unittest.TestCase):
    """The MSX family: F5 stays the computers' fast loading, so the option is on the F2 options row only (lead, 27 Nov 2026)."""

    def test_the_option_is_a_row_key_not_f5(self):
        adapter = native('hostkit/adapters/rrhk_msx.inc')
        head = adapter[:adapter.index('#include "hostkit/adapters/rrhk_sprite_option.inc"')]
        self.assertIn('#define RR_SPRITE_OPTION_KEY RRHK_ROW_SPRITES', head)
        self.assertIn('#define RR_SPRITE_OPTION_ROW', head)
        self.assertIn('#define RR_SPRITE_OPTION_HELP', head)
        self.assertIn('#define RRHK_ROW_SPRITES (SDL_NUM_SCANCODES + 22)', native('hostkit/hostkit.h'))
        self.assertIn('state[SDL_SCANCODE_F5]', native('hostkit/adapters/rrhk_computer.inc'))      # F5 held: fast loading, unchanged
        self.assertIn('"F2  Reduce sprite flicker (options)"', adapter)                             # the help names F2, not F5

    def test_both_video_chips_are_switched_for_the_picture_only(self):
        adapter = native('hostkit/adapters/rrhk_msx.inc')
        self.assertIn('#define RR_SPRITE_OPTION_APPLY(on) (tms9918_set_all_sprites(on), msx_v9938_set_all_sprites(on))', adapter)
        self.assertIn('rr_sprite_option_row(rows, false)', adapter)
        self.assertNotIn('session_option', adapter)
        self.assertIn('static int v9938_all_sprites;', native('msx_machine/msx_v9938_draw.c'))
        for state in ('msx_machine/msx_state.c', 'msx_machine/msx_machine.h'):
            self.assertNotIn('all_sprites;', native(state), state)                                  # not a field of the state

    def test_the_v9938_flags_and_collisions_read_only_the_chips_eight(self):
        draw = native('msx_machine/msx_v9938_draw.c')
        sprites = draw[draw.index('static void sprites2('):draw.index('/* ---- the line ---- */')]
        self.assertIn('int count = total < 8 ? total : 8;', sprites)
        collisions = sprites[sprites.index('/* Collisions:'):sprites.index('/* Drawing:')]
        self.assertNotIn('total', collisions)
        self.assertLess(sprites.index('v->status0 = (uint8_t)(0x40'), sprites.index('/* Drawing:'))


if __name__ == '__main__':
    unittest.main()
