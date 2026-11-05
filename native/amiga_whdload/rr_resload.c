/* Retro-Recomp: resload services of a WHDLoad slave (MIT). See rr_resload.h. */
#include "rr_resload.h"
#include "rr_decrunch.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum {
    D0 = 0, D1, D2, D3, D4, D5, D6, D7, A0, A1, A2, A3, A4, A5, A6, A7
};

/* Entry offsets of the resload table (whdload.i, ResidentLoader). */
enum {
    RL_INSTALL = 0x00, RL_ABORT = 0x04, RL_LOADFILE = 0x08, RL_SAVEFILE = 0x0C, RL_SETCACR = 0x10, RL_LISTFILES = 0x14,
    RL_DECRUNCH = 0x18, RL_LOADFILEDECRUNCH = 0x1C, RL_FLUSHCACHE = 0x20, RL_GETFILESIZE = 0x24, RL_DISKLOAD = 0x28,
    RL_DISKLOADDEV = 0x2C, RL_CRC16 = 0x30, RL_CONTROL = 0x34, RL_SAVEFILEOFFSET = 0x38, RL_PROTECTREAD = 0x3C,
    RL_PROTECTREADWRITE = 0x40, RL_PROTECTWRITE = 0x44, RL_PROTECTREMOVE = 0x48, RL_LOADFILEOFFSET = 0x4C,
    RL_RELOCATE = 0x50, RL_DELAY = 0x54, RL_DELETEFILE = 0x58, RL_PROTECTSMC = 0x5C, RL_SETCPU = 0x60, RL_PATCH = 0x64,
    RL_LOADKICK = 0x68, RL_DELTA = 0x6C, RL_GETFILESIZEDEC = 0x70, RL_PATCHSEG = 0x74, RL_EXAMINE = 0x78,
    RL_EXNEXT = 0x7C, RL_GETCUSTOM = 0x80, RL_VSNPRINTF = 0x84, RL_LOG = 0x88, RL_READJOYPORT = 0x8C
};

static const char *const entry_names[RR_RESLOAD_ENTRIES] = {
    "Install", "Abort", "LoadFile", "SaveFile", "SetCACR", "ListFiles", "Decrunch", "LoadFileDecrunch", "FlushCache",
    "GetFileSize", "DiskLoad", "DiskLoadDev", "CRC16", "Control", "SaveFileOffset", "ProtectRead",
    "ProtectReadWrite", "ProtectWrite", "ProtectRemove", "LoadFileOffset", "Relocate", "Delay", "DeleteFile",
    "ProtectSMC", "SetCPU", "Patch", "LoadKick", "Delta", "GetFileSizeDec", "PatchSeg", "Examine", "ExNext",
    "GetCustom", "VSNPrintF", "Log", "ReadJoyPort"};

/* Minimum ws_Version of each entry (whdload.i). */
static const uint8_t entry_versions[RR_RESLOAD_ENTRIES] = {
    1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2, 3, 5, 5, 6, 6, 6, 6, 6, 8, 8, 8, 10, 10, 10, 11, 11, 11, 15, 15, 15, 15, 18,
    18, 19};

static uint8_t rd8(const RrResload *r, uint32_t a) { return r->host.read8(r->host.user, a & 0xFFFFFFu); }
static void wr8(RrResload *r, uint32_t a, uint8_t v) { r->host.write8(r->host.user, a & 0xFFFFFFu, v); }
static uint16_t rd16(const RrResload *r, uint32_t a) { return (uint16_t)(rd8(r, a) << 8 | rd8(r, a + 1)); }
static uint32_t rd32(const RrResload *r, uint32_t a) { return (uint32_t)rd16(r, a) << 16 | rd16(r, a + 2); }
static void wr16(RrResload *r, uint32_t a, uint16_t v) { wr8(r, a, (uint8_t)(v >> 8)); wr8(r, a + 1, (uint8_t)v); }
static void wr32(RrResload *r, uint32_t a, uint32_t v) { wr16(r, a, (uint16_t)(v >> 16)); wr16(r, a + 2, (uint16_t)v); }

static int refuse(RrResload *r, uint32_t what, const char *fmt, const char *detail) {
    r->refused_offset = what;
    snprintf(r->message, sizeof r->message, fmt, detail);
    return RR_RESLOAD_REFUSED;
}

static void flush(RrResload *r) { if (r->host.flush) r->host.flush(r->host.user); }

void rr_resload_init(RrResload *r, const RrResloadHost *host, uint32_t slave_base, uint16_t version, uint16_t flags) {
    memset(r, 0, sizeof *r);
    r->host = *host;
    r->slave_base = slave_base;
    r->slave_version = version;
    r->slave_flags = flags;
    r->eclock = 709379u;
    r->monitor = 0x00021000u;
}

