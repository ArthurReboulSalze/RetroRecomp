# Performance: CPU time per frame

This page gives, for each machine, the **CPU time per frame**: how long the PC's processor takes to compute one frame
of a converted game, on the player's path. It is the host's cost of running the game. It is **not latency** and not
response time: it says nothing about how long a button takes to reach the picture, which is not measured. It is also
none of the other measures: native code, CPU fidelity, hardware fidelity and gameplay validation are on each machine's
page and in [QUALIFICATION.md](QUALIFICATION.md).

The README's machine table shows these figures in its « CPU per frame » column, written by `tools/qualification_gauges.py`
from the table below. A machine without a row there reads « not measured ». The release-to-release comparisons of the
same costs are in [RUNTIME_PERFORMANCE.md](RUNTIME_PERFORMANCE.md).

## How to read a figure

A game shown at 60 frames a second has **16.7 ms** for each frame (20 ms at 50 Hz). A figure of 2 ms means the processor
needs about an eighth of that frame to compute it; the rest of the frame it waits. The figures come from **one PC**:
another processor, another operating system or another load gives other numbers. A small figure is not a faster
reaction to a button, and a large one under 16.7 ms does not make the game slower.

## The method

- **The PC.** The reference PC: an AMD Ryzen 9 3900X under Windows 11, kept quiet during the timed pass (no conversion
  or test running, on the owner's go), the game's process pinned to one core (core 4) at high priority.
- **The path.** The game is the delivered executable, started with no argument, as a player starts it, alone (no
  multiplayer session), in a hidden-window test run (SDL's dummy drivers). It runs from boot with no input: the boot and
  the attract mode.
- **The figure.** The shell's own timing report gives the work of each frame: the machine's frame and its delivery, the
  sound queue, the drawing and the present. Pacing and the wait for room in the sound device are left out, since they are
  waiting, not work. Each run gives its work per frame from that report; the table gives the median of the runs.
- **The spread** is (max − min) / median of the runs, in percent: how much the runs disagree.
- **The version** is the converter's that built the game, with its commit when it was not a published release; the date
  is the day of the timed pass.

## The figures

| Machine id | Machine | Game | Median ms per frame | Spread | Runs x frames | Version | Date |
|---|---|---|---|---|---|---|---|
| sms | Master System | Sonic The Hedgehog | 0.87 | 6.1 % | 3 x 240 | 1.9.0 (main d8dba7b2) | 2026-11-20 |
| gg | Game Gear | Sonic The Hedgehog | 0.70 | 0.5 % | 3 x 240 | 1.9.0 (main d8dba7b2) | 2026-11-20 |
| gb | Game Boy | Super Mario Land | 0.76 | 5.0 % | 3 x 240 | 1.9.0 (main d8dba7b2) | 2026-11-20 |
| nes | NES | Metroid | 3.01 | 2.1 % | 3 x 240 | 1.9.0 (main d8dba7b2) | 2026-11-20 |
| md | Mega Drive | Sonic The Hedgehog 2 | 1.99 | 0.1 % | 3 x 240 | 1.9.0 (main d8dba7b2) | 2026-11-20 |

The other machines are not measured on this path yet.

## Adding or updating a row

One row per machine, keyed by its profile id (`retrorecomp/systems`), in the format above: the median in ms with two
decimals, the spread in percent, the runs and frames, the converter version as `X.Y.Z` (with `(main <commit>)` before a
release), the date in ISO form. Then run `python -B tools/qualification_gauges.py --write` so the README's column follows,
and `--check` passes. A timed pass needs a quiet PC and the owner's go first.
