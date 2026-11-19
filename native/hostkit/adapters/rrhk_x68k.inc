/* Sharp X68000 adapter for the host kit (docs/HOST_KIT.md, phase 3). Original Retro-Recomp code, MIT.
 *
 * Included by native/x68000_reference/reference_host.c, the one translation unit that owns the libretro core, the disks
 * and the quick-state envelope: the kit's loop calls the machine through the RrhkMachine table below, the frontend's
 * input callbacks read the pad words and the few host facts (guest keyboard, mouse capture, fast loading) kept here.
 * What stays the computer's own, as listed in HOST_KIT.md section 5: the guest keyboard and its Ctrl+Alt chords, the
 * captured mouse and the mouse-game profile, the floppy drives, the fast-loading key, the variable picture size.
 * Everything else (window, picture, F1/F2/F3/F4/F6/F7/F8/F9/F12, pads, pad slots, quit and restart combinations,
 * sound output) is the kit's. Guest state is never filtered. */
#include "hostkit/hostkit.h"
#include "hostkit/hostkit_session.h"
#include "retro_menu.h"
#include "runtime_i18n.h"
#include "display_settings.h"
#ifdef RR_X68000_LINKED
#include "runtime_feedback_sdl.h"
#else
/* The reference prototype has no embedded resources and no fallback hints: the kit's two calls into them are empty. */
void rr_feedback_start(int gameplay) { (void)gameplay; }
int rr_feedback_enabled(void) { return 0; }
int rr_feedback_toggle(void) { return 0; }
const char *rr_feedback_label(void) { return "Fallback hints unavailable"; }
int rr_feedback_pending(void) { return 0; }
void rr_feedback_finish(void) {}
#ifndef _WIN32
const void *rr_resource(unsigned id, size_t *size) { (void)id; *size = 0; return NULL; }
#endif
#endif

/* The actions, in menu order; the bit of an action is 1 << its index. Button A is the first button of the game
 * (libretro B), Button B the second. Both are face buttons, so autofire applies to them as on every console. */
enum { X_UP, X_DOWN, X_LEFT, X_RIGHT, X_A, X_B, X_ENTER, X_PAUSE, X_ACTIONS };
#define X_NO_PAD ((SDL_GameControllerButton)SDL_CONTROLLER_BUTTON_INVALID)
static const RrhkAction x_actions[X_ACTIONS] = {
   {"Up", L"Up", 1u << X_UP, RRHK_DIR, 0, {SDL_SCANCODE_UP, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_DPAD_UP, SDL_CONTROLLER_BUTTON_DPAD_UP}},
   {"Down", L"Down", 1u << X_DOWN, RRHK_DIR, 0, {SDL_SCANCODE_DOWN, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_DPAD_DOWN, SDL_CONTROLLER_BUTTON_DPAD_DOWN}},
   {"Left", L"Left", 1u << X_LEFT, RRHK_DIR, 0, {SDL_SCANCODE_LEFT, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_DPAD_LEFT, SDL_CONTROLLER_BUTTON_DPAD_LEFT}},
   {"Right", L"Right", 1u << X_RIGHT, RRHK_DIR, 0, {SDL_SCANCODE_RIGHT, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_DPAD_RIGHT, SDL_CONTROLLER_BUTTON_DPAD_RIGHT}},
   {"Button A", L"Button A", 1u << X_A, RRHK_FACE, 0, {SDL_SCANCODE_S, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_A, SDL_CONTROLLER_BUTTON_A}, NULL, SDLK_w},
   {"Button B", L"Button B", 1u << X_B, RRHK_FACE, 0, {SDL_SCANCODE_D, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_B, SDL_CONTROLLER_BUTTON_B}, NULL, SDLK_x},
   {"Start", L"Start", 1u << X_ENTER, RRHK_SYSTEM, 0, {SDL_SCANCODE_RETURN, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_START, SDL_CONTROLLER_BUTTON_START}},
   {"Pause", L"Pause", 1u << X_PAUSE, RRHK_SYSTEM, 0, {SDL_SCANCODE_UNKNOWN, SDL_SCANCODE_UNKNOWN}, {X_NO_PAD, X_NO_PAD}}};
