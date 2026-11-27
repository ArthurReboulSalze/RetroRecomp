# ZX Spectrum

Status: **supported** since 1.10.0, on the owner's play test of 27 November 2026 (section 6). The machine
opened on 21 November 2026 as an experimental, developer-only profile; every installation now lists it. This page says what
the machine converts, what it leaves out, and how the five measures stay apart.

## 1. Scope

| Converted | Later | Left out for now |
|---|---|---|
| Snapshots of the 16K, 48K and 128K (and the +2, a 128K with another menu ROM): `.z80` versions 1, 2 and 3 and `.sna` (48K and 128K), from a file or a ZIP holding exactly one | `.szx` snapshots; the +2A and +3 (another contention pattern, port 1FFDh, the +3 disk) | Tapes (`.tap`, `.tzx`): their loaders need exact EAR timing, and a snapshot skips every loader; the Interface 1 and Microdrive, the Timex, Pentagon, Scorpion and other clones, the ZX80 and ZX81 |
| The ULA picture (256 x 192, attributes, flash, the border per line), the beeper, the AY-3-8910 on the 128K, the keyboard, the Kempston and Sinclair Interface 2 joysticks, quick states, the ULA's contention and the floating bus | Border and paper changes within a line (each line is drawn at its end) | Games that load their next level from tape during play: a snapshot cannot; they stop at that load, and the report says so |

A snapshot is the machine's RAM and registers at one moment, saved after the game had loaded. The reader
(`retrorecomp/zxs_snapshot.py`, our own code from the public format descriptions) refuses, with a sentence, a snapshot of a
machine the converter does not model, one taken with the Interface 1 or TR-DOS ROM paged in, one that carries a ROM of its
own, and any file whose memory blocks do not decode to whole 16 KiB pages.

## 2. The route

The Z80 is translated by the shared banked Z80 chain of the Master System and the MSX (`retrorecomp/z80_chain.py`, the
pinned smsggrecomp generator and z80-recomp-core), on a machine description of the Spectrum's own; what is not translated
runs on the reference interpreter (superzazu/z80), counted. The ULA, the beeper, the 128K paging and the snapshot reader are
our own MIT code, written with floooh/chips (zlib) and Clock Signal (MIT) as written references only; the AY-3-8910 is the
MSX's model, made shared. No GPL code goes into a Spectrum game: Fuse, libspectrum, ZEsarUX and MAME's Spectrum driver are
references and external checks only. This is the maintainer's choice of 21 November 2026 (route A).

## 3. The ROM

A snapshot holds no ROM, yet the game calls the ROM's routines and its interrupt runs the ROM's handler: every converted
Spectrum game holds the ROM of its model, translated with it. The ROMs are Amstrad's copyright, redistributed under
Amstrad's permission for emulators of 31 August 1999 (no charge for the ROM code, copyright messages unaltered;
[zx-spectrum-roms.md](../licenses/zx-spectrum-roms.md)). On the maintainer's choice of 21 November 2026:

- by default the converter fetches `48.rom`, `128-0.rom` and `128-1.rom` once from a pinned source (the `roms/` folder of the
  Fuse project, at one commit) and checks the size and SHA-256 of each on every use (`retrorecomp/zxs_roms.py`); nothing of them
  is in Retro-Recomp's repository or installer;
- a player may give their own ROM in **Options → ZX Spectrum** instead (the 48K ROM, and the 128K ROM as one 32 KiB image or
  its editor ROM with the BASIC ROM beside it). It is accepted when its SHA-256 is the one of the same images, so the game
  is the same either way; Options' « Find firmware in a folder… » looks for these files too.

## 4. A conversion

`retrorecomp/zxs_conversion.py`, on the MSX's pattern:

1. The snapshot is read and turned into the machine image (`retrorecomp/zxs_build.py`: the model, the ports, the registers, the
   T-state, the RAM banks); the ROM of its model comes from `zxs_roms`.
