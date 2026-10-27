# Adding a machine

The model for the next machines (CPS-2, PC Engine, Game Boy Advance, Atari ST, Amiga 500/1200, Nintendo 64,
PlayStation). It follows [STANDARDS.md](STANDARDS.md) ("standardize before adding a machine") and was built from a
dry run: on 27 October 2026 a tenth machine, an **Atari ST** (68000, disk images, TOS firmware), was added on a throwaway
branch (`e4-dry-run`, never merged) with a profile, detection of a synthetic disk, a schema 3 path section, a report
written by the common builder, a skeleton host-kit adapter, every registry, the verification tools, the translations and
the documents. It converts nothing, and no claim here goes beyond what that run and the suite measured.

## What the dry run measured

| Measure | Before the standardization (inventory of 27 Oct, Appendix A) | After (dry run, Atari ST) |
|---|---|---|
| Files touched | 32 (20 converter modules, 1 tool, 2 tests, 8 documents, the new profile) | **45**: 6 new, 39 modified |
| Places touched | about 45 listed ranges, plus about 45 branches in `knowledge*.py` | **88** (hunks in modified files) |
| Of which converter modules | 20 (`core`, `scan_levels`, `feedback`, `metadata`, `platforms`, `batch`, `freshness`, `knowledge*`, `online`, `library`, `build_cleanup`...) | **11** modified (+3 new) |
| `if system == ...` branches added in the conversion pipeline | many (`batch`, `freshness`, `scan_levels`, `knowledge*`...) | **0**: profiles drive them (4 small ones remain in `random_routes`, the campaign tool and the ownership rules) |
| Registries (lists keyed by console) edited | not counted | **29**: 12 forced by a red test, 17 silent |

