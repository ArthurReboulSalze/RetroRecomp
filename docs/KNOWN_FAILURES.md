# Games that do not convert

Games known to fail to convert, or to be refused, with what was tried. A game listed here was investigated; it is
not a claim about any other game, and a game absent from this page is not proven to work (see
[COMPATIBILITY.md](COMPATIBILITY.md)). Each machine's specialist keeps its section current.

Kinds of entry:

- **Failing**: the conversion stops or the export does not run, and the cause is not found yet (investigation open).
- **Set aside**: investigated at length without a result (possibly a bad dump); kept here so it is not rediscovered.
- **Refused by design**: outside the supported scope of the machine (a coprocessor, a board or a medium not handled);
  the converter says so and stops.
- **Delivered unpacked**: the conversion succeeds and every route is validated, but the compressed copy cannot be
  delivered on one system; the game is published as built, a larger file, with the reason in the report.

Games that convert but run part of their code in the counted interpreter are not listed here: their reports show the
counts (the five measures stay separate: native code, CPU fidelity, hardware fidelity, gameplay validation, latency).

| Machine | Game (set or title) | Kind | What happens | What was tried | Since |
|---|---|---|---|---|---|
| Game Boy | Game Boy Color-only cartridges (header flag `0xC0`) | Refused by design | The converter refuses the cartridge (the profile is DMG only); Color-compatible cartridges are accepted and run as DMG | Outside the machine's scope | 0.12.0 |
| Game Boy | Test ROM blargg `oam_bug` `7-timing_effect` (first version of the ROM) | Failing (lockstep) | The lockstep comparison stops at step 6,717,022 (about 784 frames): the generated code is one four-cycle step behind the interpreter (PC `$2154`, SP `$C0A6` against PC `$0038`, SP `$C0A4`). The program fetches instructions from the ROM while an OAM DMA transfer is under way: the interpreter reads `$FF` there (its model of the bus conflict) and runs `RST $38`, the generated code runs the translated instruction. The second version of the ROM matches for 10,800 frames | Cause of the difference found (4 November 2026); not corrected: on a console a fetch from the bus the transfer uses would read the transfer's bytes, not the code (a program that did so has left its path; the interpreter's `$FF` is a model too), and the check would cost a test on every instruction fetch. Why the test leaves its path first is not known ([GAME_BOY.md](GAME_BOY.md#the-public-test-roms-of-blargg-and-mooneye-167-gates-g10-and-g11)) | 3 November 2026 |
| Game Boy | Test ROM blargg `oam_bug` `7-timing_effect` (both versions) | Failing (no verdict) | No verdict in 10,800 frames (three minutes of game time); a blank screen | Derails before the end (see the row above); not investigated further | 3 November 2026 |
| Game Boy | Test ROMs blargg `dmg_sound` `09-wave read while on`, `10-wave trigger while on` and `12-wave write while on` (both versions, 6 of 24) | Failing | The wave RAM read, written or triggered while the channel plays does not return the byte the channel reads at that cycle (a two-clock window): the wave channel runs on the sample clock of the audio unit, not by cycle. 1.6.8 made the other 18 of the 24 pass and the two boot-state tests of Mooneye | Rules of the power switch, the length clock and the sweep added in 1.6.8 (the sound unit is the upstream's); a cycle-exact wave channel is not attempted, no game of the campaign shows it ([GAME_BOY.md](GAME_BOY.md#the-public-test-roms-of-blargg-and-mooneye-167-gates-g10-and-g11)) | 3 November 2026 |
| Atari ST | Kick Off 2 | Failing | It converts, then stops on « Master file not present or damaged », with TOS 1.04 and with EmuTOS. The same disk read as plain sectors reaches its title screen | Two independent renderings of its protected tracks (Hatari's IPF reader and the SPS decoder library) give the same flux, so the cause is in how Hatari's WD1772 model reads the two 1024-byte protection sectors of cylinders 2 to 6; investigation capped on 7 November 2026 ([ATARI_ST.md](ATARI_ST.md#5-known-limits)) | 7 November 2026 |
| Atari ST | Turrican II, with EmuTOS | Failing | It stops after its Rainbow Arts intro: it uses low memory that EmuTOS also uses (EmuTOS's own list says « this can never work with EmuTOS ») | It runs with the player's own TOS 1.04, which the conversion accepts as an option; the report says on every EmuTOS conversion that a game written for Atari's TOS may need it ([ATARI_ST.md](ATARI_ST.md#5-known-limits)) | 7 November 2026 |
| Mega Drive | Virtua Racing (USA) | Refused by design | The cartridge declares the SVP coprocessor (`SV` at `$1C8`), not handled; the conversion stops before compiling | Nothing to try on the 68000 or Z80 side: the SVP is a capability of its own | 24 October 2026 |
| NES | Famicom Disk System images | Refused by design | Disk images are not a supported medium ([NES.md](NES.md)) | Outside the machine's scope; the upstream's FDS work is deferred ([UPSTREAMS.md](UPSTREAMS.md#deferred)) | Always |
| Super Nintendo | SPC7110 (Super Power League 4) | Refused by design | SPC7110 chip, not handled | Outside the current scope | Always |
| Super Nintendo | DSP-2 and DSP-4 (Dungeon Master, Top Gear 3000) | Refused by design | Only the DSP-1 is modelled | Outside the current scope | Always |
| Super Nintendo | Other chips, 4 (F1 ROC II, Metal Combat, Villgust) | Refused by design | Chip types `$F6` and `$25` and others, not handled | Outside the current scope | Always |
| Super Nintendo | A 6 MiB LoROM-header image (Wizardry VI) | Refused by design | Above 4 MiB with a map that is neither ExHiROM nor an S-DD1 board; no reliable mapping is known | Outside the current scope | 3 November 2026 |
| Super Nintendo | Headers with a zero checksum that fail the other checks (a damaged dump, a header that only looks filled in) | Refused by design | The header check wants a checksum, or an unset one with a regular map byte, a size that fits the image and a plausible reset instruction | The four such cartridges of the library that pass those checks convert since 1.6.7 | 29 October 2026, rule 3 November 2026 |
| Neo Geo | Fight Fever (`fightfev`) | Failing (bad input) | The conversion stops at once: the split cartridge needs a separate parent archive for `060-s1.s1` | The test archive's `060-s1.s1` has CRC `7f012104` instead of the expected `d62a72e9`, and the parent is absent: another dump should convert (not tried) | 24 October 2026, confirmed 29 October 2026 |
| Capcom CPS-1 | Rotary-dial boards, 10 sets (`forgottn`, `lostwrld` and clones) | Refused by design | The rotary dial controller is not handled | Refused by the catalogue; no conversion tried | 24 October 2026 |
| Capcom CPS-1 | Pang! 3 (`pang3`, `pang3r1`, `pang3j`) | Refused by design | Serial EEPROM and encrypted graphics, not handled | Refused by the catalogue | 24 October 2026 |
| Capcom CPS-1 | Ganbare! Marine Kun (`ganbare`) | Refused by design | Timekeeper RAM and raster interrupt, not handled | Refused by the catalogue | 24 October 2026 |
| Capcom CPS-1 | CPS Changer cartridges (`wofch`, `sfzch`, `sfach`, `sfzbch`) | Refused by design | Home-console cartridges, outside the arcade scope | Refused by the catalogue | 24 October 2026 |
| Capcom CPS-1 | Street Fighter II World 910228 (`sf2ee`, `sf2ue`) | Refused by design | This revision needs a board-specific start-up, not handled | Refused by the catalogue; `sf2`, `sf2hf` and `sf2ce` convert | 24 October 2026 |
| Capcom CPS-1 | Gamushara Battle! Puchi Monster (`pmonster`) | Refused by design | Marked not working in the reference description | Refused by the catalogue | 24 October 2026 |
| Capcom CPS-1 | Bootlegs and hacks, 65 sets (for example `sf2ebbl`, `sf2rb`, `3wondersb`, `dinohunt`) | Refused by design | « Bootleg and modified sets are outside the supported CPS-1 scope » | Refused by the catalogue; the originals convert | 24 October 2026 |
| Sharp X68000 | Hard-disk and SCSI/SASI images | Refused by design | The profile accepts floppy media only (`.dim`, `.xdf`, `.d88`, `.m3u`) | Documented limit of [X68000.md](X68000.md) | 1.1.9 |
| Sharp X68000 | Sets of more than ten disks | Refused by design | The set is left as separate files, not queued as one game | Documented limit | 1.3.0 |
| Sharp X68000 | Choujin (Fix), on Debian only | Delivered unpacked | The UPX-compressed game stops at start (SIGTRAP, exit 133) on Debian 13, with UPX 5.3.0 at `-9`, `-1` and `--lzma`, while `upx -t` passes and the unpacked program (the same bytes after `upx -d`) runs. Since 1.6.7 the shared packing step replays the compressed copy twice, sees the build pass every route, and publishes the build as built: the conversion succeeds, the file is 9.5 MB unpacked, `packing.packed` is false and `packing.unpacked_reason` says why. Windows delivers it compressed | Repeated, with and without address randomisation, on the file kept by the failed conversion; not a disk fault. Debian with `--no-compress` and the fallback both give the same CPU, RAM, picture and PCM hashes as Windows (fallback run on main at 1aa7ddd, 3 November 2026: published file byte for byte the validated build, `native_validation.packed_reference_match` true). Cause found on 9 November 2026: a bug of UPX 5.3.0's 64-bit Linux stub, upx/upx#18967. When the executable segment ends within 11 bytes of a page's end (0, or 4086 to 4095, modulo 4096, about 0.27 % of builds), the stub calls a routine that was never linked in and reaches a breakpoint. Reproduced with a small program with no game in it and read in two Nintendo 64 crash dumps, so any game on Linux can meet it; this X68000 file is no longer at hand, so it is only consistent with that cause. Fixed upstream (pull request 18968), in no release yet: the fallback stays until a UPX release carries the fix | 2 November 2026 |

## Taken off this page

- **Capcom CPS-1, the QSound boards** (18 sets: `wof`, `dino`, `punisher`, `slammast`, `mbomberj` and their clones; 2 November 2026, release 1.6.7). Listed as refused by design (« not supported yet: qsound »): they are no longer refused. They form the CPS-1.5 tier, which left the experimental status on 5 November 2026 (the owner's decision), and need your own QSound DSP ROM (`dl-1425.bin`, or the `qsound.zip` that holds it) chosen in Options → Capcom CPS-1; the Z80 program is decrypted (Kabuki) and the DSP16 is a high-level model after MAME's, not a run of the DSP16 program. The five sets of the test collection convert at the Standard level (5 of 5, 0 interpreted 68000 and Z80 instructions on both routes); the other sets were not converted here ([CPS1.md](CPS1.md#cps-15-qsound-boards)). Only the CPS Changer cartridge sets stay refused.
- **Super Nintendo, Dragon Quest III and Tales of Phantasia** (ExHiROM, 6 MiB; the English translations of the library, 3 November 2026, release 1.6.7). Listed as refused by design ("map mode not handled"): the ExHiROM map is now in the bus and the loader ([SNES.md](SNES.md)). Both convert with zero interpreted opcodes, the compressed copy equal to the reference, and show the game's first menu and its title screen at 2,500 frames. Only what the routes reach is claimed. The Japanese-translated file of Tales of Phantasia in the library has a header the converter cannot validate and is still refused.
- **Super Nintendo, Star Ocean** (S-DD1, 6 MiB; both translations of the library, 3 November 2026, release 1.6.7). Listed as failing since 1.6.6: it converted and then stayed on a black screen. The cartridge RAM decoding served banks $F0-$FF as battery RAM, where an S-DD1 board has the ROM windows of the chip (its RAM is in banks $70-$73); the S-DD1 board now has its own clause (`native/snes_cart.h`), and the S-DD1 cartridges may be up to 8 MiB. Same conversion with the old and the narrow clause, same 2,500 frames: 1 decompression session and a black picture before, 1,240 sessions and the title menu after. Only what the routes reach is claimed ([SNES.md](SNES.md)).
- **Super Nintendo, the SA-1 cartridges and Street Fighter Alpha 2** (1 November 2026, release 1.6.6). The SA-1 (map `$23`, chip type `$34` or `$35`) and the S-DD1 (map `$32`, chip type `$43` or `$45`, up to 4 MiB) are no longer refused: the SA-1 core runs as a counted interpreted device, the S-DD1 as a command model ([SNES.md](SNES.md)). Only the SA-1 cartridges named in [SNES.md](SNES.md) have been played; the others are recognised, not proved. Star Ocean stays listed above.
- **NES, Dragon Warrior IV** (29 October 2026). Listed as set aside the same day, then found: the conversion itself succeeds
  (9 min 27 s, zero interpreted cycles on the final paths); what stopped it was the fixed 120-second limit of the UPX packing of
  its large executable while other conversions shared the CPUs. Since 1.6.5 the limit grows with the file
  ([UPGRADES.md](UPGRADES.md)).
- **Neo Geo, Last Hope** (29 October 2026). Its 64 KiB fixed-graphics ROM is now repeated to 128 KiB when the cartridge is
  assembled, as the chip does; it converts with zero interpreted opcodes.
- **Super Nintendo, Duel/Test Drive II and the Popeye translation** (29 October 2026). Their map-mode byte `$32` with no chip
  is now read as an ordinary LoROM.
- **Sharp X68000, Tetris v5 and TF4G v0.3A09** (29 October 2026). Both crashed the reference on a first start when the game
  reprogrammed the CRTC during a machine line: a line made visible before it was drawn indexed the line tables with the
  "no line" marker. The line is now taken from the CRTC as it is then (`native/x68000_machine/glue_line.h`); both convert with
  zero interpreted opcodes.
- **Mega Drive, Boxing Legends of the Ring and Dragon's Revenge** (29 October 2026). Both execute the 68000 `RESET` instruction
  early; it is now executed natively in supervisor mode (PC + 2, 132 clocks; on the Mega Drive it only pulses the cartridge
  reset line). Both convert with zero interpreted 68000 and Z80 instructions.
- **Super Nintendo, the seven DSP-1 HiROM cartridges** (map mode `$31`, chip type `$03`: Lock On, Super Air Diver 2, Suzuka
  8 Hours and others, 29 October 2026). They are recognised like Super Mario Kart's board; Lock On converts with zero
  interpreted 65816 and SPC700 instructions.
- **Sharp X68000, Pensan CD** (29 October 2026). It was refused for having no sound on its routes. It is silent only on the
  routes without the mouse (a click starts its music: 4.39 million non-zero samples on the mouse route); since 1.6.5 a silent
  X68000 route is accepted and reported, and the game converts with zero interpreted opcodes.
- **Game Boy, Paperboy 2** (29 October 2026). Replayed alone on the 1.6.5 tree, it converts in 152 seconds with zero interpreter
  cycles; the 600-second probe limit it hit in the October campaign no longer applies.
- **Super Nintendo, `.fig` copier dumps** (30 October 2026). A `.fig` file whose size is whole 32 KiB blocks after a 512-byte
  copier header is now read as a Super Nintendo cartridge (an interleaved image is refused with its reason); Mario no Super
  Picross converts with zero interpreted instructions.
- **Game Boy, The Ren & Stimpy Show: Veediots!** (30 October 2026). It turns the screen off and waits; a frame only ended at
  vblank, so no frame ended again. While the LCD is off a frame now ends after 70,224 cycles (a host frame: the emulated
  state does not change); it converts with zero interpreter cycles.
- **Mega Drive, Barkley Shut Up and Jam!** (30 October 2026). It requests the sound CPU's bus and tests the grant once;
  the grant is now dated at the end of the sound CPU's current machine cycle (it came one slice late), and it converts.
- **Game Boy, Spiritual Warfare** (1 November 2026). Its unlicensed Wisdom Tree mapper (one latch switching the whole
  32 KiB window, the bank taken from the write address) is now modelled; the five Wisdom Tree cartridges convert.
