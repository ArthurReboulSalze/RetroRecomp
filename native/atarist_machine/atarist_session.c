/* Retro-Recomp Atari ST session (atarist_session.h). Original Retro-Recomp code, MIT; linked with Hatari (GPL-2.0).
 *
 * The session is the libretro frontend of Hatari's core (src/retro of the pinned Hatari, adapted by retrorecomp/atarist_hatari.py):
 * every environment call is answered here, from fixed values, so the machine never sees the host's configuration, folders or
 * clock. Files go through a libretro virtual file system that knows only this session's files, all in memory: the TOS image
 * ("tos.img" in the system folder), the floppy images, a playlist when the game has several disks, and the scratch file Hatari
 * writes a state to. Any other path does not exist for the machine. */
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <libretro.h>

#include "main.h"
#include "configuration.h"
#include "m68000.h"
#include "stMemory.h"
#include "video.h"

#include "atarist_session.h"

/* ------------------------------------------------------------------ Hatari's libretro entry points (src/retro/main_retro.c) */
RETRO_API void retro_set_environment(retro_environment_t cb);
RETRO_API void retro_set_video_refresh(retro_video_refresh_t cb);
RETRO_API void retro_set_audio_sample(retro_audio_sample_t cb);
RETRO_API void retro_set_audio_sample_batch(retro_audio_sample_batch_t cb);
RETRO_API void retro_set_input_poll(retro_input_poll_t cb);
RETRO_API void retro_set_input_state(retro_input_state_t cb);
RETRO_API void retro_init(void);
RETRO_API bool retro_load_game(const struct retro_game_info *game);
RETRO_API void retro_run(void);
RETRO_API size_t retro_serialize_size(void);
RETRO_API bool retro_serialize(void *data, size_t size);
RETRO_API bool retro_unserialize(const void *data, size_t size);
RETRO_API void retro_get_system_av_info(struct retro_system_av_info *info);
extern int nAudioFrequency;

/* ------------------------------------------------------------------------------------------- the files the machine sees */
#define VFS_PREFIX "rr:"
#define MAX_FILES 32
#define AUDIO_CAPACITY 8192

typedef struct VFile { char name[96]; uint8_t *data; size_t size, capacity; int used, owned; } VFile;
struct retro_vfs_file_handle { VFile *file; int64_t position; unsigned mode; char path[128]; };

struct RrStSession {
    RrStGame game;
    VFile files[MAX_FILES];
    char disk_paths[RR_ST_MAX_DISKS][64];
    unsigned disk_index;
    const struct retro_disk_control_ext_callback *disk_control;
    retro_keyboard_event_t keyboard;
    unsigned joystick[2];
    int mouse_dx, mouse_dy, mouse_left, mouse_right;
    uint32_t picture[RR_ST_PICTURE_MAX_WIDTH * RR_ST_PICTURE_MAX_HEIGHT];
    int width, height;
    int16_t audio[AUDIO_CAPACITY * 2];
    size_t audio_frames, audio_read;
    uint64_t frames;
    char memory_option[16];
    uint64_t interpreted, native;
    int observe, native_enabled;
    struct Observation *observed;
    size_t observed_count, observed_capacity;
    char error[256];
    void (*log)(const char *line);
};

static RrStSession *current;

/* The step hook of the adapted Hatari's 68000 loop (defined below). */
extern bool (*rr_hatari_step)(uint32_t pc, uint32_t opcode);
static bool step_hook(uint32_t pc, uint32_t opcode);

/* Hatari makes some names absolute (the TOS image: "<current folder>\rr:\tos.img"), so the session's folder is recognised
 * wherever it appears in a path; what follows it is the file's name. */
static const char *session_part(const char *path) { return path ? strstr(path, VFS_PREFIX) : NULL; }

static const char *base_name(const char *path) {
    const char *name = session_part(path);
    const char *c;
    name = name ? name + strlen(VFS_PREFIX) : path;
    for (c = name; *c; c++) if (*c == '/' || *c == '\\') name = c + 1;
    return name;
}

static int in_session(const char *path) { return session_part(path) != NULL; }

static VFile *find_file(const char *path) {
    unsigned n;
    const char *name;
    if (!current || !in_session(path)) return NULL;
    name = base_name(path);
    for (n = 0; n < MAX_FILES; n++)
        if (current->files[n].used && !strcmp(current->files[n].name, name)) return &current->files[n];
    return NULL;
}

static VFile *add_file(const char *name, const uint8_t *data, size_t size, int owned) {
    unsigned n;
    for (n = 0; n < MAX_FILES; n++) {
        VFile *f = &current->files[n];
        if (f->used) continue;
        memset(f, 0, sizeof *f);
        snprintf(f->name, sizeof f->name, "%s", name);
        f->data = (uint8_t *)data;
        f->size = f->capacity = size;
        f->used = 1;
        f->owned = owned;
        return f;
    }
    return NULL;
}

