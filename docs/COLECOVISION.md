# ColecoVision

Profile `coleco`: the ColecoVision, **experimental, developer only, in development**. This is stages 1 to 3 of the machine
([NEW_MACHINE.md](NEW_MACHINE.md), the converter's side): the converter recognises a ColecoVision cartridge file, reads it, translates it together
with your own BIOS, checks the translation against the reference interpreter and **delivers a game executable** (the player and the host kit
around the translated cartridge and BIOS). It is for developers: no player is offered it, no game has been played by a person, and nothing on this
page says that a game plays well, that the hardware is reproduced faithfully or how long input takes to reach the screen. Those are five
separate measures (native code, CPU fidelity, hardware fidelity, gameplay validation, physical latency); for this machine only the first, and the
agreement with the reference interpreter, are measured, per conversion, and only on the routes played; the delivered file is replayed headless,
not played.

## 1. What is converted, and what is not

The scope below is the one the machine is built for.

| In scope | Out of scope (with the reason) |
| --- | --- |
| ColecoVision (NTSC) cartridges of 4 KiB to 32 KiB, plain ROM, read from a `.col`, from a `.bin` or `.rom` that you choose as ColecoVision or keep in a folder named `colecovision`, `coleco`, `coleco vision` or `coleco_vision` and that begins with a header word, or from a ZIP holding one | **Super Action Controller, Roller Controller (trackball) and the driving module**: they need a mouse or an analog input. A game that needs one starts with the standard controller, and the report will say so |
| Two standard controllers: the stick, the two fire buttons and the twelve-key keypad (0-9, `*`, `#`) | **Super Game Module** (24 KiB of RAM and an AY-3-8910): nothing in the library studied needs it; a follow-up on request |
| Your own BIOS (8 KiB), never shipped | **MegaCart, Activision EEPROM, X-in-1, Super Game Cartridge**: homebrew boards; a file larger than 32 KiB is refused by the reader |
| | **ADAM** (tape and disk computer): another machine |

The reader (`retrorecomp/coleco_rom.py`) accepts a whole number of kilobytes from 4 KiB to 32 KiB, alone or as the only cartridge of a ZIP. A
ColecoVision dump has no copier header, so none is removed. Its first two bytes are a header word the BIOS reads, `55 AA` or `AA 55` (the BIOS
tells the two orders apart; the reader reports which one a file has). A `.col` is the machine's whatever its bytes; a `.bin`, a `.rom` or a ZIP
member must begin with a header word, and the folder or your choice in the menu decides. The file is read in place and never changed;
Retro-Recomp publishes no game.

## 2. The BIOS

The ColecoVision cannot start a game without its 8 KiB operating system (OS7, at 0000h-1FFFh): it starts the machine, shows the title screen,
reads the cartridge's header word and calls the game, and the games call its fixed entry points (sound, VRAM and sprite utilities, the NMI vector at
0066h). No free replacement exists, so, as for the MSX's own BIOS and unlike C-BIOS, **you give your own copy** in Options, ColecoVision. It is never
shipped, never fetched and never kept in the repository.

It is accepted by content (`retrorecomp/coleco_bios.py`): 8,192 bytes with the SHA-256 of the image the common sets carry (MAME's `coleco`: CRC-32
`3aa93ef3`, SHA-1 `45bedc4cbdeac66c7df59e9e599195c778d86a92`; these are numbers about the file). Any other file is refused with a sentence. Options'
« Find firmware in a folder… » looks for it by the same digest (`retrorecomp/firmware_search.py`). The BIOS's digest is part of a request's identity.

The converted game holds the BIOS translated beside the cartridge, and the BIOS's bytes as a resource of the game (the machine reads its data too), so
the game file is for its owner only, as the MSX's own-BIOS games are. The work folder of a conversion is named after the cartridge and the BIOS
(`.build/coleco/<sha12>-<BIOS8>`), and the BIOS's digest is part of the game's quick-state binding.

