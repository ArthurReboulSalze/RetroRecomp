/* Retro-Recomp X68000 MIT host glue: boot, reset, frame scheduling, timer.
 *
 * Copyright (c) 2026 Retro-Recomp contributors. MIT License (see LICENSE).
 *
 * Independently written from docs/X68000_GLUE_SPEC.md sections 2.5-3.6 and
 * 6.2. Sources consulted: that specification, the machine-side headers it
 * names and our native/x68000_reference host. No code from libretro.c,
 * libretro/joystick.c or libretro/timer.c is used.
 */
#include <stdlib.h>
#include <string.h>

#include "glue.h"
#include "winx68k.h"
#include "prop.h"
#include "winui.h"
#include "windraw.h"
#include "dswin.h"
#include "keyboard.h"
#include "mouse.h"
#include "joystick.h"
#include "timer.h"
#include "dosio.h"
#include "../m68000/m68000.h"
#ifdef RR_X68000_BASE74
#include "m68k.h"
#include "memory.h"
#else
#include "../x68k/x68kmemory.h"
#endif
#include "../x68k/adpcm.h"
#include "../x68k/bg.h"
#include "../x68k/crtc.h"
#include "../x68k/dmac.h"
#include "../x68k/fdc.h"
#include "../x68k/fdd.h"
#include "../x68k/gvram.h"
#include "../x68k/ioc.h"
#include "../x68k/irqh.h"
#include "../x68k/mfp.h"
#include "../x68k/midi.h"
#include "../x68k/palette.h"
#include "../x68k/pia.h"
#include "../x68k/rtc.h"
#include "../x68k/sasi.h"
#include "../x68k/scc.h"
#include "../x68k/scsi.h"
#include "../x68k/sram.h"
#include "../x68k/sysport.h"
#include "../x68k/tvram.h"
#include "../fmgen/fmg_wrap.h"
#include "hardware_clock.h"
#include "state/rr_state.h"

#ifdef _WIN32
#define RR_SLASH "\\"
#else
#define RR_SLASH "/"
#endif

/* Globals that the machine sources and our checks read (spec section 7). */
uint16_t VLINE_TOTAL = 567;
uint32_t VLINE = 0;
uint32_t vline = 0;               /* winx68k.h maps this name to HOGEvline. */
char winx68k_dir[2048];
char winx68k_ini[2048];
int CHANGEAV = 0;
int CHANGEAV_TIMING = 0;
int VID_MODE = 0;

/* Timer gate state (spec 3.5). */
uint32_t tick = 0;
uint32_t timercnt = 0;
extern unsigned int total_usec;

uint8_t rr_glue_disp_frame = 0;
static int clk_used = 0;
static int frame_skip_count = 0;
static int frame_skip_queue = 0;   /* Deterministic: never fed by wall time. */
static uint32_t old_ram_size = 0;
static int old_clkdiv = 0;

extern char filepath[MAX_PATH];
extern char rr_glue_browse_conf[];
extern uint32_t retrow, retroh;
extern int rr_glue_oldrw, rr_glue_oldrh;

/* ---- ROM loading (spec 2.7) ---- */

static const uint8_t fake_scsi_bios[46] = {
   0x00, 0xfc, 0x00, 0x14,                         /* boot entry $FC0014 */
   0x00, 0xfc, 0x00, 0x16,                         /* IOCS vector set entry */
   0x00, 0x00, 0x00, 0x00,
   'H', 'u', 'm', 'a', 'n', '6', '8', 'k',
   0x4e, 0x75,                                     /* rts */
   0x23, 0xfc, 0x00, 0xfc, 0x00, 0x2a, 0x00, 0x00, 0x07, 0xd4,
   0x74, 0xff,                                     /* moveq #-1,d2 */
   0x4e, 0x75,                                     /* rts */
   'D', 'U', 'M', 'M', 'Y', ' ',
   0x70, 0xff,                                     /* moveq #-1,d0 */
   0x4e, 0x75                                      /* rts */
};

