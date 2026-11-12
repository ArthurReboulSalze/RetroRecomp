/* The MSX machine, CPU-independent (see msx_machine.h). MIT, Retro-Recomp. */
#include "msx_machine.h"

#include <string.h>

static void rebuild_regions(MsxMachine *m)
{
    ++m->generation;
    for (int i = 0; i < 8; ++i) {
        int page = i >> 1;
        int p = (m->primary >> (page * 2)) & 3;
        int s = m->expanded[p] ? (m->secondary[p] >> (page * 2)) & 3 : 0;
        const MsxDevice *d = &m->slot[p][s];
        MsxRegion *r = &m->region[i];
        uint32_t start = (uint32_t)i << 13;
        r->primary = (uint8_t)p;
        r->secondary = (uint8_t)s;
        r->read = NULL;
        r->write = NULL;
        r->device = 0;
        if (d->kind == MSX_DEV_RAM && d->ram) {
            r->read = d->ram + start;
            r->write = d->ram + start;
        } else if (d->kind == MSX_DEV_ROM && d->rom) {
            if (d->block[i] >= 0)
                r->read = d->rom + (uint32_t)d->block[i] * 0x2000u;
            r->device = d->mapper != MSX_MAPPER_PLAIN;          /* writes reach the mapper */
            if (d->mapper == MSX_MAPPER_KONAMI_SCC && d->scc_on && i == 4)
                r->read = NULL;                                 /* 9800h-9FFFh answer from the SCC */
        }
    }
}

void msx_init(MsxMachine *m, unsigned lines_per_frame)
{
    memset(m, 0, sizeof *m);
    m->lines_per_frame = lines_per_frame ? lines_per_frame : MSX_LINES_NTSC;
    msx_reset(m);
}

void msx_set_device(MsxMachine *m, int primary, int secondary, MsxDevice device)
{
    MsxDevice *d = &m->slot[primary & 3][secondary & 3];
    *d = device;
    if (d->kind == MSX_DEV_ROM) {
        uint32_t unit = d->mapper == MSX_MAPPER_ASCII16 ? 0x4000u : 0x2000u;
        d->size = (d->size + unit - 1) & ~(unit - 1);   /* whole banks: the caller's buffer holds the FFh padding */
        msx_cart_reset(d);
    }
    m->scc_count = 0;
    for (int p = 0; p < 4; ++p)
        for (int s = 0; s < 4; ++s)
            if (m->slot[p][s].kind == MSX_DEV_ROM && m->slot[p][s].mapper == MSX_MAPPER_KONAMI_SCC && m->scc_count < 4)
                m->scc[m->scc_count++] = &m->slot[p][s];
    rebuild_regions(m);
}

void msx_set_expanded(MsxMachine *m, int primary, int expanded)
{
    m->expanded[primary & 3] = (uint8_t)(expanded != 0);
    rebuild_regions(m);
}

void msx_reset(MsxMachine *m)
{
    m->primary = 0;
    memset(m->secondary, 0, sizeof m->secondary);
    m->port_c = 0;
    memset(m->keys, 0xFF, sizeof m->keys);
    m->psg_latch = 0;
    memset(m->psg, 0, sizeof m->psg);
    m->joystick[0] = m->joystick[1] = 0x3F;
    memset(&m->vdp, 0, sizeof m->vdp);
    m->line = 0;
    m->cycles = 0;
    m->next_line = MSX_CYCLES_PER_LINE;
    m->frames = 0;
    msx_psg_reset(m);
    for (int p = 0; p < 4; ++p)
        for (int s = 0; s < 4; ++s)
            if (m->slot[p][s].kind == MSX_DEV_ROM)
                msx_cart_reset(&m->slot[p][s]);
    rebuild_regions(m);
}

void msx_print_state(const MsxMachine *m, FILE *out)
{
    fprintf(out, "\"psg\": [");
    for (int i = 0; i < 16; ++i) fprintf(out, "%s%u", i ? ", " : "", m->psg[i]);
    fprintf(out, "], \"psg_latch\": %u, \"port_c\": %u, \"blocks\": [", m->psg_latch, m->port_c);
    int first = 1;
    for (int p = 0; p < 4; ++p)
        for (int s = 0; s < 4; ++s) {
            const MsxDevice *d = &m->slot[p][s];
            if (d->kind != MSX_DEV_ROM) continue;
            fprintf(out, "%s[%d, %d", first ? "" : ", ", p, s);
            for (int i = 0; i < 8; ++i) fprintf(out, ", %d", d->block[i]);
            fprintf(out, ", %u, %u, %u, %u]", d->scc_on, d->scc.enable, d->scc.period[0], d->scc.volume[0]);
            first = 0;
        }
    fprintf(out, "], \"frame_trace\": %u, ", m->frame_trace);
}

