"""Instruction AOT for mutable Mega Drive sound drivers.

Only the converter decodes opcode structure. Generated bodies have a fixed
operation, selected by PC and guarded opcode bytes. Immediate operands remain
live reads: drivers routinely rewrite sample pointers and loop counters in RAM.
No generated body calls the reference opcode decoder.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

from .core import ConversionError
from .library import atomic_json, entry_lock, library_root
from .knowledge import ram_variants as shared_ram_variants

LIMIT = 32768


def opcode_key(raw: bytes) -> tuple[int, bytes] | None:
    if len(raw) != 4:
        return None
    mask, pos = 0, 0
    while pos < 4:
        mask |= 1 << pos
        op = raw[pos]
        pos += 1
        if op in (0xcb, 0xed):
            if pos >= 4:
                return None
            mask |= 1 << pos
            break
        if op in (0xdd, 0xfd):
            if pos >= 4:
                return None
            if raw[pos] == 0xcb:
                if pos + 2 >= 4:
                    return None
                mask |= (1 << pos) | (1 << (pos + 2))
                break
            continue
        break
    else:
        return None
    return mask, bytes(value if mask & (1 << i) else 0 for i, value in enumerate(raw))


def valid_variant(item):
    if not isinstance(item, dict):
        return False
    pc, raw = item.get('address'), item.get('bytes')
    if not (type(pc) is int and 0 <= pc <= 0xffff and
            (pc < 0x4000 or pc >= 0x8000) and isinstance(raw, str) and
            re.fullmatch('[0-9a-fA-F]{8}', raw)):
        return False
    return opcode_key(bytes.fromhex(raw)) is not None


def memory_file(rom):
    return library_root('md') / rom.sha256 / 'z80-native-entries.json'


def read_variants(rom):
    from .console16 import REPOSITORIES
    shared = shared_ram_variants('md', rom, REPOSITORIES['md'][1], field='z80_refs')
    try:
        record = json.loads(memory_file(rom).read_text(encoding='utf-8'))
        if record.get('schema') != 1 or record.get('rom_sha256') != rom.sha256:
            record = {}
    except (OSError, ValueError, TypeError, AttributeError):
        record = {}
    items = [item for item in record.get('variants', []) + shared if valid_variant(item)]
    return [{'address': pc, 'bytes': raw} for pc, _, raw in normalize(items)]


def normalize(items):
    result = set()
    for item in items:
        if valid_variant(item):
            mask, raw = opcode_key(bytes.fromhex(item['bytes']))
            pc = item['address'] & 0x1fff if item['address'] < 0x4000 else item['address']
            result.add((pc, mask, raw.hex()))
    return sorted(result)[:LIMIT]


def learn_variants(rom, checks):
    found = [item for check in checks for item in check.get('z80_variants', [])]
    # Compile every position in the uploaded driver images, including paths
    # the play probe has not taken. Guards still check the live opcode; RAM
    # operands and both RAM mirrors retain their real bus behavior.
    for check in checks:
        for raw in check.get('z80_driver_images', [])[:4]:
            if not isinstance(raw, str) or not re.fullmatch('[0-9a-fA-F]{16384}', raw):
                continue
            image = bytes.fromhex(raw)
            window = image + image[:3]
            found.extend({'address': pc, 'bytes': window[pc:pc + 4].hex()} for pc in range(8192))
    if not found:
        return 0
    path = memory_file(rom)
    with entry_lock(path.parent):
        previous = normalize(read_variants(rom))
        merged = normalize([{'address': pc, 'bytes': raw} for pc, _, raw in previous] + found)
        if merged != previous:
            atomic_json(path, {'schema': 1, 'rom_sha256': rom.sha256,
                'variants': [{'address': pc, 'bytes': raw} for pc, _, raw in merged]})
        return len(set(merged) - set(previous))


def _clean(source):
    # Preserve offsets and newlines while excluding C comments from parsing.
    return re.sub(r'/\*.*?\*/|//[^\n]*',
                  lambda m: ''.join('\n' if c == '\n' else ' ' for c in m[0]),
                  source, flags=re.S)


def _function(source, name):
    match = re.search(r'\bvoid ' + name + r'\([^;]*?\)\s*\{', source)
    if not match:
        raise ConversionError(f'Pinned Z80 semantic function changed: {name}.')
    start = match.end()
    depth = 1
    for pos in range(start, len(source)):
        depth += (source[pos] == '{') - (source[pos] == '}')
        if not depth:
            return source[start:pos]
    raise ConversionError(f'Unclosed pinned Z80 semantic function: {name}.')


def _cases(body):
    begin = body.index('switch (opcode) {') + len('switch (opcode) {')
    depth, labels = 1, []
    for match in re.finditer(r'\{|\}|case\s+(0x[0-9A-Fa-f]+|\d+)\s*:|default\s*:', body[begin:]):
        token = match[0]
        if token == '{':
            depth += 1
        elif token == '}':
            depth -= 1
            if not depth:
                end = begin + match.start()
                break
        elif depth == 1:
            labels.append((int(match[1], 0) if match[1] else None,
                           begin + match.start(), begin + match.end()))
    else:
        raise ConversionError('Pinned Z80 opcode switch changed.')
    result = {}
    pending = []
    for index, (op, _, start) in enumerate(labels):
        stop = labels[index + 1][1] if index + 1 < len(labels) else end
        code = body[start:stop].strip()
        pending.append(op)
        if code:
            code = re.sub(r'\bbreak\s*;\s*$', '', code).strip()
            for value in pending:
                result[value] = code
            pending = []
    return result


class Emitter:
    def __init__(self, source):
        clean = _clean(source)
        self.source = source
        self.bodies = {name: _function(clean, 'exec_opcode' + suffix) for name, suffix in
            [('base', ''), ('index', '_ddfd'), ('cb', '_cb'), ('dcb', '_dcb'), ('ed', '_ed')]}
        self.cases = {name: _cases(self.bodies[name]) for name in ('base', 'index', 'ed')}

    def instruction(self, raw, pos=0, family='base', index=None):
        if pos >= 4:
            raise ConversionError('Z80 prefix chain exceeds the guarded instruction window.')
        op = raw[pos]
        if family == 'base':
            preamble = f'z->cyc += cyc_00[{op}]; inc_r(z);\n'
            if op in (0xcb, 0xed):
                return preamble + 'z->pc++;\n' + self.instruction(raw, pos + 1,
                    'cb' if op == 0xcb else 'ed')
            if op in (0xdd, 0xfd):
                return preamble + 'z->pc++;\n{ uint16_t *const iz = &z->' + ('ix' if op == 0xdd else 'iy') + ';\n' + \
                    self.instruction(raw, pos + 1, 'index') + '\n}'
            return preamble + self.cases['base'].get(op, self.cases['base'][None])
        if family == 'index':
            preamble = f'z->cyc += cyc_ddfd[{op}]; inc_r(z);\n'
            if op == 0xcb:
                return preamble + '{ uint16_t addr = displace(z, *iz, nextb(z)); z->pc++;\n' + \
                    self.instruction(raw, pos + 2, 'dcb') + '\n}'
            code = self.cases['index'].get(op)
            if code is None:
                code = self.instruction(raw, pos) + '\nz->r = (z->r & 0x80) | ((z->r - 1) & 0x7f);'
            code = re.sub(r'\bIZD\b', 'displace(z, *iz, nextb(z))', code)
            code = re.sub(r'\bIZH\b', '(*iz >> 8)', code)
            code = re.sub(r'\bIZL\b', '(*iz & 0xFF)', code)
            return preamble + code
        if family == 'ed':
            return f'z->cyc += cyc_ed[{op}]; inc_r(z);\n' + \
                self.cases['ed'].get(op, self.cases['ed'][None]).replace('opcode', str(op))
        # All three CB selectors are build-time literals; the native compiler
        # folds these constant switches. There is no opcode parameter/fetch.
        body = self.bodies[family]
        return re.sub(r'\bopcode\b', str(op), body)

    def helpers(self):
        head = self.source[:self.source.index('static inline void process_interrupts(')]
        head = re.sub(r'static void exec_opcode(?:_\w+)?\([^;]+;', '', head, flags=re.S)
        return head


def generate(project: Path, engine: Path, variants):
    emitter = Emitter((engine / 'runner/external/superzazu/z80.c').read_text(encoding='utf-8'))
    entries = normalize(variants)
    keys = sorted({(mask, raw) for _, mask, raw in entries})
    ids = {key: index for index, key in enumerate(keys)}
    code = '/* Fixed-operation AOT. MIT SuperZazu semantic helpers; see embedded notices. */\n'
    code += emitter.helpers() + '\n#include "md_z80_native.h"\n'
    for index, (_, raw) in enumerate(keys):
        body = emitter.instruction(bytes.fromhex(raw))
        if 'exec_opcode' in body:
            raise ConversionError('Z80 AOT body would call the opcode interpreter.')
        code += f'static void op_{index}(z80 *const z) {{ z->pc++;\n{body}\n}}\n'
    code += '\nstatic const RrMdZ80Body bodies[] = {\n'
    code += ',\n'.join(f'{{{mask},{{' + ','.join(str(b) for b in bytes.fromhex(raw)) +
                      f'}},op_{ids[mask, raw]}}}' for _, mask, raw in entries)
    if not entries:
        code += '{0,{0},NULL}'
    code += '\n};\nstatic const uint16_t offsets[65537] = {\n'
    offsets, cursor = [], 0
    for pc in range(65537):
        while cursor < len(entries) and entries[cursor][0] < pc:
            cursor += 1
        offsets.append(str(cursor))
    code += ',\n'.join(','.join(offsets[i:i + 32]) for i in range(0, len(offsets), 32))
    code += '\n};\nconst RrMdZ80Body *rr_md_z80_bodies(uint16_t pc, unsigned *count) {\n'
    code += ' if (pc < 0x4000) pc &= 0x1fff;\n'
    code += ' *count = offsets[(unsigned)pc + 1] - offsets[pc]; return bodies + offsets[pc];\n}\n'
    (project / 'md_z80_generated.c').write_text(code, encoding='utf-8')
    stats = {'guarded_positions': len(entries), 'shared_native_bodies': len(keys),
             'runtime_opcode_decoder': False, 'mutable_operands': True}
    atomic_json(project / 'z80-native-analysis.json', stats)
    return stats


def adapt_reference(source):
    # The IRQ finishing step is shared, independently of opcode execution.
    # Genesis supplies FF on IM0's interrupt data bus. Other values keep a
    # counted reference escape rather than entering an uncounted decoder.
    old = '      exec_opcode(z, z->int_data);'
    new = '''      if (z->int_data == 0xff) {
        z->cyc += cyc_00[0xff]; inc_r(z); call(z, 0x38);
      } else {
        unsigned long before = z->cyc;
        exec_opcode(z, z->int_data);
        rr_md_z80_irq_fallback(z->cyc - before);
      }'''
    if source.count(old) != 1:
        raise ConversionError('Pinned Z80 interrupt adapter changed.')
    source = '#include "md_z80_native.h"\n' + source.replace(old, new)
    return source + '''\nvoid rr_md_z80_finish(z80 *z) { process_interrupts(z); }
void rr_md_z80_halt(z80 *z) { z->cyc += 4; inc_r(z); }
'''
