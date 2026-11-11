# Commodore Amiga

Experimental profile (`amiga`), opened in 1.7.0: the converter offers it when the installation carries the Amiga files, and
it is not shared through the compilation library yet. It converts an Amiga 500 game installed for WHDLoad into a standalone Windows
executable, with guarded native code for the 68000 code the game runs from RAM and a counted interpreter for everything else.
Nothing here says that a game plays completely, that the hardware is reproduced faithfully or how long input takes to reach the
screen: those are separate measures, listed below with what is known of each.

**What "native" means here.** The game runs on a complete emulator core inside the executable, vAmiga, with its machine, its chips and their timing and its 68000, Moira. Only the
68000 instructions that the conversion saw running (the player's Kickstart included) become native code, per opcode behind a guard: translated C for the forms the translator
knows (about 99 % of what four games execute), Moira's code specialised for the others, the two counted apart. The translation stops at the CPU: its bus functions, and the machine behind them, stay vAmiga's. The custom chips, the CIAs and the floppy drive stay vAmiga's own code; the Blitter's copy blits of the shapes a conversion saw run vAmiga's own microprogram compiled for that shape (specialised routines, not a translated program, with their own counters). So the native share below measures how much CPU code avoids the
core's interpreter; it cannot be compared with the figures of a machine whose game code is translated, and it says nothing about hardware fidelity. See [ARCHITECTURE.md](ARCHITECTURE.md#machines-that-run-on-an-emulator-core).

## 1. What is converted, and what is not

| Converted (experimental) | Not yet |
| --- | --- |
| Amiga 500 (68000, OCS/ECS) games installed for WHDLoad: one `.lha` archive holding exactly one `.Slave` and the game's files or `Disk.N` images | Installs that need a 512 KiB Kickstart (3.x, 12 of the library's installs without a 68020/AGA flag); the installs that also need resload calls the layer lacks stop with the call's number |
| Installs that need a Kickstart 1.3 (in the slave header or through `resload_LoadKick`), with the player's own image chosen in Options (section 2a). First milestone: about 230 of the library's installs ask for Kickstart 1.x and no resload service the layer lacked (1,280 ask for 1.3 in all); `resload_Examine`, `ExNext` and `ListFiles` are answered too: none of the Kickstart installs converted through the converter calls them (the five of section 3 and the 1.7.1 checks); tested on authored data only | Kickstart 1.2 installs (17; the same path, not run yet) |
| The joystick (port 2, two buttons), the mouse (port 1, captured on a click) and the keyboard; quick states (F8/F9) and the files an install saves | ADF disk images, IPF, hard-disk images, Amiga 1200 (68020, AGA), CD32, CDTV |
| Windows; Linux (`linux = 'witnessed'`): two conversions checked on a Debian 13 PC with the system GCC (9 November 2026, routes of 3,000 frames; Rick Dangerous: 0 interpreted; Civilization, with the player's Kickstart: 19, all the Kickstart's; both validated on both routes, compressed copy and quick state included, every frame compared equal to the Windows run of the same inputs), not played there | A panel on Linux: two installs were run there, none played |
| | A library of qualified paths: the profile is not in the sharing |

