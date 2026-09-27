/* Diagnostic target only: synthetic SDL events + two virtual Xbox-style pads,
 * pixel inspection and a reset through the actual generated Alex Kidd code.
 * NDEBUG must not disable checks in this Release target. */
#undef NDEBUG
#include <assert.h>
#include "controls.c"
#include "ui.c"
/* The dummy video driver cannot focus a window. Supply only that OS result;
 * controller sampling, events, presentation and the production bridge run. */
static SDL_Window *test_focus;
static SDL_bool test_game_controller(int index) {
    return SDL_JoystickIsVirtual(index) ? SDL_IsGameController(index) : SDL_FALSE;
}
#define SDL_GetKeyboardFocus() test_focus
#define SDL_IsGameController test_game_controller
#include "host.c"
#undef SDL_GetKeyboardFocus
#undef SDL_IsGameController
#define main smsrecomp_test_backend_main
#include "runtime_main.c"
#undef main
#include "include/sms_runtime.h"
#include "video/sms_vdp.h"
#include "audio/sn76489.h"

static uint32_t sample[256*192];
static uint64_t pcm_hash;
static int reset_kind, pause_kind;
static uint64_t pause_elapsed;
static void screenshot(const char *name);

static SDL_Event key_event(SDL_Scancode code) {
    SDL_Event event; SDL_zero(event); event.type = SDL_KEYDOWN;
    event.key.keysym.scancode = code; event.key.keysym.sym = SDL_GetKeyFromScancode(code);
    return event;
}
static SDL_Event button_event(int player, int button) {
    SDL_Event event; SDL_zero(event); event.type = SDL_CONTROLLERBUTTONDOWN;
    event.cbutton.button = (uint8_t)button;
    if (controllers[player]) event.cbutton.which = SDL_JoystickInstanceID(SDL_GameControllerGetJoystick(controllers[player]));
    return event;
}
static void key(SDL_Scancode code) { SDL_Event event = key_event(code); assert(handle_event(&event)); }

static uint64_t hash_bytes(uint64_t h, const void *data, size_t n) {
    const uint8_t *p = data;
    for (size_t i = 0; i < n; ++i) { h ^= p[i]; h *= 1099511628211ULL; }
    return h;
}
static void sink(const int16_t *samples, size_t frames) {
    pcm_hash = hash_bytes(pcm_hash, samples, frames * 4);
}
static uint8_t scripted_pad(uint64_t frame) {
    if (frame >= 120 && frame < 125) return SMS_PAD_B2;
    if (frame >= 240 && frame < 360) return SMS_PAD_RIGHT;
    if (frame >= 360 && frame < 390) return SMS_PAD_RIGHT | SMS_PAD_B1;
    return 0;
}
static SDL_Event pause_event(int kind) {
    if (kind == 4) return key_event(SDL_SCANCODE_KP_7);
    if (kind == 5) return key_event(SDL_SCANCODE_RETURN);
    if (kind == 6) return key_event(SDL_SCANCODE_KP_ENTER);
    return kind == 1 ? key_event(SDL_SCANCODE_P) : button_event(kind - 2, SDL_CONTROLLER_BUTTON_START);
}
static uint32_t resume_timer(uint32_t interval, void *kind) {
    (void)interval;
    SDL_Event event = pause_event((int)(uintptr_t)kind);
    SDL_PushEvent(&event); return 0;
}
static int game_callback(const uint32_t *fb, int w, int h) {
    if (glue_frame_count() == 600 && !reset_kind && !pause_kind) {
        draw_game(fb, w, h);
        screenshot("game-auto-border.bmp");
        assert(crop.w == 256 - smsrecomp_frame_left_border());
        int ww, wh; SDL_GetWindowSize(window, &ww, &wh);
        assert(ww == 768 && wh == 576);
    }
    if (reset_kind && glue_frame_count() == 180) {
        SDL_FlushEvents(SDL_FIRSTEVENT, SDL_LASTEVENT);
        SDL_Event e = reset_kind == 1 ? key_event(SDL_SCANCODE_F1) : button_event(0, SDL_CONTROLLER_BUTTON_BACK);
        assert(SDL_PushEvent(&e) == 1);
        assert(!host_present(fb, w, h)); return 1;
    }
    if (pause_kind && glue_frame_count() == 150) {
        /* Delay release so the actual wait loop must run, with no extra CPU
         * frames. No pacing or interpretation is needed to suspend execution. */
        SDL_FlushEvents(SDL_FIRSTEVENT, SDL_LASTEVENT);
        SDL_Event e = pause_event(pause_kind);
        SDL_PushEvent(&e);
        assert(SDL_AddTimer(100, resume_timer, (void*)(uintptr_t)pause_kind));
        uint64_t start = SDL_GetTicks64();
        assert(host_present(fb, w, h));
        pause_elapsed = SDL_GetTicks64() - start;
        assert(pause_elapsed >= 70 && glue_frame_count() == 150);
    }
    return 0;
}
static uint64_t run_game(int reset, int pause) {
    reset_kind = reset; pause_kind = pause;
    pcm_hash = 1469598103934665603ULL;
    assert(glue_load_rom("embedded.sms")); glue_init(false, 600);
    glue_set_input_cb(scripted_pad); glue_set_audio_sink(sink);
    glue_set_frame_callback(game_callback); glue_run();
    if (reset) {
        assert(glue_frame_count() == 180 && smsrecomp_take_reset_request());
        assert(!smsrecomp_take_reset_request());
    } else assert(glue_frame_count() == 600 && smsrecomp_interpreter_cycles() == 0);
    uint64_t h = hash_bytes(pcm_hash, &g_z80, sizeof(g_z80));
    h = hash_bytes(h, &g_vdp, sizeof(g_vdp));
    for (int addr = 0xC000; addr < 0xE000; ++addr) { uint8_t value = sms_read8((uint16_t)addr); h = hash_bytes(h, &value, 1); }
    return h;
}

