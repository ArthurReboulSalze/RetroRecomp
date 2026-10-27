# Persistent game states

Neo Geo snapshot payload v3 records the standard/enhanced machine mode while
retaining the v2 core layout and file size. Fresh F9 restores that mode before
loading fractional clock/timer state. The immediately preceding verified v2 ABI
is explicitly accepted as standard mode, including the Metal Slug 3 crab-scene
state used to qualify this change; other unknown ABIs remain rejected. The
fractional peripheral phase is retained in the serialized master-clock remainder.
The F5 preference is separate from the snapshot in `NeoGeo.Runtime/enhanced`.

Current Neo Geo exports support ordinary MVS scores/NVRAM and a
writable memory card independently of F8/F9. Changed data after guest interaction
is atomically saved at clean exit to a game/BIOS-scoped 67,712-byte file under
`datas/saves`; opening and closing without interaction creates nothing.
Successful F9 restores both memories and can persist those restored values on
exit. The ordinary format survives runtime-ABI updates for identical cartridge,
BIOS and system/region identities. The corrected quick-state format additionally
preserves volatile PVC protection RAM: 520,517 bytes on tested PVC boards,
512,325 on the other current tested boards. See [current Neo Geo qualification](NEOGEO.md#cartridge-protections-and-ordinary-saves--14-october-2026).

The Neo Geo profile uses the shared atomic F8/F9 file
envelope, with its own system id and exact cartridge/selected-BIOS/runtime
identity. Its frame-boundary snapshot includes both CPUs, LSPC, YM2610/SSG,
RTC/timers, banks, work/save/card memory and the last displayed image. The file
is about 498 KiB in `datas/states`; reading or missing F9 creates nothing.
Fresh-process CPU/image/raw-PCM replays and invalid-state rejection are tested.
The recorded replays qualify their tested paths rather than every game. See
[Neo Geo state details and evidence](NEOGEO.md#persistent-f8f9-state).

Mega Drive ABI-11 adds pointer-free cartridge state: Sega bank-page registers,
serial EEPROM phase/lines/address/staged page and remaining guest-clock write
time. F9 validates the full cartridge before mutation, rebuilds its ROM mapping
and preserves already prefetched CPU words. Independent actual-backend fixtures
exercise busy-write and banked-code states in fresh processes. Supported older
ordinary-cartridge signatures migrate explicitly, including the preceding
ABI-10 signature; previously unsupported EEPROM/mapper images cannot invent
that cartridge history from old ordinary states. See
[EEPROM persistence](MEGADRIVE_EEPROM.md) and [banked code](MEGADRIVE_MAPPERS.md).
The two qualified ABI-11 predecessors are also recognized explicitly after
wire-state validation and the delayed H/V acknowledge correction. These changes
add no serialized fields. The 1.4.1 signature is recognized as well
(`RR16_STATE_COMPAT_ABI_23`): 1.5.0 changes the default keys of the player
shell (then `console16_host_ui.c`, and `retro_keyboard.h`), which the signature
hashed but which never reaches a serialized byte. SNES has no such list: its quick
states are bound to the exact build signature, as before. The local regression restores 57 previous states from
22 exact signatures, including cartridge states, and replays 600 frames against
the decoded CPU in fresh processes. Invalid source-latch/wire combinations are
rejected before changing guest state.

Since the player shell moved into the host kit (`native/hostkit`, see
[HOST_KIT.md](HOST_KIT.md)), a Mega Drive or Super Nintendo signature no longer
hashes the shell files of the kit: it covers the listed files directly below `native/`, and the
kit lives one level down. That one change of the list gives the first kit
release a new signature, so quick states written by earlier exports do not
load into a rebuilt export; later edits of the shell leave the signature alone.

The Mega Drive backend's ABI-10 also stores its two-word 68000 prefetch queue
in twelve pointer-free CPU-section bytes. F9 preserves already fetched words
even when RAM has changed. Existing supported signatures and ABI-9 migrate
explicitly; old files have no queue history and prime it from live memory.
See [the exact compatibility and timing scope](MEGADRIVE_PREFETCH.md#states-and-evidence).

Interrupt entry now uses the live main-CPU continuation. F8/F9 waits until its
frame writes, vector reads and target queue are complete; those host stacks are
never serialized. Pending VDP sources remain in guest state until the clocked
acknowledge. The preceding qualified ABI-10 signature is explicitly supported
with the unchanged layout, including its retained queue contents.

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
`datas/states/<game-slug>-<rom-sha12>.rrstate`. Reading quick states or trying F9
without a slot creates nothing. Ordinary cartridge RAM changes can trigger
their separate battery file. F8 flushes a temporary file before atomically
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

Declared Mega Drive cartridge SRAM is included, along with its connected byte
lanes and overlay/write-protection register. F1 retains RAM but restores the boot
register state; F9 restores both from the snapshot. A successful rewind also
updates the ordinary battery file when its restored contents differ. Missing,
invalid or rolled-back states cannot commit a partial battery change. Battery
files themselves are bound to the ROM and geometry, independently of the state
ABI. See [cartridge saves](CONSOLES_16BIT.md#mega-drive-cartridge-saves).
The compact SRAM layout changes the state ABI: older incompatible quick states
are rejected, while cartridge saves survive compatible game regeneration.

The MD backing image is cleared per raster before drawing the active area,
preventing stale H40/V30 margins from surviving H32/V28 or a fresh F9 reload.
This preserves the game's active image and does not add cropping.

Work RAM aliases share the same 64 KiB snapshot. Restoring a state preserves
the architectural PC and stack addresses, including execution through a RAM
alias. The RAM-mirror correction retains the specifically qualified preceding
ABI-2 build signature for the same pinned MD engine; it does not accept other
ROMs, timing standards, arbitrary ABI signatures or damaged payloads. All inner
section lengths, cartridge geometry and integrity checks remain active.

The VDP FIFO is part of the MD guest snapshot, including a word whose first
VRAM byte has been written and whose second byte is still pending. ABI-6 also
stores active DMA source/destination/length, partial read/write progress and
pending horizontal/vertical interrupt events. The machine loader expands five
explicitly qualified ABI-2 signatures and the preceding ABI-3 FIFO signature
with zeroed new fields; the qualified ABI-4 signature keeps its layout, migrating
a directly fetched partial DMA word into the FIFO without reading its source
again. The qualified ABI-5 signature also gains the 16-byte read buffer.
The loader preserves a pending prefetch, the first latched VRAM byte, or a
completed word that differs from current VRAM. A migrated old state starts with
an idle read buffer and fetches on its next read; it cannot invent past buffering.
The source bus can be free while destination writes remain queued, and
that tail is preserved in quick states. Other saved sections retain their layout. Arbitrary old
builds are still rejected. Original player files are never rewritten by
migration. Restore validates queue, DMA, IRQ and read-buffer bounds before changing
the machine. ABI-7 keeps that guest layout and accepts the specifically qualified
ABI-6 signature as well. Capture/load refuse an instruction in progress on
either CPU, preventing a disk state from depending on a suspended host expression.
The runtime can suspend a main or audio CPU transaction during source DMA;
F8/F9 requests are deferred until both CPUs retire. The host continues guest
frames while a request is pending, even if the menu was open, and reports the
result only after the safe capture/load. No transient refusal becomes a user
error and no coroutine stack is serialized. Reset and load rebuild the Z80's
derived execution coroutine. ABI-8 retains this pointer-free layout and also
accepts the explicitly qualified ABI-7 signature. The request-driven arbiter's
pending transfer and reservation remain live derived state; disk operations
wait until both instructions retire. The stored Z80 cycle debt rebuilds the
retired clock overshoot after reload. Twenty preceding state files across ten
signatures are qualified without rewriting their originals.

ABI-9 retains the guest section size and explicitly accepts ABI-8 too. The old
machine tail's four padding bytes now carry a flagged divider fraction and
retirement debt; zeroed old padding migrates through the preceding-signature
allowlist. Invalid new clock words are rejected before guest mutation.
Instruction overrun is retained across frame boundaries and both clocks remain
continuous through the legacy diagnostic-counter wrap. Main bus yields between
words still use live continuations; disk capture/load waits for both CPUs to
retire. The final line budget allows retirement on an available bus, while DMA
and earlier requests keep their transaction barriers. No partial C stack or
pending host request enters the snapshot.

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

## Super Nintendo cartridge saves

Ordinary Super Nintendo cartridge saves are independent of quick states.
Guest changes to battery-backed SRAM are persisted atomically under `datas/saves`,
bound to the exact ROM, mapping and RAM size. F8/F9 also captures cartridge RAM;
loading an older quick state can therefore restore older progress, which is saved
on normal exit. Missing/corrupt saves are never silently replaced by blank RAM.
See [SNES validation and boundaries](SNES.md).

## Arithmetic-phase follow-up (ABI-10 layout unchanged)

The variable arithmetic/DBcc follow-up explicitly accepts the preceding
qualified ABI-10 signature. It changes instruction-local timing only, not
serialized sections. The same queue is retained after F9; an unfinished DIV
stream read blocks F8. Thirty-two prior states across fourteen signatures
replay on native/reference paths without modifying their source files.
Current packed fresh-process states and the 448-row attract case are checked
separately; accepting an old architectural state does not recreate every
old microphase. See [phase evidence](MEGADRIVE_PREFETCH.md).
