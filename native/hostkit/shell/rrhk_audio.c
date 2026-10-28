/* Audio output of the windowed loop. Queue model (the 16-bit machines): one queued device at
 * 48 kHz stereo, a priming reserve, and the pacing that keeps the picture from running ahead of
 * the sound; the machine hands over 48 kHz stereo PCM. Ring model (the NES): the machine's mono
 * PCM goes through rrhk_ring.c. Each machine's source rate and layout stay its own business. */
#ifndef SDL_MAIN_HANDLED
#define SDL_MAIN_HANDLED
#endif
#include <SDL.h>
#include <stdio.h>
#include <string.h>
#include "hostkit/hostkit_internal.h"

void rrhk_audio_open(RrhkRun *run) {
    const RrhkMachine *m = run->machine;
    SDL_AudioSpec want = {0};
    memset(&run->have, 0, sizeof run->have);
    if (m->audio_model == RRHK_AUDIO_RING) {
        run->audio = 0;
        run->audio_playing = false;
        if (!run->video_clock_test && rrhk_ring_open(m->audio_rate)) {
            if (!m->audio_enable || m->audio_enable(m->audio_rate)) { rrhk_ring_start(); run->audio = rrhk_ring_device(); }
            else rrhk_ring_close();
        }
        return;
    }
    want.freq = m->audio_rate ? (int)m->audio_rate : 48000; want.format = AUDIO_S16SYS; want.channels = 2; want.samples = 512;
    run->audio = 0;
    /* A dummy audio device's callback timer is not a calibrated 48 kHz
     * oscillator. The explicit test-only mode isolates the video deadline;
     * guest APU/DSP execution and PCM consumption still run normally. */
    if (!m->own_audio && !run->video_clock_test) run->audio = SDL_OpenAudioDevice(NULL, 0, &want, &run->have, 0);
    /* One guest frame is shorter than two device callbacks. Start with a
     * frame plus one device period, so a callback at an unlucky phase does
     * not exhaust the queue before the next frame can provide its sound.
     * This is output priming only; the guest DSP buffer is unchanged. */
    run->audio_preroll = ((Uint32)(run->have.freq * m->frame_seconds) + run->have.samples) * 4;
    run->audio_playing = false;
    /* Starts at +0 ms; grows only when a period finds the queue empty. */
    memset(&run->cushion, 0, sizeof run->cushion);
}

void rrhk_audio_pause_output(RrhkRun *run) {
    if (run->machine->audio_model == RRHK_AUDIO_RING) { rrhk_ring_clear(); return; }
    rrhk_options_audio_reset();
    if (!run->audio) return;
    SDL_PauseAudioDevice(run->audio, 1);
    SDL_ClearQueuedAudio(run->audio);
    run->audio_playing = false;
}

/* The loop did not run the machine this time (a menu is open). */
void rrhk_audio_idle(RrhkRun *run) {
    if (run->machine->audio_model == RRHK_AUDIO_RING) rrhk_ring_clear();
    else if (run->audio_playing) rrhk_audio_pause_output(run);
}

/* Bytes waiting in the device queue; 0 without a device or on the ring model. */
unsigned rrhk_audio_queued(const RrhkRun *run) {
    return run->audio && run->machine->audio_model == RRHK_AUDIO_QUEUE ? SDL_GetQueuedAudioSize(run->audio) : 0;
}

/* The sound of the frame just run, from the machine to the device. The ring model drains the
 * machine until it has nothing more; the queue model takes one block. */
void rrhk_audio_frame(RrhkRun *run) {
    const RrhkMachine *m = run->machine;
    int16_t pcm[4096]; size_t n;
    if (m->audio_model == RRHK_AUDIO_RING) {
        while ((n = m->audio(pcm, 4096)) > 0)
            if (run->audio) rrhk_ring_submit(pcm, (uint32_t)n);
        return;
    }
    n = m->audio(pcm, 4096);
    if (n && run->audio) rrhk_audio_push(run, pcm, n);
    /* A machine that may hold more than one buffer of sound per frame (the X68000's batches) is asked again while it fills one. */
    while (m->audio_chunked && n == 4096 && (n = m->audio(pcm, 4096)) > 0)
        if (run->audio) rrhk_audio_push(run, pcm, n);
}

