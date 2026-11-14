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


# No compatibility key is listed in the tree of 1.6.4 (docs/GAME_STATES.md, "States written by release 1.6.3"): the key of
# the Mega Drive and of the Super Nintendo is the very same value in 1.6.3 and 1.6.4 (it hashes their listed native files,
# the layout versions, the pinned revisions and, for the Super Nintendo, the fingerprints of the snes_* modules, none of
# which moved), so the states of 1.6.3 match the build's own `RR16_STATE_ABI`. tests/test_legacy_compat.py pins that
# value: a later edit that moves the key must add the 1.6.3 key here as `MD_STATE_ABI_163` / `SNES_STATE_ABI_163`.


def state_layout_files(system_id: str) -> list:
    """The native files that fix this console's quick-state layout: the listed top-level native files it owns
    (retrorecomp/stamp_inputs.py, never what sits on disk) minus the ones of the host role (`compilation_inputs.role`:
    the player shell, its menus, fonts, options, display and audio output). None of the host files writes or reads a
    state (docs/GAME_STATES.md lists both sets), so an interface change leaves the key, and the players' states, alone."""
    from .compilation_inputs import role, state_native_files
    return [p for p in state_native_files(system_id) if role('native/' + p.name) != 'host']


def state_key(files, system_id: str, revisions: dict, target) -> str:
    """The quick-state key: `files` as (name, bytes) in order, the layout version, for the Super Nintendo the fingerprints of
    its snes_* modules, the pinned revisions, and on a target other than Windows its name (`platforms.target_id`). The one code
    path for this build's key and for the keys of the previous release it accepts."""
    digest = hashlib.sha256()
    for name, data in files:
        digest.update(name.encode()); digest.update(data)
    digest.update(str(MD_PORTABLE_STATE_ABI if system_id == 'md' else PORTABLE_STATE_ABI).encode())
    if system_id=='snes':
        from .core import module_fingerprint
        for module in ('retrorecomp.snes_timing','retrorecomp.snes_video','retrorecomp.snes_cart','retrorecomp.snes_dma','retrorecomp.snes_bus','retrorecomp.snes_ppu_bus','retrorecomp.snes_chips'):
            digest.update(module.encode());digest.update(module_fingerprint(module).encode())
    digest.update(json.dumps(revisions,sort_keys=True).encode())
    if target is not None:
        digest.update(target.encode())
    return digest.hexdigest()


def build_target():
    """None on Windows (its key never hashed a target), else `platforms.target_id()`."""
    if os.name == 'nt':
        return None
    from .platforms import target_id
    return target_id()


# The keys of release 1.7.4, per target, accepted by this build. Since 1.7.5 the key hashes the layout files only, which are
# byte for byte those of 1.7.4 for both consoles (docs/GAME_STATES.md), so a 1.7.4 state has the same layout. Each value is
# `state_key` over every native file the console owned in 1.7.4, with the bytes of the v1.7.4 tag (the 1.7.4 algorithm), for
# that target: tests/test_legacy_compat.py recomputes them from the tag, and the Windows ones are also the keys real 1.7.4
# builds wrote. The release after 1.7.5 drops this table (only the previous release's states are kept).
STATE_ABI_174 = {
    'md': {None: '0b051c9ebd72a258642f3caf6925e90792bd96ff5138220b9c10be807e05c47f',
           'linux-x86_64': '985477fdd25d50d0e1624f1af49839c397c122e1e542a48d71437f33c2d1132a',
           'linux-arm64': '87bee4a352ecd5f8cf5cee3b64a3526a3beecee04bb37fd621d13c3a59b5d300'},
    'snes': {None: 'ee653e8dabef3057b9e16f59c6487e26f1daab1551a03010651787c39fd72189',
             'linux-x86_64': '5e1b1e33af33400f5bc6a756d0c3c31c0a1e52c100ff78a9562a75815914d743',
             'linux-arm64': '1ae2238fd3fd36671ff56e4384b7c9aefbfdb26c1163ea579d5a23b514fbf167'},
}


def write_config(project: Path, rom, system_id: str, title: str, revisions: dict):
    from .core import slug
    from .compilation_inputs import input_bytes
    key = state_key([(p.name, input_bytes(p, 'native/' + p.name)) for p in state_layout_files(system_id)],
                    system_id, revisions, build_target())
    # The generated profile is the source of truth for an explicit override.
    profile = (project / ('retro_md_game.h' if system_id == 'md' else 'retro_snes_game.h')).read_text()
    pal = ('#define RR_MD_PAL 1' if system_id == 'md' else '#define RR_SN_PAL 1') in profile
    text = ('#pragma once\n#define RR16_STATE_SYSTEM '+('1' if system_id=='md' else '2')+
            '\n#define RR16_STATE_PAL '+str(int(pal))+
            '\n#define RR16_STATE_ROM '+json.dumps(rom.sha256)+
            '\n#define RR16_STATE_ABI '+json.dumps(key)+
            '\n#define RR16_STATE_NAME '+json.dumps(slug(title),ensure_ascii=True)+'\n')
    previous = STATE_ABI_174.get(system_id, {}).get(build_target())
    if previous and previous != key:
        text += '#define RR16_STATE_COMPAT_ABI '+json.dumps(previous)+'\n'
    # Quick states of the PREVIOUS release only resume in this build. When the key of that release is not the build's own
    # (the key moved), it is added here as `#define RR16_STATE_COMPAT_ABI "<key>"` (native/console16_state.c accepts the
    # keys a build defines, next to RR16_STATE_ABI, and nothing else), for the build's own target (a Linux key also hashes its
    # target). The release that follows adds its predecessor's key and drops the older ones (docs/GAME_STATES.md). 1.7.5
    # lists the 1.7.4 key (STATE_ABI_174): its layout files are those of 1.7.4, only the files the key hashes changed.
    (project / 'retro16_state_config.h').write_text(text,encoding='ascii')
