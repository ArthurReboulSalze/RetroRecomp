/* The in-game chat of a multiplayer session (hostkit_session.h: CHAT_OUT, CHAT_SHOW, the turn notices). Included at the end of
 * rrhk_session.inc, whose pipe and state it uses; nothing here runs outside a session.
 *
 * Opening: the key labelled Y (Ctrl+Alt+Y on a computer), R3 + Select on player 1's gamepad, or the Chat tile of F2, when no
 * menu is open (another player's pause included). A key or a button this player bound to a control stays the game's. While the
 * entry is open this PC sends the neutral word and asks no pause: the others play on. The keyboard types through SDL's text
 * input (any layout), cut to the ASCII a game draws; the gamepad has six phrases, then an on-screen keyboard. When the entry
 * closes, the word stays neutral until every key and button is released: Enter (a console's Start on the keyboard), Esc, A,
 * B or Start still held from closing it never reach the game (Contra paused on the Enter that sent a line, two-PC test of
 * 17 Nov 2026). Lines received
 * (this player's own included, as the host stamped them) are plates at the top left; the turn plate (shared controls taken in
 * turns) is on the top line. While a menu covers the screen the plates wait, and their time does not run.
 *
 * Original Retro-Recomp code, MIT. */

#define RRHK_CHAT_PLATES 3          /* lines on screen at most */
#define RRHK_CHAT_ROWS 8            /* wrapped rows of those lines, all together, at most */
#define RRHK_CHAT_SHOW_MS 6000      /* a line stays this long, one second more for each wrapped row after the first */
#define RRHK_CHAT_FADE_MS 500
#define RRHK_CHAT_TURN_BRIGHT_MS 2000
#define RRHK_CHAT_ENTRY_LINE 176    /* the entry's line on the menu canvas; the shell's notices move above the chat */

/* The phrases, in the order of their numbers (RRHK_PHRASE_*), as the catalogue keys them. */
static const char *const chat_phrases[RRHK_PHRASE_COUNT] = {"GG", "Ready?", "Again?", "Pause please", "One moment", "Thanks!"};
/* The on-screen keyboard: two rows of three phrases, then four rows of ten keys. */
static const char *const chat_keys[4] = {"1234567890", "qwertyuiop", "asdfghjkl'", "zxcvbnm,.?"};
enum { CHAT_PHRASE_ROWS = 2, CHAT_PHRASE_COLUMNS = 3, CHAT_GRID_ROWS = CHAT_PHRASE_ROWS + 4, CHAT_KEY_COLUMNS = 10 };

typedef struct {
    char name[RRHK_CHAT_MAX_NAME + 1];
    char text[RRHK_CHAT_MAX_TEXT + 1];
    int phrase;                     /* 0: free text; else drawn in this player's language */
    bool timed;                     /* its time is set (when first drawn, from its wrapped rows) */
    Sint64 left_ms;                 /* time still on screen */
} RrhkChatLine;

static struct {
    bool open, grid;                /* the entry is open; the on-screen keyboard is shown */
    bool swallow_text;              /* the text event of the key that opened the entry is not typed */
    bool started_text;              /* this entry turned SDL's text input on (and turns it off) */
    bool release;                   /* closed, but a key or button held then may still be down: the word stays neutral */
    char draft[RRHK_CHAT_MAX_TEXT + 1];
    int len, caret, scroll;
    char last_sent[RRHK_CHAT_MAX_TEXT + 1];   /* given back to the draft if the line was refused (too many) */
    int row, column;                /* the on-screen keyboard's selection: rows 0-1 phrases, 2-5 keys */
    RrhkChatLine lines[RRHK_CHAT_PLATES];
    int count;
    int turn;                       /* 0: no turns; 1: another player's turn; 2: this player's */
    char turn_name[RRHK_CHAT_MAX_NAME + 1];
    Uint64 turn_bright_until;
    Uint64 tick;
} chat;

bool rrhk_chat_open(void) { return chat.open; }

