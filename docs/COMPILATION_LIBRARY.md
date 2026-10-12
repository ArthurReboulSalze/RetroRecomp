# Shared compilation knowledge

Release 0.26.0 retains exact-ROM NES RAM entry/opcode observations
alongside ROM seeds. Shared `ram_opcode_refs` contain only a CPU entry address
and an offset of that opcode in the user's PRG ROM. The converter reconstructs
the opcode from the supplied cartridge, then guards its live RAM value before
calling a precompiled instruction body. Operands remain live; no private RAM
dump or operand data enters the shared resource.

NES journal freshness is checked against the successful conversion timestamp,
so later failed/stopped observations cannot replace a qualified shared record.
Local build candidates can accelerate a retry but never skip validation.
RAM-bearing conversions compare all their configured coverage frames against
the internal CPU, including exact PCM. A configure receipt binds the inserted
guards so the pinned build bridge cannot silently regenerate them away.

The qualified snapshot bundled in 0.26.0 contains **991 exact ROMs**, including
**29 NES records and 759 guarded NES RAM entry/opcode references**. The latest
eight-cartridge gate adds four exact revisions and requalifies four records;
all other consoles and twenty-one unrefreshed NES records remain unchanged.
Batman: Return of the Joker contributes 485 guards for enabled FME-7 RAM,
after the actual compressed EXE passed three full 3,600-frame CPU/frame/PCM
comparisons and later fresh-process state checks. The snapshot occupies
36,394,933 raw bytes and 9,392,577 gzip bytes, only 3,089 compressed bytes more
than the preceding guarded-RAM snapshot. SHA-256:
`cbe3c07a9c6dc6fc0b3ab25f495982ebc236175a26288f4f130a09b4e026ef8b`.
The isolated Zelda check used an empty private library and empty generated
project, importing its 186 guards from the shared resource in its first pass.
Dependency/compiler caches were reused; this is not a cold-toolchain speed
measurement. The exact tested record is unchanged in the final snapshot.
The latest isolated FME-7 check likewise starts with empty private knowledge
and generated projects, imports all 485 shared Batman guards in its first
pass and passes three 600-frame internal CPU/frame/PCM comparisons. The
compressed result repeats those comparisons and passes fresh-process state
checks. Its tested record and snapshot hash match the final bundled resource.

Release 0.25.0 includes the final Mega Drive campaign: 24 new exact ROM records
and eight requalified records, only after ordinary strict conversion and actual packed
EXE replay. The snapshot shipped in that release contains **985 exact ROMs**: 258 SMS, 1 GG,
606 GB, 23 NES, **82 MD** and 15 SNES. It occupies 36,384,534 raw bytes and 9,387,948 gzip bytes.
SHA-256: `0f5d8d30e831021fba5301e006af373f0b5f46b941af542ae70bc4ec804ad03c`.

All other consoles and unrefreshed Mega Drive records are unchanged. Numeric
observations reconstruct guarded bodies from the user's exact ROM; raw ROM,
private driver bytes, player states, artwork and diagnostic traces are excluded.
An isolated empty private library converted Golden Axe II using its qualified
shared record in a staged ROM-free resource, with ordinary reference checks,
packed replay and fresh-process states. Integration verifies that the exact
tested ROM record is unchanged in the final shared snapshot.
Dependency/generated-code caches were reused; this was not a cold-toolchain
speed benchmark. The locally packaged converter was audited against this exact
snapshot and current source inputs. The original-ROM archives and protected
Shining Force II player state are unchanged.

The earlier cartridge-hardware refresh is recorded below as historical evidence. The decompressed resource budget is now 64 MiB, shared by the
builder, bounded loader and package audit, to retain qualified observations
across consoles. Distribution still uses gzip. Numeric allowlists, exact-ROM
binding and reference-before-learning gates are unchanged; an oversized refresh
fails before replacing the previous snapshot.

