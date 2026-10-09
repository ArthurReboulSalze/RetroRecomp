#define SDL_MAIN_HANDLED
#include <SDL.h>
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>
#include "retro_console16.h"
#include "console16_state.h"
#ifndef RR_GAME_TITLE
#define RR_GAME_TITLE "RetroRecomp"
#endif
static uint64_t fingerprint(void) {
    uint64_t h = 14695981039346656037ull;
    const uint32_t *p = rr16_pixels();
    for (size_t i = 0; i < RR16_WIDTH * RR16_HEIGHT; ++i) { h ^= p[i]; h *= 1099511628211ull; }
    return h;
}
typedef struct { unsigned frame; uint16_t p1, p2; } ReplayInput;
static ReplayInput replay[4096];
static unsigned replay_count;
static bool load_replay(const char *path, unsigned frames) {
    FILE *file = fopen(path, "rb");
    if (!file) return false;
    char line[256]; bool valid = true;
    while (fgets(line, sizeof line, file)) {
        char *text = line, extra;
        while (*text == ' ' || *text == '\t') ++text;
        if (*text == '#' || *text == '\r' || *text == '\n' || !*text) continue;
        unsigned frame, p1, p2;
        if (sscanf(text, "%u %u %u %c", &frame, &p1, &p2, &extra) != 3 ||
            p1 > UINT16_MAX || p2 > UINT16_MAX || frame >= frames ||
            replay_count == sizeof replay / sizeof *replay ||
            (replay_count && frame <= replay[replay_count - 1].frame)) {
            valid = false; break;
        }
        replay[replay_count++] = (ReplayInput){frame, (uint16_t)p1, (uint16_t)p2};
    }
    if (ferror(file)) valid = false;
    fclose(file); return valid;
}
int main(int argc, char **argv) {
    unsigned frames = 0, frame_offset = 0; bool play = false, reset_check = false;
    bool ignore_load_error = false;
    const char *save_state = NULL, *load_state = NULL;
    bool t2_gun_menu = false;
    const char *report = NULL;
    const char *input_script = NULL, *trace_path = NULL;
    for (int i = 1; i < argc; ++i) {
        if (!strcmp(argv[i], "--frames") && i + 1 < argc) frames = (unsigned)atoi(argv[++i]);
        else if (!strcmp(argv[i], "--frame-offset") && i + 1 < argc) frame_offset = (unsigned)atoi(argv[++i]);
        else if (!strcmp(argv[i], "--save-state") && i + 1 < argc) save_state = argv[++i];
        else if (!strcmp(argv[i], "--load-state") && i + 1 < argc) load_state = argv[++i];
        else if (!strcmp(argv[i], "--ignore-load-error")) ignore_load_error = true;
        else if (!strcmp(argv[i], "--play")) play = true;
        else if (!strcmp(argv[i], "--reset-check")) reset_check = true;
        else if (!strcmp(argv[i], "--gun-menu") && i + 1 < argc) t2_gun_menu = !strcmp(argv[++i], "t2");
        else if (!strcmp(argv[i], "--report") && i + 1 < argc) report = argv[++i];
        else if (!strcmp(argv[i], "--input-script") && i + 1 < argc) input_script = argv[++i];
        else if (!strcmp(argv[i], "--trace") && i + 1 < argc) trace_path = argv[++i];
    }
    if (reset_check && !frames) frames = 120;
    if (frames > 1000000 || frame_offset > 1000000 || ((save_state || load_state) && !frames)) return 2;
    if ((input_script || trace_path) && (!frames || reset_check)) return 2;
    if (input_script && !load_replay(input_script, frames + frame_offset)) return 2;
    SDL_SetMainReady();
    if (!frames && SDL_InitSubSystem(SDL_INIT_AUDIO) != 0) return 1;
    if (!rr16_init(frames != 0)) return 1;
    if (load_state) {
        wchar_t path[32768];
        bool ok=MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,load_state,-1,path,32768) && rr16_state_file(path,true);
        if (!ok && !ignore_load_error) { rr16_shutdown(); return 7; }
    }
    if (!frames) { int status = rr16_sdl_main(RR_GAME_TITLE, 3); rr16_shutdown(); SDL_Quit(); return status; }
    FILE *trace = trace_path ? fopen(trace_path, "wb") : NULL;
    if (trace_path && !trace) { rr16_shutdown(); return 3; }
    if (trace) fputs("frame,frame_hash,native,interpreted,audio_hash"
#if RR16_MD
                     ",pc,sr,sp,z80_pc,busreq,reset_off,fm_nonzero,psg_nonzero"
#endif
                     "\n", trace);
    unsigned replay_index = 0; uint16_t script_p1 = 0, script_p2 = 0;
    unsigned completed = 0;
    uint64_t sequence = 14695981039346656037ull;
    for (; completed < frames; ++completed) {
        unsigned logical_frame = completed + frame_offset;
        uint16_t input = 0;
#if RR16_MD
        if (play && logical_frame >= 300 && logical_frame < 302) input = 128; /* Start */
        if (play && logical_frame >= 480 && logical_frame < 482) input = 128;
        if (play && logical_frame >= 660 && logical_frame < 662) input = 128;
        if (play && logical_frame >= 800) input = 8 | ((logical_frame % 90 < 15) ? 16 : 0);
        if (RR16_GUN && play && logical_frame >= 900 && logical_frame < 1800 && logical_frame % 360 < 2) input = 128;
        if (RR16_GUN && play && logical_frame >= 1800 && logical_frame % 240 >= 30 && logical_frame % 240 < 32) input |= 64;
        if (RR16_GUN && play && t2_gun_menu) {
            /* Use the original controller menu: two Down presses select the
             * one-player Menacer entry. No guest RAM or ROM is patched. */
            input = 0;
            static const unsigned start_frames[] = {300,480,660,900,1200,1500,1800,2100,2400,2700};
            for (unsigned n=0; n<sizeof start_frames/sizeof *start_frames; ++n)
                if (logical_frame >= start_frames[n] && logical_frame < start_frames[n] + 2) input = 128;
            if ((logical_frame >= 1600 && logical_frame < 1602) || (logical_frame >= 1640 && logical_frame < 1642)) input = 2;
        }
#else
        if (play && logical_frame >= 180 && logical_frame < 182) input = 8;
        if (play && logical_frame >= 400 && logical_frame < 402) input = 8;
        if (play && logical_frame >= 550 && logical_frame < 552) input = 8;
        if (play && logical_frame >= 720) input = 128 | ((logical_frame % 90 < 15) ? 1 : 0);
#endif
        if (RR16_GUN && play) {
            /* Calibration aim is held centrally before moving through a grid.
             * The guest keeps its original start/calibration menus and flashes. */
            int width = rr16_visible_width();
            Rr16GunInput gun = {.x = width / 2, .y = RR16_HEIGHT / 2};
            if (logical_frame >= (t2_gun_menu ? 2400u : 1800u)) {
                gun.x = 32 + (logical_frame / 90 % 4) * (width - 64) / 3;
                gun.y = 40 + (logical_frame / 360 % 3) * 64;
            }
            gun.fire = logical_frame >= 300 && logical_frame % 180 >= 10 && logical_frame % 180 < 18;
            gun.turbo = RR16_GUN == RR_GUN_SCOPE;
            gun.aux = logical_frame >= 1200 && logical_frame % 300 < 8;
            gun.start = (input & (RR16_MD ? 128 : 8)) != 0;
            rr16_gun_input(gun);
        }
        if (input_script) {
            while (replay_index < replay_count && replay[replay_index].frame <= logical_frame) {
                script_p1 = replay[replay_index].p1; script_p2 = replay[replay_index++].p2;
            }
            input = script_p1;
        }
        if (!rr16_frame(input, script_p2)) break;
        sequence ^= fingerprint(); sequence *= 1099511628211ull;
        if (trace) {
            fprintf(trace, "%u,%016llx,%llu,%llu,%016llx", logical_frame + 1, fingerprint(),
                    rr16_native_entries(), rr16_interpreted(), rr16_audio_frame_fingerprint());
#if RR16_MD
            rr16_trace_details(trace);
#endif
            fputc('\n', trace); fflush(trace);
        }
    }
    if (save_state) {
        wchar_t path[32768];
        bool ok=MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,save_state,-1,path,32768) && rr16_state_file(path,false);
        if (!ok) { if (trace) fclose(trace); rr16_shutdown(); return 8; }
    }
    bool reset_matches = true, reset_sequence_matches = true, reset_audio_matches = true;
    uint64_t reset_first_audio = 0;
    if (reset_check && !play && completed == frames) {
        uint64_t first_audio = rr16_audio_fingerprint();
        reset_first_audio = first_audio;
        rr16_reset();
        uint64_t repeated = 14695981039346656037ull;
        for (unsigned n = 0; n < frames; ++n) {
            if (!rr16_frame(0, 0)) { reset_matches = false; break; }
            repeated ^= fingerprint(); repeated *= 1099511628211ull;
        }
        reset_sequence_matches = repeated == sequence;
        reset_audio_matches = rr16_audio_fingerprint() == first_audio;
        reset_matches = reset_matches && reset_sequence_matches && reset_audio_matches;
    }
    char summary[512];
    snprintf(summary, sizeof(summary), "{\"frames\":%u,\"interpreted_opcodes\":%llu,\"native_entries\":%llu,\"game_mode\":%u,\"player_x\":%u,\"frame_hash\":\"%016llx\",\"sequence_hash\":\"%016llx\",\"audio_cpu\":\"%s\"}",
        completed, (unsigned long long)rr16_interpreted(), (unsigned long long)rr16_native_entries(),
        rr16_game_mode(), rr16_player_x(),
        (unsigned long long)fingerprint(), (unsigned long long)sequence, rr16_audio_cpu());
    puts(summary);
    if (report) {
        FILE *f = fopen(report, "wb"); if (!f) return 3;
        summary[strlen(summary) - 1] = 0;
        fputs(summary, f); rr16_report_details(f);
        if (reset_check) fprintf(f, ",\"reset_sequence_match\":%s,\"reset_audio_match\":%s,\"reset_first_audio\":\"%016llx\"",
            reset_sequence_matches ? "true" : "false", reset_audio_matches ? "true" : "false", reset_first_audio);
        fputs("}", f);
        fclose(f);
    }
    if (trace) fclose(trace);
    rr16_shutdown(); return completed != frames ? 4 : !reset_matches ? 6 : 0;
}
int WINAPI WinMain(HINSTANCE instance, HINSTANCE previous, LPSTR command, int show) {
    return main(__argc, __argv);
}
