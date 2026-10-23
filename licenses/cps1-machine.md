# Capcom CPS-1 board catalogue

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
`docs/legal/BSD-3-Clause` at the same revision, with the copyright line taken
from the source headers (no year is stated there).

Copyright Paul Leaman

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
