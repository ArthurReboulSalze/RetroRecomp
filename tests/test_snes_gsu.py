import json
import tempfile
import unittest
from pathlib import Path

from retrorecomp import snes_gsu as gsu
from retrorecomp.snes_gsu import CLEAR, GsuRom, decode, decode_bytes, traverse


def program(base, *chunks):
    """Bytes at LoROM bank 0, address `base` (>= $8000), in a 64 KiB image."""
    image = bytearray(0x10000)
    offset = base & 0x7fff
    for chunk in chunks:
        data = bytes.fromhex(chunk) if isinstance(chunk, str) else bytes(chunk)
        image[offset:offset + len(data)] = data
        offset += len(data)
    return GsuRom(bytes(image))


def pcs(result, pbr=0):
    return sorted(pc for bank, pc in result.addresses() if bank == pbr)


class DecodeTests(unittest.TestCase):
    def at(self, hexbytes, state=CLEAR, pc=0x8000):
        data = bytes.fromhex(hexbytes)
        return decode_bytes(data[0], data[1:], 0, pc, state)

    def test_operand_lengths(self):
        self.assertEqual(self.at('01').length, 1)                  # NOP
        self.assertEqual(self.at('a312').length, 2)                # IBT R3,#$12
        self.assertEqual(self.at('f3 3412').length, 3)             # IWT R3,#$1234
        self.assertEqual(self.at('0572').length, 2)                # BRA
        for alt, length in ((1, 3), (2, 3)):                       # LM / SM
            self.assertEqual(self.at('f5 0030', (alt, 0, 0, 0)).length, length)
        for alt in (1, 2):                                         # LMS / SMS
            self.assertEqual(self.at('a5 10', (alt, 0, 0, 0)).length, 2)

    def test_prefix_changes_the_decoded_instruction(self):
        self.assertEqual(self.at('5a').mnemonic, 'ADD R10')
        self.assertEqual(self.at('5a', (1, 0, 0, 0)).mnemonic, 'ADC R10')
        self.assertEqual(self.at('5b', (2, 0, 0, 0)).mnemonic, 'ADD #11')
        self.assertEqual(self.at('5b', (3, 0, 0, 0)).mnemonic, 'ADC #11')
        self.assertEqual(self.at('65', (3, 0, 0, 0)).mnemonic, 'CMP R5')
        self.assertEqual(self.at('65', (2, 0, 0, 0)).mnemonic, 'SUB #5')
        self.assertEqual(self.at('4c').mnemonic, 'PLOT')
        self.assertEqual(self.at('4c', (1, 0, 0, 0)).mnemonic, 'RPIX')
        self.assertEqual(self.at('85').mnemonic, 'MULT R5')
        self.assertEqual(self.at('85', (3, 0, 0, 0)).mnemonic, 'UMULT #5')
        self.assertEqual(self.at('9f').mnemonic, 'FMULT')
        self.assertEqual(self.at('9f', (1, 0, 0, 0)).mnemonic, 'LMULT')
        self.assertEqual([self.at('ef', (a, 0, 0, 0)).mnemonic for a in range(4)],
                         ['GETB', 'GETBH', 'GETBL', 'GETBS'])
        self.assertEqual(self.at('df', (2, 0, 0, 0)).mnemonic, 'RAMB')
        self.assertEqual(self.at('df', (3, 0, 0, 0)).mnemonic, 'ROMB')
        self.assertEqual(self.at('33', (1, 0, 0, 0)).mnemonic, 'STB (R3)')
        self.assertEqual(self.at('43').mnemonic, 'LDW (R3)')

    def test_state_machine(self):
        i = self.at('3d')                                           # ALT1
        self.assertEqual(i.next_state, (1, 0, 0, 0))
        i = self.at('3f', (1, 1, 3, 3))                             # ALT3 clears B, keeps selectors
        self.assertEqual(i.next_state, (3, 0, 3, 3))
        self.assertEqual(self.at('23').next_state, (0, 1, 3, 3))    # WITH R3
        self.assertEqual(self.at('14').next_state, (0, 0, 0, 4))    # TO R4
        self.assertEqual(self.at('b6').next_state, (0, 0, 6, 0))    # FROM R6
        move = self.at('14', (0, 1, 3, 3))                          # WITH R3 ; TO R4
        self.assertEqual(move.mnemonic, 'MOVE R4,R3')
        self.assertEqual(move.next_state, CLEAR)
        moves = self.at('b4', (0, 1, 3, 3))
        self.assertEqual(moves.mnemonic, 'MOVES R3,R4')
        self.assertEqual(self.at('01', (2, 0, 5, 5)).next_state, CLEAR)
        # Relative branches keep the prefix state; JMP and LOOP consume it.
        self.assertEqual(self.at('0510', (1, 0, 2, 2)).next_state, (1, 0, 2, 2))
        self.assertEqual(self.at('98', (0, 0, 2, 2)).next_state, CLEAR)
        self.assertEqual(self.at('3c', (0, 0, 2, 2)).next_state, CLEAR)

    def test_operand_values(self):
        self.assertEqual(self.at('a3ff').operand, 0xffff)           # IBT sign-extends
        self.assertEqual(self.at('f3 3412').operand, 0x1234)
        self.assertEqual(self.at('a5 10', (1, 0, 0, 0)).operand, 0x20)   # LMS word address
        self.assertEqual(self.at('0502').operand, 0x8004)            # target = slot + 2
        self.assertEqual(self.at('05fe').operand, 0x8000)

    def test_register_effects_and_service_tags(self):
        self.assertEqual(self.at('4c').reads, (1, 2))
        self.assertEqual(self.at('4c').writes, (1,))
        self.assertIn(gsu.TAG_PIXEL, self.at('4c').tags)
        self.assertIn(gsu.TAG_MULT, self.at('85').tags)
        self.assertIn(gsu.TAG_ROM_BUFFER, self.at('ef').tags)
        self.assertIn(gsu.TAG_RAM_BUFFER, self.at('43').tags)
        self.assertIn(gsu.TAG_CACHE, self.at('02').tags)
        # Writing R14 reloads the ROM buffer, whatever instruction writes it.
        self.assertIn(gsu.TAG_ROM_BUFFER, self.at('fe 0080').tags)
        self.assertIn(gsu.TAG_ROM_BUFFER, self.at('5a', (0, 0, 1, 14)).tags)
        self.assertNotIn(gsu.TAG_ROM_BUFFER, self.at('5a', (0, 0, 1, 13)).tags)

    def test_r15_destination_is_a_jump(self):
        self.assertEqual(self.at('ff 0090').flow, 'r15')            # IWT R15
        self.assertEqual(self.at('ff 0090').r15_imm, 0x9000)
        self.assertEqual(self.at('af 10').flow, 'r15')              # IBT R15
        self.assertEqual(self.at('5a', (0, 0, 1, 15)).flow, 'r15')  # ADD R10 with TO R15
        self.assertEqual(self.at('5a', (0, 0, 1, 14)).flow, 'seq')
        self.assertEqual(self.at('cf', (0, 0, 1, 15)).flow, 'r15')  # OR R15
        self.assertEqual(self.at('1f', (0, 1, 3, 3)).flow, 'r15')   # MOVE R15,R3
        self.assertEqual(self.at('1f').flow, 'seq')                 # TO R15 alone writes nothing
        self.assertEqual(self.at('f5 0030', (1, 0, 0, 0)).flow, 'seq')
        self.assertEqual(self.at('ff 0030', (1, 0, 0, 0)).flow, 'r15')   # LM R15
        self.assertEqual(self.at('98').flow, 'jmp')
        self.assertEqual(self.at('98', (1, 0, 0, 0)).flow, 'ljmp')
        self.assertEqual(self.at('3c').flow, 'loop')
        self.assertTrue(self.at('3c').conditional)
        self.assertFalse(self.at('05 00').conditional)
        self.assertTrue(self.at('09 00').conditional)
        self.assertEqual(self.at('00').flow, 'stop')


