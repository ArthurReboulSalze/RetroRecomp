# Capcom CPS-1: measurement log

Dated measurements and decisions behind the [Capcom CPS-1 page](CPS1.md), kept
here so that the machine page stays a reference. Each entry says what was
measured, when, and on which engine. Nothing here measures the original boards:
the comparisons are agreement with MAME 0.289, and the conversion's own checks
are agreement between native code and a fresh interpreted reference. The five
measures (native code, CPU fidelity, hardware fidelity, gameplay validation,
physical latency) stay separate in every entry.

Entries before the 1.6.4 tree were measured on earlier engines; the figures are
**not repeated** on 1.6.4 until the standard sets are requalified (see
[Known limits](CPS1.md#known-limits) on the machine page).

## Contents

- [24 October 2026: sprite order and the first qualified sets](#24-october-2026-sprite-order-and-the-first-qualified-sets)
- [27 October 2026: shared paths](#27-october-2026-shared-paths)
- [27 October 2026: credited play and sound compared with MAME](#27-october-2026-credited-play-and-sound-compared-with-mame)
- [29 October 2026 (1.6.4): graphics RAM and quick states](#29-october-2026-164-graphics-ram-and-quick-states)

## 24 October 2026: sprite order and the first qualified sets

The table of 26 qualified sets (standard scan level, Windows, attract and
credited play routes of 3,600 frames each, up to eight conversions at once,
FBNeo romsets with their parent ZIPs) is on the [machine page](CPS1.md#qualification).
Every set passed the fresh interpreted reference on each route, the compressed
executable comparison and the fresh-process F8/F9 check, with the default DIP
switches; validation routes drive players 1 and 2.

Earlier native/reference agreement (step 3 of the development) also covered
sf2, ghouls, captcomm, megaman and strider. Since overlapping sprites are drawn
in MAME's order (the first sprite of the list stays on top, 24 October 2026),
the attract modes of ffight, ghouls, sf2, captcomm, strider and megaman match
MAME 0.289 pixel for pixel on every compared frame: one frame in 30 over 9,000
frames, 300 per set. That comparison is a development check, not part of each
conversion, and it measures agreement with MAME, not with the original boards.

## 27 October 2026: shared paths

CPS-1 took part in the shared base of paths, as an experimental machine whose
engine will still change. The rules are on the
[machine page](CPS1.md#paths-shared-between-players) and in
[COMPILATION_LIBRARY.md](COMPILATION_LIBRARY.md#cps-1-joins-the-base-step-5-of-the-standardisation-27-october-2026-part-of-160).

- No set needed learned work-RAM code when the qualified table was made, so
  there was nothing to share; the channel exists since this change.
- Final Fight gives the same route hashes on Windows and on Debian 13.
- Feedback kind 14 (a program-ROM instruction left interpreted) is recorded and
  read by nobody: the ROM is swept whole. It is diagnostic only and never shared.

## 27 October 2026: credited play and sound compared with MAME

A development check, not part of each conversion; it measures agreement with
MAME 0.289, not with the original boards. Each set runs the conversion's own
credited play route (coin, Start, then pseudo-random movement and buttons) for
3,600 frames in the reference board model and in MAME. MAME receives the same
raw port values through read taps on the 68000's input addresses, so both
sides read each value in the same frame; one frame in ten is compared pixel
for pixel.

- **21 of 24 sets** that MAME could run from the romsets used match on all 360
  compared frames: 1941, Three Wonders, Carrier Air Wing, Captain Commando
  (four-player inputs at their CPS-B addresses), Dynasty Wars, Final Fight,
  Ghouls'n Ghosts, Knights of the Round, Mega Man, Magic Sword, Nemo, Pnickies,
  Pokonyan, Quiz & Dragons, Quiz Tonosama no Yabou 2, Street Fighter II,
  Street Fighter II' Champion Edition, Strider, U.N. Squadron, Varth and Willow.
- **Three sets slip by one frame** during play: The King of Dragons from frame
  839, Mega Twins from frame 919 and Street Fighter II' Hyper Fighting from
  frame 1504. The pictures are the same one frame apart (a fade or a title step
  early or late), and their attract modes match MAME on all 300 compared frames
  of 9,000. The King of Dragons and Mega Twins each match on all 360 frames when
  MAME's input change is moved to another point of the frame (a different point
  for each game), Hyper Fighting at none. A 68000 trace of The King of Dragons
  with the same inputs finds no instruction whose duration differs over
  2,354,506 instructions; the two cores part when MAME takes the VBLANK
  interrupt one instruction earlier than the reference. This is the
  interrupt-sampling limit described in
  [Known limits](CPS1.md#known-limits) (MAME samples interrupts at the end of a
  bus access), which can move a game's main loop by a frame relative to its
  input reads.
- **Not compared**: Adventure Quiz Capcom World 2 and Mercs (MAME needs PAL
  dumps, `q522b.1a` and `c628`, that the romsets used lacked).

Sound, same routes, MAME `-wavwrite` at 55,930 Hz (Final Fight, Street Fighter
II, Ghouls'n Ghosts; one-second windows): levels agree within 0.12 dB
(median), and averaged spectra within 0.998 to 0.99998 (cosine similarity).
Below 4 kHz every third-octave band agrees within about 1 dB. The larger
differences, up to about 18 dB in single windows, lie between 5 and 10 kHz,
where the OKI's 7,576 Hz samples leave their images: the board model
interpolates the OKI linearly at the YM2151 rate, whereas MAME resamples it
with its own filter. MAME's output also drifts by about 7 ppm (the YM2151 runs
at 55,930.4 Hz), so waveform correlation is lower than the spectra suggest
(median 0.87 to 0.995). Physical audio and latency are not measured.

## 29 October 2026 (1.6.4): graphics RAM and quick states

- Street Fighter II': Champion Edition runs a short loop from graphics RAM
  (it fills and compares the graphics memory, copied there by the game). On the
  engine of the 24 October table the conversion left **75,546 interpreted 68000
  instructions** in the play route (shown as 0.06 percent in that table). In the
  1.6.4 tree the native code guards instructions run from graphics RAM like
  work-RAM code: pass 1 observes them, pass 2 translates them (each instruction
  still guarded by its live words), and the standard-level routes report zero
  interpreted instructions for the set (native code only; CPU, hardware and
  gameplay measures stay separate). `GENERATOR_REVISION` went from 6 to 7; no
  CPS-1 path was qualified yet, so nothing was lost. The observations are
  private build hints (`m68k_gfx`) of the player's library: they cannot be tied
  to a ROM image, so they are counted and never shared. Details:
  [UPGRADES.md](UPGRADES.md#cps-1-code-run-from-graphics-ram-is-guarded-natively-164-lot-h).
- The quick state changed format (magic `CPS1S002` instead of `CPS1S001`, every
  structure written field by field): 1.6.3 states are refused cleanly
  ([GAME_STATES.md](GAME_STATES.md)).
- CPS-1 has no libretro-thumbnails catalogue: the artwork step skips that
  search. Before 1.6.4, every CPS-1 conversion with online covers failed.
- Not repeated yet: the qualified table, the MAME comparisons and the sound
  comparison above, all measured on earlier engines.
