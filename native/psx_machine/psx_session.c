/* Retro-Recomp PlayStation session (psx_session.h). Original Retro-Recomp code, MIT; linked with Beetle PSX (GPL-2.0), the
 * program it ends up in is GPL-2.0 as a whole.
 *
 * The pack. The files of the player's disc are served to the core under `rrdisc://<name>` by the virtual file system below; a
 * pack names them in a manifest stored at the end of a file (the game's executable, or a pack file of the conversion):
 *
 *     [...][manifest text][trailer: "RRPSXPK1", u64 manifest offset, u64 manifest size, little endian]
 *
 *     RRPSX-PACK 1
 *     source <n> self | <UTF-8 path>             a file the data comes from (self: the pack file itself)
 *     file <name> raw <source> <offset> <size>   bytes of a source
 *     file <name> pbp <source> <image> <data> <blocks> <size>
 *                                                raw sectors of one disc of a PS1 Classics EBOOT: `image` is the file offset of its
 *                                                PSISOIMG0000, `data` the file offset its block offsets count from, `blocks` the
 *                                                number of 16-sector blocks of its table (at image + 0x4000)
 *     disc <name>                                the sheet the core loads for each disc, in order
 *
 * A conversion's pack file names the player's files where they are (sources by path); an exported game names only itself. */
#include "psx_session.h"

#include <libretro.h>
#include <encodings/deflate.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#endif

/* Set by the session before retro_load_game; read by Beetle's BIOS loader (our anchored change of libretro.c). */
extern const unsigned char *rr_psx_bios_data;
/* Counted by Beetle's instruction fetch and by the game's native steps (our anchored changes of cpu.c). */
extern uint64_t rr_psx_fetched_count, rr_psx_native_count, rr_psx_unrun_count;

#define PACK_MAGIC "RRPSXPK1"
#define MAX_SOURCES 16
#define MAX_FILES 256
#define MAX_DISCS 8
#define PBP_BLOCK (16u * 2352u)
#define MAX_OPTIONS 48

typedef struct {
    char name[96];
    int pbp, source;
    uint64_t offset, size;          /* raw: bytes of the source; pbp: the image offset, and the decoded size */
    uint64_t data;
    uint32_t blocks;
    uint32_t *block_offset;         /* pbp: file offset of each block */
    uint32_t *block_size;
} PackFile;

struct RrPsxSession {
    char error[256];
    FILE *sources[MAX_SOURCES];
    PackFile files[MAX_FILES];
    int file_count;
    char discs[MAX_DISCS][96];
    int disc_count, disc;
    int swap_frames, swap_target;   /* a disc change in progress */
    struct { char key[64], value[64]; } options[MAX_OPTIONS];
    int option_count, options_changed;
    unsigned pad[2];
    int16_t sticks[2][4];
    uint16_t rumble[2][2];
    uint32_t picture[RR_PSX_MAX_WIDTH * RR_PSX_MAX_HEIGHT];
    int width, height;
    double aspect, fps;
    int16_t audio[2 * 8192];
    size_t audio_frames;
    uint64_t frame;
    struct retro_disk_control_callback disk;
    int has_disk;
    uint8_t *bios;
};

static RrPsxSession *g;                       /* Beetle keeps its state in globals: one session per process */

static FILE *open_utf8(const char *path) {
#ifdef _WIN32
    wchar_t wide[4096];
    if (!MultiByteToWideChar(CP_UTF8, 0, path, -1, wide, 4096)) return NULL;
    return _wfopen(wide, L"rb");
#else
    return fopen(path, "rb");
#endif
}

static int seek64(FILE *f, uint64_t offset) {
#ifdef _WIN32
    return _fseeki64(f, (long long)offset, SEEK_SET);
#else
    return fseeko(f, (off_t)offset, SEEK_SET);
#endif
}

static int read_at(FILE *f, uint64_t offset, void *buffer, size_t length) {
    return seek64(f, offset) == 0 && fread(buffer, 1, length, f) == length;
}

static void fail(RrPsxSession *s, const char *format, ...) {
    va_list args;
    va_start(args, format);
    vsnprintf(s->error, sizeof s->error, format, args);
    va_end(args);
}

/* ---- the pack -------------------------------------------------------------------------------------------------------- */

