# Audio output

Master System and Game Gear exports synthesize the PSG from guest CPU cycles.
The host output is a separate stage: reducing its delay must not change the
console clock, PAL/NTSC frame pacing, PSG state, input polling or saved states.
This implementation is in `native/audio_output.inc` and is included by the
Master System / Game Gear adapter of the host kit (`native/hostkit/adapters/rrhk_sms.c`), unchanged by the move to the kit.
Game Boy has a separate output path described below; the
other console backends retain their own audio implementations.

## Game Boy output

Since 1.6.3 the Game Boy's sound output is the host kit's callback ring (`native/hostkit/shell/rrhk_ring.c`, extended to
interleaved stereo and a 10 ms start margin); the adapter `rrhk_gb.inc` hands it the samples the APU produced during each frame.
Before, `native/gb_audio_output.inc` held the same design (a deadline start, the adaptive reserve, 256-sample periods) for this
console alone. The APU, its 44.1 kHz PCM, saved state layout, CPU clock and input handling remain unchanged. The volume, mute
and output-device choice of the upstream settings panel are gone with the panel. This is a host output change
for all newly generated Game Boy games, not a cartridge-specific patch; the measurements below were taken on the former
output, and the A/B run of the kit's ring is in [HOST_KIT.md](HOST_KIT.md#phase-5-the-game-boy-163).

The callback starts one actual device period plus 10 ms after the first PCM,
including at a sample boundary inside a block. SDL is asked for 256 frames;
the actual backend period is accepted. Native F32 and S16 output preserve
sample order, amplitude, stereo, integer volume rounding and mute. Less common
formats fall back to SDL conversion. On the local WASAPI output the callback
uses 441 stereo float frames at 44.1 kHz, with a 20 ms scheduled start.

The existing 20 ms target only bounds exceptional backlogs; it no longer holds
startup until a second guest frame. Pause, reset, state loading and suspension
empty the ring and reset the deadline. An underrun fills the missing tail with
silence and re-primes playback. The callback does not execute guest code or
poll input, and starvation never accelerates the console.

`tools/gameboy_latency_selftest.py` runs 80 authored 2,000-frame timelines:
256/441/480/512/1,024-frame periods, 16 initial phases and up to 3 ms producer
jitter, with S16 and float PCM. All retain exact samples without underruns or
backlog removal; startup timing, ring wrap, volume, mute, starvation recovery,
pause reset, input sampling and concurrent producer/consumer checks also pass.

Super Mario Land 2's boot and varied-input runs each retain byte-identical
60-second raw APU captures and final guest-state JSON after 3,600 frames.
The conversion's four 3,600-frame coverage scenarios record zero interpreter
cycles; deep reference-CPU comparisons pass (30 boot frames and 240 per input
scenario). These checks do not establish complete gameplay or independent
hardware fidelity. Physical audiovisual latency and listening remain separate.

A silent ten-second replay on the real WASAPI device measured approximately
22 ms of source-timeline delay at the old callback and 13–16 ms with initial
3–6 ms margins. Those smaller margins passed the synthetic schedules but
showed short shortages in paced game runs. Following user listening feedback,
the final policy reserves 10 ms beyond the actual period (20 ms locally),
favoring stability over the lowest measured queue delay. Callback measurements
exclude GPU presentation, Windows mixing, the DAC and the speakers.

With the final margin, the same silent WASAPI replay measured 19.958 ms on
average (19.880–20.372 ms), with zero underrun or discarded samples. This is
about 4 ms more reserve than the preceding 6 ms-margin export, as requested
after listening. Super Mario Land 2 and Tetris are the targeted regenerated
exports; this does not regenerate the rest of the Game Boy collection.

Both final EXEs also completed separate 3,600-frame paced runs on WASAPI,
with a dummy video driver and muted output: their 60 one-second diagnostic
reports contained no underrun or discarded samples. Median sampled ring fill
was 10.9 ms for Super Mario Land 2 and 9.8 ms for Tetris; ring fill is not the
end-to-end latency. These runs check delivery stability without replacing
the user's listening and gameplay validation.

