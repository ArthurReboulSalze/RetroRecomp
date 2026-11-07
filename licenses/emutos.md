# EmuTOS (the Atari ST operating system of a game that boots it)

An Atari ST game exported by Retro-Recomp boots [EmuTOS](https://emutos.sourceforge.io/) when the player gave no TOS of his own
([ATARI_ST.md](../docs/ATARI_ST.md)). EmuTOS is "Copyright (C) 2001-2025 The EmuTOS development team"; its files are "distributed
under the GPL, version 2 or at your option any later version" (the GNU General Public License, text in its `doc/license.txt` and at
<https://www.gnu.org/licenses/old-licenses/gpl-2.0.html>). Nothing of EmuTOS is stored in Retro-Recomp's repository or installer.

* **Version.** EmuTOS 1.4, the 192 KiB image for the ST, STF and Mega ST in English for the United Kingdom (PAL),
  `etos192uk.img` of the official release file `emutos-192k-1.4.zip`, unchanged
  (SHA-256 `2d6f3f6f304c9ba340aff8d47ba72b274ae29b8fbe6214138846dada97edf0f3`).
* **Where it comes from.** The converter fetches the release files from the EmuTOS project on SourceForge
  (<https://sourceforge.net/projects/emutos/files/emutos/1.4/>) the first time a conversion needs them, and checks their pinned size
  and SHA-256 on every use (`retrorecomp/atarist_emutos.py`): `emutos-192k-1.4.zip`
  (`59abac06a2d29b0864c5a7cfb2af65f022c337aed34188e174a9a08cc737e4bc`) and `emutos-src-1.4.tar.gz`
  (`98977ab2593d9ab81d6fcf9629f6781369912e3fe05c224a35147d5665749702`).
* **Its complete source is in the game.** A game that boots EmuTOS embeds the image and the release's complete source archive
  `emutos-src-1.4.tar.gz`, the source of the image it runs (built with `make all192`, as the release's `readme.txt` says). The game
  writes that archive into a folder of your choice when started as `Game.exe --write-sources FOLDER` (the name of the game's own
  executable in place of `Game.exe`). Whoever passes on such a game passes this source with it, as the GPL asks.
* **EmuTOS stays a separate program.** It runs inside the emulated Atari ST as that machine's operating system, as on a real ST; the
  game executable as a whole is under the GPL, version 2, because of Hatari ([hatari.md](hatari.md)).
