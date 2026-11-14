/* Retro-Recomp Atari ST player: the windowed game (host kit) and the headless runs the conversion validates with. Original
 * Retro-Recomp code, MIT; linked with Hatari (GPL-2.0, licenses/hatari.md), so the program is distributed under the GPL.
 *
 * One executable for both: an exported game embeds its disks and its TOS image (as resources); the reference build of a
 * conversion reads them from files (`--tos FILE --disk FILE...`). Headless runs write one trace line per frame (the evidence the
 * conversion compares), a JSON report, the observed instructions and a capture of the last picture; inputs come from a bounded
 * event file keyed on the machine's frame. */
#include <SDL.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <libretro.h>
#include "atarist_session.h"
#include "platform_io.h"
#ifdef _WIN32
#include <windows.h>
#endif
#ifdef RR_ST_LINKED
#include "embedded_resources.h"
#include "atarist_payload.h"
#endif
#ifndef RR_ST_STATE_ABI
#define RR_ST_STATE_ABI "atarist-development"
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
static unsigned width = 416, height = 276;
static double aspect_ratio = 4.0 / 3.0;
static char player_config[PATH_CAP], state_slot[PATH_CAP];
static RrStSession *session;
static unsigned frame_limit, frame_number;
static bool quit_requested, restart_requested, failed, verbose;
static unsigned dump_at;
static const char *dump_path, *opcode_map_path, *opcode_lengths_path;
static char writes_path[PATH_CAP];

static void fail(const char *message) {
   if (!failed) fprintf(stderr, "%s\n", message ? message : "failed");
   failed = true;
}

static void log_line(const char *line) { fputs(line, stderr); }

#ifdef RR_ST_LINKED
#include "runtime_feedback.h"
/* An exported game keeps the player's own record (native/runtime_feedback.c, F12): what ran on the interpreter, for the next conversion of this game. The TOS's tag keeps a record
 * apart from a conversion on another TOS, whose memory differs. */
static void record_note(uint32_t pc, const uint8_t *bytes, unsigned size) { rr_feedback_note(RR_FB_ATARIST, pc, RR_ST_TOS_TAG, bytes, size); }
#else
/* The kit's calls into the player's record: a development player records none. */
void rr_feedback_start(int gameplay) { (void)gameplay; }
int rr_feedback_enabled(void) { return 0; }
int rr_feedback_toggle(void) { return 0; }
const char *rr_feedback_label(void) { return "Fallback hints unavailable"; }
int rr_feedback_pending(void) { return 0; }
void rr_feedback_finish(void) {}
#endif
#if !defined(_WIN32) && !defined(RR_ST_LINKED)
const void *rr_resource(unsigned id, size_t *size) { (void)id; *size = 0; return NULL; }
#endif

static FILE *open_utf8(const char *path, const wchar_t *mode) {
   wchar_t wide[PATH_CAP];
   return rr_from_utf8(path, wide, PATH_CAP) ? rr_fopen(wide, mode) : NULL;
}

static uint8_t *read_file(const char *path, uint32_t *size) {
   FILE *f = open_utf8(path, L"rb");
   long n;
   uint8_t *data;
   if (!f) return NULL;
   if (fseek(f, 0, SEEK_END) || (n = ftell(f)) < 0 || n > (64L << 20) || fseek(f, 0, SEEK_SET)) { fclose(f); return NULL; }
   data = (uint8_t *)malloc((size_t)n + 1);
   if (data && fread(data, 1, (size_t)n, f) != (size_t)n) { free(data); data = NULL; }
   fclose(f);
   *size = (uint32_t)n;
   return data;
}

/* Quick states: the session captures and restores in memory, the player keeps the file (UTF-8 paths). probe: capture and
 * discard (a development check that a capture leaves the timeline alone). */
static int state_save(const char *slot, bool probe) {
   uint8_t *data;
   size_t size;
   FILE *f;
   int ok;
   if (rr_st_state_capture(session, RR_ST_STATE_ABI, &data, &size)) return 4;
   if (probe) { free(data); return 0; }
   if (!(f = open_utf8(slot, L"wb"))) { free(data); return 4; }
   ok = fwrite(data, 1, size, f) == size;
   free(data);
   return fclose(f) == 0 && ok ? 0 : 4;
}

