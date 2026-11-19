/* Retro-Recomp X68000: host file access for the 2014 machine code.
 *
 * Copyright (c) 2026 Retro-Recomp contributors. MIT License (see LICENSE).
 *
 * Semantics from docs/history/x68000/X68000_PHASE3_PORTING.md section 1 (open read/write
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

/* ---- Multiplayer session media (Retro-Recomp, MIT) ----
 * In a session every seat plays the export's original disks and nothing reaches the host's files. The images of the
 * disk set are served from memory: the original bytes embedded in the executable, plus the 1 KiB blocks this session
 * wrote (an eject writes the drive back here), kept per image with a dirty bitmap. Every other write is swallowed. The
 * journals are part of the session snapshot (rr_x68k_session_images). */
#include <stdlib.h>
#include "rr_state.h"
#define SESSION_IMAGES 10
#define SESSION_BLOCK 1024u
#define SESSION_IMAGE_MAX (2u * 1024u * 1024u)
#define SESSION_BITMAP (SESSION_IMAGE_MAX / SESSION_BLOCK / 8u)
typedef struct {
   char path[4096];
   const uint8_t *original;          /* the session's starting image: the export's disk, or the host's save of it */
   size_t size;
   uint64_t base_hash;               /* FNV-1a of `original`: the snapshot and the digest cover the starting disks */
   uint8_t *bytes;                   /* the image as written in this session; NULL while it equals the original */
   uint8_t dirty[SESSION_BITMAP];    /* blocks that differ from the original */
} SessionImage;
typedef struct { SessionImage *image; size_t pos; int open; } VirtualFile;
static SessionImage session_images[SESSION_IMAGES];
static VirtualFile virtual_files[8];
static int session_media, session_restoring;

static VirtualFile *virtual_of(void *handle)
{
   VirtualFile *v = (VirtualFile *)handle;
   return v >= virtual_files && v < virtual_files + 8 ? v : NULL;
}

static unsigned session_opens;

/* Opens of the session's files by the guest's drives (an insert or an eject): a drive's shadow is read again after
 * one. Opens while restoring (a shadow read, a restore's eject) do not count. */
unsigned rr_x68k_session_opens(void) { return session_opens; }

static void *virtual_open(SessionImage *image)
{
   unsigned i;
   if (!session_restoring)
      session_opens++;
   for (i = 0; i < 8; i++)
      if (!virtual_files[i].open) {
         virtual_files[i].image = image; virtual_files[i].pos = 0; virtual_files[i].open = 1;
         return &virtual_files[i];
      }
   return NULL;
}

static SessionImage *session_image(const char *name)
{
   unsigned i;
   for (i = 0; i < SESSION_IMAGES; i++)
      if (session_images[i].original && !strcmp(session_images[i].path, name))
         return &session_images[i];
   return NULL;
}

/* One image of the set, by its path as the core opens it. Returns 0 on a bad argument or no memory. */
int rr_x68k_session_media_add(unsigned index, const char *path, const uint8_t *original, size_t size)
{
   SessionImage *image;
   if (index >= SESSION_IMAGES || !path || strlen(path) >= sizeof image->path || !original || !size ||
       size > SESSION_IMAGE_MAX)
      return 0;
   image = &session_images[index];
   free(image->bytes);
   memset(image, 0, sizeof *image);
   snprintf(image->path, sizeof image->path, "%s", path);
   image->original = original;
   image->size = size;
   image->base_hash = 14695981039346656037ull;
   for (size_t at = 0; at < size; at++)
      image->base_hash = (image->base_hash ^ original[at]) * 1099511628211ull;
   session_media = 1;
   return 1;
}

int rr_x68k_session_media_on(void) { return session_media; }

/* The session's image of disk `index` as it is now (its starting bytes plus what was written back to it), NULL: none. */
const uint8_t *rr_x68k_session_image(unsigned index, size_t *size)
{
   SessionImage *image = index < SESSION_IMAGES ? &session_images[index] : NULL;
   if (!image || !image->original) { *size = 0; return NULL; }
   *size = image->size;
   return image->bytes ? image->bytes : image->original;
}

static void joined(char *out, size_t size, const char *name);
/* The SRAM file the machine reads alone (sram.c: sram.dat in the current directory). */
void rr_x68k_sram_path(char *out, size_t size)
{
   joined(out, size, "sram.dat");
}

/* While a session snapshot is loaded, an eject must not write the drive back over the restored journal. */
void rr_x68k_session_restoring(int on) { session_restoring = on; }

static int block_dirty(const SessionImage *image, size_t block)
{
   return (image->dirty[block >> 3] >> (block & 7)) & 1;
}

/* Session snapshot: per image, its size, the dirty bitmap, then the bytes of every dirty block (the last block may be
 * short). The layout is the same before the session starts (no image: size 0, empty bitmap), so the bound can be
 * measured then. *bytes counts the block bytes. */
