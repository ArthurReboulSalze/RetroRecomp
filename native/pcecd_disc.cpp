// PC Engine CD disc: a sector provider for the pinned pcenginerecomp runtime (native/pcecd_disc.h): a CHD (version 4 or 5), an ISO, or our packed form of a CUE sheet
// with its BIN files.
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

// A CUE sheet and its BIN files as one file (retrorecomp/pcecd_disc.py write_pack), all numbers little-endian: "RRCDPCK1", u32 track count, u32 lead-out LBA,
// then per track u32 start LBA, u32 sectors from index 01, u32 stored pregap sectors, u32 flags (1: raw 2352-byte data sectors, 2: audio), u32 bytes per
// sector, u32 zero, u64 offset (in the disc) of the sector of index 01. The stored pregap sectors precede that offset. Audio samples are little-endian.
constexpr char kPackMagic[8] = {'R', 'R', 'C', 'D', 'P', 'C', 'K', '1'};
std::uint32_t le32(const std::uint8_t *p) { return std::uint32_t(p[0]) | std::uint32_t(p[1]) << 8 | std::uint32_t(p[2]) << 16 | std::uint32_t(p[3]) << 24; }
std::uint64_t le64(const std::uint8_t *p) { return le32(p) | std::uint64_t(le32(p + 4)) << 32; }

class Disc final : public pce::SectorProvider {
    struct Track {
        std::uint32_t start, count;
        std::uint64_t frame;       // CHD: the frame of the image that holds the track's index 01; pack: the byte offset of that sector in the disc
        bool raw, audio;
        std::uint32_t stored_pregap = 0;
        std::uint32_t stride = 0;  // pack: bytes per sector
    };
    Range range;
    chd_file *chd = nullptr;
    bool packed = false;
    pce::CdToc table;
    std::vector<Track> tracks;
    std::uint32_t hunk_bytes = 0, cached = std::numeric_limits<std::uint32_t>::max();
    std::vector<std::uint8_t> cache;

    bool has_tracks() const { return hunk_bytes || packed; }

    void read_range(std::uint64_t at, void *out, std::size_t size) {
        if (at > range.size || size > range.size - at || seek64(range.file, range.base + at) || std::fread(out, 1, size, range.file) != size)
            throw pce::Fault("Short sector image read");
    }

    void pack_metadata() {
        std::uint8_t head[16];
        read_range(0, head, sizeof head);
        const std::uint32_t count = le32(head + 8), leadout = le32(head + 12);
        if (!count || count > 99 || !leadout || leadout > kMaxLba - 1) throw pce::Fault("Unsupported packed disc table");
        std::uint64_t cursor = 0;
        for (std::uint32_t i = 0; i < count; ++i) {
            std::uint8_t row[32];
            read_range(16 + std::uint64_t(i) * sizeof row, row, sizeof row);
            const std::uint32_t start = le32(row), length = le32(row + 4), pregap = le32(row + 8), flags = le32(row + 12), stride = le32(row + 16);
            const std::uint64_t offset = le64(row + 24);
            const bool raw = flags & 1u, audio = flags & 2u;
            if (flags > 2u || (raw && stride != 2352) || (audio && stride != 2352) || (!raw && !audio && stride != 2048) || !length || start < cursor ||
                std::uint64_t(start) + length > leadout || pregap > start || offset < std::uint64_t(pregap) * stride || offset > range.size ||
                std::uint64_t(length) * stride > range.size - offset)
                throw pce::Fault("Unsupported packed disc track");
            tracks.push_back({start, length, offset, raw, audio, pregap, stride});
            table.tracks[table.track_count++] = {start, static_cast<std::uint8_t>(audio ? 0 : 4)};
            cursor = std::uint64_t(start) + length;
        }
        table.leadout_lba = leadout;
        cache.resize(kFrame);
    }

