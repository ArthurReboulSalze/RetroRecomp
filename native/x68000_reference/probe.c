/* Original RetroRecomp reference instrumentation, MIT. */
#include "probe.h"

#include <string.h>
#include "m68000/musashi/m68k.h"

static uint64_t rr_elapsed_usec;

void rr_x68k_get_cpu(uint32_t regs[18])
{
    unsigned i;
    if (!regs)
        return;
    regs[0] = m68k_get_reg(NULL, M68K_REG_PC);
    regs[1] = m68k_get_reg(NULL, M68K_REG_SR);
    for (i = 0; i < 8; ++i) {
        regs[2 + i] = m68k_get_reg(NULL, (m68k_register_t)(M68K_REG_D0 + i));
        regs[10 + i] = m68k_get_reg(NULL, (m68k_register_t)(M68K_REG_A0 + i));
    }
}

void rr_x68k_set_clock(uint64_t simulated_usec)
{
    rr_elapsed_usec = simulated_usec;
}

time_t rr_x68k_time(time_t *result)
{
    const time_t value = (time_t)(UINT64_C(946684800) + rr_elapsed_usec / UINT64_C(1000000));
    if (result)
        *result = value;
    return value;
}

struct tm *rr_x68k_localtime(const time_t *value)
{
    static struct tm calendar;
    if (!value)
        return NULL;
#if defined(_WIN32)
    if (gmtime_s(&calendar, value) != 0)
        return NULL;
#else
    if (!gmtime_r(value, &calendar))
        return NULL;
#endif
    return &calendar;
}
