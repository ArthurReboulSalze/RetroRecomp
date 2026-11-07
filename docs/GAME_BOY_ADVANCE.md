# Game Boy Advance (experimental, opening in 1.7.0)

Status: **experimental**. The converter turns a `.gba` cartridge (or a ZIP holding exactly one) into a standalone Windows game (a Linux one on a Debian 13 PC, see the
witness below) with your own BIOS: native code from what the game was seen to run, a counted interpreter for the rest, saves, quick states and the host kit's menus. The
machine is listed by an installation that carries its native files (`GAME_BOY_ADVANCE.available()`), like the PC Engine; there is no
developer switch. Experimental means what it means for the other machines: the evidence below is a first panel, not a qualification, and
leaving the status is the owner's own decision.

The five measures stay separate here as everywhere: **native code** (how much of the game runs as generated code, with the
interpreter fallback counted per CPU), **CPU fidelity**, **hardware fidelity**, **gameplay validation** and **physical latency**.
The comparisons below are against the engine's own interpreter, not against hardware or an independent emulator, and "exact" and
"zero latency" are never written without proof. The owner played the delivered exports on 5 and 6 November 2026 and wrote that they work
perfectly; that is a play trial of those files, recorded in [QUALIFICATION.md](QUALIFICATION.md), not a decision to leave the experimental status.

## Scope of the first profile

Converted:

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
  from a model, not from hardware): the engine's interpreter agrees on 93.96 % of all of them (2,250,000), and its generated code on
  91.08 % of an evenly spaced sample of 45,000 (figures of 5 November 2026, with the 30 patches of that day). What disagrees is the three coprocessor families (not implemented in generated code),
  encodings with R15 as an operand and other architecturally unpredictable cases, the carry flag after a multiply, and a tail that
  is now explained (below). Generated code agrees on every sampled branch, exchange, shift, load and store family, and on
  software interrupt entry in all seven modes.
* **Unseen cartridges, no per-game file.** Four commercial cartridges the engine had never been given ran headless with its
  default analysis: one ran its scripted generic input to the end with no interpreted instruction, two reached gameplay scenes
  with a few dozen distinct addresses on the interpreter, one stopped on a generated call-stack overflow. This is native code
  coverage only: the scripted input is not play and validates no gameplay.
