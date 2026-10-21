/* Retro-Recomp X68000: link stub for the retired section API.
 *
 * Copyright (c) 2026 Retro-Recomp contributors. MIT License (see LICENSE).
 *
 * The current base still carries unused *_StateAction functions that refer
 * to PX68KSS_StateAction. The MIT build never calls them (snapshots use
 * RRX68MS1); this stub only satisfies the linker and fails if reached.
 * It disappears with the pre-2020 machine base (step B), which has none.
 */
#include "common.h"

int PX68KSS_StateAction(void *st, int load, int data_only, SFORMAT *sf, const char *name, bool optional)
{
   (void)st; (void)load; (void)data_only; (void)sf; (void)optional;
   if (log_cb)
      log_cb(RETRO_LOG_ERROR, "Retired snapshot section requested: %s\n", name ? name : "?");
   return 0;
}
