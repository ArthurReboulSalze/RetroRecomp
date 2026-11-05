# Game Boy Advance (experimental, in development)

Status: **experimental**, and not yet a converter: the profile, the cartridge reader, the report writer and the path
section exist; nothing is converted, and no installation lists the machine (it is a developer-only profile, like the
X68000 before its files shipped). This page says what the machine will be, what it will not be, how it is kept apart from
the others, and what is already known. It is a plan with evidence, not a claim about games.

The five measures stay separate here as everywhere: **native code** (how much of the game runs as generated code, with the
interpreter fallback counted per CPU), **CPU fidelity**, **hardware fidelity**, **gameplay validation** and **physical latency**.
None of them is claimed for this machine yet, and "exact" and "zero latency" are never written without proof.

## Scope of the first profile

Converted, when the conversion exists:

* a `.gba` cartridge, or a ZIP holding exactly one, for one player;
* the ARM7TDMI in ARM and Thumb states, as generated code with a counted interpreter fallback, including routines copied at
  run time from the cartridge into IWRAM or EWRAM;
* the picture (modes 0 to 5, affine layers, windows, blending, mosaic), the four DMA channels, the four timers, the interrupt
  controller, the two Direct Sound channels and the four tone and noise channels, and the keypad;
* cartridge saves of the three families (SRAM, Flash 64 KiB and 128 KiB, EEPROM) and the real-time clock of the cartridges that
  carry one, kept in the converter's own versioned battery format.

Left out of the first profile, and named so: link cable and wireless adapter, multiboot, e-Reader, the Game Boy Player, and the
cartridge sensors (gyro, tilt, rumble, solar light), which come later as host inputs named in the profile. The Game Boy Color is
a Game Boy profile matter, not this one.

## The BIOS

The machine needs the player's own system ROM (`gba_bios.bin`), supplied in **Options** like the Neo Geo BIOS and the X68000
IPL, and checked by its SHA-1 before anything uses it. It is never downloaded, supplied or published. The exported game holds
code derived from that file, so a converted game stays private to its player and the report says so. No replacement BIOS and
no high-level emulation of the BIOS calls is planned for the first profile.

## The engine

The recompiler and the machine runtime are `mstan/gbarecomp` (PolyForm Noncommercial 1.0.0; the maintainer holds the author's
permission, recorded in `THIRD_PARTY_NOTICES.md` like the other mstan engines), pinned by commit in
`retrorecomp/gba_conversion.py` (`ENGINE_REV`) and downloaded at that revision on the first conversion, never copied into this
repository. Its CPU core is the engine's own submodule `arm-recomp-core` (MIT), kept at the revision the engine records.
Our fixes are carried as anchored patches on a staged copy ([UPSTREAMS.md](UPSTREAMS.md)), not as a fork. The engine's netplay,
mod, upscaling and launcher parts are not used. The two engine files derived from mGBA (MPL-2.0, the optional high-level
BIOS) are not used either.

What a trial on 5 November 2026 established (a development measurement, not a qualification, on one revision of the engine):

* **CPU, one instruction at a time.** Against the public SingleStepTests ARM7TDMI vectors (45 files of 50,000, MIT, generated
  from a model, not from hardware): the engine's interpreter agrees on 93.1 % of all of them, and its generated code on
  91.0 % of an evenly spaced sample of 45,000. What disagrees is the three coprocessor families (not implemented in generated code),
  encodings with R15 as an operand and other architecturally unpredictable cases, the carry flag after a multiply, and a tail of
  250 failures not yet explained. Generated code agrees on every sampled branch, exchange, shift, load and store family, and on
  software interrupt entry in all seven modes.
* **Unseen cartridges, no per-game file.** Four commercial cartridges the engine had never been given ran headless with its
  default analysis: one ran its scripted generic input to the end with no interpreted instruction, two reached gameplay scenes
  with a few dozen distinct addresses on the interpreter, one stopped on a generated call-stack overflow. This is native code
  coverage only: the scripted input is not play and validates no gameplay.
* **Authored hardware tests** (jsmolka's gba-tests, MIT): the ARM, Thumb and BIOS tests pass; the VRAM mirror test, the three
  save tests (halfword stores to the save bus) and the no-save read test fail.

Known gaps, to be closed as general fixes in the staged copy and not per game, anchored as the other machines' patches are (stage 3 of the plan, in this order):

1. the generated call-stack overflow seen on one cartridge, a general cause of the generated call model and not a case of that game;
2. Thumb `CMP PC, Rm` lowered as an ARM compare with an exception return;
3. the 32 KiB VRAM mirror;
4. halfword and word stores to the 8-bit save bus;
5. reads of the save window of a cartridge with no save chip (must read `0xFF`);
6. about 250 single-instruction vector failures not yet explained.

## Paths

A path is a number about a cartridge, never bytes of it. The machine's schema 3 section is keyed by CPU and map:
`arm7tdmi` on `gba`. The function roots are `phys` entries, a cartridge offset whose lowest bit says Thumb (an ARM root is word
aligned, so the bit is free); the routines copied into IWRAM (`0x03000000` to `0x03008000`) or EWRAM (`0x02000000` to
`0x02040000`) are `span` rows (RAM address, cartridge offset, length). Both shapes already exist in the schema, so adding the
machine moves no other console's stamp. The jump-table and dispatch-target shapes come with the conversion. The machine does not
share its paths until its engine is stable (it is outside the shared base).

## What exists today

| Piece | File |
| --- | --- |
| Profile (developer-only, experimental) | `retrorecomp/systems/gba.py` |
| Cartridge reader: header, checksum, hash, save chip by library identification strings, BIOS hash | `retrorecomp/gba.py` |
| Engine pin, report skeleton through the common builder, plain refusal to convert | `retrorecomp/gba_conversion.py` |
| Tests, with a synthetic cartridge (no ROM) | `tests/test_gba_profile.py` |

The report is written by the common builder (`report_schema.write_report`) with the status read from the profile and the five
measures unclaimed; interpreted instructions are counted per CPU, in one unit.

## Plan

| Stage | Content | Gate reached |
| --- | --- | --- |
| 1. Engine gate | pin, build, vectors, unseen cartridges, authored tests, licence audit (done, development measurement above) | route chosen on data |
| 2. Profile | this page, the reader, the report, the path section, translations, registry, stamps, upstreams | G1 |
| 3. Conversion | staged copy and anchored patches, analysis with code copies and roots from our paths, observation at conversion, sharded build, counters per CPU, the report writer | G2, G3, G4 |
| 4. Host | the machine's player on the common host kit: pad, picture, sound, quick states, saves, counters | G5, G6, G7 |
| 5. Independent evidence | vector self-test, authored hardware tests, comparison with independent models | G10, G11 |
| 6. Panel and fixes | a small panel chosen by risk, general fixes only | G8, G9, G12 |
| 7. Release candidate | documents, release check, Linux witness | G13 |

Leaving the experimental status is the owner's own decision after a very high bar of evidence ([QUALIFICATION.md](QUALIFICATION.md)).
