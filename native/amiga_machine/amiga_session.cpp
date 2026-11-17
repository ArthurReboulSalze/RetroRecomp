// Retro-Recomp Amiga session (see amiga_session.h). Original Retro-Recomp code, MIT; links vAmiga Core (MPL-2.0), adapted at
// build time by retrorecomp/amiga_vamiga.py.
//
// The machine boots an authored 512 KiB boot ROM (Kickstart-shaped header, then code that turns the overlay off, quiets
// interrupts and DMA, and waits): nothing of a Kickstart. After one frame the host lays out the WHDLoad memory as WHDLoad
// does (BaseMem from 0 in chip RAM, ExpMem then the slave in slow RAM), relocates the slave over itself, sets the CPU state
// WHDLoad 20.1 gives ws_GameLoader (read in the private oracle: SR $2000, marked registers, A0 = resload base, A7 = top of
// BaseMem) and enters it. Each entry of the resload table carries a CPU breakpoint: when the CPU reaches one, the call is
// answered by native/amiga_whdload/rr_resload.c and the CPU returns to the caller, with no emulated cycle for the call.
#include "vaconfig.h"
#include "Emulator.h"
#include "Amiga.h"

extern "C" {
#include "rr_resload.h"
}
#include "amiga_savefile.h"
#include "amiga_session.h"

#include <algorithm>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <map>
#include <set>
#include <string>
#include <vector>

namespace fs = std::filesystem;
using namespace vamiga;

namespace vamiga::moira { extern bool (*rr_moira_native)(Moira &, u32 pc, u16 opcode); extern u32 rr_moira_trap_base, rr_moira_trap_size; }

static constexpr uint32_t SLOW_BASE = 0xC00000;
static constexpr uint32_t SLOW_SIZE = 0x180000;     // 1.5 MiB of slow RAM: ExpMem, then the slave area
// An ExpMem too large for the slow RAM goes to a Zorro II fast RAM board configured at $200000 (up to 8 MiB, as an A500 with a
// RAM expansion has it); the slave area then takes the start of the slow RAM. Installs whose ExpMem fits keep the slow layout.
static constexpr uint32_t FAST_BASE = 0x200000;
static constexpr uint32_t FAST_MAX = 0x800000;
static uint32_t slow_slave_area(uint32_t exp_size) { return (SLOW_BASE + exp_size + 0xFFF) & ~0xFFFu; }
static bool exp_in_fast(uint32_t exp_size) { return exp_size && slow_slave_area(exp_size) + 0x7FFF0 >= SLOW_BASE + SLOW_SIZE; }
static constexpr const char STATE_MAGIC[16] = "RRAMIGA-STATE-7";
static constexpr int FIRST_LINE_PAL = 32, FIRST_LINE_NTSC = 26, FIRST_TEXEL = 308;
// Denise's horizontal counter, in super-hires pixels, at texel 0 of a line (HBLANK_MIN * 8, Denise::updateBorderBuffer): the
// display window's edges (DIWSTRT/DIWSTOP, in that unit) land on picture column (edge - SHRES_AT_TEXEL0 - FIRST_TEXEL) / 2.
static constexpr int SHRES_AT_TEXEL0 = HBLANK_MIN * 8;

struct RrAmigaSession {
    Emulator *emu = nullptr;
    Amiga *amiga = nullptr;
    std::map<std::string, std::vector<uint8_t>> files;   // lower-case name -> bytes
    fs::path save_dir;
    bool saves = false, ntsc = false;
    int model = RR_AMIGA_MODEL_A500;
    RrResloadHost host{};
    RrResload rl{};
    uint32_t resload_table = 0;
    uint64_t frame = 0;
    long calls = 0;
    std::string error, log;
    bool quit = false;         // the install ended itself with resload_Abort(TDREASON_OK): a normal exit, not a failure
    unsigned joy = 0;
    int mouse_left = 0, mouse_right = 0;
    unsigned joy2 = 0;              // the joystick of port 1 (the second player's), held bits
    int port1_mode = 0;             // RR_AMIGA_PORT1_FOLLOW, _MOUSE or _JOYSTICK (the player's choice; not part of a state)
    int cpu_factor = 1;             // rr_amiga_cpu_factor: 1, 2 or 4 (the player's choice; a state load keeps it)
    // The device port 1 holds (1: the joystick). vAmiga keeps its own private: this copy moves with the calls that move it (a mouse
    // motion or button plugs the mouse, a joystick action the joystick, a forced mode or a state load sets it).
    int port1_joystick = 0;
    uint8_t keys[128] = {};
    bool no_keyboard = false;                            // the slave's WHDLF_NoKbd: nothing here touches its keyboard interrupt
    std::vector<int16_t> pcm;
    std::vector<uint32_t> picture;
    int lines = 0;
    // An interlaced screen (LACE) is drawn as a long and a short field in turn. The picture weaves the field of this frame with the one
    // of the frame before into twice the lines (`rows`); one field alone is shown line-doubled. Where the screen moves, the field of
    // the frame before is replaced by this field's own lines (weave()). The held field and the one before it are part of a quick state.
    int rows = 0;
    std::vector<uint32_t> held;      // the field of the last frame, while LACE is set (lines rows)
    int held_lof = -1;               // its long-frame bit, -1: none held
    uint64_t held_frame = 0;         // the frame it ended
    std::vector<uint32_t> prior;     // the field of the frame before that one (the parity of the next frame's field)
    int prior_lof = -1;
    uint64_t prior_frame = 0;
    bool view_seen = false;
    int view[4] = {};          // union of the display windows opened so far: left, top, right, bottom (picture columns, rows)
    bool observing = false, native = false;
    std::set<std::pair<uint32_t, std::string>> observed;
    uint64_t interpreted_count = 0;
    // The Blitter's counters by shape (BLTCON0 and BLTCON1 without the shift fields): blits, and words or line steps, in a specialised routine (native) and in vAmiga's microprogram (interpreted).
    struct BlitCount { void (*run)(void *) = nullptr; uint64_t native_blits = 0, native_words = 0, interpreted_blits = 0, interpreted_words = 0; };
    std::map<uint32_t, BlitCount> blit;
    // The player's own record, and the window it was told last.
    void (*recorder)(uint32_t, const uint8_t *, unsigned) = nullptr;
    uint32_t window = 0, window_last = 0;
    uint8_t window_bytes[16] = {};
    bool window_set = false;
    std::map<std::string, std::string> display;               // lower-case name -> the name as the install spells it
    std::vector<std::pair<std::string, uint32_t>> listing;    // the files as resload_Examine/ExNext/ListFiles see them
    std::vector<uint8_t> kick;                                // the player's Kickstart (host memory only)
    uint32_t kick_base = 0, kick_size = 0;                    // where it sits in ExpMem once loaded (0: not loaded)
    uint64_t kick_interpreted = 0;
    // The Kickstart's instructions run on the interpreter while observing: the address and the words as they stand (a slave patches
    // some). Written beside the observations, in the conversion's private work folder only; the library keeps the addresses alone.
    std::set<std::pair<uint32_t, std::string>> kick_observed;
    // A multiplayer session (RrAmigaGame.session): every seat starts from the install's own files, and what the game saves stays in
    // memory (`overlay`, entries appended, the last one of a name wins), part of the in-process snapshot, never written to disk. The
    // recorder notes nothing while side effects are off (a silent frame, a guest).
    bool session = false, effects = true;
    std::vector<uint8_t> overlay;    // OVERLAY_CAP bytes, sized once at the start; `overlay_used` of them hold entries
    size_t overlay_used = 0;
};

static RrAmigaSession *S;   // the hooks of Moira and of the resload layer reach the one session of the process

// The saves of a session (RrAmigaSession.overlay): each entry is the name's length (2 bytes, little-endian), the name (lower case), 1
// when the file was removed, the size (4 bytes) and the bytes. 2 MiB hold a WHDLoad install's high-score files and a saved disk image
// (880 KiB) twice; a save that still does not fit once the older entries of each name are dropped is told the disk is full, the same
// on every seat.
static constexpr size_t OVERLAY_CAP = 2u << 20;

static uint32_t le32(const uint8_t *p) { return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24; }

// Each entry in order: its name, removed, size, bytes.
template <class F> static void overlay_walk(const uint8_t *p, size_t used, F &&f) {
    size_t at = 0;
    while (at + 7 <= used) {
        const size_t length = (size_t)p[at] | (size_t)p[at + 1] << 8;
        const uint8_t *name = p + at + 2;
        const bool removed = p[at + 2 + length] != 0;
        const uint32_t size = le32(p + at + 3 + length);
        f(std::string((const char *)name, length), removed, p + at + 7 + length, size);
        at += 7 + length + size;
    }
}

// The last entry of `key`: -1 none, 0 removed, 1 there (its bytes in `data`, `size`).
static int overlay_find(const std::string &key, const uint8_t **data, uint32_t *size) {
    int found = -1;
    overlay_walk(S->overlay.data(), S->overlay_used, [&](const std::string &name, bool removed, const uint8_t *bytes, uint32_t n) {
        if (name != key) return;
        found = removed ? 0 : 1; *data = bytes; *size = n;
    });
    return found;
}

// Appends an entry; when it does not fit, the older entries of each name go first. false: the disk is full.
static bool overlay_put(const std::string &key, const uint8_t *data, uint32_t size, bool removed) {
    const size_t need = 7 + key.size() + size;
    if (key.size() > 0xFFFF) return false;
    if (S->overlay_used + need > S->overlay.size()) {
        std::map<std::string, std::vector<uint8_t>> last;
        overlay_walk(S->overlay.data(), S->overlay_used, [&](const std::string &name, bool gone, const uint8_t *bytes, uint32_t n) {
            std::vector<uint8_t> entry;
            entry.push_back((uint8_t)name.size()); entry.push_back((uint8_t)(name.size() >> 8));
            entry.insert(entry.end(), name.begin(), name.end());
            entry.push_back(gone ? 1 : 0);
            for (int b = 0; b < 4; b++) entry.push_back((uint8_t)(n >> (8 * b)));
            entry.insert(entry.end(), bytes, bytes + n);
            last[name] = std::move(entry);
        });
        last.erase(key);
        size_t at = 0;
        for (auto &e : last) { memcpy(S->overlay.data() + at, e.second.data(), e.second.size()); at += e.second.size(); }
        S->overlay_used = at;
        if (at + need > S->overlay.size()) return false;
    }
    uint8_t *p = S->overlay.data() + S->overlay_used;
    p[0] = (uint8_t)key.size(); p[1] = (uint8_t)(key.size() >> 8);
    memcpy(p + 2, key.data(), key.size());
    p[2 + key.size()] = removed ? 1 : 0;
    for (int b = 0; b < 4; b++) p[3 + key.size() + b] = (uint8_t)(size >> (8 * b));
    if (size) memcpy(p + 7 + key.size(), data, size);
    S->overlay_used += need;
    return true;
}

// UTF-8 text to a path (std::filesystem::u8path is deprecated in C++20).
static fs::path upath(const std::string &s) { return fs::path(std::u8string(s.begin(), s.end())); }
static std::string utf8(const fs::path &p) { auto u = p.generic_u8string(); return std::string(u.begin(), u.end()); }

static std::string lower(std::string s) { std::transform(s.begin(), s.end(), s.begin(), [](unsigned char c) { return (char)std::tolower(c); }); return s; }

