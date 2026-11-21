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
   the next two, the console's RAM, then the cartridge window mirrored by its size), no wait state on the M1 cycle, and the TMS9928A's frame
   interrupt wired to the Z80's **/NMI** (an edge: taken when the frame flag rises with the interrupt enabled, or when it is enabled with the
   flag already up; the chain learned that pin for this machine and the SG-1000). /INT is not wired. What the translation does not cover runs on
   the reference Z80 interpreter and is counted, per CPU; code a game runs from RAM is learned and translated with byte guards on the next pass.
2. **The machine.** The video chip is the shared module `native/tms9918/` of the MSX family and the SG-1000; the sound chip is the shared
   `native/sn76489/` of the SG-1000; the 1 KiB of RAM (6000h, mirrored through 7FFFh), the expansion port (2000h-5FFFh: nothing, reads FFh), the
   controllers' ports and the keypad are the machine's own C (`native/coleco_machine/coleco_machine.c`, header comment: the map and the ports). No
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
- **A first look at the real BIOS**, on the owner's copy: the BIOS boots to its title and its game-select screen on the machine, and at the game-select
  screen the keys 1 to 4 and 5 to 8 behave as the two groups the screen offers (one player, two players) while 0, 9, `*` and `#` do nothing, which is
  what the key codes of the machine's keypad predict for 1 to 8. The codes of 0, 9, `*` and `#` themselves are **not** checked by that look.

**Not measured**: CPU fidelity against an independent oracle, hardware fidelity (the port decoding, the keypad codes of 0, 9, `*` and `#`, the VDP's
interrupt timing against a reference), gameplay validation, physical latency. MAME 0.289 is the planned private oracle; the qualification gates
([QUALIFICATION.md](QUALIFICATION.md)) are `?` for this machine until a panel has been converted and read.