#define X_BIT(action) (1u << (action))

/* What the computer shares with the other disk computers (rrhk_computer.inc) is told which of these actions is which. */
#define RRC_UP X_UP
#define RRC_DOWN X_DOWN
#define RRC_LEFT X_LEFT
#define RRC_RIGHT X_RIGHT
#define RRC_BUTTON_A X_A
#define RRC_BUTTON_B X_B
#define RRC_START X_ENTER
#define RRC_PAUSE X_PAUSE
#define RRC_BIT(action) X_BIT(action)
#define RRC_INI_SECTION L"X68000"
#define RRC_KEYBOARD_ON "Full guest keyboard: ON (F8/F9 sent to X68000)"
#define RRC_GUEST_FKEY_LAST SDL_SCANCODE_F10
#define RRC_HELP_DISKS "Ctrl+Alt+Page Up/Down: FDD0", "Add Shift: FDD1", "Ctrl+Alt+Backspace: eject disk",

/* The largest picture the machine renders (800 x 600) and the one the window starts with. */
#define X_MAX_WIDTH 800
#define X_MAX_HEIGHT 600
#include "hostkit/adapters/rrhk_computer.inc"

static struct {
   uint32_t *argb;                /* the last picture, 0xAARRGGBB, X_MAX_WIDTH per row */
   int16_t *audio;                /* the sound of this frame (stereo int16), not yet taken by the kit */
   size_t audio_count, audio_capacity, audio_taken;
} xa;



/* The libretro joypad of a port from the kit's pad word (keyboard, controller, stick, autofire, opposite directions).
 * In a multiplayer session the words are the network's: no local menu or focus changes them. */
static int player_joy(unsigned port) {
   static const struct { unsigned action, id; } map[] = { {X_UP, RETRO_DEVICE_ID_JOYPAD_UP}, {X_DOWN, RETRO_DEVICE_ID_JOYPAD_DOWN},
      {X_LEFT, RETRO_DEVICE_ID_JOYPAD_LEFT}, {X_RIGHT, RETRO_DEVICE_ID_JOYPAD_RIGHT}, {X_A, RETRO_DEVICE_ID_JOYPAD_B}, {X_B, RETRO_DEVICE_ID_JOYPAD_A} };
   unsigned mask = 0, n;
   if (!ca.windowed || port > 1) return -1;
   if (!rrhk_session_active() && (player_blocked() || !input_focus)) return 0;
   for (n = 0; n < sizeof map / sizeof map[0]; n++) if (ca.pad[port] & X_BIT(map[n].action)) mask |= 1u << map[n].id;
   return (int)mask;
}

/* ---- the picture ---- */
static void player_picture(const void *data, unsigned w, unsigned h, size_t pitch) {
   unsigned x, y;
   if (!ca.windowed || !data || !xa.argb) return;
   if (w > X_MAX_WIDTH || h > X_MAX_HEIGHT) { fail("Video geometry beyond the machine's largest picture"); return; }
   for (y = 0; y < h; y++) {
      uint32_t *out = xa.argb + (size_t)y * X_MAX_WIDTH;
      const uint8_t *row = (const uint8_t *)data + y * pitch;
      if (pixel_format == RETRO_PIXEL_FORMAT_RGB565) {
         for (x = 0; x < w; x++) {
            uint16_t v; unsigned r, g, b;
            memcpy(&v, row + x * 2, 2);
            r = (v >> 11) & 31; g = (v >> 5) & 63; b = v & 31;
            out[x] = 0xff000000u | ((r * 255 / 31) << 16) | ((g * 255 / 63) << 8) | (b * 255 / 31);
         }
      } else for (x = 0; x < w; x++) { uint32_t c; memcpy(&c, row + x * 4, 4); out[x] = c | 0xff000000u; }
   }
}
static const uint32_t *x_pixels(void) { return xa.argb; }
static int x_width(void) { return width ? (int)width : 768; }
static int x_height(void) { return height ? (int)height : 576; }


