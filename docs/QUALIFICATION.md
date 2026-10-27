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
