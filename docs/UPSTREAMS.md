# Upstream repositories

Retro-Recomp builds on pinned revisions of other people's repositories. This page says, at any time, which ones,
where each pin lives in the code, under which licence, what we compile from it, and where it stood at the last
review. It also holds the rules for moving a pin, the method that measures what a move would cost, and the list of
upstream work we chose to leave for later, each with the event that would bring it back.

Last full review: **29 October 2026**, against the upstream state of that day. Every pin below was read from the
code, not from a note. The tool [`tools/check_upstreams.py`](../tools/check_upstreams.py) redoes the comparison in
one command; [How to record a review](#how-to-record-a-review) says what to update after it.

## Where the list comes from

The list is declared in [`retrorecomp/upstreams.py`](../retrorecomp/upstreams.py), one entry per machine plus a
shared list (SDL, the toolchain, the independent CPU vectors). An upstream used by several machines is defined once
and appears once here, with all its consoles. The revisions themselves are never copied into that file: each entry
says where the code holds its pin, and the tool and the tests read it from there. A new machine declares its
upstreams in the same change as its profile ([NEW_MACHINE.md](NEW_MACHINE.md)), and adds its rows to the two tables
below. `tests/test_upstreams.py` fails when a machine has no declaration, when a declared pin cannot be read, and
when a pin or a repository is missing from this page.

Console ids: `sms` Master System, `gg` Game Gear, `gb` Game Boy, `nes` NES, `md` Mega Drive, `snes` Super Nintendo,
`ng` Neo Geo, `cps1` Capcom CPS-1, `x68` Sharp X68000.

## The pins

| Upstream | Consoles | Pin | Full revision | Pinned in |
|---|---|---|---|---|
| [mstan/smsggrecomp](https://github.com/mstan/smsggrecomp) | sms, gg | `224d5bb` | `224d5bb2c150a2c295033d35dec629ef9ee42940` | `core.ENGINE_REV` |
| [mstan/z80-recomp-core](https://github.com/mstan/z80-recomp-core) (submodule) | sms, gg, md | `0e6606a` | `0e6606a41245d54c5fd0c3dc322ef9d6890d3923` | submodule `external/z80-recomp-core` of smsggrecomp and segagenesisrecomp |
| [arcanite24/gb-recompiled](https://github.com/arcanite24/gb-recompiled) | gb | `9150f87` | `9150f87d82fa98abcb6ea22329170463f9702eb8` | `gameboy.ENGINE_REV` |
| [mstan/nesrecomp](https://github.com/mstan/nesrecomp) | nes | `1b0c621` | `1b0c621a927db17afa9723bf456a89ad15809907` | `nes.ENGINE_REV` |
| [mstan/segagenesisrecomp](https://github.com/mstan/segagenesisrecomp) | md, ng, cps1, x68 | `00c60bc` | `00c60bc855a7998f92e5614585d52bca8fffcaf2` | `console16.REPOSITORIES['md']` |
| [mstan/m68k-recomp-core](https://github.com/mstan/m68k-recomp-core) (submodule) | md, ng, cps1, x68 | `921f67b` | `921f67b1e62bf24ee0a8f2aaad0ff50cbbc4b41a` | submodule `external/m68k-recomp-core` of segagenesisrecomp |
| [RetroPortingToolKit/rbengine](https://github.com/RetroPortingToolKit/rbengine) (submodule) | md | `2a03e73` | `2a03e73693acee0fb78076ea058642c931bef12e` | submodule `external/rbengine` of segagenesisrecomp |
| [RetroPortingToolKit/snesrecomp](https://github.com/RetroPortingToolKit/snesrecomp) | snes | `a00df26` | `a00df26a87831113fec91b9225bf16b049d40775` | `console16.REPOSITORIES['snes']` |
| [libretro/geolith-libretro](https://github.com/libretro/geolith-libretro) | ng, cps1, x68 | `2dc88e3` | `2dc88e3fa72ff404213a65d6eb5bb33baa687f73` | `neogeo_build.GEOLITH_REV` |
| [carmiker/lithogen](https://github.com/carmiker/lithogen) | ng | `ef0f9bd` | `ef0f9bd94e31689def44b49e0f8351e0206b622d` | `neogeo_build.LITHOGEN_REV` (also `neogeo_catalogue.LOADER`) |
| [aaronsgiles/ymfm](https://github.com/aaronsgiles/ymfm) | cps1 | `81aec25` | `81aec25ccbb98f4873a255f7551ac4dadac59b4a` | `cps1_build.YMFM_REVISION` |
| [mamedev/mame](https://github.com/mamedev/mame) | cps1 | `61a2229` | `61a222977fd29f22ce11fbea3f7c290fd7ced091` | `cps1_catalogue.MAME_REVISION` (also `tools/build_cps1_catalogue.MAME_REVISION`) |
| [hissorii/px68k](https://github.com/hissorii/px68k) | x68 | `74ddbb3` | `74ddbb37b4e12b77362a4e12f28ceb5aaa593684` | `tools/x68000_reference.HISSORII_REV` (also `tools/x68000_base74.COMMIT`) |
| [libretro/px68k-libretro](https://github.com/libretro/px68k-libretro) | x68 | `0ad84d7` | `0ad84d7058a12b7db4f7f7a906e87fad4e2f26f6` | `tools/x68000_reference.PX68K_REV` (also `native/x68000_machine/provenance.json`) |
| [libsdl-org/SDL](https://github.com/libsdl-org/SDL) | all | `5d24957` (release 2.32.10) | `5d249570393f7a37e037abf22cd6012a4cc56a71` | `core.SDL_REV` |
| [mstorsjo/llvm-mingw](https://github.com/mstorsjo/llvm-mingw) | all (Windows build) | `20261006` | `20261006` | `toolchain.LLVM_MINGW_VERSION` |
| [Kitware/CMake](https://github.com/Kitware/CMake) | all (Windows build) | `4.4.4` | `4.4.4` | `toolchain.CMAKE_VERSION` |
| [ninja-build/ninja](https://github.com/ninja-build/ninja) | all (Windows build) | `1.13.2` | `1.13.2` | `toolchain.NINJA_VERSION` |
| [upx/upx](https://github.com/upx/upx) | all | `5.3.0` | `5.3.0` | `packing.UPX_VERSION` |
| [SingleStepTests/z80](https://github.com/SingleStepTests/z80) | sms, gg, md | `ebe1875` | `ebe1875d48f374bcfd4b505d8eb8ee751568b5f7` | `tools/fetch_z80_vectors.REVISION` |
| [SingleStepTests/m68000](https://github.com/SingleStepTests/m68000) | md | `64b2531` | `64b253116a3de04aaac4346c43680960dc9b67e5` | `tests/fixtures/md-prefetch/cases.json` (also `tests/fixtures/md-exceptions/cases.json`) |

The three submodule pins are not in our code: they are recorded by the pinned tree of their parent. The tool reads
them with `git ls-tree` on the pinned checkout under `.deps` when it is there, and asks GitHub for the parent's
tree otherwise. SDL is followed on its `release-2.32.x` branch, because the pin is a release commit and the
`SDL2` branch does not contain it.

## Role, licence, what we compile, and the last review

Licence summaries are those of [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md), which stays the authority.
"Ahead" counts upstream commits after our pin on the branch named in the first command of the next section.

| Upstream | Role | Licence | What we compile or use | Review of 29 Oct 2026 |
|---|---|---|---|---|
| [mstan/smsggrecomp](https://github.com/mstan/smsggrecomp) | Z80 recompiler and runner (Master System, Game Gear) | No licence declared; noncommercial permission reported by the project owner | Recompiler (rebuilt with our patches) and runner glue | 1 ahead. Its change (direct calls to paged addresses) is carried as our patch in 1.6.3. Keep the pin. |
| [mstan/z80-recomp-core](https://github.com/mstan/z80-recomp-core) | Z80 decoder and runtime headers | PolyForm Noncommercial 1.0.0 | Shared Z80 headers and sources used by the SMS/GG and Mega Drive engines | Identical to `main` (a side branch exists for a CD bus). Keep. |
| [arcanite24/gb-recompiled](https://github.com/arcanite24/gb-recompiled) | Game Boy recompiler and generated runtime | MIT | Compiler and runtime | Identical. Keep. |
| [mstan/nesrecomp](https://github.com/mstan/nesrecomp) | NES recompiler and cycle runtime | PolyForm Noncommercial 1.0.0 | Compiler and the cycle runtime (with its vendored emu2413) | 122 ahead. Nothing needed now; candidates in "Deferred". Keep. |
| [mstan/segagenesisrecomp](https://github.com/mstan/segagenesisrecomp) | Mega Drive recompiler and runner; source of the 68000 instruction bodies of four machines | PolyForm Noncommercial 1.0.0 plus retained vendor licences | Recompiler, `runner/`, `m68k_interp.c` (adapted by `m68000.adapt_semantics`); the CD code is not used | 106 ahead. A bump breaks 6 anchors. A 68000 fix is carried as our patch in 1.6.3. Keep. |
| [mstan/m68k-recomp-core](https://github.com/mstan/m68k-recomp-core) | 68000 decoder | PolyForm Noncommercial 1.0.0 | `common/m68k_decoder.h`, read by four generators | 11 ahead; a stricter decode validator, not shown to matter for us. Keep. |
| [RetroPortingToolKit/rbengine](https://github.com/RetroPortingToolKit/rbengine) | Rollback engine, submodule of the Mega Drive engine | MIT | Nothing: initialised with the checkout, linked only by upstream's own tests | Identical. Keep. |
| [RetroPortingToolKit/snesrecomp](https://github.com/RetroPortingToolKit/snesrecomp) | Super Nintendo interpreter and runner | PolyForm Noncommercial 1.0.0 plus MIT/ISC and other vendor licences | The 65816 interpreter, SPC700/DSP core and `runner/`; not the analyser | 200 ahead. A bump breaks an anchor. A 65816 timing fix is carried as our patch in 1.6.3. Keep. Checked 29 October 2026: hardware NMI/IRQ entry does not need upstream's `interp816_doInterrupt` (reached only through the SA-1 core, which Retro-Recomp refuses). The adapter's entry `rr_snes_cpu_interrupt` (since 1.0.0) stacks the bank only in native mode, charges 7 cycles in emulation mode and 8 in native, and takes `$FFFA/$FFFE` in emulation mode, `$FFEA/$FFEE` in native (`native/snes_bus_checks.c`, both modes). |
| [libretro/geolith-libretro](https://github.com/libretro/geolith-libretro) | Neo Geo hardware runtime; its Musashi 68000 is the reference CPU of Neo Geo, CPS-1 and X68000 | BSD-3-Clause | Machine, video and audio sources, `src/m68k` | Identical. Keep. |
| [carmiker/lithogen](https://github.com/carmiker/lithogen) | Neo Geo cartridge layout knowledge | BSD-3-Clause | The loader behind our ROM-free layout catalogue | Identical. Keep. |
| [aaronsgiles/ymfm](https://github.com/aaronsgiles/ymfm) | YM2151 emulation for CPS-1 | BSD-3-Clause | `ymfm.h`, `ymfm_fm.h`, `ymfm_fm.ipp`, `ymfm_opm.h`, `ymfm_opm.cpp` | Identical. Keep. |
| [mamedev/mame](https://github.com/mamedev/mame) | CPS-1 board data and OKI MSM6295 reference | BSD-3-Clause | No code is built from a checkout: the ROM-free catalogue and the OKI model are adapted from the driver | No change to the CPS-1 driver files, `cps1_v.cpp`, `cps1.h` or the OKI model since the pin (the rest of the repository moves daily and is not followed). Keep. |
| [hissorii/px68k](https://github.com/hissorii/px68k) | X68000 machine base, inactive since 2014 | Kenjo noncommercial terms, BSD-2-Clause (NONAKA), FMGEN freeware terms | Device sources (`x68k/`, `fmgen/`, line composition) adapted by `tools/x68000_base74.py` | Identical. Keep. |
| [libretro/px68k-libretro](https://github.com/libretro/px68k-libretro) | X68000 libretro port, private comparison mode only | GPL-2.0 | Nothing is compiled or shipped | 23 ahead. Reviewed on 29 October 2026 from the public pull-request texts only (no code read): two fixes carried as our own patches in 1.6.5, one not adopted ("Deferred"). Keep. |
| [libsdl-org/SDL](https://github.com/libsdl-org/SDL) | Window, audio and input library | zlib | The SDL2 library built from source and linked into the games | Moved from release 2.32.8 to the release 2.32.10 commit in 1.6.4 (36 commits, modest fixes: Switch Pro stick calibration and sensor coefficients, Pipewire device formats on Linux). Moves every console's game stamp. The newest SDL2 release; the branch is 88 commits ahead with unreleased work, not followed. Keep. |
| [mstorsjo/llvm-mingw](https://github.com/mstorsjo/llvm-mingw) | Portable Windows C toolchain | Apache-2.0 with LLVM exceptions; permissive runtime licences | Release archive checked by SHA-256 | `20261020` (LLVM 23.1.4) exists. Corrective. Keep. |
| [Kitware/CMake](https://github.com/Kitware/CMake) | Build generator | BSD-3-Clause | Release archive checked by SHA-256 | 4.4.5 exists. Corrective. Keep. |
| [ninja-build/ninja](https://github.com/ninja-build/ninja) | Build tool | Apache-2.0 | Release archive checked by SHA-256 | Current. |
| [upx/upx](https://github.com/upx/upx) | Executable packer | GPL with special exception for packed executables | Official 5.3.0 binaries and the source archive in `licenses/` | Current. |
| [SingleStepTests/z80](https://github.com/SingleStepTests/z80) | Independent Z80 vectors, development tests only | MIT | Fetched on demand into `.deps`; not shipped | Identical. Keep. |
| [SingleStepTests/m68000](https://github.com/SingleStepTests/m68000) | Independent 68000 vectors, development tests only | MIT | A small extract in `tests/fixtures`; not shipped | Identical. Keep. |

Licences of the four engines that PolyForm Noncommercial covers (nesrecomp, segagenesisrecomp, m68k-recomp-core,
snesrecomp) were compared with upstream on the review day: same terms, same files. Two third parties appear upstream
only after our pins (xxHash, BSD-2-Clause, in segagenesisrecomp; ares, ISC, for its CD code); they matter only if a
pin moves.

## How to check an upstream

One command checks all of them. It reads every pin from the code, then asks GitHub (through `gh` when it is
installed, through the public API otherwise) how many commits the default branch has after the pin, the compare URL,
and the date of the latest upstream commit. A failed request is reported on its own row and never stops the others.

```
python -B tools/check_upstreams.py                 # the table
python -B tools/check_upstreams.py --only snesrecomp --only SDL
python -B tools/check_upstreams.py --json          # the same rows as JSON
python -B tools/check_upstreams.py --list          # offline: only the pins the code holds
```

One repository by hand (the tool does exactly this):

```
gh api repos/<owner>/<repo>/compare/<pin>...<branch> --jq '{status, ahead_by, behind_by}'
gh api repos/<owner>/<repo>/compare/<pin>...<branch> --jq '.commits[] | .sha[0:7] + " " + (.commit.message | split("\n")[0])'
```

For a pin that is a version (llvm-mingw, CMake, Ninja, UPX) the tool compares with the latest release tag. For MAME
it counts only the commits that touch the CPS-1 driver files and the OKI model, since the rest of the repository
changes daily. For the submodules, ask for the parent's tree: `gh api repos/<parent>/contents/<path>?ref=<pin>`.

What to read next, in this order:

1. The list of upstream commits since the pin (the second command). Read the messages and the changed files, not
   only the count.
2. Which of those commits change a function we compile, or one that our adapters patch. Most commits on the engines
   are other consoles, tools or documentation.
3. A fix we want: take it as our own patch (next section) unless the change is too big to rewrite.
4. A change that forces a bump: measure the cost with the anchor method before deciding.
5. A licence change: read the new licence file first. Nothing moves until it is understood.

## Decision rule

**Moving a pin.** Our base of qualified paths is keyed by the pinned upstream revision of each console. Bumping a pin
therefore makes that console's qualified paths in the base lapse. A bump also means: repair the anchors that break
(see the anchor method), run a requalification campaign for the console, and expect the quick-state key to move
often, since the runtime state structures belong to the upstream. Do it for a reason (a feature we need, a defect we
cannot patch), for one console at a time, and not in the same release as another structural change.

**Carrying a fix as our own patch.** The pin stays, so the base stays. Only the game stamp of the consoles whose
generated code changes moves, with a note in [UPGRADES.md](UPGRADES.md) ("Exports of the previous release in the
new one"). The patch lives in the adapter function that already rewrites that upstream file, uses the strict helper
(`replace` or `replace_once`, which raise when the upstream text is not found, never a bare `str.replace`), and has
a unit test that the patched text contains the fix exactly once.

**Why a code-generation patch is honest.** The pinned revision keeps naming the upstream code we started from, and
the fix is visible in our repository as a change to an adapter that is an input of the game stamp. When the patch
changes the generated code, the game stamp of the consoles concerned moves, so an export of the previous release is
recognised as outdated and is rebuilt from its learned paths; nothing keeps running with the old code under a stamp
that claims the new one. The fix is a statement about CPU fidelity only. It says nothing about hardware fidelity,
gameplay validation or physical latency, which stay separate measures ([STANDARDS.md](STANDARDS.md), rule 8).

**Fallback and counting do not change.** A patch never hides an interpreted instruction: the counters stay per CPU
and per device.

## Licence rule

- **PolyForm Noncommercial upstreams are never copied.** This covers segagenesisrecomp, m68k-recomp-core,
  nesrecomp, snesrecomp and z80-recomp-core. We use them at their pinned revisions, downloaded on first conversion.
  A fix we want from them is rewritten by us from the processor manual (for example the MC68000 or 65816
  programmer's manual), never from the upstream diff. An anchor is a short search string that locates the place;
  the replacement text is ours.
- **GPL code (px68k-libretro after its 2020 relicensing) is rewritten from a description only.** What a defect does
  and what the correct behaviour is can be described; the code is not read while writing ours. The policy and the
  manifest of what may be kept are in [`native/x68000_machine/provenance.json`](../native/x68000_machine/provenance.json),
  and new items are added to its `reimplement_from_documentation` list before they are written.
- **Permissive upstreams** (MIT, BSD, zlib) may be adapted with their notice kept in `licenses/`; shared code stays
  MIT ([STANDARDS.md](STANDARDS.md), rule 10).
- A licence that changes upstream is read before any bump. A pin whose licence became worse for us does not move.

## The anchor method

A bump breaks our adapters when the upstream text they look for has changed. Measure it before deciding; do not guess
from the number of commits.

1. **Extract the anchors.** Parse each adapter module with `ast` and collect the literal first arguments of the
   strict helpers (`replace_once` of `core`, `replace` of `cpu`, `gun16_runtime`, `snes_timing`, and the local
   `replace` functions of the Mega Drive modules) and of the plain `str.replace` calls that act on upstream text.
   Those strings are the anchors; each one must be found, usually exactly once.
2. **Export the upstream tree.** Make a clean export (`git archive` or a clone under `.build/`) of the candidate
   revision. Never touch `.deps`.
3. **Replay the adapters.** Run our adapt functions on the exported files (the pipeline reads `.deps/<repo>`; point
   the replay at the export). Every anchor that raises is a break to repair. An adapter that no longer changes the
   output is a silent break: compare with the control.
4. **Keep a control.** Do the same replay at the pinned revision. It must pass with zero breaks and produce
   byte-identical output to the real pipeline; otherwise the replay itself is wrong.
5. **Read the result as a cost, not a verdict.** A count of broken anchors, which console they belong to, and
   whether a repaired anchor changes generated code (so the game stamp, and the qualified paths, go with it).
   The 29 October 2026 review measured it this way: 6 broken anchors for a Mega Drive bump (two of them in the
   68000 helpers shared by Neo Geo and CPS-1), 1 for a Super Nintendo bump, and 18 for a NES bump to the first
   revision that handles the Famicom Disk System.

The review scripts are not part of this repository; the method above is enough to rebuild them. Run Python on
exported upstream trees with `python -I`, so that a file of the export cannot shadow a module.

## Fixes carried as our own patches in 1.6.3

Three defects found by the review are repaired as patches on the current pins, without changing any pinned
revision. They are rewritten from the processor manuals. They are CPU fidelity fixes only.

| Fix | Consoles | Our file | Game stamp that moves |
|---|---|---|---|
| 68000: `ROXL`/`ROXR` with a register count of zero (modulo 64) must copy X into C, and `ASL.L` by 31 must compute the overflow mask without a 32-bit shift | md, ng, cps1, x68 | `m68000.py` (`adapt_semantics`) | those four consoles |
| 65816: `BRK` in native mode takes 8 cycles (7 in emulation mode) because the program bank is pushed; `COP` follows the mode (in emulation mode no bank pushed, 7 cycles, vector $FFF4) | snes | `snes_codegen.py` (`read_core`) | snes |
| Z80: a direct call to a paged address must go through the dispatch that checks the bank in place (the "functions" engine only; the default "banked" engine is not affected, and no game is known to trigger it) | sms, gg | `core.py` (`patched_generator_source`) | sms, gg |

Each is described in the section "CPU fixes carried from the upstream review in 1.6.3" of [UPGRADES.md](UPGRADES.md),
because existing exports of 1.6.2 are rebuilt from their learned paths. The `COP` correction in emulation mode goes beyond
upstream, which does not handle it either.

## Fixes carried as our own patches in 1.6.4

Defects of the Z80 "functions" engine (Master System and Game Gear), found on Alex Kidd in Miracle World and Factory Panic,
which that engine could not convert: the run ended early or the conversion stopped at the comparison with the reference
CPU. Both convert with the default "banked" engine, which is not affected. The pin does not move. They are CPU fidelity
fixes only; they change the share of native code only where a game stopped at the first affected frame and now goes on,
so that more of it is reached and compiled. Interpreter fallback stays counted per CPU. The last row is a Game Boy fix
for code a game runs from its RAM, described after the table.

| Fix | Consoles | Our file | Game stamp that moves |
|---|---|---|---|
| Z80 HALT in the generated function: the interrupt that ends it pushes the address after the HALT (the runner pushed the HALT's own address), and a handler that drops the halted frame (SP above its value at the HALT) now ends the function, as a call site already does, instead of letting the next `RET` unwind the whole C stack and end the run | sms, gg ("functions" engine only) | `core.py` (`patched_generator_source`) | sms, gg |
| Z80 interrupt acceptance in the runner of the "functions" engine: /INT is sampled at one instruction boundary and accepted at the next (including the boundary after the handler's own `RET`), as the reference CPU and the banked engine do, instead of at the boundary where the VDP made it visible, one instruction earlier (another pushed address, other registers seen by the handler, another cycle count in a polling loop); a VDP port access that raises or clears /INT brings the next sync to the next instruction instead of the next scanline; and a `RET` that unwinds every generated frame (a game that reloads SP and returns into its main code) continues at the address it popped instead of ending the run | sms, gg ("functions" engine only) | `core.py` (`prepare_functions_irq`, applied to the pinned `runner/glue.c`) | sms, gg |
| Game Boy: the pinned runtime's RAM stub (`gbrt_try_execute_ram_stub`) covers only part of the SM83 opcodes. Any other opcode executed from WRAM or HRAM (for example `LD HL,nn`, `LD A,(DE)`, `INC BC`, `ADD A,n` in a routine a game copies from its cartridge and patches) started an interpreter session that went on interpreting the ROM code the routine jumped to (Donkey Kong Land: 6,350 sessions, 3,160,836 interpreted cycles in 6,000 frames). The remaining non-prefixed, non-branch opcodes are now executed **one instruction at a time from their live bytes by a counted executor** (`rr_gb_try_ram_instruction`, behind `rr_gb_try_ram_dispatch`), after the guarded helpers and the stub have declined, and the ROM routine they jump to runs as native code again. The executor is not native code and not ahead-of-time translation: it is a per-opcode switch, written after the interpreter's own cases (same helpers, operand reads and cycle split), cheaper than an interpreter session. It, the upstream RAM stub and the upstream stub for code run from 0xFF00-0xFF7F (`gbrt_try_execute_highmem_stub`, also a per-opcode executor), the last two never counted before, are counted: instructions and guest cycles of each, per probe, in the conversion report. The counts cover the generated dispatch only; the same stubs called by the pinned interpreter inside a session are part of that session's instruction and cycle figures. The HRAM stub (`gbrt_try_execute_hram_stub`, the OAM-DMA wait routine matched by its bytes and run as one helper) is not counted, like our guarded helpers | gb | `native/gb_ram_helpers.h` (`rr_gb_try_ram_instruction`, `rr_gb_try_ram_dispatch`, `rr_gb_try_highmem_dispatch`), hooked and given its host-only counters by `gameboy_runtime.py` (`adapt_generated_project`: the `game.c` dispatch, the `GBContext` fields, the `[RR-RAM]` line of the summary); read by `gameboy.py` (`_probe`) and `report_schema.py` | gb |

The two Z80 fixes are described in [UPGRADES.md](UPGRADES.md#master-system-and-game-gear-the-functions-engine-164-lot-f). The second one is not a defect of the pin: it makes our
two engines agree on a convention that was ours to choose (the reference CPU follows it since the sampling change of 1.6.x,
`prepare_reference_irq`). Games that still fail the comparison with the "functions" engine for other reasons keep failing it; the banked
engine converts them. **Causes found on 29 October 2026** (first divergent write of the native run against its own interpreter twin, same
VDP, audio and memory; CPU fidelity against the project's reference only):

| Cause | Games | Status |
|---|---|---|
| A `RET` pops an address other than the one the generated C call stack expects: Action Fighter pushes `$0677`, jumps into a shared tail that ends in `ret nz` (`$0693`), and the Z80 continues at `$0677` while the generated function returns to its caller (frame 2530) | Action Fighter | proved; a general fix would compare the popped address with the one the caller pushed and dispatch to it, which is a change of the call model, not a patch |
| A repeating block instruction (`LDIR` at `$087B`) interrupted before it ends: the generated body sets the X and Y flags from the last byte copied, the Z80 and our corrected reference set them from the high byte of the PC while it repeats, so the AF pushed by the interrupt differs (`$64` against `$4C`) | Alex Kidd: High-Tech World (frame 69), Alex Kidd: The Lost Stars (frame 64, same bit pattern) | proved on the first divergent write; a general, small CPU-fidelity patch of the block instructions of the generator is possible |
| The interrupt is accepted at another instruction boundary than in the reference (one to a few instructions earlier or later): Sonic Spinball (Game Gear) pushes `$0562` instead of `$0566` in an `ei; ld a,(nn); cp b; jr nz` wait loop, Super Columns breaks a clear loop one iteration earlier, Sonic Triple Trouble takes it before a write the reference makes first | Sonic Spinball (Game Gear; the Master System edition passes), Super Columns, Sonic Triple Trouble | first divergence located, boundary rule not yet isolated (the tick placement around `EI` and the sampling patch of 1.6.4 are the places to read) |

The pinned compiler and runtime are untouched (the cached checkout must stay clean); every hook is a `replace_once` on the generated
project. `tools/gameboy_ram_selftest.py` builds the adapted runtime and compares every handled opcode with the pinned interpreter
(177 opcodes, 24 random states at each of four placements, WRAM and HRAM, memory, flags, cycles and timed bus effects), and checks the
counters (and, on the fixture of the trampoline test, that an interpreter session counts the stub instructions it runs itself as its own
instructions and cycles, with the dispatch counters left at zero). **Counting.** `final_checks` and `history` carry `ram_stub_instructions`,
`ram_stub_cycles`, `ram_single_step_instructions`, `ram_single_step_cycles`, `highmem_stub_instructions` and `highmem_stub_cycles` for each
probe; the schema-2 report carries them as `cpus[].scenarios[].ram_single_step` with a `ram_single_step_present` flag, and while that flag
is true the report's `native_code.zero_fallback_on_tested_scenarios` is false and its claim says that some WRAM/HRAM and 0xFF00-0xFF7F
instructions run one at a time by counted executors, not as native code (the interpreter figures stay what they are: sessions, instructions
and cycles of the interpreter). **Scope of the counts.** They cover what the generated dispatch runs, through two hooks: the upstream RAM stub
and the single-instruction executor through `rr_gb_try_ram_dispatch`, and the upstream stub for 0xFF00-0xFF7F through
`rr_gb_try_highmem_dispatch` (both `replace_once` on the generated `game.c`). Inside an interpreter session the pinned interpreter calls the
same stubs itself, and `continue`s past its own switch; the session loop has already counted that iteration, so those instructions are in the
session's instruction count and their cycles in its cycles (interpreter use, already shown) and are deliberately not added to the dispatch
counters. The HRAM stub (`gbrt_try_execute_hram_stub`) matches the whole OAM-DMA wait routine by its bytes and runs it as one batched helper,
the same category as our guarded multi-instruction helpers, and is not counted. The window adds "N RAM instructions executed one by one (not native)"
to the line of a finished conversion, and the library lists such a game as a game with fallback. The guarded multi-instruction helpers
(named routines checked by a live signature: store-and-increment, copies, DMA page selection) are not counted, as before. The change is a
statement about CPU fidelity of writable-memory code only; it says nothing about hardware fidelity, gameplay validation or physical
latency. Instructions that still reach the interpreter (`CB`-prefixed opcodes, `HALT`, `STOP`, `RST` outside the 0xFF00-0xFF7F stub, which
executes `RST 00` to `RST 38`, illegal opcodes, code spanning two memory regions) stay counted as interpreter use. See "Game Boy exports in 1.6.4" in [UPGRADES.md](UPGRADES.md).

## Fixes carried as our own patches in 1.6.5

Two of the three px68k-libretro fixes that were deferred are carried as patches of the machine base (`tools/x68000_base74.py`, which
adapts the pinned hissorii/px68k files at build time). The pin does not move. They were written from the public pull-request texts
(libretro/px68k-libretro pull requests 225 and 226), from the behaviour of MAME's HD63450 (BSD-3-Clause) and from our own reading of
the pinned line drawing; no libretro code was read, and both are listed in `reimplement_from_documentation` of
[`provenance.json`](../native/x68000_machine/provenance.json). Each has an authored reproducer in the suite that fails on the previous
code. They change what the machine does in two cases and say nothing about hardware fidelity.

| Fix | Our file | Reproducer | Game stamp that moves |
|---|---|---|---|
| A DMA START on a channel that is still active, or whose completion or error flags were not acknowledged, restarts the channel with those flags cleared instead of ending in an operation timing error (CER `0x02`). | `tools/x68000_base74.py` (`adapt_dmac`) | `tests/test_x68000_dmac.py` | x68 |
| A write to a sprite register marks the screen lines the sprite covers by the mapping the line drawing uses, not sixteen lines at an offset that ignores the background's vertical start and the line counts of the background and the display. | `tools/x68000_base74.py` (`adapt_bg`) | `tests/test_x68000_sprite_dirty.py` | x68 |

The first fix agrees with MAME (the `hd63450.cpp` read on 29 October 2026 never raises the timing error on a start); the pinned base
ended the channel with that error. The libretro fork reports a game whose ADPCM stopped for that reason; we have not looked for a game of our collection
that depends on it. The second is a defect of the pinned base itself, found with its reproducer; the pull request names frozen sprites
in Gardis Light 2.10, which is in our test collection and has not been converted again for this change. The reproducer shows 2 of 16 lines left unmarked at a 2-line start offset, and 32 of 64 with a 256-line background on a 512-line display.
Both are described in [UPGRADES.md](UPGRADES.md#x68000-dma-channel-restart-and-moved-sprite-redraw-165).

## Deferred

Upstream work that is worth having but not taken yet, with the event that brings it back. Time measurements need a
quiet machine, so anything that has to be timed waits for that.

| Topic | Upstream | Why not now | Trigger |
|---|---|---|---|
| SNES: idle detector with hash buckets | snesrecomp (`interp_bridge.c`) | Same behaviour, faster lookup instead of a linear scan per instruction. Needs a timing measurement. | Next SNES performance pass, with an A/B comparison of frame fingerprints. |
| SNES: APU advance by blocks | snesrecomp | State of the SPC700/DSP and the sound must be proven equal before any timing. | Same pass. |
| SNES: revision bump | snesrecomp, about 200 commits | One anchor really breaks (`snes_chips.py`, `dsp1()`); CMake defaults would silently switch to a different native mode on Windows x64; little gain on the code we run. | The planned SNES requalification campaign; it brings DSP-1 compile-time HLE and transactional state loading. |
| NES: MMC1 without table rebuild on a no-effect A12 change | nesrecomp (`hw_mapper.c`) | Gain not isolated yet. | NES performance pass, A/B on two MMC1 games. |
| NES: larger known-cartridge database | nesrecomp (195 entries to 3,825) | Its record structure changes and the provenance must be written down. | Before widening NES compatibility. |
| NES: Famicom Disk System | nesrecomp, about thirty commits | Needs a bump (18 anchors break), a player-supplied BIOS, a Disk action in the host kit and a full NES requalification. Upstream excluded the FDS from its own validation. | A decision to support the FDS. |
| Mega Drive: revision bump | segagenesisrecomp, 106 commits | 6 anchors break, including the divide and clear helpers in `m68000.py`, which Neo Geo and CPS-1 share. The rest duplicates what we have. | A Mega-CD decision (below). |
| Mega-CD | segagenesisrecomp (`runner/cd/`) | Per-disc recipes; strict native execution with no counted fallback, against our rule; BIOS and disc images required. | A "new machine" decision ([NEW_MACHINE.md](NEW_MACHINE.md)). |
| X68000: paired-bit OR in the graphic layer, and text transparency tested at one priority (px68k-libretro pull request 228, GPL, rewrite from description only) | px68k-libretro | The first part changes a behaviour the pull request itself calls unsure in other emulators (it picks one of the two likeliest readings of the documents); the second turns the text transparency test on at one priority so that a game's water composites. Neither has a reference here: the two games it names are not in our test collection, and no document of the machine settles the first. Not adopted. | A game of the collection that shows the problem, or a document of the machine that gives the behaviour; then write it from that, list it in `provenance.json`, and add a reproducer like `tests/test_x68000_sprite_dirty.py`. |
| 68000: timing of register-count shifts | segagenesisrecomp (`m68k_interp.c`) | The pinned core charges a fixed estimate to every shift with a register count; results and flags are right, the clocks are approximate (the shift vectors are replayed with `timing_unchecked`). | A Mega Drive timing pass, or a game whose timing depends on long shifts. |
| llvm-mingw `20261020`, CMake 4.4.5 | toolchain | Corrective versions; nothing needed. | The next toolchain change. |

## How to record a review

After running the check, in one change:

1. Run `python -B tools/check_upstreams.py` and read the commits of every row that is ahead (see "How to check an
   upstream").
2. Update the line "Last full review" at the top with the date, and the last column of the second table with the
   date's verdict for each upstream: keep, patch, bump, or new finding. Put the ahead count in the verdict.
3. If a pin moved, change it in the code first, then both tables here (short and full hash); the test fails until
   they agree. Add the bump to the release notes and, if the qualified paths of a console lapse, to
   [COMPILATION_LIBRARY.md](COMPILATION_LIBRARY.md).
4. A fix taken as our patch goes in "Fixes carried as our own patches" and in [UPGRADES.md](UPGRADES.md); a decision to
   wait goes in "Deferred" with its trigger.
5. Run `python -B -m unittest tests.test_upstreams`, `python -B tools/prepare_publication.py --tracked` and
   `python -B tools/check_doc_links.py --public`.

The review date lives on this page only. The tool shows where upstream stands today; this page says what we decided
about it and when.
