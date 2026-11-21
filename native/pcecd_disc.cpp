// PC Engine CD disc: a sector provider for the pinned pcenginerecomp runtime (native/pcecd_disc.h).
//
// The engine's own provider (runtime/src/sector.cpp) reads a CHD of version 5 only, through a libchdr shared library it loads by path, from a whole
// file, and hashes the whole file when it opens it. A game of ours holds the disc inside its own executable and has no DLL, and the library has CHDs
// of version 4: this provider takes the disc from `length` bytes of a file at `offset`, reads both versions through libchdr linked statically (the library
// decodes the hunks and reads the metadata of either version), and is given the disc's digest. The numbering of sectors, the classification of tracks
// and the errors a guest can see are the engine's own (the same rules, written again here): a disc read by this provider and by the engine's gives the
// same table of contents and the same sectors (tools/pcecd_disc_selftest.py).
//
// Original RetroRecomp code: MIT. libchdr keeps its own terms (licenses/libchdr.md); the engine its own MIT terms (licenses/pcenginerecomp.md).
#include "pcecd_disc.h"

#include <algorithm>
#include <array>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <limits>
#include <string>
#include <vector>

extern "C" {
#include "libchdr/chd.h"
}

namespace pcecd {
namespace {
namespace fs = std::filesystem;
constexpr std::uint64_t kFrame = 2448;
constexpr std::uint32_t kMaxLba = 449850;

fs::path path_of(const std::string &text) {
    return fs::path(std::u8string(reinterpret_cast<const char8_t *>(text.data()), text.size()));
}

// libchdr reads through these callbacks; the range is the disc's bytes inside the file.
struct Range {
    std::FILE *file = nullptr;
    std::uint64_t base = 0, size = 0, position = 0;
    ~Range() {
        if (file) std::fclose(file);
    }
};

int seek64(std::FILE *file, std::uint64_t offset) {
#ifdef _WIN32
    return _fseeki64(file, static_cast<__int64>(offset), SEEK_SET);
#else
    return fseeko(file, static_cast<off_t>(offset), SEEK_SET);
#endif
}

std::uint64_t range_size(void *argp) { return static_cast<Range *>(argp)->size; }
size_t range_read(void *buffer, size_t size, size_t count, void *argp) {
    auto *range = static_cast<Range *>(argp);
    if (!size || !count) return 0;
    const std::uint64_t want = std::uint64_t(size) * count;
    const std::uint64_t left = range->position < range->size ? range->size - range->position : 0;
    const std::uint64_t take = std::min(want, left) / size * size;
    if (!take || seek64(range->file, range->base + range->position)) return 0;
    const size_t got = std::fread(buffer, size, static_cast<size_t>(take / size), range->file);
    range->position += std::uint64_t(got) * size;
    return got;
}
int range_close(void *) { return 0; }       // the Range closes its own file
int range_seek(void *argp, int64_t offset, int whence) {
    auto *range = static_cast<Range *>(argp);
    std::int64_t target = whence == SEEK_SET ? offset : whence == SEEK_CUR ? std::int64_t(range->position) + offset : std::int64_t(range->size) + offset;
    if (target < 0 || std::uint64_t(target) > range->size) return -1;
    range->position = static_cast<std::uint64_t>(target);
    return 0;
}
const core_file_callbacks kCallbacks = {range_size, range_read, range_close, range_seek};

class Disc final : public pce::SectorProvider {
    struct Track {
        std::uint32_t start, count;
        std::uint64_t frame;       // the frame of the image that holds the track's index 01
        bool raw, audio;
        std::uint32_t stored_pregap = 0;
    };
    Range range;
    chd_file *chd = nullptr;
    pce::CdToc table;
    std::vector<Track> tracks;
    std::uint32_t hunk_bytes = 0, cached = std::numeric_limits<std::uint32_t>::max();
    std::vector<std::uint8_t> cache;

