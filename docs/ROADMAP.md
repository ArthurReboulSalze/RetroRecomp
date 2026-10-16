# RetroRecomp roadmap

Release 1.1.1 has seven supported console profiles on Windows and a native Linux
x86-64 package. Support remains bounded to documented cartridge hardware;
Linux is qualified on Debian 13/glibc 2.41, with broader distributions still pending.

RetroRecomp converts supported Master System, Game Gear, original Game Boy
and NES ROMs, includes a supported Mega Drive standard-cartridge profile
and a supported standard Super Nintendo profile. The 16-bit profiles analyze new cartridges automatically within
their documented hardware scope. The
priorities below describe areas to improve, not compatibility or delivery promises.

| Priority | Work needed |
| --- | --- |
| Runtime performance | Continue low-power Linux measurements, especially the unresolved Mega Drive slowdown. Shared Windows/Linux optimizations preserve output on numeric checks; desktop speed, sound quality and physical latency need target testing. See [performance notes](RUNTIME_PERFORMANCE.md). |
| Neo Geo | Broaden MVS/AES gameplay, guarded RAM coverage and independent rendering evidence. Other BIOS revisions, boards and peripherals have separate scope. See [evidence and remaining work](NEOGEO.md). |
| Broader game coverage | Explore more gameplay paths and guarded RAM variants; reduce reported interpreter fallback. |
| Video and peripherals | Refine hardware timing and edge cases using independent fixtures and game evidence. |
| Gameplay confidence | Extend repeatable scenarios and collect more hands-on validation for supported ROMs. |
| Input response | Measure end-to-end controller latency before making performance claims. |
| NES | Broaden VRC/Taito guarded-RAM and lower-ROM-alias qualification, PAL, peripheral and gameplay validation. |
| Mega Drive | Extend gameplay and unusual cartridge circuits beyond the qualified standard profile; refine electrical, field and bus-error behavior with independent evidence. |
| Super Nintendo | Extend gameplay beyond the completed standard-profile qualification; refine instruction-internal and parked-CPU phases, disputed OAM access and CX4 native coverage. Other cartridge circuits have separate support gates. |
| Knowledge size | Compact repeated SPC opcode references before another large cartridge campaign; keep the bounded 64 MiB decompressed budget and every qualification gate. |

## Recompilation priorities after 0.25.0

### NES

NES is now treated as a supported profile within its documented cartridge scope.
Native entries cover every physical PRG ROM byte, including bank-switched code.
The wider qualification set spans eight games and eight mapper families;
see [NES evidence](NES.md#broader-cartridge-validation).

The local follow-ups add guarded RAM entries and fetch-time handling for the
PPU-dependent MMC1/MMC1A and mapper-153 configurations, including enabled
FME-7 RAM and mapper 153's ordinary RAM mode. The Zelda, Kirby and FME-7 cases
use live operands instead of unconditional RAM fallback. DMA audio/sprite
arbitration, pending interrupts/reset, later fresh-process states and bounded
TriCNES comparisons extend the qualification. Continue longer, varied gameplay
and additional RAM-bearing board layouts; unobserved entry/opcode variants
and contended hardware windows remain visibly interpreted.
The current development also covers mapper-40/FME-7 ROM aliases at $6000-$7FFF
and the accessible VRC2/VRC4 and Taito X1 RAM windows. Mapper protection latches,
registers and open bus are not treated as RAM code. Expand real-cartridge paths
and board variants beyond this bounded qualification.
Optional advanced NES scanning now adds menu/dialogue and varied-input paths,
with complete per-pass CPU/image/PCM checks. Content-checked source paths
reuse identical compiled ROM bodies after RAM discoveries. Continue guided
later-game states and more cartridge revisions; broader independent PAL
qualification remains separate from these internal checks.
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

Verified local compilation hints now cover 40 exact revisions, including LoROM,
HiROM and a qualified European PAL LoROM case. Japanese single-byte header
titles are recognized, recovering previously rejected inputs; those newly
identified inputs still need execution qualification. The earlier regression
set includes 3 MiB storage mirroring.
The shared scheduler preserves WAI/deadline handoffs and RTI task
switches; authored fixtures cover those boundaries independently. Continue
varied-input qualification of more ordinary cartridges. DSP-1 board/command modelling and CX4 are integrated within their documented
limits, with CX4 device interpretation counted explicitly. Clipped DSP-1 camera
paths and the first HDMA scanline now have independent numeric/image checks;
Pilotwings passes the tested routes and Mario Kart reaches a short race.
Super FX, SA-1, S-DD1 and other circuits still require separate integration.
Native CX4 and finer hardware phases remain future work; the common CPU/DMA/HDMA fixes are qualified within their documented limits.
Recognizing headers or having upstream code is not product qualification.
PAL now has 312 raster lines, the PPU region bit, full-field IRQ scheduling and
a fractional audio-clock mapping independent of video. Its first qualification
covers progressive 224-line output. The audio/display follow-up now retains hires dots,
both interlace fields and 239-line overscan, with busy mode-switch and APU-word
ordering checks; [SNES evidence](SNES.md) records the remaining independent limits.
F8/F9 quick states and ordinary battery cartridge saves are implemented.
Guarded code now includes ordinary SRAM windows; its bounded observation table
and binary PC lookup cover more RAM routines without relaxing live-byte guards.
The sound SPC700
now uses guarded native operations; extend varied-input sound-driver checks
alongside the main CPU coverage. Broader graphics, DMA and interrupt checks must
accompany each expansion of the cartridge scope.

The released standard profile and qualified DSP-1/CX4 boards are supported. Expanding the observed cartridge set
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
