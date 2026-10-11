/* Authored raster and simulation-clock fixtures. No cartridge is needed. */
#include <stdio.h>
#include <stdlib.h>
#include "md_timing.h"
#include "sim_step.h"
#include "video/genesis_vdp.h"
#define REQUIRE(ok, text) do { if (!(ok)) { fprintf(stderr, "FAIL: %s\n", text); exit(1); } } while (0)
static unsigned rasters, arms, vblanks, endings, drains;
static uint64_t audio_clocks;
static unsigned phase;
unsigned machine_vdp_phase(void) { return phase; }
void glue_reset_frame_sync(void) { ++arms; }
void glue_run_game_frame(void) {}
void glue_sched_frame_begin(void) {}
void glue_service_vblank(void) { ++vblanks; }
void glue_end_of_wall_frame(void) { ++endings; }
void machine_set_pad_type(int port, int type) { (void)port; (void)type; }
void machine_set_pad(int port, uint16_t value) { (void)port; (void)value; }
void machine_run_frame(GenesisScanlineSink sink, void *user) { (void)sink; (void)user; ++rasters; }
void audio_mixer_drain(uint32_t clocks, int16_t *fm, size_t fm_cap, size_t *fm_written,
                       int16_t *psg, size_t psg_cap, size_t *psg_written) {
    (void)fm; (void)fm_cap; (void)psg; (void)psg_cap;
    audio_clocks += clocks; ++drains; *fm_written = *psg_written = 0;
}
int main(void) {
    REQUIRE(rr_md_hcounter(0,0)==0x85 && rr_md_hcounter(0,1)==0xa5, "line origin H counter");
    REQUIRE(rr_md_hcounter(299,0)==0x93 && rr_md_hcounter(300,0)==0xe9, "H32 counter discontinuity");
    REQUIRE(rr_md_hcounter(279,1)==0xb6 && rr_md_hcounter(280,1)==0xe4, "H40 counter discontinuity");
    REQUIRE(rr_md_hcounter(759,0)==0xff && rr_md_hcounter(760,0)==0, "H32 counter wraps");
    REQUIRE(rr_md_hcounter(779,1)==0xff && rr_md_hcounter(780,1)==0, "H40 counter wraps");
    for (int h40=0;h40<2;++h40) {
        GVDP v; gvdp_init(&v); v.reg[12]=h40?0x81:0;
        unsigned start=h40?228:280, end=h40?872:860;
        phase=start-1; REQUIRE(!(gvdp_read_control(&v)&4), "before HBlank");
        phase=start; REQUIRE(gvdp_read_control(&v)&4, "HBlank begins with elapsed clocks");
        for (int n=0;n<100;++n) REQUIRE(gvdp_read_control(&v)&4, "status reads cannot advance beam");
        phase=end-1; REQUIRE(gvdp_peek_status(&v)&4, "HBlank stays until boundary");
        phase=end; REQUIRE(!(gvdp_read_control(&v)&4), "HBlank ends with elapsed clocks");
        v.sprite_collision=v.sprite_overflow=v.vint_pending=1;
        REQUIRE((gvdp_read_control(&v)&0xe0)==0xe0, "return latched status before clearing");
        REQUIRE(!(gvdp_read_control(&v)&0xe0), "read clears collision overflow and V interrupt flags");
    }
    phase=0;
    REQUIRE(RR_MD_LINES == (RR_MD_PAL ? 313u : 262u), "progressive raster line count");
    REQUIRE(RR_MD_MASTER_HZ == (RR_MD_PAL ? 53203424u : 53693175u), "console oscillator");
    REQUIRE(RR_MD_FRAME_MASTER == (RR_MD_PAL ? 1070460u : 896040u), "one complete raster clock span");
    double fps = 1.0 / RR_MD_FRAME_SECONDS;
    REQUIRE(fps > (RR_MD_PAL ? 49.700 : 59.922) && fps < (RR_MD_PAL ? 49.702 : 59.924),
            "presentation follows the simulated raster clock");
    for (unsigned v30 = 0; v30 < 2; ++v30) {
        GVDP v; gvdp_init(&v); v.reg[1] = 0x20 | (v30 ? 8 : 0);
        unsigned irqs = 0;
        for (unsigned line = 0; line < RR_MD_LINES; ++line) {
            unsigned irq = gvdp_begin_scanline(&v, line), expected;
            /* Explicit published counter segments. NTSC V30 rolling display
             * is outside this progressive fixture's hardware claims. */
            if (RR_MD_PAL) {
                unsigned first = v30 ? 267 : 259;
                expected = line < first ? line & 255 : (v30 ? 0xd2 : 0xca) + line - first;
            } else expected = !v30 && line >= 235 ? 0xe5 + line - 235 : line & 255;
            REQUIRE((gvdp_read_hv_counter(&v) >> 8) == expected, "guest-visible V counter sequence");
            REQUIRE((gvdp_peek_status(&v) & 1) == RR_MD_PAL, "PAL status without read side effects");
            if (irq & GVDP_IRQ_VBLANK) {
                ++irqs; REQUIRE(line == (v30 ? 240u : 224u), "V interrupt at active-height boundary");
            }
        }
        REQUIRE(irqs == 1, "one V interrupt per raster");
        v.control_pending = 1; v.vint_pending = 1;
        REQUIRE((gvdp_read_control(&v) & 1) == RR_MD_PAL && !v.control_pending && !v.vint_pending,
                "status read retains PAL and consumes pending command/IRQ flags");
    }
    for (unsigned i = 0; i < 6000; ++i) REQUIRE(genesis_sim_step(NULL, NULL, NULL), "simulation tick");
    REQUIRE(arms == 6000 && rasters == 6000 && vblanks == 6000 && endings == 6000 && drains == 6000
            && genesis_sim_tick_count() == 6000, "one raster, audio drain and bookkeeping pass per tick");
    REQUIRE(audio_clocks == (RR_MD_PAL ? 6422760000ull : 5376240000ull), "cumulative audio/video clocks");
    printf("{\"standard\":\"%s\",\"raster_lines\":%u,\"frames_per_second\":%.9f,"
           "\"simulated_frames\":6000,\"audio_master_clocks\":%llu,\"passed\":true}\n",
           RR_MD_PAL ? "pal" : "ntsc", RR_MD_LINES, fps, audio_clocks);
    return 0;
}
