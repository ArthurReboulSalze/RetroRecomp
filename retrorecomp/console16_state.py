"""Portable states in private engine copies, without serialized host stacks."""
from pathlib import Path
import hashlib
import json
import os
from .gun16_runtime import replace
PORTABLE_STATE_ABI = 2  # Compact cartridge SRAM and its byte-lane geometry.
MD_PORTABLE_STATE_ABI = 11  # Cartridge serial phase, staged write and guest time.


def md_glue(source: str) -> str:
    source = replace(source, 'static GlueYieldSite s_yield_site = GLUE_YIELD_NONE;',
        '''static GlueYieldSite s_yield_site = GLUE_YIELD_NONE;
static int rr_step_running, rr_portable_resume;
static GlueYieldSite rr_deferred_yield = GLUE_YIELD_NONE;''')
    source = replace(source, 'static void yield_to_main(GlueYieldSite site)\n{',
        '''static void yield_to_main(GlueYieldSite site)
{
    /* A disk state resumes at the architectural PC, never a suspended C
     * expression. Defer cooperative bus yields until the instruction retires. */
    if (RR_MD_STEP_AOT && rr_step_running) { rr_deferred_yield = site; return; }''')
    source = replace(source, '        M68kiStatus st = m68k_interp_step();',
        '''        rr_step_running = RR_MD_STEP_AOT;
        if(RR_MD_STEP_AOT)rr_md_poll_vdp_irq();
        M68kiStatus st = m68k_interp_step();
        rr_step_running = 0;
        if (rr_deferred_yield != GLUE_YIELD_NONE) {
            GlueYieldSite site = rr_deferred_yield; rr_deferred_yield = GLUE_YIELD_NONE;
            yield_to_main(site);
        }''')
    source = replace(source, 'static void check_cycle_budget(void)\n{',
        '''static void check_cycle_budget(void)
{
    if (RR_MD_STEP_AOT && rr_step_running) return;''')
    source = replace(source, '    if (s_game_fiber_resume_pc) {',
        '''    if (rr_portable_resume) {
        uint32_t pc = s_game_fiber_resume_pc; s_game_fiber_resume_pc = 0;
        rr_portable_resume = 0;
        interp_drive_mainloop(pc); /* native dispatch; preserves guest SP/SR */
    }
    if (s_game_fiber_resume_pc) {''')
    return source + '''
void rr_md_portable_restart(uint32_t pc) {
    rr_step_running = rr_portable_resume = 0; rr_deferred_yield = GLUE_YIELD_NONE;
    rr_md_prefetch_reset();
    glue_restart_game_fiber(pc);
}
void rr_md_portable_arm(uint32_t pc) {
    s_game_fiber_resume_pc = pc & 0xffffffu; rr_portable_resume = 1;
    rr_step_running = 0; rr_deferred_yield = GLUE_YIELD_NONE;
}
'''


def snes_runtime(source: str) -> str:
    # Save after the upstream execution residue; apply after its post-load
    # audio cleanup. PAL's fractional clock and the consumer phase both carry.
    return source + '''
typedef struct RrSnesDeliveryState {
    RtlApuFrameClock clock;
    double phase, ema;
    int16 left, right;
    int starved, fade_pos, fade_out;
    bool priming;
} RrSnesDeliveryState;
static RrSnesDeliveryState rr_loaded_delivery;
void rr_snes_save_delivery(SaveLoadInfo *sli) {
    RrSnesDeliveryState s; memset(&s,0,sizeof s);
    s.clock=g_apu_frame_clock; s.phase=s_render_phase; s.ema=s_render_occ_ema;
    s.left=s_render_hold_l; s.right=s_render_hold_r; s.starved=s_render_starved;
    s.fade_pos=s_render_fade_pos; s.fade_out=s_render_fade_out; s.priming=s_render_priming;
    sli->func(sli,&s,sizeof s);
}
void rr_snes_load_delivery(SaveLoadInfo *sli) {
    sli->func(sli,&rr_loaded_delivery,sizeof rr_loaded_delivery);
}
void rr_snes_apply_delivery(void) {
    const RrSnesDeliveryState *s=&rr_loaded_delivery;
    g_apu_frame_clock=s->clock; s_render_phase=s->phase; s_render_occ_ema=s->ema;
    s_render_hold_l=s->left; s_render_hold_r=s->right; s_render_starved=s->starved;
    s_render_fade_pos=s->fade_pos; s_render_fade_out=s->fade_out; s_render_priming=s->priming;
}
'''


