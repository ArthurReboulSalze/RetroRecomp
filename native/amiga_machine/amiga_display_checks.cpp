// Agnus and Denise, recorded (MIT; tools/amiga_display_selftest.py builds it against the adapted vAmiga, never into a game).
//
// A scenario of the self-test is a small machine of its own: a boot ROM, chip RAM with a 68000 program, bitmaps, sprites and a Copper
// list, all authored by the tool (no ROM image, no Kickstart, no disk). The machine is configured as an export's session is, powers on
// that ROM, and runs the program frame after frame. The program sets up a display and then hammers it: register writes, chip RAM
// writes into the displayed bitmap, reads of VHPOSR, CLXDAT, DMACONR and of unmapped memory, blits, delays.
//
// What is recorded, so that two builds (vAmiga's paths, and later the fast paths of Agnus and Denise) can be compared:
//   * at every instruction, before it runs (the instruction hook a native step uses, returning "not handled"): Agnus's clock and beam
//     position and the 68000's registers, so a difference in a bus wait or a read value is seen at the instruction that shows it;
//   * at every frame's end: the snapshot bytes of Agnus, Denise, Paula, both CIAs and the CPU, all of chip and slow RAM, the frame's
//     sound, CLXDAT, and every row of vAmiga's texture.
// A fault can be injected (`--fault ram|clock INDEX`): the comparison of the tool must see it. Text lines of the instructions around a
// difference come with `--trace FROM COUNT`. `--per-slot` runs every line's bitplane slots on vAmiga's events and every line pass on
// vAmiga's own, and every disk event on vAmiga's scheduler (Agnus step 2, Denise step 3 and stage 7's idle-disk catch-up off;
// `--disk-fault 1` loses one held-back disk event, which the comparison must see); the summary line counts the lines batched, on events and given back midway, and
// the visible lines passed in one loop and on vAmiga's pass. The records show that two runs agree with each other, not
// that either matches the hardware.
//
// Built with RR_AMIGA_SHADOW (the self-test always does), stage 7's bus model runs in shadow (amiga_bus.h): each frame's record also
// holds a hash of every line's bus owners, the summary line carries the model's comparison with vAmiga (`bus`, `bus_mismatches`),
// `--shadow-fault N` plants a fault in the model (the comparison must see it) and `--access-trace FROM COUNT` prints the CPU's bus
// waits of those instructions with the path the model would take.
#include "vaconfig.h"
#include "Emulator.h"
#include "Amiga.h"

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <exception>
#include <string>
#include <vector>

namespace vamiga::moira { extern bool (*rr_moira_native)(Moira &, u32 pc, u16 opcode); }

namespace vamiga {

static uint64_t fnv(uint64_t h, const void *data, size_t n) {
    const uint8_t *p = static_cast<const uint8_t *>(data);
    for (size_t i = 0; i < n; i++) { h ^= p[i]; h *= 1099511628211ull; }
    return h;
}
static constexpr uint64_t BASIS = 1469598103934665603ull;

struct RrDisplayChecks {
    Emulator emu;
    Amiga *amiga = nullptr;
    std::vector<uint64_t> steps;                 // one hash per instruction
    std::vector<uint8_t> buffer;
    uint64_t fault_at = ~0ull;
    int fault_kind = 0;                          // 1: a bit of chip RAM flipped, 2: one extra colour clock
    uint64_t trace_from = ~0ull, trace_count = 0;
    uint32_t fault_address = 0;
    uint64_t dump_frame = ~0ull;
    const char *dump_path = nullptr;

    static inline RrDisplayChecks *self = nullptr;

