/* Presentation, native menus and input. The game remains in its generated C
 * routines. Pausing waits here; resetting unwinds them through glue_run(). */
#include <SDL.h>
#include "host_sdl.h"
#include "host_control.h"
#include "controls.h"
#include "ui.h"
#include "glue.h"
#include "video/sms_vdp.h"
#include "video_frame.h"
#include "embedded_rom.h"
#include "icon.h"
#include "lightphaser.h"
#include "gamestate.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static SDL_Window *window;
static SDL_Renderer *renderer;
static SDL_Texture *texture, *texture2x, *texture_cropped, *texture_cropped2x;
static SDL_GameController *controllers[CONTROL_PLAYERS];
static SDL_Rect crop, full_crop, saved_window;
static uint32_t enlarged[512 * 384];
static uint8_t pads[CONTROL_PLAYERS];
static double frequency, period;
static uint64_t deadline;
static uint64_t input_sample_counter, input_poll_period;
static SDL_AudioDeviceID audio_device;
static SDL_AudioStream *audio_stream;
static uint64_t previous_interpreter_cycles;
static int previous_interpreter_state = -1;
static bool fullscreen, reset_requested, back_latched[CONTROL_PLAYERS];
static bool fullscreen_fit;
static int menu, parent_menu, selected_row, selected_player;
static int controller_order_player;
static bool bind_gamepad, capturing;
static char menu_status[80], toast[80];
static uint64_t toast_until;
static int gun_x = -1, gun_y = -1;
static bool gun_trigger_blocked;
static int gun_option_row = 1;
static void state_completed(int operation, int result);

int smsrecomp_take_reset_request(void) {
    bool requested = reset_requested; reset_requested = false; return requested;
}

static void notice(const char *s) {
    snprintf(toast, sizeof(toast), "%s", s);
    toast_until = SDL_GetTicks64() + 2400;
}

static int controller_player(SDL_JoystickID instance) {
#ifdef RETRO_GAME_GEAR
    const int active_players = 1;
#else
    const int active_players = CONTROL_PLAYERS;
#endif
    for (int p = 0; p < active_players; ++p)
        if (controllers[p] && instance == SDL_JoystickInstanceID(SDL_GameControllerGetJoystick(controllers[p]))) return p;
    return -1;
}

