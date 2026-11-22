# Game Boy Color

**Status: experimental, in development (not in a release yet).** The Game Boy Color is the second machine of the Game Boy
engine: the same SM83 and the same pinned recompiler ([GAME_BOY.md](GAME_BOY.md)), started in the colour hardware's model. It has a
profile of its own (`gbc`), as the Game Gear has on the Master System's engine, so that its evidence, its gates, its
paths, its library and its settings are its own. The original Game Boy stays what it is.

## What is converted, and what is not

| | |
|---|---|
| Converted | Game Boy Color cartridges: Color-only (header flag `C0`) and Color-enhanced (`80`) read from a `.gbc`, a `.gb` (Color-only ones) or a single-ROM ZIP; the mappers the engine implements (MBC1, MBC3 with its clock, MBC5 including the rumble variants) |
| Stays with the Game Boy | a cartridge without the Color flag; the one Color-flagged cartridge kept as a monochrome `.gb` (Pokémon Yellow) keeps its Game Boy conversion (Arthur, 21 November 2026) |
| Not converted yet | infrared (a stub in the engine), the MBC7 tilt sensor, the Game Boy Printer and Camera, Super Game Boy borders; no boot ROM is used, ours or yours: the engine starts from a configured post-boot state, as the Game Boy does |
| Not offered yet | the link cable, multiplayer and quick-state compatibility with the Game Boy (a Color state is its own family) |
| Later, as an option | DMG cartridges coloured with the Color's compatibility palettes; a corrected LCD curve (neutral colours are the default; every test reference uses the neutral expansion of the 5-bit channels) |

The reference revision is the Color's B to E (not the Advance's colour behaviour).

## How a file reaches this profile

A `.gbc` is the Color's (one whose header has no Color flag is refused, with the message to convert it with the Game Boy profile). A `.gb` or a ZIP whose header says Color-only (`C0`) is the Color's; a Color-enhanced one (`80`) stays with the
Game Boy unless it is a `.gbc`. A headerless `.bin` or `.rom` is told by its header checksum, its declared size and its flag.

## Five measures, kept apart

- **Native code:** the generated SM83 code is the Game Boy's; the counted interpreter fallback is reported per CPU and per device as for the Game Boy. First figures (quick level, two passes, 600 frames, boot route; the play routes are in each report): Tetris DX 17,440 interpreter cycles, Pokémon Gold 0, Wario Land 3 0 (1,526 instructions run one by one in writable memory, counted apart), Shantae 473,680, Super Mario Bros. Deluxe 36, Pokémon Pinball 0, Lufia 393,930. The two high ones are what the next steps work on.
- **CPU fidelity:** the SM83 is the Game Boy's (independent vectors apply unchanged; double speed and STOP are not covered by them). Each conversion compares the generated code with the reference interpreter on its boot route (passed for the seven games; Shantae also compared over 3,600 frames at the extended level, equal, 54.7 million steps); the other six no longer route yet.
- **Hardware fidelity:** the engine's Color model (double speed, the two video banks, the eight work-RAM banks, palettes, HDMA) is the upstream's, changed by eight fixes of `retrorecomp/gameboy_color_hardware.py` that only the Color build receives (the original Game Boy's sources are not touched: a test pins it). **Measured against the public test ROMs in the Color build** (`python -B tools/gameboy_testroms.py ... --model cgb`; the ROMs are the player's downloads, kept outside the repository; Windows, 21 November 2026): 115 of the 116 applicable tests pass, each with the lock-step comparison against the pinned interpreter equal over every frame it ran: blargg `cpu_instrs` (11), `instr_timing`, `mem_timing` and `mem_timing-2`, the twelve `cgb_sound`, Mooneye's all-model tests (timing, interrupts, timers, the eight OAM-transfer tests, MBC1, MBC2, MBC5), `boot_hwio-C` and `unused_hwio-C`. One fails: `boot_div-cgbABCDE` (no boot ROM, so the divider's phase at the start is not the console's). Before the fixes the same suite passed 108 of 116. The fixes, each named by the test that showed it: the CPU is locked out of OAM and the unusable area during an OAM transfer (sixteen timing tests; the split of the transfer's source bus between cartridge, video and work RAM stays the engine's, as Pan Docs describes the Color, and no test tells it from the original console's); the timer's disable edge increments TIMA (`rapid_toggle`); the sound unit's power-off clears the length counters and the length part of NRx1 is not writable while off (`cgb_sound` 08 and 11); a write to wave RAM while channel 3 plays goes to the byte being played, the channel's timer keeps its period until it runs out, and its first sample comes six clocks after a trigger (`cgb_sound` 09 and 12: that last number is fitted to the test's checksum, with no hardware document behind it); the registers a cartridge without the Color flag finds at the start (the joypad's selection lines, the serial control register, VBK and the two palette index ports); the 5-bit colour channels widen as `(x << 3) | (x >> 2)`, the expansion of every test reference. The eighth fix is not a test's: a tick hands its cycles to the sound unit before the picture unit is synchronised, so that the HDMA's stall tick in double speed no longer reaches the sound unit first (the generated code and the interpreter were one system cycle apart, and Shantae's lock-step comparison stopped at frame 1,117; with the fix its 3,600 frames compare equal, 54.7 million steps, the comparison unchanged). **`cgb-acid2` (the picture test): 40 of 23,040 pixels differ from its reference image, on rows 88 and 128, cause not found;** every other pixel equals it. They show what the engine does against hardware test ROMs, not what a console does. Known and not changed: STOP and double speed are covered by the authored checks only (`tools/gameboy_color_selftest.py`, 417 checks against the register pages of Pan Docs), the wave channel's cycle-exact timing is the same coarse model as the original Game Boy's.
- **Gameplay validation:** none yet; the panel converts, it is not played.
- **Physical latency:** not measured.

