# Contributing to RetroRecomp

Keep the five validation areas separate: native execution coverage, CPU
fidelity, hardware fidelity, gameplay validation and physical latency.
Describe the exact path, frame count and conditions behind a measurement.
Do not infer full-game fidelity or zero latency from a native-cycle count.
Interpreter fallback is always counted, per CPU and per device, never hidden.

## Reports and ROMs

For bug reports, include the version, operating system, console, ROM hash and
steps to reproduce. Remove personal paths from logs. Do not upload commercial
ROMs, generated game executables or box art; none belongs in this repository.
Use a small authored diagnostic program when a public reproducer is needed.
Shared knowledge carries numbers about a ROM (addresses, positions, masks),
never ROM bytes.

## Before you change code

- Read [docs/STANDARDS.md](docs/STANDARDS.md): the rules every change follows
  (no third copy of shared logic, one profile per machine, versioned formats,
  unification with identical results, written "supported" criteria, clean
  licences, credits kept current and short).
- Every file has a declared role and every stamp hashes explicit lists, not the
  disk: a new native, asset or converter file is added to
  `retrorecomp/stamp_inputs.py` with its owners, and a change to a host or game
  file says which exports it affects ([docs/UPGRADES.md](docs/UPGRADES.md)).
- A new machine follows [docs/NEW_MACHINE.md](docs/NEW_MACHINE.md) (an
  experimental profile first) and is judged by the checklist in
  [docs/QUALIFICATION.md](docs/QUALIFICATION.md).
- A file is published only if it is on the explicit list in
  `tools/prepare_publication.py` (and, under `docs/`, un-ignored in
  `.gitignore`).
- Pinned upstream repositories (revisions, licences, how to check them and when to move a pin) are
  tracked in [docs/UPSTREAMS.md](docs/UPSTREAMS.md); a new machine declares its upstreams in
  `retrorecomp/upstreams.py`.
- Coding assistants: [docs/AGENTS_GUIDE.md](docs/AGENTS_GUIDE.md) is the short
  map and list of pitfalls.

## Checks

These need no ROM and are what the public CI job runs (Python 3.14):

```
python -B -m unittest discover -s tests -q
python -B tools/prepare_publication.py --tracked
python -B tools/check_doc_links.py --public
```

Run `python -B tools/gui_smoke.py` after interface changes. Native changes
require the relevant CPU, input and host self-tests (`tools/*_selftest.py`);
some need a compiler or locally supplied ROMs and cannot run in the public CI
job. See [docs/BUILDING.md](docs/BUILDING.md).

## Licences

Dependency revisions remain pinned. Describe the source and license of any
reused code, and retain third-party notices. Contributions to original
RetroRecomp code use MIT; third-party terms are not replaced by that license.
