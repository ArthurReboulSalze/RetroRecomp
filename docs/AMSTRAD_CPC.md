# Amstrad CPC

**Status: in development (experimental, developer only).** The profile `cpc` recognises Amstrad CPC disk images and converts
them, for developers only, on the CPC 6128's firmware: the panel's eight games convert with 0 interpreted instructions on their
routes, equal to the reference interpreter frame by frame, the same on Windows and Linux ([section 5](#5-panel-22-november-2026)).
It is offered in no installation; the owner's play test (G14) is to come. This page says what is built, what is measured and what
is left out. No game is claimed to be validated: the routes are short, scripted runs.

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

No free CPC firmware exists. A converted game runs on the CPC 6128's system ROM (the OS and Locomotive BASIC, 32 KiB) and the
AMSDOS ROM (16 KiB), which come from one of two places:

* **Fetched** (the default, the maintainer's choice of 21 November 2026, as for the ZX Spectrum's ROMs): on first use the
  converter fetches `cpc6128.rom` and `amsdos.rom` from the `rom/` folder of the Caprice32 project at one pinned commit, under
  Amstrad's 1999 permission for emulators ([amstrad-cpc-roms.md](../licenses/amstrad-cpc-roms.md); Locomotive BASIC is not named
  in it). Each file is checked by its size, its Git blob SHA-1 at that commit, the SHA-1 MAME 0.289 lists for it and its pinned
  SHA-256 (`retrorecomp/cpc_roms.py`); a file that fails any check is refused with a sentence. Nothing of them is in this
  repository or the installer; every converted game holds them with their notice.
* **The player's own**, chosen in Options or found by « Find firmware in a folder »: a CPC 6128 (English, French or Spanish) or
  664 system ROM and the AMSDOS ROM, recognised by the SHA-1 MAME 0.289 lists for them. The system ROM may also be its two 16 KiB
  halves in one folder, the OS and BASIC files of Clock Signal and most CPC emulators (`os6128.rom` and `basic6128.rom`,
  `os664.rom` and `basic664.rom`, `amsdos.rom` beside them): the OS half is chosen, and is recognised when it and a 16 KiB
  neighbour together are a system ROM of that list, whatever their names. Each option the player fills replaces the fetched file.

## 4. The five measures

Native code, CPU fidelity, hardware fidelity, gameplay validation and physical latency are separate measures.

* **Native code** (measured, per conversion): the Z80 instructions run natively and on the counted interpreter, per route. The
  panel's routes run 0 interpreted instructions once the code the games load into RAM is learned (two passes).
* **CPU fidelity** (measured against the project's own reference, and against independent vectors): the native run and the
  reference interpreter on the same board agree on every compared field and every frame's row (CPU, RAM, picture, sound, chips).
  The 51,328 SingleStepTests/z80 vectors (an emulator's, MIT, not hardware captures) pass through the CPC's own generator,
  registers, flags, memory, the whole 16-bit port and each vector's microseconds as the Gate Array's bus rule gives them for its
  own trace (`tools/banked_vector_selftest.py --machine cpc`, 22 November 2026). The interrupt acceptance and HALT costs come from
  the same rule on the Z80 data sheet's cycle shapes and are not in the vectors.
* **Hardware fidelity**: not measured. The chips are our own C, checked against their documented behaviour; no CPC and no
  external emulator was compared yet.
* **Gameplay validation**: not done. The routes are 3,600 frames each, scripted; the owner's play test is G14.
* **Physical latency**: not measured, never claimed.

## 5. Panel (22 November 2026)

Eight games of the owner's library (DSK and EXTENDED DSK images, read from the NAS, never copied into the repository), converted on
the pinned CPC 6128 firmware from an empty scratch library, two conversions at a time; each has two routes of 3,600 frames:
**boot** (the start command typed, then nothing) and **play** (the trainers' questions and title-screen keys first, keys only, then
the joystick at random, seeded by the disk; `retrorecomp/cpc_routes.py`).

| Game | Start | Learning (interpreted steps, pass 1 → 2) | Interpreted on boot / play | Play route reaches | Audible frames (play) |
|---|---|---|---|---|---|
| Bomb Jack | `RUN"BOMB` | 3,655,961 → 0 | 0 / 0 | the first level (the pyramids), after its trainer and control menu | 508 |
| Gryzor | `RUN"GRYZOR` | 14,386,604 → 0 | 0 / 0 | the first level (the jungle) | 66 |
| Head over Heels | `RUN"HEAD` | 336,120 → 0 | 0 / 0 | its main menu, after a trainer's three « (o/n)? » | 190 |
| Match Day II | `RUN"MATCHDAY` | 6,088,719 → 0 | 0 / 0 | its match menu | 2,698 |
| Super Hang-On | `RUN"DISC` | 7,514,067 → 0 | 0 / 0 | the race (Africa) | 2,344 |
| Robocop | `RUN"M` | 1,268,142 → 0 | 0 / 0 | the first street | 2,247 |
| Castle Master | `RUN"CASTLE` | 6,990,294 → 0 | 0 / 0 | the castle, in 3D | 186 |
| Dizzy - The Ultimate Cartoon Adventure | `RUN"DIZZYFL` | 5,042,300 → 0 | 0 / 0 | the first screen, in play | 2,932 |

For every game: the native run equals the reference interpreter on both routes, every field and every frame's row; the delivered
(compressed) file replayed headless equals both; a quick state saved near the play route's end continues in a fresh process for
600 frames, 13 kinds of damaged state and a missing one are refused; `tools/release_check.py`'s conversion, native_reference,
fallback, packed and states gates pass. The pictures at frames 2,400 and 3,600 of each play route were looked at, and the sound
written as WAV. **Linux**: Bomb Jack converted again in WSL (Debian 13) from the same sources gives the same rows as Windows on
both routes (native, reference and delivered file), the same learning and the same final hashes.

**Long routes** (22 November 2026): the eight games played 18,000 frames (five minutes: the play route's 3,600, then the joystick
and a start key every 600 frames, so a game that ended goes back into play; the 3,600-frame scripts are unchanged) with the programs
each conversion built. Native equals the reference on every field, drive A's digest included, and every frame's row; the code first
run after frame 3,600 runs on the counted interpreter (0 to 1,705,300 steps), since learning sees the 3,600-frame routes. At frames
6,000, 12,000 and 18,000: Castle Master, Gryzor and Robocop in play; Dizzy in its first room; Bomb Jack on its pyramids, then game
over, then its menu; Super Hang-On racing, then its tables and title; Match Day II in a match at the end; Head over Heels stays on
its menu. Random routes, not played games.

**Written disks**: what a game writes on drive A goes to a copy beside it (`datas/games/cpc-<identity>/disk-1.dsk`), read back at the
next start. Every conversion checks it in fresh processes of the delivered file (`--disk-copies`, the report's `disk_writes`): a
copy exactly when the game wrote, a new process starting from it, a copy of the wrong size not read and left as it was. No panel
game writes its disk on its routes; an authored program that writes a sector as AMSDOS does (`tools/cpc_reference.py`) shows the
whole path: native equal to the reference with the disk's digest compared, the copy equal to the disk with that sector written, a
fresh process starting from it. Castle Master and Rigel's Revenge were looked at for a real save: no key writes in the first, the
second saves to tape through its own routine.

Bomb Jack, Gryzor and Head over Heels are delivered for the owner's play test, with a short checklist (G14). `tools/cpc_panel.py`
reads a folder of disks and writes numbers about each one (format, odd tracks, weak and error sectors, the start command), never
their bytes.

**Found on the way**: the native side acknowledged the Gate Array's interrupt after running the acceptance's microseconds, the
reference before; an HSYNC inside them moved the next interrupt, and Bomb Jack lost one while AMSDOS loaded (now acknowledged at
the start of the acceptance, as the machine does). Most CPC games were written for the built-in mono speaker: the sound is mono by
default, the headphone jack's stereo an option (F2).

## 6. Multiplayer

Two seats in rollback (the game's own snapshots: the CPU, the board and, once the game has written it, drive A's disk): joystick 1
on keyboard row 9, joystick 2 on row 6 as the machine wires it, the host typing for everyone. The host's disk A is the match's save:
it travels to every seat and is played in memory; a guest plays the host's disk or, if none comes, the embedded one, never its own
copy; nobody writes a copy during the match, the host writes its own once at a clean end (the previous one kept as `.bak`). The
report's top-level `firmware` record (the system ROM and AMSDOS) makes a room refuse two seats on different firmware. Proved on an
authored game (`tools/netplay_game_smoke.py`: two seats, rollback, latency, loss, a save and load and a restart for everyone, equal
digests), then on the panel's games (22 November 2026):

* the snapshots on all eight (`--snap-probe 2400:300` on the play route of the delivered game): saved twice the same, a snapshot of
  the wrong size refused, and after loading the one of frame 2,400 the next 300 frames give the same digests and pictures again;
* Bomb Jack on Windows and in WSL (Debian 13), converted from the same commit: the same folded digest of those 301 frames
  (`ee81e7a4c12c893f`) and the same final hashes on both routes;
* `tools/netplay_game_smoke.py` on real games, one PC: Bomb Jack, two seats in rollback with 30 ms latency, 10 ms jitter and 2 %
  loss and a restart for everyone at frame 1,500 (97 corrections, at most 2 frames deep, digests equal on every 60th frame of
  3,000); Gryzor with the host's save at frame 1,800 and load at 2,400 for everyone (equal digests).

Not yet: two PCs (Bomb Jack is in the multiplayer specialist's plan).

## 7. G14 checklist for the owner's play test (22 November 2026)

About three minutes a game, on Bomb Jack, Gryzor and Head over Heels as delivered:

1. **Start**: the CPC's screen (« Amstrad 128K Microcomputer », BASIC 1.1, « Ready »), then the start command typed by itself and
   the disk loading (about ten seconds). The three disks carry trainers: Bomb Jack asks « Unlimited Lives (Y/N) ? » then shows a
   control menu (J: joystick, 1: one player); Head over Heels asks three « (o/n)? » questions (N and RETURN each time).
2. **Picture**: colours, centring, no tearing; a border of another colour than the paper is the machine's.
3. **Sound**: mono by default (the built-in speaker); F2's « Sound » row gives the headphone jack's stereo (A left, C right, B in the
   middle), kept per game. Bomb Jack is loud: say if it clips.
4. **Controls**: the pad is joystick 1 (A fire 1, B fire 2, Start SPACE, Select RETURN); the keyboard at the CPC's positions,
   Ctrl+Alt+K for the full keyboard. Reactivity is the owner's impression, never a latency figure.
5. **Quick states**: F8, play on, F9; then F1 (help), pause and the restart.

## 8. References

Written from the chips' data sheets and the CPC's documented behaviour; floooh/chips (zlib) and Clock Signal (MIT) read as
documentation, nothing of them copied. No GPL code: the Z80 chain carries a noncommercial licence, so no GPL part may share a CPC
game's executable.
