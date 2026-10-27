# Capcom CPS-1

Experimental profile (`cps1`) for the standard CPS-1 arcade boards (10 and 12 MHz
68000, Z80 sound with a YM2151 and an OKI MSM6295). QSound boards, the
CPS-1.5/CPS-2 families and bootlegs are outside this scope. The board's
sources and licences are listed in [cps1-machine.md](../licenses/cps1-machine.md)
and [cps1-ymfm.md](../licenses/cps1-ymfm.md).

## Converting

Add MAME or FBNeo ZIP romsets with **Automatic** detection, or choose
**Capcom CPS-1**. No BIOS is needed. Sets are recognised by the CRC of their
program ROMs, then every file is checked against the catalogue's SHA-1, so
renamed members and both romset dialects work. A split clone (for example
`sf2ua.zip`) needs its parent ZIP (`sf2.zip`) in the same folder; nothing is
written there. 129 sets of the catalogue are in scope; the converter names the
reason when a set is not (QSound, unverified graphics mapper, bootleg).

Exports go to `Games/CPS-1`. The conversion:

1. assembles the board's memory regions from the ZIPs (in the build folder);
2. translates the whole 68000 program ROM and the Z80 sound ROM (every byte
   position, both banks) into guarded native code;
3. runs every route twice in the same executable: once with every instruction
   interpreted (the fresh reference), once with the native code. The per-frame
   CPU registers and clocks, work/graphics/sound RAM, image and sound must be
   identical;
4. learns work-RAM code that was still interpreted and repeats (passes);
5. compresses the executable and compares it again with the reference;
6. saves a quick state, loads it in a fresh process and requires the same
   continuation, and checks that a damaged state is refused.

Scan levels: **quick** runs one credited play route; **standard** adds the
attract mode; **extended** and **thorough** add one or two 18,000-frame
pseudo-random routes. Routes insert a coin, press Start, then move and press
buttons; each route is reproducible from the romset identity.

The report (`datas/reports/…/conversion-report.json`) separates native code,
interpreter fallback (68000 and Z80 counted separately), the board model's
status and what was not measured: board fidelity against real hardware, full
playthroughs and physical latency are not claimed.

## Playing

