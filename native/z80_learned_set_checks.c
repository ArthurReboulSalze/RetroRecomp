/* Checks of native/z80_learned_set.h, the windows a headless run learns: no bound, first-seen order, each window once.
 * tools/z80_learned_set_selftest.py builds and runs it. MIT, Retro-Recomp. Never part of a game. */
#include "z80_learned_set.h"

static int failures;
#define REQUIRE(cond, text) do { if (!(cond)) { printf("FAIL: %s\n", text); ++failures; } } while (0)

int main(void)
{
    static RrLearnedSet set;
    /* The old bound was 4,096: go far past it, in a scattered order, with every window offered three times. */
    const uint32_t total = 200000;
    uint32_t new_windows = 0;
    for (int round = 0; round < 3; ++round)
        for (uint32_t i = 0; i < total; ++i) {
            const uint32_t word = (i * 2654435761u) ^ 0x5A5A0000u;            /* distinct for distinct i */
            const int added = rr_learned_add(&set, word);
            if (round == 0) { REQUIRE(added == 1, "a new window is added"); new_windows += (uint32_t)added; }
            else REQUIRE(added == 0, "a window seen before is not added again");
        }
    REQUIRE(new_windows == total && set.count == total, "every distinct window is kept, far past 4,096");
    REQUIRE(set.count > 4096 * 40, "the count is the real one, not a cap");
    /* First-seen order: what the headless mains write. */
    int ordered = 1;
    for (uint32_t i = 0; i < total; ++i)
        if (set.words[i] != ((i * 2654435761u) ^ 0x5A5A0000u)) { ordered = 0; break; }
    REQUIRE(ordered, "the windows stay in the order they were first seen");
    /* The words that collide in the table's hash (the same low bits) are all kept. */
    static RrLearnedSet crowd;
    for (uint32_t i = 0; i < 5000; ++i) REQUIRE(rr_learned_add(&crowd, i << 16), "windows that share their low bits are kept");
    REQUIRE(crowd.count == 5000, "5,000 windows that share their low bits are 5,000");
    REQUIRE(rr_learned_add(&crowd, 0) == 0 && rr_learned_add(&crowd, 4999u << 16) == 0, "they are found again");
    printf(failures ? "learned set: %d failed\n" : "learned set: ok (%u windows)\n", failures ? failures : (int)set.count, set.count);
    return failures ? 1 : 0;
}
