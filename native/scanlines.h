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

/* One bright beam per console line, a Gaussian across the line (sigma 0.24 of a line), averaged over the output row:
 * the alpha of a black overlay. No dark gaps below two output rows a line (they cannot be resolved) or above 300 lines a
 * frame (interlaced TV modes, 31 kHz monitors, the ST's mono screen: their lines were too fine to show gaps). */
#define RR_CRT_FINE_LINES 300
static uint8_t rr_crt_beam_alpha(int y, int height, int lines) {
    if (lines <= 0 || lines > RR_CRT_FINE_LINES || height < 2 * lines || y < 0 || y >= height) return 0;
    double lit = 0.0;
    for (int s = 0; s < 4; ++s) {
        const double pos = ((y + (s + 0.5) / 4.0) * lines) / height;
        const double d = pos - floor(pos) - 0.5;
        lit += exp(-(d * d) / (2.0 * 0.24 * 0.24));
    }
    const long a = lround(255.0 * 0.80 * (1.0 - lit / 4.0));
    return (uint8_t)(a < 0 ? 0 : a > 255 ? 255 : a);
}

/* The phosphor mask, screen space, multiplied over the picture (0xffRRGGBB, 0xff = keep). Kind 0: aperture grille,
 * vertical R G B stripes one output pixel wide; kind 1: slot mask, the stripes staggered every three rows with a thin gap. */
static uint32_t rr_crt_mask_texel(int x, int y, int kind) {
    const int lo = 179;                                   /* 0.70: the two unlit stripes keep 70 % */
    int phase = x % 3;
    if (kind == 1 && (y / 3) % 2) phase = (x + 1) % 3;
    int r = phase == 0 ? 255 : lo, g = phase == 1 ? 255 : lo, b = phase == 2 ? 255 : lo;
    if (kind == 1 && y % 3 == 2) { r = r * 3 / 4; g = g * 3 / 4; b = b * 3 / 4; }
    return 0xff000000u | (uint32_t)r << 16 | (uint32_t)g << 8 | (uint32_t)b;
}

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
#endif
