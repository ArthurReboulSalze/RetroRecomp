/* PlayStation game: the player's disc appended to this executable, run on Beetle PSX (psx_session.c) with the player's BIOS
 * embedded as resource 104 (none: OpenBIOS, built into the core). Windowed play goes through the host kit
 * (adapters/rrhk_psx.c); the converter's checks run the same executable headless. Nothing is written unless asked for on the
 * command line, except the memory card of slot 1 in the game's data folder.
 * Original Retro-Recomp code, MIT; linked with Beetle PSX, the program is GPL-2.0 as a whole (licenses/beetle-psx.md). */
#define WIN32_LEAN_AND_MEAN
#include "platform_io.h"
#include "embedded_resources.h"
#ifdef _WIN32
#include <shellapi.h>
#else
#include <unistd.h>
#endif
#include <SDL.h>
#include <math.h>
#include <errno.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "console16_state.h"
#include "retro16_state_config.h"
#include "psx_game.h"
#include "psx_session.h"
#include "runtime_feedback.h"
#include "save_set_aside.h"

/* Runtime hints: the instructions of main RAM or the BIOS that the game's native steps did not hold and the interpreter ran,
 * while the player records hints (F12). They are gathered by 16-byte block (the words run there, a mask of which, how often)
 * and handed to the bounded recorder at the end of the game, the most run first, so that its records go to the code that
 * counts: the next conversion makes them native steps after the same checks as the code its routes ran. Called by the core's
 * step hook (our anchored change of cpu.c). */
enum { HINT_SLOTS = 1 << 16 };
typedef struct { uint32_t block, words[4], count; uint8_t mask; } Hint;
static Hint *hints;
static unsigned hint_count;

/* --interpreted: every (physical address, word) the interpreter ran in this process, with its count (the
 * conversion lists them by address in its report, each with its reason). Exact, unlike the hints: a full table is said. */
enum { RAN_SLOTS = 1 << 18 };
typedef struct { uint32_t address, word; uint64_t count; } Ran;
static Ran *ran;
static unsigned ran_count;
static int ran_full;
static const char *interpreted_path;

static void ran_note(uint32_t physical, uint32_t instr) {
    if (!ran && !(ran = (Ran *)calloc(RAN_SLOTS, sizeof *ran))) { ran_full = 1; return; }
    for (unsigned slot = ((physical >> 2) * 2654435761u ^ instr * 40503u) & (RAN_SLOTS - 1), n = 0; n < RAN_SLOTS;
         ++n, slot = (slot + 1) & (RAN_SLOTS - 1)) {
        Ran *r = &ran[slot];
        if (!r->count) {
            if (ran_count >= RAN_SLOTS / 2) { ran_full = 1; return; }
            r->address = physical; r->word = instr; ran_count++;
        } else if (r->address != physical || r->word != instr) {
            continue;
        }
        r->count++;
        return;
    }
}

static int ran_order(const void *a, const void *b) {
    const Ran *x = (const Ran *)a, *y = (const Ran *)b;
    if (x->address != y->address) return x->address < y->address ? -1 : 1;
    return x->word < y->word ? -1 : x->word > y->word;
}

static int ran_write(void);

void rr_psx_fallback(uint32_t pc, uint32_t instr) {
    const uint32_t physical = pc & 0x1FFFFFFFu;
    if (interpreted_path) ran_note(physical, instr);
    if (!(physical < 0x200000u || physical - 0x1FC00000u < 0x80000u) || (physical & 3)) return;
    if (!rr_feedback_enabled()) return;
    if (!hints && !(hints = (Hint *)calloc(HINT_SLOTS, sizeof *hints))) return;
    const uint32_t block = physical & ~15u;
    const unsigned word = (physical >> 2) & 3;
    /* A block whose word differs (code loaded over other code) takes another slot: each variant is kept. */
    for (unsigned n = 0, slot = (block >> 4) * 2654435761u & (HINT_SLOTS - 1); n < 64; ++n, slot = (slot + 1) & (HINT_SLOTS - 1)) {
        Hint *h = &hints[slot];
        if (!h->count) {
            if (hint_count >= HINT_SLOTS / 2) return;
            h->block = block | 1u;   /* | 1: an empty slot matches no block */
            hint_count++;
        } else if (h->block != (block | 1u) || ((h->mask >> word) & 1 && h->words[word] != instr)) {
            continue;
        }
        h->words[word] = instr;
        h->mask |= (uint8_t)(1u << word);
        if (h->count != UINT32_MAX) h->count++;
        return;
    }
}

