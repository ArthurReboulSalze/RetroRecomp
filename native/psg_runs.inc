/* Included in the staged SN76489 before psg_advance(). Renders `count`
 * frames exactly as `count` sn_render_frame() calls would. Between channel
 * events (a counter reaching zero) every amplitude stays as it is, so only
 * the per-frame low-pass recurrence runs, once for both sides when they carry
 * the same signal and state. A settled filter (unchanged input and output)
 * repeats its output for the rest of the run. */
static int32_t rr_psg_lpf_run(int32_t mix, int32_t *y_state, int32_t *prev_state,
                              int16_t *out, size_t run, int both)
{
    int32_t y = *y_state, prev = *prev_state;
    for (size_t i = 0; i < run; ++i) {
        int64_t lp = ((int64_t)(mix + prev) * SN_LPF_SAMPLE_MAGIC
                    + (int64_t)y * SN_LPF_OUTPUT_MAGIC) / 65536;
        int32_t value = (int32_t)lp;
        if (value >  32767) value =  32767;
        if (value < -32768) value = -32768;
        int settled = prev == mix && value == y;
        prev = mix;
        y = value;
        out[i * 2] = (int16_t)value;
        if (both) out[i * 2 + 1] = (int16_t)value;
        if (settled) {
            for (size_t j = i + 1; j < run; ++j) {
                out[j * 2] = (int16_t)value;
                if (both) out[j * 2 + 1] = (int16_t)value;
            }
            break;
        }
    }
    *y_state = y;
    *prev_state = prev;
    return y;
}

static void rr_psg_render_frames(SN76489 *p, int16_t *out, size_t count)
{
    while (count > 0) {
        /* sn_tick() changes an output only when a counter reaches zero. */
        int32_t next = p->noise_counter;
        for (int i = 0; i < 3; i++) if (p->tone_counter[i] < next) next = p->tone_counter[i];
        if (next <= 1) {
            sn_render_frame(p, out, out + 1);
            out += 2;
            count--;
            continue;
        }
        size_t run = (size_t)(next - 1) < count ? (size_t)(next - 1) : count;
        int32_t amp[4];
        for (int i = 0; i < 3; i++) {
            p->tone_counter[i] -= (int32_t)run;
            amp[i] = p->tone_out[i] ? SN_VOL[p->vol[i]] : -SN_VOL[p->vol[i]];
        }
        p->noise_counter -= (int32_t)run;
        amp[3] = p->noise_out ? SN_VOL[p->vol[3]] : -SN_VOL[p->vol[3]];
        int32_t mixL = 0, mixR = 0;
        uint8_t m = p->gg_stereo;
        for (int i = 0; i < 4; i++) {
            if (m & (uint8_t)(0x10 << i)) mixL += amp[i];
            if (m & (uint8_t)(0x01 << i)) mixR += amp[i];
        }
        if (mixL == mixR && p->lpf_yL == p->lpf_yR && p->lpf_prevL == p->lpf_prevR) {
            rr_psg_lpf_run(mixL, &p->lpf_yL, &p->lpf_prevL, out, run, 1);
            p->lpf_yR = p->lpf_yL;
            p->lpf_prevR = p->lpf_prevL;
        } else {
            rr_psg_lpf_run(mixL, &p->lpf_yL, &p->lpf_prevL, out, run, 0);
            rr_psg_lpf_run(mixR, &p->lpf_yR, &p->lpf_prevR, out + 1, run, 0);
        }
        out += run * 2;
        count -= run;
    }
}

