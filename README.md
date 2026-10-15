<p align="center">
  <img src="MEDIAS/RetroRecomp_logo_outlined.png?v=8fb265de351a" alt="RetroRecomp logo" width="182">
</p>

<h1 align="center">RetroRecomp</h1>
<p align="center"><strong>Multiple retro consoles. One app. Your games, ready to launch.</strong></p>
<p align="center">Master System · Game Gear · Game Boy · NES · Mega Drive · Super Nintendo · Neo Geo</p>
<p align="center"><em>Less emulation. No FPGA. As native as possible.</em></p>

<p align="center">
  <img src="https://img.shields.io/badge/release-1.0.2-d4a737" alt="Release version 1.0.2">
  <img src="https://img.shields.io/badge/console_profiles-7-626262" alt="Seven supported console profiles">
  <img src="https://img.shields.io/badge/current_platform-Windows_x64-343434" alt="Windows x64">
  <img src="https://img.shields.io/badge/original_code-MIT-d4a737" alt="Original contributions: MIT">
</p>

<p align="center">
  <a href="https://github.com/ArthurReboulSalze/RetroRecomp/releases">Download</a> ·
  <a href="docs/BUILDING.md">Build from source</a> ·
  <a href="docs/COMPATIBILITY.md">Compatibility</a> ·
  <a href="THIRD_PARTY_NOTICES.md">Credits and licensing</a>
</p>

## One converter, multiple consoles

RetroRecomp brings several recompilers together in one application. It recompiles
game code into compact, standalone Windows executables for a simple, responsive
retro gaming experience, with as much native execution as possible and no
dedicated FPGA hardware.

- **Convert a whole collection.** Drop ROMs, ZIPs or mixed folders into the window,
  or use the file buttons. Recognized
  games are sorted by console, and multiple conversions can run together.
- **Regenerate only what needs it.** Up-to-date exports are kept when the
  converter, settings and fallback hints are unchanged. Convert the whole list
  or just the selected games; force regeneration remains available in Options.
- **Launch directly.** Generated games need no Python installation, separate ROM
  file or external SDL2 DLL. Regeneration can replace existing exports.
- **Keep familiar controls.** Shared menus, keyboard/gamepad mapping, fullscreen
  modes and lightweight filters keep the experience consistent across consoles.
  Your display mode and filter are remembered; F8/F9 quick states resume after closing the game.
- **Let your next build learn from your play.** Games remember useful fallback
  hints, helping RetroRecomp cover more of the code you actually use.
- **Make games easy to find.** Optional box-art icons and shooting tags distinguish
  your exports. Mouse aiming is available for supported lightgun games.
  Downloaded artwork is saved and reused when you regenerate games.
  Cover searches handle common title variations while keeping sequels distinct.
- **Build on shared knowledge.** Verified hints for **1,061 exact cartridge
  revisions** are included, while your own discoveries stay in your local library.

## Play. Learn. Recompile.

Your play sessions can improve the next export. When a game needs the interpreter
fallback, it collects small hints in memory and saves them **when you close the
game**, avoiding feedback writes during play.

<p align="center">
  <img src="MEDIAS/RetroRecomp_learning_cycle.png" alt="Play a game, collect fallback hints, enrich Retro-Recomp's local memory, and regenerate the executable" width="640">
</p>

RetroRecomp imports these hints, checks them against the exact game and uses them
during regeneration. **Options → console → Import fallback hints** also lets you
recover them from games stored elsewhere. Once imported, they remain in the
converter's library even if you move or delete the original game folder.

Recording is on by default; **F12** switches it on or off. Each game's feedback
file is capped at about **128 KiB**. This can reduce fallback on supported code
paths; graphics and hardware issues still need fixes in the runtime.
See [how the learning loop works](docs/RUNTIME_FEEDBACK.md).

## Console support