A `.lha` that holds no slave is refused with a sentence. With several slaves (25 archives of the maintainer's library), the one named as
the install's folder is the game and its intro, editor or helper slaves stay aside (`other_slaves` in the report; 17 of the 25); an archive
where no single slave is named so, a collection such as Dizzy Collection or Time Runners Series (8 of the 25), is refused, never guessed. The archive is read in place and never
changed. An install that asks for a Kickstart uses the player's own image (section 2a); Retro-Recomp supplies none, fetches none
and shares none. The player supplies the install; Retro-Recomp publishes no game, no disk and no firmware.

## 2. How the conversion works

1. **Reading the install.** `retrorecomp/amiga_lha.py` lists and extracts the members of the archive (LHA levels 0 to 2, methods
   `-lh0-` and `-lh5-` to `-lh7-`, CRC-16 checked); `retrorecomp/amiga_whdload.py` reads the slave's AmigaDOS hunk file and its
   `ws_` header (memory sizes, flags, the Kickstart it asks for) and lays out the install: the slave, its data folder, the disk
   images. The data folder is the one the icon's `DATA` ToolType names when the archive has it (1.7.2), else the one `ws_CurrentDir` names (Drakkhen's slave names none,
   its icon says `DATA=data`). The identity of a game is the SHA-256 of the archive.
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
   code is native too (1.7.1): the library's private memory of that image keeps only the *addresses* of the instructions run (never a
   byte; `converter-kickstart-addresses.txt`). Since 1.7.2 the run's own observation of it (`<observations>.kick`) also keeps the words as
   they stood, a slave's patches included, but only in the conversion's private work folder beside the image, never in the library; the
   steps are written from those words and from the player's own image, in memory, so the generated source and the game built from it
   belong to that player's image alone. What still runs on the interpreter (an instruction not reached in the observed runs, or one a
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
   executing from RAM. Each opcode seen becomes a form: written out as C by the translator (`retrorecomp/amiga_translate.py`), calling the machine's bus functions in the
   order and at the cycles of Moira's handler, or, for a form it does not know, the very template Moira dispatches the opcode to, compiled for that opcode alone (Moira's
   code specialised, not a translation). Chip-RAM contention stays exact either way. Each instruction seen runs its form and goes straight on to the instruction it knows comes next, when the CPU is
   there with that opcode latched and nothing is pending for a run loop. A form reads its extension words on the bus, so it is right
   for its opcode at any address, and the guard is the latched opcode alone: unpacked, patched or self-modified code that changes an
   opcode goes back to the counted interpreter, and any other rewritten word needs no tracking (`retrorecomp/amiga_codegen.py`). Beyond what ran, a sweep over the memory each
   route left adds what branches lead to and the rest of the 4 KiB pages where code ran, with the same guard; a swept instruction counts apart when it runs
   (`final_checks.native_swept`), and no route proves those that did not run. Code that is not in memory when a route ends, not loaded yet or already overwritten, cannot be swept.
   The Blitter's copy blits have a specialised routine per shape (BLTCON0 and BLTCON1 without the shift fields; at most 64 per game, the most words first): vAmiga's microprogram at its accuracy level 2,
   compiled for that shape from vAmiga's own text at build time (`amiga_vamiga.blitter_shape_header`), one step per bus slot, in the slots the reference uses, reading shifts, pointers, masks and modulos live. It is not a
   translated program: nothing is known of what a game blits, only how. A routine checks its shape at every slot, and a game that changes BLTCON during a blit goes on in vAmiga's table. Line blits and other
   shapes stay in vAmiga's microprogram. Each shape has its own native and interpreted counters (`final_checks[].blitter`), with words for a copy blit and steps for a line blit.
   The Copper is not compiled: its lists hold values that change from frame to frame (colour gradients, scroll offsets, page pointers; a guard on the whole list held 7 to 20 % of the time on the
   games that do this, measured over 72 s of eight games), and it takes at most 0.5 % of a frame, so a compiled list would be vAmiga's fetch and write with a guard in front. It stays vAmiga's unless new evidence changes one of those two figures.