    static bool hook(moira::Moira &cpu, u32 pc, u16 opcode) {
        RrDisplayChecks &c = *self;
        Agnus &agnus = c.amiga->agnus;
        struct { uint64_t clock; int32_t v, h; uint32_t pc, d[8], a[8]; uint16_t sr, op; } state{};
        state.clock = (uint64_t)agnus.clock;
        state.v = (int32_t)agnus.pos.v;
        state.h = (int32_t)agnus.pos.h;
        state.pc = pc;
        state.op = opcode;
        state.sr = cpu.getSR();
        for (int i = 0; i < 8; i++) { state.d[i] = cpu.getD(i); state.a[i] = cpu.getA(i); }
        const uint64_t index = c.steps.size();
        c.steps.push_back(fnv(BASIS, &state, sizeof state));
        if (index - c.trace_from < c.trace_count) {
            printf("step %llu clock %llu v %d h %d pc %06x op %04x sr %04x d", (unsigned long long)index, (unsigned long long)state.clock, state.v, state.h, pc, opcode, state.sr);
            for (int i = 0; i < 8; i++) printf(" %08x", state.d[i]);
            printf(" a");
            for (int i = 0; i < 8; i++) printf(" %08x", state.a[i]);
            printf("\n");
        }
        if (index == c.fault_at) {
            if (c.fault_kind == 1) c.amiga->mem.chip[c.fault_address % (uint32_t)c.amiga->mem.chipRamSize()] ^= 0x10;
            if (c.fault_kind == 2) agnus.execute();
        }
        return false;                            // the instruction runs on Moira, as without the hook
    }

    uint64_t save_hash(CoreComponent &component) {
        const isize size = component.save(buffer.data());
        return fnv(BASIS, buffer.data(), (size_t)size);
    }
};

}

using vamiga::RrDisplayChecks;

static bool read_file(const char *path, std::vector<uint8_t> &out) {
    FILE *f = fopen(path, "rb");
    if (!f) return false;
    uint8_t chunk[65536];
    size_t n;
    while ((n = fread(chunk, 1, sizeof chunk, f)) > 0) out.insert(out.end(), chunk, chunk + n);
    fclose(f);
    return true;
}

static uint32_t le32(const std::vector<uint8_t> &b, size_t at) {
    if (at + 4 > b.size()) throw std::runtime_error("The scenario file is short.");
    return (uint32_t)b[at] | (uint32_t)b[at + 1] << 8 | (uint32_t)b[at + 2] << 16 | (uint32_t)b[at + 3] << 24;
}

