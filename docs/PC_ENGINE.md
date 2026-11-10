# PC Engine

Profile `pce`, **available since 1.6.9**, supported since 1.7.2 on the owner's decision of 10 November 2026 ([G14](QUALIFICATION.md#owner-acceptance)): NEC/Hudson's PC Engine, sold as the TurboGrafx-16 in the
United States. It converts the player's own HuCard dumps (`.pce`, or a ZIP holding one) into a standalone game, US
TurboGrafx-16 HuCards included, in both dumping orders (the bit-reversed order tested on two copies made for the test; [below](#us-turbografx-16-cards-6-november-2026)). The native
code comes from what the game was seen to run; every instruction that was not seen stays interpreted, counted and
reported. No gate of the qualification list is claimed beyond what was measured.

## Contents

1. [At a glance](#1-at-a-glance)
2. [Scope](#2-scope)
3. [How a HuCard file is read](#3-how-a-hucard-file-is-read)
4. [Engine and upstream](#4-engine-and-upstream)
5. [What was measured](#5-what-was-measured)
6. [Saves](#6-saves)
7. [Shared paths](#7-shared-paths)
8. [The five measures](#8-the-five-measures)
9. [Known limits](#9-known-limits)
10. [Next stages](#10-next-stages)

## 1. At a glance

| | |
|---|---|
| Status | **Supported** since 1.7.2 (the owner's decision of 10 November 2026); open since 1.6.9 |
| Input | `.pce` HuCard images, or a ZIP holding exactly one (read by its content, [below](#3-how-a-hucard-file-is-read)) |
| Processor | One HuC6280 (a 65C02 derivative that also holds the sound generator); fallback counted in instructions |
| Engine | [rages4calm/pcenginerecomp](https://github.com/rages4calm/pcenginerecomp), MIT, pinned by commit; runtime ABI 29 |
| Reports | Common report v2 through `write_report`: native and interpreted instructions per route, guard misses, the five measures kept apart |
| Exports | A standalone Windows game per card; quick states (F8/F9); a Backup RAM file beside the game ([below](#6-saves)); two players, six buttons for the Street Fighter II board |

## 2. Scope

Decided on 5 November 2026.

- **Cards:** HuCards only. No CD-ROM2 and no SuperGrafx.
- **Video:** NTSC.
- **Pads:** the two-button pad, and the six-button pad of the Street Fighter II board. The multitap seats four players at
  most (the console takes five; Bomberman is the named case): the fifth player is not offered. A converted game is built
  for two players today; the build recipe supports the four-seat variant, which no option of the converter selects yet.
- **Boards:** the standard boards from 8 KiB to 1 MiB, including the 384 KiB and 768 KiB mirror maps, and the Street
  Fighter II board (2.5 MiB).
- **Not recognised:** the Populous RAM board, SuperGrafx images and CD images. A ZIP holds exactly one `.pce` (several or
  none are refused, and a `.sgx` is refused). The size limit of a ZIP member is declared by the profile.
- **A SuperGrafx game** (a `.pce` that needs the second video chip) cannot be told from its bytes: it starts on one chip,
  shows no picture, and the conversion refuses it ("no picture was produced"). Dai Makaimura is the example tried.
- **Saves:** a HuCard has no save memory of its own, but a game can keep 2 KiB on the console's backup unit, and some do: the
  export gives it that memory, in a file beside the game ([Saves](#6-saves)).

## 3. How a HuCard file is read

`retrorecomp/pce_rom.py` states three written rules. No title list and no checksum list is consulted, and no ROM byte is
kept or written by the reader.

- **Header.** A file whose size is whole 8 KiB banks plus 512 bytes carries a copier header (`copier512`); the 512 bytes
  are skipped. Any other size that is not whole banks is refused.
- **Bit order.** The reset vector of bank 0 (bytes `$1FFE` and `$1FFF`) must point into `$E000-$FFFF`, where the processor
  starts. A dump that passes only once each byte's bits are reversed is `bit-reversed`. A card that is plausible in neither
  order is refused. When both orders are plausible (a high byte of `$E7`, `$EF`, `$F7` or `$FF`: 4 of the 91 US cards of the
  maintainer's library), the first instruction at the vector decides: `bit-reversed` only when it is SEI, NOP or CSH once the
  bits are turned and none of them as stored (SEI, NOP or CSH start 282 of the 286 cards of the library); otherwise `linear`.
- **Board.** Chosen by the decoded size: 8 KiB to 1 MiB is the standard map, exactly 2.5 MiB is the Street Fighter II map.

The identity of a game is the SHA-256 of the file as given, header included. The decoded ROM has its own hash, which
is what the engine maps.

## 4. Engine and upstream

The profile is built on [rages4calm/pcenginerecomp](https://github.com/rages4calm/pcenginerecomp) at commit
`6bb848e88c75b3ed5dbbdcab6d1b7ef5dc1cf6d0`: its Python analysis and emitter, and its C++ runtime (HuC6280 interpreter,
video and colour chips, sound generator, timer, interrupts, pads, HuCard boards). The engine is MIT. The upstream has no
release or tag, so the pin is a commit, and every change of its runtime ABI (29 values in 11 days, none touching
HuCards since 28 October 2026) means re-emitting, rebuilding and requalifying. Notices, including the MAME opcode table
(BSD) and the PCECD_seek notice that the engine carries, are in [pcenginerecomp.md](../licenses/pcenginerecomp.md); the
pin, the review record and the rules for bumping it are in [UPSTREAMS.md](UPSTREAMS.md).

The engine is fetched at that revision when a conversion needs it; no copy is kept in the repository. The converted game
is built from the engine's runtime plus the machine bridge and the host kit's adapter of Retro-Recomp.

| Where | What |
|---|---|
| `retrorecomp/systems/pc_engine.py` | The `SystemProfile`: identity, extension `.pce`, status, CPU, path shape, report shape |
| `retrorecomp/pce_rom.py` | The HuCard reader ([above](#3-how-a-hucard-file-is-read)) |
| `retrorecomp/pce_conversion.py` | The conversion loop: routes, reference and native runs, captures, composition, packed replay, F8/F9 checks |
| `retrorecomp/pce_build.py` | The engine checkout, the module emission, the game project and its build |
| `native/pce_machine.cpp`, `native/pce_main.c` | The bridge to the engine's runtime and the game's entry point |
| `native/hostkit/adapters/rrhk_pce.c` | The adapter of the common host kit (window, menus, audio ring, controls) |
| `licenses/pcenginerecomp.md` | The engine's notices |
| `retrorecomp/stamp_inputs.py` | Roles and owners of these files ([AGENTS_GUIDE.md](AGENTS_GUIDE.md)) |

## 5. What was measured

The engine gate of 5 November 2026 was run by the PC Engine specialist on HuCards written for the purpose; no game ROM
was used. It measures the pinned engine, not a Retro-Recomp conversion.

- **Nine authored cards:** 128 KiB, 256 KiB, 384 KiB, 512 KiB, 768 KiB, 1 MiB, 256 KiB with a copier header, 256 KiB
  bit-reversed, and a 2.5 MiB Street Fighter II board; plus a multitap 6-button variant. Each runs 1,777,440
  instructions (1,777,399 for the Street Fighter II board) over 60 frames, all native, 0 interpreted. Memory, picture,
  sound and final state are identical to the engine's interpreter, and the expected bank maps are met.
- **A module on the wrong card:** run on a card it was not built for, a module gives 5 counted guard misses (interpreted)
  in hybrid mode and an explicit stop in native-only mode.
- **Processor vectors:** SingleStepTests/huc6280 (MIT, generated by Mesen, 640,000 vectors), replayed by two tools of ours
  (they fetch the corpus at its pinned revision into `.deps`, check its digest, and fail on any difference they do not
  know). On the interpreter, 563,514 of the 572,519 comparable vectors agree; the 22 reserved opcodes are refused by design
  and the 12,481 block-transfer vectors are cut by the corpus. Natively, 9,097 cases by default and 56,767 on request (231
  opcodes, 40 or 250 each) show 0 differences with the interpreter. Upstream's own adapter, merged as
  rages4calm/pcenginerecomp#6, gives the same interpreter numbers on the same corpus.
  The three known differences are explained against a second model, the source of MAME 0.289's HuC6280 core (read, not run),
  and not resolved: the TSB/TRB Z flag (1,492) and ST0-2 at 5 cycles against 4 (7,500), where the engine and MAME agree and
  the corpus differs (the corpus has no VDC), and TMA #0 (13), which depends on a latch the corpus does not carry. Both sources
  are emulators, not silicon.
- **Licence audit:** a token-overlap comparison of the engine's device sources against Geargrafx, Beetle and Mesen2 (GPL),
  MAME (BSD) and ares (ISC). No copied expression was found. This is a screening, not a legal opinion.
- **Speed:** measured on a quiet PC, 10 November 2026, one core, the headless attract route with no input, the best of three runs of 2,400 frames, host time only: against games built with the 1.7.1 pin `81b5c231` (no published 1.7.1 PC Engine export exists to measure), the frame cost is 1.09x on Blazing Lazers (4.44 to 4.84 ms a frame) and 1.04x on Street Fighter II' CE (4.49 to 4.69 ms; its old game ran 19.3 % interpreted on that route), and Street Fighter II' CE starts in 1.40 s instead of 0.21 s (its game is 25.4 MB). The bus observer of the new pin is ruled out as the cause: the same module of Blazing Lazers built with the observer compiled out costs the same (4.81 against 4.76 ms a frame, within noise). Where the rest comes from (the module the new engine emits, the rest of its runtime, the Backup RAM) is not measured apart.

### The first panel (5 November 2026)

Ten real HuCards from the owner's own library were tried one at a time, read in place (no ROM is kept in the
repository). Each conversion plays two routes of 3,600 frames (the attract loop and a play route), runs every route twice in
the same build (every instruction interpreted, then the guarded native module), and requires the per-frame CPU, work RAM,
picture and PCM traces to be identical. The compressed executable is replayed against the same reference, and a quick state
saved with F8 is loaded in a fresh process and must continue the saved timeline; a truncated state must be refused.

| Result | Games |
|---|---|
| Native on the routes played, 0 interpreted, 0 guard misses, traces equal, packed replay equal, F8/F9 in a fresh process | Bonk's Adventure, Blazing Lazers, Raiden, Space Harrier, Splatterhouse, Bomberman '93, Gradius, Santatlantean |
| Partly native, the rest interpreted, counted and reported; traces equal | Street Fighter II' Champion Edition |
| Refused: the picture never appears (a SuperGrafx game, one video chip only) | Dai Makaimura |

- **What "100 % native" means here:** on the played routes, every instruction that ran was translated code. Code the
  routes did not reach stays interpreted and counted in the report when a player reaches it. It says nothing about
  the whole game.
- **Street Fighter II' CE** (2.5 MiB, 466 bank-register contexts) reaches the engine's own bound: a code capture and a
  composed module hold 65,536 instruction identities at most. The conversion keeps each capture up to the frame before the
  first dropped identity, unites captures only while they fit, and leaves the rest interpreted. On the delivered file the
  attract route ran 71.7 million instructions natively against 28.6 million interpreted, and the play route 66.3 million
  against 35.1 million. The report lists the captures left out.
- **Pictures:** the contact sheets of every route show moving pictures; the attract loop of Space Harrier and Santatlantean
  has no input and its picture stops changing after a few frames, while their play routes move.
- **The Run button** pauses most games on a third press, so the play route chooses its start on the reference by how
  much the picture differs from the no-input run (1, 2 or 3 presses), not by a fixed count.
- **Conversion time** was 10 to 26 minutes per game with the MSVC toolchain. It is not a measure of the game's speed.

### US TurboGrafx-16 cards (6 November 2026)

Twelve conversions of eleven cards through the same loop as the first panel (two routes of 3,600 frames, native against every-instruction
interpreted, packed replay, F8/F9 in a fresh process), one at a time, on the tree of the branch `spec/pce-us-cards`. The cards
are read in place from the owner's library; no ROM is kept in the repository.

| Card | Encoding found | Native / interpreted (attract, play) | Result |
|---|---|---|---|
| Alien Crush (USA), a copy with every byte's bits reversed | `bit-reversed` (decoded hash equals the original's) | 107.5 M / 0, 107.6 M / 0 | Traces equal, packed replay equal, F8/F9 pass |
| Tiger Road (USA), a copy with every byte's bits reversed | `bit-reversed` (vector `$E7A3` reads `$E7C5` the other way; decoded hash equals the original's) | 122.4 M / 0, 114.2 M / 0 | Traces equal, packed replay equal, F8/F9 pass |
| Tiger Road (USA) | `linear` (same ambiguous vector) | 122.4 M / 0, 112.6 M / 0 | Traces equal, packed replay equal, F8/F9 pass |
| Legend of Hero Tonma (USA) | `linear` (vector `$FF00` reads the same both ways) | 71.4 M / 0, 61.3 M / 0 | Traces equal, packed replay equal, F8/F9 pass |
| Bravoman (USA) | `linear` (vector `$EFA5` reads `$F7A5` the other way) | 107.9 M / 0, 107.4 M / 0 | Traces equal, packed replay equal, F8/F9 pass |
| Bonk III (USA), 1 MiB, the largest standard board | `linear` | 106.5 M / 0, 107.0 M / 0 | Traces equal, packed replay equal, F8/F9 pass |
| Neutopia II (USA), 768 KiB mirror map | `linear` | 102.3 M / 0, 101.8 M / 0 | Traces equal, packed replay equal, F8/F9 pass |
| Boxyboy (USA), 128 KiB, the smallest | `linear` | 95.9 M / 0, 95.9 M / 0 | Traces equal, packed replay equal, F8/F9 pass |
| Night Creatures (USA), the reset code starts with STZ | `linear` | 106.4 M / 0, 101.6 M / 0 | Traces equal, packed replay equal, F8/F9 pass |
| Military Madness (USA), turn-based | `linear` | 91.4 M / 0, 91.1 M / 0 | Traces equal, packed replay equal, F8/F9 pass |
| Soldier Blade (USA), dense sprites and fast scrolling | `linear` | 106.1 M / 0, 106.0 M / 0 | Traces equal, packed replay equal, F8/F9 pass |
| Magical Chase (USA), parallax and line interrupts | `linear` | 107.4 M / 0, 107.9 M / 0 | Traces equal, packed replay equal, F8/F9 pass |

- All twelve: 0 interpreted instructions, 0 guard misses on the routes played, the native run equal to the interpreted
  reference frame by frame, moving pictures and audible sound on both routes.
- **No real bit-reversed dump exists in the owner's library.** Its 91 US `.pce` files and its Japanese ZIPs all read `linear`.
  The two `bit-reversed` rows are copies made for this test by reversing the bits of two of his own files (written under
  `.build`, never published); they are what a bit-reversed dump of those cards would look like. Reversing the bits of all 91
  US cards in memory and reading them back recovers each original, the four cards with an ambiguous vector included, once the
  first-instruction rule above is applied (without it those four were read as `linear` and decoded wrongly).
- This is the reader and the conversion of those cards, not a claim about every US card: no title or checksum list is used,
  and a US card is only as good as its play route. The owner has not played any of these eleven cards.

### Linux witness (6 November 2026)

Nine cards were converted on a Debian 13 PC (GCC 14.2, Ninja, an empty library) from the same tree (commit `92545231`) as on
Windows, at the standard level, one at a time: Bonk's Adventure, Bonk III, Neutopia II, Night Creatures, Blazing Lazers, Raiden,
Space Harrier, Splatterhouse and Bomberman '93. On both routes of 3,600 frames, the CPU, RAM, image and PCM hashes are equal to
the Windows run's, with the same native counts: 0 interpreted instructions and 0 guard misses on each side. Conversions took 12 to
28 minutes on that PC. Gradius and Santatlantean were chosen but not run there.

The Windows runs used Visual Studio's compiler; Bonk's Adventure, Blazing Lazers and Night Creatures were rebuilt with the portable
llvm-mingw toolchain that players use and give the same hashes (they converted in 5 to 13 minutes). A quick state (F8) is not
compared across systems: its key holds the target.

On 9 November 2026, two more cards were converted on the same Debian 13 PC at the extended level, from the tree `4fe3cdc6` and
with the play route that answers the game: Boxyboy (6 Run presses) and Santatlantean (4). On all three routes of each, the 18,000-frame
ones included, the CPU, RAM, picture and PCM hashes equal the Windows run's (built with llvm-mingw), with the same native counts.
That makes 10 of the 15 cards of the extended panel witnessed on Linux (Night Creatures, one of the nine of 6 November, is not in
the extended panel). The eight others of 6 November were witnessed before the start choice changed, so only Boxyboy and
Santatlantean were seen on the current routes; Gradius, Street Fighter II' CE, Tonma, Military Madness and Soldier Blade were not
run there. All of this predates the Backup RAM: the RAM hash now holds that bank, so these hashes are not comparable with today's.

### The whole panel on Linux (9 and 10 November 2026)

The 15 cards of [the release-tree panel](#the-panel-of-the-release-tree-9-november-2026) were converted again on the same Debian 13 PC from the same tree
(`cf6d56fa`), with GCC 14.2 and Ninja, an empty library, no shared base and the extended level: fourteen cards two at a time, then Street Fighter II' CE
alone. On **45 of 45 routes**, the 18,000-frame ones included, the CPU, RAM, picture, PCM and Backup RAM hashes equal the Windows panel's (llvm-mingw),
with the same native counts (0 interpreted instructions, 0 guard misses) and the same walk repairs; on every card the packed replay and the
fresh-process states pass. That meets the cross-OS criterion (G13). Street Fighter II' CE's three routes (191,563 to 590,308 identities, the larger
capture format) are equal too.

- In the run's first part, two conversions at once set up the engine's checkout at the same time: thirteen of the fourteen cards failed with a
  git error and were run again, unchanged, once the checkout was there. The fetch is now under the shared setup gate like the other engines'
  (commit `6a02b0f4`, after the panel): Boxyboy and Blazing Lazers, two at once from an empty `.deps` on the same PC, both converted
  (10 November 2026, the engine fetched once).
- Conversion times on that PC (4 cores, 7.8 GB): 26 to 37 minutes a card two at a time, about two hours for Street Fighter II' CE alone. Its
  memory stayed above 2.9 GB available, and the conversion's processes used at most 3.7 GB. These are not speed measures.
- What this does not say: nobody played a game on Linux (window, pad, sound out); a quick state is not compared across systems (its key holds
  the target); no save made by a player was tried on Linux.

### The extended panel (9 November 2026)

Fifteen cards through the same loop at the **extended** level, built with the toolchain players use (llvm-mingw), one at a
time or three at once, on the tree of the branch `spec/pce-173`, the Backup RAM included ([Saves](#6-saves)). Each plays three routes (attract with no input, play, and a
pseudo-random walk of 18,000 frames), runs each twice (every instruction interpreted, then the guarded native module) and
requires the per-frame CPU, RAM, picture and PCM traces to be equal; the compressed executable is replayed against the
same reference; a quick state is saved, loaded in a fresh process and must continue the timeline, thirteen damaged states
must be refused and a missing one must create nothing. All fifteen conversions passed these checks. The numbers are native
instructions / interpreted share (millions).

| Card | Run presses of the start | attract | play | long route (18,000) | The long route, looked at (12 pictures) |
|---|---|---|---|---|---|
| Bonk's Adventure (USA) | 2 | 107 M / 0 | 107 M / 0 | 535 M / 0 | in play to the end, reaches stage 1-2 |
| Blazing Lazers (USA) | 2 | 118 M / 0 | 114 M / 0 | 572 M / 0 | in play, dies and restarts Area 1 |
| Raiden (USA) | 1 | 110 M / 0 | 106 M / 0 | 526 M / 0 | in play (stage 1), ends on a continue countdown |
| Space Harrier (USA) | 3 | 106 M / 0 | 98 M / 0 | 542 M / 0 | plays, then a stage banner stays up (uncertain) |
| Splatterhouse (USA) | 4 | 89 M / 0 | 88 M / 0 | 425 M / 0 | in play to the end, several rooms |
| Bomberman '93 (USA) | 4 | 105 M / 0 | 104 M / 0 | 528 M / 0 | plays, then the stage restarts; ends on a city scene |
| Gradius (Japan) | 1 | 104 M / 0 | 103 M / 0 | 506 M / 0 | plays, then left paused by the walk from about frame 7,700 (below) |
| Santatlantean (aetherbyte) | 4 | 103 M / 0 | 98 M / 0 | 473 M / 0 | plays to a game over and a new high score, then loops between title and options |
| Street Fighter II' - Champion Edition (Japan) | 4 | 81 M / 19.3 % | 68 M / 33.5 % | 132 M / 74.7 % | fights (score 13,900), ends on an idle fight screen after a pause |
| Boxyboy (USA) | 6 | 96 M / 0 | 96 M / 0 | 480 M / 0 | in play (puzzle stages), not solved |
| Legend of Hero Tonma (USA) | 6 | 71 M / 0 | 64 M / 0 | 351 M / 0 | in play, reaches a tower section |
| Military Madness (USA) | 2 | 91 M / 0 | 92 M / 0 | 456 M / 0 | reaches the map, stalls on a FIGHT/SURRENDER prompt from about frame 6,000 |
| Neutopia II (USA) | 1 | 102 M / 0 | 104 M / 0 | 506 M / 0 | in play on the first overworld screens |
| Soldier Blade (USA) | 6 | 106 M / 0 | 106 M / 0 | 536 M / 0 | in play, restarts stage 1 after each game over |
| Bonk III - Bonk's Big Adventure (USA) | 1 | 107 M / 0 | 106 M / 0 | 534 M / 0 | in play (stage 1-1), then leaves for a menu |

- **0 interpreted on every route of 14 cards.** Street Fighter II' Champion Edition kept a counted interpreted share on that tree, from
  the engine's bound of 65,536 instruction identities per module (four captures were left out); `release_check` reported it as
  its one failure against the limit of 0, which is the rule working. With the engine's larger capture format it runs 0 interpreted
  ([the release tree](#the-panel-of-the-release-tree-9-november-2026)).
- **A pause the walk leaves on.** The walk presses Run in pairs, to leave stories and prompts; in play that is a pause and its end. A press of a pair can be lost (a game ignores Run while
  it restarts), and every later pair then leaves the pause on. On Gradius, from about frame 7,700, the CPU and RAM hashes changed on every frame while the picture cycled through 32 star pictures, and one more Run press
  brought the game back to play: no fault of ours was shown (checked on the delivered game, not against MAME). The conversion now looks for this on the fresh reference (`pce_conversion.repair_route`): where the picture hardly changes for a
  stretch between presses (at most 5 % distinct pictures over at least 300 frames), it tries one more Run press 60 frames in, and keeps it only if at least 20 % of the pictures to the next press are then distinct. Two presses with no answer end the search on a route,
  and the presses kept are recorded in the report (`route_start.repairs`). What it changed on three cards converted to prove it: Gradius's long route goes from 4,754 to 8,856 distinct pictures (0 interpreted); Street Fighter II' CE's from 4,521 to 11,257. What it does not fix:
  Space Harrier's long route stays at 2,409 distinct pictures. Two more presses get no answer there, and although a later one helps (4,428 distinct pictures), it took four more runs of the route to find. Military Madness's prompt, Boxyboy's still puzzle stages and
  Santatlantean's title screen also get no answer, on the delivered games, and each such route costs two more reference runs. Each run of a long route costs about 3 minutes at three conversions at once.
- **The Backup RAM and the stalls.** Compared with the same panel just before the memory existed: 14 cards keep their counts to the million, Santatlantean's attract loop goes
  from 87 M to 103 M instructions because it no longer stops, and its stall on the long route stays. The memory explains no other stall. The 12 pictures of the attract and
  long routes of Gradius and Military Madness are identical to before. Bomberman '93 only probes the memory: its pictures are the same up to the last one, where it now ends on
  a city scene and no longer on the password screen, and it still restarts its stage. Space Harrier and Street Fighter II' CE do not write it, keep their counts and were not looked at again.
- **The start.** The first panel pressed Run at fixed frames; on 7 of 18 cards the play route then stayed on a menu, a story,
  a sound test or a password screen while every check passed. The conversion now tries 1, 2, 3, 4 and 6 presses (Run pairs
  also come now and then during the walk, to leave stories and prompts), walks with the directions only for 900 frames, and
  keeps the variant whose walk showed the most pictures that the same frames without input never show (a menu shows a
  handful, a game in play hundreds). A password screen cannot be typed into during that part of the walk.
- **What "reaches play" means here.** Contact sheets of 12 pictures of each long route were looked at: every card reaches a
  stage under control at some point; nine end in play with progress, six reach play and then stall (the last column). The
  walk is pseudo-random: it does not finish a game, and most cards stay in their first stage. The pictures were inspected by
  the specialist agent, not by the owner.
- **Quick states** are checked with thirteen damaged states (an empty file, a text file, a header cut, one byte short, half cut,
  and one flipped bit in the magic, version, system, size, checksum, ROM identity, ABI and payload): each is refused and left
  as it was; loading a missing state is refused and creates nothing.
- **MAME.** `tools/pce_mame_compare.py` compares the delivered game with MAME 0.289 (`tg16`), no input on either side, the first
  3,000 frames, on four US cards: 3,000 of 3,000 pictures equal on Soldier Blade, 2,999 of 3,000 on Bonk's Adventure and on
  Military Madness (one frame, or one scanline, of timing), 2,992 of 2,999 on Boxyboy (7 single frames, each differing on under 0.6 % of its pixels). Both sides
  start from the same formatted Backup RAM, and Soldier Blade leaves the same 2,048 bytes in both. The two write the
  VDC's eight colour levels with different tables, so pictures are compared per colour channel at that level. The game's sound is
  a near-constant 9.3 to 9.5 dB below MAME's with spectra that agree (cosine 0.98 to 0.999); no waveform match is claimed.
  This is a comparison with an emulator, not with hardware.
- **Why Boxyboy once differed.** Before the Backup RAM it matched MAME on 727 of 2,999 pictures, parting at frame 729: MAME showed the title menu, the game a "FILE NOT
  CONNECTED" screen. The card tests bank `$F7` at about that frame, and MAME maps a memory there on every card while the engine's base HuCard profile does not. Forcing that bank to read `$FF` in
  MAME made 2,999 of 2,999 pictures equal the game of that time. The engine was consistent with its documented profile, and no engine fault was shown.

### The panel of the release tree (9 November 2026)

The same fifteen cards through the same loop, at the extended level, with the walk repair ([above](#the-extended-panel-9-november-2026)), the shared paths
([below](#7-shared-paths)) and the engine at `6bb848e8` with its larger capture format, on the tree `cf6d56fa` of the branch `spec/pce-exit`: Windows, llvm-mingw,
three conversions at once, online covers on, no base. These are the games delivered to the owner. All fifteen conversions passed every check (traces equal to
the fresh interpreted reference on all 45 routes, packed replay, quick states, Backup RAM).

| Card | Run presses | Repairs kept (frame) | attract | play | long route (18,000) |
|---|---|---|---|---|---|
| Bonk's Adventure (USA) | 2 | long 16,563 | 107 M / 0 | 107 M / 0 | 535 M / 0 |
| Blazing Lazers (USA) | 2 | | 118 M / 0 | 114 M / 0 | 572 M / 0 |
| Raiden (USA) | 1 | | 110 M / 0 | 106 M / 0 | 526 M / 0 |
| Space Harrier (USA) | 3 | | 106 M / 0 | 98 M / 0 | 542 M / 0 |
| Splatterhouse (USA) | 4 | | 89 M / 0 | 88 M / 0 | 425 M / 0 |
| Bomberman '93 (USA) | 4 | play 3,076; long 3,129, 4,101, 5,056 | 105 M / 0 | 104 M / 0 | 529 M / 0 |
| Gradius (Japan) | 1 | long 7,811 | 104 M / 0 | 103 M / 0 | 512 M / 0 |
| Santatlantean (aetherbyte) | 4 | | 103 M / 0 | 98 M / 0 | 473 M / 0 |
| Street Fighter II' - Champion Edition (Japan) | 4 | long 7,996 | 100 M / 0 | 102 M / 0 | 514 M / 0 |
| Boxyboy (USA) | 6 | | 96 M / 0 | 96 M / 0 | 480 M / 0 |
| Legend of Hero Tonma (USA) | 6 | | 71 M / 0 | 64 M / 0 | 351 M / 0 |
| Military Madness (USA) | 2 | long 6,746 | 91 M / 0 | 92 M / 0 | 464 M / 0 |
| Neutopia II (USA) | 1 | | 102 M / 0 | 104 M / 0 | 506 M / 0 |
| Soldier Blade (USA) | 6 | | 106 M / 0 | 106 M / 0 | 536 M / 0 |
| Bonk III - Bonk's Big Adventure (USA) | 1 | play 2,882; long 2,878 | 107 M / 0 | 106 M / 0 | 533 M / 0 |

- **0 interpreted instructions and 0 guard misses on all 45 routes**, Street Fighter II' CE included. Its three routes captured 191,563, 248,856 and 590,308
  instruction identities in the larger format, none dropped; 734,635 were emitted in 3,757 bank contexts. The cost is in the build: a 25.4 MB packed executable
  (about 120 MB unpacked), and about 34 minutes of conversion on its own (code generation about 3 minutes, the native compile about 8).
- **The 14 other cards keep their counts** to the million against the extended panel, except where a repair changed the long route: Bomberman '93 528 → 529 M,
  Gradius 506 → 512 M, Military Madness 456 → 464 M, Bonk III 534 → 533 M; each stays at 0 interpreted.
- **Conversion times are not comparable** with the earlier panels: a batch stopped before this one kept running beside it for about two hours, so up to six
  conversions shared the PC (15 to 49 minutes each). For the same reason seven cards (Splatterhouse, Gradius, Santatlantean, Tonma, Neutopia II, Soldier Blade,
  Bonk III) received their own record of that earlier batch from the library, as declared roots: every declared row was also run by their own routes
  (none declared only), so what was emitted is what they ran.

## 6. Saves

Added on 9 November 2026. A HuCard has no memory of its own, but the console's backup units (the CD interface, the Tennokoe 2, the Backup
Booster) hold 2 KiB of Backup RAM at bank `$F7`, and a card can look for it. 86 of the 286 cards of the owner's library hold the mark of the file system (`HUBM`), 63 of them with
the unlock sequence as well. Under MAME 0.289, with no input and a formatted memory, 18 of the 22 US cards among those touch it in their
first 3,000 frames and 8 create a file (Boxyboy, Chew Man Fu, Falcon, Parasol Stars, Soldier Blade, Tiger Road, Timeball, World Sports
Competition). The engine's base HuCard profile has no such memory: the bank reads `$FF`, and Boxyboy then shows "FILE NOT CONNECTED. COPY
THE PASSWORD".

**The model.** `native/pce_machine.cpp` maps bank `$F7` as plain RAM after the engine's own HuCard setup, on the same pin and with no change
to the engine. It is a choice of our bridge, not something the pinned engine offers on a HuCard. It differs from the hardware in named ways:

- **Formatted from the start.** With no save file the memory holds the file system's header (`HUBM 00 88 10 80`) and zeros. A real unit
  starts as whatever it last held and a game may offer to format it. This is what Beetle does for a HuCard (its source was read, not run). MAME
  gets the same bytes when it is compared with the game ([below](#the-extended-panel-9-november-2026)).
- **No lock.** The chip's unlock sequence and lock are not modelled: the bank is always open.
- **8 KiB of RAM, 2 KiB kept.** The file holds the first 2 KiB, the size of the chip. A write past them stays in RAM until the game is closed,
  and the report counts those bytes (`backup_beyond_2k`): none on any route of the panel.
- **One file per card.** A real unit is shared between all games; here a game sees only what it wrote.
- **No CD attached.** The pad port still says no CD is attached. MAME's says one is; forcing Boxyboy's to say none changed no picture.

**The file.** `datas/saves/<game>-<first 12 hex of the card's SHA-256>.rrsram`, 2,160 bytes: a 112-byte header (magic `RRPCEBR1`, version,
size, FNV-1a hash of the memory, the card's SHA-256) and the memory. It is written atomically, two seconds after the game's last change and
when the game closes. It belongs to the exact card and survives a rebuild of the game. `native/pce_backup.c` holds it, and `pce_main.c` asks
it once per frame.

**A file that cannot be used** (empty, cut, one byte too short or long, the raw memory without a header, another magic, version or size, a
wrong hash, another card's) is renamed `<file>.unusable-N` unchanged, the game starts as if there were none, and a notice says so. If it cannot be
moved, saving stops for that run and a notice says so. A file never stops a game. An older export simply has no file and starts formatted.

**Quick states are separate.** A save needs no F8/F9. A quick state also holds the memory, as on the Mega Drive and the Super Nintendo: F9 brings
it back as it was, and the file follows. Quick states of earlier builds are refused, as any other change of the bridge makes them.

**What was proved** on the conversions of 9 November 2026 (Windows, llvm-mingw; each check in `pce_conversion.check_backup`, written into the report's `backup_ram`):

| Check | Result |
|---|---|
| With no file, every card of the panel starts formatted | 15 of 15 |
| A valid file is read back in a fresh process | 15 of 15 |
| 11 kinds of damaged file are set aside unchanged and the game starts | 15 of 15 |
| With the same memory given to both, the native run equals the fully interpreted reference | 15 of 15 |
| The play route writes the memory, and a fresh process finds what was written | 3 of 15 (Boxyboy, Santatlantean, Soldier Blade); on the 12 others the routes only probe it |
| Bytes written past 2 KiB | 0 on every route of the 15 |

Three cards were looked at further, in fresh processes with no window:

- **Boxyboy, a player's save.** Construction mode, a floor saved with the game's own SAVE command ("THE DATA HAS BEEN SAVED", a file `SOKO-EDIT1`
  appears beside the `SOKO-DATA` the game makes at boot); the process ends; a new process's LOAD command then lists "EDIT 1: SAVED". The native game and
  the fully interpreted reference give equal traces and equal files, and loading leaves the file unchanged. The editor is not on the conversion's
  routes, so those two runs are partly interpreted, and counted: 18.8 % (15.6 M of 82.8 M instructions) and 6.8 % (4.4 M of 64.7 M).
- **Santatlantean, a high score.** The long route's game over writes a score of 380 in the table (`SANTA!.his`); a new process's title loop shows it in 8th place,
  where a first start shows `BLZ` with 300. That run has 15,513 interpreted instructions of 102.7 M: the path of a table that was changed is not on the routes. Its attract
  loop, which stopped after a few frames without the memory, now loops through its title and its score table.
- **Soldier Blade, a file with no visible use shown.** The game makes `SOLDIBLADE` at its first start and finds it again in a new process, but a scripted
  game over left it unchanged, and changing the top score in the file (with the game's own checksum recomputed) changed no picture in 1,600 frames. It is a
  card that writes the memory; that it reads a result back on screen is not shown.

What this does not say: nothing here was run on a real backup unit, on Linux, or against Beetle.

## 7. Shared paths

Added on 9 November 2026. The PC Engine is in the experimental tier of the shared base, and `path_profiles.EXPERIMENTAL_SHARED` withdraws it in one line. The site's limits and deployment are the maintainer's.

**What travels.** A record (`retrorecomp/pce_knowledge.py`) holds numbers about the player's own decoded ROM and no byte of it: for each instruction its logical PC, its eight bank registers and the offset of its first byte. The MPRs and the board's map give the
other offsets. It is made only from the captures of a conversion that passed every check, never from paths it received. A record never holds what did not come from the card:

- **Code run from work RAM or the Backup RAM** stays private and counted: the engine's format covers read-only views, and a ROM position would not say what the RAM held. On Soldier Blade that is 156 of 39,649 identities.
- **The Street Fighter II board** shares nothing: its mapper's latch is not in the engine's capture identity, so the selector the format needs cannot be told from an observation.

**What a player does with it.** The conversion gives the engine the received rows as declared roots, `pce-declared-roots-1`, the engine's own input (their [DECLARED_ROOTS.md](https://github.com/rages4calm/pcenginerecomp/blob/6bb848e88c75b3ed5dbbdcab6d1b7ef5dc1cf6d0/docs/DECLARED_ROOTS.md)), beside the history of what
that conversion really ran. The engine rebuilds the code from the player's exact image, refuses any other, and emits it with its ordinary guards. A root is not written into a capture, because a capture is a record of execution (the upstream's request). A failed conversion starts again without the received paths.

**Declared is not executed.** The report keeps them apart (`knowledge.use`): received rows; declared, declared only, overlapping and emitted, from the engine's manifest; rows the conversion's own routes really ran. A declared row says nothing until a window runs it, and the
comparison with the reference qualifies only the window it ran. No reachability is inferred: a row is one instruction, not a routine.

**At the bound.** The engine's module holds 1,048,576 identities. What a conversion really ran comes first. A capture that would pass the bound is left out whole, and received rows past it are left out, each counted (`captures_left_out`, `left_out_at_the_bound`); code
left out stays interpreted and counted, and the conversion does not fail. A route with more identities than one capture holds keeps a complete capture of its start (`complete_prefix`). Tests: `tests/test_pc_engine.py`, `IdentityBoundTests`, on small authored limits.

**The proof** (9 November 2026, Windows, llvm-mingw, Soldier Blade (USA), two empty libraries, no base, no service). A, at the extended level, makes a record of 39,493 instructions in 372 contexts; its exchange file is 20,022 bytes and holds no window of 16 bytes of the ROM. A control converts at the
standard level with no paths. B imports the file and converts at the standard level:

| | Control | B (received paths) |
|---|---|---|
| Attract and play routes, CPU, RAM, picture, PCM, trace | | equal to the control's and to A's, 0 interpreted on both routes |
| Declared rows, of which only declared, overlapping | none | 39,493, of which 6,299, 33,194 |
| Declared rows B's own routes really ran | | 33,194 |
| Executable, packed | 2,524,160 bytes | 2,720,768 bytes |
| A's long route (18,000 frames), which B's routes never played: native / interpreted / guard misses | 528,312,895 / 7,348,650 / 7,348,650 | 535,661,326 / 219 / 219 |
| That route's trace against the fresh reference | equal | equal |
| Declared rows that route really ran | | 36,355 of 39,493 |

The 219 interpreted instructions left are work-RAM code, which does not travel. A copy of the card with one byte changed is refused: the engine refuses the roots (`Snapshot SHA256 mismatch`), our reader refuses the record, and the copy's own hash finds nothing in the bank.

**What this does not say.** One card, on Windows. The long route was replayed on B's game after its conversion: it qualifies that window, not the rows it did not run, and nothing beyond. No path is qualified in the base yet: that takes a conversion that received it from another player, through the shared base.

## 8. The five measures

They stay separate everywhere ([STANDARDS.md](STANDARDS.md)).

| Measure | State |
|---|---|
| Native code | Reported per route and per CPU: native and interpreted instructions and guard misses, from the game's own counters. 0 interpreted and 0 guard misses on every route of the 15 cards of the release tree's panel, the 18,000-frame walks and Street Fighter II' CE included ([above](#the-panel-of-the-release-tree-9-november-2026)). That card needs the engine's larger capture format (up to 1,048,576 instruction identities per module); before it, 19.3 %, 33.5 % and 74.7 % of its instructions ran interpreted |
| CPU fidelity | The native module equals the engine's own interpreter, frame by frame, on the routes played (CPU state, work RAM, picture, PCM). That is agreement with the engine, not with a real HuC6280: the engine's interpreter has three known differences from an independent vector set ([above](#5-what-was-measured)) |
| Hardware fidelity | Not reported as validated. One comparison with an emulator exists, not with hardware: the delivered game against MAME 0.289 on four US cards, no input, 3,000 frames, the same Backup RAM on both sides (pictures equal on 3 of 4 cards bar one frame, and bar 7 on the fourth; sound level 9.3 to 9.5 dB below MAME's; [above](#the-extended-panel-9-november-2026)) |
| Gameplay validation | Owner play trials: eight of the nine cards of the first panel were played on 5 November 2026 (earlier tree) and worked, in his words ([QUALIFICATION.md](QUALIFICATION.md#owner-acceptance)). The extended panel's walks are pseudo-random: the long routes reach play on every card but finish no game. On 9 November 2026 the owner also played Street Fighter II' CE, on the export of the tree `700b72cb` (19 to 47 % interpreted, before the larger capture format), and said "tout marche nickel"; pressing left and right very fast to feel the lag, "extrêmement réactif"; on the interpreted share, "on avancera un peu de toute manière par la suite". That is an impression of feel: it measures neither speed nor latency. On 10 November 2026 he played the fifteen exports of the release tree and said « ils marchent tous parfaitement. Les sauvegardes marchent parfaitement. Tout est ok », then decided the exit from the experimental status. He saw the limit named here: code past the routes runs interpreted, counted and shown in the game (the owner saw it on Boxyboy after Start), and a PC Engine game keeps no player's record yet, so the code a player reaches is not made native at the next conversion. These are trials, not a coverage claim: no game was checked end to end |
| Physical latency | Not reported and not measured: `latency_ms` stays null, whatever a player feels |

Interpreter fallback is counted per CPU. The report carries `latency_ms: null`.

## 9. Known limits

- Only the routes played are compared; the rest of a game may run interpreted, and the report counts it.
- A card that needs more than 65,536 distinct instruction identities (Street Fighter II' CE) takes the engine's larger capture format: it is
  native on its routes, but its game is large (25.4 MB packed, about 120 MB unpacked) and its conversion long (about 34 minutes on its own).
  Past 1,048,576 identities, what does not fit is left out, counted and interpreted; the conversion does not fail.
- The engine's static analysis stops at the first `TAM` (a bank-register write), so the native code is taken from observed
  runs, never from the ROM alone.
- Speed is measured on two cards only, against the 1.7.1 pin ([above](#5-what-was-measured)), and the vectors have three known differences on the interpreter (the oracle is an emulator).
- A PC Engine game keeps no player's record yet: the F12 line of its help page says the record is off, and the code a player reaches past the routes stays interpreted at the next conversion.
- The play route is a pseudo-random walk: six of the fifteen panel cards stall in it (a prompt, a loop, a pause the walk left on, a restarting
  stage) and most stay in their first stage; a stall is a limit of the walk, not a statement about the game.
- The Backup RAM is a model of ours (its bank is in the RAM hash, equal on Linux on the panel's routes): plain RAM, no lock, formatted when there is no file, one file per card ([Saves](#6-saves)). The saving paths are
  not on the routes, so they run partly interpreted, and counted.
- Out of scope: CD-ROM2, SuperGrafx (refused when no picture appears), PAL timing, the Populous RAM board, and the fifth
  multitap player. A converted game is built for two players.
- The Linux build is witnessed on the 15 cards of the release-tree panel, route hashes only ([above](#the-whole-panel-on-linux-9-and-10-november-2026)); nobody played on Linux, and a quick state is not shared between Windows and Linux.
- Audio is the engine's raw PSG output at 44.1 kHz.
- No claim is made about hardware behaviour, complete gameplay or latency.

## 10. Next stages

1. The player's own record (kind 20, F12), so the code a player reaches becomes native at the next conversion, as on the Amiga.
2. A play route that answers a screen confirmed with I (Boxyboy after Start).
3. SuperGrafx and CD-ROM2 as separate studies.

No date is promised. Gate by gate status is in [QUALIFICATION.md](QUALIFICATION.md) (column `pce`), and what a new machine
must do is in [NEW_MACHINE.md](NEW_MACHINE.md).