uint16_t rr_resload_crc16(const RrResload *r, uint32_t address, uint32_t length) {
    uint16_t crc = 0;
    for (uint32_t i = 0; i < length; i++) {
        crc ^= rd8(r, address + i);
        for (int k = 0; k < 8; k++) crc = (crc & 1) ? (uint16_t)((crc >> 1) ^ 0xA001u) : (uint16_t)(crc >> 1);
    }
    return crc;
}

/* A guest string (file name), at most 255 characters. */
static void guest_name(const RrResload *r, uint32_t address, char *out, size_t cap) {
    size_t n = 0;
    for (; n + 1 < cap; n++) {
        char c = (char)rd8(r, address + (uint32_t)n);
        if (!c) break;
        out[n] = c;
    }
    out[n] = 0;
}

static int find(RrResload *r, const char *name, const uint8_t **data, uint32_t *size) {
    *data = NULL;
    *size = 0;
    return r->host.file && r->host.file(r->host.user, name, data, size);
}

/* The result of a service that failed with a DOS error: with WHDLF_NoError the slave expects no return. */
static int failed(RrResload *r, uint32_t regs[16], uint32_t error, uint32_t entry, const char *name) {
    r->io_error = error;
    regs[D0] = 0;
    regs[D1] = error;
    if (r->slave_flags & 0x2) {         /* WHDLF_NoError */
        r->abort_reason[0] = 0;
        r->abort_reason[1] = error;
        r->refused_offset = entry;
        snprintf(r->message, sizeof r->message, "%s failed with DOS error %u (%s)", entry_names[entry / 4],
                 (unsigned)error, name);
        return RR_RESLOAD_ABORT;
    }
    return RR_RESLOAD_RETURN;
}

static void copy_in(RrResload *r, uint32_t dest, const uint8_t *data, uint32_t size) {
    for (uint32_t i = 0; i < size; i++) wr8(r, dest + i, data[i]);
}

static int save(RrResload *r, uint32_t regs[16], uint32_t entry, uint32_t size, uint32_t offset, int whole) {
    char name[256];
    guest_name(r, regs[A0], name, sizeof name);
    if (!r->host.save) return failed(r, regs, RR_DOS_WRITE_PROTECTED, entry, name);
    uint8_t *buffer = (uint8_t *)malloc(size ? size : 1);
    if (!buffer) return failed(r, regs, RR_DOS_DISK_FULL, entry, name);
    for (uint32_t i = 0; i < size; i++) buffer[i] = rd8(r, regs[A1] + i);
    int error = r->host.save(r->host.user, name, offset, buffer, size, whole);
    free(buffer);
    if (error) return failed(r, regs, (uint32_t)error, entry, name);
    regs[D0] = 0xFFFFFFFFu;
    regs[D1] = 0;
    return RR_RESLOAD_RETURN;
}

/* ---- Patch lists -------------------------------------------------------------------------------------------- */

enum {
    PL_END, PL_R, PL_P, PL_PS, PL_S, PL_I, PL_B, PL_W, PL_L, PL_A, PL_PA, PL_NOP, PL_C, PL_CB, PL_CW, PL_CL, PL_PSS,
    PL_NEXT, PL_AB, PL_AW, PL_AL, PL_DATA, PL_ORB, PL_ORW, PL_ORL, PL_GA, PL_BKPT, PL_BELL, PL_IFBW, PL_IFC1,
    PL_IFC5 = PL_IFC1 + 4, PL_IFC1X, PL_IFC5X = PL_IFC1X + 4, PL_ELSE, PL_ENDIF, PL_VB, PL_VW, PL_VL, PL_ANDB, PL_ANDW,
    PL_ANDL, PL_IFC1EQ, PL_IFC5EQ = PL_IFC1EQ + 4, PL_IFC1RG, PL_IFC5RG = PL_IFC1RG + 4, PL_IFVB, PL_IFVW, PL_IFVL,
    PL_IFVBEQ, PL_IFVWEQ, PL_IFVLEQ, PL_COUNT
};

/* Where a patch offset lands: one area (resload_Patch) or a segment list (resload_PatchSeg). */
typedef struct PatchTarget { uint32_t base; uint32_t seglist; } PatchTarget;

static int target_address(const RrResload *r, const PatchTarget *t, uint32_t offset, uint32_t *address) {
    if (!t->seglist) { *address = t->base + offset; return 1; }
    uint32_t seg = t->seglist, done = 0;
    for (int guard = 0; seg && guard < 4096; guard++) {
        uint32_t length = rd32(r, seg - 4) - 8;       /* the allocation holds its size and the next pointer */
        if (offset < done + length) { *address = seg + 4 + (offset - done); return 1; }
        done += length;
        seg = rd32(r, seg) << 2;
    }
    return 0;
}