/* Any key of the keyboard, or any button or trigger of player 1's pad, is down. */
static bool chat_anything_held(void) {
    int count = 0;
    const Uint8 *keys = SDL_GetKeyboardState(&count);
    for (int k = 0; k < count; ++k) if (keys[k]) return true;
    SDL_GameController *pad = rrhk.pads[0];
    if (pad) {
        for (int b = 0; b < SDL_CONTROLLER_BUTTON_MAX; ++b) if (SDL_GameControllerGetButton(pad, (SDL_GameControllerButton)b)) return true;
        /* a trigger counts as released under half of the press threshold, as game_options.h reads it (rr_trigger_step) */
        if (SDL_GameControllerGetAxis(pad, SDL_CONTROLLER_AXIS_TRIGGERLEFT) >= 8000 ||
            SDL_GameControllerGetAxis(pad, SDL_CONTROLLER_AXIS_TRIGGERRIGHT) >= 8000) return true;
    }
    return false;
}
/* This PC's word must be neutral: the entry is open, or it closed and what was held then is not all released yet. */
bool rrhk_chat_holds_word(void) {
    if (chat.open) return true;
    if (!chat.release) return false;
    if (chat_anything_held()) return true;
    chat.release = false;
    return false;
}
static bool chat_ready(void) { return rrhk_session_on && s.setup && !s.ending_until; }
bool rrhk_chat_offered(void) { return chat_ready(); }

static void chat_close(void) {
    if (chat.open) chat.release = true;
    chat.open = false; chat.swallow_text = false;
    if (chat.started_text) { SDL_StopTextInput(); chat.started_text = false; }
}
static void chat_reset(void) {
    chat_close();
    memset(&chat, 0, sizeof chat);
}

void rrhk_chat_begin(bool grid) {
    if (!chat_ready() || chat.open) return;
    chat.open = true; chat.grid = grid; chat.swallow_text = false;
    chat.caret = chat.len; chat.row = chat.column = 0;      /* the phrases first */
    if (!SDL_IsTextInputActive()) { SDL_StartTextInput(); chat.started_text = true; }
}

/* The player bound this key, or R3, to one of the game's controls: it stays theirs. */
static bool chat_key_bound(SDL_Scancode key) {
    const RrhkMachine *m = rrhk.machine;
    for (int p = 0; p < m->table_players && p < RRHK_MAX_PLAYERS; ++p)
        for (int a = 0; a < m->action_count; ++a) if (rrhk.keys[p][a] == key) return true;
    return false;
}
static bool chat_r3_bound(void) {
    const RrhkMachine *m = rrhk.machine;
    for (int a = 0; a < m->action_count; ++a) if (rrhk.buttons[0][a] == SDL_CONTROLLER_BUTTON_RIGHTSTICK) return true;
    return false;
}
static bool chat_local_pad(SDL_JoystickID which) {
    return rrhk.pads[0] && which == SDL_JoystickInstanceID(SDL_GameControllerGetJoystick(rrhk.pads[0]));
}

/* ---- the draft ---- */

static void chat_insert(const char *utf8) {
    /* The Spanish opening marks have no glyph and would read as '?': they are left out (the closing ones stay). */
    char kept[4 * RRHK_CHAT_MAX_TEXT], ascii[4 * RRHK_CHAT_MAX_TEXT];
    size_t n = 0;
    for (const unsigned char *c = (const unsigned char *)utf8; *c && n + 1 < sizeof kept; ++c) {
        if (c[0] == 0xc2 && (c[1] == 0xa1 || c[1] == 0xbf)) { ++c; continue; }
        kept[n++] = (char)*c;
    }
    kept[n] = 0;
    rr_menu_ascii_text(kept, ascii, sizeof ascii);
    for (const char *c = ascii; *c && chat.len < RRHK_CHAT_MAX_TEXT; ++c) {
        if (*c < 32 || *c > 126) continue;
        memmove(chat.draft + chat.caret + 1, chat.draft + chat.caret, (size_t)(chat.len - chat.caret + 1));
        chat.draft[chat.caret++] = *c;
        ++chat.len;
    }
}
static void chat_erase(int at) {
    if (at < 0 || at >= chat.len) return;
    memmove(chat.draft + at, chat.draft + at + 1, (size_t)(chat.len - at));
    --chat.len;
    if (chat.caret > at) --chat.caret;
}
static bool chat_blank(void) {
    for (int i = 0; i < chat.len; ++i) if (chat.draft[i] != ' ') return false;
    return true;
}

