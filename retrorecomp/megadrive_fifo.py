"""Checked four-word VDP queue adaptations, kept outside the pinned checkout."""
from .gun16_runtime import replace


def header(source):
    source = '#include "md_vdp_fifo.h"\n' + source
    source = replace(source, '} GVDP;', '    RrMdVdpFifo rr_fifo;\n} GVDP;')
    return source + '\nvoid gvdp_fifo_advance(GVDP *v, unsigned phase);\nint gvdp_fifo_valid(const GVDP *v);\n'


def vdp(source):
    source = replace(source, '    s_pending_68k_stall = 0;\n    /* Sensible',
        '    s_pending_68k_stall = 0;\n    memset(&v->rr_fifo,0,sizeof v->rr_fifo);\n    /* Sensible')
    source = replace(source, '/* ---- DMA ----', '#include "md_vdp_fifo.inc"\n\n/* ---- DMA ----')
    source = replace(source, '    uint8_t mode = REG_DMA_SRC_HI(v) & 0xC0;',
        '    rr_fifo_wait(v,0); /* ordered before enabled legacy bulk DMA */\n'
        '    uint8_t mode = REG_DMA_SRC_HI(v) & 0xC0;')
    source = replace(source, 'void gvdp_write_control(GVDP *v, uint16_t value)\n{',
        'void gvdp_write_control(GVDP *v, uint16_t value)\n{\n    rr_fifo_sync(v);')
    start = source.index('    if (v->dma_fill_pending) { dma_run_vram_fill_data')
    end = source.index('\n}\n', start)
    source = source[:start] + '''    if (v->dma_fill_pending) {
        rr_fifo_wait(v,0); dma_run_vram_fill_data(v,value); return;
    }
    rr_fifo_write(v,value);''' + source[end:]
    source = replace(source, 'uint16_t gvdp_read_data(GVDP *v)\n{',
        'uint16_t gvdp_read_data(GVDP *v)\n{\n    rr_fifo_wait(v,0);')
    source = replace(source, 'uint16_t gvdp_read_control(GVDP *v)\n{',
        'uint16_t gvdp_read_control(GVDP *v)\n{\n    rr_fifo_sync(v);')
    source = replace(source, 'uint16_t s = 0x3400 | 0x0200;', 'uint16_t s = 0x3400 | rr_fifo_status(v);')
    source = replace(source, '    s |= 0x0200;', '    s |= rr_fifo_status(v);')
    # Scheduler calls begin only after advance(end), so the previous line's
    # remainder (including a crossing write) is preserved without duplication.
    source = replace(source, '    v->scanline = (uint16_t)line;',
        '    if(v->rr_fifo.clock>=RR_MD_MASTER_PER_LINE) v->rr_fifo.clock-=RR_MD_MASTER_PER_LINE;\n'
        '    v->scanline = (uint16_t)line;')
    return source


def machine(source):
    source = '#include <stdlib.h>\n' + source
    source = replace(source, '        /* Render + emit active scanlines.',
        '        gvdp_fifo_advance(&m->vdp,MASTER_PER_LINE);\n\n        /* Render + emit active scanlines.')
    # Adding state at the end of GVDP shifts all subsequent machine fields by
    # 48 bytes; only specifically allowed ABI-2 builds may reach this migration.
    source = replace(source, '    if (!src || len != machine_rb_save(NULL, 0)) return 0;', '''    if(!src) return 0;
    size_t need=machine_rb_save(NULL,0);
    uint8_t *expanded=NULL;
    if(len==need-sizeof(RrMdVdpFifo)) {
        expanded=calloc(1,need); if(!expanded) return 0;
        size_t prefix=offsetof(GVDP,rr_fifo);
        memcpy(expanded,src,prefix);
        memcpy(expanded+prefix+sizeof(RrMdVdpFifo),(const uint8_t *)src+prefix,len-prefix);
        src=expanded;len=need;
    }
    if(len!=need) { free(expanded); return 0; }
    if(!gvdp_fifo_valid(&((const GenesisMachine *)src)->vdp) ||
       !rr_md_sram_geometry_matches(&((const GenesisMachine *)src)->bus,&g_machine.bus)) {
        free(expanded); return 0;
    }''')
    source = replace(source, '    return 1;\n}\n\nvoid machine_set_pad',
        '    free(expanded);\n    return 1;\n}\n\nvoid machine_set_pad')
    return source + '''
int rr_md_machine_snapshot_size(size_t size) {
    size_t n=machine_rb_save(NULL,0);
    return size==n || size==n-sizeof(RrMdVdpFifo);
}
'''


def snapshot(source):
    source = replace(source, 'sizeof(GVDP) == 65824', 'sizeof(GVDP) == 65872')
    return replace(source, 'sizeof(GenesisMachine) == 139728', 'sizeof(GenesisMachine) == 139776')


def bus(source):
    source = replace(source,'extern void glue_charge_68k_stall(uint32_t cycles);',
        'extern void machine_vdp_wait(unsigned cycles);')
    source = replace(source,'if (st) glue_charge_68k_stall(st);','if (st) machine_vdp_wait(st);')
    return replace(source, '        if (a < 0xC00004u) return gvdp_read_data(b->vdp);', '''        if (a < 0xC00004u) {
            uint16_t value=gvdp_read_data(b->vdp);
            uint32_t stall=gvdp_consume_68k_stall(b->vdp);
            if(stall) machine_vdp_wait(stall);
            return value;
        }''')
