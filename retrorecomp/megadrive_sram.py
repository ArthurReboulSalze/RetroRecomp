"""Declared cartridge RAM, staged privately without changing the engine pin.

The six ordinary RAM types come from https://www.plutiedev.com/rom-header.
EEPROM wiring is a separate capability and is never treated as parallel RAM.
"""
from .core import ConversionError
from .gun16_runtime import replace

MAX_BYTES = 0x10000
TYPES = {0xa0: (1, False), 0xb0: (2, False), 0xb8: (2, False),
         0xe0: (1, True), 0xf0: (2, True), 0xf8: (2, True)}
REPORT_FIELDS = ('sram_bytes', 'sram_base', 'sram_end', 'sram_stride',
                 'sram_battery', 'sram_control', 'sram_hash')


def layout(rom):
    from .megadrive_hardware import eeprom_device
    device = eeprom_device(rom)
    if device is not None:
        return {'kind': 'eeprom', 'bytes': {'X24C01': 128, 'X24C02': 256, '24C04': 512}.get(device['chip'], 0),
                'battery': True, **device}
    data = rom.data
    if len(data) < 0x1bc or data[0x1b0:0x1b2] != b'RA':
        return {'kind': 'none', 'bytes': 0, 'battery': False}
    if data[0x1b3] == 0x40:
        return {'kind': 'eeprom', 'bytes': 0, 'battery': True, 'implemented': False}
    ram_type = data[0x1b2]
    if data[0x1b3] != 0x20 or ram_type not in TYPES:
        raise ConversionError('This Mega Drive cartridge declares an unsupported extra-memory type.')
    stride, battery = TYPES[ram_type]
    start = int.from_bytes(data[0x1b4:0x1b8], 'big')
    end = int.from_bytes(data[0x1b8:0x1bc], 'big')
    lane_ok = ((start & 1) == (ram_type >> 3 & 1) and (end & 1) == (start & 1)
               if stride == 2 else not start & 1 and bool(end & 1))
    size = (end - start) // stride + 1
    if not (start <= end < 0x400000 and lane_ok and 0 < size <= MAX_BYTES):
        raise ConversionError('The declared Mega Drive cartridge RAM range is invalid or exceeds 64 KiB.')
    return {'kind': 'sram', 'bytes': size, 'start': start, 'end': end,
            'stride': stride, 'battery': battery, 'implemented': True,
            'overlays_rom': start < len(data)}


def bus_header(source):
    start = source.index('    /* Battery-backed cartridge SRAM,')
    end = source.index('} GenesisBus;', start)
    source = source[:start] + '''    /* Compact parallel cartridge RAM, up to 64 KiB of connected bytes.
     * Immutable geometry is set after glue_init; register bits 0/1 control
     * the ROM overlay and write protection. No host pointers are serialized. */
    uint8_t  sram[0x10000];
    uint32_t sram_base, sram_end, sram_size;
    uint8_t  sram_present, sram_enabled, sram_stride, sram_battery;
''' + source[end:]
    return source.replace('#endif /* GENESIS_BUS_H */',
        'int rr_md_sram_geometry_matches(const GenesisBus *saved, const GenesisBus *live);\n'
        '#endif /* GENESIS_BUS_H */')


