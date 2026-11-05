# pcenginerecomp (PC Engine engine)

The PC Engine profile (experimental since 1.6.9: [docs/PC_ENGINE.md](../docs/PC_ENGINE.md)) is built on
[`rages4calm/pcenginerecomp` at `81b5c231e452c6879d58585c8863012e438f1d55`](https://github.com/rages4calm/pcenginerecomp/tree/81b5c231e452c6879d58585c8863012e438f1d55):
its Python analysis and emitter, and its C++ runtime (`pce-runtime`: HuC6280 interpreter, VDC, VCE, PSG, timer,
interrupts, pads, HuCard boards). The engine is fetched at that revision when a conversion needs it; no copy of
it is kept in this repository. Its runtime is compiled into every PC Engine game the converter makes, with the bridge and
the host-kit adapter of Retro-Recomp (MIT).

Three notices travel with the runtime and the emitter: the engine's own MIT licence, the BSD terms of the MAME
opcode table its `pcerecomp/isa.py` follows (kept by the engine in `licenses/MAME-HuC6280.txt`), and the MIT
notice of David Shadoff's PCECD_seek carried in `runtime/src/cd_timing.cpp` (compiled into `pce-runtime` for
every board, HuCards included). Each text below is unmodified from that revision.

## pcenginerecomp

```
MIT License

Copyright (c) 2026 Carl Prewitt Jr. and PC Engine Recomp contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## MAME HuC6280 opcode metadata

```
MAME HuC6280 disassembler opcode metadata
Source: https://github.com/mamedev/mame/blob/da9333a2a5123012a939e78c3f2df7175ea7d100/src/devices/cpu/h6280/6280dasm.cpp

Copyright (c) Bryan McPhail
Based, with permission, on the 6502 emulator by Juergen Buchmueller.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice,
   this list of conditions and the following disclaimer.
2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.
3. Neither the name of the copyright holder nor the names of its
   contributors may be used to endorse or promote products derived from this
   software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
POSSIBILITY OF SUCH DAMAGE.
```

## PCECD_seek (runtime/src/cd_timing.cpp)

```
MIT License
Copyright (c) 2019 David Shadoff
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
```
