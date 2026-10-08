# Console profiles and video standards

RetroRecomp has supported **Master System**, **Game Gear**, **Game Boy** and
**Nintendo NES** profiles, plus experimental **Mega Drive** (`md`) and
**Super Nintendo** (`snes`) profiles; see
[16-bit scope](CONSOLES_16BIT.md). All profiles are registered through
`smsrecomp/systems/__init__.py`. A profile owns its cartridge extensions, ROM
reader, converter, export category and supported video modes. Unknown formats
are rejected; ZIP inputs must contain exactly one supported cartridge, including
`.sms`, `.gg`, `.gb`, `.nes`, `.bin`, `.rom`, linear `.md`/`.gen` and validated
`.sfc`/`.smc` images. The 16-bit profiles require an exact qualified NTSC revision.

The batch queue scans mixed folders recursively and routes recognized games to
the correct console folder below `Games`, even when a custom output root is
chosen. Foreign ROM extensions appear as **Unknown console** and are skipped,
without preventing other games in the batch from converting. Automatic mode
uses the known extension or a recognizable header for `.bin`/`.rom` dumps;
manual mode can resolve headerless `.bin`/`.rom` files. A selected console does
not override a conflicting named `.sms`, `.gg` or `.gb` cartridge. These checks
identify a plausible console, not hardware fidelity or successful gameplay.

The Master System profile uses `sms` as its stable system ID, `.sms` inputs,
`Export/Games/Master System` output and an existing converter library below
`Export/datas/library`. The Game Gear profile uses `gg`, `.gg` input,
`Export/Games/Game Gear` output and an isolated library namespace. It uses
Game Gear's 12-bit CRAM and Start/stereo ports, a one-player runtime, a
160 × 144 LCD output and a separate save-state machine ID. The wider internal
VDP raster is never exposed in this version; see [Game Gear](GAME_GEAR.md).
The original Game Boy profile uses `gb`, `.gb` input,
`Export/Games/Game Boy` output, a separate SM83 compiler, a DMG 160 × 144
runtime and ROM-specific trace memory. Game Boy Color-only ROMs are rejected;
see [Game Boy](GAME_BOY.md).
The NES profile uses `nes`, `.nes` input, `Export/Games/Nintendo NES` output,
a separate 6502 compiler, its own verified ROM entry library and PAL/NTSC
runtimes. NES 2.0 timing is identified; legacy filename hints can be overridden
per game. Dendy remains unsupported; see
[NES](NES.md). Game Boy's DMG profile has no PAL/NTSC selection.
Future profiles require their own hardware/timing and validation decisions.
There is no shared assumption that every console has exactly PAL and NTSC modes.

## Cartridge region versus console timing

The [Master System cartridge header's region code](https://www.smspower.org/Development/ROMHeader)
distinguishes Japan from Export; it does **not** select a 50/60 Hz console clock.
A Europe-only filename gives
a default PAL proposal. A mixed-region filename or one without an unambiguous
Europe label defaults to NTSC. These are heuristics, not hardware detection.

Each ROM can choose `Auto`, `PAL` or `NTSC` in the converter list. `Auto` reuses
the exact ROM's saved compilation profile when it is valid for the current
engine. The selected video standard is stored separately by ROM SHA256, so it
survives an engine revision that invalidates the older compilation recipe.
Older library records recover this choice from an intact, ROM-matched recipe.
Only when neither saved choice is available does `Auto` use the filename
proposal. An explicit choice is applied to that ROM only. A supplied
`--profile` can also set:

```toml
[video]
standard = "pal"
```

The CLI accepts `--video-standard auto|pal|ntsc|dmg` for one conversion or a whole
batch. An explicit CLI choice overrides a saved or supplied profile. The
`dmg` choice applies only to Game Boy; Game Gear accepts only NTSC, and the
PAL/NTSC choices apply to Master System and NES. The 16-bit proofs accept only
NTSC. Master System records the
effective timing and its selection source in its compilation library. Game
Gear and Game Boy use their fixed console modes. New game EXEs include the
console and mode in Windows version information. A regenerated game keeps
the same ROM identity and readable filename; PAL and NTSC Master System
states have distinct machine identifiers.

Validation remains separate: native coverage and reference-CPU agreement do
not prove the chosen console timing matches original hardware, whole-game
behavior, or physical latency. The user validates visual gameplay. See
[video timing and limits](VIDEO.md) and [game states](GAME_STATES.md).
