# Adding a machine

The model for the next machines (CPS-2, PC Engine, Game Boy Advance, Atari ST, Amiga 500/1200, Nintendo 64,
PlayStation). It follows [STANDARDS.md](STANDARDS.md) ("standardize before adding a machine") and was built from two dry
runs of the same experiment: a tenth machine, an **Atari ST** (68000, disk images, TOS firmware), added on a throwaway
branch with a profile, detection of a synthetic disk, a schema 3 path section, a report written by the common builder, a
skeleton host-kit adapter, every registry, the verification tools, the translations and the documents. The first run was
on 27 October 2026 (`e4-dry-run`), before the standardization of 1.6.3; the second on 29 October 2026 (branches
`dryrun-atari-st-164` and `dryrun-atari-st-164-after`), as the acceptance test of that standardization and of the
1.6.4 fixes that followed. None is merged. The machine converts nothing, and no claim here goes beyond what those runs
and the suite measured.

## What the dry run measured

Same machine, three states of the code. Files are counted new plus modified; a place is a hunk of `git diff` in a
modified file. The stamps are the three of each of the nine existing consoles (game, host, build) and every input
fingerprinted into them, computed from the manifest before and after (`compilation_inputs.role_stamps`, `input_fingerprints`).

| Measure | 27 Oct (1.6.2 code, before the standardization) | 29 Oct, 1.6.3 as released | 29 Oct, after the 1.6.4 fixes |
|---|---|---|---|
| Files touched | 45 (6 new, 39 modified) | 41 (6 new, 35 modified) | **26 (6 new, 20 modified)** |
| Places touched | 88 | 70 | **30** |
| Converter modules modified | 11 (+3 new) | 5 (+3 new) | **3** (+3 new): `systems/registry.py`, `stamp_inputs.py`, `upstreams.py` |
| `if system == ...` branches added in the pipeline | 0 (4 small ones elsewhere) | 0 | **0** |
| Tests modified (and new) | 7 files, 15 places | 11 files, 30 places (+1 new) | **0** (+1 new, the machine's own) |
| Existing consoles whose stamps move | game: all 9; host: Mega Drive, SNES, Neo Geo, CPS-1 | game: all 9; host: 8 (all but the X68000); build: none | **none** |
| Red at the first run | 12 registries forced by a red test, 17 silent | registry test: 13 gaps; suite: 36 tests red in 13 files, nearly all literals of the nine consoles | registry test: 0 gap; suite: green with no test edited |

By kind, after the 1.6.4 fixes: converter 3 modified / 4 places (and none of them is hashed by a stamp: the registration
list, the manifest and the upstream declaration are interface modules); tools 1 / 1 (`PUBLIC_FILES`); translations 7 files / 14
places (4 keys x 8 languages); tests 0 modified; documents and `.gitignore` 9 / 11; new: the profile, the reader, the
report writer, the host-kit adapter (not compiled), the machine's page and its own test.

What the second run found, and what 1.6.4 changed:

* **Two edits to stamped files moved every console.** On 1.6.3 as released, the new CPU map went into the table `PROFILES` of
  `path_profiles.py` (one hunk, a game module owned by all) and the adapter into `hostkit.ADAPTERS` (one hunk, a host module of
  eight consoles): the nine game stamps and eight host stamps moved, the build stamps did not. Now `path_profiles.PROFILES` is
  built from each profile's `PathSpec.shapes`, `hostkit.ADAPTERS` from `host_adapter`, and the manifest of
  `stamp_inputs.py` takes the families (16-bit host, host kit, 68000) and the shared groups (`SystemProfile.stamp_groups`,
  keys `shares:<group>`) from the profiles, the machine's host adapter and profile module included. The Atari ST then edits
  no module a stamp lists; the stamps of the nine are identical with and without it, input by input.
* **That fix moves the stamps once.** `path_profiles`, `hostkit`, `systems`, `systems.specs` and the profile modules are
  edited, so every game stamp and eight host stamps changed between 1.6.3 and 1.6.4 (build stamps and the manifest, names
  and roles of the nine did not). It is acceptable in a release that reconverts anyway (1.6.4); `std_baseline` is equal
  to the one of 1.6.3 except for the values that hold a stamp.
* **The snapshot tests of 1.6.3 pinned the nine.** They compared whole tables with literals of 1.6.2, so a tenth machine
  turned about three dozen tests red. They now pin the rows of the nine consoles only (`NINE`, `only(...)`) and follow the registry for the
  rest; a machine adds no line to them. `std_baseline` photographs every registered machine from its profile.

Two costs the numbers still hide:

* **Shared code moves its machines.** Editing the machine's own conversion module moves only its own game stamp; editing
  `m68000.py` moves the five 68000 machines (Mega Drive, Neo Geo, X68000, CPS-1, Atari ST) and nobody else. A machine that
  reuses a group of another (`stamp_groups`) is moved by every edit to it: that is the point of sharing, and the reason
  the group is named by the profile.
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
`fallback_display`, `linux`, `option_keys`) and its registration in `retrorecomp/systems/registry.py` (one import and one
name in the registration list; that module is not an input of any stamp). The profile also carries what the registries
used to hold: `path_spec`, `report_shape`, `catalogues`, `library_layout`, `input_layout`, `shared_knowledge`, `host_adapter`,
`identify`, `stamp_groups` (steps 3 to 11). A firmware option is `OptionKey('<id>_<firmware>', signature=False, kind='path',
label=...)` plus a `request_identity` hook that hashes the verified firmware: a path in the request makes the signature
differ from one run to the next (`tests/test_std_baseline.py` caught it). Gate: G1.