static int state_load(const char *slot) {
   uint32_t size;
   uint8_t *data = read_file(slot, &size);
   int result;
   if (!data) return 1;
   result = rr_st_state_restore(session, RR_ST_STATE_ABI, data, size);
   free(data);
   return result;
}

static void live_test_tick(unsigned frame);
static void writes_tick(bool now);
#include "hostkit/adapters/rrhk_atarist.inc"

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

/* "begin end kind code value" per line: kind joy (port 1, code = bit 0..4), joy0 (port 0), mouse (code 0 dx, 1 dy: value per
 * frame; 2 left, 3 right), key (code = libretro key code), disk (code = disk index, inserted at `begin`); frames are the
 * machine's own (absolute, so that a resumed state sees the same inputs). */
static bool load_events(const char *path) {
   FILE *f = open_utf8(path, L"rb");
   char kind[8];
   unsigned begin, end;
   int code, value, fields;
   if (!f) return false;
   while ((fields = fscanf(f, "%u %u %7s %d %d", &begin, &end, kind, &code, &value)) == 5) {
      Event *e = &events[event_count];
      if (event_count >= MAX_EVENTS || begin >= end || end > MAX_FRAMES) { fclose(f); return false; }
      e->begin = begin; e->end = end; e->code = code; e->value = value;
      if (!strcmp(kind, "joy") && code >= 0 && code < 5) e->kind = 'j';
      else if (!strcmp(kind, "joy0") && code >= 0 && code < 5) e->kind = 'J';
      else if (!strcmp(kind, "mouse") && code >= 0 && code < 4) e->kind = 'm';
      else if (!strcmp(kind, "key") && code > 0 && code < RETROK_LAST) e->kind = 'k';
      else if (!strcmp(kind, "disk") && code >= 0 && code < RR_ST_MAX_DISKS) e->kind = 'd';
      else { fclose(f); return false; }
      event_count++;
   }
   fclose(f);
   return fields == EOF;
}

static uint8_t keys_held[RETROK_LAST];

static void scripted_inputs(uint64_t frame) {
   unsigned bits = 0, bits0 = 0, n;
   int dx = 0, dy = 0, left = 0, right = 0;
   uint8_t held[RETROK_LAST];
   memset(held, 0, sizeof held);
   for (n = 0; n < event_count; n++) {
      const Event *e = &events[n];
      if (e->kind == 'd') { if (frame == e->begin) rr_st_insert_disk(session, (unsigned)e->code); continue; }
      if (frame < e->begin || frame >= e->end) continue;
      if (e->kind == 'j') bits |= 1u << e->code;
      else if (e->kind == 'J') bits0 |= 1u << e->code;
      else if (e->kind == 'k') held[e->code] = 1;
      else if (e->code == 0) dx += e->value;
      else if (e->code == 1) dy += e->value;
      else if (e->code == 2) left = 1;
      else right = 1;
   }
   rr_st_joystick(session, 1, bits);
   rr_st_joystick(session, 0, bits0);
   rr_st_mouse(session, dx, dy, left, right);
   for (n = 1; n < RETROK_LAST; n++) if (held[n] != keys_held[n]) { rr_st_key(session, n, held[n]); keys_held[n] = held[n]; }
}

static void write_trace_line(FILE *trace) {
   RrStFrameInfo i;
   int r;
   rr_st_frame_info(session, &i);
   fprintf(trace, "%llu\t%016llx\t%016llx\t%016llx\t%06x\t%04x", (unsigned long long)i.frame, (unsigned long long)i.video,
           (unsigned long long)i.pcm, (unsigned long long)i.ram, i.pc, i.sr);
   for (r = 0; r < 8; r++) fprintf(trace, "\t%08x", i.d[r]);
   for (r = 0; r < 8; r++) fprintf(trace, "\t%08x", i.a[r]);
   fputc('\n', trace);
}

/* ---- what the game wrote to its disks: one file per game, beside its quick state ----
 * The game's own saves survive without F8/F9. Written in a temporary file then moved, once the game has written nothing for half
 * a second and at exit. A file that is not valid is kept aside as `<name>.unusable-N` and the game starts from its disks: a
 * damaged save never blocks a game. */
