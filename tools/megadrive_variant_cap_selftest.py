"""The limits of the learned code are counted, never silent (Mega Drive, 1.7.3).

    python -B tools/megadrive_variant_cap_selftest.py

An authored cartridge (no commercial code) builds a run of `MOVEQ #1,D0` words in work RAM and calls it: every word is one distinct
RAM instruction (its address differs). The exported game records at most `megadrive.RAM_VARIANT_LIMIT` of them. Two builds:

* 1,000 words: below the limit, nothing is dropped and the counters say 0;
* 3,000 words: past it, the game's own report says how many observations and how many distinct variants did not fit, the converter's
  library holds exactly the limit (it cannot see what the game dropped), the instructions past the limit stay on the counted interpreter, and the native run still equals
  the reference run.

It shows the counters and the equality on an authored program: nothing about a real game's code, or about speed.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def cartridge(words: int) -> bytes:
    data = bytearray(32768)
    for offset, value in ((0, 0xffff00), (4, 0x200), (0x70, 0x240), (0x78, 0x240)):
        data[offset:offset + 4] = value.to_bytes(4, 'big')
    data[0x100:0x110] = b'SEGA MEGA DRIVE '
    data[0x1f0:0x1f3] = b'USA'
    code = bytes.fromhex(
        '41f9 00ff2000'              # LEA $FF2000,A0
        + '323c %04x' % (words - 1)  # MOVE.W #words-1,D1
        + '343c 7001'                # MOVE.W #$7001,D2   (MOVEQ #1,D0)
        + '30c2'                     # loop: MOVE.W D2,(A0)+
        + '51c9 fffc'                # DBRA D1,loop
        + '30fc 4e75'                # MOVE.W #$4E75,(A0)+   (RTS)
        + '4eb9 00ff2000'            # JSR $FF2000
        + '33fc 8164 00c00004'       # VDP register 1: display and vertical interrupt on
        + '4e72 2000'                # idle: STOP #$2000
        + '60fa')                    # BRA.S idle
    data[0x200:0x200 + len(code)] = code
    # The vertical interrupt writes a new colour 0 to the palette every frame, so the picture moves (the conversion refuses a still one).
    handler = bytes.fromhex('5479 00ff0000'     # ADDQ.W #2,$FF0000
                            '3039 00ff0000'     # MOVE.W $FF0000,D0
                            '0240 0eee'         # ANDI.W #$0EEE,D0
                            '23fc c0000000 00c00004'    # MOVE.L #$C0000000,$C00004   (palette write address 0)
                            '33c0 00c00000'     # MOVE.W D0,$C00000
                            '4e73')             # RTE
    data[0x240:0x240 + len(handler)] = handler
    return bytes(data)


def run(words: int, work: Path) -> dict:
    from retrorecomp import megadrive
    from retrorecomp.cartridge16 import read_megadrive_rom
    from retrorecomp.console16 import prepare16, probe16, reference_differences
    path = work / f'authored-{words}.bin'
    path.write_bytes(cartridge(words))
    rom = read_megadrive_rom(path)
    executable = prepare16(path, 'md', emit=lambda _: None)
    native = probe16(executable, work, 8, scenario=f'native-{words}')
    reference = probe16(executable, work, 8, reference=True, scenario=f'reference-{words}')
    assert not reference_differences('md', native, reference), reference_differences('md', native, reference)
    return {'words': words, 'limit': native['ram_variant_limit'], 'native': native,
            'library': megadrive.ram_variant_overflow(rom, [native])}


def main() -> int:
    from retrorecomp import megadrive
    with tempfile.TemporaryDirectory(prefix='md-cap-', dir=ROOT / '.build') as folder:
        work = Path(folder)
        below, past = run(1000, work), run(3000, work)
    limit = megadrive.RAM_VARIANT_LIMIT
    assert below['limit'] == past['limit'] == limit
    low, high = below['native'], past['native']
    assert low['ram_observation_overflows'] == 0 and low['ram_variants_dropped'] == 0 and low['ram_variants_dropped_exact'] is True
    assert below['library'] == {'limit': limit, 'known': 1001, 'dropped': 0}
    assert len(high['ram_variants']) == limit
    assert high['ram_variants_dropped'] == 3001 - limit, high['ram_variants_dropped']      # 3,000 MOVEQ words and the final RTS
    assert high['ram_observation_overflows'] >= high['ram_variants_dropped'] > 0 and high['ram_variants_dropped_exact'] is True
    assert high['ram_fallback_opcodes'] > 0 and high['interpreted_opcodes'] >= high['ram_fallback_opcodes']
    # The library only learns what the game recorded: the variants the game could not hold never reach it, which is why the
    # game's own counter exists. (The library counter is tested with a library that already holds more: tests/test_megadrive.py.)
    assert past['library'] == {'limit': limit, 'known': limit, 'dropped': 0}
    result = {'passed': True, 'limit': limit,
              'below': {'words': 1000, 'recorded': len(low['ram_variants']), 'dropped_distinct': low['ram_variants_dropped'],
                        'dropped_observations': low['ram_observation_overflows']},
              'past': {'words': 3000, 'recorded': len(high['ram_variants']), 'dropped_distinct': high['ram_variants_dropped'],
                       'dropped_observations': high['ram_observation_overflows'], 'library': past['library'],
                       'ram_fallback_opcodes': high['ram_fallback_opcodes']}}
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    sys.exit(main())
