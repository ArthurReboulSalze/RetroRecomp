"""Original ordinary-cartridge decoding, RAM guard and battery-file checks."""
from pathlib import Path
import json, sys, uuid
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from retrorecomp.console16 import prepare16
from retrorecomp.core import run,toolchain
from tools.snes_scheduler_selftest import cartridge

def main():
    work=ROOT/'.build/snes-cart-selftest';work.mkdir(parents=True,exist_ok=True)
    path=work/'authored.sfc';data=cartridge(bytes.fromhex('40'),False)
    data[0x7fc0:0x7fd5]=b'RR CARTRIDGE CHECKS'.ljust(21,b' ');path.write_bytes(data)
    exe=prepare16(path,'snes',emit=lambda _:None);project=exe.parents[2]
    (project/'console16_main.c').write_text((ROOT/'native/snes_cart_checks.c').read_text(),encoding='utf-8')
    cmake,_=toolchain();run([cmake,'--build',project/'build','--config','Release','--parallel','4'],log=work/'build.log')
    files=work/'files'/uuid.uuid4().hex;files.mkdir(parents=True)
    result=json.loads(run([exe,files],cwd=work).strip().splitlines()[-1])
    observations=json.loads((files/'observations.json').read_text())
    assert len(observations['ram_variants'])==16384
    assert observations['ram_observation_overflows']==2
    assert len({(v['address'],v['bytes']) for v in observations['ram_variants']})==16384
    result.update(observations_retained=16384,overflow_events=2,duplicate_slots=0)
    (work/'results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