void msx_key(MsxMachine *m, int row, int bit, int down)
{
    if (row < 0 || row >= MSX_KEY_ROWS || bit < 0 || bit > 7)
        return;
    uint8_t mask = (uint8_t)(1u << bit);
    m->keys[row] = (uint8_t)(down ? (m->keys[row] & ~mask) : (m->keys[row] | mask));
}

void msx_joystick(MsxMachine *m, int port, uint8_t active_low)
{
    m->joystick[port & 1] = (uint8_t)(active_low & 0x3F);
}

/* FFFFh is the secondary-slot register of the primary slot selected in page 3, when that slot is expanded. */
static int secondary_register(const MsxMachine *m)
{
    int p = (m->primary >> 6) & 3;
    return m->expanded[p] ? p : -1;
}

uint8_t msx_read(MsxMachine *m, uint16_t address)
{
    if (address == 0xFFFF) {
        int p = secondary_register(m);
        if (p >= 0)
            return (uint8_t)~m->secondary[p];
    }
    const MsxRegion *r = &m->region[address >> 13];
    if (r->read)
        return r->read[address & 0x1FFF];
    if (r->device)
        return msx_cart_read(&m->slot[r->primary][r->secondary], address);
    ++m->unmapped_reads;
    return 0xFF;
}

uint8_t msx_peek(const MsxMachine *m, uint16_t address)
{
    if (address == 0xFFFF) {
        int p = secondary_register(m);
        if (p >= 0)
            return (uint8_t)~m->secondary[p];
    }
    const MsxRegion *r = &m->region[address >> 13];
    if (r->read)
        return r->read[address & 0x1FFF];
    return r->device ? msx_cart_read(&m->slot[r->primary][r->secondary], address) : 0xFF;
}

void msx_write(MsxMachine *m, uint16_t address, uint8_t value)
{
    if (address == 0xFFFF) {
        int p = secondary_register(m);
        if (p >= 0) {
            m->secondary[p] = value;
            rebuild_regions(m);
            return;
        }
    }
    MsxRegion *r = &m->region[address >> 13];
    if (r->write) {
        r->write[address & 0x1FFF] = value;
    } else if (r->device) {
        if (m->cart_write_hook)
            m->cart_write_hook(m->hook_user, address, value);
        msx_psg_catch_up(m);                      /* an SCC register write sounds from now on */
        if (msx_cart_write(&m->slot[r->primary][r->secondary], address, value))
            rebuild_regions(m);
    } else {
        ++m->dropped_writes;
    }
}

uint8_t msx_slot_of(const MsxMachine *m, uint16_t address)
{
    const MsxRegion *r = &m->region[address >> 13];
    return (uint8_t)((m->expanded[r->primary] ? 0x80 : 0) | (r->secondary << 2) | r->primary);
}

/* TMS9918A ports 98h (VRAM data) and 99h (control and status). */
static uint8_t vdp_read_data(MsxVdp *v)
{
    uint8_t value = v->readahead;
    v->readahead = v->vram[v->address];
    v->address = (uint16_t)((v->address + 1) & 0x3FFF);
    v->latch = 0;
    return value;
}

static void vdp_write_data(MsxVdp *v, uint8_t value)
{
    v->vram[v->address] = value;
    v->readahead = value;
    v->address = (uint16_t)((v->address + 1) & 0x3FFF);
    v->latch = 0;
}

static uint8_t vdp_read_status(MsxVdp *v)
{
    uint8_t value = v->status;
    v->status &= 0x1F;        /* the frame flag, the fifth-sprite flag and the collision flag clear on a read */
    v->latch = 0;
    return value;
}

/* Bits the TMS9918A keeps in each register (the others read as zero in our model). */
static const uint8_t vdp_masks[8] = { 0x03, 0xFB, 0x0F, 0xFF, 0x07, 0x7F, 0x07, 0xFF };