void rr_x68k_session_images(RRState *s, size_t *bytes)
{
   unsigned i;
   for (i = 0; i < SESSION_IMAGES && !s->error; i++) {
      SessionImage *image = &session_images[i];
      uint8_t dirty[SESSION_BITMAP];
      uint32_t size = (uint32_t)image->size;
      uint64_t base = image->base_hash;
      size_t block, count = (image->size + SESSION_BLOCK - 1) / SESSION_BLOCK, any;
      rr_state_u32(s, &size);
      rr_state_u64(s, &base);
      if (s->loading && !s->error && (size != (uint32_t)image->size || base != image->base_hash)) {
         rr_state_fail(s, "session disk set differs from the snapshot");
         return;
      }
      memcpy(dirty, image->dirty, sizeof dirty);
      rr_state_bytes(s, dirty, sizeof dirty);
      if (s->error || !image->original)
         continue;
      for (any = 0, block = 0; block < sizeof dirty; block++) any |= dirty[block];
      if (s->loading && any && !image->bytes) {
         image->bytes = (uint8_t *)malloc(image->size);
         if (!image->bytes) { rr_state_fail(s, "out of memory for a session disk"); return; }
         memcpy(image->bytes, image->original, image->size);
      }
      for (block = 0; block < count && !s->error; block++) {
         size_t at = block * SESSION_BLOCK, length = image->size - at < SESSION_BLOCK ? image->size - at : SESSION_BLOCK;
         int now = block_dirty(image, block), then = (dirty[block >> 3] >> (block & 7)) & 1;
         if (then) {
            rr_state_bytes(s, image->bytes + at, length);
            if (bytes) *bytes += length;
         } else if (now && s->loading) {
            memcpy(image->bytes + at, image->original + at, length);
         }
      }
      if (s->loading && !s->error)
         memcpy(image->dirty, dirty, sizeof dirty);
   }
}

static DWORD virtual_write(VirtualFile *v, const void *data, DWORD length)
{
   SessionImage *image = v->image;
   size_t at = v->pos, end, block;
   if (!image || session_restoring)
      return length;                     /* swallowed: not a disk of the set, or a restore's eject */
   if (at >= image->size)
      return 0;
   end = at + length > image->size ? image->size : at + length;
   if (!image->bytes) {
      if (!memcmp(image->original + at, data, end - at)) { v->pos = end; return (DWORD)(end - at); }
      image->bytes = (uint8_t *)malloc(image->size);
      if (!image->bytes) return 0;
      memcpy(image->bytes, image->original, image->size);
   }
   memcpy(image->bytes + at, data, end - at);
   for (block = at / SESSION_BLOCK; block * SESSION_BLOCK < end; block++) {
      size_t from = block * SESSION_BLOCK, to = from + SESSION_BLOCK > image->size ? image->size : from + SESSION_BLOCK;
      if (memcmp(image->bytes + from, image->original + from, to - from))
         image->dirty[block >> 3] |= (uint8_t)(1u << (block & 7));
      else
         image->dirty[block >> 3] &= (uint8_t)~(1u << (block & 7));
   }
   v->pos = end;
   return (DWORD)(end - at);
}

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
   SessionImage *image;
   if (!name || !*name)
      return NULL;
   if (session_media && (image = session_image(name)) != NULL)
      return virtual_open(image);
   file = open_utf8(name, "rb+");
   if (!file)
      file = open_utf8(name, "rb");
   return file;
}

void *file_create(const char *name)
{
   if (session_media && name && *name)
      return virtual_open(session_image(name));   /* a new file in a session: writes are swallowed */
   return name && *name ? open_utf8(name, "wb+") : NULL;
}

DWORD file_seek(void *handle, long offset, short mode)
{
   int origin = mode == 1 ? SEEK_CUR : mode == 2 ? SEEK_END : SEEK_SET;
   VirtualFile *v = virtual_of(handle);
   if (v) {
      long base = mode == 1 ? (long)v->pos : mode == 2 ? (long)(v->image ? v->image->size : 0) : 0;
      if (base + offset < 0)
         return (DWORD)-1;
      v->pos = (size_t)(base + offset);
      return (DWORD)v->pos;
   }
   if (!handle || fseek((FILE *)handle, offset, origin) != 0)
      return (DWORD)-1;
   return (DWORD)ftell((FILE *)handle);
}

DWORD file_lread(void *handle, void *data, DWORD length)
{
   VirtualFile *v = virtual_of(handle);
   if (v) {
      const SessionImage *image = v->image;
      size_t n = image && v->pos < image->size ? image->size - v->pos : 0;
      if (n > length) n = length;
      if (n) memcpy(data, (image->bytes ? image->bytes : image->original) + v->pos, n);
      v->pos += n;
      return (DWORD)n;
   }
   return handle ? (DWORD)fread(data, 1, length, (FILE *)handle) : 0;
}

DWORD file_lwrite(void *handle, const void *data, DWORD length)
{
   VirtualFile *v = virtual_of(handle);
   if (v)
      return virtual_write(v, data, length);
   if (session_media)
      return length;                   /* a session never writes the host's files (SRAM, any other file) */
   return handle ? (DWORD)fwrite(data, 1, length, (FILE *)handle) : 0;
}

short file_close(void *handle)
{
   VirtualFile *v = virtual_of(handle);
   if (v)
      v->open = 0;
   else if (handle)
      fclose((FILE *)handle);
   return 0;
}

short file_attr(const char *name)
{
   FILE *file;
   if (session_media && name && session_image(name))
      return 0;
   file = name ? open_utf8(name, "rb") : NULL;
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
