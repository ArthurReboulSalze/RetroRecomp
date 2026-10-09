"""Checked PAL timing adaptations of private copies of the pinned SNES engine.

Existing NTSC audio scheduling is retained. PAL maps master clocks to the
independent 1.02528 MHz SPC oscillator, carrying fractions between iterations.
"""
from .core import ConversionError


def replace(source, old, new, count=1):
    if source.count(old) != count:
        raise ConversionError('Pinned SNES timing hook changed; refusing an ambiguous patch.')
    return source.replace(old, new)


def configured(source):
    return '#include "retro_snes_game.h"\n#include "snes_timing.h"\n' + source


def apu_clock(source):
    # Check the pinned implementation before preserving it in the NTSC branch.
    replace(source, '#define RTL_MASTER_CYCLES_PER_FRAME 357368ull', '')
    replace(source, '#define RTL_APU_CYCLES_PER_FRAME 17088ull', '')
    replace(source, 'uint64_t start_master, start_guest, next_guest, last_duration;', '')
    return configured('''#pragma once
#include <stdint.h>
#if RR_SN_PAL
#define RTL_MASTER_CYCLES_PER_FRAME RR_SN_FRAME_MASTER
#define RTL_APU_CYCLES_PER_FRAME (RR_SN_FRAME_MASTER * RR_SN_APU_HZ / RR_SN_MASTER_HZ)
typedef struct RtlApuFrameClock {
  uint64_t start_master, start_guest, next_guest, last_duration;
  uint64_t start_remainder, next_remainder, last_master;
} RtlApuFrameClock;
static inline void rtl_apu_clock_begin(RtlApuFrameClock *clock, uint64_t master) {
  clock->start_master = master;
  clock->start_guest = clock->next_guest;
  clock->start_remainder = clock->next_remainder;
}
static inline uint64_t rtl_apu_clock_now(const RtlApuFrameClock *clock, uint64_t master) {
  uint64_t within = master >= clock->start_master ? master - clock->start_master : 0;
  return clock->start_guest +
      (within * RR_SN_APU_HZ + clock->start_remainder) / RR_SN_MASTER_HZ;
}
static inline uint64_t rtl_apu_clock_finish(RtlApuFrameClock *clock, uint64_t master) {
  uint64_t span = master >= clock->start_master ? master - clock->start_master : 0;
  if (span < RR_SN_FRAME_MASTER) span = RR_SN_FRAME_MASTER;
  uint64_t scaled = span * RR_SN_APU_HZ + clock->start_remainder;
  clock->last_duration = scaled / RR_SN_MASTER_HZ;
  clock->next_remainder = scaled % RR_SN_MASTER_HZ;
  clock->last_master = span;
  clock->next_guest = clock->start_guest + clock->last_duration;
  /* Keep the origin intact for raster IRQs after the completed iteration. */
  return clock->next_guest;
}
#else
''' + source + '\n#endif\n')


def frame_driver(source):
    return configured(replace(source, '#define BFD_MASTER_CYCLES_PER_FIELD 357368ull',
                              '#define BFD_MASTER_CYCLES_PER_FIELD RR_SN_FRAME_MASTER'))


def bus(source):
    source = replace(source, '262u', 'RR_SN_LINES', count=9)
    source = replace(source, '(32040 * 32) / (1364 * 262 * 60.0)',
        '(RR_SN_PAL ? (1025280.0 / 21281370.0) : (32040 * 32) / (1364 * 262 * 60.0))')
    return configured(source)


def ppu(source):
    source = replace(source, 'uint8_t val = 0x3; // ppu2 version (4 bit), bit 4: ntsc/pal',
        'uint8_t val = 0x3 | (RR_SN_PAL ? 0x10 : 0); // PPU2 version and video region')
    return configured(replace(source, '(262 - 225)', '(RR_SN_LINES - 225)', count=3))


def bridge(source):
    source = replace(source, '(32040.0 * 32.0) / (1364.0 * 262.0 * 60.0)',
        '(RR_SN_PAL ? (1025280.0 / 21281370.0) : (32040.0 * 32.0) / (1364.0 * 262.0 * 60.0))')
    source = replace(source, '357368u', 'RR_SN_FRAME_MASTER', count=5)
    source = replace(source, 'v <= 261u', 'v < RR_SN_LINES')
    source = replace(source, 'g_snes->vTimer <= 261u', 'g_snes->vTimer < RR_SN_LINES')
    return configured(source)


def runtime(source):
    source = replace(source, '''  return g_extended_frame_timing && g_apu_frame_clock.last_duration
      ? (double)g_apu_frame_clock.last_duration / RTL_APU_CYCLES_PER_FRAME : 1.0;''',
        '''#if RR_SN_PAL
  return g_extended_frame_timing && g_apu_frame_clock.last_master
      ? (double)g_apu_frame_clock.last_master / RR_SN_FRAME_MASTER : 1.0;
#else
  return g_extended_frame_timing && g_apu_frame_clock.last_duration
      ? (double)g_apu_frame_clock.last_duration / RTL_APU_CYCLES_PER_FRAME : 1.0;
#endif''')
    source = replace(source, '(32040.0 * 32.0) / (1364.0 * 262.0 * 60.0)',
        '(RR_SN_PAL ? (1025280.0 / 21281370.0) : (32040.0 * 32.0) / (1364.0 * 262.0 * 60.0))')
    return configured(source)


def adapt_engine(staged):
    for name, adapt in (('apu_frame_clock.h', apu_clock), ('beam_frame_driver.c', frame_driver),
                        ('snes/snes.c', bus), ('snes/ppu.c', ppu),
                        ('snes/interp_bridge.c', bridge), ('common_rtl.c', runtime)):
        path = staged / 'runner/src' / name
        path.write_text(adapt(path.read_text(encoding='utf-8')), encoding='utf-8')