static int patch_list(RrResload *r, uint32_t list, const PatchTarget *t) {
    uint32_t start = list, p = list;
    uint32_t skip = 0;         /* one bit per nesting level: set while the condition of that level is false */
    int depth = 0;
    for (int count = 0; count < 1000000; count++) {
        uint16_t word = rd16(r, p);
        p += 2;
        unsigned cmd = word & 0x3FFFu;
        int control = (word & 0x4000u) != 0;
        uint32_t at = 0;
        if (cmd == PL_END && !control) {
            if (depth) return refuse(r, RL_PATCH, "patch list ends inside an IF block%s", "");
            flush(r);
            return RR_RESLOAD_RETURN;
        }
        if (!control) {
            uint32_t offset;
            if (word & 0x8000u) { offset = rd16(r, p); p += 2; } else { offset = rd32(r, p); p += 4; }
            if (cmd != PL_NEXT && !target_address(r, t, offset, &at))
                return refuse(r, RL_PATCHSEG, "patch offset outside the segment list%s", "");
        }
        if (cmd >= PL_COUNT) return refuse(r, RL_PATCH, "unknown patch command %s", "");
        int active = skip == 0;
        uint32_t label;
        switch (cmd) {
        case PL_R: if (active) wr16(r, at, 0x4E75); break;
        case PL_P: case PL_PS:
            label = start + (uint32_t)(int32_t)(int16_t)rd16(r, p); p += 2;
            if (active) { wr16(r, at, cmd == PL_P ? 0x4EF9 : 0x4EB9); wr32(r, at + 2, label); }
            break;
        case PL_PSS: {
            label = start + (uint32_t)(int32_t)(int16_t)rd16(r, p);
            uint16_t nops = rd16(r, p + 2); p += 4;
            if (active) {
                wr16(r, at, 0x4EB9); wr32(r, at + 2, label);
                for (uint32_t k = 0; k + 1 < nops; k += 2) wr16(r, at + 6 + k, 0x4E71);
            }
            break;
        }
        case PL_S: { uint16_t d = rd16(r, p); p += 2; if (active) { wr16(r, at, 0x6000); wr16(r, at + 2, d); } break; }
        case PL_I: if (active) wr16(r, at, 0x4AFC); break;
        case PL_B: { uint16_t v = rd16(r, p); p += 2; if (active) wr8(r, at, (uint8_t)v); break; }
        case PL_W: { uint16_t v = rd16(r, p); p += 2; if (active) wr16(r, at, v); break; }
        case PL_L: { uint32_t v = rd32(r, p); p += 4; if (active) wr32(r, at, v); break; }
        case PL_A: {
            uint32_t v = rd32(r, p); p += 4;
            uint32_t value;
            if (active) {
                if (!target_address(r, t, v, &value)) return refuse(r, RL_PATCHSEG, "patch offset outside the segment list%s", "");
                wr32(r, at, value);
            }
            break;
        }
        case PL_PA: label = start + (uint32_t)(int32_t)(int16_t)rd16(r, p); p += 2; if (active) wr32(r, at, label); break;
        case PL_GA: label = start + (uint32_t)(int32_t)(int16_t)rd16(r, p); p += 2; if (active) wr32(r, label, at); break;
        case PL_NOP: { uint16_t n = rd16(r, p); p += 2; if (active) for (uint32_t k = 0; k + 1 < n; k += 2) wr16(r, at + k, 0x4E71); break; }
        case PL_C: { uint32_t n = rd16(r, p); p += 2; if (!n) n = 0x10000; if (active) for (uint32_t k = 0; k < n; k++) wr8(r, at + k, 0); break; }
        case PL_CB: if (active) wr8(r, at, 0); break;
        case PL_CW: if (active) wr16(r, at, 0); break;
        case PL_CL: if (active) wr32(r, at, 0); break;
        case PL_NEXT:
            label = start + (uint32_t)(int32_t)(int16_t)rd16(r, p);
            if (active) {
                if (depth) return refuse(r, RL_PATCH, "PL_NEXT inside an IF block%s", "");
                start = p = label;
            } else {
                p += 2;
            }
            break;
        case PL_AB: { uint16_t v = rd16(r, p); p += 2; if (active) wr8(r, at, (uint8_t)(rd8(r, at) + v)); break; }
        case PL_AW: { uint16_t v = rd16(r, p); p += 2; if (active) wr16(r, at, (uint16_t)(rd16(r, at) + v)); break; }
        case PL_AL: { uint32_t v = rd32(r, p); p += 4; if (active) wr32(r, at, rd32(r, at) + v); break; }
        case PL_ORB: { uint16_t v = rd16(r, p); p += 2; if (active) wr8(r, at, (uint8_t)(rd8(r, at) | v)); break; }
        case PL_ORW: { uint16_t v = rd16(r, p); p += 2; if (active) wr16(r, at, (uint16_t)(rd16(r, at) | v)); break; }
        case PL_ORL: { uint32_t v = rd32(r, p); p += 4; if (active) wr32(r, at, rd32(r, at) | v); break; }
        case PL_ANDB: { uint16_t v = rd16(r, p); p += 2; if (active) wr8(r, at, (uint8_t)(rd8(r, at) & v)); break; }
        case PL_ANDW: { uint16_t v = rd16(r, p); p += 2; if (active) wr16(r, at, (uint16_t)(rd16(r, at) & v)); break; }
        case PL_ANDL: { uint32_t v = rd32(r, p); p += 4; if (active) wr32(r, at, rd32(r, at) & v); break; }
        case PL_DATA: {
            uint16_t n = rd16(r, p); p += 2;
            if (active) for (uint32_t k = 0; k < n; k++) wr8(r, at + k, rd8(r, p + k));
            p += n + (n & 1u);
            break;
        }
        case PL_VB: case PL_VW: case PL_VL:
            label = start + (uint32_t)(int32_t)(int16_t)rd16(r, p); p += 2;
            if (active) {
                if (cmd == PL_VB) wr8(r, at, rd8(r, label));
                else if (cmd == PL_VW) wr16(r, at, rd16(r, label));
                else wr32(r, at, rd32(r, label));
            }
            break;
        case PL_BKPT: case PL_BELL:
            return refuse(r, RL_PATCH, "patch command %s (a debugging aid) is not provided",
                          cmd == PL_BKPT ? "PL_BKPT" : "PL_BELL");
        case PL_ELSE:
            if (!depth) return refuse(r, RL_PATCH, "PL_ELSE without IF%s", "");
            skip ^= 1u << (depth - 1);
            break;
        case PL_ENDIF:
            if (!depth) return refuse(r, RL_PATCH, "PL_ENDIF without IF%s", "");
            depth--;
            skip &= ~(1u << depth);
            break;
        default: {
            /* the IF family: compute the condition, then open a level */
            int cond;
            if (cmd == PL_IFBW) cond = r->button_wait != 0;
            else if (cmd >= PL_IFC1 && cmd <= PL_IFC5) cond = r->custom[cmd - PL_IFC1] != 0;
            else if (cmd >= PL_IFC1X && cmd <= PL_IFC5X) {
                uint16_t bit = rd16(r, p); p += 2;
                cond = bit < 32 && (r->custom[cmd - PL_IFC1X] >> bit) & 1u;
            } else if (cmd >= PL_IFC1EQ && cmd <= PL_IFC5EQ) {
                uint16_t v = rd16(r, p); p += 2;
                cond = (uint16_t)r->custom[cmd - PL_IFC1EQ] == v;
            } else if (cmd >= PL_IFC1RG && cmd <= PL_IFC5RG) {
                int16_t lo = (int16_t)rd16(r, p), hi = (int16_t)rd16(r, p + 2); p += 4;
                int16_t v = (int16_t)(uint16_t)r->custom[cmd - PL_IFC1RG];
                cond = v >= lo && v <= hi;
            } else if (cmd >= PL_IFVB && cmd <= PL_IFVLEQ) {
                label = start + (uint32_t)(int32_t)(int16_t)rd16(r, p); p += 2;
                uint32_t value = cmd == PL_IFVB || cmd == PL_IFVBEQ ? rd8(r, label)
                               : cmd == PL_IFVW || cmd == PL_IFVWEQ ? rd16(r, label) : rd32(r, label);
                if (cmd == PL_IFVB || cmd == PL_IFVW || cmd == PL_IFVL) cond = value != 0;
                else if (cmd == PL_IFVLEQ) { cond = value == rd32(r, p); p += 4; }
                else { uint16_t v = rd16(r, p); p += 2; cond = cmd == PL_IFVBEQ ? (uint8_t)v == value : v == value; }
            } else {
                return refuse(r, RL_PATCH, "unknown patch command%s", "");
            }
            if (depth >= 31) return refuse(r, RL_PATCH, "IF blocks nested deeper than 31%s", "");
            if (!cond) skip |= 1u << depth;
            depth++;
            break;
        }
        }
    }
    return refuse(r, RL_PATCH, "patch list does not end%s", "");
}

