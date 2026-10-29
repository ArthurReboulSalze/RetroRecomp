/* The windowed loop of every machine: window, picture, audio, controls, menus
 * and pacing around the machine's one-frame function. A machine whose guest owns
 * the loop (Master System, Game Gear) calls the same two halves of an iteration
 * from its frame callback (rrhk_open, rrhk_frame_done, rrhk_close). */
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
/* Divergence 8 (decided, D3): the window keeps its position and size when it goes fullscreen and back, and when the guest
 * is restarted and the window is made again. Not claimed across runs of the program. */
static SDL_Rect saved_window;

static void remember_window(void) {
    if (!run.win || rrhk.fullscreen) return;
    SDL_GetWindowPosition(run.win, &saved_window.x, &saved_window.y);
    SDL_GetWindowSize(run.win, &saved_window.w, &saved_window.h);
}

static void restore_window(void) {
    if (!run.win || !saved_window.w) return;
    SDL_SetWindowPosition(run.win, saved_window.x, saved_window.y);
    SDL_SetWindowSize(run.win, saved_window.w, saved_window.h);
}

/* The window set of divergences 6 and 7 (decided, D3): the SDL hints of the Master System and Game Gear host for every
 * machine. Direct3D 11 caps queued frames at one on Windows (SDL's automatic fallback and an explicit SDL_RENDER_DRIVER
 * still win); elsewhere X11 may present without a compositor, so synchronized swaps are requested (SDL_RENDER_VSYNC=0
 * overrides). The guest clock uses its own deadline, vsync or not. */
static void set_hints(void) {
    SDL_SetHint(SDL_HINT_RENDER_SCALE_QUALITY, "0");
    SDL_SetHint(SDL_HINT_XINPUT_ENABLED, "1");
    SDL_SetHint(SDL_HINT_WINDOWS_DPI_AWARENESS, "permonitorv2");
#ifdef _WIN32
    SDL_SetHintWithPriority(SDL_HINT_RENDER_DRIVER, "direct3d11", SDL_HINT_DEFAULT);
    SDL_SetHintWithPriority(SDL_HINT_JOYSTICK_THREAD, "1", SDL_HINT_DEFAULT);
#else
    SDL_SetHintWithPriority(SDL_HINT_RENDER_VSYNC, "1", SDL_HINT_DEFAULT);
#endif
}