static int load_pbp_table(RrPsxSession *s, PackFile *file) {
    FILE *f = s->sources[file->source];
    uint8_t *table = (uint8_t *)malloc((size_t)file->blocks * 32u);
    if (!table) return 0;
    file->block_offset = (uint32_t *)malloc(file->blocks * sizeof(uint32_t));
    file->block_size = (uint32_t *)malloc(file->blocks * sizeof(uint32_t));
    if (!file->block_offset || !file->block_size || !read_at(f, file->offset + 0x4000u, table, (size_t)file->blocks * 32u)) {
        free(table);
        return 0;
    }
    for (uint32_t i = 0; i < file->blocks; ++i) {
        const uint8_t *e = table + (size_t)i * 32u;
        file->block_offset[i] = (uint32_t)e[0] | (uint32_t)e[1] << 8 | (uint32_t)e[2] << 16 | (uint32_t)e[3] << 24;
        file->block_size[i] = (uint32_t)e[4] | (uint32_t)e[5] << 8;
        if (!file->block_size[i] || file->block_size[i] > PBP_BLOCK) { free(table); return 0; }
    }
    free(table);
    return 1;
}

static int open_pack(RrPsxSession *s, const char *path) {
    FILE *f = open_utf8(path);
    uint8_t trailer[24];
    if (!f) { fail(s, "cannot open %s", path); return 0; }
    if (fseek(f, -24, SEEK_END) != 0 || fread(trailer, 1, 24, f) != 24 || memcmp(trailer, PACK_MAGIC, 8) != 0) {
        fclose(f);
        fail(s, "%s holds no PlayStation pack", path);
        return 0;
    }
    uint64_t offset = 0, size = 0;
    for (int i = 7; i >= 0; --i) { offset = offset << 8 | trailer[8 + i]; size = size << 8 | trailer[16 + i]; }
    if (size == 0 || size > (1u << 20)) { fclose(f); fail(s, "bad pack manifest"); return 0; }
    char *text = (char *)malloc((size_t)size + 1);
    if (!text || !read_at(f, offset, text, (size_t)size)) { free(text); fclose(f); fail(s, "cannot read the pack manifest"); return 0; }
    text[size] = 0;
    s->sources[0] = f;   /* "self" is always source 0 */
    int ok = strncmp(text, "RRPSX-PACK 1\n", 13) == 0;
    for (char *line = strtok(text, "\n"); ok && line; line = strtok(NULL, "\n")) {
        int n = 0;
        if (strncmp(line, "source ", 7) == 0) {
            char *name;
            int index = (int)strtol(line + 7, &name, 10);
            while (*name == ' ') ++name;
            if (index <= 0 || index >= MAX_SOURCES) { ok = 0; break; }
            if (strcmp(name, "self") == 0) continue;
            if (!(s->sources[index] = open_utf8(name))) { fail(s, "cannot open %s", name); ok = 0; }
        } else if (strncmp(line, "file ", 5) == 0) {
            PackFile *file;
            char kind[8];
            unsigned long long a, b, c, d;
            int source;
            if (s->file_count >= MAX_FILES) { ok = 0; break; }
            file = &s->files[s->file_count];
            memset(file, 0, sizeof *file);
            if (sscanf(line + 5, "%95s %7s %d %llu %llu%n", file->name, kind, &source, &a, &b, &n) < 5) { ok = 0; break; }
            if (source < 0 || source >= MAX_SOURCES || !s->sources[source]) { ok = 0; break; }
            file->source = source;
            file->offset = a;
            if (strcmp(kind, "raw") == 0) {
                file->size = b;
            } else if (strcmp(kind, "pbp") == 0 && sscanf(line + 5 + n, "%llu %llu", &c, &d) == 2) {
                file->pbp = 1;
                file->data = b;
                file->blocks = (uint32_t)c;
                file->size = d;
                if (!file->blocks || file->size > (uint64_t)file->blocks * PBP_BLOCK || !load_pbp_table(s, file)) {
                    fail(s, "bad EBOOT block table in the pack");
                    ok = 0;
                    break;
                }
            } else { ok = 0; break; }
            ++s->file_count;
        } else if (strncmp(line, "disc ", 5) == 0) {
            if (s->disc_count >= MAX_DISCS) { ok = 0; break; }
            snprintf(s->discs[s->disc_count++], sizeof s->discs[0], "%s", line + 5);
        }
    }
    free(text);
    if (!ok || !s->disc_count) { if (!s->error[0]) fail(s, "bad pack manifest"); return 0; }
    return 1;
}