/* A free line (phrase 0, the draft) or a phrase goes to the worker, and the entry closes; a blank draft only closes it. */
static void chat_send(int phrase) {
    if (!phrase && chat_blank()) { chat_close(); return; }
    uint8_t out[2 + RRHK_CHAT_MAX_TEXT];
    out[0] = (uint8_t)phrase;
    out[1] = (uint8_t)(phrase ? 0 : chat.len);
    if (!phrase) memcpy(out + 2, chat.draft, (size_t)chat.len);
    send_message(RRHK_MSG_CHAT_OUT, out, 2u + out[1]);
    if (!phrase) {
        memcpy(chat.last_sent, chat.draft, (size_t)chat.len + 1);
        chat.draft[0] = 0; chat.len = chat.caret = chat.scroll = 0;
    }
    chat_close();
}

/* ---- from the worker ---- */

static void chat_push(const char *name, const char *text, int phrase) {
    if (chat.count == RRHK_CHAT_PLATES) { memmove(chat.lines, chat.lines + 1, sizeof chat.lines[0] * (RRHK_CHAT_PLATES - 1)); --chat.count; }
    RrhkChatLine *line = &chat.lines[chat.count++];
    snprintf(line->name, sizeof line->name, "%s", name);
    snprintf(line->text, sizeof line->text, "%s", text);
    line->phrase = phrase;
    line->timed = false; line->left_ms = 0;
}

/* CHAT_SHOW; false: it broke the rules (the session ends). */
static bool chat_show(const uint8_t *payload, uint16_t length) {
    if (length < 3) return false;
    const unsigned phrase = payload[0], name_length = payload[1];
    if (phrase > RRHK_PHRASE_COUNT || name_length > RRHK_CHAT_MAX_NAME || length < 3u + name_length) return false;
    const unsigned text_length = payload[2 + name_length];
    if (length != 3u + name_length + text_length || text_length > RRHK_CHAT_MAX_TEXT || (phrase ? text_length != 0 : !text_length))
        return false;
    char name[RRHK_CHAT_MAX_NAME + 1], text[RRHK_CHAT_MAX_TEXT + 1];
    copy_name(name, sizeof name, payload + 2, name_length);
    for (unsigned i = 0; i < text_length; ++i) {
        const uint8_t c = payload[3 + name_length + i];
        text[i] = c >= 32 && c < 127 ? (char)c : '?';
    }
    text[text_length] = 0;
    chat_push(name, text, (int)phrase);
    return true;
}
static void chat_turn(int turn, const char *name) {
    if (chat.turn == turn && !strcmp(chat.turn_name, name)) return;
    chat.turn = turn;
    snprintf(chat.turn_name, sizeof chat.turn_name, "%s", name);
    chat.turn_bright_until = SDL_GetTicks64() + RRHK_CHAT_TURN_BRIGHT_MS;
}
/* The worker refused the last line (too many in a short time): it comes back to the draft, unless something else was typed. */
static void chat_slow(void) {
    rrhk_notice(rr_tr("Too many messages: wait a moment"), 2200);
    if (!chat.len && chat.last_sent[0]) {
        snprintf(chat.draft, sizeof chat.draft, "%s", chat.last_sent);
        chat.len = chat.caret = (int)strlen(chat.draft);
    }
}

/* ---- events ---- */

