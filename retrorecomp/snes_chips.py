"""Explicit DSP-1, CX4 and Super FX integration; other cartridge circuits remain gated."""
from .cartridge16 import snes_header
from .core import ConversionError
from .snes_timing import replace

# Super FX (MARIO chip, GSU-1, GSU-2) boards: map $20, cartridge type $13-$15 or
# $1A. The GSU itself runs on the pinned engine's counted instruction core.
SUPERFX_TYPES=(0x13,0x14,0x15,0x1a)

REPORT_FIELDS=('cartridge_chip','coprocessor_mode','coprocessor_state_hash',
               'coprocessor_instructions','coprocessor_failed','coprocessor_commands')



def device_entry(checks):
    """The cartridge device's figures, apart from the CPUs' (None without one).

    The 65816 and SPC700 percentages never include device instructions: a GSU
    runs tens of millions of them per scenario and would swamp both. They stay
    visible here as interpreted device instructions per scenario and per frame.
    """
    checks=[check for check in checks if isinstance(check,dict)]
    chip=next((check['cartridge_chip'] for check in checks
               if check.get('cartridge_chip') not in (None,'none')),None)
    if chip is None:return None
    rows=[]
    for check in checks:
        count=int(check.get('coprocessor_instructions') or 0)
        frames=int(check.get('frames') or 0)
        rows.append({'scenario':check.get('scenario'),'frames':frames,'interpreted_instructions':count,
                     'interpreted_per_frame':round(count/max(1,frames),3),
                     'commands':int(check.get('coprocessor_commands') or 0)})
    return {'chip':chip,'mode':checks[-1].get('coprocessor_mode','not_run'),
            'counter_unit':'device instructions','scenarios':rows,
            'failed':any(check.get('coprocessor_failed') for check in checks)}


def device_summary(report):
    """Chip, mode and the largest interpreted device figures of a conversion report.

    Reports written before the separate entry existed carry the same numbers in
    their checks, so they read the same way. None when the cartridge has no device.
    """
    try:
        entry=report.get('cartridge_device') or device_entry(report.get('final_checks') or ())
        rows=entry['scenarios'] if entry else ()
        return None if not entry else {'chip':entry['chip'],'mode':entry.get('mode'),
            'instructions':max((row['interpreted_instructions'] for row in rows),default=0),
            'per_frame':max((row['interpreted_per_frame'] for row in rows),default=0)}
    except (AttributeError,KeyError,TypeError,ValueError):
        return None


def main_interpreted(check):
    """65816 interpreted opcodes of one check, never the device's."""
    value=check.get('main_interpreted_opcodes')
    return check.get('interpreted_opcodes',0) if value is None else value


# Command aliases follow the independent Snes9x DSP1SetByte decode. ROM-dump
# commands deliberately remain unsupported: this model contains no firmware.
DSP1_ALIASES = {0x30:0x10,0x24:4,0x2c:12,0x3c:0x1c,
    **{op:2 for op in (0x12,0x22,0x32)},
    **{op:10 for op in (0x1a,0x2a,0x3a)},
    **{op:6 for op in (0x16,0x26,0x36)},
    **{op:14 for op in (0x1e,0x2e,0x3e)},
    **{op:1 for op in (5,0x35,0x31)},0x15:0x11,0x25:0x21,
    **{op:13 for op in (9,0x39,0x3d)},0x19:0x1d,0x29:0x2d,
    0x33:3,0x3b:11,0x34:0x14,7:15,0x27:0x2f}


def command_decoder():
    cases=''.join(f'case 0x{op:02x}:return 0x{canonical:02x};' for op,canonical in sorted(DSP1_ALIASES.items()))
    return 'static inline uint8_t rr_dsp1_command(uint8_t op) {switch(op){'+cases+'default:return op;}}\n'