The game uses the shared 16-bit menus (F1 help, F2 controls, F3 filter, F4
display, F6 autofire, F7 language, F8/F9 quick state, F12 gameplay feedback).
See [controls](CONTROLS.md#capcom-cps-1). The 384×224 picture is shown at 4:3;
vertical games (1941, Varth, Mercs…) are rotated and shown at 3:4. Three- and
four-player boards take the third and fourth controllers. The F2 **DIP
switches** page sets the board's switches with MAME's names and settings; the
choice is kept per game and most boards read it at power-on (Shift+F1).
Conversions always validate the default switches and drive players 1 and 2
only. The board keeps no non-volatile memory, so there are no ordinary saves
besides F8/F9.

The window title says **Native code** or **Interpreter fallback**; F1 also shows
the sound CPU's state. With F12 enabled, interpreted instructions met while
playing are recorded beside the game and used at the next conversion.

## Qualified sets (24 October 2026, Windows)

Standard scan level: attract and credited play routes of 3,600 frames each,
up to eight conversions at once, the parent ZIPs of the NAS (FBNeo). Every
set passed the fresh interpreted reference on each route, the compressed
executable comparison and the fresh-process F8/F9 check, with the default
DIP switches; validation routes drive players 1 and 2.

| Game | Set | 68000 fallback | Z80 fallback | Notes |
| --- | --- | --- | --- | --- |
| 1941: Counter Attack | `1941` | 0 | 0 | vertical |
| Adventure Quiz Capcom World 2 | `cworld2j` | 0 | 0 |  |
| Captain Commando | `captcomm` | 0 | 0 | 4 players |
| Carrier Air Wing | `cawing` | 0 | 0 |  |
| Dynasty Wars | `dynwar` | 0 | 0 |  |
| Final Fight | `ffight` | 0 | 0 |  |
| Ghouls'n Ghosts | `ghouls` | 0 | 0 |  |
| Knights of the Round | `knights` | 0 | 0 | 3 players |
| Magic Sword: Heroic Fantasy | `msword` | 0 | 0 |  |
| Mega Man: The Power Battle | `megaman` | 0 | 0 |  |
| Mega Twins | `mtwins` | 0 | 0 |  |
| Mercs | `mercs` | 0 | 0 | vertical, 3 players |
| Nemo | `nemo` | 0 | 0 |  |
| Pnickies | `pnickj` | 0 | 0 | graphics mapper unverified by MAME |
| Pokonyan! Balloon | `pokonyan` | 0 | 0 | graphics mapper unverified by MAME |
| Quiz & Dragons: Capcom Quiz Game | `qad` | 0 | 0 |  |
| Quiz Tonosama no Yabou 2: Zenkoku-ban | `qtono2j` | 0 | 0 |  |
| Street Fighter II': Champion Edition | `sf2ce` | 75,546 (0.06%) | 0 |  |
| Street Fighter II': Hyper Fighting | `sf2hf` | 0 | 0 |  |
| Street Fighter II: The World Warrior | `sf2` | 0 | 0 |  |
| Strider | `strider` | 0 | 0 |  |
| The King of Dragons | `kod` | 0 | 0 | 3 players |
| Three Wonders | `3wonders` | 0 | 0 |  |
| U.N. Squadron | `unsquad` | 0 | 0 |  |
| Varth: Operation Thunderstorm | `varth` | 0 | 0 | vertical |
| Willow | `willow` | 0 | 0 |  |

Street Fighter II': Champion Edition runs part of its code from graphics
RAM, which native code does not cover yet: those instructions are
interpreted, counted and reported. No set needed learned RAM code, so there
was nothing to share when this table was made; the channel exists since the
shared paths below.

## Shared paths (27 October 2026, experimental)

CPS-1 takes part in the shared base of paths, as an experimental machine whose
engine will still change. The 68000 program and the Z80 sound ROM are
translated whole, so a CPS-1 path is an instruction the game ran from RAM
(work RAM or sound RAM). After a conversion that passed every check, those the
fresh interpreted reference runs executed are turned into **numbers about your
own ROM**: where their bytes sit in your assembled program or sound image. No
ROM byte, RAM word or code is stored or sent. What cannot be tied to your ROM
(code the game builds or unpacks, code run from graphics RAM) stays private and
is counted in the conversion report (`knowledge`).

- A player with the same complete romset rebuilds the instructions from their
  own ROMs; every conversion still compares each route with its fresh
  reference, and a conversion that fails with shared paths starts again without
  them.
- A path counts as qualified only for the engine revision that validated it
  (`knowledge.cores`): a new revision of the CPS-1 recompiler makes them wait
  again until a conversion of the new engine reaches them. The record has its
  own format number, and an unknown one is ignored alone.
- CPS-1 paths travel in version 3 exchange files and in line 3 of the shared base
  only. The shared paths are stored apart (`datas/knowledge/qualified-v3.json.gz`
  and `imported-v3.json.gz`); the other consoles' banks are untouched.
- The report still says **experimental**; sharing does not change that, nor
  does it claim anything about hardware fidelity or play.
- Feedback kind 14 (a program-ROM instruction left interpreted) is recorded and
  read by nobody: the ROM is swept whole. It is diagnostic only and never shared.
- The sharing can be withdrawn in one line (`path_profiles.EXPERIMENTAL_SHARED`).
  Details: [COMPILATION_LIBRARY.md](COMPILATION_LIBRARY.md#cps-1-joins-the-base-step-5-of-the-standardisation-27-october-2026-part-of-160). Final Fight gives the
same route hashes on Windows and on Debian 13.

Earlier native/reference agreement (step 3) also covered sf2, ghouls,
captcomm, megaman and strider. Since overlapping sprites are drawn in MAME's
order (the first sprite of the list stays on top, 24 October 2026), the
attract modes of ffight, ghouls, sf2, captcomm, strider and megaman match
MAME 0.289 pixel for pixel on every compared frame: one frame in 30 over
9,000 frames, 300 per set. That comparison is a development check, not part
of each conversion, and it measures agreement with MAME, not with the
original boards.

## Credited play and sound compared with MAME (27 October 2026)

A development check, not part of each conversion; it measures agreement with
MAME 0.289, not with the original boards. Each set runs the conversion's own
credited play route (coin, Start, then pseudo-random movement and buttons) for
3,600 frames in the reference board model and in MAME. MAME receives the same
raw port values through read taps on the 68000's input addresses, so both
sides read each value in the same frame; one frame in ten is compared pixel
for pixel.

- **21 of 24 sets** that MAME can run from the NAS match on all 360 compared
  frames: 1941, Three Wonders, Carrier Air Wing, Captain Commando (four-player
  inputs at their CPS-B addresses), Dynasty Wars, Final Fight, Ghouls'n Ghosts,
  Knights of the Round, Mega Man, Magic Sword, Nemo, Pnickies, Pokonyan,
  Quiz & Dragons, Quiz Tonosama no Yabou 2, Street Fighter II, Street Fighter
  II' Champion Edition, Strider, U.N. Squadron, Varth and Willow.
- **Three sets slip by one frame** during play: The King of Dragons from frame
  839, Mega Twins from frame 919 and Street Fighter II' Hyper Fighting from
  frame 1504. The pictures are the same one frame apart (a fade or a
  title step early or late), and their attract modes match MAME on all 300
  compared frames of 9,000. The King of Dragons and Mega Twins each match on
  all 360 frames when MAME's input change is moved to another point of the
  frame (a different point for each game), Hyper Fighting at none. A 68000 trace of The King of Dragons with the same
  inputs finds no instruction whose duration differs over 2,354,506
  instructions; the two cores part when MAME takes the VBLANK interrupt one
  instruction earlier than the reference. This is the interrupt-sampling
  limit described above (MAME samples interrupts at the end of a bus access),
  which can move a game's main loop by a frame relative to its input reads.
- **Not compared**: Adventure Quiz Capcom World 2 and Mercs (MAME needs PAL
  dumps, `q522b.1a` and `c628`, that the NAS romsets lack).

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
