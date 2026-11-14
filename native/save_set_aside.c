/* A save file a game cannot use, set aside under another name (save_set_aside.h). Original RetroRecomp code: MIT. */
#include "platform_io.h"
#include <stdio.h>

#include "save_set_aside.h"

bool rr_save_set_aside(const wchar_t *file)
{
    wchar_t aside[32768 + 16];
    for (unsigned n = 1; n <= 99; n++) {
        if (swprintf(aside, 32768 + 16, L"%ls.unusable-%u", file, n) < 0) return false;
        FILE *taken = rr_fopen(aside, L"rb");
        if (taken) { fclose(taken); continue; }
        return rr_replace(file, aside) != 0;
    }
    return false;
}
