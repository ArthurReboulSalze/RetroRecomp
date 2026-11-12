# RetroRecomp roadmap

This page says what is planned for each machine, in the order we expect to work on it. It states intentions, not dates or
compatibility promises: a plan can change when evidence says so. Each machine's progress through the common qualification
list is in [QUALIFICATION.md](QUALIFICATION.md); the games that do not convert are in [KNOWN_FAILURES.md](KNOWN_FAILURES.md).

Five measures stay separate in every step below: native code, CPU fidelity, hardware fidelity, gameplay validation and
physical latency. Native execution alone guarantees neither complete compatibility nor zero latency, and the interpreter
fallback stays counted and shown wherever it is used.

## Where things stand (1.7.1, November 2026)

| Machine | Status | Next step |
| --- | --- | --- |
| Master System | supported | the evidence lot below |
| Game Gear | supported | the evidence lot below |
| Game Boy | supported | Game Boy Color as a profile of its own |
| NES | supported | broader panel |
| Mega Drive | supported | report and Linux witness; MAME sound comparison |
| Super Nintendo | supported | Linux witness; DSP-2 and DSP-4 |
| Neo Geo | supported | Linux witness on more games |
| Capcom CPS-1 | supported | rotary-dial boards; the Z80 interrupt-mode-0 opcode has been counted since 1.6.5 |
| Capcom CPS-1.5 (QSound) | supported, with the CPS-1 (since 5 November 2026) | Linux witness of the QSound games; a run of the DSP16 |
| Sharp X68000 | supported | MAME sound and colours on more games; deeper disk-change and save evidence |
| Capcom CPS-2 | supported (since 1.7.0) | more of the 236 sets converted and played; the cause of the three one-picture differences with MAME; a run of the DSP16 |
| PC Engine / TurboGrafx-16 | supported (since 1.7.2) | the player's own record, a play route past a screen confirmed with I, more HuCards |
| Game Boy Advance | experimental (since 1.7.0) | covers on the next deliveries, the LDM/STM vectors, an independent emulator comparison |
| Commodore Amiga 500 | experimental (since 1.7.0) | Kickstart 1.2 and 3.x installs, then ADF images; more installs converted and played; the Linux witness of a Kickstart install |
| Atari ST | experimental (since 1.7.1) | the cause of Kick Off 2's stop on its protected tracks, more games played, the Linux play, the STE |
| Nintendo 64 | experimental (since 1.7.1) | frame pacing on Ocarina of Time, independent processor vectors, more games played, the Linux play |
| Sony PlayStation | experimental (since 1.7.1) | the owner's play of the panel discs, more discs, the Linux witness on more than one disc |
| MSX | experimental, in development (not in a release yet) | the panel and its qualification, MSX2, disks, FM-PAC and SRAM, the Linux witness |
| MSX2 | experimental, in development (not in a release yet) | stage 7 (the V9938 command engine, timing approximated) is done; next stage 8, the panel on Windows, then its qualification, disks, FM-PAC, MSX2+, the Linux witness |
| Adventure games (ScummVM) | supported (since 1.7.1), emulated and 0 % native | Ogg Vorbis, FLAC and MP3 decoders; more engine families witnessed on Linux |
| MSX (MSX1 and MSX2) | in development, not in a release | experimental in the next release: MSX1 and MSX2 together, cartridges only |

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
- **Up to four players (and five), planned for 1.7.** The common host kit already takes four players with their own keys and
  pads, and the CPS boards use them. The consoles' own multiplayer adapters come next, each modelled in its machine: the NES
  Four Score, the Mega Drive Team Player and EA 4-Way Play, the Super Nintendo Super Multitap (five players, like the PC Engine
  multitap), with the kit passing every player's pad to the machine.
- **Shared code.** The Windows/Linux comparison tools and the MAME capture tools of several machines become one module
  each.

## Per machine

### Master System and Game Gear

Next: an evidence lot like the Game Boy's in 1.6.8, with no change to how games convert: the Linux witness, a capture
campaign for liveness and route depth, per-device interpreter counters in the report, an honesty audit of the pages.
Then the six cartridges the "functions" engine still fails on (Action Fighter among them). Later: the Game Gear's sprite
flicker reduction, offered as on the Master System.

### Game Boy

Next: the **Game Boy Color** as a profile of its own: the pinned engine already runs the
Color mode, but its timing tests do not all pass yet in that mode, and Color-only cartridges stay refused until then.
The remaining test ROMs (the wave channel read while it plays, the `oam_bug` timing effect) are listed in
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
conversion. SuperGrafx and CD-ROM² are separate later studies.

