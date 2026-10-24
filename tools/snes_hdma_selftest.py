"""Render authored HDMA splits; numeric goldens were checked under Snes9x.

No external emulator, firmware or original game is needed for this regression.
The first six rows alternate black/white; later rows stay white. Exercise the
complete CPU/HDMA/render pipeline, not only the table transfer helper.
"""
from pathlib import Path
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from retrorecomp.console16 import prepare16
from retrorecomp.core import run
from tools.snes_scheduler_selftest import cartridge


def fixture(pal=False,indirect=False,palette=False,late_mutation=False):
    code=bytearray.fromhex('78 18 fb c2 30 a2 ff 1f 9a e2 30')
    def write(address,value):
        code.extend(bytes((0xa9,value,0x8d,address&255,address>>8)))
    write(0x2100,0x80);write(0x2121,0);write(0x2122,0xff);write(0x2122,0x7f)
    write(0x212c,0);write(0x212d,0);write(0x2131,0)
    table=[]
    width=4 if palette else 1
    def payload(row):
        return [0,0,255 if row&1 else 31,127 if row&1 else 0] if palette else [15 if row&1 else 0]
    for row in range(6):
        table.extend([0x81,row*width,15] if indirect else [0x81]+payload(row))
    table.append(0)
    for offset,value in enumerate(table):write(0xe00+offset,value)
    if indirect:
        for row in range(6):
            for n,value in enumerate(payload(row)):write(0xf00+row*width+n,value)
    for address,value in ((0x4300,(0x40 if indirect else 0)|(3 if palette else 0)),(0x4301,0x21 if palette else 0),
            (0x4302,0),(0x4303,14),(0x4304,0),(0x4307,0),
            (0x420c,1),(0x4209,100),(0x420a,0),
            (0x4200,0xa0 if late_mutation else 0x80),(0x2100,15)):
        write(address,value)
    code.extend(bytes.fromhex('58 cb 80 fd'))
    data=cartridge(bytes.fromhex('40'),pal);data[:len(code)]=code
    # Larger palette setup must never overlap the interrupt vector's handler.
    data[0x7000]=0x40;data[0x7200]=0x40
    data[0x7fea:0x7fec]=bytes.fromhex('00 f0')
    data[0x7fee:0x7ff0]=bytes.fromhex('00 f2')
    if late_mutation:
        for restore,offset in ((True,0x7000),(False,0x7200)):
            code=bytearray()
            for row in range(6):
                for n,value in enumerate(payload(row) if restore else ([0,0,255,127] if palette else [15])):
                    write((0xf00+row*width if indirect else 0xe00+row*(width+1)+1)+n,value)
            if not restore:code.extend(bytes.fromhex('ad 11 42'))
            code.append(0x40);data[offset:offset+len(code)]=code
    data[0x7fc0:0x7fd5]=(b'RR HDMA COLOR PROBE' if palette else b'RR HDMA LINE PROBE').ljust(21,b' ')
    return data


def main():
    work=ROOT/'.build/snes-hdma-selftest';work.mkdir(parents=True,exist_ok=True)
    cases=[]
    for pal in (False,True):
        for indirect,palette,mutation in ((False,False,False),(True,False,False),
                (False,True,False),(True,True,False),(False,True,True),(True,True,True)):
            tag=('pal' if pal else 'ntsc')+('-indirect' if indirect else '-direct')
            if palette:tag+='-palette'
            if mutation:tag+='-late-mutation'
            path=work/(tag+'.sfc');path.write_bytes(fixture(pal,indirect,palette,mutation))
            exe=prepare16(path,'snes',emit=lambda _:None)
            image=work/(tag+'.ppm')
            run([exe,'--frames','6','--frame-image',image],log=work/(tag+'.log'))
            magic,dimensions,maximum,pixels=image.read_bytes().split(b'\n',3)
            assert (magic,dimensions,maximum)==(b'P6',b'256 224',b'255')
            assert len(pixels)==256*224*3
            for row in range(224):
                expected=0 if row<6 and not row&1 else 255
                color=bytes((255,expected,expected)) if palette else bytes([expected])*3
                assert pixels[row*768:(row+1)*768]==color*256,(tag,row)
            cases.append(dict(standard='pal' if pal else 'ntsc',indirect=indirect,
                              palette=palette,late_mutation=mutation,pixels=256*224,passed=True))
    result=dict(cases=cases,pixels=sum(c['pixels'] for c in cases),passed=True)
    (work/'results.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))


if __name__=='__main__':
    main()
