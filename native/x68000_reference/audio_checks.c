/* Original authored register/PCM fixtures, MIT. No game/firmware data.
 * Yamaha YM2151 Application Manual: Timer A/B/control register descriptions.
 * Hitachi HD63450 datasheet: initiation/termination and CSR, pages 36-37.
 * OKI MSM6258 datasheet: command bits and low-nibble-first bus composition.
 * These checks establish bounded contracts, not complete chip/analogue fidelity.
 * See docs/X68000_AUDIO_STAGE4.md for primary sources and boundaries. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include "common.h"
#include "prop.h"
#include "adpcm.h"
#include "dmac.h"
#include "irqh.h"
#include "mfp.h"
#include "x68kmemory.h"
#include "fmg_wrap.h"
#include "libretro.h"
#include "audio_checks.h"
#include "check_compat.h"

extern int32_t my_irqh_callback(int32_t level);

typedef struct { const char *name; uint32_t expected, actual; } audio_result;
static audio_result results[18];
static unsigned result_count;
static uint32_t result_mask;

static void record(const char *name, uint32_t expected, uint32_t actual)
{
    unsigned index = result_count++;
    results[index].name = name;
    results[index].expected = expected;
    results[index].actual = actual;
    if (expected == actual) result_mask |= UINT32_C(1) << index;
}

static void opm_reg(uint8_t reg, uint8_t value)
{
    OPM_Write(0, reg);
    OPM_Write(1, value);
}

static void timer_a(unsigned reload, uint8_t control)
{
    OPM_Reset();
    opm_reg(0x10, (uint8_t)(reload >> 2));
    opm_reg(0x11, (uint8_t)(reload & 3));
    opm_reg(0x14, control);
}

static void timer_b(unsigned reload, uint8_t control)
{
    OPM_Reset();
    opm_reg(0x12, (uint8_t)reload);
    opm_reg(0x14, control);
}

/* Low byte: just before overflow, high byte: at overflow, status bits only.
 * OPM_Timer receives 10 MHz board ticks, not host microseconds. */
static uint32_t boundary_a(unsigned reload, unsigned ticks)
{
    uint32_t before;
    timer_a(reload, 5);
    OPM_Timer(ticks - 10);
    before = OPM_Read() & 3;
    OPM_Timer(10);
    return before | ((uint32_t)(OPM_Read() & 3) << 8);
}

static uint32_t boundary_b(unsigned reload, unsigned ticks)
{
    uint32_t before;
    timer_b(reload, 10);
    OPM_Timer(ticks - 10);
    before = OPM_Read() & 3;
    OPM_Timer(10);
    return before | ((uint32_t)(OPM_Read() & 3) << 8);
}

static void adpcm_vector(unsigned pan, int16_t pcm[1024])
{
    unsigned i;
    ADPCM_Init();
    ADPCM_SetClock(0);
    ADPCM_SetPan(8 | (int)pan);
    ADPCM_SetVolume(16);
    ADPCM_Write(0xe92001, 2);
    for (i = 0; i < 96; ++i)
        ADPCM_Write(0xe92003, (uint8_t)((i * 37u) ^ 0x75u));
    memset(pcm, 0, 1024 * sizeof(*pcm));
    ADPCM_Update(pcm, 512, (uint8_t *)pcm, (uint8_t *)(pcm + 1024));
}

static uint32_t adpcm_pan(void)
{
    int16_t pcm[1024];
    unsigned pan, i;
    uint32_t nonzero[2];
    uint32_t passed = 0;
    for (pan = 0; pan < 4; ++pan) {
        adpcm_vector(pan, pcm);
        nonzero[0] = nonzero[1] = 0;
        for (i = 0; i < 512; ++i) {
            nonzero[0] += pcm[i * 2] != 0;
            nonzero[1] += pcm[i * 2 + 1] != 0;
            if (pan == 0 && pcm[i * 2] != pcm[i * 2 + 1]) break;
        }
        if (i != 512) continue;
        if (((nonzero[0] != 0) == ((pan & 2) == 0)) &&
            ((nonzero[1] != 0) == ((pan & 1) == 0)))
            passed |= UINT32_C(1) << pan;
    }
    return passed;
}

static uint32_t adpcm_reset_replay(void)
{
    int16_t first[1024], second[1024];
    unsigned i;
    adpcm_vector(0, first);
    /* Same ratebits as initialization: SetPan alone cannot reset the phase. */
    ADPCM_Init();
    ADPCM_SetPan(11);
    ADPCM_Write(0xe92001, 2);
    for (i = 0; i < 7; ++i) ADPCM_Write(0xe92003, 0x71);
    adpcm_vector(0, second);
    return memcmp(first, second, sizeof(first)) == 0;
}

/* Exercise real serialized FM feedback history. Comparing only register values
 * would miss the audible discontinuity caused by clearing operator 0's history
 * while rebuilding the restored algorithm's derived connection pointers. */