By kind, after: converter 11 modified / 34 places; tools 6 / 15; translations 6 files / 12 places (4 keys x 8 languages);
tests that pin the console list 7 / 15; documents and `.gitignore` 9 / 12; native 1 new file. Reading it honestly: the
branches of the pipeline are gone (scan levels, feedback, metadata, Linux witness, request identity, batch options
now come from the profile), but the standardization created registries of its own (stamp manifest, CPU path
profiles, report shapes, host kit) and the verification tools, the interface and the translations list consoles too.
The total is not smaller; it is **checkable**: `tests/test_machine_registry.py` finds 15 of the 17 silent ones and
names them (the two it cannot see are the ZIP size limit and the `.gitignore` whitelist of the machine's page, step 1 and 3).
The places that could come from the profile are in the table at the end ("What stays scattered").

Two costs the numbers hide:

* **A new machine moves the game stamp of every existing machine.** `retrorecomp.systems`, `path_profiles`, `paths` and
  `random_routes` are game modules owned by all consoles; registering a machine edits them, so the nine game stamps
  moved, and the host stamp of Mega Drive, Super Nintendo, Neo Geo and CPS-1 too (`hostkit.py`). Ship a new machine in a
  release that already breaks stamps, or declare the old stamps upgradable after an A/B proof
  (`LEGACY_GAME_STAMPS`, [UPGRADES.md](UPGRADES.md)). Measured the other way: editing the machine's own conversion module
  moves only its own game stamp; editing `m68000.py` moves the five 68000 machines (Mega Drive, Neo Geo, X68000, CPS-1,
  Atari ST) and nobody else.
* **Why the Atari ST.** It exercises the most existing paths: the 68000 generator and path profile (`m68k`), disk media and
  a user firmware like the X68000, the shared 16-bit host family, schema 3 sources `tos` and `disk`, an experimental start.
  A PC Engine (HuC6280, a 6502 derivative) would exercise fewer: it needs a new CPU entry everywhere (see "Reuse by CPU").

## Experimental, then supported

A machine enters as `experimental` and may stay incomplete for a long time (CPS-1 has work left, the X68000 much more).
The profile's `status` says so; nothing else may contradict it (`tools/status_lint.py`).

| | Experimental (minimum to add it) | Supported |
|---|---|---|
| Profile, detection, reader | yes | yes |
| Paths section, report through `write_report` | yes | yes |
| Stamps, host adapter or declared own shell | yes | yes |
| Interface tab, scan note, 8 languages, README and COMPATIBILITY rows | yes | yes |
| `release_check` reader, campaign folder and extensions, risk-case list | yes (the list may be empty) | at least 6 cases in 5 categories |
| QUALIFICATION column | yes, mostly `?` | no `N`; G1, G2, G4 at least `P` |
| Linux witness (`linux = 'witnessed'`) | no (`pending`) | yes |
| Shared knowledge (`SHARED_SYSTEMS`) | no | yes (G16) |
| Native coverage, packed replay, fresh-process states, panel, owner acceptance | reported when measured, `?` otherwise | the 13 gates of [STANDARDS.md](STANDARDS.md#supported-checklist) |

`tests/test_machine_registry.py` checks the left column for every machine and the right column only for `supported` ones.

**How an experimental machine is flagged.** Reports carry `system.status` (the writer's string; `read_report` copies it
and the window shows "Created · experimental" from it), and the five measures stay separate and unclaimed by default
(`hardware_fidelity`, `gameplay`, `latency` read "not reported" or "not validated"). The interface says it in the options
tab note; the README, COMPATIBILITY and the interface strings are linted against the profile. Exports carry no
"experimental" mark of their own. The dry run found the status read from the profile by `status_lint`, the registry
test and the Neo Geo and CPS-1 report writers (`EXPERIMENTAL_PROFILES` exists but nothing in production uses it); everything
else is a literal: the X68000 writer and the Atari ST writer, the options notes in eight languages, the prose.

**What `release_check` and the campaign expect.** Today they do not read the status: every console is checked the same
way, `--require-packed` and `--require-states` come from two lists in `tools/campaign.py` (`REQUIRE_PACKED`, `REQUIRE_STATES`),
and a console with no ROM folder makes `campaign.py select` exit 2. The convention to apply until that is data: for an
experimental machine run the campaign with `--consoles <id>` and read the verdicts and the five measures as information;
for a supported one every gate of `release_check.py` must pass at the release level (fallback limit 0 or listed per
cartridge, native/reference agreement, packed replay and fresh-process states where the report carries them).

**Progress to `supported`** is the checklist of [STANDARDS.md](STANDARDS.md#supported-checklist), recorded gate by gate in
[QUALIFICATION.md](QUALIFICATION.md): G1 `tools/status_lint.py`; G2 `report_schema` and `tests/test_report_schema.py`;
G3/G4 the `native_reference` and `fallback` gates of `release_check.py`; G5/G6 `--require-packed`, `--require-states`;
G7 save tests; G8/G9 `random_routes` levels *extended* and *thorough*; G10 CPU vectors or an independent model
(`tools/*_selftest.py`); G11 hardware fixtures or an external emulator; G12 `campaign.py select` panels; G13 the Linux
host; G14 the owner's play test, written in the QUALIFICATION table; G15 `status_lint` and the report
claims; G16 numeric paths, rechecked, retried without hints. Then set `status = 'supported'`, `linux = 'witnessed'`, add the id
to `path_profiles.SHARED_SYSTEMS`, and change every prose sentence (`status_lint` lists the contradictions).

**An engine that changes often.** Four mechanisms keep this safe:

1. *Exports.* The game stamp hashes the machine's own modules and native files by bytecode: a change in the machine's engine
   moves only its stamp, so the old exports are reconverted or rediscovered, and nothing is claimed upgradable. Do not
   add `LEGACY_GAME_STAMPS` entries for an experimental machine; list its own files under its own owner group and its licences
   there too (`licenses/cps1-*.md`). A shared module (`m68000.py`, the kit) moves every machine that owns it.
2. *Stamps.* The manifest (`stamp_inputs.INPUTS`) is explicit: an unlisted file is ignored, a listed missing one is an error, so
   a work-in-progress file never moves a stamp by accident, and `tests/test_stamp_inputs.py` fails for a tracked file nobody
   listed.
3. *Shared paths.* A qualified path is qualified for one engine revision (the `core` field of its schema 3 section, the
   engine of its record). When the engine changes the paths return to *pending*: still used as hints, always rechecked
   against the reference, set aside when a conversion fails with them. An experimental machine therefore never presents a
   stale path as qualified.
4. *The switch.* Keep an experimental machine out of `path_profiles.SHARED_SYSTEMS` (and `knowledge_build.SYSTEMS`) until its
   engine is stable; to retire one, remove the id from those lists: the exchange, the service client and the key patterns
   follow (`test_the_sharing_lists_and_key_patterns_follow_one_list`): uploads and imports of that machine are refused, files already
   on disk are not touched. This is a code switch for the maintainer today, not a per-machine option for the player.

## The steps

Do them in this order; the registry test tells you which one you missed. "Reuse" refers to the table after the steps.

**1. Scope and files.** A document `docs/<MACHINE>.md` stating what is converted, what is not, and the five measures kept
apart. It must be whitelisted twice: `!docs/<MACHINE>.md` in `.gitignore` (`docs/*` is ignored by default: the file is
silently untracked otherwise) and `tools/prepare_publication.py` `PUBLIC_FILES`, which also lists every new module, native
file, test and tool.

**2. Profile.** `retrorecomp/systems/<module>.py` (a `SystemProfile` v2: `id`, `name`, `extensions`, `export_folder`,
`video_modes`, `status='experimental'`, `cpus` with their unit, `media_kinds`, `firmware`, `quick_state_family`,
`capabilities`, `feedback_kinds` (a new number: the record kind is one byte), `default_frames`, `quick_frames`,
`fallback_display`, `linux`, `option_keys`) and its registration in `retrorecomp/systems/__init__.py` (import, `ALL_PROFILES`,
`PROFILES`). A firmware option is `OptionKey('<id>_<firmware>', signature=False)` plus a `request_identity` hook that hashes the
verified firmware: a path in the request makes the signature differ from one run to the next
(`tests/test_std_baseline.py` caught it). Gate: G1.

**3. Detection and input.** `retrorecomp/<module>.py` (a reader returning an object with `sha256`, `size` or `data`). A
distinctive extension needs only `ROM_CANDIDATE_EXTENSIONS` (and `MAX_ARCHIVED_ROM_BYTES` for ZIPs) in `systems/__init__.py`;
an ambiguous one (`.bin`, `.rom`, `.zip`) needs a branch in `profile_for_path` before the extension table, ordered so that no
existing console is stolen. Test it with a synthetic file built in the test (never a ROM).

**4. Paths by CPU (schema 3).** In `retrorecomp/path_profiles.py`: the id in `SYSTEMS`, a `PROFILES[(cpu, map)]` entry (windows,
alignments, lengths, caps: reuse the shapes of the CPU, add one only for a new kind of path), `SYSTEM_SECTIONS`, `SOURCE_BOUNDS` (and
`REQUIRED_SOURCES`, `HASHED_SOURCES`, a `_validate_layout` branch when the key needs more than one source). Do not add the id to
`LEGACY_FIELDS` (schema 1 is closed) or to `SHARED_SYSTEMS` (see "Experimental, then supported"). Gate: G16 later.

**5. Recompiler and runtime.** The machine's own `<module>_conversion.py` (+ `_codegen`, `_build`), pinned engine revision, build through
`toolchain.py`. Reuse by CPU below. The counters of the interpreter fallback are per CPU and per cartridge device, in one unit
(`Cpu.unit`), never added across CPUs. Gates: G3, G4, G10.

**6. Host kit.** If the machine fits the 16-bit contract: `native/hostkit/adapters/rrhk_<id>.c` (action table, players, the
`RrhkMachine` hooks), `hostkit.ADAPTERS`, `quick_state_family = 'rr16'`, the file listed in `stamp_inputs` (host role). If it owns its
loop (NES, Game Boy, X68000), call the kit's functions and declare the family. The adapter written in the dry run is not compiled
(no C toolchain on the run); compile it before relying on it. Gates: G6, G7, [HOST_KIT.md](HOST_KIT.md).

**7. Reports.** The writer ends with `report_schema.write_report(path, report)`, with `system.id`, `status` taken from the profile, the
writer's marker key and `final_checks` rows. Add the shape to `report_schema._SHAPES` (writer, marker, main and sound CPU, unit: it
must equal the profile, the registry test checks). Nothing is derived from another measure: native code, CPU fidelity, hardware
fidelity, gameplay and latency stay five objects. Gate: G2.

**8. Fingerprints.** `stamp_inputs.INPUTS`: a group for the machine's modules, native files, licences and data; the shared groups of its
CPU re-keyed to include it (`m68000`, the codegen modules, the kit); `HOST_NATIVE` for host files; `NOT_INPUTS` for files in no stamp;
`compilation_inputs.owners()` still holds a second copy of the ownership by file-name prefix (add the prefix: a test compares both).
Roles: host (player shell), build (toolchain), game (everything else, the safe default). Text types are listed in `TEXT_SUFFIXES`.

**9. `release_check`.** `CONSOLES` and `READERS` in `tools/release_check.py`. A new writer needs no shape reader of its own: use
`read_schema2_shape` (reads `report_schema.read_report`), which the dry run added. Gates G3 to G6.

**10. Campaign.** `tools/campaign.py` (`DEFAULT_FOLDERS`, `EXTENSIONS`, `console_options`, the two argparse blocks for a firmware option,
the title regex) and a list in `tools/campaign-risk-cases.json` (empty is allowed while experimental). `tools/std_baseline.py`
(`SYSTEMS`, `CONSOLE_OPTIONS`) and `tools/status_lint.py` (`CONSOLES`, `ALIASES`). Gates G9, G12.

**11. Interface.** `retrorecomp/gui.py`: an options tab (`build_scan_options`, the firmware field and its `StringVar`, the preferences
dict); `retrorecomp/paths.py` firmware preference list; `RetroRecomp.py` (`--<id>-<firmware>` and its two `convert_batch` keywords);
`random_routes.CONSOLES` (pad layout, bits, script writer, file suffix) unless declined with a reason in the registry test;
`artwork.REPOSITORIES` and `memory_view.summaries` likewise.

**12. Translations.** Keys `options_<id>` (the first three consoles kept `options_master_system`, `options_game_gear`, `options_game_boy`),
`options_<id>_note`, `scan_note_<id>`, one label per firmware: in `retrorecomp/i18n.py` (EN, FR) and the six files of `assets/locales/`
(it, es, de, ja, ru, zh); `tests/test_languages.py` requires every key in every language and every character of the Chinese, Japanese and
Russian text to be in `assets/font-coverage.json` (a new character means rebuilding the font subsets with fontTools; the dry run
reworded instead). The games themselves speak five languages ([LANGUAGES.md](LANGUAGES.md)).

**13. Documents.** README (tagline, badge, "Console support" row, count), COMPATIBILITY, SYSTEM_PROFILES, STANDARDS (count), UPGRADES (kit row), CONTROLS,
ROADMAP, QUALIFICATION (a column, `?` for what is not measured), the machine's own page. Prose that counts consoles ("nine") is
hand-written in about ten places.

**14. Licences and credits.** `licenses/<engine>.md` listed under the machine's own owner group (a licence listed for all consoles moves every
host stamp; `THIRD_PARTY_NOTICES.md` does), the permissive engine preferred (MIT/BSD, as `ymfm` for CPS-1), the credits "Made by Retro-Recomp" line
in eight languages only for a major piece of our own work (STANDARDS rule 13). Rule 10: shared code is MIT.

**15. Checks to run.** `python -B -m unittest discover -s tests -q` (about 6.5 minutes, 1,535 tests),
`python -B tools/prepare_publication.py --tracked`, `python -B tools/status_lint.py`, then the machine's own tests: the shared kinds (fresh-process
states, saves, packed replay, languages, headless routes) plus its own.

