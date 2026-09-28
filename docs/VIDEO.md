# Master System video timing

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