The EEPROM/Sega-mapper development refresh adds four exact Mega Drive ROMs only
after normal strict advanced conversion and final packed-EXE reference checks:
Wily Wars, NBA Jam, NBA Jam Tournament Edition and the original 5 MiB Super
Street Fighter II. All five scenarios per ROM have zero main/sound fallback;
the additional packed checks identify and hash each exact executable. EEPROM
protocol and mapper tests are independent authored fixtures, not shared game
data. Actual battery boot and fresh-process F8/F9 remain separate evidence.

That earlier ROM-free snapshot had 961 identities (258 SMS, 1 GG, 606 GB,
23 NES, 58 MD, 15 SNES), 31,221,890 raw bytes and 8,099,305 compressed bytes.
SHA-256: `ea1a025e31f80fa6c7ace1ba493879d128f913bcaec40ee5914feea8cf995bca`.
All previous records and other consoles are unchanged. MD code observations
for a mapped cartridge use physical ROM offsets, with the learning key checked
against the actual fetched instruction before a bank-changing operation.
The refreshed snapshot is included in the locally rebuilt and audited
`Export/Retro-Recomp.exe`: all 168 resources and 63 frozen Python modules match
the current public source inputs. Raw private libraries, ROMs, chip save bytes
and artwork are not bundled. Evidence:
`.build/md-cartridge-hardware-20261011/qualification.json`. That earlier block did not promote
Mega Drive beyond experimental or qualify all cartridge circuits.

Regeneration also separates current export identity from stale revision reports.
When reports disagree about one filename, the branded full ROM identity in the
EXE resolves ownership. Source names are matched per executable and exact ROM,
so an older revision's generic filename cannot turn the current source into a
duplicate. Ambiguous files remain protected; byte-identical renamed games still
use the normal duplicate rule. This is common batch code for every console.

The advanced Mega Drive scan now explores the original attract sequence for at
least 18,000 frames, alongside the existing play, varied-input, early-start and
menu/dialogue routes. Exact-ROM observations from late transitions need the
same reference comparison and final native regeneration as earlier paths. This
extends qualification coverage; it does not prove the remainder of a game.

Mega Drive partial refresh now also rejects either CPU's local observation file
when it is newer than the successful exact-ROM conversion report. This closes
the stale-report gate after an unfinished/failed later scan. The previously
verified shared record is retained; the new private union needs qualification
before it can replace that record. Missing qualification dates fail closed.
Successful 16-bit conversion reports now record their completion time in UTC
after strict validation and the final observation update. The three reports
produced immediately before this metadata correction were dated only from their
actual successful conversion receipts, after verifying the exact ROM/EXE,
unchanged observations and subsequent long reference/state replay. Their
original reports and receipt hashes remain in the local qualification evidence;
filesystem modification times are never substituted for a missing qualification.
The regression includes both the 68000 and Z80 files and preservation of the
previous snapshot. `tools/megadrive_progression_selftest.py` adds longer real
two-port controller traffic and fresh-process state replay; its reports remain
local and cannot themselves bypass the conversion's normal reference gate.

The suspended-fetch follow-up changes common Mega Drive guarded Z80 execution,
with a counted continuation when the actual opcode differs after a bus wait.
Only Sonic 1, Sonic 2 and Shining Force II are requalified by exact ROM. Their
verified snapshot is embedded in the local converter; other records are intact.
The independent mutation/interrupt fixtures and isolated cold libraries are
not bundled as cartridge knowledge. A new hardware descriptor identifies known
EEPROM boards despite missing save headers and recognizes the tested Sega SRAM
replacement; it supplies no borrowed code roots or runtime save implementation.
Evidence: `.build/md-suspended-fetch-20261011/qualification.json`.

The local-BUSACK follow-up changes common Mega Drive bus-control rendezvous and
sound-CPU machine-cycle scheduling. It also distinguishes immediate interpreter
entry signals from completed-instruction counters without weakening reference
validation. Only Sonic 1, Sonic 2 and Shining Force II are eligible for an
exact-ROM knowledge refresh after qualification. Authored bus/state fixtures,
player states and private raw observations are not bundled. The verified
ROM-free snapshot is included in the locally rebuilt converter. Evidence:
`.build/md-local-busack-20261011/qualification.json`.

