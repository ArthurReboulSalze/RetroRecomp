# MSX

Experimental profiles (`msx`, and `msx2` for the MSX2, described in section 8), experimental since 1.7.3. The `msx` profile converts an MSX1 cartridge into a standalone Windows
executable whose Z80 code, as far as the conversion saw it run, is translated ahead of time to C, with a counted interpreter for the rest.
The cartridge boots on C-BIOS 0.29a or on the player's own MSX BIOS. Nothing here says that a game plays completely, that the hardware is
reproduced faithfully or how long input takes to reach the screen: those are separate measures, listed below with what is known of each, and
for the MSX most of them are not known yet.

## 1. What is converted, and what is not

| Converted (experimental) | Not yet |
| --- | --- |
| MSX1 cartridges, read from a `.rom`, a `.mx1` or a ZIP holding one (a `.rom` or `.bin` is the MSX's when its bytes hold an MSX cartridge header; a `.mx1` always is) | The turbo R; disk games (a `.dsk` is the MSX2+'s, section 9; the MSX2 is the `msx2` profile, section 8) |
| Plain cartridges of 8 KiB to 64 KiB, and the Konami, Konami SCC, ASCII 8 KiB and ASCII 16 KiB mappers, with the battery SRAM of an ASCII cartridge (since 1.7.4, section 4) | The other mappers (the rare ones), FM-PAC and its SRAM, the MSX2 clock's memory between runs |
| C-BIOS 0.29a (BSD-2-Clause), fetched by the converter from its official release on first use and pinned by SHA-256; or the player's own MSX1 BIOS (a 32 KiB main ROM; an MSX2 or later BIOS is refused), chosen in Options > MSX | Disks, cassettes, MSX-BASIC under C-BIOS |
| The keyboard, joysticks 1 and 2 (the keyboard's arrows and keys or a gamepad, and a second gamepad), the TMS9918A picture and sprites, the AY-3-8910 sound, the key click and the Konami SCC sound; quick states (F8/F9) | The FM-PAC's sound |
| Windows; Linux: one MSX1 and one MSX2 game converted headless on a Debian 13 PC, with the same results as on Windows | Windowed play on Linux |

C-BIOS runs cartridges only: it has no MSX-BASIC, so a BASIC cartridge is refused under C-BIOS, and it has no disk and no cassette. A game that needs
those, or a BASIC cartridge, needs the player's own MSX BIOS. The input is read in place and never changed. The player supplies the cartridge (and
their BIOS if they want one); Retro-Recomp publishes no game and no firmware, and an MSX BIOS is never shipped. A game converted with your own BIOS holds
that BIOS and code translated from it, as on the other machines that take your own firmware: keep it for yourself.

## 2. How the conversion works

1. **Reading the input.** `retrorecomp/msx_rom.py` reads the cartridge (or the ZIP holding one) and takes its SHA-256 as the identity of the game. It
   guesses the mapper from the cartridge's own bytes; for an MSX2 mapper cartridge, when that guess is not enough, short probe runs of the reference under each mapper settle it (the share of the program's cartridge writes that land on that mapper's registers, among runs that do not fall into empty memory; Aleste was guessed Konami SCC and is ASCII 16). `retrorecomp/msx_cbios.py` fetches C-BIOS 0.29a from its official release on first use and checks
   its SHA-256 against the pin. A BIOS of your own (a 32 KiB main ROM) is checked by its content and its SHA-256 is the identity of the firmware, in the
   request, instead of the pin of C-BIOS.
2. **Native code.** The cartridge and the BIOS are translated ahead of time to C by the shared banked Z80 chain, the one the Master System and the Game
   Gear use (`retrorecomp/z80_chain.py`), on the MSX's own description: a region map of eight 8 KiB regions with the cartridge and the BIOS as sources,
   one wait state per M1 cycle, and /INT read at the end of each instruction. Code run from RAM is learned and translated with byte guards. What the
   translation does not cover runs on a reference Z80 interpreter and is counted.
