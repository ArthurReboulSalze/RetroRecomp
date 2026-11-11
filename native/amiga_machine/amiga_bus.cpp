// The bus and DMA model of the Amiga's stage 7, in shadow (MIT, ours): see amiga_bus.h.
//
// The rules of the table, in our own words, with where each comes from (the behaviour sheet of the stage 7 plan):
//   R1  A line has 227 colour clocks, 228 on an NTSC long line (the beam's hCnt).
//   R2  Refresh takes $01, $03, $05 and $E2, $E3 instead of $E2 on a long line (Hardware Reference Manual, fixed DMA slots; the
//       long-line position as vAmiga's reference behaves).
//   R3  Disk DMA may take $07, $09, $0B; audio channel n may take $0D + 2n; sprite n may take $15 + 4n and $17 + 4n (HRM fixed
//       slots). Each is conditional: the device decides at the slot (the disk's state, Paula's request, the sprite's state).
//   R4  Which of them exist on a line is fixed at the line's start from DMACON: DMAEN and the device's own enable bit; sprite slots
//       only from line 25 (PAL) or 19 (NTSC) to the frame's last line (the reference's sprite DMA area). The four audio slots exist on
//       every line whatever DMACON says: a channel's request decides (the reference: "audio DMA is possible even in lines where the
//       DMACON bits are false").
//   R5  A bitplane fetch owns its slot whatever else wanted it (a sprite slot under an early fetch is the bitplane's; so are the
//       refresh slots $03, $05 and $E2/$E3, which the reference marks all at $01), except $01 itself, recorded as refresh (the
//       reference runs the refresh after the fetch of that colour clock). The plan's entry past the line's last colour clock runs
//       only on a long line.
//   R4b A DMACON write inside the line that changes the disk or sprite enable changes their slots from two colour clocks after it
//       to $37, without the sprite-area test (the reference's behaviour).
//   R6  The bitplane plan is read from the reference's own plan at the line's start, and again from the clock of any change of it
//       inside the line; the part of the line before the change is history.
//   R7  The CPU waits while its colour clock is owned, one clock at a time; the reference charges no finer alignment (Agnus.cpp,
//       executeUntilBusIsFree). A wait is predictable from the table alone when no Copper, Blitter or register-change event can run
//       inside it and it meets no conditional slot and no line end.
#include "vaconfig.h"
#include "Agnus.h"
#include "amiga_bus.h"

#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace vamiga {

