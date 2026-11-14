"""The common part of the 68000 computers' shared paths (retrorecomp/m68k_media_knowledge.py): RAM code tied to positions in the player's own
media, firmware instructions tied to a firmware image of a stated SHA-256. Numbers only. No ROM, disk, install or firmware is involved:
every image below is authored.

The X68000's module was cut out of `x68_knowledge` on 14 November 2026 (the Amiga and the Atari ST use the same code). Its outcomes must not
move by a byte: `X68000_OUTCOMES` is the SHA-256 of what the module before the cut gave on the deterministic scenarios below (records,
counts, merges, rebuilds, expansions, the guidance a conversion receives and every refusal's words), computed on that module and pinned.
"""
import hashlib
import json
import random
import unittest

from retrorecomp import x68_knowledge

# What `x68_outcomes()` gave on retrorecomp/x68_knowledge.py of main 9f9e9ce9 (the module before the cut).
X68000_OUTCOMES = '59729b75e860a0baaaaa32a0bd9b203790baba24769d6ad083fe301387279a5c'

PROGRAM_WORDS = (bytes.fromhex('303c1234'), bytes.fromhex('4e71'), bytes.fromhex('203c11223344'), bytes.fromhex('4e75'),
                 bytes.fromhex('61001234'), bytes.fromhex('48e7fffe'), bytes.fromhex('4cdf7fff'), bytes.fromhex('d0410000')[:2],
                 bytes.fromhex('3200'), bytes.fromhex('4e5e'), bytes.fromhex('6600fff0'), bytes.fromhex('2f08'))


def _program(rng, count):
    """A run of `count` instructions picked from PROGRAM_WORDS (each one complete by the word-count table)."""
    return [rng.choice(PROGRAM_WORDS) for _ in range(count)]


