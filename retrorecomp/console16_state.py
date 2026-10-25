"""Portable states in private engine copies, without serialized host stacks."""
from pathlib import Path
import hashlib
import json
import os
from .paths import ASSETS
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


def write_config(project: Path, rom, system_id: str, title: str, revisions: dict):
    from .core import slug
    digest = hashlib.sha256()
    for p in sorted((ASSETS / 'native').glob('*')):
        if p.is_file():
            digest.update(p.name.encode()); digest.update(p.read_bytes())
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
    # ABI-5 keeps ABI-4's layout and migrates its directly fetched partial word
    # into the FIFO. ABI-2/3 gain zeroed new fields; all other sections retain
    # their layout. Never accept
    # arbitrary signatures or other engines.
    if (os.name == 'nt' and system_id == 'md' and PORTABLE_STATE_ABI == 2 and
            revisions.get('md', (None, None))[1] == '00c60bc855a7998f92e5614585d52bca8fffcaf2'):
        text += '#define RR16_STATE_COMPAT_ABI "ea70d6ee35b79e4c6af3c512135b7422dcaf76797e51f803b7e2408db1497864"\n'
        text += '#define RR16_STATE_COMPAT_ABI_2 "9462ea4efd93526b9f7e2a76a20d6ee919ebfd1610f66e1b9e1b2657d9a8233f"\n'
        text += '#define RR16_STATE_COMPAT_ABI_3 "66c1923490f993c3d74b6926b34f5468737f7c31eab1f9b8d085981e96bcf440"\n'
        text += '#define RR16_STATE_COMPAT_ABI_4 "ff419f0ab244b73afe5efa00bfec10e7811d2d7306ace8d212b1eb775d370cd9"\n'
        text += '#define RR16_STATE_COMPAT_ABI_5 "7095702307aff35ceb2ed7f3e95b28211be8450bfba9fa84b6850c8633ccecc4"\n'
        text += '#define RR16_STATE_COMPAT_ABI_6 "e9576d9f42bb0960cf4ba710658b952014c76f5fca591a66797d89e5de573972"\n'
        text += '#define RR16_STATE_COMPAT_ABI_7 "b5a707ff940350ac3ec5d37b6ab726b9b81b6d7b35ea0f51662b5e4d0dcc5f34"\n'
        text += '#define RR16_STATE_COMPAT_ABI_8 "f8382eb4c988ced0cf21b4ba61081a920b5320a990a6ebfb313f4b9ea50c3de5"\n'
        text += '#define RR16_STATE_COMPAT_ABI_9 "ca1490f92d8731ded67f635ee3a5e0b0c84876bd8c4ba62156a8e7bf1fa997c4"\n'
        text += '#define RR16_STATE_COMPAT_ABI_10 "09433151ba55be2b3dcaa7339603d55ea60fea8a2316e61622b39af048a90abb"\n'
        text += '#define RR16_STATE_COMPAT_ABI_11 "c02e76bc12233a3edf66650d02d9dab8486163b13d52e92c5eaddfd1cda173cb"\n'
        text += '#define RR16_STATE_COMPAT_ABI_12 "b9fe2d9c7943bd369451d58f04be857c697d523636fa79d0c7cc1df37f15342c"\n'
        text += '#define RR16_STATE_COMPAT_ABI_13 "c084887942f38196567808560a34b3ed7b0b70b4eed2670b5dbc3070bec44cdf"\n'
        text += '#define RR16_STATE_COMPAT_ABI_14 "724c441b56052525ca0890205cddb87e96a420016425913d7450c655f196262d"\n'
        text += '#define RR16_STATE_COMPAT_ABI_15 "d3dc7a2a461ca5add0d933598b6aa104ee541ce1c8c66bf1c2665434c31e502d"\n'
        text += '#define RR16_STATE_COMPAT_ABI_16 "4e9a8cac290b1b459395be398f8f27d88d7a257474cc00a2df0976c6a9392d56"\n'
        text += '#define RR16_STATE_COMPAT_ABI_17 "8a5a3a6ded47c66ce497eaa1d1f94ef1a15470bf6cc128d2038b6ae17c512577"\n'
        # Local BUSACK adds transient rendezvous state only. Capture rejects
        # pending requests/live continuations; stable ownership is reconstructed.
        text += '#define RR16_STATE_COMPAT_ABI_18 "ab824881c98c32a6025ca67a70b543798762513ede5bd0a59e81f7661ec3bde5"\n'
        # Changed-fetch escape adds no serialized data or live continuation.
        text += '#define RR16_STATE_COMPAT_ABI_19 "666ef15a79132f9f28bba66b22bf86a774e030724f9ea8648b4c44bd9fff053f"\n'
        text += '#define RR16_STATE_COMPAT_ABI_20 "add78e2fbf6a042320ecbdb1f7fa6fd18368c62d778216506eef5ffabd9685be"\n'
        # ABI-11 wire-state validation is stricter; the cartridge layout and
        # every reachable protocol state are unchanged. Retain this exact
        # qualified predecessor, never an arbitrary same-size signature.
        text += '#define RR16_STATE_COMPAT_ABI_21 "1b2e492f0d14bcd8cf0038cba0a30e1ef7385a4ca1bd630d65b5a0accbca60bf"\n'
        # Source-priority ACK adds no serialized fields. This predecessor
        # has the same validated EEPROM/mapper layout and stable boundaries.
        text += '#define RR16_STATE_COMPAT_ABI_22 "db79f598ed89c45cfd6205701e7e0630feb004e1b8f67ee1826c69fbe74b7714"\n'
        # 1.4.1's signature. The 1.5.0 default keys (Enter = Start, either
        # Shift = Select) change only the player shell, never a serialized byte.
        text += '#define RR16_STATE_COMPAT_ABI_23 "58e2c720c4d5988484fb970ca2a0d0b9b722a5023d5806cd58da56d67ea96164"\n'
    (project / 'retro16_state_config.h').write_text(text,encoding='ascii')