2. How the play route starts is chosen on the reference (`route_start`, `retrorecomp/zxs_routes.py`): ENTER, SPACE, 0, 1, 5 or
   pad 1's fire pressed one to four times, or one of these keys then fire (each press held half a second: some titles read their
   key only between two notes of a tune), judged against the route without input. A snapshot whose start the search cannot find
   has reviewed start data instead (`retrorecomp/zxs_starts.py`, keyed by its SHA-256: the presses and why, found on the
   reference, played and checked like any route; the report names them). Then a deterministic walk on the controls the snapshot
   was saved for (cursor keys, Kempston or Sinclair Interface 2); a game whose own menu chose other keys does not answer it.
   When a game's menu uses another interface than the snapshot's header says, reviewed data names it (`zxs_starts.JOYSTICKS`,
   by SHA-256, found by holding each key and Kempston bit in play on the reference): the image, the pads and the routes follow
   it, and the report says why (`zxs_checks.joystick_rule`). Head over Heels reads Interface 2 (6-0); Match Day II's start
   picks « Kempston joystick » in its menu, which waits for ever unless a Kempston answers at port 1Fh. A game that polls the
   Fuller joystick's port (7Fh) though no Fuller is chosen gets a Fuller box present and idle, reading FFh (`zxs_starts.FULLER_IDLE`,
   image byte 31): Match Day II reads it every frame, and floating, its screen bytes moved the menu's cursor with no key held.
3. The ROM is translated ahead of time on the shared chain; the code the snapshot runs from RAM is learned over the routes
   and translated with byte guards (`zxs_build.learn`, up to three passes).
4. Every route is run natively and on the reference interpreter (the same machine, every instruction interpreted): the
   report fields (CPU, RAM, picture, sound, interrupts) and every frame's row must be equal, or nothing is built.
5. The game is built (`native/zxs_machine/zxs_player.c` and the host kit's computer adapter `rrhk_zxs.inc`), its compressed
   copy replayed headless on every route against the reference, and its quick states (F8, F9) checked in fresh processes,
   damaged copies refused.

The first game, Manic Miner (48K), on 21 November 2026: the play route starts with ENTER pressed twice and reaches Central
Cavern; on the attract and play routes (1,800 frames each) 6,919,640 Z80 instructions ran natively and **none on the
interpreter fallback**; the native runs, the build and its compressed copy
equal the reference on every compared field and frame row; a quick state saved at frame 1,140 continues the route for 600
frames in a fresh process. That is agreement between our native code and our reference interpreter on these routes, not a
proof of CPU fidelity against an independent Z80 or of hardware fidelity (below).

## 5. The five measures

Native code, CPU fidelity, hardware fidelity, gameplay validation and physical latency are kept apart in the report, the
interface and this page. The report counts the interpreter fallback per route in Z80 instructions and cycles (as on the
MSX), says that the native code agrees with the reference interpreter, and leaves CPU fidelity, hardware fidelity, gameplay
validation and physical latency as not validated or not measured.

**The ULA's memory contention is modelled; what it rests on is stated.** On a real Spectrum the CPU is held off when it touches
4000h-7FFFh (and, on the 128K, the odd RAM banks paged at C000h) while the ULA fetches the paper, by 6, 5, 4, 3, 2, 1, 0 or 0 T-states
by the moment within the first 128 T-states of each of the 192 paper lines, from T-state 14335 of the frame (48K, 224 a line) or
14361 (128K, 228 a line); an I/O cycle is held by the four documented cases of its high byte and bit 0. The machine's rule
(`zxs_contend_memory`, `zxs_contend_io`, native/zxs_machine/zxs_machine.c) is checked against those documented numbers
(tools/zxs_machine_selftest.py); the chain's evaluator (`Z80Machine.contention`, retrorecomp/z80_timed.py) asks it for every bus
cycle of every instruction, acceptance and HALT, natively and on the reference alike, from the bus-cycle table checked against
the SingleStepTests vectors. What is not claimed: the pattern is the documented one, not measured on a real Spectrum here; the
refresh cycles are not contended; the +2A/+3 (another pattern) are out of scope.

**The floating bus is modelled from the documented fetch timing.** An unattached port reads what the ULA is fetching: in each 8
T-states of the first 128 of a paper line the bitmap byte, its attribute, the next bitmap byte, the next attribute, then FFh four
times; FFh outside the paper; the first fetch at T-state 14347 (48K) or 14368 (128K), from Ramsoft's floating bus guide (Clock
Signal, MIT, agrees on the 48K and is about 5 T-states later on the 128K: unverified). The I/O cycle samples the bus at its end,
4 T-states after its start and its contention (`ZXS_FLOATING_SAMPLE`); the chain's evaluator gives the machine that moment before
the read, natively and on the reference alike (`zxs_floating_bus`, 23 checks in tools/zxs_machine_selftest.py). Arkanoid, which the guide names as depending
on it, now plays its first round on the play route (297 distinct pictures, bricks broken) where without it the picture froze
after frame 1,409. Not measured on a real Spectrum here.