/* ---- the sound: the frame's PCM waits here until the kit takes it ---- */
static int player_queue_audio(const int16_t *samples, size_t count) {
   if (!ca.windowed) return 1;
   if (xa.audio_count + count * 2 > xa.audio_capacity) {
      size_t capacity = (xa.audio_count + count * 2) * 2;
      void *grown = realloc(xa.audio, capacity * sizeof(int16_t));
      if (!grown) return 0;
      xa.audio = (int16_t *)grown; xa.audio_capacity = capacity;
   }
   memcpy(xa.audio + xa.audio_count, samples, count * 2 * sizeof(int16_t));
   xa.audio_count += count * 2;
   return 1;
}
static size_t x_audio(int16_t *pcm, size_t capacity) {
   size_t n = xa.audio_count - xa.audio_taken;
   if (n > capacity) n = capacity;
   if (!n) { xa.audio_count = xa.audio_taken = 0; return 0; }
   memcpy(pcm, xa.audio + xa.audio_taken, n * sizeof(int16_t));
   xa.audio_taken += n;
   return n;
}

static bool x_run_frame(uint16_t p1, uint16_t p2) {
   ca.pad[0] = p1; ca.pad[1] = p2;
   fast_forward = x_fast_forward();
   input_poll();
   if (!host_frame() || quit_requested || core_error) return false;
   return !frame_limit || frame_number < frame_limit;
}
static void x_pause(bool paused) { (void)paused; }

/* ---- Multiplayer (hostkit_session.h) ----
 * Only the exported game (the linked machine) plays in a session. Every seat plays the export's original disks from
 * memory with a fresh SRAM and nothing reaches the host's files (base74/fileio.c); the snapshot is the machine's session
 * snapshot (state/snapshot.c: RAM, video, devices, disk journals) plus the host's part below. Joystick games only: the
 * keyboard and the mouse are not carried yet (reference_host.c, input_state). */
static bool x_session_started;
#ifdef RR_X68000_LINKED
size_t rr_x68k_snap_bound(void);
size_t rr_x68k_snap_save(void *buffer, size_t capacity);
int rr_x68k_snap_load(const void *buffer, size_t size);
uint64_t rr_x68k_digest(void);
int rr_x68k_session_disk(unsigned index, const uint8_t *original, size_t size);
int rr_x68k_session_start(const uint8_t *sram);
const char *rr_x68k_disk_name(unsigned index);

/* What decides the next frames outside the machine: the frame counters, the clock of the frame callback and the
 * automatic disk changes. In process only (never sent, never a file). */
typedef struct {
   uint64_t total;                /* the snapshot's whole size: a load of another size is refused before any change */
   uint64_t input_frame;
   double elapsed_usec, fps;      /* the frame callback's clock and step: the rate follows the screen mode (a restart) */
   int selected[2];
   unsigned empty_frames[2], interest_seen[2];
   RRMediaRequest request[2];
   unsigned width, height;
} XSessionHost;

static size_t x_snap_bound(void) {
   const size_t core_bound = rr_x68k_snap_bound();
   return core_bound ? sizeof(XSessionHost) + core_bound : 0;
}
static size_t x_snap_save(void *buffer, size_t capacity) {
   XSessionHost h;
   size_t n;
   if (!buffer || capacity < sizeof h || !media_opened) return 0;
   memset(&h, 0, sizeof h);
   h.input_frame = input_frame; h.elapsed_usec = elapsed_usec; h.fps = fps;
   memcpy(h.selected, media.selected, sizeof h.selected);
   memcpy(h.empty_frames, media.empty_frames, sizeof h.empty_frames);
   memcpy(h.interest_seen, media.interest_seen, sizeof h.interest_seen);
   memcpy(h.request, media.request, sizeof h.request);
   h.width = width; h.height = height;
   n = rr_x68k_snap_save((uint8_t *)buffer + sizeof h, capacity - sizeof h);
   if (!n) return 0;
   h.total = sizeof h + n;
   memcpy(buffer, &h, sizeof h);
   return sizeof h + n;
}
static bool x_snap_load(const void *buffer, size_t size) {
   XSessionHost h;
   if (!buffer || size <= sizeof h || !media_opened) return false;
   memcpy(&h, buffer, sizeof h);
   if (h.total != size) return false;
   if (!rr_x68k_snap_load((const uint8_t *)buffer + sizeof h, size - sizeof h)) return false;
   input_frame = h.input_frame; elapsed_usec = h.elapsed_usec; fps = h.fps;
   memcpy(media.selected, h.selected, sizeof h.selected);
   memcpy(media.empty_frames, h.empty_frames, sizeof h.empty_frames);
   memcpy(media.request, h.request, sizeof h.request);
   /* The drives' interest counter is not machine state (only its change between two frames counts): the automatic disk
    * changes read it at the end of every frame, so the saved value was the counter then; take today's counter instead. */
   if (media.interest) { unsigned d; for (d = 0; d < 2; d++) media.interest_seen[d] = media.interest(d); }
   else memcpy(media.interest_seen, h.interest_seen, sizeof h.interest_seen);
   width = h.width; height = h.height;
   automatic_loading = false; memset(&loading_detector, 0, sizeof(loading_detector));
   return true;
}
static uint64_t x_digest(void) { return rr_x68k_digest(); }

