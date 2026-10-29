# Documentation index

Retro-Recomp turns the game files you own (cartridge dumps, arcade romsets, disk images) into standalone Windows or
Linux programs. It translates as much of each game as possible into native code, checks that code against a reference
processor, and keeps a counted interpreter as a fallback for the rest: what still runs interpreted is always reported,
never hidden. Nine machines are covered today: Master System, Game Gear, Game Boy, NES, Mega Drive, Super Nintendo, Neo
Geo, Capcom CPS-1 and Sharp X68000 (the last two are experimental).

**Where to start**

- *I want to install it and play:* [INSTALLING.md](INSTALLING.md), then [CONTROLS.md](CONTROLS.md).
- *I want to know whether my game works:* [COMPATIBILITY.md](COMPATIBILITY.md) and the page of your machine below; games known not to convert are in [KNOWN_FAILURES.md](KNOWN_FAILURES.md).
- *I want to understand how it works:* [ARCHITECTURE.md](ARCHITECTURE.md), then the page of a processor.
- *I want to change the code or add a machine:* [AGENTS_GUIDE.md](AGENTS_GUIDE.md), [STANDARDS.md](STANDARDS.md),
  [BUILDING.md](BUILDING.md) and [NEW_MACHINE.md](NEW_MACHINE.md).

**What it does, and where each part is described**

