"""Ordinary SNES cartridge RAM, separate from player data and quick states."""
from .cartridge16 import snes_header
from .core import ConversionError
from .gun16_runtime import replace

REPORT_FIELDS = ('sram_bytes', 'sram_battery', 'sram_mapping', 'sram_hash')
MAX_RAM_BYTES = 0x20000


def layout_bytes(data, mapping):
    header = snes_header(data)
    if not header:
        return {'bytes': 0, 'battery': False, 'mapping': mapping, 'rom_bytes': len(data)}
    offset, detected = header
    chip, exponent = data[offset+22], data[offset+24]
    if exponent > 7:
        raise ConversionError('SNES cartridge RAM above 128 KiB is not supported yet.')
    from .snes_chips import identify
    circuit=identify(data)
    size = (1 << (10+exponent)) if chip in (1, 2, 3, 5) and exponent else 0
    return {'bytes': size, 'battery': chip in (2,5) and bool(size),
            'mapping': detected, 'rom_bytes': len(data),'chip':circuit}


def layout(rom):
    return layout_bytes(rom.data, rom.mapping)


def ram_offset(memory, address):
    if not isinstance(address, int) or not 0 <= address <= 0xffffff or not memory['bytes']:
        return None
    bank, adr = address >> 16, address & 0xffff
    if bank in (0x7e, 0x7f):
        return None
    if memory.get('chip')=='dsp1-hi':
        if bank&0x7f>=0x20 and bank&0x7f<0x40 and 0x6000<=adr<0x8000:
            return (adr&0x1fff)&(memory['bytes']-1)
    elif memory['mapping'] == 'lorom':
        full = memory['rom_bytes'] <= 0x200000 and memory['bytes'] <= 0x8000
        if (0x70 <= bank < 0x7e or bank >= 0xf0) and (adr < 0x8000 or full):
            return ((bank & 15) * 0x8000 + (adr & 0x7fff)) & (memory['bytes']-1)
    elif memory['mapping'] == 'hirom':
        canonical = bank & 0x7f
        if 0x20 <= canonical < 0x40 and 0x6000 <= adr < 0x8000:
            return ((canonical & 31) * 0x2000 + (adr & 0x1fff)) & (memory['bytes']-1)
    return None


def adapt_cart(source):
    source = replace(source, '#include "cart.h"', '#include "cart.h"\n#include "snes_cart.h"\n#include "cpu_state.h"')
    old = '''      if ((((bank >= 0x70 && bank < 0x7e) || bank >= 0xf0)) &&
          adr < 0x8000 && cart->ramSize > 0) return NULL;'''
    source = replace(source, old, '      if (rr_snes_cart_ram_offset(cart,bank,adr)>=0) return NULL;')
    marker = 'static uint8_t cart_readLorom(Cart* cart, uint8_t bank, uint16_t adr) {'
    if source.count(marker) != 1:
        raise ConversionError('Pinned SNES cartridge RAM definitions changed.')
    start = source.index(marker)
    # These four definitions end the pinned file; fail closed if that changes.
    tail = source[start:]
    for marker in ('static void cart_writeLorom(', 'static uint8_t cart_readHirom(',
                   'static void cart_writeHirom(', 'bank > 0xf0', 'bank &= 0x7f;'):
        if marker not in tail:
            raise ConversionError('Pinned SNES cartridge RAM boundary changed.')
    if not tail.rstrip().endswith('}') or tail.count('static ') != 4:
        raise ConversionError('Pinned SNES cartridge RAM tail changed.')
    read = '''static uint8_t cart_read{mapping}(Cart* cart, uint8_t bank, uint16_t adr) {{
  int32_t offset=rr_snes_cart_ram_offset(cart,bank,adr);
  if(offset>=0) return cart->ram[offset];
  uint8_t *rom=cart_getRomPtr(cart,bank,adr);
  return rom ? *rom : g_cpu.open_bus;
}}
static void cart_write{mapping}(Cart* cart, uint8_t bank, uint16_t adr, uint8_t val) {{
  int32_t offset=rr_snes_cart_ram_offset(cart,bank,adr);
  if(offset>=0) cart->ram[offset]=val;
}}
'''
    return source[:start]+read.format(mapping='Lorom')+read.format(mapping='Hirom')


def adapt_loader(source):
    source='#include "retro_snes_game.h"\n'+source
    source=replace(source,'  if(used & 1) {', '''  // Input is already unheadered and has one Python-validated board mapping.
  // Do not let the loader independently guess a different header/circuit.
  used=RR_SN_HIROM ? 2 : 0;
  if(headers[used].coprocessor==0 && headers[used].chips<=2) {
    headers[used].cartType=RR_SN_HIROM ? CART_HIROM : CART_LOROM;
    headers[used].type=RR_SN_HIROM ? 1 : 0;
    if(headers[used].speed!=2 && headers[used].speed!=3)headers[used].speed=2;
  }
  if(used & 1) {''')
    return replace(source, '    cart_ram_size = headers[used].chips > 0 ? headers[used].ramSize : 0;',
        '    cart_ram_size = headers[used].chips > 0 && headers[used].ramSize > 1024 ? headers[used].ramSize : 0;')


def adapt_cpu(source):
    source=replace(source,'''    /* ROM read. RomPtr requires the global g_rom pointer to be live. */
    return cpu_latch_read8(cpu, *RomPtr(((uint32)bank << 16) | addr));''', '''    // A decoded cartridge hole is open bus, not an off-rails ROM pointer.
    // The device and SRAM windows above have already handled driven reads.
    uint8_t *rom=g_snes ? cart_getRomPtr(g_snes->cart,bank,addr) : NULL;
    return rom ? cpu_latch_read8(cpu,*rom) : cpu->open_bus;''')
    word_start=source.index('uint16 cpu_read16(CpuState *cpu, uint8 bank, uint16 addr) {')
    word_end=source.index('\nvoid cpu_write8(',word_start)
    if source[word_start:word_end].count('RomPtr(')!=1:
        raise ConversionError('Pinned SNES word bus boundary changed.')
    source=source[:word_start]+'''uint16 cpu_read16(CpuState *cpu,uint8 bank,uint16 addr) {
    uint8_t lo=cpu_read8(cpu,bank,addr);
    uint8_t hi=cpu_read8(cpu,bank,(uint16)(addr+1));
    return cpu_latch_read16(cpu,(uint16)lo|((uint16)hi<<8));
}
'''+source[word_end:]
    start=source.index('static int cpu_sram_offset(uint8 bank, uint16 addr) {')
    end=source.index('\n/* APU pacing:',start)
    if 'cart_type == CART_HIROM' not in source[start:end]:
        raise ConversionError('Pinned SNES fast cartridge RAM decoder changed.')
    return '#include "snes_cart.h"\n'+source[:start]+'''static int cpu_sram_offset(uint8 bank,uint16 addr) {
    return rr_snes_cart_ram_offset(g_snes ? g_snes->cart : NULL,bank,addr);
}
'''+source[end:]