## Reuse by CPU

| CPU | Machines today | Reuse | New for a machine on this CPU |
|---|---|---|---|
| 68000 | Mega Drive, Neo Geo, X68000, CPS-1 | `m68000.py`, `megadrive_codegen.py`, `neogeo_codegen.py`, `native/m68000_backend.*`, path profile `m68k` shapes `insn`/`span`, SingleStepTests vectors | memory map, bus, path map name (`m68k/<id>`), sources |
| Z80 | Master System, Game Gear, Mega Drive sound, Neo Geo sound, CPS-1 sound | `cpu.py`/`core.py`, `megadrive_z80.py`, `neogeo_z80.py`, `cps1_z80`, path profiles `z80/*`, SingleStepTests vectors | bus and ports, path map |
| 6502 | NES | `nes_codegen.py`, `nes_runtime.py`, path profile `mos6502` | a 65C02/HuC6280 variant (PC Engine): new opcodes and banking, new CPU entry |
| SM83 | Game Boy | `gameboy_*.py`, path profile `sm83` | none for another SM83 machine |
| 65816 and SPC700 | Super Nintendo | `snes_codegen.py`, `snes_spc.py`, path profiles `w65c816`, `spc700` | cartridge devices as `DEVICES` entries |
| ARM7TDMI, MIPS R3000A/VR4300, 68020 | none | nothing | a recompiler, a CPU vector set, a path profile and shapes, a report CPU entry |

