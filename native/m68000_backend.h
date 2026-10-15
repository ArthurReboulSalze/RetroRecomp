/* RetroRecomp MC68000 board/CPU boundary. Original contributions: MIT. */
#ifndef RR_M68000_BACKEND_H
#define RR_M68000_BACKEND_H
#include <stdint.h>
#include <stddef.h>

enum { RR_M68000_CODE_CART=1, RR_M68000_CODE_BIOS=2, RR_M68000_CODE_RAM=3 };
typedef struct {
    uint32_t region, physical_offset, available_bytes;
    unsigned mutable_code;
} RrM68000CodeLocation;
/* CPU semantics do not contain a console's memory map or master clock. */
typedef struct {
    void *context;
    uint8_t (*read8)(void *, uint32_t);
    uint16_t (*read16)(void *, uint32_t);
    void (*write8)(void *, uint32_t, uint8_t);
    void (*write16)(void *, uint32_t, uint16_t);
    int (*interrupt_ack)(void *, unsigned);
    void (*external_reset)(void *);
    int (*code_location)(void *, uint32_t, RrM68000CodeLocation *);
} RrM68000Bus;

typedef struct {
    void *context;
    void (*init)(void *);
    void (*reset)(void *);
    int (*run)(void *, unsigned); /* Retired CPU clocks, including bus waits. */
    void (*wait)(void *, int);
    void (*set_irq)(void *, unsigned, unsigned);
    unsigned (*get_irq)(void *, unsigned);
} RrM68000Backend;

typedef struct {
    uint64_t native_instructions, interpreted_instructions;
    uint64_t run_calls, clocks, bus_wait_clocks, resets, irq_assertions;
} RrM68000Stats;

/* Select only while the machine is stopped, before init/reset. */
int rr_m68000_bind(const RrM68000Backend *backend);
void rr_m68000_init(void);
void rr_m68000_reset(void);
int rr_m68000_run(unsigned clocks);
void rr_m68000_wait(int clocks);
void rr_m68000_set_irq(unsigned level, unsigned asserted);
unsigned rr_m68000_get_irq(unsigned level);
void rr_m68000_count_instruction(int native);
const RrM68000Stats *rr_m68000_stats(void);

#endif
