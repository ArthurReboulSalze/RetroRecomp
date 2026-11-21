/* The Amstrad CPC board's state: see cpc_state.h. MIT, Retro-Recomp. */
#include "cpc_state.h"

#include <stdlib.h>
#include <string.h>

#define CPC_STATE_MAGIC 0x31435043u              /* "CPC1" read little-endian */

/* A field the state must hold as the live machine has it (its version, its wiring): written, or checked equal. */
static void same(RetroStateIO *io, uint64_t live, unsigned width)
{
    uint64_t value = rr_state_word(io, live, width, UINT64_MAX);
    if (io->mode != RR_STATE_WRITE && value != live)
        io->ok = false;
}

static void bytes8(RetroStateIO *io, uint8_t *p, size_t n, uint64_t maximum)
{
    for (size_t i = 0; i < n; ++i)
        p[i] = (uint8_t)rr_state_word(io, p[i], 1, maximum);
}

/* An int64 as its two's complement in 8 bytes. */
static int64_t signed64(RetroStateIO *io, int64_t value)
{
    return (int64_t)rr_state_word(io, (uint64_t)value, 8, UINT64_MAX);
}

static void crtc_state(RetroStateIO *io, CpcCrtc *c)
{
    RR_FIELD(*c, type, 1, CPC_CRTC_TYPE2);
    bytes8(io, c->reg, sizeof c->reg, 0xFF);
    RR_FIELD(*c, select, 1, 31);
    RR_FIELD(*c, hcc, 1, 0xFF);
    RR_FIELD(*c, vcc, 1, 0xFF);
    RR_FIELD(*c, ra, 1, 0xFF);
    RR_FIELD(*c, adjust, 1, 0xFF);
    RR_FIELD(*c, in_adjust, 1, 1);
    RR_FIELD(*c, h_display, 1, 1);
    RR_FIELD(*c, v_display, 1, 1);
    RR_FIELD(*c, hsync, 1, 1);
    RR_FIELD(*c, hsync_count, 1, 0xFF);
    RR_FIELD(*c, vsync, 1, 1);
    RR_FIELD(*c, vsync_count, 1, 0xFF);
    RR_FIELD(*c, ma_row, 2, 0xFFFF);
    RR_FIELD(*c, ma_next, 2, 0xFFFF);
    RR_FIELD(*c, ma, 2, 0x3FFF);
}

static void ga_state(RetroStateIO *io, CpcGateArray *g)
{
    same(io, g->has_ram_pal, 1);
    RR_FIELD(*g, pen, 1, CPC_BORDER_PEN);
    bytes8(io, g->ink, sizeof g->ink, 31);
    RR_FIELD(*g, mode, 1, 3);
    RR_FIELD(*g, mode_next, 1, 3);
    RR_FIELD(*g, rom_config, 1, 0x0C);
    RR_FIELD(*g, ram_config, 1, 0x3F);
    RR_FIELD(*g, counter, 1, 63);
    RR_FIELD(*g, interrupt, 1, 1);
    RR_FIELD(*g, vsync_delay, 1, 2);
    RR_FIELD(*g, hsync, 1, 1);
    RR_FIELD(*g, vsync, 1, 1);
    RR_FIELD(*g, beam_x, 2, 0xFFFF);
    RR_FIELD(*g, beam_y, 2, 0xFFFF);
}

static void ppi_state(RetroStateIO *io, CpcPpi *p)
{
    RR_FIELD(*p, control, 1, 0xFF);
    RR_FIELD(*p, port_a, 1, 0xFF);
    RR_FIELD(*p, port_c, 1, 0xFF);
    RR_FIELD(*p, psg_data, 1, 0xFF);
    bytes8(io, p->keys, sizeof p->keys, 0xFF);
    bytes8(io, p->joystick, sizeof p->joystick, 0x3F);
}

