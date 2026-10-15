# Neo Geo development and qualification

## Eight-game expansion — 15 October 2026

Art of Fighting 3, Breakers Revenge, 2020 Super Baseball, Crossed Swords,
Robo Army, Twinkle Star Sprites, Pochi and Nyaa Ver 2.00 and Rage of the Dragons
are converted from locally copied, unchanged user inputs, with up to eight
concurrent conversions. Every game has front artwork, including two approved
replacements for misleading automatic results.

The final exports pass 49 reference/packed comparisons: MVS attract/play/actions,
AES attract/play and a 9,000-frame two-player route for each game, plus the
enhanced route for Twinkle Star Sprites. Main and sound fallback are zero on
these routes. Each game passes three MVS and two AES fresh-process F8/F9 points,
invalid-state rejection and ordinary-save checks (reload when changed, or the
explicit no-change case). Eight further enhanced comparisons also pass.

Enhanced Twinkle Star Sprites initially reached 42 uncompiled cartridge
locations (3,195 interpreted instructions). An explicit fresh enhanced
discovery/replay route supplies their exact banked offsets; the regenerated
packed executable matches both fresh and preceding reference results with zero
fallback. These verified observations now enter the shared compilation bank.
No CPU semantics or game code are patched to obtain that result.

Ten captures per game show active gameplay, including two-player scenes,
without obvious corruption in the sampled images. This is bounded visual and
CPU/reference evidence, not complete-game, independent physical-hardware or
physical-latency validation. The private reports, inputs and visual review are
retained under `.build/neogeo-series-20261015`; the compiled games are delivered
to `Export/Games/Neo Geo`. See [the knowledge update](COMPILATION_LIBRARY.md).

The **Neo Geo cartridge profile is supported in release 1.0.2**, following
the user's renewed gameplay validation. The earlier 24-cartridge campaign and
ten additional cartridges below document specific CPU/reference and save-state
checks; support does not establish complete hardware or visual fidelity.
Neo Geo is the seventh console profile. It uses
locally supplied cartridge archives and the four verified BIOS components.
The optional verified `neo-epo.bin` AES export BIOS enables **F11: arcade MVS /
console AES**. Switching closes the current session cleanly, then restarts the
game in the other mode; the choice is remembered. No BIOS is downloaded.
AES and MVS use separate exact identities for quick states, ordinary saves and
fallback hints. An MVS-only archive remains supported; F11 explains the missing
AES component instead of pretending to change the machine.
**The cartridge and BIOS 68000 instructions, M1 and
SM1 Z80 instructions, and observed guarded RAM variants execute native C.** The
tested demo/play routes have zero interpreted instructions on both CPUs.
Unknown instructions remain counted fallback and the window reports
`Native code` or `Interpreter fallback` from actual execution.

## Complete clone archives and reviewed artwork — 15 October 2026

A complete clone archive no longer requires its parent merely because the
catalogue declares one. The converter checks which required CRC-identified
components are actually missing. A split set still requires an independent
parent archive containing those components; the input cannot serve as its own
parent. This fixes a complete Pochi and Nyaa Ver 2.00 archive named `pnyaa.zip`,
which identifies correctly as `pnyaaa` but previously triggered parent loading.
The cartridge contents and strict component checks are preserved.

Reviewed front-cover references now support Neo Geo as well as the six earlier
profiles. The approved Art of Fighting 3 and Rage of the Dragons fronts replace
flyers returned by automatic artwork lookup. Only public image/source links and
matching metadata enter the converter; images remain in the local download cache.
A changed reference invalidates an automatic-artwork freshness receipt, so an
otherwise current export can receive its corrected icon. A manually selected
cover retains priority. See [shared knowledge](COMPILATION_LIBRARY.md).

Developer qualification routes can explicitly select enhanced MVS with an
`enhanced-` prefix, or enhanced AES with `aes-enhanced-`. Discovery and packed
replay use the same mode. These additional routes retain the mandatory standard
checks and let qualified observations cover paths reached under the faster CPU.
They do not introduce game patches or change the timing of the original profile.

## Conversion work in release 1.0.2

The reference is still run from the exact input before using learned hints.
Every route is then compared directly with the packed executable that will be
delivered. A duplicate replay on the uncompressed binary is unnecessary and is
no longer part of product conversion. Separate developer native prototypes keep
their own comparison gate. A build awaiting its packed checks cannot enter the
qualified knowledge library.

Independent routes run with up to four workers, reduced to fit an eight-worker
budget across concurrent games. State checkpoints share one continuous run;
restored processes, malformed-state rejection and ordinary-save checks remain.
An unchanged compressed cartridge is reused only after source and payload hashes
match. No reference/CPU comparison is waived because a game is in the shared bank.

The same six packed NAM-1975 routes took 119.1 seconds with one worker and
46.4 seconds with four in the local development measurement (identical results).
This is a validation-stage measurement, not a whole-conversion speedup promise;
the first measurement also overlapped other validation work. AES adds its own
reference, save-state and persistence checks. End-to-end times depend on the
cartridge, compiler cache and concurrent work.

The final packaged 1.0.2 converter completed NAM-1975, including MVS/AES checks,
in 194.4 seconds on the development machine. Repeating the same request took
2.1 seconds and kept the identical EXE: the freshness receipt avoided another
conversion. This is one local run with existing build caches, not a cold-build
or every-cartridge guarantee.

## Enhanced Neo Geo mode — updated 15 October 2026

New exports offer **F5: Enhanced Neo Geo** in the existing H help panel. This
direct switch doubles virtual 68000 capacity (12 to 24 MHz) and raises the
renderer limit from 96 to 381 sprite columns per scanline. Since 1.0.2 enhanced
mode is the fresh-install default; an explicit saved preference is respected.
Headless qualification retains standard clocks unless `--enhanced` is requested.
The choice is saved only when changed, under `NeoGeo.Runtime/enhanced`
in the shared `datas/Retro-Recomp.ini`; opening a game still creates no config.
This is an intentional extension of console limits, with gameplay qualification
bounded to the tested paths. Native/fallback counters remain real in both modes.

Video, Z80/YM audio and watchdog time remain tied to master clocks. Odd 24 MHz
instruction costs retain their half peripheral cycle through the serialized
master-counter remainder rather than losing it each instruction. Clock switches
rebase the fractional raster-IRQ count; the less precise standard divider rounds
down a residual quarter-pixel phase when returning to standard mode. This feature
does not claim original electrical timing or physical latency equivalence.

Payload v3 retains the selected machine mode in quick states without increasing
their size. The exact preceding qualified standard v2 ABI is accepted explicitly;
the user's preserved crab-scene F8 loads and produces the same standard trace.
New enhanced states restore their clock mode before core/timer residue. To test
that old scene, load it with **F9**, then press **F5**. H shows ON/OFF.
Developer CLI `--enhanced` applies the mode after any requested state load.

The final compressed Metal Slug 3 export passes 900 enhanced scene/action
frames against the forced reference, a 100-frame fresh-process enhanced F9 replay,
and a separate 7,200-frame enhanced cold boot. Standard mode replays the preserved
user v2 state identically. The same 300-frame interval produces
563,200/563,200 interleaved PCM samples
in standard/enhanced mode, with unchanged video/audio rates. Hidden SDL 600-frame
tests take 10.137600/10.137600 seconds;
mean host work is 4.17/5.37 ms,
with 0/0 over-budget frames.
The maximum repeated-image hold on the first 240 frames falls from
4 to 2 refreshes. This is a bounded
software/gameplay test, not physical latency or complete-game qualification.
Evidence: `.build/neogeo-enhanced-20261014`.

