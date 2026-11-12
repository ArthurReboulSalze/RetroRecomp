# Gameplay fallback feedback

## Compiled Games collection

The Windows/Linux converter keeps its collection in the private
`datas/compiled-games.json`. Opening the app restores this index without scanning
the executables again. Successful conversions register their original ROM path,
exact identity, version and report before the batch finishes. Scan games refreshes
the usual export folders; Add a games folder remembers another search root.
Missing files stay visible. Neither the index nor its local paths are bundled.

The table supports console/status filters, search and sorting. Right-click offers
Reconvert and Rescan. Routine scans read conversion metadata and bounded saved
feedback. Row rescans also hash the selected binary. Scanning never launches games
or reads ROM collections. Reconvert requires the original exact ROM, asks for it
if needed, checks ownership before replacing an executable and uses the regular
conversion and validation pipeline in the game's current folder.

New saved hints suggest regeneration. Already-consumed hints, fallback observed
in conversion tests, unreadable feedback and missing/changed files have distinct
states. No saved fallback is not proof of complete gameplay coverage: recording
may be disabled, older games may not record hints, and many paths may be untested.
Recognized hints are retained in the converter's private bank; they never bypass
fresh conversion checks or become qualified shared knowledge through a scan.

Game Memory loads one console in a worker and caches display summaries by file
size and modification time. It does not hash Game Boy traces to build the list.
Every row has an explicit console column, including older Master System records.
These summaries are for browsing only and never enter compilation decisions.

Generated Windows games keep a small, deduplicated set of interpreter misses in
host memory. They save it **only at normal shutdown**, under
`datas/fallbacks/<console>-<full-identity>.rrfb`, beside the game executable.
No fallback means no feedback file or directory. There is no per-frame history,
RAM dump, background write, upload, or interpreter log during gameplay.

**F12** switches recording on/off without opening a menu; H displays its current
state. Recording is enabled by default. The choice is saved on shutdown in
`datas/Retro-Recomp.ini`, under the exact console/game identity. Switching it off
suppresses both further capture and this session's feedback write; the existing
file is preserved. This never disables the interpreter or hides its counters.
Interpreter-disable mode is deliberately deferred: stopping before an unknown
instruction needs a safe pause/resume boundary for every CPU runtime. Neo Geo
reserves F11 for arcade/console switching with restart; each mode has its own hints.

The existing game window briefly shows “Saving fallback hints / for the next
recompilation...” while the shutdown write runs. There is no additional window
or artificial delay. Forced termination, crashes and power loss can lose that
session's unflushed observations.

## Size and storage

The binary format has a 96-byte header and 32 bytes per distinct observation.
Each machine's profile (`feedback_limit`) sets the most observations kept **per
exact game identity**, across all sessions:

| Machine | Most observations | Largest file | Recorder memory |
| --- | ---: | ---: | ---: |
| Mega Drive | 65,536 | 2,097,248 bytes (2 MiB) | 2.6 MiB |
| Every other machine | 4,096 | 131,168 bytes (128.094 KiB) | 152 KiB |
| Adventure (ScummVM) | none | none | none |

A Mega Drive game can meet far more unknown ROM entries in one walk than 4,096
(13,871 in one measured walk of a large game). Examples:

| Distinct observations | File size |
| --- | ---: |
| 0 | No file |
| 4 | 224 bytes |
| 100 | 3,296 bytes |
| 1,000 | 32,096 bytes |
| 4,096 | 131,168 bytes |
| 9,000 (Mega Drive only) | 288,096 bytes |
| 65,536 (Mega Drive only) | 2,097,248 bytes |