static void screenshot(const char *name) {
    int w, h; SDL_GetRendererOutputSize(renderer, &w, &h);
    SDL_Surface *surface = SDL_CreateRGBSurfaceWithFormat(0, w, h, 32, SDL_PIXELFORMAT_ARGB8888);
    assert(surface && SDL_RenderReadPixels(renderer, NULL, surface->format->format, surface->pixels, surface->pitch) == 0);
    assert(SDL_SaveBMP(surface, name) == 0); SDL_FreeSurface(surface);
}
static uint32_t pixel(int x, int y) {
    SDL_Rect rect = {x, y, 1, 1}; uint32_t color;
    assert(SDL_RenderReadPixels(renderer, &rect, SDL_PIXELFORMAT_ARGB8888, &color, 4) == 0);
    return color & 0xFFFFFF;
}

static void check_vdp_blank_column(void) {
    SmsVdp saved = g_vdp;
    vdp_reset(false);
    g_vdp.reg[0] = 0x26; g_vdp.reg[1] = 0x40;
    g_vdp.reg[2] = 0x0E; g_vdp.reg[5] = 0x7E;
    g_vdp.cram[1] = 0x03; g_vdp.cram[16] = 0x30;
    g_vdp.cram[18] = 0x0C; g_vdp.cram[19] = 0x3F;
    for (int row = 0; row < 8; ++row) {
        g_vdp.vram[32 + row*4] = 0xFF;  /* red background tile */
        g_vdp.vram[64 + row*4 + 1] = 0xFF; /* green sprite tile */
    }
    for (int entry = 0; entry < 32*28; ++entry) g_vdp.vram[0x3800 + entry*2] = 1;
    g_vdp.vram[0x3F00] = 9; g_vdp.vram[0x3F01] = 0xD0;
    g_vdp.vram[0x3F80] = 4; g_vdp.vram[0x3F81] = 2;
    vdp_render_frame(sample);
    assert(smsrecomp_frame_left_border() == 8);
    for (int y = 0; y < 192; ++y) for (int x = 0; x < 8; ++x)
        assert(sample[y*256+x] == 0xFF0000FF); /* includes sprite-covered pixels */
    assert(sample[10*256+8] == 0xFF00FF00 && sample[10*256+12] == 0xFFFF0000);
    g_vdp.reg[7] = 3; vdp_render_frame(sample);
    assert(sample[10*256+4] == 0xFFFFFFFF); /* backdrop color is not hard-coded black */
    g_vdp.reg[0] = 0x06; vdp_render_frame(sample);
    assert(smsrecomp_frame_left_border() == 0);
    assert(sample[10*256+4] == 0xFF00FF00 && sample[0] == 0xFFFF0000);
    g_vdp.reg[0] = 0x20; vdp_render_frame(sample);
    assert(smsrecomp_frame_left_border() == 0 && sample[0] == 0xFFFF0000); /* not mode 4 */
    g_vdp.reg[0] = 0x26; g_vdp.is_gg = true; vdp_render_frame(sample);
    assert(smsrecomp_frame_left_border() == 0); /* GG keeps its own viewport */
    g_vdp.is_gg = false; g_vdp.reg[0] = 0x06;
    g_vdp.reg[1] = 0; vdp_render_frame(sample);
    for (int i = 0; i < 256*192; ++i) assert(sample[i] == 0xFFFFFFFF);
    g_vdp = saved;
    vdp_render_frame(sample);
    puts("PASS: VDP left blanking covers sprites and follows the backdrop palette.");
}