CPS-2 reuses the CPS-1 modules (68000, Z80, romset reader, kit adapter) and adds the QSound device as a cartridge-device entry; the
Amiga 500 and Atari ST reuse the 68000 chain; the Amiga 1200, Game Boy Advance, Nintendo 64 and PlayStation start with a new CPU.

## What the registry test checks

`tests/test_machine_registry.py` runs `registry_problems(profile)` on every profile and returns sentences. For every machine:
status and CPU declarations; `ROM_CANDIDATE_EXTENSIONS`; the derived lists (`scan_levels`, `feedback`, `compilation_inputs`); `path_profiles`
(`SYSTEMS`, `SYSTEM_SECTIONS`, `PROFILES`, `SOURCE_BOUNDS`); `report_schema._SHAPES` equal to the profile's CPUs; the stamp manifest (profile
module listed, stamps computable, kit adapter for `rr16`); the firmware options in the command line, preferences and window; the tab and scan
note in `i18n` and in the six locale files; the tab in `gui.py`; `status_lint`, README, COMPATIBILITY, the QUALIFICATION column,
`PUBLIC_FILES`; `release_check`, `campaign`, risk cases, `std_baseline`. Registries a machine may decline (random routes, artwork,
memory view) are listed in `DECLINED` with the reason, in the same change. Only for `supported`: Linux witness, shared knowledge, four risk
cases, no failed gate. Synthetic profiles prove each gap is found.

