// The bus and DMA model of the Amiga's stage 7, in shadow (MIT, ours).
//
// Stage 7 (docs/UPGRADES.md, after 1.7.3) moves the Amiga's bus scheduling out of vAmiga's per-colour-clock loop: a per-line slot
// table of our own answers the CPU's bus waits, and the DMA devices catch up behind barriers. Its first checkpoints control nothing.
// Built with RR_AMIGA_SHADOW (the display self-test always, private reference players on request, never an export), vAmiga's Agnus
// calls the hooks below and the model computes beside it:
//   * at each line start, the line's table: refresh and bitplane slots certain, disk, audio and sprite slots conditional, from
//     DMACON and the line (our own rules) and from vAmiga's bitplane plan (read, as Agnus step 2 reads it);
//   * at each line end, the table against vAmiga's bus owners, slot by slot;
//   * at each CPU bus wait, the wait the table predicts against the wait vAmiga gave, and the path the model would take;
//   * the synchronisation points a CPU running a block with its own clock would meet, and any event that would have crossed one.
// Nothing here changes a value of the machine; the counters only say whether the table and the waits agree with vAmiga's, which
// is the reference, not whether either matches the hardware.
#pragma once

#include <cstddef>
#include <cstdint>

namespace vamiga {

class Agnus;

struct RrBus {
    // Hooks (vAmiga's Agnus, Moira's glue and Memory call them when RR_AMIGA_SHADOW is defined).
    static void reset(Agnus &agnus);
    static void lineStart(Agnus &agnus);
    static void planChanged(Agnus &agnus);
    static void dasChanged(Agnus &agnus);
    static void lineEnd(Agnus &agnus);
    static void cpuAccess(Agnus &agnus, uint32_t addr, int write);
    static void cpuDone(Agnus &agnus);
    static void busWaitStart(Agnus &agnus);
    static void busWaitEnd(Agnus &agnus, long long delay);
    static void ciaWait(Agnus &agnus);
    static void events(Agnus &agnus, long long cycle);

    // For the display self-test and the private census.
    static int fault;                       // a planted fault of the model (0: none), to show the comparison is not blind
    static uint64_t step;                   // the self-test's instruction index, for the access trace
    static uint64_t traceFrom, traceCount;  // print the CPU's bus waits of these instructions
    static uint64_t frameOwners;            // hash of every line's bus owners since the last take (the record's owner field)
    static uint64_t takeOwners() { const uint64_t h = frameOwners; frameOwners = 1469598103934665603ull; return h; }
    static size_t json(char *out, size_t size);
    static uint64_t mismatches();
};

}