def identify(data):
    header=snes_header(data)
    if not header:return 'none'
    offset,mapping=header;mode,kind=data[offset+21:offset+23]
    if kind in (0,1,2):return 'none'
    if mode==0x20 and kind==0xf3 and offset>=16 and data[offset-1]==0x10:return 'cx4'
    if mode==0x20 and kind==3:return 'dsp1-lo'
    # HiROM DSP-1 boards: the DSP-1 sits at $00-$1F:$6000-$7FFF; type $05 adds battery RAM at $20-$3F:$6000-$7FFF, type $03 has none.
    if mode==0x31 and kind in (3,5) and mapping=='hirom':return 'dsp1-hi'
    if mode==0x20 and kind in SUPERFX_TYPES and mapping=='lorom':return 'superfx'
    family=({1:'Super FX',3:'SA-1',4:'S-DD1'}.get(kind>>4) or
            ('DSP-4' if mode==0x30 and kind==3 else
             'DSP-2' if mode==0x20 and kind==5 else
             'SPC7110' if mode==0x3a and kind in (0xf5,0xf9) else 'custom circuitry'))
    raise ConversionError(f'SNES enhancement chip {family} is not integrated yet (map ${mode:02X}, type ${kind:02X}). '
                          'DSP-2/3/4, SA-1, S-DD1 and other custom chips remain unsupported.')


def cart_header(source):
    source=replace(source,'''  return cart_has_dsp1(cart) && adr >= 0x6000 && adr < 0x8000 &&
         (bank < 0x20 || (bank >= 0x80 && bank < 0xa0));''','''  if(!cart_has_dsp1(cart))return false;
  uint8_t canonical=bank&0x7f;
  if(cart->type==CART_DSP1 && cart->romImageSize<=0x100000)
    return canonical>=0x20 && canonical<0x40 && adr>=0x8000;
  return canonical<0x20 && adr>=0x6000 && adr<0x8000;''')
    source=replace(source,'static inline uint16_t cart_dsp1_register(uint16_t adr) {\n  return (uint16_t)((adr >> 12) & 1u);\n}',
        '''static inline uint16_t cart_dsp1_register(const Cart *cart,uint16_t adr) {
  if(cart->type==CART_DSP1 && cart->romImageSize<=0x100000)return (adr>>14)&1u;
  return (adr>>12)&1u;
}''')
    source=replace(source,'''  return cart_has_dsp1(cart) && adr >= 0x6000 && adr < 0x8000 &&''',
        '''  return cart && cart->type==CART_DSP1_HIROM && adr >= 0x6000 && adr < 0x8000 &&''')
    return source


def loader(source):
    start=source.index('  bool has_smk_title =')
    end=source.index('  if (has_smk_dsp1_map)',start)
    return source[:start]+'''  bool has_smk_dsp1_hirom = has_nec_dsp && headers[used].speed==3 &&
      headers[used].type==1 && (headers[used].chips==3 || headers[used].chips==5);
'''+source[end:]


def superfx_header(source):
    """Inline shortcut for the catch-up call the 65816 side makes after nearly every opcode.

    superfx_sync() starts an instruction only while six clocks of credit exist, so a call that
    leaves the credit under six just banks the clocks: the same two stores the full function
    makes before its loop. 80 to 94 percent of the calls made while the GSU runs are of that
    kind (docs/SNES_SUPERFX.md). A stopped GSU with no ROM or RAM access in flight spends the
    credit six clocks at a time and nothing else (see superfx() below): the same remainder in one
    step. SFR.G is bit 5; a presentation replay or a widescreen replay (never enabled by
    Retro-Recomp) takes the full function."""
    return replace(source,'void superfx_sync(SuperFx *fx, uint64_t master_clock);','''void superfx_sync(SuperFx *fx, uint64_t master_clock);
static inline void superfx_sync_credit(SuperFx *fx, uint64_t master_clock) {
  if (master_clock >= fx->master_clock) {
    int64_t credit = fx->clock_credit + (int64_t)(master_clock - fx->master_clock);
    if (credit < 6) { fx->clock_credit = credit; fx->master_clock = master_clock; return; }
    if (!(fx->sfr & 0x20) && !fx->romcl && !fx->ramcl && !fx->presentation && !fx->ws_replay_pending &&
        credit < 12000000) {
      fx->clock_credit = credit - (credit / 6) * 6; fx->master_clock = master_clock; return;
    }
  }
  superfx_sync(fx, master_clock);
}''')