bool rr_glue_load_roms(void)
{
   static const char *const ipl_names[] = {
      "iplrom.dat", "iplrom30.dat", "iplromco.dat", "iplromxv.dat"
   };
   void *file = NULL;
   unsigned i;
   bool scsi = false;

   for (i = 0; i < sizeof ipl_names / sizeof ipl_names[0] && !file; i++)
      file = file_open_c(ipl_names[i]);
   if (!file) {
      if (log_cb)
         log_cb(RETRO_LOG_ERROR, "[PX68K] Error: BIOS ROM image can't be found.\n");
      return false;
   }
   file_lread(file, &IPL[0x20000], 0x20000);
   file_close(file);

   for (i = 0x30600; i < 0x30c00 && !scsi; i += 2)
      scsi = IPL[i] == 0x00 && IPL[i + 1] == 0xfc && IPL[i + 2] == 0x00 && IPL[i + 3] == 0x00;
   if (scsi) {
      memset(IPL, 0x00, 0x2000);
      memset(&IPL[0x2000], 0xff, 0x1e000);
      memcpy(IPL, fake_scsi_bios, sizeof fake_scsi_bios);
   } else {
      memcpy(IPL, &IPL[0x20000], 0x20000);
   }
   for (i = 0; i < 0x40000; i += 2) {
      uint8_t byte = IPL[i];
      IPL[i] = IPL[i + 1];
      IPL[i + 1] = byte;
   }

   file = file_open_c("cgrom.dat");
   if (!file)
      file = file_open_c("cgrom.tmp");
   if (!file)
      return false;
   file_lread(file, FONT, 0xc0000);
   file_close(file);
   return true;
}

/* ---- Reset (spec 2.9) ---- */

static uint32_t ipl_long(unsigned offset)
{
   /* IPL is stored in host word order; rebuild the ROM's big-endian long. */
   return ((uint32_t)IPL[offset + 1] << 24) | ((uint32_t)IPL[offset] << 16) |
          ((uint32_t)IPL[offset + 3] << 8) | IPL[offset + 2];
}

void WinX68k_Reset(void)
{
   OPM_Reset();
   m68k_pulse_reset();
   m68k_set_reg(M68K_REG_A7, ipl_long(0x30000));
   m68k_set_reg(M68K_REG_PC, ipl_long(0x30004));

   Memory_Init();
   CRTC_Init();
   DMA_Init();
   MFP_Init();
   FDC_Init();
   FDD_Reset();
   SASI_Init();
   SCSI_Init();
   IOC_Init();
   SCC_Init();
   PIA_Init();
   RTC_Init();
   TVRAM_Init();
   GVRAM_Init();
   BG_Init();
   Pal_Init();
   IRQH_Init();
   MIDI_Init();
   Keyboard_Init();

   m68000_ICountBk = 0;
   ICount = 0;

   DSound_Stop();
   SRAM_VirusCheck();
   DSound_Play();
}

/* ---- Deferred boot on the first frame (spec 2.5.1) ---- */

