"""Private cartridge bus adaptation. Declared circuits never borrow game code."""
from .gun16_runtime import replace

REPORT_FIELDS = ('eeprom_kind', 'eeprom_writes', 'cartridge_state_hash')


def bus(source):
    # Header comes first for its compile-time clock/board declarations.
    source = '#include "md_cart.h"\n' + source
    source = replace(source, '/* ---- Controllers:', '#include "md_cart.inc"\n\n/* ---- Controllers:')
    source = replace(source, 'return b->sram_present && (b->sram_enabled&1u)',
                     'return b->sram_present && b->sram_stride && (b->sram_enabled&1u)')
    for function, width, write, peek in (
        ('gbus_read16',2,False,False), ('gbus_peek16',2,False,True),
        ('gbus_read8',1,False,False), ('gbus_peek8',1,False,True),
        ('gbus_write16',2,True,False), ('gbus_write8',1,True,False)):
        start = source.index(f'{function}(')
        pos = source.index('{',start)+1
        hook = (f'\n    if(rr_cart_write(b,a,v,{width}))return;' if write else
                f'\n    unsigned cart_value; if(rr_cart_read({"(GenesisBus *)b" if peek else "b"},a,&cart_value,{int(peek)}))return ({"uint16_t" if width==2 else "uint8_t"})cart_value;')
        source = source[:pos]+'\n    a &= 0xFFFFFFu;'+hook+source[pos:]
    # SRAM overlay registers do not enable serial memory as parallel RAM.
    source = source.replace('b->sram_enabled = (uint8_t)(v & 3);',
                            'if(!RR_MD_EEPROM_KIND)b->sram_enabled = (uint8_t)(v & 3);')
    return source


def machine(source):
    source = '#include "md_cart.h"\n' + source
    source = replace(source,'        m->master_cycle += MASTER_PER_LINE;',
                     '        m->master_cycle += MASTER_PER_LINE;\n'
                     '        rr_md_cart_advance(&m->bus,m->master_cycle);')
    return source + '\nuint64_t machine_cart_stamp(void) { return g_machine.master_cycle + machine_vdp_phase(); }\n'