* **Authored hardware tests** (jsmolka's gba-tests, MIT): the ARM, Thumb and BIOS tests pass; the VRAM mirror test, the three
  save tests (halfword stores to the save bus) and the no-save read test fail.

The gaps this trial found are closed as general fixes on the staged copy, anchored like the other machines' patches and listed in
[UPSTREAMS.md](UPSTREAMS.md) (stage 3 of the plan): the generated call-stack overflow seen on one cartridge (a general cause:
an interrupt handler left its call-return entries behind), Thumb `CMP PC, Rm` lowered as an exception return, the 32 KiB VRAM
mirror, halfword and word stores to the 8-bit save bus, reads of the save window of a cartridge with no save chip, the FIQ
register bank on interrupt entry. With them the authored ARM, Thumb, BIOS, memory and save tests all pass, and the call-stack
fix leaves three of the four cartridges bit for bit unchanged. What stays open: about 250 single-instruction vector failures
not explained (the coprocessor families, unpredictable encodings and the multiply carry among them), which the independent
evidence of stage 5 is for.

## What the conversion loop did on the four cartridges (5 November 2026)

Each cartridge went through `gba_conversion.convert` (two passes, a 600-frame boot scenario with no key and a 1,200-frame scripted
scenario, the player's BIOS, a headless host, nothing from the cartridge kept in the repository). A development measurement of
**native code coverage and of agreement between our generated code and the engine's own interpreter**; it is not CPU fidelity,
hardware fidelity or gameplay validation, and the interpreter is the engine's, not an independent oracle.

| Cartridge (by what it exposed) | Interpreted after the loop | Generated code against the engine's interpreter |
| --- | --- | --- |
| An authored ARM test | none | same picture, same cycles on both scenarios |
| One with a generated call stack overflow before the fix (a routine of 864 bytes the cartridge holds twice) | none (19 entries learned, the two copies read as one source) | boot same; the scripted scenario ended in the same scene with 135 pixels of a title animation different at frame 400, which came from where the two runs stopped, not from the machine (see the correction below): equal at 400 frames now |
| One that reaches menus quickly | none (21 entries learned) | same picture, same cycle count (228,998,554) on both scenarios |
| Two large action cartridges | none (the first needed no entry learned, the second 26) | same picture, same cycles |

Two causes had made the cycle counts of the generated code and of the interpreter drift on the third cartridge, and both were
the harness's or the engine's accounting, not the CPU: a store to WAITCNT charged the opcode fetch of that instruction with the
new wait states in the interpreter and with the old ones in the generated code (the hardware had fetched it already: the
interpreter follows the generated code now), and a scripted key word was applied between two dispatches, at different cycles in
the two modes (it is applied inside the VBlank tick now). A one-cycle offset at the end of a run is how the engine stops; the
report tolerates two cycles and says so.

**Correction of 5 November 2026 (the panel of stage 6).** Three things in this table were weaker than they read. (1) The "same cycles"
were the engine's `cycles=` of its final line, which is the cycles of its idle pump (the waits in HALT): it stops growing after the first
seconds and read 62,191,750 on three different cartridges, so it never compared anything. (2) A cartridge with a clock (Pokémon
Emerald) read the host's wall clock, and the interpreter replay lasts a hundred times longer than the native run, so the two saw different
seconds; every check now starts the clock from a fixed time and advances it with the guest's cycles, and a person playing keeps the host's
clock. (3) The interpreter left a bounded run as the frame counter changed, the generated code at the first VBlank unwind after it: on an animated
screen the final pictures differed by one step with equal CPU state (Emerald at frames 288, 290 and 600; the 135 pixels of the second
cartridge). The interpreter alone now waits for the same VBlank (two more anchored patches, `docs/UPSTREAMS.md`). What is compared now, for
each scenario, is the final picture, the guest's cycle count at the first VBlank after the frame limit (the same machine cycle in both
modes) and a hash of work RAM, IWRAM, VRAM, OAM, palette and I/O registers and one of the CPU registers taken there. Emerald agrees
on all of it at 600 frames (168,734,720 cycles, equal hashes); the cartridges of this table were replayed with the stronger check
on 6 November 2026 (next section).

## The panel of stage 6 (5 and 6 November 2026)

Six cartridges through the whole conversion (`convert`, the player included), one at a time, on a Windows PC, with the engine of the last section
of `docs/UPSTREAMS.md` (47 patches; 44 at the 1.7.0 panel). Scenarios: `boot` (600 frames, no key) and `generic` (3,600 frames, a script that presses A, Start, then Right and taps A
and B; it reaches menus and first scenes and proves nothing about gameplay). For each scenario the generated code and the engine's own interpreter run
alone and are compared on the final picture, the guest's cycle count at the first VBlank after the frame limit, a hash of work RAM, IWRAM, VRAM, OAM, palette
and I/O registers and a hash of the CPU registers. The clock of a cartridge that has one starts from a fixed time and follows the guest's cycles in every
check. The interpreter is the engine's, not an independent oracle.

| Cartridge | Save (header, engine) | Native = interpreter, 2 scenarios | Interpreted instructions (boot, generic) | Conversion | Packed player |
|---|---|---|---|---|---|
| Pokémon Emerald (BPEE, 16 MB) | Flash 128 KB, Flash 128 KB | yes | 0, 0 | 1,382 s | 37.9 MB |
| Mario Kart Super Circuit (AMKE, 4 MB) | Flash 64 KB, Flash 64 KB | yes | 0, 0 | 677 s | 13.1 MB |
| The Legend of Zelda: The Minish Cap (BZME, 16 MB) | EEPROM, EEPROM | yes | 0, 0 | 594 s | 23.0 MB |
| Pokémon Mystery Dungeon: Red Rescue Team (B24E, 32 MB) | Flash 128 KB, Flash 128 KB | yes | 0, 0 | 767 s | 47.3 MB |
| Super Mario Advance 2 (AA2E, 4 MB) | EEPROM, EEPROM | yes | 0, 0 | 1,173 s | 16.5 MB |
| Golden Sun (AGSE, 8 MB) | Flash 64 KB, Flash 64 KB | yes | 36,339, 17,740,494 | 546 s | 15.9 MB |

The packed player of each runs 600 frames hidden and silent with return code 0 and a non-empty picture and sound; that is a smoke test of the player, not
gameplay. Golden Sun draws a single colour at frame 600 (its own slow start, the same picture in both modes) and a scene of the village at frame 3,600. The five
first rows have no instruction left to interpret on the tested scenarios; that is a coverage of those scenarios, not of the game.

What the panel found, in the order it happened (each one is a patch of the engine, `docs/UPSTREAMS.md`, found by the comparison and by no other check):

1. **The clock.** A cartridge with a clock read the host's wall clock; the interpreter replay lasts a hundred times longer than the native run, so the two saw
   different seconds. The checks start the clock from a fixed time and advance it with the guest's cycles; a person playing keeps the host's clock.
2. **The end of a run.** Three different ways of ending a bounded run in the two modes gave pictures one step apart (Emerald), a frame later (Golden Sun) or no
   state at all (Mario Kart at 600 frames). Both modes now end on the VBlank where the state was taken.
3. **The engine's `cycles=` line.** It is the cycles of the idle pump (waits in HALT), constant at 62,191,750 on three cartridges; it compared nothing. It was
   replaced by the guest's cycle count and the two hashes.
4. **HALT inside a bridge.** A game whose own loop runs from RAM is interpreted through a bridge. The bridge did not wait in HALT as the runner does, so the game went
   on while the machine should have waited for its interrupt: native and interpreter parted at frame 290 to 300 of Golden Sun, with equal cycle counts at the
   limit. This touches every game that has a bridge; the cartridges above were replayed after the change.
5. **The bridge's length and its yield.** The engine stops a bridge after 200 million interpreted instructions, which killed Golden Sun (a working game, its main
   loop is a bridge). The count now restarts when the work RAM changes at a VBlank; a bridge whose work RAM never changes is still stopped and named (checked
   with a program of our own: exit code 3 after 15 s). The bridge also leaves at the VBlank yield point of the generated code, as the player's frame step needs:
   without it the packed player of Golden Sun never returned from its first frame (test killed after 900 s).

