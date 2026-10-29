# Neo Geo

Supported profile (`ng`) for SNK Neo Geo cartridge games: the arcade **MVS** and,
when your BIOS archive allows it, the console **AES** mode. Neo Geo CD, linked
cabinets, special peripherals, gambling boards and unqualified bootlegs are
outside this scope. "Supported" is a scope statement made with written criteria
([QUALIFICATION.md](QUALIFICATION.md)); it is not a claim of hardware fidelity.

Contents: [At a glance](#at-a-glance) · [Structure of the machine](#structure-of-the-machine) ·
[Engine and upstream](#engine-and-upstream) · [In the project](#in-the-project) ·
[Controls and options](#controls-and-options) · [States and saves](#states-and-saves) ·
[Qualification](#qualification) · [Known limits](#known-limits) · [History](#history)

## At a glance

| | |
|---|---|
| Status | **Supported** since 1.0.2 for the cartridge scope above (`status = 'supported'` in `retrorecomp/systems/neogeo.py`). |
| What is converted | The cartridge program (68000) and the sound program (Z80) become native C; the BIOS code is translated too. Code that was not translated runs in a counted interpreter fallback. |
| Accepted files | A `.neo` container, or a MAME/FBNeo-style ZIP set. A ZIP is identified by the CRC of its program ROMs against a ROM-free catalogue of 282 cartridge layouts; renamed members and merged archives work, a split clone needs its parent ZIP in the same folder (nothing is written there). The catalogue describes layouts, not game bytes, and is not a list of approved titles. |
| Where games are written | `Games/Neo Geo` in the export folder. |
| Firmware needed | **Your own BIOS ZIP**, chosen in **Options → Neo Geo**. It must hold `sp-s2.sp1`, `sfix.sfix`, `sm1.sm1` and `000-lo.lo` (MVS Europe, sizes and CRCs checked). For AES it must also hold `neo-epo.bin`. No BIOS is supplied, downloaded or embedded in the repository or the releases; free replacements ([NeopenBIOS](https://github.com/neogeodev/neopenbios), ISC; [neogeo-projects/neogeo-bios](https://github.com/neogeo-projects/neogeo-bios), GPLv3) are not integrated, and replacing the main BIOS alone would not settle the other three components. |
| Window caption | `Native code` or `Interpreter fallback`, from what actually ran (the caption stays in English). |

**Decisions of 29 October 2026 (release 1.6.4, lot NGE).**

- **The picture keeps all 320 columns.** It is never cropped.
- **A coloured fix-layer edge mask is painted black on screen.** The BIOS draws a
  solid fix tile in fix columns 0 and 39 as an overscan mask. Most games keep it
  black; a few (2020 Super Baseball, Joy Joy Kid, Puzzle Bobble 2, Ghostlop)
  leave it grey or orange and the picture shows a bright 8-pixel band. A
  detector reads the video chip's own fix map, tile and palette (no per-game
  list) and the host paints a latched band black **at display time only**; the
  validation hashes, reference comparisons and image dumps read the same
  pixels as before and nothing enters a saved state. It is a display
  heuristic judged on a sample of 118 games, not a hardware fact.
- **AES needs `neo-epo.bin` in the BIOS archive.** Without it F11 says "AES
  requires neo-epo.bin in your BIOS archive. Regenerate this game." The
  MVS-only archive stays supported.
- **With no BIOS chosen, the conversion says so.** The window asks you to select
  the archive in Options → Neo Geo; the command line and batch raise "Neo Geo
  needs the MVS BIOS archive (neogeo.zip): choose it in Options, Neo Geo page,
  then convert again." (before 1.6.4 this was an internal `NoneType` error).

Details and evidence: [UPGRADES.md](UPGRADES.md#neo-geo-a-coloured-edge-mask-is-painted-black-on-screen-164-lot-nge),
[RELEASE_NOTES.md](RELEASE_NOTES.md) and [NEOGEO_LOG.md](NEOGEO_LOG.md).

**Converting.** Add the cartridge with **Automatic** detection or choose **Neo
Geo**; Neo Geo joins ordinary mixed batches (up to eight conversions at once,
stop-after-active, overwrite controls, atomic publication). Each conversion
builds a fresh interpreted reference from the exact input, learns the code that
the qualification routes reach, translates it, and compares every route with the
packed executable that will be delivered: CPU registers and clocks, RAM, image
and PCM must agree. It then checks fresh-process quick states, damaged-state
rejection and ordinary saves, for MVS and, where available, AES. No comparison
is waived because the game is in the shared bank. The report keeps both
interpreter counters, the internal agreement and the limits apart
(`retrorecomp/report_schema.py`).
**Options → Neo Geo → Discovery scan**: the qualification routes are the
minimum, so *Quick* equals *Standard*; *Extended* adds one reproducible
pseudo-random route of 18,000 frames with a credit inserted before Start
(`retrorecomp/random_routes.py`), *Thorough* two. The fallback they meet is
reported, not fatal; the report records `scan_level`.

## Structure of the machine

| Part | Hardware | How Retro-Recomp handles it |
|---|---|---|
| Main CPU | Motorola 68000 (12 MHz; 24 MHz in enhanced mode, below) | Cartridge P ROM and BIOS: every even candidate in the fixed aperture (up to 1 MiB) is translated offline to guarded native C; banked code uses exact physical observations and static successors; observed work-RAM instructions become native variants guarded by their full instruction words. Anything else is the **counted interpreter** (Geolith's Musashi, the reference CPU). See [CPU_68000.md](CPU_68000.md). |
| Sound CPU | Zilog Z80 with the cartridge M1 and the BIOS SM1 program | Structural translation of both ROMs plus the observed mutable-RAM routine; bank boundaries and live accesses are guarded; external IM0 opcodes are counted fallback. See [CPU_Z80.md](CPU_Z80.md). |
| Video | LSPC: 320x224 picture, sprites, fix layer, raster timer | The reference engine (Geolith), not translated. Sprite limit 96 columns per line, 381 in enhanced mode. The edge mask (above) is a display step in the host kit view. |
| Sound | YM2610 (FM, SSG, ADPCM) | The reference engine. The first out-of-range ADPCM byte at the end of a region is rejected, small M1/SM1 ROMs are mirrored inside their chip. |
| Cartridge | Regions P (program), S (fix), M (Z80), V1/V2 (ADPCM), C (sprites) | Prepared with lithogen from the ZIP or `.neo`; regions and alignments are checked before the engine sees them. |
| Boards | Standard, linkable, PRO-CT0, KOF '98, SMA, MSLUGX, PVC | The native code view admits these mapping families (`native/neogeo_code_view.inc`). Guards never read protection ports: they do not consume CT0 responses or advance the SMA generator, and an instruction cannot straddle a port or KOF '98's mutable header overlay. Real data accesses use the board handlers. Unknown mappings stay counted fallback. |
| Memory and saves | 64 KiB MVS NVRAM, 2 KiB memory card, RTC | Ordinary saves, see below. PVC protection RAM is volatile and kept in quick states, not in the saves. |
| Peripherals | Two joysticks (A/B/C/D, Start, Coin) | Host kit controls. No light gun; the physical link cabinet is not implemented (the serial status port is excluded from code guards). The trackball of Irritating Maze is unqualified. |
| Firmware | Four BIOS components, optional `neo-epo.bin` | Your files, hashed into the identity of the game. |

**Enhanced mode (F5).** It doubles the virtual 68000 capacity (12 to 24 MHz) and
raises the sprite limit from 96 to 381 columns per line. Video, Z80/YM audio and
watchdog time stay on the master clocks. It is the fresh-install default since
1.0.2; an explicit choice is respected and saved in `NeoGeo.Runtime/enhanced` of
the shared `datas/Retro-Recomp.ini`. Headless qualification uses standard clocks
unless `--enhanced` is given. It is a deliberate extension of the console's
limits, qualified on tested paths, and claims neither original electrical timing
nor physical latency. Why it exists: crowded scenes (Metal Slug 3) exceed the
sprite limit and repeat frames at original clocks, which is not evidence of a
translator error ([log](NEOGEO_LOG.md)).

**Machine mode (F11).** Arcade MVS or console AES, chosen per game and restarted
cleanly; MVS and AES have separate identities for quick states, ordinary saves
and fallback hints. A cartridge the pinned loader supports only in arcade shows
"Arcade Only" and keeps running. The capability is read from the verified
cartridge (including revision signatures), not from a title list.

**CPU timing.** The native 68000 keeps Geolith's instruction-boundary schedule
with operand-dependent costs and disabled prefetch; the Mega Drive bus and prefetch timing is not
transplanted. Some native extension fetches and our corrected MOVEM discarded
read differ from Musashi's access count even where retired clocks and serialized
state agree; wait counters describe the reference profile, not measured
electrical waits. See [CPU_68000.md](CPU_68000.md).

## Engine and upstream

Pins live in `retrorecomp/upstreams.py` and are tracked in
[UPSTREAMS.md](UPSTREAMS.md).

| Upstream | Pin | Licence | Role |
|---|---|---|---|
| [libretro/geolith-libretro](https://github.com/libretro/geolith-libretro) | `2dc88e3` (`neogeo_build.GEOLITH_REV`) | BSD-3-Clause | Hardware runtime (cartridge boards, LSPC, YM2610) and the Musashi 68000, also used by CPS-1 and the X68000. Private adapter copy; the libretro frontend and the CHD stack are not included. |
| [carmiker/lithogen](https://github.com/carmiker/lithogen) | `ef0f9bd` (`neogeo_build.LITHOGEN_REV`, `neogeo_catalogue.LOADER`) | BSD-3-Clause, with MAME-derived data | Cartridge layout and decryption knowledge behind the ROM-free catalogue; run in an isolated process, with Unicode paths on Windows. |
| mstan/segagenesisrecomp, mstan/m68k-recomp-core | `00c60bc`, `921f67b` | PolyForm Noncommercial 1.0.0 | 68000 instruction bodies and decoder shared with Mega Drive, CPS-1 and X68000 (`retrorecomp/m68000.py`). |

Both Geolith and lithogen were reviewed identical to their pins on 29 October 2026.
The pinned checkouts are never edited; our changes are made in the adapter copy:

- M1/SM1 mirroring and the ADPCM end-of-region rejection;
- the state serializer completed with what it omits: 68000 STOP/reset/run
  latches, the YM2610 SSG divider and held samples, the palette selector, both
  LSPC sprite line buffers and their render flags, SMA's pseudo-random state,
  KOF '98's overlay mode and PVC's volatile protection RAM;
- the video timer period (the programmed value counts **N+1 pixels**), the
  eight-bit Z80 bank selection, and the sound command latch while the sound NMI
  is masked (an unacknowledged command survives masking);
- cheaper sprite-row decoding and release link-time optimisation (same results, checked against the unmodified scalar renderer);
- on Windows with the portable llvm-mingw tools, a clang profile for the engine and the host (ThinLTO): the converter builds the
  game instrumented, runs the conversion's own `play` route in a private folder, merges the counters and rebuilds with
  them (`retrorecomp/neogeo_optimization.py`, as the Super Nintendo does). The cartridge translation stays in ordinary
  objects. The profile only chooses code layout and inlining; where training fails the game is built without it, and
  `RETRO_RECOMP_PGO=0` turns it off. Outputs are identical (see [log](NEOGEO_LOG.md));
- the fix-layer routine notes its two edge tiles for the edge mask.

Licences and notices: [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).

## In the project

- **Converter** (`retrorecomp/`): `systems/neogeo.py` (profile: CPUs, stamp
  groups, path shapes), `neogeo.py` (inputs, `.neo`, ZIP identification, BIOS
  validation), `neogeo_catalogue.py` (pinned catalogue, `assets/neogeo-catalogue.json`),
  `neogeo_build.py` (project preparation, reference and native builds, state
  key, AES capability), `neogeo_codegen.py` (68000), `neogeo_z80.py` (sound),
  `neogeo_conversion.py` (the conversion and the packed-route checks),
  `neogeo_validation.py` (routes and the comparison), `neogeo_optimization.py` (Windows clang profile of the native build), `neogeo_knowledge.py`
  (numeric, BIOS-scoped hints of the shared bank), `neogeo_state_checks.py`,
  `neogeo_persistence_checks.py`, `random_routes.py` and `scan_levels.py`.
- **Native** (`native/`): `neogeo_main.c` (machine loop, modes, CLI), `neogeo_host.c/.h`
  (menu and presentation adapter), `neogeo_native.c/.h`, `neogeo_z80_native.h`,
  `neogeo_code_view.inc` (what code may be executed natively), `neogeo_decode.c`
  (offline 68000 front end), `neogeo_lithogen.c`, `neogeo_reference.c/.h`,
  `neogeo_state.c`, `neogeo_state_validate.c`, `neogeo_lspc_state.inc`,
  `neogeo_ym_state.inc`, `neogeo_persistence.c/.h`, `neogeo_fixmask.h`,
  `neogeo_sprite_decode.h`, `neogeo_input.h`, `neogeo_path_io.h`; the 68000
  backend is shared (`m68000_backend*`).
- **Host-kit adapter**: `native/hostkit/adapters/rrhk_ng.c` (F5/F11 rows, the help
  lines and the displayed view where the edge mask is applied); see [HOST_KIT.md](HOST_KIT.md).
- **ROM-free checks** (`native/neogeo_*_checks.c`, built by `tools/neogeo_*_selftest.py`):
  board and protection fixtures (`board`), keyboard and MVS switch wiring (`controls`),
  the edge-mask detector (`fixmask`), the real shared SDL menus with virtual controllers
  (`host`), 68000 ABI, dynamic cycles, IRQ and guards (`m68000`), Z80 ABI and guards (`z80`),
  ordinary saves in fresh processes (`persistence`), and `neogeo_state_selftest.py`
  for a converted game; LSPC, timer, sound-latch and YM2610 fixtures are in the same C checks.
- **Campaign and developer tools**: `tools/neogeo_campaign.py` and
  `neogeo_campaign_review.py` (finite qualification campaign and replay review),
  `neogeo_qualification.py`, `neogeo_prototype.py` (developer entry), `neogeo_state_cross.py`
  (two builds, frame by frame, and states across them), `build_neogeo_knowledge.py`.
  Developer probes accept `--headless --frames N`, `--script`, `--report`, `--capture`,
  `--pcm`, `--save-state`/`--load-state`, `--trace`, `--rtc-seed`, `--reference` and
  `--reference-z80`; none creates a file in a normal launch.
- **Tests**: `tests/test_neogeo.py`, `test_neogeo_converter.py`, `test_neogeo_fixmask.py`,
  `test_neogeo_native.py`.
- **Stamps**: the game stamp groups are `neogeo_codegen` (also CPS-1 and X68000),
  `neogeo_build` (also CPS-1), `neogeo_native` (also X68000) and `conversion_gates`;
  editing `neogeo_build.py` also moves the CPS-1 game stamp and the Neo Geo
  quick-state key. See [ARCHITECTURE.md](ARCHITECTURE.md) and [UPGRADES.md](UPGRADES.md).

## Controls and options

The Neo Geo shares the common menus, the four filters and the F2 pages
([CONTROLS.md](CONTROLS.md)).

- **Player 1**: arrows, **W/X/C/V** for A/B/C/D (letters follow the active keyboard
  layout), **Enter** for Start, either **Shift** for Coin. **Player 2**: keypad
  5/2/1/3, 8/9/6/4 for A/B/C/D, keypad Enter, keypad 0. **Controllers**: D-pad or
  left stick, A/B/X/Y, Start, Back (Coin). Start of player 2 is wired to
  STATUS_B bit 2, separately from Select. F2 remaps keyboard and gamepad per player.
- **Coin and AES.** In arcade MVS, Back is Coin. In console AES the host does not
  drive the firmware Select lines from the Coin action, so Back never opens the
  BIOS menu by accident; explicit hardware-test scripts keep the raw switch lines.
  The F1 help in AES lists only Start (from 1.6.5; before, it wrongly said
  "Shift/Back: Select").
- **Pause and reset.** Enter (Start) pauses the game itself, P is free; F1 opens
  help, Shift+F1 restarts.
- **F5** toggles enhanced mode (F1 help shows ON/OFF). **F11** switches MVS/AES and
  restarts, or shows "Arcade Only". F3/F4/F6/F7 are common; settings are read lazily
  from `datas/Retro-Recomp.ini` in independent `NeoGeo` sections, and opening, closing
  or inspecting a menu creates no file.
- **Display.** The picture is 320x224, never cropped; the edge mask is the only
  display-time change. A presentation-only power-on cover shows black over the
  firmware's initial colour-test output until the first clean monochrome intro;
  an unfamiliar screen releases it after 240 guest frames, Reset rearms it and
  loading a state releases it. The BIOS, CPU scheduling, raw framebuffer, sound
  and headless output are unchanged.
- **Options → Neo Geo**: the BIOS archive (checked before conversion, path stored
  with the preferences, a relative path inside the app folder stays portable) and the
  discovery scan level.
- **Front art.** Reviewed cover references (public links and metadata only) replace
  misleading automatic results; a manually chosen cover keeps priority.

## States and saves

General rules: [GAME_STATES.md](GAME_STATES.md).

### Persistent F8/F9 state

F8 atomically replaces one slot, `datas/states/<game>-<cartridge-and-BIOS-sha12>.rrstate`;
F9 resumes it, also after restarting the executable. The payload (`RNGSTATE`, version
3) holds the canonical 68000/Z80, bank and IRQ state, LSPC video and palette RAM,
YM2610, timers and RTC, work RAM, NVRAM, memory-card data, the frame index, the
machine mode and the presented image. It embeds no cartridge or BIOS. Files are
about 500 KiB: **512,325 bytes** on the tested boards, **520,517** on PVC boards
(volatile protection RAM). The exact cartridge, BIOS, MVS/AES mode and runtime ABI
identify a compatible state; incompatible, truncated or altered files are rejected
without touching the machine. Only a successful F8 creates the directory; a missing
F9 creates nothing. A state keeps its clock mode: the standard version-2 state of the
previous qualified ABI loads as standard; press F5 afterwards to compare.

**Between releases.** From 1.6.5 quick states need not survive an update: no
compatibility key is listed, and a quick state of 1.6.4 or earlier is refused cleanly
([GAME_STATES.md](GAME_STATES.md)). Memory cards and scores are not quick states.

### Ordinary scores and memory card

Games reload 64 KiB of MVS NVRAM and a 2 KiB memory card independently of F8/F9, from
`datas/saves/NeoGeo-<cartridge-and-BIOS-key>.rrsave` (one atomic file of **67,712
bytes**, header included). The key does not depend on the executable's name or the
runtime ABI. A plain launch, close, help menu or missing F9 creates nothing; changed
memory after real guest input is flushed at clean exit; a successful F9 makes its
restored memories eligible. This is not continuous autosave and is no protection
against a forced termination. A bad or incompatible file is preserved, not loaded,
and ordinary saving is disabled for that session with a short warning.

## Qualification

Gates and the matrix: [QUALIFICATION.md](QUALIFICATION.md) (27 October 2026: Neo
Geo meets G1-G9, G12, G14 to G16; **partial** on G10 independent CPU evidence, G11
independent hardware evidence and G13 cross-OS witness). Qualification is **per exact
ROM identity** (cartridge and BIOS) and per engine revision; only numeric
observations enter the shared bank ([COMPILATION_LIBRARY.md](COMPILATION_LIBRARY.md)).

- **Library (24 October 2026)**: of 135 archives of the maintainer's test library,
  **134 exact identities are qualified** with zero observed main and sound fallback on
  the tested routes. `fightfev` has incomplete input (clone without its parent) and
  `pnyaa` has the same contents as the qualified `pnyaaa`. Irritating Maze's
  trackball stays unqualified. Every identity needs a reconversion for 1.6.4.
- **Independent checks**: 136 authored ROM-free specification checks (video timer,
  VRAM/raster/sprites, sound latch and bank, YM2610 timers) from the documented
  hardware rather than from replaying Geolith ([log](NEOGEO_LOG.md)); sources:
  [display timing](https://wiki.neogeodev.org/index.php/Display_timing),
  [timer interrupt](https://wiki.neogeodev.org/index.php/Timer_interrupt),
  [VRAM](https://wiki.neogeodev.org/index.php/VRAM),
  [sprites](https://wiki.neogeodev.org/index.php/Sprites),
  [Z80 bankswitching](https://wiki.neogeodev.org/index.php/Z80_bankswitching),
  [68k/Z80 communication](https://wiki.neogeodev.org/index.php/68k/Z80_communication),
  [YM2610 timers](https://wiki.neogeodev.org/index.php/YM2610_timers). These
  qualify the named behaviours, not electrical bus phases.
- **Release check game**: NAM-1975 (`nam1975`), zero interpreted instructions on the
  main and sound CPUs.
- **Risk cases** (`tools/campaign-risk-cases.json`): Metal Slug 3 (state-ABI
  reference), KOF 2003 (PVC protection RAM, 520,517-byte states), Garou (SMA),
  KOF '98 (own mapper, code view and state extension), Twinkle Star Sprites
  (enhanced mode).
- **The five measures stay apart.** Native code: counted per CPU and per device, shown
  in the window and the report. CPU fidelity: native against the fresh reference on
  registers, clocks, RAM, image and PCM, per route. Hardware fidelity: most
  comparisons share Geolith's hardware implementation, so agreement does not qualify
  video or audio timing independently (only the authored checks above do).
  Gameplay validation: bounded routes (the longest long-play paths are 54,000
  frames), not completed playthroughs. Physical latency: not measured; the audio queue
  figures are logical samples, not jack latency.

## Known limits

- **Physical latency**, listening quality and controller response are not measured.
- **Hardware fidelity** is the reference engine's: fine bus phases, electrical timing
  and prefetch are not qualified; the sprite limit and slowdown behaviour of original
  games are kept at standard clocks and altered only by the optional enhanced mode.
- **Interpreter fallback** is never promised away: unseen code, unseen guards and
  some RAM variants stay counted, and a conversion with observed fallback is marked
  experimental at cartridge level. A pointer with a flagged high byte keeps its full
  PC (the reference CPU does too, so `BSR` pushes `0x8004e806` on Gowcaizer); this is
  reference agreement, not proof of real 68000 behaviour, and CPS-1 shares the pattern.
- **Edge mask**: a display heuristic, checked on converted exports of 2020 Super
  Baseball, Puzzle De Pon!, Joy Joy Kid, Puzzle Bobble 2 and Ghostlop (only the
  outer 8 columns of a latched side change; the 304 between stay identical), on
  attract and scripted screens, not on a played game. A band that has just appeared
  stays visible for the 30 frames the latch needs.
- **Cartridges with a 64 KiB fixed ROM** (Last Hope) convert since 1.6.5: the container carries the ROM twice, as its chip repeats it; a `.neo` file handed in directly with such a ROM is still refused.
- **Not covered**: Neo Geo CD, physical cabinet linking, the trackball of Irritating
  Maze, mahjong panels and quiz/board sets needing other hardware, other BIOS
  revisions and regions, a distributable free BIOS.
- **Linux and controllers**: Windows and Linux share the same host code; the ROM-free
  checks claim no physical controller test and no Linux desktop test.

## History

The dated journal (campaigns from 13 October 2026, fixes, measurements, the
decisions behind them) is [NEOGEO_LOG.md](NEOGEO_LOG.md). Milestones:

| Date | Milestone |
|---|---|
| 13-15 Oct 2026 | Private prototype, converter integration, protected boards, ordinary saves, 24-game MVS qualification, enhanced mode; supported scope from release 1.0.2 (AES firmware support) |
| 20 Oct 2026 | Release 1.1.8: arcade-only notice, native link-board code view, startup cover, AES Select |
| 24 Oct 2026 | Library campaign: 134 of 135 identities qualified; 32-bit PC fix |
| 29 Oct 2026 | Lot NGE of 1.6.4: edge mask, BIOS messages; then the mask checked on Joy Joy Kid, Puzzle Bobble 2 and Ghostlop, AES help line (1.6.5) |

The original plan and choices (French) are in the local maintainer document `NEOGEO_PLAN.md`.
