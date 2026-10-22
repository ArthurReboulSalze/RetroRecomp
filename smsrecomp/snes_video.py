"""Original display adaptations applied to a private pinned SNES runtime.

Keep both main/sub dots of a hires pair and both interlace fields. Ordinary
256-pixel rendering retains the pinned renderer. Never change guest VRAM.
"""
from .snes_timing import replace

FLAG = 0x80000000


def legacy(source, *, checks=False):
    # Presentation state is immutable during a line. Decode each row once,
    # preserving the scalar sampler for differential diagnostics.
    marker = 'void ppu_draw_whole_line_legacy(Ppu *ppu, int line) {'
    source = replace(source, marker, '#include "snes_ppu_cache.inc"\n' + marker +
                     '\n  rr_sn_bg_cache_reset();\n  rr_sn_prepare_layers(ppu);')
    marker = 'static int ppu_sample_bg(Ppu *ppu, int x, int y, int layer, bool priority) {'
    source = replace(source, marker,
        '''static int rr_sn_sample_bg_reference(Ppu *ppu, int x, int y, int layer, bool priority) {''')
    source += '''
static int ppu_sample_bg(Ppu *ppu,int x,int y,int layer,bool priority) {
#ifdef RR_SN_BG_CACHE_REFERENCE
  return rr_sn_sample_bg_reference(ppu,x,y,layer,priority);
#else
  return rr_sn_sample_bg_cached(ppu,x,y,layer,priority);
#endif
}
'''
    # Screen enables and priority order are constant in this presentation
    # line. Windows, scroll, mosaic and tile selection remain per-pixel.
    start = source.index('static int ppu_resolve_pixel(Ppu *ppu, int x, int y, bool sub,\n'
                         '                             int *r, int *g, int *b) {')
    end = source.index('\nstatic bool ppu_apply_layer_anchor', start)
    reference = source[start:end].replace('ppu_resolve_pixel(', 'rr_sn_resolve_reference(', 1)
    reference = reference.replace('ppu_sample_bg(', 'rr_sn_sample_bg_reference(')
    source = replace(source,
        '''  for (int i = 0; i < layer_count_per_mode[actMode]; i++) {
    int curLayer = layers_per_mode[actMode][i];
    int curPriority = priorities_per_mode[actMode][i];
    bool layerActive = IS_SCREEN_ENABLED(ppu, sub, curLayer) && (
      !IS_SCREEN_WINDOWED(ppu, sub, curLayer) || !ppu_window_contains(ppu, curLayer, x)
      );''',
        '''  if (rr_sn_line.active && y == rr_sn_line.y) rr_sn_line_pick(ppu, x, sub, &layer, &pixel);
  else for (unsigned i = 0; i < rr_sn_layers.count[sub]; i++) {
    int curLayer = rr_sn_layers.layer[sub][i];
    int curPriority = rr_sn_layers.priority[sub][i];
    bool layerActive = !IS_SCREEN_WINDOWED(ppu, sub, curLayer) || !ppu_window_contains(ppu, curLayer, x);''')
    # A whole presentation line samples each layer once (snes_ppu_cache.inc).
    source = replace(source, '''  for (int x = left; x < right; x++) {
    ppu_render_pixel(ppu, x, line);
  }
}''', '''#ifndef RR_SN_LINE_REFERENCE
  rr_sn_line_begin(ppu, line);
#endif
  for (int x = left; x < right; x++) {
    ppu_render_pixel(ppu, x, line);
  }
  rr_sn_line.active = 0;
}''')
    # The hires path computes both DAC dots itself. Do not resolve the same
    # pixels a first time in the ordinary-width renderer.
    source = replace(source, 'static void ppu_render_pixel(Ppu *ppu, int x, int y) {',
        '''static void ppu_render_pixel(Ppu *ppu, int x, int y) {
  if ((ppu->renderFlags & 0x80000000u) &&
      (PPU_pseudoHires(ppu) || PPU_mode(ppu)==5 || PPU_mode(ppu)==6)) {
    rr_sn_render_pair(ppu,x,y,0,0,0,0,0,0);
    return;
  }''')
    if checks:
        source += '\n' + reference
    # A dedicated flag keeps upstream clients' narrow buffers safe.
    source = replace(source, '  int row = y - 1;', '''  if (ppu->renderFlags & 0x80000000u) {
    rr_sn_render_pair(ppu, x, y, r, g, b, r2, g2, b2);
    return;
  }
  int row = y - 1;''')
    marker = 'static void ppu_render_pixel(Ppu *ppu, int x, int y);'
    source = replace(source, marker, marker + '''
static void rr_sn_render_pair(Ppu *, int, int, int, int, int, int, int, int);
''')
    return source + '''
/* The DAC emits subscreen then main-screen dots at twice the normal rate.
 * Color math on a subscreen dot uses the preceding main dot's state.
 * Reference contract: ares/sfc/ppu/dac.cpp (ISC); original implementation. */
static int rr_sn_previous[3], rr_sn_prev_clip, rr_sn_prev_math;
static int rr_sn_prev_blend, rr_sn_prev_half;
static int rr_sn_blend(int a, int b, int subtract, int half) {
  int v = subtract ? a - b : a + b;
  if (half) v >>= 1;
  return v < 0 ? 0 : v > 31 ? 31 : v;
}
static uint32_t rr_sn_rgb(Ppu *ppu, const int rgb[3]) {
  unsigned brightness = PPU_brightness(ppu);
  unsigned r = ((rgb[0] << 3) | (rgb[0] >> 2)) * brightness / 15;
  unsigned g = ((rgb[1] << 3) | (rgb[1] >> 2)) * brightness / 15;
  unsigned b = ((rgb[2] << 3) | (rgb[2] >> 2)) * brightness / 15;
  return (r << 16) | (g << 8) | b;
}
static void rr_sn_render_pair(Ppu *ppu, int x, int y,
                             int r, int g, int b, int r2, int g2, int b2) {
  int density = ppu->frameInterlace ? 2 : 1;
  int row = (y - 1) * density + (density == 2 && !ppu->evenFrame);
  uint32_t *out = (uint32_t *)(ppu->renderBuffer + row * ppu->renderPitch) + x * 2;
  if (x == 0) {
    uint16_t color = ppu->cgram[0];
    rr_sn_previous[0]=color&31; rr_sn_previous[1]=(color>>5)&31; rr_sn_previous[2]=(color>>10)&31;
    rr_sn_prev_clip=rr_sn_prev_math=rr_sn_prev_blend=rr_sn_prev_half=0;
  }
  if (!(PPU_pseudoHires(ppu) || PPU_mode(ppu)==5 || PPU_mode(ppu)==6)) {
    int rgb[3]={r,g,b}; out[0]=out[1]=rr_sn_rgb(ppu,rgb); return;
  }
  if (PPU_forcedBlank(ppu)) { out[0]=out[1]=0; return; }
  int above[3], below[3], fixed[3]={PPU_fixedColorR(ppu),PPU_fixedColorG(ppu),PPU_fixedColorB(ppu)};
  int layer=ppu_resolve_pixel(ppu,x,y,false,&above[0],&above[1],&above[2]);
  int sublayer=ppu_resolve_pixel(ppu,x,y,true,&below[0],&below[1],&below[2]);
  int window=ppu_window_contains(ppu,5,x);
  int clip=!(PPU_clipMode(ppu)==3 || (PPU_clipMode(ppu)==2 && window) || (PPU_clipMode(ppu)==1 && !window));
  int math=layer<6 && ((PPU_mathEnabled(ppu)>>layer)&1) &&
    !(PPU_preventMathMode(ppu)==3 || (PPU_preventMathMode(ppu)==2 && window) || (PPU_preventMathMode(ppu)==1 && !window));
  int blend=PPU_addSubscreen(ppu) && sublayer!=5;
  int half=PPU_halfColor(ppu) && clip && (!PPU_addSubscreen(ppu) || sublayer!=5);
  int a[3], s[3];
  for (int n=0;n<3;n++) {
    s[n]=rr_sn_prev_clip ? below[n] : 0;
    if(rr_sn_prev_math) s[n]=rr_sn_blend(s[n],rr_sn_prev_blend?rr_sn_previous[n]:fixed[n],PPU_subtractColor(ppu),rr_sn_prev_half);
    a[n]=clip ? above[n] : 0;
    if(math) a[n]=rr_sn_blend(a[n],blend?below[n]:fixed[n],PPU_subtractColor(ppu),half);
    rr_sn_previous[n]=above[n];
  }
  rr_sn_prev_clip=clip;rr_sn_prev_math=math;rr_sn_prev_blend=blend;rr_sn_prev_half=half;
  out[0]=rr_sn_rgb(ppu,s);out[1]=rr_sn_rgb(ppu,a);
}
'''


