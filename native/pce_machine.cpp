// PC Engine machine: a bridge from the C host of a Retro-Recomp game to the pinned pcenginerecomp runtime.
// It sets up the HuCard reset recipe the engine's own headless host uses (continuous video, interrupts, PSG,
// pads, queued VDC accesses, deterministic power-on), runs whole frames under one execution policy, and hands
// out the picture, the PCM, the counters and in-memory checkpoints. Nothing of the engine is patched.
// Original RetroRecomp code: MIT. The engine keeps its own MIT terms (licenses/pcenginerecomp.md).
#include "pce_machine.h"

#include "pce/cartridge.hpp"
#include "pce/checkpoint.hpp"
#include "pce/code_capture.hpp"
#include "pce/runtime.hpp"

#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <exception>
#include <filesystem>
#include <memory>
#include <optional>
#include <span>
#include <string>
#include <vector>

namespace {
constexpr std::uint64_t kFrameTicks = 1365ull * 262ull;   // one NTSC HuC6260 frame in master ticks
constexpr std::uint64_t kFnvBasis = 14695981039346656037ull, kFnvPrime = 1099511628211ull;

struct Machine {
    pce::Bus bus;
    pce::Cpu cpu;
};

struct Recipe {
    std::vector<std::uint8_t> file;
    pce::HuCardHeader header = pce::HuCardHeader::none;
    pce::HuCardEncoding encoding = pce::HuCardEncoding::linear;
    pce::HuCardProfile profile = pce::HuCardProfile::base;
    unsigned buttons = 2;
    bool multitap = false;
};

Recipe recipe;
std::unique_ptr<Machine> machine;
std::unique_ptr<pce::CodeCapture> capture;
pce::ExecutionPolicy policy = pce::ExecutionPolicy::hybrid;
std::uint16_t pads[PCE_PADS];
std::uint32_t pixels[PCE_MAX_WIDTH * PCE_MAX_HEIGHT];
unsigned picture_width, picture_height;
std::uint64_t last_sequence, frames, cropped_frames;
std::vector<std::int16_t> audio;

void message(char *error, std::size_t size, const char *text) {
    if (error && size) std::snprintf(error, size, "%s", text);
}

std::uint64_t fnv(std::uint64_t hash, const void *data, std::size_t size) {
    const auto *bytes = static_cast<const std::uint8_t *>(data);
    for (std::size_t n = 0; n < size; ++n) hash = (hash ^ bytes[n]) * kFnvPrime;
    return hash;
}

std::unique_ptr<Machine> build() {
    auto fresh = std::make_unique<Machine>();
    auto &bus = fresh->bus;
    const auto decoded = pce::decode_hucard(recipe.file, recipe.header, recipe.encoding, recipe.profile);
    bus.configure_hucard(recipe.profile, decoded.rom);
    bus.enable_continuous_video();
    bus.enable_interrupts();
    bus.enable_psg();
    if (bus.vdc.raster.enabled) bus.vdc.queued_cpu_accesses = true;     // the engine host's default profile
    bus.enable_joypad(false, false);                                     // the engine host's default region (usa)
    bus.joypad.set_multitap(recipe.multitap);
    for (unsigned slot = 0; slot < PCE_PADS; ++slot) {
        bus.joypad.set_type(slot, recipe.buttons);
        bus.joypad.set_pressed(slot, 0);
    }
    bus.power_on_cpu(fresh->cpu);
    bus.enable_audio_output(pce::AudioProfile::raw, PCE_AUDIO_RATE, pce::AudioTiming::gear);
    return fresh;
}

void publish() {
    const auto &frame = machine->bus.vdc.video.completed();
    unsigned width = frame.width, height = frame.height;
    if (width > PCE_MAX_WIDTH || height > PCE_MAX_HEIGHT) {
        ++cropped_frames;
        width = std::min<unsigned>(width, PCE_MAX_WIDTH);
        height = std::min<unsigned>(height, PCE_MAX_HEIGHT);
    }
    if (frame.rgb.size() < std::size_t(frame.width) * frame.height * 3) width = height = 0;
    for (unsigned y = 0; y < height; ++y)
        for (unsigned x = 0; x < width; ++x) {
            const std::uint8_t *rgb = &frame.rgb[(std::size_t(y) * frame.width + x) * 3];
            pixels[y * PCE_MAX_WIDTH + x] = 0xFF000000u | (std::uint32_t(rgb[0]) << 16) | (std::uint32_t(rgb[1]) << 8) | rgb[2];
        }
    picture_width = width;
    picture_height = height;
}

void drain() {
    if (!machine->bus.pcm.enabled) return;
    const auto samples = machine->bus.pcm.drain();
    audio.insert(audio.end(), samples.begin(), samples.end());
    // A host that never reads (headless without PCM) keeps at most one second.
    const std::size_t keep = PCE_AUDIO_RATE * 2;
    if (audio.size() > keep) audio.erase(audio.begin(), audio.end() - keep);
}

template <class Body> int guarded(char *error, std::size_t size, Body body) {
    try {
        body();
        return 1;
    } catch (const std::exception &failure) {
        message(error, size, failure.what());
    } catch (...) {
        message(error, size, "unknown engine failure");
    }
    return 0;
}
}  // namespace

