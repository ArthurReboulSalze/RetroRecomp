/* Appended to a local copy of the pinned PSG; its dependency stays unchanged. */
#include "state_io.h"
void smsrecomp_psg_state(RetroStateIO *io) {
    SN76489 s = s_sn;
    for (int i = 0; i < 3; ++i) {
        s.tone_period[i] = (uint16_t)rr_state_word(io, s.tone_period[i], 2, 1023);
        s.tone_counter[i] = (int32_t)rr_state_word(io, (uint32_t)s.tone_counter[i], 4, 1023);
        s.tone_out[i] = (uint8_t)rr_state_word(io, s.tone_out[i], 1, 1);
    }
    for (int i = 0; i < 4; ++i) s.vol[i] = (uint8_t)rr_state_word(io, s.vol[i], 1, 15);
    RR_FIELD(s, noise_ctrl, 1, 7); RR_FIELD(s, noise_counter, 4, 1023);
    RR_FIELD(s, lfsr, 2, UINT16_MAX); RR_FIELD(s, noise_out, 1, 1);
    RR_FIELD(s, latch, 1, 7); RR_FIELD(s, gg_stereo, 1, UINT8_MAX);
    s.lpf_yL = (int32_t)rr_state_word(io, (uint32_t)s.lpf_yL, 4, UINT32_MAX);
    s.lpf_prevL = (int32_t)rr_state_word(io, (uint32_t)s.lpf_prevL, 4, UINT32_MAX);
    s.lpf_yR = (int32_t)rr_state_word(io, (uint32_t)s.lpf_yR, 4, UINT32_MAX);
    s.lpf_prevR = (int32_t)rr_state_word(io, (uint32_t)s.lpf_prevR, 4, UINT32_MAX);
    if (s.lpf_yL < -32768 || s.lpf_yL > 32767 || s.lpf_prevL < -32768 || s.lpf_prevL > 32767 ||
        s.lpf_yR < -32768 || s.lpf_yR > 32767 || s.lpf_prevR < -32768 || s.lpf_prevR > 32767) io->ok = false;
    uint32_t leftover = (uint32_t)rr_state_word(io, s_leftover_z80_cycles, 4, 15);
    size_t read = (size_t)rr_state_word(io, s_scratch_read, 4, PSG_SCRATCH_FRAMES);
    size_t write = (size_t)rr_state_word(io, s_scratch_write, 4, PSG_SCRATCH_FRAMES);
    if (read > write) io->ok = false;
    for (unsigned i = 0; i < PSG_SCRATCH_FRAMES * 2; ++i) {
        int16_t sample = (int16_t)rr_state_word(io, (uint16_t)s_scratch[i], 2, UINT16_MAX);
        if (io->mode == RR_STATE_APPLY && io->ok) s_scratch[i] = sample;
    }
    if (io->mode == RR_STATE_APPLY && io->ok) {
        s_sn = s; s_inited = 1; s_leftover_z80_cycles = leftover;
        s_scratch_read = read; s_scratch_write = write;
    }
}