### Golden Sun

Its main loop and part of its code run from work RAM. Of the 37 RAM addresses the engine had to interpret on the first run, 21 resolve to a copy in the
cartridge once the probe records the bytes found at the time of the miss (the RAM at the end of a run is another routine's), and the report says why the others stay
interpreted (`unresolved_reasons`). The remaining ones have no copy in the cartridge: 15 Thumb routines in `0x02008030..0x02008436` and an ARM routine in IWRAM at
`0x03000828` (326,128 bridges in 3,600 frames) are code the game decompresses or writes at run time. The interpreter counted them (17.7 million instructions in
3,600 frames, 62 million before the changes above). They are native since 7 November 2026 (section "Code the cartridge does not hold", below).

What this table does not say: gameplay validation (none), hardware fidelity beyond what the authored test ROMs check, physical latency, the Linux player (built by the
witness below, never played) and any cartridge outside the six.

## Multi-language cartridges: the in-game language and the save (6 November 2026)

The language of a game is the game's own, chosen in its own menus; the converter does not touch it (the interface language of Retro-Recomp is another thing,
`F7` in the player). Two European or multi-language cartridges were converted and driven with the player itself (the delivered executable, hidden and silent,
with a key script and a scratch data folder; the last picture of each run was looked at).

| Cartridge | Conversion | Interpreted (boot, generic) | What was seen |
|---|---|---|---|
| Sonic Advance 2 (USA; En, Ja, Fr, De, Es, It; Flash 64 KB, 16 MB) | 1,045 s, 30.7 MB packed | 0, 0 | With no save the game asks "SELECT A LANGUAGE" (six choices). Choosing Deutsch gives the German name screen (NAMEN REG.); after the name is registered the game writes its 64 KB save. Started again with that save and no key: no language screen, the German title ("START DRÜCKEN") at 1,500 and 2,000 frames, the save file unchanged. The same executable with no save shows the language screen again. |
| Alien Hominid (Europe; En, Fr, De, Es, It; EEPROM, 8 MB) | 629 s, 11.8 MB packed | 0, 20.6 million | The language screen works (Italiano gives "PREMI START" and the Italian menu). This game does not keep the language: the 512-byte save is identical after choosing English and Italian, and the game asks again at the next start, so it proves the choice but not its persistence. |

