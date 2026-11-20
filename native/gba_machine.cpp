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
#include <array>
#include <memory>
#include <span>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
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
// The link cable (below): the engine's session and its cable hub only (never its recomp-net / rbengine network layer).
#include "gba_bios.h"
#include "multiplayer_launch.h"
#include "multiplayer_session.h"
#include "multiplayer_view.h"
#include "self_heal.h"

// The engine's session fallback (our patch, docs/UPSTREAMS.md): an address with no generated function is run by the interpreter, one instruction at a time, counted.
extern "C" int g_runtime_session_interp_fallback;
extern "C" unsigned long long g_runtime_session_fallback_entries, g_runtime_session_fallback_distinct;

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

// The link cable (RETRORECOMP_GBA_LINK=<2..4>, docs/GAME_BOY_ADVANCE.md "The link cable"): the engine's own session (`GbaMultiplayerSession`: N complete consoles on one
// cable, in this process, on one common timeline) replaces the single machine that run_game() builds. Every PC runs all the consoles; only the pad words travel.
// Each seat k plays console k, and this PC shows and plays the sound of its own seat's console only.
std::unique_ptr<gbarecomp::GbaMultiplayerSession> g_link;
unsigned g_link_seats = 0;                           // 0: no cable (the single machine); else the number of consoles on it
unsigned g_link_local = 0;                           // the console this PC shows (its seat)
const gbarecomp::GbaNetplayBoot* g_link_boot = nullptr;   // the engine's verified images and chip, alive while run_game() is in the link
// Only the console this PC shows is drawn (RETRORECOMP_GBA_LINK_RASTER=1: every console draws its own picture, the way the first version did, for a comparison): the consoles run with
// the rasterizer off, as the engine's own runner runs them (nothing the guest reads depends on it), and the local one is watched by the engine's presentation mirror (`GbaNetplayPresentation`),
// which draws the same 240 x 160 picture from the scanlines the console sends. The canonical state of every console is then the same on every PC whichever seat it shows.
std::unique_ptr<gbarecomp::GbaNetplayPresentation> g_link_view;
int g_link_view_seat = -1;                           // the console the mirror watches now (-1: none yet)
bool g_link_raster = false;
std::vector<uint8_t> g_link_image;                   // the cartridge save image every console plays on (the host's): the chip's bytes, empty: none
bool g_link_slices = true;                           // the engine's own product setting: native instruction batching between device events
struct LinkRow {
    uint64_t frame;
    std::array<uint16_t, 4> pads;
};
std::vector<LinkRow> g_link_script;                  // test switch RETRORECOMP_GBA_LINK_INPUTS: the engine's route files (`frame pad0 pad1 [pad2 pad3]`, pressed = 1)
std::array<uint16_t, 4> g_link_held{};
bool g_link_unwritten = false;                       // the first console's chip held a change when a restart built the consoles again: still to write at a clean end

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

uint64_t interpreted_any();   // defined with the link helpers below

void write_picture(FILE* file) {
    fprintf(file, "P6\n%d %d\n255\n", kWidth, kHeight);
    for (int i = 0; i < kWidth * kHeight; ++i) {
        const uint8_t rgb[3] = {static_cast<uint8_t>(g_pixels[i] >> 16), static_cast<uint8_t>(g_pixels[i] >> 8), static_cast<uint8_t>(g_pixels[i])};
        fwrite(rgb, 1, 3, file);
    }
}

void write_shot(uint64_t frame) {
    const std::string name = g_shot_dir + "/shot-" + std::to_string(frame) + (g_link ? "-seat" + std::to_string(g_link_local + 1) : std::string()) + ".ppm";
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
            static_cast<unsigned long long>(interpreted_any()));
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

// The console this PC plays: the single machine, or in the link the one of its seat.
gba::GbaBus* link_bus() { return g_link ? &g_link->input_machine(g_link_local).bus : nullptr; }
gba::GbaPpu* link_ppu() { return g_link ? &g_link->input_machine(g_link_local).ppu : nullptr; }