    void metadata() {
        const chd_header *header = chd_get_header(chd);
        if (!header || (header->version != 4 && header->version != 5)) throw pce::Fault("A CHD of version 4 or 5 is required");
        if (header->flags & 2u) throw pce::Fault("A CHD with a parent is not supported");
        const std::uint8_t none[CHD_SHA1_BYTES] = {};
        if (header->version == 5 && std::memcmp(header->parentsha1, none, sizeof none)) throw pce::Fault("A CHD with a parent is not supported");
        hunk_bytes = header->hunkbytes;
        const std::uint64_t logical = header->logicalbytes;
        if (!hunk_bytes || hunk_bytes > 524288 || hunk_bytes % kFrame || !logical || logical % kFrame) throw pce::Fault("Unsupported CHD hunk geometry");
        std::uint64_t storage = 0, disc = 0;
        for (std::uint32_t index = 0;; ++index) {
            char text[512] = {};
            std::uint32_t length = 0;
            auto error = chd_get_metadata(chd, CDROM_TRACK_METADATA2_TAG, index, text, sizeof text - 1, &length, nullptr, nullptr);
            if (error != CHDERR_NONE) error = chd_get_metadata(chd, CDROM_TRACK_METADATA_TAG, index, text, sizeof text - 1, &length, nullptr, nullptr);
            if (error != CHDERR_NONE) break;
            char kind[32] = {}, subtype[32] = {}, pgtype[32] = {}, pgsub[32] = {};
            int number = 0;
            unsigned frames = 0, pregap = 0, postgap = 0;
            int fields = std::sscanf(text, "TRACK:%d TYPE:%31s SUBTYPE:%31s FRAMES:%u PREGAP:%u PGTYPE:%31s PGSUB:%31s POSTGAP:%u", &number, kind, subtype,
                                     &frames, &pregap, pgtype, pgsub, &postgap);
            if (fields < 4) throw pce::Fault("Malformed CHD track metadata");
            if (fields < 8) pregap = postgap = 0;
            if (tracks.size() >= 99 || number != int(tracks.size()) + 1 || !frames || frames > kMaxLba || pregap > kMaxLba || postgap > kMaxLba)
                throw pce::Fault("Unsupported CHD track geometry");
            const std::string type = kind;
            if (type != "MODE1" && type != "MODE1_RAW" && type != "AUDIO") throw pce::Fault("Unsupported CHD track format");
            const bool stored = fields >= 8 && pgtype[0] == 'V' && pregap;
            if (stored && pregap >= frames) throw pce::Fault("Unsupported CHD track pregap");
            const std::uint64_t start = disc + pregap, count = frames - (stored ? pregap : 0);
            if (start + count > kMaxLba - 1) throw pce::Fault("CHD disc geometry exceeds the supported bound");
            tracks.push_back({static_cast<std::uint32_t>(start), static_cast<std::uint32_t>(count), storage + (stored ? pregap : 0), type == "MODE1_RAW",
                              type == "AUDIO", stored ? pregap : 0});
            table.tracks[table.track_count++] = {static_cast<std::uint32_t>(start), static_cast<std::uint8_t>(type == "AUDIO" ? 0 : 4)};
            storage += (std::uint64_t(frames) + 3) / 4 * 4;
            disc += std::uint64_t(frames) + postgap + (stored ? 0 : pregap);
        }
        if (tracks.empty() || storage * kFrame != logical) throw pce::Fault("CHD track metadata disagrees with its logical size");
        table.leadout_lba = tracks.back().start + tracks.back().count;
        cache.resize(hunk_bytes);
    }

    // The 2,448-byte frame of the image at `frame`, from the cached hunk.
    const std::uint8_t *frame_at(std::uint64_t frame) {
        const std::uint64_t position = frame * kFrame;
        const auto hunk = static_cast<std::uint32_t>(position / hunk_bytes);
        if (cached != hunk) {
            cached = std::numeric_limits<std::uint32_t>::max();       // a failed decode may leave the buffer half written
            if (chd_read(chd, hunk, cache.data()) != CHDERR_NONE) throw pce::Fault("libchdr hunk decode failed");
            cached = hunk;
        }
        return cache.data() + position % hunk_bytes;
    }

public:
    Disc(const std::string &file, std::uint64_t offset, std::uint64_t length, const std::string &sha256) {
        const auto path = path_of(file);
#ifdef _WIN32
        range.file = _wfopen(path.c_str(), L"rb");
#else
        range.file = std::fopen(path.c_str(), "rb");
#endif
        if (!range.file) throw pce::Fault("Cannot open the disc image");
        std::error_code failure;
        const auto whole = fs::file_size(path, failure);
        if (failure || offset > whole) throw pce::Fault("Cannot size the disc image");
        range.base = offset;
        range.size = length ? length : whole - offset;
        if (range.size > whole - offset) throw pce::Fault("The disc is longer than its file");
        std::array<char, 8> magic{};
        if (seek64(range.file, offset) || std::fread(magic.data(), 1, magic.size(), range.file) != magic.size()) throw pce::Fault("Short disc image read");
        if (std::string(magic.data(), magic.size()) == "MComprHD") {
            const auto error = chd_open_core_file_callbacks(&kCallbacks, &range, CHD_OPEN_READ, nullptr, &chd);
            if (error != CHDERR_NONE || !chd) throw pce::Fault(std::string("libchdr refused the CHD: ") + chd_error_string(error));
            metadata();
        } else {
            if (!range.size || range.size % 2048 || range.size / 2048 > 449849) throw pce::Fault("An ISO needs whole 2048-byte sectors, at most 449,849");
            table.track_count = 1;
            table.leadout_lba = static_cast<std::uint32_t>(range.size / 2048);
            table.tracks[0] = {0, 4};
        }
        table.validate();
        table.image_sha256 = sha256;
    }
    ~Disc() override {
        if (chd) chd_close(chd);
    }
    const pce::CdToc &toc() const override { return table; }