## 3. How it works

1. **Native code.** The cartridge and the BIOS are translated ahead of time to C by the shared banked Z80 chain (`retrorecomp/z80_chain.py`) on
   the machine's own description, `COLECO_MACHINE` in `retrorecomp/systems/coleco.py`: eight 8 KiB regions (the BIOS in the first, nothing in
   the next two, the console's RAM, then the cartridge window mirrored by its size), one wait state on every M1 cycle (as MAME 0.289's timing has it: the writes of the BIOS's start land at the same cycles once it is counted), and the TMS9928A's frame
   interrupt wired to the Z80's **/NMI** (an edge: taken when the frame flag rises with the interrupt enabled, or when it is enabled with the
   flag already up; the chain learned that pin for this machine and the SG-1000). /INT is not wired. What the translation does not cover runs on
   the reference Z80 interpreter and is counted, per CPU; code a game runs from RAM is learned and translated with byte guards on the next pass.
2. **The machine.** The video chip is the shared module `native/tms9918/` of the MSX family and the SG-1000; the sound chip is the shared
   `native/sn76489/` of the SG-1000; the 1 KiB of RAM (6000h, mirrored through 7FFFh), the expansion port (2000h-5FFFh: nothing, reads FFh), the
   controllers' ports and the keypad are the machine's own C (`native/coleco_machine/coleco_machine.c`, header comment: the map and the ports). A write
   to the SN76489A holds the CPU for 28 more cycles (the chip's /READY line is wired to the Z80's /WAIT: a value measured against MAME, below). No
   emulator core is inside the executable.
3. **The controllers.** Each player's controller is one pad word of the host kit: the stick (bits 0-3), the two fire buttons (4-5) and the keypad's
   four lines (6-9): a key is the code of the lines it pulls, so two keys held merge as on the real keypad; bit 10 is reserved (the console has no
   Pause button) and bit 11 is the host's flag « the on-screen keypad is open », which makes the machine ignore the stick and the fire buttons of
   that pad. A port reads the stick and the left fire button in joystick mode, the key's code and the right fire button in keypad mode (the
   console's writes to 80h-9Fh and C0h-DFh choose), every line active low. Nothing else reaches the game, so rollback and a multiplayer session
   will need nothing more. The twelve keys are ordinary action rows (bindable in F2), and a gamepad player's Y opens the host kit's on-screen
   keypad (`native/hostkit/adapters/rrhk_keypad.inc`): the D-pad moves, A presses a key, B or Y closes it, and the game keeps running.
4. **The routes.** A conversion plays an `attract` route (no input), a `play` route and, at the extended and thorough scan levels, long routes
   (`retrorecomp/coleco_routes.py`). The BIOS shows its title screen for about twelve seconds and then most games wait at a game-select screen for
   a fire button or a digit, so the first press comes late; how `play` starts (fire button 1, key 1, or key 1 then fire button 1 in turn, pressed
   one to three times) is chosen on the reference interpreter per cartridge, as the MSX's start is.

### How it converts (developer only)

`retrorecomp/coleco_conversion.py` runs in `.build/coleco/<sha12>-<BIOS8>`:

1. the cartridge and the BIOS are read and refused with a sentence when they are not what the machine holds (size, header word of a `.bin`, the BIOS's
   digest), before anything is written;
2. **the start of the `play` route** is chosen on the reference, then the cartridge and the BIOS are translated and the native check is built beside
   the reference runner; every route is run on the check, and the code the interpreter ran from RAM is learned (at most three passes);
3. **the comparison**: the native check and the reference run every route; every compared field (CPU registers, cycles, the /NMI count, RAM, VRAM, the picture of
   every frame, the VDP registers, the sound and the PSG, the watched bytes) and every frame's row must be equal, or the conversion is **refused**; a
   route whose picture never changes is refused too;
