# RetroRecomp roadmap

This page says what is planned for each machine, in the order we expect to work on it. It states intentions, not dates or
compatibility promises: a plan can change when evidence says so. Each machine's progress through the common qualification
list is in [QUALIFICATION.md](QUALIFICATION.md); the games that do not convert are in [KNOWN_FAILURES.md](KNOWN_FAILURES.md).

Five measures stay separate in every step below: native code, CPU fidelity, hardware fidelity, gameplay validation and
physical latency. Native execution alone guarantees neither complete compatibility nor zero latency, and the interpreter
fallback stays counted and shown wherever it is used.

## Where things stand (1.7.3, November 2026)

| Machine | Status | Next step |
| --- | --- | --- |
| Master System | supported | the evidence lot below |
| Game Gear | supported | the evidence lot below |
| Game Boy | supported | the remaining test ROMs, at low priority |
| Game Boy Color | experimental, in development (not in a release yet) | the owner's play test, routes that play further on the whole panel, the cause of the `cgb-acid2` difference, an optimisation pass |
| NES | supported | broader panel |
| Mega Drive | supported | report and Linux witness; MAME sound comparison |
| Super Nintendo | supported | Linux witness; DSP-2 and DSP-4 |
| Neo Geo | supported | Linux witness on more games |
| Capcom CPS-1 | supported | rotary-dial boards; the Z80 interrupt-mode-0 opcode has been counted since 1.6.5 |
| Capcom CPS-1.5 (QSound) | supported, with the CPS-1 (since 5 November 2026) | Linux witness of the QSound games; a run of the DSP16 |
| Sharp X68000 | supported | MAME sound and colours on more games; deeper disk-change and save evidence |
| Capcom CPS-2 | supported (since 1.7.0) | more of the 236 sets converted and played; the cause of the three one-picture differences with MAME; a run of the DSP16 |
| PC Engine / TurboGrafx-16 | supported (since 1.7.2) | the window and Linux proof of the player's own record (in 1.7.3), more HuCards |
| PC Engine CD / TurboGrafx-CD | supported (release after 1.9.1) | routes that go further on some discs, the two-PC match, the frame cost past the routes |
| Game Boy Advance | supported (since 1.7.6; experimental from 1.7.0) | a level won on a panel game, the LDM/STM vectors, an independent emulator comparison (G10, G11), the quiet-PC cost of a frame, the cartridge sensors |
| Commodore Amiga 500 | supported (since 1.7.5) | Kickstart 1.2 and 3.x installs, then ADF images; more installs converted and played; route depth past an adventure's opening (Monkey Island 2) |
| Commodore Amiga 1200 | supported (since 1.7.8; experimental from 1.7.6) | AGA super-hires at full detail, the 76 68EC020 vector cases to referee (G10), the frame cost of the display's shortcuts on a quiet PC, a game played on Linux |
| Atari ST | supported (since 1.7.5; shares its paths since 1.7.5) | the Linux half of the sharing, more games played, the Linux play, the STE |
| Nintendo 64 | supported (since 1.7.6; experimental from 1.7.1) | frame pacing on Ocarina of Time timed on a quiet PC, the stick directions on the pad page, the krom families the core fails (G10), a game played on Linux |
| Sony PlayStation | supported (since 1.7.6; experimental from 1.7.1) | 2x and 4x at speed (a threaded or hardware renderer), Metal Gear Solid's and Gran Turismo 2's route depth, the GTE vectors through native steps, mouse, multitap and light guns |
| MSX | supported (since 1.7.5) | route depth on menu-driven games, independent hardware evidence, more cartridges, FM-PAC |
| MSX2 | supported (since 1.7.5) | battery saves shown on an MSX2 game, route depth on menu-driven games, the command engine's timing, independent hardware evidence, FM-PAC |
| MSX2+ | supported (since 1.7.6; experimental from 1.7.4) | route depth (Golvellius II's intro, Pachipro Densetsu's date entry), the Linux half of shared paths, MSX-MUSIC's level on games, independent hardware evidence, FM-PAC |
| SG-1000 | experimental, developer only (stage 3: the conversion delivers a game executable, checked headless against the reference; no player is offered it, no game has been played) | the qualification gates on a small panel, then multiplayer and an optimisation pass |
| ColecoVision | experimental, developer only (stage 3: the conversion delivers a game executable, checked headless against the reference; no player is offered it, no game has been played) | the qualification gates on a small panel, then multiplayer and an optimisation pass |
| Adventure games (ScummVM) | supported (since 1.7.1), emulated and 0 % native | Ogg Vorbis, FLAC and MP3 decoders; more engine families witnessed on Linux |