- *Convert a collection:* detect the machine, discover the code, translate it, compare it with a reference
  ([ARCHITECTURE.md](ARCHITECTURE.md), scan levels in [CONSOLES_16BIT.md](CONSOLES_16BIT.md#scan-levels)).
- *Keep games current:* upgrade exports without rediscovery ([UPGRADES.md](UPGRADES.md)), the Compiled Games collection
  ([COMPILED_GAMES.md](COMPILED_GAMES.md)).
- *Learn and share:* games save fallback hints when they close ([RUNTIME_FEEDBACK.md](RUNTIME_FEEDBACK.md)); verified
  paths are shared between players ([COMPILATION_LIBRARY.md](COMPILATION_LIBRARY.md)).
- *Play:* one menu on every machine, quick states, languages, light guns
  ([CONTROLS.md](CONTROLS.md), [GAME_STATES.md](GAME_STATES.md), [LANGUAGES.md](LANGUAGES.md)).

The documentation follows how the project is built, along two crossing axes: the **processors** (recompilation, paths,
fixes, test vectors) and the **machines** (processors plus video, sound, cartridges and options). Native code, CPU
fidelity, hardware fidelity, gameplay validation and physical latency are five separate measures in every page.

| Machine | 68000 | Z80 | 6502 | SM83 | 65816 and SPC700 |
|---|---|---|---|---|---|
| [Master System](MASTER_SYSTEM.md) | none | main | none | none | none |
| [Game Gear](GAME_GEAR.md) | none | main | none | none | none |
| [Game Boy](GAME_BOY.md) | none | none | none | main | none |
| [NES](NES.md) | none | none | main | none | none |
| [Mega Drive](MEGADRIVE.md) | main | sound | none | none | none |
| [Super Nintendo](SNES.md) | none | none | none | none | main (65816), sound (SPC700) |
| [Neo Geo](NEOGEO.md) | main | sound | none | none | none |
| [Capcom CPS-1](CPS1.md) | main | sound | none | none | none |
| [Sharp X68000](X68000.md) | main | none | none | none | none |
| *Processor page* | [CPU_68000.md](CPU_68000.md) | [CPU_Z80.md](CPU_Z80.md) | [CPU_6502.md](CPU_6502.md) | [CPU_SM83.md](CPU_SM83.md) | [CPU_65816_SPC700.md](CPU_65816_SPC700.md) |

"Main" is the processor that runs the game; "sound" is a processor dedicated to the sound chips. The X68000 has no
sound processor in the project: its YM2151 and ADPCM are part of the reference machine.

## Play

- [INSTALLING.md](INSTALLING.md) — which file to download, Windows installers and portable downloads, your first game.
- [CONTROLS.md](CONTROLS.md) — shortcut table for every console profile.
- [GAME_STATES.md](GAME_STATES.md) — persistent F8/F9 game states.
- [LANGUAGES.md](LANGUAGES.md) — interface and generated-game languages.
- [BOXART.md](BOXART.md) — box art and game icons.
- [COMPILED_GAMES.md](COMPILED_GAMES.md) — the compiled-games list and controller browsing.
- [LINUX.md](LINUX.md) — Linux package, launchers, build tools and cover accounts.
- [AUDIO.md](AUDIO.md) — audio output per console.
- [VIDEO.md](VIDEO.md) — video presentation and timing: filters, scanlines, display modes.
- [COMPATIBILITY.md](COMPATIBILITY.md) — compatibility and evidence per console profile.
- [CREDITS.md](CREDITS.md) — animated credits and module playback.
- [SCREENSHOTS.md](SCREENSHOTS.md) — the converter's windows in pictures.

## How it is built

- [ARCHITECTURE.md](ARCHITECTURE.md) — converter pipeline, native backends, the five measures kept separate.
- [SYSTEM_PROFILES.md](SYSTEM_PROFILES.md) — console profiles and video standards.
- [HOST_KIT.md](HOST_KIT.md) — the common host kit contract for exported games: machine-core interface, one behaviour per host divergence, preferences migration and the migration order.
- [COMPILATION_LIBRARY.md](COMPILATION_LIBRARY.md) — shared compilation knowledge: per-console and per-ROM observations, embedded snapshot.
- [RUNTIME_FEEDBACK.md](RUNTIME_FEEDBACK.md) — gameplay fallback feedback written by the exported games.
- [RUNTIME_PERFORMANCE.md](RUNTIME_PERFORMANCE.md) — runtime performance work that does not change the output.
- [STANDARDS.md](STANDARDS.md) — the rules every change follows, the target shape (profiles, CPU-keyed paths, reports, host kit) and the "supported" checklist.
- [BUILDING.md](BUILDING.md) — build and run from source.

## Processors

Each page covers one processor family across all the machines that use it: who uses it, the recompiler and its
upstream, how code is found and translated, what stays interpreted, semantics and timing, tests and vectors.

- [CPU_68000.md](CPU_68000.md) — Motorola 68000: Mega Drive, Neo Geo, Capcom CPS-1, Sharp X68000.
- [CPU_Z80.md](CPU_Z80.md) — Zilog Z80: Master System and Game Gear (main), Mega Drive, Neo Geo and CPS-1 (sound).
- [CPU_6502.md](CPU_6502.md) — 6502 (Ricoh 2A03 and 2A07): NES.
- [CPU_SM83.md](CPU_SM83.md) — SM83: the original Game Boy.
- [CPU_65816_SPC700.md](CPU_65816_SPC700.md) — 65816 and SPC700: Super Nintendo.

## Machines

Each machine has a page (status, structure of the machine, engine and upstream, controls, states and saves,
qualification, known limits), often a `_LOG` companion with the dated evidence, and deep dives.

- **Master System** — [MASTER_SYSTEM.md](MASTER_SYSTEM.md). Deep dive: [LIGHT_PHASER.md](LIGHT_PHASER.md) (the Light Phaser).
- **Game Gear** — [GAME_GEAR.md](GAME_GEAR.md), sharing the Master System engine.
- **Game Boy** — [GAME_BOY.md](GAME_BOY.md) (original DMG profile and qualification); log: [GAME_BOY_LOG.md](GAME_BOY_LOG.md).
- **NES** — [NES.md](NES.md) (profile, cartridge and peripheral scope); log: [NES_LOG.md](NES_LOG.md).
- **Mega Drive** — [MEGADRIVE.md](MEGADRIVE.md); log: [MEGADRIVE_LOG.md](MEGADRIVE_LOG.md). Deep dives:
  [MEGADRIVE_CPU_EXCEPTIONS.md](MEGADRIVE_CPU_EXCEPTIONS.md) (synchronous MC68000 exceptions),
  [MEGADRIVE_EEPROM.md](MEGADRIVE_EEPROM.md) (serial EEPROM wire model),
  [MEGADRIVE_MAPPERS.md](MEGADRIVE_MAPPERS.md) (cartridge bank mapping),
  [MEGADRIVE_PREFETCH.md](MEGADRIVE_PREFETCH.md) (MC68000 prefetch and transaction phases),
  [MEGADRIVE_VIDEO.md](MEGADRIVE_VIDEO.md) (video qualification),
  [MEGADRIVE_Z80_TIMING.md](MEGADRIVE_Z80_TIMING.md) (Z80 machine-cycle placement).
- **Super Nintendo** — [SNES.md](SNES.md); log: [SNES_LOG.md](SNES_LOG.md). Deep dive:
  [SNES_SUPERFX.md](SNES_SUPERFX.md) (Super FX (GSU) study, experimental first slice and costed plan).
- **What the two 16-bit machines share** — [CONSOLES_16BIT.md](CONSOLES_16BIT.md) (game interface, scan levels, build and
  dependency contract) and [GUNS_16BIT.md](GUNS_16BIT.md) (Menacer, Justifier and Super Scope input).
- **Neo Geo** — [NEOGEO.md](NEOGEO.md); log: [NEOGEO_LOG.md](NEOGEO_LOG.md).
- **Capcom CPS-1** — [CPS1.md](CPS1.md) (experimental: conversion, controls, first qualified sets); log: [CPS1_LOG.md](CPS1_LOG.md).
- **Sharp X68000** — [X68000.md](X68000.md) (experimental: availability and licences).

## Running the project

- [QUALIFICATION.md](QUALIFICATION.md) — per-console qualification record: the G1-G16 gates, the status matrix and the owner-acceptance log.
- [UPGRADES.md](UPGRADES.md) — upgrading exports without rediscovery; host versus game inputs.
- [UPSTREAMS.md](UPSTREAMS.md) — every pinned upstream repository (revision, where it is pinned, licence, what we compile, last review), how to check them with `tools/check_upstreams.py`, the rules for moving a pin or carrying a fix, and the deferred list.
- [NEW_MACHINE.md](NEW_MACHINE.md) — the template for adding a machine (experimental, then supported), measured on an Atari ST dry run, with what is still scattered.
- [RELEASE_NOTES.md](RELEASE_NOTES.md) — what changed, release by release.
- [ROADMAP.md](ROADMAP.md) — current scope and the next machines.
- [QUALITY_REVIEW.md](QUALITY_REVIEW.md) — final local review before a release.
- [AGENTS_GUIDE.md](AGENTS_GUIDE.md) — entry page for coding agents and assistants: repository map, checks without ROM, the pitfalls (roles and stamps, public file list, no ROM, the five measures).
- The [README](../README.md) is the front page of the repository.

## Local documents (not in the repository)

Public documents live in this repository. Local documents stay on the development machine: they are listed by name
only, so that a reader knows they exist, and they may cite private evidence under `.build/` that is not published.

- `SPECIALISTS.md` — the machine specialist agents (one per machine or shared engine), their files in `.claude/agents/` and what stays with the lead session.
- `PROJECT_STATE.md` — resume point: the current release cycle and the previous one. Older sections are archived under `history/state/`, indexed by period in its `README.md`.
- `history/x68000/README.md` — the closed X68000 development stages (blocks 1 to 9, GPL-free plan, porting notes).
- Studies: `AMIGA_NEOGEO_RESEARCH.md`, `AUTO_EXPLORATION.md`, `CPS1_RESEARCH.md`, `LEGACY_32BIT_STUDY.md`, `LINUX_PORT_PLAN.md`, `LLM_GAMEPLAY_FEASIBILITY.md`, `MEGADRIVE_SNES_RESEARCH.md`, `NEOGEO_PLAN.md`, `SHARP_X68000_RESEARCH.md`, `research/ONLINE_DISCUSSION_2026-09-27.txt`.
- Qualification notes: `MEGADRIVE_STABILIZATION.md`, `NATIVE_COVERAGE.md`.
- X68000 references still current: `X68000_GLUE_SPEC.md` (behavioural specification of the MIT glue), `X68000_REFERENCE_LICENSES.md` (licence audit read by `tools/x68000_reference.py`).
- Interface notes from the 0.10.x releases: `DATAS_AND_BATCH.md`, `INTERFACE_AND_LANGUAGES.md`, `PLAYER2.md`, `VIDEO_AND_REGENERATION.md`.

`python tools/check_doc_links.py` verifies that every relative link in the documentation points at an existing file; `--public` restricts the check to the files of the public repository.
