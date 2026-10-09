# Master System Light Phaser

RetroRecomp includes a virtual Light Phaser on controller port 1 since 0.10.6.
Conversion selects it from an explicit cartridge catalogue, not by searching
the Z80 program for gun instructions. Known CRC32 identities take precedence
over filenames; full-title matching handles renamed regional dumps that keep
their title. Assault City's known joypad edition is explicitly excluded.
An unknown Assault City dump requires the filename to identify its Light
Phaser edition, since the two editions have different controls.

## Playing

Move the mouse to aim. Left click pulls the trigger. Right click pulls the
trigger while aiming off-screen. Clicking a letterbox border also counts as
off-screen; losing keyboard focus releases input.
The original gun has no D-pad or second face button. Player 2 remains a pad.
Laser Ghost also receives the original P2 trigger alias to select its gun mode.

In 0.10.7 the default reticle is a **small red cross**. **F5** opens Light Phaser
options; **G** in F2 opens the same page. Choose cross or dot, size 1 to 5, and
red, white or pure green. Up/Down selects a row and Left/Right changes it;
the controller D-pad and mouse arrows work too. A preview shows the result.

The dot is a square `size` console pixels wide. The cross has one-pixel strokes
and arms `size` pixels long, so the smallest cross is 3 by 3 pixels. Both follow
the game's integer scale, with clipping at the visible image edges. Pure RGB
colors are red `(255,0,0)`, white `(255,255,255)`, and green `(0,255,0)`.

Settings are shared in `datas/Retro-Recomp.ini`, under `[LightPhaser]`:
`shape=cross|dot`, `color=red|white|green`, and the existing `dot_size=1..5`
entry. Old size preferences remain valid for either shape. Missing or invalid
shape/color entries select cross/red. Reticle options do not change shot
coordinates or the sensor area. The overlay never changes the console framebuffer.

Mouse coordinates are mapped through the actual viewport, including integer
fullscreen scaling, HiDPI renderer units, filters and automatic left masking.
The system cursor is hidden over the active game image and restored in menus.

Original gun software produces bright flashes for its sensor measurement.
Those game-generated flashes are preserved; reticle options affect only the
aiming overlay.

## Automatic icon tag

Starting with 0.10.8, **Automatic tags** adds the project's red target graphic
to the lower-left of the visible box art in a generated Windows icon. It uses
the same cartridge catalogue as gun input, including the Assault City edition
exclusion. This identifies Light Phaser support, not the shooter genre; pad
games such as Bomber Raid remain untagged. Laser Ghost and compilations are
tagged because they support a gun mode.

The badge is 30% smaller than the initial design: 18.9% of the square icon
size, rounded to whole pixels with a four-pixel minimum. The badge and its
one-pixel white halo use 80% opacity. It sits near the bottom edge, with 15%
of its width extending left of the cover when there is room in the icon.
Each of the nine ICO sizes, 16 to 256 pixels, is composed separately
so small icons keep a readable badge. The original cover and tag assets are
read-only inputs; both the executable and its SDL window use the resulting
embedded resource. The icon tag is independent of the in-game reticle's shape,
size and color.

The option is enabled by default and saved with converter preferences. Disable
it in the converter or pass `--no-icon-tags` to `convert` or `batch` to regenerate
a clean cover icon. `--no-cover` still disables custom game icons. A missing
cover has no custom icon to tag; a missing or damaged tag asset keeps the cover
and logs a warning. Reports distinguish `game_tags` (catalogue classification)
from `artwork.tags` (badges actually embedded).

## Catalogue

| Cartridge/title | Selection notes |
| --- | --- |
| Assault City | Light Phaser edition only; joypad edition excluded |
| Gangster Town | P1 mouse gun; a second mouse gun is not implemented |
| Hang-On & Safari Hunt | Compilation; original game selection remains intact |
| Laser Ghost | Optional original gun mode, P2 trigger alias |
| Marksman Shooting & Trap Shooting | Compilation |
| Marksman Shooting / Trap Shooting / Safari Hunt | Compilation |
| Missile Defense 3-D | Gun input; stereoscopic glasses output is not implemented |
| Operation Wolf | Gun input; existing P2 pad retained |
| Rambo III | Gun input |
| Rescue Mission | Gun input |
| Shooting Gallery | Gun input |
| Space Gun | Gun input |
| Wanted | Gun input |
| 3D Gunner | Known unreleased prototype; not validated gameplay |
| Die Hard 2 | Unreleased; exact-title selection, no verified CRC or gameplay qualification |
| Color & Switch Test | Sega diagnostic cartridge, CRC32 `7253C3EC`; not a retail game |
| Porkpolis | Homebrew; author documents gun or P1 pad input |
| Shootagem | Homebrew; author documents gun on port 1 |
| Shooting Stars | Homebrew; author documents gun or P1 pad input |
| SMS-A-Sketch 1.2 | Homebrew drawing demo; light-gun support added in 1.2 |

