# Experimental Mega Drive and Super Nintendo profiles

RetroRecomp includes two separate experimental console profiles. This
does **not** enable arbitrary Mega Drive or SNES games. A cartridge is identified
from its console header, then its SHA-256 must match a qualified game revision
before code generation starts. A different revision, unqualified timing mode or unsupported
title is rejected rather than compiled with another game's roots.
This document describes the development tree after release 0.21.0, including
27 Mega Drive and 12 Super Nintendo revisions, native instruction paths, resolution-aware scanlines
and three qualified lightgun cartridges;
see [16-bit guns, controls and verification scope](GUNS_16BIT.md).

| Profile | Qualified cartridge | Timing | Visible image |
| --- | --- | --- | --- |
| Mega Drive | Sonic the Hedgehog, JUE revision 00, CRC32 F9394E97 | NTSC | 320 × 224 |
| Mega Drive | Columns, CRC32 D783C244 | NTSC | 320 × 224 |
| Mega Drive | Golden Axe, CRC32 665D7DF9 | NTSC | 256 × 224 (H32) |
| Mega Drive | Castle of Illusion, CRC32 BA4E9FD0 | NTSC | 320 × 224 |
| Mega Drive | Menacer 6-Game Cartridge, CRC32 936B85F7 | NTSC | 320 × 224 |
| Mega Drive | T2 - The Arcade Game, CRC32 A1264F17 | NTSC | 320 × 224 |
| Mega Drive | Aladdin, Japan, CRC32 FB5AACF0 | NTSC | 320 × 224 |
| Mega Drive | Streets of Rage 2, USA, CRC32 E01FA526 | NTSC | 320 × 224 |
| Mega Drive | The Revenge of Shinobi, JUE, CRC32 4D35EBE4 | NTSC tested | 320 × 224 |
| Mega Drive | Gunstar Heroes, Japan, CRC32 1CFD0383 | NTSC Japan | 320 × 224 |
| Mega Drive | Ecco the Dolphin, USA, CRC32 45547390 | NTSC | 320 × 224 |
| Mega Drive | Desert Strike - Return to the Gulf, USA, CRC32 67A9860B | NTSC | 320 × 224 |
| Mega Drive | Beyond Oasis, USA, CRC32 C4728225 | NTSC | 320 × 224 |
| Mega Drive | Comix Zone, Japan, CRC32 7A6027B8 | NTSC Japan | 320 × 224 |
| Mega Drive | Contra - Hard Corps, USA/Japan, CRC32 C579F45E | NTSC | 320 × 224 |
| Mega Drive | Dynamite Headdy, USA/Europe, CRC32 3DFEEB77 | NTSC tested | 320 × 224 |
| Mega Drive | Rocket Knight Adventures, Japan, CRC32 D1C8C1C5 | NTSC Japan | 256/320 × 224 |
| Mega Drive | Street Fighter II' Plus - Champion Edition, Japan, CRC32 2E487EE3 | NTSC Japan | 256 × 224 |
| Mega Drive | Thunder Force IV, Japan, CRC32 8D606480 | NTSC Japan | 320 × 224 |
| Mega Drive | ToeJam & Earl, USA, CRC32 7A588F4B | NTSC | 320 × 224 |
| Mega Drive | Vectorman, multi-region, CRC32 D38B3354 | NTSC tested | 320 × 224 |
| Mega Drive | Wonder Boy in Monster World, USA/Europe, CRC32 1592F5B0 | NTSC tested | 256 × 224 |
| Mega Drive | Sonic the Hedgehog 2, CRC32 7B905383 | NTSC tested | 320 × 224 |
| Mega Drive | Earthworm Jim, CRC32 1C07B337 | PAL | 320 × 224 |
| Mega Drive | Mortal Kombat II, CRC32 A9E013D8 | NTSC tested, six-button pad | 320 × 224 |
| Mega Drive | Road Rash II, CRC32 0876E992 | NTSC tested | 320 × 224 |
| Mega Drive | Shining Force II, CRC32 83CB46D1 | PAL | 320 × 224 |
| Super Nintendo | Super Mario World, USA, CRC32 B19ED489 | NTSC | 256 × 224 |
| Super Nintendo | Super Scope 6, USA, CRC32 B141EA99 | NTSC | 256 × 224 |
| Super Nintendo | The Legend of Zelda - A Link to the Past, USA, CRC32 777AAC2F | NTSC LoROM | 256 × 224 |
| Super Nintendo | Super Metroid, Japan/USA, CRC32 D63ED5F8 | NTSC LoROM | 256 × 224 |
| Super Nintendo | Donkey Kong Country, USA, CRC32 762AF827 | NTSC HiROM | 256 × 224 |
| Super Nintendo | Super Castlevania IV, USA, CRC32 B64FFB12 | NTSC LoROM | 256 × 224 |
| Super Nintendo | F-Zero, USA, CRC32 AA0E31DE | NTSC LoROM | 256 × 224 |
| Super Nintendo | Mega Man X, USA, CRC32 DED53C64 | NTSC LoROM | 256 × 224 |
| Super Nintendo | Chrono Trigger, USA, CRC32 2D206BF7 | NTSC HiROM | 256 × 224 |
| Super Nintendo | Super Bomberman, USA, CRC32 63A8E2C6 | NTSC HiROM | 256 × 224 |
| Super Nintendo | Super Mario All-Stars, USA, CRC32 925637C7 | NTSC LoROM | 256 × 224 |
| Super Nintendo | Pop'n TwinBee, Europe, CRC32 588A9707 | PAL LoROM | 256 × 224 |