What this shows: the cartridge save written by the player carries the game's own language setting across a restart, for the cartridge that stores it (Sonic Advance 2),
and a cartridge that does not store it writes the same bytes whatever was chosen (the player adds nothing). It does not show every language of every cartridge, the Japanese
text of any game, or that a save from real hardware is read back: the saves here were written by the player. On the restarted Sonic Advance 2 the demo that
follows the title ran 1.09 million instructions on the interpreter in 3,000 frames (code that the two scenarios of the conversion never reached; counted, reported, and
learned by the next conversion).

## The Linux witness of the six cartridges (6 November 2026)

One pass, on a Debian 13 PC (Python 3.13, GCC 14, Ninja), of the six cartridges of the panel through `batch` from the tree to merge: the files
of the commit `31e39aee`, taken with `git archive` (no leftover of earlier runs), with `linux = 'witnessed'` as the only change (the gate of
`platforms.require_backend` refuses a conversion on Linux while the profile says `pending`). The commit after it changes this page only, so the merged
tree equals the witnessed one except for that flag and this page. The run started from an empty library of observed entries, with three passes at most, and
took 316 minutes for the six, one at a time.

| Cartridge | Native = interpreter, boot and generic | Picture hash and guest cycles equal to the Windows run | Interpreted instructions, boot / generic (Debian) | Windows panel |
|---|---|---|---|---|
| Pokémon Emerald | yes | yes, both scenarios | 0 / 0 | 0 / 0 |
| Mario Kart Super Circuit | yes | yes, both | 0 / 0 | 0 / 0 |
| The Minish Cap | yes | yes, both | 972 / 1,450,569 | 0 / 0 |
| Pokémon Mystery Dungeon Red | yes | yes, both | 0 / 0 | 0 / 0 |
| Super Mario Advance 2 | yes | yes, both | 0 / 0 | 0 / 0 |
| Golden Sun | yes | yes, both | 43,087 / 38,805,055 | 36,339 / 17,740,494 |

What it says: on a second operating system, a second compiler and the Linux linker, the generated code of six cartridges equals the engine's own
interpreter on the final picture, the guest's cycle count and the state hashes at the first VBlank after the limit, and the final picture hash and the
cycle count equal the Windows ones in the 12 scenario runs. Two things were found on the way: GNU ld needs the engine's four mutually recursive static
archives in one `--start-group` (both CMake templates now have it, for non-Windows builds only; the Windows build is unchanged), and the gate above.

What it does not say. The interpreted counts of the Minish Cap and Golden Sun differ from the Windows panel: the Windows runs started from entries observed in
earlier runs, the Debian pass from none and stopped after three passes, so the two counts are not a comparison of the platforms and are not proven to be
anything else either; the checks above hold with them (the interpreter is counted, as always). The Linux player was built and packed by the same pass but
nobody played it and nothing was timed: gameplay validation, hardware fidelity and physical latency are untouched by this witness.