Everything not yet measured is `?` in [QUALIFICATION.md](QUALIFICATION.md).

## Panel

Seven cartridges and one in reserve, each for a hardware case, none dropped: Tetris DX (the first game, the smallest, a Color-only cartridge with a cable mode),
Pokémon Gold (MBC3 with a real-time clock, a 32 KiB save, trade and battle over the cable), Wario Land 3 (a Color-only platformer with a 32 KiB save; the most
code run one by one in writable memory), Shantae (4 MiB, 256 banks, heavy palette and DMA use), Super Mario Bros. Deluxe (the Color counterpart of a game of the Game
Boy's panel), Pokémon Pinball (the rumble bit of MBC5: the host has no rumble, stated and never counted as native), Lufia: The Legend Returns (an RPG with a big script,
menus and a 32 KiB save). In reserve: Kirby's Tilt 'n' Tumble (MBC7, a tilt sensor: declared out of scope for the first version). The cartridges are the player's own
downloads, outside the repository; Pokémon Yellow stays with the Game Boy (a 0x80 cartridge is the Game Boy's: the profile claims only the Color-only flag 0xC0).

## The sixteen gates, with their evidence (22 November 2026)

The letters are in [QUALIFICATION.md](QUALIFICATION.md); this table says where each piece of evidence is and what it leaves out. Windows, tree `fde462cd` (the merge `1b0f33b2`
on `aeafa681`, plus the two check tools), the scratch libraries empty, two conversions at a time. **Not claimed: hardware fidelity, gameplay validation, physical latency.**

| Gate | Evidence for the Game Boy Color | What it leaves out |
|---|---|---|
| G1 `P` | `retrorecomp/systems/game_boy_color.py` (status `experimental`), this page, the README row and COMPATIBILITY | It stays `P` until the owner's decision (G14) |
| G2 `Y` | `tools/release_check.py` reads the seven reports through `report_schema.read_report` (the Game Boy's writer: the SM83 as main CPU, the mapper and the sound unit as devices with no counter) | The mapper and the sound unit are C models: their fidelity is stated as not validated |
| G3 `Y` | **0 interpreter cycles on all 28 final routes** (seven games, four routes of 3,600 frames); the code run one by one in writable memory is counted apart and is not native: Lufia 0, Tetris DX 3,538 to 3,549 instructions a route, Super Mario Bros. Deluxe 3,403 to 3,557, Pokémon Pinball 3,369 to 3,581, Pokémon Gold 2,307 to 3,548, Shantae 30,984 to 45,492, Wario Land 3 61,043 to 120,117. The first discovery pass of every game still interprets some code (Shantae 568,000 to 692,000 instructions, Lufia 156,000 to 263,000, Super Mario Bros. Deluxe 26,000 to 54,000, the others under 1,400) and the second pass reaches 0 | Only the routes run; helpers are counted as entries and cycles, not as instructions |
| G4 `P` | Lock-step against the pinned interpreter: 30 boot frames and 240 a route on all seven (standard level); the **whole 3,600 frames** on Shantae (54.7 million steps) and Lufia (44.6 million) at the extended level; the 115 of 116 public test ROMs, each with the comparison equal over every frame it ran | The other five games were not run at the extended level; the interpreter shares the runtime's devices, so it is no independent oracle for them |
| G5 `Y` | The compressed copy replayed on the same routes with the same verdict (`packed_reference_match`) on all seven | Same routes and lengths as G4 |
| G6 `Y` | Quick states in fresh processes on the delivered copy, with the damaged ones refused, on all seven (`game_states.fresh_process_verified`); `tools/gameboy_states_check.py --model cgb` on an authored Color cartridge: all checks, the ten damaged states refused | F8 and F9 themselves are not driven; the state file has no checksum |
| G7 `Y` | `tools/gameboy_saves_check.py --model cgb`: six authored cartridges flagged Color-only (MBC1, MBC2, MBC3 with its clock, MBC5, RAM without battery, a battery never written), converted for the Color, reload byte for byte, damaged files refused: 93 checks, 0 failure; the reports of Pokémon Gold (real-time clock) and Lufia, Wario Land 3 (32 KiB of battery RAM) name the files | A game's own save code is not tested: no game was played to a save on the Color |
| G8 `Y` | `final_checks[].liveness` on every route of the seven: the picture changes and sound is heard on all 28 (62 to 2,256 distinct pictures a route; Pokémon Pinball's boot route shows 62: an attract screen); the captures of three games were looked at | Counts of changes, not proof that a game is played well; nobody has listened yet |
| G9 `P` | The extended level's long route of 18,000 frames on Shantae (7,985 distinct pictures, picture and sound alive to the last frames) and Lufia (2,053 pictures, 17,529 audible frames), 0 interpreted cycles on both | Two games of seven; pad routes, not full games |
| G10 `P` | The SM83 is the Game Boy's (the SingleStepTests vectors apply unchanged, [CPU_SM83.md](CPU_SM83.md)); blargg `cpu_instrs` 11 of 11, `instr_timing` and `mem_timing` in the Color build | STOP and double speed are covered by the authored checks only |
| G11 `P` | 115 of the 116 public Mooneye and blargg tests of the Color build; 417 authored checks of the colour hardware against Pan Docs; `cgb-acid2` 40 of 23,040 pixels differ, cause not found; `boot_div-cgbABCDE` fails (no boot ROM) | Documentation and test ROMs, not a console; the OAM-transfer source bus is the engine's |
| G12 `Y` | The panel above, none dropped, each with its reason | Seven cartridges of the player's library |
| G13 `Y` | **Four games (Tetris DX, Pokémon Gold, Super Mario Bros. Deluxe, Pokémon Pinball) converted again on Debian 13 in WSL** from the same tree and an empty library (4 of 4 ready in 63 minutes): `tools/gameboy_cross_os.py compare` says the per-frame traces (picture, sound, work RAM and program counter hashes) and the final states are **equal on 20 of 20 routes**, 129,600 frames a system (boot, two play runs, a varied run, a pseudo-random run of 18,000 frames); the Color's authored checks ran on Windows (417 and the link checks) | A Linux PC with a real display; four games of seven |
| G14 `?` | The owner's: the checklist is below | His play test |
| G15 `P` | The five measures stay separate in the report and here; this page, the README row, COMPATIBILITY, CONTROLS, MULTIPLAYER and the eight languages' strings were read for « exact », « zero latency », « perfect » and hardware claims: none; `hardware_accuracy` and `full_game` are false in the reports and physical latency is not measured | The sweep of every page is the documentation specialist's |
| G16 `?` | Not decided, evidence below | The owner's rule of 14 November 2026 (« useless sharing → no sharing ») decides |

**G16, the evidence.** The Game Boy shares its paths (`SharedKnowledge("stable")`); the Color's profile has none. At the standard level **all seven games need a second discovery
pass**: the first interprets some code (figures in G3) and the second reaches 0 on every route. A path received from another player would give that code to the first pass, so
it would save a pass (the conversion times of the seven, two at a time, were 2,878 seconds in all; Shantae's first pass interprets 685,000 instructions on its boot route). This
is a reason to share, not to decline; the work is a `shared_knowledge` in the profile, the schema-3 records keyed by CPU, the web limits and the site's list (the lesson of the
1.7.2 release: a machine shared before the site names it has its uploads refused). It is the owner's decision.

## G14 checklist for the owner's play test

Three games are in `Export/Games/Game Boy Color/`, built from the merged tree: Tetris DX, Pokémon Gold, Wario Land 3. About three minutes a game: the title, a first screen
of play, sound, the colours; the quick states (F8 and F9) and the pause menu; Pokémon Gold's save after the intro; Tetris DX's two-player mode is the multiplayer's test
([MULTIPLAYER.md](MULTIPLAYER.md)). What the owner decides is whether the Game Boy Color leaves the experimental status; no number here says that a game is complete or exact.

## Where it stands

Steps 1 to 3 of [NEW_MACHINE.md](NEW_MACHINE.md) are merged or ready: the profile, the registries and the shared variant of the conversion modules (the Game Boy's output is
unchanged: an A/B on two games, **identical** after the Color-only fixes); the qualification of 21 and 22 November 2026 (the public test ROMs and the eight Color-only
fixes above, the panel of seven, the extended level on Shantae and Lufia, the saves and states checks, the Debian witness); the link cable, GBC with GBC only. **Steps 4 to 6 are
open:** the optimisation of the Color's object-span path (timing is the performance specialist's, with the owner's agreement), the decision on path sharing (G16) and the release kit.
Still not proved: the two-player screen of a real game on two PCs, a Game Boy with a Color on one cable (not offered), and the owner's play test.
