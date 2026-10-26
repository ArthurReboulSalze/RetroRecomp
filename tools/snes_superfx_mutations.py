"""Mutation check of the authored Super FX suite.

Applies one small textual defect at a time to the *staged* copy of superfx.c that the
last tools/snes_superfx_selftest.py run built (a folder under .build, never .deps),
rebuilds, runs the suite and reports whether it noticed. A mutation that survives is
a hole in the checks (or an equivalent mutation, which is then said so here).
"""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# (name, old text, new text) -- each old text must occur exactly once in superfx.c
MUTATIONS = [
    ('adc ignores carry', '((f->sfr&SFR_ALT1)&&bit(f->sfr,2))', '0'),
    ('sbc borrow polarity', '(!(f->sfr&SFR_ALT2)&&(f->sfr&SFR_ALT1)&&!bit(f->sfr,2))', '(!(f->sfr&SFR_ALT2)&&(f->sfr&SFR_ALT1)&&bit(f->sfr,2))'),
    ('add overflow flag', '(~(sr(f)^q)&(q^z)&0x8000)', '((sr(f)^q)&(q^z)&0x8000)'),
    ('sub carry flag', 'flag(f,SFR_CY,z>=0);', 'flag(f,SFR_CY,z>0);'),
    ('cmp writes the register', 'if(!(f->sfr&SFR_ALT2)||!(f->sfr&SFR_ALT1)) wd(f,z);', 'wd(f,z);'),
    ('div2 rounding', '+((f->sfr&SFR_ALT1)?((sr(f)+1)>>16):0)', '+0'),
    ('merge zero flag', 'flag(f,SFR_Z,v&0xf0f0);', 'flag(f,SFR_Z,!(v&0xf0f0));'),
    ('merge overflow mask', 'flag(f,SFR_OV,v&0xc0c0);', 'flag(f,SFR_OV,v&0x8080);'),
    ('bge/blt swapped', '(op==6 && bit(f->sfr,3)==bit(f->sfr,4))', '(op==6 && bit(f->sfr,3)!=bit(f->sfr,4))'),
    ('bne inverted', '(op==8 && !bit(f->sfr,1))', '(op==8 && bit(f->sfr,1))'),
    ('bcs uses carry clear', '(op==0x0d && bit(f->sfr,2))', '(op==0x0d && !bit(f->sfr,2))'),
    ('loop condition', 'if(!bit(f->sfr,1)) wr(f,15,rv(f,13));', 'if(bit(f->sfr,1)) wr(f,15,rv(f,13));'),
    ('loop skips flags', 'wr(f,12,rv(f,12)-1); set_sz(f,rv(f,12));', 'wr(f,12,rv(f,12)-1);'),
    ('fmult carry', 'flag(f,SFR_CY,z&0x8000);', 'flag(f,SFR_CY,z&0x10000);'),
    ('lmult low half', 'if(f->sfr&SFR_ALT1) wr(f,4,z);', 'if(f->sfr&SFR_ALT1) wr(f,4,z>>16);'),
    ('mult signedness', '(int8_t)sr(f)*(int8_t)q', '(uint8_t)sr(f)*(uint8_t)q'),
    ('umult signedness', '(uint8_t)sr(f)*(uint8_t)q', '(int8_t)sr(f)*(int8_t)q'),
    ('getbs sign', 'default:wd(f,(int8_t)q);break;', 'default:wd(f,q);break;'),
    ('getbh keeps low byte', 'case 1:wd(f,(q<<8)|(uint8_t)sr(f));break;', 'case 1:wd(f,(q<<8));break;'),
    ('ibt sign extension', 'else wr(f,n,(int8_t)pipe(f));', 'else wr(f,n,(uint8_t)pipe(f));'),
    ('sex sign', 'if (op == 0x95) { wd(f,(int8_t)sr(f));', 'if (op == 0x95) { wd(f,(uint8_t)sr(f));'),
    ('ldw odd address', 'v|=(uint16_t)read_ram_buffer(f,f->ramaddr^1)<<8; wd(f,v);', 'v|=(uint16_t)read_ram_buffer(f,f->ramaddr+1)<<8; wd(f,v);'),
    ('sms address shift', 'f->ramaddr=(uint16_t)pipe(f)<<1; write_ram_buffer', 'f->ramaddr=(uint16_t)pipe(f); write_ram_buffer'),
    ('link offset', 'wr(f,11,rv(f,15)+n);', 'wr(f,11,rv(f,15)+n+1);'),
    ('ljmp pbr mask', 'f->pbr=rv(f,n)&0x7f;', 'f->pbr=rv(f,n)&0x3f;'),
    ('romb mask', 'f->rombr=sr(f)&0x7f;', 'f->rombr=sr(f)&0x3f;'),
    ('ramb mask', 'f->rambr=sr(f)&1;', 'f->rambr=0;'),
    ('dither phase', 'if ((x ^ y) & 1) c >>= 4;', 'if ((x ^ y) & 2) c >>= 4;'),
    ('160-line tile layout', '((x & 0xf8) << 1) + ((x & 0xf8) >> 1) + ((y & 0xf8) >> 3)', '((x & 0xf8) << 1) + ((y & 0xf8) >> 3)'),
    ('obj tile layout', '((y & 0x80) << 2) + ((x & 0x80) << 1)', '((y & 0x80) << 1) + ((x & 0x80) << 2)'),
    ('plane pair stride (flush)', 'uint32_t by = ((n >> 1) << 4) + (n & 1);\n    uint8_t d = 0;', 'uint32_t by = ((n >> 1) << 3) + (n & 1);\n    uint8_t d = 0;'),
    ('plane pair stride (rpix)', 'uint32_t by = ((n >> 1) << 4) + (n & 1);\n    step_clocks', 'uint32_t by = ((n >> 1) << 3) + (n & 1);\n    step_clocks'),
    ('lsr carry', 'if (op == 0x03) { flag(f,SFR_CY,sr(f)&1);', 'if (op == 0x03) {'),
    ('rol carry in', 'wd(f,(sr(f)<<1)|bit(f->sfr,2));', 'wd(f,(sr(f)<<1));'),
    ('ror carry in', 'wd(f,(bit(f->sfr,2)<<15)|(sr(f)>>1));', 'wd(f,(sr(f)>>1));'),
    ('mult flags', 'wd(f,z); set_sz(f,z); reset_prefix(f); if(!(f->cfgr&0x20))', 'wd(f,z); reset_prefix(f); if(!(f->cfgr&0x20))'),
    ('inc flags', 'wr(f,n,rv(f,n)+1); set_sz(f,rv(f,n));', 'wr(f,n,rv(f,n)+1);'),
    ('moves overflow', 'wd(f,rv(f,n)); flag(f,SFR_OV,rv(f,f->dreg)&0x80);', 'wd(f,rv(f,n));'),
    ('lob sign', 'flag(f,SFR_S,rv(f,f->dreg)&0x80); flag(f,SFR_Z,rv(f,f->dreg)==0); reset_prefix(f); return; }\n  if (op == 0x9f)', 'flag(f,SFR_Z,rv(f,f->dreg)==0); reset_prefix(f); return; }\n  if (op == 0x9f)'),
    ('stop prefix clear', 'f->sfr &= (uint16_t)~SFR_G; f->pipeline = 1; f->pipeline_pc = UINT32_MAX;\n    reset_prefix(f); return;', 'f->sfr &= (uint16_t)~SFR_G; f->pipeline = 1; f->pipeline_pc = UINT32_MAX;\n    return;'),
    ('ram load ordering', 'static uint8_t read_ram_buffer(SuperFx *f, uint16_t a) {\n  sync_ram(f);', 'static uint8_t read_ram_buffer(SuperFx *f, uint16_t a) {'),
    ('ram write wait', 'static void write_ram_buffer(SuperFx *f, uint16_t a, uint8_t v) {\n  sync_ram(f);', 'static void write_ram_buffer(SuperFx *f, uint16_t a, uint8_t v) {'),
    ('rom buffer bank', 'f->romdr = gsu_read(f, ((uint32_t)f->rombr << 16) | rv(f, 14));', 'f->romdr = gsu_read(f, rv(f, 14));'),
    ('scbr base', '((uint32_t)f->scbr << 10)', '((uint32_t)f->scbr << 9)'),
    ('cmode mask', 'else f->por=(uint8_t)sr(f)&0x1f;', 'else f->por=(uint8_t)sr(f)&0x0f;'),
    ('sfr write abort', 'if(g&&!(f->sfr&SFR_G)){f->cbr=0;flush_cache(f);}', ''),
    ('pixel bit order', 'x = (x & 7) ^ 7;\n  f->pixel[0].data[x] = c;', 'x = (x & 7);\n  f->pixel[0].data[x] = c;'),
    ('transparent colour zero', 'if ((f->por & 8) ? !(f->colr & 15) : !f->colr) return true;', 'if (!f->colr) return true;'),
    ('plot increments r1', 'plot(f, (uint8_t)rv(f, 1), (uint8_t)rv(f, 2));\n      wr(f, 1, rv(f, 1) + 1);', 'plot(f, (uint8_t)rv(f, 1), (uint8_t)rv(f, 2));'),
    ('freeze high', 'if (f->por & 8) return (f->colr & 0xf0) | (s & 15);', 'if (f->por & 8) return s;'),
    ('cache hit cost', 'step_clocks(f, f->clsr ? 1 : 2);\n    return f->cache[off];', 'step_clocks(f, f->clsr ? 2 : 2);\n    return f->cache[off];'),
    ('cache line fill cost', 'step_clocks(f, f->clsr ? 5 : 6);\n        f->cache[dp++]', 'step_clocks(f, f->clsr ? 6 : 6);\n        f->cache[dp++]'),
    ('multiplier extra clock', 'if(!(f->cfgr&0x20)) step_clocks(f,f->clsr?1:2); return; }', 'return; }'),
    ('fmult speed', '((f->cfgr&0x20)?3:7)', '((f->cfgr&0x20)?3:3)'),
    ('irq read does not clear', 'f->sfr&=~SFR_IRQ;f->irq_pending=false;return v;', 'return v;'),
    ('stop masked irq line', 'if (!(f->cfgr & 0x80)) { f->sfr |= SFR_IRQ; f->irq_pending = true; }', 'f->sfr |= SFR_IRQ; f->irq_pending = true;'),
    ('rom buffer reload on r14', 'if(f->r[14].modified){ f->r[14].modified=false; update_rom_buffer(f); }', 'f->r[14].modified=false;'),
    ('stw second byte', 'write_ram_buffer(f,f->ramaddr^1,(uint8_t)(sr(f)>>8)); reset_prefix(f); return; }\n  if (op == 0x3c)', 'reset_prefix(f); return; }\n  if (op == 0x3c)'),
    ('sbk high byte', 'if (op == 0x90) { write_ram_buffer(f,f->ramaddr,(uint8_t)sr(f)); write_ram_buffer(f,f->ramaddr^1,(uint8_t)(sr(f)>>8));', 'if (op == 0x90) { write_ram_buffer(f,f->ramaddr,(uint8_t)sr(f));'),
    ('rpix flush', 'flush_pixel(f, &f->pixel[1]); flush_pixel(f, &f->pixel[0]);\n  uint32_t a = pixel_address(f, x, y);', 'uint32_t a = pixel_address(f, x, y);'),
    ('branch keeps prefix', 'int8_t d=(int8_t)pipe(f); if(take) wr(f,15,rv(f,15)+d); return;', 'int8_t d=(int8_t)pipe(f); if(take) wr(f,15,rv(f,15)+d); reset_prefix(f); return;'),
    ('cache invalid on pbr write', 'case 0x3034:f->pbr=v&0x7f;flush_cache(f);break;', 'case 0x3034:f->pbr=v&0x7f;break;'),
    ('save state skips cache', 'sli->func(sli, &fx->r, 696);', 'sli->func(sli, &fx->r, 696); memset(fx->cache, 0, sizeof fx->cache);'),
    ('save state drops pixel cache', 'sli->func(sli, &fx->r, 696);', 'sli->func(sli, &fx->r, 696); fx->pixel[0].bitpend = 0;'),
    ('save state rom buffer', 'sli->func(sli, &fx->r, 696);', 'sli->func(sli, &fx->r, 696); fx->romcl = 0;'),
    ('save state ram buffer', 'sli->func(sli, &fx->r, 696);', 'sli->func(sli, &fx->r, 696); fx->ramcl = 0;'),
]

