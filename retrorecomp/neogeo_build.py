"""Pinned Neo Geo hardware prototype and bounded native CPU conversion.

Reference scheduling, instruction AOT and local qualification are distinct.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import shutil
import zlib
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED
from .conversion_common import check_exit, pinned_checkout, replace_counted, spawn
from .core import serialized_setup

from .paths import ROOT, ASSETS
from . import hostkit
from .platforms import build_executable, cmake_target_args, build_jobs, sdl_install, sdl_library

GEOLITH_REV = '2dc88e3fa72ff404213a65d6eb5bb33baa687f73'
# State key written by release 1.6.3 (Windows), computed from the v1.6.3 tag; the state files did not change since
# (docs/GAME_STATES.md, "States written by release 1.6.3"). The key of this tree moves only because this very rollover
# edits this module, whose fingerprint the key hashes.
STATE_ABI_163 = 'b04f023a36534c86af7527d56e532b4f4e4a458aa1e5b70fa6656e18ede9ee18'
LITHOGEN_REV = 'ef0f9bd94e31689def44b49e0f8351e0206b622d'


def probe_failure(route, result):
    """Retain the native runner's useful reason instead of just an exit code."""
    detail = result.stderr or result.stdout or b''
    if isinstance(detail, bytes):
        detail = detail.decode('utf-8', errors='replace')
    detail = ' '.join(str(detail).split())[-1200:]
    return RuntimeError(f'Neo Geo {route} failed (exit {result.returncode}).' +
                        (f' {detail}' if detail else ''))


def aes_compatible(content: Path) -> bool:
    """Mirror the pinned loader's AES restrictions on verified NEO regions.

    NGH alone is insufficient for revisions sharing a number. Conditional
    signatures use the loader's byte-swapped P view (file offset XOR 1).
    """
    import struct
    with Path(content).open('rb') as source:
        header=source.read(4096)
        if len(header)!=4096 or header[:4]!=b'NEO\x01':
            raise ValueError('Invalid NEO header for machine capabilities.')
        program=struct.unpack_from('<I',header,4)[0]
        ngh=struct.unpack_from('<I',header,40)[0]
        if ngh in (0x236,0x275,0x5003):return False
        if ngh==0x066:return program>=0x100000
        signature={0x263:(0x809,0x0c),0x268:(0x26b,0xb9),0x269:(0x9e91,0x0f)}.get(ngh)
        if signature is None:return True
        offset,value=signature;offset^=1
        if offset>=program:raise ValueError('NEO program is too small for its board signature.')
        source.seek(4096+offset);byte=source.read(1)
        if len(byte)!=1:raise ValueError('Truncated NEO program capability signature.')
        return byte[0]!=value


def aes_available(project: Path) -> bool:
    from .neogeo import validate_bios
    return 'aes' in validate_bios(project/'bios.zip') and aes_compatible(project/'cartridge.neo')


@serialized_setup
def pinned_dependency(name: str, url: str, revision: str) -> Path:
    from .core import run
    target = ROOT / '.deps' / name

    def git(*arguments, **options):
        return run(['git', '-C', target, *arguments], **options)

    def clone():
        research = ROOT / '.build/neogeo-research-20261013' / name
        source = research if research.is_dir() else url
        run(['git', 'clone', '--no-hardlinks', source, target])
        git('checkout', '--detach', revision)

    def refuse(head):
        raise ValueError(f'{name} revision differs from the qualified integration pin.')
    pinned_checkout(target, revision, git, present=target.exists(), clone=clone, moved=refuse,
                    dirty=lambda: ValueError(f'{name} sources changed; use an isolated adapter copy.'))
    return target


def _replace(source: str, old: str, new: str, *, count: int | None = None) -> str:
    return replace_counted(source, old, new, count=count,
                           error=lambda text: ValueError(f'Pinned Neo Geo source changed at {text[:65]!r}.'))


def staging_project(identity: str,native: bool,inputs: list[Path]) -> Path:
    project=ROOT/'.build'/f'ng-{identity[:20]}{"-native" if native else ""}'
    if any(source.resolve().is_relative_to(project.resolve()) for source in inputs):
        import uuid
        project=ROOT/'.build'/f'ng-{identity[:20]}-{uuid.uuid4().hex[:8]}'
    return project


