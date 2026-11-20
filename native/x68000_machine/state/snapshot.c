/* Retro-Recomp X68000 machine snapshot (RRX68MS1): section order, CPU, host.
 *
 * Copyright (c) 2026 Retro-Recomp contributors. MIT License (see LICENSE).
 *
 * Written from the project's own state inventory (variable declarations),
 * not from libretro/state.c or any *_StateAction function. Device sections
 * are generated into build copies by tools/x68000_state_hardware.py.
 */
#include <stdlib.h>
#include <string.h>

#include "rr_state.h"
#include "../glue.h"
#include "prop.h"
#include "keyboard.h"
#ifdef RR_X68000_BASE74
#include "memory.h"
#else
#include "../x68k/x68kmemory.h"
#endif
#include "../x68k/ioc.h"
#include "hardware_clock.h"
/* The CPU struct layout must come from the core actually linked: Geolith's
 * Musashi in the native build, PX68k's bundled copy in the reference build.
 * Do not include m68000/m68000.h here: it pulls PX68k's m68kcpu.h first and
 * the include guard would then hide the native core's header. */
#if defined(RR_X68000_EXTENDED_CPU_STATE) || defined(RR_X68000_BASE74)
#include "m68kcpu.h"
#else
#include "musashi/m68kcpu.h"
#endif
extern int ICount, m68000_ICountBk;

/* Device sections appended to the module build copies. */
void rr_state_gvram(RRState *s);
void rr_state_tvram(RRState *s);
void rr_state_crtc(RRState *s);
void rr_state_palette(RRState *s);
void rr_state_bg(RRState *s);
void rr_bg_state_sync(int loading);
void rr_state_dmac(RRState *s);
void rr_state_mfp(RRState *s);
void rr_state_irqh(RRState *s);
void rr_state_scc(RRState *s);
void rr_state_fdc(RRState *s);
void rr_state_fdd(RRState *s);
void rr_state_dim(RRState *s);
void rr_state_xdf(RRState *s);
void rr_state_sasi(RRState *s);
void rr_state_rtc(RRState *s);
void rr_state_pia(RRState *s);
void rr_state_sysport(RRState *s);
void rr_state_sram(RRState *s);
void rr_state_adpcm(RRState *s);
void rr_state_midi(RRState *s);
void rr_state_dswin(RRState *s);
void rr_state_mouse(RRState *s);
void rr_state_opm(RRState *s);
void rr_state_presented(RRState *s);
void TVRAM_SetAllDirty(void);

extern uint16_t *videoBuffer;
/* Musashi slice counters (m68kcpu.c; not declared by every m68kcpu.h). */
extern int m68ki_remaining_cycles, m68ki_initial_cycles;

static void cpu(RRState *s)
{
   m68ki_cpu_core *c = &m68ki_cpu;
   unsigned i;
   /* The header seen here must describe the linked core (see includes). */
   if (m68k_context_size() != sizeof(m68ki_cpu_core)) {
      rr_state_fail(s, "CPU core layout differs from this build");
      return;
   }
   for (i = 0; i < 16; i++) rr_state_uint(s, &c->dar[i]);
   for (i = 0; i < 16; i++) rr_state_uint(s, &c->dar_save[i]);
   rr_state_uint(s, &c->ppc); rr_state_uint(s, &c->pc);
   for (i = 0; i < 7; i++) rr_state_uint(s, &c->sp[i]);
   rr_state_uint(s, &c->vbr); rr_state_uint(s, &c->sfc); rr_state_uint(s, &c->dfc);
   rr_state_uint(s, &c->cacr); rr_state_uint(s, &c->caar); rr_state_uint(s, &c->ir);
   rr_state_uint(s, &c->t1_flag); rr_state_uint(s, &c->t0_flag); rr_state_uint(s, &c->s_flag);
   rr_state_uint(s, &c->m_flag); rr_state_uint(s, &c->x_flag); rr_state_uint(s, &c->n_flag);
   rr_state_uint(s, &c->not_z_flag); rr_state_uint(s, &c->v_flag); rr_state_uint(s, &c->c_flag);
   rr_state_uint(s, &c->int_mask); rr_state_uint(s, &c->int_level); rr_state_uint(s, &c->stopped);
   rr_state_uint(s, &c->pref_addr); rr_state_uint(s, &c->pref_data);
   rr_state_uint(s, &c->instr_mode); rr_state_uint(s, &c->run_mode);
   rr_state_uint(s, &c->reset_cycles); rr_state_uint(s, &c->virq_state);
   rr_state_uint(s, &c->nmi_pending);
   /* Cycle pool of the last slice: the native STOP handling reads it before
    * the next m68k_execute replaces it. */
   rr_state_int(s, &m68ki_remaining_cycles);
   rr_state_int(s, &m68ki_initial_cycles);
   rr_state_int(s, &ICount);
   rr_state_int(s, &m68000_ICountBk);
}