static void writes_load(void) {
   uint32_t size;
   uint8_t *data;
   wchar_t from[PATH_CAP], to[PATH_CAP];
   char aside[PATH_CAP + 32];
   int n;
   if (!writes_path[0] || !(data = read_file(writes_path, &size))) return;
   n = rr_st_writes_restore(session, data, size);
   free(data);
   if (!n) return;
   fprintf(stderr, "The saved disk writes are not valid: kept aside, the game starts from its disks.\n");
   for (n = 1; n < 1000; n++) {
      FILE *probe;
      snprintf(aside, sizeof aside, "%s.unusable-%d", writes_path, n);
      if ((probe = open_utf8(aside, L"rb"))) { fclose(probe); continue; }
      if (rr_from_utf8(writes_path, from, PATH_CAP) && rr_from_utf8(aside, to, PATH_CAP)) rr_replace(from, to);
      break;
   }
}

static void writes_save(void) {
   uint8_t *data;
   size_t size = rr_st_writes_serialize(session, &data);
   char temporary[PATH_CAP + 8];
   wchar_t from[PATH_CAP], to[PATH_CAP];
   FILE *f;
   bool ok;
   if (!size) return;
   snprintf(temporary, sizeof temporary, "%s.tmp", writes_path);
   if (!(f = open_utf8(temporary, L"wb"))) { free(data); return; }
   ok = fwrite(data, 1, size, f) == size;
   free(data);
   if (fclose(f) || !ok || !rr_from_utf8(temporary, from, PATH_CAP) || !rr_from_utf8(writes_path, to, PATH_CAP) || !rr_replace(from, to))
      fprintf(stderr, "The disk writes could not be saved.\n");
}

static void writes_tick(bool now) {
   if (writes_path[0] && rr_st_writes_pending(session, now ? 0 : 25)) writes_save();
}

static bool write_capture(const char *path);

/* ---- the live input check (opt-in: RETRORECOMP_ST_TEST_SCRIPT and RETRORECOMP_ST_TEST_LOG) ----
 * Real SDL input into the windowed game, so that the whole path a player's keys and pad take can be proved on an invisible
 * desktop (SDL_VIDEODRIVER=dummy): keys go through SDL's own keyboard state like a driver's, a virtual SDL game controller
 * plays the pad. One line per command, `FRAME verb args` (the frame the guest is about to run):
 *   key NAME 1|0      a key down or up (SDL key names)      attach / detach   a virtual game controller
 *   button NAME 1|0   a controller button (a, b, dpup...)   axis NAME VALUE   a controller axis
 *   capture FILE      the picture as a PPM                  log TEXT          what the machine holds, to the log
 *   quit              close the game
 * Nothing runs, and nothing is written, without both variables. */
extern int SDL_SendKeyboardKey(Uint8 state, SDL_Scancode scancode);   /* SDL's own entry for a keyboard driver's key */
static FILE *test_script, *test_log;
static SDL_Joystick *test_pad;
static unsigned test_due;
static char test_command[1024];
static int test_line, test_ready;

static void test_next(void) {
   char line[1100];
   test_line = 0;
   while (fgets(line, sizeof line, test_script)) {
      if (line[0] == '#' || line[0] == '\n' || line[0] == '\r') continue;
      if (sscanf(line, "%u %1023[^\r\n]", &test_due, test_command) != 2) exit(5);
      test_line = 1;
      return;
   }
}

