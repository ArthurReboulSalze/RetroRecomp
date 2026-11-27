/* The player's « sprite flicker reduction » (F5), one text for the adapters whose video chip leaves sprites past a per-line limit out of
 * the picture (the Master System and the Game Gear, the SG-1000, the ColecoVision): off by default, saved in [<Console>.Video]
 * reduce_sprite_flicker, its menu row and help line the same everywhere. MIT, Retro-Recomp.
 *
 * Included once by an adapter, after it has defined RR_SPRITE_OPTION_APPLY(on): what the option does in this machine. On the
 * TMS9918A machines it is a picture-only switch; on the Master System and the Game Gear it may change what the game reads of the sprite
 * overflow, so those say so to rr_sprite_option_row (`changes_run`) and seal it for a multiplayer session.
 *
 * Its key is F5. A computer, whose F5 is « fast loading » (rrhk_computer.inc), keeps the option on its F2 options row only: it defines
 * RR_SPRITE_OPTION_KEY (a row key past the scancodes, RRHK_ROW_SPRITES, that no keyboard sends), RR_SPRITE_OPTION_ROW (the row's text,
 * without the key's name) and RR_SPRITE_OPTION_HELP (the help line, naming F2) before the include (the MSX family, 27 Nov 2026). */
#ifndef RR_SPRITE_OPTION_KEY
#define RR_SPRITE_OPTION_KEY SDL_SCANCODE_F5
#define RR_SPRITE_OPTION_ROW "F5 Sprite flicker reduction: %s"
#define RR_SPRITE_OPTION_HELP rrhk_tr("F5  Reduce sprite flicker", "F5  Reduire le scintillement")
#endif
static bool rr_sprites_reduced;

static void rr_sprite_option_set(bool on) {
    rr_sprites_reduced = on;
    RR_SPRITE_OPTION_APPLY(on);
}

/* From the adapter's settings_loaded, `file` being the preferences it reads. */
static void rr_sprite_option_load(const RrhkUi *ui, const wchar_t *file) {
    rr_sprite_option_set(rr_ini_int(ui->video_section, L"reduce_sprite_flicker", 0, file) == 1);
}

/* From the adapter's key_event: true when the key was the option's (F5, or the computer's row key). */
static bool rr_sprite_option_key(RrhkUi *ui, SDL_Scancode key) {
    if ((int)key != RR_SPRITE_OPTION_KEY) return false;
    if (rrhk_write_ready() && rr_display_save(ui->ini_file, ui->data_dir, ui->video_section, L"reduce_sprite_flicker", !rr_sprites_reduced)) {
        rr_sprite_option_set(!rr_sprites_reduced);
        rrhk_notice(rr_sprites_reduced ? rrhk_tr("Sprite flicker reduction ON", "Reduction du scintillement ON") :
                                         rrhk_tr("Original console sprite limit", "Limite de sprites de la console"), 1800);
    } else rrhk_notice(rrhk_tr("Config unavailable", "Config inaccessible"), 1800);
    return true;
}

/* The options page's row. `changes_run`: the option may change what the program reads, so a multiplayer host sets it for everyone
 * (false for a picture-only switch, which each player chooses). */
static void rr_sprite_option_row(RrhkOptionRows *rows, bool changes_run) {
    (changes_run ? rrhk_option_row_run : rrhk_option_row_icon)(rows, RR_SPRITE_OPTION_KEY, RR_ICON_ROW_SPRITE, RR_SPRITE_OPTION_ROW,
                                                              rr_tr(rr_sprites_reduced ? "ON" : "OFF"));
}

static const char *rr_sprite_option_help(void) { return RR_SPRITE_OPTION_HELP; }
