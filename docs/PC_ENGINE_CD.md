# PC Engine CD / TurboGrafx-CD

Status: **experimental, in development** (developer installations only: the profile is not offered to players yet). Stage 1 of
[NEW_MACHINE.md](NEW_MACHINE.md) is under way: the machine identifies discs and System Cards and converts nothing yet. The decisions
below are the owner's, taken on 21 November 2026 after the study.

## 1. What it converts, and what it does not

- **Discs as the player gives them**, read in place and never changed: a **CHD** (version 4 or 5), a **CUE sheet** with its BIN files, or an
  **ISO** of 2,048-byte sectors. CD-ROM² and Super CD-ROM² discs, one disc per game.
- **The System Card is the player's own**, checked by its hash and never shipped (`retrorecomp/pcecd_card.py`). The Super System Card 3.0 of
  the USA is the card the engine's own evidence boots; the Japanese 3.0 card is known by its hash too (what runs on which card is measured
  in stage 1, section 4).
- **The disc inside the executable** (the PlayStation's way: the game holds the whole image and reads it in place) and **no DLL beside it**:
  the CHD decoder (libchdr, BSD-3-Clause) is linked into the game.
- **Authentic drive timing**: loading takes what the real drive takes. A speed-up is not part of this version.
- **Backup memory** (the 2 KiB of the CD system), kept beside the game like the PC Engine's.
- **Not in this version:** the Arcade Card (the engine has its Duo profile; no disc of it in the maintainer's library), SuperGrafx, System
  Cards that are not in the table, multi-disc games (there is none), a disc image that needs a protection circumvented.
- **One machine of its own**, not a mode of the PC Engine: its media, firmware, saves and boot differ. It shares the HuC6280, the video
  and sound chips, the bridge to the engine and the host-kit adapter with the PC Engine (`retrorecomp/stamp_inputs.py`, group `pce`/`pcecd`).

## 2. How a disc is recognised

By what it holds, never by its extension (a CHD or a CUE is also the container of other machines' discs): the second sector of the first
data track has the text `PC Engine CD-ROM SYSTEM` at offset 32 and the boot record (where the program is, where it loads, where it
starts). `retrorecomp/pcecd_disc.py` reads that sector from a CHD (its own pure-Python reader, `retrorecomp/pcecd_chd.py`, which checks
every hunk it decodes against the CRC of the file's map), from a CUE sheet or from an ISO (the PlayStation's generic readers).

On the 42 CHD discs of the maintainer's library (13.1 GB, 7 MB to 687 MB): all 42 are recognised in 5.5 seconds on a network share; 31 are
CHD version 5 and 11 are version 4 (the pinned engine's own reader refuses the version 4, which is why the game reads the disc through a
patched reader, stage 1).

## 3. The five measures

Kept apart in every report and every page, as everywhere:

- **Native code**: how much of what the disc and the System Card run was translated and how much ran on the counted interpreter fallback,
  per CPU (the HuC6280) and per device. A disc is only translated where its routes were seen to run; the rest runs counted.
- **CPU fidelity**: the HuC6280 is the PC Engine's (the vectors of the PC Engine, 640,000 of them).
- **Hardware fidelity**: the CD drive, CD audio, ADPCM and backup memory are the pinned engine's models; their evidence is the engine's.
- **Gameplay validation**: scripted routes and the owner's play test; none yet.
- **Physical latency**: not measured; nothing here says zero latency or exact timing.

## 4. Stage 1, where it stands

| Stage | State |
|---|---|
| 1a. Profile (developer only), disc and System Card readers, registries, stamps, firmware search, languages | this change |
| 1b. The conversion loop on the pinned engine, the CHD version 4 and static libchdr patch, the first disc | not started |
| 1c. The exported game and its host-kit adapter, the first game plays | not started |

Two measures remain to be made before they are written as facts: whether the Japanese card runs the USA discs and the other way round, and
which RAM profile (standard or super) each disc needs.