namespace {

enum Kind : uint8_t { FREE = 0, TAKEN = 1, MAYBE = 2 };
enum Path { FAST, STATIC, JOINT, SLOW_MAYBE, SLOW_EOL, SLOW_EVENT, SLOW_LINE, PATHS };
const char *const PATH_NAMES[PATHS] = {"fast", "static", "joint", "slow_maybe", "slow_eol", "slow_event", "slow_line"};
enum Sync { SYNC_CUSTOM, SYNC_CIA, SYNC_CIA_EVENT, SYNC_SEC_EVENT, SYNC_REG_EVENT, SYNC_LINE_POINTS, SYNCS };
const char *const SYNC_NAMES[SYNCS] = {"cpu_custom", "cpu_cia", "cia_events", "secondary_events", "register_events", "line_points"};
enum Access { ACC_CHIP, ACC_SLOW, ACC_FAST, ACC_CUSTOM, ACC_CIA, ACC_ROM, ACC_OTHER, ACCESSES };
const char *const ACCESS_NAMES[ACCESSES] = {"chip", "slow", "fast", "custom", "cia", "rom", "other"};

constexpr uint64_t BASIS = 1469598103934665603ull;
constexpr int LINE = 232;                       // at least HPOS_CNT

struct Line {
    bool valid = false;
    bool changed = false;
    isize v = 0, count = 227;
    uint8_t kind[LINE] = { };
    int8_t owner[LINE] = { };                    // the BusOwner of a certain or conditional slot
};

struct Mismatch { uint64_t frame; isize v, h; int predicted, actual, kind; };

struct State {
    Line line;
    uint64_t frames = 0, lines = 0, linesChanged = 0, linesCompared = 0;
    uint64_t taken = 0, takenWrong = 0, maybeUsed = 0, maybeUnused = 0, maybeWrong = 0, freeWrong = 0, dasTable = 0;
    uint64_t owners[int(BusOwner::COUNT)] = { };
    uint64_t spriteLines = 0;
    Mismatch first[16] = { };
    int firstCount = 0;
    // CPU side
    uint64_t access[ACCESSES] = { };
    uint64_t path[PATHS] = { }, pathDelay[PATHS] = { }, waitWrong = 0;
    Path pending = SLOW_LINE;
    long long predicted = 0;
    uint64_t syncs[SYNCS] = { };
    uint64_t crossings[4] = { }, copEvents = 0, bltEvents = 0, regEvents = 0, dasEvents = 0;
    Cycle horizon = 0;
    bool recompute = false;                     // the horizon is taken again at the next hook
    bool syncing = false;                       // a CPU access to a custom register or a CIA is under way: the horizon after it
    bool device = false;                        // the Copper or the Blitter ran since the horizon was taken
    bool reg = false, das = false;              // a register-change event, a disk/audio/sprite slot event ran since then
    Cycle frameClock = 0, clocks = 0;
    bool started = false;
    const char *out = nullptr;
};

State s;

bool isDma(int owner) { return owner >= int(BusOwner::REFRESH) && owner <= int(BusOwner::SPRITE7); }

void note(int kind, isize h, int predicted, int actual) {
    // The first few of each kind.
    int same = 0;
    for (int i = 0; i < s.firstCount; i++) same += s.first[i].kind == kind;
    if (same < 3 && s.firstCount < 16) s.first[s.firstCount++] = Mismatch{s.frames, s.line.v, h, predicted, actual, kind};
}

void set(isize h, Kind kind, BusOwner owner) {
    if (h < 0 || h >= LINE) return;
    s.line.kind[h] = kind;
    s.line.owner[h] = int8_t(owner);
}

// The bitplane part of the plan, from clock `from` on (R5, R6).
void readPlan(Agnus &a, isize from) {
    for (isize h = from; h < LINE && h < HPOS_CNT; h++) {
        if (s.line.kind[h] == TAKEN && s.line.owner[h] >= int8_t(BusOwner::BPL1) && s.line.owner[h] <= int8_t(BusOwner::BPL8)) {
            s.line.kind[h] = FREE;
            s.line.owner[h] = 0;
        }
    }
    // A refresh slot a fetch had covered is the refresh's again until the new plan covers it (R2, R5).
    for (isize h : {isize(0x03), isize(0x05), isize(s.line.count == 228 && RrBus::fault != 1 ? 0xE3 : 0xE2)}) {
        if (h >= from && s.line.kind[h] == FREE) set(h, TAKEN, BusOwner::REFRESH);
    }
    for (isize h = from; h < s.line.count && h < HPOS_CNT; h++) {
        const isize k = isize(a.sequencer.bplEvent[h]) >> 2;
        if (!k) continue;
        // R5: at $01 a fetch is recorded as refresh (the refresh of all four slots runs there, after the fetch of that clock).
        if (h == 0x01) continue;
        isize plane = ((k - 1) & 15) >> 1;
        if (RrBus::fault == 3) plane ^= 1;
        set(h, TAKEN, BusOwner(isize(BusOwner::BPL1) + plane));
    }
}

void horizonFrom(Agnus &a) {
    Cycle h = a.trigger[SLOT_CIAA];
    if (a.trigger[SLOT_CIAB] < h) h = a.trigger[SLOT_CIAB];
    if (RrBus::fault != 8 && a.trigger[SLOT_SEC] < h) h = a.trigger[SLOT_SEC];
    // A register change still to apply (INTENA, INTREQ, DMACON, the display's): the model keeps the pending list and stops there.
    if (a.trigger[SLOT_REG] < h) h = a.trigger[SLOT_REG];
    // The fixed points of the line: HSYNC at $12 (Denise's pass of the line before), the CIA-B tick at $66, the line's end.
    const isize at = a.pos.h <= 0x12 ? 0x12 : a.pos.h <= 0x66 ? 0x66 : a.pos.hCnt();   // a point of this very clock is still to come
    const Cycle fixed = a.clock + DMA_CYCLES(at - a.pos.h);
    s.horizon = fixed < h ? fixed : h;
    s.recompute = false;
    s.device = s.reg = s.das = false;
}

#if defined(__GNUC__) || defined(__clang__)
__attribute__((format(printf, 4, 5)))
#endif
void append(char *out, size_t size, size_t &n, const char *format, ...) {
    if (n >= size) return;
    va_list list;
    va_start(list, format);
    const int wrote = vsnprintf(out + n, size - n, format, list);
    va_end(list);
    if (wrote > 0) n += (size_t)wrote;
}

void dump() {
    if (!s.out) return;
    char text[8192];
    const size_t n = RrBus::json(text, sizeof text);
    if (FILE *f = fopen(s.out, "wb")) {
        fwrite(text, 1, n, f);
        fclose(f);
    }
}

}