## User-supplied Metal Slug 3 quick state — 14 October 2026

A preserved user quick state at frame 8,179 reproduces the crowded crab/explosion
scene. The delivered native EXE and its forced 68000/Z80 reference paths have
identical per-frame CPU/hardware/image/PCM traces for the next 240 frames. A
second 600-frame movement/shooting/jumping/grenade route also matches. Native
fallback remains zero on both paths. These comparisons share the hardware
implementation and do not independently qualify the original board's timings.

Headless simulation takes about 3.07 ms per frame (4.06 ms maximum) over 1,200
frames. On the separate combat route it takes 3.04 ms (4.04 ms maximum). Hidden
SDL sharp-mode playback takes 10.1376 seconds for 600 frames, at 59.185606 Hz,
with 3.54 ms mean host work, 6.95 ms maximum and no over-budget frame. The
video-clock test disables the audio device; a dummy-device check is separate
and is not a calibrated sound clock or a physical latency measurement.

The graphical loss is localized: the renderer reaches its 96-column per-line
limit in 169 of the 240 replayed frames. The first overflow affects four rows.
A private A/B run raising the limit to 381 restores missing portions on 84 of
120 sampled images, with unchanged CPU, RAM, hardware and PCM results. This
corresponds to the documented [Neo Geo sprite limit](https://wiki.neogeodev.org/index.php/Sprites);
removing it would be a deliberate enhanced-rendering mode, not evidence that
the native instruction translator was wrong.

At normal clocks the game output repeats 87 of the 240 frames, sometimes holding
an image for four refreshes. Both CPU paths produce exactly the same sequence.
A private doubled-68000-clock experiment removes the three/four-refresh holds
on this short route, but changes guest execution and does not prove real-hardware
equivalence. The number of distinct complete images is not a gameplay-FPS
measurement: partial sprite updates also change an image hash. Do not silently
ship overclocking, unlimited sprites or altered timings as a recompilation fix.

Evidence stays under `.build/neogeo-mslug3-userstate-20261014`, including the
preserved input state, traces, private diagnostic builds and A/B images. The
delivered EXE, user state/settings and shared compilation bank are unchanged.
These experiments add no public game assets or unqualified compilation hints.

## Runtime performance under sprite load — 14 October 2026

Follow-up feedback reports slow scenes with many enemies, independently of the
selected image filter. Sampled profiling identifies meaningful costs in both
68000 dispatch and the sprite calculator. The runtime now:

- Reuses the current bounded code mapping for each instruction's complete word
  guard, rather than resolving the same mapping separately for each word. It
  retains live byte checks, RAM/protection boundaries and real instruction fetches.
- Decodes an eight-pixel sprite row together instead of extracting four planar
  bits separately for each pixel. Fully invisible sprite columns skip immutable
  graphics reads only after consuming their hardware sprite-list slot. Chaining,
  the 512-pixel wrap, shrinking, priorities and the 96-sprite limit are unchanged.
- Enables release link-time optimization for the native Neo Geo target, allowing
  the compiler to optimize across the generated CPU functions and board adapter.

Authored tests compare 2,261,120 decoder/culling cases, including 128 complete
sprite-line scenes, against the unmodified pinned scalar renderer. Another
3,168 CPU comparisons, five guard/IRQ checks and 722 board mapping/protection
checks pass. These are software comparisons, not independent hardware measurements.

Three sequential before/after runs of the same active 600-frame Metal Slug 3
route, with all presentation filters disabled, reduce mean simulation time from
about 3.50 to 3.12 ms (roughly 11%). CPU, hardware, video and PCM remain identical;
both binaries stay native on that route. This proves lower runtime cost, not
that every user-reported crowded scene has been reproduced or fixed. No guest
clock, frame skip policy, sprite limit, image filter or audio quality is changed.

`--performance-report` additionally records host busy time through presentation,
Present time and over-budget frames, excluding intentional pacing/menu waits.
Normal launches still write no diagnostic files. The final compressed EXE's
controlled 600-frame SDL test holds 59.185606 Hz: sharp mode averages 3.74 ms of
host work (7.67 ms maximum), with no over-budget frame. xBR averages 5.81 ms and
records one 17.93 ms outlier, while total pacing remains on target. These paths
do not reproduce the reported severe slowdown. Audio-device latency is not
measured. Evidence: `.build/neogeo-performance-20261014`.

Both final exports (Metal Slug 3 and Sengoku 3) pass nine fresh-reference and
compressed routes totaling 58,800 frames, six fresh-process F8/F9 points,
52 invalid-state rejections and ordinary-save checks. Three further 7,200-frame
action replays match the previous runtime's CPU/hardware/image/PCM results,
with zero observed 68000/Z80 fallback. The common SDL menus, settings, two
virtual controllers and lazy file creation pass on the final Metal Slug 3 EXE;
74 targeted Python tests also pass. The verified compilation bank is rechecked
and remains byte-identical: this optimization introduces no new observed code
paths. Existing quick states retain their old ABI and are rejected safely;
ordinary saves and user settings are preserved.

Neo Geo software can also update animation less often when its original CPU
misses a frame deadline; see the [NeoGeo development documentation](https://wiki.neogeodev.org/index.php/Slowdown).
That mechanism alone does not diagnose this particular user report. Keep it
separate from the host cost measurements and preserve original game speed.

## Gameplay feedback and broader static coverage — 14 October 2026

User testing exposed early gameplay paths missed by the sampled qualification:
grenades in Metal Slug 3 and other actions in fighting games. Reproductions on
the previous exports count 9,800 interpreted 68000 instructions on the grenade
route, 26,327 in Sengoku 3 and 25,753 in KOF 2001; their Z80 remains native.
The earlier zero-fallback receipts apply only to their recorded routes.

The offline translator now scans every even candidate in the fixed cartridge
aperture (up to 1 MiB) and the supplied BIOS, rather than requiring a previously
observed entry. Legal instructions retain full mapping, length and byte guards.
Banked code still uses exact physical observations/static successors, and RAM
still requires observed guarded variants. Unknown code remains counted fallback.
This is not a claim that every byte is executable or that every game is covered.

Immutable descriptors and compiled operand forms are shared to bound generated
code size. Immediates/extensions remain offline decoded data; the native path
does not call an opcode decoder or the interpreter. Speculative static candidates
are not promoted as observed knowledge. The 3,168 CPU comparisons and stale-byte,
bank-alias, IRQ and RAM-variant guards pass with this representation.

Four held-out 7,200-frame replays (including grenades) pass with zero observed
fallback on both CPUs and unchanged CPU/hardware/image/PCM results. They were
withheld from the first corrected build's discovery. Subsequent qualification
also exercises all four joystick buttons and retains the grenade observations.
Evidence: `.build/neogeo-gameplay-coverage-20261014/holdout-before-promotion.json`.

Normal play now avoids coverage collection and per-frame diagnostic hashes;
actual native/fallback counters remain active. `--report` and tracing retain the
full checks. The opt-in `--performance-report` measures simulation cost without
collecting coverage; `--measure-from` excludes startup from frame-cost statistics.
Light/full paths produce byte-identical PCM and save states on the measured
route. Two serial before/after runs reduce headless processing time by roughly
9–16%; this is a local CPU measurement, not a physical latency measurement.

The shared xBR presentation cache recalculates only blocks whose exact 5×5 source
neighbourhood changed. It does not blend frames or reduce resolution. On 120
consecutive active Metal Slug 3 frames, filtered pixels are byte-identical and
filter CPU cost falls from 7.59 to 4.01 ms/frame in this measurement. The same
shared headers are staged by all seven console builders; newly generated games
inherit the cache, with xBR remaining last in the F3 cycle. Another 360 authored
frames pass exact comparisons across console resolutions, padded rows, borders,
alpha and reset, including 512x478 SNES output. Existing exports require regeneration.

A 600-frame hidden SDL replay of active Metal Slug 3 gameplay with xBR maintains
the 59.185606 Hz target (10.137600 seconds) with unchanged CPU/hardware results
and no fallback. Common menus, filter changes, fullscreen persistence, two virtual
controllers and fresh-process F8/F9 also pass on the final export. These are
sampled opening scenes, not the worst possible scene or a completed playthrough.
Original game timing is retained; physical display/audio latency is not measured.

## Ten additional games — 14 October 2026

Eight workers compile ten further user-owned sets: **Metal Slug 2, The King of
Fighters 2001, Samurai Shodown V Special, Shock Troopers: 2nd Squad, Windjammers,
Sengoku 3, Aero Fighters 2, Last Resort, Magician Lord and Top Hunter**. The batch
takes **734.725 seconds** on the development machine; individual times include
all reference, compression, state and ordinary-save gates under concurrent load.
No existing game or upstream dependency is modified.

All ten pass **20 fresh-reference/packed routes, 108,000 compared frames and
zero observed 68000/Z80 fallback**. The actual packed exports are replayed for
another 72,000 frames with matching counters, state, video and PCM. Private
captures are inspected: fighting, shooting, platforming, scoring, round/stage
transitions and continue prompts appear. Last Resort and Magician Lord reach
early losses/continues; these are sampled openings, not completed playthroughs.

The exports also pass **30 fresh F8/F9 replay points**, 300 frames per point,
**260 malformed-state rejections**, ten missing-F9 read-only checks and ten
ordinary-save gates. These internal CPU/runtime comparisons extend coverage;
they do not add an independent physical-hardware or latency measurement.
Top Hunter records 30 digitally clipped samples among 12,108,436 nonzero samples,
identical to its reference PCM; listening remains a separate user check.

Five online icons are unavailable: Metal Slug 2, Samurai Shodown V Special,
Windjammers, Sengoku 3 and Aero Fighters 2. This optional artwork issue is logged
separately and does not block the executables. Internet cover searches use local
caches; Batocera and its cover directories remain read-only.

The ten verified numeric records raise the ROM-free bank to **1,061 records /
34 Neo Geo**, adding **369,337 gzip bytes**. Existing records are preserved;
the updated snapshot is embedded in `Export/Retro-Recomp.exe`. The ten games
are delivered to `Export/Games/Neo Geo`, taking that folder to 34 current exports.
Evidence and exact source/candidate hashes stay under
`.build/neogeo-additional-20261014`; no GitHub publication or version bump is made.

## Final MVS qualification — 14 October 2026

This historical campaign records bounded CPU/reference and persistence results.
Later user reports of sprite/background artifacts take precedence for product
status: **release 1.0.1 remained experimental**. Release 1.0.2 follows renewed
user gameplay approval; the current scope is described above.

All four exit-plan blocks are complete for **MVS Europe, ordinary two-player
joysticks and standard/CT0/KOF98/SMA/MSLUGX/PVC mappings**. Twenty-four exact
revisions pass **87 packed/reference routes and 826,800 compared native frames**,
with **zero observed 68000 and Z80 fallback**. Eight conversion workers feed
the three planned groups continuously; the entire collection is not scanned.
There is no game-name allowlist enabling native execution. Newly reached code
is observed against the exact input before translation and comparison.

| Group | Exact sets |
| --- | --- |
| 1 | nam1975, mslug, pbobblen, samsho2, neodrift, fatfury2, kof98, kof99 |
| 2 | mslug3, mslugx, mslug5, kof2003, garou, kof2000, turfmast, blazstar |
| 3 | pulstar, shocktro, bstars2, magdrop3, spinmast, viewpoin, kof2002, lastbld2 |

Six authored controller paths run **54,000 frames each**, approximately 15m12s.
Private captures are replayed from the actual packed candidates and compare
with their qualified traces. Inspection confirms the following bounded play:

| Long path | Observed progress and limits |
| --- | --- |
| NAM-1975 | River/city/aircraft combat, changing scenes and continues |
| Metal Slug | First mission advances to its boss; combat/continues remain active, boss defeat not qualified |
| Puzzle Bobble | Moving board, scoring, shots and loss/restart cycles; later stages not qualified |
| Samurai Shodown II | Rounds, different fighters/backgrounds and continues |
| Neo Turf Masters | Shots, scores, leaderboard and progression through holes 1/2/3/4/6 |
| Blazing Star | Several stages/bosses, losses and restarts |

These paths are active gameplay rather than long idle menus. They do not prove
complete playthroughs. The other eighteen controller captures show driving,
fighting, action, shooting, baseball and puzzle play, including selection,
round-end, game-over or card transitions. Standalone two-player routes remain
part of the paired qualification wherever applicable.

Every packed export also passes three fresh-process snapshots followed by 300
matching frames: **72 replay points, 624 invalid-state rejections and 24 missing
F9 checks**. Long paths include a late snapshot at frame 53,400. Ordinary
NVRAM/card save-and-reload gates pass independently for all 24. The real shared
host on final packed KOF 2003 rechecks menus, two virtual controllers, AZERTY
labels, display/filter settings, Unicode paths, F8/F9 and lazy file creation.

Two additional original-CPU-control builds, NAM-1975 and KOF 2003, match seven
routes separately from the adapter's dispatch boundary. Their prolonged SDL
checks each run 3,600 frames: zero empty-queue frames and a 5,288-byte queue peak
(logical queued samples, **not physical latency**). Video-only pacing is
60.825600s for 3,600 frames, agreeing with 59.185606 Hz. The dummy audio clock
is uncalibrated and runs approximately 59.98s; it is not used as physical timing
proof. No startup silence is removed, and listening/jack/controller measurements
are not inferred from these digital checks.

Hardware fixes and the 136 independent authored specification checks are
described below. Input-import fixes also recognize EPROM `.ep1` members and
bound merged archives separately (1 GiB expanded by streaming, 512 MiB compressed;
prepared single cartridges retain their existing 512 MiB and region limits).
The 24 verified numeric records update the bank to **1,051 records total**,
56,898,332 raw / 15,565,059 gzip bytes, preserving every other console.

Evidence, exact input/candidate hashes, current captures, rejected states,
the discarded zero-bank startup regression and final product checks stay under
`.build/neogeo-final-qualification-20261014`. Source archives and pinned upstream
checkouts are preserved. Optional missing or uncertain online icons are recorded
separately; they do not qualify cartridge execution.

The final local one-file converter is **39,007,990 bytes**, SHA-256
`0c5cc589d10b1835cb63d61b0643e7aa9cc030ef09dd02a098ac08ca4bf4e985`.
Its audit verifies 225 declared resources and 84 compiled Python modules against
the current source; the source allowlist audit covers 486 files. The final Python
suite has 421 tests, 420 passed and one skipped; the bilingual GUI smoke passes.
Two real conversions from this frozen EXE in a Unicode folder, with an initially
empty private library, finish as `completed`: NAM-1975 uses 15,345 shared / zero
local hints and KOF 2003 uses 27,083 / zero. Their seven fresh packed routes,
state replays and ordinary saves pass with zero main/sound fallback. Cached
dependency/toolchain installations are reused; this is not a clean-OS setup test.
The 24 qualified games are delivered under `Export/Games/Neo Geo`; prior private
prototypes and user save/config data are preserved. All 25 original supplied
archives, including the BIOS, are rehashed unchanged. No online publication is
part of this local qualification.

AES, other BIOS/regions, distributable free firmware, CD/link/special peripherals,
gambling/unqualified bootleg boards and electrical bus phases remain separate
extensions. A supported profile does not promise universal zero fallback:
unseen code/guards stay counted, and conversions with observed fallback remain
marked experimental at cartridge level.

## Cartridge protections and ordinary saves — 14 October 2026

### Independent hardware fixtures for the final campaign

The final campaign adds 136 authored, ROM-free specification checks: 49 video
timer checks, 28 VRAM/raster/sprite checks, 50 sound-latch/bank checks and nine
YM2610 timer/sample-boundary checks. Expected values come from the documented
MVS pixel clock, VRAM modulo rules, sprite priority/cap and sound interface;
they are distinct from replaying native and interpreted CPUs in Geolith.

They exposed and corrected the video timer period (the programmed value counts
**N+1 pixels**, including one pixel for zero), the eight-bit Z80 bank selection
and the command latch while sound NMI is masked. An unacknowledged command now
survives masking, unmasking raises its pending edge, and port 0 acknowledges it.
Its device latch is included in snapshots and extended hardware hashes. The YM
fixtures also confirm the adapter's existing exclusion of the first out-of-range
ADPCM byte. Four additional regressions retain a compatible linear startup
mapping. Hardware bank numbers are undefined at power-on; an initial zero-bank
choice based on an outdated upstream comment made NAM-1975's demo silent and was
discarded by the campaign's audio gate. It is not presented as a hardware rule.
Pinned upstream checkouts remain unchanged.

Sources: [display timing](https://wiki.neogeodev.org/index.php/Display_timing),
[timer interrupt](https://wiki.neogeodev.org/index.php/Timer_interrupt),
[VRAM](https://wiki.neogeodev.org/index.php/VRAM),
[sprites](https://wiki.neogeodev.org/index.php/Sprites),
[Z80 bankswitching](https://wiki.neogeodev.org/index.php/Z80_bankswitching),
[CPU sound communication](https://wiki.neogeodev.org/index.php/68k/Z80_communication),
[YM timers](https://wiki.neogeodev.org/index.php/YM2610_timers), and the independently
implemented [MAME display timer/latch wiring](https://github.com/mamedev/mame/blob/master/src/mame/snk/neogeo.cpp).
These fixtures qualify the named behaviors, not electrical bus phases or every
rendering feature. Complete-game and physical audio/controller tests are separate.

The first two exit-plan blocks are implemented and locally qualified. Eight
current integrated exports cover NAM-1975, Fatal Fury 2, KOF '98, Metal Slug X,
Metal Slug 5, KOF 2003, Garou and KOF 2000. They pass **31 packed/reference
routes, 207,600 compared native frames, zero 68000/Z80 fallback**, 24 fresh-process
state replay points and 26 invalid states per game. They add MSLUGX/PVC code
views and exercise two additional SMA variants; no game-name allowlist is used.

MSLUGX guards exclude the complete challenge/response window so they cannot
advance its counter. PVC guards exclude its upper 8 KiB of cartridge RAM and
retain sub-megabyte bank offsets. Real data accesses still use the board handlers.
The independent authored fixtures make 339 mapping/protection/state checks;
30 LSPC checks and 32 keyboard/MVS wiring checks also pass.

A real defect was found: the pinned serializer saved battery-backed cartridge
RAM but omitted PVC's volatile protection RAM. The private adapter now includes
it without labelling it battery-backed SRAM. KOF 2003's first-frame CPU divergence
after F9 is fixed; current PVC snapshots are 520,517 bytes, while the other tested
boards remain 512,325 bytes. Invalid-state fixtures address the correct layout.
The full instruction RAM guards and existing SMA/KOF '98 state extensions remain.

### Ordinary scores and memory card

Generated games expose an inserted, writable 2 KiB memory card and independently
reload 64 KiB of MVS NVRAM plus card data from
`datas/saves/NeoGeo-<full-cart-and-BIOS-key>.rrsave`. One atomic file is **67,712
bytes** including its integrity/identity header. The key uses the exact prepared
cartridge, selected BIOS and MVS Europe; it is independent of the executable's
name and quick-state runtime ABI. Different games/firmware do not share this file.

First-boot initialization is tracked until actual guest input. A plain launch,
close, help menu or missing F9 creates no save directory. Changed memory after
guest interaction is flushed at clean exit; unchanged/idle sessions preserve the
file and timestamp. A successful explicit F9 also makes its restored persistent
memories eligible for the ordinary save on exit. This is not continuous autosave
or a guarantee after a forced termination/power failure. Bad/incompatible files
are preserved, machine memory is not loaded from them, and ordinary saving is
disabled for that session with a short warning. A concurrent session's new file
is preserved instead of being silently overwritten. Reading never creates files.

All eight packed games pass real ordinary-data save/reload checks in fresh
processes without F8/F9. NAM-1975's new 13,800-frame card/game-over route also
produces an actual card change and reloads both memories. That route first
exposed 8,619 main-CPU fallbacks in the previous short-route export; discovering
and translating its additional code reduces them to zero with reference agreement.
Its new state points include frame 7,000, after the card/game-over path.
ROM-free IO fixtures pass 125 checks, including 17 invalid-file cases, Unicode
paths, rename, unchanged files, explicit-state persistence and concurrent updates.

The real shared-host test rechecks menus, two virtual pads, key labels, display
settings, filters, F8/F9 and lazy file creation. Latest Python suite: 418 tests,
417 passed and one skipped. Physical audio/controller latency and complete-game
compatibility are not inferred from these tests.

Eight current numeric records are qualified for the bundled bank; it now has
nine Neo Geo records and 1,036 records total. Ordinary-memory checks are also a
promotion gate; NVRAM, card contents and PVC state bytes never enter the hints.
Evidence: `.build/neogeo-cartridge-saves-20261014`, particularly
`qualification-summary.json`, `delivery.json`, `knowledge-build.json`, fixtures
and the final batch log. Inputs and the original pinned dependencies are preserved.
The first batch's failed KOF 2003 replay is retained as evidence of the correction.
Garou's automatic online cover search did not find an image in this campaign;
its optional artwork remains a separate issue.

The final one-file converter embeds the refreshed bank and passes two real
conversions from a Unicode app folder with an initially empty private library.
NAM-1975 uses 10,320 shared / zero local hints; KOF 2003 uses 27,083 / zero.
Their seven packed routes, fresh states and ordinary saves still pass. This test
also exposed and fixed lithogen's narrow Windows argv/UTF-8 mismatch: the private
helper now takes wide arguments and the loader's output IO uses wide file APIs.
Zip/NEO contents remain identical and the pinned loader checkout is unchanged.

These earlier receipts precede the final campaign above. They remain historical
evidence; later visual reports kept release 1.0.1 experimental. Release 1.0.2
adds AES export firmware support; a distributable free BIOS remains a separate topic.

## Experimental exit plan — 14 October 2026

This assessment follows converter integration. The dated prototype receipts
below describe earlier builds; their old converter/knowledge TODOs are now
superseded. No new game campaign or runtime test was run for this assessment.
The current code and saved qualification reports establish the following:

- Nine exact local game revisions have bounded native/reference evidence.
  Three (NAM-1975, KOF '98, Metal Slug 3) have passed the integrated converter,
  packed-export and fresh-state gates and contribute bundled numeric knowledge.
  Nine prototypes, three bundled records and 282 recognized catalogue layouts
  are three different counts; recognition is not qualification.
- BIOS selection, Automatic detection, mixed batches, standalone exports,
  shared menus, two-player input, display settings and F8/F9 are implemented.
  The current integrated reports show zero 68000/Z80 fallback on their tested
  routes. A real frozen-converter KOF '98 conversion also passed.
- The native cartridge code view only admits DEFAULT, CT0, KOF98 and SMA.
  The upstream runtime additionally implements MSLUGX and PVC, but our code
  view rejects their cartridge mappings. These are concrete native-coverage
  gaps, not a missing BIOS picker or a list of unapproved game titles.
- NVRAM and memory-card bytes are included in F8/F9. The Neo Geo startup/exit
  wrapper has no independent disk load/save path for those memories; closing
  and reopening without a quick state does not restore them.
- Most comparison evidence shares Geolith's hardware implementation. Native
  CPU agreement, including matching image/PCM, does not independently qualify
  video/audio timing. The longest current ordinary route is 9,000 frames,
  about 2.5 minutes, with much shorter actual player-controlled action after
  boot and menus. Full-game and physical latency qualification remain false.

### Proposed first supported scope

Qualify **Neo Geo MVS Europe cartridge games**, using the currently accepted
user-supplied four-component BIOS, ordinary two-player controls and explicitly
covered board families. Extend those families to MSLUGX and PVC before a broad
MVS support claim. Unknown boards must retain explicit unsupported/experimental
status and honest fallback counters; scope is determined by hardware and exact
input identity, never by requiring an approved game name.

AES, other regional BIOS revisions, a distributable free replacement for all
four BIOS components, Neo Geo CD, linked cabinets, unusual peripherals and
unqualified bootleg/gambling boards are subsequent scopes. They do not block
this first MVS qualification. No private BIOS is to be shipped. Electrical
perfection, universal zero fallback and completing every game are not release
criteria; observed correctness problems within the stated scope are.

### Four bounded work blocks

| Order | Remaining work | Acceptance evidence |
| --- | --- | --- |
| 1 — Cartridge/native coverage | Add side-effect-free MSLUGX and PVC code identities, protection/bank handling and complete state restoration; exercise additional SMA variants and later RAM code. Metal Slug X, Metal Slug 5, SVC Chaos and KOF 2003 are targeted board examples from the pinned loader. Add bounded discovery/replay paths where existing scenarios miss code. | Original ROM-free bank/protection tests, no device reads caused by code guards, fresh native/reference matches and zero main/sound fallback on the selected qualification routes; replay after bank/protection changes. Unseen code remains counted fallback. |
| 2 — Ordinary persistence | Store and reload game-scoped NVRAM and memory-card data independently of F8/F9, with atomic writes, exact input/BIOS compatibility and defined behavior after F9. Respect lazy output creation: no unconditional startup dump; distinguish BIOS initialization from meaningful persistent changes. | A real in-game change survives a fresh process without F9; absent/invalid files are handled safely, other games remain isolated, and a plain launch/close without meaningful changes creates no files. Recheck quick states and settings. |
| 3 — Hardware and presentation checks | Independently check relevant raster/vertical IRQ ordering, LSPC sprite/zoom/palette behavior and 68000–Z80 sound-command/YM2610 timer interactions. Check pacing and queue stability over longer runs. Fix observed mismatches with original fixtures, documented hardware expectations or a separate implementation. | Focused evidence independent of the two Geolith CPU routes, plus no known reproducible rendering/sound/timing blocker in the selected scope. Physical listening/controller checks remain separately labelled; no latency-number claim without measurement. Prefetch/sub-instruction work is driven by demonstrated discrepancies, not an open-ended perfection gate. |
| 4 — Final bounded campaign and bank | Select 24 exact revisions in three batches of up to eight, including the existing nine and representatives of the added families/genres. Requalify through the current converter, not old prototype binaries. Add at least six 15–20 minute scenarios with verified progression, transitions/continues and two-player coverage where applicable. | Every selected packed export passes its fresh reference routes, zero observed main/sound fallback, fresh-process F8/F9 and invalid-state checks. No unresolved in-scope blocker. Promote only successful numeric records; build/audit the converter and test cold private-library conversions using the bundled hints. |

The 24-game campaign is a proposed finite validation matrix, not a catalogue
allowlist or proof for all cartridges. Record failures and fixes against exact
revisions. Replace a matrix case only for a documented availability or scope
reason, never to discard a failing in-scope game. Verify screenshots/replay
progress so a long menu loop cannot stand in for a gameplay route. Test shared
state/settings/audio/menu changes against the other supported consoles.

Once these four gates pass, the declared MVS scope can become supported while
the explicitly excluded systems/boards keep their own status. A successful
headless replay alone cannot close visual/audio gameplay findings. Publication
and a release still require the user's request.

Current receipts: `.build/neogeo-converter-20261014/work-summary.json`, its three
published-local conversion reports, and the preserved standard/protected
prototype receipts under `.build/neogeo-expansion-20261014` and
`.build/neogeo-protected-20261014`. Code anchors: `neogeo_code_view.inc`,
`neogeo_main.c`, `neogeo_host.c`, `neogeo_validation.py` and
`neogeo_build.py::compile_native`. The latest full-suite receipt is 418 tests,
417 passed and one skipped; it was not rerun for this documentation audit.

## Reusing the existing 68000

`smsrecomp/m68000.py` contains the corrected instruction semantics, operation
extraction, literal descriptors and timing helpers used by Mega Drive. Board
hook names can be supplied explicitly; the Mega Drive defaults keep its current
symbol names. `native/m68000_state_helpers.h` shares stack selection and the
ordered normal exception frame while preserving the existing snapshot layout.

`native/m68000_backend.h` defines the CPU scheduling and bus boundary. The Neo Geo
adapter routes initialization, reset, IRQ lines and memory waits through it.
Code locations identify physical cartridge/BIOS offsets and mutable work RAM;
vector switching, mirrored addresses and bank windows belong to the board.
The code view supports standard, PRO-CT0, KOF '98, SMA, MSLUGX and PVC mapping families,
not a list of approved game names. Unknown cartridge mappings remain fallback;
BIOS and ordinary RAM keep their own identities. Protection response ports are
not instruction ROM: guards never consume CT0 responses or SMA random values.
Instructions cannot straddle these ports or KOF '98's mutable header overlay.
`smsrecomp/neogeo_codegen.py` translates reached P/BIOS entries and static
successors through our existing 68000 decoder and corrected semantic bodies.
Observed entries retain their physical offset in the selected bank. A banked
logical PC is never guessed to belong to the first megabyte; RAM PCs are not
reused as cartridge roots. Different banks at the same virtual address remain
distinct compiled entries.
P and BIOS word-swapped inputs are normalized without modifying source files.
Dispatch checks physical mapping, region bounds and every instruction word
before executing a compiled body. No opcode decoder or reference opcode handler
is called on a covered path. Observed 68000 RAM instructions are translated
offline with exact full-word guards, bounded to their 64 KiB physical RAM
mirror. Several variants can share one address; an unseen instruction word or
immediate stays fallback. Dispatch uses an indexed variant chain rather than
decoding the opcode during play. This is guarded AOT, not unrestricted RAM
execution or a guarantee that every future gameplay path is covered.

The native register ABI is bridged to Geolith's canonical Musashi register and
IRQ/reset state. Clock lookup preserves this hardware profile's existing CPU
schedule, with explicit operand-dependent branches, bit operations, shifts,
MOVEM, multiply and divide costs. The prototype retains instruction-boundary
scheduling and disabled prefetch; **Mega Drive's bus/prefetch timing is not
silently transplanted to Neo Geo**. Real instruction reads and board waits
remain, but fine bus phases are not qualified. Some native extension fetches and
our corrected MOVEM discarded read differ from Musashi's access count, even when
retired clocks and the serialized machine state agree. Wait counters describe
events in this reference profile, not independently measured electrical waits.

`smsrecomp/neogeo_z80.py` reuses our structural-key and opcode-body extraction
strategy with Geolith's own Z80 ABI. Physical M1/SM1 maps select fixed operations;
bank boundaries, structural bytes and the observed mutable RAM routine are
guarded. Immediates/displacements, data and full 16-bit ports are live accesses.
Word reads are explicitly low-byte then high-byte to avoid compiler-dependent
C evaluation order. IRQ/NMI, EI delay, HALT and refresh retain the canonical
schedule. External IM0 supplied opcodes remain explicitly counted fallback.
The existing state serializer sees canonical registers; instruction-local native
scratch data is not guest state. The stage 4 wrapper now preserves the complete
frame-boundary state used by this prototype.

## Inputs and local build

The preparation process uses [lithogen](https://github.com/carmiker/lithogen)
at `ef0f9bd94e31689def44b49e0f8351e0206b622d`. Its catalogue describes cartridge
layouts, rather than restricting conversion to previously tested game titles.
Identification checks program CRCs and archive composition. Ambiguous sets
require explicit selection; missing regions and mismatching CRCs are errors.
Each preparation runs in an isolated process with local staging paths. The
Windows helper accepts Unicode paths through wide argv and explicit UTF-8 file IO.
Source archives and NAS directories are read-only inputs.

P, S, M, V1, V2 and C are separate regions. `.neo` containers are checked for
their signature, total length, region limits and required alignment before
Geolith sees them. The selected BIOS requires `sp-s2.sp1`, `sfix.sfix`, `sm1.sm1`
and `000-lo.lo`, with their expected sizes and CRCs. Identity includes original
contents, any parent archive, the selected BIOS and the pinned tool revisions.

The hardware base is [Geolith](https://github.com/libretro/geolith-libretro)
at `2dc88e3fa72ff404213a65d6eb5bb33baa687f73`, in a private adapter copy. It
provides cartridge hardware, LSPC rendering and YM2610 synthesis. Small M1/SM1
ROMs are mirrored within the selected chip; an ADPCM read at the end of a region
is rejected instead of reading into the next region. The libretro frontend and
CHD stack are not included. This prototype accepts cartridge inputs only.

```powershell
python -X utf8 tools/neogeo_prototype.py "path/to/nam1975.zip" --bios "path/to/neogeo.zip"
```

The default tool builds a reference, observes bounded controller routes,
translates the reached instructions and compares native execution before export.
NAM-1975 retains its historical two routes. The additional cartridges use
boot/demo, coin/start and genre-specific controller sequences; three also have
a two-player route. These scripts only operate the controls, including separate
name-entry confirmations for Neo Drift Out. They do not modify guest memory.
Protected-board qualification also includes a 9,000-frame autonomous demo and
a two-player route. Strict duplicate-basename/CRC checks remain: an archive
that mixes incompatible revisions must first be reduced to one verified set
in a local working copy, without altering the supplied archive.
`--reference` builds the interpreted baseline only. Rebuilding from a prepared
local input uses a distinct staging directory to preserve the input archive.
The default result is `Export/Prototypes/Neo Geo/NAM-1975.exe`. It embeds the
prepared cartridge, the four selected BIOS components and component notices,
and uses static SDL2. It creates no folders or diagnostics during ordinary play.
Cartridge data is compressed and expanded directly in memory at startup;
the executable also uses the existing verified UPX packaging path.
Neo Geo identification is available in the converter's Automatic mode and its
manual console selector. The standalone prototype tool remains a developer entry.

## Converter integration and BIOS selection

In **Options → Neo Geo**, browse to your BIOS ZIP and check it. The selected
path is persisted with the converter preferences; a relative path inside the
app folder remains portable. Only the previously validated MVS Europe firmware
and its four components are accepted. Missing/wrong components are reported
before GUI conversion; no BIOS is supplied or downloaded. AES and other BIOS
revisions remain separate qualification steps.

Cartridge ZIP/NEO inputs participate in ordinary mixed-console batches, up to
eight concurrent conversions, stop-after-active behavior, overwrite controls,
atomic publication and `Games/Neo Geo` routing. Native 68000/Z80 conversion is
the default. The report keeps both interpreter counters, internal CPU/image/PCM
agreement and physical/gameplay limits separate. The generated EXE embeds
component notices, optional cached front artwork, Windows metadata and a
branded exact-ROM ownership marker. Reading the input catalogue does not build
a preparation tool or copy data beside the source.

Merged archives are filtered in a local working copy by catalogue CRC, with
SHA equality required between same-CRC candidates. A fully CRC-matched named
revision takes precedence over clones with more files. Multiple complete
revisions without a proven choice remain an explicit ambiguity. Original ZIPs
and BIOS files are preserved. The CRC/layout catalogue contains descriptions,
not game bytes or an allowlist of qualified titles.

Three integrated cartridges (NAM-1975, KOF '98 and Metal Slug 3) pass ten packed
routes, nine fresh-process replay points and 26 invalid-state cases each, with
zero main/sound fallback on those routes. Their numeric, BIOS-scoped hints enter
the shared snapshot after the same gates; all prior console records are kept.
Unreconstructible RAM words, raw journals, states, images and PCM stay private.
Every hinted conversion still builds a fresh reference and validates its result.

The frontend is integrated; independent hardware timing, longer gameplay,
other boards and distributable free firmware remain development work. This
does not reclassify Neo Geo as a supported production console.

The prototype now uses the actual shared `console16_host_ui.c` and
`retro_menu.c` host, including its menu appearance and version footer in H.
Arrows move, W/X/C/V are A/B/C/D, Enter is Start, and either Shift inserts
player 1's coin with the default mapping. Player 2 uses keypad 5/2/1/3 for
directions, 8/9/6/4 for A/B/C/D, keypad Enter for Start and 0 for Coin.
Two controllers use D-pad/left stick, A/B/X/Y, Start and Back (Coin).
MVS player 2 Start is wired to STATUS_B bit 2, separately from Select.
NAM-1975 is an ordinary joystick game; no light-gun menu is exposed.

F2 remaps keyboard/gamepad controls per player; Left/Right changes player,
Tab changes input type, Up/Down selects a row and Enter captures a binding.
Capture accepts only the selected player's controller. Letter defaults and
displayed labels follow the active Windows keyboard layout. P or a left-stick
click pauses; F1 or player 1's right-stick click resets. F3 cycles sharp,
Scale2x, proportional scanlines and xBR last. F4 cycles window, integer
fullscreen and fitted fullscreen with the image ratio preserved. F6 toggles
face-button gamepad autofire; F7 switches EN/FR; Escape closes a menu or quits.
The window's `Native code`/`Interpreter fallback` caption stays English.

Settings are read lazily from `datas/Retro-Recomp.ini` beside the executable.
Video and mappings have independent `NeoGeo` sections. Display mode, filter,
language, autofire and custom bindings survive closing/reopening. Opening,
closing, inspecting a menu or trying F9 without a save creates no files.

## Persistent F8/F9 state

F8 atomically replaces one slot in
`datas/states/<game-name>-<cart-and-bios-sha12>.rrstate`; F9 resumes it, including
after exiting and restarting the executable. New builds use the frame-state
v2 layout: 512,325 bytes (about 500 KiB). Current PVC exports additionally retain
8 KiB of volatile cartridge protection RAM and use 520,517-byte files. Their
new ABI rejects older incompatible states. The five previously delivered EXEs
retain their original v1 layout, 509,717 bytes; the ABI rejects incompatible
states. It stores the canonical 68000/Z80, bank/IRQ state,
LSPC video/palette RAM, YM2610, timers/RTC, work RAM, NVRAM, memory-card data,
frame index and the already presented image. It embeds no cartridge or BIOS.
The exact cart regions, four selected BIOS components, MVS/region and runtime
ABI identify compatible states. Incompatible, truncated or altered files are
rejected; only a successful F8 prepares the directories.

The wrapper adds missing 68000 STOP/reset/run/instruction/cycle latches and
the YM2610 SSG output divider and held samples. Geolith's palette selector is
also rebound on load. The current extension preserves SMA's pseudo-random
sequence, KOF '98's actual overlay mode independently of its last register
write, both LSPC sprite line buffers and their selector/render flags. The
sprite buffers matter for the very first image after a fresh-process load;
only palette indices and register values are stored, never host pointers.
These corrections are made in private engine adapters,
without editing the pinned upstream checkout or ROM. At a completed
`geo_exec` boundary the accumulated sample count is zero; its last instruction
cycle temporary is overwritten before use. CPU-local native scratch and host
pointers are not serialized. Host audio queues/resampling history are cleared
and re-primed after loading; physical output is not part of the snapshot.

The initial NAM-1975 qualification used three fresh-process replays, saved at
frames 30, 2,600 and 3,300, reproducing
300 subsequent frames each: CPU/extended hardware/Z80/image and raw PCM agree
frame by frame. Eighteen invalid-file cases and a missing-file case leave the
machine unchanged. Actual shared-host event tests cover F8/F9, two SDL virtual
controllers, remapping, settings reload, all filters and F4 modes. Thirty
ROM-free checks cover keyboard and MVS two-player switch wiring. Virtual input
and a dummy audio device do not validate physical controller/jack latency.

The preserved stage 4 NAM-1975 packed EXE is 4,481,536 bytes, SHA-256
`b9c6174e602ef22d561b3f633946554f4e27382669b250996aba4795553d89c6`.
Evidence stays in `.build/neogeo-host-20261013`; it is not bundled or published.
Neo Geo is still opt-in: the production converter/BIOS-aware knowledge schema,
distributable free firmware, other cartridges/boards and finer hardware timing
remain separate gates. The six-console 1.0.0 release and bundled bank are unchanged.

Developer probes accept `--headless --frames N`, `--script FILE`, `--report FILE`,
`--capture DIRECTORY` and `--pcm FILE`. `--save-state FILE`, `--save-at FRAME`,
`--load-state FILE` and `--trace FILE` support deterministic state replay;
`--frames N` executes N additional frames after loading. Reports record instruction counts for
both CPUs, reached addresses, CPU/RAM/image/PCM hashes and audio levels. Captures
and PCM stay private; only numeric observations may later be qualified for the
shared compilation bank.
`--rtc-seed TIMESTAMP` initializes the MVS clock deterministically in UTC for
differential tests. Ordinary play initializes it from the computer's clock.
Reports also compare serialized Z80 and whole-machine state hashes, including
IRQ/DMA/sound scheduling state. Native builds accept `--reference` and
`--reference-z80` for developer comparisons. Optional CPU tracing is bounded by
`--trace-from`, `--trace-limit` and `--trace-stride`; no trace is created normally.

## Evidence boundaries

The original Mega Drive instruction bodies are compared before and after the
module extraction. Independent CPU exception/prefetch fixtures and authored
timing/interface tests cover the shared helpers. A small Mega Drive regression
lot additionally compares fresh native and reference execution.

NAM-1975 boot/attract and coin/start/play routes are compared with Geolith's
original CPU control calls. Matching CPU, RAM, image and PCM results validate
the integration boundary; both routes still use the same hardware family.
They do not prove physical hardware fidelity, complete-game coverage or physical
audio latency. Dummy SDL devices test presentation, resampling and wall-clock
cadence separately. Listening and controller response remain hands-on checks.

Earlier prototype records were not promoted before the converter integration
and BIOS-aware schema. The three newly qualified integrated records are now
included through the documented gates.
Qualified numeric P/BIOS/RAM observations remain private and exact-input scoped.
Geolith is
BSD-3-Clause with dependency-specific notices; lithogen is BSD-3-Clause with
MAME-derived data/algorithms. Existing 68000 frontend licensing remains in force.

## Protected cartridges and guarded 68000 RAM, 14 October 2026

| Cartridge | Board | Guarded 68000 RAM instruction variants | Main/sound fallback on compared routes |
| --- | --- | --- | --- |
| Fatal Fury 2 | PRO-CT0 | 0 | 0 / 0 |
| The King of Fighters '98 | KOF '98 overlay | 541 | 0 / 0 |
| The King of Fighters '99 | SMA | 529 | 0 / 0 |
| Metal Slug 3 | SMA | 552 | 0 / 0 |

Each packed EXE is compared with original Geolith CPU control on four routes:
3,600 demo, 7,200 player-controlled, 9,000 extended demo and 6,600 two-player
frames. These total sixteen bounded routes and 105,600 native frames, with
matching CPU/RAM, extended hardware/Z80, image/PCM, reached physical entries
and retired instruction totals. Captures are inspected for active combat/action
and two-player play. This does not qualify complete playthroughs, every board
variant or physical hardware timing.

Code-view fixtures exercise the real pinned board handlers with synthetic data:
214 mapping/protection/state checks confirm that guards never advance the SMA
random generator or consume CT0 responses. The 68000 suite makes 3,168
architectural comparisons across fixed ROM, BIOS, two physical banks and two RAM
mirrors; five guard/IRQ checks include observed and unobserved RAM immediates.
The Z80 suite retains 14,352 comparisons and four guards. Thirty additional
ROM-free LSPC checks reproduce both line-buffer selectors, render registers,
the first resumed scanline and rejection without mutation.

Fresh-process F8/F9 replays at frames 30, 4,500 and 6,000 compare 300 frames
each for every cartridge, including the first resumed image and raw PCM.
Twenty-six invalid states per cartridge and a missing file are rejected without
changing the machine or creating a save directory. Fatal Fury 2 exposed a real
first-frame image divergence caused by LSPC's omitted sprite line buffers;
the v2 extension fixes it. The real shared-host test on packed KOF '99 covers
menus, keyboard labels, two virtual controllers, remapping, persistent display
settings, Unicode paths and F8/F9. NAM-1975 is recompiled end to end and Metal
Slug's banked play/state paths are rechecked, keeping their delivered EXEs.

Cold SDL presentation retains actual startup silence. Metal Slug 3 has zero
nonzero PCM samples in its first 600 frames, so its additional device-output
test loads a verified frame-4,500 state and requires audible PCM during the next
600 frames. No silence is removed or audio fabricated. Video-only pacing is
checked separately against 59.185606 Hz; dummy devices do not measure jack
latency or listening quality.

The supplied Metal Slug 3 ZIP also contains another revision with conflicting
basenames. A local canonical official set is selected by catalogue CRC, with
same-CRC source candidates checked for identical SHA-256. The original ZIP and
strict archive ambiguity checks remain unchanged. This input preparation does
not patch the cartridge, waive CRC checks or silently select a different game.

Private evidence, delivery hashes, input-preservation checks and remaining
problems are recorded under `.build/neogeo-protected-20261014`. Numeric reusable
observations stay in `knowledge/ng/<exact-cart-and-BIOS-identity>` there. RAM
source links cover 535 KOF '98, 529 KOF '99 and 302 Metal Slug 3 variants;
6 and 250 additional variants respectively have no exact P/BIOS source and
remain private. Neither raw RAM words nor journals enter the shared bank.
The Python suite passes 408 of 409 tests, with one skipped. The six-console
release and 1,027-record bank are unchanged. Production converter/BIOS-aware
knowledge, distributable firmware, PVC/other mappings and independent hardware
qualification remain separate steps.

## Four-cartridge expansion on 14 October 2026

| Cartridge | Compared packed routes | Main/sound fallback |
| --- | --- | --- |
| Metal Slug | 3,600 demo + 5,400 extended demo + 7,200 play + 6,600 two-player frames | 0 / 0 |
| Neo Drift Out | 3,600 demo + 7,200 play frames | 0 / 0 |
| Puzzle Bobble | 3,600 demo + 7,200 play + 6,600 two-player frames | 0 / 0 |
| Samurai Shodown II | 3,600 demo + 7,200 play + 6,600 two-player frames | 0 / 0 |

These are twelve bounded routes, not complete-game coverage. They compare the
packed EXEs with Geolith's original CPU control calls: architectural CPU/RAM,
serialized hardware/Z80, image, raw PCM, reached logical and physical entries,
and both retired-instruction totals agree. Captures confirm shooting, racing,
puzzle play and fighting; two-player play is also inspected for the three games
that support it. Listening, physical controls and longer playthroughs remain
separate hands-on checks.

Metal Slug exposed a conversion defect: 293 demo and 295 play instructions fell
back because banked P-ROM entries above the first megabyte were collected using
only the logical PC. The common observer now records actual P/BIOS offsets from
the active code mapping. Recompilation removes those misses without changing
the cartridge or the interpreter counters. Bounded miss diagnostics expose PC,
region, offset, opcode and count only when a developer requests a report.
A further 300-frame continuation after the short Metal Slug demo exposed 5,665
fallback executions at 847 mapped instruction locations. A longer, separately
compared reference demo is now part of its conversion scenarios to collect
those routines as well.

At a completed frame, Musashi's expired `initial_cycles` and `remaining_cycles`
can shift together when native/reference fetch access counts differ. The next
active `m68k_execute` replaces them before executing or accepting an interrupt;
their difference still gives the same retired clocks. Boundary CPU hashes
compare this elapsed value and all persistent CPU latches. Reports expose both
raw counters, and snapshots retain them unchanged. Metal Slug's two otherwise
identical states resume into identical CPU/hardware/Z80/video/PCM for 300 fresh
frames. This is not a qualification of fine bus access phases. Original CPU
control bypasses the adapter wait counter, so its zero counter is not reported
as a no-wait measurement.

Each new cartridge is also checked through three fresh-process F8/F9 replays
at frames 30, 4,500 and 6,000, with 300 subsequent frames compared each time,
and eighteen invalid-state cases. Puzzle Bobble has an additional active-game
replay at frame 3,000. Shared-host tests on the final Metal Slug EXE exercise the real
menus, two virtual controllers, settings reload, Unicode paths and F8/F9.
The ROM-free 68000 suite now makes 2,112 architectural comparisons, including
two physical banks at the same virtual PC with different opcode bytes; guard
and IRQ checks remain. The Z80 suite retains 14,352 comparisons and four guards.
NAM-1975 is rebuilt and compared again as a control; its previously delivered
EXE is preserved.

Exact-input observations and receipts stay in
`.build/neogeo-expansion-20261014`. Only the four locally qualified EXEs are
added to `Export/Prototypes/Neo Geo`. No ROM, BIOS, image, private state or raw
journal is added to the repository or shared compilation resource. The
1,027-record bundled snapshot remains unchanged; production BIOS-aware knowledge
integration, free firmware, further board scopes and finer hardware timing still
require their own qualification.
Numeric entries are also retained in `knowledge/ng/<exact-input-identity>`
under that private evidence directory, with the original cartridge, BIOS and
runtime identities. No raw RAM opcode literals are copied into that reusable
observation record. The Python suite passes 407 of 408 tests, with one skipped;
all 34 Neo Geo tests pass after adding the longer demo route.

## Local qualification on 13 October 2026

- NAM-1975: 3,600 boot/attract frames and 5,400 coin/start/play frames, paired
  with original Geolith CPU control. CPU/RAM/image/PCM and reached-PC comparisons
  agree with a declared fixed RTC seed. The stage 3 native prototype additionally
  matches Z80 and full serialized hardware state. Both CPU instruction totals
  match independently; native and reference counts are deliberately distinct.
- Native ROM translation: 9,274 cartridge instructions and 2,837 BIOS instructions
  (12,111 total). The sound translator emits 417 structural bodies and one
  guarded RAM variant, including both M1 and SM1.
- Demo: 59,382,784 native 68000 instructions and 28,960,910 native Z80 instructions.
  Play: 88,912,157 and 42,848,295 respectively. Both routes have zero fallback.
  These totals describe the tested routes, not universal cartridge compatibility
  or a complete-game playthrough.
- ROM-free adapter checks: 1,056 MC68000 architectural comparisons plus guard/IRQ
  checks; 14,352 Z80 instruction/state/cycle/memory/full-port bus comparisons plus
  mutable-immediate and opcode/RAM guard checks. These complement the existing
  independent Mega Drive CPU fixtures; they do not qualify Neo Geo electrical timing.
- Cartridge decompression and the UPX-packed EXE are exercised by the same routes.
- The archived stage 3 native private EXE is 4,454,912 bytes, SHA-256
  `b91c9e42d8ddd82d1c4d37d10fb1b867946dc0cf56be95ded01077c21a13f0ed`.
- Dummy SDL output: 600 frames in 10.137656 seconds inside the presentation loop
  (10.138 seconds nominal), with no empty-queue frame reported. This is not a
  jack-output latency or subjective sound-quality measurement.
- Three Mega Drive controls: generated instruction C files are identical before
  and after extraction; fresh native/reference CPU/image/PCM comparisons pass.
  Sonic/Golden Axe have zero main/sound fallback on the tested paths; Columns
  has two main fallback instructions. No new knowledge is promoted from them.
- Independent fixtures: 864 exception cases and 2,089 prefetch cases plus 82
  authored cases pass in native and reference modes. Authored timing, native
  architecture and the generic interface tests pass. A fresh Sonic state resumes
  with matching CPU/image/audio; eight invalid state files are rejected.

Stage 1/2 receipts remain under `.build/neogeo-prototype-20261013`. Stage 3
receipts and private images/PCM are under `.build/neogeo-native-20261013`;
the conversion project is `.build/ng-4354046cd98c5c7985e2-native`.
The shared bank's SHA-256 remains
`a5b85b347b0512a54bb3a1c75ed3a549544a828ff9208780b5a50bfd50a5029b`.

## BIOS distribution boundary

No SNK BIOS or cartridge is distributed in Retro-Recomp, its repository or
releases. This local prototype uses the user's supplied BIOS solely as test
input. Free replacements are a separate compatibility/licensing gate:
[NeopenBIOS](https://github.com/neogeodev/neopenbios) has an ISC licence;
[neogeo-projects/neogeo-bios](https://github.com/neogeo-projects/neogeo-bios)
has GPLv3 and lists NAM-1975 stage-1 tests. Neither is integrated or qualified
here. Replacing the main 68000 BIOS alone does not settle the source/licence of
the SFIX, SM1 and LO components used by this hardware profile. A future bundled
replacement must check all four components and retain their applicable notices
and source obligations. Do not include the current private BIOS in a release.