static void live_test_tick(unsigned frame) {
   const char *path = getenv("RETRORECOMP_ST_TEST_SCRIPT"), *out = getenv("RETRORECOMP_ST_TEST_LOG");
   if (!test_ready) {
      test_ready = 1;
      if (!path || !out) return;
      test_script = open_utf8(path, L"rb");
      test_log = open_utf8(out, L"wb");
      if (!test_script || !test_log) exit(5);
      test_next();
   }
   if (!test_script) return;
   while (test_line && test_due <= frame) {
      char name[96], file[900];
      int value;
      if (sscanf(test_command, "key %95s %d", name, &value) == 2) {
         SDL_Scancode code = SDL_GetScancodeFromName(name);
         if (!code || SDL_SendKeyboardKey(value ? SDL_PRESSED : SDL_RELEASED, code) < 0) exit(5);
      } else if (!strcmp(test_command, "attach")) {
         int index = SDL_JoystickAttachVirtual(SDL_JOYSTICK_TYPE_GAMECONTROLLER, SDL_CONTROLLER_AXIS_MAX, SDL_CONTROLLER_BUTTON_MAX, 0);
         if (index < 0 || !(test_pad = SDL_JoystickOpen(index))) exit(5);
      } else if (!strcmp(test_command, "detach") && test_pad) {
         SDL_JoystickID id = SDL_JoystickInstanceID(test_pad);
         int i;
         SDL_JoystickClose(test_pad);
         test_pad = NULL;
         for (i = 0; i < SDL_NumJoysticks(); i++) if (SDL_JoystickGetDeviceInstanceID(i) == id) SDL_JoystickDetachVirtual(i);
      } else if (sscanf(test_command, "button %95s %d", name, &value) == 2 && test_pad) {
         SDL_GameControllerButton b = SDL_GameControllerGetButtonFromString(name);
         if (b == SDL_CONTROLLER_BUTTON_INVALID || SDL_JoystickSetVirtualButton(test_pad, b, (Uint8)value)) exit(5);
      } else if (sscanf(test_command, "axis %95s %d", name, &value) == 2 && test_pad) {
         SDL_GameControllerAxis a = SDL_GameControllerGetAxisFromString(name);
         if (a == SDL_CONTROLLER_AXIS_INVALID || SDL_JoystickSetVirtualAxis(test_pad, a, (Sint16)value)) exit(5);
      } else if (sscanf(test_command, "capture %899s", file) == 1) {
         if (!write_capture(file)) exit(5);
      } else if (!strncmp(test_command, "log", 3)) {
         RrStFrameInfo info;
         rr_st_frame_info(session, &info);
         fprintf(test_log, "%u\tpads=%d\tpad1=%04x\tpad2=%04x\tjoy1=%02x\tjoy0=%02x\tvideo=%016llx\tram=%016llx\tpc=%06x\t%s\n", frame,
                 SDL_NumJoysticks(), ca.pad[0], ca.pad[1], rr_st_joystick_bits(session, 1), rr_st_joystick_bits(session, 0), (unsigned long long)info.video,
                 (unsigned long long)info.ram, info.pc, test_command + (test_command[3] ? 4 : 3));
         fflush(test_log);
      } else if (!strcmp(test_command, "quit")) {
         quit_requested = true;
      } else exit(5);
      test_next();
   }
}

static bool write_capture(const char *path) {
   int w, h, stride, x, y;
   const uint32_t *px = rr_st_picture(session, &w, &h, &stride);
   FILE *f = open_utf8(path, L"wb");
   if (!f) return false;
   fprintf(f, "P6\n%d %d\n255\n", w, h);
   for (y = 0; y < h; y++) for (x = 0; x < w; x++) {
      uint32_t c = px[(size_t)y * stride + x];
      unsigned char rgb[3] = {(unsigned char)(c >> 16), (unsigned char)(c >> 8), (unsigned char)c};
      fwrite(rgb, 1, 3, f);
   }
   return fclose(f) == 0;
}

static bool bare_frames;
static bool interpreted_sites;     /* --interpreted-sites: the report lists where the interpreted instructions ran */

/* The report's timer D signs (A, B, C, D of atarist_session.h): {"A":{"count":N,"frame":F,"pc":P}, ...}. */
static void timer_d_signs_json(const RrStSession *s, char *out, size_t size) {
   RrStTimerDSign sign[4];
   size_t used = 0;
   unsigned k;
   rr_st_timer_d_signs(s, sign);
   used += (size_t)snprintf(out, size, "{");
   for (k = 0; k < 4 && used < size; k++)
      used += (size_t)snprintf(out + used, size - used, "%s\"%c\":{\"count\":%llu,\"frame\":%llu,\"pc\":%u}", k ? "," : "", "ABCD"[k],
                               (unsigned long long)sign[k].count, (unsigned long long)sign[k].frame, (unsigned)sign[k].pc);
   if (used < size) snprintf(out + used, size - used, "}");
}