int RrBus::fault = 0;
uint64_t RrBus::step = 0;
uint64_t RrBus::traceFrom = ~0ull;
uint64_t RrBus::traceCount = 0;
uint64_t RrBus::frameOwners = BASIS;

void RrBus::reset(Agnus &) {
    s.line.valid = false;
}

void RrBus::lineStart(Agnus &a) {
    if (!s.started) {
        s.started = true;
        s.out = getenv("RR_BUS_SHADOW_OUT");
        s.frameClock = a.clock;
        if (const char *f = getenv("RR_BUS_SHADOW_FAULT")) fault = atoi(f);
    }
    Line &line = s.line;
    line = Line{};
    line.valid = true;
    line.v = a.pos.v;
    line.count = a.pos.hCnt();
    // R2
    set(0x01, TAKEN, BusOwner::REFRESH);
    set(0x03, TAKEN, BusOwner::REFRESH);
    set(0x05, TAKEN, BusOwner::REFRESH);
    set((a.pos.lol && fault != 1) ? 0xE3 : 0xE2, TAKEN, BusOwner::REFRESH);
    // R3, R4
    u16 das = 0;
    if (a.dmacon & DMAEN) {
        das = a.dmacon & 0x3F;
        const isize first = a.isPAL() ? 25 : 19;
        if (fault != 5 && (a.pos.v < first || a.pos.v >= a.pos.vMax())) das &= 0x1F;
    }
    if (das & 0x10) for (isize h : {0x07, 0x09, 0x0B}) set(h, MAYBE, BusOwner::DISK);
    for (isize n = 0; n < 4; n++) set(0x0D + 2 * n + (fault == 2 ? 2 : 0), MAYBE, BusOwner(isize(BusOwner::AUD0) + n));
    if (das & 0x20) {
        for (isize n = 0; n < 8; n++) {
            set(0x15 + 4 * n, MAYBE, BusOwner(isize(BusOwner::SPRITE0) + n));
            set(0x17 + 4 * n, MAYBE, BusOwner(isize(BusOwner::SPRITE0) + n));
        }
    }
    // The same slots as the reference's own table of the line (the classes of its DAS events).
    for (isize h = 0; h < HPOS_CNT; h++) {
        const EventID e = a.sequencer.dasEvent[h];
        int expect = -1;
        if (e >= DAS_D0 && e <= DAS_D0 + 2) expect = int(BusOwner::DISK);
        else if (e >= DAS_A0 && e <= DAS_A0 + 3) expect = int(BusOwner::AUD0) + int(e - DAS_A0);
        else if (e >= DAS_S0_1 && e <= DAS_S7_2) expect = int(BusOwner::SPRITE0) + int(e - DAS_S0_1) / 2;
        const bool mine = line.kind[h] == MAYBE;
        if ((expect >= 0) != mine || (mine && line.owner[h] != expect)) {
            s.dasTable++;
            note(4, h, mine ? line.owner[h] : -1, expect);
        }
    }
    readPlan(a, 0);
    s.lines++;
}

