#ifndef RR_MD_Z80_NATIVE_H
#define RR_MD_Z80_NATIVE_H
#include <stdint.h>
#include <stdio.h>
#include "z80.h"
#define RR_MD_Z80_VARIANT_LIMIT 32768
typedef struct {
    uint8_t mask, bytes[4];
    void (*run)(z80 *);
} RrMdZ80Body;
const RrMdZ80Body *rr_md_z80_bodies(uint16_t pc, unsigned *count);
int rr_md_z80_peek(uint16_t pc, uint8_t *value);
int rr_md_z80_force_reference(void);
int rr_md_z80_probe(void);
void rr_md_z80_capture_driver(void);
void rr_md_z80_finish(z80 *z);
void rr_md_z80_halt(z80 *z);
void rr_md_z80_step(z80 *z);
void rr_md_z80_reset_evidence(void);
void rr_md_z80_irq_fallback(unsigned long cycles);
uint64_t rr_md_z80_native_opcodes(void);
uint64_t rr_md_z80_fallback_opcodes(void);
uint64_t rr_md_z80_native_cycles(void);
uint64_t rr_md_z80_fallback_cycles(void);
void rr_md_z80_report(FILE *file);
#endif