int rr_resload_patch(RrResload *r, uint32_t list, uint32_t destination) {
    PatchTarget t = {destination, 0};
    return patch_list(r, list, &t);
}

/* ---- Relocate ------------------------------------------------------------------------------------------------- */

static int relocate(RrResload *r, uint32_t regs[16]) {
    uint32_t address = regs[A0], tags = regs[A1];
    uint32_t chip = 0, fast = 0, align = 4, loadseg = 0, chip_tag = 0, fast_tag = 0;
    for (int guard = 0; tags && guard < 64; guard++) {
        uint32_t tag = rd32(r, tags), data = rd32(r, tags + 4);
        if (!tag) break;
        if (tag == 0x88100000u) { chip = data; chip_tag = tags + 4; }
        else if (tag == 0x88100001u) { fast = data; fast_tag = tags + 4; }
        else if (tag == 0x88100002u) align = data;
        else if (tag == 0x88100003u) loadseg = data;
        tags += 8;
    }
    if (!align || (align & (align - 1)) || align < 4) return refuse(r, RL_RELOCATE, "Relocate: bad alignment%s", "");
    if (rd32(r, address) != 0x3F3u) return refuse(r, RL_RELOCATE, "Relocate: not an executable%s", "");
    /* read the header and the hunks from guest memory into a host copy, then lay them out */
    uint32_t p = address + 4;
    while (rd32(r, p)) p += 4 + 4 * rd32(r, p);
    p += 4;
    uint32_t first = rd32(r, p + 4), last = rd32(r, p + 8);
    p += 12;
    if (last < first || last - first > 511) return refuse(r, RL_RELOCATE, "Relocate: bad hunk table%s", "");
    uint32_t count = last - first + 1, sizes[512], mem[512], base[512], at[512];
    for (uint32_t i = 0; i < count; i++) {
        uint32_t w = rd32(r, p); p += 4;
        if ((w & 0xC0000000u) == 0xC0000000u) p += 4;
        sizes[i] = 4 * (w & 0x3FFFFFFFu);
        mem[i] = w & 0xC0000000u;
    }
    /* the image to rewrite: everything from the first hunk to the end is moved, so copy it out first */
    uint32_t image_start = p, length = 0;
    {   /* find the end of the file: walk the hunk blocks */
        uint32_t q = p;
        for (uint32_t seen = 0; seen < count;) {
            uint32_t kind = rd32(r, q) & 0x3FFFFFFFu; q += 4;
            if (kind == 0x3E9 || kind == 0x3EA) q += 4 + 4 * (rd32(r, q) & 0x3FFFFFFFu);
            else if (kind == 0x3EB) q += 4;
            else if (kind == 0x3EC) { for (uint32_t n; (n = rd32(r, q)) != 0;) q += 8 + 4 * n; q += 4; }
            else if (kind == 0x3FC || kind == 0x3F7) { uint32_t s = q; for (uint16_t n; (n = rd16(r, q)) != 0;) q += 4 + 2 * n; q += 2; q += (4 - ((q - s) & 3)) & 3; }
            else if (kind == 0x3F0) { for (uint32_t n; (n = rd32(r, q)) != 0;) q += 8 + 4 * (n & 0xFFFFFFu); q += 4; }
            else if (kind == 0x3F1) q += 4 + 4 * rd32(r, q);
            else if (kind == 0x3F2) seen++;
            else return refuse(r, RL_RELOCATE, "Relocate: hunk type not read%s", "");
        }
        length = q - image_start;
    }
    uint8_t *file = (uint8_t *)malloc(length ? length : 1);
    if (!file) return refuse(r, RL_RELOCATE, "Relocate: out of memory%s", "");
    for (uint32_t i = 0; i < length; i++) file[i] = rd8(r, image_start + i);
#define FILE32(o) ((uint32_t)file[(o)] << 24 | (uint32_t)file[(o) + 1] << 16 | (uint32_t)file[(o) + 2] << 8 | file[(o) + 3])
    /* layout: over the executable itself, or in the CHIP/FAST areas; LoadSeg lists keep 8 bytes per segment */
    uint32_t extra = loadseg ? 8 : 0, cursor = address, chip_used = 0, fast_used = 0;
    for (uint32_t i = 0; i < count; i++) {
        uint32_t need = (sizes[i] + extra + align - 1) & ~(align - 1);
        uint32_t *used = NULL, area = 0;
        if (chip && mem[i] == 0x40000000u) { used = &chip_used; area = chip; }
        else if (fast && mem[i] == 0x80000000u) { used = &fast_used; area = fast; }
        if (used) { at[i] = area + *used; *used += need; }
        else { at[i] = cursor; cursor += need; }
        base[i] = at[i] + extra;
    }
    /* clear the destination, then copy hunk data and apply relocations from the host copy */
    for (uint32_t i = 0; i < count; i++) for (uint32_t k = 0; k < sizes[i] + extra; k++) wr8(r, at[i] + k, 0);
    uint32_t q = 0, index = 0;
    int current = -1;
    while (q < length) {
        uint32_t kind = FILE32(q) & 0x3FFFFFFFu; q += 4;
        if (kind == 0x3E9 || kind == 0x3EA || kind == 0x3EB) {
            uint32_t longs = FILE32(q) & 0x3FFFFFFFu; q += 4;
            current = (int)index++;
            if (kind != 0x3EB) { for (uint32_t k = 0; k < 4 * longs; k++) wr8(r, base[current] + k, file[q + k]); q += 4 * longs; }
        } else if (kind == 0x3EC) {
            for (uint32_t n; (n = FILE32(q)) != 0;) {
                uint32_t target = FILE32(q + 4);
                for (uint32_t k = 0; k < n; k++) {
                    uint32_t o = FILE32(q + 8 + 4 * k);
                    if (current >= 0 && target < count) wr32(r, base[current] + o, rd32(r, base[current] + o) + base[target]);
                }
                q += 8 + 4 * n;
            }
            q += 4;
        } else if (kind == 0x3FC || kind == 0x3F7) {
            uint32_t s = q;
            for (uint32_t n; (n = (uint32_t)file[q] << 8 | file[q + 1]) != 0;) {
                uint32_t target = (uint32_t)file[q + 2] << 8 | file[q + 3];
                for (uint32_t k = 0; k < n; k++) {
                    uint32_t o = (uint32_t)file[q + 4 + 2 * k] << 8 | file[q + 5 + 2 * k];
                    if (current >= 0 && target < count) wr32(r, base[current] + o, rd32(r, base[current] + o) + base[target]);
                }
                q += 4 + 2 * n;
            }
            q += 2;
            q += (4 - ((q - s) & 3)) & 3;
        } else if (kind == 0x3F0) {
            for (uint32_t n; (n = FILE32(q)) != 0;) q += 8 + 4 * (n & 0xFFFFFFu);
            q += 4;
        } else if (kind == 0x3F1) {
            q += 4 + 4 * FILE32(q);
        }
    }
#undef FILE32
    free(file);
    if (loadseg) {   /* each segment: allocation size, BPTR to the next segment, then the hunk */
        for (uint32_t i = 0; i < count; i++) {
            uint32_t need = (sizes[i] + extra + align - 1) & ~(align - 1);
            wr32(r, at[i], need);
            wr32(r, at[i] + 4, i + 1 < count ? (at[i + 1] + 4) >> 2 : 0);
        }
    }
    if (chip_tag) wr32(r, chip_tag, chip_used);
    if (fast_tag) wr32(r, fast_tag, fast_used);
    regs[D0] = cursor - address;     /* with LOADSEG the first segment starts at `address` (BPTR (address+4)>>2) */
    flush(r);
    return RR_RESLOAD_RETURN;
}

