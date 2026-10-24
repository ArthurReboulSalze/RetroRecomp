"""Lossless, bounded numeric encodings of exact-ROM SPC700 entry guards."""
import json

SPC_FIELDS = ('spc_refs', 'spc_ranges', 'spc_bitmaps', 'spc_deltas')


def references(record):
    for pc, offset in record.get('spc_refs', ()):
        yield pc, offset
    for first, last, offset in record.get('spc_ranges', ()):
        for pc in range(first, last + 1):
            yield pc, offset
    for first, bits, offset in record.get('spc_bitmaps', ()):
        while bits:
            bit = bits & -bits
            yield first + bit.bit_length() - 1, offset
            bits ^= bit
    for offset, deltas in record.get('spc_deltas', ()):
        pc = 0
        for delta in deltas:
            pc += delta
            yield pc, offset


def validate_deltas(entries, rom_bytes):
    """Bound the encoded input and the number of reconstructed guards first."""
    if not isinstance(entries, list) or len(entries) > 262144:
        raise ValueError('Invalid SPC700 compilation deltas.')
    count = 0
    for entry in entries:
        if (not isinstance(entry, list) or len(entry) != 2
                or type(entry[0]) is not int or not 0 <= entry[0] < rom_bytes
                or not isinstance(entry[1], list) or not 1 <= len(entry[1]) <= 65536):
            raise ValueError('Invalid SPC700 compilation deltas.')
        count += len(entry[1])
        if count > 262144:
            raise ValueError('SPC700 compilation range budget exceeded.')
        pc = 0
        for index, delta in enumerate(entry[1]):
            if type(delta) is not int or not (0 if index == 0 else 1) <= delta <= 65535:
                raise ValueError('Invalid SPC700 compilation delta.')
            pc += delta
            if pc > 65535 or 0xf0 <= pc <= 0xff:
                raise ValueError('Invalid SPC700 compilation address.')
    return count


def compact(record):
    """Replace only the encoding, preserving every exact PC/ROM-offset pair."""
    blocks = {}
    for pc, offset in references(record):
        key = (offset, pc & ~31)
        blocks[key] = blocks.get(key, 0) | (1 << (pc & 31))
    if not blocks:
        return False
    encoded = [[first, bits, offset] for (offset, first), bits in sorted(blocks.items())]
    previous = {name:record[name] for name in SPC_FIELDS if name in record}
    by_offset = {}
    for (offset, first), bits in sorted(blocks.items()):
        positions = by_offset.setdefault(offset, [])
        while bits:
            bit = bits & -bits
            positions.append(first + bit.bit_length() - 1)
            bits ^= bit
    deltas = []
    for offset, positions in sorted(by_offset.items()):
        last = 0; values = []
        for pc in positions:
            values.append(pc-last); last=pc
        deltas.append([offset,values])
    size = lambda value:len(json.dumps(value, separators=(',',':')))
    candidate = min(({'spc_bitmaps':encoded}, {'spc_deltas':deltas}), key=size)
    if size(candidate) >= size(previous):
        return False
    for name in SPC_FIELDS:
        record.pop(name, None)
    record.update(candidate)
    return True