static void keyboard(RRState *s)
{
   rr_state_bytes(s, KeyBuf, sizeof KeyBuf);
   rr_state_u8(s, &KeyBufWP);
   rr_state_u8(s, &KeyBufRP);
   rr_state_u8(s, &KeyIntFlag);
   if (s->loading && !s->error && (KeyBufWP >= KeyBufSize || KeyBufRP >= KeyBufSize))
      rr_state_fail(s, "keyboard queue position outside its buffer");
}

static void bus(RRState *s)
{
   /* A session snapshot stores the 10 MB the bus writes (mem_wrap: RAM below 0xa00000, bus error above). */
   rr_state_bus_words(s, MEM, s->session ? 0xa00000 : 0xc00000);
   rr_state_u32(s, &BusErrFlag);
   rr_state_u8(s, &IOC_IntStat);
   rr_state_u8(s, &IOC_IntVect);
}

static void host(RRState *s)
{
   uint64_t counters[8];
   unsigned i;
   rr_x68k_hardware_snapshot(counters);
   for (i = 0; i < 8; i++)
      rr_state_u64(s, &counters[i]);
   if (s->session)
      rr_state_presented(s);
   if (!videoBuffer) {
      rr_state_fail(s, "machine is not booted");
      return;
   }
   /* Only dirty lines are redrawn: the presented picture is machine state in a quick state. A session snapshot leaves it
    * out and marks every text line dirty on load, so the next frame draws the whole picture again (proven by the rollback
    * probe, which compares the presented picture of every replayed frame). */
   if (!s->session && !s->no_picture)
      rr_state_u16s(s, videoBuffer, 800 * 600);
   if (s->session && s->loading && !s->error)
      TVRAM_SetAllDirty();
   if (s->loading && !s->error)
      rr_x68k_hardware_restore(counters);
}

typedef struct {
   char tag[5];
   void (*visit)(RRState *s);
} Section;

static const Section sections[] = {
   {"MAIN", rr_state_main}, {"CPU ", cpu}, {"BUS ", bus},
   {"GVRM", rr_state_gvram}, {"TVRM", rr_state_tvram}, {"CRTC", rr_state_crtc},
   {"PALT", rr_state_palette}, {"BGSP", rr_state_bg}, {"DMAC", rr_state_dmac},
   {"MFP ", rr_state_mfp}, {"IRQH", rr_state_irqh}, {"SCC ", rr_state_scc},
   {"FDC ", rr_state_fdc}, {"FDD ", rr_state_fdd}, {"DIMD", rr_state_dim},
   {"XDFD", rr_state_xdf}, {"SASI", rr_state_sasi}, {"RTC ", rr_state_rtc},
   {"PIA ", rr_state_pia}, {"SYSP", rr_state_sysport}, {"SRAM", rr_state_sram},
   {"DSND", rr_state_dswin}, {"ADPC", rr_state_adpcm}, {"MIDI", rr_state_midi},
   {"OPM ", rr_state_opm}, {"KEYB", keyboard}, {"MOUS", rr_state_mouse},
   {"INPT", rr_state_input}, {"HOST", host}
};