static void open_controllers(void) {
    for (int i = 0; i < SDL_NumJoysticks(); ++i) {
        if (!SDL_IsGameController(i) || controller_player(SDL_JoystickGetDeviceInstanceID(i)) >= 0) continue;
        int p = controller_order_player;
#ifndef RETRO_GAME_GEAR
        if (controllers[p]) p ^= 1;
#endif
        if (controllers[p]) return;
        controllers[p] = SDL_GameControllerOpen(i);
        if (controllers[p]) {
            SDL_GameControllerSetPlayerIndex(controllers[p], p);
            const char *menu_button = SDL_GameControllerGetStringForButton(controls.buttons[p][CONTROL_PAUSE]);
            const char *reset_button = SDL_GameControllerGetStringForButton(controls.buttons[p][CONTROL_RESET]);
#ifdef RETRO_GAME_GEAR
            fprintf(stderr, "[host] player %d controller: %s; menu=%s, cartridge_start=%s\n",
#else
            fprintf(stderr, "[host] player %d controller: %s; menu=%s, reset=%s\n",
#endif
                p + 1, SDL_GameControllerName(controllers[p]),
                menu_button ? menu_button : "unassigned",
                p == 0 ? (reset_button ? reset_button : "unassigned") : "disabled");
        }
    }
}

static void apply_controller_order(void) {
#ifdef RETRO_GAME_GEAR
    return;
#else
    if (controller_order_player == controls.first_controller_player) return;
    SDL_GameController *old = controllers[0]; controllers[0] = controllers[1]; controllers[1] = old;
    bool held = back_latched[0]; back_latched[0] = back_latched[1]; back_latched[1] = held;
    memset(pads, 0, sizeof(pads));
    controls_reset_autofire();
    controller_order_player = controls.first_controller_player;
    for (int p = 0; p < CONTROL_PLAYERS; ++p) if (controllers[p]) SDL_GameControllerSetPlayerIndex(controllers[p], p);
#endif
}

bool host_init(int width, int height, int x, int y, int crop_w, int crop_h,
               int scale, const char *unused_title) {
    (void)unused_title;
    SDL_SetMainReady();
    SDL_SetHint(SDL_HINT_RENDER_SCALE_QUALITY, "0");
    SDL_SetHint(SDL_HINT_XINPUT_ENABLED, "1");
    SDL_SetHint(SDL_HINT_WINDOWS_DPI_AWARENESS, "permonitorv2");
#ifdef _WIN32
    /* SDL's D3D11 backend caps queued frames at one. Keep SDL's automatic
     * fallback and allow an explicit SDL_RENDER_DRIVER override. */
    SDL_SetHintWithPriority(SDL_HINT_RENDER_DRIVER, "direct3d11", SDL_HINT_DEFAULT);
    SDL_SetHintWithPriority(SDL_HINT_JOYSTICK_THREAD, "1", SDL_HINT_DEFAULT);
#endif
    if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_GAMECONTROLLER | SDL_INIT_TIMER) != 0) {
        fprintf(stderr, "[host] SDL: %s\n", SDL_GetError()); return false;
    }
    controls_load();
    controller_order_player = controls.first_controller_player;
    full_crop = crop = (SDL_Rect){x, y, crop_w, crop_h};
    if (scale < 1) scale = 1;
    window = SDL_CreateWindow(sms_game_title, SDL_WINDOWPOS_CENTERED,
        SDL_WINDOWPOS_CENTERED, crop_w * scale, crop_h * scale,
        SDL_WINDOW_SHOWN | SDL_WINDOW_RESIZABLE | SDL_WINDOW_ALLOW_HIGHDPI);
    if (!window) return false;
    smsrecomp_set_window_icon(window);
    SDL_SetWindowMinimumSize(window, crop_w, crop_h);
    if (saved_window.w) {
        SDL_SetWindowPosition(window, saved_window.x, saved_window.y);
        SDL_SetWindowSize(window, saved_window.w, saved_window.h);
    }
    if (fullscreen && SDL_SetWindowFullscreen(window, SDL_WINDOW_FULLSCREEN_DESKTOP) < 0) fullscreen = false;
    renderer = SDL_CreateRenderer(window, -1, SDL_RENDERER_ACCELERATED);
    if (!renderer) renderer = SDL_CreateRenderer(window, -1, SDL_RENDERER_SOFTWARE);
    if (!renderer) return false;
    SDL_RendererInfo renderer_info;
    if (SDL_GetRendererInfo(renderer, &renderer_info) == 0)
        fprintf(stderr, "[host] renderer=%s, vsync=%s; physical latency is unmeasured\n",
            renderer_info.name, renderer_info.flags & SDL_RENDERER_PRESENTVSYNC ? "on" : "off");
    texture = SDL_CreateTexture(renderer, SDL_PIXELFORMAT_ARGB8888, SDL_TEXTUREACCESS_STREAMING, crop_w, crop_h);
    texture2x = SDL_CreateTexture(renderer, SDL_PIXELFORMAT_ARGB8888, SDL_TEXTUREACCESS_STREAMING, crop_w * 2, crop_h * 2);
    if (x == 0 && crop_w == SMS_SCREEN_W) {
        texture_cropped = SDL_CreateTexture(renderer, SDL_PIXELFORMAT_ARGB8888, SDL_TEXTUREACCESS_STREAMING, crop_w - 8, crop_h);
        texture_cropped2x = SDL_CreateTexture(renderer, SDL_PIXELFORMAT_ARGB8888, SDL_TEXTUREACCESS_STREAMING, (crop_w - 8) * 2, crop_h * 2);
        if (!texture_cropped || !texture_cropped2x) return false;
    }
    if (!texture || !texture2x || !ui_init(renderer)) {
        fprintf(stderr, "[host] texture/font init: %s\n", SDL_GetError()); return false;
    }
    open_controllers();
    memset(pads, 0, sizeof(pads));
    controls_reset_autofire();
    input_sample_counter = 0;
    input_poll_period = SDL_GetPerformanceFrequency() / 1000;
    if (!input_poll_period) input_poll_period = 1;
    menu = parent_menu = selected_row = selected_player = 0; capturing = bind_gamepad = false;
    menu_status[0] = 0; previous_interpreter_state = -1; previous_interpreter_cycles = 0;
    gun_x = gun_y = -1; gun_trigger_blocked = false;
    gun_option_row = 1;
    smsrecomp_set_state_callback(state_completed);
    notice(sms_light_phaser ? controls_text("Light Phaser: mouse | F5: options", "Light Phaser : souris | F5 : options") :
        controls_text("H: help | P / Enter: pause", "H : aide | P / Entree : pause"));
    if (sms_light_phaser) fprintf(stderr, "[host] Light Phaser: mouse, left=trigger, right=off-screen; reticle=%s size=%d color=%d\n",
        controls.phaser_shape == PHASER_DOT ? "dot" : "cross", controls.phaser_dot_size, controls.phaser_color);
    return true;
}

void host_set_frame_cap(double fps) {
    frequency = (double)SDL_GetPerformanceFrequency();
    period = fps > 0.0 ? frequency / fps : 0.0;
    deadline = 0;
}

