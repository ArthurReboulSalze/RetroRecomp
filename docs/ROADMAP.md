# RetroRecomp roadmap

This page says what is planned for each machine, in the order we expect to work on it. It states intentions, not dates or
compatibility promises: a plan can change when evidence says so. Each machine's progress through the common qualification
list is in [QUALIFICATION.md](QUALIFICATION.md); the games that do not convert are in [KNOWN_FAILURES.md](KNOWN_FAILURES.md).

Five measures stay separate in every step below: native code, CPU fidelity, hardware fidelity, gameplay validation and
physical latency. Native execution alone guarantees neither complete compatibility nor zero latency, and the interpreter
fallback stays counted and shown wherever it is used.

## Where things stand (1.6.8, November 2026)

| Machine | Status | Qualification progress | Next step |
| --- | --- | --- | --- |
| Master System | supported | 63 % | the evidence lot below |
| Game Gear | supported | 60 % | the evidence lot below |
| Game Boy | supported | 91 % | owner play test; Game Boy Color as a profile of its own |
| NES | supported | 91 % | broader panel |
| Mega Drive | supported | 84 % | report and Linux witness; MAME sound comparison |
| Super Nintendo | supported | 88 % | owner play test, Linux witness; DSP-2 and DSP-4 |
| Neo Geo | supported | 94 % | Linux witness on more games |
| Capcom CPS-1 | supported | 90 % | count every Z80 step; rotary-dial boards |
| Capcom CPS-1.5 (QSound) | experimental tier of the CPS-1 | — | owner play test |
| Sharp X68000 | supported | 93 % | MAME sound and colours on more games; deeper disk-change and save evidence |

The progress figure is the share of the qualification gates that are met (half a point for a partial one). It is not a
quality score, and it never decides a status.

## Across all machines

- **The owner's play test (gate G14).** The Master System, Game Gear, Game Boy and Super Nintendo still wait for it.
- **Linux witnesses (gate G13).** The Mega Drive, Super Nintendo, Neo Geo and CPS-1 compare Windows and Linux on a few games
  only; the plan is a small campaign per machine on a Debian 13 PC.
- **Hardware evidence (gate G11)** stays partial on every machine: without measurements of real hardware, comparisons with
  test ROMs and reference emulators are what we can offer, and the reports say so.
- **The shared base.** A converter will send only the paths its base does not know yet, so the online service grows
  slowly between releases.
- **The common host kit.** A five-player adapter (PC Engine multitap, Super Nintendo multitap) is planned; today the kit
  takes four players.
- **Shared code.** The Windows/Linux comparison tools and the MAME capture tools of several machines become one module
  each.

## Per machine

### Master System and Game Gear

Next: an evidence lot like the Game Boy's in 1.6.8, with no change to how games convert: the Linux witness, a capture
campaign for liveness and route depth, per-device interpreter counters in the report, an honesty audit of the pages.
Then the six cartridges the "functions" engine still fails on (Action Fighter among them). Later: the Game Gear's sprite
flicker reduction, offered as on the Master System.

### Game Boy

Next: the owner's play test. Then the **Game Boy Color** as a profile of its own: the pinned engine already runs the
Color mode, but its timing tests do not all pass yet in that mode, and Color-only cartridges stay refused until then.
The remaining test ROMs (the wave channel read while it plays, the `oam_bug` timing effect) are listed in
[KNOWN_FAILURES.md](KNOWN_FAILURES.md) and have a low priority: no game of the campaigns shows them.

### NES

Next: a broader panel (gate G12) and an honesty pass on the pages (gate G15). Later: more
board variants and RAM-bearing layouts, longer gameplay routes. The Famicom Disk System stays out of scope.

### Mega Drive

Next: the report contract and the Linux witness on more games, a first MAME comparison of the sound, and two open choices
(the colour level table, a WAV recording option). The 22 decimal-arithmetic vectors left are undefined in the manual and
stay as they are. Later: the SVP coprocessor (Virtua Racing) as its own stage; Pico, Mega-CD, 32X and lock-on cartridges
stay out of scope.

### Super Nintendo

Next: the owner's play test and the Linux witness on more games. Then the DSP-2 and DSP-4 chips (Dungeon Master, Top Gear
3000), then the SPC7110. The Super FX runs as a counted interpreted device; a native Super FX is planned in stages
([SNES_SUPERFX.md](SNES_SUPERFX.md)). Native CX4 and finer CPU phases remain later work.

### Neo Geo

Next: the Linux witness on more games. Fight Fever needs another dump. Other BIOS
revisions, boards and peripherals keep their own scope.

### Capcom CPS-1 and CPS-1.5

Next: count every instruction the Z80 runs on the reference core (one interrupt mode is not counted yet), and the owner's
play test of the QSound games. Then the rotary-dial boards (Forgotten Worlds, Lost Worlds), done together with the
CPS-2's spinner so the two share one input. Later: a low-level model of the QSound sound chip, done once for the CPS-1.5
and the CPS-2. Pang! 3, the CPS Changer cartridges and bootlegs stay out of scope.

### Sharp X68000

The X68000 is supported since 1.6.9, on the owner's decision of 5 November 2026
([QUALIFICATION.md](QUALIFICATION.md#sharp-x68000-evidence-behind-its-column-29-october-2026-status-of-1-november-2026)).
Its gates G10 and G11 stay partial. Next: the sound and the colours compared with MAME on more games, the ten pictures of the
comparison that no picture of the game matches, deeper evidence for disk changes late in a game and for a game that saves on
purpose, and a Linux witness of interactive play. Sound-free routes stay accepted and reported; a Roland MIDI model is not
planned. Hard-disk images stay out of scope. The screen contrast of the system port stays a documented difference with MAME.

## Machines in development

Each new machine starts as an experimental profile, follows [NEW_MACHINE.md](NEW_MACHINE.md), and leaves that status only
on the owner's decision after the qualification list.

- **Capcom CPS-2.** Its own experimental profile built on the CPS-1 and CPS-1.5 modules: the 68000's encrypted program,
  decrypted with the key file of the player's own romset (keys are never shipped), the CPS-2 sprite chip and raster
  effects, QSound sound. First scope: the standard boards; spinner and paddle games later.
- **PC Engine / TurboGrafx-16.** HuCards first, on a pinned open recompiler we contribute to upstream; SuperGrafx and
  CD-ROM² later, with the player's own System Card.
- **Game Boy Advance.** A pinned recompiler with a host adapter of our own; the player's own BIOS; cartridge saves and the
  real-time clock first, sensors (tilt, gyroscope, solar) later.

## Planned after that

- Atari ST
- Amiga 500 (WHDLoad-based)
- Amiga 1200 AGA (WHDLoad-based)
- Nintendo 64
- PlayStation

This list states intentions, not dates or compatibility promises. Earlier delivery notes are in
[RELEASE_NOTES.md](RELEASE_NOTES.md).

## Improvement loop

We want to explore more paths using a local decision or vision model: observation, input choice, deterministic replay,
guarded compilation and comparison before regeneration. More explored paths do not prove complete gameplay or hardware
fidelity. The current version reuses verified observations and checks candidates; the autonomous exploration loop is not
implemented, and no model weights, API credentials or online-model integration are distributed.
