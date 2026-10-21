/* Original Retro-Recomp private X68000 snapshot envelope, MIT. */
#ifndef _WIN32
#define _POSIX_C_SOURCE 200809L
#endif
#include "state_store.h"

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <fcntl.h>
#include <sys/stat.h>
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <io.h>
#include <process.h>
#else
#include <unistd.h>
#endif

#define HEADER_SIZE 168u
#define CHECKSUM_OFFSET 160u
#define FNV_OFFSET UINT64_C(14695981039346656037)
#define FNV_PRIME UINT64_C(1099511628211)
static const unsigned char magic[8] = {'R','R','X','6','8','K','S','1'};

static RRStateResult result(RRStateResult code, char *out, size_t capacity,
                            const char *message) {
    if (out && capacity) {
        size_t length = strlen(message);
        if (length >= capacity) length = capacity - 1;
        memcpy(out, message, length);
        out[length] = 0;
    }
    return code;
}

static bool digest_valid(const char *value) {
    size_t i;
    if (!value || strlen(value) != 64) return false;
    for (i = 0; i < 64; ++i)
        if (!((value[i] >= '0' && value[i] <= '9') ||
              (value[i] >= 'a' && value[i] <= 'f'))) return false;
    return true;
}

static bool io_valid(const RRStateIO *io) {
    return io && digest_valid(io->identity) && digest_valid(io->compatibility) &&
        io->core_size && io->core_size <= RR_X68K_STATE_MAX_CORE &&
        io->auxiliary_size <= RR_X68K_STATE_MAX_AUXILIARY &&
        io->save_core && io->load_core &&
        (!io->auxiliary_size || (io->capture_auxiliary &&
            io->validate_auxiliary && io->apply_auxiliary));
}

static void put32(unsigned char *dst, uint32_t value) {
    unsigned i;
    for (i = 0; i < 4; ++i) dst[i] = (unsigned char)(value >> (8*i));
}
static void put64(unsigned char *dst, uint64_t value) {
    unsigned i;
    for (i = 0; i < 8; ++i) dst[i] = (unsigned char)(value >> (8*i));
}
static uint32_t get32(const unsigned char *src) {
    uint32_t value = 0;
    unsigned i;
    for (i = 0; i < 4; ++i) value |= (uint32_t)src[i] << (8*i);
    return value;
}
static uint64_t get64(const unsigned char *src) {
    uint64_t value = 0;
    unsigned i;
    for (i = 0; i < 8; ++i) value |= (uint64_t)src[i] << (8*i);
    return value;
}
static uint64_t checksum(uint64_t value, const void *data, size_t size) {
    const unsigned char *p = (const unsigned char *)data;
    while (size--) { value ^= *p++; value *= FNV_PRIME; }
    return value;
}

#ifdef _WIN32
static wchar_t *wide_path(const char *path) {
    int count;
    wchar_t *wide;
    count = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, path, -1, NULL, 0);
    if (count <= 0) return NULL;
    wide = (wchar_t *)malloc((size_t)count * sizeof(*wide));
    if (wide && !MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, path, -1,
                                    wide, count)) { free(wide); wide = NULL; }
    return wide;
}
static FILE *read_file(const char *path) {
    wchar_t *wide = wide_path(path);
    FILE *file = wide ? _wfopen(wide, L"rb") : NULL;
    free(wide);
    return file;
}
static FILE *exclusive_file(const char *path) {
    wchar_t *wide = wide_path(path);
    int fd = wide ? _wopen(wide, _O_CREAT | _O_EXCL | _O_BINARY | _O_WRONLY,
                           _S_IREAD | _S_IWRITE) : -1;
    FILE *file;
    free(wide);
    if (fd < 0) return NULL;
    file = _fdopen(fd, "wb");
    if (!file) _close(fd);
    return file;
}
static bool replace_file(const char *from, const char *to) {
    wchar_t *a = wide_path(from), *b = wide_path(to);
    bool ok = a && b && MoveFileExW(a,b,MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH);
    free(a); free(b);
    return ok;
}
static void remove_file(const char *path) {
    wchar_t *wide = wide_path(path);
    if (wide) _wremove(wide);
    free(wide);
}
static bool commit_file(FILE *file) { return !fflush(file) && !_commit(_fileno(file)); }
static unsigned process_id(void) { return (unsigned)_getpid(); }
#else
static FILE *read_file(const char *path) { return fopen(path, "rb"); }
static FILE *exclusive_file(const char *path) {
    int fd = open(path, O_CREAT | O_EXCL | O_WRONLY, S_IRUSR | S_IWUSR);
    FILE *file;
    if (fd < 0) return NULL;
    file = fdopen(fd, "wb");
    if (!file) close(fd);
    return file;
}
static bool replace_file(const char *from, const char *to) { return !rename(from,to); }
static void remove_file(const char *path) { remove(path); }
static bool commit_file(FILE *file) { return !fflush(file) && !fsync(fileno(file)); }
static unsigned process_id(void) { return (unsigned)getpid(); }
#endif

