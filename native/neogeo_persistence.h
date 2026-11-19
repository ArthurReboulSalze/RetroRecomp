/* Ordinary MVS saves, separate from frame snapshots. Original work: MIT. */
#ifndef RR_NEOGEO_PERSISTENCE_H
#define RR_NEOGEO_PERSISTENCE_H
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <wchar.h>
bool rr_ng_persist_begin(bool enabled);
void rr_ng_persist_activity(bool active);
void rr_ng_persist_after_state(void);
bool rr_ng_persist_close(void);
/* Multiplayer: false for a guest (it plays on the loaded save and writes nothing) and for silent frames. */
void rr_ng_persist_writes(bool allowed);
/* Multiplayer (session ABI 8): this PC's save image (NULL out: only its size), and the host's, put in memory only. */
size_t rr_ng_session_save(void *out,size_t capacity);
bool rr_ng_session_save_put(const void *in,size_t size);
bool rr_ng_persist_path(wchar_t *path,size_t capacity);
void rr_ng_persist_report(FILE *file);
#endif