size_t drain_any(int16_t* out, size_t capacity, uint32_t* rate) {
    if (g_link) {
        uint32_t block_rate = 0;
        const size_t count = link_bus()->audio().drain_sample_block(out, capacity, block_rate);
        *rate = block_rate;
        return count;
    }
    return g_api->drain_audio(out, capacity, rate);
}

const uint8_t* picture_any(int* width, int* height) {
    if (g_link) {
        *width = kWidth;
        *height = kHeight;
        if (g_link_view) return g_link_view->width() == kWidth && g_link_view->height() == kHeight ? g_link_view->pixels() : nullptr;   // null until a whole frame was drawn: the picture before stays
        return link_ppu()->has_latched_framebuffer() ? link_ppu()->latched_framebuffer() : nullptr;
    }
    return g_api->picture(width, height);
}

uint64_t interpreted_any() {
    return g_link ? static_cast<uint64_t>(gbarecomp::self_heal_interpreted_insns()) : g_api ? g_api->interpreted_instructions() : 0;
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
        const size_t count = drain_any(block, 4096, &rate);
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
    const uint8_t* rgb = picture_any(&width, &height);
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
    if (g_link || !g_save_writes || !g_api->save_dirty()) return;     // the link writes its save only at a clean end (rrgba_session_save_commit); a guest's cartridge save is never written (side_effects)
    make_parent_folders(g_save_path);
    if (!g_api->flush_save()) fprintf(stderr, "[host] the cartridge save could not be written\n");
}

void discard_unwritten_save();   // defined with the state helpers below