static bool capture(const RRStateIO *io, unsigned char *data) {
    return (!io->auxiliary_size || io->capture_auxiliary(io->context,
        data + io->core_size, io->auxiliary_size)) &&
        io->save_core(io->context, data, io->core_size);
}

RRStateResult rr_x68k_state_save(const char *path, const RRStateIO *io,
                               char *error, size_t capacity) {
    unsigned char header[HEADER_SIZE], *data = NULL;
    size_t size, path_size;
    char *temporary = NULL;
    FILE *file = NULL;
    uint64_t hash;
    unsigned attempt;
    bool ok;
    RRStateResult status;
    if (!path || !*path || !io_valid(io))
        return result(RR_STATE_INVALID,error,capacity,"Invalid snapshot configuration");
    path_size = strlen(path);
    if (path_size > 32700)
        return result(RR_STATE_INVALID,error,capacity,"Snapshot path is too long");
    size = io->core_size + io->auxiliary_size;
    data = (unsigned char *)calloc(size,1);
    temporary = (char *)malloc(path_size + 64);
    if (temporary) temporary[0] = 0;
    if (!data || !temporary) {
        status = result(RR_STATE_IO_ERROR,error,capacity,"Snapshot allocation failed");
        goto done;
    }
    if (!capture(io,data)) {
        status = result(RR_STATE_CALLBACK_ERROR,error,capacity,"Could not capture the complete snapshot");
        goto done;
    }
    memset(header,0,sizeof(header));
    memcpy(header,magic,sizeof(magic)); put32(header+8,1); put32(header+12,HEADER_SIZE);
    put64(header+16,(uint64_t)io->core_size);
    put64(header+24,(uint64_t)io->auxiliary_size);
    memcpy(header+32,io->identity,64); memcpy(header+96,io->compatibility,64);
    hash = checksum(FNV_OFFSET,header,CHECKSUM_OFFSET);
    put64(header+CHECKSUM_OFFSET,checksum(hash,data,size));
    /* Exclusive creation prevents overwriting a stale file or following an
     * attacker-supplied temporary symlink. Never delete another process's file. */
    for (attempt = 0; attempt < 128; ++attempt) {
        snprintf(temporary,path_size+64,"%s.tmp.%u.%u",path,process_id(),attempt);
        file = exclusive_file(temporary);
        if (file || errno != EEXIST) break;
    }
    if (!file) {
        status = result(RR_STATE_IO_ERROR,error,capacity,"Could not create the snapshot temporary file");
        temporary[0] = 0;
        goto done;
    }
    ok = fwrite(header,1,sizeof(header),file)==sizeof(header) &&
         fwrite(data,1,size,file)==size && commit_file(file);
    if (fclose(file)) ok = false;
    file = NULL;
    if (!ok || !replace_file(temporary,path)) {
        status = result(RR_STATE_IO_ERROR,error,capacity,"Could not commit the snapshot; previous save preserved");
        goto done;
    }
    temporary[0] = 0;
    status = result(RR_STATE_OK,error,capacity,"Game state saved");
done:
    if (file) fclose(file);
    if (temporary && *temporary) remove_file(temporary);
    free(temporary); free(data);
    return status;
}

