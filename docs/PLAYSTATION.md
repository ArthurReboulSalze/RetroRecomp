# Sony PlayStation (experimental, in development)

The PlayStation profile is **experimental** and only present in developer installations: it is being built. A conversion
makes a playable game whose R3000A code, as far as the conversion saw it run, is **native steps**; the rest runs on the machine's
interpreter and is counted and reported. This page says what it converts, how, and what it does not claim. The five measures
stay separate: native code, CPU fidelity, hardware fidelity, gameplay validation and physical latency.

## 1. What is converted

- **Discs as the player gives them**, read in place and never changed: a PS1 Classics EBOOT (`.pbp`, one to five discs), a CUE
  sheet with its BIN files (one file for the disc or one per track), a CloneCD image (`.ccd` + `.img` + `.sub`), a bare raw image
  (`.bin`, `.img`) or an ISO (`.iso`, 2,048-byte sectors: such a dump holds the file system only, so a game's XA sound and CD audio
  are missing from it, and the report says so). A multi-disc game is one EBOOT holding its discs (playlists, `.m3u`, are not read
  yet: that extension is the X68000's disk sets). A signed EBOOT from the PlayStation Store is refused (decrypting it would
  circumvent its protection).
- **NTSC-U, NTSC-J and PAL discs**, two players, digital and analog pads, memory cards.
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
process and the refusal of a damaged state. The game is published as built (not compressed: the disc follows the program).

Native code: the share of the routes' instructions run by native steps, and the interpreted remainder, are in the report per
route; outside the routes the game shows its own counter. CPU fidelity: what the core's interpreter does (the native steps are
compared with it, not with an independent CPU model). Hardware fidelity: not measured; with the free BIOS the report says so. Gameplay
validation: only the conversion's routes. Physical latency: not measured.

## 4. Not in this first scope

Mouse, multitap, light guns, the hardware renderers, LibCrypt and other sub-channel protections, CHD images, the PSP-derived BIOS.
