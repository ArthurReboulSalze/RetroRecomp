# Architecture

## Offline conversion

The Python converter identifies the ROM, loads verified compilation facts,
prepares local adaptations of pinned dependencies and emits C. CMake/MSVC
builds a game with ROM data, CPU code, hardware runtime and SDL2 host.
No JIT compiler is added to the resulting game.

The default banked backend translates supported instruction starts across
physical ROM banks. Guest PC and mapper state select the appropriate native
body, reducing dependence on discovering every indirect destination. The
classic function backend remains available via `--backend functions`.

## Runtime and fallback

The runtime maintains guest CPU state, bus, VDP, PSG, input ports, timing and
interrupts. Native execution uses those interfaces. Unknown instructions or
RAM variants can use the corrected reference interpreter. Fallback cycles,
dispatch observations and the window title make that use visible. Fullscreen
does not overlay interpreter diagnostics on gameplay.

## Improvement between generations

Observations are tied to ROM identity and checked against current ROM bytes.
Four-byte RAM windows encountered by fallback are stored locally as
`native.patterns`. A later generation can compile those variants, with guards
checking the complete instruction bytes before selecting the native body.
Changed or unknown variants use fallback.

Each candidate is tested through two scripted scenarios, strict native checks
and comparison with the corrected reference CPU. CPU state, RAM, image and
VDP traces are compared. Both paths share the hardware runtime; agreement
alone cannot certify hardware fidelity.

Publication happens after successful checks. Regeneration replaces the same
filename; a running game is replaced after it exits. Local observations and
settings stay outside the public repository.

## Responsibilities

| Area | Files |
| --- | --- |
| Desktop/CLI | `RetroRecomp.py`, `smsrecomp/gui.py`, `smsrecomp/i18n.py` |
| Conversion and CPU adaptations | `smsrecomp/core.py`, `smsrecomp/cpu.py`, `native/banked_*` |
| Learning and file identity | `smsrecomp/library.py`, `native/learning.c`, `native/manifest.inc` |
| Inputs and presentation | `native/host.c`, `native/controls.c`, `native/ui.c` |
| Covers and icons | `smsrecomp/artwork.py`, `native/icon.c` |
| Regeneration | `smsrecomp/batch.py`, `smsrecomp/publishing.py` |
| Validation | `smsrecomp/validation.py`, `native/*checks.c`, `tools/*selftest.py` |

AI exploration is a future direction. The current converter uses player
observations and fixed scripts; it does not ship a local LLM or AI player.
