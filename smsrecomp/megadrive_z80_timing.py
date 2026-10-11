"""Nominal Z80 machine-cycle placement in the private SuperZazu copy.

Shared by fixed-operation AOT helpers and the diagnostic interpreter. This
does not model electrical BR/BG/BGACK or refresh bus pins. Strict replacements
fail closed if the pinned engine changes; the upstream checkout stays intact.
"""
from .core import ConversionError


def adapt(source):
    def replace(old, new, count=1):
        nonlocal source
        if source.count(old) != count:
            raise ConversionError(f'Pinned Z80 timing adapter changed: {old[:65]}')
        source = source.replace(old, new)

    replace('  return z->read_byte(z->userdata, addr);', '''  machine_z80_boundary();
  uint8_t value = z->read_byte(z->userdata, addr);
  rr_md_z80_tick(3); return value;''')
    replace('  z->write_byte(z->userdata, addr, val);', '''  machine_z80_boundary();
  z->write_byte(z->userdata, addr, val);
  rr_md_z80_tick(3);''')
    replace('''  return (z->read_byte(z->userdata, addr + 1) << 8) |
         z->read_byte(z->userdata, addr);''', '''  uint8_t lo = rb(z, addr);
  uint8_t hi = rb(z, (uint16_t)(addr + 1));
  return lo | ((uint16_t)hi << 8);''')
    replace('''  z->write_byte(z->userdata, addr, val & 0xFF);
  z->write_byte(z->userdata, addr + 1, val >> 8);''', '''  wb(z, addr, val & 0xFF);
  wb(z, (uint16_t)(addr + 1), val >> 8);''')
    replace('''  z->sp -= 2;
  ww(z, z->sp, val);''', '''  wb(z, --z->sp, val >> 8);
  wb(z, --z->sp, val & 0xff);''')
    replace('''  z->sp += 2;
  return rw(z, z->sp - 2);''', '''  uint8_t lo = rb(z, z->sp++);
  uint8_t hi = rb(z, z->sp++);
  return lo | ((uint16_t)hi << 8);''')
    replace('''  return rb(z, z->pc++);''', '''  uint8_t value = rb(z, z->pc); ++z->pc; return value;''')
    replace('''  z->pc += 2;
  return rw(z, z->pc - 2);''', '''  uint8_t lo = nextb(z), hi = nextb(z);
  return lo | ((uint16_t)hi << 8);''')
    # Fetches are distinct from 3T operand reads, including repeated prefixes.
    at = 'static inline uint16_t get_bc('
    helpers = '''static inline uint8_t rr_nextop(z80 *z) {
  machine_z80_boundary();
  uint8_t value = z->read_byte(z->userdata, z->pc);
  ++z->pc; rr_md_z80_tick(4); return value;
}
static inline uint8_t rr_in(z80 *z, uint8_t port) {
  machine_z80_boundary();
  uint8_t value = z->port_in(z, port); rr_md_z80_tick(4); return value;
}
static inline void rr_out(z80 *z, uint8_t port, uint8_t value) {
  machine_z80_boundary();
  z->port_out(z, port, value); rr_md_z80_tick(4);
}
static inline uint16_t rr_index(z80 *z, uint16_t base, int8_t d) {
  rr_md_z80_tick(5); return (uint16_t)(base + d);
}
static inline void rr_exchange(z80 *z, uint16_t value) {
  rr_md_z80_tick(1);
  wb(z, (uint16_t)(z->sp + 1), value >> 8);
  wb(z, z->sp, value & 0xff);
}
'''
    # Replace uses before inserting the wrapper definitions themselves.
    source = source.replace('z->port_in(z,', 'rr_in(z,').replace('z->port_out(z,', 'rr_out(z,')
    replace(at, helpers + at)
    replace('const uint8_t opcode = nextb(z);', 'const uint8_t opcode = rr_nextop(z);')
    for name in ('cb', 'ed', 'ddfd'):
        old = f'exec_opcode_{name}(z, nextb(z)'
        replace(old, f'exec_opcode_{name}(z, rr_nextop(z)', 2 if name == 'ddfd' else 1)
    replace('void z80_step(z80* const z) {', 'void z80_step(z80* const z) {\n  rr_md_z80_begin(z);')
    replace('  process_interrupts(z);', '  rr_md_z80_finish(z);')
    # HALT repeats a fetch without incrementing PC.
    replace('    exec_opcode(z, 0x00);', '''    machine_z80_boundary();
    (void)z->read_byte(z->userdata, z->pc); rr_md_z80_tick(4);
    exec_opcode(z, 0x00);''')
    replace('static inline void cond_ret(z80* const z, bool condition) {',
            'static inline void cond_ret(z80* const z, bool condition) {\n  rr_md_z80_tick(1);')
    replace('    call(z, addr);', '    rr_md_z80_tick(1); call(z, addr);')
    replace('case 0xCD: call(z, nextw(z));',
            'case 0xCD: { uint16_t addr = nextw(z); rr_md_z80_tick(1); call(z, addr); }')
    for op in (0xc7, 0xcf, 0xd7, 0xdf, 0xe7, 0xef, 0xf7, 0xff):
        replace(f'case 0x{op:02X}: call(', f'case 0x{op:02X}: rr_md_z80_tick(1); call(')
    for op in (0xc5, 0xd5, 0xe5, 0xf5):
        replace(f'case 0x{op:02X}: pushw(', f'case 0x{op:02X}: rr_md_z80_tick(1); pushw(', 2 if op == 0xe5 else 1)
    replace('case 0x10: cond_jr(', 'case 0x10: rr_md_z80_tick(1); cond_jr(')
    replace('    ww(z, z->sp, get_hl(z));', '    rr_exchange(z, get_hl(z));')
    replace('    ww(z, z->sp, *iz);', '    rr_exchange(z, *iz);')
    replace('    wb(z, get_hl(z), result);', '    rr_md_z80_tick(1); wb(z, get_hl(z), result);', 2)
    # Normal indexed memory cycles spend 5T calculating the address. DDCB and
    # LD (IX+d),n instead have their own 2T placement after the following byte.
    replace('#define IZD displace(z, *iz, nextb(z))', '#define IZD displace(z, rr_index(z, *iz, nextb(z)), 0)')
    replace('''    uint16_t addr = IZD;
    uint8_t op = nextb(z);''', '''    uint16_t addr = displace(z, *iz, nextb(z));
    uint8_t op = nextb(z); rr_md_z80_tick(2);''')
    replace('''    uint16_t addr = IZD;
    wb(z, addr, nextb(z));''', '''    uint16_t addr = displace(z, *iz, nextb(z));
    uint8_t value = nextb(z); rr_md_z80_tick(2); wb(z, addr, value);''')
    for fn in ('inc', 'dec'):
        replace(f'    wb(z, addr, {fn}(z, rb(z, addr)));',
                f'    uint8_t value = {fn}(z, rb(z, addr)); rr_md_z80_tick(1); wb(z, addr, value);')
    replace('    hl = rb(z, get_hl(z));', '    hl = rb(z, get_hl(z)); rr_md_z80_tick(1);')
    replace('  uint8_t val = rb(z, addr);', '  uint8_t val = rb(z, addr); rr_md_z80_tick(1);')
    for expr in ('(val >> 4) | (a << 4)', '(val << 4) | (a & 0xF)'):
        replace(f'    wb(z, get_hl(z), {expr});', f'    rr_md_z80_tick(4); wb(z, get_hl(z), {expr});')
    for fn in ('ini', 'outi'):
        replace(f'static void {fn}(z80* const z) {{', f'static void {fn}(z80* const z) {{\n  rr_md_z80_tick(1);')
    # Interrupt cycles follow instruction retirement. Stack writes are high
    # first; IM2 vector reads happen after stacking the return address.
    replace('    z->cyc += 11;\n    call(z, 0x66);', '    z->cyc += 11;\n    rr_md_z80_tick(5); call(z, 0x66);')
    replace('      call(z, 0x38);', '      rr_md_z80_tick(7); call(z, 0x38);')
    replace('      call(z, rw(z, (z->i << 8) | z->int_data));',
            '      rr_md_z80_tick(7); pushw(z, z->pc); jump(z, rw(z, (z->i << 8) | z->int_data));')
    return '#include "md_z80_native.h"\n' + source