void RrBus::dasChanged(Agnus &a) {
    if (!s.line.valid || fault == 4) return;
    if (!s.line.changed) s.linesChanged++;
    s.line.changed = true;
    const u16 das = (a.dmacon & DMAEN) ? (a.dmacon & 0x3F) : 0;
    for (isize h = a.pos.h + 2; h < 0x38 && h < LINE; h++) {
        if (s.line.kind[h] == MAYBE && (s.line.owner[h] == int8_t(BusOwner::DISK) ||
            (s.line.owner[h] >= int8_t(BusOwner::SPRITE0) && s.line.owner[h] <= int8_t(BusOwner::SPRITE7)))) {
            s.line.kind[h] = FREE;
            s.line.owner[h] = 0;
        }
    }
    auto maybe = [&](isize h, BusOwner owner) {
        if (h >= a.pos.h + 2 && h < LINE && s.line.kind[h] == FREE) set(h, MAYBE, owner);
    };
    if (das & 0x10) for (isize h : {0x07, 0x09, 0x0B}) maybe(h, BusOwner::DISK);
    if (das & 0x20) {
        for (isize n = 0; n < 8; n++) {
            maybe(0x15 + 4 * n, BusOwner(isize(BusOwner::SPRITE0) + n));
            maybe(0x17 + 4 * n, BusOwner(isize(BusOwner::SPRITE0) + n));
        }
    }
}

void RrBus::planChanged(Agnus &a) {
    if (!s.line.valid || a.pos.h == 0 || fault == 4) return;
    if (!s.line.changed) s.linesChanged++;
    s.line.changed = true;
    readPlan(a, a.pos.h);
}

void RrBus::lineEnd(Agnus &a) {
    uint64_t hash = frameOwners;
    for (isize h = 0; h < HPOS_CNT; h++) { hash ^= uint8_t(a.busOwner[h]); hash *= 1099511628211ull; }
    frameOwners = hash;
    s.syncs[SYNC_LINE_POINTS] += 3;
    if (s.line.valid) {
        Line &line = s.line;
        s.linesCompared++;
        bool sprite = false;
        for (isize h = 0; h < HPOS_CNT; h++) {
            const int actual = int(a.busOwner[h]);
            s.owners[actual]++;
            if (actual >= int(BusOwner::SPRITE0) && actual <= int(BusOwner::SPRITE7)) sprite = true;
            const Kind kind = (fault == 6 && line.kind[h] == MAYBE) ? FREE : Kind(line.kind[h]);
            if (kind == TAKEN) {
                s.taken++;
                if (actual != line.owner[h]) { s.takenWrong++; note(1, h, line.owner[h], actual); }
            } else if (kind == MAYBE) {
                if (actual == line.owner[h]) s.maybeUsed++;
                else if (isDma(actual)) { s.maybeWrong++; note(2, h, line.owner[h], actual); }
                else s.maybeUnused++;
            } else if (isDma(actual)) {
                s.freeWrong++;
                note(3, h, -1, actual);
            }
        }
        s.spriteLines += sprite;
    }
    s.line.valid = false;
    if (a.pos.v == 0) {          // the beam has moved on: the line that ended was the frame's last
        s.frames++;
        s.clocks += a.clock - s.frameClock;
        s.frameClock = a.clock;
        if (s.out && s.frames % 50 == 0) dump();
    }
}

void RrBus::cpuAccess(Agnus &a, uint32_t addr, int) {
    Access k = ACC_OTHER;
    switch (a.mem.cpuMemSrc[(addr >> 16) & 0xFF]) {
        case MemSrc::CHIP: case MemSrc::CHIP_MIRROR: k = ACC_CHIP; break;
        case MemSrc::SLOW: case MemSrc::SLOW_MIRROR: k = ACC_SLOW; break;
        case MemSrc::FAST: k = ACC_FAST; break;
        case MemSrc::CUSTOM: case MemSrc::CUSTOM_MIRROR: k = ACC_CUSTOM; break;
        case MemSrc::CIA: case MemSrc::CIA_MIRROR: k = ACC_CIA; break;
        case MemSrc::ROM: case MemSrc::ROM_MIRROR: case MemSrc::WOM: case MemSrc::EXT: k = ACC_ROM; break;
        default: break;
    }
    if (s.recompute) horizonFrom(a);
    s.access[k]++;
    // A custom register or CIA access is a synchronisation of the model: what it schedules is known after it (cpuDone).
    if (k == ACC_CUSTOM) s.syncs[SYNC_CUSTOM]++;
    if (k == ACC_CUSTOM || k == ACC_CIA) s.syncing = true;
}

