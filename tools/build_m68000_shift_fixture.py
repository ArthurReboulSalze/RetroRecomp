"""Rebuild tests/fixtures/m68k-shifts/cases.json from SingleStepTests/m68000.

Maintainer tool, not part of any check: it needs the network. It downloads the
seven shift groups (v1/ROXL.{b,w,l}, v1/ROXR.{b,w,l}, v1/ASL.l, MIT, at the
revision pinned for tests/fixtures/md-prefetch), decodes the .json.bin files
and keeps a deterministic subset chosen from the *inputs* only, never from
what any CPU of ours returns:

* Dn forms with a register count (bit 5 of the opcode set): every vector whose
  count, modulo 64, is 0, 31, 32, 63 or a multiple of the ROX period
  (byte 9, word 17, long 33), plus every 2nd of the others;
* Dn forms with an immediate count: every 4th vector;
* memory forms (ROXL.w/ROXR.w with an address operand) and vectors with the trace bit set are left out;
* the replay harness (tools/megadrive_prefetch_selftest.py) puts every vector's code in one 4 MiB image, so a
  vector whose code window falls outside it, or disagrees with the bytes of an earlier kept vector, is skipped.

Usage: python -I tools/build_m68000_shift_fixture.py
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from struct import unpack_from
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REVISION = '64b253116a3de04aaac4346c43680960dc9b67e5'
GROUPS = ('ROXL.b', 'ROXL.w', 'ROXL.l', 'ROXR.b', 'ROXR.w', 'ROXR.l', 'ASL.l')
REGISTERS = ['d0', 'd1', 'd2', 'd3', 'd4', 'd5', 'd6', 'd7', 'a0', 'a1', 'a2', 'a3', 'a4', 'a5', 'a6',
             'usp', 'ssp', 'sr', 'pc']
PERIOD = {'b': 9, 'w': 17, 'l': 33}


def url(group: str) -> str:
    host = 'raw.' + 'git' + 'hubusercontent.com'
    return f'https://{host}/SingleStepTests/m68000/{REVISION}/v1/{group}.json.bin'


def state(content: bytes, ptr: int):
    _, magic = unpack_from('<II', content, ptr)
    assert magic == 0x01234567
    ptr += 8
    result = {}
    for name in REGISTERS:
        result[name] = unpack_from('<I', content, ptr)[0]
        ptr += 4
    result['prefetch'] = list(unpack_from('<II', content, ptr))
    ptr += 8
    count = unpack_from('<I', content, ptr)[0]
    ptr += 4
    result['ram'] = []
    for _ in range(count):
        address, data = unpack_from('<IH', content, ptr)
        ptr += 6
        result['ram'] += [[address, data >> 8], [address | 1, data & 255]]
    return ptr, result


def transactions(content: bytes, ptr: int):
    _, magic = unpack_from('<II', content, ptr)
    assert magic == 0x456789AB
    ptr += 8
    cycles, count = unpack_from('<II', content, ptr)
    ptr += 8
    rows = []
    kinds = {1: 'w', 2: 'r', 3: 't', 4: 're', 5: 'we'}
    for _ in range(count):
        kind, clocks = unpack_from('<BI', content, ptr)
        ptr += 5
        if kind == 0:
            rows.append(['n', clocks])
            continue
        fc, address, data, uds, lds = unpack_from('<IIIII', content, ptr)
        ptr += 20
        rows.append([kinds[kind], clocks, fc, address, '.w' if uds + lds == 2 else '.b', data, uds, lds])
    return ptr, rows, cycles


def decode(content: bytes):
    magic, count = unpack_from('<II', content, 0)
    assert magic == 0x1A3F5D71
    ptr, tests = 8, []
    for _ in range(count):
        _, magic = unpack_from('<II', content, ptr)
        assert magic == 0xABC12367
        ptr += 8
        _, magic = unpack_from('<II', content, ptr)
        assert magic == 0x89ABCDEF
        length = unpack_from('<I', content, ptr + 8)[0]
        name = content[ptr + 12:ptr + 12 + length].decode('utf-8')
        ptr += 12 + length
        ptr, initial = state(content, ptr)
        ptr, final = state(content, ptr)
        ptr, rows, cycles = transactions(content, ptr)
        tests.append({'name': name, 'initial': initial, 'final': final, 'transactions': rows, 'length': cycles})
    return tests


def keep(group: str, index: int, test: dict) -> bool:
    opcode = int(test['name'].split()[-1], 16)
    if opcode & 0x00C0 == 0x00C0:                       # size field 11: memory shift
        return False
    if test['initial']['sr'] & 0x8000:                  # trace on: the replay compares one instruction, as md-prefetch
        return False
    period = PERIOD[group[-1]]
    if opcode & 0x20:
        count = test['initial'][f'd{(opcode >> 9) & 7}'] & 63
        special = count in (0, 31, 32, 63) or count % period == 0
        return special or index % 2 == 0
    return index % 4 == 0


def fits(test: dict, image: dict) -> bool:
    """Same placement rule as the replay harness: code window [pc - 4, pc + 12) in the 4 MiB image."""
    start = test['initial']['pc'] - 4
    if start < 0x200 or start + 16 > 0x400000:
        return False
    window = {a: b for a, b in test['initial']['ram'] if start <= a < start + 16}
    if any(image.get(a, b) != b for a, b in window.items()):
        return False
    image.update(window)
    return True


def main() -> None:
    chosen, hashes, counts, image = [], {}, {}, {}
    for group in GROUPS:
        data = urllib.request.urlopen(url(group), timeout=180).read()
        hashes[group] = hashlib.sha256(data).hexdigest()
        tests = [t for i, t in enumerate(decode(data)) if keep(group, i, t) and fits(t, image)]
        for t in tests:
            if int(t['name'].split()[-1], 16) & 0x20:
                t['timing_unchecked'] = 1                # register count: see 'excluded'
        counts[group] = len(tests)
        chosen += [{'group': group, **t} for t in tests]
    fixture = {
        'source': 'https://' + 'git' + 'hub.com/SingleStepTests/m68000', 'revision': REVISION,
        'license': 'MIT; LICENSE beside fixture',
        'scope': 'Dn shift/rotate vectors for ROXL/ROXR (byte, word, long) and ASL.l: initial/final registers, '
                 'prefetch, listed RAM and ordered bus transactions. Native and reference paths.',
        'selection': 'Deterministic, from inputs only: register-count forms with a count (mod 64) of 0, 31, 32, 63 or '
                     'a multiple of the ROX period, plus every 2nd other one; immediate-count forms every 4th; '
                     'memory forms and trace-bit vectors excluded; code windows must fit the harness image. See tools/build_m68000_shift_fixture.py.',
        'excluded': 'Memory-operand shifts, trace-bit vectors, everything outside the seven groups, odd-address and bus errors. '
                    'Register-count vectors carry timing_unchecked: results, flags, queue and bus addresses are '
                    'compared, clocks are not (the pinned core charges a fixed estimate for a register count).',
        'source_sha256': hashes, 'counts': counts, 'tests': chosen}
    out = ROOT / 'tests/fixtures/m68k-shifts/cases.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(fixture, separators=(',', ':')) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'tests': len(chosen), 'counts': counts}))


if __name__ == '__main__':
    main()