static const char *RETRO_CALLCONV vfs_get_path(struct retro_vfs_file_handle *h) { return h->path; }

static struct retro_vfs_file_handle *RETRO_CALLCONV vfs_open(const char *path, unsigned mode, unsigned hints) {
    VFile *f = find_file(path);
    struct retro_vfs_file_handle *h;
    (void)hints;
    if (!in_session(path)) return NULL;
    if (mode & RETRO_VFS_FILE_ACCESS_WRITE) {
        if (!f) f = add_file(base_name(path), NULL, 0, 1);
        if (!f) return NULL;
        if (!f->owned) {   /* the game's own images are never written: a write goes to a private copy */
            uint8_t *copy = (uint8_t *)malloc(f->size ? f->size : 1);
            if (!copy) return NULL;
            memcpy(copy, f->data, f->size);
            f->data = copy;
            f->capacity = f->size;
            f->owned = 1;
        }
        if (!(mode & RETRO_VFS_FILE_ACCESS_UPDATE_EXISTING)) f->size = 0;
    } else if (!f) {
        return NULL;
    }
    h = (struct retro_vfs_file_handle *)calloc(1, sizeof *h);
    if (!h) return NULL;
    h->file = f;
    h->mode = mode;
    snprintf(h->path, sizeof h->path, "%s", path);
    return h;
}

static int RETRO_CALLCONV vfs_close(struct retro_vfs_file_handle *h) { free(h); return 0; }
static int64_t RETRO_CALLCONV vfs_size(struct retro_vfs_file_handle *h) { return (int64_t)h->file->size; }
static int64_t RETRO_CALLCONV vfs_tell(struct retro_vfs_file_handle *h) { return h->position; }

static int64_t RETRO_CALLCONV vfs_seek(struct retro_vfs_file_handle *h, int64_t offset, int whence) {
    int64_t base = whence == RETRO_VFS_SEEK_POSITION_CURRENT ? h->position : whence == RETRO_VFS_SEEK_POSITION_END ? (int64_t)h->file->size : 0;
    if (base + offset < 0) return -1;
    h->position = base + offset;
    return h->position;
}

static int64_t RETRO_CALLCONV vfs_read(struct retro_vfs_file_handle *h, void *s, uint64_t len) {
    uint64_t left;
    if (h->position >= (int64_t)h->file->size) return 0;
    left = h->file->size - (uint64_t)h->position;
    if (len > left) len = left;
    memcpy(s, h->file->data + h->position, (size_t)len);
    h->position += (int64_t)len;
    return (int64_t)len;
}

static int64_t RETRO_CALLCONV vfs_write(struct retro_vfs_file_handle *h, const void *s, uint64_t len) {
    VFile *f = h->file;
    uint64_t end = (uint64_t)h->position + len;
    if (!(h->mode & RETRO_VFS_FILE_ACCESS_WRITE) || end > (64u << 20)) return -1;
    if (end > f->capacity) {
        size_t capacity = f->capacity ? f->capacity : 4096;
        uint8_t *grown;
        while (capacity < end) capacity *= 2;
        if (!(grown = (uint8_t *)realloc(f->data, capacity))) return -1;
        f->data = grown;
        f->capacity = capacity;
    }
    if ((uint64_t)h->position > f->size) memset(f->data + f->size, 0, (size_t)(h->position - (int64_t)f->size));
    memcpy(f->data + h->position, s, (size_t)len);
    h->position = (int64_t)end;
    if (end > f->size) f->size = (size_t)end;
    return (int64_t)len;
}

static int RETRO_CALLCONV vfs_flush(struct retro_vfs_file_handle *h) { (void)h; return 0; }

static int64_t RETRO_CALLCONV vfs_truncate(struct retro_vfs_file_handle *h, int64_t length) {
    if (length < 0 || (size_t)length > h->file->size) return -1;
    h->file->size = (size_t)length;
    return 0;
}

static int RETRO_CALLCONV vfs_remove(const char *path) {
    VFile *f = find_file(path);
    if (!f || !f->owned) return -1;
    free(f->data);
    memset(f, 0, sizeof *f);
    return 0;
}

static int RETRO_CALLCONV vfs_rename(const char *old_path, const char *new_path) {
    VFile *f = find_file(old_path);
    if (!f || !in_session(new_path) || find_file(new_path)) return -1;
    snprintf(f->name, sizeof f->name, "%s", base_name(new_path));
    return 0;
}

static int RETRO_CALLCONV vfs_stat(const char *path, int32_t *size) {
    VFile *f = find_file(path);
    if (!f) {
        /* The system folder itself exists (Hatari checks it); nothing else outside the session's files does. */
        if (in_session(path) && !*base_name(path)) return RETRO_VFS_STAT_IS_VALID | RETRO_VFS_STAT_IS_DIRECTORY;
        return 0;
    }
    if (size) *size = (int32_t)f->size;
    return RETRO_VFS_STAT_IS_VALID;
}

