/* Retro-Recomp: unpackers of the formats resload_Decrunch provides (MIT, written from the formats' descriptions).
 *
 * Provided: Rob Northen ProPack method 1 ("RNC\1"), checked against the CRC-16 of the packed and unpacked data that its
 * header carries. Recognised but not unpacked yet (the caller refuses with the name): RNC method 2, Imploder ("IMP!",
 * "ATN!"), TPWM, Crunch-Mania ("CrM!", "CrM2", "Crm!", "Crm2").
 */
#ifndef RR_DECRUNCH_H
#define RR_DECRUNCH_H

#include <stddef.h>
#include <stdint.h>

enum { RR_PACK_NONE = 0, RR_PACK_RNC1, RR_PACK_RNC2, RR_PACK_IMP, RR_PACK_TPWM, RR_PACK_CRM };

/* The format of a buffer that starts with `head` (at least 4 bytes), and its name for messages. */
int rr_pack_format(const uint8_t *head, size_t size);
const char *rr_pack_name(int format);

/* The unpacked size the header states, or 0 when it is not known without unpacking. */
uint32_t rr_pack_unpacked_size(const uint8_t *data, size_t size);

/* Unpacks `data` into `out` (capacity `cap`). Returns the unpacked size, or 0 on error with `why` set. */
uint32_t rr_unpack(const uint8_t *data, size_t size, uint8_t *out, size_t cap, const char **why);

#endif