static int run_headless(const char *trace_path, const char *report_path, const char *capture_path, const char *observe_path,
                        unsigned save_at, bool load_start, bool probe) {
   FILE *trace = trace_path ? open_utf8(trace_path, L"wb") : NULL;
   unsigned nonblack = 0, audible = 0, n, rate = 0;
   bool stopped = false;
   const char *error = "";
   if (trace_path && !trace) { fail("Cannot write the trace"); return 1; }
   if (trace) {
      int r;
      fputs("frame\tvideo\tpcm\tram\tPC\tSR", trace);
      for (r = 0; r < 8; r++) fprintf(trace, "\tD%d", r);
      for (r = 0; r < 8; r++) fprintf(trace, "\tA%d", r);
      fputc('\n', trace);
   }
   if (load_start && state_load(state_slot)) { fail("The quick state could not be loaded"); if (trace) fclose(trace); return 1; }
   for (n = 0; n < frame_limit; n++) {
      RrStFrameInfo info, before;
      int16_t pcm[2 * 4096];
      if (bare_frames) {   /* what a frame costs, without the hashes of the checks: nothing is compared in such a run */
         scripted_inputs(n);
         if (rr_st_frame(session)) { stopped = true; error = rr_st_error(session); break; }
         while (rr_st_audio(session, pcm, 4096)) {}
         continue;
      }
      rr_st_frame_info(session, &before);
      scripted_inputs(before.frame);
      if (rr_st_frame(session)) { stopped = true; error = rr_st_error(session); break; }
      rr_st_frame_info(session, &info);
      nonblack += info.nonblack != 0;
      audible += info.audible != 0;
      if (trace) write_trace_line(trace);
      if (dump_at && info.frame == dump_at && dump_path) {
         size_t ram_size;
         const uint8_t *ram = rr_st_ram(session, &ram_size);
         FILE *d = open_utf8(dump_path, L"wb");
         if (d) { fwrite(ram, 1, ram_size, d); fclose(d); }
      }
      while (rr_st_audio(session, pcm, 4096)) {}
      writes_tick(false);
      if (save_at && info.frame == save_at && state_save(state_slot, probe)) {
         fail("The quick state could not be saved"); stopped = true; error = "state save failed"; break;
      }
   }
   writes_tick(true);
   rate = (unsigned)rr_st_refresh_rate(session);
   if (trace && fclose(trace)) { fail("Cannot write the trace"); return 1; }
   if (capture_path && !write_capture(capture_path)) { fail("Cannot write the capture"); return 1; }
   if (opcode_map_path) {
      FILE *m = open_utf8(opcode_map_path, L"wb");
      if (!m || !rr_st_write_opcode_map(session, m) || fclose(m)) { fail("Cannot write the opcode map"); return 1; }
   }
   if (observe_path) {
      FILE *o = open_utf8(observe_path, L"wb");
      if (!o || !rr_st_write_observations(session, o) || fclose(o)) { fail("Cannot write the observations"); return 1; }
   }
   if (report_path) {
      FILE *r = open_utf8(report_path, L"wb");
      char escaped[400];
      size_t k = 0;
      const char *c;
      int w, h, stride;
      char signs_json[512];
      timer_d_signs_json(session, signs_json, sizeof signs_json);
      for (c = error; *c && k + 2 < sizeof escaped; c++) { if (*c == '"' || *c == '\\') escaped[k++] = '\\'; escaped[k++] = (char)((unsigned char)*c < 32 ? ' ' : *c); }
      escaped[k] = 0;
      if (!r) { fail("Cannot write the report"); return 1; }
      rr_st_picture(session, &w, &h, &stride);
      fprintf(r, "{\"frames\":%u,\"stopped\":%s,\"error\":\"%s\",\"native\":%llu,\"chain_entries\":%llu,\"native_learned\":%llu,\"native_walked\":%llu,\"native_shared\":%llu,\"native_swept\":%llu,\"interpreted\":%llu,\"observed\":%llu,"
                 "\"nonblack_frames\":%u,\"audible_frames\":%u,\"refresh_rate\":%u,\"fps\":%u,\"audio_rate\":%u,\"picture\":[%d,%d],"
                 "\"disk\":%u,\"state_loaded\":%s,\"desktop_started\":%s,\"timer_d_patch\":%s,\"timer_d_signs\":%s,\"disk_writes\":%u",
              n, stopped ? "true" : "false", escaped, (unsigned long long)rr_st_native_count(session), (unsigned long long)rr_st_chain_entries(session), (unsigned long long)rr_st_learned_count(session), (unsigned long long)rr_st_walked_count(session), (unsigned long long)rr_st_shared_count(session), (unsigned long long)rr_st_swept_count(session),
              (unsigned long long)rr_st_interpreted_count(session), (unsigned long long)rr_st_observation_count(session),
              nonblack, audible, rate, rate, rr_st_audio_rate(session), w, h, rr_st_disk_index(session), load_start ? "true" : "false",
              rr_st_desktop_started(session) ? "true" : "false", rr_st_timer_d_patched(session) ? "true" : "false", signs_json, rr_st_writes_count(session));
      if (interpreted_sites) {
         /* Where the interpreted instructions ran: [pc, opcode, count], most run first (at most 4096), the distinct ones and the instructions the table could not hold. */
         static RrStSite sites[4096];
         size_t listed = rr_st_site_list(session, sites, 4096), s;
         fprintf(r, ",\"interpreted_sites\":[");
         for (s = 0; s < listed; s++) fprintf(r, "%s[%u,%u,%llu]", s ? "," : "", sites[s].pc, sites[s].opcode, (unsigned long long)sites[s].count);
         fprintf(r, "],\"interpreted_sites_distinct\":%llu,\"interpreted_sites_unlisted\":%llu", (unsigned long long)rr_st_site_distinct(session), (unsigned long long)rr_st_site_unlisted(session));
      }
      fprintf(r, "}\n");
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

/* ---- the game: embedded (an exported game) or read from files (the conversion's reference build) ---- */
#ifdef RR_ST_LINKED
static bool embedded_game(RrStGame *game, RrStDisk *disks) {
   size_t size, n;
   game->tos = (const uint8_t *)rr_resource(RR_ST_TOS_RESOURCE, &size);
   game->tos_size = (uint32_t)size;
   if (!game->tos || !size || RR_ST_DISK_COUNT < 1 || RR_ST_DISK_COUNT > RR_ST_MAX_DISKS) return false;
   for (n = 0; n < RR_ST_DISK_COUNT; n++) {
      disks[n].name = rr_st_disks[n].name;
      disks[n].data = (const uint8_t *)rr_resource(rr_st_disks[n].resource, &size);
      disks[n].size = (uint32_t)size;
      if (!disks[n].data || !size) return false;
   }
   game->disks = disks;
   game->disk_count = RR_ST_DISK_COUNT;
   game->machine = RR_ST_MACHINE;
   game->memory_kb = RR_ST_MEMORY_KB;
   game->autostart = RR_ST_AUTOSTART[0] ? RR_ST_AUTOSTART : NULL;
   game->timer_d_exact = RR_ST_TIMER_D_EXACT;   /* the conversion's choice for this game, no argument changes it */
   return true;
}

/* A game that boots EmuTOS carries EmuTOS's complete source archive (GPL-2.0-or-later): --write-sources DIR writes it there. */
static int write_sources(const char *folder) {
   size_t size = 0;
   const void *data = RR_ST_SOURCES_RESOURCE ? rr_resource(RR_ST_SOURCES_RESOURCE, &size) : NULL;
   char path[PATH_CAP];
   FILE *f;
   if (!data || !size) { puts("This game carries no third-party source archive (it boots the player's own TOS)."); return 0; }
   if (snprintf(path, sizeof path, "%s/%s", folder, RR_ST_SOURCES_NAME) >= (int)sizeof path) { fail("The folder path is too long"); return 1; }
   if (!(f = open_utf8(path, L"wb")) || fwrite(data, 1, size, f) != size || fclose(f)) { fail("Cannot write the source archive"); return 1; }
   printf("%s\n", path);
   return 0;
}
#endif

int main(int argc, char **argv) {
   const char *trace_path = NULL, *report_path = NULL, *capture_path = NULL, *events_path = NULL, *tos_path = NULL, *slot = NULL;
   const char *observe_path = NULL;
   const char *disk_paths[RR_ST_MAX_DISKS];
   RrStDisk disks[RR_ST_MAX_DISKS];
   unsigned disk_count = 0, save_at = 0, n;
   bool headless = false, load_start = false, probe = false, reference_cpu = false;
   RrStGame game;
   char base_path[PATH_CAP], game_dir[PATH_CAP], error[256], *base;
   int i, result;
   memset(&game, 0, sizeof game);
   game.machine = "st";
   game.memory_kb = 1024;
   SDL_SetMainReady();
#ifdef RR_ST_LINKED
   (void)rr_st_export_marker[0];
#endif
   for (i = 1; i < argc; i++) {
      const char *a = argv[i];
      if (!strcmp(a, "--headless")) headless = true;
      else if (!strcmp(a, "--verbose")) verbose = true;
      else if (!strcmp(a, "--state-load-start")) load_start = true;
      else if (!strcmp(a, "--reference-cpu")) reference_cpu = true;
      else if (!strcmp(a, "--bare-frames")) bare_frames = true;
      else if (!strcmp(a, "--interpreted-sites")) interpreted_sites = true;
      else if (!strcmp(a, "--help")) {
         puts("Retro-Recomp Atari ST player\n--headless --frames N --input-events FILE --trace TSV --report JSON --capture PPM\n"
              "--observations FILE --opcode-lengths FILE --opcode-map FILE --reference-cpu --state-slot FILE --state-save-at FRAME --state-load-start --interpreted-sites --verbose\n"
              "an exported game that boots EmuTOS: --write-sources DIR (writes EmuTOS's source archive there)\n"
              "a build without an embedded game: --tos FILE --disk FILE (up to 8, in order) --machine st|megast|ste --memory KIB --autostart A:\\NAME.PRG --timer-d patched|exact\na headless run keeps what the game writes to its disks only with --disk-writes FILE");
         return 0;
      } else if (i + 1 < argc) {
         const char *v = argv[++i];
         if (!strcmp(a, "--frames")) { char *end; unsigned long k = strtoul(v, &end, 10); if (*end || !k || k > MAX_FRAMES) { fail("Invalid frame limit"); return 1; } frame_limit = (unsigned)k; }
         else if (!strcmp(a, "--input-events")) events_path = v;
         else if (!strcmp(a, "--trace")) trace_path = v;
         else if (!strcmp(a, "--report")) report_path = v;
         else if (!strcmp(a, "--capture")) capture_path = v;
         else if (!strcmp(a, "--observations")) observe_path = v;
         else if (!strcmp(a, "--opcode-map")) opcode_map_path = v;
         else if (!strcmp(a, "--opcode-lengths")) opcode_lengths_path = v;
#ifdef RR_ST_LINKED
         else if (!strcmp(a, "--write-sources")) return write_sources(v);
#endif
         else if (!strcmp(a, "--tos")) tos_path = v;
         else if (!strcmp(a, "--disk")) { if (disk_count == RR_ST_MAX_DISKS) { fail("Too many disks"); return 1; } disk_paths[disk_count++] = v; }
         else if (!strcmp(a, "--machine")) game.machine = v;
         else if (!strcmp(a, "--memory")) game.memory_kb = (unsigned)strtoul(v, NULL, 10);
         else if (!strcmp(a, "--autostart")) game.autostart = v;
         else if (!strcmp(a, "--timer-d")) { if (!strcmp(v, "exact")) game.timer_d_exact = 1; else if (!strcmp(v, "patched")) game.timer_d_exact = 0; else { fail("--timer-d is patched or exact"); return 1; } }
         else if (!strcmp(a, "--disk-writes")) snprintf(writes_path, sizeof writes_path, "%s", v);
         else if (!strcmp(a, "--state-slot")) slot = v;
         else if (!strcmp(a, "--ram-dump-at")) dump_at = (unsigned)strtoul(v, NULL, 10);
         else if (!strcmp(a, "--ram-dump")) dump_path = v;
         else if (!strcmp(a, "--state-probe-at")) { probe = true; save_at = (unsigned)strtoul(v, NULL, 10); }
         else if (!strcmp(a, "--state-save-at")) { char *end; unsigned long k = strtoul(v, &end, 10); if (*end || !k || k > MAX_FRAMES) { fail("Invalid state frame"); return 1; } save_at = (unsigned)k; }
         else { fail("Unknown option"); return 1; }
      } else { fail("Unknown option or missing value"); return 1; }
   }
   if (headless && !frame_limit) { fail("Headless mode requires a bounded --frames"); return 1; }
   if (SDL_Init(SDL_INIT_TIMER) != 0) { fprintf(stderr, "%s\n", SDL_GetError()); return 1; }
   base = SDL_GetBasePath();
   if (!base || strlen(base) >= PATH_CAP - 200) { fail("Executable directory unavailable"); return 1; }
   snprintf(base_path, sizeof base_path, "%s", base);
   SDL_free(base);
#ifdef RR_ST_LINKED
   if (tos_path || disk_count) { fail("An embedded game cannot load other disks"); return 1; }
   if (!embedded_game(&game, disks)) { fail("The embedded game is unreadable"); return 1; }
   mouse_game = RR_ST_MOUSE_GAME != 0;
   snprintf(game_dir, sizeof game_dir, "%sdatas/games/atarist-%s", base_path, RR_ST_SOURCE_IDENTITY);
#else
   if (!tos_path || !(game.tos = read_file(tos_path, &game.tos_size))) { fail("This build needs --tos FILE and --disk FILE"); return 1; }
   for (n = 0; n < disk_count; n++) {
      const char *name = disk_paths[n], *c;
      for (c = name; *c; c++) if (*c == '/' || *c == '\\') name = c + 1;
      disks[n].name = name;
      if (!(disks[n].data = read_file(disk_paths[n], &disks[n].size))) { fail("A --disk image is unreadable"); return 1; }
   }
   game.disks = disks;
   game.disk_count = disk_count;
   snprintf(game_dir, sizeof game_dir, "%sdatas/games/atarist-development", base_path);
#endif
   if (!headless && !make_dirs(game_dir)) { fail("Cannot prepare the game's data folder"); return 1; }
   snprintf(state_slot, sizeof state_slot, "%s", slot ? slot : "");
   if (!slot) snprintf(state_slot, sizeof state_slot, "%s/quick.rrstate", game_dir);
   if (headless && ((save_at && !probe) || load_start) && !slot) { fail("States need --state-slot"); return 1; }
   snprintf(player_config, sizeof player_config, "%s/player.cfg", game_dir);
   if (!headless) snprintf(writes_path, sizeof writes_path, "%s/disk-writes.bin", game_dir);
   if (events_path && !load_events(events_path)) { fail("Invalid input event file"); return 1; }
   if (verbose) game.log = log_line;
   session = rr_st_open(&game, error, sizeof error);
   if (!session) { fail(error); return 1; }
   if (observe_path) rr_st_set_observe(session, 1);
   if (opcode_lengths_path) {
      uint32_t size;
      uint8_t *lengths = read_file(opcode_lengths_path, &size);
      if (!lengths || size != 65536) { fail("The opcode length table is unreadable"); return 1; }
      rr_st_set_opcode_lengths(session, lengths);
      free(lengths);
   }
   /* A build with native steps runs them unless the run is the interpreted reference (--reference-cpu); a build without them
    * runs every instruction on Hatari's interpreter. */
   if (!reference_cpu) rr_st_set_native(session, 1);
   if (interpreted_sites && !rr_st_set_site_count(session, 1)) { fail("Cannot keep the interpreted sites"); return 1; }
#ifdef RR_ST_LINKED
   rr_feedback_start(!headless);    /* Headless, only with RETRO_RECOMP_FEEDBACK=1: the conversion's own runs record nothing. */
   if (!reference_cpu && (!headless || rr_feedback_enabled())) rr_st_set_recorder(session, record_note);
#endif
   writes_load();
   if (headless) {
      result = run_headless(trace_path, report_path, capture_path, observe_path, save_at, load_start, probe);
   } else {
#ifdef RR_ST_LINKED
      result = player_run_windowed(RR_ST_GAME_TITLE " | Atari ST");
#else
      result = player_run_windowed("Retro-Recomp Atari ST (development)");
#endif
      writes_tick(true);
      player_store_exit();
#ifdef RR_ST_LINKED
      rr_feedback_finish();
#endif
      if (restart_requested) restart_self();
   }
#ifdef RR_ST_LINKED
   rr_feedback_finish();     /* The exit below runs no exit handler. */
#endif
   fflush(stdout); fflush(stderr);
   /* Hatari's globals are torn down with the process. */
   _Exit(failed ? 1 : result);
}