## Output path

The following section describes the shared Master System / Game Gear output.

The producer receives stereo S16 PSG samples at each completed guest video
frame, normally about 222–224 kHz. It converts them to the actual SDL device
frequency with a causal, normalized, 256-tap Blackman-windowed sinc filter and
128 fractional phases. An integer phase accumulator preserves duration across
arbitrary submission sizes. Matching source/device rates bypass conversion.
The filter has about 0.57 ms of group delay at the NTSC PSG rate and needs no
future-sample block. Conversion runs on the main thread; the device callback
only consumes prepared PCM and fills missing output with silence.

The stereo ring has a finite capacity and a smaller active high-water limit.
Playback starts one actual device callback period plus 3 ms after the first
converted PCM arrives. A performance-counter deadline lets the callback place
that start inside its output block, filling only the preceding samples with
silence. This avoids waiting for a second complete video frame. The reserve
covers callback granularity and scheduling jitter while the producer continues
to deliver complete PAL/NTSC frames. After an exceptional excess,
the oldest queued sound is discarded back to the target; guest execution is
never accelerated to feed the device. Reset, pause and state load clear both
the ring and filter history. A real underrun re-primes playback.

SDL is asked for 48 kHz, S16 stereo and 256 callback frames, with frequency,
sample-count and format changes allowed. S16 and native float output are
supported; conversion to float exactly preserves the S16 amplitudes and runs
inside the callback. On the tested WASAPI device this removes SDL's intermediate
S16-to-float stream. Other formats use the established SDL conversion fallback.
The actual backend period is accepted: locally 480 frames at 48 kHz, giving a
13 ms scheduled start. The abnormal-backlog target remains 31 ms and its limit
62 ms. These values describe **application buffering**, not the Windows mixer,
device, DAC, speakers or physical sound delay.

The former path used `SDL_AudioStream` and an unlimited `SDL_QueueAudio` queue.
The pinned SDL converter required substantial future input at this unusually
high PSG rate. The new path avoids that staging and prevents an indefinitely
growing output backlog. Smaller buffers alone would risk audible underruns;
the scheduled start and margin account for the producer's once-per-frame cadence.