void rr_x68k_session_disks(RRState *s, size_t *bytes);
static size_t journal_bytes;   /* journal blocks of the last session visit */
extern uint8_t TextDirtyLine[1024];
static uint8_t dirty_lines[1024];
/* The work buffers of the line being drawn: written before they are read for every line drawn (the rollback probe compares
 * the picture of every replayed frame), so a session snapshot and the digest store them empty. */
extern uint8_t Text_TrFlag[1024];
extern uint16_t BG_LineBuf[1600], BG_PriBuf[1600];
extern uint16_t Grp_LineBuf[1024], Grp_LineBufSP[1024], Grp_LineBufSP2[1024];
extern uint32_t VLINEBG;          /* set by WinDraw_DrawLine before each line's BG */
static struct {
   uint8_t tr[1024];
   uint16_t bg[1600], pri[1600], grp[3][1024];
   uint32_t vlinebg;
} line_work;

static void line_buffers(int keep)
{
   uint16_t *grp[3] = {Grp_LineBuf, Grp_LineBufSP, Grp_LineBufSP2};
   unsigned i;
   if (keep) {
      memcpy(line_work.tr, Text_TrFlag, sizeof line_work.tr);
      memcpy(line_work.bg, BG_LineBuf, sizeof line_work.bg);
      memcpy(line_work.pri, BG_PriBuf, sizeof line_work.pri);
      for (i = 0; i < 3; i++) memcpy(line_work.grp[i], grp[i], sizeof line_work.grp[i]);
      line_work.vlinebg = VLINEBG;
      VLINEBG = 0;
      memset(Text_TrFlag, 0, sizeof line_work.tr);
      memset(BG_LineBuf, 0, sizeof line_work.bg);
      memset(BG_PriBuf, 0, sizeof line_work.pri);
      for (i = 0; i < 3; i++) memset(grp[i], 0, sizeof line_work.grp[i]);
   } else {
      memcpy(Text_TrFlag, line_work.tr, sizeof line_work.tr);
      memcpy(BG_LineBuf, line_work.bg, sizeof line_work.bg);
      memcpy(BG_PriBuf, line_work.pri, sizeof line_work.pri);
      for (i = 0; i < 3; i++) memcpy(grp[i], line_work.grp[i], sizeof line_work.grp[i]);
      VLINEBG = line_work.vlinebg;
   }
}

static int visit(RRState *s)
{
   uint8_t magic[8];
   uint16_t format = RR_STATE_FORMAT;
   uint32_t ram = (uint32_t)Config.ram_size, count = sizeof sections / sizeof sections[0];
   uint32_t stored_ram = ram, stored_count = count;
   unsigned i;

   memcpy(magic, RR_STATE_MAGIC, 8);
   rr_state_bytes(s, magic, 8);
   rr_state_u16(s, &format);
   rr_state_u32(s, &stored_ram);
   rr_state_u32(s, &stored_count);
   if (s->loading && !s->error) {
      if (memcmp(magic, RR_STATE_MAGIC, 8) || format != RR_STATE_FORMAT)
         rr_state_fail(s, "not an RRX68MS1 snapshot");
      else if (stored_ram != ram)
         rr_state_fail(s, "snapshot RAM size differs from this machine");
      else if (stored_count != count)
         rr_state_fail(s, "snapshot section count differs");
   }
   /* The marks of the background patterns changed since the last line drawn are part of the saved picture state. */
   rr_bg_state_sync(s->loading);
   /* A session snapshot starts with its disks: the drives must hold their images before the device sections load. */
   if (s->session && !s->error) {
      size_t mark = rr_state_begin(s, "JRNL", 1);
      rr_x68k_session_disks(s, &journal_bytes);
      rr_state_end(s, mark);
   }
   /* The text lines' redraw marks only say which lines the next frame draws again. A session snapshot and the digest store
    * them all set (a load redraws the whole picture), so two seats that loaded at different frames keep equal digests. */
   if (s->session && !s->loading) {
      memcpy(dirty_lines, TextDirtyLine, sizeof dirty_lines);
      memset(TextDirtyLine, 1, sizeof dirty_lines);
      line_buffers(1);
   }
   for (i = 0; i < count && !s->error; i++) {
      size_t mark = rr_state_begin(s, sections[i].tag, 1);
      sections[i].visit(s);
      rr_state_end(s, mark);
   }
   if (s->session && !s->loading) {
      memcpy(TextDirtyLine, dirty_lines, sizeof dirty_lines);
      line_buffers(0);
   }
   if (s->loading && !s->error && s->pos != s->size)
      rr_state_fail(s, "trailing bytes after the last snapshot section");
   if (s->error && log_cb)
      log_cb(RETRO_LOG_WARN, "X68000 snapshot rejected: %s\n", s->reason ? s->reason : "unknown");
   return !s->error;
}

