# Amstrad CPC

**Status: in development (experimental, developer only).** The profile `cpc` recognises Amstrad CPC disk images, and a
developer's conversion runs its whole chain on authored programs in place of the firmware; it is offered in no installation and
has converted no game yet (the first, Bomb Jack, waits for the owner's firmware). This page says what is built, what is planned
and what is left out. No game is claimed to run.

## 1. Scope

| Planned first | Later | Left out of this profile |
|---|---|---|
| CPC 6128 disk games: a `.dsk` image (standard or extended) or a ZIP holding one, started from BASIC by the command its catalogue gives | the CPC 664's firmware on the 6128's board (accepted), CRTC types 0 and 2 for a game whose reviewed data asks for one | tapes (`.cdt`), snapshots (`.sna`), the CPC 464's firmware, the Plus range and the GX4000 (their ASIC and `.cpr` cartridges), IPF and flux images, light guns, the AMX mouse |

The Z80 is to run on the shared banked Z80 chain of the Master System and the MSX, its time rounded to the Gate Array's
microsecond; the code a disk loads into RAM is to be learned with byte guards and kept as offsets in the disk, as the MSX2+'s
disks are. What is not native runs on the reference interpreter, counted and shown. Disk protections that decrypt themselves in
RAM may stay interpreted, counted and shown.

## 2. What is built (21 November 2026)

| Piece | Where | Checked by |
|---|---|---|
| Disk reader: DSK and EXTENDED DSK, sector IDs and recorded status, weak sectors in several copies, unformatted tracks; the AMSDOS catalogue and the start command | `retrorecomp/cpc_disk.py` | `tests/test_cpc_disk.py` (images built by the test) |
| The same reader for the runtime, and the uPD765 floppy controller (machine-neutral) | `native/upd765/` | `tools/upd765_selftest.py` |
| I/O decoding and memory map (ROMs, the 6128's RAM configurations), CRTC 6845 (types 0, 1, 2), Gate Array (pens, 27 colours, modes 0-3, 300 Hz interrupt, the 6128's RAM banking, the picture), PPI 8255 with the keyboard matrix and two joysticks | `native/cpc_machine/` | `tools/cpc_hardware_selftest.py` |
| The Z80's costs on a CPC, in microseconds, for every opcode of the seven tables (taken branches and repeating block instructions apart): the Gate Array puts every bus access on one phase of its 1 MHz clock, applied to the SingleStepTests bus traces; HALT and the interrupt acceptance derived with the same rule, not yet checked against a CPC | `retrorecomp/cpc_timing.py`, `tools/cpc_timing_table.py` | `tests/test_cpc_timing.py` (57 documented costs, and the table against its derivation) |
| The 6128 board: 128 KiB of RAM and the ROMs behind the Gate Array's map, the devices on the 16-bit ports, the time in T-states (one character a microsecond), the interrupt and its acknowledge; its glue on the shared banked Z80 chain (four 16 KiB regions, the system ROM and AMSDOS as sources) | `native/cpc_machine/cpc_machine.c`, `cpc_glue.inc`, the profile's `Z80Machine` | `tools/cpc_hardware_selftest.py` (the board through its bus); the glue waits for the chain's 16-bit ports |
| The reference Z80 interpreter on the board (the counted fallback's copy, with the CPC's costs and 16-bit ports), run by authored programs as the system ROM: the costs in microseconds, 300 Hz interrupts, the drawn picture, a sector read as AMSDOS reads it | `native/cpc_machine/cpc_reference_main.c`, `tools/cpc_reference.py` | `tests/test_cpc_reference.py` |
| Native code: the same authored programs translated by the CPC's own generator on the banked Z80 chain, run headless through `cpc_glue.inc` and compared with the reference field by field (CPU, time, interrupts, RAM, picture, Gate Array, AY, controller): equal on all three, 0 interpreted steps; code built in RAM interpreted and counted (600 steps), then native with byte guards once learned (0) | `native/cpc_machine/cpc_native_main.c`, `tools/cpc_native.py` | `tests/test_cpc_native.py` |
| Firmware recognition (the player's system ROM and AMSDOS ROM, by their public SHA-1) | `retrorecomp/cpc_firmware.py` | `tests/test_cpc_profile.py` |
| The game: the board with the disk in drive A, the host kit's window through the CPC adapter (`rrhk_cpc.inc` on the computers' adapter), the start command typed from the machine's frame count; quick states (F8/F9) and the multiplayer snapshots and digest on the chain's shared state files (`z80_chain_state.inc`, `state_file.h`) | `native/cpc_machine/cpc_player.c`, `cpc_state_file.inc`, `retrorecomp/cpc_build.py` | `tests/test_cpc_build.py`; a state saved at frame 40 continued by a fresh process equals the uninterrupted run, the snapshot probe passes |
| One headless run shared by the reference runner, the native check and the game (options, the frame's sound, a row per frame, the report, the boot keys), so the three are compared field by field and row by row | `native/cpc_machine/cpc_headless.inc`, `cpc_boot_input.h` | `tools/cpc_native.py` (every row equal) |
| The conversion: the start command written, the firmware translated and the code run from RAM learned (`learn_passes`), the native run against the reference on every field and every row (a difference refuses it), the game built, the delivered (compressed) file replayed against both, quick states in a fresh process (13 damaged states refused), the report | `retrorecomp/cpc_conversion.py` | `tests/test_cpc_conversion.py` (the refusals); run end to end on an authored disk and authored programs in place of the firmware: 0 interpreted on its boot route |

These checks are tests of our chips and of the chain against their documented behaviour, on images, screens and programs the
checks build: they say nothing yet about a game. The conversion's route is the start of a game only (the command typed, then the
frames that follow, no joystick).

### The start command

A CPC disk game is started from BASIC by typing a command. The converter reads the disk's AMSDOS catalogue and proposes one, in
this order: a program named DISC (`RUN"DISC`); the one command the programs give; the one BASIC program among those the catalogue
shows (the loader of the others); the one name every other program's name starts with; `|CPM` for a disk in the system format with
no file. A disk whose catalogue does not decide stays undecided with its candidates: the conversion never picks one of two
programs.

### The uPD765

The controller finds a sector by its ID on the track under the head, from the drive's rotational position, so a track's order,
its odd IDs, its missing sectors, its deleted marks and the error status an extended image recorded are what a program reads. A
weak sector gives its copies in turn, as part of the state (two runs of one input read the same bytes). The CPC leaves the
terminal count line unconnected: a transfer ends after its last sector with « end of cylinder », which AMSDOS takes as the
normal end. Every operation completes at once (no rotation or step time, no overrun): a protection that measures time on the
disk is not answered. The SCAN commands and a FORMAT the image cannot hold in place are refused and counted.

### The picture

768 x 272 pixels: the window a monitor shows of the firmware's screen with its border. The monitor's beam returns at each CRTC
HSYNC and VSYNC, so a program that moves them moves the picture; the window's offsets are an approximation of a monitor, not a
measure of one.

## 3. Firmware

No free CPC firmware exists. The player gives his own: the 32 KiB system ROM (the OS and Locomotive BASIC) of a CPC 6128 (English,
French or Spanish) or 664, and the 16 KiB AMSDOS ROM, chosen in Options or found by « Find firmware in a folder ». They are
recognised by the SHA-1 MAME 0.289 lists for them and are never shipped. Locomotive BASIC is not covered by Amstrad's 1999
permission for emulators, so the converter does not fetch these files.

## 4. The five measures

Native code, CPU fidelity, hardware fidelity, gameplay validation and physical latency are separate measures. None is measured
for the Amstrad CPC yet: no game is converted (the authored checks measure native code and agreement with the reference on
programs written for the check, not on a game).

## 5. Panel (from the owner's library)

Bomb Jack (the first game), Gryzor, Head over Heels, Match Day II (two players: the second joystick on keyboard row 6), Super
Hang-On and Robocop (extended images with protection tracks), Castle Master (Freescape 3D), Dizzy - The Ultimate Cartoon Adventure.
`tools/cpc_panel.py` reads a folder of disks and writes numbers about each one (format, odd tracks, weak and error sectors, the
start command), never their bytes.

## 6. References

Written from the chips' data sheets and the CPC's documented behaviour; floooh/chips (zlib) and Clock Signal (MIT) read as
documentation, nothing of them copied. No GPL code: the Z80 chain carries a noncommercial licence, so no GPL part may share a CPC
game's executable.