int driver(const gbarecomp::RrDriverApi& api) {
    g_api = &api;
    int scale = 3;
    if (const char* env = getenv("RETRORECOMP_SCALE")) scale = std::max(1, atoi(env));
    const int status = rrhk_main(rrhk_adapter(), RR_GBA_TITLE, scale);
    if (g_save_writes) flush_battery();
    else discard_unwritten_save();
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

constexpr uint32_t kSaveTag = 0x30564153u;     // "SAV0": the cartridge save's section of the engine's state container
std::vector<uint8_t> g_boot_state;             // a session only: the machine's state before its first frame, kept for the host's restart

// The payload of the section `tag` of the engine's state container (the 52-byte header, then sections: tag | length | payload).
bool find_section(const std::vector<uint8_t>& blob, uint32_t tag, size_t* offset, size_t* length) {
    size_t at = 4 + 4 + 40 + 4;
    while (at + 8 <= blob.size()) {
        const uint32_t found = le32(&blob[at]), size = le32(&blob[at + 4]);
        at += 8;
        if (size > blob.size() - at) return false;
        if (found == tag) {
            *offset = at;
            *length = size;
            return true;
        }
        at += size;
    }
    return false;
}

// The engine writes its cartridge save itself when run_game() returns, whatever the player decided. A seat that must not write one (a guest, or a host whose match did not end
// cleanly: side_effects stays off) has the save marked unchanged first (the section's second field), so the engine finds nothing to write.
void discard_unwritten_save() {
    std::vector<uint8_t> state;
    std::string error;
    size_t at = 0, length = 0;
    if (!g_api || !g_api->save_dirty() || !g_api->save_state(state, error) || !find_section(state, kSaveTag, &at, &length) || length < 2) return;
    state[at + 1] = 0;
    g_api->load_state(state, error);
}

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

// ---- The link cable ----------------------------------------------------------------------------------------------------------------------------------------------------
// The engine's session is built as its own product runner builds it (multiplayer_runner.cpp), minus its window and its network: the consoles share the BIOS and the cartridge,
// each has its own chip (every one holds the host's save image: the match's rule is one save for everyone), a clock, and the same code (the generated functions bind the console
// that runs). A console's picture and sound are read from its own PPU and audio unit; the other consoles' sound is dropped every frame.
void link_configure_save(gba::GbaSave& save, const gbarecomp::SaveConfiguration& chip) {
    switch (chip.type) {
    case gba::SaveType::SRAM: save.configure_sram(chip.size); break;
    case gba::SaveType::EEPROM: save.configure_eeprom(chip.size); break;
    case gba::SaveType::Flash512:
    case gba::SaveType::Flash1M: save.configure_flash(chip.size); break;
    default: break;      // no chip
    }
}

std::vector<uint8_t> link_chip_bytes(const gba::GbaSave& save) {
    return save.sram_enabled() ? save.sram_bytes() : save.flash_enabled() ? save.flash_bytes() : save.eeprom_enabled() ? save.eeprom_bytes() : std::vector<uint8_t>();
}

bool link_load_chip(gba::GbaSave& save, const std::vector<uint8_t>& bytes) {
    if (bytes.empty()) return true;
    const bool ok = save.flash_enabled() ? save.load_flash_bytes(bytes.data(), bytes.size())
                    : save.sram_enabled() ? save.load_sram_bytes(bytes.data(), bytes.size())
                                          : save.eeprom_enabled() && save.load_eeprom_bytes(bytes.data(), bytes.size());
    if (ok) save.clear_dirty();
    return ok;
}

std::vector<uint8_t> read_save_file(const wchar_t* path) {
    std::vector<uint8_t> bytes;
    if (FILE* file = path && path[0] ? rr_fopen(path, L"rb") : nullptr) {
        uint8_t chunk[65536];
        for (size_t got; (got = fread(chunk, 1, sizeof chunk, file)) > 0;) bytes.insert(bytes.end(), chunk, chunk + got);
        fclose(file);
    }
    return bytes;
}

// The session's clock: a session's (the same on every seat), else a scripted run's fixed time, else the host's own.
int64_t link_clock() {
    if (g_clock_at_start) return static_cast<int64_t>(g_clock_at_start);
    if (const char* epoch = getenv("GBARECOMP_RTC_GUEST_EPOCH")) return strtoll(epoch, nullptr, 10);
    return static_cast<int64_t>(time(nullptr));
}

// The consoles, from power-on, on the image `g_link_image` (the host's chip; empty: a blank chip). The first time, the player's own file is the image.
bool link_build() {
    using namespace gbarecomp;
    const GbaNetplayBoot& boot = *g_link_boot;
    // An address no generated function covers (the code only a cable runs, which a single player's observation never reaches) is run by the interpreter, counted, instead of stopping the
    // match; RETRORECOMP_GBA_LINK_FALLBACK=0 is the test switch that brings the engine's own stop back (a maintainer's probe of the reviewed roots).
    const char* fallback = getenv("RETRORECOMP_GBA_LINK_FALLBACK");
    g_runtime_session_interp_fallback = fallback && atoi(fallback) == 0 ? 0 : 1;
    try {
        GbaSessionConfig config;
        GbaLinkGroup cable{GbaLinkMedium::Cable, {}};
        for (unsigned id = 0; id < g_link_seats; ++id) {
            config.machines.push_back({id, "retro-recomp-gba-link", boot.expected_rom_sha1});
            cable.machines.push_back(id);
            config.input_machines.push_back(id);
        }
        config.links = {std::move(cable)};
        g_link = std::make_unique<GbaMultiplayerSession>(std::move(config));
        g_link->set_native_slices(g_link_slices);
        const int64_t clock = link_clock();
        for (unsigned id = 0; id < g_link_seats; ++id) {
            auto& machine = g_link->machine(id);
            machine.bus.set_bios(boot.bios);
            machine.bus.set_rom(boot.rom->data(), boot.rom->size());
            link_configure_save(machine.bus.save(), boot.save);
            machine.bus.rtc().set_emulated_clock(clock);
            if (!g_link_raster) machine.ppu.set_rasterization_enabled(false);
            if (!link_load_chip(machine.bus.save(), g_link_image))
                fprintf(stderr, "[host] the cartridge save (%zu bytes) does not fit this game's chip: console %u starts on a blank one\n", g_link_image.size(), id + 1);
        }
        g_link->discard_audio_output();
        g_link_view_seat = -1;
        if (!g_link_raster && !g_link_view) {
            g_link_view = std::make_unique<GbaNetplayPresentation>(GbaNetplayViewPolicy{}, false, 1);
            g_link_view->request_width(kWidth);
        }
    } catch (const std::exception& error) {
        fprintf(stderr, "[host] the link cable could not be set up: %s\n", error.what());
        g_link.reset();
        return false;
    }
    return true;
}

uint64_t link_digest() {
    if (!g_link) return 0;
    try {
        const std::vector<uint8_t> blob = g_link->save_state();
        return fnv_bytes(1469598103934665603ull, blob.data(), blob.size());
    } catch (const std::exception&) {
        return 0;
    }
}

// One frame of every console: the pad words in seat order (pressed = 1, the hardware KEYINPUT bits). A route file of the engine (`frame pad0 pad1 ...`) replaces them in a test.
bool link_step(uint16_t first, uint16_t second) {
    std::array<uint16_t, 4> pads = {first, second, 0, 0};
    if (!g_link_script.empty()) {
        for (const LinkRow& row : g_link_script)
            if (row.frame <= g_frame_index) g_link_held = row.pads;
        pads = g_link_held;
    }
    const int seat = rrhk_session_seat();
    if (seat >= 0 && static_cast<unsigned>(seat) < g_link_seats) g_link_local = static_cast<unsigned>(seat);
    if (g_link_view && g_link_view_seat != static_cast<int>(g_link_local)) {      // the mirror watches the console of this PC's seat (known from SETUP, before the first frame)
        if (g_link_view_seat >= 0) g_link->input_machine(static_cast<unsigned>(g_link_view_seat)).ppu.set_presentation_observer(nullptr);
        g_link->input_machine(g_link_local).ppu.set_presentation_observer(g_link_view.get());
        g_link_view_seat = static_cast<int>(g_link_local);
    }
    try {
        g_link->run_frame(std::span<const uint16_t>(pads.data(), g_link_seats));
    } catch (const std::exception& error) {
        fprintf(stderr, "[host] the link cable stopped: %s\n", error.what());
        return false;
    }
    return true;
}

void load_link_route() {
    const char* path = getenv("RETRORECOMP_GBA_LINK_INPUTS");
    FILE* file = path ? fopen(path, "r") : nullptr;
    if (!file) return;
    char line[256];
    while (fgets(line, sizeof line, file)) {
        unsigned long long frame = 0;
        unsigned pad[4] = {0, 0, 0, 0};
        if (line[0] != '#' && sscanf(line, "%llu %i %i %i %i", &frame, &pad[0], &pad[1], &pad[2], &pad[3]) >= 3)
            g_link_script.push_back({frame, {static_cast<uint16_t>(pad[0] & 0x3FF), static_cast<uint16_t>(pad[1] & 0x3FF), static_cast<uint16_t>(pad[2] & 0x3FF), static_cast<uint16_t>(pad[3] & 0x3FF)}});
    }
    fclose(file);
}

// What run_game() calls instead of building the single machine and calling the driver (the engine's netplay branch, taken with our own `run`): the consoles, then the host kit's loop.
int link_run(const gbarecomp::GbaNetplayLaunch&, const gbarecomp::GbaNetplayBoot& boot) {
    g_link_boot = &boot;
    if (const char* slices = getenv("RETRORECOMP_GBA_LINK_SLICES")) g_link_slices = atoi(slices) != 0;
    if (const char* raster = getenv("RETRORECOMP_GBA_LINK_RASTER")) g_link_raster = atoi(raster) != 0;
    g_link_image = read_save_file(g_save_path);
    if (const char* seat = getenv("RETRORECOMP_GBA_LINK_SEAT")) g_link_local = std::min<unsigned>(g_link_seats - 1, static_cast<unsigned>(std::max(0, atoi(seat))));
    int status = 1;
    if (link_build()) {
        int scale = 3;
        if (const char* env = getenv("RETRORECOMP_SCALE")) scale = std::max(1, atoi(env));
        status = rrhk_main(rrhk_adapter(), RR_GBA_TITLE, scale);
        dump_picture();
        // The counters of the fallback, apart from every fidelity and validation figure: native code only reaches 100 % when both are 0.
        fprintf(stderr, "[host] link cable coverage: native entries missed %llu (%llu distinct), interpreted instructions %llu, reviewed roots %u console(s)\n",
                g_runtime_session_fallback_entries, g_runtime_session_fallback_distinct, static_cast<unsigned long long>(interpreted_any()), static_cast<unsigned>(RR_GBA_LINK_SEATS));
    }
    if (g_rows) {
        fclose(g_rows);
        g_rows = nullptr;
    }
    g_link.reset();
    g_link_view.reset();
    g_link_boot = nullptr;
    return g_failed ? 1 : status;
}

}  // namespace

