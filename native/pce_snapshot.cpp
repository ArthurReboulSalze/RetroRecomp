// PC Engine: the in-process snapshot and the digest (pce_snapshot.h). Read docs/PC_ENGINE.md, "Multiplayer", for the design.
//
// Why not the engine's checkpoint (pce::encode_checkpoint / restore_checkpoint): it is a developer file format. It writes the whole 2 MiB backing array (the ROM
// with it), allocates for every save, and a restore builds a second machine and compares every ROM byte through a function call. Rollback saves a state every
// frame and loads one for every correction, so this snapshot copies only what changes (the card's RAM banks, the VDC and its video state, the VCE, the
// interrupt and pad state, the CPU) into a buffer the caller owns, and reads it back in place.
//
// How it stays complete: the field lists below are the engine's own (runtime/src/checkpoint.cpp, MIT), minus the ROM and the configuration that never
// changes after the machine is built. The engine's audio side is written by its own functions (checkpoint::write_audio / read_audio). The probe in
// native/pce_snapshot_checks.cpp proves completeness against the engine: after a load, the engine's full checkpoint of the machine equals the one taken at the
// save, at every frame of a program that keeps every device busy, so a field the engine adds at a new pin fails that check.
//
// The format is fieldwise little-endian, never a struct image, and is a local quick state: it is never written to a file or sent.
// Original RetroRecomp code: MIT. The engine keeps its own MIT terms (licenses/pcenginerecomp.md).
#include "pce_snapshot.h"

#include "pce_machine_internal.hpp"

#include "pce/checkpoint_archive.hpp"
#include "pce/checkpoint_audio.hpp"
#include "pce/runtime.hpp"
#include "pce/scanline.hpp"

#include <algorithm>
#include <array>
#include <bit>
#include <cstring>
#include <exception>
#include <memory>
#include <span>
#include <type_traits>
#include <vector>

static_assert(std::endian::native == std::endian::little, "the snapshot is written as the machine holds it: little-endian hosts only");

// VideoOutput names this struct a friend for the engine's own checkpoint. The private fields of the video output (the latches and the two frame
// buffers) are read through it here as well; the members have names of their own, so they never meet the engine's.
namespace pce {
struct CheckpointAccess {
    template <class A, class T> static void video_core(A &ar, T &v) {
        ar(v.enabled);
        ar(v.indices_, v.sequence_, v.completed_ticks_, v.lines_rendered_, v.pixels_rendered_, v.x_, v.row_, v.line_width_, v.scroll_x_, v.scroll_y_,
           v.counter_y_, v.control_, v.mode_, v.y_pending_, v.increment_, v.burst_, v.active_, v.latch_x_clock_, v.latch_y_clock_,
           v.byr_lsb_write_clock_, v.bxr_written_before_latch_);
    }
    static VideoFrame &front(VideoOutput &v) { return v.front_; }
    static VideoFrame &back(VideoOutput &v) { return v.back_; }
    static const VideoFrame &front(const VideoOutput &v) { return v.front_; }
    static const VideoFrame &back(const VideoOutput &v) { return v.back_; }
};
}  // namespace pce

