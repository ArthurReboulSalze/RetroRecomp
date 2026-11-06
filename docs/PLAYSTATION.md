# Sony PlayStation (experimental, in development)

The PlayStation profile is **experimental** and only present in developer installations: it is being built and converts
no game yet. This page says what it will convert, how, and what it does not claim. The five measures stay separate: native
code, CPU fidelity, hardware fidelity, gameplay validation and physical latency.

## 1. What is converted

- **Discs as the player gives them**, read in place and never changed: a PS1 Classics EBOOT (`.pbp`, one to five discs), a CUE
  sheet with its BIN files (one file for the disc or one per track), a CloneCD image (`.ccd` + `.img` + `.sub`), a bare raw image
  (`.bin`, `.img`) or an ISO (`.iso`, 2,048-byte sectors: such a dump holds the file system only, so a game's XA sound and CD audio
  are missing from it, and the report says so). A playlist (`.m3u`) lists the discs of a multi-disc game. A signed EBOOT from the
  PlayStation Store is refused (decrypting it would circumvent its protection).
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
- **Native code**: the R3000A instructions a conversion sees running become guarded native steps that call the core's own
  instruction code, so the core's timing stays the core's; anything else runs on the core's interpreter and is counted.

## 3. What is not claimed

Nothing yet: no game converts. When the profile converts, a passed conversion will mean that the native run equals a fresh
interpreted run of the same machine on the conversion's routes. That is not hardware fidelity, not complete gameplay and not
physical latency.

## 4. Not in this first scope

Mouse, multitap, light guns, the hardware renderers, LibCrypt and other sub-channel protections, CHD images, the PSP-derived BIOS.