Standalone Safari Hunt, Marksman Shooting and Trap Shooting filenames are
accepted as catalogue aliases. A catalogue entry identifies a peripheral;
it is not a full-game compatibility certificate.

### Catalogue audit, 9 October 2026

The thirteen retail cartridge entries above cover the released Light Phaser
games, including the two Marksman/Trap compilations and Hang-On/Safari Hunt.
3D Gunner and Die Hard 2 are unreleased programs; Color & Switch Test is a
diagnostic tool. The four homebrew entries come from their authors' descriptions
and manuals. These additional entries select the peripheral but have not been
qualified for gameplay. SMS-A-Sketch needs an explicit 1.2 filename; earlier
versions and unidentified filenames are not assumed to support a gun.
New homebrew releases may require further entries: this is not a closed list of
every future Light Phaser program.

**T2: The Arcade Game on Master System uses a Control Pad, not the Light Phaser.**
Terminator 2: Judgment Day is also a pad game. Their gun adaptations on other
consoles must not enable a Master System gun or icon badge. Assault City has
separate joypad and gun cartridges; identifying one does not qualify the other.

The October SMS campaign now contains all thirteen retail gun cartridge entries:
Assault City (Light Phaser edition), Gangster Town, Hang-On & Safari Hunt,
Laser Ghost, both Marksman/Trap compilations, Missile Defense 3-D, Operation Wolf,
Rambo III, Rescue Mission, Shooting Gallery, Space Gun and Wanted. The two missing
editions were qualified separately using CRC32 `861B6E79` and `E8215C2E`, with
matching MAME SHA-1 identities. Strict execution and reference comparisons
passed; both 7,200-frame scripted scenarios had zero fallback cycles. Their
exports select gun input and carry the shooting badge. The original joypad
Assault City and two-game Marksman/Trap exports remain separate and unchanged.
This is scripted qualification, not validation of every gun gameplay sequence.
The unreleased programs and additional homebrew programs remain unexported;
do not substitute another cartridge's data for them.

CRC32 `C5083000` identifies the documented working Hang-On/Safari Hunt overdump
used in this batch. The catalogue now recognizes it even after a ROM rename.
MEKA marks that dump as bad because it has duplicated data and fails the original
checksum; the supplied file is preserved rather than silently rewritten.

## Hardware boundary and limits

The authored C adapter implements active-low TL trigger, TH raster pulses,
the frozen horizontal counter and the $3F input/output direction controls.
It is shared by generated native CPU code and reference CPU execution and
does not call SDL. The existing guest cycle clock drives it. Only the host
reads the mouse; no interpreter is required to implement the gun.

This implementation uses an idealized finite sensor spot: a roughly 20-us
pulse across seven nearby scanlines, calibrated H-counter offsets and the
runtime's existing 262-line NTSC timeline. It does not reproduce real CRT
brightness, phosphor persistence, sensor optics, PAL hardware or physical gun
latency. Reticle coordinates and the original games' computed coordinates can
therefore differ slightly; gameplay evidence must be reported separately from
native/reference agreement, since both CPUs share this adapter.

`python tools/lightphaser_selftest.py` uses an authored ROM on both native CPU
backends and the reference CPU, including an off-screen miss. Native host
checks verify pointer mapping, focus, cross/dot pixels, colors, shared
configuration and unchanged console pixels.
Private real-game probes use `--report <conversion-report.json> --frames N`;
they never become distributable fixtures.

## Sources

- [Sega's original software reference, I/O and gun sections](https://www.smspower.org/Development/SMSOfficialDocs).
- [Light Phaser connections and raster behavior](https://www.smspower.org/Development/LightPhaser).
- [MEKA verified cartridge catalogue](https://github.com/ocornut/meka/blob/master/meka/meka.nam), including Assault City's two editions and Laser Ghost's selection.
- [Genesis Plus GX's SMS cartridge catalogue](https://github.com/ekeeke/Genesis-Plus-GX/blob/master/core/cart_hw/sms_cart.c), used to cross-check identities and documented coordinate offsets.
- [SMS Power's Light Phaser catalogue](https://www.smspower.org/Tags/LightPhaser), including unreleased software and homebrew.
- [T2: The Arcade Game cartridge page and Control Pad selection](https://www.smspower.org/Games/T2TheArcadeGame-SMS).
- [Porkpolis author manual](https://www.smspower.org/Homebrew/Porkpolis-SMS), [Shootagem author description](https://www.smspower.org/Homebrew/Shootagem-SMS), [Shooting Stars author manual](https://www.smspower.org/Homebrew/ShootingStars-SMS), and [SMS-A-Sketch version notes](https://www.smspower.org/Homebrew/SMSASketch-SMS).

No emulator implementation code or commercial game data is copied into this
adapter or its public tests.
