/* Retro-Recomp Amiga player: the windowed game (host kit) and the headless runs the conversion validates with. Original
 * Retro-Recomp code, MIT.
 *
 * One executable for both: an exported game embeds its install (the slave and its data files, as resources) and the native
 * steps; the reference build of a conversion reads an extracted install (`--install DIR`) and runs every instruction on
 * Moira's interpreter. Headless runs write one trace line per frame (the evidence the conversion compares), a JSON report,
 * the observed RAM instructions and the resload log; inputs come from a bounded event file keyed on the machine's frame. */
#include <SDL.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "amiga_session.h"
#include "platform_io.h"
#ifdef _WIN32
#include <windows.h>
#endif
#ifdef RR_AMIGA_LINKED
#include "embedded_resources.h"
#include "amiga_payload.h"
#endif
#ifndef RR_AMIGA_STATE_ABI
#define RR_AMIGA_STATE_ABI "amiga-development"
#endif
/* The display window the conversion measured on its reference routes (amiga_payload.h); none: the standard one. */
#ifndef RR_AMIGA_VIEW_X
#define RR_AMIGA_VIEW_X 0
#define RR_AMIGA_VIEW_Y 0
#define RR_AMIGA_VIEW_W 0
#define RR_AMIGA_VIEW_H 0
#endif

#define PATH_CAP 2048
#define MAX_FRAMES 360000u
#define MAX_EVENTS 4096u

/* ---- what rrhk_computer.inc and the adapter read ---- */
static bool guest_keyboard, mouse_grab, mouse_game, input_focus = true, fast_forward, want_swap, want_eject;
static int loading_holdoff, swap_drive, swap_direction;
static const Uint8 *keys;
static int mouse_dx, mouse_dy;
static Uint32 mouse_buttons;
static unsigned width = 320, height = 256;          /* the shown display window, lores pixels x lines (a_view_place) */
static double aspect_ratio = 4.0 / 3.0;
static char player_config[PATH_CAP], state_slot[PATH_CAP];
static RrAmigaSession *session;
static unsigned frame_limit, frame_number;
static bool quit_requested, restart_requested, failed;
static int ntsc_run;
#define RR_AMIGA_NTSC_RUN ntsc_run

static void fail(const char *message) {
   if (!failed) fprintf(stderr, "%s\n", message ? message : "failed");
   failed = true;
}

/* The kit's two calls into the fallback-hint feedback: this experimental player records none. */
void rr_feedback_start(int gameplay) { (void)gameplay; }
int rr_feedback_enabled(void) { return 0; }
int rr_feedback_toggle(void) { return 0; }
const char *rr_feedback_label(void) { return "Fallback hints unavailable"; }
int rr_feedback_pending(void) { return 0; }
void rr_feedback_finish(void) {}
#if !defined(_WIN32) && !defined(RR_AMIGA_LINKED)
const void *rr_resource(unsigned id, size_t *size) { (void)id; *size = 0; return NULL; }
#endif

#include "hostkit/adapters/rrhk_amiga.inc"

/* ---- the install: embedded (an exported game) or extracted by the conversion (--install DIR) ---- */
static uint8_t *read_file(const char *path, uint32_t *size) {
   wchar_t wide[PATH_CAP];
   FILE *f;
   long n;
   uint8_t *data;
   if (!rr_from_utf8(path, wide, PATH_CAP) || !(f = rr_fopen(wide, L"rb"))) return NULL;
   if (fseek(f, 0, SEEK_END) || (n = ftell(f)) < 0 || n > (64L << 20) || fseek(f, 0, SEEK_SET)) { fclose(f); return NULL; }
   data = (uint8_t *)malloc((size_t)n + 1);
   if (data && fread(data, 1, (size_t)n, f) != (size_t)n) { free(data); data = NULL; }
   fclose(f);
   *size = (uint32_t)n;
   return data;
}

