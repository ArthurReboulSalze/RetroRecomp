"""Original CPU/bus/PPU cartridge programs and real-engine assertions.

Numeric guest results can be cross-checked with a separate accurate emulator.
No external core, firmware or commercial cartridge is needed to run these.
"""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from retrorecomp.console16 import prepare16
from retrorecomp.core import run,toolchain
from tools.snes_scheduler_selftest import cartridge

def fixture(kind,pal=False):
    if kind=='openbus':
        data=bytearray(0x10000);template=cartridge(bytes.fromhex('40'),pal)
        data[0xffc0:]=template[0x7fc0:];data[0xffd5]=0x21;data[0xffd7]=6
        data[0xffc0:0xffd5]=b'RR HIROM OPEN BUS'.ljust(21,b' ')
        for vector in (0xffea,0xffee,0xfffe):data[vector:vector+2]=bytes.fromhex('00 f0')
        data[0xf000]=0x40
        code=bytearray.fromhex('78 18 fb c2 30 a2 ff 1f 9a e2 30')
        def write(a,v):code.extend(bytes((0xa9,v,0x8d,a&255,a>>8)))
        write(0x4200,0);write(0x2100,128)
        for n,value in enumerate(b'RRBUSCOLLISION!!!'):write(0x0ff0+n,value)
        for n,bank in enumerate((0,0x30,0x80,0xb0)):
            code.extend(bytes((0xaf,2,0x60,bank,0x8d,n,0x10)))
        code.extend(bytes.fromhex('c2 20'))
        for n,bank in enumerate((0,0x30,0x80,0xb0)):
            code.extend(bytes((0xaf,2,0x60,bank,0x8d,4+n*2,0x10)))
        code.extend(bytes.fromhex('e2 20'));write(0x100e,0xc2);write(0x100f,0x99)
        code.extend(bytes.fromhex('cb 80 fd'));data[0x8000:0x8000+len(code)]=code
        return data
    code=bytearray.fromhex('78 18 fb c2 30 a2 ff 1f 9a e2 30')
    def write(a,v):code.extend(bytes((0xa9,v,0x8d,a&255,a>>8)))
    def read(a,d):code.extend(bytes((0xad,a&255,a>>8,0x8d,d&255,d>>8)))
    write(0x2100,128);write(0x4200,0)
    for n,value in enumerate(b'RRBUSCOLLISION!!!'):write(0x0ff0+n,value)
    write(0x212c,0);write(0x212d,0)
    if kind=='color':
        for index,color in ((0,0x001f),(45,0x4567)):
            write(0x2121,index);write(0x2122,color&255);write(0x2122,color>>8)
    if kind in ('object','overflow'):
        for a,v in ((0x2102,0),(0x2103,0),(0x4300,0),(0x4301,4),
                    (0x4302,0),(0x4303,0xa0),(0x4304,0),(0x4305,0x20),(0x4306,2),(0x420b,1)):
            write(a,v)
    for a,v in ((0x4207,20),(0x4208,0),(0x4209,50),(0x420a,0),(0x2100,15),(0x4200,0x30)):
        write(a,v)
    code.extend(bytes.fromhex('58 cb 80 fd'))
    rom=cartridge(bytes.fromhex('40'),pal);rom[:len(code)]=code
    rom[0x7fea:0x7fec]=rom[0x7fee:0x7ff0]=bytes.fromhex('00 f0')
    rom[0x7ffe:0x8000]=bytes.fromhex('00 f0')
    code=bytearray();read(0x4211,0x100e)
    if kind=='color':
        write(0x2121,45);write(0x2122,0xaa);write(0x2122,0xff)
        write(0x2121,45);read(0x213b,0x1000);read(0x213b,0x1001)
        write(0x4200,0);write(0x2100,128)
        write(0x2121,45);read(0x213b,0x1002);read(0x213b,0x1003)
        write(0x2121,0);read(0x213b,0x1004);read(0x213b,0x1005)
    if kind=='object':
        write(0x2102,111);write(0x2103,0);read(0x2138,0x1000);read(0x2138,0x1001)
        write(0x2102,111);write(0x2103,0);write(0x2104,0x42);write(0x2104,0x39)
        write(0x2102,14);write(0x2103,1);write(0x2104,0xd1)
        write(0x4200,0);write(0x2100,128)
        write(0x2102,111);write(0x2103,0);read(0x2138,0x1002);read(0x2138,0x1003)
        write(0x2102,24);read(0x2138,0x1004);read(0x2138,0x1005)
        write(0x2102,1);write(0x2103,1);read(0x2138,0x1006);read(0x2138,0x1007)
        write(0x2102,14);read(0x2138,0x1008)
        oam=bytearray(544)
        for n in range(128):oam[n*4+1]=200
        oam[7*4:7*4+2]=bytes((81,50));oam[12*4:12*4+2]=bytes((93,50))
        rom[0x2000:0x2220]=oam
    if kind=='overflow':
        def status(d):code.extend(bytes((0xad,0x3e,0x21,0x29,0xc0,0x8d,d&255,d>>8)))
        status(0x1000);code.extend(b'\xea'*55);status(0x1001)
        code.extend(b'\xea'*50);status(0x1002);write(0x4200,0);write(0x2100,128)
        oam=bytearray(544)
        for n in range(128):oam[n*4+1]=50 if n<33 else 200
        oam[512:]=b'\xaa'*32
        rom[0x2000:0x2220]=oam
    write(0x100f,0x99);code.extend(bytes.fromhex('cb 80 fd'))
    rom[0x7000:0x7000+len(code)]=code
    rom[0x7fc0:0x7fd5]=('RR '+kind.upper()+' COLLISION').encode().ljust(21,b' ')
    return rom

def main():
    w=ROOT/'.build/snes-bus-selftest';w.mkdir(parents=True,exist_ok=True);rows=[]
    for pal in (False,True):
        for kind in ('color','object','overflow','openbus'):
            tag=('pal-' if pal else 'ntsc-')+kind;p=w/(tag+'.sfc');p.write_bytes(fixture(kind,pal))
            exe=prepare16(p,'snes',emit=lambda _:None);project=exe.parents[2 if exe.parent.name=='Release' else 1]
            (project/'console16_main.c').write_text((ROOT/'native/snes_bus_checks.c').read_text(),encoding='utf-8')
            run([toolchain()[0],'--build',project/'build','--config','Release','--parallel','4'],log=w/(tag+'-build.log'))
            row=json.loads(run([exe],cwd=w).strip().splitlines()[-1]);row.update(kind=kind,standard='pal' if pal else 'ntsc')
            assert row['guest'][28:32]=='c299' and row['main_fallback']==0,row
            gold={'color':'aaff6745aaff','object':'5d320000423900d100','overflow':'0000c0',
                  'openbus':'003080b0000030308080b0b0'}[kind]
            assert row['guest'].startswith(gold),(tag,row,gold)
            rows.append(row)
    result=dict(cases=rows,checks=sum(r['checks'] for r in rows),passed=True)
    (w/'results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
