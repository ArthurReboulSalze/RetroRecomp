# Capcom CPS-1

**Experimental** machine profile (`cps1`): the standard CPS-1 arcade boards at 10
and 12 MHz (68000, Z80 sound CPU, YM2151 and OKI MSM6295). QSound boards,
CPS-1.5/CPS-2, bootlegs and a few special boards are outside this scope. The
sources and licences of the board model are in
[cps1-machine.md](../licenses/cps1-machine.md) and
[cps1-ymfm.md](../licenses/cps1-ymfm.md).

## Contents

1. [At a glance](#at-a-glance)
2. [Structure of the machine](#structure-of-the-machine)
3. [Engine and upstream](#engine-and-upstream)
4. [In the project](#in-the-project)
5. [Controls and options](#controls-and-options)
6. [States and saves](#states-and-saves)
7. [Qualification](#qualification)
8. [Known limits](#known-limits)
9. [History](#history)

Processors: [CPU_68000.md](CPU_68000.md) (main CPU) and [CPU_Z80.md](CPU_Z80.md)
(sound CPU). Dated measurements: [CPS1_LOG.md](CPS1_LOG.md).

## At a glance

| | |
|---|---|
| Status | Experimental (the report says `experimental` for every CPS-1 conversion) |
| Accepted | MAME or FBNeo romset `.zip` files, chosen with **Automatic** detection or **Capcom CPS-1** |
| Scope | 129 of the 233 sets of the catalogue, derived from MAME's CPS-1 driver; for a set outside the scope the converter names the reason (QSound, rotary dial, serial EEPROM, timekeeper RAM, CPS Changer cartridge, bootleg or hack, special start-up, incomplete dump, not working) |
| Firmware | None: no BIOS is needed |
| Output | `Games/CPS-1` |
| Linux | The profile is marked `pending` (not yet "converted and played on Linux"); a Final Fight conversion on Debian 13 gave the same route hashes as on Windows |

Sets are recognised by the CRC of their program ROMs, never by name, then every
file is checked against the catalogue's SHA-1, so renamed members and both
romset dialects work. A split clone (for example `sf2ua.zip`) needs its parent
ZIP (`sf2.zip`) in the same folder; nothing is written there. 12 of the 129 sets
have a graphics mapper that MAME marks as unverified (for example `pnickj`,
`pokonyan`): they convert, but never count as evidence for a qualification.

### What a conversion does

1. Assembles the board's memory regions from the ZIPs (in the build folder).
2. Translates the whole 68000 program ROM and the Z80 sound ROM (every byte
   position, both banks) into guarded native code.
3. Runs every route twice in the same executable: once with every instruction
   interpreted (the fresh reference), once with the native code. The per-frame
   CPU registers and clocks, work/graphics/sound RAM, image and sound must be
   identical.
4. Learns work-RAM, graphics-RAM and sound-RAM code that was still interpreted
   and repeats (up to three passes by default).
5. Compresses the executable and compares it again with the reference.
6. Saves a quick state, loads it in a fresh process, requires the same
   continuation, and checks that a damaged state is refused.

Scan levels: **quick** runs one credited play route; **standard** adds the
attract mode; **extended** and **thorough** add one or two 18,000-frame
pseudo-random routes. Routes insert a coin, press Start, then move and press
buttons; each route is reproducible from the romset identity.

The report (`datas/reports/…/conversion-report.json`) separates native code,
interpreter fallback (68000 and Z80 counted separately), the board model's
status and what was not measured: board fidelity against real hardware, full
playthroughs and physical latency are not claimed.

## Structure of the machine

| Block | What the board has | How Retro-Recomp handles it |
|---|---|---|
| Main CPU | MC68000 at 10 or 12 MHz ([CPU_68000.md](CPU_68000.md)); program ROM up to 4 MiB | **Native code**: the whole program ROM is swept (every even offset that decodes legally) into guarded native steps; each step is checked against its live code words. **Reference**: Musashi from the pinned Geolith copy, with every instruction interpreted. **Counted interpreter** for anything not covered |
| Work RAM | 64 KiB at `0xFF0000` | Code the game copies or builds there is observed in one pass and becomes guarded native code in the next |
| Graphics RAM | `0x900000` to `0x92FFFF` (CPS-A/B registers, tile layers, sprites, palette) | Since 1.6.4, code run from it is guarded like work-RAM code (see [Known limits](#known-limits) and [UPGRADES.md](UPGRADES.md#cps-1-code-run-from-graphics-ram-is-guarded-natively-164-lot-h)) |
| Sound CPU | Z80 at 3.579545 MHz ([CPU_Z80.md](CPU_Z80.md)); ROM `0x0000`-`0x7FFF` plus a switched 16 KiB window at `0x8000`-`0xBFFF` (two banks), RAM `0xD000`-`0xD7FF` | **Native code** at every byte position of the sound ROM, banks included; guarded Z80 RAM variants. **Reference**: the Z80 core of the pinned Geolith copy; the opcode an IM 0 interrupt supplies runs there and, since 1.6.5, is counted as interpreted. Two sound latches written by the 68000 are time-stamped and replayed when the Z80 reaches them |
| Video | CPS-A and CPS-B: three scroll layers (8x8, 16x16 and 32x32 tiles), sprites, star fields on some boards, row scroll, palette; 30 CPS-B board configurations and 58 graphics mappers in the catalogue; 8 MHz pixel clock, 512x262 total, 384x224 visible, about 59.637 Hz | Reference board model in C adapted from MAME's driver ([cps1_machine.c](../native/cps1_machine.c)). The frame is rendered whole at the start of VBLANK and coloured when it ends, as MAME presents it. Graphics ROM bank mapping, priorities and sprite order follow MAME |
| FM sound | YM2151 at 3.579545 MHz, output 55,930 Hz | ymfm (BSD-3-Clause) behind `native/cps1_opm.cpp`; the chip's IRQ goes to the Z80 |
| PCM sound | OKI MSM6295 at 1 MHz, sample rate 7,576 Hz or 6,061 Hz by pin 7 (the Z80 switches it) | Model adapted from MAME's OKI code (`native/cps1_oki.c`), interpolated linearly at the YM2151 rate; the host mixes mono and resamples to 48 kHz |
| Inputs | Joystick, six buttons, Start and coin per player; up to four players; DIP switches (`DSWA` to `DSWC`) | Host kit adapter; the DIP page uses MAME's names and settings |
| Memory | No non-volatile memory on the standard boards | No ordinary saves; quick states only |

Interrupts follow MAME: the 68000 takes its level-2 interrupt at VBLANK and the
interrupt acknowledge waits for the E clock. Prefetch is not modelled and
mid-frame register writes and 68000 bus waits are not either (see
[Known limits](#known-limits)).

## Engine and upstream

Pinned repositories (the table, the update rules and the review record are in
[UPSTREAMS.md](UPSTREAMS.md)):

| Part | Upstream | Licence |
|---|---|---|
| Board data, ROM layouts, DIP names, OKI model | [mamedev/mame](https://github.com/mamedev/mame) at `61a2229`: no code is built from a checkout; the ROM-free catalogue (`assets/cps1-catalogue.json`) and the OKI model are adapted from the driver | BSD-3-Clause |
| YM2151 | [aaronsgiles/ymfm](https://github.com/aaronsgiles/ymfm) at `81aec25` | BSD-3-Clause |
| Reference 68000 and Z80 | [libretro/geolith-libretro](https://github.com/libretro/geolith-libretro) at `2dc88e3` (Musashi, Z80 core) | BSD-3-Clause |
| 68000 translation | [mstan/segagenesisrecomp](https://github.com/mstan/segagenesisrecomp) at `00c60bc` and its submodule [mstan/m68k-recomp-core](https://github.com/mstan/m68k-recomp-core) at `921f67b` (instruction bodies and decoder, through `retrorecomp/m68000.py` and the Mega Drive and Neo Geo generators; never copied into the repository, our fixes are written from the MC68000 manual) | PolyForm Noncommercial 1.0.0 |
| Z80 translation | the Z80 core of the pinned Geolith copy (see `licenses/superzazu-z80.md`) | see the licence file |

The 68000 helpers and the Neo Geo and Mega Drive code generators are shared
with other machines: an edit there moves the CPS-1 game stamp as well as the
owner's. The CPS-1 files are all game files in
[stamp_inputs.py](../retrorecomp/stamp_inputs.py); editing one moves the CPS-1
game stamp and possibly the quick-state key.

### Paths shared between players

CPS-1 takes part in the shared base of paths as an experimental machine whose
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
  own format number (1), and an unknown one is ignored alone. The engine
  revision includes `cps1_knowledge.GENERATOR_REVISION` (7 in the 1.6.4 tree, 8 since the IM 0 count of 1.6.5).
- CPS-1 paths travel in version 3 exchange files and in line 3 of the shared
  base only. The shared paths are stored apart
  (`datas/knowledge/qualified-v3.json.gz` and `imported-v3.json.gz`); the other
  consoles' banks are untouched.
- The report still says **experimental**; sharing does not change that, nor
  does it claim anything about hardware fidelity or play.
- Feedback kind 14 (a program-ROM instruction left interpreted) is recorded and
  read by nobody: the ROM is swept whole. It is diagnostic only and never
  shared. Kinds 15 and 16 (work-RAM and sound-RAM code met while playing) are
  the player's private build hints and are not persisted.
- The sharing can be withdrawn in one line (`path_profiles.EXPERIMENTAL_SHARED`).
  Details:
  [COMPILATION_LIBRARY.md](COMPILATION_LIBRARY.md#cps-1-joins-the-base-step-5-of-the-standardisation-27-october-2026-part-of-160).
  No CPS-1 path is qualified yet.

## In the project

| Part | Files |
|---|---|
| Converter | `retrorecomp/cps1.py` (identification, ZIP reading), `cps1_catalogue.py`, `cps1_board.py` (memory regions and board description), `cps1_codegen.py` (68000 and Z80 translation), `cps1_build.py` (project, state key), `cps1_conversion.py` (routes, passes, checks, report), `cps1_knowledge.py` (shared paths) |
| Profile | `retrorecomp/systems/cps1.py` (quick-state family `rr16`, shared paths withdrawable) |
| Native | `native/cps1_machine.c/.h` (board model), `cps1_native.c/.h` and `cps1_z80_native.h` (guarded native steps), `cps1_oki.c/.h`, `cps1_opm.cpp/.h` (ymfm wrapper), `cps1_host.c/.h`, `cps1_main.c`, `cps1_m68kconf.h`, `cps1_probe.c` (headless reference runner) |
| Host kit | `native/hostkit/adapters/rrhk_cps1.c` (actions, DIP page, players 3 and 4); the shared shell is described in [HOST_KIT.md](HOST_KIT.md) |
| Data | `assets/cps1-catalogue.json` (built by `tools/build_cps1_catalogue.py`); licences in `licenses/cps1-machine.md` and `licenses/cps1-ymfm.md` |
| Tools | `tools/cps1_release_check.py` (release check at the Standard level, wraps `tools/release_check.py`); `tools/cps1_vector_selftest.py` with `native/cps1_vector_checks.c` (independent 68000 vectors through the CPS-1 generator, a developer harness that builds no game) |
| Tests | `tests/test_cps1.py`, `test_cps1_board.py`, `test_cps1_codegen.py`, `test_cps1_integration.py`, `test_cps1_knowledge.py`, `test_cps1_liveness.py`, `test_cps1_vectors.py`, `cps1_generator_pins.json` (pins of the generator sources) |

## Controls and options

The game uses the shared 16-bit menus (F1 help, F2 controls, F3 filter, F4
display, F6 autofire, F7 language, F8/F9 quick state, F12 gameplay feedback).
Keys and pads are in [CONTROLS.md](CONTROLS.md#capcom-cps-1): arrows, W/X/C and
A/S/D for the six buttons, Enter for Start, Shift (or Back) for a coin. The
third and fourth controllers play three- and four-player boards (Captain
Commando, The King of Dragons, Knights of the Round, Mercs); they have no
default keys.

- **Display**: the 384x224 picture is shown at 4:3; vertical games (1941,
  Varth, Mercs…) are rotated and shown at 3:4.
- **DIP switches**: the F2 DIP page sets the board's switches with MAME's names
  and settings; conditional switches appear when their condition holds. The
  choice is kept per game (section `CPS1.Dips.<set>` of the export's settings
  file, keys `DSWA`, `DSWB`, `DSWC`) and most boards read it at power-on
  (Shift+F1 restarts). Conversions always validate the default switches and
  drive players 1 and 2 only.
- **Help page**: the window title says **Native code** or **Interpreter
  fallback**; F1 also shows the sound CPU's state.
- **Feedback**: with F12 enabled, interpreted instructions met while playing
  are recorded beside the game and used at the next conversion as private build
  hints ([RUNTIME_FEEDBACK.md](RUNTIME_FEEDBACK.md)).

## States and saves

F8/F9 quick states use the common 16-bit family format; the CPS-1 state has the
magic `CPS1S002` since 1.6.4, with every structure written field by field.
States of 1.6.3 (`CPS1S001`) are refused cleanly. A state loads only into the
same romset and the same board and runtime sources (its key hashes them). The
board keeps no non-volatile memory, so there are no ordinary saves besides
F8/F9. Every conversion saves a state, loads it in a fresh process, requires the
same continuation and checks that a truncated state is rejected. Compatibility
across releases: [GAME_STATES.md](GAME_STATES.md) and
[UPGRADES.md](UPGRADES.md#exports-of-163-in-164).

## Qualification

The gates are in [QUALIFICATION.md](QUALIFICATION.md). In its matrix, CPS-1 meets G1, G2, G4, G5, G6 and G15, is partial on G3, G8, G9,
G10, G11, G12 and G13 (G8 and G10 since 29 October 2026, see below), unknown on
G14, and G7 and G16 do not apply. Every
conversion runs the fresh-reference comparison (G4), the packed replay (G5) and
the fresh-process state check (G6) itself.

The five measures stay separate. A CPS-1 conversion measures **native code**
(counted per CPU) and **CPU fidelity against its own interpreted reference**,
route by route. **Hardware fidelity** against real boards, **gameplay
validation** (complete playthroughs) and **physical latency** are not measured
and not claimed.

### Qualified sets (24 October 2026, Windows)

The 26 sets below passed the standard scan level on 24 October 2026 (1.6.3
engine). **Eleven of them were measured again on 29 October 2026** on the 1.6.5
tree (converter commit `98debbb`, generator revision 8); the others keep their
24 October figures until they are measured again. Standard scan level: attract
and credited play routes of 3,600 frames each, every set against the fresh
interpreted reference on each route, the compressed executable comparison and
the fresh-process F8/F9 check, with the default DIP switches; validation routes
drive players 1 and 2. A campaign of twelve sets: the five risk cases (`wof`
is refused, see below), the release
check and six sets chosen by board and by known behaviour (`kod`, `mtwins` and
`sf2hf`, which slip a frame against MAME; `pokonyan`, an unverified graphics
mapper; `mercs`, vertical and three players; `cworld2j`, a quiz board). The
per-set counts are in [CPS1_LOG.md](CPS1_LOG.md#29-october-2026-165-tree-selective-requalification).

| Game | Set | 68000 fallback | Z80 fallback | Measured | Notes |
| --- | --- | --- | --- | --- | --- |
| 1941: Counter Attack | `1941` | 0 | 0 | 29 Oct 2026 | vertical |
| Adventure Quiz Capcom World 2 | `cworld2j` | 0 | 0 | 29 Oct 2026 |  |
| Captain Commando | `captcomm` | 0 | 0 | 29 Oct 2026 | 4 players |
| Carrier Air Wing | `cawing` | 0 | 0 | 24 Oct 2026 |  |
| Dynasty Wars | `dynwar` | 0 | 0 | 24 Oct 2026 |  |
| Final Fight | `ffight` | 0 | 0 | 29 Oct 2026 |  |
| Ghouls'n Ghosts | `ghouls` | 0 | 0 | 24 Oct 2026 |  |
| Knights of the Round | `knights` | 0 | 0 | 24 Oct 2026 | 3 players |
| Magic Sword: Heroic Fantasy | `msword` | 0 | 0 | 24 Oct 2026 |  |
| Mega Man: The Power Battle | `megaman` | 0 | 0 | 24 Oct 2026 |  |
| Mega Twins | `mtwins` | 0 | 0 | 29 Oct 2026 |  |
| Mercs | `mercs` | 0 | 0 | 29 Oct 2026 | vertical, 3 players |
| Nemo | `nemo` | 0 | 0 | 24 Oct 2026 |  |
| Pnickies | `pnickj` | 0 | 0 | 24 Oct 2026 | graphics mapper unverified by MAME |
| Pokonyan! Balloon | `pokonyan` | 0 | 0 | 29 Oct 2026 | graphics mapper unverified by MAME |
| Quiz & Dragons: Capcom Quiz Game | `qad` | 0 | 0 | 24 Oct 2026 |  |
| Quiz Tonosama no Yabou 2: Zenkoku-ban | `qtono2j` | 0 | 0 | 24 Oct 2026 |  |
| Street Fighter II': Champion Edition | `sf2ce` | 0 | 0 | 29 Oct 2026 | code run from graphics RAM: see below |
| Street Fighter II': Hyper Fighting | `sf2hf` | 0 | 0 | 29 Oct 2026 |  |
| Street Fighter II: The World Warrior | `sf2` | 0 | 0 | 24 Oct 2026 |  |
| Strider | `strider` | 0 | 0 | 29 Oct 2026 |  |
| The King of Dragons | `kod` | 0 | 0 | 29 Oct 2026 | 3 players |
| Three Wonders | `3wonders` | 0 | 0 | 24 Oct 2026 |  |
| U.N. Squadron | `unsquad` | 0 | 0 | 24 Oct 2026 |  |
| Varth: Operation Thunderstorm | `varth` | 0 | 0 | 24 Oct 2026 | vertical |
| Willow | `willow` | 0 | 0 | 24 Oct 2026 |  |

`sf2ce` runs a short routine from graphics RAM (a loop that fills and compares
the graphics memory, copied there by the game). On the 24 October engine the
play route left 75,546 interpreted 68000 instructions (0.06 percent); since
1.6.4 the native code guards instructions run from graphics RAM, and the
29 October conversion reports **zero interpreted instructions** on both routes
(33 graphics-RAM instructions observed, kept as private build hints and never
shared). The eleven sets converted with no 68000 or Z80 instruction interpreted
on the routes run (the build counts the Z80 interrupt mode 0 path since 1.6.5,
but no route met it); `wof` (QSound) was refused with the named reason
("not supported yet: qsound"). These
are agreement of the native code with the board model's own interpreted
reference: they are not CPU, hardware or gameplay validation, and "zero" means
that the routes run met no interpreted instruction, not that none exists.

### Independent evidence and liveness (29 October 2026)

Two gates of the "supported" checklist got evidence on the 1.6.5 tree. Both are CPU or activity evidence, not hardware
fidelity, gameplay or latency.

**Independent CPU evidence (G10), 68000.** The SingleStepTests vector fixtures of the repository (834 shift, 2,089 prefetch
and 864 exception vectors, MIT, generated with MAME) are replayed through the CPS-1 generator path by
`tools/cps1_vector_selftest.py`: the translated steps agree with every one of them on registers, SR, PC, written bytes and
clocks, and the Musashi reference differs from the vectors in a few named groups (division and `CHK` flags, `CHK` clocks,
one line-F frame). The numbers, the two authored trace vectors that neither path delivers and the limits are in
[CPU_68000.md](CPU_68000.md#tests-and-vectors). **The Z80 sound CPU has no independent vector replay yet**: the
SingleStepTests/z80 corpus has to be downloaded first (the SMS and GG tool `tools/fetch_z80_vectors.py` caches a sample).

**Liveness (G8).** Since 1.6.5 each route of the conversion report carries `final_checks[].liveness`, read from the route's
per-frame trace: `distinct_pictures`, `picture_changes` and `last_picture_change_frame` (frames whose image hash differs from
the previous frame's), `audible_frames` and `last_audible_frame` (frames whose sound hash is not that of silence). The
conversion is refused when a route's picture never changes (it already required a non-uniform picture on every route and
sound on at least one). Measured on the eleven sets of the 29 October campaign (standard level, 3,600 frames per route; each
cell is pictures seen, or audible frames, then the last frame where the picture changed, or was audible):

| Set | Attract: pictures / last change | Attract: audible / last | Play: pictures / last change | Play: audible / last |
| --- | ---: | ---: | ---: | ---: |
| `1941` | 1,765 / 3,600 | 1,456 / 3,600 | 2,376 / 3,600 | 2,434 / 3,600 |
| `sf2ce` | 1,515 / 3,600 | 2,702 / 3,600 | 1,534 / 3,600 | 2,614 / 3,600 |
| `ffight` | 963 / 3,599 | 1,997 / 3,600 | 1,169 / 3,600 | 2,688 / 3,600 |
| `captcomm` | 2,265 / 3,600 | 2,192 / 3,600 | 1,578 / 3,600 | 2,660 / 3,600 |
| `strider` | 1,492 / 3,599 | 1,612 / 2,992 | 2,864 / 3,585 | 2,964 / 3,600 |
| `kod` | 1,967 / 3,573 | 3,033 / 3,600 | 1,311 / 3,595 | 2,937 / 3,600 |
| `mtwins` | 1,639 / 3,600 | 0 / 0 | 2,388 / 3,600 | 2,715 / 3,600 |
| `sf2hf` | 1,540 / 3,600 | 2,661 / 3,600 | 2,290 / 3,600 | 2,600 / 3,600 |
| `pokonyan` | 1,308 / 3,600 | 2,661 / 3,600 | 2,196 / 3,600 | 2,595 / 3,600 |
| `mercs` | 1,470 / 3,600 | 706 / 3,600 | 2,118 / 3,584 | 2,482 / 3,600 |
| `cworld2j` | 995 / 3,500 | 2,870 / 3,600 | 1,264 / 3,599 | 2,870 / 3,600 |

On every route of these sets the picture is still changing within the last 100 frames (the longest gap is the attract route of
`cworld2j`, last change at frame 3,500), and the sound is audible up to the last frame, except Strider's attract route (last
audible frame 2,992) and the attract route of `mtwins`, which stays silent for its 3,600 frames while its credited play route
is audible. This shows that pictures and sound move on the routes
run; it does not say what they show, and the other fifteen sets of the table have not been converted with these fields yet.

**Where each gate stands for CPS-1** (the matrix itself is in [QUALIFICATION.md](QUALIFICATION.md)):

| Gate | Evidence for CPS-1 | State |
| --- | --- | --- |
| G1 status | profile, README, COMPATIBILITY and interface all say experimental | met |
| G2 report | the common report (v2) with separate 68000 and Z80 counters, [CPS1_LOG.md](CPS1_LOG.md#29-october-2026-165-tree-selective-requalification) | met |
| G3 native coverage | zero interpreted 68000 and Z80 instructions on both routes of 11 sets (29 Oct); 15 sets measured on 24 Oct | partial |
| G4, G5, G6 | `final_checks[].reference_match`, `packed.replay.match`, `game_states.validation` in every conversion | met |
| G7 saves | no non-volatile memory on the standard boards | not applicable |
| G8 liveness | the table above (11 sets) | partial: 15 sets not measured with the fields |
| G9 route depth | standard level, 3,600-frame attract and credited play; the 18,000-frame levels are not run on the panel | partial |
| G10 independent CPU evidence | 68000 vectors above; no Z80 corpus yet | partial |
| G11 independent hardware evidence | the MAME 0.289 comparison of 24 October and 27 October, measured before 1.6.4 and not repeated | partial |
| G12 panel | 26 sets, 11 re-measured | partial |
| G13 cross-OS witness | Final Fight, same route hashes on Windows and Debian 13 (27 October) | partial |
| G14 owner acceptance | owner trials of 27 October reported in chat, not recorded; a draft row is in QUALIFICATION.md | open |
| G15 honesty | the five measures separate everywhere; "zero" means the routes run | met |
| G16 shared knowledge | no CPS-1 path is qualified; the sharing is withdrawable | not applicable |

### Reference games and risk cases

- **Release check**: `1941` (0 interpreted opcodes on 68000 and Z80).
- **Risk cases** of the qualification campaign: Street Fighter II' Champion
  Edition (`sf2ce`, code run from graphics RAM), Final Fight (`ffight`, the same
  route hashes on Windows and Debian 13), Captain Commando (`captcomm`, four
  players), Strider (`strider`, compared with MAME) and Warriors of Fate
  (`wof`, a QSound set: refused with a named reason).

### Comparison with MAME

A development check, not part of each conversion; it measures agreement with
MAME 0.289, not with the original boards. Results of 24 and 27 October 2026,
**measured before 1.6.4** (full detail in [CPS1_LOG.md](CPS1_LOG.md)):

- Attract modes of six sets (ffight, ghouls, sf2, captcomm, strider, megaman)
  match pixel for pixel on every compared frame (one in 30 over 9,000 frames).
- Credited play, 3,600 frames, one frame in ten compared: **21 of 24 sets** match
  on all compared frames; The King of Dragons, Mega Twins and Street Fighter II'
  Hyper Fighting slip by one frame (the interrupt-sampling limit below);
  Adventure Quiz Capcom World 2 and Mercs could not be compared (PAL dumps
  missing).
- Sound (three sets): levels within 0.12 dB (median) and averaged spectra within
  0.998 to 0.99998 (cosine similarity); differences of up to about 18 dB in
  single windows between 5 and 10 kHz, from the OKI interpolation. Physical
  audio and latency are not measured.

## Known limits

- **Experimental**: the report says `experimental`; no CPS-1 path is qualified
  yet. Eleven sets were requalified on the 1.6.5 tree (29 October 2026); the
  other fifteen rows of the table keep their 24 October figures.
- **Out of scope**: QSound boards, CPS-1.5/CPS-2, rotary-dial, serial-EEPROM and
  timekeeper boards, CPS Changer cartridges, bootlegs and hacks, sets that
  need board-specific start-up, and sets with a never-dumped part.
- **Graphics mapper**: 12 convertible sets have a mapper MAME marks as
  unverified (`pnickj`, `pokonyan`, `striderua`, `mercsj` and others); they
  never count as qualification evidence.
- **Interrupt sampling**: the 68000 samples its interrupt lines 4 cycles before
  the end of an instruction, as measured on MAME 0.289 traces. A game's main
  loop can still move by a frame against its input reads (three sets slip by one
  frame in the MAME comparison).
- **Timing model**: the frame is rendered whole at the start of VBLANK;
  mid-frame register writes and 68000 bus waits are not modelled, and the
  native 68000 steps use Musashi's clock table with prefetch disabled, as the
  reference does.
- **Sound**: the OKI is interpolated linearly at the YM2151 rate; MAME resamples
  it with its own filter.
- **Trace and reference differences**: the Musashi reference is built without trace support (no post-instruction trace
  exception on either path), and differs from the MAME-made vectors on the flags of `DIVU`/`DIVS`/`CHK`; the translated
  steps follow the vectors there ([CPU_68000.md](CPU_68000.md#tests-and-vectors)). A game that reached such a case would
  show as a native/reference difference and be refused.
- **Players**: validation drives players 1 and 2 only, with the default DIP
  switches; the third and fourth players and other switches are not exercised by
  conversions.
- **Gameplay and hardware**: complete playthroughs, fidelity against original
  boards and physical latency are not measured. "Zero interpreted" always means
  that the measured routes met no interpreted instruction, not that none exists.
- **Linux**: the profile is marked `pending`; interactive play, sound and pads
  on Linux were not witnessed.
- **Quick-state writer**: no test of its own beyond the magic pinned by
  `tests/test_legacy_compat.py`.

## History

Short list; the dated measurements are in [CPS1_LOG.md](CPS1_LOG.md).

- 23 to 24 October 2026: catalogue and identification, reference board model,
  native 68000 and Z80, sprite order corrected against MAME, tile rendering,
  players 3 and 4, DIP switches,, qualification of 26 sets.
- 27 October 2026: CPS-1 joins the shared base of paths (experimental);
  comparison of credited play and sound with MAME 0.289.
- 29 October 2026 (1.6.5): the Z80 interrupt mode 0 opcode is counted; eleven sets requalified; independent 68000 vectors
  replayed through the CPS-1 generator; route liveness fields in the report.
- 1.6.4: code run from graphics RAM is guarded natively (`sf2ce` goes to zero
  interpreted instructions in the standard routes), quick state `CPS1S002`,
  artwork no longer searches a libretro catalogue that CPS-1 does not have.