static void pace(void) {
    if (period <= 0.0) return;
    uint64_t now = SDL_GetPerformanceCounter();
    if (!deadline) deadline = now;
    deadline += (uint64_t)period;
    if (now > deadline + (uint64_t)(period * 4.0)) deadline = now + (uint64_t)period;
    for (;;) {
        now = SDL_GetPerformanceCounter();
        if (now >= deadline) return;
        double ms = (double)(deadline - now) * 1000.0 / frequency;
        if (ms > 2.0) SDL_Delay((uint32_t)(ms - 1.0));
    }
}

static void scale2x(const uint32_t *src, int w, int h, int stride, uint32_t *dst) {
    for (int y = 0; y < h; ++y) for (int x = 0; x < w; ++x) {
        uint32_t e = src[y*stride+x], b = src[(y ? y-1 : y)*stride+x], d = src[y*stride+(x ? x-1 : x)];
        uint32_t f = src[y*stride+(x+1 < w ? x+1 : x)], z = src[(y+1 < h ? y+1 : y)*stride+x];
        int p = (y*2)*(w*2) + x*2;
        if (b != z && d != f) {
            dst[p] = d == b ? d : e; dst[p+1] = b == f ? f : e;
            dst[p+w*2] = d == z ? d : e; dst[p+w*2+1] = z == f ? f : e;
        } else dst[p] = dst[p+1] = dst[p+w*2] = dst[p+w*2+1] = e;
    }
}

/* Windowed/first-fullscreen modes keep integer pixels. The second fullscreen
 * mode fills the output using the visible image's aspect ratio. */
static SDL_Rect game_rect(int out_w, int out_h, int *scale) {
    if (fullscreen && fullscreen_fit) {
        int width, height;
        if ((int64_t)out_w * crop.h <= (int64_t)out_h * crop.w) {
            width = out_w; height = SDL_max(1, (int)((int64_t)out_w * crop.h / crop.w));
        } else {
            height = out_h; width = SDL_max(1, (int)((int64_t)out_h * crop.w / crop.h));
        }
        *scale = SDL_max(1, SDL_min(width / crop.w, height / crop.h));
        return (SDL_Rect){(out_w-width)/2, (out_h-height)/2, width, height};
    }
    /* Keep the scale stable when a game enables/disables left-column blanking,
     * including width-limited windows near an integer-scale threshold. */
    int k = SDL_min(out_w / full_crop.w, out_h / full_crop.h);
    if (k < 1) k = 1;
    if (controls.filter == FILTER_SCALE2X && k >= 2) k -= k % 2;
    *scale = k;
    return (SDL_Rect){(out_w - crop.w*k)/2, (out_h - crop.h*k)/2, crop.w*k, crop.h*k};
}

/* Use the mask attached to the rendered frame, not a shared setting or live
 * register. Keep the window and fullscreen restore size unchanged. */
static void update_viewport(void) {
    crop = full_crop;
    if (full_crop.x == 0 && full_crop.w == SMS_SCREEN_W && smsrecomp_frame_left_border() == 8) {
        crop.x += 8; crop.w -= 8;
    }
}

/* SDL mouse coordinates are in window units; the renderer can be HiDPI.
 * Inverse-map the exact same cropped/scaled rectangle as the image.
 * Letterbox clicks remain off-screen instead of snapping to an edge. */
static bool gun_coordinates(int mouse_x, int mouse_y, int win_w, int win_h,
                            int out_w, int out_h, int *x, int *y) {
    if (win_w <= 0 || win_h <= 0) return false;
    int k; SDL_Rect dest = game_rect(out_w, out_h, &k);
    int px = (int)((int64_t)mouse_x * out_w / win_w);
    int py = (int)((int64_t)mouse_y * out_h / win_h);
    if (mouse_x < 0 || mouse_y < 0 || px < dest.x || px >= dest.x + dest.w || py < dest.y || py >= dest.y + dest.h) return false;
    *x = crop.x + (int)((int64_t)(px - dest.x) * crop.w / dest.w);
    *y = crop.y + (int)((int64_t)(py - dest.y) * crop.h / dest.h);
    return true;
}

static void sample_phaser(bool focused) {
    if (!lightphaser_enabled()) return;
    int mx, my, win_w, win_h, out_w, out_h;
    uint32_t buttons = SDL_GetMouseState(&mx, &my);
    if (!(buttons & (SDL_BUTTON_LMASK | SDL_BUTTON_RMASK))) gun_trigger_blocked = false;
    SDL_GetWindowSize(window, &win_w, &win_h);
    SDL_GetRendererOutputSize(renderer, &out_w, &out_h);
    gun_x = gun_y = -1;
    bool inside = focused && !menu && SDL_GetMouseFocus() == window &&
        gun_coordinates(mx, my, win_w, win_h, out_w, out_h, &gun_x, &gun_y);
    bool pressed = focused && !menu && !gun_trigger_blocked &&
        (buttons & (SDL_BUTTON_LMASK | SDL_BUTTON_RMASK));
    bool offscreen = !inside || (buttons & SDL_BUTTON_RMASK);
    lightphaser_pointer(offscreen ? -1 : gun_x, offscreen ? -1 : gun_y, pressed);
    SDL_ShowCursor(inside ? SDL_DISABLE : SDL_ENABLE);
    /* Laser Ghost selects its original gun mode through a P2 trigger.
     * Supply that alias as well as P1 TL; no cartridge code is patched. */
    if (pressed && sms_light_phaser_trigger_p2) pads[1] |= SMS_PAD_B1;
}

