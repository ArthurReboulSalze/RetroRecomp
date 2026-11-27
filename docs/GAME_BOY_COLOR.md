# Game Boy Color

**Status: supported** since 27 November 2026, on the owner's acceptance (G14); it ships with the next release, and no published release holds
it yet. The Game Boy Color is the second machine of the Game Boy
engine: the same SM83 and the same pinned recompiler ([GAME_BOY.md](GAME_BOY.md)), started in the colour hardware's model. It has a
profile of its own (`gbc`), as the Game Gear has on the Master System's engine, so that its evidence, its gates, its
paths, its library and its settings are its own. The original Game Boy stays what it is.

## What is converted, and what is not

| | |
|---|---|
| Converted | Game Boy Color cartridges: Color-only (header flag `C0`) and Color-enhanced (`80`) read from a `.gbc`, a `.gb` (Color-only ones) or a single-ROM ZIP; the mappers the engine implements (MBC1, MBC3 with its clock, MBC5 including the rumble variants) |
| Stays with the Game Boy | a cartridge without the Color flag; the one Color-flagged cartridge kept as a monochrome `.gb` (Pokémon Yellow) keeps its Game Boy conversion (Arthur, 21 November 2026) |
| Not converted yet | infrared (a stub in the engine), the MBC7 tilt sensor, the Game Boy Printer and Camera, Super Game Boy borders; no boot ROM is used, ours or yours: the engine starts from a configured post-boot state, as the Game Boy does |
| Multiplayer | shared controls, or two Color consoles of the same game on a link cable ([MULTIPLAYER.md](MULTIPLAYER.md)); no Color with a Game Boy on one cable |
| Not offered | quick-state compatibility with the Game Boy (a Color state is its own family) |
| Later, as an option | DMG cartridges coloured with the Color's compatibility palettes; a corrected LCD curve (neutral colours are the default; every test reference uses the neutral expansion of the 5-bit channels) |

The reference revision is the Color's B to E (not the Advance's colour behaviour).

## How a file reaches this profile

A `.gbc` is the Color's (one whose header has no Color flag is refused, with the message to convert it with the Game Boy profile). A `.gb` or a ZIP whose header says Color-only (`C0`) is the Color's; a Color-enhanced one (`80`) stays with the
Game Boy unless it is a `.gbc`. A headerless `.bin` or `.rom` is told by its header checksum, its declared size and its flag.

## Five measures, kept apart

- **Native code:** the generated SM83 code is the Game Boy's; the counted interpreter fallback is reported per CPU and per device as for the Game Boy. First figures, before the qualification below (quick level, two passes, 600 frames, boot route): Tetris DX 17,440 interpreter cycles, Pokémon Gold 0, Wario Land 3 0 (1,526 instructions run one by one in writable memory, counted apart), Shantae 473,680, Super Mario Bros. Deluxe 36, Pokémon Pinball 0, Lufia 393,930. The qualification's final routes report 0 interpreter cycles (G3 below).
- **CPU fidelity:** the SM83 is the Game Boy's (independent vectors apply unchanged; double speed and STOP are not covered by them). Each conversion compares the generated code with the reference interpreter on its boot route (passed for the seven games; Shantae and Lufia also compared over 3,600 frames at the extended level, equal, 54.7 and 44.6 million steps); the other five were not run at that level.
- **Hardware fidelity:** the engine's Color model (double speed, the two video banks, the eight work-RAM banks, palettes, HDMA) is the upstream's, changed by eight fixes of `retrorecomp/gameboy_color_hardware.py` that only the Color build receives (the original Game Boy's sources are not touched: a test pins it). **Measured against the public test ROMs in the Color build** (`python -B tools/gameboy_testroms.py ... --model cgb`; the ROMs are the player's downloads, kept outside the repository; Windows, 21 November 2026): 115 of the 116 applicable tests pass, each with the lock-step comparison against the pinned interpreter equal over every frame it ran: blargg `cpu_instrs` (11), `instr_timing`, `mem_timing` and `mem_timing-2`, the twelve `cgb_sound`, Mooneye's all-model tests (timing, interrupts, timers, the eight OAM-transfer tests, MBC1, MBC2, MBC5), `boot_hwio-C` and `unused_hwio-C`. One fails: `boot_div-cgbABCDE` (no boot ROM, so the divider's phase at the start is not the console's). Before the fixes the same suite passed 108 of 116. The fixes, each named by the test that showed it: the CPU is locked out of OAM and the unusable area during an OAM transfer (sixteen timing tests; the split of the transfer's source bus between cartridge, video and work RAM stays the engine's, as Pan Docs describes the Color, and no test tells it from the original console's); the timer's disable edge increments TIMA (`rapid_toggle`); the sound unit's power-off clears the length counters and the length part of NRx1 is not writable while off (`cgb_sound` 08 and 11); a write to wave RAM while channel 3 plays goes to the byte being played, the channel's timer keeps its period until it runs out, and its first sample comes six clocks after a trigger (`cgb_sound` 09 and 12: that last number is fitted to the test's checksum, with no hardware document behind it); the registers a cartridge without the Color flag finds at the start (the joypad's selection lines, the serial control register, VBK and the two palette index ports); the 5-bit colour channels widen as `(x << 3) | (x >> 2)`, the expansion of every test reference. The eighth fix is not a test's: a tick hands its cycles to the sound unit before the picture unit is synchronised, so that the HDMA's stall tick in double speed no longer reaches the sound unit first (the generated code and the interpreter were one system cycle apart, and Shantae's lock-step comparison stopped at frame 1,117; with the fix its 3,600 frames compare equal, 54.7 million steps, the comparison unchanged). **`cgb-acid2` (the picture test): 40 of 23,040 pixels differ from its reference image, on rows 88 and 128, cause not found;** every other pixel equals it. They show what the engine does against hardware test ROMs, not what a console does. Known and not changed: STOP and double speed are covered by the authored checks only (`tools/gameboy_color_selftest.py`, 417 checks against the register pages of Pan Docs), the wave channel's cycle-exact timing is the same coarse model as the original Game Boy's.
- **Gameplay validation:** the owner's play test of three games (Tetris DX, Pokémon Gold, Wario Land 3) on 27 November 2026, which he accepted (G14). It is a few
  minutes of each: no game was finished, and the other cartridges of the panel were not played.