static int RETRO_CALLCONV vfs_stat_64(const char *path, int64_t *size) {
    int32_t small = 0;
    int flags = vfs_stat(path, &small);
    VFile *f = find_file(path);
    if (size) *size = f ? (int64_t)f->size : 0;
    return flags;
}

static int RETRO_CALLCONV vfs_mkdir(const char *dir) { (void)dir; return -1; }
static struct retro_vfs_dir_handle *RETRO_CALLCONV vfs_opendir(const char *dir, bool hidden) { (void)dir; (void)hidden; return NULL; }
static bool RETRO_CALLCONV vfs_readdir(struct retro_vfs_dir_handle *d) { (void)d; return false; }
static const char *RETRO_CALLCONV vfs_dirent_name(struct retro_vfs_dir_handle *d) { (void)d; return NULL; }
static bool RETRO_CALLCONV vfs_dirent_is_dir(struct retro_vfs_dir_handle *d) { (void)d; return false; }
static int RETRO_CALLCONV vfs_closedir(struct retro_vfs_dir_handle *d) { (void)d; return 0; }

static struct retro_vfs_interface vfs = {
    vfs_get_path, vfs_open, vfs_close, vfs_size, vfs_tell, vfs_seek, vfs_read, vfs_write, vfs_flush, vfs_remove, vfs_rename,
    vfs_truncate, vfs_stat, vfs_mkdir, vfs_opendir, vfs_readdir, vfs_dirent_name, vfs_dirent_is_dir, vfs_closedir, vfs_stat_64,
};

/* ----------------------------------------------------------------------------------------- the machine's fixed settings */
/* Hatari's core options as the conversion runs the machine: a plain ST at 8 MHz with its cycle-exact 68000, the real TOS
 * (not patched for a faster boot), real floppy timing, the borders shown (overscan tricks stay visible), no blitter. */
static const char *option_value(const char *key) {
    /* Every option Hatari's frontend reads (src/retro/options.c), so none falls back to a default chosen elsewhere. Booleans are
     * "enabled" or "disabled". Port 0 is the mouse port (its joystick "none": the mouse), port 1 the joystick port; the second
     * fire button is not turned into "up". */
    static const char *const fixed[][2] = {
        {"hatari_dsp_type", "none"}, {"hatari_blitter", "disabled"}, {"hatari_fastboot", "disabled"}, {"hatari_timerd", "disabled"},
        {"hatari_cpu_level", "0"}, {"hatari_cpu_clock", "8"}, {"hatari_cpu_compatible", "enabled"},
        {"hatari_cpu_cycle_exact", "enabled"}, {"hatari_cpu_addr24", "enabled"}, {"hatari_cpu_data_cache", "disabled"},
        {"hatari_fpu_type", "none"}, {"hatari_fpu_softfloat", "disabled"}, {"hatari_mmu", "disabled"},
        {"hatari_patch_tos", "disabled"}, {"hatari_ttram_size", "0"}, {"hatari_auto_insert_disk_b", "disabled"},
        {"hatari_fast_floppy", "disabled"}, {"hatari_floppy_write_protection", "off"}, {"hatari_drive_a_enable", "enabled"},
        {"hatari_drive_b_enable", "enabled"}, {"hatari_drive_a_heads", "2"}, {"hatari_drive_b_heads", "2"},
        {"hatari_monitor_type", "rgb"}, {"hatari_video_timing", "ws3"}, {"hatari_borders", "enabled"},
        {"hatari_aspect_correct", "disabled"}, {"hatari_spec512_threshold", "1"}, {"hatari_joystick_autofire", "disabled"},
        {"hatari_joystick_jump_fire2", "disabled"}, {"hatari_joystick_port0", "none"}, {"hatari_joystick_port1", "real"},
    };
    size_t n;
    if (!strcmp(key, "hatari_machinetype")) return current->game.machine ? current->game.machine : "st";
    if (!strcmp(key, "hatari_memory_size")) return current->memory_option;
    for (n = 0; n < sizeof fixed / sizeof fixed[0]; n++) if (!strcmp(key, fixed[n][0])) return fixed[n][1];
    return NULL;
}

static void RETRO_CALLCONV log_printf(enum retro_log_level level, const char *format, ...) {
    char line[512];
    va_list args;
    (void)level;
    if (!current || !current->log) return;
    va_start(args, format);
    vsnprintf(line, sizeof line, format, args);
    va_end(args);
    current->log(line);
}

/* Environment calls are matched without their experimental flag. */
#define E(cmd) ((cmd) & ~RETRO_ENVIRONMENT_EXPERIMENTAL)

