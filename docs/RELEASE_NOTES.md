# RetroRecomp v0.24.0 — broader native coverage and smarter cover searches

- Game Boy uses more efficient generated C and reuses byte-identical build
  files, preserving native discovery, optimization and CPU validation. Bank
  boundaries, shared native entry selection and additional guarded RAM helpers
  improve previously failing conversions. Fourteen targeted cartridges now
  pass their checks; thirteen have no fallback on the tested paths.
- Mega Drive learns native instructions at the end of work RAM and tests
  early-start gameplay paths. The latest 20-cartridge batch passes all four
  scenarios per cartridge without main or sound CPU fallback, including
  internal CPU/memory/video/PCM comparisons.
- Cartridge identification accepts additional valid Mega Drive region headers
  and Japanese Super Nintendo header titles, without guessing another game's
  profile or accepting unsupported cartridge hardware.
- Shared cover searches handle articles, punctuation, abbreviations, Roman
  numerals, subtitles and small typos across all six consoles. Sequels, years
  and special editions stay distinct; ambiguous results are not guessed.
- The converter includes 34 reviewed front-cover references and verified,
  ROM-free compilation hints for 954 exact cartridge revisions. The compressed
  knowledge snapshot occupies about 7.4 MiB. No cover images are bundled.
- Game Boy's unused debug layout no longer writes an `imgui.ini` beside games.
  Existing game settings remain in `datas`, as on the other profiles.

**Mega Drive and Super Nintendo remain experimental.** Standard eligible
cartridges are analyzed automatically, with no fixed game allowlist. Broader
native coverage does not certify unusual cartridge hardware, all display/audio
modes or complete gameplay. See [16-bit support and remaining work](CONSOLES_16BIT.md).
Native coverage, CPU agreement, hardware fidelity, gameplay and physical latency
remain separate measures. Game Boy build timings distinguish cold builds from
repeat conversions; the validation scope has not been reduced.

Validation passes 282 ROM-free Python tests, 8,064 authored Mega Drive
instruction/state comparisons, 47,104 Game Boy bank-boundary comparisons,
65,536 native-entry selector checks and 28,277 guarded RAM-helper checks.

Download the single Windows x64 **Retro-Recomp.exe**, or use **Check for updates**.
Updates preserve games, settings, local compilation knowledge and downloaded
covers. Regenerate affected games to receive compiler/runtime changes. No ROMs,
downloaded artwork, generated games or private settings are included.

---

# RetroRecomp v0.23.0 — a new look and stronger conversion support

- New charcoal-and-gold identity, cartridge logo, outlined console artwork
  and refreshed English/French interface. The ROM list has a clear empty state,
  and the log panel includes its own scrollbar.
- Parallel batches keep available workers busy when duplicate inputs are waiting.
- Cartridge headers improve Master System/Game Gear detection, including
  renamed files and ZIP archives.
- Eligible Mega Drive and Super Nintendo cartridges can be analyzed even when
  absent from the regression catalogue. Unsupported cartridge hardware is still
  reported, and both profiles remain experimental.
- The bundled compilation library now includes verified Master System hints
  for 258 exact cartridges, with 338 cartridge identities across all six consoles.
  Reference CPU bus/interrupt fixes and long-path support improve new conversions.
- Game Boy adds guarded native support for a common sprite-DMA helper.
- Twelve reviewed front-cover references improve artwork selection and replace
  known incorrect cached images. Only public links and metadata are bundled.

The Master System qualification scenarios used 7,200 frames each for demo and
scripted play, with strict native and reference comparisons. Native coverage,
CPU agreement, hardware fidelity, gameplay and physical latency remain separate
measures. These checks do not guarantee complete compatibility with every game.

Download the single Windows x64 **Retro-Recomp.exe**, or use **Check for updates**.
Updates preserve your games, settings, compilation library and downloaded covers.
Regenerate a game to receive runtime changes. No ROMs, downloaded artwork,
generated games or private settings are included in this release.

---

# RetroRecomp v0.22.0 — remembered display and 16-bit quick states

- Generated games remember their last display mode and filter, including
  pixel-perfect and aspect-fit fullscreen. Settings remain shared per console.
- F8/F9 quick states now work on qualified Mega Drive and Super Nintendo
  profiles, including after closing the game. Missing loads create no folders.