Research note (22 November 2026, settled for the 48K on 27 November): the moment an IN samples the floating bus was first taken
from Ramsoft's guide (3 T-states into the I/O cycle, after its contention); Clock Signal samples at the cycle's end, one T-state
later. MAME 0.289 (a private oracle, never in a game) settled it on Arkanoid, from the same snapshot with the same inputs: its
raster loop (8490h-84D4h: it writes the screen at 401Fh, then reads port 28FFh until four FFh in a row) lasts the whole paper in
MAME, and with 3 T-states it read bitmap bytes where MAME reads attributes, met four FFh after about 30 lines and ran the game
loop twice a frame (two keyboard reads a frame against MAME's one). Sampled at the cycle's end, the loop and the paddle match MAME
frame for frame (section 6b). The 128K's first fetch (14368) remains the guide's and unverified: no panel game reads the floating
bus on the 128K. What the panel's games read on unattached ports, over their play routes: Arkanoid reads port FFh 140,074 times (its
deliberate use of the floating bus); Manic Miner sweeps the 256 ports ending in 1Fh once, just after its start key, with no Kempston
present (75 of them read screen bytes; the game plays on); Head over Heels reads 1Fh once without a Kempston (FFh, in the border);
Match Day II polled the Fuller port every frame (now given an idle Fuller box); the others read none.
Nothing claims exact timing. With contention, Manic Miner's play route runs 19 % fewer instructions in its 2,100 frames than
without it, and Head over Heels' 8 %.

**Known limits of the machine (27 November 2026, found against MAME 0.289, section 6).**

- **Lines are drawn at their end.** The ULA draws each line, border and paper, when the line ends, not byte by byte as the beam
  passes. A byte that a game writes while the beam crosses it therefore shows one line later than on a beam-position model. On
  the panel this gives tears of 1 to 92 pixels in one or two rows, on isolated frames (never more than three in a row), and they
  do not add up. The game's code, timing and RAM are not affected: only what a frame shows.
- **A snapshot without a frame position starts at the end of the interrupt.** A `.z80` version 1 or 2 and a `.sna` do not say
  where in the frame they were taken. We start 32 T-states into the frame on the 16K and 48K, and 36 on the 128K
  (`zxs_build.INT_END`). A `.z80` version 3 gives its T-state counter, and it is used. MAME starts elsewhere, so a game that
  seeds its random numbers from the R register or from the timing makes other random choices than in MAME:
  - Jetpac's aliens part from MAME's after frame 368;
  - The Hobbit's story parts at frame 709.

  Neither start is hardware-proven, so ours is kept. The game plays either way.
- **A snapshot can hold a program that does not go on.** Elite's snapshot halts with interrupts disabled about 50 frames in,
  inside its own decryption, in MAME 0.289 as here. The conversion still builds the game; its report says the route stopped
  (`route_stop`), and the title never animates. Another snapshot of the same game may run.
- **Code past the routes stays interpreted, and the game keeps no record of it.** What a player reaches beyond the conversion's
  routes runs on the interpreter fallback, counted and shown in the game. Its runtime-feedback kind is 28 (reserved); its games
  record nothing: the F12 row stays OFF. What a conversion learns comes from its own routes, as on the MSX, so a new conversion
  does not make that code native. A deeper scan level does (section 6 has the measure).
