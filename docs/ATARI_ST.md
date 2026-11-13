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
| Atari ST, STF and Mega ST (68000 at 8 MHz) floppy games: one disk image of IPF, STX, MSA or ST format, or a ZIP holding only such images (up to 8, in the order their names mean: a boot or unlabelled disk first, then `x (Disk 1).ipf`, `x (Disk 2).ipf`, `Disk A`, `Side B`, `Reel 2`, `Volume II`; section 2) | STE, TT and Falcon games; hard-disk images and GEMDOS folders |
| EmuTOS 1.4 (free, GPL), the default: fetched once from the EmuTOS project with its source (`retrorecomp/atarist_emutos.py`); or the player's own TOS 1.00, 1.02 or 1.04 (192 KiB), chosen in Options > Atari ST as a file or a folder of images and recognised by content (`retrorecomp/atarist_tos.py`) | TOS 1.6 and later (STE and beyond); EmuTOS in another language than English (UK) |
| The joystick (the keyboard's arrows and keys, or a gamepad), the mouse and the keyboard; quick states (F8/F9) | A played-through game |
| A disk whose boot stops at the GEM desktop: the desktop starts its only program, or the one program a clear rule picks among several (section 2) | A disk with several programs and no clear rule, or none at its root: the player opens one at the desktop; TOS 1.00 and 1.02 (no autostart line) |
| Windows; Linux (converted and validated headless on a Debian 13 PC, see below) | A game played on Linux |

A ZIP that holds anything other than floppy images is not claimed by the Atari ST profile. The input is read in place and never
changed. The player supplies the disks (and his TOS if he wants it); Retro-Recomp publishes no game, no disk and no firmware.

## 2. How the conversion works

1. **Reading the input.** `retrorecomp/atarist.py` reads the image or the ZIP (members put in disk order by `atarist_disk.disk_order_key`: the unlabelled and boot disks (Boot, StartUp, Program, Main, Loader) first, then the numbered ones by number or letter, so that Disk 10 follows Disk 9, then the disks that only have a name; a name without brackets is read from its end, `game2.st`, `game_b.st`) and takes the
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
   code), and its traps are counted as interpreted. The report says what was decided and why (`desktop_autostart`: the program, the
   candidates of the root, the rule and the reason).
   **Several programs.** Only where a clear rule picks one; rule 2 is a guess by name, and the player can still open another program from the desktop. Rule 1 (`title-word`): exactly one program whose name,
   letters and digits only, is a word of the game's title (at least four letters, no Roman numeral, no article): `CRICKET.PRG` for
   Championship Cricket, `OUTCAST_.PRG` for Outcast. Rule 2 (`only-non-utility`): else exactly one program that is not a utility, by a
   short list of names (setup, config, format, read, view, help, manual, unpack, depack, backup, copy, util, music, editor, and the installers: exact words, no exception for one game). Two
   programs that fit rule 1, or none of the two rules, leave the choice to the player: nothing is started, and the report says so. A
   lone program is started whatever its name, as before.
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
7. **The player's own record** (since 1.7.3). An exported game notes what its 68000 runs on the interpreter while the player plays: a window of 16 bytes at such an
   instruction, from RAM or the TOS ROM, with the TOS it ran on (feedback kind 24, `native/runtime_feedback.c`; F12 turns it off, at most 4,096 windows per game, kept in
   `datas/fallbacks` beside the game, private, never shared). The next conversion of that game reads it, keeps the windows of the same TOS whose ROM bytes still match,
   and walks each into instructions (`retrorecomp/m68k_record_walk.py`, shared with the Amiga): the first ran there ("learned"), the others a walk through the window finds
   ("walked", which may never have run). They become native code with the same guard, counted apart (`player_record` and `final_checks.native_learned`/`native_walked` in the
   report). The routes prove the game as before; they cannot prove these instructions, since what a route runs is observed and counts as observed.
