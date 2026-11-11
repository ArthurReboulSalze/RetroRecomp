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
//   R8  Our own bitplane plan (checkpoint 1b), for a steady line: no plan change in it or in the line before, lores or hires,
//       DDFSTRT before DDFSTOP, no more planes than the resolution fetches (6 lores, 4 hires). Fetching runs when the vertical window
//       is open and BPLEN and DMAEN are set at the line's start; it starts at DDFSTRT, not before $18 (ECS hardware start). The
//       fetch units are 8 colour clocks from the even clock at or before the start; inside a unit the planes are fetched at
//       positions 1:4 2:6 3:2 5:3 6:5 7:1 (lores) or 0:4 1:2 2:3 3:1 4:4 5:2 6:3 7:1 (hires) (HRM, DMA time slot allocation).
//   R9  The fetch stops at DDFSTOP or at $D8, whichever comes first (ECS hardware stop): the unit starting at the first unit
//       boundary at or after that clock is the last one, and its fetches add the modulo (lores: all; hires: its second half).
//   R10 The vertical window: off on the line that equals the stop line and on the frame's last line, on on the line that equals
//       the start line (comparators at the line's start); its state before the first line seen is taken from the reference once.
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
    uint8_t baseKind[LINE] = { };                // the refresh and disk, audio, sprite layer, under the bitplane plan
    int8_t baseOwner[LINE] = { };
};

struct Mismatch { uint64_t frame; isize v, h; int predicted, actual, kind; };