def prepare_project(project: Path, *, content: Path | None = None, bios: Path | None = None,
                    title: str = 'Neo Geo reference prototype', native: bool = False,
                    native_sound: bool = False, presentation: dict | None = None) -> None:
    from .megadrive_codegen import write_changed
    geo = pinned_dependency('geolith-libretro', 'https://github.com/libretro/geolith-libretro.git', GEOLITH_REV)
    litho = pinned_dependency('lithogen', 'https://github.com/carmiker/lithogen.git', LITHOGEN_REV)
    project.mkdir(parents=True, exist_ok=True)
    engine = project / 'engine'
    adapted = {'geo.h', 'geo.c', 'geo_m68k.c', 'geo_z80.c', 'geo_ymfm.c', 'geo_lspc.c', 'ymfm/ymfm_opn.c', 'geo_rtc.c', 'm68k/m68kconf.h', 'z80/z80.c', 'm68k/m68kcpu.c'}
    for file in (geo / 'src').rglob('*'):
        if file.is_file():
            destination = engine / file.relative_to(geo / 'src')
            destination.parent.mkdir(parents=True, exist_ok=True)
            if file.relative_to(geo / 'src').as_posix() not in adapted:
                write_changed(destination, file.read_text(encoding='utf-8'))
    header=(geo/'src/geo.h').read_text(encoding='utf-8')
    header=_replace(header,'#define GEOLITH_H',
        '#define GEOLITH_H\n#include <stddef.h>\n#include <stdint.h>\n#include <stdbool.h>',count=1)
    write_changed(engine/'geo.h',header)
    source=(geo/'src/geo.c').read_text(encoding='utf-8')
    source=_replace(source,'#include "geo.h"','#include "geo.h"\n#include "neogeo_reference.h"',count=1)
    source=_replace(source,'if (ngsys.sram_present)','if (rr_ng_board_cart_state())',count=2)
    # A live clock switch rebases the IRQ's fractional CPU clocks. Enhanced
    # mode intentionally changes 68000 capacity, not master/video/audio clocks.
    source=_replace(source,'    oc = !d;','''    unsigned next = !d;
    if (next != oc)
        ngsys.irq2_frags = next ? ngsys.irq2_frags << 1 : ngsys.irq2_frags >> 1;
    oc = next;''',count=1)
    # LSPC counts N+1 pixels, including the zero setting (one pixel), not N.
    # Keep the programmed register value separate from the live countdown.
    start=source.index('        // Handle IRQ2 counter\n')
    end=source.index('        geo_lspc_run(',start)
    timer=source[start:end].replace('        ','    ',1)
    timer=timer.replace('ngsys.irq2_counter += ngsys.irq2_reload;',
                        'ngsys.irq2_counter += ngsys.irq2_reload + 1u;')
    # One production helper also lets ROM-free fixtures clock the real timer
    # at instruction boundaries without running a supplied cartridge/BIOS.
    source=source[:start]+'        rr_ng_irq2_advance(icycs);\n\n'+source[end:]
    source=_replace(source,'void geo_exec(void) {',
        'static void rr_ng_irq2_advance(unsigned icycs) {\n'+timer+'}\n\nvoid geo_exec(void) {',count=1)
    # Odd instruction costs at 24 MHz must retain the half peripheral cycle.
    # The serialized master counter already holds that phase (frame size even).
    source=_replace(source,'void geo_exec(void) {','''static unsigned rr_ng_master_step(unsigned cpu_clocks) {
    unsigned master = (cpu_clocks * DIV_M68K) >> oc;
    unsigned peripheral = ((mcycs & 1u) + master) >> 1;
    mcycs += master;
    geo_watchdog_increment(master);
    return peripheral;
}

void geo_exec(void) {''',count=1)
    source=_replace(source,'''        mcycs += (icycs * DIV_M68K) >> oc;

        // Watchdog counts real time, always at the base clock rate
        geo_watchdog_increment(icycs * DIV_M68K);''',
        '        unsigned peripheral_clocks = rr_ng_master_step(icycs);',count=1)
    source=_replace(source,'geo_rtc_sync(icycs >> oc);','geo_rtc_sync(peripheral_clocks);',count=1)
    source=_replace(source,'geo_lspc_run(icycs >> oc);','geo_lspc_run(peripheral_clocks);',count=1)
    write_changed(engine/'geo.c',source)
    # All board CPU scheduling uses our replaceable interface. State format is
    # still the reference format here; AOT state needs a separate version.
    path = engine / 'geo_m68k.c'
    source = (geo / 'src/geo_m68k.c').read_text(encoding='utf-8')
    source=_replace(source,'ngsys.irq2_counter = ngsys.irq2_reload;',
                    'ngsys.irq2_counter = ngsys.irq2_reload + 1u;',count=1)
    source = _replace(source, '#include "geo_m68k.h"',
        '#include "geo_m68k.h"\n#include "neogeo_reference.h"', count=1)
    source = _replace(source,'static uint32_t protreg = 0x00000000;',
        'static uint32_t protreg = 0x00000000;\nstatic uint8_t rr_ng_kof98_overlay;',count=1)
    source = _replace(source,'    cartreg[0] = cartreg[1] = 0;',
        '    cartreg[0] = cartreg[1] = 0;\n    rr_ng_kof98_overlay = 0;',count=1)
    source = _replace(source,'if (cartreg[0] == 0x0090) { // Apply the protection overlay',
        'if (cartreg[0] == 0x0090) { // Apply the protection overlay\n            rr_ng_kof98_overlay = 1;',count=1)
    source = _replace(source,'else if (cartreg[0] == 0x00f0) { // Use the original ROM data (NEO-)',
        'else if (cartreg[0] == 0x00f0) { // Use the original ROM data (NEO-)\n            rr_ng_kof98_overlay = 0;',count=1)
    unadapted_cpu_control = source
    source = _replace(source, '    m68k_init();\n    m68k_set_cpu_type(M68K_CPU_TYPE_68000);', '    rr_m68000_init();', count=1)
    for old, new in [('m68k_pulse_reset()', 'rr_m68000_reset()'),
                     ('m68k_execute(cycs)', 'rr_m68000_run(cycs)'),
                     ('m68k_modify_timeslice(', 'rr_m68000_wait('),
                     ('m68k_set_virq(', 'rr_m68000_set_irq('),
                     ('m68k_get_virq(', 'rr_m68000_get_irq(')]:
        source = _replace(source, old, new)
    code_identity = '\n#include "neogeo_code_view.inc"\n'
    source += code_identity
    write_changed(path, source)
    write_changed(engine / 'reference_m68k.c', unadapted_cpu_control + code_identity)
    source=(geo/'src/m68k/m68kcpu.c').read_text(encoding='utf-8')
    if native:
        source=_replace(source,'\t\t\tREG_IR = m68ki_read_imm_16();\n\t\t\tm68ki_instruction_jump_table[REG_IR]();\n\t\t\tUSE_CYCLES(CYC_INSTRUCTION[REG_IR]);',
            '''            extern int rr_ng_native_run(void);
            extern void rr_ng_note_instruction(uint32_t,int);
            /* A native run consumes its own cycles, possibly for several instructions. */
            if(!rr_ng_native_run()) {
                rr_ng_note_instruction(REG_PC,0);
                REG_IR=m68ki_read_imm_16();
                m68ki_instruction_jump_table[REG_IR]();
                USE_CYCLES(CYC_INSTRUCTION[REG_IR]);
            }''',count=1)
    write_changed(engine/'m68k/m68kcpu.c',source)
    # State loading must restore the selected palette pointer as well as its
    # serialized selector. Otherwise a fresh process retains the normal bank.
    source=(geo/'src/geo_lspc.c').read_text(encoding='utf-8')
    source=_replace(source,'ngsys.irq2_counter = ngsys.irq2_reload;',
                    'ngsys.irq2_counter = ngsys.irq2_reload + 1u;',count=2)
    source=_replace(source,'    // Restore the output palette\n',
        '    geo_lspc_shadow_wr(lspc.shadow);\n    // Restore the output palette\n',count=1)
    # Decode each eight-pixel row once, instead of extracting four bitplanes
    # separately for every pixel. Keep the scalar helper for independent tests.
    source=_replace(source,'#include "geo_lspc.h"',
        '#include "geo_lspc.h"\n#include "neogeo_sprite_decode.h"',count=1)
    source=_replace(source,'''        if (sprcount++ == sprlimit)
            break;''','''        if (sprcount++ == sprlimit)
            break;
        /* Count hidden sprites toward the hardware limit and preserve chain
         * coordinates, but skip immutable C-ROM work when no pixel is visible.
         * Sprites crossing the 512-pixel wrap are NOT culled. */
        if (rr_ng_sprite_offscreen(xpos,hshrink))
            continue;''',count=1)
    source=_replace(source,'        unsigned pentry = 0; // Palette entry',
        '''        uint32_t packed_row[2]={
            rr_ng_sprite_row(romdata->c+toffset+(y<<2),ngsys.cdmode),
            rr_ng_sprite_row(romdata->c+toffset+64+(y<<2),ngsys.cdmode)};
        unsigned pentry = 0; // Palette entry''',count=1)
    source=_replace(source,'''                pentry = geo_lspc_tpix(toffset + (((0x08 & p) ^ ftile) << 3),
                    (p & 0x07) ^ fpix, y);''',
        '''                pentry = (packed_row[((p & 8) ^ ftile)>>3] >>
                    (((p & 7) ^ fpix)*4)) & 15u;''',count=1)
    write_changed(engine/'geo_lspc.c',source+'\n#include "neogeo_lspc_state.inc"\n')
    source=(geo/'src/ymfm/ymfm_opn.c').read_text(encoding='utf-8')
    write_changed(engine/'ymfm/ymfm_opn.c',source+'\n#include "neogeo_ym_state.inc"\n')
    # NEO-ZMC does not expose memory after the selected M1/SM1 chip. Mirror
    # smaller power-of-two ROMs within their chip; work RAM remains separate.
    path = engine / 'geo_z80.c'
    source = (geo / 'src/geo_z80.c').read_text(encoding='utf-8')
    # The command is latched even while NMI is masked. Unmasking a pending
    # command raises one edge; reading port 0 acknowledges the latch.
    source=_replace(source,'static uint8_t nmi_enabled = 0;',
        'static uint8_t nmi_enabled = 0;\nstatic uint8_t rr_ng_sound_pending;',count=1)
    source=_replace(source,'            // Acknowledge NMI - to implement\n',
        '            rr_ng_sound_pending = 0; // acknowledge the command latch\n',count=1)
    source=_replace(source,'            nmi_enabled = 1;\n',
        '            if (!nmi_enabled && rr_ng_sound_pending) z80_pulse_nmi(&z80ctx);\n'
        '            nmi_enabled = 1;\n',count=1)
    source=_replace(source,'    ym2610_reset();\n    nmi_enabled = 0;\n',
        '    ym2610_reset();\n    nmi_enabled = 0;\n    rr_ng_sound_pending = 0;\n',count=1)
    source=_replace(source,'    if (nmi_enabled)\n        z80_pulse_nmi(&z80ctx);',
        '    if (nmi_enabled && !rr_ng_sound_pending) z80_pulse_nmi(&z80ctx);\n'
        '    rr_ng_sound_pending = 1;',count=1)
    source+='\nunsigned rr_ng_sound_latch(void) { return rr_ng_sound_pending; }\n'
    source+='void rr_ng_sound_latch_restore(unsigned v) { rr_ng_sound_pending=(uint8_t)v; }\n'
    # Power-on bank numbers are not specified. Preserve the compatible linear
    # startup choice; every explicit selection uses all eight address bits.
    for mask in ('0x0f','0x1f','0x3f','0x7f'):
        source=_replace(source,f'((port >> 8) & {mask})',
                        '((port >> 8) & 0xff)',count=1)
    marker = 'static uint8_t geo_z80_mem_rd(void *userdata, uint16_t addr) {'
    helper = '''static uint8_t rr_ng_mrom_read(uint32_t address) {
    size_t size=mrom==romdata->m?romdata->msz:romdata->smsz;
    return size?mrom[address%size]:0xff;
}
'''
    source = _replace(source, marker, helper + marker, count=1)
    for old in ('mrom[addr]', 'mrom[zbank[0] + (addr & 0x3fff)]',
                'mrom[zbank[1] + (addr & 0x1fff)]', 'mrom[zbank[2] + (addr & 0x0fff)]',
                'mrom[zbank[3] + (addr & 0x07ff)]'):
        # Only cartridge reads; the CD RAM read/write routines remain distinct.
        start = source.index('static uint8_t geo_z80_mem_rd(')
        end = source.index('static void geo_z80_mem_wr(', start)
        block = _replace(source[start:end], 'return '+old+';', 'return rr_ng_mrom_read('+old[5:-1]+');', count=1)
        source = source[:start] + block + source[end:]
    source+='''
/* Side-effect-free sound code view. Each structural byte is checked using
 * its current bank: an instruction may straddle distinct mapped windows. */
int rr_ng_z80_code_location(uint16_t pc,unsigned *region,uint32_t *offset) {
    if(!romdata || !mrom || ngsys.cdmode || pc>=0xf800u)return 0;
    uint32_t physical=pc<0x8000u?pc:pc<0xc000u?zbank[0]+(pc&0x3fffu):
        pc<0xe000u?zbank[1]+(pc&0x1fffu):pc<0xf000u?zbank[2]+(pc&0xfffu):zbank[3]+(pc&0x7ffu);
    size_t size=mrom==romdata->m?romdata->msz:romdata->smsz;if(!size)return 0;
    *region=mrom==romdata->m?1:2;*offset=(uint32_t)(physical%size);return 1;
}
int rr_ng_z80_code_byte(uint16_t pc,uint8_t *value) {
    if(value && pc>=0xf800u) {*value=zram[pc&0x7ffu];return 1;}
    unsigned region;uint32_t offset;
    if(!value || !rr_ng_z80_code_location(pc,&region,&offset))return 0;
    *value=mrom[offset];return 1;
}
void rr_ng_z80_observe(uint16_t pc) {
    extern int rr_ng_observations;if(!rr_ng_observations)return;
    extern uint64_t rr_ng_m1_instructions,rr_ng_sm1_instructions;
    unsigned region;uint32_t offset;
    if(rr_ng_z80_code_location(pc,&region,&offset)) {
        if(region==1)++rr_ng_m1_instructions;else ++rr_ng_sm1_instructions;
    }
}
uint64_t rr_ng_z80_state_hash(void) {
    uint8_t bytes[4096]={0};geo_serial_begin();geo_z80_state_save(bytes);
    uint64_t hash=(14695981039346656037ull^rr_ng_sound_pending)*1099511628211ull;
    for(size_t n=0;n<geo_serial_size();++n)hash=(hash^bytes[n])*1099511628211ull;
    return hash;
}
'''
    write_changed(path, source)
    path = engine / 'geo_ymfm.c'
    source = (geo / 'src/geo_ymfm.c').read_text(encoding='utf-8')
    source = _replace(source, 'address > romdata->v1sz', 'address >= romdata->v1sz', count=1)
    source = _replace(source, 'address > romdata->v2sz', 'address >= romdata->v2sz', count=1)
    write_changed(path, source)
    path = engine / 'm68k/m68kconf.h'
    source = _replace((geo / 'src/m68k/m68kconf.h').read_text(encoding='utf-8'),
                      '#define M68K_INSTRUCTION_HOOK       OPT_OFF',
                      '#define M68K_INSTRUCTION_HOOK       OPT_ON', count=1)
    write_changed(path, source)
    path = engine / 'geo_rtc.c'
    source = (geo / 'src/geo_rtc.c').read_text(encoding='utf-8')
    source = _replace(source, '    time(&rawtime);\n    struct tm *timeinfo = localtime(&rawtime);',
        '''    extern int rr_ng_test_clock_enabled;
    extern int64_t rr_ng_test_clock;
    if(rr_ng_test_clock_enabled) rawtime=(time_t)rr_ng_test_clock;
    else time(&rawtime);
    struct tm *timeinfo = rr_ng_test_clock_enabled ? gmtime(&rawtime) : localtime(&rawtime);''', count=1)
    write_changed(path, source)
    # Counting happens at the actual interpreter entry, excluding HALT cycles.
    path = engine / 'z80/z80.c'
    from .neogeo_z80 import adapt_source as adapt_z80
    source = adapt_z80((geo / 'src/z80/z80.c').read_text(encoding='utf-8'))
    marker = '    const uint8_t opcode = nextb(z);\n    cyc += exec_opcode(z, opcode);'
    if native_sound:
        source=_replace(source,marker,'''    extern void rr_ng_z80_observe(uint16_t);
    rr_ng_z80_observe(z->pc);
    if(!rr_ng_z80_try(z,&cyc)) {
        ++rr_ng_z80_instructions;rr_ng_z80_note_fallback(z->pc);
        const uint8_t opcode=nextb(z);cyc+=exec_opcode(z,opcode);
    }''',count=1)
        source=_replace(source,'    cyc += exec_opcode(z, 0x00);','    inc_r(z);cyc+=4; /* HALT idle fetch, no retired instruction. */',count=1)
        source=_replace(source,'static unsigned exec_opcode(z80* const z, uint8_t opcode);',
            '#include "neogeo_z80_native.h"\nstatic int rr_ng_z80_try(z80*,unsigned*);\n'
            'static unsigned exec_opcode(z80* const z, uint8_t opcode);',count=1)
        source=_replace(source,'#undef GET_BIT','''#include "ng_z80_steps.inc"
static int rr_ng_z80_try(z80 *z,unsigned *cycles) {
    unsigned region;uint32_t offset;
    if(rr_ng_force_reference || rr_ng_force_z80_reference)return 0;
    const RrNgZ80Step *op=NULL;
    if(rr_ng_z80_code_location(z->pc,&region,&offset))op=rr_ng_z80_native_lookup(region,offset);
    else if(z->pc>=0xf800u)op=rr_ng_z80_ram_lookup(z->pc);
    if(!op)return 0;
    for(unsigned n=0;n<4;++n)if(op->mask&(1u<<n)) {
        uint8_t actual;if(!rr_ng_z80_code_byte((uint16_t)(z->pc+n),&actual) || actual!=op->bytes[n])return 0;
    }
    ++rr_ng_native_z80;*cycles=op->execute(z);return 1;
}
#undef GET_BIT''',count=1)
    else:
        source = _replace(source, marker,
            '    extern uint64_t rr_ng_z80_instructions;\n    extern void rr_ng_z80_observe(uint16_t);\n'
            '    extern void rr_ng_z80_note_fallback(uint16_t);\n'
            '    if(z->pc>=0xf800u)rr_ng_z80_note_fallback(z->pc);\n'
            '    rr_ng_z80_observe(z->pc);++rr_ng_z80_instructions;\n' + marker, count=1)
    # IM0 executes a supplied opcode instead of fetching from ROM. Keep that
    # exceptional path explicitly counted until its native form is qualified.
    source=_replace(source,'      cyc += exec_opcode(z, z->irq_data);',
        '      extern uint64_t rr_ng_z80_instructions;\n      ++rr_ng_z80_instructions;\n'
        '      cyc += exec_opcode(z, z->irq_data);',count=1)
    write_changed(path, source)
    for name in ('m68000_backend.h', 'm68000_backend.c', 'neogeo_code_view.inc', 'neogeo_reference.h',
                 'neogeo_reference.c', 'neogeo_lithogen.c', 'neogeo_main.c',
                 'neogeo_input.h', 'console16_video.h', 'neogeo_host.c', 'neogeo_host.h',
                 'neogeo_state.c', 'neogeo_state_validate.c', 'neogeo_ui_test.c', 'neogeo_ym_state.inc', 'neogeo_lspc_state.inc',
                 'neogeo_persistence.c', 'neogeo_persistence.h',
                 'neogeo_path_io.h', 'neogeo_sprite_decode.h',
                 'console16_state.c', 'console16_state.h',
                 'platform_io.c', 'platform_io.h', 'embedded_resources.h', 'retro_console16.h', 'retro_menu.c', 'retro_menu.h', 'font6x10.h', 'font10x20.h', 'runtime_i18n.h', 'runtime_catalog.inc', 'retro_keyboard.h',
                 'display_settings.h', 'autofire.h', 'game_options.h', 'audio_filter.h', 'audio_cushion.h', 'scanline_sdl.h', 'scanlines.h', 'xbr_sdl.h',
                 'xbr_filter.h', 'scale2x.h', 'gun16.h'):
        write_changed(project / name, (ASSETS / 'native' / name).read_text(encoding='utf-8'))
    hostkit.stage(project, 'ng')
    # miniz expects UTF-8 on Windows, whereas narrow CRT argv used the active
    # ANSI code page. The helper takes wide argv; all loader output IO also
    # converts UTF-8 explicitly. Keep the pinned loader checkout untouched.
    for name in ('lithogen.c','neowrite.c'):
        source=(litho/'src'/name).read_text(encoding='utf-8')
        source=_replace(source,'#include "lithogen_internal.h"',
                        '#include "lithogen_internal.h"\n#include "neogeo_path_io.h"',count=1)
        source=_replace(source,'fopen(', 'rr_ng_utf8_fopen(',count=1)
        if name=='neowrite.c':source=_replace(source,'remove(outpath)','rr_ng_utf8_remove(outpath)',count=1)
        write_changed(project/('loader_'+name),source)
    if native:
        for name in ('neogeo_native.h','neogeo_native.c','m68000_state_helpers.h'):
            write_changed(project/name,(ASSETS/'native'/name).read_text(encoding='utf-8'))
    if native_sound:
        if not native:raise ValueError('Native sound currently requires the native CPU prototype.')
        write_changed(project/'neogeo_z80_native.h',(ASSETS/'native/neogeo_z80_native.h').read_text(encoding='utf-8'))
    # No libretro frontend or CHD stack is imported. Cartridge runner never
    # accepts CD inputs. Upstream's optional internal CD code remains linked.
    cmake = f'''cmake_minimum_required(VERSION 3.20)
project(RetroNeoGeo LANGUAGES C)
if(WIN32)
  enable_language(RC)
else()
  enable_language(ASM)
endif()
set(CMAKE_C_STANDARD 11)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
if(MSVC)
  add_compile_options(/utf-8 /wd4996 /wd4244 /wd4267)
endif()
set(LITHO "{litho.as_posix()}")
file(GLOB LITHO_CRYPTO "${{LITHO}}/src/crypt/*.c")
add_executable(ng_prepare platform_io.c neogeo_lithogen.c ${{LITHO_CRYPTO}}
  loader_lithogen.c "${{LITHO}}/src/games_db.c" "${{LITHO}}/src/meta_db.c"
  loader_neowrite.c "${{LITHO}}/src/recipes.c" "${{LITHO}}/src/regions.c"
  "${{LITHO}}/src/zipio.c" "${{LITHO}}/miniz/miniz.c")
target_include_directories(ng_prepare PRIVATE "${{LITHO}}/src" "${{LITHO}}/miniz")
if(WIN32 AND NOT MSVC)
  # Visual Studio finds wmain by itself; MinGW needs to be told.
  target_link_options(ng_prepare PRIVATE -municode)
endif()
set(GEO "{geo.as_posix()}")
file(GLOB GEO_SOURCES "${{CMAKE_CURRENT_SOURCE_DIR}}/engine/geo_*.c")
list(FILTER GEO_SOURCES EXCLUDE REGEX "geo_chd.c$")
option(RR_NG_PLAIN_REFERENCE "Use Geolith CPU scheduling without the RetroRecomp boundary" OFF)
if(RR_NG_PLAIN_REFERENCE)
  list(FILTER GEO_SOURCES EXCLUDE REGEX "geo_m68k.c$")
  list(APPEND GEO_SOURCES "${{CMAKE_CURRENT_SOURCE_DIR}}/engine/reference_m68k.c")
endif()
add_library(ng_hardware STATIC engine/geo.c ${{GEO_SOURCES}}
  engine/m68k/m68kcpu.c engine/m68k/m68kops.c engine/z80/z80.c
  engine/ymfm/ymfm_adpcm.c engine/ymfm/ymfm_opn.c engine/ymfm/ymfm_ssg.c
  "${{GEO}}/deps/miniz/miniz.c" "${{GEO}}/deps/speex/resample.c"
  m68000_backend.c neogeo_reference.c platform_io.c)
target_include_directories(ng_hardware PUBLIC . engine "${{GEO}}/deps" "${{GEO}}/deps/miniz" "${{GEO}}/deps/libretro-common/include")
if(MSVC)
  target_compile_definitions(ng_hardware PRIVATE __BYTE_ORDER__=1234 __ORDER_LITTLE_ENDIAN__=1234)
endif()
'''
    if native:
        cmake+='''
file(GLOB NG_STEPS "${CMAKE_CURRENT_SOURCE_DIR}/steps/ng_step_*.c")
target_sources(ng_hardware PRIVATE neogeo_native.c ng_arithmetic.c ${NG_STEPS})
target_compile_definitions(ng_hardware PUBLIC RR_NG_NATIVE=1)
'''
    if native_sound:
        cmake+='target_compile_definitions(ng_hardware PUBLIC RR_NG_NATIVE_Z80=1)\n'
    if content is not None:
        from . import __version__
        if bios is None: raise ValueError('Neo Geo needs an explicitly selected BIOS archive.')
        notices = []
        for file in (geo / 'LICENSE', geo / 'src/m68k/readme.txt',
                     geo / 'deps/speex/COPYING', litho / 'LICENSE',
                     ASSETS / 'LICENSE', ASSETS / 'licenses/SDL2.md', ASSETS / 'licenses/xbr.md', ASSETS / 'licenses/Noto.md', ASSETS / 'licenses/UPX.md', ASSETS / 'licenses/llvm-mingw.md'):
            if file.is_file(): notices.append(file.read_text(encoding='utf-8'))
        # Component headers carry additional complete notices retained here.
        for file in (geo / 'src/z80/z80.c', geo / 'src/ymfm/ymfm_opn.c',
                     geo / 'deps/miniz/miniz.c', geo / 'deps/speex/resample.c',
                     geo / 'deps/libretro-common/include/dr/dr_flac.h'):
            text = file.read_text(encoding='utf-8')
            # dr_flac carries its MIT/public-domain alternatives at the end.
            if file.name == 'dr_flac.h':
                marker = 'This software is available as a choice of the following licenses.'
                position = text.rfind(marker)
                if position < 0: raise ValueError('Pinned dr_flac licence footer changed.')
                notices.append(text[position:])
            else:
                notices.append(text.split('*/', 1)[0] + '*/')
        write_changed(project / 'notices.txt', '\n\n'.join(notices))
        if native:
            # Reused qualified MC68000 semantics retain their upstream notices.
            # Use the same complete notice files as the Mega Drive export.
            for notice in (ROOT/'.deps/segagenesisrecomp/LICENSE',ROOT/'.deps/segagenesisrecomp/external/m68k-recomp-core/LICENSE'):
                if notice.is_file():notices.append(notice.read_text(encoding='utf-8'))
            write_changed(project/'notices.txt','\n\n'.join(notices))
        raw_content = content.read_bytes()
        packed_content = project / 'cartridge.pack'
        pack_receipt = project/'cartridge-pack.json'
        raw_hash = hashlib.sha256(raw_content).hexdigest()
        try:
            receipt = json.loads(pack_receipt.read_text())
            reused = receipt['source'] == raw_hash and receipt['packed'] == hashlib.sha256(packed_content.read_bytes()).hexdigest()
        except (OSError, ValueError, KeyError, TypeError): reused = False
        if not reused:
            payload = b'NGZ1' + len(raw_content).to_bytes(4, 'little') + zlib.compress(raw_content, 9)
            packed_content.write_bytes(payload)
            from .library import atomic_json
            atomic_json(pack_receipt, {'source':raw_hash,'packed':hashlib.sha256(payload).hexdigest()})
        from .core import executable_name
        from .metadata import write_game_metadata
        icon = False
        if presentation is not None:
            from .artwork import prepare_icon
            from .paths import boxart_cache_directory
            art = prepare_icon(project, presentation['rom_path'], title,
                presentation.get('boxart_dir') or ROOT / 'BoxArt',
                explicit=presentation.get('cover'), online=presentation.get('online_cover', True),
                enabled=presentation.get('use_cover', True), cache_directory=boxart_cache_directory('ng'),
                system_id='ng', emit=presentation.get('emit', print))
            icon = art['embedded']
            (project/'artwork.json').write_text(json.dumps(art,indent=2),encoding='utf-8')
        write_game_metadata(project,title,executable_name(title),light_phaser=False,
                            icon=icon,standard='mvs',system_id='ng')
        identity = (presentation or {}).get('export_identity')
        if identity is None:
            from .neogeo import parse_neo
            identity = parse_neo(content).sha256
        import re
        if not isinstance(identity,str) or not re.fullmatch('[a-f0-9]{64}',identity):
            raise ValueError('Invalid Neo Geo export identity.')
        (project/'export-identity.bin').write_bytes(b'[Retro-Recomp]\0'+identity.encode('ascii')+b'\0')
        write_changed(project / 'content.rc', '#pragma code_page(65001)\n' +
                      f'201 RCDATA "{packed_content.as_posix()}"\n202 RCDATA "{bios.as_posix()}"\n203 RCDATA "notices.txt"\n'
                      '205 RCDATA "export-identity.bin"\n#include "game_resources.rc"\n')
        from .resources import embed_resources
        embed_resources(project,{201:packed_content,202:bios,203:project/'notices.txt',205:project/'export-identity.bin'})
        write_changed(project / 'ng_game.h', '#pragma once\n#define RR_NG_TITLE ' + json.dumps(title) +
                      '\n#define RR_NG_VERSION ' + json.dumps(__version__) + '\n' + mode_config(content, bios))
        write_changed(project/'retro_gun_game.h','#pragma once\n#define RR16_GUN 0\n')
        write_changed(project/'retro16_state_config.h',state_config(content,bios,title))
        cmake += f'''
find_package(SDL2 CONFIG REQUIRED)
add_executable(game neogeo_main.c neogeo_host.c neogeo_state.c neogeo_state_validate.c
  neogeo_ui_test.c neogeo_persistence.c {' '.join(hostkit.sources('ng'))} console16_state.c retro_menu.c)
if(WIN32)
  target_sources(game PRIVATE content.rc)
  target_link_libraries(game PRIVATE shell32 user32 gdi32)
else()
  target_sources(game PRIVATE embedded_resources.c embedded_resources.S)
  target_link_libraries(game PRIVATE m)
endif()
target_link_libraries(game PRIVATE ng_hardware SDL2::SDL2-static)
target_compile_definitions(game PRIVATE SDL_MAIN_HANDLED RR16_NG=1 [[RR_RECOMP_VERSION="{__version__}"]])
if(MSVC)
  target_link_options(game PRIVATE /SUBSYSTEM:WINDOWS /ENTRY:mainCRTStartup)
endif()
if(WIN32 AND NOT MSVC)
  # Same subsystem and entry point as the Visual Studio build: no console window.
  target_link_options(game PRIVATE -Wl,--subsystem,windows -Wl,--entry,mainCRTStartup)
endif()
'''
        if native:
            cmake+='set_property(TARGET ng_hardware game PROPERTY INTERPROCEDURAL_OPTIMIZATION_RELEASE TRUE)\n'
    write_changed(project / 'CMakeLists.txt', cmake)
    if content is not None:
        from .feedback import stage
        from .neogeo_knowledge import context
        stage(project,'ng',context(project)[0])
        write_changed(project/'runtime_feedback_config.h',
            '#include "neogeo_host.h"\n#define RR_FEEDBACK_SYSTEM "ng"\n#define RR_FEEDBACK_IDENTITY rr_ng_identity()\n')
    else:
        from .feedback import stage
        stage(project,'ng','0'*64,target='ng_hardware')