static void chat_move(int down, int right) {
    if (down) {
        const int before = chat.row;
        chat.row = (chat.row + down + CHAT_GRID_ROWS) % CHAT_GRID_ROWS;
        const bool was_phrase = before < CHAT_PHRASE_ROWS, is_phrase = chat.row < CHAT_PHRASE_ROWS;
        if (was_phrase && !is_phrase) chat.column = chat.column * CHAT_KEY_COLUMNS / CHAT_PHRASE_COLUMNS + 1;
        else if (!was_phrase && is_phrase) chat.column = chat.column * CHAT_PHRASE_COLUMNS / CHAT_KEY_COLUMNS;
    }
    const int columns = chat.row < CHAT_PHRASE_ROWS ? CHAT_PHRASE_COLUMNS : CHAT_KEY_COLUMNS;
    chat.column = (chat.column + right + columns) % columns;
}
static void chat_pad_button(int button) {
    if (!chat.grid) { chat.grid = true; return; }       /* the first press shows the on-screen keyboard */
    switch (button) {
    case SDL_CONTROLLER_BUTTON_DPAD_UP: chat_move(-1, 0); break;
    case SDL_CONTROLLER_BUTTON_DPAD_DOWN: chat_move(1, 0); break;
    case SDL_CONTROLLER_BUTTON_DPAD_LEFT: chat_move(0, -1); break;
    case SDL_CONTROLLER_BUTTON_DPAD_RIGHT: chat_move(0, 1); break;
    case SDL_CONTROLLER_BUTTON_LEFTSHOULDER: case SDL_CONTROLLER_BUTTON_RIGHTSHOULDER:
        chat.row = chat.row < CHAT_PHRASE_ROWS ? CHAT_PHRASE_ROWS : 0; chat.column = 0; break;
    case SDL_CONTROLLER_BUTTON_A:
        if (chat.row < CHAT_PHRASE_ROWS) chat_send(chat.row * CHAT_PHRASE_COLUMNS + chat.column + 1);
        else {
            char c[2] = {chat_keys[chat.row - CHAT_PHRASE_ROWS][chat.column], 0};
            if (!chat.len && c[0] >= 'a' && c[0] <= 'z') c[0] = (char)(c[0] - 'a' + 'A');   /* a line starts with a capital */
            chat_insert(c);
        }
        break;
    case SDL_CONTROLLER_BUTTON_X: chat_erase(chat.caret - 1); break;
    case SDL_CONTROLLER_BUTTON_Y: chat_insert(" "); break;
    case SDL_CONTROLLER_BUTTON_START: chat_send(0); break;
    case SDL_CONTROLLER_BUTTON_B: chat_close(); break;
    default: break;
    }
}

/* Before every other handler (rrhk_poll_events). Closed, it takes only what opens the entry; open, every key, text and
 * gamepad button is the entry's (the quit and restart combinations still see them held, as the computers' keyboard does). */
