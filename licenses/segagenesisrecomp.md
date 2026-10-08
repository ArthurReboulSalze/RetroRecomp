## segagenesisrecomp

Source: https://github.com/mstan/segagenesisrecomp

# PolyForm Noncommercial License 1.0.0

<https://polyformproject.org/licenses/noncommercial/1.0.0>

## Acceptance

In order to get any license under these terms, you must agree to them as both strict obligations and conditions to all your licenses.

## Copyright License

The licensor grants you a copyright license for the software to do everything you might do with the software that would otherwise infringe the licensor's copyright in it for any permitted purpose. However, you may only distribute the software according to Distribution License and make changes or new works based on the software according to Changes and New Works License.

## Distribution License

The licensor grants you an additional copyright license to distribute copies of the software. Your license to distribute covers distributing the software with changes and new works permitted by Changes and New Works License.

## Notices

You must ensure that anyone who gets a copy of any part of the software from you also gets a copy of these terms or the URL for them above, as well as copies of any plain-text lines beginning with **Required Notice:** that the licensor provided with the software. For example:

> **Required Notice:** Copyright Yoyodyne, Inc. (http://example.com)

## Changes and New Works License

The licensor grants you an additional copyright license to make changes and new works based on the software for any permitted purpose.

## Patent License

The licensor grants you a patent license for the software that covers patent claims the licensor can license, or becomes able to license, that you would infringe by using the software.

## Noncommercial Purposes

Any noncommercial purpose is a permitted purpose.

## Personal Uses

Personal use for research, experiment, and testing for the benefit of public knowledge, personal study, private entertainment, hobby projects, amateur pursuits, or religious observance, without any anticipated commercial application, is use for a permitted purpose.

## Noncommercial Organizations

Use by any charitable organization, educational institution, public research organization, public safety or health organization, environmental protection organization, or government institution is use for a permitted purpose regardless of the source of funding or obligations resulting from the funding.

## Fair Use

You may have "fair use" rights for the software under the law. These terms do not limit them.

## No Other Rights

These terms do not allow you to sublicense or transfer any of your licenses to anyone else, or prevent the licensor from granting licenses to anyone else. These terms do not imply any other licenses.

## Patent Defense

If you make any written claim that the software infringes or contributes to infringement of any patent, your patent license for the software granted under these terms ends immediately. If your company makes such a claim, your patent license ends immediately for work on behalf of your company.

## Violations

The first time you are notified in writing that you have violated any of these terms, or done anything with the software not covered by your licenses, your licenses can nonetheless continue if you come into full compliance with these terms, and take practical steps to correct past violations, within 32 days of receiving notice. Otherwise, all your licenses end immediately.

## No Liability

As far as the law allows, the software comes as is, without any warranty or condition, and the licensor will not be liable to you for any damages arising out of these terms or the use or nature of the software, under any kind of legal claim.

## Definitions

The **licensor** is the individual or entity offering these terms, and the **software** is the software the licensor makes available under these terms.

**You** refers to the individual or entity agreeing to these terms.

**Your company** is any legal entity, sole proprietorship, or other kind of organization that you work for, plus all organizations that have control over, are under the control of, or are under common control with that organization. **Control** means ownership of substantially all the assets of an entity, or the power to direct its management and policies by vote, contract, or otherwise. Control can be direct or indirect.

**Your licenses** are all the licenses granted to you for the software under these terms.

**Use** means anything you do with the software requiring one of your licenses.


PolyForm Noncommercial License 1.0.0

<https://polyformproject.org/licenses/noncommercial/1.0.0>

Copyright (c) 2026 Matthew Stan

## Acceptance

In order to get any license under these terms, you must agree to them as
both strict obligations and conditions to all your licenses.

## Copyright License

The licensor grants you a copyright license for the software to do
everything you might otherwise need the licensor's permission to do. Your
license covers distributing the software, making changes and new works
based on it, and all other uses of the software, subject to the
limitations and conditions in these terms.

## Noncommercial Purposes

Any noncommercial purpose is a permitted purpose.

## Personal Uses

Personal use for research, experiment, and testing for the benefit of
public knowledge, personal study, private entertainment, hobby projects,
amateur pursuits, or religious observance, without any anticipated
commercial application, counts as use for a permitted purpose.

## Noncommercial Organizations

Use by any charitable organization, educational institution, public
research organization, public safety or health organization, environmental
protection organization, or government institution counts as use for a
permitted purpose regardless of the source of funding or obligations
resulting from the funding.

## Fair Use

You may have "fair use" rights for the software under the law. These
terms do not limit them.

## No Other Rights

These terms do not allow you to sublicense or transfer any of your
licenses to anyone else, or prevent the licensor from granting licenses to
anyone else. These terms do not imply any other licenses.

## Patent Defense

If you make any written claim that the software infringes or contributes
to infringement of any patent, your patent license for the software granted
under these terms ends immediately. If your company makes such a claim,
your patent license ends immediately for work on behalf of your company.

## Violations

The first time you are notified in writing that you have violated any of
these terms, or done anything with the software not covered by your
licenses, your licenses can nonetheless continue if you come into full
compliance with these terms, and take practical steps to correct past
violations, within 32 days of receiving notice. Otherwise, all your
licenses end immediately.

## No Liability

As far as the law allows, the software comes as is, without any warranty
or condition, and the licensor will not be liable to you for any damages
arising out of these terms or the use or nature of the software, under any
kind of legal claim.

## Definitions

The **licensor** is the individual or entity offering these terms, and the
**software** is the software the licensor makes available under these
terms.

**You** refers to the individual or entity agreeing to these terms.

**Your company** is any legal entity, sole proprietorship, or other kind
of organization that you work for, plus all organizations that have control
over, are under the control of, or are under common control with that
organization. **Control** means ownership of substantially all the assets
of an entity, or the power to direct its management and policies by vote,
contract, or otherwise. Control can be direct or indirect.

**Your licenses** are all the licenses granted to you for the software
under these terms.

**Use** means anything you do with the software requiring one of your
licenses.

---

For the avoidance of doubt, the licensor's intent is to restrict uses where
profit is derived from this software. Non-profit personal, educational,
or community use is welcome regardless of organizational context.

For commercial licensing inquiries, contact: https://1379.tech


# Third-Party Components and Licenses

Third-party licenses remain separate from the project's
[PolyForm Noncommercial license](LICENSE.md). Current source, recompiler, and
native release paths contain no clownmdemu, clown68000, or clownz80 dependency.
Those retired oracle components exist only in Git history.

## Framework dependencies

| Component | Role | License | Source |
|---|---|---|---|
| **ymfm** (`runner/external/ymfm/`) | YM2612 FM synthesis in native releases | BSD-3-Clause | <https://github.com/aaronsgiles/ymfm> |
| **superzazu/z80** (`runner/external/superzazu/`) | Z80 sound-CPU core in native releases | MIT | <https://github.com/superzazu/z80> |
| **clowncommon** (`runner/external/clowncommon/`) | Integer types and small C helpers | ISC | <https://github.com/Clownacy/clowncommon> |
| **minicoro** (`runner/external/minicoro/`) | Game-fiber context switch on an engine-owned, snapshottable stack | Unlicense OR MIT-0; its embedded context-switch assembly derives from LuaCoco (MIT, Mike Pall) | <https://github.com/edubart/minicoro> |
| **SDL2** (`runner/external/SDL2/`) | Windowing, input, rendering, and audio delivery | zlib | <https://libsdl.org> |
| **tomlc99** (`recompiler/src/toml.{c,h}`) | TOML parsing for game configuration | MIT | <https://github.com/cktan/tomlc99> |
| **recomp-net** (`external/recomp-net/`) | Optional netplay transport and lobby support | MIT | <https://github.com/TechnicallyComputers/recomp-net> |
| **ShadowVerifier and color-science core** (`runner/audio/audio_shadow.{c,h}`, `runner/video/color_lut.{c,h}`) | Opt-in verified audio/video enhancements | MIT OR Apache-2.0 | <https://github.com/JRickey/gba-recomp>, ported through the gbarecomp/snesrecomp implementations with permission |

License texts are retained with the vendored or submodule sources:

- `runner/external/ymfm/LICENSE`
- `runner/external/superzazu/LICENSE`
- `runner/external/clowncommon/LICENCE.txt`
- `runner/external/minicoro/LICENSE`, plus the LuaCoco MIT notice embedded in
  `runner/external/minicoro/minicoro.h`
- `runner/external/SDL2/SDL2-2.28.5/COPYING.txt`
- the MIT notice embedded at the top of `recompiler/src/toml.c` and `toml.h`
- `external/recomp-net/LICENSE`

`m68k-recomp-core` and `z80-recomp-core` are project-owned shared components
and carry their own license and provenance files in their submodules.

## Game-repository launcher dependencies

Game repositories normally add the shared `recomp-ui` launcher at build time;
it is not vendored by this framework repository. A release that enables it also
contains the following permissive components and must ship their notices and
assets from the selected `recomp-ui` revision:

| Component | Role | License |
|---|---|---|
| **Dear ImGui** | Immediate-mode launcher UI | MIT |
| **stb_image / stb_truetype / stb_image_write** | Image, font, and image-write helpers | Public domain or MIT |
| **tinyfiledialogs** | Native ROM file picker | zlib |
| **Lato** | Launcher typeface | SIL Open Font License 1.1 |

## Compliance notes

- Native release binaries contain no AGPL code. Release packaging must still
  follow [RELEASING.md](RELEASING.md) and include every applicable notice.
- The shipped binary must not contain a game ROM. Users supply their own ROM;
  `*.bin` is ignored and the runtime loads it separately.
- Generated C compiled into a game executable is a machine translation of ROM
  code. The project's own license cannot grant rights to third-party game code.
- This inventory is informational, not legal advice.
