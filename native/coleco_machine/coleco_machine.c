/* The ColecoVision machine (coleco_machine.h). MIT, Retro-Recomp. */
#include "coleco_machine.h"

#include <string.h>

static uint32_t fnv(uint32_t h, const uint8_t *p, size_t n)
{
    for (size_t i = 0; i < n; ++i)
        h = (h ^ p[i]) * 16777619u;
    return h;
}

void cv_init(CvMachine *m, const uint8_t *bios, const uint8_t *rom, uint32_t rom_size, unsigned lines_per_frame)
{
    memset(m, 0, sizeof *m);
    m->bios = bios;
    m->rom = rom;
    m->rom_size = rom_size;
    m->lines_per_frame = lines_per_frame;
    m->next_line = CV_CYCLES_PER_LINE;
    sn76489_reset(&m->psg, 0);
}

uint8_t cv_peek(const CvMachine *m, uint16_t address)
{
    switch (address >> 13) {
    case 0:
        return m->bios ? m->bios[address] : 0xFF;
    case 3:
        return m->ram[address & (CV_RAM_SIZE - 1)];
    case 4: case 5: case 6: case 7:
        return m->rom_size ? m->rom[(uint32_t)(address - 0x8000u) % m->rom_size] : 0xFF;
    default:
        return 0xFF;                                        /* the expansion port: nothing there */
    }
}

uint8_t cv_read(CvMachine *m, uint16_t address)
{
    return cv_peek(m, address);
}

void cv_write(CvMachine *m, uint16_t address, uint8_t value)
{
    if ((address >> 13) == 3)
        m->ram[address & (CV_RAM_SIZE - 1)] = value;        /* the BIOS and the cartridge are ROM: a write there goes nowhere */
}

/* A controller's port, active low. Joystick mode: up, right, down, left in bits 0-3 and the left fire button in bit 6; keypad mode: the key's
 * code (the lines it pulls) in bits 0-3 and the right fire button in bit 6. Bits 4, 5 and 7 read 1. While the host's on-screen keypad is open
 * (CV_PAD_KEYPAD_OPEN) the stick and the fire buttons are not the game's: only the keypad's lines reach the port. */
static uint8_t controller(const CvMachine *m, int index)
{
    uint16_t pad = m->pad[index];
    unsigned lines;
    if (m->keypad_mode) {
        lines = (pad & CV_PAD_KEY_MASK) >> CV_PAD_KEY_SHIFT;
        if ((pad & CV_PAD_B2) && !(pad & CV_PAD_KEYPAD_OPEN))
            lines |= 0x40;
    } else {
        if (pad & CV_PAD_KEYPAD_OPEN)
            pad = 0;
        lines = (pad & CV_PAD_UP ? 1u : 0u) | (pad & CV_PAD_RIGHT ? 2u : 0u) | (pad & CV_PAD_DOWN ? 4u : 0u) | (pad & CV_PAD_LEFT ? 8u : 0u)
              | (pad & CV_PAD_B1 ? 0x40u : 0u);
    }
    return (uint8_t)~lines;
}

uint8_t cv_in(CvMachine *m, uint8_t port)
{
    switch (port & 0xE0) {
    case 0xA0:
        return (port & 1) ? tms9918_read_status(&m->vdp) : tms9918_read_data(&m->vdp);
    case 0xE0:
        return controller(m, (port & 2) ? 1 : 0);
    default:
        return 0xFF;
    }
}

void cv_out(CvMachine *m, uint8_t port, uint8_t value)
{
    switch (port & 0xE0) {
    case 0x80:
        m->keypad_mode = 1;
        break;
    case 0xC0:
        m->keypad_mode = 0;
        break;
    case 0xA0:
        if (port & 1)
            tms9918_write_control(&m->vdp, value);
        else
            tms9918_write_data(&m->vdp, value);
        break;
    case 0xE0:
        sn76489_run(&m->psg, m->cycles);                     /* the sound up to now, then the new register */
        sn76489_write(&m->psg, value);
        break;
    default:
        break;
    }
}

int cv_irq(const CvMachine *m)
{
    (void)m;
    return 0;                                                /* /INT is not wired on the ColecoVision */
}

int cv_nmi_edge(CvMachine *m)
{
    const int level = tms9918_irq(&m->vdp);
    const int edge = level && !m->nmi_level;
    m->nmi_level = (uint8_t)level;
    return edge;
}

void cv_advance(CvMachine *m, uint64_t cycles)
{
    m->cycles += cycles;
    while (m->cycles >= m->next_line) {
        m->next_line += CV_CYCLES_PER_LINE;
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

unsigned cv_audio_take(CvMachine *m, int16_t *out, unsigned max)
{
    return sn76489_take(&m->psg, out, max);
}

uint32_t cv_vram_hash(const CvMachine *m)
{
    return fnv(2166136261u, m->vdp.vram, sizeof m->vdp.vram);
}

uint32_t cv_ram_hash(const CvMachine *m)
{
    return fnv(2166136261u, m->ram, sizeof m->ram);
}

uint32_t cv_frame_hash(const CvMachine *m)
{
    return fnv(fnv(2166136261u, &m->vdp.frame[0][0], sizeof m->vdp.frame), m->vdp.border, sizeof m->vdp.border);
}

int cv_dump_frame(const CvMachine *m, FILE *out)
{
    return fwrite(m->vdp.frame, 1, sizeof m->vdp.frame, out) == sizeof m->vdp.frame
        && fwrite(m->vdp.border, 1, sizeof m->vdp.border, out) == sizeof m->vdp.border;
}

/* The fields of the machine's state a report compares, as JSON members (a comma and a space after each). */
void cv_print_state(const CvMachine *m, FILE *out)
{
    fprintf(out, "\"frame_trace\": %u, \"psg\": [%u, %u, %u, %u, %u, %u, %u, %u], \"audio_dropped\": %llu, ", m->frame_trace,
            m->psg.tone[0], m->psg.tone[1], m->psg.tone[2], m->psg.noise, m->psg.volume[0], m->psg.volume[1], m->psg.volume[2],
            m->psg.volume[3], (unsigned long long)m->psg.box.dropped);
}
