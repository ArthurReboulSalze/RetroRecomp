/* Original authored state-continuation fixtures, MIT. No game or BIOS bytes.
 * Each fixture saves an active device, records its actual continuation, dirties
 * that device, restores it, then repeats the same bounded continuation. These
 * are state completeness checks, not an independent claim of chip fidelity.
 * Run after all game reports: deliberately resets devices and guest RAM.
 */
#include "session_checks.h"
#include "common.h"
#include "libretro.h"
#include "prop.h"
#include "m68000.h"
#include "x68k/x68kmemory.h"
#include "x68k/dmac.h"
#include "x68k/mfp.h"
#include "x68k/irqh.h"
#include "x68k/adpcm.h"
#include "x68k/scc.h"
#include "x68k/crtc.h"
#include "libretro/dswin.h"
#include "libretro/keyboard.h"
#include "libretro/joystick.h"
#include "libretro/mouse.h"
#include "fmgen/fmg_wrap.h"
#include "check_compat.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

extern uint8_t *pbsp, *pbrp, *pbwp, *pbep;
extern int8_t MouseX, MouseY;
extern uint8_t MouseSt;
extern uint8_t CRTC_SispScan;
extern int32_t my_irqh_callback(int32_t level);
static uint8_t *snapshot;
static size_t snapshot_size;
static int save(void) { return retro_serialize(snapshot, snapshot_size); }
static int restore(void) { return retro_unserialize(snapshot, snapshot_size); }
static void mw(unsigned reg, uint8_t value) { MFP_Write(0xe88001u + reg * 2u, value); }
static void opm_reg(uint8_t reg, uint8_t value) { OPM_Write(0, reg); OPM_Write(1, value); }
/* Match the board scheduler's bounded service intervals; the upstream mixer's
 * 32-bit clock product is not an API for submitting a full frame at once. */
static void sound_ticks(unsigned clocks)
{
    while (clocks > 10000) { DSound_Send0(10000); clocks -= 10000; }
    DSound_Send0((int32_t)clocks);
}

static void tone(void)
{
    OPM_Reset(); OPM_SetVolume(16);
    opm_reg(0x20, 0xf8); opm_reg(0x28, 0x4a); opm_reg(0x30, 0);
    for (unsigned i = 0; i < 4; ++i) {
        unsigned slot = i * 8;
        opm_reg((uint8_t)(0x40 + slot), 1);
        opm_reg((uint8_t)(0x60 + slot), 0x18);
        opm_reg((uint8_t)(0x80 + slot), 0x1f);
        opm_reg((uint8_t)(0xa0 + slot), 0);
        opm_reg((uint8_t)(0xc0 + slot), 0);
        opm_reg((uint8_t)(0xe0 + slot), 0x0f);
    }
    opm_reg(8, 0x78);
}

static int pcm_queue(void)
{
    int16_t expected[1024], actual[1024], dirty[1024];
    unsigned nonzero = 0;
    int before, expected_available;
    pbrp = pbwp = pbsp;
    memset(pbsp, 0, (size_t)(pbep - pbsp));
    ADPCM_Init(); tone(); sound_ticks(100003);
    before = audio_samples_avail();
    if (before < 441 || before > 442 || !save()) return 0;
    sound_ticks(22000);
    expected_available = audio_samples_avail();
    if (expected_available < 538 || expected_available > 539) return 0;
    raudio_callback(expected, NULL, sizeof expected);
    sound_ticks(33000); raudio_callback(dirty, NULL, 512);
    if (!restore() || audio_samples_avail() != before) return 0;
    sound_ticks(22000);
    if (audio_samples_avail() != expected_available) return 0;
    raudio_callback(actual, NULL, sizeof actual);
    for (unsigned i = 0; i < 1024; ++i) nonzero += expected[i] != 0;
    return nonzero && memcmp(expected, actual, sizeof expected) == 0;
}

