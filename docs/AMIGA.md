# Commodore Amiga

Experimental profile (`amiga`), opened in 1.7.0: the converter offers it when the installation carries the Amiga files, and
it is not shared through the compilation library yet. It converts an Amiga 500 game installed for WHDLoad into a standalone Windows
executable, with guarded native code for the 68000 code the game runs from RAM and a counted interpreter for everything else.
Nothing here says that a game plays completely, that the hardware is reproduced faithfully or how long input takes to reach the
screen: those are separate measures, listed below with what is known of each.

## 1. What is converted, and what is not

| Converted (experimental) | Not yet |
| --- | --- |
| Amiga 500 (68000, OCS/ECS) games installed for WHDLoad: one `.lha` archive holding exactly one `.Slave` and the game's files or `Disk.N` images | Installs that need a 512 KiB Kickstart (3.x, 12 of the library's installs without a 68020/AGA flag); the installs that also need resload calls the layer lacks stop with the call's number |
| Installs that need a Kickstart 1.3 (in the slave header or through `resload_LoadKick`), with the player's own image chosen in Options (section 2a). First milestone: about 230 of the library's installs ask for Kickstart 1.x and no resload service the layer lacked (1,280 ask for 1.3 in all); `resload_Examine`, `ExNext` and `ListFiles` are answered too, tested on authored data only: none of the five Kickstart installs converted so far calls them | Kickstart 1.2 installs (17; the same path, not run yet) |
| The joystick (port 2, two buttons), the mouse (port 1, captured on a click) and the keyboard; quick states (F8/F9) and the files an install saves | ADF disk images, IPF, hard-disk images, Amiga 1200 (68020, AGA), CD32, CDTV |
| Windows; Linux (`linux = 'witnessed'`): one conversion checked on a Debian 13 PC with the system GCC (Rick Dangerous, tree `fd953b8c`, 6 November 2026: validated on both routes, compressed copy and quick state included, 0 interpreted), not played there | Kickstart installs on Linux: none was run there (the same machine path; not witnessed) |
| | A library of qualified paths: the profile is not in the sharing |

A `.lha` that holds no slave, or more than one, is refused with a sentence, never guessed. The archive is read in place and never
changed. An install that asks for a Kickstart uses the player's own image (section 2a); Retro-Recomp supplies none, fetches none
and shares none. The player supplies the install; Retro-Recomp publishes no game, no disk and no firmware.

## 2. How the conversion works

1. **Reading the install.** `retrorecomp/amiga_lha.py` lists and extracts the members of the archive (LHA levels 0 to 2, methods
   `-lh0-` and `-lh5-` to `-lh7-`, CRC-16 checked); `retrorecomp/amiga_whdload.py` reads the slave's AmigaDOS hunk file and its
   `ws_` header (memory sizes, flags, the Kickstart it asks for) and lays out the install: the slave, its data folder, the disk
   images. The identity of a game is the SHA-256 of the archive.
2. **No WHDLoad, no Kickstart.** WHDLoad is closed source with all rights reserved; it is neither run nor copied. The slave is a
   68000 program that calls a table of `resload_*` services, so `native/amiga_whdload/` answers those calls itself (our own MIT
   code, written from the public autodoc; every call is counted and a service it does not provide is refused with its number,
   never answered with a pretended success). The machine boots through an authored boot ROM that enters the slave in supervisor
   mode; an install that needs no Kickstart runs no code from Commodore's firmware.
2a. **The player's Kickstart** (decisions of 6 November 2026). Options > Commodore Amiga takes one file or a folder of images
   and a Check button; images are recognised by content (`retrorecomp/amiga_kickstart.py`: plain, doubled, byte-swapped, and
   Cloanto Amiga Forever files with their `rom.key`, decoded in memory), by size and CRC-32 for the version, size and CRC-16
   for a slave's request, SHA-256 as identity. A v16+ slave that names a Kickstart in its header gets it at the start of ExpMem
   before it starts, as WHDLoad does; an older one gets it from `resload_LoadKick`. WHDLoad relocates the image with hand-made
   `.RTB` tables, which we neither make nor ship: the image keeps the addresses it was built for, and vAmiga's own writable-ROM
   mechanism (the A1000's WOM, left unlocked) is pointed at the copy, so the ROM window `$FC0000-$FFFFFF` and ExpMem are one set
   of bytes, read and written by both addresses (the slaves write into the image through its ROM addresses). The Kickstart's
   code is native too (1.7.1): an observation of it keeps only the *addresses* of the instructions run (never a byte; the private
   memory of that image keeps them in `converter-kickstart-addresses.txt`), and the conversion reads the words of each from the
   player's own image, in memory, when it writes the guarded steps, so the generated source and the game built from it belong to
   that player's image alone. What still runs on the interpreter (an instruction not reached in the observed runs, or one a
   slave patched) is counted apart in the report (`kickstart_interpreted` and `kickstart_native` per route). The image is copied only into the
   conversion's private work folder and into the player's own export (resource 298), never into the repository, the library
   or a shared record; the report names it by numbers only. 256 KiB images (1.x) only for now.
   **Memory beyond the slow RAM** (1.7.1): an ExpMem too large for the 1.5 MiB of slow RAM at `$C00000` goes to a fast RAM board
   at `$200000` (up to 8 MiB; the slave area stays at `$C00000`), and the Kickstart copy and its ROM window follow it there; a
   BaseMem above 1 MiB gets 2 MiB of chip RAM. CUSTOM1 to 5 come from the install's icon.
