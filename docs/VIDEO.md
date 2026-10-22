# Video presentation and timing

## Shared F3 filters

All six console hosts cycle through **Sharp pixels**, **Scale2x**, **Scanlines**,
then **xBR smooth**. Stored IDs remain unchanged so existing settings keep their
chosen effect. Mode 1 retains its stored setting ID and replaces
the earlier Scale2x + AA attempt with a CPU adaptation of Hyllian's xBR-lv2.
It examines a 5-by-5 neighbourhood to reconstruct diagonal contours at four
times the source resolution, with partial pixel coverage at their edges. SDL
then fits that larger image to the output using linear sampling. This changes
contour geometry instead of only blurring the original pixel boundaries.
Plain Scale2x remains available for comparison. No temporal blending, extra
queued frame, guest-memory change or audio change is introduced.

The shared filter processes the completed visible image, including the Game
Boy palette and Game Gear crop. Its texture is allocated to that visible size;
allocation failure keeps the unfiltered frame available. Buffers are reused
until the visible resolution changes. Flat-colour interiors and straight
edges are preserved in authored numeric fixtures. Pixel-art details can still
look different with reconstruction enabled; visual preference remains personal.

The local CPU-only microbenchmark measured about 0.74 ms per 256-by-240 sparse
test frame, 6.06 ms for a dense checkerboard, and 1.93 ms per 320-by-480 sparse
frame. These synthetic results exclude texture upload, GPU presentation and the
rest of the game. They do not establish whole-game performance or physical
latency. Run `python tools/xbr_selftest.py` to check contour coverage, rotation,
RGBA mixing, boundaries and these workloads without a ROM or window.

The help screen (**F1**) shows **v<version>** at the right of its title row.
The converter injects its own version during compilation for each console;
updating the converter does not change the label in an already-generated game.
The label is separate from the close-help hint and transient notifications.

The 11 October 2026 qualification regenerated only Super Mario Bros. on NES.
Automated checks cover the four filters, three display modes and their restored
settings; host compilation is checked for the other profiles. Visual preference
and gameplay confirmation remain with the user.

