/* ROM-free authored I/O and CPU proof, also reusable with private game ROMs. */
#undef NDEBUG
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "glue.h"
#include "lightphaser.h"
#include "embedded_rom.h"
#include "include/sms_runtime.h"

int smsrecomp_take_reset_request(void) { return 0; }
static unsigned script_kind;
static uint8_t shot_script(uint64_t frame) {
    int x = script_kind == 2 ? -1 : script_kind == 1 ? 192 : 64;
    int y = script_kind == 1 ? 128 : 64;
    lightphaser_pointer(x, y, false);
    bool fire = frame >= 120 && frame % 30 < 3;
    glue_set_pad2(sms_light_phaser_trigger_p2 && fire ? SMS_PAD_B1 : 0);
    return fire ? SMS_PAD_B1 : 0;
}

static void port_checks(void) {
    lightphaser_reset(true, 20);
    assert(lightphaser_dc(0, 0) == 0xFF);
    lightphaser_pointer(128, 96, true);
    assert(lightphaser_dc(0, SMS_PAD_UP) == 0xAF);
    assert(lightphaser_dd(0, 80u*228u) == 0xFF);
    uint64_t beam = 96u*228u + 128u*2u/3u;
    assert(lightphaser_dd(0, beam) == 0xBF);
    assert(lightphaser_hcounter(beam+11) == 84);
    assert(lightphaser_dd(0, beam+72) == 0xFF);
    assert(lightphaser_hcounter(200u*228u) == 84);
    lightphaser_pointer(-1, -1, true);
    assert(lightphaser_dc(0, 0) == 0xEF); /* Offscreen still pulls the trigger. */
    assert(lightphaser_dd(0, 210u*228u) == 0xFF);
    lightphaser_control(0xDD, 210u*228u, 45); /* TH1 driven low by the CPU. */
    assert(lightphaser_dd(0, 210u*228u) == 0xBF);
    assert(lightphaser_hcounter(210u*228u) == 45);
    lightphaser_control(0xFF, 210u*228u, 78);
    assert(lightphaser_dd(0, 210u*228u) == 0xFF);
    assert(lightphaser_hcounter(210u*228u) == 45); /* Rising edge does not latch. */
    lightphaser_reset(true, 16);
    lightphaser_pointer(255, 191, false);
    assert(lightphaser_hcounter(191u*228u+170u) == 143); /* No DD polling necessary. */
    assert(lightphaser_dd(SMS_PAD_B2, 191u*228u+170u) == 0xB7);
    lightphaser_reset(true, 20);
    assert(lightphaser_hcounter(0) == 0 && lightphaser_dc(0, 0) == 0xFF);
    puts("PASS: TL trigger, P2 preservation, TH raster pulse, frozen H-counter, falling-edge latch, offscreen and reset.");
}

int main(int argc, char **argv) {
    if (argc > 1 && !strcmp(argv[1], "--game")) {
        unsigned frames = argc > 2 ? (unsigned)atoi(argv[2]) : 900;
        uint8_t previous[8192];
        uint64_t hashes[3];
        for (script_kind = 0; script_kind < 3; ++script_kind) {
            for (int reference = 0; reference < 2; ++reference) {
                assert(glue_load_rom("embedded")); glue_init(false, frames);
                glue_set_input_cb(shot_script); shot_script(0);
                if (reference) glue_run_interp(); else glue_run();
                assert(glue_frame_count() == frames);
                if (!reference) {
                    assert(smsrecomp_interpreter_cycles() == 0);
                    hashes[script_kind] = 1469598103934665603ULL;
                    for (int i=0;i<8192;++i) {
                        previous[i]=sms_read8((uint16_t)(0xC000+i));
                        hashes[script_kind] = (hashes[script_kind] ^ previous[i]) * 1099511628211ULL;
                    }
                    uint64_t low, counters; lightphaser_observations(&low, &counters);
                    printf("[gun-probe] scenario=%u th_low_reads=%llu hcounter_reads=%llu ram_hash=%llu\n",
                        script_kind, (unsigned long long)low, (unsigned long long)counters, (unsigned long long)hashes[script_kind]);
                    if (script_kind < 2) assert(low > 0 && counters > 0);
                    else assert(low == 0);
                } else for (int i=0;i<8192;++i) assert(previous[i] == sms_read8((uint16_t)(0xC000+i)));
            }
        }
        assert(hashes[0] != hashes[1] || hashes[0] != hashes[2]);
        printf("PASS: %s: three gun scenarios, %u frames each, native/reference RAM equal and zero native fallback.\n", sms_game_title, frames);
        return 0;
    }
    port_checks();
    for (int offscreen = 0; offscreen < 2; ++offscreen) for (int reference = 0; reference < 2; ++reference) {
        assert(glue_load_rom("embedded")); glue_init(false, 2);
        lightphaser_reset(true, 20);
        lightphaser_pointer(offscreen ? -1 : 128, offscreen ? -1 : 96, true);
        if (reference) glue_run_interp(); else glue_run();
        assert(glue_frame_count() == 2);
        assert(sms_read8(0xC000) == 0xEF);
        assert(sms_read8(0xC003) == (offscreen ? 0 : 1));
        if (!offscreen) assert(sms_read8(0xC002) == 84);
        if (!reference) assert(smsrecomp_interpreter_cycles() == 0);
    }
    puts("PASS: authored Z80 detects trigger and gun coordinates; offscreen has no hit; native/reference both pass.");
    return 0;
}
