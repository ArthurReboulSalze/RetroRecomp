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
| Windows with a graphics card that has Vulkan 1.1 | Linux (the machine was witnessed on a Debian 13 PC during the engine gate, the conversion is not); integrated graphics (unverified) |

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
   the game is loaded by a fresh process, whose continuation is compared with the unbroken run and reported. A conversion that fails
   a check keeps the earlier export.

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

On every route, native plus interpreted instructions equal the reference's count but one: the instruction the reference has
counted and not yet finished when the frame ends. Both games' routes stay in their menus (Super Mario 64's file and sound
selections, Ocarina of Time's name entry): no route reaches play yet, so the shares above are those of menu code. The sound of a
resumed game differs because the core's state leaves out the libretro sound resampler.

## 7. Known limits

- A game whose code moves under the TLB keeps that code on the interpreter.
- The bounded routes do not reach play: what they observe is menu code (route depth, gate G9).
- A quick state is refused by another build of the same game; a resumed game's sound differs for a moment (the resampler).
- Linux conversions, integrated graphics and per-frame timing in play are not yet measured; no speed is claimed.