static PackFile *find_file(RrPsxSession *s, const char *path) {
    const char *name = path;
    if (strncmp(path, "rrdisc:", 7) != 0) return NULL;
    for (const char *p = path; *p; ++p) if (*p == '/' || *p == '\\' || *p == ':') name = p + 1;
    for (int i = 0; i < s->file_count; ++i)
        if (strcmp(s->files[i].name, name) == 0) return &s->files[i];
    return NULL;
}

/* ---- the virtual file system the core reads its disc through ----------------------------------------------------------- */

struct retro_vfs_file_handle {
    PackFile *file;
    char path[192];                 /* the path it was opened with: the core reopens files by it */
    uint64_t pos;
    int32_t cached;                 /* pbp: the block in `block`, -1 none */
    uint8_t *block;
    void *inflater;
};

static int64_t pbp_read(struct retro_vfs_file_handle *h, uint8_t *out, uint64_t length) {
    RrPsxSession *s = g;
    PackFile *file = h->file;
    uint64_t done = 0;
    while (done < length) {
        uint64_t pos = h->pos + done;
        uint32_t index = (uint32_t)(pos / PBP_BLOCK), within = (uint32_t)(pos % PBP_BLOCK);
        if (index >= file->blocks) break;
        if (h->cached != (int32_t)index) {
            uint32_t stored = file->block_size[index];
            uint8_t *in = (uint8_t *)malloc(stored);
            if (!in || !read_at(s->sources[file->source], file->data + file->block_offset[index], in, stored)) { free(in); return -1; }
            if (stored == PBP_BLOCK) {
                memcpy(h->block, in, PBP_BLOCK);
            } else {
                size_t got = 0, wrote = 0;
                if (!h->inflater && !(h->inflater = rinflate_new(-15))) { free(in); return -1; }
                rinflate_reset(h->inflater, -15);
                rinflate_set_in(h->inflater, in, stored);
                rinflate_set_out(h->inflater, h->block, PBP_BLOCK);
                int code = rinflate_process(h->inflater, &got, &wrote);
                if (code == RDEFLATE_PROCESS_ERROR) { free(in); return -1; }
                if (wrote < PBP_BLOCK) memset(h->block + wrote, 0, PBP_BLOCK - wrote);
            }
            free(in);
            h->cached = (int32_t)index;
        }
        uint64_t n = PBP_BLOCK - within;
        if (n > length - done) n = length - done;
        memcpy(out + done, h->block + within, (size_t)n);
        done += n;
    }
    return (int64_t)done;
}

static const char *RETRO_CALLCONV vfs_get_path(struct retro_vfs_file_handle *h) { return h ? h->path : NULL; }

static struct retro_vfs_file_handle *RETRO_CALLCONV vfs_open(const char *path, unsigned mode, unsigned hints) {
    (void)hints;
    PackFile *file = g ? find_file(g, path) : NULL;
    if (!file || (mode & RETRO_VFS_FILE_ACCESS_WRITE)) return NULL;
    struct retro_vfs_file_handle *h = (struct retro_vfs_file_handle *)calloc(1, sizeof *h);
    if (!h) return NULL;
    h->file = file;
    snprintf(h->path, sizeof h->path, "%s", path);
    h->cached = -1;
    if (file->pbp && !(h->block = (uint8_t *)malloc(PBP_BLOCK))) { free(h); return NULL; }
    return h;
}

static int RETRO_CALLCONV vfs_close(struct retro_vfs_file_handle *h) {
    if (!h) return -1;
    if (h->inflater) rinflate_free(h->inflater);
    free(h->block);
    free(h);
    return 0;
}

static int64_t RETRO_CALLCONV vfs_size(struct retro_vfs_file_handle *h) { return h ? (int64_t)h->file->size : -1; }
static int64_t RETRO_CALLCONV vfs_tell(struct retro_vfs_file_handle *h) { return h ? (int64_t)h->pos : -1; }

static int64_t RETRO_CALLCONV vfs_seek(struct retro_vfs_file_handle *h, int64_t offset, int whence) {
    int64_t base = whence == RETRO_VFS_SEEK_POSITION_CURRENT ? (int64_t)h->pos
                 : whence == RETRO_VFS_SEEK_POSITION_END ? (int64_t)h->file->size : 0;
    if (base + offset < 0) return -1;
    h->pos = (uint64_t)(base + offset);
    return (int64_t)h->pos;
}