RRStateResult rr_x68k_state_load(const char *path, const RRStateIO *io,
                               char *error, size_t capacity) {
    unsigned char header[HEADER_SIZE], *data = NULL, *rollback = NULL;
    size_t size, saved_core_size, saved_auxiliary_size, rollback_size;
    FILE *file = NULL;
    uint64_t hash;
    bool applied, restored_aux, restored_core;
    RRStateResult status;
    if (!path || !*path || !io_valid(io))
        return result(RR_STATE_INVALID,error,capacity,"Invalid snapshot configuration");
    file = read_file(path);
    if (!file) return result(RR_STATE_IO_ERROR,error,capacity,"No readable saved game state");
    status = RR_STATE_INVALID;
    if (fread(header,1,sizeof(header),file)!=sizeof(header) ||
        memcmp(header,magic,sizeof(magic)) || get32(header+8)!=1 ||
        get32(header+12)!=HEADER_SIZE) {
        result(status,error,capacity,"Invalid or truncated snapshot header");
        goto done;
    }
    if (!get64(header+16) || get64(header+16)>RR_X68K_STATE_MAX_CORE ||
        get64(header+24)>RR_X68K_STATE_MAX_AUXILIARY) {
        result(status,error,capacity,"Snapshot sizes exceed the validated bounds");
        goto done;
    }
    saved_core_size=(size_t)get64(header+16);
    saved_auxiliary_size=(size_t)get64(header+24);
    if (saved_core_size>SIZE_MAX-saved_auxiliary_size) {
        result(status,error,capacity,"Snapshot total size overflow");
        goto done;
    }
    if ((saved_auxiliary_size || io->auxiliary_size) &&
        (!io->validate_auxiliary || !io->apply_auxiliary)) {
        status=result(RR_STATE_INCOMPATIBLE,error,capacity,"Runtime cannot restore snapshot host state");
        goto done;
    }
    if (memcmp(header+32,io->identity,64)) {
        status = result(RR_STATE_WRONG_IDENTITY,error,capacity,"Snapshot belongs to different media, firmware or RAM");
        goto done;
    }
    if (memcmp(header+96,io->compatibility,64)) {
        status = result(RR_STATE_INCOMPATIBLE,error,capacity,"Snapshot belongs to an incompatible runtime");
        goto done;
    }
    size = saved_core_size + saved_auxiliary_size;
    rollback_size = io->core_size + io->auxiliary_size;
    data = (unsigned char *)malloc(size);
    rollback = (unsigned char *)malloc(rollback_size);
    if (!data || !rollback) {
        status = result(RR_STATE_IO_ERROR,error,capacity,"Snapshot allocation failed");
        goto done;
    }
    if (fread(data,1,size,file)!=size || fgetc(file)!=EOF || ferror(file)) {
        result(status,error,capacity,"Truncated snapshot or unexpected trailing bytes");
        goto done;
    }
    hash = checksum(FNV_OFFSET,header,CHECKSUM_OFFSET);
    if (get64(header+CHECKSUM_OFFSET)!=checksum(hash,data,size)) {
        result(status,error,capacity,"Snapshot checksum mismatch");
        goto done;
    }
    if ((saved_auxiliary_size || io->auxiliary_size) && !io->validate_auxiliary(io->context,
            data+saved_core_size,saved_auxiliary_size)) {
        result(status,error,capacity,"Snapshot media or host state is no longer valid");
        goto done;
    }
    /* No guest/core mutation has occurred before this point. */
    if (!capture(io,rollback)) {
        status = result(RR_STATE_CALLBACK_ERROR,error,capacity,"Could not capture a rollback; game state unchanged");
        goto done;
    }
    applied = !(saved_auxiliary_size || io->auxiliary_size) || io->apply_auxiliary(io->context,
        data+saved_core_size,saved_auxiliary_size);
    if (applied && io->load_core(io->context,data,saved_core_size)) {
        status = result(RR_STATE_OK,error,capacity,"Game state loaded");
        goto done;
    }
    restored_aux = !io->auxiliary_size || io->apply_auxiliary(io->context,
        rollback+io->core_size,io->auxiliary_size);
    restored_core = io->load_core(io->context,rollback,io->core_size);
    if (!restored_aux || !restored_core)
        status = result(RR_STATE_ROLLBACK_ERROR,error,capacity,"Snapshot restore and rollback failed; stop the game");
    else
        status = result(RR_STATE_CALLBACK_ERROR,error,capacity,"Snapshot restore failed; previous game state recovered");
done:
    if (file) fclose(file);
    free(rollback); free(data);
    return status;
}