/* install.txt of an extracted install: "slave <file>", "ntsc 0|1", then "file <name>\t<file>" lines (files relative to DIR). */
static bool load_install(const char *dir, RrAmigaGame *game, RrAmigaFile **files) {
   char path[PATH_CAP], line[PATH_CAP * 2];
   wchar_t wide[PATH_CAP];
   FILE *f;
   unsigned count = 0, capacity = 0;
   snprintf(path, sizeof path, "%s/install.txt", dir);
   if (!rr_from_utf8(path, wide, PATH_CAP) || !(f = rr_fopen(wide, L"rb"))) return false;
   while (fgets(line, sizeof line, f)) {
      char *end = line + strlen(line);
      while (end > line && (end[-1] == '\n' || end[-1] == '\r')) *--end = 0;
      if (!strncmp(line, "slave ", 6)) {
         snprintf(path, sizeof path, "%s/%s", dir, line + 6);
         game->slave = read_file(path, &game->slave_size);
         if (!game->slave) { fclose(f); return false; }
      } else if (!strncmp(line, "ntsc ", 5)) {
         game->ntsc = atoi(line + 5) != 0;
      } else if (!strncmp(line, "custom ", 7)) {        /* "custom N VALUE": CUSTOMn from the install's icon */
         unsigned k = 0, value = 0;
         if (sscanf(line + 7, "%u %u", &k, &value) != 2 || k < 1 || k > 5) { fclose(f); return false; }
         game->custom[k - 1] = value;
      } else if (!strncmp(line, "kickstart ", 10)) {   /* the player's Kickstart, normalised by the converter (its own work folder) */
         snprintf(path, sizeof path, "%s/%s", dir, line + 10);
         game->kickstart = read_file(path, &game->kickstart_size);
         if (!game->kickstart) { fclose(f); return false; }
      } else if (!strncmp(line, "file ", 5)) {
         char *tab = strchr(line + 5, '\t');
         RrAmigaFile *grown;
         if (!tab) { fclose(f); return false; }
         *tab = 0;
         if (count == capacity) {
            capacity = capacity ? capacity * 2 : 64;
            grown = (RrAmigaFile *)realloc(*files, capacity * sizeof **files);
            if (!grown) { fclose(f); return false; }
            *files = grown;
         }
         snprintf(path, sizeof path, "%s/%s", dir, tab + 1);
         (*files)[count].data = read_file(path, &(*files)[count].size);
         (*files)[count].name = strdup(line + 5);
         if (!(*files)[count].data || !(*files)[count].name) { fclose(f); return false; }
         count++;
      }
   }
   fclose(f);
   game->files = *files;
   game->file_count = count;
   return game->slave != NULL;
}

#ifdef RR_AMIGA_LINKED
static bool embedded_install(RrAmigaGame *game, RrAmigaFile **files) {
   size_t size, n;
   game->slave = (const uint8_t *)rr_resource(RR_AMIGA_SLAVE_RESOURCE, &size);
   game->slave_size = (uint32_t)size;
   if (!game->slave || !size) return false;
   *files = (RrAmigaFile *)calloc(RR_AMIGA_FILE_COUNT ? RR_AMIGA_FILE_COUNT : 1, sizeof **files);
   if (!*files) return false;
   for (n = 0; n < RR_AMIGA_FILE_COUNT; n++) {
      (*files)[n].name = rr_amiga_files[n].name;
      (*files)[n].data = (const uint8_t *)rr_resource(rr_amiga_files[n].resource, &size);
      (*files)[n].size = (uint32_t)size;
      if (!(*files)[n].data && size) return false;
   }
   game->files = *files;
   game->file_count = RR_AMIGA_FILE_COUNT;
   game->ntsc = RR_AMIGA_NTSC;
#ifdef RR_AMIGA_CUSTOM
   {
      static const uint32_t custom[5] = RR_AMIGA_CUSTOM;
      memcpy(game->custom, custom, sizeof custom);
   }
#endif
#ifdef RR_AMIGA_KICKSTART_RESOURCE
   /* The player's own Kickstart, built into the player's own export (decision D1, 6 Nov 2026), as the X68000 does its IPL. */
   game->kickstart = (const uint8_t *)rr_resource(RR_AMIGA_KICKSTART_RESOURCE, &size);
   game->kickstart_size = (uint32_t)size;
   if (!game->kickstart || !size) return false;
#endif
   return true;
}
#endif

