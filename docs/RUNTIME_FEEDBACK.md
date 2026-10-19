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
There are at most **4,096 observations per exact game identity**, across all
sessions: **131,168 bytes (128.094 KiB)** per file. Examples:

| Distinct observations | File size |
| --- | ---: |
| 0 | No file |
| 4 | 224 bytes |
| 100 | 3,296 bytes |
| 1,000 | 32,096 bytes |
| 4,096 | 131,168 bytes |

The same PC/CPU/guard bytes are stored only once. Reset and F9 do not erase the
session buffer, and no player save-state payload includes that host buffer.
Repeated sessions do not grow the file beyond the limit. At saturation, newer
session candidates take priority; the header reports truncation.

The recorder reserves 144 KiB of host data, with no allocation, file access or
locking on the instruction capture path. Shutdown alone reads/merges the old
file, takes a bounded Windows mutex and atomically replaces it. Separate games
and CPU architectures cannot overwrite one another's observations.

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
The game file and private converter copy each have the size limit above.
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
  shutdowns, saturation and bounded size.
- `tools/gameplay_feedback_selftest.py`: authored ROMs; a first EXE falls back,
  the standalone EXE writes on exit, and a second generation with a fresh
  converter bank uses only that feedback and passes its reference comparisons.
- `tests/test_feedback.py`: all seven console namespaces, identity/corruption
  rejection, each compiler's candidate reader, bulk import without ROMs,
  source deletion/path changes and newest-first bounded merging.

Headless conversion probes do not emit feedback by default. The developer-only
environment setting `RETRO_RECOMP_FEEDBACK=1` enables the same collector for
controlled headless checks; `0` disables it. The separate legacy Sega
`RETRO_RECOMP_LEARNING=1` diagnostic journal is still an explicit converter probe
mechanism, not the normal distributed-game recording path.

These checks distinguish native coverage and agreement with the internal
reference runtime from independent hardware fidelity, full gameplay validation
and physical audio/input latency. The feedback feature does not establish those
other measurements.