SDL references: [audio devices](https://wiki.libsdl.org/SDL2/SDL_OpenAudioDevice),
[queued output](https://wiki.libsdl.org/SDL2/SDL_QueueAudio),
[queue measurement limitations](https://wiki.libsdl.org/SDL2/SDL_GetQueuedAudioSize).

## NES output continuity

`native/hostkit/shell/rrhk_ring.c` (the host kit's callback-ring output, first the NES host's own
`nes_audio_output.inc`) delivers the APU's existing 48 kHz mono PCM
through a bounded callback ring. The old host started an empty SDL queue
immediately and discarded a whole frame of new sound whenever the pending
queue exceeded 20 ms. Scheduling variation could therefore create gaps even
when all guest CPU execution was native.

The callback starts one actual device period plus 30 ms after the first block.
This margin favors continuity over the smallest possible buffer. SDL is asked
for 256 stereo frames and accepts S16 or native float; the mono sample is copied
unchanged to both channels. This avoids an intermediate mono/format conversion
on the tested WASAPI backend. Uncommon device formats still use SDL conversion.
The APU clock, synthesis, filtering, gain, game pacing and input remain unchanged.
Pause, reset and quick-state load clear the host queue and restart its deadline.
An exceptional catch-up backlog retains the newest bounded PCM; normal PAL/NTSC
bursts are no longer discarded just for crossing the old 20 ms threshold.

`tools/nes_audio_selftest.py` exercises 160 PAL/NTSC schedules with five device
periods, 16 initial phases and up to 12 ms producer jitter over 2,000 frames.
It verifies exact S16/F32 sample order and duplicated mono channels, no missing
or discarded PCM, ring wrap, empty output, flush and underrun recovery. A model
of the old queue on those same timelines exposes both missing and discarded
samples. The model is not a recording of a physical device.

NES conversions also compare exact 48 kHz PCM against the internal interpreter
during the existing CPU/frame-state comparisons. A missing, invalid or differing
capture fails the export. Successful temporary WAV files are removed; reports
retain only sample counts and SHA256. Agreement with the internal interpreter
does not independently validate the APU against hardware. Listening and physical
audiovisual latency remain separate checks.

The 11 October 2026 Super Mario Bros. qualification keeps the original PCM and
machine-state hashes byte-for-byte on two 1,200-frame captures (boot and scripted
play). Three 3,600-frame native-coverage paths report no interpreted cycles;
the internal reference comparisons also match PCM on 120 boot frames and 600
frames per play scenario.

A private, muted WASAPI run executes 3,600 paced game frames in 60.25 seconds,
with dummy video. The device supplies 480 stereo float frames at 48 kHz: the
software startup deadline is therefore 40 ms. It reports zero missing or
discarded samples. Earlier trials with smaller margins occasionally underrun
when the host loop stalls, so the final setting prioritizes continuity. This
silent test does not assess audible quality, real GPU presentation or physical
action-to-speaker latency; listening remains pending user validation.

## Adaptive output reserve (all consoles)

Every console player shares `native/audio_cushion.h`. It starts at +0 ms, so
a machine with headroom keeps the latency above. When a device period finds no
PCM while the guest is still producing (the last block arrived less than
100 ms earlier, so menus, loads and pauses do not count), or when a backlog
must be trimmed during playback because the device stalled, the start/re-prime
delay and the trim thresholds gain 5 ms, up to +60 ms. One step comes back
after a clean wait of twice the interval between the last two gaps: 4 s at
least, two minutes at most. A machine without gaps returns to +0 ms within
seconds; recurring scheduler hitches or a borderline machine keep the reserve
they need instead of re-priming in a loop. The cost is a few integer
operations per callback and one counter read per block.

- Master System/Game Gear, NES and Game Boy: callback rings (re-prime delay,
  trim thresholds); Super Nintendo and Neo Geo: the SDL queue is paused and
  re-primed when empty before a frame is queued; Mega Drive: the target of its
  rate-controlled bridge (25 ms) moves with the reserve; X68000: the queue now
  starts after one frame, one device period and 10 ms (it previously started
  with a single frame and no margin), plus the reserve.
- Exit summaries (`[host] audio … reserve=…`, `[player] audio reserve=…`)
  report the reserve reached. Guest audio, sample rates and timelines are
  unchanged. Physical latency remains unmeasured.

Debian, AMD A4-5000 with PulseAudio: Alex Kidd 40 s, one gap (133 samples);
Factory Panic 80 s, one gap; R-Type (X68000) two minutes after the new start
reserve, no gap. Listening remains the user's validation.

## Checks and limits

Run the ROM-free numeric checks after building the SDL dependency:

```powershell
python tools/audio_selftest.py
python tools/audio_selftest.py --device
```

The optional device check sends **silence** to the default audio output. No
window, screenshot or commercial ROM is used. Tests cover stereo FIFO/wrap,
overflow retaining recent sound, clearing/re-priming, exact sample counts at
44.1/48 kHz for PAL/NTSC source rates, chunk independence, impulse response,
DC and tone waveform/phase, and rejection of ultrasonic aliases.

A virtual cadence test exercises PAL/NTSC, callback periods of 256/480/1024
frames, 16 relative starting phases and up to 1 ms of producer jitter. The
tested combinations produced neither underruns nor trimming. A three-second
silent WASAPI run also had neither. Deliberate longer stalls can still produce
silence or trimming; normal system scheduling is not guaranteed by this test.

On 11 October 2026, an additional muted real-device replay delivered 600 frames
of Alex Kidd's captured PSG PCM through each host implementation. The average
PCM timeline delay measured at the callback was **27.019 ms before and
13.349 ms after**, with no underruns or trimming in either run. Producer
scheduling delays stayed below 2.5 ms. Both used WASAPI at 48 kHz with a
480-frame period; the new callback used the native float format. This measures
software delivery of precomputed game audio, not a microphone/loopback result,
actual video presentation or the total punch-to-speaker delay. The virtual
phase sweep independently changed from 16.875–30 ms to 13 ms with that period.
Numeric checks also verify float amplitude, stereo separation, ring wrapping
and silent underrun tails. After testing the rebuilt Alex Kidd export, the user
reported a clearly improved and much less distracting audio delay. That
listening result does not supply a numeric end-to-end latency measurement.

The following is historical evidence for the earlier bounded-ring change:

In a deliberately paused, eight-frame burst test, the old queue held 117.3 ms
of output. The new WASAPI ring stayed below its 62 ms high-water limit.
The new converter produced all 6,407 expected frames; the old streaming
converter had released 5,632, leaving about 16.1 ms of output equivalent pending.
This artificial stress case demonstrates bounded buffering and removed staging,
**not a measurement of normal gameplay or physical latency**.

Local Alex Kidd checks compared 600 demo frames and 600 scripted-play frames
before/after the host change. Raw PSG WAV data, VDP traces and final CPU states
were unchanged. Native CPU states also matched the reference CPU, with zero
fallback steps in those tested scenarios. Raw PSG identity does not establish
identical resampled waveforms or complete hardware fidelity. Listening/gameplay
validation and an external input-to-sound measurement remain separate checks.
The 11 October export again preserves the full raw PSG WAV and VDP traces on
both 600-frame runs, and passes strict/native-reference conversion checks over
3,600 frames per scenario. The PSG synthesis, frame clock and input path were
not changed by the host-buffer adjustment.

## Super Nintendo

The SNES adapter initializes the APU's absolute timeline at power-on and reset,
before the first CPU port exchange. Otherwise frame-boundary synchronization
does nothing during an early loader without port I/O: the remaining relative
catch-up can produce fewer DSP samples than the completed guest frame requires.
Authored WAI/interrupt fixtures exercise this without any commercial ROM or
APU port access. Each forty-frame run advances 683,520 APU cycles, with no
missing or discarded PCM frames and agreement with the reference CPU path.

The Windows host queues every prepared stereo block at 48 kHz. Its initial
reserve and upper pacing threshold include one guest frame plus the obtained
device callback period. A fixed 20 ms threshold previously allowed a whole
callback to drain much of that reserve before a more expensive frame ran.
The presentation sleep also ends early when waiting longer would consume the
reserve needed by the next frame. Input is sampled afterwards; the sound thread
does not execute CPU/APU instructions. The normal video deadline remains in use
when enough sound is queued, and the guest DSP buffer is unchanged.

With the tested 512-frame device period, the host threshold is about 27.3 ms.
This is a software queue budget, not end-to-end latency. SDL's queue count
excludes samples already passed to Windows and the device; see the
[SDL queue measurement contract](https://wiki.libsdl.org/SDL2/SDL_GetQueuedAudioSize).

Local muted WASAPI tests on 8 October 2026 exercised 1,200 frames each of Zelda,
Super Metroid and Donkey Kong Country. A test-only counted consumer, equivalent
to SDL's queue draining and feeding silence to the real device, recorded no
missing frames after the corrections. The earlier host recorded 54, 6 and 23
partial requests respectively in those runs; that does not imply every missing
sample was audible. The corrected runs also had no DSP underflows or ring drops.
Separate 600-frame native/reference comparisons matched for all three games.
Zelda and Super Metroid also matched on a 6,000-frame varied-input replay,
including CPU, video and PCM fingerprints, with no main-CPU or SPC fallback.
Reset checks reproduced the same picture sequence and PCM output after restart.
These checks measure sample delivery, not listening quality or physical latency.
