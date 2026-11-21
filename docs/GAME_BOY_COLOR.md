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

- **Native code:** the generated SM83 code is the Game Boy's; the counted interpreter fallback is reported per CPU and per device as for the Game Boy. Not measured on a Color game yet.
- **CPU fidelity:** the SM83 is the Game Boy's (independent vectors apply unchanged; double speed and STOP are not covered by them). Not measured here yet.
- **Hardware fidelity:** the engine's Color model (double speed, the two video banks, the eight work-RAM banks, palettes, HDMA) is the upstream's and is not verified. In a first study the engine's Color model failed 17 all-model timing tests of the Mooneye suite; sixteen of them pass in a private experiment that gives the Color hardware the original console's rule for the bus during an OAM transfer. That change is not in the product, and it is to be confirmed against Color-only evidence first.
- **Gameplay validation:** none yet; the panel is chosen, not run.
- **Physical latency:** not measured.

Everything not yet measured is `?` in [QUALIFICATION.md](QUALIFICATION.md).

## Panel (chosen, not yet run)

Seven cartridges and one in reserve, each for a hardware case: Tetris DX (the first game, the smallest, Color-enhanced, a cable mode), Pokémon Gold
(MBC3 with a real-time clock), Wario Land 3, Shantae (4 MiB, 256 banks), Super Mario Bros. Deluxe, Pokémon Pinball (the rumble bit), Lufia: The
Legend Returns; in reserve Kirby's Tilt 'n' Tumble (MBC7, declared out of scope).

## Where it stands

Step 1 of [NEW_MACHINE.md](NEW_MACHINE.md): the profile, the registries, the shared variant of the conversion modules. The conversion of a first
game and the independent evidence follow.
