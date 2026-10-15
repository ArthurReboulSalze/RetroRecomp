# Shared compilation knowledge

## Partial Neo Geo campaign included in 1.1.0 — 15 October 2026

The fifty-game campaign was stopped at the user's request after its active
conversions finished: **23 successes, one failed AES snapshot check, 26 not
started**. Only the 23 successful exact cartridge/BIOS records are promoted.
The failed 3 Count Bout observations stay private until full requalification.
No remaining game or retry is launched by this knowledge update.

The 1.1.0 snapshot contains **1,092 records,
including 65 Neo Geo**: **53,561,244 raw /
14,594,906 gzip bytes**, SHA-256 `80ee5ce98c53fede21ff64293c19b022393a01ffce40c767b26c89038d94ebc7`.
All earlier numeric observations are preserved; the six other console banks
are unchanged. Exact sorted P/BIOS roots use validated, bounded positive deltas
instead of repeated region/offset pairs. Expansion and real-input consumer
checks preserve the same addresses and reconstructed guards, with no instruction
bytes added. The previous representation remains readable and the decompressed
64 MiB limit remains in force. Despite 23 additions, the compressed snapshot is
**1,690,241 bytes smaller** than release 1.0.3.

Promotion rechecks the original fresh-reference/packed receipts: 161
MVS/AES/enhanced route comparisons with zero observed main/sound fallback,
three MVS and two AES fresh-process state points per game, invalid-state
rejection and ordinary-save checks. The numeric knowledge does not depend on
artwork availability or a later state-validator correction. Old EXEs are not
regenerated here; every future conversion still performs its fresh gates.
Only numeric reconstructible references are embedded, never the private library,
ROMs, BIOS, RAM dumps, saves, covers or audio. AES observations remain separate.
Evidence: `.build/neogeo-fifty-20261015/partial-qualification.json` and
`partial-knowledge.json`. The partial campaign stays paused; only its verified
numeric snapshot is distributed in the converter.

## Eight additional Neo Geo cartridges — 15 October 2026

Eight newly qualified exact cartridge/BIOS identities extend the release 1.0.3
bank to **1,069 records, including 42 Neo Geo**.
The snapshot contains **60,006,996 raw / 16,285,147 gzip bytes**,
SHA-256 `1e0dd405b814685b54fc9fc7dd791ce9065ff5eba43900aa3d21e164317eef70`. Its compressed increase is
**339,019 bytes**; every earlier record and every other console
is preserved unchanged. The 64 MiB decompressed bound remains active.

Fresh standard MVS/AES reference, packed-executable, state and ordinary-save
gates precede promotion. Enhanced-mode discovery for Twinkle Star Sprites adds
previously unreached banked cartridge paths: the same 9,000-frame two-player
route goes from 3,195 interpreted 68000 instructions to zero,
with matching reference CPU/hardware/image/PCM results. Only validated numeric
references enter the bank; no game, BIOS, RAM dump, image, audio or save is added.
AES observations remain separate and private. The eight additional enhanced
replays also pass, without asserting full-game or physical-hardware fidelity.

The release converter bundles this verified snapshot. Two user-approved Neo Geo
front-cover references bring the separate link-only catalogue to 36 entries.
All eight downloaded covers are reused successfully with network access blocked;
the artwork itself stays in the local cache. Evidence:
`.build/neogeo-series-20261015`. See [Neo Geo](NEOGEO.md) for the sampled games.
This verified snapshot is included in release 1.0.3.

## Selective regeneration and Neo Geo modes — 15 October 2026

Release 1.0.2 records the exported binary hash, converter/runtime inputs and
the exact fallback candidates consumed by each successful conversion. Unchanged
exports are kept; new hints, changed settings or a new converter trigger fresh
conversion. Unsupported unchanged hints do not cause an endless rebuild loop.
The force option bypasses freshness only, never validation or overwrite protection.

Neo Geo keeps the original MVS identity for existing saves and knowledge. The
optional verified AES firmware adds a separate AES feedback/save identity.
Both modes have full BIOS native candidates and live guards; the shared MVS bank
only receives numeric observations actually observed on its MVS reference routes.
AES private hints remain separate and are checked on fresh AES routes.

