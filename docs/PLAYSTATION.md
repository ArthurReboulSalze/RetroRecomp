# Sony PlayStation (experimental)

The PlayStation profile is **experimental** since 1.7.1. A conversion
makes a playable game whose R3000A code, as far as the conversion saw it run, is **native steps**; the rest runs on the machine's
interpreter and is counted and reported. This page says what it converts, how, and what it does not claim. The five measures
stay separate: native code, CPU fidelity, hardware fidelity, gameplay validation and physical latency.

**What "native" means here.** The game runs on a complete emulator core inside the executable, Beetle PSX, with its machine, its chips and their timing. Only the R3000A
instructions that the conversion saw running become native steps, and each step calls the core's own instruction handlers behind a guard: it is not a standalone translation of the
game. The GTE, the GPU, the SPU and the CD-ROM controller stay the core's own code. So the native share below measures how much CPU code avoids the core's interpreter; it cannot be
compared with the figures of a machine whose game code is translated, and it says nothing about hardware fidelity. See [ARCHITECTURE.md](ARCHITECTURE.md#machines-that-run-on-an-emulator-core).

## 1. What is converted

- **Discs as the player gives them**, read in place and never changed: a PS1 Classics EBOOT (`.pbp`, one to five discs), a CUE
  sheet with its BIN files (one file for the disc or one per track), a CloneCD image (`.ccd` + `.img` + `.sub`), a bare raw image
  (`.bin`, `.img`) or an ISO (`.iso`, 2,048-byte sectors: such a dump holds the file system only, so a game's XA sound and CD audio
  are missing from it, and the report says so). A multi-disc game is one EBOOT holding its discs (playlists, `.m3u`, are not read
  yet: that extension is the X68000's disk sets). A signed EBOOT from the PlayStation Store is refused (decrypting it would
  circumvent its protection).
- **NTSC-U, NTSC-J and PAL discs**, two players, the first memory card (kept beside the game; the second port is off).
- **The DualShock pad** of each player: the d-pad, the four face buttons, L1, R1, L2 and R2 (the gamepad's triggers), L3, R3,
  Start, Select, both sticks and vibration. It powers on in digital mode, as the console's pad does (a game reads its d-pad);
  the **Analog** action (F, or the gamepad's extra button) switches it to analog mode, and a game that wants analog mode
  switches it itself. While a pad is digital, the gamepad's left stick also works as the d-pad. A game the core's database knows
  as digital-only gets a standard pad on that port (Crash Bandicoot). A multi-disc game has a **Change disc** action (N), which opens the lid, swaps the disc and closes it.
- **F3** opens the graphics page: internal resolution (1x, 2x, 4x, 8x), dithering, deinterlacing, aspect ratio and overscan
  crop. They change only the picture; the conversion's checks use the defaults (1x, the core's own settings, progressive).
- **A raised internal resolution has a real cost**: the renderer works in software on one thread. In combat in Tobal No. 1 on
  a Ryzen 9 3900X (informal, a busy PC), 2x holds the console's speed and 4x does not (about 18 % too slow, the sound breaks
  up). The game says so with a notice when a raised resolution stays behind; 1x and 2x are the settings to try first.
- **Interlaced pictures** (480 lines, Tobal No. 1's) are shown **progressive** by default: the GPU draws both fields of the
  displayed frame, so the picture is whole, without combing (the console itself draws one field per frame there; its drawing
  time is kept). Weave and Bob, on the graphics page, show the console's fields instead.
- **The gaps of CD-audio tracks** are given back to their tracks when a CUE sheet lists only each audio track's INDEX 01 while the
  image keeps its gap before it as digital silence (from one second, at most two): the core then sees the track boundary where
  the disc has it. A game that seeks to a track's start, known in whole seconds, can land in that gap; without it, it lands in the
  track before and the auto-pause stops the sound at once. Tobal No. 1 did this for ever and its fights had no music. The player's
  files are not changed, only the sheet the game holds, and the disc keeps its identity.
- **Rows a wrapping display reads and the game cannot draw are shown black.** A game can place its display so that it runs past
  the end of VRAM and wraps. Tobal No. 1 in combat starts at row 493 and draws in rows 12 to 463, so the top of its picture shows
  VRAM rows 510 and 511, whatever is stored there. The console sends them too, in the top overscan; a screen that shows every line
  shows coloured noise. Such a row keeps its place and is black, only when the display wraps, the row comes before the wrap and
  it lies outside the game's drawing area, in a 16-bit picture. Nothing is cropped and the machine is untouched: this changes the
  picture only, so hardware fidelity does not cover it. A picture loaded there rather than drawn, without a polygon, would be hidden
  too; none is known.
- **Frame pacing** follows the console: 59.826 frames a second with a progressive picture, 59.94 with an interlaced one (PAL
  49.761 and 50), so its 44,100 Hz sound reaches the device at the rate it is played.
- A disc is recognised by what it holds (an ISO 9660 volume of system `PLAYSTATION` and its boot executable named by `SYSTEM.CNF`),
  never by its extension: `.bin`, `.img` and `.iso` are shared with other machines. The image files that a sheet names are part
  of that sheet's disc and are not converted on their own.

## 2. How

- **The machine** is Beetle PSX (libretro, derived from Mednafen), pinned at one revision and driven frame by frame inside the
  game, with its software renderer. It is GPL-2.0: the game executable is GPL-2.0 as a whole, carries the licence text and a
  source offer, and holds no code under noncommercial terms. Beetle's own EBOOT reader, its dynamic recompiler and its hardware
  renderers are not compiled in.
- **The BIOS** is the player's own, identified by its hash (a file or a folder in the options; the image of the disc's region is
  chosen) and embedded in the game. Without one, the game runs on OpenBIOS (PCSX-Redux, MIT), and the report says "free BIOS"
  under hardware fidelity. No BIOS is downloaded or supplied, and none is reimplemented by high-level emulation.
- **The disc** is appended to the game executable and read in place, as the adventure games are packed.
- **Native code**: the conversion first plays its routes on an observing build of the machine (the interpreter alone, recording
  each instruction word it runs in main RAM or the BIOS). Each run of consecutive instructions becomes a native step: C code in
  which each instruction is the core's own handler with its word fixed, so it is decoded once, at conversion time. The core's
  timing stays the core's: before each instruction a step does what the interpreter's loop does (the event check, the fetch
  through the instruction cache with its cycles, the load-delay tick). Its guard is the word the CPU really fetched: when it is
  not the word the step was made for (code loaded later from the disc, an overlay, self-modifying code) or an interrupt is
  pending, the interpreter runs that instruction, counted. A step is entered at any address of its run and leaves at a taken
  branch or a timing event. Code the routes never ran stays interpreted, counted.

## 3. What a conversion checks, and what it does not claim

A conversion plays its routes headless twice: on the observing build (the interpreter alone: the reference) and on the
executable that is published (the disc inside it, its native steps): an attract route without input and a play route (Start and
Cross through the title screens, then a deterministic walk), plus long routes at the higher scan levels. It requires a picture
that changes and, on every frame of every route, the same picture, sound and RAM in both processes; it checks F8/F9 in a fresh
process and the refusal of a damaged state. It also checks the controls of the published game: each one, pressed alone on
each player's pad, must reach exactly its own button of the console, and no pad may be in analog mode at power-on.
The game is published as built (not compressed: the disc follows the program).

Native code: the share of the routes' instructions run by native steps, and the interpreted remainder, are in the report per
route; outside the routes the game shows its own counter. The fetches that run no instruction (an interrupt being taken, or
the CPU held while a DMA transfer runs, when the core fetches the same instruction again each cycle) are counted apart, in
neither figure. CPU fidelity: what the core's interpreter does (each route's native steps are compared with it). Separately,
`tools/psx_vector_selftest.py` runs independent vectors on both paths, without a game: see below. Hardware fidelity: not measured;
with the free BIOS the report says so. Gameplay validation: only the conversion's routes. Physical latency: not measured.