static int64_t RETRO_CALLCONV vfs_read(struct retro_vfs_file_handle *h, void *buffer, uint64_t length) {
    if (!h) return -1;
    if (h->pos >= h->file->size) return 0;
    if (length > h->file->size - h->pos) length = h->file->size - h->pos;
    int64_t got;
    if (h->file->pbp) {
        got = pbp_read(h, (uint8_t *)buffer, length);
    } else {
        FILE *f = g->sources[h->file->source];
        if (seek64(f, h->file->offset + h->pos) != 0) return -1;
        got = (int64_t)fread(buffer, 1, (size_t)length, f);
    }
    if (got > 0) h->pos += (uint64_t)got;
    return got;
}

static int64_t RETRO_CALLCONV vfs_write(struct retro_vfs_file_handle *h, const void *b, uint64_t n) { (void)h; (void)b; (void)n; return -1; }
static int RETRO_CALLCONV vfs_flush(struct retro_vfs_file_handle *h) { (void)h; return 0; }
static int RETRO_CALLCONV vfs_remove(const char *path) { (void)path; return -1; }
static int RETRO_CALLCONV vfs_rename(const char *a, const char *b) { (void)a; (void)b; return -1; }
static int64_t RETRO_CALLCONV vfs_truncate(struct retro_vfs_file_handle *h, int64_t n) { (void)h; (void)n; return -1; }

static int RETRO_CALLCONV vfs_stat(const char *path, int32_t *size) {
    PackFile *file = g ? find_file(g, path) : NULL;
    if (!file) return 0;
    if (size) *size = (int32_t)(file->size > 0x7fffffff ? 0x7fffffff : file->size);
    return RETRO_VFS_STAT_IS_VALID;
}

static int RETRO_CALLCONV vfs_mkdir(const char *dir) { (void)dir; return -1; }
static struct retro_vfs_dir_handle *RETRO_CALLCONV vfs_opendir(const char *dir, bool hidden) { (void)dir; (void)hidden; return NULL; }
static bool RETRO_CALLCONV vfs_readdir(struct retro_vfs_dir_handle *d) { (void)d; return false; }
static const char *RETRO_CALLCONV vfs_dirent_name(struct retro_vfs_dir_handle *d) { (void)d; return NULL; }
static bool RETRO_CALLCONV vfs_dirent_is_dir(struct retro_vfs_dir_handle *d) { (void)d; return false; }
static int RETRO_CALLCONV vfs_closedir(struct retro_vfs_dir_handle *d) { (void)d; return -1; }

static struct retro_vfs_interface vfs_iface = {
    vfs_get_path, vfs_open, vfs_close, vfs_size, vfs_tell, vfs_seek, vfs_read, vfs_write, vfs_flush, vfs_remove, vfs_rename,
    vfs_truncate, vfs_stat, vfs_mkdir, vfs_opendir, vfs_readdir, vfs_dirent_name, vfs_dirent_is_dir, vfs_closedir
};

/* ---- the libretro frontend --------------------------------------------------------------------------------------------- */

/* The core options this session sets; every other option keeps the core's default. Deterministic choices only: the disc is
 * read synchronously at the console's speed, the memory card of slot 1 is the core's own buffer, slot 2 is empty, the real
 * boot runs, no frame is duplicated, the software renderer draws at the console's resolution. */
static const char *const DEFAULTS[][2] = {
    {"beetle_psx_cd_access_method", "sync"},
    {"beetle_psx_cd_fastload", "2x(native)"},
    {"beetle_psx_use_mednafen_memcard0_method", "libretro"},
    {"beetle_psx_enable_memcard1", "disabled"},
    {"beetle_psx_skip_bios", "disabled"},
    {"beetle_psx_internal_resolution", "1x(native)"},
    {"beetle_psx_frame_duping", "disabled"},
    {"beetle_psx_cpu_dynarec", "disabled"},
    {"beetle_psx_display_internal_fps", "disabled"},
};

static void set_option(RrPsxSession *s, const char *key, const char *value) {
    for (int i = 0; i < s->option_count; ++i)
        if (strcmp(s->options[i].key, key) == 0) {
            if (strcmp(s->options[i].value, value) != 0) s->options_changed = 1;
            snprintf(s->options[i].value, sizeof s->options[i].value, "%s", value);
            return;
        }
    if (s->option_count < MAX_OPTIONS) {
        snprintf(s->options[s->option_count].key, sizeof s->options[0].key, "%s", key);
        snprintf(s->options[s->option_count].value, sizeof s->options[0].value, "%s", value);
        ++s->option_count;
        s->options_changed = 1;
    }
}

static void RETRO_CALLCONV log_quiet(enum retro_log_level level, const char *format, ...) {
    if (level < RETRO_LOG_WARN || !getenv("RR_PSX_LOG")) return;
    va_list args;
    va_start(args, format);
    vfprintf(stderr, format, args);
    va_end(args);
}