/* Makes every folder of `path` (UTF-8). */
static bool make_dirs(const char *path) {
   char part[PATH_CAP];
   wchar_t wide[PATH_CAP];
   size_t n, len = strlen(path);
   if (len >= PATH_CAP) return false;
   for (n = 1; n <= len; n++) {
      if (n < len && path[n] != '/' && path[n] != '\\') continue;
      memcpy(part, path, n); part[n] = 0;
      if (n == 2 && part[1] == ':') continue;
      if (!rr_from_utf8(part, wide, PATH_CAP) || !rr_mkdir(wide)) return false;
   }
   return true;
}

/* ---- headless runs: the input events, the trace, the report ---- */
typedef struct { unsigned begin, end; char kind; int code, value; } Event;
static Event events[MAX_EVENTS];
static unsigned event_count;

/* "begin end kind code value" per line: kind joy (code = bit 0..5), mouse (code 0 dx, 1 dy: value per frame; 2 left, 3 right),
 * key (code = Amiga raw key 0..127); frames are the machine's own (absolute, so that a resumed state sees the same inputs). */
static bool load_events(const char *path) {
   wchar_t wide[PATH_CAP];
   FILE *f;
   char kind[8];
   unsigned begin, end;
   int code, value, fields;
   if (!rr_from_utf8(path, wide, PATH_CAP) || !(f = rr_fopen(wide, L"rb"))) return false;
   while ((fields = fscanf(f, "%u %u %7s %d %d", &begin, &end, kind, &code, &value)) == 5) {
      Event *e = &events[event_count];
      if (event_count >= MAX_EVENTS || begin >= end || end > MAX_FRAMES) { fclose(f); return false; }
      e->begin = begin; e->end = end; e->code = code; e->value = value;
      if (!strcmp(kind, "joy") && code >= 0 && code < 6) e->kind = 'j';
      else if (!strcmp(kind, "mouse") && code >= 0 && code < 4) e->kind = 'm';
      else if (!strcmp(kind, "key") && code >= 0 && code < 128) e->kind = 'k';
      else { fclose(f); return false; }
      event_count++;
   }
   fclose(f);
   return fields == EOF;
}

static void scripted_inputs(uint64_t frame) {
   unsigned bits = 0, n;
   int dx = 0, dy = 0, left = 0, right = 0;
   uint8_t held[128];
   memset(held, 0, sizeof held);
   for (n = 0; n < event_count; n++) {
      const Event *e = &events[n];
      if (frame < e->begin || frame >= e->end) continue;
      if (e->kind == 'j') bits |= 1u << e->code;
      else if (e->kind == 'k') held[e->code] = 1;
      else if (e->code == 0) dx += e->value;
      else if (e->code == 1) dy += e->value;
      else if (e->code == 2) left = 1;
      else right = 1;
   }
   rr_amiga_joystick(session, bits);
   rr_amiga_mouse(session, dx, dy, left, right);
   rr_amiga_keys(session, held);
}

static void write_trace_line(FILE *trace) {
   RrAmigaFrameInfo i;
   int r;
   rr_amiga_frame_info(session, &i);
   fprintf(trace, "%llu\t%016llx\t%016llx\t%016llx\t%06x\t%04x", (unsigned long long)i.frame, (unsigned long long)i.video,
           (unsigned long long)i.pcm, (unsigned long long)i.ram, i.pc, i.sr);
   for (r = 0; r < 8; r++) fprintf(trace, "\t%08x", i.d[r]);
   for (r = 0; r < 8; r++) fprintf(trace, "\t%08x", i.a[r]);
   fputc('\n', trace);
}