static bool RETRO_CALLCONV environment(unsigned cmd, void *data) {
    switch (cmd & ~RETRO_ENVIRONMENT_EXPERIMENTAL) {
    case E(RETRO_ENVIRONMENT_GET_VARIABLE): {
        struct retro_variable *v = (struct retro_variable *)data;
        v->value = current && v->key ? option_value(v->key) : NULL;
        return v->value != NULL;
    }
    case E(RETRO_ENVIRONMENT_GET_VARIABLE_UPDATE): *(bool *)data = false; return true;
    case E(RETRO_ENVIRONMENT_GET_CORE_OPTIONS_VERSION): *(unsigned *)data = 0; return true;
    case E(RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY):
    case E(RETRO_ENVIRONMENT_GET_SAVE_DIRECTORY): *(const char **)data = VFS_PREFIX; return true;
    case E(RETRO_ENVIRONMENT_GET_LOG_INTERFACE): ((struct retro_log_callback *)data)->log = log_printf; return true;
    case E(RETRO_ENVIRONMENT_GET_VFS_INTERFACE): {
        struct retro_vfs_interface_info *info = (struct retro_vfs_interface_info *)data;
        if (info->required_interface_version > 4) return false;
        info->iface = &vfs;
        info->required_interface_version = 4;
        return true;
    }
    case E(RETRO_ENVIRONMENT_SET_KEYBOARD_CALLBACK):
        if (current) current->keyboard = ((const struct retro_keyboard_callback *)data)->callback;
        return true;
    case E(RETRO_ENVIRONMENT_SET_DISK_CONTROL_EXT_INTERFACE):
        if (current) current->disk_control = (const struct retro_disk_control_ext_callback *)data;
        return true;
    case E(RETRO_ENVIRONMENT_GET_DISK_CONTROL_INTERFACE_VERSION): *(unsigned *)data = 1; return true;
    case E(RETRO_ENVIRONMENT_GET_MESSAGE_INTERFACE_VERSION): *(unsigned *)data = 0; return true;
    case E(RETRO_ENVIRONMENT_SET_PIXEL_FORMAT): return *(const enum retro_pixel_format *)data == RETRO_PIXEL_FORMAT_XRGB8888;
    case E(RETRO_ENVIRONMENT_SET_SUPPORT_NO_GAME): case E(RETRO_ENVIRONMENT_SET_GEOMETRY): case E(RETRO_ENVIRONMENT_SET_SYSTEM_AV_INFO):
    case E(RETRO_ENVIRONMENT_SET_INPUT_DESCRIPTORS): case E(RETRO_ENVIRONMENT_SET_MESSAGE): case E(RETRO_ENVIRONMENT_SET_MESSAGE_EXT):
    case E(RETRO_ENVIRONMENT_SET_VARIABLES): case E(RETRO_ENVIRONMENT_SET_CORE_OPTIONS): case E(RETRO_ENVIRONMENT_SET_CORE_OPTIONS_INTL):
    case E(RETRO_ENVIRONMENT_SET_CORE_OPTIONS_V2): case E(RETRO_ENVIRONMENT_SET_CORE_OPTIONS_V2_INTL):
    case E(RETRO_ENVIRONMENT_SET_CORE_OPTIONS_DISPLAY): case E(RETRO_ENVIRONMENT_SET_CORE_OPTIONS_UPDATE_DISPLAY_CALLBACK):
    case E(RETRO_ENVIRONMENT_SET_DISK_CONTROL_INTERFACE): case E(RETRO_ENVIRONMENT_SET_CONTROLLER_INFO):
        return true;
    default:
        return false;
    }
}

/* ------------------------------------------------------------------------------------------ picture, sound and inputs */
static void RETRO_CALLCONV video_refresh(const void *data, unsigned width, unsigned height, size_t pitch) {
    unsigned y;
    if (!current || !data) return;
    if (width > RR_ST_PICTURE_MAX_WIDTH) width = RR_ST_PICTURE_MAX_WIDTH;
    if (height > RR_ST_PICTURE_MAX_HEIGHT) height = RR_ST_PICTURE_MAX_HEIGHT;
    for (y = 0; y < height; y++)
        memcpy(current->picture + (size_t)y * RR_ST_PICTURE_MAX_WIDTH, (const uint8_t *)data + y * pitch, width * 4u);
    current->width = (int)width;
    current->height = (int)height;
}

static size_t RETRO_CALLCONV audio_batch(const int16_t *data, size_t frames) {
    size_t room;
    if (!current) return frames;
    room = AUDIO_CAPACITY - current->audio_frames;
    if (frames > room) frames = room;
    memcpy(current->audio + current->audio_frames * 2, data, frames * 4);
    current->audio_frames += frames;
    return frames;
}

static void RETRO_CALLCONV audio_sample(int16_t left, int16_t right) {
    int16_t pair[2] = {left, right};
    audio_batch(pair, 1);
}

static void RETRO_CALLCONV input_poll(void) {}

