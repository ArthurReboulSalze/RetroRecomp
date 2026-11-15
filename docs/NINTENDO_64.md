# Nintendo 64

Experimental profile (`n64`): the converter offers it when the installation carries the Nintendo 64 files, and it is not shared
through the compilation library. It converts a Nintendo 64 cartridge image into a standalone Windows executable that runs the game on
[Mupen64Plus-Next](https://github.com/libretro/mupen64plus-libretro-nx) with the ParaLLEl renderer on Vulkan, with guarded native
blocks for the VR4300 code its reference runs observed and the core's interpreter, counted, for the rest. Nothing here says that a
game plays completely, that the hardware is reproduced faithfully, that a game runs in real time on a given computer or how long
input takes to reach the screen: those are separate measures, listed below with what is known of each.

**What "native" means here.** The game runs on a complete emulator core inside the executable, Mupen64Plus-Next with ParaLLEl-RSP and ParaLLEl-RDP, with its machine, its chips and
their timing. Only the VR4300 instructions that the conversion saw running become native blocks, and each block calls the core's own instruction handlers behind a guard: it is not a
standalone translation of the game. The RSP's microcode is recompiled at run time by ParaLLEl-RSP and the RDP runs on the graphics card, both as the core does. So the native share
below measures how much CPU code avoids the core's interpreter; it cannot be compared with the figures of a machine whose game code is translated, and it says nothing about hardware
fidelity. See [ARCHITECTURE.md](ARCHITECTURE.md#machines-that-run-on-an-emulator-core).

## 1. What is converted, and what is not

| Converted (experimental) | Not yet |
| --- | --- |
| Cartridge images in any of the three byte orders (`.z64` big-endian, `.v64` byte-swapped, `.n64` word-swapped; a `.rom` whose content is a cartridge image), NTSC and PAL | The 64DD and its disks; the Transfer Pak; the Voice Recognition Unit |
| The Expansion Pak (8 MiB) always present; a controller pak in every pad (memory pak by default, Rumble Pak on request) | Per-game choice of pak in the interface |
| Four pads with the analog stick, the C buttons on the right stick, rumble; quick states (F8/F9); the cartridge's saves and the memory paks kept in the game's data folder | A played-through game |
| Windows with a graphics card that has Vulkan 1.1; Linux, witnessed headless (two games converted on a Debian 13 PC, section 6) | A game played on Linux; integrated graphics (unverified: one machine measured, section 6) |

The input is read in place and never changed; a byte-swapped dump is put in the console's order in memory, and the identity of the
game is the SHA-256 of that big-endian image, so one cartridge dumped in two orders is one game. The player supplies the cartridge
image; Retro-Recomp publishes no game and no firmware (the console needs none: the boot is the core's own).

## 2. How the conversion works

1. **Reading the input.** `retrorecomp/n64.py` tells the byte order from the image's first word (never from the extension), checks
   the size and the boot entry point, and reads the header: the internal name, the game code, the country (PAL or NTSC) and the
   revision.
2. **The machine.** The games run on Mupen64Plus-Next pinned at one revision (`n64_core.CORE_REV`) and adapted at build time by
   `retrorecomp/n64_core.py`: only the parts it needs are copied out of the checkout, eleven upstream files with no licence notice
   are replaced by our own MIT files written from the interfaces (`native/n64_machine/glue/`), and each change to the core must find
   its pinned text exactly once, so an upstream change fails loudly. The machine is the Mupen64Plus core (the VR4300 and the
   console's devices), ParaLLEl-RSP (the RSP's microcode, recompiled at run time) and ParaLLEl-RDP (the RDP, on the GPU with Vulkan
   compute, its commands recorded on the emulation thread so that two runs give the same pixels). The machine library is built once
   per core revision; a game compiles only its own blocks, the session and the player against it.
3. **Native blocks.** The fresh reference run of a conversion runs the VR4300 on the core's pure interpreter and observes, at every
   place the code jumps to, the straight run that starts there up to its first jump or branch and that instruction's delay slot,
   once per address and per code identity (overlays load different code at one place: each version is kept). A run also ends at
   128 instructions and on an instruction that has no delay slot and does not jump (MFC0, CACHE); the instruction after it starts a
   run of its own. Those runs become C (`retrorecomp/n64_native.py`): each block calls the core's own function for each instruction
   with the opcode a constant (no fetch, no decode), stops as soon as the PC leaves the straight line (an exception), re-checks its
   own words after every store, and runs only when its words are the live ones (the guard); blocks follow one another without going
   back to the interpreter's loop. KSEG0 code and TLB-mapped code both become blocks: a run of mapped code stays within its 4 KiB page,
   and its block reads the live words through the TLB's page table, so a page mapped elsewhere fails the guard; an unmapped page has
   no block and the interpreter takes the TLB exception. The uncached KSEG1 code (the boot code) and the rarest runs (the generator
   keeps the runs that make 99.5 % of the executions, and every version of a kept address) run on the interpreter, counted. A game
   with no block runs the core's cached interpreter, also counted.
4. **Validation.** The game executable is copied alone and replayed headless on the same bounded scripts (a main route of pad and
   stick inputs and, at the Standard level, a second exploration route, 3,600 frames each): the picture, sound, RDRAM and CPU
   registers of every frame must equal the fresh reference's, and every interpreted instruction is listed where it ran, with its
   class (gate G3): the report gives the totals by class and the 256 most run sites, and names the file of the whole listing, with
   its SHA-256, in the conversion's qualification folder. So must the compressed copy that is delivered. A quick state saved by the game is loaded by a fresh process,
   given the cartridge save as it was when the state was taken; its CPU, RDRAM, picture and sound must continue the unbroken run
   (section 6). A conversion that fails a check keeps the earlier export.

## 3. The five measures

| Measure | What is known |
| --- | --- |
| **Native code** | The share of VR4300 instructions run by native blocks on the routes of each conversion, in its report (`final_checks[].native_instructions` and `interpreted_instructions`, counted the way the interpreter's loop counts them: a jump and its delay slot are one). The RSP's microcode runs on ParaLLEl-RSP's own recompiler and the RDP on the GPU: neither is VR4300 code and neither is counted as native. |
| **CPU fidelity** | The native blocks equal the core's interpreter on every frame of the routes run (trace equality with a fresh reference). Agreement with the core, not with a real VR4300. krom's 114 CPU test programs on the core's interpreter: 90 pass, 22 fail in named families (timing, the Status register after exceptions, unaligned accesses, CAUSE, PI DMA alignment), one draws no verdict and one stops the player ([QUALIFICATION.md](QUALIFICATION.md#nintendo-64-evidence-behind-its-column-15-november-2026), G10); no per-instruction vectors exist for the VR4300. |
| **Hardware fidelity** | Mupen64Plus's and ParaLLEl's, unmeasured here. ParaLLEl-RDP is a low-level RDP; the RSP runs its real microcode. No comparison with a console. |
| **Gameplay validation** | None: the routes are short bounded scripts, not play. |
| **Physical latency** | Not measured. No speed or real-time claim is made: a game's speed depends on the graphics card, and integrated graphics are unverified. |

## 4. In the game

The pad: A, B, Z (left trigger), Start, L, R, the four C buttons (the right stick, or Y and B on a gamepad, I/K/J/L on the
keyboard), the d-pad, and the control stick (a gamepad's left stick; the arrows push it to its edge on the keyboard). F2 shows every
binding and the stick's dead zone. F3 opens the graphics page: internal resolution (1x, 2x, 4x), super-sampled read-back, the
VI filters (anti-aliasing, divot, gamma dither, bilinear scaling, dither filter), deinterlacing, overscan crop, native texture
rectangles and texture LOD. Each changes only what the player sees; the defaults are the setting every check uses. The Vibration row
of the options page turns rumble off.

## 5. Licences

An exported Nintendo 64 game is distributed under the **GNU GPL, version 3**: the Mupen64Plus core is GPL-2.0-or-later and the
program also holds GNU Lightning (LGPL-3.0-or-later) and the Apache-2.0 Vulkan headers. angrylion (no commercial use) and the
GLideN64 renderer (GPL-2.0-only) are never compiled. Details, the corresponding source and the changes made to the core:
[licenses/mupen64plus-next.md](../licenses/mupen64plus-next.md).

## 6. Evidence

The engine gate (7 November 2026, three games read in place, outside the repository): native blocks equal a fresh reference on
every frame of Super Mario 64 (4,900 frames) and The Legend of Zelda: Ocarina of Time (12,000 frames); on a Debian 13 PC with
integrated graphics the picture equals Windows' frame for frame.

The first conversions through the converter (7 November 2026, Windows, llvm-mingw, an NVIDIA GeForce RTX 3090, the Standard level,
two routes of 3,600 frames each, no shared base, an empty library):

| Game | Routes | Native share of the VR4300 instructions | Guard misses | Compressed copy | Quick state in a fresh process |
| --- | --- | --- | --- | --- | --- |
| Super Mario 64 (PAL, `NSMP`, 8 MiB) | main, explore | 94.2 %, 94.4 % (2,263 blocks) | 0 | equal to the reference on both routes | CPU, RDRAM and picture continue for 400 frames; the sound samples differ |
| The Legend of Zelda: Ocarina of Time (PAL, `NZLP`, 32 MiB) | main, explore | 94.0 %, 94.1 % (3,080 blocks) | 0 | equal to the reference on both routes | CPU, RDRAM and picture continue for 400 frames; the sound samples differ |
| Mario Kart 64 (PAL, `NKTP`, 12 MiB) | main, explore | 96.3 %, 96.7 % (4,654 blocks) | 0 | equal to the reference on both routes | CPU, RDRAM and picture continue for 400 frames; the sound samples differ |

On every route, native plus interpreted instructions equal the reference's count but one: the instruction the reference has
counted and not yet finished when the frame ends. The generic routes of Super Mario 64 and Ocarina of Time stay in their menus
(the file and sound selections, the name entry); Mario Kart 64's main route reaches a race. The sound of a resumed game differs
because the core's state leaves out the libretro sound resampler.

**Routes that reach play.** At the Extended and Thorough levels a game with a route of its own also plays it
(`n64_conversion.PLAY_ROUTES`, keyed by the game code, tuned on the PAL dumps): Super Mario 64 (6,000 frames: the PAL sound
selection, file A, the intro, then Mario runs, jumps and punches in the castle grounds from about frame 3,900) and Ocarina of Time
(16,800 frames: file 1 named "A", the intro's words, then Link walks in his house from about frame 15,600).

Both converted at the Extended level (7 November 2026, same machine): every route of both games equal to its fresh reference, the
compressed copy too, the quick state continued in a fresh process.

| Game | Route | Frames | Native share | Guard misses |
| --- | --- | --- | --- | --- |
| Super Mario 64 | main, explore, play | 3,600, 3,600, 6,000 | 94.4 %, 94.7 %, 93.1 % (3,540 blocks) | 0 |
| Ocarina of Time | main, explore, play | 3,600, 3,600, 16,800 | 94.2 %, 94.2 %, 95.1 % (5,166 blocks) | 1,166, 936, 16,489 |

A guard miss is a block whose words were not the live ones at that moment: the interpreter ran those instructions, counted in the
interpreted share. Every observed version of a kept address is kept (before that, 1,648, 1,318 and 25,793 misses); the misses that
remain are versions no observation holds, whose cause is not established.

**A Debian 13 PC with integrated graphics** (8 November 2026; Intel Core i7-6600U, 2 cores, Intel HD 520, Mesa 25.0.7, GCC 14). Mario Kart 64
converted through the whole pipeline at the Standard level: the same 4,654 blocks, 96.3 % and 96.7 % native, 0 guard misses, the
compressed copy equal to the reference, the quick state continued. **The traces of both routes are byte for byte equal to Windows'**
(an NVIDIA GeForce RTX 3090, llvm-mingw): picture, sound, RDRAM and CPU registers of every frame. Super Mario 64, on the same PC with all the corrections below (the Quick level, its main route): its trace is byte for byte
equal to Windows' too, 94.2 % native, 0 guard misses, and the quick state continues CPU, RDRAM and picture for 400 frames, only the sound differing. Its compressed copy stopped at start,
twice, on a trap signal and before any output (a first run on this PC, from an earlier tree, showed no such stop; the cause has not been looked for), so the common fallback delivered
the build unpacked, as built and validated: a larger file. Those two conversions make the profile's Linux `witnessed`; neither game was played on Linux.

Its speed, on the engine gate's own host and the states of its speed pass (the PAL games, one Vulkan present per frame on a real X
display, 1,000 frames timed, three runs each; 50 frames per second is the console's rate):

| Game | Cached interpreter, median (worst) | With native blocks | Cached, with the RDP asynchronous |
| --- | --- | --- | --- |
| Ocarina of Time | 63.2 (62.6) | 71.7 (62.5) | 83.0 (82.6) |
| Mario Kart 64 | 61.6 (61.6) | no block for this game in that build: 58.7 (58.4) | 62.6 (61.8) |

These are averages over those scenes on one computer, through the engine gate's host: no per-frame figure, no dense scene and no NTSC
game there, and they do not make a requirement.

**What a player's path costs, on a strong desktop** (8 November 2026; Windows, Ryzen 9 3900X, GeForce RTX 3090). The game's own path: the host kit,
the read-back of the renderer's image, Direct3D 11 without vsync, a hidden window paced by the kit, a silent sound driver. Three runs of 1,800 frames from a
state in a busy scene with a script moving the player; worst of the three, after 200 warm-up frames; each frame's cost without the wait:

| Scene | Budget per frame | Rate kept | Median | 99th percentile | Worst frame | Frames over budget, of 1,600 | Native share |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Super Mario 64 (PAL), castle grounds | 20 ms | 50 per second | 9.1 ms | 19.0 ms | 28.0 ms | 8 | 94.7 % |
| Ocarina of Time (PAL), Hyrule Field | 20 ms | 50 per second | 10.1 ms | 22.5 ms | 26.5 ms | 216 | 95.1 % |
| Mario Kart 64 (PAL), a 4-player race | 20 ms | 50 per second | 12.5 ms | 20.0 ms | 23.6 ms | 16 | 91.1 % |
| Ocarina of Time (NTSC), Hyrule Field, no block | 16.7 ms | 60 per second | 11.7 ms | 21.5 ms | 27.1 ms | 471 | 0 % |

The rate held on every run (the lowest was 49.997 per second), because cheaper frames absorb the costly ones: the pacing is uneven on Ocarina of Time, above all in
NTSC, and how that feels has not been judged. The first 200 frames hold stalls of 31 to 60 ms. The costly frames of Ocarina of Time are the one vertical interrupt in
three where the game does the work of its picture: never two in a row, and the others cost 7 to 10 ms. In a short split of those scenes (the engine gate's host, on a computer
that was busy, so in relative terms only) the costliest third of the frames spent about 60 % of their time in the VR4300 (11 ms, against 4 ms in the other frames), 14 % in the
RSP's graphics, 11 % on the RDP, 8 % in the VI and 7 % in the sound; the read-back, the drawing and the present are about 1 ms together.

An unpaced run started after an idle can be slowed by the GPU's driver: the fixed work of each picture takes about 13 ms instead of under 1 ms, 51 frames per second instead of
176, until it flips between two processes, with the GPU seen at low clocks (samples, no clock forced). The paced runs above do not show that cost. A weaker card, integrated
graphics through this path, a visible window with vsync and real sound have not been measured, so no hardware requirement is written.

**Small text and the hidden RDRAM.** The owner found Super Mario 64's text unreadable. The cause was in our own glue: the renderer's hidden RDRAM (one byte per 16-bit word, so half the size of
RDRAM) was given an eighth, and the coverage of framebuffers higher in memory was lost, so that the VI's anti-aliasing and divot filters ate thin strokes. Corrected on 8 November 2026, with the default
filters still on; no default changed. The window's scaling (nearest, 1.2 times in width at 768 x 576) leaves the text readable. The figures of this section before this paragraph, the Debian witness of
Mario Kart 64 included, were measured before that correction.

**The quick state and the renderer's memory.** The core's state does not hold the renderer's hidden RDRAM and TMEM, so a game resumed in a fresh process drew its first frames differently
(4 of 400 on Super Mario 64). The state now holds both (format `RRN64QS2`, copied through a staging buffer at F8 and F9, so frames pay nothing), and a conversion whose resumed game differs
in CPU, RDRAM or picture is refused. On the three games (8 November 2026, Windows, 400 frames from frame 3,000): CPU, RDRAM and picture continue on every frame. The sound does not: its samples
differ on all 400 frames, their number per frame on 35 to 115 of them, by under 0.05 % in total (the core's state leaves out the audio resampler). Whether that can be heard has not been judged.

**What the quick state holds since 1.7.6 (format `RRN64QS5`).** A checksum covers every byte of a state and its size must be exact: a damaged
state (16 kinds checked by every conversion: cut, longer, empty, each header field and bytes of the body changed, another file) is refused
before the machine is touched, the program ends with exit status 4 and leaves the file as it was, and a missing state creates nothing. Beside the core's own state and the renderer's memory, the state keeps what the core and its plugins leave out
or rebuild otherwise, each found by comparing a fresh process resumed from a state with the unbroken run (and with a reload in the same process, which stayed equal), byte for
byte in RDRAM at the first frame that differed: the audio backend's rate and the sinc resampler's position and history (the sound now continues on every frame); the AI's two
queued DMA addresses, which the core's own load sets both to the last one written (Banjo-Tooie's sound and two audio buffers in RDRAM differed from the first frame), with its
format flag; whether an RSP task stopped on an interrupt and waits to go on, which the core's load clears; the RSP's own registers, which ParaLLEl-RSP keeps outside the core;
the renderer's count of primitives, the seed of the RDP's dither noise (GoldenEye 007 drew an effect otherwise 95 frames after a load); the RDP's registers (modes, combiner,
colours, scissor, images, tile descriptors), kept as the last command that set each and replayed after a load before the texture memory is restored; and a command cut at the
end of a list. With all of them, a resumed game must continue CPU, RDRAM, picture and sound: no difference is tolerated any more. The check gives the fresh process the
cartridge save as it was when the state was taken, as a player's game keeps its file; a quick state never holds the cartridge save.

**Graphics page and saves.** In runs without a visible window, every option of the F3 page was applied at start and the game kept its picture, 2x and 4x giving 1280 x 576 and 2560 x
1152. The options were also changed in the middle of a run (the internal resolution up and down, and a VI filter, at given frames, through the kit's path): the
rate held, with one stall of up to about 100 ms at a change of resolution. Ocarina of Time's SRAM: a file created in one process is
found by a fresh process, and reading it leaves the file as it was.

**Every save kind, 15 November 2026** (`tools/n64_saves_check.py` on the delivered programs of the panel, tree `4d41dd6a`). Each game writes its
save on its own route, with nothing forced: the EEPROM of Super Mario 64 and GoldenEye 007 (4 Kbit) and of Banjo-Tooie (16 Kbit), the SRAM of
Ocarina of Time and F-Zero X, the Flash of Majora's Mask, the controller pak of Rayman 2 (the note of the game it starts). For each, a fresh
process given the kept file plays on, and again with a copy in which one byte of the written kind is changed: their RDRAM differs (from frame
0 to 510 depending on when the game reads it), so the game reads the kept file, and reading it leaves the file as it was; a quick state taken
before the save was written, loaded by a fresh process, leaves the file holding what the route wrote; a file cut to half, an empty file or a
folder in its place never stops the game (600 frames) and is left as it was.

**F-Zero X: what the owner saw, an open item (14 November 2026).** The owner played F-Zero X (PAL) and accepted it for the experimental version, seeing a vibration on
the objects and an odd level of detail on the vehicles. He played at the 4x internal resolution with super-sampled read-back on and Weave deinterlacing. Measured from one
race state over 300 frames (Windows, Standard conversion, main route 95.5 % native): at 4x the CPU, RDRAM and sound are identical to 1x on every frame, only the picture
differs; with super-sampled read-back the RDRAM differs too (the framebuffer written back) while the CPU and sound stay identical; the native game equals the cached and pure
interpreters; every frame is a new picture (50 a second) and the HUD does not move. So the vehicles' motion and the choice of their models are the game's as Mupen64Plus runs
it, not the native blocks' and not the graphics settings'; their fidelity to a console is not measured. Two causes remain, not yet told apart: the host's pacing (the
picture is presented with vsync while the 50 Hz game keeps its own clock, so on a 60 or 144 Hz screen some pictures stay one refresh longer, a regular judder shared by
every PAL game), or the game's own effects (machines that shake at speed, rivals drawn with fewer polygons at a distance). The owner's description and his screen's refresh
rate will decide.

### The panel of 15 November 2026 (1.7.6)

Eight PAL cartridges chosen for what each adds, converted one at a time at the Extended level from an empty library each (Windows,
llvm-mingw, an NVIDIA GeForce RTX 3090, tree `7b33bd9d`; the same figures on `4d41dd6a`, before the state's checksum), none dropped: every route of every game equal to its fresh reference on the
pure interpreter, frame by frame (picture, sound, RDRAM, CPU registers), the compressed copy too; the quick state continued in a fresh
process on every frame of 400, sound included; the report lists every interpreted instruction, the counts adding up on every route.

| Game | Saves | Routes (frames) | Native share of the VR4300 instructions | Interpreted, by class (main route) | Guard misses (main) | Blocks | Conversion |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Super Mario 64 (`NSMP`) | EEPROM 4 Kbit | main, explore, play (3,600, 3,600, 6,000) | 99.69 %, 99.69 %, 99.28 % | boot 168,910; TLB 20; coverage cut 1,235,055 | 0 | 3,880 | 385 s |
| Mario Kart 64 (`NKTP`) | EEPROM 4 Kbit, pak | main, explore | 99.25 %, 99.78 % | boot 168,910; TLB 20; cut 4,500,578 | 0 | 4,641 | 213 s |
| F-Zero X (`NFZP`) | SRAM | main, explore | 99.41 %, 99.60 % | boot 172,201; TLB 23; guard misses 239,761; cut 2,918,763 | 19,297 | 3,120 | 239 s |
| Banjo-Tooie (`NB7P`) | EEPROM 16 Kbit | main, explore | 99.51 %, 99.48 % | boot 169,139; TLB 20; guard misses 217,071; cut 2,952,439 | 26,659 | 12,871 | 287 s |
| GoldenEye 007 (`NGEP`) | EEPROM 4 Kbit | main, explore | 99.27 %, 99.79 % | boot 168,910; TLB 110,275; guard misses 291,783; cut 6,834,253 | 494,307 | 6,971 | 321 s |
| Rayman 2 (`NY2P`) | controller pak | main, explore, play (14,200) | 99.65 %, 99.64 %, 99.43 % | boot 168,910; TLB 20; cut 4,747,966 | 0 | 6,460 | 1,187 s |
| Majora's Mask (`NZSP`) | Flash | main, explore, play (14,600) | 99.57 %, 99.68 %, 99.43 % | boot 169,139; TLB 20; guard misses 11,057; cut 2,366,432 | 987 | 6,018 | 757 s |
| Ocarina of Time (`NZLP`) | SRAM | main, explore, play (16,800) | 99.63 %, 99.57 %, 99.46 % | boot 169,139; TLB 20; guard misses 28,345; cut 1,768,658 | 1,167 | 5,201 | 765 s |

The classes: "boot" is the boot code in the RSP's memory (uncached KSEG1, always interpreted); "TLB" is mapped code in a page the
reference never observed as a run; "guard misses" are stretches that started where a block's words were not the live ones (an overlay
or a remapped page with code no observation holds); "cut" is code the reference ran whose runs the generator left out (it keeps the
runs that make 99.5 % of the executions: covering all of them triples the blocks of Super Mario 64 for half a point). No interpreted
instruction is unclassified and none is "unseen". The play routes reach play: Mario in the castle grounds, Link in his house and in the
forest, Rayman in the prison ship; the main route reaches a race in Mario Kart 64 and F-Zero X, Spiral Mountain in Banjo-Tooie and the Dam
in GoldenEye 007. Two coverage gaps were found by the listing and fixed before this panel: the run after an MFC0 (Super Mario 64's wait
on the Count register; 94.2 % native before) and TLB-mapped code (GoldenEye 007: 1.1 % before).

**What received paths would add (G16).** An N64 conversion is one observation pass, so a received path cannot save a pass. It can make
code native beyond the receiver's own routes: of the instructions each play route ran, a Standard conversion (main and explore routes
only) would have left on the interpreter 2.3 % (Majora's Mask), 3.9 % (Rayman 2), 7.3 % (Ocarina of Time) and 11.5 % (Super Mario 64);
an Extended conversion that plays the route leaves 0.54 % to 0.72 %. The Nintendo 64 does not share paths yet (not in `SHARED_SYSTEMS`).

### What "met" means for the Nintendo 64 (the target for leaving the experimental status, 14 November 2026)

The Nintendo 64 runs on a complete emulator core ([ARCHITECTURE.md](ARCHITECTURE.md#machines-that-run-on-an-emulator-core)), like the Amiga, the Atari ST and the
PlayStation, so its gates are read the way the Amiga's and the Atari ST's were when they left the experimental status: only the VR4300 is the CPU whose code becomes
native. The RSP (its microcode on ParaLLEl-RSP's own recompiler) and the RDP (on the graphics card) are the core's: they are named as emulated and never counted as native
code. A gate is met on the panel of exact cartridges converted from an empty library, not on a game chosen afterwards. Today the column reads `P` on G3 and G4 and `?` on G10.

- **G3, native code.** Met when, on every route of every panel game, each VR4300 instruction that ran on the interpreter is listed where it ran (address, word, count and
  its class) and the listed counts add up to the route's interpreted total, as on the Atari ST. The classes known today: the boot code (IPL3 and what it runs before the game
  reaches KSEG0), code outside KSEG0 (uncached KSEG1 or TLB-mapped), entries in the middle of a straight run (after an exception return), guard misses (an overlay changed
  under a block) and code the reference never reached. A class that a block can cover is brought to 0 on the panel's routes, or left with its reason written; nothing stays
  unexplained. Zero interpreted instructions is not required, and a native share alone never meets G3. Today: 3.3 to 5.8 % of the instructions are interpreted on a route,
  given as totals only, not listed.
- **G4, CPU fidelity.** Met when, on every route of every panel game, the native game equals a fresh run of the same core with the VR4300 on its pure interpreter, frame by
  frame (picture, sound, RDRAM, CPU registers), and native plus interpreted instructions equal the reference's count but the instruction in flight at the frame's end. That
  holds today on the routes of three games; met needs the whole panel, the long play routes included. The reference is Mupen64Plus's own interpreter: G4 says the native
  blocks agree with the core, not that the core agrees with a VR4300 (that is G10).
- **G10, independent CPU evidence.** No per-instruction VR4300 vectors (SingleStepTests style) were found in the study of 5 November 2026. The Amiga and the Atari ST,
  both on an emulator core, left the experimental status with G10 `P`, as the X68000 did before them, each `P` naming what is shown and what is not. For the Nintendo 64, `P` means: open CPU test programs (krom's, Unlicense; nemu64-tests, MIT) converted like games, each test's own pass or fail reading recorded, the
  native blocks equal to the interpreter on them, and every failing test named with its reason. `Y` would need vectors from an independent model (ares's VR4300, ISC, is the
  candidate) run through the native blocks and the interpreter; it is not part of the 1.7.6 target.

The other gates keep their common meaning, with what the Nintendo 64 adds: G7 needs each save kind of the panel (EEPROM 4 and 16 Kbit, SRAM, Flash, the controller pak)
found again by a fresh process without F8 or F9; G9 needs a route that reaches play on every panel game; G11 stays `P`, as on every machine; G14 is the owner's play test of
the panel. None of the gates measures hardware fidelity, gameplay coverage or latency, and none of them is claimed.

## 7. Known limits

- TLB-mapped code becomes native only in the pages the TLB maps when the reference observes it, and a page the game maps to other code
  later is a guard miss (counted). The uncached KSEG1 code (the boot code) always runs on the interpreter.
- F-Zero X: a vibration on the objects and an odd level of detail on the vehicles, seen by the owner, cause not settled (section 6); neither the native blocks nor
  the graphics settings change what the game computes.
- Only the games with a route of their own reach play, at the Extended level; the generic routes of the others may stay in menus.
- A quick state is refused by another build of the same game. At an internal resolution above 1x the upscaled coverage is not in the state (the first two
  frames after a load show the 1x content), and only the default resolution is checked.
- Linux is witnessed on two games, headless, one of them delivered unpacked (section 6). The owner played three games on Windows
  ([QUALIFICATION.md](QUALIFICATION.md)); no game has been played on Linux, and rumble has not been exercised.
- Frame pacing is uneven on Ocarina of Time (section 6); no speed requirement is claimed.
- The fallback hints of F12 are not recorded yet.
