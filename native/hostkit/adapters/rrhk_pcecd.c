/* PC Engine CD adapter: the machine contract of the host kit over the PC Engine CD game (pcecd_main.c, pcecd_machine.cpp). It is the
 * PC Engine's adapter (rrhk_pce.c, left as it is: no existing export's stamp moves) with the CD machine's names: the same HuC6280, pads,
 * multitap, HuC6260 picture and PSG (the CD drive, the CD audio and the ADPCM reach the player through the engine's own mixer, in the same
 * 44.1 kHz stereo ring). Original RetroRecomp code: MIT; the engine keeps its own MIT terms (licenses/pcenginerecomp.md). */
#define rrhk_adapter rrhk_pce_adapter
#include "rrhk_pce.c"
#undef rrhk_adapter

const RrhkMachine *rrhk_adapter(void) {
    static RrhkMachine machine;
    if (!machine.actions) {
        machine = *rrhk_pce_adapter();
        machine.ini_section = L"PCEngineCD";
        machine.console_name = "PC Engine CD";
    }
    return &machine;
}
