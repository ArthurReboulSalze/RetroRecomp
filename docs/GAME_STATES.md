# Persistent game states

The first sections describe the Master System / Game Gear format. Game Boy has its own codec;
NES now supports F8/F9 through a separate ABI-bound machine snapshot in
`datas/states/<game-slug>-<rom-sha12>.rrstate`. See the
[NES state format and validation](NES.md#controls-quick-states-and-zapper).

Starting with version 0.10.12, F8 saves one quick state and F9 loads it.
Quit, restart the same executable, and press F9 to continue at the saved point.
F8 replaces that game's existing slot; F9 without a slot displays a notice.
Both keys close an open menu or pause screen and return to gameplay.

The default native banked backend resumes from the stored guest PC and guest
stack. Loading does not introduce an interpreter step. Normal guards and
fallback accounting still apply to any subsequently executed unknown code.
The legacy function backend and reference interpreter do not support states.
Existing game executables need regeneration to gain these shortcuts.

## Storage and compatibility

States remain local beside the game executables, in:

`datas/games/<game-slug>-<rom-sha12>/<game-slug>-quicksave.state`

There is one slot per game/ROM, separate from the common control settings.
Keep the `datas` directory when moving the games. The state is about 440 KiB
with the current fixed-size format, and contains no embedded ROM or artwork.
The converter does not include states in public sources or converter releases.
From 0.10.13, reading or trying to load a state never creates its directories.
Only F8's write prepares the game directory; normal startup creates nothing.

The header identifies the exact full ROM SHA-256, state schema and hardware
model. Regenerating the same ROM with compatible schema/model retains the
slot even if native coverage or generated host addresses change. A new ROM
revision or incompatible runtime model is rejected; arbitrary compatibility
with future versions is not promised. The payload is fixed-width little-endian
data, with bounded fields and a CRC32 for accidental corruption detection.
It contains no C struct padding, pointers, function addresses or OS handles.
NTSC and PAL conversions use distinct machine identifiers, so a state saved
under one video standard cannot silently load under the other.

F8 writes a temporary file, flushes it, and atomically replaces the slot. A
failed write or replacement preserves the previous slot. F9 reads and checks
the complete file before touching the running machine. Missing, truncated,
corrupt or incompatible files display an error notice and do not load.

## Captured machine state

CPU registers (including alternate registers and internal latches), guest PC
and SP, RAM, mapper banks, VDP memory/registers/port latches/interrupt state,
scanline clocks, both raster buffers and scroll/crop latches, PSG registers,
oscillator/noise/filter phases, cycle remainder and pending synthesized audio,
and Light Phaser I/O/H-counter latches are captured after a complete CPU
instruction and its interrupt acceptance. Save/load requests from frame or
port callbacks wait for that boundary; redundant prefixes are not saved halfway.

Host keyboard/gamepad/mouse input, window/filter/language settings, SDL objects,
display pacing, queued device audio and learned compilation observations are
not machine save data. On load, queued host sound is cleared and pacing and
autofire phases restart; current physical inputs remain current. Interpreter
and execution counters stay cumulative, so rewinding cannot hide fallback use.

## Validation and limits

`python tools/gamestate_selftest.py` uses an authored ROM, without SDL video,
commercial games, screenshots or visual review. It saves in one process and
loads in another, then compares continued CPU/RAM/banks/VDP/raster/PSG/latch
state and generated PCM. It also checks rejection without mutation, native
execution after loading and preservation of diagnostic counters.

These tests validate serialization and continuation in the present runtime.
They do not establish original-hardware fidelity, physical input latency or
gameplay correctness for every game. The current mode-4, mapper and
peripheral limitations still apply. Future consoles need their own complete
machine state and model identifiers before supporting these shortcuts.

## Mega Drive and Super Nintendo

Qualified instruction-based 16-bit exports support F8/F9, with one slot in
`datas/states/<game-slug>-<rom-sha12>.rrstate`. Launching a game or trying F9
without a slot creates nothing. F8 flushes a temporary file before atomically
replacing the previous state. The header checks the complete ROM SHA-256,
console, PAL/NTSC mode, runtime ABI, bounded payload size and an integrity hash.
Different cartridges, timing modes or incompatible runtime builds are rejected.
These are Windows x64 runtime snapshots, not a format shared with other tools.

Mega Drive stores the architectural 68000 state (including STOP and stack
modes), scheduler, RAM, VDP, bus/Z80, FM/PSG chip state and pending audio events,
controller latches, additional YM timer phases and gun protocol state. Disk
states exclude the engine's in-process fiber stack. Cooperative instruction
yields wait for retirement; loading rebuilds the fiber at the stored guest PC
and preserves the guest stack instead of restoring process addresses.

SNES uses its guest snapshot codec plus pointer-free CPU/execution residue,
beam-driver resume PC and WAI latch, APU scheduling and PAL clock fractions,
audio resampler phase, memory/PPU/DSP/cartridge state and Super Scope packet
latches. The game's existing video modes and timing are retained. Host device
audio is cleared on loading, and display pacing starts again on the new timeline.
Diagnostics remain cumulative within a process; rewinding does not hide fallback.

`python tools/console16_state_selftest.py <game.exe>` checks save, process exit,
reload and replay against continuous execution, including each video/PCM frame
and final CPU/memory/hardware hashes. It also checks missing files, corruption,
ROM/region/ABI mismatches and malformed inner payloads without guest mutation.
This proves serialization and replay for the tested scenarios, not complete
gameplay or original-hardware fidelity. Regenerate games to receive this feature.
