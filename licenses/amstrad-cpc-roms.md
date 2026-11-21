# Amstrad CPC firmware (Amstrad, Locomotive Software)

An Amstrad CPC game converted by Retro-Recomp runs on the CPC's own firmware: it is started from BASIC, calls the firmware's
routines and runs its interrupt handler ([AMSTRAD_CPC.md](../docs/AMSTRAD_CPC.md)). The game therefore holds the CPC 6128's
system ROM (the operating system and Locomotive BASIC) and the AMSDOS disk ROM, translated with the game's code.

**The Amstrad CPC ROMs are copyright Amstrad. Amstrad have kindly given their permission for the redistribution of their
copyrighted material but retain that copyright.** The ROM code is not sold: Retro-Recomp and the games it converts are free, and
no charge is made for the ROMs. Their copyright messages are kept unaltered.

* **The permission.** In 1999 Cliff Lawson of Amstrad plc, in public statements to the comp.sys.amstrad.8bit and
  comp.sys.sinclair newsgroups, allowed emulator authors to include images of Amstrad's ROMs, provided that their copyright
  messages are not altered and that no charge is made for the ROM code. Amstrad plc now belongs to Sky; no later statement
  withdrawing the permission is known.
* **What it does not name.** Locomotive BASIC, in the system ROM, and AMSDOS were written by Locomotive Software for Amstrad. The
  permission is Amstrad's and does not name Locomotive Software or its BASIC. Retro-Recomp's maintainer chose on 21 November 2026
  to rely on it for the CPC's firmware as emulators have for many years.
* **Where the ROMs come from.** Nothing of them is stored in Retro-Recomp's repository or installer. The converter fetches
  `cpc6128.rom` and `amsdos.rom` from the `rom/` folder of the Caprice32 emulator project (GitHub `ColinPitrat/caprice32`,
  commit `276658ae9a9e40fc899987e69c3f5653ece37693`) the first time a conversion needs them, and checks each one's size, its Git
  blob SHA-1 at that commit, the SHA-1 MAME 0.289 lists for it and its SHA-256 (`retrorecomp/cpc_roms.py`). The ROM files are
  Amstrad's, not part of Caprice32's code; no Caprice32 code is used.
* **The player's own ROMs.** A player may give their own system ROM (one 32 KiB file, or its 16 KiB OS and BASIC halves) and
  AMSDOS ROM in Options instead: they are accepted only when their SHA-1 is one MAME lists for a CPC 6128 or 664 system ROM or for
  AMSDOS.
* **In the game.** Each converted CPC game holds the system ROM and AMSDOS it was converted with, and this notice.
