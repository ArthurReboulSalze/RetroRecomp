// gba_machine.cpp: the Game Boy Advance player's entry and machine. Original Retro-Recomp code (MIT); it links the pinned
// engine (mstan/gbarecomp, PolyForm Noncommercial), which keeps its own terms.
//
// main() hands the engine its cartridge and system ROM (linked into the executable, checked by size and SHA-1 as a file would
// be) and a driver. run_game() builds the machine as it always does, then calls the driver instead of its own window loop;
// the driver runs the host kit's loop (rrhk_main), which asks this file for one frame at a time through the C functions of
// gba_machine.h. Sound comes out of the machine as mono blocks at 32768 Hz times a power of two, and goes to the kit at 32768 Hz.
#ifndef SDL_MAIN_HANDLED
#define SDL_MAIN_HANDLED
#endif
#include <SDL.h>

#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <utility>
#include <vector>

#include "embedded_resources.h"
#include "gba_game.h"
#include "gba_machine.h"
#include "hostkit/hostkit.h"
#include "platform_io.h"
#include "rr_driver.h"
#include "runtime.h"

namespace {

constexpr int kWidth = 240, kHeight = 160;
constexpr uint32_t kOutputRate = 32768;
constexpr size_t kRingSamples = 1u << 16;
constexpr uint64_t kFlushFrames = 120;   // a battery that changed is written out at most every two seconds of play

const gbarecomp::RrDriverApi* g_api = nullptr;
bool g_restart = false, g_failed = false;
uint32_t g_pixels[kWidth * kHeight];
int16_t g_ring[kRingSamples];
size_t g_head = 0, g_tail = 0;     // the ring: samples in [tail, head)
int32_t g_sum = 0;
uint32_t g_sum_count = 0;
uint64_t g_since_flush = 0;
wchar_t g_save_path[2048];

// Test switches, like the kit's RETRORECOMP_HOST_TEST_*: RETRORECOMP_GBA_INPUT names a script in the engine's own format
// (`frame,0xKEYS`, active low) that replaces the player's keys; RETRORECOMP_GBA_DUMP names a P6 file that receives the last
// picture when the player closes. Neither is read in play.
std::vector<std::pair<uint64_t, uint16_t>> g_script;
bool g_scripted = false;
uint64_t g_frame_index = 0;
uint64_t g_audio_taken = 0, g_audio_nonzero = 0;
int g_audio_peak = 0;
bool g_selftest = false;
int g_selftest_phase = 0;
uint64_t g_state_hash = 0;

// RETRORECOMP_GBA_ROWS (a test of the player, like the switches above) names a text file that receives one line per frame,
// `frame,picture,sound,audible` (the two hashes in hexadecimal; audible is 1 when a sample of the frame was not zero): what the
// conversion compares between the build and the compressed copy it delivers, and counts to say that the picture and the sound change.
FILE* g_rows = nullptr;
uint64_t g_frame_sound = 1469598103934665603ull;
bool g_frame_audible = false;

// RETRORECOMP_GBA_STATE (a test of the player, like the switches above) presses F8 and F9 at chosen frames: `save@N` writes the
// quick state at the end of frame N; `load@K=N` loads it at the end of frame K and counts from N afterwards (the frame the state
// was saved at), so that a key script goes on where the saving process left it. Steps are separated by commas. Used by
// tools/gba_fresh_process.py to load a state in a process that never ran the frames the state holds.
struct StateStep {
    bool load;
    uint64_t at, resume;
    bool done;
};
std::vector<StateStep> g_state_steps;

void parse_state_switch() {
    const char* text = getenv("RETRORECOMP_GBA_STATE");
    while (text && *text) {
        char* end = nullptr;
        const bool load = strncmp(text, "load@", 5) == 0;
        if (!load && strncmp(text, "save@", 5) != 0) break;
        StateStep step = {load, strtoull(text + 5, &end, 10), 0, false};
        if (load && end && *end == '=') step.resume = strtoull(end + 1, &end, 10);
        else if (load) step.resume = step.at;
        g_state_steps.push_back(step);
        text = end && *end == ',' ? end + 1 : nullptr;
    }
}

void open_rows() {
    const char* path = getenv("RETRORECOMP_GBA_ROWS");
    if (path && *path) g_rows = fopen(path, "w");
}

void load_script() {
    const char* path = getenv("RETRORECOMP_GBA_INPUT");
    FILE* file = path ? fopen(path, "r") : nullptr;
    if (!file) return;
    char line[256];
    while (fgets(line, sizeof line, file)) {
        unsigned long long frame = 0;
        unsigned keys = 0;
        if (line[0] != '#' && sscanf(line, "%llu,%x", &frame, &keys) == 2) g_script.emplace_back(frame, static_cast<uint16_t>(keys));
    }
    fclose(file);
    g_scripted = true;
}

uint16_t scripted_pressed() {
    uint16_t held = 0x3FF;
    for (const auto& event : g_script)
        if (event.first <= g_frame_index) held = event.second;
    return static_cast<uint16_t>(~held & 0x3FF);
}

void report_stats() {
    if (!getenv("RETRORECOMP_GBA_DUMP")) return;
    fprintf(stderr, "[host] frames=%llu audio_samples=%llu audio_nonzero=%llu audio_peak=%d interpreted=%llu\n",
            static_cast<unsigned long long>(g_frame_index), static_cast<unsigned long long>(g_audio_taken),
            static_cast<unsigned long long>(g_audio_nonzero), g_audio_peak,
            static_cast<unsigned long long>(g_api ? g_api->interpreted_instructions() : 0));
}

void dump_picture() {
    report_stats();
    const char* path = getenv("RETRORECOMP_GBA_DUMP");
    FILE* file = path ? fopen(path, "wb") : nullptr;
    if (!file) return;
    fprintf(file, "P6\n%d %d\n255\n", kWidth, kHeight);
    for (int i = 0; i < kWidth * kHeight; ++i) {
        const uint8_t rgb[3] = {static_cast<uint8_t>(g_pixels[i] >> 16), static_cast<uint8_t>(g_pixels[i] >> 8), static_cast<uint8_t>(g_pixels[i])};
        fwrite(rgb, 1, 3, file);
    }
    fclose(file);
}

void push_sample(int16_t sample) {
    g_ring[g_head % kRingSamples] = sample;
    ++g_head;
    if (g_head - g_tail > kRingSamples) g_tail = g_head - kRingSamples;   // the oldest is dropped, never the newest
}

// The machine's sound blocks come at 32768 << n Hz: the average of 2^n samples is one output sample, so a block is cut at a
// whole number of them and the rest waits for the next.
void take_sound() {
    int16_t block[4096];
    uint32_t rate = 0;
    for (;;) {
        const size_t count = g_api->drain_audio(block, 4096, &rate);
        if (!count) break;
        const uint32_t ratio = rate >= kOutputRate && rate % kOutputRate == 0 ? rate / kOutputRate : 1;
        for (size_t i = 0; i < count; ++i) {
            g_frame_sound = (g_frame_sound ^ static_cast<uint16_t>(block[i])) * 1099511628211ull;
            if (block[i]) g_frame_audible = true;
            g_sum += block[i];
            if (++g_sum_count >= ratio) {
                push_sample(static_cast<int16_t>(g_sum / static_cast<int32_t>(g_sum_count)));
                g_sum = 0;
                g_sum_count = 0;
            }
        }
    }
}

void take_picture() {
    int width = 0, height = 0;
    const uint8_t* rgb = g_api->picture(&width, &height);
    if (!rgb || width != kWidth || height != kHeight) return;
    for (int i = 0; i < kWidth * kHeight; ++i)
        g_pixels[i] = 0xFF000000u | static_cast<uint32_t>(rgb[3 * i]) << 16 | static_cast<uint32_t>(rgb[3 * i + 1]) << 8 | rgb[3 * i + 2];
}

// `datas`, then its sub-folder: the folders of a path the engine or the kit is about to write.
void make_parent_folders(const wchar_t* path) {
    wchar_t folder[2048];
    wcsncpy(folder, path, 2047);
    folder[2047] = 0;
    wchar_t* slash = wcsrchr(folder, L'\\');
    if (!slash) slash = wcsrchr(folder, L'/');
    if (!slash) return;
    *slash = 0;
    wchar_t* parent = wcsrchr(folder, L'\\');
    if (!parent) parent = wcsrchr(folder, L'/');
    if (parent) {
        const wchar_t kept = *parent;
        *parent = 0;
        rr_mkdir(folder);
        *parent = kept;
    }
    rr_mkdir(folder);
}

bool write_atomically(const wchar_t* path, const std::vector<uint8_t>& bytes) {
    make_parent_folders(path);
    wchar_t temporary[2300];
    swprintf(temporary, 2300, L"%ls.tmp-%lu", path, rr_process_id());
    FILE* file = rr_fopen(temporary, L"wb");
    if (!file) return false;
    const bool wrote = fwrite(bytes.data(), 1, bytes.size(), file) == bytes.size() && rr_flush_file(file);
    fclose(file);
    if (wrote && rr_replace(temporary, path)) return true;
    rr_remove(temporary);
    return false;
}

void flush_battery() {
    if (!g_api->save_dirty()) return;
    make_parent_folders(g_save_path);
    if (!g_api->flush_save()) fprintf(stderr, "[host] the cartridge save could not be written\n");
}

int driver(const gbarecomp::RrDriverApi& api) {
    g_api = &api;
    int scale = 3;
    if (const char* env = getenv("RETRORECOMP_SCALE")) scale = std::max(1, atoi(env));
    const int status = rrhk_main(rrhk_adapter(), RR_GBA_TITLE, scale);
    flush_battery();
    dump_picture();
    if (g_rows) {
        fclose(g_rows);
        g_rows = nullptr;
    }
    g_api = nullptr;
    return g_failed ? 1 : status;
}

void set_environment(const char* name, const char* value) {
#ifdef _WIN32
    _putenv_s(name, value);
#else
    setenv(name, value, 1);
#endif
}

bool state_location(wchar_t* path, size_t capacity, const char* folder, const char* suffix) {
    return rr_game_data_file(path, capacity, folder, RR_GBA_NAME, RR_GBA_ROM_SHA1, suffix) != 0;
}

uint64_t picture_hash() {
    uint64_t hash = 1469598103934665603ull;
    for (uint32_t pixel : g_pixels) hash = (hash ^ pixel) * 1099511628211ull;
    return hash;
}

}  // namespace

