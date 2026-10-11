# Mega Drive serial EEPROM

RetroRecomp implements an original wire model for X24C01, X24C02 and 24C04,
with Sega, Acclaim 16 Mbit and Acclaim 32 Mbit cartridge wiring. Board selection
uses the internal product and actual save header in `megadrive_hardware.py`.
Unknown serial boards retain an explicit limitation. A parallel-SRAM replacement
does not qualify the original EEPROM board. These qualified circuits are part
of the supported standard profile; see [compatibility scope](COMPATIBILITY.md).

## Protocol and primary evidence

The [original Xicor X24C01 datasheet](https://datasheet.octopart.com/X24C01P-Intersil-datasheet-181540502.pdf)
specifies a seven-bit memory address followed by R/W, without a separate device
address byte: 128 bytes and four-byte page writes. The
[original Xicor X24C02 datasheet](https://docs.rs-online.com/d895/0900766b80029b1c.pdf)
specifies a device-selection byte, word address, 256 bytes and **four-byte** page
writes. The [ST M24C04 documentation](https://www.st.com/en/memories/m24c04-w.html)
supplies the 512-byte, sixteen-byte-page command family, with the high address
bit in the device byte. Capacity alone does not select a protocol.

`native/md_eeprom.h` implements MSB-first transmission, open-drain SDA, START,
STOP, repeated START, the ninth ACK clock, master ACK/NACK, page wrap and
sequential-read wrap. A STOP starts a staged write; busy polling returns NACK.
Programming takes a deterministic **5 ms in guest master clocks**. The Xicor
typical/max figures are 5/10 ms: this software choice is not a measurement of
each cartridge's physical write delay. Host wall time does not drive the chip.

The [published Genesis Plus GX circuit catalogue](https://github.com/ekeeke/Genesis-Plus-GX/blob/master/core/cart_hw/eeprom_i2c.c)
supplies board/product and lane facts. No serial implementation code was imported.
`native/md_cart.inc` connects the independent chip to actual 68000 byte/word and
banked Z80 accesses. Sega uses the odd-byte lane, SCL D1 and SDA D0. Acclaim
16 Mbit returns SDA on D1; Acclaim 32 Mbit separates clock/data by byte lane
and uses a word write to select ROM or EEPROM reads. EEPROM is not exposed as
parallel SRAM, nor enabled by the SRAM control register.

## Persistence and portable states

Committed bytes use the existing exact-ROM battery container in the console's
`datas` directory. Reads and normal launch create no directories or logs.
A cartridge that actually formats/writes its EEPROM may create a battery file
at shutdown, even if the player never invokes F8. Replacement is atomic.
F1 resets the serial interface and retains committed nonvolatile bytes.

ABI-11 includes the pointer-free chip phase, clock/data levels, address, staged
page and remaining guest-clock programming interval. F8/F9 can resume a busy
write in another process. The complete payload is checked before mutation;
invalid geometry, phases, addresses or intervals are rejected. Prior supported
ordinary-cartridge states migrate explicitly. Previously unsupported EEPROM
cartridges cannot load an old ordinary-SRAM state as though it were serial.

## Reproducible qualification

- `tools/megadrive_eeprom_selftest.py`: 1,238,968 independently authored protocol
  assertions, all addresses and both PAL/NTSC clocks, plus actual bus wiring
  checks (114 / 143 / 147 for the three families), clean launch and restart.
- `tools/megadrive_eeprom_state_selftest.py`: actual production objects,
  in-flight F8/F9, malformed-state rejection, atomic battery restart and reset.
  The original Wily Wars formats 64 pages on the first blank-battery boot and
  performs no new writes on the second boot with that battery. Its fixture
  has 1,527 checks; each Acclaim fixture has 388. Malformed receive states and
  an impossible eighth read bit with SCL low are rejected before mutation.
- Original supplied Wily Wars, NBA Jam and NBA Jam Tournament Edition run
  through normal advanced conversion: five scenarios per exact ROM, strict
  decoded-CPU/memory/image/PCM comparison before learning. Final scenarios have
  zero main/sound interpreter entries. Evidence remains local in
  `.build/md-cartridge-hardware-20261011/`.

The real Wily Wars battery boot and protocol fixtures establish persistence;
they do not establish completion of the game's save-menu progression. Native
coverage, shared-hardware CPU comparisons, independent circuit fixtures,
human gameplay and physical latency remain separate evidence. Other wiring
families and cartridge revisions require their own identification and tests.