3. **The machine.** The games run on the Amiga machine of [vAmiga](https://github.com/dirkwhoffmann/vAmiga) (Agnus, Denise, Paula,
   the CIAs, the floppy drive), pinned at one revision and adapted at build time by `retrorecomp/amiga_vamiga.py`, which drives it
   frame by frame inside the game. Its 68000 core, Moira, is the reference CPU of the Amiga profile.
4. **Native code.** A conversion first runs the install on the interpreted machine and records the 68000 instructions seen
   executing from RAM. Each one becomes a native step, grouped by form, that calls the very instruction template Moira dispatches
   the opcode to, so the bus accesses and their cycles (chip-RAM contention included) stay Moira's. Every step starts with a live
   comparison of the instruction's words in RAM: a word that changed (unpacked, patched or self-modified code) sends execution
   back to the counted interpreter. The generator is the one the X68000 uses (`retrorecomp/m68k_observed.py`); the Amiga declares
   its own bodies (`retrorecomp/amiga_codegen.py`).
5. **Validation.** The game executable is copied alone and replayed headless on the same bounded scripts (a main route of joystick,
   mouse and keyboard inputs, and at the Standard level a joystick exploration route, 3,000 frames each): the picture, sound, RAM
   and CPU registers of every frame and the resload calls must equal those of the fresh interpreted reference. So must the
   compressed copy that is delivered. A quick state saved by it is loaded by a fresh process, which must continue the same
   timeline (CPU, RAM, picture and the sound samples of every frame; vAmiga's snapshot leaves out the state of its sound path, so
   the adapted core saves and restores the samplers' pending samples, the filters' memory and the volume ramps itself). A conversion that fails any of these keeps the earlier export.
6. **Report.** The conversion report (schema v2, shape `amiga_conversion`) carries the interpreter fallback per CPU and keeps the
   five measures in separate objects.
7. **Picture.** The game shows the display window the game opens, not the overscan border around it: the union of its
   DIWSTRT/DIWSTOP over the reference routes (vAmiga's viewport tracking, read only) is built into the executable (`display` in the
   report), and a window the game opens later beyond it widens what is shown; nothing inside the window is cut. Without any, the
   standard window is shown (320 x 256 PAL, 320 x 200 NTSC). In the window and the first fullscreen mode the picture grows in whole
   steps of one lores pixel per line (320 x 256 PAL: 2x at 640 x 512, 3x at 960 x 768), as the other machines do; the second
   fullscreen mode fills the screen with the 4:3 aspect. The window opens at 3x.

## 3. The five measures

