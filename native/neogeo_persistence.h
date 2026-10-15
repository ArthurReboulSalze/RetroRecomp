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
bool rr_ng_persist_path(wchar_t *path,size_t capacity);
void rr_ng_persist_report(FILE *file);
#endif
