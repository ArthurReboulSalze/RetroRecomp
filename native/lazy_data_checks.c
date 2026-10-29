/* Storage behavior, no window/video/rendering or commercial ROM. The preferences are read and written by the host kit
 * (shell input module and the Master System / Game Gear adapter), the former French file included. */
#undef NDEBUG
#include <assert.h>
#include "runtime_glue.c"
#include "retro_keyboard.h"
#include "display_settings.h"
#include "hostkit/hostkit_internal.h"

static RrhkUi *load(void) {
    rrhk_bind(rrhk_adapter());
    rrhk_load_bindings();
    return rrhk_ui();
}

int main(int argc, char **argv) {
    assert(argc == 2 && glue_load_rom("authored"));
    glue_init(false, 0);
    RrhkUi *ui = load();
    wchar_t root[RETRO_PATH_CAP], game[RETRO_PATH_CAP];
    assert(retro_data_directory(root) && retro_game_directory(game));
    bool save = !strcmp(argv[1], "save"), change = !strcmp(argv[1], "config") || !strcmp(argv[1], "legacy_edit");
    bool legacy = !strcmp(argv[1], "legacy") || !strcmp(argv[1], "legacy_edit"), existing = !strcmp(argv[1], "existing");
    bool learning = !strcmp(argv[1], "learn");
    enum { BUTTON1 = 4 };
    if (legacy) {
        /* The French keys of the former file: SDL names, the unchanged 0.8 layout of player 2 ignored. */
        assert(ui->keys[0][BUTTON1] == SDL_SCANCODE_C && ui->filter == 3);
        assert(ui->keys[1][0] == SDL_SCANCODE_KP_5 && ui->keys[1][BUTTON1] == SDL_SCANCODE_KP_8);
    } else if (existing) {
        assert(ui->keys[0][BUTTON1] == SDL_SCANCODE_C && ui->filter == 3);
    } else {
        assert(ui->keys[0][BUTTON1] == rr_keyboard_letter(SDLK_w, SDL_SCANCODE_W) && ui->keys[1][BUTTON1] == SDL_SCANCODE_KP_8);
        assert(!ui->language && !ui->autofire && !ui->pointer_shape);
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
        /* What the shell writes when the player changes the filter and rebinds a key: one entry each. */
        assert(rrhk_write_ready() && rr_display_save(ui->ini_file, ui->data_dir, ui->video_section, L"filter", 3));
        ui->player = 0; ui->row = BUTTON1; ui->keys[0][BUTTON1] = SDL_SCANCODE_C;
        rrhk_store_binding();
        ui = load(); assert(ui->filter == 3 && ui->keys[0][BUTTON1] == SDL_SCANCODE_C);
        assert(ui->keys[1][BUTTON1] == SDL_SCANCODE_KP_8 && ui->buttons[1][BUTTON1] == SDL_CONTROLLER_BUTTON_A);
    }
    if (save) {
        assert(smsrecomp_request_state(RR_QUICKSAVE)); smsrecomp_state_service();
        FILE *f = retro_game_file(L"-quicksave.state", L"rb"); assert(f); fclose(f);
        g_z80.b = 99; assert(smsrecomp_state_load() == RR_STATE_OK && g_z80.b == 43);
    }
    puts("PASS: read-only startup/load-missing/default inputs; fallback reported without runtime learning; explicit config/save writes isolated.");
    return 0;
}