def cart_header_sync(source):
    """cart_sync_coprocessors() becomes an inline that takes the Super FX shortcut; every other
    device keeps the original function (renamed). A cartridge carries one device, so the Super FX
    case needs none of the other checks."""
    source=replace(source,'#include "snes.h"\n','#include "snes.h"\n#include "superfx.h"\n')
    return replace(source,'void cart_sync_coprocessors(Cart *cart, uint64_t master_clock);',
        '''void cart_sync_coprocessors_device(Cart *cart, uint64_t master_clock);
static inline void cart_sync_coprocessors(Cart *cart, uint64_t master_clock) {
  if (cart && cart->superfx) superfx_sync_credit(cart->superfx, master_clock);
  else cart_sync_coprocessors_device(cart, master_clock);
}''')


def cart(source):
    source=replace(source,'void cart_sync_coprocessors(Cart *cart, uint64_t master_clock) {\n  if (cart && cart->superfx) superfx_sync(cart->superfx, master_clock);',
        'void cart_sync_coprocessors_device(Cart *cart, uint64_t master_clock) {\n  if (cart && cart->superfx) superfx_sync(cart->superfx, master_clock);')
    source=replace(source,'cart_dsp1_register(adr)','cart_dsp1_register(cart,adr)',count=2)
    return replace(source,'    case CART_DSP1: {\n      if (cart_is_dsp1_window',
        '    case CART_DSP1: {\n      if(rr_snes_cart_ram_offset(cart,bank,adr)>=0)return NULL;\n      if (cart_is_dsp1_window')


def dsp1(source):
    start=source.index('  const char *env = getenv("SNESRECOMP_DSP1_ROM");',source.index('int dsp1_load_firmware('))
    end=source.index('  d->hle_active = 1;',start)
    source=source[:start]+source[end:]
    source=replace(source,'  sli->func(sli, &d->hle, sizeof(d->hle));',
        '  sli->func(sli, &d->hle, sizeof(d->hle));\n  sli->func(sli,&d->last_master,sizeof d->last_master);')
    source=replace(source,'provide DSP-1 firmware to continue','this command is not supported by the firmware-free model')
    source=replace(source,'[dsp1] no firmware found; using firmware-free HLE. ', '[dsp1] using the firmware-free command model. ')
    source=replace(source,'Unverified commands stop execution and request firmware.', 'Unsupported commands stop validation.')
    source=replace(source,'  d->command_count[command]++;\n  d->hle.command = command;',
        '  d->command_count[command]++;\n  command=rr_dsp1_command(command);\n  d->hle.command = command;')
    source=replace(source,'''  if (!dsp1_hle_command_shape(command, &input_words, &output_words)) {
    dsp1_hle_fail(d, command);
    return;
  }''','''  if (!dsp1_hle_command_shape(command, &input_words, &output_words)) {
    /* Unassigned command bytes are idle/no-op on the command port.
     * Recognized ROM-dump operations cannot be synthesized without firmware. */
    if(command==0x17 || command==0x37 || command==0x3f || command==0x1f)
      dsp1_hle_fail(d,command);
    else dsp1_hle_command_ready(d);
    return;
  }''')
    return '#include "retro_snes_game.h"\n'+replace(source,'kSnesMasterHz = 21477272,',
        'kSnesMasterHz = RR_SN_PAL ? 21281370 : 21477272,')


def cx4(source):
    start=source.index('  char buf[1024];',source.index('int cx4_load_firmware('))
    end=source.index('  return 1;\n}',start)
    source=source[:start]+source[end:]
    return '#include "retro_snes_game.h"\n'+replace(source,'kSnesMasterHz = 21477272,',
        'kSnesMasterHz = RR_SN_PAL ? 21281370 : 21477272,')


