# Animated credits and module playback

Included in release 1.1.4. The final presentation and music were approved by the
project owner before publication.

The credits use the application's charcoal, white and gold palette. Native Tk
canvas primitives draw a fast perspective starfield with short approaching
streaks, rotating wireframes, moving waves and a
perspective grid. Waves, cubes and the floor now move four times faster than the
first preview, independently of the readable credit roll. The two wireframe
cubes travel across the stage, bouncing at its edges. Their camera
distance varies independently, changing their size and brightness as they
approach and recede; projected corners remain within the stage after resizing.
The 64 stars use one forward-facing perspective. They fade into view across a
broad distant plane and approach along the camera's depth axis, keeping the
field spread out without unrelated sideways directions or a dense central dot.
Two small shaded checker spheres bounce on the music's percussion: gold for
kick and silver for snare, with a small damped ripple for hats. Explicit sample
roles cover all three supplied MODs, including Pocket Signals' catalog-named
percussion. Native per-instrument hit counters follow decoded tracker ticks,
including delayed notes, without guessing from held-note volumes. The animation
adapts jump duration to recent hits; muting consumes hits without producing jumps.
Perspective-scaled sizes, ground shadows and a slight squash on landing complete
the effect. Canvas meshes are reused
throughout the animation. Each console retains its own centered credit cell and links.
The automatic roll pauses on wheel, keyboard or scrollbar input. It resumes only
when requested; hovering a link temporarily holds the text so it can be clicked.
Closing the dialog releases the animation timer and audio device.

The three supplied ChipLoom compositions are original four-channel `M.K.` MOD
files under `MEDIAS/trackers_chiploom`. A random selection excludes the previous
track, including across application restarts. The sound button and last selection
use a small `datas/credits-player.json`; no updates are written during playback.
The author credit remains discreet, followed by a link to
[ChipLoom](https://github.com/ArthurReboulSalze/ChipLoom).

Playback uses **libxmp-lite 4.7.3**, also used as a reference by ChipLoom, with
**miniaudio 0.11.23** for native device output. Patterns, sample loops, notes and
effects are decoded live at 48 kHz stereo, with spline interpolation. There is no
WAV/MP3 conversion, FFmpeg process, web view, downloaded player or network access
when opening credits. Music has its own native callback; Tk is never responsible
for filling the audio buffer. An unavailable device leaves the credits usable.
The frame-buffer assembly used to observe percussion is checked against the full
reference decoder for identical PCM; synchronization is decorative, not a claim
of sample-accurate alignment with physical audio output.

Build the native player with `python tools/build_credits_audio.py`. The script
downloads pinned sources and verifies their SHA-256 values. CMake and a native
C compiler are build dependencies only. Both converter packaging scripts embed
the resulting library and the three MODs. The player, soundtrack and UI modules
are excluded from generated-game compiler inputs. They are never linked into
generated games. Full third-party notices are available from the credits screen.

Validation: `python -m unittest tests.test_credits tests.test_languages` and
`python tools/credits_selftest.py`. Optional `--reference <libxmp-library>` compares
three minutes of each supplied track byte for byte with the full reference
decoder; `--device` checks native playback/mute/close. These checks do not replace
listening and the user's approval of the animated presentation.