bool rrhk_chat_event(const SDL_Event *event) {
    if (!rrhk_session_on) return false;
    if (chat.open && !chat_ready()) chat_close();
    if (!chat.open) {
        if (!chat_ready() || rrhk.menu || rrhk.capturing) return false;
        if (event->type == SDL_KEYDOWN && !event->key.repeat && event->key.keysym.sym == SDLK_y) {
            const Uint16 mod = event->key.keysym.mod;
            const bool computer = rrhk.machine->keyboard_pad != NULL;
            const bool chord = (mod & KMOD_CTRL) && (mod & KMOD_ALT);
            if (computer ? !chord : (mod & (KMOD_CTRL | KMOD_ALT | KMOD_GUI)) != 0) return false;
            if (!computer && chat_key_bound(event->key.keysym.scancode)) return false;
            rrhk_options_observe(event);
            rrhk_chat_begin(false);
            chat.swallow_text = true;
            return true;
        }
        if (event->type == SDL_CONTROLLERBUTTONDOWN && chat_local_pad(event->cbutton.which) && !chat_r3_bound() &&
            (event->cbutton.button == SDL_CONTROLLER_BUTTON_RIGHTSTICK || event->cbutton.button == SDL_CONTROLLER_BUTTON_BACK)) {
            const SDL_GameControllerButton other = event->cbutton.button == SDL_CONTROLLER_BUTTON_BACK ?
                SDL_CONTROLLER_BUTTON_RIGHTSTICK : SDL_CONTROLLER_BUTTON_BACK;
            if (!SDL_GameControllerGetButton(rrhk.pads[0], other)) return false;
            rrhk_options_observe(event);
            rrhk_chat_begin(true);
            return true;
        }
        return false;
    }
    switch (event->type) {
    case SDL_TEXTINPUT:
        if (chat.swallow_text) { chat.swallow_text = false; return true; }
        chat_insert(event->text.text);
        return true;
    case SDL_TEXTEDITING:
        return true;
    case SDL_KEYDOWN: {
        rrhk_options_observe(event);
        const SDL_Scancode key = event->key.keysym.scancode;
        if (event->key.keysym.sym != SDLK_y) chat.swallow_text = false;
        if (event->key.repeat && key != SDL_SCANCODE_BACKSPACE && key != SDL_SCANCODE_DELETE && key != SDL_SCANCODE_LEFT &&
            key != SDL_SCANCODE_RIGHT) return true;
        if (key == SDL_SCANCODE_ESCAPE) chat_close();
        else if (key == SDL_SCANCODE_RETURN || key == SDL_SCANCODE_KP_ENTER) chat_send(0);
        else if (key == SDL_SCANCODE_BACKSPACE) chat_erase(chat.caret - 1);
        else if (key == SDL_SCANCODE_DELETE) chat_erase(chat.caret);
        else if (key == SDL_SCANCODE_LEFT && chat.caret > 0) --chat.caret;
        else if (key == SDL_SCANCODE_RIGHT && chat.caret < chat.len) ++chat.caret;
        else if (key == SDL_SCANCODE_HOME) chat.caret = 0;
        else if (key == SDL_SCANCODE_END) chat.caret = chat.len;
        else if (key == SDL_SCANCODE_V && (event->key.keysym.mod & KMOD_CTRL) && SDL_HasClipboardText()) {
            char *text = SDL_GetClipboardText();
            if (text) { chat_insert(text); SDL_free(text); }
        }
        return true;
    }
    case SDL_KEYUP: case SDL_CONTROLLERBUTTONUP:
        rrhk_options_observe(event);
        return true;
    case SDL_CONTROLLERBUTTONDOWN:
        rrhk_options_observe(event);
        if (chat_local_pad(event->cbutton.which)) chat_pad_button(event->cbutton.button);
        return true;
    default:
        return false;
    }
}

/* ---- drawing ---- */

/* Where the shell's notices go while the chat holds the bottom of the screen (their line, on the menu canvas). */
int rrhk_chat_notice_line(void) {
    if (!rrhk_session_on || !chat.open) return 172;
    return chat.grid ? 60 : 138;
}

static void chat_color(int *rgb, int red, int green, int blue, double fade) {
    rgb[0] = (int)(red * fade); rgb[1] = (int)(green * fade); rgb[2] = (int)(blue * fade);
}
static void chat_plate_box(SDL_Renderer *ren, int ox, int oy, int unit, int x, int y, int w, int h, int alpha, double fade) {
    rr_menu_box(ren, ox, oy, unit, x, y, w, h, 0, 0, 0, (int)(alpha * fade));
    rr_menu_box(ren, ox, oy, unit, x, y, w, 1, RR_MENU_GOLD, (int)(255 * fade));
    rr_menu_box(ren, ox, oy, unit, x, y + h - 1, w, 1, RR_MENU_SHADE, (int)(255 * fade));
}