3. **The machine.** The TMS9918A video, the AY-3-8910 sound, the Konami SCC sound, the PPI (keyboard and slot select), the slots and the mappers are
   Retro-Recomp's own C (`native/msx_machine/`, MIT). No emulator core is inside the executable: this is not a machine that runs on an emulator core.
4. **Routes.** A conversion plays the routes of its scan level, as the PC Engine does: `attract` (no input), `play` and, at the extended and thorough
   levels, one or two long routes of 18,000 frames. A route presses what a player's default mapping presses (a direction on joystick 1 and the cursor
   key together, fire on trigger A and SPACE together, RETURN, 1 and 2). How `play` starts is chosen on the reference interpreter for each
   cartridge: fire pressed 1, 2, 3, 4 or 6 times, or 1 to 3 times each followed by RETURN; the variant kept stays alive to its end and reaches the most
   pictures of its own, then a walk seeded by the cartridge. The report records the choice and every variant's numbers.
5. **Comparison.** Native code is compared with the reference Z80 interpreter on the same machine, on every route: the state fields at its last frame
   and one row per frame (CPU, RAM, picture, sound). A conversion whose native run differs is refused. The delivered (compressed) game is then replayed
   on every route and must give the same rows. An external emulator (openMSX) is used privately for comparisons during development and is never
   shipped.

## 3. The five measures

Kept separate here, as everywhere. Interpreter fallback is always counted, per CPU (the Z80) and reported by the conversion.

| Measure | What is known | What is not |
| --- | --- | --- |
| Native code | On the panel of 14 November 2026 (extended level: attract, play and an 18,000-frame route, from an empty library, C-BIOS 0.29a), eight MSX1 cartridges (Knightmare, Road Fighter, Space Invaders, Nemesis, Salamander, Spy vs Spy II, Dragon Slayer II - Xanadu, Deep Dungeon; plain, Konami, Konami SCC, ASCII 8 with battery SRAM, NTSC and PAL) end at 0 interpreted instructions on every route, on Windows and on a Debian 13 PC alike; Salamander also with an MSX BIOS of its owner (12 November) | Nothing is said of the games not named here. A game's first conversion interprets C-BIOS's own start-up code (about 24,700 instructions, the same for every game) until its second pass translates it |
| CPU fidelity | On the same games the native code is equal to the reference Z80 interpreter on every route, on the state fields at its end and on one row per frame (CPU, RAM, picture, sound); the delivered (compressed) game gives the same rows, and the Debian 13 PC the same fields as Windows. The 51,328 SingleStepTests/z80 vectors pass through the MSX's own build of the generator (13 November 2026). This is agreement with our own reference interpreter and with an emulator's vectors, not with a real MSX | No comparison on a real machine; the vectors run on a flat test bus, so the region map is covered by the panel, not by them |
| Hardware fidelity | Nothing is claimed. The mixing levels of the sound (PSG, key click, SCC) are a stated choice, not validated; only the key click's level was measured against openMSX (a private comparison emulator, run as a separate program) | The TMS9918A, the AY-3-8910 and the SCC against an independent reference |
| Gameplay validation | None: no game has been played through by the owner (his play checklist is in [QUALIFICATION.md](QUALIFICATION.md)) | Everything |
| Physical latency | Not measured | No latency figure; none is claimed |

These are the panel's measures (section 7). They say nothing for other games, other mappers or the player's own BIOS.

## 4. Controls