size_t retro_serialize_size(void)
{
   RRState s;
   memset(&s, 0, sizeof s);
   return visit(&s) ? s.size : 0;
}

bool retro_serialize(void *data, size_t size)
{
   RRState s;
   bool ok;
   memset(&s, 0, sizeof s);
   s.data = (uint8_t *)malloc(size ? size : 1);
   if (!s.data)
      return false;
   s.capacity = size;
   memset(s.data, 0, s.capacity);
   ok = visit(&s) && s.size == size;
   if (ok)
      memcpy(data, s.data, size);
   free(s.data);
   return ok;
}

bool retro_unserialize(const void *data, size_t size)
{
   RRState s;
   memset(&s, 0, sizeof s);
   s.data = (uint8_t *)data;
   s.size = size;
   s.loading = 1;
   return visit(&s) != 0;
}

/* ---- Multiplayer snapshot (RrhkMachine snap_bound / snap_save / snap_load / digest) ----
 * In process only: the caller's buffer, no allocation, arrays copied as they are in memory. The disks are journals,
 * bounded by RR_X68K_SESSION_JOURNAL bytes of written blocks for the whole set and the drives: a session that writes
 * more cannot be saved (the kit ends it with the reason). */
#define RR_X68K_SESSION_JOURNAL (512u * 1024u)

static void session_state(RRState *s, int loading)
{
   memset(s, 0, sizeof *s);
   s->loading = loading;
   s->fixed = s->raw = s->session = 1;
}

void rr_x68k_boot(void);

/* The kit asks the bound before the first frame (at its HELLO and SETUP): the machine boots first. */
size_t rr_x68k_snap_bound(void)
{
   RRState s;
   rr_x68k_boot();
   session_state(&s, 0);
   journal_bytes = 0;
   return visit(&s) ? s.size - journal_bytes + RR_X68K_SESSION_JOURNAL : 0;
}

size_t rr_x68k_snap_save(void *buffer, size_t capacity)
{
   RRState s;
   if (!buffer)
      return 0;
   session_state(&s, 0);
   s.data = (uint8_t *)buffer;
   s.capacity = capacity;
   journal_bytes = 0;
   return visit(&s) ? s.size : 0;
}

int rr_x68k_snap_load(const void *buffer, size_t size)
{
   RRState s;
   if (!buffer || !size)
      return 0;
   session_state(&s, 1);
   s.data = (uint8_t *)buffer;
   s.size = size;
   return visit(&s);
}

/* The digest the seats compare: the session snapshot without the picture, 64-bit FNV-1a over its words. */
uint64_t rr_x68k_digest(void)
{
   static uint8_t *buffer;
   static size_t capacity;
   const size_t bound = rr_x68k_snap_bound();
   uint64_t hash = 14695981039346656037ull, word;
   RRState s;
   size_t i;
   if (!bound)
      return 0;
   if (bound > capacity) {
      free(buffer);
      buffer = (uint8_t *)malloc(bound);
      capacity = buffer ? bound : 0;
      if (!buffer)
         return 0;
   }
   session_state(&s, 0);
   s.no_picture = 1;
   s.data = buffer;
   s.capacity = capacity;
   journal_bytes = 0;
   if (!visit(&s))
      return 0;
   for (i = 0; i + 8 <= s.size; i += 8) {
      memcpy(&word, buffer + i, 8);
      hash = (hash ^ word) * 1099511628211ull;
   }
   for (; i < s.size; i++)
      hash = (hash ^ buffer[i]) * 1099511628211ull;
   return hash;
}
