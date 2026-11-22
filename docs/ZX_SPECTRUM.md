# ZX Spectrum

Status: **experimental, in development** (step 1 of [NEW_MACHINE.md](NEW_MACHINE.md), from 21 November 2026). The
conversion runs from a snapshot to a game in a development tree (section 4); no installation lists the machine yet (it is a
developer-only profile, as the Game Boy Advance was before its first panel). This page says what the machine converts, what
it leaves out, and how the five measures stay apart.

## 1. Scope

| First (this experimental profile) | Later | Left out for now |
|---|---|---|
| Snapshots of the 16K, 48K and 128K (and the +2, a 128K with another menu ROM): `.z80` versions 1, 2 and 3 and `.sna` (48K and 128K), from a file or a ZIP holding exactly one | `.szx` snapshots; the +2A and +3 (another contention pattern, port 1FFDh, the +3 disk) | Tapes (`.tap`, `.tzx`): their loaders need exact EAR timing, and a snapshot skips every loader; the Interface 1 and Microdrive, the Timex, Pentagon, Scorpion and other clones, the ZX80 and ZX81 |
| The ULA picture (256 x 192, attributes, flash, the border per line), the beeper, the AY-3-8910 on the 128K, the keyboard, the Kempston and Sinclair Interface 2 joysticks, quick states, the ULA's contention and the floating bus | Border changes within a line (drawn at the line's end) | Games that load their next level from tape during play: a snapshot cannot; they stop at that load, and the report says so |

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
   picks « Kempston joystick » in its menu, which waits for ever unless a Kempston answers at port 1Fh.
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
Signal, MIT, agrees on the 48K and is about 5 T-states later on the 128K: unverified). The I/O cycle samples the bus 3 T-states
after its start and its contention; the chain's evaluator gives the machine that moment before the read, natively and on the
reference alike (`zxs_floating_bus`, 20 checks in tools/zxs_machine_selftest.py). Arkanoid, which the guide names as depending
on it, now plays its first round on the play route (297 distinct pictures, bricks broken) where without it the picture froze
after frame 1,409. Not measured on a real Spectrum here.
Nothing claims exact timing. With contention, Manic Miner's play route runs 19 % fewer instructions in its 2,100 frames than
without it, and Head over Heels' 8 %.

## 6. Qualification

The machine's column of [QUALIFICATION.md](QUALIFICATION.md) (22 November 2026): G2 to G6, G10, G12 and G13 `Y`; G1, G8, G9 and
G15 `P`; G7 `-`; G11, G14 and G16 `?`; the evidence is in its entry there. The
panel of the study, used for the gates once conversions run: Manic Miner (the first game: 48K, the beeper, the ROM's
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

## 7. Multiplayer

Rollback (smooth) on the game's own snapshots, two seats, offered nowhere while the machine is developer only
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
- Not done yet: two PCs (the multiplayer specialist's run with the second PC), the owner's play on two PCs. The input delay is
  counted in frames; physical latency is not measured.

Not yet: per-game data for the games whose two players share the keyboard in halves (keyed by the dump's SHA-256, sent and locked
as a session option).
