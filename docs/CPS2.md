# Capcom CPS-2

**Experimental** machine, in development (5 November 2026): the Capcom CPS-2 arcade board (1993 to 2004), a 16 MHz 68000 with an
encrypted program, the CPS graphics chips with an object chip of its own, and the QSound sound board of the
[CPS-1.5](CPS1.md#cps-15-qsound-boards). This page says what exists and what has been measured. The profile is not
registered in the converter yet: the board runs from a development build, not from the converter's window.

Sources and licences of the board model: [cps1-machine.md](../licenses/cps1-machine.md) (MAME's CPS-2 driver and decryption,
BSD-3-Clause). Until the conversion exists, the dated measurements are on this page.

## At a glance

| | |
|---|---|
| Status | Experimental, in development: the board and its evidence exist as a development build; no profile, no conversion, no export |
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

## Evidence so far (5 November 2026, Windows, MAME 0.289 as the reference)

All of it is agreement with MAME's model, never with the board. The five measures stay apart: native code, CPU fidelity, hardware
fidelity, gameplay validation and physical latency; the last three are not validated for this board.

| What | Result |
|---|---|
| Decryption against MAME's `opcodes` and `program` spaces (4 MiB each) | equal on 34 of the 37 parent sets tested; `1944`, `19xx` and `progear` are in the owner's folder under another revision of their files (not tested), `avsp` holds older 2 MiB graphics dumps (not identified) |
| `ssf2`, 2,400 frames from power on | 0 interpreted 68000 and 0 interpreted Z80 instructions (native 42 million and 24 million) |
| Bus accesses (`0x400000` to `0x8fffff`) of the first 80 frames | the same 61,657 accesses, values included, as MAME |
| `ssf2` attract, 90 pictures from frame 100 to 9,000 | identical to MAME's, pixel for pixel |
| `ssf2` credited play route, 3,600 frames | 360 pictures sampled, 360 identical to MAME's; QSound sound: median level difference 0.008 dB, averaged spectrum cosine 0.9997, aligned waveform correlation 0.97 (MAME runs the same high-level model) |
| Quick state | saved at frame 900 and loaded in a fresh process: the same CPU and RAM hashes at frame 1,500 |
| Saves | the windowed host writes a 224-byte file at the first run and leaves it unchanged at the second |
| Non-regression | a CPS-1 set (`1941`): generated code and checks identical to the previous tree; a CPS-1.5 set (`wof`): generated steps identical, 3,600-frame traces identical, 0 interpreted |

## Known limits

* No conversion, no profile, no panel yet; the evidence above is `ssf2` (and the panel of the log once it exists).
* Hardware fidelity: the speed (0.7375), MAME's one-frame lag of the sprites and its defects (for example the 32x32 tiles of
  Marvel vs. Capcom at super-move flashes) are in the reference; a picture equal to MAME's can still differ from the board's.
* The DSP16 of the QSound chip is not run; the sound is MAME's high-level model.
* Spinner and paddle games (`ecofghtr`, `pzloop2`, ten sets) are not in the first scope; nor the network adapter or the dead boards.
* The decryption watchdog (the battery that keeps the key) is not modelled, as in MAME.
* Physical latency is not measured.

## History

* 5 November 2026: study (phase 1) and first development build; the owner chose a separate `cps2` profile, the keys from the
  player's own romset only, the 236 standard sets, MAME's speed as the working model and exports of 20 to 45 MiB.
