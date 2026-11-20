"""Private copies of the pinned VDP: pixel-identical host arithmetic, and the shadow/highlight rules of the real chip.

Shadow/highlight (1.7.9): the pinned compositor shaded a pixel unless an OPAQUE high-priority layer covered it, let
operator sprites (palette 3, colours 14 and 15) fall through to lower sprites and act on them, let a low-priority
operator act on an opaque high-priority plane pixel, and shaded sprite colours 14 of palettes 0-2. The chip, as MAME's
315-5313 and Genesis Plus GX both model it: a plane tile's priority bit lifts the shadow even where its pixel is
transparent; an operator pixel is a sprite pixel (the first sprite wins, it collides, it hides lower sprites); a
low-priority operator does nothing over an opaque high-priority plane pixel; sprite colours $0E, $1E and $2E are always
at normal intensity. Outside shadow/highlight mode nothing changes (operators exist only in that mode).
"""
from .gun16_runtime import replace


SPRITE_OPERATOR = {
    # The batched sprite row (the game's build) and the scalar one (reference build), each in its own spelling.
    '''                    if (drawn[sx]) { v->sprite_collision = 1; continue; }
                    if (sh_mode && pal == 3 && nib == 14)
                        s_spr_hilite_op[sx] = 1;
                    else if (sh_mode && pal == 3 && nib == 15)
                        s_spr_shadow_op[sx] = 1;
                    else {
                        s_spr_idx[sx] = (uint8_t)(pal * 16 + nib);
                        s_spr_op[sx] = 1;
                        s_spr_hi[sx] = (uint8_t)pri;
                        drawn[sx] = 1;
                    }''': '''                    if (drawn[sx]) { v->sprite_collision = 1; continue; }
                    /* An operator is a sprite pixel too: it wins over later sprites and keeps its priority. */
                    drawn[sx] = 1;
                    s_spr_hi[sx] = (uint8_t)pri;
                    if (sh_mode && pal == 3 && nib == 14)
                        s_spr_hilite_op[sx] = 1;
                    else if (sh_mode && pal == 3 && nib == 15)
                        s_spr_shadow_op[sx] = 1;
                    else {
                        s_spr_idx[sx] = (uint8_t)(pal * 16 + nib);
                        s_spr_op[sx] = 1;
                    }''',
    '''                if (drawn[sx]) { v->sprite_collision = 1; continue; } /* first wins */

                if (sh_mode && pal == 3 && nib == 14) {        /* highlight op */
                    s_spr_hilite_op[sx] = 1;
                } else if (sh_mode && pal == 3 && nib == 15) { /* shadow op    */
                    s_spr_shadow_op[sx] = 1;
                } else {
                    s_spr_idx[sx] = (uint8_t)(pal * 16 + nib);
                    s_spr_op[sx]  = 1;
                    s_spr_hi[sx]  = (uint8_t)pri;
                    drawn[sx] = 1;
                }''': '''                if (drawn[sx]) { v->sprite_collision = 1; continue; } /* first wins */
                /* An operator is a sprite pixel too: it wins over later sprites and keeps its priority. */
                drawn[sx] = 1;
                s_spr_hi[sx] = (uint8_t)pri;
                if (sh_mode && pal == 3 && nib == 14) {        /* highlight op */
                    s_spr_hilite_op[sx] = 1;
                } else if (sh_mode && pal == 3 && nib == 15) { /* shadow op    */
                    s_spr_shadow_op[sx] = 1;
                } else {
                    s_spr_idx[sx] = (uint8_t)(pal * 16 + nib);
                    s_spr_op[sx]  = 1;
                }''',
}

SHADE_OLD = '''        if (sh_mode && px < GVDP_CRAM_ENTRIES) {
#if GENESIS_BATCHED_PLANES
            int hi_present = selection & 4;
#else
            int hi_present = (s_op && s_hi) || (a_op && a_hi) || (b_op && b_hi);
#endif
            int sh = !hi_present;
            int hl = 0;
            if (s_spr_shadow_op[xo]) sh = 1;
            if (s_spr_hilite_op[xo]) { if (sh) sh = 0; else hl = 1; }
            if (hl)      px += GVDP_PALETTE_HIGHLIGHT;
            else if (sh) px += GVDP_PALETTE_SHADOW;
        }'''

SHADE_NEW = '''        if (sh_mode && px < GVDP_CRAM_ENTRIES) {
#if GENESIS_BATCHED_PLANES
            int plane_normal = ((plane_a[xo] | plane_b[xo]) & 0x80) != 0;
            int plane_high = (plane_a[xo] & 0xC0) == 0xC0 || (plane_b[xo] & 0xC0) == 0xC0;
#else
            int plane_normal = a_hi || b_hi;
            int plane_high = (a_op && a_hi) || (b_op && b_hi);
#endif
            /* Either plane's tile priority lifts the shadow, opaque or not. The sprite slot holds a colour or an
             * operator with its priority; a low one under an opaque high plane pixel has no effect. */
            int sh, hl = 0, over = s_hi || !plane_high;
            if (s_op && over)
                sh = !(s_hi || plane_normal || (s_idx & 0x0F) == 0x0E);
            else {
                sh = !plane_normal;
                if (over && s_spr_shadow_op[xo]) sh = 1;
                else if (over && s_spr_hilite_op[xo]) { if (sh) sh = 0; else hl = 1; }
            }
            if (hl)      px += GVDP_PALETTE_HIGHLIGHT;
            else if (sh) px += GVDP_PALETTE_SHADOW;
        }'''


def spans(source):
    """Fewer, cheaper plane spans, same pixels (1.9.0 frame cost).

    Without 2-cell vertical scroll a plane row is continuous across 16-pixel columns, so a span runs to the next edge
    or window boundary instead of the next column. Each tile row is stored as one fixed 8-byte write (the bytes past
    the span are overwritten by the next span or land in the buffers' 8-byte margin) instead of a variable-length copy.
    """
    source = replace(source, '    uint8_t plane_a[GVDP_MAX_WIDTH], plane_b[GVDP_MAX_WIDTH];',
                     '    uint8_t plane_a[GVDP_MAX_WIDTH + 8], plane_b[GVDP_MAX_WIDTH + 8];')
    source = replace(source, '        else boundary = ((x >> 4) + 1) * 16;',
                     '        else boundary = vmode_2cell ? ((x >> 4) + 1) * 16 : w;')
    source = replace(source, '''        uint64_t packed=rr_md_expand_tile(bits,flip,attr);
        memcpy(out,(const uint8_t *)&packed+fx,(size_t)n);''', '''        uint64_t packed=rr_md_expand_tile(bits,flip,attr);
#if defined(__BYTE_ORDER__) && __BYTE_ORDER__ == __ORDER_BIG_ENDIAN__
        memcpy(out,(const uint8_t *)&packed+fx,(size_t)n);
#else
        packed>>=fx*8u;memcpy(out,&packed,8);
#endif''')
    return source


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
    for old, new in SPRITE_OPERATOR.items():
        source = replace(source, old, new)
    source = replace(source, SHADE_OLD, SHADE_NEW)
    source = spans(source)
    # The helper uses the VDP palette constants, already declared by this include.
    source = source.replace('#include "md_vdp_pixels.inc"\n', '', 1)
    source = replace(source, '#include "genesis_vdp.h"',
                     '#include "genesis_vdp.h"\n#include "md_vdp_pixels.inc"')
    return source