- **Paths are not shared between players** (gate G16, declined on its measure: section 6).

## 6. Qualification

The machine's column of [QUALIFICATION.md](QUALIFICATION.md), as read for the exit on 27 November 2026 (the evidence is in its
entries there):

| Gates | Reading |
|---|---|
| G2 to G6, G10, G12, G13, G14 | `Y` |
| G1 (status) | `P`: the profile, this page, the Options tab and the README's status table say supported; COMPATIBILITY's paragraph is written with the release's pages |
| G8 (liveness) | `P`: seven of the eight panel games animate to the end of their play route; Elite's snapshot halts (section 5) |
| G9 (route depth) | `P`: random routes, and an 18,000-frame route on four games; no game was played to its end |
| G11 (hardware evidence) | `P`: agreement with MAME 0.289 (below); no real Spectrum |
| G15 (honesty) | `P`: this page, the Options notes and the reports were read again after the exit; the release's README and COMPATIBILITY text is still to be read |
| G7 (saves) | `-`: a snapshot has no cartridge or battery save |
| G16 (shared paths) | `-`: declined on its measure (below) |

**The exit (27 November 2026).** The owner played the delivered games from `Export\Games\ZX Spectrum` on his gamepad and said:
« Je viens de tester Arkanoïd et c'est parfait aussi. Bien joué. Je passe le G14 pour le Spectrum. » He decided the same day that
the machine leaves the experimental status in this release. It is his acceptance, not a gameplay validation of each game, and
physical latency was not measured.

**Path sharing is declined (G16 `-`), on this measure.** A path received from another player can only make native what a
conversion leaves on the interpreter. So each of the six delivered games replayed, on the native code its Standard conversion
learned, the two 18,000-frame long routes that the Extended and Thorough levels add:

| Game | Interpreted on long route 1 | Interpreted on long route 2 |
|---|---|---|
| Arkanoid | 149 of 164.9 million instructions (under 0.001 %) | 27 of 163.7 million (under 0.001 %) |
| Robocop | 934 of 93.3 million (0.001 %) | 67,741 of 129.2 million (0.052 %) |
| Jetpac | 14,063 of 137.5 million (0.010 %) | 15,707 of 137.4 million (0.011 %) |
| Manic Miner | 34,419 of 87.8 million (0.039 %) | 45,726 of 85.1 million (0.054 %) |
| Match Day II | 125,934 of 152.6 million (0.082 %) | 97,872 of 152.0 million (0.064 %) |
| Head over Heels | 119,537 of 134.3 million (0.089 %) | 118,060 of 133.1 million (0.089 %) |

At most 0.089 % of the instructions ran on the interpreter. Under the owner's rule of 14 November 2026 (sharing that adds nothing
useful is not kept; the Nintendo 64 was declined at 2.3 % to 11.5 %), the Spectrum does not share its paths
(`DECLINED['path_sharing']`). Two limits of this measure: the routes are random walks, not a player going through a game's
levels; and the check programs of Head over Heels and Match Day II are those of 22 November.

The panel of the study, used for the gates: Manic Miner (the first game: 48K, the beeper, the ROM's
interrupt handler), Jetpac (16K), Arkanoid (the floating bus question), Match Day II (two players), Head over Heels (128K
paging and the AY), Robocop (the whole game in the 128K banks, sampled speech), Elite (heavy maths, the keyboard as the
controller), The Hobbit (typing and printing through the ROM); in reserve Uridium and Rainbow Islands.

The panel (22 November 2026, standard level, play route of 2,100 frames): the eight games equal the reference on every route
with no instruction on the interpreter fallback. Manic Miner, Jetpac, Head over Heels and The Hobbit reach play through the
variant search; Robocop, Arkanoid and Match Day II through reviewed start data (a control menu then a typed screen; ENTER then
fire; ENTER four times). Elite does not: about 50 frames after its snapshot the program halts with interrupts disabled inside
its own decryption, on the reference as natively, so its title never animates, and its report says so (`route_stop`). This is
agreement with our reference, on routes that reach part of each game: no gameplay validation.