static bool write_capture(const char *path) {
   int w, h, x, y;
   const uint32_t *px = rr_amiga_picture(session, &w, &h);
   wchar_t wide[PATH_CAP];
   FILE *f;
   if (!rr_from_utf8(path, wide, PATH_CAP) || !(f = rr_fopen(wide, L"wb"))) return false;
   fprintf(f, "P6\n%d %d\n255\n", w, h);
   for (y = 0; y < h; y++) for (x = 0; x < w; x++) {
      uint32_t c = px[(size_t)y * RR_AMIGA_PICTURE_WIDTH + x];
      unsigned char rgb[3] = {(unsigned char)(c >> 16), (unsigned char)(c >> 8), (unsigned char)c};
      fwrite(rgb, 1, 3, f);
   }
   return fclose(f) == 0;
}

static FILE *open_utf8(const char *path, const wchar_t *mode) {
   wchar_t wide[PATH_CAP];
   return rr_from_utf8(path, wide, PATH_CAP) ? rr_fopen(wide, mode) : NULL;
}

static int run_headless(const char *trace_path, const char *report_path, const char *observe_path, const char *capture_path,
                        const char *resload_path, unsigned save_at, bool load_start) {
   FILE *trace = trace_path ? open_utf8(trace_path, L"wb") : NULL;
   unsigned nonblack = 0, audible = 0, n;
   bool stopped = false;
   int state_result = -1;
   const char *error = "";
   if (trace_path && !trace) { fail("Cannot write the trace"); return 1; }
   if (trace) {
      int r;
      fputs("frame\tvideo\tpcm\tram\tPC\tSR", trace);
      for (r = 0; r < 8; r++) fprintf(trace, "\tD%d", r);
      for (r = 0; r < 8; r++) fprintf(trace, "\tA%d", r);
      fputc('\n', trace);
   }
   if (load_start) {
      state_result = rr_amiga_state_load(session, state_slot, RR_AMIGA_STATE_ABI);
      if (state_result) { fail("The quick state could not be loaded"); if (trace) fclose(trace); return 1; }
   }
   for (n = 0; n < frame_limit; n++) {
      RrAmigaFrameInfo info;
      int16_t pcm[2 * 4096];
      RrAmigaFrameInfo before;
      rr_amiga_frame_info(session, &before);
      scripted_inputs(before.frame);
      if (rr_amiga_frame(session)) { stopped = true; error = rr_amiga_error(session); break; }
      rr_amiga_frame_info(session, &info);
      nonblack += info.nonblack != 0;
      audible += info.audible != 0;
      if (trace) write_trace_line(trace);
      while (rr_amiga_audio(session, pcm, 4096)) {}
      if (save_at && info.frame == save_at && rr_amiga_state_save(session, state_slot, RR_AMIGA_STATE_ABI)) {
         fail("The quick state could not be saved"); stopped = true; error = "state save failed"; break;
      }
   }
   if (trace && fclose(trace)) { fail("Cannot write the trace"); return 1; }
   if (observe_path && !rr_amiga_write_observations(session, observe_path)) { fail("Cannot write the observations"); return 1; }
   if (resload_path && !rr_amiga_write_resload_log(session, resload_path)) { fail("Cannot write the resload log"); return 1; }
   if (capture_path && !write_capture(capture_path)) { fail("Cannot write the capture"); return 1; }
   if (report_path) {
      FILE *r = open_utf8(report_path, L"wb");
      char escaped[400];
      size_t k = 0;
      const char *c;
      for (c = error; *c && k + 2 < sizeof escaped; c++) { if (*c == '"' || *c == '\\') escaped[k++] = '\\'; escaped[k++] = (char)((unsigned char)*c < 32 ? ' ' : *c); }
      escaped[k] = 0;
      if (!r) { fail("Cannot write the report"); return 1; }
      {
         int vx, vy, vw, vh;
         if (rr_amiga_viewport(session, &vx, &vy, &vw, &vh)) fprintf(r, "{\"view\":[%d,%d,%d,%d],", vx, vy, vw, vh);
         else fputs("{\"view\":null,", r);
      }
      {
         uint32_t ksize;
         uint16_t kcrc;
         if (rr_amiga_kickstart(session, &ksize, &kcrc))
            fprintf(r, "\"kickstart\":{\"size\":%u,\"crc16\":%u,\"interpreted\":%llu,\"native\":%llu},", ksize, kcrc,
                    (unsigned long long)rr_amiga_kickstart_interpreted_count(session),
                    (unsigned long long)rr_amiga_kickstart_native_count(session));
         else fputs("\"kickstart\":null,", r);
      }
      fprintf(r, "\"quit\":%s,\"frames\":%u,\"stopped\":%s,\"error\":\"%s\",\"native\":%llu,\"interpreted\":%llu,\"resload_calls\":%ld,"
                 "\"nonblack_frames\":%u,\"audible_frames\":%u,\"fps\":%.4f,\"state_loaded\":%s}\n",
              rr_amiga_quit(session) ? "true" : "false", n, stopped ? "true" : "false", escaped, (unsigned long long)rr_amiga_native_count(session),
              (unsigned long long)rr_amiga_interpreted_count(session), rr_amiga_resload_calls(session), nonblack, audible,
              RR_AMIGA_NTSC_RUN ? 59.94 : 49.92, load_start ? "true" : "false");
      if (fclose(r)) { fail("Cannot write the report"); return 1; }
   }
   return stopped ? 2 : 0;
}