/* ---- The host's save for the match (session ABI 8) ----
 * An X68000 game saves on its own disks and in SRAM. The image carries, for each disk of the set, the 1 KiB blocks where this
 * PC's copy (datas/games/x68-<identity>/media) differs from the export's original, then the 16 KiB of SRAM:
 *   "RRX68SV1", u32 disks, then per disk u32 size, u32 blocks, blocks x (u32 index, the block's bytes); then SRAM.
 * Every seat (the host too) starts the match from the export's disks with those blocks and that SRAM, in memory only; nothing
 * is written back (base74/fileio.c). A save larger than the kit's limit is not offered: every seat then starts from the
 * export's own disks and a fresh SRAM. Little-endian words: the same on every seat. */
#define X_SAVE_MAGIC "RRX68SV1"
#define X_SAVE_BLOCK 1024u
#define X_SAVE_SRAM 16384u
const char *rr_x68k_disk_path(unsigned index);
void rr_x68k_sram_copy(uint8_t *out);
static uint8_t *x_save;               /* the host's image for this match (session_save_put), NULL: none */
static size_t x_save_size;
static uint8_t *x_base[RR_MEDIA_MAX]; /* each disk's starting image when the host's save changes it */

static void x_put32(uint8_t *p, uint32_t v) { p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); p[2] = (uint8_t)(v >> 16); p[3] = (uint8_t)(v >> 24); }
static uint32_t x_get32(const uint8_t *p) { return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24; }

/* The original of disk i (embedded in the executable). */
static const unsigned char *x_original(unsigned i, size_t *size) {
   char path[64];
   snprintf(path, sizeof path, "media/%s", rr_x68k_disk_name(i));
   return rr_x68k_payload_original(path, size);
}

/* This PC's save image (out NULL: its size), 0 when it cannot be made or is larger than the kit takes. */
static size_t x_session_save(void *out, size_t capacity) {
   uint8_t *o = (uint8_t *)out, *block = (uint8_t *)malloc(X_SAVE_BLOCK);
   size_t at = 12, disks = 0, result = 0;
   unsigned i;
   if (!block) return 0;
   for (i = 0; rr_x68k_disk_name(i); i++) disks++;
   if (o && capacity < 12) goto done;
   if (o) { memcpy(o, X_SAVE_MAGIC, 8); x_put32(o + 8, (uint32_t)disks); }
   for (i = 0; i < disks; i++) {
      size_t size = 0, n, b, count_at = at + 4;
      uint32_t blocks = 0;
      const unsigned char *original = x_original(i, &size);
      FILE *f;
      if (!original || (o && capacity < at + 8)) goto done;
      if (o) x_put32(o + at, (uint32_t)size);
      at += 8;
      f = rr_x68k_disk_path(i) ? fopen(rr_x68k_disk_path(i), "rb") : NULL;
      for (b = 0; f && b * X_SAVE_BLOCK < size; b++) {
         size_t from = b * X_SAVE_BLOCK;
         n = size - from < X_SAVE_BLOCK ? size - from : X_SAVE_BLOCK;
         if (fread(block, 1, n, f) != n) break;           /* a short copy: the rest stays the original */
         if (!memcmp(block, original + from, n)) continue;
         if (at + 4 + n > RRHK_SESSION_MAX_SAVE || (o && capacity < at + 4 + n)) { fclose(f); goto done; }
         if (o) { x_put32(o + at, (uint32_t)b); memcpy(o + at + 4, block, n); }
         at += 4 + n;
         blocks++;
      }
      if (f) fclose(f);
      if (o) x_put32(o + count_at, blocks);
   }
   if (at + X_SAVE_SRAM > RRHK_SESSION_MAX_SAVE || (o && capacity < at + X_SAVE_SRAM)) goto done;
   if (o) rr_x68k_sram_copy(o + at);
   result = at + X_SAVE_SRAM;
done:
   free(block);
   return result;
}

