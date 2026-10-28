# Retro-Recomp on Linux

This first native package targets **Linux x86-64, built on Debian 13
(glibc 2.41)**. Older distributions and ARM64 are not qualified yet. It uses the
same console implementations and verified compilation knowledge as Windows.

On Debian and Ubuntu, double-click the `.deb` package of the release (see
[installation](INSTALLING.md)). Elsewhere, use the per-user `.run` installer to
add Retro-Recomp to your applications menu:
`bash Retro-Recomp-<version>-linux-x86_64-install.run`. It installs without sudo in
`~/.local/opt/Retro-Recomp`, keeps the in-app updater writable and preserves your
games and settings on uninstall; `uninstall.sh` also offers to remove the build
tools and compiler caches (`--purge-tools` in scripts), and Options > Common >
Disk space does the same before removing the `.deb`. See [installation](INSTALLING.md).

For a portable copy, extract the archive into a writable local folder. Run `./Retro-Recomp` (or make
it executable with `chmod +x Retro-Recomp`). Python is included; no virtual
environment is needed to open the converter. To create or refresh a local
launcher with its icon after moving the folder, run
`./Retro-Recomp _install-launcher`. Dolphin may ask you to trust that launcher.
Generated games have their own cover launchers beside their native executables.
Since 1.5.0, a validated game ELF is packed with the bundled UPX 5.3.0 before it
is published, as on Windows, for every console including the X68000. UPX
restores the program in memory when it starts; `upx -d` gives the unpacked file
back. Sizes and start-up times measured on Debian are in
[BUILDING.md](BUILDING.md#linux-game-compression). If UPX cannot pack and test a
very large game (it happens with the 78 MB Metal Slug 3), the game is published
unpacked rather than failing the conversion; the conversion log and the report say so.

Conversion still requires the native build tools: `build-essential`, `cmake`,
`ninja-build`, `git`, `pkg-config`, `curl` and the SDL2 development dependencies
(X11, Wayland, ALSA, PulseAudio, udev, OpenGL/EGL/GLES, DRM/GBM, D-Bus). On
Debian and Ubuntu the converter checks them before the first conversion and,
with your consent, installs only the missing ones through `pkexec apt-get
install --no-install-recommends`, with a progress window; elsewhere it names
the missing commands. No console needs Rust/Cargo since 1.4.1. See
[BUILDING.md](BUILDING.md).
Keep Linux and Windows compiler caches separate. The package contains no ROM
or BIOS. Supply your own game files and, for Neo Geo, your BIOS.
Each game is built in its own folder under `.build` beside the converter
(`~/.local/opt/Retro-Recomp/.build` for the per-user install), removed once the
game is published, after its launcher has taken the game's icon. Folders left
by earlier versions or by failed conversions are removed from **Options ›
Common › Disk space**; see [build folders](BUILDING.md#build-folders).

Drag ROMs or folders into the main window, including filenames with spaces or
accents. The converter identifies consoles automatically and ignores duplicate
queue entries. Drops do not change a conversion already in progress.
The main window can shrink to 640 pixels high; the ROM list and log shrink with
it, while the action buttons remain accessible.

Cover downloads use the same front-cover preference, cache and curated links
as Windows. Public downloads need no account. Optional API credentials in
Options use the desktop's **Secret Service keyring** (for example GNOME Keyring
or a compatible KWallet service). Open and unlock that keyring first. If it is
unavailable, credentials are not saved as plaintext. The settings file holds
only a random keyring reference. API access requirements of each provider
still apply; Arcade Italia has no credential fields.

Use **Check for updates** to request a GitHub update. When the window opens, the
converter also looks (at most every 6 hours, quietly, downloading nothing) for a
new version and a new shared base, and shows a dot on the button; **Options ›
Common › Check for updates at startup** turns that off.
Only the Linux x86-64 asset is selected; its size, SHA-256, ELF architecture and
reported version are checked before installation. A temporary helper waits for
the converter to close, replaces it and restarts it. Installation failure rolls
back to the previous converter. `datas`, generated games and the local
compilation library are preserved.
In-game visual quality, gameplay, controller behavior and physical latency must
be checked on the target machine; compilation validation is a separate check.

## Runtime performance work

NES and SNES rendering and audio optimizations live in the shared console code
and apply to both Windows and Linux. They avoid repeated work while preserving
CPU and PPU events, every output pixel and the generated audio. NES mixing
reuses a DAC level only until a channel changes; accumulation and cartridge
audio still run every cycle. The SNES tile-row cache and active layer order
reset for each scanline and each live palette-bus snapshot. Hires rendering
computes each main/sub pair once. These caches never replace guest bus
transactions or become part of a save state.

With GCC on Linux, Mega Drive and SNES builds also optimize the hardware helpers
across source files using a short, private training run. Large generated game
bodies remain ordinary native objects. Compiler profiles are temporary, are
not compilation-library observations and are not exported. An incomplete
training run or failed final build stops the conversion. Normal game validation
still runs on the final, non-instrumented executable.

These changes require regenerating an existing game. Headless comparison times
measure engine work, not the framerate of a desktop session or physical latency.

The Mega Drive audio recovery path also avoids repeatedly dividing ring-buffer
indices during its correlation search. On the Debian test machine, the original
search could hold SDL's audio mutex for about 250 ms and block the game producer.
The replacement searches the same periods, in the same order, using scratch
allocated at initialization. Large searches use an exact integer convolution
under two prime moduli, with signed reconstruction of the original dot products.
The bridge inputs are normalized 16-bit samples, so their products and sums
can be reconstructed exactly. Small searches and unavailable optional workspace
retain the scalar path. Resampling, buffer targets, guest audio and console
timing are unchanged. The ROM-free bridge check compares complete output PCM,
loop choices and recovery behavior with the pinned implementation on both systems.
This establishes audio equivalence for those cases, not desktop framerate or
physical latency. The subsequent user-run Sonic measurements still showed slow
simulation and substantial host-audio waits, so those audio changes alone did
not resolve the reported slowdown.

On x86-64, the normal 5--25 ms recovery window now uses exact SSE2 packed
integer dot products. Pair products are extended to 64 bits before accumulation,
including the full-scale negative-input overflow case. The same periods,
normalization, tie order and output PCM are retained. Larger searches and other
architectures keep the modular-transform/scalar paths. No shorter search,
additional audio thread, larger buffer or guest clock change is introduced.
On the Debian machine, the 96-search authored workload takes about 0.18 seconds
instead of 0.39 with the preceding modular-transform implementation. This is an
isolated recovery-search measurement, not a Sonic speed or latency result.

For an explicitly requested host-output comparison, launch a Mega Drive game
with `RETRORECOMP_HOST_TEST_NO_AUDIO=1` to omit only its host sound device.
Guest PSG/YM synthesis and console timing still run. `SDL_RENDER_VSYNC=0` is the
separate SDL override for an unsynchronized display comparison. These diagnostic
overrides are process-local; normal launches keep their usual output settings.

The host audio sampler also walks contiguous ring spans and the FM/PSG mixer
advances its exact sample index with quotient/remainder increments. These avoid
per-tap and per-sample integer division without changing the signal. The 68000
decoder copies its ROM view only when a fallback decode is actually needed.

For a user-run timing investigation, `RETRORECOMP_TIMING_REPORT=<path>` writes
one small JSON report when the game closes. Counters stay in memory during play.
It separates event/queue waits, engine/audio delivery, drawing, presentation and
pacing; on Linux it also records the main thread's CPU time. This diagnostic is
off by default and does not change console speed or output settings.

Mega Drive also uses the existing tile-span renderer: shared tile addresses and
attributes are resolved once per span instead of for every pixel. A ROM-free
differential corpus compares 12,029,952 pixels plus sprite collision/overflow
flags with the scalar renderer, in both PAL and NTSC builds on Windows and
Linux. It covers scroll modes, window boundaries, interlace, priorities,
shadow/highlight and sprite limits. Raster-latch checks run on both paths.

The Z80 arbiter coalesces consecutive checkpoints only when no guest clock has
advanced and no bus request/reset or slice boundary intervenes. It retains all
actual memory transactions, DMA waits and instruction guards. Authored programs
compare CPU state, RAM, clocks and timestamped bus accesses against the original
checkpoint path. Pending-fetch mutation and save-state tests remain separate.
Guest CPU fibers remain on the same simulation thread; their coroutine library
therefore uses its single-thread configuration, matching the existing runtime
contract. None of these changes disables guest audio, skips rendered frames or
changes the console clock. Desktop speed and sound quality still require a new
user test of the regenerated executable.

At a completed Z80 instruction retirement, a main CPU which has already paid
the current slice also avoids an immediate host round trip. Fetches and waits
still suspend normally; the next instruction still returns at the slice limit.
The authored scheduler corpus retains the same state and timed transactions.

Within an active bus slice, an ordinary Z80 checkpoint can also call the same
68000 scheduler budget directly. The existing minicoro backend supports nested
resume/yield; the main CPU returns to its current caller before the ordinary
host owner is restored. The host still handles reset, ownership acknowledgement,
external bus requests and slice exits. A checkpoint already serviced before a
control change is not executed twice. No guest time is batched away, and portable
states still wait for both instructions to retire. The ROM-free corpus compares
the original, coalesced and nested paths, including shared RAM writes, bus control,
reset, suspended fetch changes, clock wrap and snapshot/parent replacement.
Reduced host transitions do not by themselves establish a game-speed improvement.

The tile-span path now expands eight indexed pixels with packed integer
arithmetic and composes sixteen pixels at a time with SSE2 on x86-64. It keeps
the scalar composition path on other targets. Palette indices, transparency,
priorities and shadow/highlight remain identical on the differential corpus.
These optimizations are shared with Windows. The synthetic 65,536-row rendering
workload on Debian takes about 0.72 seconds instead of 1.11 seconds with the
previous tile-span path. This isolated workload is not a Sonic framerate test.

The main 68000 step borrows its immutable translated instruction descriptor;
relocated RAM aliases and changed fetch images still receive a private copy.
Translated entries now also carry a small precomputed bus-preparation plan.
The native loop avoids recalculating invariant EA/control decisions while still
performing all live fetches, branch/privilege checks and bus waits. The separate
reference preparation and the 2,171-case synthetic prefetch corpus validate
the same states and transactions. This is shared Windows/Linux code, not a
change to console speed or a new audio thread. Preparation microbenchmarks
must not be presented as whole-game speed gains.
Condition flags are evaluated during prefetch preparation only for instructions
which use that result. An idle VDP advances its clock directly when no queued
write, DMA, asynchronous read or V-interrupt transition needs servicing.
The Z80 also retains its current continuation when the 68000 has already
completed the requested checkpoint. Real bus accesses, control changes, waits
and slice boundaries still pass through the scheduler. CPU, prefetch, bus,
save-state and DMA fixtures check these paths on both Windows and Debian.

The opt-in timing JSON additionally reports `md_cpu_bus_seconds`,
`md_vdp_raster_seconds` and `md_simulation_other_seconds`. The first two measure
elapsed raster-sized phases; the remainder includes chip synthesis and other
simulation work. Measurements are accumulated in memory and written at exit.
They are diagnostic phase timings, not a physical audio-latency measurement.
The audio fields `md_audio_lock_wait_seconds`, `md_audio_callback_seconds`,
`md_audio_callbacks` and `md_audio_stretch_events` separate producer blocking
from callback work and recovery frequency. Callback time belongs to the audio
thread and must not be added to the main-thread phase totals. These counters
are also opt-in, use the existing device lock and write only at shutdown.

The shared [runtime optimizations](RUNTIME_PERFORMANCE.md) also cover the other
profiles: per-span Sega tile rows, parallel NES sprite shifters, SNES bitplane
decoding, shared exact Scale2x and cheaper host audio conversion. Windows and
Debian run the same numeric output comparisons. Isolated workload speedups do
not establish whole-game framerate or physical latency on another machine.

## Build the package

Use native Linux Python 3.13 with Tk installed. In a virtual environment, install
`requirements.txt` and `PyInstaller==6.22.3`, then run
`python tools/package_linux.py`. The build audits allowlisted resources and all
compiled Retro-Recomp Python modules before replacing `Export/Retro-Recomp`.
The `.build/linux-package/audit.json` report records the executable hash and
build platform. The tarball contains only the converter and two usage/build guides.