static int pcm_queue_wrap(void)
{
    uint8_t expected[128], actual[128], dirty[128];
    /* Real queue consumer crosses the ring end. Stored offsets are relative,
     * which also permits the new process to use a different buffer address. */
    pbrp = pbep - 64; pbwp = pbsp + 64;
    for (unsigned i = 0; i < 64; ++i) {
        pbep[-64 + (int)i] = (uint8_t)(i * 3u + 1u);
        pbsp[i] = (uint8_t)(i * 5u + 7u);
    }
    if (!save() || audio_samples_avail() != 32) return 0;
    raudio_callback(expected, NULL, sizeof expected);
    memset(pbsp, 0x99, (size_t)(pbep - pbsp));
    pbrp = pbsp; pbwp = pbsp + sizeof dirty;
    raudio_callback(dirty, NULL, sizeof dirty);
    if (!restore() || audio_samples_avail() != 32) return 0;
    raudio_callback(actual, NULL, sizeof actual);
    return audio_samples_avail() == 0 && memcmp(expected, actual, sizeof expected) == 0;
}

static int adpcm_queue(void)
{
    int16_t warm[1024], expected[1024], actual[1024];
    ADPCM_Init(); ADPCM_SetClock(0); ADPCM_SetPan(8); ADPCM_SetVolume(16);
    ADPCM_Write(0xe92001, 2);
    for (unsigned i = 0; i < 128; ++i)
        ADPCM_Write(0xe92003, (uint8_t)((i * 37u) ^ 0x75u));
    memset(warm, 0, sizeof warm);
    ADPCM_Update(warm, 93, (uint8_t *)warm, (uint8_t *)(warm + 1024));
    if (!save()) return 0;
    memset(expected, 0, sizeof expected);
    ADPCM_Update(expected, 512, (uint8_t *)expected, (uint8_t *)(expected + 1024));
    ADPCM_Init(); ADPCM_SetPan(11); ADPCM_Write(0xe92001, 2);
    for (unsigned i = 0; i < 16; ++i) ADPCM_Write(0xe92003, 0x99);
    if (!restore()) return 0;
    memset(actual, 0, sizeof actual);
    ADPCM_Update(actual, 512, (uint8_t *)actual, (uint8_t *)(actual + 1024));
    unsigned nonzero = 0;
    for (unsigned i = 0; i < 1024; ++i) nonzero += expected[i] != 0;
    return nonzero && memcmp(expected, actual, sizeof expected) == 0;
}

static int keyboard_queue(void)
{
    uint8_t expected[3], actual[3];
    Keyboard_Init();
    send_keycode(0x2c, 2); send_keycode(0x2c, 1); send_keycode(0x2d, 2);
    if (!save()) return 0;
    for (unsigned i = 0; i < 3; ++i) { KeyIntFlag = 0; Keyboard_Int(); expected[i] = LastKey; }
    Keyboard_Init(); send_keycode(0x19, 2); Keyboard_Int();
    if (!restore()) return 0;
    for (unsigned i = 0; i < 3; ++i) { KeyIntFlag = 0; Keyboard_Int(); actual[i] = LastKey; }
    return expected[0] == 0x2c && expected[1] == 0xac && expected[2] == 0x2d &&
        memcmp(expected, actual, sizeof expected) == 0;
}

static int mouse_pending(void)
{
    Mouse_StartCapture(1); Mouse_SetData();
    Mouse_Event(1, 1, 0); Mouse_Event(2, 0, 0); Mouse_Event(0, 12, -7);
    if (!save()) return 0;
    Mouse_SetData();
    if (MouseX != 12 || MouseY != -7 || MouseSt != 1) return 0;
    Mouse_Event(0, 99, 52); Mouse_Event(1, 0, 0); Mouse_StartCapture(0);
    if (!restore()) return 0;
    Mouse_SetData();
    return MouseX == 12 && MouseY == -7 && MouseSt == 1;
}