class RomViewTests(unittest.TestCase):
    def test_lorom_and_linear_views(self):
        data = bytearray(0x10000 * 4)                                # 256 KiB
        data[0] = 0x11
        data[0x8000] = 0x22                                          # bank 1, $8000
        data[0x10000 + 5] = 0x33                                     # linear $41:0005
        rom = GsuRom(bytes(data))
        self.assertEqual(rom.read(0x00, 0x8000), 0x11)
        self.assertEqual(rom.read(0x00, 0x0000), 0x11)               # bit 15 is ignored
        self.assertEqual(rom.read(0x01, 0x8000), 0x22)
        self.assertEqual(rom.read(0x41, 0x0005), 0x33)
        self.assertEqual(rom.read(0x40, 0x0000), 0x11)
        self.assertEqual(rom.read(0x08, 0x8000), 0x11)               # mirrored past the end
        self.assertIsNone(rom.read(0x70, 0x0000))                    # Game Pak RAM
        self.assertIsNone(rom.read(0x60, 0x8000))
        self.assertEqual(gsu.region(0x70), 'ram')
        self.assertEqual(gsu.region(0x45), 'rom-linear')
        self.assertEqual(gsu.region(0x1f), 'rom-lorom')
        self.assertEqual(gsu.region(0x65), 'void')