Two requalifications refresh the existing 34 Neo Geo records without increasing
the total of 1,061 exact identities. Other consoles and all older qualified
entries are preserved. The snapshot is 58,541,482 raw / 15,946,128 gzip bytes,
SHA-256 `3f2178f085f25c7f57fb0eb6978943a64d2d37abba93eb66210e475433412a76`.
No BIOS, cartridge, save, capture, audio or raw feedback file is included.

## Shutdown-only gameplay feedback — 15 October 2026

All seven generated-game profiles now collect bounded fallback candidates in
memory and save them only at normal shutdown. The converter imports the exact
game's file on regeneration, then runs its existing fresh validation gates.
Each game-side file is capped at 131,168 bytes; no fallback creates no file.
F12 toggles recording, enabled by default. Each console's Options page also
offers a recovery folder and an **Import fallback hints** button: it retains
an independent private copy without compiling or loading a ROM. Imported
observations survive removal of the original game folder and path changes.
The private feedback bank is distinct from qualified shared knowledge and must
never be bundled. See [Runtime feedback](RUNTIME_FEEDBACK.md) for scope,
per-console candidate types, storage, checks and remaining unsupported cases.

## Optional enhanced Neo Geo mode — 14 October 2026

The standard Metal Slug 3 conversion is freshly qualified after adding the
optional F5 mode, retaining the same cartridge/BIOS identity and all earlier
verified numeric observations. The shared bank contains 1,061 records / 34
Neo Geo, 58,540,943 raw / 15,946,134 gzip bytes,
SHA-256 `120de0085d379d0743183f59cb93885953889c8fb518bd17a1829d60f94930c1`. Every other console is preserved. The local
converter includes the verified bank and the new runtime; no public release is
made here. Enhanced-mode scene/cold replays are validated separately and do not
promote private state data or artificially inflate the standard compilation bank.
Evidence: `.build/neogeo-enhanced-20261014`; see [Neo Geo](NEOGEO.md).

## Neo Geo runtime performance requalification — 14 October 2026

Metal Slug 3 and Sengoku 3 are freshly qualified after reducing native dispatch
and sprite-rendering overhead. Nine reference/packed routes, six fresh-process
F8/F9 points and both ordinary-save gates pass. Three additional action replays
match the preceding runtime with zero observed main/sound fallback.

The resulting verified snapshot is **byte-identical** to the preceding bank:
**1,061 records / 34 Neo Geo**, **58,540,943 raw / 15,946,134 gzip bytes**, SHA-256
`120de0085d379d0743183f59cb93885953889c8fb518bd17a1829d60f94930c1`.
No new observed code path is needed for this performance change; neither static
candidates nor the raw private library are added to inflate coverage. Every
older observation and every other console's record are retained. The local
converter includes this verified snapshot and the optimized runtime for future
exports. This is not a public release or a full-game hardware qualification.
Evidence: `.build/neogeo-performance-20261014`; see [Neo Geo](NEOGEO.md).

## Early Neo Geo gameplay paths and shared xBR — 14 October 2026

Three fresh qualifications refresh the exact Metal Slug 3, Sengoku 3 and
KOF 2001 cartridge/BIOS records after early gameplay feedback. All four action
buttons join the default discovery routes, with an additional recorded grenade
route for Metal Slug 3. Older verified numeric hints for the same identity/pins
are retained when refreshing a record; the raw private library is never imported.
The larger fixed-ROM/BIOS static scan is not itself promoted as observed knowledge.

The bank remains **1,061 records / 34 Neo Geo** and is now **58,540,943 raw /
15,946,134 gzip bytes**, SHA-256
`120de0085d379d0743183f59cb93885953889c8fb518bd17a1829d60f94930c1`.
It adds **11,738 gzip bytes**; every other console and every earlier verified
observation are preserved. Fresh reference, packed-export, state and ordinary-save
gates still apply. All four replayed action routes have zero observed fallback
and identical CPU/hardware/image/PCM results; these are bounded gameplay paths.