/* The host's image, checked against this executable's disks and kept for the session's start. */
static bool x_session_save_put(const void *in, size_t size) {
   const uint8_t *p = (const uint8_t *)in;
   size_t at = 12, disks = 0;
   unsigned i;
   for (i = 0; rr_x68k_disk_name(i); i++) disks++;
   if (!p || size < 12 + X_SAVE_SRAM || memcmp(p, X_SAVE_MAGIC, 8) || x_get32(p + 8) != disks) return false;
   for (i = 0; i < disks; i++) {
      size_t original_size = 0, b;
      uint32_t blocks;
      if (!x_original(i, &original_size) || at + 8 > size || x_get32(p + at) != original_size) return false;
      blocks = x_get32(p + at + 4);
      at += 8;
      for (b = 0; b < blocks; b++) {
         size_t from, n;
         if (at + 4 > size) return false;
         from = (size_t)x_get32(p + at) * X_SAVE_BLOCK;
         if (from >= original_size) return false;
         n = original_size - from < X_SAVE_BLOCK ? original_size - from : X_SAVE_BLOCK;
         if (at + 4 + n > size) return false;
         at += 4 + n;
      }
   }
   if (at + X_SAVE_SRAM != size) return false;
   free(x_save);
   x_save = (uint8_t *)malloc(size);
   if (!x_save) { x_save_size = 0; return false; }
   memcpy(x_save, in, size);
   x_save_size = size;
   return true;
}

/* ---- The host writes its save back at a clean end of the match (session_save_commit, Arthur 19 Nov 2026) ----
 * Nobody writes during a match (base74/fileio.c swallows every write of a session). At a clean end the kit asks the host
 * only: each disk of the set whose final bytes (a drive's image as its eject writes it back, otherwise the session's image)
 * differ from this PC's file, then the SRAM if it differs from sram.dat, is written atomically: the previous file is copied
 * to <name>.bak (one step), the new bytes go to <name>.new, then replace the file. */
size_t rr_x68k_disk_final(unsigned index, unsigned char *out, size_t capacity);
void rr_x68k_sram_file_bytes(uint8_t *out);
void rr_x68k_sram_path(char *out, size_t size);

/* 1: the file already holds these bytes; 0: it does not (or cannot be read). */
static int x_file_equals(const wchar_t *path, const uint8_t *bytes, size_t size) {
   FILE *f = rr_fopen(path, L"rb");
   uint8_t chunk[65536];
   size_t at = 0, n;
   int same = f != NULL;
   while (same && (n = fread(chunk, 1, sizeof chunk, f)) > 0) {
      if (at + n > size || memcmp(chunk, bytes + at, n)) same = 0;
      at += n;
   }
   if (f) fclose(f);
   return same && at == size;
}

