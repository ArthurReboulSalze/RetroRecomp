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
5. **Native code, next stage.** The code the game runs will become guarded native steps built on the 68000 decoder, as for the
   Amiga and the X68000. Until then the report says that all of the 68000's instructions are interpreted.

## 3. The five measures

| Measure | What is known today |
| --- | --- |
| Native code | None yet (next stage): every instruction runs on Hatari's interpreter and is counted as interpreted (Bomb Jack: 32.9 million instructions on its 3,000-frame route, 100 % interpreted). |
| CPU fidelity | Hatari's cycle-exact WinUAE 68000. Not compared with the SingleStepTests 68000 vectors yet. |
| Hardware fidelity | Not claimed. |
| Gameplay validation | None. |
| Physical latency | Not measured. |

## 4. Known limits

- STE, TT, Falcon, hard disks and CD-style media are out of scope. EmuTOS, the TOS for a player who has none, is not available yet.
- Linux is pending: the profile has not been run there.
- Quick states: saving one leaves the running machine unchanged (checked on every conversion: the delivered copy saves a state on
  its main route and its trace still equals the reference). A state loaded by a fresh process continued the saved timeline on the
  two games converted so far (Bomb Jack, Another World: CPU registers, RAM and picture of 400 frames; the sound samples of the
  first frames after a load differ, because Hatari does not save the state of its sound output). A state saved while a disk is
  being read is not yet known to continue exactly; the conversion reports the comparison, it does not refuse the game for it.
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
