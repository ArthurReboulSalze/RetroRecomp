/* Presentation-only CRT gaps, one per guest raster row, and the CRT and LCD looks. Original code. */
#ifndef RETRO_SCANLINES_H
#define RETRO_SCANLINES_H
#include <stdbool.h>
#include <stdint.h>
#include <math.h>

/* Coverage below the last third of each source row, integrated over one
 * output pixel. Fractional zooms keep partial alpha instead of rounding
 * whole bands to different thicknesses. At less than 2x, gaps cannot be
 * resolved; leave the image intact rather than darkening guest rows. */
static uint64_t rr_scanline_coverage(uint64_t position, uint64_t height) {
    uint64_t remainder = position % (3 * height);
    return position / (3 * height) * height +
        (remainder > 2 * height ? remainder - 2 * height : 0);
}
static uint8_t rr_scanline_alpha(int y, int height, int source_rows) {
    if (source_rows <= 0 || height <= 0 || y < 0 || y >= height ||
        (uint64_t)height < 2 * (uint64_t)source_rows) return 0;
    uint64_t step = 3 * (uint64_t)source_rows;
    uint64_t begin = rr_scanline_coverage((uint64_t)y * step, (uint64_t)height);
    uint64_t end = rr_scanline_coverage((uint64_t)(y + 1) * step, (uint64_t)height);
    return (uint8_t)((85 * (end - begin) + step / 2) / step);
}

/* ---- The CRT and LCD looks (HOST_KIT D35): presentation only, original code ----
 * What each look's overlays hold, one value per output pixel, computed once per size and kept in a texture
 * (scanline_sdl.h draws them). Nothing here reads or changes the machine's picture, state or timing. */

/* The CRT styles (D35, after the players' first shots, 27 Nov 2026): one set of numbers per style, for both stages. Stored
 * ids never change ([<Console>.Video] crt_style): 0 soft, 1 sharp, 2 arcade; an unknown value is the machine's default.
 *   Soft: the look as merged (stage 2 is crt-lottes-fast's defaults).
 *   Sharp: a narrow horizontal blend (stage 1: whole-pixel steps, then linear: "sharp bilinear"), a lighter mask and glow.
 *   Arcade: a cabinet monitor: thinner beams with deeper gaps, a strong slot mask (coarser on tall screens), more saturation
 *   and glow, brighter, and a slighter curve. */
#define RR_CRT_STYLES 3
enum { RR_CRT_SOFT, RR_CRT_SHARP, RR_CRT_ARCADE };
typedef struct RrCrtStyle {
    double sigma, depth;              /* stage 1: the beam's Gaussian (of a line) and how dark its gaps go */
    int boost, glow;                  /* stage 1: the added copies' colour mod (of 255): brightness, glow */
    int mask_lo, mask_flat, mask_curved;   /* stage 1: the unlit stripes' level (of 255); the mask flat and curved: 0 grille, 1 slot */
    bool sharp_rows;                  /* stage 1: whole-pixel steps across before the linear stretch */
    double corner, vignette;          /* the curved frame: corner radius (of the shorter side), edge darkening */
    double warp_x, warp_y;            /* the curve, both stages */
    float thin, blur, mask, kind_flat, kind_curved, saturation;   /* stage 2 (CRTS): thin with gaps, blur, mask level, masks, ratio exponent */
    float gain;                       /* stage 2: the light after the mask, before the tone map (what a brighter tube gives back) */
    bool coarse_mask;                 /* the mask's cells grow with the screen (one step per 1,000 rows) */
} RrCrtStyle;
static const RrCrtStyle rr_crt_styles[RR_CRT_STYLES] = {
    {0.24, 0.80, 115, 56, 179, 0, 1, false, 0.06, 0.45, 0.031, 0.041, 0.75f, -2.5f, 0.50f, 1.0f, 3.0f, 1.00f, 1.00f, false},
    {0.24, 0.80, 115, 24, 204, 0, 1, true,  0.06, 0.45, 0.031, 0.041, 0.75f, -6.0f, 0.65f, 1.0f, 3.0f, 1.00f, 1.00f, false},
    {0.20, 0.85, 230, 96, 150, 1, 1, false, 0.04, 0.35, 0.018, 0.024, 0.90f, -3.0f, 0.40f, 3.0f, 3.0f, 1.15f, 1.30f, true},
};
static const RrCrtStyle *rr_crt_style(int style) { return &rr_crt_styles[style >= 0 && style < RR_CRT_STYLES ? style : RR_CRT_SOFT]; }
/* The mask's cell size in output pixels: 1, or with coarse_mask one more per 1,000 rows of the picture's rectangle. */
static int rr_crt_mask_scale(const RrCrtStyle *style, int height) {
    return style->coarse_mask && height >= 1000 ? 1 + height / 1000 : 1;
}

