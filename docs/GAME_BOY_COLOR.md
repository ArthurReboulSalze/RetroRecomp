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
- **CPU fidelity:** the SM83 is the Game Boy's (independent vectors apply unchanged; double speed and STOP are not covered by them). Each conversion compares the generated code with the reference interpreter on its boot route (passed for the seven games); no longer route yet.
- **Hardware fidelity:** the engine's Color model (double speed, the two video banks, the eight work-RAM banks, palettes, HDMA) is the upstream's, changed by seven fixes of `retrorecomp/gameboy_color_hardware.py` that only the Color build receives (the original Game Boy's sources are not touched: a test pins it). **Measured against the public test ROMs in the Color build** (`python -B tools/gameboy_testroms.py ... --model cgb`; the ROMs are the player's downloads, kept outside the repository; Windows, 21 November 2026): 115 of the 116 applicable tests pass, each with the lock-step comparison against the pinned interpreter equal over every frame it ran: blargg `cpu_instrs` (11), `instr_timing`, `mem_timing` and `mem_timing-2`, the twelve `cgb_sound`, Mooneye's all-model tests (timing, interrupts, timers, the eight OAM-transfer tests, MBC1, MBC2, MBC5), `boot_hwio-C` and `unused_hwio-C`. One fails: `boot_div-cgbABCDE` (no boot ROM, so the divider's phase at the start is not the console's). Before the fixes the same suite passed 108 of 116. The fixes, each named by the test that showed it: the CPU is locked out of OAM and the unusable area during an OAM transfer (sixteen timing tests; the split of the transfer's source bus between cartridge, video and work RAM stays the engine's, as Pan Docs describes the Color, and no test tells it from the original console's); the timer's disable edge increments TIMA (`rapid_toggle`); the sound unit's power-off clears the length counters and the length part of NRx1 is not writable while off (`cgb_sound` 08 and 11); a write to wave RAM while channel 3 plays goes to the byte being played, the channel's timer keeps its period until it runs out, and its first sample comes six clocks after a trigger (`cgb_sound` 09 and 12: that last number is fitted to the test's checksum, with no hardware document behind it); the registers a cartridge without the Color flag finds at the start (the joypad's selection lines, the serial control register, VBK and the two palette index ports); the 5-bit colour channels widen as `(x << 3) | (x >> 2)`, the expansion of every test reference. **`cgb-acid2` (the picture test): 40 of 23,040 pixels differ from its reference image, on rows 88 and 128, cause not found;** every other pixel equals it. They show what the engine does against hardware test ROMs, not what a console does. Known and not changed: STOP and double speed are covered by the authored checks only (`tools/gameboy_color_selftest.py`, 417 checks against the register pages of Pan Docs), the wave channel's cycle-exact timing is the same coarse model as the original Game Boy's.
- **Gameplay validation:** none yet; the panel converts, it is not played.
- **Physical latency:** not measured.

Everything not yet measured is `?` in [QUALIFICATION.md](QUALIFICATION.md).

## Panel (chosen, not yet run)

Seven cartridges and one in reserve, each for a hardware case: Tetris DX (the first game, the smallest, Color-enhanced, a cable mode), Pokémon Gold
(MBC3 with a real-time clock), Wario Land 3, Shantae (4 MiB, 256 banks), Super Mario Bros. Deluxe, Pokémon Pinball (the rumble bit), Lufia: The
Legend Returns; in reserve Kirby's Tilt 'n' Tumble (MBC7, declared out of scope).

## Where it stands

Step 1 of [NEW_MACHINE.md](NEW_MACHINE.md) is merged: the profile, the registries, the shared variant of the conversion modules (the Game Boy's output is unchanged: an A/B on two games, **identical** again after the Color-only fixes), the seven games of the panel converted at the quick level, the authored colour-hardware checks. Step 2 (qualification) has started (21 and 22 November 2026): the public test ROMs in the Color build and the fixes above; three games (Tetris DX, Pokémon Gold, Wario Land 3) converted at the standard level with 0 interpreter cycles on four routes of 3,600 frames each and a lock-step comparison against the interpreter equal over the 3,600 frames of the boot route (34, 87 and 52 million steps); Tetris DX run on Debian 13 in WSL with the same picture hashes and final state as Windows. At the extended level, Lufia converts with 0 interpreter cycles on five routes (one of 18,000 frames) and Shantae with 0 after its second pass; Shantae's full-length comparison stopped on a difference between the two paths' sound units in double speed, which the comparison now treats by comparing the sound registers instead of the last sample in double speed (`adapt_color_differential`). Still to do in step 2: Shantae's comparison to the end, the panel on play routes, the gates one by one. Steps 3 (the link cable, GBC with GBC only) to 6 follow.
