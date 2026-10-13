"""Authored rectangular OBJ scenes; full-image goldens checked with Snes9x.

No original game, artwork, firmware or external emulator is required here.
"""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.snes_scheduler_selftest import cartridge
from smsrecomp.console16 import prepare16
from smsrecomp.core import run

def fixture(mode=6,pal=False):
    data=cartridge(bytes.fromhex('40'),pal)
    code=bytearray.fromhex('78 18 fb c2 30 a2 ff 1f 9a e2 20')
    def byte(a,v):code.extend(bytes((0xa9,v,0x8d,a&255,a>>8)))
    def word(a,v):
        code.extend(bytes.fromhex('c2 20'))
        code.extend(bytes((0xa9,v&255,v>>8,0x8d,a&255,a>>8)))
        code.extend(bytes.fromhex('e2 20'))
    byte(0x2100,128);byte(0x4200,0);byte(0x2101,mode<<5)
    byte(0x212c,16);byte(0x212d,0);byte(0x2131,0);byte(0x2133,0)
    byte(0x2121,0);byte(0x2122,0);byte(0x2122,0)
    byte(0x2121,129)
    for color in (31,31<<5):byte(0x2122,color&255);byte(0x2122,color>>8)
    byte(0x2115,128)
    for ty in range(8):
        for tx in range(4):
            word(0x2116,(ty*16+tx)*16)
            for _ in range(8):word(0x2118,0xff00 if ty&1 else 0xff)
            for _ in range(8):word(0x2118,0)
    objects=[];high=[0]*32
    for n in range(128):
        if n<8:
            x=(32,80,128,192)[n%4];y=24 if n<4 else 112
            big=n%2;flip=(n%4)>=2
            objects.extend((x,y,0,(128 if flip else 0)|(64 if n>=4 else 0)))
            high[n//4]|=big<<((n%4)*2+1)
        else:
            objects.extend((44,240,0,0));high[n//4]|=1<<((n%4)*2)
    byte(0x2102,0);byte(0x2103,0)
    for v in objects+high:byte(0x2104,v)
    byte(0x2100,15);byte(0x4200,128);code.extend(bytes.fromhex('58 cb 80 fd'))
    assert len(code)<0x7000
    data[:len(code)]=code;data[0x7000]=0x40;data[0x7fea:0x7fec]=bytes.fromhex('00 f0')
    data[0x7fc0:0x7fd5]=f'RR RECT OBJ {mode}'.encode().ljust(21,b' ')
    return data

def exercise(case):
    mode,pal=case;w=ROOT/'.build/snes-object-selftest';w.mkdir(parents=True,exist_ok=True)
    tag=f'{"pal" if pal else "ntsc"}-{mode}';path=w/(tag+'.sfc');path.write_bytes(fixture(mode,pal))
    exe=prepare16(path,'snes',emit=lambda _:None);image=w/(tag+'.ppm')
    run([exe,'--frames','6','--frame-image',image],log=w/(tag+'.log'))
    magic,shape,maximum,pixels=image.read_bytes().split(b'\n',3)
    assert (magic,shape,maximum)==(b'P6',b'256 224',b'255')
    expected=bytearray(256*224*3)
    for n in range(8):
        x=(32,80,128,192)[n%4];top=24 if n<4 else 112
        width=32 if n%2 else 16;height=64 if mode==6 and n%2 else 32
        for y in range(height):
            row=(y//width)*width+width-1-y%width if n%4>=2 else y
            color=bytes((0,255,0)) if (row//8)&1 else bytes((255,0,0))
            start=((top+y)*256+x)*3;expected[start:start+width*3]=color*width
    assert pixels==expected,tag
    return dict(mode=mode,standard='pal' if pal else 'ntsc',pixels=256*224,passed=True)

def main():
    with ThreadPoolExecutor(max_workers=4) as pool:cases=list(pool.map(exercise,[(m,p) for m in (6,7) for p in (False,True)]))
    result=dict(cases=cases,pixels=sum(c['pixels'] for c in cases),passed=True)
    (ROOT/'.build/snes-object-selftest/results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
if __name__=='__main__':main()