## Code the cartridge does not hold: guarded native RAM code (7 November 2026)

Some games build code in work RAM that no stretch of the cartridge holds (a decompressed overlay, a routine written word by word by another one). Until then
such a routine was interpreted, counted, and left in the report as "no copy". Now the converter makes it native under a guard, in four steps, all in the
Game Boy Advance files (`gba_analysis.py`, `gba_conversion.py`, three patches of the engine in `gba_patches.py`):

1. **The probe records the bytes** found at a RAM address when the game first reaches it with no generated function, once per *version*: a new sample is kept when
   it differs from the recorded ones outside the words that have already taken eight different values (up to 256 versions an address). Before, eight whole-hash
   versions were used up by one routine whose caller rewrites two arguments in its literal pool, and the routines that followed in the same place were never seen.
2. **The converter keeps them in memory only** (`RamCode`). They are derived from the cartridge, so they are not paths: the paths library still holds numbers
   about the cartridge and nothing else, and the bytes of a version reach the generated code of the player's own game (which holds the cartridge anyway) and no
   file of the repository or the library. The generator is given the cartridge followed by those bytes (`generator_image`, each block aligned like its RAM address,
   a zero gap after it, at most the 32 MiB window of the bus; beyond that the routine stays interpreted, reported as RAM code still reached by the interpreter).
3. **The versions are told apart.** The generator keeps one function per address, so the first version of a routine keeps its address and the next ones are named
   at the mirrors of the work RAM (IWRAM repeats every 32 KB, EWRAM every 256 KB); the guard of the generated code compares bytes and uses the live address, so the
   mirror is only a name. The same rule now applies to copies from the cartridge: two overlays swapped into the same IWRAM address from different cartridge offsets
   used to collapse into one native function.
4. **Arguments are not code.** A word that took eight or more values across the versions of a routine is an argument its caller writes into the routine's
   literal pool (read by the routine from the live RAM). It is declared to the generator as a data range and the guard of the fragment does not compare it
   (an engine patch; the generator refuses a control flow that enters a declared data range, so an instruction word taken for an argument stops the conversion
   instead of being compiled stale). One version per code shape is built.

What the guard still is: a fragment of at most 64 bytes is entered only if the live bytes equal the bytes seen (outside the argument words), and a routine whose bytes
are none of the versions seen goes to the interpreter, counted, as before. The report names the numbers (`native_coverage.ram_code`: addresses, versions, entries,
argument words, bytes added to the image) and the reasons that remain.

Measured on 7 November 2026 on a Windows PC (the same probe scenarios as the panel, three passes asked and up to two settling ones, native equals the engine's interpreter in
both scenarios, final picture hash and guest cycle count identical to the 1.7.0 panel):

| Cartridge | Interpreted instructions, boot / generic, 1.7.0 | Now |
|---|---|---|
| Golden Sun | 36,339 / 17,740,494 | 0 / 32,394 |
| The Minish Cap | 0 / 0 (Debian witness: 972 / 1,450,569, see above) | 0 / 0 |
| Pokémon Emerald | 0 / 0 | 0 / 0 |

Golden Sun's 40,656 calls of the IWRAM routine (three code shapes, three argument words) are native; what is left is two Thumb routines of EWRAM seen on the last
pass. The packed players of Golden Sun and the Minish Cap run 600 frames hidden with return code 0, sound and no interpreted instruction. The Minish Cap now
reaches 0 / 0 in the first pass because its paths are in the library of the machine that converted it; the Debian witness above started from an empty library.
Played: the owner played the delivered Golden Sun and Minish Cap of this stage on 7 November 2026 and wrote that they work perfectly (a play trial of the exports, not a measure of gameplay validation and not a decision to leave the experimental status). Not measured: gameplay validation (no route of ours), the Linux player with this code, a cartridge whose RAM code does not fit the 32 MiB window.

## The wider panel (7 November 2026)

