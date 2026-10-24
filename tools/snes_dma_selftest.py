"""Original ROM-free checks of the real DMA unit and PPU port timing."""
from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from retrorecomp.console16 import prepare16
from retrorecomp.core import run,toolchain
from tools.snes_scheduler_selftest import cartridge
def main():
    work=ROOT/'.build/snes-dma-selftest';work.mkdir(parents=True,exist_ok=True)
    cases=[]
    for pal in (False,True):
        standard='pal' if pal else 'ntsc';path=work/(standard+'.sfc');data=cartridge(bytes.fromhex('40'),pal)
        data[0x7fc0:0x7fd5]=b'RR DMA PPU CHECKS'.ljust(21,b' ');path.write_bytes(data)
        exe=prepare16(path,'snes',emit=lambda _:None);project=exe.parents[2]
        (project/'console16_main.c').write_text((ROOT/'native/snes_dma_checks.c').read_text(),encoding='utf-8')
        cmake,_=toolchain();run([cmake,'--build',project/'build','--config','Release','--parallel','4'],log=work/(standard+'-build.log'))
        cases.append(json.loads(run([exe],cwd=work).strip().splitlines()[-1])|{'standard':standard})
    result={'cases':cases,'checks':sum(c['checks'] for c in cases),'passed':all(c['passed'] for c in cases)}
    (work/'results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
