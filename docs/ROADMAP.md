# RetroRecomp roadmap

RetroRecomp converts supported Master System, Game Gear, original Game Boy
and NES ROMs, and includes experimental Mega Drive and Super Nintendo
profiles. The 16-bit profiles accept only qualified game revisions. The
priorities below describe areas to improve, not compatibility or delivery promises.

| Priority | Work needed |
| --- | --- |
| Broader game coverage | Explore more gameplay paths and guarded RAM variants; reduce reported interpreter fallback. |
| Video and peripherals | Refine hardware timing and edge cases using independent fixtures and game evidence. |
| Gameplay confidence | Extend repeatable scenarios and collect more hands-on validation for supported ROMs. |
| Input response | Measure end-to-end controller latency before making performance claims. |
| NES | Compile guarded RAM code and extend mapper, PAL, peripheral and gameplay validation beyond the qualified scope. |
| Mega Drive | Extend gameplay and peripheral validation of all twenty-two qualified profiles, qualify more cartridges, and add PAL and persistent states. |
| Super Nintendo | Extend guarded RAM, gameplay and peripheral checks beyond Super Mario World and Super Scope 6, then qualify more games, timing modes and saves. |

## Recompilation priorities after 0.20.0

### NES

NES is now treated as a supported profile within its documented cartridge scope.
Native entries cover every physical PRG ROM byte, including bank-switched code.
The wider qualification set spans eight games and eight mapper families;
see [NES evidence](NES.md#broader-cartridge-validation).

The next coverage work is guarded RAM code and the remaining unstable mapper
configurations. Kirby and Zelda demonstrate why this matters: their ROM code
is native, but execution from RAM still needs the reported fallback. Continue
longer, varied comparisons alongside the shorter per-conversion checks.
PAL/NTSC, quick states and Zapper already exist; extend their validation across
more cartridges and hands-on gameplay. Mega Drive is the next development
priority, followed by Super Nintendo.

### Mega Drive

The twenty-two qualified NTSC revisions use the same instruction compiler, with
static branch/call discovery, observed ROM entries and guarded RAM variants.
All use instruction-boundary CPU/audio scheduling, and CPU-visible FM timers
A/B are implemented. Conversion now compares raw FM/PSG samples as well as
CPU/video state. These internal checks complement sound-menu regression
replays; they do not establish hardware-accurate sound. Cartridge region codes
now select domestic/overseas NTSC hardware. TRAP and IRQ entries use the real
supervisor stack, RTE restores the correct mode stack, and STOP waits for an
accepted IRQ. Authored fixtures include these mode/stack/wait/snapshot cases;
additional CPU exception classes still need implementation and independent checks.
The priority is a generic
cartridge qualification path: derive inputs from the cartridge's vectors,
exercise different execution paths, and admit more revisions only after the
CPU/video checks succeed. Removing the identity gate alone is not support for
the full catalogue. Banked or unusual cartridges need their own hardware checks.
Then add PAL timing, F8/F9 states and cartridge-save persistence where required.
The sound Z80 now uses guarded native operations and extended uploaded-driver
coverage. Continue varied play and sound-menu comparisons; remaining interpreter
use is counted separately for the 68000 and the Z80.

### Super Nintendo

Six exact NTSC revisions are qualified, including LoROM, HiROM and 3 MiB storage
mirroring. The shared scheduler preserves WAI/deadline handoffs and RTI task
switches; authored fixtures cover those boundaries independently. Continue
varied-input qualification of more ordinary cartridges. Coprocessor
cartridges require separate CPU and hardware integration; recognizing their
headers or having upstream code is not proof that RetroRecomp supports them.
PAL, F8/F9 and persistent cartridge saves remain unfinished. The sound SPC700
now uses guarded native operations; extend varied-input sound-driver checks
alongside the main CPU coverage. Broader graphics, DMA and interrupt checks must
accompany each expansion of the cartridge scope.

For each stage, record native coverage, CPU comparison, hardware evidence,
hands-on gameplay and physical latency separately. Start with a small, varied
cartridge set for the relevant hardware paths rather than rebuilding a whole
collection after every change.

## Improvement loop

We want to explore more paths using a local decision or vision model:
observation, input choice, deterministic replay, guarded compilation and
comparison before regeneration. A stopping threshold could combine native
coverage, regression stability and exploration budget. More explored paths
do not prove complete gameplay or hardware fidelity.

The current version reuses verified observations and checks candidates. The
AI player/autonomous exploration loop is not implemented. No model weights,
API credentials or online-model integration are distributed.
