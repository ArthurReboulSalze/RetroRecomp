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

namespace vamiga::moira { extern bool (*rr_moira_native)(Moira &, u32 pc, u16 opcode); }

static constexpr uint32_t SLOW_BASE = 0xC00000;
static constexpr uint32_t SLOW_SIZE = 0x180000;     // 1.5 MiB of slow RAM: ExpMem, then the slave area
static constexpr const char STATE_MAGIC[16] = "RRAMIGA-STATE-1";
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
    RrResloadHost host{};
    RrResload rl{};
    uint32_t resload_table = 0;
    uint64_t frame = 0;
    long calls = 0;
    std::string error, log;
    bool quit = false;         // the install ended itself with resload_Abort(TDREASON_OK): a normal exit, not a failure
    unsigned joy = 0;
    int mouse_left = 0, mouse_right = 0;
    uint8_t keys[128] = {};
    std::vector<int16_t> pcm;
    std::vector<uint32_t> picture;
    int lines = 0;
    bool view_seen = false;
    int view[4] = {};          // union of the display windows opened so far: left, top, right, bottom (picture columns, rows)
    bool observing = false, native = false;
    std::set<std::pair<uint32_t, std::string>> observed;
    uint64_t native_count = 0, interpreted_count = 0;
    std::map<std::string, std::string> display;               // lower-case name -> the name as the install spells it
    std::vector<std::pair<std::string, uint32_t>> listing;    // the files as resload_Examine/ExNext/ListFiles see them
    std::vector<uint8_t> kick;                                // the player's Kickstart (host memory only)
    uint32_t kick_base = 0, kick_size = 0;                    // where it sits in ExpMem once loaded (0: not loaded)
    uint64_t kick_interpreted = 0;
};

static RrAmigaSession *S;   // the hooks of Moira and of the resload layer reach the one session of the process

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
    auto it = S->files.find(key_of(name));
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
        for (auto &f : S->files) {
            auto shown = S->display.find(f.first);
            S->listing.push_back({to_latin1(shown != S->display.end() ? shown->second : f.first), (uint32_t)f.second.size()});
        }
    }
    if (index >= S->listing.size()) return 0;
    *name = S->listing[index].first.c_str();
    *size = S->listing[index].second;
    return 1;
}

// The player's Kickstart into ExpMem, when the slave's request matches it. The image keeps the addresses it was built for (no
// relocation table): vAmiga's WOM (the A1000's writable ROM, left unlocked) is pointed at the copy, so the window
// $FC0000-$FFFFFF reads and writes the same bytes as ExpMem, and what the slave patches or writes into the image through either
// address is what runs. 256 KiB images only (Kickstart 1.x): a 512 KiB image would need the whole $F80000 window writable.
// The window over the copy in ExpMem (on), or vAmiga's own ROM mapping (off, around a snapshot).
static void kick_window(bool on) {
    if (!S->kick_size) return;
    Memory &mem = S->amiga->mem;
    mem.wom = on ? mem.slow + (S->kick_base - SLOW_BASE) : nullptr;
    mem.womMask = on ? S->kick_size - 1 : 0;
    mem.womIsLocked = false;
    mem.updateMemSrcTables();
}

static int kick_cb(void *, uint32_t size, uint16_t crc16, const char *, uint32_t destination) {
    if (S->kick.size() != size || size != 0x40000) return 0;
    if (destination < SLOW_BASE || destination + size > SLOW_BASE + SLOW_SIZE || (destination & (size - 1)) != 0) return 0;
    for (uint32_t i = 0; i < size; i++) poke(nullptr, destination + i, S->kick[i]);
    if (rr_resload_crc16(&S->rl, destination, size) != crc16) {
        for (uint32_t i = 0; i < size; i++) poke(nullptr, destination + i, 0);
        return 0;
    }
    S->kick_base = destination;
    S->kick_size = size;
    kick_window(true);
    return 1;
}