The file has two versions with the same layout. **Version 1** holds up to 4,096
observations and is byte for byte what release 1.7.2 wrote. **Version 2** holds
4,097 to 65,536 and is written only above 4,096, so today by the Mega Drive only
(a version 2 file with 4,096 or fewer observations is invalid: each count has one
form). Readers (the game's recorder and the converter) accept both versions up to
65,536; the machine's bound applies to what a writer keeps. A 1.7.2 game or
converter does not read a version 2 file: it refuses it (the file stays valid for
newer readers), and a 1.7.2 game that exits beside one writes its own session over
it. The converter's private copy, taken at each conversion or collection scan,
survives.

The same PC/CPU/guard bytes are stored only once. Reset and F9 do not erase the
session buffer, and no player save-state payload includes that host buffer.
Repeated sessions do not grow the file beyond the limit. At saturation, newer
session candidates take priority (this session's observations first, then the
old file's in file order; the tail of the old file is cut).

When a record is full, the header's `dropped` number says that something was left
out. On the Mega Drive it is also a **count of the distinct observations refused
at one merge, at least** (the maximum over merges): a small bit filter counts each
refused observation once, so the figure is a lower bound, about 5 % short at
100,000. The conversion log and the report (`refused_records`, with `limit`) show
it for the Mega Drive; for the other machines the log says only that more were
refused and the report gives `null`. On a version 1 file the number is a flag
only (a 1.7.2 game counted calls, not observations), so a machine whose bound is
above 4,096 reads it as zero.

The recorder reserves its tables as static host data (152 KiB at 4,096; 2.6 MiB
on the Mega Drive), with no allocation, file access or locking on the instruction
capture path. Shutdown alone reads/merges the old file (a working copy of at most
2 MiB and 64 KiB, allocated then), takes a bounded Windows mutex (or an exclusive
file lock) and atomically replaces it. If that working memory cannot be obtained,
nothing is written and the old file stays. A truncated, corrupt or foreign file
is ignored and replaced by the session. Separate games and CPU architectures
cannot overwrite one another's observations.

Sharing keeps its own bound: a game shares at most 4,096 observations that have a
position in its ROM (the newest first); the others stay local and are never lost.
They become shared library paths once a conversion validates them.

## Next generation

The converter searches beside the selected exports, including the parent export
directory when its output argument is a report folder. **Options → each console**
also offers an additional games folder. Its subfolders are searched read-only,
without following links/junctions or traversing save-state, artwork or library
contents. The standard export location is still checked. Searches are bounded
at 50,000 directories / 16 levels; choose a more specific game folder if needed.
The setting belongs to the converter, so exports do not need the converter's
original path. Move the game's `datas` too to preserve earlier observations;
an EXE moved alone starts a new file beside itself on its next fallback session.

The converter retains imported files
in its private `datas/library` namespace, isolated by console and full identity.
The game file and private converter copy each have the size limit above (per machine).
Renaming an executable does not change its embedded identity. Neo Geo includes
the prepared cartridge and selected BIOS in its key.

**Options → console → Import fallback hints** (French: **Rapatrier les fallbacks**)
imports every saved feedback file found in that console's usual export folder
and its configured additional folder, including subfolders. No ROM selection or
recompilation is needed. The background import reports the number of games,
retained observations and bytes, and ignores corrupt/mismatched files. It merges
duplicate observations and never changes or deletes source files. Repeating an
unchanged import does not rewrite the private records.

Once import has completed, moving or deleting the source game folder, or changing
the recovery path, does not remove the converter's independent copy. On a later
generation, the exact ROM (and BIOS for Neo Geo) selects these retained candidates
and the compiler validates them again. Back up the converter's own `datas/library`
to preserve this private knowledge when moving the converter itself. Importing
alone never promotes raw candidates into the qualified shared knowledge snapshot.

| Profile | Candidates consumed on regeneration |
| --- | --- |
| Master System / Game Gear | Mapped ROM entries and four-byte guarded writable-code patterns |
| Game Boy | Verified ROM entry PC/bank pairs; other safe writable-memory misses are retained for compiler investigation |
| NES | Physical 4 KiB ROM bank/PC roots and live PC/opcode RAM guards |
| Mega Drive | Physical ROM roots, guarded 68000 RAM instructions and structural Z80 variants |
| Super Nintendo | Guarded 65816 RAM instructions and SPC700 PC/opcode variants |
| Neo Geo | Cartridge/BIOS physical roots, guarded 68000 RAM instructions and Z80 variants |
| Capcom CPS-1 | Guarded work-RAM 68000 instructions (kind 15) and sound-RAM Z80 variants (kind 16) as private build hints of this conversion only; they are not written into the library. Kind 14 (a program-ROM instruction left interpreted) is recorded and read by nobody: the ROM is swept whole, so no path can change it. Diagnostic only, never shared |
| Sharp X68000 | Interpreted instruction words (kind 13) reused as memory-word observation variants of the next discovery |
| Commodore Amiga | Windows of 16 bytes at an interpreted 68000 instruction in RAM (kind 22), as private build hints of this conversion: never written into the library, never shared. The first instruction of a window ran and counts as `native_learned`. The instructions a walk finds after it count as `native_walked`, because a walk can reach bytes the game never ran. Each keeps the same guard. The Kickstart is not recorded |

The file is a **candidate source**, not proof of correct execution. Input sizes,
checksums, identities, memory bounds and ROM signatures are checked. The current
compiler still emits the code and retains the existing live guards, fallback
counters and fresh native/reference comparisons. An unsupported instruction,
device or unstable mapping can still need a compiler/runtime correction: merely
remembering it cannot guarantee zero fallback on the next generation.

Private feedback can contain a few instruction bytes, so it must never be added
to Git or bundled into the converter. Only the existing qualified, ROM-free
numeric snapshot is eligible for sharing after qualification. Feedback alone is
not a qualification and must never bypass the reference gates.

## Developer checks

- `tools/runtime_feedback_selftest.py`: real Windows native collector; no files
  before exit, no empty folders, Unicode/renamed paths, deduplication, concurrent
  shutdowns, saturation and bounded size. A second build staged as the Mega Drive
  (record kind 5, `RR_CHECK_KIND`) checks version 2, the 65,536 bound, the refused
  count, an old version 1 file with a large call count, two simultaneous exits
  and a truncated or damaged file.
- `tools/gameplay_feedback_selftest.py`: authored ROMs; a first EXE falls back,
  the standalone EXE writes on exit, and a second generation with a fresh
  converter bank uses only that feedback and passes its reference comparisons.
- `tests/test_feedback.py`: all nine console namespaces, identity/corruption
  rejection, each compiler's candidate reader, bulk import without ROMs,
  source deletion/path changes, newest-first bounded merging, the version 1 bytes
  pinned against release 1.7.2, the per-machine bound and the refused count.

Headless conversion probes do not emit feedback by default. The developer-only
environment setting `RETRO_RECOMP_FEEDBACK=1` enables the same collector for
controlled headless checks; `0` disables it. The separate legacy Sega
`RETRO_RECOMP_LEARNING=1` diagnostic journal is still an explicit converter probe
mechanism, not the normal distributed-game recording path.

These checks distinguish native coverage and agreement with the internal
reference runtime from independent hardware fidelity, full gameplay validation
and physical audio/input latency. The feedback feature does not establish those
other measurements.