The local converter also bundles the shared xBR cache for all seven profiles.
It changes presentation cost, not compilation observations or the filtered image.
Only newly generated EXEs receive the updated runtime. Evidence and the original
held-out replays remain under `.build/neogeo-gameplay-coverage-20261014`; see
[Neo Geo validation](NEOGEO.md). No public release is made in this task.

## Ten additional Neo Geo cartridges — 14 October 2026

Ten further exact MVS cartridges pass fresh reference/packed comparisons,
three fresh-process F8/F9 points each, invalid-state rejection and ordinary-save
checks. Their numeric observations extend the bank to **1,061 records total,
including 34 Neo Geo**, **58,502,698 raw / 15,934,396 gzip bytes**, SHA-256
`1ccc1f854bc00c83a0fe7b56f95c95fd9b8c0ea99407667ee326638953816a7f`.
The added compressed size is **369,337 bytes** (about 361 KiB); every preceding
record is retained and every other console remains unchanged. The decompressed
64 MiB limit and all fresh-validation gates remain active. This snapshot is
included in the local development converter; no public release is made here.

Only reconstructible numeric P/BIOS/RAM/sound hints are promoted. Inputs,
states, ordinary-save contents, captures and audio stay private. Evidence is
under `.build/neogeo-additional-20261014`; see [the sampled paths](NEOGEO.md).

## Qualified Neo Geo MVS development snapshot

The final campaign refreshes all **24 Neo Geo records**: **1,051 records total**,
**56,898,332 raw / 15,565,059 gzip bytes**, SHA-256
`2513b86760176a0a8ab7585395fc6417f54adcefd29af2ffa5c8d973d6a60e52`.
It adds 15 exact cart/BIOS identities to the previous nine, while preserving
every other console's records byte for byte. The increase is **712,010 gzip
bytes** (about 695 KiB); the 64 MiB decompressed budget remains intact.

Only the current completed reference routes are promoted from a reused build
folder; stale developer journals cannot add roots silently. The promotion gate
also verifies zero fallback in the saved continuous/restored state reports,
in addition to the candidate hash, exact cart/BIOS identity, fresh reference,
packed replay and ordinary-save checks. The six long controller paths retain
their newly discovered numeric entries. No cartridge, BIOS, RAM dump, state,
NVRAM/card contents, image or audio is included. Evidence stays under
`.build/neogeo-final-qualification-20261014`; see [Neo Geo](NEOGEO.md).

## Neo Geo cartridge/save qualification update

After the cartridge-protection and ordinary-save campaign, the development
snapshot contains **1,036 records / nine Neo Geo**, **53,844,079 raw / 14,853,049
gzip bytes**, SHA-256
`f2a2cbf3f240f0b73c9700fc0b456d90141026e349c31b3f71b580ecbbe2eb8c`.
Eight current integrated records are refreshed, including six additions; every
other console and the previously qualified Metal Slug 3 record are retained.
The compressed increase over the preceding integrated snapshot is 450,238 bytes.
The 64 MiB decompressed bound and fresh reference/packed/state gates remain.

The builder additionally requires the ordinary-save route's native counters,
lazy initialization and either fresh-process memory reload or an explicitly
observed no-change route. Discovery of NAM-1975's late card path fixes additional
main-CPU fallback. MSLUGX/PVC and two further SMA variants contribute numeric
P/BIOS/RAM/sound references only; card/NVRAM data, volatile PVC RAM dumps, images,
PCM and private journals stay local. The proof for this refresh is under
`.build/neogeo-cartridge-saves-20261014`. The dated sections below preserve the
earlier snapshots and their original qualification status.

## Neo Geo development observations

The integrated development converter now includes **three BIOS-scoped Neo Geo
records**, qualified through fresh reference, packed-export and F8/F9 checks.
The shared snapshot contains **1,030 records** in total; the previous 1,027
records are retained unchanged. It is **51,870,239 raw / 14,402,811 gzip bytes**,
SHA-256 `eda5f2dec415d1f3907eb9ab00480c734722c72ba2437c91ebd16e09ad6cdf35`.
The added compressed size is 194,846 bytes. No ROM or BIOS bytes are included.