static bool in_kickstart(uint32_t pc) {
    return S->kick_size && (pc >= 0xF80000 || (pc >= S->kick_base && pc < S->kick_base + S->kick_size));
}

// A save goes to the game's own folder (and replaces the install's file there on the next start).
static int save_cb(void *, const char *name, uint32_t offset, const uint8_t *data, uint32_t size, int whole) {
    auto &f = S->files[key_of(name)];
    if (whole) f.assign(data, data + size);
    else { if (f.size() < (size_t)offset + size) f.resize((size_t)offset + size, 0); std::copy(data, data + size, f.begin() + offset); }
    if (!S->saves) return 0;
    std::error_code ec;
    fs::path target = S->save_dir / upath(key_of(name));
    fs::create_directories(target.parent_path(), ec);
    fs::path temporary = target; temporary += ".tmp";
    {
        std::ofstream out(temporary, std::ios::binary | std::ios::trunc);
        if (!out.write((const char *)f.data(), (std::streamsize)f.size())) return RR_DOS_DISK_FULL;
    }
    fs::rename(temporary, target, ec);
    return ec ? RR_DOS_DISK_FULL : 0;
}

static int remove_cb(void *, const char *name) {
    S->files.erase(key_of(name));
    if (S->saves) { std::error_code ec; fs::remove(S->save_dir / upath(key_of(name)), ec); }
    return 0;
}

// Observation and native steps: the hook Moira calls before each instruction (true: a native step ran it).
#ifdef RR_AMIGA_NATIVE
struct RrAmigaStep;
extern "C" const RrAmigaStep *rr_amiga_lookup(uint32_t pc);
extern "C" void (*rr_amiga_step_of(const RrAmigaStep *))(void *, uint16_t);
extern "C" int rr_amiga_code_word(uint32_t pc, uint16_t *word) { *word = peek16(pc); return 1; }
#endif
static bool instruction_hook(vamiga::moira::Moira &m, u32 pc, u16 op) {
#ifdef RR_AMIGA_NATIVE
    if (S->native) {
        if (const RrAmigaStep *step = rr_amiga_lookup(pc)) { rr_amiga_step_of(step)(&m, op); S->native_count++; return true; }
    }
#else
    (void)m; (void)op;
#endif
    S->interpreted_count++;
    // The Kickstart's own code (the window, or its copy in ExpMem) stays on the interpreter, counted apart, and is never
    // observed: an observation keeps instruction bytes, and the Kickstart's bytes are the player's, not ours to store.
    if (in_kickstart(pc)) { S->kick_interpreted++; return false; }
    if (S->observing && in_ram(pc)) {
        char hex[25];
        for (int i = 0; i < 12; i++) snprintf(hex + 2 * i, 3, "%02x", peek(nullptr, pc + (uint32_t)i));
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
        0x60FE};                                 // bra.s *
    auto put = [&](size_t at, const uint16_t *w, size_t n) {
        for (size_t i = 0; i < n; i++) { rom[at + 2 * i] = (uint8_t)(w[i] >> 8); rom[at + 2 * i + 1] = (uint8_t)w[i]; }
    };
    put(0, head, 4);
    put(0xD2, code, sizeof code / 2);
    return rom;
}

static void jump(CPU &cpu, uint32_t pc) { cpu.setPC(pc); cpu.setIRD(peek16(pc)); cpu.setIRC(peek16(pc + 2)); }

