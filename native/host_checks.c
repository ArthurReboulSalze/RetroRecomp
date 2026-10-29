/* Diagnostic target only: the host kit's Master System / Game Gear adapter (the adapter is included, the shell is linked),
 * driven by synthetic SDL events with the dummy video driver, through the actual generated game code of the game it is
 * built for. Checks the former French preferences, the Pause menu, the menus opened from it, Shift+F1 and Esc, and that a
 * pause leaves the guest untouched. NDEBUG must not disable checks in this Release target. */
#undef NDEBUG
#include <assert.h>
#include "hostkit/adapters/rrhk_sms.c"
#include "hostkit/hostkit_internal.h"
#include "include/sms_runtime.h"
#include "audio/sn76489.h"
#include "paths.h"

static int reset_kind, pause_kind;
static uint64_t pause_elapsed, pcm_hash;

static SDL_Event make_key(SDL_Scancode code, int mod) {
    SDL_Event event; SDL_zero(event); event.type = SDL_KEYDOWN;
    event.key.keysym.scancode = code; event.key.keysym.sym = SDL_GetKeyFromScancode(code); event.key.keysym.mod = (uint16_t)mod;
    return event;
}
static void push_key(SDL_Scancode code, int mod) { SDL_Event e = make_key(code, mod); assert(SDL_PushEvent(&e) == 1); }
static uint64_t hash_bytes(uint64_t h, const void *data, size_t n) {
    const uint8_t *p = data;
    for (size_t i = 0; i < n; ++i) { h ^= p[i]; h *= 1099511628211ULL; }
    return h;
}
static void sink(const int16_t *samples, size_t frames) { pcm_hash = hash_bytes(pcm_hash, samples, frames * 4); }
static uint8_t scripted_pad(uint64_t frame) {
    if (frame >= 120 && frame < 125) return SMS_PAD_B2;
    if (frame >= 240 && frame < 360) return SMS_PAD_RIGHT;
    if (frame >= 360 && frame < 390) return SMS_PAD_RIGHT | SMS_PAD_B1;
    return 0;
}
/* The key bound to Start/Menu: player 1's (P here, from the former file) or player 2's. */
static SDL_Scancode pause_key(int kind) { return rrhk_ui()->keys[kind == 4 ? 1 : 0][PAUSE]; }
static uint32_t resume_timer(uint32_t interval, void *kind) {
    (void)interval;
    SDL_Event event = make_key(pause_key((int)(uintptr_t)kind), 0);
    SDL_PushEvent(&event);
    return 0;
}

/* One frame of the guest has run: the checks push their events here, and host_present handles them. */
static int game_callback(const uint32_t *fb, int w, int h) {
    const uint64_t frame = glue_frame_count();
    if (frame == 600 && !reset_kind && !pause_kind) {
        assert(crop.w == 256 - smsrecomp_frame_left_border());
        int ww, wh; SDL_GetWindowSize(rrhk_window(), &ww, &wh);
        assert(ww == 768 && wh == 576);
    }
    if (reset_kind && frame == 180) {
        SDL_FlushEvents(SDL_FIRSTEVENT, SDL_LASTEVENT);
        push_key(reset_kind == 1 ? SDL_SCANCODE_F1 : SDL_SCANCODE_ESCAPE, reset_kind == 1 ? KMOD_LSHIFT : 0);
        assert(!host_present(fb, w, h));
        return 1;
    }
    if (pause_kind && frame == 150) {
        /* Delay the release so that the menu loop must run, with no extra guest frame. */
        SDL_FlushEvents(SDL_FIRSTEVENT, SDL_LASTEVENT);
        push_key(pause_key(pause_kind), 0);
        assert(SDL_AddTimer(100, resume_timer, (void *)(uintptr_t)pause_kind));
        uint64_t start = SDL_GetTicks64();
        assert(host_present(fb, w, h));
        pause_elapsed = SDL_GetTicks64() - start;
        assert(pause_elapsed >= 70 && glue_frame_count() == 150 && !rrhk_ui()->menu);
    }
    return 0;
}

static uint64_t run_game(int reset, int pause) {
    reset_kind = reset; pause_kind = pause;
    pcm_hash = 1469598103934665603ULL;
    assert(host_init(256, 192, 0, 0, 256, 192, 3, "test")); host_set_frame_cap(0);
    assert(glue_load_rom("embedded.sms")); glue_init(false, 600);
    glue_set_input_cb(scripted_pad); glue_set_audio_sink(sink);
    glue_set_frame_callback(game_callback); glue_run();
    host_shutdown();
    if (reset) {
        assert(glue_frame_count() == 180);
        assert(reset == 1 ? smsrecomp_take_reset_request() : !smsrecomp_take_reset_request());
        assert(!smsrecomp_take_reset_request());
    } else assert(glue_frame_count() == 600 && smsrecomp_interpreter_cycles() == 0);
    uint64_t h = hash_bytes(pcm_hash, &g_z80, sizeof g_z80);
    h = hash_bytes(h, &g_vdp, sizeof g_vdp);
    for (int addr = 0xC000; addr < 0xE000; ++addr) { uint8_t value = sms_read8((uint16_t)addr); h = hash_bytes(h, &value, 1); }
    return h;
}