/* One bright beam per console line, a Gaussian across the line (sigma: 0.24 of a line in the soft style), averaged over the
 * output row: the alpha of a black overlay. No dark gaps below two output rows a line (they cannot be resolved) or above 300
 * lines a frame (interlaced TV modes, 31 kHz monitors, the ST's mono screen: their lines were too fine to show gaps). */
#define RR_CRT_FINE_LINES 300
static uint8_t rr_crt_beam_alpha_style(int y, int height, int lines, double sigma, double depth) {
    if (lines <= 0 || lines > RR_CRT_FINE_LINES || height < 2 * lines || y < 0 || y >= height) return 0;
    double lit = 0.0;
    for (int s = 0; s < 4; ++s) {
        const double pos = ((y + (s + 0.5) / 4.0) * lines) / height;
        const double d = pos - floor(pos) - 0.5;
        lit += exp(-(d * d) / (2.0 * sigma * sigma));
    }
    const long a = lround(255.0 * depth * (1.0 - lit / 4.0));
    return (uint8_t)(a < 0 ? 0 : a > 255 ? 255 : a);
}
static uint8_t rr_crt_beam_alpha(int y, int height, int lines) { return rr_crt_beam_alpha_style(y, height, lines, 0.24, 0.80); }

/* The phosphor mask, screen space, multiplied over the picture (0xffRRGGBB, 0xff = keep). Kind 0: aperture grille,
 * vertical R G B stripes one cell wide; kind 1: slot mask, the stripes staggered every three rows with a thin gap. lo: the
 * unlit stripes' level (179: 70 %, the soft style); scale: the cell's size in output pixels. */
static uint32_t rr_crt_mask_texel_style(int x, int y, int kind, int lo, int scale) {
    if (scale > 1) { x /= scale; y /= scale; }
    int phase = x % 3;
    if (kind == 1 && (y / 3) % 2) phase = (x + 1) % 3;
    int r = phase == 0 ? 255 : lo, g = phase == 1 ? 255 : lo, b = phase == 2 ? 255 : lo;
    if (kind == 1 && y % 3 == 2) { r = r * 3 / 4; g = g * 3 / 4; b = b * 3 / 4; }
    return 0xff000000u | (uint32_t)r << 16 | (uint32_t)g << 8 | (uint32_t)b;
}
static uint32_t rr_crt_mask_texel(int x, int y, int kind) { return rr_crt_mask_texel_style(x, y, kind, 179, 1); }

/* Vignette and rounded corners in the picture's own space (they curve with it), multiplied: grey 0xffKKKKKK.
 * corner: radius as a share of the shorter side; vignette: how much the edges darken. */
static uint32_t rr_crt_frame_texel(int x, int y, int w, int h, double corner, double vignette) {
    const double u = (x + 0.5) / w * 2 - 1, v = (y + 0.5) / h * 2 - 1;
    double k = 1.0 - vignette * (u * u * 0.6 + v * v * 0.8) * 0.5;
    const double radius = corner * (w < h ? w : h);
    if (radius > 0) {
        const double cx = fmax(radius - (x + 0.5), (x + 0.5) - (w - radius));
        const double cy = fmax(radius - (y + 0.5), (y + 0.5) - (h - radius));
        if (cx > 0 && cy > 0) {
            const double a = 0.5 - (sqrt(cx * cx + cy * cy) - radius) / 1.5;   /* anti-aliased over 1.5 pixels */
            k *= a < 0 ? 0 : a > 1 ? 1 : a;
        }
    }
    const long c = lround(255.0 * (k < 0 ? 0 : k > 1 ? 1 : k));
    return 0xff000000u | (uint32_t)c * 0x010101u;
}

/* The curve: crt-lottes' warp sends a screen point p (-1..1) to the picture point p * (1 + warp * p.yx^2). The kit places each
 * vertex of its grid where the warp sends it, so this solves the warp backwards for the picture point (sx, sy). */
static void rr_crt_warp_solve(double sx, double sy, double warp_x, double warp_y, double *px, double *py) {
    double x = sx, y = sy;
    for (int i = 0; i < 8; ++i) { x = sx / (1 + warp_x * y * y); y = sy / (1 + warp_y * x * x); }
    *px = x; *py = y;
}

/* The LCD grid over a picture of src_w x src_h shown at dst_w x dst_h: each cell keeps a dim gap on its right and bottom
 * (a sixth of the cell, at least one pixel) and three faint colour columns. Multiplied: 0xffRRGGBB. */
