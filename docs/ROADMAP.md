# RetroRecomp roadmap

RetroRecomp converts supported Master System, Game Gear, original Game Boy
and NES ROMs, includes a supported Mega Drive standard-cartridge profile
and an experimental Super Nintendo profile. The 16-bit profiles analyze new cartridges automatically within
their documented hardware scope. The
priorities below describe areas to improve, not compatibility or delivery promises.

| Priority | Work needed |
| --- | --- |
| Broader game coverage | Explore more gameplay paths and guarded RAM variants; reduce reported interpreter fallback. |
| Video and peripherals | Refine hardware timing and edge cases using independent fixtures and game evidence. |
| Gameplay confidence | Extend repeatable scenarios and collect more hands-on validation for supported ROMs. |
| Input response | Measure end-to-end controller latency before making performance claims. |
| NES | Compile guarded RAM code and extend mapper, PAL, peripheral and gameplay validation beyond the qualified scope. |
| Mega Drive | Extend gameplay and unusual cartridge circuits beyond the qualified standard profile; refine electrical, field and bus-error behavior with independent evidence. |
| Super Nintendo | Broaden gameplay checks, PAL display modes and coprocessor support; add persistent cartridge saves. |

## Recompilation priorities after 0.25.0

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

Release 0.25.0 includes the standard cartridge profile's completed qualification: three
groups of eight new cartridges plus eight feature regressions, PAL/NTSC,
advanced conversion, compressed-export replay, CPU/video/PCM agreement,
fresh-process states and corrupt-state rejection. Five routes extend to
36,000 frames. The common VDP row-fetch fix was reapplied to every new export.
Verified shared hints now cover 82 exact ROMs; this is not a cartridge allowlist
or a guarantee of complete interpreter-free playthroughs.

Supported scope includes linear ROM, declared Sega 512 KiB mapping, ordinary
SRAM, qualified X24C01/X24C02/24C04 wiring, shared controllers, quick states and
Menacer. Continue targeted gameplay and game-menu save checks. Other EEPROM
boards, mappers, SVP/Pico/CD/32X and lock-on require separate integration.

Further hardware work concerns electrical request/acknowledge precision,
remaining VDP access collisions/field details and address/bus-error handling.
These limits remain explicit without indefinitely blocking the completed
standard profile. See [compatibility evidence](COMPATIBILITY.md),
[video](MEGADRIVE_VIDEO.md), [CPU exceptions](MEGADRIVE_CPU_EXCEPTIONS.md),
[EEPROM](MEGADRIVE_EEPROM.md) and [mapping](MEGADRIVE_MAPPERS.md).

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

Super Nintendo remains experimental. Expanding the observed cartridge set
does not by itself remove its hardware and gameplay gaps; the regression catalogue
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