/* ---- Control -------------------------------------------------------------------------------------------------- */

/* whdload_time (whdload.i): days since 1978-01-01, minutes, ticks, then year (78..177), month, day, hour, min, sec. */
static void write_time(RrResload *r, uint32_t at) {
    uint32_t days = r->time_days, y = 1978;
    for (;;) {
        uint32_t len = (y % 4 == 0 && (y % 100 != 0 || y % 400 == 0)) ? 366 : 365;
        if (days < len) break;
        days -= len;
        y++;
    }
    static const uint8_t month_len[12] = {31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};
    uint32_t m = 0;
    for (; m < 12; m++) {
        uint32_t len = month_len[m] + (m == 1 && (y % 4 == 0 && (y % 100 != 0 || y % 400 == 0)));
        if (days < len) break;
        days -= len;
    }
    wr32(r, at, r->time_days);
    wr32(r, at + 4, r->time_mins);
    wr32(r, at + 8, r->time_ticks);
    wr8(r, at + 12, (uint8_t)(y % 100));                     /* 78..99 then 0..77 */
    wr8(r, at + 13, (uint8_t)(m + 1));
    wr8(r, at + 14, (uint8_t)(days + 1));
    wr8(r, at + 15, (uint8_t)(r->time_mins / 60));
    wr8(r, at + 16, (uint8_t)(r->time_mins % 60));
    wr8(r, at + 17, (uint8_t)(r->time_ticks / 50));
}