static int16_t RETRO_CALLCONV input_state(unsigned port, unsigned device, unsigned index, unsigned id) {
    (void)index;
    if (!current) return 0;
    if (device == RETRO_DEVICE_JOYPAD && port < 2) {
        unsigned bits = current->joystick[port];
        switch (id) {
        case RETRO_DEVICE_ID_JOYPAD_UP: return (bits & RR_ST_JOY_UP) != 0;
        case RETRO_DEVICE_ID_JOYPAD_DOWN: return (bits & RR_ST_JOY_DOWN) != 0;
        case RETRO_DEVICE_ID_JOYPAD_LEFT: return (bits & RR_ST_JOY_LEFT) != 0;
        case RETRO_DEVICE_ID_JOYPAD_RIGHT: return (bits & RR_ST_JOY_RIGHT) != 0;
        case RETRO_DEVICE_ID_JOYPAD_B: return (bits & RR_ST_JOY_FIRE) != 0;
        default: return 0;
        }
    }
    if (device == RETRO_DEVICE_MOUSE && port == 0) {
        int16_t value;
        switch (id) {
        /* Motion is read once per frame: the first read takes it. */
        case RETRO_DEVICE_ID_MOUSE_X: value = (int16_t)current->mouse_dx; current->mouse_dx = 0; return value;
        case RETRO_DEVICE_ID_MOUSE_Y: value = (int16_t)current->mouse_dy; current->mouse_dy = 0; return value;
        case RETRO_DEVICE_ID_MOUSE_LEFT: return (int16_t)current->mouse_left;
        case RETRO_DEVICE_ID_MOUSE_RIGHT: return (int16_t)current->mouse_right;
        default: return 0;
        }
    }
    return 0;
}

void rr_st_joystick(RrStSession *s, unsigned port, unsigned bits) { if (port < 2) s->joystick[port] = bits; }
void rr_st_mouse(RrStSession *s, int dx, int dy, int left, int right) {
    s->mouse_dx += dx; s->mouse_dy += dy; s->mouse_left = left != 0; s->mouse_right = right != 0;
}
void rr_st_key(RrStSession *s, unsigned retrok, int down) { if (s->keyboard) s->keyboard(down != 0, retrok, 0, 0); }
void rr_st_set_log(RrStSession *s, void (*log)(const char *line)) { s->log = log; }

/* ------------------------------------------------------------------------------------------------------- the session */
static int disk_extension_ok(const char *name) {
    const char *dot = strrchr(name, '.');
    static const char *const known[] = {".st", ".msa", ".stx", ".ipf", ".dim"};
    size_t n;
    if (!dot) return 0;
    for (n = 0; n < sizeof known / sizeof known[0]; n++) {
        const char *a = dot, *b = known[n];
        while (*a && *b && (*a | 32) == *b) a++, b++;
        if (!*a && !*b) return 1;
    }
    return 0;
}

RrStSession *rr_st_open(const RrStGame *game, char *error, size_t error_size) {
    static char playlist[RR_ST_MAX_DISKS * 64];
    struct retro_game_info info;
    unsigned n;
    size_t used = 0;
    if (current) { snprintf(error, error_size, "one Atari ST session per process"); return NULL; }
    if (!game || !game->tos || !game->tos_size || !game->disk_count || game->disk_count > RR_ST_MAX_DISKS) {
        snprintf(error, error_size, "a TOS image and 1 to %d disks are needed", RR_ST_MAX_DISKS);
        return NULL;
    }
    if (game->memory_kb != 512 && game->memory_kb != 1024 && game->memory_kb != 2048 && game->memory_kb != 4096) {
        snprintf(error, error_size, "ST RAM must be 512, 1024, 2048 or 4096 KiB");
        return NULL;
    }
    current = (RrStSession *)calloc(1, sizeof *current);
    if (!current) { snprintf(error, error_size, "out of memory"); return NULL; }
    current->game = *game;
    current->log = game->log;
    snprintf(current->memory_option, sizeof current->memory_option, "%u", game->memory_kb);
    add_file("tos.img", game->tos, game->tos_size, 0);
    for (n = 0; n < game->disk_count; n++) {
        const char *dot = strrchr(game->disks[n].name, '.');
        char name[64];
        if (!disk_extension_ok(game->disks[n].name)) { snprintf(error, error_size, "disk %u: unknown image format", n + 1); return NULL; }
        snprintf(name, sizeof name, "disk%u%s", n + 1, dot);
        add_file(name, game->disks[n].data, game->disks[n].size, 0);
        snprintf(current->disk_paths[n], sizeof current->disk_paths[n], VFS_PREFIX "%c%s", PATHSEP, name);
        used += (size_t)snprintf(playlist + used, sizeof playlist - used, "%s\n", name);
    }
    if (game->disk_count > 1) add_file("game.m3u", (const uint8_t *)playlist, used, 0);
    rr_hatari_step = step_hook;
    retro_set_environment(environment);
    retro_set_video_refresh(video_refresh);
    retro_set_audio_sample(audio_sample);
    retro_set_audio_sample_batch(audio_batch);
    retro_set_input_poll(input_poll);
    retro_set_input_state(input_state);
    retro_init();
    memset(&info, 0, sizeof info);
    info.path = game->disk_count > 1 ? VFS_PREFIX "\\game.m3u" : current->disk_paths[0];
    if (PATHSEP == '/' && game->disk_count > 1) info.path = VFS_PREFIX "/game.m3u";
    if (!retro_load_game(&info)) { snprintf(error, error_size, "Hatari refused the disk"); return NULL; }
    return current;
}