class TraversalTests(unittest.TestCase):
    def test_straight_line_stops_at_stop(self):
        rom = program(0x8000, '01 a312 f3 3412 00 01')
        result = traverse(rom, [(0, 0x8000)])
        self.assertEqual(pcs(result), [0x8000, 0x8001, 0x8003, 0x8006])
        self.assertEqual(result.unresolved(), [])

    def test_resume_after_stop_continues_two_bytes_later(self):
        # 8000 STOP ; 8001 NOP (consumed by the pipeline) ; 8002 INC R1 ; 8003 BRA self ; 8005 NOP (slot)
        rom = program(0x8000, '00 01 d1 05 fe 01')
        plain = traverse(rom, [(0, 0x8000)])
        self.assertEqual(pcs(plain), [0x8000])
        resumed = traverse(rom, [(0, 0x8000)], resume_after_stop=True)
        self.assertEqual(pcs(resumed), [0x8000, 0x8002, 0x8003, 0x8005])
        self.assertEqual(resumed.resume_points, {(0, 0x8002)})

    def test_relative_branch_in_a_delay_slot_reads_its_displacement_from_the_path(self):
        # Computed jump into a table of branches: `WITH R15 ; ADD R0 ; BRA .. ` where the
        # ADD (destination R15) has the BRA as its delay slot.  Observed target 8010: the BRA takes
        # its displacement from the byte at 8010 (+4) and branches to 8011 + 4 = 8015.
        image = bytearray(0x10000)
        image[0:4] = bytes.fromhex('2f 50 05 00')                    # WITH R15 ; ADD R0 ; BRA (slot) ; (operand)
        image[0x10:0x12] = bytes.fromhex('04 01')                    # 8010: disp +4 ; 8011: NOP (BRA's slot)
        image[0x15] = 0x00                                           # 8015: STOP
        result = traverse(GsuRom(bytes(image)), [(0, 0x8000)], observed={(0, 0x8001): {(0, 0x8010)}})
        self.assertIn(0x8015, pcs(result))
        self.assertEqual(result.anomalies, [])

    def test_bra_delay_slot_runs_and_skips_following_bytes(self):
        # 8000 BRA +2 ; 8002 NOP (slot) ; 8003 STOP (skipped) ; 8004 NOP ; 8005 STOP
        rom = program(0x8000, '05 02', '01', '00', '01', '00')
        result = traverse(rom, [(0, 0x8000)])
        self.assertEqual(pcs(result), [0x8000, 0x8002, 0x8004, 0x8005])
        self.assertIn((0, 0x8002, CLEAR), result.slots)

    def test_conditional_branch_follows_both_paths_after_the_slot(self):
        # 8000 BNE +2 ; 8002 NOP (slot) ; 8003 STOP (fallthrough) ; 8004 NOP ; 8005 STOP
        rom = program(0x8000, '08 02', '01', '00', '01', '00')
        result = traverse(rom, [(0, 0x8000)])
        self.assertEqual(pcs(result), [0x8000, 0x8002, 0x8003, 0x8004, 0x8005])

    def test_backward_branch_loop_terminates(self):
        # 8000 NOP ; 8001 BNE -3 (-> 8000) ; 8003 NOP ; 8004 STOP
        rom = program(0x8000, '01', '08 fd', '01', '00')
        result = traverse(rom, [(0, 0x8000)])
        self.assertEqual(pcs(result), [0x8000, 0x8001, 0x8003, 0x8004])

    def test_jmp_resolved_by_ibt_and_iwt(self):
        # IWT R8,#$8010 ; JMP R8 ; NOP (slot) ; ... ; 8010: STOP
        rom = program(0x8000, 'f8 1080', '98', '01')
        rom2 = bytearray(rom.data)
        rom2[0x10] = 0x00
        result = traverse(GsuRom(bytes(rom2)), [(0, 0x8000)])
        self.assertEqual(pcs(result), [0x8000, 0x8003, 0x8004, 0x8010])
        site = result.indirect[(0, 0x8003)]
        self.assertEqual(site.kind, 'jmp')
        self.assertEqual(site.static_targets, {(0, 0x8010)})
        self.assertEqual(result.unresolved(), [])

    def test_unresolved_jmp_uses_observed_targets(self):
        image = bytearray(0x10000)
        image[0:3] = bytes.fromhex('98 01 00')                       # JMP R8 ; NOP ; STOP
        image[0x20:0x22] = bytes.fromhex('01 00')                    # 8020: NOP ; STOP
        rom = GsuRom(bytes(image))
        plain = traverse(rom, [(0, 0x8000)])
        self.assertEqual(len(plain.unresolved()), 1)
        self.assertEqual(pcs(plain), [0x8000, 0x8001])
        seen = traverse(rom, [(0, 0x8000)], observed={(0, 0x8000): {(0, 0x8020)}})
        self.assertEqual(pcs(seen), [0x8000, 0x8001, 0x8020, 0x8021])
        self.assertEqual(seen.indirect[(0, 0x8000)].observed_targets, {(0, 0x8020)})
        self.assertEqual(len(seen.unresolved()), 1)                  # still not statically resolved

    def test_ljmp_changes_bank(self):
        image = bytearray(0x20000)
        # bank 0: IBT R9,#1 ; IWT R10,#$8000 ; FROM R10 ; ALT1 ; LJMP R9 ; NOP
        image[0:] = bytes(len(image))
        code = bytes.fromhex('a901 fa 0080 ba 3d 99 01')
        image[0:len(code)] = code
        image[0x8000] = 0x00                                         # bank 1, $8000: STOP
        result = traverse(GsuRom(bytes(image)), [(0, 0x8000)])
        self.assertIn((1, 0x8000), result.addresses())
        site = result.indirect[(0, 0x8007)]
        self.assertEqual(site.kind, 'ljmp')
        self.assertEqual(site.static_targets, {(1, 0x8000)})

    def test_iwt_r15_is_a_direct_jump_with_a_slot(self):
        # IWT R15,#$8010 ; NOP (slot) ; STOP (skipped) ; ... ; 8010: STOP
        image = bytearray(0x10000)
        image[0:5] = bytes.fromhex('ff 1080 01 00')
        image[0x10] = 0x00
        result = traverse(GsuRom(bytes(image)), [(0, 0x8000)])
        self.assertEqual(pcs(result), [0x8000, 0x8003, 0x8010])
        self.assertEqual(result.indirect[(0, 0x8000)].kind, 'r15')
        self.assertEqual(result.unresolved(), [])

    def test_loop_target_from_move_r13_r15(self):
        # 8000 IBT R12,#3 ; 8002 WITH R15 ; 8003 TO R13 (R13 = 8004) ;
        # 8004 INC R1 ; 8005 LOOP ; 8006 NOP (slot) ; 8007 STOP
        rom = program(0x8000, 'ac03', '2f', '1d', 'd1', '3c', '01', '00')
        result = traverse(rom, [(0, 0x8000)])
        site = result.indirect[(0, 0x8005)]
        self.assertEqual(site.kind, 'loop')
        self.assertEqual(site.static_targets, {(0, 0x8004)})
        self.assertEqual(pcs(result), [0x8000, 0x8002, 0x8003, 0x8004, 0x8005, 0x8006, 0x8007])
        # the prefix chain is keyed by state: the TO runs with WITH's selectors
        self.assertIn((0, 0x8003, (0, 1, 15, 15)), result.nodes)

    def test_call_and_return_through_link(self):
        # 8000 LINK #4 (R11 = 8005) ; 8001 IWT R15,#$8020 ; 8004 NOP (slot) ;
        # 8005 STOP ; 8020: JMP R11 ; 8021 NOP (slot)
        image = bytearray(0x10000)
        image[0:6] = bytes.fromhex('94 ff 2080 01 00')
        image[0x20:0x22] = bytes.fromhex('9b 01')
        result = traverse(GsuRom(bytes(image)), [(0, 0x8000)])
        self.assertEqual(result.indirect[(0, 0x8020)].static_targets, {(0, 0x8005)})
        self.assertEqual(pcs(result), [0x8000, 0x8001, 0x8004, 0x8005, 0x8020, 0x8021])

    def test_prefix_state_makes_two_nodes_for_one_address(self):
        # 8000 BEQ +2 (-> 8004) ; 8002 NOP (slot) ; 8003 ALT1 ; 8004 ADD R3 ; 8005 STOP
        # The branch path reaches the ADD with a clear state, the fall-through with ALT1.
        image = bytearray(0x10000)
        image[0:6] = bytes.fromhex('09 02 01 3d 53 00')
        result = traverse(GsuRom(bytes(image)), [(0, 0x8000)])
        states = result.prefix_states_per_address()[(0, 0x8004)]
        self.assertEqual(states, {(0, 0, 0, 0), (1, 0, 0, 0)})

    def test_multibyte_delay_slot_takes_its_operands_from_the_path_taken(self):
        # 8000 BEQ +4 (-> 8006) ; 8002 IWT R15,#$8020 (the slot) ; 8005 NOP ; 8006: 30 80 ; 8008 NOP
        # Not taken, the IWT jumps to 8020 with the NOP at 8005 as its slot.  Taken, the IWT
        # reads its address from the bytes at 8006 ($8030) and the NOP at 8008 is its slot.
        image = bytearray(0x10000)
        image[0:9] = bytes.fromhex('09 04 ff 2080 01 3080 01')
        image[0x20] = 0x00
        image[0x30] = 0x00
        result = traverse(GsuRom(bytes(image)), [(0, 0x8000)])
        self.assertEqual(pcs(result), [0x8000, 0x8002, 0x8005, 0x8008, 0x8020, 0x8030])
        self.assertEqual(result.slot_operand_sites, {(0, 0x8002)})
        self.assertEqual(result.indirect[(0, 0x8002)].static_targets, {(0, 0x8020), (0, 0x8030)})
        self.assertEqual(result.anomalies, [])

    def test_ibt_in_a_taken_delay_slot_consumes_the_first_target_byte(self):
        # 8000 BRA +1 (-> 8003) ; 8002 IBT R1,#.. (slot) ; 8003: 05 ; 8004 STOP
        # The IBT reads $05 from the target; execution resumes at 8004.
        image = bytearray(0x10000)
        image[0:6] = bytes.fromhex('05 01 a1 05 00 00')
        result = traverse(GsuRom(bytes(image)), [(0, 0x8000)])
        self.assertEqual(pcs(result), [0x8000, 0x8002, 0x8004])

    def test_code_in_game_pak_ram_is_not_followed(self):
        image = bytearray(0x10000)
        image[0:5] = bytes.fromhex('ff 0000 01 00')                  # IWT R15,#0 ... with PBR $70 below
        result = traverse(GsuRom(bytes(image)), [(0x70, 0x0000)])
        self.assertEqual(result.nodes, {})
        self.assertEqual(result.not_rom[(0x70, 0)], 'ram')

    def test_entries_may_start_with_a_prefix_state(self):
        rom = program(0x8000, '5a 00')
        result = traverse(rom, [(0, 0x8000, (1, 0, 0, 0))])
        self.assertEqual(result.nodes[(0, 0x8000, (1, 0, 0, 0))].mnemonic, 'ADC R10')

    def test_coverage_counts(self):
        rom = program(0x8000, '01 00')
        result = traverse(rom, [(0, 0x8000)])
        counts = gsu.covered_counts(result, [
            (0, 0x8000, CLEAR, 10), (0, 0x8001, CLEAR, 5),
            (0, 0x8001, (1, 0, 0, 0), 2),                            # known address, other state
            (0x70, 0x0100, CLEAR, 7)])                               # RAM
        self.assertEqual(counts['instr_total'], 24)
        self.assertEqual(counts['instr_address'], 17)
        self.assertEqual(counts['instr_state'], 15)

    def test_decode_from_rom_matches_decode_bytes(self):
        rom = program(0x8000, 'f3 3412')
        self.assertEqual(decode(rom, 0, 0x8000).operand, 0x1234)
        self.assertIsNone(decode(rom, 0x70, 0x0000))