static void scc_reg(unsigned reg, uint8_t value) { SCC_Write(0xe98001u, (uint8_t)reg); SCC_Write(0xe98001u, value); }
static int scc_packet(void)
{
    uint8_t expected[2], actual[2];
    SCC_Init(); Mouse_StartCapture(1); Mouse_SetData();
    Mouse_Event(1, 1, 0); Mouse_Event(2, 0, 0); Mouse_Event(0, 17, -9);
    scc_reg(3, 1); scc_reg(5, 0); scc_reg(5, 2);
    if (SCC_Read(0xe98003u) != 1 || !save()) return 0;
    expected[0] = SCC_Read(0xe98003u); expected[1] = SCC_Read(0xe98003u);
    SCC_Init(); scc_reg(3, 1);
    if (!restore()) return 0;
    actual[0] = SCC_Read(0xe98003u); actual[1] = SCC_Read(0xe98003u);
    return expected[0] == 17 && expected[1] == (uint8_t)-9 &&
        memcmp(expected, actual, sizeof expected) == 0;
}

static int joystick_phase(void)
{
    uint8_t expected[30], actual[30];
    Config.JOY_TYPE[0] = PAD_CYBERSTICK_A;
    Joystick_Init(); Joystick_Write(0, 0xff); Joystick_Write(0, 0);
    for (unsigned i = 0; i < 5; ++i) (void)Joystick_Read(0);
    if (!save()) return 0;
    for (unsigned i = 0; i < 30; ++i) expected[i] = Joystick_Read(0);
    Joystick_Init(); for (unsigned i = 0; i < 18; ++i) (void)Joystick_Read(0);
    if (!restore()) return 0;
    for (unsigned i = 0; i < 30; ++i) actual[i] = Joystick_Read(0);
    return memcmp(expected, actual, sizeof expected) == 0;
}

static void dw(unsigned offset, uint8_t value) { DMA_Write(0xe84080u + offset, value); }
static void da(unsigned offset, uint32_t value)
{
    dw(offset + 1, (uint8_t)(value >> 16)); dw(offset + 2, (uint8_t)(value >> 8));
    dw(offset + 3, (uint8_t)value);
}
static int dma_pending(void)
{
    uint8_t expected[16], actual[16];
    IRQH_Init(); DMA_Init();
    for (unsigned i = 0; i < 16; ++i) {
        dma_writemem24(0x1fc000u + i, (uint8_t)(11u + i * 7u));
        dma_writemem24(0x1fc040u + i, 0);
    }
    dw(4, 8); dw(5, 0); dw(6, 5); dw(10, 0); dw(11, 16);
    da(12, 0x1fc000u); da(20, 0x1fc040u); dw(0x25, 0x73); dw(0x27, 0x74);
    dw(7, 0x88); DMA_Exec(2); DMA_Exec(2);
    if (DMA[2].MTC != 13 || !save()) return 0;
    for (unsigned i = 0; i < 13; ++i) DMA_Exec(2);
    for (unsigned i = 0; i < 16; ++i) expected[i] = dma_readmem24(0x1fc040u + i);
    if (DMA[2].MTC || my_irqh_callback(3) != 0x73) return 0;
    DMA_Init(); IRQH_Init();
    for (unsigned i = 0; i < 16; ++i) dma_writemem24(0x1fc040u + i, 0xff);
    if (!restore() || DMA[2].MTC != 13) return 0;
    for (unsigned i = 0; i < 13; ++i) DMA_Exec(2);
    for (unsigned i = 0; i < 16; ++i) actual[i] = dma_readmem24(0x1fc040u + i);
    return !DMA[2].MTC && my_irqh_callback(3) == 0x73 &&
        memcmp(expected, actual, sizeof expected) == 0;
}

static int mfp_pending(void)
{
    uint32_t expected, actual;
    IRQH_Init(); MFP_Init();
    mw(MFP_IERA, 0x20); mw(MFP_IMRA, 0x20); mw(MFP_IPRA, 0);
    mw(MFP_ISRA, 0); mw(MFP_VR, 0x40); mw(MFP_TACR, 0);
    mw(MFP_TADR, 3); mw(MFP_TACR, 1); MFP_Timer(25);
    if (MFP[MFP_TADR] != 1 || !save()) return 0;
    MFP_Timer(4); if (MFP[MFP_IPRA]) return 0;
    MFP_Timer(1); expected = (uint32_t)my_irqh_callback(6);
    IRQH_Init(); MFP_Init();
    if (!restore()) return 0;
    MFP_Timer(4); if (MFP[MFP_IPRA]) return 0;
    MFP_Timer(1); actual = (uint32_t)my_irqh_callback(6);
    return expected == 0x4d && actual == expected;
}