void RrBus::cpuDone(Agnus &a) {
    if (s.syncing) {
        s.syncing = false;
        horizonFrom(a);
    }
}

void RrBus::ciaWait(Agnus &) {
    s.syncs[SYNC_CIA]++;
}

void RrBus::busWaitStart(Agnus &a) {
    const isize h = a.pos.h;
    const Line &line = s.line;
    const Cycle soon = a.clock + DMA_CYCLES(4);
    if (!line.valid || h >= line.count) { s.pending = SLOW_LINE; return; }
    if (a.trigger[SLOT_COP] <= soon || a.trigger[SLOT_BLT] <= soon) { s.pending = JOINT; return; }
    // The slot of the access itself is settled: the devices of this colour clock have run (the model catches up to it).
    if (a.busOwner[h] == BusOwner::NONE) { s.pending = FAST; s.predicted = 0; return; }
    if (!(line.kind[h] == TAKEN || (line.kind[h] == MAYBE && int(a.busOwner[h]) == line.owner[h]))) { s.pending = JOINT; return; }
    isize to = h + 1;
    while (to < line.count && line.kind[to] == TAKEN) to++;
    if (to >= line.count) { s.pending = SLOW_EOL; return; }
    if (line.kind[to] == MAYBE) { s.pending = SLOW_MAYBE; return; }
    const long long wait = (long long)(to - h) + (fault == 7 ? 1 : 0);
    const Cycle end = a.clock + DMA_CYCLES(wait);
    if (a.trigger[SLOT_REG] <= end || a.trigger[SLOT_COP] <= end || a.trigger[SLOT_BLT] <= end) { s.pending = SLOW_EVENT; return; }
    s.pending = STATIC;
    s.predicted = wait;
}

void RrBus::busWaitEnd(Agnus &a, long long delay) {
    s.path[s.pending]++;
    s.pathDelay[s.pending] += (uint64_t)delay;
    if ((s.pending == FAST || s.pending == STATIC) && delay != s.predicted) {
        s.waitWrong++;
        note(5, a.pos.h, int(s.predicted), int(delay));
    }
    if (step - traceFrom < traceCount) {
        printf("access step %llu clock %lld v %ld h %ld path %s predicted %lld delay %lld\n", (unsigned long long)step, (long long)a.clock,
               (long)a.pos.v, (long)a.pos.h, PATH_NAMES[s.pending], s.pending == FAST || s.pending == STATIC ? s.predicted : -1LL, delay);
    }
    s.pending = SLOW_LINE;
}

void RrBus::events(Agnus &a, long long cycle) {
    if (s.recompute) horizonFrom(a);
    bool sync = false;
    if (a.isDue<SLOT_REG>(cycle)) {
        s.regEvents++;
        s.reg = true;
        // A change scheduled by a DMA slot run in the block (a sprite fetch writes SPRxPOS and SPRxCTL) is the catch-up's own.
        if (a.trigger[SLOT_REG] < s.horizon) {
            s.crossings[s.device ? 0 : s.das ? 2 : 3]++;
            if (!s.device && !s.das) note(6, a.pos.h, -2, int(SLOT_REG));
        }
        s.syncs[SYNC_REG_EVENT]++;
        sync = true;
    }
    if (a.isDue<SLOT_DAS>(cycle)) { s.dasEvents++; s.das = true; }
    if (a.isDue<SLOT_COP>(cycle)) { s.copEvents++; s.device = true; }
    if (a.isDue<SLOT_BLT>(cycle)) { s.bltEvents++; s.device = true; }
    for (EventSlot slot : {SLOT_CIAA, SLOT_CIAB, SLOT_SEC}) {
        if (cycle >= a.trigger[slot]) {
            // An event earlier than the horizon taken at the last synchronisation was scheduled inside the block: by the Copper or
            // the Blitter (stepped with the CPU in the model) or by something else (a DMA device caught up late would miss it).
            if (a.trigger[slot] < s.horizon) {
                s.crossings[s.device ? 0 : s.reg ? 1 : s.das ? 2 : 3]++;
                if (!s.device) note(6, a.pos.h, s.reg ? 1 : s.das ? 2 : 3, int(slot));
            }
            s.syncs[slot == SLOT_SEC ? SYNC_SEC_EVENT : SYNC_CIA_EVENT]++;
            sync = true;
        }
    }
    // What this colour clock's events schedule is known after them: the horizon is taken again at the next hook.
    if (sync || cycle >= s.horizon) s.recompute = true;
}