static int hint_order(const void *a, const void *b) {
    const Hint *x = (const Hint *)a, *y = (const Hint *)b;
    if (x->count != y->count) return x->count < y->count ? 1 : -1;
    return x->block < y->block ? -1 : x->block > y->block;
}

/* At the end of the game: the blocks to the recorder, the most run first (it keeps what fits and writes at exit). */
static void hints_finish(void) {
    if (!hints) return;
    if (rr_feedback_enabled()) {
        unsigned used = 0;
        for (unsigned n = 0; n < HINT_SLOTS; ++n) if (hints[n].count) hints[used++] = hints[n];
        qsort(hints, used, sizeof *hints, hint_order);
        for (unsigned n = 0; n < used; ++n) {
            uint8_t bytes[16];
            for (unsigned w = 0; w < 4; ++w)
                for (unsigned b = 0; b < 4; ++b) bytes[w * 4 + b] = (uint8_t)(hints[n].words[w] >> (8 * b));
            rr_feedback_note(RR_FB_PSX, hints[n].block & ~1u, hints[n].mask, bytes, 16);
        }
    }
    free(hints);
    hints = NULL;
    hint_count = 0;
}

int rr_psx_sdl_main(const char *title, int scale);

#define FNV_BASIS 14695981039346656037ull
#define FNV_PRIME 1099511628211ull
#define BIOS_RESOURCE 104
#define MAX_SCRIPT 65536

static RrPsxSession *session;
static unsigned frame;
static int headless, frames, scripted, diagnostics;
static const char *report_path, *trace_path, *save_path, *load_path, *capture_dir, *pack_override;
#ifdef RR_PSX_OBSERVE
static const char *observe_path;
int rr_psx_observe_write(FILE *f);    /* psx_observe.c: the conversion's observing build only */
#endif
static unsigned save_at, capture_every = 600;
static int state_loaded, load_rejected, save_failed;
static FILE *trace_file;
static uint64_t pcm_hash = FNV_BASIS, image_hash = FNV_BASIS, samples, nonzero;
static unsigned nonuniform_frames;
static char fault[256];
typedef struct { unsigned frame, pads[2]; } Input;
static Input *script;
static unsigned script_count, script_pos;
static uint16_t script_pads[2];
static int16_t frame_audio[2 * 8192];
static FILE *pcm_file;   /* --pcm: the sound of every frame as the host receives it, raw 16-bit stereo (evidence) */
static size_t frame_audio_count, audio_read;
static wchar_t card_path[4096];
static uint64_t card_hash;
static int card_option;     /* --card: a headless run reads and writes this card file as the window does its own (evidence) */
static unsigned card_notice; /* 0 nothing to say; 1 an unusable card file was set aside; 2 it could not be, saving is off */
unsigned rr_psx_card_notice(void) { return card_notice; }

RrPsxSession *rr_psx_host_session(void) { return session; }

static FILE *file_open(const char *path, const wchar_t *mode) {
    wchar_t name[4096];
    return rr_from_utf8(path, name, 4096) ? rr_fopen(name, mode) : NULL;
}

static int state_file(const char *path, int load) {
    wchar_t name[4096];
    return rr_from_utf8(path, name, 4096) && rr16_state_file(name, load != 0);
}

