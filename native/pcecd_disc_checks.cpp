// The PC Engine CD disc provider (native/pcecd_disc.cpp) on a disc image: prints its table of contents and a hash of the sectors it reads, so that
// tools/pcecd_disc_selftest.py can compare it with the pure-Python reader (retrorecomp/pcecd_disc.py) and, for a CHD of version 5, with the engine's own
// provider (which loads a libchdr shared library by path and refuses version 4).
//
//   pcecd_disc_checks IMAGE SHA256 [--offset N --length N] [--engine LIBCHDR [--engine-image IMAGE]]   (--engine-image: the engine reads the CUE sheet, ours its pack)
//
// The hash is FNV-1a over the user data of the first 64 sectors of every data track and over the samples of the first 8 sectors of the first
// three audio tracks. Original RetroRecomp code: MIT.
#include "pcecd_disc.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <exception>
#include <string>

namespace {
std::uint64_t fnv(std::uint64_t hash, const void *data, std::size_t size) {
    const auto *bytes = static_cast<const std::uint8_t *>(data);
    for (std::size_t n = 0; n < size; ++n) hash = (hash ^ bytes[n]) * 1099511628211ull;
    return hash;
}

struct Summary {
    std::uint32_t tracks = 0, leadout = 0;
    std::uint64_t data[100] = {}, audio[100] = {};
    std::uint32_t starts[100] = {};
    std::uint8_t types[100] = {};
};

Summary summarise(pce::SectorProvider &provider) {
    Summary out;
    const auto &toc = provider.toc();
    out.tracks = toc.track_count;
    out.leadout = toc.leadout_lba;
    unsigned audio_seen = 0;
    for (unsigned t = 0; t < toc.track_count; ++t) {
        out.starts[t] = toc.tracks[t].index1_lba;
        out.types[t] = toc.tracks[t].type;
        const std::uint32_t end = t + 1 < toc.track_count ? toc.tracks[t + 1].index1_lba : toc.leadout_lba;
        std::uint64_t hash = 14695981039346656037ull;
        if (toc.tracks[t].type == 4) {
            for (std::uint32_t lba = toc.tracks[t].index1_lba; lba < end && lba < toc.tracks[t].index1_lba + 64; ++lba) {
                if (!provider.program_track(lba).index) continue;       // a gap between tracks: no data to read
                try {
                    const auto sector = provider.read(lba);
                    hash = fnv(hash, sector.data(), sector.size());
                } catch (const pce::SectorReadError &) {                // a sector a guest would see as a read error: only the fact is hashed
                    hash = fnv(hash, "E", 1);
                }
            }
            out.data[t] = hash;
        } else if (audio_seen < 3) {
            ++audio_seen;
            for (std::uint32_t lba = toc.tracks[t].index1_lba; lba < end && lba < toc.tracks[t].index1_lba + 8; ++lba) {
                if (!provider.audio_playable(lba)) continue;
                const auto sector = provider.read_audio(lba);
                hash = fnv(hash, sector.data(), sector.size() * sizeof(std::int16_t));
            }
            out.audio[t] = hash;
        }
    }
    return out;
}

void print(const char *label, const Summary &s) {
    std::printf("%s tracks=%u leadout=%u\n", label, s.tracks, s.leadout);
    for (unsigned t = 0; t < s.tracks; ++t)
        std::printf("%s track %u start=%u type=%u data=%016llx audio=%016llx\n", label, t + 1, s.starts[t], s.types[t],
                    static_cast<unsigned long long>(s.data[t]), static_cast<unsigned long long>(s.audio[t]));
}

bool same(const Summary &a, const Summary &b) {
    if (a.tracks != b.tracks || a.leadout != b.leadout) return false;
    for (unsigned t = 0; t < a.tracks; ++t)
        if (a.starts[t] != b.starts[t] || a.types[t] != b.types[t] || a.data[t] != b.data[t] || a.audio[t] != b.audio[t]) return false;
    return true;
}
}  // namespace

int main(int argc, char **argv) {
    if (argc < 3) {
        std::fprintf(stderr, "usage: pcecd_disc_checks IMAGE SHA256 [--offset N --length N] [--engine LIBCHDR [--engine-image IMAGE]]\n");
        return 2;
    }
    std::uint64_t offset = 0, length = 0;
    std::string engine, referee = argv[1];
    for (int i = 3; i + 1 < argc; i += 2) {
        if (!std::strcmp(argv[i], "--offset")) offset = std::strtoull(argv[i + 1], nullptr, 10);
        else if (!std::strcmp(argv[i], "--length")) length = std::strtoull(argv[i + 1], nullptr, 10);
        else if (!std::strcmp(argv[i], "--engine")) engine = argv[i + 1];
        else if (!std::strcmp(argv[i], "--engine-image")) referee = argv[i + 1];   // the engine reads this (a CUE sheet), ours reads IMAGE (its pack)
    }
    try {
        auto ours = pcecd::open_disc(argv[1], offset, length, argv[2]);
        const Summary ours_summary = summarise(*ours);
        print("ours", ours_summary);
        if (!engine.empty()) {
            auto theirs = pce::open_sector_provider(referee, engine);
            const Summary theirs_summary = summarise(*theirs);
            print("engine", theirs_summary);
            std::printf("engine %s\n", same(ours_summary, theirs_summary) ? "SAME" : "DIFFERENT");
            return same(ours_summary, theirs_summary) ? 0 : 1;
        }
    } catch (const std::exception &failure) {
        std::printf("FAULT %s\n", failure.what());
        return 3;
    }
    return 0;
}