static void preferences_file(wchar_t *file) {
    wchar_t dir[RETRO_PATH_CAP];
    assert(rr_executable_directory(dir, RETRO_PATH_CAP - 64));
    swprintf(file, RETRO_PATH_CAP, L"%ls" RR_SLASH_W L"datas", dir); rr_mkdir(file);
    swprintf(file, RETRO_PATH_CAP, L"%ls" RR_SLASH_W L"datas" RR_SLASH_W L"Retro-Recomp.ini", dir);
}

int main(void) {
    SDL_SetHint(SDL_HINT_JOYSTICK_ALLOW_BACKGROUND_EVENTS, "1");
    wchar_t file[RETRO_PATH_CAP];
    preferences_file(file);
    FILE *old = rr_fopen(file, L"wb"); assert(old);
    /* A customized configuration of 0.7 to 1.6: French sections, SDL names, the unchanged layout of player 2. */
    fputs("[Clavier]\r\nbouton1=C\r\nstart=P\r\n[Manette]\r\nbouton1=x\r\n[Video]\r\nfiltre=3\r\nmasquer_bord_gauche=0\r\n"
        "[ClavierJ2]\r\nhaut=I\r\nbas=K\r\ngauche=J\r\ndroite=L\r\nbouton1=N\r\nbouton2=M\r\nselect=Keypad 4\r\n"
        "[ManetteJ2]\r\nselect=back\r\n[LightPhaser]\r\ndot_size=4\r\nshape=dot\r\ncolor=green\r\n[Manettes]\r\nautofire=1\r\n", old);
    fclose(old);
    assert(host_init(256, 192, 0, 0, 256, 192, 3, "test")); host_set_frame_cap(0);
    RrhkUi *ui = rrhk_ui();
    /* The former keys are read where the kit's own are absent. */
    assert(ui->keys[0][BUTTON1] == SDL_SCANCODE_C && ui->buttons[0][BUTTON1] == SDL_CONTROLLER_BUTTON_X);
    assert(ui->keys[0][PAUSE] == SDL_SCANCODE_P);
    assert(ui->keys[1][BUTTON1] == SDL_SCANCODE_KP_8 && ui->keys[1][UP] == SDL_SCANCODE_KP_5);   /* the unchanged 0.8 layout is not a choice */
    assert(ui->filter == 3 && ui->language == 0 && ui->autofire == 1);
    assert(ui->pointer_size == 4 && ui->pointer_shape == 1 && ui->pointer_color == 2);
    /* A key of the kit beats the former one, and only that key is written. */
    ui->player = 0; ui->row = BUTTON1; ui->keys[0][BUTTON1] = SDL_SCANCODE_V; rrhk_store_binding();
    rrhk_bind(rrhk_adapter()); rrhk_load_bindings();
    assert(ui->keys[0][BUTTON1] == SDL_SCANCODE_V && ui->keys[0][BUTTON2] == SDL_SCANCODE_X && ui->filter == 3);
    /* The picture: whole pixels, centred; Fit keeps the aspect; the scale does not jump when the left column is blanked. */
    SDL_Rect r;
    for (int border = 0; border <= 8; border += 8) for (int filter = 0; filter < 4; ++filter) {
        full_crop = (SDL_Rect){0, 0, 256, 192}; crop = (SDL_Rect){border, 0, 256 - border, 192}; ui->filter = filter;
        assert(game_rect(1920, 1080, 0, &r) && r.w % crop.w == 0 && r.h == crop.h * (r.w / crop.w));
        assert(r.x == (1920 - r.w) / 2 && r.y == (1080 - r.h) / 2 && (filter != 2 || (r.w / crop.w) % 2 == 0));
        assert(game_rect(1920, 1080, 2, &r) && r.h == 1080 && abs(r.w * crop.h - r.h * crop.w) < crop.h);
    }
    ui->filter = 0; full_crop = crop = (SDL_Rect){0, 0, 256, 192};
    assert(game_rect(319, 201, 0, &r) && r.w == 256 && r.h == 192);
    host_shutdown();
    /* The guest: a pause with each player's key, Shift+F1 and Esc. */
    uint64_t base = run_game(0, 0);
    assert(run_game(0, 1) == base && run_game(0, 4) == base);
    assert(run_game(1, 0) != 0);
    assert(run_game(2, 0) != 0);
    /* The menus: Pause, Help from it, F2 from it; Esc goes back one menu at a time, then to the game. */
    ui->menu = RRHK_MENU_PAUSE; ui->parent_menu = 0;
    rrhk_toggle_menu(RRHK_MENU_HELP); assert(ui->menu == RRHK_MENU_HELP && ui->parent_menu == RRHK_MENU_PAUSE);
    rrhk_close_menu(); assert(ui->menu == RRHK_MENU_PAUSE && !ui->parent_menu);
    rrhk_toggle_settings(); assert(ui->menu == RRHK_MENU_CONTROLS && ui->parent_menu == RRHK_MENU_PAUSE);
    rrhk_toggle_settings(); assert(ui->menu == RRHK_MENU_PAUSE);
    rrhk_close_menu(); assert(!ui->menu);
#ifdef _WIN32
    _wremove(file);
#endif
    puts("PASS: the former French keys are read and the kit's win; Pause menu and the menus opened from it; Shift+F1 and Esc; pause leaves the guest untouched; whole-pixel picture rule.");
    return 0;
}
