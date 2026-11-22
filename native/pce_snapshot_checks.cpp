// PC Engine snapshot: the determinism probe of the machine's own checks (the contract of the multiplayer rollback tier; the NES's is native/nes_machine_checks.c).
// Built and run by tools/pce_snapshot_selftest.py against an authored HuCard that keeps every device busy; no commercial data. Built and run by
// tools/pcecd_snapshot_selftest.py against the player's own System Card and a disc (a build with RR_PCE_DISC), never run by the public checks.
//
//   pce_snapshot_checks ROM [--sf2]
//   pce_snapshot_checks --disc CARD DISC SHA256 [--standard] [--frames N] [--stride N] [--replay N]
//
// What it proves, on the interpreter (the native code is the same machine, proved apart against the reference):
//   1. A state saved at ANY save point of the first pass (every frame for a HuCard, every --stride frames for a disc), loaded back, leaves the machine exactly as it
//      was: the engine's own full checkpoint (pce::encode_checkpoint: every field of every device, the ROM, both frame buffers, the audio side) equals the one
//      taken at the save. The snapshot leaves out the ROM and the configuration, so this fails the day the engine adds a field the snapshot does not list.
//   2. The frames that follow a load are the frames that followed the save: the digest and the engine's checkpoint equal those of the first pass, frame by frame.
//   3. A save over a buffer of other bytes is identical to the first; a load of a wrong size, a flipped byte or a foreign magic is refused and the machine untouched.
//   4. A save in the middle of pending DMA, interrupts and sound restores bit for bit (the program keeps all three pending).
//   5. The digest does not depend on how the code ran (native or interpreted step counters are left out).
//   6. Nor on how the host drank the sound: a second run that drains the PCM after every frame has the same digest at every frame as the first, which does not.
//   7. A disc machine (the System Card and a disc): the drive, the ADPCM unit and the backup memory are in the snapshot and in the digest.
// Original RetroRecomp code: MIT. The engine keeps its own MIT terms (licenses/pcenginerecomp.md).
#include "pce_machine.h"
#include "pce_machine_internal.hpp"
#include "pce_snapshot.h"

#include "pce/checkpoint.hpp"

#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iterator>
#include <string>
#include <vector>