## 4. Where it stands (8 November 2026)

Each line is one measure; none says anything about the others. The record is in
[QUALIFICATION.md](QUALIFICATION.md#sony-playstation-evidence-behind-its-column-8-november-2026).

- **Native code**: on the two routes of the ten panel discs, at most 0.0003 % to 0.0131 % of the instructions ran on the
  interpreter, depending on the disc (0.0165 % on Tobal No. 1, an eleventh disc). This covers those routes only: a part of the
  game they did not reach starts on the interpreter, counted.
- **CPU fidelity**: every route of every panel disc is identical, frame by frame, to the core's interpreter. Independently of any
  game, 55,000 R3000A vectors pass on the interpreter and on the native steps, and 1,150 GTE vectors pass on the GTE. The CPU
  vectors come from ares's model, not from a console, and hold no COP0 or GTE instruction: this is agreement with a model, not
  proof against the silicon.
- **Hardware fidelity**: not measured. It is Beetle's.
- **Gameplay validation**: scripted routes reaching title screens, intros, menus or a first level, no deeper. Nobody has played
  the panel. Ape Escape's play route stops at a dark screen after its "DUALSHOCK required" notice: its gameplay is not shown.
- **Physical latency**: not measured.
- **Linux**: Ape Escape, converted on a Debian 13 PC with GCC, gives the same hashes as Windows on both routes. One disc, and no
  game played on Linux.

## 5. Not in this first scope

Mouse, multitap, light guns, the hardware renderers, LibCrypt and other sub-channel protections, CHD images, the PSP-derived BIOS.
