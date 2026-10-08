<p align="center">
  <img src="MEDIAS/RetroRecomp_ban.png" alt="RetroRecomp — from retro cartridges to native executables" width="900">
</p>

<h1 align="center">RetroRecomp</h1>
<p align="center"><strong>Your retro cartridges, ready to launch.</strong></p>
<p align="center">Add a ROM or a whole folder, convert, and play standalone Windows games.<br>
More work happens before launch, so playing stays simple and responsive.</p>
<p align="center">One converter for multiple consoles. Windows x64 is the current
output platform; more game systems and host platforms are planned.</p>
<p align="center"><em>Less emulation. No FPGA. As native as possible.</em></p>

<p align="center">
  <img src="https://img.shields.io/badge/release-0.18.0-0879fa" alt="Release version 0.18.0">
  <img src="https://img.shields.io/badge/console_profiles-6-26d7ff" alt="Six console profiles">
  <img src="https://img.shields.io/badge/current_platform-Windows_x64-0879fa" alt="Windows x64">
  <img src="https://img.shields.io/badge/original_code-MIT-aa66ff" alt="Original contributions: MIT">
</p>

<p align="center">
  <a href="https://github.com/ArthurReboulSalze/RetroRecomp/releases">Releases</a> ·
  <a href="docs/BUILDING.md">Build from source</a> ·
  <a href="docs/ROADMAP.md">Roadmap</a> ·
  <a href="THIRD_PARTY_NOTICES.md">Credits and licensing</a>
</p>

**The current Windows release includes six console profiles.** Master System,
Game Gear and original Game Boy are supported for everyday use. NES, Mega Drive
and Super Nintendo remain experimental; the two 16-bit profiles accept only
the qualified game revisions listed below. Each has its own hardware runtime
and validation limits.

## Why RetroRecomp?

- **Simple from conversion to play.** Choose one ROM or add mixed folders, then
  launch each game from its own executable. Playing needs no Python, separate
  ROM file or external SDL2 DLL. Regenerating a game replaces its previous
  export instead of filling the folder with numbered builds. The converter
  recognizes supported consoles and sorts games into their own folders;
  unknown formats are listed and skipped. Newly generated games are compacted
  into smaller standalone executables before export.
- **Native-first performance.** RetroRecomp translates Z80, SM83, 6502, 68000
  or 65816 game code ahead of time, depending on the console. Supported SMS/GG ROM-bank
  positions are prepared by default; NES games also prepare every physical
  PRG ROM entry, with dispatch following live cartridge banks. Game Boy uses
  discovery and conversion-time probes. Covered CPU paths run as
  compiled host code, while interpreter fallback remains counted and reported.
- **A practical Master System experience.** The Master System backend is now
  viable for everyday play with supported Sega-mapper ROMs. It includes two
  players, gamepad mapping, fullscreen and lightweight display filters,
  PAL/NTSC timing choices, quick states and mouse Light Phaser support for
  known gun games. Recent exports have also been reviewed in gameplay, while
  full-catalogue compatibility and exact hardware behavior remain open work.
- **Game Gear.** The shared Sega Z80 backend uses Game Gear's
  12-bit colors, Start button and stereo port, with one player and the native
  160 × 144 LCD window. ROMs are not patched or expanded beyond the visible
  screen. The profile is playable; complete catalogue compatibility and
  hardware fidelity are not established. See the [Game Gear profile](docs/GAME_GEAR.md).
- **Game Boy (fully supported profile).** Original `.gb` cartridges use a separate SM83
  compiler and 160 × 144 DMG runtime. Short branch discovery and three
  conversion probes reduce fallback on tested paths. Deep reference CPU checks
  now run by default, while the faster standard check remains available. The
  profile is no longer alpha; targeted Tetris and Super Mario Land checks pass.
  Complete catalogue and hardware behavior remain unverified. Game Boy Color-only games are
  not supported. See the [Game Boy profile](docs/GAME_BOY.md).
