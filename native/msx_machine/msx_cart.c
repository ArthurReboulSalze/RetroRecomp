/* MSX cartridges: plain ROM placement, the Konami, Konami SCC, ASCII 8 KB and ASCII 16 KB mappers, and the Konami SCC
 * sound chip. MIT, Retro-Recomp. Written from the documented behaviour of these mappers and of the SCC (MSX Resource
 * Center wiki, the measurements by Jon De Schrijder and NYYRIKKI quoted in openMSX's SCC.cc); openMSX was read to
 * settle details (RomPlain.cc, RomKonami.cc, RomKonamiSCC.cc, RomAscii8kB.cc, RomAscii16kB.cc, RomBlocks.cc),
 * nothing was copied from it.
 *
 * Banks: a block number past the end of the image wraps with a mask (the image size in blocks minus one; 31 for the
 * Konami chip, which decodes 256 KB) and gives FFh when it is still past the end. Mirrors outside 4000h-BFFFh: Konami
 * repeats 4000h-7FFFh at 0000h and 8000h-BFFFh at C000h; Konami SCC the other way round; the ASCII mappers leave pages
 * 0 and 3 empty. The SCC: a channel steps through its 32 samples once every period + 1 CPU cycles (so a tone of
 * 3,579,545 / (32 x (period + 1)) Hz); a period below 9 stops it; writing a period restarts the current sample; a
 * new volume is taken at the next sample; a channel's output is sample x volume with its low four bits dropped. The
 * deformation register (E0h-FFh) is not modelled. A channel's output is latched: a wave-RAM write at the sample being
 * played sounds from the next step, a volume from the next step or the next period write. */
#include "msx_machine.h"

#include <string.h>

static int blocks8(const MsxDevice *d) { return (int)(d->size / 0x2000u); }

static int16_t resolve(int count, int mask, int block)
{
    if (block >= count)
        block &= mask;
    return block < count ? (int16_t)block : (int16_t)-1;
}

static void set8(MsxDevice *d, int region, int block, int mask)
{
    d->block[region] = resolve(blocks8(d), mask, block);
}

static void konami_switch(MsxDevice *d, int region, int block)
{
    int mask = d->mapper == MSX_MAPPER_KONAMI ? 31 : blocks8(d) - 1;
    set8(d, region, block, mask);
    int mirror = d->mapper == MSX_MAPPER_KONAMI ? (region < 4 ? region - 2 : region + 2)
                                                : (region < 4 ? region + 4 : region - 4);
    d->block[mirror] = d->block[region];
}

static void ascii16_switch(MsxDevice *d, int page, int block)
{
    int count = (int)((d->size + 0x3FFFu) / 0x4000u);    /* a last half bank reads the padding */
    int16_t b = resolve(count, count - 1, block);
    d->block[page * 2] = b < 0 ? -1 : (int16_t)(b * 2);
    d->block[page * 2 + 1] = b < 0 ? -1 : (int16_t)(b * 2 + 1);
}

void msx_cart_reset(MsxDevice *d)
{
    for (int i = 0; i < 8; ++i)
        d->block[i] = -1;
    d->scc_on = 0;
    memset(&d->scc, 0, sizeof d->scc);
    for (int c = 0; c < 5; ++c)
        d->scc.volume[c] = d->scc.volume_now[c] = 15;          /* wave RAM 0, so every latched output is 0 */
    switch (d->mapper) {
    case MSX_MAPPER_PLAIN: {
        unsigned first = d->base / 0x2000u, count = d->size / 0x2000u;
        for (unsigned region = 0; region < 8; ++region) {
            unsigned block = region - first;      /* wraps below the base: then only the mirror can map it */
            if (block < count)
                d->block[region] = (int16_t)block;
            else if (d->mirrored && count)
                d->block[region] = (int16_t)(block & (count - 1));
        }
        break;
    }
    case MSX_MAPPER_KONAMI:
    case MSX_MAPPER_KONAMI_SCC:
        for (int region = 2; region < 6; ++region)
            konami_switch(d, region, region - 2);
        break;
    case MSX_MAPPER_ASCII8:
        for (int region = 2; region < 6; ++region)
            set8(d, region, 0, blocks8(d) - 1);
        break;
    case MSX_MAPPER_ASCII16:
        ascii16_switch(d, 1, 0);
        ascii16_switch(d, 2, 0);
        break;
    default:
        break;
    }
}