void rr_glue_boot(int argc, char **argv)
{
   unsigned i;

   strncpy(winx68k_dir, rr_glue_system_conf, sizeof winx68k_dir - 1);
   winx68k_dir[sizeof winx68k_dir - 1] = 0;
   snprintf(winx68k_ini, sizeof winx68k_ini, "%s%sconfig", rr_glue_system_conf, RR_SLASH);
   file_setcd(winx68k_dir);
   LoadConfig();
   if (rr_glue_browse_conf[0]) {
      strncpy(filepath, rr_glue_browse_conf, MAX_PATH - 1);
      filepath[MAX_PATH - 1] = 0;
   }
   WinDraw_MenuInit();
   WinUI_Init();
   m68000_init();
   if (!rr_glue_load_roms())
      return;
   Keyboard_Init();
   WinDraw_Init();
#ifdef RR_X68000_BASE74
   ADPCM_Init(RR_SOUND_RATE);
#else
   ADPCM_Init();
#endif
   FDD_Init();
   SysPort_Init();
   Mouse_Init();
   Joystick_Init();
   SRAM_Init();
   WinX68k_Reset();
   Timer_Init();
   MIDI_Init();
   MIDI_SetMimpiMap(Config.ToneMapFile);
   MIDI_EnableMimpiDef(Config.ToneMap);
   ADPCM_SetVolume((uint8_t)Config.PCM_VOL);
   OPM_SetVolume((uint8_t)Config.OPM_VOL);
   DSound_Play();

   if (argc >= 2) {
      memset(Config.FDDImage, 0, sizeof Config.FDDImage);
      memset(Config.HDImage, 0, sizeof Config.HDImage);
      for (i = 1; i < (unsigned)argc && i <= 2; i++) {
         strncpy(Config.FDDImage[i - 1], argv[i], MAX_PATH - 1);
         Config.FDDImage[i - 1][MAX_PATH - 1] = 0;
      }
   }
   FDD_SetFD(0, Config.FDDImage[0], 0);
   FDD_SetFD(1, Config.FDDImage[1], 0);
}

/* ---- Timer gate (spec 3.5) ---- */

static uint32_t timer_source(void)
{
   return total_usec;
}

void Timer_Init(void)
{
   tick = timer_source();
}

uint16_t Timer_GetCount(void)
{
   uint32_t now = timer_source();
   uint32_t difference = now - tick;
   uint32_t base = (CRTC_Regs[0x29] & 0x10) ? 180310u : 162707u;

   timercnt += difference * 10u;
   tick = now;
   if (timercnt >= base) {
      timercnt -= base;
      if (timercnt >= 2u * base)
         timercnt = 0;
      return 1;
   }
   return 0;
}

/* ---- One emulated frame (spec 3.6) ---- */

static void draw_line_if_visible(void)
{
   if (rr_glue_disp_frame != 0 || vline < CRTC_VSTART || vline >= CRTC_VEND)
      return;
   if (CRTC_VStep == 1) {
      if (vline & 1)
         WinDraw_DrawLine();
   } else if (CRTC_VStep == 4) {
      WinDraw_DrawLine();
      VLINE++;
      WinDraw_DrawLine();
   } else {
      WinDraw_DrawLine();
   }
}