/* `text` cut into rows of at most `cells` characters, at a space when there is one; returns how many (at most `max`). */
static int chat_wrap(const char *text, int cells, int *start, int *length, int max) {
    int rows = 0, at = 0;
    const int total = (int)strlen(text);
    while (at < total && rows < max) {
        int n = total - at;
        if (n > cells) {
            n = cells;
            for (int i = cells; i > cells / 2; --i) if (text[at + i] == ' ') { n = i; break; }
        }
        start[rows] = at; length[rows] = n; ++rows;
        at += n;
        while (at < total && text[at] == ' ') ++at;
    }
    return rows;
}

/* The lines, from `top`, ending above `bottom` (the entry, the on-screen keyboard): when they do not all fit, the oldest wait
 * unseen (their time runs) and the newest are shown. */
static void chat_draw_lines(SDL_Renderer *ren, int ox, int oy, int unit, int top, int bottom, Uint64 elapsed) {
    const int cell = rr_menu_text_width("M"), cells = 234 / cell;
    char line[RRHK_CHAT_PLATES][RRHK_CHAT_MAX_NAME + 3 + 200], part[200];
    int start[RRHK_CHAT_PLATES][RRHK_CHAT_ROWS], length[RRHK_CHAT_PLATES][RRHK_CHAT_ROWS], rows[RRHK_CHAT_PLATES];
    /* Wrap and age every line; the newest are kept when the rows run out (RRHK_CHAT_ROWS in all). */
    int rows_used = 0, first = chat.count;
    for (int i = chat.count - 1; i >= 0; --i) {
        RrhkChatLine *l = &chat.lines[i];
        snprintf(line[i], sizeof line[i], "%s: %s", l->name, l->phrase ? rr_tr(chat_phrases[l->phrase - 1]) : l->text);
        rows[i] = chat_wrap(line[i], cells, start[i], length[i], RRHK_CHAT_ROWS);
        if (!l->timed) { l->timed = true; l->left_ms = RRHK_CHAT_SHOW_MS + 1000 * (rows[i] - 1); }
        else l->left_ms -= (Sint64)elapsed;
        if (first == i + 1 && rows_used + rows[i] <= RRHK_CHAT_ROWS) { rows_used += rows[i]; first = i; }
    }
    /* Which of them fit above `bottom`, counting from the newest. */
    int shown = chat.count, height = 0;
    for (int i = chat.count - 1; i >= first; --i) {
        if (chat.lines[i].left_ms <= 0) continue;
        const int h = rows[i] * RR_MENU_LINE + 5 + 2;
        if (top + height + h > bottom) break;
        height += h; shown = i;
    }
    int y = top;
    for (int i = shown; i < chat.count; ++i) {
        const RrhkChatLine *l = &chat.lines[i];
        if (l->left_ms <= 0) continue;
        const double fade = l->left_ms < RRHK_CHAT_FADE_MS ? (double)l->left_ms / RRHK_CHAT_FADE_MS : 1.0;
        int widest = 0;
        for (int r = 0; r < rows[i]; ++r) if (length[i][r] > widest) widest = length[i][r];
        const int h = rows[i] * RR_MENU_LINE + 5;
        chat_plate_box(ren, ox, oy, unit, 6, y, widest * cell + 10, h, 215, fade);
        const int name_cells = (int)strlen(l->name) + 1;          /* the name and its colon, on the first row */
        int gold[3], hint[3];
        chat_color(gold, RR_MENU_GOLD, fade); chat_color(hint, RR_MENU_HINT, fade);
        for (int r = 0; r < rows[i]; ++r) {
            int x = 11, at = start[i][r], n = length[i][r];
            if (r == 0) {
                snprintf(part, sizeof part, "%.*s", name_cells, line[i]);
                rr_menu_text_plain(ren, ox, oy, unit, x, y + 3, name_cells * cell, part, hint[0], hint[1], hint[2]);
                x += name_cells * cell; at += name_cells; n -= name_cells;
            }
            if (n > 0) {
                snprintf(part, sizeof part, "%.*s", n, line[i] + at);
                rr_menu_text_plain(ren, ox, oy, unit, x, y + 3 + r * RR_MENU_LINE, n * cell, part, gold[0], gold[1], gold[2]);
            }
        }
        y += h + 2;
    }
    /* The lines past the rows' limit, and those whose time ran out, leave. */
    int kept = 0;
    for (int i = first; i < chat.count; ++i) if (chat.lines[i].left_ms > 0) chat.lines[kept++] = chat.lines[i];
    chat.count = kept;
}