Four more cartridges chosen by the owner, through the whole conversion (`batch`, online covers on, the player included), one at a time, on a Windows PC, with the tree of
7 November 2026: a second Flash 64 KB cartridge, three SRAM ones, and one (Metroid Fusion) whose code the engine finds entirely by itself. Scenarios: `boot` (600 frames) and `generic` (3,600 frames), compared with the engine's own interpreter as in the panel above.

| Cartridge | Save (header) | Native = interpreter, 2 scenarios | Interpreted instructions (boot, generic) | Paths learned (ROM roots, RAM copies) | Packed player |
|---|---|---|---|---|---|
| Advance Wars (USA, Rev 1) | Flash 64 KB | yes | 0, 0 | 528, 3 | 9.6 MB |
| Castlevania: Aria of Sorrow | SRAM | yes | 0, 0 | 26, 5 | 21.2 MB |
| Metroid Fusion | SRAM | yes | 0, 0 | 0, 0 | 20.8 MB |
| Wario Land 4 | SRAM | yes | 0, 0 | 26, 0 | 19.5 MB |

Every report names `FULLY_STATIC` for both scenarios and an embedded libretro cover; none needed RAM code. The packed players run 600 frames hidden with return code 0,
sound and no interpreted instruction. Nothing was found that needed a change: the four were converted by the tree of the previous stage as it stands. What this
adds is breadth of cartridges and save types (ten cartridges in all); it is not gameplay validation, and nobody of ours played these four.

### The Linux player played by script (7 November 2026)

The witness above converted on Linux but never ran the Linux player. On 7 November 2026 two cartridges were converted on a Debian 13 PC (GCC 14, Python 3.13,
Ninja, an empty library) from the tree of the same day and their Linux players were run under Xvfb, with the window, the OpenGL renderer and vsync on, the
sound device replaced by SDL's dummy driver, and the same key script as the Windows players (`generic`: A, Start, Right, taps of A and B), for 1,800 frames.

| Cartridge | Conversion on Debian | Native = interpreter (2 scenarios) | Picture at frame 1,800 | Sound counts (samples, non-zero, peak) |
|---|---|---|---|---|
| Golden Sun | 34 min 29 s, five passes | yes | SHA-256 equal to the Windows player's (`2904e7e6…`) | 987,391, 622,846, 21,408: equal |
| Metroid Fusion | 21 min 15 s, one pass | yes | SHA-256 equal to the Windows player's (`1a1ae4f4…`) | 987,911, 852,299, 32,767: equal |

The pictures and the sound counts are those of the Windows players, to the last bit, and the final picture hash and the guest's cycle count of both scenarios in the
reports equal the Windows ones. The window ran at the display's rate (about 31 s for 1,800 frames). This is a scripted run, not a person playing; the owner decided on
7 November 2026 that it counts as the cross-OS witness of gate G13. The sound counts are counts: the sound itself was not heard, nor recorded.

One thing the pass showed about the converter, not about Linux: Golden Sun converted from an **empty library** ends its five passes (three asked, two settling)
with 5.3 million interpreted instructions on the generic scenario (boot: 0), where the Windows machine, whose library already held the paths of earlier runs, ends at
32 thousand. The picture and the cycle count are the same; what is not yet found when the passes stop is interpreted, counted, and kept for the next conversion of the
same cartridge (the paths are saved before the long replay). A first conversion of this cartridge therefore stays at several million interpreted instructions until
it is converted again, or until more settling passes are allowed; the page does not promise the figure of the table above for a first conversion.

## Independent evidence (stage 5)

Two tools are in the repository, both outside the converter's path and run on demand; the test material is downloaded by the
player and stays outside the repository (hashes and counts only are written here).

* `tools/gba_hardware_selftest.py` converts the authored hardware tests (jsmolka's gba-tests, MIT) through the converter's own
  probe and judges the final picture against the suites' passing screen. The eight self-checking suites (ARM, Thumb, memory, BIOS and
  the four save variants) **pass**, all with the same picture, none with an instruction on the interpreter once the observations of
  a first run are learned; the three picture tests are not judged and are never counted as passed.
