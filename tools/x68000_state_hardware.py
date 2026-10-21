"""MIT machine snapshot serializers appended to pinned X68000 build copies.

Phase 2 of docs/X68000_GPL_FREE_PLAN.md. Each module receives one function,
written for Retro-Recomp, that visits its mutable state through the RRX68MS1
API (native/x68000_machine/state/rr_state.h). Upstream checkouts are never
edited; digests and anchors are verified by tools/x68000_hardware.py. Only
used by the MIT glue build (RR_X68000_MIT_GLUE).
"""
from __future__ import annotations

HASHES = {
    'x68k/gvram.c': 'bc872653f189269a2fe311ceb690ced8d406d47ead908d080fb633b4160cf2a0',
    'x68k/tvram.c': 'c1dbd673f7514facb3e80986e62097eabcd2922fe56463074b23d05399ccbcac',
    'x68k/crtc.c': 'ef27bc7daf034a3bf7a696376db1ef7ff5a7c056c63fcbec573fdfa4c4eb6490',
    'x68k/palette.c': 'a70e616f81f09fdc7d80e7fd22a442d25b168de3c322a47dbe220612ddcabc21',
    'x68k/bg.c': 'fc700c8f1cb148f6bfa3329f53097a8e55513a9cdabfef15690f42f0a499b0c1',
    'x68k/dmac.c': 'fa2cc30b15898bc7f065744ae855576f519640cbcf996ddf87147f311dcfcc6c',
    'x68k/mfp.c': '4a295a9b956b6e9aaeac0d45f238259b14ffed52032097cfe78dafde5963815c',
    'x68k/irqh.c': 'ca3f5cbc20bf90474c4d95b264d0f9e490e55d238148b744ce498e481b0dc488',
    'x68k/scc.c': 'a1bcaf0ff2dd90047e49981bc014ea4d7cf0b56a0374b09151561619c39d1f78',
    'x68k/fdc.c': '86b906a86e21c1abf6b667fb8437bd2a5ddbbc933b29e9087fb49dddadc9428d',
    'x68k/fdd.c': 'f1a882b7dcb008ed93be93ec5fdcc36e1172b67d9271d3ebc696cb6594a624bb',
    'x68k/disk_dim.c': '3a861eae50cfaf17d407f51bc09b0408d17bb5039071ce3c8af662458717626d',
    'x68k/disk_xdf.c': '6b63866a4487bf7102feb374e297f3baccc03ae113a6196ae7855280ff23b609',
    'x68k/sasi.c': 'eb326b0ce46bf4a29f11bcbbce9848bcef2aae4ebed7248346b18c79fc06bb47',
    'x68k/rtc.c': '5e0ac824ad8e6b4e490aebce8329c171c0a4c9091763a07fd82eac3d84a6825f',
    'x68k/pia.c': '56d5ca6094c0e39d7df3d09ad81243cd6db1502870f9aac9aecc481fd2eb298a',
    'x68k/sysport.c': '2f02ab41417b3f701890093493644f8a4915755309c1b86b1d770c14d2b6db61',
    'x68k/sram.c': '77b2046a918f82d8fb166e4b00b9b68187e36c4acfc97de791cdf42c93318825',
    'x68k/adpcm.c': '3e65d30381787bfcdaaebaf410bc8d4948769c081f5f004b3c6e459cf34cc805',
    'x68k/midi.c': 'c25a10840baac909a48bf5671f34c075899b1b79da8e1ea507db934283a1eab7',
    'libretro/dswin.c': '6e909ed1c6278e56827c18e4ae614a22ad5560a095bba7a36ddb4badd70abe4c',
    'libretro/mouse.c': 'd72a34ba83f1920e8d7a8518db9f5d0361c3cf35a17c583750e3ba9e49e9fe62',
    'fmgen/fmg_wrap.cpp': '9276a17247da0cf6cd06164181d817a6056a2746a2f72491dd46514d8a4a5205',
    'fmgen/fmgen.h': 'e625789d8311953a535633539a2f9105b8282411333f1122bf4aa0709f15019f',
    'fmgen/opm.h': 'eda9e609567dcabd9ff6c81cd522b7f31ec942bc96223dea9ee00f6f0f465803',
    'fmgen/fmtimer.h': '50f4ea1da436775c59a4ba4b4a136e7c7a102e94a66723d6613b6764924a3c6a',
}

