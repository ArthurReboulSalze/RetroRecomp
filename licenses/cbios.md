# C-BIOS (the MSX BIOS of a game that boots it)

An MSX game exported by Retro-Recomp boots [C-BIOS](https://cbios.sourceforge.net/) when the player gave no MSX BIOS of their
own ([MSX.md](../docs/MSX.md)). C-BIOS is a free replacement for the MSX BIOS, under the 2-clause BSD licence below. Nothing of
C-BIOS is stored in Retro-Recomp's repository or installer.

* **Version.** C-BIOS 0.29a, from the official release file `cbios-0.29a.zip`, unchanged. An MSX game embeds the MSX1 main ROM
  (`cbios_main_msx1.rom`, international 60 Hz, or `cbios_main_msx1_eu.rom`, 50 Hz) and the MSX1 logo ROM
  (`cbios_logo_msx1.rom`); an MSX2 game the MSX2 main ROM (`cbios_main_msx2.rom`, 60 Hz, or `cbios_main_msx2_eu.rom`, 50 Hz),
  the MSX2 logo ROM (`cbios_logo_msx2.rom`) and the MSX2 sub-ROM (`cbios_sub.rom`).
* **Where it comes from.** The converter fetches `cbios-0.29a.zip` from the C-BIOS project on SourceForge
  (<https://sourceforge.net/projects/cbios/files/cbios/0.29/>) the first time a conversion needs it, and checks the pinned size
  and SHA-256 of the archive (`c585a2f4a10b397e460a95043d59ac79cf4442fbb45a6e14a1e27ef9febaed73`) and of each image on every use
  (`retrorecomp/msx_cbios.py`).
* **In the game.** A game that boots C-BIOS embeds those images and this notice. C-BIOS runs cartridges only: no MSX-BASIC, no disk,
  no cassette.

## Licence (from the release's `doc/cbios.txt`)

Copyright (c) 2002-2005 BouKiCHi.  All rights reserved.
Copyright (c) 2003 Reikan.  All rights reserved.
Copyright (c) 2004-2006,2008-2010 Maarten ter Huurne.  All rights reserved.
Copyright (c) 2004-2006,2008-2011 Albert Beevendorp.  All rights reserved.
Copyright (c) 2004-2005 Patrick van Arkel.  All rights reserved.
Copyright (c) 2004,2010-2011 Manuel Bilderbeek.  All rights reserved.
Copyright (c) 2004-2006 Joost Yervante Damad.  All rights reserved.
Copyright (c) 2004-2006 Jussi Pitkänen.  All rights reserved.
Copyright (c) 2004-2007 Eric Boon.  All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions
are met:
1. Redistributions of source code must retain the above copyright
   notice, this list of conditions and the following disclaimer.
2. Redistributions in binary form must reproduce the above copyright
   notice, this list of conditions and the following disclaimer in the
   documentation and/or other materials provided with the distribution.

THIS SOFTWARE IS PROVIDED BY THE AUTHOR ``AS IS'' AND ANY EXPRESS OR
IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES
OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED.
IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY DIRECT, INDIRECT,
INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT
NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF
THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