- **NES (experimental).** `.nes` cartridges use a separate 6502 backend and a
  per-ROM library of observed code entries. Native ROM coverage includes
  bank-switched cartridges. PAL/NTSC timing, two controller ports, F8/F9 quick
  states and mouse Zapper input for known gun games are included. Targeted
  conversions pass with zero interpreter cycles on the tested paths; broad
  mapper, hardware and gameplay validation are still open. The upstream
  engine uses a noncommercial license. See the [NES profile](docs/NES.md).
- **Mega Drive (experimental).** Qualified NTSC revisions of Sonic the Hedgehog,
  Columns, Golden Axe and Castle of Illusion can be converted. A new instruction
  compiler gives the latter three games native 68000 execution on both tested
  demo and play paths, including guarded code in RAM. The sound Z80 remains
  interpreted. Menus, mapping, filters and fullscreen match the other profiles.
  Wider game compatibility, PAL and F8/F9 states remain open.
  See the [qualified cartridges and evidence](docs/CONSOLES_16BIT.md).
- **Super Nintendo (experimental).** The qualified USA revision of Super Mario
  World uses generated 65816 code and the same RetroRecomp menus. Main-CPU
  fallback and interpreted SPC700 sound remain; reference divergence still
  needs investigation. Other games, PAL, F8/F9 and persistent cartridge saves
  are not enabled yet.
  See the [16-bit integration scope](docs/CONSOLES_16BIT.md).

<p align="center">
  <img src="MEDIAS/RetroRecomp_UI.png" alt="RetroRecomp interface with automatic console selection, platform and language selectors, and a batch conversion queue" width="1000">
</p>
<p align="center"><em>Choose your ROMs, convert a batch, and launch the finished games. Conversion settings are grouped in Options.</em></p>

<p align="center">
  <img src="MEDIAS/RC_Windows_Screen.png" alt="Windows Explorer displaying generated Master System game executables with box-art icons and shooting badges" width="1100">
</p>
<p align="center"><em>Your generated games remain easy to recognize in Windows Explorer.</em></p>

## How it works

RetroRecomp converts the Z80 program inside a Master System or Game Gear ROM,
the SM83 program inside an original Game Boy ROM, the 6502 program inside an
NES ROM, or qualified 68000/65816 programs for Mega Drive and Super Nintendo
into C and then a Windows executable. The resulting game contains its
own ROM data and runtime, so playing it does not require Python, a separate
ROM file, or an external SDL2 DLL.

Video, sound, memory, inputs, bank switching and interrupts are still
reproduced by a hardware runtime. **This is static CPU recompilation with a
hardware runtime and a reported fallback interpreter.** Native coverage,
CPU agreement, hardware fidelity, gameplay and physical latency are separate
questions; none is proved by the others.

Version 0.18.0 adds the experimental 16-bit profiles, extends native NES
coverage to bank-switched cartridges, and brings NES PAL timing, quick states
and Zapper input. Keyboard labels and letter defaults now follow the active
layout, including AZERTY. Regenerate a game to apply runtime changes;
updating the converter preserves existing game executables.
See the [release notes](docs/RELEASE_NOTES.md), [NES profile](docs/NES.md)
and [16-bit scope](docs/CONSOLES_16BIT.md).

### Compile more. Discover less at runtime.

Extended native coverage is enabled by default for the SMS/GG profiles. It
prepares supported instruction positions across ROM banks before play, so
indirect jumps and bank changes can reach precompiled code. Game Boy combines
an all-bank SM83 scan, short branch discovery and scripted conversion tests.
NES prepares native entries across physical PRG banks and follows live bank
mapping. The three newer Mega Drive profiles learn missing instruction starts
and guarded RAM variants during conversion, then regenerate code in another
pass. Unknown paths can still require the appropriate reference interpreter;
its use is reported.

Game Boy keeps all three coverage tests and **Deep Game Boy validation** in its
default conversion. The latter adds longer reference CPU checks without
changing native discovery. Uncheck it under Options → Game Boy for the faster
standard check. The common export and batch settings live under Options → Common;
the SMS/GG native coverage option appears under both 8-bit Sega console tabs.