namespace {
using std::uint16_t;
using std::uint32_t;
using std::uint64_t;
using std::uint8_t;

constexpr uint8_t kMagic[8] = {'P', 'C', 'E', 'S', 'N', 'A', 'P', 1};
constexpr uint32_t kVersion = 1;
constexpr size_t kHeader = 32;                 // magic, version, core length, total length, reserved, checksum
constexpr size_t kFrameCapacity = 640u * 264u * 3u;    // the most one frame buffer holds in a snapshot: the bridge's picture limit (PCE_MAX_WIDTH x PCE_MAX_HEIGHT), the engine allows 1024 x 512
constexpr size_t kAudioCapacity = 192u * 1024u;       // the engine's audio side: the 8,192-frame PCM ring and the 64 KiB of ADPCM RAM dominate
constexpr size_t kBankBytes = 0x2000;

template <class> constexpr bool dependent_false = false;
template <class T> struct is_std_array : std::false_type {};
template <class T, size_t N> struct is_std_array<std::array<T, N>> : std::true_type {};

// The two archives: Out writes into the caller's buffer, In reads from it. Integers and bools are written as the machine holds them (a little-endian
// host, asserted above), an array of integers in one copy, an enumeration as 32 bits. Anything else is refused at compile time.
class Out {
public:
    Out(uint8_t *data, size_t capacity) : data_(data), capacity_(capacity) {}
    template <class... Ts> void operator()(const Ts &...values) { (put(values), ...); }
    void bytes(const void *source, size_t count) {
        if (count > capacity_ - size_) { overflow_ = true; return; }
        if (count) std::memcpy(data_ + size_, source, count);
        size_ += count;
    }
    size_t size() const { return size_; }
    bool ok() const { return !overflow_; }
    uint8_t *data() const { return data_; }
private:
    uint8_t *data_;
    size_t capacity_, size_ = 0;
    bool overflow_ = false;
    template <class T> void put(const T &item) {
        if constexpr (std::is_same_v<T, bool>) { const uint8_t byte = item ? 1 : 0; bytes(&byte, 1); }
        else if constexpr (std::is_enum_v<T>) { const uint32_t value = static_cast<uint32_t>(item); bytes(&value, 4); }
        else if constexpr (std::is_integral_v<T>) bytes(&item, sizeof item);
        else if constexpr (is_std_array<T>::value) {
            using E = typename T::value_type;
            if constexpr (std::is_arithmetic_v<E> && !std::is_same_v<E, bool>) bytes(item.data(), item.size() * sizeof(E));
            else for (const auto &element : item) put(element);
        } else static_assert(dependent_false<T>, "a snapshot field needs an explicit writer");
    }
};

class In {
public:
    In(const uint8_t *data, size_t size) : data_(data), size_(size) {}
    template <class... Ts> void operator()(Ts &...values) { (get(values), ...); }
    void bytes(void *target, size_t count) {
        if (count > size_ - position_) { underflow_ = true; std::memset(target, 0, count); return; }
        if (count) std::memcpy(target, data_ + position_, count);
        position_ += count;
    }
    size_t position() const { return position_; }
    bool ok() const { return !underflow_; }
    bool done() const { return !underflow_ && position_ == size_; }
private:
    const uint8_t *data_;
    size_t size_, position_ = 0;
    bool underflow_ = false;
    template <class T> void get(T &item) {
        if constexpr (std::is_same_v<T, bool>) { uint8_t byte = 0; bytes(&byte, 1); item = byte != 0; }
        else if constexpr (std::is_enum_v<T>) { uint32_t value = 0; bytes(&value, 4); item = static_cast<T>(value); }
        else if constexpr (std::is_integral_v<T>) bytes(&item, sizeof item);
        else if constexpr (is_std_array<T>::value) {
            using E = typename T::value_type;
            if constexpr (std::is_arithmetic_v<E> && !std::is_same_v<E, bool>) bytes(item.data(), item.size() * sizeof(E));
            else for (auto &element : item) get(element);
        } else static_assert(dependent_false<T>, "a snapshot field needs an explicit reader");
    }
};

// ---- the field lists (the engine's, runtime/src/checkpoint.cpp) ----

template <class A, class T> void cpu_core(A &ar, T &c) {
    ar(c.a, c.x, c.y, c.sp, c.p, c.pc, c.mpr, c.mpr_latch, c.ticks, c.cycles, c.vdc_wait_ticks, c.clock_divisor, c.irq_sampled, c.irq_vector,
       c.irq_entries, c.rti_steps);
}
// How the code ran, not what the guest is: left out of the digest, so that builds that differ in their native code agree.
template <class A, class T> void cpu_counters(A &ar, T &c) {
    ar(c.native_steps, c.interpreter_steps, c.guard_misses, c.native_block_steps, c.interpreter_block_steps, c.block_bytes);
}
template <class A, class T> void raster_state(A &ar, T &r) {
    ar(r.enabled, r.hsync, r.vsync, r.compare_pending, r.blank_consumed, r.control, r.master_ticks, r.frames, r.vblank_events, r.rcr_events, r.hclock, r.line,
       r.dot, r.vdc_line, r.raster_line, r.divider, r.total_lines, r.h_state, r.v_state, r.h_remaining, r.v_remaining, r.event_remaining, r.event, r.horizontal,
       r.vertical);
}
template <class A, class T> void vdc_core(A &ar, T &v) {
    ar(v.enabled, v.irq1, v.selected, v.status, v.reg, *v.vram, v.read_buffer, v.vram_bus_latch, v.queued_cpu_accesses, v.pending_vram_read,
       v.pending_vram_write, v.vram_transfer_delay, v.vram_cpu_cycles, v.load_bg_start_clock, v.load_bg_end_clock, v.hsync_start_clock, v.reads, v.writes,
       v.vram_changes);
    raster_state(ar, v.raster);
    pce::CheckpointAccess::video_core(ar, v.video);
    ar(v.satb);
    for (auto &row : v.sprite_rows) ar(row.x, row.index, row.flip, row.palette, row.front, row.planes);
    ar(v.sprite_count, v.sprite_overflow, v.sprite_burst, v.sprite_active, v.sprite_control, v.sprite_mode, v.dma_enabled, v.satb_armed, v.satb_pending,
       v.vram_dma_pending, v.dma_source, v.dma_dest, v.dma_words, v.satb_words);
}
template <class A, class T> void joypad_state(A &ar, T &j) {
    ar(j.enabled, j.japanese, j.cd, j.multitap, j.sel, j.clr, j.extra, j.selected, j.latched);
    for (auto &p : j.pads) ar(p.buttons, p.pressed);
    ar(j.reads, j.writes);
}
template <class A, class T> void interrupt_state(A &ar, T &i) {
    ar(i.enabled, i.timer_enabled, i.timer_pending, i.mask, i.external, i.timer_reload, i.timer_counter, i.timer_frozen_phase, i.master_ticks, i.timer_deadline,
       i.entries, i.reads, i.writes);
}

size_t ram_banks(const pce::Bus &bus) {
    size_t count = 0;
    for (const auto kind : bus.kind) count += kind == pce::BankKind::ram;
    return count;
}
// Only the standard HuCard boards: a CD, an ADPCM unit or an Arcade Card is a machine this snapshot does not describe.
bool supported(const pce::Bus &bus) {
    return bus.hucard && bus.system_card == pce::SystemCardProfile::none && !bus.arcade_card && !bus.cd.enabled && !bus.adpcm.enabled &&
           (bus.hucard_profile == pce::HuCardProfile::base || bus.hucard_profile == pce::HuCardProfile::sf2);
}

// The part of the state that decides future frames and is the same whatever the native code was: the digest hashes exactly these bytes.
template <class A, class B, class C> void core(A &ar, B &bus, C &cpu) {
    cpu_core(ar, cpu);
    ar(bus.kind, bus.hucard_mapper_latch);
    for (size_t bank = 0; bank < 256; ++bank) {
        if (bus.kind[bank] != pce::BankKind::ram) continue;
        ar.bytes(bus.bytes->data() + bus.backing_address(static_cast<uint32_t>(bank) << 13), kBankBytes);
    }
    vdc_core(ar, bus.vdc);
    ar(bus.vce.enabled, bus.vce.control, bus.vce.address, bus.vce.palette, bus.vce.reads, bus.vce.writes);
    joypad_state(ar, bus.joypad);
    interrupt_state(ar, bus.irq);
    ar(bus.io_latch, bus.work_ram_mirrors);
}

uint64_t hash_bytes(const uint8_t *data, size_t size) {
    uint64_t h = 0x243F6A8885A308D3ull ^ size;
    size_t i = 0;
    for (; i + 8 <= size; i += 8) {
        uint64_t word;
        std::memcpy(&word, data + i, 8);
        h = (h ^ word) * 0x9E3779B97F4A7C15ull;
        h ^= h >> 29;
    }
    uint64_t tail = 0;
    for (unsigned shift = 0; i < size; ++i, shift += 8) tail |= static_cast<uint64_t>(data[i]) << shift;
    h = (h ^ tail) * 0x9E3779B97F4A7C15ull;
    h ^= h >> 32;
    h *= 0xD6E8FEB86659FD93ull;
    return h ^ (h >> 32);
}

std::unique_ptr<pce::checkpoint::Writer> audio_writer;    // made by the first save: it reserves 8 MiB, which a game that never joins a session does not need
std::vector<uint8_t> digest_scratch;

size_t core_bound(const pce::Bus &bus) {
    // The VRAM, the sprite and video latches, the CPU, the VCE and the timer, and the card's RAM banks; 16 KiB cover everything else the lists write.
    return 64 * 1024 + 64 * 1024 + 16 * 1024 + ram_banks(bus) * kBankBytes;
}

void put32(uint8_t *at, uint32_t value) { std::memcpy(at, &value, 4); }
void put64(uint8_t *at, uint64_t value) { std::memcpy(at, &value, 8); }
uint32_t get32(const uint8_t *at) { uint32_t value; std::memcpy(&value, at, 4); return value; }
uint64_t get64(const uint8_t *at) { uint64_t value; std::memcpy(&value, at, 8); return value; }

// A frame buffer is picture output, never guest state (the engine clears the back buffer at every frame start and the completed frame is only read by the host),
// so it never decides a save: its size is kept, its pixels up to kFrameCapacity (a frame wider or taller than the bridge's picture limit keeps the first
// part, and the rest is black after a load).
void write_frame(Out &out, const pce::VideoFrame &frame) {
    const uint32_t stored = static_cast<uint32_t>(std::min(frame.rgb.size(), kFrameCapacity));
    out(frame.width, frame.height, stored);
    out.bytes(frame.rgb.data(), stored);
}
void read_frame(In &in, pce::VideoFrame &frame) {
    uint32_t width = 0, height = 0, stored = 0;
    in(width, height, stored);
    if (!in.ok() || width > 1024 || height > 512 || stored > kFrameCapacity || stored > static_cast<size_t>(width) * height * 3) {
        frame.width = frame.height = 0;
        frame.rgb.clear();
        return;
    }
    frame.width = width;
    frame.height = height;
    frame.rgb.resize(static_cast<size_t>(width) * height * 3);       // within the 1.5 MiB the engine reserved: no allocation
    in.bytes(frame.rgb.data(), stored);
    std::fill(frame.rgb.begin() + stored, frame.rgb.end(), uint8_t(0));
}
// What a snapshot is checked by: its payload and the header fields after the magic.
uint64_t checksum(const uint8_t *base, size_t total) {
    return hash_bytes(base + kHeader, total - kHeader) * 0x9E3779B97F4A7C15ull + hash_bytes(base + 8, 16);
}
}  // namespace