/* ------------------------------------------------------------------------------- the step hook of the 68000 loop */
/* The hook the adapted Hatari calls before each instruction of its cycle-exact loop (retrorecomp/atarist_hatari.py). A build
 * without native steps runs every instruction on Hatari's table: the hook counts it and, when the conversion observes, records
 * the instruction (its pc and its own bytes: the length Hatari's table gives its opcode, at most 10 on a 68000) once. */
extern bool (*rr_hatari_step)(uint32_t pc, uint32_t opcode);
typedef struct Observation { uint32_t pc; uint8_t bytes[12]; uint32_t used; } Observation;   /* used: the length in bytes */
static uint8_t opcode_bytes[65536];   /* the instruction length of every opcode, from op_smalltbl_14 (2 for an illegal one) */
static int opcode_bytes_ready;

static void build_opcode_bytes(void) {
    unsigned op, n;
    for (op = 0; op < 65536; op++) {
        cpuop_func_noret *handler = cpufunctbl_noret[op];
        opcode_bytes[op] = 2;
        for (n = 0; op_smalltbl_14[n].handler_ff_noret || op_smalltbl_14[n].handler_ff; n++)
            if (op_smalltbl_14[n].handler_ff_noret == handler) {
                int length = op_smalltbl_14[n].length;
                if (length >= 2 && length <= 12 && !(length & 1)) opcode_bytes[op] = (uint8_t)length;
                break;
            }
    }
    opcode_bytes_ready = 1;
}

/* The bytes at pc when pc is in RAM, the cartridge area or the TOS ROM (read from the machine's arrays, never through the bus:
 * no device register is touched); 0 elsewhere. */
static int code_bytes(uint32_t pc, uint8_t out[12], unsigned length) {
    pc &= 0xffffff;
    memset(out, 0, 12);
    if (pc + length <= STRamEnd) { memcpy(out, STRam + pc, length); return 1; }
    if (pc >= 0xe00000 && pc + length <= 0x1000000 && ROMmemory) { memcpy(out, RomMem + pc, length); return 1; }
    return 0;
}

static uint32_t observation_hash(uint32_t pc, const uint8_t *bytes) {
    uint32_t h = 2166136261u ^ pc;
    int n;
    for (n = 0; n < 12; n++) { h ^= bytes[n]; h *= 16777619u; }
    return h;
}

static int observe_insert(RrStSession *s, uint32_t pc, const uint8_t *bytes, unsigned length) {
    size_t mask, i;
    if (s->observed_count * 2 >= s->observed_capacity) {
        size_t capacity = s->observed_capacity ? s->observed_capacity * 2 : 65536, n;
        Observation *grown, *old = s->observed;
        if (capacity > ((size_t)1 << 24)) return 0;
        if (!(grown = (Observation *)calloc(capacity, sizeof *grown))) return 0;
        s->observed = grown;
        s->observed_capacity = capacity;
        s->observed_count = 0;
        for (n = 0; old && n < capacity / 2; n++) if (old[n].used) observe_insert(s, old[n].pc, old[n].bytes, old[n].used);
        free(old);
    }
    mask = s->observed_capacity - 1;
    for (i = observation_hash(pc, bytes) & mask;; i = (i + 1) & mask) {
        Observation *o = &s->observed[i];
        if (!o->used) { o->used = length; o->pc = pc; memcpy(o->bytes, bytes, 12); s->observed_count++; return 1; }
        if (o->pc == pc && !memcmp(o->bytes, bytes, 12)) return 1;
    }
}

#ifdef RR_ST_NATIVE
/* The generated index of native steps (retrorecomp/atarist_codegen.py and the shared m68k_observed generator): a step is found
 * by its pc and kept only while every word of its instruction is the one observed (the live-word guard of the index, which
 * reads the words through rr_st_code_word); the session also requires the opcode Hatari prefetched to be the step's own. */
struct RrStStep;
const struct RrStStep *rr_st_lookup(uint32_t pc);
void (*rr_st_step_of(const struct RrStStep *s))(uint32_t);
uint32_t rr_st_step_opcode(const struct RrStStep *s);
#endif

/* One instruction word at pc for the guard, big-endian from the machine's arrays (never through the bus). */
int rr_st_code_word(uint32_t pc, uint16_t *word) {
    pc &= 0xffffff;
    if (pc + 2 <= STRamEnd) { *word = (uint16_t)(STRam[pc] << 8 | STRam[pc + 1]); return 1; }
    if (pc >= 0xe00000 && pc + 2 <= 0x1000000 && ROMmemory) { *word = (uint16_t)(RomMem[pc] << 8 | RomMem[pc + 1]); return 1; }
    return 0;
}