static void draw_phaser(const SDL_Rect *dest, int scale) {
    if (!lightphaser_enabled() || menu || gun_x < crop.x || gun_y < crop.y) return;
    SDL_RenderSetClipRect(renderer, dest);
    ui_phaser_reticle(renderer, dest->x + (int)((int64_t)(gun_x - crop.x)*dest->w/crop.w),
        dest->y + (int)((int64_t)(gun_y - crop.y)*dest->h/crop.h), scale);
    SDL_RenderSetClipRect(renderer, NULL);
}

static void draw_game(const uint32_t *fb, int w, int h) {
    update_viewport();
    bool trimmed = crop.w != full_crop.w;
    SDL_Texture *image = trimmed ? texture_cropped : texture;
    const uint32_t *pixels = fb + crop.y * w + crop.x;
    int out_w, out_h, k; SDL_GetRendererOutputSize(renderer, &out_w, &out_h);
    SDL_Rect dest = game_rect(out_w, out_h, &k);
    if (controls.filter == FILTER_SCALE2X && k >= 2 && w <= 256 && h <= 192) {
        /* Filter only the visible area, so masked backdrop pixels cannot bleed
         * back into the game at the edge. Textures are cached at both widths. */
        scale2x(pixels, crop.w, crop.h, w, enlarged);
        image = trimmed ? texture_cropped2x : texture2x;
        SDL_UpdateTexture(image, NULL, enlarged, crop.w * 8);
    } else SDL_UpdateTexture(image, NULL, pixels, w * 4);
    SDL_SetTextureScaleMode(image, controls.filter == FILTER_LINEAR ? SDL_ScaleModeLinear : SDL_ScaleModeNearest);
    SDL_SetRenderDrawColor(renderer, 0, 0, 0, 255); SDL_RenderClear(renderer);
    SDL_RenderCopy(renderer, image, NULL, &dest);
    if (controls.filter == FILTER_SCANLINES && k >= 2) {
        SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
        SDL_SetRenderDrawColor(renderer, 0, 0, 0, 95);
        for (int y = 0; y < crop.h; ++y) {
            int top = (int)((int64_t)y * dest.h / crop.h);
            int bottom = (int)((int64_t)(y+1) * dest.h / crop.h);
            SDL_Rect line = {dest.x, dest.y + bottom - (bottom-top)/2, dest.w, (bottom-top)/2};
            SDL_RenderFillRect(renderer, &line);
        }
        SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_NONE);
    }
    draw_phaser(&dest, k);
}

static void clear_audio(void) {
    if (audio_device) SDL_ClearQueuedAudio(audio_device);
    if (audio_stream) SDL_AudioStreamClear(audio_stream);
}

static void state_completed(int operation, int result) {
    if (result == RR_STATE_OK) {
        if (operation == RR_QUICKLOAD) {
            clear_audio(); deadline = input_sample_counter = 0;
            controls_reset_autofire(); previous_interpreter_state = -1;
        }
        notice(operation == RR_QUICKSAVE ? controls_text("Game state saved", "Etat du jeu sauvegarde") :
            controls_text("Game state loaded", "Etat du jeu charge"));
    } else if (result == RR_STATE_MISSING) notice(controls_text("No saved game state yet", "Aucun etat sauvegarde"));
    else if (result == RR_STATE_INCOMPATIBLE) notice(controls_text("Game state incompatible", "Etat du jeu incompatible"));
    else if (result == RR_STATE_INVALID) notice(controls_text("Game state invalid; game unchanged", "Etat invalide ; jeu inchange"));
    else notice(controls_text("Cannot read/write game state", "Impossible de lire/ecrire l'etat"));
}

static void toggle_fullscreen(void) {
    if (fullscreen && !fullscreen_fit) {
        fullscreen_fit = true;
        notice(controls_text("Fullscreen - fit, original ratio", "Plein ecran ajuste - ratio conserve"));
        deadline = 0; return;
    }
    bool wanted = !fullscreen;
    if (wanted) {
        SDL_GetWindowPosition(window, &saved_window.x, &saved_window.y);
        SDL_GetWindowSize(window, &saved_window.w, &saved_window.h);
    }
    if (SDL_SetWindowFullscreen(window, wanted ? SDL_WINDOW_FULLSCREEN_DESKTOP : 0) == 0) {
        fullscreen = wanted;
        fullscreen_fit = false;
        if (!fullscreen && saved_window.w) {
            SDL_SetWindowPosition(window, saved_window.x, saved_window.y);
            SDL_SetWindowSize(window, saved_window.w, saved_window.h);
        }
        notice(fullscreen ? controls_text("Fullscreen - integer scale", "Plein ecran - echelle entiere") : controls_text("Windowed", "Mode fenetre"));
    } else notice(controls_text("Fullscreen unavailable", "Plein ecran indisponible"));
    deadline = 0;
}

