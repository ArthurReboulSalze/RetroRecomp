# Console profiles and video standards

RetroRecomp currently converts **Master System** cartridges only. Its profile
is implemented in `smsrecomp/systems/master_system.py` and registered through
`smsrecomp/systems/__init__.py`. A profile owns its cartridge extensions, ROM
reader, converter, export category and supported video modes. Unknown formats
are rejected; they are never passed through the Master System backend.

The Master System profile uses `sms` as its stable system ID, `.sms` inputs,
`Export/Games/Master System` output and an existing converter library below
`Export/datas/library`. Future profiles will receive their own output category
and library namespace. They must implement their own ROM parser, CPU/hardware
runtime, timing choices, validation and save-state model before registration.
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

The CLI accepts `--video-standard auto|pal|ntsc` for one conversion or a whole
batch. An explicit CLI choice overrides a saved or supplied profile. The
converter log and private conversion report record the effective timing and
its selection source. New game EXEs include the selected standard in Windows
version information. A regenerated game keeps the same ROM identity and
readable filename; PAL and NTSC states have distinct machine identifiers.

Validation remains separate: native coverage and reference-CPU agreement do
not prove the chosen console timing matches original hardware, whole-game
behavior, or physical latency. The user validates visual gameplay. See
[video timing and limits](VIDEO.md) and [game states](GAME_STATES.md).