The original ROMs remain read-only. Linear `.md`/`.gen` and validated
`.sfc`/`.smc` images, single-cartridge ZIPs, and identifiable `.bin`/`.rom`
files are recognized. A SNES copier header is removed only from the in-memory
build input. Interleaved SMD and additional unqualified cartridge profiles
are not enabled in these proofs. No ROM patches or widescreen mode are applied.
Mega Drive region headers take precedence over misleading filenames: a
PAL-only header cannot be forced to NTSC. A reset
stack pointer of zero is valid: the first predecrement push wraps onto work RAM.
Region parsing accepts the original J/U/E letters and the later ASCII hex mask
in the three defined region bytes. Reserved header bytes do not affect it;
unknown codes are reported and rejected before conversion. Three exact legacy
revisions have explicit qualified NTSC region hints: Columns and Golden Axe
have empty headers; Castle of Illusion uses the older US code. Their complete
SHA-256 identities bind these exceptions; a filename or modified ROM cannot
inherit them. A lone E retains
the original PAL meaning. Japan-only cartridges now select the domestic NTSC
version register; multi-region cartridges prefer overseas NTSC when available.
The ROM's region checks stay intact. See the author's
[region-header reference](https://plutiedev.com/rom-header).

Qualified PAL Mega Drive builds use 313 raster lines and a 53,203,424 Hz master
clock; NTSC builds use 262 lines and 53,693,175 Hz. Video, audio-chip clocks,
console region/status bits and the host deadline use the same selected standard.
One raster spans 3,420 master clocks per line, yielding approximately 49.70146
PAL or 59.92274 NTSC frames per second. The progressive vertical-counter jump
sequences are covered by authored fixtures. These checks do not certify
sub-scanline CPU budgets, DMA/FIFO contention or interlaced/NTSC V30 behavior.
See [hardware measurements](https://www.plutiedev.com/mirror/kabuto-hardware-notes).
The two new PAL images are named USA in the supplied collection; qualification
uses their actual cartridge bytes. Multi-region revisions remain NTSC-only
unless that exact profile has also passed PAL checks.

### Super Nintendo PAL timing

The first European revision uses 312 lines of 1,364 master clocks and
a 21,281,370 Hz video oscillator: approximately 50.00698 fields per second.
The PPU's $213F region bit, raster journal chronology, vblank polling and IRQ
comparators use the same region. PAL includes the longer vblank interval;
an authored interrupt on line 300 verifies that it is not truncated at the
NTSC field boundary.

The SPC oscillator remains 1,025,280 Hz, producing 32,040 native DSP samples
per second. Fractional cycles carry between host iterations, including long
loaders; switching to PAL does not slow the sound driver to 50/60 of its
original rate. Existing qualified NTSC audio scheduling is retained in this
stage. Timing constants were checked against the primary ares implementation:
[system clocks](https://github.com/ares-emulator/ares/blob/master/ares/sfc/system/system.cpp),
[APU oscillator](https://github.com/ares-emulator/ares/blob/master/ares/sfc/system/system.hpp)
and [PPU field geometry](https://github.com/ares-emulator/ares/blob/master/ares/sfc/ppu/ppu.cpp).

This initial PAL scope is progressive 256 x 224. Overscan, interlace and
512-pixel modes are not qualified. The converter checks the actual active
raster, excluding screen-off register initialization. Long qualification
runs also require picture and PCM activity, in addition to internal
native/reference agreement. A silent or unsupported-display result must
not become a qualified export merely because both CPU paths agree.

The PAL cartridge passes demo/play tests of 3,600 images and a varied
6,000-image input replay with zero interpreted main or sound CPU operations.
These checks establish the tested paths and internal agreement; independent
full hardware fidelity, physical latency and complete gameplay remain separate.

Additional European probes did not qualify: Terranigma remained silent, while
The Firemen and Smash Tennis exercised hires on active lines during extended
input replays. These results identify work for the audio/512-pixel stages;
none of these cartridges is enabled or exported by this PAL stage.

## Shared game interface

Both profiles use RetroRecomp's SDL presentation and menu renderer: H help,
P pause, F1 restart, F2 keyboard/gamepad mapping, F3 nearest/linear/Scale2x/
scanlines, F4 window/integer fullscreen/aspect-preserving fullscreen,
F6 autofire and F7 English/French. Two controller ports are wired; the
selected game determines whether two-player gameplay exists. Controller
left-stick click pauses; player one's right-stick click restarts.
Gun games use the mouse on port 2, a small red cross, and F5 gun settings.

The scanline filter places a translucent gap between every guest raster row,
using the actual displayed height. Its cached mask accounts for fractional
fullscreen scaling and HiDPI output, without darkening alternate game rows.
Below 2x vertical scaling, the image stays intact because those gaps cannot
be resolved. Only presentation changes; game pixels and timing remain untouched.

Mega Drive defaults to arrows, W/X/C for A/B/C and Enter for Start. The qualified
Street Fighter II' Plus and Mortal Kombat II profiles expose X/Y/Z and Mode in
F2, using A/S/D and right Shift by default. Their two controller ports use the
six-button protocol; other profiles retain three-button pads. SNES
defaults to arrows, W/X/A/S for A/B/X/Y, Q/E for L/R, right Shift for Select
and Enter for Start. Player two uses the numeric keypad and has no reset
shortcut. F2 exposes the console's actual controls.
Letter defaults and F2 key labels follow the active keyboard layout,
including AZERTY. Saved custom mappings retain their physical key positions.

F8/F9 quick states are implemented for the qualified instruction-based profiles,
including PAL. They survive closing and restarting the game and are stored in
`datas/states/<game-slug>-<rom-sha12>.rrstate`. A runtime ABI or ROM mismatch is
rejected. See [captured state and validation](GAME_STATES.md#mega-drive-and-super-nintendo).
Independent SNES cartridge battery-save files remain unimplemented; use F8/F9
to preserve progress in these builds.

Ordinary launch/quit creates no data directory or log. Changing a saved
setting creates `datas/Retro-Recomp.ini` beside the games, with separate
Mega Drive and SNES control sections. Probe logs belong to the converter's
private build directories and are created only by explicit conversion tests.

## Native coverage and validation

All qualified Mega Drive games use instruction-level AOT.
Each known ROM instruction emits its selected C operation with literal
operands. Execution follows the real 68000 PC and stack, including computed
jumps, changed return addresses and hardware-shaped interrupt frames. It does
not dispatch covered instructions through an opcode interpreter. This avoids
the earlier C-function call model's unsafe stack exits and Sonic-specific
callbacks. The sound Z80 now has its own guarded instruction-AOT path.

Before probing, a bounded work queue follows direct calls, both conditional
branches and fallthrough from verified instruction starts. It stops at returns,
unknown indirect targets and invalid bytes. This extends static coverage; it
does not claim that arbitrary ROM data is code or cover every computed target.
On the three new revisions it added hundreds of instructions, but did not
reduce the measured first-pass fallback or the two-pass cold conversion count.

The converter's demo/play probes collect missing ROM instruction starts and
RAM code variants. Later passes regenerate static code from those observations.
Every 68000 RAM variant requires an exact live match of all instruction bytes;
unseen or modified code uses the visible reference fallback. Records are scoped
to the exact ROM hash in the converter's `datas/library/md` namespace. Generated
games keep diagnostic observations in memory and never write a learning library.
H32 and H40 output uses the VDP's active 256- or 320-pixel width at presentation.

Qualified SNES cartridges use a separate 65816 adapter. The converter selects one
compiled operation for every physical ROM byte and writes a ROM-PC dispatch
map. LoROM and HiROM mirrors follow the live cartridge mapping. Non-power-of-two
images match the loader's repeated final block: a 3 MiB image repeats its final
MiB in the fourth MiB. Both original image size and padded storage size are
checked without changing the supplied ROM. Covered operations bypass
the opcode-switch interpreter while retaining the real PC, stack, opcode-fetch
timing and live operand reads. Register-width flags, bank wrapping and memory
accesses therefore retain the pinned engine's semantics. Operands are not
specialized into literals as they are in the Mega Drive adapter.

SNES RAM helpers are learned during converter probes, then compiled with an
exact PC and four-byte live-code guard, covering the longest 65816 instruction.
Changed bytes or an unobserved helper use the counted interpreter. Up to
2,048 variants are stored in `datas/library/snes/<rom-sha256>/native-ram.json`.
Generated games never persist learning observations. The SPC700 sound processor
also uses guarded native operations, described below. Both native and reference tests use the real PC/stack
instruction scheduler instead of the previous paired C-call bridge.

The converter records interpreted main-CPU **opcodes**, separately from the
sound-CPU opcode and cycle counters. Main-CPU percentages refer only to that
CPU; both sound processors have separate cycle-based percentages. The window title
signals interpreter use, including the sound CPU, and H explains that status.

Demo and scripted-play probes cover 3,600 frames per scenario. Columns, Golden
Axe and Castle of Illusion already reached **zero interpreted 68000 instructions**
with matching internal reference results in release 0.18.0. The new Sonic path
now reaches the same result after learning four missing ROM starts in a second
pass; Golden Axe also passes a repeat check after this shared-path change.
Mega Drive comparisons cover the visible-frame sequence, final CPU registers,
PC, RAM, VRAM, CRAM, VSRAM, VDP registers and retired instruction totals.
They now also require matching FM/PSG sample counts and hashes, audio activity,
Z80 registers, PC, RAM, total instructions/cycles and CPU-visible timer state.
Main-CPU comparisons also include SR, both stack pointers and the STOP latch. Constant nonzero DAC output is not
counted as changing audio. A shared silent-driver bug can still match a
reference, so dedicated sound regressions also require sustained activity.
Authored Mega Drive fixtures now exercise 7,872 instruction/state comparisons,
guest-stack return modification, RTE frames, byte stack alignment and
self-modifying RAM guard rejection. Additional authored checks exercise static
control-flow discovery and timer start/stop, overflow, flags, reload and long
clock spans. The three new revisions reach zero interpreted 68000 instructions
in both 3,600-frame scenarios, with complete CPU/video/PCM reference agreement.

The common 68000 compiler also implements all four MOVEP transfers. Byte accesses
visit alternating bus addresses, word loads preserve the upper half of the
destination register, and flags remain unchanged. Independent expectations
check signed displacements, odd addresses, 24-bit bus wrap and the 16/24-clock
cost, in addition to the native/reference comparison. See Motorola's
[programming reference](https://www.nxp.com/docs/en/reference-manual/M68000PRM.pdf).

The subsequent qualification of Gunstar Heroes, Ecco and Desert Strike also
reaches zero interpreted 68000 opcodes in both 3,600-frame scenarios. Gunstar
initially passed CPU agreement while remaining on the game's region-lock
screen: both paths presented the wrong overseas console to a Japanese ROM.
Selecting domestic hardware changes the video sequence, restores input-driven
progression and produces changing FM/PSG samples over 3,040/2,968 play frames.
Ecco and Desert Strike produce changing FM samples over 3,296 and 3,243 play
frames respectively. These are numerical activity checks, not listening tests.
The conversion comparison now includes the console version register.

Ecco also exposed an unimplemented TRAP #0 in its RAM interrupt stub. All sixteen
TRAP forms are now translated to native operations that fetch
the live vector, clear the trace bit and preserve the old SR/following PC on the
guest's six-byte exception frame. RTE unwinds that frame, including nesting and
stack wrap. Independent fixture expectations check the 34-clock TRAP cost and
frame contents against Motorola's
[MC68000 manual, sections 6.3.5 and 8.12](https://www.nxp.com/docs/en/reference-manual/MC68000UM.pdf).
Further cartridge checks exposed a user-mode TRAP in Street Fighter II and
STOP in Thunder Force IV, both of which halted the earlier runtime at boot.
SR writes now select the correct active stack; TRAP and accepted IRQs switch
to SSP before writing their frame. RTE reads the entire frame on SSP before
restoring user mode. The pinned active/shadow stack layout is retained in
rollback snapshots. STOP loads SR, retires once and advances the scheduler
without fetching more instructions until an accepted IRQ wakes it. The
STOP latch is also saved and restored by the CPU snapshot section.
Independent fixtures cover mode transitions, IRQ/TRAP frames, STOP waiting,
instruction counts and snapshot restoration against the
[MC68000 manual, sections 6.1–6.3 and 8.11](https://www.nxp.com/docs/en/reference-manual/MC68000UM.pdf).
Privileged instructions encountered in user mode are explicitly refused;
their privilege-violation exceptions are not implemented. Trace and complete
bus/address-error handling also remain unimplemented. This is not complete
68000 exception support. RAM stubs retain exact-byte guards and visible fallback.

## Mega Drive sound scheduling

Every instruction-AOT profile alternates the 68000 and Z80 sixteen times per
scanline, dividing the existing cycle budgets. Interrupt handlers execute on
the normal instruction fiber, allowing the audio CPU and VDP to progress during
guest polling loops. Yielding and interrupt injection happen between retired
instructions. Legacy forced-zero mailbox responses are disabled for this path.
This prevents short BUSREQ releases from being missed indefinitely; it is not
a game-specific mailbox patch or an audio-CPU speed multiplier.

The CPU-visible YM2612 model now implements timers A and B, based on the
[Sega YM2612 register documentation](https://www.smspower.org/maxim/Documents/YM2612)
and the clock/reload behavior of the already bundled BSD-licensed
[ymfm timer implementation](https://github.com/aaronsgiles/ymfm/blob/main/src/ymfm_fm.ipp).
Timer A ticks every 1,008 master clocks; B every 16,128. Flag clearing does not
restart a running timer, and frequency changes take effect at reload. F1
resets this additional timer state. BUSY status and timer-driven CSM synthesis
are not fully implemented; no claim of complete YM2612 fidelity is made.

Aladdin's sound driver previously waited forever for the absent timer-A flag.
The new model produces sustained changing FM/PSG samples. Streets of Rage 2
previously stopped responding while switching BGM tracks because the Z80 could
not clear the mailbox. A 7,300-frame replay now exercises 28 track selections
and a later sound-effect selection; native/reference PCM and CPU/video state
agree, and each checked menu change still responds. Its extra observed ROM
starts are learned by the converter, keeping this tested sound-menu path native.

The headless runner accepts an explicit `--input-script` with increasing
`frame player1_mask player2_mask` decimal rows; input is held until the next
row. `--trace` writes an explicitly requested diagnostic CSV. Normal launches
still create neither. Reproduce the local cartridge checks with:

```powershell
python tools/megadrive_audio_selftest.py "path/to/Streets of Rage 2.exe" --scenario sor2-music --output .build/sor2-sound-check
python tools/megadrive_audio_selftest.py "path/to/Aladdin.exe" --scenario aladdin-audio --output .build/aladdin-sound-check
```

The music replay follows the [official Sega manual](https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/71165/manuals/04%20SOR2_PC_MG_EFIGS_US_v6.pdf).
These tests inspect digital samples, not loudspeakers, subjective sound quality
or physical audio latency. Z80 fallback is measured independently of 68000 coverage.

## Mega Drive native sound CPU

The converter now generates fixed-operation C bodies for the Z80. Lookup uses
the live PC and converter-generated opcode guards; a covered operation never
enters the reference opcode decoder. Base, CB, ED, DD/FD and indexed-CB forms
are specialized during conversion. The pinned MIT SuperZazu ALU helpers are
retained, together with their notice; this is internal semantic agreement,
not an independent hardware oracle.

Sound drivers execute from mutable RAM. Guards check the bytes that choose the
operation, including prefixes and the indexed-CB opcode. Immediate values and
index displacements remain live bus reads, so changing sample pointers or loop
parameters does not invalidate native code. Changed operation bytes use the
counted reference path. Both RAM mirrors and banked code use the actual bus
view; I/O registers are never peeked to satisfy a native guard.

Conversion probes capture up to four uploaded 8 KiB driver images when the Z80
reset is released. Every supported position is precompiled, including paths
the demo did not take. Unobserved uploads, changed opcodes and prefix chains
beyond the four-byte guard window can still require fallback. The converter
stores at most 32,768 PC/opcode variants in the exact ROM's
`datas/library/md/<rom-sha256>/z80-native-entries.json`. Driver images and
game-derived observations remain local and are not bundled in the converter.
Games keep diagnostic evidence in memory and create no learning files.

IRQ acceptance, EI delay, HALT refresh and instruction cycles retain the
existing scheduler's boundaries. F1 restores the original machine and clears
both CPUs' counters. The title reports actual fallback use by either CPU;
sound processing is no longer labelled interpreted unconditionally.

Authored fixtures cover 28,544 instruction/state and ordered-write comparisons,
plus independent checks for mutable operands, opcode changes, missing code,
bank changes, PC wrap, EI, HALT and IM1 stack/cycles. Run them without game data:

```powershell
python tools/megadrive_z80_selftest.py
```

Gunstar Heroes, Aladdin Japan and Streets of Rage 2 each reach **zero
interpreted 68000 and Z80 instructions** in 3,600-frame demo and play probes.
The same result holds for Sonic in a private regression build. CPU state,
memory, visible-frame sequences and FM/PSG PCM agree with the internal
reference. The 7,300-frame Streets of Rage 2 sound-menu replay also stays native
through 29 selections. Packed exports pass repeated F1/video/PCM checks and an
isolated launch without extra files. These are bounded scenarios, not a promise
that every later path or other cartridge will remain at zero fallback.

Ten additional qualified cartridges were checked over three scenarios each:
3,600 demo frames, 3,600 play frames and a 6,000-frame replay with varied
directions, action buttons, Start transitions and second-player inputs.
The longer replay exposed 2,807 additional ROM/RAM observations, which were
verified and learned by the local converter before regenerating these ten
exports. All three scenarios then reached **zero interpreted instructions on
both the 68000 and Z80**, with matching CPU/memory, visible-frame sequences
and FM/PSG PCM against the internal reference. The packed executables also
passed a 1,200-frame reset comparison and isolated launch without extra files.
These checks cover 13,200 frames per cartridge; they do not certify complete
gameplay, independent hardware fidelity or physical latency. Visual and
listening review remains with the user.

## Further validation scope

### Optional advanced Mega Drive scan

Enable **Options → Mega Drive → Advanced Mega Drive scan** to add a varied-input
replay to every compile/test/learn pass. It runs for at least 6,000 frames, or the
configured **Frames per test** when that is higher. Directions, A/B/C, Start and
player-two controls are exercised; qualified six-button games also use X/Y/Z.
The T2 profile preserves its original Menacer menu selection and mouse test.

All three scenarios are compared against the internal CPU/video/audio reference
before new 68000 ROM/RAM entries or Z80 opcode variants enter the local library.
The converter regenerates code while verified observations are added, within
the existing **Maximum passes** limit. It stops when no new paths are found.
The final report records the scan mode, each scenario's budget, fallback counters
and reference comparisons. Reaching the pass limit can still leave counted fallback.

The option is off by default and applies only to Mega Drive. It increases
conversion time and broadens tested coverage; it cannot explore every level or
certify independent hardware accuracy. Standard mode retains its two reference
checked scenarios. Use `--md-advanced-scan` with `convert` or `batch` in the CLI.

A cold-library Comix Zone check on 8 October 2026 completed in 152.352 seconds
and two passes, reaching zero interpreted 68000 and Z80 instructions on all
three scenarios (3,600 + 3,600 + 6,000 frames). CPU/memory, visible-frame sequence
and FM/PSG PCM matched the internal reference. This is one measured cartridge
on the development machine; conversion time and later gameplay vary by title.

### SPC700 sound-program recompilation

The Super Nintendo sound CPU now follows a separate PC-directed AOT path.
Conversion selects fixed SPC700 operation bodies and builds guarded address
tables for uploaded sound programs. Live opcode checks reject changed code;
immediate operands and data accesses still use the existing APU bus. The boot
overlay has its own mapping, so underlying RAM is selected only when the
guest disables that overlay. Volatile I/O instruction fetches retain the
counted reference path instead of attempting a side-effecting guard.

Probes collect exact misses and up to four sound-RAM images, allowing the next
pass to cover driver positions it has not executed yet. A compressed, bounded
opcode map in `datas/library/snes/<rom-sha256>/spc-native.json` stores that
converter knowledge. Ordinary play retains counters only and creates no files.
The converter's `memory` command reports sound-map size and variant count.

Native execution uses the live SPC registers and preserves instruction costs,
taken-branch penalties, stopping, timers, DSP access and CPU/APU port scheduling.
Stopped scheduler ticks are recorded separately from retired opcodes. Unknown
code still uses the visible, counted reference fallback; the window title
reflects either CPU's fallback use.

Every SNES conversion pass compares the native and fully interpreted paths
before teaching the library. Headless tests consume the same one-frame audio
blocks as interactive play and compare PCM, SPC registers, APU RAM/timers/ports,
DSP state, instruction counts and cycle totals, alongside the existing
main-CPU and video checks. These are internal shared-semantics comparisons,
not independent hardware measurements or complete-game validation.

The ROM-free SPC700 self-test covers all 256 operations across all status-flag
combinations, PC wrapping, the boot overlay, opcode replacement, volatile
fetches and bus ordering: 65,860 differential cases, with nine additional
assertions for live operands, branch cycles, read-to-clear timers and stopping.

With an empty sound bank, two conversion passes reduced fallback as follows
on 8 October 2026. Each demo and play scenario runs for 3,600 frames; existing
65816 RAM observations were reused. Both CPUs finish at zero fallback on all
four tested paths, with matching PCM and CPU/APU/DSP/video state.

| Qualified NTSC revision | SPC700 fallback in first sound pass, demo / play | Final fallback, demo / play |
| --- | ---: | ---: |
| Super Mario World | 15,845,354 / 15,646,412 | 0 / 0 |
| Super Scope 6 | 14,919,382 / 14,985,769 | 0 / 0 |

The two compressed sound maps total 185,522 bytes. Reset checks repeat the
same 600-frame image and PCM sequence on both games. The host adapter resets
the architectural CPU state and clocks as well as the sound-delivery history
when restarting, while preserving cartridge save RAM.

### 65816 and shared comparison limits

Super Mario World's first ROM-only pass reported 372,060 interpreted main-CPU
instructions in demo and 100,750 in play. Learning 130 RAM variants and
regenerating reduced both to **zero**, over approximately 49 million retired
instructions per scenario. Both full-length reference comparisons match:
visible-frame sequence, final CPU registers/PC, RAM, VRAM, CGRAM, OAM,
high OAM, APU RAM and CPU/master/APU clocks. Authored SNES fixtures pass
33,098 instruction/state/bus comparisons across all 256 operations, register
widths, emulation/native modes, decimal arithmetic, LoROM/HiROM mirrors and changed
RAM/ROM guard rejection. Boot/reset/repeated 600-frame image sequences also
match for Sonic and SMW.

The SNES interrupt scheduler now yields at the field deadline or WAI, retaining
the architectural stack and continuation. An interrupt routine can outlive one
field or park inside the handler. RTI also publishes the actual popped return
address: a game can use a modified interrupt frame to switch guest tasks.
Discarding that destination skipped Zelda's polygon worker even while both
native and reference tests agreed. Three ROM-free fixtures separately check
WAI, a long interrupt and RTI task switching against explicit clock and PC
expectations (`python tools/snes_scheduler_selftest.py`).

Four additional NTSC revisions were checked on 8 October 2026: A Link to the
Past, Super Metroid, Donkey Kong Country and Super Castlevania IV. Each completed
3,600 demo frames, 3,600 standard input frames and 6,000 frames with varied
controller input, with zero interpreted instructions on both CPUs and matching
internal CPU/memory/video/PCM diagnostics. Donkey Kong Country exercises HiROM;
Super Metroid also exercises the 3 MiB-to-4 MiB cartridge mirror.

Reset testing exposed a separate FastROM issue: the upstream MEMSEL shadow
survived restart, changing early boot bus costs and the audio handshake. The
host now clears it with the architectural CPU state and clocks. All four
packed exports repeat their 600-frame image and PCM sequence after reset,
without erasing cartridge SRAM. Packed/raw startup diagnostics match, and a
short isolated launch creates no extra files. Visual, listening and complete
gameplay acceptance remain user checks.

The SDL SNES audio host queues every generated PCM block. Catch-up after a host
scheduling delay waits briefly for room before the next input sample/frame;
it no longer consumes and silently drops a whole block above the 20 ms queue
target. Opening and resuming the device waits for its first block. A 600-frame
dummy-device test with four injected 35 ms delays formerly dropped 3,194 stereo
frames (about 66.5 ms); the corrected host queued all 479,536 frames. Peak queued
PCM was about 36.3 ms and the existing DSP cushion was unchanged. These are
digital queue checks, not a listening test or a physical latency measurement.

The separately maintained [sp00nznet/snesrecomp](https://github.com/sp00nznet/snesrecomp)
was also inspected at `644c7647a9b2a6f286abe14ff07e1751e98c4a17`. It packages
LakeSnes hardware behind a bus/platform adapter for separately recompiled game
code. Its scheduling, graphics and audio integration provide useful comparison
points; both projects have LakeSnes ancestry, so it is not an independent
hardware oracle. No source from that project was added to these builds.

Game packing uses UPX level 9 rather than its exhaustive `--best` search. Private
large-SNES tests compacted approximately 33.5 MB to 7.0 MB in 26.3 seconds and
47.3 MB to 10.0 MB in 36.8 seconds. Integrity verification still precedes atomic
replacement of an existing export. These timings depend on the build and host.

Every conversion compares native and reference execution over the full
requested demo/play length. Missing diagnostics or differing state, images,
timing or instruction totals reject the candidate and preserve the previous
export. Sonic and SMW's earlier reference divergences are resolved on these
bounded paths; this is not a claim that every game path has been explored.

The instruction adapters and references share pinned semantic helpers.
Agreement checks the adapters, not an independent hardware oracle.
Untested gameplay may still encounter interpreter fallback. Hardware
accuracy, full-game compatibility, sound quality and physical latency remain
unvalidated. User gameplay review is still required.

## Expanded qualification after 0.21.0

The five additional Mega Drive revisions pass demo/play checks of 3,600 frames
each and an advanced 6,000-frame replay, with zero interpreted 68000 or Z80
opcodes on the final tested paths. The five additional SNES revisions pass the
two 3,600-frame scenarios and a varied 6,000-frame replay. Chrono Trigger's
additional RAM paths were learned only after matching the reference and the
regenerated replay finishes without fallback. Each comparison covers CPU state, memory,
visible-frame sequences and audio PCM. Standard Mega Drive conversion now also
compares against the internal reference before admitting any observations to
the library; that gate is no longer limited to advanced scans.

The regeneration checks reuse front covers with artwork network transports
blocked, compare packed and unpacked exports over 600 frames, and verify reset
video/audio under equivalent memory conditions. F-Zero and Super Mario All-Stars
initialize cartridge SRAM on their first boot; a normal reset preserves it and
can therefore change the boot timing, PCM or visible sequence. Their native
resets match the reference resets with preserved SRAM; replaying with the same
initial SRAM also reproduces the original video and PCM. No save RAM is cleared
by the player's reset to force a match. Short isolated launches create no extra files. These
checks complement the authored instruction and raster fixtures; the internal
reference still shares the hardware model.

Hidden SDL pacing measurements use dummy devices. A PAL export completed
1,200 frames in 24.144120 seconds against 24.144160 expected; a SNES export
completed 1,200 in 20.015378 against 19.967116 expected under conversion load.
An NTSC Mega Drive sample completed 1,800 in 30.038580 against 30.038678 expected.
These measurements check the presentation deadline, not physical input/audio
latency or the accuracy of an in-game timer.

## Build and dependency contract

These profiles use pinned sources downloaded into `.deps` on first conversion:

| Component | Revision |
| --- | --- |
| [segagenesisrecomp](https://github.com/mstan/segagenesisrecomp) | `00c60bc855a7998f92e5614585d52bca8fffcaf2` |
| [snesrecomp](https://github.com/RetroPortingToolKit/snesrecomp) | `a00df26a87831113fec91b9225bf16b049d40775` |
| [SuperMarioWorldRecomp](https://github.com/mstan/SuperMarioWorldRecomp) | `8dedb2869414f20d1d86d34081be26594560cc15` |

The existing Windows C++ toolchain is required for conversion. The SNES
function analyzer for Super Mario World additionally requires an installed stable Rust toolchain, minimum
1.85; this integration does not install Rust automatically. Generated games
need none of those development tools to run.
The ten other qualified SNES instruction maps do not require that function analyzer or
the separate SuperMarioWorldRecomp dependency.

Generated-source analysis is cached for the exact ROM, pinned engine/game
profile, adapter revision and verified observations. Changes to that identity
invalidate the cache. Both conversions use
the existing batch queue, clean filenames, per-console folders, atomic
replacement, Windows metadata, cover icons and executable compression.

Component licences and notices are embedded in each game EXE. The imported
frameworks retain their **PolyForm Noncommercial 1.0.0** terms; RetroRecomp's
MIT licence does not replace them. See [Genesis notices](../licenses/segagenesisrecomp.md),
[SNES notices](../licenses/snesrecomp.md) and [SMW notices](../licenses/SuperMarioWorldRecomp.md).

The next stages are broader Mega Drive gameplay and mapper qualification,
broader SNES RAM/gameplay coverage, state/SRAM integration, SNES PAL and wider
Mega Drive PAL qualification, and additional structurally
different titles. Recognition alone does not grant conversion compatibility.