The keys of a converted game, also in [CONTROLS.md](CONTROLS.md#msx-and-msx2-experimental):

| Key | MSX |
| --- | --- |
| Arrow keys | Joystick 1; they also press the MSX cursor keys |
| X | Trigger A (it also presses SPACE) |
| W | Trigger B |
| Start (Enter, pad Start) | The MSX SPACE key |
| Select (right Shift, pad Back) | The MSX F1 key |
| Ctrl+Alt+K | Hands the whole keyboard to the MSX; F1 to F5 then go to the MSX, and the help is at Ctrl+F1 |

F8 saves a quick state and F9 loads it, at the end of a frame, in the game's folder beside its settings (`datas/games/msx-<identity>`, or `msx2-<identity>`
on the MSX2). A state is refused, and the game goes on untouched, when anything differs: the cartridge, the BIOS, the options or the build. Each conversion
checks it on the delivered file: a state saved near the end of the route is loaded by a fresh process, which must continue the same frames for 600 frames,
and damaged or missing states must be refused and left as they were. The F2 pages, autofire and the speed and sound controls are the common ones of the host kit.

**Saves (battery SRAM, since 1.7.4).** An ASCII 8 KiB or 16 KiB cartridge with battery SRAM keeps it in `datas/saves/<game>-<cartridge>.rrsram`
beside the game: loaded at start, written two seconds after the game last wrote it and when the window closes. The conversion finds the SRAM
from the bank values the game writes (a bit above the bank number, which depends on the cartridge's wiring); its mapper probe counts the writes to
that SRAM apart from the writes a cartridge would ignore (since 14 November 2026: Deep Dungeon, ASCII 8 with 2 KiB of SRAM, was read as ASCII 16
before, and Super Daisenryaku, ASCII 16 with 2 KiB, as ASCII 8). The size is the mapper's, not the board's: 8 KiB on ASCII 8 and 2 KiB repeated over
the page on ASCII 16 (Deep Dungeon's 2 KiB live in an 8 KiB file); a game that selects its SRAM only later than its routes keeps none. A file the game
cannot use is moved aside (`.unusable-1`) and the game starts blank. Checked on Dragon Slayer II - Xanadu and Deep Dungeon (Japan): the play route
writes the SRAM, a fresh process finds it, damaged files are set aside. No MSX2 game of the panel selected its SRAM on its routes. Quick states carry the SRAM of their moment. The FM-PAC and its SRAM are not converted. The MSX2 clock's battery memory (the RP5C01's 26 nibbles, where the BIOS keeps its screen settings, a title and a password) is not kept between runs: no game was checked for it and none of the panel is known to use it, and it can be added if a game needs it (the owner's decision, 14 November 2026).

## 5. Known C-BIOS failures

C-BIOS is a free BIOS, not Microsoft's, and a few games depend on what only the original has.

- **Salamander (Japan): no longer seen failing.** In development (12 November 2026) its playfield stayed black under C-BIOS 0.29a while the score and
  the lives changed, on our machine and on openMSX 22.0 with the same C-BIOS. On the panel of the 1.7.3 release tree it is drawn under C-BIOS on all three
  routes, as with the owner's own MSX BIOS (the stars, the ships, the enemies, the mothership and the score panel of the first stage, the same pictures
  on both BIOSes). Why the earlier run differed is not established, and nothing past the start of the first stage was looked at; if your copy shows a
  black playfield, choose your own MSX BIOS in Options > MSX.
- **Heroes of the Lance (Japan, MSX2): its Japanese text is drawn with the wrong characters under C-BIOS** (seen on the panel of 14 November 2026:
  the character introductions and the menus show Greek letters and symbols). C-BIOS's character set is not a Japanese MSX's; with your own Japanese
  MSX2 BIOS it is not checked yet. The game runs (0 interpreted instructions on every route).
- **BASIC cartridges** are refused under C-BIOS, which has no MSX-BASIC.

Other known limits: the FM-PAC and cassettes are not converted, disk games are the MSX2+'s (section 9; MSX2 cartridges are the `msx2` profile, section 8), and no game other than the ones named in sections 3 and 4 has been checked.

## 6. Licences

Original code, the machine, the translator glue and the checks are MIT, like the rest of Retro-Recomp. C-BIOS is BSD-2-Clause and is downloaded by the
converter from its official release, not kept in this repository. The player's own MSX BIOS is never shipped. openMSX is used privately for comparisons only
and nothing of it is in an executable or in this repository. The Z80 translator and the reference Z80 interpreter are the ones of the Master System and the Game Gear, under
their own licences, listed in [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) (z80-recomp-core, superzazu/z80).

## 7. Where it stands in the qualification

The `msx` and `msx2` columns of [QUALIFICATION.md](QUALIFICATION.md) were evaluated again on 14 November 2026, on a panel of eight cartridges per
machine converted at the extended level from an empty library, on Windows and on a Debian 13 PC (the evidence of each letter is there). Met: the status
(G1), the common report (G2), native coverage (G3), the fresh reference run (G4), the replay of the delivered file (G5), the fresh-process quick states
(G6), liveness (G8), the independent Z80 vectors (G10), the panel (G12), the Linux witness (G13: the sixteen games give the same report fields on both
systems), honesty (G15) and, on the MSX, battery saves (G7: two games). Partial: battery saves on the MSX2 (G7: no MSX2 game of the panel selected its
SRAM on its routes), route depth (G9: thirteen of the sixteen long routes reach play; Deep Dungeon stays in its name entry, Super Daisenryaku in its map
setup, Heroes of the Lance at a question of its menu) and independent hardware evidence (G11). Unknown: the owner's acceptance (G14; his play checklist is
in QUALIFICATION.md).