/* "frame p1 p2": the pad words (hex, the session's bits), held from that frame on. */
static int load_script(const char *path) {
    FILE *f = file_open(path, L"rb");
    if (!f) return 0;
    if (!(script = (Input *)calloc(MAX_SCRIPT, sizeof *script))) { fclose(f); return 0; }
    char line[256];
    unsigned last = 0;
    while (fgets(line, sizeof line, f)) {
        if (line[0] == '#' || line[0] == '\n' || line[0] == '\r') continue;
        if (script_count >= MAX_SCRIPT) { fclose(f); return 0; }
        Input *row = &script[script_count];
        if (sscanf(line, "%u %x %x", &row->frame, &row->pads[0], &row->pads[1]) != 3 || row->frame < last ||
            row->pads[0] > 0xffff || row->pads[1] > 0xffff) { fclose(f); return 0; }
        last = row->frame;
        script_count++;
    }
    fclose(f);
    scripted = 1;
    return script_count != 0;
}

static uint64_t fnv(const void *data, size_t size, uint64_t h) {
    const uint8_t *p = (const uint8_t *)data;
    for (size_t i = 0; i < size; ++i) h = (h ^ p[i]) * FNV_PRIME;
    return h;
}

/* The memory card of slot 1 is written to the game's data folder when it changed (the core keeps it in memory). It is the raw
 * 128 KiB of the card (the .mcr form other programs read too). A file the game cannot use (another size, a folder, unreadable)
 * is moved aside whole to "<card>.unusable-N" and the game starts with the core's empty card; when it cannot be moved, it stays
 * untouched and nothing is saved this session. A card of the right size with damaged contents is the console's own case: the
 * BIOS or the game says so and offers to format it. */
static void card_sync(int load) {
    size_t size = 0;
    uint8_t *card = rr_psx_card(session, &size);
    if (!card || !size || !card_path[0]) return;
    if (load) {
        uint8_t *read = (uint8_t *)malloc(size);
        if (!read) { card_path[0] = 0; card_notice = 2; return; }
        errno = 0;
        FILE *f = rr_fopen(card_path, L"rb");
        int usable = 0, present = f != NULL || (errno != 0 && errno != ENOENT);
        if (f) {
            usable = fread(read, 1, size, f) == size && fgetc(f) == EOF && !ferror(f);
            fclose(f);
        }
        if (usable) memcpy(card, read, size);
        free(read);
        if (present && !usable) {
            card_notice = rr_save_set_aside(card_path) ? 1 : 2;
            if (card_notice == 2) card_path[0] = 0;
            fprintf(stderr, card_notice == 1 ? "The memory card file could not be used: set aside, the game starts with an "
                                               "empty card.\n"
                                             : "The memory card file could not be used nor set aside: nothing is saved.\n");
        }
        card_hash = fnv(card, size, FNV_BASIS);
        return;
    }
    uint64_t h = fnv(card, size, FNV_BASIS);
    if (h == card_hash) return;
    wchar_t temporary[4100], folder[4096];
    /* datas/ and datas/saves/ beside the game, created on the first write. */
    wcsncpy(folder, card_path, 4095);
    folder[4095] = 0;
    for (int level = 0; level < 2; ++level) {
        wchar_t *slash = wcsrchr(folder, L'/');
        wchar_t *back = wcsrchr(folder, L'\\');
        if (back > slash) slash = back;
        if (!slash) break;
        *slash = 0;
    }
    rr_mkdir(folder);
    wcsncpy(folder, card_path, 4095);
    {
        wchar_t *slash = wcsrchr(folder, L'/'), *back = wcsrchr(folder, L'\\');
        if (back > slash) slash = back;
        if (slash) { *slash = 0; rr_mkdir(folder); }
    }
    swprintf(temporary, 4100, L"%ls.tmp", card_path);
    FILE *f = rr_fopen(temporary, L"wb");
    if (!f) return;
    int ok = fwrite(card, 1, size, f) == size;
    ok = (fclose(f) == 0) && ok;
    if (ok && rr_replace(temporary, card_path)) card_hash = h;
}

/* One frame with the pads of the script or of the window; 0 when the machine stopped. */
/* The Analog button of each player, held for a few frames after a press of its key or button (the pad reads the press). */
enum { ANALOG_PRESS_FRAMES = 6 };
static int analog_held[2];
void rr_psx_host_analog(int player) { if (player >= 0 && player < 2) analog_held[player] = ANALOG_PRESS_FRAMES; }