def ppu(source):
    # Parity and field modes belong to the beam, not an optional render walk.
    source = replace(source, '    ppu->evenFrame = !ppu->evenFrame;', '')
    source = replace(source, '  int count;\n  uint32_t dropped;\n  PpuRasterEntry e[PPU_RASTER_MAX];',
        '  int count;\n  uint32_t dropped;\n  bool wrapped;\n  PpuRasterEntry e[PPU_RASTER_MAX];')
    source = replace(source, '  f->dropped = 0;', '  f->dropped = 0;\n  f->wrapped = false;')
    source = replace(source, '  raster_snapshot(&s_field[0], ppu);',
        '  raster_snapshot(&s_field[0], ppu);\n'
        '  s_field[0].wrapped = g_snes->vPos < (ppu->frameOverscan ? 240u : 225u);')
    source = replace(source, '  f->e[f->count].key = raster_key(line);',
        '  f->e[f->count].key = line + (f->wrapped ? RR_SN_LINES + 1u : 0u);')
    source = replace(source, '  limit = raster_key((uint16_t)line);',
        '  limit = (uint16_t)(RR_SN_LINES + 1u + line);')
    source = replace(source, 'const unsigned line = key < (RR_SN_LINES - 225) ? key + 225 : key - (RR_SN_LINES - 225);',
        'const unsigned line = key % (RR_SN_LINES + 1u);')
    return source + '''
void rr_sn_raster_wrap(void) {
  if(s_raster_armed) s_field[s_raster_cur].wrapped=true;
}
'''