5. **Validation.** The game executable is copied alone and replayed headless on the same bounded scripts (a main route of joystick,
   mouse and keyboard inputs, and at the Standard level a joystick exploration route, 3,000 frames each, and at the Extended level one long varied route of 18,000 frames seeded from the install): the picture, sound, RAM
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
| Native code | Measured with the 1.7.2 tree (8 November 2026; main and exploration routes of 3,600 frames; native entries, then instructions left on the counted interpreter): Rick Dangerous 36.1 M and 36.5 M, 0 and 0; Civilization (Kickstart) 4.42 M and 4.35 M, 19 and 19; California Games (Kickstart) 45.8 M and 46.1 M, 48 and 49; Twylyte (Kickstart) 49.0 M and 43.1 M, 10,638 and 10,601 (0.022 % and 0.025 %). Every interpreted instruction of the three Kickstart installs is the Kickstart's, counted apart (`kickstart_interpreted`). **Not measured again since 1.7.0:** the ten-install panel (6 November 2026: 0 interpreted on every route of 3,000 frames, 44.8 to 76.0 million native entries per game over two routes) and the five Kickstart 1.3 installs (main route, native entries / Kickstart instructions interpreted: Black Tiger 31.1 M / 2.34 M, Flying Shark 23.7 M / 1.58 M, North & South (NTSC) 13.1 M / 3.42 M, Dungeon Master 19.7 M / 7.67 M, Hostages 23.7 M / 5.32 M); the Kickstart counts there were taken before 1.7.2 stopped a slave's patched words from missing their guard. |
| Native code, the player's own record | Pinball Dreams (the NTSC archive) at the quick level on Windows (9 November 2026), played by script, headless, with the recorder on, then reconverted beside its game: on Ignition the same script went from 13.4 million interpreted instructions to 0 (10.9 million `native_learned`, 2.4 million `native_walked`). With all four tables recorded (18,000 frames each, 1,337 records of 4,096, none dropped), the same scripts ran 0 interpreted on all four. Steel Wheel and Beat Box equal their fresh reference on all 18,000 frames, Ignition on 7,000 (picture, sound, RAM, CPU registers). In a hidden window, a normal exit writes the file; with F12 off it writes none. On a Debian 13 PC (same day, headless, the PAL archive): the same path on Ignition went from 16.9 million interpreted instructions to 0 (14.3 million `native_learned`, 2.6 million `native_walked`, 560 records, none dropped) and equals its fresh reference on all 7,000 frames; the reconverted game was validated on both Standard routes, compressed copy and quick state included. Rick Dangerous interpreted nothing over 18,000 frames there, so it recorded nothing. No window was run on Linux and no frame was compared across the two systems for this path. Scripted keys, not a person's play; one game on each system |
| Native code, panel | 15 installs at the extended level, 9 November 2026 ([QUALIFICATION.md](QUALIFICATION.md#commodore-amiga-the-panel-9-november-2026)): 14 converted, 3.48 billion native instructions, 420 interpreted, all the Kickstart's; 337.8 million Blitter copy words in specialised routines, none in vAmiga's microprogram. Only what the routes ran is measured: three of Pinball Dreams' four tables run partly on the interpreter (16 % to 52 % of the 3,000 frames after the table is picked), counted and shown |
| Native code, Blitter | Measured with the 1.7.2 tree (9 November 2026; two routes of 3,600 frames): every copy word of the routes ran in a specialised routine on Rick Dangerous (1 shape), Apidya (4), Lemmings (3) and Civilization (12), and none changed shape on the way; Civilization's line blits, 32 and 16, stay in vAmiga's microprogram. These counts are of the shapes the same routes taught: a shape new to a player's game runs on vAmiga, counted. The Blitter is 0.1 to 3.6 % of a frame (private profile, a loaded PC), so this is not where the machine spends its time. |
| CPU fidelity | `tools/amiga_vector_selftest.py`: every translated opcode (40,586) against Moira's handler on random states, 0 differ. Moira (MIT) was compared with the SingleStepTests 68000 vectors; its deviations from them are recorded in 15 families (private engine-gate notes). On Rick Dangerous the trace of every frame (picture, sound, RAM, CPU registers) and the resload log of the native game are identical to the interpreted reference machine's, on both routes. |
| Hardware fidelity | Not claimed. `tools/amiga_blitter_selftest.py` shows the Blitter's routines equal vAmiga's microprogram (1,023 shapes, 8,184 random blits, 970,162 bus slots, 0 differ), not the chip. `tools/amiga_display_selftest.py` (10 November 2026, for the Agnus and Denise fast paths to come) runs authored scenarios (a display set up and hammered by a 68000 program, no ROM image) and records every instruction and every frame: the records replay the same (12 scenarios, 427,604 instructions), an injected fault is seen and placed, and the build with Denise's line work by table (step 1, [UPGRADES.md](UPGRADES.md)) gives the same records as the build before it on 40 more scenarios (1,301,275 instructions); with a line's bitplane slots taken in a batch (step 2), each scenario gives the same records batched and with every line on vAmiga's events (12 scenarios, 420,350 instructions, 9,755 lines batched), and the same as the build of step 0 on 40 more (1,297,343 instructions); with a quiet line's pass in one loop (step 3) added, the same again on both sets (50,072 visible lines in one pass). This is equality with vAmiga's own paths, not with the chips. As a development check, the same installs were run privately in an independent emulator with the real WHDLoad and its pictures compared with ours on 59 reference frames each: Lotus 2 matched 59/59, Lemmings 58/59, Speedball 2 54/59, Elite 51/59, Turrican 2 49/59. Pinball Dreams (NTSC) first scored 19/59; looked for at any offset at the Amiga's 4-bit colour depth, all 59 of its pictures are in the other emulator's stream (the two tools crop some display windows differently). These are counts of equal pictures on a few frames, not a fidelity claim. |
| Gameplay validation | One owner play trial: the ten panel installs, converted with the tree at `977cf63e` and delivered in `Export`, were played on 6 November 2026 and worked, in his words ([QUALIFICATION.md](QUALIFICATION.md#owner-acceptance)). A trial, not a coverage claim: no game was checked end to end, and it is not a decision to leave the experimental status. |
| Physical latency | Not measured. |

## 4. Known limits

- Of the 2,967 Amiga 500 installs of the maintainer's library that the profile can read, 1,180 carry the `Examine` flag
  (their slave answers the game's file requests through its own operating-system emulation, which asks the resload layer
  for each file's information) and 1,040 of those also ask for a Kickstart. Until 1.7.1 they stopped at boot with a
  memory error (see UPGRADES); the fix is checked headless on eight of them, and through the converter on the ones listed
  in section 3. The other Examine installs are not checked.
- Kickstart 3.x installs, ADF, Amiga 1200, CD32 and CDTV are out of scope; Linux is witnessed, not played (section 1). With a Kickstart, the operating system loads through the
  resload layer at no emulated cost: loading is faster than on the real machine (a hardware-fidelity limit, not claimed
  otherwise).
- The first conversion needs the pinned vAmiga sources (fetched into the workspace) and the C++ toolchain of the converter.
- The slave is entered in the CPU state WHDLoad 20.1 gives it (supervisor, interrupt mask 0, marked registers), read once in a
  private run of the real WHDLoad; installs that depend on other WHDLoad behaviour stop with the reason in the report.
  CIA-B is left as the system leaves it (read on the real WHDLoad: DDRA `$C0`, DDRB `$FF`, no drive selected, motor off): the disk
  lines are outputs, so a read of `$BFD100` gives back what the game wrote there. A slave that reads the side-select bit to know which
  side of a disk the game asked for (Blood Money's does: 26 slaves of the library name `$BFD100`) otherwise reads the idle pin (1) and
  loads the wrong tracks.
- (1.7.2) The player's own record keeps at most 4,096 records per game, the shared limit. Each is one window of 16 bytes at an interpreted instruction, read when the instruction runs, so the instructions a walk finds are as they stood at that moment; each native instruction keeps its guard on the opcode. Past the limit the newest are kept and the file counts the others. Pinball Dreams used 1,337 and Lotus 2 used 5, none dropped. A game with much more unseen code could reach it (about 3 instructions per window on Pinball Dreams, so about 12,000 unseen instructions would fill it); not measured on such a game. Memory images are not taken at each load, and the Kickstart is not recorded.
- (1.7.2) A key changing sets the keyboard's bit in CIA-A's interrupt mask (`CIAICRF_SP`), unless the slave has `WHDLF_NoKbd`. WHDLoad's autodoc says it sets that bit on each
  interrupt when it uses the VBR, and that before 19.0 AmigaOS's mask stayed active; a game that takes the machine over may install a level 2 handler and never enable the
  bit itself. Pinball Dreams does: until this change no key reached it, on the reference machine either, so F1 to F4 could not pick a table and no conversion had seen a table run. The bit is
  written when a key changes because that is the only moment it can matter: a route without a key sees no difference. Exports made before this keep the old behaviour until they are reconverted.
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
  the machine runs vAmiga's most precise mode (its default 2, which vAmiga calls cycle-exact; not checked here against hardware). A faster CPU changes the course of the game, so that run
  cannot be compared and nothing is claimed from it. Whether a real Amiga 500 shows it as strongly is not measured here (hardware
  fidelity is not claimed).
- The chipset's collision detection (CLXCON/CLXDAT: sprite-sprite, sprite-playfield, playfield-playfield) is on since 1.7.1; vAmiga ships
  it off for speed (`DENISE_CLX_SPR_SPR`, `DENISE_CLX_SPR_PLF`, `DENISE_CLX_PLF_PLF`), which would have hidden every collision from a game
  that reads CLXDAT. Apidya reads it never (0 reads in 1,700 frames); Blood Money does (36 reads over the 2,500 frames of the standard
  route, and its RAM then differs from frame 859 of that route with the detection on).
- (1.7.2) The files an install saves go to `datas/games/amiga-<identity>/saves`, below that folder only, whole or not at all (a temporary file replaces the old
  one once every byte is flushed and closed; a refusal is reported to the slave as a full disk and leaves the file and the game's view of it as they were).
  Shown on one game, 5th Gear (`tools/amiga_saves_check.py`, 8 November 2026): it writes `5thgear.highs` by itself on the exploration route, a relaunch keeps it, a fresh
  process reads it (through a one-byte-changed copy: the game saved what its install already holds), a quick state does not roll it back, a damaged file never stops the
  game, and a refused save is reported as DOS error 221 (a slave that sets NoError then stops there, as WHDLoad does). A really full disk, a new high score and other games are not checked.
- (1.7.2) The library's memory of an install (earlier observations, Kickstart addresses) only helps: one that cannot be read, or is past the bound of an observation,
  is ignored, and a conversion that fails after merging it is tried once more without it (`remembered_data` in the report). Shown with an oversized valid file on Rick Dangerous (quick level): ignored, the conversion finished and replaced it; the retry itself is tested with a fake conversion.
- The profile is hidden unless the installation carries the Amiga converter's files (`retrorecomp/amiga.py`, `converter_available`).

## 5. Licences

- Retro-Recomp's Amiga files (the converter modules, `native/amiga_whdload/`, `native/amiga_machine/`, the host-kit adapter) are MIT.
- vAmiga's `Core/` is **MPL-2.0** per file; our changes to those files, applied at build time, are MPL-2.0 too. Moira, the CPU
  inside it, is **MIT**. The vAmiga application (GPL-3.0 or later) is not used. Notice: [licenses/vamiga.md](../licenses/vamiga.md).
- Nothing of the PolyForm Noncommercial engines (segagenesisrecomp, m68k-recomp-core) is used since 1.7.2: the instructions' lengths come from Moira's
  disassembler. So an exported Amiga game is MIT and MPL-2.0; no GPL code joins it
  (searched on 8 November 2026 in the adapted Core, the Amiga's native files and the notices of SDL and xBR: no GPL notice).
- Each exported game carries its notices as resource 203, like the other machines: Retro-Recomp's licence, vAmiga and Moira, SDL and the
  host kit's parts
  (`amiga_conversion.NOTICE_FILES`).
- WHDLoad is freeware with all rights reserved and is not distributed or run. The JST resload emulation (MIT) was read as a
  reference only; none of its decrunchers is copied.
- Upstream pins and review: [UPSTREAMS.md](UPSTREAMS.md).

## 6. Where it stands in the qualification

The Amiga column of [QUALIFICATION.md](QUALIFICATION.md#commodore-amiga-evidence-behind-its-column-8-november-2026) reads, on 8 November 2026: `Y` on G1; `P` on G2 to G8, G10, G11, G13, G14
and G15; `-` on G16 (the Amiga shares no paths); `?` on G9 and G12. Each `P` names what is shown and what is missing there; none of them says hardware fidelity, gameplay
coverage or latency. Leaving the experimental status is the maintainer's own decision, after a very high evidence bar.