extern "C" {

static void run_selftest(void);
static void run_state_switch(void);

bool rrgba_frame(uint16_t pressed) {
    if (!g_api || g_restart) return false;
    if (g_scripted) pressed = scripted_pressed();
    g_api->set_keyinput(static_cast<uint16_t>(~pressed & 0x3FF));
    ++g_frame_index;
    g_frame_sound = 1469598103934665603ull;
    g_frame_audible = false;
    if (!g_api->step_frame()) {
        g_failed = true;
        return false;
    }
    take_picture();
    take_sound();
    if (g_rows)
        fprintf(g_rows, "%llu,%016llx,%016llx,%d\n", static_cast<unsigned long long>(g_frame_index), static_cast<unsigned long long>(picture_hash()),
                static_cast<unsigned long long>(g_frame_sound), g_frame_audible ? 1 : 0);
    if (g_selftest) run_selftest();
    if (!g_state_steps.empty()) run_state_switch();
    if (++g_since_flush >= kFlushFrames) {
        g_since_flush = 0;
        flush_battery();
    }
    return true;
}

const uint32_t* rrgba_pixels(void) { return g_pixels; }

size_t rrgba_audio(int16_t* pcm, size_t capacity) {
    size_t count = 0;
    while (count < capacity && g_tail != g_head) pcm[count++] = g_ring[g_tail++ % kRingSamples];
    g_audio_taken += count;
    for (size_t i = 0; i < count; ++i) {
        if (pcm[i]) ++g_audio_nonzero;
        g_audio_peak = std::max(g_audio_peak, std::abs(static_cast<int>(pcm[i])));
    }
    return count;
}

void rrgba_reset(void) { g_restart = true; }
uint64_t rrgba_interpreted(void) { return g_api ? g_api->interpreted_instructions() : 0; }
uint64_t rrgba_frames(void) { return g_api ? g_api->frames() : 0; }

bool rrgba_state_path(wchar_t* path, size_t capacity) { return state_location(path, capacity, "states", ".rrstate"); }

bool rrgba_state_file(const wchar_t* path, bool load) {
    if (!g_api || !path || !path[0]) return false;
    std::string error;
    if (load) {
        FILE* file = rr_fopen(path, L"rb");
        if (!file) return false;
        std::vector<uint8_t> bytes;
        uint8_t chunk[65536];
        size_t got;
        while ((got = fread(chunk, 1, sizeof chunk, file)) > 0) bytes.insert(bytes.end(), chunk, chunk + got);
        fclose(file);
        const bool loaded = g_api->load_state(bytes, error);
        if (loaded) {
            g_head = g_tail = 0;       // the sound of the moment the state was taken is not played over the restored one
            g_sum = 0;
            g_sum_count = 0;
            take_picture();
        } else {
            fprintf(stderr, "[host] quick state refused: %s\n", error.c_str());
        }
        return loaded;
    }
    std::vector<uint8_t> bytes;
    return g_api->save_state(bytes, error) && write_atomically(path, bytes);
}

static void run_state_switch(void) {
    for (StateStep& step : g_state_steps) {
        if (step.done || step.at != g_frame_index) continue;
        step.done = true;
        wchar_t path[2048];
        const bool ok = rrgba_state_path(path, 2048) && rrgba_state_file(path, step.load);
        fprintf(stderr, "[state] %s at frame %llu %s\n", step.load ? "load" : "save", static_cast<unsigned long long>(step.at),
                ok ? "ok" : "FAILED");
        if (ok && step.load) g_frame_index = step.resume;
        break;   // a load moves the frame count: the next step is looked at on the next frame
    }
}

// RETRORECOMP_GBA_SELFTEST=1 (a test of the player, like the switches above): the quick state is saved at frame 200, the machine
// runs to frame 260 and its picture is hashed, the state is loaded, the same 60 frames run again, and the two pictures must be
// the same. The result is one line on stderr.
static void run_selftest(void) {
    wchar_t path[2048];
    static bool power_cycled = false;
    if (getenv("RETRORECOMP_GBA_SELFTEST")[0] == '2') {      // a power cycle at frame 100: the machine is built again
        if (!power_cycled && g_frame_index == 100) {
            power_cycled = true;
            rrgba_reset();
        }
        return;
    }
    if (g_selftest_phase == 0 && g_frame_index == 200) {
        const bool saved = rrgba_state_path(path, 2048) && rrgba_state_file(path, false);
        if (!saved) fprintf(stderr, "[selftest] state save FAILED\n");
        g_selftest_phase = 1;
    } else if (g_selftest_phase == 1 && g_frame_index == 260) {
        g_state_hash = picture_hash();
        const bool loaded = rrgba_state_path(path, 2048) && rrgba_state_file(path, true);
        if (!loaded) fprintf(stderr, "[selftest] state load FAILED\n");
        g_frame_index = 200;
        g_selftest_phase = 2;
    } else if (g_selftest_phase == 2 && g_frame_index == 260) {
        fprintf(stderr, "[selftest] quick state round trip %s\n", picture_hash() == g_state_hash ? "PASSED" : "FAILED: the picture differs");
        g_selftest_phase = 3;
    }
}

}  // extern "C"