- The same proportional scanline mask is used across all six consoles.
- Window execution-status text stays in English with either menu language.
- A compact compilation-knowledge library is included in the converter, with
  verified hints for 327 exact cartridge revisions across all six consoles.
  It contains no ROM bytes, artwork or personal settings. New discoveries stay
  local and normal validation remains enabled.
- Broader cartridge checks and guarded RAM execution improve Game Boy, NES and
  16-bit support. Mega Drive now covers 27 qualified revisions and Super Nintendo
  12, including selected PAL revisions. Both 16-bit profiles remain experimental.

234 ROM-free Python tests pass in the development checkout. Fresh-process
quick-state replay matches the uninterrupted image, sound and machine state on
eight tested Mega Drive/SNES games. Display persistence and fractional scanline
geometry are checked separately. These checks do not establish complete gameplay,
independent hardware fidelity or physical latency.

Regenerate games to receive these runtime changes. State compatibility requires
the same ROM, video standard and compatible runtime ABI. See
[state formats and validation](GAME_STATES.md).

Download the single Windows x64 **Retro-Recomp.exe**, or use **Check for updates**.
Updating the converter preserves your existing games, settings and cached artwork.
Original component notices remain embedded; their own licensing terms apply.

---

# RetroRecomp v0.21.0 — saved covers and expanded 16-bit support

## Your artwork, ready for regeneration

Downloaded covers are saved in `datas/BoxArt` beside the converter, separated by
console. Regenerating a game reuses its validated image without another network
request, including after a ROM rename or a change of export folder. Front and
three-quarter versions are retained separately, and existing downloads are reused.
Changing API credentials keeps your artwork. Title-screen and screenshot fallbacks
are retained too. Missing or damaged images use the normal search.

## More 16-bit coverage and smoother audio

Mega Drive now includes twenty-two qualified NTSC revisions and an optional
advanced scan. Both its 68000 and sound Z80, and the Super Nintendo's 65816 and
SPC700, use guarded native paths. Super Nintendo adds four qualified revisions
for six in total, with improvements to interrupt scheduling and audio delivery.
See the [current compatibility limits](CONSOLES_16BIT.md).

Box-art searches prefer Internet front covers by default, with alternate public
hosts and fallback images when a box is unavailable. The SNES audio host now keeps
a reserve suited to the output device and initializes its audio clock from boot.

## Update

Use **Check for updates** or download the single Windows x64 **Retro-Recomp.exe**.
Your games, settings, learning library and downloaded artwork stay local and are
preserved by an update. Regenerate games to receive runtime improvements.
No ROMs, downloaded artwork, generated games or private settings are bundled.
Component notices are embedded; the matching [UPX sources](../licenses/upx-5.2.1-src.tar.xz)
remain available in the repository.

Native coverage, agreement with the internal reference, hardware fidelity,
gameplay validation and physical latency remain separate measures. Mega Drive
and Super Nintendo remain experimental; the other four console profiles are supported.

---

# RetroRecomp v0.20.0 — lightguns across more consoles

## Play with the mouse

Mega Drive now supports Menacer aiming in **Menacer 6-Game Cartridge** and
**T2 - The Arcade Game**. Super Nintendo adds **Super Scope 6**. Move the mouse
to aim, left-click to fire, and use **F5** to choose the cross or dot, size and
color. The default red cross has thicker strokes for better visibility.
Original controller-selection and calibration screens remain intact.

T2's gun detection and CPU/audio scheduling have been corrected. Gun input in
all three games has been confirmed by the user after the fix.

## One app, six consoles

The README is shorter and focuses on the multiconsole experience: mixed-folder
batches, compact standalone games and shared menus. Master System, Game Gear
and original Game Boy are supported. NES, Mega Drive and Super Nintendo remain
experimental; the 16-bit profiles accept six qualified Mega Drive revisions
and two Super Nintendo revisions. See the [current game list](CONSOLES_16BIT.md)
and [gun controls](GUNS_16BIT.md). Other gun games are not automatically enabled.
PAL execution and F8/F9 states are still unavailable on the 16-bit profiles.

## Validation

168 ROM-free Python tests and 127 authored native gun checks pass. Each new gun
cartridge passes 3,600-frame demo and scripted-play comparisons with the internal
reference, with zero interpreted main-CPU instructions on those tested paths.
The sound processors remain interpreted. CPU agreement, hardware fidelity,
complete gameplay and physical latency are separate measures; these checks do
not establish complete hardware accuracy or zero latency.