def mode_config(content: Path, bios: Path) -> str:
    from .neogeo import parse_neo, validate_bios
    from .neogeo_knowledge import key
    cart = parse_neo(content); firmware = validate_bios(bios)
    mvs = key(cart.sha256, firmware['sha256'])
    aes = aes_identity(cart.sha256, firmware)
    compatible=aes_compatible(content)
    return ('#define RR_NG_ARCADE_ONLY '+str(int(not compatible))+'\n'+
            '#define RR_NG_AES_AVAILABLE '+str(int('aes' in firmware and compatible))+'\n'+
            '#define RR_NG_MVS_IDENTITY '+json.dumps(mvs)+'\n'+
            '#define RR_NG_AES_IDENTITY '+json.dumps(aes)+'\n')


def aes_identity(cart: str, firmware: dict) -> str:
    return hashlib.sha256(json.dumps({'cart':cart, 'bios':firmware['sha256'],
        'aes':firmware.get('aes', {}).get('sha256'), 'system':'aes','region':'eu'},sort_keys=True).encode()).hexdigest()


def state_config(content: Path,bios: Path,title: str) -> str:
    """Canonical cart/selected BIOS identity, separate from presentation options."""
    from .neogeo import parse_neo,validate_bios
    from .core import executable_name
    cart=parse_neo(content);firmware=validate_bios(bios)
    identity=hashlib.sha256(json.dumps({'cart':cart.sha256,'bios':firmware['sha256'],
        'system':'mvs','region':'eu'},sort_keys=True).encode()).hexdigest()
    abi=hashlib.sha256(b'NeoGeo-frame-state-v2:'+GEOLITH_REV.encode())
    for name in ('native/neogeo_state.c','native/neogeo_state_validate.c','native/neogeo_reference.c','native/neogeo_ym_state.inc',
                 'native/neogeo_code_view.inc','native/neogeo_lspc_state.inc',
                 'native/neogeo_native.c','native/neogeo_z80_native.h'):
        abi.update((ASSETS/name).read_bytes())
    # Frozen converters carry Python in PYZ, not raw .py resources. Reuse the
    # verified module fingerprint path rather than reading missing source files.
    import importlib
    from .core import module_fingerprint
    for name in ('retrorecomp.neogeo_build','retrorecomp.neogeo_codegen','retrorecomp.neogeo_z80'):
        importlib.import_module(name);abi.update(name.encode());abi.update(module_fingerprint(name).encode())
    if os.name != 'nt':
        from .platforms import target_id
        abi.update(target_id().encode())
    # The previous release's state key is added here as `#define RR16_STATE_COMPAT_ABI "<key>"` by the release that
    # follows it (docs/GAME_STATES.md); the keys of older releases are never kept. Windows only: the key of a Linux
    # build also hashes its target, and no Linux 1.6.3 key was recorded.
    return '#pragma once\n#include "neogeo_host.h"\n#define RR16_STATE_SYSTEM 3\n#define RR16_STATE_PAL 0\n'+\
        '#define RR16_STATE_ROM (rr_ng_aes()?'+json.dumps(aes_identity(cart.sha256,firmware))+':'+json.dumps(identity)+')\n#define RR16_STATE_ABI '+json.dumps(abi.hexdigest())+\
        ('\n#define RR16_STATE_COMPAT_ABI '+json.dumps(STATE_ABI_163) if os.name=='nt' else '')+\
        '\n#define RR16_STATE_NAME '+json.dumps(Path(executable_name(title)).stem if os.name=='nt' else executable_name(title))+'\n'