Algorithm/API references: [xBR-lv2, pinned MIT source](https://github.com/libretro/glsl-shaders/blob/235448f244bf676d135f7b25ea6b8e1eae41c4e4/xbr/shaders/xbr-lv2.glsl),
[included permission notice](../licenses/xbr.md),
[Scale2x](https://www.scale2x.it/algorithm),
[SDL texture sampling](https://wiki.libsdl.org/SDL2/SDL_SetTextureScaleMode).

## Master System video timing

## Common correction in local development 0.10.9

The previous renderer used the final VRAM, CRAM and registers to draw the
entire frame. A game changing its palette or horizontal scroll during active
display therefore received those values across the whole screen. Agreement
between native and reference CPU output could not expose that shared video
error.

A headless Gangster Town probe confirmed active-display palette and scroll
updates. In a representative play frame, scroll register writes occurred at
lines 56 and 168, and palette entry 16 changed at lines 113 and 191. These
are private-ROM diagnostic observations, not distributed game captures.

Every newly converted Master System game now receives the same mode-4
renderer from `native/video_mode4.inc`, integrated by `prepare_runtime`.
The pinned dependency remains unchanged. There is no per-game graphics patch.

## Rendering contract

- Each line advances the VDP every 228 guest CPU cycles. NTSC uses 262 lines
  and approximately 3.580 MHz; PAL uses 313 lines and approximately 3.547 MHz.
  A ROM named for Europe alone defaults to PAL; mixed-region and other ROMs
  default to NTSC. A compilation profile can specify `[video] standard` to
  choose either timing, or the converter can override it per ROM. The console
  standard is not encoded reliably in the cartridge header. The selection
  belongs to the [Master System profile](SYSTEM_PROFILES.md); other consoles
  define their own timing choices.
- The H-INT counter advances on entering a scanline; V-INT starts at line 193.
  Both standards have their own V-counter wrap during blanking.
  The boundary was checked against the [SMS Power VDP hardware test](https://www.smspower.org/forums/10695-SMSVDPTester).
- Each active line is composed using its VRAM, palette and display controls.
- Horizontal scroll is captured at each line boundary; a later register write
  changes the following line. Vertical scroll is captured for the next frame.
- A completed buffer is preserved while the guest builds the following frame.
  Vblank updates cannot recolor or move pixels already produced.
- The first eight sprites intersecting a line are selected, with transparent
  pixels, background priority, sprite priority, top-edge wrap and zoom handled.
  Collision and overflow flags are generated during line processing.
- In mode 4, sprite collisions inside the blanked left column are suppressed;
  collisions at the first unmasked pixel remain active on SMS and Game Gear.
  This rule is independently reflected in the [MAME mode-4 VDP implementation](https://github.com/mamedev/mame/blob/master/src/devices/video/315_5124.cpp#L1271).
- Left blanking follows the line's backdrop color after sprite composition.
  Automatic cropping requires the mask across the whole frame, rather than
  trusting a register value from vblank.

Hardware I/O synchronizes pending line transitions before reads and writes.
Since 0.10.10, a stop requested during that synchronization waits for the
current CPU step to complete. The instruction still performs its port access,
remaining register updates and fallback accounting before the runner stops.
Reset clears the pending stop. This avoids comparing partial IN/OUT states
at the final frame, while retaining the raster transition and full CPU check.
The line renderer runs without SDL calls or heap allocations. Windows/SDL
presentation, filtering and the Light Phaser reticle consume the completed
buffer; original game-generated flashes remain intact.

The sprite limits and status flags follow the [Sega software reference](https://www.smspower.org/Development/SMSOfficialDocs).
Latch behavior and sprite evaluation were also checked against the
[SMS Plus GX implementation](https://github.com/libretro/smsplus-gx/blob/master/source/render.c).
Our renderer is original code; that implementation is a behavior reference,
not a bundled dependency.

## Sprite flicker and the optional Master System enhancement

Characters are composed from multiple sprites. The original eight-sprite line
limit can drop parts of a character, even when the CPU runs entirely as native
code. Games may reverse their sprite list each frame to alternate which parts
survive. That produces flicker resembling transparency; it does not imply an
interpreter fallback or a translation error.

A private Double Dragon route (exact ROM SHA256
`26290f94a597ad015da5b74e8d3649aa50b033c280c81fbfa460f947376b776a`)
reproduced up to 16 sprites on a line. Across 3,600 frames, 621 had overflowing
lines; 69,183 pixel positions differed between the original limit and the
expanded composition, summed across frames. Consecutive scanline traces show
the game reversing its sprite ordering. The user's follow-up demonstrated that
removing the limit alone did not settle overlapping characters. In 1,300 sampled
frames, 34 consecutive pairs had identical sprite geometry, patterns and palette
but different overlap pixels solely because their order changed. Comparing the
actual raster buffers before/after stabilization removed all 3,998 changed pixel
positions in those 34 pairs. These are finite scripted observations, not
whole-game qualification or visual acceptance.

New Master System exports offer **F5: sprite flicker reduction**. The initial
default retains the original limit; the choice is saved in the console's shared
video settings. When enabled, the renderer draws sprites beyond slot eight and
stabilizes confirmed rapidly reversing lists. At least 75% of the sprite
identities must match unambiguously between frames, with 95% of their pairwise
priorities agreeing on the direction, and two reversals within four frames are
needed. Small animation changes may add/remove or rearrange pieces. Only current
positions and pattern bytes are drawn; background priority and left blanking
remain active. A mid-frame attribute change bypasses stabilization, and a
priority change lasting more than eight frames is respected again. Ambiguous
identities or a scene/mode change discard the history.

Guest collision flags are calculated separately in the original SAT order,
using only its first eight eligible sprites. Extra sprites and stabilized
presentation order never affect collisions. Overflow still reports the ninth
sprite, whether it is drawn or not. Game Gear is unaffected.

This changes presentation rather than the cartridge's execution. There is no
frame blending, extra audio queue, ROM patch or per-title rendering exception.
It can change which character appears in front during a detected reversal
cycle; this is intentionally a display enhancement, not exact console behavior.
It cannot reconstruct sprites omitted by game software or remove all intentional
blinking. The [SMS Power developer discussion](https://www.smspower.org/forums/2535-VDPQuestion)
independently describes Double Dragon's repeated sprite-order reversal.
Presentation preference/history remain outside the game-state format; history
is relearned after F9/reset. F8/F9 retains the existing serialized fields and the
current host choice. Cartridge saves never enter the compilation snapshot.

The same route was checked with both CPU paths and both display choices:
CPU/RAM/banks/VDP/PSG/raster latches and the complete PCM stream matched, with
zero interpreter fallback on the native paths. Only pixel buffers are excluded
from the cross-mode machine comparison. This does not certify full VDP accuracy
or physical latency.

## Technical verification

`native/video_checks.c` contains authored, ROM-free VDP fixtures covering
palette splits, vblank preservation, horizontal/vertical scroll latches,
sprite priority/collision/overflow, wrap/zoom, border metadata and reset.
Both NTSC and PAL fixtures check H-INT, V-INT and V-counter boundaries.
They check numerical outputs without a window or screenshot.

`python tools/frame_stop_selftest.py` compiles an authored fixture for all
12 immediate, register and block I/O forms. Its 72 cases check frame limits
and host stop requests on native, reference and fallback paths, including
registers, RAM, completed instructions, fallback accounting and reset.

For an existing local conversion, run:

```powershell
python tools/video_selftest.py --report "path/to/conversion-report.json" --probe --frames 1800
```

The optional game probe records register/palette writes and completed frame
hashes on both CPU paths, using the existing game build. All diagnostic data
stays below `.build`. No visual review is performed by this tool.

To measure sprite overflow and compare the original/enhanced composition in an
existing Master System banked conversion:

```powershell
python tools/sms_sprite_selftest.py --report "path/to/conversion-report.json" --frames 3600
```

This diagnostic runs two CPU paths and two display choices without SDL video.
It records affected scanlines and their sprite order, verifies exact guest state
and PCM equality, and stores all private evidence in `.build/sms-sprite-selftest`.
The probe target is optional and never runs or creates logs in normal exports.

New conversion VDP traces contain `pixels_h` for each completed frame. A
different rendered frame or missing hash rejects the candidate before it
replaces an exported game, even if final registers and RAM happen to agree.
Legacy traces remain readable. Per-frame hashes compare the CPU paths; the
authored chip fixtures provide separate evidence for the rendering rules.

## Limits

This model processes scanlines, not individual VDP pixel clocks. Mid-line
palette changes are quantized to a line. Exact CRAM dots, VRAM-fetch contention,
SMS1-specific zoom/address quirks, other display modes and full PAL hardware
fidelity are not validated. A region label is a default timing choice, not
proof of the console a particular cartridge was played on. Full gameplay
validation remains separate, as does physical latency.

Bubble Bobble still performs many active-display VRAM writes in the headless
scenario. Real SMS VRAM has [limited CPU access slots while drawing](https://www.smspower.org/forums/18738-WritingToVDPAndVRAMOutsideVBLANK),
which this scanline model does not reproduce. Fewer active writes with PAL
timing do not by themselves prove that every transient black tile is fixed.