static void toggle_menu(int kind) {
    controls_reset_autofire();
    capturing = false; menu_status[0] = 0;
    if (menu == kind) { menu = parent_menu; parent_menu = 0; }
    else { if (menu == 3) parent_menu = 3; menu = kind; }
}

static void change_gun_option(int change) {
    bool ok;
    if (gun_option_row == 0)
        ok = controls_phaser_shape((controls.phaser_shape + change + PHASER_SHAPE_COUNT) % PHASER_SHAPE_COUNT);
    else if (gun_option_row == 1)
        ok = controls_phaser_dot_size(SDL_clamp(controls.phaser_dot_size + change, 1, 5));
    else ok = controls_phaser_color((controls.phaser_color + change + PHASER_COLOR_COUNT) % PHASER_COLOR_COUNT);
    if (!ok) notice(controls_text("Config unavailable", "Config inaccessible"));
}

static bool handle_event(const SDL_Event *e) {
    if (e->type == SDL_QUIT) return false;
    if (e->type == SDL_CONTROLLERDEVICEADDED) open_controllers();
    if (e->type == SDL_CONTROLLERDEVICEREMOVED) {
        int p = controller_player(e->cdevice.which);
        if (p >= 0) {
            SDL_GameControllerClose(controllers[p]); controllers[p] = NULL;
            pads[p] = 0; back_latched[p] = false;
            if (selected_player == p) capturing = false;
            /* The other connected controller keeps its player assignment. */
            open_controllers();
        }
    }
    int event_player = -1;
    if ((e->type == SDL_CONTROLLERBUTTONDOWN || e->type == SDL_CONTROLLERBUTTONUP) &&
        (event_player = controller_player(e->cbutton.which)) < 0) return true;
    if (e->type == SDL_CONTROLLERBUTTONUP && controls_system_button(event_player, e->cbutton.button, CONTROL_RESET)) back_latched[event_player] = false;
    bool keyboard = e->type == SDL_KEYDOWN && !e->key.repeat;
    bool gamepad = e->type == SDL_CONTROLLERBUTTONDOWN;
    if (!keyboard && !gamepad) {
        if (e->type == SDL_MOUSEBUTTONDOWN && e->button.button == SDL_BUTTON_LEFT && menu == 4) {
            int ox, oy, unit, out_w, out_h, win_w, win_h;
            ui_layout(renderer, &ox, &oy, &unit); SDL_GetRendererOutputSize(renderer, &out_w, &out_h);
            SDL_GetWindowSize(window, &win_w, &win_h);
            int x = (e->button.x * out_w / win_w - ox) / unit;
            int y = (e->button.y * out_h / win_h - oy) / unit;
            if (x >= 14 && x < 240 && y >= 34 && y < 106 && (y-34)%24 < 22) {
                gun_option_row = (y-34)/24;
                change_gun_option(x < 42 ? -1 : 1);
            }
        }
        if (e->type == SDL_MOUSEBUTTONDOWN && e->button.button == SDL_BUTTON_LEFT && menu == 2 && !capturing) {
            int ox, oy, unit, out_w, out_h, win_w, win_h;
            ui_layout(renderer, &ox, &oy, &unit); SDL_GetRendererOutputSize(renderer, &out_w, &out_h);
            SDL_GetWindowSize(window, &win_w, &win_h);
            int x = (e->button.x * out_w / win_w - ox) / unit;
            int y = (e->button.y * out_h / win_h - oy) / unit;
            if (x >= 12 && x < 244 && y >= 30 && y < 42) {
#ifndef RETRO_GAME_GEAR
                selected_player ^= 1; menu_status[0] = 0;
                selected_row = SDL_min(selected_row, controls_action_count(selected_player) - 1);
#endif
            } else if (x >= 12 && x < 244 && y >= 58 && y < 58 + 12 * controls_action_count(selected_player)) {
                selected_row = (y-58)/12; capturing = true;
            }
        }
        return true;
    }
    SDL_Scancode key = keyboard ? e->key.keysym.scancode : SDL_SCANCODE_UNKNOWN;
    int button = gamepad ? e->cbutton.button : -1;
    /* Capture a keyboard binding before invoking its old system action. */
    if (menu == 2 && capturing && !bind_gamepad && keyboard && key != SDL_SCANCODE_ESCAPE &&
        key != SDL_SCANCODE_H && !(key >= SDL_SCANCODE_F2 && key <= SDL_SCANCODE_F12)) {
        bool ok = controls_bind(selected_player, selected_row, false, (int)key);
        snprintf(menu_status, sizeof(menu_status), "%s", ok ? controls_text("Binding saved", "Commande memorisee") :
            controls_text("Reserved key or config unavailable", "Touche reservee ou config inaccessible"));
        if (ok) capturing = false;
        return true;
    }
    /* Start and Select can be captured without invoking their old action. */
    if (menu == 2 && capturing && bind_gamepad && gamepad) {
        if (event_player != selected_player) return true;
        bool ok = controls_bind(selected_player, selected_row, true, button);
        snprintf(menu_status, sizeof(menu_status), "%s", ok ? controls_text("Binding saved", "Commande memorisee") :
            controls_text("Button already used or config unavailable", "Bouton utilise ou config inaccessible"));
        if (ok) capturing = false;
        return true;
    }
    /* Reserved system actions remain available with every binding set. */
    if (key == SDL_SCANCODE_F1 || controls_system_key(key, CONTROL_RESET) || controls_system_button(event_player, button, CONTROL_RESET)) {
        if (gamepad) {
            if (back_latched[event_player]) return true;
            back_latched[event_player] = true; /* Holding the configured button does not reset again. */
        }
        fprintf(stderr, "[host] reset requested at frame %llu\n", (unsigned long long)glue_frame_count());
        reset_requested = true; return false;
    }
    bool enter = key == SDL_SCANCODE_RETURN || key == SDL_SCANCODE_KP_ENTER;
    if (((menu != 2 || !enter) && (key == SDL_SCANCODE_P || enter || controls_system_key(key, CONTROL_PAUSE))) ||
        controls_system_button(event_player, button, CONTROL_PAUSE)) {
        menu = menu == 3 ? 0 : 3; parent_menu = 0; capturing = false; return true;
    }
    if (key == SDL_SCANCODE_ESCAPE) {
        if (capturing) capturing = false;
        else if (menu) { menu = parent_menu; parent_menu = 0; }
        else return false;
        return true;
    }
    if (key == SDL_SCANCODE_H) { toggle_menu(1); return true; }
    if (key == SDL_SCANCODE_F2) { controls_load(); apply_controller_order(); toggle_menu(2); return true; }
    if (key == SDL_SCANCODE_F3) {
        controls_load(); int wanted = (controls.filter + 1) % FILTER_COUNT;
        if (controls_filter(wanted)) notice(controls_filter_label(wanted));
        else notice(controls_text("Cannot write datas/Retro-Recomp.ini", "Impossible d'ecrire datas/Retro-Recomp.ini"));
        return true;
    }
    if (key == SDL_SCANCODE_F4) { toggle_fullscreen(); return true; }
    if (lightphaser_enabled() && (key == SDL_SCANCODE_F5 || (menu == 2 && !capturing && key == SDL_SCANCODE_G))) {
        controls_load(); toggle_menu(4); return true;
    }
    if (key == SDL_SCANCODE_F6) {
        if (controls_autofire(!controls.autofire))
            notice(controls.autofire ? controls_text("Gamepad autofire ON - hold buttons 1/2", "Autofire manette ON - maintenir 1/2") :
                controls_text("Gamepad autofire OFF", "Autofire manette OFF"));
        else notice(controls_text("Config unavailable", "Config inaccessible"));
        return true;
    }
    if (key == SDL_SCANCODE_F7) {
        if (controls_language(!controls.language)) {
            previous_interpreter_state = -1;
            notice(controls_text("Language: English", "Langue : francais"));
        }
        return true;
    }
    if (key == SDL_SCANCODE_F8 || key == SDL_SCANCODE_F9) {
        if (smsrecomp_request_state(key == SDL_SCANCODE_F8 ? RR_QUICKSAVE : RR_QUICKLOAD)) {
            menu = parent_menu = 0; capturing = false;
        } else notice(controls_text("Game states need the native banked backend", "Etats : moteur natif par banques requis"));
        return true;
    }
    if (menu == 4) {
        if (key == SDL_SCANCODE_UP || button == SDL_CONTROLLER_BUTTON_DPAD_UP)
            gun_option_row = (gun_option_row + 2) % 3;
        if (key == SDL_SCANCODE_DOWN || button == SDL_CONTROLLER_BUTTON_DPAD_DOWN)
            gun_option_row = (gun_option_row + 1) % 3;
        int change = key == SDL_SCANCODE_LEFT || key == SDL_SCANCODE_MINUS || button == SDL_CONTROLLER_BUTTON_DPAD_LEFT ? -1 :
            key == SDL_SCANCODE_RIGHT || key == SDL_SCANCODE_EQUALS || button == SDL_CONTROLLER_BUTTON_DPAD_RIGHT ? 1 : 0;
        if (change) change_gun_option(change);
        return true;
    }
    if (menu != 2) return true;
    if (!capturing && (key == SDL_SCANCODE_LEFT || key == SDL_SCANCODE_RIGHT ||
        button == SDL_CONTROLLER_BUTTON_LEFTSHOULDER || button == SDL_CONTROLLER_BUTTON_RIGHTSHOULDER)) {
#ifndef RETRO_GAME_GEAR
        selected_player ^= 1; selected_row = SDL_min(selected_row, controls_action_count(selected_player) - 1);
#endif
        menu_status[0] = 0; return true;
    }
#ifndef RETRO_GAME_GEAR
    if (!capturing && bind_gamepad && key == SDL_SCANCODE_C) {
        if (controls_controller_order(controller_order_player ^ 1)) {
            apply_controller_order(); snprintf(menu_status, sizeof(menu_status), "%s", controls_text("P1/P2 controllers swapped", "Manettes J1/J2 inversees"));
        } else snprintf(menu_status, sizeof(menu_status), "%s", controls_text("Config unavailable", "Config inaccessible"));
        return true;
    }
#endif
    if (gamepad && event_player != selected_player) return true;
    if (capturing) {
        if ((bind_gamepad && !gamepad) || (!bind_gamepad && !keyboard)) return true;
        bool ok = controls_bind(selected_player, selected_row, bind_gamepad, bind_gamepad ? button : (int)key);
        snprintf(menu_status, sizeof(menu_status), "%s", ok ? controls_text("Binding saved", "Commande memorisee") :
            controls_text("Reserved button or config unavailable", "Commande reservee ou config inaccessible"));
        if (ok) capturing = false;
    } else if (key == SDL_SCANCODE_TAB) {
        bind_gamepad = !bind_gamepad; menu_status[0] = 0;
    }
    else if (key == SDL_SCANCODE_UP || button == SDL_CONTROLLER_BUTTON_DPAD_UP)
        selected_row = (selected_row + controls_action_count(selected_player) - 1) % controls_action_count(selected_player);
    else if (key == SDL_SCANCODE_DOWN || button == SDL_CONTROLLER_BUTTON_DPAD_DOWN)
        selected_row = (selected_row + 1) % controls_action_count(selected_player);
    else if (enter || button == SDL_CONTROLLER_BUTTON_A) { capturing = true; menu_status[0] = 0; }
    else if (key == SDL_SCANCODE_D) {
        snprintf(menu_status, sizeof(menu_status), "%s", controls_defaults(selected_player, bind_gamepad) ?
            controls_text("Default bindings restored", "Commandes par defaut restaurees") : controls_text("Config unavailable", "Config inaccessible"));
    }
    return true;
}