static int irq_callback_rebuild(void)
{
    IRQH_Init(); MFP_Init();
    mw(MFP_IERA, 0x20); mw(MFP_IMRA, 0x20); mw(MFP_IPRA, 0);
    mw(MFP_ISRA, 0); mw(MFP_VR, 0x40); mw(MFP_TACR, 0);
    mw(MFP_TADR, 1); mw(MFP_TACR, 1); MFP_Timer(10);
    if (MFP[MFP_IPRA] != 0x20 || !save()) return 0;
    /* Discard this process's callback pointers, as a fresh process does. */
    IRQH_Init();
    if (!restore()) return 0;
    return my_irqh_callback(6) == 0x4d && MFP[MFP_IPRA] == 0;
}

static int video_clear_phase(void)
{
    CRTC_FastClrLine = 97; CRTC_SispScan = 1;
    if (!save()) return 0;
    CRTC_FastClrLine = 0; CRTC_SispScan = 0;
    return restore() && CRTC_FastClrLine == 97 && CRTC_SispScan == 1;
}

uint32_t rr_x68k_session_checks(const char *json_path)
{
    static const struct { const char *name; int (*run)(void); } cases[] = {
        {"queued_pcm_and_fractional_clock_resume", pcm_queue},
        {"queued_pcm_wrap_and_pointer_rebuild", pcm_queue_wrap},
        {"adpcm_pending_decode_exact_pcm_resume", adpcm_queue},
        {"keyboard_pending_make_break_order", keyboard_queue},
        {"mouse_pending_motion_buttons_capture", mouse_pending},
        {"scc_partial_mouse_packet_resume", scc_packet},
        {"joystick_cyberstick_handshake_resume", joystick_phase},
        {"active_external_dma_exact_resume", dma_pending},
        {"mfp_fractional_prescaler_irq_resume", mfp_pending},
        {"pending_irq_callback_process_rebuild", irq_callback_rebuild},
        {"video_clear_scan_progress_resume", video_clear_phase},
    };
    FILE *out = json_path ? fopen(json_path, "wb") : NULL;
    uint32_t mask = 0;
    int saved_joy_type = Config.JOY_TYPE[0], saved_lpf = Config.Sound_LPF;
    snapshot_size = retro_serialize_size();
    snapshot = snapshot_size && snapshot_size <= 64u * 1024u * 1024u ? malloc(snapshot_size) : NULL;
    if (!out || !snapshot) { if (out) fclose(out); free(snapshot); return 0; }
    Config.Sound_LPF = 0;
    fputs("{\"schema\":1,\"kind\":\"authored-state-continuation\",\"destructive_after_capture\":true,\"cases\":[", out);
    for (unsigned i = 0; i < sizeof cases / sizeof cases[0]; ++i) {
        int ok = cases[i].run();
        if (ok) mask |= UINT32_C(1) << i;
        fprintf(out, "%s{\"name\":\"%s\",\"passed\":%s}", i ? "," : "", cases[i].name, ok ? "true" : "false");
    }
    fprintf(out, "],\"mask\":%u,\"expected_mask\":%u,\"state_bytes\":%zu,\"passed\":%s}\n",
        mask, RR_X68K_SESSION_EXPECTED, snapshot_size, mask == RR_X68K_SESSION_EXPECTED ? "true" : "false");
    Config.JOY_TYPE[0] = saved_joy_type; Config.Sound_LPF = saved_lpf;
    free(snapshot); snapshot = NULL;
    if (fclose(out)) return 0;
    return mask;
}