static void fdc_state(RetroStateIO *io, Upd765 *f)
{
    same(io, f->tc_wired, 1);
    same(io, f->unit_mask, 1);
    RR_FIELD(*f, phase, 1, UPD765_RESULT);
    bytes8(io, f->cmd, sizeof f->cmd, 0xFF);
    RR_FIELD(*f, cmd_len, 1, sizeof f->cmd);
    RR_FIELD(*f, cmd_need, 1, sizeof f->cmd);
    bytes8(io, f->result, sizeof f->result, 0xFF);
    RR_FIELD(*f, result_len, 1, sizeof f->result);
    RR_FIELD(*f, result_pos, 1, sizeof f->result);
    bytes8(io, f->int_pending, sizeof f->int_pending, 1);
    bytes8(io, f->int_st0, sizeof f->int_st0, 0xFF);
    RR_FIELD(*f, command, 1, 31);
    RR_FIELD(*f, unit, 1, 3);
    RR_FIELD(*f, head, 1, 1);
    RR_FIELD(*f, mt, 1, 1);
    RR_FIELD(*f, sk, 1, 1);
    RR_FIELD(*f, c, 1, 0xFF);
    RR_FIELD(*f, h, 1, 0xFF);
    RR_FIELD(*f, r, 1, 0xFF);
    RR_FIELD(*f, n, 1, 0xFF);
    RR_FIELD(*f, eot, 1, 0xFF);
    RR_FIELD(*f, dtl, 1, 0xFF);
    RR_FIELD(*f, st0, 1, 0xFF);
    RR_FIELD(*f, st1, 1, 0xFF);
    RR_FIELD(*f, st2, 1, 0xFF);
    RR_FIELD(*f, at_end, 1, 1);
    RR_FIELD(*f, format_left, 1, 0xFF);
    RR_FIELD(*f, format_fill, 1, 0xFF);
    bytes8(io, f->format_id, sizeof f->format_id, 0xFF);
    RR_FIELD(*f, sector, 2, DSK_MAX_SECTORS - 1);
    RR_FIELD(*f, copy, 1, 0xFF);
    RR_FIELD(*f, track_left, 1, 0xFF);
    RR_FIELD(*f, pos, 4, 0x10000);
    RR_FIELD(*f, length, 4, 0x10000);
    RR_FIELD(*f, weak_reads, 4, 0xFFFFFFFFu);
    RR_FIELD(*f, commands, 4, 0xFFFFFFFFu);
    RR_FIELD(*f, boot_reads, 4, 0xFFFFFFFFu);
    RR_FIELD(*f, unmodelled, 4, 0xFFFFFFFFu);
    for (int d = 0; d < UPD765_DRIVES; ++d) {
        Upd765Drive *drive = &f->drive[d];
        same(io, drive->image != NULL, 1);                        /* a state made with the same disks in the drives */
        RR_FIELD(*drive, write_protected, 1, 1);
        RR_FIELD(*drive, written, 1, 1);
        RR_FIELD(*drive, pcn, 1, DSK_MAX_CYLINDERS - 1);
        RR_FIELD(*drive, position, 1, DSK_MAX_SECTORS_PER_TRACK - 1);
    }
}