def dsp1_model(source):
    source=replace(source,'  uint8_t inputs;\n  uint8_t outputs;',
        '  command=rr_dsp1_command(command);\n  uint8_t inputs;\n  uint8_t outputs;')
    source=replace(source,'  uint8_t expected_inputs;\n  uint8_t expected_outputs;',
        '  command=rr_dsp1_command(command);\n  uint8_t expected_inputs;\n  uint8_t expected_outputs;')
    source=replace(source,'bool dsp1_hle_execute_state(',
        '#include "snes_dsp1_projection.inc"\n\nbool dsp1_hle_execute_state(')
    start=source.index('    case 0x02: {',source.index('bool dsp1_hle_execute_state('))
    end=source.index('    case 0x06: {',start)
    source=source[:start]+'''    case 0x02: {
      if(!rr_dsp1_projection(state,input,output))return false;
      break;
    }
'''+source[end:]
    source=replace(source,'''      int16_t vertical = (int16_t)(
          q15_multiply(
              px, q15_multiply(state->cos_azs,
                               (int16_t)-(int32_t)state->sin_aas)) +
          q15_multiply(py, q15_multiply(state->cos_azs, state->cos_aas)) +
          q15_multiply(
              pz, q15_multiply((int16_t)-(int32_t)state->sin_azs, 0x7fff)));''',
        '''      int16_t vertical=(int16_t)(
          rr_dsp1_axis(px,state->cos_azs,-(int32_t)state->sin_aas)+
          rr_dsp1_axis(py,state->cos_azs,state->cos_aas)+
          rr_dsp1_axis(pz,-(int32_t)state->sin_azs,INT16_MAX));''')
    source=replace(source,'''    case 0x0a: {
      if (!state || !state->projection_valid) return false;''','''    case 0x0a: {
      if(!state)return false;
      /* Pilotwings starts raster output before its first projection command.
       * Authored independent Snes9x probe: reset coefficients yield zeros. */
      if(!state->projection_valid) {
        output[0]=output[1]=output[2]=output[3]=0;
        break;
      }''')
    source=replace(source,'    case 0x10:\n      inputs = 2;',
        '    case 0x1c:\n      inputs=6; outputs=3; break;\n'
        '    case 0x38:\n      inputs=4; outputs=1; break;\n'
        '    case 0x0f: case 0x2f:\n      inputs=1; outputs=1; break;\n'
        '    case 0x0e:\n      inputs=2; outputs=2; break;\n'
        '    case 0x01: case 0x11: case 0x21:\n      inputs=4; outputs=0; break;\n'
        '    case 0x0d: case 0x1d: case 0x2d: case 0x03: case 0x13: case 0x23:\n      inputs=3; outputs=3; break;\n'
        '    case 0x0b: case 0x1b: case 0x2b:\n      inputs=3; outputs=1; break;\n'
        '    case 0x14:\n      inputs=6; outputs=3; break;\n    case 0x10:\n      inputs = 2;')
    return replace(source,'    case 0x06: {\n      if (!state', '''    case 0x0f: output[0]=0; break;
    case 0x2f: output[0]=0x100; break;
    case 0x38: {
      int64_t value=(int64_t)input[0]*input[0]+(int64_t)input[1]*input[1]+
          (int64_t)input[2]*input[2]-(int64_t)input[3]*input[3];
      output[0]=(int16_t)((value>>15)+1);break;
    }
    case 0x1c: {
      int16_t sz=dsp1_sin((uint16_t)input[0]),cz=dsp1_cos((uint16_t)input[0]);
      int16_t sy=dsp1_sin((uint16_t)input[1]),cy=dsp1_cos((uint16_t)input[1]);
      int16_t sx=dsp1_sin((uint16_t)input[2]),cx=dsp1_cos((uint16_t)input[2]);
      int16_t x=(int16_t)(q15_multiply(input[4],sz)+q15_multiply(input[3],cz));
      int16_t y=(int16_t)(q15_multiply(input[4],cz)-q15_multiply(input[3],sz));
      int16_t z=(int16_t)(q15_multiply(x,sy)+q15_multiply(input[5],cy));
      output[0]=(int16_t)(q15_multiply(x,cy)-q15_multiply(input[5],sy));
      output[1]=(int16_t)(q15_multiply(z,sx)+q15_multiply(y,cx));
      output[2]=(int16_t)(q15_multiply(z,cx)-q15_multiply(y,sx));break;
    }
    case 0x01: case 0x11: case 0x21: {
      if(!state)return false;
      int16_t (*matrix)[3]=state->matrix[command>>4];
      int16_t m=input[0]>>1;
      int16_t sz=dsp1_sin((uint16_t)input[1]),cz=dsp1_cos((uint16_t)input[1]);
      int16_t sy=dsp1_sin((uint16_t)input[2]),cy=dsp1_cos((uint16_t)input[2]);
      int16_t sx=dsp1_sin((uint16_t)input[3]),cx=dsp1_cos((uint16_t)input[3]);
      int16_t mz=q15_multiply(m,sz),mc=q15_multiply(m,cz);
      matrix[0][0]=q15_multiply(mc,cy);
      matrix[0][1]=(int16_t)-(int32_t)q15_multiply(mz,cy);
      matrix[0][2]=q15_multiply(m,sy);
      matrix[1][0]=(int16_t)(q15_multiply(mz,cx)+q15_multiply(q15_multiply(mc,sx),sy));
      matrix[1][1]=(int16_t)(q15_multiply(mc,cx)-q15_multiply(q15_multiply(mz,sx),sy));
      matrix[1][2]=(int16_t)-(int32_t)q15_multiply(q15_multiply(m,sx),cy);
      matrix[2][0]=(int16_t)(q15_multiply(mz,sx)-q15_multiply(q15_multiply(mc,cx),sy));
      matrix[2][1]=(int16_t)(q15_multiply(mc,sx)+q15_multiply(q15_multiply(mz,cx),sy));
      matrix[2][2]=q15_multiply(q15_multiply(m,cx),cy);
      break;
    }
    case 0x0d: case 0x1d: case 0x2d:
    case 0x03: case 0x13: case 0x23: {
      if(!state)return false;
      int16_t (*matrix)[3]=state->matrix[command>>4];
      for(unsigned row=0;row<3;row++) {
        int32_t value=0;
        for(unsigned col=0;col<3;col++)value+=q15_multiply(input[col],
            (command&15)==13 ? matrix[row][col] : matrix[col][row]);
        output[row]=(int16_t)value;
      }
      break;
    }
    case 0x0b: case 0x1b: case 0x2b: {
      if(!state)return false;
      int16_t (*matrix)[3]=state->matrix[command>>4];int64_t value=0;
      for(unsigned col=0;col<3;col++)value+=(int32_t)input[col]*matrix[0][col];
      output[0]=(int16_t)(value>>15);break;
    }
    case 0x14: {
      int16_t sec,sec_exponent,c,e,sine,tangent;
      int16_t sy=dsp1_sin((uint16_t)input[2]),cy=dsp1_cos((uint16_t)input[2]);
      inverse(dsp1_cos((uint16_t)input[1]),0,&sec,&sec_exponent);
      normalize_double((int32_t)input[3]*cy-(int32_t)input[4]*sy,&c,&e);
      e=(int16_t)(sec_exponent-e);
      normalize(q15_multiply(c,sec),&c,&e);
      output[0]=(int16_t)(input[0]+truncate_coefficient(c,e));
      output[1]=(int16_t)(input[1]+q15_multiply(input[3],sy)+q15_multiply(input[4],cy));
      normalize_double((int32_t)input[3]*cy+(int32_t)input[4]*sy,&c,&e);
      e=(int16_t)(sec_exponent-e);
      normalize(dsp1_sin((uint16_t)input[1]),&sine,&e);
      tangent=q15_multiply(sec,sine);
      normalize((int16_t)-(int32_t)q15_multiply(c,tangent),&c,&e);
      output[2]=(int16_t)(input[2]+truncate_coefficient(c,e)+input[5]);
      break;
    }
    case 0x0e: {
      /* Screen-to-ground projection expressed in the model's existing Q15
       * coefficient/exponent coordinates; no firmware table is imported. */
      if(!state)return false;
      int16_t coefficient,exponent,scale,vertical_exponent;
      inverse((int16_t)(q15_multiply(input[1],state->sin_azs)+state->v_offset),8,&coefficient,&exponent);
      exponent=(int16_t)(exponent+state->vplane_exponent);
      scale=q15_multiply(coefficient,state->vplane_coefficient);
      vertical_exponent=(int16_t)(exponent+state->target_sec_exponent);
      normalize(scale,&coefficient,&exponent);
      coefficient=q15_multiply(truncate_coefficient(coefficient,exponent),(int16_t)((uint16_t)input[0]<<8));
      output[0]=(int16_t)(state->center_x+q15_multiply(coefficient,state->cos_aas));
      output[1]=(int16_t)(state->center_y-q15_multiply(coefficient,state->sin_aas));
      normalize(q15_multiply(scale,state->target_sec_coefficient),&coefficient,&vertical_exponent);
      coefficient=q15_multiply(truncate_coefficient(coefficient,vertical_exponent),(int16_t)((uint16_t)input[1]<<8));
      output[0]=(int16_t)(output[0]+q15_multiply(coefficient,(int16_t)-(int32_t)state->sin_aas));
      output[1]=(int16_t)(output[1]+q15_multiply(coefficient,state->cos_aas));
      break;
    }
    case 0x06: {
      if (!state''')