HEADER = '\n/* ---- Retro-Recomp RRX68MS1 serializer (MIT, tools/x68000_state_hardware.py) ---- */\n#include <string.h>\n#include "rr_state.h"\n'

# Module bodies: C statements visiting the module's state with `s`.
C_BODIES = {
    'x68k/gvram.c': ('gvram', '''
   rr_state_bus_words(s, GVRAM, sizeof GVRAM);
   rr_state_u16s(s, Grp_LineBuf, 1024);
   rr_state_u16s(s, Grp_LineBufSP, 1024);
   rr_state_u16s(s, Grp_LineBufSP2, 1024);
   rr_state_u16s(s, Grp_LineBufSP_Tr, 1024);
'''),
    'x68k/tvram.c': ('tvram', '''
   rr_state_bus_words(s, TVRAM, sizeof TVRAM);
   rr_state_bytes(s, TextDrawWork, sizeof TextDrawWork);
   rr_state_bytes(s, TextDirtyLine, sizeof TextDirtyLine);
   rr_state_bytes(s, Text_TrFlag, sizeof Text_TrFlag);
'''),
    'x68k/crtc.c': ('crtc', '''
   rr_state_bytes(s, CRTC_Regs, sizeof CRTC_Regs);
   rr_state_u8(s, &CRTC_Mode);
   rr_state_u32(s, &TextDotX); rr_state_u32(s, &TextDotY);
   rr_state_u16(s, &CRTC_VSTART); rr_state_u16(s, &CRTC_VEND);
   rr_state_u16(s, &CRTC_HSTART); rr_state_u16(s, &CRTC_HEND);
   rr_state_u32(s, &TextScrollX); rr_state_u32(s, &TextScrollY);
   rr_state_u32s(s, GrphScrollX, 4); rr_state_u32s(s, GrphScrollY, 4);
   rr_state_u8(s, &CRTC_FastClr);
   rr_state_u8(s, &CRTC_SispScan);
   rr_state_u32(s, &CRTC_FastClrLine);
   rr_state_u16(s, &CRTC_FastClrMask);
   rr_state_u16(s, &CRTC_IntLine);
   rr_state_u8(s, &CRTC_VStep);
   rr_state_bytes(s, VCReg0, 2); rr_state_bytes(s, VCReg1, 2); rr_state_bytes(s, VCReg2, 2);
   rr_state_bytes(s, CRTC_RCFlag, 2);
   rr_state_int(s, &HSYNC_CLK);
'''),
    'x68k/palette.c': ('palette', '''
   rr_state_bytes(s, Pal_Regs, sizeof Pal_Regs);
   rr_state_u16s(s, TextPal, 256);
   rr_state_u16s(s, GrphPal, 256);
   rr_state_u16s(s, Pal16, 65536);
   rr_state_u16(s, &Ibit);
   rr_state_u16(s, &Pal_HalfMask); rr_state_u16(s, &Pal_Ix2);
   rr_state_u16(s, &Pal_R); rr_state_u16(s, &Pal_G); rr_state_u16(s, &Pal_B);
'''),
    'x68k/bg.c': ('bg', '''
   rr_state_bytes(s, BG, sizeof BG);
   rr_state_bus_words(s, Sprite_Regs, sizeof Sprite_Regs);
   rr_state_bytes(s, BG_Regs, sizeof BG_Regs);
   rr_state_u16(s, &BG_CHREND); rr_state_u16(s, &BG_BG0TOP); rr_state_u16(s, &BG_BG0END);
   rr_state_u16(s, &BG_BG1TOP); rr_state_u16(s, &BG_BG1END);
   rr_state_u8(s, &BG_CHRSIZE);
   rr_state_u32(s, &BG_AdrMask);
   rr_state_u32(s, &BG0ScrollX); rr_state_u32(s, &BG0ScrollY);
   rr_state_u32(s, &BG1ScrollX); rr_state_u32(s, &BG1ScrollY);
   rr_state_i32(s, &BG_HAdjust); rr_state_i32(s, &BG_VLINE);
   rr_state_bytes(s, BGCHR8, sizeof BGCHR8);
   rr_state_bytes(s, BGCHR16, sizeof BGCHR16);
   rr_state_u16s(s, BG_LineBuf, 1600);
   rr_state_u16s(s, BG_PriBuf, 1600);
   rr_state_u32(s, &VLINEBG);
'''),
    'x68k/dmac.c': ('dmac', '''
   unsigned ch;
   for (ch = 0; ch < 4; ch++) {
      dmac_ch *c = &DMA[ch];
      rr_state_u8(s, &c->CSR); rr_state_u8(s, &c->CER); rr_state_bytes(s, c->dmy0, sizeof c->dmy0);
      rr_state_u8(s, &c->DCR); rr_state_u8(s, &c->OCR); rr_state_u8(s, &c->SCR); rr_state_u8(s, &c->CCR);
      rr_state_bytes(s, c->dmy1, sizeof c->dmy1);
      rr_state_u16(s, &c->MTC); rr_state_u32(s, &c->MAR);
      rr_state_bytes(s, c->dmy2, sizeof c->dmy2);
      rr_state_u32(s, &c->DAR);
      rr_state_bytes(s, c->dmy3, sizeof c->dmy3);
      rr_state_u16(s, &c->BTC); rr_state_u32(s, &c->BAR);
      rr_state_bytes(s, c->dmy4, sizeof c->dmy4);
      rr_state_u8(s, &c->NIV); rr_state_u8(s, &c->dmy5); rr_state_u8(s, &c->EIV); rr_state_u8(s, &c->dmy6);
      rr_state_u8(s, &c->MFC); rr_state_bytes(s, c->dmy7, sizeof c->dmy7);
      rr_state_u8(s, &c->CPR); rr_state_bytes(s, c->dmy8, sizeof c->dmy8);
      rr_state_u8(s, &c->DFC); rr_state_bytes(s, c->dmy9, sizeof c->dmy9);
      rr_state_u8(s, &c->BFC); rr_state_bytes(s, c->dmya, sizeof c->dmya);
      rr_state_u8(s, &c->GCR);
   }
   rr_state_int(s, &DMA_IntCH);
   rr_state_int(s, &DMA_LastInt);
'''),
    'x68k/mfp.c': ('mfp', '''
   rr_state_bytes(s, MFP, sizeof MFP);
   rr_state_u8(s, &LastKey);
   rr_state_bytes(s, Timer_Reload, sizeof Timer_Reload);
   rr_state_i32s(s, Timer_Tick, 4);
'''),
    'x68k/irqh.c': ('irqh', '''
   unsigned i;
   rr_state_bytes(s, IRQH_IRQ, sizeof IRQH_IRQ);
   rr_state_bytes(s, RR_IRQH_CallbackId, sizeof RR_IRQH_CallbackId);
   for (i = 0; i < 8; i++) {
      /* Function addresses differ between processes: keep stable source ids. */
      if (RR_IRQH_CallbackId[i] >= sizeof RR_IRQH_Handlers / sizeof RR_IRQH_Handlers[0]) {
         rr_state_fail(s, "unknown interrupt source");
         return;
      }
      if (s->loading && !s->error)
         IRQH_CallBack[i] = RR_IRQH_Handlers[RR_IRQH_CallbackId[i]];
   }
'''),
    'x68k/scc.c': ('scc', '''
   rr_state_i8(s, &MouseX); rr_state_i8(s, &MouseY); rr_state_u8(s, &MouseSt);
   rr_state_u8(s, &SCC_RegNumA); rr_state_u8(s, &SCC_RegSetA);
   rr_state_bytes(s, SCC_RegsB, sizeof SCC_RegsB);
   rr_state_u8(s, &SCC_RegNumB); rr_state_u8(s, &SCC_RegSetB); rr_state_u8(s, &SCC_Vector);
   rr_state_bytes(s, SCC_Dat, sizeof SCC_Dat);
   rr_state_u8(s, &SCC_DatNum);
'''),
    'x68k/fdc.c': ('fdc', '''
   rr_state_int(s, &fdc.cmd); rr_state_int(s, &fdc.cyl); rr_state_int(s, &fdc.drv);
   rr_state_int(s, &fdc.ready); rr_state_int(s, &fdc.ctrl); rr_state_int(s, &fdc.wexec);
   rr_state_int(s, &fdc.rdptr); rr_state_int(s, &fdc.wrptr); rr_state_int(s, &fdc.rdnum);
   rr_state_int(s, &fdc.wrnum); rr_state_int(s, &fdc.bufnum);
   rr_state_int(s, &fdc.st0); rr_state_int(s, &fdc.st1); rr_state_int(s, &fdc.st2);
   rr_state_bytes(s, fdc.RspBuf, sizeof fdc.RspBuf);
   rr_state_bytes(s, fdc.PrmBuf, sizeof fdc.PrmBuf);
   rr_state_bytes(s, fdc.DataBuf, sizeof fdc.DataBuf);
   rr_state_bytes(s, fdc.ScanBuf, sizeof fdc.ScanBuf);
'''),
    'x68k/fdd.c': ('fdd', '''
   rr_state_ints(s, fdd.SetDelay, 4); rr_state_ints(s, fdd.Types, 4);
   rr_state_ints(s, fdd.ROnly, 4); rr_state_ints(s, fdd.EMask, 4);
   rr_state_ints(s, fdd.Blink, 4); rr_state_int(s, &fdd.Access);
'''),
    'x68k/sasi.c': ('sasi', '''
   rr_state_bytes(s, SASI_Buf, sizeof SASI_Buf);
   rr_state_u8(s, &SASI_Phase);
   rr_state_u32(s, &SASI_Sector); rr_state_u32(s, &SASI_Blocks);
   rr_state_bytes(s, SASI_Cmd, sizeof SASI_Cmd);
   rr_state_u8(s, &SASI_CmdPtr);
   rr_state_u16(s, &SASI_Device);
   rr_state_u8(s, &SASI_Unit);
   rr_state_i16(s, &SASI_BufPtr);
   rr_state_u8(s, &SASI_RW); rr_state_u8(s, &SASI_Stat); rr_state_u8(s, &SASI_Error);
   rr_state_bytes(s, SASI_SenseStatBuf, sizeof SASI_SenseStatBuf);
   rr_state_u8(s, &SASI_SenseStatPtr);
'''),
    'x68k/rtc.c': ('rtc', '''
   rr_state_bytes(s, RTC_Regs, sizeof RTC_Regs);
   rr_state_u8(s, &RTC_Bank);
   rr_state_int(s, &RTC_Timer1); rr_state_int(s, &RTC_Timer16);
'''),
    'x68k/pia.c': ('pia', '''
   rr_state_u8(s, &pia.PortA); rr_state_u8(s, &pia.PortB);
   rr_state_u8(s, &pia.PortC); rr_state_u8(s, &pia.Ctrl);
'''),
    'x68k/sysport.c': ('sysport', '''
   rr_state_u8(s, &sysport.contrast); rr_state_u8(s, &sysport.monitor);
   rr_state_u8(s, &sysport.keyctrl); rr_state_u8(s, &sysport.cputype);
'''),
    'x68k/sram.c': ('sram', '''
   rr_state_bus_words(s, SRAM, sizeof SRAM);
   rr_state_bool(s, &write_enabled);
'''),
    'x68k/adpcm.c': ('adpcm', '''
   rr_state_int(s, &ADPCM_VolumeShift);
   rr_state_i16s(s, ADPCM_BufR, 96000);
   rr_state_i16s(s, ADPCM_BufL, 96000);
   rr_state_i32(s, &ADPCM_WrPtr); rr_state_i32(s, &ADPCM_RdPtr);
   if (s->loading && (ADPCM_WrPtr < 0 || ADPCM_WrPtr >= 96000 || ADPCM_RdPtr < 0 || ADPCM_RdPtr >= 96000)) {
      rr_state_fail(s, "ADPCM ring position outside its buffer");
      return;
   }
   rr_state_u32(s, &ADPCM_ClockRate);
   rr_state_u32(s, &ADPCM_Count);
   rr_state_int(s, &ADPCM_Step); rr_state_int(s, &ADPCM_Out);
   rr_state_u8(s, &ADPCM_Playing); rr_state_u8(s, &ADPCM_Clock);
   rr_state_int(s, &ADPCM_PreCounter); rr_state_int(s, &ADPCM_DifBuf); rr_state_int(s, &ADPCM_Pan);
   rr_state_int(s, &OldR); rr_state_int(s, &OldL);
   rr_state_ints(s, Outs, 8); rr_state_ints(s, OutsIp, 4);
   rr_state_ints(s, OutsIpR, 4); rr_state_ints(s, OutsIpL, 4);
'''),
    'x68k/midi.c': ('midi', '''
   rr_state_int(s, &MIDI_CTRL); rr_state_int(s, &MIDI_POS); rr_state_int(s, &MIDI_SYSCOUNT);
   rr_state_u8(s, &MIDI_LAST);
   rr_state_bytes(s, MIDI_BUF, sizeof MIDI_BUF);
   rr_state_bytes(s, MIDI_EXCVBUF, sizeof MIDI_EXCVBUF);
   rr_state_u8(s, &MIDI_RegHigh); rr_state_u8(s, &MIDI_Vector); rr_state_u8(s, &MIDI_IntEnable);
   rr_state_u8(s, &MIDI_IntVect); rr_state_u8(s, &MIDI_IntFlag);
   rr_state_u32(s, &MIDI_Buffered); rr_state_i32(s, &MIDI_BufTimer);
   rr_state_u8(s, &MIDI_R05);
   rr_state_u32(s, &MIDI_GTimerMax); rr_state_u32(s, &MIDI_MTimerMax);
   rr_state_i32(s, &MIDI_GTimerVal); rr_state_i32(s, &MIDI_MTimerVal);
   rr_state_u8(s, &MIDI_MODULE);
   /* DelayBuf only feeds a host MIDI device (none here) and is stamped with
    * wall-clock time; saving it would make snapshots non-deterministic. */
'''),
    'libretro/dswin.c': ('dswin', '''
   uint32_t read_offset = (uint32_t)(pbrp - pbsp), write_offset = (uint32_t)(pbwp - pbsp);
   rr_state_bytes(s, pcmbuffer, sizeof pcmbuffer);
   rr_state_i32(s, &snd_precounter);
   rr_state_offset(s, &read_offset, (uint32_t)sizeof pcmbuffer);
   rr_state_offset(s, &write_offset, (uint32_t)sizeof pcmbuffer - 1);
   if (s->loading && !s->error) {
      if ((read_offset & 3) || (write_offset & 3) || snd_precounter < 0 || snd_precounter >= 10000000) {
         rr_state_fail(s, "audio ring position is invalid");
         return;
      }
      pbrp = pbsp + read_offset;
      pbwp = pbsp + write_offset;
   }
'''),
    'libretro/mouse.c': ('mouse', '''
   rr_state_f32(s, &MouseDX); rr_state_f32(s, &MouseDY);
   rr_state_u8(s, &MouseStat); rr_state_u8(s, &MouseSW);
'''),
}

