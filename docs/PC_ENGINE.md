# PC Engine

Experimental profile (`pce`), **available since 1.6.9**: NEC/Hudson's PC Engine, sold as the TurboGrafx-16 in the
United States. It converts the player's own HuCard dumps (`.pce`, or a ZIP holding one) into a standalone game, US
TurboGrafx-16 HuCards included, in both dumping orders ([below](#us-turbografx-16-cards-6-november-2026)). The native
code comes from what the game was seen to run; every instruction that was not seen stays interpreted, counted and
reported. It is experimental: no gate of the qualification list is claimed beyond what was measured.

## Contents

1. [At a glance](#1-at-a-glance)
2. [Scope](#2-scope)
3. [How a HuCard file is read](#3-how-a-hucard-file-is-read)
4. [Engine and upstream](#4-engine-and-upstream)
5. [What was measured](#5-what-was-measured)
6. [The five measures](#6-the-five-measures)
7. [Known limits](#7-known-limits)
8. [Next stages](#8-next-stages)

## 1. At a glance

| | |
|---|---|
| Status | **Experimental**, available since 1.6.9 |
| Input | `.pce` HuCard images, or a ZIP holding exactly one (read by its content, [below](#3-how-a-hucard-file-is-read)) |
| Processor | One HuC6280 (a 65C02 derivative that also holds the sound generator); fallback counted in instructions |
| Engine | [rages4calm/pcenginerecomp](https://github.com/rages4calm/pcenginerecomp), MIT, pinned by commit; runtime ABI 29 |
| Reports | Common report v2 through `write_report`: native and interpreted instructions per route, guard misses, the five measures kept apart |
| Exports | A standalone Windows game per card; quick states (F8/F9); two players, six buttons for the Street Fighter II board |

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
- **Saves:** HuCards have no save memory.

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
`81b5c231e452c6879d58585c8863012e438f1d55`: its Python analysis and emitter, and its C++ runtime (HuC6280 interpreter,
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
- **Speed:** not measured yet. It needs a quiet PC and the owner's go.

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

Twelve conversions through the same loop as the first panel (two routes of 3,600 frames, native against every-instruction
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
  and a US card is only as good as its play route. The owner has not played these twelve.

### Linux witness (6 November 2026)

Nine cards were converted on a Debian 13 PC (GCC 14.2, Ninja, an empty library) from the same tree (commit `92545231`) as on
Windows, at the standard level, one at a time: Bonk's Adventure, Bonk III, Neutopia II, Night Creatures, Blazing Lazers, Raiden,
Space Harrier, Splatterhouse and Bomberman '93. On both routes of 3,600 frames, the CPU, RAM, image and PCM hashes are equal to
the Windows run's, with the same native counts: 0 interpreted instructions and 0 guard misses on each side. Conversions took 12 to
28 minutes on that PC. Gradius and Santatlantean were chosen but not run there.

The Windows runs used Visual Studio's compiler; Bonk's Adventure, Blazing Lazers and Night Creatures were rebuilt with the portable
llvm-mingw toolchain that players use and give the same hashes (they converted in 5 to 13 minutes). A quick state (F8) is not
compared across systems: its key holds the target.

## 6. The five measures

They stay separate everywhere ([STANDARDS.md](STANDARDS.md)).

| Measure | State |
|---|---|
| Native code | Reported per route and per CPU: native and interpreted instructions and guard misses, from the game's own counters. 0 interpreted on the played routes of 8 of the 9 converted games; Street Fighter II' CE keeps a counted interpreted share |
| CPU fidelity | The native module equals the engine's own interpreter, frame by frame, on the routes played (CPU state, work RAM, picture, PCM). That is agreement with the engine, not with a real HuC6280: the engine's interpreter has three known differences from an independent vector set ([above](#5-what-was-measured)) |
| Hardware fidelity | Not reported. No independent hardware comparison exists |
| Gameplay validation | One owner play trial: eight of the nine converted cards were played on 5 November 2026 (earlier tree) and worked, in his words ([QUALIFICATION.md](QUALIFICATION.md#owner-acceptance)). That is a trial, not a coverage claim: no game was checked end to end |
| Physical latency | Not reported and not measured |

Interpreter fallback is counted per CPU. The report carries `latency_ms: null`.

## 7. Known limits

- Experimental: only the routes played are compared; the rest of a game may run interpreted, and the report counts it.
- A card that needs more than 65,536 distinct instruction identities (Street Fighter II' CE) is only partly native by the
  engine's design.
- The engine's static analysis stops at the first `TAM` (a bank-register write), so the native code is taken from observed
  runs, never from the ROM alone.
- Speed on a real card is unmeasured, and the vectors have three known differences on the interpreter (the oracle is an emulator).
- Out of scope: CD-ROM2, SuperGrafx (refused when no picture appears), PAL timing, the Populous RAM board, and the fifth
  multitap player. A converted game is built for two players.
- The Linux build is witnessed on 9 of 11 cards ([above](#linux-witness-6-november-2026)); a quick state is not shared between Windows and Linux.
- Audio is the engine's raw PSG output at 44.1 kHz.
- No claim is made about hardware behaviour, complete gameplay or latency.

## 8. Next stages

1. A speed measure on a quiet PC.
2. More HuCards through the same loop, then more of the owner's play trials.
3. SuperGrafx and CD-ROM2 as separate studies.

No date is promised. Gate by gate status is in [QUALIFICATION.md](QUALIFICATION.md) (column `pce`), and what a new machine
must do is in [NEW_MACHINE.md](NEW_MACHINE.md).
