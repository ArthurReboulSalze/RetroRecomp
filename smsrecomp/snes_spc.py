"""PC-directed AOT for mutable SPC700 sound programs.

Operation selection happens during conversion. Generated PC tables guard the
live opcode; operands still use the real APU bus. Converter-only observations
are compressed and tied to the exact cartridge. Games never persist them.
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import re
import zlib

from .core import ConversionError
from .library import atomic_json, entry_lock, library_root
from .knowledge import record_for
from .megadrive_codegen import _masked, write_changed
from .snes_codegen import cycle_costs

MASK_BYTES = 65536 * 32


def memory_file(rom):
    return library_root('snes') / rom.sha256 / 'spc-native.json'


def read_masks(rom):
    from .supernintendo import knowledge_engine
    shared = bytearray(MASK_BYTES)
    for pc, offset in record_for('snes', rom, knowledge_engine(rom)).get('spc_refs', []):
        opcode = rom.data[offset]
        shared[pc * 32 + opcode // 8] |= 1 << (opcode & 7)
    try:
        record = json.loads(memory_file(rom).read_text(encoding='utf-8'))
        if record.get('schema') != 1 or record.get('rom_sha256') != rom.sha256:
            return bytes(shared)
        raw = base64.b64decode(record['opcode_masks'], validate=True)
        stream = zlib.decompressobj()
        masks = stream.decompress(raw, MASK_BYTES + 1)
        if len(masks) != MASK_BYTES or not stream.eof or stream.unused_data:
            return bytes(shared)
        return bytes(a | b for a, b in zip(masks, shared))
    except (OSError, ValueError, TypeError, KeyError, AttributeError, zlib.error):
        return bytes(shared)


def valid_variant(item):
    return (isinstance(item, dict) and type(item.get('address')) is int and
            0 <= item['address'] <= 65535 and not 0xf0 <= item['address'] <= 0xff and
            type(item.get('opcode')) is int and 0 <= item['opcode'] <= 255)


def learn(rom, checks):
    variants = [item for check in checks for item in check.get('spc_variants', [])
                if valid_variant(item)]
    images = [bytes.fromhex(raw) for check in checks
              for raw in check.get('spc_driver_images', [])[:4]
              if isinstance(raw, str) and re.fullmatch('[0-9a-fA-F]{131072}', raw)]
    if not variants and not images:
        return 0
    path = memory_file(rom)
    with entry_lock(path.parent):
        previous = read_masks(rom)
        masks = bytearray(previous)
        for image in images:
            for pc, opcode in enumerate(image):
                if not 0xf0 <= pc <= 0xff:
                    masks[pc * 32 + opcode // 8] |= 1 << (opcode & 7)
        for item in variants:
            opcode = item['opcode']
            masks[item['address'] * 32 + opcode // 8] |= 1 << (opcode & 7)
        added = sum((new ^ old).bit_count() for new, old in zip(masks, previous))
        if added:
            atomic_json(path, {'schema': 1, 'rom_sha256': rom.sha256,
                'opcode_masks': base64.b64encode(zlib.compress(masks, 9)).decode('ascii')})
        return added


def operation_bodies(source):
    signature = 'static void spc_doOpcode(Spc* spc, uint8_t opcode) {'
    try:
        start = source.index(signature)
        masked = _masked(source)
        cursor = masked.index('{', masked.index('switch(opcode)', start)) + 1
        depth, labels = 1, []
        pattern = re.compile(r'case\s+(0x[0-9a-fA-F]+)\s*:')
        while depth:
            match = pattern.match(masked, cursor) if depth == 1 else None
            if match:
                labels.append((int(match[1], 16), cursor, match.end()))
                cursor = match.end()
                continue
            depth += (masked[cursor] == '{') - (masked[cursor] == '}')
            cursor += 1
    except (ValueError, IndexError) as error:
        raise ConversionError('Pinned SPC700 execution definitions changed.') from error
    bodies, pending = {}, []
    for i, (opcode, _, end) in enumerate(labels):
        stop = labels[i + 1][1] if i + 1 < len(labels) else cursor - 1
        pending.append(opcode)
        if masked[end:stop].strip():
            for value in pending:
                if value in bodies:
                    raise ConversionError('Duplicate pinned SPC700 operation.')
                bodies[value] = re.sub(r'\bopcode\b', f'0x{value:02x}', source[end:stop].strip())
            pending = []
    if pending or set(bodies) != set(range(256)):
        raise ConversionError('Pinned SPC700 definitions changed; refusing partial translation.')
    return bodies


def boot_bytes(source):
    try:
        block = source.split('static const uint8_t bootRom[0x40] = {', 1)[1].split('};', 1)[0]
        values = bytes(int(value, 16) for value in re.findall(r'0x[0-9a-fA-F]+', _masked(block)))
    except (ValueError, IndexError) as error:
        raise ConversionError('Pinned SPC700 boot mapping changed.') from error
    if len(values) != 64:
        raise ConversionError('Pinned SPC700 boot mapping changed.')
    return values


def native_source(source, boot, masks):
    if len(boot) != 64 or len(masks) != MASK_BYTES:
        raise ConversionError('Invalid SPC700 native address map.')
    bodies, cycles = operation_bodies(source), cycle_costs(source)
    code = ['/* Generated fixed-operation SPC700 AOT. Upstream notices retained. */']
    for opcode in range(256):
        if 'spc_doOpcode' in bodies[opcode]:
            raise ConversionError('SPC700 AOT would call the reference decoder.')
        code.append(f'''static void rr_spc_op_{opcode:02x}(Spc *spc) {{
    (void)spc_readOpcode(spc); /* exactly one real, timed bus fetch */
    spc->cyclesUsed = {cycles[opcode]};
    do {{ {bodies[opcode]} }} while (0);
}}
''')
    sets, ids, mapping = [()], {(): 0}, []
    guarded = 0
    for pc in range(65536):
        mask = int.from_bytes(masks[pc * 32:(pc + 1) * 32], 'little')
        if 0xf0 <= pc <= 0xff:
            mask = 0  # volatile I/O cannot be peeked or guarded safely
        values = []
        while mask:
            bit = mask & -mask
            values.append(bit.bit_length() - 1)
            mask ^= bit
        key = tuple(values)
        guarded += len(key)
        if key not in ids:
            ids[key] = len(sets)
            sets.append(key)
        mapping.append(ids[key])
    for index, values in enumerate(sets[1:], 1):
        code.append(f'static const RrSpcNativeOp rr_spc_set_{index}[] = {{' +
            ','.join(f'{{0x{opcode:02x},rr_spc_op_{opcode:02x}}}' for opcode in values) + '};')
    code.append('static const struct { const RrSpcNativeOp *ops; unsigned count; } rr_spc_sets[] = {{NULL,0},' +
                ','.join(f'{{rr_spc_set_{index},{len(values)}}}' for index, values in enumerate(sets[1:], 1)) + '};')
    code.append('static const uint16_t rr_spc_pc_sets[65536] = {' +
                ',\n'.join(','.join(map(str, mapping[i:i + 32])) for i in range(0, 65536, 32)) + '};')
    code.append('static const RrSpcNativeOp rr_spc_boot[64] = {' +
                ','.join(f'{{0x{opcode:02x},rr_spc_op_{opcode:02x}}}' for opcode in boot) + '};')
    code.append('''const RrSpcNativeOp *rr_spc_native_lookup(Spc *spc) {
    if (!rr_spc_native_enabled()) return NULL;
    if (spc->apu->romReadable && spc->pc >= 0xffc0) return &rr_spc_boot[spc->pc - 0xffc0];
    unsigned id = rr_spc_pc_sets[spc->pc];
    if (!id) return NULL;
    uint8_t opcode = spc->apu->ram[spc->pc]; /* side-effect-free guard */
    for (unsigned n = 0; n < rr_spc_sets[id].count; ++n)
        if (rr_spc_sets[id].ops[n].opcode == opcode) return rr_spc_sets[id].ops + n;
    return NULL;
}
''')
    return '\n'.join(code) + '\n', guarded


def adapt_core(source):
    marker = 'int spc_runOpcode(Spc* spc) {'
    if source.count(marker) != 1 or source.count('#include "spc.h"') != 1:
        raise ConversionError('Pinned SPC700 execution boundary changed.')
    source = source.replace('#include "spc.h"', '#include "spc.h"\n#include "snes_spc_native.h"', 1)
    return source.replace(marker, 'int rr_spc_reference_step(Spc* spc) {', 1) + '\n#include "snes_spc_ops.inc"\n'


def adapt_audio_reset(source):
    markers = ('static void rtl_reset_audio_delivery(void) {',
               'static int16 s_render_hold_l;', 'static int16 s_render_hold_r;')
    if any(source.count(marker) != 1 for marker in markers):
        raise ConversionError('Pinned SNES audio-delivery reset contract changed.')
    # Upstream keeps the previous output as a fade anchor when loading a
    # guest snapshot. A new boot/restart must not replay that old sound tail.
    return source + '''\nvoid rr_snes_reset_audio_delivery(void) {
  rtl_reset_audio_delivery();
  s_render_hold_l = 0;
  s_render_hold_r = 0;
}
'''


def generate(engine: Path, project: Path, rom):
    source = (engine / 'runner/src/snes/spc.c').read_text(encoding='utf-8')
    boot = boot_bytes((engine / 'runner/src/snes/apu.c').read_text(encoding='utf-8'))
    masks = read_masks(rom)
    code, guarded = native_source(source, boot, masks)
    write_changed(project / 'snes_spc_ops.inc', code)
    addresses = sum(any(masks[pc * 32:(pc + 1) * 32]) for pc in range(65536) if not 0xf0 <= pc <= 0xff)
    report = {'schema': 1, 'rom_sha256': rom.sha256, 'guarded_ram_variants': guarded,
        'guarded_ram_addresses': addresses,
        'boot_positions': 64, 'compiled_operations': 256, 'runtime_opcode_decoder': False,
        'mutable_operands': True, 'semantics_sha256': hashlib.sha256(source.encode()).hexdigest(),
        'adapter_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    atomic_json(project / 'spc-native-analysis.json', report)
    return report