uint8_t host_get_pad1(void) { return pads[0]; }
uint8_t host_get_pad2(void) {
#ifdef RETRO_GAME_GEAR
    return 0;
#else
    return pads[1];
#endif
}

static void sample_controls(void) {
    bool focused = SDL_GetKeyboardFocus() == window;
#ifdef RETRO_GAME_GEAR
    const int active_players = 1;
#else
    const int active_players = CONTROL_PLAYERS;
#endif
    for (int p = 0; p < active_players; ++p) {
        SDL_GameController *controller = controllers[p];
        if (controller && !SDL_GameControllerGetAttached(controller)) controller = NULL;
        pads[p] = controls_read(p, controller, focused);
    }
#ifdef RETRO_GAME_GEAR
    pads[1] = 0;
#endif
    sample_phaser(focused);
    input_sample_counter = SDL_GetPerformanceCounter();
}

void host_refresh_input(void) {
    if (!window || menu) return;
    uint64_t now = SDL_GetPerformanceCounter();
    if (input_sample_counter && now - input_sample_counter < input_poll_period) return;
    /* Main thread only. Refresh both players and keyboard/gamepads together;
     * a busy guest polling its ports cannot force an OS poll per instruction.
     * System actions remain in the frame event loop so reset can unwind safely. */
    SDL_PumpEvents();
    sample_controls();
    glue_set_pad1(pads[0]); glue_set_pad2(pads[1]);
}

