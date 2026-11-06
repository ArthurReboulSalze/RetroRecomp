# Sony PlayStation (experimental, in development)

The PlayStation profile is **experimental** and only present in developer installations: it is being built. A conversion
already makes a playable game, but **every R3000A instruction still runs on the machine's interpreter** (counted and reported):
the native code comes with the next stage. This page says what it converts, how, and what it does not claim. The five measures
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
- **Native code** (the next stage, not in this build): the R3000A instructions a conversion sees running will become guarded native steps that call the core's own
  instruction code, so the core's timing stays the core's; anything else will run on the core's interpreter, counted.

## 3. What a conversion checks, and what it does not claim

A conversion plays its routes headless on the executable that is published (the disc inside it): an attract route without
input and a play route (Start and Cross through the title screens, then a deterministic walk), plus long routes at the higher
scan levels. It requires a picture that changes, plays the play route a second time in a fresh process and requires the same
picture, sound and RAM on every frame, and checks F8/F9 in a fresh process and the refusal of a damaged state. The game is
published as built (not compressed: the disc follows the program).

Native code: none yet (0 %; every instruction is interpreted and counted). CPU fidelity: what the core's interpreter does, not
checked against an independent CPU model yet. Hardware fidelity: not measured; with the free BIOS the report says so. Gameplay
validation: only the conversion's routes. Physical latency: not measured.

## 4. Not in this first scope

Mouse, multitap, light guns, the hardware renderers, LibCrypt and other sub-channel protections, CHD images, the PSP-derived BIOS.