static bool step_hook(uint32_t pc, uint32_t opcode) {
    if (!current) return false;
    if (current->observe) {
        uint8_t bytes[12];
        unsigned length;
        if (!opcode_bytes_ready) build_opcode_bytes();
        length = opcode_bytes[opcode & 0xffff];
        if (code_bytes(pc, bytes, length)) observe_insert(current, pc & 0xffffff, bytes, length);
    }
#ifdef RR_ST_NATIVE
    if (current->native_enabled) {
        const struct RrStStep *step = rr_st_lookup(pc);
        if (step && rr_st_step_opcode(step) == (opcode & 0xffff)) {
            rr_st_step_of(step)(opcode);   /* Hatari's own handler of this opcode, called directly */
            current->native++;
            return true;
        }
    }
#endif
    current->interpreted++;
    return false;
}

int rr_st_set_native(RrStSession *s, int enabled) {
#ifdef RR_ST_NATIVE
    s->native_enabled = enabled != 0;
    return 1;
#else
    (void)s;
    return !enabled;
#endif
}

/* The opcode -> handler table of Hatari's cycle-exact 68000 as the machine runs it (the table the step hook falls back to):
 * "<opcode hex> <index>", the index of the opcode's entry in op_smalltbl_14 (gencpu shares a handler between tables, so its name
 * is read from the cpustbl.c of the build by the converter), or "-" for an opcode sent to an illegal-instruction handler. */
int rr_st_write_opcode_map(const RrStSession *s, FILE *out) {
    static const struct cputbl *table = op_smalltbl_14;
    unsigned n, op;
    (void)s;
    if (!CpuRunCycleExact) return 0;   /* the map is the cycle-exact table's: the machine must run that loop */
    for (op = 0; op < 65536; op++) {
        cpuop_func_noret *handler = cpufunctbl_noret[op];
        int found = -1;
        for (n = 0; table[n].handler_ff_noret || table[n].handler_ff; n++)
            if (table[n].handler_ff_noret == handler) { found = (int)n; break; }
        if (found < 0) fprintf(out, "%04x -\n", op);
        else fprintf(out, "%04x %d\n", op, found);   /* the entry's index; its handler's name is read from Hatari's cpustbl.c */
    }
    return !ferror(out);
}

uint64_t rr_st_interpreted_count(const RrStSession *s) { return s->interpreted; }
uint64_t rr_st_native_count(const RrStSession *s) { return s->native; }
void rr_st_set_observe(RrStSession *s, int enabled) { s->observe = enabled != 0; }
size_t rr_st_observation_count(const RrStSession *s) { return s->observed_count; }

static int observation_order(const void *a, const void *b) {
    const Observation *x = (const Observation *)a, *y = (const Observation *)b;
    if (x->pc != y->pc) return x->pc < y->pc ? -1 : 1;
    return memcmp(x->bytes, y->bytes, 12);
}

int rr_st_write_observations(const RrStSession *s, FILE *out) {
    Observation *sorted;
    size_t n, k = 0;
    if (!(sorted = (Observation *)malloc((s->observed_count ? s->observed_count : 1) * sizeof *sorted))) return 0;
    for (n = 0; n < s->observed_capacity; n++) if (s->observed[n].used) sorted[k++] = s->observed[n];
    qsort(sorted, k, sizeof *sorted, observation_order);
    for (n = 0; n < k; n++) {
        int b;
        fprintf(out, "%06x ", (unsigned)sorted[n].pc);
        for (b = 0; b < (int)sorted[n].used; b++) fprintf(out, "%02x", sorted[n].bytes[b]);
        fputc('\n', out);
    }
    free(sorted);
    return !ferror(out);
}

unsigned rr_st_disk_count(const RrStSession *s) { return s->game.disk_count; }

int rr_st_insert_disk(RrStSession *s, unsigned index) {
    const struct retro_disk_control_ext_callback *dc = s->disk_control;
    if (index >= s->game.disk_count) return -1;
    if (index == s->disk_index) return 0;
    if (!dc || !dc->set_eject_state || !dc->set_image_index) return -1;
    if (!dc->set_eject_state(true) || !dc->set_image_index(index) || !dc->set_eject_state(false)) return -1;
    s->disk_index = index;
    return 0;
}

unsigned rr_st_disk_index(const RrStSession *s) { return s->disk_index; }

int rr_st_frame(RrStSession *s) {
    if (s->error[0]) return -1;
    s->audio_frames = s->audio_read = 0;
    retro_run();
    s->frames++;
    if (bQuitProgram) { snprintf(s->error, sizeof s->error, "the machine stopped"); return -1; }
    return 0;
}