4. **the game** is built (the player, the machine, the host kit, SDL2, the cartridge as resource 103, the BIOS as 104, the notices as 203), delivered
   compressed, replayed headless on every route and compared again with the reference and the native check, and its quick states are checked in a
   fresh process (F8 and F9, damaged and foreign states refused);
5. the report (`conversion-report.json`, schema 2, marker `coleco_checks`) states what was measured and what was not.

What exists today: the profile, the reader, the BIOS check, the machine's description, the machine's C (`native/coleco_machine`, with the shared
`native/tms9918` and `native/sn76489`), the conversion loop, the game itself (`coleco_player.c`, its adapter `rrhk_coleco.inc` and its quick states
`coleco_state_file.inc`), the registries and this page.

### Multiplayer

A match is two seats in rollback (docs/MULTIPLAYER.md): the host kit saves one in-process snapshot a frame (the state's body without the picture,
`cv_snap_*` in `coleco_state_file.inc`) and compares a digest of it. The pad word carries the stick, the fire buttons and the keypad's lines (and the
on-screen keypad's flag), so a key pressed on any seat reaches the game on every PC; the pop-up opens on the local seat only. Both PCs need the same
BIOS: the report has a top-level `bios` record the lobby compares, and the boot digest would refuse a different one anyway. There is no cartridge save
to share. `--snap-probe AT:N` of the delivered game (headless) saves a snapshot, runs N frames, loads it and runs the same frames again: every digest
and picture is compared (`tools/coleco_player_selftest.py`, proof (d)).

## 4. Licences

The converted game will compile in the banked Z80 chain's generator and core, the corrected reference interpreter (`licenses/smsggrecomp.md`,
`licenses/z80-recomp-core.md`, `licenses/superzazu-z80.md`), and the shared MIT modules; no GPL component. The BIOS is yours, not ours.

## 5. Evidence

What is checked, and what each check covers (the five measures stay apart):

