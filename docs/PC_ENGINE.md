# PC Engine

Experimental profile (`pce`), **in development and developer-only**: NEC/Hudson's PC Engine, sold as the TurboGrafx-16 in
the United States. Today the profile identifies HuCard images and converts nothing. Players see no PC Engine entry in
the interface, and a `.pce` file is refused as an unknown console. Nothing of the machine is distributed.

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
| Status | **Experimental, developer-only**: stage 2 of 7. The profile identifies HuCards and converts nothing |
| Input | `.pce` HuCard images (read by its content, [below](#3-how-a-hucard-file-is-read)) |
| Processor | One HuC6280 (a 65C02 derivative that also holds the sound generator); fallback counted in instructions |
| Engine | [rages4calm/pcenginerecomp](https://github.com/rages4calm/pcenginerecomp), MIT, pinned by commit; runtime ABI 29 |
| Reports | Common report v2 through `write_report`; an identification only, no measure reported |
| Exports | None yet |

## 2. Scope

Decided on 5 November 2026.

- **Cards:** HuCards only. No CD-ROM2 and no SuperGrafx.
- **Video:** NTSC.
- **Pads:** 2- and 6-button pads, and the multitap read for 4 players (the console takes 5; Bomberman is the named case).
- **Boards:** the standard boards from 8 KiB to 1 MiB, including the 384 KiB and 768 KiB mirror maps, and the Street
  Fighter II board (2.5 MiB).
- **Not recognised:** the Populous RAM board, SuperGrafx images and CD images. ZIP archives are deferred: reading them
  needs a size-limit entry in a shared module, which is not touched at this stage.
- **Saves:** HuCards have no save memory.

## 3. How a HuCard file is read

`retrorecomp/pce_rom.py` states three written rules. No title list and no checksum list is consulted, and no ROM byte is
kept or written by the reader.

- **Header.** A file whose size is whole 8 KiB banks plus 512 bytes carries a copier header (`copier512`); the 512 bytes
  are skipped. Any other size that is not whole banks is refused.
- **Bit order.** The reset vector of bank 0 (bytes `$1FFE` and `$1FFF`) must point into `$E000-$FFFF`, where the processor
  starts. A dump that passes only once each byte's bits are reversed is `bit-reversed`. When both orders are plausible
  the card stays `linear`. A card that is plausible in neither order is refused.
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

The engine is fetched at that revision when a conversion needs it; no copy is kept in the repository, and nothing of it
is compiled into a game yet.

| Where | What |
|---|---|
| `retrorecomp/systems/pc_engine.py` | The `SystemProfile`: identity, extension `.pce`, status, CPU, path shape, report shape |
| `retrorecomp/pce_rom.py` | The HuCard reader ([above](#3-how-a-hucard-file-is-read)) |
| `retrorecomp/pce_conversion.py` | The identification report; `convert` refuses with "not converted yet" |
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
- **Processor vectors:** SingleStepTests/huc6280 (MIT, generated by Mesen, 640,000 vectors). On the interpreter, 563,514
  of the 572,519 comparable vectors agree. The three known differences are the TSB/TRB Z flag, ST0-2 at 5 cycles against
  4, and TMA #0. Natively, 9,091 cases show 0 differences with the interpreter. This was proposed upstream as
  rages4calm/pcenginerecomp#6.
- **Licence audit:** a token-overlap comparison of the engine's device sources against Geargrafx, Beetle and Mesen2 (GPL),
  MAME (BSD) and ares (ISC). No copied expression was found. This is a screening, not a legal opinion.
- **Speed:** not measured yet. It needs a quiet PC and the owner's go.

## 6. The five measures

They stay separate everywhere ([STANDARDS.md](STANDARDS.md)). While nothing is converted, all five are **not reported**.

| Measure | State |
|---|---|
| Native code | Not reported: no game is converted. The engine gate above ran authored cards, not games |
| CPU fidelity | Not reported for a conversion. The vectors above are on the pinned engine, measured outside the repository's own tools |
| Hardware fidelity | Not reported. No independent hardware comparison exists |
| Gameplay validation | Not reported. No game has been played |
| Physical latency | Not reported and not measured |

Interpreter fallback will be counted per CPU and per device once a conversion exists. The report carries
`converted: false` and `latency_ms: null`.

## 7. Known limits

- Nothing is converted, no game executable exists, and the interface does not offer the machine.
- The engine's static analysis stops at the first `TAM` (a bank-register write), so the native code cannot come from
  reading the ROM alone; stage 3 takes it from observed runs.
- Speed on a real card is unmeasured, and the vectors have three known differences on the interpreter.
- Out of scope today: CD-ROM2, SuperGrafx, PAL timing, the Populous RAM board, ZIP archives, and the fifth multitap
  player.
- No claim is made about hardware behaviour, complete gameplay or latency.

## 8. Next stages

The profile is at stage 2 of 7: it identifies HuCards and converts nothing. The rest:

3. The conversion loop, driven by captures: unseen code stays interpreted and counted.
4. The host-kit adapter.
5. Independent evidence, with a tool of ours for the vectors.
6. A panel of ten HuCards, converted one at a time.
7. An experimental release.

No date is promised. Gate by gate status is in [QUALIFICATION.md](QUALIFICATION.md) (column `pce`), and what a new machine
must do is in [NEW_MACHINE.md](NEW_MACHINE.md).