static int control(RrResload *r, uint32_t regs[16]) {
    uint32_t tags = regs[A0];
    int success = 1;
    for (int guard = 0; tags && guard < 256; guard++) {
        uint32_t tag = rd32(r, tags), slot = tags + 4;
        if (tag == 0) break;                                /* TAG_DONE */
        if (tag == 1) { tags += 8; continue; }              /* TAG_IGNORE */
        if (tag == 2) { tags = rd32(r, slot); continue; }   /* TAG_MORE */
        if (tag == 3) { tags += 8 + 8 * rd32(r, slot); continue; }   /* TAG_SKIP */
        switch (tag - 0x88000000u) {
        case 0: wr32(r, slot, r->attn_flags); break;                 /* ATTNFLAGS_GET */
        case 1: wr32(r, slot, r->eclock); break;                     /* ECLOCKFREQ_GET */
        case 2: wr32(r, slot, r->monitor); break;                    /* MONITOR_GET */
        case 6: wr32(r, slot, (uint32_t)r->button_wait); break;      /* BUTTONWAIT_GET */
        case 7: case 8: case 9: case 10: case 11: wr32(r, slot, r->custom[tag - 0x88000007u]); break;
        case 12: r->cbswitch = rd32(r, slot); break;                 /* CBSWITCH_SET */
        case 13: wr32(r, slot, 0); break;                            /* CHIPREVBITS_GET: OCS */
        case 14: wr32(r, slot, r->io_error); break;                  /* IOERR_GET */
        case 16: r->cbaf = rd32(r, slot); break;                     /* CBAF_SET */
        case 17: wr32(r, slot, RR_RESLOAD_WHDLOAD_VERSION); break;   /* VERSION_GET */
        case 18: wr32(r, slot, 0); break;                            /* REVISION_GET */
        case 19: wr32(r, slot, 0); break;                            /* BUILD_GET */
        case 20:                                                     /* TIME_GET: pointer to a whdload_time */
            if (!r->scratch) return refuse(r, RL_CONTROL, "Control TIME_GET needs a scratch area%s", "");
            write_time(r, r->scratch);
            wr32(r, slot, r->scratch);
            break;
        case 21: wr32(r, slot, 0x0200); break;                       /* BPLCON0_GET: the system's colour burst */
        case 22: wr32(r, slot, r->keytrans); break;                  /* KEYTRANS_GET */
        case 27: wr32(r, slot, 0); break;                            /* LANG_GET: no selection */
        case 40: wr32(r, slot, r->exp_mem_size); break;              /* EXPMEMSIZE_GET */
        case 23: case 24: case 25: case 26: case 28: case 29: case 30: case 32: case 33: case 34: case 35:
            break;                                                   /* Snoop and debugger settings: no effect here */
        default:
            /* as WHDLoad: an item it does not process makes the call return FALSE; it is noted, never pretended */
            snprintf(r->message, sizeof r->message, "Control tag 0x%08X not processed", (unsigned)tag);
            r->unknown_tags++;
            success = 0;
            break;
        }
        tags += 8;
    }
    regs[D0] = success ? 0xFFFFFFFFu : 0;
    return RR_RESLOAD_RETURN;
}

