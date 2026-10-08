/* Storage behavior, no window/video/rendering or commercial ROM. */
#undef NDEBUG
#include <assert.h>
#include "runtime_glue.c"
#include "controls.c"
int main(int argc, char **argv) {
    assert(argc == 2 && glue_load_rom("authored"));
    glue_init(false, 0); controls_load();
    wchar_t root[RETRO_PATH_CAP], game[RETRO_PATH_CAP];
    assert(retro_data_directory(root) && retro_game_directory(game));
    bool save = !strcmp(argv[1], "save"), change = !strcmp(argv[1], "config") || !strcmp(argv[1], "legacy_edit");
    bool legacy = !strcmp(argv[1], "legacy") || !strcmp(argv[1], "legacy_edit"), existing = !strcmp(argv[1], "existing");
    bool learning = !strcmp(argv[1], "learn");
    if (legacy) {
        assert(controls.keys[0][4] == SDL_SCANCODE_C && controls.filter == FILTER_SCANLINES);
        assert(controls.keys[1][0] == SDL_SCANCODE_KP_5 && controls.keys[1][4] == SDL_SCANCODE_KP_8);
        assert(controls.keys[1][CONTROL_RESET] == SDL_SCANCODE_UNKNOWN);
    } else if (existing) {
        assert(controls.keys[0][4] == SDL_SCANCODE_C && controls.filter == FILTER_SCANLINES);
    } else {
        assert(controls.keys[0][4] == rr_keyboard_letter(SDLK_w, SDL_SCANCODE_W) && controls.keys[1][4] == SDL_SCANCODE_KP_8);
        assert(!controls.language && !controls.autofire && controls.phaser_shape == PHASER_CROSS);
    }
    assert(!smsrecomp_observations_read());
    if (!existing) assert(GetFileAttributesW(root) == INVALID_FILE_ATTRIBUTES);
    assert(smsrecomp_state_load() == RR_STATE_MISSING);
    retro_game_file_reset(L"-missing.log");
    assert(!retro_game_file_replace(L"-missing.tmp", L"-quicksave.state"));
    if (!existing) assert(GetFileAttributesW(root) == INVALID_FILE_ATTRIBUTES);
    /* A real unknown RAM encoding executes under fallback, without persistence
     * unless this is an explicitly opted-in converter probe. */
    g_z80.pc = 0xC100; g_z80.b = 42; g_ram[0x100] = 0x04;
    assert(game_banked_step(0,1,2) == 0); sms_enter(g_z80.pc); sms_dispatch_miss(g_z80.pc);
    assert(g_z80.b == 43 && g_hybrid_calls == 1 && g_hybrid_cyc > 0);
    if (!existing && !learning) assert(GetFileAttributesW(root) == INVALID_FILE_ATTRIBUTES);
    if (change) {
        assert(controls_filter(FILTER_SCANLINES));
        assert(controls_bind(0,4,false,SDL_SCANCODE_C));
        controls_load(); assert(controls.filter == FILTER_SCANLINES && controls.keys[0][4] == SDL_SCANCODE_C);
        assert(controls.keys[1][4] == SDL_SCANCODE_KP_8 && controls.buttons[1][4] == SDL_CONTROLLER_BUTTON_A);
    }
    if (save) {
        assert(smsrecomp_request_state(RR_QUICKSAVE)); smsrecomp_state_service();
        FILE *f = retro_game_file(L"-quicksave.state", L"rb"); assert(f); fclose(f);
        g_z80.b = 99; assert(smsrecomp_state_load() == RR_STATE_OK && g_z80.b == 43);
    }
    puts("PASS: read-only startup/load-missing/default inputs; fallback reported without runtime learning; explicit config/save writes isolated.");
    return 0;
}
