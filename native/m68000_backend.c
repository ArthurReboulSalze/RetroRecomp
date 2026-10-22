#include "m68000_backend.h"
#include <string.h>
#include <assert.h>
static RrM68000Backend cpu;
static RrM68000Stats stats;
int rr_m68000_bind(const RrM68000Backend *backend) {
    if (!backend || !backend->init || !backend->reset || !backend->run ||
        !backend->wait || !backend->set_irq || !backend->get_irq) return 0;
    cpu = *backend;
    memset(&stats, 0, sizeof stats);
    return 1;
}
void rr_m68000_init(void) { assert(cpu.init); cpu.init(cpu.context); }
void rr_m68000_reset(void) { ++stats.resets; cpu.reset(cpu.context); }
int rr_m68000_run(unsigned clocks) {
    int elapsed = cpu.run(cpu.context, clocks);
    ++stats.run_calls;
    if (elapsed > 0) stats.clocks += (unsigned)elapsed;
    return elapsed;
}
void rr_m68000_wait(int clocks) {
    if (clocks > 0) stats.bus_wait_clocks += (unsigned)clocks;
    cpu.wait(cpu.context, clocks);
}
void rr_m68000_set_irq(unsigned level, unsigned asserted) {
    if (level > 7 || level == 0) return;
    if (asserted) ++stats.irq_assertions;
    cpu.set_irq(cpu.context, level, asserted != 0);
}
unsigned rr_m68000_get_irq(unsigned level) {
    return level && level <= 7 ? cpu.get_irq(cpu.context, level) : 0;
}
void rr_m68000_count_instruction(int native) {
    if (native) ++stats.native_instructions;
    else ++stats.interpreted_instructions;
}
void rr_m68000_count_native(unsigned count) { stats.native_instructions += count; }
const RrM68000Stats *rr_m68000_stats(void) { return &stats; }
