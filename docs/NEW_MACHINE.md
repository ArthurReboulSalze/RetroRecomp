# Adding a machine

The playbook that takes a machine from its study to the release that ships it: one ordered path, each step with its
checklist, the evidence it must leave and the gate that closes it. The lead session (the one that merges) drives it with a
specialist per machine; the maintainer tests (G14), decides the exit from the experimental status and gives the publication
go, and decides a route only when it mixes licences. Anyone on the path stops and asks him when a step meets an unknown, a
fundamental question or a blocker ([Stop and ask the maintainer](#stop-and-ask-the-maintainer)). The second half of the page is reference: the registration steps that
step 1 points to, reuse by CPU, what the registry test checks, what stays scattered, and the dry run that measured them.

The rules behind every step are in [STANDARDS.md](STANDARDS.md) and [AGENTS_GUIDE.md](AGENTS_GUIDE.md): no ROM in the
repository, a declared role for every file, explicit public files, the five measures kept apart (native code, CPU fidelity,
hardware fidelity, gameplay validation, physical latency), the interpreter fallback always counted, and no push or release
without the maintainer's word.

## The path at a glance

| Step | Ends with | Gate to go on | Decided by |
|---|---|---|---|
| [0. Study](#step-0-study) | a written study, a route, a panel of 7-8 games | the route needs no licence mix, or the maintainer chose it | the lead; the maintainer for a GPL or noncommercial mix |
| [1. Experimental profile](#step-1-experimental-profile-and-registries) | the machine in every registry, one game converted | registry test and suite green, no other machine's stamp moved by accident | the lead |
| [2. Qualification](#step-2-qualification-g1-to-g16) | G1-G16 proved in [QUALIFICATION.md](QUALIFICATION.md) | every gate proved, none relaxed; G14 and the exit | the maintainer (G14 and the exit) |
| [3. Multiplayer](#step-3-multiplayer) | the machine offered in a room, proved on two copies then two PCs | the proofs recorded, the profile fields set | the lead |
| [4. Optimisation](#step-4-optimisation-pass) | the frame cost cut with identical output | no regression, identical output proven, risky items listed | the lead; risky items the maintainer |
| [5. Sharing paths](#step-5-sharing-paths-only-if-useful) | sharing, or a recorded decline | G16 `Y`, or `-` with its evidence | the maintainer when the gain is small |
| [6. Release kit](#step-6-release-kit) | notes, « What's new », credits, tables, stamps | every check green | the maintainer's publication go |

[Step 7](#step-7-who-does-what) says who does what, and the [progress board](#progress-board) follows each machine through
the steps. Multiplayer and optimisation never change what a game does alone: each change shows identical output first, or the
evidence of step 2 that it touches is taken again.

## Stop and ask the maintainer

The path runs with little help, but not at any cost. At every step, stop and ask instead of pushing on when one of these
comes up:

- **An unknown or a possible problem**: something the study did not foresee, a behaviour nobody can explain yet, a risk to
  the player's files, the exports or another machine.
- **A fundamental question**: the scope, the design, a licence, a result that contradicts the plan, a gate that cannot be met
  as it is written.
- **Being stuck.** The stop rule: two approaches that failed on the same blocker, or about three hours of work on it with no
  step forward, whichever comes first.

The report says what blocks, what was tried and what it showed, and the options with a recommendation. A specialist sends it
to the lead, and the lead takes it to the maintainer. Then wait: nobody works around the blocker alone, relaxes a gate to get
past it, or starts a different route without his answer. Other work that does not depend on it may go on.

## Step 0: study

Nothing in `retrorecomp/` or `native/` yet: the study is a report, kept with the specialist's local notes, and a short summary
for the maintainer.

Checklist:

- **Scope.** The media and models converted first (cartridges before disks, one model before its successors), and what is
  left out, each with its weight in a real library and the reason. The hardware to model, chip by chip.
- **Upstreams.** First a static recompiler that can be pinned (mstan's and RetroPortingToolKit's repositories first, then
  the community's), else an emulator core to build on, else our own. For each candidate: the repository, its last activity,
  its exact licence (file and line), what we would compile from it. Repositories are cloned read-only under `.build/` to read;
  nothing downloaded is built or run during the study.
- **Licence route.** GPL code is allowed in an export (ScummVM, the Atari ST's Hatari), but never GPL together with a
  noncommercial licence (PolyForm Noncommercial and the like) in one executable. Prefer MIT, BSD and zlib parts (as `ymfm`
  for the CPS boards), and a route that needs nobody's permission. Shared code stays MIT (STANDARDS rule 10); the
  licence rules of [UPSTREAMS.md](UPSTREAMS.md#licence-rule) apply to every fix taken from an upstream. When the chosen route
  mixes GPL or noncommercial code, the maintainer decides; otherwise the lead does. An upstream's own network layer, launcher
  or mod loader is not used: the session is ours. Media that would need a protection circumvented (signed or encrypted
  downloads) is refused.
- **CPU reuse.** Fill the machine's line of [Reuse by CPU](#reuse-by-cpu): what exists, what is new. A CPU new to the
  project needs an independent vector set or model (G10), a path profile with its shapes, and a report CPU entry. When no
  per-instruction vectors exist for it, say now what G10 will rest on (test programs, a second model).
- **Firmware.** Is a BIOS, TOS, Kickstart or IPL needed? The rule of every machine: the player's own file, checked by its
  hash, never shipped; a free replacement by default when enough games run on it (C-BIOS for the MSX cartridges, EmuTOS for
  the Atari ST), with what it cannot run stated.
- **Panel.** 7-8 games at most, each with its reason: one hardware case each (a mapper, a sound chip, a save type, a video
  mode, a protection, a peripheral), plus one or two in reserve. One of them is named the first game, used for every example
  and first read. Larger panels only in the maintainer's own campaigns.
- **Multiplayer preview.** The ports and players the machine had (multitaps, four-player boards), a link cable, and whether
  its whole state can be saved and loaded in memory cheaply (rollback) or not (delay).
- **Plan.** The stages to step 6 with an estimate in AI wall-clock time and its bottleneck, the risks, and the maintainer's
  decision if a licence mix is in it.

Evidence: the study report and its summary, numbers about the games only (sizes, counts, hashes), never ROM bytes.
Gate: a route without a licence mix, or the maintainer's written choice of one.

## Step 1: experimental profile and registries

The machine enters as `experimental` ([Experimental, then supported](#experimental-then-supported)), on the specialist's branch,
in stages that each end in a commit:

1. A profile with `developer_only = True` (offered only where the machine's files are installed), its reader, report
   skeleton, path section, upstreams and stamp entries: it identifies files and converts nothing.
2. The conversion loop on the pinned engine: our patches are anchored edits of a staged copy (the strict `replace_once`
   helpers of [UPSTREAMS.md](UPSTREAMS.md#decision-rule)), never a fork.
3. The exported game and its host-kit adapter; the first game plays.
4. Independent evidence in the repository: CPU vectors, small authored hardware programs.
5. A first panel and the Linux witness, then the machine opens to players as experimental: `developer_only` off, the options
   and scan notes in eight languages, the README and COMPATIBILITY rows, the credits line if it is a major piece.

The registration steps below have the detail; this is the list a reviewer ticks before the merge.

- [ ] Page `docs/<MACHINE>.md` (scope, what is not converted, the five measures apart), whitelisted in `.gitignore` and in
  `PUBLIC_FILES` of `tools/prepare_publication.py`, with every new module, native file, test and tool (registration 1).
- [ ] Profile `retrorecomp/systems/<module>.py` with `status = 'experimental'`, `linux = 'pending'`, registered in
  `systems/registry.py` (registration 2).
- [ ] Each firmware option with its line in `RECOGNISERS` of `retrorecomp/firmware_search.py` in the same change, so that
  Options' « Find firmware in a folder… » looks for it (registration 2).
- [ ] Detection tested on a synthetic file built by the test, stealing no other machine's files (registration 3).
- [ ] `path_spec` with its shapes; the machine kept out of `path_profiles.SHARED_SYSTEMS` (registration 4).
- [ ] Upstreams declared in `retrorecomp/upstreams.py` and in both tables of [UPSTREAMS.md](UPSTREAMS.md); `python -B
  tools/check_upstreams.py` shows each pin (registration 5).
- [ ] Host adapter on the kit, or its own loop calling the kit, with its quick-state family (registration 6).
- [ ] Report through `report_schema.write_report`, its shape in `_SHAPES`; the fallback counted per CPU and per device, in
  one unit, never added across CPUs (registration 7).
- [ ] Its own group in `stamp_inputs.INPUTS`, the shared groups it reuses in `stamp_groups` (registration 8). Measure the
  stamps of every other machine before and after (`compilation_inputs.role_stamps`): they must not move, or the move is
  declared in [UPGRADES.md](UPGRADES.md).
- [ ] Licence pages in `licenses/`, declared in the profile's `notice_files`, a row in `THIRD_PARTY_NOTICES.md`, the
  upstream's notice in `tests/test_game_notices.py` (registration 14).
- [ ] The converter's strings in eight languages, every Chinese, Japanese and Russian character in
  `assets/font-coverage.json` (reword rather than add one); the game's own menus in the five Latin-script languages only
  (registration 12, [LANGUAGES.md](LANGUAGES.md)).
- [ ] Documents: README's « In development » row, COMPATIBILITY, a QUALIFICATION column of `?` and its page row,
  SYSTEM_PROFILES, CONTROLS, ROADMAP, the machine counts of README, STANDARDS and AGENTS_GUIDE (registration 13).
- [ ] A registry the machine declines (random routes, artwork, memory view) in `DECLINED` of `tests/test_machine_registry.py`
  with its reason, in the same change.
- [ ] **A value that differs per machine goes on its profile**, never into a shared table (a ZIP size limit added to a shared
  table once moved every game stamp; it is now `archived_rom_limits` on the profile). The one-byte feedback kind and the
  `PathSpec` order are new numbers, reserved for the machine.
- [ ] **An audit of every list** the machine touches, beyond the registry test: the build cleanup, the credits grouping, the
  firmware messages in eight languages, the firmware flags of `campaign.py` and `ab_conversion.py` with their help text.
- [ ] **Builds that travel**: text scripts in LF, a Linux link that groups its archives (GNU ld), resources written only when
  their bytes change, a deep installation folder that keeps paths under the Windows limit, two first conversions on a fresh
  toolchain folder that share one setup instead of cloning the engine twice.

Evidence: `tests/test_machine_registry.py` with no gap, the full suite green, `python -B tools/prepare_publication.py
--tracked` and `python -B tools/status_lint.py` clean, and the first game converted from an empty library with its
fallback counted in the report.
Gate: those checks, on the branch and again on main after the merge (a suite run in a worktree skips the tests that need
the main checkout's toolchain folder: read its real exit code on main).

## Step 2: qualification, G1 to G16

The gates are the "supported" checklist of [STANDARDS.md](STANDARDS.md#supported-checklist), recorded letter by letter in the
matrix of [QUALIFICATION.md](QUALIFICATION.md) (`Y`, `P`, `N`, `?`, `-`), each with its evidence section. A gate is proved on
the machine's own panel, converted from an empty library.

| Gate | What it needs in practice | What to reuse |
|---|---|---|
| G1 Status | profile, README, documents, notes and interface say the same | `tools/status_lint.py` |
| G2 Report | report v2, main, sound and device counters apart | `report_schema.write_report`, `tests/test_report_schema.py` |
| G3 Native code | 0 interpreted main and sound instructions on every final scenario, or each one listed with its count; devices apart | the machine's counters; `release_check.py` fallback gate |
| G4 CPU check | a fresh reference run equals the native run (CPU, RAM, picture, sound) on every scenario | `release_check.py` `native_reference` gate |
| G5 Delivered file | the packed executable that ships is replayed against the reference | `delivery_evidence.deliver_packed`, `replay_packed`, group `conversion_gates` |
| G6 States | F8/F9 across a fresh process, a damaged state refused, a missing one creates nothing | the kit's quick-state family, a versioned key |
| G7 Saves | battery, EEPROM, memory card, disk writes survive a quit without F8/F9 | the machine's save tests |
| G8 Liveness | pictures and sound change; the `play` route never frozen; captures looked at | `delivery_evidence.liveness_summary`, `frozen_route` |
| G9 Route depth | long or authored routes reach play | `random_routes` levels *extended* and *thorough*, or authored routes for a machine in `DECLINED['random_routes']` |
| G10 CPU vectors | independent CPU evidence | SingleStepTests sets where they exist (pinned in UPSTREAMS), else an independent model; `tools/<id>_selftest.py` |
| G11 Hardware proof | named behaviours checked by fixtures or an external emulator | the machine's fixtures |
| G12 Panel | the panel's games, none dropped for failing | `tools/campaign.py select`, `tools/campaign-risk-cases.json` (6 cases in 5 categories for `supported`) |
| G13 Cross-OS | Windows and Linux give the same route hashes | Linux in WSL (Debian 13) on the build PC; a GPU proof needs a real Linux PC; then `linux = 'witnessed'` |
| G14 Owner OK | the maintainer's play test, recorded | a checklist in QUALIFICATION; his words, dated |
| G15 Honesty | no exact fidelity, full game or latency claimed without proof | `status_lint`, the report's claims |
| G16 Shared hints | numeric hints, rechecked, retried without them; or `-` | [step 5](#step-5-sharing-paths-only-if-useful) |

How the work is done:

- **Generic first.** A game that fails reveals a shared mechanism to fix (the CPU, the bus, a device), not a game to patch.
  What is truly one game's (a protection, a timing quirk) is reviewed data keyed by the dump's SHA-256, never a condition on a
  title in code.
- **Counted fallback.** What is not native runs on the interpreter, counted per CPU and per device, and shown in the report,
  the interface and the documents. A gate is never met by hiding a count.
- **The five measures apart** in every report field, matrix entry and sentence: a `Y` of G4 says nothing of G11, and none of
  them is a latency figure.
- **Evidence that counts.** Compare the machine's state, not an engine's counters; a native run that differs from the
  interpreter refuses the conversion, it is never skipped; a zero needs a positive control that shows the probe can count; an
  authored proof program is checked before the machine is blamed; the Linux witness is the same tree, and a witness on part
  of the panel stays `P`.
- **A machine on an emulator core** (the Amiga, the Atari ST, the PlayStation, the Nintendo 64): only the CPU the converter
  translates counts as native, the other chips are named emulated, and the page says what each gate means for this core
  before the exit. A category with no translated CPU (Adventure, ScummVM) writes its own criteria on its page instead of the
  matrix.
- **Sibling profiles** (MSX, MSX2, MSX2+; Amiga and Amiga 1200) carry their own status words: a sentence naming one beside
  another's status is a `status_lint` error waiting to happen.
- **How much to test.** Reduce breadth, never depth; set the budget before starting; the player's real path first (the
  delivered executable, started as a player starts it). Lengthen a run only for a reason, and say it.
- **Conversions.** At most two at once per specialist and eight in all, builds with four jobs. Test conversions write under
  `.build/` with a scratch library (`RETRO_RECOMP_LIBRARY_DIR`); a proof of shared paths must not set it, since it also
  turns the path banks off. Compare executables for byte identity only when built at the same folder path.
- **G14.** Write the checklist in QUALIFICATION (as for the machines already there): six to eight games, what to do in about
  three minutes each, what should happen, the known limits, and the five measures to keep apart. The games are delivered
  executables in `Export/Games/<console>`, built in a player's conditions (empty library, online covers on, the portable
  toolchain), replacing the old ones. Only the maintainer fills the row, in his words, with the date. No tool and no agent
  sets G14 or the status. The code of the exit (status, notes in eight languages, credits, the status test) is prepared on
  the branch beforehand and waits for his word; G14 is its own dated commit.

Evidence: the matrix in letters, an evidence section per gate group, `python -B tools/qualification_gauges.py --write` then
`--check`.
Gate: every gate proved and none relaxed, then the maintainer's G14 and his word to leave the experimental status. Then
`status = 'supported'`, `linux = 'witnessed'`, the id in `SHARED_SYSTEMS` if it shares (step 5), and every sentence
`status_lint` lists, changed in the same commit.

## Step 3: multiplayer

The session contract is [HOST_KIT.md](HOST_KIT.md#25-multiplayer-sessions-session-abi-9); the player's page is
[MULTIPLAYER.md](MULTIPLAYER.md). The three modes (one controller per player, everyone, turns), the lobby, the chat and the
encryption come from the converter and the kit: the machine brings its state and its ports.

- [ ] **Digest.** The deterministic state as named fields in a fixed byte order, the same on Windows and Linux, leaving out
  what does not decide the next frames (the picture, the sound samples, step counters). Without it the machine is not offered
  (`netplay_session = False`). Check that Windows and Linux give the same digests on the same frames.
- [ ] **Tier.** Rollback (smooth) when the adapter gives `snap_bound`, `snap_save` and `snap_load`: the whole state that decides
  future frames, in memory, no allocation per call, valid after any frame, complete at once on load, and a save plus a load
  cheap enough to repeat several times in a frame. Write the snapshot field by field: an engine's own checkpoint often writes
  the ROM and allocates. When the engine's state cannot be saved that way (a load of tens of milliseconds, an allocation per
  call), the delay tier (`netplay_rollback = False`), as the PlayStation, the Nintendo 64 and the Game Boy Advance. A held
  button must not be pressed again after a load.
- [ ] **Seats.** `netplay_seats` from the ports the machine really had (multitaps, four-player boards), with
  `netplay_seats_ceiling` when it depends on the game, `netplay_shared_only` for one set of controls; `run_frame` reads every
  port, players 3 and 4 included, and a silent frame calls `run_frame` only.
- [ ] **Side effects.** Save writes, recordings and rumble only when allowed: never in a silent frame, never on a guest.
- [ ] **The host leads.** Restart for everyone (or `session_no_restart` with its notice when the restart relaunches the
  process); F8 / F9 in memory for the match; the game's own save handed to the guests (`session_save`, `session_save_put`),
  written back to the host's file only at a clean end, the old file kept as a backup; the options that change the run sent
  and locked (`session_options`: an option is one when two seats' digests differ with it); one clock for a machine with a real-time clock
  (`session_begin`); on a computer, the host types for everyone through the computer adapter.
- [ ] **Link cable**, if the machine has one: every PC runs every console and shows its own player's, `netplay_link_seats`
  set only once two consoles are proved on one PC.
- [ ] **Mixed builds.** `netplay_portable` only after the gate that two exports of one dump, differing only by their learned
  paths, compute the same frames.
- [ ] The machine's row in MULTIPLAYER.md (mode, players, notes) and the README's table, which reads the profile.

Evidence, in this order, each recorded in [UPGRADES.md](UPGRADES.md):

1. The kit's session on the machine's adapter, ROM-free where the machine allows (`tools/hostkit_session_selftest.py`).
2. A real export as two copies on one PC, then three or four when it seats them, with simulated latency, jitter and loss,
   a restart and a save and load (`tools/netplay_game_smoke.py`): the digests agree every second and no match breaks.
3. Two PCs on a home network (`tools/netplay_lan_acceptance.py`), the same commit on both PCs; then the maintainer's play on
   two PCs.
4. A link cable: two consoles on one PC (as `tools/gameboy_link_play.py`, `tools/gameboy_link_selftest.py` and
   `tools/gg_link_selftest.py` do), then two PCs. A two-PC link
   PASS counts only with « 2 ports » in the game's log on each PC and the same commit on both.

Physical latency is not measured; the input delay is counted in frames, which is not the same measure.
Gate: the proofs recorded, the profile fields set, the machine in MULTIPLAYER.md.

## Step 4: optimisation pass

The measure is the CPU time per frame on the player's path ([PERFORMANCE.md](PERFORMANCE.md#the-method)): the delivered
executable, alone, from the shell's own timing report.

1. **Identical output first.** Each change is proved on its own, before any timing: the same executable byte for byte where
   the change is in the converter (`tools/ab_conversion.py` builds A and B from two trees), else the same pictures, sound and
   state hashes on the panel's routes.
2. **Then a timed slot**, on the strict quiet gate: no conversion, test or agent running on the PC, and the maintainer's go
   (or his standing word for the night). A and B run interleaved on one pinned core at high priority, one warm-up dropped,
   then three timed runs; the median and the spread are kept, and a change within the spread is noise. A whole pass stays
   within about five minutes.
3. **Keep clean code, drop tricks.** A change that makes the code cleaner is kept even with no gain; a shortcut that weakens a
   safety net (a guard, a check, a counter, a fallback) is dropped even with a gain. Changes on the hot path are declared and
   reviewed. A stage measured slower on the quiet PC is reverted, even when the work behind it was large.
4. **Risky items go on a list for the maintainer**, with the gain and the risk: anything that could change behaviour, remove
   a guard or keep a stale cache. None is merged without his word.
5. **Say what it is.** A gain on a headless check only is named as such; a cost a release adds is written beside the gains.
   The machine's rows go in PERFORMANCE.md (Windows, and Linux in WSL2), then `tools/qualification_gauges.py --write`.

Gate: identical output proven for each change, no regression of the machine's row against the previous release, the
risky list answered.

## Step 5: sharing paths, only if useful

Sharing a machine's discovered paths is done only when it serves a purpose ([QUALIFICATION.md](QUALIFICATION.md#leaving-the-experimental-status)).

- [ ] **Measure first**, on the panel: would received paths add native instructions, or save a conversion pass? If not, or
  if the maintainer judges the gain too small, the machine does not share: G16 reads `-` with that evidence, and the id goes
  in `DECLINED['path_sharing']`.
- [ ] **If it shares:** schema 3 records ([COMPILATION_LIBRARY.md](COMPILATION_LIBRARY.md)), with an empty layout and the
  existing shapes when possible so that `path_profiles` (in every game stamp) is not edited; the record rules as data in the
  machine's knowledge module; caps that count what they leave out; a conversion that fails with received rows converted again
  without them, and the report says so; an audit with invented rows that shows none reaches the player's paths. The proof
  is made from two empty libraries: one converts and sends, the other receives and is measured.
- [ ] **Qualification of a path** is the shared rule: qualified when a conversion that received it from another player
  reached and validated it against the reference, for one engine revision; the maintainer's own campaigns are qualified
  outright; the sender's discoveries wait.
- [ ] **The site before the release.** The service's limits for the machine are regenerated from the profile and deployed
  before the release that starts sharing it, on the maintainer's word: a machine that shares before the service names it has
  its uploads refused whole.
- [ ] The id in `path_profiles.SHARED_SYSTEMS` and `knowledge_build.SYSTEMS`.

Gate: G16 `Y`, or `-` with its evidence.

## Step 6: release kit

For the release that ships the machine (and every release after it):

- [ ] **UPGRADES.md**, « Exports of the previous release in this one »: the game, host and build stamps measured between the
  two trees (`compilation_inputs.role_stamps` on `git archive` copies), the quick-state key of each machine checked with the
  code that holds it, and what is kept (cartridge saves, memory cards, written disks).
- [ ] **RELEASE_NOTES.md**: a complete, compact list under a few headings, one line per item, checked against
  `git log v<previous>..main`; the speed figures change by change with their costs; the five-measures sentence; the Windows
  security notice.
- [ ] **The in-app « What's new »**: a separate compact body for the GitHub release, under about 6,000 characters (the
  dialog cuts at 12,000), readable as plain text (no table, no meaning carried by bold alone), links absolute to the tag, ending
  with the security notice, the ScummVM source sentence and the link to the full notes. Run `updater.release_notes` on the
  file and read what it prints.
- [ ] **Credits** « Made by Retro-Recomp »: one short line per major piece of our own work, `label: body`, in eight
  languages, every character in the font subsets (STANDARDS rule 13).
- [ ] **README**: the version badge and the machine counts, a short « New in » paragraph, the machine's row (the console
  table is written by `tools/qualification_gauges.py --write`), the multiplayer table. It stays general.
- [ ] **QUALIFICATION**: the matrix in letters, then `qualification_gauges.py --write` and `--check`.
- [ ] **Stamps of the release**: `python -B tools/release_stamps.py --write` on the tree that is published, then `--check`.
- [ ] **Conversion times**: `python -B tools/conversion_times.py <report folders>` (Windows reports, portable toolchain), at
  least three reports per machine and level, the rest derived; `assets/conversion-times.json` is written from it by hand
  and reviewed.
- [ ] **The candidate in a player's conditions**: copies of real exports of the previous release converted again with online
  covers on, and the machine's games delivered for the maintainer.
- [ ] **Checks**: the suite, `prepare_publication.py --tracked`, `check_doc_links.py --public`, `gui_smoke.py`, `status_lint.py`,
  `qualification_gauges.py --check`, `release_stamps.py --check`.

Gate: the maintainer's publication go. Nothing is pushed, tagged or published before it.

## Step 7: who does what

| Who | Does |
|---|---|
| The maintainer | four decisions: a route that mixes GPL or noncommercial code (step 0); the G14 play test; leaving the experimental status; the publication go. A short list reaches him besides: risky optimisation items, a sharing gain that may be too small, the quiet PC for a timed pass. |
| The lead session | plans and writes the briefs, owns the cross-machine code (host kit shell, stamp machinery, registry, installer), reviews and merges every branch, runs the release, relays the maintainer's words. |
| A machine specialist | one per machine (or per family), created from the specialist template (`.claude/agents/_template-machine.md`, kept with the local agent files, outside the public repository): its profile, modules, native files, adapter, tools, tests and page, on its own branch `spec/<id>-<version>` in its own worktree. It never pushes or merges. |
| Shared specialists | documentation (cross-machine pages, notes, the release texts), interface (the in-game shell: F1-F12, pause, menus), multiplayer (the session, lobby and proofs), performance (timed passes, the risky list), upstream liaison (fixes offered back, sent only on the maintainer's word). |

Every brief carries the house rules:

- stop and ask on an unknown, a fundamental question or a blocker (two failed approaches, or about three hours with no step
  forward), with what blocks, what was tried and the options with a recommendation; then wait
  ([Stop and ask the maintainer](#stop-and-ask-the-maintainer));

- commit on the specialist's own branch, files staged by name, never a stash, never a push or merge;
- no visible window (SDL's dummy video and sound drivers, the splash screen suppressed), no busy-wait loop, no search of a
  whole disk;
- at most two conversions at once per specialist, eight in all, builds with four jobs; test outputs under `.build/`, a scratch
  library for test conversions;
- no ROM, firmware or game executable in the repository; games read in place, never modified;
- timing only on the quiet-PC go; external messages only on the maintainer's word;
- long outputs to files and the verdict in the message; a resume note at each boundary, and the specialist's « Learned »
  section updated;
- the five measures apart, the fallback counted, no « exact » and no « zero latency » without proof.

## Progress board

One column per machine in progress, from its study to the release that ships it supported; the column is removed once the
machine is in the QUALIFICATION matrix as supported and its release is out. Letters as in the matrix: `Y` done, `P` partial,
`N` no, `?` not started, `-` not applicable. `<id>` is the example column: copy it for each machine.

| Step | Item | `<id>` |
|---|---|---|
| 0 | Scope and hardware list | ? |
| 0 | Upstreams and licence route (maintainer's choice if mixed) | ? |
| 0 | CPU reuse line, firmware rule | ? |
| 0 | Panel of 7-8 games with reasons | ? |
| 1 | Profile, registries, `DECLINED` reasons | ? |
| 1 | Firmware search line | ? |
| 1 | Upstreams, notices, public files | ? |
| 1 | Eight languages, font subsets | ? |
| 1 | First game converted, fallback counted | ? |
| 2 | G1-G13, G15 (the matrix column) | ? |
| 2 | G14 checklist written, games delivered | ? |
| 2 | G14 and exit (maintainer) | ? |
| 3 | Digest, tier, seats | ? |
| 3 | Two copies with latency and loss | ? |
| 3 | Two PCs (and « 2 ports » for a link) | ? |
| 4 | Identical output per change | ? |
| 4 | Timed pass, PERFORMANCE rows, risky list | ? |
| 5 | Sharing measured: shares or declined | ? |
| 5 | Site limits deployed (if it shares) | ? |
| 6 | Notes, « What's new », credits | ? |
| 6 | README, gauges, release stamps, conversion times | ? |
| 6 | Publication go (maintainer) | ? |

---

**Reference.** What follows is the detail the steps point to.

## Experimental, then supported

A machine enters as `experimental` and may stay incomplete for a long time (CPS-1 stayed experimental until 1.6.6 and the X68000 until 1.6.9).
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
   add `LEGACY_GAME_STAMPS` entries for an experimental machine; list its own files under its own owner group; its licence
   pages are declared on its profile (`notice_files`), which makes them its own host inputs. A shared module (`m68000.py`, the kit) moves every machine that owns it.
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

## Registration steps

The detail of [step 1](#step-1-experimental-profile-and-registries). Do them in this order; the registry test tells you which one you missed. "Reuse" refers to the table after the steps.

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
differ from one run to the next (`tests/test_std_baseline.py` caught it). Each firmware option also gets its line in
`RECOGNISERS` of `retrorecomp/firmware_search.py` (keyed by the option's name: the check the conversion already makes, or digests
in `KNOWN_DIGESTS`), so that Options' « Find firmware in a folder… » looks for it; that module is interface code, so the line
moves no stamp. Gate: G1.

**3. Detection and input.** `retrorecomp/<module>.py` (a reader returning an object with `sha256`, `size` or `data`). The
extensions come from `profile.extensions` (`ROM_CANDIDATE_EXTENSIONS` is derived; only a foreign format the converter does
not read goes into `FOREIGN_EXTENSIONS` of the registry). A distinctive extension needs nothing else; an ambiguous one
(`.bin`, `.rom`, `.zip`) needs `Identify(path_order=..., content_order=...)` and the hooks `identify_path` /
`identify_content`, with an order that steals no existing console (the registry refuses a clash). A machine read from
ZIPs with a cartridge extension declares its size limit on its profile (`archived_rom_limits`). Test it with a synthetic file built
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

**8. Fingerprints.** `stamp_inputs.INPUTS`: one group for the machine's own modules, native files and data (its licence pages come from its profile's `notice_files`; the
only edit; an unlisted file is ignored, a listed missing one is an error, and `tests/test_stamp_inputs.py` fails for a tracked
file nobody listed). Its profile module, its host adapter, the 68000 / 16-bit-host / host-kit families and the shell every
console links come from the profile. The shared groups it reuses (`megadrive_codegen`, `neogeo_codegen`, `conversion_gates`,
`megadrive_z80`, `neogeo_build`, `neogeo_native`, `md_prefetch`, `guns16`, `z80_main`) are named in `stamp_groups`; a new file several
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

**13. Documents.** README (tagline, badge, count; its "Console support" table is written by `tools/qualification_gauges.py --write`,
and a machine still in development has a row in its "In development" table instead), COMPATIBILITY, SYSTEM_PROFILES, STANDARDS (count),
AGENTS_GUIDE (count), UPGRADES (kit row), CONTROLS, ROADMAP, MULTIPLAYER (step 3), QUALIFICATION (a column of the matrix in letters, `?` for what is not measured, and a row in its
"Console | Page" table), the machine's own page. Prose that counts consoles ("nine") is
hand-written in about ten places.

**14. Licences and credits.** `licenses/<engine>.md` for every component compiled into its games, declared on the profile
(`notice_files`; `optional_notice_files` for a part only some games use): `retrorecomp/notices.py` builds each game's embedded text
from that list and the stamps take the file's owners from it, so the notice moves no other machine's stamp. A row in
`THIRD_PARTY_NOTICES.md` (the public list, an input of no game) and the upstream's notice in `tests/test_game_notices.py`. The permissive engine preferred (MIT/BSD, as `ymfm` for CPS-1), the credits "Made by Retro-Recomp" line
in eight languages only for a major piece of our own work (STANDARDS rule 13). Rule 10: shared code is MIT.

**15. Checks to run.** `python -B -m unittest discover -s tests -q`,
`python -B tools/prepare_publication.py --tracked`, `python -B tools/status_lint.py`, then the machine's own tests: the shared kinds (fresh-process
states, saves, packed replay, languages, headless routes) plus its own.

## Reuse by CPU

| CPU | Machines today | Reuse | New for a machine on this CPU |
|---|---|---|---|
| 68000 | Mega Drive, Neo Geo, X68000, CPS-1, CPS-2, Atari ST; the Amiga 500 on its own chain | `m68000.py`, `megadrive_codegen.py`, `neogeo_codegen.py`, `native/m68000_backend.*`, path profile `m68k` shapes `insn`/`span`, SingleStepTests vectors; the Amiga's chain on Moira with translated forms (`retrorecomp/amiga_translate.py`) | memory map, bus, path map name (`m68k/<id>`), sources |
| 68EC020 | Amiga 1200 | the Amiga's chain on Moira and vAmiga, `tools/amiga_m68020_vectors.py` | a second model to compare with (G10) |
| Z80 | Master System, Game Gear, MSX, MSX2, MSX2+; the sound CPU of the Mega Drive, Neo Geo and CPS boards | `cpu.py`/`core.py`, `megadrive_z80.py`, `neogeo_z80.py`, `cps1_z80`, path profiles `z80/*`, SingleStepTests vectors; for a main-CPU Z80, the banked chain through `z80_chain.py` (group `z80_main`): the machine declares a `Z80Machine` (slots and bank key, RAM cut, M1 wait states, an NMI pin, its own instruction costs as a `Z80Costs` table when its bus stretches them) | bus and ports, path map, its `Z80Machine` |
| 6502 | NES | `nes_codegen.py`, `nes_runtime.py`, path profile `mos6502` | a variant's opcodes and banking |
| HuC6280 | PC Engine | the pinned PC Engine engine, `tools/fetch_huc6280_vectors.py`, `tools/pce_huc6280_vector_selftest.py`, shapes `insn` and `opcode_ptr` | another HuC6280 machine (SuperGrafx, CD-ROM²) adds its devices |
| SM83 | Game Boy | `gameboy_*.py`, path profile `sm83` | none for another SM83 machine |
| 65816 and SPC700 | Super Nintendo | `snes_codegen.py`, `snes_spc.py`, path profiles `w65c816`, `spc700` | cartridge devices as `DEVICES` entries |
| ARM7TDMI | Game Boy Advance | the pinned engine and its ARM core, `tools/fetch_gba_vectors.py`, `tools/gba_vector_selftest.py`, shapes `phys` and `span` | an ARM9 or a second ARM CPU would be new |
| MIPS R3000A | PlayStation | guarded native steps on the pinned core, `tools/fetch_psx_vectors.py`, `tools/psx_vector_selftest.py` | another R3000A machine: its bus |
| MIPS VR4300 | Nintendo 64 | guarded native blocks on the pinned core; test programs converted like games for G10 | no per-instruction vector set exists |
| SH-2, x86 and others | none | nothing | a recompiler or a core, a CPU vector set, a path profile and shapes, a report CPU entry |

CPS-2 reuses the CPS-1 modules (68000, Z80, romset reader, kit adapter) and adds the QSound device as a cartridge-device entry; the
Atari ST reuses the 68000 chain, the computer adapter of the kit and the media knowledge it shares with the X68000 and the Amiga.
The MSX family runs on the banked Z80 chain of the Master System. Adventure (ScummVM) has no translated CPU.

## What the registry test checks

`tests/test_machine_registry.py` runs `registry_problems(profile)` on every profile and returns sentences. For every machine:
status and CPU declarations; `ROM_CANDIDATE_EXTENSIONS`; the derived lists (`scan_levels`, `feedback`, `compilation_inputs`); `path_profiles`
(`SYSTEMS`, `SYSTEM_SECTIONS`, `PROFILES`, `SOURCE_BOUNDS`); `report_schema._SHAPES` equal to the profile's CPUs; the stamp manifest (profile
module listed, stamps computable, kit adapter for `rr16`); the firmware options in the command line, preferences and window, and their
recognisers in `firmware_search.RECOGNISERS`; the tab and scan
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
| `random_routes.SCRIPT_WRITERS`, `campaign.SHARE_FOLDERS` | Only for a new script format, or a share that names its folder differently |
| About eighty `system == ...` branches for the nine machines' own behaviour (`knowledge*`, `build_cleanup`, `memory_view`, the exchange, `scan_levels`, `core`, `gui_queue`...) | Not touched by a registration and not measured by the dry run; a machine meets them when it becomes supported (shared knowledge, library layout, build cleanup): remedies `library_layout`, `build_layout`, `scan_options` on the profile |

Removed since 27 October (1.6.3 and 1.6.4): the detection chain and the extension tables, the path tables and the map
shapes, the shared-knowledge lists, the report shapes and writer branches, the two copies of the stamp ownership, the host-kit
adapter list, the random-route pad tables, the firmware lists of the command line, the preferences and the window, the
generic options tab, the verification tools' console lists and gates, the catalogue tables, the report `status` literal, and
the tests that pinned the list of nine.

## Background: the dry run behind the registration steps

The registration steps were the model of the eleven machines added since (CPS-2 to the Amiga 1200). They follow [STANDARDS.md](STANDARDS.md) ("standardize before adding a machine") and was built from two dry
runs of the same experiment: a tenth machine, a synthetic **Atari ST** (68000, disk images, TOS firmware; not the Atari ST
of 1.7.1, see [ATARI_ST.md](ATARI_ST.md)), added on a throwaway
branch with a profile, detection of a synthetic disk, a schema 3 path section, a report written by the common builder, a
skeleton host-kit adapter, every registry, the verification tools, the translations and the documents. The first run was
on 27 October 2026 (`e4-dry-run`), before the standardization of 1.6.3; the second on 29 October 2026 (branches
`dryrun-atari-st-164` and `dryrun-atari-st-164-after`), as the acceptance test of that standardization and of the
1.6.4 fixes that followed. None is merged. That throwaway machine converts nothing, and no claim here goes beyond what those runs
and the suite measured.

### What it measured

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
