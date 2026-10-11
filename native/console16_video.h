#ifndef RR_CONSOLE16_VIDEO_H
#define RR_CONSOLE16_VIDEO_H
#include <stdint.h>
#include <string.h>

/* Storage rows and display geometry differ in MD interlace mode 2: two
 * woven rows occupy the height of one progressive raster line. */
typedef struct Rr16Rect { int x, y, w, h; } Rr16Rect;
static inline Rr16Rect rr16_video_rect(int canvas_w, int canvas_h, int width,
                                     int raster_height, int row_density,
                                     int integer_scale) {
    Rr16Rect r = {0, 0, 0, 0};
    if (canvas_w <= 0 || canvas_h <= 0 || width <= 0 || raster_height <= 0 || row_density <= 0)
        return r;
    double scale = (double)canvas_w / width;
    if ((double)canvas_h / raster_height < scale) scale = (double)canvas_h / raster_height;
    /* IM2 needs X=2n, Y=n for integer texture pixels and the original aspect.
     * On a smaller canvas fit the entire image rather than cropping it. */
    if (integer_scale && scale >= row_density)
        scale = ((int)scale / row_density) * row_density;
    r.w = (int)(width * scale); r.h = (int)(raster_height * scale);
    r.x = (canvas_w - r.w) / 2; r.y = (canvas_h - r.h) / 2;
    return r;
}
static inline int rr16_video_copy_row(uint32_t *pixels, int stride, int rows,
                                     int line, const uint32_t *source, int width) {
    if (!pixels || !source || stride <= 0 || line < 0 || line >= rows || width <= 0 || width > stride)
        return 0;
    memcpy(pixels + (size_t)line * stride, source, (size_t)width * sizeof *source);
    return 1;
}
/* Hash the visible image, not unused backing margins. Geometry is part of
 * the evidence: progressive/interlace images cannot silently hash alike. */
static inline uint64_t rr16_video_hash(const uint32_t *pixels, int stride, int width,
                                      int height, int raster_height) {
    uint64_t h = 14695981039346656037ull;
    h = (h ^ (unsigned)width) * 1099511628211ull;
    h = (h ^ (unsigned)height) * 1099511628211ull;
    h = (h ^ (unsigned)raster_height) * 1099511628211ull;
    for (int y = 0; y < height; ++y) for (int x = 0; x < width; ++x)
        h = (h ^ pixels[(size_t)y * stride + x]) * 1099511628211ull;
    return h;
}
#endif
