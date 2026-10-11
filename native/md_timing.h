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
/* Standard H32/H40 only. Phase zero is the scheduler's V-counter increment
 * (external H=85/A5), not the leftmost visible pixel. Horizontal divider
 * changes around HSYNC produce short B6/E4 and long E6..F7 intervals in H40.
 * Numeric timing facts checked against Genesis Plus GX core/hvc.h; no table
 * or implementation from that engine is distributed. See MD video notes. */
static inline unsigned rr_md_hcounter(unsigned phase, int h40) {
    phase %= RR_MD_MASTER_PER_LINE;
    if (!h40) {
        unsigned n = 0x85u + phase / 20u;
        if (n > 0x93u) n += 0x55u;
        return n & 255u;
    }
    if (phase < 280u) return 0xa5u + phase / 16u;
    if (phase < 304u) return phase < 288u ? 0xe4u : 0xe5u;
    if (phase < 652u) {
        static const unsigned edges[] = {321,341,361,381,399,419,439,459,478,
                                         497,517,537,557,575,595,615,635,652};
        unsigned n=0;
        while (phase >= edges[n]) ++n;
        return 0xe6u+n;
    }
    return (0xf8u + (phase-652u)/16u) & 255u;
}
/* Logic-analyser transitions: internal H=126..00A (H32),
 * H=166.5..00B.5 (H40). Read count cannot move either boundary. */
static inline int rr_md_hblank(unsigned phase, int h40) {
    phase %= RR_MD_MASTER_PER_LINE;
    return phase >= (h40 ? 228u : 280u) && phase < (h40 ? 872u : 860u);
}
#endif