**3. Detection and input.** `retrorecomp/<module>.py` (a reader returning an object with `sha256`, `size` or `data`). The
extensions come from `profile.extensions` (`ROM_CANDIDATE_EXTENSIONS` is derived; only a foreign format the converter does
not read goes into `FOREIGN_EXTENSIONS` of the registry). A distinctive extension needs nothing else; an ambiguous one
(`.bin`, `.rom`, `.zip`) needs `Identify(path_order=..., content_order=...)` and the hooks `identify_path` /
`identify_content`, with an order that steals no existing console (the registry refuses a clash). A machine read from
ZIPs with a cartridge extension also needs its size limit in `MAX_ARCHIVED_ROM_BYTES`. Test it with a synthetic file built
in the test (never a ROM).

**4. Paths by CPU (schema 3).** In the profile, `path_spec = PathSpec(order, sections, source_bounds, required_sources,
hashed_sources, shapes)`: the sections (CPU, map) the machine uses, the bounds of its sources, and under `shapes` the
bounds of each map it introduces (windows, alignments, lengths, caps: reuse the shapes of the CPU, add one only for a new
kind of path; a map two machines share is declared once). `path_profiles` builds `SYSTEMS`, `SYSTEM_SECTIONS`,
`PROFILES`, `SOURCE_BOUNDS`, `REQUIRED_SOURCES`, `HASHED_SOURCES` and `GAME_KEY` from it. A key that needs a consistency
check between sources, or layout fields, still needs a branch in `_validate_sources` / `_validate_layout`. Do not add the id
to `LEGACY_FIELDS` (schema 1 is closed) and leave `shared_knowledge` empty (see "Experimental, then supported"). Gate: G16 later.

**5. Recompiler and runtime.** The machine's own `<module>_conversion.py` (+ `_codegen`, `_build`), pinned engine revision, build through
`toolchain.py`. Reuse by CPU below. Declare the machine's upstream repositories (engine, reference CPU, libraries, test vectors) in `retrorecomp/upstreams.py` (`MACHINE_UPSTREAMS[<id>]`, or a reason in `NO_UPSTREAM`; an upstream another machine already uses is listed under it too) and add its rows to the two tables of [UPSTREAMS.md](UPSTREAMS.md); `tests/test_upstreams.py` fails otherwise. The module is an interface module of the stamps, so declaring moves no stamp. The counters of the interpreter fallback are per CPU and per cartridge device, in one unit
(`Cpu.unit`), never added across CPUs. Gates: G3, G4, G10.

**6. Host kit.** If the machine fits the 16-bit contract: `native/hostkit/adapters/rrhk_<id>.c` (action table, players, the
`RrhkMachine` hooks), `host_adapter = 'adapters/rrhk_<id>.c'` and `quick_state_family = 'rr16'` in the profile
(`hostkit.ADAPTERS`, the host role of the file, its place in the machine's stamps and the 16-bit family files all follow).
If it owns its loop (NES, Game Boy, X68000), call the kit's functions and declare the family. The adapter written in the dry
run is not compiled (no C toolchain on the run); compile it before relying on it. Gates: G6, G7, [HOST_KIT.md](HOST_KIT.md).

**7. Reports.** The writer ends with `report_schema.write_report(path, report)`, with `system.id`, `status` taken from the profile, the
writer's marker key and `final_checks` rows. Add the shape to `report_schema._SHAPES` (writer, marker, main and sound CPU, unit: it
must equal the profile, the registry test checks). Nothing is derived from another measure: native code, CPU fidelity, hardware
fidelity, gameplay and latency stay five objects. Gate: G2.

**8. Fingerprints.** `stamp_inputs.INPUTS`: one group for the machine's own modules, native files, licences and data (the
only edit; an unlisted file is ignored, a listed missing one is an error, and `tests/test_stamp_inputs.py` fails for a tracked
file nobody listed). Its profile module, its host adapter, the 68000 / 16-bit-host / host-kit families and the shell every
console links come from the profile. The shared groups it reuses (`megadrive_codegen`, `neogeo_codegen`, `conversion_gates`,
`megadrive_z80`, `neogeo_build`, `neogeo_native`, `md_prefetch`, `guns16`) are named in `stamp_groups`; a new file several
machines will share is a new `shares:<group>` key. `HOST_NATIVE` and `NOT_INPUTS` only for a file that is host-side or in no
stamp. Roles: host (player shell), build (toolchain), game (everything else, the safe default). Text types are listed in
`TEXT_SUFFIXES`.

