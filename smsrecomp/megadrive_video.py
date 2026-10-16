"""Pixel-identical host arithmetic, in private copies of the pinned VDP."""
from .gun16_runtime import replace


def optimize(source):
    source = '#include "md_vdp_pixels.inc"\n' + source
    old = '''        for (int i = 0; i < n; ++i) {
            unsigned nib = (bits >> (28 - ((fx + i) ^ flip) * 4)) & 15;
            out[i] = (uint8_t)(attr | nib | (nib ? 0x40 : 0));
        }'''
    source = replace(source, old, '''#if RR_MD_REFERENCE_PIXELS
''' + old + '''
#else
        uint64_t packed=rr_md_expand_tile(bits,flip,attr);
        memcpy(out,(const uint8_t *)&packed+fx,(size_t)n);
#endif''')
    old = '''    for (int x = -content_extra, xo = content_start; xo < content_end; x++, xo++) {'''
    source = replace(source, old, '''    int composed=content_start;
#if GENESIS_BATCHED_PLANES
    if(!s_ws_bgdiag)composed=rr_md_compose_pixels(out,content_start,content_end,
        plane_a,plane_b,s_spr_idx,s_spr_op,s_spr_hi,s_spr_shadow_op,s_spr_hilite_op,
        backdrop,sh_mode);
#endif
    for (int x = composed-offset, xo = composed; xo < content_end; x++, xo++) {''')
    # The helper uses the VDP palette constants, already declared by this include.
    source = source.replace('#include "md_vdp_pixels.inc"\n', '', 1)
    source = replace(source, '#include "genesis_vdp.h"',
                     '#include "genesis_vdp.h"\n#include "md_vdp_pixels.inc"')
    return source