static bool RETRO_CALLCONV rumble_state(unsigned port, enum retro_rumble_effect effect, uint16_t strength) {
    if (!g || port > 1) return false;
    g->rumble[port][effect == RETRO_RUMBLE_STRONG ? 0 : 1] = strength;
    return true;
}

static bool RETRO_CALLCONV environment(unsigned cmd, void *data) {
    RrPsxSession *s = g;
    switch (cmd) {
    case RETRO_ENVIRONMENT_GET_VARIABLE: {
        struct retro_variable *var = (struct retro_variable *)data;
        var->value = NULL;
        for (int i = 0; s && i < s->option_count; ++i)
            if (strcmp(s->options[i].key, var->key) == 0) { var->value = s->options[i].value; return true; }
        return false;
    }
    case RETRO_ENVIRONMENT_GET_VARIABLE_UPDATE:
        *(bool *)data = s && s->options_changed;
        if (s) s->options_changed = 0;
        return true;
    case RETRO_ENVIRONMENT_SET_PIXEL_FORMAT:
        return *(const enum retro_pixel_format *)data == RETRO_PIXEL_FORMAT_XRGB8888;
    case RETRO_ENVIRONMENT_GET_LOG_INTERFACE:
        ((struct retro_log_callback *)data)->log = log_quiet;
        return true;
    case RETRO_ENVIRONMENT_GET_CAN_DUPE:
        *(bool *)data = false;
        return true;
    case RETRO_ENVIRONMENT_GET_INPUT_BITMASKS:
        return true;
    case RETRO_ENVIRONMENT_GET_RUMBLE_INTERFACE:
        ((struct retro_rumble_interface *)data)->set_rumble_state = rumble_state;
        return true;
    case RETRO_ENVIRONMENT_GET_AUDIO_VIDEO_ENABLE:
        *(int *)data = 3;
        return true;
    case RETRO_ENVIRONMENT_GET_VFS_INTERFACE: {
        struct retro_vfs_interface_info *info = (struct retro_vfs_interface_info *)data;
        if (info->required_interface_version > 3) return false;
        info->required_interface_version = 3;
        info->iface = &vfs_iface;
        return true;
    }
    case RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY:
    case RETRO_ENVIRONMENT_GET_SAVE_DIRECTORY:
        /* A folder that holds nothing: the BIOS comes from memory, the memory card from rr_psx_card. */
        *(const char **)data = "rrsys://";
        return true;
    case RETRO_ENVIRONMENT_SET_DISK_CONTROL_INTERFACE:
        if (s) { s->disk = *(const struct retro_disk_control_callback *)data; s->has_disk = 1; }
        return true;
    case RETRO_ENVIRONMENT_GET_DISK_CONTROL_INTERFACE_VERSION:
        *(unsigned *)data = 0;   /* the first interface only */
        return true;
    case RETRO_ENVIRONMENT_SET_SYSTEM_AV_INFO: {
        const struct retro_system_av_info *av = (const struct retro_system_av_info *)data;
        if (s) { s->fps = av->timing.fps; s->aspect = av->geometry.aspect_ratio; }
        return true;
    }
    case RETRO_ENVIRONMENT_SET_GEOMETRY: {
        const struct retro_game_geometry *geometry = (const struct retro_game_geometry *)data;
        if (s) s->aspect = geometry->aspect_ratio;
        return true;
    }
    case RETRO_ENVIRONMENT_SET_CORE_OPTIONS_DISPLAY:
    case RETRO_ENVIRONMENT_SET_CORE_OPTIONS_UPDATE_DISPLAY_CALLBACK:
    case RETRO_ENVIRONMENT_SET_INPUT_DESCRIPTORS:
    case RETRO_ENVIRONMENT_SET_CONTROLLER_INFO:
    case RETRO_ENVIRONMENT_SET_MEMORY_MAPS:
    case RETRO_ENVIRONMENT_SET_SERIALIZATION_QUIRKS:
    case RETRO_ENVIRONMENT_SET_PERFORMANCE_LEVEL:
    case RETRO_ENVIRONMENT_SET_MESSAGE:
    case RETRO_ENVIRONMENT_SET_MESSAGE_EXT:
        return true;
    default:
        return false;
    }
}

