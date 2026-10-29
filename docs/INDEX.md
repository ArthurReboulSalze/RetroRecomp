# Documentation index

One line per document, grouped by theme and console. Public documents live in
this repository. Local documents stay on the development machine: they are
listed by name only, so that a reader knows they exist, and they may cite
private evidence under `.build/` that is not published.

## Start here

- [README](../README.md) — what Retro-Recomp does, downloads, supported consoles.
- [COMPATIBILITY.md](COMPATIBILITY.md) — compatibility and evidence per console profile.
- [ROADMAP.md](ROADMAP.md) — current scope and the next machines.
- [RELEASE_NOTES.md](RELEASE_NOTES.md) — what changed, release by release.
- [QUALITY_REVIEW.md](QUALITY_REVIEW.md) — final local review before a release.

## Install, build, play

- [INSTALLING.md](INSTALLING.md) — Windows installers and portable downloads.
- [BUILDING.md](BUILDING.md) — build and run from source.
- [LINUX.md](LINUX.md) — Linux package, launchers, build tools and cover accounts.
- [CONTROLS.md](CONTROLS.md) — shortcut table for every console profile.
- [LANGUAGES.md](LANGUAGES.md) — interface and generated-game languages.
- [COMPILED_GAMES.md](COMPILED_GAMES.md) — the compiled-games list and controller browsing.
- [GAME_STATES.md](GAME_STATES.md) — persistent F8/F9 game states.
- [BOXART.md](BOXART.md) — box art and game icons.
- [CREDITS.md](CREDITS.md) — animated credits and module playback.

## Converter and shared runtime

- [ARCHITECTURE.md](ARCHITECTURE.md) — converter pipeline, native backends, the five measures kept separate.
- [STANDARDS.md](STANDARDS.md) — the rules every change follows, the target shape (profiles, CPU-keyed paths, reports, host kit) and the "supported" checklist.
- [AGENTS_GUIDE.md](AGENTS_GUIDE.md) — entry page for coding agents and assistants: repository map, checks without ROM, the pitfalls (roles and stamps, public file list, no ROM, the five measures).
- [HOST_KIT.md](HOST_KIT.md) — the common host kit contract for exported games: machine-core interface, one behaviour per host divergence, preferences migration and the migration order.
- [QUALIFICATION.md](QUALIFICATION.md) — per-console qualification record: the G1-G16 gates, the status matrix and the owner-acceptance log.
- [NEW_MACHINE.md](NEW_MACHINE.md) — the template for adding a machine (experimental, then supported), measured on an Atari ST dry run, with what is still scattered.
- [COMPILATION_LIBRARY.md](COMPILATION_LIBRARY.md) — shared compilation knowledge: per-console and per-ROM observations, embedded snapshot.
- [RUNTIME_FEEDBACK.md](RUNTIME_FEEDBACK.md) — gameplay fallback feedback written by the exported games.
- [UPGRADES.md](UPGRADES.md) — upgrading exports without rediscovery; host versus game inputs.
- [UPSTREAMS.md](UPSTREAMS.md) — every pinned upstream repository (revision, where it is pinned, licence, what we compile, last review), how to check them with `tools/check_upstreams.py`, the rules for moving a pin or carrying a fix, and the deferred list.
- [RUNTIME_PERFORMANCE.md](RUNTIME_PERFORMANCE.md) — runtime performance work that does not change the output.
- [SYSTEM_PROFILES.md](SYSTEM_PROFILES.md) — console profiles and video standards.
- [VIDEO.md](VIDEO.md) — video presentation and timing: filters, scanlines, display modes.
- [AUDIO.md](AUDIO.md) — audio output per console.

## Consoles

### Master System and Game Gear

- [GAME_GEAR.md](GAME_GEAR.md) — Game Gear profile.
- [LIGHT_PHASER.md](LIGHT_PHASER.md) — Master System Light Phaser.

### Game Boy

- [GAME_BOY.md](GAME_BOY.md) — original DMG profile and qualification.

### NES

- [NES.md](NES.md) — NES profile, cartridge and peripheral scope.

### Mega Drive and Super Nintendo

- [CONSOLES_16BIT.md](CONSOLES_16BIT.md) — Mega Drive and Super Nintendo profiles.
- [GUNS_16BIT.md](GUNS_16BIT.md) — Menacer, Justifier and Super Scope input.
- [MEGADRIVE_CPU_EXCEPTIONS.md](MEGADRIVE_CPU_EXCEPTIONS.md) — synchronous MC68000 exceptions.
- [MEGADRIVE_EEPROM.md](MEGADRIVE_EEPROM.md) — serial EEPROM wire model.
- [MEGADRIVE_MAPPERS.md](MEGADRIVE_MAPPERS.md) — cartridge bank mapping.
- [MEGADRIVE_PREFETCH.md](MEGADRIVE_PREFETCH.md) — MC68000 prefetch and transaction phases.
- [MEGADRIVE_VIDEO.md](MEGADRIVE_VIDEO.md) — Mega Drive video qualification.
- [MEGADRIVE_Z80_TIMING.md](MEGADRIVE_Z80_TIMING.md) — Z80 machine-cycle placement.
- [SNES.md](SNES.md) — Super Nintendo development and qualification.
- [SNES_SUPERFX.md](SNES_SUPERFX.md) — Super FX (GSU) study, experimental first slice and costed plan.

### Neo Geo

- [NEOGEO.md](NEOGEO.md) — Neo Geo development and qualification.

### Capcom CPS-1

- [CPS1.md](CPS1.md) — Capcom CPS-1 profile: conversion, controls, first qualified sets.

### Sharp X68000

- [X68000.md](X68000.md) — experimental X68000 profile, availability and licences.

## Local documents (not in the repository)

- `SPECIALISTS.md` — the machine specialist agents (one per machine or shared engine), their files in `.claude/agents/` and what stays with the lead session.
- `PROJECT_STATE.md` — resume point: the current release cycle and the previous one. Older sections are archived under `history/state/`, indexed by period in its `README.md`.
- `history/x68000/README.md` — the closed X68000 development stages (blocks 1 to 9, GPL-free plan, porting notes).
- Studies: `AMIGA_NEOGEO_RESEARCH.md`, `AUTO_EXPLORATION.md`, `CPS1_RESEARCH.md`, `LEGACY_32BIT_STUDY.md`, `LINUX_PORT_PLAN.md`, `LLM_GAMEPLAY_FEASIBILITY.md`, `MEGADRIVE_SNES_RESEARCH.md`, `NEOGEO_PLAN.md`, `SHARP_X68000_RESEARCH.md`, `research/ONLINE_DISCUSSION_2026-09-27.txt`.
- Qualification notes: `MEGADRIVE_STABILIZATION.md`, `NATIVE_COVERAGE.md`.
- X68000 references still current: `X68000_GLUE_SPEC.md` (behavioural specification of the MIT glue), `X68000_REFERENCE_LICENSES.md` (licence audit read by `tools/x68000_reference.py`).
- Interface notes from the 0.10.x releases: `DATAS_AND_BATCH.md`, `INTERFACE_AND_LANGUAGES.md`, `PLAYER2.md`, `VIDEO_AND_REGENERATION.md`.

`python tools/check_doc_links.py` verifies that every relative link in the
documentation points at an existing file; `--public` restricts the check to the
files of the public repository.