def snes_frame_driver(source: str) -> str:
    return source + '''
void rr_snes_driver_save(uint32_t state[2]) {
    state[0]=s_resume_pc; state[1]=s_wai_halted;
}
bool rr_snes_driver_load(const uint32_t state[2]) {
    if (state[0]>0xffffffu || state[1]>1) return false;
    s_resume_pc=state[0]; s_wai_halted=state[1]!=0; return true;
}
'''


# State keys written by release 1.6.1 (Mega Drive and Super Nintendo, Windows), computed from the v1.6.1 tag by the same
# code that reproduces the documented 1.5.6 key from its tag (docs/GAME_STATES.md, "States written by release 1.6.1").
# 1.6.2 adds strings to the runtime catalogue, a native file both consoles own, which their keys hash; the serialized
# layout did not change.
MD_STATE_ABI_161 = 'fb6d191a2b8c3975e4a69560fb204ad1e79c8726bb55f448e15e2d201550c959'
SNES_STATE_ABI_161 = '366aa5f94b8c57080255e2540bc513bc8e875e8b03fc8fb02bef344b2c05ddf1'


def write_config(project: Path, rom, system_id: str, title: str, revisions: dict):
    from .core import slug
    digest = hashlib.sha256()
    # The listed native files this console owns (retrorecomp/stamp_inputs.py), not whatever sits in native/.
    from .compilation_inputs import input_bytes, state_native_files
    for p in state_native_files(system_id):
        digest.update(p.name.encode()); digest.update(input_bytes(p, 'native/' + p.name))
    digest.update(str(MD_PORTABLE_STATE_ABI if system_id == 'md' else PORTABLE_STATE_ABI).encode())
    if system_id=='snes':
        from .core import module_fingerprint
        for module in ('retrorecomp.snes_timing','retrorecomp.snes_video','retrorecomp.snes_cart','retrorecomp.snes_dma','retrorecomp.snes_bus','retrorecomp.snes_ppu_bus','retrorecomp.snes_chips'):
            digest.update(module.encode());digest.update(module_fingerprint(module).encode())
    digest.update(json.dumps(revisions,sort_keys=True).encode())
    if os.name != 'nt':
        from .platforms import target_id
        digest.update(target_id().encode())
    # The generated profile is the source of truth for an explicit override.
    profile = (project / ('retro_md_game.h' if system_id == 'md' else 'retro_snes_game.h')).read_text()
    pal = ('#define RR_MD_PAL 1' if system_id == 'md' else '#define RR_SN_PAL 1') in profile
    text = ('#pragma once\n#define RR16_STATE_SYSTEM '+('1' if system_id=='md' else '2')+
            '\n#define RR16_STATE_PAL '+str(int(pal))+
            '\n#define RR16_STATE_ROM '+json.dumps(rom.sha256)+
            '\n#define RR16_STATE_ABI '+json.dumps(digest.hexdigest())+
            '\n#define RR16_STATE_NAME '+json.dumps(slug(title),ensure_ascii=True)+'\n')
    # Quick states of the PREVIOUS release only resume in this build: the key that release wrote is added here as
    # `#define RR16_STATE_COMPAT_ABI "<key>"` (native/console16_state.c accepts the keys a build defines, next to
    # RR16_STATE_ABI, and nothing else). The release that follows a release adds that release's key and drops the
    # older ones (docs/GAME_STATES.md). Mega Drive and Super Nintendo, Windows only: the key of a Linux build also hashes
    # its target, and no Linux 1.6.1 key was recorded.
    if os.name == 'nt':
        key = MD_STATE_ABI_161 if system_id == 'md' else SNES_STATE_ABI_161
        text += f'#define RR16_STATE_COMPAT_ABI {json.dumps(key)}\n'
    (project / 'retro16_state_config.h').write_text(text,encoding='ascii')
