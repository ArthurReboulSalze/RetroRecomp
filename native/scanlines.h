/* Presentation-only CRT gaps, one per guest raster row. Original code. */
#ifndef RETRO_SCANLINES_H
#define RETRO_SCANLINES_H
#include <stdint.h>

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
#endif
