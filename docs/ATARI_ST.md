# Atari ST

Experimental profile (`atarist`), added in 1.7.1: the converter offers it when the installation carries the Atari ST files, and it
is not shared through the compilation library. It converts an Atari ST, STF or Mega ST floppy game into a standalone Windows
or Linux executable that runs the game on [Hatari](https://github.com/hatari/hatari), with native code for the 68000 instructions its
reference runs observed and Hatari's interpreter, counted, for the others. Nothing here says that a game plays completely, that the hardware is reproduced
faithfully or how long input takes to reach the screen: those are separate measures, listed below with what is known of each.

**What "native" means here.** The game runs on a complete emulator core inside the executable, Hatari, with its machine, its chips and their timing. Only the 68000 instructions that
the conversion saw running become native code, Hatari's own instruction handlers compiled again per opcode and chained: it is not a standalone translation of the game. The video,
the sound, the disk controller and the other chips stay Hatari's own code. So the native share below measures how much CPU code avoids the core's interpreter; it cannot be compared
with the figures of a machine whose game code is translated, and it says nothing about hardware fidelity. See [ARCHITECTURE.md](ARCHITECTURE.md#machines-that-run-on-an-emulator-core).

## 1. What is converted, and what is not

| Converted (experimental) | Not yet |
| --- | --- |
| Atari ST, STF and Mega ST (68000 at 8 MHz) floppy games: one disk image of IPF, STX, MSA or ST format, or a ZIP holding only such images (up to 8, played in the order of their names: `x (Disk 1).ipf`, `x (Disk 2).ipf`) | STE, TT and Falcon games; hard-disk images and GEMDOS folders |
| EmuTOS 1.4 (free, GPL), the default: fetched once from the EmuTOS project with its source (`retrorecomp/atarist_emutos.py`); or the player's own TOS 1.00, 1.02 or 1.04 (192 KiB), chosen in Options > Atari ST as a file or a folder of images and recognised by content (`retrorecomp/atarist_tos.py`) | TOS 1.6 and later (STE and beyond); EmuTOS in another language than English (UK) |
| The joystick (the keyboard's arrows and keys, or a gamepad), the mouse and the keyboard; quick states (F8/F9) | A played-through game |
| A disk whose boot stops at the GEM desktop: the desktop starts its only program (section 2) | A disk with several programs to choose from; TOS 1.00 and 1.02 (no autostart line) |
| Windows; Linux (converted and validated headless on a Debian 13 PC, see below) | A game played on Linux |

A ZIP that holds anything other than floppy images is not claimed by the Atari ST profile. The input is read in place and never
changed. The player supplies the disks (and his TOS if he wants it); Retro-Recomp publishes no game, no disk and no firmware.

## 2. How the conversion works

1. **Reading the input.** `retrorecomp/atarist.py` reads the image or the ZIP (members sorted by name for the disk order) and takes the
   SHA-256 of the file as the identity of the game. `retrorecomp/atarist_tos.py` recognises the player's TOS by its header (never
   by its name) and takes its SHA-256 as the identity of the firmware. Without one, `retrorecomp/atarist_emutos.py` takes EmuTOS
   1.4: the first conversion fetches its two release files (`emutos-192k-1.4.zip` and the source `emutos-src-1.4.tar.gz`) from
   the EmuTOS project on SourceForge into the converter's dependency folder; their size and SHA-256 are pinned and checked on
   every use. The machine boots the United Kingdom image (PAL, English). An EmuTOS image is never taken for the player's TOS.
2. **The machine.** The games run on Hatari (the cycle-exact WinUAE 68000, the Shifter, GLUE and MMU video, the YM2149, the MFP,
   the IKBD, the WD1772 and the DMA), pinned at one revision (`atarist_hatari.HATARI_REV`) and adapted at build time by
   `retrorecomp/atarist_hatari.py`: each replacement must find its pinned text exactly once, so an upstream change fails loudly.
   Its libretro frontend is driven frame by frame inside the game (`native/atarist_machine/`). The TOS and the disks are served from
   memory through a libretro virtual file system, so no file of the player is written to a work folder for the machine to read.
3. **Validation.** A conversion starts with a fresh interpreted reference run of the game. The game executable is then copied alone
   and replayed headless on the same bounded scripts (a main route of joystick, mouse and keyboard inputs and, at the Standard level,
   a second exploration route, 3,000 frames each with TOS 1.04 and 3,600 with EmuTOS; the extended and thorough levels add one and two
   pseudo-random routes of 18,000 frames): the picture, sound, RAM and CPU registers of every frame must equal the
   reference's. So must the compressed copy that is delivered. A quick state saved by the game is loaded by a fresh process, whose
   continuation is compared with the unbroken run and reported. A conversion that fails a check keeps the earlier export.
4. **A boot that stops at the desktop.** Some disks do not start by themselves: the boot reaches the GEM desktop and the player
   opens the program. When the root of disk 1 holds exactly one program to open (a `.PRG`, `.APP`, `.GTP` or `.TOS` file that is
   not hidden and is not a hard-disk installer, whose names start with `INSTAL`) and there is no `AUTO` folder,
   `retrorecomp/atarist_disk.py` names it and the desktop starts it by the TOS's own autostart line (`#Z`), in a desktop file
   Hatari serves in memory (its `inffile.c`; TOS 1.04 and EmuTOS have that line, TOS 1.00 and 1.02 do not). The disk image is
   not changed, and the program starts once GEM is up, as after a double click. The autostart is kept only when the main
   reference run shows that the boot reached the desktop (the TOS opened that file); otherwise the references run again without
   it, so a disk that starts by itself runs as before (Carrier Command, whose disk also holds one `.TOS` utility, gives the same
   counts with and without the feature). While the autostart is kept, Hatari's GEMDOS hook stays installed (its cartridge
   code), and its traps are counted as interpreted. The report says what was decided and why (`desktop_autostart`).
   Why this route: an `AUTO` folder cannot be added to an IPF disk without changing its flux and runs before GEM is up (a GEM
   program cannot start from it), and a mouse route depends on each TOS's desktop layout.
5. **Report.** The conversion report (schema v2, shape `atarist_conversion`) carries the interpreter fallback per CPU, in
   instructions, and keeps the five measures in separate objects.
6. **Native code.** The reference run records the 68000 instructions it runs from RAM, the TOS ROM and the cartridge area (their
   address and their own bytes). A *form* is the very handler Hatari's cycle-exact table would call for an opcode, its generated
   text compiled again with the opcode as a literal, on one shared copy of Hatari's bus path without its pointers (`retrorecomp/atarist_codegen.py`,
   from the opcode table the reference player writes and Hatari's generated `cpustbl.c` and `cpuemu_13.c`): Hatari's code specialised, not a
   translation, so the prefetch, the cycles and the bus waits of the ST stay Hatari's. An *instruction* (one per address and opcode observed)
   runs its form and goes straight on to the instruction it knows comes next, without the 68000 loop, when the CPU is there and nothing is due
   between the two (an event whose clock has passed, an MFP update, a special flag, an interrupt level above the mask); otherwise it returns to the loop, whose work then sees
   what it would have seen. The guard is the opcode the CPU has latched: a form reads its extension words on the bus, so it is right for its opcode at any address and with any
   extension words, and a word rewritten in memory needs no tracking (`tools/atarist_prefetch_check.py`). An opcode Hatari's table treats as illegal is never native. The 68000
   decoder of m68k-recomp-core tells the length and the target of an observed instruction, during the conversion only. A pass that still meets interpreted instructions adds them and builds again. An observation keeps each instruction's
   own words by the decoder's length table (`--opcode-lengths`): Hatari's table gives the length of its handlers' fetches, which
   is shorter for some instructions (JMP (d8,PC,Xn)), and an instruction observed without its extension word cannot be decoded.

## 3. The five measures

| Measure | What is known today |
| --- | --- |
| Native code | The panel of ten games, converted once each on Windows with TOS 1.04 (6 November 2026) and with EmuTOS 1.4 (7 November 2026), Standard level (Bomb Jack at Quick), main route of 3,000 frames (the exploration route is within a few instructions of it): see the tables below. On the tested routes only. |
| CPU fidelity | The native code is Hatari's own handlers, specialised per opcode (section 2): on the ten games the trace of every frame (picture, sound, RAM, CPU registers) of the native game and of its compressed copy is identical to the interpreted reference's, on every route. This shows that the steps equal the core, not that the core equals a 68000; the independent corpus is the vectors. Hatari's cycle-exact 68000 replayed on the SingleStepTests 68000 fixtures (`tools/atarist_vector_selftest.py`): 6,764 vectors. On a flat 24-bit bus 6,762 run and the state agrees on 6,760 (the two others are divisions by zero whose N/Z flags the 68000 leaves undefined); on the ST's memory map 3,593 run and all agree. Clocks on the flat bus: 4,363 equal, 1,857 the ST's 4-cycle rounding, 14 CHK vectors 4 clocks more, 528 neither explained nor refuted (a fixture without a list of bus transactions). The native form was compared on 6,107 vectors of the flat bus and 3,569 of the ST's map, those whose opcode has a form, and equals the interpreter on all of them; with `--all-forms`, each of the 45,814 forms of every opcode but RESET equals the table's handler on eight random states (366,512 runs: registers, flags, clocks in each position of the bus slot, interrupt level changing during the instruction, prefetch, RAM, and 834,101 bus accesses in order and clock). These checks found that a compiler reads a literal differently: ADDX.L D6,D6 gave wrong flags until the forms were compiled with wrapping arithmetic. The fixtures leave out odd-address and bus errors, TAS, TRAPV and interrupt acknowledge. The vectors are MAME-made, not silicon. |
| Hardware fidelity | Not claimed for the machine. Named behaviours measured from inside it with authored 68000 programs against the documentation, not against silicon (`tools/atarist_hardware_check.py`, 37 measurements, 36 agree): the PAL frame and line, the MFP's prescalers and timer B's event count, a 320x200 picture pixel by pixel, the YM2149's tone periods, the IKBD's packets and byte time, the WD1772's index period, step rates and DMA reads. One recorded difference: the YM2149 runs on the PAL crystal's division (2.005312 MHz), 0.27 % above the round 2 MHz its data sheet gives as a maximum. The 263 lines at 60 Hz rest on the GLUE's vertical counter as MAME and the gstmcu replica model it; several numbers rest on Hatari and MAME, as the check's `SOURCES` say (the WD1772 data sheet, the Atari Compendium and the ST's schematics were not reached). MAME 0.289, flagged not working on the ST, agrees on the video and MFP lines it can run. |
| Gameplay validation | None. |
| Physical latency | Not measured. |

With TOS 1.04 (United Kingdom):

| Game (disks) | Native | Interpreted | Own screen reached by the route |
| --- | ---: | ---: | --- |
| Bomb Jack (1) | 32,910,533 | 1 | yes (title, credits) |
| Another World (2) | 33,425,253 | 1 | yes (code-wheel protection) |
| Operation Stealth (3) | 30,004,899 | 269,820 | no on 6 November: the GEM desktop (the interpreted ones are TOS line-F calls); the desktop now starts it (section 2) |
| Captain Blood (2) | 29,886,965 | 264,772 | no on 6 November: the GEM desktop; since the desktop starts `BLOOD.PRG` (7 November, Quick): 33,095,811 native, 2,330 interpreted, its title |
| Elite (1) | 39,364,470 | 3 | yes (manual-word protection) |
| Lethal Xcess (2) | 34,895,160 | 0 | yes (music device menu) |
| Turrican II (1) | 39,532,761 | 2,139 | yes (title, credits) |
| Carrier Command (1) | 38,039,056 | 0 | yes (language menu) |
| Kick Off 2 (1) | 39,538,414 | 2 | no on 6 November: "Master file not present or damaged" (fixed on 8 November, see below) |
| Indiana Jones and the Temple of Doom (1) | 40,182,497 | 2 | yes (title, high scores) |

With EmuTOS 1.4 (United Kingdom), the default, and the joystick reaching the machine (7 November 2026, the delivered conversions:
Standard level, main route of 3,600 frames; Turrican II with the player's TOS 1.04):

| Game (disks) | Native | Interpreted | What the route's last picture shows |
| --- | ---: | ---: | --- |
| Bomb Jack (1) | 36,110,480 | 5 | the game, started by the joystick's fire |
| Another World (2) | 54,602,986 | 5 | "ERROR": the route's random code-wheel entry is wrong (the protection) |
| Operation Stealth (3) | 59,908,753 | 1,065 | colour-code protection; started from the desktop (`DELPHINE.PRG`; the installer is not a program to open); the interpreted ones are Hatari's GEMDOS traps |
| Captain Blood (2) | 38,780,981 | 75 | its title (asks for disk 2); started from the desktop (`BLOOD.PRG`) |
| Elite (1) | 50,657,290 | 4 | manual-word protection |
| Lethal Xcess (2) | 47,421,455 | 4 | its credits, past the music menu |
| Turrican II (1), TOS 1.04 | 47,864,686 | 0 | a level of the game; on EmuTOS it stops after its intro: EmuTOS's own `doc/incompatible.txt` names Turrican among the games that use low memory EmuTOS also uses ("this can never work with EmuTOS") |
| Carrier Command (1) | 50,975,919 | 4 | language menu |
| Indiana Jones and the Temple of Doom (1) | 53,278,013 | 6 | the game |
| Kick Off 2 (1) | 56,306,524 | 1,781 | a practice match (its protection passes: section 3) |

Every route of these conversions equals its fresh interpreted reference, the compressed copy too. A state saved on the main route
continues in a fresh process on all ten, on every column, sound samples included (section 5). Kick Off 2 was added on 8 November 2026
(delivered conversion, Standard level, EmuTOS).

"Own screen" means the route's last picture is the game's, not that the game was played.

At the thorough level (9 November 2026, one tree, every game: main and exploration routes of 3,000 frames, two pseudo-random routes of 18,000, Turrican II with the player's TOS 1.04, the others on EmuTOS). All 40 routes equal their
fresh interpreted reference and the compressed copy; a state continues on every game:

| Game | Native, the two long routes | Interpreted, the two long routes | What the long routes' last pictures show |
| --- | ---: | ---: | --- |
| Bomb Jack | 136,907,471 / 138,237,061 | 5 / 5 | the game |
| Another World | 234,379,563 / 235,274,078 | 5 / 5 | "ERROR": the random entry at the code wheel is wrong |
| Operation Stealth | 285,910,180 / 285,061,396 | 5,030 / 5,068 | colour-code protection |
| Captain Blood | 167,058,885 / 211,761,208 | 291 / 197 | its title (asks for disk 2) / the cockpit, on the route that changes disk |
| Elite | 234,159,606 / 234,193,136 | 4 / 4 | manual-word protection |
| Lethal Xcess | 210,834,689 / 216,231,471 | 4 / 4 | asks for disk B / a level, on the route that changes disk |
| Turrican II | 188,091,921 / 189,277,948 | 0 / 0 | a level |
| Carrier Command | 330,586,259 / 291,892,045 | 4 / 4 | black, after its language menu, with few program counters and no sound: a stop not explained |
| Indiana Jones and the Temple of Doom | 265,364,451 / 266,378,956 | 6 / 6 | the game |
| Kick Off 2 | 246,147,304 / 242,438,886 | 1,781 / 1,781 | a practice match |

IPF reading. Hatari's built-in IPF reader is checked against an independent reader of the same files (a development tool, not shipped) and
against the SPS decoder library (capsimg, built privately for this comparison only, never in an export, never in the repository). Two defects
of the reader were found this way on Kick Off 2's protected tracks (cylinders 2 to 6 of side 0: a 1024-byte sector written across the index, a
second 1024-byte sector whose data mark is one cell out of phase, a 2 ms area without flux), and fixed in `retrorecomp/atarist_hatari.py`:
a phantom flux transition at the index, and the write splice. The reader draws a track's write splice as three inverted cells at the end of the last
block's gap; on a track whose last block has no gap those are the first cells of the track, here the first A1 mark of sector 1's ID, which then has two
marks where the WD1772 needs three: an ordinary read answers "record not found" and the game stops on its own error. The splice is now drawn only
where its cells lie in gaps. Every ordinary track keeps it where it was (the other panel games skip none, and Bomb Jack's controller trace is
byte for byte the same). Kick Off 2 now reaches its menus, its protection passes through the WD1772 model, and the first 981 controller commands
equal those of the same disk as plain sectors. With the fix the flux and the sector CRCs agree with capsimg's rendering.

## 4. Controls

Player 1 plays the ST's joystick port (the port games read by default): the arrows, W for the fire button (Button A) and X for
Button B (an ST joystick has one button, so B does nothing in most games), Enter for Start; or a gamepad (the first one
plugged is player 1). Player 2 plays the other port, the one the mouse uses (a two-player game reads it): the second keys
of the options, or a second gamepad. F1 is the help, F2 the options, F8 and F9 save and load a quick state, F11 pauses.
Ctrl+Alt+K gives the whole keyboard to the Atari (to type a protection's word); Ctrl+Alt+M or a middle click lets the mouse go;
Ctrl+Alt+Page Up and Page Down change the disk in drive A.

Until 7 November 2026 the joystick did not reach the games: Hatari's libretro frontend reads the ST's joystick port from its
port 0 and the mouse port from its port 1 (its `joy_ui.c` swaps them), and the session handed the first player's joystick to
the other one, where it was disabled; the validation routes' joystick events went the same way, so the routes of 6 and 7
November exercised the keyboard and the mouse only. Fixed in `atarist_session.c`; the routes now play the joystick too.
The check that found and proves it runs the converted game itself: with `RETRORECOMP_ST_TEST_SCRIPT` and
`RETRORECOMP_ST_TEST_LOG` set (nothing runs and nothing is written without both), the player feeds real SDL input to the
windowed game on an invisible desktop (`SDL_VIDEODRIVER=dummy`): keys through SDL's keyboard state, a virtual SDL game
controller for the pad, pictures captured on the way. On Bomb Jack, before the fix the title never left the screen, with the
pad or with the keys; after it, fire starts the game and the stick moves Jack, with the pad and with the keys alike (the same
picture and RAM hashes at every step). The same check on the delivered, compressed executables (7 November, after the
reconversion): Bomb Jack with the pad and with the keys, the same hashes as the development build; Lethal Xcess, whose intro
waits for the stick (a run with no input stays on it for 800 frames, a run with a virtual pad leaves it at the first press and
reaches its music menu). The second player's stick is enabled but not proven in a game yet.

Owner play trial, 7 November 2026: the maintainer tried the nine reconverted games with the controls and reported that the
gamepad control works (the first try, before the fix, found that it did not). It is a trial of the controls only, not a
gameplay validation of any game, and it changes no gate.

## 5. Known limits

- STE, TT, Falcon, hard disks and CD-style media are out of scope.
- **EmuTOS is not Atari's TOS** (known limit). Some games written for Atari's TOS do not run on it; EmuTOS's own
  `doc/incompatible.txt` lists the known ones. Turrican II is one of them on the panel: it uses low memory that EmuTOS also uses
  ("this can never work with EmuTOS"), and it stops after its Rainbow Arts intro. **The player's own TOS is needed for such a
  game.** Every conversion on EmuTOS says so in its messages and in its report (`tos_note`): no signal tells a game that EmuTOS
  cannot run from a game waiting on a still screen, so the sentence is the same for every game. The private memory of a game is
  kept per TOS.
- The first conversion without a TOS of the player's needs the network once, for EmuTOS (3.5 MB).
- Linux: the ten panel games were converted and validated on a Debian 13 PC (9 November 2026, system GCC, Standard level, the tree of the Windows panel above): the same counts as Windows, the
  traces of all 20 routes (CPU registers, RAM, picture and sound of every frame) byte for byte those of Windows, the compressed copy and the state continuation too. No game was played interactively on Linux (window, sound, pad).
- Quick states: saving one leaves the running machine unchanged (checked on every conversion: the delivered copy saves a state on its main route and its
  trace still equals the reference), and a fresh process that loads it continues the unbroken run on every column, sound samples included (compared by every
  conversion over 400 frames, reported, not refused). Three mechanisms were found for this on 8 November 2026 by comparing a state of the running machine with a
  state of the loaded one, stored block by stored block: Hatari's restore ejects and reinserts the floppies after the controller came back, which restarted the
  drive's rotation and its loaded track (a later read met the disk elsewhere: Bomb Jack saved during a load, Turrican II before its next load); the filters' memory
  and the mixing buffer were not in a state; the restore's reset sent its silent mixing buffer to the speakers. A damaged state, or one of another build, is refused
  before the machine is touched, a missing one creates nothing (`tools/atarist_saves_check.py`).
- Saves: what a game writes to its disks (any image format; on IPF Hatari itself refused every write with "record not found") is kept beside the quick state, in
  `datas/games/atarist-<game>/disk-writes.bin`, and survives without F8/F9; the image is never changed. A file that is not valid is kept aside as
  `disk-writes.bin.unusable-N` and the game starts from its disks. A state brings the disks back as they were when it was saved. Not kept: a track the game formats
  (WD1772 Write Track on an IPF answers an error, as before), and a Read Track shows the original track, not the written sectors. A game that asks for a separate blank
  save disk has none to use yet.
  One real game was seen saving (`tools/atarist_saves_game.py`, 9 November 2026, TOS 1.04 and EmuTOS, Windows and Linux): The Lurking Horror writes 27 sectors by GEMDOS, and a new process with the file restores to the
  room of the save, where one without it answers "Failed."; no game of the panel was seen saving.
- The first conversion needs the pinned Hatari sources (fetched into the workspace) and the C toolchain of the converter.
- The profile is hidden unless the installation carries the Atari ST converter's files (`retrorecomp/atarist.py`,
  `converter_available`).

## 6. Licences

- Retro-Recomp's Atari ST files (the converter modules, `native/atarist_machine/`, the host-kit adapter) are MIT.
- Hatari is **GPL-2.0-or-later**; three headers of its WinUAE CPU core say version 2 only, so **an exported Atari ST game is
  distributed under the GPL, version 2**, with Hatari at the pinned revision and the build-time changes of
  `retrorecomp/atarist_hatari.py` as its corresponding source. Its IPF reader (`src/floppies/ipf_dsk.c`) is BSD-3-Clause; the
  capsimg library is never built or linked. Notice: [licenses/hatari.md](../licenses/hatari.md).
- The disks and the player's TOS embedded in an export are the player's own; the GPL does not make them redistributable and
  Retro-Recomp distributes none.
- EmuTOS is **GPL-2.0-or-later**. A game that boots it embeds the image and the release's complete source archive, which the game
  writes into a folder on request (`Game.exe --write-sources FOLDER`). Retro-Recomp's repository and installer hold no EmuTOS
  file. Notice: [licenses/emutos.md](../licenses/emutos.md).
- The 68000 decoder of m68k-recomp-core (PolyForm Noncommercial) runs during the conversion only, to tell the length and the
  target of an observed instruction; since 1.7.3 none of its text enters a game.
- Upstream pins and review: [UPSTREAMS.md](UPSTREAMS.md).

## 7. Where it stands in the qualification

The Atari ST column of [QUALIFICATION.md](QUALIFICATION.md) is `P` on the gates with evidence above and `?` elsewhere. Leaving the experimental status is the maintainer's
own decision, after a very high evidence bar.