Each machine's progress through the qualification list, with its bar and percentage, is in the [README](../README.md#console-support) and in
[QUALIFICATION.md](QUALIFICATION.md#progress-through-the-qualification-list): both are generated from the same matrix, so this table does not repeat the figures.
It is not a quality score, and it never decides a status.

## Across all machines

- **The owner's play test (gate G14)** is passed on every machine: the Master System, Game Gear, Game Boy and Super Nintendo
  joined on 5 November 2026.
- **Linux witnesses (gate G13).** The Mega Drive, Super Nintendo, Neo Geo and CPS-1 compare Windows and Linux on a few games
  only; the plan is a small campaign per machine on a Debian 13 PC.
- **Hardware evidence (gate G11)** stays partial on every machine: without measurements of real hardware, comparisons with
  test ROMs and reference emulators are what we can offer, and the reports say so.
- **The shared base.** A converter will send only the paths its base does not know yet, so the online service grows
  slowly between releases.
- **Up to four players: done in 1.9.0.** The consoles' own adapters are modelled in their machines (the NES Four Score, the Mega
  Drive Team Player, EA 4-Way Play and J-Cart, the Super Nintendo Super Multitap, the PC Engine multitap), and every machine plays
  with friends on a local network or over the Internet ([MULTIPLAYER.md](MULTIPLAYER.md)). A fifth player is not offered: a room
  seats four.
- **Shared code.** The Windows/Linux comparison tools and the MAME capture tools of several machines become one module
  each.

## Per machine

### Master System and Game Gear

Next: an evidence lot like the Game Boy's in 1.6.8, with no change to how games convert: the Linux witness, a capture
campaign for liveness and route depth, per-device interpreter counters in the report, an honesty audit of the pages.
Then the six cartridges the "functions" engine still fails on (Action Fighter among them). Later: the Game Gear's sprite
flicker reduction, offered as on the Master System.

### Game Boy

The **Game Boy Color** has its own experimental profile on the same engine since November 2026
([GAME_BOY_COLOR.md](GAME_BOY_COLOR.md)). Next for the Game Boy: the remaining test ROMs (the wave channel read while it plays, the `oam_bug` timing effect) are listed in
[KNOWN_FAILURES.md](KNOWN_FAILURES.md) and have a low priority: no game of the campaigns shows them.

### NES

Next: a broader panel (gate G12) and an honesty pass on the pages (gate G15). Later: more
board variants and RAM-bearing layouts, longer gameplay routes. The Famicom Disk System stays out of scope.

### Mega Drive

Next: the report contract and the Linux witness on more games, a first MAME comparison of the sound, and two open choices
(the colour level table, a WAV recording option). The 22 decimal-arithmetic vectors left (`ABCD`, `SBCD`,
`NBCD` on operands that are not digits) are undefined in the manual; Moira (MIT), the 68000 core of the Amiga's reference
machine, agrees with all 22, so its results are a candidate rule for a later release, once for the four 68000 machines
(Mega Drive, Neo Geo, CPS, X68000) in the shared state rules. Later: the SVP coprocessor (Virtua Racing) as its own stage; Pico, Mega-CD, 32X and lock-on cartridges
stay out of scope.

### Super Nintendo

Next: the Linux witness on more games. Then the DSP-2 and DSP-4 chips (Dungeon Master, Top Gear
3000), then the SPC7110. The Super FX runs as a counted interpreted device; a native Super FX is planned in stages
([SNES_SUPERFX.md](SNES_SUPERFX.md)). Native CX4 and finer CPU phases remain later work.

### Neo Geo

Next: the Linux witness on more games. Fight Fever needs another dump. Other BIOS
revisions, boards and peripherals keep their own scope.

### Capcom CPS-2

Supported since 1.7.0 (experimental in 1.6.9), once the owner's decision is recorded: its own profile built on the CPS-1 and CPS-1.5 modules, with the
68000's encrypted program decrypted by the key file of the player's own romset (keys are never shipped), the CPS-2 object chip and raster effects, and
QSound sound. First scope: the 236 standard boards; the ten spinner and paddle games and the three games with inputs of their own later. Next: more of the
236 sets converted and played, the cause of the three one-picture differences with MAME, and a low-level model of the QSound chip's DSP16, done once for the
CPS-1.5 and the CPS-2.

### Capcom CPS-1 and CPS-1.5

