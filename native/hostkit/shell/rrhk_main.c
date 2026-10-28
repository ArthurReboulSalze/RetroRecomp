/* The windowed loop of every machine: window, picture, audio, controls, menus
 * and pacing around the machine's one-frame function. */
#ifndef SDL_MAIN_HANDLED
#define SDL_MAIN_HANDLED
#endif
#include <SDL.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
#include "platform_io.h"
#include "display_settings.h"
#include "embedded_resources.h"
#include "retro_menu.h"
#include "runtime_feedback_sdl.h"
#include "hostkit/hostkit_internal.h"

static RrhkRun run;

int rrhk_main(const RrhkMachine *m, const char *title, int scale) {
    RrhkRun *r = &run;
    memset(r, 0, sizeof *r);
    r->machine = m;
    r->title = title;
    SDL_SetMainReady();
#ifndef _WIN32
    SDL_SetHintWithPriority(SDL_HINT_RENDER_VSYNC, "1", SDL_HINT_DEFAULT);
#endif
    if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_GAMECONTROLLER | SDL_INIT_AUDIO) != 0) return 1;
    rrhk_bind(m);
    rrhk_load_bindings();
    rrhk_options_init(m->ini_section);
    if (m->machine_fkeys) rrhk_options_keyboard(m->console_name, m->machine_fkeys);
    const char *test_limit = getenv("RETRORECOMP_HOST_TEST_FRAMES");
    r->test_frames = test_limit ? (unsigned)atoi(test_limit) : 0;
    if (!r->test_frames && m->frame_limit) r->test_frames = m->frame_limit();
    const char *test_no_audio = getenv("RETRORECOMP_HOST_TEST_NO_AUDIO");
    r->video_clock_test = r->test_frames && test_no_audio && test_no_audio[0] == '1';
    m->state_path(r->state_path, 32768);
    if (scale < 1) scale = 3;
    snprintf(r->caption, sizeof(r->caption), "%s | %s", title, "Native code");
    r->win = SDL_CreateWindow(r->caption, SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
        m->display_width() * scale, m->raster_height() * scale, SDL_WINDOW_RESIZABLE | SDL_WINDOW_ALLOW_HIGHDPI |
        (r->test_frames ? SDL_WINDOW_HIDDEN : 0));
    rr_set_window_icon(r->win);
    if (r->win && rrhk.fullscreen && SDL_SetWindowFullscreen(r->win, SDL_WINDOW_FULLSCREEN_DESKTOP) != 0) rrhk.fullscreen = 0;
    r->ren = r->win ? SDL_CreateRenderer(r->win, -1, SDL_RENDERER_ACCELERATED) : NULL;
    if (!r->ren && r->win) r->ren = SDL_CreateRenderer(r->win, -1, SDL_RENDERER_SOFTWARE);
    r->tex = r->ren ? rrhk_texture_create(r) : NULL;
    r->upscaled = (uint32_t *)malloc(m->max_width * 2 * m->max_height * 2 * sizeof(uint32_t));
    if (!r->tex || !r->upscaled) {
        free(r->upscaled); if (r->ren) SDL_DestroyRenderer(r->ren); if (r->win) SDL_DestroyWindow(r->win); return 1;
    }
    SDL_SetTextureScaleMode(r->tex, SDL_ScaleModeNearest);
    rr_menu_init(r->ren);
    rrhk_audio_open(r);
    rrhk_open_pads();
    r->frequency = SDL_GetPerformanceFrequency();
    r->next = SDL_GetPerformanceCounter();
    r->test_started = r->next;
    const char *timing_path = getenv("RETRORECOMP_TIMING_REPORT");
    bool timing_enabled = timing_path && *timing_path;
    RrhkTiming timing = {0};
    r->title_state = -1;
    r->running = true;
    const char *test_filter = r->test_frames ? getenv("RETRORECOMP_HOST_TEST_FILTER") : NULL;
    if (test_filter && !strcmp(test_filter, "3")) rrhk.filter = 3;
    while (r->running) {
        Uint64 timing_ticks[7] = {0};
        double timing_cpu = timing_enabled ? rrhk_thread_cpu() : 0;
        bool timing_ran_frame = false;
        if (timing_enabled) timing_ticks[0] = SDL_GetPerformanceCounter();
        rrhk_audio_wait_room(r);
        if (m->frame_start) m->frame_start(r->win, r->ren);
        rrhk_poll_events(r);
        if (rrhk_options_quit(rrhk.menu)) r->running = false;
        else if (rrhk_options_restart(rrhk.menu)) { m->reset(); rrhk_audio_pause_output(r); rrhk.menu = 0; }
        if (!r->running) break;
        /* A computer's fast loading key: no pacing, no sound, a picture every eighth frame. */
        bool fast = m->fast_forward && m->fast_forward();
        if (fast != r->fast) { r->fast = fast; r->next = SDL_GetPerformanceCounter(); rrhk_audio_pause_output(r); }
        if (r->pending_state && m->state_ready()) {
            bool load = r->pending_state == 2;
            bool ok = m->state_file(r->state_path, load);
            r->pending_state = 0;
            const char *message = ok ? (load ? rrhk_tr("Quick state loaded", "Partie chargee") : rrhk_tr("Quick state saved", "Partie sauvegardee")) :
                (load ? rrhk_tr("No compatible quick state to load", "Aucune sauvegarde compatible") :
                 m->save_failed_en ? rrhk_tr(m->save_failed_en, m->save_failed_fr) : rrhk_tr("Cannot save game state", "Impossible de sauvegarder"));
            rrhk_notice(message, 1800);
            if (ok) { rrhk.menu = 0; rrhk.capturing = 0; }
            if (ok && load) { rrhk_audio_pause_output(r); r->next = SDL_GetPerformanceCounter(); }
        }
        bool idle = (rrhk.menu != 0 || rrhk.paused) && !r->pending_state;
        m->pause(idle);
        /* Explicit performance reports only; include CPU, audio preparation,
         * drawing and Present, but exclude intentional pacing/menu waits. */
        Uint64 work_started = m->cost_enabled && m->cost_enabled() && !rrhk.menu && !rrhk.paused ? SDL_GetPerformanceCounter() : 0;
        uint64_t input_frame = m->input_frame ? m->input_frame() : r->frame;
        uint16_t pad1 = rrhk_pad_word(0, input_frame);
        if (m->pointer) rrhk_pointer_sample(r->win, r->ren, pad1);
        if (!idle) {
            if (timing_enabled) timing_ticks[1] = SDL_GetPerformanceCounter();
            if (m->before_frame) {
                RrhkAudioProbe probe = {r->audio_playing, rrhk_audio_queued(r),
                                        (unsigned)r->have.freq, r->have.samples};
                m->before_frame(&probe, input_frame);
            }
            if (!m->run_frame(pad1, m->pointer && !m->pointer_keeps_player2 ? 0 : rrhk_pad_word(1, input_frame))) { r->running = false; break; }
            ++r->frame;
            timing_ran_frame = true;
            if (timing_enabled) timing_ticks[2] = SDL_GetPerformanceCounter();
            rrhk_audio_frame(r);
            if (r->test_frames && r->frame >= r->test_frames) r->running = false;
        } else rrhk_audio_idle(r);
        if (timing_enabled) timing_ticks[3] = SDL_GetPerformanceCounter();
        const bool shown = !r->fast || (r->frame & 7) == 0;
        if (shown) rrhk_present_picture(r);

        int current_title_state = (m->interpreted() || m->audio_interpreted() ? 1 : 0);
        /* A cartridge device (GSU, CX4, DSP-1) still running on its instruction
         * core is signalled apart from the CPUs; it is never hidden. */
        if (m->device_interpreted && !current_title_state && m->device_interpreted()) current_title_state = 2;
        if (current_title_state != r->title_state) {
            snprintf(r->caption, sizeof(r->caption), "%s | %s", title,
                     current_title_state == 2 ? "Cartridge chip interpreted" :
                     current_title_state ? "Interpreter fallback" : "Native code");
            SDL_SetWindowTitle(r->win, r->caption);
            r->title_state = current_title_state;
        }
        rrhk_menu_draw(r->ren);
        if (!rrhk.menu && rrhk.status[0] && SDL_GetTicks64() < rrhk.status_until) {
            int ox, oy, unit; rr_menu_layout(r->ren, &ox, &oy, &unit);
            rr_menu_text(r->ren, ox, oy, unit, 8, 183, rrhk.status, RR_MENU_GOLD);
        }
        if (m->before_present) m->before_present(r->ren);
        Uint64 present_started = work_started ? SDL_GetPerformanceCounter() : 0;
        if (timing_enabled) timing_ticks[4] = SDL_GetPerformanceCounter();
        if (shown) SDL_RenderPresent(r->ren);
        Uint64 now = SDL_GetPerformanceCounter();
        timing_ticks[5] = now;
        if (work_started && m->cost) m->cost(1000.0 * (now - work_started) / r->frequency,
                                            1000.0 * (now - present_started) / r->frequency);
        if (rrhk.menu || rrhk.paused) { r->next = now; SDL_Delay(16); continue; }
        if (r->fast) { r->next = now; continue; }
        r->next += (Uint64)(m->frame_seconds * r->frequency);
        rrhk_audio_pace(r, now);
        if (r->next > now) {
            Uint32 ms = (Uint32)((r->next - now) * 1000 / r->frequency);
            if (ms > 1) SDL_Delay(ms - 1);
            while (SDL_GetPerformanceCounter() < r->next) {}
        } else if (now - r->next > r->frequency / 4) r->next = now;
        if (timing_enabled && timing_ran_frame) {
            timing_ticks[6] = SDL_GetPerformanceCounter();
            ++timing.frames; timing.thread_cpu += rrhk_thread_cpu() - timing_cpu;
            for (unsigned n = 0; n < 6; ++n) {
                double seconds = (double)(timing_ticks[n + 1] - timing_ticks[n]) / r->frequency;
                timing.total[n] += seconds;
                if (seconds > timing.maximum[n]) timing.maximum[n] = seconds;
            }
        }
    }
    double elapsed = (double)(SDL_GetPerformanceCounter() - r->test_started) / r->frequency;
    if (m->finished) m->finished(elapsed);
    if (r->test_frames) {
        fprintf(stderr, "{\"host_frames\":%llu,\"wall_seconds\":%.6f,\"expected_seconds\":%.6f,"
                "\"measured_fps\":%.6f,\"target_fps\":%.6f,\"video_clock_only\":%s}\n",
                (unsigned long long)r->frame, elapsed, r->frame * m->frame_seconds, r->frame / elapsed, 1.0 / m->frame_seconds,
                r->video_clock_test ? "true" : "false");
    }
    rrhk_timing_write(m, timing_path, &timing, r->ren, r->frequency);
    rr_feedback_close_screen(r->ren);
    rrhk_audio_close(r);
    rrhk_close_pads();
    rr_menu_shutdown(); free(r->upscaled); if (r->tex) SDL_DestroyTexture(r->tex);
    rr_xbr_destroy(&r->xbr);
    rr_scanlines_destroy(&r->scanlines);
    SDL_ShowCursor(SDL_ENABLE);
    SDL_DestroyRenderer(r->ren); SDL_DestroyWindow(r->win); return 0;
}

SDL_Window *rrhk_window(void) { return run.win; }

/* F4 and the computers' own display shortcut. */
void rrhk_cycle_display(void) {
    int changed = rr_display_cycle(run.win, &rrhk.fullscreen, rrhk.ini_file, rrhk.data_dir, rrhk.video_section);
    if (changed < 0) snprintf(rrhk.status, sizeof(rrhk.status), "%s", rrhk_tr("Config unavailable", "Config inaccessible"));
}

void rrhk_notice(const char *text, Uint64 milliseconds) {
    snprintf(rrhk.status, sizeof rrhk.status, "%s", text);
    rrhk.status_until = SDL_GetTicks64() + milliseconds;
}