    // The sector `relative` sectors from a track's index 01 (negative: its stored pregap): the CHD's 2,448-byte frame, or the pack's sector.
    const std::uint8_t *sector_of(const Track &track, std::int64_t relative) {
        if (!packed) return frame_at(static_cast<std::uint64_t>(static_cast<std::int64_t>(track.frame) + relative));
        read_range(static_cast<std::uint64_t>(static_cast<std::int64_t>(track.frame) + relative * std::int64_t(track.stride)), cache.data(), track.stride);
        return cache.data();
    }

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
        } else if (std::memcmp(magic.data(), kPackMagic, sizeof kPackMagic) == 0) {
            packed = true;
            pack_metadata();
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
            if (!has_tracks()) result.index = 0;
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
        if (!has_tracks() || lba >= table.leadout_lba) return false;
        for (std::size_t i = 0; i < tracks.size(); ++i) {
            const auto &track = tracks[i];
            if (lba >= track.start && lba - track.start < track.count) return track.audio;
            if (lba < track.start && track.start - lba <= track.stored_pregap) return track.audio && i > 0 && tracks[i - 1].audio;
        }
        return false;
    }

    pce::AudioSector read_audio(std::uint32_t lba) override {
        if (!has_tracks()) throw pce::Fault("ISO data sectors cannot be read as audio");
        auto it = std::find_if(tracks.begin(), tracks.end(), [lba](const auto &t) {
            return (lba >= t.start && lba - t.start < t.count) || (t.audio && lba < t.start && t.start - lba <= t.stored_pregap);
        });
        if (it == tracks.end()) throw pce::Fault("Audio LBA falls in a CHD gap or outside the disc");
        if (lba >= it->start && !it->audio) throw pce::Fault("MODE1 data sectors cannot be read as audio");
        const std::uint8_t *data = sector_of(*it, std::int64_t(lba) - std::int64_t(it->start));
        pce::AudioSector samples{};
        // The audio of a CHD is big-endian, FLAC-decoded hunks included; a pack's is little-endian.
        for (unsigned i = 0; i < samples.size(); ++i) {
            const unsigned value = packed ? unsigned(data[2 * i]) | unsigned(data[2 * i + 1]) << 8 : (unsigned(data[2 * i]) << 8) | data[2 * i + 1];
            samples[i] = static_cast<std::int16_t>(value < 32768 ? int(value) : int(value) - 65536);
        }
        return samples;
    }

    pce::Sector read(std::uint32_t lba) override {
        pce::Sector sector{};
        if (!has_tracks()) {
            if (lba >= table.leadout_lba) throw pce::SectorReadError(pce::SectorReadReason::out_of_range, lba, "Sector LBA outside ISO");
            const std::uint64_t at = range.base + std::uint64_t(lba) * 2048;
            if (seek64(range.file, at) || std::fread(sector.data(), 1, sector.size(), range.file) != sector.size()) throw pce::Fault("Short sector image read");
            return sector;
        }
        if (lba >= table.leadout_lba) throw pce::SectorReadError(pce::SectorReadReason::out_of_range, lba, "Sector LBA falls in a CHD gap or outside the disc");
        auto it = std::find_if(tracks.begin(), tracks.end(), [lba](const auto &t) { return lba >= t.start && lba - t.start < t.count; });
        if (it == tracks.end()) throw pce::SectorReadError(pce::SectorReadReason::unrecoverable_data, lba, "Sector LBA falls in a CHD gap or outside the disc");
        if (it->audio) throw pce::SectorReadError(pce::SectorReadReason::wrong_data_track, lba, "Audio sectors cannot be read as MODE1 user data");
        const std::uint8_t *frame = sector_of(*it, std::int64_t(lba) - std::int64_t(it->start));
        if (it->raw) {
            if (frame[0] != 0 || frame[11] != 0 || frame[15] != 1 || !std::all_of(frame + 1, frame + 11, [](auto c) { return c == 255; }))
                throw pce::SectorReadError(pce::SectorReadReason::media_data_error, lba, "Invalid MODE1 raw sector header");
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
