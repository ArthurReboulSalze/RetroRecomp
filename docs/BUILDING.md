# Build and run

Prebuilt per-user installers are available for Windows and Linux; portable
downloads remain available. See [installation and installer builds](INSTALLING.md).

Release 1.1.6 retains portable collection paths and repairs older copied
inventories in a background task when opening Compiled Games. A complete scan
cleans confirmed missing entries. This is collection metadata only; existing
games need no regeneration. See [compiled games](COMPILED_GAMES.md).

## Collection data in 1.1.5

Both systems keep the collection, favorites, optional ROM folders, covers and
manually requested game summaries in private `datas` beside the converter.
These files are excluded from source snapshots and converter packages.
See [compiled games](COMPILED_GAMES.md) for locations and regeneration behavior.

## Credits music in converter packages

Both converter packaging scripts build a small native MOD player with CMake and
a C compiler. `python tools/build_credits_audio.py` downloads hash-verified,
pinned libxmp-lite and miniaudio sources; packaged users need no compiler or
separate audio player. Three original ChipLoom MODs and the player are embedded
in the converter, never in generated games. See [credits](CREDITS.md).

After building, `python tools/credits_selftest.py` checks the actual decoder and
percussion events; `--device` also checks playback, mute and shutdown.

## Linux x86-64

The first Linux package has bounded witnesses for all seven consoles on
Debian 13 x86-64: Master System, Game Gear, Game Boy, NES, Mega Drive, Super
Nintendo and Neo Geo. Native/reference checks, language persistence and selected
fresh-process state checks pass; this does not qualify every cartridge. This is
not an ARM64 qualification. Build and run on Linux itself;
WSL is unnecessary. Keep the
Linux source workspace and caches separate from Windows. A target marker rejects
reuse of caches belonging to another OS/architecture.