static uint32_t rr_lcd_texel(int x, int y, int dst_w, int dst_h, int src_w, int src_h) {
    const double cell_w = (double)dst_w / src_w, cell_h = (double)dst_h / src_h;
    const double fx = fmod(x + 0.5, cell_w), fy = fmod(y + 0.5, cell_h);
    const double gap_w = fmax(1.0, cell_w / 6.0), gap_h = fmax(1.0, cell_h / 6.0);
    const bool gap = fx >= cell_w - gap_w || fy >= cell_h - gap_h;
    const int third = (int)(fx * 3.0 / (cell_w - gap_w > 1.0 ? cell_w - gap_w : 1.0));
    const double v = gap ? 0.62 : 1.0;
    const int r = (int)lround(255.0 * v * (third == 0 ? 1.0 : 0.90));
    const int g = (int)lround(255.0 * v * (third == 1 ? 1.0 : 0.90));
    const int b = (int)lround(255.0 * v * (third >= 2 ? 1.0 : 0.90));
    return 0xff000000u | (uint32_t)r << 16 | (uint32_t)g << 8 | (uint32_t)b;
}
/* ---- The handhelds' "Real screen" LCD style (D35, 27 Nov 2026): the screen each handheld had, drawn from its picture ----
 * lcd_style ([<Console>.Video]): 0 real screen, 1 the grid above; an unknown value is the real screen. The panel is the
 * machine's (RrhkMachine.lcd_panel), never stored:
 *   TFT (Game Boy Color, Game Boy Advance): a dark matrix between the cells, R G B columns in each, a little ghosting;
 *   STN (Game Gear): the same, softer, with the passive screen's slower response;
 *   DMG (Game Boy): a monochrome dot matrix whose gaps show the light screen behind the dots, and the slow response.
 * The response (ghost) is a share of the last shown picture kept in the next, once per game frame: rr_lcd_ghost_pixel. */
#define RR_LCD_STYLES 2
enum { RR_LCD_REAL, RR_LCD_GRID };
enum { RR_PANEL_TFT, RR_PANEL_STN, RR_PANEL_DMG, RR_PANELS };
typedef struct RrLcdPanel {
    int ghost;                     /* of 256: the last shown picture's share in the next */
    int gap_div;                   /* the gap: a cell / gap_div, at least one pixel, on each cell's right and bottom */
    double gap_level, off_level;   /* colour panels, multiplied: the gap's level, the two unlit columns' level */
    int boost;                     /* colour panels: an added copy's colour mod (of 255), what the matrix takes back */
    int light;                     /* DMG: the gap's blend toward the screen's own colour (of 255) */
    uint32_t paper;                /* DMG: that colour, the pale olive of the screen where no dot is lit (0xRRGGBB) */
} RrLcdPanel;
static const RrLcdPanel rr_lcd_panels[RR_PANELS] = {
    {64, 6, 0.50, 0.68, 110, 0, 0},
    {115, 7, 0.55, 0.70, 90, 0, 0},
    {128, 7, 1.0, 1.0, 0, 70, 0xc8d0a8u},
};
static const RrLcdPanel *rr_lcd_panel(int panel) { return &rr_lcd_panels[panel >= 0 && panel < RR_PANELS ? panel : RR_PANEL_TFT]; }

/* The real screen's overlay over a picture of src_w x src_h shown at dst_w x dst_h. Colour panels: multiplied (0xffRRGGBB),
 * the gap dark and three columns in each cell. DMG: blended (0xAARRGGBB), the pale screen over the gaps, nothing over the dots. */
static uint32_t rr_lcd_real_texel(int x, int y, int dst_w, int dst_h, int src_w, int src_h, int panel) {
    const RrLcdPanel *p = rr_lcd_panel(panel);
    const double cell_w = (double)dst_w / src_w, cell_h = (double)dst_h / src_h;
    const double fx = fmod(x + 0.5, cell_w), fy = fmod(y + 0.5, cell_h);
    const double gap_w = fmax(1.0, cell_w / p->gap_div), gap_h = fmax(1.0, cell_h / p->gap_div);
    const bool gap = fx >= cell_w - gap_w || fy >= cell_h - gap_h;
    if (panel == RR_PANEL_DMG) return gap ? (uint32_t)p->light << 24 | p->paper : 0u;
    const int third = (int)(fx * 3.0 / (cell_w - gap_w > 1.0 ? cell_w - gap_w : 1.0));
    const double v = gap ? p->gap_level : 1.0;
    const int r = (int)lround(255.0 * v * (third == 0 ? 1.0 : p->off_level));
    const int g = (int)lround(255.0 * v * (third == 1 ? 1.0 : p->off_level));
    const int b = (int)lround(255.0 * v * (third >= 2 ? 1.0 : p->off_level));
    return 0xff000000u | (uint32_t)r << 16 | (uint32_t)g << 8 | (uint32_t)b;
}

/* The slow response: the new picture with `keep` (of 256) of the last shown one left in it, per colour. Opaque. */
static uint32_t rr_lcd_ghost_pixel(uint32_t now, uint32_t before, int keep) {
    uint32_t out = 0xff000000u;
    for (int shift = 0; shift < 24; shift += 8) {
        const int a = (int)(now >> shift & 255), b = (int)(before >> shift & 255);
        out |= (uint32_t)(a + (b - a) * keep / 256) << shift;
    }
    return out;
}
#endif