The CPU-pause follow-up fixes common Mega Drive STOP deadlines and the wall
clock used after a pending Z80 transaction is released from BUSREQ/reset.
Only Sonic 1, Sonic 2 and Shining Force II are requalified by exact ROM here.
The verified snapshot is refreshed only after native/reference qualification
and embedded in the local converter; player states, ROMs and private raw
observations remain excluded. These timing fixes are shared runtime code,
not per-game hints. Evidence: `.build/md-cpu-pauses-20261011/qualification.json`.

The Z80 phase follow-up changes shared Mega Drive code, including memory-cycle
placement and impossible-budget validation. Only Sonic 1, Sonic 2 and Shining
Force II are eligible for exact-ROM requalification in this block. The refreshed
verified snapshot is included in the locally rebuilt converter after validation;
raw driver observations, player states and the private campaign database are
not bundled. Authored phase fixtures are test sources, not cartridge knowledge.
See [the timing evidence](MEGADRIVE_Z80_TIMING.md).

The Mega Drive internal-wait follow-up changes the common bus scheduler, not
per-game code: explicit 68000 internal work can yield to external Z80 requests,
and retirement retains a modular clock budget. Sonic 1, Sonic 2 and Shining
Force II are requalified by exact ROM after the usual native/reference checks.
Only these three records are eligible for refresh; authored timing fixtures and
player states remain outside the bundled knowledge.

The shared xBR presentation filter is bundled as common host code, with its MIT
notice. It is not a cartridge patch or a compilation observation. Only Super
Mario Bros.' exact NES record is requalified for this display follow-up; the
verified snapshot remains unchanged. No game images enter the shared library.

The NES audio-continuity follow-up changes common output delivery and strengthens
conversion validation with exact native/interpreter PCM comparisons. Only Super
Mario Bros.' exact record is requalified here. No ROM bytes, recordings or
per-game audio workaround enter the shared snapshot; future NES exports use the
same updated host and checks. Native coverage remains separate from sound-device
delivery, physical latency and listening validation.

The Game Boy audio-output follow-up likewise changes the common host, not
cartridge code or APU synthesis. Super Mario Land 2 and Tetris are requalified
by exact ROM identity after coverage and deep reference-CPU checks. The verified snapshot
contains no audio, ROM bytes, private measurements or per-game latency patch.
The updated common output code is bundled with the converter for future exports.

The Master System audio-latency follow-up changes shared host output buffering,
not cartridge translation or PSG behavior. Alex Kidd's exact record is
requalified after native/reference checks; no PCM, audio traces or per-game
latency workaround is added to the bundled knowledge. See [audio evidence and
measurement limits](AUDIO.md).

