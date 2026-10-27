# Console profiles and video standards

RetroRecomp has supported **Master System**, **Game Gear**, **Game Boy**,
**Nintendo NES**, **Mega Drive** (`md`) and standard **Super Nintendo** (`snes`) profiles; see
[16-bit scope](CONSOLES_16BIT.md). All profiles are registered through
`retrorecomp/systems/__init__.py`. A profile owns its cartridge extensions, ROM
reader, converter, export category and supported video modes. Unknown formats
are rejected; ZIP inputs must contain exactly one supported cartridge, including
`.sms`, `.gg`, `.gb`, `.nes`, `.bin`, `.rom`, linear `.md`/`.gen` and validated
`.sfc`/`.smc` images. The 16-bit profiles derive analysis from each cartridge;
an unknown revision does not require a catalogue entry. Hardware limits and
native/reference validation still apply before export.
Release 1.0.2 additionally supports **Neo Geo** (`ng`) in the documented
cartridge scope, making seven supported profiles after renewed gameplay tests.
Its ZIP reader identifies a multi-file cartridge by verified
CRC/layout metadata before the ordinary single-cartridge ZIP reader. `.neo`
containers use independent region hashes. Identification uses a ROM-free
catalogue bundled from pinned lithogen and needs no compiler or BIOS selection.
Conversion requires the selected, verified MVS Europe BIOS. Exports go to
`Games/Neo Geo`; shared menus, mapping, settings and quick states use the same
host as the 16-bit consoles. Optional verified AES export firmware enables F11
console/arcade switching with restart and separate saves. Other firmware and CD
remain outside this scope. Ordinary game-scoped NVRAM/card saves are independent of F8/F9;
native mapping now includes standard/CT0/KOF '98/SMA/MSLUGX/PVC families.
The final 24-cartridge campaign passes 87 packed/reference routes and six
54,000-frame controller paths. Ten additional exact sets pass 20 more routes;
34 verified cartridge/BIOS numeric records are included in the local converter.
Independent authored hardware fixtures and
fresh states/ordinary saves complement these routes. Unseen paths still report
fallback; electrical timing and full playthroughs are separate evidence.
See [Neo Geo scope](NEOGEO.md).
The experimental **Capcom CPS-1** profile (`cps1`) reads MAME/FBNeo ZIP romsets
of the standard boards. Automatic mode checks CPS-1 program ROM CRCs before the
Neo Geo and single-cartridge readers; a split clone reads its parent ZIP beside
it. Exports go to `Games/CPS-1` with the shared 16-bit host. See
[CPS-1](CPS1.md).
The experimental **Sharp X68000** profile (`x68`) converts `.dim`/`.xdf` disks
and `.m3u` disk sets with the player's own IPL and font ROM, and exports to
`Games/Sharp X68000`; see [X68000](X68000.md).

The batch queue scans mixed folders recursively and routes recognized games to
the correct console folder below `Games`, even when a custom output root is
chosen. Foreign ROM extensions appear as **Unknown console** and are skipped,
without preventing other games in the batch from converting. Automatic mode
uses the known extension or a recognizable header for `.bin`/`.rom` dumps.
For Master System and Game Gear, a recognized Sega cartridge header also
corrects a misleading `.sms`/`.gg` extension, including ZIP members;
manual mode can resolve headerless `.bin`/`.rom` files. A selected console does
not override a conflicting detected console. Headerless `.sms`/`.gg` files keep
their extension-based profile. These checks
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

The CLI accepts `--video-standard auto|pal|ntsc|dmg|mvs` for one conversion or a whole
batch. An explicit CLI choice overrides a saved or supplied profile. The
`dmg` choice applies only to Game Boy and `mvs` only to Neo Geo; Game Gear accepts only NTSC, and the
PAL/NTSC choices apply to Master System, NES and eligible 16-bit cartridges.
Mega Drive and SNES use the cartridge header and exact-ROM overrides; an incompatible
override is rejected before compilation. Multi-region Mega Drive cartridges
can select either declared standard, with fresh conversion checks. Master System records the
effective timing and its selection source in its compilation library. Game
Gear and Game Boy use their fixed console modes. New game EXEs include the
console and mode in Windows version information. A regenerated game keeps
the same ROM identity and readable filename; PAL and NTSC Master System
states have distinct machine identifiers.

Validation remains separate: native coverage and reference-CPU agreement do
not prove the chosen console timing matches original hardware, whole-game
behavior, or physical latency. The user validates visual gameplay. See
[video timing and limits](VIDEO.md) and [game states](GAME_STATES.md).