/* Preserve every produced block. If the host catches up after a scheduling
 * delay, wait for a little room before sampling inputs and running the next
 * frame instead of discarding ~17 ms of sound. SDL drains whole device
 * periods. Keep a guest frame plus one such period before starting work: a
 * fixed 20 ms threshold could lose 10.7 ms in one callback and leave too
 * little for a costly frame. */
void rrhk_audio_wait_room(RrhkRun *run) {
    run->audio_target = run->audio_preroll + rr_cushion_frames(&run->cushion, (Uint32)run->have.freq) * 4;
    if (run->audio && run->audio_playing && !rrhk.menu && !rrhk.paused) {
        Uint64 until = SDL_GetTicks64() + 20;
        while (SDL_GetQueuedAudioSize(run->audio) > run->audio_target && SDL_GetTicks64() < until)
            SDL_Delay(1);
    }
}

/* `samples` int16 values (frames * 2) from the machine, through the audio filter and into the queue. */
void rrhk_audio_push(RrhkRun *run, int16_t *pcm, size_t samples) {
    rrhk_options_audio(pcm, (unsigned)(samples / 2), 2, false, run->have.freq);
    /* Only our pushes refill the queue: empty now means the device
     * ran dry since the last frame. Re-prime with a larger reserve. */
    if (run->audio_playing && !SDL_GetQueuedAudioSize(run->audio)) {
        if (rr_cushion_gap(&run->cushion))
            run->audio_target = run->audio_preroll + rr_cushion_frames(&run->cushion, (Uint32)run->have.freq) * 4;
        SDL_PauseAudioDevice(run->audio, 1); run->audio_playing = false;
    } else if (run->audio_playing) rr_cushion_clean(&run->cushion, (Uint32)(samples / 2), (Uint32)run->have.freq);
    rr_cushion_pushed(&run->cushion);
    if (SDL_QueueAudio(run->audio, pcm, (Uint32)(samples * sizeof(int16_t))) != 0) {
        SDL_CloseAudioDevice(run->audio); run->audio = 0; run->audio_playing = false;
    } else if (!run->audio_playing && SDL_GetQueuedAudioSize(run->audio) >= run->audio_target) {
        SDL_PauseAudioDevice(run->audio, 0); run->audio_playing = true;
    }
}

/* Video and the sound device have independent clocks. Do not sleep through
 * the remaining audio reserve: recover the lead before the next guest frame
 * instead of inserting silence or making the DSP run ahead. Retain the
 * normal video deadline whenever the device queue has enough sound. */
void rrhk_audio_pace(RrhkRun *run, Uint64 now) {
    if (!run->audio || !run->audio_playing) return;
    Uint32 queued = SDL_GetQueuedAudioSize(run->audio);
    Uint64 spare = queued > run->audio_target ? queued - run->audio_target : 0;
    Uint64 audio_deadline = now + spare * run->frequency / ((Uint64)run->have.freq * 4);
    if (run->next > audio_deadline) run->next = audio_deadline;
}

void rrhk_audio_close(RrhkRun *run) {
    if (run->machine->audio_model == RRHK_AUDIO_RING) { rrhk_ring_close(); return; }
    if (run->audio && SDL_AtomicGet(&run->cushion.raises))
        fprintf(stderr, "[host] audio reserve=+%d ms (raised %d times); physical latency unmeasured\n",
            rr_cushion_ms(&run->cushion), SDL_AtomicGet(&run->cushion.raises));
    if (run->audio) SDL_CloseAudioDevice(run->audio);
}
