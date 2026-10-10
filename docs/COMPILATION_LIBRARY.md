# Shared compilation knowledge

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

## Reproducible cold measurements

`RETRO_RECOMP_BUNDLED_KNOWLEDGE=0` disables the shared snapshot. Selecting an
isolated library with `RETRO_RECOMP_LIBRARY_DIR` (or the legacy
`SMSRECOMP_LIBRARY_DIR`) also disables it, so a cold compilation benchmark does
not silently reuse packaged knowledge. Discovery and validation still run.
Record whether local and bundled knowledge were enabled when comparing times.
