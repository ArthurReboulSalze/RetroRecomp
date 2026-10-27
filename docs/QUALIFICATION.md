# Qualification record

Per-console qualification record for Retro-Recomp. The rules every change
follows and the "supported" checklist are defined in
[STANDARDS.md](STANDARDS.md#supported-checklist); the gates G1-G16 below are
short names for that checklist, numbered by the 27 October 2026 pipeline
inventory. This page records the current status matrix and the
owner-acceptance log. It makes no claim beyond them.

## Gates

| # | Gate | Defined by |
|---|---|---|
| G1 | Scope and status stated consistently | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G2 | Report contract | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G3 | Native coverage on every final scenario | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G4 | CPU fidelity: fresh reference run | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G5 | Packed replay of the delivered file | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G6 | Fresh-process states | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G7 | Saves | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G8 | Liveness | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G9 | Route depth | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G10 | Independent CPU evidence | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G11 | Independent hardware evidence | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G12 | Panel | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G13 | Cross-OS witness | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G14 | Owner acceptance | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G15 | Honesty | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G16 | Shared-knowledge safety | [STANDARDS.md](STANDARDS.md#supported-checklist) |

## Status matrix (27 October 2026)

`Y` met, `P` partial, `N` no, `?` unknown, `-` not applicable. Consoles:
sms = Master System, gg = Game Gear, gb = Game Boy, nes = Nintendo NES,
md = Mega Drive, snes = Super Nintendo, ng = Neo Geo, cps1 = Capcom CPS-1,
x68 = Sharp X68000.

| Gate | sms | gg | gb | nes | md | snes | ng | cps1 | x68 |
|---|---|---|---|---|---|---|---|---|---|
| G1 | P | P | P | Y | Y | P | Y | Y | Y |
| G2 | P | P | P | P | P | Y | Y | Y | P |
| G3 | Y | Y | P | P | Y | Y | Y | P | Y |
| G4 | Y | Y | P | P | Y | Y | Y | Y | Y |
| G5 | P | Y | ? | Y | Y | Y | Y | Y | P |
| G6 | ? | ? | P | Y | Y | Y | Y | Y | Y |
| G7 | - | - | P | P | Y | P | Y | - | ? |
| G8 | ? | ? | ? | P | P | Y | Y | ? | ? |
| G9 | P | P | P | P | Y | P | Y | P | P |
| G10 | Y | Y | P | Y | P | P | P | ? | P |
| G11 | P | P | P | P | P | P | P | P | P |
| G12 | Y | P | Y | P | Y | Y | Y | P | P |
| G13 | P | P | P | P | P | P | P | P | Y |
| G14 | ? | ? | ? | ? | Y | ? | Y | ? | ? |
| G15 | P | P | P | P | P | P | Y | Y | P |
| G16 | Y | Y | Y | Y | Y | Y | Y | - | - |

### Caveats

- The G5 and G6 rows say "met" where the check exists as a campaign step.
  Only ng and cps1 run G5 inside every conversion, and ng, cps1 and x68 run
  G6 inside every conversion. Read G5 and G6 as "met per conversion" only for
  those three.
- G14 for NES, SNES, SMS, GG, GB, CPS-1 and X68 means "no recorded owner
  decision found", not proof that none exists. X68000 and CPS-1 owner trials
  were reported in chat on 27 October 2026 and are not written in a document
  yet; they belong in the owner-acceptance table below when recorded.

## Panel sizes

No common panel size exists today. The panel sizes noted by the 27 October
2026 inventory are: Neo Geo 24+10, Mega Drive 24+8, Super Nintendo DSP-1/CX4
8, Super FX 9, NES 8+10+8+6, Game Boy 606, Master System 258, CPS-1 26,
X68000 19. Whether G12 needs a common threshold is a policy decision that has
not been recorded.

## Owner acceptance

Owner play tests (gate G14), one row per test. The table starts empty; the
owner fills it in.

| Date | Console | Games tried | Verdict | Notes |
|---|---|---|---|---|
|  |  |  |  |  |

## Running the verification campaign

`tools/campaign.py` is a developer tool: it prepares and runs the pre-release
check on a sample of each console, with the verdicts of
`tools/release_check.py`. It is not in the converter or in any release
archive, reads the ROM folders without writing to them, and keeps every
output under `.build/campaign-<version>/`. Run it on the Windows build PC with
the converter about to be published (`Retro-Recomp.exe`, or `RetroRecomp.py`
from a checkout); it does not replace the owner's play tests (G14).

1. **Select.** `python tools/campaign.py select --roms-root <folder with one
   ROM folder per console> --version 1.6.0` (or set `RETRO_RECOMP_ROMS`; no
   private path is written in the tool). Per console, `--count` games (10 by
   default): half drawn at random with `--seed` (the same folder, seed and
   risk file always give the same games), half from the risk cases of
   `tools/campaign-risk-cases.json` (titles and the reason each one is hard,
   from this repository's documents; edit the file to change them). With
   `--random N`, every risk case found is taken plus exactly N random games;
   the 1.6.0 campaign uses `--random 2` with four or five risk cases a
   console, seven games at most (Arthur, 27 October 2026). Each file
   is read by the converter's own detector before it is kept. The result,
   `selection.json`, holds paths and SHA-256 only. `--hermes N` marks N games
   per console for the Linux sample.
2. **Run.** `python tools/campaign.py run <converter> --version 1.6.0 --jobs 4
   --level standard`. Up to 8 conversions run at once inside one batch per
   chunk of games (`--chunk`, default twice `--jobs`); one verdict file and one
   log per game go to `journal/<console>/`. An interrupted run resumes by
   skipping games that have a verdict (`--retry-failed` and `--redo` run them
   again; `--consoles`, `--subset hermes`, `--limit` and `--smallest N` narrow
   the run). Neo Geo takes `--ng-bios`, X68000 `--x68-ipl` and `--x68-cgrom`.
   The new observations stay in the converter workspace of the campaign
   (`out/app` for the frozen converter). On the Linux machine, run `select`
   again there with its own ROM root and the same seed, then `run --subset
   hermes` with the Linux converter.
3. **Report.** `python tools/campaign.py report --version 1.6.0` writes
   `summary.md` and `summary.json`: per console and game, the verdict, the
   scan level, the conversion time, the interpreter fallback per CPU and per
   cartridge device (read through `retrorecomp/report_schema.py`; "not
   measured" stays "not measured"), and the five measures separately with the
   claim each report makes: native code, CPU fidelity, hardware fidelity,
   gameplay validation, physical latency. A pass means the gates of
   `release_check.py` held (conversion, native/reference agreement, fallback
   limit, and for Neo Geo, CPS-1 and X68000 the packed replay and the
   fresh-process states); it says nothing about hardware fidelity, full games
   or latency. A case marked `expect: refusal` passes only when the converter
   refuses the cartridge, and is counted apart as "refused".
4. **Upgrade.** `python tools/campaign.py upgrade <converter> <export folder>
   [...] --from-version 1.5.6` copies existing exports into the campaign
   (the originals are untouched, and each old executable is kept under
   `upgrade/before/`), runs the converter's own batch path without `--force`,
   and records per game whether it was an already-current export, a quick
   upgrade (only the player shell changed) or a full reconversion, with the
   release_check verdict of the new report.
5. **States.** `python tools/campaign.py states pairs` resumes, for Mega Drive
   and Super Nintendo, a state written headless by each old export in its
   upgraded export, through `tools/state16_cross.py --one-way`; the outcome is
   resumed identically, resumed but different, diverged or refused.
   `states files --states-dir <folder>` loads slots saved by hand in the old
   player into the new exports (and, when the old export is known, compares
   both continuations). A refusal is a clean outcome unless a release note
   promises migration. What this proves is only what it ran: a state of real
   play from an older build is checked only when its file is given.
