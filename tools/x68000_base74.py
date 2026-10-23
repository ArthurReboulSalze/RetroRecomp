"""Generate the X68000 machine build tree from the hissorii PX68k base (74ddbb3).

Phase 3 of docs/history/x68000/X68000_GPL_FREE_PLAN.md. Every kept file is checked byte for
byte against commit 74ddbb3 of the pinned repository, then copied with LF
endings and Retro-Recomp's documented adaptations. Original notices are
kept. The extracted checkout is never modified.

Kept (see native/x68000_machine/PROVENANCE.md): x68k machine files, fmgen
OPM, the line composition of x11/windraw.c, the key queue of x11/keyboard.c
and x11/mouse.c. Everything else comes from native/x68000_machine (MIT).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

COMMIT = '74ddbb37b4e12b77362a4e12f28ceb5aaa593684'
# No console window per git call when run inside the windowed converter.
NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
COMPAT = ROOT / 'native/x68000_machine/base74'

X68K_C = ('adpcm bg crtc dmac fdc fdd disk_d88 disk_dim disk_xdf gvram ioc irqh mem_wrap mercury mfp '
          'midi palette pia rtc sasi scc scsi sram sysport tvram').split()
FMGEN_CPP = ('fmg_wrap', 'fmgen', 'fmtimer', 'opm')


def git_blob(repo: Path, path: str) -> bytes:
    return subprocess.run(['git', '-C', str(repo), 'show', f'{COMMIT}:{path}'],
                          check=True, capture_output=True, creationflags=NO_WINDOW).stdout


def lf(data: bytes) -> bytes:
    return data.replace(b'\r\n', b'\n')


def replace(data: bytes, before: str, after: str, count: int = 1) -> bytes:
    old, new = before.encode('latin-1'), after.encode('latin-1')
    if data.count(old) != count:
        raise ValueError(f'74ddbb3 anchor differs ({data.count(old)}x): {before[:80]!r}')
    return data.replace(old, new)


def between(data: bytes, start: str, end: str | None) -> bytes:
    a = data.index(start.encode('latin-1'))
    b = data.index(end.encode('latin-1'), a) if end else len(data)
    return data[a:b]


def notice(data: bytes) -> bytes:
    """Leading comment block of a source file (its licence notice)."""
    end = data.index(b'*/') + 2
    return data[:end] + b'\n'


# ---- Adaptations (Retro-Recomp, MIT) -------------------------------------

def adapt_crtc(d: bytes) -> bytes:
    # IPL power-on window (R02/R03/R06/R07 = 28/124/40/552), a hardware fact.
    d = replace(d, '\tZeroMemory(GrphScrollY, sizeof(GrphScrollY));\n}',
                '\tZeroMemory(GrphScrollY, sizeof(GrphScrollY));\n'
                '\tCRTC_HSTART = 28;\n\tCRTC_HEND = 124;\n\tCRTC_VSTART = 40;\n\tCRTC_VEND = 552;\n}')
    # Window registers are 10-bit; never derive a width from an inverted window.
    d = replace(d, 'CRTC_HSTART = (((WORD)CRTC_Regs[0x4]<<8)+CRTC_Regs[0x5]);\n'
                   '\t\t\tTextDotX = (CRTC_HEND-CRTC_HSTART)*8;',
                'CRTC_HSTART = (((WORD)CRTC_Regs[0x4]<<8)+CRTC_Regs[0x5])&1023;\n'
                '\t\t\tif (CRTC_HEND > CRTC_HSTART) TextDotX = (CRTC_HEND-CRTC_HSTART)*8;')
    d = replace(d, 'CRTC_HEND = (((WORD)CRTC_Regs[0x6]<<8)+CRTC_Regs[0x7]);\n'
                   '\t\t\tTextDotX = (CRTC_HEND-CRTC_HSTART)*8;',
                'CRTC_HEND = (((WORD)CRTC_Regs[0x6]<<8)+CRTC_Regs[0x7])&1023;\n'
                '\t\t\tif (CRTC_HEND > CRTC_HSTART) TextDotX = (CRTC_HEND-CRTC_HSTART)*8;')
    d = replace(d, 'VLINE_TOTAL = (((WORD)CRTC_Regs[8]<<8)+CRTC_Regs[9]);',
                'VLINE_TOTAL = (((WORD)CRTC_Regs[8]<<8)+CRTC_Regs[9])&1023;\n'
                '\t\t\tif (!VLINE_TOTAL) VLINE_TOTAL = 1;')
    d = replace(d, '/VLINE_TOTAL;', '/(VLINE_TOTAL ? VLINE_TOTAL : 1);', 2)
    d = replace(d, 'CRTC_VSTART = (((WORD)CRTC_Regs[0xc]<<8)+CRTC_Regs[0xd]);',
                'CRTC_VSTART = (((WORD)CRTC_Regs[0xc]<<8)+CRTC_Regs[0xd])&1023;')
    d = replace(d, 'CRTC_VEND = (((WORD)CRTC_Regs[0xe]<<8)+CRTC_Regs[0xf]);',
                'CRTC_VEND = (((WORD)CRTC_Regs[0xe]<<8)+CRTC_Regs[0xf])&1023;')
    # Video controller R0 (0xE82400) is a word register: latch both bytes, as
    # R1/R2 already do (MAME keeps the full word too).
    return replace(d, '\tswitch(adr&0x701)\n\t{\n\tcase 0x401:\n\t\tif (VCReg0[adr&1] != data)',
                   '\tswitch(adr&0x701)\n\t{\n\tcase 0x400:\n\tcase 0x401:\n\t\tif (VCReg0[adr&1] != data)')


def adapt_mfp(d: bytes) -> bytes:
    d = replace(d, 'ICount%HSYNC_CLK', 'ICount%(HSYNC_CLK?HSYNC_CLK:1)')
    d = replace(d, '/CRTC_Regs[1]', '/(CRTC_Regs[1]?CRTC_Regs[1]:1)', 2)
    # A running timer keeps its counter; a stopped one loads the new value.
    for i, mode in enumerate(('MFP[MFP_TACR]&15', 'MFP[MFP_TBCR]&15',
                              '(MFP[MFP_TCDCR]>>4)&7', 'MFP[MFP_TCDCR]&7')):
        d = replace(d, f'Timer_Reload[{i}] = MFP[reg] = data;',
                    f'Timer_Reload[{i}] = data;\n\t\t\tif (!({mode})) MFP[reg] = data;')
    d = replace(d, '\t\tcase MFP_TACR:\n\t\t\tMFP[reg] = data;\n',
                '\t\tcase MFP_TACR:\n\t\t\tif (!(data&15)) Timer_Tick[0] = 0;\n\t\t\tMFP[reg] = data;\n')
    d = replace(d, '\t\tcase MFP_TBCR:\n\t\t\tMFP[reg] = data;\n',
                '\t\tcase MFP_TBCR:\n\t\t\tif (!(data&15)) Timer_Tick[1] = 0;\n\t\t\tMFP[reg] = data;\n')
    d = replace(d, '\t\tcase MFP_TCDCR:\n\t\t\tMFP[reg] = data;\n',
                '\t\tcase MFP_TCDCR:\n\t\t\tif (!(data&0x70)) Timer_Tick[2] = 0;\n'
                '\t\t\tif (!(data&7)) Timer_Tick[3] = 0;\n\t\t\tMFP[reg] = data;\n')
    return d


def adapt_gvram(d: bytes) -> bytes:
    # GVRAM is 512 KiB and line reads wrap inside it: the second byte of the
    # last word (pages 2/3 start one byte in) must not be read past the array.
    d = replace(d, '#define GET_WORD_W8(src) (*(BYTE *)(src) | *((BYTE *)(src) + 1) << 8)',
                '#define GVRAM_BYTE_AT(src, n) GVRAM[((DWORD)((BYTE *)(src) - GVRAM) + (n)) & 0x7ffff]\n'
                '#define GET_WORD_W8(src) (GVRAM_BYTE_AT(src, 0) | GVRAM_BYTE_AT(src, 1) << 8)')
    d = replace(d, 'x ^= 0x1ff;', 'x = (x ^ 0x1ff) + 1;')
    # The C fast clear advanced its pointer linearly while x wrapped at 512,
    # clearing the next line (and past GVRAM on the last one). Address each
    # word from the wrapped x, as the assembly version of this function does.
    d = replace(d, '\t\tp = (WORD *)(GVRAM + offy + offx * 2);\n\n\t\tfor (x = 0; x < h; ++x) {\n'
                   '\t\t\t*p++ &= CRTC_FastClrMask;\n',
                '\t\tfor (x = 0; x < h; ++x) {\n\t\t\tp = (WORD *)(GVRAM + offy + offx * 2);\n'
                '\t\t\t*p &= CRTC_FastClrMask;\n')
    return d


def adapt_tvram(d: bytes) -> bytes:
    start = d.index(b'\tif (opaq) {\n\t\tfor (i = 0; (i < TextDotX) && (x > 0)')
    end = d.index(b'#endif\t/* USE_ASM */\n}', start)
    body = (b'\t(void)addr;\n'
            b'\t/* The text plane wraps at 1024 dots (10-bit scroll). */\n'
            b'\tfor (i = 0; i < TextDotX; ++i, ++off) {\n'
            b'\t\tt = TextDrawWork[y + ((TextScrollX + i) & 0x3ff)] & 0xf;\n'
            b'\t\tif (opaq) {\n\t\t\tText_TrFlag[off] = t ? 1 : 0;\n\t\t\tBG_LineBuf[off] = TextPal[t];\n'
            b'\t\t} else if (t) {\n\t\t\tText_TrFlag[off] |= 1;\n\t\t\tBG_LineBuf[off] = TextPal[t];\n\t\t}\n\t}\n')
    return d[:start] + body + d[end:]


def adapt_dmac(d: bytes) -> bytes:
    d = replace(d, 'DMA[ch].CSR |= 0x10;', 'DMA[ch].CSR |= 0x90;')
    return replace(d, '\t\tBusErrFlag = 0;\n\t\tswitch ( ((DMA[ch].OCR>>4)&3)+((DMA[ch].DCR>>1)&4) ) {',
                   '\t\tBusErrFlag = 0;\n'
                   '\t\t/* Word/long operands on a 16-bit port must be even. */\n'
                   '\t\t{\n\t\t\tunsigned transfer = ((DMA[ch].OCR >> 4) & 3) + ((DMA[ch].DCR >> 1) & 4);\n'
                   '\t\t\tif (transfer == 5 || transfer == 6) {\n'
                   '\t\t\t\tif (DMA[ch].MAR & 1) { DMAERR(ch, 0x05) break; }\n'
                   '\t\t\t\tif (DMA[ch].DAR & 1) { DMAERR(ch, 0x06) break; }\n\t\t\t}\n\t\t}\n'
                   '\t\tswitch ( ((DMA[ch].OCR>>4)&3)+((DMA[ch].DCR>>1)&4) ) {')


def adapt_adpcm(d: bytes) -> bytes:
    return replace(d, 'ADPCM_PreCounter = 0;\n\tmemset(Outs,',
                   'ADPCM_PreCounter = 0;\n\tADPCM_Count = 0;\n\tADPCM_DifBuf = 0;\n\tADPCM_Clock = 0;\n'
                   '\tADPCM_ClockRate = ADPCM_Clocks[0];\n\tADPCM_Pan = 0;\n\tmemset(Outs,')


def adapt_irqh(d: bytes) -> bytes:
    d = replace(d, '\tC68k_Set_IRQ(&C68K, 0, 0);\n', '\trr_cpu_set_irq(0);\n')
    pattern = re.compile(rb'C68k_Set_IRQ_Callback\(&C68K, IRQH_CallBack\[i\]\);\s*'
                         rb'C68k_Set_IRQ\(&C68K, i, HOLD_LINE\);[^\n]*\n'
                         rb'\s*if \( ?C68K\.ICount ?\) \{[^\n]*\n[^\n]*\n[^\n]*\n\s*\}')
    d, count = pattern.subn(b'rr_cpu_set_irq(i);', d)
    if count != 2:
        raise ValueError('74ddbb3 interrupt raise sequence differs')
    return d


def adapt_fdd(d: bytes) -> bytes:
    return d + b'''
/* Retro-Recomp (MIT): physical presence and activity for the frontend. */
unsigned RR_FDD_MediaMask(void)
{
    return (fdd.Types[0] != FD_Non ? 1u : 0u) | (fdd.Types[1] != FD_Non ? 2u : 0u);
}
unsigned RR_FDD_BlinkMask(void)
{
    return (fdd.Blink[0] ? 1u : 0u) | (fdd.Blink[1] ? 2u : 0u);
}
'''


def adapt_fdc(d: bytes) -> bytes:
    # Guest interest in each drive, for the frontend's disk requests: reads of
    # the drive status register selecting it, and FDC commands issued while it
    # is the active drive. Counters only, never machine state; the frontend
    # takes differences and resynchronizes after a state load or reset.
    d = replace(d, 'BYTE FASTCALL FDC_Read(DWORD adr)\n{',
                '/* Retro-Recomp (MIT): guest drive polls and commands. */\n'
                'static unsigned rr_fdc_polls[2], rr_fdc_commands[2];\n'
                'unsigned RR_FDC_DriveInterest(unsigned drive)\n{\n'
                '\treturn drive < 2 ? rr_fdc_polls[drive] + rr_fdc_commands[drive] : 0u;\n}\n\n'
                'BYTE FASTCALL FDC_Read(DWORD adr)\n{')
    d = replace(d, '\t} else if ( adr==0xe94005 ) {\n\t\tif ( (fdc.ctrl&1)&&(FDD_IsReady(0)) ) ret = 0x80;',
                '\t} else if ( adr==0xe94005 ) {\n'
                '\t\trr_fdc_polls[0] += fdc.ctrl&1; rr_fdc_polls[1] += (fdc.ctrl>>1)&1;\n'
                '\t\tif ( (fdc.ctrl&1)&&(FDD_IsReady(0)) ) ret = 0x80;')
    return replace(d, '\t\t\t\tfdc.cmd = data&0x1f;\n',
                   '\t\t\t\tfdc.cmd = data&0x1f;\n'
                   '\t\t\t\tif ( fdc.drv==0||fdc.drv==1 ) rr_fdc_commands[fdc.drv]++;\n')


def buffer_mask(prefix: str) -> bytes:
    # Loaded-image mask read by the authored disk checks (our code, MIT).
    return ('\n/* Retro-Recomp (MIT): drives holding a buffered image. */\n'
            f'unsigned RR_{prefix}_BufferMask(void)\n{{\n'
            '\tunsigned mask = 0; int drive;\n'
            f'\tfor (drive = 0; drive < 4; drive++) if ({prefix}Img[drive]) mask |= 1u << drive;\n'
            '\treturn mask;\n}\n').encode('ascii')


def adapt_dim(d: bytes) -> bytes:
    # A failed insert must not leave a half-loaded image (DIM_Cleanup ejects
    # every slot and indexes its type table from the buffered header).
    d = replace(d, '\t\tZeroMemory(DIMFile[drv], MAX_PATH);\n\t\tFDD_SetReadOnly(drv);\n\t\treturn FALSE;',
                '\t\tZeroMemory(DIMFile[drv], MAX_PATH);\n\t\tFDD_SetReadOnly(drv);\n'
                '\t\tfree(DIMImg[drv]); DIMImg[drv] = NULL;\n\t\treturn FALSE;')
    d = replace(d, 'dim_set_error:\n\tFile_Close(fp);\n\tFDD_SetReadOnly(drv);\n\treturn FALSE;',
                   'dim_set_error:\n\tFile_Close(fp);\n\tFDD_SetReadOnly(drv);\n'
                   '\tfree(DIMImg[drv]); DIMImg[drv] = NULL;\n\tZeroMemory(DIMFile[drv], MAX_PATH);\n\treturn FALSE;')
    # The header lists the tracks the image holds; absent tracks were never
    # read into the (uninitialised) buffer and must stay unformatted.
    d = replace(d, '\tFile_Close(fp);\n\tif ( !dh->overtrack ) memset(dh->trkflag, 1, 170);\n\treturn TRUE;',
                '\tFile_Close(fp);\n\treturn TRUE;')
    d = replace(d, '\t\tDIMCur[drv] = 0;\n\t\tDIMImg[drv] = 0;', '\t\tDIMCur[drv] = 0;\n\t\tDIMTrk[drv] = 0;\n\t\tDIMImg[drv] = 0;')
    return d + buffer_mask('DIM')


def adapt_xdf(d: bytes) -> bytes:
    d = replace(d, '\t\tZeroMemory(XDFFile[drv], MAX_PATH);\n\t\tFDD_SetReadOnly(drv);\n\t\treturn FALSE;',
                '\t\tZeroMemory(XDFFile[drv], MAX_PATH);\n\t\tFDD_SetReadOnly(drv);\n'
                '\t\tfree(XDFImg[drv]); XDFImg[drv] = NULL;\n\t\treturn FALSE;')
    d = replace(d, '\tFile_Read(fp, XDFImg[drv], 1261568);\n\tFile_Close(fp);',
                '\tif (File_Read(fp, XDFImg[drv], 1261568) != 1261568) {\n\t\tFile_Close(fp); FDD_SetReadOnly(drv);\n'
                '\t\tfree(XDFImg[drv]); XDFImg[drv] = NULL;\n\t\tZeroMemory(XDFFile[drv], MAX_PATH); return FALSE;\n\t}\n'
                '\tFile_Close(fp);')
    return d + buffer_mask('XDF')


def adapt_d88_header(d: bytes) -> bytes:
    # The on-disk D88 header has 32-bit fields; `long` is 64-bit on Linux.
    d = replace(d, '\tlong\tfd_size;', '\tint32_t\tfd_size;')
    return replace(d, '\tlong\ttrackp[164];', '\tint32_t\ttrackp[164];')


def adapt_fmg_wrap(d: bytes) -> bytes:
    # Mercury Unit (YMF288) support is not part of this machine profile.
    cut = d.index(b'// ----------------------------------------------------------\n// ---------------------------- YMF288')
    d = d[:cut]
    d = replace(d, 'private:\n\tvirtual void Intr(bool);\n\tint CurReg;\n\tDWORD CurCount;',
                'private:\n\tvirtual void Intr(bool);\npublic:\n\tint CurReg;\n\tDWORD CurCount;')
    d = replace(d, 'MyOPM::MyOPM()\n{\n\tCurReg = 0;\n}', 'MyOPM::MyOPM()\n{\n\tCurReg = 0;\n\tCurCount = 0;\n}')
    return replace(d, 'if ( opm ) opm->Reset();',
                   'if ( opm ) { opm->Reset(); opm->CurReg = 0; opm->CurCount = 0; }')


def adapt_opm_h(d: bytes) -> bytes:
    return replace(d, '\t\tuint\tlfo_count_prev_;', '\t\tuint\tlfo_count_prev_;\n\t\tuint\tlfo_random_;')


def adapt_opm(d: bytes) -> bytes:
    # Deterministic LFO noise owned by the chip (libc rand() is host dependent
    # and shared). The table builder keeps its own sequence.
    first = d.index(b'namespace FM')
    d = d[:first] + (b'/* Retro-Recomp (MIT): deterministic LFO noise source. */\n'
                     b'static unsigned int rr_lfo_random(unsigned int *state)\n{\n'
                     b'\t*state = *state * 214013u + 2531011u;\n\treturn (*state >> 16) & 0x7fff;\n}\n\n') + d[first:]
    d = replace(d, 'OPM::OPM()\n{\n\tlfo_count_ = 0;\n\tlfo_count_prev_ = ~0;',
                'OPM::OPM()\n{\n\tlfo_count_ = 0;\n\tlfo_count_prev_ = ~0;\n\tlfo_random_ = 1;')
    d = replace(d, 'void OPM::Reset()\n{\n\tint i;',
                'void OPM::Reset()\n{\n\tlfo_count_ = lfo_step_ = lfocount = lfodcount = 0;\n'
                '\tlfo_count_prev_ = ~0;\n\tlfo_random_ = 1;\n'
                '\t/* The table builder consumed 128 draws before the first mix. */\n'
                '\tfor (unsigned n = 0; n < OPM_LFOENTS / 4; ++n) rr_lfo_random(&lfo_random_);\n\tint i;')
    d = replace(d, 'void OPM::BuildLFOTable()\n{', 'void OPM::BuildLFOTable()\n{\n\tunsigned int table_random = 1;')
    d = replace(d, 'r = (rand() / 17) & 0xff;', 'r = (rr_lfo_random(&table_random) / 17) & 0xff;')
    return replace(d, 'int c = (rand() / 17) & 0xff;', 'int c = (rr_lfo_random(&lfo_random_) / 17) & 0xff;')


def adapt_mem_wrap(d: bytes) -> bytes:
    # X68000 memory map: main RAM may occupy 0x000000-0xBFFFFF (12 MiB with
    # expansion boards). The qualified runtime maps the whole aperture; 74ddbb3
    # stops at 10 MiB and bus-errors 0xA00000-0xBFFFFF.
    d = replace(d, '\tif (addr < 0x00a00000) {\t// RAM 10MB\n\t\tMEM[addr ^ 1] = val;\n'
                   '\t} else if (addr < 0x00c00000) {\n\t\twm_buserr(addr, val);\n\t}',
                '\tif (addr < 0x00c00000) {\t/* main RAM aperture, 12 MiB */\n\t\tMEM[addr ^ 1] = val;\n\t}')
    return replace(d, '\tif (addr < 0x00a00000) {\t// RAM 10MB\n\t\tv = MEM[addr ^ 1];\n'
                      '\t} else if (addr < 0x00c00000) {\n\t\trm_buserr(addr);\n\t\tv = 0;\n\t}',
                   '\tif (addr < 0x00c00000) {\t/* main RAM aperture, 12 MiB */\n\t\tv = MEM[addr ^ 1];\n\t}')


def adapt_d88(d: bytes) -> bytes:
    # Sector lists: link each sector to the previous one of the same track.
    # 74ddbb3 never records the previous sector (load dereferences NULL from
    # the second sector on; a formatted track keeps only its first sector).
    d = replace(d, '\t\t\t\tif ( sct ) {\n\t\t\t\t\toldsi->next = si;',
                '\t\t\t\tif ( oldsi ) {\n\t\t\t\t\toldsi->next = si;')
    d = replace(d, '\t\t\t\tsi->next = 0;\n\t\t\t\tif (oldsi) oldsi = si;',
                '\t\t\t\tsi->next = 0;\n\t\t\t\toldsi = si;')
    d = replace(d, '\tfor (i=0; i<num; i++, buf+=4) {\n\t\tint size = 128<<buf[3];\n'
                   '\t\tD88_SECTINFO *si = (D88_SECTINFO*)malloc(sizeof(D88_SECTINFO)+size), *oldsi = NULL;\n'
                   '\t\tif ( !si ) goto d88_writeid_error;\n\t\tif ( i ) {\n\t\t\tif (oldsi) oldsi->next = si;',
                '\tD88_SECTINFO *oldsi = NULL;\n'
                '\tfor (i=0; i<num; i++, buf+=4) {\n\t\tint size = 128<<buf[3];\n'
                '\t\tD88_SECTINFO *si = (D88_SECTINFO*)malloc(sizeof(D88_SECTINFO)+size);\n'
                '\t\tif ( !si ) goto d88_writeid_error;\n\t\tif ( oldsi ) {\n\t\t\toldsi->next = si;')
    return d


def adapt_crtc_h(d: bytes) -> bytes:
    # Complete the array types (crtc.c defines four pages) so sizeof works.
    d = replace(d, 'extern\tDWORD\tGrphScrollX[];', 'extern\tDWORD\tGrphScrollX[4];')
    return replace(d, 'extern\tDWORD\tGrphScrollY[];', 'extern\tDWORD\tGrphScrollY[4];')


ADAPT = {
    'x68k/mem_wrap.c': adapt_mem_wrap, 'x68k/crtc.h': adapt_crtc_h, 'x68k/disk_d88.c': adapt_d88,
    'x68k/crtc.c': adapt_crtc, 'x68k/mfp.c': adapt_mfp, 'x68k/gvram.c': adapt_gvram,
    'x68k/tvram.c': adapt_tvram, 'x68k/dmac.c': adapt_dmac, 'x68k/adpcm.c': adapt_adpcm,
    'x68k/irqh.c': adapt_irqh, 'x68k/fdd.c': adapt_fdd, 'x68k/fdc.c': adapt_fdc, 'x68k/disk_dim.c': adapt_dim,
    'x68k/disk_xdf.c': adapt_xdf, 'x68k/disk_d88.h': adapt_d88_header,
    'fmgen/fmg_wrap.cpp': adapt_fmg_wrap, 'fmgen/opm.h': adapt_opm_h, 'fmgen/opm.cpp': adapt_opm,
}


# ---- RRX68MS1 serializers for this base (Retro-Recomp, MIT) ----------------
from tools.x68000_state_hardware import C_BODIES as _HEAD_BODIES, DISK as _DISK, \
    FM_BODY as _FM_BODY, FM_FRIEND as _FM_FRIEND, HEADER as _STATE_HEADER  # noqa: E402


def _long(name: str) -> str:
    """Serialize a `long` (64-bit on Linux) as a checked 32-bit value."""
    return ('   { int32_t v = (int32_t)%s;\n'
            '     if (!s->loading && (long)v != %s) rr_state_fail(s, "%s exceeds 32 bits");\n'
            '     rr_state_i32(s, &v); if (s->loading && !s->error) %s = v; }\n') % (name, name, name, name)


STATE74 = dict(_HEAD_BODIES)
del STATE74['libretro/dswin.c']                       # base74/audio_mix.c provides DSND
STATE74['x11src/mouse.c'] = STATE74.pop('libretro/mouse.c')
STATE74['x68k/gvram.c'] = ('gvram', '''
   rr_state_bus_words(s, GVRAM, sizeof GVRAM);
   rr_state_u16s(s, Grp_LineBuf, 1024);
   rr_state_u16s(s, Grp_LineBufSP, 1024);
   rr_state_u16s(s, Grp_LineBufSP2, 1024);
''')
STATE74['x68k/mfp.c'] = ('mfp', _HEAD_BODIES['x68k/mfp.c'][1] + '   rr_state_u8(s, &Timer_TBO);\n')
STATE74['x68k/sysport.c'] = ('sysport', '\n   rr_state_bytes(s, SysPort, sizeof SysPort);\n')
STATE74['x68k/sram.c'] = ('sram', '\n   rr_state_bus_words(s, SRAM, sizeof SRAM);\n')
STATE74['x68k/bg.c'] = ('bg', _HEAD_BODIES['x68k/bg.c'][1].replace(
    '   rr_state_i32(s, &BG_HAdjust); rr_state_i32(s, &BG_VLINE);\n', _long('BG_HAdjust') + _long('BG_VLINE'))
    + '   rr_state_bytes(s, BG_Dirty0, sizeof BG_Dirty0);\n   rr_state_bytes(s, BG_Dirty1, sizeof BG_Dirty1);\n')
STATE74['x68k/adpcm.c'] = ('adpcm', _HEAD_BODIES['x68k/adpcm.c'][1].replace(
    '   rr_state_i32(s, &ADPCM_WrPtr); rr_state_i32(s, &ADPCM_RdPtr);\n', _long('ADPCM_WrPtr') + _long('ADPCM_RdPtr')))
STATE74['x68k/midi.c'] = ('midi', _HEAD_BODIES['x68k/midi.c'][1]
    .replace(' rr_state_i32(s, &MIDI_BufTimer);', '')
    .replace('   rr_state_i32(s, &MIDI_GTimerVal); rr_state_i32(s, &MIDI_MTimerVal);\n', '')
    + _long('MIDI_BufTimer') + _long('MIDI_GTimerVal') + _long('MIDI_MTimerVal')
    + '   rr_state_u8(s, &MIDI_EXCVWAIT); rr_state_u8(s, &MIDI_Playing); rr_state_u8(s, &MIDI_TxFull);\n')
STATE74['x68k/irqh.c'] = ('irqh', '''
   /* Stable ids of the device routines (addresses differ between processes). */
   extern DWORD FASTCALL FDC_Int(BYTE), FDD_Int(BYTE), SASI_Int(BYTE), DMA_Int(BYTE),
      MIDI_Int(BYTE), SCC_Int(BYTE), MFP_IntCallback(BYTE);
   void *const handlers[] = {NULL, (void *)IRQH_DefaultVector, (void *)FDC_Int, (void *)FDD_Int,
      (void *)SASI_Int, (void *)DMA_Int, (void *)MIDI_Int, (void *)SCC_Int, (void *)MFP_IntCallback};
   BYTE ids[8];
   unsigned i, k;
   for (i = 0; i < 8; i++) {
      ids[i] = 255;
      for (k = 0; k < sizeof handlers / sizeof handlers[0]; k++)
         if (IRQH_CallBack[i] == handlers[k]) ids[i] = (BYTE)k;
      if (!s->loading && ids[i] == 255) {
         rr_state_fail(s, "unknown interrupt routine");
         return;
      }
   }
   rr_state_bytes(s, IRQH_IRQ, sizeof IRQH_IRQ);
   rr_state_bytes(s, ids, sizeof ids);
   if (s->loading && !s->error)
      for (i = 0; i < 8; i++) {
         if (ids[i] >= sizeof handlers / sizeof handlers[0]) {
            rr_state_fail(s, "unknown interrupt routine");
            return;
         }
         IRQH_CallBack[i] = handlers[ids[i]];
      }
''')

FM74 = (_FM_BODY
        .replace('phase < NEXT || phase > OFF', 'phase < Operator::next || phase > Operator::off')
        .replace('o.eg_phase_ = (EGPhase)phase;', 'o.eg_phase_ = (Operator::EGPhase)phase;')
        .replace('rr_state_i32(s, &o.out_); rr_state_i32(s, &o.out2_);',
                 'rr_state_i32(s, &o.out_); rr_state_i32(s, &o.out2_); rr_state_i32(s, &o.in2_);')
        .replace('rr_state_u32(s, &o.clock); rr_state_u32(s, &o.rate);',
                 'rr_state_u32(s, &o.clock); rr_state_u32(s, &o.rate); rr_state_u32(s, &o.pcmrate);'))
# OPM::interpolation is declared but never written nor read in 74ddbb3 (it is
# uninitialised): like Timer::status, it is not machine state.


def adapt_state74(name: str, data: bytes) -> bytes:
    if name in STATE74:
        function, body = STATE74[name]
        return data + (_STATE_HEADER + f'void rr_state_{function}(RRState *s)\n{{{body}}}\n').encode('ascii')
    if name in ('x68k/disk_dim.c', 'x68k/disk_xdf.c'):
        prefix = 'DIM' if name.endswith('dim.c') else 'XDF'
        capacity = '1024*9*170+sizeof(DIM_HEADER)' if prefix == 'DIM' else '1261568'
        return data + (_STATE_HEADER + _DISK.format(lower=prefix.lower(), prefix=prefix,
                                                     capacity=capacity)).encode('ascii')
    if name == 'fmgen/fmgen.h':
        for cls in ('Operator', 'Channel4', 'Chip'):
            data = replace(data, f'\tclass {cls}\n\t{{\n', f'\tclass {cls}\n\t{{\n{_FM_FRIEND}')
        return data
    if name == 'fmgen/opm.h':
        return replace(data, '\tclass OPM : public Timer\n\t{\n', '\tclass OPM : public Timer\n\t{\n' + _FM_FRIEND)
    if name == 'fmgen/fmtimer.h':
        return replace(data, '\tclass Timer\n\t{\n', '\tclass Timer\n\t{\n' + _FM_FRIEND)
    if name == 'fmgen/fmg_wrap.cpp':
        return data + (_STATE_HEADER + FM74).encode('ascii')
    return data


def windraw_compose(src: bytes) -> bytes:
    body = between(src, '#ifdef PSP\n#ifdef FULLSCREEN_WIDTH', '/********** menu')
    return notice(src) + b'''
/* Retro-Recomp: only the line composition of x11/windraw.c (74ddbb3) is kept;
 * presentation (SDL, GLES, PSP, menus) is replaced by base74/host_draw.c. */
#include "common.h"
#include "winx68k.h"
#include "winui.h"
#include "prop.h"
#include "bg.h"
#include "crtc.h"
#include "gvram.h"
#include "palette.h"
#include "tvram.h"
#include "windraw.h"

extern WORD *ScrBuf;

''' + body


def keyboard_machine(src: bytes) -> bytes:
    globals_ = between(src, 'BYTE\tKeyBufWP;', 'struct keyboard_key kbd_key[]')
    init = between(src, 'void\nKeyboard_Init(void)', '// ----------------------------------\n//\t')
    send = between(src, '#define P6K_UP 1', 'static BYTE get_x68k_keycode')
    interrupt = between(src, 'void\nKeyboard_Int(void)', '/**********')
    interrupt = re.sub(rb'\n\t\tprintf\("KeyBufRP:[^\n]*', b'', interrupt)
    return notice(src) + b'''
/* Retro-Recomp: only the X68000 key queue of x11/keyboard.c (74ddbb3) is
 * kept; host key tables and the software keyboard are not used. */
#include "common.h"
#include "keyboard.h"
#include "mfp.h"

#define NC 0

''' + globals_ + init + send + interrupt


def mouse(src: bytes) -> bytes:
    cut = src.index(b'void Mouse_ChangePos(void)')
    data = src[:cut] + b'void Mouse_ChangePos(void)\n{\n}\n'
    return replace(data, '\tprintf("ME(): %f %f\\n", dx, dy);\n', '')


def generate(source: Path, repo: Path, output: Path, geolith: Path) -> dict:
    marker = source / '.retro-recomp-pin'
    if marker.is_file():  # extracted archive
        pinned = COMMIT in marker.read_text().split()
    else:  # pinned git checkout
        pinned = subprocess.run(['git', '-C', str(source), 'rev-parse', 'HEAD'], check=True,
                                capture_output=True, text=True, creationflags=NO_WINDOW).stdout.strip() == COMMIT
    if not pinned:
        raise ValueError('The X68000 machine base is not pinned to 74ddbb3.')
    actual = subprocess.run(['git', '-C', str(repo), 'rev-parse', COMMIT], check=True,
                            capture_output=True, text=True, creationflags=NO_WINDOW).stdout.strip()
    if actual != COMMIT:
        raise ValueError('The reference repository lacks the 74ddbb3 commit.')
    receipt = {'schema': 1, 'base_commit': COMMIT, 'files': []}

    def take(path: str) -> bytes:
        raw = (source / path).read_bytes()
        # Checkouts may convert line endings; compare canonical LF content.
        if lf(raw) != lf(git_blob(repo, path)):
            raise ValueError(f'{path} differs from commit 74ddbb3')
        return lf(raw)

    def emit(name: str, data: bytes, origin: str, original: bytes):
        data = adapt_state74(name, data)
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or target.read_bytes() != data:
            target.write_bytes(data)
        receipt['files'].append({'output': name, 'origin': origin,
                                 'origin_sha256': hashlib.sha256(original).hexdigest(),
                                 'output_sha256': hashlib.sha256(data).hexdigest()})

    for header in sorted((source / 'x68k').glob('*.h')):
        path = 'x68k/' + header.name
        data = take(path)
        emit(path, ADAPT.get(path, lambda d: d)(data), path, data)
    for name in X68K_C:
        path = f'x68k/{name}.c'
        data = take(path)
        emit(path, ADAPT.get(path, lambda d: d)(data), path, data)
    for header in sorted((source / 'fmgen').glob('*.h')):
        path = 'fmgen/' + header.name
        data = take(path)
        emit(path, ADAPT.get(path, lambda d: d)(data), path, data)
    for name in FMGEN_CPP:
        path = f'fmgen/{name}.cpp'
        data = take(path)
        emit(path, ADAPT.get(path, lambda d: d)(data), path, data)
    for path, convert, out in (('x11/windraw.c', windraw_compose, 'x11src/windraw_compose.c'),
                               ('x11/keyboard.c', keyboard_machine, 'x11src/keyboard.c'),
                               ('x11/mouse.c', mouse, 'x11src/mouse.c')):
        data = take(path)
        emit(out, convert(data), path, data)
    for path in ('doc/kero_src.txt', 'fmgen/readme.txt'):
        data = take(path)
        emit('notices/' + path, data, path, data)
    # Musashi (Geolith copy, MIT) with our X68000 configuration header.
    for source_file in sorted((geolith / 'src/m68k').glob('*')):
        if source_file.is_file() and source_file.name not in ('m68kconf.h', 'm68kdasm.c'):
            data = source_file.read_bytes()
            emit('m68000/musashi/' + source_file.name, data, 'geolith-libretro/src/m68k/' + source_file.name, data)
    config = (COMPAT / 'musashi/m68kconf.h').read_bytes()
    emit('m68000/musashi/m68kconf.h', config, 'native/x68000_machine/base74/musashi/m68kconf.h', config)
    # Our MIT compat headers, where the kept sources look for x11/ and m68000/.
    for folder in ('x11', 'm68000'):
        for header in sorted((COMPAT / folder).glob('*.h')):
            data = header.read_bytes()
            emit(f'{folder}/{header.name}', data, 'native/x68000_machine/base74/' + folder, data)
    (output / 'base74-generation.json').write_text(json.dumps(receipt, indent=1) + '\n', encoding='utf-8')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--repo', type=Path, help='git repository holding the commit (default: --source)')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--geolith', type=Path, required=True)
    args = parser.parse_args()
    receipt = generate(args.source, args.repo or args.source, args.output, args.geolith)
    print(f"{len(receipt['files'])} files generated from {COMMIT[:12]}")


if __name__ == '__main__':
    main()