extern "C" {

static void run_selftest(void);
static void run_state_switch(void);

bool rrgba_frame(uint16_t pressed) { return rrgba_frame_pads(pressed, 0); }

bool rrgba_frame_pads(uint16_t pressed, uint16_t other) {
    if ((!g_api && !g_link) || g_restart) return false;
    if (g_session && !g_link && g_boot_state.empty()) {                  // the state before the first frame: what a restart in a session goes back to
        std::string error;
        if (!g_api->save_state(g_boot_state, error)) g_boot_state.clear();
    }
    if (g_frame_index == 0) {                                 // test switch: write the session's save image (what the host hands to the guests) to a file
        const char* image = getenv("RETRORECOMP_GBA_SAVE_IMAGE");
        const size_t size = image ? rrgba_session_save(nullptr, 0) : 0;
        if (size) {
            std::vector<uint8_t> bytes(size);
            rrgba_session_save(bytes.data(), size);
            if (FILE* out = fopen(image, "wb")) {
                fwrite(bytes.data(), 1, size, out);
                fclose(out);
            }
        }
    }
    if (const char* touch = getenv("RETRORECOMP_GBA_SAVE_TOUCH")) {      // test switch: at this frame, mimic a game's write to its cartridge (the last byte of the chip flipped, the save marked changed)
        if (g_frame_index + 1 == strtoull(touch, nullptr, 10)) {
            std::vector<uint8_t> now;
            std::string error;
            size_t at = 0, length = 0;
            if (g_link) {                                         // the link: the first console's chip gets a byte (programmed the way a game does: the command cycles, then the byte)
                gba::GbaSave& chip = g_link->machine(0).bus.save();
                if (chip.flash_enabled()) {
                    const uint32_t last = static_cast<uint32_t>(chip.flash_size() - 1);
                    chip.flash_write(0x5555, 0xAA);
                    chip.flash_write(0x2AAA, 0x55);
                    chip.flash_write(0x5555, 0xA0);
                    chip.flash_write(last, 0x00);          // programming only clears bits: 0 changes any byte that is not already 0
                } else if (chip.sram_enabled()) {
                    chip.sram_write(static_cast<uint32_t>(chip.sram_size() - 1), 0x5A);
                }
            } else if (g_api->save_state(now, error) && find_section(now, kSaveTag, &at, &length) && length > 16) {
                now[at + 1] = 1;                                  // dirty_
                now[at + length - 14] ^= 0xFF;                    // the last byte of a Flash chip (the 13 bytes after it: SRAM flag, size, length)
                g_api->load_state(now, error);
            }
        }
    }
    if (g_scripted) pressed = scripted_pressed();
    if (!g_link) g_api->set_keyinput(static_cast<uint16_t>(~pressed & 0x3FF));
    ++g_frame_index;
    g_frame_sound = 1469598103934665603ull;
    g_frame_audible = false;
    if (g_link ? !link_step(pressed, other) : !g_api->step_frame()) {
        g_failed = true;
        return false;
    }
    take_picture();
    take_sound();
    if (g_link) g_link->discard_audio_output();               // the other consoles never feed this PC's speaker
    for (const uint64_t frame : g_shot_frames)
        if (frame == g_frame_index) write_shot(frame);
    if (g_rows)
        fprintf(g_rows, "%llu,%016llx,%016llx,%d\n", static_cast<unsigned long long>(g_frame_index), static_cast<unsigned long long>(picture_hash()),
                static_cast<unsigned long long>(g_frame_sound), g_frame_audible ? 1 : 0);
    if (g_digest_every && g_frame_index % g_digest_every == 0) {
        uint64_t parts[5] = {0, 0, 0, 0, 0};
        const uint64_t first = g_link ? link_digest() : state_digest(parts), second = g_link ? link_digest() : state_digest();       // reading the digest must not change the machine: twice in a row is the same
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

// A restart. Alone, the loop ends and the machine is built again (the engine's own start-up). In a session that cannot be: the engine's start-up opens the kit's loop again and
// the session's pipes are closed with the first one. The machine goes back to the state it had before its first frame (kept in memory at that moment) instead, as a power cycle
// does, except for the cartridge save, which a power cycle keeps: the section of the save of the present state replaces the one of the boot state before it is loaded.
void rrgba_reset(void) {
    if (g_link) {                                              // the link: the consoles are built again from power-on, on the chip of the first one (a power cycle keeps the save)
        g_link_unwritten = g_link_unwritten || g_link->machine(0).bus.save().dirty();   // the chip the file does not hold yet survives the power cycle: it is still to write at the end
        g_link_image = link_chip_bytes(g_link->machine(0).bus.save());
        g_audio_running = 1469598103934665603ull;
        if (!link_build()) g_failed = true;
        return;
    }
    if (!g_session || !g_api || g_boot_state.empty()) {
        g_restart = true;
        return;
    }
    std::vector<uint8_t> now, state = g_boot_state;
    std::string error;
    size_t now_at = 0, now_length = 0, boot_at = 0, boot_length = 0;
    if (g_api->save_state(now, error) && find_section(now, kSaveTag, &now_at, &now_length) && find_section(state, kSaveTag, &boot_at, &boot_length)) {
        if (now_length == boot_length) memcpy(&state[boot_at], &now[now_at], now_length);
        else fprintf(stderr, "[host] the cartridge save changed its size: the restart keeps the one of the start\n");
    }
    if (!g_api->load_state(state, error)) {
        fprintf(stderr, "[host] the restart could not load the state of the start: %s\n", error.c_str());
        g_failed = true;
        return;
    }
    g_audio_running = 1469598103934665603ull;
}
uint64_t rrgba_digest(void) { return g_link ? link_digest() : state_digest(); }
void rrgba_side_effects(bool allowed) { g_save_writes = allowed; }

// The cartridge save in a session (session ABI 8): the host's image travels to every seat. The image is the "SAV0" section of the engine's state container: the chip's memory
// (SRAM, Flash or EEPROM, whichever the game has) as the machine reads it from power-on, the same fields on every PC. It is read before the first frame (the engine has loaded the
// save file by then) and a guest puts it back in the same section, in memory only: the file is never touched (side_effects(false)).
size_t rrgba_session_save(void* out, size_t capacity) {
    if (g_link) {                                              // the link: the chip's bytes of the first console (the host's seat)
        const std::vector<uint8_t> chip = link_chip_bytes(g_link->machine(0).bus.save());
        if (chip.empty() || chip.size() > RRHK_SESSION_MAX_SAVE) return 0;
        if (out) {
            if (capacity < chip.size()) return 0;
            memcpy(out, chip.data(), chip.size());
        }
        return chip.size();
    }
    std::vector<uint8_t> blob;
    std::string error;
    size_t at = 0, length = 0;
    if (!g_api || !g_api->save_state(blob, error) || !find_section(blob, kSaveTag, &at, &length) || length == 0) return 0;
    if (length > RRHK_SESSION_MAX_SAVE) {
        fprintf(stderr, "[host] the cartridge save (%zu bytes) is larger than a session carries: every seat keeps its own\n", length);
        return 0;
    }
    if (out) {
        if (capacity < length) return 0;
        memcpy(out, &blob[at], length);
    }
    return length;
}

// The host, when a match ends cleanly: the save as it is now in memory goes to this PC's own save file, atomically (the engine writes a temporary file and renames it), the previous
// file kept beside it as ".bak" (itself written atomically). Nothing was written during the match (side_effects(false) on every seat). Nothing changed in memory: nothing to write.
bool rrgba_session_save_commit(void) {
    if (!(g_api || g_link) || !g_save_path[0]) return false;
    if (g_link ? !(g_link->machine(0).bus.save().dirty() || g_link_unwritten) : !g_api->save_dirty()) return true;
    FILE* file = rr_fopen(g_save_path, L"rb");
    if (file) {
        std::vector<uint8_t> previous;
        uint8_t buffer[65536];
        for (size_t got; (got = fread(buffer, 1, sizeof buffer, file)) > 0;) previous.insert(previous.end(), buffer, buffer + got);
        fclose(file);
        const std::wstring backup = std::wstring(g_save_path) + L".bak";
        if (!write_atomically(backup.c_str(), previous)) {
            fprintf(stderr, "[host] the previous cartridge save could not be kept as a backup: the save is not rewritten\n");
            return false;
        }
    }
    make_parent_folders(g_save_path);
    if (g_link) {                                              // the link: the first console's chip, atomically (the engine's own write is not in this path)
        if (!write_atomically(g_save_path, link_chip_bytes(g_link->machine(0).bus.save()))) {
            fprintf(stderr, "[host] the cartridge save could not be written\n");
            return false;
        }
        g_link->machine(0).bus.save().clear_dirty();
        g_link_unwritten = false;
        return true;
    }
    if (!g_api->flush_save()) {
        fprintf(stderr, "[host] the cartridge save could not be written\n");
        return false;
    }
    return true;
}

bool rrgba_session_save_put(const void* in, size_t size) {
    if (g_link) {                                              // the link: the host's chip goes in every console (the match plays on one save), in memory only
        if (!in || size == 0 || size != link_chip_bytes(g_link->machine(0).bus.save()).size()) {
            fprintf(stderr, "[host] the host's cartridge save (%zu bytes) does not fit this game's chip: this seat keeps its own\n", size);
            return false;
        }
        const std::vector<uint8_t> image(static_cast<const uint8_t*>(in), static_cast<const uint8_t*>(in) + size);
        for (unsigned id = 0; id < g_link_seats; ++id) link_load_chip(g_link->machine(id).bus.save(), image);
        g_link_image = image;                                  // a restart builds the consoles again on it
        return true;
    }
    if (!g_api || !in || size == 0) return false;
    std::vector<uint8_t> now;
    std::string error;
    size_t at = 0, length = 0;
    if (!g_api->save_state(now, error) || !find_section(now, kSaveTag, &at, &length) || length != size) {
        fprintf(stderr, "[host] the host's cartridge save (%zu bytes) does not fit this game's chip: this seat keeps its own\n", size);
        return false;
    }
    memcpy(&now[at], in, size);
    if (!g_api->load_state(now, error)) {
        fprintf(stderr, "[host] the host's cartridge save could not be put in: %s\n", error.c_str());
        g_failed = true;
        return false;
    }
    g_audio_running = 1469598103934665603ull;
    if (!g_boot_state.empty()) {                                  // a restart goes back to the state of the start, with the host's save in it
        size_t boot_at = 0, boot_length = 0;
        if (find_section(g_boot_state, kSaveTag, &boot_at, &boot_length) && boot_length == size) memcpy(&g_boot_state[boot_at], in, size);
    }
    return true;
}
// The session's clock (RRHK_SESSION_CLOCK, the same on every seat) is already the engine's guest epoch: the engine reads it once when it starts, which is before the kit's setup.
void rrgba_session_begin(uint64_t clock) {
    if (g_clock_at_start && clock != g_clock_at_start)
        fprintf(stderr, "[host] the session's clock (%llu) is not the one this machine started with (%llu): a cartridge clock would differ\n",
                static_cast<unsigned long long>(clock), static_cast<unsigned long long>(g_clock_at_start));
}
uint64_t rrgba_interpreted(void) { return interpreted_any(); }
unsigned rrgba_link_seats(void) { return g_link_seats; }
uint64_t rrgba_frames(void) { return g_link ? link_ppu()->frame_count() : g_api ? g_api->frames() : 0; }

bool rrgba_state_path(wchar_t* path, size_t capacity) { return state_location(path, capacity, "states", ".rrstate"); }

bool rrgba_state_file(const wchar_t* path, bool load) {
    if (g_link) {
        fprintf(stderr, "[host] quick states are not available on the link cable\n");
        return false;
    }
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
    load_link_route();
    // The link cable: that many consoles (2 to 4) on one cable. The room's worker says it in the game's environment (RRHK / session_pipe.LINK_ENV: the consoles the match may run; this engine
    // builds its consoles before HELLO, so SETUP comes too late for it); RETRORECOMP_GBA_LINK is the same thing for a test run on its own.
    const char* cable = getenv("RETRORECOMP_NETPLAY_LINK");
    if (!cable) cable = getenv("RETRORECOMP_GBA_LINK");
    if (cable) {
        // Every cartridge may have a cable (two consoles; more only as far as a reviewed row of retrorecomp/gba_link.py ran its route: RR_GBA_LINK_SEATS). A cartridge with no row has no
        // reviewed link roots: the code only the cable runs is interpreted, counted and listed in the log (never a stop of the match). RETRORECOMP_GBA_LINK_FORCE lifts the cap of consoles.
        const int seats = atoi(cable);
        const unsigned reviewed = static_cast<unsigned>(RR_GBA_LINK_SEATS);
        const unsigned ready = getenv("RETRORECOMP_GBA_LINK_FORCE") ? 4u : std::max(2u, reviewed);
        if (seats >= 2 && seats <= 4 && static_cast<unsigned>(seats) <= ready) {
            g_link_seats = static_cast<unsigned>(seats);
            if (!reviewed)
                fprintf(stderr, "[host] link cable: no reviewed link roots for this game: the code only the cable runs is interpreted (counted, listed below)\n");
        } else if (seats >= 2)
            fprintf(stderr, "[host] the link cable is refused: at most %u console(s) on a cable for this game (coverage.link_cable of its report); it plays on one console\n", ready);
    }
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
    } else if ((g_scripted || g_selftest || !g_link_script.empty() || getenv("RETRORECOMP_HOST_TEST_FRAMES")) && !getenv("GBARECOMP_RTC_GUEST_EPOCH"))
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
        if (g_link_seats) {
            // The engine's netplay branch of run_game() (its images checked, its chip chosen, its mods off) with our own `run`: the engine's session, and the host kit's loop on top of it.
            static std::string link_name = RR_GBA_NAME;
            gbarecomp::RunOptions options;
            options.netplay = std::make_shared<gbarecomp::GbaNetplayLaunch>();
            options.netplay->enabled = true;
            options.netplay->run = link_run;
            options.builtin_game_name = link_name.c_str();
            options.builtin_rom_sha1 = RR_GBA_ROM_SHA1;
            status = gbarecomp::run_game(static_cast<int>(arguments.size()), arguments.data(), options);
        } else {
            status = gbarecomp::run_game(static_cast<int>(arguments.size()), arguments.data());
        }
    } while (g_restart && status == 0);
    return status;
}
