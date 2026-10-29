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
| Game Boy | Paperboy 2 | Failing | The discovery probes reach their 600-second limit; nothing is added to the shared knowledge and the game is not qualified | Bank-boundary, RAM-helper and selector fixes of the same campaign did not help; cause (CPU, mapper or other) not found. Not replayed since 1.6.4 | 10 October 2026 |
| Game Boy | Spiritual Warfare | Failing | Same symptom: probes at the 600-second limit, game not qualified | Same attempts; not replayed since 1.6.4 | 10 October 2026 |
| Game Boy | The Ren & Stimpy Show: Veediots! | Failing | Same symptom: probes at the 600-second limit, game not qualified | Same attempts; not replayed since 1.6.4 | 10 October 2026 |
| Game Boy | Game Boy Color-only cartridges (header flag `0xC0`) | Refused by design | The converter refuses the cartridge (the profile is DMG only); Color-compatible cartridges are accepted and run as DMG | Outside the machine's scope | 0.12.0 |
| Mega Drive | Virtua Racing (USA) | Refused by design | The cartridge declares the SVP coprocessor (`SV` at `$1C8`), not handled; the conversion stops before compiling | Nothing to try on the 68000 or Z80 side: the SVP is a capability of its own | 24 October 2026 |
| Mega Drive | Boxing Legends of the Ring (USA) | Failing | The game reaches the 68000 `RESET` instruction, whose board wiring is not modelled, and the conversion stops | Cause found in the 24 October campaign ([MEGADRIVE.md](MEGADRIVE.md), known limits); no `RESET` emulation tried. Not replayed on 1.6.5 | 24 October 2026 |
| Mega Drive | Dragon's Revenge (USA) | Failing | Same cause: the `RESET` instruction is reached | Same; no `RESET` emulation tried. Not replayed on 1.6.5 | 24 October 2026 |
| Mega Drive | Barkley Shut Up and Jam! (USA) | Failing | An opcode the decoder does not accept is reached in the cartridge header area, and the conversion stops | Located in the 24 October campaign; whether it is real code or data read as code is not checked. Not replayed on 1.6.5 | 24 October 2026 |
| NES | Famicom Disk System images | Refused by design | Disk images are not a supported medium ([NES.md](NES.md)) | Outside the machine's scope; the upstream's FDS work is deferred ([UPSTREAMS.md](UPSTREAMS.md#deferred)) | Always |
| Super Nintendo | SA-1 cartridges, 15 (for example Super Mario RPG, Kirby Super Star, Kirby's Dream Land 3) | Refused by design | The SA-1 coprocessor is not handled; the converter names it and stops | Outside the current scope | Always |
| Super Nintendo | S-DD1 cartridges, 3 (Star Ocean, Street Fighter Alpha 2) | Refused by design | S-DD1 decompression chip, not handled | Outside the current scope | Always |
| Super Nintendo | SPC7110 (Super Power League 4) | Refused by design | SPC7110 chip, not handled | Outside the current scope | Always |
| Super Nintendo | DSP-2 and DSP-4 (Dungeon Master, Top Gear 3000) | Refused by design | Only the DSP-1 is modelled | Outside the current scope | Always |
| Super Nintendo | DSP-1 on HiROM boards other than Super Mario Kart's, 7 (for example Lock On, Super Air Diver 2, Suzuka 8 Hours) | Refused by design | Header `$31` with chip type `$03`: only the Super Mario Kart HiROM signature and the LoROM DSP-1 are recognised | Extending the recognised signatures is possible, not tried | 29 October 2026 |
| Super Nintendo | Other chips, 4 (F1 ROC II, Metal Combat, Villgust) | Refused by design | Chip types `$F6` and `$25` and others, not handled | Outside the current scope | Always |
| Super Nintendo | ExHiROM or more than 4 MiB, 4 (Dragon Quest III, Tales of Phantasia, Wizardry VI) | Refused by design | Map mode not handled | Outside the current scope | Always |
| Super Nintendo | `.fig` copier dumps (4 seen) | Refused by design | The file type is not read (`.sfc`, `.smc`, `.bin` and `.rom` only) | Renaming to `.smc` after checking the dump is not interleaved should work; not tried | 29 October 2026 |
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
| Sharp X68000 | Tetris v5 (1991, Cyber Factory) | Failing | Start-up error on the interpreted reference, so no conversion can start | Seen in the survey of the 378 test-collection entries; cause not investigated yet | 24 October 2026 |
| Sharp X68000 | Pensan CD (Tanaka Yuu) | Failing | Same start-up error on the reference | Same survey; not investigated yet | 24 October 2026 |
| Sharp X68000 | TF4G v0.3A09 (1993, TNB Saisakusho) | Failing | Same start-up error on the reference (the v0.6426 version of the same title is not affected) | Same survey; not investigated yet | 24 October 2026 |
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
