"""Compile original PPU collision/latch fixtures against the real engine."""
from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from retrorecomp.console16 import prepare16
from retrorecomp.core import run,toolchain
from tools.snes_scheduler_selftest import cartridge
def main():
    w=ROOT/'.build/snes-ppu-bus-selftest';w.mkdir(parents=True,exist_ok=True);cases=[]
    for pal in (False,True):
        tag='pal' if pal else 'ntsc';p=w/(tag+'.sfc');rom=cartridge(bytes.fromhex('40'),pal)
        rom[0x7fc0:0x7fd5]=b'RR PPU BUS CHECKS'.ljust(21,b' ');p.write_bytes(rom)
        exe=prepare16(p,'snes',emit=lambda _:None);project=next(parent for parent in exe.parents if (parent/'CMakeLists.txt').is_file())
        (project/'console16_main.c').write_text((ROOT/'native/snes_ppu_bus_checks.c').read_text(),encoding='utf-8')
        run([toolchain()[0],'--build',project/'build','--config','Release','--parallel','4'],log=w/(tag+'-build.log'))
        cases.append(json.loads(run([exe],cwd=w).strip().splitlines()[-1])|dict(standard=tag))
    result=dict(cases=cases,checks=sum(c['checks'] for c in cases),passed=all(c['passed'] for c in cases))
    (w/'results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