uint64_t RrBus::mismatches() {
    return s.takenWrong + s.maybeWrong + s.freeWrong + s.dasTable + s.waitWrong;
}

size_t RrBus::json(char *out, size_t size) {
    size_t n = 0;
#define put(...) append(out, size, n, __VA_ARGS__)
    put("{\"frames\":%llu,\"lines\":%llu,\"lines_compared\":%llu,\"lines_plan_changed\":%llu,\"sprite_lines\":%llu,",
        (unsigned long long)s.frames, (unsigned long long)s.lines, (unsigned long long)s.linesCompared, (unsigned long long)s.linesChanged,
        (unsigned long long)s.spriteLines);
    put("\"table\":{\"taken\":%llu,\"taken_wrong\":%llu,\"maybe_used\":%llu,\"maybe_unused\":%llu,\"maybe_wrong\":%llu,\"free_wrong\":%llu,\"das_table_wrong\":%llu},",
        (unsigned long long)s.taken, (unsigned long long)s.takenWrong, (unsigned long long)s.maybeUsed, (unsigned long long)s.maybeUnused,
        (unsigned long long)s.maybeWrong, (unsigned long long)s.freeWrong, (unsigned long long)s.dasTable);
    put("\"owners\":[");
    for (int i = 0; i < int(BusOwner::COUNT); i++) put(i ? ",%llu" : "%llu", (unsigned long long)s.owners[i]);
    put("],\"accesses\":{");
    for (int i = 0; i < ACCESSES; i++) put(i ? ",\"%s\":%llu" : "\"%s\":%llu", ACCESS_NAMES[i], (unsigned long long)s.access[i]);
    put("},\"waits\":{");
    for (int i = 0; i < PATHS; i++) put(i ? ",\"%s\":[%llu,%llu]" : "\"%s\":[%llu,%llu]", PATH_NAMES[i], (unsigned long long)s.path[i], (unsigned long long)s.pathDelay[i]);
    put("},\"wait_wrong\":%llu,\"syncs\":{", (unsigned long long)s.waitWrong);
    for (int i = 0; i < SYNCS; i++) put(i ? ",\"%s\":%llu" : "\"%s\":%llu", SYNC_NAMES[i], (unsigned long long)s.syncs[i]);
    put("},\"crossings\":{\"after_copper_or_blitter\":%llu,\"after_register_change\":%llu,\"after_das_slot\":%llu,\"other\":%llu},\"events\":{\"copper\":%llu,\"blitter\":%llu,\"register\":%llu},\"colour_clocks\":%lld,\"fault\":%d,\"first\":[",
        (unsigned long long)s.crossings[0], (unsigned long long)s.crossings[1], (unsigned long long)s.crossings[2], (unsigned long long)s.crossings[3], (unsigned long long)s.copEvents, (unsigned long long)s.bltEvents, (unsigned long long)s.regEvents,
        (long long)AS_DMA_CYCLES(s.clocks), fault);
    for (int i = 0; i < s.firstCount; i++) {
        const Mismatch &m = s.first[i];
        put(i ? ",[%llu,%ld,%ld,%d,%d,%d]" : "[%llu,%ld,%ld,%d,%d,%d]", (unsigned long long)m.frame, (long)m.v, (long)m.h, m.kind, m.predicted, m.actual);
    }
    put("]}");
#undef put
    return n < size ? n : size - 1;
}

}