## Update

Download the single Windows x64 **Retro-Recomp.exe**, or use **Check for updates**.
Regenerate the affected games to receive the gun improvements. Updating the
converter preserves existing games and settings. No ROMs, downloaded covers,
generated games, personal settings or compilation library are bundled.
Component notices remain embedded in the EXE; their own licensing terms apply.
The matching [UPX source archive](../licenses/upx-5.2.1-src.tar.xz) is in the repository.

---

# RetroRecomp v0.19.0 — more native 16-bit execution and refined scanlines

## Mega Drive

Sonic the Hedgehog now uses the same instruction-AOT path as Columns,
Golden Axe and Castle of Illusion, preserving the real 68000 PC, stack and
interrupt frames. The earlier Sonic-specific callbacks are no longer used
on this path. After learning four missing ROM entries, demo and scripted-play
checks of 3,600 frames each completed with zero interpreted main-CPU opcodes.
Their complete visible-frame sequences and final CPU, memory and VDP state
match the internal reference. Golden Axe also passes the same full-length
regression check. The sound Z80 remains interpreted.

## Super Nintendo

Super Mario World now has a compiled 65816 operation map for every physical
ROM byte, with live LoROM mapping, real PC/stack control flow, timed operand
reads and register-width handling. Conversion tests learn RAM helpers in
a library scoped to the exact cartridge hash; each native helper verifies
its PC and four live bytes before running. Modified or unknown code keeps
the reported fallback. Games never write this learning library themselves.

The first ROM-only pass reported 372,060 interpreted instructions in demo and
100,750 in play. Learning 130 RAM variants reduced both to zero over the next
two 3,600-frame checks, about 49 million retired instructions per scenario.
Visible-frame sequences, final CPU/memory state and CPU/master/APU clocks
match the internal reference. The earlier reference divergence is resolved
on these tested paths. Authored fixtures pass 16,544 instruction/state/bus
comparisons, including register widths and changed-code guards.
The SPC700 sound processor remains interpreted.

## Scanlines and validation

Mega Drive and SNES scanlines now draw a fine translucent gap for each guest
raster row instead of darkening every other game row. A cached mask follows
the actual display height, including fractional fullscreen scaling and HiDPI;
below 2x, the effect stays off to preserve readability. Framebuffers and guest
timing are unchanged. Numeric presentation checks pass, and both compressed
test exports launch with the filter active without creating files or folders.

Both 16-bit converters compare native and reference execution over the full
requested demo/play length. Missing diagnostics or differences reject the
candidate and preserve the previous export. The memory command also reports
the MD/SNES converter's ROM entries, guarded RAM variants and library size.
162 ROM-free Python tests pass. Native/reference agreement uses shared engine
semantics; independent hardware fidelity, complete gameplay and physical
latency remain separate evidence.

## Scope and update

Mega Drive and SNES remain experimental. Compatibility is still restricted
to the four exact qualified NTSC Mega Drive revisions and the qualified USA
revision of Super Mario World. Other games, PAL execution and F8/F9 states
are not enabled for these profiles; SNES cartridge-save persistence is also
unfinished. SNES conversion needs installed stable Rust >= 1.85.
See [qualified cartridges and evidence](CONSOLES_16BIT.md).

Download the single Windows x64 **Retro-Recomp.exe**, or use **Check for updates**.
Regenerate games to receive the new execution paths and scanlines; updating
the converter preserves existing game exports and settings. No ROMs, downloaded
covers, generated games, settings or personal compilation library are bundled.
Component terms and notices remain in the EXE, including the imported
frameworks' PolyForm Noncommercial licences. The matching
[UPX 5.2.1 source archive](../licenses/upx-5.2.1-src.tar.xz) remains in the repository.

# RetroRecomp v0.18.0 — Mega Drive expansion and broader NES support

The Windows converter now includes **six console profiles**. Master System,
Game Gear and original Game Boy remain supported for everyday use. NES,
Mega Drive and Super Nintendo are experimental, with explicit compatibility
limits and separate native, reference-CPU, hardware, gameplay and latency evidence.

## Mega Drive and Super Nintendo

Mega Drive accepts exact qualified NTSC revisions of **Sonic the Hedgehog,
Columns, Golden Axe and Castle of Illusion**. A new instruction-level compiler
for the latter three follows the real 68000 PC, stack and interrupt frames.
Conversion passes learn missing ROM entries and RAM instruction variants;
native RAM code checks every instruction byte before running. Changed or
unknown code uses the reported fallback. Failed reference comparison preserves
the previous export.