DISK = '''
void rr_state_{lower}(RRState *s)
{{
   /* Media are attached by the frontend first; only matching drives load. */
   uint32_t present = 0, saved;
   unsigned drive;
   for (drive = 0; drive < 4; drive++)
      if ({prefix}Img[drive]) present |= 1u << drive;
   saved = present;
   rr_state_u32(s, &saved);
   if (s->loading && !s->error && saved != present) {{
      rr_state_fail(s, "inserted {prefix} media differ from the snapshot");
      return;
   }}
   rr_state_ints(s, {prefix}Cur, 4);
   rr_state_ints(s, {prefix}Trk, 4);
   for (drive = 0; drive < 4; drive++)
      if ({prefix}Img[drive])
         rr_state_bytes(s, {prefix}Img[drive], {capacity});
}}
'''

FM_FRIEND = '\t\tfriend struct RRFmState;\n'

FM_BODY = r'''
namespace FM {
extern int pmtable[2][8][256];
extern uint32_t amtable[2][4][256];

/* Visits private fmgen state; friend of Timer, OPM, Channel4, Operator, Chip. */
struct RRFmState {
   static void op(RRState *s, Operator &o)
   {
      int type = (int)o.type_, phase = (int)o.eg_phase_;
      rr_state_i32(s, &o.out_); rr_state_i32(s, &o.out2_);
      rr_state_u32(s, &o.dp_); rr_state_u32(s, &o.detune_); rr_state_u32(s, &o.detune2_);
      rr_state_u32(s, &o.multiple_); rr_state_u32(s, &o.pg_count_); rr_state_u32(s, &o.pg_diff_);
      rr_state_i32(s, &o.pg_diff_lfo_);
      rr_state_int(s, &type);
      rr_state_u32(s, &o.bn_);
      rr_state_int(s, &o.eg_level_); rr_state_int(s, &o.eg_level_on_next_phase_);
      rr_state_int(s, &o.eg_count_); rr_state_int(s, &o.eg_count_diff_);
      rr_state_int(s, &o.eg_out_); rr_state_int(s, &o.tl_out_); rr_state_int(s, &o.eg_rate_);
      rr_state_int(s, &o.eg_curve_count_); rr_state_int(s, &o.ssg_offset_);
      rr_state_int(s, &o.ssg_vector_); rr_state_int(s, &o.ssg_phase_);
      rr_state_u32(s, &o.key_scale_rate_);
      rr_state_int(s, &phase);
      rr_state_u32(s, &o.ms_); rr_state_u32(s, &o.tl_); rr_state_u32(s, &o.tl_latch_);
      rr_state_u32(s, &o.ar_); rr_state_u32(s, &o.dr_); rr_state_u32(s, &o.sr_);
      rr_state_u32(s, &o.sl_); rr_state_u32(s, &o.rr_); rr_state_u32(s, &o.ks_);
      rr_state_u32(s, &o.ssg_type_);
      rr_state_cbool(s, &o.keyon_); rr_state_cbool(s, &o.amon_);
      rr_state_cbool(s, &o.param_changed_); rr_state_cbool(s, &o.mute_);
      if (s->loading && !s->error) {
         if (type < 0 || type > 1 || phase < NEXT || phase > OFF) {
            rr_state_fail(s, "invalid FM operator mode");
            return;
         }
         o.type_ = (OpType)type;
         o.eg_phase_ = (EGPhase)phase;
         o.ams_ = amtable[o.type_][o.amon_ ? (o.ms_ >> 4) & 3 : 0];
      }
   }

   static void channel(RRState *s, Channel4 &c)
   {
      unsigned i;
      rr_state_u32(s, &c.fb);
      rr_state_ints(s, c.buf, 4);
      rr_state_int(s, &c.algo_);
      if (s->loading && !s->error) {
         if (c.algo_ < 0 || c.algo_ > 7) {
            rr_state_fail(s, "invalid FM algorithm");
            return;
         }
         /* Routing first: it resets operator outputs that are restored next. */
         int buf[4];
         memcpy(buf, c.buf, sizeof buf);
         c.SetAlgorithm(c.algo_);
         memcpy(c.buf, buf, sizeof buf);
      }
      for (i = 0; i < 4; i++)
         op(s, c.op[i]);
      if (s->loading && !s->error)
         c.pms = pmtable[c.op[0].type_][c.op[0].ms_ & 7];
   }

   static void chip(RRState *s, Chip &c)
   {
      int type = (int)c.optype_;
      unsigned i;
      rr_state_u32(s, &c.ratio_); rr_state_u32(s, &c.aml_); rr_state_u32(s, &c.pml_);
      rr_state_int(s, &c.pmv_);
      rr_state_int(s, &type);
      for (i = 0; i < 4; i++)
         rr_state_u32s(s, c.multable_[i], 16);
      if (s->loading && !s->error) {
         if (type < 0 || type > 1) {
            rr_state_fail(s, "invalid FM chip mode");
            return;
         }
         c.optype_ = (OpType)type;
      }
   }

   static void timer(RRState *s, Timer &t)
   {
      /* Timer::status is never initialised nor read (OPM::status shadows it). */
      rr_state_u8(s, &t.regtc);
      rr_state_bytes(s, t.regta, sizeof t.regta);
      rr_state_i32(s, &t.timera); rr_state_i32(s, &t.timera_count);
      rr_state_i32(s, &t.timerb); rr_state_i32(s, &t.timerb_count);
      rr_state_i32(s, &t.timer_step);
   }

   static void opm(RRState *s, OPM &o)
   {
      unsigned i;
      timer(s, o);
      rr_state_int(s, &o.fmvolume);
      rr_state_u32(s, &o.clock); rr_state_u32(s, &o.rate);
      rr_state_u32(s, &o.pmd); rr_state_u32(s, &o.amd);
      rr_state_u32(s, &o.lfocount); rr_state_u32(s, &o.lfodcount);
      rr_state_u32(s, &o.lfo_count_); rr_state_u32(s, &o.lfo_count_diff_);
      rr_state_u32(s, &o.lfo_step_); rr_state_u32(s, &o.lfo_count_prev_);
      rr_state_u32(s, &o.lfo_random_);
      rr_state_u32(s, &o.lfowaveform); rr_state_u32(s, &o.rateratio);
      rr_state_u32(s, &o.noise); rr_state_i32(s, &o.noisecount); rr_state_u32(s, &o.noisedelta);
      rr_state_u8(s, &o.lfofreq); rr_state_u8(s, &o.status); rr_state_u8(s, &o.reg01);
      rr_state_bytes(s, o.kc, sizeof o.kc);
      rr_state_bytes(s, o.kf, sizeof o.kf);
      rr_state_bytes(s, o.pan, sizeof o.pan);
      for (i = 0; i < 8; i++)
         channel(s, o.ch[i]);
      chip(s, o.chip);
   }
};
}

extern "C" void rr_state_opm(RRState *s)
{
   int present = opm != NULL;
   rr_state_bool(s, &present);
   if (s->error || present != (opm != NULL)) {
      rr_state_fail(s, "FM sound chip presence differs");
      return;
   }
   if (!opm)
      return;
   rr_state_int(s, &opm->CurReg);
   rr_state_u32(s, &opm->CurCount);
   FM::RRFmState::opm(s, *opm);
}
'''


