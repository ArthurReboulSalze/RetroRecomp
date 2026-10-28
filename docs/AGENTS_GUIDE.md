# Guide for coding agents and assistants

A short entry page for AI coding tools (Claude Code, Codex and others) and for
people who want the shape of the repository fast. It states facts and pitfalls;
the reasons live in [STANDARDS.md](STANDARDS.md) and
[ARCHITECTURE.md](ARCHITECTURE.md). Claude Code loads this page through the
one-line `CLAUDE.md` at the repository root. Codex and other tools that only
read `AGENTS.md` do not find it by themselves: point them here.

## What the project is

Retro-Recomp converts a player's own game dumps into standalone Windows or
Linux executables, with as much native code as possible and a counted
interpreter fallback for the rest. Nine machines: Master System, Game Gear,
Game Boy, NES, Mega Drive, Super Nintendo, Neo Geo (supported), Capcom CPS-1,
Sharp X68000 (experimental). Original code is MIT; some third-party engines
keep other terms ([THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)).

## Map of the repository

| Path | What is there |
|---|---|
| `RetroRecomp.py` | Entry point: interface, `batch` command line, internal stamp commands |
| `retrorecomp/` | The converter (Python): pipeline, interface, per-machine discovery and code generation; the window is `gui.py` plus the `gui_*.py` mixins ([ARCHITECTURE.md](ARCHITECTURE.md)) |
| `retrorecomp/systems/` | One `SystemProfile` per machine: identity, status, CPUs, devices, options |
| `retrorecomp/stamp_inputs.py`, `compilation_inputs.py` | What each stamp hashes and which role every file has |
| `retrorecomp/path_profiles.py`, `report_schema.py` | CPU-keyed paths (schema 3) and the common conversion report (v2) |
| `native/` | C and C++ runtime and host code compiled into exported games; `native/hostkit/` is the common host kit |
| `tools/` | Self-tests, release check, qualification campaigns, publication and documentation checks |
| `tests/` | The `unittest` suite, which needs no ROM |
| `assets/`, `profiles/`, `licenses/` | Pictures, fonts, locales, the knowledge snapshot, example profile, notices |
| `docs/` | Public documents, indexed in [INDEX.md](INDEX.md) |

## Checks that need no ROM

Python 3.14. Run from the repository root:

```
python -B -m unittest discover -s tests -q
python -B tools/prepare_publication.py --tracked
python -B tools/check_doc_links.py --public
python -B tools/gui_smoke.py
```

The first two are the public CI job. Native self-tests in `tools/*_selftest.py`
build C code and need a compiler (see [BUILDING.md](BUILDING.md)). Anything
that converts a real game needs the player's own ROM, outside the repository.

## Rules that are easy to break

- **No ROM in the repository**, ever: no dump, no generated game executable,
  no commercial box art. Paths and hints are numbers about a ROM (addresses,
  positions, masks), never ROM bytes. Use a small authored program when a
  reproducer is needed.
- **Every file has a declared role** (host, build or game) and its owners in
  `retrorecomp/stamp_inputs.py`; stamps hash those explicit lists, never what
  is on disk. A new file under `native/`, `assets/`, `profiles/` or
  `licenses/`, or a new converter module, is added there (with its owners, or
  declared out of the stamps) when it is created, or
  `tests/test_stamp_inputs.py` fails. Editing a host or game file moves the
  stamps of the consoles that own it and affects existing exports: say so in
  the change notes ([UPGRADES.md](UPGRADES.md)).
- **The public file list is explicit.** A file ships only if it is in
  `PUBLIC_FILES` in `tools/prepare_publication.py` and, for `docs/`, is
  un-ignored in `.gitignore`. Check with `prepare_publication.py --tracked`.
  Private notes, site and service tools, secrets and the user's ROM library
  stay out.
- **Five measures stay separate** everywhere (code, reports, interface,
  documents): native code, CPU fidelity, hardware fidelity, gameplay
  validation and physical latency. Interpreter fallback is always counted and
  shown per CPU and per device. Never write "exact" or "zero latency" without
  proof.
- **Follow [STANDARDS.md](STANDARDS.md)**: no third copy of shared logic, one
  profile per machine instead of `if system == ...`, versioned formats,
  unification with identical results, written criteria for "supported", clean
  licences in shared code, files split beyond about 1,500 lines, and the
  credits window kept current and short.
- **A new machine** follows [NEW_MACHINE.md](NEW_MACHINE.md): experimental
  profile first, then the checklist in [QUALIFICATION.md](QUALIFICATION.md).
  `tests/test_machine_registry.py` lists the registries a new machine must join.
- Text files are LF (`.gitattributes`). A user-visible string is translated in
  the eight interface languages; characters must exist in the font subsets
  (`tests/test_languages.py` checks this).
- Do not push, publish or release without being asked.

## Where to read next

[README](../README.md) · [CONTRIBUTING](../CONTRIBUTING.md) ·
[INDEX.md](INDEX.md) · [STANDARDS.md](STANDARDS.md) ·
[HOST_KIT.md](HOST_KIT.md) · [COMPILATION_LIBRARY.md](COMPILATION_LIBRARY.md) ·
[UPGRADES.md](UPGRADES.md)
