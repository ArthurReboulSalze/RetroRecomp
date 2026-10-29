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
exercise busy-write and banked-code states in fresh processes. Quick states of
the Mega Drive and Super Nintendo are bound to the exact build signature, with
one exception: the signature of the previous release (see
[the rule](#the-rule-the-previous-release-only)). Earlier signatures that older
releases accepted (the ABI-2 to ABI-11 predecessors, the 1.4.1 and 1.5.6 keys)
are no longer recognized, so the migrations of their layouts that the
generated code still holds can no longer be reached; a previously unsupported
EEPROM/mapper image cannot invent that cartridge history from old ordinary states. See
[EEPROM persistence](MEGADRIVE_EEPROM.md) and [banked code](MEGADRIVE_MAPPERS.md).
Invalid source-latch/wire combinations are
rejected before changing guest state.

Since the player shell moved into the host kit (`native/hostkit`, see
[HOST_KIT.md](HOST_KIT.md)), a Mega Drive or Super Nintendo signature no longer
hashes the shell files of the kit: it covers the listed files directly below `native/`, and the
kit lives one level down. That one change of the list gives the first kit
release a new signature; later edits of the shell leave the signature alone.

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

**Nothing uninitialised is written (X68000, 1.6.3).** Every byte of a quick state is a value of the machine: two states of
the same game at the same moment are byte-identical. Up to 1.6.2 an X68000 state was not: the FM chip (`new MyOPM()` in the
pinned fmgen) was allocated from the heap without being cleared, fmgen's constructors and `Reset` leave members of its
operators and channels untouched, and the serializer saved them, so a window of about 1.7 KB of the OPM section held
leftovers of the process's heap, pieces of its environment text among them (the `PATH`). The chip's storage is now zeroed
when it is allocated (`tools/x68000_base74.py`, `adapt_fmg_wrap`); the layout and the size of the state do not change, and
the X68000 state key moves (X68000 states are refused between releases, as the tables below show). The other consoles' state
writers were read for the same pattern ([UPGRADES.md](UPGRADES.md#x68000-exports-in-163-host-kit-phase-3)).

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

## The rule: the previous release only

A quick state resumes only in an export built by the same release, or by the next one when that release lists the
state key of the previous one: backward compatibility is owed to the previous release and to nothing older (decision of
28 October 2026). The key is the 64-character `RR16_STATE_ABI` of `retro16_state_config.h`. The release that follows a
release writes that release's key as `RR16_STATE_COMPAT_ABI` (`console16_state.write_config` for the Mega Drive and
Super Nintendo, `neogeo_build.state_config`, `cps1_build.state_config`; `native/console16_state.c` accepts the keys a
build defines, next to its own) after checking, with a real state of a real export, that the serialized bytes are the
same. It drops the keys of older releases. The tree of 1.6.0 listed none: its states resumed in 1.6.0 exports only. The
tree of 1.6.1 listed the 1.6.0 key of the Mega Drive, the Neo Geo and CPS-1 (Windows), as
[below](#states-written-by-release-160). The tree of 1.6.2 listed the 1.6.1 key of those three and of the Super Nintendo
(Windows) and dropped the 1.6.0 ones, as [below](#states-written-by-release-161). The tree of 1.6.3 lists the 1.6.2 key
of the same four (Windows) and drops the 1.6.1 ones, as [below](#states-written-by-release-162). A state that is not
accepted is refused cleanly by the loader, never loaded wrongly; a player coming from an older release starts the game
again from its own saves.

## States written by release 1.5.6 (history)

This section is the dated record of the 1.6.0 work; the keys it names are no longer listed by any build (see the rule
above), so a 1.5.6 state no longer loads in 1.6.0 or after.

1.6.0 changes the quick-state key of the Mega Drive, Super Nintendo, Neo Geo and CPS-1 (the shell files of the host kit are
no longer part of the key, the build modules of CPS-1 changed). What each key hashes is not what is serialized, so what
loads is decided one console at a time, and always by a real state written by a real 1.5.6 export (27 October 2026,
Windows, `.build/legacy-156-20261027/`, run headless, nothing on screen). A state that is not accepted is refused
cleanly by the loader (exit code of the headless run, notice in the player), never loaded wrongly.

| Console | State of a 1.5.6 export in a 1.6.0 export | Proof |
| --- | --- | --- |
| Mega Drive | **loads (Windows)**, through `RR16_STATE_COMPAT_ABI_24` (`console16_state.MD_STATE_ABI_156`, found in the real exports' `retro16_state_config.h`) | `tools/state16_cross.py --one-way` on Alex Kidd in the Enchanted Castle, 300 frames replayed after the state: a state written by the 1.5.6 export after a warm-up of 600 frames resumes in the upgraded export with the same trace over the 900 frames compared (warm-up and replay) and the same final guest state, and the same after a warm-up of 900 frames (1,200 frames compared); the state is 206,953 bytes both ways (logs `states-md-w600.log` and `states-md-w900.log` in the evidence folder). The 1.6.0 export built before the key was added refuses the same state (exit 7), so the key is what makes it load |
| Neo Geo | **loads (Windows)**, through `RR16_STATE_COMPAT_ABI_24` (`neogeo_build.STATE_ABI_156`) | `tools/neogeo_state_cross.py --one-way` on Puzzled (Joy Joy Kid), with the tool's default route: a state written at frame 2,600 by the 1.5.6 export resumes in the 1.6.0 export, same trace over the 2,900 frames compared (2,600 warm-up and 300 replayed), 512,325 bytes. The serialized state files (`neogeo_state.c`, the LSPC and YM state includes) are byte-identical since the tag |
| Super Nintendo | **refused** | policy: SNES quick states are bound to the exact build signature (the engine changed after 1.5.2); the key moves in 1.6.0 and no compatibility key is added. Not run on a real SNES export |
| CPS-1 | **loads (Windows)**, through `RR16_STATE_COMPAT_ABI_24` (`cps1_build.LEGACY_STATE_ABI_156`; `cps1_knowledge.GENERATOR_REVISION` raised to 2 for it: no CPS-1 path was qualified yet) | the serialized bytes did not change: a 1.5.6 Nemo state and the 1.6.0 one have the same size (691,390 bytes) and differ only in the 64 bytes of the key in the header. A state written by the real 1.5.6 export (saved at frame 600) resumes in the upgraded export built with the key, headless: the 300 frames after it equal the 1.5.6 export's own timeline (`.build/legacy-156-20261027/cps1x-key`), and `tools/neogeo_state_cross.py --cps1 --one-way` gives the same trace over 900 frames. The upgraded export built without the key refuses it (exit 4, `cps1x-nokey`) |
| Master System, Game Gear, Game Boy, NES | not run | the generated sources of 1.5.6 and 1.6.0 are identical (docs/UPGRADES.md); their keys depend on those files. The quick states of the Master System and Game Gear cannot be saved headless, so they were not exercised |
| X68000 | refused | the key carries the compiler's identity by design; X68000 exports are converted in full |

Mega Drive: at frame 1,200 of the cross-check route the 1.5.6 exports themselves refuse to write a state (the writer exits 8,
for Alex Kidd in the Enchanted Castle as for Art Alive, whose export also runs mostly in the interpreter); the result above is
therefore taken at frames 600 and 900, where they write one. This proves serialization and resume on these routes, not
gameplay or hardware fidelity.

The compatibility keys of the Mega Drive, Neo Geo and CPS-1 (and the 1.4.1 ones) are written only on Windows
(`console16_state.py`, `neogeo_build.py`, `cps1_build.py`: `os.name == 'nt'`): the key of a Linux build also hashes its target, which no
Linux 1.5.6 key was recorded for, so a state written by a Linux 1.5.6 export is refused by a 1.6.0 export (cleanly, as above). Not
run on Linux.

## States written by release 1.6.0

*History: since 1.6.2 these keys are no longer listed by any build (see the rule above), so a state written by a 1.6.0
export loads in 1.6.1 exports and not in 1.6.2 ones.*

1.6.1 changes the quick-state key of three consoles. Mega Drive: `native/md_z80_bus.inc` (the deferred sound-CPU payment,
see [UPGRADES.md](UPGRADES.md#mega-drive-exports-of-160-in-161)) and `native/md_boundary_checks.c` are listed native files of
the console, and the key hashes them. Neo Geo and CPS-1: their keys hash the fingerprints of `neogeo_build` and
`cps1_build`, which changed (packing notice, removal of the pre-1.6.0 keys, and now the compatibility line itself). The
serialized states did not change. The release adds the 1.6.0 key of each as a compatibility key, so the states of the
previous release keep loading (the rule: the previous release only). The Super Nintendo key did not change.

| Console | Key written by 1.6.0 (Windows) | Where it is listed |
| --- | --- | --- |
| Mega Drive | `2832912487d66aa2f846a6c48ca7248976adec158ee407b8fcb3a509f514d6c8` | `console16_state.MD_STATE_ABI_160`, written by `write_config` as `RR16_STATE_COMPAT_ABI` |
| Neo Geo | `6e0721d152aa17f6bec321b960177773b7e9eaf06c29cc350b39f3a4b91fc46a` | `neogeo_build.STATE_ABI_160`, in `state_config` |
| CPS-1 | `bc842183c642e70f5c9a43570d685ce8ea1efa826c7f21e8268c4a6abfb6fa9d` | `cps1_build.LEGACY_STATE_ABI_160`, in `state_config` |
| Super Nintendo | `366aa5f94b8c57080255e2540bc513bc8e875e8b03fc8fb02bef344b2c05ddf1`, the same key in 1.6.1 | none needed: the key did not move |
| Master System, Game Gear, Game Boy, NES | no key of this kind | nothing to list |
| X68000 | refused (the key carries the compiler's identity by design) | none |

**Where the keys come from.** Each key was computed from the `v1.6.0` tag (`git archive`, Python 3.14.5) by calling its
console's own `write_config` or `state_config` on a fixed synthetic project: the keys do not depend on the ROM, only on
the listed native files, the console's module fingerprints and its repository revisions. The same call run on the
`v1.5.6` tag gives the three 1.5.6 keys of the table above, which were found in real 1.5.6 exports (`9866fc8d...` Mega
Drive, `fa66982c...` Neo Geo, `a04dc60c...` CPS-1): the computation is the one real exports follow. `Export/` holds no
generated `retro16_state_config.h` of a 1.6.0 export (the build folders are removed when a game is published), and its
quick states were written by earlier releases, so no real 1.6.0 key was read back.

**What was checked about the layout.** The serialized bytes are fixed by the state files and by the layout versions, none of
which moved between the tag and 1.6.1: `PORTABLE_STATE_ABI` is 2 and `MD_PORTABLE_STATE_ABI` is 11 in both trees, and below
`native/` only `md_z80_bus.inc` and `md_boundary_checks.c` differ (the fix touches transient scheduling variables that no
state file reads; the Neo Geo and CPS-1 state files, `console16_state.c` and `md_portable_state.inc` are byte-identical).
`tests/test_legacy_compat.py` pins the three keys, the one-line-per-console output on Windows and no line elsewhere.

**Not run.** The proof the rule asks for, a real state written by a real 1.6.0 export resuming in a 1.6.1 export
(`tools/state16_cross.py`, `tools/neogeo_state_cross.py --one-way`, `--cps1`), needs conversions of both releases and was
not run for these lines; the table is the claim "same layout" resting on the files above, not a replay. Linux: the key of a
Linux build also hashes its target and no Linux 1.6.0 key was recorded, so the lines are written on Windows only and a
state written by a Linux 1.6.0 export is refused cleanly.

## States written by release 1.6.1

*History: since 1.6.3 these keys are no longer listed by any build (see the rule above), so a state written by a 1.6.1
export loads in 1.6.2 exports and not in 1.6.3 ones.*

1.6.2 changes the quick-state key of all four consoles that list one, for two reasons. Mega Drive and Super Nintendo:
`native/runtime_catalog.inc`, the eight-language runtime catalogue (five strings of the pad slot policy join it, see
[UPGRADES.md](UPGRADES.md#exports-of-161-in-162-host-kit-f2-capture-and-autofire-notice)), is a listed native file of
both consoles and the key hashes it. Neo Geo and CPS-1: their keys hash the fingerprints of `neogeo_build` and
`cps1_build`, which are edited by this very rollover (the 1.6.0 constants and lines are removed and replaced by the
1.6.1 ones); the catalogue is not among their hashed files. `cps1_build.py` is a pinned CPS-1 generator source, so
`cps1_knowledge.GENERATOR_REVISION` goes to 5 and `tests/cps1_generator_pins.json` follows, as for the 1.6.1 line (nothing
a RAM path could notice moved, same cost as then). The serialized states did not change: the layout versions
(`PORTABLE_STATE_ABI` 2, `MD_PORTABLE_STATE_ABI` 11) and every state source file are those of the `v1.6.1` tag. The
tree of 1.6.2 therefore adds the 1.6.1 key of each console as a compatibility key, so the states of the previous
release keep loading (the rule: the previous release only), and drops the 1.6.0 keys: a state written by a 1.6.0 export
is refused cleanly. The Super Nintendo gets its first compatibility line, because its key, unchanged since 1.6.0, moves
now; the key of 1.6.1 is the same as the one of 1.6.0.

| Console | Key written by 1.6.1 (Windows) | Where it is listed |
| --- | --- | --- |
| Mega Drive | `fb6d191a2b8c3975e4a69560fb204ad1e79c8726bb55f448e15e2d201550c959` | `console16_state.MD_STATE_ABI_161`, written by `write_config` as `RR16_STATE_COMPAT_ABI` |
| Super Nintendo | `366aa5f94b8c57080255e2540bc513bc8e875e8b03fc8fb02bef344b2c05ddf1` (also the 1.6.0 key) | `console16_state.SNES_STATE_ABI_161`, written by `write_config` |
| Neo Geo | `5c25722def19e560b4cbce7c7424d3c2f3317a2a91f6d3d3f184f16a46fdc474` | `neogeo_build.STATE_ABI_161`, in `state_config` |
| CPS-1 | `f745f993a28521fa17dbe84332964b677a3ab35f5bbb77b7f7c1fcb95cd902ee` | `cps1_build.LEGACY_STATE_ABI_161`, in `state_config` |
| Master System, Game Gear, Game Boy, NES | no key of this kind | nothing to list |
| X68000 | refused (the key carries the compiler's identity by design) | none |

The compatibility lines are written on Windows only (`os.name == 'nt'`): the key of a Linux build also hashes its target,
and no Linux 1.6.1 key was recorded. **Where the keys come from**: as for 1.6.0, each key was computed from the `v1.6.1`
tag by calling the console's own `write_config` or `state_config` on a fixed synthetic project (Python 3.14.5);
`tests/test_legacy_compat.py` pins them. No state of a real 1.6.1 export was resumed in a 1.6.2 export for this
rollover: it proves which keys are accepted, not a cross-run of the serialized bytes (not run).

## States written by release 1.6.2

1.6.3 changes the quick-state key of all four consoles that list one (the keys computed from the `v1.6.2` tag and from the
tree of 1.6.3 differ on each of them), for two reasons. Mega Drive and Super Nintendo: the key hashes the native files
each console lists (`state_native_files`), and the host kit work of 1.6.3 edited that list: the shell of the Master System
and Game Gear (`host.c`, `controls.c/.h`, `ui.c/.h`) left it, and `game_options.h`, `audio_output.inc`,
`runtime_catalog.inc`, `CMakeLists.txt` and the checks (`host_checks.c`, `presentation_checks.c`, `lazy_data_checks.c`,
`game_options_checks.c`, `audio_checks.c`) changed. Neo Geo and CPS-1: their keys hash the fingerprints of `neogeo_build` and
`cps1_build`, which now write their files and patch the pinned sources through `conversion_common` (the CPS-1 files are
byte for byte those of the previous generator revision on a real conversion, as the comment of
`cps1_knowledge.GENERATOR_REVISION` records) and are edited again by this very rollover (the 1.6.1 constants and lines
are replaced by the 1.6.2 ones). None of the state files nor the layout versions moved: `PORTABLE_STATE_ABI` is 2 and
`MD_PORTABLE_STATE_ABI` is 11 in both trees, and `console16_state.c/.h`, `md_portable_state.inc`, `neogeo_state.c`,
`neogeo_state_validate.c`, `neogeo_lspc_state.inc`, `neogeo_ym_state.inc`, `cps1_machine.c`, `cps1_oki.c`, `cps1_opm.cpp`,
`neogeo_host.c` and `cps1_host.c` have no difference between the tag and this tree (checked with a diff of the two
trees). The tree of 1.6.3 therefore adds the 1.6.2 key of each console as a compatibility key, so the states of the
previous release keep loading (the rule: the previous release only), and drops the 1.6.1 keys: a state written by a
1.6.1 export is refused cleanly. The Super Nintendo key of 1.6.1, which was also the key of 1.6.0, is gone for good.

| Console | Key written by 1.6.2 (Windows) | Moved in 1.6.3 | Where it is listed |
| --- | --- | --- | --- |
| Mega Drive | `7943c469d11b059b7cf2a6ff4597dc2809d25cd5b093752d837c2a4d8c661948` | yes | `console16_state.MD_STATE_ABI_162`, written by `write_config` as `RR16_STATE_COMPAT_ABI` |
| Super Nintendo | `b9fbf76dc2cc49459420ff111d143c64c72cd72b440a1264d91b38be21bcb5c4` | yes | `console16_state.SNES_STATE_ABI_162`, written by `write_config` |
| Neo Geo | `0d361a5f02f0f6838bf555dce0b89dd8fa1dce8cd23045fd2811653fec0720df` | yes | `neogeo_build.STATE_ABI_162`, in `state_config` |
| CPS-1 | `b24053cfe60639a1a464f74e63d155dcb351ac0713796e554937edd65821d8e9` | yes | `cps1_build.LEGACY_STATE_ABI_162`, in `state_config` |
| Master System, Game Gear, Game Boy | no key of this kind | none | nothing to list: a state of an export of 1.6.2 loads in an export of 1.6.3 and the reverse ([UPGRADES.md](UPGRADES.md#master-system-and-game-gear-exports-in-163-host-kit-phase-4), [Game Boy](UPGRADES.md#game-boy-exports-in-163-host-kit-phase-5)) |
| NES | `RR_NES_STATE_ABI`, no compatibility line | no: every input it hashes (`nes_machine.py`, the state files, `retro_nes.h`, the PPU includes) is unchanged since the tag | nothing to list; not recomputed from a real build |
| X68000 | refused (the key carries the compiler's identity by design, and `reference_host.c` moved onto the host kit) | yes | none |

The compatibility lines are written on Windows only (`os.name == 'nt'`): the key of a Linux build also hashes its target,
and no Linux 1.6.2 key was recorded. **Where the keys come from**: as for 1.6.1, each key was computed from the `v1.6.2`
tag (the same archive the legacy game stamps were computed from, [UPGRADES.md](UPGRADES.md#exports-of-162-in-163)) by
calling the console's own `write_config` or `state_config` on a fixed synthetic project (Python 3.14.5, the Python of the
packaged Windows converter); `tests/test_legacy_compat.py` pins them. Only the Mega Drive key hashes files alone; the
Super Nintendo, Neo Geo and CPS-1 ones also hash the bytecode fingerprints of their modules, so they are the Python 3.14
Windows converter's keys. **Not run:** no state of a real 1.6.2 export was resumed in a 1.6.3 export for this
rollover. It proves which keys are accepted, from the files above, not a cross-run of the serialized bytes
(`tools/state16_cross.py`, `tools/neogeo_state_cross.py --one-way`, `--cps1`); it measures neither gameplay validation nor
hardware fidelity.

`cps1_build.py` is a pinned CPS-1 generator source and this rollover edits it: `cps1_knowledge.GENERATOR_REVISION` stays 6
(the revision 1.6.3 already needed for the 68000 shifts and the shared helpers, never shipped), and
`tests/cps1_generator_pins.json` follows with the new digest; the comment of the revision says so.