// The guest names its files in ISO-8859-1 (the Amiga's character set); the install's names are kept here in UTF-8, as
// the converter wrote them. A name crossing the resload layer is converted each way (Déjà Vu asks for "déjà vu").
static std::string from_latin1(const char *guest) {
    std::string out;
    for (const unsigned char *c = (const unsigned char *)guest; *c; c++) {
        if (*c < 0x80) out += (char)*c;
        else { out += (char)(0xC0 | (*c >> 6)); out += (char)(0x80 | (*c & 0x3F)); }
    }
    return out;
}
static std::string to_latin1(const std::string &text) {
    std::string out;
    for (size_t i = 0; i < text.size(); i++) {
        unsigned char c = (unsigned char)text[i];
        if (c < 0x80) { out += (char)c; continue; }
        if ((c & 0xE0) == 0xC0 && i + 1 < text.size()) {
            unsigned code = (unsigned)(c & 0x1F) << 6 | ((unsigned char)text[i + 1] & 0x3F);
            out += code < 0x100 ? (char)code : '?';
            i++;
            continue;
        }
        out += '?';                                          // beyond ISO-8859-1: no Amiga name can ask for it
        while (i + 1 < text.size() && ((unsigned char)text[i + 1] & 0xC0) == 0x80) i++;
    }
    return out;
}
static std::string key_of(const char *guest) { return lower(from_latin1(guest)); }
static uint8_t peek(void *, uint32_t a) { return S->amiga->mem.spypeek8<Accessor::CPU>(a); }
static void poke(void *, uint32_t a, uint8_t v) { S->amiga->mem.patch(a, (u8)v); }
static uint16_t peek16(uint32_t a) { return (uint16_t)(peek(nullptr, a) << 8 | peek(nullptr, a + 1)); }
static uint32_t peek32(uint32_t a) { return (uint32_t)peek16(a) << 16 | peek16(a + 2); }
static void poke32(uint32_t a, uint32_t v) { for (int k = 0; k < 4; k++) poke(nullptr, a + k, (uint8_t)(v >> (24 - 8 * k))); }
static bool in_ram(uint32_t pc) { return pc < 0xA00000 || (pc >= 0xC00000 && pc < 0xDC0000); }
// The host bytes behind a span of the slow RAM or of the fast RAM board, or nullptr.
static uint8_t *host_ram(uint32_t a, uint32_t size) {
    Memory &mem = S->amiga->mem;
    if (mem.slow && a >= SLOW_BASE && a + size <= SLOW_BASE + (uint32_t)mem.slowRamSize()) return mem.slow + (a - SLOW_BASE);
    if (mem.fast && a >= FAST_BASE && a + size <= FAST_BASE + (uint32_t)mem.fastRamSize()) return mem.fast + (a - FAST_BASE);
    return nullptr;
}

// One display window (vAmiga's ViewportMsg: super-hires columns, lines) into the union, in picture coordinates. A window that
// does not close on its line or frame (stop at or before start) is open to the picture's edge; an unset start or a sliver is
// not a window.
static void note_viewport(RrAmigaSession *s, const ViewportMsg &v) {
    const int origin = SHRES_AT_TEXEL0 + FIRST_TEXEL, first = s->ntsc ? FIRST_LINE_NTSC : FIRST_LINE_PAL;
    // DIWSTRT not written yet (the reset state the boot leaves, 0): no window. Denise's smallest start is $002 ($008 scaled).
    if (v.hstrt < 8 || v.vstrt <= 0) return;
    int x0 = (v.hstrt - origin) / 2, x1 = v.hstop > v.hstrt ? (v.hstop - origin + 1) / 2 : RR_AMIGA_PICTURE_WIDTH;
    int y0 = v.vstrt - first, y1 = v.vstop > v.vstrt ? v.vstop - first : s->lines;
    x0 = std::clamp(x0, 0, RR_AMIGA_PICTURE_WIDTH); x1 = std::clamp(x1, 0, RR_AMIGA_PICTURE_WIDTH);
    y0 = std::clamp(y0, 0, s->lines); y1 = std::clamp(y1, 0, s->lines);
    if (x1 - x0 < 64 || y1 - y0 < 32) return;
    if (!s->view_seen) { s->view[0] = x0; s->view[1] = y0; s->view[2] = x1; s->view[3] = y1; s->view_seen = true; return; }
    s->view[0] = std::min(s->view[0], x0); s->view[1] = std::min(s->view[1], y0);
    s->view[2] = std::max(s->view[2], x1); s->view[3] = std::max(s->view[3], y1);
}

static int file_cb(void *, const char *name, const uint8_t **data, uint32_t *size) {
    const std::string key = key_of(name);
    if (S->session) {
        const int saved = overlay_find(key, data, size);
        if (saved >= 0) return saved;
    }
    auto it = S->files.find(key);
    if (it == S->files.end()) return 0;
    *data = it->second.data();
    *size = (uint32_t)it->second.size();
    return 1;
}

// The install's files for resload_Examine/ExNext/ListFiles: taken again at index 0 (saves may have added some), spelled as
// the install spells them.
static int list_cb(void *, uint32_t index, const char **name, uint32_t *size) {
    if (index == 0) {
        S->listing.clear();
        // A session's saves: the last entry of each name, over the install's files (in name order, as the map gives them).
        std::map<std::string, std::pair<bool, uint32_t>> saved;
        if (S->session)
            overlay_walk(S->overlay.data(), S->overlay_used, [&](const std::string &key, bool removed, const uint8_t *, uint32_t n) {
                saved[key] = {removed, n};
            });
        std::map<std::string, uint32_t> all;
        for (auto &f : S->files) all[f.first] = (uint32_t)f.second.size();
        for (auto &f : saved) {
            if (f.second.first) all.erase(f.first);
            else all[f.first] = f.second.second;
        }
        for (auto &f : all) {
            auto shown = S->display.find(f.first);
            S->listing.push_back({to_latin1(shown != S->display.end() ? shown->second : f.first), f.second});
        }
    }
    if (index >= S->listing.size()) return 0;
    *name = S->listing[index].first.c_str();
    *size = S->listing[index].second;
    return 1;
}

#ifdef RR_AMIGA_NATIVE
// The native code of this game (retrorecomp/amiga_codegen.py): the instruction known at this pc for the opcode the CPU has latched. It goes on
// by itself to the instructions it knows come next; a step can never sit on a trap of the resload table, which stops the CPU before it runs.
typedef void (*RrAmigaCode)(void *);
extern "C" RrAmigaCode rr_amiga_lookup(uint32_t pc, uint16_t opcode);
extern "C" uint64_t rr_amiga_native_total, rr_amiga_translated_total, rr_amiga_swept_total, rr_amiga_learned_total, rr_amiga_walked_total, rr_amiga_kick_total;
extern "C" const uint32_t *rr_amiga_run_flags;
extern "C" uint32_t rr_amiga_kick_base, rr_amiga_kick_size;
// The specialised routines of this game's Blitter shapes (retrorecomp/amiga_codegen.py).
typedef struct { uint16_t con0, con1; RrAmigaCode run; } RrAmigaBlitShape;
extern "C" const RrAmigaBlitShape rr_amiga_blit_shapes[];
extern "C" const unsigned rr_amiga_blit_shape_count;
#endif
// A blit begins: count it under its shape, and give the slot event this shape's routine if the game has one. A line blit never has one.
static void (*blit_begin(u16 con0, u16 con1, u32 size))(void *) {
    auto &count = S->blit[(uint32_t)(con0 & 0x0fff) << 16 | (con1 & 0x001f)];
    if (count.run && S->native) { count.native_blits++; count.native_words += size; return count.run; }
    count.interpreted_blits++;
    count.interpreted_words += size;
    return nullptr;
}
// Where the native code counts the Kickstart's copy in ExpMem.
static void native_kick_window() {
#ifdef RR_AMIGA_NATIVE
    rr_amiga_kick_base = S->kick_base;
    rr_amiga_kick_size = S->kick_size;
#endif
}

// The player's Kickstart into ExpMem, when the slave's request matches it. The image keeps the addresses it was built for (no
// relocation table): vAmiga's WOM (the A1000's writable ROM, left unlocked) is pointed at the copy, so the window
// $FC0000-$FFFFFF reads and writes the same bytes as ExpMem, and what the slave patches or writes into the image through either
// address is what runs. A 256 KiB image (Kickstart 1.x) takes $FC0000-$FFFFFF and stays writable there; a 512 KiB one (3.x, the A1200's)
// takes the whole $F80000 window, read-only there as an A1200's ROM is (the slave patches it through ExpMem).
// The window over the copy in ExpMem (on), or vAmiga's own ROM mapping (off, around a snapshot).
static void kick_window(bool on) {
    if (!S->kick_size) return;
    Memory &mem = S->amiga->mem;
    uint8_t *copy = on ? host_ram(S->kick_base, S->kick_size) : nullptr;
    mem.wom = copy;
    mem.womMask = copy ? S->kick_size - 1 : 0;
    mem.womIsLocked = copy && S->kick_size == 0x80000;     // locked: banks $F8-$FF all show the copy (unlocked, $F8-$FB show the boot ROM)
    mem.updateMemSrcTables();
}

static int kick_cb(void *, uint32_t size, uint16_t crc16, const char *, uint32_t destination) {
    if (S->kick.size() != size || !(size == 0x40000 || (size == 0x80000 && S->model == RR_AMIGA_MODEL_A1200))) return 0;
    if (!host_ram(destination, size) || (destination & (size - 1)) != 0) return 0;
    for (uint32_t i = 0; i < size; i++) poke(nullptr, destination + i, S->kick[i]);
    if (rr_resload_crc16(&S->rl, destination, size) != crc16) {
        for (uint32_t i = 0; i < size; i++) poke(nullptr, destination + i, 0);
        return 0;
    }
    S->kick_base = destination;
    S->kick_size = size;
    native_kick_window();
    kick_window(true);
    return 1;
}

static uint32_t kick_low() { return 0x1000000u - S->kick_size; }
static bool in_kickstart(uint32_t pc) {
    // The window the writable-ROM alias covers ($FC0000-$FFFFFF for a 256 KiB image, $F80000- for 512 KiB), or the copy in ExpMem; the
    // authored boot ROM below the window is not the Kickstart.
    return S->kick_size && (pc >= kick_low() || (pc >= S->kick_base && pc < S->kick_base + S->kick_size));
}

// A save goes to the game's own folder (and replaces the install's file there on the next start). Below that folder only (a name
// that would leave it is refused), through a temporary file that replaces the old one once every byte reached the disk
// (amiga_savefile.h); the game's view of the file changes only when the disk took the save, so a refused write is reported to the
// slave (disk full) and leaves both the file and what the game reads back as they were.
static int save_cb(void *, const char *name, uint32_t offset, const uint8_t *data, uint32_t size, int whole) {
    const std::string key = key_of(name);
    if ((S->saves || S->session) && !rr_amiga_savefile::inside_folder(key)) return RR_DOS_WRITE_PROTECTED;
    std::vector<uint8_t> next;
    if (whole) next.assign(data, data + size);
    else {
        const uint8_t *was = nullptr;
        uint32_t was_size = 0;
        if (file_cb(nullptr, name, &was, &was_size)) next.assign(was, was + was_size);
        if (next.size() < (size_t)offset + size) next.resize((size_t)offset + size, 0);
        std::copy(data, data + size, next.begin() + offset);
    }
    if (S->session) return overlay_put(key, next.data(), (uint32_t)next.size(), false) ? 0 : RR_DOS_DISK_FULL;
    if (S->saves && !rr_amiga_savefile::replace_file(S->save_dir / upath(key), next)) return RR_DOS_DISK_FULL;
    S->files[key] = std::move(next);
    return 0;
}

