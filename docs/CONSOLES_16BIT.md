# Experimental Mega Drive and Super Nintendo profiles

RetroRecomp 0.18.0 includes two separate experimental console profiles. This
does **not** enable arbitrary Mega Drive or SNES games. A cartridge is identified
from its console header, then its SHA-256 must match a qualified game revision
before code generation starts. A different revision, PAL ROM or unsupported
title is rejected rather than compiled with another game's roots.

| Profile | Qualified cartridge | Timing | Visible image |
| --- | --- | --- | --- |
| Mega Drive | Sonic the Hedgehog, JUE revision 00, CRC32 F9394E97 | NTSC | 320 × 224 |
| Mega Drive | Columns, CRC32 D783C244 | NTSC | 320 × 224 |
| Mega Drive | Golden Axe, CRC32 665D7DF9 | NTSC | 256 × 224 (H32) |
| Mega Drive | Castle of Illusion, CRC32 BA4E9FD0 | NTSC | 320 × 224 |
| Super Nintendo | Super Mario World, USA, CRC32 B19ED489 | NTSC | 256 × 224 |

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

Sonic's 68000 paths use static generated C; its sound Z80 remains interpreted.
The compiler rejects unsupported dispatch sites during generation.
Super Mario World uses generated 65816 C and an instruction interpreter for
remaining paths; its SPC700 sound processor remains interpreted.

Columns, Golden Axe and Castle of Illusion use a new instruction-level AOT
adapter. Each known ROM instruction emits its selected C operation with literal
operands. Execution follows the real 68000 PC and stack, including computed
jumps, changed return addresses and hardware-shaped interrupt frames. It does
not dispatch covered instructions through an opcode interpreter. This avoids
the C-function call model's unsafe stack exits found when extending beyond Sonic.

The converter's demo/play probes collect missing ROM instruction starts and
RAM code variants. Later passes regenerate static code from those observations.
Every RAM variant requires an exact live match of all instruction bytes;
unseen or modified code uses the visible reference fallback. Records are scoped
to the exact ROM hash in the converter's `datas/library/md` namespace. Generated
games keep diagnostic observations in memory and never write a learning library.
H32 and H40 output uses the VDP's active 256- or 320-pixel width at presentation.

The converter records interpreted main-CPU **opcodes**, separately from the
sound-CPU status. The Mega Drive native counter counts main-CPU opcodes; the
SNES native counter counts compiled bridge entries. These different units
are deliberately not combined into a misleading native percentage. The
window title signals interpreter use, including the sound CPU, and H explains
that status.

Earlier demo and scripted-play probes complete 1,800 frames for Sonic and SMW. Sonic
reported zero interpreted 68000 opcodes in those two runs; SMW still reported
millions of interpreted 65816 opcodes. The internal visible-frame sequences
differed from the reference execution over a 120-frame boot comparison.
The three new Mega Drive games complete demo and scripted-play probes of
3,600 frames each with **zero interpreted 68000 instructions** on those tested
paths, including the learned RAM helpers. Their visible-frame sequence, final
CPU registers, RAM, VRAM, CRAM, VSRAM, VDP registers and retired instruction
counts match the separate reference execution over the same complete probes.
Authored fixtures additionally exercise 6,208 instruction/state comparisons,
guest-stack return modification, RTE exception frames, byte stack alignment
and self-modifying RAM guard rejection.
An empty-library conversion of all three titles reaches these results in two
passes per title, using the default 3,600-frame tests. Prior observations are
not required for this measured result.

The instruction adapter and reference share the pinned decoder and semantic
helpers. Agreement checks the adapter, not an independent hardware oracle.
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
analyzer additionally requires an installed stable Rust toolchain, minimum
1.85; this integration does not install Rust automatically. Generated games
need none of those development tools to run.

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
reference-divergence diagnosis for the earlier proofs, reduced 65816 fallback,
state/SRAM integration, PAL timing qualification and additional structurally
different titles. Recognition alone does not grant conversion compatibility.