With an empty converter library, each of those three games reached zero
interpreted 68000 opcodes in two passes, on demo and scripted-play tests of
3,600 frames each. The complete visible-frame sequences and final CPU/memory/
VDP state matched the internal reference. Cold conversions took about 65–78
seconds per title with two concurrent jobs on the development machine;
these are local measurements, not a speed guarantee. Authored fixtures passed
6,208 instruction/state comparisons, plus stack and modified-RAM guard checks.
The VDP's H32/H40 mode selects the correct 256/320-pixel display width.

The Mega Drive sound Z80 remains interpreted. Sonic retains its earlier
compiler route and reference divergence. The experimental Super Nintendo
profile accepts only the qualified USA revision of **Super Mario World**;
it retains substantial 65816 fallback, interpreted SPC700 sound and reference
divergence. Both profiles share RetroRecomp's menus, controls, filters,
fullscreen, cover icons and compressed exports. PAL and F8/F9 are not enabled
for either profile; persistent SNES cartridge saves are also not implemented.
SNES conversion additionally needs an installed stable Rust toolchain >= 1.85.
See [qualified cartridges, dependencies and evidence](CONSOLES_16BIT.md).

## NES

Native coverage now prepares every physical PRG ROM entry, including
bank-switched cartridges, with dispatch following live mappings and operands
read from the live bus at bank boundaries. RAM execution and unstable mappings
keep their fallback safeguards. Authored NROM/MMC1/UxROM/CNROM/MMC3 checks passed
332,800 instruction cases across NTSC and PAL. Targeted Super Mario Bros. 3,
Mega Man 2 and Mega Man probes reached zero fallback on three 1,800-frame paths.

The NES profile adds selectable PAL timing, persistent F8/F9 quick states and
mouse Zapper input for known gun games, with a configurable red cross by
default. States verify ROM identity, timing, ABI and corruption before loading;
failed loads leave the running game intact. Normal launch/quit and loading a
missing state create no data folder. The full 256 × 240 NES picture remains
visible. See [NES scope and limits](NES.md).

## Controls and update

Key labels and letter defaults follow the active keyboard layout, including
AZERTY, in the Master System, Game Gear, NES and new 16-bit menus. Saved custom
mappings retain their physical key positions; Game Boy already handled this.

Download the standalone Windows x64 **Retro-Recomp.exe**, or use the manual
**Check for updates** button. Regenerate a game to apply runtime changes;
updating the converter preserves existing game executables and settings.
No ROMs, downloaded covers, generated games, settings or personal compilation
library are included. Third-party terms and notices are retained, including
the 16-bit engines' PolyForm Noncommercial licences.

Native/reference agreement is bounded software evidence using shared engine
semantics, not an independent hardware oracle or a full-game playthrough.
Physical latency has not been measured. Gameplay review remains separate.

# RetroRecomp v0.17.0 — improved Sega audio and better box-art icons

Master System and Game Gear exports now use an audio path with shorter
sample-rate conversion staging and a bounded output buffer. It accepts the
Windows device's actual callback period and primes playback to accommodate
PAL/NTSC frame delivery. Pause, restart and state load clear queued sound.
Console clocks, input handling and PSG sound synthesis are unchanged.

ROM-free numeric checks passed for PAL/NTSC timing, stereo separation, filter
response, buffer bounds and callback scheduling. Silent WASAPI output checks
also passed. On the local Alex Kidd cartridge, two 600-frame scenarios kept
identical raw PSG sound, VDP traces and final CPU states before/after the change,
with matching reference CPU states and zero fallback. These are bounded
technical checks; total physical audio latency has not been measured.
See [audio details](AUDIO.md).

**Options → Box art** adds user-configured ScreenScraper, TheGamesDB and IGDB
access. API credentials are stored separately with Windows account protection;
ordinary website accounts alone are not enough for these services. Local
artwork remains first priority, with the public Libretro library as a no-key
fallback. ArcadeItalia is listed for reference; its MAME API does not serve
the current console profiles.

Real three-quarter box images are preferred. When one is unavailable, the
front cover stays flat: no artificial spine or perspective is added. Original
or HD sources are requested when available, and all nine ICO sizes, up to
256 × 256, are rendered directly from the source. Older API thumbnail caches
can be checked again for a better source. Portable Game Boy and NES builds
also locate their bundled licensing notices correctly. See [box-art setup](BOXART.md).