Neo Geo records use the exact prepared region/NGH identity, four selected BIOS
component hashes, MVS Europe, and pinned loader/runtime revisions. Numeric
P/BIOS roots, RAM source offsets and Z80 structural references reconstruct
guards from the user's own input. Wrong firmware, changed regions, out-of-range
references and raw-word/path fields are rejected. Shared hints remain additive:
every conversion still builds a fresh reference before learning and compares
the packed game and fresh-process states before replacing an export.
Local qualified records live in `datas/library/ng/<cart-and-BIOS-key>` beside
the converter. `tools/build_neogeo_knowledge.py` accepts integrated conversion
reports only after reference/packed/state qualification and candidate-hash
verification, and preserves every other console's records. Earlier prototype
receipts below remain private; they are not imported as unchecked journals.

The standard-board and protected-board Neo Geo prototypes store private numeric reached-PC/guard and
comparison receipts under its local build directory. Both CPUs are native on
the bounded tested routes; these observations are **not promoted** to the bundled bank. Future Neo Geo
records must be keyed by the original multi-region contents, parent data when
used, the selected BIOS, system/region and pinned loader/runtime/CPU versions.
Static-native and hardware/gameplay qualification still apply before promotion.
The earlier prototype snapshot was unchanged. See [Neo Geo](NEOGEO.md).
Banked Neo Geo roots now include the actual physical P/BIOS offset observed
under the current mapping, rather than a guessed offset from the virtual PC.
Metal Slug, Neo Drift Out, Puzzle Bobble and Samurai Shodown II receipts remain
local under `.build/neogeo-expansion-20261014`. Retain them with their exact
cartridge/BIOS identities; do not import their raw journals into the released
bank or skip ordinary reference, packed-export and state validation.
Protected-board receipts for Fatal Fury 2, KOF '98, KOF '99 and Metal Slug 3
stay under `.build/neogeo-protected-20261014`. Their guarded 68000 RAM entries
retain numeric `(RAM offset, source region, source offset, byte length)` links
only when the exact instruction bytes can be reconstructed from the identified
P/BIOS input. Unreconstructible variants stay in private discovery reports;
do not copy raw RAM words into a reusable or bundled observation record.
Code guards exclude live protection response/random ports and the KOF '98
mutable overlay. Board state, sprite line buffers, snapshots, PCM and captured
images are validation evidence, not compilation observations to distribute.

## Release 1.0.0: SNES device knowledge and lossless SPC ranges

Current bundled snapshot: **1,027 exact ROMs / 44 SNES**, **51,025,629 raw / 14,207,965 gzip bytes**.
SHA-256: `a5b85b347b0512a54bb3a1c75ed3a549544a828ff9208780b5a50bfd50a5029b`. Eight device cartridges pass ordinary,
packed and fresh-process state checks before promotion; four also pass longer
active-device routes. Unchanged console records are preserved. Existing SNES
SPC guards are losslessly encoded as PC ranges and ROM offsets; every previous
pair is checked for semantic equality. Both old pairs and bounded ranges remain
readable. No ROM, RAM dump, firmware, cover or private journal is bundled.
The 64 MiB raw bound remains; hints never bypass conversion validation.

Two conversions from the final audited one-file EXE start with an empty private
library and use this bundled snapshot. See [SNES evidence and limits](SNES.md).
Dated sections below preserve historical counts and publication status.

## Local SNES standard-profile qualification and opcode guards

Previous snapshot: **1,023 exact ROMs / 40 SNES**, **58,832,410 raw /
15,035,601 gzip bytes**, SHA-256
`bc7d03f401b009965ef39bb0e9a80dbd7043edb7bd49032b09aa3a4831a194bd`. Nine SNES records are refreshed; 31 others and every other
console record remain unchanged. Relative to the previous completed 34-record
snapshot, this campaign adds six exact revisions and requalifies three controls.