class SurveyTests(unittest.TestCase):
    def test_survey_of_a_synthetic_dump(self):
        from tools.snes_gsu_survey import survey
        image = bytearray(0x10000)
        image[0:4] = bytes.fromhex('a102 4c 00')            # IBT R1,#2 ; PLOT ; STOP
        # An unreached routine (8100: NOP ; STOP) that the dump says ran from the cache.
        image[0x100:0x102] = bytes.fromhex('01 00')
        dump = {
            'total_instructions': 33, 'synthetic_nops': 0, 'cpu_cache_writes': 0, 'cache_fills': 2, 'cache_flushes': 1,
            'jobs': [[0x008000, 10, 10, 30, 90, 3]],
            'sync_calls_running': 4, 'sync_clock_log2': [0] * 40, 'sync_instr_log2': [0, 0, 4] + [0] * 37,
            'pcs': [[0x008000, 0, 0, 0, 0, 3, 0xa1, 10, 0x8000], [0x008002, 0, 0, 0, 0, 3, 0x4c, 10, 0x8000],
                    [0x008003, 0, 0, 0, 0, 3, 0x00, 10, 0x8000],
                    [0x008100, 0, 0, 0, 0, 3, 0x01, 1, 0x8100], [0x008101, 0, 0, 0, 0, 3, 0x00, 1, 0x8100],
                    [0x700000, 0, 0, 0, 0, 2, 0x01, 1, 0]],
            'indirect': []}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'dump.json'
            path.write_text(json.dumps(dump))
            result = survey(bytes(image), [path])
        self.assertEqual(result['instructions'], 33)
        self.assertEqual(result['jobs']['distinct_entry_points'], 1)
        self.assertEqual(result['game_pak_ram_instructions'], 1)
        self.assertEqual(result['rom_byte_mismatches'], 0)
        # 30 ROM-origin instructions run in the traversed routine, 2 in the unreached one.
        self.assertEqual(result['rom_instructions'], 32)
        self.assertEqual(result['static_from_entries']['executed_distinct_keys_missed'], 2)
        self.assertAlmostEqual(result['static_from_entries']['rom_executed_covered_by_address_percent'], 93.75)
        self.assertEqual(result['mix']['plot']['count'], 10)
        self.assertEqual(result['cache']['pcs_with_n_cbr_values'], {'1': 5})
        self.assertEqual(result['cache']['executed_under_the_pcs_most_common_cbr_percent'], 100.0)
        self.assertEqual(result['sync_windows']['instructions_per_call_share_percent']['<8'], 100.0)


if __name__ == '__main__':
    unittest.main()
