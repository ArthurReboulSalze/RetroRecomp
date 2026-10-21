/* Original Retro-Recomp private X68000 snapshot envelope, MIT. */
#ifndef RR_X68000_STATE_STORE_H
#define RR_X68000_STATE_STORE_H

#include <stdbool.h>
#include <stddef.h>

/* File bytes are canonical little endian; no host pointers are persisted.
 * The opaque core format is accepted only for the exact compatibility digest.
 * Identity is the exact media/firmware/RAM SHA-256; compatibility identifies
 * this core's complete state schema and generation. Both are 64 lower-case hex.
 *
 * Auxiliary data is caller-owned, bounded, pointer-free host state. Validation
 * MUST NOT mutate the machine. Apply is called before loading the core, so
 * mounted media can be reinstated before the controller state is restored.
 * A failed apply or core load rolls back both from a fresh in-memory snapshot.
 * core_size/auxiliary_size describe the CURRENT machine for save/rollback.
 * Loading uses bounded sizes from the saved envelope: ejecting/mounting disks
 * can legitimately change the core's serialized buffer count. Load/apply and
 * validate callbacks must accept their supplied size, not assume current sizes.
 * Call these functions only between guest frames, on the emulation thread. */
typedef struct RRStateIO {
    void *context;
    const char *identity;
    const char *compatibility;
    size_t core_size;
    size_t auxiliary_size;
    bool (*save_core)(void *context, void *data, size_t size);
    bool (*load_core)(void *context, const void *data, size_t size);
    bool (*capture_auxiliary)(void *context, void *data, size_t size);
    bool (*validate_auxiliary)(void *context, const void *data, size_t size);
    bool (*apply_auxiliary)(void *context, const void *data, size_t size);
} RRStateIO;

typedef enum RRStateResult {
    RR_STATE_OK = 0,
    RR_STATE_IO_ERROR,
    RR_STATE_INVALID,
    RR_STATE_WRONG_IDENTITY,
    RR_STATE_INCOMPATIBLE,
    RR_STATE_CALLBACK_ERROR,
    RR_STATE_ROLLBACK_ERROR
} RRStateResult;

#define RR_X68K_STATE_MAX_CORE (64u * 1024u * 1024u)
#define RR_X68K_STATE_MAX_AUXILIARY (32u * 1024u * 1024u)

/* Paths are UTF-8 on both Windows and Linux. A successful save atomically
 * replaces the previous slot only after the temporary file is committed.
 * A failed save leaves the previous slot intact. Missing parent directories
 * are not created. Non-OK load never reports success after a partial restore;
 * RR_STATE_ROLLBACK_ERROR is fatal and the caller must stop guest execution.
 * Errors are short English UI messages; error may be NULL when capacity = 0. */
RRStateResult rr_x68k_state_save(const char *path, const RRStateIO *io,
                               char *error, size_t capacity);
RRStateResult rr_x68k_state_load(const char *path, const RRStateIO *io,
                               char *error, size_t capacity);

#endif