struct State {
    Line line;
    // Time and blocks: colour clocks while the Copper or the Blitter is running (the model steps them with the CPU) and the free
    // ones; the synchronisations met in free time, (a) every secondary event stopping the CPU, (b) Paula's audio, disk, pot and
    // serial events caught up instead (their interrupts still stop it through IRQ and IPL).
    Cycle lastClock = 0;
    bool lastJoint = false;
    uint64_t jointClocks = 0, freeClocks = 0, freeSyncsA = 0, freeSyncsB = 0, freeSyncsC = 0, regFixed = 0;
    uint64_t sec[SLOT_TER - SLOT_SEC + 1] = { };
    // Checkpoint 1b: our own plan of a steady line against the reference's plan at the line's start.
    bool bpv = false, bpvSeeded = false, previousChanged = true, carryIn = true, latch = false, latchKnown = false, bpvKnown = false;
    isize lastVstrt = -1, lastVstop = -1;
    uint64_t ddfCovered = 0, ddfEqual = 0, ddfWrong = 0, ddfNotCovered[6] = { };   // changed, resolution, planes, order, carried in, window edge
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
    uint64_t crossings[4] = { }, copEvents = 0, bltEvents = 0, regEvents = 0, dasEvents = 0, bplEvents = 0;
    uint64_t dasKind[7] = { };                  // refresh, disk, audio, sprite, sprite DMA update, CIA-B tick, line end
    uint64_t slotUse[3][2] = { };               // disk, audio, sprite conditional slots: used, unused
    Cycle horizon = 0, horizonAt = 0;
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

void setBase(isize h, Kind kind, BusOwner owner) {
    if (h < 0 || h >= LINE) return;
    s.line.baseKind[h] = kind;
    s.line.baseOwner[h] = int8_t(owner);
}

// The bitplane part of the plan, from clock `from` on (R5, R6).
void readPlan(Agnus &a, isize from) {
    // From `from` on: the refresh and DAS layer, then the bitplane plan over it (R5).
    for (isize h = from; h < LINE; h++) {
        s.line.kind[h] = s.line.baseKind[h];
        s.line.owner[h] = s.line.baseOwner[h];
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

bool joint(Agnus &a) {
    const Cycle soon = a.clock + DMA_CYCLES(4);
    return a.trigger[SLOT_COP] <= soon || a.trigger[SLOT_BLT] <= soon;
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
    s.horizonAt = a.clock;
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

int ownPlan(Agnus &a, uint8_t *k);

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
        s.lastClock = a.clock;
        s.jointClocks = s.freeClocks = 0;
        if (const char *f = getenv("RR_BUS_SHADOW_FAULT")) fault = atoi(f);
    }
    Line &line = s.line;
    line = Line{};
    line.valid = true;
    line.v = a.pos.v;
    line.count = a.pos.hCnt();
    // R2
    setBase(0x01, TAKEN, BusOwner::REFRESH);
    setBase(0x03, TAKEN, BusOwner::REFRESH);
    setBase(0x05, TAKEN, BusOwner::REFRESH);
    setBase((a.pos.lol && fault != 1) ? 0xE3 : 0xE2, TAKEN, BusOwner::REFRESH);
    // R3, R4
    u16 das = 0;
    if (a.dmacon & DMAEN) {
        das = a.dmacon & 0x3F;
        const isize first = a.isPAL() ? 25 : 19;
        if (fault != 5 && (a.pos.v < first || a.pos.v >= a.pos.vMax())) das &= 0x1F;
    }
    if (das & 0x10) for (isize h : {0x07, 0x09, 0x0B}) setBase(h, MAYBE, BusOwner::DISK);
    for (isize n = 0; n < 4; n++) setBase(0x0D + 2 * n + (fault == 2 ? 2 : 0), MAYBE, BusOwner(isize(BusOwner::AUD0) + n));
    if (das & 0x20) {
        for (isize n = 0; n < 8; n++) {
            setBase(0x15 + 4 * n, MAYBE, BusOwner(isize(BusOwner::SPRITE0) + n));
            setBase(0x17 + 4 * n, MAYBE, BusOwner(isize(BusOwner::SPRITE0) + n));
        }
    }
    // The same slots as the reference's own table of the line (the classes of its DAS events).
    for (isize h = 0; h < HPOS_CNT; h++) {
        const EventID e = a.sequencer.dasEvent[h];
        int expect = -1;
        if (e >= DAS_D0 && e <= DAS_D0 + 2) expect = int(BusOwner::DISK);
        else if (e >= DAS_A0 && e <= DAS_A0 + 3) expect = int(BusOwner::AUD0) + int(e - DAS_A0);
        else if (e >= DAS_S0_1 && e <= DAS_S7_2) expect = int(BusOwner::SPRITE0) + int(e - DAS_S0_1) / 2;
        const bool mine = line.baseKind[h] == MAYBE;
        if ((expect >= 0) != mine || (mine && line.baseOwner[h] != expect)) {
            s.dasTable++;
            note(4, h, mine ? line.baseOwner[h] : -1, expect);
        }
    }
    readPlan(a, 0);
    s.lines++;
    // Checkpoint 1b: our own plan of the line against the reference's, both from the line's start state.
    uint8_t mine[LINE];
    const int reason = ownPlan(a, mine);
    if (reason) s.ddfNotCovered[reason - 1]++;
    else {
        s.ddfCovered++;
        bool equal = true;
        for (isize h = 0; h < LINE && h < HPOS_CNT; h++) {
            const int theirs = int(a.sequencer.bplEvent[h]) >> 2;
            if (theirs != mine[h]) {
                if (equal) note(8, h, mine[h], theirs);
                if (equal && getenv("RR_BUS_DDF_DEBUG") && s.ddfWrong < 6) {
                    fprintf(stderr, "ddf v=%ld strt=%x stop=%x con0=%04x dmacon=%04x bpv=%d lol=%d count=%ld vstrt=%ld vstop=%ld\n", (long)a.pos.v,
                            a.sequencer.ddfstrt, a.sequencer.ddfstop, a.bplcon0Initial, a.dmaconInitial, s.bpv, a.pos.lol, (long)s.line.count,
                            (long)a.sequencer.vstrt, (long)a.sequencer.vstop);
                    fprintf(stderr, "  mine:");
                    for (isize x = 0; x < HPOS_CNT; x++) if (mine[x]) fprintf(stderr, " %lx:%d", (long)x, mine[x]);
                    fprintf(stderr, "\n  theirs:");
                    for (isize x = 0; x < HPOS_CNT; x++) if (int(a.sequencer.bplEvent[x]) >> 2) fprintf(stderr, " %lx:%d", (long)x, int(a.sequencer.bplEvent[x]) >> 2);
                    fprintf(stderr, "\n");
                }
                equal = false;
            }
        }
        (equal ? s.ddfEqual : s.ddfWrong)++;
    }
}

// R8-R10: our own bitplane plan of a steady line, k = the reference's event code >> 2 (0: no fetch). Returns the reason it does not
// cover the line (0: covered).
int ownPlan(Agnus &a, uint8_t *k) {
    for (isize h = 0; h < LINE; h++) k[h] = 0;
    const isize v = a.pos.v;
    const bool before = s.bpv;
    // After a change inside a line (a DIW write may close or open the window at once) the window is unknown until a comparator
    // matches again.
    if (a.sequencer.vstrt != s.lastVstrt || a.sequencer.vstop != s.lastVstop) {
        if (s.bpvSeeded) s.bpvKnown = false;                       // a DIW write: the window may have changed at once
        s.lastVstrt = a.sequencer.vstrt;
        s.lastVstop = a.sequencer.vstop;
    }
    if (!s.bpvSeeded) { s.bpv = a.sequencer.ddfInitial.bpv; s.bpvSeeded = s.bpvKnown = true; }
    else if (v == a.sequencer.vstop || v == (a.isPAL() ? 312 : 262)) { s.bpv = false; s.bpvKnown = true; }
    else if (v == a.sequencer.vstrt) { s.bpv = true; s.bpvKnown = true; }
    const bool edge = before != s.bpv;
    // R9b: the start latch (set when the beam reaches DDFSTRT, cleared when it reaches DDFSTOP; a position past the line's last
    // colour clock is never reached; the reference processes up to $E4) carries into the next line, whose fetch then starts at $18.
    const bool latched = s.latch, latchKnown = s.latchKnown;
    {
        const isize strt = a.sequencer.ddfstrt, stop = a.sequencer.ddfstop, end = 0xE5;   // the reference processes positions up to $E4
        const bool sets = strt < end, clears = stop < end;
        if (sets && clears) s.latch = strt > stop;
        else if (sets) s.latch = true;
        else if (clears) s.latch = false;
        if (sets || clears) s.latchKnown = true;
    }
    // A line after one this plan did not cover, or whose last unit ran past its end, may start with the fetch state the line before
    // left (the start latch of a window opened after its stop, a unit cut by the line's end): not covered yet. The line's own end
    // state is still computed from its registers, so coverage resumes on the line after.
    const bool carried = s.carryIn;
    const auto plan = [&]() -> int {
        s.carryIn = true;
        const u16 con0 = a.bplcon0Initial;
        if (con0 & 0x0040) return 2;                               // super-hires
        const bool hires = con0 & 0x8000;
        const isize planes = (con0 >> 12) & 7;
        if (planes > (hires ? 4 : 6)) return 3;
        const isize strt = a.sequencer.ddfstrt, stop = a.sequencer.ddfstop;
        if (strt >= stop) return 4;
        const bool run = s.bpv && (a.dmaconInitial & DMAEN) && (a.dmaconInitial & BPLEN);
        if (!run || planes == 0) { s.carryIn = false; return 0; }
        static const int8_t LORES[8] = {0, 4, 6, 2, 0, 3, 5, 1}, HIRES[8] = {4, 2, 3, 1, 4, 2, 3, 1};
        const isize start = (latched || strt < 0x18) ? 0x18 : strt;
        const isize request = stop < 0xD8 ? stop : 0xD8;
        if (request < start) return 4;
        const isize first = start & ~isize(1);
        isize last = first;
        while (last < request) last += 8;                          // the first unit boundary at or after the stop request
        if (RrBus::fault == 9) last -= 8;
        s.carryIn = last + 8 > s.line.count;
        for (isize unit = first; unit <= last; unit += 8) {
            for (isize c = 0; c < 8; c++) {
                const isize h = unit + c;
                if (h < start || h >= LINE) continue;
                const int plane = hires ? HIRES[c] : LORES[c];
                if (!plane || plane > planes) continue;
                const bool mod = unit == last && (!hires || c >= 4);
                k[h] = uint8_t(1 + (hires ? 16 : 0) + 2 * (plane - 1) + (mod ? 1 : 0));
            }
        }
        return 0;
    };
    const int reason = plan();
    if (getenv("RR_BUS_DDF_TRACE")) fprintf(stderr, "line %ld reason %d carried %d latchKnown %d latch %d bpv %d/%d changed %d carryOut %d\n", (long)v, reason,
                                            carried, latchKnown, latched, s.bpv, s.bpvKnown, s.previousChanged, s.carryIn);
    // A line whose start latch or window is not known passes an unknown state on (its units may be aligned otherwise). A tail
    // carried in from the line before ends before $18 and does not change the line's own units.
    if (s.previousChanged || !latchKnown || !s.bpvKnown) s.carryIn = true;
    if (s.previousChanged) return 1;
    if (carried || !latchKnown || !s.bpvKnown) return 5;
    if (edge) return 6;
    return reason;
}

void RrBus::dasChanged(Agnus &a) {
    // Only a change of this line: at its end the beam has moved on before the next line's table is built.
    if (!s.line.valid || a.pos.v != s.line.v || fault == 4) return;
    if (!s.line.changed) s.linesChanged++;
    s.line.changed = true;
    const u16 das = (a.dmacon & DMAEN) ? (a.dmacon & 0x3F) : 0;
    const isize from = a.pos.h + 2;
    for (isize h = from; h < 0x38 && h < LINE; h++) {
        const int8_t o = s.line.baseOwner[h];
        if (s.line.baseKind[h] == MAYBE && (o == int8_t(BusOwner::DISK) || (o >= int8_t(BusOwner::SPRITE0) && o <= int8_t(BusOwner::SPRITE7)))) {
            s.line.baseKind[h] = FREE;
            s.line.baseOwner[h] = 0;
        }
    }
    auto maybe = [&](isize h, BusOwner owner) { if (h >= from) setBase(h, MAYBE, owner); };
    if (das & 0x10) for (isize h : {0x07, 0x09, 0x0B}) maybe(h, BusOwner::DISK);
    if (das & 0x20) {
        for (isize n = 0; n < 8; n++) {
            maybe(0x15 + 4 * n, BusOwner(isize(BusOwner::SPRITE0) + n));
            maybe(0x17 + 4 * n, BusOwner(isize(BusOwner::SPRITE0) + n));
        }
    }
    if (from < LINE) readPlan(a, from);
}

void RrBus::planChanged(Agnus &a) {
    // Only a change of this line (a change applied at its colour clock 0, after the line's start, included).
    if (!s.line.valid || a.pos.v != s.line.v || fault == 4) return;
    if (!s.line.changed) s.linesChanged++;
    s.line.changed = true;
    readPlan(a, a.pos.h);
}

void RrBus::lineEnd(Agnus &a) {
    uint64_t hash = frameOwners;
    for (isize h = 0; h < HPOS_CNT; h++) { hash ^= uint8_t(a.busOwner[h]); hash *= 1099511628211ull; }
    frameOwners = hash;
    s.syncs[SYNC_LINE_POINTS] += 3;
    if (!joint(a)) { s.freeSyncsA += 3; s.freeSyncsB += 3; }
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
                const int o = line.owner[h];
                const int cls = o == int(BusOwner::DISK) ? 0 : (o >= int(BusOwner::AUD0) && o <= int(BusOwner::AUD3)) ? 1 : 2;
                s.slotUse[cls][actual == o ? 0 : 1]++;
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
    s.previousChanged = s.line.changed || !s.line.valid;
    if (s.previousChanged) s.latchKnown = false;      // a change inside the line may have moved the start latch
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
    if ((k == ACC_CUSTOM || k == ACC_CIA) && !joint(a)) { s.freeSyncsA++; s.freeSyncsB++; s.freeSyncsC++; }
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
    const bool now = joint(a);
    (s.lastJoint ? s.jointClocks : s.freeClocks) += (uint64_t)AS_DMA_CYCLES(cycle - s.lastClock);
    s.lastClock = cycle;
    s.lastJoint = now;
    bool sync = false;
    if (a.isDue<SLOT_REG>(cycle)) {
        s.regEvents++;
        s.reg = true;
        // A change scheduled by a DMA slot run in the block (a sprite fetch writes SPRxPOS and SPRxCTL) is the catch-up's own.
        if (a.trigger[SLOT_REG] < s.horizon) {
            s.crossings[s.device ? 0 : s.das ? 2 : 3]++;
            if (!s.device && !s.das) note(7, a.pos.h, int(SLOT_REG), int(AS_DMA_CYCLES(a.trigger[SLOT_REG] - s.horizonAt)));
        }
        // HSYNC at $12 and the line's end are the line's fixed points (counted there); other changes are syncs of their own.
        if (a.pos.h == 0x12 || a.pos.h >= a.pos.hCnt()) s.regFixed++;
        else {
            s.syncs[SYNC_REG_EVENT]++;
            if (!now) { s.freeSyncsA++; s.freeSyncsB++; s.freeSyncsC++; }
        }
        sync = true;
    }
    if (a.isDue<SLOT_DAS>(cycle)) {
        s.dasEvents++;
        s.das = true;
        const EventID e = a.id[SLOT_DAS];
        s.dasKind[e == DAS_REFRESH ? 0 : (e >= DAS_D0 && e <= DAS_D0 + 2) ? 1 : (e >= DAS_A0 && e <= DAS_A0 + 3) ? 2 :
                  (e >= DAS_S0_1 && e <= DAS_S7_2) ? 3 : e == DAS_SDMA ? 4 : e == DAS_TICK ? 5 : 6]++;
    }
    if (a.isDue<SLOT_BPL>(cycle)) s.bplEvents++;
    if (a.isDue<SLOT_COP>(cycle)) { s.copEvents++; s.device = true; }
    if (a.isDue<SLOT_BLT>(cycle)) { s.bltEvents++; s.device = true; }
    for (EventSlot slot : {SLOT_CIAA, SLOT_CIAB, SLOT_SEC}) {
        if (cycle >= a.trigger[slot]) {
            // An event earlier than the horizon taken at the last synchronisation was scheduled inside the block: by the Copper or
            // the Blitter (stepped with the CPU in the model) or by something else (a DMA device caught up late would miss it).
            if (a.trigger[slot] < s.horizon) {
                s.crossings[s.device ? 0 : s.reg ? 1 : s.das ? 2 : 3]++;
                if (!s.device && (s.reg || s.das)) note(6, a.pos.h, s.reg ? 1 : 2, int(slot));
                if (!s.device && !s.reg && !s.das) {
                    // Unexplained: which slot (a secondary one by its own number), and how long after the horizon was taken.
                    long which = slot;
                    if (slot == SLOT_SEC) for (long k = SLOT_CH0; k <= SLOT_TER; k++) if (cycle >= a.trigger[k]) { which = k; break; }
                    note(7, a.pos.h, int(which), int(AS_DMA_CYCLES(a.trigger[slot] - s.horizonAt)));
                }
            }
            s.syncs[slot == SLOT_SEC ? SYNC_SEC_EVENT : SYNC_CIA_EVENT]++;
            if (!now) s.freeSyncsA++;
            if (slot == SLOT_SEC) {
                bool cpuVisible = false;
                for (long k = SLOT_CH0; k <= SLOT_TER; k++) {
                    if (cycle >= a.trigger[k]) {
                        s.sec[k - SLOT_SEC]++;
                        if (!(k >= SLOT_CH0 && k <= SLOT_DSK) && k != SLOT_POT && k != SLOT_TXD && k != SLOT_RXD) cpuVisible = true;
                    }
                }
                if (cpuVisible && !now) { s.freeSyncsB++; s.freeSyncsC++; }
            } else if (!now) s.freeSyncsB++;
            sync = true;
        }
    }
    // What this colour clock's events schedule is known after them: the horizon is taken again at the next hook.
    if (sync || cycle >= s.horizon) s.recompute = true;
}

uint64_t RrBus::mismatches() {
    return s.takenWrong + s.maybeWrong + s.freeWrong + s.dasTable + s.waitWrong + s.ddfWrong;
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
    put("],\"time\":{\"joint_clocks\":%llu,\"free_clocks\":%llu,\"free_syncs_all_secondary\":%llu,\"free_syncs_paula_caught_up\":%llu,\"free_syncs_cpu_visible\":%llu,\"register_fixed\":%llu}",
        (unsigned long long)s.jointClocks, (unsigned long long)s.freeClocks, (unsigned long long)s.freeSyncsA, (unsigned long long)s.freeSyncsB, (unsigned long long)s.freeSyncsC,
        (unsigned long long)s.regFixed);
    put(",\"das\":{\"refresh\":%llu,\"disk\":%llu,\"audio\":%llu,\"sprite\":%llu,\"sprite_update\":%llu,\"tick\":%llu,\"line_end\":%llu,\"bpl_events\":%llu,"
        "\"disk_slots\":[%llu,%llu],\"audio_slots\":[%llu,%llu],\"sprite_slots\":[%llu,%llu]},\"secondary\":{",
        (unsigned long long)s.dasKind[0], (unsigned long long)s.dasKind[1], (unsigned long long)s.dasKind[2], (unsigned long long)s.dasKind[3],
        (unsigned long long)s.dasKind[4], (unsigned long long)s.dasKind[5], (unsigned long long)s.dasKind[6], (unsigned long long)s.bplEvents,
        (unsigned long long)s.slotUse[0][0], (unsigned long long)s.slotUse[0][1], (unsigned long long)s.slotUse[1][0], (unsigned long long)s.slotUse[1][1],
        (unsigned long long)s.slotUse[2][0], (unsigned long long)s.slotUse[2][1]);
    static const char *const SEC_NAMES[] = {"sec", "ch0", "ch1", "ch2", "ch3", "dsk", "vbl", "irq", "ipl", "kbd", "txd", "rxd", "pot", "tertiary"};
    for (long k = 1; k <= SLOT_TER - SLOT_SEC; k++) put(k > 1 ? ",\"%s\":%llu" : "\"%s\":%llu", SEC_NAMES[k], (unsigned long long)s.sec[k]);
    put("},\"own_plan\":{\"covered\":%llu,\"equal\":%llu,\"different\":%llu,\"not_covered\":{\"changed\":%llu,\"super_hires\":%llu,\"planes\":%llu,\"window_order\":%llu,\"carried_in\":%llu,\"window_edge\":%llu}}}",
        (unsigned long long)s.ddfCovered, (unsigned long long)s.ddfEqual, (unsigned long long)s.ddfWrong, (unsigned long long)s.ddfNotCovered[0],
        (unsigned long long)s.ddfNotCovered[1], (unsigned long long)s.ddfNotCovered[2], (unsigned long long)s.ddfNotCovered[3],
        (unsigned long long)s.ddfNotCovered[4], (unsigned long long)s.ddfNotCovered[5]);
#undef put
    return n < size ? n : size - 1;
}

}
