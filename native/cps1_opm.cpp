/* YM2151 wrapper over ymfm; see cps1_opm.h. */
#include "cps1_opm.h"
#include "ymfm_opm.h"

#include <cstring>
#include <new>
#include <vector>

namespace {

class interface_t : public ymfm::ymfm_interface {
public:
    cps1_opm_irq irq = nullptr;
    void *context = nullptr;
    int32_t timer[2] = {-1, -1};   /* clocks left, -1 = stopped */
    uint64_t now = 0, busy_end = 0;

    void ymfm_set_timer(uint32_t tnum, int32_t duration_in_clocks) override
    {
        timer[tnum & 1] = duration_in_clocks;
    }
    void ymfm_set_busy_end(uint32_t clocks) override { busy_end = now + clocks; }
    bool ymfm_is_busy() override { return now < busy_end; }
    void ymfm_update_irq(bool asserted) override
    {
        if (irq) irq(context, asserted ? 1 : 0);
    }
    /* One output sample spans 64 chip clocks. */
    void advance(int32_t clocks)
    {
        for (uint32_t index = 0; index < 2; index++) {
            if (timer[index] < 0) continue;
            timer[index] -= clocks;
            if (timer[index] <= 0) {
                timer[index] = -1;
                m_engine->engine_timer_expired(index);
            }
        }
    }
};

}  // namespace

struct cps1_opm {
    interface_t intf;
    ymfm::ym2151 chip;
    cps1_opm() : chip(intf) {}
};

extern "C" {

cps1_opm *cps1_opm_create(cps1_opm_irq irq, void *context)
{
    cps1_opm *opm = new (std::nothrow) cps1_opm();
    if (!opm) return nullptr;
    opm->intf.irq = irq;
    opm->intf.context = context;
    opm->chip.reset();
    return opm;
}

void cps1_opm_destroy(cps1_opm *chip) { delete chip; }

void cps1_opm_reset(cps1_opm *chip)
{
    chip->intf.timer[0] = chip->intf.timer[1] = -1;
    chip->intf.now = chip->intf.busy_end = 0;
    chip->chip.reset();
}

uint8_t cps1_opm_read(cps1_opm *chip, uint32_t offset, uint64_t now)
{
    chip->intf.now = now;
    return chip->chip.read(offset);
}

void cps1_opm_write(cps1_opm *chip, uint32_t offset, uint8_t data, uint64_t now)
{
    chip->intf.now = now;
    chip->chip.write(offset, data);
}

void cps1_opm_generate(cps1_opm *chip, int32_t *left, int32_t *right)
{
    ymfm::ym2151::output_data output;
    chip->chip.generate(&output, 1);
    chip->intf.advance(64);
    *left = output.data[0];
    *right = output.data[1];
}

size_t cps1_opm_save(cps1_opm *chip, uint8_t *buffer, size_t capacity)
{
    std::vector<uint8_t> data;
    ymfm::ymfm_saved_state state(data, true);
    chip->chip.save_restore(state);
    size_t extra = sizeof chip->intf.timer + sizeof chip->intf.busy_end;
    if (!buffer) return data.size() + extra;
    if (capacity < data.size() + extra) return 0;
    std::memcpy(buffer, data.data(), data.size());
    std::memcpy(buffer + data.size(), chip->intf.timer, sizeof chip->intf.timer);
    std::memcpy(buffer + data.size() + sizeof chip->intf.timer, &chip->intf.busy_end, sizeof chip->intf.busy_end);
    return data.size() + extra;
}

int cps1_opm_load(cps1_opm *chip, const uint8_t *buffer, size_t size)
{
    size_t extra = sizeof chip->intf.timer + sizeof chip->intf.busy_end;
    if (size < extra) return 0;
    std::vector<uint8_t> data(buffer, buffer + size - extra);
    ymfm::ymfm_saved_state state(data, false);
    chip->chip.save_restore(state);
    std::memcpy(chip->intf.timer, buffer + data.size(), sizeof chip->intf.timer);
    std::memcpy(&chip->intf.busy_end, buffer + data.size() + sizeof chip->intf.timer, sizeof chip->intf.busy_end);
    chip->chip.invalidate_caches();
    return 1;
}

}  // extern "C"