bool host_present(const uint32_t *fb, int width, int height) {
    if (!texture) return false;
    uint64_t interpreted = smsrecomp_interpreter_cycles();
    int reference = getenv("SMSRECOMP_REFERENCE") != NULL;
    int active = smsrecomp_interpreter_active() || interpreted != previous_interpreter_cycles;
    int state = reference ? 3 : (active ? 1 : (interpreted ? 2 : 0));
    if (state != previous_interpreter_state) {
        char title[320];
        snprintf(title, sizeof(title), "%s | %s", sms_game_title,
            reference ? controls_text("Reference interpreter", "Interpreteur de reference") :
                (active ? controls_text("Fallback interpreter ACTIVE", "Interpreteur de secours ACTIF") :
                (interpreted ? controls_text("Native code | fallback used earlier", "Code natif | secours deja utilise") : controls_text("Native code", "Code natif"))));
        SDL_SetWindowTitle(window, title); previous_interpreter_state = state;
    }
    previous_interpreter_cycles = interpreted;
    draw_game(fb, width, height);
    if (SDL_GetTicks64() < toast_until) ui_toast(renderer, toast);
    SDL_RenderPresent(renderer);
    pace(); /* Sample controls after pacing, just before computing the next frame. */
    bool keep = true;
    SDL_Event e;
    while (SDL_PollEvent(&e)) if (!handle_event(&e)) { keep = false; break; }
    if (menu && keep) {
        if (sms_light_phaser) {
            lightphaser_pointer(-1, -1, false); gun_x = gun_y = -1;
            gun_trigger_blocked = true; SDL_ShowCursor(SDL_ENABLE);
        }
        clear_audio(); if (audio_device) SDL_PauseAudioDevice(audio_device, 1);
        while (menu && keep) {
            draw_game(fb, width, height);
            ui_menu(renderer, menu, selected_player, menu == 4 ? gun_option_row : selected_row, bind_gamepad, capturing,
                controllers[selected_player] ? SDL_GameControllerName(controllers[selected_player]) : NULL, menu_status);
            SDL_RenderPresent(renderer);
            if (SDL_WaitEventTimeout(&e, 16)) keep = handle_event(&e);
        }
        clear_audio(); if (audio_device) SDL_PauseAudioDevice(audio_device, 0);
        deadline = 0;
    }
    sample_controls();
    for (int p = 0; p < CONTROL_PLAYERS; ++p) {
        int reset_button = controls.buttons[p][CONTROL_RESET];
        if (keep && (reset_button < 0 || !controllers[p] || !SDL_GameControllerGetButton(controllers[p], reset_button))) back_latched[p] = false;
    }
    return keep;
}

