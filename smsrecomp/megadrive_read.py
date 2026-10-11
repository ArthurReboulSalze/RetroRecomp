"""Checked VDP prefetch staging; preserve architectural save boundaries."""
from .gun16_runtime import replace


def header(source):
    source = '#include "md_vdp_read.h"\n' + source
    return replace(source, '    RrMdVdpIrq rr_irq;\n} GVDP;',
                   '    RrMdVdpIrq rr_irq;\n    RrMdVdpRead rr_read;\n} GVDP;')


def vdp(source):
    source = replace(source, '    memset(&v->rr_irq,0,sizeof v->rr_irq);',
                     '    memset(&v->rr_irq,0,sizeof v->rr_irq);\n'
                     '    memset(&v->rr_read,0,sizeof v->rr_read);')
    source = replace(source, '#include "md_vdp_dma.inc"',
        '#define RR_MD_TIMED_READ 1\n'
        'static void rr_read_retire(GVDP *v);\nstatic int rr_read_valid(const GVDP *v);\n'
        '#include "md_vdp_dma.inc"\n#include "md_vdp_read.inc"')
    source = replace(source, '    rr_fifo_sync(v);\n    if (!v->control_pending)',
        '    rr_fifo_sync(v);\n    rr_read_cancel(v);\n    if (!v->control_pending)')
    source = replace(source, '        maybe_start_dma(v);\n',
        '        maybe_start_dma(v);\n        if(!v->dma_active)rr_read_start(v);\n')
    source = replace(source, 'void gvdp_write_data(GVDP *v, uint16_t value)\n{',
        'void gvdp_write_data(GVDP *v, uint16_t value)\n{\n'
        '    rr_fifo_sync(v);rr_read_cancel(v);')
    source = replace(source, '    rr_fifo_wait(v,0);\n    uint16_t out;',
        '    if(rr_read_code(v->code))return rr_read_data(v);\n'
        '    rr_fifo_wait(v,0); /* invalid-command behavior retained, unqualified */\n'
        '    uint16_t out;')
    source = replace(source, 'uint16_t gvdp_peek_data(const GVDP *v)\n{',
        'uint16_t gvdp_peek_data(const GVDP *v)\n{\n'
        '    if(v->rr_read.state==2)return (uint16_t)v->rr_read.value;\n'
        '    if(v->rr_read.state==3)return (uint16_t)(v->rr_read.value|v->vram[(v->rr_read.address&65534u)+1]);\n'
        '    if(v->rr_read.state&1u)return rr_read_memory(v,v->rr_read.code,v->rr_read.address);')
    return source


def snapshot(source):
    source = replace(source, 'sizeof(GVDP) == 65912', 'sizeof(GVDP) == 65928')
    return replace(source, 'sizeof(GenesisMachine) == 139816', 'sizeof(GenesisMachine) == 139832')


def machine(source):
    marker = '    size_t extra=sizeof(RrMdVdpDma)+sizeof(RrMdVdpIrq);'
    # Two occurrences are expected (loader and size checker); anchor the
    # complete loader block before deriving positions, rejecting source drift.
    source = replace(source, marker+'\n    if(len==need-extra || len==need-extra-sizeof(RrMdVdpFifo)) {',
                     marker+'\n    if(len==need-extra || len==need-extra-sizeof(RrMdVdpFifo)) {')
    start = source.index('    size_t extra=sizeof(RrMdVdpDma)+sizeof(RrMdVdpIrq);')
    end = source.index('    if(len!=need)', start)
    source = source[:start] + '''    size_t read=sizeof(RrMdVdpRead);
    size_t extra=sizeof(RrMdVdpDma)+sizeof(RrMdVdpIrq);
    if(len==need-read || len==need-read-extra || len==need-read-extra-sizeof(RrMdVdpFifo)) {
        expanded=calloc(1,need);if(!expanded)return 0;
        size_t added=need-len;
        size_t prefix=added==read?offsetof(GVDP,rr_read):
            added==read+extra?offsetof(GVDP,rr_dma):offsetof(GVDP,rr_fifo);
        memcpy(expanded,src,prefix);
        memcpy(expanded+prefix+added,(const uint8_t *)src+prefix,len-prefix);
        src=expanded;len=need;
    }
''' + source[end:]
    return replace(source,
        'return size==n || size==n-extra || size==n-extra-sizeof(RrMdVdpFifo);',
        'size_t read=sizeof(RrMdVdpRead);\n'
        '    return size==n || size==n-read || size==n-read-extra || size==n-read-extra-sizeof(RrMdVdpFifo);')
