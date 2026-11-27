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
- **The drive's own timing**: loading takes the time the engine's drive model gives it (seek and read delays), never shortened; it was not compared with a real drive. A speed-up is not part of this version.
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

## 5. Route depth (gate G9)

The first routes (the PC Engine's walk: Run pressed a few times, then directions and taps) leave a disc in its menus: Ys Book I & II rested on its « Location / Start game story » menu for the
whole 18,000-frame route, and Akumajou Dracula X stayed on its file screen. From the extended level, the first long route of a conversion (21,600 frames, six minutes of the game) is therefore built **segment by segment**
(`retrorecomp/pcecd_routes.py`): from the quick state at the end of what was chosen so far, four **styles** of input each play the next 3,600 frames on the observing build (two at a time),
and the style that makes the game run the most code **not run before** (the engine's code capture identities, then the distinct pictures) is kept: `walk` (the PC Engine's), `menu` (a cursor stepped
down and answered, over and over), `action` (directions held, I in bursts, II tapped) and `tap` (single taps of any button, one after the other: it types on a name entry grid). Nothing knows a game;
the report names each segment's choice and every style's score (`route_start.exploration`) and marks the route `explored` (`final_checks[].style`). The route the conversion then plays against the reference,
checks and ships is the composed script, played from the start; the states it was built from are the quick states the conversion checks.

On Akumajou Dracula X this is what changes: the route types a name in the file screen (a save in the backup memory), starts the game, reaches the first stage (health bar and score on screen) and its
cut-scenes, where the walk stopped at the file screen for the whole route. A route's depth is a measure of the route, never of the game: what a route reaches is not what a player can reach, and what it
does not reach runs on the interpreter, counted.

## 6. Multiplayer (step 3, 22 November 2026)

The machine joins the sessions on the **rollback** tier, with the PC Engine's adapter (`rrhk_pce.c`, which the CD adapter includes): a state saved at any frame and loaded back leaves the machine as it was, a
digest of every frame is compared between the seats, the multitap is plugged for every seat, and the backup memory is the session's save (the host's file is handed to the guests, played in memory and written
back at a clean end, the old file kept).

* **What the snapshot holds** (`native/pce_snapshot.cpp`): the CPU, the System Card's RAM and the drive's (RAM banks of 8 KiB), the 2 KiB of backup memory (bank $F7, locked until a game
  asks), the video, the palette, the pads and interrupts as for a HuCard, and, through the engine's own checkpoint writer, the drive (command and data transport, a read in flight, the CD audio position and
  fader), the ADPCM unit (its 64 KiB of RAM, its clocks and flags) and the PSG. About 0.85 MB a snapshot, less than 2 MB the bound.
* **The digest** is the HuCard's (the CPU, the RAM banks, the video, the palette, the pads, the timer) plus the backup memory and the engine's own field list of the drive and the ADPCM unit (patch 7 of the engine, UPSTREAMS.md),
  never the PCM the host drank, never the step counters. It does not depend on how the host drained the sound, nor on Windows or Linux.
* **The lobby** compares the System Card: the report names it at the top level (`bios`, with its SHA-256), so two players with another card are refused before the launch.

Proofs (all on Dracula X or Lords of Thunder, the player's own card and discs, never in the repository):

| Proof | Result |
|---|---|
| `tools/pcecd_snapshot_selftest.py` (the probe on the interpreter, 1,800 frames of pseudo-random pads on Lords of Thunder, a save point every 60 frames) | PASS: the engine's full checkpoint after each load equals the one at the save, 696 frames replayed after the loads repeat the digest and the checkpoint, damaged or short snapshots refused, the digest reads the drive, the ADPCM RAM, the backup memory and the card's RAM and does not read how the sound was drained. The first pass read 396 sectors, played 1,505 CD audio sectors and made 98,336 ADPCM writes |
| The same probe on Debian 13 (WSL) | the 30 digests of the first pass equal Windows's, line for line |
| `tools/netplay_game_smoke.py` on Dracula X, 2 seats, rollback 5, 30 ms ± 10, 2 % loss, save at frame 600, load at 1,500, restart at 2,200, 3,000 frames | PASS: boot digests equal, 50 digests of 50 different values equal on both seats, 95 and 183 rollbacks (deepest 5), the host's save written back |
| The HuCard output | unchanged: an A/B of Alien Crush and Air Zonk and the snapshot self-test on both boards (UPGRADES.md) |

**Three and four seats, 22 November 2026.** The converter builds every disc for two players, except the ones a reviewed table lists (`pcecd.MULTITAP_PLAYERS`, keyed by the disc's digest, the rule of the HuCards'
`pce_build.MULTITAP_PLAYERS`). An entry is evidence: `tools/pcecd_multitap_probe.py` runs the converted game on its own long route, with the multitap plugged, once with the other pads idle (twice, to show the run is deterministic)
and once for each of pads 2, 3 and 4 pressed by a fixed pattern; **a pad that changes the RAM, CPU, picture or sound hash of the run is a pad the game reads**. On the nine-disc panel: Dungeon Explorer II reads pads 2 and 3
(all four hashes) and pad 4 (the RAM): **four players**; Buster Bros. reads pad 2 only; Dracula X, Lords of Thunder, Ys III, Addams Family, 4 in 1 Super CD and Ys Book I & II read pad 1 only on their routes (that is what the route
reached, not a claim about the game's menus). Only Dungeon Explorer II is listed; every other disc stays at two seats.

| Proof, Dungeon Explorer II (USA), four players | Result |
|---|---|
| `tools/pcecd_snapshot_selftest.py --tap 4` (1,800 frames of pseudo-random pads on four pads, a save point every 60 frames) | PASS: 30 save points loaded, 696 frames replayed after the loads, same checks as above; 417 sectors read |
| The same probe on Debian 13 (WSL) | the 30 digests equal Windows's, line for line |
| `tools/netplay_game_smoke.py --seats 4`, rollback 5, 30 ms ± 10, 2 % loss, save at 600, load at 1,500, restart at 2,200, 3,000 frames | PASS: boot digests equal, 50 digests of 50 different values equal on the four seats, 132 to 350 rollbacks per seat (deepest 3), the host's save written back |
| The same with `--seats 3` | PASS |

Not proved, and not claimed: the two-PC run (the multiplayer specialist's, with the ThinkPad) and physical latency (never measured). The backup memory stayed blank in the probe's route (Lords of Thunder), so the snapshot's path for it is proved on hand-set bytes (the probe's disturbed-state load). A game did write it on a route of the panel: Ys Book I & II's play route answers its « initialize the File Cabinet? » question, the memory it wrote survives a fresh process (section 4), but no session has played that game yet.

