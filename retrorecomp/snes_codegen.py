"""Static ROM-PC to compiled 65816 operations for SNES cartridges.

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

from .core import ConversionError, module_fingerprint, replace_once
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


def native_source(source: str, rom: bytes, ram_variants=(), *, mapping='lorom',ram_opcodes=()) -> str:
    if mapping not in ('lorom', 'hirom'):
        raise ConversionError('SNES native lookup supports ordinary LoROM and HiROM only.')
    bus_rom = mirrored_rom(rom)
    cart_type = 'CART_LOROM' if mapping == 'lorom' else 'CART_HIROM'
    from .snes_chips import identify
    cart_type={'none':cart_type,'dsp1-lo':'CART_DSP1','dsp1-hi':'CART_DSP1_HIROM',
               'cx4':'CART_CX4','superfx':'CART_SUPERFX'}[identify(rom)]
    rom_mapping=mapping
    bodies, cycles = operation_bodies(source), cycle_costs(source)
    functions = []
    for opcode in range(256):
        functions.append(f'''static void rr_sn_op_{opcode:02x}(Interp816 *cpu) {{
    /* The core has already performed the timed opcode fetch exactly once. */
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
    from .supernintendo import valid_ram_variant,valid_ram_address
    from .snes_cart import layout_bytes
    memory = layout_bytes(rom, rom_mapping)
    ram = sorted({(item['address'],int(item['bytes'][:2],16)) for item in ram_variants
                  if valid_ram_variant(item,memory=memory)} |
                 {(pc,op) for pc,op in ram_opcodes if valid_ram_address(pc,memory=memory)
                  and type(op) is int and 0<=op<=255})
    ram_table = ('static const struct { uint32_t pc; const RrSnesNativeOp *op; } '
        'rr_sn_ram[] = {' + ','.join(f'{{{pc},&rr_sn_entry_{op:02x}}}' for pc,op in ram) + '};\n') if ram else ''
    operations = ('static const RrSnesNativeOp *const rr_sn_ops[256] = {' +
                  ','.join(f'&rr_sn_entry_{opcode:02x}' for opcode in range(256)) + '};\n')
    # The exact PC and opcode of a RAM instruction are looked up in a table indexed by the WRAM
    # byte it sits at (one load for the ordinary case). An entry holds the first bank and opcode
    # seen there; a WRAM byte reached under another bank (the low-bank mirrors) or with a second
    # observed opcode is flagged shared and sent to the binary search over `rr_sn_ram`, so both
    # paths give the same answer for every PC. Cartridge RAM code always takes the search.
    ram_search = f'''static const RrSnesNativeOp *rr_sn_ram_search(uint32_t pc, int fetched) {{
    uint8_t bytes[4];
    if (!rr_snes_read_ram_code(pc, bytes)) return NULL;
    unsigned lo=0,hi={len(ram)}u;
    while(lo<hi) {{ unsigned mid=lo+(hi-lo)/2;
        if(rr_sn_ram[mid].pc<pc) lo=mid+1; else hi=mid;
    }}
    for (unsigned i = lo; i < {len(ram)}u && rr_sn_ram[i].pc == pc; ++i)
        /* Only the observed operation is static. Its operands and M/X
         * widths are read by the compiled body through the timed bus. */
        if (bytes[0] == rr_sn_ram[i].op->opcode)
            return fetched<0 || rr_sn_ram[i].op->opcode==fetched ? rr_sn_ram[i].op : NULL;
    return NULL;
}}
static uint32_t rr_sn_wram_entry[0x20000];
static bool rr_sn_wram_filled;
static bool rr_sn_ram_mapped(uint32_t pc) {{
    for (unsigned n = 0; n < 4; ++n) {{
        uint8_t bank = (uint8_t)(pc >> 16); uint16_t address = (uint16_t)(pc + n);
        if (cpu_wram_offset(bank, address) < 0 &&
            rr_snes_cart_ram_offset(g_snes ? g_snes->cart : NULL, bank, address) < 0) return false;
    }}
    return true;
}}
static void rr_sn_wram_fill(void) {{
    if (rr_sn_wram_filled) memset(rr_sn_wram_entry, 0, sizeof rr_sn_wram_entry);
    rr_sn_wram_filled = true;
    for (unsigned i = 0; i < {len(ram)}u; ++i) {{
        uint32_t pc = rr_sn_ram[i].pc;
        int32_t offset = cpu_wram_offset((uint8_t)(pc >> 16), (uint16_t)pc);
        if (offset < 0 || !rr_sn_ram_mapped(pc)) continue;
        uint32_t entry = 0x10000u | ((pc >> 16) << 8) | rr_sn_ram[i].op->opcode;
        if (!rr_sn_wram_entry[offset]) rr_sn_wram_entry[offset] = entry;
        else if ((rr_sn_wram_entry[offset] & 0xffffu) != (entry & 0xffffu)) rr_sn_wram_entry[offset] |= 0x20000u;
    }}
}}
''' if ram else ''
    ram_lookup = '''if (!mapped) {
        int32_t offset = cpu_wram_offset((uint8_t)(pc >> 16), (uint16_t)pc);
        if (offset >= 0) {
            uint32_t entry = rr_sn_wram_entry[offset];
            if (!entry) return NULL;
            uint8_t live = g_ram[offset];
            if (((entry >> 8) & 0xffu) == (pc >> 16) && (entry & 0xffu) == live)
                return fetched<0 || live==fetched ? rr_sn_ops[live] : NULL;
            if (!(entry & 0x20000u)) return NULL;
        }
        return rr_sn_ram_search(pc, fetched);
    }''' if ram else 'if (!mapped) return NULL;'
    fill = 'rr_sn_wram_fill();' if ram else ''
    if cart_type == 'CART_SUPERFX':
        rom_ptr = '''/* The pinned loader gives Super FX boards no ROM pointer: the CPU reads ROM
     * through the GSU bus. Code lookup uses the same LoROM ($00-$3F) and linear
     * ($40-$5F) views; the fetched-opcode check below still rejects a byte the
     * GSU bus replaced while the coprocessor owns ROM. */
    uint8_t b = bank & 0x7f;
    if (b < 0x40 && adr >= 0x8000)
        return &rr_sn_cart->rom[(((uint32_t)b << 15) | (adr & 0x7fffu)) % rr_sn_cart->romSize];
    if (b >= 0x40 && b < 0x60)
        return &rr_sn_cart->rom[(((uint32_t)(b - 0x40) << 16) | adr) % rr_sn_cart->romSize];
    return NULL;'''
    else:
        rom_ptr = 'return cart_getRomPtr(rr_sn_cart, bank, adr);'
    return ('/* Generated ROM-PC operation map. LakeSnes/snesrecomp notices retained. */\n'
        '#include <string.h>\n#include "types.h"\n#include "cpu_state.h"\n#include "snes/snes.h"\n'
        '#include "snes/cart.h"\n#include "snes_cart.h"\nextern Snes *g_snes;\nextern uint8_t g_ram[0x20000];\n' +
        '\n'.join(functions) + tables + '\n' + mapping + ram_table + operations + f'''
{ram_search}static bool rr_sn_enabled, rr_sn_bound, rr_sn_active;
static Cart *rr_sn_cart;
/* The cartridge is loaded once, before the first instruction: its board, storage and image
 * length are checked here, once, not at every instruction. Call again after any change. */
bool rr_snes_native_bind(void) {{
    Cart *cart = g_snes ? g_snes->cart : NULL;
    rr_sn_bound = false; rr_sn_cart = NULL;
    if (cart && cart->type == {cart_type} && cart->romSize == {len(bus_rom)}u &&
        cart->romImageSize == {len(rom)}u) {{
        rr_sn_cart = cart; rr_sn_bound = true;
        {fill}
    }}
    rr_sn_active = rr_sn_enabled && rr_sn_bound;
    return rr_sn_bound;
}}
void rr_snes_native_set_enabled(bool enabled) {{ rr_sn_enabled = enabled; rr_sn_active = enabled && rr_sn_bound; }}
bool rr_snes_read_ram_code(uint32_t pc, uint8_t bytes[4]) {{
    for (unsigned n = 0; n < 4; ++n) {{
        int32_t offset = cpu_wram_offset((uint8_t)(pc >> 16), (uint16_t)(pc + n));
        if (offset >= 0) bytes[n] = g_ram[offset];
        else {{
            offset = rr_snes_cart_ram_offset(g_snes ? g_snes->cart : NULL,
                                             (uint8_t)(pc >> 16), (uint16_t)(pc+n));
            if (offset < 0) return false;
            bytes[n] = g_snes->cart->ram[offset];
        }}
    }}
    return true;
}}
static uint8_t *rr_sn_rom_ptr(uint8_t bank, uint16_t adr) {{
    {rom_ptr}
}}
static const RrSnesNativeOp *rr_sn_lookup(uint32_t pc, int fetched) {{
    if (!rr_sn_active) return NULL;
    uint8_t *mapped = rr_sn_rom_ptr((uint8_t)(pc>>16), (uint16_t)pc);
    {ram_lookup}
    size_t offset = (size_t)(mapped - rr_sn_cart->rom);
    if (offset >= {len(bus_rom)}u) return NULL;
    const RrSnesNativeOp *operation = rr_sn_pages[offset >> 8][offset & 255u];
    /* A modified cartridge byte never selects another compiled operation. */
    return *mapped == operation->opcode && (fetched<0 || fetched==operation->opcode) ? operation : NULL;
}}
const RrSnesNativeOp *rr_snes_native_lookup(Interp816 *cpu) {{
    return rr_sn_lookup(((uint32_t)cpu->k<<16)|cpu->pc,-1);
}}
const RrSnesNativeOp *rr_snes_native_lookup_fetched(uint32_t pc,uint8_t opcode) {{
    return rr_sn_lookup(pc,opcode);
}}
''')


def correct_software_interrupts(source: str) -> str:
    """Give BRK and COP the 65816 manual's stack, cycles and vector in both modes.

    The pinned interpreter counts a native-mode BRK as 7 cycles (the manual says 8:
    K is stacked, one cycle more than in emulation mode) and runs COP as if the CPU
    were always in native mode (in emulation mode COP does not stack K, takes 7
    cycles and vector $FFF4, not $FFE4). The operation bodies compiled natively and
    the interpreter copy written into the project both come from this one corrected
    text, so the two stay equal. Written from the manual, not from the upstream fix.
    """
    brk = '        interp816_pushByte(cpu, interp816_getFlags(cpu) | (cpu->e ? 0x10 : 0));\n'
    source = replace_once(source, brk,
        brk + '        if(!cpu->e) cpu->cyclesUsed++; // native mode: K is stacked, 8 cycles\n')
    return replace_once(source,
        '      interp816_readOpcode(cpu);\n'
        '      interp816_pushByte(cpu, cpu->k);\n'
        '      interp816_pushWord(cpu, cpu->pc);\n'
        '      interp816_pushByte(cpu, interp816_getFlags(cpu));\n'
        '      cpu->cyclesUsed++; // native mode: 1 extra cycle\n'
        '      cpu->i = true;\n'
        '      cpu->d = false;\n'
        '      cpu->k = 0;\n'
        '      cpu->pc = interp816_readWord(cpu, 0xffe4, 0xffe5);\n',
        '      interp816_readOpcode(cpu);\n'
        '      if(!cpu->e) interp816_pushByte(cpu, cpu->k);\n'
        '      interp816_pushWord(cpu, cpu->pc);\n'
        '      interp816_pushByte(cpu, interp816_getFlags(cpu));\n'
        '      if(!cpu->e) cpu->cyclesUsed++; // native mode: K is stacked, 8 cycles\n'
        '      cpu->i = true;\n'
        '      cpu->d = false;\n'
        '      cpu->k = 0;\n'
        '      cpu->pc = cpu->e\n'
        '          ? interp816_readWord(cpu, 0xfff4, 0xfff5)\n'
        '          : interp816_readWord(cpu, 0xffe4, 0xffe5);\n')


def read_core(engine: Path) -> str:
    """The pinned interpreter source with the BRK/COP correction: what both readers use."""
    return correct_software_interrupts(
        (engine / 'runner/src/snes/interp816.c').read_text(encoding='utf-8'))


def adapt_core(source: str) -> str:
    source = source.replace('#include "interp816.h"',
                            '#include "interp816.h"\n#include "snes_native_steps.h"', 1)
    marker = '  uint8_t opcode = interp816_readOpcode(cpu);'
    if source.count(marker) != 1:
        raise ConversionError('Pinned 65816 execution boundary changed.')
    context = '  g_interp816_cur_pc = _pcb;'
    if source.count(context) != 1:
        raise ConversionError('Pinned 65816 fetched-opcode context changed.')
    source = source.replace(context, context+'''
  const RrSnesNativeOp *native = rr_snes_native_lookup_fetched(_pcb,opcode);
  if (native) {
    native->execute(cpu);
    rr16_snes_note_native();
    return cpu->cyclesUsed;
  }
  rr16_snes_observe_fallback(_pcb);
''', 1)
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
    # An NMI handler may execute CLI and rely on a raster IRQ preempting it.
    # Preserve its real stack/PC and yield to the beam scheduler at that edge;
    # waiting for RTI can delay a split by a hundred lines (Axelay).
    irq='if (auto_quiescent && steps && !in.i && g_snes &&'
    if source.count(irq)!=1:
        raise ConversionError('Pinned SNES nested IRQ boundary changed.')
    source=source.replace(irq,
        'if ((auto_quiescent || (stop_on_rti && s_lle_master_deadline)) && steps && !in.i && g_snes &&',1)
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
    source = read_core(engine)
    from .supernintendo import read_ram_variants,read_ram_opcodes
    ram = read_ram_variants(rom)
    opcodes=read_ram_opcodes(rom)
    write_changed(project / 'snes_native_ops.inc', native_source(source, rom.data, ram, mapping=rom.mapping,ram_opcodes=opcodes))
    report = {'schema': 1, 'rom_sha256': rom.sha256, 'native_rom_positions': len(rom.data),
              'compiled_operations': 256,
              'mapping': rom.mapping, 'native_bus_positions': len(mirrored_rom(rom.data)),
              'guarded_ram_variants': len(ram),
              'guarded_ram_opcodes': len(opcodes),
              'semantics_sha256': hashlib.sha256(source.encode()).hexdigest(),
              'adapter_sha256': module_fingerprint(__name__)}
    atomic_json(project / 'snes-step-analysis.json', report)
    return report