int rr_psx_host_frame(const uint16_t pads[2], const int16_t axes[2][4]) {
    unsigned words[2] = {pads[0], pads[1]};
    if (scripted) {
        while (script_pos < script_count && script[script_pos].frame <= frame) {
            script_pads[0] = (uint16_t)script[script_pos].pads[0];
            script_pads[1] = (uint16_t)script[script_pos].pads[1];
            script_pos++;
        }
        words[0] = script_pads[0];
        words[1] = script_pads[1];
    }
    rr_psx_pad(session, 0, words[0], scripted || !axes ? NULL : axes[0]);
    rr_psx_pad(session, 1, words[1], scripted || !axes ? NULL : axes[1]);
    for (int p = 0; p < 2; ++p) {
        rr_psx_analog_button(session, p, analog_held[p] > 0);
        if (analog_held[p] > 0) analog_held[p]--;
    }
    if (rr_psx_frame(session) != 0) { snprintf(fault, sizeof fault, "%s", rr_psx_error(session)); return 0; }
    frame++;
    frame_audio_count = rr_psx_audio(session, frame_audio, sizeof frame_audio / sizeof frame_audio[0] / 2) * 2;
    if (pcm_file) fwrite(frame_audio, sizeof frame_audio[0], frame_audio_count, pcm_file);
    audio_read = 0;
    if (diagnostics) {
        RrPsxFrameInfo info;
        rr_psx_frame_info(session, &info);
        image_hash = (image_hash ^ info.video) * FNV_PRIME;
        pcm_hash = (pcm_hash ^ info.pcm) * FNV_PRIME;
        samples += info.samples;
        for (size_t n = 0; n < frame_audio_count; n++) nonzero += frame_audio[n] != 0;
        if (info.nonblack) nonuniform_frames++;
        if (trace_file)
            fprintf(trace_file, "%u,%016llx,%016llx,%016llx,%u,%d,%dx%d,%016llx,%016llx\n", frame, (unsigned long long)info.ram,
                    (unsigned long long)info.video, (unsigned long long)info.pcm, info.samples, info.audible, info.width,
                    info.height, (unsigned long long)info.cpu, (unsigned long long)info.vram);
    }
    if (save_path && save_at == frame && !state_file(save_path, 0)) save_failed = 1;
    if (capture_dir && !(frame % capture_every)) {
        char path[4096];
        int w, h;
        const uint32_t *pixels = rr_psx_picture(session, &w, &h, NULL);
        snprintf(path, sizeof path, "%s/frame-%06u.ppm", capture_dir, frame);
        FILE *image = file_open(path, L"wb");
        if (!image) { snprintf(fault, sizeof fault, "picture capture failed"); return 0; }
        fprintf(image, "P6\n%d %d\n255\n", w, h);
        const int pitch = rr_psx_picture_pitch(session);
        for (int i = 0; i < w * h; i++) {
            const uint32_t pixel = pixels[(size_t)(i / w) * pitch + i % w];
            unsigned char rgb[3] = {(unsigned char)(pixel >> 16), (unsigned char)(pixel >> 8), (unsigned char)pixel};
            fwrite(rgb, 1, 3, image);
        }
        if (fclose(image)) { snprintf(fault, sizeof fault, "picture capture failed"); return 0; }
    }
    if ((!headless || card_option) && !(frame % 300)) card_sync(0);
    return 1;
}

size_t rr_psx_take_audio(int16_t *out, size_t capacity) {
    size_t count = frame_audio_count - audio_read;
    if (count > capacity) count = capacity & ~(size_t)1;
    memcpy(out, frame_audio + audio_read, count * sizeof *out);
    audio_read += count;
    return count;
}
unsigned rr_psx_frame_index(void) { return frame; }

static int open_session(void);
/* The renderer asked for (1.7.7): 1 the graphics card (Vulkan), 0 the CPU. A window starts with the card (the saved choice of F3 then
 * switches it at once); a headless run, a check of the conversion, draws with the CPU unless --gfx renderer=0 asks for the card. */
static int want_vulkan;
int rr_psx_host_reset(void) {
    card_sync(0);
    rr_psx_close(session);
    session = NULL;
    frame = 0; script_pos = 0; memset(script_pads, 0, sizeof script_pads);
    frame_audio_count = audio_read = 0;
    return open_session();
}