* `tools/gba_vector_selftest.py` (with `tools/fetch_gba_vectors.py`, pinned to revision `e3097d88`, 45 files of 50,000) stages the
  patched engine and runs SingleStepTests/ARM7TDMI (MIT, generated from NanoBoyAdvance: a model, not hardware) against the engine's
  interpreter (all 2,250,000 vectors) and the generated code (a sample of 45,000). On 5 November 2026 with the 30 patches: the
  interpreter agrees on **93.96 %** (the 136,000 failures are 75,516 coprocessor instructions, 11,554 multiply carries, 48,476
  encodings with R15 as an operand and unpredictable cases, and **385 other**, of them 247 `LDM`/`STM`, 88 Thumb `LDM`/`STM` and 50
  `PUSH`/`POP`); the generated code agrees on **91.08 %** (3,000 coprocessor, 230 multiply carry, 774 R15, **11 other**). The patches
  moved the interpreter by about 18,000 vectors (the FIQ bank on interrupt entry among them) and the generated code by 12. The
  coprocessor instructions are not implemented in generated code, by the engine's design, and the multiply carry and R15 cases are
  where the model and the architecture's unpredictable results meet. This is CPU fidelity against a model, not against hardware.

  **The tail, explained on 7 November 2026** (the raw log of that run decoded, no new run; `tools/gba_vector_selftest.py report` now names two more
  classes and the unexplained count is 0 in both checks). Of the 385: 247 are ARM `LDM`/`STM` with the S bit (user bank) **and write-back** in a banked mode
  (FIQ, IRQ, supervisor, abort, undefined), an encoding the architecture leaves unpredictable and for which the model chooses one base register and one set
  of written-back registers; and 138 (88 Thumb `LDMIA`/`STMIA`, 50 `PUSH`/`POP`) are Thumb block transfers with an **empty register list**, where the
  ARM7TDMI transfers R15 and moves the base by `0x40`. The model has that behaviour; the engine's interpreter and its generated code do not. The 11 of
  the generated code are the same two classes (7 and 4). So nothing in the tail is a defect in the transfers of real registers; the Thumb empty list is a
  known hardware behaviour that is not modelled (hardware fidelity), not seen in the games of the panel, and not worth an engine patch before a game needs it.

## The player (stage 4)

The exported game is a Windows executable that links the engine's runtime, the cartridge's generated code, the code generated
from the player's own BIOS, the host kit's shell and `native/hostkit/adapters/rrhk_gba.c`, and carries the cartridge and the
system ROM as resources (it stays private to its player). The engine's window loop is not used: `native/gba_driver.h` is the seam
(a driver installed before `run_game()`, called once the machine is built, instead of the loop), `native/gba_machine.cpp` is the
driver and the machine's side of the adapter. The machine steps one frame from VBlank to VBlank; the kit does the window, the
pacing, the controls, the menus, the quick state and the sound.

| | |
| --- | --- |
| Picture | 240 x 160, the engine's latched frame (RGB888) turned into the kit's 0xAARRGGBB |
| Sound | the engine's mono blocks at 32,768 Hz times a power of two, averaged down to 32,768 Hz, into the kit's ring |
| Controls | ten buttons (A, B, L, R, Select, Start, the pad), one player; the kit's bindings, autofire and controllers |
| Quick state | F8 / F9, one slot: the engine's own container (magic, version, ROM SHA-1), 0.6 MB, in `datas/states` |
| Battery | SRAM, Flash or EEPROM, the engine's raw file in `datas/saves`, written at most every two seconds when it changed and at exit |
| Reset | a power cycle: the machine is built again in the same process (the window is created again) |
| Honesty | the interpreter's instruction count and the engine's coverage report (with the addresses it ran), in `datas/learning` |
| Not yet | the RTC and the sensors beyond what the engine does, the box-art icon on a first conversion without the network, compression of the executable, the gameplay feedback record; Linux: the conversion is witnessed (below), the Linux player was never played |