/* The bytes go to `path` atomically, the previous file kept as path.bak. 1: written or already equal. */
static int x_write_back(const char *utf8, const uint8_t *bytes, size_t size) {
   wchar_t path[4096], temporary[4100], backup[4100];
   FILE *f;
   int ok;
   uint64_t hash = 14695981039346656037ull;
   size_t i;
   for (i = 0; i < size; i++) hash = (hash ^ bytes[i]) * 1099511628211ull;
   if (!rr_from_utf8(utf8, path, 4096) || wcslen(path) > 4090) return 0;
   if (x_file_equals(path, bytes, size)) {
      fprintf(stderr, "[x68000] save at the end of the match: %s unchanged (fnv %016llx)\n", utf8, (unsigned long long)hash);
      return 1;
   }
   wcscpy(temporary, path); wcscat(temporary, L".new");
   wcscpy(backup, path); wcscat(backup, L".bak");
   f = rr_fopen(temporary, L"wb");
   if (!f) return 0;
   ok = fwrite(bytes, 1, size, f) == size && rr_flush_file(f);
   if (fclose(f)) ok = 0;
   if (ok && rr_exists(path)) { rr_remove(backup); ok = rr_copy_new(path, backup); }
   if (ok) ok = rr_replace(temporary, path);
   if (!ok) rr_remove(temporary);
   fprintf(stderr, "[x68000] save at the end of the match: %s %s (fnv %016llx)\n", utf8, ok ? "written" : "NOT written",
           (unsigned long long)hash);
   return ok;
}

static bool x_session_save_commit(void) {
   uint8_t *buffer = (uint8_t *)malloc(RRHK_SESSION_MAX_SAVE);
   char sram_path[4096];
   unsigned i;
   int ok = buffer != NULL;
   for (i = 0; ok && rr_x68k_disk_name(i); i++) {
      size_t n = rr_x68k_disk_final(i, buffer, RRHK_SESSION_MAX_SAVE);
      ok = n && rr_x68k_disk_path(i) && x_write_back(rr_x68k_disk_path(i), buffer, n);
   }
   if (ok) {
      rr_x68k_sram_file_bytes(buffer);
      rr_x68k_sram_path(sram_path, sizeof sram_path);
      ok = x_write_back(sram_path, buffer, X_SAVE_SRAM);
   }
   free(buffer);
   return ok != 0;
}

/* The session starts (after SETUP and the host's save, before the boot digest and frame 0): every seat plays the export's
 * disks with the host's written blocks and SRAM (the host itself: its own, the image it sent; the export's disks and a fresh
 * SRAM when no image can be made), from
 * memory; the machine boots (or restarts) on them with its peripheral clock at zero (the RTC then reads 1 January 2000,
 * RRHK_SESSION_CLOCK), and the disk session opens as after a first frame. */
static void x_session_begin(uint64_t clock) {
   size_t at = 12;
   unsigned i;
   (void)clock;
   x_session_started = true;
   /* The host is handed no image: it plays on its own save, the very image it sent to the guests. */
   if (!x_save && (x_save_size = x_session_save(NULL, 0)) != 0) {
      x_save = (uint8_t *)malloc(x_save_size);
      if (!x_save || x_session_save(x_save, x_save_size) != x_save_size) { free(x_save); x_save = NULL; x_save_size = 0; }
   }
   for (i = 0; rr_x68k_disk_name(i); i++) {
      size_t size = 0;
      const unsigned char *bytes = x_original(i, &size);
      uint32_t blocks = 0, b;
      if (!bytes) { fail("A disk of the set is missing from this executable"); return; }
      if (x_save) { blocks = x_get32(x_save + at + 4); at += 8; }
      free(x_base[i]); x_base[i] = NULL;
      if (blocks) {
         if (!(x_base[i] = (uint8_t *)malloc(size))) { fail("Not enough memory for the host's save"); return; }
         memcpy(x_base[i], bytes, size);
         for (b = 0; b < blocks; b++) {
            size_t from = (size_t)x_get32(x_save + at) * X_SAVE_BLOCK, n = size - from < X_SAVE_BLOCK ? size - from : X_SAVE_BLOCK;
            memcpy(x_base[i] + from, x_save + at + 4, n);
            at += 4 + n;
         }
         bytes = x_base[i];
      }
      if (!rr_x68k_session_disk(i, bytes, size)) { fail("A disk of the set could not be prepared"); return; }
   }
   if (!rr_x68k_session_start(x_save ? x_save + at : NULL)) { fail("The session's disks could not be inserted"); return; }
   input_frame = 0; elapsed_usec = 0.0;
   automatic_loading = false; memset(&loading_detector, 0, sizeof(loading_detector));
   if (!media_opened) {
      media_opened = rr_media_open(&media, content, media_config, &disk_callbacks, select_drive, core.media_ready) != 0;
      if (!media_opened) { fail(rr_media_error(&media)); return; }
      rr_media_set_interest(&media, core.media_interest);
   }
}
#endif
static int x_players(void) { return 2; }
static void x_reset(void) {
   core.reset();
   if (media_opened && !rr_media_boot(&media)) fail(rr_media_error(&media));
   automatic_loading = false; memset(&loading_detector, 0, sizeof(loading_detector));
}
static uint64_t x_interpreted(void) {
#ifdef RR_X68000_DEVCPU
   return cpu_stats[2] + cpu_stats[3];
#else
   return 1;   /* the reference prototype runs the whole MC68000 on its interpreter */
#endif
}
static uint64_t x_zero(void) { return 0; }
static uint64_t x_input_frame(void) { return input_frame; }
static bool x_state_ready(void) { return true; }
static bool x_state_path(wchar_t *path, size_t capacity) { return rr_from_utf8(state_slot, path, capacity) != 0; }
static bool x_state_file(const wchar_t *path, bool load) { (void)path; return snapshot(load) == RR_STATE_OK; }





