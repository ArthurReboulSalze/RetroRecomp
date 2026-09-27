/* A diagnostic ROM repeatedly executes IN ($DC)/IN ($DD), storing both bytes
 * in RAM. Check actual generated CPU execution against the reference CPU. */
#undef NDEBUG
#include <assert.h>
#include <stdio.h>
#include "glue.h"
#include "embedded_rom.h"
#include "include/sms_runtime.h"

int smsrecomp_take_reset_request(void) { return 0; }

int main(void) {
    const uint8_t states[] = {0, SMS_PAD_UP, SMS_PAD_DOWN, SMS_PAD_LEFT,
        SMS_PAD_RIGHT, SMS_PAD_B1, SMS_PAD_B2, 63};
    unsigned cases = 0;
    for (int a = 0; a < 8; ++a) for (int b = 0; b < 8; ++b) for (int reference = 0; reference < 2; ++reference) {
        assert(glue_load_rom("embedded")); glue_init(false, 2);
        glue_set_pad1(states[a]); glue_set_pad2(states[b]);
        if (reference) glue_run_interp(); else glue_run();
        assert(glue_frame_count() == 2);
        if (!reference) assert(smsrecomp_interpreter_cycles() == 0 && glue_dispatch_miss_count() == 0);
        assert(sms_read8(0xC000) == (uint8_t)~(states[a] | ((states[b] & 3) << 6)));
        assert(sms_read8(0xC001) == (uint8_t)~(states[b] >> 2));
        ++cases;
    }
    printf("PASS: %u CPU runs, both players independently read by IN ($DC)/IN ($DD); native has zero fallback.\n", cases);
    return 0;
}