static void RETRO_CALLCONV video_refresh(const void *data, unsigned width, unsigned height, size_t pitch) {
    RrPsxSession *s = g;
    if (!s || !data) return;   /* a duplicated frame keeps the last picture */
    if (width > RR_PSX_MAX_WIDTH) width = RR_PSX_MAX_WIDTH;
    if (height > RR_PSX_MAX_HEIGHT) height = RR_PSX_MAX_HEIGHT;
    for (unsigned y = 0; y < height; ++y) {
        const uint32_t *row = (const uint32_t *)((const uint8_t *)data + (size_t)y * pitch);
        uint32_t *out = s->picture + (size_t)y * width;
        for (unsigned x = 0; x < width; ++x) out[x] = row[x] & 0x00ffffffu;
    }
    s->width = (int)width;
    s->height = (int)height;
}

static size_t RETRO_CALLCONV audio_batch(const int16_t *data, size_t frames) {
    RrPsxSession *s = g;
    if (!s) return frames;
    size_t room = sizeof s->audio / sizeof s->audio[0] / 2 - s->audio_frames;
    size_t n = frames < room ? frames : room;
    memcpy(s->audio + s->audio_frames * 2, data, n * 2 * sizeof(int16_t));
    s->audio_frames += n;
    return frames;
}

static void RETRO_CALLCONV audio_sample(int16_t left, int16_t right) {
    int16_t pair[2] = {left, right};
    audio_batch(pair, 1);
}

static void RETRO_CALLCONV input_poll(void) {}

static int16_t RETRO_CALLCONV input_state(unsigned port, unsigned device, unsigned index, unsigned id) {
    RrPsxSession *s = g;
    if (!s || port > 1) return 0;
    if (device == RETRO_DEVICE_JOYPAD) {
        if (id == RETRO_DEVICE_ID_JOYPAD_MASK) return (int16_t)s->pad[port];
        return (int16_t)((s->pad[port] >> id) & 1u);
    }
    if (device == RETRO_DEVICE_ANALOG && index <= RETRO_DEVICE_INDEX_ANALOG_RIGHT && id <= RETRO_DEVICE_ID_ANALOG_Y)
        return s->sticks[port][index * 2 + id];
    return 0;
}

/* ---- the session ------------------------------------------------------------------------------------------------------ */

RrPsxSession *rr_psx_open(const RrPsxGame *game, char *error, size_t error_size) {
    if (g) { if (error) snprintf(error, error_size, "a PlayStation session is already open"); return NULL; }
    RrPsxSession *s = (RrPsxSession *)calloc(1, sizeof *s);
    if (!s) { if (error) snprintf(error, error_size, "out of memory"); return NULL; }
    g = s;
    s->aspect = 4.0 / 3.0;
    s->fps = 59.94;
    for (size_t i = 0; i < sizeof DEFAULTS / sizeof DEFAULTS[0]; ++i) set_option(s, DEFAULTS[i][0], DEFAULTS[i][1]);
    s->options_changed = 0;
    if (!open_pack(s, game->pack)) goto failed;
    s->disc = game->disc >= 0 && game->disc < s->disc_count ? game->disc : 0;
    if (game->bios) {
        if (!(s->bios = (uint8_t *)malloc(RR_PSX_BIOS_BYTES))) { fail(s, "out of memory"); goto failed; }
        memcpy(s->bios, game->bios, RR_PSX_BIOS_BYTES);
    }
    rr_psx_bios_data = s->bios;
    retro_set_environment(environment);
    retro_set_video_refresh(video_refresh);
    retro_set_audio_sample(audio_sample);
    retro_set_audio_sample_batch(audio_batch);
    retro_set_input_poll(input_poll);
    retro_set_input_state(input_state);
    retro_init();
    {
        char path[128];
        struct retro_game_info info;
        snprintf(path, sizeof path, "rrdisc://pack/%s", s->discs[s->disc]);
        memset(&info, 0, sizeof info);
        info.path = path;
        if (!retro_load_game(&info)) { fail(s, "the core could not load %s", s->discs[s->disc]); retro_deinit(); goto failed; }
    }
    retro_set_controller_port_device(0, RETRO_DEVICE_SUBCLASS(RETRO_DEVICE_ANALOG, 1));   /* DualShock */
    retro_set_controller_port_device(1, RETRO_DEVICE_SUBCLASS(RETRO_DEVICE_ANALOG, 1));
    {
        struct retro_system_av_info av;
        retro_get_system_av_info(&av);
        s->fps = av.timing.fps;
        s->aspect = av.geometry.aspect_ratio;
    }
    return s;
failed:
    if (error) snprintf(error, error_size, "%s", s->error[0] ? s->error : "cannot open the game");
    rr_psx_close(s);
    return NULL;
}