/* The turn badge (1.8.1): in a match in turns, always there for every seat (the options row « Turn badge » hides it), from who
 * holds the controls now (rrhk_session_holder); bright for two seconds after a change (the TURN notices), gold for this seat. */
static int chat_turn_shown(void) {
    const int holder = rrhk_session_holder();
    if (holder < 0 || !rrhk_turn_badge()) return 0;
    return holder == rrhk_session_seat() ? 2 : 1;
}
static void chat_draw_turn(SDL_Renderer *ren, int ox, int oy, int unit, Uint64 now) {
    char text[64];
    const int turn = chat_turn_shown();
    if (turn == 2) snprintf(text, sizeof text, "%s", rr_tr("Your turn"));
    else snprintf(text, sizeof text, rr_tr("Turn: %s"), rrhk_session_seat_name(rrhk_session_holder()));
    const bool bright = now < chat.turn_bright_until;
    int width = rr_menu_text_width(text); if (width > 200) width = 200;
    const int x = 250 - width - 10;
    chat_plate_box(ren, ox, oy, unit, x, 3, width + 10, 15, bright ? 235 : 150, 1.0);
    if (bright || turn == 2) rr_menu_text_plain(ren, ox, oy, unit, x + 5, 6, width, text, RR_MENU_ACCENT);
    else rr_menu_text_plain(ren, ox, oy, unit, x + 5, 6, width, text, RR_MENU_HINT);
}

static void chat_draw_grid(SDL_Renderer *ren, int ox, int oy, int unit) {
    rr_menu_box(ren, ox, oy, unit, 6, 77, 244, 93, RR_MENU_PANEL_RGB, 235);
    rr_menu_box(ren, ox, oy, unit, 6, 77, 244, 1, RR_MENU_GOLD, 255);
    rr_menu_hints(ren, ox, oy, unit, 12, 80, 232, rr_tr("A: type | X: delete | Y: space"), RR_MENU_HINT);
    rr_menu_hints(ren, ox, oy, unit, 12, 90, 232, rr_tr("Start: send | B: close | LB/RB: phrases"), RR_MENU_HINT);
    for (int row = 0; row < CHAT_GRID_ROWS; ++row) {
        const bool phrases = row < CHAT_PHRASE_ROWS;
        const int columns = phrases ? CHAT_PHRASE_COLUMNS : CHAT_KEY_COLUMNS, w = phrases ? 78 : 22, step = phrases ? 80 : 24;
        const int y = phrases ? 102 + row * 11 : 126 + (row - CHAT_PHRASE_ROWS) * 11;
        for (int column = 0; column < columns; ++column) {
            const int x = 8 + column * step;
            const bool selected = row == chat.row && column == chat.column;
            char label[40];
            if (phrases) snprintf(label, sizeof label, "%s", rr_tr(chat_phrases[row * CHAT_PHRASE_COLUMNS + column]));
            else {
                char c = chat_keys[row - CHAT_PHRASE_ROWS][column];
                if (!chat.len && c >= 'a' && c <= 'z') c = (char)(c - 'a' + 'A');
                label[0] = c; label[1] = 0;
            }
            if (selected) {
                rr_menu_box(ren, ox, oy, unit, x - 1, y - 1, w + 2, 12, RR_MENU_GOLD, 255);
                rr_menu_box(ren, ox, oy, unit, x, y, w, 10, RR_MENU_SELECT, 255);
            } else rr_menu_box(ren, ox, oy, unit, x, y, w, 10, 34, 30, 22, 255);
            int width = rr_menu_text_width(label); if (width > w - 4) width = w - 4;
            if (selected) rr_menu_text_plain(ren, ox, oy, unit, x + (w - width) / 2, y, width, label, RR_MENU_ACCENT);
            else rr_menu_text_plain(ren, ox, oy, unit, x + (w - width) / 2, y, width, label, RR_MENU_GOLD);
        }
    }
}

