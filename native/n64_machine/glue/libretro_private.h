/* Retro-Recomp Nintendo 64: frontend callbacks the core files share with libretro.c (which defines them).
 * Written from their uses. SPDX-License-Identifier: MIT */
#pragma once
#include "libretro.h"
#ifdef __cplusplus
extern "C" {
#endif
extern retro_log_printf_t log_cb;
extern retro_environment_t environ_cb;
void retro_return(void);
#ifdef __cplusplus
}
#endif