bool host_audio_init(uint32_t rate) {
    if (SDL_InitSubSystem(SDL_INIT_AUDIO) != 0) return false;
    SDL_AudioSpec want, have; SDL_zero(want);
    want.freq = 48000; want.format = AUDIO_S16SYS; want.channels = 2; want.samples = 512;
    audio_device = SDL_OpenAudioDevice(NULL, 0, &want, &have, SDL_AUDIO_ALLOW_FREQUENCY_CHANGE);
    if (!audio_device) return false;
    audio_stream = SDL_NewAudioStream(AUDIO_S16SYS, 2, (int)rate, have.format, have.channels, have.freq);
    if (!audio_stream) { SDL_CloseAudioDevice(audio_device); audio_device = 0; return false; }
    SDL_PauseAudioDevice(audio_device, 0);
    fprintf(stderr, "[host] audio %d Hz, %u samples; latency is unmeasured\n", have.freq, have.samples);
    return true;
}

void host_audio_submit(const int16_t *samples, size_t count) {
    if (!audio_stream || !audio_device) return;
    SDL_AudioStreamPut(audio_stream, samples, (int)(count * 2 * sizeof(int16_t)));
    uint8_t buffer[8192]; int available;
    while ((available = SDL_AudioStreamAvailable(audio_stream)) > 0) {
        int size = available < (int)sizeof(buffer) ? available : (int)sizeof(buffer);
        int got = SDL_AudioStreamGet(audio_stream, buffer, size);
        if (got <= 0) break;
        SDL_QueueAudio(audio_device, buffer, (uint32_t)got);
    }
}

void host_audio_shutdown(void) {
    if (audio_stream) SDL_FreeAudioStream(audio_stream);
    if (audio_device) SDL_CloseAudioDevice(audio_device);
    audio_stream = NULL; audio_device = 0;
}

void host_shutdown(void) {
    if (sms_light_phaser) { lightphaser_pointer(-1, -1, false); SDL_ShowCursor(SDL_ENABLE); }
    smsrecomp_set_input_refresh(NULL);
    smsrecomp_set_state_callback(NULL);
    input_sample_counter = 0;
    if (window && !fullscreen) {
        SDL_GetWindowPosition(window, &saved_window.x, &saved_window.y);
        SDL_GetWindowSize(window, &saved_window.w, &saved_window.h);
    }
    for (int p = 0; p < CONTROL_PLAYERS; ++p) {
        if (controllers[p]) SDL_GameControllerClose(controllers[p]);
        controllers[p] = NULL; pads[p] = 0;
    }
    ui_shutdown();
    if (texture_cropped2x) SDL_DestroyTexture(texture_cropped2x);
    if (texture_cropped) SDL_DestroyTexture(texture_cropped);
    if (texture2x) SDL_DestroyTexture(texture2x);
    if (texture) SDL_DestroyTexture(texture);
    if (renderer) SDL_DestroyRenderer(renderer);
    if (window) SDL_DestroyWindow(window);
    texture = texture2x = texture_cropped = texture_cropped2x = NULL; renderer = NULL; window = NULL;
    SDL_Quit();
}