/* ---- Packed data ---------------------------------------------------------------------------------------------- */

/* Unpacks `data` to guest `dest`. Returns 1 and the size, 0 when it is not packed, -1 (refused) for a packed format
   this layer does not unpack or a damaged one. */
static int unpack_to(RrResload *r, const uint8_t *data, uint32_t size, uint32_t dest, uint32_t *unpacked) {
    int format = rr_pack_format(data, size);
    if (format == RR_PACK_NONE) return 0;
    uint32_t want = rr_pack_unpacked_size(data, size);
    uint8_t *out = (uint8_t *)malloc(want ? want : 1);
    const char *why = "out of memory";
    uint32_t got = out ? rr_unpack(data, size, out, want, &why) : 0;
    if (!got) {
        free(out);
        r->refused_offset = RL_DECRUNCH;
        snprintf(r->message, sizeof r->message, "%s data: %s", rr_pack_name(format), why ? why : "not unpacked");
        return -1;
    }
    copy_in(r, dest, out, got);
    free(out);
    *unpacked = got;
    return 1;
}

static int decrunch(RrResload *r, uint32_t regs[16]) {
    uint8_t head[18];
    for (uint32_t i = 0; i < sizeof head; i++) head[i] = rd8(r, regs[A0] + i);
    int format = rr_pack_format(head, sizeof head);
    if (format == RR_PACK_NONE) { regs[D0] = 0; return RR_RESLOAD_RETURN; }    /* unknown data: size 0, as WHDLoad */
    uint32_t total = format == RR_PACK_RNC1 || format == RR_PACK_RNC2 ? 18 + (head[8] << 24 | head[9] << 16 | head[10] << 8 | head[11]) : 0;
    if (!total) {
        r->refused_offset = RL_DECRUNCH;
        snprintf(r->message, sizeof r->message, "resload_Decrunch: %s is not unpacked yet", rr_pack_name(format));
        return RR_RESLOAD_REFUSED;
    }
    uint8_t *packed = (uint8_t *)malloc(total);
    if (!packed) return refuse(r, RL_DECRUNCH, "resload_Decrunch: out of memory%s", "");
    for (uint32_t i = 0; i < total; i++) packed[i] = rd8(r, regs[A0] + i);
    uint32_t size = 0;
    int done = unpack_to(r, packed, total, regs[A1], &size);
    free(packed);
    if (done < 0) return RR_RESLOAD_REFUSED;
    regs[D0] = size;
    flush(r);
    return RR_RESLOAD_RETURN;
}

/* ---- The table ------------------------------------------------------------------------------------------------ */