**9. `release_check`.** Nothing to add: `CONSOLES` and `READERS` follow the profiles, and a writer needs no shape reader of its
own (`read_schema2_shape` reads `report_schema.read_report`). Gates G3 to G6.

**10. Campaign.** `tools/campaign.py` derives its consoles, folders, extensions, firmware options and the `--require-*` gates
from the profiles (a share that names its folders differently is told in `SHARE_FOLDERS`); a list in
`tools/campaign-risk-cases.json` is optional while the machine is experimental. `tools/std_baseline.py` and
`tools/status_lint.py` read the profiles. Gates G9, G12.

**11. Interface.** The options tab, the firmware fields and their saved paths (`paths.py`), the command-line flags
(`RetroRecomp.py`) and the preferences are generated from `option_keys` and `firmware`; the pad of the random routes from
`input_layout` (a new script format needs a writer in `random_routes.SCRIPT_WRITERS`); the box-art repository and the
catalogue tables from `catalogues`; the memory window from `library_layout` (a machine may decline the pad layout, the
artwork or the memory window with a reason in `DECLINED` of `tests/test_machine_registry.py`).

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

**15. Checks to run.** `python -B -m unittest discover -s tests -q` (about 6 minutes, 1,786 tests),
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
note in `i18n` and in the six locale files; the tab in `gui_options.py`; `status_lint`, README, COMPATIBILITY, the QUALIFICATION column,
`PUBLIC_FILES`; `release_check`, `campaign`, risk cases, `std_baseline`; `tests/test_upstreams.py` checks that the machine declares its upstreams and that each pin is on the [UPSTREAMS.md](UPSTREAMS.md) page. Registries a machine may decline (random routes, artwork,
memory view) are listed in `DECLINED` with the reason, in the same change. Only for `supported`: Linux witness, shared knowledge, four risk
cases, no failed gate. Synthetic profiles prove each gap is found.

## What stays scattered

What a new machine still edits by hand, measured on 29 October 2026 (the 30 places above), and what is left in the code that
names consoles. The first rows stay on purpose; the others have a remedy if they start to cost.

| Place | Why it stays, or the remedy |
|---|---|
| `systems/registry.py`: one import, one name (2 places) | On purpose: the explicit registration list, an interface module that no stamp hashes |
| `stamp_inputs.INPUTS`: the group of the machine's own files (1 place) | On purpose: the manifest is explicit (STANDARDS rule 5); everything the profile can state is derived |
| `upstreams.py`: the machine's upstreams or the reason it has none (1 place) | A recorded decision; it could move onto the profile |
| Translations: `options_<id>`, `options_<id>_note`, `scan_note_<id>`, one label per firmware, in eight languages (14 places) | Content; a generic scan note would save one key |
| Documents: README (tagline, badge, count, table row), COMPATIBILITY, QUALIFICATION column, SYSTEM_PROFILES, STANDARDS count, UPGRADES kit row, CONTROLS, ROADMAP (11 places in 9 files) | Prose; a count lint beside `status_lint`, and tables generated from the profiles, would remove most |
| `PUBLIC_FILES` of `tools/prepare_publication.py` and the `.gitignore` whitelist of the machine's page | On purpose: the public file list is explicit; a `docs/*.md` pattern would make it implicit |
| `path_profiles._validate_sources`, `_validate_layout` (`ng`, `cps1`, `x68` branches) | Only for a machine whose key needs a cross-check or layout fields; a validator on `PathSpec` would remove them |
| `path_profiles.LEGACY_FIELDS`, `knowledge_build.engines()` | Schema 1 is closed; the engine revision matters only for a shared (supported) machine of the site's base |
| `systems.MAX_ARCHIVED_ROM_BYTES`, `random_routes.SCRIPT_WRITERS`, `campaign.SHARE_FOLDERS` | Only for a machine read from a ZIP with a cartridge extension, a new script format, or a share that names its folder differently |
| About eighty `system == ...` branches for the nine machines' own behaviour (`knowledge*`, `build_cleanup`, `memory_view`, the exchange, `scan_levels`, `core`, `gui_queue`...) | Not touched by a registration and not measured by the dry run; a machine meets them when it becomes supported (shared knowledge, library layout, build cleanup): remedies `library_layout`, `build_layout`, `scan_options` on the profile |

Removed since 27 October (1.6.3 and 1.6.4): the detection chain and the extension tables, the path tables and the map
shapes, the shared-knowledge lists, the report shapes and writer branches, the two copies of the stamp ownership, the host-kit
adapter list, the random-route pad tables, the firmware lists of the command line, the preferences and the window, the
generic options tab, the verification tools' console lists and gates, the catalogue tables, the report `status` literal, and
the tests that pinned the list of nine.
