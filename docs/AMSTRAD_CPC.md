# Amstrad CPC

**Status: in development (experimental, developer only).** The profile `cpc` recognises Amstrad CPC disk images and converts
nothing yet; it is offered in no installation. This page says what is built, what is planned and what is left out. No game is
claimed to run.

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
| Firmware recognition (the player's system ROM and AMSDOS ROM, by their public SHA-1) | `retrorecomp/cpc_firmware.py` | `tests/test_cpc_profile.py` |

These checks are tests of our chips against their documented behaviour, on images and screens the checks build: they say
nothing yet about a game.

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
for the Amstrad CPC yet: no game is converted.

## 5. Panel (from the owner's library)

Bomb Jack (the first game), Gryzor, Head over Heels, Match Day II (two players: the second joystick on keyboard row 6), Super
Hang-On and Robocop (extended images with protection tracks), Castle Master (Freescape 3D), Dizzy - The Ultimate Cartoon Adventure.
`tools/cpc_panel.py` reads a folder of disks and writes numbers about each one (format, odd tracks, weak and error sectors, the
start command), never their bytes.

## 6. References

Written from the chips' data sheets and the CPC's documented behaviour; floooh/chips (zlib) and Clock Signal (MIT) read as
documentation, nothing of them copied. No GPL code: the Z80 chain carries a noncommercial licence, so no GPL part may share a CPC
game's executable.