| Console | Current status |
| --- | --- |
| Master System | Supported; two players, PAL/NTSC, quick states and Light Phaser |
| Game Gear | Supported; native handheld display and colors |
| Game Boy | Supported; original Game Boy, quick states, grayscale or classic green |
| NES | Supported; validated cartridge layouts, PAL/NTSC, quick states and Zapper |
| Mega Drive | Supported; standard cartridges, PAL/NTSC, SRAM/supported EEPROM, quick states and Menacer |
| Super Nintendo | Supported standard cartridges; LoROM/HiROM, PAL/NTSC, quick states, battery saves and Super Scope |
| Neo Geo | Supported cartridge profile; arcade MVS, optional console AES, two players, scores, memory card and quick states |

Compatibility depends on the game and revision. See the
[compatibility guide](docs/COMPATIBILITY.md) and
[16-bit support](docs/CONSOLES_16BIT.md) for the current limits.
The 16-bit profiles analyze new games automatically; there is no fixed game list.
The standard Mega Drive and Super Nintendo profiles are supported within their
documented cartridge scope. Qualified SNES DSP-1/CX4 boards are also supported;
CX4 device interpretation remains visible. Other enhancement chips require
separate integration.
**Neo Geo leaves experimental status in 1.0.2**, following further gameplay tests.
Select your BIOS ZIP in **Options → Neo Geo**, then add cartridge ZIPs or NEO
files using Automatic detection. See the [Neo Geo guide](docs/NEOGEO.md).
Its exports remember scores and memory-card data at clean exit, alongside F8/F9.

## Beyond the original console limits

- **Master System — fewer flickering sprites.** F5 enables extra sprites and
  stabilizes rapid sprite-order changes to reduce flicker during busy scenes.
- **Neo Geo — enhanced mode on by default.** More 68000 CPU capacity and a higher
  sprite limit help reduce slowdowns in busy scenes. F5 returns to original limits.
- **Neo Geo — arcade or home console.** F11 switches MVS/AES with a clean restart
  when the supplied BIOS archive includes the supported AES firmware. Each mode
  keeps its own saves and fallback hints.

These optional enhancements change the original machine's limits. Their effects
depend on the game; they do not guarantee that every slowdown or visual issue disappears.

## From conversion to your game collection

![RetroRecomp converter](MEDIAS/RetroRecomp_UI.png?v=3f29b62f5679)

*The refreshed charcoal-and-gold interface keeps mixed-console batches, options and updates together.*

## Get started

1. Download **Retro-Recomp.exe** from the [latest release](https://github.com/ArthurReboulSalze/RetroRecomp/releases).
2. Add your ROMs or folders, leave console detection on **Automatic**, and convert.
3. Open the generated games in their console folders under **Games** beside the app.

Conversion needs a supported build toolchain; see the
[setup guide](docs/BUILDING.md). Playing the exported games needs no development tools.
ROMs and downloaded box art are not included.

Use **Options** for conversion settings and **Check for updates** when you want
a newer version. Update checks are manual. Updating the converter preserves
your games and settings; regenerate games to receive new runtime features.
Downloaded artwork stays in `datas/BoxArt` beside the converter, sorted by console.

In games, **H** shows help, **F2** configures controls, **F3** changes filters and
**F4** cycles fullscreen modes. **F8/F9** save/load quick states, including the
qualified Mega Drive and Super Nintendo profiles. See [all controls](docs/CONTROLS.md).

## Compatibility and credits

Interpreter fallback is reported when needed. Native coverage, CPU agreement,
hardware fidelity, gameplay testing and physical latency are separate measures;
native execution alone does not guarantee complete compatibility or zero latency.
Detailed checks and ongoing work live in the
[documentation](docs/COMPATIBILITY.md) and [roadmap](docs/ROADMAP.md).

Created and integrated by [Arthur Reboul Salze](https://github.com/ArthurReboulSalze).
The app's **Credits** page links the independent projects behind each console.

Original RetroRecomp contributions use the [MIT license](LICENSE). Imported
components retain their own terms, including noncommercial restrictions;
MIT does not override them. See [third-party notices](THIRD_PARTY_NOTICES.md).
Notices are embedded in the EXE; the matching
[UPX source archive](licenses/upx-5.2.1-src.tar.xz) is available in this repository.

Feedback and contributions are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md).
