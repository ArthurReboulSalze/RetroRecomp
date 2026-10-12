"""Observed NES RAM entry/opcode guards, scoped to the exact cartridge.

Only opcodes already represented in this ROM's AOT bodies are eligible.
Operands are always read from the live bus, so changing an operand needs no
new variant. Shared hints reference an opcode byte in the original PRG ROM;
they contain neither an executable RAM dump nor a generated game image.
"""
from pathlib import Path
import hashlib
import json
import re

from .core import ConversionError

MAX_GUARDS = 65536
RAM_SITE = re.compile(r'^# ram:([0-9A-Fa-f]{1,4}):([0-9A-Fa-f]{1,2})$')


def valid_pc(pc: int) -> bool:
    return 0 <= pc < 0x2000 or 0x6000 <= pc <= 0xFFFF


def read_sites(path: Path) -> set[tuple[int, int]]:
    try:
        if path.stat().st_size > 16 * 1024 * 1024:
            raise ConversionError('NES entry trace exceeds its size limit.')
        entries = set()
        for line in path.read_text(encoding='ascii').splitlines():
            if match := RAM_SITE.fullmatch(line):
                pc, op = (int(value, 16) for value in match.groups())
                if valid_pc(pc): entries.add((pc, op))
        if len(entries) > MAX_GUARDS:
            raise ConversionError('Too many NES guarded RAM entry variants.')
        return entries
    except FileNotFoundError:
        return set()


def opcode_sources(rom) -> dict[int, int]:
    from .nes import _nes_size
    data = rom.data; header = data[:16]
    start = 16 + (512 if header[6] & 4 else 0)
    size = _nes_size(header[4], header[9] & 15, 16384) if rom.nes2 else header[4] * 16384
    result = {}
    for offset in range(start, start + size):
        result.setdefault(data[offset], offset)
        if len(result) == 256: break
    return result


def shared_sites(rom, record: dict) -> set[tuple[int, int]]:
    sources = opcode_sources(rom)
    start = 16 + (512 if rom.data[6] & 4 else 0)
    end = start + (_prg_size(rom))
    return {(pc, rom.data[offset]) for pc, offset in record.get('ram_opcode_refs', [])
            if valid_pc(pc) and start <= offset < end and rom.data[offset] in sources}


def _prg_size(rom) -> int:
    from .nes import _nes_size
    return _nes_size(rom.data[4], rom.data[9] & 15, 16384) if rom.nes2 else rom.data[4] * 16384


def trace_text(rom_entries, ram_entries) -> str:
    return (''.join(entry + '\n' for entry in sorted(rom_entries)) +
            ''.join(f'# ram:{pc:04X}:{op:02X}\n' for pc, op in sorted(ram_entries)))


def write_guards(generated: Path, entries, rom) -> int:
    allowed = opcode_sources(rom)
    entries = sorted({(pc, op) for pc, op in entries if valid_pc(pc) and op in allowed})
    if len(entries) > MAX_GUARDS:
        raise ConversionError('Too many NES guarded RAM entry variants.')
    source = generated.read_text(encoding='utf-8')
    begin = '/* RR_NES_RAM_GUARD_BEGIN */'
    end = '/* RR_NES_RAM_GUARD_END */'
    if source.count(begin) != 1 or source.count(end) != 1:
        raise ConversionError('NES generated guard insertion point changed.')
    keys = [pc * 256 + op for pc, op in entries]
    if keys:
        guard = 'static const uint32_t ram_keys[] = {\n' + ''.join(
            f'    0x{key:06X}u,\n' for key in keys) + '};\n'
        guard += '''static bool ram_guard(uint16_t pc, uint8_t op) {
    uint32_t key = ((uint32_t)pc << 8) | op;
    unsigned lo = 0, hi = sizeof(ram_keys) / sizeof(ram_keys[0]);
    while (lo < hi) {
        unsigned mid = lo + (hi - lo) / 2;
        if (ram_keys[mid] < key) lo = mid + 1; else hi = mid;
    }
    return lo < sizeof(ram_keys) / sizeof(ram_keys[0]) && ram_keys[lo] == key;
}
'''
    else:
        guard = 'static bool ram_guard(uint16_t pc, uint8_t op) { (void)pc; (void)op; return false; }\n'
    prefix, tail = source.split(begin)
    _, suffix = tail.split(end)
    rewritten = prefix + begin + '\n' + guard + end + suffix
    if rewritten != source: generated.write_text(rewritten, encoding='utf-8')
    # The pinned configure bridge rechecks every generated source against this
    # receipt. Bind the legitimately added guards so configuration cannot
    # silently regenerate an umbrella without its RAM entries.
    stamp = generated.parent.parent / 'complete.json'
    if stamp.is_file():
        sources = sorted(generated.parent.glob('game_cyc*.c'))
        stamp.write_text(json.dumps({p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                     for p in sources}), encoding='utf-8')
    return len(keys)
