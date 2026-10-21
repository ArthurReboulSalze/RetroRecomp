/* Retro-Recomp X68000 compat: File_* names used by the machine code.
 *
 * Copyright (c) 2026 Retro-Recomp contributors. MIT License (see LICENSE).
 */
#ifndef RR_BASE74_FILEIO_H
#define RR_BASE74_FILEIO_H

#include "common.h"
#include "dosio.h"

#define FILEH HANDLE
#define FSEEK_SET 0
#define FSEEK_CUR 1
#define FSEEK_END 2

/* Callers pass BYTE* or char* names; the file layer only reads them. */
#define File_Open(n) file_open((const char *)(n))
#define File_Create(n) file_create((const char *)(n))
#define File_Seek file_seek
#define File_Read file_lread
#define File_Write file_lwrite
#define File_Close file_close
#define File_Attr(n) file_attr((const char *)(n))
#define File_SetCurDir(n) file_setcd((const char *)(n))
#define File_OpenCurDir(n) file_open_c((const char *)(n))
#define File_CreateCurDir(n, ...) file_create_c((const char *)(n))
#define File_AttrCurDir(n) file_attr_c((const char *)(n))

#endif