/* The renderer, switched in play: the machine taken as a quick state, the session opened again with the other renderer, the state
 * given back (nothing to keep before the first frame). 1 done (the card may still be refused: rr_psx_renderer_note), 0 the session
 * could not open again (`fault`). */
static int reopen_session(void);
int rr_psx_host_set_renderer(int vulkan) {
    if (!session || want_vulkan == (vulkan != 0)) return session != NULL;
    want_vulkan = vulkan != 0;
    return reopen_session();
}

/* The session opened again on the same renderer, the machine carried as a quick state: a change Beetle's renderer cannot take in
 * place (multisampling: the in-place rebuild keeps the programs of the old sample count, and the picture breaks at the game's
 * next display mode change). */
int rr_psx_host_reopen(void) { return session ? reopen_session() : 0; }

static char carried[64][2][64];   /* the core options a session opened again starts with */
static int carried_count;
static int reopen_session(void) {
    carried_count = rr_psx_option_count(session) < 64 ? rr_psx_option_count(session) : 64;
    for (int i = 0; i < carried_count; ++i) rr_psx_option_at(session, i, carried[i][0], carried[i][1]);
    size_t size = 0;
    uint8_t *state = frame ? rr16_state_capture(&size) : NULL;
    /* The last picture, shown again until the machine's next frame: a window draws while F3 holds the machine. */
    int w = 0, h = 0;
    const uint32_t *shown = rr_psx_picture(session, &w, &h, NULL);
    const int pitch = rr_psx_picture_pitch(session);
    uint32_t *last = w > 0 && h > 0 && pitch >= w ? (uint32_t *)malloc((size_t)w * h * sizeof(uint32_t)) : NULL;
    if (last) for (int y = 0; y < h; ++y) memcpy(last + (size_t)y * w, shown + (size_t)y * pitch, (size_t)w * sizeof(uint32_t));
    card_sync(0);
    rr_psx_close(session);
    session = NULL;
    const int opened = open_session();
    if (opened && state && !rr16_state_restore(state, size)) frame = 0;
    if (opened && last) rr_psx_keep_picture(session, last, w, h, w);
    free(last);
    free(state);
    return opened;
}

/* ------------------------------------------------------------ quick states (console16_state.c) */

enum { STATE_HEADER = 16 };
static void put32(uint8_t *p, uint32_t v) { for (unsigned n = 0; n < 4; n++) p[n] = (uint8_t)(v >> (8 * n)); }
static uint32_t get32(const uint8_t *p) { uint32_t v = 0; for (unsigned n = 0; n < 4; n++) v |= (uint32_t)p[n] << (8 * n); return v; }

bool rr16_state_ready(void) { return true; }   /* a frame ends with the CPU between instructions */
uint8_t *rr16_state_capture(size_t *size) {
    size_t machine = 0;
    uint8_t *payload = rr_psx_state_capture(session, &machine);
    if (!size || !payload || !machine || machine > (64u << 20)) { free(payload); return NULL; }
    uint8_t *data = (uint8_t *)malloc(STATE_HEADER + machine);
    if (!data) { free(payload); return NULL; }
    memcpy(data, "RRPSXST2", 8);
    put32(data + 8, frame);
    put32(data + 12, (uint32_t)machine);
    memcpy(data + STATE_HEADER, payload, machine);
    free(payload);
    *size = STATE_HEADER + machine;
    return data;
}
bool rr16_state_restore(const uint8_t *data, size_t size) {
    if (!data || size < STATE_HEADER || memcmp(data, "RRPSXST2", 8) || get32(data + 12) != size - STATE_HEADER) return false;
    if (rr_psx_state_restore(session, data + STATE_HEADER, size - STATE_HEADER) != 0) return false;
    frame = get32(data + 8);
    script_pos = 0; memset(script_pads, 0, sizeof script_pads);
    while (script_pos < script_count && script[script_pos].frame < frame) {
        script_pads[0] = (uint16_t)script[script_pos].pads[0];
        script_pads[1] = (uint16_t)script[script_pos].pads[1];
        script_pos++;
    }
    frame_audio_count = audio_read = 0;
    return true;
}