def dsp1_model_header(source):
    source += '\n'+command_decoder()
    return replace(source,'  bool projection_valid;',
        '  int16_t center_x,center_y;\n  int16_t matrix[3][3][3];\n'
        '  int16_t target_sec_coefficient,target_sec_exponent;\n  bool projection_valid;')


def superfx(source):
    """Code-cache window as fullsnes documents it: GSU address A is at S-CPU address
    3100h + (A AND 1FFh), so the S-CPU offset X holds cache slot (X - CBR) mod 512, the slot the
    opcode fetch uses for A = CBR + slot. The pinned core adds CBR instead of subtracting it,
    which agrees only while 2*CBR is a multiple of 512 (the documented example, CBR=C3A0, shows
    the difference). Checked by tools/snes_superfx_selftest.py (cache_window_* cases).

    Bus ownership (SCMR RON/RAN): the GSU waits instead of reading and writing a Game Pak bus the
    S-CPU owns (SUPERFX_BUS_WAIT below; bus_ownership_checks in native/snes_superfx_checks.c)."""
    source=replace(source,'return f->cache[(uint16_t)(a + f->cbr) & 511];','return f->cache[(uint16_t)(a - f->cbr) & 511];')
    source=replace(source,'a = (uint16_t)(a + f->cbr) & 511;','a = (uint16_t)(a - f->cbr) & 511;')
    source=replace(source,'static void run_one(SuperFx *f) {\n  if (!(f->sfr & SFR_G)) { step_clocks(f, 6); return; }\n',
        SUPERFX_BUS_WAIT+'static void run_one(SuperFx *f) {\n  if (!(f->sfr & SFR_G)) { step_clocks(f, 6); return; }\n  if (gsu_bus_wait(f)) return;\n')
    # Almost every clock charge happens with no ROM or RAM access in flight: keep that case
    # inline (same arithmetic) and the countdown handling out of line (same function).
    source=replace(source,'static void step_clocks(SuperFx *f, unsigned clocks);\n','''static void step_clocks_slow(SuperFx *f, unsigned clocks);
static inline void step_clocks(SuperFx *f, unsigned clocks) {
  if (f->romcl | f->ramcl) { step_clocks_slow(f, clocks); return; }
  f->clock_credit -= clocks;
}
''')
    source=replace(source,'static void step_clocks(SuperFx *f, unsigned clocks) {\n  if (f->romcl) {','static void step_clocks_slow(SuperFx *f, unsigned clocks) {\n  if (f->romcl) {')
    # The instruction ring is read only by the engine's debug server, which Retro-Recomp games
    # never start; it cost five stores per instruction. Define RR_GSU_TRACE to keep it.
    source=replace(source,'''  uint64_t sequence=++f->instruction_count;
  SuperFxTraceEntry *trace=&f->trace[sequence&255];
  trace->sequence=sequence;
  trace->r15=rv(f,15);
  trace->sfr=f->sfr;
  trace->pbr=f->pbr;
  trace->opcode=op;
''','''  ++f->instruction_count;
#ifdef RR_GSU_TRACE
  {
    uint64_t sequence=f->instruction_count;
    SuperFxTraceEntry *trace=&f->trace[sequence&255];
    trace->sequence=sequence;
    trace->r15=rv(f,15);
    trace->sfr=f->sfr;
    trace->pbr=f->pbr;
    trace->opcode=op;
  }
#endif
''')
    source=replace(source,'static void run_one(SuperFx *f) {','''#if defined(_MSC_VER) && !defined(__clang__)
#define RR_GSU_ALWAYS_INLINE __forceinline
#else
#define RR_GSU_ALWAYS_INLINE inline __attribute__((always_inline))
#endif
static RR_GSU_ALWAYS_INLINE void run_one(SuperFx *f) {''')
    # A stopped GSU with no ROM or RAM access in flight does nothing in a catch-up iteration
    # but spend six clocks (run_one: step_clocks(f, 6)), so k iterations leave the credit
    # reduced by 6k with k = floor(credit / 6). Same result in one step, same iteration cap.
    return replace(source,'''  unsigned guard=0; while(f->clock_credit>=6 && guard++<2000000) {''','''  if(f->clock_credit>=6 && !(f->sfr&SFR_G) && !f->romcl && !f->ramcl &&
     !(f->presentation && f->presentation->pending) && !f->ws_replay_pending &&
     f->clock_credit/6<=2000000) {
    f->clock_credit-=(f->clock_credit/6)*6;
    return;
  }
  unsigned guard=0; while(f->clock_credit>=6 && guard++<2000000) {''')



