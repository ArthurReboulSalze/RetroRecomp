# Capcom CPS-1 board catalogue and machine

The CPS-1 machine runtime (`native/cps1_machine.c`, `native/cps1_machine.h`)
adapts the board logic of the same MAME driver files to C: memory map,
CPS-A/CPS-B registers, graphics bank mapping, palette, tile layers, sprites,
star fields, priority masks and the sound latch/bank wiring. The OKI MSM6295
(`native/cps1_oki.c`, `native/cps1_oki.h`) adapts MAME's
`src/devices/sound/okim6295.cpp` (`copyright-holders:Mirko Buffoni,Aaron
Giles`) and `src/devices/sound/okiadpcm.cpp` (`copyright-holders:Andrew
Gardner,Aaron Giles`), both `license:BSD-3-Clause`, at the same revision. The
reference CPUs are Musashi and the Z80 core of the pinned Geolith copy (see
`licenses/musashi.md` and `licenses/superzazu-z80.md`); the YM2151 is ymfm
(see `licenses/cps1-ymfm.md`).

The native CPS-1 runtime (`native/cps1_native.c`, `native/cps1_native.h`,
`native/cps1_z80_native.h`) is Retro-Recomp code (MIT) adapted from
`native/neogeo_native.*`. The code it runs is generated on the user's machine
from the user's own ROMs: MC68000 bodies from m68k-recomp-core (see
`licenses/segagenesisrecomp.md`) and Z80 bodies from the pinned Geolith Z80
core (see `licenses/superzazu-z80.md`); it is never distributed.

Retro-Recomp's CPS-1 board catalogue (`assets/cps1-catalogue.json`) is derived
from MAME's CPS-1 driver at revision
[`61a222977fd29f22ce11fbea3f7c290fd7ced091`](https://github.com/mamedev/mame/tree/61a222977fd29f22ce11fbea3f7c290fd7ced091/src/mame/capcom):
`src/mame/capcom/cps1.cpp` (set list and ROM layouts) and
`src/mame/capcom/cps1_v.cpp` (CPS-B board registers and graphics mappers).
Both files state `license:BSD-3-Clause` and `copyright-holders:Paul Leaman`.
`tools/build_cps1_catalogue.py` reads them at that revision, checks their
SHA-256 values and writes the catalogue; the catalogue records the same
revision and notice. No ROM data is included.

Retro-Recomp is noncommercial. The terms below come from MAME's
`docs/legal/BSD-3-Clause` at the same revision, with the copyright lines taken
from the source headers (no year is stated there).

Copyright Paul Leaman; Mirko Buffoni; Aaron Giles; Andrew Gardner

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are
met:

1. Redistributions of source code must retain the above copyright
   notice, this list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright
   notice, this list of conditions and the following disclaimer in the
   documentation and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its
   contributors may be used to endorse or promote products derived from
   this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS
IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED
TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A
PARTICULAR PURPOSE ARE DISCLAIMED.  IN NO EVENT SHALL THE COPYRIGHT
HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED
TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