def configure_build(project: Path, target: str) -> Path:
    from .core import run, toolchain
    cmake, generator = toolchain()
    sdl = sdl_install()
    if not (sdl / sdl_library()).exists():
        from .core import dependencies
        _, sdl, _, _ = dependencies()
    run([cmake, '-S', project, '-B', project / 'build', '-G', generator, *cmake_target_args(),
         f'-DCMAKE_PREFIX_PATH={sdl.as_posix()}'], log=project / 'build.log')
    run([cmake, '--build', project / 'build', '--config', 'Release', '--target', target,
         '--parallel', build_jobs()], log=project / 'build.log')
    return build_executable(project / 'build',target)


def preparation_tool() -> Path:
    from .core import serialized_setup
    @serialized_setup
    def build():
        project = ROOT / '.build/neogeo-preparation'
        prepare_project(project)
        return configure_build(project, 'ng_prepare')
    return build()


def load_catalogue(tool: Path) -> list[dict]:
    from .core import run
    return json.loads(run([tool, '--catalogue']))


def convert_reference(path: Path, *, bios: Path, output: Path | None = None,
                      set_name: str | None = None, emit=print, native: bool = False,
                      title: str | None = None, presentation: dict | None = None, pack: bool = True,
                      qualification: dict | None = None, validation_workers: int = 1,
                      defer_to_packed: bool = False) -> Path:
    from .core import run
    from .neogeo import read_set, validate_bios, parse_neo, combined_identity, parent_archives
    from .library import atomic_json, entry_lock
    tool = preparation_tool()
    catalogue = load_catalogue(tool)
    game = read_set(path, catalogue, set_name=set_name)
    bios_info = validate_bios(bios)
    parent_sources = parent_archives(game, catalogue)
    identity = combined_identity(game, bios_info, engine_revision=GEOLITH_REV, loader_revision=LITHOGEN_REV)
    if 'aes' in bios_info:
        identity = hashlib.sha256((identity+bios_info['aes']['sha256']).encode()).hexdigest()
    if parent_sources:
        identity = hashlib.sha256((identity + json.dumps(
            [records for _, records in parent_sources], sort_keys=True)).encode()).hexdigest()
    # A developer may rebuild from an already prepared local input. Never
    # truncate/overwrite a caller's archive or container through a staging alias.
    inputs=[path,bios,*[parent for parent,_ in parent_sources]]
    project=staging_project(identity,native,inputs)
    project.mkdir(parents=True, exist_ok=True)
    with entry_lock(project):
        # Fixed ASCII staging names handle spaces/accents/UNC safely. Nothing
        # writes to sources. Each caller has a process-isolated loader.
        local_bios = project / 'bios.zip'
        # Only the selected four BIOS components are needed in the game EXE.
        with ZipFile(bios) as source, ZipFile(local_bios, 'w') as destination:
            for record in bios_info['members'] + ([bios_info['aes']] if 'aes' in bios_info else []):
                original = next(entry for entry in source.infolist()
                                if entry.filename.replace('\\', '/').rsplit('/', 1)[-1].casefold() == record['name'])
                info = ZipInfo(record['name'], date_time=(1990, 1, 1, 0, 0, 0))
                info.compress_type = ZIP_DEFLATED
                data = source.read(original)
                if hashlib.sha256(data).hexdigest() != record['sha256']:
                    raise ValueError('BIOS changed during preparation.')
                destination.writestr(info, data)
        container = project / 'cartridge.neo'
        if path.suffix.casefold() == '.neo':
            shutil.copyfile(path, container)
            if parse_neo(container).sha256 != game.sha256:
                raise ValueError('NEO cartridge changed during preparation.')
        else:
            local_zip = project / 'cartridge.zip'
            shutil.copyfile(path, local_zip)
            if read_set(local_zip, load_catalogue(tool), set_name=game.set_name).sha256 != game.sha256:
                raise ValueError('Neo Geo cartridge changed during preparation.')
            from .neogeo import canonical_archive
            selected_zip=project/'selected-cartridge.zip'
            descriptor=next(row for row in catalogue if row['set']==game.set_name)
            canonical_archive(local_zip,selected_zip,descriptor)
            parents = []
            for number, (parent, parent_records) in enumerate(parent_sources):
                target = project / f'parent-{number}.zip'
                shutil.copyfile(parent, target)
                from .neogeo import archive_members
                if archive_members(target, hash_contents=True,cartridge_paths=True) != parent_records:
                    raise ValueError('Neo Geo parent changed during preparation.')
                canonical_parent=project/f'selected-parent-{number}.zip'
                parent_descriptor=next(row for row in catalogue if row['set']==game.parent)
                canonical_archive(target,canonical_parent,parent_descriptor)
                parents.append(canonical_parent)
            emit(f'Neo Geo: assembling {game.set_name}, strict CRC validation.')
            run([tool, game.set_name, selected_zip, container, *parents, local_bios], log=project / 'prepare.log')
        prepared = parse_neo(container)
        actual_title = title or prepared.title
        prepare_project(project, content=container, bios=local_bios, title=actual_title,presentation=presentation)
        from .feedback import ingest
        from .neogeo_knowledge import context
        feedback=ingest('ng',context(project)[0],(presentation or {}).get('feedback_output'),emit=emit)
        if 'aes' in bios_info and aes_compatible(container):
            feedback['aes'] = ingest('ng',aes_identity(prepared.sha256,bios_info),
                                    (presentation or {}).get('feedback_output'),emit=emit)
        atomic_json(project/'runtime-feedback-use.json',feedback)
        emit('Neo Geo reference prototype: 68000 and Z80 are interpreted.')
        executable = configure_build(project, 'game')
        if native:
            executable=compile_native(project,executable,title=actual_title,set_name=game.set_name,emit=emit,
                presentation=presentation,qualification=qualification,validation_workers=validation_workers,
                defer_to_packed=defer_to_packed)
        atomic_json(project / 'input.json', {'identity': identity, 'source': game.metadata(),
                    'prepared': prepared.metadata(), 'bios': bios_info,
                    'parents': [list(records) for _, records in parent_sources], 'geolith': GEOLITH_REV,
                    'lithogen': LITHOGEN_REV, 'native_68000': native, 'native_z80': native,
                    'knowledge_promoted': False, 'stage': 'native-prototype' if native else 'reference-prototype'})
        if not pack:
            return executable
        if output is None:
            from .core import executable_name
            output = ROOT / 'Export/Prototypes/Neo Geo' / executable_name(prepared.title)
        output.parent.mkdir(parents=True, exist_ok=True)
        from .conversion_gates import pack_candidate
        packed_executable = project / 'packed-game.exe'
        pack_candidate(executable, packed_executable, emit)
        shutil.copy2(packed_executable, output)
        return output