Install CMake, Ninja, pkg-config, a C/C++ toolchain, Python 3.11+ with Tk/venv/dev,
and development headers for X11/Wayland, ALSA/PulseAudio, udev, OpenGL, DRM/GBM and
DBus. The SDL2 source revision remains pinned and is built locally. Use a Python
virtual environment for `requirements.txt`: Debian 13's system Pillow 11 does
not satisfy the current Pillow >=12 requirement.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python RetroRecomp.py setup
.venv/bin/python RetroRecomp.py gui
.venv/bin/python RetroRecomp.py convert "/path/to/your-game.sms" --output Export/Games
```

The game is an executable ELF, with its ROM, SDL2, menu font and notices embedded.
It needs compatible Linux system/display/audio libraries, with no Python or
compiler required to play. Validated Linux x86-64 game ELFs, X68000 games
included, are packed with the bundled UPX 5.2.1, like Windows games (below).
The converter supports manual GitHub updates. `--credits` prints the game notices. Settings,
quick states and shutdown-only fallback hints use `datas` beside the game.
Source usage exports to `Export/Games/<console>`. Batch/GUI defaults are one
game and two compiler tasks on Linux; `RETRO_RECOMP_BUILD_JOBS` adjusts the latter.

During concurrent conversions, each game's compiler tasks are also capped by
its share of the CPUs available to the converter process. This includes Game
Boy; its reference-check budgets are unchanged. Up to eight conversions can
run together, but using fewer can be better on memory-constrained machines.

Release 1.1.3 adds interrupted-batch recovery. On reopening the
converter, unfinished rows are restored without reading their ROMs or starting
conversion automatically. Press Convert to resume, or Convert selected to process
only the chosen rows. Other recovered rows remain available after closing.
Remove/Clear retires them. Small checkpoint files stay in the converter's private
`datas/pending-batches`; they contain paths and progress, never ROM copies.

Linux games request VSync by default, keeping the console's clock limiter.
`SDL_RENDER_VSYNC=0` is an explicit diagnostic override. Window managers and
display drivers still determine physical presentation; a renderer flag alone
does not prove tear-free output. Menus draw plain ASCII with the public-domain
Misc Fixed 10x20 bitmap in 5 x 10 cells, scaled to the window by area coverage (6x10 at 1x);
games carry no glyph table. The converter uses process-private
font subsets; it does not install system fonts. See [languages](LANGUAGES.md).

Cover lookup and offline reuse share the Windows pipeline. Source usage caches
downloads in `Export/datas/BoxArt/<console>/Downloaded` and associations in `Saved`.
The game's window icon is embedded in the ELF. Linux file managers and app menus
use a `.desktop` launcher whose `Icon` references a PNG; the raw ELF does not have
a Windows Explorer-style file icon. Exports now create that launcher and a local
PNG in `datas/launchers`, with the raw ELF listed in `.hidden` for file managers.
Existing current exports can repair their launcher without recompilation. The
launcher uses absolute paths; ask the converter to refresh it after moving the
folder. Optional API credentials use the desktop Secret Service keyring;
public cover sources need no API account. See [LINUX.md](LINUX.md).

Useful target-native checks (an optional `--rom` is a private supplied witness):

```sh
.venv/bin/python -m unittest discover -s tests
.venv/bin/python tools/linux_sms_selftest.py --rom "/path/to/your-game.sms"
.venv/bin/python tools/runtime_feedback_selftest.py
.venv/bin/python tools/gamestate_selftest.py
.venv/bin/python tools/gamestate_selftest.py --pal
.venv/bin/python tools/frame_stop_selftest.py
.venv/bin/python tools/language_selftest.py
.venv/bin/python tools/nes_ppu_selftest.py
.venv/bin/python tools/nes_machine_selftest.py
.venv/bin/python tools/neogeo_board_selftest.py
```

The Linux prototype preserves the mandatory native/reference and strict checks.
Matching those checks does not establish full-game coverage, physical hardware
fidelity or measured controller/audio latency. The current development host is
Debian 13/glibc 2.41; older distributions require separate build/compatibility work.

## Windows x64 prerequisites

**Packaged converter:** before the first conversion, Retro-Recomp checks for
Git and a C/C++ compiler and offers to install what is missing, with a progress
window. Everything goes into `datas/tools` beside the converter, without
administrator rights: a portable MinGit (40 MB), and the build tools, pinned and
SHA-256-checked: llvm-mingw 20261006 (clang and lld with the MinGW-w64 headers
and `windres`, UCRT variant), CMake 4.4.4 and Ninja 1.13.2. The download is about
245 MB and 380 MB are installed once the unused parts (32-bit and ARM targets,
Python, debugger) are left out. Every console uses the same tools, and none needs
Rust any more (Super Mario World uses the generic SNES analysis since 1.4.1).
Games built this way need Windows 10 or later (UCRT). A Visual Studio Build Tools
installation stays a fallback: the converter uses it only when the portable tools
are absent, and `RETRO_RECOMP_TOOLCHAIN=llvm` or `msvc` forces one of the two
(the two never share a build folder; switching rebuilds). Source usage keeps the
list below.

- Python 3.11 or newer for source usage (release built with 3.14.5).
- Git on PATH.
- The portable build tools above (installed by the converter on first use) or
  Visual Studio Build Tools 2022 or a detected supported Visual Studio
  installation, with x64 C++ tools, CMake and Windows SDK.
- Internet for first-time dependency setup; optional for missing-cover lookup.

The packaged converter includes Python. Generated games include their runtime
and SDL2 and do not need a development environment to play.
The converter bundles UPX 5.2.1 and compacts each validated game executable
before replacing the previous export, then has UPX test it. On Windows
(`assets/tools/upx.exe`, `-9 --compress-resources=0 --compress-icons=0`) every
console is packed; resources stay readable. On Linux x86-64
(`assets/tools/upx-amd64_linux`, `-9`) every console is packed too, the X68000
included. Both
binaries are the unmodified official builds of the v5.2.1 release, checked by
SHA-256 before each use (`retrorecomp/packing.py`): the Linux one is `upx` from
`upx-5.2.1-amd64_linux.tar.xz` (archive
`402162aad30af47e60dbd767fb2e64ca394ace9727ba1f40283641f1d1b91657`, binary
`287b3dffe9dcafd8e366e162ac4ab41e5cf45a3c6768970256af0869288d84a1`). Each
converter carries only its own packer. Neo Geo and CPS-1 replay their routes
on the packed executable; the other consoles validate the build before packing.
UPX restores the same program in memory at start-up: Linux games still find
their folder through `/proc/self/exe`, and the Neo Geo MVS/AES switch re-runs
the same file. No game reads its own file: an X68000 game's disks, IPL and font
ROM are linked into the program (`retrorecomp/resources.py`), restored by UPX
with the rest and copied from memory to `datas/games/x68-<identity>`; on Windows
they are PE resources, read from memory too. A Linux ELF packs its marker with
the rest of the program, so a Linux game moved without its `datas/reports` is no longer recognized by its
content (like Master System, Game Gear and Game Boy games on Windows); it is
then kept, never overwritten. Packing is a build input: changing it rebuilds
exports without rediscovery ([compilation library](COMPILATION_LIBRARY.md)).
A NeoGeo BIOS selected by the user is required for Neo Geo; it is not downloaded.
The UPX license and packed-executable exception are in
[licenses/UPX.md](../licenses/UPX.md).

### Linux game compression

Measured on the Debian 13 build machine (4 cores), one game per console, quick
scan level, 25 October 2026. Each game was converted by the commit before this
change (uncompressed) and again by this change (compressed, full conversion).
`upx -d` of every compressed game gives back, byte for byte, the uncompressed
export of the earlier commit, except the NES one: 136 bytes differ, a 64-digit
key and the ELF build ID, because the NES state key covers the project folder,
which differed between the two source trees. Start-up is the time from
launch to the first visible window under Xvfb, median of 7 runs with a warm
file cache; it includes SDL start-up and is not a latency measurement.

| Console | Game | Uncompressed | Compressed | Ratio | Start-up, uncompressed → compressed |
| --- | --- | ---: | ---: | ---: | ---: |
| Master System | Alex Kidd in Miracle World | 5,954,280 | 1,890,160 | 0.32 | 235 → 208 ms |
| Game Gear | Sonic The Hedgehog | 8,401,680 | 2,637,684 | 0.31 | 223 → 207 ms |
| Game Boy | Tetris | 6,326,048 | 1,775,320 | 0.28 | 512 → 506 ms |
| NES | Super Mario Bros. | 10,177,128 | 3,278,740 | 0.32 | 198 → 231 ms |
| Mega Drive | Sonic The Hedgehog | 12,560,192 | 3,555,956 | 0.28 | 414 → 531 ms |
| Super Nintendo | ActRaiser | 36,434,712 | 7,469,468 | 0.21 | 211 → 274 ms |
| Neo Geo (MVS) | 2020 Super Baseball | 21,829,440 | 7,413,940 | 0.34 | 196 → 265 ms |
| CPS-1 | 1941: Counter Attack | 17,560,992 | 4,975,132 | 0.28 | 211 → 294 ms |
| X68000 | Active Shoot | 14,836,976 | 3,756,180 | 0.25 | 121 → 170 ms |
| X68000 | Alien Syndrome | 11,534,544 | 3,307,136 | 0.29 | 115 → 160 ms |

Separately for every game: native validation passed before and after, with
zero interpreted instructions both times (main and audio CPUs); `upx -t`
passes; the compressed game keeps its execute bit and its `.desktop` launcher
is unchanged; it was still running after 10 s under `xvfb-run`. Quick states
between the uncompressed and compressed builds of the same game: a state saved
by one resumes in the other with identical per-frame traces and the same state
size, both ways (`tools/state16_cross.py` for Mega Drive and Super Nintendo,
`tools/neogeo_state_cross.py` for Neo Geo and CPS-1, `tools/nes_state_cross.py`,
`tools/x68000_cross.py --same-compiler` for X68000).
Master System, Game Gear and Game Boy were checked only through their window
(F8 in the earlier build, then F9 and F8 in the compressed one): the state file
has the same size and the game keeps running; the restored frame was not
compared. The Neo Geo AES restart could not be exercised (no AES BIOS in the
test archive); a packed test program re-running `/proc/self/exe` works. CPU
fidelity, hardware fidelity, gameplay and physical latency are not measured by
these checks.

The X68000 rows were measured afterwards on the same machine and day: the
uncompressed export by the commit that still left X68000 games as built, the
compressed one by the commit that packs them. `upx -d` of each compressed game
gives back that uncompressed export byte for byte. The headless X68000 state
check used the converter's input route, with a state saved at frame 3,200 and
resumed for 400 frames, and one saved during boot (frame 120) and resumed for
40. X68000 quick states were also exercised through the window, with XTest keys
under Xvfb: F8 in the uncompressed export, then the compressed one, published
over it, loaded that state with F9 (none rejected) and saved again with F8,
same state size. The X68000 start-up times come from a separate probe with the
same definition (median of 7 launches, alternated between the two builds after
one warm-up each; a second pass gave 116 → 168 and 113 → 161 ms): compare them
within a row. Resident memory 13 s after launch differed by less than 4 MB.

```powershell
python -m pip install -r requirements.txt
python RetroRecomp.py gui
python RetroRecomp.py setup
python RetroRecomp.py convert "ROMS/your-game.sms" --no-online-cover
python RetroRecomp.py convert "ROMS/your-game.gb" --no-online-cover
python RetroRecomp.py convert "ROMS/your-game.nes" --no-online-cover
python RetroRecomp.py convert "ROMS/nam1975.zip" --ng-bios "D:/your-bios/neogeo.zip"
python RetroRecomp.py batch --rom-dir ROMS --frames 3600 --passes 3 --jobs 8 --no-online-cover
python RetroRecomp.py batch --rom-dir "D:/mixed-a" --rom-dir "D:/mixed-b" --system auto
python RetroRecomp.py batch --rom-dir ROMS --no-overwrite
```

`ROMS` is a local folder for your own ROMs; it is not committed. Source usage
exports to `Export`; build files and dependencies stay in `.build` and `.deps`.
The packaged converter creates `Games` beside its executable. Automatic
identification routes supported ROMs into `Master System`, `Game Gear`,
`Game Boy`, `Nintendo NES`, `Mega Drive`, `Super Nintendo` or `Neo Geo` subfolders;
unknown formats are reported and skipped. `--output`
selects another Games root, and `--system sms|gg|gb|nes|md|snes` resolves ambiguous
`.bin`/`.rom` dumps when their console is known to the user. The GUI offers
the same Automatic/manual console selector and an opt-in custom export folder.
The supported Neo Geo `ng` profile also detects multi-region cartridge ZIPs and `.neo`
containers. In **Options → Neo Geo**, select a BIOS ZIP and use **Check BIOS**.
The current MVS Europe scope verifies `sp-s2.sp1`, `sfix.sfix`, `sm1.sm1` and
`000-lo.lo` by size, CRC and selected-component SHA identity. Paths inside the
converter folder are saved relatively; external paths are remembered explicitly.
The CLI accepts `--system ng` and `--ng-bios` for single games or mixed batches.
No BIOS or cartridge is bundled in the converter. Locally generated Neo Geo
games embed the selected data and need no separate BIOS file to play.
Optional verified `neo-epo.bin` enables console AES on F11 for compatible
cartridges; no extra firmware means MVS-only output. Switching restarts the game
and isolates saves by mode. Arcade-only cartridges instead show "Arcade Only"
without restarting; conversion retains their mandatory MVS checks.

Batch conversion keeps current exports when their converter/runtime fingerprint,
ROM, options, manual cover, selected BIOS and imported fallback candidates match
the successful export receipt and the EXE's SHA-256. Missing or older receipts
regenerate conservatively. **Convert selected** limits work to selected rows.
**Options → General → Force regeneration** overrides freshness checks; disabling
overwrite still protects existing games. New unsupported hints are attempted
once per changed set, not repeatedly for an identical file.
Merged ZIP revisions are selected only through matching program/component
CRCs; an unresolved revision is reported, never guessed from a different game.
Batch conversion runs three games at once by default for any mix of supported
consoles. Set **Concurrent games** in the GUI or use `batch --jobs 1..8` to
control CPU and memory use. `--jobs 1` runs sequentially. Stopping waits for
already active games and leaves the rest of the queue untouched.
**Overwrite existing games** is enabled by default; disable it to keep already
exported games when running a large batch. Distinct ROM bytes with the same
base title receive region/revision labels from filenames when available, or
version A/B labels. Identical ROM bytes under different names are reported
with the existing name and are not exported as a different game.

Game Boy keeps its all-bank discovery and four coverage scenarios enabled
(boot, left/right play and varied input for tests of at least 750 frames).
**Deep Game Boy validation (slow)** is now on by default: it adds three longer
instruction-by-instruction play comparisons, including varied input, to the
mandatory boot CPU check.
For a faster standard validation, uncheck it under Options → Game Boy or pass
`--no-gb-deep-validation` to `convert` or `batch`. Native discovery is the same
in both modes; other consoles ignore this setting. The conversion log and
report show timings and validation scope.

Game Boy's optimized C generation and reuse of byte-identical generated files
reduce build work without changing native discovery or the CPU comparisons.
An initial conversion still compiles new code; repeat-build timings should not
be presented as cold-build timings. See [Game Boy build evidence](GAME_BOY.md).

## Build folders

Each conversion builds its game in a project folder of its own under `.build`
beside the converter (the project root from source, the converter's folder
when packaged): generated C, object files, the raw executable and validation
runs, about 25 to 110 MB for an 8-bit game and more for 16-bit and arcade games.
Since 1.5.1 that folder is removed once the game is published in the games
folder; a failed or stopped conversion keeps it, as its messages point into
it. Shared caches stay: `.deps`, `.build/native-source`, the NES and Mega Drive
compilers and step decoders, `neogeo-preparation`, `cps1-reference` and the
X68000 SDK bases. Learned paths live in the library under `datas`, so a later
upgrade or reconversion needs nothing from the removed folder; it only rebuilds
from scratch, without the incremental build an earlier folder allowed.
**Options › Common › Disk space** measures the folders left by earlier versions
or by failed and stopped conversions, and removes them after a confirmation.
Only folders named like one game's project are counted (per console, by the
ROM identity in the name); links are not followed, and a folder used within the
last hour, or locked by a running CPS-1 or X68000 conversion, is kept.
`--keep-build` on `convert` and `batch` (or `RETRO_RECOMP_KEEP_BUILD=1`) keeps
the folder for the developer checks below.

## Pinned game dependencies

| Dependency | Revision |
| --- | --- |
| smsggrecomp | `224d5bb2c150a2c295033d35dec629ef9ee42940` |
| SDL2 | `98d1f3a45aae568ccd6ed5fec179330f47d4d356` |
| gb-recompiled (original Game Boy) | `9150f87d82fa98abcb6ea22329170463f9702eb8` |
| nesrecomp (NES; noncommercial license) | `1b0c621a927db17afa9723bf456a89ad15809907` |
| Independent SingleStepTests/Z80 corpus | `ebe1875d48f374bcfd4b505d8eb8ee751568b5f7` |

The converter checks revisions and applies adaptations to generated copies.
It does not edit the pinned checkouts. Dependencies are downloaded at setup,
not vendored in the release. Read [the licensing notices](../THIRD_PARTY_NOTICES.md)
before redistributing a toolchain or generated game.

## Checks

```powershell
python -m unittest discover -s tests
python tools/player2_selftest.py
python tools/banked_vector_selftest.py
python tools/gameboy_latency_selftest.py
python tools/gameboy_ram_selftest.py
python tools/megadrive_native_selftest.py
python tools/snes_native_selftest.py
```

Python tests use temporary synthetic fixtures and require no commercial ROM.
Native CPU/input checks build authored diagnostic programs locally. Host
checks need an already converted game supplied by the tester, converted with
`--keep-build` so that its build folder is still there:

```powershell
python RetroRecomp.py batch "ROMS/your-game.sms" --keep-build
python tools/host_selftest.py --game "Your game title"
```

The same applies to every helper that reads a report's `build_directory`
(`icon_selftest`, `banked_cpu_selftest`, `sms_sprite_selftest`,
`video_selftest`, `banked_verify`, `neogeo_campaign_review`) and to
`build_neogeo_knowledge.py`, which refuses a removed Neo Geo build folder.
`RETRO_RECOMP_KEEP_BUILD=1` does the same for scripts; `publishing_selftest`
sets it.

Some historical helpers target the locally tested titles and need those ROMs.
The GUI smoke helper checks a local queue of five supplied games. These checks
are not part of the ROM-free public CI; games and reports are not distributed.

## Package the converter

For the native Debian 13 x86-64 preview, see [LINUX.md](LINUX.md) and run
`python tools/package_linux.py` on Linux. It produces `Export/Retro-Recomp`,
a local icon launcher, and an audited tarball. Windows packaging stays separate;
neither build is a cross-compiler. Linux requirements include the pinned
tkinterdnd2 and SecretStorage dependencies in `requirements.txt`.

For ROM-free numeric Sega audio checks, including an optional silent run on
the default sound device, see [AUDIO.md](AUDIO.md).

```powershell
python -m pip install "PyInstaller==6.22.3"
powershell -File tools/package.ps1
```

Packaging derives icon/banner resources from the two project branding images
and writes `Export/Retro-Recomp.exe`. `tools/prepare_publication.py` stages an
explicit list of public files, audits it and prepares a standalone release EXE.
It never pushes or uploads. See `--help` for source and release preparation.

After qualifying new cartridge cases, refresh the ROM-free compressed hint
snapshot before packaging. The snapshot is included in the converter and
combines with the user's local observations; validation remains mandatory.
See the [compilation library workflow](COMPILATION_LIBRARY.md), including how
to disable local and bundled hints for a cold timing comparison.

```powershell
python tools/prepare_publication.py --stage .build/publication/repository
python tools/prepare_publication.py --staged
```

Build from that snapshot to keep private profiles and observations out of the
frozen converter. Then audit its decompressed assets and create the release:

```powershell
powershell -File .build/publication/repository/tools/package.ps1
python tools/prepare_publication.py --source .build/publication/repository --exe .build/publication/repository/Export/Retro-Recomp.exe --standalone Export/Releases/Retro-Recomp.exe
```

The EXE contains the converter and its legal notices. The matching
[UPX 5.2.1 source archive](https://github.com/ArthurReboulSalze/RetroRecomp/blob/e522cbde7ca6e7e6eccc0c901389a4178492e6d7/licenses/upx-5.2.1-src.tar.xz)
stays in the public repository. Link it clearly beside the EXE on every
download page. No loose license files are needed beside the local EXE.
Keep source staging and
release audit reports private. The publication tool checks an explicit allowlist
and common credential patterns; review the outgoing diff as well. Public CI
runs the same checks on all tracked files and ROM-free Python tests.
