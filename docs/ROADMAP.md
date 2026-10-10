# RetroRecomp roadmap

RetroRecomp converts supported Master System, Game Gear, original Game Boy
and NES ROMs, and includes experimental Mega Drive and Super Nintendo
profiles. The 16-bit profiles analyze new cartridges automatically within
their documented hardware scope. The
priorities below describe areas to improve, not compatibility or delivery promises.

| Priority | Work needed |
| --- | --- |
| Broader game coverage | Explore more gameplay paths and guarded RAM variants; reduce reported interpreter fallback. |
| Video and peripherals | Refine hardware timing and edge cases using independent fixtures and game evidence. |
| Gameplay confidence | Extend repeatable scenarios and collect more hands-on validation for supported ROMs. |
| Input response | Measure end-to-end controller latency before making performance claims. |
| NES | Compile guarded RAM code and extend mapper, PAL, peripheral and gameplay validation beyond the qualified scope. |
| Mega Drive | Broaden gameplay, peripheral and mapper validation; widen PAL evidence and add persistent cartridge saves. |
| Super Nintendo | Broaden gameplay checks, PAL display modes and coprocessor support; add persistent cartridge saves. |

## Recompilation priorities after 0.24.0

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

The shared snapshot now contains verified hints for 51 exact cartridges using
the same instruction compiler, with
static branch/call discovery, observed ROM entries and guarded RAM variants.
All use instruction-boundary CPU/audio scheduling, and CPU-visible FM timers
A/B are implemented. Conversion now compares raw FM/PSG samples as well as
CPU/video state. These internal checks complement sound-menu regression
replays; they do not establish hardware-accurate sound. Cartridge region codes
now select the qualified PAL/NTSC clock and domestic/overseas hardware. MOVEP
uses separate byte lanes, and six-button profiles expose their full controls.
TRAP and IRQ entries use the real
supervisor stack, RTE restores the correct mode stack, and STOP waits for an
accepted IRQ. Authored fixtures include these mode/stack/wait/snapshot cases;
additional CPU exception classes still need implementation and independent checks.
The generic cartridge path now derives inputs from each cartridge's vectors
and checks native/reference execution before export. Continue exercising
different gameplay paths; removing the catalogue gate does not establish
support for every hardware variant. Banked or unusual cartridges need their own hardware checks.
Expand PAL qualification and F8/F9 regression coverage, then add cartridge-save
persistence where required. Sub-scanline timing and unusual cartridge hardware
still require independent checks.
The sound Z80 now uses guarded native operations and extended uploaded-driver
coverage. Continue varied play and sound-menu comparisons; remaining interpreter
use is counted separately for the 68000 and the Z80.
Work-RAM tail instructions now use their actual length rather than excluding all
starts in the last sixteen bytes. Early-start probes exercise code that late
demo inputs missed. The latest 20-cartridge batch has zero main/audio fallback
on its four tested scenarios per cartridge. Keep expanding targeted regression
checks before resuming the full collection campaign.

### Super Nintendo

Verified compilation hints now cover 15 exact revisions, including LoROM,
HiROM and a qualified European PAL LoROM case. Japanese single-byte header
titles are recognized, recovering previously rejected inputs; those newly
identified inputs still need execution qualification. The earlier regression
set includes 3 MiB storage mirroring.
The shared scheduler preserves WAI/deadline handoffs and RTI task
switches; authored fixtures cover those boundaries independently. Continue
varied-input qualification of more ordinary cartridges. Coprocessor
cartridges require separate CPU and hardware integration; recognizing their
headers or having upstream code is not proof that RetroRecomp supports them.
PAL now has 312 raster lines, the PPU region bit, full-field IRQ scheduling and
a fractional audio-clock mapping independent of video. Its first qualification
covers progressive 224-line output; overscan, interlace, hires and further PAL
revisions remain to validate. F8/F9 quick states are implemented; persistent
cartridge saves remain unfinished. The sound SPC700
now uses guarded native operations; extend varied-input sound-driver checks
alongside the main CPU coverage. Broader graphics, DMA and interrupt checks must
accompany each expansion of the cartridge scope.

Both 16-bit profiles remain experimental. Expanding the observed cartridge set
does not remove the hardware and gameplay gaps above; the regression catalogue
is not an allowlist. The full Mega Drive and SNES campaigns remain paused until
explicitly resumed; concentrate on the shared compiler and recorded failures.

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