# Game Pak bus ownership. fullsnes (SCMR, $303A): RON/RAN 0 = the S-CPU owns the ROM/RAM bus,
# 1 = the GSU; a GSU access to a bus the S-CPU owns puts the GSU in WAIT until it is handed back
# (ares, ISC, spins in its read/write paths the same way). The core runs each instruction
# atomically and cannot suspend inside one, so the wait is taken before the instruction starts.
# Dirt Racer depends on it: it writes display-list bytes into Game Pak RAM from the 65816 with
# RAN=0 while the GSU command loop is still running (checked by native/snes_superfx_checks.c).
SUPERFX_BUS_WAIT='''enum { GSU_BUS_ROM = 1, GSU_BUS_RAM = 2 };

static unsigned gsu_fetch_bus(const SuperFx *f, uint16_t a) {
  uint16_t off = (uint16_t)(a - f->cbr);
  if (off < 512 && f->cache_valid[off >> 4]) return 0;
  return f->pbr <= 0x5f ? GSU_BUS_ROM : GSU_BUS_RAM;
}

static unsigned gsu_bus_needed(const SuperFx *f, uint8_t op) {
  unsigned need = 0, operands = 0;
  if (f->romcl) need |= GSU_BUS_ROM;
  if (f->ramcl) need |= GSU_BUS_RAM;
  if (op >= 0x05 && op <= 0x0f) operands = 1;
  else if ((op >= 0x30 && op <= 0x3b) || (op >= 0x40 && op <= 0x4c) || op == 0x90)
    need |= GSU_BUS_RAM;
  else if (op >= 0xa0 && op <= 0xaf) {
    operands = 1;
    if (f->sfr & (SFR_ALT1 | SFR_ALT2)) need |= GSU_BUS_RAM;
  } else if (op >= 0xf0) {
    operands = 2;
    if (f->sfr & (SFR_ALT1 | SFR_ALT2)) need |= GSU_BUS_RAM;
  }
  for (unsigned n = 0; n <= operands; n++)
    need |= gsu_fetch_bus(f, (uint16_t)(f->r[15].data + n));
  return need;
}

static bool gsu_bus_wait(SuperFx *f) {
  unsigned owned = (scmr_ron(f) ? GSU_BUS_ROM : 0) | (scmr_ran(f) ? GSU_BUS_RAM : 0);
  if (!(gsu_bus_needed(f, f->pipeline) & ~owned)) return false;
  f->clock_credit -= 6;
  return true;
}

'''


def adapt_engine(staged):
    for filename,adapt in (('cart.h',lambda source:cart_header_sync(cart_header(source))),('cart.c',cart),('snes_other.c',loader),
                            ('dsp1.c',dsp1),('cx4.c',cx4),('superfx.h',superfx_header),('superfx.c',superfx),
                            ('dsp1_hle.c',dsp1_model),('dsp1_hle.h',dsp1_model_header)):
        path=staged/'runner/src/snes'/filename
        path.write_text(adapt(path.read_text(encoding='utf-8')),encoding='utf-8')