/* Everything before the first iteration. false: no window, and nothing is left open. */
static bool open_run(const RrhkMachine *m, const char *title, int scale) {
    RrhkRun *r = &run;
    memset(r, 0, sizeof *r);
    r->machine = m;
    r->title = title;
    r->driven = m->driven;
    SDL_SetMainReady();
    set_hints();
    if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_GAMECONTROLLER | (m->driven ? SDL_INIT_TIMER : SDL_INIT_AUDIO)) != 0) {
        fprintf(stderr, "[host] SDL: %s\n", SDL_GetError());
        return false;
    }
    /* A guest that is restarted opens the shell again: nothing of the previous menus survives. */
    rrhk.menu = rrhk.parent_menu = rrhk.player = rrhk.row = rrhk.gamepad_page = rrhk.capturing = rrhk.paused = 0;
    rrhk.status[0] = 0;
    rrhk_bind(m);
    rrhk_load_bindings();
    rrhk_options_init(m->ini_section);
    if (m->machine_fkeys) rrhk_options_keyboard(m->console_name, m->machine_fkeys);
    const char *test_limit = getenv("RETRORECOMP_HOST_TEST_FRAMES");
    r->test_frames = test_limit ? (unsigned)atoi(test_limit) : 0;
    if (!r->test_frames && m->frame_limit) r->test_frames = m->frame_limit();
    const char *test_no_audio = getenv("RETRORECOMP_HOST_TEST_NO_AUDIO");
    r->video_clock_test = r->test_frames && test_no_audio && test_no_audio[0] == '1';
    if (m->state_path) m->state_path(r->state_path, 32768);
    if (scale < 1) scale = 3;
    snprintf(r->caption, sizeof(r->caption), "%s | %s", title, "Native code");
    r->win = SDL_CreateWindow(r->caption, SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
        m->display_width() * scale, m->raster_height() * scale, SDL_WINDOW_RESIZABLE | SDL_WINDOW_ALLOW_HIGHDPI |
        (r->test_frames ? SDL_WINDOW_HIDDEN : 0));
    if (r->win) {
        if (m->window_icon) m->window_icon(r->win); else rr_set_window_icon(r->win);
        if (m->minimum_window) SDL_SetWindowMinimumSize(r->win, m->display_width(), m->raster_height());
        restore_window();
    }
    if (r->win && rrhk.fullscreen && SDL_SetWindowFullscreen(r->win, SDL_WINDOW_FULLSCREEN_DESKTOP) != 0) rrhk.fullscreen = 0;
    r->ren = r->win ? SDL_CreateRenderer(r->win, -1, SDL_RENDERER_ACCELERATED) : NULL;
    if (!r->ren && r->win) r->ren = SDL_CreateRenderer(r->win, -1, SDL_RENDERER_SOFTWARE);
    if (r->ren) {
        SDL_RendererInfo info;
        if (SDL_GetRendererInfo(r->ren, &info) == 0)
            fprintf(stderr, "[host] renderer=%s, vsync=%s; physical latency is unmeasured\n",
                info.name, info.flags & SDL_RENDERER_PRESENTVSYNC ? "on" : "off");
    }
    r->tex = r->ren ? rrhk_texture_create(r) : NULL;
    r->upscaled = (uint32_t *)malloc(m->max_width * 2 * m->max_height * 2 * sizeof(uint32_t));
    if (!r->tex || !r->upscaled) {
        free(r->upscaled); if (r->ren) SDL_DestroyRenderer(r->ren); if (r->win) SDL_DestroyWindow(r->win);
        r->ren = NULL; r->win = NULL; r->upscaled = NULL;
        return false;
    }
    SDL_SetTextureScaleMode(r->tex, SDL_ScaleModeNearest);
    rr_menu_init(r->ren);
    rrhk_audio_open(r);
    rrhk_open_pads();
    r->frequency = SDL_GetPerformanceFrequency();
    r->next = SDL_GetPerformanceCounter();
    r->test_started = r->next;
    r->timing_path = getenv("RETRORECOMP_TIMING_REPORT");
    r->timing_enabled = r->timing_path && *r->timing_path;
    r->title_state = -1;
    r->running = true;
    r->ran = true;      /* a guest that owns the loop has run its first frame when it first calls */
    const char *test_filter = r->test_frames ? getenv("RETRORECOMP_HOST_TEST_FILTER") : NULL;
    if (test_filter && !strcmp(test_filter, "3")) rrhk.filter = 3;
    return true;
}

static uint64_t now_ticks(void) { return SDL_GetPerformanceCounter(); }

/* The first half of an iteration: events, quit and restart, the state requests, the pads, and the machine's frame (or,
 * for a guest that owns the loop, the hand-over of the pad words: the guest runs when the caller returns). false: stop. */
static bool begin_frame(RrhkRun *r) {
    const RrhkMachine *m = r->machine;
    memset(r->ticks, 0, sizeof r->ticks);
    r->cpu_started = r->timing_enabled ? rrhk_thread_cpu() : 0;
    r->ran_frame = false;
    if (r->timing_enabled) r->ticks[0] = now_ticks();
    rrhk_audio_wait_room(r);
    if (m->frame_start) m->frame_start(r->win, r->ren);
    rrhk_poll_events(r);
    if (rrhk_options_quit(rrhk.menu)) r->running = false;
    else if (rrhk_options_restart(rrhk.menu)) { m->reset(); rrhk_audio_pause_output(r); rrhk.menu = 0; }
    if (!r->running) return false;
    /* A computer's fast loading key: no pacing, no sound, a picture every eighth frame. */
    bool fast = m->fast_forward && m->fast_forward();
    if (fast != r->fast) { r->fast = fast; r->next = now_ticks(); rrhk_audio_pause_output(r); }
    if (r->pending_state && m->state_ready()) {
        bool load = r->pending_state == 2;
        bool ok = m->state_file(r->state_path, load);
        r->pending_state = 0;
        if (m->state_deferred) {
            /* The machine services the request at its own safe boundary and reports with rrhk_state_done. */
            if (ok) { rrhk.menu = rrhk.parent_menu = 0; rrhk.capturing = 0; }
            else rrhk_notice(m->save_failed_en ? rrhk_tr(m->save_failed_en, m->save_failed_fr) : rrhk_tr("Cannot save game state", "Impossible de sauvegarder"), 1800);
        } else {
            const char *message = ok ? (load ? rrhk_tr("Quick state loaded", "Partie chargee") : rrhk_tr("Quick state saved", "Partie sauvegardee")) :
                (load ? rrhk_tr("No compatible quick state to load", "Aucune sauvegarde compatible") :
                 m->save_failed_en ? rrhk_tr(m->save_failed_en, m->save_failed_fr) : rrhk_tr("Cannot save game state", "Impossible de sauvegarder"));
            rrhk_notice(message, 1800);
            if (ok) { rrhk.menu = rrhk.parent_menu = 0; rrhk.capturing = 0; }
            if (ok && load) { rrhk_audio_pause_output(r); r->next = now_ticks(); }
        }
    }
    bool idle = (rrhk.menu != 0 || rrhk.paused) && !r->pending_state;
    m->pause(idle);
    /* Explicit performance reports only; include CPU, audio preparation,
     * drawing and Present, but exclude intentional pacing/menu waits. */
    r->work_started = m->cost_enabled && m->cost_enabled() && !rrhk.menu && !rrhk.paused ? now_ticks() : 0;
    uint64_t input_frame = m->input_frame ? m->input_frame() : r->frame;
    uint16_t pad1 = rrhk_pad_word(0, input_frame);
    if (m->pointer) rrhk_pointer_sample(r->win, r->ren, pad1);
    r->ran = !idle;
    if (r->ran) {
        if (r->timing_enabled) r->ticks[1] = now_ticks();
        if (m->before_frame) {
            RrhkAudioProbe probe = {r->audio_playing, rrhk_audio_queued(r),
                                    (unsigned)r->have.freq, r->have.samples};
            m->before_frame(&probe, input_frame);
        }
        if (!m->run_frame(pad1, m->pointer && !m->pointer_keeps_player2 ? 0 : rrhk_pad_word(1, input_frame))) { r->running = false; return false; }
        ++r->frame;
        r->ran_frame = true;
    }
    return true;
}