static void vdp_write_control(MsxVdp *v, uint8_t value)
{
    if (!v->latch) {
        /* The MSX1 VDP has no real latch for the address: the first byte is the low address byte at once. */
        v->address = (uint16_t)((v->address & 0x3F00) | value);
        v->first = value;
        v->latch = 1;
        return;
    }
    v->latch = 0;
    if (value & 0x80) {
        v->reg[value & 7] = (uint8_t)(v->first & vdp_masks[value & 7]);
        /* A register write also loads the high address bits (TMS99x8 behaviour some MSX1 programs rely on). */
        v->address = (uint16_t)(((value << 8) | (v->address & 0xFF)) & 0x3FFF);
    } else {
        v->address = (uint16_t)(v->first | ((value & 0x3F) << 8));
        if (!(value & 0x40)) {     /* read setup: the VDP prefetches the first byte */
            v->readahead = v->vram[v->address];
            v->address = (uint16_t)((v->address + 1) & 0x3FFF);
        }
    }
}

/* Bits of each AY-3-8910 register: coarse periods 4 bits, noise and volumes 5, envelope shape 4. */
static const uint8_t psg_masks[16] = { 0xFF, 0x0F, 0xFF, 0x0F, 0xFF, 0x0F, 0x1F, 0xFF,
                                       0x1F, 0x1F, 0x1F, 0xFF, 0xFF, 0x0F, 0xFF, 0xFF };

uint8_t msx_in(MsxMachine *m, uint8_t port)
{
    switch (port) {
    case 0x98: return vdp_read_data(&m->vdp);
    case 0x99: return vdp_read_status(&m->vdp);
    case 0xA2:
        if (m->psg_latch == 14) {
            int connector = (m->psg[15] >> 6) & 1;
            return (uint8_t)((m->joystick[connector] & 0x3F) | m->key_layout);
        }
        return m->psg_latch < 16 ? m->psg[m->psg_latch] : 0xFF;
    case 0xA8: return m->primary;
    case 0xA9: {
        int row = m->port_c & 0x0F;
        return row < MSX_KEY_ROWS ? m->keys[row] : 0xFF;
    }
    case 0xAA: return m->port_c;
    default: return 0xFF;
    }
}

void msx_out(MsxMachine *m, uint8_t port, uint8_t value)
{
    switch (port) {
    case 0x98: vdp_write_data(&m->vdp, value); break;
    case 0x99: vdp_write_control(&m->vdp, value); break;
    case 0xA0: m->psg_latch = value; break;
    case 0xA1: if (m->psg_latch < 16) msx_psg_write(m, m->psg_latch, (uint8_t)(value & psg_masks[m->psg_latch])); break;
    case 0xA8: m->primary = value; rebuild_regions(m); break;
    case 0xAA: msx_psg_catch_up(m); m->port_c = value; break;   /* bit 7 is the key click: sound up to now first */
    case 0xAB:
        msx_psg_catch_up(m);
        if (!(value & 0x80)) {     /* bit set/reset on port C */
            uint8_t bit = (uint8_t)(1u << ((value >> 1) & 7));
            m->port_c = (uint8_t)((value & 1) ? (m->port_c | bit) : (m->port_c & ~bit));
        }
        break;
    default: break;
    }
}

int msx_irq(const MsxMachine *m)
{
    return (m->vdp.status & 0x80) && (m->vdp.reg[1] & 0x20);
}

void msx_advance(MsxMachine *m, uint64_t cycles)
{
    m->cycles += cycles;
    while (m->cycles >= m->next_line) {
        m->next_line += MSX_CYCLES_PER_LINE;
        if (m->line < MSX_HEIGHT)            /* the line that just ended is drawn with the state it ended with */
            msx_vdp_draw_line(m, (int)m->line);
        if (m->line == MSX_HEIGHT - 1)       /* sprites of line 192: flags only, before the frame flag */
            msx_vdp_check_line(m, MSX_HEIGHT);
        if (++m->line == MSX_VBLANK_LINE)
            m->vdp.status |= 0x80;
        if (m->line == m->lines_per_frame) {
            m->line = 0;
            ++m->frames;
            if (m->trace_frames) {           /* a running hash, so a divergence that reconverges still shows */
                uint32_t h = m->frame_trace ^ 2166136261u;
                const uint8_t *p = &m->vdp.frame[0][0];
                for (size_t i = 0; i < sizeof m->vdp.frame; ++i) h = (h ^ p[i]) * 16777619u;
                for (int i = 0; i < MSX_HEIGHT; ++i) h = (h ^ m->vdp.border[i]) * 16777619u;
                for (int i = 0; i < 8; ++i) h = (h ^ m->vdp.reg[i]) * 16777619u;
                m->frame_trace = (h ^ m->vdp.status) * 16777619u;
            }
        }
        if (m->line_hook)
            m->line_hook();
    }
    msx_psg_catch_up(m);
}