## What stays scattered

Hard-coded lists or `if system == ...` the dry run met that should come from the profile. Production code was not refactored;
this is the list of follow-ups.

| Place | Remedy |
|---|---|
| `systems.ROM_CANDIDATE_EXTENSIONS`, `MAX_ARCHIVED_ROM_BYTES`, the detection chain of `profile_for_path` | derive from `profile.extensions`; a profile hook `identify(path, data)` with an order |
| `path_profiles.SYSTEMS`, `SYSTEM_SECTIONS`, `SOURCE_BOUNDS`, `REQUIRED_SOURCES`, `HASHED_SOURCES`, `_validate_layout`, the `ng` branches | a per-machine path spec attached to the profile (`path_sections`, `sources`, `layout`) |
| `SHARED_SYSTEMS`, `knowledge_build.SYSTEMS`, `knowledge_build.engines()`, `LEGACY_FIELDS` | profile `shared_knowledge` (the switch) and an `engine_revision()` hook |
| `report_schema._SHAPES` (a copy of the CPUs) and the writer-name branches of `_main_scenario`, `_scan`, `_cpu_scenarios` | derive archs and units from the profile; per-writer adapters, or writers that emit schema 2 natively |
| `compilation_inputs.owners()` and `stamp_inputs.INPUTS` (two copies of ownership); shared groups re-keyed by hand | keep the manifest only; a CPU-family table built from `profile.cpus` |
| `systems`, `path_profiles`, `paths`, `random_routes` are game modules owned by all: a new machine moves nine game stamps | registration data in an interface module; per-machine path tables in their own modules |
| `hostkit.ADAPTERS`, `HOST_NATIVE`, the kit entry in `INPUTS` (and `hostkit.py` is a host input of four consoles) | profile `host_adapter`; derive the other two |
| `random_routes.CONSOLES`, `*_BITS`, `script_text`, `write_route` suffix (seven script formats) | profile `input_layout` and `route_writer`; the kit's one input-script format |
| `paths.py` firmware tuple, `gui.py` firmware variables, `RetroRecomp.py` flags and keywords, `tools/campaign.py` flags | generate from `option_keys` and `firmware` (`OptionKey` gets a kind and a label) |
| `gui.py` options tabs (one hand-written block per console), `scan_note_<id>`, `options_<id>`, the legacy tab keys | a generic tab from the profile; a string prefix on the profile |
| `status_lint.CONSOLES/ALIASES`, `std_baseline.SYSTEMS/CONSOLE_OPTIONS`, `release_check.CONSOLES/READERS`, `campaign.DEFAULT_FOLDERS/EXTENSIONS` | derive from `ALL_PROFILES`; one reader (`read_report`) instead of eight shape readers |
| `campaign.REQUIRE_PACKED/REQUIRE_STATES`, risk-case minimum, `select` exiting 2 without a folder | gates from `profile.status`; experimental machines opt in with `--consoles` |
| `artwork.REPOSITORIES`, `cover_sources.SS_SYSTEMS/TGDB_SYSTEMS/IGDB_SLUGS`, `cover_references.SYSTEMS`, `game_metadata.PLATFORMS` | a `catalogues` mapping on the profile; a missing entry must be a decision, not a `KeyError` |
| `memory_view` patterns, `build_cleanup` layout rules, `compiled_games.ADVANCED_SCAN_SYSTEMS`, `compiled_games_view.SHARED_CONSOLES` | profile `library_layout`, `build_layout`, `scan_options` |
| The report's `status` literal in each writer; the queue's "Created · experimental" keyed on that string | `write_report` fills `system.status` from the profile; a per-cartridge downgrade stays an explicit override |
| Tests that pin the nine ids (`test_system_profiles`, `test_stamp_inputs`, `test_compilation_inputs`, `test_std_baseline`, `test_paths_schema`, `test_campaign`, `test_gui_state`) | iterate `system_ids()`; risk-case minimum only for supported machines |
| Prose counts ("nine", "seven") and the `.gitignore` documents whitelist | a count lint beside `status_lint`; a `docs/*.md` pattern |