static int remove_cb(void *, const char *name) {
    const std::string key = key_of(name);
    if (S->session) { overlay_put(key, nullptr, 0, true); return 0; }
    S->files.erase(key);
    if (S->saves && rr_amiga_savefile::inside_folder(key)) { std::error_code ec; fs::remove(S->save_dir / upath(key), ec); }
    return 0;
}

// The player's own record (kind 22 of native/runtime_feedback.c): 16 bytes at an interpreted instruction, which the conversion walks into instructions, so that the bounded record holds
// more of them. An instruction that follows the one before in the window it was told just now needs no record of its own, as long as the window still holds its opcode.
static void record_window(uint32_t pc) {
    if (S->window_set && pc > S->window_last && pc - S->window_last <= 10 && pc - S->window + 1 < 16 &&
        peek(nullptr, pc) == S->window_bytes[pc - S->window] && peek(nullptr, pc + 1) == S->window_bytes[pc - S->window + 1]) {
        S->window_last = pc;
        return;
    }
    for (uint32_t i = 0; i < 16; i++) S->window_bytes[i] = peek(nullptr, pc + i);
    S->recorder(pc, S->window_bytes, 16);
    S->window = S->window_last = pc;
    S->window_set = true;
}

// Observation and native steps: the hook Moira calls before each instruction (true: a native step ran it).
static bool instruction_hook(vamiga::moira::Moira &m, u32 pc, u16 op) {
#ifdef RR_AMIGA_NATIVE
    if (S->native) {
        if (RrAmigaCode run = rr_amiga_lookup(pc, op)) { run(&m); return true; }
    }
#else
    (void)m; (void)op;
#endif
    S->interpreted_count++;
    // The Kickstart's own code (the window, or its copy in ExpMem) is counted apart. Its bytes are the player's: what is observed
    // here stays in the conversion's private work folder, where the image itself is, and only the addresses are remembered.
    if (in_kickstart(pc)) {
        S->kick_interpreted++;
        if (S->observing && pc >= kick_low()) {
            char hex[33];
            int length = (int)std::min<uint32_t>(S->model == RR_AMIGA_MODEL_A1200 ? 16 : 12, 0x1000000u - pc) & ~1;
            for (int i = 0; i < length; i++) snprintf(hex + 2 * i, 3, "%02x", peek(nullptr, pc + (uint32_t)i));
            S->kick_observed.insert({pc, hex});
        }
        return false;
    }
    if (S->recorder && S->effects && in_ram(pc)) record_window(pc);
    if (S->observing && in_ram(pc)) {
        // 12 bytes hold any 68000 instruction (10 at most). On the A1200, 16 (the bound of every machine's observations) hold every
        // 68EC020 instruction but a MOVE between two full-extension modes (up to 22 bytes), which stays interpreted and counted.
        char hex[33];
        int window = S->model == RR_AMIGA_MODEL_A1200 ? 16 : 12;
        for (int i = 0; i < window; i++) snprintf(hex + 2 * i, 3, "%02x", peek(nullptr, pc + (uint32_t)i));
        S->observed.insert({pc, hex});
    }
    return false;
}
static void update_hook() { vamiga::moira::rr_moira_native = (S->native || S->observing) ? instruction_hook : nullptr; }

static std::vector<uint8_t> boot_rom() {
    std::vector<uint8_t> rom(512 * 1024, 0);
    const uint16_t head[] = {0x1114, 0x4EF9, 0x00F8, 0x00D2};
    const uint16_t code[] = {
        0x46FC, 0x2700,                          // move.w #$2700,sr
        0x13FC, 0x0003, 0x00BF, 0xE201,          // move.b #3,$bfe201   (CIA-A DDRA: OVL, LED out)
        0x13FC, 0x0002, 0x00BF, 0xE001,          // move.b #2,$bfe001   (OVL off: chip RAM at 0)
        0x33FC, 0x7FFF, 0x00DF, 0xF09A,          // move.w #$7fff,$dff09a (INTENA)
        0x33FC, 0x7FFF, 0x00DF, 0xF096,          // move.w #$7fff,$dff096 (DMACON)
        0x33FC, 0x7FFF, 0x00DF, 0xF09C,          // move.w #$7fff,$dff09c (INTREQ)
        // CIA-B as the system leaves it when a slave starts (read on the real WHDLoad: DDRA $C0, DDRB $FF, no drive selected): the
        // disk lines are outputs, so a read of PRB gives back what the game wrote (a slave reads the side-select bit of $bfd100 to
        // know which side of a disk the game asked for). The values are written before the directions so nothing is selected.
        0x13FC, 0x00F8, 0x00BF, 0xD000,          // move.b #$f8,$bfd000 (CIA-B PRA)
        0x13FC, 0x00FF, 0x00BF, 0xD100,          // move.b #$ff,$bfd100 (CIA-B PRB: no drive selected, motor off)
        0x13FC, 0x00C0, 0x00BF, 0xD200,          // move.b #$c0,$bfd200 (CIA-B DDRA)
        0x13FC, 0x00FF, 0x00BF, 0xD300,          // move.b #$ff,$bfd300 (CIA-B DDRB)
        0x60FE};                                 // bra.s *
    auto put = [&](size_t at, const uint16_t *w, size_t n) {
        for (size_t i = 0; i < n; i++) { rom[at + 2 * i] = (uint8_t)(w[i] >> 8); rom[at + 2 * i + 1] = (uint8_t)w[i]; }
    };
    put(0, head, 4);
    put(0xD2, code, sizeof code / 2);
    return rom;
}

static void jump(CPU &cpu, uint32_t pc) { cpu.setPC(pc); cpu.setIRD(peek16(pc)); cpu.setIRC(peek16(pc + 2)); }

// A jump into the resload table stops the machine's run loop (amiga_vamiga.py: one comparison after each instruction).
static void set_traps() {
    vamiga::moira::rr_moira_trap_base = S->resload_table;
    vamiga::moira::rr_moira_trap_size = 4 * RR_RESLOAD_ENTRIES;
}

static FILE *open_file(const char *path, const char *mode) {
#ifdef _WIN32
    std::wstring wide_mode(mode, mode + strlen(mode));
    return _wfopen(upath(path).c_str(), wide_mode.c_str());
#else
    return fopen(path, mode);
#endif
}

static bool fail(char *error, size_t size, const std::string &why) { if (error && size) snprintf(error, size, "%s", why.c_str()); return false; }

static bool enter_slave(const RrAmigaGame *game, char *error, size_t error_size) {
    const uint8_t *slave = game->slave;
    size_t n = game->slave_size;
    auto be32 = [&](size_t o) -> uint32_t { return o + 4 <= n ? (uint32_t)slave[o] << 24 | (uint32_t)slave[o + 1] << 16 | (uint32_t)slave[o + 2] << 8 | slave[o + 3] : 0; };
    // The ws_ header of the first code hunk (the slave was checked by the converter: hunk file, WHDLOADS id).
    size_t p = 4;
    while (be32(p) && p < n) p += 4 + 4 * (size_t)be32(p);
    p += 4;
    uint32_t first = be32(p + 4), last = be32(p + 8);
    p += 12 + 4 * (size_t)(last - first + 1) + 8;
    if (p + 36 > n) return fail(error, error_size, "The slave's header is truncated.");
    uint16_t version = (uint16_t)(slave[p + 12] << 8 | slave[p + 13]);
    uint16_t flags = (uint16_t)(slave[p + 14] << 8 | slave[p + 15]);
    S->no_keyboard = (flags & 0x40) != 0;
    uint32_t base_mem = be32(p + 16);
    int32_t exp_mem = version >= 8 ? (int32_t)be32(p + 32) : 0;
    uint32_t exp_size = exp_mem < 0 ? (uint32_t)-exp_mem : (uint32_t)exp_mem;
    bool fast = exp_in_fast(exp_size);
    uint32_t exp_base = !exp_size ? 0 : fast ? FAST_BASE : SLOW_BASE;
    uint32_t slave_area = fast ? SLOW_BASE : slow_slave_area(exp_size);
    S->resload_table = slave_area + 0x40000;
    uint32_t stack_top = slave_area + 0x7FFF0;
    uint32_t chip = (uint32_t)S->amiga->mem.chipRamSize();
    if (stack_top >= SLOW_BASE + SLOW_SIZE || base_mem > chip || n > 0x3F000)
        return fail(error, error_size, "The install's memory does not fit the Amiga 500 layout (BaseMem, ExpMem or slave too large).");
    if (fast) {
        // The board waits in its autoconfig state since the power-on; it is given $200000 as the Kickstart's expansion code would.
        if (exp_size > FAST_MAX || (uint32_t)S->amiga->mem.fastRamSize() < exp_size)
            return fail(error, error_size, "The install's ExpMem is larger than the 8 MiB of fast RAM an Amiga 500 expansion gives.");
        S->amiga->zorro.pokeACF(0xE80048, (u8)(FAST_BASE >> 16));
        if (S->amiga->ramExpansion.getBaseAddr() != FAST_BASE) return fail(error, error_size, "The fast RAM board could not be configured.");
    }

    // BaseMem and ExpMem filled as WHDLoad does ($CCCCCCCC, or 0 with WHDLF_ClearMem), $0 = 0, $4 = $F0000001.
    uint32_t fill = (flags & 0x1000) ? 0 : 0xCCCCCCCCu;
    for (uint32_t a = 0; a < base_mem; a += 4) poke32(a, fill);
    for (uint32_t a = 0; a < exp_size; a += 4) poke32(exp_base + a, fill);
    poke32(0, 0);
    poke32(4, 0xF0000001u);
    for (size_t i = 0; i < n; i++) poke(nullptr, slave_area + (uint32_t)i, slave[i]);
    for (uint32_t k = 0; k < RR_RESLOAD_ENTRIES; k++) poke32(S->resload_table + 4 * k, 0x4E754E71);

    const bool writable = game->save_dir || S->session;     // a session's saves stay in memory (RrAmigaSession.overlay)
    S->host = RrResloadHost{nullptr, peek, poke, file_cb, writable ? save_cb : nullptr, writable ? remove_cb : nullptr, nullptr};
    S->host.list = list_cb;
    S->host.kickstart = kick_cb;
    if (S->model == RR_AMIGA_MODEL_A1200) {
        // The 68EC020's instruction cache: what resload_FlushCache (and every load or patch, as WHDLoad clears the caches after
        // them) empties, and what resload_SetCACR switches. The A500's 68000 has none, so its host keeps neither.
        S->host.flush = [](void *) { CPU &cpu = S->amiga->cpu; cpu.setCACR(cpu.getCACR() | 0x8u); };
        S->host.cacr = [](void *, uint32_t value, uint32_t mask) -> uint32_t {
            CPU &cpu = S->amiga->cpu;
            // exec's CACR bits for the instruction cache are the 68020's own (EnableI 0, FreezeI 1, ClearI 3); the 68EC020 has no data cache.
            uint32_t old = cpu.getCACR() & 0x3u;
            uint32_t now = ((old & ~mask) | (value & mask)) & 0xBu;
            cpu.setCACR(now);
            return old;
        };
    }
    rr_resload_init(&S->rl, &S->host, slave_area, version, flags);
    if (S->model == RR_AMIGA_MODEL_A1200) {
        S->rl.attn_flags = 0x0003u;    // AFF_68010 | AFF_68020, as exec reports a 68EC020 without an FPU
        S->rl.chip_rev = 0x000Fu;      // GFXF_HR_AGNUS | GFXF_HR_DENISE | GFXF_AA_ALICE | GFXF_AA_LISA
    }
    for (int k = 0; k < 5; k++) S->rl.custom[k] = game->custom[k];
    S->rl.exp_mem_size = exp_size;
    S->rl.scratch = S->resload_table + 0x1000;
    S->rl.time_days = 8035; S->rl.time_mins = 12 * 60; S->rl.time_ticks = 0;
    if (S->ntsc) { S->rl.eclock = 715909u; S->rl.monitor = 0x00011000u; }
    uint32_t regs[16] = {0};
    regs[8] = slave_area;                          // resload_Relocate of the slave over itself
    regs[15] = stack_top;
    RrResload boot = S->rl; boot.slave_version = 20;
    if (rr_resload_call(&boot, 0x50, regs) != RR_RESLOAD_RETURN) return fail(error, error_size, std::string("Slave relocation: ") + boot.message);
    uint32_t loader = slave_area + peek16(slave_area + 24);   // ws_GameLoader
    if (exp_base) poke32(slave_area + 32, exp_base);          // ws_ExpMem now holds the address, as WHDLoad does
    // A v16+ slave that names a Kickstart in its header gets it at the start of ExpMem before ws_GameLoader, as WHDLoad does
    // (resload_LoadKick serves the older slaves at run time). Kickstart 1.x only for now.
    S->rl.exp_mem = exp_base;
    if (version >= 16 && peek32(slave_area + 44) == 0x80000 && S->model != RR_AMIGA_MODEL_A1200)
        return fail(error, error_size, "This install needs a 512 KiB Kickstart (3.x); only 256 KiB Kickstarts (1.x) are supported yet.");
    if (rr_resload_load_slave_kickstart(&S->rl) != RR_RESLOAD_RETURN)
        return fail(error, error_size, std::string("Kickstart: ") + S->rl.message);

    CPU &cpu = S->amiga->cpu;
    cpu.setSR(0x2000);
    for (int i = 0; i < 8; i++) cpu.setD(i, 0xD0D0D0D0u + 0x01010101u * (uint32_t)i);
    cpu.setA(0, S->resload_table);
    for (int i = 1; i < 7; i++) cpu.setA(i, 0xA0A0A0A0u + 0x01010101u * (uint32_t)i);
    cpu.setA(7, base_mem);
    cpu.setUSP(stack_top - 0x4000);
    jump(cpu, loader);
    set_traps();
    char line[160];
    snprintf(line, sizeof line, "slave v%u flags %04x base %06x exp %06x@%06x slave %06x loader %06x resload %06x\n", version, flags,
             base_mem, exp_size, exp_base, slave_area, loader, S->resload_table);
    S->log += line;
    return true;
}

