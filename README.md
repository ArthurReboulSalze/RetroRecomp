<p align="center">
  <img src="MEDIAS/RetroRecomp_ban.png" alt="RetroRecomp — multiconsole game recompilation" width="900">
</p>

<h1 align="center">RetroRecomp</h1>
<p align="center"><strong>Six retro consoles. One app. Your games, ready to launch.</strong></p>
<p align="center">Master System · Game Gear · Game Boy · NES · Mega Drive · Super Nintendo</p>
<p align="center"><em>Less emulation. No FPGA. As native as possible.</em></p>

<p align="center">
  <img src="https://img.shields.io/badge/release-0.22.0-0879fa" alt="Release version 0.22.0">
  <img src="https://img.shields.io/badge/console_profiles-6-26d7ff" alt="Six console profiles">
  <img src="https://img.shields.io/badge/current_platform-Windows_x64-0879fa" alt="Windows x64">
  <img src="https://img.shields.io/badge/original_code-MIT-aa66ff" alt="Original contributions: MIT">
</p>

<p align="center">
  <a href="https://github.com/ArthurReboulSalze/RetroRecomp/releases">Download</a> ·
  <a href="docs/BUILDING.md">Build from source</a> ·
  <a href="docs/COMPATIBILITY.md">Compatibility</a> ·
  <a href="THIRD_PARTY_NOTICES.md">Credits and licensing</a>
</p>

## One converter, multiple consoles

RetroRecomp brings several recompilers together in one application. It prepares
game code before you play and creates a compact, standalone Windows executable
for each game. The goal is a simple, responsive experience with as much native
execution as possible, without dedicated FPGA hardware.

- **Convert a whole collection.** Add individual ROMs or mixed folders. Recognized
  games are sorted by console, and multiple conversions can run together.
- **Launch directly.** Generated games need no Python installation, separate ROM
  file or external SDL2 DLL. Regeneration can replace existing exports.
- **Keep familiar controls.** Shared menus, keyboard/gamepad mapping, fullscreen
  modes and lightweight filters keep the experience consistent across consoles.
  Your display mode and filter are remembered; F8/F9 quick states resume after closing the game.
- **Make games easy to find.** Optional box-art icons and shooting tags distinguish
  your exports. Mouse aiming is available for supported lightgun games.
  Downloaded artwork is saved and reused when you regenerate games.
- **Reuse compilation knowledge.** The converter includes useful cartridge
  hints and keeps new discoveries locally. See the
  [shared library guide](docs/COMPILATION_LIBRARY.md).

## Console support

| Console | Current status |
| --- | --- |
| Master System | Supported; two players, PAL/NTSC, quick states and Light Phaser |
| Game Gear | Supported; native handheld display and colors |
| Game Boy | Supported; original Game Boy, quick states, grayscale or classic green |
| NES | Supported; validated cartridge layouts, PAL/NTSC, quick states and Zapper |
| Mega Drive | Experimental; 27 qualified revisions, NTSC and selected PAL games, quick states and Menacer |
| Super Nintendo | Experimental; 12 qualified revisions, NTSC and initial PAL support, quick states and Super Scope |

Compatibility depends on the game and revision. See the
[compatibility guide](docs/COMPATIBILITY.md) and
[16-bit support](docs/CONSOLES_16BIT.md) for the current limits.
More consoles and output platforms are planned.

## From conversion to your game collection

![RetroRecomp converter](MEDIAS/RetroRecomp_UI.png)

*One interface for mixed-console batches, options and updates.*

![Standalone game executables in Windows Explorer](MEDIAS/RC_Windows_Screen.png)

*Launch games directly from Windows Explorer, with optional box-art icons and lightgun tags.*

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