int main(int argc, char **argv) {
    using namespace vamiga;
    if (argc < 3) {
        fprintf(stderr, "usage: amiga_display_checks SCENARIO RECORD [--fault ram|clock INDEX] [--trace FROM COUNT] [--per-slot]\n");
        return 2;
    }
    static RrDisplayChecks c;
    RrDisplayChecks::self = &c;
    for (int i = 3; i < argc; i++) {
        if (!strcmp(argv[i], "--fault") && i + 2 < argc) {
            c.fault_kind = !strcmp(argv[i + 1], "ram") ? 1 : !strcmp(argv[i + 1], "clock") ? 2 : 0;
            c.fault_at = strtoull(argv[i + 2], nullptr, 10);
            i += 2;
        } else if (!strcmp(argv[i], "--trace") && i + 2 < argc) {
            c.trace_from = strtoull(argv[i + 1], nullptr, 10);
            c.trace_count = strtoull(argv[i + 2], nullptr, 10);
            i += 2;
        } else if (!strcmp(argv[i], "--dump") && i + 2 < argc) {
            c.dump_frame = strtoull(argv[i + 1], nullptr, 10);
            c.dump_path = argv[i + 2];
            i += 2;
        } else if (!strcmp(argv[i], "--per-slot")) {
            Agnus::rrBplBatching = false;
            Denise::rrQuiet = false;
            DiskController::rrLazyOn = false;
            Agnus::rrSprSkip = false;
            Agnus::rrBltLane = false;
        } else if (!strcmp(argv[i], "--blt-off")) {
            Agnus::rrBltLane = false;
        } else if (!strcmp(argv[i], "--blt-fault") && i + 1 < argc) {
            Agnus::rrBltFault = atoi(argv[i + 1]);
            i += 1;
        } else if (!strcmp(argv[i], "--spr-off")) {
            Agnus::rrSprSkip = false;
        } else if (!strcmp(argv[i], "--spr-fault") && i + 1 < argc) {
            Agnus::rrSprFault = atoi(argv[i + 1]);
            i += 1;
        } else if (!strcmp(argv[i], "--disk-off")) {
            DiskController::rrLazyOn = false;
        } else if (!strcmp(argv[i], "--disk-fault") && i + 1 < argc) {
            DiskController::rrFault = atoi(argv[i + 1]);
            i += 1;
#ifdef RR_AMIGA_SHADOW
        } else if (!strcmp(argv[i], "--shadow-fault") && i + 1 < argc) {
            RrBus::fault = atoi(argv[i + 1]);
            i += 1;
        } else if (!strcmp(argv[i], "--access-trace") && i + 2 < argc) {
            RrBus::traceFrom = strtoull(argv[i + 1], nullptr, 10);
            RrBus::traceCount = strtoull(argv[i + 2], nullptr, 10);
            i += 2;
#endif
        } else {
            fprintf(stderr, "Unknown argument %s\n", argv[i]);
            return 2;
        }
    }
    std::vector<uint8_t> scenario;
    if (!read_file(argv[1], scenario)) { fprintf(stderr, "Cannot read %s\n", argv[1]); return 2; }
    FILE *record = nullptr;
    try {
        // Scenario, little endian: "RRDS", version 1, flags (bit 0: NTSC), chip KiB, frames, fault address, ROM size, ROM, then regions
        // (address, size, bytes) written into chip RAM after power-on, before the first instruction.
        if (scenario.size() < 4 || memcmp(scenario.data(), "RRDS", 4) || le32(scenario, 4) != 1) throw std::runtime_error("Not a scenario of this version.");
        const uint32_t flags = le32(scenario, 8), chip_kb = le32(scenario, 12), frames = le32(scenario, 16);
        c.fault_address = le32(scenario, 20);
        const uint32_t rom_size = le32(scenario, 24);
        size_t at = 28;
        if (at + rom_size > scenario.size()) throw std::runtime_error("The scenario's ROM is short.");
        std::vector<uint8_t> rom(scenario.begin() + (ptrdiff_t)at, scenario.begin() + (ptrdiff_t)(at + rom_size));
        at += rom_size;

        // The machine as amiga_session.cpp configures it for an export.
        c.emu.initialize();
        c.emu.set(ConfigScheme::A500_ECS_1MB);
        c.emu.set(Opt::AMIGA_VIDEO_FORMAT, (flags & 1) ? (i64)TV::NTSC : (i64)TV::PAL);
        c.emu.set(Opt::MEM_SLOW_RAM, 0x180000 / 1024);
        c.emu.set(Opt::MEM_CHIP_RAM, chip_kb);
        c.emu.set(Opt::DENISE_CLX_SPR_SPR, 1);
        c.emu.set(Opt::DENISE_CLX_SPR_PLF, 1);
        c.emu.set(Opt::DENISE_CLX_PLF_PLF, 1);
        c.emu.set(Opt::LA_CONNECT, 0);
        c.emu.set(Opt::MON_PALETTE, (i64)Palette::RGB);
        c.emu.set(Opt::MEM_RAM_INIT_PATTERN, (i64)RamInitPattern::ALL_ZEROES);
        c.emu.set(Opt::AUD_ASR, 0);
        c.amiga = &c.emu.rrMain();
        Amiga &amiga = *c.amiga;
        amiga.audioPort.setSampleRate(48000.0);
        amiga.mem.loadRom(rom.data(), (isize)rom.size());
        amiga.powerOn();
        const uint32_t regions = le32(scenario, at);
        at += 4;
        for (uint32_t r = 0; r < regions; r++) {
            const uint32_t address = le32(scenario, at), size = le32(scenario, at + 4);
            at += 8;
            if (at + size > scenario.size() || (uint64_t)address + size > (uint64_t)amiga.mem.chipRamSize()) throw std::runtime_error("A region of the scenario lies outside chip RAM.");
            memcpy(amiga.mem.chip + address, scenario.data() + at, size);
            at += size;
        }
        amiga.run();
        c.buffer.resize(64u << 20);
        moira::rr_moira_native = RrDisplayChecks::hook;

        record = fopen(argv[2], "wb");
        if (!record) throw std::runtime_error("Cannot write the record.");
        const uint32_t rows = (uint32_t)Tex::height;
        fwrite("RRDR", 1, 4, record);
        const uint32_t head[3] = {2, frames, rows};
        fwrite(head, 4, 3, record);
        std::vector<float> sound;
        for (uint32_t frame = 0; frame < frames; frame++) {
            amiga.computeFrame();
            Message m; std::exception_ptr e;
            while (amiga.msgQueue.get(m, e)) {}
            auto &stream = amiga.audioPort.stream;
            const isize count = stream.count();
            sound.assign((size_t)count * 2, 0.0f);
            const isize got = count ? amiga.audioPort.copyInterleaved(sound.data(), count) : 0;
            uint64_t row[13] = {};
            row[0] = (uint64_t)c.steps.size();
            row[1] = c.save_hash(amiga.agnus);
            row[2] = c.save_hash(amiga.denise);
            row[3] = c.save_hash(amiga.paula);
            row[4] = c.save_hash(amiga.ciaA);
            row[5] = c.save_hash(amiga.ciaB);
            row[6] = c.save_hash(amiga.cpu);
            row[7] = fnv(BASIS, amiga.mem.chip, (size_t)amiga.mem.chipRamSize());
            row[8] = amiga.mem.slow ? fnv(BASIS, amiga.mem.slow, (size_t)amiga.mem.slowRamSize()) : 0;
            row[9] = fnv(BASIS, sound.data(), (size_t)got * 2 * sizeof(float));
            row[10] = amiga.denise.spypeekCLXDAT();
            row[11] = (uint64_t)amiga.agnus.clock;
            if (getenv("RR_DISK_DEBUG")) {
                char text[512];
                amiga.paula.diskController.rrDebug(text, sizeof text);
                fprintf(stderr, "frame %u clock %lld %s\n", frame, (long long)amiga.agnus.clock, text);
            }
#ifdef RR_AMIGA_SHADOW
            row[12] = RrBus::takeOwners();       // every line's bus owners (who took each colour clock), hashed
#endif
            fwrite(row, 8, 13, record);
            const Texture &tex = amiga.denise.pixelEngine.getStableBuffer();
            const uint32_t *px = (const uint32_t *)tex.pixels.ptr;
            for (uint32_t y = 0; y < rows; y++) {
                const uint64_t h = fnv(BASIS, px + (size_t)y * Tex::width, (size_t)Tex::width * sizeof(uint32_t));
                fwrite(&h, 8, 1, record);
            }
            if (frame == c.dump_frame && c.dump_path) {
                if (FILE *d = fopen(c.dump_path, "wb")) {
                    fwrite(px, sizeof(uint32_t), (size_t)Tex::width * rows, d);
                    fclose(d);
                }
            }
        }
        const uint64_t total = c.steps.size();
        fwrite(&total, 8, 1, record);
        fwrite(c.steps.data(), 8, c.steps.size(), record);
        if (fclose(record)) { record = nullptr; throw std::runtime_error("Cannot write the record."); }
        record = nullptr;
        const Agnus &agnus = amiga.agnus;
        const Denise &denise = amiga.denise;
        printf("{\"frames\":%u,\"instructions\":%llu,\"fault\":%d,\"lines\":[%llu,%llu,%llu],\"words\":[%llu,%llu],\"quiet\":[%llu,%llu]", frames,
               (unsigned long long)total, c.fault_kind, (unsigned long long)agnus.rrLines[0], (unsigned long long)agnus.rrLines[1],
               (unsigned long long)agnus.rrLines[2], (unsigned long long)agnus.rrWords[0], (unsigned long long)agnus.rrWords[1],
               (unsigned long long)denise.rrQuietLines[0], (unsigned long long)denise.rrQuietLines[1]);
        const u64 *disk = amiga.paula.diskController.rrCounts;
        printf(",\"disk\":[%llu,%llu,%llu,%llu],\"sprite_slots_left_out\":%llu", (unsigned long long)disk[0], (unsigned long long)disk[1],
               (unsigned long long)disk[2], (unsigned long long)disk[3], (unsigned long long)agnus.rrSprSkipped);
        printf(",\"blitter_alone\":%llu", (unsigned long long)agnus.rrBltAlone);
#ifdef RR_AMIGA_SHADOW
        {
            static char bus[8192];
            RrBus::json(bus, sizeof bus);
            printf(",\"bus_mismatches\":%llu,\"bus\":%s", (unsigned long long)RrBus::mismatches(), bus);
        }
#endif
        printf("}\n");
    } catch (std::exception &e) {
        if (record) fclose(record);
        fprintf(stderr, "The scenario failed: %s\n", e.what());
        fflush(stdout);
        std::_Exit(3);
    }
    fflush(stdout);
    std::_Exit(0);
}