def _replace(data: bytes, before: str, after: str) -> bytes:
    old, new = before.encode('ascii'), after.encode('ascii')
    if data.count(old) != 1:
        raise ValueError('Pinned snapshot adaptation anchor differs: ' + before[:72])
    return data.replace(old, new)


def adapt_state(name: str, data: bytes) -> bytes:
    if name in C_BODIES:
        function, body = C_BODIES[name]
        return data + (HEADER + f'void rr_state_{function}(RRState *s)\n{{{body}}}\n').encode('ascii')
    if name in ('x68k/disk_dim.c', 'x68k/disk_xdf.c'):
        prefix = 'DIM' if name.endswith('dim.c') else 'XDF'
        capacity = '1024*9*170+sizeof(DIM_HEADER)' if prefix == 'DIM' else '1261568'
        return data + (HEADER + DISK.format(lower=prefix.lower(), prefix=prefix,
                                            capacity=capacity)).encode('ascii')
    if name == 'fmgen/fmgen.h':
        for cls in ('Operator', 'Channel4', 'Chip'):
            data = _replace(data, f'\tclass {cls}\n\t{{\n', f'\tclass {cls}\n\t{{\n{FM_FRIEND}')
        return data
    if name == 'fmgen/opm.h':
        return _replace(data, '\tclass OPM : public Timer\n\t{\n',
                        '\tclass OPM : public Timer\n\t{\n' + FM_FRIEND)
    if name == 'fmgen/fmtimer.h':
        return _replace(data, '\tclass Timer\n\t{\n', '\tclass Timer\n\t{\n' + FM_FRIEND)
    if name == 'fmgen/fmg_wrap.cpp':
        return data + (HEADER + FM_BODY).encode('ascii')
    return data
