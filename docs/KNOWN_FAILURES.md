# Games that do not convert

Games known to fail to convert, or to be refused, with what was tried. A game listed here was investigated; it is
not a claim about any other game, and a game absent from this page is not proven to work (see
[COMPATIBILITY.md](COMPATIBILITY.md)). Each machine's specialist keeps its section current.

Kinds of entry:

- **Failing**: the conversion stops or the export does not run, and the cause is not found yet (investigation open).
- **Set aside**: investigated at length without a result (possibly a bad dump); kept here so it is not rediscovered.
- **Refused by design**: outside the supported scope of the machine (a coprocessor, a board or a medium not handled);
  the converter says so and stops.

Games that convert but run part of their code in the counted interpreter are not listed here: their reports show the
counts (the five measures stay separate: native code, CPU fidelity, hardware fidelity, gameplay validation, latency).

| Machine | Game (set or title) | Kind | What happens | What was tried | Since |
|---|---|---|---|---|---|
| Game Boy | Spiritual Warfare (Unl) | Failing | The start-up probe never ends (100 % CPU); the export finishes frame 1 then runs into illegal code (thousands of `0xDD` opcodes) | Replayed alone on 29 October 2026: reproducible. The header says "ROM only, 32 KiB" for a 256 KiB file: an unlicensed custom mapper is likely, not proven | 10 October 2026 |
| Game Boy | The Ren & Stimpy Show: Veediots! | Failing | The probe with inputs hangs between frames 215 and 216: the game turns the screen off and never back on, and a frame only ends at VBlank, so no frame ends again | Replayed alone on 29 October 2026: reproducible and deterministic. A general fix is planned: end a frame after 70,224 cycles while the screen is off | 10 October 2026 |
| Game Boy | Game Boy Color-only cartridges (header flag `0xC0`) | Refused by design | The converter refuses the cartridge (the profile is DMG only); Color-compatible cartridges are accepted and run as DMG | Outside the machine's scope | 0.12.0 |
| Mega Drive | Virtua Racing (USA) | Refused by design | The cartridge declares the SVP coprocessor (`SV` at `$1C8`), not handled; the conversion stops before compiling | Nothing to try on the 68000 or Z80 side: the SVP is a capability of its own | 24 October 2026 |
| Mega Drive | Barkley Shut Up and Jam! (USA) | Failing (cause found) | After 42 frames the game jumps to `$0000`: at `$EB8` it requests the Z80 bus (`MOVE.W #$0100,$A11100`), tests the grant once (`BTST #0,$A11100`, `BNE.W` to `$0000`) and assumes it at once; our bus arbiter grants it one slice late (about 188 master clocks instead of at most about 90) | Real code, not data read as code; traced to the slice approximation of `native/md_z80_bus.inc` (not proven). A dedicated arbiter change is planned (authored reproducer first, then a 13-game A/B) | 24 October 2026, cause found 29 October 2026 |
| NES | Famicom Disk System images | Refused by design | Disk images are not a supported medium ([NES.md](NES.md)) | Outside the machine's scope; the upstream's FDS work is deferred ([UPSTREAMS.md](UPSTREAMS.md#deferred)) | Always |
| Super Nintendo | SA-1 cartridges, 15 (for example Super Mario RPG, Kirby Super Star, Kirby's Dream Land 3) | Refused by design | The SA-1 coprocessor is not handled; the converter names it and stops | Outside the current scope | Always |
| Super Nintendo | S-DD1 cartridges, 3 (Star Ocean, Street Fighter Alpha 2) | Refused by design | S-DD1 decompression chip, not handled | Outside the current scope | Always |
| Super Nintendo | SPC7110 (Super Power League 4) | Refused by design | SPC7110 chip, not handled | Outside the current scope | Always |
| Super Nintendo | DSP-2 and DSP-4 (Dungeon Master, Top Gear 3000) | Refused by design | Only the DSP-1 is modelled | Outside the current scope | Always |
| Super Nintendo | Other chips, 4 (F1 ROC II, Metal Combat, Villgust) | Refused by design | Chip types `$F6` and `$25` and others, not handled | Outside the current scope | Always |
| Super Nintendo | ExHiROM or more than 4 MiB, 4 (Dragon Quest III, Tales of Phantasia, Wizardry VI) | Refused by design | Map mode not handled | Outside the current scope | Always |
| Super Nintendo | Headers with a zero checksum (Power Drive Europe and four prototypes) | Refused by design | The header check wants a non-zero checksum | A specific rule is possible, not made | 29 October 2026 |
| Neo Geo | Fight Fever (`fightfev`) | Failing (bad input) | The conversion stops at once: the split cartridge needs a separate parent archive for `060-s1.s1` | The test archive's `060-s1.s1` has CRC `7f012104` instead of the expected `d62a72e9`, and the parent is absent: another dump should convert (not tried) | 24 October 2026, confirmed 29 October 2026 |
| Capcom CPS-1 | QSound boards, 18 sets (`wof`, `dino`, `punisher`, `slammast`, `mbomberj` and their clones) | Refused by design | « not supported yet: qsound » (Kabuki-encrypted Z80 and QSound DSP not handled) | `wof` converted on 29 October 2026: refused with its reason; the others are refused by the catalogue | 24 October 2026 |
| Capcom CPS-1 | Rotary-dial boards, 10 sets (`forgottn`, `lostwrld` and clones) | Refused by design | The rotary dial controller is not handled | Refused by the catalogue; no conversion tried | 24 October 2026 |
| Capcom CPS-1 | Pang! 3 (`pang3`, `pang3r1`, `pang3j`) | Refused by design | Serial EEPROM and encrypted graphics, not handled | Refused by the catalogue | 24 October 2026 |
| Capcom CPS-1 | Ganbare! Marine Kun (`ganbare`) | Refused by design | Timekeeper RAM and raster interrupt, not handled | Refused by the catalogue | 24 October 2026 |
| Capcom CPS-1 | CPS Changer cartridges (`wofch`, `sfzch`, `sfach`, `sfzbch`) | Refused by design | Home-console cartridges, outside the arcade scope | Refused by the catalogue | 24 October 2026 |
| Capcom CPS-1 | Street Fighter II World 910228 (`sf2ee`, `sf2ue`) | Refused by design | This revision needs a board-specific start-up, not handled | Refused by the catalogue; `sf2`, `sf2hf` and `sf2ce` convert | 24 October 2026 |
| Capcom CPS-1 | Gamushara Battle! Puchi Monster (`pmonster`) | Refused by design | Marked not working in the reference description | Refused by the catalogue | 24 October 2026 |
| Capcom CPS-1 | Bootlegs and hacks, 65 sets (for example `sf2ebbl`, `sf2rb`, `3wondersb`, `dinohunt`) | Refused by design | « Bootleg and modified sets are outside the supported CPS-1 scope » | Refused by the catalogue; the originals convert | 24 October 2026 |
| Sharp X68000 | Hard-disk and SCSI/SASI images | Refused by design | The profile accepts floppy media only (`.dim`, `.xdf`, `.m3u`) | Documented limit of [X68000.md](X68000.md) | 1.1.9 |
| Sharp X68000 | Sets of more than ten disks | Refused by design | The set is left as separate files, not queued as one game | Documented limit | 1.3.0 |

## Taken off this page

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