def bus_source(source):
    source = '#include "retro_md_game.h"\n' + source
    start = source.index('/* Battery SRAM geometry from the ROM header')
    end = source.index('/* ---- Controllers:', start)
    source = source[:start] + '''/* Declared parallel RAM. EEPROM is not a byte-addressable substitute. */
static uint32_t rr_sram_be32(const uint8_t *p) {
    return ((uint32_t)p[0]<<24) | ((uint32_t)p[1]<<16) | ((uint32_t)p[2]<<8) | p[3];
}
static void rr_sram_geometry(GenesisBus *b, uint32_t start, uint32_t end,
                             unsigned stride, unsigned battery) {
    if (start>end || end>=0x400000u || (stride!=1 && stride!=2)) return;
    if (stride==1 ? ((start&1u) || !(end&1u)) : ((start&1u)!=(end&1u))) return;
    uint32_t size=(end-start)/stride+1u;
    if (size>sizeof b->sram) return;
    b->sram_present=1; b->sram_base=start; b->sram_end=end; b->sram_size=size;
    b->sram_stride=(uint8_t)stride; b->sram_battery=(uint8_t)battery;
    /* Small linear cartridges have no ROM behind SRAM. Overlapping ROM
     * remains visible until bit 0 of $A130F1 selects the RAM overlay. */
    b->sram_enabled=(uint8_t)(start>=RR_MD_ROM_BYTES);
}
void gbus_sram_setup(GenesisBus *b) {
    memset(b->sram,0xff,sizeof b->sram);
    b->sram_base=b->sram_end=b->sram_size=0;
    b->sram_present=b->sram_enabled=b->sram_stride=b->sram_battery=0;
    if (g_rom[0x1b0]!='R' || g_rom[0x1b1]!='A' || g_rom[0x1b3]!=0x20) return;
    unsigned type=g_rom[0x1b2], stride;
    switch(type) {
        case 0xa0: case 0xe0: stride=1; break;
        case 0xb0: case 0xb8: case 0xf0: case 0xf8: stride=2; break;
        default: return;
    }
    uint32_t start=rr_sram_be32(g_rom+0x1b4), end=rr_sram_be32(g_rom+0x1b8);
    if (stride==2 && (start&1u)!=((type>>3)&1u)) return;
    rr_sram_geometry(b,start,end,stride,(type&0x40u)!=0);
}
void gbus_sram_set_geometry(GenesisBus *b, uint32_t start, uint32_t end) {
    if (b->sram_present || !start || (g_rom[0x1b0]=='R' && g_rom[0x1b1]=='A')) return;
    rr_sram_geometry(b,start,end,(start&1u)==(end&1u)?2u:1u,1);
}
static int sram_hit(const GenesisBus *b, uint32_t a) {
    return b->sram_present && (b->sram_enabled&1u)
        && a>=(b->sram_base&~1u) && a<=(b->sram_end|1u);
}
static int rr_sram_byte(const GenesisBus *b, uint32_t a) {
    return a>=b->sram_base && a<=b->sram_end
        && (b->sram_stride==1 || !((a-b->sram_base)&1u));
}
static uint8_t rr_sram_read(const GenesisBus *b, uint32_t a) {
    /* Unconnected byte lanes read high in this parallel-RAM model. */
    return rr_sram_byte(b,a) ? b->sram[(a-b->sram_base)/b->sram_stride] : 0xff;
}
static void rr_sram_write(GenesisBus *b, uint32_t a, uint8_t value) {
    if (!(b->sram_enabled&2u) && rr_sram_byte(b,a))
        b->sram[(a-b->sram_base)/b->sram_stride]=value;
}
uint8_t *gbus_sram_buffer(GenesisBus *b) { return b->sram; }
uint32_t gbus_sram_size(const GenesisBus *b) { return b->sram_present?b->sram_size:0u; }
int rr_md_sram_geometry_matches(const GenesisBus *saved, const GenesisBus *live) {
    return saved->sram_present==live->sram_present && saved->sram_base==live->sram_base
        && saved->sram_end==live->sram_end && saved->sram_size==live->sram_size
        && saved->sram_stride==live->sram_stride && saved->sram_battery==live->sram_battery
        && saved->sram_size<=sizeof saved->sram && saved->sram_enabled<=3;
}

''' + source[end:]
    old = '        uint32_t o = a - b->sram_base;\n        return (uint16_t)((b->sram[o] << 8) | b->sram[(o + 1u) % b->sram_size]);'
    if source.count(old) != 2:
        raise ConversionError('Pinned Mega Drive SRAM read hooks changed.')
    source = source.replace(old, '        return (uint16_t)(((uint16_t)rr_sram_read(b,a)<<8) | rr_sram_read(b,a+1u));')
    source = replace(source, '        return b->sram[a - b->sram_base];', '        return rr_sram_read(b,a);')
    source = replace(source, '        return b->sram[(a & 0xFFFFFFu) - b->sram_base];',
                     '        return rr_sram_read(b,a & 0xffffffu);')
    source = replace(source, '        uint32_t o = a - b->sram_base;\n        b->sram[o] = (uint8_t)(v >> 8); b->sram[(o + 1u) % b->sram_size] = (uint8_t)v;',
                     '        rr_sram_write(b,a,(uint8_t)(v>>8)); rr_sram_write(b,a+1u,(uint8_t)v);')
    source = replace(source, 'if (sram_hit(b, a)) { b->sram[a - b->sram_base] = v; return; }',
                     'if (sram_hit(b, a)) { rr_sram_write(b,a,v); return; }')
    source = replace(source, 'if (a == 0xA130F1u || a == 0xA130F0u)', 'if (a == 0xA130F1u)')
    source = replace(source, '    /* Word-aligned fall-through for VDP/IO byte writes (value on both halves). */',
        '    if (a == 0xA130F0u) return; /* register is on the odd byte lane */\n'
        '    /* Word-aligned fall-through for VDP/IO byte writes (value on both halves). */')
    return source.replace('b->sram_enabled = (uint8_t)(v & 1);', 'b->sram_enabled = (uint8_t)(v & 3);')


def snapshot_source(source):
    return replace(replace(source,
        'sizeof(GenesisBus) == 24664', 'sizeof(GenesisBus) == 73816'),
        'sizeof(GenesisMachine) == 90576', 'sizeof(GenesisMachine) == 139728')


def machine_source(source):
    return replace(source, '    memcpy(&g_machine, i, sizeof g_machine);',
        '    const GenesisMachine *saved=(const GenesisMachine *)i;\n'
        '    if (!rr_md_sram_geometry_matches(&saved->bus,&g_machine.bus)) return 0;\n'
        '    memcpy(&g_machine, i, sizeof g_machine);')