def compile_native(project: Path,reference_executable: Path,*,title='Neo Geo prototype',set_name='',emit=print,
                   presentation: dict | None = None,qualification: dict | None = None,validation_workers: int = 1,
                   defer_to_packed: bool = False) -> Path:
    """Discover against the exact private inputs, translate, then compare.

    No shared knowledge bypass, game patch, function override or guessed RAM
    image is permitted. This bounded route is not complete-game qualification.
    """
    import subprocess
    from .neogeo_codegen import generate
    from .neogeo_z80 import generate as generate_sound
    from .neogeo_validation import extended_routes,compare,route_arguments
    from .library import atomic_json
    baseline=project/'reference-game.exe'
    shutil.copy2(reference_executable,baseline)
    observations=project/'native-discovery';observations.mkdir(exist_ok=True)
    from .neogeo import validate_bios
    routes=extended_routes(set_name,qualification,aes=aes_available(project))
    from concurrent.futures import ThreadPoolExecutor
    references={};seeds=set();ram=[];main_ram=[];physical={'p':set(),'bios':set()}
    def probe(binary,name,frames,script):
        destination=observations/(name+'.json')
        result=spawn([str(binary),'--headless',*route_arguments(name),'--frames',str(frames),'--script',str(script),
            '--rtc-seed','1760000000','--report',str(destination)],cwd=observations,timeout=max(180,frames/60*4),
            capture_output=True)
        check_exit(result,lambda failed:probe_failure(name, failed))
        return json.loads(destination.read_text(encoding='utf-8'))
    def observe(row):
        name,(frames,text)=row
        script=observations/(name+'.inputs');script.write_text(text,encoding='ascii')
        emit(f'Neo Geo: observing {name}, {frames} reference frames.')
        report=probe(baseline,name+'-reference',frames,script)
        return name, report
    with ThreadPoolExecutor(max_workers=validation_workers) as pool:
        observed = list(pool.map(observe,routes.items()))
    for name,report in observed:
        references[name]=report;seeds.update(report['reached_pc']);ram+=report.get('z80_variants',[])
        main_ram+=report.get('m68k_ram_variants',[])
        for region,offsets in report.get('reached_physical',{}).items():
            if region in physical and (region!='bios' or not name.startswith('aes-')):physical[region].update(offsets)
    from .neogeo_knowledge import hints
    known,known_ram,known_z80,usage=hints(project)
    for region in physical:physical[region].update(known[region])
    main_ram+=known_ram;ram+=known_z80
    atomic_json(project/'knowledge-use.json',usage)
    emit(f'Neo Geo knowledge: {usage["shared"]} shared and {usage["local"]} local numeric hints; fresh reference checks remain active.')
    prepare_project(project,content=project/'cartridge.neo',bios=project/'bios.zip',title=title,native=True,native_sound=True,
                    presentation=presentation)
    main=generate(project,seeds,physical,main_ram);sound=generate_sound(project,ROOT/'.deps/geolith-libretro',ram)
    emit(f'Neo Geo: translating {main["translated_instructions"]} P/BIOS instructions and {sound["structural_bodies"]} sound bodies.')
    binary=configure_build(project,'game');checks=[]
    def verify(row):
        name,(frames,_)=row
        native=probe(binary,name+'-native',frames,observations/(name+'.inputs'))
        compare(native,references[name],require_native=False)
        check={'route':name,'frames':frames,'passed':True,
            'main_native':native['native_68000'],'main_fallback':native['interpreted_68000'],
            'sound_native':native['native_z80'],'sound_fallback':native['interpreted_z80']}
        emit(f'Neo Geo: {name} matches reference; fallback main={native["interpreted_68000"]}, sound={native["interpreted_z80"]}.')
        return check
    if not defer_to_packed:
        with ThreadPoolExecutor(max_workers=validation_workers) as pool:
            checks = list(pool.map(verify,routes.items()))
    atomic_json(project/'native-validation.json',{'passed':not defer_to_packed,
        'awaiting_packed_validation':defer_to_packed,'routes':checks,'main':main,'sound':sound,
        'reference_sha256':hashlib.sha256(baseline.read_bytes()).hexdigest(),
        'native_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),
        'physical_bus_phases_qualified':False,'physical_latency_measured':False,'knowledge_promoted':False})
    return binary


def convert_native(path: Path,*,bios: Path,output: Path | None = None,
                   set_name: str | None = None,emit=print) -> Path:
    return convert_reference(path,bios=bios,output=output,set_name=set_name,emit=emit,native=True)
