<p align="center">
  <img src="MEDIAS/RetroRecomp_ban.png" alt="RetroRecomp — from retro cartridges to native executables" width="900">
</p>

<h1 align="center">RetroRecomp</h1>
<p align="center"><strong>Less emulation. No FPGA. As native as possible.</strong></p>
<p align="center">Turn your own retro game ROMs into standalone executables.<br>
Compile ahead of time. Learn from new execution paths. Regenerate better builds.</p>

<p align="center">
  <img src="https://img.shields.io/badge/version-0.10.4-0879fa" alt="Version 0.10.4">
  <img src="https://img.shields.io/badge/current_system-Master_System-26d7ff" alt="Master System">
  <img src="https://img.shields.io/badge/current_platform-Windows_x64-0879fa" alt="Windows x64">
  <img src="https://img.shields.io/badge/original_code-MIT-aa66ff" alt="Original contributions: MIT">
</p>

<p align="center">
  <a href="https://github.com/ArthurReboulSalze/RetroRecomp/releases">Releases</a> ·
  <a href="docs/BUILDING.md">Build from source</a> ·
  <a href="docs/ROADMAP.md">Roadmap</a> ·
  <a href="THIRD_PARTY_NOTICES.md">Credits and licensing</a>
</p>

## The idea

RetroRecomp converts the Z80 program inside a Sega Master System ROM into C,
then compiles it into a Windows executable. The resulting game contains its
own ROM data and runtime, so playing it does not require Python, a separate
ROM file, or an external SDL2 DLL.

The goal is to run as much of the game's CPU program as possible as native
host code, while keeping the original game's behavior. Video, sound, memory,
inputs, bank switching and interrupts are still reproduced by a hardware
runtime. **This is static CPU recompilation with a hardware runtime and a
reported fallback interpreter.** It is not a claim of entirely eliminating
emulation, perfect fidelity, or zero physical latency.

### Compile more. Discover less at runtime.

Extended native coverage is enabled by default. It prepares supported
instruction positions across ROM banks before play, so indirect jumps and
bank changes can reach precompiled code. Unknown or changed RAM code can
still require the reference interpreter; its use is counted and reported.

### Each generation can improve the next

Execution discoveries are saved locally against the game's identity. A later
conversion verifies those observations against the ROM, compiles additional
RAM instruction variants with byte guards, and checks the candidate build
before replacing the previous executable. An unknown variant remains a
reported fallback rather than being treated as known code.

This memory is a compilation library, not an AI model. An optional local AI
player to explore more paths is a future research direction; it is not part
of the current release. See [the architecture](docs/ARCHITECTURE.md).

## Available today

| Capability | Current release |
| --- | --- |
| Game system | Sega Master System, Sega mapper |
| Output | Standalone Windows x64 game executable |
| Conversion | Single ROM or batch; extended coverage enabled by default |
| Improvement | Verified observations and guarded RAM variants reused on regeneration |
| Interface | English and French, with contextual help and conversion log |
| Inputs | Two players, separate keyboard mappings, Xbox/XInput-style gamepads |
| Presentation | Integer-scaled fullscreen, sharp pixels, bilinear, Scale2x, scanlines |
| Game icons | Optional local box art, with optional online lookup |
| Files | Shared `datas` folder; game-specific data isolated by identity |
| Regeneration | Same game filename; replacement deferred if the executable is running |

**No ROMs, commercial game executables, box art, screenshots of games or
personal compilation libraries are distributed in this repository or release.**
Use your own ROMs and artwork that you are entitled to use. Generated game
executables embed the ROM and must not be treated as redistributable merely
because RetroRecomp generated them.

## Getting started on Windows

1. Download and extract the Windows x64 ZIP from [Releases](https://github.com/ArthurReboulSalze/RetroRecomp/releases).
2. Install Git and Visual Studio Build Tools with **Desktop development with C++**, including x64 tools, CMake and a Windows SDK. Python is unnecessary for the packaged converter.
3. Run `Retro-Recomp.exe`, choose **Add ROMs** or **Add folder**, then **Convert / regenerate**.
4. Select a successful result and choose **Play game**.

The first conversion downloads pinned build dependencies and compiles them.
Internet access is required for that setup. Afterward, cached dependencies can
be reused; missing-cover downloads are optional. No ROM is uploaded by the
cover lookup: it uses the game title.

```text
RetroRecomp/
  Retro-Recomp.exe
  LICENSE
  THIRD_PARTY_NOTICES.md
  licenses/
  datas/                         created locally when needed
  Games/
    Master System/
      Your game.exe              created from your own ROM
      datas/                     shared controls, per-game memory and reports
```

The release starts clean: it contains no saved settings, games or learned
observations. Files are resolved relative to the application and games,
including when launched from a different working directory.

### Game shortcuts

| Key | Action |
| --- | --- |
| F1 | Restart |
| F2 | Configure keyboard/gamepad mappings, including Start/Menu and J1 Select/Reset |
| F3 | Next filter |
| F4 | Fullscreen/window |
| F6 | English/French |
| H | Help |
| P / Enter | Pause/resume; Enter retains its binding role inside F2 |
| Esc | Close the current menu, then quit |

Gamepad Start/Menu pauses by default. Select/Back restarts for player 1 only;
player 2 cannot reset. Fullscreen keeps interpreter diagnostics out of the
game image, while counters and logs remain available. There are no save states
in this release. See [controls](docs/CONTROLS.md).

## What has been verified

The measurements are deliberately separate:

| Area | Evidence and limit |
| --- | --- |
| Native execution | Five locally supplied games passed two 3,600-frame scenarios each with zero fallback cycles on those scenarios. This is not full-game coverage. |
| CPU fidelity | The native CPU changes were checked against 51,328 cases from a pinned independent Z80 vector corpus at version 0.10.0. These CPU checks were not rerun for the 0.10.4 UI changes. |
| Reference comparison | Current conversion checks compare CPU, RAM, final image and VDP traces with the corrected reference CPU. Both paths share the same hardware runtime. |
| Hardware fidelity | Complete console fidelity has not been established. |
| Gameplay | Full playthroughs and physical two-controller sessions have not been established. |
| Physical latency | Not measured; no zero-latency guarantee. |

Version 0.10.4 also passed 43 application tests, five publication privacy checks,
and native SDL checks with two virtual
controllers, including 4,096 simultaneous input states, remapping, pause,
restart and fullscreen. Validation files and game captures stay local; they
are not bundled with this public repository.

See [compatibility and limitations](docs/COMPATIBILITY.md) before assuming
a game, mapper or platform is supported.

## Where we want to go

RetroRecomp is designed to grow beyond the Master System. Future work includes
additional consoles and native outputs for **Linux, macOS and Android**.
Game Gear and other retro consoles are candidates; Neo Geo AES/MVS and Amiga
A1200/AGA are longer-term research directions.

These are roadmap goals, **not available platforms or compatibility promises**.
New processors, graphics/audio hardware, build toolchains and validation are
required. There is no announced delivery date. [Explore the roadmap](docs/ROADMAP.md).

## Development and credits

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
Third-party material retains its own terms. The pinned upstream engine states
that its license is not yet declared; the shared Z80 core uses PolyForm
Noncommercial 1.0.0. MIT does not override those terms or grant rights to ROMs
or artwork. See [third-party notices and the outstanding licensing issue](THIRD_PARTY_NOTICES.md).

Contributions are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md), and do not
attach commercial ROMs, generated game binaries, copyrighted box art or private logs.
