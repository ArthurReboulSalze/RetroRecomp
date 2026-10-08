# Experimental Mega Drive and Super Nintendo profiles

RetroRecomp includes two separate experimental console profiles. This
does **not** enable arbitrary Mega Drive or SNES games. A cartridge is identified
from its console header, then its SHA-256 must match a qualified game revision
before code generation starts. A different revision, PAL ROM or unsupported
title is rejected rather than compiled with another game's roots.
This document describes release 0.20.0, including the native instruction
paths, resolution-aware scanlines and three qualified lightgun cartridges;
see [16-bit guns, controls and verification scope](GUNS_16BIT.md).

| Profile | Qualified cartridge | Timing | Visible image |
| --- | --- | --- | --- |
| Mega Drive | Sonic the Hedgehog, JUE revision 00, CRC32 F9394E97 | NTSC | 320 × 224 |
| Mega Drive | Columns, CRC32 D783C244 | NTSC | 320 × 224 |
| Mega Drive | Golden Axe, CRC32 665D7DF9 | NTSC | 256 × 224 (H32) |
| Mega Drive | Castle of Illusion, CRC32 BA4E9FD0 | NTSC | 320 × 224 |
| Mega Drive | Menacer 6-Game Cartridge, CRC32 936B85F7 | NTSC | 320 × 224 |
| Mega Drive | T2 - The Arcade Game, CRC32 A1264F17 | NTSC | 320 × 224 |
| Super Nintendo | Super Mario World, USA, CRC32 B19ED489 | NTSC | 256 × 224 |
| Super Nintendo | Super Scope 6, USA, CRC32 B141EA99 | NTSC | 256 × 224 |

The original ROMs remain read-only. Linear `.md`/`.gen` and validated
`.sfc`/`.smc` images, single-cartridge ZIPs, and identifiable `.bin`/`.rom`
files are recognized. A SNES copier header is removed only from the in-memory
build input. Interleaved SMD, PAL execution and additional cartridge profiles
are not enabled in these proofs. No ROM patches or widescreen mode are applied.

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

Mega Drive defaults to arrows, W/X/C for A/B/C and Enter for Start. SNES
defaults to arrows, W/X/A/S for A/B/X/Y, Q/E for L/R, right Shift for Select
and Enter for Start. Player two uses the numeric keypad and has no reset
shortcut. F2 exposes the console's actual controls.
Letter defaults and F2 key labels follow the active keyboard layout,
including AZERTY. Saved custom mappings retain their physical key positions.

F8/F9 states and SNES battery-backed save persistence are not implemented yet.
Do not rely on these test builds to preserve a saved adventure.

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
callbacks. Its sound Z80 remains interpreted.

The converter's demo/play probes collect missing ROM instruction starts and
RAM code variants. Later passes regenerate static code from those observations.
Every RAM variant requires an exact live match of all instruction bytes;
unseen or modified code uses the visible reference fallback. Records are scoped
to the exact ROM hash in the converter's `datas/library/md` namespace. Generated
games keep diagnostic observations in memory and never write a learning library.
H32 and H40 output uses the VDP's active 256- or 320-pixel width at presentation.

Super Mario World uses a separate 65816 adapter. The converter selects one
compiled operation for every physical ROM byte and writes a ROM-PC dispatch
map. LoROM mirrors follow the live cartridge mapping. Covered operations bypass
the opcode-switch interpreter while retaining the real PC, stack, opcode-fetch
timing and live operand reads. Register-width flags, bank wrapping and memory
accesses therefore retain the pinned engine's semantics. Operands are not
specialized into literals as they are in the Mega Drive adapter.

SNES RAM helpers are learned during converter probes, then compiled with an
exact PC and four-byte live-code guard, covering the longest 65816 instruction.
Changed bytes or an unobserved helper use the counted interpreter. Up to
2,048 variants are stored in `datas/library/snes/<rom-sha256>/native-ram.json`.
Generated games keep observations in memory only. The SPC700 sound processor
remains interpreted. Both native and reference tests use the real PC/stack
instruction scheduler instead of the previous paired C-call bridge.

The converter records interpreted main-CPU **opcodes**, separately from the
sound-CPU status. Both native counters now count retired main-CPU opcodes, so
reported native percentages refer only to the main CPU. The window title
signals interpreter use, including the sound CPU, and H explains that status.

Demo and scripted-play probes cover 3,600 frames per scenario. Columns, Golden
Axe and Castle of Illusion already reached **zero interpreted 68000 instructions**
with matching internal reference results in release 0.18.0. The new Sonic path
now reaches the same result after learning four missing ROM starts in a second
pass; Golden Axe also passes a repeat check after this shared-path change.
Mega Drive comparisons cover the visible-frame sequence, final CPU registers,
PC, RAM, VRAM, CRAM, VSRAM, VDP registers and retired instruction totals.
Authored Mega Drive fixtures exercise 6,208 instruction/state comparisons,
guest-stack return modification, RTE frames, byte stack alignment and
self-modifying RAM guard rejection.

Super Mario World's first ROM-only pass reported 372,060 interpreted main-CPU
instructions in demo and 100,750 in play. Learning 130 RAM variants and
regenerating reduced both to **zero**, over approximately 49 million retired
instructions per scenario. Both full-length reference comparisons match:
visible-frame sequence, final CPU registers/PC, RAM, VRAM, CGRAM, OAM,
high OAM, APU RAM and CPU/master/APU clocks. Authored SNES fixtures pass
16,544 instruction/state/bus comparisons across all 256 operations, register
widths, emulation/native modes, decimal arithmetic, LoROM mirrors and changed
RAM/ROM guard rejection. Boot/reset/repeated 600-frame image sequences also
match for Sonic and SMW.

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
Super Scope 6's instruction map does not require that function analyzer or
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
broader SNES RAM/gameplay coverage, state/SRAM integration, PAL timing
qualification and additional structurally
different titles. Recognition alone does not grant conversion compatibility.