static void restart_self(void) {
#ifdef _WIN32
   STARTUPINFOW si;
   PROCESS_INFORMATION pi;
   wchar_t *line = _wcsdup(GetCommandLineW());
   memset(&si, 0, sizeof si); si.cb = sizeof si;
   if (line && CreateProcessW(NULL, line, NULL, NULL, FALSE, 0, NULL, NULL, &si, &pi)) { CloseHandle(pi.hThread); CloseHandle(pi.hProcess); }
   free(line);
#endif
}

int main(int argc, char **argv) {
   char base_path[PATH_CAP], game_dir[PATH_CAP], saves[PATH_CAP], error[256];
   const char *install_dir = NULL, *trace_path = NULL, *report_path = NULL, *observe_path = NULL, *capture_path = NULL;
   const char *events_path = NULL, *resload_path = NULL, *slot = NULL, *save_dir_arg = NULL;
   bool headless = false, reference_cpu = false, load_start = false;
   unsigned save_at = 0;
   RrAmigaGame game;
   RrAmigaFile *files = NULL;
   char *base;
   int i, result;
   memset(&game, 0, sizeof game);
   SDL_SetMainReady();
#ifdef RR_AMIGA_LINKED
   (void)rr_amiga_export_marker[0];
#endif
   for (i = 1; i < argc; i++) {
      const char *a = argv[i];
      if (!strcmp(a, "--headless")) headless = true;
      else if (!strcmp(a, "--reference-cpu")) reference_cpu = true;
      else if (!strcmp(a, "--state-load-start")) load_start = true;
      else if (!strcmp(a, "--help")) {
         puts("Retro-Recomp Amiga player\n--headless --frames N --input-events FILE --trace TSV --report JSON --observations FILE\n"
              "--capture PPM --resload-log FILE --reference-cpu --state-slot FILE --state-save-at FRAME --state-load-start\n"
              "--install DIR (a build without an embedded game) --saves DIR");
         return 0;
      } else if (i + 1 < argc) {
         const char *v = argv[++i];
         if (!strcmp(a, "--frames")) { char *end; unsigned long n = strtoul(v, &end, 10); if (*end || !n || n > MAX_FRAMES) { fail("Invalid frame limit"); return 1; } frame_limit = (unsigned)n; }
         else if (!strcmp(a, "--input-events")) events_path = v;
         else if (!strcmp(a, "--trace")) trace_path = v;
         else if (!strcmp(a, "--report")) report_path = v;
         else if (!strcmp(a, "--observations")) observe_path = v;
         else if (!strcmp(a, "--capture")) capture_path = v;
         else if (!strcmp(a, "--resload-log")) resload_path = v;
         else if (!strcmp(a, "--state-slot")) slot = v;
         else if (!strcmp(a, "--state-save-at")) { char *end; unsigned long n = strtoul(v, &end, 10); if (*end || !n || n > MAX_FRAMES) { fail("Invalid state frame"); return 1; } save_at = (unsigned)n; }
         else if (!strcmp(a, "--install")) install_dir = v;
         else if (!strcmp(a, "--saves")) save_dir_arg = v;
         else { fail("Unknown option"); return 1; }
      } else { fail("Unknown option or missing value"); return 1; }
   }
   if (headless && !frame_limit) { fail("Headless mode requires a bounded --frames"); return 1; }
   if (SDL_Init(SDL_INIT_TIMER) != 0) { fprintf(stderr, "%s\n", SDL_GetError()); return 1; }
   base = SDL_GetBasePath();
   if (!base || strlen(base) >= PATH_CAP - 200) { fail("Executable directory unavailable"); return 1; }
   snprintf(base_path, sizeof base_path, "%s", base);
   SDL_free(base);
#ifdef RR_AMIGA_LINKED
   if (install_dir) { fail("An embedded game cannot load another install"); return 1; }
   if (!embedded_install(&game, &files)) { fail("The embedded install is unreadable"); return 1; }
   mouse_game = RR_AMIGA_MOUSE_GAME != 0;
   snprintf(game_dir, sizeof game_dir, "%sdatas/games/amiga-%s", base_path, RR_AMIGA_SOURCE_IDENTITY);
#else
   if (!install_dir || !load_install(install_dir, &game, &files)) { fail("This build needs --install DIR (an extracted WHDLoad install)"); return 1; }
   snprintf(game_dir, sizeof game_dir, "%sdatas/games/amiga-development", base_path);
#endif
   if (!make_dirs(game_dir)) { fail("Cannot prepare the game's data folder"); return 1; }
   snprintf(saves, sizeof saves, "%s/saves", save_dir_arg ? save_dir_arg : game_dir);
   if (save_dir_arg) snprintf(saves, sizeof saves, "%s", save_dir_arg);
   snprintf(state_slot, sizeof state_slot, "%s", slot ? slot : "");
   if (!slot) snprintf(state_slot, sizeof state_slot, "%s/quick.rrstate", game_dir);
   snprintf(player_config, sizeof player_config, "%s/player.cfg", game_dir);
   game.save_dir = saves;
   ntsc_run = game.ntsc;
   a_view_init(game.ntsc, RR_AMIGA_VIEW_X, RR_AMIGA_VIEW_Y, RR_AMIGA_VIEW_W, RR_AMIGA_VIEW_H);
   session = rr_amiga_open(&game, error, sizeof error);
   if (!session) { fail(error); return 1; }
   if (!reference_cpu && !rr_amiga_set_native(session, 1)) { fail("This build has no native steps"); return 1; }
   if (observe_path) rr_amiga_set_observe(session, 1);
   if (events_path && !load_events(events_path)) { fail("Invalid input event file"); return 1; }
   if (headless) {
      result = run_headless(trace_path, report_path, observe_path, capture_path, resload_path, save_at, load_start);
   } else {
#ifdef RR_AMIGA_LINKED
      result = player_run_windowed(RR_AMIGA_GAME_TITLE " | Commodore Amiga", game.ntsc);
#else
      result = player_run_windowed("Retro-Recomp Amiga (development)", game.ntsc);
#endif
      player_store_exit();
      if (restart_requested) restart_self();
   }
   fflush(stdout); fflush(stderr);
   /* The machine's destructor expects its emulator thread, which this host never starts: leave without it. */
   _Exit(failed ? 1 : result);
}
