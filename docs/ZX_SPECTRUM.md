# ZX Spectrum

Status: **experimental, in development** (step 1 of [NEW_MACHINE.md](NEW_MACHINE.md), from 21 November 2026). The profile
identifies snapshots and writes reports; **nothing is converted yet**, and no installation lists the machine (it is a
developer-only profile, as the Game Boy Advance was before its first conversion). This page says what the machine will
convert, what it leaves out, and how the five measures stay apart.

## 1. Scope

| First (this experimental profile) | Later | Left out for now |
|---|---|---|
| Snapshots of the 16K, 48K and 128K (and the +2, a 128K with another menu ROM): `.z80` versions 1, 2 and 3 and `.sna` (48K and 128K), from a file or a ZIP holding exactly one | `.szx` snapshots; the +2A and +3 (another contention pattern, port 1FFDh, the +3 disk) | Tapes (`.tap`, `.tzx`): their loaders need exact EAR timing, and a snapshot skips every loader; the Interface 1 and Microdrive, the Timex, Pentagon, Scorpion and other clones, the ZX80 and ZX81 |
| The ULA picture (256 x 192, attributes, flash, the border per line), the beeper, the AY-3-8910 on the 128K, the keyboard, the Kempston and Sinclair Interface 2 joysticks, quick states | The floating bus (a few games read it), the ULA's memory contention | Games that load their next level from tape during play: a snapshot cannot; they stop at that load, and the report says so |

A snapshot is the machine's RAM and registers at one moment, saved after the game had loaded. The reader
(`retrorecomp/zxs_snapshot.py`, our own code from the public format descriptions) refuses, with a sentence, a snapshot of a
machine the converter does not model, one taken with the Interface 1 or TR-DOS ROM paged in, one that carries a ROM of its
own, and any file whose memory blocks do not decode to whole 16 KiB pages.

## 2. The route

The Z80 is translated by the shared banked Z80 chain of the Master System and the MSX (`retrorecomp/z80_chain.py`, the
pinned smsggrecomp generator and z80-recomp-core), on a machine description of the Spectrum's own; what is not translated
runs on the reference interpreter (superzazu/z80), counted. The ULA, the beeper, the 128K paging and the snapshot reader are
our own MIT code, written with floooh/chips (zlib) and Clock Signal (MIT) as written references only; the AY-3-8910 is the
MSX's model, made shared. No GPL code goes into a Spectrum game: Fuse, libspectrum, ZEsarUX and MAME's Spectrum driver are
references and external checks only. This is the maintainer's choice of 21 November 2026 (route A).

## 3. The ROM

A snapshot holds no ROM, yet the game calls the ROM's routines and its interrupt runs the ROM's handler: every converted
Spectrum game holds the ROM of its model, translated with it. The ROMs are Amstrad's copyright, redistributed under
Amstrad's permission for emulators of 31 August 1999 (no charge for the ROM code, copyright messages unaltered;
[zx-spectrum-roms.md](../licenses/zx-spectrum-roms.md)). On the maintainer's choice of 21 November 2026:

- by default the converter fetches `48.rom`, `128-0.rom` and `128-1.rom` once from a pinned source (the `roms/` folder of the
  Fuse project, at one commit) and checks the size and SHA-256 of each on every use (`retrorecomp/zxs_roms.py`); nothing of them
  is in Retro-Recomp's repository or installer;
- a player may give their own ROM in **Options → ZX Spectrum** instead (the 48K ROM, and the 128K ROM as one 32 KiB image or
  its editor ROM with the BASIC ROM beside it). It is accepted when its SHA-256 is the one of the same images, so the game
  is the same either way; Options' « Find firmware in a folder… » looks for these files too.

## 4. The five measures

Native code, CPU fidelity, hardware fidelity, gameplay validation and physical latency are kept apart in the report, the
interface and this page. Nothing is measured yet: the report skeleton (`retrorecomp/zxs_conversion.py`) carries every measure
as not measured or not validated, and the interpreter fallback will be counted in Z80 cycles, as on the MSX.

**A hardware-fidelity limit, stated plainly: the ULA's memory contention is not modelled.** On a real Spectrum the CPU is slowed when it
touches 4000h-7FFFh (and some ports) while the ULA draws the screen; here every instruction takes its plain Z80 time. Games run
slightly faster than on the machine, and effects timed to the T-state (multicolour engines, some border effects and beeper tunes)
can differ. Nothing claims exact timing. Contention comes in a later stage of step 1, written as a design for the shared Z80 chain
first, and it is required before the panel is judged for leaving the experimental status (Arkanoid and the multicolour games
depend on it).

## 5. Qualification

The machine's column of [QUALIFICATION.md](QUALIFICATION.md) is `?` except G1 (`P`: the status is declared and linted). The
panel of the study, used for the gates once conversions run: Manic Miner (the first game: 48K, the beeper, the ROM's
interrupt handler), Jetpac (16K), Arkanoid (the floating bus question), Match Day II (two players), Head over Heels (128K
paging and the AY), Robocop (the whole game in the 128K banks, sampled speech), Elite (heavy maths, the keyboard as the
controller), The Hobbit (typing and printing through the ROM); in reserve Uridium and Rainbow Islands.

## 6. Multiplayer (later)

Two seats: the Sinclair Interface 2 has two joysticks on the keyboard matrix, and the Kempston beside it is the common pair.
The whole state (48 or 128 KiB of RAM, the ULA and AY registers, the CPU) is small, so the rollback tier is expected.
