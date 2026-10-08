# Audio output

Master System and Game Gear exports synthesize the PSG from guest CPU cycles.
The host output is a separate stage: reducing its delay must not change the
console clock, PAL/NTSC frame pacing, PSG state, input polling or saved states.
This implementation is in `native/audio_output.inc` and is included by the
shared Sega host. Other console backends retain their own audio implementations.

## Output path

The producer receives stereo S16 PSG samples at each completed guest video
frame, normally about 222–224 kHz. It converts them to the actual SDL device
frequency with a causal, normalized, 256-tap Blackman-windowed sinc filter and
128 fractional phases. An integer phase accumulator preserves duration across
arbitrary submission sizes. Matching source/device rates bypass conversion.
The filter has about 0.57 ms of group delay at the NTSC PSG rate and needs no
future-sample block. Conversion runs on the main thread; the device callback
only consumes prepared PCM and fills missing output with silence.

The stereo ring has a finite capacity and a smaller active high-water limit.
It primes with 21 ms plus one actual device callback period, covering PAL
frame delivery and callback scheduling. Its high-water margin allows another
video frame and one device period. After an exceptional excess,
the oldest queued sound is discarded back to the target; guest execution is
never accelerated to feed the device. Reset, pause and state load clear both
the ring and filter history. A real underrun re-primes playback.

SDL is asked for 48 kHz, S16 stereo and 256 callback frames, with frequency and
sample-count changes allowed. The actual backend period is accepted. For the
tested WASAPI device this was 480 frames at 48 kHz: a 31 ms priming target and
62 ms high-water limit. These values describe **application buffering**, not
the Windows mixer, device, DAC, speakers or physical sound delay.

The former path used `SDL_AudioStream` and an unlimited `SDL_QueueAudio` queue.
The pinned SDL converter required substantial future input at this unusually
high PSG rate. The new path avoids that staging and prevents an indefinitely
growing output backlog. Smaller buffers alone would risk audible underruns;
the priming and margin account for the producer's once-per-frame cadence.

SDL references: [audio devices](https://wiki.libsdl.org/SDL2/SDL_OpenAudioDevice),
[queued output](https://wiki.libsdl.org/SDL2/SDL_QueueAudio),
[queue measurement limitations](https://wiki.libsdl.org/SDL2/SDL_GetQueuedAudioSize).

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