void rr_psx_close(RrPsxSession *s) {
    if (!s) return;
    if (g == s && s->disc_count && s->width) { retro_unload_game(); retro_deinit(); }
    for (int i = 0; i < s->file_count; ++i) { free(s->files[i].block_offset); free(s->files[i].block_size); }
    for (int i = 0; i < MAX_SOURCES; ++i) if (s->sources[i]) fclose(s->sources[i]);
    rr_psx_bios_data = NULL;
    free(s->bios);
    if (g == s) g = NULL;
    free(s);
}

void rr_psx_pad(RrPsxSession *s, int player, unsigned bits, const int16_t sticks[4]) {
    if (player < 0 || player > 1) return;
    s->pad[player] = bits & 0xffffu;
    for (int i = 0; i < 4; ++i) s->sticks[player][i] = sticks ? sticks[i] : 0;
}

int rr_psx_frame(RrPsxSession *s) {
    s->audio_frames = 0;
    if (s->swap_frames) {
        /* A disc change: the lid is open for a few frames, the disc is replaced, then the lid closes. */
        if (--s->swap_frames == 30 && s->has_disk) s->disk.set_image_index((unsigned)s->swap_target);
        if (s->swap_frames == 0 && s->has_disk) { s->disk.set_eject_state(false); s->disc = s->swap_target; }
    }
    retro_run();
    ++s->frame;
    return 0;
}

const char *rr_psx_error(const RrPsxSession *s) { return s->error; }

const uint32_t *rr_psx_picture(const RrPsxSession *s, int *width, int *height, double *aspect) {
    if (width) *width = s->width;
    if (height) *height = s->height;
    if (aspect) *aspect = s->aspect;
    return s->picture;
}

size_t rr_psx_audio(RrPsxSession *s, int16_t *pcm, size_t capacity) {
    size_t n = s->audio_frames < capacity ? s->audio_frames : capacity;
    memcpy(pcm, s->audio, n * 2 * sizeof(int16_t));
    return n;
}

double rr_psx_fps(const RrPsxSession *s) { return s->fps; }

int rr_psx_rumble(const RrPsxSession *s, int player, uint16_t *low, uint16_t *high) {
    if (player < 0 || player > 1) return 0;
    *low = s->rumble[player][0];
    *high = s->rumble[player][1];
    return *low || *high;
}

int rr_psx_disc_count(const RrPsxSession *s) { return s->disc_count; }
int rr_psx_disc_current(const RrPsxSession *s) { return s->disc; }

int rr_psx_disc_select(RrPsxSession *s, int index) {
    if (!s->has_disk || index < 0 || index >= s->disc_count || index == s->disc || s->swap_frames) return 0;
    s->disk.set_eject_state(true);
    s->swap_target = index;
    s->swap_frames = 60;
    return 1;
}

int rr_psx_option(RrPsxSession *s, const char *key, const char *value) {
    char full[64];
    snprintf(full, sizeof full, "beetle_psx_%s", key);
    set_option(s, full, value);
    return 1;
}

static uint64_t fnv(const void *data, size_t size, uint64_t h) {
    const uint8_t *p = (const uint8_t *)data;
    for (size_t i = 0; i < size; ++i) { h ^= p[i]; h *= 0x100000001b3ull; }
    return h;
}

void rr_psx_frame_info(const RrPsxSession *s, RrPsxFrameInfo *info) {
    const uint64_t basis = 0xcbf29ce484222325ull;
    memset(info, 0, sizeof *info);
    info->frame = s->frame;
    info->width = s->width;
    info->height = s->height;
    info->video = fnv(s->picture, (size_t)s->width * (size_t)s->height * 4u, basis);
    info->pcm = fnv(s->audio, s->audio_frames * 4u, basis);
    info->samples = (uint32_t)s->audio_frames;
    const void *ram = retro_get_memory_data(RETRO_MEMORY_SYSTEM_RAM);
    info->ram = ram ? fnv(ram, RR_PSX_RAM_BYTES, basis) : 0;
    for (int i = 0; i < s->width * s->height; ++i) if (s->picture[i]) { info->nonblack = 1; break; }
    for (size_t i = 0; i < s->audio_frames * 2; ++i) if (s->audio[i] > 64 || s->audio[i] < -64) { info->audible = 1; break; }
}

