/* The optional function-differential harness cannot safely enter a PC-driven
 * backend through a host-stack ABI. Production uses the banked loop directly. */
#include <stdio.h>
#include <stdlib.h>
#include "sms_runtime.h"
void call_by_address(uint16_t addr) {
    fprintf(stderr, "[banked] function-form diagnostic unsupported at %04X; use CPU/frame differential checks\n", addr);
    exit(2);
}