extern "C" RrAmigaSession *rr_amiga_open(const RrAmigaGame *game, char *error, size_t error_size) {
    if (S) { fail(error, error_size, "One Amiga session per process."); return nullptr; }
    if (game->model != RR_AMIGA_MODEL_A500 && game->model != RR_AMIGA_MODEL_A1200) { fail(error, error_size, "Unknown Amiga model."); return nullptr; }
    S = new RrAmigaSession;
    S->ntsc = game->ntsc != 0;
    S->model = game->model;
    for (unsigned i = 0; i < game->file_count; i++) {
        S->files[lower(game->files[i].name)] = std::vector<uint8_t>(game->files[i].data, game->files[i].data + game->files[i].size);
        S->display[lower(game->files[i].name)] = game->files[i].name;
    }
    if (game->kickstart && game->kickstart_size) S->kick.assign(game->kickstart, game->kickstart + game->kickstart_size);
    S->session = game->session != 0;
    if (S->session) {
        // A session: this player's own saves go into the session's memory (the overlay, in name order), never back to the folder. The
        // host plays on them, and a guest's are replaced by the host's before the match (rr_amiga_session_save_put); one that does not
        // fit is left out, and the boot digest tells two different saves apart.
        S->overlay.assign(OVERLAY_CAP, 0);
        std::map<std::string, std::vector<uint8_t>> own;
        std::error_code ec;
        const fs::path folder = game->save_dir && *game->save_dir ? upath(game->save_dir) : fs::path();
        if (!folder.empty() && fs::is_directory(folder, ec))
            for (auto &e : fs::recursive_directory_iterator(folder, ec)) {
                if (!e.is_regular_file() || e.path().extension() == ".tmp") continue;
                std::ifstream in(e.path(), std::ios::binary);
                own[lower(utf8(fs::relative(e.path(), folder)))] = std::vector<uint8_t>((std::istreambuf_iterator<char>(in)), {});
            }
        for (auto &f : own)
            if (rr_amiga_savefile::inside_folder(f.first)) overlay_put(f.first, f.second.data(), (uint32_t)f.second.size(), false);
    } else if (game->save_dir && *game->save_dir) {
        S->saves = true;
        S->save_dir = upath(game->save_dir);
        std::error_code ec;
        if (fs::is_directory(S->save_dir, ec))
            for (auto &e : fs::recursive_directory_iterator(S->save_dir, ec)) {
                if (!e.is_regular_file() || e.path().extension() == ".tmp") continue;
                std::ifstream in(e.path(), std::ios::binary);
                std::vector<uint8_t> bytes((std::istreambuf_iterator<char>(in)), {});
                S->files[lower(utf8(fs::relative(e.path(), S->save_dir)))] = std::move(bytes);
            }
    }
    try {
        // The chip RAM the install's BaseMem needs (512 KiB, or 1 MiB, or 2 MiB above it), read before the machine is configured.
        uint32_t chip_kb = 512, fast_kb = 0;
        {
            const uint8_t *b = game->slave; size_t n = game->slave_size;
            auto be32 = [&](size_t o) -> uint32_t { return o + 4 <= n ? (uint32_t)b[o] << 24 | (uint32_t)b[o + 1] << 16 | (uint32_t)b[o + 2] << 8 | b[o + 3] : 0; };
            size_t q = 4; while (be32(q) && q < n) q += 4 + 4 * (size_t)be32(q); q += 4;
            uint32_t f = be32(q + 4), l = be32(q + 8); q += 12 + 4 * (size_t)(l - f + 1) + 8;
            if (be32(q + 16) > 0x80000) chip_kb = be32(q + 16) > 0x100000 ? 2048 : 1024;
            uint32_t version = be32(q + 12) >> 16;
            int32_t exp_mem = version >= 8 ? (int32_t)be32(q + 32) : 0;
            uint32_t exp_size = exp_mem < 0 ? (uint32_t)-exp_mem : (uint32_t)exp_mem;
            if (exp_in_fast(exp_size)) fast_kb = std::min<uint32_t>((exp_size + 0xFFFF) & ~0xFFFFu, FAST_MAX) / 1024;
        }
        S->emu = new Emulator;
        S->emu->initialize();
        if (S->model == RR_AMIGA_MODEL_A1200) {
            // vAmiga's A1200 scheme sets the CPU, the chips, the 32-bit bus and the chip RAM, not the A1200 bank map (its own
            // window sets that separately). An A1200 always has 2 MiB of chip RAM.
            S->emu->set(ConfigScheme::A1200_2MB);
            S->emu->set(Opt::MEM_BANKMAP, (i64)BankMap::A1200);
            chip_kb = 2048;
        } else {
            S->emu->set(ConfigScheme::A500_ECS_1MB);
        }
        S->emu->set(Opt::AMIGA_VIDEO_FORMAT, S->ntsc ? (i64)TV::NTSC : (i64)TV::PAL);
        // No battery clock (1.7.7): neither a stock Amiga 500 nor a stock Amiga 1200 has one, and vAmiga's (an OKI chip by default) reads the
        // host's time, so a game or a Kickstart that read it would see another value in the reference run and in the native one.
        S->emu->set(Opt::RTC_MODEL, (i64)RTCRevision::NONE);
        S->emu->set(Opt::MEM_SLOW_RAM, SLOW_SIZE / 1024);
        S->emu->set(Opt::MEM_CHIP_RAM, chip_kb);
        // The chipset's collision detection is always there on a real Amiga (CLXCON/CLXDAT: sprite-sprite, sprite-playfield and
        // playfield-playfield); vAmiga ships it off for speed, so a game that reads CLXDAT would never see a collision.
        S->emu->set(Opt::DENISE_CLX_SPR_SPR, 1);
        S->emu->set(Opt::DENISE_CLX_SPR_PLF, 1);
        S->emu->set(Opt::DENISE_CLX_PLF_PLF, 1);
        S->emu->set(Opt::LA_CONNECT, 0);                    // vAmiga's logic analyzer, a debugging recorder: it changes nothing in the machine
        if (fast_kb) S->emu->set(Opt::MEM_FAST_RAM, fast_kb);
        S->emu->set(Opt::MON_PALETTE, (i64)Palette::RGB);   // plain 4-bit to 8-bit colours, no monitor model
        S->emu->set(Opt::MEM_RAM_INIT_PATTERN, (i64)RamInitPattern::ALL_ZEROES);
        S->emu->set(Opt::AUD_ASR, 0);                       // a fixed sample rate: the sound does not follow the host's clock
        // A session's snapshot leaves the ROM out (512 KiB of our boot ROM, the same on every seat and never written; the player's
        // Kickstart lives in ExpMem, in slow RAM, which the snapshot keeps): one snapshot a frame on the rollback tier copies less.
        if (S->session) S->emu->set(Opt::MEM_SAVE_ROMS, false);
        // The texture in the host's own order (0xAARRGGBB): the palette is packed once in that order, and the picture's copy moves
        // texels without swapping red and blue in each pixel. Setting it repacks the palette (Host::setOption, updateRGBA).
        S->emu->set(Opt::HOST_TEX_FORMAT, (i64)TexFormat::ARGB);
        S->amiga = &S->emu->rrMain();
#ifdef RR_AMIGA_NATIVE
        rr_amiga_run_flags = S->amiga->rrRunFlags();
        rr_amiga_native_total = rr_amiga_translated_total = rr_amiga_swept_total = rr_amiga_learned_total = rr_amiga_walked_total = rr_amiga_kick_total = 0;
        for (unsigned n = 0; n < rr_amiga_blit_shape_count; n++)
            S->blit[(uint32_t)rr_amiga_blit_shapes[n].con0 << 16 | rr_amiga_blit_shapes[n].con1].run = rr_amiga_blit_shapes[n].run;
#endif
        rr_blit_begin = blit_begin;
        rr_blit_left_midway = 0;
        S->amiga->audioPort.setSampleRate((double)RR_AMIGA_AUDIO_RATE);
        auto rom = boot_rom();
        S->amiga->mem.loadRom(rom.data(), (isize)rom.size());
        S->amiga->powerOn();
        S->amiga->run();
        S->amiga->keyboard.rrHandshakeOver();   // as on a machine long up: its power-up codes do not reach the game (amiga_vamiga.py)
        S->amiga->controlPort1.setDevice(ControlPortDevice::MOUSE);
        S->amiga->controlPort2.setDevice(ControlPortDevice::JOYSTICK);
        try { S->amiga->computeFrame(); } catch (StateChangeException &) {}   // the boot ROM quiets the machine
        S->amiga->audioPort.stream.clear(SamplePair{0, 0});
        if (!enter_slave(game, error, error_size)) return nullptr;
    } catch (std::exception &e) {
        fail(error, error_size, std::string("The Amiga machine could not start: ") + e.what());
        return nullptr;
    }
    S->lines = S->ntsc ? RR_AMIGA_PICTURE_LINES_NTSC : RR_AMIGA_PICTURE_LINES_PAL;
    S->rows = S->lines;
    S->picture.assign((size_t)RR_AMIGA_PICTURE_WIDTH * RR_AMIGA_PICTURE_MAX_ROWS, 0xFF000000u);
    // A session's machine starts as a snapshot's load leaves it (vAmiga's empty hard drives describe themselves again after a load,
    // which changes the bytes of their state): the same state whether a seat has rolled back yet or not.
    if (S->session) {
        std::vector<uint8_t> once(rr_amiga_snap_bound(S));
        const size_t n = rr_amiga_snap_save(S, once.data(), once.size());
        if (!n || !rr_amiga_snap_load(S, once.data(), n)) { fail(error, error_size, "The Amiga machine could not start a session."); return nullptr; }
    }
    return S;
}