void rr_glue_exec_frame(void)
{
   int clk_total, clkdiv, usedclk, clk_next, clk_count, clk_line = 0;
   int key_interval = 0, mouse_interval = 0, slice, used;
   bool hsync;

   if (cpu_readmem24_dword(0xed0008) != (uint32_t)Config.ram_size) {
      cpu_writemem24(0xe8e00d, 0x31);
      cpu_writemem24_dword(0xed0008, (uint32_t)Config.ram_size);
   }
   if (Config.FrameRate != 7)
      rr_glue_disp_frame = (uint8_t)((rr_glue_disp_frame + 1) % Config.FrameRate);

   vline = 0;
   clk_count = -ICount;
   clk_total = (CRTC_Regs[0x29] & 0x10) ? 180310 : 162707;
   clk_total = clk_total * Config.clockmhz / 10;
   clkdiv = Config.clockmhz;
   if (clkdiv != old_clkdiv || (uint32_t)Config.ram_size != old_ram_size) {
      old_clkdiv = clkdiv;
      old_ram_size = (uint32_t)Config.ram_size;
   }
   rr_x68k_hardware_frame((unsigned)clk_total);
   ICount += clk_total;
   clk_next = clk_total / VLINE_TOTAL;
   hsync = true;

   do {
      slice = ICount > 200 ? 200 : ICount;
      if (hsync) {
         hsync = false;
         clk_line = 0;
         MFP_Int(0);
         if (vline >= CRTC_VSTART && vline < CRTC_VEND)
            VLINE = ((vline - CRTC_VSTART) * CRTC_VStep) / 2;
         else
            VLINE = 0xffffffffu;
         if (!(MFP[MFP_AER] & 0x40) && vline == CRTC_IntLine)
            MFP_Int(1);
         if (MFP[MFP_AER] & 0x10) {
            if (vline == CRTC_VSTART)
               MFP_Int(9);
         } else if (CRTC_VEND >= VLINE_TOTAL) {
            if ((int)vline == (int)CRTC_VEND - (int)VLINE_TOTAL)
               MFP_Int(9);
         } else if (vline == (uint32_t)(VLINE_TOTAL - 1)) {
            MFP_Int(9);
         }
      }

      {
         int remaining = m68k_execute(slice);
         m68000_ICountBk = slice - remaining;
         used = slice - m68000_ICountBk;
      }
      clk_used += used * 10;
      usedclk = clk_used / clkdiv;
      clk_line += usedclk;
      rr_x68k_hardware_tick((unsigned)used, (unsigned)usedclk);
      clk_used -= usedclk * clkdiv;
      ICount -= used;
      clk_count += used;

      MFP_Timer(usedclk);
      RTC_Timer(usedclk);
      DMA_Exec(0);
      DMA_Exec(1);
      DMA_Exec(2);

      if (clk_count >= clk_next) {
         MIDI_DelayOut(Config.MIDIAutoDelay ? Config.BufferSize * 5 : (unsigned)Config.MIDIDelay);
         MFP_TimerA();
         if ((MFP[MFP_AER] & 0x40) && vline == CRTC_IntLine)
            MFP_Int(1);
         draw_line_if_visible();
         ADPCM_PreUpdate((uint32_t)clk_line);
         OPM_Timer((uint32_t)clk_line);
         MIDI_Timer((uint32_t)clk_line);
         if (++key_interval > VLINE_TOTAL / 4) {
            key_interval = 0;
            Keyboard_Int();
         }
         if (++mouse_interval > VLINE_TOTAL / 8) {
            mouse_interval = 0;
            SCC_IntCheck();
         }
         DSound_Send0(clk_line);
         rr_x68k_hardware_line();
         vline++;
         clk_next = (int)(((uint32_t)clk_total * (vline + 1)) / VLINE_TOTAL);
         hsync = true;
      }
   } while (vline < VLINE_TOTAL);

   if (CRTC_Mode & 2) {
      if (CRTC_FastClr) {
         CRTC_FastClr--;
         if (!CRTC_FastClr)
            CRTC_Mode &= 0xfd;
      } else {
         CRTC_FastClr = (CRTC_Regs[0x29] & 0x10) ? 1 : 2;
         TVRAM_SetAllDirty();
         GVRAM_FastClear();
      }
   }
   FDD_SetFDInt();
   if (rr_glue_disp_frame == 0)
      WinDraw_Draw();
}

/* ---- Snapshot section MAIN: frame scheduling and presentation state. ---- */

void rr_state_main(RRState *s)
{
   rr_state_int(s, &clk_used);
   rr_state_u32(s, &VLINE);
   rr_state_u16(s, &VLINE_TOTAL);
   rr_state_u32(s, &vline);
   rr_state_u32(s, &retrow);
   rr_state_u32(s, &retroh);
   rr_state_u8(s, &rr_glue_disp_frame);
   rr_state_int(s, &frame_skip_count);
   rr_state_int(s, &frame_skip_queue);
   rr_state_f32(s, &rr_glue_framerate);
   rr_state_int(s, &VID_MODE);
   rr_state_uint(s, &total_usec);
   rr_state_int(s, &CHANGEAV);
   rr_state_int(s, &CHANGEAV_TIMING);
   rr_state_int(s, &rr_glue_oldrw);
   rr_state_int(s, &rr_glue_oldrh);
   rr_state_int(s, &rr_glue_firstcall);
   rr_state_u32(s, &old_ram_size);
   rr_state_int(s, &old_clkdiv);
   rr_state_u32(s, &tick);
   rr_state_u32(s, &timercnt);
   if (s->loading && !s->error && (!VLINE_TOTAL || retrow > 2048 || retroh > 2048))
      rr_state_fail(s, "invalid frame geometry");
}
