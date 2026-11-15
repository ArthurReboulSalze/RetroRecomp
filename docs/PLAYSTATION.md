# Sony PlayStation

The PlayStation profile is **supported** since 1.7.6, on the owner's decision of 15 November 2026 after his play test (open as
experimental in 1.7.1; [section 8](#8-the-exit-from-the-experimental-status-15-november-2026-supported-from-176)). A conversion
makes a playable game whose R3000A code, as far as the conversion saw it run, is **native steps**; the rest runs on the machine's
interpreter and is counted and reported. This page says what it converts, how, and what it does not claim. The five measures
stay separate: native code, CPU fidelity, hardware fidelity, gameplay validation and physical latency.

**What "native" means here.** The game runs on a complete emulator core inside the executable, Beetle PSX, with its machine, its chips and their timing. Only the R3000A
instructions that the conversion saw running become native steps, and each step holds the core's own instruction handlers, expanded with the word fixed, behind a guard: it is not a standalone translation of the
game. The GTE, the GPU, the SPU and the CD-ROM controller stay the core's own code. So the native share below measures how much CPU code avoids the core's interpreter; it cannot be
compared with the figures of a machine whose game code is translated, and it says nothing about hardware fidelity. See [ARCHITECTURE.md](ARCHITECTURE.md#machines-that-run-on-an-emulator-core).

## 1. What is converted

- **Discs as the player gives them**, read in place and never changed: a PS1 Classics EBOOT (`.pbp`, one to five discs), a CUE
  sheet with its BIN files (one file for the disc or one per track), a CloneCD image (`.ccd` + `.img` + `.sub`), a bare raw image
  (`.bin`, `.img`) or an ISO (`.iso`, 2,048-byte sectors: such a dump holds the file system only, so a game's XA sound and CD audio
  are missing from it, and the report says so). A multi-disc game is one EBOOT holding its discs (playlists, `.m3u`, are not read
  yet: that extension is the X68000's disk sets). A signed EBOOT from the PlayStation Store is refused (decrypting it would
  circumvent its protection).
- **NTSC-U, NTSC-J and PAL discs**, two players, the first memory card (kept beside the game; the second port is off).
- **The DualShock pad** of each player: the d-pad, the four face buttons, L1, R1, L2 and R2 (the gamepad's triggers), L3, R3,
  Start, Select, both sticks and vibration. It powers on in digital mode, as the console's pad does (a game reads its d-pad);
  the **Analog** action (F, or the gamepad's extra button) switches it to analog mode, and a game that wants analog mode
  switches it itself. A stick pushed to its very edge is held at the edge of libretro's range (since 1.7.6: a gamepad whose
  stick read -32768 straight left was read by the core as full right; Ape Escape). While a pad is digital, the gamepad's left
  stick also works as the d-pad. A game the core's database knows
  as digital-only gets a standard pad on that port (Crash Bandicoot). A multi-disc game has a **Change disc** action (N), which opens the lid, swaps the disc and closes it.
- **Aspect ratio.** "Corrected", the default, shows the console's own pixel shape: with the overscan cropped (the default) that is
  1.22 wide for 1 high for most games (the part of a 4:3 line the game draws), so a fullscreen picture keeps black bars at its
  sides. "4:3" fills a 4:3 area instead and stretches the picture about 9 % wider than the console's signal; "Uncorrected" shows
  square pixels. None of them changes a pixel of the picture or a check.
- **The graphics card draws the picture** (1.7.7, the owner's decision of 15 November 2026: Beetle's Vulkan renderer). F3's first
  row, **Renderer**, chooses between the graphics card (the default) and the CPU (Beetle's software renderer, the reference of the
  conversion's checks, which never open the card). With the card the machine stays the checked one: beside it the software
  renderer keeps its own copy of the console's VRAM at 1x, and on Ape Escape the RAM, the CPU state, the sound and that VRAM equal
  the CPU renderer's at 1x on every one of 3,300 frames, with the card drawing at 1x or at 8x; only the picture is the card's own.
  A computer with no usable card (no Vulkan loader, no device, a device the renderer cannot run on) opens the game on the CPU and
  says so; nothing fails. Changing the row in play opens the machine again on the other renderer and gives it back as a quick
  state (a state saved with one renderer loads with the other: checked both ways, 600 frames equal). The Vulkan headers come from
  Khronos, and the shader layout and the HDR pieces the renderer asks for are our own files ([licence](../licenses/beetle-psx.md)).
- **Anti-aliasing and texture filtering** (1.7.7, on the owner's questions: « il me semble pas avoir vu d'options
  d'anti-aliasing pour la PlayStation », then « juste au moins pouvoir activer ou pas le filtrage des textures »). Two F3 rows,
  the graphics card only (marked « (GPU) »), both **Off** by default. « Anti-aliasing »: MSAA 2x, 4x or 8x (several samples per pixel on the
  polygons' edges, at the internal resolution), or Supersampling (Beetle draws at the internal resolution and reduces the picture
  to the console's size, each pixel the mean of the drawn ones; at 1x it has nothing to reduce). They are values of one row
  because both together only add cost. « Texture filtering »: the console's nearest texel, bilinear, or 3-point (the Nintendo
  64's own filter). Beetle's xBR, SABR and JINC2 texture upscalers, its adaptive smoothing, its MDEC chroma filter and texture
  replacement are not offered, and there is no mipmapping (the console has none and Beetle adds none). Both rows act on the card's
  drawing alone: on Ape Escape (3,300 frames) with MSAA 8x, with Supersampling at 4x, with bilinear and with 3-point plus MSAA 4x
  at 4x, the RAM, the CPU state, the sound and the VRAM equal the run with both Off on every frame, at 0 interpreted
  instructions; with the CPU drawing the rows change nothing (every column equal, picture included) and the game says so once.
  Their cost is the card's: MSAA multiplies the samples drawn, Supersampling draws the internal resolution in full.
- **Geometry precision (PGXP)** (1.7.7, on the owner's question: « Est-ce qu'on peut, nous aussi, utiliser comme Beetle PGXP ? »).
  Two F3 rows: « Geometry precision (PGXP) » keeps the GTE's results with sub-pixel precision and carries them through memory to
  the GPU, so 3D models stop wobbling (Beetle's "memory only" mode); « Perspective-correct textures » draws textures with
  perspective. Both are **On** by default for the player since the owner tried them (« C'est impeccable. Il faut l'activer par
  défaut »); a choice a player saved is kept, and a player who never touched the rows gets On. Perspective-correct textures need
  PGXP: with PGXP Off the second row is held off and says so. Both change in play, on the card and on the CPU. **The run a player
  sees by default is therefore not the checked run.** PGXP changes the emulated run slightly, as a raised resolution does on the
  CPU: on Ape Escape (3,300 frames) the RAM differs on about 450 frames and the CPU state on about 380, then comes back. The
  conversion's checks always run with both rows Off, and no fidelity is claimed for the run with them On. It still runs at 0 interpreted instructions (the native steps carry PGXP's own calls). Not
  offered: Beetle's "memory + CPU" mode (marked « Buggy » upstream), its PGXP primitive culling (known to lock some games) and its
  vertex cache; the core's game database still turns PGXP off for the games it knows break with it.
- **F3** also has the internal resolution (1x, 2x, 4x, and 8x on the card only: asked for on the CPU it draws 4x and says so),
  dithering, aspect ratio and overscan crop. Dithering, aspect ratio and overscan crop change only the picture. On the CPU a
  raised internal resolution also changes the emulated drawing time, so the game runs slightly differently from the checked 1x
  (measured on Ape Escape: at 2x, RAM and CPU differ from frame 96 on); on the card it does not (the comparison above). The
  conversion's checks use the CPU at 1x and the core's own settings. Since 1.7.6 there is no deinterlacing row: the picture is
  always progressive.
- **Screen format: 4:3 / 16:9** on the options page (since 1.7.6, kept per game): for a game that has its own widescreen option and
  draws a squeezed picture for a 16:9 television, 16:9 shows that picture 16 wide for 9 high. It changes only the rectangle the
  picture is shown in (the Aspect ratio row of F3 is not read then); a game without such an option is simply stretched. Checked
  on a game without a widescreen mode (a synthetic check: the saved choice gives a 1708 x 960 rectangle on a full-HD screen where
  4:3 gives 1228 x 960); no game's own widescreen mode has been tried.
- **A raised internal resolution has a real cost**: the renderer works in software on one thread. In combat in Tobal No. 1 on
  a Ryzen 9 3900X (informal, a busy PC), 2x holds the console's speed and 4x does not (about 18 % too slow, the sound breaks
  up). The game says so with a notice when a raised resolution stays behind; 1x and 2x are the settings to try first.
- **Interlaced pictures** (480 lines, Tobal No. 1's) are shown **progressive** by default: the GPU draws both fields of the
  displayed frame, so the picture is whole, without combing (the console itself draws one field per frame there; its drawing
  time is kept).
- **The gaps of CD-audio tracks** are given back to their tracks when a CUE sheet lists only each audio track's INDEX 01 while the
  image keeps its gap before it as digital silence (from one second, at most two): the core then sees the track boundary where
  the disc has it. A game that seeks to a track's start, known in whole seconds, can land in that gap; without it, it lands in the
  track before and the auto-pause stops the sound at once. Tobal No. 1 did this for ever and its fights had no music. The player's
  files are not changed, only the sheet the game holds, and the disc keeps its identity.
- **Rows a wrapping display reads and the game cannot draw are shown black.** A game can place its display so that it runs past
  the end of VRAM and wraps. Tobal No. 1 in combat starts at row 493 and draws in rows 12 to 463, so the top of its picture shows
  VRAM rows 510 and 511, whatever is stored there. The console sends them too, in the top overscan; a screen that shows every line
  shows coloured noise. Such a row keeps its place and is black, only when the display wraps, the row comes before the wrap and
  it lies outside the game's drawing area, in a 16-bit picture. Nothing is cropped and the machine is untouched: this changes the
  picture only, so hardware fidelity does not cover it. A picture loaded there rather than drawn, without a polygon, would be hidden
  too; none is known.
- **Frame pacing** follows the console: 59.826 frames a second with a progressive picture, 59.94 with an interlaced one (PAL
  49.761 and 50), so its 44,100 Hz sound reaches the device at the rate it is played.
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
process and the refusal of a damaged state. It also checks the controls of the published game: each one, pressed alone on
each player's pad, must reach exactly its own button of the console, and no pad may be in analog mode at power-on.
The game is published as built (not compressed: the disc follows the program).

Native code: the share of the routes' instructions run by native steps, and the interpreted remainder, are in the report per
route; outside the routes the game shows its own counter. The fetches that run no instruction (an interrupt being taken, or
the CPU held while a DMA transfer runs, when the core fetches the same instruction again each cycle) are counted apart, in
neither figure. CPU fidelity: what the core's interpreter does (each route's native steps are compared with it). Separately,
`tools/psx_vector_selftest.py` runs independent vectors on both paths, without a game: see below. Hardware fidelity: not measured;
with the free BIOS the report says so. Gameplay validation: only the conversion's routes. Physical latency: not measured.

## 4. Where it stands (15 November 2026)

Each line is one measure; none says anything about the others. The record is in
[QUALIFICATION.md](QUALIFICATION.md#sony-playstation-evidence-behind-its-column-15-november-2026).

- **Native code**: on the 24 routes of the eight panel discs (attract, play and an 18,000-frame route each), no instruction ran on
  the interpreter: 54.5 billion native instructions. This covers those routes only: code a game reaches later starts on the
  interpreter, counted, shown in the window title, and becomes native at the next conversion with the player's F12 hints (Gran
  Turismo 2's licence drive: 24 % interpreted before the owner's hints were taken, 2.2 % after).
- **CPU fidelity**: every frame of every route equals the core's interpreter in RAM, picture, sound and CPU state (registers, COP0,
  GTE). Independently of any game, 55,000 R3000A vectors pass on the interpreter and on the native steps, and 1,150 GTE vectors
  pass on the GTE. The CPU vectors come from ares's model, not from a console, and hold no COP0 or GTE instruction: this is
  agreement with a model, not proof against the silicon.
- **Hardware fidelity**: Beetle's. Measured on named behaviours only (`tools/psx_hardware_selftest.py`, 15 November 2026): the GPU
  tests of ps1-tests, booted through the BIOS like a game, draw what a console drew on 9 of 11 to the pixel, the CLUT cache and line
  ends apart; the timer, DMA and CD-ROM tests print cycle counts that differ from the console's ([QUALIFICATION.md](QUALIFICATION.md)).
- **Gameplay validation**: scripted routes; the long route reaches play on six of the eight discs, the two others are named with
  their reason in the report (Metal Gear Solid returns to its title, Gran Turismo 2 stays in its credits). The owner played Gran
  Turismo 2 on 15 November 2026 ("c'est fonctionnel"); the panel's play test (G14) is his.
- **Physical latency**: not measured. The frame cost was measured once on a quiet PC (15 November 2026, Gran Turismo 2 driving,
  an off-screen window with the sound device): 6.5 ms a frame at 1x, 7.6 ms at 2x, 11.7 ms at 4x with frames up to 33 ms, and no
  sample missing on that drive; 4x is labelled heavy and is too heavy for 3D racing on that PC (a stated limit).
- **Linux**: Ape Escape (EBOOT) and WipEout 2097 (CUE/BIN, PAL), converted on a Debian 13 PC with GCC, give the same values as
  Windows on all three routes. No game played on Linux.

## 5. What each gate meant here (written before the exit)

The PlayStation is, like the Amiga and the Atari ST, an emulator core with native code. Beetle PSX runs the machine, and the
conversion turns the R3000A code its routes ran into native steps. The gates of [STANDARDS.md](STANDARDS.md#supported-checklist)
are read for it as they were for those two machines, which left the experimental status in 1.7.5. A gate is `Y` only when what
is written here is shown. Anything less is `P`, with what is missing named. No gate says hardware fidelity, gameplay coverage or
latency.

- **Native code (G3).** Native: the R3000A instructions in main RAM and in the BIOS that the routes ran, as guarded steps holding
  the interpreter's own handler bodies. Not native, and not counted as such: the GPU, SPU, CD-ROM controller, MDEC, DMA and
  timers, which Beetle emulates (as vAmiga emulates the Amiga's chips), and the GTE's arithmetic, which a COP2 step calls in
  Beetle's GTE code. **Met:** on every final route of every panel disc, either no instruction runs on the interpreter, or each
  one that does is listed in the report by address, with its count and its reason (`final_checks[].interpreted_by_address`).
  The reasons are a word beyond the four kept for one address, code the observation did not hold, code outside main RAM and
  the BIOS, or a word a step holds but was reached from the step of another word at the address before it. None may be left
  unexplained: the game's own count must equal the sum of the list. An interrupt pending is not a reason: the fetch then runs
  no instruction (it is counted apart), except a COP2 instruction, which Beetle runs before taking the interrupt and which a
  step therefore holds too. Code past the routes runs on the counted interpreter, as on every machine: no whole-game claim.
- **CPU fidelity, the reference (G4).** The reference is a fresh run of the same machine with every instruction on Beetle's
  interpreter: the observing build, which records the code it runs and does not change the machine. **Met:** on every frame of
  every final route of every panel disc, the delivered executable equals that reference in RAM, picture and sound, as today,
  and in the CPU's own state. That state is the 32 registers, HI and LO, the PC, the COP0 registers a game sees (SR, CAUSE,
  EPC) and the GTE's registers. Today's per-frame trace holds RAM, picture and sound only, so the CPU state is the part to add
  (the Amiga's trace carries its registers). This is agreement with Beetle's interpreter, not with a real R3000A.
- **CPU fidelity, independent (G10).** The corpus: SingleStepTests/r3000 (55,000 vectors, made from ares's interpreter), run
  on Beetle's interpreter and on the native steps, and the GTE vectors of JaCzekanski/ps1-tests (1,150, recorded on a console
  according to their author). **Met for `Y`:** every vector passes on both paths with none unexplained, the check of the check
  sees a corrupted vector, and the GTE vectors also pass through native COP2 steps, not only on the GTE directly. The R3000A
  vectors hold no COP0 or GTE instruction and come from a model, not silicon; that stays written beside the letter. Without the
  COP2 path, G10 stays `P`, as it was for the Amiga, the Atari ST and the X68000 when they left.

The other gates are read as on the Amiga and the Atari ST:

- **Saves (G7):** two games save to the first memory card on their route. A fresh process of the delivered file reads the card
  back, and a damaged card file is set aside and never blocks the game.
- **Liveness and depth (G8, G9):** each panel disc's long route gets past its loading screens and cut-scenes into play, and its
  pictures are read. A route that cannot do so (a protection, a peripheral the game requires) is named in the report with its
  reason, and is never forced past it by a patch.
- **Hardware evidence (G11):** ps1-tests' GPU, timer and CD-ROM tests run on the machine and their results are recorded. This is
  `P` on every machine: named behaviours, not the chips.
- **Panel and platforms (G12, G13):** 7 or 8 discs with written reasons, none dropped for failing, and at least four of them as
  risk cases in `tools/campaign-risk-cases.json`. One or two discs on a Debian 13 PC give the same route hashes as on Windows.
- **Owner acceptance (G14):** the owner plays the delivered discs and decides. No tool or agent fills this gate.
- **Honesty (G15):** the interface, the exported game's window and its report are read for claims.
- **Shared knowledge (G16):** a supported machine either shares its paths or is declined on its panel's measured evidence that
  received paths would add no native instruction and save no conversion pass (the owner's rule of 14 November 2026). Measured:
  received paths add native code beyond the receiver's own routes, so the PlayStation shares them (section 6).

## 6. Shared paths (the experimental tier of the base, from 1.7.6)

The owner decided on 14 November 2026 that the PlayStation shares its paths (« Oui, elle partage »), after this measure on Ape
Escape: a receiver converting at the standard level (its attract and play routes, 48,809 observed words) and given the
observations of another player's long route (36,024 words more) runs the first level, which its own routes never reach, with no
instruction on the interpreter instead of 924,083,036 (19 % of 4.86 billion); no conversion pass is saved (a PlayStation
conversion is always one pass).

**What travels** (`retrorecomp/psx_knowledge.py`, on the common `path_records`): numbers about the player's own disc and BIOS,
never their bytes. A run of R3000A code a conversion observed whose words are found, as they are, in a file of the disc becomes a
span `[address, offset, length]`; the offset counts the user data of the disc's ISO 9660 volume, so a CUE/BIN and an EBOOT of the
same dump read the same words. Code run from the BIOS ROM, or from the kernel the BIOS copies into low RAM, becomes a row of the
player's BIOS, used only by a player whose BIOS has the same SHA-256. The record is keyed by the discs' digests. Words found in
neither stay private, counted: code a game decompresses (Ape Escape's main code is packed in its data file) never travels.
A record is made only from a conversion's own observations once every check passed; what a player received is not shared again
until his own conversion observes it. Received words become native steps behind the same guard as observed ones (the word the
CPU fetches), ranked after every observed word of their address, so a received word that does not fit runs on the interpreter,
counted. The whole sharing is withdrawn with one line (`path_profiles.EXPERIMENTAL_SHARED`).

**The proof** (14 and 15 November 2026, Windows, one conversion at a time, each player with an empty library of its own; tree of
`4f70b43c`): player A converts at the extended level and exports a version 3 file; player B imports it and converts at the standard
level; player C converts at the standard level with nothing imported; then A's 18,000-frame route is played by B's and C's games.

| Disc | A's record | B received | B's and C's checks | Long route: interpreted, C → B | Picture at the end |
|---|---|---|---|---|---|
| Ape Escape | 60,269 words in the disc, 6,988 in the BIOS, 17,576 private (of 84,833) | 67,257 words, 31,890 new | all pass, 0 interpreted on their routes, B's own record equal to C's | 924,083,036 → 220,036,709 (−76 %) | the same |
| Metal Gear Solid (2 discs) | 43,313 in the discs, 7,857 in the BIOS, 13,543 private (of 64,713) | 51,170 words, 3 new | all pass, 0 interpreted, B's record equal to C's | 594 → 0 | the same |

Ape Escape's remaining 220 million are the code it decompresses: its words are in none of the disc's files. Metal Gear Solid's
routes stay at its title screen (section 4), so its long route runs almost nothing its standard routes did not. A record whose
spans were moved to random places of the disc (player D, Ape Escape) changes nothing a conversion checks: every check passes, 0
interpreted on the routes, the same picture at the end of the long route (886,115,939 interpreted there: random places that hold
zeros give the R3000A's NOP, which real code holds too).

## 7. Not in this first scope

Mouse, multitap, light guns, the hardware renderers, LibCrypt and other sub-channel protections, CHD images, the PSP-derived BIOS.

## 8. The exit from the experimental status (15 November 2026, supported from 1.7.6)

The owner played the delivered exports on 15 November 2026 (said of the Nintendo 64 and the PlayStation together):
« Je viens de tester la Nintendo 64 et la PlayStation sur plusieurs jeux. Donc, le comportement du jeu en lui-même, ça me paraît plutôt solide et plutôt réactif. Je n'ai pas eu de bug graphique. J'ai pu aussi faire une sauvegarde sur Gran Turismo 2 qui a fonctionné. » Asked whether to take the PlayStation out of the experimental status: « Oui, sors-la ».

What the exit rests on ([QUALIFICATION.md](QUALIFICATION.md#sony-playstation-evidence-behind-its-column-15-november-2026)): eight discs at 0
interpreted instructions on all 24 routes, every frame equal to the interpreter including the CPU state, F9 in a fresh process on all eight, the
same values on a Debian 13 PC, two games' saves read back in a fresh process, the routes read into play or named with their stop, the ps1-tests
GPU programs drawing what a console drew, and shared paths.

**Limits, written:**
- **Resolution.** The picture is drawn in software on one thread. On the owner's PC 1x and 2x hold speed and 4x falls behind (« Le 2x tient
  très bien. […] le 4x, ça commence à ralentir et le 8x, c'est injouable »; frames up to 33 ms at 4x on one licence drive of Gran Turismo 2,
  a full race heavier). 8x is no longer offered. 2x is the advised raised resolution.
- **Native code** is the code the routes ran: code a game reaches later runs on the counted interpreter, shown in the window title, and becomes
  native at the next conversion with the player's F12 hints. What a game decompresses stays private in the shared paths.
- **Route depth.** Metal Gear Solid's routes go back to its title after the level select; Gran Turismo 2's stay in its credits (its races were
  driven by the owner and on a licence route).
- No hardware-fidelity claim, no latency measure, no game validated as played through.

## 9. The graphics card (1.7.7): what it rests on

- **The eight discs.** Each panel disc converted from the 1.7.7 tree, then its three routes (24 routes, 204,000 frames) played again
  with the graphics card (`--gfx renderer=0`): the RAM, the CPU state, the sound and the VRAM equal, on every frame, the CPU
  renderer's traces the conversion itself recorded (Windows, an NVIDIA GeForce RTX 3090). No run fell back to the CPU.
- **A real Linux driver.** Ape Escape converted on a Debian 13 PC with an Intel HD Graphics 520 (Mesa's ANV driver): its three
  routes (25,500 frames) with the card, the same four columns equal to the CPU renderer's, the picture the card's own. Linux tests
  now run in WSL Debian on the Windows PC, where Vulkan goes through Microsoft's D3D12 layer or Mesa's llvmpipe: that Debian PC
  stays the evidence for a Linux GPU driver.
- **No card.** In WSL the only Vulkan device is Mesa's llvmpipe (a device emulated on the CPU): the game refuses it, draws with
  its own CPU renderer and says so, and its trace equals the CPU renderer's on every column, picture included (Ape Escape, 3,900
  frames). `RETRORECOMP_TEST_VULKAN=none|device` gives the same fallback on any computer.
- **Switching in play.** Card to CPU and CPU to card from F3, while the machine waits in the menu, under each of the four filters,
  in a hidden window of the real Windows video driver (Direct3D 11): the game continues. The first 1.7.7 build closed there under
  xBR and Scale2x (the session opened again had no picture yet and those filters read it); the session now always gives a picture,
  the last one until the next frame (the owner's report of 15 November 2026: « dès que je switch de moteur […] le jeu se ferme
  tout de suite »).