**Shared paths: declined (G16 `-`).** Sharing paths serves no purpose here, so the MSX and the MSX2 do not share them (the owner's rule of 14 November
2026). The evidence is the panel's: the only code its sixteen games run from RAM is the BIOS hooks they write, a jump into the cartridge followed by a return
(`C3 nn nn C9`), whose bytes are in no cartridge, so a game's record would hold no path; and the instructions a game's first conversion interprets are
C-BIOS's own start-up code (about 24,700 on most games) and those hooks. A received path would add no native instruction and save no conversion pass. The sharing code that was
written for them is kept apart, should a game ever run cartridge code from RAM.

Leaving the experimental status is the owner's own decision (G14), and nothing here asks for it.

## 8. The MSX2 (`msx2`)

Experimental profile `msx2`, the second profile of the MSX family, beside `msx` as the Game Gear is beside the Master System. It shares the Z80 chain, the
keyboard, the sound and the cartridge mappers of the MSX1 and adds the V9938, a memory mapper and a clock. It is experimental since 1.7.3, and
**the V9938 command engine's timing is approximated**.

**Converted:** MSX2 cartridges (plain, Konami, Konami SCC, ASCII 8 KiB and ASCII 16 KiB mappers), from a `.mx2`, `.rom` or ZIP that you
choose as MSX2 in the console list or that sits in a folder named `msx2` (a `.mx2` with no such hint goes to the MSX2+: section 9). The machine (implemented, and checked only as section 8's table says): the V9938 drawn line by line (all screen modes, sprite mode 2, the
palette, scrolling, the line interrupt, the display pages; VRAM is held as the chip holds it, in two banks, so Graphic 6 and 7 reach their logical addresses interleaved), the V9938 command engine (all twelve commands, HMMC, YMMM, HMMM, HMMV, LMMC, LMCM, LMMM, LMMV, LINE, SRCH, PSET and POINT, and STOP, with the logical operations, in the bitmap modes G4 to G7 only; V9938 commands: all twelve, timing approximated), the memory mapper (128, 256 or 512 KiB of RAM, chosen in Options > MSX2, default 256) and the
RP5C01 clock, frozen at 2000-01-01 12:00:00 and then running on machine time (not your PC's clock). The picture is 544 x 228 (see [CONTROLS.md](CONTROLS.md#msx-and-msx2-experimental)).

**Firmware:** C-BIOS 0.29a MSX2 images (main ROM, logo and sub-ROM), fetched and pinned like the MSX1's, or your own MSX2 BIOS pair: the main ROM
(`msx2_bios`) and its 16 KiB sub-ROM (`msx2_subrom`, the file beginning "CD"), chosen in Options > MSX2 and never shipped. The same rules as for the MSX1:
the input is never changed, and a game converted with your own BIOS holds it and code translated from it.

**Timing approximated** means an average cost per byte or dot in three classes (display off or outside the picture; picture with sprites off; with sprites on) plus a line-end cost; the chip's access slots and the slots the CPU takes are not modelled. C-BIOS's MSX2 logo, drawn by an HMMC, now appears.

**Not yet:** disks,
cassettes, FM-PAC, the turbo R, windowed play on Linux (the MSX2+ is its own profile, section 9).

**Not modelled in the V9938:** the access-slot timing of port 98h and of the command engine, the F and FH status flags' lost windows, the change of frame length when R#9's LN bit
switches, mid-line effects, the field offset of interlace, superimpose and digitise, and expansion RAM, and a flags-only sprite pass after the picture. The audio of an MSX2 game under heavy load is an open point, to check on a quiet PC. Where hardware reports disagree on sprite mode 2's rules,
the profile follows openMSX's reading; that is a choice, not a proof.

**The five measures for the MSX2**, kept separate:

| Measure | What is known | What is not |
| --- | --- | --- |
| Native code | On 14 authored cases, on both boards, 0 interpreted instructions after learning; on the panel of 14 November 2026 (extended level, from an empty library) Metal Gear, Space Manbow, Aleste, Hydlide 3, Super Daisenryaku, Vampire Killer, Fantasy Zone II, Heroes of the Lance end at 0 interpreted instructions on every route, equal to our reference interpreter frame by frame, on Windows and on a Debian 13 PC alike | Hydlide 3's long route stays in its character set-up menu at this level (at the thorough level, 13 November, it walks the overworld); Super Daisenryaku stays in its map setup and Heroes of the Lance at a question of its menu; Metal Gear's play route stops at its first transceiver call (its long route goes on); pad routes, not full games |
| CPU fidelity | On the same 14 cases the native code equals the reference Z80 interpreter on 39 compared fields (the 37 of the MSX1 plus the V9938 state and the mapper). This is agreement with our own reference, not with a real MSX2 | No independent comparison on a real machine |
| Hardware fidelity | Nothing is claimed as exact. 682 hand-worked checks of the V9938, the engine and the MSX2 board pass (development checks, not a qualification): they check our model against our own reading of the documents. Against openMSX (a private comparison emulator, never shipped) the 128 KiB VRAM, the 47 VDP registers and the palette are equal at chosen still frames for the C-BIOS logo, two authored cartridges, Metal Gear, Space Manbow, Aleste and Hydlide 3; at other frames the differences are timing (a command still running, a palette fade step, a sprite double-buffer phase) | Other frames; command timing; the RP5C01; everything in the list above |
| Gameplay validation | None: no game has been played through | Everything |
| Physical latency | Not measured | No latency figure; none is claimed |

Section 3's remarks apply here too. The `msx2` column of [QUALIFICATION.md](QUALIFICATION.md) has the `msx` column's letters but for battery saves
(G7, partial: section 7).

## 9. The MSX2+ (`msx2plus`)

Experimental profile `msx2plus`, the third profile of the family, experimental since 1.7.4. It is the MSX2's board with the V9958
in place of the V9938 and the I/O port F4h, and the same cartridges, mappers, SRAM, routes, checks and quick states.

**Converted:** MSX2+ cartridges, from a `.rom` or ZIP that you choose as MSX2+ in the console list or that sits in a folder named `msx2+`
(or `msx2plus`, `msx2p`).

**MSX2 or MSX2+: which machine a file goes to** (Arthur's rule, 13 November 2026), in this order:

1. MSX2 chosen in the console list, or the file in an `msx2` folder: the MSX2.
2. MSX2+ chosen, or the file in an `msx2+` folder: the MSX2+.
3. A file known to be at least MSX2 with nothing saying which (a `.mx2`, or a ZIP holding one, outside those folders): the MSX2+, which runs
   nearly every MSX2 game, while the MSX2 cannot run an MSX2+ game.
4. A plain `.rom` with no hint: the MSX1's check, as before (the doubt is not widened to MSX1 files).

The conversion says in one line which hint decided (`msx2+ folder`, `msx2 folder`, `chosen in the menu`, or `in doubt between MSX2 and
MSX2+: MSX2+`). There is no table of checksums and no scan of the code. **Firmware:** C-BIOS 0.29a's MSX2+ images (main ROM, logo, and the MSX2 sub-ROM), from the same pinned archive as the MSX1's
and MSX2's, or your own MSX2+ BIOS pair (the main ROM, byte 2Dh = 2, and its 16 KiB sub-ROM), chosen in Options > MSX2+ and never shipped.

**The V9958, as written from Yamaha's V9958 technical data and the MSX2+ technical documents:** R#25 (CMD, VDS, YAE, YJK, WTE, MSK, SP2), R#26
and R#27 (the horizontal scroll: R#26 moves the picture left in 8-dot steps, R#27 back right by 0 to 7 dots; SP2 shows two pages side by side;
MSK covers the left 8 dots with the border), the ID 2 in S#1, YJK and YJK+YAE in Graphic 7 (15-bit colours: R = Y + J, G = Y + K,
B = (5Y - 2J - K) / 4 rounded down, each clipped to 0-31; with YAE a byte with bit 3 set shows the palette colour of its bits 7-4), and the
command engine in every screen mode with CMD (as Graphic 7). Sprites do not scroll; in the YJK modes they take the palette's colours. Port F4h
is a latch, 00h at power-on.

