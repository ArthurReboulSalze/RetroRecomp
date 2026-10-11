#ifndef RR_MD_VDP_READ_H
#define RR_MD_VDP_READ_H
#include <stdint.h>
/* One pointer-free prefetch request/buffer. State: 0 idle, 1 awaiting an
 * first external slot, 3 awaiting the second VRAM byte, 2 latched.
 * The command/address belong to the request,
 * not to a later control-port write. No invented fixed pipeline delay. */
typedef struct RrMdVdpRead {
    uint32_t address, value, code, state;
} RrMdVdpRead;
#endif
