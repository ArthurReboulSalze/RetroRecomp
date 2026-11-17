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
#include "hostkit/hostkit_session.h"
#include "platform_io.h"
#include "rr_driver.h"
#include "runtime.h"
#include "state_envelope.h"

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
bool g_save_writes = true;           // off for a guest in a session: its cartridge save is never written
// A multiplayer session (hostkit_session.h), below: the session flag, the digest test switch, the clock the engine started on and the running hash of the mixed samples.
bool g_session = false;
uint64_t g_clock_at_start = 0;      // the session's clock the engine was started with (it reads its guest epoch once, at its start)
unsigned g_digest_every = 0;       // test switch RETRORECOMP_GBA_DIGEST=<n>: print the digest every n frames (never read in play); the sound is hashed as in a session
uint64_t g_audio_running = 1469598103934665603ull;     // the hash of every mixed sample so far, taken only in a session: the digest holds it

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

// RETRORECOMP_GBA_SHOTS (a test of the player, like the switches above) lists frames, separated by commas: the picture of each of them is written as
// `shot-<frame>.ppm` in the folder named by RETRORECOMP_GBA_SHOT_DIR, so that a route can be read from the pictures along it (tools/gba_route_captures.py).
std::vector<uint64_t> g_shot_frames;
std::string g_shot_dir;
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

void parse_shots() {
    const char* list = getenv("RETRORECOMP_GBA_SHOTS");
    const char* folder = getenv("RETRORECOMP_GBA_SHOT_DIR");
    if (!list || !folder || !*folder) return;
    g_shot_dir = folder;
    while (*list) {
        char* end = nullptr;
        const unsigned long long frame = strtoull(list, &end, 10);
        if (end == list) break;
        g_shot_frames.push_back(frame);
        list = *end == ',' ? end + 1 : end;
    }
}

void write_picture(FILE* file) {
    fprintf(file, "P6\n%d %d\n255\n", kWidth, kHeight);
    for (int i = 0; i < kWidth * kHeight; ++i) {
        const uint8_t rgb[3] = {static_cast<uint8_t>(g_pixels[i] >> 16), static_cast<uint8_t>(g_pixels[i] >> 8), static_cast<uint8_t>(g_pixels[i])};
        fwrite(rgb, 1, 3, file);
    }
}