For one local Super Mario Land conversion with a populated entry library, deep
validation took 55.8 seconds after these optimizations, versus a historical
deep run of about 750 seconds (over 10× less time). The runs used different
cache and implementation conditions, so this is a historical comparison, not
a controlled benchmark or a time guarantee for other games. With an empty
entry library, the current deep conversion took 84.5 seconds. See the
[Game Boy measurements](docs/GAME_BOY.md) for validation scope and timings.

### Each generation can improve the next

Discoveries made during the converter's automated tests are saved locally
against the game's identity. The SMS/GG and newer Mega Drive profiles can compile observed RAM
instruction variants with byte guards; Game Boy and NES reuse observed ROM
entry points. Each generation checks its candidate before replacing an older
executable. Unknown code remains a reported fallback.

This memory is a compilation library, not an AI model. An optional local AI
player to explore more paths is a future research direction; it is not part
of the current release. See [the architecture](docs/ARCHITECTURE.md).

## Available today

| Capability | Current Windows release |
| --- | --- |
| Game system | Master System, Game Gear and original Game Boy; experimental NES, Mega Drive and Super Nintendo profiles |
| Output | Standalone Windows x64 game executable |
| Conversion | Single ROM or mixed-console batch, three concurrent games by default (1–8 adjustable); extended SMS/GG coverage enabled by default |
| Improvement | ROM-specific entry observations; guarded RAM variants on SMS/GG and the three newer Mega Drive profiles |
| Interface | English and French, with contextual help and conversion log |
| Inputs | Master System: two players and optional gun; Game Gear and Game Boy: one player; NES: two joypads or mouse Zapper; Mega Drive/SNES: two controller ports |
| Presentation | Integer-scaled fullscreen, sharp pixels, bilinear, Scale2x, scanlines |
| Video timing | Master System and NES: per-ROM PAL/NTSC; Game Gear: NTSC 160 × 144 LCD; Game Boy: DMG 160 × 144; Mega Drive/SNES proofs: NTSC |
| Light Phaser | Master System only: mouse aiming in catalogue-selected gun games; configurable reticle |
| Quick states | F8 save and F9 load on Master System, Game Gear, Game Boy and NES; not yet on Mega Drive/SNES |
| Game icons | Optional local/online box art; automatic shooting badges for known Master System gun games |
| Files | Shared `datas` folder; game-specific data isolated by identity |
| Regeneration | Same game filename; replacement deferred if the executable is running |
| Batch overwrite | On by default; disable to skip already exported games without rebuilding them |

The Master System profile includes scanline-aware video, PAL/NTSC timing
choices, CPU/VDP comparisons and persistent quick states. Its Light Phaser
mode uses mouse aiming for known gun games; the reticle and automatic icon
badges are configurable. See [video timing](docs/VIDEO.md),
[Light Phaser support](docs/LIGHT_PHASER.md),
[game states](docs/GAME_STATES.md) and
[console profiles](docs/SYSTEM_PROFILES.md) for the details and limits.

Generated games create no default INI or diagnostic log just from being
launched. Settings and quick states are saved only when requested; changed
cartridge battery RAM may write a per-game save on exit. The converter keeps
its separate learning library for future generations.
The screenshots above show locally generated icons; the repository and converter download
contain **no ROMs, game executables, separate box-art files, gameplay captures
or personal compilation libraries**.

Under **Options → Box art**, configure ScreenScraper, TheGamesDB or IGDB for
missing artwork. Local covers remain first priority, with public Libretro
downloads available without an API key. Real three-quarter boxes are preferred
by default; when unavailable, the front cover stays flat, with no generated
spine or perspective. Source images are requested at original or HD resolution
when available, and each Windows icon size is generated directly from the source.
ArcadeItalia is referenced
in the same panel; its public MAME API does not cover the current console
profiles. See [box-art sources and setup](docs/BOXART.md).