namespace {
int failures = 0;
void expect(bool condition, const char *what, long a = 0, long b = 0) {
    if (condition) return;
    ++failures;
    std::printf("FAIL %s (%ld, %ld)\n", what, a, b);
}

// What the probe runs: an authored HuCard, or the player's card and disc.
struct Config {
    std::vector<uint8_t> rom;
    bool sf2 = false;
    bool disc = false;
    std::vector<uint8_t> card;
    std::string disc_path, disc_sha256;
    bool super_ram = true;
    unsigned frames = 150, stride = 1, replay = 24;
    bool digests = false;       // print the digest of every 60th frame of the first pass: two machines' lines (Windows, Linux) must be the same
} config;

uint64_t fnv(const std::vector<uint8_t> &bytes) {
    uint64_t hash = 14695981039346656037ull;
    for (const auto byte : bytes) hash = (hash ^ byte) * 1099511628211ull;
    return hash;
}

// The pads of frame `f` (1-based): a fixed pseudo-random pattern that depends on the frame number only, as the host's inputs do.
void pads_of(unsigned f, uint16_t pads[PCE_PADS]) {
    uint32_t x = f * 2654435761u;
    for (unsigned slot = 0; slot < PCE_PADS; ++slot) {
        x = x * 1664525u + 1013904223u;
        pads[slot] = slot < 2 ? static_cast<uint16_t>((x >> 11) & 0x0FF) : 0;
    }
}

struct Frame {
    uint64_t digest = 0;       // pce_snapshot_digest
    uint64_t engine = 0;       // the engine's full checkpoint, hashed
    uint64_t counters = 0;     // the bridge's frame counter
};

std::vector<uint8_t> engine_checkpoint() {
    pce::settle_silent_cd_source(*pce_bridge::bus());
    return pce::encode_checkpoint(*pce_bridge::bus(), *pce_bridge::cpu());
}

bool step_frame(unsigned f) {
    uint16_t pads[PCE_PADS];
    pads_of(f, pads);
    pce_machine_set_pads(pads);
    char error[256] = {0};
    if (!pce_machine_run_frame(error, sizeof error)) {
        std::printf("FAIL the engine faulted at frame %u: %s\n", f, error);
        ++failures;
        return false;
    }
    return true;
}

Frame observe() {
    Frame frame;
    frame.digest = pce_snapshot_digest();
    frame.engine = fnv(engine_checkpoint());
    frame.counters = pce_bridge::frame_count();
    return frame;
}

bool start() {
    char error[256] = {0};
    pce_machine_shutdown();
    bool ok;
    if (config.disc) {
        const PceDiscRecipe recipe = {config.card.data(), config.card.size(), config.disc_path.c_str(), 0, 0, config.disc_sha256.c_str(),
                                      config.super_ram ? 1 : 0, 0, PCE_UNKNOWN_NEC_INVALID, 2, 0};
        ok = pce_machine_init_disc(&recipe, error, sizeof error) != 0;
    } else {
        ok = pce_machine_init(config.rom.data(), config.rom.size(), 0, 0, config.sf2 ? PCE_BOARD_SF2 : PCE_BOARD_BASE, 2, 0, error, sizeof error) != 0;
    }
    if (!ok) {
        std::printf("FAIL cannot start the machine: %s\n", error);
        ++failures;
        return false;
    }
    pce_machine_policy(PCE_POLICY_HYBRID);
    return true;
}

void probe(const char *label) {
    const unsigned frames = config.frames, replay = config.replay, stride = config.stride;
    if (!start()) return;
    const size_t bound = pce_snapshot_bound();
    expect(bound > 0, "the snapshot has a bound");
    std::vector<uint8_t> saved(bound, 0xA5), other(bound, 0x5A);

    // The first pass: every observation of every frame, a snapshot at the save points.
    std::vector<std::vector<uint8_t>> snapshot(frames + 1);
    std::vector<Frame> first(frames + 1);
    std::vector<uint64_t> engine_at(frames + 1, 0);
    std::vector<uint8_t> have(frames + 1, 0);
    size_t largest = 0, total = 0, engine_bytes = 0;
    for (unsigned f = 1; f <= frames; ++f) {
        if (!step_frame(f)) return;
        first[f] = observe();
        const size_t n = pce_snapshot_save(saved.data(), saved.size());
        expect(n > 0 && n <= bound, "a save writes within the bound", static_cast<long>(n), static_cast<long>(bound));
        largest = std::max(largest, n);
        total += n;
        if (f % stride == 0 || f == frames) {
            snapshot[f].assign(saved.begin(), saved.begin() + static_cast<long>(n));
            have[f] = 1;
            const auto engine = engine_checkpoint();
            engine_at[f] = fnv(engine);
            engine_bytes = engine.size();
        }
        // 3. A save over other bytes is the same save.
        if (f % 17 == 1) {
            const size_t again = pce_snapshot_save(other.data(), other.size());
            expect(again == n && std::memcmp(other.data(), saved.data(), n) == 0, "a save over other bytes is identical", static_cast<long>(again), static_cast<long>(n));
        }
    }
    std::printf("%s: %u frames, snapshot %zu bytes at most (mean %zu), bound %zu, the engine's own checkpoint %zu bytes, a save point every %u frame(s)\n", label,
                frames, largest, total / frames, bound, engine_bytes, stride);

    if (config.digests)
        for (unsigned f = 60; f <= frames; f += 60) std::printf("digest %u %016llx\n", f, static_cast<unsigned long long>(first[f].digest));
    if (config.disc) {
        const auto *b = pce_bridge::bus();
        std::printf("%s: what the first pass reached: %llu sectors read, %llu CD audio sectors played, %llu ADPCM writes (%llu bytes by DMA), %llu backup-memory bytes not blank, "
                    "%llu CD commands the engine does not model\n", label, static_cast<unsigned long long>(b->cd.sectors_read), static_cast<unsigned long long>(b->cd.audio.sectors_played),
                    static_cast<unsigned long long>(b->adpcm.writes), static_cast<unsigned long long>(b->adpcm.dma_bytes),
                    static_cast<unsigned long long>(std::count_if(b->bytes->begin() + b->backing_address(0xF7u << 13), b->bytes->begin() + b->backing_address(0xF7u << 13) + 2048,
                                                                  [](uint8_t v) { return v != 0; })),
                    static_cast<unsigned long long>(b->cd.unknown_commands + b->cd.invalid_commands));
    }

    // 1, 2, 4: every save point is loaded and compared right away and over the frames that follow.
    unsigned replayed = 0, loaded = 0;
    for (unsigned s = 1; s <= frames; ++s) {
        if (!have[s]) continue;
        // Go somewhere else first so that a load that restores nothing is seen: run on from the end and load back.
        const unsigned last = std::min(frames, s + replay);
        if (!pce_snapshot_load(snapshot[s].data(), snapshot[s].size())) {
            expect(false, "a snapshot of this machine loads", s);
            continue;
        }
        ++loaded;
        const auto restored = engine_checkpoint();
        expect(fnv(restored) == engine_at[s], "after a load the engine's full checkpoint equals the one at the save", s, static_cast<long>(restored.size()));
        expect(pce_snapshot_digest() == first[s].digest, "after a load the digest equals the one at the save", s);
        expect(pce_bridge::frame_count() == first[s].counters, "after a load the bridge's counter is the saved one", s);
        for (unsigned f = s + 1; f <= last; ++f) {
            if (!step_frame(f)) return;
            const Frame again = observe();
            expect(again.digest == first[f].digest, "the frames after a load repeat the digest", f, s);
            expect(again.engine == first[f].engine, "the frames after a load repeat the engine's checkpoint", f, s);
            ++replayed;
        }
        // The machine, run past the end of the first pass, is not at the same frame as the next save point: the next load must bring it back.
        if (!step_frame(last + 1)) return;
    }
    std::printf("%s: %u save points loaded, %u frames replayed after a load\n", label, loaded, replayed);

    // 3. Refusals leave the machine as it was.
    if (!pce_snapshot_load(snapshot[frames].data(), snapshot[frames].size())) expect(false, "the last snapshot loads");
    const uint64_t before = pce_snapshot_digest();
    const auto checkpoint_before = engine_checkpoint();
    const auto &good = snapshot[frames];
    expect(!pce_snapshot_load(good.data(), good.size() - 1), "a snapshot one byte short is refused");
    expect(!pce_snapshot_load(good.data(), 0), "an empty snapshot is refused");
    expect(!pce_snapshot_load(good.data(), 7), "a snapshot shorter than its header is refused");
    std::vector<uint8_t> longer(good);
    longer.push_back(0);
    expect(!pce_snapshot_load(longer.data(), longer.size()), "a snapshot one byte long is refused");
    for (const size_t position : {size_t(0), size_t(9), size_t(12), size_t(16), size_t(20), size_t(25), size_t(33), good.size() / 2, good.size() - 1}) {
        std::vector<uint8_t> damaged(good);
        damaged[position] ^= 0x40;
        expect(!pce_snapshot_load(damaged.data(), damaged.size()), "a flipped byte is refused", static_cast<long>(position));
    }
    expect(pce_snapshot_digest() == before && engine_checkpoint() == checkpoint_before, "refused loads leave the machine untouched");
    expect(pce_snapshot_save(saved.data(), 16) == 0, "a save into a buffer that is too small writes nothing");

    // 5. The digest does not read how the code ran.
    const uint64_t digest = pce_snapshot_digest();
    pce_bridge::cpu()->native_steps += 12345;
    pce_bridge::cpu()->interpreter_steps += 54321;
    pce_bridge::cpu()->guard_misses += 7;
    pce_bridge::bus()->generation[3] += 99;
    expect(pce_snapshot_digest() == digest, "the digest leaves out the step counters and the generations");
    pce_bridge::cpu()->native_steps -= 12345;
    pce_bridge::cpu()->interpreter_steps -= 54321;
    pce_bridge::cpu()->guard_misses -= 7;
    pce_bridge::bus()->generation[3] -= 99;
    // ... and does read the guest: one byte of work RAM, the program counter, a VRAM word, the VCE, the pads.
    auto *bus = pce_bridge::bus();
    auto *cpu = pce_bridge::cpu();
    (*bus->bytes)[bus->backing_address(0x1F0000u + 0x100)] ^= 1;
    expect(pce_snapshot_digest() != digest, "the digest reads work RAM");
    (*bus->bytes)[bus->backing_address(0x1F0000u + 0x100)] ^= 1;
    cpu->pc ^= 1;
    expect(pce_snapshot_digest() != digest, "the digest reads the program counter");
    cpu->pc ^= 1;
    (*bus->vdc.vram)[0x123] ^= 1;
    expect(pce_snapshot_digest() != digest, "the digest reads VRAM");
    (*bus->vdc.vram)[0x123] ^= 1;
    bus->vce.palette[5] ^= 1;
    expect(pce_snapshot_digest() != digest, "the digest reads the palette");
    bus->vce.palette[5] ^= 1;
    bus->irq.timer_counter ^= 1;
    expect(pce_snapshot_digest() != digest, "the digest reads the timer");
    bus->irq.timer_counter ^= 1;
    expect(pce_snapshot_digest() == digest, "the digest comes back with the state");

    // 7. A disc machine: the drive, the ADPCM unit and the backup memory are read by the digest and carried by the snapshot.
    if (config.disc) {
        const auto sensitive = [&](const char *what, auto &&flip) {
            flip();
            const bool read = pce_snapshot_digest() != digest;
            flip();
            expect(read && pce_snapshot_digest() == digest, what);
        };
        sensitive("the digest reads the ADPCM RAM", [&] { bus->adpcm.ram[0x1234] ^= 1; });
        sensitive("the digest reads the ADPCM address", [&] { bus->adpcm.read_address ^= 1; });
        sensitive("the digest reads the drive's phase", [&] { bus->cd.scsi.phase ^= 1; });
        sensitive("the digest reads the drive's sector counter", [&] { bus->cd.scsi.current_lba ^= 1; });
        sensitive("the digest reads the CD audio state", [&] { bus->cd.audio.current_lba ^= 1; });
        sensitive("the digest reads the CD interrupt mask", [&] { bus->cd.interrupt_enable ^= 4; });
        sensitive("the digest reads the CD acknowledge", [&] { bus->cd.ack = !bus->cd.ack; });
        sensitive("the digest reads the backup memory", [&] { (*bus->bytes)[bus->backing_address(0xF7u << 13) + 5] ^= 1; });
        sensitive("the digest reads the card's RAM", [&] { (*bus->bytes)[bus->backing_address(0x80u << 13) + 77] ^= 1; });
        // What the snapshot carries of them: change each, load the last snapshot, the machine is back.
        const auto before_load = engine_checkpoint();
        bus->adpcm.ram[0x1234] ^= 0x55;
        bus->cd.scsi.phase ^= 1;
        (*bus->bytes)[bus->backing_address(0xF7u << 13) + 5] ^= 0xAA;
        if (!pce_snapshot_load(snapshot[frames].data(), snapshot[frames].size())) expect(false, "the last snapshot loads over a disturbed disc machine");
        expect(engine_checkpoint() == before_load && pce_snapshot_digest() == digest, "a load puts back the drive, the ADPCM unit and the backup memory");
    }

    // 6. How the host drank the sound is not the guest: a run that drains the PCM after every frame has the digests of the first pass.
    if (!start()) return;
    std::vector<int16_t> sink(96000);
    unsigned differing = 0;
    for (unsigned f = 1; f <= frames; ++f) {
        if (!step_frame(f)) return;
        pce_machine_audio(sink.data(), sink.size());
        if (pce_snapshot_digest() != first[f].digest) ++differing;
    }
    expect(differing == 0, "a run that drains the sound has the digests of one that does not", differing);
}
}  // namespace