void write_shot(uint64_t frame) {
    const std::string name = g_shot_dir + "/shot-" + std::to_string(frame) + ".ppm";
    if (FILE* file = fopen(name.c_str(), "wb")) {
        write_picture(file);
        fclose(file);
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
            if (g_rows) {                          // only a run that writes the rows hashes the sound: play is unchanged
                g_frame_sound = (g_frame_sound ^ static_cast<uint16_t>(block[i])) * 1099511628211ull;
                if (block[i]) g_frame_audible = true;
            }
            if (g_session || g_digest_every) g_audio_running = (g_audio_running ^ static_cast<uint16_t>(block[i])) * 1099511628211ull;
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

// A save file larger than the chip of this cartridge would stop the engine at its start (it refuses the file and the game never opens): it is set aside whole,
// as the other machines do with a file they cannot use, and the game starts without a save. A shorter file is read as far as it goes.
void set_aside_unusable_save() {
    if (RR_GBA_SAVE_LIMIT <= 0 || !g_save_path[0]) return;
    FILE* file = rr_fopen(g_save_path, L"rb");
    if (!file) return;
    fseek(file, 0, SEEK_END);
    const long size = ftell(file);
    fclose(file);
    if (size <= RR_GBA_SAVE_LIMIT) return;
    const std::wstring aside = std::wstring(g_save_path) + L".damaged";
    if (rr_replace(g_save_path, aside.c_str())) fprintf(stderr, "[host] a cartridge save larger than the chip (%ld bytes) was set aside\n", size);
}

void flush_battery() {
    if (!g_save_writes || !g_api->save_dirty()) return;     // a guest's cartridge save is never written (side_effects)
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

// The quick state file is the engine's own state inside the envelope the other machines share (state_envelope.h: a magic, a schema, a machine, the game's SHA-256, the length
// of the body and its CRC-32). The engine's format checks its magic, its version, the cartridge's SHA-1 and the structure of its sections but has no checksum of the memory it
// holds, so a byte flipped in the middle of the file was accepted. A file that was cut, grown or damaged anywhere, or that belongs to another game, is refused before the engine
// sees it; a file of the engine's own format (no envelope, written by an earlier build) is refused as well: quick states may break between releases. The body is the engine's
// bytes as they are: `g_state_blob` holds them on the way out and on the way in.
std::vector<uint8_t> g_state_blob;

void gba_state_body(RetroStateIO* io) {
    if (io->mode == RR_STATE_WRITE) {
        rr_state_bytes(io, g_state_blob.data(), g_state_blob.size());
    } else if (io->mode == RR_STATE_CHECK) {
        io->pos = io->size;
    } else {
        g_state_blob.assign(io->data + io->pos, io->data + io->size);
        io->pos = io->size;
    }
}

RetroStateEnvelope gba_state_envelope() {
    return RetroStateEnvelope{"RRGBAST" "\0", 1, 0, RR_GBA_ROM_SHA256, gba_state_body};
}

// A multiplayer session (hostkit_session.h): every seat runs the same simulation from the same start. The cartridge's clock runs on the guest's cycles from the session's one fixed
// time (the wall clock would differ between two PCs), the cartridge save is read as a game alone reads it (the boot digest holds it: two seats with another save are refused) and a
// guest never writes it (`side_effects`).

uint64_t fnv_bytes(uint64_t hash, const uint8_t* bytes, size_t size) {
    for (size_t i = 0; i < size; ++i) hash = (hash ^ bytes[i]) * 1099511628211ull;
    return hash;
}

uint32_t le32(const uint8_t* at) { return at[0] | at[1] << 8 | at[2] << 16 | static_cast<uint32_t>(at[3]) << 24; }

// The session's digest: the engine's state container (header, then sections tag | length | payload, little-endian, written field by field) read section by section.
// Kept: the CPU registers (the first 180 bytes: 16 + 1 + 3 x 6 + 2 x 5 words; what follows is the generated code's call stack, an artefact of how it runs), the memories and
// the bus, the registers, the cartridge save and the picture processing unit. Left out: the sound section (it holds the host's output ring and the cursors that follow the
// host's pace; the mixed samples are in `g_audio_running` instead), the counters and the timing of this process, and the mods. The same bytes on every PC for the same inputs.
uint64_t state_digest(uint64_t* parts = nullptr) {
    std::vector<uint8_t> blob;
    std::string error;
    if (!g_api || !g_api->save_state(blob, error)) return 0;
    constexpr size_t kHeader = 4 + 4 + 40 + 4, kCpuWords = 16 + 1 + 3 * 6 + 2 * 5;
    if (blob.size() < kHeader || memcmp(blob.data(), "GBAS", 4) != 0) return 0;
    uint64_t hash = 1469598103934665603ull;
    size_t at = kHeader;
    while (at + 8 <= blob.size()) {
        const uint32_t tag = le32(&blob[at]), length = le32(&blob[at + 4]);
        at += 8;
        if (length > blob.size() - at) return 0;
        const bool cpu = tag == 0x30555043u;            // "CPU0"
        const bool kept = cpu || tag == 0x30535542u || tag == 0x305F4F49u || tag == 0x30564153u || tag == 0x30555050u;   // BUS0, IO_0, SAV0, PPU0
        if (kept) {
            hash = fnv_bytes(hash, &blob[at - 8], 4);
            size_t head = cpu ? std::min<size_t>(length, kCpuWords * 4) : length, tail = 0;
            if (tag == 0x30535542u) {
                // The bus: the five memories (EWRAM, IWRAM, palette, VRAM, OAM), the last fetched word, the BIOS flag and the count of unmapped reads, then the cartridge clock chip
                // and the matrix, which are left out (the clock writes the host's own time even when no clock is fitted), and the three wait-state words at the end.
                constexpr size_t kMemories = 262144 + 32768 + 1024 + 98304 + 1024, kAfter = 4 + 1 + 8, kWaits = 12;
                if (length < kMemories + kAfter + kWaits) return 0;
                head = kMemories + kAfter;
                tail = kWaits;
            }
            hash = fnv_bytes(hash, &blob[at], head);
            if (tail) hash = fnv_bytes(hash, &blob[at + length - tail], tail);
            if (parts) {                                      // the test switch prints each section's own hash: which one differs between two runs
                const int slot = cpu ? 0 : tag == 0x30535542u ? 1 : tag == 0x305F4F49u ? 2 : tag == 0x30564153u ? 3 : 4;
                parts[slot] = fnv_bytes(fnv_bytes(1469598103934665603ull, &blob[at], head), &blob[at + length - tail], tail);
            }
        }
        at += length;
    }
    uint8_t sound[8];
    for (int i = 0; i < 8; ++i) sound[i] = static_cast<uint8_t>(g_audio_running >> (8 * i));
    return fnv_bytes(hash, sound, 8);
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
    for (const uint64_t frame : g_shot_frames)
        if (frame == g_frame_index) write_shot(frame);
    if (g_rows)
        fprintf(g_rows, "%llu,%016llx,%016llx,%d\n", static_cast<unsigned long long>(g_frame_index), static_cast<unsigned long long>(picture_hash()),
                static_cast<unsigned long long>(g_frame_sound), g_frame_audible ? 1 : 0);
    if (g_digest_every && g_frame_index % g_digest_every == 0) {
        uint64_t parts[5] = {0, 0, 0, 0, 0};
        const uint64_t first = state_digest(parts), second = state_digest();       // reading the digest must not change the machine: twice in a row is the same
        fprintf(stderr, "[digest] frame %llu %016llx cpu %016llx bus %016llx io %016llx save %016llx ppu %016llx sound %016llx%s\n", static_cast<unsigned long long>(g_frame_index),
                static_cast<unsigned long long>(first), static_cast<unsigned long long>(parts[0]), static_cast<unsigned long long>(parts[1]), static_cast<unsigned long long>(parts[2]),
                static_cast<unsigned long long>(parts[3]), static_cast<unsigned long long>(parts[4]), static_cast<unsigned long long>(g_audio_running), first == second && first ? "" : " UNSTABLE");
    }
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
uint64_t rrgba_digest(void) { return state_digest(); }
void rrgba_side_effects(bool allowed) { g_save_writes = allowed; }
// The session's clock (RRHK_SESSION_CLOCK, the same on every seat) is already the engine's guest epoch: the engine reads it once when it starts, which is before the kit's setup.
void rrgba_session_begin(uint64_t clock) {
    if (g_clock_at_start && clock != g_clock_at_start)
        fprintf(stderr, "[host] the session's clock (%llu) is not the one this machine started with (%llu): a cartridge clock would differ\n",
                static_cast<unsigned long long>(clock), static_cast<unsigned long long>(g_clock_at_start));
}
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
        const RetroStateEnvelope envelope = gba_state_envelope();
        const int read = rr_state_envelope_read(&envelope, bytes.data(), bytes.size());
        if (read == RR_STATE_INCOMPATIBLE) error = "a state of another game or of another version of this player";
        else if (read != RR_STATE_OK) error = "not a state of this player, or cut, grown or damaged";
        const bool loaded = read == RR_STATE_OK && g_api->load_state(g_state_blob, error);
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
    if (!g_api->save_state(g_state_blob, error)) return false;
    const RetroStateEnvelope envelope = gba_state_envelope();
    std::vector<uint8_t> file(RR_STATE_ENVELOPE_HEADER + g_state_blob.size());
    size_t size = 0;
    if (rr_state_envelope_write(&envelope, file.data(), file.size(), &size) != RR_STATE_OK) return false;
    file.resize(size);
    return write_atomically(path, file);
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
    parse_shots();
    parse_state_switch();
    g_selftest = getenv("RETRORECOMP_GBA_SELFTEST") != nullptr;
    // Every check (a scripted run, the self-test, the kit's frame limit) starts the cartridge's clock from a fixed time and moves it
    // with the guest's cycles, so two runs of the same script see the same seconds; a person playing keeps the host's clock.
    if (const char* every = getenv("RETRORECOMP_GBA_DIGEST")) g_digest_every = static_cast<unsigned>(std::max(0, atoi(every)));
    g_session = getenv(RRHK_SESSION_ENV) && *getenv(RRHK_SESSION_ENV) && !getenv("RETRORECOMP_HOST_TEST_FRAMES");
    if (g_session && !getenv("GBARECOMP_RTC_GUEST_EPOCH")) {
        g_clock_at_start = RRHK_SESSION_CLOCK;
        set_environment("GBARECOMP_RTC_GUEST_EPOCH", std::to_string(g_clock_at_start).c_str());
    } else if ((g_scripted || g_selftest || getenv("RETRORECOMP_HOST_TEST_FRAMES")) && !getenv("GBARECOMP_RTC_GUEST_EPOCH"))
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
    set_aside_unusable_save();
    int status = 0;
    do {
        g_restart = false;
        g_audio_running = 1469598103934665603ull;
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
