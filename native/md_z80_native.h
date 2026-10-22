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
enum { RR_MD_Z80_BASE, RR_MD_Z80_CB, RR_MD_Z80_ED, RR_MD_Z80_INDEX, RR_MD_Z80_DCB };
void rr_md_z80_resume(z80 *z, uint8_t opcode, unsigned family, uint16_t parameter);
void rr_md_z80_fetch_fallback(void);
void rr_md_z80_step(z80 *z);
void rr_md_z80_begin(z80 *z);
void rr_md_z80_tick(unsigned cycles);
void machine_z80_boundary(void);
void machine_z80_instruction_boundary(void);
/* Z80 bus cycles: own RAM ($0000-$3FFF) is private to the sound CPU. */
void machine_z80_access(uint16_t address);
void machine_z80_write(uint16_t address);
void machine_z80_fallback(void);
/* Retired-instruction evidence, restored with the CPU when a deferred
 * rendezvous is replayed (see md_z80_bus.inc). */
typedef struct {
    uint64_t native_ops, fallback_ops, native_cycles, fallback_cycles, timing_misses;
    unsigned long phase_origin, phase_cycles;
} RrMdZ80Evidence;
void rr_md_z80_evidence_save(RrMdZ80Evidence *evidence);
void rr_md_z80_evidence_load(const RrMdZ80Evidence *evidence);
void rr_md_z80_sync(z80 *z);
uint64_t rr_md_z80_timing_misses(void);
void rr_md_z80_reset_evidence(void);
void rr_md_z80_irq_fallback(unsigned long cycles);
uint64_t rr_md_z80_native_opcodes(void);
uint64_t rr_md_z80_fallback_opcodes(void);
uint64_t rr_md_z80_native_cycles(void);
uint64_t rr_md_z80_fallback_cycles(void);
void rr_md_z80_report(FILE *file);
#endif