Next: the Linux witness of the QSound games. Then the rotary-dial boards (Forgotten Worlds, Lost Worlds), done together with the
CPS-2's spinner so the two share one input. Later: a low-level model of the QSound sound chip, done once for the CPS-1.5
and the CPS-2. Pang! 3, the CPS Changer cartridges and bootlegs stay out of scope.

### Sharp X68000

The X68000 is supported since 1.6.9, on the owner's decision of 5 November 2026
([QUALIFICATION.md](QUALIFICATION.md#sharp-x68000-evidence-behind-its-column-29-october-2026-status-of-1-november-2026)).
Its gates G10 and G11 stay partial. Next: the sound and the colours compared with MAME on more games, the ten pictures of the
comparison that no picture of the game matches, deeper evidence for disk changes late in a game and for a game that saves on
purpose, and a Linux witness of interactive play. Sound-free routes stay accepted and reported; a Roland MIDI model is not
planned. Hard-disk images stay out of scope. The screen contrast of the system port stays a documented difference with MAME.

### PC Engine

Supported since 1.7.2, on the owner's decision of 10 November 2026; open since 1.6.9 ([PC_ENGINE.md](PC_ENGINE.md)): HuCards of the standard boards and the
Street Fighter II board, NTSC, two players. Next: the player's own record, so the code a player reaches past the routes becomes native at the
next conversion; a play route past a screen confirmed with I (Boxyboy); more HuCards through the same loop. Street Fighter II' CE is native on its routes with the engine's larger capture format, at the cost of a large game and a long
conversion. SuperGrafx is a separate later study; CD-ROM² is [PC Engine CD](PC_ENGINE_CD.md).

### Game Boy Advance

Supported since 1.7.6, on the owner's decision of 14 November 2026 (open as experimental in 1.7.0; [GAME_BOY_ADVANCE.md](GAME_BOY_ADVANCE.md)): `.gba` cartridges with your own BIOS, native code from what each
game was seen to run, the rest interpreted and counted, cartridge saves. Next: the Linux witness, the box-art covers on a first
conversion, the cartridge sensors (tilt, gyroscope, solar) as host inputs, a comparison with an independent emulator (today the agreement is with the engine's own
interpreter) and the cost of a frame on a quiet PC.

### Commodore Amiga 500

Supported since 1.7.5, on the owner's decision of 14 November 2026 (open as experimental in 1.7.0; [AMIGA.md](AMIGA.md)): a pinned machine core (vAmiga, with its 68000 Moira) driven frame by frame, native 68000
steps structured by the shared decoder; games installed for WHDLoad, with no WHDLoad run (its services are answered by our own code). Installs
that ask for a Kickstart 1.3 convert with the player's own image since 1.7.0, and the Kickstart's code runs as guarded native steps since 1.7.1.
Next: Kickstart 1.2 and 3.x installs, then ADF images.

### Atari ST

Supported since 1.7.5, on the owner's decision of 14 November 2026 (open as experimental in 1.7.1; [ATARI_ST.md](ATARI_ST.md)): ST, STF and Mega ST floppy games on Hatari, EmuTOS 1.4 by default or the player's own TOS,
native steps for the 68000 code the reference run saw, the player's record and a sweep of memory. Next: more games through the same loop and a game played on Linux. The STE, TT, Falcon and hard disks are out of scope today.

### Nintendo 64

Supported since 1.7.6, on the owner's decision of 15 November 2026 (open as experimental in 1.7.1; [NINTENDO_64.md](NINTENDO_64.md)): cartridge
images on Mupen64Plus-Next with the ParaLLEl renderer on Vulkan, guarded native blocks for the VR4300 code the reference run saw, KSEG0 and
TLB-mapped. Next: frame pacing on Ocarina of Time timed on a quiet PC, the right stick as rebindable C buttons, and a game played on Linux. The 64DD is out of scope today.

### Sony PlayStation

Supported since 1.7.6, on the owner's decision of 15 November 2026 after his play test (open as experimental in 1.7.1;
[PLAYSTATION.md](PLAYSTATION.md)): discs on Beetle PSX with native R3000A steps for the code the conversion saw run, the CPU state compared
on every frame, shared paths. Next: 2x and 4x at speed (the renderer is software on one thread), the route depth of Metal Gear Solid and Gran Turismo 2,
the GTE vectors through native steps, and the mouse, multitap and light guns, which are out of scope today.

### MSX

Supported since 1.7.5, on the owner's decision of 14 November 2026 (open as experimental in 1.7.3; [MSX.md](MSX.md)): MSX1 cartridges (plain, Konami, Konami SCC, ASCII 8 and ASCII 16) booted by C-BIOS, a free BIOS, or the player's own
BIOS (never shipped), native Z80 code from the shared banked chain. Its panel of eight cartridges was converted again on 14 November 2026 on Windows and on a Debian 13 PC (G1 to G8, G10, G12, G13 and G15 met, [QUALIFICATION.md](QUALIFICATION.md)); path sharing is declined, as it would serve no purpose. Next: route depth on menu-driven games, independent hardware evidence. The turbo R,
cassettes and the FM-PAC are out of scope today; disk games are the MSX2+'s.

### MSX2

Supported since 1.7.5 with the MSX (open as experimental in 1.7.3), the second profile of the family ([MSX.md](MSX.md#8-the-msx2-msx2)): MSX2 cartridges on the V9938 drawn by line, with its command
engine (its timing approximated), a memory mapper and the RP5C01 clock, booted by C-BIOS or the player's own BIOS pair. Its panel of eight cartridges was converted again on 14 November 2026 with the MSX's (the same letters but battery saves, partial). Next: the
command engine's timing, battery saves shown on an MSX2 game. Cassettes and the FM-PAC are out of scope today; the MSX2+ is its own profile.

### MSX2+

Supported since 1.7.6, on the owner's decision of 14 November 2026 after his play test of six games (open as experimental in 1.7.4;
[MSX.md](MSX.md#9-the-msx2-msx2plus)): MSX2+ cartridges and disk games on the V9958 with MSX-MUSIC, your own kanji font as an option, the next
disk given when a game asks, and shared paths (the experimental tier of the base). Its panel of nine was converted on Windows and on a Debian 13
PC with equal fields on every route. Next: route depth on Golvellius II and Pachipro Densetsu, the Linux half of the shared paths and a path
qualified by another player, MSX-MUSIC's level compared on games, independent hardware evidence. Cassettes and the FM-PAC are out of scope today.

### Adventure games (ScummVM)

Supported since 1.7.1 as a category of its own, emulated and 0 % native by design ([SCUMMVM.md](SCUMMVM.md)). Next: Ogg Vorbis, FLAC and MP3 decoders
(games that need CD audio rips or compressed speech), and the witness on Linux of more engine families.

## Planned after that

Six machines close to the hardware already converted are in their study (November 2026), in this order. Each follows the
playbook of [NEW_MACHINE.md](NEW_MACHINE.md): the study is approved first, then an experimental profile, the qualification
list, multiplayer and an optimisation pass. The SG-1000 has its experimental profile since 21 November 2026, for developers only
([SG1000.md](SG1000.md)): it converts cartridges into a game executable for developers, and no player is offered it yet.

| Machine | What is reused | What is new |
| --- | --- | --- |
| SG-1000 | the Z80, the TMS9918A video chip of the MSX, the SN76489 sound chip of the Master System | the board, the pads |
| Game Boy Color | the Game Boy's CPU and engine, which already runs the colour mode | done as an experimental machine (22 November 2026, [GAME_BOY_COLOR.md](GAME_BOY_COLOR.md)): Color-only fixes of the runtime, no boot ROM, the link cable; the owner has not played it |
| ColecoVision | the same three chips as the SG-1000 | the player's BIOS, the keypad controller; its experimental profile has begun for developers (21 November 2026, [COLECOVISION.md](COLECOVISION.md)) |
| Amstrad CPC | the Z80, the AY sound chip of the MSX | the video, the floppy drive, code loaded from disk |
| ZX Spectrum | the Z80, the AY sound chip (128K) | the video, snapshots first (tapes later); study approved 21 November 2026, experimental profile begun ([ZX_SPECTRUM.md](ZX_SPECTRUM.md)) |
| PC Engine CD | the PC Engine's CPU and video, the disc reading of the PlayStation | done (experimental from 21 November 2026, supported on 27 November 2026, [PC_ENGINE_CD.md](PC_ENGINE_CD.md)): the drive, ADPCM and CD audio are the engine's, the player's System Card, code loaded from disc observed on the routes |

This list states intentions, not dates or compatibility promises. Earlier delivery notes are in
[RELEASE_NOTES.md](RELEASE_NOTES.md).

## Improvement loop

We want to explore more paths using a local decision or vision model: observation, input choice, deterministic replay,
guarded compilation and comparison before regeneration. More explored paths do not prove complete gameplay or hardware
fidelity. The current version reuses verified observations and checks candidates; the autonomous exploration loop is not
implemented, and no model weights, API credentials or online-model integration are distributed.