With the ULA's contention (the same day, standard level): the eight games convert again with no instruction on the fallback,
native equal to the reference on every route, the compressed copy equal and the quick states checked in a fresh process; the same
seven reach play, the CPU now held off as the documented pattern says (Manic Miner's play route runs 19 % fewer instructions in its
2,100 frames, Head over Heels' 8 %). Elite halts the same way with contention (40,981 instructions), and again with the floating
bus: neither is its cause; a snapshot taken inside its loader stays open.

The first Linux witness, the same day, in WSL (Debian 13) on the build PC: Manic Miner and Head over Heels converted from the
same tree give the same start, the same learning counts and, on both routes, the same frame trace, RAM, picture and sound
hashes and step counts as on Windows; the compressed copy and the quick states pass there too. A witness in WSL is not a proof
of a Linux graphics driver.

Against MAME 0.289 (27 November 2026). MAME is a private oracle and is never put in a game. Each panel game was replayed from the
same snapshot with the same route and the same peripherals. The paper was compared on every frame of the 2,100-frame play route.
- Manic Miner: 2,043 of 2,099 frames identical.
- Match Day II: identical from frame 1,082 to the end; the frames that differ are all in its menus.
- Head over Heels: 1,958 of 2,098 frames identical.
- Elite halts in MAME too: the same HALT with interrupts disabled, the same registers, byte-identical RAM at frame 300. Its stop
  is in the snapshot.
- Robocop and Arkanoid: see section 6b.

The few frames that differ do so by a row or two. Our ULA draws each paper row at the end of its line, so a byte the game writes
while the beam passes shows one line later than in MAME (traced on Jetpac, frame 168).

Two recorded differences are not adopted, because nothing decides between the two conventions without hardware:
- **Start phase.** A `.z80` version 1 gives no position in the frame, and we start at the end of the interrupt. Jetpac seeds its
  random numbers from the R register, so its aliens part from MAME's after frame 368. With MAME's R moved by 114, it is identical
  on 1,610 of 2,099 frames.
- **The Hobbit.** It makes another random choice at frame 709 (« Thorin waits » here, Thorin sings about gold in MAME). Its seed
  differs in RAM from the start key at frame 150, and no start phase of ours from 0 to 480 T-states reproduces MAME's.

This is agreement with a second emulator (G11 `P`), not hardware proof.

## 6b. Controls of two panel games (27 November 2026, after the owner's first play)

- **Arkanoid** reads the keyboard (left: the half-row Caps Shift to V; right: B to M and Space; fire: A to L, not redefinable) and
  Sinclair Interface 2 on keys 1-5 (1 left, 2 right, 5 fire); it reads the Kempston port once at its start and uses no Kempston
  here (the snapshot declares none). ZXDB lists Interface 2 and Kempston as its joysticks, and no mouse: the Spectrum had mice
  (AMX, Kempston mouse), but this game reads none, so the kit's mouse has nothing to drive. The pad is Interface 2's 1-5.
  - **The paddle is faster towards the ball.** This is the game's code (read on 27 November 2026, after the owner found right
    faster than left). The game keeps the paddle's speed at 94BAh. Each frame, a routine at 8EEAh compares the paddle's centre
    (its x, 94B8h, plus 10) with the x of the lowest ball. While a direction is held:
    - towards the ball, the speed starts at 4 pixels a frame and grows by 1 every frame (8DFFh for left, 8E1Ch for right);
    - away from the ball, the speed is 2.

    So with the ball on the right, a right press moves 4, 5, 6 pixels in its first frames and then 2 once the paddle passes the
    ball, while left moves 2. With the ball on the left, it is the other way round (measured: −4, −5, −6, then −2; right +2).
    A ball resting on the paddle before a launch sits right of the centre, and it moves with the paddle. So before every launch,
    right keeps accelerating (4, 5, 6 … 13 pixels a frame up to the wall) and left stays at 2. That is the asymmetry a player
    sees most.
  - **The ball leaves the paddle by itself.** With no input at all, the ball appears on the paddle (frame 1,325 of the play
    route) and is launched at frame 1,535, about 4.2 seconds later at 50 frames a second. It leaves at the same frame whether
    the paddle is held left, held right or not moved, and MAME 0.289 launches it at the same frame. A player who moves during
    those seconds sees the ball go as if the move had fired it (the owner's report of 27 November); no fire key is pressed.
  - **Checked on the pad path and against MAME 0.289** (27 November 2026). Same snapshot, the ball in flight, the paddle and
    the speed read every frame:
    - MAME 0.289 with Interface 2's 1 and 2 held (the pad's keys) and with Z and M gives the same positions as ours, one frame
      apart as everywhere on this machine (section 6).
    - A scratch build of the delivered game (never shipped) attached an SDL virtual pad. Through the kit's shell and this
      adapter, the left stick, the d-pad and both together press key 1 alone for left and key 2 alone for right. No other
      half-row, no Kempston and no player 2. The speeds are those above.

    The pad path is pinned by `tests/test_zx_spectrum.py` (the adapter's table is the routes' table, one key a direction).
  - **A second, adversarial pass** (27 November 2026, on the owner's word that right stayed faster in flight). A scratch build
    of the delivered game played three sessions of 6,500 frames with a virtual left stick (random holds while the ball is high,
    tracking when it comes down). Over 15,633 logged frames:

    | Ball in play | Stick left | Stick right |
    |---|---|---|
    | left of the paddle's centre | mean 6.2 pixels a frame, up to 17 (1,195 frames) | 2 pixels a frame, always (1,462 frames) |
    | right of the paddle's centre | 2 pixels a frame, always (2,383 frames) | mean 6.3 pixels a frame, up to 15 (1,128 frames) |

    The fast side is under 4 pixels on 2 to 5 % of its frames, when the ball has just crossed the centre. The ball's height
    changes nothing. The same sessions show:
    - the move routine runs once a frame: one read of each key port in each of the 14,828 play frames, and the paddle never
      moves by anything but its stored speed;
    - the stick presses key 1 or key 2 alone, on every frame.

    Three things that could have made this ours were ruled out:
    - **The start phase.** Nine start T-states from 0 to 69,000 give the same paddle and ball on every frame: the snapshot waits
      in the ROM's `PAUSE` (a `HALT`), so the first interrupt aligns it.
    - **The snapshot.** It is a `.z80` version 2 of the 48K original, saved in BASIC before the game starts, with no trainer.
    - **The frame sync.** The loop at 848Fh waits for the paper, then for four idle reads of the floating bus in a row, and
      returns once a frame.

    Independent sources say the same of the original: a 2018 Retro Video Gamer review describes the bat's speed « depending on
    how far away you were from the ball », and Sinclair User (April 1987) says the ball flies up by itself « after a couple of
    seconds ». No real Spectrum was used here.
  - **The first build ran twice as fast.** Our first build moved the paddle twice as fast (4 a frame in flight, 4 left and 9,
    13, 17 … right at rest): the floating bus was sampled one T-state early and the game ran its loop twice a frame (section
    5); fixed on 27 November.
  - With the floating bus off, the game does not run at all (as documented for the original edition).
- **Robocop** reads the Kempston (chosen in its own menu by the start data); the pad drives it. Compared with MAME 0.289 (`spec128`
  with a Kempston added, same snapshot, same inputs, frame numbers equal): the paper is pixel-identical through the menus and
  the directives and in many play frames, and held left behaves the same in both: from the start of play Robocop only turns to
  face left (he is at the level's left end) and nothing scrolls in 300 frames; after walking right (the street scrolls about
  0.8 pixel a frame), left scrolls the street back only once the enemies standing against him are gone. This matches MAME 0.289;
  it is the game's behaviour, not hardware-verified. The keyboard controls were not compared. The pad path (27 November 2026, the same scratch build
  with a virtual pad): the left stick, the d-pad and both together set the Kempston's left bit (02h) alone or its right bit (01h)
  alone, and press no key.