// The changes of a joystick's held bits since `was`, as vAmiga's actions (each action also plugs the joystick into its port).
static bool joystick_actions(Joystick &joy, unsigned was, unsigned bits) {
    bool acted = false;
    auto axis = [&](unsigned minus, unsigned plus, GamePadAction pull_minus, GamePadAction pull_plus, GamePadAction release) {
        int before = (was & plus ? 1 : 0) - (was & minus ? 1 : 0), after = (bits & plus ? 1 : 0) - (bits & minus ? 1 : 0);
        if (before == after) return;
        joy.trigger(after < 0 ? pull_minus : after > 0 ? pull_plus : release);
        acted = true;
    };
    axis(RR_AMIGA_JOY_LEFT, RR_AMIGA_JOY_RIGHT, GamePadAction::PULL_LEFT, GamePadAction::PULL_RIGHT, GamePadAction::RELEASE_X);
    axis(RR_AMIGA_JOY_UP, RR_AMIGA_JOY_DOWN, GamePadAction::PULL_UP, GamePadAction::PULL_DOWN, GamePadAction::RELEASE_Y);
    if ((bits ^ was) & RR_AMIGA_JOY_FIRE) joy.trigger(bits & RR_AMIGA_JOY_FIRE ? GamePadAction::PRESS_FIRE : GamePadAction::RELEASE_FIRE);
    if ((bits ^ was) & RR_AMIGA_JOY_FIRE2) joy.trigger(bits & RR_AMIGA_JOY_FIRE2 ? GamePadAction::PRESS_FIRE2 : GamePadAction::RELEASE_FIRE2);
    return acted || ((bits ^ was) & (RR_AMIGA_JOY_FIRE | RR_AMIGA_JOY_FIRE2));
}

extern "C" void rr_amiga_joystick(RrAmigaSession *s, unsigned bits) {
    joystick_actions(s->amiga->controlPort2.joystick, s->joy, bits);
    s->joy = bits;
}

// Port 1 follows the device used last, as vAmiga's ports do by themselves; a forced mode keeps the other device's input away from it.
extern "C" void rr_amiga_mouse(RrAmigaSession *s, int dx, int dy, int left, int right) {
    if (s->port1_mode != RR_AMIGA_PORT1_JOYSTICK) {
        auto &mouse = s->amiga->controlPort1.mouse;
        if (dx || dy) mouse.setDxDy((double)dx, (double)dy);
        if (!left != !s->mouse_left) mouse.trigger(left ? GamePadAction::PRESS_LEFT : GamePadAction::RELEASE_LEFT);
        if (!right != !s->mouse_right) mouse.trigger(right ? GamePadAction::PRESS_RIGHT : GamePadAction::RELEASE_RIGHT);
        if (dx || dy || !left != !s->mouse_left || !right != !s->mouse_right) s->port1_joystick = 0;
    }
    s->mouse_left = left != 0; s->mouse_right = right != 0;
}

extern "C" void rr_amiga_joystick2(RrAmigaSession *s, unsigned bits) {
    if (s->port1_mode != RR_AMIGA_PORT1_MOUSE && joystick_actions(s->amiga->controlPort1.joystick, s->joy2, bits)) s->port1_joystick = 1;
    s->joy2 = bits;
}

extern "C" void rr_amiga_port1_mode(RrAmigaSession *s, int mode) {
    if (mode < RR_AMIGA_PORT1_FOLLOW || mode > RR_AMIGA_PORT1_JOYSTICK) mode = RR_AMIGA_PORT1_FOLLOW;
    s->port1_mode = mode;
    if (mode == RR_AMIGA_PORT1_MOUSE) { s->amiga->controlPort1.setDevice(ControlPortDevice::MOUSE); s->port1_joystick = 0; }
    if (mode == RR_AMIGA_PORT1_JOYSTICK) { s->amiga->controlPort1.setDevice(ControlPortDevice::JOYSTICK); s->port1_joystick = 1; }
}

// vAmiga's CPU_OVERCLOCKING for the session's factor: its A1200 scheme sets 2 (the 68EC020's 14 MHz, twice the 68000's 7 MHz, which
// is 0, no overclocking); x2 and x4 multiply the model's own clock (A500: 2 and 4, 14 and 28 MHz; A1200: 4 and 8, 28 and 56 MHz).
static void apply_cpu_factor(RrAmigaSession *s) {
    const long base = s->model == RR_AMIGA_MODEL_A1200 ? 2 : 1;
    const long value = s->cpu_factor == 1 ? (s->model == RR_AMIGA_MODEL_A1200 ? 2 : 0) : base * s->cpu_factor;
    if (s->amiga->cpu.getOption(Opt::CPU_OVERCLOCKING) == value) return;
    s->amiga->cpu.resyncOverclockedCpu();   // the CPU's sub-cycle debt is settled at the old factor first
    s->emu->set(Opt::CPU_OVERCLOCKING, value);
}

extern "C" void rr_amiga_cpu_factor(RrAmigaSession *s, int factor) {
    s->cpu_factor = factor == 2 || factor == 4 ? factor : 1;
    apply_cpu_factor(s);
}

extern "C" int rr_amiga_port1_device(RrAmigaSession *s) {
    return s->port1_joystick;
}

extern "C" void rr_amiga_keys(RrAmigaSession *s, const uint8_t held[128]) {
    for (unsigned k = 0; k < 128; k++) {
        if (!held[k] == !s->keys[k]) continue;
        // WHDLoad sets CIAICRF_SP in CIA-A's interrupt mask on each interrupt, unless WHDLF_NoKbd (its autodoc, "cias"), and older
        // ones left AmigaOS's mask: a game that takes the machine over with a level 2 handler may never enable it itself (Pinball
        // Dreams). Here it is set when a key changes, the only moment it can matter: a route without a key sees no difference.
        if (!s->no_keyboard) s->amiga->ciaA.poke(0x0D, 0x88);
        if (held[k]) s->amiga->keyboard.press((KeyCode)k); else s->amiga->keyboard.release((KeyCode)k);
        s->keys[k] = held[k] ? 1 : 0;
    }
}

// The mean of two ARGB pixels, channel by channel (the alpha of two opaque pixels stays opaque).
static inline uint32_t mean_pixel(uint32_t a, uint32_t b) { return (a & b) + (((a ^ b) & 0xFEFEFEFEu) >> 1); }

// An interlaced frame (LACE): `field` (this frame's lines, `lof` its long-frame bit) and the field held from the frame just before, of the other
// parity, become one picture of twice the lines: the long field's line y on row 2y, the short field's on row 2y + 1. A field with no partner
// (the first interlaced frame, two fields of one parity, a frame missed) is shown alone, each line on two rows. The display only: the machine
// draws its fields as it does; the picture the player shows (and the trace hashes) is the woven one, the same in every run.
//
// Motion (1.7.7, Arthur's go of 15 November 2026): the two fields are 1/50 s apart, so where the screen moves the woven picture combs
// (Pinball Illusions' interlaced table, scrolling). The field of this parity two frames back (`prior`) tells where: a pixel of this field
// equal to the same pixel two frames back is still. A row of the held field is kept where this field's lines above and below it are still
// at that column (a still screen is the plain weave, every detail of both fields), and is replaced by their mean where they moved. Each
// field keeps its own rows, so a moving area does not jump by a line. Display only; nothing here is read back by the machine.
static void weave(RrAmigaSession *s, std::vector<uint32_t> &&field, int lof) {
    const size_t w = RR_AMIGA_PICTURE_WIDTH;
    const bool pair = s->held_lof >= 0 && s->held_lof != lof && s->held_frame + 1 == s->frame && s->held.size() == field.size();
    const bool known = pair && s->prior_lof == lof && s->prior_frame + 2 == s->frame && s->prior.size() == field.size();
    const uint32_t *top = pair ? (lof ? field.data() : s->held.data()) : field.data();
    const uint32_t *bottom = pair ? (lof ? s->held.data() : field.data()) : field.data();
    for (int y = 0; y < s->lines; y++) {
        memcpy(s->picture.data() + (size_t)(2 * y) * w, top + (size_t)y * w, w * sizeof(uint32_t));
        memcpy(s->picture.data() + (size_t)(2 * y + 1) * w, bottom + (size_t)y * w, w * sizeof(uint32_t));
    }
    if (known) {
        const uint32_t *now = field.data(), *before = s->prior.data();
        for (int y = 0; y < s->lines; y++) {
            // The held field's line y: row 2y + 1 between this field's lines y and y + 1 (this field long), or row 2y between y - 1 and y.
            const int a = lof ? y : std::max(y - 1, 0), b = lof ? std::min(y + 1, s->lines - 1) : y;
            const uint32_t *na = now + (size_t)a * w, *nb = now + (size_t)b * w, *ba = before + (size_t)a * w, *bb = before + (size_t)b * w;
            uint32_t *out = s->picture.data() + (size_t)(lof ? 2 * y + 1 : 2 * y) * w;
            for (size_t x = 0; x < w; x++)
                if (na[x] != ba[x] || nb[x] != bb[x]) out[x] = mean_pixel(na[x], nb[x]);
        }
    }
    s->rows = 2 * s->lines;
    s->prior = std::move(s->held);
    s->prior_lof = s->held_lof;
    s->prior_frame = s->held_frame;
    s->held = std::move(field);
    s->held_lof = lof;
    s->held_frame = s->frame;
}

