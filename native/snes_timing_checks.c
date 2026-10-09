/* Authored clock expectations, independent of the CPU reference interpreter. */
#include <stdint.h>
#include <stdio.h>
#include "apu_frame_clock.h"
#define REQUIRE(x) do { ++checks; if (!(x)) { fprintf(stderr, "line %u: %s\n", __LINE__, #x); return 1; } } while (0)
int main(void) {
    unsigned checks = 0;
    RtlApuFrameClock clock = {0};
    uint64_t master = 0, previous = 0;
    REQUIRE(RR_SN_LINES == (RR_SN_PAL ? 312 : 262));
    REQUIRE(RR_SN_FRAME_MASTER == (RR_SN_PAL ? 425568 : 357368));
    for (unsigned n = 0; n < 6000; ++n) {
        rtl_apu_clock_begin(&clock, master);
        REQUIRE(rtl_apu_clock_now(&clock, master) == previous);
        REQUIRE(rtl_apu_clock_now(&clock, master + 1364) >= previous);
        master += RR_SN_FRAME_MASTER;
        previous = rtl_apu_clock_finish(&clock, master);
#if RR_SN_PAL
        REQUIRE(previous == master * 1025280ull / 21281370ull);
        REQUIRE(clock.next_remainder == master * 1025280ull % 21281370ull);
        REQUIRE(clock.last_master == 425568);
#else
        REQUIRE(previous == (n + 1ull) * 17088ull);
#endif
    }
    /* A long loader is charged for every elapsed field, not one host call. */
    rtl_apu_clock_begin(&clock, master);
    master += RR_SN_FRAME_MASTER * 7 + 123;
    previous = rtl_apu_clock_finish(&clock, master);
#if RR_SN_PAL
    REQUIRE(previous == master * 1025280ull / 21281370ull);
    REQUIRE(clock.last_master == 425568 * 7ull + 123);
#else
    REQUIRE(previous == 6000ull * 17088 + (357368ull * 7 + 123) * 17088 / 357368);
#endif
    /* A short WAI iteration still advances a full audio field. */
    rtl_apu_clock_begin(&clock, master);
    uint64_t short_end = rtl_apu_clock_finish(&clock, master + 10);
    REQUIRE(short_end > previous);
#if RR_SN_PAL
    REQUIRE(short_end == (master + 425568) * 1025280ull / 21281370ull);
#else
    REQUIRE(short_end == previous + 17088);
#endif
    clock = (RtlApuFrameClock){0};
    rtl_apu_clock_begin(&clock, 1234);
    REQUIRE(rtl_apu_clock_now(&clock, 0) == 0);  /* reset inside first iteration */
    printf("{\"standard\":\"%s\",\"checks\":%u,\"passed\":true}\n", RR_SN_PAL ? "pal" : "ntsc", checks);
    return 0;
}
