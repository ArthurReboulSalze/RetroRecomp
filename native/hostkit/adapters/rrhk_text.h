/* One adapter text in the five game languages (host kit, 22 Nov 2026). Original Retro-Recomp code, MIT.
 *
 * An adapter's own words (a notice, an option row, the on-screen keypad's title) that are not in native/runtime_catalog.inc: that
 * file is a host input of every machine, so a new string there moves every host stamp. Until the catalogue next moves, such a text
 * is a row of this type in the adapter and is read with rrhk_text; it joins assets/locales and rr_tr then (docs/HOST_KIT.md 8).
 *
 *     static const RrhkText c_sound = {"Sound: %s", "Son : %s", "Audio: %s", "Sonido: %s", "Ton: %s"};
 *     rrhk_notice(rrhk_text(&c_sound), 3500);
 *
 * The fields follow rr_language_codes (native/runtime_catalog.inc): en, fr, it, es, de. The texts are printable ASCII, as the games'
 * menus write them (the five languages without accents, "Pave numerique", "Kopfhoerer"): the generated games embed the Latin font
 * subsets only. tests/test_hostkit_text.py checks every row of every adapter that includes this file: five strings, ASCII.
 * A missing or empty translation falls back to the English one. Header only: nothing to build, no state, the same in C and C++. */
#ifndef RRHK_TEXT_H
#define RRHK_TEXT_H
#include "runtime_i18n.h"
#include <string.h>

/* The five game languages, the fields below (a sixth would need a field and a branch here). */
typedef char rrhk_text_five_languages[RR_LANGUAGE_COUNT == 5 ? 1 : -1];

typedef struct {
    const char *en, *fr, *it, *es, *de;
} RrhkText;

/* The text in the game's current language (the F2 choice, rr_language_get), English when that one is missing. */
static inline const char *rrhk_text(const RrhkText *text) {
    const char *code = rr_language_code(rr_language_get());
    const char *chosen = NULL;
    if (code) {
        if (!strcmp(code, "fr")) chosen = text->fr;
        else if (!strcmp(code, "it")) chosen = text->it;
        else if (!strcmp(code, "es")) chosen = text->es;
        else if (!strcmp(code, "de")) chosen = text->de;
    }
    return chosen && chosen[0] ? chosen : text->en;
}

#endif