**Not modelled:** WTE's wait states (no access slots here), the VDS pin, the horizontal scroll in the text modes. **Not yet:** MSX-MUSIC
(YM2413), the kanji ROM, cassettes, disks on the MSX1 and MSX2 profiles.

### Disks (13 November 2026, branch `spec/msx2plus-disk-174`)

**Converted:** an MSX2+ disk game, from a `.dsk` (720 KiB double-sided or 360 KiB single-sided) or a set of one to ten `.dsk` files. A set is
grouped as the Atari ST's and the X68000's are (`rom_sources.disk_sets`, shared: names that differ only by "Disk 1", "Disk 2"...), into an M3U
whose first line marks the machine (`# Retro-Recomp system: msx2plus`). A `.dsk` is the MSX2+'s wherever it sits (no other machine of the
converter reads `.dsk`); an MSX1 or MSX2 disk game therefore goes to the MSX2+ too (only MSX2+ games were on the panel).
The disks are embedded in the game, in order; the game boots from the first.

**Firmware:** a disk game needs **your own** MSX2+ BIOS pair and **your own** disk ROM (16 KiB starting with "AB", chosen in Options > MSX2+
disk ROM): C-BIOS has no disk ROM, and none is shipped. The panel used one machine's firmware (Panasonic FS-A1WSX: main ROM, sub-ROM, disk ROM).