SNES `ram_opcode_refs` contain only PC/ROM-offset numeric pairs. The user's exact
ROM reconstructs the guarded opcode; operands stay live on the timed bus. This
retains useful observations whose changing four-byte literals had no ROM source.
No raw RAM journal, ROM, firmware, cover or player data is bundled. Shared hints
never bypass ordinary CPU/image/PCM validation. The decompressed 64 MiB bound
is retained. See [SNES scope and evidence](SNES.md).

The final audited local one-file converter embeds this snapshot and passes two
fresh-private-library conversions. The published 0.26.0 package is unchanged.
Earlier dated sections below retain historical snapshot sizes and counts.


## SNES object, cartridge-decoding and nested-IRQ qualification

The local snapshot contains **1,017 exact ROMs / 34 SNES records**. Eight new
revisions are promoted only after their final ordinary and compressed-export
CPU/state/frame/PCM comparisons and fresh-process states pass. Six controls
are requalified; twenty other SNES records and every other console's records
remain identical. Native coverage, hardware checks and reviewed gameplay
are separate evidence: the Axelay case showed why internal image agreement
alone cannot establish hardware fidelity. Timing and mapping fixes belong
to the common runtime, rather than game-name exceptions in the hint bank.

Size: **53,484,310 raw / 13,704,461 gzip bytes**, an increase of 1,817,450
compressed bytes. SHA-256:
`c7ffb62f854250026d38daa135332f7108a01c954c2cccf7230694bcb3345cc0`.
The 1,178 RAM patterns without reconstructible ROM references remain private.
There are no ROM bytes, raw private journals, firmware, covers or player data
in the resource. The decompressed 64 MiB bound is retained.
Shared observations never bypass normal conversion/reference validation.

Evidence: `.build/snes-nested-irq-qualification-20261013/knowledge-build.json`,
`delivery.json`, original independent fixtures and the final frozen-converter
checks. The resource is included in the locally rebuilt one-file converter;
the published 0.26.0 release is unchanged until a publication is requested.

## Super Nintendo bus arbitration requalification

The CPU/DMA/HDMA correction belongs to the common runtime. It does not add
per-game timing patches to the knowledge resource. The six exact SNES controls
undergo ordinary CPU/frame/PCM comparison again before their hints can be
refreshed; packed routes and fresh-process states are checked separately.
CPU bus requests, channel counters, PPU journals and player saves are never
compilation observations. The other twenty SNES records and every other
console's records are preserved. Evidence is kept locally in
`.build/snes-bus-arbitration-20261012/knowledge-build.json` and `delivery.json`.

The qualified observations are unchanged: **1,009 exact ROMs / 26 SNES**,
**46,497,854 raw / 11,887,011 gzip bytes**, with the same snapshot SHA below.
The correction requires regenerating affected game executables; reusing hints
never bypasses their normal validation. No private library, firmware, ROM or
player data is added to the converter.

## Super Nintendo camera and HDMA refresh

The verified local snapshot now contains **1,009 exact ROM records**, including
**26 SNES records**. Pilotwings is added only after its corrected DSP-1 paths
pass normal conversion, packed CPU/frame/PCM comparisons and fresh-process
states. Five existing SNES controls are requalified. Twenty other SNES records
and every other console's records are preserved exactly. A short Mario Kart
race is also compared through native/reference execution; neither that route
nor the library claims full-game coverage. CX4 remains interpreted and counted.

Size: **46,497,854 raw bytes / 11,887,011 gzip bytes**, an increase of 261,660
compressed bytes over the preceding snapshot. SHA-256:
`7eb71dba1a291d38087ff980c63f83aeabf71c40450d6c4db5fa843fda6672f1`.
Nineteen RAM patterns without reconstructible ROM references remain private.
The normal report timestamp must follow both main/sound observation journals;
shared hints never replace that validation. No original ROM, firmware, cover,
player SRAM or state is included. The decompressed 64 MiB bound is unchanged.

Evidence: `.build/snes-horizon-hdma-20261012/knowledge-build.json` and packed
receipts in `delivery.json`. The earlier follow-up below records the prior
snapshot and its former Pilotwings exclusion.

