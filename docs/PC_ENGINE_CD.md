# PC Engine CD / TurboGrafx-CD

Status: **experimental**, open to players (21 November 2026). Step 1 of [NEW_MACHINE.md](NEW_MACHINE.md) is done: nine discs convert, the Linux witness agrees with Windows, the
owner has not played them (G14, step 2). The decisions below are the owner's, taken on 21 November 2026 after the study.

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

## 4. Stage 1, where it stands (21 November 2026)

| Stage | State |
|---|---|
| 1a. Profile, disc and System Card readers, registries, stamps, firmware search, languages | done |
| 1b. The conversion loop on the pinned engine, our disc provider (libchdr static, CHD version 4 and 5, the disc inside the executable) | done: nine discs converted |
| 1c. The delivered game and its host-kit adapter | the delivered game replays its routes equal to the reference, quick states and backup memory checked; the window itself is for the owner's play test (G14) |

**The nine discs converted from an empty library** (Windows, llvm toolchain, two conversions at a time, scan level `standard`: a boot route and a play route of 3,600 frames each; the
maintainer's Japanese Super System Card 3.0, the Super RAM profile, the drive's unknown commands answered as the NEC reference does, `nec-invalid`):

| Disc | Container | Why it is in the panel | Native instructions run / interpreted | Emitted in the module |
|---|---|---|---|---|
| Ys III (USA) | CHD v5 | the engine's own flagship; first game | 102.7 M / 0 (one play route) | 10,861 instructions, 35 contexts |
| Akumajou Dracula X (Japan) | CHD **v4** | a version 4 container; Japan region | 214.5 M / 0 | 13,124, 133 contexts |
| The Addams Family (USA) | CHD v5, one cooked data track, no audio track | the smallest disc (7 MB) | 222.5 M / 0 | 8,810, 23 contexts |
| Lords of Thunder (USA) | CHD v5 | a scrolling shooter, CD audio driven by the game | 208.2 M / 0 | 79,512, 573 contexts |
| Buster Bros. (USA) | CHD v5 | two players | 214.5 M / 0 | 6,953, 19 contexts |
| Dungeon Explorer II (USA) | CHD v5 | a multitap candidate | 201.3 M / 0 | 15,746, 92 contexts |
| Valis III (USA) | CHD v5 | 18 data tracks interleaved with the audio | 216.4 M / 0 | 6,860, 21 contexts |
| 4 in 1 Super CD (USA) | CHD v5 | four games behind a menu | 204.8 M / 0 | 49,673, 317 contexts |
| Ys Book I & II (USA) | CHD v5 | the most ADPCM voice | 204.7 M / 0 | 14,483, 54 contexts |

What these numbers say and what they do not: on the two routes of each disc (boot, then a play route), no instruction ran on the interpreter, the delivered game gave the same picture, sound,
RAM and CPU state on every frame as the build with every instruction interpreted, a quick state continued the saved timeline in a fresh process, and eleven kinds of damaged backup
file were set aside. **They do not say the games are translated**: a route of 3,600 frames reaches the System Card's start-up and the first screens of a game, and the boot route sees only the
System Card's "push RUN" screen (three pictures, no sound), so the code a game loads later from its disc has not run. The depth of the routes past the loading screens is gate G9, still `?`.
Nothing here says hardware fidelity, gameplay or latency.

Measured on the way: the strict policy for the drive's unknown commands stops Ys III and The Addams Family (an unknown command `$FF` when RUN is pressed) and is not the default; the Japanese
card runs USA discs and Japanese ones; a conversion takes about twelve minutes on this PC (two at a time).

**The Linux witness**: The Addams Family converted on Debian 13 (WSL, gcc, headless) from an empty library gives the same 222,527,282 observed instructions, the same module (8,810
instructions in 23 contexts) and, on both routes, the same CPU, RAM, picture and PCM hashes and the same trace digest as Windows. One disc, not a panel; no Linux GPU is involved.
