/* Shadow/highlight on the adapted Mega Drive VDP: replay the authored port writes of
 * tools/megadrive_shadow_selftest.py, render the grid, and print each 8x8 cell as [CRAM index, intensity].
 * A development check, outside the stamps: it is not compiled into a game. */
#include "genesis_vdp.h"
#include <stdio.h>
#include <stdlib.h>
#include "md_shadow_pattern.h"

unsigned machine_vdp_phase(void) { return 0; }

static GVDP vdp;
static uint8_t frame[128][GVDP_MAX_WIDTH];

int main(void) {
    gvdp_init(&vdp);
    gvdp_reset(&vdp);
    for (size_t i = 0; i < sizeof rr_shadow_writes / sizeof rr_shadow_writes[0]; ++i) {
        uint32_t w = rr_shadow_writes[i];
        if ((w >> 16) == 2) for (unsigned k = 0; k < 32768; ++k) gvdp_write_data(&vdp, 0);
        else if ((w >> 16) == 1) gvdp_write_data(&vdp, (uint16_t)w);
        else gvdp_write_control(&vdp, (uint16_t)w);
    }
    vdp.sprite_collision = 0;
    for (int line = 0; line < 128; ++line) gvdp_render_scanline(&vdp, line, frame[line]);
    int uniform = 1;
    printf("{\"grid\":[");
    for (int band = 0; band < 16; ++band) {
        printf("%s[", band ? "," : "");
        for (int col = 0; col < 16; ++col) {
            uint8_t px = frame[band * 8][col * 8];
            for (int y = 0; y < 8; ++y) for (int x = 0; x < 8; ++x)
                if (frame[band * 8 + y][col * 8 + x] != px) uniform = 0;
            const char *level = px >= GVDP_PALETTE_HIGHLIGHT ? "highlight" : px >= GVDP_PALETTE_SHADOW ? "shadow" : "normal";
            printf("%s[%u,\"%s\"]", col ? "," : "", (unsigned)(px & 63), level);
        }
        printf("]");
    }
    printf("],\"uniform\":%s,\"collision\":%u}\n", uniform ? "true" : "false", (unsigned)vdp.sprite_collision);
    return 0;
}
