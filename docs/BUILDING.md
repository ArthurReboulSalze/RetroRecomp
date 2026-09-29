# Build and run

## Windows x64 prerequisites

- Python 3.11 or newer for source usage (release built with 3.14.5).
- Git on PATH.
- Visual Studio Build Tools 2022 or a detected supported Visual Studio
  installation, with x64 C++ tools, CMake and Windows SDK.
- Internet for first-time dependency setup; optional for missing-cover lookup.

The packaged converter includes Python. Generated games include their runtime
and SDL2 and do not need a development environment to play.
The converter bundles UPX 5.2.1 and compacts each validated Windows game
executable before replacing the previous export. This applies to Master
System, Game Gear, Game Boy and NES; only newly generated games are affected.
The UPX license and packed-executable exception are in
[licenses/UPX.md](../licenses/UPX.md).

```powershell
python -m pip install -r requirements.txt
python RetroRecomp.py gui
python RetroRecomp.py setup
python RetroRecomp.py convert "ROMS/your-game.sms" --no-online-cover
python RetroRecomp.py convert "ROMS/your-game.gb" --no-online-cover
python RetroRecomp.py convert "ROMS/your-game.nes" --no-online-cover
python RetroRecomp.py batch --rom-dir ROMS --frames 3600 --passes 3 --no-online-cover
python RetroRecomp.py batch --rom-dir "D:/mixed-a" --rom-dir "D:/mixed-b" --system auto
```

`ROMS` is a local folder for your own ROMs; it is not committed. Source usage
exports to `Export`; build files and dependencies stay in `.build` and `.deps`.
The packaged converter creates `Games` beside its executable. Automatic
identification routes supported ROMs into `Master System`, `Game Gear`,
`Game Boy` or `Nintendo NES` subfolders; unknown formats are reported and skipped. `--output`
selects another Games root, and `--system sms|gg|gb|nes` resolves ambiguous
`.bin`/`.rom` dumps when their console is known to the user. The GUI offers
the same Automatic/manual console selector and an opt-in custom export folder.

Game Boy keeps its all-bank discovery and three coverage scenarios enabled.
Its default reference CPU check covers up to 30 boot frames. To add the much
slower instruction-by-instruction play comparisons, enable **Deep Game Boy
validation (slow)** in the GUI or pass `--gb-deep-validation` to `convert` or
`batch`. Allow several extra minutes per Game Boy game; other consoles ignore
this flag. The conversion log and report show timings and validation scope.

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
```

Python tests use temporary synthetic fixtures and require no commercial ROM.
Native CPU/input checks build authored diagnostic programs locally. Host
checks need an already converted game supplied by the tester:

```powershell
python tools/host_selftest.py --game "Your game title"
```

Some historical helpers target the locally tested titles and need those ROMs.
The GUI smoke helper checks a local queue of five supplied games. These checks
are not part of the ROM-free public CI; games and reports are not distributed.

## Package the converter

```powershell
python -m pip install "PyInstaller==6.22.3"
powershell -File tools/package.ps1
```

Packaging derives icon/banner resources from the two project branding images
and writes `Export/Retro-Recomp.exe`. `tools/prepare_publication.py` stages an
explicit list of public files, audits it and prepares a clean release ZIP.
It never pushes or uploads. See `--help` for source and release preparation.

```powershell
python tools/prepare_publication.py --stage .build/publication/repository
python tools/prepare_publication.py --staged
```

Build from that snapshot to keep private profiles and observations out of the
frozen converter. Then audit its decompressed assets and create the release:

```powershell
powershell -File .build/publication/repository/tools/package.ps1
python tools/prepare_publication.py --source .build/publication/repository --exe .build/publication/repository/Export/Retro-Recomp.exe --release Export/Releases/RetroRecomp-v0.14.1-windows-x64.zip
```

The ZIP contains only the converter and legal notices. Keep source staging and
release audit reports private. The publication tool checks an explicit allowlist
and common credential patterns; review the outgoing diff as well. Public CI
runs the same checks on all tracked files and ROM-free Python tests.
