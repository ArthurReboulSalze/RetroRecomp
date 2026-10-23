# ymfm (YM2151) for the CPS-1 runtime

The CPS-1 runtime generates YM2151 (OPM) sound with ymfm by Aaron Giles,
[`aaronsgiles/ymfm` at `81aec25ccbb98f4873a255f7551ac4dadac59b4a`](https://github.com/aaronsgiles/ymfm/tree/81aec25ccbb98f4873a255f7551ac4dadac59b4a):
`src/ymfm.h`, `ymfm_fm.h`, `ymfm_fm.ipp`, `ymfm_opm.h` and `ymfm_opm.cpp`,
compiled unmodified from a copy made by `smsrecomp/cps1_build.py`.
`native/cps1_opm.cpp` is the Retro-Recomp interface (timers, interrupt and
busy flag on the Z80 clock). The Neo Geo uses a separate C port of other ymfm
cores through Geolith.

The licence below is the unmodified `LICENSE` file of that revision.

```
BSD 3-Clause License

Copyright (c) 2021, Aaron Giles
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its
   contributors may be used to endorse or promote products derived from
   this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```
