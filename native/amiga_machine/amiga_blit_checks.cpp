// The Blitter's specialised routines against vAmiga's microprogram, slot by slot (MIT; tools/amiga_blitter_selftest.py builds it against the adapted vAmiga, never into a game).
//
// A blit of a shape, from a random state, runs twice on a machine that is not powered on: through the microprogram's table and through the shape's routine, with the same random memory
// and the same random bus from slot to slot (who holds it, the CPU's claim, the Blitter's priority, Blitter DMA going off and on). After every slot the Blitter's whole snapshot, the slot's
// bus record and the bus counters must be equal; at the end also Agnus, Paula and chip RAM. Some blits have BLTCON0 or BLTCON1 changed on the way. A wrong routine must be seen.
#include "vaconfig.h"
#include "Emulator.h"
#include "Amiga.h"
#include "RrBlitterShape.h"

#include <cstdio>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <vector>

typedef void (*RrCode)(void *);
typedef struct { uint16_t con0, con1; RrCode run; } RrShape;
extern "C" const RrShape rr_amiga_blit_shapes[];
extern "C" const unsigned rr_amiga_blit_shape_count;

namespace vamiga {

struct RrBlitChecks {
    Emulator emu;
    Amiga *amiga = nullptr;
    Blitter *blitter = nullptr;
    Agnus *agnus = nullptr;
    std::vector<u8> ram, agnus0, paula0, agnus1, paula1, ram1, buffer;
    uint64_t slots = 0, differences = 0;
    static inline RrCode answer = nullptr;

    struct Random {
        uint64_t s;
        explicit Random(uint64_t seed) : s(seed * 0x9e3779b97f4a7c15ull + 0x1234567) {}
        uint32_t next() { s ^= s << 13; s ^= s >> 7; s ^= s << 17; return (uint32_t)(s >> 16); }
    };

    static RrCode begin(u16, u16, u32) { return answer; }

    void start() {
        emu.initialize();
        emu.set(ConfigScheme::A500_ECS_1MB);
        emu.set(Opt::MEM_CHIP_RAM, 512);
        emu.set(Opt::MEM_SLOW_RAM, 0);
        amiga = &emu.rrMain();
        agnus = &amiga->agnus;
        blitter = &amiga->agnus.blitter;
        rr_blit_begin = begin;
        ram.resize((size_t)amiga->mem.chipRamSize());
        Random r(1);
        for (auto &byte : ram) byte = (u8)r.next();
        buffer.resize(4 * 1024 * 1024);
        agnus0.resize((size_t)agnus->save(buffer.data()));
        memcpy(agnus0.data(), buffer.data(), agnus0.size());
        paula0.resize((size_t)amiga->paula.save(buffer.data()));
        memcpy(paula0.data(), buffer.data(), paula0.size());
    }

    // One run of a blit; `step` is folded into a hash, slot by slot.
    uint64_t run(uint16_t con0, uint16_t con1, uint64_t seed, RrCode routine, bool change_midway, std::vector<u8> &agnus_after, std::vector<u8> &paula_after, std::vector<u8> &ram_after) {
        agnus->load(agnus0.data());
        amiga->paula.load(paula0.data());
        memcpy(amiga->mem.chip, ram.data(), ram.size());
        agnus->stats.usage[BUS_BLITTER] = 0;        // Not part of a snapshot.
        Random r(seed);
        Blitter &b = *blitter;
        const u32 mask = (u32)ram.size() - 1;
        b.bltcon0 = (u16)((r.next() & 0xf000) | con0);
        b.bltcon1 = (u16)((r.next() & 0xf000) | con1);
        b.bltapt = r.next() & mask & ~1u;
        b.bltbpt = r.next() & mask & ~1u;
        b.bltcpt = r.next() & mask & ~1u;
        b.bltdpt = r.next() & mask & ~1u;
        b.bltamod = (i16)(r.next() & 0x7ffe) - 0x4000;
        b.bltbmod = (i16)(r.next() & 0x7ffe) - 0x4000;
        b.bltcmod = (i16)(r.next() & 0x7ffe) - 0x4000;
        b.bltdmod = (i16)(r.next() & 0x7ffe) - 0x4000;
        b.bltafwm = (u16)r.next();
        b.bltalwm = (u16)r.next();
        b.bltsizeH = (u16)(1 + r.next() % 7);
        b.bltsizeV = (u16)(1 + r.next() % 5);
        b.anew = (u16)r.next();
        b.bnew = (u16)r.next();
        b.chold = (u16)r.next();
        b.aold = (u16)r.next();
        b.bold = (u16)r.next();
        b.ahold = (u16)r.next();
        b.bhold = (u16)r.next();
        b.dhold = (u16)r.next();
        agnus->dmacon = DMAEN | BLTEN;
        answer = routine;
        b.prepareBlit();
        b.beginSlowCopyBlit();
        const unsigned change_at = change_midway ? 1 + r.next() % 40 : ~0u;
        uint64_t hash = 0xcbf29ce484222325ull;
        auto fold = [&hash](const void *data, size_t size) {
            auto *p = static_cast<const u8 *>(data);
            for (size_t i = 0; i < size; i++) hash = (hash ^ p[i]) * 0x100000001b3ull;
        };
        for (unsigned slot = 0; b.running && slot < 20000; slot++) {
            agnus->pos.h = (isize)(r.next() % 226);
            const uint32_t bus = r.next();
            agnus->busOwner[agnus->pos.h] = bus & 3 ? BusOwner::NONE : static_cast<BusOwner>(1);
            agnus->setBLS((bus & 28) == 0);
            agnus->dmacon = (u16)(DMAEN | ((bus & 0x3e0) ? BLTEN : 0) | ((bus & 0xc00) ? 0 : BLTPRI));
            if (slot == change_at) {
                if (bus & 0x1000) b.bltcon0 ^= (u16)(1 << (r.next() % 12));
                else b.bltcon1 ^= (u16)(1 << (1 + r.next() % 4));
            }
            b.serviceEvent(BLT_COPY_SLOW);
            slots++;
            fold(buffer.data(), (size_t)b.save(buffer.data()));
            fold(&agnus->busOwner[agnus->pos.h], sizeof agnus->busOwner[0]);
            fold(&agnus->busAddr[agnus->pos.h], sizeof agnus->busAddr[0]);
            fold(&agnus->busData[agnus->pos.h], sizeof agnus->busData[0]);
            fold(&agnus->stats.usage[BUS_BLITTER], sizeof agnus->stats.usage[BUS_BLITTER]);
        }
        const bool finished = !b.running;
        fold(&finished, 1);
        agnus_after.resize(agnus0.size());
        memcpy(agnus_after.data(), buffer.data(), (size_t)agnus->save(buffer.data()));
        paula_after.resize(paula0.size());
        memcpy(paula_after.data(), buffer.data(), (size_t)amiga->paula.save(buffer.data()));
        ram_after.assign(amiga->mem.chip, amiga->mem.chip + ram.size());
        return hash;
    }

