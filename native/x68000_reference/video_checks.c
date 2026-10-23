/* Original RetroRecomp authored X68000 video vectors, MIT.
 * See docs/history/x68000/X68000_VIDEO_STAGE4.md for sources and evidence boundaries. */
#include "video_checks.h"

#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "libretro.h"
#include "crtc.h"
#include "gvram.h"
#include "tvram.h"
#include "bg.h"
#include "palette.h"
#include "windraw.h"
#include "winx68k.h"
#include "m68000/musashi/m68k.h"

extern uint16_t *videoBuffer;
extern uint8_t Debug_Text, Debug_Grp, Debug_Sp;

struct vector_result {
    const char *name;
    unsigned comparisons, failures;
    uint32_t first_expected, first_actual;
};

struct state_difference { char field[100]; unsigned bytes; };

static uint32_t little_word(const uint8_t *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

/* Report names/counts only, never dump guest RAM or firmware contents. */
static unsigned state_differences(const void *before, const void *after, size_t size,
                                  struct state_difference differences[16])
{
    const uint8_t *a = before, *b = after;
    size_t pos = 32;
    unsigned count = 0;
    while (pos + 36 <= size) {
        char section[33];
        const uint32_t length = little_word(a + pos + 32);
        size_t end;
        memcpy(section, a + pos, 32); section[32] = 0; pos += 36;
        if (length > size - pos) break;
        end = pos + length;
        while (pos < end) {
            char field[64];
            unsigned different = 0;
            const unsigned name_length = a[pos++];
            uint32_t bytes, i;
            if (name_length > end - pos || end - pos - name_length < 4) return count;
            memcpy(field, a + pos, name_length < 63 ? name_length : 63);
            field[name_length < 63 ? name_length : 63] = 0; pos += name_length;
            bytes = little_word(a + pos); pos += 4;
            if (bytes > end - pos) return count;
            for (i = 0; i < bytes; ++i) if (a[pos + i] != b[pos + i]) ++different;
            if (different && count < 16) {
                snprintf(differences[count].field, sizeof(differences[count].field),
                         "%s/%s", section, field);
                differences[count++].bytes = different;
            }
            pos += bytes;
        }
    }
    return count;
}

static void equal(struct vector_result *r, uint32_t actual, uint32_t expected)
{
    r->comparisons++;
    if (actual != expected) {
        if (!r->failures) {
            r->first_expected = expected;
            r->first_actual = actual;
        }
        r->failures++;
    }
}

static void palette_word(uint32_t address, uint16_t value)
{
    Pal_Write(address, (uint8_t)(value >> 8));
    Pal_Write(address + 1, (uint8_t)value);
}

static void graphic_pixel(unsigned page, unsigned x, unsigned y, unsigned value)
{
    GVRAM_Write(0xc00001u + page * 0x80000u + y * 1024u + x * 2u,
                (uint8_t)value);
}

static void sprite_word(unsigned index, unsigned offset, uint16_t word)
{
    const uint32_t address = 0xeb0000u + index * 8u + offset;
    BG_Write(address, (uint8_t)(word >> 8));
    BG_Write(address + 1, (uint8_t)word);
}

static void fill_graphic_palette(void)
{
    unsigned i;
    for (i = 0; i < 256; ++i)
        GrphPal[i] = (uint16_t)(0x4000u + i);
}

static void fill_text_palette(void)
{
    unsigned i;
    for (i = 0; i < 256; ++i)
        TextPal[i] = (uint16_t)(0x5000u + i);
}

static uint16_t channel_bits(uint16_t mask)
{
    /* Display may use RGB565 or RGB555.  The guest has five primary bits:
     * select the highest five bits of each host channel independently. */
    unsigned n = 0;
    uint16_t bits = 0, b;
    for (b = 0x8000; b && n < 5; b >>= 1)
        if (mask & b) { bits |= b; ++n; }
    return bits;
}

uint32_t rr_x68k_video_checks(const char *json_path)
{
    struct vector_result r[RR_X68K_VIDEO_CHECK_COUNT] = {
        {"cold_crtc_geometry"}, {"graphics_4bpp_four_planes"},
        {"graphics_even_byte_ignored"}, {"graphics_8bpp_two_planes"},
        {"graphics_16bpp_byte_order"}, {"graphics_1024_quadrants"},
        {"graphics_horizontal_wrap_all_planes"}, {"graphics_vertical_wrap"},
        {"text_planar_pixel_bits"}, {"text_simultaneous_plane_selection"},
        {"text_mask_logical_byte_parity"}, {"text_raster_copy_selected_planes"},
        {"palette_grbi_primaries_and_intensity"}, {"video_controller_mirrors"},
        {"graphics_zero_transparency_and_page_order"}, {"sprite_index_priority"},
        {"sprite_horizontal_vertical_flip"}, {"graphics_masked_fast_clear_wrap"},
        {"text_horizontal_wrap"}, {"machine_snapshot_restored"},
        {"graphics_text_sprite_priority_composition"}
    };
    const size_t snapshot_size = retro_serialize_size();
    void *snapshot = snapshot_size ? malloc(snapshot_size) : NULL;
    void *after = snapshot_size ? malloc(snapshot_size) : NULL;
    const unsigned cpu_context_size = m68k_context_size();
    void *cpu_context = cpu_context_size && cpu_context_size <= 1024u * 1024u ?
                        malloc(cpu_context_size) : NULL;
    uint16_t *frame_before = videoBuffer ? malloc(800u * 600u * sizeof(uint16_t)) : NULL;
    uint8_t dirty_before[1024];
    const uint8_t debug_text_before = Debug_Text, debug_grp_before = Debug_Grp,
                  debug_sp_before = Debug_Sp;
    const uint32_t vline_before = VLINE;
    const uint32_t vlinebg_before = VLINEBG;
    uint32_t mask = 0;
    struct state_difference differences[16];
    unsigned difference_count = 0;
    unsigned i, page, x;
    bool restored = false;
    FILE *report;

    memcpy(dirty_before, TextDirtyLine, sizeof(dirty_before));
    if (!snapshot || !after || !frame_before || !cpu_context ||
        m68k_get_context(cpu_context) != cpu_context_size ||
        !retro_serialize(snapshot, snapshot_size))
        goto done;
    memcpy(frame_before, videoBuffer, 800u * 600u * sizeof(uint16_t));

    CRTC_Init();
    equal(&r[0], CRTC_HSTART, 28); equal(&r[0], CRTC_HEND, 124);
    equal(&r[0], CRTC_VSTART, 40); equal(&r[0], CRTC_VEND, 552);

    memset(CRTC_Regs, 0, sizeof(CRTC_Regs));
    memset(GVRAM, 0, sizeof(GVRAM));
    for (page = 0; page < 4; ++page)
        graphic_pixel(page, 17, 9, 0xa0u + page + 1u);
    for (page = 0; page < 4; ++page)
        equal(&r[1], GVRAM_Read(0xc00001u + page * 0x80000u + 9u * 1024u + 34u), page + 1u);
    for (page = 0; page < 4; ++page)
        GVRAM_Write(0xc00000u + page * 0x80000u + 9u * 1024u + 34u, 0xff);
    for (page = 0; page < 4; ++page) {
        equal(&r[2], GVRAM_Read(0xc00000u + page * 0x80000u + 9u * 1024u + 34u), 0);
        equal(&r[2], GVRAM_Read(0xc00001u + page * 0x80000u + 9u * 1024u + 34u), page + 1u);
    }

    CRTC_Regs[0x28] = 1;
    GVRAM_Write(0xc00001, 0x3c); GVRAM_Write(0xc80001, 0xa5);
    equal(&r[3], GVRAM_Read(0xc00001), 0x3c);
    equal(&r[3], GVRAM_Read(0xc80001), 0xa5);
    equal(&r[3], GVRAM_Read(0xc00000), 0);
    equal(&r[3], GVRAM_Read(0xc80000), 0);

    CRTC_Regs[0x28] = 8;
    equal(&r[4], GVRAM_Read(0xc00000), 0xa5);
    equal(&r[4], GVRAM_Read(0xc00001), 0x3c);
    GVRAM_Write(0xc00000, 0x72); GVRAM_Write(0xc00001, 0x19);
    equal(&r[4], GVRAM_Read(0xc00000), 0x72);
    equal(&r[4], GVRAM_Read(0xc00001), 0x19);

    memset(GVRAM, 0, sizeof(GVRAM)); CRTC_Regs[0x28] = 4;
    /* A 1024x1024 4bpp canvas packs its four 512x512 quadrants in the
     * same physical word's nibbles. Distinct edge pixels test both axes. */
    for (page = 0; page < 4; ++page) {
        const unsigned px = 511u + (page & 1u) * 512u;
        const unsigned py = 511u + (page >> 1u) * 512u;
        GVRAM_Write(0xc00001u + py * 2048u + px * 2u, (uint8_t)(page + 3u));
    }
    for (page = 0; page < 4; ++page) {
        const unsigned px = 511u + (page & 1u) * 512u;
        const unsigned py = 511u + (page >> 1u) * 512u;
        equal(&r[5], GVRAM_Read(0xc00001u + py * 2048u + px * 2u), page + 3u);
    }
    CRTC_Regs[0x28] = 0;
    for (page = 0; page < 4; ++page)
        equal(&r[5], GVRAM_Read(0xc00001u + page * 0x80000u + 511u * 1024u + 1022u), page + 3u);

    fill_graphic_palette(); TextDotX = 16; VLINE = 7;
    memset(GVRAM, 0, sizeof(GVRAM));
    for (page = 0; page < 4; ++page) {
        GrphScrollX[page] = 511; GrphScrollY[page] = 0;
        graphic_pixel(page, 511, 7, 11);
        for (x = 0; x < 15; ++x) graphic_pixel(page, x, 7, (x % 9) + 1);
        memset(Grp_LineBuf, 0, sizeof(Grp_LineBuf));
        Grp_DrawLine4(page, 1);
        equal(&r[6], Grp_LineBuf[0], 0x400b);
        for (x = 1; x < 16; ++x)
            equal(&r[6], Grp_LineBuf[x], 0x4000u + ((x - 1) % 9) + 1);
    }
    GrphScrollX[0] = 0; GrphScrollY[0] = 511; VLINE = 1;
    graphic_pixel(0, 0, 0, 13); Grp_DrawLine4(0, 1);
    equal(&r[7], Grp_LineBuf[0], 0x400d);

    TVRAM_Init(); fill_text_palette(); TextDotX = 16;
    TextScrollX = TextScrollY = VLINE = 0;
    for (page = 0; page < 4; ++page)
        TVRAM_Write(0xe00000u + page * 0x20000u, (uint8_t)(0x80u >> page));
    Text_DrawLine(1);
    for (x = 0; x < 4; ++x) equal(&r[8], BG_LineBuf[16 + x], 0x5000u + (1u << x));
    equal(&r[8], BG_LineBuf[20], 0x5000);

    CRTC_Regs[0x2a] = 1; CRTC_Regs[0x2b] = 0xa0;
    TVRAM_Write(0xe00020, 0x96);
    for (page = 0; page < 4; ++page)
        equal(&r[9], TVRAM_Read(0xe00020u + page * 0x20000u), (page & 1) ? 0x96 : 0);

    CRTC_Regs[0x2a] = 0;
    TVRAM_Write(0xe00040, 0xa5); TVRAM_Write(0xe00041, 0x5a);
    CRTC_Regs[0x2e] = 0xf0; CRTC_Regs[0x2f] = 0x0f; CRTC_Regs[0x2a] = 2;
    TVRAM_Write(0xe00040, 0x3c); TVRAM_Write(0xe00041, 0xc3);
    equal(&r[10], TVRAM_Read(0xe00040), 0xac);
    equal(&r[10], TVRAM_Read(0xe00041), 0xca);

    CRTC_Regs[0x2a] = 0;
    for (page = 0; page < 4; ++page)
        for (i = 0; i < 512; ++i) {
            TVRAM_Write(0xe00200u + page * 0x20000u + i, (uint8_t)(i * 13u + page + 1u));
            TVRAM_Write(0xe00400u + page * 0x20000u + i, 0x66);
        }
    CRTC_Regs[0x2b] = 5; CRTC_Regs[0x2c] = 1; CRTC_Regs[0x2d] = 2;
    CRTC_RasterCopy();
    for (page = 0; page < 4; ++page)
        for (i = 0; i < 512; ++i)
            equal(&r[11], TVRAM_Read(0xe00400u + page * 0x20000u + i),
                  (page & 1) ? 0x66 : (uint8_t)(i * 13u + page + 1u));
    TextScrollY = 8; Text_DrawLine(1);
    equal(&r[11], BG_LineBuf[16], 0x5000);
    equal(&r[11], BG_LineBuf[22], 0x500e);
    equal(&r[11], BG_LineBuf[23], 0x5005);

    Pal_SetColor();
    memset(Pal_Regs, 0xff, sizeof(Pal_Regs));
    palette_word(0xe82000, 0x07c0); palette_word(0xe82002, 0xf800);
    palette_word(0xe82004, 0x003e); palette_word(0xe82206, 0x07c1);
    equal(&r[12], GrphPal[0], channel_bits(WinDraw_Pal16R));
    equal(&r[12], GrphPal[1], channel_bits(WinDraw_Pal16G));
    equal(&r[12], GrphPal[2], channel_bits(WinDraw_Pal16B));
    equal(&r[12], TextPal[3], channel_bits(WinDraw_Pal16R) | Ibit);
    equal(&r[12], Pal_Read(0xe82000), 7); equal(&r[12], Pal_Read(0xe82001), 0xc0);

    for (page = 0; page < 3; ++page) {
        VCtrl_Write(0xe82400u + page * 0x100u, (uint8_t)(0x11u + page));
        VCtrl_Write(0xe82401u + page * 0x100u, (uint8_t)(0x55u + page));
        for (i = 0; i < 0x100; ++i)
            equal(&r[13], VCtrl_Read(0xe82400u + page * 0x100u + i),
                  (i & 1) ? 0x55u + page : 0x11u + page);
    }

    memset(GVRAM, 0, sizeof(GVRAM)); fill_graphic_palette();
    CRTC_Regs[0x28] = 0; CRTC_Regs[0x29] = 0; VLINE = 0;
    memset(GrphScrollX, 0, sizeof(GrphScrollX));
    memset(GrphScrollY, 0, sizeof(GrphScrollY));
    graphic_pixel(0, 0, 0, 5); graphic_pixel(0, 1, 0, 6);
    graphic_pixel(1, 0, 0, 0); graphic_pixel(1, 1, 0, 7);
    Grp_DrawLine4(0, 1); Grp_DrawLine4(1, 0);
    equal(&r[14], Grp_LineBuf[0], 0x4005); equal(&r[14], Grp_LineBuf[1], 0x4007);

    BG_Init(); fill_text_palette(); VLINEBG = 0; BG_VLINE = 0; BG_HAdjust = 0;
    /* Pattern0 row0 = [1,2,...]; pattern1 row0 = [3,4,...]. */
    BG_Write(0xeb8000, 0x12); BG_Write(0xeb8080, 0x34);
    sprite_word(0, 0, 16); sprite_word(0, 2, 16); sprite_word(0, 4, 0); sprite_word(0, 6, 1);
    sprite_word(1, 0, 16); sprite_word(1, 2, 16); sprite_word(1, 4, 1); sprite_word(1, 6, 1);
    BG_DrawLine(1, 1);
    equal(&r[15], BG_LineBuf[16], 0x5001); equal(&r[15], BG_LineBuf[17], 0x5002);
    sprite_word(0, 6, 0); BG_DrawLine(1, 1);
    equal(&r[15], BG_LineBuf[16], 0x5003); equal(&r[15], BG_LineBuf[17], 0x5004);

    sprite_word(1, 6, 0); sprite_word(0, 6, 1); sprite_word(0, 4, 0x4000);
    BG_DrawLine(1, 1);
    equal(&r[16], BG_LineBuf[30], 0x5002); equal(&r[16], BG_LineBuf[31], 0x5001);
    equal(&r[16], BG_LineBuf[16], 0x5000);
    sprite_word(0, 4, 0x8000); VLINEBG = 15; BG_DrawLine(1, 1);
    equal(&r[16], BG_LineBuf[16], 0x5001); equal(&r[16], BG_LineBuf[17], 0x5002);

    memset(GVRAM, 0xff, sizeof(GVRAM)); CRTC_Regs[0x28] = 0;
    CRTC_Regs[0x29] = 0; GrphScrollX[0] = 511; GrphScrollY[0] = 511;
    CRTC_FastClrMask = 0xff0f; GVRAM_FastClear();
    equal(&r[17], GVRAM_Read(0xc80001u + 511u * 1024u + 1022u), 0);
    equal(&r[17], GVRAM_Read(0xc80001), 0);
    equal(&r[17], GVRAM_Read(0xc00001), 15);
    equal(&r[17], GVRAM_Read(0xd00001), 15);
    equal(&r[17], GVRAM_Read(0xc80001u + 256u * 1024u + 512u), 15);

    TVRAM_Init(); fill_text_palette(); CRTC_Regs[0x2a] = 0; CRTC_Regs[0x29] = 0;
    TextDotX = 16; TextScrollX = 1023; TextScrollY = VLINE = 0;
    TVRAM_Write(0xe0007f, 1); TVRAM_Write(0xe00000, 0x80);
    TVRAM_Write(0xe20000, 0x40); Text_DrawLine(1);
    equal(&r[18], BG_LineBuf[16], 0x5001);
    equal(&r[18], BG_LineBuf[17], 0x5001);
    equal(&r[18], BG_LineBuf[18], 0x5002);
    BG_LineBuf[17] = 0x7777; Text_DrawLine(0);
    equal(&r[18], BG_LineBuf[17], 0x5001);

    /* Three separate nonzero pixels at the same position. Exercise the final
     * compositor, not only intermediate plane buffers, for each front layer.
     * One further vector makes text transparent to expose the next layer. */
    TVRAM_Init(); BG_Init(); memset(GVRAM, 0, sizeof(GVRAM));
    fill_text_palette(); fill_graphic_palette();
    Debug_Text = Debug_Grp = Debug_Sp = 1;
    TextDotX = 16; TextScrollX = TextScrollY = VLINE = 0;
    CRTC_Regs[0x28] = CRTC_Regs[0x29] = CRTC_Regs[0x2a] = CRTC_Regs[0x0d] = 0;
    memset(GrphScrollX, 0, sizeof(GrphScrollX));
    memset(GrphScrollY, 0, sizeof(GrphScrollY));
    TVRAM_Write(0xe00000, 0x80); graphic_pixel(0, 0, 0, 5);
    BG_Write(0xeb8000, 0x30); BG_Write(0xeb0808, 2);
    BG_HAdjust = BG_VLINE = 0;
    sprite_word(0, 0, 16); sprite_word(0, 2, 16); sprite_word(0, 4, 0); sprite_word(0, 6, 1);
    VCReg0[0] = VCReg0[1] = VCReg2[0] = 0;
    VCReg2[1] = 0x61; VCReg1[1] = 0xe4;
    VCReg1[0] = 0x24; TextDirtyLine[0] = 1; WinDraw_DrawLine();
    equal(&r[20], videoBuffer[0], 0x4005);
    VCReg1[0] = 0x21; TextDirtyLine[0] = 1; WinDraw_DrawLine();
    equal(&r[20], videoBuffer[0], 0x5001);
    VCReg1[0] = 0x09; TextDirtyLine[0] = 1; WinDraw_DrawLine();
    equal(&r[20], videoBuffer[0], 0x5003);
    VCReg1[0] = 0x12; TVRAM_Write(0xe00000, 0);
    TextDirtyLine[0] = 1; WinDraw_DrawLine();
    equal(&r[20], videoBuffer[0], 0x5003);

    restored = retro_unserialize(snapshot, snapshot_size);
    /* PX's state loader reapplies SR after loading its internal flags, which
     * normalizes equivalent nonzero N/Z representations. Diagnostics must
     * restore the original opaque CPU context as well, not merely an equal SR.
     * This in-process context is never persisted or used across builds. */
    if (restored) m68k_set_context(cpu_context);
    /* The loader deliberately invalidates all text cache lines. Restore the
     * diagnostic-only invalidation flags and raster counters as well. */
    memcpy(TextDirtyLine, dirty_before, sizeof(dirty_before));
    VLINE = vline_before; VLINEBG = vlinebg_before;
    Debug_Text = debug_text_before; Debug_Grp = debug_grp_before; Debug_Sp = debug_sp_before;
    memcpy(videoBuffer, frame_before, 800u * 600u * sizeof(uint16_t));
    equal(&r[19], restored, true);
    if (restored) {
        equal(&r[19], retro_serialize(after, snapshot_size), true);
        equal(&r[19], memcmp(snapshot, after, snapshot_size) == 0, true);
        difference_count = state_differences(snapshot, after, snapshot_size, differences);
    }

done:
    for (i = 0; i < RR_X68K_VIDEO_CHECK_COUNT; ++i)
        if (r[i].comparisons && !r[i].failures) mask |= UINT32_C(1) << i;
    report = json_path ? fopen(json_path, "wb") : NULL;
    if (report) {
        fprintf(report, "{\n  \"schema\": 1,\n  \"suite\": \"authored-x68000-video\",\n"
                "  \"mask\": %u,\n  \"expected_mask\": %u,\n  \"state_restored\": %s,\n"
                "  \"guest_cpu_instructions\": 0,\n  \"checks\": [\n",
                mask, RR_X68K_VIDEO_EXPECTED, restored ? "true" : "false");
        for (i = 0; i < RR_X68K_VIDEO_CHECK_COUNT; ++i)
            fprintf(report, "    {\"name\":\"%s\",\"passed\":%s,\"comparisons\":%u,"
                    "\"failures\":%u,\"first_expected\":%u,\"first_actual\":%u}%s\n",
                    r[i].name, (mask & (UINT32_C(1) << i)) ? "true" : "false",
                    r[i].comparisons, r[i].failures, r[i].first_expected, r[i].first_actual,
                    i + 1 == RR_X68K_VIDEO_CHECK_COUNT ? "" : ",");
        fprintf(report, "  ],\n  \"state_differences\": [\n");
        for (i = 0; i < difference_count; ++i)
            fprintf(report, "    {\"field\":\"%s\",\"changed_bytes\":%u}%s\n",
                    differences[i].field, differences[i].bytes, i + 1 == difference_count ? "" : ",");
        fprintf(report, "  ]\n}\n");
        if (fclose(report) != 0) mask = 0;
    } else {
        mask = 0;
    }
    free(cpu_context); free(frame_before); free(after); free(snapshot);
    return mask;
}