static uint32_t opm_snapshot_pcm(unsigned random_lfo)
{
    int16_t warm[1024], expected[512], actual[512];
    unsigned i, nonzero = 0;
    const size_t size = retro_serialize_size();
    void *snapshot = size && size <= 64u * 1024u * 1024u ? malloc(size) : NULL;
    uint32_t result = 0;
    if (!snapshot) return 0;
    OPM_Reset();
    OPM_SetVolume(16);
    /* Channel 0: both outputs, serial algorithm, maximum feedback. */
    opm_reg(0x20, 0xf8);
    opm_reg(0x28, 0x4a);
    opm_reg(0x30, 0);
    for (i = 0; i < 4; ++i) {
        const unsigned slot = i * 8;
        opm_reg((uint8_t)(0x40 + slot), 1);    /* DT=0, multiplier=1. */
        opm_reg((uint8_t)(0x60 + slot), 0x18); /* Authored level. */
        opm_reg((uint8_t)(0x80 + slot), 0x1f); /* Fast attack. */
        opm_reg((uint8_t)(0xa0 + slot), 0);
        opm_reg((uint8_t)(0xc0 + slot), 0);
        opm_reg((uint8_t)(0xe0 + slot), 0x0f);
    }
    if (random_lfo) {
        opm_reg(0x18, 0xff); /* Fast sample-and-hold LFO. */
        opm_reg(0x19, 0x7f); /* AM depth. */
        opm_reg(0x19, 0xff); /* PM depth. */
        opm_reg(0x38, 0x73); /* Channel 0 AM/PM sensitivity. */
        opm_reg(0x1b, 3);
    }
    opm_reg(8, 0x78); /* All four operators key on, channel 0. */
    memset(warm, 0, sizeof(warm));
    OPM_Update(warm, 512, (uint8_t *)warm, (uint8_t *)(warm + 1024));
    if (!retro_serialize(snapshot, size)) goto done;
    memset(expected, 0, sizeof(expected));
    OPM_Update(expected, 256, (uint8_t *)expected, (uint8_t *)(expected + 512));
    /* Advance sound beyond the saved point before loading it. */
    memset(warm, 0, sizeof(warm));
    OPM_Update(warm, 512, (uint8_t *)warm, (uint8_t *)(warm + 1024));
    if (random_lfo) { srand(123); for (i = 0; i < 19; ++i) (void)rand(); }
    if (!retro_unserialize(snapshot, size)) goto done;
    memset(actual, 0, sizeof(actual));
    OPM_Update(actual, 256, (uint8_t *)actual, (uint8_t *)(actual + 512));
    for (i = 0; i < 512; ++i) nonzero += expected[i] != 0;
    result = nonzero && memcmp(expected, actual, sizeof(expected)) == 0;
done:
    free(snapshot);
    return result;
}

#define DMA3_BASE UINT32_C(0xe840c0)
#define DATA_BASE UINT32_C(0x1fe000)

static void dma_reg(unsigned offset, uint8_t data)
{
    DMA_Write(DMA3_BASE + offset, data);
}

static void dma_address(unsigned offset, uint32_t value)
{
    dma_reg(offset + 1, (uint8_t)(value >> 16));
    dma_reg(offset + 2, (uint8_t)(value >> 8));
    dma_reg(offset + 3, (uint8_t)value);
}

static void dma_setup(unsigned count)
{
    unsigned i;
    IRQH_Init();
    DMA_Init();
    ADPCM_Init();
    ADPCM_SetPan(8);
    ADPCM_Write(0xe92001, 2);
    for (i = 0; i < 4; ++i)
        cpu_writemem24(DATA_BASE + i, (uint8_t)(0x17u + i * 0x21u));
    dma_reg(4, 0);       /* 8-bit device port. */
    dma_reg(5, 0x33);    /* Byte/no packing; first auto-request, then external. */
    dma_reg(6, 4);       /* Memory increments, device fixed. */
    dma_reg(10, (uint8_t)(count >> 8));
    dma_reg(11, (uint8_t)count);
    dma_address(12, DATA_BASE);
    dma_address(20, 0xe92003);
    dma_reg(0x25, 0x73);
    dma_reg(0x27, 0x74);
    dma_reg(7, 0x88);    /* Start, interrupt enable. */
}

static uint32_t dma_complete(void)
{
    unsigned i;
    dma_setup(4);
    for (i = 0; i < 3; ++i) DMA_Exec(3);
    if (DMA[3].MTC != 0 || DMA[3].MAR != DATA_BASE + 4 ||
        DMA[3].DAR != 0xe92003 || DMA[3].CER != 0 ||
        (DMA[3].CSR & 0x98) != 0x80) return 0;
    return (uint32_t)my_irqh_callback(3);
}

static uint32_t dma_halt(void)
{
    unsigned count, address;
    dma_setup(4);
    dma_reg(7, 0x28);
    count = DMA[3].MTC;
    address = DMA[3].MAR;
    DMA_Exec(3);
    return DMA[3].MTC == count && DMA[3].MAR == address &&
        (DMA[3].CSR & 0x08) != 0;
}