- **ROM-free** (`tests/test_coleco_*.py`, in the public suite; `tests/test_coleco_conversion.py` end to end with `RR_COLECO_END_TO_END=1`): the
  profile, the reader, the BIOS check, the routes and the build files, and an **authored** cartridge with an **authored** stand-in BIOS
  (`tools/coleco_authored.py`: no byte of a game or of a console's BIOS) that converts, equals the reference interpreter on every route, runs no
  interpreter after learning, is delivered and replayed, and reads each controller as the machine's own ports say (the stick, the fire buttons and
  the keypad's lines, both controllers, both modes). This is agreement between the machine and its own reference, not evidence about a console.
- **The delivered game on the host kit** (`tools/coleco_player_selftest.py`, needs a C toolchain): the game's headless replay equals the native
  check, quick states carry a fresh process, and a windowed run (offscreen video, dummy audio) presents pictures and answers the keyboard.
- **The keypad on a gamepad** (`tools/hostkit_keypad_selftest.py`): the host kit's on-screen keypad, around a fake machine.
- **MAME 0.289 as a private oracle** (22 November 2026, run apart from this repository, on the owner's BIOS and cartridges; nothing of MAME is in it):
  - *the controllers' ports*, with every input pressed in turn and read in both modes on both controllers: the twelve keys' codes, the four
    directions and the two fire buttons agree line by line, with two corrections it gave: `*` and `#` were swapped, and the unused bit 7 reads 0. A
    ROM-free end-to-end check keeps those bytes (`tests/test_coleco_conversion.py`, `MAME_KEYPAD`);
  - *the Z80's timing*: twenty-six groups of instructions (the prefixed ones, the block, I/O and branch ones) take exactly the cycles MAME gives them
    on an authored program with an authored BIOS, once the console's two wait states are in: **one on every M1 cycle**, and **28 more cycles for each
    write to the sound chip**; both were found because the real BIOS's writes landed late in MAME, and each is now in the machine and in the chain's
    description of it;
  - *the writes to the console's RAM*: from power on, the real BIOS and a retail cartridge's title and game-select screens make the same
    318,494 writes, in the same order and at the same cycles (within the width of one instruction), as MAME over the first 1000 frames, the frame
    interrupt included; with a key pressed at the game-select screen the two stay the same until about twenty frames after it, where they part: not
    explained yet (a candidate is how a held key is sampled against the frame interrupt), and not claimed either way.

**Not measured**: hardware fidelity (MAME is an emulator, not a console: where this machine agrees with it, both may differ from a real ColecoVision;
nothing was measured on one), CPU fidelity beyond the independent vectors (they pass: 51,328 of 51,328 through this machine's own generator build with one wait state per M1 cycle, `tools/banked_vector_selftest.py --machine coleco`, 22 November 2026; an emulator's vectors on a flat test bus, not hardware captures), gameplay validation, physical latency. The
qualification gates ([QUALIFICATION.md](QUALIFICATION.md)) are `?` for this machine until a panel has been converted and read.

## 6. G14 checklist for the owner's play test (22 November 2026)

Three delivered executables in `Export/Games/ColecoVision` (built from main of 22 November 2026 with the owner's own BIOS, empty scratch library, portable
toolchain, online covers on); about three minutes each. The owner fills the row of the owner-acceptance table in his own words and date; nothing here
sets G14 or the status. The console has **no Pause button**: a game that pauses does it with its own keys.

Controls: arrows move; **D** and **S** are the two fire buttons; the keypad is the digit keys (top row or numeric pad), `*` on **[** and `#` on **]**;
on a gamepad the D-pad moves, A/B fire, **Y opens the on-screen keypad** (D-pad to move, A to press, B or Y closes it; the game keeps running).

| Game | Try | Should happen |
|---|---|---|
| Donkey Kong (USA, Europe) | At the game-select screen press **1** (keypad) or a fire button, then fire again; walk Mario to the first ladder and climb, jump a barrel with **D**; **F8**, play on, **F9**. | Title, then the girders with barrels and the music; jumps over barrels score and ring; the state comes back where it was saved. |
| Bump 'N' Jump (USA, Europe) | **1** at the select screen, then fire; steer with left/right, jump with **D**; try the gamepad keypad (**Y**) once to pick the game if you have one. | The road scrolls, cars and the jump bonus; engine and jump sounds. The play route reaches the game only through the keypad start, as it should. |
| Pitfall II - Lost Caverns (USA) | A fire button at the title; run, jump, climb; **F8**/**F9**. | The jungle and cavern screens with their music; Harry runs and jumps; the picture changes on a long walk. |

Also, once: **F2** shows the keys and the keypad's row, **F6** autofire never presses a keypad key, player 2 on I J K L (U and O fire), the sound is clean for a
minute.

**Evidence beside it** (conversion reports; the native run equals the corrected reference interpreter, with one wait state on every M1 cycle and the VDP
interrupt on /NMI, on every frame of the attract and of a 3,600-frame pad route): **0 interpreted steps on all six runs**; Donkey Kong 22.3 million native
steps on its play route (3,540 guarded steps), Bump 'N' Jump 24.9 million, Pitfall II 22.8 million (1,497 guarded steps); audible frames measured on every play route (nobody has listened yet);
the BIOS is the owner's own, checked by SHA-256 and recorded in the report; the offscreen frames at 1,500 and 3,000 frames show the games in play.
Against MAME 0.289 as a private oracle: the controllers' ports agree line by line, the Z80 timing groups agree, and the console RAM writes of the BIOS, the
title and the game-select screen are identical over 1,000 frames. **G10 is `Y`** (51,328 independent Z80 vectors); G1 to G9 and G11 to G16 stay `?`
until a panel is read.

**Not claimed**: hardware fidelity (MAME is an emulator; nothing was measured on a console; keys `0 9 * #` follow MAME only), the unexplained parting from
MAME about twenty frames after a key press at the game-select screen, gameplay validation (three games, played by routes, not through), physical
latency (never measured). Not converted: the Super Game Module, Adam and the driving or roller controllers.
