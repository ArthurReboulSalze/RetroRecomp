"""Original raster patterns and real 65816 APU word-store ordering."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import json,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from retrorecomp.console16 import prepare16
from retrorecomp.core import run,toolchain
from tools.snes_scheduler_selftest import cartridge

def scene_cartridge(mode=5,pseudo=False,overscan=False,interlace=False,pal=False):
    """Original striped scene for independent renderer comparisons."""
    data=cartridge(bytes.fromhex('40'),pal);code=bytearray.fromhex('78 18 fb c2 30 a2 ff 1f 9a e2 20')
    def byte(reg,value):code.extend(bytes((0xa9,value,0x8d,reg&255,reg>>8)))
    def word(reg,value):
        code.extend(bytes.fromhex('c2 20'))
        code.extend(bytes((0xa9,value&255,value>>8,0x8d,reg&255,reg>>8)))
        code.extend(bytes.fromhex('e2 20'))
    byte(0x2100,0x80);byte(0x4200,0);byte(0x2105,mode)
    byte(0x2133,(8 if pseudo else 0)|(4 if overscan else 0)|(1 if interlace else 0))
    byte(0x2107,0x60);byte(0x2108,0x68);byte(0x210b,0x21)
    byte(0x212c,1);byte(0x212d,1 if mode in (5,6) else 2);byte(0x2115,0x80)
    byte(0x2121,0)
    for color in (0,31,31<<5)+tuple([0]*30)+(31<<5,):
        byte(0x2122,color&255);byte(0x2122,color>>8)
    depth=8 if mode==0 else 16
    for address,words in ((0x1000+depth,[0x55aa if mode in (5,6) else 0xff]*8+[0]*8),
                          (0x1000+depth*2,[0x55aa]*8+[0]*8),
                          (0x2000+8,[0xff]*8)):
        word(0x2116,address)
        for value in words:word(0x2118,value)
    for address in (0x6000,0x6800):
        word(0x2116,address)
        code.extend(bytes.fromhex('c2 30 a2 00 04 a9 01 00 8d 18 21 ca d0 fa e2 20'))
    byte(0x2100,15);code.extend(bytes.fromhex('cb 80 fd'))
    assert len(code)<0x1000
    data[:len(code)]=code;return data

def exercise(pal):
    work=ROOT/'.build/snes-video-selftest'/('pal' if pal else 'ntsc');work.mkdir(parents=True,exist_ok=True)
    data=cartridge(bytes.fromhex('40'),pal)
    code=bytearray.fromhex('78 18 fb c2 30 a2 ff 1f 9a')
    for base in (0x2140,0x2154,0x217c):
        code.extend(bytes((0xa9,0x34,0x12,0x8d,base&255,base>>8,
                           0xa9,0x78,0x56,0x8d,(base+2)&255,(base+2)>>8)))
    code.extend(bytes.fromhex('cb 80 fd'))
    data[:len(code)]=code;path=work/'authored.sfc';path.write_bytes(data)
    exe=prepare16(path,'snes',emit=lambda _:None);project=next(parent for parent in exe.parents if (parent/'CMakeLists.txt').is_file())
    (project/'console16_main.c').write_text((ROOT/'native/snes_video_checks.c').read_text(),encoding='utf-8')
    cmake,_=toolchain();run([cmake,'--build',project/'build','--config','Release','--parallel','4'],log=work/'build.log')
    result=json.loads(run([exe],cwd=work).strip().splitlines()[-1]);(work/'results.json').write_text(json.dumps(result,indent=2)+'\n');return result
def main():
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(exercise,(False,True)))
    print(json.dumps(results,indent=2))
if __name__=='__main__':main()