static void scc_write(MsxScc *s, uint8_t address, uint8_t value)
{
    if (address < 0x80) {
        s->wave[address >> 5][address & 31] = (int8_t)value;
        return;
    }
    if (address >= 0xA0)
        return;                                   /* A0h-DFh nothing; E0h-FFh deformation: not modelled */
    unsigned r = address & 0x0F;
    if (r < 10) {
        unsigned c = r >> 1;
        s->period[c] = (uint16_t)((r & 1) ? ((s->period[c] & 0x0FF) | ((value & 0x0F) << 8))
                                          : ((s->period[c] & 0xF00) | value));
        s->count[c] = 0;                          /* a period write restarts the current sample, at the new volume */
        s->volume_now[c] = s->volume[c];
        s->out[c] = (int16_t)((s->wave[c < 4 ? c : 3][s->pos[c]] * s->volume_now[c]) >> 4);
    } else if (r < 15) {
        s->volume[r - 10] = value & 15;
    } else {
        s->enable = value & 0x1F;
    }
}

int msx_cart_write(MsxDevice *d, uint16_t address, uint8_t value)
{
    switch (d->mapper) {
    case MSX_MAPPER_KONAMI:
        if (address >= 0x6000 && address < 0xC000) {
            konami_switch(d, address >> 13, value);
            return 1;
        }
        return 0;
    case MSX_MAPPER_KONAMI_SCC: {
        if (address < 0x5000 || address >= 0xC000)
            return 0;
        if (d->scc_on && address >= 0x9800 && address < 0xA000) {
            scc_write(&d->scc, (uint8_t)address, value);
            return 0;
        }
        int changed = 0;
        if ((address & 0xF800) == 0x9000) {
            uint8_t on = (value & 0x3F) == 0x3F;
            changed = on != d->scc_on;
            d->scc_on = on;
        }
        if ((address & 0x1800) == 0x1000) {
            konami_switch(d, address >> 13, value);
            changed = 1;
        }
        return changed;
    }
    case MSX_MAPPER_ASCII8:
        if (address >= 0x6000 && address < 0x8000) {
            set8(d, ((address >> 11) & 3) + 2, value, blocks8(d) - 1);
            return 1;
        }
        return 0;
    case MSX_MAPPER_ASCII16:
        if (address >= 0x6000 && address < 0x7800 && !(address & 0x0800)) {
            ascii16_switch(d, ((address >> 12) & 1) + 1, value);
            return 1;
        }
        return 0;
    default:
        return 0;
    }
}

uint8_t msx_cart_read(const MsxDevice *d, uint16_t address)
{
    if (d->mapper == MSX_MAPPER_KONAMI_SCC && d->scc_on && address >= 0x9800 && address < 0xA000) {
        uint8_t a = (uint8_t)address;
        return a < 0x80 ? (uint8_t)d->scc.wave[a >> 5][a & 31] : 0xFF;
    }
    int16_t block = d->block[address >> 13];
    return block < 0 ? 0xFF : d->rom[(uint32_t)block * 0x2000u + (address & 0x1FFF)];
}

int msx_scc_step(MsxScc *s, unsigned cycles)
{
    int sum = 0;
    for (int c = 0; c < 5; ++c) {
        unsigned period = s->period[c];
        if (period >= 9) {                        /* below 9 the channel does not move */
            s->count[c] = (uint16_t)(s->count[c] + cycles);
            int stepped = 0;
            while (s->count[c] > period) {
                s->count[c] = (uint16_t)(s->count[c] - (period + 1));
                s->pos[c] = (uint8_t)((s->pos[c] + 1) & 31);
                stepped = 1;
            }
            if (stepped) {                        /* the sample and the volume are taken when the channel steps */
                s->volume_now[c] = s->volume[c];
                s->out[c] = (int16_t)((s->wave[c < 4 ? c : 3][s->pos[c]] * s->volume_now[c]) >> 4);
            }
        }
        if (s->enable & (1u << c))
            sum += s->out[c];                     /* sample x volume, low four bits dropped (arithmetic shift: floor) */
    }
    return sum;                                   /* -600 to +595 */
}