/* ------------------------------------------------------------ the session and the report */

static int self_path(char *out, size_t capacity) {
#ifdef _WIN32
    wchar_t wide[4096];
    DWORD n = GetModuleFileNameW(NULL, wide, 4096);
    return n > 0 && n < 4096 && rr_to_utf8(wide, out, capacity);
#else
    ssize_t n = readlink("/proc/self/exe", out, capacity - 1);
    if (n <= 0) return 0;
    out[n] = 0;
    return 1;
#endif
}

static int open_session(void) {
    char pack[4096];
    size_t bios_size = 0;
    const uint8_t *bios = (const uint8_t *)rr_resource(BIOS_RESOURCE, &bios_size);
    if (bios && bios_size != RR_PSX_BIOS_BYTES) bios = NULL;
    if (pack_override) snprintf(pack, sizeof pack, "%s", pack_override);
    else if (!self_path(pack, sizeof pack)) { snprintf(fault, sizeof fault, "cannot find this executable's path"); return 0; }
    RrPsxGame game = {pack, bios, NULL, 0, want_vulkan, (const char (*)[2][64])carried, carried_count};
    session = rr_psx_open(&game, fault, sizeof fault);
    carried_count = 0;
    if (!session) return 0;
    if (!headless || card_option) card_sync(1);
    return 1;
}

/* "RRPSX-INTERPRETED 1", then "<address> <word> <count>" (hex, hex, decimal) sorted by address, then the total of the
 * interpreted instructions ("total": those outside main RAM and the BIOS are the difference) and "full" if the table
 * filled up. */
static int ran_write(void) {
    FILE *f = file_open(interpreted_path, L"wb");
    if (!f) return 0;
    fprintf(f, "RRPSX-INTERPRETED 1\n");
    if (ran) {
        unsigned used = 0;
        for (unsigned n = 0; n < RAN_SLOTS; ++n) if (ran[n].count) ran[used++] = ran[n];
        qsort(ran, used, sizeof *ran, ran_order);
        for (unsigned n = 0; n < used; ++n)
            fprintf(f, "%08x %08x %llu\n", ran[n].address, ran[n].word, (unsigned long long)ran[n].count);
    }
    fprintf(f, "total %llu\n%s", (unsigned long long)(session ? rr_psx_interpreted(session) : 0), ran_full ? "full\n" : "");
    int okay = !ferror(f);
    return fclose(f) == 0 && okay;
}

static int report(void) {
    if (!report_path) return 1;
    FILE *f = file_open(report_path, L"wb");
    if (!f) return 0;
    char escaped[sizeof fault * 2];
    size_t e = 0;
    for (size_t n = 0; fault[n] && e + 2 < sizeof escaped; n++) {
        char c = fault[n];
        if (c == '"' || c == '\\') escaped[e++] = '\\';
        escaped[e++] = (c >= 32 && c < 127) ? c : '?';
    }
    escaped[e] = 0;
    size_t bios_size = 0;
    int player_bios = rr_resource(BIOS_RESOURCE, &bios_size) != NULL && bios_size == RR_PSX_BIOS_BYTES;
    fprintf(f, "{\"stage\":\"psx\",\"frames\":%u,\"interpreted_instructions\":%llu,\"native_instructions\":%llu,\"unrun_fetches\":%llu,\"pad_analog_mode\":[%d,%d],"
               "\"bios\":\"%s\",\"discs\":%d,\"image_hash\":\"%016llx\",\"pcm_hash\":\"%016llx\",\"pcm_samples\":%llu,"
               "\"nonzero_samples\":%llu,\"nonuniform_frames\":%u,\"pcm_rate\":%u,\"pcm_channels\":2,"
               "\"state_loaded\":%s,\"load_rejected\":%s,\"save_failed\":%s,\"fault\":\"%s\"}\n",
            frame, (unsigned long long)(session ? rr_psx_interpreted(session) : 0),
            (unsigned long long)(session ? rr_psx_native(session) : 0),
            (unsigned long long)(session ? rr_psx_unrun(session) : 0),
            session ? rr_psx_pad_analog_mode(session, 0) : -1, session ? rr_psx_pad_analog_mode(session, 1) : -1,
            player_bios ? "player" : "free",
            session ? rr_psx_disc_count(session) : 0, (unsigned long long)image_hash, (unsigned long long)pcm_hash,
            (unsigned long long)samples, (unsigned long long)nonzero, nonuniform_frames, RR_PSX_AUDIO_RATE,
            state_loaded ? "true" : "false", load_rejected ? "true" : "false", save_failed ? "true" : "false", escaped);
    int okay = !ferror(f);
    return fclose(f) == 0 && okay;
}

