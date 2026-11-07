/* Retro-Recomp: resload services of a WHDLoad slave (MIT). See rr_resload.h. */
#include "rr_resload.h"
#include "rr_decrunch.h"

#include <stdarg.h>
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

/* An AmigaDOS error code in words (the codes of dos/dos.h a slave reports through resload_Abort). */
static const char *dos_error_name(uint32_t code) {
    switch (code) {
    case 103: return "not enough memory";
    case 202: return "object in use";
    case 204: return "folder not found";
    case 205: return "file not found";
    case 213: return "disk not validated";
    case 214: return "disk write-protected";
    case 218: return "device not mounted";
    case 221: return "disk full";
    case 225: return "not a DOS disk";
    case 226: return "no disk";
    default: return NULL;
    }
}

/* The sentence a resload_Abort leaves for the player: what the slave could not do, named, with its raw numbers kept after
   it. The TDREASON values are those of WHDLoad's public include whdload.i; primary and secondary mean what the autodoc
   of resload_Abort says for each reason. */
static void describe_abort(RrResload *r) {
    const uint32_t reason = r->abort_reason[0], primary = r->abort_reason[1], secondary = r->abort_reason[2];
    char name[128];
    const char *dos = dos_error_name(primary);
    char error[64];
    if (dos) snprintf(error, sizeof error, "%s, AmigaDOS error %u", dos, (unsigned)primary);
    else snprintf(error, sizeof error, "AmigaDOS error %u", (unsigned)primary);
    switch ((int32_t)reason) {
    case -1:
        snprintf(r->message, sizeof r->message, "the game quit (resload_Abort, TDREASON_OK)");
        return;
    case 1: case 2: case 27:
        guest_name(r, secondary, name, sizeof name);
        snprintf(r->message, sizeof r->message, "the install could not %s %s%s%s (%s; resload_Abort reason %d)",
                 reason == 1 ? "read" : reason == 2 ? "write" : "delete", name[0] ? "the file \"" : "a file", name,
                 name[0] ? "\"" : "", error, (int)(int32_t)reason);
        return;
    case 6:
        guest_name(r, secondary, name, sizeof name);
        snprintf(r->message, sizeof r->message, "the install could not list the folder \"%s\" (%s; resload_Abort reason 6)", name, error);
        return;
    case 7:
        snprintf(r->message, sizeof r->message, "the install could not read its disk %u (error %u; resload_Abort reason 7)",
                 (unsigned)secondary, (unsigned)primary);
        return;
    case 9:
        snprintf(r->message, sizeof r->message, "the slave does not recognise this version of the game's files (resload_Abort reason 9)");
        return;
    case 10:
        guest_name(r, primary, name, sizeof name);
        snprintf(r->message, sizeof r->message, "the slave's operating-system emulation failed in \"%s\" (error %u; resload_Abort reason 10)",
                 name, (unsigned)secondary);
        return;
    case 11: snprintf(r->message, sizeof r->message, "the install needs a 68020 processor (resload_Abort reason 11)"); return;
    case 12: snprintf(r->message, sizeof r->message, "the install needs the AGA chipset (resload_Abort reason 12)"); return;
    case 13: snprintf(r->message, sizeof r->message, "the install runs on NTSC only (resload_Abort reason 13)"); return;
    case 14: snprintf(r->message, sizeof r->message, "the install runs on PAL only (resload_Abort reason 14)"); return;
    case 43:
        guest_name(r, primary, name, sizeof name);
        snprintf(r->message, sizeof r->message, "the slave stopped: \"%s\" (resload_Abort reason 43)", name);
        return;
    default:
        snprintf(r->message, sizeof r->message, "the slave ended the program (resload_Abort reason %d, %u, %u)",
                 (int)(int32_t)reason, (unsigned)primary, (unsigned)secondary);
    }
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

/* ---- Kickstart ------------------------------------------------------------------------------------------------ */

static void format_to(char *buffer, size_t cap, const char *fmt, ...) {
    size_t used = strlen(buffer);
    if (used + 1 >= cap) return;
    va_list args;
    va_start(args, fmt);
    vsnprintf(buffer + used, cap - used, fmt, args);
    va_end(args);
}

/* Where the image goes: the start of ExpMem, which must exist and hold it. */
static int kick_room(RrResload *r, uint32_t size) {
    if (!r->exp_mem) return refuse(r, RL_LOADKICK, "no ExpMem to load a Kickstart image into%s", "");
    if (r->exp_mem_size && size > r->exp_mem_size) {
        r->refused_offset = RL_LOADKICK;
        snprintf(r->message, sizeof r->message, "the Kickstart image asked for (%u bytes) is larger than ExpMem (%u bytes)",
                 (unsigned)size, (unsigned)r->exp_mem_size);
        return RR_RESLOAD_REFUSED;
    }
    return RR_RESLOAD_RETURN;
}

/* One try: the host owns the image, answers whether the player's matches and copies it to ExpMem. */
static int kick_try(RrResload *r, uint32_t size, uint16_t crc, const char *name) {
    if (!r->host.kickstart || !r->host.kickstart(r->host.user, size, crc, name, r->exp_mem)) return 0;
    r->kick_loaded = 1;
    r->kick_size = size;
    r->kick_crc = crc;
    snprintf(r->kick_name, sizeof r->kick_name, "%s", name);
    flush(r);
    return 1;
}

static void kick_wanted(RrResload *r, uint32_t size, uint16_t crc, const char *name, uint32_t count) {
    r->kick_wanted_size = size;
    r->kick_wanted_crc = crc;
    snprintf(r->kick_wanted_name, sizeof r->kick_wanted_name, "%s", name);
    r->kick_wanted_count = count;
}

/* One image asked for and not found: the refusal names it by size, CRC-16 and name. */
static int kick_missing(RrResload *r, uint32_t size, uint16_t crc, const char *name) {
    kick_wanted(r, size, crc, name, 1);
    r->refused_offset = RL_LOADKICK;
    snprintf(r->message, sizeof r->message,
             "the Kickstart image the slave asks for is not among the player's: size %u, CRC-16 %04X, name %s",
             (unsigned)size, (unsigned)crc, name);
    return RR_RESLOAD_REFUSED;
}

/* resload_LoadKick: only returns on success, as the autodoc says; WHDLoad's switch to the operating system afterwards
   has no counterpart here (the slave goes on with the image at the start of ExpMem). */
static int load_kick(RrResload *r, uint32_t regs[16]) {
    uint32_t size = regs[D0];
    uint16_t crc = (uint16_t)regs[D1];
    char name[64];
    guest_name(r, regs[A0], name, sizeof name);
    r->kick_loaded = 0;
    int room = kick_room(r, size);
    if (room != RR_RESLOAD_RETURN) return room;
    return kick_try(r, size, crc, name) ? RR_RESLOAD_RETURN : kick_missing(r, size, crc, name);
}

/* Offsets in the slave structure (whdload.i): ws_kickname (RPTR), ws_kicksize (ULONG), ws_kickcrc (UWORD). */
enum { WS_KICKNAME = 42, WS_KICKSIZE = 44, WS_KICKCRC = 48 };

int rr_resload_load_slave_kickstart(RrResload *r) {
    r->kick_loaded = 0;
    if (r->slave_version < 16) return RR_RESLOAD_RETURN;
    uint32_t base = r->slave_base;
    uint32_t rptr = rd16(r, base + WS_KICKNAME), size = rd32(r, base + WS_KICKSIZE);
    uint16_t crc = rd16(r, base + WS_KICKCRC);
    if (!size || !rptr) return RR_RESLOAD_RETURN;         /* the slave asks for no Kickstart */
    int room = kick_room(r, size);
    if (room != RR_RESLOAD_RETURN) return room;
    char name[64];
    if (crc != 0xFFFFu) {
        guest_name(r, base + rptr, name, sizeof name);
        return kick_try(r, size, crc, name) ? RR_RESLOAD_RETURN : kick_missing(r, size, crc, name);
    }
    /* WHDLoad 16.1: pairs of (CRC-16, RPTR to a name) ended by a CRC-16 of 0, tried in order */
    char list[256];
    list[0] = 0;
    uint32_t count = 0;
    for (uint32_t pos = base + rptr; count < 32; pos += 4) {
        uint16_t entry_crc = rd16(r, pos);
        if (!entry_crc) break;
        guest_name(r, base + rd16(r, pos + 2), name, sizeof name);
        if (!count) kick_wanted(r, size, entry_crc, name, 0);
        count++;
        if (kick_try(r, size, entry_crc, name)) {
            wr16(r, base + WS_KICKCRC, entry_crc);       /* the slave learns which image it got */
            r->kick_wanted_count = 0;
            return RR_RESLOAD_RETURN;
        }
        format_to(list, sizeof list, "%s%04X %s", count > 1 ? ", " : "", (unsigned)entry_crc, name);
    }
    r->kick_wanted_count = count;
    r->refused_offset = RL_LOADKICK;
    snprintf(r->message, sizeof r->message,
             "none of the %u Kickstart images the slave asks for is among the player's: size %u, CRC-16 and name %s",
             (unsigned)count, (unsigned)size, list);
    return RR_RESLOAD_REFUSED;
}

/* ---- Examine, ExNext, ListFiles ------------------------------------------------------------------------------ */

/* The install's files as the host lists them; folders are implied by the names ('/' separated, AmigaDOS compares
   names without regard to case). WHDLoad's autodoc is silent on several points, settled here and the same everywhere:
   - the entries of a folder come sorted by name (case-insensitive, then byte order), folders among the files;
   - a folder shows the spelling of its name that sorts first when several files spell it differently;
   - dates are the fixed start time of Control TIME_GET, protection bits are 0 (all allowed), no comment, no owner;
   - a file's fib_NumBlocks is its size in 512-byte blocks, rounded up; a folder's size and blocks are 0;
   - the data folder itself is "" and examines as a folder with an empty name;
   - Examine and ExNext failures return their error without ending the program, with or without WHDLF_NoError (the
     autodoc says "only returns on success" of ListFiles alone), and Examine does not require WHDLF_Examine. */

enum {
    FIB_DISKKEY = 0, FIB_DIRENTRYTYPE = 4, FIB_FILENAME = 8, FIB_PROTECTION = 116, FIB_ENTRYTYPE = 120, FIB_SIZE = 124,
    FIB_NUMBLOCKS = 128, FIB_DATE = 132, FIB_COMMENT = 144, FIB_NAME_CAP = 108
};
#define ST_FILE ((uint32_t)-3)
#define ST_USERDIR 2u

typedef struct DirEntry {
    char name[FIB_NAME_CAP];
    int is_dir;
    uint32_t size;
} DirEntry;

static unsigned fold(unsigned char c) { return (c >= 'a' && c <= 'z') ? (unsigned)(c - 'a' + 'A') : c; }

static int name_compare(const char *a, const char *b) {
    for (; *a && *b; a++, b++) if (fold((unsigned char)*a) != fold((unsigned char)*b)) break;
    return (int)fold((unsigned char)*a) - (int)fold((unsigned char)*b);
}

/* Are the first `n` characters of `a` the name `b` (without regard to case)? */
static int name_prefix_is(const char *a, size_t n, const char *b) {
    if (strlen(b) != n) return 0;
    for (size_t i = 0; i < n; i++) if (fold((unsigned char)a[i]) != fold((unsigned char)b[i])) return 0;
    return 1;
}

static int listing(RrResload *r, uint32_t index, const char **name, uint32_t *size) {
    return r->host.list && r->host.list(r->host.user, index, name, size);
}

/* The entry of folder `dir` that follows `last` in the sorted order (the first one when `last` is NULL). Needs no
   copy of the listing: one pass over the host's files picks the smallest name above `last`. */
static int next_child(RrResload *r, const char *dir, const char *last, DirEntry *out) {
    const char *file;
    uint32_t size, found = 0;
    size_t dir_len = strlen(dir);
    for (uint32_t i = 0; listing(r, i, &file, &size); i++) {
        const char *rest = file;
        if (dir_len) {
            if (strlen(file) <= dir_len + 1 || file[dir_len] != '/' || !name_prefix_is(file, dir_len, dir)) continue;
            rest = file + dir_len + 1;
        }
        size_t len = strcspn(rest, "/");
        if (!len) continue;
        DirEntry c;
        c.is_dir = rest[len] == '/';
        c.size = c.is_dir ? 0 : size;
        if (len >= sizeof c.name) len = sizeof c.name - 1;
        memcpy(c.name, rest, len);
        c.name[len] = 0;
        if (last && name_compare(c.name, last) <= 0) continue;
        if (found) {
            int order = name_compare(c.name, out->name);
            if (order > 0 || (order == 0 && strcmp(c.name, out->name) >= 0)) continue;
        }
        *out = c;
        found = 1;
    }
    return (int)found;
}

/* What `path` names: 1 a file, 2 a folder, 0 nothing; `leaf` gets the object's own name as the install spells it. */
static int resolve(RrResload *r, const char *path, DirEntry *leaf) {
    memset(leaf, 0, sizeof *leaf);
    if (!*path) { leaf->is_dir = 1; return 2; }
    size_t plen = strlen(path);
    const char *slash = strrchr(path, '/');
    size_t own_len = strlen(slash ? slash + 1 : path);
    if (!own_len) return 0;
    const char *file;
    uint32_t size;
    int kind = 0;
    for (uint32_t i = 0; listing(r, i, &file, &size); i++) {
        size_t flen = strlen(file);
        const char *own = file + (plen - own_len);      /* the last part of the path, as this file spells it */
        if (flen >= plen && (flen == plen || file[plen] == '/') && name_prefix_is(file, plen, path)) {
            if (flen == plen) {                           /* the file itself */
                leaf->is_dir = 0;
                leaf->size = size;
                snprintf(leaf->name, sizeof leaf->name, "%.*s", (int)(own_len < FIB_NAME_CAP - 1 ? own_len : FIB_NAME_CAP - 1), own);
                return 1;
            }
            char spelled[FIB_NAME_CAP];                   /* a file below it: the folder exists */
            snprintf(spelled, sizeof spelled, "%.*s", (int)(own_len < FIB_NAME_CAP - 1 ? own_len : FIB_NAME_CAP - 1), own);
            if (kind != 2 || strcmp(spelled, leaf->name) < 0) memcpy(leaf->name, spelled, sizeof spelled);
            leaf->is_dir = 1;
            kind = 2;
        }
    }
    if (!kind && !r->host.list) {            /* a host without a listing can still answer for a file by name */
        const uint8_t *data;
        if (find(r, path, &data, &size)) {
            leaf->size = size;
            snprintf(leaf->name, sizeof leaf->name, "%.*s", (int)(own_len < FIB_NAME_CAP - 1 ? own_len : FIB_NAME_CAP - 1), slash ? slash + 1 : path);
            return 1;
        }
    }
    return kind;
}

/* Only the fields the layer has values for are written, the name up to its NUL and the comment as an empty string: the
   buffer is not cleared and its owner and reserved tail (offset 145 on) are left alone. The autodoc says the buffer
   holds 260 bytes, but the operating-system emulation of Another World and 4D Sports Boxing (Kickstart 1.3) hands the
   layer a FileInfoBlock with only 240 bytes before the end of its allocation: writing all 260 zeroed the header of the
   free chunk behind it, which emptied exec's fast-memory list and made every later allocation fail (AmigaDOS 103). */
static void fill_fib(RrResload *r, uint32_t fib, uint32_t key, const DirEntry *e) {
    wr32(r, fib + FIB_DISKKEY, key);
    wr32(r, fib + FIB_DIRENTRYTYPE, e->is_dir ? ST_USERDIR : ST_FILE);
    size_t length = 0;
    for (; e->name[length] && length < FIB_NAME_CAP - 1; length++) wr8(r, fib + FIB_FILENAME + (uint32_t)length, (uint8_t)e->name[length]);
    wr8(r, fib + FIB_FILENAME + (uint32_t)length, 0);
    wr32(r, fib + FIB_PROTECTION, 0);
    wr32(r, fib + FIB_ENTRYTYPE, e->is_dir ? ST_USERDIR : ST_FILE);
    wr32(r, fib + FIB_SIZE, e->size);
    wr32(r, fib + FIB_NUMBLOCKS, (e->size + 511u) / 512u);
    wr32(r, fib + FIB_DATE, r->time_days);
    wr32(r, fib + FIB_DATE + 4, r->time_mins);
    wr32(r, fib + FIB_DATE + 8, r->time_ticks);
    wr8(r, fib + FIB_COMMENT, 0);                  /* no comment */
}

static int examine_failed(RrResload *r, uint32_t regs[16], uint32_t error) {
    r->io_error = error;
    regs[D0] = 0;
    regs[D1] = error;
    return RR_RESLOAD_RETURN;
}

/* fib_DiskKey of a folder: the token of its walk (low 4 bits: slot) in the high half, how many entries ExNext has
   returned so far in the low half. The walk's folder lives in r->scans; the position is in the FIB itself, so a copy of
   the FIB goes on from where it was. */
static uint16_t scan_open(RrResload *r, const char *dir) {
    unsigned slot = RR_SCAN_SLOTS;
    for (unsigned i = 0; i < RR_SCAN_SLOTS; i++)
        if (r->scans[i].token && !name_compare(r->scans[i].dir, dir)) return r->scans[i].token;
    for (unsigned i = 0; i < RR_SCAN_SLOTS && slot == RR_SCAN_SLOTS; i++) if (!r->scans[i].token) slot = i;
    if (slot == RR_SCAN_SLOTS) slot = r->scan_generation % RR_SCAN_SLOTS;      /* all busy: one walk gives way */
    r->scan_generation++;
    uint16_t generation = (uint16_t)((r->scan_generation & 0xFFFu) | 1u);
    r->scans[slot].token = (uint16_t)((generation << 4) | slot);
    snprintf(r->scans[slot].dir, sizeof r->scans[slot].dir, "%s", dir);
    return r->scans[slot].token;
}

static int examine(RrResload *r, uint32_t regs[16]) {
    char name[256];
    guest_name(r, regs[A0], name, sizeof name);
    DirEntry e;
    int kind = resolve(r, name, &e);
    if (!kind) return examine_failed(r, regs, RR_DOS_OBJECT_NOT_FOUND);
    fill_fib(r, regs[A1], kind == 2 ? (uint32_t)scan_open(r, name) << 16 : 0, &e);
    regs[D0] = 0xFFFFFFFFu;
    regs[D1] = 0;
    return RR_RESLOAD_RETURN;
}

static int exnext(RrResload *r, uint32_t regs[16]) {
    uint32_t fib = regs[A0], key = rd32(r, fib + FIB_DISKKEY);
    uint16_t token = (uint16_t)(key >> 16);
    const RrScan *scan = &r->scans[token & 15u];
    if (!token || scan->token != token) return examine_failed(r, regs, RR_DOS_OBJECT_WRONG_TYPE);   /* not a folder's FIB */
    char last[FIB_NAME_CAP];
    size_t n = 0;
    for (; n + 1 < sizeof last && (last[n] = (char)rd8(r, fib + FIB_FILENAME + (uint32_t)n)) != 0; n++) {}
    last[n] = 0;
    uint32_t done = key & 0xFFFFu;
    DirEntry e;
    if (!next_child(r, scan->dir, done ? last : NULL, &e)) return examine_failed(r, regs, RR_DOS_NO_MORE_ENTRIES);
    fill_fib(r, fib, (key & 0xFFFF0000u) | (done < 0xFFFFu ? done + 1 : done), &e);
    regs[D0] = 0xFFFFFFFFu;
    regs[D1] = 0;
    return RR_RESLOAD_RETURN;
}

/* resload_ListFiles: the names of a folder's files (folders are skipped), each followed by a 0, sorted; D0 is how
   many were written. A name that does not fit ends the list with ERROR_BUFFER_OVERFLOW (the autodoc names no code). */
static int list_files(RrResload *r, uint32_t regs[16]) {
    uint32_t capacity = regs[D0], buffer = regs[A1], used = 0, amount = 0;
    char name[256];
    guest_name(r, regs[A0], name, sizeof name);
    DirEntry dir;
    int kind = resolve(r, name, &dir);
    if (kind != 2) return failed(r, regs, kind ? RR_DOS_OBJECT_WRONG_TYPE : RR_DOS_OBJECT_NOT_FOUND, RL_LISTFILES, name);
    DirEntry e;
    const char *last = NULL;
    char previous[FIB_NAME_CAP];
    int overflow = 0;
    while (next_child(r, name, last, &e)) {
        snprintf(previous, sizeof previous, "%s", e.name);
        last = previous;
        if (e.is_dir) continue;
        uint32_t need = (uint32_t)strlen(e.name) + 1;
        if (need > capacity - used) { overflow = 1; break; }
        for (uint32_t i = 0; i < need; i++) wr8(r, buffer + used + i, (uint8_t)e.name[i]);
        used += need;
        amount++;
    }
    if (amount) flush(r);
    if (overflow) {
        int status = failed(r, regs, RR_DOS_BUFFER_OVERFLOW, RL_LISTFILES, name);
        regs[D0] = amount;
        return status;
    }
    regs[D0] = amount;
    regs[D1] = 0;
    r->io_error = 0;
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
    {
        /* resload_Abort(success, primary, secondary) takes its arguments at (a7): the documented call pushes them and jumps
           through `rts`, so no return address lies above them. A slave that called it with jsr has its return address
           first (an address, never one of the small TDREASON values): it is skipped. */
        uint32_t sp = regs[A7], first = rd32(r, sp);
        if (first > 0xFFFFu && first != 0xFFFFFFFFu) sp += 4;
        for (int k = 0; k < 3; k++) r->abort_reason[k] = rd32(r, sp + 4 * (uint32_t)k);
        describe_abort(r);
        return RR_RESLOAD_ABORT;
    }
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
    case RL_LOADKICK: return load_kick(r, regs);
    case RL_EXAMINE: return examine(r, regs);
    case RL_EXNEXT: return exnext(r, regs);
    case RL_LISTFILES: return list_files(r, regs);
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