def bus(source):
    source = source.replace('225u', 'RR_SN_VBLANK_LINE')
    source = replace(source, 'snes->vPos >= 225)', 'snes->vPos >= RR_SN_VBLANK_LINE)')
    # Existing region adapter supplies RR_SN_LINES, now add the extra odd
    # interlace field line. Field modes latch at the actual V=0 boundary.
    source = source.replace('RR_SN_LINES', 'RR_SN_FIELD_LINES')
    source = replace(source, 'if (v == 0u) snes->rdnmiPending = false;',
        'if (v == 0u) { snes->rdnmiPending = false; rr_sn_begin_field(); }')
    source = replace(source, '        snes->rdnmiPending = false;\n        if (check_irq',
        '        snes->rdnmiPending = false; rr_sn_begin_field();\n        if (check_irq')
    prefix = '''
extern void rr_sn_raster_wrap(void);
extern void rr_sn_adjust_field_deadline(unsigned line);
#define RR_SN_FIELD_LINES (RR_SN_LINES + (g_ppu->frameInterlace && !g_ppu->evenFrame))
#define RR_SN_VBLANK_LINE (g_ppu->frameOverscan ? 240u : 225u)
static void rr_sn_begin_field(void) {
  g_ppu->evenFrame=!g_ppu->evenFrame;
  g_ppu->frameOverscan=PPU_overscan(g_ppu);
  g_ppu->frameInterlace=PPU_interlace(g_ppu);
  rr_sn_raster_wrap();
  rr_sn_adjust_field_deadline(RR_SN_VBLANK_LINE);
}
'''
    marker='static const double apuCyclesPerMaster'
    return source.replace(marker, prefix+'\n'+marker,1)


def frame_driver(source):
    source = replace(source, '#define BFD_VBLANK_LINE 225u',
        '#define BFD_VBLANK_LINE (g_ppu->frameOverscan ? 240u : 225u)')
    source = replace(source, ': BFD_MASTER_CYCLES_PER_FIELD);',
        ': (1364ull * (RR_SN_LINES + (g_ppu->frameInterlace && !g_ppu->evenFrame))));')
    # Update an armed deadline at V=0, including during a busy opcode loop or
    # a suspended interrupt. Both enabling and disabling overscan must take
    # effect before the newly selected vblank edge is crossed.
    source=replace(source,'static uint32_t s_resume_pc;', '''static uint32_t s_resume_pc;
static uint64_t rr_sn_frame_end;
static unsigned rr_sn_end_line;
static bool rr_sn_field_running;
void rr_sn_adjust_field_deadline(unsigned line) {
  if(!rr_sn_field_running || line==rr_sn_end_line)return;
  if(line>rr_sn_end_line) rr_sn_frame_end+=(line-rr_sn_end_line)*1364ull;
  else rr_sn_frame_end-=(rr_sn_end_line-line)*1364ull;
  rr_sn_end_line=line;
  interp_bridge_set_master_deadline(rr_sn_frame_end);
}''')
    source=replace(source,'  if (booting) {\n    s_resume_pc = reset_vector();',
        '  rr_sn_frame_end=frame_end; rr_sn_end_line=BFD_VBLANK_LINE; rr_sn_field_running=true;\n'
        '  if (booting) {\n    s_resume_pc = reset_vector();')
    for marker in ('    run_interrupt(nmi_vector(), frame_end);',
                   '      run_interrupt(irq_vector(), frame_end);',
                   '      (void)interp_bridge_run_until_quiescent(&g_cpu, s_resume_pc);'):
        source=replace(source,marker,marker+'\n    frame_end=rr_sn_frame_end;')
    source=replace(source,'    cart_sync_coprocessors(g_snes->cart, g_cpu.master_cycles);\n  }\n}',
        '    cart_sync_coprocessors(g_snes->cart, g_cpu.master_cycles);\n  }\n  rr_sn_field_running=false;\n}')
    source = replace(source, '    ppu_checkOverscan(g_ppu);', '')
    # Mode flags already latched by the bus, do not relatch at NMI.
    source = replace(source, '    ppu_handleVblank(g_ppu);',
        '    bool mode=g_ppu->frameInterlace; ppu_handleVblank(g_ppu); g_ppu->frameInterlace=mode;')
    source = replace(source, '  for (line = 1; line <= 224; line++) {',
        '  ppu_runLine(g_ppu,0);\n  for (line = 1; line <= (g_ppu->frameOverscan ? 239 : 224); line++) {')
    return source


def adapt_engine(staged):
    for name,adapt in (('snes/ppu_legacy.c',legacy),('snes/ppu.c',ppu),
                       ('snes/snes.c',bus),('beam_frame_driver.c',frame_driver)):
        path=staged/'runner/src'/name
        path.write_text(adapt(path.read_text(encoding='utf-8')),encoding='utf-8')
