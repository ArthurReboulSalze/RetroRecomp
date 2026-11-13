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

Measured on 7 November 2026 on a Windows PC (the same probe scenarios as the panel, three passes asked and up to two settling ones (four since, see the Linux section below), native equals the engine's interpreter in
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

One thing the pass showed about the converter, not about Linux: Golden Sun converted from an **empty library** ends its passes with millions of interpreted
instructions on the generic scenario (boot: 0), where a machine whose library already held the paths of earlier runs ends at 32 thousand. With two settling passes
(five in all) the Debian pass ended at 5.3 million. With **four** (`SETTLING_PASSES`, seven in all, only while the last pass still taught something) a conversion
from an empty library on a Windows PC took 16 min 23 s in all, the player included, and ended at **3.9 million** (passes 5 to 7: 5.35, 4.17, 3.86 million); the
report counts no unresolved miss at the end, the last three addresses having been turned into paths by the last pass. The picture and the cycle count are the same as
with the full library. So every pass peels one layer (a routine reached only once the one before is native) and seven are not enough for this cartridge from
nothing; what is not found when the passes stop is interpreted, counted, and kept (the paths are saved before the long replay), so a second conversion of the same
cartridge continues from there. The figure of the table above (32 thousand) is that of a converted-again cartridge; the page does not promise it for a first conversion.

## The verdict is enforced, and a first conversion converges faster (12 November 2026, 1.7.3)

**A conversion that differs from the interpreter fails.** `validation_failures` (`gba_conversion.py`) reads the native runs against the engine's own
interpreter, and `convert` raises `ConversionError` when a native run errored, when a scenario was not replayed, or when the picture, the guest cycle count,
the memory hash or the CPU hash differ. Before, a native run that errored did not count as a difference and a mismatch did not stop the conversion. Proved on an
authored cartridge with a forced mismatch (`induced.py` of the maintainer's scratch folder): the conversion is refused, no report and no game are written. A batch
that fails with received rows converts the cartridge once more without them (see *Paths*).

**The bridge proposes its callees.** When the engine reaches a routine with no generated function it interprets it *with its whole call subtree*, and until now the
callees of that subtree became visible one layer per pass: each pass found the next layer of calls and the conversion needed as many passes. A patch of the
probe host (`rr_bridge_callee`, in `gba_patches.py`, 52 patches in all) records, while the bridge interprets, every `BL`/`BLX` target and every computed
non-return jump (`BX`, `MOV PC`, `LDR PC`) as a miss with count 0 ("bridged x0"); the next pass has them as roots. It does not propose a return (a transfer that
closes a call the bridge opened, an exception return, the stop address), only exact work-RAM windows, one target once, and it saves the proposals once every 32
new targets and at the end. Native equals the engine's interpreter on every scenario of every cartridge below; a proposed address the generator cannot use is
refused as before and the conversion fails visibly. It is the recorder, not the generated code, that changed: the paths the first pass learns are numbers about the
cartridge, like all others.

Measured on 12 November 2026 on a Windows PC, four cartridges from an **empty** library (a scratch one), three passes asked, `--jobs 1`, the PC being used for
other work (the times are not a benchmark):

| Cartridge | Interpreted, pass 1 (boot / generic) | Passes to 0 / 0 | Total time |
|---|---|---|---|
| Advance Wars (USA, Rev 1) | 2,044,548 / 60,656,952 | 2 | 49 min |
| Golden Sun | 2,581,873 / 72,238,564 | 5 (3 asked, 2 settling) | 22 min |
| The Minish Cap | 1,636,808 / 19,684,139 | 3 | 18 min |
| Pokémon Emerald | 106,192 / 3,782,142 | 2 | 41 min |

Most of the time is the long replay of the scenarios with the interpreter alone (Advance Wars, 45 minutes of the 49), not the passes. Golden Sun from an empty library
took seven passes and ended with 3.86 million interpreted instructions in generic before the patch; with the first version of the patch it took four passes (19.6 minutes) and 0;
the version with the guards above takes five, one more settling pass, and reaches the same 0 / 0. Not measured: a Linux conversion with the patch (asked of the Debian slot), cartridges outside these four.

## Thumb blocks with an empty register list, and the loads left (12 November 2026)

ARM7TDMI stores the program counter plus six (not plus four) when a Thumb `STMIA` or `PUSH` has an empty register list, and transfers sixteen words
(the register base moves by 0x40). Two engine patches (`interpreter.cpp` and `arm_codegen.cpp`) give the interpreter and the generated code that stored value.
`tools/gba_vector_selftest.py` on the SingleStepTests/ARM7TDMI vectors (a model's behaviour, not hardware): the `thumb_empty_list` class falls from 138 to 76 of the
interpreter's vectors and from 4 to 2 of the generated code's (two stores of the class are now agreed; the overall agreement is 93.96 % and 91.08 % as before,
the class was a few vectors out of 2.25 million). What is left in the class is the **loads** (`LDMIA`/`POP` with an empty list), a hardware behaviour the engine does not model; the
class is narrowed to them, a store that still fails would be counted as `other`, and `other` is 0. The patch moves the Game Boy Advance game stamp with the others.

## The silent caps are counted (12 November 2026)

Four limits of the guarded RAM code were silent: the report now counts them in `native_coverage.ram_code.caps`:
`versions_refused_by_the_converter` (the converter keeps at most 256 versions of an address), `addresses_capped_in_the_probe` (the probe's own bound; it writes
`CAPPED address n` into the miss-bytes file the converter reads), `versions_without_a_mirror` (a version that cannot be named at a work-RAM mirror) and
`image_over_the_cartridge_window` (the RAM code that does not fit the 32 MiB bus window and stays interpreted). A figure above zero is a reason a routine is
interpreted, shown beside the instruction counts; it is not a defect by itself.

## The fresh process: states, saves and route depth (12 November 2026)

The checks were made in one process. `tools/gba_fresh_process.py` (`state`, `save` and `keys` subcommands; 34 tests that need no ROM) runs the **delivered**
executable in separate processes and compares what comes out. The player has a test switch for it, `RETRORECOMP_GBA_STATE=save@N,load@K=N`, read by
`native/gba_machine.cpp` (saves the quick state at guest frame N, or loads it at frame K, in a hidden player; the switch is the one thing that moves the Game Boy
Advance game stamp in this item, together with the engine patches).

* **G6, states.** Metroid Fusion: a state saved at frame 1500 of a run, then a *new* process started from the cartridge and loaded at frame 2: 200 frames later the
  picture's SHA-256 is the first process's (a control run that does not load differs). The second route (no key, saved at frame 600, loaded at frame 5, 300 frames
  later) is equal too. Both players ran with 0 interpreted instructions. The state file is 586,348 bytes.
* **G7, saves.** Sonic Advance 2 (a 64 KB Flash chip): process A, from no save, picks the language and enters a name (`sonic_advance_2_save_write.keys`) and the
  cartridge writes the file (8,140 bytes differ from the erased fill, 29 distinct values: not trivial); process B, with that file and no key, shows the saved game
  (Sega logo, title) where a control with no save asks for the language; the file is identical after process B. One cartridge, one chip family; EEPROM and SRAM
  were not exercised this way.
* **G9, route depth.** Four scripted routes in `tools/gba_routes/`, run on the delivered players at several lengths and in several processes, 0 interpreted
  instructions on every run (`FULLY_STATIC`, no miss): Advance Wars from the title to Nell's lesson on the first Field Training map (about frame 5,000, 10,000
  frames run), Wario Land 4 from the title to Entry Passage with Wario in play (about frame 4,200, 10,000 frames), Metroid Fusion from the title through the long
  opening story to Samus under control in the Navigation Room (about frame 24,000, 30,000 frames run) and the Sonic Advance 2 pair above. They are what the player
  sees in the first minutes of play, not a level or a boss. No bug was found by these runs.

All of this is native code coverage and a comparison of one executable with itself in another process. It says nothing about gameplay validation or hardware fidelity.

## The cost of a frame (12 November 2026)

`tools/gba_frame_cost.py` (12 tests, no ROM) measures the host time of the same frames of a cartridge in the probe host, native and with the interpreter alone,
interleaved A/B, the best of N, with a banner that asks for a quiet PC. It states **host time**; it is not a latency, not a cost on the player's machine and not a
comparison with a real console. Its plumbing was exercised on a normal PC on 12 November 2026 (2.3 ms a frame on a busy machine, which is not a figure); the quiet-PC pass is not
done and no figure is claimed here.

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
machine moves no other console's stamp. The jump-table and dispatch-target shapes come with the conversion. Paths a conversion learns stay in the player's own library;
bytes derived from the cartridge never go there.

### Sharing the paths, stage A (12 November 2026, 1.7.3; experimental tier, not yet deployed)

The machine can send and receive its paths in the experimental tier of the base (`retrorecomp/gba_knowledge.py`, `SharedKnowledge('experimental', withdrawable=True,
quick_check_from_shared=False, module='gba_knowledge')`), on the pattern of the PC Engine: a schema 3 record with an **empty layout**, so `path_profiles.py`, which
every console's game stamp hashes, is not edited and only the Game Boy Advance game stamp moves.

* **What travels.** The ROM roots (`phys`, offset and Thumb bit) and the RAM copies (`span`: RAM address and Thumb bit, cartridge offset, length) of one exact cartridge
  (`gba:<SHA-256 of the cartridge>`), numbers only. An ARM root and an ARM copy are word aligned in the cartridge and in RAM; a received record holds at most
  262,144 roots and 4,096 copies (`PATH_CAPS`), and at most 8 versions of one RAM address.
* **What never travels.** The bytes of a RAM routine, their versions and argument words, anything derived from the BIOS. A record is made only from rows **this**
  conversion's own runs executed, after both scenarios were equal to the engine's interpreter. A row it received and did not itself reach is not in the record it makes:
  `qualified_by_this_converter` is always 0 and no received row is saved in the player's library.
* **How a received row is used.** As a hint: a *pending* root (not yet qualified) is given to the generator as a declared root, in a deterministic order of a hash of
  the cartridge and the offset (not the lowest offsets, so low-offset junk cannot crowd out the rest), at most 16,384 per cartridge; what the cap leaves out is counted
  (`left_out_by_the_cap`). A row is *qualified* only when a window of a conversion executed it, and the key of a record is the engine pin and our revision of its use
  (`cores` = SHA-1 of `gba:<PATH_REVISION>:<ENGINE_REV>:<ARM_CORE_REV>`), not our game stamp; a test pins the recompiler-side patches and the probe's recorders so that a
  patch a path could notice raises the revision by hand.
* **When it fails.** If the conversion with received rows fails (the generator refuses a root, or the generated code differs from the interpreter), `convert` converts the
  cartridge once more without them and says so in the report (`set_aside_after_a_failure`). The report's `shared_paths` block counts received, used, left out and qualified.
* **Audit.** `tools/gba_bogus_rows_audit.py` invents 2,000 valid-but-meaningless roots and RAM copies and converts a cartridge with them as the imported bank of a
  scratch library; it requires `bogus_rows_in_players_paths` and `bogus_rows_in_promoted_record` to be 0 and the conversion to pass. Result on the Minish Cap (12 November 2026, scratch
  library, nothing shared): with 2,000 bogus roots and 2,000 bogus RAM copies, then with 150 roots and 20 roots, **the generator of the pinned recompiler did not end** (see
  the next bullet), the conversion was stopped, converted again without the received rows, and passed with native equal to the interpreter on both scenarios, 0 interpreted
  instructions and the same 16,335 functions as the clean conversion; no bogus row reached the player's paths or the record the conversion promotes (both counters 0).
  With `--max-root-offset 0x1D0000` (230 roots inside the code area of the cartridge, plus 2,000 RAM copies) the generator accepted every row: 68,500 functions instead of
  16,335, pass 3 with 0 interpreted instructions, native equal to the interpreter on both scenarios, `received_rows_used` 2,230, 0 qualified, both counters 0.
* **A finding about the pinned generator.** `gba_recompile.exe` can loop forever on a wrong ARM or Thumb root inside cartridge data (one root of the Minish Cap was enough;
  20 random roots hung it in 3 of 4 seeds; 2,000 random RAM copies alone are fine, 45 s). A poisoned record could therefore make a conversion hang. The converter now stops
  the generator after 300 seconds when rows were received (900 seconds otherwise), turns that into a conversion error, and the conversion is converted again without **all**
  received rows (qualified ones too: a row that hangs the generator is not a hint worth keeping). It is for the maintainer to report upstream.
* **Not done.** The site's limits for the `gba` machine are not regenerated or deployed, no record was uploaded, and the Linux witness is not run: sharing is code and tests
  in the tree, switched on only with the release and the maintainer's seeding. The local carry-over of paths at a pin bump is for later.

## The panel of twelve, the delivered file, the refusals and the routes (13 November 2026, 1.7.4)

Twelve cartridges chosen by risk (all four save chips, 4 to 16 MB, two clock cartridges, a software 3D game, a role-playing game of 16 MB) were converted from an **empty** scratch library on a
Windows PC, two conversions at a time (`batch --jobs 2`, the PC in use for other work: the times are not a benchmark), three passes asked and up to four settling ones,
with the tree of `spec/gba-174`. None was dropped. Each ran the two scenarios (`boot` 600 frames, `generic` 3,600 frames) natively and with the engine's interpreter alone;
on all twelve the final picture, the guest's cycle count, the memory hash and the CPU hash are equal.

| Cartridge | Size, save chip | Passes (3 asked, up to 4 settling) | Interpreted at pass 1, boot / generic | Interpreted at the end | Time (Windows, two conversions at once) |
|---|---|---|---|---|---|
| Golden Sun | 8 MB, flash64 | 5 | 2,581,873 / 72,238,564 | 0 / 0 | 21 min |
| Advance Wars (Rev 1) | 4 MB, flash64 | 2 | 2,044,548 / 60,656,952 | 0 / 0 | 27 min |
| The Minish Cap | 16 MB, eeprom | 3 | 1,636,808 / 19,684,139 | 0 / 0 | 19 min |
| Pokémon Emerald | 16 MB, flash128 | 2 | 106,192 / 3,782,142 | 0 / 0 | 44 min |
| Pokémon Ruby (Rev 2) | 16 MB, flash128 | 2 | 50,811 / 802,234 | 0 / 0 | 24 min |
| Metroid Fusion | 8 MB, sram | 1 | 0 / 0 | 0 / 0 | 14 min |
| Wario Land 4 | 8 MB, sram | 2 | 1,422 / 37,051 | 0 / 0 | 21 min |
| Sonic Advance 2 | 16 MB, flash64 | 2 | 97,066 / 4,432,092 | 0 / 0 | 24 min |
| Mario Kart Super Circuit | 4 MB, flash64 | 2 | 3,230 / 332,875 | 0 / 0 | 23 min |
| Mario & Luigi Superstar Saga | 16 MB, eeprom | 3 | 1,765,387 / 153,260,822 | 0 / 0 | 28 min |
| Mega Man Zero 3 | 8 MB, sram | 2 | 63,873 / 658,163 | 0 / 0 | 29 min |
| Crazy Taxi Catch a Ride | 8 MB, eeprom | 2 | 1,128,263 / 60,667,828 | 0 / 0 | 31 min |

Pokémon Ruby, Mario & Luigi, Mega Man Zero 3 and Crazy Taxi are new on this page; the other eight were converted before (the first-pass counts of Golden Sun, Advance Wars,
The Minish Cap and Pokémon Emerald are the ones of [the 12 November pass](#the-verdict-is-enforced-and-a-first-conversion-converges-faster-12-november-2026-173)).
This is native code coverage on two bounded scripted scenarios and the comparison with the engine's own interpreter, which is not an independent oracle; it says nothing about
gameplay or hardware fidelity.

### The delivered file: gates G5 and G8

The exported player writes one text line per frame when it is started with `RETRORECOMP_GBA_ROWS` (a test switch, never read in play): the frame, the hash of the picture,
the hash of the sound of that frame and whether a sample was not zero. After the player is built, the conversion runs it hidden on both scenarios, then runs the **compressed
copy it is going to deliver** the same way, and refuses to publish unless the compressed copy ends at the same frame with the same last picture and **the same row for every
frame** (`delivery_evidence`, the helper the other machines use; the copy is replayed on the unpacked build if the compression fails on the system, as for them). The rows are
also the liveness record of the report: how many different pictures and sound blocks, the last frame at which the picture changed, how many frames carried a sample. A
generic scenario whose picture never changes refuses the conversion.

On the twelve: the compressed copy matched on both scenarios of every cartridge (`packed_reference_match` true), the picture changed in every scenario (1,028 to 2,905 different pictures in the generic scenario of 3,600 frames, 203 to 454 in the boot scenario of 600), and 2,514 to 3,433 of the 3,600 frames of the generic scenario and 201 to 504 of the 600 frames of the boot scenario carried a
sample. Nobody listened to those samples: the rows show that the sound changes, not that it is right.

### Quick states and the files they are read from: gate G6

`tools/gba_fresh_process.py refusals` saves a state in one process, then damages the file in eight ways (emptied, cut in half, last byte missing, grown by 64 bytes, the first 16
bytes inverted, the cartridge identity inverted, noise of the same size, one byte inverted in the middle) and tries to load each in a fresh process, then tries to load none.
On the delivered Golden Sun, **seven of seven** forms that break the container are refused with a message (`quick state refused`), the game goes on as a run that never loaded a
state (same picture and frame count as the control, exit code 0), and the missing state creates no file. The eighth, one byte inverted in the middle of the memory, is
**accepted**: a state of memory has no checksum (the engine checks the magic, the version, the cartridge's SHA-1 and the structure of the sections), so a flipped byte of
memory is the game's own business; the check reports it and does not require it. The fresh-process state check itself (a state saved by one process and loaded by another gives the
same picture, a control that never loads gives another) passes on Golden Sun and Metroid Fusion with 0 interpreted instructions in every process.

### Saves: gate G7

The save of one process read back by a fresh one, with a control with no file, to the picture (`gba_fresh_process.py save`): Sonic Advance 2 (a Flash chip of 64 KB, the
language screen to the name), Pokémon Emerald (a **128 KB Flash** file written by the Start menu's SAVE, 131,072 bytes, 148 distinct values, and the title shows CONTINUE in
the second process) and The Minish Cap (the **8 KB EEPROM** written when the file is made, the file select shows it in the second process). The file is identical after the
second process. Not shown: the **SRAM** family. Mega Man Zero 3 was tried: on its route the game rewrites only the 192 header bytes of its 32 KB file and the title does not
change, because the route never reaches one of its save points; a route to a save point of an SRAM cartridge is still to be made. Saves from real hardware are not read.

### Routes into play: gate G9

One key script per panel cartridge, in `tools/gba_routes/` (numbers only: a frame and the buttons held), run on the delivered players:

| Route (`tools/gba_routes/`) | Frames | Instructions the interpreter ran on the route | Last picture, SHA-256 (first 16 digits) |
|---|---|---|---|
| Golden Sun: the title, the intro, the rainy Vale scene | 4,500 | 34 | `5582b59b2f2de25e` |
| Advance Wars: Nell's lesson on the first Field Training map | 10,000 | 0 | `0d5dcf35394cdac6` |
| The Minish Cap: a new file, the intro, Link's house | 10,000 | 13,910,846 | `56161e0fd97184d0` |
| Pokémon Emerald: the intro, the moving van, the player's house | 9,600 | 9,733,707 | `a8f5fb98324d3d1c` |
| Metroid Fusion: the opening story, Samus in the Navigation Room | 30,000 | 0 | `6ad2598f42b38b2c` |
| Wario Land 4: Entry Passage, Wario in play | 10,000 | 0 | `070e11ca1c241eb3` |
| Sonic Advance 2: the language screen to the save (the G7 route) | 1,500 | 0 | `962bbf2fd78b72e1` |
| Mario Kart Super Circuit: a race | 4,500 | 0 | `c329fb2241850849` |
| Pokémon Ruby: the same, on the clock cartridge | 9,400 | 8,373,178 | `b40b81a019ea61d7` |
| Mario & Luigi: the castle scenes, a Toad walks a house | 6,500 | 14,268 | `a85a84f3dee937a2` |
| Mega Man Zero 3: the intro and the briefing, Zero in a snowy stage | 20,000 | 59,017,036 | `49092f3d0637eac9` |
| Crazy Taxi: the taxi driving in the city | 4,200 | 0 | `acd8986b69a00232` |

Every route reaches play: the pictures at several frames were read one by one (a title, a menu or an opening story is not play; these are: the player's character in a house or
a village, a kart in a race, a taxi in the city, Zero in a stage, Samus under control). They are the **first minutes**, not a level won, a boss or a save point.
Seven routes run with 0 instructions interpreted or a few (34 for Golden Sun, 14,268 for Mario & Luigi). Four routes run **millions** of interpreted instructions (The Minish Cap, Pokémon
Emerald and Ruby, Mega Man Zero 3): they walk through code that the two scenarios of the conversion never reach, so the generated code does not contain it and the
interpreter runs it, correctly and counted. These routes are not part of the discovery: a route as a third scenario would learn that code, but its replay with the interpreter
alone, which the verdict needs, is too slow (a run of 3,000 frames of Pokémon Emerald with the engine's interpreter alone had not ended after 15 minutes, where the native player takes
one and a half), so it is a decision for the maintainer, not a thing done here. No route was compared with an interpreter run: a route says how deep the player goes and
that it still draws and plays sound, not that the picture is the right one.

The last-picture hashes above are those of the final players. The eight routes made on 13 November gave the same hashes on the players converted before the delivered file's evidence
was added (the rows are written beside the picture and change nothing of what is drawn).

### The Linux witness of the same tree (gate G13)

Golden Sun, Mario Kart Super Circuit and Pokémon Emerald were converted from an empty library on a Debian 13 PC (the tree of `spec/gba-174` as of the delivered file's evidence, one job
at a time, the PC shared with other conversions: 50, 36 and 72 minutes, the times of a busy machine) and their delivered players run hidden under SDL's dummy drivers with the same
key scripts:

| Cartridge | Conversion on Debian | Route | Last picture (first 16 digits) | Interpreted on the route |
|---|---|---|---|---|
| Golden Sun | five passes, 0 / 0 at the end, native = interpreter | the Vale scene, 4,500 frames | `5582b59b2f2de25e`, **equal to Windows** | 34, equal |
| Mario Kart Super Circuit | two passes, 0 / 0, native = interpreter | a race, 4,500 frames | `c329fb2241850849`, **equal** | 0, equal |
| Pokémon Emerald | two passes, 0 / 0, native = interpreter | the player's house, 9,600 frames | `a8f5fb98324d3d1c`, **equal** | 9,733,707, equal |

The functions generated per pass and the interpreted counts per pass of Golden Sun equal the Windows ones (13,600, 15,695, 15,768, 15,771 and 15,776 functions; one instruction apart in
the first pass of the generic scenario, 72,238,563 against 72,238,564, an intermediate count that changes nothing). The compressed copy matched the player as built on both scenarios on Linux too (`packed_reference_match` true on the three). On the Golden Sun player, the fresh-process state check
passes (same picture as the process that saved, the control differs, both pictures equal the Windows ones) and so does the refusals check (seven of seven forms refused, a missing state
creates nothing, the byte flipped in the middle accepted, as on Windows).


### The "NOT_STATIC" label on Linux

On the Debian 13 PC the passes of Golden Sun and of Mario Kart printed `NOT_STATIC` even with 0 interpreted instructions, where the Windows passes printed `FULLY_STATIC` (Pokémon Emerald's printed
`FULLY_STATIC` on Linux too). The engine calls a run fully static only when no address was bridged **and nothing was healed**; on Linux the engine reported 1 heal in the boot scenario and 12 in the
generic one of Golden Sun (the 12 addresses the second pass had learned) and 1 in Mario Kart's, on Windows 0. It is a label and a count: the interpreted instructions, the pictures and the verdicts are equal on both systems. The log and the rows
of the report now carry the number of heals (`healed_native`), so that the label can be read with its reason. The cause (a warm miss cache read back on Linux, as the engine's comment says,
or something else) was not looked for.

### What this does not show

Gameplay beyond the first minutes of twelve cartridges, the SRAM family's save, an independent oracle of the CPU (the interpreter is the engine's own), hardware fidelity (no
external emulator was compared), the sound itself (counts and hashes, not listening) and physical latency (not measured; `tools/gba_frame_cost.py` is ready and waits for a quiet PC).


## What exists today

| Piece | File |
| --- | --- |
| Profile (experimental, listed with its files) | `retrorecomp/systems/gba.py` |
| Cartridge reader: header, checksum, hash, save chip by library identification strings, BIOS hash | `retrorecomp/gba.py` |
| Engine pin, the conversion loop (observe, learn paths, rebuild), the player export, the delivered file's evidence, the report | `retrorecomp/gba_conversion.py` |
| The player: the project of the executable, its resources, the kit | `retrorecomp/gba_player.py`, `native/gba_machine.cpp`, `native/gba_machine.h`, `native/gba_driver.h`, `native/hostkit/adapters/rrhk_gba.c` |
| Checkout of the pinned engine and the staged, patched copy | `retrorecomp/gba_engine.py`, `retrorecomp/gba_patches.py` |
| Misses to roots and RAM routines, the engine's configuration | `retrorecomp/gba_analysis.py` |
| Shared paths (the record, the limits, the received rows' use) | `retrorecomp/gba_knowledge.py`, `tests/test_gba_knowledge.py`, `tools/gba_bogus_rows_audit.py` |
| Fresh-process checks (state, refusals, save, route), twelve key-script routes and the save scripts, cost of a frame | `tools/gba_fresh_process.py`, `tools/gba_routes/`, `tools/gba_frame_cost.py` |
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
