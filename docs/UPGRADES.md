# Upgrading exports without rediscovery

When a new converter version only changes the **player shell** (menus,
options, on-screen text, fonts, filters, sound output, icons, notices) and a
game has nothing new to learn, its export is **upgraded**: the executable is
rebuilt from the paths already learned, without replaying the exploration
routes. Anything that can change which code a game runs, how it is translated
or how it is validated still triggers a full conversion.

This page keeps the rules, the current release and the one before it, and still the sections of 1.7.0 and 1.6.8. The detail of releases 1.6.9, 1.6.7 and 1.6.6 is in
[UPGRADES_HISTORY.md](UPGRADES_HISTORY.md), and that of 1.6.5 and before in [UPGRADES_HISTORY_OLDER.md](UPGRADES_HISTORY_OLDER.md) (the same text,
the same anchors).

## When an export is upgraded

A conversion batch (or **Reconvert** in the collection) upgrades a game only
when all of the following hold:

- the previous export has a version 3 receipt (the only one this release
  writes and reads), and its executable is exactly the file that receipt names;
- the request's **game part** is unchanged: game-side converter inputs, scan
  level, passes, frames, video standard, BIOS or machine identity, target,
  ROM and the bundled or imported knowledge for that cartridge;
- no new gameplay hints (F12 feedback) were recorded since that export;
- the previous validation did not fail;
- only the **host part** changed: host inputs, title, language, artwork or
  icon tags.

Older receipts have no game part: the first batch after updating from a release
before 1.6.0 converts each game once in full. A forced conversion from the queue
always rediscovers; **Reconvert** in the collection always rebuilds, but
upgrades when the conditions above hold.

A third role, **build**, covers the choice of the C toolchain
(`retrorecomp/toolchain.py`): changing the compiler or its options also upgrades an
export, because the executable is recompiled and rechecked on the quick routes.
Exports of the **previous release** can be accepted the same way through an explicit list of
equivalent game stamps; see [Build inputs](COMPILATION_LIBRARY.md#build-inputs-and-exports-of-an-earlier-release-that-stay-upgradable-150).

## The rule: the previous release only

Backward compatibility is owed to the previous release and to nothing older (decision of 28 October 2026). For release
N it covers the exports, receipts, quick states and local files that release N-1 wrote, and nothing else:

- `LEGACY_GAME_STAMPS` (`retrorecomp/stamp_inputs.py`) lists the game stamps of release N-1, where its exports were
  shown to differ from release N only in how the game is built (none when the release changes what a game does). The
  release procedure replaces the entries, it never adds to those of an older release. The table was empty in the tree of
  1.6.0; the tree of 1.6.1 listed the stamps of 1.6.0 ([history](UPGRADES_HISTORY_OLDER.md#exports-of-160-in-161)); the tree of 1.6.2 listed those of
  1.6.1 ([history](UPGRADES_HISTORY_OLDER.md#exports-of-161-in-162)); the tree of 1.6.3 listed those of 1.6.2 ([history](UPGRADES_HISTORY_OLDER.md#exports-of-162-in-163)); the
  tree of 1.6.4 lists none, a full reconversion of every console ([below](UPGRADES_HISTORY_OLDER.md#exports-of-163-in-164)).
- The quick-state keys of release N-1 are the only `RR16_STATE_COMPAT_ABI` lines a build writes
  ([GAME_STATES.md](GAME_STATES.md#the-rule-the-previous-release-only)). None in the tree of 1.6.0; the Mega Drive, Neo
  Geo and CPS-1 keys of 1.6.0 (Windows) in the tree of 1.6.1. The Mega Drive, Super Nintendo, Neo
  Geo and CPS-1 keys of 1.6.1 (Windows) in the tree of 1.6.2. The same four consoles' keys of 1.6.2 (Windows) in the
  tree of 1.6.3. The Neo Geo key of 1.6.3 (Windows) alone in the tree of 1.6.4: the Mega Drive and Super Nintendo keys did
  not move, and the CPS-1 and NES states changed ([below](UPGRADES_HISTORY_OLDER.md#exports-of-163-in-164)).
- A receipt of another schema than the current one (3) is never current, and a report is read in the places the current
  writers use (`scan_level`, `scan.level`), not in those of releases before 1.6.0.
- Nothing migrates the files of a release older than N-1 (collection inventories without a recorded base, the X68000
  observation pairs of the development stages, the library of the former name, default key bindings of old settings).

A player coming from an older release reconverts (or reinstalls); nothing is lost on disk, the old files are simply
not read.

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

## Exports of 1.8.0 in the next release

The release after 1.8.0 is the multiplayer release (in preparation; main is frozen after this change and the work goes on in the
multiplayer branch, which adds its own lines here). One line per change, with the stamps it moves.

| Change | Game stamps that move | Host and build stamps | Quick states |
| --- | --- | --- | --- |
| [Every machine: the pad's Options button opens the F2 tiles, Quit is their last tile](#every-machine-the-pads-options-button-opens-the-f2-tiles-quit-is-their-last-tile-next-release) | none | **the host stamp of all 21 profiles** (the shell, `game_options.h`, `retro_menu.c`, the catalogue and the locales) | unchanged (host files are outside every state key) |
| Every machine, multiplayer in turns: the F2 tiles Pass / Give the controller and Everyone / Turns, the turn badge and its options row ([HOST_KIT D33](HOST_KIT.md#d33)) | none | **the host stamp of all 21 profiles** (`rrhk_menu.c`, `rrhk_events.c`, `rrhk_options.c`, `rrhk_main.c`, `rrhk_chat.inc`, `hostkit.h`, `hostkit_internal.h`, `retro_menu.c` and `.h`, the catalogue and the locales) | unchanged |
| [Every machine: a Restart the game tile in F2](#every-machine-a-restart-the-game-tile-in-f2-next-release) | none | **the host stamp of all 21 profiles** (`rrhk_menu.c`, `rrhk_main.c`, `hostkit_internal.h`, `retro_menu.c` and `.h`, the catalogue and the locales) | unchanged (host files are outside every state key) |
| [NES, Game Boy, PC Engine, Game Boy Advance, Nintendo 64, PlayStation: the sound ring is always regulated](#nes-game-boy-pc-engine-game-boy-advance-nintendo-64-playstation-the-sound-ring-is-always-regulated-next-release) | none | **the host stamp of all 21 profiles** (`rrhk_ring.c`, `rrhk_audio.c`, `hostkit_internal.h`, `audio_cushion.h`; the sound changes only on the six ring machines) | unchanged |
| [Sony PlayStation: the host changes PGXP, the CPU's resolution and the renderer in a match](#sony-playstation-the-host-changes-pgxp-the-cpus-resolution-and-the-renderer-in-a-match-next-release) | none | the PlayStation's host stamp (`rrhk_psx.c`) | unchanged |
| [Every machine: the sound no longer crackles in multiplayer](#every-machine-the-sound-no-longer-crackles-in-multiplayer-next-release) | none | **the host stamp of all 21 profiles** (`rrhk_main.c`, `rrhk_audio.c`, `rrhk_ring.c`, `hostkit_internal.h`) | unchanged (host files are outside every state key) |
| [Sharp X68000: rollback and the host's F8 / F9 in multiplayer; the computers share only the pads in a session](#sharp-x68000-rollback-and-the-hosts-f8--f9-in-multiplayer-the-computers-share-only-the-pads-in-a-session-next-release) | **x68** | **the host stamp of x68, amiga, a1200, atarist, msx, msx2, msx2plus** (`rrhk_computer.inc`, `rrhk_x68k.inc`) | **X68000 only:** its key moves (the portable format does not) |
| [Nintendo 64: multiplayer on the delay tier, and a change of resolution in play keeps the renderer's memory](#nintendo-64-multiplayer-on-the-delay-tier-and-a-change-of-resolution-in-play-keeps-the-renderers-memory-next-release) | the Nintendo 64 (`n64_cpu.c`, `n64_session.cpp`, `n64_player.c`) | the Nintendo 64's host stamp (`rrhk_n64.inc`) | Nintendo 64 states of 1.8.0 refused (the state key hashes the session sources) |
| [Every machine: multiplayer, two to four players over the local network](#every-machine-multiplayer-two-to-four-players-over-the-local-network-next-release) | **the game stamp of all 21 profiles** (the simulation identity and the recipe mode in `retrorecomp.batch` and the profiles) | **the host stamp of every profile with the host kit** (the session code of the shell, `hostkit_session.h`, the chat, the catalogue and the locales) | unchanged on every machine (the session code is outside every state key) |
| [Super Nintendo: multiplayer, digest and rollback on the boards without a chip](#super-nintendo-multiplayer-digest-and-rollback-on-the-boards-without-a-chip-next-release) | **the game stamp of the Super Nintendo** (`console16.py`: the profile answers a session) | **the host stamp of the Super Nintendo** (`snes_backend.c`, `rrhk_snes.c`) | **the Super Nintendo quick-state key moves** (it hashes `snes_backend.c`); an older quick state is refused cleanly |
| [Super Nintendo: four players (Super Multitap) and the host's save in a session](#super-nintendo-four-players-super-multitap-and-the-hosts-cartridge-save-in-a-session-next-release) | **the Super Nintendo game stamp** (the multitap list and the report) | **the Super Nintendo host stamp** (`snes_backend.c`, `rrhk_snes.c`) | the Super Nintendo key moves (as above) |
| [MSX, MSX2, MSX2+: multiplayer on the rollback tier](#msx-msx2-msx2-multiplayer-on-the-rollback-tier-next-release) | **the MSX, MSX2 and MSX2+ game stamps** (`msx_snapshot.inc`, `msx_player.c`, `msx_state.c`, `msx_build.py`, `systems/msx.py`) | **the MSX, MSX2 and MSX2+ host stamps** (`rrhk_msx.inc`) | unchanged (the quick-state files keep their layout and the picture) |
| [MSX: a MegaROM with no direct mapper store is probed, not refused](#msx-a-megarom-with-no-direct-mapper-store-is-probed-not-refused-next-release) | **the MSX, MSX2 and MSX2+ game stamps** (`retrorecomp/msx_conversion.py`) | none | unchanged |
| [MSX, MSX2, MSX2+: the host's save travels in a session](#msx-msx2-msx2-the-hosts-save-travels-in-a-session-next-release) | **the MSX, MSX2 and MSX2+ game stamps** (`msx_snapshot.inc`, `msx_player.c`) | **the MSX, MSX2 and MSX2+ host stamps** (`rrhk_msx.inc`) | unchanged (the quick-state files keep their layout) |
| [MSX, MSX2, MSX2+: the host's save travels in a session and is written back at its end](#msx-msx2-msx2-the-hosts-save-travels-in-a-session-and-is-written-back-at-its-end-next-release) | **the MSX, MSX2 and MSX2+ game stamps** (`msx_snapshot.inc`, `msx_player.c`) | **the MSX, MSX2 and MSX2+ host stamps** (`rrhk_msx.inc`) | unchanged (the quick-state files keep their layout) |
| [Game Boy: rollback and the host's F8 / F9 for everyone](#game-boy-rollback-and-the-hosts-f8--f9-for-everyone-next-release) | **the Game Boy game stamp** (`gb`: the runtime part `native/gb_machine_state.h`, `gb_digest.h`, the patches of `gameboy_runtime.py` and `gameboy_hardware.py`) | **the Game Boy host stamp** (`rrhk_gb.inc`) | unchanged (the quick-state file format is not touched) |
| [NES: the Four Score, players 3 and 4 (multiplayer)](#nes-the-four-score-players-3-and-4-multiplayer-next-release) | **the NES game stamp** (`nes_machine.py`, `nes_runtime.py`, `nes_catalog.py`, `nes.py`, the profile) | **the NES host stamp** (`rrhk_nes.c`, `retro_nes.h`) | **the NES quick-state key moves** (`nes_machine.py` adds the Four Score register to the saved APU); an older quick state is refused cleanly |
| [NES: the host's save travels in a session](#nes-the-hosts-save-travels-in-a-session-next-release) | none | **the NES host stamp** (`rrhk_nes.c`, `retro_nes.h`) and the game stamp (`nes_runtime.py`: the save write of the program) | **the NES quick-state key moves again** (it hashes `nes_machine_state.inc`); an older quick state is refused cleanly |
| [Mega Drive: the rollback tier and the host's F8 / F9 for everyone](#mega-drive-the-rollback-tier-and-the-hosts-f8--f9-for-everyone-next-release) | **the Mega Drive game stamp and engine stamp** (`retrorecomp/megadrive_rollback.py`, new, and its hooks in `megadrive_audio`, `megadrive_bus`, `megadrive_memory`, `megadrive_runtime`) | **the Mega Drive host stamp** (`native/hostkit/adapters/rrhk_md.c`) | unchanged (no file of the Mega Drive key is touched; the quick-state format does not change) |
| [Mega Drive: four players with the Team Player, the 4 Way Play or the J-Cart](#mega-drive-four-players-with-the-team-player-the-4-way-play-or-the-j-cart-next-release) | **the Mega Drive game and engine stamps** (`retrorecomp/megadrive_multitap.py`, new, and its hooks); **the game stamps of the Super Nintendo, Neo Geo, CPS-1, CPS-2, PC Engine and PlayStation** (`console16.py`, the report's player count; their games do not change) | **the Mega Drive host stamp** (`rrhk_md.c`) | unchanged |
| [Mega Drive, Super Nintendo, PC Engine: the host's save written back at a match's clean end](#mega-drive-super-nintendo-pc-engine-the-hosts-save-written-back-at-a-matchs-clean-end-next-release) | **the game stamps of the Mega Drive, Super Nintendo, PC Engine, MSX, MSX2 and MSX2+** (`native/cart_save.c` and `.h`, which they share; `md_battery.c` and `.h`, `md_backend.c`) | **the Mega Drive host stamp** (`rrhk_md.c`) | **the quick-state keys of those six profiles move** (they hash `cart_save.c`; the Mega Drive's also `md_backend.c` and `md_battery.c`): older quick states are refused cleanly; the state and save formats do not change |
| [Mega Drive: the host's save written back at a match's clean end](#mega-drive-the-hosts-save-written-back-at-a-matchs-clean-end-next-release) | **the Mega Drive game stamp** (`md_battery.c` and `.h`, `md_backend.c`) | **the Mega Drive host stamp** (`rrhk_md.c`) | **the Mega Drive quick-state key moves** (it hashes `md_backend.c` and `md_battery.c`): an older quick state is refused cleanly; the state and save formats do not change |
| [Sony PlayStation: multiplayer, the digest and the host's settings (delay tier)](#sony-playstation-multiplayer-the-digest-and-the-hosts-settings-delay-tier-next-release) | **the game stamp of the PlayStation** (`psx_session.c`, `psx_main.c`, `psx_session.h`; Beetle's adaptation: one line of `spu.c`) | **the host stamp of the PlayStation** (`rrhk_psx.c`) and **of every machine with the host kit** (one catalogue string in the eight locales, `runtime_catalog.inc`) | unchanged (the PlayStation's state key hashes none of these files; a state's format does not change) |
| [Neo Geo: rollback and the host's F8 / F9 for everyone in a match](#neo-geo-rollback-and-the-hosts-f8--f9-for-everyone-in-a-match-next-release) | **the Neo Geo game stamp** (`native/neogeo_state.c`, `neogeo_main.c`, `neogeo_persistence.c`, `neogeo_reference.c` and `.h`, `neogeo_host.h`, the profile) | **the Neo Geo host stamp** (`rrhk_ng.c`) | Neo Geo's key **does not move** (the F8 state is untouched; no quick-state file or key is edited) |
| [Game Boy: rollback and the host's F8 / F9 for everyone](#game-boy-rollback-and-the-hosts-f8--f9-for-everyone-next-release) | **the Game Boy game stamp** (`gb`: the runtime part `native/gb_machine_state.h`, `gb_digest.h`, the patches of `gameboy_runtime.py` and `gameboy_hardware.py`) | **the Game Boy host stamp** (`rrhk_gb.inc`) | unchanged (the quick-state file format is not touched) || [Game Boy Advance: multiplayer on the delay tier](#game-boy-advance-multiplayer-on-the-delay-tier-next-release) | the Game Boy Advance only (`586c1761d5bd` to `2ac1bcdddb63`) | the Game Boy Advance host stamp only (`d52501526302` to `fd6a26f3aada`); build unchanged | unchanged |
| [Game Boy Advance: multiplayer on the delay tier](#game-boy-advance-multiplayer-on-the-delay-tier-next-release) | the Game Boy Advance only (`586c1761d5bd` to `2ac1bcdddb63`) | the Game Boy Advance host stamp only (`d52501526302` to `fd6a26f3aada`); build unchanged | unchanged |
| [Commodore Amiga 500 and 1200: multiplayer on the rollback tier](#commodore-amiga-500-and-1200-multiplayer-on-the-rollback-tier-next-release) | **the Amiga 500 and Amiga 1200 game stamps** (`amiga_session.cpp`, `amiga_session.h`, `amiga_player.c`, the new `retrorecomp.amiga_vamiga_session`, `retrorecomp.amiga_conversion`, `systems/amiga.py`) | **the Amiga 500 and Amiga 1200 host stamps** (`rrhk_amiga.inc`) | **the Amiga quick-state key moves** (it hashes `amiga_session.cpp`, `amiga_session.h` and the adapted vAmiga): an older quick state is refused cleanly; the file's layout is unchanged |
| [Commodore Amiga 500 and 1200: the F1 help says how two players play](#commodore-amiga-500-and-1200-the-f1-help-says-how-two-players-play-next-release) | none | **the Amiga 500 and Amiga 1200 host stamps** (`rrhk_amiga.inc`) | unchanged |
| [Commodore Amiga 500 and 1200: the host writes its saves back at a match's clean end](#commodore-amiga-500-and-1200-the-host-writes-its-saves-back-at-a-matchs-clean-end-next-release) | **the Amiga 500 and Amiga 1200 game stamps** (`amiga_session.cpp`, `amiga_session.h`, `amiga_savefile.h`) | **the Amiga 500 and Amiga 1200 host stamps** (`rrhk_amiga.inc`) | **the Amiga quick-state key moves** (it hashes `amiga_session.cpp`, `amiga_session.h`): an older quick state is refused cleanly; the file's layout is unchanged |
| [Commodore Amiga 500 and 1200: an Imploder block whose checksum differs](#commodore-amiga-500-and-1200-an-imploder-block-whose-checksum-differs-next-release) | **the Amiga 500 and Amiga 1200 game stamps** (`native/amiga_whdload/rr_decrunch.c`) | none | unchanged (the quick-state key does not hash the unpacker) |

## Commodore Amiga 500 and 1200: the F1 help says how two players play (next release)

Arthur did not find Alien Breed 2 (AGA)'s two-player mode (19 November 2026). An Amiga game chooses one or two players in its own menu
(Alien Breed 2: "Number Of Players" on its title screen, 1 by default), and its player 2 holds the joystick of port 1, where the mouse
usually is, which player 2's pad drives (alone, the « Mouse port » row on player 2's pad page, Auto by default; in a session, port 1 is
the joystick on every seat). The F1 help's second line under the keys now says so, in the five game languages (« 2 joueurs : menu du
jeu | manette 2 : port souris »), in place of the computers' Ctrl+Alt+K line: the panel holds two lines there (a third ran past its
edge in an offscreen capture), and Ctrl+Alt+K stays on the second page (Tab) as "full guest keyboard". `rrhk_amiga.inc` only
(`a_help_controls`; its five-language texts share one `a_language`); the Atari ST keeps the computers' two lines. Checked by an
offscreen capture of the help page of a converted game in the five languages: the line ends inside the panel.

**Stamps** (against `spec/multiplayer` `e83119c8`): the Amiga 500 and Amiga 1200 host stamps; no game stamp, quick states unchanged.

## Sony PlayStation: the host changes PGXP, the CPU's resolution and the renderer in a match (next release)

Session ABI 9 for the PlayStation (Arthur wants the host to change the run-changing options in a match). The host's F3 rows that
the match sends every seat (`pgxp`, `pgxp_texture`, the CPU renderer's resolution, the renderer when PGXP is On) are no longer refused
on the host: its choice is kept (saved as alone) and reported by `session_options`, never applied in this match (a renderer switch
in play opens the core again; the host's frames stop at once anyway). The kit sees the report differ once the menu is closed, sends
`RELAUNCH`, and the match starts again for everyone with the new values. A renderer the host asks for that this PC cannot draw with
(the card refused at start: no usable Vulkan device) is reported as the CPU, so it asks nothing. A guest's rows stay refused (« Set
by the host in multiplayer »); its F3 still shows its own values, not the host's (the kit's graphics page has no hook for that yet).
Multisampling stays refused on every seat in a match (picture only, it is not sent). Alone, nothing changes.

**Stamps** (against `spec/multiplayer` `8041b8e2`): the PlayStation's host stamp (`native/hostkit/adapters/rrhk_psx.c`); no game
stamp; quick states unchanged.

## NES, Game Boy, PC Engine, Game Boy Advance, Nintendo 64, PlayStation: the sound ring is always regulated (next release)

Arthur's yes of 19 November 2026 (HOST_KIT [D33](HOST_KIT.md#d33)): the six machines on the kit's sound ring no longer play the
machine's PCM byte for byte when the game is not locked to the display. The ring resamples every block by D30's base and a correction
of at most 0.5 % from its fill, so it no longer drifts with the two clocks to a trim or a gap; it has 80 ms more room before a trim and
a trim no longer raises its reserve. For a player: no more crackle from the drift or from a burst after a hitch; the pitch moves by at
most 0.5 % (usually about 0.01 %); no latency added on average; the highest frequencies slightly softer (linear interpolation).
Physical latency unmeasured. In a multiplayer game the ring was already regulated by the change above; this one extends it to a game
alone. The queue model's machines are unchanged.

Measured (counters of the ring's closing line, the real sound device with the game muted, never by ear): Tekken 3 alone, 3,600
frames (60 s), on this PC (busy: one run, counts not a timing): before 1 gap, 2 trims; after 0 gaps, 0 trims. On the second PC (a
Windows 10 laptop on Wi-Fi), two runs each without a window (SDL's dummy video): before 0 / 0 and 0 / 1 trim, after 0 / 0 and 0 / 0;
two runs each with a real window and renderer (Direct3D 11) on a hidden desktop: 0 / 0 everywhere, before and after. The attract
mode of a run of 60 s does not show the laptop's crackle (Arthur heard it in play); a run on a quiet PC is recorded here when made.

**Stamps** (against `spec/psx-audio` `b3fb20ba`): the host stamp of all 21 profiles (`rrhk_ring.c`, `rrhk_audio.c`,
`hostkit_internal.h`, `audio_cushion.h`, a comment); no game stamp; quick states unchanged (host files are outside every state key).
An export's own sound changes only on the six ring machines.

## Every machine: the sound no longer crackles in multiplayer (next release)

Arthur, 19 November 2026, Tekken 3 together over his local network: the game stays fluid, the music crackles a lot (a little alone on
his PC, more on the ThinkPad). Cause, in the host kit's loop (`rrhk_main.c`, `end_frame`), for every machine: an iteration whose
frame had not come yet (the session waits for it up to three quarters of a frame, then shows the last picture and asks again) went
through `rrhk_audio_idle`, which **threw away the sound waiting** (the ring model: `rrhk_ring_clear`; the queue model: pause and
`SDL_ClearQueuedAudio`) and started it again after a reserve of silence. Now:

- an iteration that waits for its frame keeps the sound (only a session's pause clears it, as before);
- a multiplayer game's ring (the ring model: NES, Game Boy, PC Engine, Game Boy Advance, Nintendo 64, PlayStation) is always
  regulated (since the next change, a game alone too), with the resampling of D30 at the session's base (1.0 included), so its fill comes back to its target instead of drifting
  to a trim or a gap; its resampler is no longer restarted by a change of pace; its trim bound is 80 ms higher (a burst of frames
  after a wait no longer throws sound away) and a trim no longer raises its reserve;
- the ring's closing line counts what a player hears as a crackle: `cleared=` samples and `(gaps N, trims N, clears N)`, and the
  device period.

A game alone was unchanged by this one (see the change above for its ring).

Measured with counters, never by ear (`tools/netplay_game_smoke.py --real-audio PlayStation`: the system's own sound output, each seat
muted in its game options, so the device pulls the sound at its own pace; SDL's dummy driver sleeps whole milliseconds and its counts
mean nothing). Tekken 3, two seats on one PC, 3,600 frames (60 s), real device (period 441):

| Link | Kit | Seat 1: gaps / trims / clears | Seat 2: gaps / trims / clears |
| --- | --- | --- | --- |
| 5 ms, jitter 15 ms, delay 2 | before | 1 / 4 / 7 | 4 / 8 / 17 |
| 5 ms, jitter 15 ms, delay 2 | after | 1 / 0 / 0 | 1 / 0 / 0 |
| 20 ms, jitter 40 ms, delay 3 | before | 0 / 1 / 39 | 1 / 2 / 42 |
| 20 ms, jitter 40 ms, delay 3 | after | 11 / 0 / 0 | 11 / 0 / 0 |

The same game alone, same 60 s: 1 gap, 2 trims. What is left on the rough link: a waiting iteration still advances the schedule by a
whole period, never made up, so the sound waiting runs one frame short per wait. Keeping the schedule there (the frame runs when it
comes and the next ones catch up) brought that link to 1 gap and 1 trim per seat, but it changes what the time sync sees (the faster
seat of `tools/netplay_lockstep_selftest.py`'s drift check then waits on 359 of 900 frames, its bound is 225): it is left to the
multiplayer work, not in this change. The digests of every run stay equal (PASS). One run
each on a busy PC: counts, not a timing; physical latency unmeasured. The queue model (the other machines) gets the first change only;
its own regulation in a session is not measured here.

**Stamps** (against `spec/multiplayer` `ba3ff615`): the host stamp of all 21 profiles (`rrhk_main.c`, `rrhk_audio.c`, `rrhk_ring.c`,
`hostkit_internal.h`); no game stamp; quick states unchanged.

## Commodore Amiga 500 and 1200: the host writes its saves back at a match's clean end (next release)

The host kit's rule of 19 November 2026 (Arthur: « Oui, réécris la carte de l'hôte à la fin »): nobody writes a save file during a
match, the host included, and the host writes its saves back once when the match ends cleanly (it ended, the host closed the room or
quit its game; never after a desync, a refused boot or a lost connection). Both Amigas now give the kit's `session_save_commit`
(`rrhk_amiga.inc`, `rr_amiga_session_save_commit` in `amiga_session.cpp`): the session's saves as they are in memory at that moment (the
last entry of every name) go to the host's own save folder, `datas/games/amiga-<identity>/saves/`, the one the game reads alone. Only a
file that changed is written: its previous bytes are first kept at the same name in the folder beside it, `saves.bak/` (a one-step
backup: the backup of an earlier match goes), then the new bytes replace it through a temporary file and a rename
(`amiga_savefile.h`, `commit_folder`); a file the game removed during the match is kept in `saves.bak/` and then removed. A backup that
cannot be written leaves its file as it was, and the host is told « Sauvegarde non mise à jour ». The backups sit beside the save folder,
not in it, so the game never reads or lists them. A guest never writes. Before this, an Amiga host kept what the game saved during the
match in memory only. Proof (no ROM): `tools/amiga_rollback_selftest.py` now also runs, on both models, a host seat (its folder holds
the final saves of the session's memory after the commit, `saves.bak/score` holds the previous file, an unchanged file has no backup,
no temporary is left, a second commit moves nothing) and a guest seat (its folder byte for byte as before); the harness of
`tests/test_amiga_resload.py` checks `commit_folder` alone (changed, unchanged, new and removed files, a refused backup, a name outside).

**Stamps** (against `spec/multiplayer` `8b8477d4`): the Amiga 500 and Amiga 1200 game stamps (`amiga_session.cpp`, `amiga_session.h`,
`amiga_savefile.h`) and host stamps (`rrhk_amiga.inc`); the Amiga quick-state key moves (it hashes `amiga_session.cpp` and
`amiga_session.h`): an older quick state is refused cleanly, the file's layout is unchanged.

## Commodore Amiga 500 and 1200: an Imploder block whose checksum differs (next release)

Body Blows (AGA) stopped at frame 459 of a two-player match on the Amiga 1200 ("Imploder checksum differs"), on every seat and
alone too once the game reaches that data: one of the 72 Imploder blocks of its install (on its third disk image) carries a stored
checksum that is not the sum of its words, and the game unpacks it through `resload_Decrunch`. The block unpacks whole: its stream
ends exactly where its output begins, as all 72 do. `rr_decrunch.c` now refuses an Imploder block for its checksum only when its
stream does not land exactly too (WHDLoad's autodoc: every unpacker checks that the decompression succeeded; this install runs under
WHDLoad). The authored Imploder stream of `tests/test_amiga_resload.py` now leaves the top byte of an odd stream unused, as the packer
does, so it lands exactly; the harness checks that a block with only its checksum changed unpacks to the same bytes and that one whose
size is wrong is still refused. Proof: every Imploder block of the install unpacks; Body Blows (AGA) converted again passes
`tools/netplay_game_smoke.py --rollback 5 --frames 3000 --hold 4 --latency 30 --jitter 10` (the run that stopped at frame 459: 3,000 frames, 521 corrections on the second seat, the digests equal).

**Stamps** (against `spec/multiplayer` `5af44e9d`): the Amiga 500 and Amiga 1200 game stamps; nothing else.

## Commodore Amiga 500 and 1200: multiplayer on the rollback tier (next release)

Both Amigas answer a session (`netplay_session`) at the NES's level: rollback and the host's F8 / F9 for everyone. The game gives an
in-process snapshot (`rr_amiga_snap_*` in `native/amiga_machine/amiga_session.cpp`: vAmiga's state through its own serialiser without
the per-component checksums, the sound path, the resload state, the inputs held, the keyboard's held keys, and the session's saves) and
a digest (named session fields, then vAmiga's serialised state, then the saves). The changes to the adapted vAmiga are in a new
module, `retrorecomp/amiga_vamiga_session.py`, outside the generator's pinned sources as `amiga_vamiga_display` is (nothing it adds runs
unless a snapshot is saved or loaded, so no path can notice it): `amiga_vamiga.py` is not edited, `GENERATOR_REVISION` stays 2 and the
paths of the base keep their engine. They are `CoreComponent::rrSave` / `rrLoad`, walking the components by reference (no allocation per
call), the sound path's state into a buffer the session holds, and the keyboard's held keys (`Keyboard::keyDown`), which no vAmiga snapshot keeps: a load left those of the timeline left, and a Start (the
guest's Return) pressed again after a rollback could be lost on one seat (the first smoke desynchronised at frame 1199 for that). A
quick state also sets them again now, from the keys it holds. In a session the host's saves travel (session ABI 8: `session_save`,
`session_save_put`): every seat reads its own save files once into the session's memory, the host plays on its own, and a guest plays
on the host's image instead (an image is never empty, so a host without saves leaves a guest without its own too); what the game saves
then stays in that memory, inside the snapshot, never written to disk during the match (the host writes it back at a clean end: see
the section on `session_save_commit`); port 1 holds the joystick;
the CPU speed (x1, x2, x4) is a run-changing option: this PC's value goes in the host's HELLO (`session_options`, `cpu=N`), the host's
reaches every seat (`session_option`), and the F2 row is refused during the match. The host's restart takes every seat back to the
state the session started with (a snapshot), never the process restart a game alone does. Joystick games; the keyboard and the mouse
are not carried. Alone, nothing changes: the session code is reached only with the converter's pipes. Proofs: `tools/amiga_rollback_selftest.py`
(an authored slave: copper, a bitplane, blits, audio DMA, five interrupt sources, the keyboard with its handshake, a resload save and two
loads) passes on both models (a snapshot after every frame changes nothing, a load at any frame replays the same frames and digests, a
load is complete at once, wrong sizes refused, the session's saves taken back, no allocation); without the held-keys fix it fails. A
headless `--rollback-check 7` of the converted Lotus 2 (a 5-frame rollback every 7 frames for 3,000 frames on the native game, the
two-player route): every replayed frame identical. `tools/netplay_game_smoke.py --rollback 5 --latency 30 --jitter 10 --hold 4
--save-at 600 --load-at 1500` passes on Lotus 2 (Amiga 500: 521 corrections, up to 5 frames deep), the digests equal before the load
and different after, and `--restart-at 900` passes; the same `--rollback-check` and smoke pass on All New World of Lemmings (Amiga 1200,
its Kickstart 3.1: about 300 corrections per seat, up to 5 frames deep). On the Amiga 1200 the host waited at the prediction cap 51
times in 3,000 frames: replaying 5 frames of that machine fits less easily in a frame (its cost is not measured). Snapshots: about 2.2 MB (Amiga 500) and 3.7 MB (Amiga 1200), the constant boot ROM left out in a session (`MEM_SAVE_ROMS` off); their time is not measured yet (a quiet
PC, with the owner's agreement).

**Stamps** (against `spec/multiplayer` `a08bdd4e`): the Amiga 500 and Amiga 1200 game and host stamps, and their quick-state key; nothing else.
| [Windows packing: the call filter's last candidate](#windows-packing-the-call-filters-last-candidate-next-release) | none | **the build stamp of every profile** (`retrorecomp/packing.py` is a build input) | unchanged |

## MSX, MSX2, MSX2+: the host's save travels in a session (next release)
## MSX, MSX2, MSX2+: the host's save travels in a session and is written back at its end (next release)

The MSX family gives the kit `session_save` / `session_save_put` (session ABI 8, `native/msx_machine/msx_snapshot.inc`), so a
guest plays the match on the host's save instead of its own. The image, little-endian: `RMSXSAV1`, the cartridge's battery SRAM
(its size, then its bytes), then for a disk game each disk as the sectors that differ from the embedded disk (their number, then
each sector's index and its 512 bytes): a disk game's saves travel as a few sectors, not as its 720 KB disks, which would pass the
kit's 2 MB bound. A guest checks the whole image before it changes anything (magic, SRAM size, disk count, every sector index and
the exact length), then puts every disk back as embedded (its own copies never count) and the host's sectors over them. The guest's
loop runs its first frame before SETUP comes, on the seat's own saves (as the Game Boy found): in a session the game keeps the
machine at power-on (an in-process snapshot taken before the first instruction), and `session_begin` (SETUP) loads it on every
seat, then lays the match's image (the host's own bytes, or those handed to the guest), so a game that read its save in that
first frame still starts from the host's everywhere. The SRAM and the disk in drive A are in the digest. A host whose rewritten sectors would still pass the bound plays the embedded disks
for the match like every seat, keeps its copies untouched and is told. A guest writes **no save file**, its end included: the
SRAM file and the disk copies written at the process's end now wait for the side effects too, where before a guest's last
write would have put the host's bytes in its own file. The MSX2 clock keeps no file (it starts on the same date everywhere); a
for the match like every seat, keeps its copies untouched and is told. **Nobody writes a save file during a match, the host
included** (the kit holds every seat's side effects off from SETUP to the end, 8b8477d4): the SRAM file and the disk copies
written at the process's end now wait for the side effects too, where before a guest's last write would have put the host's
bytes in its own file. **At a clean end the host writes its save back once** (`session_save_commit`): the SRAM file when the
SRAM differs from what the host sent (msx_sram.c's atomic write), and the copy of each disk the game wrote (a staged file, then a
rename), each previous file kept first as `.bak` (a staged copy, then a rename); a file that could not be backed up is not
rewritten, and an SRAM file that was unreadable at the start stays as it is ("Save not updated"). A game with no save has no
hook. The MSX2 clock keeps no file (it starts on the same date everywhere); a
restart for everyone keeps the match's SRAM and disks, as the machine's reset does. Alone, a game reads and writes its saves as
before.

**Proofs** (`tools/netplay_game_smoke.py --seats 2 --rollback 5 --host-save ... --save-at 600 --load-at 1500 --restart-at 2200`,
3,000 frames, 30 ms with 10 ms of jitter, a scratch library, no window): Deep Dungeon (MSX) and Dragon Slayer II - Xanadu
(MSX2+) on the owner's own SRAM saves, and the authored disk that writes (`tools/msx_write_disk.py`, MSX2+, the owner's FS-A1WSX
BIOS) on the copy the game itself wrote alone (one sector, a 527-byte image): every seat boots on the same digest, the save,
load and restart fall on the same frames, every digest is equal, and only seat 1 holds the save file at the end; the boot
digests are those of the power-on state with the save (each differs from the end of the seat's own first frame). The image each
digests are those of the power-on state with the save (each differs from the end of the seat's own first frame). The
write-back (a clean end by STOP ended): the authored disk started from a blank copy, the game wrote its sector during the match,
and at the end the host's copy equals the in-memory disk (the hash its game printed), its `.bak` equals the blank copy; on the
copy the game had written alone the same sector was written again, so the file is the same and the `.bak` is the previous file;
on Deep Dungeon and Xanadu the scripted pads did not change the SRAM, so nothing was rewritten and no `.bak` was made. The
guests' folders hold no save file in every run. After a refused boot the host's file is untouched and no `.bak` is made. The image each
host game sent (its real SAVE_OUT, read through `session_game.py`) is byte for byte the one the guests were handed. Negative
controls: a guest handed the same image with a blank SRAM, or with no sector, is refused at boot ("does not start from the same
state as the host's").

**Stamps** (against `spec/multiplayer` `2d3cc8c1`): the MSX, MSX2 and MSX2+ game and host stamps; nothing else.
**Stamps** (against `spec/multiplayer` `8b8477d4`): the MSX, MSX2 and MSX2+ game and host stamps; nothing else.

## MSX: a MegaROM with no direct mapper store is probed, not refused (next release)

A cartridge larger than the plain sizes whose bytes hold no `LD (nn),A` store to a mapper register (it reaches its registers through
computed addresses) was refused at conversion ("its mapper could not be recognised"). It now goes to the mapper probe, the short
reference runs under each mapper that already settle Aleste and the battery boards, and is refused only when no run is credible.
Bubble Bobble (MSX2, 128 KiB) converts as ASCII 8, with C-BIOS and with the player's own MSX2 BIOS: 0 interpreted, equal to the
reference, its title screen drawn. A cartridge the static guess already recognised takes the same path as before.

**Stamps:** the MSX, MSX2 and MSX2+ game stamps (`retrorecomp/msx_conversion.py`).

## MSX, MSX2, MSX2+: multiplayer on the rollback tier (next release)

The MSX family answers a session (`netplay_session`) at the NES's level: rollback and the host's F8 / F9 for everyone, on the shared
shape of the driven machines (session ABI 5). The game gives an in-process snapshot (`native/msx_machine/msx_snapshot.inc`: the disk
in drive A, the other disks written so far, the drive's counters and the disk-request rule, the keyboard matrix and the joysticks, then
the quick state's body without the last picture, which the next frame draws again) and its digest (FNV-1a 64 over the same bytes); a
silent frame draws and plays nothing, and the SRAM file and the disk copies wait while side effects are off. Joystick games; the
keyboard is not carried in a session. Proofs: a headless `--snap-probe AT:N` (snapshot, N frames, load, the same N frames: every digest
and every picture equal; a save over other bytes identical; a wrong size refused) passes on an authored FM cartridge, an authored disk
that writes inside the window, Salamander, Metal Gear, Dragon Slayer II - Xanadu (SRAM) and Xak III across two requested disk changes;
`tools/netplay_game_smoke.py --rollback 5 --save-at 600 --load-at 1500` passes on Salamander (MSX), Metal Gear (MSX2) and The Goonies
R Good Enough (MSX2+), the digests equal before the load and different after. Snapshots: 85 KB to 417 KB for a cartridge, about 1.15
MB for a disk game; their time is not measured yet (a quiet PC, with the owner's agreement).

**Stamps** (against `spec/multiplayer` `ea1ac0ba`): the MSX, MSX2 and MSX2+ game and host stamps; nothing else.
| [PC Engine: rollback and the host's F8 / F9 for everyone](#pc-engine--turbografx-16-rollback-and-the-hosts-f8--f9-for-everyone-next-release) | **the PC Engine game stamp** (`native/pce_machine.cpp`, `pce_machine.h`, `pce_machine_internal.hpp`, `pce_snapshot.cpp`, `pce_snapshot.h`, `pce_main.c`, `retrorecomp/pce_build.py`, `systems/pc_engine.py`) | **the PC Engine host stamp** (the adapter `adapters/rrhk_pce.c`) | unchanged (the snapshot is a session's, not a quick state's) |

## Sharp X68000: rollback and the host's F8 / F9 in multiplayer; the computers share only the pads in a session (next release)

[X68000.md](X68000.md). **The computers (`rrhk_computer.inc`, commit ca357e84):** while a session runs, only the two pad words
reach the guest on the X68000, Atari ST, Amiga and MSX family: no key or mouse of the PC (`player_poll` gives none), the guest
keyboard stays off (Ctrl+Alt+K and the F2 row say it is not shared), no function key, no local menu, focus or gamepad Start,
no disk or fast-loading key of one seat; Start stays the guest's Return of the first player, from the pad word. Alone, nothing
changes. **The X68000:** a session snapshot in memory (`state/snapshot.c`: `rr_x68k_snap_bound/save/load`, `rr_x68k_digest`) built
from the quick state's own visitors (`rr_state.h`: a fixed buffer, arrays copied as they are in memory, the 10 MB of RAM the bus
can write, the last presented picture size), without allocation. The presented picture is not in it: a load marks every line to
be drawn again, and the redraw marks and the line work buffers are stored empty, so seats that loaded at different frames keep
equal digests; the disks are journals (the 1 KiB blocks that differ from the
original, per disk of the set and per drive), bounded by 512 KiB. In a session every seat plays the export's own disks from
memory with a fresh SRAM and its peripheral clock at zero (the RTC reads 1 January 2000), and nothing reaches the host's files
(`base74/fileio.c`: the set's images are served from memory, any other write is swallowed; the disk choices are not saved at
the end). Silent frames show no picture and queue no sound; the seat's own disk keys and fast loading do nothing. The portable
quick-state format (RRX68MS1) does not change. **Proof (ROM-free in the kit's sense, on a real game):** `--rollback-probe`
(save, 600 frames, load, the same 600 frames: every digest equal; a second save over other bytes identical; a load one byte short
refused with no change; the digest of the loaded state equal; the presented picture of every replayed frame equal) passes at 25 save points of Bubble Bobble (Dempa), from the boot and
its disk loading to two-player play. **Stamps** (compared with spec/multiplayer 65cf35f3): the X68000 game stamp and host
stamp; the host stamp of the Amiga, Amiga 1200, Atari ST, MSX, MSX2 and MSX2+ (`rrhk_computer.inc`). The X68000 quick-state
key moves (`reference_host.c`, `rr_state.c`, `snapshot.c` are hashed): quick states of earlier X68000 exports are refused
cleanly. **Limits:** joystick games only (keyboard and mouse are not carried); both players need the same IPL and font ROM (they
are inside the executable); a session that writes more than 512 KiB of disk blocks ends with the reason.

**The host's save travels to every seat (session ABI 8).** An X68000 game saves on its own disks and in SRAM, so the host's save
image (`session_save`, `rrhk_x68k.inc`) is the 1 KiB blocks where the host's copies of the set's disks differ from the export's
originals, then its 16 KiB of SRAM (at most the kit's 2 MiB). Every seat, the host too, starts the match from the export's disks
with those blocks and that SRAM, in memory only; a guest's own files are never read or written. The snapshot and the digest
carry a hash of each disk the match started from, so a different start is refused at the boot digest. The host part of the
snapshot also keeps the frame rate (it follows the screen mode, which a restart changes) and takes the drives' poll counter
afresh after a load. **Proof:** `netplay_game_smoke --rollback 5 --host-save` (a written copy of Bubble Bobble's disk, only in
seat 1's folder) `--save-at 600 --load-at 1500 --restart-at 2200`: PASS, the same boot digest on both seats and a different one
without the save; the guest's copy stays the original. A restart alone on the rollback tier: PASS (it failed before the frame
rate was kept). The probe gains `--rollback-reset-at` (a restart in both timelines): snapshots 5 frames before to 50 after a
restart replay equal. **Stamps:** the X68000 game and host stamps.

**At a clean end of the match, the host writes its save back (session_save_commit, Arthur 19 Nov 2026).** Nobody writes during
the match (every write of a session stays in memory). When the match ends cleanly, the kit asks the host only: each disk of the
set whose final bytes (a drive's image as its eject writes it back, otherwise the session's image) differ from the host's file,
then `sram.dat` if the SRAM differs, is written atomically (`<name>.new`, then a replace) with the previous file kept as
`<name>.bak`; an unchanged file is left alone. **Proof:** `netplay_game_smoke --rollback 5 --host-save sram.dat` (a real SRAM
whose RAM-size field says 1 MiB; the machine writes its 2 MiB there every frame) `--save-at 600 --load-at 1500 --restart-at 2200`:
PASS; the host's `sram.dat` is the image the hook reports (same FNV), its `.bak` is the planted file, its disk is unchanged and
not rewritten; the guest holds no `sram.dat`, no backup, and its disk is the original. **Stamps:** the X68000 game and host stamps.

## Atari ST: multiplayer on the rollback tier (next release)

The Atari ST answers a session (`netplay_session`), with the rollback tier and the host's F8 / F9 for everyone. The adapted Hatari gets a
lean in-memory snapshot of its own (`retrorecomp/atarist_hatari_rollback.py`, GPL-2.0 like Hatari; `native/atarist_machine/atarist_snapshot.h`,
outside the engine's native inputs, so the Atari ST's qualified paths stay valid: the engine identity is unchanged): it keeps what a game
changes (the 68000 with its prefetch, the RAM and the I/O area, the MFP, the YM2149, the keyboard controller, the WD1772 and the position in
an IPF track, the cycle and video counters, the generator) and leaves out what it does not (the TOS, the configuration, the images, the
flux), restores in place at once (a digest or a save right after a load is complete), and keeps the table of sectors a game wrote (up to 64
KB, a bigger table refuses the save). A game on STX, SCP or Kryoflux images has no snapshot and stays on the delay tier. The digest is named
fields in a fixed order (the same on Windows and Linux). In a match the host's written disk travels to every seat (session ABI 8: `session_save` gives the table of sectors its game wrote, the bytes of
its `disk-writes.bin`; a guest plays on it in memory through `session_save_put`; a guest with none from the host starts from the export's own
disks, and so does a host whose table is more than a snapshot carries, 64 KB, with a notice); no seat reads its own saved writes or writes the
file during the match (the writes stay in memory); when a match ends cleanly the host's table is written back once to its own `disk-writes.bin`
(`session_save_commit`: a temporary file, then a rename, the file it replaces kept as `.bak`; nothing is written when the match played on the
untouched disks because the saved table was too big), reads the session's clock (the board's real-time clock, when a model has one, runs on
UTC 1 January 2000), and a restart goes back in place to the machine after its first frame. The keyboard and the mouse are cut (joystick games
first), except Start's Return (the pad word of player 1) and the keys the host types (session ABI 9); in a match the two joysticks and those keys come from the
frame's words whatever this window's focus or menus (a seat whose window lost the focus ran neutral joysticks while the others ran the network's), and the adapter's
state of the held keys travels as one byte per key after each snapshot (a key is an edge, so a load without it would press or release them again: a first
version with Start's Return only desynchronised at frame 59); the disk change is off. Alone, a game runs as before.

**Proofs:** `tools/atarist_snapshot_check.py` (no ROM: authored 68000 programs on the timers, the picture, the PSG, the keyboard controller
with joysticks and the floppy controller, 19 runs: save, run, load, run again, every digest equal; a save right after a load byte for byte
the first; a damaged or wrong-size snapshot refused with the machine untouched; the table of writes restored; two restarts from different
moments give the same machine). `tools/netplay_game_smoke.py` on Bomb Jack converted by this branch: `--frames 3000 --rollback 5 --latency 30
--jitter 10 --hold 4 --save-at 600 --load-at 1500` PASS (tier rollback on both seats, 3,000 frames, 50 digests equal, the save and load at
the same frames); with `--save-digests`, with and without `--save-at 600 --load-at 1200`, the 20 digests before the load are equal and the
10 after it differ; `--restart-at 700` PASS (both seats restart before frame 702). A snapshot takes 1.44 MB (bound 1.51 MB with the table of
writes); its time is not measured yet (a quiet PC, with the owner's agreement). Not a claim of fidelity or of gameplay validation.

**Host's written disk:** `tools/netplay_game_smoke.py --seats 2 --frames 3000 --rollback 5 --latency 30 --jitter 10 --hold 4 --host-save <authored disk-writes file
of 3 sectors> --save-name datas/games/<game>/disk-writes.bin --save-at 600 --load-at 1500 --restart-at 2200` PASS on Bomb Jack (every seat boots on the same digest,
which differs from the untouched disk's; only seat 1 holds the file; 50 digests equal; the restart before frame 2202); a host table of 200 sectors (more than 64 KB)
with guests handed none: PASS on the untouched disk's digest. After a match (`--host-save` with the authored file, 1,500 frames): the host's `disk-writes.bin` equals the final table, its `.bak` equals the previous file, the
guest's folder holds no file; with the 200-sector table the file is left as it was and no `.bak` appears. The probe also checks the image given, a buffer too small refused, forgotten, put back and a damaged image refused.

**Stamps:** the Atari ST's game stamp (the adaptation of Hatari: `atarist_hatari_rollback.py`, `atarist_snapshot.h`) and host stamp (the
adapter `rrhk_atarist.inc`); nothing else. The Hatari adaptation digest moves: the machine core is built again once.

## Game Boy Advance: multiplayer on the delay tier (next release)

The profile answers a session (`netplay_session`, input sharing only: one pad, every seat's buttons merged). What moves, against `spec/multiplayer` at `87b3fe97` (`compilation_inputs.role_stamps`, every other machine equal): the Game Boy Advance **game** stamp
(`native/gba_machine.cpp`, `gba_machine.h` and the profile) and its **host** stamp (`rrhk_gba.c`: the digest, `side_effects`, `session_begin`); the build stamp and the engine's patch set (55 patches, no new recompiler build) do not change, so the shared paths and the site's limits do not either.
- **The digest** is read from the engine's own state container, section by section, and hashes the CPU registers (not the generated code's call stack), the memories and the bus words, the registers, the cartridge save and the picture processing unit, plus a running hash of every mixed sample. The sound section (it holds the host's output ring) and the cartridge clock chip's block (it writes the PC's own time even on a cartridge with no clock) are left out. The first version of the digest differed between two runs of the same inputs for that reason; the test switch `RETRORECOMP_GBA_DIGEST=<n>` prints it with each section's hash.
- **Session rules** (the multiplayer contract): the cartridge save is read as when playing alone and a guest never writes it (`side_effects`); the cartridge's clock starts from the session's clock (`RRHK_SESSION_CLOCK`, 1 January 2000 UTC) through the engine's guest epoch, which it reads once when it starts; `session_begin` checks it. No snapshot (the engine's state container allocates per call): the delay tier only, no rollback.
- **Proof so far:** the digest is the same in two processes that play the same script (30 digests over 3,000 frames of Mario Kart Super Circuit, none unstable, all different); two copies on one PC on the delay tier (`netplay_game_smoke.py --machine gba --delay 2 --latency 30 --jitter 10`, 3,000 frames): PASS, 50 digests equal on both seats. Physical latency is not measured.
- **The host's restart for everyone** (Shift+F1) works in place in a session. It used to relaunch the engine's start-up, which opened the kit's loop again and closed the session's pipes: every seat stopped with exit code 1 a few frames later. In a session the player now keeps the machine's state before its first frame in memory and a restart loads it back (the cartridge save of the present state replaces the boot one, as a power cycle keeps the battery save). Stamps against `spec/multiplayer` `864b9573`: the Game Boy Advance **game** stamp only (`2ac1bcdddb63` to `ba9e07105df1`), host and build unchanged, every other machine equal. Proof: `netplay_game_smoke.py ... --seats 2 --delay 2 --machine gba --frames 1200 --restart-at 600` PASS (20 digests equal, exit 0 on both seats); the digests of that run and of the same run without the restart are the same up to the restart and different after it (index 10 of 20), so the restart acts. Alone, a restart is as before.
- **The host's save travels to every seat** (session ABI 8, `session_save` / `session_save_put` in `rrhk_gba.c`). The image is the cartridge-save section of the engine's state container (the chip's memory, SRAM, Flash or EEPROM, as the machine reads it from power-on); a guest puts it back into the same section in memory before the boot digest and plays on it, and never writes its own file. A save whose size does not fit the guest's chip is refused with a notice (that seat keeps its own, and the boot digest says "another save"). Before this, a host with a save and a guest without one booted on different digests and the match was refused. Nobody writes a save file during a match (the kit holds `side_effects(false)` on every seat, the host included); at a clean end the host's `session_save_commit` writes the save as it is in memory to its own file through the engine's atomic write, after keeping the previous file as `<save>.bak` (also written atomically); a match whose memory save did not change writes nothing. The engine itself writes its save when its start-up function returns, whatever the player decided: a seat that must not write one now has the save marked unchanged first (a guest that had a changed save wrote a file at the end of the match before; no test had a guest with a changed save). The test switch `RETRORECOMP_GBA_SAVE_IMAGE=<file>` writes the image the host hands out. Stamps against `spec/multiplayer` `8b8477d4`: the Game Boy Advance **game** stamp (`ba9e07105df1` to `a32c53665d15`; `gba_machine.cpp`, `gba_machine.h`) and **host** stamp (`201e74171cae` to `ddbf3ade2101`; `rrhk_gba.c`) only; build and every other machine equal. Proof (Mario Kart Super Circuit, a 64 KB Flash save authored for the test, two copies on one PC, `--machine gba --delay 2`): both seats boot on the same digest, which is the one of the host's save; handed a blank image instead, the match is refused at boot ("another save"); with a game write simulated at frame 1000 (test switch `RETRORECOMP_GBA_SAVE_TOUCH`), after the match the host's file holds the final save, its `.bak` is the previous file byte for byte, and the guest's folder holds no save.
- **Alone,** nothing changes: the session code is reached only with the pipes, and the digest is never computed.

## Every machine: multiplayer, two to four players over the local network (next release)

In preparation on the multiplayer branch; this section is completed when it merges. What moves: the game stamp of the 21
profiles (the simulation identity that lets two players check they run the same game, and the recipe mode: modules of every
game stamp), so **every export is converted again once**; the host stamp of every machine with the host kit (the session code
of the shell: `hostkit_session.h` at session ABI 7 (the sticks travel since 7), `rrhk_session.inc`, the chat `rrhk_chat.inc`, new catalogue strings in the
eight locales). Alone, a game runs as before: the session code is reached only when the converter starts the game with its
pipes (`RETRORECOMP_NETPLAY_PIPE`), and the solo restart, controls, quick states and pacing are unchanged (tests of the kit's
session self-test, "restart alone" and "alone"). In a session the host's F8 / F9 save and load the match's state for everyone at
the same frame, in memory only and for that match only: the players' own quick-state files are never read or written, and the
format of a quick state does not change. Cartridge saves and preferences are untouched. **Proof so far** (17
November 2026, two Windows PCs on a home network, Contra NES): two-player matches with no desync, the host's restart for
everyone, 150 ms of simulated round trip on the rollback tier with no wait, the in-game chat on keyboard and gamepad.
Physical latency is not measured.
**19 November 2026:**
- Two-PC acceptance (`tools/netplay_lan_acceptance.py`, 3,000 frames: the host's save, load and restart for everyone, 50
  digests compared) PASS on every machine the second PC can run, with 4 seats across the two PCs on the Mega Drive (Gauntlet
  IV, Team Player). The N64 needs a Vulkan device that PC lacks; its 4-seat proof is on one PC.
- Three fixes the runs found:
  - a game with sticks (PlayStation, N64) now plays over the network: the datagram carries the records' FLAG_AXES;
  - a CPS-1 board's DIP switches pass the launch;
  - the two-PC tool spaces its guests (the room holds two handshakes per address at a time).
- **Protocol 4 of the room** (both rooms, the converter only, no stamp moves):
  - an X25519 exchange in the handshake, tied to the invitation's secret;
  - ChaCha20-Poly1305 on every control frame and match datagram, with the same sizes as the tags of protocol 3;
  - from `cryptography` 50.0.2, pinned in `requirements.txt` and now frozen into the Windows converter too (about +3.7 MB;
    notice `licenses/cryptography.md`).
  - This closes the stated limit of the local room (a guest who captured another's handshake could compute its keys), and is
    the base of the Internet room. A converter of protocol 3 and one of protocol 4 do not join each other.

**Session ABI 9 (19 November 2026, after Arthur's first two-PC test):** the host stamp of every machine with the host kit moves
again (`hostkit_session.h`, `hostkit.h`, `rrhk_session.inc`, `rrhk_options.c`, `rrhk_events.c`, the catalogue), and so does the
host stamp of the Neo Geo (`rrhk_ng.c`), the Amiga 500 and 1200, the Atari ST, the MSX family and the X68000 (`rrhk_computer.inc`
and their adapters, `reference_host.c`). Alone, nothing changes for a player.
- **The host changes the options of the match.** In a session the host's run-changing rows (the sprite limits, the Neo Geo
  boost and its MVS / AES machine, the Amiga CPU speed, the CPS DIP switches; the PlayStation's PGXP, CPU resolution and renderer rows, below) are no longer faded:
  the host changes one, its game sends `RELAUNCH`, the match ends for everyone (`STOP_RELAUNCH`, lobby reason `relaunch`; no
  save written back) and the room starts it again at once with the new options (a power-on, as a restart). A guest's rows stay
  faded and show the host's values. A Neo Geo guest is started in the host's machine (`--aes` / `--mvs`), its own setting kept.
- **The host types on a computer.** Ctrl+Alt+K in a session is the host's: its held keys (a 16-byte bitmap of the typing keys,
  never a function key nor a Ctrl+Alt chord) travel in its input records (`input_records` protocol 3 of the datagrams) and
  every seat's Amiga, Atari ST, X68000 or MSX types them at the same frame; a guest stays on its pad. A seat's session input no
  longer depends on its window's focus (the Atari ST and MSX ran their joysticks neutral on an unfocused seat).
- Proof: the kit's session self-test (27 scenarios: the host's relaunch, a guest's change asking nothing, the host's keys) and an
  end-to-end relaunch between two worker processes; real games: see the multiplayer notes.

## Super Nintendo: multiplayer, digest and rollback on the boards without a chip (next release)

On the multiplayer branch (`spec/snes-rollback`). The Super Nintendo answers a session: `SnesProfile` sets `netplay_session`, and the
adapter (`rrhk_snes.c`) gives the host kit a **digest**, a **snapshot** and **side effects**. The digest (`rr16_snes_digest`,
`snes_backend.c`) walks the engine's own serializers in a fixed order (65816 and its registers and cycle counters, WRAM and the beam,
interrupt and joypad state with the multitap, SPC700 and APU RAM with the S-DSP **without its output ring** (the audio thread moves its
read cursor), PPU registers, memories and ports (not the widescreen sprite classifier, which is presentation), DMA/HDMA, cartridge
RAM and every enhancement chip), each field named, none a pointer. The snapshot is the engine's rollback snapshot
(`RtlNetplaySnapshotToMemory` / `RtlRollbackLoadFromMemory`: the guest state, the execution residue, the output ring blanked on save
and kept live on load) in a buffer the kit owns, about 335 to 345 KiB, the bound measured once; the retained picture of the field
(presentation) is left out of a rollback snapshot, so a quick state file keeps one more byte (the flag that says it is there).
`side_effects(false)` stops the cartridge save write, for a silent frame and, for a guest, for the whole session (the periodic write
and the one at exit). **Boards proven for rollback: the ones without an enhancement chip, and one real game of each chip** (Super FX: Star Fox; SA-1: Kirby
Super Star; CX4: Mega Man X3; S-DD1: Street Fighter Alpha 2; DSP-1: Super Mario Kart), the chips' state being the engine's own
(`cart_saveload`); the other games of those chips run the same code and are not a proof of their own. **Stamps:** the Super Nintendo game stamp
moves (the profile) and its host stamp moves (`snes_backend.c`, `rrhk_snes.c`, the new `snes_cpu/machine_checks.c`): its exports are rebuilt and
converted again once; no other machine's stamp moves. **Quick states:** the Super Nintendo key hashes `snes_backend.c` and so moves; an
older quick state is refused cleanly (accepted by the multiplayer specialist, 17 November 2026). **Proof so far** (17 November 2026, one
PC, no ROM in the repository): `tools/snes_machine_selftest.py` (ROM-free: four authored cartridges, NTSC and PAL, with and without a
raster interrupt, 6,708 checks: a save over other bytes is the same bytes, load then save is the same bytes, a replay of 40 frames from
three save points equals the first run in digest, picture and sound, a wrong size and a too small capacity are refused); the same
checks over Super Mario World, Secret of Mana and Chrono Trigger (digests equal at every frame of every replay; the picture differs in at
most 3 of the first replayed, silent frames and the sound block differs because the live output ring is kept, both presentation);
`netplay_game_smoke.py --frames 3000 --rollback 5 --latency 30 --jitter 10 --hold 4 --save-at 600 --load-at 1500` on the same three
games, and on the five chip games above: PASS, tier rollback on both seats (Super Mario World: 499 and 279 corrections, deepest 4), the save and the load at the same
frames, digests equal; with `--save-digests`, equal up to frame 1499 and different from frame 1559 when the load acts. The
digest of every frame of a scripted two-pad route of 3,000 frames (`tools/snes_digest_cross_os.py`: the digest and its seven partitions) is **identical between
Windows (clang, llvm-mingw) and Linux (GCC 14, Debian 13)** on Super Mario World, Star Fox (Super FX) and Kirby Super Star (SA-1), 17 November
2026. Physical latency and the cost of a save or a load are not measured.

## Master System and Game Gear: rollback snapshot and the frame handed over at an instruction boundary (next release)

The multiplayer branch asks every machine for an in-process snapshot (`snap_bound`, `snap_save`, `snap_load`) so that a session can
leave the delay tier. The banked engine now has one: `smsrecomp_snap_*` in `native/gamestate.inc`, with the raster state in
`video_mode4.inc` and the sound chip in `psg_state.inc`. It is the same content as the quick state (CPU, banks, RAM, VDP, raster
buffers and sprite history, PSG and its undrained samples, Light Phaser latches, the cycle and frame counters of the timeline), copied
as it stands in memory, about 460 KB, never a file and never sent. The cartridge has no RAM in this runtime. The functions engine
and the reference interpreter have none (size 0: they stay on the delay tier, as before). The frame also changes hands later: the
runner ends a frame inside the video step, which an `IN` or `OUT` on the VDP or the PSG runs in the middle of the instruction, so a
snapshot taken or loaded there would cut an instruction in two. In a session the adapter marks the frame and the banked loop gives
it to the kit at the end of the instruction that follows, on the request word it already tests after every instruction: a game
without a session runs the same code as before and pays nothing. What moves: `gamestate.inc`, `gamestate.h`, `state_io.h` and `psg_state.inc` are inputs of every console (the group `*`, as `core.py`), so the game stamp of
all nine consoles moves with this change (the generated game is the same for every console but the Master System and the Game Gear, whose runtime gains the
functions above); `video_mode4.inc` is the pair's own. The host stamp of the Master System and the Game Gear moves with their adapter. The quick state format
and its keys are unchanged. The digest values change by at most one instruction of timing, the same on every seat of a build. **Proof**: `tools/gamestate_selftest.py` mode 3 (save at a frame, run twenty frames, load, run them
again: every digest identical, from the frame edge the kit uses; a wrong size, a foreign buffer and a short buffer refused; the
odd latches restored after the machine was wiped), on the main loop and on an EI + HALT loop; the real-game proof and the timing
come with the kit change.

## Capcom CPS-1, CPS-1.5 and CPS-2: the rollback tier and the host's F8 / F9 for everyone (next release)

The three boards give the multiplayer session what the NES gives it: the digest, an in-process snapshot (`snap_bound`, `snap_save`,
`snap_load`), a frame that can be run again silently, and `side_effects` (profiles `cps1` and `cps2`: `netplay_session = True`, four
seats). What moves: **the game stamp and the host stamp of the CPS-1 and of the CPS-2** (`cps1_machine.c`, `cps1_opm.cpp`, `cps1_main.c`
and the host files `cps1_host.c`, `cps1_persistence.c` and the adapter `rrhk_cps1.c`); no other machine, and the identity of the shared
paths of both boards changes with the machine's sources, as for any change of them.
- **One field list.** The quick states and the snapshot are written by the same routine (`state_put`); the quick-state format, key and
  magic do not change, so the quick states of earlier exports still load. The snapshot is the same bytes without the 344 KB picture (the
  next frame draws it again: checked by comparing the first pictures after a load with the reference's) and with the EEPROM's "file is
  behind" flag at 0. It is 347 to 401 KB, allocates nothing (the three chip buffers of a save are static, and the YM2151 state vector
  keeps its capacity), and the digest is the FNV-1a of the same fields in the same order.
- **The EEPROM in a session** (session ABI 8, 19 November 2026): the host's EEPROM image (128 bytes) travels to every seat before the boot digest
  and after a restart (`session_save`, `session_save_put` in `rrhk_cps1.c`, the code in `cps1_host.c`), and a guest plays on it in memory only:
  its frames ask for no file (`side_effects` off for the whole session) and its own file is as it was. Nobody writes the file during the match, the
  host included (the kit's rule of 19 November 2026): when the match ends cleanly the host's EEPROM, as it is in memory, is written back once over
  its own file (`session_save_commit`, `rr_cps1_save_commit`: a temporary file then a rename, the previous file kept whole as `.bak`; a file that
  could not be used at the start is never written over; a board without an EEPROM has no hook). This replaces the first rule of the rollback work (a blank EEPROM on every seat, nothing read or
  written). The digest covers the EEPROM, so a seat on another image is refused at boot. Proof: `netplay_game_smoke.py --seats 2 --host-save`
  with the real EEPROM of Super Street Fighter II, the raw 128 bytes as `--save-image`, `--save-at 600 --load-at 1500 --restart-at 2200`, rollback
  tier, 3000 frames: PASS, every seat boots on the same digest (not the blank one), only seat 1 holds the file; control: guests handed a blank
  image are refused at boot (`boot_mismatch`). The write-back, on 1944 (`1944j`, whose EEPROM changes on a coin) with its real save: after the match
  the host's file holds the memory of the game (its checksum equals the digest the game printed at the write), differs from the file before by the
  one byte the match changed, `.bak` equals the file before, the guest's folder has no `saves` folder, Arthur's own file is untouched.
- **The DIP switches are run-changing options** (session ABI 6): the adapter reports the host's three DIP words in its HELLO
  (`dips=00ff,00fc,009f`) and applies the host's to every seat from SETUP, in memory only (a guest's own settings file is never written and
  comes back when it plays alone). The DIP page was already run-changing, so its keys are refused in a session. Proof: 1941 with a guest whose
  settings file holds other DIP values: boot mismatch without the host's options, PASS (1200 frames, rollback tier) with them.
- **Players 3 and 4** are read in `run_frame` and no longer in `before_frame`: a frame run again after a correction (hostkit session,
  "silent") calls `run_frame` with the session's words but never `before_frame`, so pads set there were those of the last live frame and
  four-seat matches diverged at the first correction (found by the four-seat smoke run). Alone, the word is the same.
- **Proof** (17 November 2026, tree of `spec/cps-rollback`, converted with the portable llvm toolchain): the determinism probe in the
  game itself (`tools/cps1_snap_check.py`, the game's `--snapshot-check`: four save phases, 61 checks each: save over other bytes equal,
  wrong size refused with the machine left as it was, digests and pictures equal after a load and a replay of 120 frames, the digest
  sees a changed byte) passes on Super Street Fighter II (CPS-2), Warriors of Fate (CPS-1.5 with EEPROM), 1941 and Captain Commando
  (CPS-1); a game built with the work RAM left out of the load fails it on 14 checks (the probe sees an incomplete snapshot). Two copies
  on one PC, rollback tier, 3000 frames, 30 ms one way with 10 ms of jitter, the host's save at frame 600 and load at 1500 for
  everyone: PASS on Super Street Fighter II and Warriors of Fate; four seats PASS on Captain Commando. Super Street Fighter II with
  `--save-digests`: the rollback tier and the delay tier give the same digests and history; with and without the save and load the
  digests are equal up to frame 1499 and differ from the first one after the load. Not measured: the cost of a save or a load, physical
  latency, hardware fidelity.
## Neo Geo: rollback and the host's F8 / F9 for everyone in a match (next release)

**What changes.** A Neo Geo export answers a multiplayer session like the NES: the delay tier, the rollback tier (the console's frames
are run again on a corrected guess, five at most) and the host's F8 / F9 for everyone. Alone, nothing changes: the session code is
reached only when the converter starts the game with its pipes (`RETRORECOMP_NETPLAY_PIPE`).
- **The snapshot** (`rr_ng_snap_*`, `native/neogeo_state.c`): the same fields as the F8 state (both CPUs, work RAM, NVRAM and memory
  card, protection RAM, LSPC with its video RAM and palettes, YM2610, timers, RTC, pending interrupts, the 68000 slice, the YM and
  board latches, the LSPC pipeline, the frame index) in memory only, 225,417 bytes on NAM-1975 and 233,609 on KOF 2003 (PVC board),
  with no allocation and without the picture. A load keeps the fix-layer mask latch and the audio chain as they are, so a correction
  does not blink the edge band or cut the sound.
- **The digest** (`rr_ng_digest`): the three hashes the route traces already carry (68000 registers, the serialized hardware state with
  its latches, the Z80) and the frame index.
- **The clock of the match** (`session_begin`): the board's RTC starts from 1 January 2000 UTC on every seat, not from the PC's time.
- **The host's save for everyone** (session ABI 8, `session_save` and `session_save_put`): the image is "RNG1", the sizes of the MVS NVRAM and of the memory card, then both
  (67,596 bytes, the payload of the `.rrsave` file in memory). The host's travels to every seat before the boot digest, so a host whose NVRAM (bookkeeping, high
  scores) or memory card holds data and a blank guest start from the same machine; a guest writes nothing (`side_effects(false)`) and a size or header that is not
  this board's is refused (`refused: save`). Nobody writes a save file during a match, the host included (the kit holds `side_effects(false)` from SETUP to the end); when the
  match ends cleanly the kit calls `session_save_commit` on the host only: the in-memory NVRAM and card are written to the host's own `.rrsave`
  atomically (a temporary file, then a rename), the file it replaces kept as `.rrsave.bak`, with the same checks as the write at exit (an unchanged
  memory writes nothing; a file another copy changed is not overwritten). Proof: NAM-1975 with a real save (the card-save route's, 218 non-zero NVRAM
  bytes), two copies, rollback 5, F8 at 600, F9 at 1,500, restart at 2,200: PASS, one boot digest on both seats (different from the blank save's), only seat 1 holds the file; after the match the host's file is the final image (its NVRAM and card hashes are the ones the game logged
  from memory at the commit), `.bak` is byte for byte the previous file, no temporary file is left and the guests' folders hold nothing.
- **The host's values for everyone** (session ABI 6): the clock mode (the F5 boost: 24 MHz and 381 sprites, or standard) and the
  machine (MVS or AES) of the host's PC ride the room into every seat's SETUP as `clock=enhanced|standard` and `system=mvs|aes`
  (`session_options`, `session_option`), and F5 and F11 are refused (run-changing rows) for the match. The clock mode is applied
  in the game; a machine cannot be: MVS and AES boot different firmware, so a seat whose game runs the other one refuses the match
  naming `system` (the player switches with F11, which restarts the game, before the match).
- **The determinism probe:** `--snapshot-probe WARM RUN` on the game and `tools/neogeo_snapshot_probe.py` (save, run, load, run: every
  digest and the last snapshot byte for byte equal; a refused load changes nothing).

**What it does not change.** The code generated for the game, the F8 / F9 state of a game alone (`neogeo_state.c` keeps
`rr16_state_capture` and `rr16_state_restore` as they were), the 68000 and the Z80, the interpreter fallback counting.

**Hot path:** no. A frame does the same work when no session runs; the two records the fallback makes check one flag
(`rr_ng_feedback_off`) on the path that already runs the interpreter. The cost of a snapshot per frame has not been measured (timing
only with Arthur's word on a quiet PC).

**What moves:** the Neo Geo game stamp and the Neo Geo host stamp, besides what the multiplayer release moves for every machine; no
other console (nothing shared is edited). **Quick states:** unchanged. Evidence: the probe passes at four save points (300, 2,500,
3,001 and 4,700 frames) on NAM-1975 and KOF 2003; two copies on one PC, rollback tier 5, 30 ms latency and 10 ms jitter, the host's
save at frame 600 and load at 1,500: PASS on both games (NAM-1975: 307 and 498 rollbacks, KOF 2003: 340 and 425), digests equal on both
seats and, with `--save-digests` (NAM-1975), equal to a run without the save and load up to frame 1,499 and different after it.

## Game Boy: rollback and the host's F8 / F9 for everyone (next release)

Branch `spec/gb-rollback` (from `spec/multiplayer`). The Game Boy joins a session on the **rollback tier**, in input sharing (a handheld
plays "everyone" or "turns": `netplay_shared_only`), with the host's F8 / F9 for everyone, like the NES. Alone nothing changes: the session
code is reached only with the pipes, and the quick-state file of the runtime is not touched.

**What it adds.** `native/gb_machine_state.h` (appended to the runtime's `gbrt.c`, where the static core-state capture is): an in-memory
snapshot of the context (the quick-state file's core state: CPU, mapper registers, the MBC3 clock in cycles, DMA, HDMA, serial, LCD-off
bookkeeping), the five memory blocks, the cartridge RAM, the video unit's and the sound unit's own structs, and the five fields of the sound
unit's lazy scheduling. **A snapshot never synchronises the sound unit** (the quick-state file does), so taking one changes nothing of the
future. **One size for every game**: 343,696 bytes (the cartridge RAM counts at its largest, 128 KiB, a smaller one is padded), so that the
host kit can ask it when the session opens, before the guest registers its context. `rr_gb_snap_bound`, `rr_gb_snap_save` (0 on failure, no
allocation), `rr_gb_snap_load` (complete at once; refuses a wrong size, a damaged header, another ROM; the context is untouched).
`rr_gb_digest`: FNV-1a over named fields in a fixed byte order (CPU, mapper, clock, time, the sound unit's scheduling, DMA, HDMA, serial, the
memory blocks, the video unit by field, the sound unit by field in `audio.c`: `gameboy_hardware.adapt_audio_digest`), never a raw struct,
nothing of the pictures, the interpreter and performance counters or the host. The adapter (`rrhk_gb.inc`) adds the pad registers of the
platform layer and wires `snap_bound`, `snap_save`, `snap_load`, `digest`, `side_effects`, `session_begin`.

**In a session.** The kit's shared way for the machines whose guest owns the loop (session ABI 5) needs no hook of the Game Boy: a silent
frame is a frame the generated loop runs and ends at its next `rrhk_frame_done`. The adapter does the rest: a session's frame is one whole
machine frame (the smooth LCD slices of the loop are off in a session: `gb_platform_get_smooth_lcd_transitions`), the pads are the session's
words (fixed for the frame), nothing goes to the sound output and no picture is copied during a silent frame, and the cartridge RAM and
clock files are not written when `side_effects(false)` (a guest's whole session, silent frames: `write_persistence_transaction` is patched in
`gameboy_host.py`). The MBC3 clock runs on the session's clock (`session_begin`: 1 January 2000 UTC on every seat, the registers set from it,
no time stamp of the clock file or of this PC). Saves load as a game alone loads them and the boot digest refuses two seats whose cartridge
RAM differs, until the kit's transfer of the host's saves arrives.

**The host's save travels (session ABI 8).** `session_save` gives the host's cartridge RAM (its `.sav` file, read from the persistence folder
because the kit asks at HELLO, before the game has loaded anything; only the sizes a cartridge has), `session_save_put` takes it on a guest. The
guest's loop runs one frame before the session's SETUP, on its own save, so SETUP (`session_begin`, which is also called at every restart)
puts every seat back in **the state the game began in** (kept at the first slice, in a session only: the snapshot of the machine), then the
match's cartridge RAM (blank on every seat when the host has none), then the session's clock. A guest never reads or writes its own save
or clock file. The RTC counters are the session clock's, never the file's.

**The host's save is written back at a clean end.** Nobody writes a save file during a match (the kit holds the side effects off from SETUP to the end,
the host included). When the match ends cleanly the kit calls `session_save_commit` on the host: the in-memory cartridge RAM goes to the host's own `.sav`
through the runtime's atomic transaction (a staged file, then a replace), after the previous file was copied to `.bak` (no copy, no write). The clock
stays the session's and is never written; a guest writes nothing. **Proof** (19 November 2026, two copies of Super Mario Land 2, `--host-save`,
rollback tier, 3000 frames, save at 600, load at 1500, restart at 2200): the host's file after the match has the FNV-1a the game logged for the in-memory
image it wrote, its `.bak` is the planted file byte for byte, the host's file differs from it (the game rewrote the planted bytes, which are not a real
save), and the guests' folders hold no save, backup or temporary file.

**Proof.** `tools/gameboy_machine_selftest.py` + `native/gb_machine_checks.c`: three authored cartridges (MBC1 with RAM, MBC3 with a clock,
MBC5 on the colour hardware) in 420 random slices with random host writes between them (DMA, HDMA, sound, timer, serial, LCD, scroll,
mapper, memory), compared with an independent whole-state hash of the raw context: a run replayed from a snapshot gives the same digest,
the same whole-state hash and the same snapshot bytes after every step (2,055 steps replayed from two load points, on the same context and
on one allocated apart); a snapshot every step changes nothing of the run; the same bytes over any buffer; refusals leave the context as it
was; the digest moves with every group of fields and not with the pictures or the counters; snapshots were taken in the middle of an OAM DMA
(115), the DMA start-up (40), an HDMA (217), a timer reload (13), a serial transfer (253), a halted CPU, a switched-off screen and at a
finished frame (EI-pending: its own case). The same checks pass on four real cartridges read from the player's library, never copied
(Tetris, Super Mario Land 2, Link's Awakening, Pokemon Yellow: 4,420 snapshots compared each), through the interpreter.
**Two copies of a real game on one PC** (`tools/netplay_game_smoke.py`, input sharing "everyone", `--rollback 5 --latency 30 --jitter 10
--hold 4 --save-at 600 --load-at 1500`, 3000 frames, 17 November 2026): Tetris and Pokemon Yellow (MBC5 with battery RAM) PASS on the rollback
tier on both seats (Tetris: 260 and 426 corrections, deepest 5, 3,035 and 3,230 snapshots, equal boot digest and 50 equal digests, the save
and the load at the same frames); a delay-tier run and a rollback-tier run with the same pads and delay give the same digests; the same run
with `--save-at` / `--load-at` is equal to it before the load and different after (the load acts). Not measured: the cost of a snapshot on a
quiet PC (about 336 KB copied per frame), physical latency, a Linux run, a game with a clock.

**Stamps** (compared with `spec/multiplayer`, all 21 machines): only the Game Boy moves, its **game** stamp (the runtime part, the two
patches and the persistence patch; the multiplayer branch already moves every game stamp, so this adds no further reconversion) and its **host**
stamp (the adapter). Quick states: no key moves. The profile gets `netplay_session = True`.
## PC Engine / TurboGrafx-16: rollback and the host's F8 / F9 for everyone (next release)

The PC Engine joins the multiplayer rollback tier at the level of the NES: its adapter gives the host kit an in-process snapshot, a digest and the side-effects switch ([PC_ENGINE.md](PC_ENGINE.md#multiplayer-rollback-and-the-hosts-f8--f9-for-everyone-17-november-2026)),
and its profile says `netplay_session`, with up to four seats through the multitap, which a session plugs in for every seat and whose players 3 and 4 are read inside `run_frame`; the host's Backup RAM travels to every seat, and the host writes it back once to its own file when a match ends cleanly (the previous file kept as `.bak`). **What moves:** the PC Engine game stamp (`native/pce_machine.cpp` and `.h`, the new `pce_machine_internal.hpp`, `pce_snapshot.cpp` and `.h`, `pce_main.c`,
`retrorecomp/pce_build.py` with its new files, `systems/pc_engine.py`) and the PC Engine host stamp (`adapters/rrhk_pce.c`); no other machine moves. A PC Engine export of the previous release is
converted again once, as every export is for the multiplayer release. **Quick states:** unchanged, and a session never reads or writes them. **Hot path:** none added to a solo game: the snapshot is reached only through the adapter's
pointers when the converter starts the game with its pipes; the only change a solo frame sees is one call that tells whether the player's record is on (it was a direct pointer). **Proof:** the probe of the snapshot on an authored card and the Street Fighter II
board, and Bomberman '93 in two copies on the rollback tier with a save and a load for everyone; nothing is timed.
**Alone, the multitap is plugged too:** solo pictures are unchanged on the panel (14 of 15 cards show the same pictures over 1,500 frames of the play walk; the fifteenth, Street Fighter II' CE, had its second fighter copy the first player), and two-player local play now works (pad II was a copy of pad I).

## NES: the Four Score, players 3 and 4 (multiplayer) (next release)

On the multiplayer branch (`spec/nes-fourscore`, cut from `spec/multiplayer`). A NES game that reads the **Four Score** (the
adapter that gives two ports four controllers) now gets players 3 and 4, alone and in a session. **Machine:** each port's serial
register is 24 bits long instead of 8 (`nes_machine.py` `_four_score`, patching the engine's `hw_apu.c` in the staged copy only):
$4016 returns player 1's eight buttons, then player 3's, then the signature `00010000`; $4017 players 2 and 4 and `00100000`
(nesdev wiki, "Four Score"). A game built without it (`RR_NES_FOUR_SCORE 0`, every game but those in the catalogue) loads ones
behind the first byte, which is what the engine shifted in before: its reads are unchanged. The extra pads reach the machine as
controller ports 2 and 3 of `cyc_set_controller`, and the register is part of the saved APU (`RrFourScore`), so a quick state,
the in-process snapshot of the rollback tier and the digest carry it. **Adapter:** `rrhk_nes.c` reads players 3 and 4 inside
`run_frame`, not in `before_frame`, so a frame run again after a correction (silent, no `before_frame`) has the corrected words;
`players()` says 4 and the binding table has four rows only for those games. **Converter:** `nes_catalog.four_score_game` (NES 2.0
header, default expansion device 2, or the exact title of a game written for the adapter; never a Zapper game) sets
`RR_NES_FOUR_SCORE` in the project's CMake file; the report says `input_players` 4 and `four_score`; the NES profile has
`netplay_seats` 4 as a ceiling (`netplay_seats_ceiling`) and `lobby_check.players_in_report` reads the report's number, so the
lobby seats 4 for these games and 2 for every other. **Stamps:** the NES game stamp and host stamp move (every NES export is
converted again once, as for any NES engine change); **the NES quick-state key moves** (it hashes the staged `hw_apu.c`); an older
quick state is refused cleanly. No other machine moves. **Proof so far:** the ROM-free fixture `tools/nes_machine_selftest.py`
(authored cartridges, mappers 0 and 4, NTSC and PAL, 3 more checks than the two-player build): the 24 bits of both ports with the
four pads and the signatures, a new strobe, a read cut in the middle then saved and loaded (quick state and snapshot), the digest
seeing the pads of players 3 and 4; the build without the Four Score is unchanged (749 and 751 checks as before, plus its own). Not
proven: a Four Score game played on four seats (see the multiplayer notes of the same branch), the Famicom's own four-player adapter
(different wiring, not supported), and the catalogue's titles were not all checked against a dump.

## NES: the host's save travels in a session (next release)

On the multiplayer branch (`spec/nes-session-save`, session ABI 8). `rrhk_nes.c` gives the kit `session_save` / `session_save_put`
over `rr_nes_session_save` (`nes_machine_state.inc`): one image of the cartridge's nonvolatile memory (region 0: battery RAM,
EEPROM) and the Datach's EEPROM (region 1), magic `RNS1`, the two lengths little endian, the two regions. A guest imports the
host's image before the boot digest, so every seat starts from the host's save; a wrong magic, length or size is refused and
changes nothing. A guest also writes **no save file**: `side_effects(false)` makes the program's end-of-game write return at once
(`rr_nes_saves_blocked`, the patched `cyc_save.inc`), where before a guest overwrote its own save file with the match's. Alone, a game
loads and saves as before. **Proof so far:** the ROM-free fixture (`tools/nes_machine_selftest.py`: a battery MMC1 cartridge, the size
query, a save over other bytes identical, a blank machine then the host's image gives the host's bytes and the same CPU, hardware and
memories as a machine that loaded that save before its power-on, wrong images refused, the ban on writing). With The Legend of Zelda
(MMC1, 32 KB of battery memory) on two seats, 300 frames, no seed anywhere: both boot digests equal and only the host's folder holds a
save file at the end (the guest writes none, though the same run changed the memory on both). **Not proven:** that a guest plays on the
host's save in a real match: `tools/netplay_game_smoke.py` does not carry the host's save to the other seats (only the room worker does),
so a run with a save on the host alone is refused there by the boot digest, as it would be without the feature; the same save on both
seats passes. The Datach's region 1 is checked by the layout only.

**Written back at a clean end (19 November 2026, `spec/nes-save-commit`, session hook `session_save_commit`).** The kit holds every
seat's side effects off during the match, the host's included; when the match ends cleanly it calls the hook on the host only, and
the program's host file (`cyc_host.c`, `nes_runtime.py`) writes the memory's save back atomically (the program's `save_write`: a
temporary file, then a rename), keeping the previous file as `<file>.bak`; a file already equal to the memory, or a blank memory with
no file yet, is left alone as at the end of a game played alone. A game with no cartridge save installs no hook. **Proof:** The
Legend of Zelda, two seats, `--host-save` with a raw 32 KB seed: PASS, equal boot digests and 25 equal digests, "the host's save was
written back", the host's `.sav` changed (8,154 bytes differ from the seed), its `.bak` is byte for byte the seed, and the guest's
folder holds no save file. Not compared: the written file against the machine's final memory by an independent reader (it is
`cyc_nvram_export` written by the existing `save_write`), the Datach's own file, a desync or a lost connection (no write by the kit's rule).

## Mega Drive: the rollback tier and the host's F8 / F9 for everyone (next release)

The Mega Drive leaves the delay tier: its adapter gives the in-process snapshot of `hostkit.h` (`snap_bound`, `snap_save`,
`snap_load`), so a session plays it on the rollback tier and the host's F8 / F9 save and load the match's state for everyone.
The snapshot is the whole state that decides later frames: the 68000, work RAM, the machine (VDP, bus, cartridge RAM, sound
CPU), the YM2612 and PSG with their undrained samples and timers, the queued sound events, the scheduler, the pads, the
cartridge chips and the gun. A frame can end with the 68000 suspended inside an instruction (a 68000-to-VRAM DMA, a bus wait),
with the sound CPU suspended in a read of the 68000's bus, or with a bus request not yet granted. A quick state refuses those
frame ends; the snapshot keeps them. It holds the two live continuations (the fibers' stacks, raw) and the statics those
instructions read when they resume, kept raw because nothing they point to moves in a process: fibers are now kept for the
whole run (a destroyed one is parked and reset in place when one of the same size is needed). Memory only, never written to a
file or sent; no allocation per call once the YM2612's two buffers exist. A silent frame (a rollback running frames already
heard again) gives the sound device nothing. All of it is added to the private runtime copies by
`retrorecomp/megadrive_rollback.py`; the files of the Mega Drive quick-state key are not touched, and a quick state keeps its
portable form. A build without step code (none of the current conversions) gives no snapshot and stays on the delay tier.
**Size:** `snap_bound` is 427,430 bytes; the largest save seen was 211,454 bytes (game fiber stack at most 1,844 bytes, sound
CPU's 1,288). Save and load times are not measured. **Proof** (17 November 2026, Streets of Rage 2, llvm build):
`tools/megadrive_rollback_selftest.py` (`native/md_rollback_checks.c`, linked with a game build's objects). First, an authored
program in work RAM with no game code: 224 rollbacks, each a save, eight frames with changing pads, a load and the same eight
frames, every frame's digest and sound identical and the snapshot after them the same. Of those, 153 at frame ends with the
68000 inside an instruction under DMA, 186 with the sound CPU suspended on the bus and 10 with a bus request pending. Seven
negative controls (a part from the later state: the game fiber, the bus scheduler, the glue, the interpreter, the sound CPU's
phase, the 68000, the RAM) are each noticed. A save over other bytes gives the same bytes; short buffers, wrong sizes and a
wrong header are refused. Second, the game itself: 1,800 frames from power-on, 434 rollbacks, all exact (128 with the 68000
inside an instruction, 242 with the sound CPU suspended). Two copies on one PC (`tools/netplay_game_smoke.py --frames 3000
--rollback 5 --latency 30 --jitter 10 --hold 4 --save-at 600 --load-at 1500`): PASS, both seats on the rollback tier (192 and
528 rollbacks, deepest 5), the save at frame 602 and the load at 1502 on both. With `--save-digests`, with and without the
save and load: 25 of 25 digests equal before the load, 0 of 25 after (the load acts). **Stamps:** the Mega Drive game, engine
and host stamps move (compared with `spec/multiplayer` 1f5b2340); no other machine's. **Existing exports:** a Mega Drive
game converted before stays on the delay tier until it is converted again (the multiplayer release converts every export
again anyway).

## Sony PlayStation: multiplayer, the digest and the host's settings (delay tier) (next release)

On the multiplayer branch (`spec/psx-mp-digest`). The PlayStation's adapter gives the host kit a **digest** (`rr_psx_digest`:
CPU and GTE, RAM, scratchpad, sound RAM and the memory card in a fixed little-endian order, no VRAM), `side_effects` (a guest
records no runtime hint), `session_save` and `session_save_put` (session ABI 8: the host's memory card travels to every seat
before the boot digest; no seat writes a card file during the match; at a clean end the host's card is written back to its own
file through `session_save_commit`, atomically, the old file kept as `<card>.bak`; a restart carries the card as it is),
`session_begin` and `session_option` with four keys the host sets for everyone: `pgxp`, `pgxp_texture`, `cpu_resolution`
and, with PGXP On, `renderer`; their F3 rows are refused during a match. `rr_psx_session_values` (`session_options`, session ABI 6) gives the host's own values.
The profile answers a session (`netplay_session`); the sticks travel with the pads (session ABI 7). Alone, nothing changes: every
new path is reached only in a match (or by the headless `--match` and `--digests` of the evidence). What moves: the
PlayStation's game stamp (the profile, its runtime and Beetle's adaptation: `rr_psx_spu_ram`), so a PlayStation export is
converted again; the PlayStation's host stamp; one new catalogue string (« Not during a multiplayer game ») moves the host stamp
of every machine with the host kit, as the multiplayer line above already does. Quick states: unchanged. **Proof**:
[PLAYSTATION.md section 10](PLAYSTATION.md#10-multiplayer-the-digest-and-the-hosts-settings-next-release-delay-tier) (Ape
Escape: digests equal on the same run with PGXP Off and On, and between Windows and Linux; the settings that change the run
measured and pushed; two copies through the session on the delay tier PASS with the host's values). Physical latency is not
measured.

## Nintendo 64: multiplayer on the delay tier, and a change of resolution in play keeps the renderer's memory (next release)

The Nintendo 64 gives the session what the delay tier needs. **Digest:** the machine's state as named fields folded as values in a
fixed order (`rr_n64_cpu_digest`: the VR4300's registers, PC and COP0 / COP1, the RSP's memory and registers, the RDP, MI / VI / AI
/ PI / RI / SI, PIF RAM, the whole RDRAM, then the save memory with the four paks), never the quick state's bytes (about a
kilobyte of the core's own block holds heap and code addresses that differ from run to run). **The host's saves travel to every
seat** (`session_save` / `session_save_put`, session ABI 8): the whole save memory, cartridge EEPROM, SRAM or flash and the four
controller paks (296,960 bytes), put in memory before the boot digest; **nobody writes a save during the match**, the host included (the kit's
`side_effects`), and **at a clean end the host writes its save back once** (`session_save_commit`: its saves.bin written
atomically, the previous file kept as saves.bin.bak). **The cartridge clock** (Animal Forest's) runs on the session's from `session_begin`, plus the emulated
seconds, the same date on every seat whatever its time zone; the core sets up its devices during the first frame, so the clock is
put back after it. **ParaLLEl-RDP records on the emulation thread** in a session even if asked otherwise (its own worker is not
deterministic). **The keyboard's Stick actions** read this PC's keys, so in a session every port's stick is the session's: the kit
folds them into the sticks this PC sends (`stick_actions`). The profile sets `netplay_session`, so the converter offers its games. The
host's restart is refused in a session (the Nintendo 64's restart starts the program again, which would end the match): the kit's
`session_no_restart` answers Shift+F1 and the pad's Restart combination with « Not during a multiplayer game » and asks nothing
of the other seats. The graphics rows stay per seat: they change the picture only. The blank controller paks needed nothing: the
core formats them before it seeds their serial generator, so their serials are zero on every run.

**The fix that comes with it, alone too:** a change of internal resolution (or supersampling) in play started ParaLLEl-RDP
again from scratch, so its hidden RDRAM, its TMEM, the count that seeds its dither noise and the last commands that set its
registers were lost: GoldenEye 007's RDRAM differed from the frame after the change (1,158 of 1,800 frames, 15 November gate
traces), and a seat changing its picture mid-match would have left the others. The renderer's memory now goes over to the new
renderer, as a quick state carries it. **Proof** (17 November 2026, Windows, RTX 3090, Quick conversions of Super Mario 64 and
GoldenEye 007, 3,600 frames of the main route, headless): two runs give the same 61 digests; inputs that differ from frame 1,500
give the same digests before and different ones after; another save memory changes the start digest; the resolution changed at
frame 1,800 leaves RDRAM, sound, CPU registers and PC equal to the run without it on every frame; a quick state resumed in a
fresh process gives the unbroken run's digests from its first frame on (the digest taken right after the load, before any frame,
differs: the delay tier never takes one there). **Two copies in a session on one PC** (`tools/netplay_game_smoke.py`, 30 ms
latency, 10 ms jitter, delay tier): Super Mario 64 and Mario Kart 64 with two seats over 1,800 frames, Mario Kart 64 with four seats
over 1,200 frames, every digest equal on every seat (`PASS`). **The sticks** (`--sticks`, Mario Kart 64, two seats, 1,800
frames): `PASS`, and against the same run without sticks (the same pad words: the same history) all 30 digests differ from frame
59 on: the sticks reach the machine, the same on both seats. **The host's save** (Mario Kart 64, four seats, 1,800 frames, the
host's real save from an earlier match, the guests' folders without one): `PASS`, every seat's boot digest the save's, no guest
writes a save file; without the transfer the same case was refused at boot (a Debian host's save against Windows guests, 19 November).
**The write-back:** after that match the host's saves.bin equals the final in-memory image (the checksum its game printed) and
saves.bin.bak the file it started from, the guests' folders hold no file; a host with no save (two seats, 3,000 frames) ends with
the save the game wrote during the match, and no backup.
Physical latency is not measured. **Stamps:** the Nintendo 64's game stamp (`n64_cpu.c`,
`n64_session.cpp`, `n64_player.c`) and host stamp (`rrhk_n64.inc`); Nintendo 64 quick states of 1.8.0 are refused cleanly (the
state key hashes the session sources).
## Super Nintendo: four players (Super Multitap) and the host's cartridge save in a session (next release)

On the multiplayer branch, after the rollback of the section above. **Four players:** a game on the reviewed list of Super Multitap
games (`retrorecomp/snes_multitap.py`: the dump's SHA-256, the title, the pads the game uses, 3 or 4, and where the claim comes from;
Barkley Shut Up and Jam!, Capcom's Soccer Shootout, Secret of Mana, and the Super Bomberman series: Super Bomberman, 2, 4 in its English
translation and 5; Panic Bomber W and B-Daman are games of two players and stay off the list) gets a tap in console port 2 in a session of **three or
four seats** (`session_begin`, `rrhk_session_ports() >= 3`): seat 0 is port 1's pad and seats 1 to 4 are the tap's, the ones the game
does not use left unplugged; the adapter reads the pads 3 and 4 in `run_frame` (`rrhk_pad_word(2)` and `(3)`), never in
`before_frame`. The engine's tap is not transparent (every game reads its pads another way with it: a game of two pads ends in
another state), so a game that is not listed, and a listed game alone or in a room of two, plays as before. The profile says
`netplay_seats = 4` as a ceiling, the report of a game says `players 1 to N` (`qualification_scope.controls`, N from the list) and its
HELLO says the same. **The list is third-party data: the engine itself says no multitap title has been run, and no game was played
with that many pads here; it is a reviewed list, not a gameplay validation.** **The host's save:** `session_save` and
`session_save_put` give the board's battery RAM (the save RAM, the SA-1's BW-RAM, the Super FX's game pak RAM), so the host's cartridge
save travels to every seat for the match, in memory only. **Stamps:** the Super Nintendo game stamp (the list, the report, the header
define of a listed game) and host stamp (`snes_backend.c`, `rrhk_snes.c`, `snes_cpu/machine_checks.c`); the Super Nintendo quick-state key
moves again with `snes_backend.c` (already moving in the section above). Games that are not listed keep the same generated sources.
**Proof so far** (17 November 2026, one PC): `netplay_game_smoke.py --rollback 5 --seats 4 --save-at 600 --load-at 1500` on Barkley
Shut Up and Jam! and `--seats 3` on Secret of Mana: PASS, rollback tier on every seat, digests equal; Secret of Mana in a room of two:
PASS and its boot digest differs from the room of three (the tap is plugged from three seats only); `snes_machine_selftest.py --rom`
on Secret of Mana checks the save image out, back in and a wrong size refused (8 KiB). Super Bomberman 2 and Super Bomberman (USA), 4 seats, rollback with a save at 600, a load at 1500 and
a restart for everyone at 2200: PASS, the report says `players 1 to 4`. Not proven: the games' own use of four pads, a
host save that differs from a guest's.

## Super Nintendo, Mega Drive, PC Engine: the host's save written back at the end of a match (next release)

Arthur's rule of 19 November 2026 (« Oui, réécris la carte de l'hôte à la fin »): nobody writes a save file during a match, the host included
(the host kit holds `side_effects(false)` on every seat from SETUP to the end), and at a **clean** end of the match (ended, the host closed the
room or quit its game; never after a desync, a refused boot or a lost connection) the kit calls the new hook `session_save_commit` on the host
only. **The Super Nintendo has it:** `rr_cart_save_commit` (new in `native/cart_save.c`, the file the three cartridge-save machines share)
writes the battery RAM as it is in memory to the host's own `.rrsram` once, atomically (a staged file, then a replace), after keeping the file
it replaces as `<file>.bak` (a staged copy, then a replace; the previous save, one step back); it answers false, and leaves the file that was
there untouched, when no file is open, or the previous file cannot be kept or the new one cannot be written. A board without a battery
leaves the hook empty (the kit lets the machine exit as alone). The Mega Drive and PC Engine adapters can call the same function with their
own file's words. **Stamps:** the Super Nintendo, Mega Drive and PC Engine game stamps (`native/cart_save.c`, `native/cart_save.h`) and host
stamps (`rrhk_snes.c`, `snes_backend.c`, `snes_battery.c`, `snes_cpu/machine_checks.c` for the Super Nintendo); a quick-state key that hashes
those files moves with them (no compatibility key is carried, as in every release since 1.6.5; battery saves are not concerned: the file format
is unchanged and a file written without the hook still loads). **Proof:** `tools/snes_machine_selftest.py` gains a cartridge with a 2 KiB
battery (type 2) and 27 checks: nothing is written with no file open; the first commit writes a file whose bytes are the memory and no `.bak`;
the second writes the new image and leaves a `.bak` equal to the first file; the next start reads what was committed back; a flush after the
commit writes nothing; a start with the file off commits nothing. A real game (Super Mario World, two seats, rollback tier, 1500 frames, 19 November 2026, one PC): without a file the host's folder
holds one after the match (the kit logs « the host's save was written back ») and the guest's none; with that file planted on the host
(and its bytes handed to the guest, as a room does) the match passes, the host's file is there after it and its `.bak` equals the file
planted. Super Mario World does not change its save on a title screen, so the file equals the planted one: the case of a memory that differs
from the file is the selftest's. Not proven: a match that really changes a save, two PCs, Linux.
## Windows packing: the call filter's last candidate (next release)

**What was wrong.** A Windows game whose code leaves UPX no spare cto byte is packed with a shorter SizeOfCode (the call filter of 1.6.7,
`packing.call_filter_length`). The length it chose, `first - 1`, is always the end of the candidate that opens the interval where the cto value
is taken: that candidate (an E8 or E9, or the 8x of a 0F 8x) stands at length - 5. UPX's scan (`ctok.h`, `ic < size - 5`) stops at length - 6, so
it never saw the candidate and the value looked spare; the run-time stub (`arch/amd64/bxx.S`, which reads a candidate at p while p + 1 < length - 3,
so up to length - 5) does see it, finds the cto as its first operand byte and rewrites an operand the packer never filtered: the CALL or jump goes
elsewhere. `upx -t` and `upx -d` use the packer's bound, and a replay of a route that does not run that instruction cannot see it. Seen on Neo Geo
KOF 2003 (a crash in the multiplayer session's setup, 17 November 2026); checked on the four real exports of the maintainer that carry a
`call_filter` record, from three machines: KOF 2003 (cto 0x60), Sonic The Hedgehog 2 (Mega Drive, 0xb1), 2020 Super Baseball (Neo Geo, 0xbe)
and Dimahoo (CPS-2, 0x95): in all four the cto is the first operand byte of the candidate at length - 5. So it is not rare: **every export packed with a
shortened call filter carries one such site** (harmless while the instruction is never executed; a game that does run it crashes or misbehaves).

**What changes.** The model reads the stub's bound: a length is usable only if no value the packer may take as cto equals the first operand byte of the
candidate at length - 5. The search goes down from the top of every spare stretch (the limit, or the length before an interval) and moves to the next
stretch when the lengths of one fall into an interval of the same value. A packed file's real cto (`upx --fileinfo`, "filter 0x49/0x60") is checked
against the same window and the build is packed again one byte shorter if it hits (three times at most, then the game is published unpacked as built,
with the reason in the report). On the four real builds the length moves by one byte (for instance 1,398,064 to 1,398,063 bytes of KOF 2003), the file
size does not change and `upx -t` passes. Proof on the new code: KOF 2003 converted with a shortened filter (2,005,559 bytes) and the two-copy
rollback session smoke passes; Sonic 2 (Mega Drive), 2020 Super Baseball (Neo Geo) and Dimahoo (CPS-2) converted, their packed replay gate passes (those
builds needed no shortened filter this time). Linux is not touched (its ELF is packed without this filter).

**What moves:** the build stamp of every profile (`packing.py` is a build input: 21 profiles, no game and no host stamp, as
`tests/test_legacy_compat.py` checks for any packing change). Quick states unchanged. **Exports already delivered** with a `call_filter` record carry one
possibly corrupted call or jump; the multiplayer release converts every export again anyway.

## Mega Drive: four players with the Team Player, the 4 Way Play or the J-Cart (next release)

A Mega Drive game made for three or four players gets players 3 and 4 through the adapter it was made for; the player plugs
nothing and chooses nothing (Arthur, 17 November 2026). `retrorecomp/megadrive_multitap.py` picks it per game and adds it to the
game's private bus copy:
- **The control ports** (the Team Player and the EA 4 Way Play, one adapter answering both protocols, as later Team Player units
  did, so a game that probes one then the other finds the one it wants). Chosen when the game declares the Team Player (a `4`
  in the header's I/O support at `$190`), when its code holds its own 4 Way Play probe (the instruction writing `$7C` to
  `$A10005`), or from the reviewed table `TEAM_PLAYER_DUMPS` for a Team Player game that declares nothing (Gauntlet IV).
- **The J-Cart** (Codemasters: two pad ports on the cartridge, at `$38FFFE` and `$3FFFFE`), from the reviewed table
  `JCART_DUMPS` of exact dumps (Pete Sampras Tennis, Sampras Tennis 96, Micro Machines 2, Military and Turbo Tournament 96,
  Super Skidmarks), since no header declares it.

Over a library of 997 Mega Drive dumps, 92 get an adapter (86 on the ports, 6 J-Cart); every other game keeps its two
ordinary pads, unchanged. Such a game has four players everywhere: its report says "players 1 to 4" (`input_players`,
`multitap`), the lobby seats four (`netplay_seats` 4, a ceiling the report and the game's HELLO set per game), alone the host
kit gives players 3 and 4 their own bindings, and in a session they are the session's port words 3 and 4, set inside
`run_frame` so a frame run again after a correction reads the same ones. The adapters' state is part of the rollback
snapshot; a quick state does not keep it (after a quick-state load the adapters start from idle and the game sets them again
on its next read). In a session (`session_begin`) the adapter on the control ports stays plugged only when the session has three
or four ports (`rrhk_session_ports`): two players play on two plain pads, as on a console without the adapter; the J-Cart is
the cartridge and stays. **The host's save** (session ABI 8): `session_save` / `session_save_put` give the cartridge's battery
SRAM or EEPROM, the bytes the game reads back (kept in the bus's save bytes for both), so every seat plays on the host's save,
in memory only; a guest writes none.

**Proof** (17 November 2026, llvm builds, no ROM in the repository): `tools/megadrive_rollback_selftest.py`, mode
`multitap`, drives the three protocols through the bus as a game does (the Team Player identified with TH alone, `3` then
`F`, then its handshake, the four pad types and every data nibble; the 4 Way Play's signature `$7C` and each pad selected
with both TH levels; the J-Cart's two pads at both addresses with both TH levels; an adapter's selection undone by a rollback
load). MAME 0.289 (no multitap attached) showed how the games probe: Columns III, Gauntlet IV and Mega Bomberman toggle TH
alone on both ports; Mega Bomberman first writes the 4 Way Play sequence `$43`, `$7C`, `$7F` to port B. Five games converted
(the internal reference comparison passes on each) and played by four copies on one PC, `tools/netplay_game_smoke.py
--seats 4 --frames 3000 --rollback 5 --latency 30 --jitter 10 --hold 4 --save-at 600 --load-at 1500`: PASS on the rollback
tier for all four seats, the match's save and load at the same frames on every seat, and each game's log says it reads
players 3 and 4 through its adapter: Team Player, Columns III (declared) and Gauntlet IV (from the table); 4 Way Play, General
Chaos and Mega Bomberman; J-Cart, Pete Sampras Tennis. With two seats Columns III passes too and its log shows no adapter
(unplugged below three ports); with four it identifies the Team Player. The host's save: NBA Jam (Team Player, a 256-byte
EEPROM), the host seat on a save file of known bytes and the guests on none (`--host-save`, `--save-image` its raw bytes):
PASS with four and with two seats, every seat starting from the same boot digest, which differs from the boot digest of the
same game without a save (the host's bytes reached every seat). Not proven: a game played to its four-player mode by hand, a Team
Player game expecting the adapter on port B, a fifth Team Player pad.

**Stamps:** the Mega Drive game, engine and host stamps move (`megadrive_multitap.py`, new; its hooks in `megadrive.py`,
`megadrive_cart.py`, `megadrive_rollback.py`; the adapter `rrhk_md.c`); `console16.py` (the report's player count) moves the game
stamps of the Super Nintendo, Neo Geo, CPS-1, CPS-2, PC Engine and PlayStation too, with no change to their games (the
multiplayer release converts every export again anyway). Quick-state keys: unchanged.

## Mega Drive, Super Nintendo, PC Engine: the host's save written back at a match's clean end (next release)

The kit's rule of 19 November 2026 (Arthur: « Oui, réécris la carte de l'hôte à la fin »): nobody writes a save file during a match,
the host included, and when a match ends cleanly the host writes its save back once (`session_save_commit`). The cartridge save file
the three machines share (`native/cart_save.c`) gets that writer, `rr_cart_save_commit`: the memory as it is, at once (no quiet-time
pacing), atomically (a temporary file, then a rename), the file there before kept as `<file>.bak` and put back if the last rename
fails. The ordinary write is unchanged (the Super Nintendo's and the PC Engine's logs of `tools/cart_save_selftest.py` are equal to
those of the revision before, byte for byte). The Mega Drive uses it now (`rr_md_battery_commit`, `rrhk_md.c`); the Super Nintendo
and the PC Engine can call it from their adapters. The Mega Drive also no longer writes its save at exit while its side effects
are off (before, the exit's forced write ignored them: a guest that had its own file would have had the match written into it).
## Mega Drive: the host's save written back at a match's clean end (next release)

The kit's rule of 19 November 2026 (Arthur: « Oui, réécris la carte de l'hôte à la fin »): nobody writes a save file during a match,
the host included, and when a match ends cleanly the host writes its save back once (`session_save_commit`). The Mega Drive calls
the shared writer of `native/cart_save.c` (`rr_cart_save_commit`, added for the Super Nintendo: the memory at once, atomically, the
file there before kept as `<file>.bak`) with its own identity words (`rr_md_battery_commit`, `rr16_md_session_save_commit`,
`rrhk_md.c`). The Mega Drive also no longer writes its save at exit while its side effects are off (before, the exit's forced write
ignored them: a guest that had its own file would have had the match written into it). At the end of a match each seat says its
save's size and FNV-1a on stderr, and the host also what it wrote back.

**Proof** (19 November 2026, Windows, llvm build, no ROM in the repository): `tools/cart_save_selftest.py` passes for the three
machines, with a new Mega Drive scenario (a commit with nothing open is refused and writes nothing; without a file before it writes
one and no backup; after the match changed the memory, the file is the memory at once and the backup is the previous file); the Super
Nintendo's and the PC Engine's logs equal those of `spec/multiplayer` 8b8477d4. Madden NFL 95 (4 Way Play, 8 KiB battery SRAM) on
Nintendo's and the PC Engine's logs equal those of `spec/multiplayer` 89a00c0e (their files are not touched). Madden NFL 95 (4 Way Play, 8 KiB battery SRAM) on
`tools/netplay_game_smoke.py`: two seats with no save anywhere, PASS, the host writes a file back at the end whose bytes equal the
memory every seat reports at the end (`[save]` lines), the guest writes nothing; then two seats on that file as the host's save
(`--host-save`, `--save-image`, `--save-at 600 --load-at 1500`): PASS, every seat on the same boot digest, the save changes during the
match, and at the end the host's file equals the final memory of both seats, its `.bak` equals the file planted before, and the
guest's folder holds no save. Four seats with no save pass too; four seats with the host's save did not start (every seat on the
same boot digest, then an exception in the smoke tool's link thread; reported to the multiplayer specialist). Not run: the two-PC run
with a real save.
guest's folder holds no save. The same with four seats on that file: PASS, the host's file equals the final memory of the four seats, its `.bak` equals the planted file, the guests write nothing. (Two earlier four-seat runs did not start, in the smoke tool's link thread; eight runs since, NBA Jam and Madden NFL 95, three and four seats, on the kit commits before and after the save rule and on this change, all pass.) Not run: the two-PC run with a real save.

## Every machine: a Restart the game tile in F2 (next release)

[HOST_KIT.md](HOST_KIT.md#d32), D32. The F2 menu (`rrhk_menu.c`) gains a tile before Quit, **Restart the game** (`RR_ICON_RESTART`,
a new tile icon in `retro_menu.c`): it goes back to the game and asks the loop (`rrhk_hub_take_restart`, `rrhk_main.c`) for the
restart the pad's Restart combination does: the machine's `reset` alone, the host's restart of every seat in a multiplayer
session (`rrhk_session_restart`; the session pipe and its ABI do not change). A guest, and the Nintendo 64 in a session, have no
such tile. **Texts:** "Restart the game" in the eight locales, catalogue regenerated. **Proof:** the kit's capabilities
self-test (558 checks: the tile restarts once and goes back to the game; the graphics and options tiles are one step further
left; the host's « Change this option? » before a relaunch, ABI 9: No and Esc drop the key, Yes gives it back once). Two more
texts in the eight locales for that question. **Stamps:** no game stamp moves; the host stamp of the 21 profiles moves: every export is upgraded once (rebuilt), none
converted again. **Existing exports:** unchanged until that upgrade.

## Every machine: the pad's Options button opens the F2 tiles, Quit is their last tile (next release)

[HOST_KIT.md](HOST_KIT.md#d31), D31. `game_options.h`: a seventh combination, **Options** (`RR_COMBO_OPTIONS`, last, so the stored
entries and capture ids of the six others do not move), the Guide button by default (`options_pad`; a preferences file of 1.8.0 has
no such entry and gets Guide), one button or a combination, F2 fixed on the keyboard page; the press that completes it on any pad
sets `menu_request`, and the kit opens or closes the F2 tiles (`rrhk_toggle_settings`), where the Guide button used to open the
options page itself. Its buttons are hidden from the game from that press until all are released (`menu_hold`,
`rrhk_options_hidden` in the kit's pad reading). A capture for Options equal to, inside or around another combination is refused
(and the other way round), as is one overlapping R3 + Select (`RR_CHAT_PAD`, the multiplayer chat's chord). The F2 menu
(`rrhk_menu.c`) gains a last tile, **Quit the game** (`RR_ICON_EXIT`, a new tile icon in `retro_menu.c`), which asks "Quit? No /
Yes" with No selected and comes back to the tiles on No or Esc; the options page loses its last row, Quit the game (D23, 1.7.6),
and `RRHK_KEY_QUIT` goes with it. Past two lines the tiles scroll, two lines at a time. **Texts:** three new entries in the eight
locales ("Press: open the menu", "F2: fixed key", "Kept for the chat (R3 + Select)"); "Options" and "Quit the game" were already
there. **Proof:** offscreen
captures of a fake console on the real shell (two players with a DIP page; one player at 160 x 144, the Game Boy's picture, at the
default scale and at 1x; four players: three lines of tiles), the kit's capabilities self-test (the Quit tile in place of the Quit
row; the graphics and options tiles before it), the players' self-test and the options self-test (Guide by default, a chord taken,
the chat's and Restart's refused, the held buttons hidden). **Stamps:** no game stamp moves; the host stamp of the 21
profiles moves (compared with `main` 36abf44b): every export is upgraded once (rebuilt), none converted again. **Existing
exports:** unchanged until that upgrade; an older preferences file keeps every binding and gets Guide for Options.

## Exports of 1.7.9 in 1.8.0

1.8.0 is the release after 1.7.9. One line per change, with the stamps it moves.

| Change | Game stamps that move | Host and build stamps | Quick states |
| --- | --- | --- | --- |
| [A build folder from another source directory is discarded](#a-build-folder-from-another-source-directory-is-discarded) | none | **the build stamp of every profile** (`retrorecomp/toolchain.py`) | unchanged |
| [The converter: a Front-end mode](#the-converter-a-front-end-mode) | none | **the host stamp of every profile** (`native/player_gamepad.c`) | unchanged |

## A build folder from another source directory is discarded

`toolchain.reset_incompatible_cache` (run before every CMake configure) also deletes a build folder whose `CMakeCache.txt` names another
source directory than the `-S` it is given. A packaged converter's sources live in a temporary folder that changes at each launch, so a
machine build left unfinished by a closed window was refused by CMake at every later launch (16 November 2026, Arthur's 1869 on the
Amiga 1200). **Stamps:** the build stamp of every profile (`toolchain.py` is the build input): every export is upgraded once (recompiled
and checked on its quick routes), none converted again.

## The converter: a Front-end mode

`retrorecomp/gui_front_end.py`, `front_end.py` and `front_end_view.py` (new interface modules): a wall of box art over the Compiled
Games inventory, with its own small file `datas/front-end.json` (schema 1: the console shown, the order, the covers per row of each
console or of the favourites and the search, and when each game was last played, by console and ROM identity; never a path or a
title). Two window preferences, `start_front_end` and `start_front_end_fullscreen` (`INTERFACE_PREFERENCES`). `game_details.Cards`
gains `cached_cover` (only the saved cover: the front-end never reads an executable), and `Cards.cover` keeps the same result. The
converter's controller bridge `native/player_gamepad.c` reports L2 and R2 as bits 29 and 30 of the button mask (the 12 values of a
poll keep their layout, so Compiled Games' navigation reads them unchanged); its build (`tools/build_player_gamepad.py`,
`tools/player_gamepad/CMakeLists.txt`) now links the games' llvm-mingw SDL2 on Windows. **Stamps:** no game stamp moves; the host
stamp of every profile moves (`native/player_gamepad.c` is a host input of every profile, though no game links it), in the same release
whose build stamp already moves for every profile: every export is upgraded once, none converted again (game, host and build stamps
of the 21 profiles compared with `main` d87cd720). **Existing exports:** unchanged until that upgrade.

## Exports of 1.7.8 in 1.7.9

1.7.9 is the release after 1.7.8. This section is the index of its changes, one line per section below, with the stamps that section says move, computed for its own change on the tree of its branch.

| Change | Game stamps that move | Host and build stamps | Quick states |
| --- | --- | --- | --- |
| [Commodore Amiga 500 and 1200: play travels, the Amiga 1200 shares](#commodore-amiga-500-and-1200-play-travels-the-amiga-1200-shares-179) | **the Amiga and the Amiga 1200** (`amiga_conversion.py`, `amiga_knowledge.py`, `systems/amiga.py`, the new `a1200_knowledge.py`) | none | the Amiga and Amiga 1200 keys move (every input); the others are unchanged |
| [Mega Drive: shadow and highlight follow the chip](#mega-drive-shadow-and-highlight-follow-the-chip-179) | **the Mega Drive** (`megadrive_video.py`, `md_vdp_pixels.inc`) | none | the Mega Drive key moves (`md_vdp_pixels.inc`; older Mega Drive states refused cleanly, no compatibility key); the others are unchanged |
| [NES: a PAL NES 2.0 header is accepted](#nes-a-pal-nes-20-header-is-accepted-179) | **the Nintendo NES** (`nes_codegen.py`, `nes_machine.py`) | none | the key of a build made from LF files (every published release) does not move; a source checkout with CRLF files now gives that same key (it moved once, see the section) |
| [The converter: a welcome in the log panel and the developer's message](#the-converter-a-welcome-in-the-log-panel-and-the-developers-message-179) | none | none (window modules only) | unchanged |
| Time estimates in the window (RELEASE_NOTES 1.7.9) | none | none (window modules and `assets/conversion-times.json`, interface only) | unchanged |

## Commodore Amiga 500 and 1200: play travels, the Amiga 1200 shares (1.7.9)

On the owner's word of 16 November 2026 (« Je préfère que tu mettes en place directement le partage de chemin pour l'Amiga 500 et 1200. »; [COMPILATION_LIBRARY.md](COMPILATION_LIBRARY.md#commodore-amiga-1200-joins-the-base-and-play-travels-179-16-november-2026)).

- **What changes:** a conversion that passed puts into its shared record, beside its routes' instructions, the first instruction of each window of the player's F12 record that it made native, when it sits in the install (`amiga_conversion.promoted_record`; the report's `knowledge.promotion.play` counts it). The Amiga 1200 joins the experimental tier of the base (`SharedKnowledge`, module `retrorecomp/a1200_knowledge.py`, out of `DECLINED['path_sharing']`), and its record counts its Kickstart 3.x as 512 KiB at $F80000 (before, every Kickstart instruction of an A1200 stayed private); received Kickstart rows are split at the model's own window. The game itself, its routes and its checks are unchanged.
- **Stamps:** the game stamps of the Amiga 500 and of the Amiga 1200 (both convert through `amiga_conversion.py` and `amiga_knowledge.py`, and `systems/amiga.py` holds both profiles); `path_profiles.py` is not edited, so no other machine moves. No host or build stamp moves. An export of 1.7.8 is converted again in full on either machine; the player's own record of an install (`paths-record.json`) is read as before and gains rows.
- **A replay stopped from outside says so** (both Amigas): a player run that ends with an error code and no message of its own (on Windows, a process ended from the Task Manager or a converter closed) is reported with the frame it reached and as stopped from outside, not by the game (`amiga_conversion.replay_failure`; 1869, 16 November 2026).
- **Site:** the `a1200` limits must be on retro-recomp.com before the release, or an upload holding an A1200 game is refused whole.

## Mega Drive: shadow and highlight follow the chip (1.7.9)

From a player's report of 9 November 2026 (Puyo Puyo Tsuu, converted with 1.7.1: « the puyos are dark except when at the bottom or above another puyo »).

- **What changes:** in shadow/highlight mode, the pinned VDP shaded a pixel unless an opaque high-priority layer covered it. On the chip, a plane tile's priority bit lifts the shadow even where its pixel is transparent. The other three rules of the chip, also absent from the pinned VDP: an operator sprite pixel (palette 3, colour 14 or 15) is a sprite pixel that wins over later sprites and collides; a low-priority operator does nothing over an opaque high-priority plane pixel; sprite colours $0E, $1E and $2E are always at normal intensity. Outside shadow/highlight mode the picture is unchanged (operators exist only in that mode). The private VDP copy carries the rules, scalar and SSE2 (`megadrive_video.SHADE_NEW`, `native/md_vdp_pixels.inc`).
- **Checked:** `tools/megadrive_shadow_selftest.py` replays an authored grid of 256 cases (planes absent, transparent high, opaque low, opaque high, crossed with colours, colour 14 of each palette, operators of either priority, operators over and under another sprite) on the VDP as a game builds it, three ways (batched SSE2, batched scalar, unbatched scalar): all 256 match the rules; on the 1.7.8 VDP, 112 do not. The same grid as a small authored 68000 program, run in MAME 0.289 (`--rom`), gives the 256 values of the rules (MAME's 315-5313 and Genesis Plus GX agree on them). `megadrive_vdp_batch_selftest.py` (random lines, shadow/highlight on half of them) keeps scalar, batched and SSE2 equal. **Not checked:** Puyo Puyo Tsuu itself (no dump here); no game was played.
- **Stamps:** the Mega Drive game stamp (`3fd2b602140a` to `2b841c000d84`); no host or build stamp, no other machine. An export of 1.7.8 is converted again in full. The Mega Drive quick-state key moves because `md_vdp_pixels.inc` is one of its files; the state layout does not change, but no compatibility key is added: a quick state made before 1.7.9 is refused cleanly by the reconverted game. Cartridge saves are not touched.

## NES: a PAL NES 2.0 header is accepted (1.7.9)

Three players' reports (1.6.6 and 1.7.4: Super Mario Bros. 3, Mega Man 2 and Chip 'n Dale, European dumps) ended pass 1 with `[cyc] unsupported cartridge metadata for mapper 4 submapper 0` (mapper 1 for the others). The pinned `nes_cart_variant_supported` (nesrecomp `1b0c621`) refuses every NES 2.0 header whose timing field is not 0 (NTSC) or 2 (multi-region), so **every NES 2.0 dump that declares PAL (1) failed**, in the compiler and again in the runtime check. The converter models PAL itself (`RR_NES_PAL`); the refusal was a leftover of an engine that did not.

- **What changes:** the staged copy of `common/nes_cart.h` (the compiler's and the machine's) refuses only Dendy (3), as the engine's later revisions do (`nes_codegen.patched_cart_header`, a fail-closed replacement: it stops if the pinned line changes). The pin does not move. Dendy stays refused, with the converter's existing message.
- **Reproduced** with Super Mario Bros. 3 (USA) from the maintainer's library with its header rewritten in a scratch folder as NES 2.0 with timing 1 (PAL): the compiler of 1.7.8 stops with the message above; the corrected one generates the sources (tests: the four timings through the real compiler; the refusal is the only text that changes). The library holds no NES 2.0 dump of its own: the three reports are the only real ones.
- **Stamps:** the NES game stamp (`nes_codegen.py` and `nes_machine.py` are inputs). No host or build stamp moves. **Quick states:** the PAL header patch does not move `RR_NES_STATE_ABI` (the header is hashed as the engine wrote it; no saved structure changes; a test pins this). See the next point for the key. **Existing exports:** an NTSC or iNES export is converted again at its next conversion with identical code; nothing played changes.
- **The state key no longer depends on line ends** (16 November 2026, with Arthur's word). `prepare_machine` hashed eight native files (`retro_nes.h`, `nes_machine_state.inc`, `nes_mapper_state.inc`, `nes_state.c`, `nes_ppu_fast.inc`, `nes_ppu_lazy.inc`, `nes_sprite_extra.inc`, `nes_sprite_shift.h`) and appended `nes_ram.inc` to the staged mapper source as raw bytes, while the engine's own files were already hashed with `\r\n` read as `\n`. A source checkout with CRLF files (Windows with `autocrlf`) therefore gave another `RR_NES_STATE_ABI` than an LF one on the same commit (`3d647ca1…` against `e8c2939c…`). The files in question were stale CRLF copies in the maintainer's main checkout (checked out before the `eol=lf` rules; the index holds LF); they were rewritten from the index and `tests/test_stamp_inputs.py` now refuses a CRLF stamp input, and this normalisation stays as a second guard. Now the key names the text. **What moves:** only the key of a CRLF source checkout, once: quick states written by an export converted from such a tree are refused cleanly, like at any key change. **What does not:** a build made from LF files, which is what every published release bundles (the canonical source audit of 1.7.8 lists `native/nes_state.c` at 4,065 bytes, the LF size), keeps its key; so do the states of its games. A test builds the machine from an LF and a CRLF copy of the native files and requires one key; it fails when the normalisation is removed.
- **Not covered:** Dendy dumps (no Dendy timing in the converter); NES 2.0 variants the engine lists as unsupported for other reasons (the check names them the same way).

## The converter: a welcome in the log panel and the developer's message (1.7.9)

`retrorecomp/gui_welcome.py` and `retrorecomp/announcement.py`: the log panel shows an English ASCII welcome until a real line
is written, then the site's message to every player (`GET /api/v1/announcement`, `{"active", "message", "updated_utc"}`, read
at start while the start-up check is on), or « Not connected to the Internet. » when the site cannot be reached. Two new
interface modules and one changed hint in the eight languages (`assets/locales/` is outside the stamps); the window's single
side margin (`gui_common.EDGE`, 12 px, with the status bar's marks in the corners), the Knowledge button's picture
(`gui_drawing.py`) and the leaderboard's crown room (`gui_leaderboard.py`) are window code too.
**Stamps:** none (game, host and build stamps of the 21 profiles checked identical to `main`). **Existing exports:** unchanged.

## Exports of 1.7.7 in 1.7.8

1.7.8 is the release after 1.7.7. This section is the index of its changes, one line per section below, with the stamps that section says move, computed for its own change on the tree of its branch.

| Change | Game stamps that move | Host and build stamps | Quick states |
| --- | --- | --- | --- |
| [Commodore Amiga 1200: supported](#commodore-amiga-1200-supported-178) | **the Amiga and the Amiga 1200** (`retrorecomp/systems/amiga.py`) | none | refused (every build's are) |
| [Builds: the converter's own tools only, Release everywhere](#builds-the-converters-own-tools-only-release-everywhere-178) | **the Atari ST, the Game Boy Advance and the Nintendo 64** (`atarist_conversion.py`, `gba_build.py`, `gba_player.py`, `n64_conversion.py`) | **the build stamp of every profile** (`retrorecomp/toolchain.py`) | the Amiga, Atari ST and Nintendo 64 keys move (every input); the others are unchanged |
| [The converter: a window for missing box art](#the-converter-a-window-for-missing-box-art-178) | none | none (window modules only) | unchanged |
| [Find firmware in a folder: short paths](#find-firmware-in-a-folder-short-paths-178) | none | none (window module only) | unchanged |

## Commodore Amiga 1200: supported (1.7.8)

The Amiga 1200 leaves the experimental status on the owner's play test of eight installs, 16 November 2026 (G14; [AMIGA.md](AMIGA.md#leaving-the-experimental-status-16-november-2026)).

- **What changes:** the profile's status is `supported`, its Linux witness is declared (`linux = 'witnessed'`), its paths stay out of the sharing for now (`DECLINED['path_sharing']`, the owner's word, pending a measure); the Options note loses "experimental" (English and French; the six other languages never said it); the README marks it as running on an emulator core, as the Amiga 500. The machine, its conversion and the game are unchanged.
- **Stamps:** the game stamp of the Amiga 1200 **and of the Amiga 500**: `retrorecomp/systems/amiga.py` holds both profiles and is a game input of both, hashed as a whole, so the status line moves both. No host or build stamp moves (the interface strings are not stamp inputs). An export of 1.7.7 is converted again in full on either machine.

## Builds: the converter's own tools only, Release everywhere (1.7.8)

GitHub issue 1 (16 November 2026): a player with Visual Studio installed and without the portable tools had every Game Boy Advance
conversion stop with « The Game Boy Advance recompiler was not built ». The converter had picked Visual Studio by itself; its
multi-configuration build made a Debug program in `Debug/` while `platforms.build_executable` looks in `Release/`.

- **What changes:** `toolchain.select()` returns the portable tools, or Visual Studio only when `RETRO_RECOMP_TOOLCHAIN=msvc` asks for
  it; an installed Visual Studio is never picked by itself, so the window offers the download instead (the owner's rule: nobody needs
  Visual Studio). The failed-download message no longer suggests installing Visual Studio (its string is gone in the eight
  languages). The Game Boy Advance (recompiler, probe host, player), the Atari ST and the Nintendo 64 pass `--config Release` like
  every other machine; `tests/test_build_config.py` scans every `cmake --build` of the converter. The CI's Windows runner asks for
  Visual Studio by name.
- **Stamps:** the game stamps of the Atari ST, the Game Boy Advance and the Nintendo 64 (their build modules); the build stamp of
  every profile (`toolchain.py`). With the portable tools the programs built are the same: the option is ignored by Ninja.
- **Existing exports:** Atari ST, Game Boy Advance and Nintendo 64 exports are converted again once (the owner's word: « c'est pas
  grave si ça doit être reconverti »); every other export is upgraded (recompiled, checked again on its quick routes).

## The converter: a window for missing box art (1.7.8)

`retrorecomp/gui_covers.py`: with the option on (a window preference, on by default), a queue game that ends without box art joins
one window where the player drops or chooses an image; it becomes the game card's cover and reaches the export through the Compiled
Games reconversion, whose game part is unchanged, so only the shell is rebuilt. The queue's « Choose box art… » and the Compiled
Games card and right-click open the same window. **Stamps:** none (window modules). **Existing exports:** unchanged.

## Find firmware in a folder: short paths (1.7.8)

The already-set comparison resolves both paths, so a value in its Windows 8.3 form (`PROGRA~1`) is the same file. **Stamps:** none.

## Exports of 1.7.6 in 1.7.7

1.7.7 is the release after 1.7.6 (in preparation). This section is the index of its changes, one line per section below, with the stamps that section says move, computed for its own change on the tree of its branch.

| Change | Game stamps that move | Host and build stamps | Quick states |
| --- | --- | --- | --- |
| [Every machine: no crash when a machine has no picture yet](#every-machine-no-crash-when-a-machine-has-no-picture-yet-177) | none | **the host stamp of all 21 profiles** (`rrhk_video.c`, `hostkit/hostkit.h`) | the Amiga, Atari ST and Nintendo 64 keys move (every input, the host's included); the others do not |
| [Every machine: Sync to display (Auto / Locked / Free / Variable refresh)](#every-machine-sync-to-display-auto--locked--free--variable-refresh-177) | none | **the host stamp of all 21 profiles** (the shell, `hostkit/hostkit.h`, `audio_cushion.h`, `audio_output.inc`, `retro_menu.c` and `.h`, `runtime_catalog.inc`, the locale files, `rrhk_sms.c`, `rrhk_msx.inc`) | the Amiga, Atari ST and Nintendo 64 keys move (every input, the host's included); the others do not |
| [Mega Drive: its sound follows a game locked to the display](#mega-drive-its-sound-follows-a-game-locked-to-the-display-177) | none | the Mega Drive's host stamp (`retrorecomp/megadrive_audio.py`, `hostkit/adapters/rrhk_md.c`) | none |
| [Commodore Amiga: an AGA dual playfield with a priority above 4 is drawn](#commodore-amiga-an-aga-dual-playfield-with-a-priority-above-4-is-drawn-177) | the Amiga and the Amiga 1200 | none | refused (every build's are) |
| [Commodore Amiga: the weave of interlaced screens follows the motion](#commodore-amiga-the-weave-of-interlaced-screens-follows-the-motion-177) | the Amiga and the Amiga 1200 | none | `RRAMIGA-STATE-7` (refused) |
| [Commodore Amiga: a LoadSeg list keeps the sizes AmigaDOS stores](#commodore-amiga-a-loadseg-list-keeps-the-sizes-amigados-stores-177) | the Amiga and the Amiga 1200 (`rr_resload.c`) | none | refused (every build's are) |
| [Commodore Amiga 1200: the display's speed shortcuts under AGA](#commodore-amiga-1200-the-displays-speed-shortcuts-under-aga-177) | the Amiga and the Amiga 1200 (the adaptation's digest) | none | refused (every build's are) |
| [Sony PlayStation: anti-aliasing and texture filtering](#sony-playstation-anti-aliasing-and-texture-filtering-177) | the PlayStation's (`psx_main.c`, `psx_session.c`: a session opened again keeps its options) | the PlayStation's host stamp (`rrhk_psx.c`) and the host stamp of every profile (`runtime_catalog.inc`, the locales: five new strings) | none |
| [Sony PlayStation: geometry precision (PGXP)](#sony-playstation-geometry-precision-pgxp-177) | none | the PlayStation's host stamp (`rrhk_psx.c`) and the host stamp of every profile (`runtime_catalog.inc`, the locales: two new strings) | none |
| [Sony PlayStation: the graphics card draws the picture](#sony-playstation-the-graphics-card-draws-the-picture-177) | the PlayStation (`psx_main.c`, `psx_session.h`, `psx_build.py`, the shared Vulkan side compiled in) and the Nintendo 64 (the shared Vulkan side gains its closing functions) | the PlayStation's (`psx_session.c`, `rrhk_psx.c`), and the host stamp of all 20 profiles (`runtime_catalog.inc` and the locales: five new strings) | none (a state loads with either renderer) |
| [Sony PlayStation: the trace records the VRAM (format 2)](#sony-playstation-the-trace-records-the-vram-format-2-177) | the PlayStation (`psx_session.c`, `psx_session.h`, `psx_main.c`, `psx_conversion.py`) | the PlayStation's host stamp (`psx_session.c`) | none |
| [Nintendo 64 and PlayStation: one Vulkan frontend](#nintendo-64-and-playstation-one-vulkan-frontend-177) | the Nintendo 64 (`n64_session.cpp`, `CMakeLists.txt`, the new `native/libretro_vulkan_host.c` and `.h`), the PlayStation (the same two files, not yet compiled into its games) | none | **Nintendo 64 states of 1.7.6 are refused** (the state key hashes the session and the shared files) |
| [Sony PlayStation: the Vulkan renderer compiled in, not yet used](#sony-playstation-the-vulkan-renderer-compiled-in-not-yet-used-177) | the PlayStation (the prepared Beetle tree: its sources, defines, include folders and the Vulkan headers) | the PlayStation's host stamp (`psx_session.c`) | PlayStation states of 1.7.6 refused (another build: the state key holds the prepared tree's digest) |
| [Commodore Amiga: the Kickstart a slave's code asks for](#commodore-amiga-the-kickstart-a-slaves-code-asks-for-177) | the Amiga and the Amiga 1200 (`amiga_kickstart.py`) | none | none |
| [Commodore Amiga: resload_Decrunch unpacks the Imploder](#commodore-amiga-resload_decrunch-unpacks-the-imploder-177) | the Amiga and the Amiga 1200 (`rr_decrunch.c`, `rr_decrunch.h`) | none | refused (every build's are) |
| [Commodore Amiga 1200: a player's record walked with the 68EC020's lengths](#commodore-amiga-1200-a-players-record-walked-with-the-68ec020s-lengths-177) | the Amiga, the Amiga 1200 and the Atari ST (`amiga_conversion.py`, `m68k_record_walk.py`) | none | none |
| « Find firmware in a folder… » in Options › Consoles ([INSTALLING.md](INSTALLING.md#finding-firmware-in-a-folder); no section of this page; merge `246103b7`) | none | none (`firmware_search.py` and `gui_firmware.py` are interface modules, outside the stamps) | none |
| The converter's console menu: short labels, a field and a list as wide as their longest entry (no section of this page; merge `b318698e`) | none | none (`console_menu.py` is an interface module, outside the stamps) | none |
| The Amiga 1200's 68EC020 against an independent model (G10, [QUALIFICATION.md](QUALIFICATION.md#commodore-amiga-1200-evidence-behind-its-column-15-november-2026); no section of this page; commit `1f9c582a`) | none | none (`m68020_vector_checks.cpp` is a check, outside the stamps) | none |
| [Commodore Amiga: no battery clock](#commodore-amiga-no-battery-clock-177) | the Amiga and the Amiga 1200 (`amiga_session.cpp`) | none | refused (every build's are) |

## Every machine: Sync to display (Auto / Locked / Free / Variable refresh) (1.7.7)

On the owner's question of 15 November 2026 about vsync (« j'ai un petit écran 4:3 qui est en 60 Hz, et j'ai l'impression que
c'est plus visible là »), his go (« Oui, lance-le », then « Version complète »), FreeSync on his 144 Hz screen and « faut que ça
soit géré pour Linux aussi ». The study is `vsync-study-177` (private notes).

* **What changes for players.** The options page has a new row, **Sync to display**, kept per machine
  (`[<Console>.Video] sync`), default **Auto**: a game whose rate is within 1 % of the screen's measured refresh is locked to
  it (each frame shown for exactly one refresh, no more hitch every few seconds), running at the screen's rate (60.00 Hz
  instead of 59.92, +0.13 %) with its sound resampled by the same fraction; otherwise it runs as in 1.7.6. **Locked** goes up
  to 3 %, **Free** is the game's own clock with vsync off (on Linux too, where 1.7.6 always asked vsync), **Variable
  refresh** is for FreeSync / G-Sync / HDMI VRR screens (on Windows the Direct3D 12 renderer, from the next start). See
  [CONTROLS.md](CONTROLS.md#sync-to-display-177) and [HOST_KIT.md](HOST_KIT.md#d30) (D30).
* **What it is not.** No latency figure: the lock aligns frames to the refresh and adds no wait over Windows' composed present;
  physical latency stays unmeasured. Variable refresh cannot be detected (DXGI reports tearing support, not FreeSync): the
  player chooses it.
* **Never locked**: the conversion's hidden-window checks (their runs and stamps are unchanged), `SDL_RENDER_VSYNC` set, the
  menus, pause, fast forward and other speeds. An own-audio machine without the `audio_ratio` hook stays free and says so.
* **Stamps.** The host stamp of all 21 profiles moves; no game or build stamp. The quick-state keys of the Nintendo 64, the
  Amiga and the Atari ST move (they hash every input); the Mega Drive and Super Nintendo keys hash no host file and do not.
* **Checks.** `tools/hostkit_capabilities_selftest.py` run 15: Auto and Locked's decision for given rates (60 Hz with 59.92,
  60.10 and 59.73 Hz; the Neo Geo's 59.19 Hz beyond Auto and within Locked; PAL on 60 Hz and 144 Hz screens never locked),
  the sound factor's bounds, a ten-minute closed loop (also with the refresh measured 0.1 % off), then the real loop with a
  stand-in refresh: the row's four values and their preference, locked in play only (free in a menu and at max speed), the
  notice. `tools/audio_selftest.py`: the Master System / MSX converter locked for a simulated minute, nothing trimmed and no
  underrun, against a control without the factor that trims. Both also pass on Linux (Debian, headless). An offscreen gallery
  (hidden window) shows the four filters and the menus identical pixel for pixel on Direct3D 11 and Direct3D 12. Not
  checkable without a screen: the smoothness itself, judged by the owner on his 60 Hz and 144 Hz screens.

## Mega Drive: its sound follows a game locked to the display (1.7.7)

With « Sync to display » ([HOST_KIT.md](HOST_KIT.md), decision D30), a game Locked to the screen runs at the screen's rate (Sonic 2 at
60.00 Hz instead of 59.92, +0.13 %): the machine makes its sound that much faster while the device still plays it at its own rate. The kit
tells the machine the factor (`RrhkMachine.audio_ratio`, base = machine Hz / refresh Hz, exactly 1.0 when not locked, in menus, pause,
fast forward or a speed other than 100 %); the Mega Drive adapter hands it to the engine's bridge (`rr_md_audio_base`, written by
`retrorecomp/megadrive_audio.py`), which uses it as a feed-forward on its resampling step: each output frame consumes 1/base source
frames. The bridge's own fill controller (the pinned one: P on the fill error, low-pass, slew, +/-0.5 %) keeps correcting the rest, so the
kit's `rr_drc_ratio` is not stacked on it. The value is set from the producer side under the device lock, nothing is allocated in the
callback, a device opened again keeps it, and at 1.0 the pinned step runs alone.

- **Checked** (`tools/megadrive_audio_bridge_selftest.py` and its new `native/md_audio_locked_checks.c`, a development check outside the stamps, portable toolchain): at 1.0 the PCM and loop choices equal the pinned bridge's,
  hashes unchanged (`c4a3f668...`, steady `e467be96...`); a locked mode runs 300 simulated seconds: with the feed-forward the fill stays at
  25.93 ms for base 0.99871 and 1.003, as at 1.0 (the controller alone would hold it 0.7 ms high or 4.7 ms low), with no stretch, underrun or
  overflow. Sonic 2 converted on this tree: its routes run no interpreter and match the reference, the compressed copy too.
- **Not checked here:** a real locked run needs a window on a real screen (the kit's test runs and the dummy video driver do not lock); it
  is Arthur's eyes test on Sonic 2, where `md_audio_stretch_events` of the timing report and the stderr line « sync to display: ... locked »
  say whether it held. Physical latency stays unmeasured.
- **Stamps:** the Mega Drive's host stamp only (`megadrive_audio.py`, a host module, and `hostkit/adapters/rrhk_md.c`); no game stamp,
  nothing a game runs changes; no quick-state key moves (the locked check is a new file outside the stamps, so the key, which hashes the
  game-role native files, is not touched).

## Every machine: no crash when a machine has no picture yet (1.7.7)

Found by the PlayStation specialist on 15 November 2026: switching the PlayStation's renderer in F3 reopened its session, which
had no picture until its next frame, and the menu holds the machine; with the xBR or Scale2x filter the game closed (access
violation), because both read the picture themselves. Sharp pixels and scanlines survived (SDL refuses a NULL upload).

* **The kit** (`rrhk_video.c`, [HOST_KIT.md](HOST_KIT.md), Pictures): when `pixels()` returns NULL or the visible size is 0 x 0,
  the game's area is black under every filter and nothing is read; the picture comes back with the machine's next one. Any machine whose picture is missing
  for a moment (a session reopened, a Restart under a menu) is covered; the PlayStation's session also never returns NULL now
  (its own branch).
* **Stamps.** The host stamp of all 21 profiles moves (`rrhk_video.c`, `hostkit/hostkit.h`, a comment). No game or build
  stamp. The quick-state keys of the Nintendo 64, the Amiga and the Atari ST move (they hash every input); no other.
* **Checks.** `tools/hostkit_capabilities_selftest.py`, run 14: a machine with no picture (NULL, then 0 x 0) under each of the four
  filters, on a console (F3 cycles) and on the machine whose picture grows (the F3 page): a black game area, no crash, then the picture
  again. Without the change the same run ends in an access violation (exit 0xC0000005).

## Commodore Amiga: an AGA dual playfield with a priority above 4 is drawn (1.7.7)

In dual-playfield mode, OCS and ECS Denise draw a playfield transparent when its priority in `BPLCON2` is above 4. vAmiga applied
that on every chipset; AGA's Lisa draws the playfield. An Amiga 1200 game that writes 7 to both priorities (Pinball Illusions'
title, `BPLCON2` `$003F`, eight planes) showed colour 0 on every pixel: a black screen with the music playing. The adapted Core now
keeps the rule for OCS and ECS only; where the playfield stands among the sprites is unchanged.

- **What changes:** the picture of an AGA dual-playfield line whose priority is above 4, nothing else. On Pinball Illusions, 5,600
  frames before and after: sound, memory and CPU equal on every frame, pictures different from the title's first frame on. The Amiga
  500 is not concerned (the rule stays as it was for OCS and ECS).
- **Where:** a new module, `retrorecomp/amiga_vamiga_display.py`, holds the picture-only changes to the adapted vAmiga Core. It is
  not one of the generator's sources (`amiga_knowledge.GENERATOR_SOURCES`): a change that only decides a pixel's colour cannot be
  noticed by a path, so `GENERATOR_REVISION` stays 2 and the qualified paths stay qualified. `tests/test_amiga_vamiga_display.py`
  limits the module to the listed functions of Denise. `amiga_vamiga.py` is unchanged.
- **Stamps:** the game stamp of the Amiga and of the Amiga 1200 (the new module, and the adaptation's digest in the build's
  identity). Their exports of 1.7.6 are converted again in full on the first batch; no other machine moves. Quick states of an
  earlier build are refused, as every build's are.
- **Upstream:** a gap of vAmiga `f51a6bf` (`Denise::translateDPF`), offered as dirkwhoffmann/vAmiga#1039; kept as our patch until
  it is merged and the pin moves ([UPSTREAMS.md](UPSTREAMS.md)).

## Commodore Amiga: the weave of interlaced screens follows the motion (1.7.7)

Since 1.7.6 an interlaced screen (LACE) is shown woven: the long and the short field side by side, twice the lines. The two fields
are 1/50 s apart, so where the screen moves the picture combed (Pinball Illusions' whole-table view, F10, while the table scrolls:
every moving edge doubled). Owner's decision of 15 November 2026, « Oui, lance-le »: no option, for every interlaced screen.

- **What changes:** the session keeps the field of the frame before the held one (the same parity as the coming field). A pixel of
  the held field stays where this frame's field, on the lines just above and below it, equals that older field; where it changed,
  the pixel becomes the mean of those two lines. A still screen is the 1.7.6 weave byte for byte; a moving area shows this frame's
  field at its own rows (no comb, no line jump). Generic: the LACE bit and the long-frame bit only.
- **Measured on the interpreted reference machine, before and after:** Pinball Illusions' table pan in F10 (6,400 frames), pictures
  different on the pan only, comb index of the table 19.3 before, 0.7 after; Banshee's interlaced title, 1 picture of 1,200 different
  (its first interlaced fade-in); Fears, Super Stardust, Slam Tilt, Roadkill and Civilization (Amiga 500) identical, pictures
  included. Sound, memory and CPU equal on every frame of every game. Super Stardust's bonus screen is not reached without play.
- **Quick states:** `RRAMIGA-STATE-7`, the older field after the held one. A state saved in the F10 pan, loaded, gives the continuous
  run's pictures from the fourth frame on (sound, memory and CPU from the first). The first frames after a load differ in one field
  of the table in 1.7.6 already (2 frames, the bitplane state at a save, an open note); the motion test makes it 3.
- **Stamps:** the game stamp of the Amiga and of the Amiga 1200 (`amiga_session.cpp`), with the section above; nothing else moves.

## Sony PlayStation: anti-aliasing and texture filtering (1.7.7)

**What changes.** F3 gains two rows after the internal resolution, for the graphics card only, both Off by default:
« Anti-aliasing (GPU) » (MSAA 2x, 4x, 8x, or Supersampling as on the Nintendo 64: drawn at twice the internal resolution and
reduced by two as the frame is read back, so the picture keeps the size the resolution row gives; nothing at 8x) and
« Texture filtering (GPU) » (bilinear or 3-point). They change in play; with the CPU drawing they do nothing and the game says so once.
No mipmapping is offered (the console has none).

**What it does not change.** With both rows Off (the default) every frame is byte for byte what it was: on Ape Escape, 3,300 frames
on the CPU and on the card, every trace column equal to the build before this change, picture included. With the rows on, the
machine is the same: RAM, CPU state, sound and VRAM equal on every frame (MSAA 8x; Supersampling at 4x; bilinear; 3-point with
MSAA 4x at 4x), at 0 interpreted instructions; only the card's picture differs. Changing them in play (with the resolution, through
Supersampling's change of drawing size) was checked in a window of the real Windows video driver under each filter, on the
card and on the CPU: the game continues. MSAA changed in play opens the session again (a quick state, as a renderer switch does)
with its multisampling set before the renderer is built: the first build of this change rebuilt Beetle's renderer in place, which
kept the programs of the old sample count, and the picture broke at the game's next display mode change (the owner's report of
15 November 2026). A session opened again now starts with the core options it had (`RrPsxGame.options`). The proof compares the
picture as well as the machine: same size as the run without MSAA, content over the whole width.

**Stamps:** the PlayStation's host stamp (`rrhk_psx.c`), its game stamp (`psx_main.c`, `psx_session.c`), and the host stamp of every
profile (`runtime_catalog.inc`, the locales). **Existing exports:** converted again in full at their next conversion. **Quick
states:** unchanged. **Hot path:** with both rows Off, the same.

## Sony PlayStation: geometry precision (PGXP) (1.7.7)

**What changes.** F3 gains two rows after the internal resolution, both **On by default for the player** (the owner's decision of
15 November 2026, after trying them): « Geometry precision (PGXP) » (Beetle's PGXP in its "memory only" mode) and
« Perspective-correct textures » (held off while PGXP is Off: it corrects only what PGXP carries). A choice a player saved is kept.
They change in play, on the card and on the CPU, without reopening the session. Beetle's "memory + CPU" mode, its PGXP culling
and its vertex cache are not offered. **What a player sees by default is not the checked run:** with PGXP on the emulated run
differs slightly (RAM and CPU state on some frames, written on the PlayStation's page), and no fidelity is claimed for it.

**What it does not change.** The conversion's checks run with both rows Off, and there every frame is byte for byte what it was: on Ape Escape, 3,300 frames
on the CPU and on the card, every trace column equal to the build before this change, picture included. The checks of a
conversion run with PGXP off. With PGXP on the run stays at 0 interpreted instructions and differs slightly from the checked one
(RAM and CPU state on some frames: written on the PlayStation's page). Turning it on and off in play was checked headless and in a
window of the real Windows video driver under each filter, the machine held after each change: the game continues.

**Stamps:** the PlayStation's host stamp (`rrhk_psx.c`) and the host stamp of every profile (`runtime_catalog.inc`, the locales).
**Existing exports:** converted again in full at their next conversion. **Quick states:** unchanged (PGXP keeps nothing in a state;
after F9 its precision comes back as the game recomputes its vertices). **Hot path:** with PGXP off, the same; On (the player's
default) adds Beetle's PGXP bookkeeping to the GTE and memory steps (not timed: no timing run for this change).

## Sony PlayStation: the graphics card draws the picture (1.7.7)

**What changes** (the owner's decisions of 15 November 2026: Vulkan, by default, the CPU when no card can be used). A PlayStation
game opens Beetle PSX's Vulkan renderer through the libretro Vulkan side it shares with the Nintendo 64
(`native/libretro_vulkan_host.c`), reads each frame back from the card and shows it. F3 gains a first row, **Renderer**: Graphics
card (Vulkan), the default, or CPU (the software renderer). The software renderer keeps its copy of VRAM at 1x beside the card
(Beetle's "Software Framebuffer", forced on), so a game that reads VRAM back reads the console's. The internal resolution list is
1x, 2x, 4x and 8x (graphics card); 8x asked for on the CPU draws 4x and says so. A computer with no usable card opens on the CPU
and the player is told once ("No usable graphics card: the CPU draws the picture"); `RETRORECOMP_TEST_VULKAN=none|device` makes a
test run behave as such a computer. Changing the renderer in play takes a quick state, opens the session again on the other
renderer and loads it back; the same reopening (and a Restart) now gives every F3 row its value again (before, a Restart left the
core's defaults until the row was touched). A session that has drawn nothing yet gives the window a black picture, and a renderer
switch keeps the last picture until the next frame: the first build of this change closed the game when F3 switched the renderer
under the xBR or Scale2x filter (the owner's report of 15 November 2026), since those filters read the picture while the menu held
the machine. `--gfx-at FRAME:KEY=INDEX` changes a row during a headless run, as on the Nintendo 64.

**What it does not change.** Every check of a conversion: a headless run draws with the CPU at 1x unless `--gfx renderer=0` asks
for the card. Checked on Ape Escape (3,300 frames, a build of this tree): with the card at 1x and at 8x, the RAM, the CPU state, the
sound and the VRAM equal the CPU renderer's on every frame; both fallbacks (no loader, a device refused) run exactly as the CPU
renderer, picture included; a quick state saved on one renderer and loaded on the other continues for 600 frames equal to the
uninterrupted run.

**Stamps:** the PlayStation's game stamp (`psx_main.c`, `psx_session.h`, `psx_build.py`; the shared Vulkan side, declared for both
machines) and host stamp (`psx_session.c`, `rrhk_psx.c`); the Nintendo 64's game stamp (the shared side's two closing functions,
which the Nintendo 64 never calls); the host stamp of every profile (`runtime_catalog.inc`, the locales). **Existing exports:**
converted again in full at their next conversion. **Quick states:** none moves by this change; a state loads with either renderer.
**Hot path:** the card's frame is read back each frame (the Nintendo 64's way); the CPU renderer's path is unchanged.

**The device chosen** (the same release). Without a discrete GPU the shared Vulkan side now takes the best other device (an
integrated GPU, then a virtual one, then any other, a device emulated on the CPU last) instead of the first one listed; on a
computer with a discrete GPU the choice is unchanged (the Nintendo 64's included). The PlayStation refuses a device emulated on
the CPU (Mesa's llvmpipe, which WSL offers): its own CPU renderer is better than an emulated card, so it falls back with the
notice. The Nintendo 64, which needs Vulkan, still uses such a device when it is the only one.

## Sony PlayStation: the trace records the VRAM (format 2) (1.7.7)

**What changes.** The per-frame trace a PlayStation game writes for its checks (`--trace`) gains a ninth column, `vram`: the hash
of the core's VRAM, the 1 MiB the console drew into (larger when the software renderer draws at a raised resolution). With the
Vulkan renderer the picture a game shows is the graphics card's own and is never compared; the VRAM, kept by the software
renderer's copy at 1x, is what a check compares instead (on Ape Escape it is equal to the software renderer's on every frame,
with RAM, CPU state and sound). The trace has a format, named by its header line (`psx_conversion.TRACE_FORMATS`): format 1 is
the eight columns of 1.7.1 to 1.7.6, format 2 the nine of 1.7.7. Both are read; a trace of no known format is refused with a
sentence, and two traces of different formats are never compared (one of them comes from another build).

**Existing reports and qualified evidence.** A conversion report carries no trace, only what the routes showed (liveness fields):
reports of 1.7.6 are unchanged and still read. The traces kept as evidence of the 1.7.6 qualification are format 1 and stay
readable; they are never compared with a 1.7.7 trace (a comparison across builds was never a proof). The conversion compares
traces of one build only, so nothing it checks changes.

**Stamps:** the PlayStation's game stamp (`psx_main.c`, `psx_session.h`, `psx_conversion.py`) and host stamp (`psx_session.c`).
**Existing exports:** converted again in full at their next conversion. **Quick states:** unchanged by this change. **Hot path:**
no (the VRAM is hashed in the checks' headless runs only).

## Nintendo 64 and PlayStation: one Vulkan frontend (1.7.7)

**What changes.** The Vulkan side of the Nintendo 64's libretro frontend (the instance, the device the core creates through its
negotiation, the libretro Vulkan interface given to the core, the read-back of each frame into the picture) moves out of
`native/n64_machine/n64_session.cpp` into `native/libretro_vulkan_host.c`, so that the PlayStation's Vulkan renderer uses the same
code rather than a copy. The calls are the same, in the same order: the functions come from the same loader (the Nintendo 64 still
initialises volk and loads its tables at the same two points, through two hooks), the queue is behind one lock (an SDL mutex in
place of a C++ one), and the error messages are unchanged.

**What it does not change.** The Nintendo 64's pictures, sound, memory and CPU state: the gate is the Nintendo 64 specialist's
(three games, the same exes built from both trees at one folder path, every trace column, the captures and RDRAM byte-equal on the
main route and on the graphics paths the read-back touches; quick states equal apart from their key).

**Stamps:** the Nintendo 64's game stamp (`n64_session.cpp`, `CMakeLists.txt`, the shared files) and the PlayStation's (the shared
files, declared for both). **Existing exports:** converted again in full at their next conversion. **Quick states:** Nintendo 64
states of 1.7.6 are refused cleanly (the state key hashes the session and the shared files). **Hot path:** the read-back of each
frame, the same calls.

## Sony PlayStation: the Vulkan renderer compiled in, not yet used (1.7.7)

**What changes.** Step 1 of the graphics-card renderer ([PLAYSTATION.md](PLAYSTATION.md)): every PlayStation game now holds Beetle
PSX's Vulkan renderer (`rhi/rhi_lib_vulkan.c`, `rhi/rhi_upscaler.c`, MIT, with their prebuilt shaders and the texture tracker
they call), compiled with Beetle's `HAVE_VULKAN` and `HAVE_HW`. It is not opened yet: the session asks for the software renderer,
the reference of every check. What the renderer needs and the game cannot hold is replaced: SPIRV-Cross (Apache-2.0) by our
`native/psx_machine/psx_spirv_reflect.c` (equal on all 92 prebuilt shaders, `tools/psx_spirv_reflect_selftest.py`), the HDR
transform by `native/psx_machine/psx_hdr_none.c` ("off"), Beetle's Apache-2.0 copy of the Vulkan headers by Khronos's own,
pinned and taken under MIT (`psx_beetle.VULKAN_HEADERS_REV`, a new upstream). The game stays GPL-2.0-only as a whole; its notice
gains the renderer's MIT and ISC terms and Khronos's MIT terms. A core built with its hardware renderers names its options
`beetle_psx_hw_<name>`: the session answers them under the names it already used.

**What it does not change.** The picture and every check: the per-frame trace of a game built this way equals the trace of the
software-only build (frame, RAM, picture, sound, CPU state; checked on Ape Escape).

**Stamps:** the PlayStation's game stamp (the prepared tree's sources, defines and include folders, the two new files, the Vulkan
headers) and host stamp (`psx_session.c`). **Existing exports:** converted again in full at their next conversion. **Quick
states:** PlayStation states of 1.7.6 are refused cleanly (the state key holds the prepared tree's digest). **Site limits:**
unchanged. **Hot path:** no (the renderer is not opened; the game is about 5 MB larger).

## Commodore Amiga 1200: a player's record walked with the 68EC020's lengths (1.7.7)

A player's own record (F12, kind 22) is a list of windows of bytes, each noted where an instruction ran on the interpreter; the next
conversion walks each window into instructions (`retrorecomp/m68k_record_walk.py`). The Amiga 1200's walk used the length its opcodes
give alone, the 68000's rule. A 68EC020 instruction with a full extension word is longer than its first word says, so the walk cut it
and took its extension words for instructions of their own. That code is guarded by the opcode the CPU latches, so it never ran wrong,
but it was code that never runs, and what followed it in the window was lost.

- **What changes:** the Amiga 1200's walk reads the extension words (`m68020_lengths.length`, the lengths its sweep and its translator
  already use; `amiga_conversion.walk_record`); a window that cuts an instruction ends the walk there. The Amiga 500's walk is
  `amiga_codegen.walk_records`, unchanged, and the Atari ST's too (`m68k_record_walk.walk_windows` takes an optional length by bytes).
- **Measured on the owner's six Amiga 1200 records of 15 November 2026** (counts only): five of six walked differently; Fears' 4,096
  windows give 382 entries of the old walk the new one does not make (cut instructions and extension words read as code) and 79 it
  adds (the instructions after them).
- **Generator pins:** `amiga_codegen.py` is not edited, so `GENERATOR_REVISION` stays 2 and the Amiga 500's qualified paths stay
  qualified; the Amiga 1200 shares no path.
- **Stamps:** the game stamp of the Amiga, of the Amiga 1200 and of the Atari ST (the shared walk); the output of the Amiga 500 and of the
  Atari ST is unchanged. Their exports are converted again in full on the first batch.

## Commodore Amiga: a LoadSeg list keeps the sizes AmigaDOS stores (1.7.7)

`resload_Relocate` with `WHDLTAG_LOADSEG` lays an executable out as AmigaDOS's LoadSeg does: each segment is its size, the BPTR to the
next, then the hunk. The size was stored padded to the alignment (8 bytes); AmigaDOS stores the hunk's size plus 8, and the alignment
only decides where the next segment goes. `resload_PatchSeg` counts its offsets across the segments with the stored sizes, so each
padded segment moved the patches after it by 4 bytes. Alien Breed 3D's slave patches the game's third segment: its patches landed 8
bytes early, and the game stayed black.

- **What changes:** the stored size only (placement unchanged); `tests/amiga_resload_harness.c` checks the size and a patch past a
  padded segment.
- **Measured:** Alien Breed 3D shows its title with its music. Pinball Illusions, Slam Tilt, Banshee, Fears, Gloom, Zool 2, Roadkill and
  Super Stardust (Amiga 1200), and six Amiga 500 installs (Civilization among them; five of the fourteen call Relocate or PatchSeg):
  identical traces before and after, 2,500 frames each, pictures included.
- **Stamps:** the game stamp of the Amiga and of the Amiga 1200 (`rr_resload.c`); their exports are converted again in full.

## Commodore Amiga: no battery clock (1.7.7)

vAmiga gives every machine an OKI battery clock that reads the host's time. Neither a stock Amiga 500 nor a stock Amiga 1200 has one,
and a clock that follows the host makes two runs of the same game differ as soon as the game or its Kickstart reads it: the reference
run and the native one would disagree for a reason that is not the game's. The session now sets no clock (`Opt::RTC_MODEL` NONE).

- **Measured:** Pinball Illusions (5,000 frames), Slam Tilt, Civilization and Gloom (3,000), Banshee and Fears (2,000), before and after
  on the interpreted reference machine: identical traces, pictures included. None of them reads the clock.
- **Stamps:** the game stamp of the Amiga and of the Amiga 1200 (`amiga_session.cpp`); their exports are converted again in full.

## Commodore Amiga 1200: the display's speed shortcuts under AGA (1.7.7)

Owner's decision of 16 November 2026 (« c'est quelque chose qui est important »). The Amiga 500's display shortcuts, added stage by
stage (one pass for both parities of a line, the bitplane slots of a line in a batch, the quiet line, the idle sprites), were switched
off under AGA: an Amiga 1200 game ran vAmiga's slower path for every line.

- **What changes:** the four are open to AGA. One pass: both parities are prepared first (their state is disjoint). The batch: the
  range it checks is taken for FMODE's widest fetch, and a wide fetch leaves its last word on the data bus, as vAmiga's own path does
  (a read of a write-only register returns it; found by the self-test's AGA scenario 8008). The quiet line: BPLCON4's XOR and
  BPLCON3's playfield 2 offset are in its key. The idle sprites: unchanged rule.
- **Where:** `retrorecomp/amiga_vamiga_display.py`, whose rule widens from picture-only changes to the display pipeline: Denise's
  drawing and the bitplane and sprite slots of Agnus, each replayed against vAmiga's own path by the self-test; never the CPU, the
  memory, the CIAs, Paula, the Copper or the Blitter (`tests/test_amiga_vamiga_display.py`). `amiga_vamiga.py` is not edited:
  `GENERATOR_REVISION` stays 2 and the Amiga 500's qualified paths stay qualified.
- **Proof:** tools/amiga_display_selftest.py passes with 12 AGA scenarios beside the 12 OCS/ECS and 8 super-hires ones (1,568,415 instructions recorded, every record of the batched run equal to vAmiga's per-slot run, 64 of 64 planted faults seen); its AGA scenario 8008 found the data-bus difference above. Real games, reference machine, with and without: Pinball Illusions (6,400 frames, its F10 interlaced table), Slam Tilt, Banshee, Fears, Gloom, Zool 2, Roadkill, Super Stardust and Alien Breed 3D (3,000 frames each), Civilization and an Amiga 500 game (2,500): identical traces, pictures included; on Fears 936,000 of 939,000 lines are batched and 858,003 visible lines take the one-pass loop, against none before.
- **The bus model in shadow** (stage 7) is not compared on AGA scenarios: it holds the OCS/ECS slot table only; the self-test says so
  in its summary.
- **Not measured:** the gain per frame (a timing pass on a quiet PC, with the owner's agreement).
- **Stamps:** the game stamp of the Amiga and of the Amiga 1200 (the adaptation's digest); exports converted again in full.

## Commodore Amiga: the Kickstart a slave's code asks for (1.7.7)

A WHDLoad slave names the Kickstart it needs in its header, or passes it to `resload_LoadKick` in its registers: the size in D0, the
CRC-16 in D1, the name in A0. For the second kind the converter chose an image by version, 1.3 first and 256 KiB only; an Amiga 1200
slave that asks for 3.1 that way (All New World of Lemmings: 512 KiB, `$9FF5`, `40068.a1200`) got a 1.3 image and stopped at its
first frame, the player's 3.1 unused.

- **What changes:** `amiga_kickstart.request_of_slave` reads, in the 24 bytes before each call, `move.l #imm,d0` or `moveq #n,d0`
  with `swap d0` (the size), `move.w #imm,d1` or `move.l #imm,d1` (the CRC-16) and `lea d16(pc),a0` (the name); the request is then
  matched exactly, as a header's. A call it cannot read keeps the old choice. The call still checks the image at run time.
- **Measured:** All New World of Lemmings converts (quick level, every check passed; its 59,006 interpreted instructions are all the
  Kickstart's, 0.12 %); on 250 installs sampled in each NAS folder, 46 of the 47 LoadKick-only slaves are read, and the player's
  Kickstarts match all 46.
- **Stamps:** the game stamp of the Amiga and of the Amiga 1200 (`amiga_kickstart.py`); exports converted again in full.

## Commodore Amiga: resload_Decrunch unpacks the Imploder (1.7.7)

`resload_Decrunch` recognised the File Imploder (`IMP!`, `ATN!`) and refused it by name. Two Amiga 1200 installs of the NAS stopped at
their first frame for it (Alien Breed 2 and Body Blows Galactic, both AGA).

- **What changes:** an Imploder unpacker in `native/amiga_whdload/rr_decrunch.c`, our own C written from the format's description
  (temisu/ancient's, BSD-2, credited with Crunch-Mania): the stream read backward with its first 12 bytes in the trailer, literal
  runs and matches from short prefix codes and the trailer's tables, the closing checksum checked. RNC method 2 and TPWM are still
  refused by name.
- **Measured:** both installs convert (quick level, every check passed, 0 interpreted instructions); the three Imploder files of
  their archives unpack with their checksum; `tests/test_amiga_resload.py` unpacks an authored stream byte for byte and refuses a
  damaged one.
- **Stamps:** the game stamp of the Amiga and of the Amiga 1200; exports converted again in full.

## Exports of 1.7.5 in 1.7.6

1.7.6 is the release after 1.7.5 (in preparation). This section is the index of its changes, one line per section below, with the stamps that section says move, computed for its own change on the tree of its branch.

| Change | Game stamps that move | Host and build stamps | Quick states |
| --- | --- | --- | --- |
| [Game Boy Advance: supported](#game-boy-advance-supported-176) | the Game Boy Advance (`retrorecomp/systems/gba.py`, its status) | none | none |
| [Commodore Amiga 1200: an experimental profile beside the Amiga 500](#commodore-amiga-1200-an-experimental-profile-beside-the-amiga-500-176) | the Amiga, the Atari ST and the X68000 (the shared 68000 path records and their instruction lengths); the new `a1200` | the host stamps of `amiga` and `a1200` (interlaced screens woven) | **every Amiga state is refused** (format `RRAMIGA-STATE-6`) |
| [Commodore Amiga: the CPU's speed, a player's option](#commodore-amiga-the-cpus-speed-a-players-option-176) | the Amiga and the Amiga 1200 (`amiga_session.cpp`, `amiga_player.c`, `amiga_conversion.py`) | the Amiga and the Amiga 1200 (`rrhk_amiga.inc`) | none (`RRAMIGA-STATE-6`; a state of an earlier build is refused, as every build's are) |
| [Path records: one copy for the 68000 computers and the MSX2+](#path-records-one-copy-for-the-68000-computers-and-the-msx2-176) | the X68000, the Amiga and the Atari ST (`retrorecomp/m68k_media_knowledge.py` set on the new `retrorecomp/path_records.py`) | none | none |
| [MSX2+: MSX-MUSIC, the kanji font, shared paths](#msx2-msx-music-the-kanji-font-shared-paths-176) | the MSX, the MSX2 and the MSX2+ (the shared MSX machine files) | the MSX2+ (its option labels) | MSX, MSX2 and MSX2+: refused (layout `msx-state-6`) |
| [MSX2+: supported](#msx2-supported-176) | the MSX2+ (`retrorecomp/systems/msx.py`, its status) | the MSX2+ (its option note) | none |
| [Sony PlayStation: a stick pushed straight left no longer goes right](#sony-playstation-a-stick-pushed-straight-left-no-longer-goes-right-176) | none | the PlayStation's host stamp (`psx_session.c`) | none (the state holds no stick) |
| [Sony PlayStation: the graphics page without deinterlacing and 8x](#sony-playstation-the-graphics-page-without-deinterlacing-and-8x-176) | the PlayStation (`native/hostkit/adapters/rrhk_psx.c`) | none | none |
| [Sony PlayStation: supported](#sony-playstation-supported-176) | the PlayStation (`retrorecomp/systems/psx.py`, its status) | none | none |
| [Sony PlayStation: shared paths](#sony-playstation-shared-paths-176) | the PlayStation | none | none |
| [Sony PlayStation: the CPU state is compared, every interpreted instruction is listed, the GTE's quick state is fixed, the memory card is set aside when unusable](#sony-playstation-the-cpu-state-is-compared-every-interpreted-instruction-is-listed-the-gtes-quick-state-is-fixed-the-memory-card-is-set-aside-when-unusable-176) | the PlayStation | the PlayStation's host stamp | PlayStation states of 1.7.5 refused (another build) |
| [Every machine: a 16:9 screen format for the games' own widescreen mode, scanlines per console line](#every-machine-a-169-screen-format-for-the-games-own-widescreen-mode-scanlines-per-console-line-176) | none | **the host stamp of all 20 profiles** | the Amiga, Atari ST and Nintendo 64 keys move (every input, the host's included); the others do not |
| [Every machine: stick directions as inputs, new keyboard defaults on S D F / E R T](#every-machine-stick-directions-as-inputs-new-keyboard-defaults-on-s-d-f--e-r-t-176) | none | **the host stamp of all 20 profiles** (`hostkit/hostkit.h`, the shell, the adapters' default keys) | the Amiga, Atari ST and Nintendo 64 keys move (every input, the host's included); the others do not |
| [Every machine: the pad's speed controls as combinations, the graphics page from F2 and from the pad](#every-machine-the-pads-speed-controls-as-combinations-the-graphics-page-from-f2-and-from-the-pad-176) | none | **the host stamp of all 20 profiles** (`game_options.h`, `retro_menu.c`, the shell, the locale files) | the Amiga, Atari ST and Nintendo 64 keys move (every input, the host's included); the others do not |
| [Machines' own rows and pages: their icons](#machines-own-rows-and-pages-their-icons-176) | none | **the host stamp of all 20 profiles** (`retro_menu.c`, `retro_menu.h`, `hostkit/hostkit.h` and six adapters) | the Amiga, Atari ST and Nintendo 64 keys move (every input, the host's included); the others do not |
| [Nintendo 64: supported](#nintendo-64-supported-176) | the Nintendo 64 (TLB-mapped code and the run after an MFC0 become native blocks, the report's interpreted listing, the quick state) | **the Nintendo 64's host stamp**, and the host stamp of every other profile (`runtime_catalog.inc`) | **the Nintendo 64 states of 1.7.5 are refused** (`RRN64QS2`); the Amiga and Atari ST keys move (every input) |
| [Nintendo 64: the graphics page in five rows](#nintendo-64-the-graphics-page-in-five-rows-176) | none | **the host stamp of all 20 profiles** (`runtime_catalog.inc`, the locale files), the Nintendo 64's for `rrhk_n64.inc` | the Amiga, Atari ST and Nintendo 64 keys move (every input, the host's included); the others do not |
| [Nintendo 64: Supersampling and 8x on the graphics page](#nintendo-64-supersampling-and-8x-on-the-graphics-page-176) | none | **the host stamp of all 20 profiles** (`runtime_catalog.inc`, the locale files), the Nintendo 64's for `rrhk_n64.inc` | the Amiga, Atari ST and Nintendo 64 keys move (every input, the host's included); the others do not |
| [Nintendo 64: the C buttons on the right stick, "Left stick", the 16:9 screen format](#nintendo-64-the-c-buttons-on-the-right-stick-left-stick-the-169-screen-format-176) | none | **the Nintendo 64's host stamp** (`rrhk_n64.inc`) | the Nintendo 64 key moves (every input, the host's included) |
| [Nintendo 64: "Picture area (auto)", the overscan crop by default](#nintendo-64-picture-area-auto-the-overscan-crop-by-default-176) | **the Nintendo 64** (the glue and the session) | **the host stamp of all profiles** (`runtime_catalog.inc`, the locale files), the Nintendo 64's for `rrhk_n64.inc` | **the Nintendo 64 key moves**; the Amiga and Atari ST keys move (every input, the host's included) |
| [Every machine: clear any binding, Restore defaults on each control page](#every-machine-clear-any-binding-restore-defaults-on-each-control-page-176) | none | **the host stamp of all 21 profiles** (the shell, `hostkit/hostkit_internal.h`, `runtime_catalog.inc`, the locale files) | the Amiga, Atari ST and Nintendo 64 keys move (every input, the host's included); the others do not |
| [Every machine: symmetric sticks, -32767..32767](#every-machine-symmetric-sticks-176) | none | **the host stamp of all 21 profiles** (`rrhk_input.c`, `hostkit/hostkit.h`) | the Amiga, Atari ST and Nintendo 64 keys move (every input, the host's included); the others do not |
| [Linux: a moved game folder keeps a working launcher](#linux-a-moved-game-folder-keeps-a-working-launcher-176) | none | **the host stamp of all 21 profiles** (`rrhk_main.c`, `hostkit/hostkit_internal.h`) | the Amiga, Atari ST and Nintendo 64 keys move (every input, the host's included); the others do not |
| [Every machine: "Quit the game", the last row of the options page](#every-machine-quit-the-game-the-last-row-of-the-options-page-176) | none | **the host stamp of all 20 profiles** (the shell, `retro_menu.c`, `runtime_catalog.inc`, the locale files) | the Amiga, Atari ST and Nintendo 64 keys move (every input, the host's included); the others do not |
| [Game Boy Advance: the sound is compared, the quick state has a checksum, a save larger than its chip is set aside, the report names its units](#game-boy-advance-the-sound-is-compared-the-quick-state-has-a-checksum-a-save-larger-than-its-chip-is-set-aside-the-report-names-its-units-175) (titled 1.7.5, but not in the `v1.7.5` tag: it ships in 1.7.6 with the merge of `spec/gba-175`) | the Game Boy Advance | none | **the Game Boy Advance states of 1.7.5 are refused** (the checksum envelope) |
| emu2413's `LICENSE` keeps its exact bytes on a Windows checkout (`-text` in `.gitattributes`; no section of this page; commit `ffbaee01`) | none | none | none |
| The README's console order (no section of this page; merge `a87db1fe`) | none | none | none |

## Game Boy Advance: supported (1.7.6)

**Status.** The Game Boy Advance is supported from 1.7.6, on the owner's decision of 14 November 2026 after his play test of six cartridges (G14, the owner-acceptance table of
[QUALIFICATION.md](QUALIFICATION.md#owner-acceptance); [GAME_BOY_ADVANCE.md](GAME_BOY_ADVANCE.md#the-exit-from-the-experimental-status-14-november-2026-supported-from-176)). The profile's status is `supported`,
the conversion report's `status` is read from the profile, the Options note loses "experimental" in the eight languages and the credits no longer list the machine among the experimental ones. Nothing a conversion does changes.

**Stamps** (`compilation_inputs.role_stamps`, this branch against `spec/gba-175`, then against main `fe5ef2c3`): **the Game Boy Advance game stamp only**. Against `spec/gba-175` the status alone moves it (`e6e3909337ce` to `c336150515fd`;
`retrorecomp/systems/gba.py` and the docstring of `retrorecomp/gba.py` are among its inputs); against main, where the 1.7.5 changes of that branch are not yet merged, it is `f65705900b6a` to `c336150515fd`. The Game Boy Advance host and build stamps (`3f8e2ffea164`, `6b70933a9b0a`)
and every other machine's stamps equal main's.

**Existing exports:** the game stamp moves, so an export is converted again in full at its next conversion, from the player's own paths; the Game Boy Advance's exports are private (a game holds code derived from the player's BIOS) and
there is no frozen legacy stamp for them. The six exports of 14 November 2026 are not converted again for this change. **Quick states:** unchanged (the Game Boy Advance quick state is checked by the game's SHA-256 and the envelope's
schema, neither of which reads a stamp). **Site limits:** unchanged. **Hot path:** no.

## Commodore Amiga 1200: an experimental profile beside the Amiga 500 (1.7.6)

**What changes.** A new profile, `a1200` (experimental), converts Amiga 1200 WHDLoad installs on the same converter, session and host
adapter as the Amiga 500, run with the A1200 model: vAmiga's A1200 scheme (68EC020 with its instruction cache, AGA, 2 MiB of chip RAM, the
A1200 bank map), the 68EC020's instructions as native code (Moira's 68020 core specialised per opcode, lengths read from the extension words:
`retrorecomp/m68020_lengths.py`) and the player's Kickstart 3.x over `$F80000` ([AMIGA.md](AMIGA.md#7-the-amiga-1200-a1200)). The
Amiga 500's conversions give the same outputs: its opcode table is byte-identical, its generated code unchanged. On both Amigas,
`resload_Decrunch` now unpacks Crunch-Mania files (`native/amiga_whdload/rr_decrunch.c`): an install that stopped there converts.

**Stamps** (`compilation_inputs.role_stamps`, this branch against main `a87db1fe`): **the game stamps of the Amiga (`df26554edb79` to
`f518d06f1ee4`), the Atari ST (`6116a5b0bb28` to `2c7abad214e0`) and the X68000 (`d2ca5b2765b2` to `cec9c4a08a86`)**; no host or build stamp
moves. The Amiga's from its own files (the session, the resload layer, the opcode-table tool, the generator, the conversion); the three
together from `retrorecomp/m68k_media_knowledge.py` and `retrorecomp/path_records.py`: the common record handling cut out on the MSX2+ branch
(`eef2e984`, carried here as the same patch) and the instruction-length hook on it, whose 68000 answers are the old ones
(`tests/test_m68020_lengths.py`). The Amiga's `GENERATOR_REVISION` is 2: the Amiga paths qualified by revision 1 wait again.

**Interlaced screens (15 November 2026, after Arthur's play test).** On both Amigas, a screen with LACE set is shown woven: the long and the
short field in one picture of twice the lines (`amiga_session.cpp`), so it no longer moves a line every frame; the adapter shows the twice-as-many
rows in the same window (`rrhk_amiga.inc`). Generic: it keys on the machine's LACE bit and the frame's long-field bit, never on a game. The
picture hash of interlaced frames changes, the same in the reference and native runs; a game without LACE is unchanged byte for byte
(Slam Tilt: every field of its report equal). Banshee's title no longer alternates; a quick state saved during it continues 100 frames
equal in a fresh process. A quick state now carries the held field and, on the A1200, restores the window of a 512 KiB Kickstart. Stamps of
this part, against `4d875fbc`: **the game and host stamps of `amiga` and `a1200`**, nothing else.

**Existing exports:** the three game stamps move, so their exports are converted again in full at their next conversion. **Quick states:**
every Amiga state is refused (`RRAMIGA-STATE-6`: the resload state grew by the A1200's chip revision bits, and the held interlaced field follows the sound). The X68000's and
the Atari ST's states do not read these files. **Site limits:** the `a1200` machine is not shared (experimental). **Hot path:** the
A500's native steps are unchanged; the A1200's frame cost was measured on a quiet PC (Slam Tilt 10.6 ms a frame, Lotus 2 on the A500 7.0 ms).

## Commodore Amiga: the CPU's speed, a player's option (1.7.6)

**What changes.** Both Amiga models get the row « CPU speed: Normal / x2 / x4 » on F2's options page (`rrhk_amiga.inc`), Normal by
default, kept per game in `cpu.cfg`; the player's `--cpu-factor 1|2|4` sets it for one run. The session sets vAmiga's CPU overclocking
for it (`rr_amiga_cpu_factor`, `amiga_session.cpp`: A500 0, 2, 4; A1200 2, 4, 8) and sets the player's choice again after a quick-state
load (the snapshot carries the factor it was saved with). The exception to D14 is the owner's decision of 15 November 2026
([HOST_KIT.md](HOST_KIT.md#d14)). The conversion never passes the factor: routes, checks and state proofs run at Normal, and at Normal the
session changes nothing (it sets the option only when it differs). `amiga_conversion.CPU_STOCK_ONLY` (reviewed data by SHA-256, empty)
adds `RR_AMIGA_CPU_STOCK_ONLY` to the payload of a listed install, which keeps the row at Normal; no other install's payload changes.

**Proof.** Headless on Fears (A1200, converted at the quick level on this branch with every check passing): a new picture every 3.36,
2.19 and 1.33 frames at Normal, x2 and x4, the same place in the corridor at the same frame; a state saved at x4 and loaded with no factor
runs at Normal (3.0 frames a picture), loaded at x4 at x4 (1.0); the in-play state saved at Normal loaded at x4 runs at x4 (1.07). The menu
harness (`tests/amiga_menu_harness.c`, 48 checks): the row cycles and says the model's clock, the choice is kept, `--cpu-factor` is for one
run, an unknown value or a damaged file reads as Normal, a listed game stays at Normal. Host cost, indicative (a PC that was not quiet):
18.2, 19.4 and 20.5 ms a frame on Fears; the quiet-PC timing pass waits for the owner's OK. Normal changes nothing: Slam Tilt and Banshee
(A1200) and Five A Side Soccer (A500), converted again at the quick level on this branch, give reports whose every field of every route
equals their earlier conversions' (`2d92f029` and `eb6b6a6e`), trace digests included.

**Stamps** (`compilation_inputs.role_stamps`, this branch against main `3a03053e`): **the game and host stamps of `amiga` and `a1200`**
(`amiga_session.cpp`, `amiga_session.h`, `amiga_player.c`, `amiga_conversion.py`; `rrhk_amiga.inc`), nothing else. **Existing exports:**
converted again in full at their next conversion. **Quick states:** the format is unchanged (`RRAMIGA-STATE-6`); a state of an earlier
build is refused, as every build's are. **Site limits:** unchanged. **Hot path:** at Normal, none (one comparison after a state load); at
x2 and x4 the CPU runs that many more cycles a frame (the host figures above).

## Path records: one copy for the 68000 computers and the MSX2+ (1.7.6)

**What changes.** `retrorecomp/path_records.py` holds what every machine of the schema 3 tier does with its path records: naming a record
(`record_digest`), its engine, its comparable paths, whether two records are about the same images, uniting two records, salvaging a received
one, gathering the three banks for a conversion and the player's library record. The 68000 computers' `MediaKnowledge`
(`retrorecomp/m68k_media_knowledge.py`) is now a subclass of it and keeps only what its firmware rows add (the union, the rebuild, the
expansion of its rows); the MSX2+ (below) uses it directly. A pure refactor (commit `eef2e984`): `tests/test_m68k_media_knowledge.py` pins
every outcome, the X68000's records are byte for byte the same, nothing a conversion does changes.

**Stamps** (`compilation_inputs.role_stamps`, the commit against its parent): **the game stamps of the X68000, the Amiga and the Atari ST**
(a new group `shares:path_records`, and `m68k_media_knowledge` moved); their host and build stamps and every other machine's stamps are
unchanged. **Existing exports:** converted again in full at their next conversion, from the player's own paths; the records already in a
library or a bank keep being read (same format, same engine strings).

## MSX2+: supported (1.7.6)

**Status.** The MSX2+ is supported from 1.7.6, on the owner's decision of 14 November 2026 after his play test of the six games of the
checklist (G14, the owner-acceptance table of [QUALIFICATION.md](QUALIFICATION.md#owner-acceptance); [MSX.md](MSX.md#9-the-msx2-msx2plus)).
The profile's status is `supported`, the report's `status` is read from the profile, the Options note loses "experimental" in the eight
languages (and now names MSX-MUSIC, the kanji font and the disk requests in place of a stale "not yet"). Nothing a conversion does changes.

**Stamps:** the MSX game stamps move with `retrorecomp/systems/msx.py` (shared by the MSX, the MSX2 and the MSX2+, already moving in this
release), and the MSX2+ host stamp with its option note. **Existing exports:** as in the section below.

## MSX2+: MSX-MUSIC, the kanji font, shared paths (1.7.6)

**What changes.** On the MSX2+: MSX-MUSIC (the YM2413 on emu2413 v1.5.9, MIT; C-BIOS's music ROM by default, your own FM BIOS as an
option), your own kanji font as an option (128 or 256 KiB, never shipped), and the shared paths of the experimental tier (the RAM windows a
conversion learned, as offsets in the cartridge or in the disks; Arthur's decision of 14 November 2026). The MSX and the MSX2 get none of
them: their games link nothing of MSX-MUSIC and their output is unchanged (Aleste as an MSX2 game: the same image and sound hashes as on
main). [MSX.md](MSX.md#9-the-msx2-msx2plus) has the details and the five measures.

**Stamps** (this branch against main `a87db1fe`, the path-records change included): **the game stamps of the MSX, the MSX2 and the MSX2+**
(the machine files they share: `msx_machine.c`, `msx_psg.c`, `msx_state.c`, the runners, `msx_conversion.py`, `systems/msx.py`), **the MSX2+
host stamp** (its option labels); plus the X68000, Amiga and Atari ST game stamps of the change above. Every other stamp is unchanged.

**Disk requests.** A game of several disks gets the next disk when it asks for one, in its routes and in play (the player is told;
Page Up / Page Down stay the player's); the routes no longer change disks at fixed frames (MSX.md, "Disk requests").

**Existing exports:** MSX, MSX2 and MSX2+ games are converted again in full at their next conversion. **Quick states:** the layout is
`msx-state-6` (the YM2413 and the kanji addresses are in it), so the quick states of 1.7.5 games are refused cleanly at load, never
misread; cartridge SRAM and the copies of written disks are kept.

## Every machine: clear any binding, Restore defaults on each control page (1.7.6)

On the owner's request of 15 November 2026 (a button he had put on the Nintendo 64's Stick rows could not be removed): any binding
of any machine can be cleared, and each control page can be put back to its defaults ([HOST_KIT.md](HOST_KIT.md#d28), D28).

* **Stamps.** The host stamp of all 21 profiles moves (`hostkit/hostkit.h` (a comment), `hostkit/hostkit_internal.h`, the shell's
  `rrhk_input.c`, `rrhk_events.c`, `rrhk_menu.c`, `rrhk_options.c`, `runtime_catalog.inc` and the seven locale files). No adapter,
  no game or build stamp: existing exports are not converted again for it. The quick-state keys of the machines that hash every
  input (the Nintendo 64, the Amiga, the Atari ST) move; no other quick-state key.
* **What players see.** Delete, Backspace or the pad's X on a binding or combination row clears it, and it stays cleared. A last
  row, **Restore defaults**, on every control page; so a page that showed fifteen rows exactly now scrolls by one. A button bound
  on a Nintendo 64 Stick row reads "X / Left stick". The ^ and v marks of a scrolling page are visible.
* **Preferences.** Unchanged formats: a cleared row is the key 0 / button -1 every machine already read as "no binding"; Restore
  writes the default values themselves.
* **Texts.** Two new entries in the five game languages: "Enter: remap | Del/X: clear | Left/Right: page" and "Enter / A: restore
  this page".
* **Checks.** `tools/hostkit_capabilities_selftest.py` run 13 (Delete, Backspace and the pad's X clear keys, buttons and a
  combination, read back as cleared at the next start; Restore defaults on the keyboard and gamepad pages, the swap, the other
  player untouched); a gallery of the owner's saved Nintendo 64 page (before, cleared, restored) in French and English.

## Every machine: symmetric sticks (1.7.6)

On the owner's word of 15 November 2026 (« Oui, inclus-la »), after the PlayStation's stick fix: SDL gives -32768 at a stick's
left or top edge, and a core may not take it. Beetle's DualShock turned it into the opposite edge (Ape Escape: full left went
right), and Mupen64Plus-Next's `x*x + y*y` overflows an int when both axes are -32768 (the stick read as centred in that corner).
The kit's `rrhk_pad_axes`, which every machine that reads the sticks calls, now gives -32768 as -32767, before and after the dead
zone; a replay's recorded axes are given as recorded. The PlayStation keeps its own clamp for its script and reference runs.

* **Stamps.** The host stamp of all 21 profiles moves (the shell's `rrhk_input.c`, `hostkit/hostkit.h` (a comment)). No adapter,
  no game or build stamp: existing exports are not converted again for it. The quick-state keys of the machines that hash every
  input (the Nintendo 64, the Amiga, the Atari ST) move, as 1.7.6 already moves them; no other quick-state key.
* **What players see.** A stick pushed fully left or up reaches the edge on every machine that reads the sticks (today the
  PlayStation and the Nintendo 64); one step of 32767 is lost on that side only, nothing a game can tell.
* **Checks.** `tools/hostkit_capabilities_selftest.py`: a virtual pad at -32768 (SDL really gives it) comes out -32767 at 0 %,
  32767 stays, the dead zone's corners stay at or above -32767, and a script's -32768 is given as recorded.

## Linux: a moved game folder keeps a working launcher (1.7.6)

On the owner's report of 15 November 2026 (Linux exports copied to another PC started from nothing): « qu'on puisse déplacer
notre jeu sans que ça casse tous les chemins ». The launcher `<game>.desktop` beside each Linux game holds absolute paths (no
relative form works on every desktop: GLib leaves `%k` empty), and up to 1.7.5 the game file itself was listed in the folder's
`.hidden`, so after a move nothing could be started.

* **The converter** (`retrorecomp/linux_desktop.py`) no longer hides the game file, and takes the line earlier versions wrote out
  of `.hidden` (the player's lines kept byte for byte) when it writes or retires a launcher.
* **The game** (the kit's `rrhk_main.c`, [HOST_KIT.md](HOST_KIT.md#d29), D29), at start on Linux: when its own launcher carries
  our identity marker and no longer names its folder, its Exec, Path and Icon lines are written again for the current folder
  (atomically, mode 0755, every other byte kept); our `.hidden` line is taken out the same way. Any failure is silent; a
  launcher without our marker is never touched; nothing runs on Windows. Adventure (ScummVM) games do not run the kit and are
  not healed: the converter refreshes their launcher.
* **What players do.** After moving a folder, double-click the game file once (it is visible now); its launcher works again
  from then on. A game rebuilt by 1.7.6 (its host stamp moves) carries the heal; a 1.7.5 game file moved as it is does not.
* **Stamps.** The host stamp of all 21 profiles moves (`rrhk_main.c`, `hostkit/hostkit_internal.h`); `linux_desktop.py` is
  interface code and moves none. No game or build stamp. The quick-state keys of the Nintendo 64, the Amiga and the Atari ST
  move, as 1.7.6 already moves them; no other.
* **Checks.** `tools/hostkit_capabilities_selftest.py`: the healed text equals the lines `linux_desktop.py` writes for a path
  with a space, `$`, `"`, a backquote, `%` and a backslash, every other byte kept (a second group's Exec untouched); a current
  launcher, one without our marker, one with an upper-case identity and a too-long path are left alone; on Linux, the files
  (mode 0755, the player's `.hidden` lines kept, an emptied `.hidden` removed, a foreign launcher byte-identical).
  `tests/test_linux_desktop.py` for the converter.

## Every machine: a 16:9 screen format for the games' own widescreen mode, scanlines per console line (1.7.6)

A machine whose games may draw an anamorphic widescreen picture can show it at 16:9, kept per game; the scanlines follow the
console's lines on every machine ([HOST_KIT.md](HOST_KIT.md#d27), D27).

* **Stamps.** The host stamp of all 20 profiles moves (`hostkit/hostkit.h`: `RrhkMachine.widescreen`, `RrhkUi.widescreen`;
  `hostkit/hostkit_internal.h`; the shell's `rrhk_video.c`, `rrhk_input.c`, `rrhk_options.c`, `rrhk_events.c`, `rrhk_main.c`,
  `rrhk_menu.c`; `retro_menu.c` and `retro_menu.h` for the icon; `runtime_catalog.inc` and the locales). No game or build
  stamp, no quick-state key. The row appears on a machine once its adapter sets `widescreen` (the Nintendo 64 and the
  PlayStation, by their specialists).
* **What players see.** On those machines a "Screen format" row (4:3 by default). On every machine, scanlines at 2x or 4x
  internal resolution: one dark line per console line, visible again (before: one per internal row, too thin to see at 2x and
  not drawn at all at 4x below a 1920-row screen).
* **Preferences.** One section, `[<Console>.Widescreen]`, one key per game (its title, letters and digits), 1 for 16:9.
* **Texts.** One new entry in the five game languages: "Screen format: %s" (the values 4:3 and 16:9 are not translated).
* **Checks.** `tools/hostkit_capabilities_selftest.py` run 12 (the row, the key kept for the game, the 16:9 rectangle, read back
  at the next start); the filter measurement of the 3D geometries before and after the scanline fix.

## Every machine: stick directions as inputs, new keyboard defaults on S D F / E R T (1.7.6)

A stick direction can be bound to any digital control, and player 1's keyboard defaults of the machines with few buttons move to
S D F / E R T ([HOST_KIT.md](HOST_KIT.md#d26), D26).

* **Stamps.** The host stamp of all 20 profiles moves (`hostkit/hostkit.h`: the stick values, `pad_label`, `former_letter`; the
  shell's `rrhk_input.c`, `rrhk_events.c`, `rrhk_menu.c`; `runtime_catalog.inc` and the locales). The adapters whose tables
  change are host files of their machines: `rrhk_gb.inc`, `rrhk_nes.c`, `rrhk_sms.c`, `rrhk_md.c`, `rrhk_snes.c`, `rrhk_gba.c`,
  `rrhk_ng.c`, `rrhk_cps1.c`, `rrhk_pce.c`, `rrhk_amiga.inc`, `rrhk_atarist.inc`, `rrhk_x68k.inc`, `rrhk_msx.inc`. No game or
  build stamp, no quick-state key.
* **What players see.** After the upgrade, buttons 1-3 on S D F and 4-6 on E R T on those machines; a key the player chose in
  F2 is kept. The PlayStation and the Nintendo 64 are unchanged. A stick direction appears on the gamepad page as "R stick right"
  and so on.
* **Preferences.** Nothing to migrate by hand: a saved key equal to the former default moves by itself; the stick values 66-73
  are new binding values (a 1.7.5 export reading them ignores them).
* **Texts.** Nine new entries in the five game languages: the eight stick directions and "Left stick".
* **Checks.** `tools/hostkit_capabilities_selftest.py` run 11 (a stick bound by F2, refused on a host-side row, held and
  released with the hysteresis) and `tools/hostkit_players_selftest.py` (the new defaults of the CPS-1 adapter, players 3 and 4,
  the migration of a former default, a default a saved key uses dropped).

## Every machine: the pad's speed controls as combinations, the graphics page from F2 and from the pad (1.7.6)

Fast forward and Max speed become rows of player 1's gamepad page; a machine with a graphics page gets a Graphics tile in F2
and an "F3 Graphics" row on its options page ([HOST_KIT.md](HOST_KIT.md#d25), D25).

* **Stamps.** The host stamp of all 20 profiles moves (`native/game_options.h`, `game_options_checks.c`, `retro_menu.c`,
  `retro_menu.h`, `runtime_catalog.inc`, `hostkit/hostkit_internal.h`, the shell's `rrhk_events.c`, `rrhk_input.c`,
  `rrhk_main.c`, `rrhk_menu.c`, `rrhk_options.c`, the seven locale files); no adapter, no game or build stamp, no quick-state key
  (none of these files fixes a state layout).
* **What players see.** Nothing changes in play: R2 still fast-forwards and L2 still toggles the maximum speed, unless the game
  has the trigger (as before) or the player moves or clears them. Two more rows on player 1's control pages; on the N64 and the
  PlayStation a Graphics tile and the "F3 Graphics" row.
* **Preferences.** Two keys, `[<Console>.Options] fast_forward_pad` and `max_speed_pad` (missing: R2 and L2; 0: cleared): a file
  of 1.7.5 loads unchanged.
* **Texts.** Six new entries in the five game languages: "Fast forward", "Max speed", their two hints, "Tab and `: fixed keys",
  "F3 Graphics".
* **Per-frame cost.** The trigger reading of the speed controls moves from the event loop to two combination checks a frame.
* **Checks.** `tools/game_options_selftest.py` (defaults, held and toggled, refusal while they hold a trigger) and
  `tools/hostkit_capabilities_selftest.py` runs 1, 4, 6 and 10 (290 checks).

## Machines' own rows and pages: their icons (1.7.6)

The rows and pages a machine draws or adds itself get their icons ([HOST_KIT.md](HOST_KIT.md#d24), D24).

* **Stamps.** The host stamp of all 20 profiles moves (the seven icons are in `native/retro_menu.c` and `retro_menu.h`, and
  `RRHK_ROW_KEYBOARD` moves to `hostkit/hostkit.h`); the adapters changed are `rrhk_gb.inc`, `rrhk_nes.c`, `rrhk_sms.c`,
  `rrhk_ng.c`, `rrhk_cps1.c` and `rrhk_computer.inc` (host files of their machines). No game or build stamp, no quick-state key.
* **What players see.** An icon instead of the generic gem on those rows; on the CPS-1 DIP page and the computers' shortcut page,
  an icon before each line.
* **Checks.** A quick conversion of one game per changed adapter (NES, Master System, Game Boy, Neo Geo, MSX for
  `rrhk_computer.inc`; the CPS-1 adapter is built by `tools/hostkit_players_selftest.py`), the gallery of the five pages in
  English and French, the suite.

## Nintendo 64: supported (1.7.6)

**Status.** The Nintendo 64 is supported from 1.7.6, on the owner's decision of 15 November 2026 after his play test of the eight panel
exports (G14, the owner-acceptance table of [QUALIFICATION.md](QUALIFICATION.md#owner-acceptance);
[NINTENDO_64.md](NINTENDO_64.md#supported-from-176-15-november-2026)). It does not share its paths, on the same decision (the gain
judged too small: 2.3 % to 11.5 % of a play route at the Standard level). The profile's status is `supported`, the report's `status` is read
from the profile, the Options note loses "experimental" in the eight languages and the credits no longer list the machine among the
experimental ones.

**What else the branch brings** (`spec/n64-176`): TLB-mapped code and the run after an MFC0 become native blocks; the report lists every
interpreted instruction by class (the totals and the 256 most run sites; the whole listing in the qualification folder); the quick state
(format `RRN64QS5`) holds what the core and its plugins left out, carries a checksum and continues with its sound; the restart check gives
the save memory as it was; Majora's Mask and Rayman 2 have play routes.

**Stamps** (`compilation_inputs.role_stamps`, this branch against main `03b1daa7`): the Nintendo 64 game stamp (`b2f1227b519d` to
`8a8f380f9f2c`) and host stamp (`f8f6db677f10` to `e3bb3877160c`) move; its build stamp is unchanged. The host stamp of every other profile
moves for the game catalogue (`native/runtime_catalog.inc`, the graphics page below); their game and build stamps equal main's.

**Existing exports:** the game stamp moves, so a Nintendo 64 export is converted again in full at its next conversion. **Quick states:** the
1.7.5 ones (`RRN64QS2`) are refused cleanly (exit status 4 in a test run; in play, the kit's notice). **Cartridge saves:** unchanged, the same
file of 296,960 bytes beside the game. **Site limits:** unchanged (no shared paths). **Hot path:** the native blocks' dispatch adds a binary
search for TLB-mapped addresses only; KSEG0 dispatch is unchanged.

## Nintendo 64: the graphics page in five rows (1.7.6)

On the owner's word of 15 November 2026 (« Oui, valide »), the F3 page of the Nintendo 64 keeps five rows: Internal resolution, Edge
smoothing (console), Smooth scaling (console), Dither smoothing and Overscan crop (Native texture LOD left too once the owner
closed his F-Zero X remark: its level of detail is the game's own)
([NINTENDO_64.md](NINTENDO_64.md#4-in-the-game)).

* **Stamps.** The host stamp of all 20 profiles moves (`native/runtime_catalog.inc` and the seven locale files: three new entries,
  eight N64-only entries removed); the Nintendo 64's host stamp moves for its adapter `rrhk_n64.inc`. No game or build stamp, no
  quick-state key.
* **What players see.** Six rows fewer. The renderer's other settings are fixed at the defaults every check uses: no super-sampled
  read-back, native texture LOD off, Bob deinterlacing, the gamma dither and native texture rectangles on; the divot filter follows Edge smoothing. A player who
  had changed a removed row (Weave, the read-back) gets the default back; the kept rows keep their saved values (same ini keys).
* **Texts.** Three new entries in the five game languages: "Edge smoothing (console)", "Smooth scaling (console)", "Dither smoothing".
* **Checks.** A quick conversion of Super Mario 64, its game run headless with each kept row changed, and run with an ini that still
  holds the removed rows; the suite.

## Nintendo 64: Supersampling and 8x on the graphics page (1.7.6)

On the owner's word of 15 November 2026 (« Ok pour ta proposition d'anti-crénelage. », then « Dans la 1.7.6 »), the F3 page of the
Nintendo 64 gains a **Supersampling** row under Internal resolution, Off by default, and the resolution row gains **8x**
([NINTENDO_64.md](NINTENDO_64.md#4-in-the-game)). Supersampling draws at twice the internal resolution and ParaLLEl's scanout reduces
the picture by two: same picture size, each pixel the mean of four. At 8x, the renderer's largest, it does nothing.

* **Stamps** (`compilation_inputs.role_stamps`, branch `spec/n64-ssaa-176` against main `deb44dae`). The host stamp of all 20 profiles
  moves (`native/runtime_catalog.inc` and the seven locale files: one new entry); the Nintendo 64's host stamp (`e3bb3877160c` to
  `b6b4c55e1937`) moves also for its adapter `rrhk_n64.inc`. No game or build stamp moves: existing exports are not converted again
  for it. The Nintendo 64's quick-state key moves (it hashes every input, the host's included): a state of a build before is refused
  cleanly. Cartridge saves are unchanged.
* **What players see.** Six rows on the page. A player who touches nothing gets the same picture as before (the whole trace of a run
  equal). 8x is heavy: on an RTX 3090 it does not hold full speed (the read-back of a 5120 x 2304 picture each frame); 4x with
  Supersampling draws at 8x for the read-back cost of 4x. A weak or integrated graphics card may hold neither.
* **Texts.** One new entry in the five game languages: "Supersampling".
* **Checks.** A quick conversion of Super Mario 64; its game run headless at the defaults (trace equal to the build before), at 4x,
  4x with Supersampling, 1x with Supersampling, 8x and 8x with Supersampling (sizes, equal traces at 8x), with Supersampling turned on
  and off at given frames; a rough unpaced cost of each size; the suite. No hot-path change: the renderer's options only.

## Nintendo 64: "Picture area (auto)", the overscan crop by default (1.7.6)

On the owner's word of 15 November 2026 (« Oui, auto par défaut », then « auto par défaut, mais que ça soit une option qu'on puisse
désactiver »), the Overscan crop row of F3 gains **Picture area (auto)**, its new default: each frame is cut to the window the game's
video interface opens (its H_START and V_START registers, PAL told by V_SYNC as parallel-rdp tells it, less the VI's guard band of 8 and
7 pixels), through parallel-rdp's `crop_rect`, so the blank border a television hid is not shown; the pixels keep their shape (the
session reports the uncropped frame, `rr_n64_picture_frame`, and the adapter's display width follows it)
([NINTENDO_64.md](NINTENDO_64.md#4-in-the-game)). **Off** shows the console's whole picture, borders included; 8 and 16 pixels stay.

* **Stamps** (`compilation_inputs.role_stamps`, branch `spec/n64-overscan-176` against main `893748a9`). The Nintendo 64's game stamp
  moves (`8a8f380f9f2c` to `b187be879648`: the glue `parallel_glue.cpp` and `parallel.h`, the session `n64_session.cpp` and `.h`, which
  start every run with the crop, the reference player's included) and its host stamp (`68c9dd815779` to `fcf22888e83d`, the adapter);
  the host stamp of every other profile moves for the game catalogue (`runtime_catalog.inc` and the locale files: one new entry). No
  build stamp.
* **Existing exports:** the game stamp moves, so a Nintendo 64 export is converted again in full at its next conversion (already the
  case between 1.7.5 and 1.7.6). **Quick states:** the Nintendo 64 key moves (a state of a build before is refused cleanly).
  **Cartridge saves:** unchanged.
* **What players see.** A larger picture with no blank border in the window and in Fit to screen (Super Mario 64, PAL: 625 x 237
  instead of 640 x 288 with 8, 8, 25 and 26 blank pixels). A player who chose a value of the row keeps it (the row's values keep their
  index; the new one is last); one who never touched it gets the crop. The kit saves a row only when the player changes it.
* **Texts.** One new entry in the five game languages: "Picture area (auto)".
* **Checks.** The eight panel games converted at the Quick level (native against reference with the crop in both: all ready); each
  game run headless to frame 3,600 of its main route with the crop and with Off: no blank edge left with the crop except a game's own
  black (F-Zero X draws a black frame inside its picture; Majora's Mask's frame is a text screen), the HUDs whole; the suite.

## Nintendo 64: the C buttons on the right stick, "Left stick", the 16:9 screen format (1.7.6)

On the stick plan the owner saw, with the kit's stick directions as inputs (the section above): the four C buttons default to the right
stick's four directions (`RRHK_PAD_RSTICK_*`, rebindable in F2 like any button), Y and B are free, and the right stick's axes are no
longer handed to the core (which read them as C buttons past half way); the four keyboard Stick rows show "Left stick" on the gamepad
page; the adapter sets `widescreen`, so the options page offers **Screen format: 4:3 / 16:9** for games that squeeze a widescreen
picture with their own option ([NINTENDO_64.md](NINTENDO_64.md#4-in-the-game)).

* **Stamps** (`compilation_inputs.role_stamps`, branch `spec/n64-ssaa-176`): the Nintendo 64's host stamp (its adapter
  `rrhk_n64.inc`). No game or build stamp; the Nintendo 64's quick-state key moves (every input, the host's included).
* **What players see.** The C buttons on the right stick as before, now through the kit (the kit's threshold instead of the core's
  half way); Y and B do nothing until bound. A C binding saved in F2 is kept. The control stick is unchanged.
* **Checks.** `tools/n64_sticks_selftest.py` (the kit's shell and this adapter around a stub session, one virtual pad, no window): the
  left stick reaches the core as the kit reads it at several positions, each right-stick direction presses its C button past the
  threshold and none under it, the right stick's axes reach the core as 0, Y and B press nothing; an adapter that still passes the axes
  on fails it. A Super Mario 64 run of 3,600 frames (main route: the stick in every direction, C buttons) keeps its whole trace against
  the build before. GoldenEye 007's Ratio 16:9 set from its watch menu by a scripted route, captured without a window: the squeezed
  picture the 16:9 format stretches.

## Every machine: "Quit the game", the last row of the options page (1.7.6)

The options page ends with a **Quit the game** row ([HOST_KIT.md](HOST_KIT.md#d23), D23) that asks the same "Quit? No / Yes"
as Esc; No comes back to the page.

* **Stamps.** The host stamp of all 20 profiles moves (`hostkit/hostkit_internal.h`, the shell's `rrhk_options.c`,
  `rrhk_events.c`, `rrhk_menu.c`, `native/retro_menu.c` and `retro_menu.h` for the icon, `runtime_catalog.inc`, the seven
  locale files); no game or build stamp, no quick-state key (none of these files fixes a state layout).
* **What players see.** One more row, last; at most fourteen rows (the computers, the Neo Geo), no scrolling anywhere.
* **Texts.** One new entry in the five game languages: "Quit the game".
* **Checks.** `tools/hostkit_capabilities_selftest.py` run 9: the row asks, No and Esc come back to the page while the game
  waits, Esc then goes back to the tiles, Yes ends the loop (280 checks).

## Sony PlayStation: the CPU state is compared, every interpreted instruction is listed, the GTE's quick state is fixed, the memory card is set aside when unusable (1.7.6)

**What changes for a conversion.** The per-frame trace of every route carries a hash of the CPU state a game sees (the R3000A's 32
registers, LO, HI, the PC, the pending load, SR, CAUSE, EPC and the GTE's 64 registers), so the published game is compared with the
interpreter on it too, and so is the F9 continuation. Every instruction the interpreter runs on a route is listed by address in the
report with its reason (`final_checks[].interpreted_by_address`). Two gaps of the native steps are closed: a step that reaches a word
another step holds at the same address (code loaded over other code) hands it to that step, and a COP2 instruction, which Beetle runs
with an interrupt pending, is held by a step too. Ape Escape, at the extended level: 0 interpreted instructions on its three routes
(before: 6,527, 6,613 and 84,619).

**Two fixes of the machine.** Loading a quick state left five of the GTE's registers as they were before the load, and gave
LZCR a computed value instead of the register's (Beetle's `GTE_StateAction`; carried as our anchored fixes,
[UPSTREAMS.md](UPSTREAMS.md#playstation-a-fix-carried-on-beetle-psx-176)).

**Memory card.** A card file the game cannot use (another size, a folder, unreadable) is moved aside whole as
`<card>.mcr.unusable-N` and the game starts with an empty card; the window says so once. It used to be left in place, unread, and
nothing was saved for that session. The card stays the raw 128 KiB other programs read. The move is the new shared helper
`native/save_set_aside.c`, the PlayStation's alone for now.

**Stamps** (`compilation_inputs.role_stamps`, the branch as a whole, the shared paths and G11 included, against main `ffbaee01`, at `6a5d9e9b`): the PlayStation's game stamp (`55f0e406d72d` to `8a84b9740b28`) and host stamp (`bd8f35608de2` to `58aa32803f59`); every other machine's stamps equal main's. **Existing exports:** converted again in full at their next conversion. **Quick states:** a PlayStation state of 1.7.5 is
refused (another build), as for any change of the game. **Hot path:** the step hook calls one more step lookup when a step hands
back a word, which the routes measure as a gain (no interpreted instruction left on Ape Escape's routes); no timing was taken.

## Sony PlayStation: a stick pushed straight left no longer goes right (1.7.6)

**What changes** (Arthur, 15 November 2026, Ape Escape: « si je fais gauche bien droite sur le stick, gauche toute sur le stick,
ça part vers la droite », diagonals going left). A gamepad's stick at its very edge reads -32768 on its negative side. Beetle's
DualShock computes the byte the game reads as `32768 + right - left * 32768 / 32767`: for -32768 that is -1, shifted to 0xFF, the
other edge. The session now holds a stick value at -32767, the edge of libretro's analog range; nothing else of the stick changes.
Checked through the core on a private build (the byte the DualShock hands the game for the left stick's X): -32768 gave 255
before and gives 0 now; -32767, 0 and 32767 give 0, 128 and 255 as before.

**Stamps:** the PlayStation's host stamp (`psx_session.c`). **Existing exports:** rebuilt at their next conversion.
**Quick states:** unchanged. **Hot path:** no.

## Sony PlayStation: the graphics page without deinterlacing and 8x (1.7.6)

**What changes.** F3's page loses two choices (the owner, 15 November 2026). The **Deinterlacing** row is gone: the picture is always
progressive, the session's core setting that was already the row's default (« ok »). **8x** leaves the internal resolution list
(« le 8x, c'est injouable »: 64 times the pixels, never in time on one thread); 1x, 2x and 4x stay. A settings file of 1.7.5 loads
cleanly: its `deinterlace=` is a key no row reads any more (ignored, left in the file), and a saved `resolution=3` is out of range and
keeps the default, 1x.

**Stamps:** the PlayStation's host stamp (the adapter is among its host inputs); its game and build stamps do not move for this change.
**Existing exports:** converted again in full at their next conversion. **Quick states:** unchanged (the deinterlacer's setting was already progressive
by default; a state taken at 8x in 1.7.5 is refused cleanly like every PlayStation state of 1.7.5). **Site limits:** unchanged.
**Hot path:** no.

## Sony PlayStation: supported (1.7.6)

**Status.** The PlayStation is supported from 1.7.6, on the owner's decision of 15 November 2026 after his play test (G14, the owner-acceptance
table of [QUALIFICATION.md](QUALIFICATION.md#owner-acceptance); [PLAYSTATION.md](PLAYSTATION.md#8-the-exit-from-the-experimental-status-15-november-2026-supported-from-176)).
The profile's status is `supported`, the conversion report's `status` is read from the profile and the Options note loses "experimental" in
the eight languages. Nothing a conversion does changes.

**Stamps:** the PlayStation's game stamp (the profile is among its inputs); its host and build stamps do not move for this change.
**Existing exports:** converted again in full at their next conversion. **Quick states:** unchanged by this change. **Site limits:**
unchanged by this change. **Hot path:** no.

## Sony PlayStation: shared paths (1.7.6)

**What changes.** The PlayStation joins the experimental tier of the shared base (Arthur, 14 November 2026: « Oui, elle partage »;
[PLAYSTATION.md](PLAYSTATION.md#6-shared-paths-the-experimental-tier-of-the-base-from-176)). A conversion receives the words of the qualified bank,
the player's library record and the imported bank before its native steps are written, and writes its own record into the player's library once
every check passed; the report gains `knowledge` (what was received, and the record's counts and digest). A failure of the sharing is reported there
and never fails a conversion. `PsxInput` keeps each disc's digest (`disc_digests`); the game's identity is unchanged.

**Stamps:** the PlayStation's game stamp only (`retrorecomp/psx_knowledge.py` and the profile's `shared_knowledge` are its inputs, with
`path_records`); its host and build stamps do not move for this change. **Existing exports:** converted again in full at their next conversion.
**Quick states:** unchanged by this change. **Site limits:** the site must know the PlayStation's records before 1.7.6 is published
(`RECORD_RULES`, sent to the web specialist on 14 November 2026). **Hot path:** no (received words become native steps like observed ones).

## Exports of 1.7.4 in 1.7.5

1.7.5 is the release after 1.7.4 (published on 14 November 2026). This section is the index of its changes, one line per section below, with the
stamps that section says move. Each section computed its stamps for its own change alone, on the tree of its branch.

| Change | Game stamps that move | Host and build stamps | Quick states |
| --- | --- | --- | --- |
| [MSX and MSX2: the mapper probe of battery-backed boards, the exit panel and the exit from the experimental status](#msx-and-msx2-the-mapper-probe-of-battery-backed-boards-the-exit-panel-and-the-exit-from-the-experimental-status-175) | the MSX, the MSX2 and the MSX2+ | none | none (`msx-state-5`); a cartridge whose mapper the probe now reads differently refuses its old states (the mapper is in the binding) |
| [Game Boy Advance: the sound is compared, the quick state has a checksum, a save larger than its chip is set aside, the report names its units](#game-boy-advance-the-sound-is-compared-the-quick-state-has-a-checksum-a-save-larger-than-its-chip-is-set-aside-the-report-names-its-units-175) | the Game Boy Advance only (`f65705900b6a` to `e6e3909337ce`: its probe patches, its player, its conversion) | none | the quick state of a Game Boy Advance game converted before is refused cleanly (the new envelope) |
| [Commodore Amiga: the second joystick on port 1](#commodore-amiga-the-second-joystick-on-port-1-175) | the Amiga (`amiga_session.cpp`, `amiga_session.h`, `amiga_player.c`, `amiga_conversion.py`) | **the Amiga's host stamp** (`native/hostkit/adapters/rrhk_amiga.inc`) | **every Amiga state is refused** (format `RRAMIGA-STATE-4`) |
| [Commodore Amiga: supported](#commodore-amiga-supported-175) | the Amiga (`retrorecomp/systems/amiga.py`, its status) | none (the interface strings are in no stamp) | the Amiga key moves, as between any two Amiga builds |
| [Commodore Amiga: its paths are shared, as the experimental tier of the base](#commodore-amiga-its-paths-are-shared-as-the-experimental-tier-of-the-base-175-g16) | the Amiga (`amiga_knowledge.py`, `amiga_conversion.py`, its profile) and the X68000 (`knowledge.received` in its report) | none | the Amiga key moves, as between any two Amiga builds; the X68000 key does not |
| [Mega Drive and Super Nintendo: an interface change no longer refuses the quick states](#mega-drive-and-super-nintendo-an-interface-change-no-longer-refuses-the-quick-states-175) | the Mega Drive, the Super Nintendo, the Neo Geo, the CPS-1, the CPS-2, the PC Engine and the PlayStation (`console16_state.py`); nothing a game runs changes | none | Mega Drive and Super Nintendo keys move once; the 1.7.4 keys are accepted (Windows and Linux) |
| [68000 computers: the shared paths' common part cut out of the X68000's module](#68000-computers-the-shared-paths-common-part-cut-out-of-the-x68000s-module-175) | the X68000 (`m68k_media_knowledge.py` joins its game inputs); its outcomes do not change | none | none |
| [Every machine: row icons in the menus, Quick save and Quick load on the gamepad](#every-machine-row-icons-in-the-menus-quick-save-and-quick-load-on-the-gamepad-175) | none | host of all 20 profiles | the Amiga, Atari ST and Nintendo 64 keys move (every input, the host's included); the Mega Drive and Super Nintendo keys do not, once they keep only the layout files (spec/state-key-175) |
| [Every machine: a machine's own row on a player's gamepad page](#every-machine-a-machines-own-row-on-a-players-gamepad-page-175) | none | host of all 20 profiles | the Amiga, Atari ST and Nintendo 64 keys move (every input, the host's included); the others do not |
| [Atari ST: its paths are shared, as the experimental tier of the base, and the checks toward leaving the experimental status](#atari-st-its-paths-are-shared-as-the-experimental-tier-of-the-base-175-g16-and-the-checks-toward-leaving-the-experimental-status) | the Atari ST (`atarist_knowledge.py`, `atarist_conversion.py`, `atarist_disk.py`, its profile) | none | the Atari ST key moves (it takes every input of the machine) |
| [Atari ST: a key held at F8 and let go before F9 no longer stays down](#atari-st-a-key-held-at-f8-and-let-go-before-f9-no-longer-stays-down-175-gate-g6) | the Atari ST (`atarist_hatari.py`) | the Atari ST (its adapter `rrhk_atarist.inc`) | the Atari ST key moves (it takes every input of the machine) |
| [Atari ST: supported](#atari-st-supported-175) | the Atari ST (`retrorecomp/systems/atari_st.py`, its status) | none | the Atari ST key moves (it takes every input of the machine) |
| The converter window keeps one dismiss binding per window for its hover hints (Linux: choosing a console 0.6-2.6 s to about 45 ms, closing the options up to 3.6 s to about 170 ms on a 4-core Debian 13 PC; no section of this page; merge `e9be9d44`) | none (`tooltips.py`, interface code) | none | none |

## Commodore Amiga: the second joystick on port 1 (1.7.5)

On a real Amiga a two-player game takes the mouse out of port 1 and a second joystick in (Lotus 2's split screen, Speedball 2). Arthur's
proposal, approved on 14 November 2026 (« Oui, on valide »), for 1.7.5:

- **Port 1 follows the device used last**, as vAmiga's own ports do: player 2's pad plugs the joystick into port 1, a motion or a click of
  the mouse plugs the mouse back. A plate says which device the port holds, in the five languages of the games. Nothing changes for a game
  where player 2's pad is not used: port 1 stays the mouse, as before.
- **Mouse port**, a row at the top of player 2's pad page (the shell's row and icon, by the interface specialist), keeps the port on one
  device for a game that needs it: Auto (the default), Mouse or Pad 2, kept per game in the game's own `port1.cfg`. The adapter's calls are
  `a_port1_mode`, `a_set_port1_mode` and `a_port1_device` (`rrhk_amiga.inc`); F2 offers two players' pages.
- **The session** (`rr_amiga_joystick2`, `rr_amiga_port1_mode`, `rr_amiga_port1_device`) keeps its own copy of the device port 1 holds:
  vAmiga's is private and its snapshot does not keep it. A quick state carries it with the second joystick's bits, in the header's field that
  was reserved (`RRAMIGA-STATE-4`, still 200 bytes; a state whose field holds other bits is refused).
- **Routes.** The headless player reads `joy2` events (port 1's joystick) and takes `--port1`. `amiga_conversion.ROUTE_PLAYER2` makes the
  main route of the installs it lists their two-player route (reviewed data by SHA-256); Lotus 2's chooses two players in its menu and races
  split-screen. No other install's route changes, so their traces do not either.
- **A held button survives F9** (an older flaw, every Amiga build before this one). vAmiga's joysticks and mouse buttons come back neutral
  from a snapshot, and the next frame's inputs, unchanged, did not press them again: a state saved with a button held (Lotus 2's race, fire
  held to accelerate) continued with it released (three bytes of slow RAM differ one frame after the load, the fire bit). Found by this
  proof, reproduced on the export of 13 November in a one-player race. After the load the session presses again, from neutral, what was held
  (port 2's joystick, port 1's, the mouse buttons), then plugs port 1 as saved. The panel's G6 had passed because nothing was held at its save.
- **Proof** (Lotus 2, this branch): the two-player route equals the fresh reference on every frame, the compressed copy too, and the quick
  state saved in the race (port 1 on the joystick, both players accelerating) continues for 600 frames in a fresh process; a state saved in
  the race and reloaded continues the saved timeline in the three cases tried (two players with and without player 2's inputs, one player);
  the adapter's checks pass in `tests/amiga_menu_harness.c` (34).

**Hot path:** two calls a frame (port 1's joystick and the mouse), each a comparison when nothing changes.

**What moves:** the Amiga's game stamp (the session, the player, the conversion) and its host stamp (the adapter); no other machine.

**Quick states:** every Amiga state is refused (`RRAMIGA-STATE-4`), as between any two Amiga builds.

## Game Boy Advance: the sound is compared, the quick state has a checksum, a save larger than its chip is set aside, the report names its units (1.7.5)

**What changes.**
- **The sound is part of the conversion's verdict** (gate G4). Three anchored patches of the engine (`docs/UPSTREAMS.md`, 55 patches in all) make the mixer keep a hash of every sample it produces; the
  probe's snapshot line prints it with the count, and the native run is compared with the interpreter's on it, next to the picture, the cycles and the memory and CPU hashes. None of the three touches what
  a path names: the shared paths, their key and the site's limits do not change.
- **The quick state is wrapped in a checksum** (gate G6). The player writes the engine's state inside the envelope the Z80 machines and the MSX share (`native/state_envelope.h`, already an input of every console: a magic, a schema, the game's SHA-256, a length and a CRC-32; no envelope of its own) and refuses a file damaged anywhere; a state of an earlier build
  has no envelope and is **refused cleanly** with a message, nothing else is lost.
- **A save file larger than the chip is set aside** (gate G7). The engine refused such a file and the game did not open (exit code 1); the player now moves it to `<file>.damaged` and starts without a save. A smaller or damaged file
  of the right size is read as before. The header of the player names the chip's largest save (`RR_GBA_SAVE_LIMIT`).
- **The report** (gate G2) names the picture processing unit and the sound unit as hardware devices, carries `route_warnings` and the qualification scope, and its rows give the sound hash and sample count of each scenario.
- **A batch of two conversions builds a new recompiler one after the other** (a lock file in `.deps`): two builds in one folder broke the second one's configuration.
- **Test switches of the player** (never read in play): `RETRORECOMP_GBA_SHOTS` and `RETRORECOMP_GBA_SHOT_DIR` write the picture of chosen frames; the tools `gba_route_captures.py` and `gba_fresh_process.py damaged-saves` use them.

**Hot path:** no. The player does one `getenv` per switch at start; the sound is hashed only when the rows file is asked for, and the state envelope is written and read at F8 and F9 only.

**What moves:** the Game Boy Advance **game** stamp only (`f65705900b6a` on the tree of 13 November, `e6e3909337ce` on this branch: `native/gba_machine.cpp`, `retrorecomp/gba_patches.py`, `gba_build.py`, `gba_conversion.py`, `gba_player.py` and
`systems/gba.py` are game inputs). The Game Boy Advance host and build stamps (`3f8e2ffea164`, `6b70933a9b0a`) and **every other console's stamp** are those of main (compared with main `19ad2cb8`: only that one differs).
**Existing exports:** the game stamp moves, so an export is converted again in full at its next conversion, from the player's own paths (the machine is experimental and its exports are private; no frozen legacy stamp). **Site limits:**
unchanged (the record, its key and `PATH_REVISION` do not move; the pinned-patch test passes).

## Commodore Amiga: supported (1.7.5)

**Status.** The Amiga is supported from 1.7.5, on the owner's decision of 14 November 2026 after his play test of six installs (G14, the
owner-acceptance table of [QUALIFICATION.md](QUALIFICATION.md#owner-acceptance); [AMIGA.md](AMIGA.md#leaving-the-experimental-status-14-november-2026)).
The profile's status is `supported`, the Options note loses "(experimental)" in the eight languages and the credits no longer mark it. Nothing a
conversion does changes.

**What moves:** the Amiga's game stamp only (`retrorecomp/systems/amiga.py` holds the status; `compilation_inputs.role_stamps` against `efdc0585`).
The 1.7.5 update handles it as for the PC Engine and the MSX: the delivered exports are not converted again.

**Quick states:** the Amiga's key moves, as between any two Amiga builds.

## Mega Drive and Super Nintendo: an interface change no longer refuses the quick states (1.7.5)

The quick-state key of the two consoles hashes the files that fix the state layout only (`console16_state.state_layout_files`): the
console's listed native files minus the host role (the player shell: menus, fonts, options, display and audio output). Until 1.7.4 every
interface change moved it and refused the players' states. The list and the reason are in
[GAME_STATES.md](GAME_STATES.md#mega-drive-and-super-nintendo-the-key-hashes-the-layout-files-only-175).

- **Quick states:** the key moves once in 1.7.5, and the 1.7.4 key of the build's target is accepted (`RR16_STATE_COMPAT_ABI`; Windows,
  `linux-x86_64`, `linux-arm64`, computed by the same function as the build's key from the files of the v1.7.4 tag, the Windows values
  equal to the keys real 1.7.4 builds wrote): the layout files are byte for byte those of 1.7.4 for both consoles; a state saved by a 1.7.4
  Sonic 2 and Super Mario World (Windows) loads in the 1.7.5 build and continues with the same hashes as in 1.7.4 for 300 frames.
- **Stamps** (`tools/std_baseline.py`, tree `efdc0585` against this one): the game stamps of the Mega Drive, the Super Nintendo, the Neo Geo,
  the CPS-1, the CPS-2, the PC Engine and the PlayStation move (`retrorecomp/console16_state.py` is one of their game inputs); no host or build
  stamp. Nothing a game runs changes.
- **Not changed:** `compilation_inputs.state_native_files` (the full owned list) and the Master System / Game Gear build signature that uses it;
  the CPS-1, Neo Geo, PC Engine and PlayStation keys (explicit lists of their own).

## Commodore Amiga: its paths are shared, as the experimental tier of the base (1.7.5, G16)

The Amiga joins `path_profiles.SHARED_SYSTEMS` as the X68000 did: schema 3 records only, qualified per engine revision, withdrawable in one line
(`EXPERIMENTAL_SHARED`). `retrorecomp/amiga_knowledge.py` binds the common part (`m68k_media_knowledge`) to the Amiga's names.

- **What a path is.** A run of instructions a fresh reference run observed in RAM, found as it is in the install's media (the slave, then the
  files the slave may load by name, each padded to an even length): a row `[address, offset, length]`. A Kickstart instruction whose words are
  the image's: a row of the player's 256 KiB Kickstart, valid only for an image of that SHA-256. Numbers only. Code a game unpacks or relocates
  is not in the files: it stays private and is counted (`knowledge.promotion` in the report).
- **What a conversion does with received paths.** It rebuilds the instructions from the player's own archive (and Kickstart), checks them like
  an observation file, and makes them native next to its own; they are never added to the observations the library keeps. The routes then
  validate the game as always. A failure with imported paths is converted again without them (the batch, as for every machine); one with the
  player's own record is converted again without it, like the remembered observations. The quick check from shared paths is declined
  (`quick_check_from_shared=False`): a first conversion runs its own routes.
- **What it keeps.** The record of its fresh reference runs (never the player's F12 record, the remembered observations or the received
  paths), merged with the install's earlier one, in `<library>/amiga/<archive SHA-256>/paths-record.json`; the report names it
  (`knowledge.record_sha256`), which is what the sharing checks before sending it.
- **Engine identity.** `amiga_knowledge.engine()` hashes the vAmiga pin, the native files that run the steps and `GENERATOR_REVISION` (1),
  which tests/amiga_generator_pins.json ties to the generator's Python sources (`amiga_codegen`, `amiga_translate`, `amiga_vamiga`,
  `m68k_observed`): editing one of them fails that test until the revision is raised.
- **Schema.** In the Amiga's profile, its path sources become `install` and `kickstart` (256 KiB) and its windows gain the Kickstart's
  ($FC0000-$FFFFFF). Its layout stays empty, as the Game Boy Advance's (no format number of its own): a branch of `path_profiles` for it would
  move every machine's game stamp. `amiga_knowledge.RECORD_RULES` states the rest for the site's builder; the common part refuses a media of
  an odd size.
- **The player observes 12-byte windows.** The common part takes one instruction's words; `m68k_media_knowledge.exact` cuts each Amiga window to
  the instruction it starts with before a path is made or compared (the first proof conversions promoted nothing without it).
- **Proof and decision** (14 November 2026, [AMIGA.md](AMIGA.md#shared-paths-175)): a receiver of another player's paths for Lotus 2, Lemmings and
  Another World passed with one pass, the same interpreted counts and wall time as a control with nothing imported, and a few hundred instructions
  made native by the paths alone. The owner decided that the Amiga shares (« Oui, partage direct »).
- **Stamps** (`compilation_inputs.role_stamps`, this change against `01d1d7d1`): **the game stamps of the Amiga and the X68000** (the X68000 for
  `knowledge.received` in its report, below); no host or build stamp; no quick-state key.
- **What the received paths gave: `knowledge.received`**, the same field on the three 68000 computers (the Amiga, the X68000 from this release, the
  Atari ST when it shares): `offered` (instructions rebuilt from received paths), `reached` (those this conversion's own fresh reference runs ran
  too, so validated on its routes) and `added` (made native only because a path named them: their guard checks them when a player reaches them).
  Computed by the conversion (`m68k_media_knowledge.received_use`), no counter in the players. The common report carries it inside
  `knowledge.record` as it carries `knowledge.use`; no window shows either. The X68000's records do not change: only its report gains the field.

## 68000 computers: the shared paths' common part cut out of the X68000's module (1.7.5)

The Amiga and the Atari ST share their paths like the X68000: RAM code tied to positions in the player's own media, firmware instructions tied to the
player's own firmware image (the IPL, the Kickstart, the TOS). The code that does it was the X68000's (`x68_knowledge.py`); it is now
`retrorecomp/m68k_media_knowledge.py`, one `MediaKnowledge` per machine, and nothing in it names a machine.

- **What is common.** The word-count table, the search of runs of observed instructions in the media, the records (make, validate, merge,
  rebuild, entry set), promotion, the expansion of received paths from the player's own images, the guidance of the three banks and the player's
  library record.
- **What stays the X68000's** (`x68_knowledge.py`): its names, bounds, windows and the words of its refusals, its engine identity
  (`engine_core`, `GENERATOR_REVISION`), its disk content, the IPL as the machine maps it and which observed IPL entries become rows.
- **Identical results.** `tests/test_m68k_media_knowledge.py` runs twelve deterministic scenarios through every function of the X68000 module
  (records, counts, merges, rebuilds, expansions, the guidance a conversion receives, every refusal's words) and pins the SHA-256 of all outcomes,
  computed on the module before the cut (`9f9e9ce9`): it holds. `tests/test_x68_knowledge.py` passes, with one test now lowering the bound on the
  common part. The engine identity does not move, so every X68000 path qualified for its engine stays qualified.
- **Stamps** (`compilation_inputs.role_stamps`, this branch against `9f9e9ce9`): **the game stamp of the X68000 only** (the new module is in its
  inputs, the group `shares:m68k_media_knowledge`); no host or build stamp; no quick-state key. An X68000 export of 1.7.4 is converted once in full,
  with the same result.

## Atari ST: its paths are shared, as the experimental tier of the base (1.7.5, G16), and the checks toward leaving the experimental status

The Atari ST joins `path_profiles.SHARED_SYSTEMS` (Arthur, 14 November 2026: «Oui, il partage»): schema 3 records only, qualified per engine revision, withdrawable in one line (`EXPERIMENTAL_SHARED`).
`retrorecomp/atarist_knowledge.py` binds the common part (`m68k_media_knowledge`) to the Atari ST's names.

- **What a path is.** A TOS instruction: a row `[address, offset, length]` of the player's 192 KiB TOS, valid only for a TOS of the SHA-256 the record states. A run of instructions a fresh reference run
  observed in RAM and found as it is in the **logical content** of the disks (the standard-format sectors of every image, in (cylinder, side, sector) order, `atarist_disk.logical_content`): a row of that
  content. Numbers only. Code a loader relocates or unpacks, custom-format tracks, STX images and Hatari's own code of the desktop hook stay private and are counted (`knowledge.promotion`). The game is the
  SHA-256 of the file the player gave.
- **What a conversion does with received paths.** It rebuilds the instructions from the player's own images, makes them native next to its own (never added to the observations the library keeps), and the
  routes validate the game as always. A failure with imported paths is converted again without them (the batch, for every machine). The quick check from shared paths is declined. The report's
  `knowledge.received` (`offered`, `reached`, `added`, computed by `m68k_media_knowledge.received_use`, no counter in the player) is the field of the X68000 and the Amiga.
- **What it keeps.** The record of its fresh reference runs, in `<library>/atarist/<game>/tos-<key>/compilation.json` (one per TOS, united by `library_record`); the report names it
  (`knowledge.record_sha256`). **Engine identity:** `atarist_knowledge.engine()` hashes Hatari's pin, the four native files that run the steps and `GENERATOR_REVISION` (1), which
  `tests/atarist_generator_pins.json` ties to `atarist_codegen.py` and `atarist_hatari.py`.
- **Schema.** The layout stays empty, as the Amiga's and the Game Boy Advance's: `path_profiles` is not edited (a branch for it would move every machine's game stamp), so the record carries no format
  number of its own. `atarist_knowledge.RECORD_RULES` states the rest for the site's builder. The profile's sources were already `disk` and `tos`.
- **What it gives** (measured on Operation Stealth, The Lurking Horror and Turrican II, [ATARI_ST.md](ATARI_ST.md#2-how-the-conversion-works) item 9): no conversion pass saved (1 and 1), nothing
  changed on the routes the receiver runs, native code added beyond them (Turrican II: 30,455,168 interpreted instructions on a route the receiver did not run, 2,920,653 with the paths received; the two
  others within 1 % and 8 %); the speed value is not measured.
- **Also in this change**, none of it in a game: `tools/atarist_saves_game.py --exe` runs the save of The Lurking Horror on a delivered executable (G7); five risk cases for the Atari ST in
  `tools/campaign-risk-cases.json`; the owner's play checklist for seven games ([QUALIFICATION.md](QUALIFICATION.md#checklist-for-arthur-atari-st-play-test-g14)); `atarist_disk.logical_content`
  (all tracks of an IPF, where the desktop rules read two cylinders).
- **Stamps** (`compilation_inputs.role_stamps`, this branch against main `19ad2cb8`, `RetroRecomp.py` tree of each): **the game stamp of the Atari ST only** (`f414185b00f5` to `08644c6cc052`; its inputs are
  `atarist_knowledge.py`, `atarist_conversion.py`, `atarist_disk.py`, its profile and the group `shares:m68k_media_knowledge`); no other machine's game stamp, no host or build stamp, no native file, no
  quick-state key. An Atari ST export of 1.7.4 is converted once in full, with the same result on the routes; the seven games delivered for the owner's play were built one merge before the last
  (which added the function `exact` to `m68k_media_knowledge.py`, unused by the Atari ST): they carry the stamp before it.

## Atari ST: supported (1.7.5)

On the owner's decision of 14 November 2026 (the owner-acceptance table of [QUALIFICATION.md](QUALIFICATION.md#owner-acceptance): « Oui, sors-le », after his play test of seven games), the Atari ST is
supported from 1.7.5; it opened as experimental in 1.7.1. The status lives in `retrorecomp/systems/atari_st.py`, which is an input of the Atari ST's game stamp, so the change moves that stamp once more (with
this release's other Atari ST changes); the 1.7.5 update handles it as for the PC Engine, the MSX and the Amiga, and the delivered exports are not converted again. The Options note loses "(experimental)" in
the eight languages (`options_atarist_note`) and the credits no longer list the Atari ST among the experimental machines; nothing else of the converter changes.

**Stamps** (`compilation_inputs.role_stamps`, this branch against main `6e4d6d1d`): **the game stamp of the Atari ST only** (`b5cfd4de57c4` to `6116a5b0bb28`); no other machine, no host or build stamp, no quick-state key.

## Atari ST: a key held at F8 and let go before F9 no longer stays down (1.7.5, gate G6)

**What was wrong.** The host sends the guest's keys as changes only. A typed key held when F8 saved the state and released before F9 loaded it was released in the old machine, then
the load brought back a snapshot that holds the key down: the key stayed down in the guest (The Lurking Horror: from the first frame after the load, 0 of 500 frames equal the timeline in which the
key was let go). A key still held at F9 but not at F8 was never pressed again (the host had already sent its press). The pad, the fire button and the mouse buttons are read again every frame and come
back right (checked on Bomb Jack: held and still held, held and released, pressed after, 300 of 300 frames equal the timeline each time, against a control where the holds change it).

**What changes.** After Hatari's restore (the adaptation of `memorySnapShot.c` in `retrorecomp/atarist_hatari.py`), every key that `Keyboard.KeyStates` shows as down gets its break code, as the host
had sent it before the load. In the host adapter (`native/hostkit/adapters/rrhk_atarist.inc`), a state load makes the adapter wait three frames (Hatari restores inside the next frame) and then forget what
it had sent, so the keys still held are pressed again. `tools/atarist_keys_check.py` runs the check on executables a conversion delivered (`--pad` on Bomb Jack, `--keys` on The Lurking Horror). **Results on the fixed build** (14 November 2026, Windows, Bomb Jack
and The Lurking Horror converted from this branch at the quick level, headless): the pad cases still 300 of 300 frames equal the timeline each (control: the holds change it), and the key held at F8 and
released before F9 **500 of 500 frames equal the timeline** (the 1.7.4 build, the same check: 0 of 500; the same check with no key held: 500 of 500).

**Stamps** (`compilation_inputs.role_stamps`, this branch against main `6115b82d`): **the Atari ST game stamp** (`08644c6cc052` to `b5cfd4de57c4`: `atarist_hatari.py` is one of its inputs) **and its host
stamp** (`ef245155bc7c` to `fd8405ed4de4`: the adapter); no other machine, no build stamp, no quick-state key (a state is tied to the build that wrote it and is refused between builds, as after any reconversion). **The engine identity of the shared
paths does not move** (`atarist_knowledge.GENERATOR_REVISION` stays 1): the generated native code and the guards are the same, so no path qualified for it waits again; `tests/atarist_generator_pins.json`
follows the new text of `atarist_hatari.py`, the one thing that test pins. The seven games delivered for the owner's play keep their stamp: the fix only touches a key held across F8.

## MSX and MSX2: the mapper probe of battery-backed boards, the exit panel and the exit from the experimental status (1.7.5)

**What changes.** The mapper probe of an ASCII cartridge runs the reference with a blank SRAM behind every bank value past the cartridge
(`--sram-probe` of `msx_reference_main.c`): the game's writes to that SRAM are counted apart (`sram_writes`) instead of as writes the cartridge
would ignore, and one register write is no longer evidence when another candidate's run made two (`msx_build.choose_mapper`). Deep Dungeon
(ASCII 8, 2 KiB SRAM) was read as ASCII 16 and Super Daisenryaku (ASCII 16, 2 KiB SRAM) as ASCII 8; both convert with their own mapper now,
and the sixteen other cartridges probed keep their choice. Five risk cases each for the MSX and the MSX2 join `tools/campaign-risk-cases.json`,
and the campaign's MSX share folder is `msx1`. Path sharing is declined for the MSX and the MSX2 (`DECLINED['path_sharing']`; the evidence is in
[MSX.md](MSX.md#7-where-it-stands-in-the-qualification)), so nothing of the base changes for them. The MSX2 profile's note says its clock's battery
memory is not kept.

**Hot path:** none; the probe runs before the conversion, on the reference only.

**What moves:** the MSX, MSX2 and MSX2+ game stamps (`msx_build.py`, `msx_conversion.py`, `msx_reference_main.c`, `systems/msx.py`). No other
machine's stamp moves (checked against `v1.7.4` and main with `RetroRecomp.py _compilation-stamps`). A previous export of an ASCII cartridge whose
probe now chooses another mapper was built with the wrong one: convert it again (Deep Dungeon and Super Daisenryaku among the panel's).

**Status.** The MSX and the MSX2 are supported from 1.7.5, on the owner's decision of 14 November 2026 after his play test (the owner-acceptance
table of [QUALIFICATION.md](QUALIFICATION.md#owner-acceptance)); the MSX2+ stays experimental. The status lives in `retrorecomp/systems/msx.py`,
which the three profiles share, so the change moves the MSX, MSX2 and MSX2+ game stamps once more; the 1.7.5 update handles it as for the PC
Engine, and the delivered exports are not converted again. `tools/status_lint.py` no longer reads the page name `MSX.md` in a link as the
MSX (the three profiles share their page).

**Quick states:** the layout is unchanged (`msx-state-5`).

## Every machine: a machine's own row on a player's gamepad page (1.7.5)

The shell gains `RrhkMachine.pad_rows` ([HOST_KIT.md](HOST_KIT.md#d22), D22): rows of a machine at the top of one player's
gamepad page. The Amiga's Mouse port row uses it (its adapter, on the Amiga's own branch); no other machine declares one.

* **Stamps.** The host stamp of all 20 profiles moves (`hostkit/hostkit.h`, `hostkit/hostkit_internal.h`, the shell's
  `rrhk_menu.c`, `rrhk_events.c`, `rrhk_input.c`, `native/retro_menu.c` and `retro_menu.h` for the two port icons,
  `runtime_catalog.inc` and the seven locale files); no game or build stamp, no quick-state key (none of these files fixes a
  state layout).
* **What players see.** Nothing on a machine without a row; on the Amiga, once its adapter declares it, the Mouse port row.
* **Texts.** Four new entries in the five game languages: "Mouse port", "Auto (last used)", "Mouse", "Pad 2".
* **Checks.** `tools/hostkit_capabilities_selftest.py` run 8: the row on player 2's gamepad page only, values chosen and wrapped,
  the controls below it still bound by F2 (271 checks).

## Every machine: row icons in the menus, Quick save and Quick load on the gamepad (1.7.5)

The player shell changes on every machine at once ([HOST_KIT.md](HOST_KIT.md#d20), decisions D20 and D21): each row of the
control, options and graphics pages has its icon, and player 1's gamepad page binds Quick save and Quick load.

* **Stamps.** The host stamp of **all 20 profiles** moves; no game stamp and no build stamp moves, so every export of 1.7.4 is
  upgraded without rediscovery. Files: `native/retro_menu.c`, `retro_menu.h`, `game_options.h`, `game_options_checks.c`,
  `runtime_catalog.inc`, `hostkit/hostkit.h`, `hostkit/hostkit_internal.h` and the shell's `rrhk_main.c`, `rrhk_menu.c`,
  `rrhk_options.c`; the seven locale files. Adventure (ScummVM) is among them because its profile lists the shared host files,
  although its games do not link the kit: nothing changes in them.
* **What players see.** An icon before every row of F2's control pages, the options page and the F3 graphics page; on player
  1's pages two rows more, **Quick save** and **Quick load** (F8 and F9 on the keyboard page). A control page with more than
  fifteen rows scrolls, as since 1.7.0.
* **Quick states.** The shell's change moves nothing in a state. The Mega Drive and Super Nintendo keys hashed every listed
  file directly below `native/`, the menus' included; spec/state-key-175 makes them hash only the files that fix the state
  layout, so that this section moves no key. Measured against that main before merging.
* **Preferences.** Two keys added, `[<Console>.Options] quick_save_pad` and `quick_load_pad` (button masks, missing =
  unassigned): a file of 1.7.4 loads unchanged. An export of 1.7.4 reading a file written by 1.7.5 ignores them.
* **Texts.** Six new entries in the catalogue of the five game languages (and in the seven locale files): "Quick save", "Quick
  load", their two hold hints, "Already used by %s" and "F8 and F9: fixed keys".
* **Triggers.** L2 and R2 (axes in SDL) count as buttons in the four combinations, alone or with others, with a hysteresis
  (pressed past 16000, released under 8000); the shell's game rows and speed controls read them through the same function. A
  trigger used by a combination is no longer a speed control. Masks keep the triggers in bits 24 and 25. A game control
  may be bound to L2 or R2 on every machine (until 1.7.4, the PlayStation and the Nintendo 64 only): F2 captures it, the
  preferences keep it (`RRHK_PAD_LEFT_TRIGGER` 64, `RRHK_PAD_RIGHT_TRIGGER` 65, as before), play reads it with the same
  function; a trigger bound to a control is no longer a speed control, an unbound one still is.
* **Per-frame cost.** Two more combination checks per frame, beside Quit and Restart (mask comparisons on player 1's pad); not
  measured on its own, covered by the release's frame-cost comparison.
* **Checks.** `tools/game_options_selftest.py` (defaults, fixed keyboard rows, refusal, the two holds once each, persistence)
  and `tools/hostkit_capabilities_selftest.py` (247 checks: binding on a virtual pad, refusal, save and load held in play,
  nothing inside a menu, a control page of 24 rows), with the portable toolchain.

## Exports of 1.7.3 in 1.7.4

1.7.4 is the release after 1.7.3 (published on 13 November 2026). This section is the index of its changes, one line per section below (or per page when a change has no
section here), with the stamps that section says move. Each section computed its stamps for its own change alone, on the tree of its branch; the totals are under the table and were
computed on `main` on 13 November 2026 (`ddfeb018`).

| Change | Game stamps that move | Host and build stamps | Quick states |
| --- | --- | --- | --- |
| [68000 machines: the decimal instructions follow Moira on every operand](#68000-machines-the-decimal-instructions-follow-moira-on-every-operand-174) | the Mega Drive, the Neo Geo, the CPS-1, the CPS-2 and the X68000 (their generated code changes; `GENERATOR_REVISION` of the CPS-1 and the X68000 raised) | none | **the X68000 key moves** (it hashes the generated `m68kcpu.c`); the others do not |
| [Mega Drive: what the report says](#mega-drive-what-the-report-says-174-gates-g2-and-g15) | the Mega Drive, the Super Nintendo, the Neo Geo, the CPS-1, the CPS-2, the PC Engine and the PlayStation (`console16.py`) | none | none |
| [Every machine: the menus drawn again, F2 as tiles, "Quit?", the opening plates and a stretched F4 mode](#every-machine-the-menus-drawn-again-f2-as-tiles-quit-the-opening-plates-and-a-stretched-f4-mode-174) | none | **the host stamp of every profile** (the host kit's shell, `retro_menu.c`, `game_options.h`, `runtime_catalog.inc`, `display_settings.h`) | **the Mega Drive and Super Nintendo keys move** (they hash `retro_menu.c`, `retro_menu.h`, `game_options.h`, `runtime_catalog.inc`), and the Amiga, Atari ST and Nintendo 64 keys (every input, the host's included); the others do not |
| [MSX2+: a third profile of the MSX family, with the V9958](#msx2-a-third-profile-of-the-msx-family-with-the-v9958-174-experimental-step-1) | the MSX and the MSX2 (their files); the MSX2+ is new | none | **the MSX and MSX2 states are refused** (layout `msx-state-4`) |
| [MSX2+: disk games](#msx2-disk-games-174-experimental-step-2) | the MSX, the MSX2 and the MSX2+ (`msx_fdc.c`, `msx_disk.py`) | none (`rom_sources.py` is in no stamp) | **the MSX and MSX2 states are refused** (layout `msx-state-5`) |
| [MSX and MSX2: the cartridge's battery SRAM is kept, the common report has the counts](#msx-and-msx2-the-cartridges-battery-sram-is-kept-the-common-report-has-the-counts-174) | the MSX and the MSX2, and **every machine that uses `conversion_gates.py`** (all but the Super Nintendo, the Game Boy Advance and ScummVM); the PC Engine's own conversion; no other game changes | none | **the MSX and MSX2 states are refused** (layout `msx-state-3`, the SRAM), and the Amiga, Atari ST and Nintendo 64 keys move (every input); the others do not |
| [Game Boy Advance: the delivered file is replayed against the player as built, the player can write a row per frame, a heal count in the report](#game-boy-advance-the-delivered-file-is-replayed-against-the-player-as-built-the-player-can-write-a-row-per-frame-a-heal-count-in-the-report-174) | the Game Boy Advance only | none | no key of ours: a state is the engine's own container; a state of a game converted before may be refused |
| [Atari ST: the root of a disk is read as the TOS reads it, two names more among the utilities, the interpreted instructions listed by address, the known stops in the report](#atari-st-the-root-of-a-disk-is-read-as-the-tos-reads-it-two-names-more-among-the-utilities-the-interpreted-instructions-listed-by-address-the-known-stops-in-the-report-174) | the Atari ST only | none | the Atari ST key moves |
| [Commodore Amiga: route scripts in LF on every system, the long route's script digest in the report](#commodore-amiga-route-scripts-in-lf-on-every-system-the-long-routes-script-digest-in-the-report-174) | the Amiga only | none | the Amiga key moves, as between any two Amiga builds |
| [Commodore Amiga: Another World and Lemmings answer their first screen; every route of such an install starts with the answer](#commodore-amiga-another-world-and-lemmings-answer-their-first-screen-every-route-of-such-an-install-starts-with-the-answer-174) | the Amiga only (the routes of Another World, Lemmings and Monkey Island 2 change) | none | the Amiga key moves, as between any two Amiga builds |
| [Commodore Amiga: quick states carry a checksum and the install's identity; damaged ones are refused](#commodore-amiga-quick-states-carry-a-checksum-and-the-installs-identity-damaged-ones-are-refused-174-g6) | the Amiga only | none | **every Amiga state is refused** (format `RRAMIGA-STATE-3`) |
| [Sharp X68000: a game opened through a linked folder starts](#sharp-x68000-a-game-opened-through-a-linked-folder-starts-174) | the X68000 only (`payload.c`, `media_session.c`, `tools/x68000_reference.py`) | none | none (the key hashes neither file) |
| [Sharp X68000: a game that asks for its system disk again gets it back](#sharp-x68000-a-game-that-asks-for-its-system-disk-again-gets-it-back-174) | the X68000 only (`media_session.c`, `media_session.h`) | none | the X68000 key moves (`media_session.h`), as it already does in 1.7.4 |
| The converter window on Linux: a context menu closes when you click elsewhere (no section of this page; commit `e2512ecc`) | none (interface code) | none | none |
| The Mega Drive's native test harnesses link with the portable toolchain, Visual Studio only as a fallback (no section of this page; merge `8f0c85c9`) | none (tools) | none | none |
| Licences: the m68k-recomp-core author's permission for the Atari ST in `licenses/` and the third-party notices (no section of this page; commit `71c6acec`) | none (embedded in no game; `stamp_inputs.NOT_INPUTS`) | none | none |
| Tests: two failures seen only in the public CI of 1.7.3 (no section of this page; commit `96a70fa0`) | none | none | none |
| Qualification: the letters of the MSX, MSX2, MSX2+, Atari ST, Mega Drive, Game Boy Advance and Amiga columns ([QUALIFICATION.md](QUALIFICATION.md); no section of this page) | none | none | none |

Taken together (`compilation_inputs.role_stamps` of the twenty profiles, the tree of `v1.7.3` against `main`, Windows, Python 3.14): **the game stamp of every
profile but Adventure (ScummVM) moves**: the Master System, Game Gear, Game Boy, NES, Nintendo 64 and PlayStation through `conversion_gates.py` (and the PlayStation through
`console16.py`), the others through their own changes as well; **the host stamp of every profile moves**, with the new in-game interface; **no build stamp moves**. The MSX2+ is new.

| Machine | Game stamp (v1.7.3, now) | Host stamp | Build stamp |
| --- | --- | --- | --- |
| Master System | `0f2ae3577f5f`, `da7740751f6c` | `afcd7d80d268`, `9c85ab2c271f` | `fe2d99b3cd5e` (same) |
| Game Gear | `f6156c79361a`, `5659d9208ad1` | `1a50c71be834`, `207706f2e7e6` | `f5671c38cf26` (same) |
| Game Boy | `fda8a848fcba`, `4a7ee6ffd023` | `b0c6d1f25dcb`, `b5b3db390890` | `819a054ad881` (same) |
| NES | `d003f9637777`, `0766ec8cacdf` | `aace3c47c69a`, `d104374c07dd` | `8e0941f93b43` (same) |
| Mega Drive | `fcf472f6e2b0`, `99b2890365d8` | `ae954d97ef21`, `51731b499338` | `9615ff2e96c8` (same) |
| Super Nintendo | `830816cf1a5d`, `70b9bd7f54b0` | `1338832835c7`, `c18fd880c901` | `3f0a58ad3c7c` (same) |
| Neo Geo | `296e61d8c8b5`, `10c2a91887ed` | `209363c3cb2d`, `3fba6ce0ccc0` | `110349f043bd` (same) |
| X68000 | `6a1a3e6fffa6`, `4b3544e4c896` | `cd36f942cda8`, `f797a5fe02b9` | `5903c0449429` (same) |
| CPS-1 | `5bad58285e1e`, `d477757abcb7` | `1744a86d265c`, `b1d84d7c729a` | `2782cd370f91` (same) |
| CPS-2 | `3d06a5ebcc85`, `e87153ef3f90` | `5f073fe7a9ca`, `2d378c71769a` | `81a51ad49349` (same) |
| PC Engine / TurboGrafx-16 | `dc4e67408d8f`, `467ee58b350b` | `20772c959102`, `ee9194a1d5cc` | `66d912662e5c` (same) |
| Game Boy Advance | `20b869ddcba2`, `f65705900b6a` | `287e639d641a`, `3f8e2ffea164` | `6b70933a9b0a` (same) |
| Amiga | `f069a288af8a`, `b9c3b53105d9` | `7d590498bb06`, `ec0dd3422e72` | `92ca8a0c142c` (same) |
| Atari ST | `6c70ccd1ff7c`, `f414185b00f5` | `c1f3ab554861`, `71e4d66f2a87` | `54b75964897d` (same) |
| Nintendo 64 | `77b096906adf`, `b2f1227b519d` | `93684dc83103`, `b7e3362c659a` | `4f6fedf926c7` (same) |
| Adventure (ScummVM) | `7e79677b16a3` (same) | `2e274a46f2af`, `73f0cabdf927` | `05417bbcea96` (same) |
| Sony PlayStation | `c6a915039614`, `65cfde0bce50` | `34ac75fcabae`, `c6229c50d0ee` | `b6c9cf73b176` (same) |
| MSX | `5ad96cd2add4`, `15a037262516` | `7f3fdbbcf3d1`, `7f2e26ded315` | `3e7de8099a99` (same) |
| MSX2 | `cbb66977125c`, `2ffee6245075` | `e75758647762`, `5a5bc27e0c7c` | `d2329c8c61ad` (same) |
| MSX2+ | `8ae143afa6f8` (new) | `ccd13cd7df54` (new) | `88e08041d92f` (new) |

(First twelve hexadecimal digits of each stamp.) `LEGACY_GAME_STAMPS` stays empty. **So every export of 1.7.3 is converted again once at the upgrade**, at the quick level,
from its learned paths, and the window offers it, **except the games of Adventure (ScummVM)**, which are only upgraded (rebuilt with the new host files, no
rediscovery; they look the same, as ScummVM draws its own menus). The shared paths of the base are kept: they are qualified by the recompiler's revision, not by this stamp.

**Quick states.** The **Mega Drive and Super Nintendo keys move**: they hash their listed native files, which the new interface changes (`retro_menu.c`, `retro_menu.h`,
`game_options.h`, `runtime_catalog.inc`). The **Amiga, Atari ST and Nintendo 64 keys move**: each takes every input of its machine, the host's included; the Amiga's
state file also has a new format (`RRAMIGA-STATE-3`, with the install's identity and a checksum). The **X68000 key moves**: it hashes the generated CPU code, which the
decimal instructions change. The **MSX and MSX2 states are refused**: their layout went from `msx-state-2` to `msx-state-5` (the SRAM, the port F4h, the disk controller).
A quick state of 1.7.3 of those eight machines is refused cleanly (no compatibility key is carried, [GAME_STATES.md](GAME_STATES.md)); nothing is lost but that state. The keys of
the NES, the Neo Geo, the CPS-1, the CPS-2, the PC Engine and the PlayStation hash none of the files that changed, so their states of 1.7.3 load in the rebuilt export; the Master
System, Game Gear and Game Boy have no such key. A quick state of the Game Boy Advance is the engine's own container, with no key of ours; its section says a state of a game
converted before may be refused. The MSX2+ is new. **Cartridge saves** are kept on every machine (the MSX and MSX2 now keep the battery SRAM of their ASCII cartridges); the game
saves of Adventure (ScummVM) are ScummVM's own. A game of 1.7.3 that reads the stretched F4 mode (`display_mode` 3) written by 1.7.4 opens in a window.

## Sharp X68000: a game opened through a linked folder starts (1.7.4)

Every X68000 game, those of earlier releases included, refused to start when its folder was reached through a link (a symbolic link, a junction, a drive
letter or a library folder that points elsewhere): it stopped with "Cannot prepare private game data (linked path, changed firmware, or another running
copy)". The host checked every folder from the root of the drive down to the game's data, and refused a link anywhere on the way.

- **What is checked now.** Only the game's own data: `datas`, `games`, `x68-<identity>` and what is under them, on Windows (no reparse point) and on Linux
  (`lstat`, no symbolic link). The folders above the executable's are the player's and are never inspected; the executable already runs from there. A link
  inside the game's data is still refused, as are a hard link in place of a file and a second running copy (the lock).
- **The media session** (`media_session.c`) checks its files the same way, from the folder that holds the media folder down. The converter's staging
  (`tools/x68000_reference.py`) checks from the output folder down, so a conversion whose output sits below a linked folder works too.
- **Proof.** Twins, converted from this tree: 30 headless frames exit 0 from its folder and from the same folder reached through a drive-level symbolic link, and
  exit 1 with the same message when `datas\games` is made a junction. Tests (`test_x68000_payload`, `test_x68000_media_session`, `test_x68000_reference`) build a
  linked parent (a junction on Windows, a symbolic link elsewhere) and show the start, and keep refusing a link at `datas`, `games`, `x68-<identity>`,
  `media` and `system`; they fail on the code of `4d7f4b65`.
- **Stamps** (`compilation_inputs.role_stamps`, this branch against `4d7f4b65`): **the game stamp of the X68000 only**; no host or build stamp; the quick-state key
  does not move (it hashes `media_session.h`, not these files). Only the X68000 has this check; the other machines' runtimes refuse no link in a folder above their data.

## Sharp X68000: a game that asks for its system disk again gets it back (1.7.4)

The automatic disk policy ([X68000.md](X68000.md#automatic-disk-changes)) never offered back the disk the game had just ejected. Lagoon ejects its System disk and
asks for a user disk or the System disk again; the policy offered the three data disks, the game refused each one, and FDD0 stayed empty under the message.

- **What changes.** The ejected disk is no longer excluded: it comes last, after every other disk of the set was refused. A blink request still never takes
  the other drive's disk, and a disk refused twice still ends the request with the drive empty. Nothing changes for a request that an earlier disk answers,
  which is every request the panel's routes reached (Metal Sight, Power Unit; Choujin and Super Hang-On make none): only a request in which every other disk
  was refused is affected, and that one used to leave the drive empty.
- **Proof.** Lagoon's keyboard route, before: System ejected at frame 1968, Disk 1, 2 and 3 refused, FDD0 empty with the message at frame 2600. The same
  route with the System disk put back by hand (and no key after frame 2200) reaches play at frame 4000; with this change the policy puts it back itself.
  The authored media-session harness checks the new order (the ejected disk offered last, then the request exhausted).
- **Stamps:** the game stamp of the X68000 only (`media_session.c`, `media_session.h`); no host or build stamp. The X68000 quick-state key moves (it hashes
  `media_session.h`), as it already does in 1.7.4; the format of a pending request in a state is unchanged.

## 68000 machines: the decimal instructions follow Moira on every operand (1.7.4)

`ABCD`, `SBCD` and `NBCD` on operands that are not decimal digits are left undefined by the manual; the four 68000 machines gave
their own answer, and 22 vectors of `tests/fixtures/m68k-groups` (`ABCD` 2, `SBCD` 2, `NBCD` 18) disagreed with it. They now follow Moira
(MIT, the 68000 of vAmiga) on the result and on the five flags X, C, N, Z and V, register and memory forms, written from its behaviour in our own
code (`retrorecomp/megadrive_rules.py` state rules 4 to 8, reached by the Neo Geo, CPS-1 and X68000 native steps through
`retrorecomp/m68000_state_rules.py`; the Musashi reference of those three through `retrorecomp/musashi_fixes.py`, 20 handlers). A valid
decimal operand gives the same result as before; V, which the native steps always cleared, now takes Moira's value (no hardware test or
documented source says otherwise; the manual calls it undefined).

- **Evidence** (`tools/megadrive_moira_vectors.py` with `native/md_bcd_checks.c`, a real run of Moira, portable toolchain): every operand pair,
  X and Z of each instruction (1,050,624 states), **0 differences** on the result and the five flags, on the Mega Drive's native steps and on its
  reference path (before: 41,616, 36,864 and 704 states outside V; 4,288 to 147,776 on V alone). `m68k-groups`: **2,895 of 2,895** vectors whole on the
  Mega Drive, the CPS-1, the X68000 and the Neo Geo, native and reference alike (before 2,873); both deviation lists are empty. The vectors come
  from MAME and Moira is a software model: neither is silicon.
- **What moves:** the generated code and the **game stamps of the Mega Drive, the Neo Geo, the CPS-1, the CPS-2 and the X68000**
  (`tools/std_baseline.py`; no host or build stamp). Of the quick-state keys, only the X68000's moves: it hashes the generated CPU code
  (`m68kcpu.c`) that the Musashi fixes change; the Mega Drive, Neo Geo, CPS-1 and CPS-2 keys hash none of the files changed; `GENERATOR_REVISION` of `cps1_knowledge.py` 13 to 14 and of
  `x68_knowledge.py` 1 to 2, with `tests/cps1_generator_pins.json` and `tests/x68_generator_pins.json`. Existing exports of these five machines are
  converted again in full. A game that never runs a decimal instruction on a non-decimal digit does the same thing as before.
- **Left as listed:** the same bench found that on 16 forms with no vector (`ADDI`, `SUBI`, `ANDI`, `ORI`, `EORI` `.L` and `CMPI` on `-(An)` and
  `(d8,An,Xn)`) the Mega Drive's first read comes two clocks later than Moira's (the same total clocks and data); and that Moira writes the high word of
  a long read-modify-write first where the MAME vectors write the low word first. Neither is changed (no vector for the first, the vectors win on the
  second).

## Mega Drive: what the report says (1.7.4, gates G2 and G15)

One writer change of `retrorecomp/console16.py` and `console16_optimization.py` (commit `50ce0d5f`): the report of a Mega Drive conversion now writes
`independent_cpu_oracle: false`, a `qualification_scope` with `universal_zero_fallback_claim: false`, `cpu_agreement`, the sound and main CPU's word over
every route, `native_percentage_scope`, `native_coverage` and a closing "ready (no interpreter on the routes played | interpreter fallback reported)" line;
the per-route line gives the native side. The state schema, machine and ROM identity, the ordinary saves (supported, scope, path), two players and the
pad or gun, and the SDL revision are recorded; a field that would claim a tool proof stays empty unless this conversion ran it. The common report reads
the route hashes, the main CPU's mode and share and the build fields (`report_schema.py`, an interface module). The Super Nintendo shares the writer: its
`audio_cpu` is now the word over every route, it gains `native_percentage_scope`, and two log lines change wording. **Game stamps that move:** the Mega Drive,
the Super Nintendo, the Neo Geo, the CPS-1, the CPS-2, the PC Engine and the PlayStation (`console16.py` is one of their inputs); no host or build stamp.
The window's fallback line of the machines counted in instructions says "on the tested routes, at most" and "hardware unverified" (interface strings, no stamp).

## Every machine: the menus drawn again, F2 as tiles, "Quit?", the opening plates and a stretched F4 mode (1.7.4)

The player shell changes on every machine at once ([HOST_KIT.md](HOST_KIT.md#d15), decisions D15 to D19): F2 opens a menu
of tiles, Esc and the Quit combination ask "Quit? No / Yes", notices are plates, each game says its keys when it opens, the
menus get icons, block letters and key caps, and F4 gains a fourth mode, stretched fullscreen.

* **Stamps** (`compilation_inputs.role_stamps`, compared with main `f57eb9e3` on Windows). The files changed are host inputs
  (`stamp_inputs.HOST_NATIVE`): `native/retro_menu.c`, `retro_menu.h`, `game_options.h`, `runtime_catalog.inc`,
  `display_settings.h`, `display_settings_checks.c`, `hostkit/hostkit.h`, `hostkit/hostkit_internal.h` and the shell's
  `rrhk_main.c`, `rrhk_menu.c`, `rrhk_events.c`, `rrhk_options.c`, `rrhk_input.c`, `rrhk_video.c`, `rrhk_pointer.c`. The **host stamp moves for all twenty profiles**: sms, gg, gb, nes, md, snes, ng, cps1,
  cps2, pce, gba, amiga, atarist, n64, psx, msx, msx2, msx2plus, x68 and scummvm. **No game stamp and no build stamp moves.**
  An export of 1.7.3 is **upgraded** (rebuilt from its learned paths, no rediscovery), as for any change of the shell.
  ScummVM's games do not use the kit (their menus are ScummVM's own), but their host stamp lists the same files: they are
  upgraded too, and look the same afterwards.
* **What players see** (every machine on the kit; nothing changes in ScummVM's games): F2 opens the tiles; Esc in play and
  L3+R3 ask "Quit? No / Yes"; a plate at the bottom of the picture for about 4.5 s when the game opens (F1, F2, Esc; with a
  gamepad, its Quit and Restart combinations; on a computer, who has the keyboard), which the new **Start-up reminders** row
  of the options page turns off; F4 gains a **stretched** fullscreen mode after fit (the whole screen, the aspect ignored),
  and names each mode in a notice; notices on a dark plate; the help, control pages, options, graphics and gun pages with the
  mark, block letters, icons and key caps; gamepad buttons named as printed on a pad. The Master System, Game Gear and MSX
  adapters still post their own opening notice (2.4 s), which shows above the kit's plates until their adapters drop it
  (adapter change, not in this step).
* **Quick states of the Mega Drive and the Super Nintendo.** Their state key hashes the listed files directly below `native/`
  (`compilation_inputs.state_native_files`, read by `console16_state.write_config`), which include `retro_menu.c`,
  `retro_menu.h`, `game_options.h` and `runtime_catalog.inc`: the key moves, and an F8 state written by 1.7.3 is refused with
  the usual notice ("No compatible quick state to load") instead of being loaded. Cartridge saves are not concerned. No other
  machine's state key reads these files (the CPS-1/CPS-2, Neo Geo, PC Engine, NES, PlayStation and MSX keys hash their own
  machine files; the Master System's `compiler_signature` that lists them is a record of the library, not a state key; the
  X68000's key hashes its own machine files and its generated CPU code), so their F8 states of 1.7.3 still load. The Amiga, Atari ST and
  Nintendo 64 keys take every input of their machine, the host's included (`sdk_stamp`), so they move with this change too (their game
  stamps move in 1.7.4 anyway).
* **Texts.** Thirteen new entries in the catalogue of the five game languages (and in the seven locale files): "Controls",
  "Options", "Help", "Yes", "No", "P%d", "Reset", "Start-up reminders: %s", "Stretched", "F4  Window / Pixel / Fit /
  Stretched", the tiles' hint line and the two lines about a computer's keyboard. Every
  other text is an existing one, drawn differently.
* **F4.** `[<Console>.Video] display_mode` keeps 0, 1 and 2 (window, pixel-perfect, fit) for what they meant, and adds 3
  (stretched); an exported game of 1.7.3 reading a 3 written by 1.7.4 falls back to the window, as for any unknown value.
  Checked: `tools/display_settings_selftest.py` (saved 0 to 3 read as themselves, 4 and -1 as the window, two rounds of F4)
  and the capabilities run (F4 four times, the notice, the whole output, a machine that clamps its former value).
* **Preferences.** One key added, `[Interface] start_help` (the new **Start-up reminders** row of the options page: 0 turns
  the opening plates off; absent or 1, they are shown); none renamed: bindings, combinations and options are read and written
  as before.
* **Unchanged.** What the pages do, the function keys, the pictures the machines produce (the plates and menus are drawn on
  the window after the picture), the headless runs, the routes and their hashes. A hidden-window test run shows no opening
  plate and still stops on Esc or on the Quit combination without a question.
* **Measured.** `tools/hostkit_capabilities_selftest.py` (205 checks: the tiles, the pages opened from them, "Quit?" with No,
  Esc and Yes, the Start-up reminders row and its preference, the four F4 modes) and `tools/hostkit_players_selftest.py` pass with the portable toolchain on Windows. The frame cost of the
  plates and of an open menu was **not** measured; nothing is drawn once the plates are gone and no menu is open.

## MSX2+: a third profile of the MSX family, with the V9958 (1.7.4, experimental, step 1)

**What changes.** The `msx2plus` profile opens as experimental for MSX2+ cartridges ([MSX.md](MSX.md#9-the-msx2-msx2plus)): the MSX2's board
with the V9958 (R#25-R#27, the ID in S#1, YJK and YAE in Graphic 7, the horizontal scroll with MSK and SP2, the command engine in every mode with
CMD) and the port F4h; C-BIOS 0.29a's MSX2+ images come from the same pinned archive. The MSX2 picture's points may be 15-bit colours (bit 15
set); a V9938 never makes one, so an MSX2 game's picture is unchanged (the MSX2 panel converted on this tree is equal to the panel of 13 November
on 15 fields of each of its 12 routes). The status lint and the registry test find a machine name by lookaround, not `\b`, so "MSX2+" is a name
and "MSX2" followed by "+" is another machine; every other name matches as before.

**Hot path:** a V9958 line with a scroll or the mask is drawn up to three times (the background of one or two pages, then the sprites); a V9938
line takes the same path as before.

**What moves:** the MSX and MSX2 game stamps (`msx_machine.c`, `msx_machine.h`, `msx_state.c`, `msx_v9938.c`, `msx_v9938_draw.c`,
`msx_v9938_cmd.c`, `msx_player.c`, `msx_native_main.c`, `msx_reference_main.c`, `msx_state_file.inc`, `rrhk_msx.inc`, `msx_cbios.py`,
`msx_conversion.py`, `systems/msx.py`); the MSX2+ is a new owner of the same files and of `cart_save.c` and `route_start.py`. No other
machine's stamp moves.

**Quick states:** the layout is `msx-state-4` (the port F4h); a state of an earlier build is refused cleanly.

## MSX2+: disk games (1.7.4, experimental, step 2)

**What changes.** The `msx2plus` profile converts disk games: a `.dsk` (720 or 360 KiB) or a set of one to ten, grouped into an M3U whose first
line names the machine ([MSX.md](MSX.md#disks-13-november-2026-branch-specmsx2plus-disk-174)). A disk game needs the player's own MSX2+ BIOS pair
and own disk ROM (a new path option, Options > MSX2+ disk ROM; nothing is shipped). The runtime gains the TC8566AF disk controller in slot 2 with
the disk ROM (`msx_fdc.c`, our own MIT code); the disks are embedded in the game, what a game writes goes to a copy beside its settings
(`datas/games/msx2plus-<id>/disk-N.dsk`), Page Up / Page Down change disk, and the long routes of a multi-disk game insert the next disks. The
report names the disk interface in the cartridge's place and has a `disk_writes` block (what the game wrote, checked in fresh processes).
`tools/msx_write_disk.py` builds an authored disk (our own boot sector, no game data) that writes one sector, which proves the write path
end to end; `tools/msx_fdc_selftest.py` checks the controller alone (a write changes exactly the sectors it is given).

**Shared:** `rom_sources.disk_sets` now groups disk sets for any machine that declares them (`DiskSetKind`: the profile, its suffixes, its
folder, its marker), and an M3U it writes for the MSX2+ starts with `# Retro-Recomp system: msx2plus`; the X68000's M3U bytes are unchanged
(a test pins them) and the Atari ST's sets are untouched. `rom_sources.py` is in no stamp.

**Hot path:** none: the controller is reached only when the program reads or writes its four registers; a cartridge game builds without it
(`RR_MSX_DISKS` is 0) and its loop is unchanged.

**What moves:** the MSX, MSX2 and MSX2+ game stamps (`msx_fdc.c` and `msx_fdc.h` are new files of the three; `msx_machine.c`,
`msx_machine.h`, `msx_cart.c`, `msx_glue.inc`, `msx_player.c`, `msx_state.c`, `msx_route.inc`, `msx_native_main.c`,
`msx_reference_main.c`, `msx_build.py`, `msx_conversion.py`, `msx_routes.py`, `systems/msx.py`, and the new `retrorecomp/msx_disk.py`). No other machine's
stamp moves.

**Quick states:** the layout is `msx-state-5` (the controller and the disk in the drive); a state of an earlier build is refused cleanly.

## MSX and MSX2: the cartridge's battery SRAM is kept, the common report has the counts (1.7.4)

**What changes.**
- **Battery SRAM** (gate G7). An ASCII 8 KiB or ASCII 16 KiB cartridge whose game selects a bank past its image (the bit above the
  bank number that its wiring uses for the SRAM: bit 5 on Xanadu, bit 7 on Royal Blood, bit 4 on Hydlide 2) gets its SRAM: the
  conversion finds the bit from the bank values the game writes while the start is chosen, then chooses the start again with it.
  The SRAM (8 KiB on ASCII 8, 2 KiB repeated over the page on ASCII 16) is readable where it is selected and written only in
  8000h-BFFFh. The player keeps it in `datas/saves/<game>-<cartridge>.rrsram` through the shared `native/cart_save.c` (the Mega
  Drive's, Super Nintendo's and PC Engine's), loaded at start and written two seconds after the game last wrote it and when it
  closes; a file it cannot use is set aside, never deleted. Each such conversion checks it on the delivered file in fresh
  processes (no file, a valid file, eleven damaged files, what the play route wrote surviving into the next process). Dragon
  Slayer II - Xanadu (Japan), standard level: bit 5 found, the play route writes it, the checks pass, 0 interpreted instructions.
- **The common report** (gate G2): the MSX's final rows also give `native_entries`, `interpreted_opcodes` and
  `interpreter_cycles`, so the report's main CPU block has its counts (they were `null`); `hardware_devices` names the mapper,
  the video chip, the PSG and the SCC; `route_warnings` uses the Master System's rule. The shared reader is unchanged.
- **Shared helpers:** the cartridge-save file format and its damaged copies (`conversion_gates.cart_save_file`,
  `damaged_cart_saves`, `fnv64`) are lifted from `pce_conversion.py`, whose `backup_file` and `damaged_backups` now call them with
  identical results (the PC Engine's tests unchanged).

**Hot path:** no. A cartridge with SRAM reads and writes its SRAM pages through the mapper's path, which only ASCII cartridges with
SRAM take; no other machine's code changes.

**What moves:**
- The MSX and MSX2 game stamps: `native/msx_machine/msx_cart.c`, `msx_machine.c`, `msx_machine.h`, `msx_state.c`, `msx_player.c`,
  `msx_native_main.c`, `msx_reference_main.c`, `msx_headless.inc`, the new `msx_sram.c` and `msx_sram.h`, `retrorecomp/msx_rom.py`
  and `retrorecomp/msx_conversion.py`; `native/cart_save.c` and `cart_save.h` become inputs of the MSX and MSX2 too (their bytes do
  not change, so the Mega Drive's, Super Nintendo's and PC Engine's stamps do not move for them).
- `retrorecomp/conversion_gates.py` moves the game stamps of the machines of `shares:conversion_gates`; `retrorecomp/pce_conversion.py`
  moves the PC Engine's.

**Quick states:** MSX and MSX2 states carry the SRAM: the layout is `msx-state-3`, and a state of 1.7.3 is refused cleanly (the build
binding differs). No other machine's state changes.

## Game Boy Advance: the delivered file is replayed against the player as built, the player can write a row per frame, a heal count in the report (1.7.4)

**What changes.**
- **The delivered file** (gates G5 and G8). The player writes one text line per frame (the frame, the hash of the picture, the hash of the sound of that frame, whether a
  sample was not zero) when `RETRORECOMP_GBA_ROWS` names a file: a test switch, like the player's other `RETRORECOMP_GBA_*` ones, never read in play, and the sound is hashed
  only when the switch is set. After the player is built the conversion runs it on both scenarios, then runs the compressed copy it delivers (`delivery_evidence`, the helper of the
  other machines) and **refuses to publish** a copy whose last picture, frame count or any row differs; a picture that never changes in the generic scenario refuses the
  conversion too. The report gets the liveness of each scenario, `packed_reference_match`, `delivered_file` and `sound_routes`. A conversion takes a few minutes more (two
  runs of the player per scenario).
- **The report counts the heals** the engine did (`healed_native` in the rows and in the log): on Linux the engine's `NOT_STATIC` label also counts a heal.
- **Checks** (tools, not the converter): `gba_fresh_process.py refusals` (damaged quick states refused, a missing one creates nothing) and `route` (a route's last picture, frame count and
  interpreted count); twelve key-script routes and three save scripts in `tools/gba_routes/`.

**Hot path:** no. The player does one `getenv` at start; with the switch unset it does nothing more per frame than before (one pointer test).

**What moves:** the Game Boy Advance **game** stamp only (`20b869ddcba2` on main at the 1.7.3 release, `f65705900b6a` on this branch: `native/gba_machine.cpp`, `retrorecomp/gba_build.py` and
`retrorecomp/gba_conversion.py` are game inputs). The host stamp and the build stamp of the Game Boy Advance do not move, and **no other console's** stamp moves (the stamps of the nineteen
profiles were compared with main `f3479c5a`: only that one differs). `delivery_evidence.py`, `conversion_gates.py` and `resources.py` are untouched. **Existing Game Boy Advance
exports:** the game stamp moves, so a 1.7.3 export is converted in full at its next conversion, from the player's own paths (experimental, private to the player, no frozen legacy stamp). **Quick
states and saves:** the cartridge save is untouched; a quick state of a game converted before may be refused by the build binding (a rule of [UPGRADES](#the-rule-the-previous-release-only)).

## Atari ST: the root of a disk is read as the TOS reads it, two names more among the utilities, the interpreted instructions listed by address, the known stops in the report (1.7.4)

The Atari ST game stamp moves, from `f61238ca2d46` to `f414185b00f5` (measured on main `be170091`; the host and build stamps do not move), so an Atari ST export of 1.7.3 is converted again in
full by the first batch of 1.7.4. What a converted game does is not changed, except where a disk's root was read wrongly or a name is now a utility:

- **The root directory of disk 1 is read after two FATs, as the TOS reads it.** The reader of `atarist_disk.py` believed the BPB's number of FATs, and the TOS takes every floppy to have two. Of the 275 disk 1 images
  of the library tried, 10 declare one FAT and three change: Battle Probe (empty root before; `PROBE.PRG`, started by the desktop autostart, which stays kept only when the reference run shows the boot reached the
  desktop), Pharaoh III (`PHAROAH.TOS`: it starts its menu with the player's own TOS 1.04 and ends in an EmuTOS "Panic: Bus Error") and Trailblazer (`EDITOR.PRG` and `TRAIL.PRG`). The other 272 decide as before.
- **"music" and "editor" are utilities** in rule 2 of the desktop autostart (exact words): Conquests of Camelot starts `SIERRA.PRG` (not `MUSIC.PRG`) and Trailblazer starts `TRAIL.PRG`. The rule stays a guess by name, and the
  player can open another program from the desktop. Language versions, game pairs and Mercenary are still left to the player.
- **Each report lists where the interpreted instructions ran**: `final_checks[].interpreted_sites` (address, opcode, count, most run first), `interpreted_sites_distinct`, `interpreted_sites_unlisted` and `interpreted_sites_complete`
  (the counts add up to the run's total; true on all 47 routes of the panel), asked of the delivered file's runs by the player's option `--interpreted-sites` (a table of 65,536 sites, off in a game that is played). The report also names the
  Shifter/GLUE/MMU and the YM2149 as devices (`hardware_devices`, no counter), the MFP, the IKBD and the WD1772 with its DMA in `machine.other_devices`, keeps the picture changes and the frame of the last one in the
  liveness record, and fills `route_warnings` (the Sega modules' function: a route whose picture stops changing in its first tenth).
- **`atarist_notes.py`: the known stops.** A table, keyed by a dump's SHA-256, of what the routes of the panel run of 13 November 2026 stop on: Another World (code wheel), Carrier Command (manual word), Elite (novella protection),
  Operation Stealth (colour codes), Leader Board (hardware key), Trinity (a resolution the machine does not start in), and Metro-Cross and Pharaoh III (EmuTOS; they start with the player's TOS 1.04). It adds a sentence to
  `route_warnings` and changes nothing a conversion does: no protection is answered, skipped or patched.

**Proof** (Windows, one tree, 13 November 2026): the panel of eight games, converted one at a time from an empty scratch library at the extended level (Lethal Xcess at the thorough level: the second long route changes the disk, and it reaches play);
on all 25 routes the native game and its compressed copy equal the fresh interpreted reference (picture, sound, RAM, CPU registers of every frame) and the state continues in a fresh process on 8 of 8 ([ATARI_ST.md](ATARI_ST.md#3-the-five-measures)). Seven more games
were converted in the same run and are outside the panel; the fifteen exports were delivered to the owner's folder with the same publish step as the batch (each published file's SHA-256 equals the compressed copy the conversion replayed).

## Commodore Amiga: route scripts in LF on every system, the long route's script digest in the report (1.7.4)

**What changes.** The input script of each route (`inputs-<route>.txt`) is written as LF bytes on every system. It used to be
written in text mode, so Windows wrote CRLF. The player reads both the same way, but `final_checks[].script_sha256` of the same
route differed between Windows and Linux. The Lotus 2 witness of 12 Nov showed it: every hash of both routes was equal, and only
these two digests differed. The long routes of `advanced_scan.long_routes` (so `scan.routes` of the common report) now also carry
their `script_sha256`.

**Hot path:** no. Conversion time and the report only. The events, and so the inputs a game receives, are the same.

**What moves:** the Amiga's game stamp (the conversion module); no other console. On Windows, the `script_sha256` of every route
changes once, to the LF file's digest, which is the one Linux already wrote.

**Quick states:** the Amiga's key moves, as between any two Amiga builds.

## Commodore Amiga: Another World and Lemmings answer their first screen; every route of such an install starts with the answer (1.7.4)

**What changes.**
- **Another World (FR).** Its routes answer the code wheel with the joystick: three submissions at frames 500, 900 and 1300. The
  generic route follows from frame 1500, without mouse events, because the slave maps the left button to the access-code screen,
  which locks a game whose protection has not passed. Headless on the delivered exe, the protection passes and the intro plays to
  the laboratory (5,217 audible frames of 7,000; before, 43).
- **Lemmings (Image).** After its intro, the pointer moves onto "1 PLAYER" and clicks, then the level's briefing is clicked. The
  generic route follows from frame 4800. Headless, level 1 is played from about frame 4,500 on.
- **Every route of an install in `ROUTE_ANSWERS`** now starts with the answer: main as before, and now also the exploration route
  (at least the answer's frames) and the long routes. Monkey Island 2's exploration and long routes change with it.
- Both are the inputs the game's owner would give (the lead, 13 Nov: Monkey Island 2's answer of 1.7.3 is the precedent; a
  protection is never patched or skipped). A route is a scripted input, not gameplay validation.
- **One writer of the routes.** `amiga_conversion.route_events` writes every route, answered or not, for the conversion and for
  `tools/amiga_route_captures.py`. Before, that tool rewrote the routes without the answer, so its pictures of an answered install were
  not of the route the conversion played. It now refuses a route whose rewritten script does not have the report's `script_sha256`.
  The 27 routes of the final panel (13 November, nine installs) give their recorded digests again: the conversion's scripts are unchanged.
- **Known stops in the report.** An install whose routes are known to stop before play is named with its reason in the report's
  `route_warnings` (read into `honesty.route_warnings`), from `amiga_conversion.ROUTE_STOPS`, as the Atari ST does: Monkey Island 2's
  routes end in its opening. Words about a game, never its bytes; no route is chosen from them.

**Hot path:** no. Conversion time only: these three installs run their answer on every route.

**What moves:** the Amiga's game stamp (the conversion module); no other console. The routes, the observed code and the native
counts of Another World, Lemmings and Monkey Island 2 change. The other installs' routes do not.

**Quick states:** the Amiga's key moves, as between any two Amiga builds.

## Commodore Amiga: quick states carry a checksum and the install's identity; damaged ones are refused (1.7.4, G6)

**What changes.**
- **The quick state file** (`RRAMIGA-STATE-3`, was 2). Its header now has the install's identity (its SHA-256) and a checksum of the
  whole file (FNV-1a 64). A state of another build or install, or one with a changed byte, a cut, or anything added after its end,
  is refused before the machine is touched. The game goes on as it was. The headless player exits 4 on a refused state, as the
  other machines' players do. The F9 page says the state could not be loaded, as before.
- **The conversion** checks quick states with the shared `conversion_gates.check_quick_states`, as the PC Engine and the MSX do.
  The state is saved 600 frames before the main route's end and continued by a fresh process of the compressed copy for those 600
  frames (it was 400). Then 17 damaged copies must each be refused and left byte for byte as they were: empty, header cut, one
  byte short, one byte more, half cut, a flipped bit in the magic, the ABI, the identity, the frame, the inputs, each size, the
  checksum, the resload state, the payload and the last byte, and a text file. Loading a missing state must be refused and create
  nothing. The report's `game_states.validation` carries these results.
- **The bitplane batch at a state** (stage 7's open note). A state taken while a batched line still has bitplane slots to run,
  which can happen when one instruction runs past line 0 before the state, now gives that line back first. The slots this colour
  clock has seen run, and the rest go back to vAmiga's events, which the snapshot keeps (`Agnus::rrBeforeSave`). The display
  self-test takes a state inside a batched line on 6 scenarios: every record is equal to the run with every line on vAmiga's
  events, and leaving the slots out (`--state-fault 3`) is seen on all 6. The rest of the self-test is unchanged (12 + 8
  scenarios, 40 of 40 faults, 0 bus-model differences).

**Hot path:** no. The check runs at a state's save and load only. The bitplane give-back runs only when a state is taken inside a
batched line.

**What moves:** the Amiga's game stamp (the session, the player, the adapter `rrhk_amiga.inc`, the conversion module and the
adaptation of vAmiga); no other console. The host kit's shell is not touched.

**Quick states:** every Amiga state saved before this change is refused cleanly (another format), as the rule of 1.6.5 allows.
Cartridge-like saves (the files an install writes through resload) are not affected.

## Exports of 1.7.2 in 1.7.3

1.7.3 is the release after 1.7.2 (published on 10 November 2026). This section is the index of its changes, one line per section below (or per page when a change has no
section here), with the stamps that section says move. Each section computed its stamps for its own change alone, on the tree of its branch; the totals are under the table and were
computed on `main` on 12 November 2026 (`6bdc7863`).

| Change | Game stamps that move | Host and build stamps | Quick states |
| --- | --- | --- | --- |
| [MSX and MSX2: the shared pieces the two new profiles use](#msx-and-msx2-the-shared-pieces-the-two-new-profiles-use-173); the MSX and the MSX2 open as experimental machines | **every machine's game stamp** (`native/gamestate.inc`, `state_envelope.h`, `runtime_feedback.h`), and the PC Engine's own conversion; no game of an existing machine changes; the MSX and the MSX2 are new | none (C-BIOS's notice is the MSX's own) | **the Mega Drive and Super Nintendo keys move**, and the Amiga, Atari ST and Nintendo 64 keys; the others do not; the MSX and MSX2 keys are new |
| [Every console: each game embeds the notices of its own components](#every-console-each-game-embeds-the-notices-of-its-own-components-173) | **every machine's game stamp** (the modules that write the notices) | **the host stamp of every machine, once** (`notices.py`, the notice files each machine owns, `THIRD_PARTY_NOTICES.md` leaving the inputs) | **the Neo Geo key moves** (`neogeo_build.py`), and the Amiga, Atari ST and Nintendo 64 keys; the others do not |
| [Game Boy Advance: the first conversion converges faster, a conversion that differs from the interpreter fails, shared paths](#game-boy-advance-the-first-conversion-converges-faster-a-conversion-that-differs-from-the-interpreter-fails-shared-paths-173) | the Game Boy Advance only | none | no key of ours: a state is the engine's own container (magic, version, the ROM's SHA-1); a state of a game converted before may be refused |
| The command line: `--gba-bios` has its own help text, and a test requires one for every firmware path flag (no section of this page; commit `c93ae7bd`) | none | none | none |
| [Commodore Amiga: what the sweep's bound leaves out is counted](#commodore-amiga-what-the-sweeps-bound-leaves-out-is-counted-173) | the Amiga only | none | the Amiga key moves, as between any two Amiga builds |
| [Commodore Amiga: a border of one colour written four Texels at a time (colour step B)](#commodore-amiga-a-border-of-one-colour-written-four-texels-at-a-time-173-colour-step-b) | the Amiga only | none | the Amiga key moves, as between any two Amiga builds |
| [Commodore Amiga: the texture in the host's order, the picture copied without a swap (colour step D)](#commodore-amiga-the-texture-in-the-hosts-order-the-picture-copied-without-a-swap-173-colour-step-d) | the Amiga only | none | the Amiga key moves, as between any two Amiga builds |
| [Commodore Amiga: one lookup per hires pixel inside the display window (colour step A)](#commodore-amiga-one-lookup-per-hires-pixel-inside-the-display-window-173-colour-step-a) | the Amiga only | none | the Amiga key moves, as between any two Amiga builds |
| [Commodore Amiga: the sweep's bound shared between images and phases, the Kickstart part removed](#commodore-amiga-the-sweeps-bound-shared-between-images-and-phases-the-kickstart-part-removed-173) | the Amiga only | none | the Amiga key moves, as between any two Amiga builds |
| [Commodore Amiga: the main route presses 1 and 2, and answers Monkey Island 2's protection](#commodore-amiga-the-main-route-presses-1-and-2-and-answers-monkey-island-2s-protection-173) | the Amiga only (the routes of every Amiga game change) | none | the Amiga key moves, as between any two Amiga builds |
| [Amiga, Atari ST and Sharp X68000: the click that captures the mouse stays the host's](#amiga-atari-st-and-sharp-x68000-the-click-that-captures-the-mouse-stays-the-hosts-173) | none | **the host stamps of the Amiga, the Atari ST and the X68000** (`native/hostkit/adapters/rrhk_computer.inc`) | the Amiga and Atari ST keys move (they take every input, the host's included); the X68000 key does not |
| [Mega Drive: a larger player's record, anchored static discovery, and a learning pass when the last one still ran the interpreter](#mega-drive-a-larger-players-record-anchored-static-discovery-and-a-learning-pass-when-the-last-one-still-ran-the-interpreter-173) | **every machine's game stamp** (`native/runtime_feedback.c`, `feedback.py`, the profiles), the Mega Drive's own files too | none | **the Mega Drive and Super Nintendo keys move** (`runtime_feedback.c`), and the Amiga, Atari ST and Nintendo 64 keys; the others do not |
| [Every console: a conversion with its own library reads no player's record of the player's exports](#every-console-a-conversion-with-its-own-library-reads-no-players-record-of-the-players-exports-173) | **every machine's game stamp** (`feedback.py`); no game changes | none | the Amiga, Atari ST and Nintendo 64 keys move; the others do not |
| The Z80 chain: the reference CPU's M1 count is taken back with R where it calls `inc_r` twice for one M1 cycle, for machines with M1 wait states (no section of this page; commit `b9f0d38f`; off for the Master System and the Game Gear) | the Master System and the Game Gear (`retrorecomp/cpu.py`); their output does not change | none | none (they have no key) |
| [Amiga, Atari ST, Nintendo 64, CPS-2, PlayStation, MSX: the build project is removed after publication](#amiga-atari-st-nintendo-64-cps-2-playstation-msx-the-build-project-is-removed-after-publication-173) | none (interface code) | none | none |
| [MSX, MSX2, Atari ST: a free firmware download refused by a mirror is tried three times](#msx-msx2-atari-st-a-free-firmware-download-refused-by-a-mirror-is-tried-three-times-173) | the MSX, the MSX2 and the Atari ST (`msx_cbios.py`, `atarist_emutos.py`); no game changes | none | none |
| [Mega Drive, Super Nintendo, PC Engine: one cartridge-save file for the three](#mega-drive-super-nintendo-pc-engine-one-cartridge-save-file-for-the-three-173) | the Mega Drive, the Super Nintendo and the PC Engine, and the Neo Geo, the CPS-1, the CPS-2 and the PlayStation through `console16.py` (their games do not change) | none | **the Mega Drive and Super Nintendo keys move** (they hash the listed native files); the others do not |
| [PC Engine / TurboGrafx-16: the player's own record, and a start with I after Run](#pc-engine--turbografx-16-the-players-own-record-and-a-start-with-i-after-run-173) | the PC Engine only | none | **the PC Engine key moves** (the bridge files change) |
| [Master System, Game Gear: the Z80 chain's second-machine seams completed](#master-system-game-gear-the-z80-chains-second-machine-seams-completed-173) | **every machine's game stamp** (`core.py`, `native/banked_emitter.inc`); the Master System and Game Gear output is byte-identical | none | the Amiga, Atari ST and Nintendo 64 keys move; the others do not |
| [Atari ST: the player's own record](#atari-st-the-players-own-record-173) | the Atari ST, and the Amiga through the walk they share (`m68k_record_walk.py`; no Amiga output changes) | none | the Atari ST and Amiga keys move (the Amiga's with its game stamp) |
| [Atari ST: a sweep over the memory at the end of the routes](#atari-st-a-sweep-over-the-memory-at-the-end-of-the-routes-173) | the Atari ST, and the Amiga through the same shared walk (no Amiga output changes) | none | the Atari ST and Amiga keys move |
| [Atari ST: the disks in the order their names mean, and a program chosen among several](#atari-st-the-disks-in-the-order-their-names-mean-and-a-program-chosen-among-several-173) | the Atari ST only | none | the Atari ST key moves |
| [Atari ST: Hatari's timer D patch chosen per game](#atari-st-hataris-timer-d-patch-chosen-per-game-173) | the Atari ST only (and the Hatari adaptation digest, so the machine core is built again once) | none | the Atari ST key moves |
| [Mega Drive: the limits of the learned code are counted, never silent](#mega-drive-the-limits-of-the-learned-code-are-counted-never-silent-173) | the Mega Drive, and the Super Nintendo, the Neo Geo, the CPS-1, the CPS-2, the PC Engine and the PlayStation through `console16.py` (their output does not change) | none | **the Mega Drive key moves** (`md_backend.c`); the others do not |
| [Neo Geo: the code the reference runs could not keep is counted and reported](#neo-geo-the-code-the-reference-runs-could-not-keep-is-counted-and-reported-173) | the Neo Geo only | none | **the Neo Geo key moves** (`native/neogeo_reference.c`) |
| [Super Nintendo: the rows the RAM-code limit leaves out are counted](#super-nintendo-the-rows-the-ram-code-limit-leaves-out-are-counted-173) | the Super Nintendo, and the Mega Drive, the Neo Geo, the CPS-1, the CPS-2, the PC Engine and the PlayStation through `console16.py` (their output does not change) | none | none |
| [Master System and Game Gear: the cap on compiled RAM windows is counted](#master-system-and-game-gear-the-cap-on-compiled-ram-windows-is-counted-173) | **every machine's game stamp** (`core.py`, `library.py`); no game changes | none | the Amiga, Atari ST and Nintendo 64 keys move; the others do not |
| The knowledge exchange: an import of shared paths counts the valid rows a limit leaves out (`knowledge_exchange.dropped`; no section of this page; merge `6d8e27b7`) | none (`knowledge_exchange.py` and `online.py` are out of the stamps) | none | none |
| The converter window: what a sync or an import of shared paths left out is said in one line, in the eight languages (no section of this page; commit `4924c803`) | none (interface strings) | none | none |
| [Master System, Game Gear: the Z80 chain made ready for a second Z80 machine](#master-system-game-gear-the-z80-chain-made-ready-for-a-second-z80-machine-173) | **every machine's game stamp** (`core.py`, `native/banked_emitter.inc`); the Master System and Game Gear output is byte-identical | none | the Amiga, Atari ST and Nintendo 64 keys move; the others do not |
| [Every console: a step still writing goes past its time limit](#every-console-a-step-still-writing-goes-past-its-time-limit-173) | **every machine's game stamp** (`core.py` and `batch.py`) | none | the Amiga, Atari ST and Nintendo 64 keys move; the others do not |
| [Commodore Amiga: Denise's line work by table and by word, Agnus's clock step inlined (Agnus/Denise step 1)](#commodore-amiga-denises-line-work-by-table-and-by-word-agnuss-clock-step-inlined-173-agnusdenise-step-1) | the Amiga only (each section says so) | none | the Amiga key moves, as between any two Amiga builds |
| [Commodore Amiga: a line's bitplane slots taken in a batch (Agnus/Denise step 2)](#commodore-amiga-a-lines-bitplane-slots-taken-in-a-batch-173-agnusdenise-step-2) | the Amiga only (each section says so) | none | the Amiga key moves, as between any two Amiga builds |
| [Commodore Amiga: a quiet line's pass in one loop (Agnus/Denise step 3)](#commodore-amiga-a-quiet-lines-pass-in-one-loop-173-agnusdenise-step-3) | the Amiga only (each section says so) | none | the Amiga key moves, as between any two Amiga builds |
| [Commodore Amiga: stage 7's bus model in shadow, never in an export (stage 7 checkpoints 0-2)](#commodore-amiga-stage-7s-bus-model-in-shadow-never-in-an-export-173-stage-7-checkpoints-0-2) | the Amiga only (the text of the hooks enters vAmiga's adaptation) | none | the Amiga key moves |
| [Commodore Amiga: the idle disk controller's events caught up (stage 7 checkpoint 3a)](#commodore-amiga-the-idle-disk-controllers-events-caught-up-173-stage-7-checkpoint-3a) | the Amiga only (each section says so) | none | the Amiga key moves, as between any two Amiga builds |
| [Commodore Amiga: the idle sprites' slots left out of their lines (stage 7 checkpoint 3b)](#commodore-amiga-the-idle-sprites-slots-left-out-of-their-lines-173-stage-7-checkpoint-3b) | the Amiga only (each section says so) | none | the Amiga key moves, as between any two Amiga builds |
| [Commodore Amiga: quick states on a frame cut short, and the idle sprites counted once (stage 7)](#commodore-amiga-quick-states-on-a-frame-cut-short-and-the-idle-sprites-counted-once-173-stage-7) | the Amiga only (each section says so) | none | the Amiga key moves, as between any two Amiga builds |
| [Commodore Amiga: the Blitter served alone on its colour clock, tried and reverted (stage 7 checkpoint 4)](#commodore-amiga-the-blitter-served-alone-on-its-colour-clock-tried-and-reverted-173-stage-7-checkpoint-4) | none: not in any build | none | none |
| [Commodore Amiga: checkpoint 3's counters in the conversion report (stage 7)](#commodore-amiga-checkpoint-3s-counters-in-the-conversion-report-173-stage-7) | the Amiga only (each section says so) | none | the Amiga key moves, as between any two Amiga builds |
| The converter window: a step that reaches its time limit is named in the player's language (no section of this page; commit `976e2a88`) | none (interface strings) | none | none |
| Qualification: the Game Boy Advance's G15 (honesty) is partial ([QUALIFICATION.md](QUALIFICATION.md); no section of this page) | none | none | none |

Taken together (`compilation_inputs.role_stamps` of the nineteen profiles, the tree of `v1.7.2` against `main`, Windows, Python 3.14): **the game stamp of every
profile moves**, through the converter's own build steps (`core.py`, `batch.py`, `native/banked_emitter.inc`) and the player's record
(`native/runtime_feedback.c`, `feedback.py`); **the host stamp of every profile moves**, once, because each game now embeds the notices of its own
components (the click that captures the mouse moves the Amiga, Atari ST and X68000 host stamps as well); **no build stamp moves**. The MSX and the MSX2 are new.

| Machine | Game stamp (v1.7.2, now) | Host stamp | Build stamp |
| --- | --- | --- | --- |
| Master System | `63c93fcb0264`, `0f2ae3577f5f` | `62a7e9f65d83`, `afcd7d80d268` | `fe2d99b3cd5e` (same) |
| Game Gear | `70eafce5937a`, `f6156c79361a` | `fa5e7fa22b05`, `1a50c71be834` | `f5671c38cf26` (same) |
| Game Boy | `b218f94d2c75`, `fda8a848fcba` | `2a0942586a4a`, `b0c6d1f25dcb` | `819a054ad881` (same) |
| NES | `af5a3a096738`, `d003f9637777` | `39c36bfa861a`, `aace3c47c69a` | `8e0941f93b43` (same) |
| Mega Drive | `ed3a49ab59a8`, `fcf472f6e2b0` | `8f4324fbcb85`, `ae954d97ef21` | `9615ff2e96c8` (same) |
| Super Nintendo | `064bd8544d76`, `830816cf1a5d` | `d35383911455`, `1338832835c7` | `3f0a58ad3c7c` (same) |
| Neo Geo | `b45ca489a2c9`, `296e61d8c8b5` | `f1fde4b7a652`, `209363c3cb2d` | `110349f043bd` (same) |
| X68000 | `107b51de2145`, `6a1a3e6fffa6` | `be9dae27aacf`, `cd36f942cda8` | `5903c0449429` (same) |
| CPS-1 | `28dd85714948`, `5bad58285e1e` | `0220746ac9ad`, `1744a86d265c` | `2782cd370f91` (same) |
| CPS-2 | `cb7b5d304275`, `3d06a5ebcc85` | `7889559074ad`, `5f073fe7a9ca` | `81a51ad49349` (same) |
| PC Engine / TurboGrafx-16 | `aa7913b68d39`, `dc4e67408d8f` | `3da7363bd893`, `20772c959102` | `66d912662e5c` (same) |
| Game Boy Advance | `1658c523234f`, `20b869ddcba2` | `7b18d021f143`, `287e639d641a` | `6b70933a9b0a` (same) |
| Amiga | `6854eee76d0e`, `f069a288af8a` | `8ca835ce1027`, `7d590498bb06` | `92ca8a0c142c` (same) |
| Atari ST | `e6f3506a6be7`, `6c70ccd1ff7c` | `3b7c6f50488a`, `c1f3ab554861` | `54b75964897d` (same) |
| Nintendo 64 | `ec87144eb331`, `77b096906adf` | `3c4f6ccca458`, `93684dc83103` | `4f6fedf926c7` (same) |
| Adventure (ScummVM) | `42dfc172e91c`, `7e79677b16a3` | `82088d749a09`, `2e274a46f2af` | `05417bbcea96` (same) |
| Sony PlayStation | `4a3b197254a5`, `c6a915039614` | `5dbdb5df79ca`, `34ac75fcabae` | `b6c9cf73b176` (same) |
| MSX | `5ad96cd2add4` (new) | `7f3fdbbcf3d1` (new) | `3e7de8099a99` (new) |
| MSX2 | `cbb66977125c` (new) | `e75758647762` (new) | `d2329c8c61ad` (new) |

(First twelve hexadecimal digits of each stamp.) `LEGACY_GAME_STAMPS` stays empty. **So every export of 1.7.2, on every machine, is converted again once at the
upgrade**, at the quick level, from its learned paths, and the window offers it. The shared paths of the base are kept: they are qualified by the recompiler's revision, not by
this stamp.

**Quick states.** The **Amiga, Atari ST and Nintendo 64 keys move**: each takes every input of its machine, which moves with the converter's build steps (and the Amiga's
own files, and the Amiga and Atari ST host, change too). The **Mega Drive and Super Nintendo keys move** too: they hash their listed native files, which the shared cartridge-save file and the player's record
(`runtime_feedback.c`) change (and the Mega Drive's learned-code counters). The **PC Engine key moves**: it hashes the bridge files the player's record changes. The **Neo Geo key moves**: it hashes
`native/neogeo_reference.c` (the counted variants) and the code of `neogeo_build.py` (the notices). A quick state of 1.7.2 of those seven
machines is refused cleanly (no compatibility key is carried, [GAME_STATES.md](GAME_STATES.md)); nothing is lost but that state. The keys of the NES, the
CPS-1, the CPS-2, the PlayStation and the X68000 hash none of the files that changed (the X68000's host stamp moves, its key does not), so their states of 1.7.2 load in the rebuilt export; the Master System, Game Gear and Game Boy have no such key. A quick state of
the Game Boy Advance is the engine's own container (magic, version, the ROM's SHA-1), with no key of ours; its section says a state of a game converted before may be refused. The MSX and MSX2 keys are new. **Cartridge saves** are kept on every machine; the game saves of Adventure (ScummVM) are ScummVM's own.

## MSX and MSX2: the shared pieces the two new profiles use (1.7.3)

**What changes.** The MSX and the MSX2 open as experimental profiles ([MSX.md](MSX.md)); nothing of an existing export changes behaviour. What they
share with other machines was lifted out of those machines instead of copied a third time (STANDARDS rule 1), with identical
results, and two shared tables grow:
- **The quick-state envelope** (`native/state_envelope.h`, new): the Master System's 88-byte header, CRC and check-then-apply,
  lifted from `native/gamestate.inc`, which now calls it. The bytes of a Master System or Game Gear quick state are unchanged:
  Alex Kidd in Miracle World, quick states saved by an export built before and after, are equal byte for byte, and the Sega
  quick-state harness passes 6/6 on both.
- **The fresh-process quick-state check** (`conversion_gates.check_quick_states`), lifted from `pce_conversion.check_states`, which
  now calls it with the same texts and the same record.
- **The start chosen on the reference** (`retrorecomp/route_start.py`, new): `choose_start`, `liveness_score`, `divergence`,
  `reach` and `stuck_stretch`, lifted from `pce_conversion.py`, whose functions keep their names as callers. Alien Crush
  (Japan), standard level: the chosen start, every variant's numbers, the route scripts and `game_states` are equal before and
  after the three lifts.
- **The feedback kinds** (`native/runtime_feedback.h`): `RR_FB_MSX` 26 and `RR_FB_MSX2` 27, and `RR_FB_MAX_KIND` 27.

**Hot path:** no. The Master System's generated glue calls the same envelope code through one more function; the PC Engine's
changes are in its Python conversion only.

**What moves:**
- `native/gamestate.inc` and `native/state_envelope.h` are game-stamp inputs of every console (`ALL`): **every console's game
  stamp moves**.
- `native/runtime_feedback.h` is a game-stamp input of every console: **every console's game stamp moves** (the same release).
- `retrorecomp/conversion_gates.py` moves the game stamps of the machines of `shares:conversion_gates` (the Master System, Game
  Gear, Game Boy, NES, Mega Drive, Neo Geo, X68000, CPS-1, CPS-2, PC Engine, Amiga, Atari ST, Nintendo 64, PlayStation, and
  now the MSX and MSX2).
- `retrorecomp/pce_conversion.py` moves the PC Engine's game stamp; `retrorecomp/route_start.py` is a new game input of the PC
  Engine, the MSX and the MSX2.
- No other machine's host stamp moves: C-BIOS's notice (`licenses/cbios.md`) is an optional notice of the MSX and MSX2
  profiles only (embedded in a game that boots C-BIOS), and THIRD_PARTY_NOTICES.md is no longer a stamp input.

**Quick states:** the bytes of a state do not change on any existing machine (the Master System's and Game Gear's are equal; the PC
Engine's format is not touched). The Mega Drive and Super Nintendo keys move, because they hash `native/gamestate.inc` and
`native/runtime_feedback.h` among their listed files, and the Amiga, Atari ST and Nintendo 64 keys take every input of their machine: all five
move in 1.7.3 anyway. The PC Engine key hashes none of the files changed. The MSX and MSX2 states are new (layout `msx-state-2`).

## Every console: each game embeds the notices of its own components (1.7.3)

Until 1.7.2 the complete public list, `THIRD_PARTY_NOTICES.md`, was a host input of every console (and was embedded as it stood in
the Master System and Game Gear games), and most licence pages were listed for all consoles. One machine's new row therefore moved
the host stamp of every other machine. From 1.7.3:

- **A game embeds the notices of the components compiled into it, and no other.** The text is built in one place
  (`retrorecomp/notices.py`) from the lists its machine's profile declares: `notice_files` (the machine's engines and chips),
  `optional_notice_files` (only the games that use the part: EmuTOS on the Atari ST, the reused 68000 semantics on the Neo Geo's
  native route) and the player shell's `SHELL_NOTICE_FILES` (SDL2, the xBR filter, the menu fonts, the portable compiler's runtime,
  UPX). Retro-Recomp's own licence is always there. What only the pinned engine carries (a vendored library's licence file, a source
  header) is still read from the engine at its pin and added after the declared files (Mega Drive, Super Nintendo, Neo Geo, CPS-1,
  CPS-2). A declared file that is missing stops the conversion: a notice is never dropped silently. The CPS family's text is
  written by `cps1_conversion.write_notices` over the one `cps1_build.py` still prepares: that file is a pinned generator source, and a
  notice is no reason to raise `GENERATOR_REVISION` and make the qualified CPS paths wait again; its old list goes with the next revision.
- **Each notice file is a host input of the machines that embed it only.** `stamp_inputs.py` lists no licence file any more: it reads
  the same profile lists, so the owners of a notice are exactly the machines that declare it. `THIRD_PARTY_NOTICES.md` stays the
  complete public list of the converter distribution and is an input of no game. The notices of the converter's own runtime (Python,
  Tcl/Tk, Pillow, PyInstaller, OpenSSL, zlib, the Linux desktop parts, the Noto interface fonts) and of the development test vectors
  are declared out of the stamps (`NOT_INPUTS`).
- **The third-party content of each machine is complete, and in several cases better than before.** Nothing a game compiles lost its
  notice. Added: the X68000 games, which embedded no notice at all, now carry theirs as resource 203 (machine runtime, FMGEN, Musashi,
  the reused 68000 semantics); the Neo Geo's native route now carries GenesisRecomp's own terms (it looked for a file the pinned engine
  does not have, and silently carried only the decoder's); the Master System, Game Gear, Game Boy, NES and Game Boy Advance games
  carry UPX's notice like the others; every machine names the menu fonts (X.Org Misc Fixed, public domain;
  `licenses/misc-fixed.md`); the adventure executables carry the compiler runtime's notice. `licenses/smsggrecomp.md` is new: the
  permission and its limits, as the public list words them. Removed: the Noto font notice (no game holds a Noto glyph, see
  [LANGUAGES.md](LANGUAGES.md)), and, in the Master System and Game Gear games, the public list itself with its rows about the other
  machines and the converter; their second notice resource (104, `filter_legal.txt`) is folded into the one text, which
  `--credits` prints. The NES, the Neo Geo and the CPS family read their engines' own terms from the licence pages (the same texts as
  the pinned files) instead of the checkout.

**Hot path:** no. **Proof:** `tests/test_game_notices.py` (every profile's text holds each declared file; the declared lists cover
`MACHINE_UPSTREAMS`; a notice's owners are its embedders; a new machine's notice changes no other machine's inputs or stamps;
editing one machine's notice moves that machine's host stamp alone), `tests/test_stamp_inputs.py`.

**What moves:** **the host stamp of every console, once** (the new host module, the notice files each machine now owns, the public
list leaving the inputs). The modules that write the notices are game-side, so the game stamps move too (every game stamp moves in
1.7.3 anyway). **From now on a new machine's notice moves only its own stamps**: it declares its files on its profile and adds a row
to the public list, which no game reads. **Quick states:** the Neo Geo key moves (it hashes the code of `neogeo_build.py`, which now
writes the notices through `notices.py`); the Amiga, Atari ST and Nintendo 64 keys take every input of their machine, the host's included, so they
move too (all four move in 1.7.3 anyway); the other keys hash none of the files changed. The bytes of a state do not change.

## Game Boy Advance: the first conversion converges faster, a conversion that differs from the interpreter fails, shared paths (1.7.3)

The Game Boy Advance's engine patches (`retrorecomp/gba_patches.py`, 47 patches in 1.7.2, 52 now, `ENGINE_REV` unchanged, pin `c1a5fda3`) and converter, and its player's test
switch. **What changes for a player:** (1) the interpreter's bridge proposes the callees of a routine it interprets, so a *first* conversion from an empty library reaches
0 interpreted instructions in fewer passes (Golden Sun 7 passes with 3.86 million interpreted in generic before, 5 asked-and-settling passes and 0 now; Advance Wars 2,
The Minish Cap 3, Pokémon Emerald 2; [GAME_BOY_ADVANCE.md](GAME_BOY_ADVANCE.md#the-verdict-is-enforced-and-a-first-conversion-converges-faster-12-november-2026-173)); (2) a conversion
whose generated code differs from the engine's interpreter, or whose native run errored, now **fails** where it could pass, and a generator that does not end (it can loop on a wrong root; 300 s with received rows, 900 s otherwise) is stopped and the conversion made again without the received rows; (3) a Thumb `STMIA`/`PUSH` with an empty register list stores
the program counter plus six as the hardware does (interpreter and generated code); (4) the report counts the caps of the RAM code (`native_coverage.ram_code.caps`); (5) the machine can
share its paths in the experimental tier (`gba_knowledge.py`, a schema 3 record with an empty layout; not on until the site's limits for `gba` are deployed with the release); (6) the player reads
the test switch `RETRORECOMP_GBA_STATE` (a hidden player only).
**What moves:** the Game Boy Advance **game** stamp (`1658c523234f` in 1.7.2, `375fdcf55fc3` on the branch, `d89f30a66855` to `9ddd7055d88c` for this merge on main `3c593926`, then `ef6f51ae60c8` to `20b869ddcba2` when the module states its record rules for the site (`RECORD_RULES`, release 1.7.3 not yet published): the engine patches, the conversion code and the player source are game inputs). The host stamp
(`7b18d021f143`) and the build stamp (`6b70933a9b0a`) of the Game Boy Advance do not move, and **no other console's** stamp moves (the three stamps of the seventeen profiles were compared with the
merge base `a5379530`: only that one differs). `resources.py` is untouched. **Existing Game Boy Advance exports:** the game stamp moves, so an export of 1.7.2 is converted in full at its next conversion, from the player's own paths
(a game input changed; the machine is experimental and its exports are private to the player; no frozen legacy stamp is kept for it). **Quick states and saves:** the cartridge save is untouched; a quick state of a game converted before may be refused after the new build, by
the rule of [UPGRADES](#the-rule-the-previous-release-only). **Hot path:** none. The generated code differs from before only where the new roots add functions and where the Thumb empty-list store is
generated (two vectors of the self-test); the interpreter's replay is the proof, not a timing; `tools/gba_frame_cost.py` has not made its quiet-PC pass.

## Commodore Amiga: what the sweep's bound leaves out is counted (1.7.3)

**What changes.** The sweep beyond the routes stops at 150,000 instructions per conversion (`SWEEP_LIMIT`). Until now it stopped
there silently: Cyber Games reached it exactly. The bound stays where it is, but `native_forms` now reports what it left out:
- `sweep_limit` and `sweep_limit_reached`;
- `sweep_left_out.walk_places_left`: the places a branch walk had queued and not reached;
- `sweep_left_out.page_addresses_left`: the even addresses of the 4 KiB pages where code ran that were not tried.

The same figures are in `native_validation.generation.sweep_cut`. They count candidates, not instructions: most of those addresses
hold no code. Whatever they hold, if it ever runs, runs on the interpreter and is counted there, as before. The generated code is
unchanged: the same instructions are swept, in the same order.

**Proof.** Cyber Games at the standard scan level, by the real command line: 51,690 swept instructions, the bound not reached, and
every route equal to the conversion of main a5379530. At the extended level (a third route of 18,000 frames), the case where 1.7.1
reached the bound: 150,000 swept, `sweep_limit_reached` true, 74,308 walk places and 860,160 page addresses left out, and all three
routes equal to the reference, 0 interpreted outside the Kickstart.

**Hot path:** no. This is conversion time only.

**What moves:** the Amiga's game stamp (the code generator and the conversion module); no other console.

**Quick states:** the Amiga's key moves, as between any two Amiga builds.

## Commodore Amiga: a border of one colour written four Texels at a time (1.7.3, colour step B)

**What changes.** In step 3's colorize of a quiet line (`PixelEngine::rrColorize`), an 8-entry chunk whose border bytes are all
the same non-zero value is now written as four 64-bit Texels of that border colour. Before, each entry chose between the border
and the bitplane colour. A Texel holds its colour twice (`TEXEL`), so the texture row is the same byte for byte. Chunks with a
mixed border, and chunks inside the display window, are unchanged.

**Why.** On a normal PC, the border chunks were 7.5 % of a Lotus 2 frame and 8.4 % of a Rick Dangerous frame
(`PLAN-colour-20261112.md`). This is not a quiet-PC timing.

**Proofs.**
- The display self-test passes: 52 scenarios, every texture row equal to vAmiga's own colorize (`--per-slot`).
- A planted fault (`--colour-fault 1`: the one-colour chunk one bit off) is seen in 52 of 52 scenarios.
- Wave 1 by the real command line (Lotus 2, Rick Dangerous, Lemmings, Civilization, two routes each): every route equal to the conversions of main a5379530 (picture, sound, CPU, RAM and trace hashes, native and interpreted counts, the reference and compressed matches, the quick-state restart).

**Hot path:** yes, the per-line colorize: one comparison more per chunk that has a border, four stores instead of eight on one-colour
chunks. Measured in the quiet-PC pass at the end of the colour steps.

**What moves:** the Amiga's game stamp (the adaptation of vAmiga, the display checks); no other console. Denise stays emulated.

**Quick states:** the Amiga's key moves, as between any two Amiga builds.

## Commodore Amiga: the texture in the host's order, the picture copied without a swap (1.7.3, colour step D)

**What changes.** The session sets vAmiga's texture format to ARGB (`Opt::HOST_TEX_FORMAT`), so the palette is packed in the host's
order once. Until now the option was never set, and the session swapped red and blue in every pixel of every frame. The copy of
the picture now moves one 32-bit value per hires pixel and sets the alpha byte. The picture handed to the host is meant to be the
same bytes as before. A Fable review of 12 Nov found it safe: until now the format was ABGR, because the option was never set and
`HostConfig` is value-initialised, so the old swap gave 0xAARRGGBB; every texel outside the palettes that reaches the copied area
reads the same in both orders.

**Proofs.**
- Wave 1 by the real command line (Lotus 2, Rick Dangerous, Lemmings, Civilization, two routes each): every route equal to the conversions of main a5379530 (picture, sound, CPU, RAM and trace hashes, native and interpreted counts, the reference and compressed matches, the quick-state restart).

**Why.** On a normal PC, the copy with its swap was 6.0 % of a Lotus 2 frame and 8.9 % of a Rick Dangerous frame
(`PLAN-colour-20261112.md`). This is not a quiet-PC timing.

**Hot path:** yes, the end of each frame: the per-pixel swap is gone.

**What moves:** the Amiga's game stamp (the session); no other console.

**Quick states:** the Amiga's key moves, as between any two Amiga builds.

## Commodore Amiga: one lookup per hires pixel inside the display window (1.7.3, colour step A)

**What changes.** In step 3's colorize of a quiet line, an 8-entry chunk inside the display window first checks that its four pairs
of entries (2k and 2k + 1) hold the same colour index. If they do, it writes one 64-bit Texel (the colour twice) per pair: four
lookups instead of eight. A chunk whose pairs differ keeps one lookup per entry, and is counted (`rrCellsRefused`).
- **Why pairs differ.** In lores and hires a pixel always fills two or four entries from an even position. Super-hires does not.
  This machine has an ECS Agnus and an OCS Denise, so Agnus can draw super-hires on a line Denise's guard still calls quiet. A
  resolution change at the line's start, or a quick state loaded in mid-line, can also leave pairs unequal.
- **Review.** Fable reviewed the design on 12 Nov and found the super-hires case; the pair check is its recommendation.

**Proofs.**
- The display self-test: the 52 scenarios, plus 8 new ones with BPLCON0's SHRES bit. The 52 old scenarios are generated as before.
- Every texture row of all 60 scenarios is equal to vAmiga's own colorize.
- Planted faults, each seen:
  - `--colour-fault 2`, a cell's second entry one bit off: 60 of 60 scenarios;
  - `--colour-fault 3`, cells taken without the pair check: exactly the 8 super-hires scenarios.
- 234,044 chunks were refused, and 0 cells were written from a Texel with two different halves (the census under `RR_AMIGA_SHADOW`).
- A second Fable read of the committed code found it safe.
- Wave 1 by the real command line (Lotus 2, Rick Dangerous, Lemmings, Civilization, two routes each): every route equal to the conversions of main a5379530 (picture, sound, CPU, RAM and trace hashes, native and interpreted counts, the reference and compressed matches, the quick-state restart).

**Hot path:** yes, the per-line colorize: one 8-byte load and three operations more per chunk inside the window, four lookups less
when the pairs match. Measured in the quiet-PC pass at the end of the colour steps.

**What moves:** the Amiga's game stamp (the adaptation of vAmiga, the display checks); no other console. Denise stays emulated.

**Quick states:** the Amiga's key moves, as between any two Amiga builds.

## Commodore Amiga: the sweep's bound shared between images and phases, the Kickstart part removed (1.7.3)

**What changes.** The sweep first finds everything it can reach, up to 8 times the bound. When that is more than the bound
(150,000 instructions), the bound is now shared equally between each memory image's branch walk and its page fill (water-filling,
in order). Until now the first image's walk could take it all, and on Cyber Games at the extended level the page fill and the
other images never ran.
- **Under the bound nothing changes.** The same instructions are kept, in the same order, so a game below it gets the same code.
- **The Kickstart sweep is removed.** The Amiga's code apertures end at $DC0000, so it never added an instruction.
- **The report is exact now.** `native_forms` gives `sweep_reachable`, `sweep_left_out` (instructions, no longer candidate
  addresses) and `sweep_buckets` (image, phase, reached, kept). This replaces the counters added a few commits earlier, which were
  never released.

Arthur decided this on 12 Nov, from the measure in `SWEEP-MEASURE-20261112.md`. On an unseen route the sweep served up to 82 % of
the native entries (Civilization), and the cap cut 71 % of Cyber Games at the extended level.

**Proofs.** By the real command line, scratch library:
- **Cyber Games at the extended level.**
  - The sweep reaches 515,013 instructions; 150,000 are kept and 365,013 left out, counted. Before this change it also kept 150,000,
    but the first image's walk took them all.
  - The buckets now share them: image 0's walk 46,021 of 335,632, its fill 46,020 of 112,638, image 2's fill 46,020 of 54,804, and
    the small buckets whole.
  - Every field of the three routes is the same as before the change, hashes included, with 0 interpreted outside the Kickstart.
  - On an unseen route of 18,000 frames (headless, one run), interpreted instructions fall from 790,198 to 96,625, with the same
    trace.
- **Civilization at the standard level, under the bound.** The swept instructions, native forms, route fields and hashes are the
  same as main a5379530's. On the unseen route its native entries, swept entries and trace are the same as in the earlier measure.

**Hot path:** no. This is conversion time only. The generated code changes only for a game whose reachable code is above the bound.

**What moves:** the Amiga's game stamp (the code generator and the conversion module); no other console.

**Quick states:** the Amiga's key moves, as between any two Amiga builds.

## Commodore Amiga: the main route presses 1 and 2, and answers Monkey Island 2's protection (1.7.3)

**What changes.**
- **Every game.** The generic main route also taps the keys 1 (frame 400) and 2 (frame 1300), never when one of them is the slave's
  quit key. Civilization's first screen, "1) Mouse + Keyboard / 2) Keyboard", waited for one of them, so its routes stayed silent.
- **Monkey Island 2 only.** The game is recognised by its install's SHA-256 (`ROUTE_ANSWERS`, numbers about the install). Its main
  route first answers the "lame-o" copy protection: Return, any recipe digits, Return, then a box clicked with the mouse. The
  generic route follows from frame 3100. The route is at least 7,000 frames long, because the first sound comes at about frame 6,000.

Arthur decided this on 12 Nov, after playing the games himself; the study is `SILENT-ROUTES-20261112.md`. Another World's answer
waits for the green-screen investigation. A route is a scripted input, not gameplay validation. The native code it finds is still
proved against the interpreted reference, as on every route.

**Hot path:** no. This is conversion time only. Monkey Island 2's conversion runs a longer main route.

**What moves:** the Amiga's game stamp (the conversion module); no other console. The routes of every Amiga game change, so their
observed code and their native counts can change too.

**Recheck.** On 12 Nov the 12 delivered games other than Another World were converted by the real command line, scratch library.
- **All 12 pass.** Native validation passed, both routes equal the reference and the compressed copy, the quick-state restart is
  equal, 0 interpreted outside the Kickstart, and the Kickstart installs keep their 19 counted opcodes.
- **Explore routes:** unchanged, all five hashes equal on all 12.
- **Main routes:** they changed on 10 games, as expected. On Pinball Dreams and Shadow of the Beast every hash is the same.
- **Civilization:** its main route is audible now (2,491 frames) and runs 36.8 M native entries instead of 4.4 M.
- **Monkey Island 2:** its main route of 7,000 frames is audible (272 frames) and runs 79.3 M native entries instead of 41.0 M.
- **Not investigated:** Pinball Dreams' main route has 48 more native entries with the same trace.

**Quick states:** the Amiga's key moves, as between any two Amiga builds.

## Amiga, Atari ST and Sharp X68000: the click that captures the mouse stays the host's (1.7.3)

**What changes.** On the disk computers a left click in the window captures the mouse. Until now that click also reached the guest:
the event went on, and the next frames read the button still held. The machine saw a left click the player never meant for it.
- **The new rule.** The capturing click is consumed. The guest's left button stays up until that click is released, and every later
  click is the guest's, as before.
- **Unchanged.** A mouse game captures at start without a click, and Ctrl+Alt+M captures without one either.
- **Why.** On Another World's protection screen that stray click locked the game: the lead's decision of 12 Nov, the same rule on
  every computer machine.

**Proof.** `tests/amiga_menu_harness.c` gains seven checks of the click, with SDL's dummy driver and no window shown:
- the capturing click is consumed and captures the mouse;
- the guest's left button stays up while that click is held, and after it is released;
- a click on the captured mouse is the guest's, press and release.

The same harness on the code before the change fails three of them. The Atari ST, X68000 and host kit unit tests pass. The one
X68000 failure needs the main checkout's `.deps` and is unrelated.

**Hot path:** no. One test per frame on a flag.

**What moves:** the host stamp of the Amiga, the Atari ST and the X68000 (`native/hostkit/adapters/rrhk_computer.inc`, host role,
`shares:hostkit_computer`). No game stamp moves. Exports already made keep the old behaviour until they are rebuilt.

**Quick states:** the Amiga and Atari ST keys take every input of their machine, the host's included, so they move (they move in 1.7.3
anyway); the X68000 key hashes its own state sources, which do not change.

## Mega Drive: a larger player's record, anchored static discovery, and a learning pass when the last one still ran the interpreter (1.7.3)

Three changes that act on what a Mega Drive player meets **past the conversion's routes**. Measures are kept apart: everything below is native code (and what the
interpreter still ran); none of it says anything about CPU fidelity, hardware fidelity, gameplay or latency. A walk is 36,000 frames of pseudo-random pad input with a
seed no conversion uses, run on the delivered game: a script, not a person playing.

### 1. The player's record: a bound per machine, the Mega Drive at 65,536 notes

The record an exported game writes (`datas/fallbacks/<system>-<sha256>.rrfb`, F12) held at most 4,096 notes for every machine, so one play session handed the next
conversion at most 4,096 roots. Ultimate Mortal Kombat 3 (not in the shared base) met 13,871 distinct unknown ROM entries in one walk and filled the file (131,168 bytes).
`retrorecomp/systems` now has `feedback_limit` per profile (default 4,096; **only the Mega Drive** sets 65,536), `native/runtime_feedback.c` takes it from
`RR_FEEDBACK_LIMIT` in the generated config header, and `retrorecomp/feedback.py` reads and writes the same two shapes. Designed and reviewed by a Fable agent
(`md-record-cap-design.md`).

- **Format:** the 96-byte header and the 32-byte records are unchanged. A file of 4,096 records or fewer is **version 1, byte for byte what 1.7.2 wrote** (two sha256 pins in
  `tests/test_feedback.py`); a file of 4,097 to 65,536 records is **version 2** (at most 2,097,248 bytes). An old file of any machine loads as before.
- **What is refused is counted:** the header's `dropped` now counts **distinct** refused records (a lower bound, from a small bit filter; before, the game added 1 per refused
  call). The conversion log says "at least M more were refused: the record is full at 65536" for the Mega Drive; the report key `runtime_feedback` gains `limit` and
  `refused_records` (null for a 4,096 machine) and `max_bytes_per_game` per machine. A 1.7.2 file's raw call count is read as 0 where the bound is above 4,096.
- **Every machine, what changes:** the recorder reserves 152 KiB (was 144 KiB) for a 4,096 machine and **2.6 MiB for the Mega Drive**; a full file of a 4,096 machine now ends
  its log line with "more were refused: the record is full at 4096" (true, and it stays on at every conversion of a game whose file is full); `dropped` counts distinct
  records instead of calls (every reader only tests it against zero); if the recorder cannot allocate its merge buffers at exit it writes nothing and keeps the old file
  (before, it overwrote it with the session alone). Machines: Master System, Game Gear, Game Boy, NES, Super Nintendo, Neo Geo, X68000, CPS-1, CPS-2, PC Engine, Game Boy
  Advance, Amiga, Atari ST, Nintendo 64, PlayStation: bound 4,096, files unchanged. Adventure (ScummVM): no record.
- **Sharing:** the shared bank keeps 4,096 observations per game (`OBSERVATION_LIMIT`, unchanged; sharing declared roots is a later decision). `shareable_observations` now
  stops at 4,096 rows that have a ROM position and looks at most 8,192 rows (each costs a search of the ROM), so a 65,536-row record still exports a file that imports.
- **Older builds:** a 1.7.2 game exiting beside a version 2 file does not read it and **overwrites it with its own session** (no crash, the file stays valid; the converter's
  private copy survives); a 1.7.2 converter refuses a file above 131,168 bytes (ignored, "unreadable" in the collection). Both are the previous-release rule, not a break.
- **Proof (UMK3, scratch library, the default level):** the delivered game, after two walks, wrote **6,556 notes, version 2, 209,888 bytes, 0 refused** (the 1.7.2 bound
  would have cut at 4,096). The conversion beside that file read 6,556 candidates, compiled 43,491 native instructions, 0 interpreted opcodes on its routes, native equal to
  the reference and the compressed copy equal to it. Same walks on the result: the recorded seed **0 interpreted opcodes**; a seed never recorded **0.30 %** (1.26 M opcodes,
  860 distinct unknown entries). For comparison, with the old bound one round gave 0.55 % and 0.54 % on the same game (4,096 notes, 9-10 k entries left).
- **Not done / not measured:** the recorder's hot path on the Mega Drive grows its tables from 144 KiB to 2.6 MiB (a note is one hash, one slot, one 32-byte compare per
  interpreted ROM instruction): **frame cost not measured** (needs a quiet PC and Arthur's go); the Linux (flock) run of the self-test and the one-off run of the 1.7.2
  `runtime_feedback.c` beside a version 2 file were not done.

### 2. Anchored static discovery of 68000 code (Mega Drive)

Code reached only through a pointer table or a computed jump was found by observed execution only. `retrorecomp/megadrive_static.py` (new, Mega Drive only) reads the tables
**that already reached code indexes** and adds their targets as roots, never a scan of the ROM: seven rules (`MOVEA.L (d8,PC,Xn)` / `LEA` / `ADDI.L` + an indexed `JMP`/`JSR` through
long pointers; offset-word tables of Sega and Treasure code; PC-indexed rows of `BRA`/`JMP`; long ROM operands of reached `LEA`/`PEA`/`MOVEA.L #`/`MOVE.L #`), a table read bounded at 256
entries, at most 12 rounds, and a ceiling of about 32,768 added instructions. Every target passes a legality test (the decoder's own, plus refusal of `MN_ILLEGAL` and
`MN_OTHER`, a $0000 word, an odd or out-of-ROM target, overlap with reached code, and a stream too short); each refusal has one counted reason and `targets = accepted + refused`
per rule. Two optional rules (c2, a1u) are coded and **off**. Designed and reviewed by a Fable agent (`md-static-design.md`); the prototype and its measures are in `.build/p174-static`.

- **A wrong guess never runs as native code:** ROM is immutable, so the body for an address is the decode of the bytes at that address and runs only when the CPU's PC is really
  there; a root on data is dead code (size and build time only). Odd addresses and RAM are excluded; a banked cartridge above 4 MiB skips the rules and is counted. The roots go to
  `generate_steps` only, never into `game.toml`, never into the library, the shared base or the record.
- **Counted:** the report key `static_discovery` (per rule: targets, accepted, refused by reason; `roots_accepted`, `roots_refused`, `extra_instructions`, `rounds_exhausted`, `skipped`)
  and one conversion-log line ("Static discovery: N roots from reached code (+M instructions), K candidates refused (X at the cap)").
- **Figures** (instructions, native code only): Ultimate Mortal Kombat 3, first conversion at the default level: the static start went from **8,443 to 26,966** native
  instructions (773 roots, +18,523, 516 refused, the round limit reached); the first routes' interpreted main-CPU opcodes fell from **3,237,163 and 3,399,555 to 296,670 and 385,852**
  (demo, play, 3,600 frames each); after the first learning pass 17,135 became 32,267 native instructions and the routes ran **0 interpreted**, native equal to the reference. The
  walk of 36,000 frames (not a conversion route): **2.40 % to 0.31 % and 0.28 %** interpreted (two walks; 13,871 unknown entries became 5,628 and 6,151). Gunstar Heroes (paths from the
  base, quick check): 453 roots, **+7,438** instructions on 27,509 (34,947), 838 refused, 0 interpreted, native equal to the reference. Sonic 2: 157 roots, +2,777 on 33,879 (36,656), 549 refused.
- **Cost:** more native code. In instruction counts, a first conversion grows 1.1 to 3.2 times (Sonic 2 1.1, Gunstar 1.7, UMK3 3.2 in the prototype) and a played one 1.07 to 1.5. The
  decoder runs about twice per round: UMK3's `code generation` phase read 40.6 s against 1.6 s before the change, and 33.0 s after the decoder tool was built once instead of at every
  run (a PC in use, up to two conversions at once: not a benchmark, only the order of magnitude). What is left beyond the anchored rule is dispatchers entered only through object data and computed jumps into unrolled loops:
  no static rule finds them (Gunstar 343 and UMK3 471 routine heads in the prototype).

### 3. A learning pass when the last pass still ran the interpreter (Mega Drive and Super Nintendo)

A quick check from shared paths (the base holds them) asks for one pass, so the code its routes had just recorded on the interpreter stayed on it in the delivered game: Sonic 2's final
line read "Sound CPU: 8,604 interpreted Z80 opcodes", and a walk of 36,000 frames ran 286,260 (28 variants). Now, when the last pass the settings allow still ran interpreted opcodes **and**
recorded something learnable, **one** more pass learns it and regenerates the code (`console16.convert16`; the log says so, the report carries `residual_learning_pass: true`;
never more than one, never when the last pass ran none, never when nothing new was learned).

- **Proof (Sonic 2, quick check, scratch library):** pass 1/1 ran 8,604 and 8,346 Z80 opcodes interpreted (demo, play), learned 37 variants, and the second pass ran **0 and 0** (100 % native
  on the sound CPU); native equal to the reference, the compressed copy equal to it; one more pass in the conversion (127 s against 70 s in that run, a busy PC: not a benchmark).
- **Which machines:** the Mega Drive and the **Super Nintendo** (they share `convert16`): the behaviour changes only under those conditions; Donkey Kong Country (standard level, three
  passes) ended its first pass at 0 and took no extra pass. The Neo Geo, CPS-1, CPS-2, PC Engine, X68000, Amiga and Atari ST use only helpers of `console16.py` (`dependencies16`,
  `REPOSITORIES`) and their own conversion loops: **behaviour unchanged**, only their game stamps move with the file.

### Checked, and what moves

- Unit tests: the record format, profiles, compiled games, sharing, stamps (`tests/test_feedback.py`, `test_system_profiles.py`, `test_compiled_games.py`,
  `test_knowledge_exchange.py`), `tests/test_megadrive_static.py` (authored bytes only, one test with the real decoder), the pass loop (`tests/test_console16.py`); the native recorder's self-test
  (`tools/runtime_feedback_selftest.py`, portable toolchain: both a 4,096 and a 65,536 build, old files, a damaged file, two exits at once).
- **Stamps** (`tools/std_baseline.py`, tree `751866b8` against this one): the **game stamp of every machine moves** (`native/runtime_feedback.c`, `retrorecomp/feedback.py` and the profiles are
  inputs of all), with the Mega Drive's own (`megadrive_static.py`, `console16.py`); **no host and no build stamp** moves. The **quick-state key** of the Mega Drive, the Super Nintendo and the
  Master System / Game Gear build signature move (they hash the listed native files, which now include `runtime_feedback.c`); the Mega Drive and Super Nintendo keys had already moved in 1.7.3
  (the cartridge-save file), so a 1.7.2 quick state is refused cleanly as before. The Master System and the Game Gear have no quick-state key; the keys of the
  Amiga, the Atari ST and the Nintendo 64 take every input of their machine, so they move too (they move in 1.7.3 anyway). The four pinned 68000 generator files and `megadrive_codegen.py`, `megadrive_z80.py` are untouched.
  New files and their role: `retrorecomp/megadrive_static.py` (game, md), `tests/test_megadrive_static.py`.
- Existing exports are affected: every game's next conversion is a full one in the sense of this page (its game stamp moved).

## Every console: a conversion with its own library reads no player's record of the player's exports (1.7.3)

A conversion given its own library (`RETRO_RECOMP_LIBRARY_DIR`: a test, a campaign) still read the player's own records
(`datas/fallbacks/*.rrfb`) beside the player's exports and in the folders the Options name, so a test's counts could depend on what the
player had played. It now reads only the records beside its own output, as its path banks were already set aside
(`feedback._isolated`). A player's normal conversion is unchanged. Proof: `tests/test_feedback.py`. **Hot path:** no. **What moves:**
`retrorecomp/feedback.py` is a game-stamp input of every console (every game stamp moves in 1.7.3 anyway). **Quick states:** the keys of the Amiga, the Atari ST and the Nintendo 64 take every input of their machine, so they move (they move in
1.7.3 anyway); the other keys hash none of the files changed.

## Amiga, Atari ST, Nintendo 64, CPS-2, PlayStation, MSX: the build project is removed after publication (1.7.3)

The cleanup of build projects (`build_cleanup.classify`) knew the folders of the first nine machines only. A conversion on
the Amiga (`amiga/<host>/<engine12>/<game16>`), the Atari ST (`atarist/<host>/<engine12>/<game16>/<TOS16>`), the Nintendo 64
(`n64/<host>/<engine12>/<game16>`), the CPS-2 (`cps2/<set>-<sha12>`), the PlayStation (`psx/<sha12>`) or the MSX and MSX2
(`msx/<sha12>-<BIOS8>`) left its project in `.build` after publication, and Options > Common > Disk space never listed it: a
few hundred MB per game, without limit. These shapes are now rules like the others: a published game's project goes, with
the same game's projects under an older engine; the shared bases (engine references, the vAmiga, Hatari and Mupen64Plus
builds) never match. Projects left by earlier versions appear in Disk space. A test fails when a registered machine has no
rule. Proof: `tests/test_build_cleanup.py`. **Hot path:** no. **What moves:** nothing: `build_cleanup` is interface code,
which no stamp hashes.

## MSX, MSX2, Atari ST: a free firmware download refused by a mirror is tried three times (1.7.3)

C-BIOS (MSX, MSX2) and EmuTOS (Atari ST) are fetched from SourceForge on first use, which sends each request to a mirror; a mirror may refuse it. Each fetch tried once more after a refusal. (A failure seen during the 1.7.3 release check came from the maintainer's firewall, which blocks outgoing connections of programs it does not know, not from a mirror: WinError 10013 for every host.) The two fetches now share `updater.download_pinned`: up to three tries on a refused or broken connection, 3 then 6 seconds apart; a file of the wrong size or hash is never fetched again, and the sentence the player reads when every try fails is unchanged. Proof: `tests/test_updater.py`, `tests/test_atarist_profile.py`. **Hot path:** no. **What moves:** the **game** stamps of the MSX, the MSX2 and the Atari ST (they move in 1.7.3 anyway); host and build stamps and quick-state keys do not.

## Mega Drive, Super Nintendo, PC Engine: one cartridge-save file for the three (1.7.3)

The cartridge's save file beside the game was written three times: `native/md_battery.c`, `native/snes_battery.c` and `native/pce_backup.c` each carried their own load at start, their own two-second pacing, atomic write, size and header checks and set-aside of a file the game cannot use ([STANDARDS.md](STANDARDS.md), rule 1). The rules are now written once in `native/cart_save.c` and `cart_save.h`, and each machine's file keeps only what is its own: the format (magic, the identity words the file repeats, where its hash sits, the largest memory), its memory and its guards. The differences between the machines are named capabilities of the format, not silent divergences: the Mega Drive leaves a file it cannot use where it is and opens without saving, where the Super Nintendo and the PC Engine move it to `.unusable-N` and start blank; the PC Engine also reports a file that exists and cannot be read (notice 2). Nothing a player can see changes: the same file under `datas/saves/<game>-<card>.rrsram`, the same 112-byte header and size, the same moments of writing (the memory quiet for two seconds, checked every half second, a failed write retried after ten seconds, at once on exit), the same handling of a missing, short, long, damaged or read-only file. An old save still loads, and a bad one is never deleted and never blocks a game. Two cases the old code could not reach are tidied: a file is read into the buffer reserved at start instead of an allocation whose failure counted as a damaged file (the Mega Drive and the Super Nintendo), and a PC Engine whose machine is not there is refused instead of read at address zero.

**Proof.** `tools/cart_save_selftest.py` builds each machine's own entry points with `native/cart_save_checks.c` over a stand-in memory, with the portable toolchain (llvm-mingw), and runs them in a scratch folder: a fresh save and its pacing, a reload, nineteen kinds of file (empty, short header, short or long payload, another magic, version, size, ROM, identity word or hash, a changed byte, bytes no field covers), a folder where the file should be, a file where the folder should be, read-only files, the ninety-nine names taken, and the cases where saving is off. The program checks the written file against its own writer of the format and prints every result, notice, memory hash and byte left on disk. With `--against 683f22ea` (the sources of 1.7.2) it builds those too and requires the same log: 289 lines for the Mega Drive, 306 for the Super Nintendo, 326 for the PC Engine, equal line by line, so the bytes on disk are equal before and after. A change of the pacing by one millisecond in the new file is caught by the same comparison. The other self-tests of these saves (`megadrive_sram_selftest.py` and the Mega Drive and Super Nintendo cartridge checks) read the new file list.

**Hot path:** no (the file is looked at twice a second, outside the frame). **What moves:** the Mega Drive, Super Nintendo and PC Engine game stamps (`native/cart_save.c`, `native/cart_save.h`, the three machines' files, `console16.py`, `pce_build.py`): md `ed3a49ab59a8` to `fe76d6ca02f8`, snes `064bd8544d76` to `9926f19eb43f`, pce `aa7913b68d39` to `bcb4ccd25784`. Because `retrorecomp/console16.py` is a module of the whole 16-bit family, the game stamps of the Neo Geo, the CPS-1, the CPS-2 and the PlayStation move with it (`b45ca489a2c9` to `7ac8db94e287`, `28dd85714948` to `8a2840f6e587`, `cb7b5d304275` to `dff3d26878f1`, `4a3b197254a5` to `8b76809837b2`) although what their games run does not change; their host and build stamps do not move, and neither do any other console's. **Quick states:** no state holds the save file and no layout moves, but the Mega Drive and Super Nintendo quick-state keys hash their listed native files, so their values move with this change (checked on main, `1ff81f47` against `751866b8`): a quick state of 1.7.2 of those two machines is refused cleanly (no compatibility key is carried, [GAME_STATES.md](GAME_STATES.md)); nothing is lost but that state, and cartridge saves are kept. The PC Engine key does not hash these files.

## PC Engine / TurboGrafx-16: the player's own record, and a start with I after Run (1.7.3)

**The player's own record.** A PC Engine game now records, in a window, each instruction of the card that the interpreter ran (kind 20 of the shared recorder, F12, written at a normal
exit beside the game). The next conversion reads the notes back against the player's own ROM and declares them to the engine as roots, so the code the player reached becomes native; the report's
`runtime_feedback.recording_default` was true in 1.7.2 while no game recorded; it is now true because they do (and false on the Street Fighter II board). Proved on Blazing Lazers by script: an 18,000-frame walk went from 733,921 interpreted instructions to 0 after one
recording and one conversion, and equals its fresh reference on all 18,000 frames ([PC_ENGINE.md](PC_ENGINE.md#the-players-own-record-12-november-2026)). The Street Fighter II board does not record. If the engine refuses the roots, the conversion goes on without them.
**What the owner saw in 1.7.2 is answered once the owner plays:** code past the routes stays interpreted, counted and shown, until his own record has been converted.

**The start with I.** The conversion also tries one, two and three Run presses each followed by a tap of I, and keeps the best variant by the same rule. On the fifteen cards of the panel it was kept on two
(Military Madness, a real gain; Splatterhouse, a tie settled by one picture), and it does not help Boxyboy, whose start waits on a second Run. The panel of the new tree: 15 of 15 at 0 interpreted and 0 guard misses on every route,
on Windows.

**What moves:** only the PC Engine's game stamp (`native/pce_machine.cpp`, `native/pce_machine.h`, `native/pce_main.c`, `pce_conversion.py`, `pce_knowledge.py`); every game stamp moves in 1.7.3 anyway. A PC Engine
export of 1.7.2 is rebuilt when it is upgraded, and its quick states are refused cleanly, as after any change of the bridge. **Hot path (declared):** the game's step loop copies the program counter and the
eight bank registers and compares one counter at each step while the recorder is on (the default in a window); not timed. The frame cost against the 1.7.1 pin (1.09x and 1.04x, [below](#pc-engine--turbografx-16-the-larger-capture-format-shared-paths-the-walk-repair-and-the-exit-from-the-experimental-status-172))
is accepted by the owner and was not investigated further.

## Master System, Game Gear: the Z80 chain's second-machine seams completed (1.7.3)

**What changes.** The study of a second Z80 machine built its native stage on the chain of [the first step](#master-system-game-gear-the-z80-chain-made-ready-for-a-second-z80-machine-173) and found five places
where a machine that is not a Sega one had to work around it. They are closed in the shared chain; nothing is added to the Master
System or the Game Gear, and no machine is added.
- **A front end for a machine keyed by a region map.** With `--banked-step` its generator no longer gives the cartridge to the Sega
  cartridge parser (which strips 512 bytes from a file 512 bytes above a multiple of 16 KiB and looks for the TMR SEGA header):
  `z80_chain.generator_main` writes that machine's entry point, and `cg_emit_banked_mapped` (`native/banked_emitter.inc`) reads
  every source whole and pads it with FFh to whole regions. The Sega machines' entry point is the same text as before.
- **The start of a step.** `Z80Machine.step_begin` makes the loop call `smsrecomp_step_begin(prefix_pending)` at the start of every
  step. Off for the Sega mapper: the call is not written.
- **Redundant prefixes.** A machine that reads /INT at the end of the instruction (`irq_sample='instruction_end'`) no longer
  advances its hardware on each redundant DD/FD prefix. The Sega runner still does, as before.
- **The state copies.** `native/banked_reference_state.inc` (new) holds `state_to_hz` / `state_from_hz`, the copies between the
  translated registers and the reference CPU of the counted fallback; `Z80Machine.reference_state` pastes it ahead of the loop. The
  Master System and the Game Gear keep the pair of their pinned runner, because their generated glue must not change;
  `tests/test_z80_chain.py` compares the two pairs statement by statement.
- **A guarded window inside a region.** `BankedRegion` (region-map machines only) gains `guard_from` / `guard_to`: one window of a
  region that shows a source runs through the byte guards, the rest stays keyed by position.

**The output is identical.** For the Master System and the Game Gear nothing a conversion writes changes. `native/banked_runtime.inc`
is not edited. Proof, three conversions with the real command line (portable toolchain, Windows, a library of their own), once
with the code of main `6d8e27b7` and once with this change, both in the same folder:
- Sonic The Hedgehog (Master System, banked), Sonic The Hedgehog (Game Gear, banked), Alex Kidd in Miracle World (Master System,
  `--backend functions`).
- The 146 files the translator generates and the 77 other sources and inputs of the three projects are equal byte for byte; the
  three build logs differ by the times.
- The three delivered executables are equal byte for byte, and so are the unpacked ones and every object file.
- The 29 run records are equal but for wall-clock times (frames, VDP traces, RAM, final CPU state, native and interpreted counts).
- The two runs share one folder because the same code built in two different folders gave equal generated sources and executables
  that differ by a few bytes (43 in the Game Gear game, offsets to a few variables): the linked bytes can depend on the checkout
  path. This is true of main before this change too.

`tests/test_z80_chain.py` pins each seam as text (the Sega loop is still the file itself; what the other settings render). The
region-map form with the new front end and the window was run in an authored harness (44 checks: the 23 of [the first
step](#master-system-game-gear-the-z80-chain-made-ready-for-a-second-z80-machine-173), a cartridge of 32 KiB + 512 bytes read whole and padded, a window that guards the last quarter of a region). That
study's own comparison with its reference interpreter (authored cartridges, a free BIOS) was run on this change in a scratch copy of
its branch, with its glue as it is and with its glue moved onto the five seams: 14 of 14 cases equal both times. None of this is a
qualification of any machine, and it says nothing of CPU fidelity, hardware fidelity, gameplay or latency.

**Hot path:** no. The generated C of a Master System or Game Gear game is the same text, and the executables are the same bytes.

**What moves:** `native/banked_emitter.inc` and `retrorecomp/core.py` are game-stamp inputs of every console, so **every console's
game stamp moves** (it moves in 1.7.3 anyway); `retrorecomp/z80_chain.py` moves the game stamps of the Master System and the Game
Gear (group `shares:z80_main`). `native/banked_reference_state.inc` is declared out of the stamps (`NOT_INPUTS`) until a machine of
the converter uses it. Host and build stamps do not move.

**Quick states:** the keys of the Amiga, the Atari ST and the Nintendo 64 take their machine's build stamp, which `core.py` is an
input of, so they move (they move in 1.7.3 anyway). The Master System and the Game Gear have no such key; the other keys hash none of
the files changed.

## Atari ST: the player's own record (1.7.3)

An exported Atari ST game now keeps the player's own record (F12, on by default, in `datas/fallbacks` beside the game): windows of 16 bytes at instructions that ran on the interpreter, with the TOS they
ran on. The next conversion of that game reads it and makes native code of those instructions and of what a walk through each window finds, counted apart (`native_learned`, `native_walked`,
`player_record` in the report); no route proves them, the guard on the latched opcode is the same, and a window of another TOS or whose ROM bytes changed is not used. The record is private and never
shared. The walk is shared with the Amiga (`retrorecomp/m68k_record_walk.py`): the Amiga's `walk_records` now calls it, with identical results on three real records of players (Lotus 2 among them).
Measured on one scripted session each: Turrican II's window of play past its routes from 6.91 % native to 100.00 %, Indiana Jones from 569 interpreted instructions to 0; beyond the routes the native trace
equals the interpreted one. **What moves:** the Atari ST's game stamp and the Amiga's game stamp (the shared walk; no Amiga output changes); no host stamp, not the X68000's. **Quick states:** the Atari ST's
key moves, as between any two Atari ST builds. **Hot path:** nothing on native code; on an interpreted instruction, one test, and a 16-byte read and a record when a new window starts.

## Atari ST: a sweep over the memory at the end of the routes (1.7.3)

A conversion now walks an image of the RAM taken at the last frame of each fresh reference run, with the TOS ROM, from the instructions the routes ran, and compiles what it reaches as native code with the same
guard on the latched opcode (`retrorecomp/m68k_record_walk.py`, shared; `atarist_codegen.sweep`): branches, DBcc, JSR and JMP with an absolute or PC-relative address, and what falls through, from an
observed instruction the image still holds as observed, up to 60,000 instructions added (a capped sweep says so). They are counted apart (`sweep` and `final_checks.native_swept` in the report; the player's
headless report has `native_swept`); no route proves them, and on the routes the count is 0 by construction. The image is read by the conversion and deleted, never copied to the library or to the export; a page
fill (every even address of a page where code ran) is written and tested but off (measured once on Turrican II: 91.48 % native, 59,190 swept, 42.6 MB, trace equal). Measured on Windows, Standard level from an empty library, the delivered game on a play script of 5,200 (Turrican II, TOS 1.04) and
4,500 frames (Bomb Jack, EmuTOS): Turrican II's window of play from 6.91 % native to 73.00 %, Bomb Jack's 17 interpreted instructions to 0; native and interpreted traces of every frame byte-identical. Cost, on a PC shared with other sessions (so the times are indicative), a cold build of the same game's native code without and with the sweep, in turn: Turrican II 24-33 s and 19.6 MB against 61-81 s and 29.3 MB (packed 4.6 against 5.3 MB), Bomb Jack 38 s and 22.5 MB
against 49 s and 25.3 MB (packed 5.6 against 6.0 MB). `tools/atarist_sweep_guard_check.py` shows the guard on an authored program that rewrites a swept block before it runs it (another opcode: the routine never
runs, the interpreter does; the same opcode with another extension word: the routine runs and reads the new word). **What moves:** the Atari ST's game stamp, and the Amiga's game stamp as well, because
`retrorecomp/m68k_record_walk.py` (the walk shared by the two machines, which gained the sweep) is owned by both: no Amiga output changes, the Amiga's own sweep (`amiga_codegen.sweep`) is not touched. No
host stamp, not the X68000's. **Quick states:** the Atari ST's key moves, as between any two Atari ST builds. **Hot path:** nothing on native code (a swept instruction counts into one more counter); the exe is larger and
a conversion compiles longer in proportion to what is swept.

## Atari ST: the disks in the order their names mean, and a program chosen among several (1.7.3)

**What changes.** Two rules of the conversion, both read from names and from the root directory of disk 1, nothing run:
- **Disk order.** A ZIP's disks were taken in the alphabetical order of their member names, which put the wrong disk first when the boot disk is not the first by name
  (Battle Chess: the "Animation Disk" before the "StartUp Disk"; The Chessmaster 2000: "(Games Disk)" before the disk without a label; Mean 18: the "Famous Courses" disks before the
  "Program Disk"). `retrorecomp/atarist_disk.py` now puts them in disk order: the disk without a label and the boot disks (Boot, StartUp, Program, Main, Loader) first, then the numbered
  ones by number or letter (Disk 1, Disk A, Side B, Reel 2, Volume II; Disk 10 follows Disk 9), then the disks that only have a name; a name without brackets is read from its end
  (`game2.st`, `game_b.st`). Of the 79 multi-disk ZIPs of the library tried (names only), exactly those three change order.
- **Several programs on disk 1.** When disk 1 has no `AUTO` folder, the desktop autostart took the only program of the root and nothing otherwise. It now also takes, among several, the
  one program whose name is a word of the game's title (`CRICKET.PRG` for Championship Cricket), or else the only one that is not a utility by a short list of names (setup,
  config, format, read, view, help, backup, copy, unpack...). Two programs that fit, or none, leave the choice to the player, who opens the program at the desktop; `desktop_autostart` in the
  report gives the program, the `candidates` of the root, the `rule` (`only-program`, `title-word`, `only-non-utility`) and the `reason`. A lone program is started as before.

**Library.** Of the 18 ZIPs that stopped on the desktop in the census of 12 November 2026, six now start their program (Battle Chess, The Chessmaster 2000, Championship Cricket, Logical,
Outcast, Rody et Mastico III) and twelve are left to the player (Backgammon Royale, Chess Simulator, Conquests of Camelot, Mean 18 and Mercenary have several programs no rule picks; Battle
Probe, Kick Off 2 - Winning Tactics, Leader Board, Metro-Cross, Pac-Mania, Trailblazer and World Class Leader Board have no program at their root). The decision of the other 257 ZIPs is the one it was.

**Proof** (Windows, EmuTOS 1.4, Standard level, 3,600 frames on two routes, headless; every route of the native game and of its packed copy equals the fresh reference, and the saved state
continues the run): The Chessmaster 2000 (disk order, then `CMASTER.PRG`) reaches its title, which shows an alert from the game ("Lost my BIG pieces!"); Battle Chess (`CHESS.TOS`, the
StartUp disk first) reaches a screen of its own, a prompt that looks like its manual protection; Championship Cricket (`CRICKET.PRG`) reaches a match; Outcast (`OUTCAST_.PRG`) reaches
its title; Mercenary (two programs that both fit) stops on the EmuTOS desktop and the report says why. These are first screens on the tested routes, not played games.

**Hot path:** no. **What moves:** the Atari ST's game stamp (`9159a9d9c95b` to `9aad96e2808d` with the other Atari ST changes of 1.7.3, measured on main `6d8e27b7`; the conversion modules `atarist.py`, `atarist_disk.py` and `atarist_conversion.py`); its host stamp and its
build stamp do not, and no other machine moves. A game of this machine converted before is reconverted in full on its next conversion; an export keeps playing as it did. **Quick states:**
no native file of the session or the player changes, so the format of a state is the one of before.

## Atari ST: Hatari's timer D patch chosen per game (1.7.3)

**What changes.** Since 1.7.2 every Atari ST game ran Hatari's patch of the MFP's timer D, which slows down TOS's own start of that timer and changes what a game that uses the timer as TOS left it sees. Now the patch is chosen per game. The new option **Atari ST: timer D** (`atarist_timer_d`, `--atarist-timer-d`, in the request signature) is `auto` by default, `patched` or `exact`. On `auto` the fresh references run with the patch, and a detector in the adapted Hatari counts, from outside the TOS's addresses, a read of TDDR (A), timer D's interrupt left enabled and unmasked without a write of TDDR or a start (B) and TCDCR started before any write of TDDR (C); reads of TCDCR (D) are counted and never decide. A sign on any route makes the references run again with the patch off, and the game is built and validated on that machine. The reference, the native game and its packed copy always run the same mode: each run's report says which, and the conversion refuses a run of another mode (it refused any run without the patch before). `machine.timer_d` in the report says the mode, the choice, the reason (the sign, the frame, the pc, the route) and every sign by route. The detector sees the code the routes reach and nothing else, and the TOS's own code is not looked at ([ATARI_ST.md](ATARI_ST.md#5-known-limits)).
**Seen:** Bomb Jack (EmuTOS) shows no sign and stays patched; The Seven Gates of Jambala reads TDDR (A, frame 779, pc `$0106F8`) and runs exact, 4 interpreted instructions on a route; both validate on every route and on the packed copy. An `exact` game costs about 1.3 to 1.8 times the host cycles of the same game patched (the 9 November estimates, not a timing).
**Hot path:** no change for a game that stays patched; the detector is three comparisons on a register access of the MFP, none per instruction. A game that runs exact runs a heavier machine, as before 1.7.2.
**What moves:** the Atari ST's game stamp (`9159a9d9c95b` to `9aad96e2808d` with the other Atari ST changes of 1.7.3, measured on main `6d8e27b7`; the session, the player, the conversion, the Hatari adaptation and the profile are in it), the Hatari adaptation digest (`e89a52b7e31d` to `1bb961c240a8`: the machine core is built again once), and the request signature of every Atari ST export, which now holds the option; the host and build stamps and every other console's stamps do not move. An Atari ST export of an earlier version is rebuilt when it is upgraded, and a game that now shows a sign is reconverted on the exact machine. Quick states: the Atari ST's key moves, as between any two Atari ST builds. Tool: `tools/atarist_hardware_check.py` measures the detector (51 measurements, 49 agree, the same 2 recorded differences).

## Mega Drive: the limits of the learned code are counted, never silent (1.7.3)

The Mega Drive keeps three tables of code it learned from the runs: the work-RAM instructions (2,048 distinct variants, in the exported
game's recording table and in the library), the Z80 opcode variants (32,768) and the driver images whose 8,192 positions are all compiled
(4 per run). What did not fit was dropped without a trace: an instruction past the limit is not recorded, so no later pass compiles it, and it
stays on the counted interpreter, but nothing said why. It is now counted and reported at every place that cuts:

| Where it is cut | What counts it |
|---|---|
| the exported game's recording of work-RAM variants (`native/md_backend.c`, 2,048) | `ram_observation_overflows` (observations of a variant that no longer fit), `ram_variants_dropped` (distinct ones, from a table of 4,096; `ram_variants_dropped_exact` is false if that table saturated, and then the distinct count is a lower bound) and `ram_variant_limit`, in the report of each probe (so in each `final_checks` row and in each row of `passes`) and in the conversion log (the line the Super Nintendo already had, now for the Mega Drive too) |
| the library of work-RAM variants (`megadrive.py`: the lowest addresses are kept, as before) | `megadrive.ram_variant_overflow`: distinct variants known against the limit, and how many are past it |
| the Z80 variants the game could not record (`z80_dropped_variants`, already in the probe report) | now also in the conversion log, like the RAM line |
| the library of Z80 variants and the driver images (`megadrive_z80.py`: 32,768 variants, 4 images per run) | `megadrive_evidence.z80_limits`, read after the last learning: the library's size against the limit (`library_full` when it is at it), how many variants the runs observed are not in it (`observed_dropped`), and the driver images past the first four of a run (`images_dropped`); `megadrive_z80.py` itself is not edited (it is a pinned CPS-1 generator source) |

One block ties them together, `learning_limits` in the conversion report (`megadrive_evidence.learning_limits`): the limits, what is known, what is
past each, the game's own counts, `anything_cut`, and the claim that what is past a limit is not recorded and stays on the counted interpreter. When
anything was cut, the conversion log says so in one line. **What is dropped is the same as before:** the variants that are kept are the same, so no
generated code changes; the selection (lowest addresses first) is left as it was, and a "keep the newest" rule is not part of this change. The instructions
past a limit are already counted as interpreted fallback (`ram_fallback_opcodes`, `audio_interpreted_opcodes`, and `main_interpreted_opcodes` in the batch
result); what is new is the cause. The common report v2 (`report_schema.py`, the lead's) does not read `learning_limits` yet.

**Figures.** The 27 October snapshot gave the largest known records: 1,261 work-RAM variants (62 % of 2,048; the cartridge is not among the owner's
exports) and 23,436 Z80 variants (72 % of 32,768, Altered Beast). Read by this change's conversions (quick check, scratch library, shared paths on):
Altered Beast (USA) 34 RAM variants of 2,048 and **23,437 Z80 variants in the library, for a limit of 32,768 (71.5 %)**; Gunstar Heroes (USA) 389 of 2,048 (19 %) and 15,903 Z80 variants
(48.5 %); both with nothing cut, 0 interpreted on both routes, native equal to the reference. A limit **is** reached by an authored cartridge
(`tools/megadrive_variant_cap_selftest.py`: a loop writes 3,000 `MOVEQ` words to work RAM and calls them): 3,001 distinct RAM instructions against 2,048,
the game records 2,048 and reports 953 observations and 953 distinct variants dropped, the library holds exactly 2,048, native equals the reference; the same
cartridge converted whole (`batch`): pass 1 interprets 3,001 main CPU opcodes and says 953 were past the limit, pass 2 runs 2,048 natively and 953 stay
interpreted and counted on both routes, `learning_limits` says 3,001 known for 2,048 (953 past the limit), and the compressed copy matches the reference.
A control with 1,000 words reports 0 everywhere.

**Is a bigger limit cheap?** In the game, yes: the RAM table is `M68KInstr ram_variants[2048]`, 60 bytes each (123 kB; 8,192 would be 491 kB), and each
variant is one more guarded body to compile; the Z80 table indexes with 16 bits, so 32,768 could rise to 65,535 at about 128 kB more. In the shared record,
no: the field caps `('ram_refs', 2048)` and `('z80_refs', 32768)` of `path_profiles.LEGACY_FIELDS` (and the site's checks of the same table) decide what a record
may hold, so a bigger local limit would only be lost when shared. Raising them is a format revision, not a Mega Drive change. With 62 % and 72 % of the
limits used by the largest known games, and four driver images alone able to fill the Z80 limit (4 x 8,192 positions), the counters are what decides: raise a
limit when one of them shows a game that reaches it.

**What moves.** Game stamps: the Mega Drive (`md_backend.c`, `megadrive.py`, `megadrive_evidence.py`, `console16.py`), and the CPS-1, the CPS-2, the Super Nintendo, the
Neo Geo and the PC Engine through `console16.py` alone (their behaviour does not change: the line the Super Nintendo had is now written for both, and the
new block is the Mega Drive's alone). `megadrive_z80.py` is **not** edited (the CPS-1 pins it, `tests/cps1_generator_pins.json`; the Z80 counters read it from
outside), so no CPS-1 generator pin or `GENERATOR_REVISION` is involved. Host and build stamps of every
console: unchanged (stamp baseline, `tools/std_baseline.py`, before and after). **The quick-state key of the Mega Drive moves** (`md_backend.c` is one of the
native files `RR16_STATE_ABI` hashes: `d76e8413…` becomes `3b585e00…`): Mega Drive quick states written by a 1.7.2 game are refused cleanly by a 1.7.3
game (the N-1 rule of this page, no compat key); cartridge saves are not affected, and the state layout is not touched. The keys of the Super Nintendo, the
CPS-1 and the Neo Geo do not move (same digests). The four 68000 generator files that the CPS-1 and the X68000 pin (`m68000.py`, `m68000_state_rules.py`,
`megadrive_rules.py`, `neogeo_codegen.py`) are not touched. New file and its role: `tools/megadrive_variant_cap_selftest.py` (no stamp; in `PUBLIC_FILES`).

**Cost.** None on the hot path: the new code runs only when a RAM instruction does not fit, which is the slow path that already scans 2,048 entries.
The report grows by four numbers per probe.

**Checked.**

- unit tests: `LearnedCodeLimitsAreCountedTests` (the library counts, the Z80 library and its images count, the driver images learned are the first four of
  each run, the report block and its exactness flag), the console, report-writer, stamp and Mega Drive suites;
- `megadrive_variant_cap_selftest`: below and past the limit, native equal to the reference (figures above);
- the authored cartridge converted whole, and Altered Beast and Gunstar Heroes converted from a scratch library (figures above);
- A/B (`tools/ab_conversion.py`, `e4ec565b` against this branch, Gunstar Heroes (USA), standard scan, empty library on both sides): both convert, 504 files
  compared, and **only nine differ**: `md_backend.c` (the change), `generation-identity.json` (the stamps), `hardware-profile.profdata` (the compiler's profile of the
  rebuilt binary) and the six probe result files, whose only differences are the four new keys (`ram_observation_overflows`, `ram_variant_limit`,
  `ram_variants_dropped`, `ram_variants_dropped_exact`); in the conversion report the differences are those keys, `learning_limits` and the new fields of
  `passes`, and the packed size ratio (0.3488 against 0.3487, a different binary). Every generated step, every picture, sound, CPU, RAM, VDP and Z80 hash is equal.

## Neo Geo: the code the reference runs could not keep is counted and reported (1.7.3)

**What changes.** The reference runs of a Neo Geo conversion keep at most 4,096 variants of work-RAM 68000 code and 4,096 variants of
Z80 code (`RR_NG_VARIANT_CAP`, `native/neogeo_reference.h`). Past that, a note was dropped without a trace: the Z80 side had no counter,
and the 68000 side wrote a flag (`m68k_ram_observations_truncated`) that nothing read. Now:
- the executable's reference report writes `variant_cap`, `m68k_ram_variants_dropped` and `z80_variants_dropped` beside the flag;
- the conversion report has a `native_discovery` record: the cap, the same figures per route, their maximum over the routes (never a sum),
  the flag read from every route, and `observed_code_dropped`;
- when something was dropped, the conversion says so in its log. Dropped code is not translated: a run that reaches it uses the counted
  interpreter fallback, shown as before in `final_checks` and in the game.

A dropped count is a number of notes, not of distinct variants: a variant met again counts again. No game of the panel reaches the cap
(the most observed 68000 variants are 565, on Matrimelee, and 1 Z80 variant on every set read), so the counters read 0.

**What it does not change.** The code generated for the game: the counters sit after the point where a variant is kept or dropped, and
the generators are untouched. A report of an earlier build has no `native_discovery`.

**Hot path:** no. The counter is a store on the path that already drops a note, at conversion time only (the reference runs).

**What moves:** the Neo Geo game stamp (`native/neogeo_main.c`, `neogeo_reference.c`, `neogeo_reference.h` and `retrorecomp/neogeo_conversion.py`
are Neo Geo files); the CPS-1, CPS-2 and X68000 stamps and the two generator pins do not (`neogeo_codegen.py` is not edited). The
Neo Geo quick-state key **moves**: it hashes `native/neogeo_reference.c` among its state files (and the code of `neogeo_build`, `neogeo_codegen`
and `neogeo_z80`), so a Neo Geo quick state of 1.7.2 is refused cleanly.

## Super Nintendo: the rows the RAM-code limit leaves out are counted (1.7.3)

The three places of `supernintendo.py` that cut the RAM-code tables at `RAM_VARIANT_LIMIT` (16,384 rows) left no trace: the merged read of the
guarded RAM variants, the merged read of the RAM opcode guards, and the merge a conversion writes back into the library (`native-ram.json`). Each keeps the
lowest addresses and drops the rest, as before; what is new is that the number of rows there were is kept (`supernintendo.row_counts(rom)`, per kind: `ram_variants`,
`ram_opcodes`, their `_own` forms and `library_merge`). The conversion report of a Super Nintendo game carries it as `library_rows` (`{kind: {limit, rows,
dropped}}`), and the conversion log says so when a kind left rows out. The line printed when a run met more distinct RAM instructions than the native table keeps
(`ram_observation_overflows`) no longer says those instructions stay on the counted interpreter: since 1.6.7 they run from their live opcode, compiled and counted as
compiled and not observed. **What a game does is unchanged**: nothing that is read, kept or generated differs (counters only).

How near the limit is: two conversions at the standard level from an empty library (Dirt Racer, Star Fox 2 (USA), the two cartridges the shared base holds the most
RAM-code rows for) read 7,827 and 8,517 rows (48 % and 52 % of the limit, 0 left out); native equal to the reference on both routes, the compressed copy equal to it, 0
interpreted opcodes of the 65816 and the SPC700. The shared record of the base is nearer: Dirt Racer 13,354 rows of `ram_opcode_refs` of 16,384 (82 %), Godzilla - Kaijuu
Daikessen 12,330, the two Star Fox 2 11,974 and 11,469, of 314 records (four above 8,192). *Raising the limit:* the local limit is two constants (`RAM_VARIANT_LIMIT` and
`RR_SN_RAM_VARIANT_LIMIT` of `native/snes_native_steps.h`, a power of two for the hash of `snes_backend.c`; 32,768 would add 192 KiB of static arrays to the game, and moves
the Super Nintendo's quick-state key), but it is not the limit that binds: what travels is bounded by the field caps of `path_profiles.LEGACY_FIELDS` (`ram_refs` and
`ram_opcode_refs`, 16,384 rows each), which the exchange validates and from which the site's limits are generated (`tools/build_web_limits.py`); a record over a cap is refused
by a converter that does not know the new one and by the site until its limits are deployed. So a raise is a format and site decision, not a one-line change; none is made here.

Stamps (`compilation_inputs.role_stamps`, the tree of `e4ec565b` against this one): the game stamps of the Super Nintendo move, and of the Mega Drive, the Neo Geo, the CPS-1, the
CPS-2, the PC Engine and the PlayStation with it (`console16.py` is a game input of those machines: it holds the report key and the log line; `supernintendo.py` is the
Super Nintendo's); no host and no build stamp moves, and the quick-state key does not (no native file and no pinned revision changes).

## Master System and Game Gear: the cap on compiled RAM windows is counted (1.7.3)

The banked engine compiles at most 4,096 RAM windows per ROM (`library.PATTERN_LIMIT`; the generator reads the same file). `GameMemory.code_patterns()` cuts at that limit, so the
report's `compiled_windows` and `pending_windows`, both taken from it, could never show that a window was left out. The report now says it: `learning.native_profiles` gains
`window_limit` (4,096) and `windows_over_limit`, the number of distinct windows the ROM's journal, the candidates of its own feedback and the shared hints hold beyond the limit
(0 when none was left out; the journal itself keeps them). Nothing is compiled differently and no game changes: the largest known ROM holds 0 of them in the shared base, so the cap is a
bound today and now a visible one. Reports, not games.

**What moves.** `retrorecomp.core` and `retrorecomp.library` are inputs of every console: the game stamp of every machine then moves with this change like with any edit of `core.py`
(the generated game is the same); the host stamps do not move. The quick-state keys of the Amiga, the Atari ST and the Nintendo 64 take their machine's
build stamp, so they move (they move in 1.7.3 anyway); the other keys do not. An export made before carries no `windows_over_limit` (it reads as absent, not as 0).

## Master System, Game Gear: the Z80 chain made ready for a second Z80 machine (1.7.3)

**What changes.** The banked Z80 engine carried the Sega mapper as constants: the bank key `b0, b1, b2`, three 16 KiB slots, a first
KiB that never pages, code from RAM at `pc >= $C000`, the plain Z80 cycle table and /INT sampled at the start of a step. They are now
one description per machine, `Z80Machine` in the new `retrorecomp/z80_chain.py`, which the profiles of the Master System and the Game
Gear name (`z80_machine = SEGA_MAPPER`). The emitter (`native/banked_emitter.inc`) reads it and names no mapper or address of its
own; the step loop (`native/banked_runtime.inc`) is unchanged, and `z80_chain.runtime_source` renders its machine-dependent lines.
The description also has what a second machine will need and no machine uses yet: wait states per M1 cycle, /INT read at the end of
the instruction, and a second way to key the code, by a region map over several sources with RAM in any region (`Z80RegionMap`).
A machine also names the folders of its own build of the translator (`generator_tag`; `core.dependencies` and
`core.compiler_signature` take the machine), and `cpu.prepare_reference` can make the reference CPU count its M1 cycles
(`m1_counter`), from which the counted fallback adds the wait states. For the Sega mapper the tag is empty and the count is off:
the same folders, the same signature, the same reference CPU. No machine is added.

**The output is identical.** For the Master System and the Game Gear nothing a conversion writes changes. Proof, three conversions
with the real command line (portable toolchain, Windows), once from main `f12dc2df` and once from this change, in two separate
checkouts with a library of their own:
- Sonic The Hedgehog (Master System, banked), Sonic The Hedgehog (Game Gear, banked), Alex Kidd in Miracle World (Master System,
  `--backend functions`).
- The 146 files the translator generates and the 77 other sources and inputs of the three projects (the patched glue, the Z80 headers,
  the reference CPU, the configuration) are equal byte for byte; the three build logs differ by the checkout path and the times.
- The three delivered executables are equal byte for byte, and so are the unpacked ones.
- The 29 run records are equal but for wall-clock times and the checkout path (frames, VDP traces, RAM, final CPU state, native and
  interpreted counts).

`tests/test_z80_chain.py` pins that the step loop rendered for the Sega mapper is the file itself, and what another machine renders.
The region-map form was run once in an authored harness (two sources, a map that changes, RAM in a low region, an instruction across
a region edge, one wait state per M1): 23 checks. It is not a qualification of any machine, and it says nothing of CPU fidelity,
hardware fidelity, gameplay or latency.

**Hot path:** no. The generated C of a Master System or Game Gear game is the same text, and the executables are the same bytes.

**What moves:** the game stamps of the Master System and the Game Gear (their profiles, the new module, the group `shares:z80_main`
that now holds `retrorecomp/cpu.py`). `native/banked_emitter.inc` and `retrorecomp/core.py` are game-stamp inputs of every console,
so **every console's game stamp moves** (it moves in 1.7.3 anyway, see the next section). Host and build stamps do not move.

**Quick states:** the keys of the Amiga, the Atari ST and the Nintendo 64 take their machine's build stamp, which `core.py` is an
input of, so they move (they move in 1.7.3 anyway). The Master System and the Game Gear have no such key; the other keys hash none of
the files changed.

## Every console: a step still writing goes past its time limit (1.7.3)

A player's small PC needed more than 30 minutes to compile Kirby's Adventure, and the conversion stopped at the step's fixed limit
while the compiler was still finishing files. The build and generation steps (`core.run`: CMake, the compilers, the recompilers) now
go past their limit while they are still writing (a compiler prints a line per finished file), as long as their last line is younger
than the limit, up to four times the limit (`PROGRESS_LIMIT_FACTOR`). A step that writes nothing for a whole limit is stopped as
before, and Stop still kills it at once. Replays and probes keep their fixed limit. The shared setup lock (the SDL build) waits as long.
A step stopped this way is named with the time it ran, in minutes. The game report lists the five languages a generated game ships
(`ui_languages`; it listed the converter's eight), and the CPS-1 and CPS-2 print "no interpreter on the routes played" when a set is
ready without a fallback, as the PC Engine does. Proof: `tests/test_stop_now.py` (a writing step past its limit, a silent one stopped at
it, an endless writer stopped at the ceiling, text decoded as `subprocess.run` does). **Hot path:** no, nothing in a game changes.
**What moves:** `retrorecomp/core.py` and `batch.py` are game-stamp inputs of every console, so **every console's game stamp moves**:
an export of 1.7.2 is converted again at the upgrade (the quick upgrade above, from its learned paths). The shared paths of the base are kept (they are qualified by the
recompiler's revision, not by this stamp). **Quick states:** the keys of the Amiga, the Atari ST and the Nintendo 64 take their machine's build stamp, which this change moves, so they move; the other keys hash none of the files changed (see the index above).

## Commodore Amiga: Denise's line work by table and by word, Agnus's clock step inlined (1.7.3, Agnus/Denise step 1)

Hand optimisations of emulated code, through vAmiga's adaptation (`retrorecomp/amiga_vamiga.py`): the same events at the same instants and the same bytes in every buffer after each
function, fewer operations. Denise's draw routines take a shift register's slices from a table and write the line buffer four or two entries at a time; when both parities are armed
at the same offset one pass writes what the two passes wrote. The dual-playfield translation runs vAmiga's own loop once on the 256 possible bytes for a playfield state and then
looks each pixel up. The palette pass takes eight entries at a time where none is border. `Agnus::execute`, called at every colour clock, is defined in its header so it can be
inlined. Agnus and Denise stay emulated; nothing here is specialised from a game. ThinLTO of the Core, the session and the player (`RR_AMIGA_THINLTO`, clang only; llvm-mingw on
Windows) is on: a quiet-PC timing on 10 November 2026 (Lotus 2's native game, 2,400 frames of a racing route, one core, two interleaved runs per build) gave 2.571 ms of
machine time per frame before this step, 2.245 ms with it (-12.7 %) and 1.992 ms with it and ThinLTO (-11.2 % more), past the 3 % bar Arthur set; the two ThinLTO runs differed by
7 %. A second quiet pass on 11 November (four interleaved rounds, the rounds of each build within 3 %): 2.493 ms before, 2.158 ms with this step (-13.4 %), 1.887 ms with ThinLTO
(-12.6 % more); the 7 % did not come back. This is the cost of a frame on one PC, not a latency.
Proof: `tools/amiga_display_selftest.py --against` the build made before the change: 40 scenarios of 4 frames (1,301,275 instructions) and the 12 of the default run, every
instruction's record and every frame's record equal; each of the four new paths broken on purpose in its own build is seen (in 3 to 6 scenarios of 6). Lotus 2's native game and the
reference player, built before and after (and after with ThinLTO), give the same trace on every one of 3,600 frames of a racing route (picture, sound, RAM, registers). The first-read
conversions are not done yet. **What it brings:** the timing above, on one game; an earlier estimate from shares of a loaded PC was 12-17 % (21-25 % on a dual-playfield game). **Hot path:** this is one. **What moves:** vAmiga's adaptation and the Amiga's game stamp; no other console. **Quick states:** the Amiga's key moves, as between any two Amiga
builds; the dual-playfield table is derived and rebuilt after a load.

## Commodore Amiga: a line's bitplane slots taken in a batch (1.7.3, Agnus/Denise step 2)

Agnus no longer schedules an event for every bitplane slot of a line whose plan allows it. At the start of such a line its bitplane DMA slots are marked taken on the bus, as
vAmiga's own events mark them before anyone else in their colour clock, and they run later in their own order, each at the beam position of its slot, as soon as something could
see them: a custom register access by the CPU or the Copper, a chip RAM write (CPU, Blitter, disk DMA, the host's patches) into a fetch still to come, a read of the open bus,
the start of a register-change event (HSYNC and EOL among them), and vAmiga's own bitplane event. The data bus keeps the colour clock of its last value, so that a fetch run late
never covers a later one. The guard, decided per line: no AGA, never line 0 (where a host frame ends), every bitplane DMA slot between $18 and $E1, no super-hires fetch, each
plane's modulo on its last fetch, every fetch in chip RAM; a new plan in the middle of the line (DDF, BPLCON0, DMACON, the vertical window) or a pointer moved out of chip RAM gives
the rest of the line back to vAmiga's events. Through vAmiga's adaptation (`retrorecomp/amiga_vamiga.py`, MPL-2.0 edits). Agnus stays emulated: the same work, at fewer
scheduled instants; nothing is specialised from a game. The lines and words batched, on events and given back are counted per route in the conversion report
(`final_checks.agnus_denise`, with the device notes under `hardware_devices`).
Proof: `tools/amiga_display_selftest.py` now runs each scenario batched and with `--per-slot` (every line on vAmiga's events) in the same build: 12 scenarios of 4 frames (420,350
instructions; 9,755 lines batched, 488 given back midway, 5,069 on events), every instruction's record and every frame's record equal. `--against` the frozen build of step 0:
40 scenarios of 4 frames (1,297,343 instructions; 32,161 lines batched, 1,940 given back, 16,119 on events), all equal. The scenario program gained reads of write-only registers
(they write the last bus value into them), BPL1DAT writes and pointer writes. A first version missed one case, found by the self-test on 9 NTSC scenarios out of 52: on an NTSC
long line vAmiga runs the bitplane event of position 227, which came before slots still pending; that event now runs them first. Each barrier broken on purpose in its own build is seen against `--per-slot` on 8 other scenarios: the
register-event barrier 8 of 8, the give-back of the marks 8 of 8, the custom read barrier 7, the custom write barrier 6, the bus clock 6, the bitplane-event barrier 2 (the NTSC
ones), the chip RAM write barrier only 1 of 8 (a random write seldom lands ahead of the beam in the same line: that barrier is the least exercised). Lotus 2's native game and
the reference player built with this step (and ThinLTO) give the same trace as the build before step 1 on every one of 3,600 frames of a racing route. First-read conversions
with the real command line (11 November 2026): Lotus 2, Pinball Dreams (NTSC) and Shadow of the Beast, two routes of 3,600 frames each, every frame equal to the fresh
reference, 0 instructions interpreted. **What it brings:** on a quiet PC, 11 November 2026, one core, Lotus 2's racing route of 2,400 frames, four interleaved rounds, the
machine time per frame goes from 1.887 ms (step 1 with ThinLTO) to 1.809 ms (-4.1 %; rounds within 2.1 %), past the 3 % bar; one game, not a latency. **Hot path:** this is one. **What moves:** vAmiga's adaptation and the Amiga's game stamp; no other
console. **Quick states:** the Amiga's key moves, as between any two Amiga builds; the batch state is derived, never saved (line 0, where a state is taken, never has one).

## Commodore Amiga: a quiet line's pass in one loop (1.7.3, Agnus/Denise step 3)

At the end of every visible line Denise translates its line buffer into colour indices (`translate`), draws the sprites, checks playfield collisions and turns the indices
into the texture row (`colorize`). On a quiet line the colour index of each buffer byte depends only on that byte and on the line's start state, so `translate`'s own loop is run
once on the 256 possible bytes for that state (kept in a table, rebuilt when the state changes) and the row is written in one pass: index through the table, then the palette
or the border colour, eight entries at a time where none is border. Colour changes inside the line are applied between chunks, as `colorize` applies them; the collision check
runs as before. Quiet means: no sprite armed or recorded in the line, no BPLCON0, BPLCON2 or BPLCON4 change in it, no HAM, no super-hires, no border sprites, no hidden bitplanes
or X-ray layers, not AGA, and the next line visible (vAmiga's VBLANK branch reads the buffers `translate` leaves, so the last visible line takes vAmiga's pass). Every other line
takes vAmiga's line pass. Through vAmiga's adaptation (MPL-2.0 edits). Denise stays emulated; the plan's draw list and per-game routine keys were not needed for this first
form, so nothing is specialised from a game: it is a hand optimisation of the same work, with a guard. Counted per route in `final_checks.agnus_denise` (visible lines in one
pass, on vAmiga's pass).
Proof: the display self-test with steps 2 and 3 against `--per-slot` (both off) on the 12 default scenarios (12,176 visible lines in one pass, 1,460 on vAmiga's pass) and
`--against` the frozen build of step 0 on 40 more (37,896 and 6,560), every instruction's and every frame's record equal. A first version differed on Denise's snapshot only, with
the same pictures: `translate` writes its end-of-line entry into the change history before clearing it, and those entries are saved; the one-pass line now does the same. Each
rule broken on purpose in its own build is seen against `--per-slot` on 8 other scenarios: a wrong table entry 6 of 8, a colour change skipped 7, the border ignored in a block 6,
the collision check skipped 8, the sprite guard off 2, the BPLCON-change guard off 6, the history entry not written 1. Lotus 2's native game and the reference player built with steps 2 and 3 give the same trace as the
build before step 1 on every one of 3,600 frames of a racing route; on that route 1,123,512 lines were batched and 3,601 ran on events (line 0 of each frame, none given back),
and 1,029,889 visible lines were passed in one loop against 3,601 on vAmiga's pass (the last visible line of each frame). **What it brings:** on the same quiet pass, 1.809
to 1.710 ms per frame (-5.5 %; rounds within 0.7 %); steps 1 to 3 with ThinLTO together, 2.493 to 1.710 ms (-31.4 %) on Lotus 2's route, one PC, not a latency. **Hot
path:** this is one. **What moves:** vAmiga's adaptation and the Amiga's game stamp; no other console. **Quick states:** the Amiga's key moves, as between any two Amiga builds;
the table is derived, never saved.

## Commodore Amiga: stage 7's bus model in shadow, never in an export (1.7.3, stage 7 checkpoints 0-2)

**What changes.** A bus and DMA model of our own (`native/amiga_machine/amiga_bus.*`, MIT) can be computed beside vAmiga, line by
line, to compare its slots and its CPU waits with vAmiga's. Its hooks in vAmiga's adaptation (MPL-2.0 edits) sit under
`#ifdef RR_AMIGA_SHADOW`.
- The CMake option `RR_AMIGA_SHADOW` is OFF by default. An export is never built with it.
- Only the display self-test and private reference players turn it on.
- Without it, every hook is removed by the preprocessor, so an export compiles the same code as before.

**Hot path:** no, in an export: the hooks are not compiled.

**What moves:** the text of the hooks is part of vAmiga's adaptation, so its digest moves, and with it the Amiga's game stamp. No
other console moves.

**Quick states:** the Amiga's key moves, as between any two Amiga builds.

## Commodore Amiga: the idle disk controller's events caught up (1.7.3, stage 7 checkpoint 3a)

**What changes.** vAmiga's disk controller has an event about every 56 colour clocks, whether or not a floppy is in use. In a WHDLoad
install that is 1,269 events per frame on every game, between 4 and 21 % of all the machine's events.

**The guard.** The controller is idle when:
- no drive is selected;
- its DMA is off;
- DSKSYNC is not zero;
- its shift register already holds zero.

An idle controller's event only shifts zeros in, writes a zero byte into its FIFO and advances the rotation delay: it cannot raise an
interrupt or touch memory.

**How the events are held back.**
- The events after one are taken off the scheduler, up to 64 of them, and never past the host frame's end (the first instruction after
  line 0's HSYNC) as it is known when they are taken. A frame cut short later can still end with some held back; the events that are
  due run before any quick state is taken (see "quick states on a frame cut short" below).
- One event is scheduled at the time of the last of them. The others run in order when it comes, or when something could see the
  controller first: its registers (DSKLEN, DSKDAT, DSKBYTR, DSKSYNC), the CIA-B port that selects a drive and its motor.
- Their times are those vAmiga's own arithmetic gives: each event runs on the first colour clock at or after its trigger, and the next
  is scheduled from there.
- A barrier inside Agnus's events (a Copper or delayed write) runs the events strictly before its colour clock. A CPU access runs those
  of its own clock too, as vAmiga's order is.

This is done through vAmiga's adaptation (MPL-2.0 edits). Paula stays emulated, and nothing is specialised from a game.

**Proof.**
- The display self-test now compares each scenario with every disk event on vAmiga's scheduler (`--per-slot` turns the catch-up
  off). Its programs also read DSKBYTR, write DSKSYNC (zero now and then) and DSKLEN, and select drive 0 and its motor through CIA-B.
- 52 scenarios of 4 frames: 167,806 disk events held back in 2,725 batches (420 of them run at a barrier), every instruction's and
  every frame's record equal (Paula's and Agnus's snapshots included).
- One held-back event lost on purpose is seen in 52 of 52 scenarios.
- Two first versions were caught by these records:
  - one added the delay to the trigger instead of to the colour clock the event runs on;
  - one let a batch run past the host frame's end.
- Lotus 2's native game and the reference player built with this change give the same trace as the build before step 1 on every one
  of 3,600 frames of a racing route.
- The reference player gives the same trace as before on Rick Dangerous, Lemmings and Civilization (main routes, 3,600 frames each).
- On those four games the disk events left on the scheduler go from 1,269 to 21 per frame.

**What it brings:** timed together with the idle sprite slots below (one quiet-PC pass for all of checkpoint 3).

**Hot path:** this is one.

**What moves:** vAmiga's adaptation and the Amiga's game stamp; no other console.

**Quick states:** the Amiga's key moves, as between any two Amiga builds. The held-back events that are due run before a state is
taken.

## Commodore Amiga: the idle sprites' slots left out of their lines (1.7.3, stage 7 checkpoint 3b)

**What changes.** With sprite DMA on, Agnus has two slot events per sprite on every line (16 per line), even when no sprite is shown.
On Lotus 2 that is 4,563 events per frame with 16 fetches. On Civilization it is 4,321 events with 73 fetches, a third of all its
events.

**The rule.** A sprite's cycle does nothing on a line where its DMA is off and that is not its stop line. Both are known at the line's
start, since the sprite's DMA state is updated at $E1 of the line before.
- Such a sprite's two events are left out of the line's schedule.
- A write to its SPRxPOS or SPRxCTL puts it back for the rest of the line. vAmiga always applies such a write by a register-change
  event, before the slot events of its colour clock.
- Line 0, where the host frame ends, keeps every event, and so does AGA.

This is done through vAmiga's adaptation (MPL-2.0 edits). Agnus stays emulated, and nothing is specialised from a game.

**Proof.**
- The display self-test compares each scenario with every sprite slot on the schedule (`--per-slot`, or `--spr-off` alone).
- 52 scenarios of 4 frames: 892,295 sprite slot events left out, every instruction's and every frame's record equal. (An earlier
  count, 892,752, counted some twice; see "quick states on a frame cut short" below.)
- An armed sprite taken for idle on purpose is seen in 51 of 51 scenarios that show sprites.
- Lotus 2's native game and the reference player built with checkpoints 3a and 3b give the same trace as the build before step 1 on
  every one of 3,600 frames of a racing route.
- The reference player gives the same trace on Rick Dangerous, Lemmings and Civilization (main routes, 3,600 frames each).
- First-read conversions with the real command line, checkpoints 3a and 3b together (11 November 2026): Lotus 2, Rick Dangerous,
  Lemmings and Civilization (with the player's Kickstart 1.3).
  - Two routes of 3,600 frames each, every frame equal to the fresh reference; the compressed copy, the resload log and the quick-state
    restart are equal too.
  - 0 instructions interpreted, but Civilization's 19, which are all the Kickstart's, as in 1.7.2.

**What it brings** (checkpoint 3 as a whole, idle disk and idle sprite slots together): the machine's time per frame, measured
in one quiet-PC pass on 11 Nov 2026 (Windows, one core, native game, 3 rounds of 2,400 frames, median of the rounds):

| Game | Before Agnus/Denise step 1 | Steps 1-3 (1.7.3) | Plus checkpoint 3 | Against steps 1-3 |
|---|--:|--:|--:|--:|
| Lotus 2 | 2.529 ms | 1.748 ms | 1.516 ms | -13.3 % |
| Rick Dangerous | 2.157 ms | 1.368 ms | 1.355 ms | about -1 % (inside the spread) |

- Lotus 2 gains in each round (-12.2 %, -13.8 %, -13.3 %); the rounds spread by 1.5 % at most.
- Rick Dangerous has no sprite event to leave out, and its gain is smaller than the spread of its rounds (up to 4.9 %).
- This is machine time only. It says nothing about physical latency.

**Hot path:** this is one.

**What moves:** vAmiga's adaptation and the Amiga's game stamp; no other console.

**Quick states:** the Amiga's key moves; the line's set of idle sprites is derived, never saved (line 0 has none).

## Commodore Amiga: quick states on a frame cut short, and the idle sprites counted once (1.7.3, stage 7)

**What changes.**
- **Before a quick state is taken,** the idle disk controller's held-back events that are due now run, and the next one is scheduled.
  A batch is bounded by the frame's end as known when it starts. A frame cut short after that can end with events held back: VPOSW
  clearing LOF, or BEAMCON0 switching from PAL to NTSC. A snapshot keeps none of those events.
- **After a quick state is loaded,** stage 7's derived state of the timeline that was left goes: the disk controller's held-back
  events, the line's idle sprites, and the mark of Agnus's event loop.
- **The count of idle sprite slot events** counts each slot once, when its line ends. A mid-line DMACON change or a sprite woken
  inside its line used to count some slots twice. This changes the report's counter only, not the machine.

This is done through vAmiga's adaptation (MPL-2.0 edits) and the session. Agnus and Paula stay emulated.

**Proof.**
- The display self-test runs two new scenarios: every frame starts long and PAL and is cut short near its end, through VPOSW in one
  and BEAMCON0 in the other. A quick state is taken at the end of frame 1 and loaded back at the end of frame 3.
  - Every record is equal to the run with every event on vAmiga's scheduler. Held-back events were run at a frame's end 5 times in
    each scenario.
  - Leaving out the run before the snapshot, or the clearing after the load, is seen in both scenarios.
- The 52 random scenarios are unchanged: every record is equal, with no frame ending with events held back.
- Stage 7's model in shadow on wave 1 (Lotus 2, Rick Dangerous, Lemmings and Civilization, 3,600 frames each, the reference player):
  0 differences, and every figure is the same as before this change.
- Lotus 2 converted by the real command line: two routes of 3,600 frames, each frame equal to the fresh reference, with 0
  instructions interpreted. The compressed copy and the quick-state restart are equal too.

**Hot path:** no. The run before a state is taken and the clearing after a load happen only at a quick state; the count of a line's
idle sprite slots happens once per line.

**What moves:** vAmiga's adaptation, the session, and so the Amiga's game stamp. No other console moves.

**Quick states:** the Amiga's key moves. A state of an earlier build is refused, as between any two Amiga builds.

## Commodore Amiga: the Blitter served alone on its colour clock, tried and reverted (1.7.3, stage 7 checkpoint 4)

Not in any build. Checkpoint 4 served the Blitter's event alone when no other slot could be due on its colour clock. Its checks were
equal to vAmiga's. On a quiet PC (12 Nov 2026), it timed 2 to 3 % slower than checkpoint 3 on Lotus 2 and on Rick Dangerous, so it was
reverted. Nothing of it remains, and no stamp moved.

## Commodore Amiga: checkpoint 3's counters in the conversion report (1.7.3, stage 7)

**What changes.** Each route's `final_checks.agnus_denise` now also counts what checkpoint 3 did:
- `disk_idle_batches`, `disk_idle_batches_at_event`, `disk_idle_batches_at_barrier` and `disk_events_held_back`, for the idle disk
  controller;
- `sprite_slot_events_left_out`, for the idle sprites.

The `hardware_devices` details of `agnus_copper` and `paula` say what these are. Agnus and Paula stay emulated. A report of an earlier
build reads 0 for each of them.

**Hot path:** no. The counters existed already; the session only writes them at the end of a run.

**What moves:** the Amiga's game stamp (the session and the conversion module); no other console.

**Quick states:** the Amiga's key moves, as between any two Amiga builds.

## Exports of 1.7.1 in 1.7.2

1.7.2 is the release after 1.7.1 (published on 8 November 2026). This section is the index of its changes, one line per section below (or per machine page when a change has no
section here), with the stamps that section says move. Each section computed its stamps for its own change alone, on the tree of its branch; the totals are under the table and were
computed on `main` on 10 November 2026.

| Change | Game stamps that move | Host and build stamps | Quick states |
| --- | --- | --- | --- |
| [Sony PlayStation: two discs at once no longer fetch Beetle PSX together](#sony-playstation-two-discs-at-once-no-longer-fetch-beetle-psx-together-172) | the PlayStation only (`920cf82497a6` to `4a3b197254a5`) | none | no key moves: the PlayStation key hashes the Beetle adaptation and the session files, which do not change |
| [PC Engine / TurboGrafx-16: the larger capture format, shared paths, the walk repair, and the exit from the experimental status](#pc-engine--turbografx-16-the-larger-capture-format-shared-paths-the-walk-repair-and-the-exit-from-the-experimental-status-172) | the PC Engine only (each section gives its step) | none | the PC Engine key moves (the bridge and the engine revision change) |
| [PC Engine / TurboGrafx-16: a Backup RAM beside the game](#pc-engine--turbografx-16-a-backup-ram-beside-the-game-172) | the PC Engine only (each section gives its step) | none | the PC Engine key moves (the bridge and the engine revision change) |
| [Atari ST: Hatari's timer D patch on, and the native code compiled better](#atari-st-hataris-timer-d-patch-on-and-the-native-code-compiled-better-172) | the Atari ST only | none | the Atari ST key moves, as between any two Atari ST builds |
| [Atari ST: a write after a seek without verify finds its sector](#atari-st-a-write-after-a-seek-without-verify-finds-its-sector-172) | the Atari ST only | none | the Atari ST key moves, as between any two Atari ST builds |
| [Atari ST: Hatari's code specialised per opcode, and chained](#atari-st-hataris-code-specialised-per-opcode-and-chained-172) | the Atari ST only | its host stamp, through its notice (`licenses/hatari.md`) | the Atari ST key moves, as between any two Atari ST builds |
| [PC Engine / TurboGrafx-16: the play route answers the game](#pc-engine--turbografx-16-the-play-route-answers-the-game-172) | the PC Engine only (each section gives its step) | none | the PC Engine key moves (the bridge and the engine revision change) |
| [Commodore Amiga: the icon's DATA ToolType names the data folder](#commodore-amiga-the-icons-data-tooltype-names-the-data-folder-172) | the Amiga only (each section says so) | none | the Amiga key moves, as between any two Amiga builds |
| [Commodore Amiga: a file the game saves reaches the disk whole or not at all](#commodore-amiga-a-file-the-game-saves-reaches-the-disk-whole-or-not-at-all-172) | the Amiga only (each section says so) | none | the Amiga key moves, as between any two Amiga builds |
| [Commodore Amiga: a conversion that fails with remembered data is tried again without it](#commodore-amiga-a-conversion-that-fails-with-remembered-data-is-tried-again-without-it-172) | the Amiga only (each section says so) | none | the Amiga key moves, as between any two Amiga builds |
| [Commodore Amiga: the report and the F2 menu say less than they did](#commodore-amiga-the-report-and-the-f2-menu-say-less-than-they-did-172) | the Amiga only (each section says so) | none | the Amiga key moves, as between any two Amiga builds |
| [Commodore Amiga: the keyboard's power-up handshake is over when a slave starts](#commodore-amiga-the-keyboards-power-up-handshake-is-over-when-a-slave-starts-172) | the Amiga only (each section says so) | none | the Amiga key moves, as between any two Amiga builds |
| [Commodore Amiga: the player's own record](#commodore-amiga-the-players-own-record-172) | the Amiga only (each section says so) | none | the Amiga key moves, as between any two Amiga builds |
| [Commodore Amiga: the keyboard reaches a game that never enables its interrupt; F1-F4 on the long route](#commodore-amiga-the-keyboard-reaches-a-game-that-never-enables-its-interrupt-f1-f4-on-the-long-route-172) | the Amiga only (each section says so) | none | the Amiga key moves, as between any two Amiga builds |
| [Commodore Amiga: a long route at the extended level](#commodore-amiga-a-long-route-at-the-extended-level-172) | the Amiga only (each section says so) | none | the Amiga key moves, as between any two Amiga builds |
| [Commodore Amiga: the Blitter's copy blits, specialised routines by shape (recompilation stage 6)](#commodore-amiga-the-blitters-copy-blits-specialised-routines-by-shape-172-recompilation-stage-6) | the Amiga only (each section says so) | none | the Amiga key moves, as between any two Amiga builds |
| [Commodore Amiga: a sweep beyond the routes (recompilation stage 4)](#commodore-amiga-a-sweep-beyond-the-routes-172-recompilation-stage-4) | the Amiga only (each section says so) | none | the Amiga key moves, as between any two Amiga builds |
| [Commodore Amiga: 68000 forms translated to C (recompilation stage 3)](#commodore-amiga-68000-forms-translated-to-c-172-recompilation-stage-3) | the Amiga only (each section says so) | none | the Amiga key moves, as between any two Amiga builds |
| [Commodore Amiga: the instructions' lengths come from Moira, and no recompiler is needed](#commodore-amiga-the-instructions-lengths-come-from-moira-and-no-recompiler-is-needed-172) | the Amiga only (each section says so) | none | the Amiga key moves, as between any two Amiga builds |
| [Commodore Amiga: Moira's code specialised per opcode, and chained (recompilation stage 2)](#commodore-amiga-moiras-code-specialised-per-opcode-and-chained-172-recompilation-stage-2) | the Amiga only (each section says so) | none | the Amiga key moves, as between any two Amiga builds |
| [Commodore Amiga: a debugging recorder off, the resload traps without breakpoints (recompilation stage 1)](#commodore-amiga-a-debugging-recorder-off-the-resload-traps-without-breakpoints-172-recompilation-stage-1) | the Amiga only (each section says so) | none | the Amiga key moves, as between any two Amiga builds |
| [Commodore Amiga: the guard compares what the CPU has latched](#commodore-amiga-the-guard-compares-what-the-cpu-has-latched-172) | the Amiga only (each section says so) | none | the Amiga key moves, as between any two Amiga builds |
| [Commodore Amiga: Kickstart words a slave patched run native too](#commodore-amiga-kickstart-words-a-slave-patched-run-native-too-172) | the Amiga only (each section says so) | none | the Amiga key moves, as between any two Amiga builds |
| [Commodore Amiga: an archive with an intro or editor slave beside the game](#commodore-amiga-an-archive-with-an-intro-or-editor-slave-beside-the-game-172) | the Amiga only (each section says so) | none | the Amiga key moves, as between any two Amiga builds |
| Computers: full guest typing gives F1 to the guest, and the help page names Ctrl+Alt+K ([CONTROLS.md](CONTROLS.md); no section of this page) | none | the host stamps of the X68000, the Amiga and the Atari ST (the shared computer adapter and their own) | no key moves |
| Atari ST: states that continue with their sound, disk writes kept beside the state, long routes, the panel ([ATARI_ST.md](ATARI_ST.md); no section of this page) | the Atari ST only | none | the Atari ST key moves |
| Tests: the window and reconvert tests no longer write the player's real `Export/datas` (no section of this page) | none | none | none |

Taken together (`compilation_inputs.role_stamps` of the seventeen profiles, the tree of `v1.7.1` against `main`, Windows, Python 3.14): **the game stamps of the PC Engine,
the Amiga, the Atari ST and the PlayStation move**, **the host stamps of the X68000, the Amiga and the Atari ST move**, and **no build stamp moves**. Every other machine is
unchanged.

| Machine | Game stamp (v1.7.1, now) | Host stamp (v1.7.1, now) | Build stamp |
| --- | --- | --- | --- |
| Master System | `63c93fcb0264` (same) | `62a7e9f65d83` (same) | `fe2d99b3cd5e` (same) |
| Game Gear | `70eafce5937a` (same) | `fa5e7fa22b05` (same) | `f5671c38cf26` (same) |
| Game Boy | `b218f94d2c75` (same) | `2a0942586a4a` (same) | `819a054ad881` (same) |
| NES | `af5a3a096738` (same) | `39c36bfa861a` (same) | `8e0941f93b43` (same) |
| Mega Drive | `ed3a49ab59a8` (same) | `8f4324fbcb85` (same) | `9615ff2e96c8` (same) |
| Super Nintendo | `064bd8544d76` (same) | `d35383911455` (same) | `3f0a58ad3c7c` (same) |
| Neo Geo | `b45ca489a2c9` (same) | `f1fde4b7a652` (same) | `110349f043bd` (same) |
| X68000 | `107b51de2145` (same) | `55ac9db11502`, `be9dae27aacf` | `5903c0449429` (same) |
| CPS-1 | `28dd85714948` (same) | `0220746ac9ad` (same) | `2782cd370f91` (same) |
| CPS-2 | `cb7b5d304275` (same) | `7889559074ad` (same) | `81a51ad49349` (same) |
| PC Engine / TurboGrafx-16 | `ebcbc2a403cd`, `aa7913b68d39` | `3da7363bd893` (same) | `66d912662e5c` (same) |
| Game Boy Advance | `1658c523234f` (same) | `7b18d021f143` (same) | `6b70933a9b0a` (same) |
| Amiga | `ba01a0a7e76e`, `6854eee76d0e` | `b264a452712e`, `8ca835ce1027` | `92ca8a0c142c` (same) |
| Atari ST | `fa09328f914f`, `e6f3506a6be7` | `f8a69516f53e`, `3b7c6f50488a` | `54b75964897d` (same) |
| Nintendo 64 | `ec87144eb331` (same) | `3c4f6ccca458` (same) | `4f6fedf926c7` (same) |
| Adventure (ScummVM) | `42dfc172e91c` (same) | `82088d749a09` (same) | `05417bbcea96` (same) |
| Sony PlayStation | `920cf82497a6`, `4a3b197254a5` | `5dbdb5df79ca` (same) | `b6c9cf73b176` (same) |

(First twelve hexadecimal digits of each stamp.) `LEGACY_GAME_STAMPS` stays empty. **So every export of 1.7.1 of the PC Engine, the Amiga, the Atari ST and the PlayStation is
converted again, from its qualified paths, once, when the player updates**, and the window offers it; it is not a quick host-only upgrade. **An X68000 export is upgraded**: its
host stamp alone moves, so it is rebuilt from its paths with no rediscovery. The exports of the other machines are not touched.

**Quick states.** The **PC Engine key moves** (it hashes the engine revision and the bridge files `pce_machine.cpp`, `pce_machine.h` and `pce_main.c`, which change), and the
**Amiga and Atari ST keys move** (each follows its machine's build, which changes): a quick state of 1.7.1 of those three machines is refused cleanly (no compatibility key is
carried, [GAME_STATES.md](GAME_STATES.md)); nothing is lost but that state. The **PlayStation key does not move**: its game stamp moves for the setup gate, but the key hashes the
Beetle adaptation and the session files, which do not change, so a PlayStation state of 1.7.1 loads in the rebuilt export. The X68000 key hashes none of the files that changed (the
change is in the host adapter). The other machines are not rebuilt. **Cartridge saves** are kept on every machine, and the PC Engine's new Backup RAM file starts formatted.

## Sony PlayStation: two discs at once no longer fetch Beetle PSX together (1.7.2)

The pinned Beetle PSX checkout in `.deps` is shared by every disc, but only the game's own work folder was locked. Two discs converted at once on a fresh `.deps` could both clone it. Fetching it now goes through the shared setup gate, as the other machines' setups do. Nothing changes in the machine or in a game.

**What moves:** only the PlayStation's game stamp: game `920cf82497a6` to `4a3b197254a5` (`psx_beetle.py`). Its host and build stamps and every other console's stamps do not move. A PlayStation export of an earlier version is rebuilt when it is upgraded, to the same machine.

## PC Engine / TurboGrafx-16: the larger capture format, shared paths, the walk repair, and the exit from the experimental status (1.7.2)

**Engine pin** `81b5c231` to `6bb848e8` (pcenginerecomp, ABI 29). A card that needs more than 65,536 instruction identities gets the engine's larger capture format (up to 1,048,576, past it left out and counted): Street Fighter II' Champion Edition now runs 0 interpreted instructions on its three routes, where it ran 19.3 %, 33.5 % and 74.7 % interpreted; its game is 25.4 MB packed and its conversion takes about 34 minutes on its own. **Shared paths**, numbers only, in the experimental tier of the base: a record is made from a passed conversion's captures, and a conversion that receives paths gives them to the engine as declared roots, never as captures ([PC_ENGINE.md](PC_ENGINE.md#7-shared-paths)). **The walk repair:** where the play walk left a game paused, one more Run press is kept if the game answers (Gradius at frame 7,811). **The fetch of the engine** goes through the shared setup gate, so two cards at once on a fresh `.deps` no longer clone it together. **Status:** supported, on the owner's decision of 10 November 2026 after playing the fifteen exports of this tree ([QUALIFICATION.md](QUALIFICATION.md#owner-acceptance)). **The limit he saw:** native code covers what the conversion's own routes ran (about one minute of play and five minutes of pseudo-random walk), not the whole game; code past that runs through the interpreter, counted and shown in the game. The routes are thinnest on Boxyboy (after Start it waits on a screen the walk does not confirm), Military Madness, Space Harrier and Santatlantean (their long walks stall on a prompt or a loop); the owner saw it on Boxyboy after Start. A PC Engine game keeps no player's record yet, so the code a player reaches is not made native at the next conversion. The conversion report's `runtime_feedback.recording_default` reads `true` for the PC Engine, but no PC Engine game records anything: its F12 line says the record is off and stays off. 1.7.3 corrects the field together with the record itself. Evidence: the 15-card panel on Windows and on a Debian 13 PC, 45 of 45 routes equal ([PC_ENGINE.md](PC_ENGINE.md#the-panel-of-the-release-tree-9-november-2026)).

**Hot path:** the new pin calls a bus observer on every read and write of the CPU (no observer is set in a game). **Speed**, measured on a quiet PC, 10 November 2026, one core, the headless attract route with no input, the best of three runs of 2,400 frames, host time only: against games built with the 1.7.1 pin `81b5c231` (no published 1.7.1 PC Engine export exists to measure), the frame cost is 1.09x on Blazing Lazers (4.44 to 4.84 ms a frame) and 1.04x on Street Fighter II' CE (4.49 to 4.69 ms; its old game ran 19.3 % interpreted on that route), and Street Fighter II' CE starts in 1.40 s instead of 0.21 s (its game is 25.4 MB). The bus observer of the new pin is ruled out as the cause: the same module of Blazing Lazers built with the observer compiled out costs the same (4.81 against 4.76 ms a frame, within noise). Where the rest comes from (the module the new engine emits, the rest of its runtime, the Backup RAM) is not measured apart. **What moves:** only the PC Engine's game stamp: game `4d4c66fc090c` to `aa7913b68d39` (`native/pce_machine.cpp`, `native/pce_machine.h`, `native/pce_main.c`, `pce_conversion.py`, `pce_build.py`, `pce_knowledge.py`, `systems/pc_engine.py`); its host and build stamps and every other console's stamps do not move. **Exports:** a PC Engine export of an earlier version is rebuilt when it is upgraded; its Backup RAM file is kept. **Quick states:** refused cleanly, as after any change of the bridge.

## PC Engine / TurboGrafx-16: a Backup RAM beside the game (1.7.2)

A game can now keep the 2 KiB of the console's backup unit between runs. Bank `$F7` is mapped as plain RAM by our bridge, on the same engine pin and with no change to the engine. With no file it starts with the file system's header, a written choice ([PC_ENGINE.md](PC_ENGINE.md#6-saves)). The file is `datas/saves/<game>-<card>.rrsram`, beside the other machines' saves; a damaged or wrong-size file is set aside as `.unusable-N` and never blocks a game. Boxyboy, which showed "FILE NOT CONNECTED. COPY THE PASSWORD", now starts and saves.

**What moves:** only the PC Engine's game stamp: game `750e062dca69` to `4d4c66fc090c` (`native/pce_backup.c`, `native/pce_machine.cpp`, `native/pce_main.c`, `pce_conversion.py`, `pce_build.py`, `systems/pc_engine.py`). Its host and build stamps and every other console's stamps do not move. A PC Engine export of an earlier version is rebuilt when it is upgraded. It has no save to lose: it starts formatted. Its quick states are refused cleanly, as after any change of the bridge. Tool, no stamp: `tools/pce_mame_compare.py` gives MAME the same formatted memory.

## Atari ST: Hatari's timer D patch on, and the native code compiled better (1.7.2)

TOS starts the MFP's timer D at a very high rate with its interrupt off, one event every couple of instructions, which is why the chains stayed short. This machine now runs Hatari's own option (`hatari_timerd`): when the code starting the timer is in the TOS's addresses, Hatari starts it far slower, and answers TOS the old value. **This changes the machine, on purpose, on the owner's decision of 9 November 2026: a game that uses this timer as TOS left it sees another rhythm, or another value in its data register.** No fidelity is claimed for it; a game that programs the timer itself is not touched; Hatari's list names Exterminator, The Seven Gates of Jambala and Super Sprint as needing the option off, and none of the ten panel games relies on it ([ATARI_ST.md](ATARI_ST.md#5-known-limits)).
The reference, the native game and its packed copy run the same machine: the frame comparison cannot see the patch, so each run's report says Hatari has it set, a conversion refuses a run without it, and the conversion report states it (`machine.timer_d`). `tools/atarist_hardware_check.py` measures it from RAM and from the ROM.
Compiled better: the test between two instructions inline in each instruction, the fault exits out of the hot path, link-time optimisation of the session and the native code with the player (not of Hatari's core); each changes no statement. The executable grows by about 12 % (Bomb Jack).
Proof: vectors, and all 45,814 forms against the table's handlers on random states, 0 differ, with LTO. The panel at the thorough level: all 40 routes equal to the fresh reference, the packed copy and the state continuation too. The three games tried with the player's TOS 1.04 too. On a Debian 13 PC with GCC and LTO, the panel at the Standard level: 20 of 20 traces byte equal to Windows.
An estimate on a loaded PC, headless, no hashing, host cycles of 3,000 frames. The option alone, off over on: on EmuTOS 1.30 to 1.70, on TOS 1.04 1.56 to 1.80, on three games. Against the export before this change, on the panel: 1.18 to 1.67. The native code over the table: 1.21 to 1.47. Not a timing.
**Hot path:** the chain's test and next are now inlined at each instruction; the rest is unchanged. **What moves:** the Atari ST's game stamp and the Hatari options of its session; no other machine. **Exports:** games from before keep their machine until they are converted again. **Quick states:** the Atari ST's key moves, as between any two Atari ST builds.

## Atari ST: a write after a seek without verify finds its sector (1.7.2)

Hatari's read commands load the track under the head; its write command did not, as an MFM write only ever ended in "record not found" before Retro-Recomp kept what a game writes. A TOS that seeks without verify, as EmuTOS does, then looked for the sector on the track last loaded:
The Lurking Horror's save answered "Failed." on EmuTOS. It now saves on EmuTOS and TOS 1.04, and restores in a new process, on Windows and a Debian 13 PC (`tools/atarist_saves_game.py`). **Exports:** a game that saved on EmuTOS keeps what it has; one
whose save failed had written nothing. **What moves:** the Hatari adaptation, so the Atari ST's game stamp; no other machine.

## Atari ST: Hatari's code specialised per opcode, and chained (1.7.2)

A native step was a call to Hatari's own handler behind a page-table look-up and a comparison of every word in memory, which made it slower than the interpreter (14 to 29 % on a loaded PC). Now a *form* is
Hatari's handler, its generated text compiled again with the opcode as a literal, on one shared copy of Hatari's bus path without its pointers, and each observed instruction (one per address
and opcode) goes straight on to the instruction it knows comes next. This is Hatari's code specialised, not a translation: same bus accesses, same cycles. A form reads its extension words on the bus, so
the guard is the opcode the CPU has latched and a word rewritten in memory needs no tracking; an instruction with the same opcode and other extension words now runs native where it was interpreted. The 68000 loop
sees what it saw: a chain stops, untouched, whenever something is due after an instruction (a clock event, an MFP update, a special flag, an interrupt level above the mask). Chains are short: the MFP's timer D, as TOS
programs it, makes an event every few instructions, about 2 instructions per entry on Bomb Jack (`chain_entries` in the report).
Vectors: every native form equals the interpreter on the vectors that have one, and with `tools/atarist_vector_selftest.py --all-forms` each of the 45,814 forms equals the table's handler on eight random states (366,512 runs, 834,101 bus accesses compared in order and clock, an interrupt line changing during the instruction, through the bank's functions and on direct RAM). The vectors found ADDX.L D6,D6 wrong with a literal opcode: the forms are compiled
with `-fwrapv`, and the same check without it finds that family. The whole panel at the thorough level: every frame of all 40 routes equal to the fresh reference, the packed copy and the state continuation too.
An estimate on a loaded PC, headless, no hashing, host cycles of 3,000 frames, table over native: Bomb Jack 1.05, Turrican II 1.09 to 1.17, Indiana Jones 0.98 to 1.00, Kick Off 2 1.04, Lethal Xcess 1.20; not a timing.
Licence: no text of `m68k_decoder.h` is in a game any more, so the notice of segagenesisrecomp leaves the exports; the decoder still runs during the conversion.
**Hot path:** the look-up and the word comparison are gone from the instructions inside a chain; two calls of one shared test per instruction instead, one count per entry. Handlers keep their pointers on the interpreted path. **What moves:** the
Atari ST's game stamp, and its host stamp through its notice (`licenses/hatari.md`); no other machine. **Quick states:** the Atari ST's key moves, as between any two Atari ST builds. The window title and the note "not fully recompiled" are unchanged.

## PC Engine / TurboGrafx-16: the play route answers the game (1.7.2)

The first panel pressed Run at fixed frames, and on 7 of 18 cards the play route then stayed on a menu, a story, a sound test or a password screen while every check passed. The conversion now tries 1, 2, 3, 4 and 6 Run presses, walks with the directions only for 900 frames (so a password screen is not typed into), keeps the variant whose walk showed the most pictures that the same frames without input never show, and presses Run twice now and then to leave stories and prompts (`pce_conversion.start_candidates`, `reach`, `choose_start`). Quick states are checked with 13 damaged states (all refused and left as they were) and a missing one (refused, creates nothing). The line printed when a game is ready says "no interpreter on the routes played" instead of "native code only", and the profile's scope note says a converted game is built for two players.

**What moves:** only the PC Engine's game stamp (`pce_conversion.py` and `systems/pc_engine.py` are inputs of it): game `750e062dca69` (it was `ebcbc2a403cd` on main); its host and build stamps and every other console's stamps do not. A PC Engine export of an earlier version is rebuilt when it is upgraded: the routes it was checked on change, the game does not. Tools only, no stamp: `tools/pce_mame_compare.py` (the delivered game against MAME 0.289, a private oracle), `tools/pce_route_captures.py` (pictures along each route) and the native vector tier widened on request (`--per-opcode 250`). Evidence: [PC_ENGINE.md](PC_ENGINE.md#the-extended-panel-9-november-2026).

## Commodore Amiga: the icon's DATA ToolType names the data folder (1.7.2)

An install whose slave leaves `ws_CurrentDir` empty and whose icon says `DATA=data` (Drakkhen, NTSC, French, German and the plain one) was read with its
data folder at the archive's top: the `Disk.N` images in `data/` were not found and the game stopped at boot with "DiskLoad failed with DOS error 205
(Disk.1)". The icon (`<slave>.info`, read the way `CUSTOM1` to `5` are) is now asked for `DATA`; when it names a folder of the archive that holds files, that is
the data folder, as WHDLoad lets it replace the slave's `ws_CurrentDir` (a ToolType in parentheses is off; a name that matches nothing leaves the earlier rule).
Run headless with the interpreted machine for 1,500 frames, the four Drakkhen installs reach the end with picture and sound (non-black frames 1,309 to
1,340 of 1,500), where the tree before stops at frame 135 (NTSC). Any other install whose icon carries a `DATA` ToolType (about 14 of the maintainer's library)
may now find its files where it did not; none of them was run again. **What moves:** the Amiga's game stamp for those installs only (the install's files
change); the code is `retrorecomp/amiga_whdload.py`. No other console.

## Commodore Amiga: a file the game saves reaches the disk whole or not at all (1.7.2)

What an install saves (`resload_SaveFile`) goes to `datas/games/amiga-<identity>/saves`. The write went through a temporary file but did not look at the
flush and the close, so a disk that took only part of the bytes could still replace a good save with a short one and tell the game it worked; the game's own view
of the file changed before the disk was asked. Now the temporary file replaces the old one only when every byte is flushed and closed, the game is told the save
failed (disk full) when anything refused, its view of the file and the file on disk stay as they were, and no temporary file stays behind. A name that would
leave the save folder (absolute, a volume or drive colon, a backslash, `.` or `..`) is refused with "write-protected" instead of being written elsewhere;
deleting follows the same rule. On 5th Gear (8 November 2026), with a folder where the file goes so that the replacing rename fails, the save was refused, the run stopped at it
with DOS error 221 as WHDLoad does for a slave that sets NoError, the folder stayed and no temporary file was left. The helper is `native/amiga_machine/amiga_savefile.h` and is checked by an authored program (`tests/test_amiga_resload.py`:
names, a first write, a replacement, a folder in the file's place, a file in the folder's place, a stale temporary). A disk that is really full cannot be made in
that test; a refused rename is. **What moves:** the Amiga's game stamp (`amiga_session.cpp`); no other console. **Quick states:** the Amiga's key moves, as between any two Amiga builds.

## Commodore Amiga: a conversion that fails with remembered data is tried again without it (1.7.2)

The library remembers, per install, the instructions earlier conversions saw (and the Kickstart addresses). A remembered file that cannot be read was ignored, but one
that is valid and too large (past the bound of an observation) stopped the conversion for good, since the file was only replaced by a conversion that finished. It
is now ignored like a damaged one, and a conversion that fails after it merged anything from that memory is tried once more without it; on success the
run's own observations replace the remembered ones. Checked on Rick Dangerous (quick level) with a valid file of 1,048,577 lines (13.6 MB): ignored, ready in 6 min 34 s, the file replaced
by the run's own 4,896 lines; the retry itself is tested with a fake conversion, not on a real failure. The report says what the memory added, what was ignored and, after a retry, why (`remembered_data`). The
Amiga does not share paths (G16 `-`). **What moves:** the converter only (`retrorecomp/amiga_conversion.py`), plus the report's wording below.

## Commodore Amiga: the report and the F2 menu say less than they did (1.7.2)

The report states what it measures: `native_coverage` names the Kickstart instructions of the player's image when the install uses one, `qualification_scope.media`
the installs that ask for a Kickstart 1.x, `machine.model` that the memory is laid out as WHDLoad lays it out, `video_model.fps_is: nominal` (the frame rate the
player paces by, not a measurement) and `native_validation.independent_cpu_oracle: false` (the native steps and the reference both run Moira). The F2 menu offers
one player's page (one joystick is wired; the mouse is port 1), no second page that led nowhere. The Options note and the Kickstart check ("recognised", since the
image is known by its size and CRC) are reworded in the eight languages. **What moves:** the Amiga's game stamp (`rrhk_amiga.inc`); no other console.

## Commodore Amiga: the keyboard's power-up handshake is over when a slave starts (1.7.2)

Twylyte and California Games stopped at boot with a guru, which 1.7.1 blamed on a 68020; that was wrong: the real WHDLoad boots them on a 68000
(a private run of Copperline). The cause: vAmiga's keyboard waits a second after a reset and then sends `$FD` and `$FE`. On a real machine that ended
long before WHDLoad started; here the slave starts a frame after the power-on, so the codes arrived about a second into the game, during the
Kickstart's boot, and reached a slave's keyboard handler that a player's key would reach much later (that handler then read a word at an odd
address, an address error on a 68000, as a real key press may also cause on such a slave; not checked). The machine now declares the handshake over
at its power-on (`Keyboard::rrHandshakeOver`, a build-time change of the MPL-2.0 file). Both installs boot with picture and sound; Time Runners 19
still stays black, for another reason not found yet. A game's run shifts by a few instructions around that second (Rick Dangerous: 24 more on each
route, the picture, sound and memory of each frame again equal to the fresh reference). **What moves:** the Amiga's game stamp; no other console.
**Quick states:** the Amiga's key moves, as between any two Amiga builds.

## Commodore Amiga: the player's own record (1.7.2)

An exported Amiga game now records windows of 16 bytes at the 68000 instructions it interprets in RAM (feedback kind 22, the shared recorder, F12, written at a normal exit), and a reconversion beside that game makes them native, behind the same guard. What ran counts as `native_learned`, what a walk found after it as `native_walked`, apart from route-proved and swept code. These are private hints of that conversion: never in the library, never shared (G16 stays `-`). No shared file changes, so the 4,096-record limit holds. **What moves:** the Amiga's game stamp; no other console. **Hot path:** the instruction hook gains one test while a game runs, and each interpreted RAM instruction compares its window; a native instruction learned or walked adds one counter, as a swept one does. An export made before this records nothing until it is reconverted.

## Commodore Amiga: the keyboard reaches a game that never enables its interrupt; F1-F4 on the long route (1.7.2)

A key changing now sets `CIAICRF_SP` in CIA-A's interrupt mask, as WHDLoad's autodoc describes, unless the slave has `WHDLF_NoKbd` (`native/amiga_machine/amiga_session.cpp`). Found on Pinball Dreams, whose level 2 handler waits for a mask it never sets: no key reached it, with the native code or on the fresh vAmiga reference. The long route's menu keys gain F1 to F4. **What moves:** the Amiga's game stamp; no other console. **Hot path:** none, it runs when a key changes. An export keeps its old behaviour until it is reconverted.

## Commodore Amiga: a long route at the extended level (1.7.2)

The extended level now adds one route of 18,000 frames, seeded from the install (`computer_routes.long_events`, the same body as the Atari ST's, which a test shows; the ST keeps its own so that its stamps do not move), and the thorough level two. It is for route depth, not for native code: on Apidya and Lemmings 18,000 frames brought under 2 % more instructions. A route does not finish a game. `tools/amiga_route_captures.py` takes pictures along each route of a delivered game (`--capture-every`, headless only). **What moves:** the Amiga's game stamp; no other console. A conversion at the standard level runs the same routes as before.

## Commodore Amiga: the Blitter's copy blits, specialised routines by shape (1.7.2, recompilation stage 6)

A game's copy blits of the shapes its reference runs saw now go through a routine compiled for that shape: vAmiga's own microprogram (its accuracy level 2), whose text `amiga_vamiga.blitter_shape_header` takes at build time
with BLTCON0 and BLTCON1 without their shift fields as template parameters, so the compiler folds the channels, the direction, the fill and the minterm's 256-way switch. One step per bus slot, in the slots the reference uses,
everything else read live. Specialised routines, not a translated program. A routine checks its shape at every slot; a game that changes BLTCON during a blit goes on in vAmiga's table (`left_midway`). Line blits, shapes beyond
the 64 that move the most words, and shapes the routes never saw stay in vAmiga's microprogram. Native and interpreted counters by shape: `final_checks[].blitter`; the report's `hardware_devices` names the Blitter apart from Agnus and
the Copper, Denise and Paula, which stay emulated. The Copper is not compiled ([AMIGA.md](AMIGA.md), section 2).
Proof: `tools/amiga_blitter_selftest.py` runs 1,023 shapes (every channel set with every fill and direction, every minterm) on 8,184 random blits, a quarter with BLTCON changed on the way, through vAmiga's table and through the routine, with the same random bus from slot to slot:
the Blitter's whole snapshot and the slot's bus record after each of 970,162 slots, then Agnus, Paula and chip RAM, 0 differ; a routine that writes a wrong word is seen 16 times out of 16. Rick Dangerous, Apidya, Lemmings and Civilization: every frame equals the fresh reference on both routes,
with the same CPU counts and sound hashes as stage 4 and every copy word in a routine (shapes 1, 4, 3, 12). **What it brings:** little. On a loaded PC a slot took about 2 ns less out of 11 to 20 ns, with runs from 0.83 to 1.57 times, no timing; the Blitter is 0.1 to 3.6 % of a frame, so under 1 % of a frame at best.
**Hot path:** one pointer test per copy-blit slot, and a table lookup per blit. **Size:** 4 to 14 KiB more per compressed game on the four. **What moves:** vAmiga's adaptation and the Amiga's game stamp; no other console. **Quick states:** the Amiga's key moves, as between any two Amiga builds; a state saved during a blit goes on correctly in the table.

## Commodore Amiga: a sweep beyond the routes (1.7.2, recompilation stage 4)

What a player reaches beyond the scripted routes ran on the interpreter. The conversion now reads the memory each route's fresh reference leaves (in its private work folder, removed once read) and
goes outward from the observed code: what branches lead to, what follows them, then the rest of the 4 KiB pages where code ran, since a subroutine called through a pointer is reached by nothing
else; a Kickstart image is walked but not filled. A guess that is not code is only a routine that never runs. The swept instructions carry the same guard, the latched opcode. They count apart when
they run (`final_checks.native_swept`; `native_forms.swept_instructions` is what is known), so a report never presents swept code that did not run as proved on a route; the routes it was read from
ran the observed code, so on them the count stays at 0. Nothing swept enters the library.
Proof: Rick Dangerous, Apidya, Lemmings and Civilization as usual, equal to the reference with the same counts. And a build that learned only the main route, playing the explore route it never saw: every frame
and the resload log equal to the reference on the three games tried; 320,225 instructions swept and run with none interpreted on Rick, 1,227,349 and none on Lemmings. On Apidya it reaches 6 of 9,565: that code is no longer
in memory when the main route ends: later loads overwrite it (an image at frame 130 holds it), so it stays on the counted interpreter. Civilization has no such test: its routes run the same code.
The routes are scripts and these are about a minute of each game; this does not say what share of a whole game a sweep reaches. **Size:** 12,730 to 95,933 more instructions compiled; Rick's exe goes from 2.88 MB to 3.28 MB, Civilization's is 8.33 MB
against the first sweep. **Hot path:** one more count per swept instruction that runs. **What moves:** the Amiga's game stamp; no other console. **Quick states:** the Amiga's key moves, as between any two Amiga builds.

## Commodore Amiga: 68000 forms translated to C (1.7.2, recompilation stage 3)

The forms of 50 Moira handlers are now written out as C by a translator (`amiga_translate`): the effective address, the operation and the flags for that opcode, every register a
literal index, calling the machine's bus functions (`read`, `write`, `prefetch`, `readExt`, `sync`) in Moira's order. Extension words are still read on the bus, so the guard stays the latched
opcode. Other forms stay Moira's code specialised. Each route's report counts the two apart (`final_checks.native_translated`, `native_moira_specialised`), and `native_forms` gives the
static counts. Translated share of the instructions executed on two routes of 3,600 frames: Rick Dangerous 99.8 %, Apidya 99.9 %, Lemmings 99.9 %, Civilization 99.0 %. Translated is a statement about the 68000's code:
Agnus, Denise, Paula and the CIAs stay emulated, and this says nothing of hardware fidelity.
Proof: `tools/amiga_vector_selftest.py` now runs every one of the 40,586 translated opcodes against Moira's handler on 32 random states over a random memory, with the interrupt lines
changing at a random bus access: 1,298,752 runs, 0 differ on registers, SR, PC, queue, clock, each bus access, internal buffers, function code and flags. Deliberate errors were reported
(a flag, a clock, a moved poll of the lines, a register, the order of a long write, an address error frame); one was not (a `readBuffer` write that a later prefetch overwrites). This shows equality with Moira, not
with the hardware; the corpus of 6,762 vectors still runs through the steps, all equal. The same four games: every frame equal to the fresh reference, packed copy and state continuation too, with the same counts.
An estimate on a loaded PC, headless (hashing included), interpreted time over native time on 1,200 frames: Rick 1.00, Apidya 1.01, Lemmings 1.00, Civilization 1.00; the 68000 is a small part of a frame here, not a timing.
**Hot path:** one more count per translated instruction; the form's text differs, its bus accesses do not. **What moves:** the Amiga's game stamp; no other console. **Quick states:** the Amiga's key moves, as between any two Amiga builds.

## Commodore Amiga: the instructions' lengths come from Moira, and no recompiler is needed (1.7.2)

The chain of the native code needs the length of an observed instruction and the address it names. Both came from the decoder of `m68k-recomp-core`, built during each
conversion. The length now comes from Moira's disassembler, in the table of its handlers, and the address from the handler and the instruction's words; a wrong guess could only
miss a chain, which still compares the pc at run time. An Amiga conversion no longer reads anything from segagenesisrecomp or m68k-recomp-core, so no PolyForm Noncommercial
text is involved in it, and a machine with extension words the decoder cannot read (a later Amiga) stays open. An opcode the decoder refused now runs native, Moira's code like
the rest. **Hot path:** none. **What moves:** the Amiga's game stamp; no other console.

## Commodore Amiga: Moira's code specialised per opcode, and chained (1.7.2, recompilation stage 2)

A native step was a call to Moira's own handler behind a look-up and a comparison of every word through the memory map, which made it slower than the interpreter. Now a *form*
is Moira's handler compiled for one opcode, with the opcode as a literal and Moira's code inlined, and each observed instruction (one per address and opcode) goes straight on
to the instruction it knows comes next. This is Moira's code specialised, not a translation: same bus accesses, same cycles, same code. A form reads its extension words on
the bus as the interpreter does, so it is right for its opcode at any address: the guard is now the opcode the CPU has latched, and a word rewritten in memory, by anything,
needs no tracking. An instruction with the same opcode and other extension words now runs native where it was interpreted. The run loops see what they saw: the chain stops
whenever a flag is pending for Moira or the Amiga, and returns there on anything it does not know.
Vectors: 6,762 of 6,762 equal to the interpreter on registers, SR, PC, prefetch, clock and each bus access. Rick Dangerous, Apidya, Lemmings and Civilization, two routes of
3,600 frames each: every frame equal to the fresh reference on picture, sound, RAM and registers, the packed copy and the state continuation too, with the same instruction counts.
An estimate on a loaded PC, headless (hashing included), interpreted time over native time on 1,200 frames: Rick 1.00, Apidya 1.07, Lemmings 1.00, Civilization 1.01; not a timing.
Licence: the index no longer contains `m68k_decoder.h`, so no PolyForm text enters an Amiga game, and its notice leaves the exports; the decoder still runs during the conversion.
**Hot path:** the look-up and the word comparison are gone from most instructions; one count, two flag reads and a pc and opcode comparison per instruction added. **What
moves:** the Amiga's game stamp; no other console. **Quick states:** the Amiga's key moves, as between any two Amiga builds.

## Commodore Amiga: a debugging recorder off, the resload traps without breakpoints (1.7.2, recompilation stage 1)

Two costs the machine paid for nothing a game can see. vAmiga's logic analyzer, a recorder for its debugger, is connected by default and took 12 to 14 % of a
frame's samples; it is off (`Opt::LA_CONNECT`). The resload traps were debugger breakpoints, which keep every 68000 instruction on Moira's slow path and walk a list (0.6 to
5.6 % of the samples); they are one comparison after each instruction (`rr_moira_trap`, a build-time change of Moira's MIT file). Shares of a sampling profile on a loaded PC,
not a timing. **Hot path:** one comparison per instruction added, the slow path and the breakpoint walk removed. Nothing here is recompilation: the counters do not change. **What
moves:** the Amiga's game stamp; no other console. **Quick states:** the Amiga's key moves, as between any two Amiga builds.

## Commodore Amiga: the guard compares what the CPU has latched (1.7.2)

A native step was chosen by comparing the instruction's words in memory, while the CPU was about to run the opcode it had already prefetched. A word rewritten just
after its prefetch could therefore run the step of the new word with the old opcode. It never happened on a game (8 games, 16 routes, about 480 million instructions:
memory and the latched words never differed), and an authored program shows it (358 of 367 cases differ from the interpreter); the frame comparison covers the routes
only, so a player's play beyond them had no proof. The guard now compares the latched opcode and next word, and memory beyond them; on the same authored program no step
runs and nothing differs. **Hot path:** three stores per instruction, and two reads through the memory map less. **What moves:** the Amiga's game stamp; no other console.

## Commodore Amiga: Kickstart words a slave patched run native too (1.7.2)

A slave patches some of the Kickstart's instructions; a step written from the pristine image then missed its guard for ever, and those instructions, often
in loops, stayed on the interpreter. The observation of a run (`<observations>.kick`, in the conversion's private work folder, with the image itself) now
keeps the words as they stood; the steps come from those and from the image, and the library still keeps the addresses alone, no byte. Civilization: 14,988
Kickstart instructions interpreted on the main route become 19 of 4.42 million; California Games 48, Twylyte 10,638 of 49.0 million (0.022 %), on two routes of
3,600 frames, each frame equal to the fresh interpreted reference, the compressed copy too and the quick state with its sound. Native code and CPU fidelity only.
**What moves:** the Amiga's game stamp; no other console.

## Commodore Amiga: an archive with an intro or editor slave beside the game (1.7.2)

An archive with several slaves was refused. The slave named as the install's own folder is now the game, the others staying aside (`Superfrog/Superfrog.slave` beside
`SuperfrogIntro.slave`): 17 of the 25 such archives of the maintainer's library. A collection where no single slave is so named stays refused, never guessed.
**What moves:** the Amiga's game stamp; an install that was refused converts; nothing else changes.

## Exports of 1.7.0 in 1.7.1

1.7.1 is the release after 1.7.0 (published on 7 November 2026). This section is the index of its changes, one line per section below (or per machine page when a change has no
section here), with the stamps that section says move. Each section computed its stamps for its own change alone, on the tree of its branch; the totals are under the table and were
computed on `main` on 8 November 2026.

| Change | Game stamps that move | Host and build stamps | Quick states |
| --- | --- | --- | --- |
| [Adventure games (ScummVM): the options page, the keys and the supported status](#adventure-games-scummvm-the-options-page-the-keys-and-the-supported-status-171) | the Adventure (ScummVM) game stamp, and nothing else in that section | the Adventure (ScummVM) build stamp (`97d9ad0da628` to `fd819f80e824`) | no key moves; the saves are ScummVM's own, in `datas/` |
| [Host kit and resources: two small shared changes](#host-kit-and-resources-two-small-shared-changes-171) | **every machine's game stamp** (already moving in 1.7.1, so no conversion on top) | **every machine's host stamp** (already moving in 1.7.1); no build stamp | no key moves (the Mega Drive, Super Nintendo and CPS keys hash none of these files) |
| [Sony PlayStation opens as an experimental machine](#sony-playstation-opens-as-an-experimental-machine-171) | a new machine: the PlayStation stamps are new | its own | its key is new |
| [Atari ST opens as an experimental machine](ATARI_ST.md) (no section of this page; the facts are on the machine page) | a new machine: the Atari ST stamps are new | its own | its key is new |
| [Nintendo 64 opens as an experimental machine](NINTENDO_64.md) (no section of this page; the facts are on the machine page) | a new machine: the Nintendo 64 stamps are new | its own | its key is new |
| [Game Boy Advance: guarded native RAM code](GAME_BOY_ADVANCE.md#code-the-cartridge-does-not-hold-guarded-native-ram-code-7-november-2026) (no section of this page) | the Game Boy Advance | none stated | not stated |
| [Commodore Amiga: Examine no longer overwrites the memory behind a slave's FileInfoBlock](#commodore-amiga-examine-no-longer-overwrites-the-memory-behind-a-slaves-fileinfoblock-171) | the Amiga only (each section says so) | none | the Amiga's key moves where the section says so (a state of an earlier Amiga build is refused cleanly) |
| [Commodore Amiga: a route the game ends itself](#commodore-amiga-a-route-the-game-ends-itself-171) | the Amiga only (each section says so) | none | the Amiga's key moves where the section says so (a state of an earlier Amiga build is refused cleanly) |
| [Commodore Amiga: the icon's CUSTOM1 to 5, names with accents, a larger ExpMem and BaseMem, a registered WHDLoad](#commodore-amiga-the-icons-custom1-to-5-names-with-accents-a-larger-expmem-and-basemem-a-registered-whdload-171) | the Amiga only (each section says so) | none | the Amiga's key moves where the section says so (a state of an earlier Amiga build is refused cleanly) |
| [Commodore Amiga: the Kickstart's code runs as guarded native steps, written from the player's own image](#commodore-amiga-the-kickstarts-code-runs-as-guarded-native-steps-written-from-the-players-own-image-171) | the Amiga only (each section says so) | none | the Amiga's key moves where the section says so (a state of an earlier Amiga build is refused cleanly) |
| [Commodore Amiga: CIA-B enters the slave as the system leaves it](#commodore-amiga-cia-b-enters-the-slave-as-the-system-leaves-it-171) | the Amiga only (each section says so) | none | the Amiga's key moves where the section says so (a state of an earlier Amiga build is refused cleanly) |
| [Commodore Amiga: the chipset's collision detection is on](#commodore-amiga-the-chipsets-collision-detection-is-on-171) | the Amiga only (each section says so) | none | the Amiga's key moves where the section says so (a state of an earlier Amiga build is refused cleanly) |
| [Commodore Amiga: the window says so when the whole run is interpreted](#commodore-amiga-the-window-says-so-when-the-whole-run-is-interpreted-171) | the Amiga only (each section says so) | none | the Amiga's key moves where the section says so (a state of an earlier Amiga build is refused cleanly) |
| [Commodore Amiga: a quick state continues the sound sample for sample](#commodore-amiga-a-quick-state-continues-the-sound-sample-for-sample-171) | the Amiga only (each section says so) | none | the Amiga's key moves where the section says so (a state of an earlier Amiga build is refused cleanly) |

Taken together (`compilation_inputs.role_stamps` of the seventeen profiles, the tree of `v1.7.0` against `main`): **the game stamp and the host stamp of all fourteen earlier profiles move**
(the thirteen machines of 1.7.0 and Adventure (ScummVM)), and **no build stamp moves except the Adventure (ScummVM) one**. The Atari ST, the Nintendo 64 and the PlayStation are new, with
stamps of their own. The sections above that say "no other console's stamp moves" were computed before the three machines joined the registry and the notices; the sum is larger than
any of them.

| Machine | Game stamp (v1.7.0, now) | Host stamp (v1.7.0, now) | Build stamp |
| --- | --- | --- | --- |
| Master System | `ffb447e12968`, `63c93fcb0264` | `4c698ce40729`, `62a7e9f65d83` | `fe2d99b3cd5e` (same) |
| Game Gear | `9f3d2cd547bb`, `70eafce5937a` | `9e302b729213`, `fa5e7fa22b05` | `f5671c38cf26` (same) |
| Game Boy | `1c847126de1d`, `b218f94d2c75` | `d03f39763f54`, `2a0942586a4a` | `819a054ad881` (same) |
| NES | `88240b6d2e3b`, `af5a3a096738` | `a91c8c6c0d28`, `39c36bfa861a` | `8e0941f93b43` (same) |
| Mega Drive | `3c62c2e5c7a3`, `ed3a49ab59a8` | `b45d74b5e78f`, `8f4324fbcb85` | `9615ff2e96c8` (same) |
| Super Nintendo | `0bc2b194ed99`, `064bd8544d76` | `ebe78ef356a1`, `d35383911455` | `3f0a58ad3c7c` (same) |
| Neo Geo | `328279cbfc1c`, `b45ca489a2c9` | `098ae12034e1`, `f1fde4b7a652` | `110349f043bd` (same) |
| X68000 | `d42bb1882a76`, `107b51de2145` | `4cc410c21d5a`, `55ac9db11502` | `5903c0449429` (same) |
| CPS-1 | `b2ef983bc3fd`, `28dd85714948` | `ff2e8295501f`, `0220746ac9ad` | `2782cd370f91` (same) |
| CPS-2 | `71a11548e45d`, `cb7b5d304275` | `7f31bbdfb091`, `7889559074ad` | `81a51ad49349` (same) |
| PC Engine / TurboGrafx-16 | `78f5641c38ec`, `ebcbc2a403cd` | `bdcc346995e1`, `3da7363bd893` | `66d912662e5c` (same) |
| Game Boy Advance | `05e06c23687a`, `1658c523234f` | `f94b7ff7c92f`, `7b18d021f143` | `6b70933a9b0a` (same) |
| Amiga | `ff35e3b8af69`, `ba01a0a7e76e` | `136af9f804ed`, `b264a452712e` | `92ca8a0c142c` (same) |
| Atari ST | new, `fa09328f914f` | new, `f8a69516f53e` | new, `54b75964897d` |
| Nintendo 64 | new, `ec87144eb331` | new, `3c4f6ccca458` | new, `4f6fedf926c7` |
| Adventure (ScummVM) | `be8047b230ac`, `42dfc172e91c` | `4a96d24af08d`, `82088d749a09` | `97d9ad0da628`, `05417bbcea96` |
| Sony PlayStation | new, `920cf82497a6` | new, `5dbdb5df79ca` | new, `b6c9cf73b176` |

(First twelve hexadecimal digits of each stamp.) `LEGACY_GAME_STAMPS` stays empty. **So every export of 1.7.0, on every machine, is converted again, from its qualified paths, once, when the
player updates**, and the window offers it; it is not a quick host-only upgrade.

**Quick states.** The **Mega Drive and Super Nintendo keys move** (`native/runtime_catalog.inc` and `native/runtime_feedback.h`, which those two keys hash, changed): a quick state of 1.7.0 of
those two machines is refused cleanly (no compatibility key is carried, [GAME_STATES.md](GAME_STATES.md)); nothing is lost but that state. The **Amiga's key moves** with its sound-carrying state (an
earlier Amiga state is refused). The keys of the NES, the Neo Geo, the CPS-1, the CPS-2, the PC Engine and the X68000 hash none of the files that changed, so their states of 1.7.0 load; the
Master System, Game Gear and Game Boy have no such key. **Cartridge saves** are kept on every machine; the game saves of Adventure (ScummVM) are ScummVM's own.

## Adventure games (ScummVM): the options page, the keys and the supported status (1.7.1)

"Adventure (ScummVM)" ([SCUMMVM.md](SCUMMVM.md)) leaves the experimental status on the owner's decision of 7 November 2026: `retrorecomp/systems/scummvm.py` says `supported`, the
interface note and the documents follow in the eight languages, and the criteria are written in [SCUMMVM.md](SCUMMVM.md#what-supported-means-here) because the qualification matrix
(gates G1 to G16, risk cases, shared paths) is made for recompiled machines; `tests/test_machine_registry.py` asks of an emulated supported category a Linux witness and that page,
instead. The same release carries the options page and the keys of the game (the ScummVM patch `0002-retrorecomp-options-page.patch`, [SCUMMVM.md](SCUMMVM.md)).

**What moves.** `compilation_inputs.role_stamps` of the fourteen machines on the tree before the status (`fa196008`) and on this one: **only the Adventure (ScummVM) game stamp**,
`4e3367b550d2` before, `0369d5533936` after (the profile is a game input of that machine only; the options-page patch was already counted in `4e3367b550d2`, which replaced the
released `be8047b230ac`). Its build stamp moves too, `97d9ad0da628` to `fd819f80e824` (`scummvm_build.py` finds `.deps` from a packaged exe); the host stamps and the build stamps of every other machine do not move, and no other game stamp moves.

**The ScummVM pack and the CMake fix** move those two stamps again, and only those: game `aa2b67d2bcd4` to `8af339f2af21` (`systems/scummvm.py`, `scummvm_export.py`), build `fd819f80e824` to `de9fefa86a8b` (`scummvm_build.py`). The button itself is interface code (`gui_options.py`, `i18n.py`), which no stamp hashes. A runtime that is already current is not rebuilt; a stale one starts from a new build folder the first time, because folders made before this version carry no record of how they were configured.

**The menu colours** (`0003-retrorecomp-theme-colours.patch`, `_pack_theme` in `scummvm_build.py`) move the same two stamps once more, and only those: game `8af339f2af21` to `42dfc172e91c`, build `de9fefa86a8b` to `05417bbcea96`. The patch digest is part of every runtime's identity, so each engine family's runtime is rebuilt by its next conversion.

**Exports.** An adventure executable of 1.7.0 is converted again when its game stamp is checked (it has the old options and no Ctrl+F1 to Ctrl+F4); no other export is. **Quick states** and **cartridge saves**:
none moves, a game's saves are ScummVM's own, in `datas/`.

## Host kit and resources: two small shared changes (1.7.1)

**What moves.** The game and host stamps of every machine, compared entry by entry before and after. They move in 1.7.1 anyway, so no export is converted again because of this alone. No build stamp moves. The quick-state keys of the Mega Drive, the Super Nintendo and the CPS boards hash none of these files.

**What changes.** Off Windows, `resources.embed_resources` no longer rewrites its three generated files with the same bytes, so a second preparation of a game relinks nothing; the Game Boy Advance's local workaround is gone. On Windows it does nothing, as before. `rrhk_action_pressed` and `rrhk_action_held` give an adapter the actions it handles itself, as the player bound them: the PlayStation's Analog button and the Nintendo 64's Stick actions use them, and neither adapter includes `hostkit_internal.h` any more. The rules are those the adapters had. `RrhkMachine.native_caption` names the window title's words while nothing is interpreted: the PlayStation, the Nintendo 64, the Atari ST and the Amiga say "Native CPU, emulated hardware", every other machine still "Native code".

**Checked.** The unit test of the embedding (on Windows, through `write_embedding`) and the kit's capabilities self-test with a virtual controller. **Not checked yet:** a game of either machine played or converted with these calls, and the embedding on Linux; both belong to the release checks.

## Sony PlayStation opens as an experimental machine (1.7.1)

The Sony PlayStation (profile `psx`, [PLAYSTATION.md](PLAYSTATION.md)) opens to players as an **experimental** machine. No export of
it exists before this release, so nothing is upgraded. It takes no path from the shared base and gives none. The machine is Beetle
PSX, pinned and fetched on the first conversion, with anchored changes listed in `psx_beetle.REPLACEMENTS`; the game executable
is GPL-2.0 as a whole. Its files are game inputs of `psx` alone: no other console's stamp moves for them.

## Commodore Amiga: Examine no longer overwrites the memory behind a slave's FileInfoBlock (1.7.1)

Installs that load their files through the slave's own operating-system emulation (the `Examine` flag: 1,180 of the 2,967
Amiga 500 installs of the maintainer's library that the profile reads, 1,040 of them with a Kickstart) stopped at boot with
"not enough memory" (AmigaDOS 103). The cause, found by tracing exec: the emulation calls `resload_Examine` with a
FileInfoBlock that has only 240 bytes before the next free chunk; the layer cleared and wrote all 260 bytes of a
FileInfoBlock, zeroing that chunk's header, so exec's fast-memory list held one chunk of size 0 and every later
allocation failed. `Examine` and `ExNext` now write only the fields they have values for (the name up to its NUL, the
sizes, the date, an empty comment) and leave the rest of the buffer alone. Another World (FR) and 4D Sports Boxing, the
two cases Arthur met, run; so do Maniac Mansion, Monkey Island 2 and Beneath a Steel Sky (the first two and the last
stopped before the change). **What moves:** the Amiga's game stamp (`native/amiga_whdload/rr_resload.c`); no other console.

## Commodore Amiga: a route the game ends itself (1.7.1)

A scripted route may make a game quit through its own menu (`resload_Abort` with `TDREASON_OK`): 4D Sports Boxing does so at
frame 1,702 of the exploration route. Such a reference run is accepted when it lasted at least 1,000 frames; every later run of
that route (native passes, the compressed copy, the quick-state continuation) must end the same way, and its trace and resload
log, the final call included, must equal the reference's. The report marks the route `ended_by_game` with the frames it ran.
Any other stop still fails the conversion. **What moves:** the Amiga's game stamp (`amiga_conversion.py`, the session and the
player); no other console.

## Commodore Amiga: the icon's CUSTOM1 to 5, names with accents, a larger ExpMem and BaseMem, a registered WHDLoad (1.7.1)

Four changes to what a slave may ask of the layer, found by running 24 installs of the library headless with the player's
Kickstart 1.3. **CUSTOM1 to CUSTOM5** are read from the install's own icon (`<slave>.info`, its ToolTypes, as WHDLoad does; a
ToolType in parentheses is off) and answered to `resload_Control`; there is no per-game setting in the window. 432 of the 2,967
installs carry one (413 CUSTOM1); Might & Magic 3 (DE) needs CUSTOM1=2 to start. **Names**: a guest name is ISO-8859-1 and the
install's file name UTF-8; they are converted both ways (23 archives have accents), so a slave finds a file it names with an
accent. **Memory**: an ExpMem that does not fit the 1.5 MiB of slow RAM (88 installs of the library did not fit) is given to a
Zorro II fast RAM board configured at `$200000` (up to 8 MiB), with the slave area staying in slow RAM; a BaseMem above 1 MiB
gets 2 MiB of chip RAM (3 installs). 72 of the 88 now fit (59 of them with Kickstart 1.x); the other 16 need a 512 KiB
Kickstart (a later step). **Registered**: 198 slaves of the library name
the undocumented `resload_Control` tag `WHDLTAG_Private3` and test its answer for non-zero (zero makes them stop with
`TDREASON_MUSTREG`, "WHDLoad must be registered", or skip patches); it is answered 1, a value of ours, not one read from
WHDLoad. Civilization, which stopped with that reason, runs. **Measure:** headless, interpreted, 1,500 frames, each with a
picture: Settlers, Conquests of the Longbow, Civilization, Ambermoon, Kings Quest 5, UFO Enemy Unknown, Zeewolf, Skidmarks,
Cyber Games (native code, CPU fidelity, hardware fidelity and gameplay are not measured by this run). **Known limit as written in
1.7.1, corrected in 1.7.2:** this note blamed a 68020 for three installs that stop at boot; the real WHDLoad boots them on a 68000 (see
the 1.7.2 entry on the keyboard's handshake).
**What moves:** the Amiga's game stamp (`amiga_session.cpp`, `rr_resload.c`, `amiga_player.c`, `amiga_conversion.py`); no other
console. **Quick states:** the Amiga's key moves, as between any two Amiga builds.

## Commodore Amiga: the Kickstart's code runs as guarded native steps, written from the player's own image (1.7.1)

An install that runs with the player's Kickstart spent most of its instructions in the Kickstart (81 to 98 % in Might & Magic 3,
Civilization and Skidmarks), all on the counted interpreter. The player now observes the Kickstart's instructions by **address
only**; the conversion keeps those addresses in the private memory of that image (`converter-kickstart-addresses.txt`, numbers,
never a byte, one folder per image identity) and, when it writes the guarded steps, reads the words of each instruction from the
player's own image in memory. The steps keep the live-word guard of every step, so a Kickstart word a slave patched falls back to the
counted interpreter. The generated source and the game built from it exist only in that player's private work folder and export;
nothing derived from the image is shared, and the observation file and the library hold addresses only (**changed in 1.7.2:** the run's own
observation of the Kickstart keeps the words as they stood, a slave's patches included, in the conversion's private work folder only; the library
still keeps the addresses alone). **Measure** (Civilization,
the real converter, two routes of 3,600 frames, validated against the fresh interpreted reference, the compressed copy and the
quick state): the interpreted share fell from 97.7 % to 0.34 % (14,988 Kickstart instructions still interpreted, 4.30 million
native on the main route). This is the native-code measure only; CPU fidelity is the frame-by-frame equality with the interpreted
reference on those scripts, and hardware fidelity, gameplay and latency are not measured. **What moves:** the Amiga's game stamp
(`amiga_session.cpp`, `amiga_player.c`, `amiga_conversion.py`); no other console, and no shared 68000 file or path format is touched.
**Quick states:** the Amiga's key moves, as between any two Amiga builds.

## Commodore Amiga: CIA-B enters the slave as the system leaves it (1.7.1)

Blood Money played noise ("a 56K modem") from the first tune on. Cause, found by comparing with the real WHDLoad (private run of Copperline):
the slave's loader wrapper adds 79 tracks to the offset of a `resload_DiskLoad` when bit 2 of CIA-B's port B (`$BFD100`, the disk side
select) reads 0, and our boot ROM left CIA-B at its reset state, every pin an input, so the bit always read 1: the music samples (track 107)
were read from track 28 instead, whose data the game played as sound (the same lengths, periods and pointers as on the real machine, other
bytes). The real machine has CIA-B DDRA `$C0` and DDRB `$FF` while a slave runs (the disk lines are outputs, so a read gives back the
latch). The boot ROM now sets CIA-B's PRA `$F8`, PRB `$FF` (no drive selected, motor off), DDRA `$C0` and DDRB `$FF`, in that order.
After the change the three sample regions of Blood Money are byte for byte those of the real machine (0 of 74,256 bytes differ) and the
sound has tonal structure instead of flat noise. 26 slaves of the maintainer's library name `$BFD100` in their own code (Blood Money,
Menace, Nebulus, North And South, Lotus, Space Ace and others), so other disk-side readers may have loaded wrong tracks too; the native
steps were never involved (the run on the interpreter plays the same noise). **What moves:** the Amiga's game stamp
(`native/amiga_machine/amiga_session.cpp`); no other console. **Quick states:** the Amiga's key moves, as between any two Amiga builds.

## Commodore Amiga: the chipset's collision detection is on (1.7.1)

A real Amiga always detects collisions between sprites and between sprites and the playfields (CLXCON/CLXDAT); vAmiga ships the three
detections off for speed and the Amiga machine did not turn them on, so a game that reads CLXDAT never saw a collision. They are on now
(`native/amiga_machine/amiga_session.cpp`). Library check by counting CLXDAT reads over the standard route: Blood Money reads it (36
reads in 2,500 frames), Xenon 2, Turrican, Shadow of the Beast, R-Type, Menace, Armalyte, Battle Squadron, Rick Dangerous, Lotus 2, Speedball 2 and
Wings of Death do not (nor Apidya). **What moves:** the Amiga's game stamp; no other console. A game that reads CLXDAT may now play
differently from an earlier export of it (the detection a real Amiga performs; the match of the game's behaviour with hardware is not measured). **Quick states:** the Amiga's key moves, as between any two Amiga builds.

## Commodore Amiga: the window says so when the whole run is interpreted (1.7.1)

With `--reference-cpu` (every instruction on the interpreter) the window's title said "Native code", because no hook counts instructions in
that mode. The Amiga adapter now reports the run as interpreted, so the title reads "Interpreter fallback". Reports are unchanged (they count
through the player). **What moves:** the Amiga's host and game stamps (`amiga_player.c`, `rrhk_amiga.inc`); no other console.

## Commodore Amiga: a quick state continues the sound sample for sample (1.7.1)

vAmiga's snapshot leaves out the memory of its sound path, so the samples after a load differed from an unbroken run and the
conversion could not compare them. The adapted core (`retrorecomp/amiga_vamiga.py`, `Ports/AudioPort.h`, MPL-2.0 like the file) now
saves and restores the four samplers' pending samples, the three filters' memory, the sub-sample fraction, the master volume ramps
and the muted flag; the player appends them to its state file and clears the output stream after a load. Headless, a state
saved mid-run and resumed in a fresh process gives the same sound hash on all 200 frames compared (Apidya, Zeewolf, Cyber Games),
with the CPU registers, RAM and picture; the conversion now compares the sound after a load too. **What moves:** the Amiga's game
stamp (the adapted core, `amiga_session.cpp`, `amiga_conversion.py`); no other console. **Quick states:** the state file schema is
now `RRAMIGA-STATE-2`: states of earlier Amiga builds are refused cleanly. Hardware fidelity and physical latency are not
measured by this check.

## Exports of 1.6.9 in 1.7.0

1.7.0 is the release after 1.6.9 (published on 6 November 2026). This section is the index of its changes, one line per section below, with the stamps
that section says move. Each section computed its stamps for its own change alone; the totals are under the table. It lists what is on `main` so far.

| Change | Game stamps that move | Host and build stamps | Quick states |
| --- | --- | --- | --- |
| [Computers: a press of the middle button releases the mouse](#computers-a-press-of-the-middle-button-releases-the-mouse-170) | none | X68000 host (`rrhk_computer.inc`) | no key moves |
| [Game Boy Advance opens as an experimental machine](#game-boy-advance-opens-as-an-experimental-machine-170) | none (a new machine: Game Boy Advance stamps are new) | host stamp of all eleven other consoles (THIRD_PARTY_NOTICES) | none (no earlier export) |
| [Host kit: analog sticks, rumble, the 3D graphics page, larger pictures and disc change](#host-kit-analog-sticks-rumble-the-3d-graphics-page-larger-pictures-and-disc-change-170) | none | **host stamp of all eleven consoles** (the kit, `runtime_catalog.inc`) | **the Mega Drive and Super Nintendo keys move** (the catalogue); no other key |
| [Capcom CPS-2 leaves the experimental status](#capcom-cps-2-leaves-the-experimental-status-170) | CPS-1 (and CPS-1.5, the same board) and CPS-2; the other nine consoles keep theirs (`path_profiles.py` untouched) | **host stamp of every console** (`artwork.py`, box art of the CPS family) | no key moves (`native/cps1_persistence.c`, the EEPROM writer, is hashed by none) |
| [PC Engine / TurboGrafx-16: US cards, the reset-instruction tie-break, the Linux build](UPGRADES_HISTORY.md#pc-engine-an-experimental-machine-169) (the paragraph "US TurboGrafx-16 cards") | the PC Engine only (the reader, the profile and the report writer) | none | not stated |

| [The index of native steps may have its own language](#the-index-of-native-steps-may-have-its-own-language-170) | **every console** (`systems/specs.py`, an input of every game stamp), and the X68000 again (`m68k_observed.py`) | none | no key stated to move |
| [Covers: a subtitle that names the game, and extra names from a profile](#covers-a-subtitle-that-names-the-game-and-extra-names-from-a-profile-170) | none | **host stamp of every console** (`cover_titles.py`, `artwork.py`) | no key moves |
| [Commodore Amiga: an experimental machine](#commodore-amiga-an-experimental-machine-170) | a new machine: the Amiga stamps are new; its profile and converter modules are the only game inputs it adds | the notices (a vAmiga row) and the Amiga files; no build stamp | the Amiga's key is new; no other console's key moves for it |
| [The F12 recorder accepts the hints of every machine](#the-f12-recorder-accepts-the-hints-of-every-machine-170) | **the game stamp of all thirteen machines** (`runtime_feedback.c` and `.h`, `freshness.py`) | none | no key moves for it (the Mega Drive and Super Nintendo keys hash the recorder but already move) |
| [Commodore Amiga: the player's own Kickstart 1.3](#commodore-amiga-the-players-own-kickstart-13-170) | the Amiga only (`f68fb739871c` at the time of the section) | none | the Amiga's key moves (a state of an earlier Amiga build is refused cleanly); no other key |
| [Adventure games (ScummVM): a category of its own](#adventure-games-scummvm-a-category-of-its-own-170) | **the game stamp of the thirteen earlier machines** (`batch.py`, `report_schema.py`; no new conversion on top of the others); the ScummVM stamps are new | **host stamp of the thirteen earlier machines** (the notices, the licence pages); the ScummVM stamps are new | no key moves; the exports have no state of ours |

<!-- Rows of the changes merged after this index go here, in the order of their merge, with their new stamps and keys. -->

Taken together (`compilation_inputs.role_stamps` of the eleven consoles, the tree of `v1.6.9` against `main`, from the stamps each section lists): **the game stamp and the host stamp of the eleven consoles of 1.6.9 move; no build stamp moves** (the Amiga section computed it on the tree of `v1.6.9`; the game stamps move through
`systems/specs.py`, which every game stamp hashes, and the host stamps through the notices, the host kit and the box-art modules). The Game Boy Advance and the Amiga are new. So every export of 1.6.9
is converted again from its paths, once, when it is upgraded. `LEGACY_GAME_STAMPS` stays empty. The recorder change above moves the game stamp of all thirteen machines for itself, and adds no conversion on top of this total. Adventure (ScummVM) is a fourteenth profile with stamps of its own, new; it moves no stamp that was not already moving.

**Quick states.** Only **the Mega Drive and the Super Nintendo keys** move (the host kit's strings are in `native/runtime_catalog.inc`, which those two keys hash): a quick state
written by a Mega Drive or Super Nintendo export of 1.6.9 is refused cleanly (no compatibility key is carried, [GAME_STATES.md](GAME_STATES.md)); nothing is lost but that state. The keys of the
NES, the Neo Geo, the CPS-1 and CPS-1.5, the CPS-2 and the X68000 hash none of the files that changed, so their 1.6.9 states load (the PC Engine section does not state its key); the Game Boy Advance and the Amiga have keys of their own, new; the Master System, Game Gear and Game Boy have no key.
**Cartridge saves** are kept on every console; the EEPROM of the CPS-1.5 and the CPS-2 is now written by a worker thread (a stop within about a second of the last change loses that change).

## Computers: a press of the middle button releases the mouse (1.7.0)

On the computers, a press of the middle mouse button (the wheel) now releases a captured mouse, as Ctrl+Alt+M does; the
button never reaches the game (the X68000's and the Amiga's mice had two buttons). The capture notices say so, in English
and French. What moves: the **host stamp of the X68000** (`native/hostkit/adapters/rrhk_computer.inc`, host role); no game
or build stamp, no quick-state key. An export of 1.6.9 keeps working as it is; reconverting it brings the middle-button release.

## Host kit: analog sticks, rumble, the 3D graphics page, larger pictures and disc change (1.7.0)

Five capabilities of the player shell for the PlayStation, written for every machine ([HOST_KIT.md section 2.4](HOST_KIT.md#24-sticks-the-graphics-page-larger-pictures-rumble-and-discs-170),
decision [D14](HOST_KIT.md#d14)): `rrhk_pad_axes` and a Stick dead zone row, the F3 graphics page, a picture that grows past
its opening size, `rrhk_rumble` and a shared Vibration row, a Change disc action, and up to twenty controls per machine
(`RRHK_MAX_ACTIONS` 12 to 20; an F2 page scrolls past fifteen rows; the triggers bindable as buttons with `trigger_buttons`).
Each one is a new field of the machine table (or a limit no machine of 1.6.9 reaches) that is off when an adapter leaves it
out, and **no adapter of 1.6.9 declares one**: on the eleven consoles F3, the menus, the input, the bindings and preferences
(the X68000's `player.cfg` included) and the pictures are unchanged (A/B below).

**What moves.** Computed with `compilation_inputs.role_stamps` of the eleven consoles, the tree of `main` at `27e30e0` against
this change (all five capabilities, the twenty controls and the review fixes, recomputed on the final tree): **the host stamp of all eleven consoles** (`native/hostkit/hostkit.h`, `hostkit_internal.h`, seven files of
`native/hostkit/shell/` and `native/runtime_catalog.inc` are host inputs). **No game stamp and no build stamp moves**: an export
of 1.6.9 that has nothing else to rebuild is upgraded (rebuilt from its paths, no rediscovery).

| Console | Game stamp | Host stamp (before, after) | Build stamp |
| --- | --- | --- | --- |
| Master System | `3e16a0301d90` (same) | `1b834d7b9fbc`, `5e19fd3e1507` | `fe2d99b3cd5e` (same) |
| Game Gear | `4f9d69e86e89` (same) | `c9e0e360f031`, `6a0a2110937d` | `f5671c38cf26` (same) |
| Game Boy | `ff30f88ca9f1` (same) | `772d06158394`, `c545c7240609` | `819a054ad881` (same) |
| NES | `a3537f590fcf` (same) | `21b599f4ec81`, `82968356d271` | `8e0941f93b43` (same) |
| Mega Drive | `a0de8eae71a4` (same) | `7bda64083b03`, `d6f288c77b93` | `9615ff2e96c8` (same) |
| Super Nintendo | `ae2146874e49` (same) | `2a4bc2c7b468`, `45d3816ac86c` | `3f0a58ad3c7c` (same) |
| Neo Geo | `a3733e1113ff` (same) | `1f2e8a0e2450`, `57af9580985d` | `110349f043bd` (same) |
| X68000 | `6c7509bf49d2` (same) | `47212d53043d`, `1df1d70e5a4b` (with the middle-click release above) | `5903c0449429` (same) |
| CPS-1 | `e6380523c2d1` (same) | `0f8432dcd5c5`, `33eca10a92c8` | `2782cd370f91` (same) |
| CPS-2 | `8d2c63c4b35a` (same) | `0f2bade664f6`, `453594c99c49` | `81a51ad49349` (same) |
| PC Engine | `c8545bf9018e` (same) | `6ea8ea8ac8eb`, `98e3865903b4` | `66d912662e5c` (same) |

(First twelve hexadecimal digits of each stamp.)

**Quick states.** The kit's nine new strings are in the five-language game catalogue, `native/runtime_catalog.inc`, which the
**Mega Drive and Super Nintendo** keys hash (`compilation_inputs.state_native_files`): **those two keys move**, and a quick state
written by a Mega Drive or Super Nintendo export of 1.6.9 is refused cleanly by its 1.7.0 build (no compatibility key is carried,
[GAME_STATES.md](GAME_STATES.md)); nothing is lost but that state. The keys of the NES, the Neo Geo, the CPS-1, the CPS-2, the
PC Engine and the X68000 hash none of the changed files and do not move; the Master System, the Game Gear and the Game Boy have
no key of this kind. `native/game_options.h` and `native/retro_menu.c` are unchanged. **Cartridge saves** are kept on every console.

**Preferences.** Nothing is renamed or read differently on the eleven consoles. A machine that declares the new fields adds
`deadzone` to `[<Console>.Gamepad.PlayerN]`, its options' keys to `[<Console>.Video]`, and `rumble` to `[Manettes]`.

**A/B** (Windows, llvm-mingw, offscreen SDL, `tools/hostkit_ab.py` with its virtual clock and modelled audio device; the A side
built from `git archive 27e30e0 native tools`, the B side from this tree, both against the same kept builds):

* X68000 (`build-x68`, the kept conversion of `.build/x68`): the scripts `play` (3,280 frames), `autofire`, `keyboard`, `mouse`,
  `states` and `ui` (518 frames, 47 pictures of help, F2 and options pages in five languages) with the machine's per-frame trace
  (`--trace`): **identical**, every file (pictures, trace, audio, window log, preferences).
* CPS-1, Warriors of Fate (three players, a DIP page; `build --refresh-kit`), the standard battery of 3,968 iterations (both
  players' keys and pads, the filters and display modes, every language, every F2 page, states, preferences): **identical** (61
  files: 3,968 picture hashes, 52 captures, 2,768 audio pushes, the state file, the preferences).
* Both A/B runs were made again on the final tree (the twenty controls, the scrolling pages, `trigger_buttons` and the review fixes): identical
  again, every file.
* ROM-free: `tests/test_hostkit_capabilities.py` (the five capabilities on a fake machine of eighteen controls, its scrolling F2
  page and its triggers as L2 and R2, then the same machine with every field left out), `tests/test_hostkit_players.py`, `tests/test_hostkit.py` and the X68000 harnesses of the suite.

Not measured: a real gamepad (stick values and rumble go through SDL's virtual controller only), a real display, Linux, the other
consoles by A/B (same shell code; only the X68000 and the CPS-1 were run), and a 3D machine itself (none exists yet).

## Game Boy Advance opens as an experimental machine (1.7.0)

The Game Boy Advance (profile `gba`, [GAME_BOY_ADVANCE.md](GAME_BOY_ADVANCE.md)) opens to players as an **experimental** machine in 1.7.0. It is new:
no export of it exists before this release, so nothing is upgraded. It takes no path from the shared base and gives none (it is not in the base). It asks for
your own BIOS (`gba_bios.bin`, checked by its SHA-1); a converted game holds code derived from it and stays private to you. The engine is
[mstan/gbarecomp](https://github.com/mstan/gbarecomp) pinned at `c1a5fda36fb4` (PolyForm Noncommercial, with the author's permission) and its submodule
`arm-recomp-core` (MIT), fetched on the first conversion and carried with 44 anchored patches ([UPSTREAMS.md](UPSTREAMS.md)).

What the change moves, computed with `compilation_inputs.role_stamps` on `main` (27e30e03) and on the branch (game, host, build, first 12 hexadecimal digits):

| Console | Game stamp | Host stamp | Build stamp |
|---|---|---|---|
| sms | 3e16a0301d90 (same) | 1b834d7b9fbc → 033d55196e25 | same |
| gg | 4f9d69e86e89 (same) | c9e0e360f031 → 1a565bafd044 | same |
| gb | ff30f88ca9f1 (same) | 772d06158394 → 67546878fe4b | same |
| nes | a3537f590fcf (same) | 21b599f4ec81 → b49e7d1d6a9a | same |
| md | a0de8eae71a4 (same) | 7bda64083b03 → 75dc61baeb8b | same |
| snes | ae2146874e49 (same) | 2a4bc2c7b468 → ab414537de23 | same |
| ng | a3733e1113ff (same) | 1f2e8a0e2450 → a17e0dd77249 | same |
| cps1 | e6380523c2d1 (same) | 0f8432dcd5c5 → 28aaed430011 | same |
| x68 | 6c7509bf49d2 (same) | 47212d53043d → be0daff05bb1 | same |
| cps2 | 8d2c63c4b35a (same) | 0f2bade664f6 → 56a02d1ee4c6 | same |
| pce | c8545bf9018e (same) | 6ea8ea8ac8eb → 78d65184c1bf | same |
| gba (new) | a90b434c6d70 | 8eb4c3a0974e | 6b70933a9b0a |

- **No game stamp and no build stamp of another console moves.** The profile declares its own ZIP limit (`archived_rom_limits`), its own path order (11), its own
  feedback kind (21) and its own files in `stamp_inputs.py`; no shared module was edited for it besides the registry (an interface module that no stamp hashes).
- **The host stamp of the eleven other consoles moves**, because `THIRD_PARTY_NOTICES.md` (a host input) gains the row of gbarecomp and arm-recomp-core. No
  export changes behaviour: a host stamp that moved only means the licence page of the next conversion is newer.
- `.gba` is no longer a "foreign" extension: a `.gba` file is claimed by the Game Boy Advance profile (or reported as unavailable when the installation lacks its files).

## The index of native steps may have its own language (1.7.0)

The shared generator of observed 68000 code (`retrorecomp/m68k_observed.py`) wrote the index of native steps in the language of the steps. The index is
C (its page tables are array designators); the Amiga's steps are C++ (they call Moira's instruction templates), and a C++ index needed a warning switched
off. `ObservedCode.index_extension` (`retrorecomp/systems/specs.py`) names the extension of `steps/index` when it differs from the steps'; `None`, the
default, keeps the steps' extension. The Amiga sets `'.c'`: its steps are C++ functions with C linkage and its index is C. One line of `write_steps`
reads the field; no other line of the shared module changes. A contract test (`tests/test_observed_index_contract.py`) writes the index of every
machine that declares an `ObservedCode` and compiles it, warnings as errors, in the language its extension names; the former C++ index of the Amiga fails it.

**Proof that the X68000 does not change.** The native project of two games (R-Type and Lemmings, the variants of their recorded observations) was written
with the converter of `main` and with this tree: **78 files, 0 differences** (the decoder's build folder and the logs name the tree and are left out).
The generator's revision (`x68_knowledge.GENERATOR_REVISION`) stays 1, as for the move of the generator in 1.6.9, so no qualified path is lost; the
digest of `retrorecomp/m68k_observed.py` in `tests/x68_generator_pins.json` is updated.

**What moves**: `retrorecomp/systems/specs.py` is an input of the game stamp of all nine consoles, so **the game stamp of every console moves**;
`retrorecomp/m68k_observed.py` moves the game stamp of the X68000 again. No host or build stamp moves. The output of the X68000's generator is
identical, but an export upgraded across this change is converted again once, as the stamps say.

## Commodore Amiga: resload_Abort read as documented, and said in words (1.7.0)

`resload_Abort(success, primary, secondary)` takes its arguments at `(a7)`, as the autodoc's synopsis says (the documented call
jumps through `rts`, so no return address lies above them); the layer read them one slot too far, so an aborting slave
showed three meaningless numbers ("the slave ended the program (103, 53452, 16730414)"). It now reads them at `(a7)`
(skipping a return address when a slave arrived with `jsr`) and says what the slave could not do: "the install could not
read the file '4DBoxing' (not enough memory, AmigaDOS error 103; resload_Abort reason 1)". **What moves:** the Amiga's game
stamp (`native/amiga_whdload/rr_resload.c`); no other console.

## Commodore Amiga: the player's own Kickstart 1.3 (1.7.0)

An install that asks for a Kickstart 1.x (in its slave header or through `resload_LoadKick`) now converts with the player's own
image, chosen in Options > Commodore Amiga ([AMIGA.md](AMIGA.md), section 2a). The image goes only into the conversion's private
work folder and the player's own export; its code is interpreted and counted apart. Installs that need none are converted as
before. Kickstart installs were not run on Linux (the same machine path; not witnessed there).

**What moves** (`compilation_inputs.role_stamps` of `main` at 575c900a against this branch, 6 November 2026): **the game stamp of the Amiga only** (`f68fb739871c`); no other console's stamp moves, no host or build stamp moves.
**Quick states:** the Amiga's key moves (its
session sources changed): Amiga states of earlier builds are refused cleanly, as they are between any two Amiga builds.

## Covers: a subtitle that names the game, and extra names from a profile (1.7.0)

Two generic changes to the box lookup (`retrorecomp/cover_titles.py`, `retrorecomp/artwork.py`). A query without a subtitle that
equals a catalogue entry's main title no longer drops that entry for an edition word found only in its subtitle, when the
subtitle holds other words too ("Speedball 2" finds "Speedball 2 - Brutal Deluxe"; "Super Metroid - Redux", "Tetris DX" and
bracketed tags still count as editions). And a profile may offer extra names for its games' boxes (`cover_titles(path)`, an
optional capability read with `getattr`), tried only after the file's name and the title find nothing: the Amiga offers the
slave's own name, cleaned of its decorations ("Lotus 2" finds "Lotus Turbo Challenge 2").

**Proof without conversions:** the box choice was replayed for the 1,232 conversion reports of `Export` (nine machines) against
the cached catalogues, with the tree before and after: 2 choices change, both Amiga (Lotus 2 and Speedball 2, none before).

**What moves:** both modules are host inputs of every console (`HOST_MODULES`): **the host stamp of every console moves**, no
game stamp; an export of 1.6.9 is upgraded without rediscovery for that part.

## Commodore Amiga: an experimental machine (1.7.0)

The Amiga 500 opens as an experimental profile (`amiga`, [AMIGA.md](AMIGA.md)): WHDLoad installs that need no Kickstart, on the
vAmiga Core (MPL-2.0 per file) and its 68000 Moira (MIT), with our own resload layer. Each Amiga game carries its notices as
resource 203, and THIRD_PARTY_NOTICES has a vAmiga row.

**Offered to players.** The profile is no longer for developer installations only: like the Game Boy Advance and the PC
Engine, it is listed when the installation carries its converter files (`amiga.converter_available`), its options note no
longer says otherwise in the eight languages, and the credits list it as experimental. Linux is `witnessed` (one install
converted and validated on a Debian 13 PC; G13 `P`). Against the merged `main` this moves **the Amiga's game stamp only**
(its profile and converter modules); no other console's stamp moves. The check reads the Amiga's native files only: a
packaged converter keeps its Python modules inside the executable, so a check of `amiga_conversion.py` as a file had hidden
the profile from every packaged 1.7.0 build (found by the release check of the packaged executable; fixed before
publication, the Amiga's game stamp only). The same check then found the Amiga's decoder looking for the shared
generated decoder folder in the packaged converter's unpacked files instead of its working folder (`ROOT`, as the X68000
does); fixed too, the Amiga's game stamp only.

**What moves** (`compilation_inputs.role_stamps` of the tree of `main` at 27e30e03 against this branch, computed on 6 November
2026, the change of `index_extension` above included): **the game stamp and the host stamp of the eleven consoles of 1.6.9**; no
build stamp. The game stamps move through the profile modules and `systems/specs.py`, the host stamps through
THIRD_PARTY_NOTICES. The Amiga's stamps are new. **Quick states:** the Amiga's key is new. Outside the Amiga's own folders the
branch changes no native file (`git diff 27e30e03 -- native`), and the X68000's generated code is identical (section above), so
no other console's key moves and their 1.6.9 states load.

## The F12 recorder accepts the hints of every machine (1.7.0)

A game's player keeps a small set of the interpreter misses it meets (the hints for the next recompilation, written at normal shutdown, recording switched on and off by F12,
[RUNTIME_FEEDBACK.md](RUNTIME_FEEDBACK.md)). `native/runtime_feedback.c` refused every kind above `RR_FB_CPS1_Z80` (16), the last kind of the CPS-1, so **the interpreter misses of
the CPS-2, the PC Engine, the Game Boy Advance and the Amiga, whose kinds are 17 and above, were never recorded**: no hint of those machines could reach a feedback file. The bound is now `RR_FB_MAX_KIND` (`native/runtime_feedback.h`, 23, the largest kind a profile may declare; a larger one
is still refused as garbage), and `tests/test_system_profiles.py` fails when a profile declares a kind above it. Alongside, `retrorecomp/freshness.py` identifies a game that is a
folder (not a file) by its `item.sha256` instead of hashing it as a file, which would fail.

**What moves.** Computed with `compilation_inputs.role_stamps` of the thirteen machines on the tree of `main` before this change (`575c900a`) and on this tree (first twelve
hexadecimal digits of each stamp, 6 November 2026):

| Machine | Game stamp (before, after) | Host stamp | Build stamp |
| --- | --- | --- | --- |
| Master System | `e79637610588`, `49fe6e32e245` | `52732894c705` (same) | `fe2d99b3cd5e` (same) |
| Game Gear | `c42ec7af339f`, `8c00b18cbb84` | `12ddf0d7f71c` (same) | `f5671c38cf26` (same) |
| Game Boy | `e9fd59f69c23`, `84ee8993f728` | `cf765eccafd3` (same) | `819a054ad881` (same) |
| NES | `e1e7dbd43df6`, `70294cfa87ce` | `71877ffa5602` (same) | `8e0941f93b43` (same) |
| Mega Drive | `405fbb268e93`, `a51188bb861f` | `81f2da5cd72d` (same) | `9615ff2e96c8` (same) |
| Super Nintendo | `75e3f274ba12`, `183e40e13480` | `86e398dab378` (same) | `3f0a58ad3c7c` (same) |
| Neo Geo | `d507c3759c6a`, `dc211c9479da` | `b7fe8c803579` (same) | `110349f043bd` (same) |
| X68000 | `2f70a9be8803`, `ad8e4bc0f227` | `1ca7429d24bd` (same) | `5903c0449429` (same) |
| CPS-1 | `e14379ea4193`, `da3f9a93f08f` | `075e0ff74ad2` (same) | `2782cd370f91` (same) |
| CPS-2 | `aece1f235d63`, `d0dfdf7fcd0a` | `6d09623637fd` (same) | `81a51ad49349` (same) |
| PC Engine / TurboGrafx-16 | `dd23d12432c7`, `61785d10f6b3` | `e688aeb8d524` (same) | `66d912662e5c` (same) |
| Game Boy Advance | `25a43b11f017`, `a8f3639ad2c9` | `f91cddfbe6b9` (same) | `6b70933a9b0a` (same) |
| Amiga | `55862e6f7665`, `f6905ac1baf4` | `8e7c7e682d10` (same) | `92ca8a0c142c` (same) |

(First twelve hexadecimal digits of each stamp.) **The game stamp of all thirteen machines moves** (`native/runtime_feedback.c` and `.h` are game inputs of every machine, as is
`retrorecomp/freshness.py`); no host stamp and no build stamp moves for this change. Against the tree of `v1.6.9` the game stamps of the eleven machines of 1.6.9 had already moved
(see the index above), so this adds no conversion to a player who upgrades from 1.6.9.

**What it means for players.** A moved game stamp means that an export is not upgraded in the quick host-only way (rebuilt from its learned paths, without discovery): it is
**converted again, with its discovery routes**, from its qualified paths, once, when the player updates. Every export of 1.6.9, on every console, is in that case in 1.7.0; the cost
is the length of a conversion per game. The reason: an export made by 1.6.9 carries the recorder that drops the hints, and only a rebuilt game carries the new one; Arthur decided it
knowingly (« fix it in 1.7.0 »).

**Quick states.** No key moves for this change: the Mega Drive and Super Nintendo keys hash `runtime_feedback.c` and `.h` too, and they already move for the host kit's catalogue
(a quick state of 1.6.9 of those two machines is refused once, not twice); the other machines' keys hash none of the files changed. **Cartridge saves** are kept.

**Not measured.** The cost of the changed test in the recorder (one comparison per recorded miss) and a game of each new machine played to a normal shutdown to see its feedback file
written: the change is proved by the bound test and by the stamps, not by an A/B of a game.

## Adventure games (ScummVM): a category of its own (1.7.0)

"Adventure (ScummVM)" ([SCUMMVM.md](SCUMMVM.md), profile `scummvm`) is added as an **experimental** category of its own: a folder of an adventure game that ScummVM's
detection recognises becomes one executable holding ScummVM and the player's own game files, **emulated and 0 % native by design**. It is new: no export of it exists before 1.7.0, so
nothing is upgraded, and it takes no part in the shared base of paths or in the qualification matrix. The measures of native code and CPU fidelity do not apply to it; gameplay is
validated game by game (the owner played ten prototype executables, a play trial) and physical latency is not measured. ScummVM and Retro-Recomp's patch of it are under the GPL
(version 3 or later), kept apart from the MIT code and carried with a written offer of the source ([licenses/scummvm.md](../licenses/scummvm.md)); Windows is built and Linux is
witnessed on one small game.

**What moves.** Computed with `compilation_inputs.role_stamps` of the fourteen machines on the tree of `main` before this merge (`f03a713e`) and on this tree (first twelve
hexadecimal digits of each stamp, 6 November 2026):

| Machine | Game stamp (before, after) | Host stamp (before, after) | Build stamp |
| --- | --- | --- | --- |
| Master System | `49fe6e32e245`, `ffb447e12968` | `52732894c705`, `4c698ce40729` | same |
| Game Gear | `8c00b18cbb84`, `9f3d2cd547bb` | `12ddf0d7f71c`, `9e302b729213` | same |
| Game Boy | `84ee8993f728`, `1c847126de1d` | `cf765eccafd3`, `d03f39763f54` | same |
| NES | `70294cfa87ce`, `88240b6d2e3b` | `71877ffa5602`, `a91c8c6c0d28` | same |
| Mega Drive | `a51188bb861f`, `3c62c2e5c7a3` | `81f2da5cd72d`, `b45d74b5e78f` | same |
| Super Nintendo | `183e40e13480`, `0bc2b194ed99` | `86e398dab378`, `ebe78ef356a1` | same |
| Neo Geo | `dc211c9479da`, `328279cbfc1c` | `b7fe8c803579`, `098ae12034e1` | same |
| X68000 | `ad8e4bc0f227`, `d42bb1882a76` | `1ca7429d24bd`, `4cc410c21d5a` | same |
| CPS-1 | `da3f9a93f08f`, `2d6bdc5b1ca4` | `075e0ff74ad2`, `ff2e8295501f` | same |
| CPS-2 | `d0dfdf7fcd0a`, `b841f976989c` | `6d09623637fd`, `7f31bbdfb091` | same |
| PC Engine / TurboGrafx-16 | `61785d10f6b3`, `78f5641c38ec` | `e688aeb8d524`, `bdcc346995e1` | same |
| Game Boy Advance | `a8f3639ad2c9`, `05e06c23687a` | `f91cddfbe6b9`, `f94b7ff7c92f` | same |
| Amiga | `c7a44bc35458`, `a82d6ccb72ca` | `8e7c7e682d10`, `136af9f804ed` | same |
| Adventure (ScummVM) | new, `c7d5b2bf31be` | new, `4a96d24af08d` | new, `1b3f09984ccc` |

Five fixes made before publication move only the stamps of the machine they belong to: the Amiga's availability check (native files only, so a packaged
converter offers the profile), its decoder reading the working folder and resload_Abort said in words give the Amiga the game stamp `ff35e3b8af69`; the ScummVM patch that leaves no route to a modal window, and the folder scan that
refuses with a sentence when the build tools are missing instead of starting a build, give Adventure (ScummVM) the game stamp `be8047b230ac` and the build stamp
`97d9ad0da628` (the released tree). The CPS EEPROM writer's two flags and spin lock go through the Interlocked functions under Visual Studio
(the fallback toolchain compiles C11 atomics only with an experimental switch, so every CPS-1 and CPS-2 conversion failed
there; the portable clang and GCC keep `<stdatomic.h>` and the same code): the game stamps of the CPS-1 `b2ef983bc3fd` and the
CPS-2 `71a11548e45d`, which were moving in 1.7.0 already. On Linux a second Game Boy Advance player preparation no longer rewrites its three embedded resource files with equal bytes
(found by the Linux CI): the Game Boy Advance game stamp in the table above is the released one.

**The game stamp and the host stamp of the thirteen earlier machines move again** (`retrorecomp/batch.py` and `report_schema.py` are game inputs of every machine, and
`THIRD_PARTY_NOTICES.md` and the new licence pages are host inputs); no build stamp moves for them. This adds no conversion on top of 1.7.0: against `v1.6.9` every game stamp had already
moved (the index above). The ScummVM stamps are new.

**Quick states.** No key moves: no native file listed in a key changed, and the ScummVM exports have no F8/F9 state of ours (a game's saves are ScummVM's own, in `datas/`).
**Cartridge saves** of the other machines are kept.

**Not measured.** The speed of a ScummVM game, a Linux run of any engine family but the one witnessed, and the cost of the new test in `batch.py`.

## Capcom CPS-2 leaves the experimental status (1.7.0)

The CPS-2 (profile `cps2`, [CPS2.md](CPS2.md)) is a supported machine, the decision being the owner's ([QUALIFICATION.md](QUALIFICATION.md#owner-acceptance)). What moves,
computed with `compilation_inputs.role_stamps` on the commit the branch was cut from (27e30e03) and on the branch `spec/cps2-exit-170` (first 12 hexadecimal digits of each stamp):

| Console | Game stamp | Host stamp | Build stamp |
|---|---|---|---|
| sms | 3e16a0301d90 → 3e16a0301d90 (same) | 1b834d7b9fbc → 013be1c42081 (moves) | same |
| gg | 4f9d69e86e89 → 4f9d69e86e89 (same) | c9e0e360f031 → 69bcb747bee3 (moves) | same |
| gb | ff30f88ca9f1 → ff30f88ca9f1 (same) | 772d06158394 → d7f2d1b91dbd (moves) | same |
| nes | a3537f590fcf → a3537f590fcf (same) | 21b599f4ec81 → 09e18a69af7c (moves) | same |
| md | a0de8eae71a4 → a0de8eae71a4 (same) | 7bda64083b03 → 774f6daae149 (moves) | same |
| snes | ae2146874e49 → ae2146874e49 (same) | 2a4bc2c7b468 → 423b38546baf (moves) | same |
| ng | a3733e1113ff → a3733e1113ff (same) | 1f2e8a0e2450 → 76460953331d (moves) | same |
| cps1 | e6380523c2d1 → aa1a80f01e09 (moves) | 0f8432dcd5c5 → a01cacaa9528 (moves) | same |
| x68 | 6c7509bf49d2 → 6c7509bf49d2 (same) | 47212d53043d → 1d8e4c116284 (moves) | same |
| cps2 | 8d2c63c4b35a → 34899059c985 (moves) | 0f2bade664f6 → 14e9a20d9fe2 (moves) | same |
| pce | c8545bf9018e → c8545bf9018e (same) | 6ea8ea8ac8eb → 9f41cb76dbf1 (moves) | same |

- **Game stamps: only the CPS-1 and the CPS-2 move**; the other nine consoles keep theirs, because `path_profiles.py` is untouched (a CPS-2 path record has an empty layout, checked by
  `cps1_knowledge.validate_record`). **Host stamps: every console moves**, through `artwork.py` (the optional `cover_titles` capability); build stamps do not move.
- **The CPS-1 and the CPS-2 find their box art.** Their profiles name the libretro-thumbnails `MAME` repository, which files its images under MAME's description
  of each set, and the platform numbers of ScreenScraper (6 and 7, read on its system pages) and TheGamesDB (23, "Arcade"). The search uses the optional profile
  capability `cover_titles(path)`: the set's catalogue title, then its parent's, tried after the file's name and the title (a clone shows its parent's box; no list
  of games). For these machines, a repository that files one box under two spellings of the same name ("Street Fighter II - ..." and "Street Fighter II_ ...") no longer
  makes the choice ambiguous when downloading. Replayed over the reports of `Export`, before and after: no choice of another machine changes. `artwork.py` is a host module
  of every console, so every host stamp moves; the game stamps move only for the CPS-1 family. Existing exports get their icon on the next conversion.
- **The EEPROM of the CPS-1.5 and the CPS-2 is saved off the frame path.** A game changes its cells one after another at start and on a coin, and each change
  wrote the file at once, with a flush to disk that can wait a long while on a busy disk (a frame log of `ssf2` showed single frames of several seconds with the disk
  busy, against 36 ms at most without the write). A worker thread now writes the last contents after the EEPROM has been stable for about a second, and play
  ending writes it at once; a stop of the program within that second loses that last change. `native/cps1_persistence.c` is a host file of the CPS-1 family.
- **The CPS-2 game stamp moves**: its report now says `completed` (not `experimental`), its board tier is `supported`, it shares its paths and its
  profile, translations and notices changed. An export of the CPS-2 of 1.6.9 is rebuilt once on its next conversion, with the same code, pictures and sound.
- **The CPS-1 family's game stamp moves** (the CPS-1 and CPS-1.5 share the board model): `native/cps1_machine.c` now includes `native/cps1_cps2_board.inc`, `cps1_knowledge`
  takes the board as a keyword, `capcom_sets` reads a ROM that FBNeo stores twice over. The final A/B comparison of `1941` and `wof` against `main`
  (`tools/ab_conversion.py`): the generated steps, the board folder and every piece of evidence (CPU, RAM, picture and sound hashes, traces, states, the compressed copy)
  are identical; the files that differ are the changed native sources and the new include, `notices.txt` and the receipt, engine and record digests of the report.
- **Hot path of the CPS-1, as in 1.6.9**: nothing new here (the guards of 1.6.9 stay: a branch per bus access, `if (tile_priority)` per tile pixel); its frame cost is
  still to be measured with the comparison of frame costs of the release, on a quiet PC.
- **The CPS-2 shares its paths** like the CPS-1: its record is tied to its own engine identity (`cps2-m68k` and `cps2-z80` digests), points into the decrypted program, and
  holds no key and no ROM byte. None of the sets observes a path, so nothing is qualified.

## Exports of 1.6.7 in 1.6.8

1.6.8 is the release after 1.6.7 (published on 3 November 2026). This section is the index of its changes, one line per section
below, with the stamps that section says move. Each section computed its stamps for its own change alone; the totals are under the table.

| Change | Game stamps that move | Host and build stamps | Quick states |
| --- | --- | --- | --- |
| [Lead: the engine sources and SDL follow their pins in an older library](#lead-the-engine-sources-and-sdl-follow-their-pins-in-an-older-library-168) (with the review retouches at its end) | all nine consoles (`core.py`, `delivery_evidence.py`) | none | no key moves |
| [Game Boy: the state after the boot ROM, the serial clock phase and the sound unit](#game-boy-the-state-after-the-boot-rom-the-serial-clock-phase-and-the-sound-unit-168-gates-g10-and-g11) | Game Boy | none | no key (the Game Boy has none) |
| [Sharp X68000: the picture is converted only when the host reads it](#sharp-x68000-the-picture-is-converted-only-when-the-host-reads-it-168-frame-cost) | Sharp X68000 | none | **`RR_X68K_STATE_ABI` moves**: states of 1.6.7 refused |
| [Super Nintendo: the ROM address without a division, the 65816 stack pages, the SPC700 EI and DI, the evidence](#super-nintendo-the-rom-address-without-a-division-the-65816-stack-pages-the-spc700-ei-and-di-the-evidence-168) | Super Nintendo, Mega Drive, Neo Geo, CPS-1 (`console16.py`) | none | **the Super Nintendo and Mega Drive keys move** (the snesrecomp pin): states of 1.6.7 refused |
| [Mega Drive: the bus layout of the 68000 follows the independent vectors, and the Z80 hash of the report is portable](#mega-drive-the-bus-layout-of-the-68000-follows-the-independent-vectors-and-the-z80-hash-of-the-report-is-portable-168) | Mega Drive (and the X68000 and CPS-1, with no change of behaviour for them) | none | **the Mega Drive key moves**: states of 1.6.7 refused |
| Notices: the SameBoy palette tables of the Game Boy runtime, and the machines no longer called experimental in the notices | none | **host stamp of every console** (`THIRD_PARTY_NOTICES.md` and the licence pages are host inputs) | none |

Taken together (`compilation_inputs.role_stamps` of the nine consoles, the tree of `v1.6.7` against the tree of this release, computed on
4 November 2026): **the game stamp and the host stamp of every console move; no build stamp moves.** `LEGACY_GAME_STAMPS` stays empty, as in
every release since 1.6.4: the pins section changes `core.py`, which every game stamp hashes, and proving that a console's games come out
the same from it would take a real receipt per console. So every export of 1.6.7 is converted again from its paths when it is upgraded.

**Quick states.** The keys move for **the Mega Drive, the Super Nintendo and the X68000**: a quick state written by a 1.6.7 export is refused
cleanly there (no compatibility key is carried, [GAME_STATES.md](GAME_STATES.md)); nothing is lost but that state. The keys of the Neo Geo, the
CPS-1 and the NES do not move (the files they hash did not change), so their 1.6.7 quick states load. The Master System, the Game Gear and the
Game Boy have no key of this kind. **Cartridge saves** are kept on every console.

## Lead: the engine sources and SDL follow their pins in an older library (1.6.8)

Every conversion of every console first prepares the shared pieces in `.deps` (`core.dependencies()`): the Master System and
Game Gear engine sources (`.deps/smsggrecomp`, `core.ENGINE_REV`) and the SDL2 sources (`.deps/SDL`, `core.SDL_REV`). Up to
1.6.7, a checkout of another revision than the pin was refused ("Version inattendue de SDL"), and nothing converted. SDL moved
in 1.6.4 (2.32.8 to 2.32.10), so a library whose `.deps` a release up to 1.6.3 had made refused every conversion from 1.6.4 on
(found on 3 November 2026 by the CPS-1 release check, which reused an old workspace). Deleting `.deps/SDL` was the workaround.

From 1.6.8, `core.follow_pin` brings both checkouts to their pins through the shared `conversion_common.pinned_checkout`:

- a clean checkout of another revision fetches the pinned revision (no fetch when the checkout already has it), checks it out
  detached and updates its submodules; the window and the log say "Updating SDL to the pinned revision…". The SDL install is
  keyed by its revision (`platforms.sdl_install_key`) and the Z80 → C translator by its patched sources, so both rebuild by
  themselves, once;
- untracked files (the SDL build and install folders live inside `.deps/SDL`) are not edits;
- the conversion still stops, and the folder is left as it is, when tracked files carry edits (now also at the pinned
  revision, as the other consoles' engines already did), when the folder is not a git checkout, or when the revision cannot be
  fetched (offline). Each case has its own message in the log, in French and English; the window's steps are in the eight
  interface languages. A missing or empty folder is cloned, as before.

| Game stamps that move | Host and build stamps | Quick states |
| --- | --- | --- |
| all nine consoles (`retrorecomp.core` is a game input of every console; read with `compilation_inputs.role_stamps` before and after) | none (`i18n`, `gui_updates` and the locales are interface files) | no key moves (no native file changes) |

What a game does is unchanged: the pins themselves do not move, and a library already at the pins runs the same commands as
before plus the edit check. `tests/test_dependency_pins.py` covers each case with local repositories (no network).

*Review retouches (1.6.8, structure only).* The hash of a silent sound frame is now read in one place: `delivery_evidence.silent_hash`
(per number of samples, the Neo Geo and the CPS-1) and `silent_hashes` (every even count, the Super Nintendo), instead of three
readings of the same multiplies; the sets are the same as before (checked value for value). The DSP-1 and CX4 adaptations of the
Super Nintendo find their pinned text through `snes_chips.anchor`, so a moved text refuses the conversion with its message instead
of a Python error. Game stamps that move: every console (`delivery_evidence`), already moving with the pins above; what a game
does is unchanged.

*Linux keeps NRV packing (measured, 1.6.8).* The start-up cost of UPX `--lzma` on Linux was measured on 4 November 2026 with
`tools/startup_cost.py` (pack `--determinism`, then start `--runs 9`, one pinned core) on a Debian 13 PC (Intel Core i7-6600U, 2015),
four games converted unpacked from the 1.6.8 tree. LZMA makes the files 25 to 50 % smaller (Secret of Mana 6.8 MB against 13.7 MB) but
adds 100 to 150 ms to the start of the small games and **451 ms** to the largest (Kirby's Adventure and Secret of Mana: 0.62 to 0.67 s
against 0.16 to 0.21 s), beyond the margin of about 0.3 s that decided Windows in 1.6.7. So `packing.LINUX_METHOD` stays `'nrv'`; a faster
machine would likely show less, which is not measured. Both methods passed `upx -t` and packed to the same bytes twice. The tool now
copies with `shutil.copy`, which keeps the executable bit that UPX needs on Linux (it copied with `copyfile`). No stamp moves.

## Game Boy: the state after the boot ROM, the serial clock phase and the sound unit (1.6.8, gates G10 and G11)

The public test ROMs ([GAME_BOY.md](GAME_BOY.md#the-public-test-roms-of-blargg-and-mooneye-167-gates-g10-and-g11)) showed where the runtime differs from the console right after the boot ROM and in the sound unit.
Four corrections, all `replace_once` patches of the private generated project (a moved upstream marker refuses the conversion; `tests/test_gameboy_boot_apu.py`):

- **The sound unit starts where the boot ROM leaves it** (`gameboy_hardware.adapt_post_boot_apu`): channel 1 is on at volume 0 with the 64 of the length counter the boot ROM's note wrote, so `$FF26` reads
  `$F1` (it read `$F0`). The mix is unchanged: the channel is silent.
- **The LCD starts where the common console leaves it** (`gameboy_runtime.adapt_boot_ppu_phase`): the pinned reset has the LCD where the first revision of the console leaves it, at line 145; the common revision
  (DMG ABC) leaves it in vertical blank with LY already reading 0 (STAT `$85`), late in line 153. Mooneye's `boot_hwio` accepts a window of phases (it passes at the steps tried from 3,950 to 4,108 dots after the reset and fails
  at 3,900 and below and at 4,150 and above); the PPU is stepped by 4,096 dots after its reset in a DMG without boot ROM (line 153, dot 452, mode 1, LY reading 0; no vertical-blank edge is crossed). The exact dot within
  the window is not measured. Only the PPU is stepped, the divider keeps its value: the phase between DIV and the PPU is not tested.
- **A serial transfer with the internal clock ends on the phase of the divider** (`gameboy_runtime.adapt_serial_phase`): the first bit comes at the next falling edge of bit 8 of the divider, not 4,096 dots after the start.
- **Rules of the sound unit** (`gameboy_hardware.adapt_power_off`, `adapt_length_clock`, `adapt_sweep_calculation`): the power switch of `$FF26` keeps the wave RAM and the length counters, and the length part of
  NR11, NR21, NR31 and NR41 is writable while the unit is off; enabling a length in the first half of a length period clocks it once and a trigger of an empty counter loads one less; a sweep with a shift of 0 still
  calculates at every sweep clock (nothing is written back, an overflow turns the channel off); leaving negate mode after a calculation made in it turns channel 1 off. The negate flag lives in the unused `freq` field of
  channel 1, so the saved sound state keeps its size.

*Proof.* On the 152 test ROMs of blargg and Mooneye, 128 passed on the 1.6.7 tree and 144 pass now: `boot_hwio-dmgABCmgb` and `boot_sclk_align-dmgABCmgb` pass, and `dmg_sound` goes from 4 to 18 of 24
(both versions of each test). Native code and interpreter stay equal step by step on every test but `oam_bug` `7-timing_effect` (see [KNOWN_FAILURES.md](KNOWN_FAILURES.md)). Six `dmg_sound` tests (the wave
channel read, trigger and write while it plays) still fail.

*Hot path: not touched.* The generated code and the per-sample mix are unchanged. The serial rule runs when a transfer starts, the PPU rule once at reset, the sound rules on writes to the
power switch, NR10, NRx1 and NRx4 and on the 128 Hz sweep clock. Channel 1 is enabled from the reset, so its timer and its 64 Hz envelope step from frame 0 (a contribution of 0 at volume 0). No timing was taken.

| Game stamps that move | Host and build stamps | Quick states |
| --- | --- | --- |
| Game Boy only (`retrorecomp.gameboy_runtime` and `retrorecomp.gameboy_hardware` are inputs of its `game` stamp; read with `compilation_inputs.role_stamps` against the base of the branch: the other eight consoles do not move) | none | no key moves (the saved sound state keeps its size) |

*What it changes in practice, measured on twelve games.* The twelve games of the 1.6.7 campaign were converted on the 1.6.8 tree and replayed with the three runtimes (1.6.7, the new sound unit alone, everything) on
their four routes (boot, two play runs and the pseudo-random route of 18,000 frames), comparing the picture, sound, work RAM and program counter of every frame (`tools/gameboy_cross_os.py`):

- **The sound rules alone change no picture, no work RAM and no program counter on any frame of the 48 routes**; the sound hash of the frame differs on ten of the twelve games (not on Contra or Pokémon Yellow),
  probably from the phase of channel 1, which now runs from the boot ROM on, and where a length edge case occurs. This was not heard against a console.
- **A behaviour change, decided on 4 November 2026: the LCD starts where the common console leaves it (the DMG ABC, LY reading 0 in vertical blank, confirmed by `boot_hwio`).** The game starts 4,096 dots (nine lines) later in the frame. A game of 1.6.7 that is converted
  again **no longer replays frame for frame what it did**: the program counter and the work RAM at the end of a frame differ from the first frames on most games (table below), and what depends on the timing follows
  (Tetris deals other pieces on its long route; animations and random numbers elsewhere). All twelve stay alive: the number of different pictures per route stays within a few percent except Metroid II's boot route and
  the long routes of Final Fantasy Legend II, Pokémon Red and Tetris, which show more because the game reaches other screens. Same policy as the corrections found by the independent vectors.
- One figure to read with care: the count of frames with a non-zero sample falls on some games (Metroid II 17,645 to 14,304 frames of 18,000). It counts a constant offset of the output filter left at silence
  (142 on each side of 32,768 on Metroid II in 1.6.7), which the new start does not keep; the mixed channels are silent in both.

| Game | Routes (of 4) with the sound hash of 1.6.7, sound rules alone | Routes (of 4) equal to 1.6.7 in picture / sound / work RAM / program counter, everything | Frames with another picture (of 21,600) |
|---|---|---|---|
| Contra: The Alien Wars | 4 | 0 / 0 / 0 / 0 | 768 |
| Exodus | 3 | 4 / 0 / 0 / 0 | 0 |
| Final Fantasy Legend II | 0 | 0 / 0 / 0 / 0 | 20,448 |
| Link's Awakening | 0 | 0 / 0 / 0 / 0 | 2,373 |
| Mega Man V | 3 | 4 / 0 / 4 / 0 | 0 |
| Metroid II | 0 | 3 / 0 / 2 / 0 | 166 |
| Pokémon Red | 0 | 0 / 0 / 0 / 0 | 4,334 |
| Pokémon Yellow | 4 | 0 / 0 / 0 / 0 | 1,257 |
| Super Mario Land | 1 | 0 / 0 / 0 / 0 | 453 |
| Tetris | 0 | 3 / 0 / 3 / 0 | 17,021 |
| The Ren & Stimpy Show: Veediots! | 2 | 4 / 0 / 4 / 4 | 0 |
| Wario Land II | 0 | 4 / 0 / 4 / 4 | 0 |

The routes are the boot, the two play runs and the pseudo-random route of 18,000 frames of each conversion (quick level, an empty library); with the sound rules alone the picture, the work RAM and the program counter are equal to 1.6.7 on every route of every game. Final Fantasy Legend II shows another picture on nearly every frame (its title and menus animate on the timing); this was not looked at screen by screen.

## Sharp X68000: the picture is converted only when the host reads it (1.6.8, frame cost)

*Frame cost (1.6.8 item).* R-Type measured 1.05 against 1.6.6 on 3 November 2026 (+0.028 ms a frame, 0.591 to 0.619, quiet PC, start-up taken out
of both). Found by reading and counting, nothing timed. R-Type draws 256 x 256 pixels a frame (read from the report of a headless run: 65,536 pixels).
**The cause is the colour correction of 1.6.7** ([the intensity bit](UPGRADES_HISTORY.md#sharp-x68000-the-intensity-bit-of-the-palette-lifts-red-green-and-blue-167)),
in this way: until 1.6.6 the core handed its RGB565 buffer to the host as it was, and the conversion to the window's pixels lived in the window kit
(`player_picture`, only reached when a window is open). 1.6.7 moved the work into the core: every frame, `convert_frame` reads the machine's 16-bit
colour word of each pixel, looks it up in a 65,536-entry table and writes a 32-bit pixel, whatever the host does with the picture. A headless run
(the benchmark, a user's `--headless`) reads nothing, so it paid 65,536 lookups, loads and stores a frame
for no one: about one cycle a pixel is 22 microseconds on a 3 GHz core, which is the size of the +28 microseconds measured, the rest being the 256 KB
table and the 256 KB of 32-bit pixels competing for the cache with the emulation. The other candidates were read and eliminated by count: the
Musashi corrections touch only the overflow path of `DIVU` and `DIVS`, `CHK`, `LINK A7` and the opcodes `F620`-`F627`; the shared state rules touch
`LINK`, `UNLK` and `NEGX`, a local variable and one test that fold at compile time; the libretro comparison base leaves the build files without a
change of compile flag (`-O2`, no profile-guided build for this machine, so no profile to go stale); the host kit changed only in the Super Nintendo adapter.

**The fix.** The core asks libretro's "video enabled" bit (`RETRO_ENVIRONMENT_GET_AUDIO_VIDEO_ENABLE`) at each frame and converts only when it is set.
The reference host, which is also the host of a window, answers from what it does with the picture: a trace or a report hashes it, a capture or a window
keeps it; a headless run with none of these does not read it, and the core hands it the last converted picture again. The machine, its state,
its sound and every hash are untouched. A host that does not answer is treated as wanting the picture. A saved state redraws through the full
conversion whatever the answer (`rr_x68k_framebuffer`). In a window nothing changes for the player: the conversion still runs each frame, and it is
expected not to be more expensive than in 1.6.6 (a table lookup in the core and a plain copy in the kit, against three multiplications and divisions per pixel in
the kit), not timed. In a window in fast forward the core converts every frame while the kit reads one in eight: that is outside the measured path, left as it is.

**Proof.** (1) Counted, not timed: a build of this tree with a counter in `present_frame` (not kept) ran R-Type for 900 frames. Headless with no report,
as the benchmark runs it: 0 frames converted, 899 skipped. Headless with `--report`: 899 frames converted (138,870,784 pixels, the start-up pictures
being larger than the 256 x 256 of the game), 0 skipped. (2) The machine is untouched: both runs saved a state at frame 800 (`--state-slot`, `--state-save-at`)
and the two files are the same, 19,410,352 bytes, same SHA-256. (3) The fingerprints are the same: the conversion hashes the picture of every route, so its runs convert every
frame: a conversion of R-Type on this tree has the CPU, RAM, picture and sound hashes of the same conversion before the change, on the three routes
(R-Type and Bubble Bobble, 253 values of the checks compared, 0 differ in hashes, counters and interpreted opcodes; the one difference is the report field `packed.method`, added to main after the baseline was converted). (4) `tests/test_x68000_colour.py` fixes the contract in the sources.
The speed itself is not timed here: the measurement on a quiet PC is the lead's.

**What moves.** The Sharp X68000 game stamp (`libretro_api.c` and `reference_host.c` are game inputs): an export of 1.6.7 stays as it is, and a 1.6.8 export is
a full reconversion. **The state compatibility key `RR_X68K_STATE_ABI` moves too** (it hashes `reference_host.c`): a quick state written by a 1.6.7 export is
refused cleanly by a 1.6.8 game (no compatibility key, no crash, no overwrite); the layout of the state is the same. Host and build stamps and the other
consoles do not move.

## Super Nintendo: the ROM address without a division, the 65816 stack pages, the SPC700 EI and DI, the evidence (1.6.8)

*Frame cost (1.6.8 item 1).* Secret of Mana measured 1.04 against 1.6.6 on 3 November 2026 (+0.23 ms a frame, quiet PC, start-up taken
out). Found by reading and counting, nothing timed: the training run of the conversion (1,800 frames, `hardware-profile.profdata`)
counts, per frame, 97,126 calls of `cart_getRomPtr`, 52,020 of `cpu_read8` and 41,870 evaluations of `rr_snes_cart_ram_offset`. The
pinned `cart_getRomPtr` ended every ROM byte read (the CPU, the instruction fetch, a DMA) in `off % cart->romSize`, a 32-bit division,
inlined in `cpu_read8`, `bridge_bus_read`, `rr_snes_cpu_read_begin` and the interpreter's step. What 1.6.7 added on that path is small by the
same count: the image-size comparison of the ExHiROM board in the HiROM read (two instructions), the S-DD1 board test in
`rr_snes_cart_ram_offset`, the emulation-flag tests of the branches and of the indexed direct-page addressing; the hot functions grew by
13 to 38 instructions (`interp816_runOpcode` 439 to 477, `cpu_read8` 373 to 406, `cart_getRomPtr` 186 to 201) and the step's frame by 16 bytes. That is
about half a million instructions a frame at most, under 1 %: it does not explain 4 % alone, and a code layout that moved is a reasonable
remainder. The change: the remainder is the mask when the size is a power of two (every image the loader pads), and is the division for any other
size, so the address is the same in every case (`snes_cart.adapt_cart`, `native/snes_cart_checks.c` compares the pointers of 7 sizes, 2 of them not
powers of two, over every bank); the Super FX board's code lookup, which had its own remainder, divides by the constant length that
`rr_snes_native_bind` has already checked. *Hot path: touched, expected faster, not timed* (the lead asks Arthur for the quiet-PC slot).
Proof: A/B of the 1.6.7 tree and this one, from an empty library, Secret of Mana: the 19 hash fields of each of the six probe files
(native, packed copy, reference; demo and play) are equal; what differs is `cart.c`, the compiler's profile data and the analysis file.

*Stack pages of the 65816 in emulation mode (gate G10).* `PEA`, `PEI`, `PER`, `PHD`, `PLD`, `JSL`, `RTL` and `JSR (a,x)` step the 16-bit
stack pointer without wrapping and set its high byte back to 1 only at the end; the 6502 instructions keep wrapping after every byte
(`snes_codegen.correct_stack_pages`, fail-closed on the pinned text; native mode is the same text as before, and `JSL` is cheaper: no flag test
after each byte). The vectors: 0 semantic differences in the 130,448 cases of the larger run (it was 11) and in the 32,768 of the usual one.
A game that stays in emulation mode and keeps its stack at the edge of page 1 is the only one concerned.
`PEA` also loses a hack of the pinned engine, which zeroed Y when the operand was `$C2AE` (no counterpart on the chip; Super Metroid holds 38 sites of those
bytes and is the likely target). Six cartridges that hold the bytes convert with identical hashes before and after on the standard routes (Super Metroid, Axelay,
Breath of Fire, Terranigma, Samurai Shodown, Battle Clash); a game whose later routes run that exact `PEA` could still move, and would then be showing what the chip does.

*SPC700 `EI` and `DI`* take 3 cycles (the pinned table said 2; the chip's timing and the vectors agree, `snes_spc.interrupt_flag_cycles`).
This one changes what a game does where its sound driver runs these instructions: **Chrono Trigger's driver does** (the observed
positions hold four of them), and its conversion, A/B against the tree before, keeps the same pictures in the demo but a different count of APU
cycles (+11), a different sound hash and a main CPU that is 390 cycles shorter over the 24,000 frames; the other games of the panel that do not
use them are identical. It is its own commit (`878ec77`): it can be left out of a release that wants every hash identical.

*Audible frames.* A frame is audible when its sound hash is not the hash of silence for its number of samples (`snes_evidence.silent_blocks`,
the method of the Neo Geo and the CPS-1; the host does not change). Every final check now carries `liveness.audible_frames` and
`last_audible_frame` instead of `None` (gate G8).

*Report.* `qualification_scope.universal_zero_fallback_claim: false` and `native_validation.independent_cpu_oracle: false` (the conversion's
reference is the engine's own interpreter), read back by the common `honesty` block (gate G15).

*Engine pin* (`snesrecomp` from `a00df26` to `fb8cf15`, the reasons and the four reworked adapters in [UPSTREAMS.md](UPSTREAMS.md#super-nintendo-the-pin-of-168)).
What a game does is unchanged on the panel: the tree of this release at the old pin and at the new one give the same 21 hash fields (picture, sequence,
CPU, RAM, video, colour and sprite memory, sound RAM, PCM, program counter, cycles, device state) in each of the six probe files (native, compressed copy,
reference; demo and play) on eight games, one per board: Secret of Mana (HiROM), Super Mario World (LoROM), Lock On (DSP-1 on HiROM), Street Fighter Alpha 2
(S-DD1), Star Fox (Super FX), Mega Man X3 (CX4), Kirby Super Star (SA-1) and Dragon Quest III (ExHiROM). The twelve games of the panel convert at the new
pin with the native run equal to the reference, the compressed copy equal to it, and 0 interpreted opcodes of the 65816 and of the SPC700. The Linux build (GCC)
of the new engine builds and runs; its per-frame traces equal the Windows ones on four games and twelve routes (Secret of Mana, Super Mario World, Star Fox and
Kirby Super Star: the attract and play routes of 3,600 frames and one pseudo-random route of 18,000 frames of each, `tools/snes_cross_os.py`). Two adaptations are
beyond the anchors: the engine counts the native-mode `BRK` cycle itself (our correction of 1.6.3 is retired, the adapter requires the engine's line), and
its UTF-8 manifest resource is left out of the Windows link (the game carries the converter's manifest; two do not link). Not enabled: what the range offers
behind a build selection (fused ROM reads, fused DSP mixing, APU spans, HD Mode 7).

*Stamps* (`compilation_inputs.role_stamps`, the tree of 1.6.7 against this one):

| Game stamps that move | Host and build stamps | Quick states |
| --- | --- | --- |
| the Super Nintendo, the Mega Drive, the Neo Geo and the CPS-1 (`console16.py` is a game input of the four: it holds the pin and the report block); the other five do not (the game stamps of all nine already move with the pins of the lead's section above) | none | the Super Nintendo's `RR16_STATE_ABI` moves (it hashes the pinned revisions and the fingerprints of the `snes_*` modules); so does the Mega Drive's, because `console16_state.write_config` hashes the whole `revisions` dictionary, which holds the snesrecomp pin (moot for the release, which moves it anyway): a quick state of 1.6.7 is refused cleanly; a battery save is not concerned |

*Tools that change no export.* `tools/snes_cross_os.py` (the per-frame witness between two systems, gate G13), `tools/snes_route_captures.py`
(the last picture of each route, gate G9), `tools/snes_game_saves_check.py` (the battery save of a delivered game across three processes,
gate G7). `tools/snes_cpu_vector_selftest.py` takes the larger sample with `--samples 256`.

## Mega Drive: the bus layout of the 68000 follows the independent vectors, and the Z80 hash of the report is portable (1.6.8)

The 452 vectors of `tests/fixtures/m68k-groups` that still differed from the Mega Drive after 1.6.7 (the total of clocks was right, the
layout of the bus transactions was not, [CPU_68000.md](CPU_68000.md#what-the-groups-fixture-found-since-166)) are corrected: **2,873 of 2,895
vectors now agree on every check, on the native steps and on the reference path; the 22 left are `ABCD`, `SBCD` and `NBCD` on operands that
are not decimal digits, which the manual leaves undefined.** The causes, by instruction:

| Cause | Vectors | Where it is corrected |
|---|---|---|
| a long read-modify-write to memory (`ADD`, `SUB`, `AND`, `OR`, `EOR`, `NEG`, `NEGX`, `NOT`, `CLR`) writes its low word first | 111 | `retrorecomp/megadrive_bus_rules.py` (the executor's `mem_write`) |
| `ADDX.L`, `SUBX.L` on two predecrement operands: each long is read from its low word; the result is written low word, next prefetch, high word | 13 | the same module (`mem_write_split`) and `rr_md_prefetch_hold`/`release` in `native/md_prefetch.inc` |
| the two internal clocks of the predecrement forms of `ABCD`, `SBCD`, `ADDX`, `SUBX` come before the first read | 98 (the 13 above included) | `native/md_prefetch.inc` (live preparation) and `megadrive_codegen.prefetch_plan` (static plan) |
| a byte or word immediate (or a bit number) with a memory destination: the internal clocks come after the word that follows the immediate | 17 | the same two places, plan flag `RR_PF_IDLE_AFTER_FIRST` |
| `ANDI`, `ORI`, `EORI`, `MOVE` to the condition code register read the second word of the queue again after 8 (4 for `MOVE`) internal clocks, then prefetch as usual | 147 | `rr_pf_finish` |
| `LINK` and `MOVEP` fetch their last word after their writes, not before | 79 | `RR_PF_BEFORE_WRITE` is off for them, in the live preparation and in the plan |

**Not proved:** the long immediate forms with a memory destination that needs an address calculation (`ADDI.L`, `SUBI.L`, `ANDI.L`, `ORI.L`, `EORI.L` and `CMPI.B`, `.W`, `.L` on `-(An)` or `(d8,An,Xn)`) have no vector in the
fixture; their layout stays the pinned model's. The corrections change where the transactions of an instruction fall, not the total of its
clocks, so a frame-timed effect can still shift by the clocks between two accesses (VDP, Z80 and I/O ports see the order and the instant of
each access).

**Z80 hash of the report.** `z80_cpu_hash` (the Mega Drive's report and trace field) hashed the bytes of the Z80 structure: that structure holds a
`unsigned long` (32 bits on Windows, 64 on Linux), bit fields and padding, so the same Z80 gave a different value on the two systems. It is now
taken field by field (`z80_state_hash`, `native/md_backend.c`: registers, flags, interrupt state and the low 32 bits of the cycle count). What reads
it: `retrorecomp/console16.py` (`MD_AUDIO_FIELDS`: copied into each route's `final_checks` row and compared between the native run and the
reference run of the same conversion) and `tools/state_checks.py` (`GUEST_FIELDS`: compared between a run and the run resumed from a quick state).
Both compare two values taken by the same executable, so they are unaffected; no golden, no shared path and no knowledge record holds it. **A report of
1.6.7 and a report of 1.6.8 are no longer comparable on this one field (on Windows too: the value of the same state is different), and the
tool that compares reports across systems (`tools/megadrive_cross_os.py`) must be given two reports of 1.6.8 or later.** Elsewhere: the Neo Geo and
the CPS-1 do not use this structure for their hash (`rr_ng_z80_state_hash` and `cps1_cpu_hash` read registers one at a time; the CPS-1 writes
its Z80 field by field in its states); the engine's machine snapshot, which the Mega Drive quick states use, still writes the Z80 structure as it is,
and is not changed (a state is not claimed portable between systems; changing its layout would need a compat key).

**What moves.** The Mega Drive game stamp (the generated steps and the runtime change). `native/md_prefetch.inc` and `megadrive_codegen.py` are
inputs of the X68000 stamp (`native/md_prefetch.inc`) and of the X68000 and CPS-1 stamps (`megadrive_codegen.py`, `shares:megadrive_codegen`): their
**game stamps move too, with no change of behaviour**: they take only the arithmetic part of `md_prefetch.inc` and apply none of the Mega Drive's rules; the replays of the vectors give the same figures as before (X68000: 2,873 native and
2,889 Musashi of 2,895 on `m68k-groups`, 2,171 of 2,171 on `md-prefetch`; CPS-1: the same, 864 of 864 on `md-exceptions`, 834 of 834 on
`m68k-shifts`). The Neo Geo stamp **does not move**: the new rules are in a module of their own, `megadrive_bus_rules.py`, because
`megadrive_rules.py` is an input of the Neo Geo stamp (it reads the state rules) and is left as it was. Host and build stamps of every console:
unchanged (checked on the stamp baseline, `tools/std_baseline.py`, before and after). **The quick-state key of the Mega Drive moves**: `RR16_STATE_ABI` hashes the native files the console owns
(`console16_state.write_config` through `compilation_inputs.state_native_files`), and `md_backend.c`, `md_prefetch.inc`, `md_native_steps.h` and
`md_prefetch.h` changed (digest `366b24f1…` on `main`, `5bf4260b…` here). The Mega Drive quick states written by a 1.6.7 game are therefore
**refused cleanly by a 1.6.8 game** (the N-1 rule of this page: no compat key, no crash, no overwrite); cartridge saves are not affected. The state
layout itself is not touched. The keys of the Neo Geo, the CPS-1 and the Super Nintendo do not move (same digests; the X68000 does not read that
digest). **CPS-1 path identities:** `retrorecomp/cps1_knowledge.py` lists `native/md_prefetch.inc` in its `NATIVE_INPUTS`, so the identities of the
`cps1-m68k` and `cps1-z80` paths move with this change; the behaviour is unchanged (the CPS-1 and the Neo Geo cut only the multiply and divide part
out of that file, which this change does not touch), and whether to raise `GENERATOR_REVISION` is the CPS-1 specialist's call. New files and their roles: `retrorecomp/megadrive_bus_rules.py` (game, owner Mega Drive), the new tools
`tools/megadrive_mame_compare.py` and `tools/megadrive_cross_os.py` (no stamp), all in `PUBLIC_FILES`.

**Cost.** On the hot path of the translated steps, small and **not measured**: the long read-modify-write sets and clears one flag around its write
and takes one branch in `mem_write`; the preparation of an instruction tests one more plan flag; the end of every instruction with a pending
prefetch switches on four mnemonics (`rr_pf_refetch_idle`). The lead measures the cost per frame at the release, on a quiet PC.

**Checked.**

- *Vectors:* `megadrive_groups_selftest` 2,873 of 2,895 (the 22 listed, same on both paths); `megadrive_prefetch_selftest` 2,171 of 2,171 (with the 82
  authored cases), on `m68k-shifts` 834 of 834; `megadrive_prefetch_plan_selftest` (live preparation against static plan) passed;
  `megadrive_exception_selftest` 864 of 864; `megadrive_cycles_selftest`, `megadrive_native_selftest`, `megadrive_timing_selftest` passed.
- *Campaign of 11 games* (the 1.6.7 list, `batch --system md`, one conversion at a time, quick check from the base), compared with the 1.6.7 tree:
  all `supported`; the hashes of the last frame, of the sequence of frames and of the CPU/prefetch state are **identical on 21 of 22 routes**.
  The exception is the play route of Shinobi III (PAL): the two runs equal each other up to frame 1,096, then at the end of frame 1,097 the 68000 of the new
  tree stands five instructions further (PC `$1924` against `$1912`, Z flag different), the picture hash of that frame is still equal, and the sound and
  the later pictures differ. Both addresses are in the same straight-line routine of the ROM (it reads script bytes with `(A5)+` and writes the fields of
  an object), so neither run is polling anything there. The cause was traced with every 68000 bus access and every instruction retirement of frame 1,097
  logged on both trees (kept builds with a log added in their private copy of the glue, rebuilt and run with `--frames 1200 --play`; nothing of it is in the
  repository): (1) the 68000 and the Z80 meet at the scheduler's rendezvous, a budget of a few clocks set by the Z80's timeline; the old tree yields at the
  access to `$14D4` at clock 92 and the Z80's last instruction overshoots by 5 clocks, the new tree yields elsewhere (clocks 88, 115, 123, 127), because the
  corrected layout moved the 68000's accesses by a few clocks, so the same instructions fall on the other side of a rendezvous; (2) from the fifth
  instruction of the frame the two timelines differ by 5 to 13 clocks (the new tree earlier by 13 at `$0520`); (3) the vertical-blank interrupt, asserted at the
  same absolute clock, is accepted at the next instruction boundary: the old tree takes it after the instruction at `$0520` (vector read of `$78` at clock
  109,578), the new tree runs the loop `$0512`-`$0522` once more and takes it 5 clocks later, so the frame ends five instructions apart. It is the
  arbitration approximation between the two processors that already made BUSACK dating a limit (the rendezvous is not the hardware's cycle-exact bus
  sharing), not a poll of the VDP, the horizontal-vertical counter or the Z80 bus request. The interpreted counts of this campaign are **not**
  comparable with 1.6.7's: the 1.6.8 tree started with an empty private library, so the quick check had no learned variants of RAM code (OutRun
  171,603 and 126,569 interpreted instructions, Contra play 52,785, Sonic 2's Z80 8,604 and 8,346, Sonic 3 two); OutRun converted again with a
  standard scan and no shared base reaches 0 interpreted in its second pass (2.9 and 3.0 million in the first), as any discovery does.
- *Cross-OS witness (gate G13)*, three games (Sonic The Hedgehog 2, NBA Jam - Tournament Edition, Streets of Rage 2, all USA) converted with the
  same tree on Windows and on a Debian 13 PC, standard scan, no shared base, empty library: the demo and play routes of 3,600 frames of each, **6 of 6
  routes identical** on every field of `final_checks` (picture, frame sequence, CPU/prefetch, VDP, RAM, Z80, YM, counters of native and interpreted
  68000 and Z80 instructions, bus and Z80 timing misses). A first round showed `z80_cpu_hash` different on all six: the cause above. Not covered: the
  other cartridges of the panel, long and authored routes, interactive play on Linux.
- *MAME 0.289, pictures (gate G11):* see [QUALIFICATION.md](QUALIFICATION.md#mega-drive-evidence-behind-its-column-4-november-2026).

## Host or game: the classification

Every input that shapes an export is fingerprinted (`retrorecomp/compilation_inputs.py`).
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
| Sound output after the emulated mixer | `audio_filter.h`, `audio_cushion.h`, `audio_output.inc`, `hostkit/shell/rrhk_ring.c`, `md_audio_loop.inc`, `md_audio_resample.inc`, `megadrive_audio.py` |
| Artwork, metadata, publishing | `artwork.py`, `cover_*.py`, `metadata.py`, `languages.py`, `publishing.py`, `windows.py`, `notices.py`, the `licenses/*.md` a machine's profile declares, application icons |
| Checks of the above | `game_options_checks.c`, `language_checks.c`, `xbr_checks.c`, `display_settings_checks.c`, `icon_checks.c`, `audio_checks.c`, `nes_audio_checks.c` |

Each machine family has one shell for its window, menus and input:

| Machine | Shell (host) | Entry used by discovery and validation (game) |
| --- | --- | --- |
| Master System, Game Gear | the host kit, staged beside the common runtime: the shell and `hostkit/adapters/rrhk_sms.c` (with `audio_output.inc`) | `launcher.c` and the Z80 runtime |
| Game Boy | the host kit, staged in the project's runtime: the shell, `hostkit/adapters/rrhk_gb.inc` (included by the patched `platform_sdl.cpp`) and `gameboy_host.py` | `game_main.c`, `gameboy_runtime.py` |
| Mega Drive, SNES, Neo Geo, CPS-1, NES | the host kit: `native/hostkit/shell/rrhk_*.c` (shared) and `native/hostkit/adapters/rrhk_<machine>.c`, copied by `hostkit.py` | `console16_main.c`, `neogeo_main.c`, `cps1_main.c`, machine adapters; for the NES, the runner adapted by `nes_runtime.py` |
| Sharp X68000 | the host kit, compiled from the tree: the shell and `hostkit/adapters/rrhk_x68k.inc`, included by the frontend | `x68000_reference/reference_host.c` (frame loop, reports, states, disks) and the SDK |
| MSX and MSX2 (experimental) | the host kit, compiled from the tree: the shell and `hostkit/adapters/rrhk_msx.inc`, included by the player (`native/msx_machine/msx_player.c`) | `native/msx_machine/msx_native_main.c` (frame loop, reports) and `msx_reference_main.c` (the reference interpreter's host) |

Files that are used both by the shell and by headless checks stay game-side:
`platform_io.c/.h` (quick-state files), `embedded_resources.h`, the
machine adapters `cps1_host.c` and `neogeo_host.c` (input and state
mapping), and every CPU, video, sound-chip, timing, learning and validation
file. Since 1.2.8 the Game Boy shell patches live in `gameboy_host.py`,
separate from the runtime patches in `gameboy_runtime.py`; the guest-side
JOYP refresh hook moved from `gameboy_timing.py` to
`gameboy_runtime.adapt_input_refresh_hook`. The generated Game Boy project is
byte-identical before and after that split. (Since 1.6.3 `gameboy_timing.py` is gone: the Game Boy shell is the host kit and its
adapter.)

The modules that read the paths (`knowledge.py`, `path_profiles.py`, `feedback.py`,
`neogeo_knowledge.py`, `snes_knowledge.py`) are game-side, `knowledge.py`,
`path_profiles.py` and `feedback.py` for every console: they decide which code a
game starts from. Since 1.6.0 `knowledge.py` delegates to `path_profiles.py`, so
that module is in every console's game stamp (it was an interface module while
only the exchange and the shared base used it). The modules that only share
discoveries (`knowledge_exchange.py`, `knowledge_build.py`, `online.py`) stay
interface modules. Neo Geo receipts of releases before 1.6.0 hashed the whole Neo Geo bank in their knowledge part; 1.6.0 hashes the
game's own record, which is one more reason none of them is listed.
A Neo Geo receipt is written with the game's key as the conversion found it. The paths' own stamp (`knowledge_stamp`) hashes the game's
record, not the bank: see [the paths and the stamps](COMPILATION_LIBRARY.md#stage-b3-the-conversions-follow-the-module-27-october-2026).

## Reproducible stamps

A stamp hashes a list, never what is on disk (docs/STANDARDS.md rule 5). The
list is `INPUTS` in `retrorecomp/stamp_inputs.py`: every converter module and
every file that can enter a stamp, grouped by the consoles that own it, plus
`NOT_INPUTS` for the tracked files that are deliberately out (interface
pictures, locales, credits, the knowledge snapshot, the UPX tools). A file on
disk that is not listed changes no stamp; a listed file that is missing is an
error; `tests/test_stamp_inputs.py` fails when a tracked file is neither
listed nor declared out, or when a listed file is not bundled in the
executable. Text is hashed with CRLF turned into LF (and `.gitattributes`
pins LF for these types), so a Windows working tree, an archive of a tag and
Linux give the same stamps; the two catalogues that are checksummed byte for
byte are hashed as they are. The save-state key of the Mega Drive and Super
Nintendo and the Master System / Game Gear compiler signature read the same
list (the native files their console owns), not the folder.

`compilation_inputs.py` (the algorithm) and `stamp_inputs.py` (the data) are
interface modules: no stamp hashes them, so registering an interface module,
adding a file to one console's list or editing `LEGACY_GAME_STAMPS` moves no
game stamp. A change of the algorithm itself bumps `STAMP_LABEL`, which a test
pins on a synthetic input.

## Adding or changing a file

- Every new file under `native/`, `assets/`, `profiles/` or `licenses/`, and
  every new converter module, is added to `INPUTS` with its owners (or to
  `NOT_INPUTS` / `INTERFACE_MODULES` when no game depends on it). The
  completeness test names what is missing. Its role (host, build or game) comes
  from the tables below. A licence page a game embeds is not listed there: the machine's profile declares it
  (`notice_files`) and that makes it a host input of that machine only.
- A new menu, text, filter or shell file: add it to `HOST_NATIVE` or
  `HOST_MODULES`, and to the tables above, only if no headless discovery or
  validation run uses it.
- A Python patch module must not mix shell and machine patches; split it as
  `gameboy_host.py` / `gameboy_runtime.py` do.
- `tests/test_compilation_inputs.py` checks the classification of every
  machine's shell and entry.
