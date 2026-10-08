#define SDL_MAIN_HANDLED
#include <SDL.h>
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "retro_console16.h"
#ifndef RR_GAME_TITLE
#define RR_GAME_TITLE "RetroRecomp"
#endif
static uint64_t fingerprint(void) {
    uint64_t h = 14695981039346656037ull;
    const uint32_t *p = rr16_pixels();
    for (size_t i = 0; i < RR16_WIDTH * RR16_HEIGHT; ++i) { h ^= p[i]; h *= 1099511628211ull; }
    return h;
}
int main(int argc, char **argv) {
    unsigned frames = 0; bool play = false, reset_check = false;
    const char *report = NULL;
    for (int i = 1; i < argc; ++i) {
        if (!strcmp(argv[i], "--frames") && i + 1 < argc) frames = (unsigned)atoi(argv[++i]);
        else if (!strcmp(argv[i], "--play")) play = true;
        else if (!strcmp(argv[i], "--reset-check")) reset_check = true;
        else if (!strcmp(argv[i], "--report") && i + 1 < argc) report = argv[++i];
    }
    if (reset_check && !frames) frames = 120;
    if (frames > 1000000) return 2;
    SDL_SetMainReady();
    if (!frames && SDL_InitSubSystem(SDL_INIT_AUDIO) != 0) return 1;
    if (!rr16_init(frames != 0)) return 1;
    if (!frames) { int status = rr16_sdl_main(RR_GAME_TITLE, 3); rr16_shutdown(); SDL_Quit(); return status; }
    unsigned completed = 0;
    uint64_t sequence = 14695981039346656037ull;
    for (; completed < frames; ++completed) {
        uint16_t input = 0;
#if RR16_MD
        if (play && completed >= 300 && completed < 302) input = 128; /* Start */
        if (play && completed >= 480 && completed < 482) input = 128;
        if (play && completed >= 660 && completed < 662) input = 128;
        if (play && completed >= 800) input = 8 | ((completed % 90 < 15) ? 16 : 0);
#else
        if (play && completed >= 180 && completed < 182) input = 8;
        if (play && completed >= 400 && completed < 402) input = 8;
        if (play && completed >= 550 && completed < 552) input = 8;
        if (play && completed >= 720) input = 128 | ((completed % 90 < 15) ? 1 : 0);
#endif
        if (!rr16_frame(input, 0)) break;
        sequence ^= fingerprint(); sequence *= 1099511628211ull;
    }
    bool reset_matches = true;
    if (reset_check && !play && completed == frames) {
        rr16_reset();
        uint64_t repeated = 14695981039346656037ull;
        for (unsigned n = 0; n < frames; ++n) {
            if (!rr16_frame(0, 0)) { reset_matches = false; break; }
            repeated ^= fingerprint(); repeated *= 1099511628211ull;
        }
        reset_matches = reset_matches && repeated == sequence;
    }
    char summary[512];
    snprintf(summary, sizeof(summary), "{\"frames\":%u,\"interpreted_opcodes\":%llu,\"native_entries\":%llu,\"game_mode\":%u,\"player_x\":%u,\"frame_hash\":\"%016llx\",\"sequence_hash\":\"%016llx\",\"audio_cpu\":\"interpreted\"}",
        completed, (unsigned long long)rr16_interpreted(), (unsigned long long)rr16_native_entries(),
        rr16_game_mode(), rr16_player_x(),
        (unsigned long long)fingerprint(), (unsigned long long)sequence);
    puts(summary);
    if (report) {
        FILE *f = fopen(report, "wb"); if (!f) return 3;
        summary[strlen(summary) - 1] = 0;
        fputs(summary, f); rr16_report_details(f); fputs("}", f);
        fclose(f);
    }
    rr16_shutdown(); return completed != frames ? 4 : !reset_matches ? 6 : 0;
}
int WINAPI WinMain(HINSTANCE instance, HINSTANCE previous, LPSTR command, int show) {
    return main(__argc, __argv);
}
