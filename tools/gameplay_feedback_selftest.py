"""Actual two-generation fallback feedback checks using original authored ROMs.

Generation two uses a fresh converter bank: only the standalone game's exit
file survives. Source ROMs, user games, user saves and the real bank stay intact.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from retrorecomp.platforms import build_executable, cmake_target_args
from retrorecomp import feedback


def sega(work,system):
    from retrorecomp.core import convert
    data=bytearray([0xc9]*8192);data[:3]=bytes.fromhex('c3 00 01')
    program=bytes.fromhex('f3 31 f0 df 3e 00 32 00 c0 3e 02 32 01 c0 2a 00 c0 e9')
    data[0x100:0x100+len(program)]=program
    data[0x200:0x209]=bytes.fromhex('3e a5 32 10 c0 76 c3 05 02')
    source=work/('authored.'+('sms' if system=='sms' else 'gg'));source.write_bytes(data)
    output=work/'games';emit=lambda _:None
    built=convert(source,title='Authored_'+system,output=work/'first-reports',
                  backend='functions',passes=1,frames=3,use_cover=False,online_cover=False,emit=emit)
    report=json.loads((work/'first-reports/conversion-report.json').read_text())
    assert any(r['interpreter_cycles']>0 for r in report['final_checks'])
    output.mkdir();first=output/'Renamed standalone.exe';shutil.copy2(built,first)
    os.environ['RETRO_RECOMP_FEEDBACK']='1'
    subprocess.run([first,'--headless','--frames','3'],check=True,capture_output=True,timeout=30)
    del os.environ['RETRO_RECOMP_FEEDBACK']
    identity=hashlib.sha256(data).hexdigest()
    path=first.parent/'datas/fallbacks'/f'{system}-{identity}.rrfb'
    rows,_=feedback.decode(path.read_bytes(),system,identity)
    assert rows
    os.environ['RETRO_RECOMP_LIBRARY_DIR']=str(work/'fresh-bank')
    second=convert(source,title='Authored_renamed_'+system,output=output,
                   backend='functions',passes=1,frames=3,use_cover=False,online_cover=False,emit=emit)
    final=json.loads((output/'conversion-report.json').read_text())
    assert feedback.records(system,identity)
    assert all(c['interpreter_cycles']==0 for c in final['final_checks']), final['final_checks']
    assert all(c['passed'] for c in final['strict_checks'])
    return {'system':system,'sites':len(rows),'bytes':path.stat().st_size,
            'first_fallback':True,'second_fallback':0,'fresh_bank':True,'reference_match':True}


def snes(work):
    from tools.snes_ram_selftest import ram_cartridge
    from retrorecomp.console16 import prepare16,probe16,reference_differences
    from retrorecomp.cartridge16 import read_snes_rom
    path=work/'authored.sfc';data=ram_cartridge();data[0x7fc0:0x7fc0+21]=b'RR FEEDBACK FIXTURE'.ljust(21,b' ');path.write_bytes(data)
    rom=read_snes_rom(path);first=prepare16(path,'snes',emit=lambda _:None)
    before=probe16(first,work,20,scenario='before')
    assert before['interpreted_opcodes']==6
    env=os.environ.copy();env['RETRO_RECOMP_FEEDBACK']='1'
    subprocess.run([first,'--frames','20'],env=env,check=True,capture_output=True,timeout=30)
    file=first.parent/'datas/fallbacks'/f'snes-{rom.sha256}.rrfb'
    rows,_=feedback.decode(file.read_bytes(),'snes',rom.sha256)
    os.environ['RETRO_RECOMP_LIBRARY_DIR']=str(work/'fresh-bank')
    feedback.ingest('snes',rom.sha256,first.parent)
    second=prepare16(path,'snes',emit=lambda _:None)
    native=probe16(second,work,20,scenario='after')
    reference=probe16(second,work,20,reference=True,scenario='after')
    assert native['interpreted_opcodes']==0 and not reference_differences('snes',native,reference)
    return {'system':'snes','sites':len(rows),'bytes':file.stat().st_size,'first_fallback':6,
            'second_fallback':0,'fresh_bank':True,'reference_match':True}


def md(work):
    from retrorecomp.console16 import prepare16,probe16,reference_differences
    from retrorecomp.cartridge16 import read_megadrive_rom
    data=bytearray(32768)
    for offset,value in ((0,0xffff00),(4,0x200),(0x70,0x240),(0x78,0x240)):
        data[offset:offset+4]=value.to_bytes(4,'big')
    data[0x100:0x110]=b'SEGA MEGA DRIVE '
    data[0x1f0:0x1f3]=b'USA'
    code=bytes.fromhex('33fc 7001 00ff0100 33fc 4e75 00ff0102 4eb9 00ff0100 4e72 2700')
    data[0x200:0x200+len(code)]=code;data[0x240:0x242]=bytes.fromhex('4e73')
    path=work/'authored.bin';path.write_bytes(data);rom=read_megadrive_rom(path)
    first=prepare16(path,'md',emit=lambda _:None)
    before=probe16(first,work,3,scenario='before')
    assert before['interpreted_opcodes']>0,before
    env=os.environ.copy();env['RETRO_RECOMP_FEEDBACK']='1'
    subprocess.run([first,'--frames','3'],env=env,check=True,capture_output=True,timeout=30)
    file=first.parent/'datas/fallbacks'/f'md-{rom.sha256}.rrfb'
    rows,_=feedback.decode(file.read_bytes(),'md',rom.sha256)
    os.environ['RETRO_RECOMP_LIBRARY_DIR']=str(work/'fresh-bank')
    feedback.ingest('md',rom.sha256,first.parent)
    second=prepare16(path,'md',emit=lambda _:None)
    native=probe16(second,work,3,scenario='after')
    reference=probe16(second,work,3,reference=True,scenario='after')
    assert native['interpreted_opcodes']==0 and not reference_differences('md',native,reference)
    return {'system':'md','sites':len(rows),'bytes':file.stat().st_size,'first_fallback':before['interpreted_opcodes'],
            'second_fallback':0,'fresh_bank':True,'reference_match':True}


def nes(work):
    from tools.nes_native_selftest import fixture
    from retrorecomp.nes import convert_nes,read_nes_rom
    data=bytearray(fixture(0))
    # NES deliberately retains interrupted-build RAM candidates. Give every
    # authored test invocation a distinct ROM identity, rather than mistaking
    # an earlier fixture's guarded build cache for first-generation discovery.
    tag=work.parent.name.encode('ascii');data[16+0x5000:16+0x5000+len(tag)]=tag
    code=bytes.fromhex('78 d8 a2 ff 9a a9 e6 8d 00 03 a9 10 8d 01 03 a9 60 8d 02 03 a9 00 85 10 20 00 03 4c 1b 80')
    data[16:16+len(code)]=code
    path=work/'authored.nes';path.write_bytes(data);rom=read_nes_rom(path)
    emit=lambda _:None
    built=convert_nes(path,title='Authored NES feedback',output=work/'first-reports',
                      passes=1,frames=3,use_cover=False,online_cover=False,emit=emit)
    before=json.loads((work/'first-reports/conversion-report.json').read_text())
    assert any(c['interpreter_cycles']>0 for c in before['final_checks'])
    output=work/'games';output.mkdir();first=output/'Renamed standalone.exe';shutil.copy2(built,first)
    env=os.environ.copy();env['RETRO_RECOMP_FEEDBACK']='1'
    subprocess.run([first,'--headless','--frames','3'],env=env,check=True,capture_output=True,timeout=30)
    file=output/'datas/fallbacks'/f'nes-{rom.sha256}.rrfb'
    rows,_=feedback.decode(file.read_bytes(),'nes',rom.sha256)
    os.environ['RETRO_RECOMP_LIBRARY_DIR']=str(work/'fresh-bank')
    convert_nes(path,title='Authored renamed NES feedback',output=output,
                passes=1,frames=3,use_cover=False,online_cover=False,emit=emit)
    after=json.loads((output/'conversion-report.json').read_text())
    assert all(c['interpreter_cycles']==0 for c in after['final_checks'])
    return {'system':'nes','sites':len(rows),'bytes':file.stat().st_size,'first_fallback':True,
            'second_fallback':0,'fresh_bank':True,'reference_match':True}


def gb(work):
    from retrorecomp.core import run
    from retrorecomp.gameboy import _dependencies,_known_entries,read_game_boy_rom,CPU_MATCH
    from retrorecomp.gameboy_runtime import adapt_generated_project
    from retrorecomp.resources import embed_resources
    from retrorecomp.gameboy_coverage import write_entries
    data=bytearray(32768);data[0x100:0x103]=bytes.fromhex('c3 50 01')
    code=bytes.fromhex('f3 af e0 40 31 f0 df 3e 00 ea 00 c0 3e 02 ea 01 c0 fa 00 c0 6f fa 01 c0 67 e9')
    data[0x150:0x150+len(code)]=code
    data[0x200:0x20c]=bytes.fromhex('3e a5 ea 10 c0 3e 91 e0 40 76 18 fd')
    path=work/'authored.gb';path.write_bytes(data);rom=read_game_boy_rom(path)
    engine,compiler,sdl,cmake,generator=_dependencies(lambda _:None)
    def build(folder,trace=None,force=False):
        folder.mkdir(exist_ok=True);(folder/'rom.gb').write_bytes(data)
        command=[compiler,folder/'rom.gb','-o',folder,'--runtime-dir',engine/'runtime','--output-prefix','game','--no-comments']
        if trace:command+=['--use-trace',trace]
        run(command,log=folder/'build.log')
        adapt_generated_project(folder,'feedback-'+rom.sha256[:12],rom.sha256,'Authored GB feedback')
        (folder/'game_resources.rc').write_text('1 RCDATA {0}\n')
        embed_resources(folder,{})   # the ELF counterpart of the .rc on Linux; nothing on Windows
        if force:
            # Explicit authored dispatch miss exercises real interpreter capture
            # even if the pinned compiler's static scan already found this ROM.
            target=folder/'game.c';text=target.read_text()
            marker='void gb_dispatch(GBContext* ctx, uint16_t addr) {'
            text=text.replace(marker,marker+'\n    if(addr==0x150) { gbrt_execute_dispatch_fallback(ctx,0,addr,GB_DISPATCH_FALLBACK_ADDRESS_NOT_COMPILED,0);return;}')
            target.write_text(text)
        run([cmake,'-S',folder,'-B',folder/'build','-G',generator,*cmake_target_args(),f'-DCMAKE_PREFIX_PATH={sdl.as_posix()}'],log=folder/'build.log')
        run([cmake,'--build',folder/'build','--config','Release','--target','game','--parallel','4'],log=folder/'build.log')
        return build_executable(folder / 'build', 'game')
    first=build(work/'first',force=True)
    env=os.environ.copy();env['RETRO_RECOMP_FEEDBACK']='1'
    subprocess.run([first,'--headless','--limit-frames','3'],env=env,check=True,capture_output=True,timeout=60)
    file=first.parent/'datas/fallbacks'/f'gb-{rom.sha256}.rrfb'
    rows,_=feedback.decode(file.read_bytes(),'gb',rom.sha256);assert rows
    os.environ['RETRO_RECOMP_LIBRARY_DIR']=str(work/'fresh-bank')
    feedback.ingest('gb',rom.sha256,first.parent)
    trace=work/'feedback.trace';write_entries(trace,_known_entries(rom))
    assert _known_entries(rom)
    second=build(work/'second',trace=trace)
    result=work/'after.json'
    run([second,'--headless','--limit-frames','3','--dump-state',result])
    state=json.loads(result.read_text());assert state['dispatch_fallbacks']==0
    comparison=run([second,'--differential','--differential-frames','3'],timeout=180)
    assert CPU_MATCH.search(comparison)
    return {'system':'gb','sites':len(rows),'bytes':file.stat().st_size,'forced_authored_dispatch_miss':True,
            'second_dispatch_fallbacks':0,'fresh_bank':True,'reference_match':True}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--systems',nargs='+',choices=['sms','gg','gb','nes','md','snes'],default=['sms','gg','gb','nes','md','snes'])
    args=parser.parse_args()
    root=ROOT/'.build/gameplay-feedback-selftest'/uuid.uuid4().hex;root.mkdir(parents=True)
    os.environ['RETRO_RECOMP_BUNDLED_KNOWLEDGE']='0'
    os.environ['RETRO_RECOMP_LEARNING']='0'
    results=[]
    for system in args.systems:
        work=root/system;work.mkdir()
        os.environ['RETRO_RECOMP_LIBRARY_DIR']=str(work/'first-bank')
        row={'snes':snes,'md':md,'nes':nes,'gb':gb}.get(system,lambda w:sega(w,system))(work)
        results.append(row);print(json.dumps(row),flush=True)
        (root/'results.json').write_text(json.dumps(results,indent=2))
    print(root)


if __name__=='__main__':main()
