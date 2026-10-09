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

## Workflow for future sessions

1. Read `README.md`, this guide and the local `docs/PROJECT_STATE.md` before
   continuing compiler work. Preserve the source ROMs and unrelated edits.
2. Convert the cartridges needed for the investigation, with up to eight
   simultaneous conversions when resources allow. Keep NAS sources read-only;
   all build files, observations, downloads and exports stay local.
3. Inspect new fallback sites or disagreements, fix the shared compiler/runtime
   where appropriate, and run meaningful checks for that change. Record native
   coverage, CPU agreement, hardware fidelity, gameplay and physical latency
   separately. Gameplay and listening checks belong to the user unless requested.
4. Refresh the compact snapshot from qualified local observations and successful
   conversion reports. Pass all relevant local ROM directories explicitly:

   ```powershell
   python tools/build_compilation_knowledge.py --rom-dir ROMS --reports Export/Games
   ```

   Repeat `--rom-dir` for additional local input directories. Report the compressed
   size and omitted observations. Do not copy the private library wholesale.
5. Build the converter with `tools/package.ps1`; audit the embedded snapshot and
   exact source/resources with `tools/prepare_publication.py`. Record the results
   and remaining limitations in `docs/PROJECT_STATE.md`. Publication needs an
   explicit user request.

Refresh and embed the snapshot after new qualified discoveries, so the next
converter build shares those hints. Snapshot generation includes only qualified
records whose source ROMs are available in the supplied directories. It does
not claim compatibility with every revision or every possible gameplay path.
Updating the converter does not change existing game executables; runtime
changes require regenerating the affected games.

## Reproducible cold measurements

`RETRO_RECOMP_BUNDLED_KNOWLEDGE=0` disables the shared snapshot. Selecting an
isolated library with `RETRO_RECOMP_LIBRARY_DIR` (or the legacy
`SMSRECOMP_LIBRARY_DIR`) also disables it, so a cold compilation benchmark does
not silently reuse packaged knowledge. Discovery and validation still run.
Record whether local and bundled knowledge were enabled when comparing times.