**The disk interface, our own code** (`native/msx_machine/msx_fdc.c`, MIT): the TC8566AF with the uPD765 command set, one drive, in slot 2
page 1 with the disk ROM, registers at 7FF8h-7FFBh (mirrored at BFF8h). The addresses and the commands were read from MAME's MSX disk
interface (BSD-3) as documentation only; no line is copied. There are no rotation or seek delays: a command ends when the program reads its
result. The disk ROM is Z80 code like the game's and is translated with it; the report names the disk interface in the cartridge's place.

**What a game writes:** the embedded disks never change. A written disk is copied beside the game's settings
(`datas/games/msx2plus-<id>/disk-N.dsk`) a few seconds after the last write and at exit, and is read back the next time the game starts; a copy
of the wrong size is ignored and left as it is. **Disk change:** Page Up / Page Down, with the same notices as the Atari ST; the long routes of
a multi-disk game insert the next disk at frame 6,000 and then every 3,000 frames (the play route never changes disk). Quick states include
the controller and the disk in the drive.

**The disk panel (13 November 2026, extended level, two conversions at a time, online covers on):** Arc, Quinpl, Nyancle Racing, Sonyc
(one disk each), Laydock 2 - Last Attack, F-1 Spirit 3D Special, Golvellius II, Xak III - The Tower of Gazzel (several disks). On all eight,
0 interpreted Z80 instructions on attract, play and the long route (18,000 frames), each equal to its fresh reference and to the packed file,
quick states passing in fresh processes. Where the long routes get: Arc, Quinpl, Laydock 2 and F-1 Spirit 3D Special play (F-1's attract and
play look alike, and its dashboard digits were not checked); Nyancle Racing enters a name and races; Sonyc plays a stage, then waits on its
password screen; Golvellius II stays in its Japanese intro; Xak III shows its intro, then asks for disk 3 ("SET DISK 3 AND PUSH SPACE
PLEASE"), which the route's fixed disk changes do not answer. Xak III showed no sign of needing the kanji ROM on its routes; what its later
screens need is not known. Covers: Quinpl and Xak III found one (libretro); the other six have none.

**Writes, proven on an authored disk:** no panel game writes to its disks on its routes. `tools/msx_write_disk.py` builds a 720 KiB disk of
our own (an MSX-DOS boot sector, no game data) whose boot program refuses the MSX-DOS boot call, hooks H.STKE and, once BASIC has started,
writes one 512-byte pattern to sector 20 through PHYDIO. Converted as a game (0 interpreted instructions), it writes; the copy kept beside the
game differs from the image in sector 20 only, which holds the pattern, every other byte identical; a fresh process starts from the copy, and a
copy of the wrong size is ignored. A first version wrote 256 sectors: it wrote from the MSX-DOS boot call, where page 0 is RAM, so its
`CALL 0144h` ran RAM instead of PHYDIO (traced: the call never passed the H.PHYD hook). The controller wrote exactly what the disk ROM sent it,
one WRITE command a sector, each ended by the terminal count. `tools/msx_fdc_selftest.py` checks the controller alone (21 checks, needs a C
compiler): one sector asked, one written and the rest of the image unchanged; up to EOT; past EOT without terminal count; write protection; a
sector off the track; a stray byte in the result phase; a read.

**First comparison, and an open difference (13 November 2026).** Family Stadium Professional Baseball slides its title in with the
horizontal scroll (R#25 = 3, R#26 from 0 to 32, ending at R#26 = 32, R#27 = 4); openMSX 22.0 (a private comparison emulator run as a separate
program, never shipped) with its C-BIOS MSX2+ machine shows the same slide and the same final values, about 60 frames later (its boot is
longer). Open: after the slide openMSX's R#1 has the line interrupt off (42h) and ours keeps it on (62h). openMSX's C-BIOS MSX2+ machine also
has MSX-MUSIC, which ours does not yet, and that can change the game's path; the cause is not proven.

**The five measures:** native code: 0 interpreted Z80 instructions on the 24 routes of the disk panel (the first conversion of each game
learns its paths: between 0 and 40.5 million interpreted instructions in that pass, none after). CPU fidelity: each route equals a fresh
run of the reference (the same Z80 interpreter on the same machine model), not real hardware. Hardware fidelity: not validated (the V9958, the
PSG and the disk controller are C models; one openMSX comparison, above). Gameplay: bounded pad routes, not full games. Physical latency: not
measured. The `msx2plus` column of [QUALIFICATION.md](QUALIFICATION.md) has the letters and their evidence.
