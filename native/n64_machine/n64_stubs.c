/* Retro-Recomp Nintendo 64: empty entry points of the renderers that are not compiled. Original Retro-Recomp code, MIT.
 *
 * GLideN64 (GPL-2.0-only) and angrylion (no commercial use) are left out of every build (licenses/mupen64plus-next.md); the core's
 * plugin table and libretro.c still name their functions. The session always selects the ParaLLEl RDP, so none of these runs. */
#include <stdbool.h>
#include <stddef.h>
#include "m64p_types.h"
#include "m64p_plugin.h"

m64p_error gln64PluginGetVersion(m64p_plugin_type *type, int *version, int *api, const char **name, int *caps)
{
    (void)type; (void)version; (void)api; (void)name; (void)caps;
    return M64ERR_UNSUPPORTED;
}
void gln64ChangeWindow(void) {}
int gln64InitiateGFX(GFX_INFO info) { (void)info; return 0; }
void gln64MoveScreen(int x, int y) { (void)x; (void)y; }
void gln64ProcessDList(void) {}
void gln64ProcessRDPList(void) {}
void gln64RomClosed(void) {}
int gln64RomOpen(void) { return 0; }
void gln64ShowCFB(void) {}
void gln64UpdateScreen(void) {}
void gln64ViStatusChanged(void) {}
void gln64ViWidthChanged(void) {}
void gln64ReadScreen2(void *dest, int *width, int *height, int front) { (void)dest; *width = 0; *height = 0; (void)front; }
void gln64DestroyGfxContext(void) {}
void gln64ReinitGfxContext(void) {}
void gln64_thr_gl_invoke_command_loop(void) {}
bool threaded_gl_safe_shutdown = false;
bool glsm_ctl(int state, void *data) { (void)state; (void)data; return false; }
void gln64SetRenderingCallback(void (*callback)(int)) { (void)callback; }
void gln64FBRead(unsigned int address) { (void)address; }
void gln64FBWrite(unsigned int address, unsigned int size) { (void)address; (void)size; }
void gln64FBGetFrameBufferInfo(void *info) { (void)info; }
void Config_LoadConfig(void) {}
/* cxd4's DMEM and IMEM pointers are defined upstream by GLideN64; cxd4 assigns them when it starts. */
unsigned char *DMEM = 0, *IMEM = 0;

/* fgets over the core's built-in ROM database (the adapted rom.c reads it from memory, retrorecomp/n64_core.py): at most size - 1
 * characters, up to and including a newline; NULL at its end. */
char *rr_n64_ini_gets(char *buffer, int size, const char **cursor)
{
    const char *p = *cursor;
    int n = 0;
    if (!p || !*p || size < 2) return NULL;
    while (n < size - 1 && p[n]) {
        buffer[n] = p[n];
        if (p[n++] == '\n') break;
    }
    buffer[n] = 0;
    *cursor = p + n;
    return buffer;
}