uint8_t *rr_psx_card(RrPsxSession *s, size_t *size) {
    (void)s;
    if (size) *size = retro_get_memory_size(RETRO_MEMORY_SAVE_RAM);
    return (uint8_t *)retro_get_memory_data(RETRO_MEMORY_SAVE_RAM);
}

uint64_t rr_psx_interpreted(const RrPsxSession *s) {
    (void)s;
    return rr_psx_fetched_count - rr_psx_native_count - rr_psx_unrun_count;
}
uint64_t rr_psx_native(const RrPsxSession *s) { (void)s; return rr_psx_native_count; }
uint64_t rr_psx_unrun(const RrPsxSession *s) { (void)s; return rr_psx_unrun_count; }

uint8_t *rr_psx_state_capture(RrPsxSession *s, size_t *size) {
    (void)s;
    size_t n = retro_serialize_size();
    uint8_t *data = n ? (uint8_t *)malloc(n + 4) : NULL;
    if (!data || !retro_serialize(data + 4, n)) { free(data); return NULL; }
    data[0] = (uint8_t)s->disc; data[1] = data[2] = data[3] = 0;
    if (size) *size = n + 4;
    return data;
}

int rr_psx_state_restore(RrPsxSession *s, const uint8_t *data, size_t size) {
    if (!data || size < 5 || size - 4 != retro_serialize_size() || data[0] >= s->disc_count) return 3;
    if (!retro_unserialize(data + 4, size - 4)) return 3;
    s->disc = data[0];
    s->audio_frames = 0;
    return 0;
}

/* ---- quick states ----------------------------------------------------------------------------------------------------- */

#define STATE_MAGIC "RRPSXST1"

static FILE *open_write(const char *path) {
#ifdef _WIN32
    wchar_t wide[4096];
    if (!MultiByteToWideChar(CP_UTF8, 0, path, -1, wide, 4096)) return NULL;
    return _wfopen(wide, L"wb");
#else
    return fopen(path, "wb");
#endif
}

int rr_psx_state_save(RrPsxSession *s, const char *path, const char *abi) {
    size_t size = retro_serialize_size();
    uint8_t *data = (uint8_t *)malloc(size ? size : 1);
    if (!data || !retro_serialize(data, size)) { free(data); return 3; }
    FILE *f = open_write(path);
    if (!f) { free(data); return 4; }
    char head[80] = {0};
    snprintf(head, sizeof head, "%s %.64s", STATE_MAGIC, abi ? abi : "");
    uint8_t meta[12];
    uint64_t length = size;
    uint32_t disc = (uint32_t)s->disc;
    for (int i = 0; i < 8; ++i) meta[i] = (uint8_t)(length >> (8 * i));
    for (int i = 0; i < 4; ++i) meta[8 + i] = (uint8_t)(disc >> (8 * i));
    int ok = fwrite(head, 1, sizeof head, f) == sizeof head && fwrite(meta, 1, sizeof meta, f) == sizeof meta
          && fwrite(data, 1, size, f) == size;
    ok = (fclose(f) == 0) && ok;
    free(data);
    return ok ? 0 : 4;
}

int rr_psx_state_load(RrPsxSession *s, const char *path, const char *abi) {
    FILE *f = open_utf8(path);
    if (!f) return 1;
    char head[80], want[80] = {0};
    uint8_t meta[12];
    snprintf(want, sizeof want, "%s %.64s", STATE_MAGIC, abi ? abi : "");
    if (fread(head, 1, sizeof head, f) != sizeof head || fread(meta, 1, sizeof meta, f) != sizeof meta) { fclose(f); return 3; }
    if (memcmp(head, STATE_MAGIC, 8) != 0) { fclose(f); return 3; }
    if (memcmp(head, want, sizeof head) != 0) { fclose(f); return 2; }
    uint64_t length = 0;
    for (int i = 7; i >= 0; --i) length = length << 8 | meta[i];
    uint32_t disc = (uint32_t)meta[8] | (uint32_t)meta[9] << 8 | (uint32_t)meta[10] << 16 | (uint32_t)meta[11] << 24;
    if (length != retro_serialize_size() || (int)disc >= s->disc_count) { fclose(f); return 2; }
    uint8_t *data = (uint8_t *)malloc((size_t)length);
    if (!data || fread(data, 1, (size_t)length, f) != length) { free(data); fclose(f); return 3; }
    fclose(f);
    int ok = retro_unserialize(data, (size_t)length);
    free(data);
    if (ok) s->disc = (int)disc;
    return ok ? 0 : 3;
}