extern "C" int rr_amiga_frame(RrAmigaSession *s) {
    if (!s->error.empty()) return -1;
    Amiga &amiga = *s->amiga;
    CPU &cpu = amiga.cpu;
    bool done = false;
    uint32_t regs[16];
    try {
        while (!done) {
            try {
                amiga.computeFrame();
                done = true;
            } catch (StateChangeException &) {
                uint32_t pc = cpu.getPC();
                if (pc < s->resload_table || pc >= s->resload_table + 4 * RR_RESLOAD_ENTRIES) { s->error = "The CPU stopped outside the resload table."; return -1; }
                for (int i = 0; i < 8; i++) { regs[i] = cpu.getD(i); regs[8 + i] = cpu.getA(i); }
                uint32_t offset = pc - s->resload_table;
                int status = rr_resload_call(&s->rl, offset, regs);
                s->calls++;
                char line[160];
                snprintf(line, sizeof line, "%llu %02X %s d0=%08X d1=%08X a0=%06X a1=%06X\n", (unsigned long long)s->frame, offset,
                         status == RR_RESLOAD_RETURN ? "ok" : status == RR_RESLOAD_ABORT ? "abort" : "refused", regs[0], regs[1], regs[8], regs[9]);
                s->log += line;
                if (status != RR_RESLOAD_RETURN) {
                    s->error = s->rl.message[0] ? s->rl.message : "resload call refused";
                    s->quit = status == RR_RESLOAD_ABORT && s->rl.abort_reason[0] == 0xFFFFFFFFu;
                    return -1;
                }
                for (int i = 0; i < 7; i++) { cpu.setD(i, regs[i]); cpu.setA(i, regs[8 + i]); }
                cpu.setD(7, regs[7]);
                uint16_t sr = cpu.getSR() & ~0x000Fu;
                if (regs[0] & 0x80000000u) sr |= 0x8;
                if (!regs[0]) sr |= 0x4;
                cpu.setSR(sr);
                uint32_t sp = cpu.getA(7), ret = peek32(sp);
                cpu.setA(7, sp + 4);
                jump(cpu, ret);
            }
        }
    } catch (std::exception &e) {
        s->error = std::string("The Amiga machine stopped: ") + e.what();
        return -1;
    }
    s->frame++;
    // The display window of the frames just run: vAmiga's viewport tracking posts the widest DIWSTRT/DIWSTOP of a frame when it
    // changes. Only read here, never written: the guest is not touched. The queue is drained so it never fills.
    {
        Message m; std::exception_ptr e;
        while (amiga.msgQueue.get(m, e)) if (m.type == Msg::VIEWPORT) note_viewport(s, m.viewport);
    }
    // The sound of this frame, all of it (the stream is never drained below what was made: no underflow handling).
    auto &stream = amiga.audioPort.stream;
    size_t count = (size_t)stream.count();
    s->pcm.resize(count * 2);
    if (count) {
        std::vector<float> f(count * 2);
        isize got = amiga.audioPort.copyInterleaved(f.data(), (isize)count);
        s->pcm.resize((size_t)got * 2);
        for (size_t i = 0; i < (size_t)got * 2; i++) {
            float v = f[i] * 32767.0f;
            s->pcm[i] = (int16_t)(v > 32767.0f ? 32767 : v < -32768.0f ? -32768 : (int)v);
        }
    }
    // The picture: hires pixels of the overscan window, one row per line.
    const Texture &tex = amiga.denise.pixelEngine.getStableBuffer();
    const uint32_t *px = (const uint32_t *)tex.pixels.ptr;
    int first = s->ntsc ? FIRST_LINE_NTSC : FIRST_LINE_PAL;
    const bool lace = amiga.denise.lace();
    // Without LACE the field is the picture; with it, the field goes to a buffer of its own first (woven below).
    std::vector<uint32_t> field;
    if (lace) field.resize((size_t)RR_AMIGA_PICTURE_WIDTH * s->lines);
    for (int y = 0; y < s->lines; y++) {
        const uint32_t *row = px + (size_t)(first + y) * Tex::width + FIRST_TEXEL;
        uint32_t *out = (lace ? field.data() : s->picture.data()) + (size_t)y * RR_AMIGA_PICTURE_WIDTH;
        // One hires pixel per Texel (its first half); the texture is ARGB already (HOST_TEX_FORMAT above), the alpha is opaque.
        for (int x = 0; x < RR_AMIGA_PICTURE_WIDTH; x++) out[x] = 0xFF000000u | row[2 * x];
    }
    if (!lace) {
        s->rows = s->lines;
        s->held_lof = -1;              // a screen without LACE ends what was held: no stale field joins a later interlaced one
        s->held.clear();
        s->prior_lof = -1;
        s->prior.clear();
        return 0;
    }
    weave(s, std::move(field), tex.lof ? 1 : 0);
    return 0;
}

extern "C" const char *rr_amiga_error(const RrAmigaSession *s) { return s->error.c_str(); }
extern "C" int rr_amiga_quit(const RrAmigaSession *s) { return s->quit; }

extern "C" int rr_amiga_kickstart(const RrAmigaSession *s, uint32_t *size, uint16_t *crc16) {
    if (!s->kick_size) return 0;
    *size = s->kick_size; *crc16 = s->rl.kick_crc;
    return 1;
}
extern "C" uint64_t rr_amiga_kickstart_interpreted_count(const RrAmigaSession *s) { return s->kick_interpreted; }
extern "C" uint64_t rr_amiga_kickstart_native_count(const RrAmigaSession *) {
#ifdef RR_AMIGA_NATIVE
    return rr_amiga_kick_total;
#else
    return 0;
#endif
}

extern "C" int rr_amiga_viewport(const RrAmigaSession *s, int *x, int *y, int *w, int *h) {
    if (!s->view_seen) return 0;
    *x = s->view[0]; *y = s->view[1]; *w = s->view[2] - s->view[0]; *h = s->view[3] - s->view[1];
    return 1;
}

extern "C" const uint32_t *rr_amiga_picture(const RrAmigaSession *s, int *width, int *height) {
    *width = RR_AMIGA_PICTURE_WIDTH; *height = s->rows;
    return s->picture.data();
}

extern "C" size_t rr_amiga_audio(RrAmigaSession *s, int16_t *pcm, size_t capacity_frames) {
    size_t n = std::min(capacity_frames, s->pcm.size() / 2);
    memcpy(pcm, s->pcm.data(), n * 2 * sizeof(int16_t));
    s->pcm.erase(s->pcm.begin(), s->pcm.begin() + (ptrdiff_t)(n * 2));
    return n;
}

static uint64_t fnv(uint64_t h, const void *data, size_t n) {
    const uint8_t *p = (const uint8_t *)data;
    for (size_t i = 0; i < n; i++) { h ^= p[i]; h *= 1099511628211ull; }
    return h;
}

extern "C" void rr_amiga_frame_info(const RrAmigaSession *s, RrAmigaFrameInfo *info) {
    Amiga &amiga = *s->amiga;
    const uint64_t basis = 1469598103934665603ull;
    memset(info, 0, sizeof *info);
    info->frame = s->frame;
    // The picture the player shows (every row of it is drawn each frame), not vAmiga's whole texture: the texture's
    // blanking lines are not redrawn every frame, so after a quick state is loaded they still hold what the new process
    // drew before (North And South showed it on the first frame after a load), which is no part of the game's picture.
    info->video = fnv(basis, s->picture.data(), (size_t)RR_AMIGA_PICTURE_WIDTH * s->rows * sizeof(uint32_t));
    info->pcm = fnv(basis, s->pcm.data(), s->pcm.size() * sizeof(int16_t));
    uint64_t ram = fnv(basis, amiga.mem.chip, (size_t)amiga.mem.chipRamSize());
    if (amiga.mem.slow) ram = fnv(ram, amiga.mem.slow, (size_t)amiga.mem.slowRamSize());
    if (amiga.mem.fast && amiga.mem.fastRamSize()) ram = fnv(ram, amiga.mem.fast, (size_t)amiga.mem.fastRamSize());
    info->ram = ram;
    info->pc = amiga.cpu.getPC(); info->sr = amiga.cpu.getSR();
    for (int i = 0; i < 8; i++) { info->d[i] = amiga.cpu.getD(i); info->a[i] = amiga.cpu.getA(i); }
    info->samples = (uint32_t)(s->pcm.size() / 2);
    for (size_t i = 0; i < s->pcm.size() && !info->audible; i++) info->audible = s->pcm[i] != 0;
    for (size_t i = 0; i < (size_t)RR_AMIGA_PICTURE_WIDTH * s->rows && !info->nonblack; i++) info->nonblack = (s->picture[i] & 0xFFFFFFu) != 0;
}

extern "C" int rr_amiga_set_native(RrAmigaSession *s, int enabled) {
#ifdef RR_AMIGA_NATIVE
    s->native = enabled != 0; update_hook(); return 1;
#else
    (void)s; return !enabled;
#endif
}
extern "C" void rr_amiga_set_observe(RrAmigaSession *s, int enabled) { s->observing = enabled != 0; update_hook(); }
// What the memory holds now, for the conversion's sweep of code (retrorecomp/amiga_codegen.py): each RAM as a big-endian start and size, then its bytes. The conversion's private work
// folder only.
extern "C" int rr_amiga_write_memory(const RrAmigaSession *, const char *path) {
    FILE *o = open_file(path, "wb");
    if (!o) return 0;
    Memory &mem = S->amiga->mem;
    const struct { uint32_t start; size_t size; } regions[] = {
        {0, (size_t)mem.chipRamSize()}, {FAST_BASE, (size_t)mem.fastRamSize()}, {SLOW_BASE, (size_t)mem.slowRamSize()}};
    for (auto &r : regions) {
        if (!r.size) continue;
        std::vector<uint8_t> bytes(r.size);
        for (size_t i = 0; i < r.size; i++) bytes[i] = peek(nullptr, r.start + (uint32_t)i);
        const uint32_t head[2] = {r.start, (uint32_t)r.size};
        for (uint32_t value : head) for (int k = 24; k >= 0; k -= 8) fputc((int)(value >> k & 0xff), o);
        if (fwrite(bytes.data(), 1, bytes.size(), o) != bytes.size()) { fclose(o); return 0; }
    }
    return fclose(o) == 0;
}
extern "C" int rr_amiga_write_observations(const RrAmigaSession *s, const char *path) {
    FILE *o = open_file(path, "wb");
    if (!o) return 0;
    for (auto &e : s->observed) fprintf(o, "%06x %s\n", e.first, e.second.c_str());
    if (fclose(o) != 0) return 0;
    // The Kickstart's beside it, in the same form: this file stays in the private work folder.
    FILE *k = open_file((std::string(path) + ".kick").c_str(), "wb");
    if (!k) return 0;
    for (auto &e : s->kick_observed) fprintf(k, "%06x %s\n", e.first, e.second.c_str());
    return fclose(k) == 0;
}
extern "C" uint64_t rr_amiga_native_count(const RrAmigaSession *) {
#ifdef RR_AMIGA_NATIVE
    return rr_amiga_native_total;
#else
    return 0;
#endif
}
extern "C" uint64_t rr_amiga_translated_count(const RrAmigaSession *) {
#ifdef RR_AMIGA_NATIVE
    return rr_amiga_translated_total;
#else
    return 0;
#endif
}
extern "C" uint64_t rr_amiga_swept_count(const RrAmigaSession *) {
#ifdef RR_AMIGA_NATIVE
    return rr_amiga_swept_total;
#else
    return 0;
#endif
}
extern "C" uint64_t rr_amiga_learned_count(const RrAmigaSession *) {
#ifdef RR_AMIGA_NATIVE
    return rr_amiga_learned_total;
#else
    return 0;
#endif
}
extern "C" uint64_t rr_amiga_walked_count(const RrAmigaSession *) {
#ifdef RR_AMIGA_NATIVE
    return rr_amiga_walked_total;
#else
    return 0;
#endif
}
extern "C" void rr_amiga_set_recorder(RrAmigaSession *s, void (*note)(uint32_t, const uint8_t *, unsigned)) { s->recorder = note; }
extern "C" uint64_t rr_amiga_interpreted_count(const RrAmigaSession *s) { return s->interpreted_count; }
extern "C" void rr_amiga_write_blitter(const RrAmigaSession *s, FILE *o) {
    fprintf(o, "{\"left_midway\":%llu,\"shapes\":[", (unsigned long long)rr_blit_left_midway);
    const char *comma = "";
    for (auto &e : s->blit) {
        fprintf(o, "%s[%u,%u,%d,%llu,%llu,%llu,%llu]", comma, e.first >> 16, e.first & 0xffff, e.second.run != nullptr, (unsigned long long)e.second.native_blits,
                (unsigned long long)e.second.native_words, (unsigned long long)e.second.interpreted_blits, (unsigned long long)e.second.interpreted_words);
        comma = ",";
    }
    fputs("]}", o);
}
extern "C" void rr_amiga_write_display(const RrAmigaSession *s, FILE *o) {
    const auto &agnus = s->amiga->agnus;
    const auto &denise = s->amiga->denise;
    const u64 *disk = s->amiga->paula.diskController.rrCounts;
    fprintf(o, "{\"bitplane_lines\":[%llu,%llu,%llu],\"bitplane_words\":[%llu,%llu],\"line_pass\":[%llu,%llu],\"disk_idle\":[%llu,%llu,%llu,%llu],"
               "\"sprite_slots_left_out\":%llu}",
            (unsigned long long)agnus.rrLines[0], (unsigned long long)agnus.rrLines[1], (unsigned long long)agnus.rrLines[2],
            (unsigned long long)agnus.rrWords[0], (unsigned long long)agnus.rrWords[1],
            (unsigned long long)denise.rrQuietLines[0], (unsigned long long)denise.rrQuietLines[1],
            (unsigned long long)disk[0], (unsigned long long)disk[1], (unsigned long long)disk[2], (unsigned long long)disk[3],
            (unsigned long long)agnus.rrSprSkipped);
}
extern "C" long rr_amiga_resload_calls(const RrAmigaSession *s) { return s->calls; }
extern "C" int rr_amiga_write_resload_log(const RrAmigaSession *s, const char *path) {
    FILE *o = open_file(path, "wb");
    if (!o) return 0;
    fwrite(s->log.data(), 1, s->log.size(), o);
    return fclose(o) == 0;
}