int rr_resload_call(RrResload *r, uint32_t offset, uint32_t regs[16]) {
    if (offset & 3 || offset / 4 >= RR_RESLOAD_ENTRIES) return refuse(r, offset, "resload offset outside the table%s", "");
    unsigned entry = offset / 4;
    r->calls[entry]++;
    if (r->slave_version < entry_versions[entry])
        return refuse(r, offset, "resload_%s needs a newer slave version", entry_names[entry]);
    char name[256];
    const uint8_t *data;
    uint32_t size;
    switch (offset) {
    case RL_ABORT:
        for (int k = 0; k < 3; k++) r->abort_reason[k] = rd32(r, regs[A7] + 4 + 4 * (uint32_t)k);
        snprintf(r->message, sizeof r->message, "the slave ended the program (%u, %u, %u)",
                 (unsigned)r->abort_reason[0], (unsigned)r->abort_reason[1], (unsigned)r->abort_reason[2]);
        return RR_RESLOAD_ABORT;
    case RL_LOADFILE: case RL_LOADFILEOFFSET: {
        uint32_t want = regs[D0], from = regs[D1];
        guest_name(r, regs[A0], name, sizeof name);
        if (!find(r, name, &data, &size)) return failed(r, regs, RR_DOS_OBJECT_NOT_FOUND, offset, name);
        if (offset == RL_LOADFILE) { copy_in(r, regs[A1], data, size); regs[D0] = size; regs[D1] = 0; }
        else {
            if (from > size) return failed(r, regs, RR_DOS_SEEK_ERROR, offset, name);
            uint32_t n = want < size - from ? want : size - from;
            copy_in(r, regs[A1], data + from, n);
            regs[D0] = 0xFFFFFFFFu; regs[D1] = 0;
        }
        flush(r);
        return RR_RESLOAD_RETURN;
    }
    case RL_GETFILESIZE:
        guest_name(r, regs[A0], name, sizeof name);
        regs[D0] = find(r, name, &data, &size) ? size : 0;
        return RR_RESLOAD_RETURN;
    case RL_GETFILESIZEDEC:
        guest_name(r, regs[A0], name, sizeof name);
        if (!find(r, name, &data, &size)) { regs[D0] = 0; return RR_RESLOAD_RETURN; }
        { uint32_t dec = rr_pack_unpacked_size(data, size); regs[D0] = dec ? dec : size; }
        return RR_RESLOAD_RETURN;
    case RL_LOADFILEDECRUNCH: {
        guest_name(r, regs[A0], name, sizeof name);
        if (!find(r, name, &data, &size)) return failed(r, regs, RR_DOS_OBJECT_NOT_FOUND, offset, name);
        uint32_t unpacked = 0;
        int done = unpack_to(r, data, size, regs[A1], &unpacked);
        if (done < 0) return RR_RESLOAD_REFUSED;
        if (!done) { copy_in(r, regs[A1], data, size); unpacked = size; }
        regs[D0] = unpacked;
        regs[D1] = 0;
        flush(r);
        return RR_RESLOAD_RETURN;
    }
    case RL_DECRUNCH: return decrunch(r, regs);
    case RL_DISKLOAD: {
        snprintf(name, sizeof name, "Disk.%u", (unsigned)(regs[D2] & 0xFF));
        if (!find(r, name, &data, &size)) return failed(r, regs, RR_DOS_OBJECT_NOT_FOUND, offset, name);
        if (regs[D0] > size || regs[D1] > size - regs[D0]) return failed(r, regs, RR_DOS_SEEK_ERROR, offset, name);
        copy_in(r, regs[A0], data + regs[D0], regs[D1]);
        regs[D0] = 0xFFFFFFFFu; regs[D1] = 0;
        flush(r);
        return RR_RESLOAD_RETURN;
    }
    case RL_SAVEFILE: return save(r, regs, offset, regs[D0], 0, 1);
    case RL_SAVEFILEOFFSET: return save(r, regs, offset, regs[D0], regs[D1], 0);
    case RL_DELETEFILE:
        guest_name(r, regs[A0], name, sizeof name);
        if (!r->host.remove) return failed(r, regs, RR_DOS_WRITE_PROTECTED, offset, name);
        { int e = r->host.remove(r->host.user, name); if (e) return failed(r, regs, (uint32_t)e, offset, name); }
        regs[D0] = 0xFFFFFFFFu; regs[D1] = 0;
        return RR_RESLOAD_RETURN;
    case RL_CRC16: regs[D0] = rr_resload_crc16(r, regs[A0], regs[D0]); return RR_RESLOAD_RETURN;
    case RL_FLUSHCACHE: flush(r); return RR_RESLOAD_RETURN;
    case RL_SETCACR: case RL_SETCPU: regs[D0] = 0; return RR_RESLOAD_RETURN;    /* a 68000 has no cache */
    case RL_DELAY: return RR_RESLOAD_RETURN;     /* returns at once: the wait is not modelled yet */
    case RL_CONTROL: return control(r, regs);
    case RL_PATCH: return rr_resload_patch(r, regs[A0], regs[A1]);
    case RL_PATCHSEG: { PatchTarget t = {0, regs[A1] << 2}; return patch_list(r, regs[A0], &t); }
    case RL_RELOCATE: return relocate(r, regs);
    case RL_GETCUSTOM:
        if (regs[D0]) wr8(r, regs[A0], 0);      /* no Custom/S string is given */
        regs[D0] = 0;
        return RR_RESLOAD_RETURN;
    case RL_LOG: return RR_RESLOAD_RETURN;
    default:
        return refuse(r, offset, "resload_%s is not provided", entry_names[entry]);
    }
}
