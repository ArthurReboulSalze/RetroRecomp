# CRTS (crt-lottes-fast)

Timothy Lottes, "PUBLIC DOMAIN CRT-STYLED SCALAR" (CRTS, 20180120b), adapted for RetroArch by hunterk;
ported by Retro-Recomp to one source for Direct3D 11 (HLSL) and OpenGL (GLSL 1.20) in
`native/hostkit/shell/rrhk_crts.inc`, the CRT looks' graphics-card pass (host kit decision D35).

Source: https://github.com/libretro/glsl-shaders/blob/a35069864b4bf30f8c8e740d57206543fb7e745e/crt/shaders/crt-lottes-fast.glsl

The file states its licence as follows:

LICENSE = UNLICENSE (aka PUBLIC DOMAIN)

This is free and unencumbered software released into the public domain.

Anyone is free to copy, modify, publish, use, compile, sell, or distribute this
software, either in source code form or as a compiled binary, for any purpose,
commercial or non-commercial, and by any means.

In jurisdictions that recognize copyright laws, the author or authors of this
software dedicate any and all copyright interest in the software to the public
domain. We make this dedication for the benefit of the public at large and to
the detriment of our heirs and successors. We intend this dedication to be an
overt act of relinquishment in perpetuity of all present and future rights to
this software under copyright law.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

For more information, please refer to <http://unlicense.org/>

## Why this shader

Every game of every machine on the host kit carries the same looks. Many of the
host kit's machines compile code under noncommercial terms (PolyForm
Noncommercial and the like), which cannot sit in one executable with code under
the GNU GPL. So the CRT looks use only public-domain or MIT shaders. The
well-known CRT shaders crt-geom, crt-easymode, crt-royale, crt-guest-advanced,
zfast_crt and crt-pi are under the GPL and are not used.

crt-geom-mini (DariusG, glsl-shaders `crt/shaders/crt-geom-mini.glsl` at the
same revision) carries an MIT notice but is not used. It describes itself as a
"CRT-Geom replica", and its code is crt-geom's (GPL-2.0-or-later, cgwg,
Themaister and DOLLS):
- the same `scanlineWeights(distance, color)` function, with crt-geom's
  Gaussian beam width `0.3 + 0.1 * ...` from crt-geom's `USEGAUSSIAN` branch;
- the same `ratio_scale` and `uv_ratio = fract(ratio_scale)`;
- the two lines `weights = scanlineWeights(uv_ratio.y, col)` and
  `weights2 = scanlineWeights(1.0 - uv_ratio.y, col2)` (crt-geom lines
  487-488, crt-geom-mini lines 196-197).

A third party cannot relicense a derivative of a GPL file, so its MIT notice
cannot be relied on.
