# Contributing to RetroRecomp

Keep the five validation areas separate: native execution coverage, CPU
fidelity, hardware fidelity, gameplay validation and physical latency.
Describe the exact path, frame count and conditions behind a measurement.
Do not infer full-game fidelity or zero latency from a native-cycle count.

For bug reports, include the version, operating system, mapper, ROM hash and
steps to reproduce. Remove personal paths from logs. Do not upload commercial
ROMs, generated game executables or box art. Use a small authored diagnostic
program when a public reproducer is needed.

Run `python -m unittest discover -s tests` for Python changes. Native changes
require relevant CPU/input/host checks; some need locally supplied ROMs and
cannot run in the public CI job. See [BUILDING.md](docs/BUILDING.md).

Dependency revisions remain pinned. Describe the source and license of any
reused code, and retain third-party notices. Contributions to original
RetroRecomp code use MIT; third-party terms are not replaced by that license.