## Super Nintendo DMA and enhancement-circuit follow-up

The verified local resource contains **1,008 exact ROM records**, including
**25 SNES records**. Three DSP-1/CX4 revisions are added and three ordinary
controls requalified. Nineteen other SNES records and every other console's
records are preserved exactly. The hints concern the compiled 65816/SPC700
paths; they do not turn the CX4 device interpreter into native code.
Pilotwings' failed projection route contributes no record.

Size: **45,458,546 raw bytes / 11,625,351 gzip bytes**, an increase of 723,864
compressed bytes. SHA-256:
`12b2a90943ea9987a1ae5711f7798b4b719e697b28456d15689deedb060df9a7`.
Nineteen observed RAM patterns without reconstructible ROM references remain
private. Both CPU and sound journals must precede their successful ordinary
qualification report. Packed replays and fresh-process states are checked
separately. No ROM, firmware, player SRAM/state or artwork is embedded in the
shared resource; the decompressed 64 MiB bound is unchanged.

## Super Nintendo cartridge RAM and save follow-up

The verified local resource contains **1,005 exact ROM records**, including
**22 SNES records**. Four additional RPG revisions are qualified and four
existing controls are requalified; all other records remain unchanged.
The common runtime now covers ordinary cartridge battery files, SRAM code
windows and a larger bounded RAM observation set, with fetched-opcode checking.

Size: **42,665,032 raw bytes / 10,901,487 gzip bytes**, an increase of 953,001
compressed bytes. SHA-256:
`6cd437dfdd1c229085c51efacf85740010973ab9374e1f18bf58f7c6c3a639dd`.
The 4,016 RAM patterns without reconstructible original-ROM references remain
private. The resource still contains only numeric observations and exact-ROM
identities: no ROM, player SRAM, state, artwork or raw sound-driver RAM.
The overall 64 MiB decompressed size bound remains unchanged. Only the SNES
RAM-reference limit grows to 16,384; other console limits stay unchanged.

## Super Nintendo audio and display qualification

The verified follow-up contains **1,001 exact ROM records**, including **18
Super Nintendo records**. Three PAL revisions are added and five SNES controls
are requalified after complete main/sound CPU, memory, video and PCM comparison.
Other consoles and the ten untouched SNES records are preserved exactly.
Updated audio/upload behavior and full display modes come from the common
runtime; no title patch is distributed.

Size: **38,765,930 raw bytes / 9,948,486 gzip bytes**, an increase of 555,244
compressed bytes. SHA-256:
`5bcc7a43d4bacd548d7e9066e0ea6e659966b0f73cbc414108bf0820dba61b6e`.
The 179 RAM patterns without an exact reconstructible ROM source remain private.
Shared records contain numeric ROM references, never raw sound-driver RAM,
operand data, player states, images or ROMs. SNES now also requires both CPU
journals to predate the successful qualification report before promotion.

Actual compressed exports and fresh-process states are checked separately.
See [SNES development and remaining limits](SNES.md). The earlier NES and
released snapshot sections below remain historical evidence.

## Current exploration and cache follow-up

The verified local resource now retains **998 exact ROM records, 36 NES
records and 837 NES RAM entry/opcode references**. Five NES revisions are
requalified on six complete 3,600-frame paths each; the three added paths also
pass in their actual compressed exports, with fresh-process state checks.
The Batman menu replay contributes one newly qualified RAM guard. Other
consoles and the thirty-one unrefreshed NES records remain identical.

Size: **36,397,119 raw bytes / 9,393,242 gzip bytes**, just one compressed byte
more than the preceding lower-ROM/RAM-window snapshot. SHA-256:
`fea6e68bfd4d590852b264f9367b1e0f42617f5088666a1b890b0355424925f7`.

The source cache reuses generated code only. It binds the exact ROM/compiler
and ROM entry input, verifies stored source hashes and applies current RAM
guards separately. Normal tests always run again. Advanced scan observations
are compared with the reference before another compilation pass; final-pass
results are bound to the actual source EXE. Failed or stale journals still
cannot replace qualified shared records. No scripts, raw RAM, player states,
ROMs, artwork or private library enter this resource.