Install the standalone Windows x64 `Retro-Recomp.exe`, or use the manual
**Check for updates** button. **Regenerate a game to apply the new audio path
or icons**; installing the converter does not rewrite existing games.
Master System, Game Gear and original Game Boy remain supported profiles;
NES remains experimental. Authenticated artwork APIs have fixture coverage
but still need live validation with user-supplied developer credentials.
The download contains no ROMs, cover downloads, generated game executables,
settings or personal compilation library. Licensing and upstream attributions
are unchanged.

# RetroRecomp v0.16.0 — broader native NES coverage

The experimental NES profile now compiles every NROM (mapper 0) ROM position
that can begin a complete instruction, including targets not found by scripted
exploration. An instruction crossing `$FFFF` still uses the reported fallback;
bank-switching mappers retain their existing discovery-based compilation. The
upstream NESRecomp checkout is unchanged: RetroRecomp stages a private compiler
adapter during conversion.

On the local Super Mario Bros. cartridge, 32,767 of 32,768 potential CPU ROM
entry positions were compiled. Boot and two scripted input runs of 3,600 frames
each used zero interpreter cycles. The generated game matched the **same
engine's internal interpreter** for 120 boot frames and 600 frames of each
input run; an additional 3,600-frame gameplay comparison also matched. One
private first conversion took about 2 minutes 44 seconds, and the packed Mario
game grew from about 1.33 MB to 2.42 MB. These are measurements of one cartridge
and bounded paths, not proof of complete-game or independent hardware fidelity.
Physical input latency was not measured. The NES profile remains experimental.

NES game windows now show only the game name and `Native code` or `Interpreter
fallback`, matching the compact status used by other profiles. Any ROM, RAM or
other CPU fallback keeps the fallback status visible until the game closes.
Gameplay probes also keep exercising inputs beyond the first 300 frames, and
the in-app fallback footer is shorter. Only Super Mario Bros. was regenerated
locally; other games were not rebuilt for this release.

The Windows x64 download is a standalone `Retro-Recomp.exe`. Existing installs
can use the manual **Check for updates** button. The release contains no ROMs,
covers, generated game executables, settings or personal observation library.
The original RetroRecomp code remains MIT; the NES backend retains its PolyForm
Noncommercial terms and attribution. See the [NES profile](NES.md) and
[third-party notices](../THIRD_PARTY_NOTICES.md).

# RetroRecomp v0.15.0 — faster Game Boy conversion and a cleaner workspace

Original Game Boy is now a supported everyday-use profile rather than an alpha
feature. Deep reference CPU validation is enabled by default, including once
for existing GUI preferences; it can still be disabled under Options → Game Boy
or with `--no-gb-deep-validation`. This changes the depth of CPU checks, not
native ROM discovery or the interpreter fallback policy.

The converter's Options window groups shared export, artwork, batch and
overwrite settings under Common, with separate Master System, Game Gear,
Game Boy and NES tabs for console-specific settings. The Credits and Check for
updates buttons have exchanged places. The ROM list uses the space freed by
removing conversion settings from the main window.

Game Boy now compares matching CPU memory blocks efficiently, builds generated
C code with bounded MSVC parallelism, and runs independent deep comparison
scenarios concurrently. On one local Super Mario Land conversion with a
populated entry library, deep validation took 55.8 seconds; a historical deep
run took about 750 seconds, over 10× longer. Those runs had different cache
and implementation conditions, so this is not a controlled across-game
speedup. An empty-library deep run under the new code took 84.5 seconds.
All three final 3600-frame probes reported zero fallback cycles and the
requested CPU comparisons matched the internal reference. These results do
not establish complete-game compatibility, independent hardware fidelity,
gameplay quality or physical latency. Existing games were not regenerated.
NES remains experimental and Game Boy Color-only cartridges remain unsupported.

# RetroRecomp v0.14.5 — edition names and optional regeneration

Batch conversion now distinguishes different ROM revisions with source-derived
region/revision labels, or stable version A/B labels when the filenames do not
identify the difference. Roman numerals and sequel numbers in titles remain
part of the game name. Identical ROM bytes under different filenames are
reported with the existing game's name; they cannot produce a different game.
The new **Overwrite existing executables** option is on by default. Turning it off
skips already exported games while converting missing ones, including in mixed
console batches. No game was regenerated for this converter change.

