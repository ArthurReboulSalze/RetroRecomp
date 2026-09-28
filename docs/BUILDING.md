# Build and run

## Windows x64 prerequisites

- Python 3.11 or newer for source usage (release built with 3.14.5).
- Git on PATH.
- Visual Studio Build Tools 2022 or a detected supported Visual Studio
  installation, with x64 C++ tools, CMake and Windows SDK.
- Internet for first-time dependency setup; optional for missing-cover lookup.

The packaged converter includes Python. Generated games include their runtime
and SDL2 and do not need a development environment to play.

```powershell
python -m pip install -r requirements.txt
python RetroRecomp.py gui
python RetroRecomp.py setup
python RetroRecomp.py convert "ROMS/your-game.sms" --no-online-cover
python RetroRecomp.py batch --rom-dir ROMS --frames 3600 --passes 3 --no-online-cover
```

`ROMS` is a local folder for your own ROMs; it is not committed. Source usage
exports to `Export`; build files and dependencies stay in `.build` and `.deps`.
The packaged converter creates `Games/Master System` beside its executable.

## Pinned game dependencies

| Dependency | Revision |
| --- | --- |
| smsggrecomp | `224d5bb2c150a2c295033d35dec629ef9ee42940` |
| SDL2 | `98d1f3a45aae568ccd6ed5fec179330f47d4d356` |
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
python tools/prepare_publication.py --source .build/publication/repository --exe .build/publication/repository/Export/Retro-Recomp.exe --release Export/Releases/RetroRecomp-v0.10.17-windows-x64.zip
```

The ZIP contains only the converter and legal notices. Keep source staging and
release audit reports private. The publication tool checks an explicit allowlist
and common credential patterns; review the outgoing diff as well. Public CI
runs the same checks on all tracked files and 66 ROM-free Python tests.