The frozen converter is tested on two separate launches with an initially
empty private library/project. Batman imports all 486 guards from the shared
resource in its first pass; six 600-frame CPU/frame/PCM comparisons pass on
each launch. The second launch regenerates no C source and rebuilds no object
(72 reused), while repeating every reference check. Fresh-process states also
pass. This verifies the bundled resource and stable source/include paths;
dependency/compiler caches are reused, so it is not a cold-toolchain benchmark.

## Lower-ROM and RAM-window qualification after 0.26.0

The local verified snapshot contains **998 exact ROM records**, including
**36 NES records and 836 guarded NES entry/opcode references**. This adds seven
exact NES revisions and requalifies Batman: Return of the Joker; all other
consoles and the twenty-eight unrefreshed NES records are unchanged.
Minelvaton Saga's supplied translated mapper-80 revision contributes 77 guards
for accessible Taito RAM. Only CPU entry addresses and original-PRG opcode
offsets are stored, with the existing exact-ROM and live-opcode checks.

The eight actual compressed exports pass three full 3,600-frame internal
CPU/memory/frame/PCM comparisons each and two fresh-process state continuations
after 720/1,800 frames. Journal freshness remains required. Mapper-40/FME-7
lower ROM aliases are covered by the common translator, not ambiguous seeds
in the upstream upper-address format. Protection state, operands, chip RAM
dumps, player states and cartridge battery contents are never shared.

The snapshot uses **36,397,107 raw bytes and 9,393,241 gzip bytes**, only
**664 compressed bytes more** than the released 0.26.0 snapshot. SHA-256:
`a4a7abf048635759c8d1f18c5ace7b6c71cf49315e63d2e9a9615c7755c8ea57`.

The rebuilt frozen converter passes a real Minelvaton conversion with initially
empty private knowledge and generated projects. It imports all 77 shared guards
in its first pass, reports no interpreted cycles on three 600-frame paths,
matches internal CPU/frame/PCM and passes fresh-process state continuation.
Dependency/compiler caches are reused; this is not a cold-toolchain speed
measurement. The audited EXE contains this exact final snapshot and current
native sources, with no ROM, player state or raw private library.

## Released 0.26.0 snapshot

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

SNES byte-access timing, DMA ownership, refresh holds and PPU collision latches
belong to the common runtime, rather than ROM-specific delay hints. After such
a change, requalify the exact-ROM CPU, memory, visible-frame and PCM routes
before refreshing the bundled snapshot. Bus requests, sprite/palette latches,
player quick states and independent reference captures never enter that
snapshot. Independent hardware-model disagreement must remain documented even
when the two internal CPU paths agree. The current evidence and open gates are
recorded in [SNES development](SNES.md).

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

## Neo Geo development observations

Stage 3 NAM-1975 stores reached P/BIOS addresses, exact structural Z80 RAM
observations and paired native/reference reports only in its private conversion
project. Cartridge region hashes, all four selected BIOS hashes, loader/core
pins, semantic hash and native EXE SHA identify the evidence. The controller
routes do not bypass reference validation. Native counts are checked separately
from CPU/RAM/image/PCM and serialized hardware-state agreement.

No Neo Geo record enters the production six-console snapshot yet: its
BIOS-aware shared schema and production profile are a subsequent integration
gate. Preserve these qualified numeric observations for that gate, never the
raw P/BIOS/M1/SM1 images, generated instruction C, audio, covers or user states.
The existing verified snapshot remains bundled unchanged. See
[Neo Geo prototype scope](NEOGEO.md).

Stage 4 adds private shared-host/state receipts under
`.build/neogeo-host-20261013`. CPU/image/raw-PCM/extended-state replay gates are
independent of coverage observations. A player's `.rrstate`, framebuffer, raw
audio and INI file are never compilation knowledge and must not enter the bank.
The existing 1,027-record snapshot is unchanged; no Neo Geo promotion occurs.
