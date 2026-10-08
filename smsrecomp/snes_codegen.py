"""Static ROM-PC to compiled 65816 operations for qualified SNES cartridges.

The selected LakeSnes-derived operation bodies retain their upstream notices.
ROM positions select their operation at conversion time. Live operand reads
preserve M/X widths, bank-boundary wrapping and the existing timed bus. Covered
execution never calls the opcode-switch interpreter. RAM and changed ROM bytes
retain the counted reference fallback.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
import re

from .core import ConversionError
from .megadrive_codegen import _masked, write_changed
from .library import atomic_json


def operation_bodies(source: str) -> dict[int, str]:
    start = source.index('static void interp816_doOpcode(Interp816* cpu, uint8_t opcode) {')
    switch = source.index('switch(opcode)', start)
    masked = _masked(source)
    cursor = masked.index('{', switch) + 1
    depth, labels = 1, []
    case = re.compile(r'case\s+(0x[0-9a-fA-F]+)\s*:')
    while depth:
        match = case.match(masked, cursor) if depth == 1 else None
        if match:
            labels.append((int(match[1], 16), cursor, match.end()))
            cursor = match.end()
            continue
        depth += (masked[cursor] == '{') - (masked[cursor] == '}')
        cursor += 1
    bodies = {opcode: source[end:labels[i + 1][1] if i + 1 < len(labels) else cursor - 1].strip()
              for i, (opcode, _, end) in enumerate(labels)}
    if set(bodies) != set(range(256)):
        raise ConversionError('Pinned 65816 operation definitions changed; refusing partial translation.')
    return bodies


def cycle_costs(source: str) -> list[int]:
    block = source.split('static const int cyclesPerOpcode[256] = {', 1)[1].split('};', 1)[0]
    values = [int(value) for value in re.findall(r'\b\d+\b', _masked(block))]
    if len(values) != 256 or any(value < 1 for value in values):
        raise ConversionError('Pinned 65816 cycle table changed.')
    return values


def mirrored_rom(rom: bytes) -> bytes:
    """Match the pinned loader's power-of-two storage without changing inputs.

    Repeat the last populated block, not the entire ROM modulo its size.
    In particular, a 3 MiB image maps its final MiB again in the fourth MiB.
    """
    if not rom or len(rom) % 256:
        raise ConversionError('SNES native ROM map requires complete 256-byte pages.')
    size = max(0x8000, 1 << (len(rom) - 1).bit_length())
    data = bytearray(rom)
    block = 1
    while len(data) != size:
        if len(data) & block:
            data.extend(data[-block:])
        block <<= 1
    return bytes(data)


def native_source(source: str, rom: bytes, ram_variants=(), *, mapping='lorom') -> str:
    if mapping not in ('lorom', 'hirom'):
        raise ConversionError('SNES native lookup supports qualified LoROM and HiROM only.')
    bus_rom = mirrored_rom(rom)
    cart_type = 'CART_LOROM' if mapping == 'lorom' else 'CART_HIROM'
    bodies, cycles = operation_bodies(source), cycle_costs(source)
    functions = []
    for opcode in range(256):
        functions.append(f'''static void rr_sn_op_{opcode:02x}(Interp816 *cpu) {{
    g_interp816_cur_pc = ((uint32_t)cpu->k << 16) | cpu->pc;
    (void)interp816_readOpcode(cpu); /* preserve the opcode fetch's bus timing */
    cpu->cyclesUsed = {cycles[opcode]};
    do {{ {bodies[opcode]} }} while (0);
}}
static const RrSnesNativeOp rr_sn_entry_{opcode:02x} = {{0x{opcode:02x}, rr_sn_op_{opcode:02x}}};
''')
    pages, page_ids = [], {}
    slots = []
    for offset in range(0, len(bus_rom), 256):
        page = bytes(bus_rom[offset:offset + 256])
        if page not in page_ids:
            page_ids[page] = len(pages)
            pages.append(page)
        slots.append(page_ids[page])
    tables = '\n'.join(f'static const RrSnesNativeOp *const rr_sn_page_{i}[256] = {{\n' +
        ','.join(f'&rr_sn_entry_{opcode:02x}' for opcode in page) + '\n};'
        for i, page in enumerate(pages))
    mapping = 'static const RrSnesNativeOp *const *const rr_sn_pages[] = {' + \
              ','.join(f'rr_sn_page_{index}' for index in slots) + '};\n'
    from .supernintendo import valid_ram_variant
    ram = [item for item in ram_variants if valid_ram_variant(item)]
    ram_table = ('static const struct { uint32_t pc; uint8_t bytes[4]; const RrSnesNativeOp *op; } '
        'rr_sn_ram[] = {' + ','.join('{' + str(item['address']) + ',{' +
        ','.join(str(byte) for byte in bytes.fromhex(item['bytes'])) + '},&rr_sn_entry_' +
        item['bytes'][:2].lower() + '}' for item in ram) + '};\n') if ram else ''
    ram_lookup = f'''if (!mapped) {{
        uint8_t bytes[4];
        uint32_t pc = ((uint32_t)cpu->k << 16) | cpu->pc;
        if (!rr_snes_read_ram_code(pc, bytes)) return NULL;
        for (unsigned i = 0; i < {len(ram)}u; ++i)
            if (rr_sn_ram[i].pc == pc && !memcmp(bytes, rr_sn_ram[i].bytes, 4)) return rr_sn_ram[i].op;
        return NULL;
    }}''' if ram else 'if (!mapped) return NULL;'
    return ('/* Generated ROM-PC operation map. LakeSnes/snesrecomp notices retained. */\n'
        '#include "types.h"\n#include "cpu_state.h"\n#include "snes/snes.h"\n'
        '#include "snes/cart.h"\nextern Snes *g_snes;\nextern uint8_t g_ram[0x20000];\n' +
        '\n'.join(functions) + tables + '\n' + mapping + ram_table + f'''
static bool rr_sn_enabled;
void rr_snes_native_set_enabled(bool enabled) {{ rr_sn_enabled = enabled; }}
bool rr_snes_read_ram_code(uint32_t pc, uint8_t bytes[4]) {{
    for (unsigned n = 0; n < 4; ++n) {{
        int32_t offset = cpu_wram_offset((uint8_t)(pc >> 16), (uint16_t)(pc + n));
        if (offset < 0) return false;
        bytes[n] = g_ram[offset];
    }}
    return true;
}}
const RrSnesNativeOp *rr_snes_native_lookup(Interp816 *cpu) {{
    if (!rr_sn_enabled || !g_snes || !g_snes->cart || g_snes->cart->type != {cart_type} ||
        g_snes->cart->romSize != {len(bus_rom)}u ||
        g_snes->cart->romImageSize != {len(rom)}u) return NULL;
    uint8_t *mapped = cart_getRomPtr(g_snes->cart, cpu->k, cpu->pc);
    {ram_lookup}
    size_t offset = (size_t)(mapped - g_snes->cart->rom);
    if (offset >= {len(bus_rom)}u) return NULL;
    const RrSnesNativeOp *operation = rr_sn_pages[offset >> 8][offset & 255u];
    /* A modified cartridge byte never selects another compiled operation. */
    return *mapped == operation->opcode ? operation : NULL;
}}
''')


def adapt_core(source: str) -> str:
    source = source.replace('#include "interp816.h"',
                            '#include "interp816.h"\n#include "snes_native_steps.h"', 1)
    marker = '  uint8_t opcode = interp816_readOpcode(cpu);'
    if source.count(marker) != 1:
        raise ConversionError('Pinned 65816 execution boundary changed.')
    source = source.replace(marker, '''  const RrSnesNativeOp *native = rr_snes_native_lookup(cpu);
  if (native) {
    native->execute(cpu);
    rr16_snes_note_native();
    return cpu->cyclesUsed;
  }
''' + marker, 1)
    source = source.replace(marker, '  rr16_snes_observe_fallback(((uint32_t)cpu->k << 16) | cpu->pc);\n' + marker, 1)
    marker = '  s_interp816_insns++;'
    if source.count(marker) != 1:
        raise ConversionError('Pinned 65816 retirement boundary changed.')
    source = source.replace(marker, '  rr16_snes_note_interpreted(_pcb);\n' + marker, 1)
    return source + '\n#include "snes_native_ops.inc"\n'


def adapt_bridge(source: str) -> str:
    # The previous paired C-call route has different scheduler semantics.
    # Both the instruction AOT and reference use the real PC/stack bus route.
    marker = 'if (bounce_ok && has_body) {'
    if source.count(marker) != 1:
        raise ConversionError('Pinned 65816 call bridge changed.')
    source = source.replace(marker, 'if (0 && bounce_ok && has_body) {', 1)
    # Architectural interrupts can span a field or reach WAI after changing
    # their stack. Keep the real PC/stack and return control to the beam driver
    # at its deadline instead of running to RTI/the 250,000-step cap.
    deadline = ('        if (auto_quiescent && s_lle_master_deadline &&\n'
                '            cpu->master_cycles >= s_lle_master_deadline) {')
    waiting = ('if (auto_quiescent || yield_pc) {\n'
               '                lle_resume_set(((uint32_t)in.k << 16) | in.pc, INTERP_RESUME_SITE_WAI, in.sp);')
    if source.count(deadline) != 1 or source.count(waiting) != 1:
        raise ConversionError('Pinned SNES interrupt deadline/WAI boundary changed.')
    source = source.replace(deadline, deadline.replace('auto_quiescent &&',
        '(auto_quiescent || stop_on_rti) &&'), 1)
    source = source.replace(waiting, waiting.replace('auto_quiescent || yield_pc',
        'auto_quiescent || yield_pc || (stop_on_rti && s_lle_master_deadline)'), 1)
    # RTI may restore a different PC/stack: cartridges use architectural
    # interrupt frames to switch guest threads. The host must resume the
    # popped destination, not the PC it suspended before the interrupt.
    returned = '        if (stop_on_rti && op == 0x40) {\n            sync_interp_to_cpu(&in, cpu);'
    if source.count(returned) != 1:
        raise ConversionError('Pinned SNES architectural RTI boundary changed.')
    return source.replace(returned,
        '        if (stop_on_rti && op == 0x40) {\n'
        '            lle_resume_set(((uint32_t)in.k << 16) | in.pc, INTERP_RESUME_SITE_EXTERNAL, in.sp);\n'
        '            sync_interp_to_cpu(&in, cpu);', 1)


def adapt_frame_driver(source: str) -> str:
    marker = '  update_resume_pc();\n}\n\nvoid snes_beam_frame_driver_run_frame(void) {'
    if source.count(marker) != 1:
        raise ConversionError('Pinned SNES interrupt scheduler boundary changed.')
    return source.replace(marker,
        '  update_resume_pc();\n'
        '  if (interp_bridge_lle_took_wai()) s_wai_halted = true;\n'
        '}\n\nvoid snes_beam_frame_driver_run_frame(void) {', 1)


def generate(engine: Path, project: Path, rom) -> dict:
    if not rom.data or len(rom.data) % 256:
        raise ConversionError('SNES native ROM map requires complete 256-byte pages.')
    source = (engine / 'runner/src/snes/interp816.c').read_text(encoding='utf-8')
    from .supernintendo import read_ram_variants
    ram = read_ram_variants(rom)
    write_changed(project / 'snes_native_ops.inc', native_source(source, rom.data, ram, mapping=rom.mapping))
    report = {'schema': 1, 'rom_sha256': rom.sha256, 'native_rom_positions': len(rom.data),
              'compiled_operations': 256,
              'mapping': rom.mapping, 'native_bus_positions': len(mirrored_rom(rom.data)),
              'guarded_ram_variants': len(ram),
              'semantics_sha256': hashlib.sha256(source.encode()).hexdigest(),
              'adapter_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    atomic_json(project / 'snes-step-analysis.json', report)
    return report
