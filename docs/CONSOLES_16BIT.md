# The 16-bit family: what the Mega Drive and the Super Nintendo share

The Mega Drive and the Super Nintendo are separate machines with separate pages, [MEGADRIVE.md](MEGADRIVE.md) and
[SNES.md](SNES.md). This page keeps only what the two profiles use in common: the game interface (menu, keys, quick
states), the discovery scan levels, and the build and dependency contract. Anything specific to one machine (cartridge
scope, boards, saves, qualification, known limits) is on its own page, and the dated evidence of each is in
[MEGADRIVE_LOG.md](MEGADRIVE_LOG.md) and [SNES_LOG.md](SNES_LOG.md).

Both profiles are instruction-based: the main processor is translated ahead of time to guarded native C and whatever
cannot be translated is counted, never hidden (the processors are described in [CPU_68000.md](CPU_68000.md),
[CPU_Z80.md](CPU_Z80.md) and [CPU_65816_SPC700.md](CPU_65816_SPC700.md)). Passing the project's own checks does not
establish hardware fidelity, complete gameplay or physical latency.

## Contents

1. [Shared game interface](#shared-game-interface)
2. [Scan levels](#scan-levels)
3. [Build and dependency contract](#build-and-dependency-contract)
4. [Where the rest went](#where-the-rest-went)

## Shared game interface

Both profiles use RetroRecomp's SDL presentation and menu renderer: F1 help,
Shift+F1 restart, F2 keyboard/gamepad mapping, F3 sharp/Scale2x/scanlines/xBR
smooth, F4 window/integer fullscreen/aspect-preserving fullscreen,
F6 autofire and F7 for the menu language. Enter, the cartridge Start, pauses
the game itself. Two controller ports are wired; the
selected game determines whether two-player gameplay exists. Controller
left-stick click pauses; player one's right-stick click restarts.
Gun games use the mouse on port 2, a small red cross, and F5 gun settings.

The scanline filter places a translucent gap between every guest raster row,
using the actual displayed height. Its cached mask accounts for fractional
fullscreen scaling and HiDPI output, without darkening alternate game rows.
Below 2x vertical scaling, the image stays intact because those gaps cannot
be resolved. Only presentation changes; game pixels and timing remain untouched.

Mega Drive defaults to arrows, W/X/C for A/B/C and Enter for Start. The qualified
Street Fighter II' Plus and Mortal Kombat II profiles expose X/Y/Z and Mode in
F2, using A/S/D and right Shift (either Shift works) by default. Their two
controller ports use the six-button protocol; other profiles retain
three-button pads. SNES defaults to arrows, W/X/A/S for A/B/X/Y, Q/E for L/R,
Shift for Select (left by default, either Shift works since 1.5.0) and Enter
for Start. Player two uses the numeric keypad and has no reset
shortcut. F2 exposes the console's actual controls.
Letter defaults and F2 key labels follow the active keyboard layout,
including AZERTY. Saved custom mappings retain their physical key positions.

F8/F9 quick states are implemented for the qualified instruction-based profiles,
including PAL. They survive closing and restarting the game and are stored in
`datas/states/<game-slug>-<rom-sha12>.rrstate`. A runtime ABI or ROM mismatch is
rejected. See [captured state and validation](GAME_STATES.md#mega-drive-and-super-nintendo).
Ordinary SNES battery-backed cartridge RAM is saved independently in
`datas/saves`, with exact ROM/mapping identity and atomic writes after guest
changes. Volatile RAM stays in memory. See [SNES cartridge saves](SNES.md).

Reading existing settings or progress creates no directory or log. Guest
changes to battery RAM, a saved state or a saved setting create only their
required data files. Changing a saved
setting creates `datas/Retro-Recomp.ini` beside the games, with separate
Mega Drive and SNES control sections. Probe logs belong to the converter's
private build directories and are created only by explicit conversion tests.

## Scan levels

Each console tab in **Options** sets a **discovery scan level**, with optional
pass and frame overrides and a short note on what is recommended. *Quick* runs
one pass on a capped scenario length; *Standard* is the qualified default (demo
and play); *Extended* adds a 12,000-frame attract test, the authored Mega Drive
replays and one **reproducible pseudo-random play route** of 18,000 frames;
*Thorough* runs the attract sequence for 24,000 frames and two routes
(`retrorecomp/random_routes.py`, `retrorecomp/scan_levels.py`).
Their seed is the console and the exact ROM identity, so every conversion of the
same cartridge replays the same routes, and the same script drives the native
export and its reference run; the report keeps each route's seed and index. A
route is ordinary host controller input: long movement phases that often hold a
button, short taps, paired Start presses that pause and resume, occasional
Select and player-two taps, and neutral pauses between phases. Opposing
directions are never pressed together and nothing in guest memory or game code
is patched. Each route boots the game afresh. The converter can also chain the
second route from the machine state the first one saved at its last frame
(`--save-state` / `--load-state` of the headless host, one state file per
engine so the native export and its reference each restore their own, both
written by the same executable; the report then marks the route with
`continues_from`). That mode is off by default: measured on 23 October 2026 on
Sonic and Donkey Kong Country, it found no new opcode variant, because the
routes do not progress past the first screen and a chained route can end at
the title screen. Lightgun games keep their authored mouse routes instead.

Standard is the default. The longer levels increase conversion time and
broaden tested coverage; they cannot explore every level or certify independent
hardware accuracy. On the command line, `--scan-level quick|standard|extended|thorough`
applies to every console of a `convert` or `batch` run; `--md-advanced-scan`
still means thorough. The report records the level under `advanced_scan.level`.

The Mega Drive authored replays (varied input, early start, menu and dialogue) and the cold-library measurements are in
[MEGADRIVE.md](MEGADRIVE.md) and [MEGADRIVE_LOG.md](MEGADRIVE_LOG.md); the Super Nintendo scenarios are in
[SNES.md](SNES.md) and [SNES_LOG.md](SNES_LOG.md).

## Build and dependency contract

These profiles use pinned sources downloaded into `.deps` on first conversion:

| Component | Revision |
| --- | --- |
| [segagenesisrecomp](https://github.com/mstan/segagenesisrecomp) | `00c60bc855a7998f92e5614585d52bca8fffcaf2` |
| [snesrecomp](https://github.com/RetroPortingToolKit/snesrecomp) | `a00df26a87831113fec91b9225bf16b049d40775` |

A C++ toolchain is required for conversion; the converter offers to install it.
Since 1.4.1, every SNES cartridge, Super Mario World included, uses the
generic instruction-map analysis: no Rust and no separate
SuperMarioWorldRecomp dependency. Generated games need none of those
development tools to run.

Generated-source analysis is cached for the exact ROM, pinned engine/game
profile, adapter revision and verified observations. Changes to that identity
invalidate the cache. Both conversions use
the existing batch queue, clean filenames, per-console folders, atomic
replacement, Windows metadata, cover icons and executable compression.
The packaged converter fingerprints embedded bytecode when Python source files
are absent. Temporary extraction paths are excluded from those fingerprints,
so restarting the converter does not invalidate unchanged compiler inputs.

Component licences and notices are embedded in each game EXE. The imported
frameworks retain their **PolyForm Noncommercial 1.0.0** terms; RetroRecomp's
MIT licence does not replace them. See [Genesis notices](../licenses/segagenesisrecomp.md) and
[SNES notices](../licenses/snesrecomp.md).

## Where the rest went

| You are looking for | Page |
| --- | --- |
| Mega Drive scope, boards, saves, controls, qualification, limits | [MEGADRIVE.md](MEGADRIVE.md) |
| Mega Drive dated evidence (release qualification, compiler and runtime evidence, cartridge saves, native coverage, sound scheduling, native sound CPU, scan routes) | [MEGADRIVE_LOG.md](MEGADRIVE_LOG.md) |
| Super Nintendo scope, boards, saves, controls, qualification, limits | [SNES.md](SNES.md) |
| Super Nintendo dated evidence (PAL timing, the 65816 adapter, SPC700 recompilation, shared comparison limits, scan scenarios) | [SNES_LOG.md](SNES_LOG.md) |
| The processors | [CPU_68000.md](CPU_68000.md), [CPU_Z80.md](CPU_Z80.md), [CPU_65816_SPC700.md](CPU_65816_SPC700.md) |
| Light guns (Menacer, Justifier, Super Scope) | [GUNS_16BIT.md](GUNS_16BIT.md) |
| Compatibility and evidence per console | [COMPATIBILITY.md](COMPATIBILITY.md) |