- **Physical latency:** not measured.

The letters are in [QUALIFICATION.md](QUALIFICATION.md); no one of these five measures stands for another.

## What the partial gates mean for a player

- **G4 (CPU check), `P`.** The instruction-by-instruction comparison with the reference interpreter covers the start of each tested route on every game (30 frames
  from boot, 240 frames of a route); the whole 3,600 frames only on Shantae and Lufia. A difference that shows up later in another game would not have been seen. The
  interpreter shares the runtime's picture, sound and cartridge models: agreeing with it says nothing about those against a console.
- **G9 (route depth), `P`.** Long routes (18,000 frames, pad input) were run on two games of seven, and no game was played to its end. A later part of a game can hold code no
  conversion met: it then runs on the counted interpreter, and the game goes on; the next conversion learns it.
- **G10 (CPU vectors), `P`.** The independent vectors cover the SM83 as the original Game Boy uses it. STOP and double speed, which many Color games use, are covered by our own
  authored checks and the public test ROMs only.
- **G11 (hardware proof), `P`.** 115 of 116 public test ROMs pass and 40 pixels of the Color picture test differ (cause not found): documentation and test ROMs, not a console.

## Known limits

- No infrared, no MBC7 tilt sensor (Kirby's Tilt 'n' Tumble), no Printer or Camera, no Super Game Boy borders; no boot ROM.
- A rumble cartridge does not make the pad vibrate.
- The link cable joins two Color consoles of the same game; a Color and a Game Boy on one cable are not offered. Two consoles were proved on one PC; a real game on two PCs
  is the multiplayer test still to be recorded.
- Code run from work RAM or HRAM runs one instruction at a time and is counted apart: it is not native (up to 120,117 instructions on a route of Wario Land 3).
- Quick states belong to the Color alone: a Game Boy state is not read.

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
| G1 `Y` | `retrorecomp/systems/game_boy_color.py` (status `supported`), this page, the README row, COMPATIBILITY and the release notes, read again with the exit on 27 November 2026: `tools/status_lint.py` finds no contradiction | The five release pages are the documentation specialist's |
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
| G14 `Y` | The owner's play test of Tetris DX, Pokémon Gold and Wario Land 3 (27 November 2026): « Ok, je valide le G14 pour les autres consoles » ([QUALIFICATION.md](QUALIFICATION.md#owner-acceptance)). The same day he asked whether the sound was crunchy, then kept it as it is | His play test is not a full game |
| G15 `Y` | Read again with the exit: this page, CONTROLS, MULTIPLAYER and the eight languages' strings that name the Color claim no exact fidelity, full game, hardware accuracy or latency; `hardware_accuracy` and `full_game` are false in the reports and physical latency is not measured | Pages that are not the Color's are the documentation specialist's |
| G16 `P` | Shares its paths ([below](#shared-paths-g16)), experimental tier: schema 3 records, withdrawable | The online service must know `gbc` before the release; a path is qualified only once another player's conversion reached it |

## Shared paths (G16)

The Color shares what its conversions learn, as the Game Boy does: numbers about the player's own cartridge, `(bank, address)` of code a route
reached, in the schema 3 form of the newer machines (`retrorecomp/gbc_knowledge.py`; one `rom` source, its size and SHA-256; the shapes
`gb_offsets` and `gb_rows` of the `sm83/gbc` map). No ROM byte, no RAM byte, no code and no gameplay record travels. A qualified path counts for the
engine revision that validated it. The sharing is in the experimental tier of the base and can be withdrawn with one line. The original Game Boy
keeps its own records, unchanged. A conversion that received paths still runs its own passes and its Standard comparisons (no quick check from
received paths: the Color's double speed was proved only by the longer comparisons), and one that fails with them is converted again without them.

**What it saves, measured on 27 November 2026** at the Standard level (Windows, the portable llvm toolchain, headless, the PC shared with another
conversion: indicative figures, not a benchmark). « Without » starts from an empty library; « with » from a library that already holds the
cartridge's entries, which is what received paths give a first conversion:

| Game | Without: passes, total | With: passes, total | Interpreted instructions the first pass is spared, per route | Time of the second pass alone |
| --- | --- | --- | --- | --- |
| Shantae | 2, 1,930 s | 1, 1,689 s | 567,000 to 692,000 | 328 s |
| Lufia: The Legend Returns | 2, 1,632 s | 1, 1,013 s | 156,000 to 263,000 | 287 s |
| Super Mario Bros. Deluxe | 2, 857 s | 1, 560 s | 26,000 to 54,000 | 156 s |

Lufia's difference is inflated by the other conversion (its compilation took 892 s against 501 s); the last column is the steadier figure. The final
executable is the same, byte for byte: what a received path saves is conversion time. Beyond a conversion's own routes it also makes code of
another player's routes native: Shantae, on a pseudo-random route no conversion plays, went from 302,249 interpreted instructions to 41 with the
entries of another such route; Lufia had 174 to 372 left and Super Mario Bros. Deluxe none.

**Proved with two libraries** (the exchange file, not a copied library):
Super Mario Bros. Deluxe at the Standard level. The sender, from an empty library, took 2 passes (747 s) and exported its 1,438 entries as a version 3 file.
The receiver, from an empty library, imported that file and took 1 pass (500 s) with 0 interpreted instructions on its four final routes; the same comparisons
passed (30 frames from boot, 240 on each of three routes) and **its executable is the sender's, byte for byte**. It kept 1,430 of the entries as its own: the 8
that no route of its own reached again are not remembered. Times indicative (the PC was running other conversions).

## G14 checklist for the owner's play test

**Done: accepted on 27 November 2026.** Three games were delivered in `Export/Games/Game Boy Color/`, built from the merged tree: Tetris DX, Pokémon Gold, Wario Land 3. About three minutes a game: the title, a first screen
of play, sound, the colours; the quick states (F8 and F9) and the pause menu; Pokémon Gold's save after the intro; Tetris DX's two-player mode is the multiplayer's test
([MULTIPLAYER.md](MULTIPLAYER.md)). What the owner decides is whether the Game Boy Color leaves the experimental status; no number here says that a game is complete or exact.

## Where it stands

Steps 1 to 3 of [NEW_MACHINE.md](NEW_MACHINE.md) are done: the profile, the registries and the shared variant of the conversion modules (the Game Boy's output is
unchanged by it); the qualification of 21 and 22 November 2026 (the public test ROMs and the eight Color-only fixes above, the panel of seven, the extended level on
Shantae and Lufia, the saves and states checks, the Debian witness); the link cable, GBC with GBC only. The owner accepted it on 27 November 2026 and the profile is
`supported`, with its paths shared (step 5). **Open:** the optimisation of the Color's object-span path (step 4: timing is the performance specialist's, with the owner's
agreement), the online service learning `gbc` before the release, the release stamps, and a real game's two-player screen on two PCs.