int main(int argc, char** argv) {
    (void)argc;
    const std::string program = argv[0];
    size_t rom_size = 0, bios_size = 0;
    const void* rom = rr_resource(RR_GBA_ROM_RESOURCE, &rom_size);
    const void* bios = rr_resource(RR_GBA_BIOS_RESOURCE, &bios_size);
    if (!rom || !bios) {
        fprintf(stderr, "[host] this executable does not carry its cartridge or its system ROM\n");
        return 1;
    }
    gbarecomp::g_rr_embedded_rom = {static_cast<const uint8_t*>(rom), rom_size};
    gbarecomp::g_rr_embedded_bios = {static_cast<const uint8_t*>(bios), bios_size};
    gbarecomp::g_rr_driver = driver;
    load_script();
    open_rows();
    parse_state_switch();
    g_selftest = getenv("RETRORECOMP_GBA_SELFTEST") != nullptr;
    // Every check (a scripted run, the self-test, the kit's frame limit) starts the cartridge's clock from a fixed time and moves it
    // with the guest's cycles, so two runs of the same script see the same seconds; a person playing keeps the host's clock.
    if ((g_scripted || g_selftest || getenv("RETRORECOMP_HOST_TEST_FRAMES")) && !getenv("GBARECOMP_RTC_GUEST_EPOCH"))
        set_environment("GBARECOMP_RTC_GUEST_EPOCH", "1767225600");
    // The player compiles nothing at run time (the engine's self-heal recompiler stays off) and keeps what the engine says about
    // its own coverage, with the addresses the interpreter ran, in `datas/learning`, not beside the executable.
    if (!getenv("GBARECOMP_SELFHEAL_RECOMPILE")) set_environment("GBARECOMP_SELFHEAL_RECOMPILE", "0");
    wchar_t learning[2048];
    char learning_utf8[4096];
    if (!getenv("GBARECOMP_MISS_FRAG") && state_location(learning, 2048, "learning", ".misses.toml") &&
        rr_to_utf8(learning, learning_utf8, sizeof learning_utf8)) {
        set_environment("GBARECOMP_MISS_FRAG", learning_utf8);
        make_parent_folders(learning);
    }
    if (!getenv("GBARECOMP_COVERAGE_JSON") && state_location(learning, 2048, "learning", ".coverage.json") &&
        rr_to_utf8(learning, learning_utf8, sizeof learning_utf8))
        set_environment("GBARECOMP_COVERAGE_JSON", learning_utf8);
    wchar_t save[2048];
    char save_utf8[4096] = "";
    if (state_location(save, 2048, "saves", ".sav") && rr_to_utf8(save, save_utf8, sizeof save_utf8))
        wcsncpy(g_save_path, save, 2047);
    int status = 0;
    do {
        g_restart = false;
        if (g_selftest) fprintf(stderr, "[selftest] machine built, frame %llu\n", static_cast<unsigned long long>(g_frame_index));
        std::string rom_sha1 = RR_GBA_ROM_SHA1, no_window = "--no-window", quiet = "--quiet", rom_flag = "--rom-sha1",
                    save_flag = "--save", save_value = save_utf8;
        std::vector<char*> arguments = {const_cast<char*>(program.c_str()), &rom_flag[0], &rom_sha1[0], &no_window[0], &quiet[0]};
        if (save_utf8[0]) {
            arguments.push_back(&save_flag[0]);
            arguments.push_back(&save_value[0]);
        }
        status = gbarecomp::run_game(static_cast<int>(arguments.size()), arguments.data());
    } while (g_restart && status == 0);
    return status;
}
