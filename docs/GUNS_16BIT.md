# Mega Drive and Super Nintendo lightguns

Release 0.20.0 adds mouse Menacer input on Mega Drive and mouse
Super Scope input on Super Nintendo. Recognition is based on an explicit
per-console catalogue. CPU conversion builds a separate profile for each ROM;
a familiar gun-game filename never selects a different cartridge's native code.
These additions are experimental.

## Qualified test cartridges

| Console | Cartridge | CRC32 | Device |
| --- | --- | --- | --- |
| Mega Drive | Menacer 6-Game Cartridge | 936B85F7 | Menacer |
| Mega Drive | T2 - The Arcade Game | A1264F17 | Menacer |
| Super Nintendo | Super Scope 6, USA | B141EA99 | Super Scope |

All three were tested with NTSC profiles. PAL variants may be converted when
their hardware is supported, but are not covered by these three test results.
Menacer and T2 have separate native analysis and RAM observations. Super Scope
6 uses a generic per-ROM 65816 operation map and its own cartridge identity;
no Super Mario World function tree or game RAM aliases are used.

The catalogue also identifies Body Count and the two Mega Drive Lethal
Enforcers games, and SNES Scope titles such as Yoshi's Safari, Battle Clash,
Metal Combat, Bazooka Blitzkrieg, X Zone and Tin Star. Catalogue recognition
does not mean these additional ROMs have been gameplay-tested. Mega Drive Justifier pins,
detection and gun selection have authored tests, but no Justifier cartridge
has been gameplay-validated yet. The SNES Justifier has a different serial protocol and is
catalogued only. This build exposes one mouse gun on controller port 2;
the standard controller remains on port 1.

## Controls

Move the mouse to aim and left-click to fire. A small red cross is the default.
The cross uses two display-pixel-wide strokes on both 16-bit profiles.
F5 opens gun settings, also available through Tab in F2 controls. Choose cross
or dot, size 1–12, and red, white or pure green. The overlay is drawn after
the game and scanlines, without changing the console framebuffer. Mouse
coordinates follow the actual game rectangle in windowed, integer fullscreen,
fractional fullscreen and HiDPI modes. Bars outside that rectangle are offscreen.
Opening a host menu or losing focus releases the gun buttons.

| Host input | Menacer | Super Scope |
| --- | --- | --- |
| Left mouse button | A / trigger | Fire |
| Right mouse button | B | Cursor |
| Middle mouse button | C | Scope Pause |
| Enter / mapped controller Start | Start | Scope Pause |

Scope Turbo is a separate option in F5, on by default. It represents the
gun's physical turbo switch; F6 still controls gamepad autofire. Non-turbo
Scope Fire and Pause are edge-triggered; Cursor stays active while held.
Follow each game's original calibration and controller-selection screens.
Original flashes remain intact. P pauses the RetroRecomp host independently
of a console gun's Pause button.

Only an explicit setting change creates `datas/Retro-Recomp.ini`. Gun settings
are shared per console, in `MegaDrive.Gun` or `SNES.Gun`. Normal launch and quit
create no log, learning files or data directory. Recognised gun exports receive
the existing shooting icon tag and the required gun in Windows metadata.

## Hardware model and verification limits

Menacer uses positive button bits; Justifier uses its own active-low bits and
identification sequence. CPU-driven port outputs are preserved. A sensor hit
drives TH, supplies the discontinuous H counter, and requests a level-2
interrupt when the game enables it. Menacer horizontal conversion and offsets
are game-specific. Menacer buttons are acquired by the receiver's long-reset
sequence on output pins PD4/PD5 and retained until the next acquisition.
TH-only device identification does not acquire the current buttons. This
keeps T2's gun detection valid when the host's mapped Start is held to confirm
the controller menu. A short counter reset retains the last button packet.
Video is still rendered by scanline: the horizontal value is an estimate,
not a dot-accurate IRQ delivery time.
For non-latching games it is supplied only during the gun interrupt.

The new gun cartridges deliver real 68000 exception frames through the normal
instruction fiber. Video and Z80 execution continue during an interrupt's
polling loops; bus polls cannot yield halfway through a guest instruction.
RTE restores the guest's PC and SR. Gun profiles interleave the 68000 and Z80
sixteen times per line within the existing 488/228 cycle budgets. CPU
instruction overshoot carries between slices, and Z80 audio stamps include
the slice offset. This prevents T2's brief BUSREQ releases from being missed
at every whole-line boundary, starving its audio CPU and leaving IRQ2 masked.
Legacy non-gun interrupt scheduling is unchanged.

Super Scope has serial and automatic controller reads, signature bits,
one-shot buttons, turbo and offscreen state. Sensor hits update the PPU H/V
counters on the beam timeline through WRIO's latch gate. WRIO powers up high;
SLHV and STAT78 respect its gate. Counter read phase is retained on a light
hit. The input model uses the established x+10/y-3 coordinate convention and
leaves calibration to the game. Brightness sensitivity, infrared interference
and real CRT sensor delays are not simulated.

Authored fixtures check pins, output ownership, identification, counter
boundaries, serial/automatic reads, button edges, offscreen input and PPU
latching. Conversion compares native and interpreted main-CPU executions on
3,600-frame demo and scripted mouse-play scenarios, including CPU/memory,
visible-frame sequence and gun state. Both paths share hardware semantics;
agreement is not independent hardware validation or complete gameplay
validation. The Z80/SPC700 audio CPUs remain interpreted, and physical latency
has not been measured. Complete playthrough validation remains open.
The tested Menacer and Super Scope scenarios produce sensor captures. T2's
script now selects one-player Menacer through its original menu, without
changing guest RAM or ROM. Its 3,000-frame-or-longer gun test requires sensor
captures, delivered gun interrupts and acquired trigger packets. These are
also compared with the reference. The user has confirmed functional gun input
in all three cartridges, including T2 after its receiver and scheduling fixes.
This hands-on check does not establish complete gameplay or hardware fidelity.

## Original protocol references

The peripheral implementation is original RetroRecomp code. These primary
documentation and original implementation sources were consulted for protocol
facts; no external emulator gun implementation was copied:

- [Eke-Eke's Mega Drive lightgun hardware notes](https://gendev.spritesmind.net/mirrors/eke/gen_lightgun.pdf):
  Menacer/Justifier pins, supported games, counters and game offsets.
- [Genesis Plus GX lightgun implementation](https://github.com/ekeeke/Genesis-Plus-GX/blob/master/core/input_hw/lightgun.c):
  comparison of documented Menacer counter conversion.
- [Super Famicom controller documentation](https://wiki.superfamicom.org/controllers):
  Scope serial data, auto-read, one-shot buttons and latch line.
- [Super Famicom register documentation](https://wiki.superfamicom.org/registers):
  WRIO power-up, SLHV, counter phase and STAT78 latch clearing.
- [Mesen2 Super Scope implementation](https://github.com/SourMesen/Mesen2/blob/master/Core/SNES/Input/SuperScope.h):
  existing mouse-coordinate convention, used as a compatibility reference.

Run `python tools/gun16_selftest.py` with the pinned engines already available
for the ROM-free native fixtures, and `python -m unittest discover -s tests`
for the catalogue, identity and reference-gate tests.
