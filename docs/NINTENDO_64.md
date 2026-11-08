# Nintendo 64

Experimental profile (`n64`): the converter offers it when the installation carries the Nintendo 64 files, and it is not shared
through the compilation library. It converts a Nintendo 64 cartridge image into a standalone Windows executable that runs the game on
[Mupen64Plus-Next](https://github.com/libretro/mupen64plus-libretro-nx) with the ParaLLEl renderer on Vulkan, with guarded native
blocks for the VR4300 code its reference runs observed and the core's interpreter, counted, for the rest. Nothing here says that a
game plays completely, that the hardware is reproduced faithfully, that a game runs in real time on a given computer or how long
input takes to reach the screen: those are separate measures, listed below with what is known of each.

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
   once per address and per code identity (overlays load different code at one place: each version is kept). Those runs become C
   (`retrorecomp/n64_native.py`): each block calls the core's own function for each instruction with the opcode a constant (no
   fetch, no decode), stops as soon as the PC leaves the straight line (an exception), re-checks its own words after every store,
   and runs only when its words are the live ones (the guard); blocks follow one another without going back to the interpreter's
   loop. Code at other addresses (TLB-mapped code, the boot code) and code not seen runs on the interpreter, counted. A game with no
   block runs the core's cached interpreter, also counted.
4. **Validation.** The game executable is copied alone and replayed headless on the same bounded scripts (a main route of pad and
   stick inputs and, at the Standard level, a second exploration route, 3,600 frames each): the picture, sound, RDRAM and CPU
   registers of every frame must equal the fresh reference's. So must the compressed copy that is delivered. A quick state saved by
   the game is loaded by a fresh process, whose CPU, RDRAM and picture must continue the unbroken run; only the sound may differ
   (section 6). A conversion that fails a check keeps the earlier export.

## 3. The five measures

| Measure | What is known |
| --- | --- |
| **Native code** | The share of VR4300 instructions run by native blocks on the routes of each conversion, in its report (`final_checks[].native_instructions` and `interpreted_instructions`, counted the way the interpreter's loop counts them: a jump and its delay slot are one). The RSP's microcode runs on ParaLLEl-RSP's own recompiler and the RDP on the GPU: neither is VR4300 code and neither is counted as native. |
| **CPU fidelity** | The native blocks equal the core's interpreter on every frame of the routes run (trace equality with a fresh reference). Agreement with the core, not with a real VR4300: no independent processor vectors have been run. |
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
(an NVIDIA GeForce RTX 3090, llvm-mingw): picture, sound, RDRAM and CPU registers of every frame. Super Mario 64, on the same PC after the correction of the hidden RDRAM below: its main route's trace is byte for byte
equal to Windows' too, 0 guard misses. Those two conversions make the profile's Linux `witnessed`; neither game was played on Linux. Both ran before the quick state held the
renderer's memory (below), and the picture of Super Mario 64's did not continue then, as on Windows at the time: a resumed game has not been measured on Linux since.

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

**Graphics page and saves.** In runs without a visible window, every option of the F3 page was applied at start and the game kept its picture, 2x and 4x giving 1280 x 576 and 2560 x
1152. The options were also changed in the middle of a run (the internal resolution up and down, and a VI filter, at given frames, through the kit's path): the
rate held, with one stall of up to about 100 ms at a change of resolution. Ocarina of Time's SRAM: a file created in one process is
found by a fresh process, and reading it leaves the file as it was. EEPROM, Flash and the controller paks were not exercised.

## 7. Known limits

- A game whose code moves under the TLB keeps that code on the interpreter.
- Only the games with a route of their own reach play, at the Extended level; the generic routes of the others may stay in menus.
- A quick state is refused by another build of the same game. A resumed game's sound samples differ from the unbroken run (section 6). At an internal resolution above 1x the upscaled
  coverage is not in the state, and only the default resolution is checked.
- Linux is witnessed on two games, headless, and a resumed game has not been measured there since the state holds the renderer's memory. The owner played three games on Windows
  ([QUALIFICATION.md](QUALIFICATION.md)); no game has been played on Linux, and rumble has not been exercised.
- Frame pacing is uneven on Ocarina of Time (section 6); no speed requirement is claimed.
- The fallback hints of F12 are not recorded yet.
