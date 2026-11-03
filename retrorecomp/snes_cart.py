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
    if circuit=='superfx':
        # Same rule as the pinned loader: version-3 headers ($33 maker) give
        # Game Pak RAM in $FFBD; older boards (Star Fox) default to 64 KiB.
        extended=data[offset-3] if data[offset+26]==0x33 else 0
        size=1<<(10+extended) if 1<=extended<=8 else 0x10000
        return {'bytes': size, 'battery': chip in (0x15,0x1a),
                'mapping': detected, 'rom_bytes': len(data), 'chip': circuit}
    if circuit=='sa1':
        # BW-RAM: the size is the header's RAM exponent; the board keeps it in a battery when the type says so ($35).
        size=(1 << (10+exponent)) if exponent else 0
        return {'bytes': size, 'battery': chip==0x35 and bool(size),
                'mapping': detected, 'rom_bytes': len(data), 'chip': circuit}
    if circuit=='sdd1':
        size=(1 << (10+exponent)) if exponent else 0
        return {'bytes': size, 'battery': chip==0x45 and bool(size),
                'mapping': detected, 'rom_bytes': len(data), 'chip': circuit}
    size = (1 << (10+exponent)) if chip in (1, 2, 3, 5) and exponent else 0
    return {'bytes': size, 'battery': chip in (2,5) and bool(size),
            'mapping': detected, 'rom_bytes': len(data),'chip':circuit}


def layout(rom):
    return layout_bytes(rom.data, rom.mapping)


def ram_offset(memory, address):
    if (not isinstance(address, int) or not 0 <= address <= 0xffffff or not memory['bytes']
            or memory.get('chip') in ('superfx','sa1')):
        # Game Pak RAM shared with the GSU is never a guarded 65816 code window.
        return None
    bank, adr = address >> 16, address & 0xffff
    if bank in (0x7e, 0x7f):
        return None
    if memory.get('chip')=='sdd1':
        # The S-DD1 board's RAM is in banks $70-$73; $C0-$FF are its ROM windows.
        if 0x70 <= bank < 0x74 and adr < 0x8000:
            return ((bank & 15) * 0x8000 + (adr & 0x7fff)) & (memory['bytes']-1)
    elif memory.get('chip')=='dsp1-hi':
        if bank&0x7f>=0x20 and bank&0x7f<0x40 and 0x6000<=adr<0x8000:
            return (adr&0x1fff)&(memory['bytes']-1)
    elif memory['mapping'] == 'lorom':
        full = memory['rom_bytes'] <= 0x200000 and memory['bytes'] <= 0x8000
        if (0x70 <= bank < 0x7e or bank >= 0xf0) and (adr < 0x8000 or full):
            return ((bank & 15) * 0x8000 + (adr & 0x7fff)) & (memory['bytes']-1)
    elif memory['mapping'] in ('hirom', 'exhirom'):
        canonical = bank & 0x7f
        if 0x20 <= canonical < 0x40 and 0x6000 <= adr < 0x8000:
            return ((canonical & 31) * 0x2000 + (adr & 0x1fff)) & (memory['bytes']-1)
    return None


def adapt_cart(source):
    source = replace(source, '#include "cart.h"', '#include "cart.h"\n#include "snes_cart.h"\n#include "cpu_state.h"\n'
                     '#include "snes_native_steps.h"')
    # SA-1 board: how far behind the S-CPU the coprocessor stands when the S-CPU reaches it, before and after the
    # synchronisation (reported per run).
    source = replace(source, '''    case CART_SA1:
      cart_sync_coprocessors(cart, cart_master_clock(cart));
      return sa1_cpu_read(cart->sa1, bank, adr, 0xff);''', '''    case CART_SA1:
      /* The S-CPU reaches the SA-1 at the master clock of THIS bus cycle (cart_master_clock is the clock of
       * the end of the previous instruction: the SA-1 stood up to thousands of clocks behind). */
#if RR_SN_SA1
      rr_snes_sa1_before((int64_t)g_cpu.master_cycles - (int64_t)sa1_master_clock(cart->sa1));
#endif
      cart_sync_coprocessors(cart, g_cpu.master_cycles);
#if RR_SN_SA1
      rr_snes_sa1_after((int64_t)g_cpu.master_cycles - (int64_t)sa1_master_clock(cart->sa1));
#endif
      return sa1_cpu_read(cart->sa1, bank, adr, 0xff);''')
    source = replace(source, '''    case CART_SA1:
      cart_sync_coprocessors(cart, cart_master_clock(cart));
      sa1_cpu_write(cart->sa1, bank, adr, val);''', '''    case CART_SA1:
      /* The S-CPU reaches the SA-1 at the master clock of THIS bus cycle (cart_master_clock is the clock of
       * the end of the previous instruction: the SA-1 stood up to thousands of clocks behind). */
#if RR_SN_SA1
      rr_snes_sa1_before((int64_t)g_cpu.master_cycles - (int64_t)sa1_master_clock(cart->sa1));
#endif
      cart_sync_coprocessors(cart, g_cpu.master_cycles);
#if RR_SN_SA1
      rr_snes_sa1_after((int64_t)g_cpu.master_cycles - (int64_t)sa1_master_clock(cart->sa1));
#endif
      sa1_cpu_write(cart->sa1, bank, adr, val);''')
    old = '''      if ((((bank >= 0x70 && bank < 0x7e) || bank >= 0xf0)) &&
          adr < 0x8000 && cart->ramSize > 0) return NULL;'''
    source = replace(source, old, '      if (rr_snes_cart_ram_offset(cart,bank,adr)>=0) return NULL;')
    # ExHiROM boards (an image above 4 MiB): the address line A23 picks the half of the ROM. Banks $80-$FF reach the first 4 MiB,
    # banks $00-$7D the second. A HiROM image of 4 MiB or less is untouched.
    source = replace(source, '''    case CART_HIROM: {
      uint8_t canonical = bank & 0x7f;
      if (adr < 0x8000 && canonical < 0x40) return NULL;
      off = ((uint32_t)(canonical & 0x3f) << 16) | adr;
      break;''', '''    case CART_HIROM: {
      uint8_t canonical = bank & 0x7f;
      if (adr < 0x8000 && canonical < 0x40) return NULL;
      off = ((uint32_t)(canonical & 0x3f) << 16) | adr;
      if (cart->romImageSize > 0x400000 && !(bank & 0x80)) off += 0x400000;
      break;''')
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
#if RR_SN_EXHIROM
  // ExHiROM: the header is the one at $40FFC0 (the reset vector is read at $00:FFFC, which is ROM $40FFFC).
  if(length >= 0x410000) readHeader(data, length, 0x40ffc0, &headers[2]);
#endif
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
    # The S-DD1 decompresses on a CPU read of its window ($C0-$FF) when a channel is armed for the address (`sdd1_cpu_read`,
    # inside `cart_read`). The pinned `cpu_read8` sends the Super FX, the SA-1, the CX4 and the DSP-1 windows to `cart_read` and
    # every other ROM read to the plain pointer, so a CPU read of decompressed data came back as the compressed bytes: the
    # S-DD1 reaches `cart_read` too, for banks $C0-$FF (the others stay as LoROM, and as before).
    source=replace(source,'''    if (g_snes && g_snes->cart && g_snes->cart->type == CART_SA1)
        return cpu_latch_read8(cpu, cart_read(g_snes->cart, bank, addr));
''','''    if (g_snes && g_snes->cart && g_snes->cart->type == CART_SA1)
        return cpu_latch_read8(cpu, cart_read(g_snes->cart, bank, addr));
''')
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