static void ay_state(RetroStateIO *io, CpcMachine *m)
{
    static const uint8_t mask[16] = { 0xFF, 0x0F, 0xFF, 0x0F, 0xFF, 0x0F, 0x1F, 0xFF, 0x1F, 0x1F, 0x1F, 0xFF, 0xFF, 0x0F,
                                      0xFF, 0xFF };
    Ay38910 *ay = &m->ay;
    RR_FIELD(*ay, ticks, 4, 0xFFFFFFFFu);
    for (int c = 0; c < 3; ++c) {
        ay->tone_count[c] = (uint16_t)rr_state_word(io, ay->tone_count[c], 2, 0xFFFF);
        ay->tone_out[c] = (uint8_t)rr_state_word(io, ay->tone_out[c], 1, 1);
    }
    RR_FIELD(*ay, noise_count, 2, 0xFFFF);
    RR_FIELD(*ay, lfsr, 4, 0x1FFFF);
    RR_FIELD(*ay, env_count, 2, 0xFFFF);
    RR_FIELD(*ay, env_step, 1, 15);
    RR_FIELD(*ay, env_up, 1, 1);
    RR_FIELD(*ay, env_holding, 1, 1);
    for (int r = 0; r < 16; ++r)
        m->ay_reg[r] = (uint8_t)rr_state_word(io, m->ay_reg[r], 1, mask[r]);
    RR_FIELD(*m, ay_latch, 1, 16);
    RR_FIELD(*m, ay_next, 8, UINT64_MAX);
    m->ay_left = (int)rr_state_word(io, (uint64_t)m->ay_left, 2, 0xFFFF);
    m->ay_right = (int)rr_state_word(io, (uint64_t)m->ay_right, 2, 0xFFFF);
    AudioBox *box = &m->audio;
    RR_FIELD(*box, time, 8, UINT64_MAX);
    RR_FIELD(*box, next_sample, 8, UINT64_MAX);
    same(io, box->step, 8);
    box->acc[0] = signed64(io, box->acc[0]);
    box->acc[1] = signed64(io, box->acc[1]);
    RR_FIELD(*box, acc_cycles, 8, UINT64_MAX);
}

int cpc_machine_state(CpcMachine *m, RetroStateIO *io)
{
    same(io, CPC_STATE_MAGIC, 4);
    same(io, CPC_STATE_VERSION, 1);
    rr_state_bytes(io, m->ram, sizeof m->ram);
    crtc_state(io, &m->crtc);
    ga_state(io, &m->ga);
    ppi_state(io, &m->ppi);
    fdc_state(io, &m->fdc);
    ay_state(io, m);
    RR_FIELD(*m, upper_rom, 1, 0xFF);
    RR_FIELD(*m, motor, 1, 1);
    RR_FIELD(*m, phase, 1, 3);
    RR_FIELD(*m, frame_ready, 1, 1);
    RR_FIELD(*m, cycles, 8, UINT64_MAX);
    RR_FIELD(*m, frames, 8, UINT64_MAX);
    return io->ok ? 0 : 1;
}

size_t cpc_state_size(const CpcMachine *m)
{
    static uint8_t scratch[CPC_RAM_BYTES + 4096];
    RetroStateIO io = { scratch, sizeof scratch, 0, RR_STATE_WRITE, true };
    cpc_machine_state((CpcMachine *)m, &io);                      /* writing reads the machine only */
    return io.ok ? io.pos : 0;
}

size_t cpc_state_save(const CpcMachine *m, uint8_t *out, size_t capacity)
{
    RetroStateIO io = { out, capacity, 0, RR_STATE_WRITE, true };
    cpc_machine_state((CpcMachine *)m, &io);
    return io.ok ? io.pos : 0;
}

int cpc_state_load(CpcMachine *m, const uint8_t *in, size_t size)
{
    /* RR_FIELD assigns as it reads, in CHECK as in APPLY: the check runs on a copy, so a refused state leaves the machine as it
     * was. */
    static CpcMachine copy;
    memcpy(&copy, m, sizeof copy);
    RetroStateIO check = { (uint8_t *)in, size, 0, RR_STATE_CHECK, true };
    cpc_machine_state(&copy, &check);
    if (!check.ok || check.pos != size)
        return 0;
    RetroStateIO apply = { (uint8_t *)in, size, 0, RR_STATE_APPLY, true };
    cpc_machine_state(m, &apply);
    cpc_rebuild(m);
    return apply.ok;
}

uint64_t cpc_state_digest(const CpcMachine *m)
{
    static uint8_t scratch[CPC_RAM_BYTES + 4096];
    size_t n = cpc_state_save(m, scratch, sizeof scratch);
    uint64_t h = 1469598103934665603ull;
    for (size_t i = 0; i < n; ++i) { h ^= scratch[i]; h *= 1099511628211ull; }
    return n ? h : 0;
}