static void chat_draw_entry(SDL_Renderer *ren, int ox, int oy, int unit, Uint64 now) {
    const int y = RRHK_CHAT_ENTRY_LINE, cell = rr_menu_text_width("M");
    if (!chat.grid) rr_menu_plate(ren, ox, oy, unit, y - 18, "Enter: send | Esc: close", -1);
    chat_plate_box(ren, ox, oy, unit, 6, y - 3, 244, 16, 225, 1.0);
    char prefix[40], counter[16] = "";
    snprintf(prefix, sizeof prefix, "%s: ", rr_tr("Chat"));
    if (chat.len >= RRHK_CHAT_MAX_TEXT - 20) snprintf(counter, sizeof counter, "%d/%d", chat.len, RRHK_CHAT_MAX_TEXT);
    const int prefix_width = rr_menu_text_width(prefix), counter_width = rr_menu_text_width(counter);
    rr_menu_text_plain(ren, ox, oy, unit, 11, y, prefix_width, prefix, RR_MENU_HINT);
    if (counter[0]) rr_menu_text_plain(ren, ox, oy, unit, 245 - counter_width, y, counter_width, counter, RR_MENU_HINT);
    int visible = (234 - prefix_width - (counter[0] ? counter_width + 4 : 0)) / cell - 1;
    if (visible < 1) visible = 1;
    if (chat.caret < chat.scroll) chat.scroll = chat.caret;
    if (chat.caret > chat.scroll + visible) chat.scroll = chat.caret - visible;
    if (chat.scroll > chat.len) chat.scroll = chat.len;
    char shown[RRHK_CHAT_MAX_TEXT + 1];
    const int n = chat.len - chat.scroll < visible ? chat.len - chat.scroll : visible;
    snprintf(shown, sizeof shown, "%.*s", n, chat.draft + chat.scroll);
    const int x = 11 + prefix_width;
    if (n > 0) rr_menu_text_plain(ren, ox, oy, unit, x, y, n * cell, shown, RR_MENU_GOLD);
    if ((now / 500) % 2 == 0) rr_menu_box(ren, ox, oy, unit, x + (chat.caret - chat.scroll) * cell, y + 1, 1, 9, RR_MENU_ACCENT, 255);
}

/* After the menus and the notices (end_frame): the lines, the turn plate, the entry. */
void rrhk_chat_draw(SDL_Renderer *ren) {
    if (!rrhk_session_on) return;
    const Uint64 now = SDL_GetTicks64(), elapsed = chat.tick ? now - chat.tick : 0;
    chat.tick = now;
    const int turn = chat_turn_shown();
    if (rrhk.menu || (!chat.count && !turn && !chat.open)) return;   /* a menu covers the screen: the lines wait */
    int ox, oy, unit;
    rr_menu_layout(ren, &ox, &oy, &unit);
    SDL_SetRenderDrawBlendMode(ren, SDL_BLENDMODE_BLEND);
    if (turn) chat_draw_turn(ren, ox, oy, unit, now);
    /* the lines end above the on-screen keyboard (77), the entry's key hints (155) or the shell's notices */
    const int bottom = !chat.open ? 160 : chat.grid ? 75 : 153;
    if (chat.count) chat_draw_lines(ren, ox, oy, unit, turn ? 21 : 3, bottom, elapsed);
    if (chat.open) {
        if (chat.grid) chat_draw_grid(ren, ox, oy, unit);
        chat_draw_entry(ren, ox, oy, unit, now);
    }
    SDL_SetRenderDrawBlendMode(ren, SDL_BLENDMODE_NONE);
}