extern "C" {

int pce_machine_init(const uint8_t *file, size_t size, int copier_header, int bit_reversed, int board,
                     int pad_buttons, int multitap, char *error, size_t error_size) {
    return guarded(error, error_size, [&] {
        if (!file || !size) throw pce::Fault("no HuCard image");
        if (pad_buttons != 2 && pad_buttons != 6) throw pce::Fault("pads have two or six buttons");
        recipe.file.assign(file, file + size);
        recipe.header = copier_header ? pce::HuCardHeader::copier512 : pce::HuCardHeader::none;
        recipe.encoding = bit_reversed ? pce::HuCardEncoding::bit_reversed : pce::HuCardEncoding::linear;
        recipe.profile = board == PCE_BOARD_SF2 ? pce::HuCardProfile::sf2 : pce::HuCardProfile::base;
        recipe.buttons = unsigned(pad_buttons);
        recipe.multitap = multitap != 0;
        machine = build();
        last_sequence = machine->bus.vdc.video.sequence();
        frames = cropped_frames = 0;
        picture_width = picture_height = 0;
        audio.clear();
        std::memset(pads, 0, sizeof pads);
    });
}

int pce_machine_reset(char *error, size_t error_size) {
    return guarded(error, error_size, [&] {
        if (recipe.file.empty()) throw pce::Fault("the machine was never started");
        machine = build();
        last_sequence = machine->bus.vdc.video.sequence();
        audio.clear();
        std::memset(pads, 0, sizeof pads);
    });
}

void pce_machine_policy(int value) {
    policy = value == PCE_POLICY_REFERENCE ? pce::ExecutionPolicy::interpreter_only
           : value == PCE_POLICY_NATIVE_ONLY ? pce::ExecutionPolicy::native_only : pce::ExecutionPolicy::hybrid;
}

void pce_machine_set_pads(const uint16_t masks[PCE_PADS]) {
    for (unsigned slot = 0; slot < PCE_PADS; ++slot) pads[slot] = masks[slot] & 0x0FFF;
}

int pce_machine_run_frame(char *error, size_t error_size) {
    return guarded(error, error_size, [&] {
        if (!machine) throw pce::Fault("the machine was never started");
        auto &bus = machine->bus;
        auto &cpu = machine->cpu;
        for (unsigned slot = 0; slot < PCE_PADS; ++slot) bus.joypad.set_pressed(slot, pads[slot]);
        const std::uint64_t deadline = cpu.ticks + 8 * kFrameTicks;
        while (bus.vdc.video.sequence() == last_sequence) {
            if (cpu.ticks >= deadline) throw pce::Fault("no picture was published within eight frames");
            std::optional<pce::CodeCapture::Pending> pending;
            if (capture) pending = capture->before(bus, cpu);
            const auto status = pce::step(bus, cpu, deadline, policy);
            if (capture) capture->after(*pending, cpu);
            if (status == pce::Exit::miss || status == pce::Exit::unsupported) {
                char text[160];
                std::snprintf(text, sizeof text, "%s at pc $%04X (mpr %02X %02X %02X %02X %02X %02X %02X %02X)",
                              pce::exit_name(status), cpu.pc, cpu.mpr[0], cpu.mpr[1], cpu.mpr[2], cpu.mpr[3],
                              cpu.mpr[4], cpu.mpr[5], cpu.mpr[6], cpu.mpr[7]);
                throw pce::Fault(text);
            }
        }
        last_sequence = bus.vdc.video.sequence();
        ++frames;
        publish();
        drain();
    });
}

const uint32_t *pce_machine_pixels(unsigned *width, unsigned *height) {
    if (width) *width = picture_width;
    if (height) *height = picture_height;
    return pixels;
}

unsigned pce_machine_dot_clock(void) { return machine ? machine->bus.vce.control & 3u : 0u; }

size_t pce_machine_audio(int16_t *out, size_t capacity) {
    const std::size_t count = std::min(capacity & ~std::size_t(1), audio.size());
    if (count) {
        std::copy(audio.begin(), audio.begin() + std::ptrdiff_t(count), out);
        audio.erase(audio.begin(), audio.begin() + std::ptrdiff_t(count));
    }
    return count;
}

void pce_machine_counters(PceCounters *counters) {
    if (!counters) return;
    *counters = PceCounters{};
    if (!machine) return;
    const auto &cpu = machine->cpu;
    *counters = PceCounters{cpu.native_steps, cpu.interpreter_steps, cpu.guard_misses, cpu.irq_entries,
                            frames, cropped_frames};
}

uint64_t pce_machine_cpu_hash(void) {
    if (!machine) return 0;
    const auto &cpu = machine->cpu;
    std::uint8_t registers[8] = {cpu.a, cpu.x, cpu.y, cpu.sp, cpu.p, std::uint8_t(cpu.pc), std::uint8_t(cpu.pc >> 8),
                                 cpu.mpr_latch};
    std::uint64_t hash = fnv(kFnvBasis, registers, sizeof registers);
    hash = fnv(hash, cpu.mpr.data(), cpu.mpr.size());
    hash = fnv(hash, &cpu.ticks, sizeof cpu.ticks);
    return fnv(hash, &cpu.cycles, sizeof cpu.cycles);
}

uint64_t pce_machine_ram_hash(void) {
    if (!machine) return 0;
    return fnv(kFnvBasis, machine->bus.bytes->data() + 0xF8 * 0x2000, 0x2000);
}

uint8_t *pce_machine_state_save(size_t *size) {
    if (!machine || !size) return nullptr;
    try {
        const auto encoded = pce::encode_checkpoint(machine->bus, machine->cpu);
        auto *copy = static_cast<std::uint8_t *>(std::malloc(encoded.size()));
        if (!copy) return nullptr;
        std::memcpy(copy, encoded.data(), encoded.size());
        *size = encoded.size();
        return copy;
    } catch (...) {
        return nullptr;
    }
}

int pce_machine_state_load(const uint8_t *data, size_t size) {
    if (!machine || !data || !size) return 0;
    try {
        pce::restore_checkpoint(machine->bus, machine->cpu, std::span<const std::uint8_t>(data, size));
        last_sequence = machine->bus.vdc.video.sequence();
        audio.clear();
        return 1;
    } catch (...) {
        return 0;
    }
}

void pce_machine_free(void *data) { std::free(data); }

int pce_machine_capture_begin(const char *path, unsigned capacity, char *error, size_t error_size) {
    return guarded(error, error_size, [&] {
        if (capture) throw pce::Fault("code capture already started");
        const auto name = std::filesystem::path(std::u8string(reinterpret_cast<const char8_t *>(path)));
        capture = std::make_unique<pce::CodeCapture>(name, capacity);
    });
}

int pce_machine_capture_finish(char *error, size_t error_size) {
    return guarded(error, error_size, [&] {
        if (!capture) return;
        capture->finish();
        capture.reset();
    });
}

void pce_machine_shutdown(void) {
    capture.reset();
    machine.reset();
    recipe = Recipe{};
    audio.clear();
}

}  // extern "C"
