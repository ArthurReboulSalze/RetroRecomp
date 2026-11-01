"""Rebuild tests/fixtures/m68k-groups/cases.json from SingleStepTests/m68000: the instruction groups no other fixture has.

Maintainer tool, not part of any check: it needs the network. It downloads each group listed in GROUPS (v1/<group>.json.bin,
MIT, at the revision pinned for tests/fixtures/md-prefetch), decodes it with the reader of tools/build_m68000_shift_fixture.py
(imported, not copied) and keeps a deterministic subset chosen from the *inputs* only, never from what any CPU of ours returns:

* vectors with the trace bit set, with a bus or address error (a transaction of kind `re` or `we`) or whose code window falls
  outside the replay image (the harness of tools/megadrive_prefetch_selftest.py puts every vector's code in one 4 MiB image) are
  left out first; of the others every STRIDE-th is kept, in file order;
* for the register-count shifts and rotates the vectors whose count, modulo 64, is 0, 31, 32 or 63 are kept as well; memory
  forms (size field 11) are left out, as in tests/fixtures/m68k-shifts;
* a vector whose code disagrees with the bytes of an earlier kept vector is skipped.

The groups are the ones of the repository's other fixtures left out (md-prefetch, md-exceptions, m68k-shifts), and TAS, TRAPV
and RESET, which the other fixtures list as excluded. Usage: python -I tools/build_m68000_groups_fixture.py
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.build_m68000_shift_fixture import REVISION, decode, fits, url

STRIDE = 8
GROUPS = tuple('''ABCD ADD.b ADD.l ADDA.l ADDA.w ADDX.b ADDX.l ADDX.w AND.b AND.l AND.w ANDItoCCR ASL.b ASL.w ASR.b ASR.l ASR.w
BCHG BCLR BSET BTST CLR.b CLR.l CMP.b CMP.l CMP.w CMPA.l CMPA.w EOR.b EOR.l EOR.w EORItoCCR EXG EXT.l EXT.w LINK LSL.b LSL.l
LSL.w LSR.b LSR.l LSR.w MOVE.q MOVEA.l MOVEA.w MOVEP.l MOVEP.w MOVEtoCCR NBCD NEG.b NEG.l NEG.w NEGX.b NEGX.l NEGX.w NOT.b NOT.l
NOT.w OR.b OR.l OR.w ORItoCCR ROL.b ROL.l ROL.w ROR.b ROR.l ROR.w RTR RTS SBCD SUB.b SUB.l SUB.w SUBA.l SUBA.w SUBX.b SUBX.l
SUBX.w SWAP Scc TST.b TST.l TST.w UNLINK'''.split())
SHIFTS = ('ASL', 'ASR', 'LSL', 'LSR', 'ROL', 'ROR')
# The Motorola manual leaves the overflow flag (V, bit 1 of the SR) undefined for the decimal instructions.
UNDEFINED_V = ('ABCD', 'SBCD', 'NBCD')


def eligible(test: dict) -> bool:
    start = test['initial']['pc'] - 4
    return (not test['initial']['sr'] & 0x8000 and not any(row[0] in ('re', 'we') for row in test['transactions'])
            and 0x200 <= start and start + 16 <= 0x400000)


def wanted(group: str, test: dict, rank: int) -> bool:
    opcode = int(test['name'].split()[-1], 16)
    if group[:3] in SHIFTS and opcode & 0x00C0 == 0x00C0:        # memory shift: not in this fixture
        return False
    if group[:3] in SHIFTS and opcode & 0x20 and (test['initial'][f'd{(opcode >> 9) & 7}'] & 63) in (0, 31, 32, 63):
        return True
    return rank % STRIDE == 0


def main() -> None:
    chosen, hashes, counts, image = [], {}, {}, {}
    for group in GROUPS:
        data = urllib.request.urlopen(url(group), timeout=180).read()
        hashes[group] = hashlib.sha256(data).hexdigest()
        pool = [test for test in decode(data) if eligible(test)]
        tests = [test for rank, test in enumerate(pool) if wanted(group, test, rank) and fits(test, image)]
        counts[group] = len(tests)
        chosen += [{'group': group, **test, **({'sr_mask': 0xFFFF & ~0x0002} if group in UNDEFINED_V else {})} for test in tests]
    fixture = {
        'source': 'https://' + 'git' + 'hub.com/SingleStepTests/m68000', 'revision': REVISION,
        'license': 'MIT; LICENSE beside fixture',
        'scope': 'Initial/final registers, RAM and queue; ordered bus address/data/lanes and clock per transaction, for the '
                 f'{len(GROUPS)} instruction groups the other fixtures do not hold. Native and reference paths.',
        'selection': f'Deterministic, from inputs only: of the vectors without the trace bit, without a bus or address error and '
                     f'whose code fits the harness image, every {STRIDE}th in file order; register-count shifts and rotates also '
                     'those with a count (mod 64) of 0, 31, 32 or 63. See tools/build_m68000_groups_fixture.py.',
        'excluded': 'Odd-address and bus errors, trace-bit vectors, memory-operand shifts, TAS, TRAPV, RESET, the groups of the '
                    'other fixtures and later CPUs. FC retained but not routed or compared. Undefined flags are masked where '
                    'the Motorola manual leaves them undefined (sr_mask).',
        'source_sha256': hashes, 'counts': counts, 'tests': chosen}
    out = ROOT / 'tests/fixtures/m68k-groups/cases.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(fixture, separators=(',', ':')) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'tests': len(chosen), 'counts': counts}))


if __name__ == '__main__':
    main()