int rr_psx_input_check(RrPsxSession *s, FILE *out);   /* the adapter: every action reaches its own button of the console */
void rr_psx_gfx_defaults(void);
bool rr_psx_gfx_assign(const char *assignment, bool windowed);

static int execute(int argc, char **argv) {
    const char *gfx[8];
    int gfx_count = 0, input_check = 0;
    /* --gfx-at FRAME:KEY=INDEX (tests): a graphics row changed between two frames of a headless run, as F3 changes it in play. */
    unsigned gfx_at_frame[8];
    const char *gfx_at[8];
    int gfx_at_count = 0;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--headless")) headless = 1;
        else if (i + 1 < argc && !strcmp(argv[i], "--frames")) frames = atoi(argv[++i]);
        else if (i + 1 < argc && !strcmp(argv[i], "--report")) report_path = argv[++i];
        else if (i + 1 < argc && !strcmp(argv[i], "--save-state")) save_path = argv[++i];
        else if (i + 1 < argc && !strcmp(argv[i], "--save-at")) save_at = (unsigned)atoi(argv[++i]);
        else if (i + 1 < argc && !strcmp(argv[i], "--load-state")) load_path = argv[++i];
        else if (i + 1 < argc && !strcmp(argv[i], "--trace")) trace_path = argv[++i];
        else if (i + 1 < argc && !strcmp(argv[i], "--capture")) capture_dir = argv[++i];
        else if (i + 1 < argc && !strcmp(argv[i], "--capture-every")) capture_every = (unsigned)atoi(argv[++i]);
        else if (i + 1 < argc && !strcmp(argv[i], "--pack")) pack_override = argv[++i];
        else if (i + 1 < argc && !strcmp(argv[i], "--gfx") && gfx_count < 8) gfx[gfx_count++] = argv[++i];
        else if (i + 1 < argc && !strcmp(argv[i], "--gfx-at") && gfx_at_count < 8) {
            const char *spec = argv[++i], *colon = strchr(spec, ':');
            if (!colon) return 2;
            gfx_at_frame[gfx_at_count] = (unsigned)atoi(spec);
            gfx_at[gfx_at_count++] = colon + 1;
        }
        else if (i + 1 < argc && !strcmp(argv[i], "--pcm")) { if (!(pcm_file = file_open(argv[++i], L"wb"))) return 3; }
        else if (!strcmp(argv[i], "--input-check")) input_check = 1;
        else if (i + 1 < argc && !strcmp(argv[i], "--interpreted")) interpreted_path = argv[++i];
        else if (i + 1 < argc && !strcmp(argv[i], "--card")) {
            if (!rr_from_utf8(argv[++i], card_path, 4096)) return 2;
            card_option = 1;
        }
#ifdef RR_PSX_OBSERVE
        else if (i + 1 < argc && !strcmp(argv[i], "--observe")) observe_path = argv[++i];
#endif
        else if (i + 1 < argc && !strcmp(argv[i], "--script")) { if (!load_script(argv[++i])) return 2; }
        else return 2;
    }
    if (frames < 0 || frames > 1000000 || (headless && !frames && !input_check) || !capture_every) return 2;
    diagnostics = report_path || trace_path;
    want_vulkan = !headless && !input_check;
    if (!headless) rr_game_data_file(card_path, 4096, "saves", RR16_STATE_NAME, RR16_STATE_ROM, ".mcr");
    if (SDL_Init(SDL_INIT_TIMER)) return 3;
    if (!open_session()) { fprintf(stderr, "%s\n", fault[0] ? fault : "no PlayStation disc in this executable"); SDL_Quit(); return 3; }
    rr_feedback_start(!headless && !input_check);   /* runtime hints: play in the window only, never a conversion run */
    if (input_check) {
        const int failures = rr_psx_input_check(session, stdout);
        rr_psx_close(session);
        SDL_Quit();
        return failures ? 5 : 0;
    }
    /* The graphics options: the kit applies them in a window; a headless run applies the defaults (and --gfx) itself. */
    if (headless) rr_psx_gfx_defaults();
    for (int n = 0; n < gfx_count; ++n)
        if (!rr_psx_gfx_assign(gfx[n], !headless)) { fprintf(stderr, "unknown graphics option %s\n", gfx[n]); return 2; }
    if (trace_path) {
        if (!(trace_file = file_open(trace_path, L"wb"))) return 3;
        fprintf(trace_file, "frame,ram,image,pcm,samples,audible,size,cpu,vram\n");   /* format 2 (retrorecomp/psx_conversion.py) */
    }
    if (load_path) {
        state_loaded = state_file(load_path, 1);
        load_rejected = !state_loaded;
        if (!state_loaded) return 4;
    }
    int ran = 1, host_result = 0;
    if (headless) {
        static const uint16_t released[2];
        for (int n = 0; n < frames && ran; n++) {
            for (int k = 0; k < gfx_at_count; ++k)
                if (gfx_at_frame[k] == frame && !rr_psx_gfx_assign(gfx_at[k], false)) {
                    fprintf(stderr, "graphics option %s at frame %u failed%s%s\n", gfx_at[k], frame, fault[0] ? ": " : "", fault);
                    ran = 0;
                }
            if (ran) ran = rr_psx_host_frame(released, NULL);
        }
        if (card_option) card_sync(0);
    } else {
        host_result = rr_psx_sdl_main(RR_PSX_TITLE, 3);
        ran = !fault[0];
        card_sync(0);
    }
    if (save_path && !save_at && !state_file(save_path, 0)) save_failed = 1;
    if (!ran) fprintf(stderr, "%s\n", fault);
    int okay = report() && ran && !save_failed && !host_result;
