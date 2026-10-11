/* Authored public-API APU regressions. No cartridge or recorded game audio.
 * Expectations: gbdev Pan Docs, Audio_details.md (DAC, duty, NR43 clocks). */
#include "gbrt.h"
#include "audio.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned failures, checks, nonzero_samples;
static void check(int passed, const char* message) {
    ++checks;
    if (!passed) { ++failures; fprintf(stderr, "FAIL: %s\n", message); }
}
void gb_dispatch(GBContext* ctx, uint16_t address) {
    (void)ctx; (void)address;
    fputs("Unexpected guest CPU execution\n", stderr); abort();
}
static void capture(GBContext* ctx, int16_t left, int16_t right) {
    (void)ctx;
    if (left || right) ++nonzero_samples;
}
static GBContext* context(void) {
    GBConfig config = {0};
    config.model = GB_MODEL_DMG;
    config.enable_audio = true;
    GBContext* ctx = gb_context_create(&config);
    if (!ctx) abort();
    ctx->callbacks.on_audio_sample = capture;
    gb_audio_reset(ctx->apu);
    gb_audio_write(ctx, 0xFF26, 0); gb_audio_write(ctx, 0xFF26, 0x80);
    gb_audio_write(ctx, 0xFF24, 0x77);
    return ctx;
}
static void rising_envelope(unsigned channel) {
    GBContext* ctx = context();
    uint16_t env = channel == 1 ? 0xFF12 : channel == 2 ? 0xFF17 : 0xFF21;
    uint16_t trigger = channel == 1 ? 0xFF14 : channel == 2 ? 0xFF19 : 0xFF23;
    const unsigned mask = 1u << (channel - 1u);
    gb_audio_write(ctx, 0xFF25, (uint8_t)(mask | mask << 4));
    if (channel != 4) {
        gb_audio_write(ctx, env - 1, 0x80);
        gb_audio_write(ctx, trigger - 1, 0xFF);
    } else gb_audio_write(ctx, 0xFF22, 0);
    gb_audio_write(ctx, env, 0x09); /* initial 0; increase every envelope tick */
    gb_audio_write(ctx, trigger, channel == 4 ? 0x80 : 0x87);
    nonzero_samples = 0;
    gb_audio_step(ctx, 1024);
    check(nonzero_samples == 0, "initial zero envelope must be silent");
    for (unsigned i = 0; i < 8; ++i) gb_audio_div_tick(ctx->apu, 0, 8192, false);
    check(gb_audio_read(ctx, env) == 0x09, "envelope must not alter its register");
    check((gb_audio_read(ctx, 0xFF26) & mask) != 0, "rising channel remains active");
    gb_audio_step(ctx, 1024);
    char message[80]; snprintf(message, sizeof(message), "channel %u rising envelope produces PCM", channel);
    check(nonzero_samples != 0, message);
    gb_context_destroy(ctx);
}
static void retrigger_phase(unsigned channel) {
    GBContext* ctx = context();
    uint16_t env = channel == 1 ? 0xFF12 : 0xFF17;
    uint16_t trigger = channel == 1 ? 0xFF14 : 0xFF19;
    gb_audio_write(ctx, env - 1, 0); /* duty 0, high at step 7 */
    gb_audio_write(ctx, env, 0x90);
    gb_audio_write(ctx, trigger - 1, 0xFE);
    gb_audio_write(ctx, trigger, 0x87); /* duty timer period 8 */
    gb_audio_step(ctx, 56); /* seven duty steps */
    const unsigned shift = channel == 1 ? 0 : 4;
    check(((gb_audio_read_pcm12(ctx->apu) >> shift) & 15) == 9, "pulse reaches duty step 7");
    gb_audio_write(ctx, trigger, 0x87);
    check(((gb_audio_read_pcm12(ctx->apu) >> shift) & 15) == 9, "retrigger preserves pulse duty step");
    gb_audio_step(ctx, 8);
    check(((gb_audio_read_pcm12(ctx->apu) >> shift) & 15) == 0, "retrigger reloads pulse timer");
    gb_context_destroy(ctx);
}
static void noise_clock(unsigned shift) {
    GBContext* ctx = context();
    gb_audio_write(ctx, 0xFF21, 0xF0);
    gb_audio_write(ctx, 0xFF22, (uint8_t)(shift << 4));
    gb_audio_write(ctx, 0xFF23, 0x80);
    int stable = true;
    const uint8_t initial = gb_audio_read_pcm34(ctx->apu);
    for (unsigned i = 0; i < 40; ++i) {
        gb_audio_step(ctx, 8u << shift);
        stable &= gb_audio_read_pcm34(ctx->apu) == initial;
    }
    check(stable == (shift >= 14), "NR43 shift 14/15 stops noise clocks, shift 13 runs");
    gb_context_destroy(ctx);
}
int main(void) {
    rising_envelope(1); rising_envelope(2); rising_envelope(4);
    retrigger_phase(1); retrigger_phase(2);
    noise_clock(13); noise_clock(14); noise_clock(15);
    printf("{\"checks\":%u,\"failures\":%u}\n", checks, failures);
    return failures ? 1 : 0;
}
