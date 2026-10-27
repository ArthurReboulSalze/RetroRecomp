# Standards for adding to Retro-Recomp

Retro-Recomp converts games for nine machines (Master System, Game Gear, Game
Boy, NES, Mega Drive, Super Nintendo, Neo Geo, Capcom CPS-1, Sharp X68000) and
more are planned. This page states the rules every change follows and the
shape the code is converging to, so that a new machine costs a profile, a CPU
core and a host adapter, not a copy of everything. The inventory behind it
(27 October 2026) measured where the code is today; the target sections say
"target" where the code does not follow them yet. How the pipeline works
today is described in [ARCHITECTURE.md](ARCHITECTURE.md).

## The rules

1. **No third copy.** When logic appears for a second machine, it moves into a
   shared module instead of being copied a third time. A deliberate per-machine
   difference is a named capability of that machine, documented, not a silent
   divergence between two copies.
2. **Shared pieces first.** A new machine plugs into the profile, the host kit,
   the CPU-keyed path schema and the report schema. Anything it cannot use is
   written down in its own document with the reason.
3. **One place says what a machine is.** Its `SystemProfile` (in
   `retrorecomp/systems/`) carries its identity, status, CPUs, devices, export
   folder, scan settings and capabilities. Code reads the profile instead of
   testing `if system == ...`. *Target: about 25 registries and branches still
   hold this today.*
4. **Every file has a declared role.** `retrorecomp/compilation_inputs.py`
   classifies inputs as **host** (the player shell: an export is rebuilt, never
   rediscovered), **build** (toolchain) or **game** (discovery and generated
   code: exports need the upgrade path or a reconversion). A new file gets its
   role and its owners when it is created, and the change notes say which
   exports it affects. See [UPGRADES.md](UPGRADES.md).
5. **Stamps hash explicit lists, never what is on disk.** A fingerprint, ABI key
   or SDK stamp names its files; text inputs are hashed with normalised line
   ends. A stamp computed from a release tag must equal the stamp of the
   released executable. *Target: several stamps still glob directories.*
6. **Formats are versioned.** Paths, shared-base archives, quick states,
   battery files, reports and route scripts carry a schema version. Readers
   accept the previous version or refuse it cleanly, never misread it.
7. **Unify with identical results.** Moving code into a shared piece is done
   machine by machine, with proof that nothing observable changed: generated
   sources byte-identical, frames, audio and states identical before and
   after, on Windows and Linux. A behaviour change is its own documented step.
8. **Measurements stay separate.** Native code, CPU fidelity, hardware fidelity,
   gameplay validation and physical latency are reported separately everywhere
   (reports, interface, documents). Interpreter fallback is always counted and
   shown per CPU and per cartridge device, never folded away. Nothing says
   "exact" or "zero latency" without proof.
9. **"Supported" has written criteria**, the same for every machine (the
   checklist below), measured by tools where possible.
10. **Clean licences in shared code.** Shared code is MIT. Engines under other
    terms (PolyForm Noncommercial for the SNES engine, the GPL-free X68000 route
    with its private GPL comparison mode) stay behind a clear boundary and keep
    their notices. Third-party semantics come from documentation or permissive
    sources.
11. **ROM-free knowledge.** Paths are numbers about the ROM (addresses,
    positions, masks), never ROM bytes; imported paths are always checked
    again and dropped when a conversion fails with them.
12. **Files stay readable.** Beyond about 1,500 lines a module is split by
    responsibility.

## Target shape

### Profile (converter)

`SystemProfile` v2 is data first, hooks second: `id`, names, `status`
(`experimental` or `supported`), CPUs (with their roles: main, sound),
cartridge devices, media kinds, export folder, scan settings, quick-state
family, capabilities (guns, mouse, keyboard, battery, disks) and the hooks the
pipeline calls (identify, convert, report, freshness). Adding a machine means
adding a profile and its modules, not editing lists across the pipeline.

### Paths (discovery)

Paths are keyed by **CPU**, not by console: a game record owns one section per
CPU (Z80, 68000, 6502, SM83, 65816, SPC700...) and per cartridge device, plus
named sources (ROM, BIOS, IPL, disks). One validator applies per-CPU bounds;
the same limits are generated for the website's checks. Machines that share a
CPU share its path kinds. *Target: schema 3; today each console has its own
fields (`retrorecomp/knowledge.py`), and CPS-1 and X68000 have none.*

### Reports

One `conversion-report.json` schema, versioned, with a section per CPU and per
device (native counts, interpreted counts in one unit, per scenario), separate
sections for each kind of measurement, the scan level, routes, states and
saves. Readers (interface, freshness, uploads) read it through one module.
*Target: seven writers produce seven shapes today.*

### Host kit (exported games)

The machine core provides a frame buffer, audio samples, pad and pointer state,
state blobs and battery blobs. The kit provides the rest: window, scaling and
filters, fullscreen, input and bindings, menus and languages, audio output,
quick-state and battery files, preferences, the headless options the converter
uses (input scripts, captures, reports) and the window title that shows
fallback. The contract grows from the existing 16-bit one
(`native/retro_console16.h`). *Target: five host code bases today.*

## "Supported" checklist

A machine is `supported` when its conversions meet these gates on a panel of
exact ROMs converted from an empty private library; each gate is reported in
its own measure category.

| Gate | What is shown |
|---|---|
| Status | profile status, README, documents, release notes and interface agree |
| Report | the versioned report with separate main, audio and device counters |
| Native coverage | 0 interpreted main and audio instructions on every final scenario, or each one listed with its count; devices counted apart |
| CPU fidelity | a fresh reference run equals the native run (CPU, RAM, image, sound) on every scenario |
| Delivered file | the published executable is replayed against the reference |
| States | fresh-process F8/F9, damaged states refused, a missing state creates nothing |
| Saves | battery and similar saves survive without F8/F9 |
| Liveness and depth | pictures and sound change; long or authored routes reach play; captures inspected |
| Independent evidence | CPU vectors or an independent model; hardware fixtures or an external emulator for named behaviours |
| Panel and platforms | varied boards, none dropped for failing; Windows and Linux give identical route hashes |
| Owner acceptance | the owner's play test, recorded |
| Honesty | hardware fidelity, full-game coverage and latency are never claimed without proof |
| Shared knowledge | hints are numeric, rechecked, and the conversion retries without them on failure |

Per-console qualification record (gates G1-G16, status matrix, owner-acceptance
log): [QUALIFICATION.md](QUALIFICATION.md).

## Adding a machine

1. Profile v2 with status `experimental`.
2. CPU cores: reuse an existing one when the CPU is shared; otherwise add its
   path kinds and bounds to the schema.
3. Host adapter on the host kit; machine-specific inputs (keyboard, mouse,
   guns, media) as declared capabilities.
4. Reports, states and saves through the shared formats.
5. Tests: the shared kinds (states, saves, packed replay, languages, headless
   routes) plus the machine's own.
6. Qualification against the checklist, then `supported`.
