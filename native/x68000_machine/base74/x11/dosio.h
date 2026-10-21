/* Retro-Recomp X68000 compat: host file access used by the machine code.
 *
 * Copyright (c) 2026 Retro-Recomp contributors. MIT License (see LICENSE).
 * Implemented in base74/fileio.c (stdio).
 */
#ifndef RR_BASE74_DOSIO_H
#define RR_BASE74_DOSIO_H

#include "common.h"

#ifdef __cplusplus
extern "C" {
#endif
void *file_open(const char *name);
void *file_create(const char *name);
DWORD file_seek(void *handle, long offset, short mode);
DWORD file_lread(void *handle, void *data, DWORD length);
DWORD file_lwrite(void *handle, const void *data, DWORD length);
short file_close(void *handle);
short file_attr(const char *name);
void file_setcd(const char *directory);
void *file_open_c(const char *name);
void *file_create_c(const char *name);
short file_attr_c(const char *name);
#ifdef __cplusplus
}
#endif

#endif