Master System sprite investigations also distinguish compiler observations from
hardware display limits. Double Dragon exposed the original eight-sprite
overflow and alternating sprite order, not a missing native entry. The shared
renderer now offers an optional presentation enhancement, including stabilization
of confirmed rapidly reversing overlap priorities, while preserving guest
collision/overflow behavior. It also suppresses collisions in the blanked left
column. The fix is shipped as common source, not a per-ROM patch or artwork hint.
Only Double Dragon's exact record is requalified for this follow-up; no bulk
campaign or raw diagnostic data enters the bundled knowledge. See [video
diagnosis and separate evidence](VIDEO.md#sprite-flicker-and-the-optional-master-system-enhancement).

The 68000 step backend now guards RAM bodies against the actual fetched image,
including stale words retained by its two-word prefetch queue. The prepared
body remains stable through retirement. Queue state/hash and impossible bus
budgets are part of exact-ROM validation; shared hints never bypass those gates.
See [prefetch qualification and explicit exclusions](MEGADRIVE_PREFETCH.md).

The MOVE/MOVEM and exception-phase follow-up retains those gates. Destination
extensions use the values fetched after the source read; an incomplete interrupt
cannot become a disk snapshot. External synthetic transaction tests qualify the
shared compiler/runtime separately from cartridge observations. They are not
inserted as game hints, and internal reference agreement alone cannot replace
them. Only the targeted exact-ROM records are refreshed after successful checks.

The earlier Mega Drive video qualification added complete interlace capture and
clock-driven horizontal counters/HBlank after CPU exceptions and RAM mirrors.
Authored video patterns, a separate counter reference and targeted cartridge
conversions stay separate from hardware and gameplay evidence. See the
[video checks and remaining limits](MEGADRIVE_VIDEO.md).
RAM observations retain exact-ROM ownership and live-byte guards. One native
body can cover the same physical RAM bytes at all console aliases without
changing relative PCs or importing another cartridge's code. That refresh requalified
three exact Mega Drive cartridges and added Sonic 2's newly reached observations.
The MOVE/MOVEM and exception-phase qualification revalidated the same three exact cartridges
without adding observations or changing other records. The snapshot remains 955 exact identities,
including 52 Mega Drive revisions, at 7,755,201 compressed bytes. These counts
describe reusable observations, not complete compatibility or gameplay coverage.

RetroRecomp keeps useful discoveries for each console and exact cartridge
revision. Converting more cartridges can expose new compiler or runtime cases;
those findings help us improve the shared source code. Conversion itself does
not automatically rewrite the compiler, and a finite catalogue does not make
scripted tests exhaustive.

## Included in the converter

`assets/compilation-knowledge.json.gz` is a compact, versioned snapshot embedded
in **Retro-Recomp.exe**. The converter reads it without creating a local folder.
New discoveries remain in the converter's local `datas/library`; both sources
are combined when preparing a game. Generated game executables already contain
their compiled code and do not need this library or learning logs to play.

Each record is bound to the console, full ROM SHA256, byte size and compiler
engine revision. A different cartridge revision or engine cannot reuse it.
Missing, invalid or incompatible records leave normal discovery and validation
enabled. Local observations remain available alongside the bundled snapshot.
This also applies to Mega Drive and Super Nintendo: neither the known-game
catalogue nor this snapshot is a conversion allowlist. Eligible unknown
cartridges are analyzed directly, then validated before their discoveries
can enter the shared snapshot.

The snapshot contains numeric instruction addresses, bank identifiers, hashes
and offsets into the user's own ROM. It contains no ROM bytes, copied audio
drivers, artwork, executable code, credentials, titles or machine paths.

| Console | Reusable information |
| --- | --- |
| Master System / Game Gear | Verified banked instruction entries and ROM offsets for guarded RAM patterns |
| Game Boy | Observed ROM instruction entries by bank |
| NES | Observed ROM entries by 4 KB physical bank |
| Mega Drive | ROM entries and ROM offsets for guarded 68000/Z80 RAM variants |
| Super Nintendo | ROM offsets for guarded RAM variants and SPC700 opcode masks |

RAM patterns can be shared only when their bytes can be reconstructed from the
same user-provided ROM. Other dynamic patterns stay local. Existing live-memory
guards still apply, and an unknown case can use the reported interpreter fallback.
The snapshot never bypasses the native/reference validation gate.

## Release 0.24.0 snapshot

| Console | Exact cartridge records |
| --- | ---: |
| Master System | 258 |
| Game Gear | 1 |
| Game Boy | 606 |
| NES | 23 |
| Mega Drive | 51 |
| Super Nintendo | 15 |
| **Total** | **954** |

The snapshot is **7,734,174 bytes compressed (about 7.4 MiB)** and
29,743,114 bytes before compression. These counts describe qualified reusable
observations, not the number of fully playable or universally interpreter-free
games. Each observation remains scoped to its exact cartridge and engine.
The converter includes this snapshot, not the private campaign registers,
downloaded images or raw local learning library.

## Development snapshot, 10 October 2026

The SRAM qualification refreshes one existing MD record and adds one exact
cartridge record after the normal four-scenario native/reference gate. The
development converter now embeds **52 MD records and 955 total records**;
the other consoles and the remaining fifty MD records are unchanged.
The snapshot is **7,755,866 bytes compressed** and 29,846,918 bytes before
compression. Only verified numeric ROM references and opcode masks are shared;
player SRAM, states, artwork and the private library remain local.
Native/reference agreement and serialization tests are distinct from
game-menu saving, complete gameplay and independent hardware fidelity.

## Master System qualification, 9 October 2026

The SMS campaign qualified 256 distinct supplied cartridges, followed by two
additional gun editions: **258 exact cartridges** in total. It used extended
native coverage, up to six passes and 7,200 frames per demo/play scenario, with
up to eight concurrent conversions. Both final scenarios recorded zero fallback cycles;
strict execution and CPU/RAM/framebuffer/VDP comparisons with the reference
passed. This evidence covers the scripted scenarios, not every gameplay path or
physical hardware behavior. Eight byte-identical extra files were skipped and
one misleadingly named Game Gear cartridge was excluded from the SMS batch.

The retained SMS observations occupy about **11 MiB locally**. The shareable SMS
portion is only **12 KiB compressed**: 258 exact ROM identities and 101 verified
ROM entry hints. Extended ROM translation does not need an observation for every
translated byte. The 2,970 observed RAM variants without a verified ROM source
remain local; embedding their raw bytes would violate the ROM-free format.
Existing qualified records for the other five consoles were preserved unchanged.

Discoveries also produced common source fixes: a reference BIT memory access
must not write back and accidentally change a bank register; withdrawn VDP IRQs
must not remain pending across DI/EI; explicit learning writes must support long
Windows paths. These fixes are bundled compiler/runtime behavior and therefore
benefit new cartridges independently of per-game hints. A Sega hardware header
also takes precedence over a misleading `.sms`/`.gg` extension.

## Game Boy qualification, 10 October 2026

The initial supplied DMG batch finished: 638 input files, **592 qualified exact
cartridges**, 28 successful byte-identical extras skipped, and 18 failed input
attempts covering 17 exact cartridges. Six conversions ran concurrently on the
final continuation, with up to six passes and four 7,200-frame scenarios.
Internal instruction-by-instruction CPU/memory comparisons passed for all 592
qualified exports. Of these, 487 recorded zero fallback cycles in the scripted
scenarios; 105 retained reported fallback. This does not establish complete
gameplay coverage, physical hardware fidelity or physical latency.

That campaign's snapshot contained **773,878 numeric Game Boy entry hints** for
those 592 exact identities. Its GB portion occupies **2,014,198 bytes compressed**
(about 1.92 MiB); the snapshot after that campaign was 6,711,274 bytes. Existing records for the
other consoles were preserved. The local converter was rebuilt and its embedded
snapshot audited. No ROM bytes, private RAM contents, artwork or private paths
were added to the reusable knowledge resource.

The initial failures remained separate from shared qualified hints. Five CPU comparisons
disagreed at instructions starting at `0x3FFE` or `0x3FFF`, around the boundary
between fixed and switchable ROM banks. Operand reads under the live bank mapping
were identified for follow-up; the correction and evidence are recorded below.
Other retained failures include headless probe timeouts, a boot access violation
and an incomplete fallback inventory. A timeout alone does not identify a CPU
bug. Follow-up work must preserve the CPU validation gate.

Private evidence is kept in `.build/gb-library-expansion/`: final conversion
results, qualified and residual-fallback inventories, exact-ROM compiler findings,
source integrity, knowledge summary and converter audit. Never publish that
private directory. The 22 approved missing Game Boy cover corrections use the
separate links-only `assets/cover-references.json`; their downloaded images stay
in the local artwork cache.

## Mega Drive startup qualification, 10 October 2026

A targeted follow-up fixed a shared learning/translation boundary: valid 68000
instructions at the end of work RAM were excluded by a maximum-size reservation.
The converter now checks their actual length and retains all live-memory guards.
An additional 1,800-frame early-start replay is part of the advanced scan,
alongside the existing demo, play and varied-input scenarios. Every replay is
compared with the internal CPU/video/audio reference before its observations
enter the library.

Testing the 42 existing exports found five cartridges with fallback when starting
early, despite zero fallback in their previous final scenarios. Those five now
record zero interpreted 68000 and Z80 operations on all four scenarios after
regeneration. Two other cartridges passed the RAM-boundary regression checks.
These are scripted coverage and internal-reference results, not complete gameplay
or independent hardware validation. The full Mega Drive and SNES batches remain paused.

Seven newly qualified exact Mega Drive identities were added to the bundled
snapshot, bringing its Mega Drive catalogue to **35 cartridges**. Previously
qualified records were preserved unchanged. The whole ROM-free snapshot is now
**7,035,273 bytes compressed** after this MD refresh, an increase of **323,999 bytes**; six RAM patterns
without a matching source in their own ROM remain private. The new instruction
windows are represented by offsets into the exact user-provided ROM, never copied
game bytes. Private before/after counts, reference reports and resolved-problem
history are retained under `.build/md-ram-tail-20261010/` and the MD problem register.
The local converter was rebuilt and its embedded snapshot, modules and resources
audited against the current source. The remainder of the paused collection's
observations stays local until its own snapshot refresh.

## Mega Drive first twenty exports, 10 October 2026

After the user removed the Mega Drive executables, a targeted batch regenerated
the first twenty supplied files alphabetically with eight concurrent conversions,
up to six passes and the advanced scan. All twenty passed the four scripted
scenarios: demo, play and varied inputs at 7,200 frames, plus early-start at
1,800 frames. No 68000 or Z80 interpreter operations occurred in the final
scenarios. Internal CPU/memory/visible-frame/audio PCM comparisons passed.
The actual compressed exports also passed 1,800-frame early-start replays
against those references. This does not qualify every gameplay path, physical
latency or hardware fidelity independently of the internal reference.

The verified Japanese Alex Kidd cartridge's empty region header is now handled
by its complete SHA256 identity; its other hashes match the Libretro/No-Intro
Japan record. Other ROM revisions cannot inherit that exception. No cartridge
bytes were modified. Both distinct editions of After Burner II and Aladdin
remain separate exports, and the cartridge header determines PAL/NTSC timing.

Sixteen new exact MD identities were added and four requalified, bringing the
MD snapshot to **51 cartridges and 809,553 numeric hints**. All other consoles
and the remaining 31 MD records are unchanged. The full snapshot occupies
**7,734,174 bytes compressed**, **29,743,114 bytes uncompressed**, an increase
of **650,559 bytes**. No unqualified observations or ROM bytes were included.
Its SHA256 is
`baf35f3b50a1c3a8f80e9fe8fd37b1a9226578a7e958d6b87f9a3780b2f5f952`.
Private batch evidence and the snapshot audit are under
`.build/md-first20-20261010/`. The local converter was rebuilt; its embedded
snapshot, 52 Python modules and 128 resources match the current sources.
The historical collection checkpoint now records
43 qualified cartridges; it is not an inventory of the twenty installed EXEs.
The full MD collection and SNES campaign remain paused.

## Game Boy APU/menu follow-up, 11 October 2026

Super Mario Land and Tetris were requalified after the shared APU corrections
and direct F5 palette toggle. Both passed four 3,600-frame coverage probes
with zero fallback and their deep CPU comparisons. Only these two GB records
were refreshed; all other exact-ROM records were preserved. No new numeric
entry hints were discovered: the current 955-identity multi-console snapshot
remains byte-identical, including 606 GB identities / 793,352 GB hints.
It is verified in the rebuilt converter. The APU expectations are qualified
separately by authored hardware checks, not by these entry hints or the shared
CPU reference; unspecified-game sprite flicker remains unqualified.

## Game Boy targeted compiler follow-up, 10 October 2026

After build, trace and guarded-native-helper improvements, 14 of the initial
17 failed exact cartridges now complete all four 7,200-frame probes and their
deep internal CPU comparisons. Thirteen report zero fallback on those probes;
Max remains qualified with reported writable-code fallback. Three other previously
qualified cartridges have lower RAM fallback, and Mario was requalified as a
performance control. Details and timings are in [the Game Boy profile](GAME_BOY.md).

The refreshed snapshot preserves 588 GB records, requalifies four and adds
14 identities: **606 exact GB cartridges and 793,352 numeric ROM entry hints**.
The GB records compress to **2,063,871 bytes**. The complete multi-console
snapshot is **7,083,615 bytes compressed**, **27,105,549 bytes uncompressed**,
only **48,342 bytes larger** than the preceding MD refresh. Every other console's
records are unchanged. Its SHA-256 is
`ac37d783ee358ad7282f3de0b36220300d55317f35cf5502ff2eed8b739c4e36`.
Only numeric observations from successful exact-ROM qualifications were added;
no game bytes, RAM dumps, images or private paths enter the resource.

Paperboy 2, Spiritual Warfare and The Ren & Stimpy Show: Veediots! remain
unqualified after the unchanged 600-second probe timeout. Their diagnostics
stay private. The cumulative register now has 500 identities with zero fallback
in their qualified scenarios and 106 with residual fallback. This combines the
initial campaign with targeted follow-up, not a new full-library qualification.

Private evidence is in `.build/gb-speed-20261010/`; the collection's
`compiler-findings.json` retains the initial summary, resolved failures and
remaining cases by full ROM SHA-256. The converter embeds the updated snapshot;
existing game exports require regeneration to use changed native helpers or
generated code. The global Mega Drive and SNES campaigns remain paused.

## Workflow for future sessions

1. Read `README.md`, this guide and the local `docs/PROJECT_STATE.md` before
   continuing compiler work. Preserve the source ROMs and unrelated edits.
2. Convert the cartridges needed for the investigation, with up to eight
   simultaneous conversions when resources allow. Keep NAS sources read-only;
   all build files, observations, downloads and exports stay local.
   Exact copies wait for the current conversion of that ROM without blocking
   unrelated games from using free workers. A failed first copy still allows
   a later identical input to retry; successful copies are deduplicated by
   console and exact ROM identity.
3. Inspect new fallback sites or disagreements, fix the shared compiler/runtime
   where appropriate, and run meaningful checks for that change. Record native
   coverage, CPU agreement, hardware fidelity, gameplay and physical latency
   separately. Gameplay and listening checks belong to the user unless requested.
   Maintain a private register by console and full ROM SHA-256 of conversion
   failures and fallback still present in the final probes. Separate main and
   audio CPU counters, retain error messages and diagnostic paths, and keep
   rejected cartridge formats separate from compiler failures. Preserve resolved
   cases in the history. These diagnostics must not enter the shared snapshot.
4. Refresh the compact snapshot from qualified local observations and successful
   conversion reports. Pass all relevant local ROM directories explicitly:

   ```powershell
   python tools/build_compilation_knowledge.py --rom-dir ROMS --reports Export/Games
   ```

   Repeat `--rom-dir` for additional local input directories. Report the compressed
   size and omitted observations. Do not copy the private library wholesale.

   When refreshing one console, preserve the existing qualified snapshot with
   `--base`, especially if old game reports have been deleted:

   ```powershell
   python tools/build_compilation_knowledge.py --rom-dir ROMS/MasterSystem --reports Export/Games --base assets/compilation-knowledge.json.gz
   ```

   The base must be a previously qualified ROM-free snapshot. Its records stay
   unchanged unless the current conversion evidence qualifies a replacement.
   The summary distinguishes retained records, newly qualified identities and
   refreshed identities. A failed new conversion cannot replace a base record.
   Runtime hints remain bound to the exact console, ROM hash, size and engine.
5. Build the converter with `tools/package.ps1`; audit the embedded snapshot and
   exact source/resources with `tools/prepare_publication.py`. Record the results
   and remaining limitations in `docs/PROJECT_STATE.md`. Publication needs an
   explicit user request.

Refresh and embed the snapshot after new qualified discoveries, so the next
converter build shares those hints. New and refreshed records require source
ROMs in the supplied directories and successful qualification. Existing
qualified base records can be retained without rebuilding other consoles. It does
not claim compatibility with every revision or every possible gameplay path.
Updating the converter does not change existing game executables; runtime
changes require regenerating the affected games.

## Gameplay paths missed by startup scripts

The Mega Drive converter now expands reached tables of adjacent direct jump
instructions during offline analysis. Advanced scanning also includes a fresh
menu/dialogue replay with released A/C confirmations for controller games.
Each new replay is compared with the internal CPU/memory/video/PCM reference
before learning. Observations from a copied gameplay state use the same gate;
the player's state and cartridge saves never enter the shared snapshot.

The Shining Force II follow-up reproduced fallback 31 frames after loading a
copied player state and pressing an action button. The prior startup probes had
missed these branches. Three state-based replays and one fresh-boot menu replay
matched the internal reference before 61 ROM instruction observations were
learned. This is a coverage fix, not a claim of complete gameplay validation.

## Common translator corrections

Shared observations are not a substitute for correcting the common translator.
The MC68000 synchronous-exception work adds native vector/stack behavior and
independent CPU fixtures; every subsequent Mega Drive generation uses that
correction. Unknown or unsupported instructions remain visible limitations.
The usual exact-ROM reference gate still applies before hints can be promoted.
See [exception verification scope](MEGADRIVE_CPU_EXCEPTIONS.md).

VDP queue, asynchronous read prefetch, separate DMA source/FIFO phases, pending-IRQ and within-slice CPU
resume corrections live in the shared runtime,
rather than per-game hints. Exact-ROM requalification must compare CPU, memory, visible image and
PCM again after such a change. The compilation snapshot contains reached ROM
entries only; queued writes, pending/half/ready read buffers, DMA progress, IRQ latches, player snapshots and
cartridge saves never enter it. The three targeted cartridges are requalified
after the timing change; the wider collection stays paused. See
[video and timing qualification scope](MEGADRIVE_VIDEO.md).

DMA bus suspension and Z80 external-bus ownership also belong to the common
runtime. They are not per-ROM hints. Requalify the bounded exact-ROM targets
after changing them, then refresh the verified shared snapshot and bundle it
in the local converter. Live coroutine stacks and pending host F8/F9 requests
never enter the compilation library. Keep the wider campaigns paused until
their separate hardware/gameplay gates are ready.

Request-driven Z80/68000 arbitration and clocked bus reservations likewise
belong to the common runtime, not a growing list of per-game delays. Only
requalified exact-ROM observations may enter the shared snapshot after this
change. Requests, reservation clocks and live CPU continuations never enter it.
The bounded Sonic 1/2 and Shining Force II qualification is recorded separately
from physical bus fidelity in the local arbitration report.

Ordered main-CPU transactions, clock-debt persistence and common EA timing/read
corrections likewise belong to the shared compiler/runtime. A new bus-budget
failure prevents qualification even if native and reference agree on the same
bad estimate. Requalify the exact ROMs before refreshing their shared records;
do not promote a failed report. Clock state stays in the game's quick state,
not in the compilation snapshot. Evidence for this follow-up is
`.build/md-bus-phases-20261010/qualification.json`.

## Reproducible cold measurements

`RETRO_RECOMP_BUNDLED_KNOWLEDGE=0` disables the shared snapshot. Selecting an
isolated library with `RETRO_RECOMP_LIBRARY_DIR` (or the legacy
`SMSRECOMP_LIBRARY_DIR`) also disables it, so a cold compilation benchmark does
not silently reuse packaged knowledge. Discovery and validation still run.
Record whether local and bundled knowledge were enabled when comparing times.

## Operand-dependent arithmetic qualification

MUL/DIV operand costs, their stream phases, DBcc expiry and divide-overflow
corrections belong to the common compiler/runtime, not per-game observations.
Requalify exact ROMs against the reference and independent bus-budget gates
before refreshing the verified bundled snapshot. Only the three bounded MD
records are refreshed here; raw corpus files, private library data, player
states and runtime timing latches are never embedded as knowledge. See
[CPU phase scope and remaining gates](MEGADRIVE_PREFETCH.md).
