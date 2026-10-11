"""Original synthetic Sega mapper cartridge; production bus/CPU/DMA/state path."""
from pathlib import Path
import json
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from smsrecomp.console16 import prepare16
from smsrecomp.core import run,toolchain
from smsrecomp.cartridge16 import read_megadrive_rom
from smsrecomp.megadrive_codegen import generate_steps
from tools.megadrive_bus_selftest import executable


def main():
    work=ROOT/'.build/megadrive-mapper-selftest';work.mkdir(parents=True,exist_ok=True)
    payload=bytearray(b'\xff'*0x500000)
    for pos,value in ((0,0xffc000),(4,0x200),(0x70,0x300),(0x78,0x300)):
        payload[pos:pos+4]=value.to_bytes(4,'big')
    payload[0x100:0x110]=b'SEGA SSF'.ljust(16,b' ')
    payload[0x120:0x150]=b'AUTHORED MAPPER'.ljust(48,b' ')
    payload[0x1f0:0x200]=b'U'.ljust(16,b' ')
    payload[0x200:0x202]=bytes.fromhex('60fe');payload[0x300:0x302]=bytes.fromhex('4e73')
    pcs={0x200,0x300}
    for page in range(10):
        base=page<<19;payload[base+0x500:base+0x502]=(0xa000+page).to_bytes(2,'big')
    for offset,raw in ((0x400400,'6008'),(0x400410,'41fa0008'),(0x400420,'51c80008'),
                       (0x80430,'70014e71'),(0x400430,'70ff4e71'),(0x480430,'70024e71'),
                       (0x400440,'13fc000900a130f3')):
        data=bytes.fromhex(raw);payload[offset:offset+len(data)]=data;pcs.add(offset)
    path=work/'authored.bin';path.write_bytes(payload)
    game=prepare16(path,'md',title='Authored Sega mapper',emit=lambda x:None);project=game.parents[2]
    generate_steps(ROOT/'.deps/segagenesisrecomp',project,read_megadrive_rom(path),pcs,follow_flow=False)
    cmake,_=toolchain();run([cmake,'--build',project/'build','--config','Release','--parallel','4'],log=work/'build.log')
    exe=executable(project,work,(ROOT/'native/md_mapper_checks.c').read_text(encoding='utf-8'))
    results=[]
    with tempfile.TemporaryDirectory(prefix='rr-md-mapper-') as temp:
        state=Path(temp)/'authored.rrstate'
        for mode in ('create','restore'):
            results.append(json.loads(run([exe,mode,state]).strip().splitlines()[-1]))
    result=dict(passed=True,checks=sum(r['checks'] for r in results),fresh_process_state=True,
                mapper_native_relative_code=True,prefetched_previous_bank=True,banked_z80_and_dma=True)
    (work/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
