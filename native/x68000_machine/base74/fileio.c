/* Retro-Recomp X68000: host file access for the 2014 machine code.
 *
 * Copyright (c) 2026 Retro-Recomp contributors. MIT License (see LICENSE).
 *
 * Semantics from docs/X68000_PHASE3_PORTING.md section 1 (open read/write
 * then read-only, NULL on failure; seek returns the absolute position; *_c
 * names are joined onto the directory set by file_setcd). Paths are UTF-8.
 */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>

#ifdef _WIN32
#include <wchar.h>
/* Declared here: the compat "windows.h" shadows the system header. */
__declspec(dllimport) int __stdcall MultiByteToWideChar(unsigned, unsigned long, const char *, int,
                                                        wchar_t *, int);
#define RR_SLASH '\\'
#else
#define RR_SLASH '/'
#endif

typedef uint32_t DWORD;

static char current_directory[4096];

static FILE *open_utf8(const char *name, const char *mode)
{
#ifdef _WIN32
   wchar_t wide_name[4096], wide_mode[8];
   if (!MultiByteToWideChar(65001u, 0, name, -1, wide_name, 4096) ||
       !MultiByteToWideChar(65001u, 0, mode, -1, wide_mode, 8))
      return NULL;
   return _wfopen(wide_name, wide_mode);
#else
   return fopen(name, mode);
#endif
}

void *file_open(const char *name)
{
   FILE *file;
   if (!name || !*name)
      return NULL;
   file = open_utf8(name, "rb+");
   if (!file)
      file = open_utf8(name, "rb");
   return file;
}

void *file_create(const char *name)
{
   return name && *name ? open_utf8(name, "wb+") : NULL;
}

DWORD file_seek(void *handle, long offset, short mode)
{
   int origin = mode == 1 ? SEEK_CUR : mode == 2 ? SEEK_END : SEEK_SET;
   if (!handle || fseek((FILE *)handle, offset, origin) != 0)
      return (DWORD)-1;
   return (DWORD)ftell((FILE *)handle);
}

DWORD file_lread(void *handle, void *data, DWORD length)
{
   return handle ? (DWORD)fread(data, 1, length, (FILE *)handle) : 0;
}

DWORD file_lwrite(void *handle, const void *data, DWORD length)
{
   return handle ? (DWORD)fwrite(data, 1, length, (FILE *)handle) : 0;
}

short file_close(void *handle)
{
   if (handle)
      fclose((FILE *)handle);
   return 0;
}

short file_attr(const char *name)
{
   FILE *file = name ? open_utf8(name, "rb") : NULL;
   if (!file)
      return -1;
   fclose(file);
   return 0;
}

void file_setcd(const char *directory)
{
   snprintf(current_directory, sizeof current_directory, "%s", directory ? directory : "");
}

static void joined(char *out, size_t size, const char *name)
{
   size_t length = strlen(current_directory);
   if (length && current_directory[length - 1] != RR_SLASH)
      snprintf(out, size, "%s%c%s", current_directory, RR_SLASH, name);
   else
      snprintf(out, size, "%s%s", current_directory, name);
}

void *file_open_c(const char *name)
{
   char path[4096];
   joined(path, sizeof path, name);
   return file_open(path);
}

void *file_create_c(const char *name)
{
   char path[4096];
   joined(path, sizeof path, name);
   return file_create(path);
}

short file_attr_c(const char *name)
{
   char path[4096];
   joined(path, sizeof path, name);
   return file_attr(path);
}
