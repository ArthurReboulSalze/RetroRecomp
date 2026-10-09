#ifndef RR_MD_TIMING_H
#define RR_MD_TIMING_H
/* Master-clock facts and progressive raster counter sequences. Cartridge
 * timing is selected at conversion, independently of its filename. */
#ifndef RR_MD_PAL
#define RR_MD_PAL 0
#endif
#define RR_MD_LINES (RR_MD_PAL ? 313u : 262u)
#define RR_MD_MASTER_HZ (RR_MD_PAL ? 53203424u : 53693175u)
#define RR_MD_MASTER_PER_LINE 3420u
#define RR_MD_FRAME_MASTER (RR_MD_LINES * RR_MD_MASTER_PER_LINE)
#define RR_MD_PSG_HZ (RR_MD_MASTER_HZ / 240u)
#define RR_MD_FRAME_SECONDS ((double)RR_MD_FRAME_MASTER / RR_MD_MASTER_HZ)
static inline unsigned rr_md_vcounter(unsigned line, int v30) {
    line %= RR_MD_LINES;
    if (RR_MD_PAL) {
        if (line >= (v30 ? 267u : 259u)) line -= 57u;
    } else if (!v30 && line >= 235u) {
        line -= 6u;
    }
    return line & 255u;
}
#endif