Use your own ROMs and artwork that you are entitled to use. Generated game
executables embed the ROM and must not be treated as redistributable merely
because RetroRecomp generated them.

## Getting started on Windows

1. Download `Retro-Recomp.exe` for Windows x64 from [Releases](https://github.com/ArthurReboulSalze/RetroRecomp/releases). The [source build instructions](docs/BUILDING.md) are also available.
2. Install Git and Visual Studio Build Tools with **Desktop development with C++**, including x64 tools, CMake and a Windows SDK. Python is unnecessary for the packaged converter.
   The experimental Super Nintendo profile also requires an installed stable Rust toolchain, version 1.85 or newer.
3. Run `Retro-Recomp.exe`, choose **Add ROMs** or add one or more folders. Console detection is **Automatic** by default. Review unknown rows, then choose **Convert / regenerate**.
4. Select a successful result and choose **Play game**.

The converter creates `Games` beside `Retro-Recomp.exe` by default and adds a
subfolder for each recognized console as needed. Check **Custom
export folder** to choose a different root; the console subfolders are still
created there. `.sms`, `.gg`, `.gb`, `.nes`, linear `.md`/`.gen`, validated
`.sfc`/`.smc` and single-ROM ZIP files are recognized by their format.
For `.bin` and `.rom` dumps, Automatic uses a recognizable
cartridge header; if the console remains unknown, choose it explicitly in the
top-right selector. Unrecognized ROMs are shown in the queue and batch report,
and are never compiled as another console. Original ROM files are only read.

The first conversion downloads pinned build dependencies and compiles them.
Internet access is required for that setup. Afterward, cached dependencies can
be reused; missing-cover downloads are optional. Cover lookup uploads no ROM
bytes. It uses the title and console; ScreenScraper can also use the filename,
file size and ROM hashes to identify the correct edition.

```text
RetroRecomp/
  Retro-Recomp.exe
  datas/                         created locally when needed
  Games/
    Master System/
      Your game.exe              created from your own ROM
      datas/                     saved controls/states; conversion reports when generated
    Game Gear/
      Another game.exe           separate Game Gear export category
      datas/
    Game Boy/
      Third game.exe             separate Game Boy export category
      datas/
    Nintendo NES/
      Fourth game.exe            experimental NES export category
      datas/
    Mega Drive/
      Qualified game.exe         experimental, exact NTSC revision required
      datas/
    Super Nintendo/
      Super Mario World.exe      experimental, qualified USA revision only
      datas/
```

The release starts clean: it contains no saved settings, games or learned
observations. Files are resolved relative to the application and games,
including when launched from a different working directory.

To update the converter, click **Check for updates** in its toolbar. RetroRecomp
does not contact GitHub for updates on startup. If you accept a newer Windows
release, it verifies the EXE download, closes, replaces the converter, then
restarts. Existing `Games` and `datas` are preserved. Builds through v0.14.1
need one manual replacement to use the single-EXE update format.

The **Credits** button names the creator and links the independent upstream
recompilers and runtimes used for each console profile. The list scrolls as new
consoles are added. Its licensing viewer contains the complete bundled notices
and links to the matching [UPX 5.2.1 source archive](https://github.com/ArthurReboulSalze/RetroRecomp/blob/e522cbde7ca6e7e6eccc0c901389a4178492e6d7/licenses/upx-5.2.1-src.tar.xz).

### Game shortcuts

| Key | Action |
| --- | --- |
| F1 | Restart |
| F2 | Configure keyboard/gamepad mappings, including console-specific buttons |
| F3 | Next filter |
| F4 | Window → pixel-perfect fullscreen → fit fullscreen → window |
| F6 | Gamepad autofire on/off |
| F7 | English/French |
| F8 | Save/replace this game's quick state (SMS, GG, GB and NES) |
| F9 | Load it, including after quitting and restarting (SMS, GG, GB and NES) |
| H | Help |
| P / Enter | Pause/resume on SMS/GG; other profiles use P for pause and Enter for cartridge Start |
| Esc | Close the current menu, then quit |

On Master System, gamepad Start/Menu pauses by default and Select/Back restarts
for player 1 only; player 2 cannot reset. On Game Gear, Start goes to the
cartridge and Back opens the menu. Game Gear has no player 2 or Light Phaser.
Game Boy uses the same menu style and shortcuts; W/X are A/B, Enter is
cartridge Start, either Shift is Select, and P pauses. F5 chooses between its
default grayscale image and classic green. Its controller
Start and Back remain cartridge buttons, with left-stick click for pause.
NES uses W/X for A/B, Enter and right Shift for cartridge Start/Select, and
P for pause. Its second player uses the keypad. See [NES](docs/NES.md) for
the experimental profile's controls and limitations. Mega Drive defaults to
W/X/C for A/B/C; SNES uses W/X/A/S for A/B/X/Y and Q/E for L/R. Both use Enter
for cartridge Start. See the [16-bit controls and limits](docs/CONSOLES_16BIT.md).
Fullscreen keeps interpreter diagnostics out of the
game image, while counters remain available and logs require explicit
diagnostics. Games exported before quick states were added need regeneration
to gain F8/F9. See [controls](docs/CONTROLS.md)
and [state storage and compatibility](docs/GAME_STATES.md).

## What has been verified

The measurements are deliberately separate:

| Area | Evidence and limit |
| --- | --- |
| Native execution | Several local games reached zero fallback cycles in their tested demo and scripted-play scenarios. This does not cover every game path. |
| CPU fidelity | Independent Z80 checks covered 51,328 cases for the native CPU work; current conversions also compare observed CPU results with the reference interpreter. |
| Reference comparison | Conversion checks compare CPU, RAM, image hashes and VDP traces on observed scenarios. Both paths share the same hardware runtime. |
| Hardware fidelity | Authored NTSC/PAL and scanline checks pass; complete console fidelity, including pixel-clock effects, is not established. |
| Gameplay | Recent exports have been reviewed in play, but full-catalogue playthroughs and physical two-controller sessions are not established. |
| Physical latency | Not measured; no zero-latency guarantee. |

ROM-free Python and native self-tests cover conversion, video, input and state
handling. Targeted Game Gear, Game Boy and NES checks are documented in their
profile pages. Validation files and game captures stay local; they are not
bundled with this public repository.

See [compatibility and limitations](docs/COMPATIBILITY.md) before assuming
a game, mapper or platform is supported.

## Next for Master System

Work continues on game coverage, hardware behavior and validation of more
gameplay paths. The [roadmap](docs/ROADMAP.md) tracks these Master System
priorities without promising compatibility for every cartridge.

## Development and credits

RetroRecomp was created and integrated by [Arthur Reboul Salze](https://github.com/ArthurReboulSalze).
It brings several independent recompilers and runtimes together in one converter.
The desktop application is written in Python; the generated games and host
runtime use C and SDL2. [Build instructions](docs/BUILDING.md) cover source
usage, packaging and reproducible dependency revisions.

RetroRecomp builds on [mstan/smsggrecomp](https://github.com/mstan/smsggrecomp),
[mstan/z80-recomp-core](https://github.com/mstan/z80-recomp-core),
[superzazu/z80](https://github.com/superzazu/z80),
[SDL2](https://github.com/libsdl-org/SDL),
[Pillow](https://python-pillow.org/), and
[SingleStepTests/z80](https://github.com/SingleStepTests/z80) for independent CPU validation.

**Original RetroRecomp contributions are licensed under [MIT](LICENSE).**
Third-party material retains its own terms. The pinned upstream SMS/GG engine
has no declared public license; its author has granted the RetroRecomp project
owner noncommercial use with attribution. The shared Z80 core uses PolyForm
Noncommercial 1.0.0. MIT does not override those terms or grant rights to ROMs
or artwork. See [third-party notices and licensing limits](THIRD_PARTY_NOTICES.md).

Contributions are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md), and do not
attach commercial ROMs, generated game binaries, copyrighted box art or private logs.