# Mutations the documentation cannot judge: fullsnes is silent, so a survivor here is expected.
EXPECTED_SURVIVORS = {
    'cache invalid on pbr write': 'fullsnes does not say that writing PBR empties the code cache',
}


def main():
    from retrorecomp.core import run, toolchain
    work = ROOT / '.build/snes-superfx-selftest'
    info = json.loads((work / 'project.json').read_text())
    project, exe = Path(info['project']), Path(info['exe'])
    source = project / 'engine/runner/src/snes/superfx.c'
    original = source.read_text(encoding='utf-8')
    cmake, _ = toolchain()
    only = sys.argv[1:]
    report = []
    try:
        for name, old, new in MUTATIONS:
            if only and name not in only:
                continue
            if original.count(old) != 1:
                report.append({'mutation': name, 'result': 'pattern-not-unique', 'count': original.count(old)})
                print(report[-1])
                continue
            source.write_text(original.replace(old, new), encoding='utf-8')
            try:
                run([cmake, '--build', info['build'], '--config', 'Release', '--parallel', '4'],
                    log=work / 'mutation-build.log')
                out = run([exe], cwd=work, timeout=1800).strip().splitlines()
                result = json.loads(out[-1])
                killed = result['mismatches'] > 0 or not result['passed']
                row = {'mutation': name, 'result': 'killed' if killed else 'SURVIVED',
                       'mismatches': result['mismatches']}
            except Exception as error:      # a crash or hang also notices the defect
                row = {'mutation': name, 'result': 'killed', 'detail': str(error)[:120].replace('\n', ' ')}
            report.append(row)
            print(row, flush=True)
    finally:
        source.write_text(original, encoding='utf-8')
        run([cmake, '--build', info['build'], '--config', 'Release', '--parallel', '4'], log=work / 'mutation-build.log')
    survived = [r for r in report if r['result'] == 'SURVIVED' and r['mutation'] not in EXPECTED_SURVIVORS]
    summary = {'mutations': len(report), 'killed': sum(r['result'] == 'killed' for r in report),
               'survived': [r['mutation'] for r in survived],
               'expected_survivors': {k: v for k, v in EXPECTED_SURVIVORS.items() if any(r['mutation'] == k and r['result'] == 'SURVIVED' for r in report)},
               'invalid': [r['mutation'] for r in report if r['result'] == 'pattern-not-unique']}
    (work / 'mutations.json').write_text(json.dumps({'summary': summary, 'rows': report}, indent=2) + '\n')
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