    pce::ProgramTrackLookup program_track(std::uint32_t lba) const override {
        pce::ProgramTrackLookup result{true, {}};
        if (lba < table.leadout_lba) {
            if (!hunk_bytes) result.index = 0;
            else
                for (unsigned i = 0; i < tracks.size(); ++i)
                    if (lba >= tracks[i].start && lba - tracks[i].start < tracks[i].count) {
                        result.index = i;
                        break;
                    }
        }
        return result;
    }

    bool audio_playable(std::uint32_t lba) const override {
        if (!hunk_bytes || lba >= table.leadout_lba) return false;
        for (std::size_t i = 0; i < tracks.size(); ++i) {
            const auto &track = tracks[i];
            if (lba >= track.start && lba - track.start < track.count) return track.audio;
            if (lba < track.start && track.start - lba <= track.stored_pregap) return track.audio && i > 0 && tracks[i - 1].audio;
        }
        return false;
    }

    pce::AudioSector read_audio(std::uint32_t lba) override {
        if (!hunk_bytes) throw pce::Fault("ISO data sectors cannot be read as audio");
        auto it = std::find_if(tracks.begin(), tracks.end(), [lba](const auto &t) {
            return (lba >= t.start && lba - t.start < t.count) || (t.audio && lba < t.start && t.start - lba <= t.stored_pregap);
        });
        if (it == tracks.end()) throw pce::Fault("Audio LBA falls in a CHD gap or outside the disc");
        if (lba >= it->start && !it->audio) throw pce::Fault("MODE1 data sectors cannot be read as audio");
        const std::uint64_t frame = lba >= it->start ? it->frame + (lba - it->start) : it->frame - (it->start - lba);
        const std::uint8_t *data = frame_at(frame);
        pce::AudioSector samples{};
        // The audio of a CHD is big-endian, FLAC-decoded hunks included.
        for (unsigned i = 0; i < samples.size(); ++i) {
            const unsigned value = (unsigned(data[2 * i]) << 8) | data[2 * i + 1];
            samples[i] = static_cast<std::int16_t>(value < 32768 ? int(value) : int(value) - 65536);
        }
        return samples;
    }

    pce::Sector read(std::uint32_t lba) override {
        pce::Sector sector{};
        if (!hunk_bytes) {
            if (lba >= table.leadout_lba) throw pce::SectorReadError(pce::SectorReadReason::out_of_range, lba, "Sector LBA outside ISO");
            const std::uint64_t at = range.base + std::uint64_t(lba) * 2048;
            if (seek64(range.file, at) || std::fread(sector.data(), 1, sector.size(), range.file) != sector.size()) throw pce::Fault("Short sector image read");
            return sector;
        }
        if (lba >= table.leadout_lba) throw pce::SectorReadError(pce::SectorReadReason::out_of_range, lba, "Sector LBA falls in a CHD gap or outside the disc");
        auto it = std::find_if(tracks.begin(), tracks.end(), [lba](const auto &t) { return lba >= t.start && lba - t.start < t.count; });
        if (it == tracks.end()) throw pce::SectorReadError(pce::SectorReadReason::unrecoverable_data, lba, "Sector LBA falls in a CHD gap or outside the disc");
        if (it->audio) throw pce::SectorReadError(pce::SectorReadReason::wrong_data_track, lba, "Audio sectors cannot be read as MODE1 user data");
        const std::uint8_t *frame = frame_at(it->frame + lba - it->start);
        if (it->raw) {
            if (frame[0] != 0 || frame[11] != 0 || frame[15] != 1 || !std::all_of(frame + 1, frame + 11, [](auto c) { return c == 255; }))
                throw pce::SectorReadError(pce::SectorReadReason::media_data_error, lba, "Invalid CHD MODE1 raw sector header");
            frame += 16;
        }
        std::copy_n(frame, sector.size(), sector.begin());
        return sector;
    }
};
}  // namespace

std::shared_ptr<pce::SectorProvider> open_disc(const std::string &file, std::uint64_t offset, std::uint64_t length, const std::string &sha256) {
    return std::make_shared<Disc>(file, offset, length, sha256);
}
}  // namespace pcecd
