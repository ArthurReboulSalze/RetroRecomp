/* Local development payload; only user-supplied private bytes reach this file. */
#ifndef RR_X68000_PAYLOAD_H
#define RR_X68000_PAYLOAD_H
#include <stddef.h>
int rr_x68k_payload_prepare(const char *base,char *directory,size_t capacity);
void rr_x68k_payload_release(void);
#endif
