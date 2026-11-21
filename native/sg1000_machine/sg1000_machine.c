/* The Sega SG-1000 machine (sg1000_machine.h). MIT, Retro-Recomp. */
#include "sg1000_machine.h"

#include <string.h>

static uint32_t fnv(uint32_t h, const uint8_t *p, size_t n)
{
    for (size_t i = 0; i < n; ++i)
        h = (h ^ p[i]) * 16777619u;
    return h;
}

void sg_init(SgMachine *m, const uint8_t *rom, uint32_t rom_size, unsigned lines_per_frame)
{
    memset(m, 0, sizeof *m);
    m->rom = rom;
    m->rom_size = rom_size;
    m->lines_per_frame = lines_per_frame;
    m->next_line = SG_CYCLES_PER_LINE;
    sn76489_reset(&m->psg, 0);
}

uint8_t sg_peek(const SgMachine *m, uint16_t address)
{
    if (address < 0xC000)
        return m->rom_size ? m->rom[address % m->rom_size] : 0xFF;
    return m->ram[address & (SG_RAM_SIZE - 1)];
}

uint8_t sg_read(SgMachine *m, uint16_t address)
{
    return sg_peek(m, address);
}

void sg_write(SgMachine *m, uint16_t address, uint8_t value)
{
    if (address >= 0xC000)
        m->ram[address & (SG_RAM_SIZE - 1)] = value;        /* the cartridge area is ROM: a write there goes nowhere */
}

/* Port DCh: pad 1 (up, down, left, right, 1, 2) in bits 0-5 and pad 2's up and down in bits 6-7; DDh: pad 2's left, right, 1, 2 in
 * bits 0-3. Active low: a button held reads 0. The bits no pad drives read 1. */
static uint8_t pad_port(const SgMachine *m, int second)
{
    uint8_t one = (uint8_t)(m->pad[0] & 0x3F), two = (uint8_t)(m->pad[1] & 0x3F);
    if (!second)
        return (uint8_t)~(one | ((two & 3) << 6));
    return (uint8_t)(0xF0 | (~(two >> 2) & 15));
}

uint8_t sg_in(SgMachine *m, uint8_t port)
{
    switch (port >> 6) {
    case 2:
        return (port & 1) ? tms9918_read_status(&m->vdp) : tms9918_read_data(&m->vdp);
    case 3:
        return pad_port(m, port & 1);
    default:
        return 0xFF;
    }
}

void sg_out(SgMachine *m, uint8_t port, uint8_t value)
{
    switch (port >> 6) {
    case 1:
        sn76489_run(&m->psg, m->cycles);                     /* the sound up to now, then the new register */
        sn76489_write(&m->psg, value);
        break;
    case 2:
        if (port & 1)
            tms9918_write_control(&m->vdp, value);
        else
            tms9918_write_data(&m->vdp, value);
        break;
    default:
        break;
    }
}

int sg_irq(const SgMachine *m)
{
    return tms9918_irq(&m->vdp);
}

void sg_pause(SgMachine *m)
{
    m->nmi_edge = 1;
}

int sg_nmi_edge(SgMachine *m)
{
    int edge = m->nmi_edge;
    m->nmi_edge = 0;
    return edge;
}

void sg_advance(SgMachine *m, uint64_t cycles)
{
    m->cycles += cycles;
    while (m->cycles >= m->next_line) {
        m->next_line += SG_CYCLES_PER_LINE;
        if (tms9918_line_end(&m->vdp, &m->line, m->lines_per_frame)) {
            ++m->frames;
            if (m->trace_frames) {           /* a running hash, so a divergence that reconverges still shows */
                uint32_t h = m->frame_trace ^ 2166136261u;
                const uint8_t *p = &m->vdp.frame[0][0];
                for (size_t i = 0; i < sizeof m->vdp.frame; ++i) h = (h ^ p[i]) * 16777619u;
                for (int i = 0; i < TMS_HEIGHT; ++i) h = (h ^ m->vdp.border[i]) * 16777619u;
                for (int i = 0; i < 8; ++i) h = (h ^ m->vdp.reg[i]) * 16777619u;
                m->frame_trace = (h ^ m->vdp.status) * 16777619u;
            }
        }
        if (m->line_hook)
            m->line_hook();
    }
    sn76489_run(&m->psg, m->cycles);
}

unsigned sg_audio_take(SgMachine *m, int16_t *out, unsigned max)
{
    return sn76489_take(&m->psg, out, max);
}

uint32_t sg_vram_hash(const SgMachine *m)
{
    return fnv(2166136261u, m->vdp.vram, sizeof m->vdp.vram);
}

uint32_t sg_ram_hash(const SgMachine *m)
{
    return fnv(2166136261u, m->ram, sizeof m->ram);
}

uint32_t sg_frame_hash(const SgMachine *m)
{
    return fnv(fnv(2166136261u, &m->vdp.frame[0][0], sizeof m->vdp.frame), m->vdp.border, sizeof m->vdp.border);
}

int sg_dump_frame(const SgMachine *m, FILE *out)
{
    return fwrite(m->vdp.frame, 1, sizeof m->vdp.frame, out) == sizeof m->vdp.frame
        && fwrite(m->vdp.border, 1, sizeof m->vdp.border, out) == sizeof m->vdp.border;
}

/* The fields of the machine's state a report compares, as JSON members (a comma and a space after each). */
void sg_print_state(const SgMachine *m, FILE *out)
{
    fprintf(out, "\"frame_trace\": %u, \"psg\": [%u, %u, %u, %u, %u, %u, %u, %u], \"audio_ticks\": %llu, ", m->frame_trace,
            m->psg.tone[0], m->psg.tone[1], m->psg.tone[2], m->psg.noise, m->psg.volume[0], m->psg.volume[1], m->psg.volume[2],
            m->psg.volume[3], (unsigned long long)m->psg.ticks);
}