extern "C" {

size_t pce_snapshot_bound(void) {
    const auto *bus = pce_bridge::bus();
    if (!bus) return 0;
    return kHeader + core_bound(*bus) + 4096 + 4 + kAudioCapacity + 2 * (12 + kFrameCapacity);
}

size_t pce_snapshot_save(void *buffer, size_t capacity) {
    auto *bus = pce_bridge::bus();
    auto *cpu = pce_bridge::cpu();
    if (!bus || !cpu || !buffer || capacity < kHeader || !supported(*bus)) return 0;
    try {
        if (!audio_writer) audio_writer = std::make_unique<pce::checkpoint::Writer>();
        audio_writer->data.clear();
        pce::settle_silent_cd_source(*bus);
        pce::checkpoint::write_audio(*audio_writer, *bus);
        if (audio_writer->data.size() > kAudioCapacity) return 0;
        auto *base = static_cast<uint8_t *>(buffer);
        Out out(base + kHeader, capacity - kHeader);
        const auto &constant_bus = *bus;
        const auto &constant_cpu = *cpu;
        core(out, constant_bus, constant_cpu);
        const size_t core_length = out.size();
        cpu_counters(out, constant_cpu);
        out(constant_bus.generation);
        out(pce_bridge::frame_count(), pce_bridge::cropped_count());
        out(static_cast<uint32_t>(audio_writer->data.size()));
        out.bytes(audio_writer->data.data(), audio_writer->data.size());
        write_frame(out, pce::CheckpointAccess::front(constant_bus.vdc.video));
        write_frame(out, pce::CheckpointAccess::back(constant_bus.vdc.video));
        if (!out.ok()) return 0;
        const size_t total = kHeader + out.size();
        std::memcpy(base, kMagic, 8);
        put32(base + 8, kVersion);
        put32(base + 12, static_cast<uint32_t>(core_length));
        put32(base + 16, static_cast<uint32_t>(total));
        put32(base + 20, 0);
        put64(base + 24, checksum(base, total));
        return total;
    } catch (const std::exception &) {
        return 0;
    }
}

int pce_snapshot_load(const void *buffer, size_t size) {
    auto *bus = pce_bridge::bus();
    auto *cpu = pce_bridge::cpu();
    if (!bus || !cpu || !buffer || size < kHeader || size > pce_snapshot_bound() || !supported(*bus)) return 0;
    const auto *base = static_cast<const uint8_t *>(buffer);
    if (std::memcmp(base, kMagic, 8) != 0 || get32(base + 8) != kVersion || get32(base + 16) != size) return 0;
    const size_t core_length = get32(base + 12);
    if (core_length > size - kHeader || checksum(base, size) != get64(base + 24)) return 0;
    try {
        const uint8_t old_latch = bus->hucard_mapper_latch;
        In in(base + kHeader, size - kHeader);
        core(in, *bus, *cpu);
        if (!in.ok() || in.position() != core_length) return 0;
        cpu_counters(in, *cpu);
        in(bus->generation);
        in(pce_bridge::frame_count(), pce_bridge::cropped_count());
        uint32_t audio_length = 0;
        in(audio_length);
        if (!in.ok() || audio_length > kAudioCapacity) return 0;
        const size_t audio_at = kHeader + in.position();
        if (audio_length > size - audio_at) return 0;
        pce::checkpoint::Reader audio(std::span<const uint8_t>(base + audio_at, audio_length));
        pce::checkpoint::read_audio(audio, *bus);
        audio.finish();
        In frames(base + audio_at + audio_length, size - audio_at - audio_length);
        read_frame(frames, pce::CheckpointAccess::front(bus->vdc.video));
        read_frame(frames, pce::CheckpointAccess::back(bus->vdc.video));
        if (!frames.done()) return 0;
        // SF2: the physical window follows the bank latch (the engine keeps the whole file apart and copies the selected quarter in).
        if (bus->hucard_profile == pce::HuCardProfile::sf2 && bus->hucard_mapper_latch != old_latch)
            std::copy_n(bus->hucard_mapper_rom.begin() + 0x80000 + static_cast<size_t>(bus->hucard_mapper_latch & 3) * 0x80000, 0x80000,
                        bus->bytes->begin() + 0x80000);
        pce_bridge::published_sequence_is(bus->vdc.video.sequence());
        pce_bridge::drop_audio();
        return 1;
    } catch (const std::exception &) {
        return 0;
    }
}

uint64_t pce_snapshot_digest(void) {
    const auto *bus = pce_bridge::bus();
    const auto *cpu = pce_bridge::cpu();
    if (!bus || !cpu || !supported(*bus)) return 0;
    const size_t bound = core_bound(*bus);
    if (digest_scratch.size() < bound) digest_scratch.resize(bound);
    Out out(digest_scratch.data(), digest_scratch.size());
    core(out, *bus, *cpu);
    if (!out.ok()) return 0;
    return hash_bytes(digest_scratch.data(), out.size());
}

}  // extern "C"
