# Capcom CPS-1: measurement log

Dated measurements and decisions behind the [Capcom CPS-1 page](CPS1.md), kept
here so that the machine page stays a reference. Each entry says what was
measured, when, and on which engine. Nothing here measures the original boards:
the comparisons are agreement with MAME 0.289, and the conversion's own checks
are agreement between native code and a fresh interpreted reference. The five
measures (native code, CPU fidelity, hardware fidelity, gameplay validation,
physical latency) stay separate in every entry.

Entries before the 1.6.4 tree were measured on earlier engines; the figures are
**not repeated** on 1.6.4 or later, except for the 26 sets measured again on
29 October 2026 (see the last entry and [Known limits](CPS1.md#known-limits) on
the machine page).

## Contents

- [24 October 2026: sprite order and the first qualified sets](#24-october-2026-sprite-order-and-the-first-qualified-sets)
- [27 October 2026: shared paths](#27-october-2026-shared-paths)
- [27 October 2026: credited play and sound compared with MAME](#27-october-2026-credited-play-and-sound-compared-with-mame)
- [29 October 2026 (1.6.4): graphics RAM and quick states](#29-october-2026-164-graphics-ram-and-quick-states)
- [29 October 2026 (1.6.5 tree): selective requalification](#29-october-2026-165-tree-selective-requalification)
- [29 October 2026 (1.6.5 tree): independent vectors and route liveness](#29-october-2026-165-tree-independent-vectors-and-route-liveness)
- [29 October 2026 (1.6.5 tree): the whole panel, routes, captures and long routes](#29-october-2026-165-tree-the-whole-panel-routes-captures-and-long-routes)
- [30 October 2026 (1.6.5 tree): Z80 vectors, MAME again and a Linux witness](#30-october-2026-165-tree-z80-vectors-mame-again-and-a-linux-witness)
- [1 November 2026 (1.6.6 tree): Z80 corrections, sound against MAME and a third Linux witness](#1-november-2026-166-tree-z80-corrections-sound-against-mame-and-a-third-linux-witness)
- [2 November 2026 (1.6.7 tree): the CPS-1.5 board without its sound, against MAME](#2-november-2026-167-tree-the-cps-15-board-without-its-sound-against-mame)

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

## 29 October 2026 (1.6.5 tree): selective requalification

A campaign of twelve sets after the generator revision went from 6 to 7 (1.6.4)
and 8 (1.6.5). Tree: local `main` at `98debbb` (branch `spec/cps1-165b`), Windows,
standard scan level (attract and credited play routes of 3,600 frames each),
default DIP switches, players 1 and 2 driven, one conversion at a time, an empty
library per set, no shared base, FBNeo romsets read in place. The set list: the
five risk cases of the qualification campaign (`sf2ce`, `ffight`, `captcomm`,
`strider`, `wof`), the release check `1941`, and `kod`, `mtwins` and `sf2hf` (one
frame of slip against MAME in the 27 October comparison), `pokonyan`
(unverified graphics mapper), `mercs` (vertical, three players, not comparable
with MAME) and `cworld2j` (quiz board, not comparable with MAME).

Every conversion of the eleven supported sets passed on all its checks: the
reference comparison on both routes (CPU registers and clocks, RAM, image and
sound hashes), the packed executable replay, and the fresh-process F8/F9 state
check with the truncated state rejected. Counts over the two routes (7,200
frames), in instructions retired:

| Set | Native 68000 | Interpreted 68000 | Native Z80 | Interpreted Z80 | Graphics-RAM instructions observed |
| --- | ---: | ---: | ---: | ---: | ---: |
| `1941` | 101,209,464 | 0 | 44,659,319 | 0 | 0 |
| `sf2ce` | 129,196,735 | 0 | 40,478,778 | 0 | 33 |
| `ffight` | 97,414,101 | 0 | 44,637,833 | 0 | 0 |
| `captcomm` | 97,686,875 | 0 | 40,357,633 | 0 | 0 |
| `strider` | 100,806,294 | 0 | 50,621,232 | 0 | 0 |
| `kod` | 99,225,388 | 0 | 40,521,586 | 0 | 0 |
| `mtwins` | 99,132,420 | 0 | 40,248,589 | 0 | 0 |
| `sf2hf` | 126,323,470 | 0 | 40,448,751 | 0 | 0 |
| `pokonyan` | 95,411,855 | 0 | 40,430,657 | 0 | 0 |
| `mercs` | 102,583,926 | 0 | 44,359,963 | 0 | 0 |
| `cworld2j` | 120,027,456 | 0 | 40,267,838 | 0 | 0 |

- `sf2ce` goes from 75,546 interpreted 68000 instructions (24 October engine,
  0.06 percent) to **zero**: 33 instructions run from graphics RAM were observed
  and translated, as private build hints that are counted and never shared.
- `wof` (Warriors of Fate, QSound) was refused as expected, with the named reason
  "CPS-1 set wof is not supported yet: qsound".
- No regression against the 24 October table: every set that had zero
  interpreted instructions still has zero. The Z80 interrupt mode 0 path is
  counted in this tree (1.6.5); no route of these sets met it.
- No shared path was produced or qualified (the work-RAM and sound-RAM code
  counts are zero for the eleven sets), so no CPS-1 path is qualified yet, and
  the report stays `experimental`.
- Not measured: the other fifteen sets of the table, the comparison with MAME
  (not repeated on this tree), hardware fidelity, complete playthroughs,
  physical latency and any speed. "Zero" means that the routes run met no
  interpreted instruction.

## 29 October 2026 (1.6.5 tree): independent vectors and route liveness

Two pieces of evidence for the gates of the "supported" checklist, on branch `spec/cps1-165c` (tree of `main` at `8212d95`
plus the changes of that branch). Both are CPU or activity evidence; hardware fidelity, gameplay and latency stay unmeasured.

- **Independent 68000 vectors** (`tools/cps1_vector_selftest.py`, about two minutes, Windows, llvm-mingw): the three
  SingleStepTests fixtures (834 shift, 2,171 prefetch including the 82 authored cases, 864 exception vectors) ran once
  through the CPS-1 translated steps and once through Musashi interpreting every instruction. Every vector ran as a native
  step. Native versus vector: 834/834, 2,169/2,171 and 864/864 on registers, SR, PC and written bytes, and the same counts on
  clocks; the two exceptions are the authored vectors that set the trace bit, which neither path delivers (Musashi built
  without trace). Musashi versus vector: 834/834, 2,091/2,171 and 858/864 on state; 834/834, 2,151/2,171 and 838/864 on
  clocks. The groups where the reference differs: `DIVU`, `DIVS`, `CHK`, one line-F frame, and 5 authored division cases.
  Detail and limits: [CPU_68000.md](CPU_68000.md#tests-and-vectors).
- **Route liveness** (new `final_checks[].liveness` fields): the eleven sets of the requalification were converted again
  with the fields; 0 interpreted 68000 and Z80 instructions and every check passed again, as in the campaign above. Per set
  and route, the distinct pictures, the last frame where the picture changed, the audible frames and the last audible frame
  are in the table of [CPS1.md](CPS1.md#independent-evidence-and-liveness-29-october-2026). The `mtwins` attract route is
  silent for its 3,600 frames; its play route is audible.
- Not done: the Z80 vector replay (the SingleStepTests/z80 corpus is not cached on this machine and has to be downloaded);
  the fifteen other sets of the table were not converted with the liveness fields.

## 29 October 2026 (1.6.5 tree): the whole panel, routes captures and long routes

Branch `spec/cps1-165d`, tree of local `main` at `cd5b69d`, Windows. The 26 sets of the qualification table were converted
again, one at a time, at the standard level (attract and credited play routes of 3,600 frames each), with an empty library
per set, no shared base, FBNeo romsets read in place. Every conversion passed: the reference comparison on both routes, the
packed replay (the report now says "unpacked build executable and a packed copy replayed against the reference"), and the
fresh-process F8/F9 check with the truncated state rejected. Instructions retired over the two routes:

| Set | Native 68000 | Interpreted 68000 | Native Z80 | Interpreted Z80 |
| --- | ---: | ---: | ---: | ---: |
| `1941` | 101,209,464 | 0 | 44,659,319 | 0 |
| `cworld2j` | 120,027,456 | 0 | 40,267,838 | 0 |
| `captcomm` | 97,686,875 | 0 | 40,357,633 | 0 |
| `cawing` | 106,243,502 | 0 | 40,170,109 | 0 |
| `dynwar` | 97,289,335 | 0 | 50,879,433 | 0 |
| `ffight` | 97,414,101 | 0 | 44,637,833 | 0 |
| `ghouls` | 122,624,131 | 0 | 51,237,798 | 0 |
| `knights` | 99,099,182 | 0 | 40,399,194 | 0 |
| `msword` | 95,478,386 | 0 | 41,419,080 | 0 |
| `megaman` | 132,672,499 | 0 | 48,756,407 | 0 |
| `mtwins` | 99,132,420 | 0 | 40,248,589 | 0 |
| `mercs` | 102,583,926 | 0 | 44,359,963 | 0 |
| `nemo` | 107,829,046 | 0 | 40,393,052 | 0 |
| `pnickj` | 130,710,167 | 0 | 40,189,358 | 0 |
| `pokonyan` | 95,411,855 | 0 | 40,430,657 | 0 |
| `qad` | 113,998,824 | 0 | 40,270,604 | 0 |
| `qtono2j` | 122,125,976 | 0 | 48,258,913 | 0 |
| `sf2ce` | 129,196,735 | 0 | 40,478,778 | 0 |
| `sf2hf` | 126,323,470 | 0 | 40,448,751 | 0 |
| `sf2` | 106,081,054 | 0 | 40,452,851 | 0 |
| `strider` | 100,806,294 | 0 | 50,621,232 | 0 |
| `kod` | 99,225,388 | 0 | 40,521,586 | 0 |
| `3wonders` | 98,099,080 | 0 | 40,272,835 | 0 |
| `unsquad` | 111,390,795 | 0 | 50,763,574 | 0 |
| `varth` | 127,483,058 | 0 | 40,320,115 | 0 |
| `willow` | 106,438,658 | 0 | 50,813,792 | 0 |

- No regression against the 24 October table, and none against the eleven sets of the earlier campaign of this day.
- Liveness (pictures and sound per route) for the 26 sets is in the table of
  [CPS1.md](CPS1.md#independent-evidence-and-liveness-29-october-2026). Attract routes with no audible frame: `dynwar`,
  `ghouls`, `mtwins`, `unsquad`; `willow` has 53.
- **Captures**: the credited play route of each set was replayed headless on its delivered executable (the script rebuilt and
  its hash checked against the report) with a capture every 600 frames; the six captures of each set were put on a contact
  sheet and inspected by the specialist agent. All 26 sets reach play. The sheets stay in the maintainer's build folder
  (`.build/cps1-165d/captures`): they show commercial games.
- **Extended level** (a third route of 18,000 pseudo-random frames) on `sf2ce`, `ffight` and `1941`: 0 interpreted 68000 and
  Z80 instructions, 451,738,928, 343,094,818 and 349,448,315 native 68000 instructions over the three routes, every check
  passed; the picture changes up to the last frame of the long route (17,997 for `ffight`). The captures every 3,000 frames
  show `sf2ce` fighting, game over, title and a new game, `ffight` deep in its first stage, `1941` looping through play and
  title.
- Not measured: the comparison with MAME (still the 24 and 27 October figures), the Z80 vectors, Linux, hardware fidelity,
  complete playthroughs, physical latency and speed. The wall times of the conversions (50 to 260 s) are not timings.

## 30 October 2026 (1.6.5 tree): Z80 vectors, MAME again and a Linux witness

Branch `spec/cps1-165d` on local `main` (`8da49bf` at the end). Three pieces of evidence for the gates of the "supported"
checklist. All are CPU or picture agreement with a reference; none is hardware fidelity, gameplay or latency.

**Independent Z80 vectors** (`tools/cps1_z80_vector_selftest.py`, Windows, llvm-mingw, about 30 seconds with the corpus cached):
the pinned SingleStepTests/z80 sample (`ebe1875`, 32 vectors per family, 1,604 families, 51,328 vectors; fetched once by
`tools/fetch_z80_vectors.py` into `.deps/z80-vectors`) through the CPS-1 translated Z80 bodies and the patched Geolith core
(native), and through the same core interpreting every instruction (reference), on a flat bus whose ports answer from the vector.
38,433 vectors lie in the sound ROM windows, 1,615 in sound RAM (each one native step), 11,280 outside the code map (each
one interpreted and counted once). Native versus reference: identical on all 51,328, state and clock. Against the vectors,
both: 50,429 of 51,328 on the state, 51,200 on the clock. Differences by family (state, clock, differing fields; P and Q not
compared):

| Family | State | Clock | Fields |
| --- | ---: | ---: | --- |
| `37` | 4 | 0 | f 4 |
| `3f` | 7 | 0 | f 7 |
| `dd 22` | 32 | 0 | wz 32 |
| `dd 2a` | 32 | 0 | wz 32 |
| `dd 37` | 12 | 0 | f 12 |
| `dd 3f` | 17 | 0 | f 17 |
| `dd e9` | 32 | 0 | wz 32 |
| `ed 40` | 32 | 0 | f 30, wz 32 |
| `ed 48` | 32 | 0 | f 27, wz 32 |
| `ed 4d` | 16 | 0 | iff1 16 |
| `ed 4e` | 18 | 32 | im 18 |
| `ed 50` | 32 | 0 | f 21, wz 32 |
| `ed 57` | 23 | 0 | f 23 |
| `ed 58` | 32 | 0 | f 23, wz 32 |
| `ed 5f` | 23 | 0 | f 23 |
| `ed 60` | 32 | 0 | f 24, wz 32 |
| `ed 68` | 32 | 0 | f 25, wz 32 |
| `ed 6e` | 20 | 32 | im 20 |
| `ed 70` | 32 | 0 | f 24, wz 32 |
| `ed 77` | 0 | 32 | - |
| `ed 78` | 23 | 0 | f 23 |
| `ed 7f` | 0 | 32 | - |
| `ed a3` | 32 | 0 | ports 32 |
| `ed ab` | 32 | 0 | f 12, wz 32, ports 32 |
| `ed b0` | 26 | 0 | f 26 |
| `ed b1` | 25 | 0 | f 25 |
| `ed b2` | 31 | 0 | f 31 |
| `ed b3` | 32 | 0 | f 27, ports 32 |
| `ed b8` | 20 | 0 | f 20 |
| `ed b9` | 32 | 0 | f 25, wz 32 |
| `ed ba` | 30 | 0 | f 30 |
| `ed bb` | 32 | 0 | f 28, ports 32 |
| `fd 22` | 32 | 0 | wz 32 |
| `fd 2a` | 32 | 0 | wz 32 |
| `fd 37` | 11 | 0 | f 11 |
| `fd 3f` | 17 | 0 | f 17 |
| `fd e9` | 32 | 0 | wz 32 |

Totals by field over the vectors: flags 535, WZ 480, ports 128, IM 38, IFF1 16; no written byte differs. Which side is right in each
case was not investigated (the oracle is JSMoo). They are the Geolith core's: it is also the Neo Geo's sound core, whose own
conversions were not replayed here.

**MAME 0.289 again** (`tools/cps1_mame_compare.py`, 26 sets, attract and credited play routes of 3,600 frames, one frame in ten, delivered
game against MAME, MAME's input reads replaced frame by frame; the frame of a read is derived from MAME's machine time, the game's
line 0 falling 22 of 262 lines after MAME's vertical blank starts; identical frames over compared frames):

| Set | Attract | Credited play | First different frame |
| --- | ---: | ---: | ---: |
| `1941` | 360/360 | 360/360 |  |
| `cworld2j` | not comparable | not comparable |  |
| `captcomm` | 360/360 | 360/360 |  |
| `cawing` | 360/360 | 360/360 |  |
| `dynwar` | 360/360 | 360/360 |  |
| `ffight` | 360/360 | 360/360 |  |
| `ghouls` | 360/360 | 360/360 |  |
| `knights` | 360/360 | 360/360 |  |
| `msword` | 360/360 | 360/360 |  |
| `megaman` | 360/360 | 360/360 |  |
| `mtwins` | 360/360 | 360/360 |  |
| `mercs` | not comparable | not comparable |  |
| `nemo` | 360/360 | 360/360 |  |
| `pnickj` | 360/360 | 360/360 |  |
| `pokonyan` | 360/360 | 360/360 |  |
| `qad` | 360/360 | 360/360 |  |
| `qtono2j` | 360/360 | 360/360 |  |
| `sf2ce` | 360/360 | 360/360 |  |
| `sf2hf` | 360/360 | 154/360 | 1510 |
| `sf2` | 360/360 | 360/360 |  |
| `strider` | 360/360 | 360/360 |  |
| `kod` | 360/360 | 360/360 |  |
| `3wonders` | 360/360 | 360/360 |  |
| `unsquad` | 360/360 | 360/360 |  |
| `varth` | 360/360 | 360/360 |  |
| `willow` | 360/360 | 360/360 |  |

Two sets are not comparable (PAL dumps missing from the romsets). `sf2hf` differs from frame 1,505 on isolated whole pictures (86,016
pixels, every pixel); against MAME's frame one before or after, other frames differ instead (offset test at step 1): a one-frame
slip, independent of the input phase between 5 and 40 lines. The King of Dragons and Mega Twins no longer slip. Sound not repeated.

**Linux witness** (Debian 13, Hermès, Python 3.13.5, gcc 14.2; one conversion of `sf2ce`, standard level, in a folder apart that
was removed afterwards; the ROM was copied for the run and deleted): 0 interpreted 68000 and Z80 instructions, 129,196,735 native
68000 and 40,478,778 native Z80 instructions over both routes, the reference comparison, the packed replay and the fresh-process state
check passed, and the CPU, RAM, image and sound hashes and the trace hashes of both routes are **identical** to the Windows conversion
(attract `3bbf4e1b9e913170` image, play `58d38aebe87defe0`). The conversion took 237 seconds
(Windows 138 s), the first 147 seconds including a build of SDL; these are wall times on a shared machine, not timings.

## 1 November 2026 (1.6.6 tree): Z80 corrections, sound against MAME and a third Linux witness

Branch `spec/cps1-165e` on local `main` of 1.6.5 (`850cf2d`).

**Z80 corrections** (`neogeo_z80.FIXES`, [UPSTREAMS.md](UPSTREAMS.md#fixes-carried-as-our-own-patches-in-166)). The replay of 51,328 independent
Z80 vectors through the CPS-1 path goes from 50,429 to **51,260** matching states and from 51,200 to **51,328** matching clocks, native and interpreted
paths identical on every vector; the 68 left are the X and Y flags of `SCF` and `CCF` (the Q latch is not carried). A/B from the main checkout
(`tools/ab_conversion.py`, tree of 1.6.5 against the tree of the branch): `sf2ce` and `ffight` identical except the Z80 core, its translated bodies,
the knowledge record (engine revision 9) and the compressed size; `nam1975` and `mslug3`: picture and sound hashes identical, Z80 and hardware hashes
different from frame 2380 of the AES play route (`nam1975`, cause `LD A,R`: the game reads R, the X and Y bits of F are now those of the result) and
from row 506 of the per-frame state checks (`mslug3`, causes WZ of `LD IX,(nn)` and `LD (nn),IX`, then X, Y and WZ of `IN r,(C)`): found by converting
again with the corrections switched off one at a time (a control run with all of them off reproduces the 1.6.5 hashes exactly).

**Sound against MAME 0.289** (`tools/cps1_mame_compare.py --sound`, credited play route of 3,600 frames, 24 comparable sets; MAME's WAV at 55,930 Hz
against the game's samples, one-second windows with sound on both sides; the lag found by correlation is zero on every set). Level difference in
dB (median and largest window), cosine of the averaged magnitude spectra, largest third-octave difference of the averaged spectrum below 4 kHz and
from 5 to 16 kHz (dB), waveform correlation, windows silent on one side:

| Set | Level median | Level max | Spectra cosine | Bands < 4 kHz | Bands 5 to 16 kHz | Waveform | Silent |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `1941` | 0.139 | 0.39 | 0.99740 | 0.97 | 0.40 | 0.67 | 18 |
| `captcomm` | 0.045 | 0.29 | 0.99917 | 0.41 | 1.15 | 0.72 | 14 |
| `cawing` | 0.054 | 0.16 | 0.99890 | 0.28 | 0.31 | 0.49 | 12 |
| `dynwar` | 0.024 | 0.40 | 0.99361 | 0.53 | 0.22 | 0.43 | 14 |
| `ffight` | 0.118 | 0.65 | 0.99638 | 1.06 | 0.88 | 0.62 | 14 |
| `ghouls` | 0.011 | 0.10 | 0.99893 | 0.06 | 0.04 | 0.22 | 28 |
| `knights` | 0.024 | 0.21 | 0.99874 | 0.63 | 0.51 | 0.57 | 13 |
| `msword` | 0.104 | 0.66 | 0.99807 | 0.67 | 0.60 | 0.67 | 18 |
| `megaman` | 0.060 | 0.64 | 0.99707 | 0.76 | 0.26 | 0.68 | 11 |
| `mtwins` | 0.056 | 0.87 | 0.99782 | 0.46 | 0.28 | 0.49 | 13 |
| `nemo` | 0.122 | 0.26 | 0.99788 | 0.71 | 0.29 | 0.61 | 22 |
| `pnickj` | 0.032 | 0.24 | 0.99881 | 0.15 | 0.20 | 0.56 | 22 |
| `pokonyan` | 0.371 | 0.99 | 0.99599 | 0.82 | 0.60 | 0.35 | 13 |
| `qad` | 0.060 | 0.50 | 0.99788 | 0.76 | 0.56 | 0.56 | 12 |
| `qtono2j` | 0.049 | 0.39 | 0.99896 | 1.07 | 1.95 | 0.80 | 8 |
| `sf2ce` | 0.050 | 0.39 | 0.99888 | 0.90 | 1.07 | 0.80 | 16 |
| `sf2hf` | 0.415 | 5.41 | 0.98625 | 1.43 | 1.64 | 0.29 | 16 |
| `sf2` | 0.033 | 0.13 | 0.99920 | 0.70 | 0.56 | 0.86 | 15 |
| `strider` | 0.006 | 0.68 | 0.99112 | 0.18 | 0.23 | 0.49 | 10 |
| `kod` | 0.018 | 0.35 | 0.99899 | 0.89 | 0.77 | 0.74 | 10 |
| `3wonders` | 0.096 | 0.92 | 0.99627 | 0.41 | 0.52 | 0.41 | 15 |
| `unsquad` | 0.033 | 0.40 | 0.99673 | 0.50 | 0.21 | 0.31 | 12 |
| `varth` | 0.105 | 0.30 | 0.99802 | 0.93 | 1.09 | 0.66 | 12 |
| `willow` | 0.013 | 0.20 | 0.99657 | 0.06 | 0.12 | 0.36 | 13 |

The waveform correlation is low because the OKI is interpolated linearly here and filtered by MAME in its own way, and because windows are not
phase-aligned below the sample; it is not claimed. `sf2hf` is the set whose picture slips by a frame in the same run. Physical audio and latency are
not measured.

**Linux witness 3** (Debian 13, Hermès, one conversion of `1941`, standard level, in a folder apart removed afterwards, the ROM copied for the run
and deleted, archive of `main` and a copy of the dependency cache; `.deps` of the existing checkout read, nothing else touched): 0 interpreted 68000 and
Z80 instructions, 101,209,464 native 68000 and 44,659,319 native Z80 instructions over both routes, every check passed, and the CPU, RAM, picture and
sound hashes and the trace hashes of both routes are **identical** to the Windows conversion (attract picture `5bd0c5a2c01d5df5`, play `4def87fdac4ed72a`).
It took 119 seconds (Windows 67 s): wall times on a shared machine, not timings.

## 2 November 2026 (1.6.7 tree): the CPS-1.5 board without its sound, against MAME

The QSound boards (CPS-1.5) join as an experimental tier ([CPS1.md](CPS1.md#cps-15-qsound-boards-experimental-tier)). Here the board runs without
its sound (the QSound registers are accepted and answer ready after the next sample; the sound is silence), compared with MAME 0.289 with the same
tool as the other sets: `tools/cps1_mame_compare.py`, FBNeo romsets of the test collection (one set per family: `wof`, `dino`, `punisher`,
`slammast`, `mbombrd`), the QSound DSP ROM read by MAME from the BIOS folder (MAME needs it to start; the game under test does not read it yet),
stand-in files of one byte for the PLD dumps the zips lack, routes `attract` and `play` of 3,600 frames, a picture compared every 10th frame.

| Set | `attract` | `play` |
|---|---|---|
| `wof` | 360 of 360 identical | 360 of 360 |
| `dino` | 359 of 360 (frame 1,640) | 360 of 360 |
| `punisher` | 360 of 360 | 360 of 360 |
| `slammast` | 360 of 360 | 360 of 360 |
| `mbombrd` | 360 of 360 | 360 of 360 |

`wof` also compared on each of its first 300 frames: 308 of 308 identical. `dino` compared on each of the first 1,700 frames of `attract`: two frames
differ (1,279 and 1,640, 4,400 to 4,700 pixels in the upper right of the picture), the frames around them are identical; the cause was not isolated
(mid-frame writes are not modelled, see the timing model in the known limits).

Counted per processor on 3,600 frames of `attract` of a first-pass build (nothing learned yet): interpreted Z80 instructions 0 on the five sets; interpreted
68000 instructions 0 on `wof`, `dino`, `punisher` and `mbombrd` (56 to 67 million native 68000 instructions, 48 to 50 million native Z80), and 39,388 on
`slammast` (66,679,903 native), all from a checksum routine the game copies into work RAM: the next pass of a conversion builds guarded native code
for such variants, as it does for the CPS-1 sets.

The first comparison of `wof` differed for 20 frames from the first picture on: the game reads its EEPROM during start-up and waits for each write
to finish, and the model took writes as instant. With the write and erase times of MAME's `eeprom.cpp` (1.75 ms, 1 ms, 8 ms for all cells) every
frame agrees. What this shows: pictures agree with MAME's on these routes. It says nothing about the sound (not there yet), the other 13 sets, hardware
fidelity or play.

### The sound of the CPS-1.5 boards, against MAME (same day, 1.6.7 tree)

The high-level QSound model (`native/cps1_qsound.c`, from MAME's `qsoundhle.cpp`) with the DSP ROM of the BIOS folder (the QSound DSP ROM
the player supplies: nothing of it is kept in a report), `tools/cps1_mame_compare.py --sound` adapted to the two channels at 24,038 Hz
(`-samplerate 24038` for MAME, each channel compared on its own), `attract` and `play` routes of 3,600 frames of the five sets, pictures
every 10th frame. The picture agreed on 3,599 of the 3,600 compared frames of the ten routes of the five sets: the exception is the isolated
`dino` frame 1,640 of `attract` (see the open items). The sound of `play`, per channel (left and right in the same
ranges), 60 windows of one second:

| Set | level difference, median / max (dB) | averaged spectrum cosine | one-third-octave bands, worst (dB) | waveform correlation, aligned, median / min |
|---|---|---|---|---|
| `wof` | 0.010 / 0.10 | 0.9994 to 0.9997 | 0.07 | 0.97 / 0.76 |
| `dino` | 0.006 to 0.010 / 0.30 | 0.9997 | 0.06 | 0.98 / 0.72 |
| `punisher` | 0.009 / 0.09 | 0.9992 to 0.9994 | 0.15 | 0.98 / 0.88 |
| `slammast` | 0.006 to 0.008 / 0.85 | 0.9968 to 0.9969 | 0.12 | 0.96 / 0.56 |
| `mbombrd` | 0.005 to 0.006 / 0.08 | 0.9992 to 0.9994 | 0.05 | 0.97 / 0.82 |

The attract routes of `wof`, `dino` and `punisher` are silent on both sides over the first minute; `slammast` and `mbombrd` play music in
attract and agree there too (levels 0.003 dB). The correlation is not 1: MAME writes the sound at 24,038 Hz while the chip makes 24,038.46,
so the two drift by half a sample a second (the waveform correlation of the whole signal is low whatever the sound, which is why the aligned one is
given), and a register write can land one sample earlier or later than MAME's stream puts it. Not claimed: waveforms equal, hardware.

**Open items** (CPS-1.5): the two isolated frames of `dino` in `attract` (1,279 and 1,640, 4,400 to 4,700 pixels in the upper right of the
picture, the frames around them identical; the every-10th-frame comparison catches only the second; the cause is not isolated, mid-frame
writes are not modelled); the 13 sets of the tier that the
test collection does not hold; a run of the DSP16 instead of the model (about 10 to 15 hours of work, a third counted processor); the
owner's play trial of the tier.