## 7. Multiplayer

Rollback (smooth) on the game's own snapshots, two seats, offered like any listed machine with a session
([MULTIPLAYER.md](MULTIPLAYER.md)). A snapshot is the quick state's body (the CPU, then every field of the machine: the RAM
banks, the ULA, the keyboard rows and the Kempston latch, the AY's counters, the frame position) in memory, about 203 KiB, checked
whole and applied only then; the digest is FNV-1a 64 over the same bytes with the picture and the sound box left out (the next
frame redraws every line; each PC drains its sound at its own pace). Player 1 is on the joystick interface the snapshot was saved
for (or the reviewed one), player 2 on the Interface 2 keys player 1 does not use, each a pure function of its seat's word ANDed
with the keyboard; the host types for everyone. A restart puts every seat back at the game's start (the snapshot taken when the
game opened in the match). The report carries a top-level `firmware` record (the model's ROMs in bank order, their SHA-256, each
bank's), so a room refuses two PCs on different ROMs before the match. The Spectrum has no save to carry.

Evidence (22 November 2026, `spec/zx-multiplayer`):

- `--snap-probe AT:N` (headless, in the game itself) on six panel games (Manic Miner, Jetpac, Arkanoid, Match Day II, Head over
  Heels, Robocop), at frames 300 (120 frames) and 1,200 (200 frames): the snapshot is the same bytes twice, a load one byte short
  is refused with nothing changed, and after the load every digest and every picture is the same: PASS on all twelve.
- Windows and Linux (WSL, Debian 13) give the same digests on the same frames (Manic Miner, Head over Heels, Arkanoid, six points).
- `tools/netplay_game_smoke.py` on Manic Miner, two seats, rollback 5, 30 ms of latency with 10 of jitter, 2 % of packets lost,
  the match saved at 600 and loaded at 1,500, restarted at 2,200: 3,000 frames, 50 digests equal on both seats, 133 rollbacks
  (deepest 2), the restart and the save and load on the same frames: PASS.
- Two PCs (27 November 2026, the multiplayer specialist's harness, the same commit dce6c18d on both PCs): Manic Miner ran in
  both passes of the eight-game run (12 of 12, then 11 of 11 PASS). Each side's log reads « 2 ports »; 50 digests were compared
  and all are equal; the save, the load and the restart fall on the same frames; rollback. Manic Miner is a one-player game: one
  seat plays and the other watches.
- Not done yet: a two-PC run of a Spectrum game with two players, and the owner's own play on two PCs. The input delay is
  counted in frames; physical latency is not measured.

Known limits (22 November 2026):

- A restart in a match goes through the game's own reset path (the embedded machine image loaded again on every seat at the same
  frame, the keyboard rows and the Kempston latch cleared), not through `session_begin`, which lays the start snapshot at the
  match's start only; the smoke test's digests stay equal after the restart at frame 2,200.
- With player 1 on the cursor keys (5 left, 6 down, 7 up, 8 right, 0 fire), player 2 goes on Interface 2's 1-5, whose fire (5)
  is player 1's left: a press of player 2's fire also reads as player 1 going left. Interface 2's 6-0 would overlap four keys, so
  1-5 is the smaller overlap; the fix is per-game data (player 2 on the Kempston when the game reads it, or the interface the game's
  menu gives player 2), keyed by the dump's SHA-256 and locked for the match.
- Match Day II, two players: with the idle Fuller box its menu cursor stays where a press leaves it (a press, then nothing held:
  the cursor does not move again; native, reference and the delivered game equal on every frame of that route). The two-player
  match is reached on the reference by: ENTER on the title; on « Select joystick », SPACE until the arrow is on « Kempston
  joystick », ENTER; on the main menu, SPACE once to « 2 Player Matchday », ENTER; on « First half », ENTER. Which keys player 2
  moves with in the match is not yet confirmed: after the kick-off, held for a second, only the bottom row, 0 and the Kempston's fire
  changed the picture, and no direction of either player; « Keys and options », « Player 2 keys » lets the host type player 2's
  keys (6, 7, 8, 9, 0 would put them on player 2's pad).
- Not yet: per-game data for the games whose two players share the keyboard in halves (keyed by the dump's SHA-256, sent and locked
  as a session option).
