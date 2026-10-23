# Upgrading exports without rediscovery

When a new converter version only changes the **player shell** (menus,
options, on-screen text, fonts, filters, sound output, icons, notices) and a
game has nothing new to learn, its export is **upgraded**: the executable is
rebuilt from the paths already learned, without replaying the exploration
routes. Anything that can change which code a game runs, how it is translated
or how it is validated still triggers a full conversion.

## When an export is upgraded

A conversion batch (or **Reconvert** in the collection) upgrades a game only
when all of the following hold:

- the previous export has a version 3 receipt (written since 1.2.8), and its
  executable is exactly the file that receipt names;
- the request's **game part** is unchanged: game-side converter inputs, scan
  level, passes, frames, video standard, BIOS or machine identity, target,
  ROM and the bundled or imported knowledge for that cartridge;
- no new gameplay hints (F12 feedback) were recorded since that export;
- the previous validation did not fail;
- only the **host part** changed: host inputs, title, language, artwork or
  icon tags.

Older receipts have no game part, so the first batch after updating to 1.2.8
still converts each game once in full. A forced conversion from the queue
always rediscovers; **Reconvert** in the collection always rebuilds, but
upgrades when the conditions above hold.

## What an upgrade does

The console's normal conversion runs at the **quick** scan level: one pass on
the shortest routes of that console (see [scan levels](CONSOLES_16BIT.md#scan-levels)).
The compiler starts from the same learned paths (local library, bundled and
imported knowledge), so the same code is generated. Native code is still
compared with the reference CPU on those routes, quick states are still
checked where the console checks them, and any interpreter fallback is still
reported. Nothing is skipped silently: the report carries an `upgrade` block
with the reason, the check level and the original discovery (its version,
date, scan level and final checks), kept across successive upgrades. The
collection marks a game as using fallback if either the quick check or the
inherited discovery met it.

An upgrade does not claim more than it checked. It does not replay long or
pseudo-random routes, and it is not a fidelity or latency measurement.

## Host or game: the classification

Every input that shapes an export is fingerprinted (`smsrecomp/compilation_inputs.py`).
`role()` splits them in two. **Host** inputs are the interactive player
shell. They are never used by the headless runs that discover and validate a
game's code; those go through each console's entry (launcher, main, runner),
which is game-side. **Everything not listed as host is game-side**, so a new
or unclassified file triggers a full conversion until it is classified.

The same categories apply to every machine:

| Category | Host inputs |
| --- | --- |
| Shared menu core (identical everywhere) | `retro_menu.c/.h`, `game_options.h`, `autofire.h`, `retro_keyboard.h` |
| On-screen text and fonts | `runtime_catalog.inc`, `runtime_i18n.h`, `font6x10.h`, `font10x20.h` |
| Presentation | `scale2x.h`, `scanlines.h`, `scanline_sdl.h`, `xbr_filter.h`, `xbr_sdl.h`, `display_settings.h`, `icon.c/.h` |
| Sound output after the emulated mixer | `audio_filter.h`, `audio_cushion.h`, `audio_output.inc`, `gb_audio_output.inc`, `nes_audio_output.inc`, `md_audio_loop.inc`, `md_audio_resample.inc`, `megadrive_audio.py` |
| Artwork, metadata, publishing | `artwork.py`, `cover_*.py`, `metadata.py`, `languages.py`, `publishing.py`, `windows.py`, `licenses/*.md`, `THIRD_PARTY_NOTICES.md`, application icons |
| Checks of the above | `game_options_checks.c`, `language_checks.c`, `xbr_checks.c`, `display_settings_checks.c`, `icon_checks.c`, `audio_checks.c`, `nes_audio_checks.c` |

Each machine family has one shell for its window, menus and input:

| Machine | Shell (host) | Entry used by discovery and validation (game) |
| --- | --- | --- |
| Master System, Game Gear | `host.c`, `ui.c/.h`, `controls.c/.h` | `launcher.c` and the Z80 runtime |
| Game Boy | `gb_menu.inc`, `gb_input_refresh.inc`, `gameboy_host.py`, `gameboy_timing.py` | `game_main.c`, `gameboy_runtime.py` |
| NES | `nes_host_ui.c` | the runner adapted by `nes_runtime.py` |
| Mega Drive, SNES, Neo Geo, CPS-1 | `console16_host_ui.c` | `console16_main.c`, `neogeo_main.c`, `cps1_main.c`, machine adapters |
| Sharp X68000 | `x68000_reference/player_ui.inc` | `x68000_reference/reference_host.c` and the SDK |

Files that are used both by the shell and by headless checks stay game-side:
`platform_io.c/.h` (quick-state files), `embedded_resources.h`, the
machine adapters `cps1_host.c` and `neogeo_host.c` (input and state
mapping), and every CPU, video, sound-chip, timing, learning and validation
file. Since 1.2.8 the Game Boy shell patches live in `gameboy_host.py`,
separate from the runtime patches in `gameboy_runtime.py`; the guest-side
JOYP refresh hook moved from `gameboy_timing.py` to
`gameboy_runtime.adapt_input_refresh_hook`. The generated Game Boy project is
byte-identical before and after that split.

## Adding or changing a file

- A new menu, text, filter or shell file: add it to `HOST_NATIVE` or
  `HOST_MODULES`, and to the tables above, only if no headless discovery or
  validation run uses it.
- A Python patch module must not mix shell and machine patches; split it as
  `gameboy_host.py` / `gameboy_runtime.py` do.
- `tests/test_compilation_inputs.py` checks the classification of every
  machine's shell and entry.