    bool same(uint16_t con0, uint16_t con1, uint64_t seed, RrCode routine, bool change_midway) {
        std::vector<u8> a2, p2, r2;
        const uint64_t table = run(con0, con1, seed, nullptr, change_midway, agnus1, paula1, ram1);
        const uint64_t shape = run(con0, con1, seed, routine, change_midway, a2, p2, r2);
        return table == shape && a2 == agnus1 && p2 == paula1 && r2 == ram1;
    }

    // A routine that writes a wrong word: the check must see it.
    static void wrong(void *p) {
        auto &b = *static_cast<Blitter *>(p);
        b.rrRun<0x9f0, 0x00>();
        b.dhold ^= 0x0010;
    }
};

}

using vamiga::RrBlitChecks;

int main(int argc, char **argv) {
    const int blits = argc > 1 ? atoi(argv[1]) : 8;
    static RrBlitChecks checks;
    try {
        checks.start();
    } catch (std::exception &e) {
        fprintf(stderr, "The machine could not start: %s\n", e.what());
        return 3;
    }
    uint64_t scenarios = 0, midway = 0;
    for (unsigned n = 0; n < rr_amiga_blit_shape_count; n++) {
        const RrShape &shape = rr_amiga_blit_shapes[n];
        for (int k = 0; k < blits; k++) {
            const bool change = k % 4 == 3;
            scenarios++;
            midway += change;
            if (!checks.same(shape.con0, shape.con1, ((uint64_t)shape.con0 << 24) ^ ((uint64_t)shape.con1 << 40) ^ (uint64_t)k, shape.run, change)) {
                checks.differences++;
                if (checks.differences <= 20) printf("differ %03x %02x blit %d%s\n", shape.con0, shape.con1, k, change ? " (changed on the way)" : "");
            }
        }
    }
    // The harness sees a wrong routine.
    unsigned wrong_seen = 0;
    for (int k = 0; k < 16; k++) wrong_seen += !checks.same(0x9f0, 0x00, 1000 + (uint64_t)k, RrBlitChecks::wrong, false);
    // A routine that is not this blit's shape leaves it at its first slot, and the blit is still right.
    const uint64_t before = vamiga::rr_blit_left_midway;
    const bool other_shape_same = checks.same(0x9f0, 0x00, 77, rr_amiga_blit_shape_count ? (rr_amiga_blit_shapes[0].con0 == 0x9f0 && !rr_amiga_blit_shapes[0].con1 ? rr_amiga_blit_shapes[1].run : rr_amiga_blit_shapes[0].run) : nullptr, false);
    const uint64_t left = vamiga::rr_blit_left_midway - before;
    printf("{\"shapes\":%u,\"blits\":%llu,\"changed_on_the_way\":%llu,\"slots\":%llu,\"differ\":%llu,\"wrong_routine_seen\":%u,\"other_shape_same\":%s,\"other_shape_left\":%llu}\n",
           rr_amiga_blit_shape_count, (unsigned long long)scenarios, (unsigned long long)midway, (unsigned long long)checks.slots, (unsigned long long)checks.differences, wrong_seen,
           other_shape_same ? "true" : "false", (unsigned long long)left);
    fflush(stdout);
    std::_Exit(checks.differences || wrong_seen < 8 || !other_shape_same || !left ? 1 : 0);
}