static void set_breakpoints() {
    auto &bp = S->amiga->cpu.debugger.breakpoints;
    for (uint32_t k = 0; k < RR_RESLOAD_ENTRIES; k++)
        if (!bp.isSetAt(S->resload_table + 4 * k)) bp.setAt(S->resload_table + 4 * k);
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
    uint32_t base_mem = be32(p + 16);
    int32_t exp_mem = version >= 8 ? (int32_t)be32(p + 32) : 0;
    uint32_t exp_size = exp_mem < 0 ? (uint32_t)-exp_mem : (uint32_t)exp_mem;
    uint32_t exp_base = exp_size ? SLOW_BASE : 0;
    uint32_t slave_area = (SLOW_BASE + exp_size + 0xFFF) & ~0xFFFu;
    S->resload_table = slave_area + 0x40000;
    uint32_t stack_top = slave_area + 0x7FFF0;
    uint32_t chip = (uint32_t)S->amiga->mem.chipRamSize();
    if (stack_top >= SLOW_BASE + SLOW_SIZE || base_mem > chip || n > 0x3F000)
        return fail(error, error_size, "The install's memory does not fit the Amiga 500 layout (BaseMem, ExpMem or slave too large).");

    // BaseMem and ExpMem filled as WHDLoad does ($CCCCCCCC, or 0 with WHDLF_ClearMem), $0 = 0, $4 = $F0000001.
    uint32_t fill = (flags & 0x1000) ? 0 : 0xCCCCCCCCu;
    for (uint32_t a = 0; a < base_mem; a += 4) poke32(a, fill);
    for (uint32_t a = 0; a < exp_size; a += 4) poke32(exp_base + a, fill);
    poke32(0, 0);
    poke32(4, 0xF0000001u);
    for (size_t i = 0; i < n; i++) poke(nullptr, slave_area + (uint32_t)i, slave[i]);
    for (uint32_t k = 0; k < RR_RESLOAD_ENTRIES; k++) poke32(S->resload_table + 4 * k, 0x4E754E71);

    S->host = RrResloadHost{nullptr, peek, poke, file_cb, game->save_dir ? save_cb : nullptr, game->save_dir ? remove_cb : nullptr, nullptr};
    S->host.list = list_cb;
    S->host.kickstart = kick_cb;
    rr_resload_init(&S->rl, &S->host, slave_area, version, flags);
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
    if (version >= 16 && peek32(slave_area + 44) == 0x80000)
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
    set_breakpoints();
    char line[160];
    snprintf(line, sizeof line, "slave v%u flags %04x base %06x exp %06x@%06x slave %06x loader %06x resload %06x\n", version, flags,
             base_mem, exp_size, exp_base, slave_area, loader, S->resload_table);
    S->log += line;
    return true;
}