// ---- quick states ----------------------------------------------------------------------------------------------------
// magic, ABI string, the install's identity, frame, inputs held, sizes, a checksum (FNV-1a 64 of the whole file with this field
// zero), then the resload state (its host callbacks are this process's), the keys held, vAmiga's snapshot and the sound path's
// memory. A state of another build or install, or one whose bytes changed, is refused before the machine is touched.
// `port1`: the device port 1 holds (bit 0: the joystick; vAmiga's snapshot does not keep it) and the second joystick's held bits (8-15).
struct StateHead { char magic[16]; char abi[72]; char identity[72]; uint64_t frame; uint32_t joy, mouse_left, mouse_right, snapshot_size, audio_size, port1; uint64_t checksum; };
static_assert(sizeof(StateHead) == 200, "the Amiga state header is 200 bytes (retrorecomp/amiga_conversion.py, damaged_states)");

// vAmiga's state and the sound path's, from a quick state (`in_process` false: a Snapshot, checked by vAmiga) or a session's
// snapshot (CoreComponent::rrLoad, every component's size checked before a byte is read). false: refused.
static bool machine_load(RrAmigaSession *s, const uint8_t *data, size_t size, bool in_process, const uint8_t *audio, size_t audio_size) {
    kick_window(false);
    try {
        if (in_process) {
            if (s->amiga->rrLoad(data, (isize)size) != (isize)size) { kick_window(true); return false; }
        } else {
            s->amiga->loadSnapshot(Snapshot(data, (isize)size));
        }
        s->amiga->agnus.rrAfterLoad();   // stage 7's derived state of the timeline left goes
    } catch (std::exception &) {
        kick_window(true);
        return false;
    }
    if (!s->amiga->audioPort.rrLoadAudio(audio, audio_size)) { kick_window(true); return false; }
    s->amiga->audioPort.stream.clear(SamplePair{0, 0});   // the load may have padded the stream; the frames after it hold only what they make
    return true;
}

// The session's own state after machine_load: the resload state (this process's host callbacks kept), the Kickstart's window, the
// frame, the inputs held, port 1's device, the keys, the CPU's speed (the player's own, or the session's), the traps and the hook.
static void after_load(RrAmigaSession *s, RrResload rl, uint64_t frame, unsigned joy, unsigned joy2, int mouse_left, int mouse_right,
                       int port1_joystick, const uint8_t keys[128]) {
    rl.host = s->rl.host;
    s->rl = rl;
    // The Kickstart the saved timeline had loaded, wherever it came from (a header loads it before the slave, but
    // resload_LoadKick only when the slave calls it): its copy is in the restored ExpMem, so only the window is set again. A timeline
    // saved before its resload_LoadKick (a session rolled back past it) has none yet: vAmiga's own mapping, as before the call.
    if (s->rl.kick_loaded && s->rl.exp_mem && (s->rl.kick_size == 0x40000 || s->rl.kick_size == 0x80000) && s->kick.size() == s->rl.kick_size) {
        s->kick_base = s->rl.exp_mem;
        s->kick_size = s->rl.kick_size;
    } else {
        s->kick_base = s->kick_size = 0;
    }
    native_kick_window();
    kick_window(true);
    s->frame = frame;
    // The inputs held when the state was saved: what the machine's ports hold now.
    s->joy = joy; s->joy2 = joy2; s->mouse_left = mouse_left; s->mouse_right = mouse_right;
    // vAmiga's joysticks and mouse buttons come back from a snapshot neutral (a fire button held at the save was lost: a state saved in a
    // Lotus 2 race, fire held, continued with the fire released, 14 Nov 2026), and the next frame's inputs, unchanged, would not press them
    // again: what was held is pressed again here, from neutral, as the frame's inputs would. Port 1 is then plugged as it was saved.
    joystick_actions(s->amiga->controlPort2.joystick, 0, s->joy);
    joystick_actions(s->amiga->controlPort1.joystick, 0, s->joy2);
    if (s->mouse_left) s->amiga->controlPort1.mouse.trigger(GamePadAction::PRESS_LEFT);
    if (s->mouse_right) s->amiga->controlPort1.mouse.trigger(GamePadAction::PRESS_RIGHT);
    s->port1_joystick = port1_joystick;
    s->amiga->controlPort1.setDevice(s->port1_joystick ? ControlPortDevice::JOYSTICK : ControlPortDevice::MOUSE);
    memcpy(s->keys, keys, sizeof s->keys);
    s->amiga->keyboard.rrSetKeysDown(keys);   // the keyboard's own held keys (no snapshot keeps them): those held at the save
    // The snapshot restored the CPU speed it was saved with; the player's own choice holds.
    apply_cpu_factor(s);
    set_traps();
    update_hook();
}

extern "C" int rr_amiga_state_save(RrAmigaSession *s, const char *path, const char *abi, const char *identity) {
    try {
        // vAmiga saves an ordinary machine: the WOM over ExpMem is lifted around the snapshot (its reader reallocates
        // ROM and WOM buffers by the sizes it was configured with, which an alias is not), then set again. The image and
        // what was patched into it are in slow RAM, which the snapshot keeps. Stage 7's held-back disk events that are due
        // run first: a snapshot keeps none of them (Agnus::rrBeforeSave).
        s->amiga->agnus.rrBeforeSave();
        kick_window(false);
        std::unique_ptr<Snapshot> snap;
        try { snap = s->amiga->takeSnapshot(utl::Compressor::NONE); } catch (...) { kick_window(true); throw; }
        kick_window(true);
        StateHead head{};
        memcpy(head.magic, STATE_MAGIC, sizeof head.magic);
        snprintf(head.abi, sizeof head.abi, "%s", abi ? abi : "");
        snprintf(head.identity, sizeof head.identity, "%s", identity ? identity : "");
        head.frame = s->frame; head.joy = s->joy; head.mouse_left = (uint32_t)s->mouse_left; head.mouse_right = (uint32_t)s->mouse_right;
        head.port1 = (uint32_t)rr_amiga_port1_device(s) | (s->joy2 & 0xFFu) << 8;
        head.snapshot_size = (uint32_t)snap->data.size;
        // The sound path's own memory (samplers, filters, volume ramps), which the snapshot leaves out.
        std::vector<uint8_t> audio;
        s->amiga->audioPort.rrSaveAudio(audio);
        head.audio_size = (uint32_t)audio.size();
        // The interlaced field held for the picture's weave (amiga_session.h), after the sound: 0, or 1 | its long-frame bit << 1, then its lines.
        const uint32_t held_info = s->held_lof >= 0 && s->held.size() == (size_t)RR_AMIGA_PICTURE_WIDTH * s->lines ? 1u | (uint32_t)s->held_lof << 1 : 0u;
        const size_t held_bytes = held_info ? s->held.size() * sizeof(uint32_t) : 0;
        // Then the field before it, the same way (kept only when it is the frame just before the held one).
        const uint32_t prior_info = held_info && s->prior_lof >= 0 && s->prior_frame + 1 == s->held_frame && s->prior.size() == s->held.size()
                                    ? 1u | (uint32_t)s->prior_lof << 1 : 0u;
        const size_t prior_bytes = prior_info ? s->prior.size() * sizeof(uint32_t) : 0;
        uint64_t sum = fnv(14695981039346656037ull, &head, sizeof head);
        sum = fnv(sum, &s->rl, sizeof s->rl);
        sum = fnv(sum, s->keys, sizeof s->keys);
        sum = fnv(sum, snap->data.ptr, (size_t)snap->data.size);
        sum = fnv(sum, audio.data(), audio.size());
        sum = fnv(sum, &held_info, sizeof held_info);
        sum = fnv(sum, s->held.data(), held_bytes);
        sum = fnv(sum, &prior_info, sizeof prior_info);
        head.checksum = fnv(sum, s->prior.data(), prior_bytes);
        std::string temporary = std::string(path) + ".tmp";
        FILE *f = open_file(temporary.c_str(), "wb");
        if (!f) return 4;
        bool ok = fwrite(&head, sizeof head, 1, f) == 1 && fwrite(&s->rl, sizeof s->rl, 1, f) == 1 &&
                  fwrite(s->keys, sizeof s->keys, 1, f) == 1 && fwrite(snap->data.ptr, 1, (size_t)snap->data.size, f) == (size_t)snap->data.size &&
                  fwrite(audio.data(), 1, audio.size(), f) == audio.size() && fwrite(&held_info, sizeof held_info, 1, f) == 1 &&
                  fwrite(s->held.data(), 1, held_bytes, f) == held_bytes && fwrite(&prior_info, sizeof prior_info, 1, f) == 1 &&
                  fwrite(s->prior.data(), 1, prior_bytes, f) == prior_bytes;
        ok = fclose(f) == 0 && ok;
        std::error_code ec;
        if (ok) fs::rename(upath(temporary), upath(path), ec);
        if (!ok || ec) { fs::remove(upath(temporary), ec); return 4; }
        return 0;
    } catch (std::exception &) {
        return 4;
    }
}