const RrhkMachine *rrhk_adapter(void) {
   static RrhkMachine machine;
   if (!machine.actions) {
      machine = (RrhkMachine){
         .ini_section = L"X68000", .console_name = "X68000",
         .table_players = 2, .players = x_players,
         .actions = x_actions, .action_count = X_ACTIONS,
         .up = X_UP, .down = X_DOWN, .left = X_LEFT, .right = X_RIGHT, .start = X_ENTER,
         .max_width = X_MAX_WIDTH, .max_height = X_MAX_HEIGHT, .frame_seconds = 1.0 / 61.46,
         .own_audio = false, .audio_model = RRHK_AUDIO_QUEUE, .audio_rate = 44100u, .audio_chunked = true,
         .video_section = L"X68000", .autofire_section = L"X68000", .indexed_bindings = true, .bindings_clearable = true,
         .machine_fkeys = 10,
         .save_failed_en = "Cannot save game state", .save_failed_fr = "Impossible de sauvegarder",
         .reset = x_reset, .run_frame = x_run_frame, .pause = x_pause,
         .pixels = x_pixels, .visible_width = x_width, .visible_height = x_height, .raster_height = x_height, .display_width = x_width,
         .audio = x_audio, .interpreted = x_interpreted, .audio_interpreted = x_zero,
         .state_path = x_state_path, .state_ready = x_state_ready, .state_file = x_state_file, .input_frame = x_input_frame,
         .settings_loaded = x_settings_loaded, .option_rows = x_option_rows, .key_event = x_key_event,
         .help_lines = x_help_lines, .help_controls = x_help_controls,
         .frame_start = x_frame_start, .finished = x_finished,
         .event = x_event, .keyboard_pad = x_keyboard_pad, .fast_forward = x_fast_forward, .game_rect = x_game_rect,
         .help_page = x_help_page, .action_held = x_action_held,
#ifdef RR_X68000_LINKED
         .snap_bound = x_snap_bound, .snap_save = x_snap_save, .snap_load = x_snap_load,
         .digest = x_digest, .session_begin = x_session_begin,
         .session_save = x_session_save, .session_save_put = x_session_save_put, .session_save_commit = x_session_save_commit,
#endif
      };
   }
   return &machine;
}

/* The windowed game: the kit runs the loop and calls x_run_frame for each guest frame. */
static int player_run_windowed(const char *title) {
   RrhkMachine *machine = (RrhkMachine *)rrhk_adapter();
   int status;
   machine->frame_seconds = 1.0 / fps;
   machine->own_audio = mute;
   ca.windowed = true;
   xa.argb = (uint32_t *)calloc((size_t)X_MAX_WIDTH * X_MAX_HEIGHT, sizeof(uint32_t));
   if (!xa.argb) { fail("Presentation allocation failed"); return 1; }
   status = rrhk_main(machine, title, 1);
   return status;
}
static void player_shutdown(void) { free(xa.argb); free(xa.audio); xa.argb = NULL; xa.audio = NULL; }