| Measure | What is known today |
| --- | --- |
| Native code | The ten-install panel (6 November 2026): 0 interpreted instructions on every route of 3,000 frames, 44.8 to 76.0 million native entries per game over two routes. The five Kickstart 1.3 installs (6 November 2026): the game's own code native, every interpreted instruction the Kickstart's (counted apart, `kickstart_interpreted`): main route, native entries / Kickstart instructions interpreted: Black Tiger 31.1 M / 2.34 M, Flying Shark 23.7 M / 1.58 M, North & South (NTSC) 13.1 M / 3.42 M, Dungeon Master 19.7 M / 7.67 M, Hostages 23.7 M / 5.32 M. |
| CPU fidelity | The steps call Moira's own templates. Moira (MIT) was compared with the SingleStepTests 68000 vectors; its deviations from them are recorded in 15 families (private engine-gate notes). On Rick Dangerous the trace of every frame (picture, sound, RAM, CPU registers) and the resload log of the native game are identical to the interpreted reference machine's, on both routes. |
| Hardware fidelity | Not claimed. As a development check, the same installs were run privately in an independent emulator with the real WHDLoad and its pictures compared with ours on 59 reference frames each: Lotus 2 matched 59/59, Lemmings 58/59, Speedball 2 54/59, Elite 51/59, Turrican 2 49/59. Pinball Dreams (NTSC) first scored 19/59; looked for at any offset at the Amiga's 4-bit colour depth, all 59 of its pictures are in the other emulator's stream (the two tools crop some display windows differently). These are counts of equal pictures on a few frames, not a fidelity claim. |
| Gameplay validation | One owner play trial: the ten panel installs, converted with the tree at `977cf63e` and delivered in `Export`, were played on 6 November 2026 and worked, in his words ([QUALIFICATION.md](QUALIFICATION.md#owner-acceptance)). A trial, not a coverage claim: no game was checked end to end, and it is not a decision to leave the experimental status. |
| Physical latency | Not measured. |

## 4. Known limits

- Of the 2,967 Amiga 500 installs of the maintainer's library that the profile can read, 1,180 carry the `Examine` flag
  (their slave answers the game's file requests through its own operating-system emulation, which asks the resload layer
  for each file's information) and 1,040 of those also ask for a Kickstart. Until 1.7.1 they stopped at boot with a
  memory error (see UPGRADES); the fix is checked headless on eight of them, and through the converter on the ones listed
  in section 3. The other Examine installs are not checked.
- Kickstart 3.x installs, ADF, Amiga 1200, CD32 and CDTV are out of scope; Linux is pending (one conversion checked, none
  played: section 1; no Kickstart install was converted on Linux). With a Kickstart, the operating system loads through the
  resload layer at no emulated cost: loading is faster than on the real machine (a hardware-fidelity limit, not claimed
  otherwise).
- The first conversion needs the pinned vAmiga sources (fetched into the workspace) and the C++ toolchain of the converter.
- The slave is entered in the CPU state WHDLoad 20.1 gives it (supervisor, interrupt mask 0, marked registers), read once in a
  private run of the real WHDLoad; installs that depend on other WHDLoad behaviour stop with the reason in the report.
  CIA-B is left as the system leaves it (read on the real WHDLoad: DDRA `$C0`, DDRB `$FF`, no drive selected, motor off): the disk
  lines are outputs, so a read of `$BFD100` gives back what the game wrote there. A slave that reads the side-select bit to know which
  side of a disk the game asked for (Blood Money's does: 26 slaves of the library name `$BFD100`) otherwise reads the idle pin (1) and
  loads the wrong tracks.
- (1.7.1) After a quick state is loaded, the sound samples are bit-identical to an unbroken run on the games checked (Apidya, Zeewolf, Cyber Games, 200 frames each); a state saved by an earlier build is refused.
- (1.7.1) Apidya's bee flickers, and is whole, cut to a thin strip or missing from frame to frame: the game draws it with the
  blitter while the screen is being scanned. Compared with Copperline running the real WHDLoad (private, comparison only; the same
  Apidya, the same joystick play): the scroll cadence (1 lores pixel every second frame) and the screen wipes agree frame for frame,
  0.1 to 0.8 % of the playfield pixels differ (small moving objects), and the bee flickers on both with the same character, its pattern
  differing from frame to frame as it depends on the exact timing. So it is the game's behaviour on this hardware model, not a defect of
  the native steps (the interpreted run shows it too), of the display crop (nothing is drawn outside the shown window) or of the layer.
  Does it depend on the machine's memory or timing settings? Same joystick play, 181 frames, each frame's picture compared with the
  baseline's: **identical** with 512 KiB of slow RAM instead of our 1.5 MiB (the original configuration: chip 512 KiB plus 512 KiB slow;
  Apidya has no ExpMem, so the fast RAM at `$200000` is not in play), with the slow-RAM delay off, with an OCS Agnus (8371) instead of
  the ECS one, and with the collision detection on. Only the blitter's two less accurate modes change it (181 and 103 of 181 frames);
  the machine runs the most accurate one (cycle-exact, vAmiga's default 2). A faster CPU changes the course of the game, so that run
  cannot be compared and nothing is claimed from it. Whether a real Amiga 500 shows it as strongly is not measured here (hardware
  fidelity is not claimed).
- The chipset's collision detection (CLXCON/CLXDAT: sprite-sprite, sprite-playfield, playfield-playfield) is on since 1.7.1; vAmiga ships
  it off for speed (`DENISE_CLX_SPR_SPR`, `DENISE_CLX_SPR_PLF`, `DENISE_CLX_PLF_PLF`), which would have hidden every collision from a game
  that reads CLXDAT. Apidya reads it never (0 reads in 1,700 frames); Blood Money does (36 reads over the 2,500 frames of the standard
  route, and its RAM then differs from frame 859 of that route with the detection on).
- The profile is hidden unless the installation carries the Amiga converter's files (`retrorecomp/amiga.py`, `converter_available`).

## 5. Licences

- Retro-Recomp's Amiga files (the converter modules, `native/amiga_whdload/`, `native/amiga_machine/`, the host-kit adapter) are MIT.
- vAmiga's `Core/` is **MPL-2.0** per file; our changes to those files, applied at build time, are MPL-2.0 too. Moira, the CPU
  inside it, is **MIT**. The vAmiga application (GPL-3.0 or later) is not used. Notice: [licenses/vamiga.md](../licenses/vamiga.md).
- Each exported game carries its notices as resource 203, like the other machines: Retro-Recomp's licence, vAmiga and Moira, the
  68000 decoder of m68k-recomp-core (compiled into the index of native steps), SDL and the host kit's parts
  (`amiga_conversion.NOTICE_FILES`).
- WHDLoad is freeware with all rights reserved and is not distributed or run. The JST resload emulation (MIT) was read as a
  reference only; none of its decrunchers is copied.
- Upstream pins and review: [UPSTREAMS.md](UPSTREAMS.md).

## 6. Where it stands in the qualification

The Amiga column of [QUALIFICATION.md](QUALIFICATION.md) is mostly `?`: only the rows above are measured. Leaving the
experimental status is the maintainer's own decision, after a very high evidence bar.
