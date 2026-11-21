/* The disc a PC Engine CD game holds: appended to the game's own executable and read in place (docs/PC_ENGINE_CD.md), the way the PlayStation's game holds its disc.
 * After the disc comes a trailer of 88 bytes: the disc's SHA-256 as 64 lower-case hex digits, its offset and its length in the file (64-bit, little-endian), then
 * the 8 bytes "RRPCECD1". Original RetroRecomp code: MIT. */
#ifndef RR_PCECD_PACK_H
#define RR_PCECD_PACK_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
#define RR_PCECD_TRAILER 88u
/* The running executable's path in UTF-8 and the disc it holds: 1 when it holds one. `sha256` receives 64 digits and a terminator. */
int rr_pcecd_find_embedded(char *path, size_t path_size, uint64_t *offset, uint64_t *length, char sha256[65]);
#ifdef __cplusplus
}
#endif
#endif