int main(int argc, char **argv) {
    assert(argc == 2);
    SDL_SetHint(SDL_HINT_JOYSTICK_ALLOW_BACKGROUND_EVENTS, "1");
    MultiByteToWideChar(CP_UTF8, 0, argv[1], -1, config_path, 32768);
    /* Simulate a customized one-player configuration from 0.7. */
    FILE *old = _wfopen(config_path, L"wb"); assert(old);
    fputs("[Clavier]\r\nbouton1=C\r\n[Manette]\r\nbouton1=x\r\n[Video]\r\nfiltre=3\r\nmasquer_bord_gauche=0\r\n"
        "[ClavierJ2]\r\nhaut=I\r\nbas=K\r\ngauche=J\r\ndroite=L\r\nbouton1=N\r\nbouton2=M\r\nselect=Keypad 4\r\n"
        "[ManetteJ2]\r\nselect=back\r\n", old); fclose(old);
    assert(host_init(256, 192, 0, 0, 256, 192, 3, "test")); host_set_frame_cap(0);
    assert(controls.keys[0][4] == SDL_SCANCODE_C && controls.buttons[0][4] == SDL_CONTROLLER_BUTTON_X);
    assert(controls.keys[1][4] == SDL_SCANCODE_KP_8 && controls.buttons[1][4] == SDL_CONTROLLER_BUTTON_A);
    assert(controls.keys[1][CONTROL_PAUSE] == SDL_SCANCODE_KP_7 && controls.keys[1][CONTROL_RESET] == SDL_SCANCODE_UNKNOWN);
    assert(controls.buttons[1][CONTROL_RESET] == SDL_CONTROLLER_BUTTON_INVALID);
    char disabled[128];
    read_name(L"ClavierJ2", L"select", disabled, sizeof(disabled)); assert(!disabled[0]);
    read_name(L"ManetteJ2", L"select", disabled, sizeof(disabled)); assert(!disabled[0]);
    assert(controls.language == 0);
    char old_border[128]; read_name(L"Video", L"masquer_bord_gauche", old_border, sizeof(old_border)); assert(!old_border[0]);
    assert(controls.filter == FILTER_SCANLINES);
    char migrated[128]; read_name(L"ClavierJ2", L"bouton2", migrated, sizeof(migrated)); assert(!strcmp(migrated, "Keypad 9"));
    for (int p = 0; p < CONTROL_PLAYERS; ++p) assert(controls_defaults(p, false) && controls_defaults(p, true));
    assert(controls_filter(0));
    SDL_VirtualJoystickDesc desc; SDL_zero(desc);
    desc.version = SDL_VIRTUAL_JOYSTICK_DESC_VERSION; desc.type = SDL_JOYSTICK_TYPE_GAMECONTROLLER;
    desc.naxes = SDL_CONTROLLER_AXIS_MAX; desc.nbuttons = SDL_CONTROLLER_BUTTON_MAX;
    desc.button_mask = (1u << SDL_CONTROLLER_BUTTON_MAX) - 1;
    desc.axis_mask = (1u << SDL_CONTROLLER_AXIS_MAX) - 1;
    desc.name = "Retro-Recomp virtual Xbox J1";
    int device = SDL_JoystickAttachVirtualEx(&desc); assert(device >= 0);
    desc.name = "Retro-Recomp virtual Xbox J2";
    int device2 = SDL_JoystickAttachVirtualEx(&desc); assert(device2 >= 0);
    open_controllers(); assert(controllers[0] && controllers[1] && controllers[0] != controllers[1]);
    SDL_Joystick *joystick = SDL_GameControllerGetJoystick(controllers[0]);
    SDL_Joystick *joystick2 = SDL_GameControllerGetJoystick(controllers[1]);
    SDL_JoystickID id2 = SDL_JoystickInstanceID(joystick2);
    key(SDL_SCANCODE_F2);
    for (int i = 0; i < 4; ++i) key(SDL_SCANCODE_DOWN);
    key(SDL_SCANCODE_RETURN); key(SDL_SCANCODE_C);
    assert(!capturing && controls.keys[0][4] == SDL_SCANCODE_C && controls.keys[1][4] == SDL_SCANCODE_KP_8);
    controls_load(); assert(controls.keys[0][4] == SDL_SCANCODE_C);
    key(SDL_SCANCODE_RETURN); key(SDL_SCANCODE_ESCAPE);
    assert(!capturing && controls.keys[0][4] == SDL_SCANCODE_C);
    key(SDL_SCANCODE_TAB); key(SDL_SCANCODE_RETURN);
    SDL_Event event = button_event(0, SDL_CONTROLLER_BUTTON_X); assert(handle_event(&event));
    controls_load(); assert(controls.buttons[0][4] == SDL_CONTROLLER_BUTTON_X);
    key(SDL_SCANCODE_RIGHT); assert(selected_player == 1);
    key(SDL_SCANCODE_RETURN);
    event = button_event(0, SDL_CONTROLLER_BUTTON_Y); assert(handle_event(&event));
    assert(capturing && controls.buttons[1][4] == SDL_CONTROLLER_BUTTON_A);
    event = button_event(1, SDL_CONTROLLER_BUTTON_Y); assert(handle_event(&event));
    assert(!capturing && controls.buttons[1][4] == SDL_CONTROLLER_BUTTON_Y);
    key(SDL_SCANCODE_TAB); key(SDL_SCANCODE_RETURN); key(SDL_SCANCODE_V);
    controls_load();
    assert(controls.keys[1][4] == SDL_SCANCODE_V && controls.keys[0][4] == SDL_SCANCODE_C);
    assert(controls.buttons[1][4] == SDL_CONTROLLER_BUTTON_Y && controls.buttons[0][4] == SDL_CONTROLLER_BUTTON_X);
    key(SDL_SCANCODE_D); assert(controls.keys[1][4] == SDL_SCANCODE_KP_8 && controls.keys[0][4] == SDL_SCANCODE_C);
    key(SDL_SCANCODE_TAB); key(SDL_SCANCODE_C);
    assert(controller_player(id2) == 0 && controls.first_controller_player == 1);
    controls_load(); assert(controls.first_controller_player == 1);
    key(SDL_SCANCODE_C); assert(controller_player(id2) == 1 && controls.first_controller_player == 0);
    for (int p = 0; p < CONTROL_PLAYERS; ++p)
        assert(!controls_bind(p, 4, true, SDL_CONTROLLER_BUTTON_START) && !controls_bind(p, 4, false, SDL_SCANCODE_P));
    assert(!controls_bind(1, 4, false, SDL_SCANCODE_KP_7));
    assert(controls_bind(1, 4, false, SDL_SCANCODE_KP_4)); /* former reset key is now free */
    assert(controls_defaults(1, false));
    assert(!controls_bind(1, CONTROL_RESET, false, SDL_SCANCODE_KP_4));
    assert(!controls_bind(1, CONTROL_RESET, true, SDL_CONTROLLER_BUTTON_BACK));
    assert(controls_bind(1, CONTROL_PAUSE, false, SDL_SCANCODE_KP_6));
    controls_load(); assert(controls.keys[1][CONTROL_PAUSE] == SDL_SCANCODE_KP_6 && controls.keys[1][4] == SDL_SCANCODE_KP_8);
    assert(controls_defaults(1, false));
    assert(!controls_bind(-1, 4, false, SDL_SCANCODE_C) && !controls_defaults(2, false));
    key(SDL_SCANCODE_ESCAPE); assert(menu == 0);
    for (int p = 0; p < CONTROL_PLAYERS; ++p) assert(controls_defaults(p, false) && controls_defaults(p, true));

    /* Exercise both added controller rows through the real menu. Capture
     * precedes old system actions, and ignores the other player's controller. */
    key(SDL_SCANCODE_F2); selected_player = selected_row = 0; bind_gamepad = true;
    key(SDL_SCANCODE_UP); assert(selected_row == CONTROL_RESET);
    key(SDL_SCANCODE_RETURN); assert(capturing && menu == 2);
    event = button_event(1, SDL_CONTROLLER_BUTTON_BACK); assert(handle_event(&event) && capturing);
    event = button_event(0, SDL_CONTROLLER_BUTTON_RIGHTSHOULDER); assert(handle_event(&event) && !capturing);
    key(SDL_SCANCODE_UP); assert(selected_row == CONTROL_PAUSE);
    key(SDL_SCANCODE_KP_ENTER); assert(capturing && menu == 2);
    event = button_event(0, SDL_CONTROLLER_BUTTON_LEFTSHOULDER); assert(handle_event(&event) && !capturing);
    controls_load();
    assert(controls.buttons[0][CONTROL_PAUSE] == SDL_CONTROLLER_BUTTON_LEFTSHOULDER);
    assert(controls.buttons[0][CONTROL_RESET] == SDL_CONTROLLER_BUTTON_RIGHTSHOULDER);
    assert(controls_bind(0, 4, true, SDL_CONTROLLER_BUTTON_START)); /* freed button is playable */
    key(SDL_SCANCODE_ESCAPE); assert(!menu);
    event = button_event(0, SDL_CONTROLLER_BUTTON_START); assert(handle_event(&event) && !menu);
    event = button_event(0, SDL_CONTROLLER_BUTTON_BACK); assert(handle_event(&event) && !smsrecomp_take_reset_request());
    event = button_event(1, SDL_CONTROLLER_BUTTON_BACK); assert(handle_event(&event) && !smsrecomp_take_reset_request());
    key(SDL_SCANCODE_KP_4); assert(!menu && !smsrecomp_take_reset_request());
    event = button_event(0, SDL_CONTROLLER_BUTTON_LEFTSHOULDER); assert(handle_event(&event) && menu == 3);
    assert(handle_event(&event) && !menu);
    event = button_event(0, SDL_CONTROLLER_BUTTON_RIGHTSHOULDER); assert(!handle_event(&event) && smsrecomp_take_reset_request());
    assert(handle_event(&event) && !smsrecomp_take_reset_request()); /* held custom reset */
    event.type = SDL_CONTROLLERBUTTONUP; assert(handle_event(&event));
    event.type = SDL_CONTROLLERBUTTONDOWN; assert(!handle_event(&event) && smsrecomp_take_reset_request());
    event.type = SDL_CONTROLLERBUTTONUP; assert(handle_event(&event));
    key(SDL_SCANCODE_F2); key(SDL_SCANCODE_DOWN); assert(selected_row == CONTROL_RESET);
    key(SDL_SCANCODE_RIGHT); assert(selected_player == 1 && selected_row == CONTROL_PAUSE);
    key(SDL_SCANCODE_DOWN); assert(selected_row == 0);
    key(SDL_SCANCODE_UP); assert(selected_row == CONTROL_PAUSE);
    key(SDL_SCANCODE_RETURN);
    event = button_event(1, SDL_CONTROLLER_BUTTON_BACK); assert(handle_event(&event) && !capturing && menu == 2);
    controls_load(); assert(controls.buttons[1][CONTROL_PAUSE] == SDL_CONTROLLER_BUTTON_BACK);
    key(SDL_SCANCODE_ESCAPE);
    assert(handle_event(&event) && menu == 3 && !smsrecomp_take_reset_request());
    assert(handle_event(&event) && !menu);
    for (int p = 0; p < CONTROL_PLAYERS; ++p) assert(controls_defaults(p, true));
    controls_load();
    assert(controls.buttons[0][CONTROL_PAUSE] == SDL_CONTROLLER_BUTTON_START && controls.buttons[0][CONTROL_RESET] == SDL_CONTROLLER_BUTTON_BACK);
    assert(controls.buttons[1][CONTROL_PAUSE] == SDL_CONTROLLER_BUTTON_START && controls.buttons[1][CONTROL_RESET] == SDL_CONTROLLER_BUTTON_INVALID);
    /* Even a hand-edited legacy J2 reset cannot regain a host reset action. */
    assert(write_name(L"ClavierJ2", L"select", "Keypad 4") && write_name(L"ManetteJ2", L"select", "back"));
    controls_load();
    event = button_event(1, SDL_CONTROLLER_BUTTON_BACK); assert(handle_event(&event) && !smsrecomp_take_reset_request());
    key(SDL_SCANCODE_KP_4); assert(!smsrecomp_take_reset_request());
    assert(!controls_bind(0, 4, false, SDL_SCANCODE_RETURN) && !controls_bind(1, 4, false, SDL_SCANCODE_KP_ENTER));
    puts("PASS: configurable Start/Menu and Select/Reset, capture and persistence, Enter validation; no J2 reset.");

    assert(SDL_JoystickSetVirtualButton(joystick, SDL_CONTROLLER_BUTTON_A, 1) == 0);
    SDL_GameControllerUpdate(); assert(controls_read(0, controllers[0], true) == SMS_PAD_B1);
    SDL_JoystickSetVirtualButton(joystick, SDL_CONTROLLER_BUTTON_A, 0);
    SDL_JoystickSetVirtualButton(joystick, SDL_CONTROLLER_BUTTON_B, 1);
    SDL_GameControllerUpdate(); assert(controls_read(0, controllers[0], true) == SMS_PAD_B2);
    SDL_JoystickSetVirtualButton(joystick, SDL_CONTROLLER_BUTTON_B, 0);
    SDL_JoystickSetVirtualButton(joystick, SDL_CONTROLLER_BUTTON_DPAD_LEFT, 1);
    SDL_JoystickSetVirtualAxis(joystick, SDL_CONTROLLER_AXIS_LEFTY, -20000);
    SDL_JoystickSetVirtualButton(joystick2, SDL_CONTROLLER_BUTTON_B, 1);
    SDL_JoystickSetVirtualAxis(joystick2, SDL_CONTROLLER_AXIS_LEFTX, 20000);
    SDL_GameControllerUpdate(); assert(controls_read(0, controllers[0], true) == (SMS_PAD_LEFT | SMS_PAD_UP));
    assert(controls_read(1, controllers[1], true) == (SMS_PAD_RIGHT | SMS_PAD_B2));
    assert(controls_read(0, controllers[0], false) == 0 && controls_read(1, controllers[1], false) == 0);
    SDL_JoystickSetVirtualButton(joystick, SDL_CONTROLLER_BUTTON_DPAD_LEFT, 0);
    SDL_JoystickSetVirtualAxis(joystick, SDL_CONTROLLER_AXIS_LEFTY, 0);
    SDL_JoystickSetVirtualButton(joystick2, SDL_CONTROLLER_BUTTON_B, 0);
    SDL_JoystickSetVirtualAxis(joystick2, SDL_CONTROLLER_AXIS_LEFTX, 0);
    SDL_GameControllerUpdate();

    /* Every simultaneous six-button state reaches the two SMS ports. Use the
     * same sampler as production, with an explicit keyboard snapshot. */
    assert(glue_load_rom("embedded.sms")); glue_init(false, 600);
    for (int a = 0; a < 64; ++a) for (int b = 0; b < 64; ++b) {
        uint8_t keys[SDL_NUM_SCANCODES] = {0};
        for (int i = 0; i < 6; ++i) {
            keys[controls.keys[0][i]] = (a >> i) & 1;
            keys[controls.keys[1][i]] = (b >> i) & 1;
        }
        pads[0] = read_controls(0, NULL, true, keys); pads[1] = read_controls(1, NULL, true, keys);
        assert(pads[0] == a && pads[1] == b);
        glue_set_pad1(host_get_pad1()); glue_set_pad2(host_get_pad2());
        assert(sms_io_in(0xDC) == (uint8_t)~(a | ((b & 3) << 6)));
        assert(sms_io_in(0xDD) == (uint8_t)~(b >> 2));
        assert(sms_io_in(0xC0) == sms_io_in(0xDC) && sms_io_in(0xFF) == sms_io_in(0xDD));
    }
    memset(pads, 0, sizeof(pads));
    uint8_t system_keys[SDL_NUM_SCANCODES] = {0};
    system_keys[SDL_SCANCODE_KP_7] = system_keys[SDL_SCANCODE_KP_4] = 1;
    assert(read_controls(1, NULL, true, system_keys) == 0);
    key(SDL_SCANCODE_F6); assert(controls.language == 1);
    controls_load(); assert(controls.language == 1);
    key(SDL_SCANCODE_F6); assert(controls.language == 0);

    SDL_FlushEvents(SDL_FIRSTEVENT, SDL_LASTEVENT);
    SDL_JoystickSetVirtualButton(joystick, SDL_CONTROLLER_BUTTON_A, 1);
    SDL_JoystickSetVirtualButton(joystick2, SDL_CONTROLLER_BUTTON_B, 1);
    SDL_GameControllerUpdate();
    test_focus = window;
    assert(sdl_frame_cb(sample, 256, 192) == 0);
    assert(host_get_pad1() == SMS_PAD_B1 && host_get_pad2() == SMS_PAD_B2);
    assert(sms_io_in(0xDC) == 0xEF && sms_io_in(0xDD) == 0xF7);
    test_focus = NULL;
    assert(sdl_frame_cb(sample, 256, 192) == 0);
    assert(host_get_pad1() == 0 && host_get_pad2() == 0);
    assert(sms_io_in(0xDC) == 0xFF && sms_io_in(0xDD) == 0xFF);
    SDL_JoystickSetVirtualButton(joystick, SDL_CONTROLLER_BUTTON_A, 0);
    SDL_JoystickSetVirtualButton(joystick2, SDL_CONTROLLER_BUTTON_B, 0);
    SDL_GameControllerUpdate();

    for (int y = 0; y < 192; ++y) for (int x = 0; x < 256; ++x)
        sample[y*256+x] = 0xFF000000 | ((x/16)%2 ? 0x2458A0 : 0xFFFFFF);
    int k; SDL_Rect r = game_rect(1920, 1080, &k);
    assert(k == 5 && r.w == 1280 && r.h == 960 && r.x == 320 && r.y == 60);
    draw_game(sample, 256, 192); assert(pixel(0, 0) == 0xFFFFFF && pixel(2, 2) == 0xFFFFFF);
    screenshot("pixels-nets.bmp");
    assert(controls_filter(FILTER_LINEAR)); draw_game(sample, 256, 192); screenshot("bilineaire.bmp");
    assert(pixel(47, 0) != 0xFFFFFF && pixel(47, 0) != 0x2458A0);
    assert(controls_filter(FILTER_SCANLINES)); draw_game(sample, 256, 192);
    assert(pixel(0, 0) == 0xFFFFFF && pixel(0, 2) < 0xFFFFFF); screenshot("scanlines.bmp");
    assert(controls_filter(FILTER_SCALE2X)); r = game_rect(1920, 1080, &k);
    assert(k == 4 && r.w == 1024 && r.h == 768); draw_game(sample, 256, 192); screenshot("scale2x.bmp");
    uint64_t start = SDL_GetPerformanceCounter();
    for (int i = 0; i < 1000; ++i) scale2x(sample, 256, 192, 256, enlarged);
    printf("Scale2x CPU (test pattern): %.4f ms/frame\n", (SDL_GetPerformanceCounter()-start)*1000.0 / SDL_GetPerformanceFrequency() / 1000);
    assert(controls_filter(0));
    /* A game-requested blank column is cropped automatically. The window and
     * integer scale stay stable; ordinary black gameplay is retained. */
    SmsVdp before_crop = g_vdp;
    g_vdp.reg[0] = 0x26; vdp_render_frame(sample);
    for (int y = 0; y < 192; ++y) for (int x = 0; x < 256; ++x)
        sample[y*256+x] = x < 8 ? 0xFF000000 : 0xFF345678;
    draw_game(sample, 256, 192);
    int window_w, window_h; SDL_GetWindowSize(window, &window_w, &window_h);
    assert(crop.x == 8 && crop.w == 248 && window_w == 768 && window_h == 576);
    assert(pixel(11, 0) == 0 && pixel(12, 0) == 0x345678 && pixel(755, 575) == 0x345678 && pixel(756, 575) == 0);
    r = game_rect(1920, 1080, &k);
    assert(k == 5 && r.w == 1240 && r.h == 960 && r.x == 340 && r.y == 60);
    assert(sample[0] == 0xFF000000 && g_vdp.reg[0] == 0x26);
    screenshot("border-cropped.bmp");
    /* A previous manual value and F7 no longer change automatic behaviour. */
    assert(write_name(L"Video", L"masquer_bord_gauche", "0"));
    key(SDL_SCANCODE_F7); controls_load();
    toast_until = 0; draw_game(sample, 256, 192);
    assert(crop.x == 8 && crop.w == 248);
    read_name(L"Video", L"masquer_bord_gauche", old_border, sizeof(old_border)); assert(!old_border[0]);
    /* Register writes after rendering must not reinterpret the pending image. */
    g_vdp.reg[0] = 0x06; draw_game(sample, 256, 192); assert(crop.x == 8);
    r = game_rect(500, 400, &k); assert(k == 1 && r.w == 248);
    /* Bilinear filtering must clamp to the visible edge, not sample black
     * masked pixels. Scale2x gets the same cropped boundary. */
    for (int filter = 0; filter < FILTER_COUNT; ++filter) {
        assert(controls_filter(filter)); draw_game(sample, 256, 192);
        r = game_rect(768, 576, &k);
        assert(pixel(r.x, r.y) == 0x345678 && pixel(r.x+r.w-1, r.y) == 0x345678);
    }
    assert(controls_filter(FILTER_SCALE2X));
    sample[8] = 0xFF000000; sample[256+9] = sample[512+8] = 0xFF0000FF;
    draw_game(sample, 256, 192);
    assert(enlarged[2 * 496] == 0xFF345678); /* left neighbour clamps to E */
    assert(controls_filter(FILTER_NEAREST));
    g_vdp.reg[0] = 0x06; vdp_render_frame(sample);
    for (int y = 0; y < 192; ++y) for (int x = 0; x < 256; ++x)
        sample[y*256+x] = x < 8 ? 0xFF000000 : 0xFF345678;
    g_vdp.reg[0] = 0x26; draw_game(sample, 256, 192); /* inverse stale-register case */
    SDL_GetWindowSize(window, &window_w, &window_h);
    assert(crop.x == 0 && crop.w == 256 && window_w == 768 && window_h == 576 && pixel(0, 0) == 0);
    r = game_rect(500, 400, &k); assert(k == 1 && r.w == 256);
    screenshot("border-full.bmp");
    /* Alternate mask and display states, including fullscreen restore. */
    key(SDL_SCANCODE_F4); assert(fullscreen);
    SDL_Rect restore = saved_window;
    for (int i = 0; i < 32; ++i) {
        g_vdp.reg[0] = i & 1 ? 0x26 : 0x06;
        g_vdp.reg[1] = i & 2 ? 0x40 : 0;
        vdp_render_frame(sample); draw_game(sample, 256, 192);
        assert(crop.w == (i & 1 ? 248 : 256));
        assert(memcmp(&restore, &saved_window, sizeof(restore)) == 0);
    }
    key(SDL_SCANCODE_F4); assert(!fullscreen);
    SDL_GetWindowSize(window, &window_w, &window_h); assert(window_w == 768 && window_h == 576);
    SDL_SetWindowSize(window, 500, 400);
    for (int i = 0; i < 32; ++i) {
        g_vdp.reg[0] = i & 1 ? 0x26 : 0x06;
        vdp_render_frame(sample); draw_game(sample, 256, 192);
        SDL_GetWindowSize(window, &window_w, &window_h); assert(window_w == 500 && window_h == 400);
        r = game_rect(window_w, window_h, &k); assert(k == 1);
    }
    SDL_SetWindowSize(window, 768, 576);
    g_vdp.is_gg = true; g_vdp.reg[0] = 0x26; vdp_render_frame(sample); draw_game(sample, 256, 192);
    assert(crop.w == 256); /* no SMS border crop on Game Gear */
    g_vdp = before_crop;
    vdp_render_frame(sample);
    draw_game(sample, 256, 192);
    /* Compare the actual full SDL output with reference status active. */
    SDL_GetRendererOutputSize(renderer, &window_w, &window_h);
    size_t image_bytes = (size_t)window_w * window_h * 4;
    void *image_before = malloc(image_bytes), *image_after = malloc(image_bytes);
    assert(image_before && image_after);
    assert(SDL_RenderReadPixels(renderer, NULL, SDL_PIXELFORMAT_ARGB8888, image_before, window_w*4) == 0);
    toast_until = 0; fullscreen = true; _putenv_s("SMSRECOMP_REFERENCE", "1");
    SDL_FlushEvents(SDL_FIRSTEVENT, SDL_LASTEVENT);
    assert(host_present(sample, 256, 192));
    assert(strstr(SDL_GetWindowTitle(window), "Reference interpreter"));
    assert(SDL_RenderReadPixels(renderer, NULL, SDL_PIXELFORMAT_ARGB8888, image_after, window_w*4) == 0);
    assert(memcmp(image_before, image_after, image_bytes) == 0);
    free(image_before); free(image_after);
    fullscreen = false; _putenv_s("SMSRECOMP_REFERENCE", ""); previous_interpreter_state = -1;
    check_vdp_blank_column();
    puts("PASS: automatic frame-based crop, obsolete setting ignored, stable window/scale, cropped filters and clean fullscreen.");
    for (int i = 0; i < FILTER_COUNT; ++i) key(SDL_SCANCODE_F3);
    assert(controls.filter == FILTER_NEAREST);
    key(SDL_SCANCODE_F4); assert(fullscreen); key(SDL_SCANCODE_F4); assert(!fullscreen);
    draw_game(sample, 256, 192); ui_menu(renderer, 1, 0, 0, false, false, NULL, NULL); screenshot("help.bmp");
    for (int p = 0; p < CONTROL_PLAYERS; ++p) {
        draw_game(sample, 256, 192); ui_menu(renderer, 2, p, 4, false, false, SDL_GameControllerName(controllers[p]), NULL);
        screenshot(p ? "bindings-j2.bmp" : "bindings.bmp");
        for (int language = 0; language < 2; ++language) {
            assert(controls_language(language));
            draw_game(sample, 256, 192); ui_menu(renderer, 2, p, controls_action_count(p)-1, true, false, SDL_GameControllerName(controllers[p]), NULL);
            screenshot(p ? (language ? "gamepad-j2-fr.bmp" : "gamepad-j2-en.bmp") : (language ? "gamepad-j1-fr.bmp" : "gamepad-j1-en.bmp"));
        }
    }
    assert(controls_language(0));
    draw_game(sample, 256, 192); ui_menu(renderer, 3, 0, 0, false, false, NULL, NULL); screenshot("pause.bmp");
    key(SDL_SCANCODE_P); key(SDL_SCANCODE_H); key(SDL_SCANCODE_ESCAPE); assert(menu == 3);
    key(SDL_SCANCODE_P); assert(!menu);
    SDL_FlushEvents(SDL_FIRSTEVENT, SDL_LASTEVENT);
    _putenv_s("SMSRECOMP_STRICT", "1");
    uint64_t baseline = run_game(0, 0);
    run_game(1, 0); assert(run_game(0, 0) == baseline);
    run_game(2, 0);
    event = button_event(0, SDL_CONTROLLER_BUTTON_BACK);
    assert(handle_event(&event) && !smsrecomp_take_reset_request());
    event.type = SDL_CONTROLLERBUTTONUP; assert(handle_event(&event));
    assert(run_game(0, 0) == baseline);
    assert(run_game(0, 1) == baseline && pause_elapsed >= 70);
    assert(run_game(0, 2) == baseline && pause_elapsed >= 70);
    assert(run_game(0, 3) == baseline && pause_elapsed >= 70);
    assert(run_game(0, 4) == baseline && pause_elapsed >= 70);
    assert(run_game(0, 5) == baseline && pause_elapsed >= 70);
    assert(run_game(0, 6) == baseline && pause_elapsed >= 70);
    SDL_JoystickDetachVirtual(device);
    SDL_PumpEvents();
    for (int pass = 0; pass < 2; ++pass)
        while (SDL_PollEvent(&event)) assert(handle_event(&event));
    assert(!controllers[0] && controllers[1] && controller_player(id2) == 1);
    menu = 2; selected_player = 0; bind_gamepad = true; capturing = false;
    key(SDL_SCANCODE_C); assert(controllers[0] && !controllers[1] && controller_player(id2) == 0);
    key(SDL_SCANCODE_C); assert(!controllers[0] && controllers[1] && controller_player(id2) == 1);
    key(SDL_SCANCODE_ESCAPE);
    desc.name = "Retro-Recomp virtual Xbox replacement J1";
    device = SDL_JoystickAttachVirtualEx(&desc); assert(device >= 0);
    open_controllers(); assert(controllers[0] && controller_player(id2) == 1);
    SDL_JoystickID id1 = SDL_JoystickInstanceID(SDL_GameControllerGetJoystick(controllers[0]));
    /* Detach by current index: SDL compacts indices when a device is removed. */
    for (int i = SDL_NumJoysticks() - 1; i >= 0; --i)
        if (SDL_JoystickGetDeviceInstanceID(i) == id1 || SDL_JoystickGetDeviceInstanceID(i) == id2)
            assert(SDL_JoystickDetachVirtual(i) == 0);
    SDL_PumpEvents();
    while (SDL_PollEvent(&event)) assert(handle_event(&event));
    assert(!controllers[0] && !controllers[1]);
    host_shutdown();
    assert(host_init(256, 192, 0, 0, 256, 192, 3, "test")); host_set_frame_cap(0);
    assert(run_game(0, 0) == baseline);
    host_shutdown();
    puts("PASS: J1/J2 independent remapping/config migration, two virtual controllers/hotplug, 4096 simultaneous port states.");
    puts("PASS: filters/pixels/fullscreen, P/Enter/numpad and both controllers pause, J1-only reset; native CPU/RAM/VDP/PCM.");
    return 0;
}
