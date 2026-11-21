#ifndef RETRO_RECOMP_STATE_FILE_H
#define RETRO_RECOMP_STATE_FILE_H
/* A quick state's file around the shared envelope (state_envelope.h): its build binding, the machine's own consistency check,
 * the atomic save and the whole read. Machine-neutral, MIT, Retro-Recomp. Compiled with platform_io.c.
 *
 * The body the envelope carries is (1) the build binding, `binding_size` bytes the converter writes for one build (the state's
 * layout, the firmware, the model...), compared and never applied, then (2) the machine's own body (`envelope.body`). The bytes
 * are those the MSX writes by hand today (msx_machine/msx_state_file.inc), so a machine moving here keeps its files.
 *
 * Loading checks the whole state on the machine's scratch copies first, then applies it, so a refused load changes nothing:
 *   RR_STATE_MISSING       no file;
 *   RR_STATE_INCOMPATIBLE  a whole, undamaged state of another schema, model, game or build (the binding differs);
 *   RR_STATE_INVALID       not a state, cut, damaged (the CRC), a field out of its bounds, longer than `capacity`, or refused by
 *                          the machine's consistency check (`consistent`, called once its body has been decoded in the check
 *                          pass, before anything is applied: for example the cycle within one line of the machine's);
 *   RR_STATE_IO_ERROR      the file exists but could not be read, or the state could not be written.
 * Saving writes `<path>.<process>.tmp` beside the file, flushes it and only then puts it in the file's place: a save that fails
 * at any point leaves the old file whole, and removes its temporary.
 *
 * One state is read or written at a time (the body reaches its file through a static). The folder of `path` is the caller's. */
#include <stdio.h>
#include <stdlib.h>
#include <wchar.h>
#include "state_envelope.h"
#include "platform_io.h"

typedef struct {
    RetroStateEnvelope envelope;     /* magic, schema, machine (model), identity, and the machine's body */
    const uint8_t *binding;          /* the build binding, compared and never applied (NULL with binding_size 0: none) */
    size_t binding_size;
    bool (*consistent)(void);        /* the machine's check of what its body decoded (NULL: none); false refuses the load */
    size_t capacity;                 /* the largest state of this machine, the envelope's header included */
} RetroStateFile;

static const RetroStateFile *rr_state_file_current;
static bool rr_state_file_binding_differs;

static void rr_state_file_body(RetroStateIO *io)
{
    const RetroStateFile *f = rr_state_file_current;
    bool differs = false;
    for (size_t i = 0; i < f->binding_size; ++i)
        if ((uint8_t)rr_state_word(io, f->binding[i], 1, 255) != f->binding[i]) differs = true;
    if (!io->ok) return;
    if (differs) { rr_state_file_binding_differs = true; io->ok = false; return; }
    f->envelope.body(io);
    if (io->mode == RR_STATE_CHECK && io->ok && f->consistent && !f->consistent()) io->ok = false;
}

/* The state in memory: RR_STATE_OK and its size, or RR_STATE_INVALID (the machine refused, or `capacity` is too small). */
static int rr_state_file_encode(const RetroStateFile *f, uint8_t *data, size_t capacity, size_t *size)
{
    RetroStateEnvelope e = f->envelope;
    e.body = rr_state_file_body;
    rr_state_file_current = f;
    return rr_state_envelope_write(&e, data, capacity, size);
}

/* A state read whole from memory: checked, then applied only when every check passed (the codes above). */
static int rr_state_file_decode(const RetroStateFile *f, uint8_t *data, size_t size)
{
    RetroStateEnvelope e = f->envelope;
    e.body = rr_state_file_body;
    rr_state_file_current = f;
    rr_state_file_binding_differs = false;
    int result = rr_state_envelope_read(&e, data, size);
    /* The body runs only on a whole state whose length and CRC are right: a binding that differs there is another build's. */
    if (result == RR_STATE_INVALID && rr_state_file_binding_differs) result = RR_STATE_INCOMPATIBLE;
    return result;
}

static int rr_state_file_save(const RetroStateFile *f, const wchar_t *path)
{
    uint8_t *data = (uint8_t *)malloc(f->capacity);
    if (!data) return RR_STATE_IO_ERROR;
    size_t size = 0;
    if (rr_state_file_encode(f, data, f->capacity, &size) != RR_STATE_OK) { free(data); return RR_STATE_INVALID; }
    wchar_t temporary[32768];
    swprintf(temporary, 32768, L"%ls.%lu.tmp", path, rr_process_id());
    FILE *file = rr_fopen(temporary, L"wb");
    bool ok = file && fwrite(data, size, 1, file) == 1;
    if (ok) ok = rr_flush_file(file) != 0;
    if (file && fclose(file) != 0) ok = false;
    free(data);
    if (ok) ok = rr_replace(temporary, path) != 0;
    if (!ok && file) rr_remove(temporary);
    return ok ? RR_STATE_OK : RR_STATE_IO_ERROR;
}

static int rr_state_file_load(const RetroStateFile *f, const wchar_t *path)
{
    FILE *file = rr_fopen(path, L"rb");
    if (!file) return rr_exists(path) ? RR_STATE_IO_ERROR : RR_STATE_MISSING;
    uint8_t *data = (uint8_t *)malloc(f->capacity);
    if (!data) { fclose(file); return RR_STATE_IO_ERROR; }
    size_t size = fread(data, 1, f->capacity, file);
    int extra = fgetc(file);
    bool read_ok = !ferror(file);
    fclose(file);
    int result = !read_ok ? RR_STATE_IO_ERROR : extra != EOF ? RR_STATE_INVALID : rr_state_file_decode(f, data, size);
    free(data);
    return result;
}
#endif