The local converter library was audited after a large Master System batch:
6,893,562 bytes in 581 files, but only 101 ROM entries were verified for
reuse, all for one Alex Kidd cartridge (2,631 bytes in a compact JSON pack).
The remaining observations are RAM-related and cannot be shared as verified
ROM entries. The library stays local; no personal paths, ROM-derived code
patterns or conversion histories are bundled into this build.

# RetroRecomp v0.14.4 — concurrent batch conversion (included in v0.14.5)

Mixed-console batches can now convert up to eight different games in parallel.
The GUI and `batch` command default to three concurrent games; choose one for
the previous sequential behavior or adjust the setting for available CPU and
memory. Export names are reserved before builds begin, so editions with the
same title keep separate executables and per-ROM reports. Stopping a batch
allows active conversions to finish without starting more games. Shared
dependency setup is serialized. This changes conversion throughput only;
runtime responsiveness and game validation have not been remeasured.

# RetroRecomp v0.14.3 — clearer update errors (included in v0.14.5)

Connection and firewall failures during the manual update check or download
now show a short English or French message instead of the raw network exception.
HTTP service errors use a separate retry-later message. Download checks and
rollback behavior remain unchanged.

# RetroRecomp v0.14.2 — standalone converter download

The Windows converter is now distributed as one `Retro-Recomp.exe`. Its Credits
window displays the bundled project license and complete third-party notices,
with a link to the matching [UPX 5.2.1 source archive](https://github.com/ArthurReboulSalze/RetroRecomp/blob/e522cbde7ca6e7e6eccc0c901389a4178492e6d7/licenses/upx-5.2.1-src.tar.xz).
The download does not place license folders or source archives beside the EXE.

The manual updater now downloads and verifies that single EXE, replaces the
converter after it closes, and restarts it. Versions through v0.14.1 need one
manual replacement to adopt the new update format. Games and user settings are
preserved. No game executable was regenerated for this packaging change.

# RetroRecomp v0.14.1 — visible upstream credits

The converter now has a **Credits** button. It explains that RetroRecomp
combines several independent console-specific recompilers and runtimes in one
application, credits creator and integrator Arthur Reboul Salze, and links the
upstream repositories used for Master System, Game Gear, Game Boy and NES.
The console list scrolls to accommodate future profiles. Licensing notices
remain available from the same window. The main toolbar also shows the
installed RetroRecomp version beside the Credits and update controls.

The v0.14.0 converter can install this version through its manual **Check for
updates** button. The release includes only the converter and legal notices;
it does not regenerate games or bundle ROMs, covers, settings or game data.
The NES profile remains experimental.

# RetroRecomp v0.14.0 — manual in-app updates

The Windows converter now has a **Check for updates** button. It makes no
update request on startup. A click checks this project's GitHub releases,
including previews, and offers a newer Windows x64 package. On acceptance it
downloads and verifies the ZIP, then uses a temporary helper to replace the
converter after it closes and restart the updated version. A failed file
replacement restores the previous converter. Existing games, preferences,
saved states and compilation memory are left in place. Earlier versions need
one manual installation of v0.14.0 to gain this updater.

The release contains the converter and legal notices only. Master System,
Game Gear and original Game Boy remain the playable profiles; NES remains
experimental. This release does not regenerate any game executables.

# RetroRecomp v0.13.0 — multi-console Windows x64 preview

The Windows converter now includes four profiles in one interface. It accepts
mixed ROM folders, detects recognized formats, and exports games into separate
Master System, Game Gear, Game Boy and Nintendo NES folders. Master System,
Game Gear and original Game Boy are playable; the new NES profile remains
experimental.
Only the converter and legal notices are in the release ZIP: no ROMs, covers,
generated games or personal conversion library are included.

Game Gear keeps the native 160 × 144 LCD crop, 12-bit palette and one-player
controls. Original Game Boy uses a separate SM83 recompiler, DMG presentation
and an optional deep CPU validation mode. Game Boy Color-only cartridges are
unsupported. Generated games are compacted before export. Fallback remains
measured and reported; native coverage alone does not prove CPU, hardware or
gameplay fidelity, nor physical input latency.

An experimental Nintendo NES profile now identifies `.nes` and single-ROM
ZIP cartridges, recompiles observed 6502 paths with pinned NESRecomp, and
exports standalone Windows games under `Games/Nintendo NES`. The converter
keeps ROM-specific entry observations, reports exact native/interpreted CPU
cycles and compares short frame hashes with the same engine's interpreter.
The generated game embeds its ROM and legal notices. Its menu uses the shared
RetroRecomp canvas with two players and the main display shortcuts. NES is
NTSC-only for now; F8/F9 states, broad mapper/gameplay validation and
independent hardware comparison remain open. The NES engine is licensed
PolyForm Noncommercial 1.0.0. Review [third-party notices](../THIRD_PARTY_NOTICES.md)
before redistribution.

# RetroRecomp v0.12.0 — source development build, no release ZIP

Original Game Boy `.gb` and single-ROM ZIP inputs now use a separate pinned
SM83 recompiler and Game Boy runtime. Converted games go into
`Export/Games/Game Boy`, support one player and native 160 × 144 output,
and keep settings and saves lazy in `datas`. The report counts fallback
instructions/cycles without inventing a native percentage. The initial local
Tetris, MBC1 Super Mario Land and battery-backed MBC2 Lazlos' Leap boot tests
ran 120 frames with zero fallback cycles in their final exports; a 30-frame
generated/reference CPU comparison matched for each. Super Mario Land first had 76 fallback cycles; reusing its
observed entry trace removed them on this boot path. Unchanged battery RAM
does not create a data folder on launch/quit. This is not independent hardware
or whole-game validation. This historical source development build was not
packaged as a GitHub release; Game Boy is included in v0.13.0.

Game Boy also seeds short ROM branches and learns from boot plus two scripted
play paths. The default CPU validation keeps a short mandatory boot check;
**Deep Game Boy validation (slow)** optionally adds the much longer per-play
comparisons. Native discovery and coverage tests stay the same in both modes.
Reports now identify validation scope and time spent on each conversion stage.

# RetroRecomp v0.11.0 — source development build, no release ZIP

Game Gear cartridge conversion was first introduced as a console
profile. `.gg` and single-ROM ZIP inputs use Game Gear colors, Start, stereo
port, one-player controls and separate game exports. The original 160 × 144 LCD
view is the only presentation mode. No ROM patch or expanded view is used.
Factory Panic passed targeted
120-frame native/reference checks; whole-game and visual verification remain
open. This historical development build was not published as a GitHub release;
Game Gear is included in v0.13.0.

# RetroRecomp v0.10.17 — Master System for Windows x64

Convert your own Master System ROMs into standalone Windows games. This preview
release brings the supported Sega-mapper backend to a practical, playable
state: add a ROM or a folder, convert, and launch each result directly. The
converter performs more CPU work ahead of time to reduce interpreter fallback
while keeping any fallback use visible.

## What's new since v0.10.4

- Scanline-aware Mode 4 video, PAL/NTSC timing choices and corrected interrupt
  boundaries. A chosen timing is remembered for the exact ROM across converter
  engine updates.
- Mouse Light Phaser support for known gun games, with a configurable reticle
  and optional shooting badges on generated cover icons.
- Two fullscreen sizes, gamepad autofire, and persistent F8/F9 quick states
  for newly generated games.
- Cleaner game folders: normal launch creates no data directory or diagnostic
  log. Settings and states are written when needed; converter learning stays
  in the converter's own library.
- Generated games carry their title, console, required controls and
  RetroRecomp version in standard Windows executable metadata.

## Validation and limits

66 ROM-free Python tests pass. Authored native checks cover CPU-step stopping,
video timing, input and game states. Locally tested titles have reached zero
fallback cycles in specified demo and scripted-play scenarios and passed
native/reference CPU and VDP comparisons. These checks do not establish
whole-game coverage or exact hardware fidelity. Physical input latency and
comparative FPS have not been measured.

The ZIP contains the converter and legal notices only: no ROMs, generated
games, separate box art, settings or compilation library. Git and Visual
Studio C++ Build Tools are needed to convert games; neither Python nor a
development toolchain is needed to play a generated game. See the
[README](https://github.com/ArthurReboulSalze/RetroRecomp/blob/main/README.md),
[compatibility notes](https://github.com/ArthurReboulSalze/RetroRecomp/blob/main/docs/COMPATIBILITY.md)
and [third-party licensing notices](https://github.com/ArthurReboulSalze/RetroRecomp/blob/main/THIRD_PARTY_NOTICES.md).