extern "C" int rr_amiga_state_load(RrAmigaSession *s, const char *path, const char *abi, const char *identity) {
    FILE *f = open_file(path, "rb");
    if (!f) return 1;
    StateHead head{};
    RrResload rl{};
    uint8_t keys[128];
    std::vector<uint8_t> data;
    bool ok = fread(&head, sizeof head, 1, f) == 1;
    if (ok && (memcmp(head.magic, STATE_MAGIC, sizeof head.magic) || strncmp(head.abi, abi ? abi : "", sizeof head.abi) ||
               strncmp(head.identity, identity ? identity : "", sizeof head.identity))) { fclose(f); return 2; }
    ok = ok && !(head.port1 & ~0xFF01u);       // only the device bit and the joystick's bits
    ok = ok && fread(&rl, sizeof rl, 1, f) == 1 && fread(keys, sizeof keys, 1, f) == 1 && head.snapshot_size && head.snapshot_size < (256u << 20) && head.audio_size < (64u << 20);
    std::vector<uint8_t> audio;
    if (ok) { data.resize(head.snapshot_size); ok = fread(data.data(), 1, data.size(), f) == data.size(); }
    if (ok) { audio.resize(head.audio_size); ok = fread(audio.data(), 1, audio.size(), f) == audio.size(); }
    uint32_t held_info = 0;
    std::vector<uint32_t> held;
    ok = ok && fread(&held_info, sizeof held_info, 1, f) == 1 && !(held_info & ~3u) && (held_info & 1u || !held_info);
    if (ok && held_info) { held.resize((size_t)RR_AMIGA_PICTURE_WIDTH * s->lines); ok = fread(held.data(), sizeof(uint32_t), held.size(), f) == held.size(); }
    uint32_t prior_info = 0;
    std::vector<uint32_t> prior;
    ok = ok && fread(&prior_info, sizeof prior_info, 1, f) == 1 && !(prior_info & ~3u) && (prior_info & 1u || !prior_info) && (held_info || !prior_info);
    if (ok && prior_info) { prior.resize((size_t)RR_AMIGA_PICTURE_WIDTH * s->lines); ok = fread(prior.data(), sizeof(uint32_t), prior.size(), f) == prior.size(); }
    uint8_t extra;
    ok = ok && fread(&extra, 1, 1, f) == 0;      // nothing after the fields
    fclose(f);
    if (ok) {
        const uint64_t expected = head.checksum;
        head.checksum = 0;
        uint64_t sum = fnv(14695981039346656037ull, &head, sizeof head);
        sum = fnv(sum, &rl, sizeof rl);
        sum = fnv(sum, keys, sizeof keys);
        sum = fnv(sum, data.data(), data.size());
        sum = fnv(sum, audio.data(), audio.size());
        sum = fnv(sum, &held_info, sizeof held_info);
        sum = fnv(sum, held.data(), held.size() * sizeof(uint32_t));
        sum = fnv(sum, &prior_info, sizeof prior_info);
        ok = fnv(sum, prior.data(), prior.size() * sizeof(uint32_t)) == expected;
    }
    if (!ok) return 3;
    if (!machine_load(s, data.data(), data.size(), false, audio.data(), audio.size())) return 3;
    after_load(s, rl, head.frame, head.joy, head.port1 >> 8 & 0xFFu, (int)head.mouse_left, (int)head.mouse_right, (int)(head.port1 & 1u), keys);
    // The field the saved frame ended with, for the next frame's weave (none held: the next interlaced frame starts alone).
    s->held = std::move(held);
    s->held_lof = held_info ? (int)(held_info >> 1 & 1u) : -1;
    s->held_frame = head.frame;
    s->prior = std::move(prior);
    s->prior_lof = prior_info ? (int)(prior_info >> 1 & 1u) : -1;
    s->prior_frame = head.frame - 1;
    return 0;
}

// ---- the in-process snapshot of a multiplayer session (rollback) ----------------------------------------------------------
// The head (named fields), the resload state as this process holds it (its host callbacks are this process's: never sent), vAmiga's
// state (CoreComponent::rrSave: the same bytes as a quick state's snapshot, without its checksums), the sound path, a session's saves.
struct SnapHead { uint32_t magic, vamiga, audio, overlay; uint64_t frame; uint32_t joy, joy2, mouse_left, mouse_right, port1_joystick; uint8_t keys[128], keys_down[128]; };
static constexpr uint32_t SNAP_MAGIC = 0x52524153u;   // "RRAS"

extern "C" size_t rr_amiga_snap_bound(RrAmigaSession *s) {
    kick_window(false);
    const size_t machine = (size_t)s->amiga->size();
    kick_window(true);
    return sizeof(SnapHead) + sizeof(RrResload) + machine + s->amiga->audioPort.rrAudioBound() + s->overlay.size();
}

extern "C" size_t rr_amiga_snap_save(RrAmigaSession *s, void *buffer, size_t capacity) {
    uint8_t *out = (uint8_t *)buffer;
    SnapHead head{};
    size_t at = sizeof head + sizeof s->rl;
    if (capacity < at) return 0;
    try {
        s->amiga->agnus.rrBeforeSave();     // as a quick state: no disk event or batched line is left held back
        kick_window(false);
        isize n = 0;
        try { n = s->amiga->rrSave(out + at, (isize)(capacity - at)); } catch (...) { kick_window(true); throw; }
        kick_window(true);
        if (n <= 0) return 0;
        head.vamiga = (uint32_t)n;
        at += (size_t)n;
    } catch (std::exception &) {
        return 0;
    }
    const size_t audio = s->amiga->audioPort.rrSaveAudioTo(out + at, capacity - at);
    if (!audio) return 0;
    head.audio = (uint32_t)audio;
    at += audio;
    if (s->overlay_used > capacity - at) return 0;
    memcpy(out + at, s->overlay.data(), s->overlay_used);
    head.overlay = (uint32_t)s->overlay_used;
    at += s->overlay_used;
    head.magic = SNAP_MAGIC;
    head.frame = s->frame; head.joy = s->joy; head.joy2 = s->joy2;
    head.mouse_left = (uint32_t)s->mouse_left; head.mouse_right = (uint32_t)s->mouse_right; head.port1_joystick = (uint32_t)s->port1_joystick;
    memcpy(head.keys, s->keys, sizeof head.keys);
    s->amiga->keyboard.rrKeysDown(head.keys_down);
    memcpy(out, &head, sizeof head);
    memcpy(out + sizeof head, &s->rl, sizeof s->rl);
    return at;
}

extern "C" int rr_amiga_snap_load(RrAmigaSession *s, const void *buffer, size_t size) {
    const uint8_t *in = (const uint8_t *)buffer;
    SnapHead head;
    RrResload rl;
    if (!buffer || size < sizeof head + sizeof rl) return 0;
    memcpy(&head, in, sizeof head);
    memcpy(&rl, in + sizeof head, sizeof rl);
    if (head.magic != SNAP_MAGIC || head.overlay > s->overlay.size() ||
        sizeof head + sizeof rl + (size_t)head.vamiga + head.audio + head.overlay != size) return 0;
    const uint8_t *machine = in + sizeof head + sizeof rl;
    if (!machine_load(s, machine, head.vamiga, true, machine + head.vamiga, head.audio)) return 0;
    memcpy(s->overlay.data(), machine + head.vamiga + head.audio, head.overlay);
    s->overlay_used = head.overlay;
    after_load(s, rl, head.frame, head.joy, head.joy2, (int)head.mouse_left, (int)head.mouse_right, (int)head.port1_joystick, head.keys);
    s->amiga->keyboard.rrSetKeysDown(head.keys_down);   // exactly the keyboard's (a full queue may not have taken a held key)
    // The picture's held fields belong to the timeline left (no allocation: the buffers keep their room).
    s->held.clear(); s->held_lof = -1;
    s->prior.clear(); s->prior_lof = -1;
    s->pcm.clear();
    return 1;
}

static void put_le(uint64_t &h, uint64_t value, int bytes) {
    for (int b = 0; b < bytes; b++) { const uint8_t v = (uint8_t)(value >> (8 * b)); h = fnv(h, &v, 1); }
}

extern "C" uint64_t rr_amiga_digest(RrAmigaSession *s) {
    // vAmiga's state through the snapshot's own walk, into a buffer kept for the digests (the first one sizes it).
    static std::vector<uint8_t> scratch;
    uint64_t h = 14695981039346656037ull;
    put_le(h, s->frame, 8);
    put_le(h, s->joy, 4); put_le(h, s->joy2, 4); put_le(h, (uint32_t)s->mouse_left, 4); put_le(h, (uint32_t)s->mouse_right, 4);
    put_le(h, (uint32_t)s->port1_joystick, 4);
    put_le(h, s->kick_base, 4); put_le(h, s->kick_size, 4);
    put_le(h, s->rl.io_error, 4); put_le(h, s->rl.kick_loaded, 1);
    h = fnv(h, s->keys, sizeof s->keys);
    {
        uint8_t down[128];
        s->amiga->keyboard.rrKeysDown(down);
        h = fnv(h, down, sizeof down);
    }
    try {
        kick_window(false);
        const size_t need = (size_t)s->amiga->size();
        if (scratch.size() < need) scratch.resize(need);
        isize n = 0;
        try { s->amiga->agnus.rrBeforeSave(); n = s->amiga->rrSave(scratch.data(), (isize)scratch.size()); } catch (...) { kick_window(true); throw; }
        kick_window(true);
        put_le(h, (uint64_t)n, 8);
        h = fnv(h, scratch.data(), (size_t)std::max<isize>(n, 0));
    } catch (std::exception &) {
        put_le(h, 0, 8);
    }
    put_le(h, s->overlay_used, 8);
    return fnv(h, s->overlay.data(), s->overlay_used);
}

extern "C" void rr_amiga_side_effects(RrAmigaSession *s, int allowed) { s->effects = allowed != 0; }

// The session's saves as one image: "RRSV", then the overlay's entries (amiga_session.cpp, overlay_walk). Never empty, so a host
// without saves still sends one, and a guest then plays without its own.
static constexpr uint8_t SAVES_MAGIC[4] = {'R', 'R', 'S', 'V'};

extern "C" size_t rr_amiga_session_save(RrAmigaSession *s, void *out, size_t capacity) {
    const size_t need = sizeof SAVES_MAGIC + s->overlay_used;
    if (!s->session) return 0;
    if (!out) return need;
    if (capacity < need) return 0;
    memcpy(out, SAVES_MAGIC, sizeof SAVES_MAGIC);
    memcpy((uint8_t *)out + sizeof SAVES_MAGIC, s->overlay.data(), s->overlay_used);
    return need;
}

extern "C" int rr_amiga_session_save_put(RrAmigaSession *s, const void *in, size_t size) {
    const uint8_t *p = (const uint8_t *)in;
    if (!s->session || !in || size < sizeof SAVES_MAGIC || memcmp(p, SAVES_MAGIC, sizeof SAVES_MAGIC)) return 0;
    p += sizeof SAVES_MAGIC;
    size -= sizeof SAVES_MAGIC;
    if (size > s->overlay.size()) return 0;
    // Whole entries only, each a name the save folder could hold.
    size_t at = 0;
    while (at < size) {
        if (size - at < 7) return 0;
        const size_t length = (size_t)p[at] | (size_t)p[at + 1] << 8;
        if (size - at < 7 + length || p[at + 2 + length] > 1) return 0;
        const uint32_t n = le32(p + at + 3 + length);
        if (size - at - 7 - length < n) return 0;
        if (!rr_amiga_savefile::inside_folder(std::string((const char *)p + at + 2, length))) return 0;
        at += 7 + length + n;
    }
    memcpy(s->overlay.data(), p, size);
    s->overlay_used = size;
    return 1;
}
