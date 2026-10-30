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
