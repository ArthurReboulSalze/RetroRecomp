# Atari ST

Experimental profile (`atarist`), added in 1.7.1: the converter offers it when the installation carries the Atari ST files, and it
is not shared through the compilation library. It converts an Atari ST, STF or Mega ST floppy game into a standalone Windows
executable that runs the game on [Hatari](https://github.com/hatari/hatari). In this first stage there is no native code yet: every
68000 instruction is counted as interpreted. Nothing here says that a game plays completely, that the hardware is reproduced
faithfully or how long input takes to reach the screen: those are separate measures, listed below with what is known of each.

## 1. What is converted, and what is not

| Converted (experimental) | Not yet |
| --- | --- |
| Atari ST, STF and Mega ST (68000 at 8 MHz) floppy games: one disk image of IPF, STX, MSA or ST format, or a ZIP holding only such images (up to 8, played in the order of their names: `x (Disk 1).ipf`, `x (Disk 2).ipf`) | STE, TT and Falcon games; hard-disk images and GEMDOS folders |
| The player's own TOS 1.00, 1.02 or 1.04 (192 KiB), chosen in Options > Atari ST as a file or a folder of images and recognised by content (`retrorecomp/atarist_tos.py`) | EmuTOS as the default for a player without a TOS of his own: not yet, the TOS row is needed for now |
| The joystick, the mouse and the keyboard; quick states (F8/F9) | A panel of games; a played-through game |
| Windows | Linux (`linux = 'pending'`) |

A ZIP that holds anything other than floppy images is not claimed by the Atari ST profile. The input is read in place and never
changed. The player supplies the disks and the TOS; Retro-Recomp publishes no game, no disk and no firmware.

## 2. How the conversion works

1. **Reading the input.** `retrorecomp/atarist.py` reads the image or the ZIP (members sorted by name for the disk order) and takes the
   SHA-256 of the file as the identity of the game. `retrorecomp/atarist_tos.py` recognises the TOS by its header (never by its
   name) and takes its SHA-256 as the identity of the firmware.
2. **The machine.** The games run on Hatari (the cycle-exact WinUAE 68000, the Shifter, GLUE and MMU video, the YM2149, the MFP,
   the IKBD, the WD1772 and the DMA), pinned at one revision (`atarist_hatari.HATARI_REV`) and adapted at build time by
   `retrorecomp/atarist_hatari.py`: each replacement must find its pinned text exactly once, so an upstream change fails loudly.
   Its libretro frontend is driven frame by frame inside the game (`native/atarist_machine/`). The TOS and the disks are served from
   memory through a libretro virtual file system, so no file of the player is written to a work folder for the machine to read.
3. **Validation.** A conversion starts with a fresh interpreted reference run of the game. The game executable is then copied alone
   and replayed headless on the same bounded scripts (a main route of joystick, mouse and keyboard inputs and, at the Standard level,
   a second exploration route, 3,000 frames each): the picture, sound, RAM and CPU registers of every frame must equal the
   reference's. So must the compressed copy that is delivered. A quick state saved by the game is loaded by a fresh process, whose
   continuation is compared with the unbroken run and reported. A conversion that fails a check keeps the earlier export.
4. **Report.** The conversion report (schema v2, shape `atarist_conversion`) carries the interpreter fallback per CPU, in
   instructions, and keeps the five measures in separate objects.
5. **Native code.** The reference run records the 68000 instructions it runs from RAM, the TOS ROM and the cartridge area (their
   address and their own bytes). Each becomes a native step, grouped by form, that calls the very handler Hatari's cycle-exact
   table would call for its opcode (`retrorecomp/atarist_codegen.py`, read from the opcode table the reference player writes and
   the handler names of Hatari's generated `cpustbl.c`), so the prefetch, the cycles and the bus waits of the ST stay Hatari's.
   Every step starts with a live comparison of the instruction's words in memory and of the opcode Hatari prefetched: a word that
   changed (unpacked, loaded or self-modified code) sends the instruction back to the counted interpreter, and an opcode Hatari's
   table treats as illegal is never a step. The generator is the one the X68000 and the Amiga use (`retrorecomp/m68k_observed.py`,
   with the 68000 decoder of m68k-recomp-core). A pass that still meets interpreted instructions adds them and builds again.

## 3. The five measures

| Measure | What is known today |
| --- | --- |
| Native code | The panel of ten games, converted once each on Windows (6 November 2026, Standard level; Bomb Jack at Quick), main route of 3,000 frames (the exploration route is within a few instructions of it): see the table below. On the tested routes only. |
| CPU fidelity | The native steps call Hatari's own handlers: on the ten games the trace of every frame (picture, sound, RAM, CPU registers) of the native game and of its compressed copy is identical to the interpreted reference's, on every route. Hatari's cycle-exact 68000 replayed on the SingleStepTests 68000 fixtures (`tools/atarist_vector_selftest.py`, on the ST memory map and on a flat 24-bit bus): the final state agrees on every vector run except two authored divisions by zero whose N/Z flags the 68000 leaves undefined; the clock differences are the ST's 4-cycle bus rounding except 14 CHK vectors (4 clocks more); the native step equals the interpreter on every vector. The vectors are MAME-made, not silicon. |
| Hardware fidelity | Not claimed. |
| Gameplay validation | None. |
| Physical latency | Not measured. |

| Game (disks) | Native | Interpreted | Own screen reached by the route |
| --- | ---: | ---: | --- |
| Bomb Jack (1) | 32,910,533 | 1 | yes (title, credits) |
| Another World (2) | 33,425,253 | 1 | yes (code-wheel protection) |
| Operation Stealth (3) | 30,004,899 | 269,820 | no: GEM desktop (the game is a program to open; the interpreted ones are TOS line-F calls) |
| Captain Blood (2) | 29,886,965 | 264,772 | no: GEM desktop; its disk lists one file there on TOS 1.00, 1.02 and 1.04 alike, also when its sectors are read by an independent reader, so the game is started from the desktop (a route that opens it is needed) |
| Elite (1) | 39,364,470 | 3 | yes (manual-word protection) |
| Lethal Xcess (2) | 34,895,160 | 0 | yes (music device menu) |
| Turrican II (1) | 39,532,761 | 2,139 | yes (title, credits) |
| Carrier Command (1) | 38,039,056 | 0 | yes (language menu) |
| Kick Off 2 (1) | 39,538,414 | 2 | no: "Master file not present or damaged"; the same disk read as plain sectors by an independent reader reaches the title screen, so the IPF path is at fault (one defect found and fixed, see below; the cause is not found yet) |
| Indiana Jones and the Temple of Doom (1) | 40,182,497 | 2 | yes (title, high scores) |

"Own screen" means the route's last picture is the game's, not that the game was played.

IPF reading. Hatari's built-in IPF reader is checked against an independent reader of the same files (a development tool,
not shipped): on ordinary tracks the sectors decoded from the flux Hatari generates equal the IPF's own. On the five protected
tracks of Kick Off 2 (a 1024-byte sector written across the index) a phantom flux transition at the index corrupted the sector
after it; fixed in `retrorecomp/atarist_hatari.py` (the time from the last transition to the index joins the first interval). The
game still stops, so a second cause remains (its protection sector holds a no-flux area, which a real drive reads as noise).

## 4. Known limits

- STE, TT, Falcon, hard disks and CD-style media are out of scope. EmuTOS, the TOS for a player who has none, is not available yet.
- Linux is pending: the profile has not been run there.
- Quick states: saving one leaves the running machine unchanged (checked on every conversion: the delivered copy saves a state on
  its main route and its trace still equals the reference). A state loaded by a fresh process continued the saved timeline on the
  ten panel games (CPU registers, RAM and picture of 400 frames; the sound samples of the first frames after a load differ, because
  Hatari does not save the state of its sound output). A state saved while a disk is being read now resumes the read at the right
  place in the track (a fix to Hatari's IPF reader), but Bomb Jack saved during its loading still differs in its RAM from the second
  frame after the load; the conversion reports the comparison, it does not refuse the game for it.
- The first conversion needs the pinned Hatari sources (fetched into the workspace) and the C toolchain of the converter.
- The profile is hidden unless the installation carries the Atari ST converter's files (`retrorecomp/atarist.py`,
  `converter_available`).

## 5. Licences

- Retro-Recomp's Atari ST files (the converter modules, `native/atarist_machine/`, the host-kit adapter) are MIT.
- Hatari is **GPL-2.0-or-later**; three headers of its WinUAE CPU core say version 2 only, so **an exported Atari ST game is
  distributed under the GPL, version 2**, with Hatari at the pinned revision and the build-time changes of
  `retrorecomp/atarist_hatari.py` as its corresponding source. Its IPF reader (`src/floppies/ipf_dsk.c`) is BSD-3-Clause; the
  capsimg library is never built or linked. Notice: [licenses/hatari.md](../licenses/hatari.md).
- The disks and the TOS embedded in an export are the player's own; the GPL does not make them redistributable and Retro-Recomp
  distributes none.
- The 68000 decoder of m68k-recomp-core (PolyForm Noncommercial) is used under Matthew Stan's permission of 6 November 2026 to
  combine it with GPL code in Retro-Recomp's exports.
- Upstream pins and review: [UPSTREAMS.md](UPSTREAMS.md).

## 6. Where it stands in the qualification

The Atari ST column of [QUALIFICATION.md](QUALIFICATION.md) is `?` except G1. Leaving the experimental status is the maintainer's
own decision, after a very high evidence bar.