Checked on the first game (a hidden window, no sound device, development measurements): the player's picture at frame 300 is
pixel for pixel the probe host's; a quick state saved at frame 200 and loaded at frame 260 gives the same picture 60 frames later;
the machine produces sound (a peak of 19,200 on a 16-bit scale after a few seconds); a power cycle builds the machine again and
runs on; the pacing is 59.7275 Hz. None of this is a gameplay validation.

## Paths

A path is a number about a cartridge, never bytes of it. The machine's schema 3 section is keyed by CPU and map:
`arm7tdmi` on `gba`. The function roots are `phys` entries, a cartridge offset whose lowest bit says Thumb (an ARM root is word
aligned, so the bit is free); the routines copied into IWRAM (`0x03000000` to `0x03008000`) or EWRAM (`0x02000000` to
`0x02040000`) are `span` rows (RAM address, cartridge offset, length). Both shapes already exist in the schema, so adding the
machine moves no other console's stamp. The jump-table and dispatch-target shapes come with the conversion. The machine does not
share its paths until its engine is stable (it is outside the shared base). Paths a conversion learns stay in the player's own library;
bytes derived from the cartridge never go there.

## What exists today

| Piece | File |
| --- | --- |
| Profile (experimental, listed with its files) | `retrorecomp/systems/gba.py` |
| Cartridge reader: header, checksum, hash, save chip by library identification strings, BIOS hash | `retrorecomp/gba.py` |
| Engine pin, the conversion loop (observe, learn paths, rebuild), the player export, the report | `retrorecomp/gba_conversion.py` |
| The player: the project of the executable, its resources, the kit | `retrorecomp/gba_player.py`, `native/gba_machine.cpp`, `native/gba_machine.h`, `native/gba_driver.h`, `native/hostkit/adapters/rrhk_gba.c` |
| Checkout of the pinned engine and the staged, patched copy | `retrorecomp/gba_engine.py`, `retrorecomp/gba_patches.py` |
| Misses to roots and RAM routines, the engine's configuration | `retrorecomp/gba_analysis.py` |
| Recompiler, BIOS and game generation, the headless probe host, the key scripts | `retrorecomp/gba_build.py` |
| Tests, with a synthetic cartridge and a faked toolchain (no ROM, no BIOS) | `tests/test_gba_profile.py`, `tests/test_gba_conversion.py`, `tests/test_gba_player.py` |

The report is written by the common builder (`report_schema.write_report`) with the status read from the profile and the five
measures unclaimed; interpreted instructions are counted per CPU, in one unit.

## Plan

| Stage | Content | Gate reached |
| --- | --- | --- |
| 1. Engine gate | pin, build, vectors, unseen cartridges, authored tests, licence audit (done, development measurement above) | route chosen on data |
| 2. Profile | this page, the reader, the report, the path section, translations, registry, stamps, upstreams (done; listed since the 1.7.0 preparation) | G1 |
| 3. Conversion | staged copy and anchored patches, analysis with code copies and roots from our paths, observation at conversion, sharded build, counters per CPU, the report writer | G2, G3, G4 |
| 4. Host | the machine's player on the common host kit: pad, picture, sound, quick states, saves, counters | G5, G6, G7 |
| 5. Independent evidence | vector self-test and authored hardware tests (done, see above); comparison with an independent emulator (not done) | G10, G11 |
| 6. Panel and fixes | a small panel chosen by risk, general fixes only | G8, G9, G12 |
| 7. Release candidate | documents, release check, Linux witness (the Debian pass of the tree to merge, see [the section](#the-linux-witness-of-the-six-cartridges-6-november-2026)) | G13 (`P`, done 6 November 2026) |

Leaving the experimental status is the owner's own decision after a very high bar of evidence ([QUALIFICATION.md](QUALIFICATION.md)).
