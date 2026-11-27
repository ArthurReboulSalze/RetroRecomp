# PC Engine CD / TurboGrafx-CD

Status: **experimental**, open to players (21 November 2026). Steps 1 to 3 of [NEW_MACHINE.md](NEW_MACHINE.md) are done as far as they can be without the owner: nine discs convert and match on
Windows and Linux, routes reach play on all nine (Dungeon Explorer II since a fix of 27 November), multiplayer is proved on one PC. The owner played three of them and accepted them (G14, 27 November 2026, [QUALIFICATION.md](QUALIFICATION.md#owner-acceptance)); the exit from experimental is not recorded. The decisions
below are the owner's, taken on 21 November 2026 after the study.

## 1. What it converts, and what it does not

- **Discs as the player gives them**, read in place and never changed: a **CHD** (version 4 or 5), a **CUE sheet** with its BIN files, or an
  **ISO** of 2,048-byte sectors. CD-ROM² and Super CD-ROM² discs, one disc per game. Every disc converted so far is a CHD: the CUE path was checked on authored discs only and no real ISO
  has been converted. An ISO holds one data track and no CD audio, so it is not a full copy of a disc that has audio tracks.
- **The System Card is the player's own**, checked by its hash and never shipped (`retrorecomp/pcecd_card.py`). Two Super System Card 3.0 images are accepted, USA and Japan; any other file is
  refused. Every measure on this page was taken with the Japanese card. We have not run the USA card; the engine's own evidence boots it.
- **The disc inside the executable** (the PlayStation's way: the game holds the whole image and reads it in place) and **no DLL beside it**:
  the CHD decoder (libchdr, BSD-3-Clause) is linked into the game. The executable also holds your System Card: it contains your disc and your firmware, so it is for you only.
- **The drive's own timing**: loading takes the time the engine's drive model gives it (seek and read delays), never shortened; it was not compared with a real drive. A speed-up is not part of this version.
- **Backup memory** (the 2 KiB of the CD system), kept beside the game like the PC Engine's. Without a save file it starts **formatted** (the file system header, nothing stored), as on a HuCard, in Beetle and in MAME: a real unit starts as it was left, and a game may refuse an unformatted one and send you to the System Card's own memory screen (Dungeon Explorer II does).
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
- **CPU fidelity**: the HuC6280 is the PC Engine's; its vectors were run again for this machine on 27 November 2026 (table below).
- **Hardware fidelity**: the CD drive, CD audio, ADPCM and backup memory are the pinned engine's models; their evidence is the engine's, plus the comparison with MAME of section 7.
  Nothing here compares them with a console.
- **Gameplay validation**: scripted routes and captures looked at; no full play of a game is recorded.
- **Physical latency**: not measured; nothing here says zero latency or exact timing.

**The HuC6280 vectors** (`SingleStepTests/huc6280`, commit `4ce378e04e243437e6f74dfe76c3cb7c70e45bf1`, 256 files, 185,548,937 bytes, files digest
`f5b70cc85766242f8249728b56d60e269e9ee1168c252f21bf9719ca5dc84ea0`, pinned in `tools/fetch_huc6280_vectors.py`; MIT, generated with the Mesen emulator, so an emulator's expectations, not hardware).
Run on 27 November 2026: the pinned interpreter, then the code the engine's emitter translates (250 vectors an opcode). The disc games compile the same CPU, emitter and pin.

| Group | Opcodes | Interpreter: vectors run | equal (state and cycles) | state differs | cycles differ | Translated code: cases | differs from the interpreter | Known differences |
|---|---|---|---|---|---|---|---|---|
| load, store, register transfer | 49 | 122,500 | 122,500 | 0 | 0 | 12,250 | 0 | - |
| arithmetic, logic, compare, test | 69 | 172,500 | 172,500 | 0 | 0 | 17,250 | 0 | - |
| shift, increment, bit change | 54 | 135,000 | 133,508 | 1,492 | 0 | 13,500 | 0 | TSB, TRB: the Z flag from the result (as MAME), the vectors from A AND memory |
| branch, jump, call, return, BRK | 33 | 82,500 | 82,500 | 0 | 0 | 8,250 | 0 | - |
| stack | 8 | 20,000 | 20,000 | 0 | 0 | 2,000 | 0 | - |
| flags, speed, NOP | 11 | 27,500 | 27,500 | 0 | 0 | 2,750 | 0 | - |
| block transfers | 5 | 19 | 19 | 0 | 0 | 17 | 0 | most are cut by the corpus's length cap |
| bank registers and VDC port (TAM, TMA, ST0-ST2) | 5 | 12,500 | 4,987 | 13 | 7,500 | 750 | 0 | ST0-ST2: 1 cycle more (VDC access, as MAME); TMA with mask 0: the transfer latch |
| reserved opcodes | 22 | 0 | 0 | 0 | 0 | 0 | 0 | refused by design (55,000 vectors) |

The translated code ran 56,767 cases; its 157 state differences and 750 cycle differences from the vectors are the interpreter's, on the same cases, and none differs from the interpreter. TAM and TMA are left
to the interpreter tier (they change the guarded mapping).

## 4. The panel

| Stage | State |
|---|---|
| 1a. Profile, disc and System Card readers, registries, stamps, firmware search, languages | done |
| 1b. The conversion loop on the pinned engine, our disc provider (libchdr static, CHD version 4 and 5, the disc inside the executable) | done: nine discs converted |
| 1c. The delivered game and its host-kit adapter | the delivered game replays its routes equal to the reference, quick states and backup memory checked; the window itself is for the owner's play test (G14) |

**The nine discs converted from an empty library** (Windows, llvm toolchain, two conversions at a time, scan level `standard`: a boot route and a play route of 3,600 frames each; the
maintainer's Japanese Super System Card 3.0, the Super RAM profile, the drive's unknown commands answered with CHECK CONDITION, the engine's `nec-invalid` policy, whose byte counts follow a table of the Beetle emulator's NEC core and not NEC documentation):

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
| Ys Book I & II (USA) | CHD v5 | a lot of ADPCM voice | 204.7 M / 0 | 14,483, 54 contexts |

What these numbers say and what they do not: on the two routes of each disc (boot, then a play route), no instruction ran on the interpreter, the delivered game gave the same picture, sound,
RAM and CPU state on every frame as the build with every instruction interpreted, a quick state continued the saved timeline in a fresh process, and eleven kinds of damaged backup
file were set aside. **They do not say the games are translated**: a route of 3,600 frames reaches the System Card's start-up and the first screens of a game, and the boot route sees only the
System Card's "push RUN" screen (three pictures, no sound), so the code a game loads later from its disc has not run. The depth of the routes past the loading screens is gate G9: the extended level's explored route (below) reaches play on all nine discs of the panel.
Nothing here says hardware fidelity, gameplay or latency.

Measured on the way: the strict policy for the drive's unknown commands stops Ys III and The Addams Family (an unknown command `$FF` when RUN is pressed) and is not the default; the Japanese
card runs USA discs and Japanese ones; a conversion takes about twelve minutes on this PC (two at a time).

**The Linux witness (27 November 2026):** the nine discs converted on Debian 13 (WSL, headless) give the same exploration choices, modules and final CPU, RAM, picture, PCM, trace and backup
hashes and native counts as on Windows. No Linux PC with a real display, GPU, pad or sound output is covered. (A first witness on The Addams Family dates from 21 November 2026.)

### The panel of nine at the extended level (27 November 2026)

Converted through `batch` with the online covers off (`tools/release_check.py`, extended level, an empty private library, two at a time, the portable llvm toolchain, Japanese Super System Card 3.0, tree
`spec/pcecd-g9`). Routes: attract (3,600 frames), play (3,600), and the explored long route (21,600). Every gate of `release_check` passes on all nine: **0 interpreted instructions on all 27 routes**, 0 guard
misses, native equal to the reference on every frame, the published executable replayed, quick states and damaged states. A conversion takes 30 to 39 minutes on this PC, two at a time.

| Disc | Native instructions run (millions) | Emitted (instructions, bank contexts) | Explored segments | Long route: distinct pictures | What the long route reaches (captures looked at) |
|---|---|---|---|---|---|
| The Addams Family | 889 | 9,932 / 25 | walk, action, action, menu, menu, walk | 9,562 | **in play**: the first level |
| Akumajou Dracula X | 872 | 43,896 / 383 | walk, walk, action, action, tap, walk | 7,937 | **in play**: a name typed (a save written), the stage 0 fight on the carriage |
| Buster Bros. | 867 | 8,098 / 19 | walk, menu, action, walk, walk, action | 13,634 | **in play**: stages 1 and 2-4 |
| Dungeon Explorer II (before the memory change) | 773 | 45,071 / 252 | tap, tap, tap, menu, walk, walk | 1,300 | the player-count menu, the world map and the opening scenes; no play seen |
| Dungeon Explorer II (converted again) | 794 | 59,714 / 319 | tap, walk, walk, walk, walk, walk | 2,560 | **in play**: the file screen, the opening scenes, then the castle with two characters and their health bars |
| 4 in 1 Super CD | 839 | 115,380 / 574 | action, menu, tap, walk, walk, walk | 13,796 | **in play**: Gate of Thunder (one of the four games) |
| Lords of Thunder | 858 | 125,684 / 841 | action, action, walk, menu, menu, walk | 12,695 | **in play**: the shop, the first stage and its enemies |
| Valis III | 814 | 18,103 / 34 | tap, action, action, walk, action, tap | 9,938 | **in play**: the first stage |
| Ys Book I & II | 800 | 43,708 / 109 | tap, walk, walk, action, walk, walk | 12,796 | **in play**: the town of Ys I (a save written) |
| Ys III | 827 | 37,199 / 55 | menu, tap, action, walk, tap, action | 3,724 | **in play**: the opening and the first town, then a room the route does not leave |

**Saves:** Dracula X and Ys Book I & II write the backup memory on their long route; in a fresh process the game starts with exactly the memory the first run left, and Dracula X shows the name it saved
(« PLAYER1 AA ») in its file screen and goes on to play. On every disc: without a save file the game finds the memory (then blank, see below), a valid file is read, eleven kinds of damaged file are set aside. Later on 27 November the memory without a save was changed to start formatted (section 1).

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

**Dungeon Explorer II (27 November 2026).** Its routes stopped short of play because a disc without a save file found a **blank** backup memory: choosing START asks « make a save file? » and, on YES, answers « please initialize
backup RAM » and returns to the title. A real player would have had to go to the System Card's own memory screen first. The memory now starts formatted, as on a HuCard, in Beetle and in MAME (section 1), and
the game goes on to its file screen. Converted again at the extended level (`tools/release_check.py`, empty private library): every gate passes, 0 interpreted instructions on the three routes, native equal to the
reference, and the long route reaches the castle in play. The other eight discs of the panel were converted before this change; they reached play then, and the change reaches a game only through what it reads
from that memory.

## 6. Multiplayer (step 3, 22 November 2026)

The machine joins the sessions on the **rollback** tier, with the PC Engine's adapter (`rrhk_pce.c`, which the CD adapter includes): a state saved and loaded back leaves the machine as it was (probed every 60 frames over 1,800 frames, the table below), a
digest of every frame is compared between the seats, the multitap is plugged for every seat, and the backup memory is the session's save (the host's file is handed to the guests, played in memory and written
back at a clean end, the old file kept).

* **What the snapshot holds** (`native/pce_snapshot.cpp`): the CPU, the System Card's RAM and the drive's (RAM banks of 8 KiB), the 2 KiB of backup memory (bank $F7, locked until a game
  asks), the video, the palette, the pads and interrupts as for a HuCard, and, through the engine's own checkpoint writer, the drive (command and data transport, a read in flight, the CD audio position and
  fader), the ADPCM unit (its 64 KiB of RAM, its clocks and flags) and the PSG. About 0.85 MB a snapshot, less than 2 MB the bound.
* **The digest** is the HuCard's (the CPU, the RAM banks, the video, the palette, the pads, the timer) plus the backup memory and the engine's own field list of the drive and the ADPCM unit (patch 7 of the engine, UPSTREAMS.md),
  never the PCM the host drank, never the step counters. The sound the host drained is left out of it; in the probes the digests were equal on Windows and Linux.
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

## 7. The drive compared with MAME (27 November 2026)

`tools/pcecd_mame_compare.py` (development only) boots the same Japanese Super System Card 3.0 and the same disc on both sides: our machine with every instruction on the interpreter
(`native/pcecd_mame_probe.cpp`), and MAME 0.289 (`pce scdsys`, headless). Both play the same pad script (Run on « push RUN », then I and now and then Run) for 12,000 frames, from the same formatted backup
memory. The two drives do not take the same time, so nothing is compared frame by frame: the events are compared **in the order the program made them**.

| Behaviour | Akumajou Dracula X (CHD v4) | Lords of Thunder | Ys Book I & II |
|---|---|---|---|
| Drive commands with their parameters | 30 of 30 equal | 60 of 60 equal | 27 of 27 equal |
| Interrupt mask writes ($1802) | 9 of 9 | 51 of 51 | 3 of 3 |
| CD audio: first and last sector of each playback | 2 of 2 | 14 of 14 | 2 of 2 |
| Data the program read through $1808 (bytes, hash) | 346,112, equal | 1,695,744, equal | 256,000, equal |
| ADPCM port writes ($1808-$180F) | 50 of 50 | 334 of 334 | 2,330 of 2,330 |
| Bytes written through the ADPCM data port ($180A) | none (loaded by DMA) | 163,839, equal | none (loaded by DMA) |
| ADPCM RAM (64 KiB) at each drive selection | 30 of 30 equal | 60 of 60 equal | 27 of 27 equal |
| CD RAM and Super RAM (256 KiB) at each selection | equal at all 30 | equal at 12, then a few bytes differ (at most 726) | equal at 22, then 1 or 2 bytes differ |
| Backup memory lock state and unlock writes | equal (5 writes) | equal (never unlocked) | equal (3 writes) |
| Backup memory (2 KiB) at the end | equal | equal | equal |

**How to read it.** The commands, the data read, the sectors played and the ADPCM contents are what a program sees of the drive, and they agree. The RAM differences are in the program's own
variables, consistent with the two machines not taking the same time (the data read is equal); each difference was not traced to its cause.

**Known limits.**
- **The System Card's signature**: our engine answers `AA 55 03` at $18C1-$18C3; MAME answers `AA 55 00` there and `AA 55 03` at $18C5-$18C7. The games boot on both; which one a console does is not
  settled here.
- **Reads of the lock register** ($1803) differ in number: they are polling loops, which depend on timing.
- **Not compared**: the drive's timing (seek and transfer delays), the sound itself (CD audio, ADPCM and PSG mixing), the video, a real console. MAME is another emulator, not hardware.
- Three discs, the first 12,000 frames of one pad script each: nothing is said of the other discs or of later in these.
