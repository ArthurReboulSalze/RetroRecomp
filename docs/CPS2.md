# Capcom CPS-2

**Supported** machine (supported since 1.7.0, once the owner's decision is recorded in [QUALIFICATION.md](QUALIFICATION.md#owner-acceptance)); it opened to players as an experimental one in 1.6.9 (« OK pour CPS2 en expérimental sur la 1.6.9 », 5 November 2026):
the Capcom CPS-2 arcade board (1993 to 2004), a 16 MHz 68000 with an encrypted program, the CPS graphics chips with an object chip of its own,
and the QSound sound board of the [CPS-1.5](CPS1.md#cps-15-qsound-boards). This page says what exists and what has been measured. The profile
`cps2` reuses the CPS-1 pipeline and shares its paths like the CPS-1 does: in the experimental tier of the shared base, with no path qualified
yet (the games observe none).

Sources and licences of the board model, and where the keys come from: [cps1-machine.md](../licenses/cps1-machine.md) (MAME's CPS-2 driver
and decryption, BSD-3-Clause; the keys are files of your own romset, never supplied). The dated measurements are on this page.

## At a glance

| | |
|---|---|
| Status | Supported (supported since 1.7.0, once the owner's decision is recorded in [QUALIFICATION.md](QUALIFICATION.md#owner-acceptance)): the panel of 17 sets converts at the extended level on Windows and on Debian with the same hashes; the evidence is below, and what is not measured is named in the limits |
| Scope of the first release | The standard A-board with the player's own key: 258 sets of MAME's CPS-2 driver (Capcom and licensed games); 236 of them are complete in the owner's FBNeo romsets by file names. Out: bootlegs (47), dead boards (2), network adapter (7), spinner and paddle games (10, later), `gigaman2` |
| Keys | A set's 20-byte decryption key is a file of the player's own romset (`ssf2.key`). The converter reads it from the archive; it never supplies, embeds or downloads one, and refuses a romset that has none |
| Sound | The QSound chip, with the player's own `dl-1425.bin` (the same option as the CPS-1.5); the DSP16 is not executed: a high-level model, as MAME's by default |
| Size | Graphics ROMs of 12 to 32 MiB and QSound samples of 4 to 8 MiB: an export is expected at 20 to 45 MiB |

### What the board does that the CPS-1 does not

* **The 68000 fetches its instructions through a decryption.** Two Feistel networks keyed by the game's 64-bit key and the low 16
  bits of the address decrypt every instruction word, extension word, immediate and PC-relative operand; data reads see the stored
  words. The converter keeps both images (`maincpu.bin`, `maincpu-op.bin`) and translates the decrypted one
  (`retrorecomp/cps2_crypt.py`, 7 to 15 seconds for a 4 MiB program in plain Python).
* **An object chip.** Two object RAM banks, latched at VBLANK; sprites carry their own 3-bit priority against the tile layers
  and are drawn from the last entry down, with block sprites and offset registers.
* **Raster interrupts.** The CPS-B-21 counters raise IPL2 on a chosen line and position; games use them for effects (the stages of
  `ssf2`, the lava of `msh`). The picture is drawn up to the interrupt's line, then the game's handler changes the registers.
* **A 16-bit 93C46 EEPROM**, set up by the board's output port; no switches (the DIP bank exists only on development boards).
* **16 MHz, run as MAME runs it**: slowed by 0.7375 (11.8 MHz) for the waitstates MAME does not emulate. The speed of the board is
  therefore MAME's working model, not a measurement of the hardware.

## Structure of the machine

| Part | Model |
|---|---|
| Main CPU | MC68000, 16 MHz x 0.7375; the translated code of the decrypted image, the reference interpreter (Musashi) for the rest, with separate immediate and PC-relative reads on this board |
| Sound CPU | Z80 at 8 MHz, plain (no set uses the encrypted sound program), 250 Hz interrupt, shared RAM at `0x618000`, held in reset by bit 3 of the EEPROM port |
| Graphics | CPS-A / CPS-B-21 as the CPS-1 (tile layers 8x8, 16x16, 32x32, row scroll, palette), object RAM `0x700000` / `0x708000`, output registers `0x400000`; ROMs stored shuffled in banks of 2 MiB |
| Sound | QSound ([CPS-1.5](CPS1.md#cps-15-qsound-boards)): stereo, 24,038 Hz |
| Storage | 93C46, 64 words, `datas/saves/` file as the CPS-1.5 |

## Evidence (5 and 6 November 2026, Windows and Debian, MAME 0.289 as the reference)

All of it is agreement with MAME's model, never with the board. The five measures stay apart: native code, CPU fidelity, hardware
fidelity, gameplay validation and physical latency; the last three are not validated for this board.

| What | Result |
|---|---|
| Decryption against MAME's `opcodes` and `program` spaces (4 MiB each) | equal on the 35 archives of the owner's folder that are in the scope (the sets they hold are the parents, or for `1944`, `19xx` and `progear` the clones `1944j`, `19xxu` and `progearu`); 3 archives of sets with inputs of their own (`choko`, `cybots`, `qndream`) are outside the scope |
| `ssf2`, 2,400 frames from power on | 0 interpreted 68000 and 0 interpreted Z80 instructions (native 42 million and 24 million) |
| Bus accesses (`0x400000` to `0x8fffff`) of the first 80 frames | the same 61,657 accesses, values included, as MAME |
| `ssf2` attract, 90 pictures from frame 100 to 9,000 | identical to MAME's, pixel for pixel |
| `ssf2` credited play route, 3,600 frames | 360 pictures sampled, 360 identical to MAME's; QSound sound: median level difference 0.008 dB, averaged spectrum cosine 0.9997, aligned waveform correlation 0.97 (MAME runs the same high-level model) |
| Panel of eight sets, the same credited play route and the same sampling (MAME 0.289) | `ssf2`, `ddtod`, `dimahoo`, `xmvsf`, `mvsc`, `msh`: 360 of 360 pictures identical; `sfa3`: 359 of 360 (one picture at frame 100); `mmatrix`: 92 of 360, see the limits. Sound on all eight: median level difference 0.004 to 0.026 dB, averaged spectrum cosine 0.9968 to 0.9997; the waveform agrees at 0.98 to 0.99 (median of the best-lag correlation per 0.1 s window), with a lag that drifts by under one sample per second: MAME runs the chip at 24,038 Hz and the game at 24,038.46 Hz |
| Bus accesses (`0x400000` to `0x92ffff`: object output, shared RAM, object RAM, CPS registers, inputs, EEPROM port, graphics RAM) of the whole route | `sfa3` (2,000 frames) and `msh` (2,200 frames): the same accesses, values included, as MAME; `mmatrix`: the same for the first 1,340 frames |
| Raster interrupt (`ssf2`, attract from frame 6,818, counter 1 reloaded at 148) | frames 6,800 to 7,000 compared one by one with MAME: identical, 152 of the 183 raster frames at the same frame number and the rest at the nearest of three neighbours |
| Quick state | saved at frame 900 and loaded in a fresh process: the same CPU and RAM hashes at frame 1,500 |
| Saves | the windowed host writes a 224-byte file at the first run and leaves it unchanged at the second |
| Conversion of the first eight sets through the converter (5 November 2026, tree of the branch `spec/cps2-170`, standard scan level, `--no-online-cover`) | The eight sets of the panel convert: each with a fresh reference run of every instruction, 0 interpreted 68000 and 0 interpreted Z80 instructions on the attract and credited play routes, the compressed copy equal to the reference, a quick state saved and continued in a fresh process, a truncated state refused; 100 to 145 seconds a set on one Windows PC, executables of about 20 MiB. The report says `experimental` and keeps hardware fidelity, gameplay and latency as not validated |
| **Final pass** (6 November 2026, the exit tree, extended scan level: the attract route, the credited play route and one pseudo-random route of 18,000 frames) | 17 sets converted on Windows: `1944j`, `19xxu`, `armwar`, `avsp`, `ddtod`, `dimahoo`, `megaman2`, `mmatrix`, `mpang`, `msh`, `mvsc`, `progearu`, `sfa3`, `sfz2al`, `ssf2`, `xmcota`, `xmvsf`. 0 interpreted 68000 and 0 interpreted Z80 instruction on every route, the compressed copy equal to the fresh reference, a quick state continued in a fresh process and a truncated state refused, `completed` and a supported board in every report; 205 to 404 seconds a set, two at a time. The sets are the owner's panel of eight, five drawn at random (seed 170: `xmcota`, `mpang`, `sfz2al`, `megaman2`, `armwar`) and the four whose files differ from the catalogue's (`1944`, `19xx`, `progear`, `avsp`) |
| Linux (the same pass on the Debian 13 PC) | the same 17 sets converted there: the CPU, RAM, picture and sound hashes of all 51 routes are equal to Windows' (51 of 51) |
| Thorough scan level (two more pseudo-random routes) | `ddtod`, `mvsc`, `ssf2`: 0 interpreted instructions on every route |
| The nine sets beyond the panel against MAME 0.289 (the credited play route, 3,600 frames, a picture every 10 frames and the sound) | 8 of 9 sets have 360 of 360 pictures identical (`1944j`, `19xxu`, `armwar`, `megaman2`, `mpang`, `progearu`, `sfz2al`, `xmcota`); `avsp` 359 of 360 (the first difference at frame 100). The sound: median level difference 0.003 to 0.057 dB, averaged spectrum cosine 0.9932 to 0.9997 |
| `ddsom`, the number of players | on a blank EEPROM the game starts with two players; with the service switch on, the test menu's *Chute type* set to 4 players and *Save and exit*, a relaunch without the switch shows four *Press start* places (`.build/cps2-exit/evidence/g7-ddsom-after-restart.png`); the setting is kept in the save file |
| The 68000 and Z80 translated steps through the CPS-2 variant of the generator (`tools/cps1_vector_selftest.py --cps2`: the PC-relative operands are read through the instruction-fetch hooks) | the same independent vectors as the CPS-1's agree: 834 of 834, 864 of 864, 2,169 of 2,171 (the two others are the authored vectors with the trace bit set, which these builds do not run), and the groups fixture with the same recorded deviations (native 2,873 of 2,895, reference 2,889) |
| Shared paths | the CPS-2 shares like the CPS-1 (`cps2_knowledge`, the board as a keyword of `cps1_knowledge`); none of the 17 sets observes a path, so nothing is qualified yet |
| Non-regression (earlier tree, before the profile) | a CPS-1 set (`1941`): generated code and checks identical to the previous tree; a CPS-1.5 set (`wof`): generated steps identical, 3,600-frame traces identical, 0 interpreted |

## Players, switches and the test menu

The board has no DIP switches: a game's settings (number of players, coinage, difficulty, language) are kept in its EEPROM and changed in the
game's own test menu, which the board's service switch opens. The F2 DIP page of an exported game therefore has one setting, **Service
switch (the game's test menu)**: set it to *On*, restart with Shift+F1, and the test menu appears; move with player 1's joystick and
button 1, change a setting with Left and Right, choose *Save and exit*, then set the switch back to *Off* and restart. The setting is kept
per game like the CPS-1's switches; the game's own settings are kept in the save file. Read on 5 November 2026 with a blank EEPROM (a game that
was never started), by playing four credited players from the title screen:

| Set | Players on a blank EEPROM | Where the number is set |
|---|---|---|
| `ddtod` | 4 | |
| `armwar` | 3 | |
| `ddsom` | 2 (a third and fourth player do nothing) | test menu, 7 Configuration, 1 System, *Chute type* (2, 3 or 4 players) |
| `batcir` | 2 | the test menu, not read further |
| `avsp` | not read (the set converts since 1.7.0: FBNeo's four 2 MiB graphics files are read as the catalogue's 1 MiB ROMs) | `Chute type` of the test menu to read |

## Known limits

* The first eight sets' pictures and sound were compared with MAME on a development build driven with MAME's own route; the delivered files of the final pass were compared for the nine others only.
* `mmatrix`: the title animation of the picture is one frame ahead of MAME's from frame 775 to 783 (the same pictures, shifted by one frame), although
  every bus access of the game, graphics RAM included, is equal to MAME's; the cause is not found. Every other frame of the route is equal.
* The boot self-test of `sfa3` and `avsp` ("RAM OK") fades out one step later in ours than in MAME's at frame 100 (one picture of 360): the bus
  accesses of `sfa3`, graphics RAM included, are identical for 150 frames, and no colouring line tried (0 to 255) changes it. Named, not explained.
* Timing inside an instruction: the 68000 here reads and writes at the start of an instruction, MAME's clock a few bus cycles later (about 5 pixels
  for a read, 10 for a write). The raster counters are read with 8 cycles added to compensate; a game that reads a counter near the end of a line can
  still see the next line's value earlier or later than MAME does.
* Hardware fidelity: the speed (0.7375), MAME's one-frame lag of the sprites and its defects (for example the 32x32 tiles of
  Marvel vs. Capcom at super-move flashes) are in the reference; a picture equal to MAME's can still differ from the board's.
* The DSP16 of the QSound chip is not run; the sound is MAME's high-level model.
* Spinner and paddle games (`ecofghtr`, `pzloop2`, ten sets) are not in the first scope; nor the network adapter or the dead boards.
* The decryption watchdog (the battery that keeps the key) is not modelled, as in MAME.
* Physical latency is not measured.

## History

* 5 November 2026: study (phase 1) and first development build; the owner chose a separate `cps2` profile, the keys from the
  player's own romset only, the 236 standard sets, MAME's speed as the working model and exports of 20 to 45 MiB.
* 6 November 2026: the exit from the experimental status prepared on the branch `spec/cps2-exit-170`: the paths shared like the CPS-1's, the four sets
  whose files differ read, the decryption compared with MAME on 35 archives, the vectors through the CPS-2 variant, the test-menu setting kept across a
  restart, and one pass of 17 sets at the extended scan level on Windows and on Debian with equal hashes. The owner's decision is recorded in
  [QUALIFICATION.md](QUALIFICATION.md#owner-acceptance).