extern "C" RrAmigaSession *rr_amiga_open(const RrAmigaGame *game, char *error, size_t error_size) {
    if (S) { fail(error, error_size, "One Amiga session per process."); return nullptr; }
    S = new RrAmigaSession;
    S->ntsc = game->ntsc != 0;
    for (unsigned i = 0; i < game->file_count; i++) {
        S->files[lower(game->files[i].name)] = std::vector<uint8_t>(game->files[i].data, game->files[i].data + game->files[i].size);
        S->display[lower(game->files[i].name)] = game->files[i].name;
    }
    if (game->kickstart && game->kickstart_size) S->kick.assign(game->kickstart, game->kickstart + game->kickstart_size);
    if (game->save_dir && *game->save_dir) {
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
        // The chip RAM the install's BaseMem needs (512 KiB, or 1 MiB above it), read before the machine is configured.
        uint32_t chip_kb = 512;
        {
            const uint8_t *b = game->slave; size_t n = game->slave_size;
            auto be32 = [&](size_t o) -> uint32_t { return o + 4 <= n ? (uint32_t)b[o] << 24 | (uint32_t)b[o + 1] << 16 | (uint32_t)b[o + 2] << 8 | b[o + 3] : 0; };
            size_t q = 4; while (be32(q) && q < n) q += 4 + 4 * (size_t)be32(q); q += 4;
            uint32_t f = be32(q + 4), l = be32(q + 8); q += 12 + 4 * (size_t)(l - f + 1) + 8;
            if (be32(q + 16) > 0x80000) chip_kb = 1024;
        }
        S->emu = new Emulator;
        S->emu->initialize();
        S->emu->set(ConfigScheme::A500_ECS_1MB);
        S->emu->set(Opt::AMIGA_VIDEO_FORMAT, S->ntsc ? (i64)TV::NTSC : (i64)TV::PAL);
        S->emu->set(Opt::MEM_SLOW_RAM, SLOW_SIZE / 1024);
        S->emu->set(Opt::MEM_CHIP_RAM, chip_kb);
        S->emu->set(Opt::MON_PALETTE, (i64)Palette::RGB);   // plain 4-bit to 8-bit colours, no monitor model
        S->emu->set(Opt::MEM_RAM_INIT_PATTERN, (i64)RamInitPattern::ALL_ZEROES);
        S->emu->set(Opt::AUD_ASR, 0);                       // a fixed sample rate: the sound does not follow the host's clock
        S->amiga = &S->emu->rrMain();
        S->amiga->audioPort.setSampleRate((double)RR_AMIGA_AUDIO_RATE);
        auto rom = boot_rom();
        S->amiga->mem.loadRom(rom.data(), (isize)rom.size());
        S->amiga->powerOn();
        S->amiga->run();
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
    S->picture.assign((size_t)RR_AMIGA_PICTURE_WIDTH * RR_AMIGA_PICTURE_MAX_HEIGHT, 0xFF000000u);
    return S;
}

extern "C" void rr_amiga_joystick(RrAmigaSession *s, unsigned bits) {
    auto &joy = s->amiga->controlPort2.joystick;
    unsigned was = s->joy;
    auto axis = [&](unsigned minus, unsigned plus, GamePadAction pull_minus, GamePadAction pull_plus, GamePadAction release) {
        int before = (was & plus ? 1 : 0) - (was & minus ? 1 : 0), after = (bits & plus ? 1 : 0) - (bits & minus ? 1 : 0);
        if (before == after) return;
        joy.trigger(after < 0 ? pull_minus : after > 0 ? pull_plus : release);
    };
    axis(RR_AMIGA_JOY_LEFT, RR_AMIGA_JOY_RIGHT, GamePadAction::PULL_LEFT, GamePadAction::PULL_RIGHT, GamePadAction::RELEASE_X);
    axis(RR_AMIGA_JOY_UP, RR_AMIGA_JOY_DOWN, GamePadAction::PULL_UP, GamePadAction::PULL_DOWN, GamePadAction::RELEASE_Y);
    if ((bits ^ was) & RR_AMIGA_JOY_FIRE) joy.trigger(bits & RR_AMIGA_JOY_FIRE ? GamePadAction::PRESS_FIRE : GamePadAction::RELEASE_FIRE);
    if ((bits ^ was) & RR_AMIGA_JOY_FIRE2) joy.trigger(bits & RR_AMIGA_JOY_FIRE2 ? GamePadAction::PRESS_FIRE2 : GamePadAction::RELEASE_FIRE2);
    s->joy = bits;
}

extern "C" void rr_amiga_mouse(RrAmigaSession *s, int dx, int dy, int left, int right) {
    auto &mouse = s->amiga->controlPort1.mouse;
    if (dx || dy) mouse.setDxDy((double)dx, (double)dy);
    if (!left != !s->mouse_left) mouse.trigger(left ? GamePadAction::PRESS_LEFT : GamePadAction::RELEASE_LEFT);
    if (!right != !s->mouse_right) mouse.trigger(right ? GamePadAction::PRESS_RIGHT : GamePadAction::RELEASE_RIGHT);
    s->mouse_left = left != 0; s->mouse_right = right != 0;
}

extern "C" void rr_amiga_keys(RrAmigaSession *s, const uint8_t held[128]) {
    for (unsigned k = 0; k < 128; k++) {
        if (!held[k] == !s->keys[k]) continue;
        if (held[k]) s->amiga->keyboard.press((KeyCode)k); else s->amiga->keyboard.release((KeyCode)k);
        s->keys[k] = held[k] ? 1 : 0;
    }
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
    for (int y = 0; y < s->lines; y++) {
        const uint32_t *row = px + (size_t)(first + y) * Tex::width + FIRST_TEXEL;
        uint32_t *out = s->picture.data() + (size_t)y * RR_AMIGA_PICTURE_WIDTH;
        for (int x = 0; x < RR_AMIGA_PICTURE_WIDTH; x++) {
            uint32_t c = row[2 * x];
            out[x] = 0xFF000000u | (c & 0xFFu) << 16 | (c & 0xFF00u) | (c >> 16 & 0xFFu);
        }
    }
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

extern "C" int rr_amiga_viewport(const RrAmigaSession *s, int *x, int *y, int *w, int *h) {
    if (!s->view_seen) return 0;
    *x = s->view[0]; *y = s->view[1]; *w = s->view[2] - s->view[0]; *h = s->view[3] - s->view[1];
    return 1;
}

extern "C" const uint32_t *rr_amiga_picture(const RrAmigaSession *s, int *width, int *height) {
    *width = RR_AMIGA_PICTURE_WIDTH; *height = s->lines;
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
    info->video = fnv(basis, s->picture.data(), (size_t)RR_AMIGA_PICTURE_WIDTH * s->lines * sizeof(uint32_t));
    info->pcm = fnv(basis, s->pcm.data(), s->pcm.size() * sizeof(int16_t));
    uint64_t ram = fnv(basis, amiga.mem.chip, (size_t)amiga.mem.chipRamSize());
    if (amiga.mem.slow) ram = fnv(ram, amiga.mem.slow, (size_t)amiga.mem.slowRamSize());
    if (amiga.mem.fast && amiga.mem.fastRamSize()) ram = fnv(ram, amiga.mem.fast, (size_t)amiga.mem.fastRamSize());
    info->ram = ram;
    info->pc = amiga.cpu.getPC(); info->sr = amiga.cpu.getSR();
    for (int i = 0; i < 8; i++) { info->d[i] = amiga.cpu.getD(i); info->a[i] = amiga.cpu.getA(i); }
    info->samples = (uint32_t)(s->pcm.size() / 2);
    for (size_t i = 0; i < s->pcm.size() && !info->audible; i++) info->audible = s->pcm[i] != 0;
    for (size_t i = 0; i < (size_t)RR_AMIGA_PICTURE_WIDTH * s->lines && !info->nonblack; i++) info->nonblack = (s->picture[i] & 0xFFFFFFu) != 0;
}

extern "C" int rr_amiga_set_native(RrAmigaSession *s, int enabled) {
#ifdef RR_AMIGA_NATIVE
    s->native = enabled != 0; update_hook(); return 1;
#else
    (void)s; return !enabled;
#endif
}
extern "C" void rr_amiga_set_observe(RrAmigaSession *s, int enabled) { s->observing = enabled != 0; update_hook(); }
extern "C" int rr_amiga_write_observations(const RrAmigaSession *s, const char *path) {
    FILE *o = open_file(path, "wb");
    if (!o) return 0;
    for (auto &e : s->observed) fprintf(o, "%06x %s\n", e.first, e.second.c_str());
    return fclose(o) == 0;
}
extern "C" uint64_t rr_amiga_native_count(const RrAmigaSession *s) { return s->native_count; }
extern "C" uint64_t rr_amiga_interpreted_count(const RrAmigaSession *s) { return s->interpreted_count; }
extern "C" long rr_amiga_resload_calls(const RrAmigaSession *s) { return s->calls; }
extern "C" int rr_amiga_write_resload_log(const RrAmigaSession *s, const char *path) {
    FILE *o = open_file(path, "wb");
    if (!o) return 0;
    fwrite(s->log.data(), 1, s->log.size(), o);
    return fclose(o) == 0;
}

// ---- quick states ----------------------------------------------------------------------------------------------------
// magic, ABI string, frame, resload state (its host callbacks are this process's), inputs held, then vAmiga's snapshot.
struct StateHead { char magic[16]; char abi[72]; uint64_t frame; uint32_t joy, mouse_left, mouse_right, snapshot_size; };

extern "C" int rr_amiga_state_save(RrAmigaSession *s, const char *path, const char *abi) {
    try {
        // vAmiga saves an ordinary machine: the WOM over ExpMem is lifted around the snapshot (its reader reallocates
        // ROM and WOM buffers by the sizes it was configured with, which an alias is not), then set again. The image and
        // what was patched into it are in slow RAM, which the snapshot keeps.
        kick_window(false);
        std::unique_ptr<Snapshot> snap;
        try { snap = s->amiga->takeSnapshot(utl::Compressor::NONE); } catch (...) { kick_window(true); throw; }
        kick_window(true);
        StateHead head{};
        memcpy(head.magic, STATE_MAGIC, sizeof head.magic);
        snprintf(head.abi, sizeof head.abi, "%s", abi ? abi : "");
        head.frame = s->frame; head.joy = s->joy; head.mouse_left = (uint32_t)s->mouse_left; head.mouse_right = (uint32_t)s->mouse_right;
        head.snapshot_size = (uint32_t)snap->data.size;
        std::string temporary = std::string(path) + ".tmp";
        FILE *f = open_file(temporary.c_str(), "wb");
        if (!f) return 4;
        bool ok = fwrite(&head, sizeof head, 1, f) == 1 && fwrite(&s->rl, sizeof s->rl, 1, f) == 1 &&
                  fwrite(s->keys, sizeof s->keys, 1, f) == 1 && fwrite(snap->data.ptr, 1, (size_t)snap->data.size, f) == (size_t)snap->data.size;
        ok = fclose(f) == 0 && ok;
        std::error_code ec;
        if (ok) fs::rename(upath(temporary), upath(path), ec);
        if (!ok || ec) { fs::remove(upath(temporary), ec); return 4; }
        return 0;
    } catch (std::exception &) {
        return 4;
    }
}

extern "C" int rr_amiga_state_load(RrAmigaSession *s, const char *path, const char *abi) {
    FILE *f = open_file(path, "rb");
    if (!f) return 1;
    StateHead head{};
    RrResload rl{};
    uint8_t keys[128];
    std::vector<uint8_t> data;
    bool ok = fread(&head, sizeof head, 1, f) == 1;
    if (ok && (memcmp(head.magic, STATE_MAGIC, sizeof head.magic) || strncmp(head.abi, abi ? abi : "", sizeof head.abi))) { fclose(f); return 2; }
    ok = ok && fread(&rl, sizeof rl, 1, f) == 1 && fread(keys, sizeof keys, 1, f) == 1 && head.snapshot_size && head.snapshot_size < (256u << 20);
    if (ok) { data.resize(head.snapshot_size); ok = fread(data.data(), 1, data.size(), f) == data.size(); }
    fclose(f);
    if (!ok) return 3;
    kick_window(false);
    try {
        s->amiga->loadSnapshot(Snapshot(data.data(), (isize)data.size()));
    } catch (std::exception &) {
        kick_window(true);
        return 3;
    }
    rl.host = s->rl.host;
    s->rl = rl;
    // The Kickstart the saved timeline had loaded, wherever it came from (a header loads it before the slave, but
    // resload_LoadKick only when the slave calls it): its copy is in the restored slow RAM, so only the window is set again.
    if (s->rl.kick_loaded && s->rl.exp_mem >= SLOW_BASE && s->rl.kick_size == 0x40000 && s->kick.size() == s->rl.kick_size) {
        s->kick_base = s->rl.exp_mem;
        s->kick_size = s->rl.kick_size;
    }
    kick_window(true);
    s->frame = head.frame;
    // The inputs held when the state was saved: what the machine's ports hold now.
    s->joy = head.joy; s->mouse_left = (int)head.mouse_left; s->mouse_right = (int)head.mouse_right;
    memcpy(s->keys, keys, sizeof keys);
    set_breakpoints();
    update_hook();
    return 0;
}