8. **The sweep beyond the routes** (since 1.7.3). Code a game loads or unpacks after the conversion's routes end is not in any observation. At its end each fresh reference run
   leaves an image of the RAM at its last frame (`--ram-dump-at`, read by the conversion and deleted: the game's bytes are never kept), and the sweep walks it, with the TOS ROM, from
   the instructions the routes ran (`retrorecomp/m68k_record_walk.py`, shared; the Atari ST's `atarist_codegen.sweep`): from an observed instruction that the image still holds as it
   was observed (a stale one starts nothing) it follows branches, DBcc, JSR and JMP with an absolute or PC-relative address, and what falls through, up to an opcode Hatari's table sends to
   its exception handlers, an address outside the machine's apertures, or the cap of 60,000 instructions added (a capped sweep says so in the report and in a message). What it reaches
   becomes native code with the same guard as the others, counted apart (`sweep` in the report, `final_checks.native_swept`): it was only reached from observed code, so no route proves it,
   and on the routes the count is 0 by construction. A block that the game rewrites before it jumps in is the guard's case: another opcode there and the routine never runs (the interpreter does),
   the same opcode with another extension word runs the routine, which reads the new word on the bus (`tools/atarist_sweep_guard_check.py`, three variants on an authored program, native and
   interpreted traces byte-identical). A page fill (every even address of a page where code ran) is written and tested but left off: it costs more than it gives.

## 3. The five measures

| Measure | What is known today |
| --- | --- |
| Native code | The panel of ten games, converted once each on Windows with TOS 1.04 (6 November 2026) and with EmuTOS 1.4 (7 November 2026), Standard level (Bomb Jack at Quick), main route of 3,000 frames (the exploration route is within a few instructions of it): see the tables below; the panel of eight games of 13 November 2026 (extended level, interpreted instructions listed by address) follows them. On the tested routes only. |
| CPU fidelity | The native code is Hatari's own handlers, specialised per opcode (section 2): on the ten games the trace of every frame (picture, sound, RAM, CPU registers) of the native game and of its compressed copy is identical to the interpreted reference's, on every route. This shows that the steps equal the core, not that the core equals a 68000; the independent corpus is the vectors. Hatari's cycle-exact 68000 replayed on the SingleStepTests 68000 fixtures (`tools/atarist_vector_selftest.py`): 6,764 vectors. On a flat 24-bit bus 6,762 run and the state agrees on 6,760 (the two others are divisions by zero whose N/Z flags the 68000 leaves undefined); on the ST's memory map 3,593 run and all agree. Clocks on the flat bus: 4,363 equal, 1,857 the ST's 4-cycle rounding, 14 CHK vectors 4 clocks more, 528 neither explained nor refuted (a fixture without a list of bus transactions). The native form was compared on 6,107 vectors of the flat bus and 3,569 of the ST's map, those whose opcode has a form, and equals the interpreter on all of them; with `--all-forms`, each of the 45,814 forms of every opcode but RESET equals the table's handler on eight random states (366,512 runs: registers, flags, clocks in each position of the bus slot, interrupt level changing during the instruction, prefetch, RAM, and 834,101 bus accesses in order and clock). These checks found that a compiler reads a literal differently: ADDX.L D6,D6 gave wrong flags until the forms were compiled with wrapping arithmetic. The fixtures leave out odd-address and bus errors, TAS, TRAPV and interrupt acknowledge. The vectors are MAME-made, not silicon. |
| Hardware fidelity | Not claimed for the machine. Named behaviours measured from inside it with authored 68000 programs against the documentation, not against silicon (`tools/atarist_hardware_check.py`, 51 measurements, 49 agree, 2 recorded differences): the PAL frame and line, the MFP's prescalers and timer B's event count, a 320x200 picture pixel by pixel, the YM2149's tone periods, the IKBD's packets and byte time, the WD1772's index period, step rates and DMA reads. Two recorded differences: the YM2149 runs on the PAL crystal's division (2.005312 MHz), 0.27 % above the round 2 MHz its data sheet gives as a maximum; and timer D, started from the TOS's addresses, runs slower with Hatari's patch of it, which is on for a game that shows no sign of relying on the timer as TOS left it and off for one that does (section 5). The 263 lines at 60 Hz rest on the GLUE's vertical counter as MAME and the gstmcu replica model it; several numbers rest on Hatari and MAME, as the check's `SOURCES` say (the WD1772 data sheet, the Atari Compendium and the ST's schematics were not reached). MAME 0.289, flagged not working on the ST, agrees on the video and MFP lines it can run. |
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

**The panel of eight (1.7.4, 13 November 2026).** Eight games chosen for what each one adds, converted one at a time on Windows from an empty scratch library, from one tree (1.7.3 and the changes of 1.7.4), at the extended level
(the main and the exploration routes of 3,000 frames and one pseudo-random route of 18,000), Lethal Xcess at the thorough level (a second route of 18,000 frames that changes the disk once), with EmuTOS 1.4, Turrican II with the player's TOS 1.04.
On all 25 routes the native game and its compressed copy equal the fresh interpreted reference, frame by frame (picture, sound, RAM, CPU registers), and the state saved on the main route continues in a fresh process on 8 of 8; no game was dropped. The interpreted
instructions of a run are listed where they ran (`final_checks[].interpreted_sites`: address, opcode, count) and add up to the run's total on 25 of 25 routes. They are of three kinds: EmuTOS's own start (four to six instructions:
processor probes, line A and line F, the same addresses in every game), Hatari's GEMDOS hook (its cartridge code at $FA002A, installed while the desktop starts a program: a file read through GEMDOS is one of them; 351 to 775,400 on a route) and the game's own line A
opcodes (Kick Off 2 at $012E60), which never become native code, as Hatari's table sends them to its exception handlers. Pictures change on the main route of every game and every game is heard on at least one route. What the routes reach is read from the
last picture of each (the captures were looked at by the specialist agent, not by the owner; pad and key routes, not played games):

| Game (disks) | Why it is on the panel | TOS, timer D | Starts by | Interpreted per route (main / exploration / long) | The routes reach |
| --- | --- | --- | --- | ---: | --- |
| Bomb Jack (1) | EmuTOS, starts by itself, a joystick arcade game: the plain case | EmuTOS, patched | itself | 5 / 5 / 5 | play |
| Another World (2) | two disks, starts by itself, a code-wheel protection | EmuTOS, patched | itself | 5 / 5 / 5 | the code wheel, then ERROR after the route's entry (protection) |
| Operation Stealth (3) | three disks, started by the desktop, Hatari's GEMDOS hook, a colour-code protection | EmuTOS, patched | DELPHINE.PRG | 872 / 857 / 5,026 | the colour-code check (protection) |
| Turrican II (1) | the player's own TOS 1.04, which EmuTOS cannot run | TOS 1.04, patched | itself | 0 / 0 / 0 | a level |
| Kick Off 2 (1) | protected tracks read through the WD1772 model, line A in the game's code | EmuTOS, patched | itself | 545 / 423 / 2,095 | menus, a match |
| Lethal Xcess (2) | timer D chosen `exact` by `auto`, two disks (the disk change of the second long route) | EmuTOS, exact | itself | 4 / 4 / 4 / 4 | its title, then INSERT DISK B; play after the disk change |
| The Lurking Horror (1) | a text game on the keyboard, started by the desktop, saves through GEMDOS | EmuTOS, patched | LURKING.PRG | 99,302 / 99,702 / 775,400 | its text game, typed commands |
| Battle Probe (1) | a disk the converter read wrongly until 1.7.4 (it declares one FAT), started by the desktop | EmuTOS, patched | PROBE.PRG | 351 / 354 / 10,833 | play |

Six of the eight reach play or a match on a route; Another World and Operation Stealth stop on a copy protection whose answer is on a wheel or a card that came with the game: no route answers or skips a protection, and each says so in the report's `route_warnings`.
The same run converted seven more games (Captain Blood, Carrier Command, Championship Cricket, Elite, Indiana Jones and the Temple of Doom, Outcast, The Seven Gates of Jambala), all validated the same way; they are not the panel, no gate rests on them, and
their exports stay in the owner's folder. Of them Carrier Command (a language menu, then its manual-word protection) and Elite (its novella protection) also stop on a protection, and Jambala stays on its title.

At the thorough level, with the timer D patch for every game (9 November 2026, before it was chosen per game, one tree, every game: main and exploration routes of 3,000 frames, two pseudo-random routes of 18,000, Turrican II with the player's TOS 1.04, the others on EmuTOS; a scratch library holding the same tree's Standard pass). All 40 routes equal their
fresh interpreted reference and the compressed copy; a state continues on every game:

| Game | Native, the two long routes | Interpreted, the two long routes | What the long routes' last pictures show |
| --- | ---: | ---: | --- |
| Bomb Jack | 136,890,241 / 138,174,475 | 5 / 5 | the game |
| Another World | 234,420,603 / 235,342,206 | 5 / 5 | "ERROR": the random entry at the code wheel is wrong |
| Operation Stealth | 286,238,048 / 284,651,047 | 5,026 / 5,075 | colour-code protection |
| Captain Blood | 167,032,020 / 211,808,239 | 291 / 197 | its title (asks for disk 2) / the cockpit, on the route that changes disk |
| Elite | 234,129,207 / 234,162,312 | 4 / 4 | manual-word protection |
| Lethal Xcess | 210,827,512 / 216,224,316 | 4 / 4 | asks for disk B / a level, on the route that changes disk |
| Turrican II | 188,091,921 / 189,277,948 | 0 / 0 | a level |
| Carrier Command | 330,585,019 / 291,890,645 | 4 / 4 | black: its manual-word protection after three wrong entries, on TOS 1.04 as well; the game idles, nothing failed |
| Indiana Jones and the Temple of Doom | 264,303,741 / 265,577,441 | 6 / 6 | the game |
| Kick Off 2 | 240,242,407 / 243,229,276 | 2,095 / 1,781 | a practice match |

**Which library these figures come from.** A conversion keeps the instructions it saw in the player's library and starts from them next time, so what is native beyond a route depends on it. The tables of 6 and 7 November and the qualification runs before 9 November had earlier conversions of the same game and TOS in their library (the converter's own working copy, never a player's). The Standard pass of 9 November started from an empty one: on Linux for every game, and with the same counts on Windows. A route's own counts barely depend on it, as a conversion adds what a route misses until none is left.
**Beyond its routes, it decides.** Turrican II converted once at the Standard level from an empty library ran 7 % of its instructions natively in a window of play past its routes (frames 3,800 to 5,200); with the conversions of the days before in its library, 99.99 %. A player's first conversion is the first case: the rest is interpreted, counted, and equal on the routes.
**A player's own record closes it on what was played** (1.7.3, measured on one scripted session each, `RETRO_RECOMP_FEEDBACK=1` on the delivered game): Turrican II's window of play went
from 6.91 % native to 100.00 % at the next conversion (3,912 windows read, 3,669 learned and 2,814 walked instructions; in the window 11,993,335 learned and 668,026 walked executions), and Indiana
Jones from 569 interpreted instructions in its window to 0. Recording changed nothing in the run (traces equal with and without it), and beyond the routes the reconverted game's trace equals the
interpreted run of the same build on 5,400 and 4,700 frames. A session covers what it played, nothing more.
**The sweep reaches code no route ran, with no session needed** (1.7.3, Standard level from an empty library, TOS 1.04 for Turrican II and EmuTOS for Bomb Jack, the delivered game on the play script, 12 November 2026):
Turrican II's window of play (frames 3,800 to 5,200) goes from 6.91 % of its instructions native to 73.00 % (9,928,216 of 13,601,146, of which 8,988,431 swept; the interpreter ran 3,672,930); 26,801 instructions
were swept (10,870 roots of which 2,222 stale, 31,706 reached, not capped), 32,419 native instructions in 2,726 forms against 5,618 in 1,618. Bomb Jack's window (frames 3,000 to 4,500) was already 99.9998 %
native (17 interpreted of 10,353,857) and the sweep takes those 17 (6,550 swept, 17,330 native instructions against 10,780). The native and the interpreted (`--reference-cpu`) traces of every frame are
byte-identical on 5,200 and 4,500 frames, with and without the sweep. The routes' own counts do not change (`native_swept` is 0 on them). The cost is compile time and size: see `docs/UPGRADES.md`. The rest of
Turrican II's window is what a static walk does not reach (calls and jumps through registers and tables, code unpacked later than the routes' end); a player's own record closes it, and a page fill (off), measured once on Turrican II, reaches 91.48 % (59,190 swept instructions, an exe of 42.6 MB against 29.3, packed 6.8 against 5.3, one cold compile of 88 s on a shared PC, trace equal), at a cost that grows faster than what it gives.

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
- **A boot that stops at the desktop with nothing the converter can choose** (known limit). When disk 1 has no `AUTO` folder and holds
  several programs that no rule of section 2 picks (two language versions, a game and its music player, two games on one disk), or
  holds none at its root, the game starts at the GEM desktop and the player opens the program with the mouse (Ctrl+Alt+M captures it,
  as on any desktop game; a double click on drive A, then on the program). The report (`desktop_autostart.reason` and `candidates`)
  names the programs and says that no rule picked one. Which disk-1 programs a game needs is not read from the program: only the names
  of the root are. The root is read where the TOS reads it, after two FATs whatever the BPB declares (1.7.4: Battle Probe, Pharaoh III and Trailblazer declare
  one, and looked empty before). In the library tried (275 ZIPs; the twelve of the census of 12 November 2026 were each booted for the first time on 13 November,
  headless, on EmuTOS and on TOS 1.04) the games that stop at the desktop are: Backgammon Royale (BG.PRG and three language versions), Chess Simulator
  (CHESS_F.PRG, CHESS_GB.PRG), Mean 18 (ARCH.PRG, GOLF.PRG) and Mercenary (ESCAPE.TOS and SECOND.TOS, two games) with several programs and no rule; Kick Off 2 - Winning
  Tactics, a data disk with nothing to start; and Trailblazer, now that "editor" is a utility, started by TRAIL.PRG. The census had put three others among them that start
  by themselves (Pac-Mania through its AUTO folder, World Class Leader Board, and Leader Board, whose title then prints "INSERT SECURITY KEY": a hardware-key
  protection the converter does not answer, listed in the report's `route_warnings`); Metro-Cross starts by itself on TOS 1.04 and stays on a blank screen on
  EmuTOS, and Pharaoh III (PHAROAH.TOS, the only program once the root is read as the TOS reads it) starts its menu on TOS 1.04 and ends in an EmuTOS "Panic: Bus
  Error" (choose your own TOS 1.04 in Options > Atari ST for both). Six others start their program since 1.7.3 (Battle Chess, The Chessmaster 2000, Championship Cricket,
  Logical, Outcast, Rody et Mastico III), Battle Probe (PROBE.PRG) and Conquests of Camelot (SIERRA.PRG, as MUSIC.PRG is a utility; its title shows on EmuTOS) since 1.7.4.
  Several disks that start by themselves (a boot sector of their own, an `AUTO` folder) are not concerned. A disk
  whose root is empty and whose boot sector is a plain one cannot be told apart statically from a data
  disk: the report says it holds no program.
- **The MFP's timer D: Hatari's patch of it is chosen per game** (1.7.3; the patch itself is a known limit, on purpose, since 1.7.2). TOS, EmuTOS as well as Atari's, starts this timer at a very high rate with its interrupt off; each tick costs an event in Hatari, one every couple of instructions, which keeps the native chains short. Hatari's own option (`hatari_timerd`) starts it far slower when the code that starts it is in the TOS's addresses, and tells TOS the old value when TOS reads it back. The rate left differs by TOS, as the patch of the control register fires once: TOS 1.04 stays at prescaler 200, data 100, 123 Hz; EmuTOS writes the register again at boot and stays at prescaler 4, data 100, 6,144 Hz, which is 123 events per frame of about 974. **A game that uses the timer as TOS left it sees another rhythm, or another value in its data register; a game that programs the timer itself is not touched.** So the machine has two modes, and each game gets one: `patched` (Hatari's option on, lighter on the PC) or `exact` (off: TOS starts the timer as it asks, `tools/atarist_hardware_check.py` measures 599 interrupts for 598.4 by the data sheet, the same program started from RAM). No fidelity is claimed in either mode.
  **How a game gets its mode.** The Options row "Atari ST: timer D" (`atarist_timer_d`, `--atarist-timer-d` on the command line) is `auto` by default, `patched` or `exact`. On `auto` the fresh references run with the patch, and a detector in the adapted Hatari (`retrorecomp/atarist_hatari.py`, observation only, in either mode) looks at the accesses to the MFP's registers made from outside the TOS's addresses: **sign A**, a read of timer D's data register (TDDR); **sign B**, timer D's interrupt left enabled and unmasked (IERB and IMRB bit 4) while the code never wrote TDDR or started the timer, so that TOS's own brief enabling at boot does not count; **sign C**, TCDCR written with timer D's bits not zero before any write of TDDR; **sign D**, a read of TCDCR, counted and never alone a reason. If A, B or C is seen on any route, the references run again with the patch off, the game is built and validated on that machine (the reference, the native game and its packed copy run the same mode: each run's report says which, and a conversion refuses a run of another mode), and the report says why in `machine.timer_d`: the mode, the choice, the reason (the sign, the frame, the pc and the route), the counts of every sign by route, and the first references' mode they were measured on. `patched` and `exact` force the mode and say so. The frame comparison cannot see the mode, as the reference has it too.
  **What was seen** (EmuTOS, the Standard routes, 12 November 2026): Bomb Jack shows no sign and stays `patched`; The Seven Gates of Jambala reads TDDR once (sign A, frame 779, pc $0106F8 in RAM, on both routes), so `auto` runs it `exact` (Hatari's list names it as needing the option off, for its colour rasters); both routes of each equal their fresh reference and the compressed copy, and Jambala is 4 interpreted instructions on a route (48.9 million native). `tools/atarist_hardware_check.py` now also measures the detector with authored programs (51 measurements, 49 agree, the same 2 recorded differences): each sign counts from RAM, nothing counts for the same accesses made from the ROM, for a masked interrupt, or for the order a game that sets the timer itself uses, and the counts are the same with the patch off.
  **What the detector misses.** It sees the code the routes reach: a game that touches the timer only later, or on a path the scripted inputs never take, is `patched` without a sign. TOS's own code is not looked at, so a game that reaches the timer through the TOS (the RS-232 routines use it as the baud rate generator) shows nothing. A sign can also be a false alarm (a game that restores the interrupt enable register it saved when TOS had timer D's bit set reads as sign B): the cost is a heavier game, never a wrong one. Hatari's source also names Paradroid and Speedball as using the timer without setting it up, and its list names Exterminator and Super Sprint; none of them was tried. With EmuTOS, the boot itself runs a little differently from the unpatched machine, so a game's course can differ between the two modes (Elite draws another word at its protection, Kick Off 2's long route ends elsewhere): the same sensitivity as a shift of one frame in the inputs.
  **What `patched` buys**, an estimate on a PC that was not quiet, host cycles of the main route, the option off over on, nothing else changed (5 runs, median and min, 9 November 2026): on EmuTOS Bomb Jack 1.55 and 1.58, Indiana Jones 1.30 and 1.57 (noisy), Kick Off 2 1.70 and 1.60; on TOS 1.04 Bomb Jack 1.56 and 1.58, Indiana Jones 1.80 and 1.76, Kick Off 2 1.76 and 1.65: so an `exact` game costs 1.3 to 1.8 times the host cycles of the same game `patched`. Not a timing. None of the ten panel games reads timer D or relies on its rate outside TOS (counters on their main and first long routes, 9 November 2026): Lethal Xcess and Turrican II touch the timer but program it themselves.
- **EmuTOS is not Atari's TOS** (known limit). Some games written for Atari's TOS do not run on it; EmuTOS's own
  `doc/incompatible.txt` lists the known ones. Turrican II is one of them on the panel: it uses low memory that EmuTOS also uses
  ("this can never work with EmuTOS"), and it stops after its Rainbow Arts intro. **The player's own TOS is needed for such a
  game.** Every conversion on EmuTOS says so in its messages and in its report (`tos_note`): no signal tells a game that EmuTOS
  cannot run from a game waiting on a still screen, so the sentence is the same for every game. The private memory of a game is
  kept per TOS.
- The first conversion without a TOS of the player's needs the network once, for EmuTOS (3.5 MB).
- Linux: the ten panel games were converted and validated on a Debian 13 PC (9 November 2026, system GCC, Standard level, the tree of the Windows panel above): the same counts as Windows, the
  traces of all 20 routes (CPU registers, RAM, picture and sound of every frame) byte for byte those of Windows, the compressed copy and the state continuation too. No game was played interactively on Linux (window, sound, pad).
- Linux, panel of eight (13 November 2026, a Debian 13 PC, system GCC, the tree of `spec/atarist-174`, extended level, one scratch library per game, the game's files deleted after each run): Bomb Jack, Another World, Operation Stealth, Turrican II (the player's own TOS 1.04), Kick Off 2, Lethal Xcess, The Lurking Horror and Battle Probe were converted and validated there; the trace hash of every one of the 24 routes (3 per game; the fourth, thorough-level route of Lethal Xcess was not run on Linux) is the same as on Windows, with the same native and interpreted counts, and the compressed copy and the state continuation equal the reference. No game was played interactively on Linux (window, sound, pad).
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
  save disk has none to use yet: The Pawn is one (tried on 13 November 2026, EmuTOS, headless: its save command asks for a file name, then answers "Ouch - bad save", with three names; the file system of its disk is a nine-sector
  fragment that holds only its loader, so the TOS has no room to create a file there, and the game expects a blank formatted disk).
  One real game was seen saving (`tools/atarist_saves_game.py`, 9 November 2026, TOS 1.04 and EmuTOS, Windows and Linux): The Lurking Horror writes 27 sectors by GEMDOS, and a new process with the file restores to the
  room of the save, where one without it answers "Failed."; no route of the panel saves.
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
  target of an observed instruction; since 1.7.2 none of its text enters a game. Its author granted the project owner an
  additional, personal permission (13 November 2026) for this build-time use on the Atari ST target, alongside the GPL
  components of the exports, on condition that no code of m68k-recomp-core enters them; it does not pass to forks or to other
  machines: [licenses/m68k-recomp-core-atari-st-permission.md](../licenses/m68k-recomp-core-atari-st-permission.md).
- Upstream pins and review: [UPSTREAMS.md](UPSTREAMS.md).

## 7. Where it stands in the qualification

The Atari ST column of [QUALIFICATION.md](QUALIFICATION.md) (13 November 2026) is `Y` on G1 to G6, G8, G9, G12, G13 and G15, `P` on G7 (saves: one real game) and on G10 and G11 (named behaviours measured against documentation and
fixtures, not silicon), `?` on G14 (the owner's own play, which no tool fills) and `-` on G16 (no shared paths). G9 rests on six of the eight panel games reaching play or a match, the two others stopping on a protection that
each lists in `route_warnings` with its reason. Leaving the experimental status is the maintainer's own decision, after a very high evidence bar.