const char *rr_st_error(const RrStSession *s) { return s->error; }

const uint32_t *rr_st_picture(const RrStSession *s, int *width, int *height, int *stride) {
    *width = s->width; *height = s->height; *stride = RR_ST_PICTURE_MAX_WIDTH;
    return s->picture;
}

int rr_st_refresh_rate(const RrStSession *s) { (void)s; return nScreenRefreshRate; }
unsigned rr_st_audio_rate(const RrStSession *s) { (void)s; return (unsigned)nAudioFrequency; }

size_t rr_st_audio(RrStSession *s, int16_t *pcm, size_t capacity_frames) {
    size_t n = s->audio_frames - s->audio_read;
    if (n > capacity_frames) n = capacity_frames;
    memcpy(pcm, s->audio + s->audio_read * 2, n * 4);
    s->audio_read += n;
    return n;
}

static uint64_t fnv(uint64_t h, const void *data, size_t size) {
    const uint8_t *p = (const uint8_t *)data;
    size_t n;
    for (n = 0; n < size; n++) { h ^= p[n]; h *= 0x100000001b3ull; }
    return h;
}

void rr_st_frame_info(const RrStSession *s, RrStFrameInfo *info) {
    const uint64_t basis = 0xcbf29ce484222325ull;
    int y, r;
    uint32_t any = 0;
    memset(info, 0, sizeof *info);
    info->frame = s->frames;
    info->video = basis;
    for (y = 0; y < s->height; y++) {
        const uint32_t *row = s->picture + (size_t)y * RR_ST_PICTURE_MAX_WIDTH;
        int x;
        info->video = fnv(info->video, row, (size_t)s->width * 4);
        for (x = 0; x < s->width; x++) any |= row[x] & 0xffffffu;
    }
    info->nonblack = any != 0;
    info->pcm = fnv(basis, s->audio, s->audio_frames * 4);
    info->samples = (uint32_t)s->audio_frames;
    for (y = 0; (size_t)y < s->audio_frames * 2; y++) if (s->audio[y]) { info->audible = 1; break; }
    info->ram = fnv(basis, STRam, STRamEnd);
    info->pc = M68000_GetPC();
    info->sr = M68000_GetSR();
    for (r = 0; r < 8; r++) { info->d[r] = Regs[REG_D0 + r]; info->a[r] = Regs[REG_A0 + r]; }
}

const uint8_t *rr_st_ram(const RrStSession *s, size_t *size) { (void)s; *size = STRamEnd; return STRam; }

/* ------------------------------------------------------------------------------------------------------ quick states */
#define STATE_MAGIC "RRATARIST-STATE-1"
#define STATE_SCRATCH "hatari_savestate.tmp"

/* One capture of Hatari's snapshot (retro_serialize_size writes it to the scratch file of the system folder, which is this
 * session's memory), behind a header with the build's identity, the session's frame and the disk in drive A. */
int rr_st_state_capture(RrStSession *s, const char *abi, uint8_t **out, size_t *out_size) {
    char header[256];
    VFile *scratch;
    int length;
    uint8_t *data;
    *out = NULL; *out_size = 0;
    if (!retro_serialize_size() || !(scratch = find_file(VFS_PREFIX STATE_SCRATCH)) || !scratch->size) return 4;
    length = snprintf(header, sizeof header, "%s\n%s\n%llu %llu %u\n", STATE_MAGIC, abi, (unsigned long long)scratch->size,
                      (unsigned long long)s->frames, s->disk_index);
    if (length <= 0 || (size_t)length >= sizeof header || !(data = (uint8_t *)malloc((size_t)length + scratch->size))) return 4;
    memcpy(data, header, (size_t)length);
    memcpy(data + length, scratch->data, scratch->size);
    *out = data;
    *out_size = (size_t)length + scratch->size;
    return 0;
}

int rr_st_state_restore(RrStSession *s, const char *abi, const uint8_t *data, size_t size) {
    char magic[64], stored[128], counts[96];
    unsigned long long length, frames;
    unsigned disk;
    size_t at = 0, n;
    char *lines[3] = {magic, stored, counts};
    size_t caps[3] = {sizeof magic, sizeof stored, sizeof counts};
    for (n = 0; n < 3; n++) {
        size_t k = 0;
        while (at < size && data[at] != '\n' && k + 1 < caps[n]) lines[n][k++] = (char)data[at++];
        if (at >= size || data[at] != '\n') return 3;
        lines[n][k] = 0;
        at++;
    }
    if (strcmp(magic, STATE_MAGIC)) return 3;
    if (strcmp(stored, abi)) return 2;
    if (sscanf(counts, "%llu %llu %u", &length, &frames, &disk) != 3 || !length || length != size - at ||
        disk >= s->game.disk_count) return 3;
    if (!retro_unserialize(data + at, (size_t)length)) return 3;
    s->frames = frames;
    s->disk_index = disk;
    return 0;
}