int main(int argc, char **argv) {
    if (argc < 2) {
        std::printf("usage: pce_snapshot_checks ROM [--sf2] | --disc CARD DISC SHA256 [--standard] [--frames N] [--stride N] [--replay N]\n");
        return 2;
    }
    const auto read_file = [](const char *path) {
        std::ifstream file(path, std::ios::binary);
        return std::vector<uint8_t>((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());
    };
    if (std::string(argv[1]) == "--disc") {
        if (argc < 5) {
            std::printf("usage: pce_snapshot_checks --disc CARD DISC SHA256 [--standard] [--frames N] [--stride N] [--replay N]\n");
            return 2;
        }
        config.disc = true;
        config.card = read_file(argv[2]);
        config.disc_path = argv[3];
        config.disc_sha256 = argv[4];
        config.frames = 600;
        config.stride = 20;
        config.replay = 24;
        for (int i = 5; i < argc; ++i) {
            const std::string option = argv[i];
            if (option == "--standard") config.super_ram = false;
            else if (option == "--frames" && i + 1 < argc) config.frames = static_cast<unsigned>(std::max(1, std::atoi(argv[++i])));
            else if (option == "--digests") config.digests = true;
            else if (option == "--stride" && i + 1 < argc) config.stride = static_cast<unsigned>(std::max(1, std::atoi(argv[++i])));
            else if (option == "--replay" && i + 1 < argc) config.replay = static_cast<unsigned>(std::atoi(argv[++i]));
        }
        if (config.card.size() != PCE_CARD_BYTES) {
            std::printf("the card is %u bytes, not %u: %s\n", static_cast<unsigned>(config.card.size()), PCE_CARD_BYTES, argv[2]);
            return 2;
        }
        probe(config.super_ram ? "disc, Super System Card RAM" : "disc, System Card RAM");
    } else {
        config.rom = read_file(argv[1]);
        if (config.rom.empty()) {
            std::printf("cannot read %s\n", argv[1]);
            return 2;
        }
        config.sf2 = argc > 2 && std::string(argv[2]) == "--sf2";
        probe(config.sf2 ? "sf2 board" : "base board");
    }
    pce_machine_shutdown();
    std::printf(failures ? "FAIL: %d check(s) failed\n" : "PASS\n", failures);
    return failures ? 1 : 0;
}
