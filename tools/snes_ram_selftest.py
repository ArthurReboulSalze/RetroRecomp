"""Original ROMs execute mutable SRAM code and retain guest-written progress."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import json,os,subprocess,sys,uuid
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from smsrecomp.console16 import prepare16,probe16,reference_differences
from smsrecomp.cartridge16 import read_snes_rom
from smsrecomp import supernintendo
from tools.snes_scheduler_selftest import cartridge
from tools.console16_state_selftest import check
WORK=None

def ram_cartridge(mapping='lorom',pal=False,battery=True):
    data=cartridge(bytes.fromhex('40'),pal)
    if mapping=='hirom':
        data.extend(bytes(0x10000-len(data)))
        data[0x8000:0x10000]=data[:0x8000]
        data[0x7fc0:0x8000]=bytes(64)
    base=0xf00000 if mapping=='lorom' else 0xa06000
    code=bytearray.fromhex('78 18 fb c2 30 a2 ff 1f 9a a9 00 00 5b 9c 10 00 9c 12 00')
    def long(op,adr):code.extend(bytes((op,adr&255,(adr>>8)&255,adr>>16)))
    def store(adr,value):code.extend(bytes((0xa9,value&255,value>>8)));long(0x8f,adr)
    for value in (0x10e6,0x10c6,0x12e6):
        store(base,value);store(base+2,0xea6b);long(0x22,base)
    # Increment a guest counter in battery RAM once at boot; don't reset it.
    long(0xaf,base+0x100);code.append(0x1a);long(0x8f,base+0x100)
    code.extend(bytes.fromhex('e2 20 a9 80 8d 00 21 cb 80 fd'))
    offset=0 if mapping=='lorom' else 0x8000
    data[offset:offset+len(code)]=code
    data[offset+0x300:offset+0x30c]=bytes.fromhex('e6 10 6b ea c6 10 6b ea e6 12 6b ea')
    data[offset+0x30c:offset+0x310]=bytes.fromhex('6b ea 00 00')
    header=0x7fc0 if mapping=='lorom' else 0xffc0
    data[header:header+21]=(b'RR SRAM '+mapping.encode()+ (b' PAL' if pal else b' NTSC')+ (b' B' if battery else b' V')).ljust(21,b' ')
    data[header+21]=0x20 if mapping=='lorom' else 0x21
    data[header+22]=2 if battery else 1;data[header+24]=3
    return data

def exercise(case):
    mapping,pal=case
    work=WORK/(mapping+('-pal' if pal else '-ntsc'))
    work.mkdir(parents=True,exist_ok=True)
    path=work/'authored.sfc';path.write_bytes(ram_cartridge(mapping,pal));rom=read_snes_rom(path)
    exe=prepare16(path,'snes',emit=lambda _:None)
    native=probe16(exe,work,20,scenario='discovery')
    reference=probe16(exe,work,20,reference=True,scenario='discovery')
    assert not reference_differences('snes',native,reference)
    assert native['interpreted_opcodes']==6, native['interpreted_opcodes']  # INC/DEC and each RTL.
    added=supernintendo.learn_ram_variants(rom,[native]);assert added==4,added
    # Retain one literal per PC/opcode, rather than every operand value.
    # The last INC now changes its operand without an exact four-byte hint.
    journal=supernintendo.memory_file(rom);record=json.loads(journal.read_text())
    seen=set();retained=[]
    for item in record['ram_variants']:
        key=(item['address'],item['bytes'][:2])
        if key not in seen:retained.append(item);seen.add(key)
    assert len(retained)==3
    record['ram_variants']=retained;journal.write_text(json.dumps(record))
    exe=prepare16(path,'snes',emit=lambda _:None)
    native=probe16(exe,work,20,scenario='qualified')
    reference=probe16(exe,work,20,reference=True,scenario='qualified')
    assert not reference_differences('snes',native,reference)
    assert native['interpreted_opcodes']==0
    battery=work/'persistent'/'counter.rrsram'
    def boot(name):
        report=work/(name+'.json')
        p=subprocess.run([str(exe),'--frames','20','--cartridge-save',str(battery),
                          '--report',str(report)],capture_output=True,text=True,timeout=60)
        assert p.returncode==0,p.stderr
        return json.loads(report.read_text())
    # Each invocation has a new process/CPU; carry only the cartridge save.
    if battery.exists():raise RuntimeError('Use a clean fixture output directory for persistence checks.')
    first=boot('first');raw=battery.read_bytes();assert raw[112+0x100:112+0x102]==bytes((1,0))
    second=boot('second');raw=battery.read_bytes();assert raw[112+0x100:112+0x102]==bytes((2,0))
    assert first['sram_hash']!=second['sram_hash']
    state=check(exe,work/'state',13,11)
    result={'mapping':mapping,'pal':pal,'rom_sha256':rom.sha256,'initial_fallback':6,
            'learned_variants':added,'retained_pc_opcodes':len(retained),'live_operand_mutation_native':True,'final_fallback':0,'persistent_counter':2,
            'state':state,'passed':True}
    (work/'result.json').write_text(json.dumps(result,indent=2)+'\n');return result

def main():
    global WORK
    WORK=ROOT/'.build/snes-ram-selftest'/uuid.uuid4().hex
    os.environ['RETRO_RECOMP_LIBRARY_DIR']=str(WORK/'knowledge')
    with ThreadPoolExecutor(max_workers=2) as pool:
        rows=list(pool.map(exercise,((m,p) for m in ('lorom','hirom') for p in (False,True))))
    (ROOT/'.build/snes-ram-selftest/results.json').write_text(json.dumps(rows,indent=2)+'\n')
    print(json.dumps(rows,indent=2))

if __name__=='__main__':main()
