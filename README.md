<h1 align="center">
  <img src="MEDIAS/RetroRecomp_cartridge_rr.png?v=6c27780690cc" alt="RetroRecomp: the RR cartridge" width="240"><br>
  RetroRecomp
</h1>
<p align="center"><strong>Retro consoles and classic computers. One growing project.</strong></p>
<p align="center">Master System · Game Gear · Game Boy · NES · Mega Drive · Super Nintendo · Neo Geo · Capcom CPS-1 · Sharp X68000</p>
<p align="center"><em>Less emulation. No FPGA. As native as possible.</em></p>

<p align="center">
  <img src="https://img.shields.io/badge/release-1.6.4-d4a737" alt="Release version 1.6.4">
  <img src="https://img.shields.io/badge/console_profiles-9-626262" alt="Nine console profiles, including the experimental Capcom CPS-1 and Sharp X68000">
  <img src="https://img.shields.io/badge/platforms-Windows_x64_%7C_Linux_x86--64-343434" alt="Windows x64 and Linux x86-64">
  <img src="https://img.shields.io/badge/original_code-MIT-d4a737" alt="Original contributions: MIT">
</p>

<p align="center">
  <a href="https://github.com/ArthurReboulSalze/RetroRecomp/releases">Download</a> ·
  <a href="docs/BUILDING.md">Build from source</a> ·
  <a href="docs/COMPATIBILITY.md">Compatibility</a> ·
  <a href="docs/RELEASE_NOTES.md">What's new</a> ·
  <a href="THIRD_PARTY_NOTICES.md">Credits and licensing</a> ·
  <a href="https://retro-recomp.com">Website</a>
</p>

https://github.com/user-attachments/assets/818d3278-d698-491e-a58b-e11edc602923

<p align="center"><sub><em>RetroRecomp in under two minutes: how your own game dumps become native Windows and Linux programs.</em></sub></p>

https://github.com/user-attachments/assets/ac2dff32-b23c-44a4-ab81-ef962833251d

<p align="center"><sub><em>Under the hood, in under three minutes: how RetroRecomp is built and how it works.</em></sub></p>

<p align="center">
  <img src="MEDIAS/RetroRecomp_Collection_fr.png" alt="Compiled Games collection in French, with scan-level stars, box art and a game summary, demo collection" width="860">
</p>
<p align="center"><sub><em>Compiled Games, in French: favorites, scan-level stars, covers, summaries and New paths.</em></sub></p>

RetroRecomp brings several recompilers together in one application. It turns
your own game dumps into standalone Windows or Linux executables, with as much
native code as possible: no emulator to configure, no dedicated FPGA hardware.

## Install in 3 steps

1. **Download.** Open the
   [latest release](https://github.com/ArthurReboulSalze/RetroRecomp/releases/latest) and take
   the file for your computer: `Retro-Recomp-<version>-windows-x64-setup.exe` on Windows,
   `retro-recomp_<version>_amd64.deb` on Debian or Ubuntu (double-click it), or
   `Retro-Recomp-<version>-linux-x86_64-install.run` on another 64-bit Linux. Windows may say
   *unknown publisher* because the installer is not signed with a paid certificate: choose
   **More info → Run anyway** (it is not a virus alert, see
   [Windows security warnings](docs/INSTALLING.md#windows-security-warnings)).
2. **Add your ROMs.** Start Retro-Recomp, drop your own ROM files, ZIPs, arcade romsets, disk
   images or whole folders on the window, and leave the console on **Automatic**. ROMs and box
   art are never included.
3. **Convert and play.** Press Convert. The first time, Retro-Recomp offers to install the build
   tools it needs; accept. Your games appear in one folder per console under **Games**, beside
   the application, and in the **Compiled Games** window.

The full guide, with portable downloads, updates and uninstalling, is
[docs/INSTALLING.md](docs/INSTALLING.md); the keys of every game are in
[docs/CONTROLS.md](docs/CONTROLS.md).

## Console support

| Machine | Status | What is converted |
| --- | --- | --- |
| [Master System](docs/MASTER_SYSTEM.md) | Supported | Two players, PAL/NTSC, quick states and Light Phaser |
| [Game Gear](docs/GAME_GEAR.md) | Supported | Native handheld display and colors |
| [Game Boy](docs/GAME_BOY.md) | Supported | Original Game Boy, quick states, grayscale or classic green |
| [NES](docs/NES.md) | Supported | Validated cartridge layouts, PAL/NTSC, quick states and Zapper |
| [Mega Drive](docs/MEGADRIVE.md) | Supported | Standard cartridges, PAL/NTSC, SRAM and EEPROM saves, quick states and Menacer |
| [Super Nintendo](docs/SNES.md) | Supported | Standard cartridges, LoROM/HiROM, PAL/NTSC, quick states, battery saves and Super Scope |
| [Neo Geo](docs/NEOGEO.md) | Supported | Cartridge games: arcade MVS, optional console AES, two players, scores, memory card and quick states; needs your BIOS ZIP in **Options → Neo Geo** |
| [Capcom CPS-1](docs/CPS1.md) | Experimental | MAME/FBNeo ZIP romsets of the standard boards (no QSound), up to four players and six buttons, DIP switches, vertical games rotated, quick states; no BIOS, and a split clone needs its parent ZIP beside it |
| [Sharp X68000](docs/X68000.md) | Experimental | DIM/XDF disks and multi-disk sets, quick states, mouse and keyboard; needs your own IPL and font ROM |

Compatibility depends on the game and the revision; there is no fixed game list. See the
[compatibility guide](docs/COMPATIBILITY.md). Interpreter fallback is always reported: native
code, CPU fidelity, hardware fidelity, gameplay validation and physical latency are separate
measures, and native execution alone guarantees neither complete compatibility nor zero latency.

## Learn more

How it works, what each machine does and how the project is run: start from the
[documentation index](docs/INDEX.md). The windows of the converter are in the
[screenshots](docs/SCREENSHOTS.md), each release's changes in the
[release notes](docs/RELEASE_NOTES.md), and the machines planned next in the
[roadmap](docs/ROADMAP.md).

## For developers

- [docs/BUILDING.md](docs/BUILDING.md): build and run from source, and the dependencies.
- [CONTRIBUTING.md](CONTRIBUTING.md): how to propose a change.
- [docs/AGENTS_GUIDE.md](docs/AGENTS_GUIDE.md): the repository map, the checks that need no ROM and the pitfalls, for coding agents and people alike.
- [docs/STANDARDS.md](docs/STANDARDS.md): the rules every change follows.

## Credits and licence

Created and integrated by [Arthur Reboul Salze](https://github.com/ArthurReboulSalze).
The app's **Credits** page links the independent projects behind each console.

Original RetroRecomp contributions use the [MIT license](LICENSE). Imported
components retain their own terms, including noncommercial restrictions;
MIT does not override them. See [third-party notices](THIRD_PARTY_NOTICES.md).
Notices are embedded in the converter; the matching
[UPX source archive](licenses/upx-5.3.0-src.tar.xz) is available in this repository.
