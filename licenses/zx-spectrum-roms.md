# ZX Spectrum ROMs (Amstrad)

A ZX Spectrum game converted by Retro-Recomp runs on the Spectrum's own ROM: a snapshot holds the machine's RAM only, and the
game calls the ROM's routines and its interrupt handler ([ZX_SPECTRUM.md](../docs/ZX_SPECTRUM.md)). The game therefore holds
the ROM, translated with it.

**The ZX Spectrum 48K and 128K ROMs are copyright Amstrad. Amstrad have kindly given their permission for the redistribution
of their copyrighted material but retain that copyright.** The ROM code is not sold: Retro-Recomp and the games it converts are
free, and no charge is made for the ROMs. Their copyright messages are kept unaltered.

* **The permission.** Cliff Lawson of Amstrad plc, in a public statement to the comp.sys.sinclair and comp.sys.amstrad.8bit
  newsgroups on 31 August 1999, allowed emulator authors to include images of the ROMs of the Spectrum 48K, 128K, +2, +2A and +3,
  provided that their copyright messages are not altered and that no charge is made for the ROM code. Amstrad plc now belongs to
  Sky; no later statement withdrawing the permission is known. Retro-Recomp's maintainer chose on 21 November 2026 to rely on it.
* **Where the ROMs come from.** Nothing of them is stored in Retro-Recomp's repository or installer. The converter fetches
  `48.rom`, `128-0.rom` and `128-1.rom` from the `roms/` folder of the Fuse emulator project (GitHub mirror
  `fuse-emulator/fuse`, commit `089eadf7c175c54a37ff66843479235a845890fd`) the first time a conversion needs them, and checks the
  size and SHA-256 of each on every use (`retrorecomp/zxs_roms.py`). In that folder the ROM files are under Amstrad's permission,
  not under Fuse's licence; no Fuse code is used.
* **The player's own ROM.** A player may give their own 48K or 128K ROM in Options instead: it is accepted only when its SHA-256
  is the one of these same images, so the converted game is the same.
* **In the game.** Each converted Spectrum game holds the ROM of its model (16K and 48K: `48.rom`; 128K: `128-0.rom` and
  `128-1.rom`) and this notice.
