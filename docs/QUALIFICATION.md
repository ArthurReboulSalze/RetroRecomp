# Qualification record

Per-console qualification record for Retro-Recomp. The rules every change
follows and the "supported" checklist are defined in
[STANDARDS.md](STANDARDS.md#supported-checklist); the gates G1-G16 below are
short names for that checklist, numbered by the 27 October 2026 pipeline
inventory. This page records the current status matrix and the
owner-acceptance log. It makes no claim beyond them.

## Leaving the experimental status

The bar to leave `experimental` stays very high: every gate is proved, and no gate is relaxed to get there. The final decision is
always the maintainer's own: he decides whether a machine leaves the experimental status, on the panel criterion (G12) and on his
dated acceptance, worded as he gave it (G14). No tool and no agent fills G14, or moves a profile to `supported`, without his explicit
yes.

Path sharing (G16) is not asked of a machine on which it serves no purpose (the maintainer's decision of 14 November 2026): when the
panel shows that received paths would add no native instruction and save no conversion pass, or a gain the maintainer judges too
small to be worth it (his decision of 15 November 2026, the Nintendo 64), the machine does not share, G16 reads `-`
with that evidence in its entry, and `tests/test_machine_registry.py` lists it in `DECLINED['path_sharing']`. Sharing that serves a
purpose is still required.

## Gates

| # | Gate | Short name | Defined by |
|---|---|---|---|
| G1 | Scope and status stated consistently | Status | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G2 | Report contract | Report | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G3 | Native coverage on every final scenario | Native code | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G4 | CPU fidelity: fresh reference run | CPU check | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G5 | Packed replay of the delivered file | Delivered file | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G6 | Fresh-process states | States | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G7 | Saves | Saves | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G8 | Liveness | Liveness | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G9 | Route depth | Route depth | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G10 | Independent CPU evidence | CPU vectors | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G11 | Independent hardware evidence | Hardware proof | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G12 | Panel | Panel | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G13 | Cross-OS witness | Cross-OS | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G14 | Owner acceptance | Owner OK | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G15 | Honesty | Honesty | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G16 | Shared-knowledge safety | Shared hints | [STANDARDS.md](STANDARDS.md#supported-checklist) |

## Status matrix (27 October 2026; the X68000, CPS-1, NES and Game Boy columns, and G5 and G8 of the Master System, Game Gear, Super Nintendo and Neo Geo, of 1 November 2026; G8 and G10 of the Neo Geo of 2 November 2026; G10 of the Game Boy and G14 of the NES, CPS-1 and X68000 of 3 November 2026; G1 to G4, G13 and G15 of the Game Boy, G1, G7 to G10 and G15 of the Super Nintendo and G8 of the Mega Drive of 4 November 2026; G2, G10, G13 and G15 of the Mega Drive of 13 November 2026; G14 and G16 of the X68000 of 5 November 2026; the PC Engine and Amiga columns of 5 November 2026; the CPS-2 column of 6 November 2026; the PlayStation column of 8 November 2026; G7, G15 and G16 of the Amiga of 8 November 2026; G13 and G14 of the PC Engine of 10 November 2026; the MSX and MSX2 columns, and their G13, of 12 November 2026; G1 to G15 of the MSX and MSX2, and G2 to G12 and G15 of the MSX2+, of 13 November 2026; the MSX and MSX2 columns, and their G14, of 14 November 2026; G1 to G5, G8, G12 and G15 of the Atari ST of 13 November 2026; G2 to G9, G12, G13 and G15 of the Amiga of 13 November 2026, and its G14 and G16 of 14 November 2026; the Nintendo 64 column of 15 November 2026; G1, G12, G14 and G16 of the Amiga 1200 of 16 November 2026)

### Progress through the qualification list

<!-- qualification-gauges:begin (written by tools/qualification_gauges.py: edit the matrix in letters, not this block) -->

One line per console: how many of the gates that apply to it are met (a half for a partial
one). `unknown` and `no` count 0 and `not applicable` is left out. It is **approximate and not a quality score**: it does not mix the five
measures (native code, CPU fidelity, hardware fidelity, gameplay validation, physical latency), which stay separate in every report, and a
console's status is never a threshold of this bar: leaving the experimental status is the owner's own decision (G14, see
[Leaving the experimental status](#leaving-the-experimental-status)). The status column is read from the profile registry.

| Console | Status | Progress | Gates |
| --- | --- | --- | --- |
| Master System | supported | `██████████` 97 % | ✅ 14 · 🟡 1 · ❔ 0 |
| Game Gear | supported | `█████████░` 93 % | ✅ 13 · 🟡 2 · ❔ 0 |
| Game Boy | supported | `██████████` 97 % | ✅ 15 · 🟡 1 · ❔ 0 |
| Nintendo NES | supported | `█████████░` 91 % | ✅ 13 · 🟡 3 · ❔ 0 |
| Mega Drive | supported | `██████████` 97 % | ✅ 15 · 🟡 1 · ❔ 0 |
| Super Nintendo | supported | `█████████░` 94 % | ✅ 14 · 🟡 2 · ❔ 0 |
| Neo Geo | supported | `█████████░` 94 % | ✅ 14 · 🟡 2 · ❔ 0 |
| Capcom CPS-1 | supported | `█████████░` 90 % | ✅ 12 · 🟡 3 · ❔ 0 |
| Sharp X68000 | supported | `█████████░` 91 % | ✅ 13 · 🟡 3 · ❔ 0 |
| Capcom CPS-2 | supported | `█████████░` 94 % | ✅ 14 · 🟡 2 · ❔ 0 |
| PC Engine / TurboGrafx-16 | supported | `█████████░` 94 % | ✅ 14 · 🟡 2 · ❔ 0 |
| Game Boy Advance | supported | `█████████░` 91 % | ✅ 13 · 🟡 3 · ❔ 0 |
| Commodore Amiga | supported | `█████████░` 91 % | ✅ 13 · 🟡 3 · ❔ 0 |
| Atari ST | supported | `█████████░` 91 % | ✅ 13 · 🟡 3 · ❔ 0 |
| Nintendo 64 | supported | `█████████░` 90 % | ✅ 13 · 🟡 1 · ❔ 1 |
| Sony PlayStation | supported | `████████░░` 81 % | ✅ 10 · 🟡 6 · ❔ 0 |
| MSX | supported | `█████████░` 93 % | ✅ 13 · 🟡 2 · ❔ 0 |
| MSX2 | supported | `█████████░` 90 % | ✅ 12 · 🟡 3 · ❔ 0 |
| MSX2+ | supported | `█████████░` 91 % | ✅ 13 · 🟡 3 · ❔ 0 |
| Commodore Amiga 1200 | supported | `████████░░` 84 % | ✅ 11 · 🟡 5 · ❔ 0 |
| ZX Spectrum | supported | `████████░░` 82 % | ✅ 9 · 🟡 5 · ❔ 0 |
| PC Engine CD / TurboGrafx-CD | supported | `█████████░` 93 % | ✅ 13 · 🟡 2 · ❔ 0 |
| SG-1000 | supported | `██████████` 96 % | ✅ 13 · 🟡 1 · ❔ 0 |
| Game Boy Color | supported | `████████░░` 84 % | ✅ 11 · 🟡 5 · ❔ 0 |
| ColecoVision | supported | `██████████` 96 % | ✅ 13 · 🟡 1 · ❔ 0 |
| Amstrad CPC | supported | `██████████` 97 % | ✅ 14 · 🟡 1 · ❔ 0 |

**The matrix, with symbols** (the letters below are its source): ✅ met, 🟡 partial, ❌ no, ❔ unknown, ➖ not applicable.

| Gate (short name) | Master System | Game Gear | Game Boy | Nintendo NES | Mega Drive | Super Nintendo | Neo Geo | Capcom CPS-1 | Sharp X68000 | Capcom CPS-2 | PC Engine / TurboGrafx-16 | Game Boy Advance | Commodore Amiga | Atari ST | Nintendo 64 | Sony PlayStation | MSX | MSX2 | MSX2+ | Commodore Amiga 1200 | ZX Spectrum | PC Engine CD / TurboGrafx-CD | SG-1000 | Game Boy Color | ColecoVision | Amstrad CPC |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| G1 Status | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 🟡 | 🟡 | ✅ | ✅ | ✅ | ✅ |
| G2 Report | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 🟡 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| G3 Native code | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| G4 CPU check | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 🟡 | ✅ | ✅ |
| G5 Delivered file | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| G6 States | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 🟡 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| G7 Saves | ➖ | ➖ | ✅ | ✅ | ✅ | ✅ | ✅ | ➖ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 🟡 | ✅ | ✅ | ➖ | ✅ | ➖ | ✅ | ➖ | ✅ |
| G8 Liveness | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 🟡 | ✅ | ✅ | ✅ | ✅ | ✅ |
| G9 Route depth | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 🟡 | 🟡 | 🟡 | 🟡 | 🟡 | ✅ | ✅ | 🟡 | ✅ | ✅ |
| G10 CPU vectors | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 🟡 | ✅ | ✅ | 🟡 | 🟡 | 🟡 | 🟡 | 🟡 | ✅ | ✅ | ✅ | 🟡 | ✅ | ✅ | ✅ | 🟡 | ✅ | ✅ |
| G11 Hardware proof | 🟡 | 🟡 | 🟡 | 🟡 | 🟡 | 🟡 | 🟡 | 🟡 | 🟡 | 🟡 | 🟡 | 🟡 | 🟡 | 🟡 | ❔ | 🟡 | 🟡 | 🟡 | 🟡 | 🟡 | 🟡 | 🟡 | 🟡 | 🟡 | 🟡 | 🟡 |
| G12 Panel | ✅ | 🟡 | ✅ | 🟡 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| G13 Cross-OS | ✅ | ✅ | ✅ | ✅ | ✅ | 🟡 | 🟡 | 🟡 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| G14 Owner OK | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| G15 Honesty | ✅ | ✅ | ✅ | 🟡 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 🟡 | ✅ | ✅ | ✅ | 🟡 | 🟡 | ✅ | ✅ | ✅ | ✅ | ✅ |
| G16 Shared hints | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 🟡 | 🟡 | 🟡 | 🟡 | 🟡 | 🟡 | 🟡 | ➖ | 🟡 | ➖ | ➖ | 🟡 | 🟡 | ➖ | ➖ | ➖ | 🟡 | ➖ | ➖ |

<!-- qualification-gauges:end -->

<details>
<summary>The matrix in letters: the source that the tools read</summary>

`Y` met, `P` partial, `N` no, `?` unknown, `-` not applicable. Consoles:
sms = Master System, gg = Game Gear, gb = Game Boy, nes = Nintendo NES,
md = Mega Drive, snes = Super Nintendo, ng = Neo Geo, cps1 = Capcom CPS-1,
x68 = Sharp X68000, cps2 = Capcom CPS-2, pce = PC Engine / TurboGrafx-16, gba = Game Boy Advance, amiga = Commodore Amiga, atarist = Atari ST, n64 = Nintendo 64,
psx = Sony PlayStation, msx = MSX, msx2 = MSX2, msx2plus = MSX2+, zxs = ZX Spectrum, sg1000 = SG-1000 (supported on the owner's acceptance of 27 November 2026), pcecd = PC Engine CD / TurboGrafx-CD, gbc = Game Boy Color, coleco = ColecoVision (supported on the owner's acceptance of 27 November 2026), cpc = Amstrad CPC (supported from 27 November 2026, on the owner's G14).

| Gate | sms | gg | gb | nes | md | snes | ng | cps1 | x68 | cps2 | pce | gba | amiga | atarist | n64 | psx | msx | msx2 | msx2plus | a1200 | zxs | pcecd | sg1000 | gbc | coleco | cpc |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| G1 | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | P | P | Y | Y | Y | Y |
| G2 | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | P | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y |
| G3 | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y |
| G4 | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | P | Y | Y |
| G5 | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y |
| G6 | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | P | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y |
| G7 | - | - | Y | Y | Y | Y | Y | - | Y | Y | Y | Y | Y | Y | Y | Y | Y | P | Y | Y | - | Y | - | Y | - | Y |
| G8 | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | P | Y | Y | Y | Y | Y |
| G9 | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | P | P | P | P | P | Y | Y | P | Y | Y |
| G10 | Y | Y | Y | Y | Y | Y | Y | Y | P | Y | Y | P | P | P | P | P | Y | Y | Y | P | Y | Y | Y | P | Y | Y |
| G11 | P | P | P | P | P | P | P | P | P | P | P | P | P | P | ? | P | P | P | P | P | P | P | P | P | P | P |
| G12 | Y | P | Y | P | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y |
| G13 | Y | Y | Y | Y | Y | P | P | P | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y |
| G14 | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y |
| G15 | Y | Y | Y | P | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | P | Y | Y | Y | P | P | Y | Y | Y | Y | Y |
| G16 | Y | Y | Y | Y | Y | Y | Y | P | P | P | P | P | P | P | - | P | - | - | P | P | - | - | - | P | - | - |

The page of each console, which the README links its line to (a console of the matrix needs one):

| Console | Page |
|---|---|
| sms | [MASTER_SYSTEM.md](MASTER_SYSTEM.md) |
| gg | [GAME_GEAR.md](GAME_GEAR.md) |
| gb | [GAME_BOY.md](GAME_BOY.md) |
| gbc | [GAME_BOY_COLOR.md](GAME_BOY_COLOR.md) |
| nes | [NES.md](NES.md) |
| md | [MEGADRIVE.md](MEGADRIVE.md) |
| snes | [SNES.md](SNES.md) |
| ng | [NEOGEO.md](NEOGEO.md) |
| cps1 | [CPS1.md](CPS1.md) |
| x68 | [X68000.md](X68000.md) |
| cps2 | [CPS2.md](CPS2.md) |
| pce | [PC_ENGINE.md](PC_ENGINE.md) |
| gba | [GAME_BOY_ADVANCE.md](GAME_BOY_ADVANCE.md) |
| amiga | [AMIGA.md](AMIGA.md) |
| atarist | [ATARI_ST.md](ATARI_ST.md) |
| n64 | [NINTENDO_64.md](NINTENDO_64.md) |
| psx | [PLAYSTATION.md](PLAYSTATION.md) |
| msx | [MSX.md](MSX.md) |
| msx2 | [MSX.md](MSX.md) |
| msx2plus | [MSX.md](MSX.md) |
| a1200 | [AMIGA.md](AMIGA.md) |
| zxs | [ZX_SPECTRUM.md](ZX_SPECTRUM.md) |
| sg1000 | [SG1000.md](SG1000.md) |
| coleco | [COLECOVISION.md](COLECOVISION.md) |
| pcecd | [PC_ENGINE_CD.md](PC_ENGINE_CD.md) |
| cpc | [AMSTRAD_CPC.md](AMSTRAD_CPC.md) |

</details>

### Caveats

- SG-1000 and ColecoVision (27 November 2026; branch `spec/sg1000-coleco-supported`): **both leave the experimental status** (`supported`), on the owner's G14 of the same day and his word that they leave it in this release; G1 and G15 move from `P` to `Y`. **G1**: the two profiles say `supported` (listed to players, `linux = 'witnessed'` on the WSL witness of 22 November below), and the machine pages, MULTIPLAYER, ROADMAP, SYSTEM_PROFILES, the interface notes in the eight languages and the converter's own delivery notes say the same; the README, COMPATIBILITY, INDEX, release notes and credits are the documentation specialist's, and `tools/status_lint.py` is the check that they agree. **G15**: the two machine pages, their rows on the shared pages and the interface notes were read for « exact », « accurate », « perfect », latency and hardware claims: none. **G11 stays `P`** (MAME comparisons only, no hardware), **G7** and **G16** stay `-` (`DECLINED['path_sharing']`, with its reason). No other cell moved, and no panel was converted again for the flip: G2 to G13 are the readings of 22 November on `08196a91`. **G13 witnessed again** the same day on the release candidate's tree (`738e8075`, with F5 and the F3 looks): Flicky, Congo Bongo, Donkey Kong and Bump 'N' Jump converted by one script on Windows and on Debian 13 in WSL, empty scratch libraries: 146 values a game of the final checks (picture, RAM, VRAM and sound hashes, the frame trace, the native steps, the route script) and the snapshot digests of two probes each are equal, native equals the reference with 0 interpreted steps on both routes. Headless: no window, look or F5 on a Linux screen. Not claimed: hardware fidelity, gameplay beyond the games the owner tried, physical latency.
- SG-1000, ColecoVision, Amstrad CPC and Game Boy Color (27 November 2026; branch `spec/docs-g14-27nov`): **G14 moves from `?` to `Y`** on the owner's play test of the games delivered in `Export\Games` (three per console, the owner-acceptance table below): « Ok, je valide le G14 pour les autres consoles, à part pour le ZX Spectrum. » His remarks of the same day were handled before it: the Game Boy Color's sound stays as it is, on his word; Flicky and Bump 'N' Jump show the same picture in MAME, and an F5 sprite flicker reduction was added (off by default, [CONTROLS.md](CONTROLS.md)). A play impression, not a measure: no claim of CPU or hardware fidelity, of gameplay beyond the games tried, or of latency. **The four stay experimental**: no profile moves to `supported` here and G1 stays `P`; the flip comes with the release, on his word. **The ZX Spectrum's G14 stays `?`**: he held it back because Arkanoid's paddle still moves faster to the right than to the left on his pad.
- SG-1000 and ColecoVision (22 November 2026; branch `spec/smsgg-g10` at `08196a91`, Windows and a witness on Debian 13 in WSL, an empty scratch library, two conversions at a time; the matrix reading is the specialist's, the lead merges): **G2 to G6, G8, G9, G12 and G13 move from `?` to `Y` on both, G10 too; G1, G11 and G15 to `P`; G7 to `-` (neither console has a cartridge save) and G16 to `-` (sharing declined, below); G14 stays `?`** (the owner's, with the checklists of [SG1000.md](SG1000.md#10-g14-checklist-for-the-owners-play-test-22-november-2026) and [COLECOVISION.md](COLECOVISION.md#6-g14-checklist-for-the-owners-play-test-22-november-2026)). The panel is eight games on each machine, none dropped: ColecoVision Donkey Kong, Bump 'N' Jump, Pitfall II, Ken Uston's Blackjack-Poker (the keypad game), Alcazar (a maze), 2010 (a 32 KiB board with heavy guarded steps), Moon Patrol (32 KiB prototype) and Pac-Man (prototype); SG-1000 Flicky, Congo Bongo (PAL by its name), Sega-Galaga, Champion Baseball (40 KiB), Bomb Jack, Elevator Action, Zaxxon and Hang-On II. **G2, G3, G4, G5, G6**: `tools/release_check.py`'s `check_report` reads the 16 reports and passes every gate on all of them: conversion, native equals the reference on every final scenario, **0 interpreted steps** (main CPU; the video and sound chips are C models, counted apart as devices), the delivered file replayed against the reference, and the quick states in a fresh process with the damaged ones refused; the report is the common v2 with its counters separate. **G8 and G9**: every play route is alive at its end (the picture changes until frame 3,400 to 3,600) with audible frames measured on every one (nobody has listened yet); the captures at 1,800 and 3,500 frames of the 16 games were looked at (all in play, the ColecoVision keypad games after their menu); at the extended level one long route of 18,000 frames was run on eight of them (Donkey Kong, Pitfall II, Ken Uston, Pac-Man; Flicky, Elevator Action, Zaxxon, Hang-On II): every one stays alive to its last 20 to 220 frames with 0 interpreted steps and native equal to the reference, 2,670 to 10,533 distinct pictures (Ken Uston, a card game: 50). Pad routes, not full games, and the keypad tour can send a game back to its select screen (seen on Pac-Man, Pitfall II and Moon Patrol: the part before it reached play). **G12 and G13**: five of the panel's games (Bump 'N' Jump, Pitfall II, Ken Uston, Congo Bongo, Sega-Galaga) were converted again in WSL from the same sources: every field of the final checks (the picture, RAM, VRAM and sound hashes, the frame trace, the native steps) and the chosen start are equal to Windows', and the snapshot digests of seven real games (those five, Donkey Kong, Flicky) are equal on both systems; the authored self-tests ran on both. Not covered: a Linux PC with a real display. **G15 `P`**: the two machine pages, their rows in the README, COMPATIBILITY and CONTROLS were read for « exact », « zero latency » and hardware claims: none; the sweep of every page is the documentation specialist's. **G10 `Y`**: `tools/banked_vector_selftest.py --machine sg1000` and `--machine coleco` compile the 51,328 SingleStepTests/z80 vectors (22,704 encodings) with each machine's own build of the generator (`SG1000_MACHINE`, no wait state; `COLECO_MACHINE`, one wait state per M1 cycle added to the expected T-states): 51,328 pass, 0 fail, 0 miss on each ([CPU_Z80.md](CPU_Z80.md)); an emulator's vectors, not hardware captures, on a flat test bus, so the region map's dispatch is covered by the games, not by them. **G11 `P`**: no hardware was used. ColecoVision: the controller ports agree with MAME 0.289 line by line (two corrections it gave), the Z80's two wait states (one per M1 cycle, 28 cycles per sound-chip write) were found and kept, and the console's RAM writes of the BIOS and a cartridge's first 1000 frames are identical to MAME's; one parting after a key press is not explained. SG-1000: the pad ports for both pads and the one-NMI-per-press Pause agree with MAME; Flicky's frames agree for 65 frames and then differ by a frame phase that is understood and **not adopted** (a recorded difference, to revisit only if a game depends on it). See [COLECOVISION.md](COLECOVISION.md#5-evidence) and [SG1000.md](SG1000.md#7-where-it-stands-in-the-qualification). **G16 `-`**: path sharing is declined on the panels' evidence, under the owner's rule of 14 November 2026 (« useless sharing → no sharing », `DECLINED['path_sharing']` in `tests/test_machine_registry.py`): the 16 games learn no pattern (`learned_patterns` 0, every learning pass 0 interpreted steps) and reach 0 interpreted steps on every route, so a received path would add no native instruction and save no pass; neither machine is in `path_profiles.SHARED_SYSTEMS`. Not claimed: hardware fidelity, gameplay validation, physical latency.
- Amstrad CPC (22 November 2026, its figures taken again on 27 November with the routes' fire on the stick's default line, pin 6, bit 4; branch `spec/cpc-panel`, Windows and a witness on Debian 13 in WSL, an empty scratch library, two conversions at a time, the pinned CPC 6128 firmware; the matrix reading is the specialist's, the lead merges): **G1 to G10 and G12 to G15 are `Y`; G11 `P`; G16 `-`** (27 November 2026: the owner's G14, the supported status, the Linux witness on five games, the sharing declined). The panel is eight disks of the owner's library, none dropped, DSK and EXTENDED DSK: Bomb Jack, Gryzor, Head over Heels, Match Day II, Super Hang-On, Robocop, Castle Master and Dizzy - The Ultimate Cartoon Adventure, each with a boot route and a play route of 3,600 frames. **G2 to G6**: `tools/release_check.py`'s `check_report` passes conversion, native_reference, fallback, packed and states on the eight reports: the native run equals the reference interpreter on both routes, every field and every frame's row; **0 interpreted steps** on every route after two learning passes (the first interprets 0.3 to 13.6 million steps and learns them, the second 0; the Gate Array, CRTC, AY and uPD765 are C models, not counted as CPU); the delivered compressed file replayed headless equals both; a quick state continues in a fresh process and 13 kinds of damaged state are refused. **G1 `Y`**: supported from 27 November 2026 (`AmstradCpcProfile.status`, no longer developer-only: every installation lists and converts it), the Options note in eight languages, its page's « Known limits » section; it was experimental and developer-only before. **G8 `Y`, G9 `Y`**: every play route is alive at its end, reaching a level, a race, a match menu or a first screen in play (Head over Heels its menu), with audible frames on every one (190 to 2,932); the pictures at frames 2,400 and 3,600 were looked at. A long route of 18,000 frames (five minutes: the conversion's play route, then from frame 3,600 the joystick and a start key every 600 frames, `cpc_routes.LATER_FROM`, so that a game that ended goes back into play; the 3,600-frame scripts are unchanged byte for byte) was run on all eight with the programs each conversion built: native equals the reference on every compared field, drive A's digest included, and on every one of the 18,000 frames' rows; the picture changes to the end on all eight (435 to 13,696 distinct pictures); the code a game first runs after frame 3,600 runs on the counted interpreter (0 to 2,565,973 steps), since learning sees the 3,600-frame routes only. Captures at frames 6,000, 12,000 and 18,000: Castle Master, Gryzor (scoring) and Robocop in play at all three; Dizzy in its first room; Bomb Jack on its pyramids, then game over, then its menu; Super Hang-On racing in Africa, then its tables and title; Match Day II in a match at 18,000; Head over Heels stays on its menu (the cursor moves; no capture shows play). Random routes, not played games; nobody has played. **G10 `Y`**: `tools/banked_vector_selftest.py --machine cpc` compiles the 51,328 SingleStepTests/z80 vectors (22,704 encodings, in six parts that fit the two 16 KiB banks the CPC's map reaches) with the CPC's own build of the generator (`CPC_MACHINE`: its table of costs, 16-bit ports): 51,328 pass, 0 fail, 0 miss, registers, flags, WZ/Q/P and memory as on the other machines, each vector's T-states as the CPC's bus rule gives them for its own trace (not the table's value, so a taken branch, a repeating block instruction and every prefixed form meet their own count), and the whole port address of each I/O cycle ([CPU_Z80.md](CPU_Z80.md)); positive controls: the plain Z80 counts fail 30,015 vectors on cycles, the ports cut to their low byte 956 on I/O. Beside it the table is checked against its derivation (`tools/cpc_timing_table.py --check`) and authored programs give native equal to the reference (`tools/cpc_native.py`). An emulator's vectors on a flat test bus, not hardware captures; the interrupt acceptance, HALT and the 176 undefined ED opcodes are outside the corpus. **G12 `Y`**: the eight disks vary in format (odd tracks, weak and error sectors as `tools/cpc_panel.py` counts them), start command and kind of game; three more (Carrier Command, Dark Side, Rigel's Revenge) convert the same way, each chosen for a case the panel lacked. **G13 `Y`**: five panel games (Bomb Jack, Gryzor, Head over Heels, Match Day II, Robocop) converted on Windows and in WSL (Debian 13) from one commit (main `9ce0f3a6`), each from an empty library: the same learning on both systems (3,657,542, 13,606,247, 336,120, 6,088,720 and 1,268,142 interpreted steps on the first pass, 0 on the second), and on both routes the same final checks (native steps, 0 interpreted, the RAM, picture and sound hashes, the sound samples, the interrupts, the scripts), native equal to the reference and the delivered file equal on every frame's row; the multiplayer snapshot probe passes on both with the same folded digests over 301 frames of each play route (`75a8746ce9ab3afb`, `6ddf87dade799211`, `820a6c518dd7a3df`, `e404d2ff9b54537f`, `3b4a113e250c4c80`). Not covered: a Linux PC with a real display. **G15 `Y`**: every page that names the CPC (its page, README, COMPATIBILITY, MULTIPLAYER, QUALIFICATION, UPGRADES, CPU_Z80, INDEX, ROADMAP, SYSTEM_PROFILES, UPSTREAMS, HOST_KIT) and the game's own help and option texts were read for « exact », « accurate », « perfect », latency and hardware claims: none; two stale statements were corrected (COMPATIBILITY said nothing was converted, INDEX had no CPC entry, 27 November 2026). **G7 `Y`**: what a game writes on drive A goes to a copy beside it, and every conversion checks it in fresh processes of the delivered file (`cpc_conversion.check_disk_copies`, the report's `disk_writes`); the path was first proven on an authored program (`tools/cpc_reference.py` `write_program`, native equal to the reference with drive A's digest). A real game, 27 November 2026: Sport of Kings saves a meeting through its own SAVE option (its cassette calls, which AMSDOS sends to drive A: two files added). On the converted game, a headless run that plays the menus and saves writes the disk (`disk_written` 1, 167 controller commands against 139 without the save) and its copy; a fresh process on that copy starts from the written disk (`disk_start_fnv` equal to the first run's `disk_fnv`) and the game's own « load a saved game? » brings the meeting back with no setup questions, while the same keys on the embedded disk wait for a tape. Scripted input, no physical play; a second save over a file and a full disk are not exercised. **G11 `P`**: compared on 27 November 2026 with MAME 0.289's `cpc6128` driver as a private oracle, running the same firmware: over the firmware's first 4,098 RAM writes the two machines agree in order, value and time (within a write's place in its instruction); the CRTC, ROM-select, Gate Array and PPI write sequences are identical; the screen RAM at « Ready » is identical byte for byte and the picture pen for pen (one raster line apart); the interrupts come six a frame, 3,328 us apart, and a frame lasts 19,968 us in both; 25 authored blocks of instruction timing agree; and the uPD765 commands of a Bomb Jack load (945 bytes) and its sector data agree. They differ in the phase of the interrupts from reset (580 us: the CRTC's power-on registers), in port B's printer and expansion bits (MAME models a printer), in the disk's speed (ours has no rotation), in the ID a read returns at the end of a track, in the VSYNC width of the CRTC type, and by 1 us in the IM 1 acceptance (ours 5 us, MAME 4 us; neither measured on a CPC). It also showed the pad's main button on the stick's second fire line: Gryzor reads only the default one (pin 6, bit 4), now the main button's. Evidence from another emulator, not from a CPC; the acceptance waits for a hardware test. **G16 `-`**: path sharing declined under the owner's rule of 14 November 2026 (« useless sharing → no sharing », `DECLINED['path_sharing']` in `tests/test_machine_registry.py`), on the measure of three more disks (Carrier Command, Dark Side, Rigel's Revenge, 27 November 2026): received patterns add no native instruction (the same native code at the end, 0 interpreted either way) and save one learning pass (12 to 15 s of a 60 to 95 s conversion, not timed on a quiet PC); the CPC is not in `path_profiles.SHARED_SYSTEMS` ([AMSTRAD_CPC.md](AMSTRAD_CPC.md#5-panel-22-november-2026)). **G14 `Y`**: the owner played Bomb Jack, Gryzor and Head over Heels with the checklist of [AMSTRAD_CPC.md](AMSTRAD_CPC.md#7-g14-checklist-for-the-owners-play-test-22-november-2026) and gave it on 27 November 2026 (« CPC bien », then « Ok, je valide le G14 »). Not claimed: hardware fidelity, gameplay validation, physical latency.
- Game Boy Color (21 November 2026; branches `spec/gbc-profile` and `spec/gbc-qualify`, Windows, from an empty scratch library, two conversions at a time): G10, G11 and G13 move to `P`, every other gate stays `?`. Evidence, from the public test ROMs of the player's downloads run **in the Color build** (`tools/gameboy_testroms.py --model cgb`; the ROMs are not in the repository): 115 of the 116 applicable tests pass, each with the lock-step comparison against the pinned interpreter equal over every frame it ran (blargg `cpu_instrs` 11, `instr_timing`, `mem_timing` and `mem_timing-2`, the twelve `cgb_sound`, Mooneye's all-model timing, interrupt, timer, DMA, MBC1, MBC2 and MBC5 tests, `boot_hwio-C` and `unused_hwio-C`); `boot_div-cgbABCDE` fails (the engine has no boot ROM, so the divider's phase at the start is not the console's). Eight Color-only fixes were needed and each is named in `retrorecomp/gameboy_color_hardware.py` (seven by the test that showed it, the eighth, the order in which a tick feeds the sound unit in double speed, by Shantae's lock-step comparison, now equal over its 3,600 frames): the bus lock-out of OAM during a transfer, the timer's disable edge, the sound unit's power-off, the wave channel's writes and timer, the registers a cartridge without the Color flag finds, the 5-bit colour expansion. **Linux witness (G13):** Tetris DX converted in WSL (Debian 13, from an empty scratch library) and run on the same 1,900-frame scripted route: the picture hashes of six frames and the final state (registers, cycle counters, work RAM, video RAM) equal Windows's; one game, not a panel. **Why `P` and not `Y`:** the tests prove what the engine does against the hardware's own test ROMs, the CPU vectors do not cover STOP and double speed, the source bus split of an OAM transfer is the engine's and no test tells it from the original console's, and the panel has not been run on routes yet. Details: [GAME_BOY_COLOR.md](GAME_BOY_COLOR.md).
- Game Boy Color (22 November 2026, morning; branch `spec/gbc-qualify`, tree `fde462cd` on main `aeafa681`, Windows and Debian 13 in WSL, empty scratch libraries, two conversions at a time; the matrix reading is the specialist's, the lead merges): **G2, G3, G5, G6, G7, G8, G12 and G13 move to `Y`; G1, G4, G9 and G15 to `P`; G10 and G11 stay `P`; G14 and G16 stay `?`.** The panel is seven games, none dropped (Tetris DX, Pokémon Gold, Wario Land 3, Shantae, Super Mario Bros. Deluxe, Pokémon Pinball, Lufia). **G2 to G6**: `tools/release_check.py` (standard level, 2,878 s) passes every gate on all seven: native equals the reference, **0 interpreter cycles on all 28 final routes**, the delivered file replayed against the reference, the quick states in a fresh process; the code run one by one in writable memory (2,307 to 120,117 instructions a route, Lufia 0) is counted apart and is not native. The lock-step comparison is 30 boot frames and 240 a route on all seven (**G4 `P`**) and the whole 3,600 frames on Shantae (54.7 million steps) and Lufia (44.6 million) at the extended level. **G7**: `tools/gameboy_saves_check.py --model cgb` (six authored Color-only cartridges, 93 checks, 0 failure) and `tools/gameboy_states_check.py --model cgb`. **G8, G9**: every route of the seven is alive; the 18,000-frame route of Shantae and Lufia stays alive with 0 interpreted cycles (two games of seven: **G9 `P`**). **G13**: Tetris DX, Pokémon Gold, Super Mario Bros. Deluxe and Pokémon Pinball were converted again in WSL from the same tree: the per-frame traces and the final states equal Windows' on 20 of 20 routes (129,600 frames a system). **G16** is not decided: all seven games need a second discovery pass (the first interprets some code, Shantae 685,000 instructions on its boot route), so sharing the paths would save a pass; the owner's rule decides ([GAME_BOY_COLOR.md](GAME_BOY_COLOR.md#the-sixteen-gates-with-their-evidence-22-november-2026)). Not claimed: hardware fidelity, gameplay validation, physical latency.
- Game Boy Color (27 November 2026, the exit; branch `spec/gbc-supported` on main `847f17ed`): the profile is `supported` and Linux `witnessed`, after the owner's G14 of the same day. **G1 and G15 move from `P` to `Y`**: read again with the exit; `tools/status_lint.py` finds no contradiction once the release lines of README, COMPATIBILITY and RELEASE_NOTES say supported. **G16 moves from `?` to `P`**: the Color shares its paths (schema 3 records, `retrorecomp/gbc_knowledge.py`, experimental tier); the measure and the two-library proof are in [GAME_BOY_COLOR.md](GAME_BOY_COLOR.md#shared-paths-g16). It stays `P` while no path has been qualified by another player's conversion and the online service has not learnt `gbc`. **G4, G9, G10 and G11 stay `P`** (what that means for a player: [the page](GAME_BOY_COLOR.md#what-the-partial-gates-mean-for-a-player)).
- PC Engine CD (27 November 2026; branch `spec/pcecd-g9`, tree `75050d05` on main `dce6c18d`, Windows and Debian 13 in WSL, empty private libraries, two conversions at a time, the portable llvm toolchain, the player's own Japanese Super System Card 3.0; the matrix reading is the specialist's, the lead merges): **G2 to G8, G10, G12 and G13 move from `P` to `Y`; G1, G9, G11 and G15 are `P`; G14 and G16 are `?`**. Panel: nine discs of the maintainer's library (Ys III, Akumajou Dracula X in CHD version 4, The Addams Family, Lords of Thunder, Buster Bros., Dungeon Explorer II, Valis III, 4 in 1 Super CD, Ys Book I & II), none dropped, converted through `batch` by `tools/release_check.py` at the extended level (attract, play, and an explored long route of 21,600 frames). **G2**: report v2 with the HuC6280's counts and no device counter (the CD drive, CD audio and ADPCM are the engine's C++ models, not counted CPUs), the System Card named at the top level. **G3 to G6**: every gate of `release_check` passes on all nine: 0 interpreted instructions on all 27 routes, 0 guard misses, native equal to the reference on every frame, the published executable replayed (its hash is the report's), quick states in a fresh process with damaged ones refused. **G7**: backup memory files checked on all nine (a blank one is formatted by the System Card, a valid one read, eleven damaged ones set aside); Dracula X and Ys Book I & II write it on their long route, a fresh process starts with exactly that memory, and Dracula X shows the saved name (« PLAYER1 AA ») and goes on to play. **G8**: every route alive with audio, the nine long routes' captures looked at (nobody has listened). **G9 `P`**: eight of nine long routes reach play (a level, a fight, a town); Dungeon Explorer II reaches the player-count menu, the map and the opening scenes only. **G10 `Y`**: the vectors re-run on 27 November 2026 on this branch (`spec/pcecd-g10`, the corpus `SingleStepTests/huc6280` at `4ce378e0`, files digest `f5b70cc8…`, downloaded with the owner's yes): the pinned interpreter (`tools/pce_huc6280_vector_selftest.py`) runs 585,000 of the 640,000 vectors (the 22 reserved opcodes are refused by design), 563,514 equal, the differences exactly the explained ones (TSB and TRB flags, ST0 to ST2 cycle, TMA with mask 0), and the code the engine's emitter translates (`tools/pce_huc6280_native_vector_selftest.py --per-opcode 250`) runs 56,767 cases with 0 differences from the interpreter; the same CPU, emitter and pin as the disc games (the carried patches touch only the sound, picture and raster files). An emulator's vectors, not hardware; the CD banks and the System Card are exercised by the games, not by the vectors. **G11 `P`**: the drive, CD audio, ADPCM and backup memory are the engine's models; our own check covers the disc reading (`tools/pcecd_disc_selftest.py`: CHD 4 and 5, ISO and packed CUE equal to the Python reader and the engine's), nothing independent on drive behaviour. **G12**: five risk cases in `tools/campaign-risk-cases.json`; not covered: a real CUE or ISO disc (the library holds CHDs; CUE is proven on an authored disc), a System Card other than the Japanese 3.0, the standard RAM profile. **G13**: the nine discs converted in WSL from the same tree give the same exploration choices, modules and every final field (CPU, RAM, picture, PCM, trace, backup, native counts) as Windows; no Linux PC with a real display. **G14 `?`**: the owner's. **G16 `?`**: path sharing not measured yet, not declined. Not claimed: hardware fidelity, gameplay validation, physical latency. Details: [PC_ENGINE_CD.md](PC_ENGINE_CD.md).
- PC Engine CD, G14 (27 November 2026; branch `spec/pcecd-g11`; the owner's words relayed by the lead session): **G14 moves from `?` to `Y`**. The owner played the three games then in `Export\Games\PC Engine CD`: Akumajou Dracula X - Chi no Rondo (Japan), Lords of Thunder (USA) and Ys Book I & II - Ancient Ys Vanished (USA), converted that morning from `spec/pcecd-g9` at `25b86572` (extended level, online covers on, the owner's Japanese Super System Card 3.0), before the re-delivery of the same day. After playing them: « PC Engine très bien ». Later the same day: « Ok, je valide le G14 pour le PC Engine CD ». This is his play test and his impression: it says nothing of CPU or hardware fidelity, of complete gameplay or of latency. It does not by itself take the machine out of the experimental status.
- PC Engine CD (27 November 2026, afternoon; branch `spec/pcecd-g11`, conversions made on main `17758da3`, Windows, the portable llvm toolchain, the player's own Japanese Super System Card 3.0; the matrix reading is the specialist's, the lead merges): **G9 and G15 move from `P` to `Y`; G1 stays `P` (as for every machine still experimental) and G11 stays `P`, now with a comparison**. **G9 `Y`**: Dungeon Explorer II stopped before play because a disc without a save found a blank backup memory (« please initialize backup RAM »); the memory now starts formatted, as on a HuCard, in Beetle and in MAME, and the disc converted again at the extended level passes every gate with 0 interpreted instructions and reaches the castle in play. With it, all nine discs of the panel have a route that reaches play; the other eight were converted before the change, which a game feels only through what it reads from that memory (the three Export games were converted again after it). **G11 `P`**: `tools/pcecd_mame_compare.py` compares our interpreter with MAME 0.289 on three discs (Akumajou Dracula X, Lords of Thunder, Ys Book I & II) in the order the program made the events: every drive command with its parameters (30, 60, 27), the interrupt mask writes, the first and last sector of every CD audio playback, the data read through $1808 (up to 1,695,744 bytes), the ADPCM port writes and ADPCM RAM, the backup memory lock, unlock writes and final contents agree. Known limits: the System Card's signature at $18C3 differs, a few bytes of CD RAM differ on two discs after a while (the program's own variables, not traced), the lock polls differ in number; timing, sound mixing, video and a real console were not compared ([PC_ENGINE_CD.md](PC_ENGINE_CD.md), section 7). **G15 `Y`**: the audit's findings are closed (a disc game now keeps no player's record, so nothing promises a use it does not have; the drive-timing sentence, the card, CUE/ISO and Linux statements, the scan-level note; the credits name the PC Engine CD and libchdr; release-notes entry). **G16 `-`** (measured 27 November 2026, `convert` with the first pass starting from the module another conversion of the same disc learned, as a received bank would give it): a received module adds no native instruction (same exploration choices, same route scripts, same picture and CPU hashes, 0 interpreted with or without it) and saves the second learning pass: Ys Book I & II 2,144 s to 1,629 s (-24 %), The Addams Family 2,158 s to 1,710 s (-21 %), two conversions at a time, indicative and not a benchmark. No path format can carry it today: a disc's code runs from the CD RAM, which the PC Engine's records (offsets in the card) do not name, and its bytes cannot travel. A Standard conversion could gain code from an Extended one, which Extended already gives its own player. Declined for this release (`DECLINED['path_sharing']`), the owner's to confirm since a pass would be saved. **The exit:** the owner's decision of 27 November 2026 (relayed by the lead session) that the six new machines leave the experimental status in this release; the profile is `supported`. **G1 stays `P`** until README, COMPATIBILITY, the release notes and the credits are assembled for the release (the docs specialist's), then `Y` with `status_lint`.
- ZX Spectrum (21 November 2026, step 1 of the playbook, in development): G1 `P`: the profile is declared experimental and
  developer-only, `tools/status_lint.py` agrees, and no installation lists it; nothing converts yet, so every other gate is `?`.
- ZX Spectrum, G10 (22 November 2026; branch `spec/zx-g10` on main 7c8b04ba, Windows; the matrix reading is the specialist's, the
  lead merges): **G10 moves from `?` to `Y`**. `tools/banked_vector_selftest.py --machine zxs` compiles the 51,328
  SingleStepTests/z80 vectors (22,704 encodings, in six parts that fit the two 16 KiB banks the Spectrum's map reaches) with the
  Spectrum's own build of the generator, **its ULA contention on** (`ZXS_MACHINE`: 16-bit ports, `contention`; the bodies ask the
  machine's own C rule, native/zxs_machine): each vector starts at its own T-state inside a 48K frame's contended window
  (`z80_vector_start`: every phase of the 8 T-state pattern, the idle part of a line, several lines) and is expected the vector's
  T-states plus the delay the documented rule gives over its bus cycles from its initial state (`z80_vector_delay`, in Python, on
  the bus-cycle table these same vectors check T-state by T-state): 51,328 pass, 0 fail, 0 miss, registers, flags, WZ/Q/P, memory,
  the whole port address of each I/O cycle and the total T-states. 10,697 vectors carry a delay. Positive control: expecting no
  delay (`--expect-no-delay`) fails exactly those 10,697 on cycles. An emulator's vectors on a flat test bus with a documented rule,
  not hardware captures; the interrupt acceptance, HALT and the 176 undefined ED opcodes are outside the corpus (the acceptances and
  HALT are covered by the chain's compiled gate). Not claimed: hardware fidelity, gameplay validation, physical latency.
- ZX Spectrum, the panel (22 November 2026; branch `spec/zx-g10` on main 7c8b04ba, Windows and a witness on Debian 13 in WSL, an
  empty scratch library and datas, two conversions at a time, the ULA's contention and the floating bus on; the matrix reading is
  the specialist's, the lead merges): **G2 to G6, G12 and G13 move from `?` to `Y`; G8, G9 and G15 to `P`; G7 to `-` (a snapshot has
  no cartridge or battery save); G1 stays `P`, G11, G14 and G16 stay `?`**. The panel is eight snapshots, none dropped: Manic Miner
  (48K, the beeper), Jetpac (16K), Arkanoid (the floating bus), Match Day II (a Kempston chosen in its menu), Head over Heels (128K
  paging and the AY), Robocop (the game in the 128K banks, sampled speech), Elite (its own decryption at start) and The Hobbit (typing
  through the ROM), each with an attract route of 1,800 frames and a play route of 2,100. **G2 to G6**: `tools/release_check.py`'s
  `check_report` passes conversion, native_reference, fallback, packed and states on the eight reports: the native run equals the
  reference interpreter on both routes, every field and every frame's row; **0 interpreted steps** on every route (the ULA, the
  beeper and the AY are C models, not counted as CPU), after one learning pass on six games and two on Elite and The Hobbit; the
  delivered compressed file replayed headless equals both; a quick state continues in a fresh process and damaged states are
  refused. **G8 `P`**: seven play routes change their picture to the end (The Hobbit, a text adventure, is silent; the six others
  audible to frame 1,842 to 2,100), and the captures at frames 800 and 2,050 were looked at (Central Cavern, Jetpac in flight, the
  first round of Arkanoid with bricks broken, a match, the rooms of Head over Heels, Robocop's street, The Hobbit answering LOOK and
  WAIT); Elite does not: its program halts in its own decryption about 50 frames in, with or without contention and the floating bus
  (an open note in its report). **G9 `P`**: at the extended level a long route of 18,000 frames (five minutes) was run on four
  (Manic Miner, Jetpac, Head over Heels, Robocop): native equals the reference on every one of the 18,000 frames' rows, 0 interpreted
  steps, the picture still changing at frame 17,138 to 18,000, 2,804 to 8,493 distinct pictures, audible frames on all four; captures
  at 9,000 and 17,990: three in play, Robocop back on its control menu after its game ended. Random routes, not played games.
  **G12 `Y`**: the eight vary in model (16K, 48K, 128K), sound (beeper, AY, speech), controls (cursor keys, Kempston, Interface 2,
  the keyboard as a text parser) and what they read (the floating bus, a menu-chosen joystick, the 128K's paging); the reviewed data
  of four (start presses, a joystick interface) is keyed by their SHA-256. **G13 `Y`**: Manic Miner, Head over Heels, Arkanoid and
  Robocop converted again in WSL from the same tree give every field of every route's final check equal to Windows' (the CPU, RAM,
  picture and sound hashes, the frame trace, the step counts), the same chosen start and the same learning, and the compressed file
  replays there; no Linux PC with a real display. **G15 `P`**: the machine page and the Spectrum's rows of the README and
  COMPATIBILITY were read for « exact », « zero latency » and hardware claims: none (the stale « converts nothing yet » of the README,
  COMPATIBILITY and the profile's scope note corrected); the sweep of every page is the documentation specialist's. **G11 `?`**: the
  contention and floating-bus fixtures are written from documented numbers (Ramsoft's guide; Clock Signal, MIT, agrees on the 48K
  and differs by about 5 T-states on the 128K's first fetch, unverified); no hardware and no second emulator compared. **G16 `?`**:
  six games learn their code with no interpreted step on the first pass, Elite and The Hobbit need a second (24,126 and 3,422,129
  steps on the first): a received path would save that second pass (about 13 to 16 s of learning) on those two and add no native
  instruction; whether that gain is worth sharing is the maintainer's to decide. **G14 `?`**: the owner's, with the checklist of
  the six delivered games. Not claimed: hardware fidelity, gameplay validation, physical latency.
- ZX Spectrum, G11 (27 November 2026; branch `spec/zx-g11` on main f63e259b, Windows; MAME 0.289 as a private oracle, never in a
  game; the matrix reading is the specialist's, the lead merges): **G11 moves from `?` to `P`**. No hardware was used: this is
  agreement with a second emulator. The eight panel games were replayed in MAME 0.289 from the same snapshots, with the same
  routes and the same peripherals (a Kempston, the idle Fuller box). The paper was compared on every frame of the 2,100-frame
  play route (our frame f is MAME's picture f+1).
  - Manic Miner: 2,043 of 2,099 frames identical.
  - Match Day II: identical from frame 1,082 to the end; the 18 frames that differ are all in its menus.
  - Head over Heels (128K paging and the AY): 1,958 of 2,098 frames identical.
  - Elite stops in MAME too. It halts with interrupts disabled at the same instruction, with the same registers, and the RAM is
    byte-identical at frame 300: the stop is the snapshot's, not our machine's.
  - Robocop: pixel-identical through its menus and in many play frames; held left behaves the same.
  - Arkanoid: its paddle matches MAME frame by frame. This comparison found our only real error: the floating bus was sampled
    one T-state early, and it is fixed (ZX_SPECTRUM.md, section 5).
  - The other frames that differ do so by 1 to 92 pixels in one or two rows, never more than three frames in a row. We draw each
    paper row at the end of its line, so a byte written while the beam passes shows a line later than in MAME. This was traced on
    one frame (Jetpac, frame 168: the same writes in the same order).

  Two differences are recorded and **not adopted**:
  - The start phase of a snapshot that does not give one. A `.z80` v1 carries no T-state, and we start at the end of the
    interrupt. Jetpac seeds its random numbers from the R register: with MAME's R advanced by 114, it is identical on 1,610 of
    2,099 frames; without that, it parts at frame 368.
  - The Hobbit makes a different random choice at frame 709. A seed in RAM differs from the start key at frame 150, and no start
    phase of ours from 0 to 480 T-states (step 8) reproduces MAME's.

  Not claimed: hardware fidelity, gameplay validation, physical latency.

- ZX Spectrum, G14 (27 November 2026; branch `spec/zx-pad`): **G14 moves from `?` to `Y`**. The owner's words: « Je viens de
  tester Arkanoïd et c'est parfait aussi. Bien joué. Je passe le G14 pour le Spectrum. » He played from `Export\Games\ZX Spectrum`,
  on his own gamepad. Six games were delivered there for this test: Manic Miner, Jetpac, Head over Heels, Match Day II, Arkanoid
  and Robocop (Arkanoid, Robocop, Manic Miner and Jetpac rebuilt on 27 November from main e6bc5eec; the two others from 22
  November).
  - His reports named Arkanoid and Robocop. Which of the four others he opened is not recorded here.
  - Arkanoid was the last open point. He had found right faster than left, and the ball leaving when the stick moved. Both are
    the game's own rules (ZX_SPECTRUM.md, section 6b), and he saw left become the fast side with the check given to him.
  - This is the owner's acceptance. It is not a gameplay validation of each game from end to end, and physical latency was not
    measured.
- ZX Spectrum, the exit (27 November 2026; branch `spec/zxs-supported` on main 9ce0f3a6; the matrix reading is the specialist's,
  the lead merges): **the ZX Spectrum leaves the experimental status in the release after 1.9.1**, on the owner's decision of the
  same day, after his G14. The profile is `supported` and listed in every installation (it was developer-only).
  - **G16 moves from `?` to `-`**: path sharing is declined on its measure, under the owner's rule of 14 November 2026. Each of
    the six delivered games replayed, on the native code its Standard conversion learned, the two 18,000-frame long routes a
    deeper level adds. From 0.000 % to 0.089 % of the instructions ran on the interpreter (Arkanoid 149 and 27 instructions;
    Head over Heels 119,537 and 118,060 of about 134 million), which is all a received path could make native. Random routes, not
    a player going through a game's levels. `tests/test_machine_registry.py` lists the machine in `DECLINED['path_sharing']`.
  - **G1 stays `P`**: the profile, the machine page, the Options tab in eight languages and the README's status table say
    supported; `tools/status_lint.py` still reads « experimental » in COMPATIBILITY's paragraph and the README's « In development »
    text, which are written with the release's pages. It reads `Y` once they agree.
  - **G15 stays `P`**: the machine page, the Options notes and the report fields were read again after the exit for « exact »,
    « zero latency » and hardware claims: none. The release's README and COMPATIBILITY text is still to be read.
  - **G8 and G9 stay `P`**: seven of the eight panel games animate to the end of their play route, and Elite's snapshot halts in
    its own decryption (in MAME 0.289 too; its report says `route_stop`). Routes are random, with an 18,000-frame route on four
    games.
  - Not done: a two-PC multiplayer test of a Spectrum game. The game records nothing of the player's play (its
    runtime-feedback kind, 28, is reserved; the F12 row stays OFF, as on the MSX), so code past the routes stays interpreted and
    counted. Not claimed: hardware fidelity, gameplay validation, physical latency.

- Atari ST (6 to 9 November 2026; experimental profile of 1.7.1, raised on the branch of 1.7.2): G1 `P`: the profile is declared experimental and
  `tools/status_lint.py` agrees, and the machine is offered to players in 1.7.1. G2 `P`: the common report v2 of every conversion. G3 `P`:
  the ten panel games converted at the Standard level: with TOS 1.04 0 to 3 instructions interpreted on a route (2,139 on Turrican II on 6 November, 0 in the
  delivered conversion of 8 November), with EmuTOS 1.4, the default, 4 to 6 on seven games, 75 and 1,065 on the two the desktop starts (Hatari's
  GEMDOS traps), 1,781 on Kick Off 2. At the thorough level Lethal Xcess shows 4 interpreted over four routes including two of 18,000 frames
  (a first read ran 145 million on a route when the disk was changed under a game that did not ask for it: the long routes now change disk once, in the
  second route only). G4 `P`: every route of every conversion is identical, frame by frame, to a fresh interpreted reference; this shows that the
  steps equal the core, not that the core equals a 68000 (the independent corpus is G10). An authored program that rewrites its very next instruction
  (`tools/atarist_prefetch_check.py`) gives the interpreter's result through the native code, guarded by the opcode Hatari latched (8 November 2026). Since 1.7.2 the native code is Hatari's handlers
  specialised per opcode and chained; all 45,814 forms equal the table's handlers on random states, and the frame comparison stands. The routes play the joystick since 7 November (a port swap of Hatari's frontend had left it unplugged); a live check with real SDL
  keys and a virtual gamepad on the delivered Bomb Jack and Lethal Xcess proves the controls, and the owner's play trial of 7 November, on the nine
  reconverted games, found the gamepad control working: a trial of the controls, not an exit and not a gameplay validation. G5 `P`: the compressed
  copy too. G6 `Y`: on the ten panel games of 8 November 2026 the state saved on the main route continues in a fresh process on every column,
  CPU registers, RAM, picture and sound samples, for 400 frames (the sound used to be left out and Turrican II and a state taken during a disk read used
  to differ: three mechanisms of Hatari's restore were found and fixed, ATARI_ST.md section 5); `tools/atarist_saves_check.py`, authored, shows that a
  missing state creates nothing and that a damaged state and a state of another build are refused before the machine is touched, on an IPF and on a
  plain-sector disk. G7 `P`: what a game writes to its disks is kept beside the quick state and survives without F8/F9 (the authored check, in separate
  processes, on both formats: written, found by a new process, the image unchanged, a damaged file kept aside), and on a real game on 9 November 2026 (`tools/atarist_saves_game.py`): The Lurking
  Horror saves by GEMDOS, 27 sectors, on TOS 1.04 and on EmuTOS, on Windows and on a Debian 13 PC, and a new process with the file restores to the room of the save, where a process without it answers
  "Failed."; that check found a defect, a write after a seek without verify (EmuTOS seeks so) looked on the wrong track. Not kept: a formatted track. One game; no game of the panel was seen saving. G8 `P`: a moving picture is required on the main route. G9 `P`: the extended and thorough levels add one and two pseudo-random
  routes of 18,000 frames; the whole panel ran at the thorough level from one tree on 9 November 2026, with the timer D patch on for every game (it has been chosen per game since 1.7.3): all 40 routes equal to their fresh reference and to the compressed copy, the captures inspected, 0 to 5,075 instructions
  interpreted on a route. Six reach play on a long route (Bomb Jack, Captain Blood, Indiana Jones, Kick Off 2, Lethal Xcess, Turrican II). Four do not, as a random route cannot answer a protection: Another World, Elite, Operation Stealth, and Carrier Command, whose manual-word protection blanks the screen after three wrong entries (the same on TOS 1.04; the game idles, nothing failed). G10 `P`: the SingleStepTests 68000 fixtures through Hatari's cycle-exact 68000 and the native steps
  (`tools/atarist_vector_selftest.py`): 6,764 vectors; flat bus 6,762 run, the state agrees on 6,760 (the two others are divisions by zero whose flags the 68000
  leaves undefined); ST map 3,593 run, all agree; clocks on the flat bus 4,363 equal, 1,857 the ST's 4-cycle rounding, 14 CHK vectors 4 clocks more, 528 neither
  explained nor refuted (a fixture without a list of bus transactions); the native form was compared on 6,107 vectors and equals the interpreter on all of them;
  the fixtures leave out odd-address and bus errors, TAS, TRAPV and interrupt acknowledge. G11 `P`: authored 68000 programs measured from inside the machine against
  the hardware's documentation (`tools/atarist_hardware_check.py`, 51 measurements: the PAL and 60 Hz frame and line, the MFP's prescalers, timer B and timer D, the detector that chooses the timer D mode of a game (12 authored programs), a 320x200 picture pixel by
  pixel, the YM2149's tone periods, the IKBD's packets and byte time, the WD1772's index period, step rates and DMA reads): 49 agree and two are recorded differences
  (the YM2149 runs on the PAL crystal's division, 0.27 % above the round 2 MHz, which its data sheet gives as a maximum; timer D, started from the TOS's addresses, runs far slower with Hatari's `hatari_timerd` patch: 96 interrupts for 598.4, and 599 when RAM starts it or when the patch is off. A game that uses this timer as TOS left it sees another rhythm with the patch, which is why it is chosen per game since 1.7.3: [ATARI_ST.md](ATARI_ST.md#5-known-limits)). The 263 lines at 60 Hz rest on the GLUE's vertical counter as MAME and the gstmcu replica model it. Read again on 9 November 2026: the MC68901 and YM2149
  data sheets, STINTERN and the ikbd protocol text confirm what they are cited for; not reached: the WD1772 data sheet (one transcription of its summary differs on the step rates), the Atari Compendium, the ST's schematics, so those numbers are said to rest on Hatari and MAME. MAME 0.289
  agrees on the video and MFP lines it can run and could not run the WD1772, the IKBD, the picture or the sound; no real ST was measured, STF PAL only. G12 `P`: with EmuTOS the panel reaches 9 of 10 own screens (Another World shows its code wheel, then "ERROR" for the route's
  random entry), Operation Stealth and Captain Blood being started from the desktop; Kick Off 2, which stopped on its own error until 8 November, now plays (the write
  splice of Hatari's IPF reader covered the first sync mark of a sector, ATARI_ST.md section 3); Turrican II is one EmuTOS documents as incompatible and plays in a
  level with the player's TOS 1.04. G13 `Y`: the ten panel games converted and validated on a Debian 13 PC with the system GCC and link-time optimisation, from the tree of 9 November 2026 with the timer D patch (Standard level, an empty library): the same native and interpreted counts as Windows and
  the traces of all 20 routes byte for byte equal to Windows' (picture, sound, RAM, CPU registers of every frame), each state continuing; The Lurking Horror's saves too. No game played on Linux (window, sound, pad). G15 `P`: read on 8 November 2026 for this gate (the machine page, this
  matrix, COMPATIBILITY, the README, the release notes and upgrades, UPSTREAMS, INDEX, KNOWN_FAILURES, the roadmap, the architecture page, the two licence notices, every
  string that names the machine in the eight languages, the conversion's messages and every field of the report, the adapter and player strings, nine reports); 15
  statements were corrected (one stale, six overclaiming or incomplete, eight wording); since then, the timer D limit is stated in the report (`machine.timer_d`: the mode, why and the signs seen), the machine page and the upgrades; no fidelity is claimed for it, and the frame comparison cannot see it as the reference has the patch too; still open and not the specialist's to change: the shared F1 help lists drive B
  and eject controls the Atari ST answers "not available" to, the common report's `gameplay.claim`, and the site's card that lists the machine as upcoming. G14 stays
  `?`: the acceptance is the owner's decision. G16 `-`: the Atari ST shares no paths and is not in `SHARED_SYSTEMS`, the owner's decision of 9 November 2026: its steps
  call Hatari's own handlers, so a shared path would raise the native count without making a game faster. The question comes back with a translated 68000, and a
  supported Atari ST would have to join the sharing (`tests/test_machine_registry.py`). No hardware fidelity is claimed, no game is validated and the latency is not
  measured ([ATARI_ST.md](ATARI_ST.md#3-the-five-measures)).

- Atari ST (13 November 2026; tree of `spec/atarist-174`, Windows, one conversion at a time from an empty scratch library): **G1, G2, G3, G4, G5, G8, G9, G12 and G15 move from `P` to `Y`**; G6 and G13 stay `Y`, G7, G10 and G11 stay `P`,
  G14 stays `?` and G16 `-`. The evidence is in [ATARI_ST.md](ATARI_ST.md#3-the-five-measures) (the panel of eight) and in [UPGRADES.md](UPGRADES.md). **G12 is `Y`: the panel of eight is converted and validated on Windows and on a Debian 13 PC, and the two agree (13 November 2026; system GCC and the tree of `spec/atarist-174` on Linux, llvm-mingw on Windows, extended level, one scratch library per game, the game's files deleted after each run): every one of the 8 games, 24 routes (3 each at the extended level; the fourth route that Lethal Xcess has at the thorough level on Windows was not run on Linux), has the same trace hash on both systems (CPU registers, RAM, picture and sound of every frame), the same native and interpreted counts, and the compressed copy and the state continuation equal the fresh reference. Nothing was played on Linux (window, sound, pad). The Linux tree is the branch before the new in-game interface of `main`, which moves the host stamp only.** The Windows half: eight games chosen for what each adds, none dropped, every one equal to the fresh reference on every route:
  Bomb Jack (the plain case: EmuTOS, starts by itself, a joystick game), Another World (two disks, a code-wheel protection), Operation Stealth (three disks, started by the desktop, Hatari's GEMDOS hook, a colour-code protection), Turrican II (the player's own TOS 1.04,
  which EmuTOS cannot run), Kick Off 2 (protected tracks read through the WD1772 model, line A in the game), Lethal Xcess (timer D chosen `exact` by `auto`, two disks and a disk change), The Lurking Horror (a text game on the keyboard, started by the desktop, saving through GEMDOS)
  and Battle Probe (a disk read wrongly until 1.7.4, started by the desktop). **G4 and G5 `Y`**: on the 25 routes of the panel (extended level, 3,000 frames twice and 18,000 once; Lethal Xcess at the thorough level with a second route of 18,000 that changes the disk) the
  native game and its compressed copy equal the fresh interpreted reference, frame by frame (picture, sound, RAM, CPU registers), and the published executable is byte for byte the compressed copy that was replayed (SHA-256 compared); the reference is Hatari's own interpreter, which
  the vectors of G10 check and not an independent oracle. **G3 `Y`**: the interpreted instructions of every run are listed where they ran (address, opcode, count; the counts add up to the run's total on 25 of 25 routes): EmuTOS's own start (four to six), Hatari's GEMDOS hook while the
  desktop starts a program (351 to 775,400 on a route) and the game's line A opcodes, which never become native; devices are counted apart (they run on Hatari). **G2 `Y`**: the report names the Shifter/GLUE/MMU and the YM2149 as devices with no counter, the MFP, the IKBD and the WD1772
  with its DMA beside them, and carries `route_warnings`. **G8 `Y`**: the picture changes on the main route of all eight games and each is heard on a route; the last picture of every route was looked at by the specialist agent, not by the owner. **G1 `Y`**: `tools/status_lint.py`
  finds 0 contradictions, and the pages were corrected (the desktop list, KNOWN_FAILURES, ROADMAP); the one statement that still disagrees is outside this machine's pages: the public page `site/index.html` lists the Atari ST among the machines that "will join", each in its own experimental phase.
  **G15 `Y`**: the machine page, this matrix, COMPATIBILITY, the README, the release notes, UPGRADES, KNOWN_FAILURES, ROADMAP, the F1 help of the adapter (it lists only the disk keys the machine answers) and the report's claims were read again after the features of 1.7.3 and 1.7.4; five
  statements were corrected (the list of desktop games, Kick Off 2 listed as failing, two stale lines of the roadmap and the count of games "left to the player"); no fidelity, completeness or latency is claimed. **G9 `Y`**, on the same rule as the Master System and Game Gear of 5 November (two of twelve games never started there, each listed in `route_warnings` with its reason): six of the eight panel games reach play or a match (Bomb Jack, Turrican II, Kick Off 2, Lethal Xcess after the disk change, The Lurking Horror, Battle Probe); Another World and Operation Stealth stop on a protection whose answer is on a wheel or a card that came with the game, and each says so in `route_warnings`: no route answers or skips a protection, and no verifiable list of the answers was found. The seven games outside the panel add three more stops of the same kinds (Carrier Command, Elite, and The Seven Gates of Jambala on its title). **G7 stays `P`**: one real game (The Lurking Horror) saves through GEMDOS on two TOSes and two systems; a second game was tried on 13 November (The Pawn asks for a file name, then answers "Ouch - bad save", with three names: the file system of its disk is a nine-sector fragment holding only its loader and it expects a blank formatted disk, which the machine does not offer
  yet; Trinity does not start in low resolution), so it is not a second proof. The same run converted seven more games (Captain Blood, Carrier Command, Championship Cricket, Elite, Indiana Jones and the Temple of Doom, Outcast, The Seven
  Gates of Jambala), validated the same way and outside the panel; no letter rests on them. G14 is the owner's: his folder holds the exports.
- MSX and MSX2 (13 November 2026; experimental profiles `msx` and `msx2` of 1.7.3; letters set on the evidence of the release tree, main `6bdc7863`,
  whose MSX code is that of the tag `v1.7.3`): the panel is ten cartridges converted at the extended level (attract, play and an 18,000-frame route) from an empty
  library with C-BIOS 0.29a, through the real batch command, and delivered to the owner's `Export` on 12 November 2026: for the MSX Knightmare (plain 32 KiB),
  Road Fighter and Space Invaders (plain 16 KiB), Nemesis (Konami), Salamander (Konami SCC) and Spy vs Spy II (PAL, Konami SCC chosen by the probe); for the
  MSX2 Metal Gear (Konami), Space Manbow (Konami SCC), Aleste (ASCII 16, chosen by the probe where the bytes suggested Konami SCC) and Hydlide 3 (ASCII 8).
  Salamander was also converted with the owner's own MSX BIOS on the development tree of 12 November. G1 `P`: the profiles are declared experimental and
  `tools/status_lint.py` agrees; the machine is offered to players in 1.7.3; a read of the pages for this gate is still to do (G15), and three statements of
  [MSX.md](MSX.md) were found stale and corrected on 13 November (no Linux witness, no release-level run, Salamander black under C-BIOS: the panel's
  captures show its first stage drawn under C-BIOS as with the owner's BIOS). G2 `P`: every conversion writes the common report v2, but its main CPU block carries no count (`native` and `interpreted` are
  `null` on every route: the MSX's rows name them `native_steps` and `interpreted_steps`, which the common reader does not read) and its device list is
  empty; the counts are in the MSX's own `final_checks`. G3 `Y`: 0 interpreted Z80 instructions on all 30 routes of the ten games (16.8 to 121.8 million
  native instructions a route), and on the three routes of Salamander with the owner's BIOS; code run from RAM is translated with byte guards and counted; there
  is no audio CPU. G4 `Y`: every route is run again on a fresh reference (the same machine with every instruction on the reference Z80 interpreter) and
  must equal the native run on the state fields at its end (39 fields on the MSX2: CPU, RAM, VRAM, the V9938 and the mapper, the sound samples) and on one
  row per frame (CPU, RAM, picture, sound); a conversion that differs is refused; all 30 routes are equal. This is agreement with our own reference, not
  with a real MSX (independent evidence is G10). G5 `Y`: the compressed copy is replayed on every route and gives the same rows, and its SHA-256 is the
  published file's, on all ten games. G6 `Y`: on all ten games the state saved at frame 2,940 of the play route on the delivered file is loaded by a fresh
  process that continues the same rows for 600 frames (picture, sound, RAM, program counter: the full register set is not in these rows), 13 damaged copies
  (empty, cut, a flipped bit in each header field and the build binding, the payload, a file that is not a state) are refused with exit 4 and left as they
  were, and a missing state creates nothing; the same on a Debian 13 PC (G13). G7 `N`: battery saves are not kept: the SRAM mappers and the FM-PAC are not
  converted and the MSX2 clock's memory is not kept between runs; no panel game was checked for a save. G8 `P`: a moving picture is required on the play and
  long routes (not on attract) and the conversion refuses a route that never changes; sound is recorded per route; the captures of all ten games were looked
  at by the specialist, not by the owner. Missing: the report's `route_warnings` stays `null`, so a route that never reaches play (Hydlide 3) is not named
  in the report. G9 `P`: the extended level adds one pseudo-random route of 18,000 frames; on it the six MSX games and three of the four MSX2 games reach
  play (Metal Gear's play route is held by its first transceiver call, its long route goes on), and Hydlide 3 never leaves its Set Up menu (character
  creation, name entry). The thorough level was not run. G10 `P`: no independent CPU vectors are run through the MSX's own build of the generator; the
  translation rules are those of the Master System's banked chain, whose 51,328 SingleStepTests/z80 vectors pass on the Master System's build (G10 `Y`
  there), and the MSX build differs by its region map and its M1 wait state. G11 `P`: MSX2: against openMSX 22.0 (private, never shipped) the 128 KiB VRAM,
  the 47 VDP registers and the palette are equal at chosen still frames on the C-BIOS logo, two authored cartridges and the four MSX2 panel games; the V9938
  command times were measured on openMSX run as a separate program (within 4 % with the display off, 1 to 7 % on average in the picture, up to about 40 % on
  some shapes with sprites on); 682 hand-worked checks of the V9938, its command engine and the board. MSX: only the key click's level was measured
  against openMSX; the TMS9918A, the AY-3-8910 and the SCC are not compared with an independent reference. No real MSX was measured. G12 `P`: the ten
  cartridges cover the plain, Konami, Konami SCC, ASCII 8 and ASCII 16 boards, NTSC and PAL, C-BIOS and an own BIOS, and none was dropped for failing; six
  and four games are fewer than the other machines' panels, and Windows and Linux were compared on one game each (G13). G13 `P` (owner decision, 12
  November 2026): Nemesis and Metal Gear (Japan) converted headless on a Debian 13 PC with the system GCC 14.2 from main `ebae2550`, C-BIOS fetched on
  first use, 0 interpreted instructions on their three routes and every compared report field equal to Windows (per route: the native, guarded and
  interpreted counts, the frame trace, the RAM, VRAM, picture and sound hashes, the rows of the native and compressed runs), quick states passing; not
  played in a window there. G14 `?`: no row in the owner-acceptance table; the owner tried the MSX2 exports of 12 November 2026 (his remarks on the
  scrolling, the aspect and the covers were fixed before 1.7.3), which is not recorded as a verdict. G15 `?`: the read of every statement for this gate
  is to do. G16 `-`: the MSX shares no paths and is not in `SHARED_SYSTEMS`. Not yet implemented: disks, cassettes, FM-PAC, the SRAM mappers, MSX2+.
  Scope and the five measures: [MSX.md](MSX.md).

- Atari ST (14 November 2026; branch `spec/atarist-175`, Windows, toward leaving the experimental status): **G7 moves from `P` to `Y`**, and **G16 from `-` to `P`**; every other letter is as of 13 November
  (`Y` on G1 to G6, G8, G9, G12, G13 and G15; `P` on G10 and G11; `?` on G14). **G7 `Y`:** the save is shown on the delivered executable of a panel game, not only on the reference player
  (`python -B tools/atarist_saves_game.py --exe "Lurking Horror, The.exe"`, the file the batch delivered into `Export/Games/Atari ST`, EmuTOS inside, headless, separate processes): 27 sectors written, the file of the
  disk writes found by a new process (the room of the save, "Second Floor", where a process without the file shows "Terminal Room" and "Failed."), the executable byte for byte unchanged, and a damaged file kept aside as
  `<name>.unusable-1` while the game starts from its disks. It is the one panel game that saves by a script (the routes are joystick, mouse and keyboard scripts; a track a game formats is not kept: limit in
  [ATARI_ST.md](ATARI_ST.md#5-known-limits)). **G16 `P`**, like the other experimental sharers: the Atari ST shares its paths (Arthur's decision of 14 November 2026, «Oui, il partage») as schema 3 records of rows into the
  player's own TOS and into the logical sectors of the player's own disks, on the common `m68k_media_knowledge`; `knowledge.received` (offered, reached, added) reports what received paths gave. Shown on Operation Stealth,
  The Lurking Horror and Turrican II: a library at the extended level exports its record, an empty library imports it, the conversion is equal to the fresh reference on every route with and without it (traces 32 of 32).
  **Not a gain in conversion passes** (1 and 1 in all twelve conversions), nothing changed on the routes the receiver runs, native code added beyond them: on a route the receiver did not run Turrican II goes from
  30,455,168 interpreted instructions to 2,920,653 (-90 %), The Lurking Horror by 1.1 % and Operation Stealth by 8 %; the speed value is not measured (the added forms run Hatari's handlers, the saving is the interpreter's
  dispatch). Safety on Turrican II: a record moved to addresses no run reaches leaves the conversion equal to the reference, a record of other disks is ignored with its reason. Not yet: the Linux half of G16. The 1.7.5
  work also settles the Atari ST's risk cases (five in `tools/campaign-risk-cases.json`) and a play checklist for the owner (below); the simulated flip to `supported` (a scratch run of `registry_problems`, nothing
  committed) lists no other requirement of the registry; the four texts a flip changes are README, COMPATIBILITY, the release notes and the interface strings (`tools/status_lint.py`). G14 and the flip are the owner's.
- Game Boy Advance (14 November 2026, evening; branch `spec/gba-supported-176`, from `spec/gba-175`): **G14 moves from `P` to `Y`** on the owner's play test of the six games of the checklist (the owner-acceptance table below) and the Game Boy Advance **leaves the experimental status: it is supported from 1.7.6** (1.7.5 was frozen the same morning), on Arthur's word (« Oui, sors-la »). **G15 stays `Y`** as proposed by the entry of the same day on `spec/gba-175`, after the pages were read again for the new status (the README, the compatibility page, the interface strings in eight languages and the report say `supported` and keep the five measures apart; "exact" and "zero latency" are written nowhere). The matrix is otherwise unchanged: `Y` on G1 to G9, G12 to G15, `P` on G10 (94 % of the independent vectors), G11 (no external emulator) and G16 (the experimental tier of the base); 91 %. The scope and limits (no level won, no latency measure, no hardware-fidelity claim) are in [GAME_BOY_ADVANCE.md](GAME_BOY_ADVANCE.md#the-exit-from-the-experimental-status-14-november-2026-supported-from-176).
- Atari ST (14 November 2026, evening; branch `spec/atarist-supported-175`): **G14 moves from `?` to `Y`** on the owner's play test of the seven games of the checklist (the owner-acceptance table below) and the Atari ST **leaves the experimental status: it is supported from 1.7.5**, on Arthur's word (« Oui, sors-le »). The matrix is otherwise unchanged (`Y` on G1 to G9, G12 to G15; `P` on G10, G11 and G16): G10 and G11 are named behaviours measured against documentation and fixtures, G16 has its Linux half still to run; the exit record and its scope are in [ATARI_ST.md](ATARI_ST.md#7-where-it-stands-in-the-qualification).
- MSX and MSX2 (13 November 2026, afternoon; branch `spec/msx-174` after `def76191`): G1, G2, G8, G9 and G10 moved from `P` to `Y`, G7
  from `N` to `P`, G15 from `?` to `P`. The panel of the morning entry plus Dragon Slayer II - Xanadu (Japan) (ASCII 8 with battery SRAM) was converted
  again at the **thorough** level (attract, play and two pseudo-random routes of 18,000 frames) from an empty library, two at a time: 44 routes, 0
  interpreted Z80 instructions on each, each equal to its fresh reference and to the compressed copy, the quick states passing on all eleven, the first
  three routes' counts equal to the release tree's. G1 `Y`: the read for G15 corrected eleven statements (below); the profiles, `tools/status_lint.py`,
  the README, COMPATIBILITY, the roadmap and the interface agree on "experimental". G2 `Y`: the common report's main CPU block now has its counts
  (`native`, `interpreted`, cycles and `fallback_present` false on every route, read from the reports of this campaign), `devices` names the mapper,
  the video chip, the PSG and the SCC as C models with no counter, and `honesty.route_warnings` is filled (empty on all 44 routes). G7 `P`: the
  battery SRAM of ASCII 8 and ASCII 16 cartridges is kept (found from the bank values the game writes; [MSX.md](MSX.md#4-controls)); on Xanadu, the
  only panel game with SRAM, bit 5 is found (the documented one), the play route writes it, a fresh process finds it, eleven damaged files are set aside
  whole; not kept: the FM-PAC's SRAM and the MSX2 clock's memory; one game. G8 `Y`: a moving picture is required on the play and long routes, the
  route warnings are reported, and the captures of the long routes were looked at by the specialist (not the owner). G9 `Y`: on a long route all eleven
  games reach play: Hydlide 3 creates a character, chooses a class and walks the overworld on its second long route (the extended level's single
  long route stayed in its Set Up menu), Metal Gear reaches the dock and its first long route goes past the transceiver call (its second stays on the
  call), Xanadu walks its town; pad routes, not full games. G10 `Y`: `tools/banked_vector_selftest.py --machine msx` compiles the 51,328
  SingleStepTests/z80 vectors (22,704 encodings) with the MSX's own build of the generator and expects one wait state per M1 cycle: 51,328 pass, 0
  fail, 0 miss ([CPU_Z80.md](CPU_Z80.md)); the vectors are an emulator's, not hardware captures, and run on a flat test bus, so the region map's
  dispatch is covered by the panel, not by them. G15 `P`: read on 13 November 2026 (30 files and about 70 strings: the MSX pages, COMPATIBILITY,
  CONTROLS, UPSTREAMS, ROADMAP, KNOWN_FAILURES, the eight languages, the profile, the report fields, the adapter and the player); eleven statements
  corrected (F8/F9 said unavailable, Salamander still black in three places, the development-era figures, Metal Gear's held route unsaid, a stale
  "pending", the roadmap's next step, the profile's scope note); left: the published 1.7.3 release notes, whose Salamander sentence a later note
  must correct. G11, G12 and G13 stay `P`, G14 `?`.
- MSX and MSX2 (14 November 2026; branch `spec/msx-175` from `v1.7.4`, panel tree `d0b32436`; the owner's go of the same day to prepare the exit, the
  flip and G14 being his): a new panel of eight cartridges per machine, each with its reason, none dropped for failing, converted at the **extended** level
  (attract, play and an 18,000-frame route) from an empty library and an empty build cache, C-BIOS 0.29a, online covers on, two at a time. MSX: Knightmare
  (plain 32 KiB, the control case), Road Fighter (plain 16 KiB), Space Invaders (plain 16 KiB), Nemesis (Konami), Salamander (Konami SCC), Spy vs Spy II
  (PAL; the probe chooses Konami SCC), Dragon Slayer II - Xanadu (ASCII 8, 8 KiB battery SRAM), Deep Dungeon (ASCII 8, 2 KiB battery SRAM). MSX2: Metal Gear
  (Konami), Space Manbow (Konami SCC, the vertical scroll), Aleste (ASCII 16, chosen by the probe), Hydlide 3 (ASCII 8), Super Daisenryaku (ASCII 16, 2 KiB
  battery SRAM, looks for an FM-PAC), Vampire Killer (Konami), Fantasy Zone II (ASCII 16, scrolling), Heroes of the Lance (ASCII 8, 512 KiB, 8 KiB battery
  SRAM). Two of them first showed a converter fault, fixed in the shared mechanism: the mapper probe now counts the writes to a battery SRAM apart from
  the writes a cartridge would ignore (Deep Dungeon was read as ASCII 16) and no longer takes one register write as evidence when another run made two
  (Super Daisenryaku was read as ASCII 8); the 16 other probed cartridges keep their choice. Results: 16 of 16 converted, 0 interpreted Z80 instructions
  on all 48 routes (from 78.1 to 121.8 million native instructions a long route), each route equal to its fresh reference and to the packed file, the
  quick states passing on all 16; delivered to `Export/Games/MSX` and `Export/Games/MSX2`. G7 MSX `Y`: Xanadu and Deep Dungeon write their SRAM on the
  play route, a fresh process finds it, eleven damaged files are set aside; the FM-PAC and its SRAM are not converted (no MSX-MUSIC model) and the MSX2
  clock's battery memory is not kept (the owner's decision of 14 November 2026), both stated as limits. G7 MSX2 `P`: the MSX2 runs the same SRAM code, but
  no MSX2 game of the panel selected its SRAM on its routes (Super Daisenryaku and Heroes of the Lance have battery SRAM). G8 `Y`: the captures of every
  route were looked at by the specialist (not the owner). G9 `P` (from `Y`: this panel is deeper than the last): thirteen of the sixteen long routes reach
  play; Deep Dungeon stays in its name entry (where it writes its save), Super Daisenryaku in its map setup, Heroes of the Lance at a question of its menu,
  whose Japanese text C-BIOS draws with the wrong characters ([MSX.md](MSX.md#5-known-c-bios-failures)). G12 `Y`: eight a machine, the plain, Konami,
  Konami SCC, ASCII 8 and ASCII 16 boards, battery SRAM, NTSC and PAL, none dropped. G13 `Y`: the sixteen converted again on a Debian 13 PC with the
  system GCC 14.2 from the same tree, one at a time through the machine's job slots, the ROM copied in for the step and deleted after: every report field
  compared is equal to Windows on every route (21 a route: the native, guarded, halt and interpreted counts, the interpreted cycles, the frames, the input
  script and its events, the frame trace, the RAM, VRAM, picture and sound hashes, the sound samples, the interrupts, the reference, frame-row and packed-row
  equalities, the liveness), and the mapper, standard and learning counts too; Knightmare's Linux export was opened in its window on a virtual display (no
  screen), titled "Native code", and drew its title screen. G15 `Y`: read on 14 November 2026 (MSX.md, COMPATIBILITY, CONTROLS, ROADMAP, KNOWN_FAILURES,
  UPSTREAMS, the release notes, README, INDEX, the profile, the report's strings and the option notes in the eight languages); corrected: the vectors said
  not run (MSX.md), "no game other than section 3", the published 1.7.3 notes' Salamander sentence (already corrected by the 1.7.4 notes, so the line
  of the 13 November entry above is stale), SRAM said not converted (COMPATIBILITY, the option notes), the MSX2+ said not converted or in development
  (COMPATIBILITY, ROADMAP, MSX.md), a `.dsk` said refused (KNOWN_FAILURES), the Z80 vectors' machines (UPSTREAMS), the option notes' "instructions seen
  running" (the cartridge and the BIOS are translated ahead of time; RAM code is learned). G16 `-`: path sharing is declined on the panel's evidence (the
  owner's rule of 14 November 2026, `DECLINED['path_sharing']`): the only RAM code its sixteen games run is the BIOS hooks they write, `C3 nn nn C9` (a
  jump into the cartridge, then a return), 1 to 4 windows a game and 259 on Hydlide 3 (a hook table), whose bytes are in no cartridge, so every record
  holds 0 paths; the 0 to 49,521 instructions a game's first conversion interprets are C-BIOS's start-up code (about 24,700 on most games) and those hooks; a received path
  would add no native instruction and save no pass. The sharing code written for them is parked on `spec/msx-175-sharing-parked`. A scratch run of
  `registry_problems` with the status set to `supported` finds nothing for `msx` and `msx2` (not committed: the flip and G14 are the owner's).
- MSX and MSX2 (14 November 2026, G14 and G1; branch `spec/msx-exit-175`): G14 `?` to `Y`: the owner played the six games of his checklist
  (Knightmare, Salamander, Dragon Slayer II - Xanadu (MSX), Metal Gear, Space Manbow, Aleste (MSX2)), the panel's exports, and decided the exit: « Donc, je viens de tester les jeux MSX1 et MSX2, ça marche impeccable. Tu peux les sortir de l'expérimental. » G1 stays `Y` with the status now `supported` in `retrorecomp/systems/msx.py`
  (the MSX2+ stays `experimental`), the option notes of the eight languages, MSX.md, the README, COMPATIBILITY, INDEX, ROADMAP, CONTROLS and the
  agents' guide; `tools/status_lint.py` and `tests/test_machine_registry.py` agree on the real profiles (the supported tier included: Linux
  witnessed, risk cases, path sharing declined on the evidence, no gate `N`).
- MSX2+ (13 November 2026; experimental profile `msx2plus`, the third profile of the MSX family, branch `spec/msx2plus-174`): G1 `P`: the
  profile is declared experimental and `tools/status_lint.py` agrees; not offered in a release yet. Every other gate but G16 is `?`: no panel has run.
  G16 `-`: the MSX2+ shares no paths and is not in `SHARED_SYSTEMS`. Scope and the five measures: [MSX.md](MSX.md#9-the-msx2-msx2plus).
- MSX2+ disk panel (13 November 2026, evening; branch `spec/msx2plus-disk-174`, panel approved by the lead): Arc, Quinpl, Nyancle Racing,
  Sonyc, Laydock 2 - Last Attack, F-1 Spirit 3D Special, Golvellius II and Xak III - The Tower of Gazzel (four single-disk and four multi-disk
  games), converted at the **extended** level (attract, play and one long route of 18,000 frames) from an empty library, two at a time, online
  covers on, with the owner's own MSX2+ firmware of one machine (main ROM, sub-ROM and disk ROM of a Panasonic FS-A1WSX). G2 `Y`: the
  common report's main CPU block has its counts on every route, `devices` names the disk interface (the disk ROM and the TC8566AF) in the
  cartridge's place, the V9958 and the PSG as C models with no counter (seen in a conversion after `34994e59`; the panel's reports, made before,
  name a plain mapper there), `honesty.route_warnings` is filled (empty on all 24 routes), and `disk_writes` says what the game wrote. G3 `Y`:
  0 interpreted Z80 instructions on all 24 routes; the first conversion learns (between 0 and 40.5 million interpreted instructions in that
  pass, counted and reported). G4 `Y`: each route equals its fresh reference run. G5 `Y`: each route of the delivered, packed file equals the
  native run. G6 `Y`: the quick states pass in fresh processes on all eight (layout `msx-state-5`, with the controller and the disk in the drive).
  G7 `P`: no panel game writes to its disks on its routes; the write path is proven on an authored disk (`tools/msx_write_disk.py`, our own boot
  sector, no game data): converted as a game, it writes, the copy is kept beside the game, a fresh process starts from it, a copy of the wrong
  size is ignored and kept, the embedded disks never change, and the copy differs from the image in the one sector written (its 512 bytes, every
  other byte identical); `tools/msx_fdc_selftest.py` checks that a write changes exactly the sectors it is given (21 checks; a controller that
  ignores the terminal count on a write fails 7). Cartridge SRAM uses the MSX2's code, not checked on an MSX2+ game. G8 `Y`: a moving picture is required on the play and long routes, the route warnings
  are reported, and the long routes' captures were looked at by the specialist (not the owner). G9 `P`: six of the eight reach play on their
  long route (Arc, Quinpl, Laydock 2, F-1 Spirit 3D Special, Nyancle Racing after its name entry, Sonyc for a stage before its password
  screen); Golvellius II stays in its Japanese intro, and Xak III stops on "SET DISK 3 AND PUSH SPACE PLEASE", which the route's fixed disk
  changes (frame 6,000, then every 3,000) do not answer. G10 `Y`: the MSX2+ is built with the MSX's own generator build (`MSX_MACHINE`), whose
  51,328 SingleStepTests/z80 vectors pass (the MSX column). G11 `P`: one openMSX comparison of the V9958's horizontal scroll (Family Stadium,
  [MSX.md](MSX.md#9-the-msx2-msx2plus)), with an open difference on R#1; the disk controller is compared with nothing independent. G12 `P`: eight
  disk games, varied (shooting, racing, puzzle, role-playing, one to several disks), none dropped for failing, at the extended level only; one
  firmware; no cartridge game on this panel; not compared on Linux. G13 `?`: no Linux run. G14 `?`: no owner verdict. G15 `P`: read for this
  step (MSX.md section 9, COMPATIBILITY, UPGRADES, the profile's scope note, the report's device names); one statement corrected (the report
  named a plain cartridge for a disk game); the full read of every page and string for the MSX2+ is to do.
- Commodore Amiga 1200 (16 November 2026; branch `spec/a1200-exit-178`): **G14 moves from `?` to `Y`** on the owner's play test of the eight installs of the checklist (Slam Tilt, Pinball Illusions, Alien Breed 3D, Fears, Banshee, Super Stardust, Chaos Engine, All New World of Lemmings), converted by the 1.7.7 candidate (`rc-177` at `35ac18c9`) and delivered in `Export\Games\Amiga 1200`: « Je viens de tester les huit jeux Amiga 1200, ça marche impeccable, tu peux le sortir de l'expérimental. » **G12 moves from `P` to `Y`**: the two installs named in 1.7.6 (Pinball Illusions, Alien Breed 3D) were converted again on that tree, passed every check and were played. **G16 stays `?`**: its paths are not shared for now, on his word of 15 November 2026 (« on n'active pas le partage de chemin encore. On verra si c'est pertinent. Pour l'instant, ça n'a pas l'air de l'être. »), and a measure with and without received paths is to be done later, not in this exit (16 November 2026: « pour le partage des chemins, on fera des tests plus tard. Faudra qu'on fasse des tests quand même. »). **G1 moves to `Y`**: the profile is declared `supported` and `tools/status_lint.py` agrees on the README, the compatibility page, the release notes and the interface strings in eight languages. The Amiga 1200 **leaves the experimental status: it is supported from 1.7.8**. G9, G10, G11 and G15 stay `P`, with their evidence and what is missing named in [its section](#commodore-amiga-1200-evidence-behind-its-column-15-november-2026); no gate is relaxed. Replayed on the exit branch (16 November 2026, the standard level, from empty scratch libraries): Slam Tilt, Pinball Illusions, Alien Breed 3D and All New World of Lemmings on Windows (llvm-mingw) and on WSL Debian 13 (GCC), every field of every route equal between the two and equal to the conversions the owner played; only the report's status reads `supported`. The scope is in [AMIGA.md](AMIGA.md#leaving-the-experimental-status-16-november-2026): no game played through, no hardware fidelity or latency claimed, the interpreted share counted and shown.
- Commodore Amiga 1200 (16 November 2026; branch `spec/a1200-share-179`): **G16 moves from `?` to `P`**: it shares its paths from 1.7.9 as the experimental tier of the base, like the Amiga 500, on the owner's word: « Je préfère que tu mettes en place directement le partage de chemin pour l'Amiga 500 et 1200. Ça permettra à tous les joueurs d'utiliser les temps de jeu des autres utilisateurs, même si à la recompilation du jeu, on n'a rien découvert. » (the measure with and without received paths cancelled). On both Amigas the record now also holds the instructions the player's game ran on the interpreter in play (F12) that a passing conversion made native. Proof on All New World of Lemmings ([AMIGA.md](AMIGA.md#shared-paths-179)): a receiver given the sender's paths, which held the owner's 219 played instructions, had all 219 native and 10,104 more native instructions than a control with nothing, with the same traces, the same interpreted counts and the same wall time. `P` like the other machines of that tier: no path qualified in the base yet.
- Nintendo 64 (15 November 2026, afternoon; branch `spec/n64-176`): **G14 moves from `P` to `Y`** on the owner's play test of the eight exports of the checklist (the owner-acceptance table below), **G16 from `?` to `-`** (sharing declined on his decision, the gain being small, not nil), and the Nintendo 64 **leaves the experimental status: it is supported from 1.7.6**, on Arthur's word: « Ça me paraît bien faible pour partager les chemins. Si on a que 10% de gain max, […] on va sortir Nintendo de l'expérimental, mais on va pas partager les chemins. » The matrix is otherwise unchanged (`Y` on G1 to G9, G12, G13, G15; `P` on G10, krom's tests with the core's failures named; `?` on G11). The flip, simulated before (`registry_problems` on the real profile), asks for nothing more. The scope and limits are in [NINTENDO_64.md](NINTENDO_64.md#supported-from-176-15-november-2026): no game played through, no hardware fidelity or latency claimed, the interpreted share counted and shown.
- Nintendo 64 (15 November 2026; branch `spec/n64-176`, experimental): **G1 to G9, G12, G13 and G15 move to `Y`, G10 to `P`**; G14 stays `P`, G11 and G16 stay `?`. The evidence is [its section](#nintendo-64-evidence-behind-its-column-15-november-2026): a panel of eight PAL cartridges at the Extended level, none dropped, every route equal to the core's pure interpreter frame by frame on Windows and byte for byte equal on a Debian 13 PC; every interpreted instruction listed with its class (two coverage gaps found that way and fixed: the run after an MFC0 and TLB-mapped code); the quick state continued with its sound and 16 damaged states refused; every save kind read back by a fresh process; krom's 114 CPU tests, 90 passing on the core's interpreter, the failures named. G14 waits for the owner's play test of the panel, G16 for his decision on sharing (the panel shows that received paths would add native code). No hardware fidelity, gameplay coverage or latency is claimed.
- MSX2+ (14 November 2026, night; branch `spec/msx2plus-supported-176`): **G14 moves from `?` to `Y`** on the owner's play test of the six games of the checklist (the owner-acceptance table below), and the MSX2+ **leaves the experimental status: it is supported from 1.7.6**, on Arthur's word (« Oui, sors-le »). **G1 moves to `Y`**: the profile is declared `supported` and `tools/status_lint.py` agrees on the README, the compatibility page, the release notes and the interface strings in eight languages; `registry_problems` finds nothing for the real profile. The matrix is otherwise unchanged: `Y` on G1 to G8, G10, G12 to G15, `P` on G9 (route depth), G11 (two openMSX comparisons, no independent emulator on the panel) and G16 (the experimental tier of the base).
- Sony PlayStation (15 November 2026; branch `spec/psx-176`): on the final panel pass of the night (tree `6a5d9e9b`) and the Debian 13 witness, **G3, G4, G5, G8, G9, G12 and G13 move to `Y`**, **G7 to `Y`** (WipEout 2097 on a route and the owner's own Gran Turismo 2 save, each read back in a fresh process), **G11 to `P`** (ps1-tests through the BIOS) and **G16 to `P`** (shared paths, on the owner's « Oui, elle partage » of 14 November). **G14 moves to `Y`** on the owner's play test and the PlayStation **leaves the experimental status: it is supported from 1.7.6**, on Arthur's word (« Oui, sors-la »). **G1 moves to `Y`**: the profile is declared `supported` and `tools/status_lint.py` agrees on the README, the compatibility page, the release notes and the interface strings in eight languages. `P` stays on G2 (the report gates of release_check not run on its reports), G6 (a truncated state only), G10 (the GTE vectors not through native steps), G11, G15 (read in the code, not in a window) and G16 (the experimental tier of the base).
- MSX2+ panel of 1.7.6 (14 November 2026, night; branch `spec/msx2plus-176`): **G7, G12, G13 and G15 move to `Y`**; G9 and G11 stay `P`,
  G14 `?` (the owner's). The panel: four cartridges on C-BIOS 0.29a (Family Stadium Professional Baseball, the V9958 scroll and MSX-MUSIC;
  Pachipro Densetsu, ASCII 8; The Goonies R Good Enough, Konami SCC; Dragon Slayer II - Xanadu, ASCII 8 with battery SRAM, the G7 game) and
  five disk games with the owner's FS-A1WSX firmware (Laydock 2, F-1 Spirit 3D Special, Xak III, Quinpl, Golvellius II), none dropped, at
  the extended level: all 27 routes 0 interpreted, equal to the fresh reference, the packed file equal, the quick states equal in a fresh
  process. G7 `Y`: Xanadu's play route writes its SRAM, the memory survives a fresh process and damaged files are set aside, on the MSX2+;
  disk writes as on 13 November. G12 `Y`: nine games, cartridges and disks, every mapper the profile reads but ASCII 16 without SRAM
  (Family Stadium is ASCII 16), one to four disks. The Goonies R Good Enough first came out as ASCII 8 (a blue screen): the mapper probe
  did not count the SCC's sound registers as the Konami SCC's; fixed (`05f8d828`), and the 13 mapper cartridges of the 1.7.5 MSX and
  MSX2 panels, probed again, keep their mappers. G13 `Y`: the nine converted again on a Debian 13 PC (system GCC 14.2, the branch's tree
  at `05f8d828`, one job slot each, the ROM, the disks and the firmware copied in for the step and deleted after): the 21 fields of every
  route equal Windows on all 27 routes; the learning counts differ on four disk games only because their Windows build folders had already
  learned in earlier runs (F-1 Spirit 3D Special, with none, equal there too). G9 `P`: the long routes reach play on six of the nine,
  Xak III answers its disk request and loads disk 3, Golvellius II stays in its intro, Pachipro Densetsu in its birth-date entry. G15 `Y`:
  read for the 1.7.6 changes (MSX.md section 9 with MSX-MUSIC, kanji, disk requests and shared paths, COMPATIBILITY, UPGRADES, the
  profile's scope note and option labels, the report's devices and BIOS sources); the five measures are kept apart and no page claims
  exact fidelity or latency. The flip to `supported`, simulated (`registry_problems` with the status changed, nothing committed), asks
  for nothing more once the five risk cases of `tools/campaign-risk-cases.json` are in. The checklist for the owner is below.
- MSX2+ disk requests (14 November 2026; branch `spec/msx2plus-176`): G9 stays `P`, with Xak III's stop removed. The routes and the player answer
  a game's disk requests (`native/media_request.h`: a lone read of the boot sector, no other drive command for 60 frames before and after,
  the picture still for 16 frames) with the next disk of the set, instead of 1.7.5's fixed changes at frames 6,000, 9,000... The rule was
  measured first: on the first disk of each multi-disk game of the panel (F-1 Spirit 3D Special, Golvellius II, Laydock 2, Xak III; 18,000
  frames each), it fires only on Xak III's five reads of its "SET DISK" screen, none elsewhere. Converted at the extended level with it
  (owner's FS-A1WSX firmware), Xak III's long route gets disk 2 at frame 16,759 and disk 3 at 16,963 (its request was for disk 3; disk 2 was
  refused by the game and the rule moved on) and loads from disk 3 until the route ends; Golvellius II stays in its intro (it asks nothing
  there). 0 interpreted and equal to the reference on all six routes. Eleven fixtures check the rule (`msx_hardware_checks.c`).
- MSX2+ path sharing (14 November 2026; branch `spec/msx2plus-176`): **G16 moves from `-` to `P`**, like the other experimental sharers. The
  MSX2+ shares its paths (Arthur's decision of 14 November 2026, « Oui, il partage ») as schema 3 records of the experimental tier: the RAM
  windows a conversion learned, as offsets in the cartridge (`rom`) or in the disks (`disk1` ... `diskN`, keyed by the disk set; the BIOS image
  they were found with, disk ROM included, is stated and hashed), `retrorecomp/msx_knowledge.py` on `retrorecomp/path_records.py`. The MSX and
  the MSX2 keep `-`. Step 0 (Quinpl, quick level): of the 561 windows its first conversion learned, 540 are in the disk's bytes and 21 are built
  in RAM; with the 540 received before learning, its first pass interpreted 957 Z80 instructions instead of 2,043,837 and the conversion took
  31.5 s instead of 40.4 s. The proof (Quinpl, one disk; Laydock 2 - Last Attack, two disks; standard level, the owner's FS-A1WSX firmware;
  Windows): converted from an empty library (A), their records exported to a version 3 knowledge file by the real exchange code, the library,
  banks and build cache emptied, the file imported, converted again (B): the first pass interprets 7,076 instructions instead of 8,713,776
  (Quinpl) and 536,934 instead of 2,795,253 (Laydock 2: its 124 windows built in RAM stay private, counted), the translation and learning
  phase 16.4 s instead of 20.7 s and 16.0 s instead of 19.0 s, every route at 0 interpreted and equal to the reference in A and in B. Safety
  (C): an imported record of 400 random places of the same disks (windows no route runs as code) changes nothing: 0 interpreted, every route
  equal to the reference. **The limit, stated:** what sharing buys is time and a smaller first pass, not a better game: the delivered
  executables of A and B pass the same checks. A received window is shared again only once this player's own conversion learns it (the
  Master System's rule): B's own record holds only what it learned itself. Not yet: the Linux half of G16, a path qualified by another
  player's conversion.
- Nintendo 64 (7 November 2026; experimental profile, branch `spec/n64-171`): G1 `P`: the profile is declared experimental and
  `tools/status_lint.py` agrees; the machine is offered to players in 1.7.1 (the owner's go of 8 November 2026, in the owner-acceptance table). G2 `P`: the common report v2 of every conversion, the VR4300 counted in
  instructions (a jump and its delay slot as one). G3 `P`: Super Mario 64 and Ocarina of Time (PAL) converted at the Standard level,
  5.6 to 6.0 % of the instructions interpreted on the routes, 0 guard misses. G4 `P`: every route of both conversions is identical,
  frame by frame (picture, sound, RDRAM, CPU registers), to a fresh reference on the core's pure interpreter; native plus interpreted
  equals the reference's count but the one instruction in flight at the frame's end. G5 `P`: the compressed copy too. G6 `P`: the
  state saved on the main route must continue CPU, RDRAM and picture for 400 frames in a fresh process, or the conversion is refused; the
  sound samples are not compared and differ on all 400 frames. Measured on Windows on three games, on Linux on one. G7 `P`: Ocarina of Time's SRAM, a file created in one process found by a fresh one; EEPROM, Flash and paks not exercised. G8 `P`: a moving picture is required on the main route. G9 `P`: Mario Kart 64's main route races; at the Extended
  level Super Mario 64 (6,000 frames) and Ocarina of Time (16,800 frames) play routes of their own that reach play, equal to their
  references (Ocarina of Time: 16,489 guard misses on that route, run on the interpreter and counted); other games' generic routes
  may stay in menus. G14 `P`: the owner played three games and gave his go for the experimental opening (owner-acceptance table); not an exit. G13 `P`: Mario Kart 64 and Super Mario 64 converted on a Debian 13 PC (GCC, integrated graphics, 8 November 2026): the
  traces of their routes byte for byte equal to Windows'; profile Linux `witnessed`, not played there. Nothing is
  measured against vectors or against hardware; no speed, hardware fidelity or latency is claimed
  ([NINTENDO_64.md](NINTENDO_64.md#3-the-five-measures)).

- Amiga (8, 13 and 14 November 2026; opened to players as experimental in 1.7.0, supported from 1.7.5 on the owner's G14 of 14 November 2026): the evidence of each letter is in
  [its section](#commodore-amiga-evidence-behind-its-column-8-november-2026). G1 `Y`: the profile, `docs/AMIGA.md` and `tools/status_lint.py` agree.
  G2 to G8 `Y` on [the panel of 13 November](#commodore-amiga-the-panel-of-13-november-2026) (eight installs and Panza Kick Boxing for the saves, extended level,
  tree `be3f4483`, llvm-mingw): a v2 report read by the common reader; 0 interpreted instructions outside the player's Kickstart on every route, the Kickstart's
  listed (19 or 7 a route); every frame of every route equal to the fresh interpreted reference of the same machine, the compressed copy too; states with a
  checksum and the install's identity, continued for 600 frames in a fresh process, 17 damaged ones refused; Panza Kick Boxing's boxers saved on a player's route,
  kept, read back and kept across a second conversion; moving pictures on every route, the last change of each long route within 250 frames of its end. The
  reference is the same machine's interpreter, not an independent oracle. G9 `Y`: the long route reaches play on 7 of the 8 and on Panza Kick Boxing; Monkey
  Island 2's ends in its opening, named with its reason in `route_warnings`. G10 `P`: `tools/amiga_vector_selftest.py` (6,762 vectors of the four fixtures: the native steps equal Moira's interpreter on
  6,762, Moira agrees with the vectors on 6,440 and differs on 322, all in named families, 0 unexplained); Moira is the Amiga's own reference CPU. G11 `P`: six
  installs compared picture by picture with an independent emulator running the real WHDLoad (private); not a fidelity claim. G12 `Y`: the eight named
  installs of the owner's rule, none dropped. G13 `Y`: the Debian 13 PC (GCC 14) gives the same CPU, RAM, picture, PCM and trace digests as Windows on every route of Lotus 2, Rick Dangerous, Blood Money, Apidya, Lemmings, Pinball Dreams and Shadow Of The Beast (tree `96a70fa0`) and of Another World, Lemmings and Monkey Island 2 (tree `be3f4483`, the Kickstart installs included); not played on Linux. G14 `Y`: the owner played the six installs of his checklist on 14 November 2026 and decided the exit (« Oui, sors-le »). G15 `Y`: the audit of
  8 November and an exported game read in its window on 13 November, title included ("Interpreter fallback" on a Kickstart install). G16 `P`: the Amiga shares
  its paths as the experimental tier of the base (14 November 2026, the owner's decision); on Lotus 2, Lemmings and Another World a receiver of
  another player's paths saved no pass and added little native code on its routes, and the gain beyond them was not measured on the Amiga. Not yet: Kickstart 3.x installs, ADF, the Amiga 1200 ([AMIGA.md](AMIGA.md#3-the-five-measures)).

- Game Boy Advance (6 November 2026, tree of `spec/gba-170`): the machine is prepared to open as experimental in 1.7.0. G3 and G4 are `P`:
  six cartridges converted (Pokémon Emerald, Mario Kart Super Circuit, The Minish Cap, Pokémon Mystery Dungeon Red, Super Mario Advance 2 and
  Golden Sun) and equal to the engine's own interpreter on the final picture, the guest's cycle count, a hash of the memory and a hash of
  the CPU registers over 600 and 3,600 frames; five have 0 interpreted instructions on those scenarios and Golden Sun 17.7 million of its
  own code that has no copy in the cartridge (counted and reported); the interpreter is the engine's, not an independent oracle, and
  `release_check.py` was not run. G5 `P`: the packed players run 600 frames hidden with return code 0; not the packed replay of the tools.
  G6 `P`: a quick state saved and loaded in the same process gives the same picture; no fresh-process check. G7 `P`: the four authored
  save tests pass and the battery file is written; no game save was loaded back by a check of ours. G8 `P`: six packed players draw and
  play sound for 600 frames; G12 `P`: that is the panel (six cartridges, and four more on 7 November 2026 with no interpreted instruction on the scenarios; not the owner's perimeter). G11 `P`: the authored hardware tests (jsmolka,
  MIT) pass with the staged patches; no external emulator. G14 `P`: the owner played the delivered Sonic Advance on 5 November 2026 and
  then the series of delivered cartridges on 6 November 2026 ("it works perfectly"), and the rebuilt Golden Sun and Minish Cap with
  guarded native RAM code on 7 November 2026 ("it works perfectly"); play trials of the exports, not a decision to
  leave the experimental status. G10 is `P`: `tools/gba_vector_selftest.py` runs SingleStepTests/ARM7TDMI (a model's behaviour, not
  hardware) on the patched engine, 93.96 % of the interpreter's 2,250,000 vectors and 91.08 % of a sample of 45,000 for the generated
  code, the rest being coprocessor instructions (not in generated code), multiply carries and R15 operands, and a tail of 385 and 11 that
  was decoded on 7 November 2026 and is two classes: ARM `LDM`/`STM` with the user-bank bit and write-back in a banked mode (unpredictable in the
  architecture) and Thumb block transfers with an empty register list (a hardware behaviour the engine does not model); unexplained: 0. G11 also rests on `tools/gba_hardware_selftest.py`: the eight self-checking
  authored suites pass. G13 is `P` (6 November 2026): the same six cartridges were converted on a Debian 13 PC from the tree to merge (the commit
  `31e39aee` plus `linux = 'witnessed'` as the only change; the commit between is a documents page), three passes from an empty library: on both
  scenarios the generated code equals the engine's interpreter, and the final picture hash and the guest's cycle count equal the Windows ones, 12
  scenario runs of 12 ([the section of the page](GAME_BOY_ADVANCE.md#the-linux-witness-of-the-six-cartridges-6-november-2026)). On 7 November 2026 the Linux players of Golden Sun and Metroid Fusion
  were also run under Xvfb with the key script of the Windows runs: the picture at frame 1,800 and the sound counts equal the Windows ones (a scripted run, which the owner
  accepted as the G13 witness; nobody heard the sound).

- Game Boy Advance (12 November 2026, tree of `spec/gba-173`, Windows only; **no letter of the matrix is moved by this entry, and G15 stays as it is**).
  What is new: a conversion that differs from the interpreter, or whose native run errored, fails (`validation_failures`); the bridge proposes its callees, so a first
  conversion from an empty library reaches 0 interpreted instructions in 2 to 5 passes on Advance Wars, Golden Sun, The Minish Cap and Pokémon Emerald, native equal to
  the engine's interpreter on both scenarios of each ([GAME_BOY_ADVANCE.md](GAME_BOY_ADVANCE.md#the-verdict-is-enforced-and-a-first-conversion-converges-faster-12-november-2026-173));
  Thumb `STMIA`/`PUSH` with an empty list store the value of the hardware (vectors of the class 138 to 76 and 4 to 2; the loads remain, G10 stays `P`); the caps of the RAM code are counted
  in the report. **Proposals for the owner to decide, with the evidence (letters are his):**
  G6 *States* stays `P`: a state saved in one process and loaded by a *new* process gives the same picture on Metroid Fusion (two routes, a control that differs, 0 interpreted
  instructions); not shown by a check of ours: a damaged state refused and a missing state creating nothing, and only one cartridge. G7 *Saves* stays `P`: Sonic Advance 2 writes
  its 64 KB Flash save in one process and a second process shows the saved game (the file is identical after; a run with no save asks for the language); EEPROM and SRAM
  were not exercised this way, and only one cartridge. G9 *Route depth* `?` to `P`: four scripted routes reach play with 0 interpreted instructions at 10,000 to 30,000 frames
  (Advance Wars to Nell's lesson on the first Field Training map, Wario Land 4 to Entry Passage in play, Metroid Fusion to Samus under control after the opening story, the Sonic Advance 2 pair);
  they are the first minutes, not a level, a boss or an owner's perimeter. G16 *Shared hints* `-` to `P` **when the release switches sharing on**: the record is numeric (offsets and
  lengths of one exact cartridge, no bytes), rows a conversion receives are rechecked by its own run and are never saved nor shared, and a failed conversion with received rows
  is converted again without them (tests; a forced-mismatch proof; `tools/gba_bogus_rows_audit.py` on the Minish Cap with 2,000, 150 and 20 invented rows: the generator hangs on wrong roots, the converter stops it after 300 s and converts again without them, native equal to the interpreter, no bogus row in the player's paths or the promoted record; 230 in-area roots accepted by the generator also pass); no path is qualified yet, the site's limits are not deployed
  and nothing was shared, the CPS-1, X68000 and PC Engine precedent. Not done: the Debian witness of this tree, the quiet-PC cost of a frame, a conversion of any other cartridge.

- Game Boy Advance (14 November 2026, tree of `spec/gba-175`; Windows, and a Debian 13 PC for the four cartridges of the panel; the status is **not** changed and G14 is the owner's alone):
  **G1, G2, G4, G7, G9 and G15 move from `P` to `Y`** (proposals in the owner's matrix, each with its evidence and its limit; he may take any of them back); G3, G5, G6, G8, G12 and G13 stay `Y`; G10, G11, G14 and
  G16 stay `P`. Six cartridges were converted again on this tree from an empty library with online covers (Golden Sun, Mario Kart Super Circuit, The Minish Cap, Crazy Taxi, with F-Zero: Maximum Velocity and Pokémon Emerald as extra evidence): native
  equal to the engine's interpreter on both scenarios of each, 0 interpreted instructions at the end, the compressed copy equal to the player as built
  ([GAME_BOY_ADVANCE.md](GAME_BOY_ADVANCE.md#leaving-the-experimental-status-what-175-adds-14-november-2026)). G1 and G15: this page, the compatibility page, the README, the upstream page, the interface notes in eight languages, the
  profile and the report read for this gate, three statements corrected, everything says `experimental`, "exact" and "zero latency" nowhere. G2: the report names the picture unit and the sound unit as hardware devices, carries `route_warnings` and the
  scope with no universal zero-fallback claim (read through `report_schema`); the native instruction count is not available from the engine and stays unset. G4: the sound is in the comparison with the interpreter (a hash of every
  mixed sample and their count, three engine patches), with the picture, the cycles and the memory and CPU hashes; the interpreter is the engine's own, not an independent oracle. G7: all four chips are read back by a fresh process
  (Flash 64 KB on Sonic Advance 2, Flash 128 KB on Pokémon Emerald, EEPROM on The Minish Cap, **SRAM on F-Zero: Maximum Velocity**) and five damaged forms of a save never stop a game; a save larger than its chip stopped the game before and is set
  aside now (a bug found by the check). G6 (stays `Y`): the quick state has a checksum, so **eight of eight** damaged forms are refused (one byte in the middle was accepted before). G9: authored routes of 4,200 to 12,000 frames on the four
  cartridges, twelve pictures of each along the route from the delivered file, read: play is reached (Isaac walking in Vale, a kart in a race, Link walking about his house, a taxi in the city), the first minutes and a long run, **not a level won**,
  and not the pseudo-random 18,000-frame level of the other machines (a scenario of that length would need an interpreter replay of hours); three routes run millions of interpreted instructions, counted. G13: the eight routes (and their twelve
  pictures each) give the same pictures and counts on Debian as on Windows, with the Golden Sun states, the damaged states and the Minish Cap save checks. G10 stays `P`: the independent vectors agree on 94 % of the interpreter's, the rest is coprocessor,
  unpredictable and modelling classes; G11 stays `P`: authored hardware tests only, no external emulator; G16 stays `P` as in the leaving of the other machines (the sharing of 1.7.3 as it is, nothing uploaded by this work). Not shown: gameplay
  validation beyond the routes, hardware fidelity, physical latency (`tools/gba_frame_cost.py` has not made its quiet-PC pass), the sound itself (counts and hashes, not listening).

- Game Boy Advance (13 November 2026, tree of `spec/gba-174`; Windows, and a Debian 13 PC for four cartridges): a panel of **four** cartridges (the maintainer's decision of 13 November: Golden Sun, Mario Kart Super Circuit, The Minish Cap, Crazy Taxi: Flash 64 KB and EEPROM, affine layers, code run from RAM, a software 3D game) and eight more as extra evidence, not panel members
  (Pokémon Emerald and Ruby: Flash 128 KB and the clock; Metroid Fusion, Mega Man Zero 3, Wario Land 4: SRAM; Sonic Advance 2; Advance Wars; Mario & Luigi), 4 to 16 MB, converted from an empty library, none dropped, native equal to the engine's interpreter on both scenarios of each (picture, guest cycles, memory and CPU hashes), 0 interpreted
  instructions at the end ([GAME_BOY_ADVANCE.md](GAME_BOY_ADVANCE.md#the-panel-of-four-eight-more-cartridges-the-delivered-file-the-refusals-and-the-routes-13-november-2026-174)). The matrix moves
  in letters, each with its evidence (the owner may take any of them back): G3 *Native code* `P` to `Y`: 0 interpreted instructions on the final scenarios of the twelve, the four
  routes that run millions of instructions listed with their counts; G5 *Delivered file* `P` to `Y`: the conversion runs the player as built, then the compressed copy it
  delivers, and publishes only if the last picture, the frame count and **every frame's row** (picture hash, sound hash, audible) are equal (12 of 12); G8 *Liveness* `P` to `Y`: the
  rows say that picture and sound change (1,028 to 2,905 different pictures in the generic scenario, 2,514 to 3,433 frames with a sample of 3,600; nobody listened); G6 *States*
  `P` to `Y`: a state saved by one process is loaded by a fresh one (Golden Sun and Metroid Fusion on Windows, Golden Sun on Debian), seven of seven damaged forms of the file that
  break its container are refused and a missing state creates nothing (the eighth, one byte flipped in the middle of the memory, is accepted: no checksum); G12 *Panel* `P` to `Y`:
  the four, none dropped (two of the four save chips; Flash 128 KB, the clock and SRAM only through the extra evidence); G13 *Cross-OS* `P` to `Y`: on Debian the conversions of Golden Sun, Mario Kart, Pokémon Emerald and The Minish Cap end with the same counts and the delivered players give
  **the same last picture as Windows on their routes** (4,500, 4,500, 9,600 and 10,000 frames; 34, 0, 9,733,707 and 13,910,846 interpreted instructions, equal), the Golden Sun state and refusals checks and the Emerald save pass there too; G9 *Route depth* `?` to `P`: one route per cartridge
  reaches play (twelve), the first minutes, not a level or a boss, four of them through millions of interpreted instructions (code the two scenarios never reach); G16 *Shared hints* `-` to
  `P`: the path sharing of 1.7.3 (numeric records, received rows rechecked and never saved, a failed conversion converted again without them, the generator's time limit). **Not moved:**
  G7 *Saves* stays `P` (three chips of four: Flash 64 KB on Sonic Advance 2, Flash 128 KB on Pokémon Emerald, EEPROM on The Minish Cap; SRAM was tried on Mega Man Zero 3 and its route does not reach a save point),
  G4 stays `P` (the sound is not compared with the interpreter's), G10 and G11 stay `P`, G2 and G15 are not examined, G1 and G14 are the owner's. No gate is `Y` by an agent's word: these are proposals in the owner's matrix.

- CPS-1 (29 October 2026): G3, G8 and G9 moved from `P` to `Y` on the evidence of the section below (26 sets, one tree). G9 `Y`
  rests on captures inspected by the specialist agent, not by the owner. G10 is `Y` since 1.6.6 (both CPUs replay independent vectors; the Z80 core is corrected in the converter's copy and only the `SCF`/`CCF` X and Y flags
  remain). G11 and G13 stay `P` with fresher evidence (1 November).

- CPS-1 (1 November 2026): the profile is `supported`. G12 moved from `P` to `Y` on the owner's choice of criterion 1 ("every set of
  the perimeter he owns is converted and validated": 26 of 26); the two boards and the 20 mappers the panel does not cover are noted in
  [CPS1.md](CPS1.md#panel-coverage). G14 is `P`: the owner accepted the exit from the experimental status on the evidence, and the play
  trial list is still to do on the 1.6.6 executable (see *Owner acceptance*). G16 is `P`: the paths are numeric, rechecked and retried
  without hints, but no CPS-1 path is qualified yet and CPS-1 stays in the experimental tier of the shared base (a tier of the base, not the machine's status). G13 stays `P`
  (three sets of 26 on Debian 13; interactive play on Linux not witnessed).

- X68000 (1 November 2026): G2 and G9 moved from `P` to `Y` on the evidence of the section below (1.6.6 tree). G9 `Y` rests on the
  four risk cases and on captures inspected by the specialist agent, not by the owner; the thorough level (36,000 frames) was not run.

- X68000 (5 November 2026): the profile is `supported` since 1.6.9. G14 moved from `P` to `Y` on the owner's decision of 5 November 2026
  (quoted in *Owner acceptance*), taken with G10 and G11 still `P`: 22 vectors of undefined decimal arithmetic, and MAME on five games
  with the sound not compared. The Mega Drive stands with G10 `P`, and every supported machine with G11 `P`. The scope and the follow-ups are
  in [the exit section](#sharp-x68000-scope-and-follow-ups-at-the-exit-5-november-2026). G16 moved from `-` to `P` the same day: the owner approved the sharing of the
  X68000's paths in both directions, and the rule of the repository wants a supported machine in the sharing.

- The G5 and G6 rows say "met" where the check exists as a campaign step.
  Only ng, cps1, (since 1.6.5) x68 and (since 1.6.6) md, nes and gb run G5 inside every conversion (sms and gg too, but only
  with the banked engine, see below), and ng, cps1, x68 and (since 1.6.6) nes and gb run G6 inside every conversion. Read G5 and G6
  as "met per conversion" only for those.
- Game Boy (1 November 2026): G5 and G6 `Y` per conversion, G7 `Y`, G8 `P`. G5: after the lockstep comparisons the compressed copy is
  replayed on the same routes and must give the same verdict line (`retrorecomp/gameboy_delivery.py`; [UPGRADES_HISTORY.md](UPGRADES_HISTORY.md#game-boy-the-packed-replay-and-the-liveness-record-166-gates-g5-and-g8)).
  G6: every conversion checks the quick states in a fresh process, and `tools/gameboy_states_check.py` does it on an authored
  cartridge and on Super Mario Land. G7: `tools/gameboy_saves_check.py` on six cartridges written for it ([GAME_BOY.md](GAME_BOY.md)).
  G8 is `P`: the liveness record exists on every conversion, but no campaign of captures was inspected for the Game Boy.
- Game Boy (4 November 2026): G1, G2, G3, G4, G13 and G15 moved from `P` to `Y`; G11 stays `P`. Evidence in [GAME_BOY.md](GAME_BOY.md#the-sixteen-gates-with-their-evidence-167):
  G1 `tools/status_lint.py` shows 0 contradictions and 0 drift items; G2 the report of every one of the twelve campaign games has the SM83's counters per route and the mapper and the sound unit as devices
  that state they are C models, with `hardware_fidelity_validated: false` (like the NES, with no counter for a device that runs no program); G3 no interpreter instruction on any final route of the twelve
  games, the writable code run one by one listed per game (Wario Land II 925,868 instructions, the others 0 to 77,317), the native count and the fallback percentage stay unknown; G4 the CPU,
  memory, picture and sound of native code and interpreter equal over every route of the twelve games at the extended level (the long route over its first 3,600 of 18,000 frames) and, since 1.6.8, on the
  151 of the 152 test ROMs frame by frame plus one documented divergence (`oam_bug` 7, first version, at step 6,717,022); G15 the audit of 3 November repeated on every public line that names the machine (README, documents, eight interface languages, converter strings), no claim of exactness,
  zero latency or hardware fidelity found. Limits: G4 is agreement of two executions of the same machine model, not an independent oracle (G10 is); the long route is compared on its first 3,600 frames;
  the audit is a search of the words of exactness, accuracy and completeness with the matches read, not a reading of every page. **G11** stays `P`: Mooneye passes 94 of 94 applicable tests since 1.6.8 (the state
  after the boot ROM now matches the DMG ABC) and `dmg_sound` 18 of 24, but the three wave-channel tests of each version fail, `oam_bug` `7-timing_effect` gives no verdict and no hardware capture was made.
  **G13** `Y`: Windows and a Debian 13 PC convert the twelve games of the campaign from the same tree (`5ff5595`, quick level, empty library) and give equal per-frame traces (picture, sound, work RAM, program counter) and final
  states on 48 of 48 routes (280,800 frames per system); the generated sources are equal but the embedded resources. Limits: twelve of the 606 cartridges, the quick level, four routes each, no thorough run, no comparison with a console.
- NES (1 November 2026): G2, G3, G4, G7, G8 and G9 moved from `P` to `Y` on the evidence of the section *Nintendo NES: evidence behind
  its column* below (campaign of eight games at the thorough level, delivered-file checks, captures). G9 `Y` rests on pictures
  looked at by the specialist agent, not by the owner. G12, G13 and G15 stay `P`, G14 stays `?`.
- Game Boy (3 November 2026): G8 and G9 moved from `P` to `Y` on the campaign of twelve games of 1.6.7 at the extended level
  ([GAME_BOY.md](GAME_BOY.md#the-campaign-of-twelve-games-167-gates-g8-and-g9)): every game `supported`, full CPU comparison, the
  compressed copy identical, no interpreter cycle, states checked. Play is reached on six games (Tetris, Wario Land II, Mega Man V, Contra,
  Exodus, Veediots); the six others show liveness only (a pause, a first room, menus). The sheets were looked at by the specialist agent,
  not by the owner; not full games.
- Master System and Game Gear (5 November 2026, release 1.6.9): G1, G2, G5, G6, G8, G9 and G15 moved from `P` to `Y` for both columns on the evidence
  of [MASTER_SYSTEM.md](MASTER_SYSTEM.md#the-panel-of-twelve-games-169-gates-g2-g5-g6-g8-g9) (a panel of twelve chosen cartridges, six of each console, converted at the
  extended level with the banked engine and replayed on the delivered file) and its table of the sixteen gates. G2: the report has the mapper, the video chip and
  the sound chip as devices with no counter, the native instruction count of the banked engine, and the reference comparison of the "functions" engine read as what it is (the
  demo route only). G5: the compressed copy matches the fresh reference on 36 routes of 12 games (banked) and its own final pass on 8 games (functions). G6: the fresh-process
  check on the twelve harness builds. G8 and G9: ten of the twelve games reach a screen of the game on the pseudo-random route; **two never start** (Micro Machines, Codemasters
  registers; Shining Force II, cartridge RAM: neither is modelled) and the report now lists such routes in `route_warnings`; Gunstar Heroes ends on the game's own error screen
  on its pseudo-random route (unexplained). Read as of the default (banked) engine: the optional "functions" engine has no quick states, interprets part of one route
  and does not export three of the twelve games (the reference check refuses it) and builds a fourth not at all. The pictures were looked at by the specialist agent, not by
  the owner; pad routes, not full games. **G1** and **G15**: the status and the perimeter are one list on the pages, COMPATIBILITY.md and the README; the audit of the
  words of exactness, accuracy and completeness found three sentences to correct, no claim of fidelity or zero latency. **G13** `Y` (5 November 2026): Windows and a Debian 13 PC convert the twelve games of the panel from the same tree (`e84167e`, extended level, banked engine, empty library, `tools/sega_cross_os.py`) and give equal per-frame traces (picture, sound, RAM and VDP hashes), equal RAM at the last frame and equal final CPU registers on 36 of 36 routes (302,400 frames per system). Limits: twelve of the 258 cartridges, the banked engine only (the "functions" engine was not witnessed), pad routes, no interactive play on Linux, and no comparison of the generated sources. **G11** stays `P`, **G14** stays `?`.
- Game Boy (3 November 2026): G10 moved from `P` to `Y` on two independent pieces of evidence: the 404,358 SingleStepTests vectors on plain memory (402,589 match the
  interpreter, all of the RAM executors'), and the public test ROMs run on the delivered files ([GAME_BOY.md](GAME_BOY.md#the-public-test-roms-of-blargg-and-mooneye-167-gates-g10-and-g11)):
  blargg `cpu_instrs` 11 of 11, `instr_timing`, `mem_timing` 6 of 6, and Mooneye's instruction, interrupt, HALT and timing tests, each with the native code and the pinned interpreter
  equal step by step for the whole run. Limits: `STOP` is covered by neither (the vectors differ by convention, `cpu_instrs` leaves it out), the test ROMs ran at the quick level,
  one conversion each, and one lockstep stops early on a ROM that gives no verdict (`oam_bug` `7-timing_effect`, listed in [KNOWN_FAILURES.md](KNOWN_FAILURES.md)). G11 stays `P`: on 3 November Mooneye
  passed 92 of 94 applicable tests and the sound unit failed 18 of the 24 `dmg_sound` tests (figures of 1.6.8 in the next entry); no hardware capture was made.
- Mega Drive (4 November 2026): G8 moved from `P` to `Y` on the liveness record read on 14 conversions (28 routes) and the captures of 11 games
  ([below](#mega-drive-evidence-behind-its-column-4-november-2026)); the routes that rest on a menu are listed there. G2, G10, G11 and G13 stay `P` with
  fresh evidence and a precise list of what is missing. The captures were looked at by the specialist agent, not by the owner.
- Mega Drive (13 November 2026): G2, G10 and G15 moved from `P` to `Y` on the evidence of the section *Mega Drive: evidence behind its column (13 November 2026)*
  ([below](#mega-drive-evidence-behind-its-column-13-november-2026)): the report of a Sonic 2 conversion now carries the route hashes, the states, saves, input and build sections
  and the two honesty flags (commits `50ce0d5f`, `658dfb03`); the 2,895 groups vectors agree on all of them since 1.7.4 and Moira (MIT) is the independent model for the forms no vector holds
  (`b63a9d11`, `4d024c4d`); the honesty audit of that date found and fixed the wording and report defects listed there; G13 the same day, on eight cartridges chosen by risk (46 of 46 routes identical on Windows and Debian). G11 stays `P`. The oracles are MAME and Moira, not silicon; the gate is about the
  report, the CPU model and the words, not about hardware fidelity, gameplay or latency.
- NES (3 November 2026): G13 moved from `P` to `Y`: the eight games of the campaign, converted on Windows and on Debian 13 with the same
  engine revision and the same native sources, give identical per-frame traces and sound on all six routes of 3,600 frames (48 routes). See the row of the NES table below.
  The panel of ten mapper families of 1.6.7 passes at the thorough level (G12 stays `P`: the panel size policy is not decided). A defect of
  the quick-state writer found on the way (the PRG register was not saved, 1.6.5 and 1.6.6) is described in [UPGRADES.md](UPGRADES.md).
- Master System and Game Gear (1 November 2026, completed 2 November): G5 is `P` for both. The compressed copy is replayed by both
  engines since 1.6.7: the banked engine compares it with the fresh reference of each route, the "functions" engine (which has no
  per-route reference) with the final pass of the same build, and the report says which (`packed_replay` for the functions engine). What
  is recorded is synthetic tests (`tests/test_sega_evidence.py`), runs on three banked games and 18 + 3 + 15 functions conversions
  ([UPGRADES_HISTORY.md](UPGRADES_HISTORY.md#master-system-and-game-gear-the-functions-engine-replays-the-delivered-copy-and-starts-from-the-reset-state-167)),
  not a result per console. The Game Gear was `Y` before; nothing recorded separated the two consoles, which share the engine and the adapter.
  G6 is judged on the banked engine, the default: the "functions" engine has no quick states ([MASTER_SYSTEM.md](MASTER_SYSTEM.md)),
  so it has nothing to check and is not claimed.
- Super Nintendo and Neo Geo (1 November 2026): G8 moved from `Y` to `P`. The Super Nintendo has a liveness check for the cartridges
  with a coprocessor only (`supernintendo.validate_device_liveness`), none for an ordinary cartridge; the Neo Geo has no liveness record
  yet (`retrorecomp/neogeo_conversion.py` uses `deliver_packed` and `replay_routes`, not `liveness_summary`). See the section
  *Shared evidence helper*.
- Super Nintendo (4 November 2026): G1, G7, G8, G9, G10 and G15 moved from `P` to `Y` on the evidence of the section *Super Nintendo: evidence behind its
  column* below (twenty-four conversions of two trees, the vectors of both CPUs, captures of the routes inspected by the specialist agent, not by the owner). G8
  returns to `Y` after its move to `P` of 1 November. G11 stays `P`, G14 stays `?`. G13 stays `P` with fresh evidence: four games, 12 routes of 12 identical between Windows and Debian 13 (see the section).
- Neo Geo (2 November 2026): G10 moved from `P` to `Y`. Both CPUs replay independent vectors through the Neo Geo generator, the same ones
  as the CPS-1 and with the same figures ([NEOGEO.md](NEOGEO.md#qualification), [NEOGEO_LOG.md](NEOGEO_LOG.md)). 68000
  (`tools/neogeo_vector_selftest.py`): the three SingleStepTests fixtures (834 + 2,171 + 864 vectors, the 82 authored cases included) all run
  as native steps; the native steps agree with 3,867 of 3,869 on registers, SR, PC, written bytes and clocks. Z80
  (`tools/neogeo_z80_vector_selftest.py`): 51,328 vectors through `neogeo_z80.generate` and the Geolith core corrected in the converter's copy
  (`neogeo_z80.FIXES`), 49,685 as native steps below `0xf800` and 1,643 through observed RAM variants; native and interpreted identical on every
  vector, 51,260 states (99.87 percent) and all 51,328 clocks agree with the oracle. **Reserves, written as they are:**
  (a) the two authored 68000 vectors that set the trace bit, which neither path delivers (the Neo Geo Musashi is built without trace);
  (b) the 68 Z80 vectors that differ are the X and Y flags of `SCF` and `CCF` and their `DD`/`FD` duplicates (the Q latch of the original chip is
  not carried: a store per instruction and a state field); (c) the shared Musashi, the reference of every conversion, differed from the
  68000 vectors on `DIVU`/`DIVS` flags (and the division clocks), `CHK` flags and clocks and one line-F stack byte; the converter now
  corrects it in its own copy (`retrorecomp/musashi_fixes.py`, 3 November 2026, group `shares:musashi_fixes` of the Neo Geo, CPS-1 and
  X68000 stamps) and the three vector selftests have no known deviation left; N and Z after a divide overflow, and N after a `CHK`
  that does not trap, are undefined on the 68000: the interpreter now gives the values the translated steps give, which are also the
  vectors'; (d) the oracles are MAME (68000) and JSMoo (Z80), not hardware, and the bus is flat: nothing
  of the board, the YM2610, the command latch or the prefetch bus phases.
- Neo Geo (2 November 2026): G8 moved from `P` back to `Y`. The packed replays now run with `--trace` and every `final_checks[]` row carries
  `liveness` with the CPS-1 keys (`frames`, `distinct_pictures`, `picture_changes`, `last_picture_change_frame`, `audible_frames`,
  `last_audible_frame`), counted from frame 1, through `delivery_evidence.py` unchanged (`liveness_summary`, `report_fields`,
  `require_moving_picture`); a route whose picture never changes stops the conversion, as on the CPS-1, and every route of a set is required
  to move (MVS and AES). Read on conversions of the tree: NAM-1975 (7 routes), Puzzle De Pon! (6), Metal Slug 3 (7) and The Irritating Maze
  (4): every route changed its picture on more than a thousand frames and was audible on more than half of them. **Scope:** the record is on
  every conversion from now on; it was read on four sets, not on the 134 identities, and it says that picture and sound change, nothing of what
  they show (the captures of the earlier campaigns are G9's evidence).
- Neo Geo (3 November 2026): G13 stays `P` with fresh evidence. `nam1975`, `mslug3` (SMA) and `twinspri` (2 MiB) converted on Windows and on
  Debian 13 give the same instruction counts, 0 interpreted instructions and the same CPU, RAM, hardware, Z80, picture and sound hashes on all
  19 route rows ([NEOGEO_LOG.md](NEOGEO_LOG.md#cross-os-witness-on-debian-three-sets--3-november-2026)). Three sets of the 134 identities; interactive play
  on Linux is not witnessed.
- Master System, Game Gear, Game Boy and Super Nintendo (5 November 2026): G14 moved from `?` to `Y` on the owner's play test of
  two games per console converted with the tree of `main` at `491e845` (owner-acceptance table). Two games per console are a play test,
  not a campaign: no claim of gameplay beyond them, and nothing about hardware fidelity or latency.

## Shared evidence helper: G5 and G8 (`retrorecomp/delivery_evidence.py`)

Neo Geo, CPS-1 and the X68000 produce the packed replay (G5) and the liveness record (G8) through one
module, and since 1.6.6 so do the Master System and Game Gear, the Game Boy, the Mega Drive and the NES, so a machine
that joins them gives the same evidence in the same shape ([STANDARDS.md](STANDARDS.md) rules 1 and 7). The module
reads rows a machine already writes; it never runs a game.

- **Liveness.** `liveness_summary(rows)` takes one `FrameRow` per frame (picture hash; optionally the sound hash, an
  audible flag, a RAM hash, a program counter) and returns the same nine keys for every machine. A key the machine
  cannot give is `None`, never `0`. `frozen_route` is the one rule that refuses a route whose picture never changed (one
  distinct picture or none); which routes must move stays the machine's call (CPS-1: every route; X68000: the main route
  only, because a game that waits for a click or a key shows a still picture on the others).
- **Report fields stay each machine's own.** The common keys are `frames`, `distinct_pictures`, `picture_changes`,
  `last_picture_change_frame`, `audible_frames`, `last_audible_frame`, `distinct_sound_blocks`, `distinct_ram_states` and
  `distinct_program_counters`. CPS-1 reports the first six (`final_checks[].liveness`). The X68000 reports `frames`,
  `distinct_pictures`, `distinct_audio_blocks` (= `distinct_sound_blocks`), `distinct_ram_states` and
  `distinct_program_counters`, then `nonblack_frames` and `nonzero_samples` from its replay report (`liveness[]`). Frame
  numbers are the machine's own: CPS-1 and Neo Geo count from 1, the X68000 from 0. Neo Geo reports the CPS-1 six keys (`final_checks[].liveness`).
- **Packed replay.** `deliver_packed` compresses a copy of the build as publication does and takes its SHA-256 before any
  replay; `replay_packed` (or `replay_routes` where the machine's callback compares by itself) replays that copy on every
  route and compares it with the fresh reference. `native_validation.packed_reference_match` and
  `packed_candidate_sha256` are written from the delivered file (`validation_fields()`, `report_fields()`); the first
  refuses to be written before every route matched. Since 1.6.7 a compressed copy that fails its replay on the converting
  system is replaced by the build as built and every route is replayed again on it; if that passes, the compressed copy is
  replayed once more on the first route that failed, and only a failure that is reproduced is blamed on the compression: the
  unpacked file is then delivered and reported as such (`packing.unpacked_reason`). A failure that does not reproduce, or a
  build that fails too, raises the first error ([BUILDING.md](BUILDING.md)). It is the same file that passed every route that
  is delivered, packed or not.

The Master System and the Game Gear use it since 1.6.6 (`retrorecomp/sega_evidence.py`): the runner's `--vdp-trace` has two more
columns, `psg_h` (hash of the PSG's stereo samples of the frame) and `psg_nz` (their non-zero count), written only when a trace is
written; every conversion records `final_checks[].liveness` per route (picture from `pixels_h`, sound, RAM; no program counter, so that
key is None) and refuses a conversion whose main (`play`) route never changed picture; the banked engine also replays the compressed
copy of the build on both routes against the fresh reference (`native_validation.packed_reference_match`, `packed_candidate_sha256`).
Both engines have the liveness record and the packed replay (the "functions" engine compares the copy with the final pass of its own
build). G8 is `P` for both columns: the record exists on every conversion, but the captures were not inspected as a campaign and the
risk cases were not run to play. G5 stays as recorded: the replay is in the conversion for every game, run on three banked games and
on the functions batches here.

The NES uses it since 1.6.6 (`retrorecomp/nes_checks.py`, `retrorecomp/nes.py`): the headless `--hash-out` line of the exported
game carries `pic=` (the hash of the rendered 256 x 240 picture), `snd=` (the hash of the frame's sound) and `aud=` (1 when a
sample was not zero), the liveness record of each route is read from it, the delivered copy is replayed on every route and its
trace and PCM compared with the fresh reference, and the machine is in the `conversion_gates` group.

The Super Nintendo uses it since 1.6.7 (`retrorecomp/snes_evidence.py`), for every cartridge with or without a coprocessor, as the Mega Drive does
(`megadrive_evidence.py`): the 16-bit host's `--trace` line (frame, picture hash, counters, sound hash) feeds the same record, a frame is audible when its
sound hash is not the hash of silence for its number of samples (since 1.6.8, as the Neo Geo and the CPS-1 do; the host writes no extra column), the
program counter is `None`, and `frozen_route` refuses a `play` route whose picture never changed (the other routes may sit in a menu). The record is in
`final_checks[].liveness` of every conversion, with the route's own `pcm_nonzero` and `visible_frames`; `supernintendo.validate_device_liveness` still
judges the cartridges that have a counted device.

The packed replay (G5) needs, for each machine, a callback that starts the compressed copy with the same arguments as the
probe that made the reference and compares the same fields (Mega Drive and Super Nintendo: `reference_differences`;
Master System and Game Gear: `compare_execution`; NES: the `.hash` lines and the PCM; Game Boy: the verdict line of the
build), and the group `conversion_gates` in the machine's `stamp_groups`.

## Sharp X68000: evidence behind its column (29 October 2026, status of 1 November 2026)

The X68000 is **supported** since 1.6.9 (owner's decision of 5 November 2026, [below](#sharp-x68000-scope-and-follow-ups-at-the-exit-5-november-2026)). This is what each gate rests on today and what is still missing, with the file that
shows it. `P` means a part is shown and the rest is named; nothing here says exact hardware, gameplay coverage or latency.

| Gate | X68000 | Evidence | What is missing |
|---|---|---|---|
| G1 | Y | `retrorecomp/systems/x68000.py` (status `supported` since 1.6.9), [X68000.md](X68000.md), `tests/test_system_profiles.py`, `tools/status_lint.py` | | ? |
| G2 | Y | Common report v2 (`report_schema.py`, `tests/test_report_schema.py`, golden `tests/x68000_common_golden.json`). Since 1.6.6 the sections are filled from the conversion itself: `cpus` (one 68000, native and interpreted counts per route), `validation.cpu_fidelity` (digests of the CPU, RAM, image and PCM traces per route), `scan.routes` (frames, steps and script digest of each exploration route), `states.validation` (fresh process, compressed copy, the frame of the save and the 400 continued frames), `saves`, `input_players`, `peripheral`, `packed.replay` | `devices` is empty and there is no audio CPU section: the machine has no cartridge device and its sound is part of the reference machine, so a counter per device does not apply. `saves.validation.checked_in_this_conversion` is false (the proof is the test and the tool named there, not a step of the conversion) | ? |
| G3 | Y | `final_checks[].interpreted_opcodes` is 0 on the main, mouse and keyboard routes of the four risk cases (below) | Only on the routes run | ? |
| G4 | Y | A fresh interpreted reference per conversion, trace equality (`native_validation.reference_match`, `tests/test_x68000_conversion.py`) | | ? |
| G5 | Y | The compressed copy is replayed on every route against the same reference (`packed_reference_match`, `packed_candidate_sha256`, `retrorecomp/x68000_conversion.py`); R-Type, Metal Sight, Lemmings and Super Hang-On matched on 3 routes each | The published file is compressed again by `publishing.py` (UPX is deterministic: the SHA-256 recorded in the report equals the published one on the run checked); on Debian the compressed copy of Choujin stops at start and is refused (the panel row below) | ? |
| G6 | Y | F9 in a fresh process and the early floppy DMA, now on the compressed copy (`state_checks`) | | ? |
| G7 | Y | `tests/test_x68000_payload.py`: a played disk survives every start and a second build of the same machine identity; a disk of another size, a missing one or a folder in its place is moved to `<name>.unusable-N` and replaced from the executable; a changed host file is treated the same way; the game always starts. `tools/x68000_saves_check.py` on a real game (below): the game wrote to its disk, a relaunch and a second conversion found it as it was | The writes found are file time stamps of 4 to 12 bytes (below): no game was seen saving a score or a position on purpose, which needs play beyond the routes | ? |
| G8 | Y | `liveness` in every report, per route and for the delivered file; captures looked at; the four risk cases below reach play, R-Type and Metal Sight on the standard routes, Lemmings and Super Hang-On on authored routes (`tools/x68000_play_routes.py`) | Scope: the four risk cases, not every set of the panel. 8 of the 84 reviewed mouse sets make no sound on any standard route and 15 show a still picture on the 4,000-frame main route, which a click or a key wakes on another route (Route rules, below) | ? |
| G9 | Y | The four risk cases were converted at the extended level (main, mouse, keyboard and one 18,000-frame pseudo-random route), 0 interpreted opcodes on every route, the compressed copy matching the reference on the four routes (table below); play is reached on the delivered file for R-Type and Metal Sight (standard and long routes), for Super Hang-On (long route, and its authored route) and for Lemmings (authored route; its standard and long routes stay on the menu) | Inspected by the specialist agent, not by the owner; four games, not the 84 mouse sets; the thorough level (36,000 frames) was not run; not full games | ? |
| G10 | P | The 3,869 SingleStepTests vectors (834 shift, 2,089 prefetch plus 82 authored cases, 864 exception) replayed through the X68000 generator and through the same Musashi interpreting every instruction: the translated steps agree with every vector on registers, SR, PC, written bytes and clocks, and the Musashi reference agrees with them too since 3 November 2026 (`retrorecomp/musashi_fixes.py`, the correction shared with the CPS-1 and the Neo Geo) (`tools/x68000_vector_selftest.py`, `tests/test_x68000_vectors.py`, [CPU_68000.md](CPU_68000.md#tests-and-vectors)); Musashi as the reference, 20 authored CPU guards (`native/x68000_native/guard_checks.c`, `tools/x68000_native_check.py`); a fourth fixture, the 2,895 vectors of 85 instruction groups no other fixture holds (`m68k-groups`, 3 November 2026): every vector runs as a native step and every total of clocks equals the vector's, on the native steps and on Musashi alike. The state first agreed for 2,862 vectors natively and 2,883 on Musashi; since the X68000, the CPS-1 and the Neo Geo apply the Mega Drive's state rules for `LINK A7`, `UNLK A7` and `NEGX` to their translated steps (`retrorecomp/m68000_state_rules.py`) and Musashi pushes `A7` as it was for `LINK A7`, it agrees for 2,873 and 2,889. The rest is recorded (`tests/fixtures/m68k-groups/deviations-musashi-machines.json`, checked by `tools/x68000_vector_selftest.py`: a group that differs and is not listed fails, and so does a count that changes) | The oracle is MAME, not silicon; odd-address and bus errors, `TAS`, `TRAPV` and the interrupt pins are outside the fixtures. The 22 native vectors of the fourth fixture that still differ are the decimal instructions (`ABCD` 2, `SBCD` 2, `NBCD` 18) on operands that are not decimal digits, which the manual leaves undefined (Musashi differs on 6 of them, and the native steps and Musashi differ from each other on 45); they are not modelled. No conversion of the panel showed a native/reference difference | ? |
| G11 | P | Authored video, audio, timing, session and disk vectors (`tools/x68000_*_check.py`); MAME 0.289 (its `x68000` driver, run with the IPL and font ROM it expects: the hashes of the owner's firmware are the ones MAME lists) against the delivered game on five games, no input on either side (`tools/x68000_mame_compare.py`, 2 November 2026): **90 of the 104 pictures of MAME that stand still have the same shape in the game** (R-Type 14 of 16, Lemmings 19 of 24, Star Luster 26 of 31, Quarth 19 of 20, Bubble Bobble 12 of 13), the first 200 frames (the Human68k start-up screen) are identical to the pixel on R-Type, and after the disk has loaded the two emulators advance image for image at a constant lag (665 frames on R-Type) | Sound is **not** compared, and colours only on Bubble Bobble: the palette's intensity bit now lifts the three channels as in MAME (the game's picture is XRGB8888 from the machine's own colour word, UPGRADES 1.6.7) and 97.03 percent of the pixels of its 12 matched pictures are identical to MAME's (93.55 before; the shape match of the tool does not depend on colours); the rest comes from the screen contrast of the system port, applied to the palette by the base but by MAME at display, after the raw screen this tool reads, and from rounding. Of the 14 pictures with no match, 4 are explained (2 of R-Type fall beyond the 3,000 frames captured on the game side, 2 are transition frames that agree on 99.97 percent of their pixels) and 10 are **not explained** (Lemmings 5, Star Luster 4, Bubble Bobble 1). Disks load more slowly in MAME, so the lag is per game and not calibrated. MAME is not hardware and marks its driver imperfect | ? |
| G12 | Y | **The owner chose option B (2 November 2026): 21 named games, each with its written reason, none dropped for failing** (the panel and its rule are [below](#sharp-x68000-the-panel-2-november-2026)); all 21 are converted on Windows (22 conversions with R-Type again at 4 MiB), 0 interpreted opcodes on every route, the compressed copy matching, F8/F9 resumed in a fresh process; the collection holds 418 images, 33 multi-disk sets and 84 reviewed mouse sets | The panel covers the categories it names, not the whole collection; the two sets that used to stop the reference (Tetris v5, TF4G v0.3A09) and Pensan CD (silent on its keys) are in it and convert | ? |
| G13 | Y | Windows and Debian trace hashes (CPU, RAM, picture and PCM, main, mouse and keyboard routes) are equal on the 21 games of the panel (2 November 2026, 1.6.6 tree), and again on the tree of the exit (5 November 2026: 21 games, 63 routes, CPU, RAM, picture and PCM, [below](#sharp-x68000-scope-and-follow-ups-at-the-exit-5-november-2026)) | Interactive play on Linux (window, captured mouse, full keyboard, sound out, gamepad) is not witnessed. On 2 November Choujin was delivered on Debian unpacked (its UPX-compressed copy stopped at start there; [KNOWN_FAILURES.md](KNOWN_FAILURES.md)); on 5 November it packs like the others | ? |
| G14 | Y | Play test passed on 3 November 2026 (five games); five more games, drawn at random, played on 5 November 2026 (Double Target, Fancy Qix, Twins, Danger Area, Pac-Land, converted with the 1.6.8 tree), and the owner's decision of the same day to leave the experimental status (quoted in the owner-acceptance table) | The decision was given with G10 and G11 `P`; it is the owner's and he can revert it. Five games drawn at random and played are not a campaign: no claim of gameplay beyond them | ? |
| G15 | Y | The five measures stay separate in the report and in [X68000.md](X68000.md). Read on 3 November 2026 for this gate: every string of the interface that names the machine, in the eight languages, the README and every public document that names the machine, the local documents (`docs/history/x68000`, the research page, the specifications), the host kit's lines and the report writer. No claim of exact hardware, complete gameplay, zero latency or zero fallback was found; the report now states `universal_zero_fallback_claim: false` like the CPS-1 and the Neo Geo (its common `honesty` block read `null` for it), and the roadmap paragraph that still listed the panel and the Linux comparison as missing was rewritten | The word "exact" appears in the documents for media identities and for redraw marks, never for fidelity; the generic help text of the converter ("sometimes beyond the original machine") is not specific to this machine | ? |
| G16 | P | Numeric paths (spans of RAM code tied to positions in the player's own disks, instruction positions in the IPL of a stated SHA-256), made only from the fresh reference runs of a conversion that passed, rechecked by every conversion; a failing conversion starts again without them; the sharing can be withdrawn in one line (`path_profiles.EXPERIMENTAL_SHARED`); the record has its own format number and is qualified by engine revision (`x68_knowledge`, [COMPILATION_LIBRARY.md](COMPILATION_LIBRARY.md#x68000-joins-the-base-169-5-november-2026)) | No X68000 path is qualified yet (qualified: reached and validated against the reference by a conversion that received it from another player); the X68000 stays in the experimental tier of the shared base (schema 3 only; a tier of the base, not the machine's status) | ? |

The four risk cases, converted one at a time with the 1.6.5 tree (standard scan level, `--no-online-cover`, an empty library;
"pictures" is the number of different pictures of the delivered file on the route, out of 4,000 frames unless noted):

| Game | Main route | Mouse route | Keyboard route | Interpreted opcodes | Seen on the captures |
|---|---|---|---|---|---|
| R-Type (Irem) | 1,744 pictures, 2,796 audio blocks | 2,169 / 2,829 | 1,693 / 2,845 | 0 | The game-over screen: play was reached |
| Metal Sight (System Sacom) | 311 / 3,241 | 312 / 3,379 | 127 / 2,745 | 0, 2 automatic disk changes | In play (a mech shooter screen) |
| Lemmings (Imagineer) | 993 / 59 | 5,756 / 9 (10,000 frames, 72,288 mouse reads) | 1,003 / 9 | 0 | The menu, with the mouse pointer and a level name; no level reached |
| Lemmings, authored play route (4,000 frames, quick scan) | 1,238 / 911 | | | 0 | Level 1 ("Just dig!") with its lemmings walking out and the time running: play was reached |
| Super Hang-On (Sharp / SPS) | 74 / 3,131 | 1,939 / 8,638 (10,000 frames) | 74 / 3,131 | 0, no automatic disk change | The title screens; the game was not reached |
| Super Hang-On, authored play route (10,000 frames, quick scan) | 2,432 / 9,083 | | | 0 | The first stage, course Africa, the bike running (score 4,310, speed 93 km): play was reached |

The same four games at the extended level (1.6.6 tree, `--scan-level extended`, an empty library, one conversion at a time; the long route is
one pseudo-random route of 18,000 frames; "pictures / audio" as above; interpreted opcodes 0 on every route, `packed_reference_match` true):

| Game | Long route (pictures / audio) | Native instructions on the long route | Seen on the last capture of the long route |
|---|---|---|---|
| R-Type (Irem) | 5,303 / 13,687 | 263,243,083 | The game's own menu (play, rank, demo, sound test) after the game over of the main route |
| Metal Sight (System Sacom) | 3,843 / 17,186 | 245,481,575 | In play (a mech shooter screen), 2 automatic disk changes on the routes |
| Lemmings (Imagineer) | 11,010 / 9 | 283,177,608 | The title menu: the standard routes do not enter a level, the authored route does (above) |
| Super Hang-On (Sharp / SPS) | 8,042 / 17,130 | 268,313,547 | The first stage, course Africa, the bike running (score 10,170, speed 91 km) |

The two authored routes were run again on the 1.6.6 tree: the same pictures and audio blocks as in 1.6.5 (Lemmings 1,238 / 911, Super Hang-On
2,432 / 9,083), 0 interpreted, packed copy matching. The captures (commercial game pictures) stay outside the repository.

What the games write (G7). A survey of 378 starts (the single-disk sets and the first disk of each other set, 3,000 frames of the
qualification inputs, the fresh reference) found six sets that change their own disk: Cybermission (Login), Darius Dokomade
Tatakaemasuka, F-1 Fastest Lap (Michael Company), Hoippuru X68K, Sekizui Hansha De Acchoo v613.61 and Twin Soul. Each changes 4 to 12
bytes, the time and date fields of a file's directory entry (Human68k stamps a file it opens for writing). On Cybermission,
`tools/x68000_saves_check.py` converted the game, ran its player (12 bytes changed on its disk), ran it again (the disk was
kept byte for byte), converted the game a second time and ran that new player over the same data folder (the disk was kept, and no
second data folder appeared). The other 372 starts left their disk as it was; none of them saves a score or a position without play.

Route rules (what the standard routes wake). The 84 reviewed mouse sets, each run on a fresh interpreted reference on the 4,000-frame
main route (keys and buttons) and on the 10,000-frame mouse route (`tools/x68000_mouse_survey.py`; the reference only, no conversion):
sound on the main route for 70, on the mouse route for 74, on at least one of them for 76 (8 sets are silent on both: Fire, Future Wars,
Ganbare! Paichan, Giga Fight 68K, Last Tempest A, Puzzle (1991), See Through v2, Uno); a picture that still changes in the last 1,000
frames for 69 on the main route and 80 on the mouse route, and for every set on at least one of them. The main route is silent for six
sets that the mouse route makes speak (Pensan CD, Boyon Boyon, Get Ready, Magritte, Oh! Hajiki!, Tonkotsu Pro Roku Hachi Kei) and still
for 15 that the mouse route moves. Carrying the first clicks of the mouse route on the main route would give sound to 75 and a moving picture
to 81, losing Klax's sound and the picture of Tonkotsu Pro and Tower of Druaga, and it would change the main route of every listed set, so it
is not done: the conversion looks for sound on every route it replays instead (`native_validation.sound_routes`, UPGRADES.md). A game that
loads for a long time needs a longer route than the main one: Super Hang-On's title counts down about once a second from 99 while the game
sets up its sound module and takes no start before it reaches 0 (about frame 8,500).

A conversion took 133 to 186 seconds on the Windows build PC with these three routes (the compressed replays are 28 to 39 of
them). Picture and sound changing is not gameplay validation, and a route that stays on a title screen proves only that the
machine runs.

## Capcom CPS-1: evidence behind its column (29 October 2026, status of 1 November 2026)

CPS-1 is **supported** since 1.6.6, on the owner's decision of 1 November 2026 taken on this evidence; his own play trial is still to do. Each gate with the file or measure that shows it and what is still missing; nothing here says
hardware fidelity, gameplay coverage or latency. Details and tables: [CPS1.md](CPS1.md#qualification), dated measurements in
[CPS1_LOG.md](CPS1_LOG.md#29-october-2026-165-tree-the-whole-panel-routes-captures-and-long-routes).

| Gate | CPS-1 | Evidence | What is missing |
|---|---|---|---|
| G1 | Y | `retrorecomp/systems/cps1.py` (status `supported`), README, COMPATIBILITY, INDEX, the interface; `tools/status_lint.py` shows 0 contradictions | | ? |
| G2 | Y | Common report v2 with separate 68000 and Z80 counters (`report_schema.py`) | | ? |
| G3 | Y | `final_checks[].interpreted_opcodes` and `audio_interpreted_opcodes` are 0 on both routes of the 26 sets of the table (29 October, one tree) | Only on the routes run | ? |
| G4 | Y | A fresh interpreted reference per route in every conversion (`final_checks[].reference_match`) | | ? |
| G5 | Y | The compressed copy replayed against the reference (`packed.replay.match`, `packing.compared_on`) | | ? |
| G6 | Y | F8/F9 in a fresh process, damaged state refused (`game_states.validation`) | | ? |
| G7 | - | No non-volatile memory on the standard boards | | ? |
| G8 | Y | `final_checks[].liveness` per route (pictures, last picture change, audible frames, last audible frame) for the 26 sets; a route whose picture never changes is refused | Four attract routes are silent (`dynwar`, `ghouls`, `mtwins`, `unsquad`); every set is audible on its play route | ? |
| G9 | Y | The credited play route of each of the 26 sets reaches play (six captures per set, replayed on the delivered file, inspected); the 18,000-frame route ran on `sf2ce`, `ffight` and `1941` | Inspected by the specialist agent, not by the owner; not full games | ? |
| G10 | Y | 68000: the three SingleStepTests fixtures through the CPS-1 generator, the native steps agree with 3,787 of 3,787 vectors and 80 of 82 authored cases (`tools/cps1_vector_selftest.py`). Z80: 51,328 vectors through the CPS-1 Z80 bodies and the Geolith core corrected in the converter's copy since 1.6.6, native and interpreted identical, 51,260 states (99.87 percent) and all 51,328 clocks agree with the oracle (`tools/cps1_z80_vector_selftest.py`, `neogeo_z80.FIXES`) | The X and Y flags of `SCF`/`CCF` (the Q latch is not carried: a store per Z80 instruction and a state field); the CPS-1 Musashi is built without trace support (the two authored trace vectors are not delivered by either path); since 3 November 2026 the reference agrees with every other vector (`retrorecomp/musashi_fixes.py`). The groups fixture (`m68k-groups`, 2,895 vectors) was replayed too on 3 November 2026, with the same result as the X68000 and the Neo Geo: all clocks equal, state 2,873 native and 2,889 on Musashi, only the decimal instructions on operands that are not digits differ (`tests/fixtures/m68k-groups/deviations-musashi-machines.json`); the status of this gate is unchanged | ? |
| G11 | P | MAME 0.289 on the 1.6.5 tree (`tools/cps1_mame_compare.py`, 30 October and 1 November): 24 sets comparable, the picture of the attract route identical on all of them, of the credited play route on 23; the sound within 0.42 dB (median level) and 0.99 (averaged spectra) on the 24 | `sf2hf` slips by a frame; two sets need PAL dumps the romsets lack; MAME is not hardware; the waveforms are not claimed equal (OKI interpolation) | ? |
| G12 | Y | The owner chose criterion 1 (1 November 2026): every set of the perimeter that he owns is converted and validated, 26 of 26 (the perimeter has 129 sets) | Not covered by the panel and noted in [CPS1.md](CPS1.md#panel-coverage): the boards `CPS_B_17` (`sf2ua`) and `CPS_B_21_BT5` (`varthj`), 20 of the 45 mappers (seen in sets the collection lacks) | ? |
| G13 | P | Final Fight (27 October), Street Fighter II' Champion Edition (30 October) and 1941 (1 November) give the same CPU, RAM, image, sound and trace hashes on Windows and Debian 13 | Three sets of 26 | ? |
| G14 | Y | Exit from the experimental status accepted by the owner on 1 November 2026 on the evidence of 1.6.6; play trial list passed on 3 November 2026 on the 1.6.7 tree (owner-acceptance table) | | ? |
| G15 | Y | The five measures stay separate in the report and in [CPS1.md](CPS1.md) | | ? |
| G16 | P | Numeric paths, rechecked by every conversion, a failing conversion starts again without them; the sharing can be withdrawn in one line | No CPS-1 path is qualified yet; CPS-1 stays in the experimental tier of the shared base (schema 3 only; a tier of the base, not the machine's status) | ? |

## Capcom CPS-2: evidence behind its column (6 November 2026, release 1.7.0)

The CPS-2 opened as an **experimental** machine in 1.6.9 (« OK pour CPS2 en expérimental sur la 1.6.9 », 5 November 2026) and leaves that
status in 1.7.0: the decision (G14) is the owner's and is recorded in the owner-acceptance table below. Details and tables: [CPS2.md](CPS2.md). The
letters here are about the first scope (the standard boards, 236 sets), measured on 17 of them; nothing says exact hardware,
complete gameplay or latency.

| Gate | CPS-2 | Evidence | What is missing |
|---|---|---|---|
| G1 | Y | `retrorecomp/systems/cps2.py` (status `supported`), `tools/status_lint.py` shows 0 contradictions | | ? |
| G2 | Y | The common report (`report_schema`, written by `cps1_conversion` with `system.id` `cps2`); the key file of the romset is not in it | | ? |
| G3 | Y | 0 interpreted 68000 and 0 interpreted Z80 instructions on every route of the 17 sets (attract, credited play, one 18,000-frame pseudo-random route: the extended level) and of `ddtod`, `mvsc`, `ssf2` at the thorough level | | ? |
| G4 | Y | A fresh reference run of every instruction per conversion; native and reference traces equal on every route | | ? |
| G5 | Y | The compressed copy is replayed against the same reference on every route, on Windows and on Debian | | ? |
| G6 | Y | F8/F9 in a fresh process and a truncated state refused, on all 17 | | ? |
| G7 | Y | The 93C46 EEPROM file is written at the first run and read at the second on every set; a setting changed in the test menu (`ddsom`: 2 players to 4) is kept after a restart | | ? |
| G8 | Y | `liveness` in every report; every route reaches a moving picture and sound | | ? |
| G9 | Y | The extended level on the 17 sets and the thorough level on `ddtod`, `mvsc`, `ssf2` (routes of up to 18,000 frames); the routes are pseudo-random, they do not finish a game | No complete game | ? |
| G10 | Y | The 68000 and Z80 translated steps through the CPS-2 variant of the generator agree with the same independent vectors as the CPS-1's (`tools/cps1_vector_selftest.py --cps2`); the decryption equals MAME's on 35 archives | No vectors of their own for the object chip or the raster counters | ? |
| G11 | P | MAME 0.289: pictures 360 of 360 on `ssf2`, `ddtod`, `dimahoo`, `xmvsf`, `mvsc`, `msh` and on 8 of the 9 sets beyond the panel (one picture of 360 differs on `sfa3` and `avsp`: the boot self-test fades one step later; `mmatrix`: a title animation one frame ahead for 9 frames); bus accesses equal on `sfa3` and `msh`; sound within 0.057 dB and spectrum cosine at least 0.9932 on the nine | A comparison with MAME is not hardware; the DSP16 is a model; the three named differences are not explained | ? |
| G12 | Y | The owner's panel of eight, five sets drawn at random (seed 170) and the four sets whose files differ from the catalogue's: 17 sets | The other sets of the 236; the ten spinner and paddle sets and the three sets with inputs of their own are out of the scope | ? |
| G13 | Y | The 17 sets converted on the Debian 13 PC at the extended level: the CPU, RAM, picture and sound hashes of all 51 routes equal to Windows' | A game was not played interactively on Linux (window, sound, pad) | ? |
| G14 | Y | Arthur played the eight panel games on 5 November 2026 (« les 8 marchent parfaitement ») and the 17 sets of the final pass on 6 November 2026, then decided that the CPS-2 leaves the experimental status (owner-acceptance table) | | ? |
| G15 | Y | The five measures stay separate in the report, in [CPS2.md](CPS2.md) and in the interface; read on 6 November 2026 for this gate: the options note and the scan note in eight languages, the README and the documents that name the CPS-2, the report writer (`status`, `board_tier`, `hardware_fidelity_validated: false`, `full_game_validated: false`, no latency) | | ? |
| G16 | P | The paths are shared like the CPS-1's (`cps2_knowledge`, experimental tier of the base, withdrawable with one line); none of the 17 sets observes a path | No path qualified: the games observe none | ? |

## Nintendo NES: evidence behind its column (1 November 2026)

The NES is **supported within its validated cartridge and peripheral scope**. This is what each gate rests on, with the file or
measure that shows it and what is still missing. `Y` here is the letter the evidence supports; the status matrix above carries these
letters since 1 November 2026. Nothing here says exact hardware, gameplay coverage or latency.

Two trees gave the evidence. The campaign (G3, G4, G9) ran on the 1.6.6 tree before the delivered-file checks existed
(the converter of 30 October plus the PAL NMI change); the delivered-file checks (G5 to G8) ran on the tree that has them, on
the games named in each row.

| Gate | NES | Evidence | What is missing |
|---|---|---|---|
| G1 | Y | `retrorecomp/systems/nes.py` (status `supported`), [NES.md](NES.md), `tools/status_lint.py` | | ? |
| G2 | Y | Common report v2 (`report_schema.py`): the main 6502's counters per route in cycles (native, interpreted in ROM, in RAM, elsewhere), `native_validation`, `final_checks[].liveness`, `game_states` with its fresh-process check, `ordinary_saves`, `packed` with its replay. The 2A03's APU is part of the CPU and no cartridge device runs instructions, so there is no device or audio-CPU section | Counts are in cycles, not instructions (the generated code does not count them: that would be a cost in the hot path); freshness, the library and the website still read the old keys | ? |
| G3 | Y | 1 November 2026, campaign of eight games at the thorough level (below): 0 interpreted cycles on all 64 routes (8 games, 8 routes each). Ballblazer, the one old report that showed fallback (32,283 RAM cycles, 0.22), converts with 0 on the current tree after one RAM entry is learned | Only on the routes run. Of 45 library traces, 9 games run code from RAM (one to 486 entries each); the others have none | ? |
| G4 | Y at the extended and thorough levels | A fresh interpreter reference per route in every conversion: the CPU trace, the memory and hardware hashes and, since 1.6.6, the hash of every picture and every frame's sound, then the exact PCM. At the thorough level every route is compared whole: 57,600 frames per game, **460,800 frame pairs** over the eight campaign games, all equal. At the default level the reference covers 120 or 600 frames of each 3,600-frame route (`final_checks[].reference_frames` says how many) | The reference is the engine's own interpreter, so this is agreement between two executions of the same machine model, not an independent oracle (that is G10) |
| G5 | Y per conversion | Since 1.6.6 the conversion compresses a copy of the build as publication does, replays it on every route and compares each per-frame trace and the PCM with the fresh reference (`native_validation.packed_reference_match`, `packed_candidate_sha256`, `retrorecomp/delivery_evidence.py`). Balloon Fight, Asterix, The Legend of Zelda, Mr. Gimmick, Gumshoe and Castlevania III matched on their three default routes (for Balloon Fight the SHA-256 of the published file equals the replayed candidate's) | Replayed on the routes of the conversion's level, not on every game of the library |
| G6 | Y per conversion | Since 1.6.6 F8/F9 are checked in a fresh process on the delivered file (`retrorecomp/nes_checks.py`, `game_states.validation`): a start and a missing load create no file, two saves of one run are identical, a state loaded in another process continues with the same CPU, memory, hardware, picture and sound (180 frames after a save at frame 600 of the play route), and six damaged states (magic, ABI, ROM identity, region, payload, truncation) are refused without touching either file | |
| G7 | Y | `tools/nes_saves_check.py` on a cartridge written for the check (MMC1, battery RAM, a program that counts its launches): the first launch saves 1, the second finds it and saves 2, a second conversion over the same export leaves the file as it was, and the new build saves 3; the conversion's own probes left no file beside the export. The report says what a game saves (`ordinary_saves`: battery or none, the file's path) | No real game was seen saving a score or a position on purpose: that needs play beyond the routes. The check is a developer tool, not run during a conversion | ? |
| G8 | Y | Every route of every conversion carries a liveness record (`final_checks[].liveness`: distinct pictures, picture changes, last picture change, audible frames, last audible frame, distinct sound blocks, RAM states and program counters) read from the per-frame trace, and the conversion refuses a game whose main route (the right-hand play run) never changes its picture. End-of-route pictures of the eight campaign games were looked at (G9) | A route may rest on a title or a menu. The main route moves, but the record shows how little on some games at the default level: the right-hand run of The Legend of Zelda has 124 different pictures in 3,600 frames, and that of Mr. Gimmick has no sound after frame 181 | ? |
| G9 | Y | The thorough level runs six authored routes of 3,600 frames (boot, two play runs, a menu and dialogue run, a Select and second-player run, a varied movement run) and two pseudo-random routes of 18,000 frames seeded from the exact ROM, 57,600 frames per game. `tools/nes_route_captures.py` replays them on the delivered files and takes the last picture: **all eight games reached play on at least one route**. The Legend of Zelda (the overworld, Link in the field), Mr. Gimmick (the first stage, score 130), Esper Dream 2 (rooms and a dialogue), Gumshoe (a water stage with a score), Front Line (the road, score 300), Commando (the field, then the title with a score of 450: a game over), Castlevania III (stage 1-02) and Kirby's Adventure (Vegetable Valley) | First stages only, not full games. The pictures were looked at by the specialist agent, not by the owner. Kirby stays on its first level on both long routes; Gumshoe's second long route ends on a plain blue picture | ? |
| G10 | Y | The separate TriCNES-derived software oracle on NTSC routes (see the validation sections of [NES.md](NES.md)) | PAL has no independent oracle | ? |
| G11 | P | Authored fixtures of the clock, the APU, the Zapper and the mappers ([NES.md](NES.md#self-tests)) | No external emulator or hardware comparison; fine 2C07 register races and the PAL vblank-clear timing are unconfirmed (NESdev lists it as such) | ? |
| G12 | P | The eight games below, the ten games of the 1.6.7 panel of mapper families (mappers 9, 10, 19, 64, 118, 23, 16, 1 at 512 KiB, 2 in PAL and 69: ten of ten pass at the thorough level, [NES.md](NES.md#panel-of-mapper-families-3-november-2026)), the 1.6.4 player-conditions reconversion of Kirby's Adventure and the earlier qualifications of 8 to 12 October | The panel size policy is not decided | ? |
| G13 | Y | Windows and a Debian 13 PC, each converting the game with the same engine revision and the same native sources at the standard level, replay the six routes of the extended level (boot, two play runs, a menu and dialogue run, a Select and second-player run, a varied movement run; 3,600 frames each) with `tools/nes_cross_os.py`: the per-frame trace (program counter and registers, work memory, mapper, PPU and APU hashes, picture and sound hashes) and the SHA-256 of the 48 kHz sound are identical on all 48 routes of the eight games (The Legend of Zelda, Mr. Gimmick, Kirby's Adventure, Castlevania III, Gumshoe, Front Line, Commando, Esper Dream 2: mappers 1, 69, 4, 5, 66, 0, 2 and 26, NTSC and PAL). Quick states resumed across the Visual Studio and portable-toolchain builds (`tools/nes_state_cross.py`) | The two pseudo-random routes of 18,000 frames of the thorough level were not replayed on Debian, nor the ten games of the 1.6.7 panel; the traces were not compared with a reference console. Six of the eight games had identical native sources on both systems; the exception is Kirby's Adventure and Castlevania III, built with the corrected state writer on Windows only and with the previous one on Debian, which shows that the correction changes no trace | ? |
| G14 | Y | Play test passed on 3 November 2026 (six games, owner-acceptance table) | | ? |
| G15 | P | The five measures stay separate in the report and in [NES.md](NES.md) | The older documents have not all been read for this | ? |
| G16 | Y | Numeric hints, rechecked and retried without hints on a failed conversion; the RAM entries a conversion adds are permissions the guard checks | | ? |

The campaign (`tools/campaign.py`, thorough level, one conversion at a time, seed 166): the five risk cases of
`tools/campaign-risk-cases.json` plus Kirby's Adventure for the MMC3 family (a file kept outside the repository for this run) and two
games drawn at random. Each was chosen for a reason written before the run:

| Game | Mapper | Why | Interpreted cycles | Conversion |
|---|---|---|---|---|
| Castlevania III: Dracula's Curse (USA) | MMC5 | Mapped RAM and extra mapper state | 0 | 970 s |
| The Legend of Zelda (USA) | MMC1 | Battery RAM; code runs from cartridge RAM (1,470 guarded entries at this level) | 0 | 813 s |
| Mr. Gimmick (Europe) | FME-7, PAL | PAL timing and a CPU-clocked IRQ counter | 0 | 1,161 s |
| Esper Dream 2 (Japan, translated) | VRC6 | Extra mapper audio | 0 | 843 s |
| Gumshoe (USA, Europe) | 66 | Zapper input | 0 | 797 s |
| Kirby's Adventure (USA) | MMC3 | The most common board; its PPU-address IRQ counter keeps the direct PPU clock | 0 | 861 s |
| Front Line (Japan) | 0 | Drawn at random | 0 | 403 s |
| Commando (USA) | 2 | Drawn at random | 0 | 399 s |

Eight of eight passed the gates of `tools/release_check.py` (conversion, native and reference agreement, fallback limit). Times
are those of one run on the Windows build PC while other sessions were working: they say how long a thorough conversion takes,
not how fast anything runs.

The checks themselves are run by `tools/campaign.py`, `tools/nes_route_captures.py`, `tools/nes_saves_check.py` and
`tools/nes_state_selftest.py`; none of them needs a ROM in the repository.

### CPS-1.5 (QSound boards): in the CPS-1 column since 5 November 2026

Not a column of the matrix: these boards were a tier of the CPS-1 (`board_tier: experimental` in their reports, a column of the catalogue) from 1.6.7 and
left it on 5 November 2026 on the owner's decision (G14 below); the CPS-1 column now covers them, with the limits listed here. What exists, dated 2 November 2026 on the
1.6.7 tree and 5 November on the 1.6.8 tree, detail in [CPS1.md](CPS1.md#cps-15-qsound-boards) and [CPS1_LOG.md](CPS1_LOG.md#2-november-2026-167-tree-the-cps-15-board-without-its-sound-against-mame):
the Kabuki decryption equal to MAME's on six sets; the pictures of the five sets of the test collection (one per family, of 18) agree with MAME 0.289
on 3,599 of 3,600 compared frames; the sound of the high-level QSound model agrees with MAME's **for the same model**: MAME 0.289 plays these boards with
its high-level model by default, so this validates the port against MAME's model, not against the hardware nor against a run of the DSP16.
The five sets of the test collection convert through the whole chain at the Standard level (0 interpreted instructions on both routes, reference equal to native, states, packed copy; 2 November 2026).

| Gate | Letter for the QSound boards | Evidence | Still missing |
|---|---|---|---|
| G3, G4, G5, G6 | Y on the five sets | 0 interpreted 68000 and Z80 instructions, native equal to the fresh reference, packed copy replayed, quick state continued in a fresh process, a truncated state refused | the other 13 sets were not converted: they are not in the owner's collection |
| G7 saves | Y | the 93C46 EEPROM file written by the delivered executables of the five sets (224 bytes, unchanged at a second run), `tools/cps1_eeprom_selftest.py` and `tools/cps1_persistence_selftest.py` | the service and test buttons are not wired: the settings kept in the EEPROM cannot be changed in play |
| G10 CPU | P | the 68000 and Z80 are the cores of the CPS-1 (independent vectors, G10 `Y` there); the Kabuki decryption equals MAME's on six sets | no independent vectors for the Kabuki Z80 itself or the QSound path |
| G11 hardware | P | pictures 3,599 of 3,600 equal to MAME 0.289, sound compared with MAME's high-level model, which MAME plays by default | a comparison with MAME is not hardware; the DSP16 program is not run, the sound is a model |
| G12 panel | P | the 5 sets of the owner's collection (one per family of 18) | 13 sets not owned and never converted |
| G13 Linux | N | no QSound game was run on Linux | a Linux witness of at least one QSound game |
| G14 owner | **Y** | 5 November 2026 (row below) | |
| G16 shared paths | P | 8 paths of `slammast` shared and reused by a second empty library with identical results (CPS1.md); numeric, rechecked by every conversion | only one set of five learns paths; the Z80 side has nothing to share; no QSound path is qualified in the base |

The letters of the CPS-1 column of the matrix above are not changed by this tier; where a gate is `P` or `N` here, the QSound boards have it open although the column reads `Y`.

## Super Nintendo: evidence behind its column (4 November 2026, release 1.6.8)

The Super Nintendo is **supported within the boards and the routes below**. This is what the gates that moved on 4 November 2026 rest on, with the
file or the measure that shows it and what is still missing. `Y` is the letter the evidence supports, proposed by the specialist session; the status
matrix above carries the letters the lead has accepted. Nothing here says exact hardware, complete gameplay or latency.

Two sets of conversions gave the evidence. The campaign of the 1.6.7 tree (twelve games at the thorough level, 2 and 3 November 2026: Dragon Ball Z -
Hyper Dimension, Marvelous, Masters New - Harukanaru Augusta 3, Jikkyou Oshaberi Parodius, SD F-1 Grand Prix, Kirby's Dream Land 3, Stunt Race FX,
Super Mario World 2, Mega Man X3, Suzuka 8 Hours, Star Ocean, Street Fighter Alpha 2) gave the long routes; the panel of the 1.6.8 tree (twelve games at the
standard level from an empty library, pin `fb8cf15`: Secret of Mana, Super Mario World, Chrono Trigger, Lock On, Donkey Kong Country 2, Street Fighter Alpha 2,
Star Fox, Mega Man X3, Kirby Super Star, Dragon Quest III (ExHiROM), Super Mario Kart, Star Ocean) gave the rest. All twenty-four: native equal to the
reference on every route, the compressed copy equal to it, 0 interpreted opcodes of the 65816 and of the SPC700; the SA-1, Super FX and CX4 programs are counted as
interpreted device instructions on their own line, the DSP-1 and the S-DD1 are command models.

| Gate | Letter | Evidence | Still missing |
|---|---|---|---|
| G1 Scope and status | Y | `retrorecomp/systems/console16.py` (status `supported`), the README row, [COMPATIBILITY.md](COMPATIBILITY.md), the board scope of [SNES.md](SNES.md) and the interface note of the Options window in the eight languages say the same board scope since 4 November (ExHiROM and the 8 MiB S-DD1 were missing from two of them); `tools/status_lint.py` shows 0 contradictions | The README row is shorter than the scope (it does not name the coprocessor boards) |
| G7 Saves | Y | `tools/snes_saves_check.py`: one cartridge written for the purpose per board (9 boards), the file, its ten damaged forms, no battery no file, the quick states; `tools/snes_game_saves_check.py` on delivered games, across three processes: Super Mario World (LoROM, 2 KiB), Dragon Quest III (ExHiROM, 8 KiB), Star Ocean (S-DD1, 8 KiB) and Kirby Super Star (SA-1, 8 KiB: the game rewrites part of its save in its first frame, from what it loaded) write their file, read it back, and set a damaged copy aside byte for byte | Secret of Mana, Chrono Trigger and Donkey Kong Country 2 wrote nothing in their save RAM in 2,000 frames (they start it from their menus): not exercised. A save made by a player from a game's menu is not reached by the routes |
| G8 Liveness | Y | Every conversion records `final_checks[].liveness` per route: pictures, picture changes, last picture change, and since 1.6.8 the audible frames and the last audible frame (a frame is audible when its sound hash is not the hash of silence); a frozen `play` route is refused; the pictures of the routes were looked at for G9 | The pictures were looked at by the specialist agent, not by the owner; Dragon Quest III's demo is silent (0 audible frames of 3,600) |
| G9 Route depth | Y | `tools/snes_route_captures.py` replays the routes of the twelve thorough conversions on their delivered files and takes the last picture (and, for a route that ends on a fade, four pictures): **11 of the 12 games reached play on at least one route**: a fight (Dragon Ball Z, Street Fighter Alpha 2), a round of golf (Augusta 3), a race (SD F-1, Stunt Race FX, Suzuka 8 Hours), a level (Kirby's Dream Land 3, Super Mario World 2, Marvelous), the game's dialogue scenes (Star Ocean), and Parodius at its continue screen (after a game over) | Mega Man X3 stays in its introduction on every route (the pseudo-random input does not leave it in 18,000 frames); first stages only, not full games; the pictures were looked at by the specialist agent, not by the owner |
| G10 Independent CPU evidence | Y | The SingleStepTests vectors on both CPUs ([CPU_65816_SPC700.md](CPU_65816_SPC700.md)): 65816 **0 differences of semantics** in 32,768 cases (native and emulation mode) and in 130,448 of the larger run; SPC700 **0** in 29,959; the compiled operations equal the interpreted ones. The differences that remain are of timing (the 65816's `WAI` and `STP`, the SPC700's `SLEEP` and `STOP`) and of bus order (dummy accesses the cores do not make) | The reference of a conversion is the engine's own interpreter (the report says `independent_cpu_oracle: false`); the vectors are a development-time evidence; the SA-1 core's interrupt entry in emulation mode is not corrected and not measured |
| G13 Cross-OS witness | P | Four games converted on Windows and on a Debian 13 PC (GCC) from the same tree, the same engine revision and an empty library at the standard level, replayed with `tools/snes_cross_os.py`: Secret of Mana (HiROM), Super Mario World (LoROM), Star Fox (Super FX), Kirby Super Star (SA-1). **12 routes of 12 give the same per-frame trace** (picture, counters and sound hash of every frame) **and the same report hashes** (CPU, RAM, video, colour and sprite memory, sound RAM, PCM, program counter, cycles): the attract route and the play route of 3,600 frames, and one pseudo-random route of 18,000 frames of each game (the standard level makes none: the tool adds it, from the ROM's identity, like the conversion's). The GCC build of the new engine builds and runs | Four of the 314 known identities, two boards of the coprocessor kind; the long routes of the thorough level and the chained ones were not replayed on Debian; quick states across the two systems and interactive play on Linux are not witnessed; the DSP-1, CX4 and S-DD1 boards and ExHiROM have no Debian witness |
| G15 Honesty | Y | The five measures stay separate in the report (`honesty`, `qualification_scope.universal_zero_fallback_claim: false`, `native_validation.independent_cpu_oracle: false`) and in [SNES.md](SNES.md). Read on 4 November 2026 for this gate: the README, [COMPATIBILITY.md](COMPATIBILITY.md), [SNES.md](SNES.md), [SNES_SUPERFX.md](SNES_SUPERFX.md), [CPU_65816_SPC700.md](CPU_65816_SPC700.md), [GUNS_16BIT.md](GUNS_16BIT.md) and the interface strings that name the machine in the eight languages (a word search for exact, perfect, accurate, zero latency, 100 % and their translations, then a read of each hit): no claim of exact hardware, complete gameplay, zero latency or zero fallback was found | The older dated journals ([SNES_LOG.md](SNES_LOG.md)) were searched, not read in full |

Unchanged and still partial: **G11** (the independent hardware evidence is authored cartridges against the contracts of Snes9x, bsnes and ares, not an external
emulator or hardware comparison; [SNES.md](SNES.md#qualification)), G14 (no owner decision recorded).

## Mega Drive: evidence behind its column (4 November 2026)

What the specialist agent measured for the gates that were `P` on 3 November, on the 1.6.8 tree (the Mega Drive's column otherwise stands on
the matrix above and on [MEGADRIVE.md](MEGADRIVE.md#qualification)). Nothing here says hardware fidelity, gameplay coverage or latency: MAME is a
model, not hardware, and the numbers are of the delivered files on the routes run. The captures were looked at by the specialist agent, not by the
owner. The rows G2, G10 and G15 below are the state of 4 November; they were superseded on 13 November 2026
([next section](#mega-drive-evidence-behind-its-column-13-november-2026)).

| Gate | Mega Drive | Evidence | What is missing |
|---|---|---|---|
| G2 | P | Common report v2 with the 68000 and the Z80 as separate sections, `native_validation` per route, `final_checks[].liveness`, `packed` with its replay (`report_schema.py`) | Read through `read_report` on a 1.6.8 report, these sections are empty: (a) `validation.cpu_fidelity.scenarios[].hashes` (the writer holds the hashes in `final_checks` but `report_schema._cpu_scenarios` writes `None` for the `console16` writer); (b) `states` has `supported`, keys and compatibility only: no `schema`, `machine`, `rom_identity`, `fresh_process_verified` or `validation`, although the conversion chains the end state of a route into the next process; (c) `saves` has the cartridge memory layout and no `ordinary_saves` verdict (the proof is `tools/megadrive_save_selftest.py`, as for the X68000); (d) `runtime.input_players` and `peripheral` are `None` (pad type, guns); (e) the main CPU has no `mode`, `reported_label`, `interpreted_percent` or `cycles` (counts are in instructions); (f) `build.*` (backend, engine and SDL revisions, compiler signature, executable size) is `None`. All of it lives in `console16.py` and `report_schema.py`, which the Super Nintendo shares and whose G2 is `Y` on the same record: either the criterion is met for both or for neither, which is the lead's call, not a Mega Drive change | ? |
| G8 | Y | The liveness record of the delivered file on every route of every conversion (`megadrive_evidence.py` through `delivery_evidence.py`, the same record and the same refusal of a frozen `play` route as the other machines; no third copy). Read on 14 conversions, 28 routes: the 11 games of the 1.6.7 list at the quick level (1,200 frames) and three at the standard level (3,600 frames). The picture changes on every route (101 to 2,126 distinct pictures), the FM or the PSG gives a non-zero sample on every frame of every route (28 of 28), and the last picture change falls in the last 30 frames on 21 of 28 routes. Captures of the 11 games at frame 1,200, demo and play: gameplay or an attract run in Earthworm Jim 2, OutRun, Road Rash 3, Shinobi III and the Sonic 3 intro, a title or a menu in the six others (Contra, Ecco, NBA Jam, Sonic 2, Streets of Rage 2, Super Street Fighter II) | A route may rest on a title or a menu: the `play` route of Streets of Rage 2 stays on its menu from frame 688 (101 pictures in 3,600 frames), Ecco's stops changing at 1,046 of 1,200, OutRun's at 1,114, and the attract routes of Contra (969) and Road Rash 3 (1,076) end early; the two NBA Jam routes of the quick level repeat the logo animation. "Audible" is a non-zero FM or PSG sample, not music. Fourteen conversions, not every cartridge of the panel | ? |
| G10 | P | 2,873 of 2,895 vectors of 85 instruction groups agree on every check, on the native steps and on the reference path ([CPU_68000.md](CPU_68000.md#what-the-groups-fixture-found-since-166)); with the 2,171 prefetch vectors (82 authored cases included), the 864 exception vectors and the 834 shift vectors, all of which agree; the Z80 vectors | The oracle is MAME, not silicon; the 22 vectors left are the decimal instructions on operands that are not digits (undefined in the manual, not modelled); the long immediate forms with a memory destination that needs an address calculation (`ADDI.L`, `SUBI.L`, `ANDI.L`, `ORI.L`, `EORI.L`, and `CMPI` of every size) have no vector; odd-address and bus errors, `TAS`, `TRAPV` and the interrupt pins are outside the fixtures | ? |
| G11 | P | MAME 0.289 (`genesis` NTSC, `megadriv` PAL) against the delivered file on 11 games, no input on either side, `tools/megadrive_mame_compare.py` (first run, 4 November 2026): of the **80 pictures of MAME that stand still, 78 have the same shape in the game** (the first 3,000 frames: logos, titles, menus, attract screens), and **on all 78 the 8 levels of every colour channel are the same pixel by pixel**; the game's picture comes a few frames after MAME's (4 to 6 on Sonic 2; the lag is reported, not corrected, and not read on the others) | The two emulators write the 8 levels of a channel differently: MAME 0, 52, 87, 116, 144, 172, 206, 255, the game 0, 49, 87, 119, 146, 174, 206, 255 (at most 3 of 255 apart, four levels of eight), so the share of pixels with the same 24-bit colour is 33 to 100 percent by game (mean 0.90 Contra, 0.33 Road Rash 3, 1.0 Ecco): not a different picture, a different table, and which table is closer to a real console is **not** known (not changed). Two pictures of MAME have no match (the Emerald Hill title card of Sonic 2, an interlaced picture, and one picture of Super Street Fighter II): not explained. **Sound is not compared**: the delivered executable has no option that writes its sound to a file. Nothing that moves, no raster effect, no timing; MAME is not hardware | ? |
| G13 | P | Windows and a Debian 13 PC convert Sonic The Hedgehog 2, NBA Jam - Tournament Edition and Streets of Rage 2 with the same tree (standard scan, no shared base, empty library) and the demo and play routes of 3,600 frames give **the same value on every field of `final_checks`** (`tools/megadrive_cross_os.py compare`): 6 of 6 routes, the picture, frame sequence, CPU/prefetch, VDP, RAM, Z80 and YM hashes, the counters of native and interpreted instructions and the timing misses | Three games of 24 + 8; the long and authored routes were not replayed on Debian, nor was interactive play. A first round differed on `z80_cpu_hash` for all six routes: the hash read the bytes of a structure that holds a `long` (32 bits on Windows, 64 on Linux); it is taken field by field since 1.6.8 ([UPGRADES.md](UPGRADES.md)) | ? |

Plan for G11, in order (none started): (1) an option of the delivered executable that writes the PCM it mixed to a WAV file (the Mega Drive host has none:
about half an AI hour in `native/console16_main.c`, shared with the Super Nintendo, so the lead's), then the comparison of level and averaged spectrum on
the first 20 seconds, as `tools/cps1_mame_compare.py` does for the CPS-1; (2) the same route on both sides with input, MAME's pad read replaced by a tap
on `$A10003` as the CPS-1 tool does for its ports, on the 12 raster-effect games of the 1.6.7 list; (3) frame-by-frame comparison of a raster effect
(Sonic 2's split screen, Ecco, Contra - Hard Corps) with the lag measured and not corrected; (4) the choice of the colour table, a decision that moves every
Mega Drive picture hash. Results are always written as "model against MAME".

## Mega Drive: evidence behind its column (13 November 2026)

What the specialist agent measured and read on 13 November 2026, on the tree of branch `spec/md-174` (release 1.7.4 in preparation), for four of the five gates that were `P` after 4 November: G2, G10, G13 and G15 are now `Y`.
G11 stays `P` (the table above). The wording is that of the SNES and PC Engine rows of the same gates: `Y` means the criterion is met within the scope written in the last column.
Nothing here says hardware fidelity, gameplay coverage or physical latency: the oracles are MAME and Moira, models and not silicon, the five measures stay apart, and the numbers are of the delivered files and of the fixtures run.

| Gate | Mega Drive | Evidence | What is missing |
|---|---|---|---|
| G2 Report | Y | The six gaps of the 4 November row are closed (writer `retrorecomp/console16.py`, commit `50ce0d5f`; reader `retrorecomp/report_schema.py`). Read through `read_report` on a Sonic The Hedgehog 2 conversion of this tree: `honesty.independent_cpu_oracle` is `False` and `honesty.universal_zero_fallback_claim` is `False` (both read `None` before) and `qualification_scope` is written; `validation.cpu_fidelity.scenarios[]` carry the route hashes, 16 digests per route (cpu, ram, vram, cram, vsram, vdp_register, frame, sequence, fm, psg, z80_cpu, z80_ram, ym_timer, cpu_prefetch, cartridge_state, sram); `states` has its schema (`RR16ST1-MD-11`), the machine and the ROM identity; `saves` has `ordinary_saves` with its `supported`, `reason`, `scope` and `path`; `runtime.input_players` is 2, with the pad and the gun; the main CPU has its `mode`, `reported_label` and interpreted share; `build` has the executable size, the engine and SDL revisions and the phase times. The Super Nintendo, whose G2 was `Y` on the same writer, reads the same fields | Three fields stay empty, on purpose. `states.fresh_process_verified` and `states.validation` are written only when a conversion chains routes; the fresh-process proof of the states is `tools/console16_state_selftest.py` (G6). `saves.validation` stays empty: the proof of the cartridge memory is `tools/megadrive_save_selftest.py` (G7). The main CPU's `cycles` stay empty (the 68000 is counted in instructions, not cycles) and `build.compiler_signature` too (no 16-bit writer computes one). Read on one conversion, not on every cartridge of the panel |
| G10 CPU vectors | Y | 2,895 of 2,895 vectors of the 85 instruction groups agree on every check, on the native steps and on the reference path (was 2,873 of 2,895 on 4 November): since 1.7.4 the 22 decimal vectors (`ABCD`, `SBCD`, `NBCD` on operands that are not digits) follow Moira, result and all five flags, on the four 68000 machines (commit `b63a9d11`; the CPS-1, CPS-2, Neo Geo and X68000 game stamps move with it). With the 2,171 prefetch vectors, the 864 exception vectors and the 834 shift vectors, all of which agree, and the Z80 vectors. For the forms no vector holds, an independent model: Moira (MIT, the 68000 of vAmiga) made 3,744 vectors (seed 174) of `ADDI`, `SUBI`, `ANDI`, `ORI`, `EORI` `.L` and `CMPI` `.B`, `.W`, `.L` on every memory mode, and of the decimal instructions, replayed through the native steps and the reference: registers, SR, PC, prefetch queue, memory and total clocks agree on every vector. Exhaustive decimal check, every operand pair with X and Z, 1,050,624 states: 0 differences (`tools/megadrive_moira_vectors.py`, `native/md_bcd_checks.c`; commit `4d024c4d`, evidence only, no stamp) | The oracles are MAME and Moira, not silicon. The bus differs on two families, listed and not changed: Moira writes the high word of a long read-modify-write first where the MAME vectors write the low word first (672 vectors, `ADDI.L` and `SUBI.L`), and on 16 forms with no MAME vector (the long immediates and `CMPI` on `-(An)` and `(d8,An,Xn)`) the first read comes two clocks later than Moira's, with the same total clocks and the same data. Odd-address and bus errors, `TAS`, `TRAPV` and the interrupt pins stay outside the fixtures. Agreement with a model is not agreement with a console |
| G13 Cross-OS | Y | Windows (llvm-mingw) and a Debian 13 PC (system GCC) converted eight cartridges from the same tree (`b63a9d11`, the decimal rule in), at the extended level, an empty library and no shared base, and `tools/megadrive_cross_os.py compare` finds **46 routes of 46 identical** on every field of `final_checks` (picture, frame sequence, CPU and prefetch, VDP, RAM, Z80 and YM hashes, native and interpreted counters, timing misses): the attract run of 12,000 frames, the play route of 3,600, the authored routes (6,000, 1,800 and 6,000 frames) and the pseudo-random route of 18,000 frames, on every game but the gun cartridge. The eight, one per risk (Arthur's rule of 13 November: 7 to 8 games a panel): Super Street Fighter II (the Sega 512 KiB bank mapper, 5 MiB, where the static discovery stands aside), NBA Jam - Tournament Edition (the Acclaim serial EEPROM), Gunstar Heroes (a heavy Z80 driver), Sonic The Hedgehog 2 (interlace and the split screen), the Menacer 6-Game Cartridge (the gun: its own authored routes, no pseudo-random route, 4 routes), Castlevania - The New Generation (PAL), Phantasy Star IV (battery SRAM) and Ecco the Dolphin (68000 code run from work RAM); every route ran no interpreter on both systems. Before: three games, six routes | Eight of 24 + 8 cartridges, chosen by risk; the quick states across the two systems, the window and interactive play on Linux are not witnessed; the Windows and Debian builds came from the tree before the merge of the new in-game interface (`df9e1668`), which moves the host stamp only (no game stamp), so the routes are those of the same game code |
| G15 Honesty | Y | Audit of 13 November 2026, by the method of the SNES and PC Engine rows: the README, [COMPATIBILITY.md](COMPATIBILITY.md), the `MEGADRIVE*.md` pages, [CPU_68000.md](CPU_68000.md), [CPU_Z80.md](CPU_Z80.md), [GUNS_16BIT.md](GUNS_16BIT.md), [CONSOLES_16BIT.md](CONSOLES_16BIT.md), the Mega Drive rows of this page, the 1.6.x and 1.7.x notes and [UPGRADES.md](UPGRADES.md), the interface strings in the eight languages (a word search for exact, perfect, accurate, faithful, identical, zero latency, 100 %, complete and their translations, then a read of each hit, about 486), the exported game's menu and strings, the conversion log lines and the report writer. No claim of exact hardware, complete gameplay, a full catalogue, zero latency or zero fallback was left without its scope. Found and fixed (commits `658dfb03` and `50ce0d5f`): the report did not state `independent_cpu_oracle` false, `universal_zero_fallback_claim` false and a scope; `native_percentage` was the main CPU's alone beside a hybrid sound CPU without saying so; `audio_cpu` took the last route; "completed its finite qualification" on three pages; a stale "audio CPUs remain interpreted" in [GUNS_16BIT.md](GUNS_16BIT.md); the sound-CPU fallback line lacked the word "fallback" in Japanese and Russian; the Thorough level was named "complete" in Japanese; the window's fallback line now says tested routes and hardware unverified | `MEGADRIVE_LOG.md` was searched and its hit passages read, not read in full. The exported game's F1 line "Sound CPU: native code" is a per-session counter: changing it is a host-kit change, not made (it would move the host stamp of every host-kit console). No one read an exported game in its window for this gate |

## PC Engine: evidence behind its column (5 November 2026)

The PC Engine is open since 1.6.9 and **supported since 1.7.2**, on the owner's decision of 10 November 2026 (G14; [PC_ENGINE.md](PC_ENGINE.md)): HuCards are converted and the first panel of ten real
cards was run on 5 November 2026; twelve conversions of eleven US cards (Tiger Road twice: as dumped and as a bit-reversed copy; Alien Crush as a bit-reversed copy only) followed on 6 November ([PC_ENGINE.md](PC_ENGINE.md#us-turbografx-16-cards-6-november-2026)). `P` means a part is shown and the rest is named; `?` is not measured. Nothing here says hardware
fidelity, gameplay coverage or latency; the owner's play trials (eight games on 5 November 2026, the fifteen exports of the release tree on 10 November) are in the owner-acceptance table.

| Gate | PC Engine | Evidence | What is missing |
|---|---|---|---|
| G1 | Y | `retrorecomp/systems/pc_engine.py` (status `supported`), [PC_ENGINE.md](PC_ENGINE.md), the README, COMPATIBILITY, INDEX, UPGRADES, the interface strings in eight languages and the credits agree (`tools/status_lint.py`: 0 contradictions, 0 drift items; the honesty audit of 9 November 2026 read them all) | The owner's acceptance is G14, not this gate | ? |
| G2 | Y | `retrorecomp/pce_conversion.py` goes through `report_schema.write_report` (v2): native and interpreted instructions per route and per CPU, guard misses, the five measures apart, `latency_ms: null`, the route start, the Backup RAM's validation, the quick-state validation and the packed replay; read by `tools/release_check.py` on the 15 conversions of the panel | The device section is empty: the machine has one processor and no cartridge device | ? |
| G3 | Y | 15 cards at the extended level (attract and play of 3,600 frames, a long route of 18,000), built with the players' toolchain (llvm-mingw): 0 interpreted instructions and 0 guard misses on every final scenario of the 15 cards on the release tree `cf6d56fa` ([panel](PC_ENGINE.md#the-panel-of-the-release-tree-9-november-2026)). Street Fighter II' Champion Edition needs the engine's larger capture format (191,563 to 590,308 instruction identities a route, none dropped; 734,635 emitted); on the earlier pin's 65,536 bound it ran 19.3 %, 33.5 % and 74.7 % interpreted | Only observed code is native; no whole-game claim | ? |
| G4 | Y | The native run equals a fresh run with every instruction interpreted, frame by frame (CPU hash, work RAM, picture, PCM), on every route of the 15 cards, the 18,000-frame ones included | Agreement with the engine's own interpreter, not with a real HuC6280 (the engine against independent vectors is G10) | ? |
| G5 | Y | The compressed executable is replayed against the fresh reference on every route of the 15 cards on Windows, and on the Debian 13 PC on the cards witnessed there (their Linux reports carry the same replay) | | ? |
| G6 | Y | F8/F9 continue the saved timeline in a fresh process for 600 frames on all 15; 13 damaged states (an empty file, a text file, a header cut, one byte short, half cut, and a flipped bit in the magic, version, system, size, checksum, ROM identity, ABI and payload) are refused and left as they were; loading a missing state is refused and creates nothing (`pce_conversion.check_states`) | A continuation longer than 600 frames | ? |
| G7 | Y | A card can look for 2 KiB of Backup RAM on the console's backup unit: 86 of the owner's 286 cards hold the file system's mark, and the export now gives them that memory in `datas/saves` beside the game, with no F8/F9 and no change to the engine ([PC_ENGINE.md](PC_ENGINE.md#6-saves)). On all 15 panel cards: no file starts formatted (`HUBM 00 88 10 80`, a written choice, as Beetle's source does), a valid file is read back in a fresh process, 11 kinds of damaged file are set aside unchanged and the game starts, and the native run equals the reference with the same memory. 3 of the 15 write on their routes and a fresh process finds it (Boxyboy, Santatlantean, Soldier Blade); no route writes past 2 KiB. A player's save on Boxyboy, by the game's own SAVE command, is listed by the game's LOAD in a new process; a high score from Santatlantean's route appears in its table in a new process. On Boxyboy, the native and reference traces and files of those two runs are equal | Windows only; no real backup unit, and Beetle's source was read, not run. The saving paths are not on the routes, so they run partly interpreted, and counted (Boxyboy's save 18.8 %, its load 6.8 %). Soldier Blade writes its file, but no visible use of it is shown. Plain RAM, no lock, one file per card (a real unit is shared) | ? |
| G8 | Y | Every route shows moving pictures and sound by the liveness rule; the last picture change of the 18,000-frame route falls within 600 frames of its end on all 15 cards; the long routes were inspected (G9). The attract loop with no input of Space Harrier stops after a few frames and is reported; Santatlantean's, which also stopped before the Backup RAM, now loops through its title and its score table | | ? |
| G9 | Y | The extended level plays a pseudo-random 18,000-frame route seeded from the card, on 15 cards. The start (1 to 6 Run presses) is chosen by how many pictures the walk shows that the same frames without input never show, so a card that waits on a menu, a story or a password screen is not kept there (before this, 7 of 18 cards stayed on such a screen). Contact sheets of 12 pictures of each long route were looked at: every card reaches play at some point; 9 end in play with progress (Bonk's Adventure reaches stage 1-2, Blazing Lazers, Bonk III, Soldier Blade, Raiden, Boxyboy, Tonma, Neutopia II on its first overworld screens, Splatterhouse) and 6 reach play and then stall (Military Madness on a FIGHT/SURRENDER prompt from about frame 6,000, Santatlantean looping between its title and its options, Gradius left paused by the walk's Run pairs from about frame 7,700 (one more Run press at frame 8,000 brings it back to play; the walk repair now keeps such a press, at frame 7,811 on the release tree), Bomberman '93 restarting its stage, Space Harrier uncertain, Street Fighter II' CE on an idle fight screen after a pause) | Pseudo-random walks do not finish games (most stay in stage 1); the pictures were inspected by the specialist agent, not by the owner | ? |
| G10 | Y | SingleStepTests/huc6280 (MIT, generated by Mesen, 640,000 vectors) replayed by tools of ours with exact pinned counts (`tools/pce_huc6280_vector_selftest.py`, `tools/pce_huc6280_native_vector_selftest.py`): on the pinned engine's interpreter 563,514 of the 572,519 comparable vectors agree; natively 9,097 cases by default and 56,767 on request (231 opcodes, 40 or 250 each) show 0 differences with that interpreter. Upstream's own adapter gives the same interpreter numbers on the same corpus. The three known differences are explained against a second independent model, the source of MAME 0.289's HuC6280 core (read, not run), not resolved: on the TSB/TRB Z flag and on ST0-2 at 5 cycles the engine and MAME agree and the corpus differs (the corpus has no VDC); on TMA the engine agrees with the corpus on all 2,487 nonzero-mask vectors where MAME's multi-bit rule does not, and the 13 mask-0 vectors depend on a latch the corpus does not carry | Both sources are emulators, not silicon; the native tier replays a sample of each opcode, not its 2,500 vectors | ? |
| G11 | P | The delivered game against MAME 0.289 (`tg16` driver), no input on either side, the first 3,000 frames, `tools/pce_mame_compare.py`, on four US cards. Both sides start from the same formatted Backup RAM. Pictures after placing the game's picture in MAME's frame, at the level of each colour channel: 3,000 of 3,000 equal on Soldier Blade (which leaves the same 2,048 bytes in the memory on both sides), 2,999 of 3,000 on Bonk's Adventure and on Military Madness (the other frame is a one-frame or one-scanline timing difference), 2,992 of 2,999 on Boxyboy (7 single frames, each under 0.6 % of its pixels). Boxyboy's earlier 727 of 2,999 had one cause: MAME maps a memory at bank `$F7` on every card, the engine's base HuCard profile does not, and with that bank forced to read `$FF` in MAME 2,999 of 2,999 pictures equalled the game of that time; no engine fault was shown. The two write the VDC's 8 colour levels with different tables, so 24-bit equality is reported apart. Sound: the game's AC level is a near-constant 9.3 to 9.5 dB below MAME's, spectra agree to a cosine of 0.98 to 0.999 averaged over one-second windows; no waveform match is claimed | A comparison with MAME, not hardware: four cards, the first 50 seconds, no input, no gameplay, no latency. MAME's output has a DC offset the game's does not, its frame is 263 lines, the engine's frame length differs on Bonk's Adventure (734.3 against 737.3 samples a frame), and on the `pce` driver two US cards stay black | ? |
| G12 | Y | 15 cards chosen from the owner's library, read in place, none kept in the repository: boards of 128 KiB to 1 MiB, the 384 KiB and 768 KiB mirror maps, the 2.5 MiB Street Fighter II board, a Japanese ZIP, a homebrew card, and bit-reversed copies read as such. All 15 run 0 interpreted instructions on every route of the release tree, Street Fighter II' Champion Edition included through the engine's larger capture format (its game is 25.4 MB packed and takes about 34 minutes to convert). The only card of the first panel not converted is a SuperGrafx game (Dai Makaimura), refused by scope: one video chip, no picture appears. Windows and Debian hashes are equal on all 15 cards of the release tree (G13) | The panel is the owner's library, chosen by the specialist; no SuperGrafx or CD card | ? |
| G13 | Y | The whole panel on the release tree `cf6d56fa` (9 and 10 November 2026): the 15 cards converted on a Debian 13 PC (GCC 14.2, Ninja, an empty library, the extended level, two at a time and Street Fighter II' CE alone) give the same CPU, RAM, picture, PCM and Backup RAM hashes as the Windows panel (llvm-mingw) on 45 of 45 routes, the 18,000-frame ones included, with the same native counts (0 interpreted, 0 guard misses), the same walk repairs, and on each card the packed replay and the fresh-process states passing ([PC_ENGINE.md](PC_ENGINE.md#the-whole-panel-on-linux-9-and-10-november-2026)) | Route hashes, not play: nobody played a game on Linux (window, pad, sound out). A quick state is not compared across systems (its key holds the target), and no save made by a player was tried on Linux. Conversion times on that PC (26 to 37 minutes two at a time, Street Fighter II' CE about two hours alone) are not a speed measure | ? |
| G14 | Y | The owner played the fifteen exports of the release tree `cf6d56fa` in `Export\Games\PC Engine` and decided on 10 November 2026 that the PC Engine / TurboGrafx-16 leaves the experimental status in 1.7.2 (owner-acceptance table); he had played eight exports of an earlier tree on 5 November 2026 | A play trial of fifteen cards, not a coverage claim: code past the routes runs interpreted, counted and shown in the game (the owner saw it on Boxyboy after Start), and a PC Engine game keeps no player's record yet, so the code a player reaches is not made native at the next conversion. It says nothing of hardware fidelity or latency | ? |
| G15 | Y | The honesty audit of 9 November 2026 read the documents, the interface strings in eight languages, the exported game and the report fields: no claim of exactness, hardware fidelity, whole-game coverage or latency without proof; every flag that should be false is false and every claim string names what was tested. It found one misleading line ("ready (native code only)", now "no interpreter on the routes played"), the scope note, and counts that disagreed; all fixed | Two shared items, not this profile's, were fixed in 1.7.3: the report lists the five languages a game ships (it listed the eight of the converter), and the CPS-1 prints "no interpreter on the routes played" too | ? |
| G16 | P | Numeric paths: PC, eight MPRs and a ROM offset per instruction, with no byte of the ROM; a record is made only from the captures of a conversion that passed, and a player's conversion gives the engine the received rows as declared roots (`pce-declared-roots-1`), never as captures. A failed conversion starts again without them, and one line withdraws them (`path_profiles.EXPERIMENTAL_SHARED`). The proof on Soldier Blade, from two empty libraries: the routes of the conversion that received the paths equal those of a control with none, and A's long route, which it never played, runs 535,661,326 native, 219 interpreted (work-RAM code, which does not travel) and 219 guard misses against 7,348,650 interpreted on the control, equal to the fresh reference; a card with one byte changed is refused ([PC_ENGINE.md](PC_ENGINE.md#7-shared-paths)) | No path is qualified in the base yet (a conversion that received it from another player through the base must reach it); a declared row is qualified only by a window that runs it; one card in the proof; work-RAM code and the Street Fighter II board do not travel. The PC Engine stays in the experimental tier of the base (a tier of the base, not the machine's status) | ? |

## Sony PlayStation: evidence behind its column (15 November 2026)

The PlayStation is **supported since 1.7.6**, on the owner's decision of 15 November 2026 (open as experimental in 1.7.1; [PLAYSTATION.md](PLAYSTATION.md#8-the-exit-from-the-experimental-status-15-november-2026-supported-from-176)). The final panel pass of 15 November 2026 ran on the tree `6a5d9e9b`
(Windows, the players' toolchain llvm-mingw, the extended level: attract, play and an 18,000-frame route, one conversion at a time), its games delivered
to `Export/Games/PlayStation`; Gran Turismo 2's export of the same game stamp (00:34 UTC, with the owner's runtime hints) stands for it. `P` means a part
is shown and the rest is named; `?` is not measured. Nothing here says hardware fidelity, gameplay coverage or latency.

| Gate | PlayStation | Evidence | What is missing |
|---|---|---|---|
| G1 | Y | `retrorecomp/systems/psx.py` (status `supported` since 1.7.6, on the owner's decision of 15 November 2026), [PLAYSTATION.md](PLAYSTATION.md), the README, COMPATIBILITY, INDEX, ROADMAP, SYSTEM_PROFILES, STANDARDS, the release notes and the Options note in eight languages agree (`status_lint`: 0 contradictions); `tests/test_machine_registry.py` passes on the real profile, the supported tier included | | ? |
| G2 | P | `retrorecomp/psx_conversion.py` goes through `report_schema.write_report` (v2): native, interpreted and unrun instructions per route, every interpreted instruction listed by address with its reason (`interpreted_by_address`), the liveness of each route, the route warnings, the F9 validation, the shared paths' `knowledge` (what was received, the record's digest and counts), `latency_ms: null` | The report gates of `tools/release_check.py` were not run on the PlayStation's reports | ? |
| G3 | Y | The panel of 8 discs below: **0 interpreted instructions on every one of the 24 routes**, 0 unexplained (the report lists each interpreted instruction by address with its reason; there are none). 54.5 billion native instructions over the 24 routes. Two gaps of the native steps were closed on the way: a step reaching a word another step holds at that address (overlays) hands it over, and a COP2 instruction, which Beetle runs with an interrupt pending, is held too ([PLAYSTATION.md](PLAYSTATION.md)) | Only the code the routes ran is native: code reached later runs on the counted interpreter, shown in the window title (Gran Turismo 2's races: 24 % of a licence drive before the owner's hints were taken, 2.2 % after). No whole-game claim | ? |
| G4 | Y | On every frame of the 24 routes, the published game equals the observing build, which runs every instruction on Beetle's interpreter, in RAM, picture, sound **and the CPU state** (the 32 registers, LO, HI, PC, the pending load, SR, CAUSE, EPC and the GTE's 64 registers, in the per-frame trace since 1.7.6). The CPU column found two defects of Beetle's GTE quick states (carried fixes, [UPSTREAMS.md](UPSTREAMS.md#playstation-a-fix-carried-on-beetle-psx-176)) | Agreement with Beetle's interpreter, not with a real R3000A | ? |
| G5 | Y | The routes are played by the published executable (disc inside, not compressed) against a fresh reference in another process, on Windows and on a Debian 13 PC (G13) | | ? |
| G6 | P | On the 8 discs, F9 continues the saved timeline for 600 frames in a fresh process, CPU state included; a truncated state is refused | Damaged states other than a truncated file; a continuation longer than 600 frames | ? |
| G7 | Y | `tools/psx_saves_check.py`, two games, 15 November 2026. WipEout 2097: its own save menu writes `WO2097 A` on card 1 on a route; a fresh process with that card lists it, one with none shows an empty card. Gran Turismo 2: the owner saved in the delivered game (« J'ai pu aussi faire une sauvegarde sur Gran Turismo 2 qui a fonctionné »; `BASCUS-94455GAME`, 4 blocks); a fresh process given a copy of his card (`--card`, the file itself only read) differs from one with none from frame 1,045 on. On both: five unusable card files (empty, half, one byte short, one byte long, a folder) are each set aside whole as `<card>.unusable-1` and the game plays exactly as with no card. A card stays the raw 128 KiB other programs read | His first Gran Turismo 2 save of the night before did not reach the card (not explained; the second did); a full disk and a refused rename are not made; the card of slot 2 is off | ? |
| G8 | Y | `liveness` on the 24 routes: every route shows a moving picture (215 to 14,337 distinct pictures) and every route is audible (944 to 17,467 audible frames); the last picture change of every 18,000-frame route falls within 94 frames of its end | Silent routes would be reported, not refused | ? |
| G9 | Y | The routes push through menus every 900 frames and hold Cross on half the walk (1.7.6, generic, no game named). `tools/psx_route_captures.py` (which refuses a route whose rewritten script differs from the report's) took 12 pictures of each play and long route; the specialist read them: the long route reaches play on 6 of 8 (Ape Escape's first level, Final Fantasy VII's Midgar, Soul Reaver, Symphony of the Night's prologue, WipEout 2097 and R4 racing). The two that do not are named with their reason in `route_warnings` (`psx_conversion.ROUTE_STOPS`, by disc SHA-256): Metal Gear Solid goes back to its title after its level select; Gran Turismo 2 stays in its credit pages (driving was shown by a licence route made for G7, not by the conversion's routes) | Read by the specialist, not by the owner; routes do not finish a game | ? |
| G10 | P | `tools/psx_vector_selftest.py` on 8 November 2026: SingleStepTests/r3000, generated from ares's interpreter (55,000 of 55,000 on the core's interpreter, 55,000 of 55,000 on the native steps), and the GTE vectors of JaCzekanski/ps1-tests (1,150 of 1,150); the check of the check corrupts vectors and sees it on each path | The CPU vectors come from a model, not silicon, and hold no COP0 or GTE instruction; the GTE values come from a console according to their author and run on the GTE directly, not through a COP2 step | ? |
| G11 | P | `tools/psx_hardware_selftest.py` (15 November 2026): the prebuilt programs of JaCzekanski/ps1-tests (release build-158, MIT; their expected results recorded on a console by the suite's authors) boot through the player's BIOS from a small disc the tool builds (licensed volume, SYSTEM.CNF, every sector with its EDC and ECC) on the machine prepared as a conversion prepares it. GPU, the whole VRAM against the console's: in the 320x240 area the tests draw, 9 of 11 equal to the pixel (clipping, quad, rectangles, texture-flip, texture-overflow, transparency, triangle, uv-interpolation, vram-to-vram-overlap), clut-cache 99.67 % (one row: the CLUT cache is not modelled), lines 99.92 % (line ends); mask-bit prints 7 of 7 lines as the console, gp0-e1 10 of 12 | Named behaviours, not the chips. The tests that print cycle counts measured on the console differ wherever the timing does (timers 1 of 129 lines, the DMA tests 2-10 of 11-132, CD-ROM getloc 16 of 45, timing 2 of 19; the lines are compared in order); disc-swap stops at 5 of 11 lines (no lid opened); SPU and MDEC tests not run; one console's output, one BIOS | ? |
| G12 | Y | Eight discs with written reasons, none dropped, at most eight by the owner's rule: Ape Escape (the DualShock asked for), Final Fantasy VII (three discs in one EBOOT, much code), Metal Gear Solid (two discs, codec, a title it returns to), Soul Reaver (streaming, the most native steps), Symphony of the Night (2D, name entry), WipEout 2097 (PAL, CUE/BIN, CD audio), R4 (NTSC-J, CUE/BIN, the Japanese BIOS), Gran Turismo 2 (the Simulation Mode disc, the owner's choice of 14 November 2026; its Arcade disc is outside the panel). Five of them are risk cases in `tools/campaign-risk-cases.json`. All convert and pass every check above | Chosen by the specialist and the owner; the panel of 8 November (ten discs) is the earlier one | ? |
| G13 | Y | Ape Escape (EBOOT, NTSC-U) and WipEout 2097 (CUE/BIN with CD audio, PAL), converted on a Debian 13 PC with the system GCC on 15 November 2026, tree `6a5d9e9b`, from an empty library: the native, interpreted and unrun counts, the picture, sound, trace and script digests of the three routes, the native steps' digest, their count and the shared record's digest equal the Windows panel's (27 of 27 values a disc); F9 passes there. The copies of the discs and BIOS were deleted after | Not played on Linux (window, sound out, gamepad); two discs | ? |
| G14 | Y | The owner played the delivered PlayStation exports on 15 November 2026 (said of the Nintendo 64 and the PlayStation together): « Je viens de tester la Nintendo 64 et la PlayStation sur plusieurs jeux. Donc, le comportement du jeu en lui-même, ça me paraît plutôt solide et plutôt réactif. Je n'ai pas eu de bug graphique. J'ai pu aussi faire une sauvegarde sur Gran Turismo 2 qui a fonctionné. » Asked « Je sors la PlayStation de l'expérimental ? »: « Oui, sors-la » (the owner-acceptance table). On resolution, the same day: « Le 2x tient très bien. […] le 4x, ça commence à ralentir et le 8x, c'est injouable » (a written limit: 1x and 2x hold on his PC, 4x falls behind, 8x is no longer offered). Later the same day, on the stick fix delivered in Ape Escape (a stick at its very edge read as the other edge): « La correction du pad dans Ape Escape marche parfaitement » | A play test, not a coverage claim: code past the routes runs interpreted, counted and shown in the window title | ? |
| G15 | P | The audit of 8 November 2026 (report, profile, interface strings, PLAYSTATION.md), and on 15 November 2026 a read of the PlayStation's own words in the code of the game: the window title (`… | Native CPU, emulated hardware`, or `Interpreter fallback` when the interpreter runs), the keys page, the notices (resolution too heavy, card set aside). The report keeps `cpu_fidelity_validated`, `independent_cpu_oracle` and `hardware_accuracy_validated` false and `latency_ms: null` | The pages were read in the code, not captured in a window (the off-screen harness of the host kit has no PlayStation) | ? |
| G16 | P | The PlayStation shares its paths as the experimental tier of the base from 1.7.6, on the owner's decision of 14 November 2026 (« Oui, elle partage »), after the measure: a receiver at the standard level given another player's long-route observations ran Ape Escape's first level with 0 interpreted instructions instead of 924,083,036, no pass saved. `retrorecomp/psx_knowledge.py` on `path_records`: spans of the player's own discs (ISO 9660 user-data offsets, the same in every container) and rows of his own BIOS, keyed by the discs' digests; code a game decompresses stays private, counted. **Proof** (14-15 November 2026, tree `4f70b43c`, one conversion at a time, an empty library each): A extended + version 3 export, B imported + standard, C standard: Ape Escape (B received 67,257 words; long route 924,083,036 → 220,036,709 interpreted, the rest is its decompressed code) and Metal Gear Solid, two discs (51,170 words; 594 → 0); every check passes, B's own record equals C's, the same picture at the end; a record with random offsets (D) changes nothing a conversion checks ([PLAYSTATION.md](PLAYSTATION.md#6-shared-paths-the-experimental-tier-of-the-base-from-176)) | No pass saved; code a game decompresses never travels; no PlayStation path is qualified in the base yet (reached and validated by a conversion that received it from another player, counted by the site) | ? |

## Commodore Amiga: evidence behind its column (8 November 2026)

The Amiga is **supported since 1.7.5**, on the owner's decision of 14 November 2026 (open as experimental in 1.7.0; [AMIGA.md](AMIGA.md)): an Amiga 500 game installed for WHDLoad is converted, with the player's own Kickstart 1.x for the
installs that ask for one. It runs on the vAmiga machine and its 68000, Moira, the native code being translated C per opcode (the forms the translator knows) or Moira's code specialised, counted apart, behind a guard on the latched opcode. `P` means a part is
shown and the rest is named; `?` is not measured. Nothing here says hardware fidelity, gameplay coverage or latency. G2 to G9, G12, G13 and G15 are of 13 November 2026 ([the panel of 13 November](#commodore-amiga-the-panel-of-13-november-2026)); the others of 8 and 9 November.

| Gate | Amiga | Evidence | What is missing |
|---|---|---|---|
| G1 | Y | `retrorecomp/systems/amiga.py` (status `supported` since 1.7.5, on the owner's decision of 14 November 2026), [AMIGA.md](AMIGA.md), the README, COMPATIBILITY, INDEX, ROADMAP, the release notes and the Options note in eight languages agree (`status_lint`: 0 contradictions); `tests/test_machine_registry.py` passes on the real profile, the supported tier included | | ? |
| G2 | Y | `retrorecomp/amiga_conversion.py` goes through `report_schema.write_report` (v2): native and interpreted instructions per route on the 68000, the Kickstart's apart, the Blitter's counters, the per-route CPU, RAM, picture and PCM digests, every route's script digest, the quick-state validation (17 damaged states, the 600-frame continuation), the saves section and the packed replay; `native_validation.independent_cpu_oracle: false`, `latency_ms: null`. Read by `tools/release_check.py`'s report gates through the common reader on the nine reports of [the panel of 13 November](#commodore-amiga-the-panel-of-13-november-2026): conversion, native/reference, packed copy and states pass on all nine | The device section describes the Blitter (its routines and line blits are counted per route in `final_checks[].blitter`, not in the section's own scenarios), Agnus's Copper, Denise and Paula, which are emulated, not translated. The fallback gate at limit 0 lists the three Kickstart installs with their counts (G3) | ? |
| G3 | Y | [the panel of 13 November](#commodore-amiga-the-panel-of-13-november-2026), tree `be3f4483`, llvm-mingw: 0 interpreted instructions on every route (main, explore, long-1 of 18,000 frames) of Lotus 2, Lemmings, Pinball Dreams, Shadow Of The Beast, Blood Money and Apidya; the Kickstart installs list theirs, all the Kickstart's: Another World and Monkey Island 2 19 a route, Panza Kick Boxing 7. 2.37 billion native instructions over the nine. Blitter copy words in specialised routines, line blits in vAmiga's microprogram, counted apart | Only the code the routes ran is native: code reached later runs on the counted interpreter (three of Pinball Dreams' four tables, for one: [the 9 November panel](#commodore-amiga-the-panel-9-november-2026)). No whole-game claim | ? |
| G4 | Y | On every route of the nine of [the panel of 13 November](#commodore-amiga-the-panel-of-13-november-2026) and of Rick Dangerous (tree `96a70fa0`), the native game equals a fresh run of the same machine with every instruction interpreted, on every frame (picture, sound, RAM, CPU registers) and on the resload calls; the 18,000-frame routes included | The reference is the machine's own interpreter (Moira): agreement with it, not with a real 68000 (Moira against vectors is G10) | ? |
| G5 | Y | The compressed executable is replayed against the fresh reference on every route of the nine on Windows and of the installs converted on the Debian 13 PC (G13), whose Linux reports carry the same replay |  | ? |
| G6 | Y | Since 1.7.4 a state carries a checksum of the whole file and the install's identity (`RRAMIGA-STATE-3`). On all nine of [the panel of 13 November](#commodore-amiga-the-panel-of-13-november-2026): a state saved 600 frames before the end of the main route continues in a fresh process of the delivered file for 600 frames, equal to the timeline (CPU, RAM, picture, sound samples); 17 damaged states (empty, not a state, a header cut, a body cut, one byte short or longer, the last byte, and a changed magic, ABI, identity, frame, joystick, resload, snapshot size, audio size, payload or checksum) are refused with exit status 4 and left as they were; loading a missing state is refused and creates nothing (`conversion_gates.check_quick_states`). A state taken while a line's bitplane slots are batched gives them back first: `tools/amiga_display_selftest.py` saves mid-line on six scenarios and the fresh load equals the run on all six, the fault it injects seen on all six | A continuation longer than 600 frames. States of 1.7.3 are refused cleanly (another build), as for any Amiga build | ? |
| G7 | Y | `tools/amiga_saves_check.py` on two installs, two conversions each with fresh libraries. 5th Gear (8 November 2026) writes `5thgear.highs` by itself on the exploration route. Panza Kick Boxing (FR) (13 November 2026, Windows, tree `be3f4483`, llvm) saves on the route a player uses (OPTIONS, the save row, MAINTENANT): it writes `boxer.00a` and `boxer.00i` (36 bytes each, through `resload_SaveFileOffset`); a relaunch keeps them; a fresh process reads the kept file (shown through a copy with byte 8 changed: the machine differs from frame 1,148); a state saved before the files existed does not roll them back; cut to half, emptied or replaced by a folder they never stop the game (2,400 frames); a refused save (a folder where `boxer.00a` goes) is reported as DOS error 221 and the run stops on that file's call, as WHDLoad's NoError slaves do, after the other file was written, with no temporary file left and the folder untouched; a second conversion leaves one data folder and the same files | Both games saved what their install already holds (Panza's default boxers: saving after progress is the game's SI PROGRES setting, which the route does not reach), so a changed save is shown through a copy; a really full disk is not made (a refused rename is); not run on Linux; each second conversion gave the same executable byte for byte, which is not a test of a rebuild | ? |
| G8 | Y | `liveness` on every route of [the panel of 13 November](#commodore-amiga-the-panel-of-13-november-2026): every route shows a moving picture (74 to 9,761 distinct pictures) and every route but one is audible (Monkey Island 2's exploration route: 0 audible frames on its title screens; its main and long routes are audible). Replayed headless from the delivered file with the route's script checked against the report, the last picture change of the 18,000-frame route falls within 250 frames of its end on all nine (within 600 on all nine). The long routes were inspected (G9) | Silent routes are reported, not refused | ? |
| G9 | Y | The extended level plays the 18,000-frame route seeded from the install; an install that must answer a first screen (Another World's code wheel with the joystick, Monkey Island 2's protection, Lemmings' menu) starts every route with the answer, as its owner would give it, never a patch (`ROUTE_ANSWERS`). `tools/amiga_route_captures.py` (which now rewrites the answered routes and refuses a script whose digest differs from the report's) took 12 pictures of each of the 27 routes of [the panel of 13 November](#commodore-amiga-the-panel-of-13-november-2026); the specialist read them: the long route reaches play on 7 of the 8 (Lotus 2, Another World, Lemmings, Pinball Dreams, Shadow Of The Beast, Blood Money, Apidya) and on Panza Kick Boxing. The one that does not is named with its reason in its report's `route_warnings` (since 1.7.4, `amiga_conversion.ROUTE_STOPS`): Monkey Island 2's routes answer its protection and play its opening, and the long route ends in the campfire story on Scabb Island, before the first scene the player controls (Escape, which skips a scene, is not among the route's keys). The same rule as the Master System, Game Gear and Atari ST columns | Read by the specialist, not by the owner; routes do not finish a game. Monkey Island 2's delivered report is of the tree `be3f4483`, before `route_warnings`: its next conversion carries the line. An Escape in its answer is a later improvement, not made | ? |
| G10 | P | `tools/amiga_vector_selftest.py` (8 November 2026): the four SingleStepTests fixtures (6,764 vectors; the two that expect the trace exception after the instruction are left out and counted): the Amiga's native steps equal Moira's interpreter on 6,762 of 6,762 (registers, SR, PC, queue, clock, every bus access); Moira against the vectors: 6,440 agree on everything, 322 differ, all 322 in named families with a written reason and a fixed count, 0 unexplained; a corrupted vector is seen | The corpus is generated with MAME, not recorded on a chip; Moira is the Amiga's reference CPU, so the steps are checked against Moira, and Moira against an oracle of another kind; flat memory, no chip-RAM contention; no 68020 | ? |
| G11 | P | Six installs compared picture by picture with an independent emulator running the real WHDLoad (private): Lotus 2 59 of 59, Lemmings 58, Speedball 2 54, Elite 51, Turrican 2 49; Pinball Dreams NTSC 19 of 59 until looked for at any offset (all 59 then) | Counts of equal pictures on a few frames; not a fidelity claim | ? |
| G12 | Y | [the panel of 13 November](#commodore-amiga-the-panel-of-13-november-2026): eight installs with their written reasons, at most eight by the owner's rule of 13 November 2026, none dropped, all eight converted at the extended level, equal to the fresh reference on every route and delivered (Lotus 2 kept as the interface specialist built it); Panza Kick Boxing beside them for G7. The 15 installs of [9 November](#commodore-amiga-the-panel-9-november-2026), Superfrog refused with its sentence, are the earlier panel | Chosen by the specialist and approved by the lead, not by the owner. Interpreted instructions are listed; what the routes did not run is not measured | ? |
| G13 | Y | On a Debian 13 PC with the system GCC 14, from an empty library, the player's Kickstart copied for the run and deleted after: Lotus 2, Rick Dangerous, Blood Money, Apidya, Lemmings, Pinball Dreams and Shadow Of The Beast on the tree `96a70fa0` (13 November 2026) give the same CPU, RAM, picture and PCM digests, trace digests, native counts, native forms and audible frames as the Windows panel of that tree on every route (497 of 497 values); Another World, Lemmings and Monkey Island 2 on the final tree `be3f4483` (the three installs whose routes changed, two of them Kickstart installs) the same against the final Windows panel (213 of 213 values, the 19 Kickstart instructions a route included). Each Linux conversion passed its packed replay and its fresh-process state. The five other installs give the same trace digests on Windows on the two trees | Not played on Linux (window, sound out, gamepad); the Kickstart installs on the final tree only (Another World, Lemmings and Monkey Island 2), the others on `96a70fa0`, whose traces on Windows equal the final tree's | ? |
| G14 | Y | The owner played the six installs of [the checklist](#checklist-for-arthur-commodore-amiga-play-test-g14) on 14 November 2026 (the exports of 13 November in `Export\Games\Amiga`) and decided the exit: « je te valide bien que tous ces jeux marchent parfaitement. »; asked whether to take the Amiga out of the experimental status: « Oui, sors-le » (owner-acceptance table); the owner had played the ten panel installs of 6 November 2026 | Six installs played, not a coverage claim: code past the routes runs interpreted, counted and shown in the window title. Not converted: Kickstart 3.x installs, ADF disks, the Amiga 1200 | ? |
| G15 | Y | The audit of 8 November 2026 (report writer, profile, strings in eight languages, AMIGA.md, the caveat, UPGRADES, README, COMPATIBILITY, SYSTEM_PROFILES, INDEX, CPU_68000, the adapter and the player), its findings applied; and on 13 November 2026 an exported game read in its window on a hidden desktop: Lotus 2 (tree `96a70fa0`) titled `Lotus 2 | Commodore Amiga | Native CPU, emulated hardware`, Another World (tree `be3f4483`, the new interface) titled `... | Interpreter fallback` (it runs 19 Kickstart instructions on the interpreter); the F1, F2 and F12 pages and messages of both claim no exactness, latency or whole-game native code. The report keeps `independent_cpu_oracle: false`, `hardware_accuracy_validated` false and `latency_ms: null` | The wording of `rr_resload.c` was searched for claim words, not read line by line | ? |
| G16 | P | The Amiga shares its paths as the experimental tier of the base since 1.7.5, on the owner's decision of 14 November 2026 (« Oui, partage direct »): `retrorecomp/amiga_knowledge.py` on the common part of the 68000 computers (`m68k_media_knowledge.py`, the X68000's, whose outcomes a test pins). Numbers only: runs of observed RAM code found as they are in the player's own install, Kickstart instructions of the player's own image; what a game unpacks stays private and is counted. **Proof (14 November 2026, tree `ceed7b28`, llvm, one conversion at a time, three players each with its own data folder):** player A converted Lotus 2, Lemmings and Another World (FR) at the extended level (records of 736, 1,289 and 352 spans, Another World's with 19,760 Kickstart rows) and exported them (a version 3 file, 22,137 paths); player B imported that file into an empty library and converted the three at the standard level, every check passing; player C converted them the same way with nothing imported. B against C: one pass each; the same instructions still interpreted after it (0 and 0, 0 and 0, 38 and 38, the Kickstart's); the same native counts on the routes; wall time 391 and 420 s, 663 and 680 s, 695 and 690 s; the received paths offered 8,848, 3,847 and 22,353 instructions, of which B's own fresh runs reached 8,246, 3,780 and 21,791 and 602, 67 and 562 were made native by the paths alone (`knowledge.received`); with the sweep, B generated 20, 0 and 489 native instructions more than C, of about 37,000. The library keeps its own observations on the player's PC: one that cannot be read or is past the bound of an observation is ignored, and a conversion that fails after merging it is tried once more without it (Rick Dangerous at the quick level with a valid 13.6 MB file of 1,048,577 lines: ignored, ready in 6 min 34 s, the report says so, the file is replaced by the run's own 4,896 lines). | No pass saved and little native code added on these routes. The gain beyond the routes was not measured on the Amiga: the decision rests on the shared mechanism and on the Atari ST's Turrican II (its unpacked code tied to the player's own disk: about 90 % fewer interpreted instructions on a route beyond the receiver's own). No Amiga path is qualified in the base yet (reached and validated by a conversion that received it from another player, counted by the site, whose side is deployed with the release). Monkey Island 2's files are packed: none of its observed code travels | ? |

## Nintendo 64: evidence behind its column (15 November 2026)

The Nintendo 64 is **supported since 1.7.6**, on the owner's decision of 15 November 2026 (open as experimental in 1.7.1; [NINTENDO_64.md](NINTENDO_64.md)). It runs on a complete emulator core
(Mupen64Plus-Next with ParaLLEl-RSP and ParaLLEl-RDP) whose VR4300 code the conversion makes native as guarded blocks; the gates are read as
for the Amiga and the Atari ST ([what "met" means](NINTENDO_64.md#what-met-means-for-the-nintendo-64-the-target-for-leaving-the-experimental-status-14-november-2026)).
The evidence is [the panel of 15 November 2026](NINTENDO_64.md#the-panel-of-15-november-2026-176): eight PAL cartridges at the Extended level,
Windows (llvm-mingw, an NVIDIA GeForce RTX 3090, tree `7b33bd9d`) and a Debian 13 PC (GCC, an Intel HD Graphics 520, tree `4d41dd6a`, the
same blocks and traces: the later commit adds only the quick state's checksum). Nothing here says hardware fidelity, gameplay coverage or latency.

| Gate | Nintendo 64 | Evidence | What is missing |
|---|---|---|---|
| G1 | Y | `retrorecomp/systems/n64.py` (status `supported` since 1.7.6, on the owner's decision of 15 November 2026); NINTENDO_64.md, README, COMPATIBILITY and the interface say so; `tools/status_lint.py` finds no contradiction | | ? |
| G2 | Y | `n64_conversion` writes the common report v2; `tools/release_check.py`'s report gates read the eight panel reports through the common reader: conversion, native against reference, fallback, packed copy and states pass on all eight | The report has no device section: the RSP and the RDP are the core's, named as emulated | ? |
| G3 | Y | Every interpreted VR4300 instruction of every route is listed where it ran (address, word, count, class) and the counts add up on 20 of 20 routes (`final_checks[].interpreted_sites_complete`; the report gives the totals by class and the 256 most run sites, the whole listing is a file of the qualification folder named with its SHA-256). Classes: the boot code (about 169,000 instructions a route), mapped pages never observed (20 to 110,275), guard misses (0 to 291,783), the generator's coverage cut (the rest); none unseen. 99.25 % to 99.79 % native a route | The coverage cut (the rarest 0.5 % of the executions) is left with its reason: covering it triples the blocks for half a point. Code past the routes runs interpreted, counted | ? |
| G4 | Y | Every route of the eight (20 routes, up to 16,800 frames) equals a fresh run of the same core with the VR4300 on its pure interpreter, every frame (picture, sound, RDRAM, CPU registers); native plus interpreted equals the reference's count but the instruction in flight | The reference is the core's interpreter: agreement with Mupen64Plus, not with a VR4300 (G10) | ? |
| G5 | Y | The compressed program is replayed on every route of the eight against the same reference, on Windows and on the Debian 13 PC (the common fallback delivers the build unpacked when a compressed copy fails twice: not needed on this panel) | | ? |
| G6 | Y | `conversion_gates.check_quick_states` on every conversion: a state saved on the main route, loaded by a fresh process given the save memory as it was, continues 400 frames (CPU, RDRAM, picture and sound); 16 damaged copies refused (exit 4) and left as they were; a missing state creates nothing (format `RRN64QS5`, with a checksum) | | ? |
| G7 | Y | `tools/n64_saves_check.py` on the delivered programs: EEPROM 4 Kbit (Super Mario 64, GoldenEye 007), 16 Kbit (Banjo-Tooie), SRAM (Ocarina of Time, F-Zero X), Flash (Majora's Mask) and the controller pak (Rayman 2), each written by its route: a fresh process reads the kept file (a copy with one byte changed makes RDRAM differ), reading leaves it as it was, an earlier quick state does not roll it back, a cut, empty or folder file never stops the game | The Transfer Pak and the 64DD are not supported | ? |
| G8 | Y | A moving picture is required on the main route; liveness of every route in the report; captures of every play route read | | ? |
| G9 | Y | Every panel game reaches play: play routes of their own for Super Mario 64, Ocarina of Time, Majora's Mask and Rayman 2; the main route races in Mario Kart 64 and F-Zero X, reaches Spiral Mountain in Banjo-Tooie and the Dam in GoldenEye 007 | Generic routes of games outside the panel may stay in menus | ? |
| G10 | P | `tools/n64_cpu_tests.py`, 15 November 2026: krom's 114 CPU test programs (PeterLemon/N64 at `7085543`, public domain; CPU, COP0, COP1, exceptions, PI DMA alignment), each run on the core's pure interpreter for 200 frames and its own verdict read on its picture (PASS and FAIL in its result column; the 13 floating-point compare tables against krom's reference picture): **90 pass**. 22 fail in named families, each the core's behaviour: the two timing tests (no cycle model), the exception tests (Syscall 4, Trap 2, TLB miss 6, Compare 1: on the four pictures read, the Status register after the exception), unaligned accesses that raise no exception (2), CAUSE's initial and written values (1), PI DMA from the cartridge at odd alignments (4); one draws no verdict (COP1 full mode, a table without PASS or FAIL) and one stops the reference player (LL, LLD, SC, SCD). Programs also converted like games (COP0 Cause and Register, COP1 ABS, ADD and C.EQ, and the sample of the night's summary): the native blocks equal the interpreter on every frame and draw the same verdicts | The tests and the interpreter are not silicon; krom's reference pictures were not made on our side. No VR4300 vectors exist; nemu64-tests not run (it needs a Rust nightly toolchain, a download not made). The failures are the core's (Mupen64Plus), reproduced by the native blocks, not fixed here | ? |
| G11 | ? | Not measured | No comparison with a console or another emulator | ? |
| G12 | Y | The panel of eight, none dropped, converted on Windows and on the Debian 13 PC; every route has the same trace hash and the same native and interpreted counts on both | | ? |
| G13 | Y | Same as G12: the traces of the eight games' 20 routes byte for byte equal on Windows and on a Debian 13 PC with integrated graphics; the compressed copy replayed on both | Nothing was played on Linux (window, sound, pad) | ? |
| G14 | Y | The owner played the eight exports of [the checklist](#checklist-for-arthur-nintendo-64-play-test-g14) on 15 November 2026: « Je viens de tester la Nintendo 64 et la PlayStation sur plusieurs jeux. Donc, le comportement du jeu en lui-même, ça me paraît plutôt solide et plutôt réactif. Je n'ai pas eu de bug graphique. » F-Zero X's remark is closed (« c'est le jeu »); his decision the same day takes the Nintendo 64 out of the experimental status (owner-acceptance table) | A play test, not a coverage claim: code past the routes runs interpreted, counted | ? |
| G15 | Y | The report sets `hardware_accuracy_validated: false`, `full_game_validated: false`, `latency_ms: null`; the pages keep the five measures apart and say the N64 is not a fully recompiled system | | ? |
| G16 | - | Declined on the owner's decision of 15 November 2026 (« Ça me paraît bien faible pour partager les chemins. Si on a que 10% de gain max, […] on va sortir Nintendo de l'expérimental, mais on va pas partager les chemins. »): a received path would make native, beyond the receiver's own routes, 2.3 % to 11.5 % of a play route's instructions at the Standard level (the panel), a gain judged too small, not nil; `DECLINED['path_sharing']` in `tests/test_machine_registry.py` | The interpreted share stays counted and shown: 2.3 % to 11.5 % of a play route at the Standard level, 0.2 % to 0.75 % at the Extended level | ? |

### Checklist for Arthur: Nintendo 64 play test (G14)

A checklist, not a record: the verdicts and the notes are yours. Play the **delivered executables** in `Export/Games/Nintendo 64/` (converted on
15 November 2026 from the tree `7b33bd9d`, Extended level, online covers on; nothing here asks you to convert anything). Eight games, about ten
minutes each. A tick means "it looked and sounded right to you in this test"; nothing here says exact hardware, complete gameplay or latency.

| | Super Mario 64 | Mario Kart 64 | F-Zero X | Banjo-Tooie | GoldenEye 007 | Rayman 2 | Majora's Mask | Ocarina of Time |
|---|---|---|---|---|---|---|---|---|
| Why it is here | the control; EEPROM | EEPROM and pak | SRAM; your open remark (vibration, vehicles' detail) | EEPROM 16 Kbit; the state's sound | its code under the TLB | saves on the controller pak | Flash; a long intro | SRAM; overlays |
| It starts without an error window | | | | | | | | |
| Stick and buttons answer (a gamepad is player 1; **F1** shows the keys) | | | | | | | | |
| Sound is the game's (music and effects) | | | | | | | | |
| **F8** in play, move on, **F9** goes back to the saved moment, sound included | | | | | | | | |
| Close the window, start again, **F9** loads the state saved before | | | | | | | | |
| **F3** graphics page: the picture stays right at another internal resolution | | | | | | | | |
| Nothing odd: a frozen picture, silence, wrong colours, a crash | | | | | | | | |

Then three checks:

1. **A save made in the game.** In Super Mario 64 collect a star (or in Ocarina of Time save at a save prompt), quit, start again: the file
   must be there. The cartridge save and the paks are kept in `datas/games/n64-<identity>/saves.bin`.
2. **The controller pak.** In Rayman 2 start a new game, quit, start again and choose Load: the slot must be listed.
3. **A game of your own.** Convert one cartridge of the library that is not in this list and play it like the others: which one, and what it
   did, is the most useful line of this checklist.

Known limits to keep in mind: no 64DD, Transfer Pak or VRU; the boot code and the rarest code run interpreted, counted; frame pacing is
uneven in Ocarina of Time and not yet timed again; F-Zero X's two remarks are an open item. Keep the five measures apart when you judge.

| Date | Console | Games tried | Verdict | Notes |
|---|---|---|---|---|
| 15 November 2026 | Nintendo 64 | The eight exports of this checklist | « Je viens de tester la Nintendo 64 et la PlayStation sur plusieurs jeux. Donc, le comportement du jeu en lui-même, ça me paraît plutôt solide et plutôt réactif. Je n'ai pas eu de bug graphique. » | F-Zero X: « non, non, ça vibre pas. […] c'est le jeu, donc j'ai pas de problème avec F-Zero. Ça marche très bien. » Asked about the sharing: « Ça me paraît bien faible pour partager les chemins. Si on a que 10% de gain max, […] on va sortir Nintendo de l'expérimental, mais on va pas partager les chemins. » |

## Panel sizes

No common panel size exists today. The panel sizes noted by the 27 October
2026 inventory are: Neo Geo 24+10, Mega Drive 24+8, Super Nintendo DSP-1/CX4
8, Super FX 9, NES 8+10+8+6, Game Boy 606, Master System 258, CPS-1 26,
X68000 21 (19 before 2 November 2026), PlayStation 10. Whether G12 needs a common threshold is a policy decision that has
not been recorded; for CPS-1 the owner chose, on 1 November 2026, "every set of the perimeter he owns".

### Sharp X68000: the panel (2 November 2026)

**Written rule.** The panel is 21 named games of the owner's collection (option B of 2 November 2026), each chosen for at least one reason in
these categories, and none is ever dropped because it fails: a failure becomes a line of [KNOWN_FAILURES.md](KNOWN_FAILURES.md), not an absence.
The categories are the structure of the floppies (1, 2, 3, 4 and 5 disks, the largest set of the collection has 5), their behaviour (an automatic
disk change, a refusal then the next disk, an eject after loading), the mouse (read through the system calls or through the SCC chip, and a
mouse that wakes a sound), the sound (a silent route accepted, a sound that starts after a click), the picture mode (15 kHz at 55.46 frames a
second, 31 kHz at 61.46), the sets that used to stop, and a spread of genres. Each game is converted at the Standard level from an empty
library, one conversion at a time, on Windows, and again on Debian (the 1.6.6 source, whose X68000 game stamp equals this tree's) with a temporary
copy of the disks that is deleted afterwards. R-Type is converted once more with the 4 MiB option (the option, not a game of the panel).

| Game | Why it is in the panel |
|---|---|
| R-Type (Irem) | one disk, 15 kHz, the release-check game |
| Metal Sight (System Sacom) | 5 disks (the largest set), 31 kHz, automatic disk changes (2 on the routes) |
| Lemmings (Imagineer) | the mouse through the SCC chip |
| Super Hang-On (Sharp / SPS) | 2 disks ejected after loading, a long load, 31 kHz |
| Metal Unit II Power Unit | 3 disks, the third after a refusal |
| Tricorn Final (Xain) | 4 disks, 15 kHz |
| Cranked Arrow (Fukuda Naoto) | 3 disks, another maker |
| Choujin (Fix) | 2 disks ejected after loading, 31 kHz |
| Tetris v5 (Cyber Factory) | stopped the reference (CRTC reprogrammed during a line), fixed in 1.6.5 |
| TF4G v0.3A09 | the same cause, fixed in 1.6.5 |
| Pensan CD (Tanaka Yuu) | silent on its keys, its music starts after a click |
| Uno | silent on every standard route, a card game played with the mouse |
| Boyon Boyon | silent on the main route, sound on the mouse route |
| Populous (Imagineer) | the mouse through the SCC chip |
| Cameltry (Denpa) | the mouse through the SCC chip, 31 kHz |
| Dungeon Master (FTL) | 2 disks (System and User), the mouse |
| Afterburner II (Dempa) | 2 disks, 31 kHz |
| Star Luster (Dempa) | one disk, 31 kHz, 3D |
| Nemesis '94 Gradius 2 | horizontal shooter, one disk, 15 kHz |
| Quarth (Konami) | puzzle, one disk |
| Bubble Bobble (Dempa) | arcade port, one disk |

**Result (Windows, 2 November 2026, 1.6.6 tree).** All 21 convert and are delivered (110 to 226 seconds each on the build PC), with 0 interpreted
opcodes on the main, mouse and keyboard routes, the compressed copy matching the reference, and the F8/F9 state resumed in a fresh process.
Uno is accepted as silent (its report says so); every other game has sound on at least one route. Metal Sight shows its 2 automatic disk changes; the other
multi-disk sets show none on these routes (their disk requests, if any, come later in the game: not observed). R-Type at 4 MiB gives the same pictures
as at 2 MiB.

**Result (Debian, same day).** 20 of the 21 convert and are delivered with the same CPU, RAM, picture and PCM hashes as Windows on every
route. The 21st, Choujin, was refused on Debian at the replay of its compressed copy: the UPX-compressed program stops at start (SIGTRAP) with
`-9`, `-1` and `--lzma`, although `upx -t` passes and the program UPX unpacks from it is byte for byte the one that was validated and runs. Converted on
Debian with `--no-compress` it gives the same hashes as Windows. This is the packing step shared by every console, not the X68000
([KNOWN_FAILURES.md](KNOWN_FAILURES.md)). With the shared fallback of 1.6.7 (main at 1aa7ddd, 3 November 2026) the same conversion on Debian succeeds:
the journal says the compressed copy failed its replay and the unpacked build is replayed instead, `native_validation.packed_reference_match` is true,
`packing.packed` is false with `unpacked_reason` ("... twice ..."), and the published file has the SHA-256 of the validated build; a witness game of the
panel (R-Type) stayed compressed, with no fallback line. So 21 of the 21 are delivered on Debian, one of them unpacked. These checks say that the native code, the picture and the sound of the routes run are the same on the two systems;
they say nothing of complete gameplay, exact hardware or latency.

### Sharp X68000: scope and follow-ups at the exit (5 November 2026)

**What the exit stands on.** The column above, with every gate `Y` except G10 and G11, which stay `P` as they do for the other supported 68000
machines (G10: 22 of 2,895 vectors of undefined decimal arithmetic; G11: MAME, a model and not hardware). The owner decided with both open, after the
play trials of 3 and 5 November 2026. Nothing here says exact hardware, complete gameplay or physical latency.

**Scope stated at the exit** (also in [X68000.md](X68000.md#8-known-limits)): floppy games only; no hard-disk images, no set of more than ten
disks, no copy-protected D88; the few games that play only through an external Roland MIDI module run silent and the report says so (a decision
of 29 October 2026 for this machine only); the mouse and the keyboard are checked by routes and by play on a few games; saves are proved by an
authored program and by file time stamps of real games; the machine shares its paths as the experimental tier of the base (G16 `P`); the screen contrast of the system port is a
known difference with MAME, not changed.

**Follow-ups** (none of them blocks the exit; each can move a hash and says so when it does): the sound of the five games compared with MAME
(the CPS-1's is within 0.42 dB), the colours compared on the four games that have none, the ten pictures of MAME that no picture of the game matches
(Lemmings 5, Star Luster 4, Bubble Bobble 1), authored vectors for the long immediate forms with a memory destination, the thorough scan level and
disk requests late in a game, a game that saves on purpose, interactive play witnessed on Linux, a new review of the px68k upstreams, and a first X68000 path qualified by the conversion of another player (G16 `Y`).

**Replay on the tree of the exit (5 November 2026, Windows).** The 21 games of the panel and R-Type at 4 MiB were converted again with the tree of the exit commit (standard level, an empty private library for each, no shared base, no online cover, two conversions at a time, 122 to 325 seconds each): **0 interpreted opcodes on all 66 routes** (22 conversions, three routes each), the compressed copy matching the fresh reference on all 22, F8/F9 resumed in a fresh process on all 22, the report says `supported`, sound on 21 of the 22 (Uno is accepted as silent, as before) and the two automatic disk changes of Metal Sight. Against the panel of 2 November (the 1.6.6 tree): the **CPU, RAM and PCM hashes are equal on all 66 routes**; the picture hashes differ on all 66, as expected (the 1.6.7 colour of the intensity bit, [UPGRADES_HISTORY.md](UPGRADES_HISTORY.md)); the numbers of different pictures and of audio blocks of every route are equal. Two further conversions (Twins, Fancy Qix) against the 1.6.8 tree give 513 values each of which only the status and the timings differ: the CPU, RAM, picture and PCM hashes and the trace digest of the three routes are equal. **Replay on Debian (5 November 2026, a Debian 13 PC, the same tree, one conversion at a time, disks copied for the run and deleted after):** the 21 games convert and are delivered, with 0 interpreted opcodes on every route and the compressed copy matching; across the 21 games and 63 routes the **CPU, RAM, picture and PCM hashes are equal to the Windows replay** (no difference), as are the numbers of pictures and audio blocks, the sound routes, the disk changes and the state checks. Choujin, which Debian delivered unpacked in the 2 November panel, now packs on Debian like the others (the Linux packer keeps NRV, [UPGRADES.md](UPGRADES.md)).

## Owner acceptance

Owner play tests (gate G14), one row per test. The table starts empty; the
owner fills it in.

| Date | Console | Games tried | Verdict | Notes |
|---|---|---|---|---|
|  |  |  |  |  |
| 1 November 2026 | Capcom CPS-1 | none (decision on the evidence, no game played for this row) | Exit from the experimental status validated by Arthur on the basis of the 1.6.6 evidence | The play trial list of `CPS1_ACCEPTATION.md` is still to do on the 1.6.6 executable. The owner trials of 27 October 2026 were reported in chat and are not recorded here. |
| 1 November 2026 | Mega Drive | none recorded (owner acceptance, no game list written) | accepted by the owner (Arthur), who uses these machines and validated them as supported; no written play checklist for this row | Recorded on 1 November 2026 at the maintainer's confirmation of the `Y` of the matrix. |
| 1 November 2026 | Neo Geo | none recorded (owner acceptance, no game list written) | accepted by the owner (Arthur), who uses these machines and validated them as supported; no written play checklist for this row | Recorded on 1 November 2026 at the maintainer's confirmation of the `Y` of the matrix. |
| 3 November 2026 | Nintendo NES | The Legend of Zelda, Kirby's Adventure, Mr. Gimmick, Duck Hunt, Battletoads, Castlevania III, converted with the 1.6.7 tree in a player's conditions and delivered in `Export` | Arthur: "je viens de faire mes essais NES, CPS et X68000, on est bon" | The trial list of the NES checklist below; G14 `Y`. |
| 3 November 2026 | Capcom CPS-1 | 1941, Street Fighter II' Champion Edition, Final Fight, Captain Commando, Strider, Mercs, converted with the 1.6.7 tree (generator revision 12) in a player's conditions and delivered in `Export` | Arthur: "je viens de faire mes essais NES, CPS et X68000, on est bon" | The play trial list of `CPS1_ACCEPTATION.md`, which the row of 1 November left to do; G14 moves from `P` to `Y`. |
| 6 November 2026 | Capcom CPS-2 | The 17 sets of the final pass, delivered in `Export\Games\CPS-2` (the exit tree, extended level) | Arthur, after playing the 17 delivered files, on 6 November 2026: « Je viens de tester tous les jeux CPS2, tout marche parfaitement. Il y a juste un léger freeze qui arrive lorsqu'on insère une pièce. Peut-être que c'est normal, peut-être que c'est pas grand-chose. En tout cas, tout est fonctionnel. Donc, à voir ce qu'on peut faire pour ça. Et après, on sort le CPS2 de l'expérimental. » | The decision to leave the experimental status, given once the hitch on a coin is looked at: G14 moves from `P` to `Y`. The hitch was the EEPROM file written on the frame; it is now written off the frame ([UPGRADES.md](UPGRADES.md)). After trying the redelivered CPS-2 games on 6 November 2026, Arthur confirmed: « je viens de tester le CPS2, tu peux le sortir de l'expérimental, ça marche parfaitement. » It says nothing of the DSP16, of hardware fidelity, of the other sets or of latency. |
| 5 November 2026 | Capcom CPS-2 | The eight panel sets (`ssf2`, `ddtod`, `dimahoo`, `xmvsf`, `mvsc`, `msh`, `sfa3`, `mmatrix`), converted with the tree of the branch `spec/cps2-170` at `1b5ae31` and delivered in `Export\Games\CPS-2` | Arthur, after a first trial of the development builds (« Il y en a qui démarrent parfaitement avec le son et tout. Il y en a quelques-uns qui ne démarrent pas. »), then on the delivered files: « Je viens de faire une campagne de test des jeux CPS-2 et PC Engine. J'ai testé les 8 jeux de chaque console et les 8 marchent parfaitement. Bravo ! »; he also agreed to open the machine as experimental: « OK pour CPS2 en expérimental sur la 1.6.9. » | A successful play trial, **not** a decision to leave the experimental status: G14 is `P`. It validates how the eight games behave; it says nothing of the DSP16 (a model after MAME's), of hardware fidelity, of the other 228 sets or of latency. |
| 5 November 2026 | Capcom CPS-1.5 (QSound boards) | The Punisher, Cadillacs and Dinosaurs, Warriors of Fate, converted with the 1.6.8 tree (`cc46a1b`, generator revision 12) in a player's conditions and delivered in `Export` | Arthur, after playing them: « Tu peux aussi sortir le CPS 1.5 de l'expérimental. Je valide le comportement des jeux dessus (ça marche très bien). » (the day before, about these games and the Sharp X68000 ones: « Les deux marchent parfaitement ») | G14 `Y` for the QSound boards: they leave the experimental tier and join the CPS-1 and the shared base of paths. It validates how the games behave; it says nothing of the DSP16 (a model after MAME's), of hardware fidelity or of latency. |
| 3 November 2026 | Sharp X68000 | R-Type, Metal Sight, Lemmings, Super Hang-On, Bubble Bobble, converted with the 1.6.7 tree in a player's conditions and delivered in `Export` | Arthur: "je viens de faire mes essais NES, CPS et X68000, on est bon" | The play test passed. It is not a decision to leave the experimental status: G10 and G11 are still `P`, and the exit stays the owner's explicit decision once every gate is proved. G14 is `P`. |
| 5 November 2026 | Sharp X68000 | Double Target, Fancy Qix, Twins, Danger Area, Pac-Land, drawn at random (seed 20261105) among the games of his collection not yet in `Export`, converted with the 1.6.8 tree in a player's conditions and delivered in `Export` | Arthur: « Bon, je viens de tester les derniers jeux que tu m'as sortis là sur Sharp X68000 et sur le CPS. Les deux marchent parfaitement. Tu peux sortir le Sharp de l'expérimental, même si on aura forcément quelques évolutions à faire derrière. » | The decision to leave the experimental status, given with G10 and G11 still `P`; it also counts as his last trial on the tree of the exit, whose commit changes the status written in the report and nothing in the player. G14 `Y`. |
| 5 November 2026 | Master System | Sonic The Hedgehog, Wonder Boy III - The Dragon's Trap (banked engine), converted with the tree of `main` at `491e845` in a player's conditions (0 interpreted instructions on the tested routes) and delivered in `Export` | Arthur, after playing them: « Je viens de tester tous les jeux de toutes les consoles dernièrement sorties. Tout marche parfaitement bien pour le g14. » | G14 moves from `?` to `Y`. A play test of two games: it says nothing of hardware fidelity or latency. |
| 5 November 2026 | Game Gear | Sonic The Hedgehog, Super Columns (banked engine), converted with the tree of `main` at `491e845` in a player's conditions (0 interpreted instructions on the tested routes) and delivered in `Export` | Arthur, after playing them: « Je viens de tester tous les jeux de toutes les consoles dernièrement sorties. Tout marche parfaitement bien pour le g14. » | G14 moves from `?` to `Y`. A play test of two games: it says nothing of hardware fidelity or latency. |
| 5 November 2026 | Game Boy | The Legend of Zelda: Link's Awakening, Kirby's Dream Land, converted with the tree of `main` at `491e845` in a player's conditions (0 interpreted instructions on the tested routes) and delivered in `Export` | Arthur, after playing them: « Je viens de tester tous les jeux de toutes les consoles dernièrement sorties. Tout marche parfaitement bien pour le g14. » | G14 moves from `?` to `Y`. A play test of two games: it says nothing of hardware fidelity or latency. |
| 5 November 2026 | Super Nintendo | Super Mario World, The Legend of Zelda: A Link to the Past, converted with the tree of `main` at `491e845` in a player's conditions (0 interpreted instructions on the tested routes) and delivered in `Export` | Arthur, after playing them: « Je viens de tester tous les jeux de toutes les consoles dernièrement sorties. Tout marche parfaitement bien pour le g14. » | G14 moves from `?` to `Y`. A play test of two games: it says nothing of hardware fidelity or latency. |
| 10 November 2026 | PC Engine / TurboGrafx-16 | The fifteen exports of the release tree `cf6d56fa` in `Export\Games\PC Engine` (Blazing Lazers, Bomberman '93, Bonk III, Bonk's Adventure, Boxyboy, Gradius, Legend of Hero Tonma, Military Madness, Neutopia II, Raiden, Santatlantean, Soldier Blade, Space Harrier, Splatterhouse, Street Fighter II' - Champion Edition), converted at the extended level in a player's conditions (0 interpreted instructions on the routes played) and delivered on 9 November 2026 | Arthur, after playing them: « ils marchent tous parfaitement. Les sauvegardes marchent parfaitement. Tout est ok »; then « Oui, oui, tu passes le PC Engine et TurboGrafx FX en supporté ». On the speed measure (Blazing Lazers 1.09x and Street Fighter II' CE 1.04x the frame cost of the 1.7.1 pin): « je valide comme ça ». On the interpreted code shown after Start on Boxyboy: « on va améliorer les consoles au fur et à mesure » | The decision to leave the experimental status: G14 moves from `P` to `Y`, and the PC Engine is supported in 1.7.2. A play trial of fifteen cards: code past the routes runs interpreted, counted and shown in the game (the owner saw it on Boxyboy after Start), and a PC Engine game keeps no player's record yet, so the code a player reaches is not made native at the next conversion. It says nothing of hardware fidelity, whole-game coverage or latency. |
| 5 November 2026 | PC Engine | Blazing Lazers, Bomberman '93, Gradius, Raiden, Santatlantean, Space Harrier, Splatterhouse, Street Fighter II' Champion Edition (the eight HuCards of `Export\Games\PC Engine`), converted with the tree of `spec/pce-170` **before** its merge of `main` (commits up to `ad4d7ec`, the host kit without the four-player change; every one 0 interpreted instructions on the tested routes except Street Fighter II', which keeps a counted interpreted share) in a player's conditions and delivered in `Export` | Arthur, after playing them: « Je viens de faire une campagne de test des jeux CPS-2 et PC Engine. J'ai testé les 8 jeux de chaque console et les 8 marchent parfaitement. Bravo! » | A play trial that passed, **not** a decision to leave the experimental status: the PC Engine stays experimental and G14 reads `P`. The exports played come from a tree older than the one that opens the machine in 1.6.9 and are not the exports of that tree. |
| 6 November 2026 | Commodore Amiga | The ten panel installs (Rick Dangerous, Lemmings, Elite, Pinball Dreams NTSC, Speedball 2, Turrican 2, Shadow of the Beast, Lotus 2, Cannon Fodder, Prince of Persia), converted with the tree of `spec/amiga-170` at `977cf63e` (the display window and the middle click included) and delivered in `Export\Games\Amiga`; every one 0 interpreted instructions on its two routes of 3,000 frames | Arthur, on a first build of the panel the same morning: « ça marche parfaitement », apart from a large black frame and a picture that did not grow with the window (both fixed in `31d7da35`); then on these exports: « je viens de tester les jeux Amiga, c'est nickel » | A play trial that passed, **not** a decision to leave the experimental status: the Amiga stays experimental and G14 reads `P`. It says nothing of hardware fidelity, of the installs that need a Kickstart, of other games or of latency. |
| 8 November 2026 | Nintendo 64 | Super Mario 64, The Legend of Zelda: Ocarina of Time, Mario Kart 64 (PAL), converted at the Standard level with the tree of the branch `spec/n64-171` at `9380f67c`, delivered in `Export\Games\Nintendo 64` | Arthur, after playing the three: « Globalement, ça se passe bien. Pour moi, c'est OK pour la version expérimentale. On a encore quelques bugs, bien sûr. » He found Super Mario 64's text unreadable. This is his go for the experimental opening, not an exit from it: the games he played predate the correction of that text (hidden RDRAM, [NINTENDO_64.md](NINTENDO_64.md#6-evidence)). |
| 14 November 2026 | MSX, MSX2 | The six games of the checklist (Knightmare, Salamander, Dragon Slayer II - Xanadu (MSX), Metal Gear, Space Manbow, Aleste (MSX2)), the panel exports of 14 November 2026 in `Export\Games\MSX` and `Export\Games\MSX2` (tree `d0b32436` of `spec/msx-175`, extended level, C-BIOS 0.29a) | Arthur, after playing them: « Donc, je viens de tester les jeux MSX1 et MSX2, ça marche impeccable. Tu peux les sortir de l'expérimental. » | Exit from the experimental status decided: the MSX and the MSX2 are supported from 1.7.5; the MSX2+ stays experimental. The stamp move of the status change is handled by the 1.7.5 update, as for the PC Engine; the exports are not converted again |
| 14 November 2026 | Commodore Amiga | The six games of the checklist (Lotus 2, Another World (FR), Monkey Island 2, Lemmings (Image), Pinball Dreams (NTSC), Panza Kick Boxing (FR)), the exports of 13 November 2026 in `Export\Games\Amiga` (tree `be3f4483` of `spec/amiga-176`, extended level, llvm-mingw; Lotus 2 as the interface specialist built it) | Arthur, after playing them: « je te valide bien que tous ces jeux marchent parfaitement. »; asked whether to take the Amiga out of the experimental status: « Oui, sors-le » | Exit from the experimental status decided: the Amiga is supported from 1.7.5. The stamp move of the status change is handled by the 1.7.5 update, as for the PC Engine and the MSX; the exports are not converted again. A play test of six installs, not a coverage claim: code past the routes runs interpreted, counted and shown in the window title. |
| 14 November 2026 | Atari ST | The seven games of the checklist (Bomb Jack, Turrican II (the player's TOS 1.04), Operation Stealth, The Lurking Horror, Kick Off 2, Lethal Xcess, Battle Probe), the exports of 14 November 2026 in `Export\Games\Atari ST` (built by the batch from the tree of `spec/atarist-175`, Standard level, llvm-mingw, online covers on) | Arthur, after playing them: « Ok, donc Atari ça marche, nickel, j'ai testé les jeux. »; asked "Je sors l'Atari ST de l'expérimental ?": « Oui, sors-le » | Exit from the experimental status decided: the Atari ST is supported from 1.7.5. The stamp move of the status change is handled by the 1.7.5 update, as for the PC Engine, the MSX and the Amiga; the exports are not converted again (they predate the interface merge: the 1.7.5 reconversion brings the pad quick save and load rows he found missing). A play test of seven games, not a coverage claim; the STE, the Mega STE, the TT, the Falcon, hard disks and the monochrome monitor are not converted. |
| 14 November 2026 | Game Boy Advance | The six games of the checklist (Golden Sun, Mario Kart Super Circuit, The Minish Cap, Crazy Taxi: Catch a Ride, F-Zero: Maximum Velocity, Pokémon Emerald), the exports of 14 November 2026 in `Export\Games\Game Boy Advance` (built from the final tree of `spec/gba-175`, empty library, online covers on, llvm-mingw) | Arthur, after playing them: « Moi, je viens de tester les jeux Game Boy Advance. Donc ça marche parfaitement. Ils se comportent de manière parfaite. »; asked "Je sors la GBA de l'expérimental pour la 1.7.6 ?": « Oui, sors-la » | Exit from the experimental status decided: the Game Boy Advance is supported from 1.7.6 (1.7.5 was frozen the same morning). The stamp move of the status change is handled by the 1.7.6 update; the exports are not converted again. A play test of six games, not a coverage claim: no level won, no latency or hardware-fidelity measure; G10, G11 and G16 stay `P`. |
| 14 November 2026 | MSX2+ | The six games of the checklist (Family Stadium Professional Baseball, The Goonies R Good Enough, Dragon Slayer II - Xanadu, Laydock 2 - Last Attack, F-1 Spirit 3D Special, Xak III - The Tower of Gazzel), the exports of 14 November 2026 in `Export\Games\MSX2+` (tree `05f8d828` of `spec/msx2plus-176`, the player's default level, online covers on; C-BIOS 0.29a for the cartridges, the owner's FS-A1WSX firmware with its kanji font for the disks) | Arthur, after playing them: « Ok, je viens de tester MSX2, donc c'est ok, ça marche. » (he said "MSX2"; the games he had just played were the MSX2+ ones); asked "Je sors le MSX2+ de l'expérimental ?": « Oui, sors-le » | Exit from the experimental status decided: the MSX2+ is supported from 1.7.6. The stamp move of the status change is handled by the 1.7.6 update; the exports are not converted again. A play test of six games, not a coverage claim: no game played through, no latency or hardware-fidelity measure; G9, G11 and G16 stay `P`. |
| 15 November 2026 | Sony PlayStation | The eight discs delivered in `Export\Games\PlayStation` from the tree `6a5d9e9b` (Gran Turismo 2 of 00:34 UTC, with his hints), several of them played | « Je viens de tester la Nintendo 64 et la PlayStation sur plusieurs jeux. Donc, le comportement du jeu en lui-même, ça me paraît plutôt solide et plutôt réactif. Je n'ai pas eu de bug graphique. J'ai pu aussi faire une sauvegarde sur Gran Turismo 2 qui a fonctionné. » Then « Oui, sors-la » | 1x and 2x hold on his PC, 4x falls behind and cut the sound in Gran Turismo 2's races, 8x was unplayable and is no longer offered (a written limit); his Gran Turismo 2 save was read back by the G7 check |
| 16 November 2026 | Commodore Amiga 1200 | The eight installs of the checklist (Slam Tilt, Pinball Illusions, Alien Breed 3D, Fears, Banshee, Super Stardust, Chaos Engine, All New World of Lemmings), converted by the 1.7.7 candidate (`rc-177` at `35ac18c9`, the standard level) and delivered in `Export\Games\Amiga 1200` | « Je viens de tester les huit jeux Amiga 1200, ça marche impeccable, tu peux le sortir de l'expérimental. » | His decision: the Amiga 1200 leaves the experimental status in 1.7.8. Its paths are not shared for now, on his word of 15 November 2026: « on n'active pas le partage de chemin encore. On verra si c'est pertinent. Pour l'instant, ça n'a pas l'air de l'être. » Then: « pour le partage des chemins, on fera des tests plus tard. Faudra qu'on fasse des tests quand même. » |
| 15 November 2026 | Nintendo 64 | The eight exports of the checklist (Super Mario 64, Mario Kart 64, F-Zero X, Banjo-Tooie, GoldenEye 007, Rayman 2, Majora's Mask, Ocarina of Time), delivered from the tree `7b33bd9d` | « Je viens de tester la Nintendo 64 et la PlayStation sur plusieurs jeux. Donc, le comportement du jeu en lui-même, ça me paraît plutôt solide et plutôt réactif. Je n'ai pas eu de bug graphique. » On F-Zero X: « non, non, ça vibre pas. […] c'est le jeu, donc j'ai pas de problème avec F-Zero. Ça marche très bien. » | His decision the same day: the Nintendo 64 leaves the experimental status in 1.7.6 and does not share its paths: « Ça me paraît bien faible pour partager les chemins. Si on a que 10% de gain max, […] on va sortir Nintendo de l'expérimental, mais on va pas partager les chemins. » |
| 27 November 2026 | SG-1000 | The three games of [the checklist](SG1000.md#10-g14-checklist-for-the-owners-play-test-22-november-2026) in `Export\Games\SG-1000`: Congo Bongo (Japan, Europe) (Alt) and Sega-Galaga (Japan), delivered on 22 November 2026, and Flicky (Japan), delivered again on 27 November 2026 with the F5 sprite flicker reduction | Arthur, after playing the delivered games that morning: « Ok, je viens de tester quelques jeux, ça marche parfaitement. pour les shaders et les machines. »; then « Ok, je valide le G14 pour les autres consoles, à part pour le ZX Spectrum. » | G14 moves from `?` to `Y`; the « autres consoles » are the SG-1000, the ColecoVision, the Amstrad CPC and the Game Boy Color (the ZX Spectrum is held back and the PC Engine CD is recorded in its own row). His remark on Flicky's picture was handled before: MAME shows the same picture, and the F5 sprite flicker reduction was added, off by default. A play impression of three games, not a measure: no claim of CPU or hardware fidelity, of gameplay beyond the games tried, or of latency. The status stays experimental: leaving it comes with the release, on his word. |
| 27 November 2026 | ColecoVision | The three games of [the checklist](COLECOVISION.md#6-g14-checklist-for-the-owners-play-test-22-november-2026) in `Export\Games\ColecoVision` (the owner's own BIOS): Donkey Kong (USA, Europe) and Pitfall II - Lost Caverns (USA), delivered on 22 November 2026, and Bump 'N' Jump (USA, Europe), delivered again on 27 November 2026 with the F5 sprite flicker reduction | Arthur, after playing the delivered games that morning: « Ok, je viens de tester quelques jeux, ça marche parfaitement. pour les shaders et les machines. »; then « Ok, je valide le G14 pour les autres consoles, à part pour le ZX Spectrum. » | G14 moves from `?` to `Y`. His remark on Bump 'N' Jump's picture was handled before: MAME shows the same picture, and the F5 sprite flicker reduction was added, off by default. A play impression of three games, not a measure: no claim of CPU or hardware fidelity, of gameplay beyond the games tried, or of latency. The status stays experimental: leaving it comes with the release, on his word. |
| 27 November 2026 | Amstrad CPC | The three games of [the checklist](AMSTRAD_CPC.md#7-g14-checklist-for-the-owners-play-test-22-november-2026) in `Export\Games\Amstrad CPC` (the pinned CPC 6128 firmware): Bomb Jack, Gryzor and Head over Heels, delivered on 27 November 2026 | Arthur, after playing the delivered games that morning: « Ok, je viens de tester quelques jeux, ça marche parfaitement. pour les shaders et les machines. »; then « Ok, je valide le G14 pour les autres consoles, à part pour le ZX Spectrum. » | G14 moves from `?` to `Y`; earlier the same day he had written « CPC bien ». A play impression of three games, not a measure: no claim of CPU or hardware fidelity, of gameplay beyond the games tried, or of latency. The status stays experimental: leaving it comes with the release, on his word. |
| 27 November 2026 | Game Boy Color | The three games of [the checklist](GAME_BOY_COLOR.md#g14-checklist-for-the-owners-play-test) in `Export\Games\Game Boy Color`: Tetris DX, Pokémon Gold and Wario Land 3, delivered on 22 November 2026 (compiler revision `9150f87d`) | Arthur, after playing the delivered games that morning: « Ok, je viens de tester quelques jeux, ça marche parfaitement. pour les shaders et les machines. »; then « Ok, je valide le G14 pour les autres consoles, à part pour le ZX Spectrum. » | G14 moves from `?` to `Y`. His remark on the sound was settled before: it stays as it is, on his word. A play impression of three games, not a measure: no claim of CPU or hardware fidelity, of gameplay beyond the games tried, or of latency. The status stays experimental: leaving it comes with the release, on his word. |
| 27 November 2026 | PC Engine CD / TurboGrafx-CD | Akumajou Dracula X - Chi no Rondo (Japan), Lords of Thunder (USA), Ys Book I & II - Ancient Ys Vanished (USA), delivered that morning in `Export\Games\PC Engine CD` from `spec/pcecd-g9` at `25b86572` | Arthur, after playing them: « PC Engine très bien »; later the same day: « Ok, je valide le G14 pour le PC Engine CD » | G14 `Y` (his words relayed by the lead session); the exit from the experimental status is not part of this row |

### Commodore Amiga: the panel (9 November 2026)

Chosen for risk and approved before the run, in the player's own library. Each game had to convert or refuse with a sentence; equal the fresh reference on every route (picture, sound, RAM, CPU registers); report its interpreter and Blitter counters; pass the compressed copy and the quick state; have its captures looked at. A failure would have stayed on the list with its cause. Extended level (main and explore of 3,600 frames, long-1 of 18,000), Windows, tree `9a2c807a`, online covers on, delivered to `Export/Games/Amiga`; Pinball Dreams again with the keyboard fix (`spec/amiga-172`, same day), which also adds F1-F4 to the long route.

Totals over the 14: 3.48 billion native instructions, 420 interpreted, all 420 of them the Kickstart's (19 or 7 per route); 337.8 million Blitter copy words in specialised routines, none in vAmiga's microprogram, none left midway. Line blits stay in vAmiga's microprogram and are counted apart. Native here is the 68000 and the Blitter's copy blits; Agnus, Denise, Paula and the CIAs stay emulated.

| Install | Why it is here | Native (M) | Interpreted | Blitter copy words in routines | Instructions (swept) | Furthest a route reached |
|---|---|---|---|---|---|---|
| Rick Dangerous | Reference case, one Blitter shape, RNC packed | 252.9 | 0 | 4,575,380 | 15,863 (12,653) | Play, two levels |
| Blood Money | Long-standing panel game, heavy Blitter | 242.5 | 0 | 58,866,098 | 24,740 (20,693) | Play, several levels |
| Apidya (Kaiko) | Code per level, TPWM | 260.0 | 0 | 47,626,351 | 50,121 (43,331) | Play |
| Lemmings (Image) | Levels are data, mouse | 165.3 | 0 | 64,709,360 | 29,139 (25,951) | Main menu |
| Pinball Dreams (NTSC) | NTSC timing, picture offset, keys chosen by the game | 185.3 | 0 | 31,455,032 | 30,031 (25,739) | Play on one table |
| Shadow Of The Beast | Copper parallax | 223.1 | 0 | 2,241,138 | 68,373 (63,328) | Play |
| Another World (FR) | Polygon drawing, French install | 344.2 | 57, the Kickstart's | 32,563,293 | 39,184 (16,369) | Code wheel |
| Monkey Island 2 | Many files, saves, adventure | 288.2 | 57, the Kickstart's | 2,902,160 | 95,804 (50,505) | Protection, then the intro |
| Civilization | Kickstart, line blits, mouse | 224.7 | 57, the Kickstart's | 4,247,793 | 147,883 (114,155) | Opening animation |
| Settlers | Mouse game, long CPU work | 265.4 | 57, the Kickstart's | 38,044,146 | 147,308 (115,387) | Protection |
| Cyber Games | Little-known install, name-matching risk | 292.0 | 21, the Kickstart's | 32,596,533 | 215,745 (150,000) | Play |
| Might & Magic 3 (DE) | Kickstart, German, saves | 272.3 | 57, the Kickstart's | 1,261,516 | 70,621 (41,159) | Title menu |
| 4D Sports Boxing | Filled polygons | 246.7 | 57, the Kickstart's | 15,009,529 | 119,926 (71,083) | Play, a round |
| Superfrog | Fast scrolling | Refused | | | | `Superfrog.lha` holds no WHDLoad slave: not an Amiga WHDLoad install |
| Deja Vu (NTSC) | NTSC, text adventure | 217.4 | 57, the Kickstart's | 1,702,153 | 69,691 (33,578) | Play |

What the panel found: Pinball Dreams took no key at all, on the native code and on the reference alike, so the equality of the first run said nothing about it; the owner found it by playing. The same run with and without one key shows the difference on the other 13 converted games: the key changes RAM on 12, and on Shadow Of The Beast it changes nothing (a joystick game, not looked at further). With the fix, in the delivered file's window (a hidden desktop, keys posted to the window), Ctrl+Alt+K then F1, F2, F3 or F4 starts each of the four tables; so does F3 with the F2 row "F1-F10 keys: Amiga", and F4 with the keyboard row. On the 3,000 frames after the key, headless: Nightmare 25.4 M native and 0 interpreted, the table the long route entered; Steel Wheel 21.3 M native and 4.07 M interpreted (16 %); Beat Box 21.6 M and 4.19 M (16 %); Ignition 12.6 M and 13.4 M (52 %), code those routes never ran. It is counted, and the window title says so. Nobody has played a table for this entry.

### Commodore Amiga: the panel of 13 November 2026

**Rule.** At most eight installs a machine (the owner's rule of 13 November 2026), each with its reason, none dropped because it fails. The 15 installs of 9 November were cut to these eight; Lotus 2 (the test game) and Another World stayed by name. Panza Kick Boxing (FR) is converted beside them as the save game of G7, outside the count. Extended level (main and explore of 3,600 frames, 7,000 or 7,200 for the three installs that answer a first screen, long-1 of 18,000), from an empty library, one conversion at a time, the player's own Kickstart, online covers on. Windows with the players' toolchain (llvm-mingw 20261006, CMake 4.4.4, Ninja 1.13.2), tree `be3f4483` (`spec/amiga-176`, main's new in-game interface merged); delivered to `Export/Games/Amiga` except Lotus 2, whose export carries the interface specialist's build.

| Install | Why it is here | Native (M, three routes) | Interpreted per route | Furthest the long route reached (captures read) |
|---|---|---|---|---|
| Lotus 2 | The test game: 3D road, colour steps | 283.6 | 0 | Races, twice, after the menu and the course picture |
| Another World (FR) | Kickstart, polygons, the joystick answer to its code wheel | 287.0 | 19, the Kickstart's | The intro, the pool (play), the "press the button" screen with an access code after a death, the pool again |
| Monkey Island 2 | Kickstart, many files, the answer to its protection | 366.2 | 19, the Kickstart's | The opening: the protection, "Check one", the credits, Scabb Island, the campfire story; **not** the first scene the player controls |
| Lemmings (Image) | Mouse; the route clicks 1 PLAYER | 263.6 | 0 | Level 1 played: lemmings out, the timer running, the view scrolled |
| Pinball Dreams (NTSC) | NTSC timing; keys choose the table | 185.3 | 0 | A table in play, balls launched |
| Shadow Of The Beast | Copper parallax | 223.3 | 0 | Play: running across the plain |
| Blood Money | Heavy Blitter | 241.4 | 0 | Play on the first level, the shop between levels |
| Apidya (Kaiko) | Code per level, TPWM | 267.8 | 0 | Play, the options screen, play again |
| Panza Kick Boxing (FR), outside the count | Saves (G7), French | 256.3 | 7, the Kickstart's | Training, then fights in the ring |

Every route of the nine equals the fresh interpreted reference on every frame (picture, sound, RAM, CPU registers, resload calls), the compressed copy too; F8/F9 continue for 600 frames in a fresh process; 17 damaged states are refused and a missing one creates nothing (G6). The five installs whose routes did not change since the tree `96a70fa0` give the same trace digests on every route as on that tree. Rick Dangerous, of the earlier panel, ran on `96a70fa0` only (Windows and Debian, G13).

### Checklist for Arthur: Sony PlayStation play test (G14)

A checklist, not a record: the verdicts and the notes are yours, and leaving the experimental status is your decision alone. Play the
executables in `Export/Games/PlayStation`, delivered on 15 November 2026 from the tree `6a5d9e9b` (Gran Turismo 2 at 00:34 UTC, with your hints).
A few minutes a game. Nothing here says exact hardware, complete gameplay or latency; a tick means "it looked and sounded right to you in this
test". F2 shows the keys (Cross X, Circle C, Square W, Triangle A, Start Enter, Select Shift; F Analog; N change disc). **F3 → Internal resolution:
2x is the advised setting; 4x is labelled heavy and is too heavy for 3D racing on this PC.**

| | Ape Escape | Final Fantasy VII | Metal Gear Solid | Soul Reaver | Symphony of the Night | WipEout 2097 | R4 | Gran Turismo 2 |
|---|---|---|---|---|---|---|---|---|
| Why it is here | the DualShock (press F once for analog) | three discs, much code | two discs | streaming | 2D, saves in save rooms | PAL, CD audio | Japanese, your Japanese BIOS | a full race at 2x; your save |
| It starts without an error window | | | | | | | | |
| The window title ends with "Native CPU, emulated hardware" until new code runs | | | | | | | | |
| Sound is the game's (music and effects) | | | | | | | | |
| **F8**, move on, **F9** goes back | | | | | | | | |
| A save from the game's menu, then quit, start again: the game finds it | | | | | | | | |
| Nothing odd: a frozen picture, silence, a wrong colour, lag on fast left/right | | | | | | | | |

Known, not a failure: code a game reaches for the first time runs on the interpreter (the window title says so) and becomes native at the
next conversion with your F12 hints; Gran Turismo 2's last save did not reach its card (to be looked at with you).

### Checklist for Arthur: Commodore Amiga play test (G14)

A checklist, not a record: the verdicts and the notes are yours, and leaving the experimental status is your decision alone. Play the
executables already in `Export/Games/Amiga`: six of the eight installs of [the panel of 13 November](#commodore-amiga-the-panel-of-13-november-2026),
delivered from the tree `be3f4483` (Lotus 2 as the interface specialist built it), whose games behave as in 1.7.4. One short session: a few
minutes a game. Nothing here says exact hardware, complete gameplay or latency; a tick means "it looked and sounded right to you in this test".
F2 shows each game's keys; the joystick is the arrows and **W** (fire) or a gamepad.

| | Lotus 2 | Another World | Monkey Island 2 | Lemmings | Pinball Dreams | Panza Kick Boxing |
|---|---|---|---|---|---|---|
| Why it is here | the test game: a 3D road, colour steps | your Kickstart, polygons, the code wheel | your Kickstart, many files, the recipe protection | the mouse | NTSC, keys choose the table | saves its boxers |
| It starts without an error window | | | | | | |
| The window title ends with | Native CPU, emulated hardware | Interpreter fallback (19 Kickstart instructions) | Interpreter fallback (19 Kickstart instructions) | Native CPU, emulated hardware | Native CPU, emulated hardware | Interpreter fallback (7 Kickstart instructions) |
| What to do | choose a race in the menu and drive a lap | on the code wheel, enter your wheel's symbols (the conversion's routes pass it with the joystick: fire four times, right three times, fire, three times over); then play the pool scene | type any four digits and Return on the recipe screen, then click the box; watch the opening, then walk Guybrush a few steps | click **1 PLAYER** (the mouse is captured on a click, **Ctrl+Alt+M** releases it), then play level 1 | **Ctrl+Alt+K**, then **F1** to **F4** pick the table; launch a ball and use the flippers | change your boxer (train him, or pick another), then OPTIONS, the save row (SAUVEGARDE), **MAINTENANT** and fire; close the game, start it again: your boxer is as you left him |
| Sound is the game's (music and effects) | | | | | | |
| **F8** in play, move on, **F9** goes back to the saved moment | | | | | | |
| Close the window, start it again, **F9** loads the state saved before | | | | | | |
| Nothing odd: a frozen picture, silence where there was sound, a wrong colour, lag on fast left/right | | | | | | |

Known, not a failure: on Another World's code-wheel screen a left click, **C** or a second fire button opens the install's access-code
screen and locks the game until it is restarted ([AMIGA.md](AMIGA.md#4-known-limits)); Pinball Dreams' other three tables run partly on the
interpreter, as the window title says once you reach them. A state saved before 1.7.4 is refused, as between any two builds.

| Date | Console | Games tried | Verdict | Notes |
|---|---|---|---|---|
| 14 November 2026 | Commodore Amiga | Lotus 2, Another World (FR), Monkey Island 2, Lemmings (Image), Pinball Dreams (NTSC), Panza Kick Boxing (FR) | « je te valide bien que tous ces jeux marchent parfaitement. »; asked whether to take the Amiga out of the experimental status: « Oui, sors-le » | the exit from the experimental status (the owner-acceptance table) |

### Checklist for Arthur: Commodore Amiga 1200 play test (G14)

A checklist, not a record: the verdicts and the notes are yours. Play the **delivered executables** of the 1.7.7 candidate in
`Export\Games\Amiga 1200` (a game converted by an older build does not show the 1.7.7 fixes). For each: it starts and reaches play
past the title screens; the picture is right (AGA colours, nothing shifted, an interlaced screen that neither shakes nor combs when it
scrolls); the sound; the controls (the pad, the keyboard for the pinballs, Ctrl+Alt+K when a game wants its F1 to F10 keys); F8, play
on, F9 goes back; your fast left/right test (an impression, not a measure).

| Install | What it tests | Look at |
|---|---|---|
| Slam Tilt | 68020 and AGA, 256 colours (the test game) | the tables, the scrolling, the flippers |
| Pinball Illusions | the player's Kickstart 3.1; AGA dual playfield | the table selection (F1 to F4), a table; Ctrl+Alt+K then F10: the whole interlaced view, no comb while it scrolls |
| Alien Breed 3D | the slave's patches across segments | past the title, the 3D game |
| Fears | a 3D engine, code in fast RAM | smoothness; F2, the processor speed row |
| Banshee | Kickstart 3.1, an interlaced title | the title (still, sharp), the shots, the sound |
| Super Stardust | Crunch-Mania; it keeps its preferences | an option changed, quit, restart: it stays. The super-hires intro at half detail is the known limit |
| Chaos Engine | 2D action | the first level, both characters |
| All New World of Lemmings | the Kickstart 3.1 asked in the slave's code | it starts, then a level |

| Date | Console | Games tried | Verdict | Notes |
|---|---|---|---|---|
| 16 November 2026 | Commodore Amiga 1200 | Slam Tilt, Pinball Illusions, Alien Breed 3D, Fears, Banshee, Super Stardust, Chaos Engine, All New World of Lemmings | « Je viens de tester les huit jeux Amiga 1200, ça marche impeccable, tu peux le sortir de l'expérimental. » | Exit decided (G14) |

### Checklist for Arthur: Sharp X68000 play test (G14)

A checklist, not a record: the verdicts and the notes are yours. Play the **delivered executable** of the release you are judging
(not a reconversion of the day). `python tools/x68000_owner_trial.py --roms <your X68000 folder> --ipl <iplrom.dat> --cgrom <cgrom.dat>`
converts these five games as a player would, one at a time, under `.build/x68-owner-trial/` (never into Export, each in a private
library), and writes `TRIAL.md` there with where each executable is and what to try; the executables carry your IPL and font ROM, so
they stay on your machine. Nothing here says exact hardware,
complete gameplay or latency; a tick means "it looked and sounded right to you in this test".

| | R-Type (Irem) | Metal Sight (System Sacom) | Lemmings (Imagineer) | Super Hang-On (Sharp / SPS) | Bubble Bobble (Dempa) |
|---|---|---|---|---|---|
| Why it is here | one disk, the control | five disks: the disk changes | mouse game that drives the mouse chip itself | two disks, ejected after loading | an arcade port whose colours were corrected in 1.6.7 |
| It starts without an error window | | | | | |
| Controls: arrows, **W** and **X** (A and B), **Enter** (Start) | | | The mouse is captured at launch (**Ctrl+Alt+M** releases it); the keyboard or a gamepad also moves the pointer and presses its buttons. Click "1 PLAYER", then play level 1 | The title counter counts down from 99 while the game loads (about two minutes of play time); hold **F5** for fast loading; nothing answers before it reaches 0 | Two players share the keyboard and a gamepad; the colours look right, with no green cast on the dark parts |
| Sound is the game's (music and effects) | | | | | |
| The disk changes by itself, with no key from you | not applicable | at each "insert disk" request, until play | not applicable | none expected: it must run as if there were no policy | not applicable |
| **F8** in play, move on, **F9** goes back to the saved moment | | | | | |
| Close the window, start the executable again, **F9** loads the state saved before | | | | | |
| Nothing odd: a frozen picture, silence where there was sound, a wrong colour | | | | | |

Then three checks on the machine itself, each on one game of your choice:

1. **Save, relaunch, reconvert.** The game's disks are copied beside the player on the first start (`datas/games/x68-<identity>/media`)
   and the game writes into its own copy. Pick a game you know writes to its disk (a save, a high score, a configuration), save in it,
   close, start again and find the save; then convert the same game again, start the new executable and find the save once more.
   None of the four games above is known to save on purpose (the only writes seen in 378 starts are file time stamps of 4 to 12 bytes,
   above), so this check needs a game that does: tell me which one and I add it to the risk cases. If a disk was damaged, the player moves
   it to `<name>.unusable-1` and writes the original again; it never deletes it.
2. **A D88 image.** The collection holds only DIM files, so make a D88 of a disk you own with
   `python tools/x68000_disk_rewrite.py "R-Type (Irem).dim" --format d88 R-Type.d88` (outside the repository: it holds the whole disk),
   convert it into another output folder than the DIM's, and play it like the DIM. It is the same game: same identity, same saved data, the
   same pictures and sound. A D88 from elsewhere with a copy-protection layout (deleted or failing sectors, 2DD) is refused with a reason,
   on purpose.
3. **A multi-disk set from a folder.** Add one disk of a numbered set (for example Metal Sight, disk 1 of 5) to the queue: the five disks
   must join as one game. A set named with a gap (disk 3 missing) is queued with the disks found and the gap is reported in the log.

| Date | Console | Games tried | Verdict | Notes |
|---|---|---|---|---|
| (to fill) | Sharp X68000 | (to fill) | (to fill) | (to fill) |

### Checklist for Arthur: Nintendo NES play test (G14)

A checklist, not a record: the verdicts and the notes are yours. Play the **delivered executable** of the release you are judging.
`python tools/nes_owner_trial.py --roms <your NES folder>` converts these six games as a player would, one at a time, under
`.build/nes-owner-trial/` (never into Export), writes `TRIAL.md` there with the same table and takes one picture of each right-hand
play route. Nothing here says exact hardware, complete gameplay or latency; a tick means "it looked and sounded right to you in this
test".

| | Zelda | Kirby's Adventure | Mr. Gimmick (PAL) | Duck Hunt (Zapper) | Battletoads | Castlevania III |
|---|---|---|---|---|---|---|
| Why it is here | MMC1, battery save, long game | MMC3 scanline IRQ, battery save | 50 Hz cartridge, FME-7 sound chip | the Zapper | two players, AxROM, code in RAM | MMC5, extra sound channels |
| It starts without an error window | | | | | | |
| Controls: arrows, **W** and **X**, **Enter** (Start), **Shift** (Select); player 2 on the keypad | | | | The mouse aims, the left button shoots, the right button shoots off-screen | Both pads answer | |
| Sound is the game's (music and effects) | | | The speed and the pitch of a PAL game | | | The extra pulse channels are heard |
| **F8** in play, move on, **F9** goes back | | | | | | |
| Close the window, start again, **F9** loads the state saved before | | | | | | |
| A save made in the game is still there after closing and starting again | | | not applicable | not applicable | not applicable | not applicable |
| **F3** changes the picture filter, **F4** the window mode | | | | | | |
| Nothing odd: a frozen picture, a flickering status bar, a wrong colour | | | | | | |

Then four checks, each on the game that fits:

1. **Battery save.** Start a game in Zelda or Kirby, save in the game, quit, start again and load it. The file is
   `datas/games/<game>-<12 hex digits>.sav` beside the player; the conversion's own test runs leave none.
2. **Autofire and extra sprites.** On a gamepad, **F6** turns autofire on and off (a notice shows "Autofire ON" or "Autofire OFF"; a game
   samples its pad once per frame, so what it makes of it is the game's). **F5** toggles the extra sprites: in a game that flickers
   (Battletoads, Castlevania III) fewer objects blink; off by default.
3. **The Zapper.** In Duck Hunt, **F2** then the Zapper page (after the four control pages) changes the reticle: cross or dot, size, red,
   white or green. The light is an approximation fed by the pixels the PPU emits: say if a shot you think was good counts as a miss, or
   the opposite, and where on the screen.
4. **Language.** **F7** changes the language of the player's own menus (the game's text is the cartridge's).

Known limits to keep in mind while you play: the Zapper's light is approximate; one Zapper only (no second gun, no other special
controller); the Famicom Disk System is not supported; no Dendy timing (NTSC and PAL only). Keep the five measures apart when you judge: the CPU is checked against independent vectors and
the hardware against authored fixtures, not against a reference console, and a good feel here is neither an exact fidelity nor a
latency measure.

| Date | Console | Games tried | Verdict | Notes |
|---|---|---|---|---|
| (to fill) | Nintendo NES | (to fill) | (to fill) | (to fill) |

### Checklist for Arthur: Atari ST play test (G14)

A checklist, not a record: the verdicts and the notes are yours. Play the **delivered executables** that stand in `Export/Games/Atari ST/` (converted from the final tree of the release you are
judging, online covers on; nothing here asks you to convert anything). One short session, seven games, about ten minutes each. Nothing here says exact hardware, complete gameplay or latency;
a tick means "it looked and sounded right to you in this test". The games that start on EmuTOS need no file from you; Turrican II was converted with your TOS 1.04.

| | Bomb Jack | Turrican II | Operation Stealth | The Lurking Horror | Kick Off 2 | Lethal Xcess | Battle Probe |
|---|---|---|---|---|---|---|---|
| Why it is here | the control: EmuTOS, starts by itself, joystick | needs the player's own TOS 1.04 (EmuTOS stops it) | three disks, started by the desktop, a colour-code protection | the game that saves to its disk; keyboard | a sports game: two players, the joystick on both ports | two disks, the disk change, a shooter | started by the desktop, a joystick game |
| It starts without an error window | | | | | | | |
| Controls: arrows, **W** (fire), **Enter** (Start); a gamepad is player 1 | | | the mouse drives it; **Ctrl+Alt+M** lets the mouse go | you type: **Ctrl+Alt+K** gives the keyboard to the Atari | player 2 on its own keys or a second gamepad | | |
| Sound is the game's (music and effects) | | | | | | | |
| The disk change: **Ctrl+Alt+Page Up / Page Down** when the game asks | not applicable | not applicable | at each "insert disk" | not applicable | not applicable | "INSERT DISK B" | not applicable |
| **F8** in play, move on, **F9** goes back to the saved moment | | | | | | | |
| Close the window, start again, **F9** loads the state saved before | | | | | | | |
| Nothing odd: a frozen picture, silence where there was sound, a wrong colour | | | | | | | |

Then three checks, each on the game that fits:

1. **A save made in the game.** In The Lurking Horror, walk a room, type `save`, then a file name, quit, start the game again and type `restore`, the same name: you must find the room you left.
   What the game writes to its disk is kept in `datas/games/atarist-<identity>/disk-writes.bin` beside the player; the disk image inside the executable never changes. A damaged file is
   moved to `disk-writes.bin.unusable-1` and the game starts from its disks.
2. **A protection.** Operation Stealth asks for a colour code from its card: the conversion's routes stop there on purpose, because no route
   answers or skips a protection. If you own the card, type the answer yourself (**Ctrl+Alt+K** first) and tell me whether the game goes on.
3. **A game of your own.** Add one disk or ZIP of the ST library that is not in this list to the queue, convert it, and play it like the others: which one, and what it did, is the most useful
   line of this checklist.

Known limits to keep in mind while you play: the STE, the Mega STE, the TT, the Falcon, hard disks and the monochrome monitor are not supported; a game that formats a track on an IPF disk
cannot keep that write; Metro-Cross, Pharaoh III and Trinity do not run as they should (listed in KNOWN_FAILURES.md). Keep the five measures apart when you judge: the CPU is Hatari's,
checked against an independent corpus and the hardware against authored programs, not against a real ST, and a good feel here is neither an exact fidelity nor a latency measure.

| Date | Console | Games tried | Verdict | Notes |
|---|---|---|---|---|
| 14 November 2026 | Atari ST | Bomb Jack, Turrican II, Operation Stealth, The Lurking Horror, Kick Off 2, Lethal Xcess, Battle Probe | « Ok, donc Atari ça marche, nickel, j'ai testé les jeux. »; asked whether to take the Atari ST out of the experimental status: « Oui, sors-le » | the exit from the experimental status (the owner-acceptance table) |

### Checklist for Arthur: MSX and MSX2 play test (G14)

A checklist, not a record: the verdicts and the notes are yours. Play the **delivered executables** in `Export/Games/MSX` and
`Export/Games/MSX2`: the panel of 14 November 2026 (extended level, C-BIOS 0.29a, online covers on), converted from tree `d0b32436` of
`spec/msx-175`. About twenty minutes: a few minutes a game. Nothing here says exact hardware, complete gameplay or latency; a tick means "it
looked and sounded right to you in this test".

| | Knightmare | Salamander | Dragon Slayer II - Xanadu | Metal Gear | Space Manbow | Aleste |
|---|---|---|---|---|---|---|
| Machine and why it is here | MSX, plain 32 KiB: the control case | MSX, Konami SCC sound | MSX, ASCII 8 with battery SRAM | MSX2, Konami, the V9938 | MSX2, Konami SCC, the vertical scroll | MSX2, ASCII 16, fast scrolling |
| It starts without an error window | | | | | | |
| Controls: **arrows**, **X** (trigger A, SPACE), **W** (trigger B), **Enter** (SPACE), **right Shift** (MSX F1) | | | | | | |
| Sound is the game's (music and effects) | | the SCC's voices | | | the SCC's voices | |
| The scroll is smooth (no judder, no torn band) | | | | | the backgrounds you saw choppy before 1.7.3 | |
| **F8** in play, move on, **F9** goes back | | | | | | |
| Close the window, start again, **F9** loads the state saved before | | | | | | |
| A save made in the game is still there after closing and starting again | not applicable | not applicable | | not applicable | not applicable | not applicable |
| **F3** changes the picture filter, **F4** the window mode | | | | | | |
| Nothing odd: a frozen picture, a flickering sprite row, a wrong colour | | | | | | |

Then three checks:

1. **Battery save.** In Xanadu, save in the game (its own save menu), quit, start again and load it. The file is
   `datas/saves/<game>-<cartridge>.rrsram` beside the player; it is written two seconds after the game last writes it and when the window
   closes.
2. **The whole keyboard.** **Ctrl+Alt+K** hands the keyboard to the MSX (F1 to F5 then go to the MSX, the help is at Ctrl+F1); again
   gives it back.
3. **Language.** **F7** changes the language of the player's own menus (the game's text is the cartridge's).

Known limits to keep in mind while you play: C-BIOS boots no MSX-BASIC, disk or cassette; the FM-PAC and its SRAM and the MSX2 clock's
battery memory are not converted; the V9938's command timing is approximated. Keep the five measures apart when you judge: the CPU is
checked against our own reference interpreter and independent vectors, the hardware against our reading of the documents and a few
openMSX comparisons, not against a real MSX, and a good feel here is neither an exact fidelity nor a latency measure.

| Date | Console | Games tried | Verdict | Notes |
|---|---|---|---|---|
| 14 November 2026 | MSX, MSX2 | Knightmare, Salamander, Dragon Slayer II - Xanadu (MSX), Metal Gear, Space Manbow, Aleste (MSX2) | « Donc, je viens de tester les jeux MSX1 et MSX2, ça marche impeccable. Tu peux les sortir de l'expérimental. » | the exit from the experimental status (the owner-acceptance table) |

### Checklist for Arthur: MSX2+ play test (G14)

A checklist, not a record: the verdicts and the notes are yours. Play the **delivered executables** in `Export/Games/MSX2+`, converted on
14 November 2026 from tree `05f8d828` of `spec/msx2plus-176` as a player converts (the default level, online covers on): the three
cartridges on C-BIOS 0.29a, the three disk games with your own Panasonic FS-A1WSX firmware (main ROM, sub-ROM, disk ROM, MSX-MUSIC BIOS and
kanji font). About thirty minutes: a few minutes a game, more for Xak III if you want to see it ask for a disk. Nothing here says exact
hardware, complete gameplay or latency; a tick means "it looked and sounded right to you in this test".

| | Family Stadium Professional Baseball | The Goonies R Good Enough | Dragon Slayer II - Xanadu | Laydock 2 - Last Attack | F-1 Spirit 3D Special | Xak III - The Tower of Gazzel |
|---|---|---|---|---|---|---|
| What it is and why it is here | Cartridge, ASCII 16: the V9958's horizontal scroll, MSX-MUSIC | Cartridge, Konami SCC: the mapper fixed today, SCC music | Cartridge, ASCII 8 with battery SRAM (an MSX game on the MSX2+) | Two disks, a shooter | Three disks, 3D racing | Four disks, role-playing: asks for its disks |
| It starts without an error window | | | | | | |
| Controls: **arrows**, **X** (trigger A, SPACE), **W** (trigger B), **Enter** (SPACE), **right Shift** (MSX F1) | | | | | | |
| Sound is the game's (music and effects) | the FM music (MSX-MUSIC) | the SCC's voices | | the FM music | the FM music | the FM music |
| The scroll is smooth (no judder, no torn band) | the title sliding in | | | | | |
| **F8** in play, move on, **F9** goes back | | | | | | |
| Close the window, start again, **F9** loads the state saved before | | | | | | |
| A save made in the game is still there after closing and starting again | not applicable | not applicable | | the game's DATA SAVE (on its disk) | | |
| Nothing odd: a frozen picture, a flickering sprite row, a wrong colour | | | | | | |

Then three checks:

1. **Disk requests.** In Xak III, when the game says "SET DISK n AND PUSH SPACE PLEASE", press SPACE: the player puts the next disk in by
   itself and says so ("The game asked for a disk"); if it was not the one asked for, press SPACE again and it tries the next. **Page Up /
   Page Down** still change the disk by hand.
2. **Battery save.** In Xanadu, save in the game, quit, start again and load it (`datas/saves/<game>-<cartridge>.rrsram`).
3. **A written disk.** In a disk game that saves (Laydock 2's DATA SAVE), save, quit, start again: the save is in the copy of the disk kept
   beside the game (`datas/games/msx2plus-<identity>/disk-<n>.dsk`); the embedded disks never change.

Known limits to keep in mind while you play: the MSX2+ stays experimental until your decision; C-BIOS boots no MSX-BASIC or disk (disk games
need your own firmware); cassettes and the FM-PAC are not converted; the V9958's command timing and the disk drive's timing are
approximated; MSX-MUSIC's level was set against openMSX on one authored cartridge, not on games. Keep the five measures apart when you judge:
the CPU is checked against our own reference interpreter and independent vectors, the hardware against our reading of the documents and a
few openMSX comparisons, not against a real MSX2+, and a good feel here is neither an exact fidelity nor a latency measure.

| Date | Console | Games tried | Verdict | Notes |
|---|---|---|---|---|
| 14 November 2026 | MSX2+ | Family Stadium Professional Baseball, The Goonies R Good Enough, Dragon Slayer II - Xanadu, Laydock 2 - Last Attack, F-1 Spirit 3D Special, Xak III - The Tower of Gazzel | « Ok, je viens de tester MSX2, donc c'est ok, ça marche. » (the MSX2+ games), then « Oui, sors-le » | the exit from the experimental status (the owner-acceptance table) |

### Checklist for Arthur: Game Boy Advance play test (G14)

A checklist, not a record: the verdicts and the notes are yours. Play the **delivered executables** in `Export/Games/Game Boy Advance`: six games of 14 November 2026, converted from the final tree of `spec/gba-175` (empty library, online
covers on), about three minutes each. For every game: look at the icon and the first menu art, press **F2** and **Esc** (the "Quit?" question), play a little, **F8**, play on, **F9**, then quit and open it again. Nothing here says exact hardware,
complete gameplay or latency; a tick means "it looked and sounded right to you in this test".

| Game | What to do | What should happen |
|---|---|---|
| Golden Sun | new game, A through the intro, walk Isaac around Vale | text and pictures right, music, Isaac walks; F8/F9 returns to the saved moment |
| Mario Kart Super Circuit | 1P Grand Prix, one lap, steer, an item | the kart steers and the track scrolls, the engine sounds play, no freeze |
| The Minish Cap | new file, walk out of Link's house | Link walks, the HUD shows; quit and reopen: the file select lists the file (EEPROM) |
| Crazy Taxi: Catch a Ride | a game, a customer, the destination | the city is drawn and moves (the speed is your impression, not a measure) |
| F-Zero: Maximum Velocity | register a pilot, one lap | the race runs; quit and reopen: the pilot is listed (SRAM) |
| Pokémon Emerald | new game to the van, Start menu, SAVE, quit, reopen | CONTINUE is offered (Flash 128 KB); the clock cartridge asks nothing odd |

Known limits to keep in mind while you play: the converter checked the first minutes and long runs of four of these cartridges by authored routes, not a level won; the comparison is with the engine's own interpreter, not with a real console;
the cartridge sensors and the e-Reader are not converted, and the link cable plays in a multiplayer match only. Keep the five measures apart when you judge: a good feel here is neither an exact fidelity nor a latency measure.

| Date | Console | Games tried | Verdict | Notes |
|---|---|---|---|---|
| 14 November 2026 | Game Boy Advance | Golden Sun, Mario Kart Super Circuit, The Minish Cap, Crazy Taxi: Catch a Ride, F-Zero: Maximum Velocity, Pokémon Emerald | « Moi, je viens de tester les jeux Game Boy Advance. Donc ça marche parfaitement. Ils se comportent de manière parfaite. »; asked whether to take the Game Boy Advance out of the experimental status: « Oui, sors-la » | the exit from the experimental status (the owner-acceptance table) |

### Checklist for Arthur: PC Engine CD play test (G14)

G14 is already `Y` (the owner-acceptance table). This list is for the same three games **delivered again** on 27 November 2026 into `Export/Games/PC Engine CD` from the final tree of `spec/pcecd-g11`, if you want to look at what
changed since the copies you played: a pad plugged in during play reaches the game, a game without a save starts with a formatted backup memory, and a disc game keeps no player's record (F12 does nothing). About three minutes
each; the System Card shows « PUSH RUN BUTTON » first (Enter or the pad's Start). Nothing here says exact hardware, complete gameplay or latency.

| Game | What to do | What should happen |
|---|---|---|
| Akumajou Dracula X - Chi no Rondo | title, your file screen, the first stage; I attacks, II jumps; F8, play on, F9 | the name saved before is listed; intro voices and stage music play; F9 returns to the saved moment |
| Lords of Thunder | START, pick an armour, the first stage | CD music through the stage, the ship flies and shoots |
| Ys Book I & II | Ys title, « Start game story », walk in the town | your File Cabinet is found (no new question if you had a save) |
| Any of them | unplug the pad and plug it back (or into another port) during play | the game answers it again |

Known limits: routes saw the first minutes, not a level won; the drive was compared with MAME on three discs, not with a console; the two-PC match is not proved.


## Commodore Amiga 1200: evidence behind its column (15 November 2026)

The profile `a1200` ([AMIGA.md](AMIGA.md#7-the-amiga-1200-a1200)), branch `spec/amiga1200-176`, supported from 1.7.8 on the owner's
decision of 16 November 2026 (the exports he played are below the panel). Every conversion
below ran on Windows (llvm-mingw), one at a time, from an empty scratch library, with the player's own Kickstart 3.1 where the install asks
for one. Nothing here says exact hardware, complete gameplay or latency: the five measures stay apart, and only native code and CPU
agreement with the reference are measured.

**The panel** (standard level: a main route and an exploration route of 3,600 frames each; the installs of the A1200 folder; run again on the
branch at `0f0ca6f1` on 15 November 2026, the same native counts where the first run had them):

| Install | What it tests | Native on the main route | Interpreted (main, explore) | Checks |
|---|---|---|---|---|
| Slam Tilt | the test game: a 68020 and AGA slave, 256-colour tables | 71,723,069 | 0, 0 | all |
| Pinball Illusions | the player's Kickstart 3.1 over `$F80000` | 172,559,712 | 1, 1 (a Kickstart instruction) | all; its title was black in 1.7.6 (below), fixed in 1.7.7 |
| Zool 2 AGA | AGA sprites and scrolling | 46,198,804 | 0, 0 | all |
| Banshee | Kickstart 3.1, a 68020 shooter | 40,576,307 | 1, 1 (a Kickstart instruction) | all |
| Fears | a chunky 3D engine | 70,462,637 | 0, 0 | all |
| Roadkill | Kickstart 3.1 | 232,904,955 | 1, 1 (a Kickstart instruction) | all |
| Gloom | Crunch-Mania files | 195,552,589 | 0, 0 | all |
| Super Stardust | Crunch-Mania files, an intro in AGA super-hires | 67,488,880 | 0, 0 | all |
| Alien Breed 3D | LoadSeg sizes (black in 1.7.6, starts since 1.7.7) | — | — | its title and music (below) |

**The exports the owner played** (16 November 2026): the eight installs of his checklist, converted by the 1.7.7 candidate (`rc-177` at
`35ac18c9`, Windows, llvm-mingw, the standard level, covers on, one at a time from an empty scratch library) and delivered in
`Export\Games\Amiga 1200`. Every check passed on all eight, the quick state continued in a fresh process.

| Install | Native on the main route | Interpreted (main, explore) |
|---|---|---|
| Slam Tilt | 71,723,069 | 0, 0 |
| Pinball Illusions | 172,559,712 | 1, 1 (a Kickstart instruction) |
| Alien Breed 3D | 196,897,271 | 0, 0 |
| Fears | 70,462,637 | 0, 0 |
| Banshee | 40,576,307 | 1, 1 (a Kickstart instruction) |
| Super Stardust | 67,488,880 | 0, 0 |
| Chaos Engine | 52,599,094 | 0, 0 |
| All New World of Lemmings | 62,198,151 | 59,006, 59,006 (the Kickstart's, 0.10 %) |

"All" means: the native game's trace (picture, sound, RAM and CPU registers of every frame) equals the fresh reference on every route, so
do the resload calls; the compressed copy replays equal; a quick state saved in it continues the same timeline in a fresh process and its 18
damaged copies are refused.

**Alien Breed 3D** stayed black on our A1200 model in 1.7.6, while the private oracle under the real WHDLoad shows its intro. Its slave
builds its own ExecBase with most vectors set to ILLEGAL and patches the game with `resload_PatchSeg`, whose offsets run across the
segments of a LoadSeg list by their stored sizes. Our `resload_Relocate` stored each size padded to 8 bytes (AmigaDOS stores the hunk's
size plus 8), so the slave's patches in the game's third segment landed 8 bytes early; its skip over the `ciaa.resource` probe fell inside
the probe, and the game called `OpenResource` through the slave's ExecBase. **Fixed in 1.7.7** (`rr_resload.c`, generic): the title and its
music come; the A1200 panel and six Amiga 500 installs give the same traces before and after (2,500 frames each, pictures included).

**Pinball Illusions** passed every check of the panel in 1.7.6, but after its intro the screen stayed black with the music playing
(Arthur's play test of 15 November 2026), where the private oracle under the real WHDLoad goes on to « Loading » and the title. The
interpreted reference machine showed the same black screen. It is the table-selection screen: F1 to F4 still choose a table on it
(Arthur), so in 1.7.6 the game can be played. The checks compare the native run with that machine, so they could not see
it. **Cause, found and fixed in 1.7.7:** the game was running and its copper list was the title's (`COP1LC` `$A748`, `DMACON` `$03FE`,
`BPLCON0` `$0611`: eight planes in dual playfield); it writes `$003F` to `BPLCON2`, priority 7 for both playfields. vAmiga drew a
dual playfield whose priority is above 4 transparent on every chipset, which only OCS and ECS Denise do; every pixel was colour 0. The
adapted Core keeps that for OCS and ECS only. Proof on the interpreted reference machine, before and after, 5,600 frames with no input:
sound, memory and CPU equal on every frame, the picture different on 870 frames, the first of them frame 4,731 (the title's first);
the title shows « Loading », then the rings and the credits, as the oracle's does. Slam Tilt and Roadkill (A1200) and Civilization (Amiga 500)
give the same trace before and after on 3,000 frames each, pictures included. Converted again at the standard level, Pinball Illusions passes
every check. Hardware fidelity is still not claimed: the rule for AGA is read from another emulator and the oracle, not measured on a
machine.

**G11 (private oracle).** Copperline (GPL-3.0, built privately, never shipped) runs the same install on its A1200 model under the real
WHDLoad 20.1, with no input, one picture a second; the converted game runs headless with no input, a picture every 5 frames over 70 seconds.
An oracle picture is "found" when it appears whole inside one of ours (8 bits per channel; lores widened to our hires columns, super-hires
taken every second pixel). Counts of the distinct non-black oracle pictures found: Slam Tilt 20 of 48, Pinball Illusions 24 of 37, Zool 2
18 of 23, Banshee 16 of 34, Roadkill 18 of 31, Fears 1 of 1, Gloom 2 of 4, Super Stardust 6 of 62. The pictures not found, looked at for Slam
Tilt and Super Stardust, are WHDLoad's own splash screen, fades and scrolls caught at other instants (Super Stardust's intro is a scrolling
text, almost every frame unique); no colour or layout difference was seen. A comparison of two emulators, not of the chips: G11 is `P`.

**Frame cost** (a quiet PC, Arthur's OK, 14 November 2026): Slam Tilt 10.6 ms a frame on the A1200 model, Lotus 2 on the A500 7.0 ms (PAL
frames are 20 ms). Our four fast paths of vAmiga's display stay off under AGA for now.

| Gate | a1200 | Evidence | What is missing |
|---|---|---|---|
| G1 | Y | The profile is declared `supported` (16 November 2026, the owner's decision), with its own column, library folder, quick-state family and path section; `tools/status_lint.py` agrees on the README, the compatibility page, the release notes and the interface strings in eight languages | | ? |
| G2 | Y | Every panel conversion writes the common report, its system `a1200`, its status read from the profile | | ? |
| G3 | Y | Interpreted instructions counted per route and shown (0 or 1, the 1 a Kickstart instruction) | | ? |
| G4 | Y | Native traces equal the fresh reference on every route of the panel | | ? |
| G5 | Y | The compressed copy replays equal on every route | | ? |
| G6 | Y | The quick state continues in a fresh process; 18 damaged copies refused, in every conversion | | ? |
| G7 | Y | `tools/amiga_saves_check.py --system a1200` on Super Stardust (16 November 2026, Windows, llvm, two conversions with fresh libraries): it writes `ssd.prefs` (94 bytes) by itself on the exploration route; the file is kept at relaunch and read back by the game; a quick state does not roll it back; cut to half or empty, the game still starts and runs; a refused save (a folder in the file's place) stops the game with WHDLoad's message, no temporary left (the game writes its preferences at start, so the folder case is that refusal too); kept after a second conversion, in one data folder | | ? |
| G8 | Y | Moving picture and sound on the routes (the conversion's liveness checks) | | ? |
| G9 | P | The routes reach play on Slam Tilt and Zool 2 (pictures); not checked install by install | A per-install record of where the routes end | ? |
| G10 | P | Moira's 68EC020 is the reference CPU; our lengths agree with Moira's disassembler on 19,084 random instructions. `tools/amiga_m68020_vectors.py` (16 November 2026, seed 1): 200,000 random instructions from random states, Moira as vAmiga builds it against Musashi's 68EC020 (an independent model, MIT, built for the check only): 192,264 equal on registers, SR, PC and the bytes written (clocks not compared); every one of the 7,731 others in a written family: 4,938 coprocessor instructions (no FPU on the A1200: Moira takes line F, Musashi models a 68881), 2,322 flags or results the manual leaves undefined (CHK, CHK2, DIV, BCD, MUL.L), 395 where Moira is right and this Musashi is not (PACK/UNPK byte order and RTE format error by the manual, LINK A7 by WinUAE's hardware-confirmed model), 76 to referee (MOVEM to -(An) with An listed, bit fields, CAS2) | A third model or hardware for the 76; Musashi is a model, not the silicon | ? |
| G11 | P | The oracle comparison above (8 installs) | Hardware evidence beyond another emulator | ? |
| G12 | Y | A panel of 9 named, none dropped: 8 pass every check, of which Pinball Illusions stayed black after its intro in 1.7.6; one did not start in 1.7.6 (Alien Breed 3D); both fixed in 1.7.7, named with the cause, converted again by the 1.7.7 candidate (`rc-177` at `35ac18c9`), every check passed, and played by the owner on 16 November 2026 | | ? |
| G13 | Y | Slam Tilt converted on a Debian 13 PC (GCC, tree `f5e125a6`, the standard level): every field of both routes equals the Windows report, every trace digest included. Then Pinball Illusions (the player's Kickstart 3.1), Gloom (Crunch-Mania) and Zool 2 at the standard level on WSL Debian 13 (GCC) and on Windows (llvm), tree `97f8712c`, 16 November 2026: every field of both routes of all three equal, trace digests included | A game played interactively on Linux (window, sound, pad) | ? |
| G14 | Y | The owner played the eight installs of [the checklist](#checklist-for-arthur-commodore-amiga-1200-play-test-g14) on 16 November 2026 (the exports of the 1.7.7 candidate in `Export\Games\Amiga 1200`) and decided the exit: « Je viens de tester les huit jeux Amiga 1200, ça marche impeccable, tu peux le sortir de l'expérimental. » (owner-acceptance table) | Eight installs played, not a coverage claim: code past the routes runs interpreted, counted and shown in the window title | ? |
| G15 | P | AMIGA.md section 7 and this section keep the five measures apart and name the failures | An exported A1200 game read in its window (the title naming the interpreter fallback), as on the Amiga 500 | ? |
| G16 | P | Shares its paths from 1.7.9 as the experimental tier of the base, like the Amiga 500, on the owner's word of 16 November 2026: « Je préfère que tu mettes en place directement le partage de chemin pour l'Amiga 500 et 1200. Ça permettra à tous les joueurs d'utiliser les temps de jeu des autres utilisateurs, même si à la recompilation du jeu, on n'a rien découvert. Il y a certaines personnes qui peuvent lancer des recompilations très avancées et nous faire découvrir d'autres chemins. » The measure with and without received paths was cancelled with it. `retrorecomp/a1200_knowledge.py` binds the Amiga 1200's rules (its `a1200` section, the 68EC020's lengths, its Kickstart 3.x of 512 KiB at $F80000) on the Amiga 500's module; numbers only; the record holds the fresh reference runs of a conversion that passed and the instructions the player's game ran on the interpreter in play (F12) that it made native. Proof in [AMIGA.md](AMIGA.md#shared-paths-179) | No path qualified in the base yet; the gain beyond the routes is not measured; a Kickstart 1.3 on the A1200 keeps its Kickstart rows private | ? |

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