#ifdef RR_PSX_OBSERVE
    if (observe_path) {
        FILE *f = file_open(observe_path, L"wb");
        if (!f || !rr_psx_observe_write(f)) okay = 0;
        if (f && fclose(f)) okay = 0;
    }
#endif
    if (trace_file && fclose(trace_file)) okay = 0;
    if (interpreted_path && !ran_write()) okay = 0;
    if (pcm_file && fclose(pcm_file)) okay = 0;
    hints_finish();
    rr_psx_close(session);
    SDL_Quit();
    return okay ? 0 : 3;
}

#ifdef _WIN32
int main(void) {
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX | SEM_NOOPENFILEERRORBOX);
    int argc = 0;
    wchar_t **wide_argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    char **argv = calloc((size_t)argc, sizeof *argv);
    if (!wide_argv || !argv) return 3;
    for (int i = 0; i < argc; i++) {
        int n = WideCharToMultiByte(CP_UTF8, 0, wide_argv[i], -1, NULL, 0, NULL, NULL);
        argv[i] = malloc(n);
        WideCharToMultiByte(CP_UTF8, 0, wide_argv[i], -1, argv[i], n, NULL, NULL);
    }
    int result = execute(argc, argv);
    if (result && argc == 1) SDL_ShowSimpleMessageBox(SDL_MESSAGEBOX_ERROR, "PlayStation", "Unable to start this PlayStation game.", NULL);
    for (int i = 0; i < argc; i++) free(argv[i]);
    free(argv);
    LocalFree(wide_argv);
    return result;
}
#else
int main(int argc, char **argv) {
    int result = execute(argc, argv);
    if (result && argc == 1) SDL_ShowSimpleMessageBox(SDL_MESSAGEBOX_ERROR, "PlayStation", "Unable to start this PlayStation game.", NULL);
    return result;
}
#endif