/* The second half: the sound of the frame just run, the picture, the title, the menus and notices, and the pacing. */
static void end_frame(RrhkRun *r) {
    const RrhkMachine *m = r->machine;
    if (r->ran) {
        if (r->timing_enabled) r->ticks[2] = now_ticks();
        rrhk_audio_frame(r);
        if (r->test_frames && r->frame >= r->test_frames) r->running = false;
    } else rrhk_audio_idle(r);
    if (r->timing_enabled) r->ticks[3] = now_ticks();
    const bool shown = !r->fast || (r->frame & 7) == 0;
    if (shown) rrhk_present_picture(r);

    int current_title_state = (m->interpreted() || m->audio_interpreted() ? 1 : 0);
    /* A cartridge device (GSU, CX4, DSP-1) still running on its instruction
     * core is signalled apart from the CPUs; it is never hidden. */
    if (m->device_interpreted && !current_title_state && m->device_interpreted()) current_title_state = 2;
    if (current_title_state != r->title_state) {
        snprintf(r->caption, sizeof(r->caption), "%s | %s", r->title,
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
    Uint64 present_started = r->work_started ? now_ticks() : 0;
    if (r->timing_enabled) r->ticks[4] = now_ticks();
    if (shown) SDL_RenderPresent(r->ren);
    Uint64 now = now_ticks();
    r->ticks[5] = now;
    if (r->work_started && m->cost) m->cost(1000.0 * (now - r->work_started) / r->frequency,
                                           1000.0 * (now - present_started) / r->frequency);
    if (rrhk.menu || rrhk.paused) { r->next = now; SDL_Delay(16); return; }
    if (r->fast) { r->next = now; return; }
    r->next += (Uint64)(m->frame_seconds * r->frequency);
    rrhk_audio_pace(r, now);
    if (r->next > now) {
        Uint32 ms = (Uint32)((r->next - now) * 1000 / r->frequency);
        if (ms > 1) SDL_Delay(ms - 1);
        while (SDL_GetPerformanceCounter() < r->next) {}
    } else if (now - r->next > r->frequency / 4) r->next = now;
    if (r->timing_enabled && r->ran_frame) {
        r->ticks[6] = now_ticks();
        ++r->timing.frames; r->timing.thread_cpu += rrhk_thread_cpu() - r->cpu_started;
        for (unsigned n = 0; n < 6; ++n) {
            double seconds = (double)(r->ticks[n + 1] - r->ticks[n]) / r->frequency;
            r->timing.total[n] += seconds;
            if (seconds > r->timing.maximum[n]) r->timing.maximum[n] = seconds;
        }
    }
}

static void close_run(RrhkRun *r) {
    const RrhkMachine *m = r->machine;
    double elapsed = (double)(SDL_GetPerformanceCounter() - r->test_started) / r->frequency;
    if (m->finished) m->finished(elapsed);
    if (r->test_frames) {
        fprintf(stderr, "{\"host_frames\":%llu,\"wall_seconds\":%.6f,\"expected_seconds\":%.6f,"
                "\"measured_fps\":%.6f,\"target_fps\":%.6f,\"video_clock_only\":%s}\n",
                (unsigned long long)r->frame, elapsed, r->frame * m->frame_seconds, r->frame / elapsed, 1.0 / m->frame_seconds,
                r->video_clock_test ? "true" : "false");
    }
    rrhk_timing_write(m, r->timing_path, &r->timing, r->ren, r->frequency);
    rr_feedback_close_screen(r->ren);
    remember_window();
    rrhk_audio_close(r);
    rrhk_close_pads();
    rr_menu_shutdown(); free(r->upscaled); if (r->tex) SDL_DestroyTexture(r->tex);
    rr_xbr_destroy(&r->xbr);
    rr_scanlines_destroy(&r->scanlines);
    SDL_ShowCursor(SDL_ENABLE);
    SDL_DestroyRenderer(r->ren); SDL_DestroyWindow(r->win);
    r->ren = NULL; r->win = NULL; r->tex = NULL; r->upscaled = NULL;
}

int rrhk_main(const RrhkMachine *m, const char *title, int scale) {
    if (!open_run(m, title, scale)) return 1;
    RrhkRun *r = &run;
    while (r->running) {
        if (!begin_frame(r)) break;
        end_frame(r);
    }
    close_run(r);
    return 0;
}

/* A guest that owns the loop: it ran a frame, and calls here with the picture ready. The end of that iteration, then as many
 * iterations as the menus need (the guest does not run meanwhile), then the beginning of the one the guest runs for. */
bool rrhk_open(const RrhkMachine *m, const char *title, int scale) { return open_run(m, title, scale); }

bool rrhk_frame_done(void) {
    RrhkRun *r = &run;
    if (!r->win) return false;
    end_frame(r);
    while (r->running) {
        if (!begin_frame(r)) return false;
        if (r->ran) return true;
        end_frame(r);
    }
    return false;
}

void rrhk_stop(void) { run.running = false; }

void rrhk_pointer_poll(uint16_t pad1) {
    if (run.win && run.machine->pointer) rrhk_pointer_sample(run.win, run.ren, pad1);
}

void rrhk_close(void) {
    if (run.win) close_run(&run);
}

SDL_Window *rrhk_window(void) { return run.win; }

/* F4 and the computers' own display shortcut. Window, then integer-scale fullscreen, then fit fullscreen, then the window
 * again at the position and size it had (divergence 8). Going from one fullscreen mode to the other keeps the window as it is. */
void rrhk_cycle_display(void) {
    int wanted = (rrhk.fullscreen + 1) % 3;
    bool leaving_window = rrhk.fullscreen == 0, entering_window = wanted == 0;
    if (leaving_window) remember_window();
    if ((leaving_window || entering_window) &&
        SDL_SetWindowFullscreen(run.win, wanted ? SDL_WINDOW_FULLSCREEN_DESKTOP : 0) != 0) return;
    rrhk.fullscreen = wanted;
    if (entering_window) restore_window();
    if (!rrhk_write_ready() || !rr_display_save(rrhk.ini_file, rrhk.data_dir, rrhk.video_section, L"display_mode", wanted))
        snprintf(rrhk.status, sizeof(rrhk.status), "%s", rrhk_tr("Config unavailable", "Config inaccessible"));
}

void rrhk_notice(const char *text, Uint64 milliseconds) {
    snprintf(rrhk.status, sizeof rrhk.status, "%s", text);
    rrhk.status_until = SDL_GetTicks64() + milliseconds;
}

/* The outcome of a deferred state request (RrhkMachine.state_deferred), from the machine's own safe boundary. */
void rrhk_state_done(bool load, int result) {
    const RrhkMachine *m = run.machine;
    if (result == 0) {
        rrhk_notice(load ? rrhk_tr("Quick state loaded", "Partie chargee") : rrhk_tr("Quick state saved", "Partie sauvegardee"), 1800);
        if (load) { rrhk_audio_pause_output(&run); run.next = now_ticks(); }
    } else if (load) rrhk_notice(rrhk_tr("No compatible quick state to load", "Aucune sauvegarde compatible"), 1800);
    else rrhk_notice(m && m->save_failed_en ? rrhk_tr(m->save_failed_en, m->save_failed_fr) : rrhk_tr("Cannot save game state", "Impossible de sauvegarder"), 1800);
}