static uint32_t dma_error(unsigned count, unsigned abort)
{
    uint32_t vector;
    dma_setup(count);
    if (abort) dma_reg(7, 0x18);
    vector = (uint32_t)my_irqh_callback(3);
    if (vector != 0x74) return 0;
    /* Actual packs CER and relevant CSR; independent manual expectation. */
    return DMA[3].CER | ((uint32_t)(DMA[3].CSR & 0x98) << 8);
}

uint32_t rr_x68k_audio_checks(const char *json_path)
{
    FILE *file;
    unsigned i;
    uint32_t before, actual;
    uint8_t saved_ram[4];
    int saved_lpf = Config.Sound_LPF;
    result_count = 0;
    result_mask = 0;
    for (i = 0; i < 4; ++i) saved_ram[i] = cpu_readmem24(DATA_BASE + i);
    Config.Sound_LPF = 0;
    IRQH_Init();
    MFP_Init();
    record("ym2151_timer_a_16us", 0x100, boundary_a(1023, 160));
    record("ym2151_timer_b_256us", 0x200, boundary_b(255, 2560));
    record("ym2151_timer_a_32us", 0x100, boundary_a(1022, 320));
    record("ym2151_timer_b_512us", 0x200, boundary_b(254, 5120));

    timer_a(1023, 5);
    OPM_Timer(160);
    before = OPM_Read() & 3;
    opm_reg(0x14, 0x10);
    record("ym2151_flag_clear", 1, before | ((uint32_t)(OPM_Read() & 3) << 8));
    timer_a(1023, 1); /* Load enabled, IRQ/status flag disabled. */
    OPM_Timer(1600);
    record("ym2151_status_enable", 0, OPM_Read() & 3);
    timer_a(1023, 5);
    OPM_Timer(80);
    opm_reg(0x14, 4); /* Stop loaded timer; status must stay clear. */
    OPM_Timer(10000);
    record("ym2151_stop_timer", 0, OPM_Read() & 3);
    timer_a(1023, 5);
    for (i = 0; i < 159; ++i) OPM_Timer(1);
    before = OPM_Read() & 3;
    OPM_Timer(1);
    record("ym2151_fractional_board_ticks", 0x100,
        before | ((uint32_t)(OPM_Read() & 3) << 8));
    timer_a(1023, 5);
    OPM_Timer(9); /* Dirty wrapper sub-microsecond accumulator, then reset. */
    timer_a(1023, 5);
    OPM_Timer(159);
    before = OPM_Read() & 3;
    OPM_Timer(1);
    record("ym2151_reset_fractional_phase", 0x100,
        before | ((uint32_t)(OPM_Read() & 3) << 8));

    IRQH_Init();
    MFP_Init();
    MFP[MFP_IERB] = MFP[MFP_IMRB] = 8;
    MFP[MFP_IPRA] = MFP[MFP_IPRB] = 0;
    MFP[MFP_ISRA] = MFP[MFP_ISRB] = 0;
    MFP[MFP_VR] = 0x40;
    timer_a(1023, 5);
    OPM_Timer(160);
    before = MFP[MFP_IPRB] & 8;
    actual = (uint32_t)my_irqh_callback(6);
    if (before != 8 || (MFP[MFP_IPRB] & 8) != 0) actual = 0;
    record("ym2151_mfp_interrupt_vector", 0x43, actual);

    DMA_Init();
    record("adpcm_stereo_pan", 15, adpcm_pan());
    record("adpcm_reset_pcm_replay", 1, adpcm_reset_replay());
    record("audio_dma_completion_vector", 0x73, dma_complete());
    record("audio_dma_halt_preserves_transfer", 1, dma_halt());
    record("audio_dma_software_abort_coc_err", 0x9011, dma_error(4, 1));
    record("audio_dma_zero_count_coc_err", 0x900d, dma_error(0, 0));
    record("ym2151_snapshot_exact_pcm_resume", 1, opm_snapshot_pcm(0));
    record("ym2151_random_lfo_snapshot_and_host_independence", 1, opm_snapshot_pcm(1));

    for (i = 0; i < 4; ++i) cpu_writemem24(DATA_BASE + i, saved_ram[i]);
    Config.Sound_LPF = saved_lpf;
    file = json_path ? fopen(json_path, "wb") : NULL;
    if (!file) return 0;
    fprintf(file, "{\"schema\":1,\"destructive_after_capture\":true,"
        "\"expected_mask\":%u,\"passed_mask\":%u,\"checks\":[",
        RR_X68K_AUDIO_EXPECTED, result_mask);
    for (i = 0; i < result_count; ++i) {
        fprintf(file, "%s{\"name\":\"%s\",\"expected\":%u,\"actual\":%u,\"passed\":%s}",
            i ? "," : "", results[i].name, results[i].expected,
            results[i].actual, results[i].expected == results[i].actual ? "true" : "false");
    }
    fprintf(file, "]}\n");
    if (fclose(file) != 0) return 0;
    return result_mask;
}