def _scenario(seed):
    """An authored disk with programs at known places, an IPL of instruction words, and observations: runs found in the disk, runs that
    are not (private), short coincidences, malformed rows, rows outside RAM, and IPL entries."""
    rng = random.Random(seed)
    disk = bytearray(b'\x00\x01' * rng.randrange(0x1000, 0x4000))
    variants, placed = [], []
    for n in range(rng.randrange(3, 9)):
        program = _program(rng, rng.randrange(1, 12))
        blob = b''.join(program)
        offset = rng.randrange(0x100, len(disk) - len(blob) - 2) & ~1
        disk[offset:offset + len(blob)] = blob
        pc = rng.randrange(0x1000, 0xbf0000) & ~1
        placed.append((pc, offset, blob))
        cut = rng.randrange(0, 3)          # sometimes the run is observed in part, or with a changed instruction in the middle
        for raw in program[:len(program) - cut]:
            variants.append({'pc': pc, 'words': raw.hex(), 'hits': 1})
            pc += len(raw)
        if n % 3 == 1:
            variants.append({'pc': pc, 'words': '61001234', 'hits': 1})
    variants += [{'pc': 0x3001, 'words': '4e71'}, {'pc': 'x', 'words': '4e71'}, {'pc': 0x4000, 'words': '4e'}, {'pc': 0x4002, 'words': 'zz71'},
                 {'pc': 0xe00000, 'words': '4e71'}, {'pc': 0x5000, 'words': '303c'}, 'not a row']
    ipl = bytearray(b'\x4e\x71' * (128 * 1024 // 2))
    entries = []
    for at in range(0x100, 0x100 + 2 * rng.randrange(2, 20), 2):
        ipl[at:at + 2] = bytes.fromhex('4e75')
        entries.append([at, 1])
    spans = [{'source': 'ipl', 'sha256': hashlib.sha256(bytes(ipl)).hexdigest(), 'address': 0xfc0000, 'offset': 0, 'length': 128 * 1024,
              'entries': entries}, {'source': 'other'}, 'junk']
    return bytes(disk), bytes(ipl), variants, spans


def _words(error):
    return f'{type(error).__name__}: {error}'


def _broken_records(record):
    """Records that lie, each mutation named, and the words each refusal gives."""
    def mutated(change):
        copy = json.loads(json.dumps(record))
        change(copy)
        return copy
    cases = {
        'format 9': lambda r: r['identity']['layout'].update(format=9),
        'other machine': lambda r: r.update(game='md:' + '6' * 64),
        'layout': lambda r: r['identity'].update(layout={'format': 1, 'x': 1}),
        'no disk': lambda r: r['identity']['sources'].pop('disk'),
        'no sha': lambda r: r['identity']['sources']['disk'].pop('sha256'),
        'ipl size': lambda r: r['identity']['sources'].setdefault('ipl', {'bytes': 5, 'sha256': '0' * 64}).update(bytes=5),
        'devices': lambda r: r.update(devices={'x': {}}),
        'cpu': lambda r: r['cpus'].update(z80={}),
        'paths kind': lambda r: r['cpus']['m68k']['paths'].update(other=[]),
        'not a dict': lambda r: r.clear(),
    }
    out = {}
    for name, change in cases.items():
        try:
            x68_knowledge.validate_record(mutated(change), '6' * 64)
            out[name] = 'accepted'
        except ValueError as error:
            out[name] = _words(error)
    for name, bad in (('identity', ('7' * 64)), ('none', None)):
        try:
            x68_knowledge.validate_record(record, bad)
            out[name] = 'accepted'
        except ValueError as error:
            out[name] = _words(error)
    return out


def x68_outcomes():
    """Every outcome of the X68000 module on the scenarios, as one canonical JSON text."""
    identity = '6' * 64
    out = []
    for seed in range(12):
        disk, ipl, variants, spans = _scenario(seed)
        span_rows, ipl_rows, counts = x68_knowledge.translate(disk, ipl, variants, spans)
        record, promotion = x68_knowledge.promote(identity, disk, ipl, variants, spans)
        plain, _ = x68_knowledge.promote(identity, disk, None, variants[: len(variants) // 2], [])
        merged = x68_knowledge.merged(identity, plain, record)
        merged_other_way = x68_knowledge.merged(identity, record, plain)
        kept, kept_counts = x68_knowledge.promote(identity, disk, ipl, variants[:3], spans, previous=record)
        expanded, left = x68_knowledge.expanded_rows(record, disk, ipl)
        expanded_other_ipl = x68_knowledge.expanded_rows(record, disk, bytes(128 * 1024))[1]
        guidance = x68_knowledge.shared_rows(identity, disk, ipl, qualified=record, imported=plain, library=kept)
        stale = json.loads(json.dumps(record))
        stale['cpus']['m68k']['core'] = '0' * 40
        guidance_stale = x68_knowledge.shared_rows(identity, disk, ipl, qualified=stale, imported=None)
        other_disk = x68_knowledge.shared_rows(identity, disk + b'\x00\x00', ipl, imported=record)[1]
        hints = x68_knowledge.entry_set(record)
        rebuilt = x68_knowledge.rebuild(record, set(sorted(hints)[: len(hints) // 2]))
        try:
            x68_knowledge.expanded_rows(record, disk[:-2], ipl)
            other = 'expanded'
        except ValueError as error:
            other = _words(error)
        out.append({'seed': seed, 'translate': [span_rows, ipl_rows, counts], 'record': record, 'promotion': promotion, 'plain': plain,
                    'merged': merged, 'merged_other_way': merged_other_way, 'kept': kept, 'kept_counts': kept_counts,
                    'expanded': expanded, 'left': left, 'left_other_ipl': expanded_other_ipl, 'guidance': guidance,
                    'guidance_stale': guidance_stale, 'other_disk': other_disk, 'entry_set': sorted(hints), 'rebuilt': rebuilt,
                    'digest': x68_knowledge.record_digest(record), 'same_images': x68_knowledge.same_images(record, plain),
                    'salvaged': x68_knowledge.salvaged_record(identity, record) == record,
                    'salvaged_broken': x68_knowledge.salvaged_record(identity, {'game': 'x'}),
                    'refusals': _broken_records(record), 'other_disk_expand': other,
                    'facts': x68_knowledge.source_facts(disk, ipl), 'engine_of': x68_knowledge.record_engine(record) == x68_knowledge.engine()})
    return json.dumps(out, sort_keys=True, separators=(',', ':'), default=list)


class ReceivedUseTests(unittest.TestCase):
    def test_received_paths_are_counted_as_offered_reached_by_the_routes_and_added_by_the_paths_alone(self):
        from retrorecomp.m68k_media_knowledge import received_use
        received = {(0x1000, '4e71'), (0x1002, '4e75'), ('firmware', 0xfc0100)}
        own = {(0x1000, '4e71'), (0x2000, '4e71'), ('firmware', 0xfc0100)}
        self.assertEqual(received_use(received, own), {'offered': 3, 'reached': 2, 'added': 1})
        self.assertEqual(received_use((), own), {'offered': 0, 'reached': 0, 'added': 0})


class X68000OutcomesTests(unittest.TestCase):
    def test_the_x68000_outcomes_are_those_of_the_module_before_the_cut(self):
        self.assertEqual(hashlib.sha256(x68_outcomes().encode('ascii')).hexdigest(), X68000_OUTCOMES)


if __name__ == '__main__':
    unittest.main()