### Game Boy Advance

Experimental since 1.7.0 ([GAME_BOY_ADVANCE.md](GAME_BOY_ADVANCE.md)): `.gba` cartridges with your own BIOS, native code from what each
game was seen to run, the rest interpreted and counted, cartridge saves. Next: the Linux witness, the box-art covers on a first
conversion, the cartridge sensors (tilt, gyroscope, solar) as host inputs, a comparison with an independent emulator (today the agreement is with the engine's own
interpreter) and the owner's decision, which alone ends the experimental status.

### Commodore Amiga 500

Experimental since 1.7.0 ([AMIGA.md](AMIGA.md)): a pinned machine core (vAmiga, with its 68000 Moira) driven frame by frame, native 68000
steps structured by the shared decoder; games installed for WHDLoad, with no WHDLoad run (its services are answered by our own code). Installs
that ask for a Kickstart 1.3 convert with the player's own image since 1.7.0, and the Kickstart's code runs as guarded native steps since 1.7.1.
Next: Kickstart 1.2 and 3.x installs, then ADF images.

### Atari ST

Experimental since 1.7.1 ([ATARI_ST.md](ATARI_ST.md)): ST, STF and Mega ST floppy games on Hatari, EmuTOS 1.4 by default or the player's own TOS,
native steps for the 68000 code the reference run saw. Next: the cause of Kick Off 2's stop, more games through the same loop, the owner's play
trials and a game played on Linux. The STE, TT, Falcon and hard disks are out of scope today.

### Nintendo 64

Experimental since 1.7.1 ([NINTENDO_64.md](NINTENDO_64.md)): cartridge images on Mupen64Plus-Next with the ParaLLEl renderer on Vulkan, guarded
native blocks for the VR4300 code the reference run saw. Next: frame pacing on Ocarina of Time, independent processor vectors, more games and
a game played on Linux. The 64DD is out of scope today.

### Sony PlayStation

Experimental since 1.7.1 ([PLAYSTATION.md](PLAYSTATION.md)): discs on Beetle PSX with native R3000A steps for the code the conversion saw run. Next:
the owner's play of the panel discs, more discs, the Linux witness beyond one disc, and the mouse, multitap and light guns, which are out of scope today.

### MSX

In development as an experimental profile ([MSX.md](MSX.md)): MSX1 cartridges (plain, Konami, Konami SCC, ASCII 8 and ASCII 16) booted by C-BIOS or the player's own
BIOS, native Z80 code from the shared banked chain. Next: a panel of games and its qualification, the owner's play, the Linux witness, quick states. MSX2+ and the turbo R,
disks, cassettes, FM-PAC and the SRAM mappers are out of scope today.

### MSX2

In development as a second experimental profile of the family ([MSX.md](MSX.md#8-the-msx2-msx2)): MSX2 cartridges on the V9938 drawn by line, a memory mapper and the
RP5C01 clock, booted by C-BIOS or the player's own BIOS pair. The V9938 command engine (stage 7) is done, timing approximated. Next: stage 8, the panel on Windows, then its qualification, the owner's play, the
Linux witness. Disks, cassettes, FM-PAC and MSX2+ are out of scope today.

### Adventure games (ScummVM)

Supported since 1.7.1 as a category of its own, emulated and 0 % native by design ([SCUMMVM.md](SCUMMVM.md)). Next: Ogg Vorbis, FLAC and MP3 decoders
(games that need CD audio rips or compressed speech), and the witness on Linux of more engine families.

## In development

### MSX (MSX1 and MSX2)

Not in 1.7.3. The MSX1 and the MSX2 are planned to open together as an experimental machine in the next release, cartridges only.
A cartridge runs on C-BIOS, a free BIOS, by default, or on the player's own MSX BIOS (never shipped). Disks come later;
tapes are not planned. Nothing is claimed yet of its native code, CPU fidelity, hardware fidelity, gameplay or latency: each is
measured and stated apart once the machine opens, with the interpreter fallback counted as on every machine.

## Planned after that

- Amiga 1200 AGA (WHDLoad-based)

This list states intentions, not dates or compatibility promises. Earlier delivery notes are in
[RELEASE_NOTES.md](RELEASE_NOTES.md).

## Improvement loop

We want to explore more paths using a local decision or vision model: observation, input choice, deterministic replay,
guarded compilation and comparison before regeneration. More explored paths do not prove complete gameplay or hardware
fidelity. The current version reuses verified observations and checks candidates; the autonomous exploration loop is not
implemented, and no model weights, API credentials or online-model integration are distributed.
