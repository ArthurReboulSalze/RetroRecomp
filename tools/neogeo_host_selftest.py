"""Exercise the real common SDL menus using keys and two virtual controllers.

Hidden test windows; output is local and opt-in. Does not measure physical IO.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from smsrecomp import __version__


def launch(exe,output,name,events,folder=None,*args):
    folder=folder or output/name;folder.mkdir(parents=True,exist_ok=True)
    copy=folder/exe.name
    if not copy.exists():shutil.copyfile(exe,copy)
    script=output/(name+'.events');log=output/(name+'.jsonl')
    script.write_text('\n'.join(events)+'\n',encoding='utf-8')
    env={**os.environ,'RETRORECOMP_HOST_TEST_FRAMES':'300',
         'RETRORECOMP_NG_UI_SCRIPT':str(script),'RETRORECOMP_NG_UI_LOG':str(log),
         'SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS':'1','SDL_AUDIODRIVER':'dummy',
         'SDL_GAMECONTROLLER_IGNORE_DEVICES_EXCEPT':'0x0000/0x0000'}
    result=subprocess.run([str(copy),*map(str,args)],capture_output=True,env=env,timeout=45)
    if result.returncode:raise RuntimeError(f'{name}: exit {result.returncode}: {result.stderr[-2000:]!r}')
    records=[json.loads(row) for row in log.read_text(encoding='utf-8').splitlines()]
    return {row['label']:row for row in records},folder


def check(exe,output):
    output.mkdir(parents=True,exist_ok=True)
    # Opening/closing/help/remap inspection/missing F9 must have no sidecars.
    empty,folder=launch(exe,output,'no-files',[
        '0 snap defaults','1 key H','2 snap help',f'2 capture {output}/help.bmp',
        '3 key H','4 key F2','5 snap controls','6 key Escape',
        '7 key F9','8 snap absent','9 quit'])
    assert empty['defaults']['key_labels']==['W','X','C','V'],empty['defaults']
    assert empty['help']['menu']==1 and empty['controls']['menu']==2
    assert 'v'+__version__ in empty['help']['version']
    assert empty['absent']['status']=='No compatible quick state to load'
    assert list(folder.iterdir())==[folder/exe.name]
    settings,folder=launch(exe,output,'settings',[
        '0 key F3','1 snap scale2x','2 key F3','3 snap scanlines','4 key F3','5 snap xbr',
        '6 key F3','7 snap sharp','8 key F3','9 key F3',
        '10 key F4','11 snap integer','12 key F4','13 snap fitted',
        '14 key F7','15 key F6','16 snap preferences','17 key P','18 snap paused',
        '19 key P','20 key F2','21 key Return','22 key J','23 snap p1-remap',
        '24 key Right','25 key Return','26 key K','27 snap p2-remap','28 key Escape','29 quit'])
    assert [settings[k]['filter'] for k in ('scale2x','scanlines','xbr','sharp')]==[2,3,1,0]
    assert settings['integer']['display_mode']==1 and settings['integer']['fullscreen']
    assert settings['fitted']['display_mode']==2 and settings['fitted']['fullscreen']
    assert settings['preferences']['french']==settings['preferences']['autofire']==1
    assert settings['paused']['menu']==3
    assert settings['p1-remap']['keyboard'][0][0]==13 and settings['p2-remap']['keyboard'][1][0]==14
    reopened,_=launch(exe,output,'reopened',['0 snap reopened','1 quit'],folder)
    actual=reopened['reopened']
    assert actual['filter']==3 and actual['display_mode']==2 and actual['fullscreen']
    assert actual['french']==actual['autofire']==1 and actual['keyboard']==settings['p2-remap']['keyboard']
    windowed,_=launch(exe,output,'windowed',['0 key F4','1 snap windowed','2 quit'],folder)
    assert windowed['windowed']['display_mode']==0 and not windowed['windowed']['fullscreen']
    restored,_=launch(exe,output,'windowed-reopened',['0 snap restored','1 quit'],folder)
    assert restored['restored']['display_mode']==0 and not restored['restored']['fullscreen']
    pads,folder=launch(exe,output,'controllers',[
        '0 attach 0','0 attach 1','2 snap attached',
        '3 button 0 a 1','3 button 0 b 1','3 button 0 x 1','3 button 0 y 1',
        '3 button 0 start 1','3 button 0 back 1','3 button 1 start 1','3 button 1 back 1',
        '4 snap all-buttons','5 axis 1 leftx 24000','6 snap analog-right',
        '7 button 1 dpleft 1','8 snap opposing','9 axis 1 leftx 0','9 button 1 dpleft 0',
        '9 button 0 a 0','9 button 0 b 0','9 button 0 x 0','9 button 0 y 0',
        '9 button 0 start 0','9 button 0 back 0','9 button 1 start 0','9 button 1 back 0',
        '10 key F2','11 key Tab','12 key Return','13 button 1 b 1','14 snap wrong-controller',
        '15 button 0 leftstick 1','16 snap assigned',f'16 capture {output}/controls.bmp',
        '17 button 0 leftstick 0','17 button 1 b 0','18 key Escape','19 key F6','20 button 0 leftstick 1',
        *[f'{n} snap autofire-{n}' for n in range(21,34)],
        '34 button 0 leftstick 0','35 button 0 leftstick 1','36 snap pad-pause',
        '37 button 0 leftstick 0','38 button 0 leftstick 1','39 snap pad-resume',
        '40 button 0 leftstick 0','41 button 0 rightstick 1','42 snap pad-reset',
        '43 button 0 rightstick 0','44 detach 0','45 detach 1','47 snap removed','48 quit'])
    assert pads['attached']['controllers']==[True,True]
    assert pads['all-buttons']['pads']==[1008,768],pads['all-buttons']
    assert pads['analog-right']['pads'][1]==776 and pads['opposing']['pads'][1]==768
    assert pads['wrong-controller']['capturing']==1
    assert pads['assigned']['capturing']==0 and pads['assigned']['gamepad'][0][0]==7
    pulses=[bool(pads[f'autofire-{n}']['pads'][0]&16) for n in range(21,34)]
    assert True in pulses and False in pulses
    assert all(a != b for a,b in zip(pulses,pulses[1:])), pulses
    assert pads['pad-pause']['menu']==pads['pad-resume']['menu']==0
    assert pads['pad-reset']['menu']==0 and pads['pad-reset']['frame']>pads['pad-resume']['frame']
    assert pads['removed']['controllers']==[False,False]
    padreopened,_=launch(exe,output,'pads-reopened',['0 snap persisted','1 quit'],folder)
    assert padreopened['persisted']['gamepad'][0][0]==7
    # F8/F9 reach the real shared event loop and disk path, then a fresh process.
    saved,folder=launch(exe,output,'quickstate',[
        '3 key F8','4 snap saved','14 snap before-load','15 key F9','16 snap loaded','17 quit'])
    assert saved['saved']['status']=='Quick state saved' and saved['loaded']['status']=='Quick state loaded'
    states=list((folder/'datas/states').glob('*.rrstate'));assert len(states)==1
    assert not (folder/'datas/Retro-Recomp.ini').exists()
    quick,_=launch(exe,output,'quickstate-reopened',['0 key F9','1 snap loaded','2 quit'],folder)
    assert quick['loaded']['status']=='Quick state loaded'
    assert quick['loaded']['frame']==saved['saved']['frame']
    assert not list(folder.rglob('*.tmp'))
    # Enhanced mode is a direct F5 switch, remembered without opening a menu.
    enhanced,folder=launch(exe,output,'enhanced',[
        '0 snap default','0 key F5','1 snap standard','1 key F5','2 snap enabled','3 key H','4 snap enhanced-help',
        f'4 capture {output}/enhanced-help.bmp','5 key H','6 key F1','7 snap restart',
        '8 key F8','9 snap saved','10 quit'])
    assert enhanced['default']['enhanced_mode']
    assert not enhanced['standard']['enhanced_mode']
    assert enhanced['enabled']['enhanced_mode'] and enhanced['enabled']['menu']==0
    assert enhanced['enabled']['status']=='Enhanced Neo Geo: ON'
    assert enhanced['enhanced-help']['menu']==1 and enhanced['restart']['enhanced_mode']
    assert enhanced['saved']['status']=='Quick state saved'
    fresh,_=launch(exe,output,'enhanced-reopened',[
        '0 snap remembered','1 key F5','2 snap standard','3 key F9','4 snap restored',
        '5 key F5','6 snap disabled','7 quit'],folder)
    assert fresh['remembered']['enhanced_mode']
    assert not fresh['standard']['enhanced_mode']
    assert fresh['restored']['enhanced_mode'] and fresh['restored']['status']=='Quick state loaded'
    assert not fresh['disabled']['enhanced_mode'] and fresh['disabled']['menu']==0
    disabled,_=launch(exe,output,'enhanced-disabled-reopened',['0 snap disabled','1 quit'],folder)
    assert not disabled['disabled']['enhanced_mode']
    mode_restart = check_mode_restart(exe, output) if empty['defaults'].get('aes_available') else None
    result={'source_exe':str(exe),'source_exe_sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),
            'menus_and_shortcuts':True,'two_virtual_controllers':True,'bindings_persisted':True,
            'azerty_labels':empty['defaults']['key_labels'],'filter_order':[2,3,1,0],
            'fullscreen_and_filters_fresh_process':True,'f8_f9_fresh_process':True,
            'opening_and_missing_f9_create_nothing':True,'state_bytes':states[0].stat().st_size,
            'enhanced_f5_persisted_and_state_restored':True,
            'f11_restart':mode_restart,
            'physical_controller_and_audio_validation':False}
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n');return result


def check_mode_restart(exe, output):
    """Drive the real F11 close/relaunch twice, with isolated user data."""
    folder=output/'mode-restart';folder.mkdir(exist_ok=True)
    copy=folder/exe.name;shutil.copyfile(exe,copy)
    first=folder/'mvs.events';second=folder/'aes.events';last=folder/'return.events'
    first_log=folder/'mvs.jsonl';second_log=folder/'aes.jsonl';last_log=folder/'return.jsonl'
    last.write_text('0 snap returned\n0 key F9\n1 snap restored\n2 quit\n',encoding='utf-8')
    second.write_text(f'0 snap aes\n0 key F9\n1 snap absent\n2 key F8\n3 snap saved\n'
        f'4 restart-script {last}\n4 restart-log {last_log}\n5 key F11\n',encoding='utf-8')
    first.write_text(f'0 snap mvs\n0 key F8\n1 snap saved\n2 restart-script {second}\n'
        f'2 restart-log {second_log}\n3 key F11\n',encoding='utf-8')
    env={**os.environ,'RETRORECOMP_HOST_TEST_FRAMES':'300','SDL_AUDIODRIVER':'dummy',
         'RETRORECOMP_NG_UI_SCRIPT':str(first),'RETRORECOMP_NG_UI_LOG':str(first_log)}
    subprocess.run([str(copy),'--mvs'],check=True,env=env,capture_output=True,timeout=45)
    deadline=time.monotonic()+45
    while time.monotonic()<deadline:
        if last_log.exists() and 'restored' in last_log.read_text(encoding='utf-8'):
            break
        time.sleep(.1)
    def records(path):return {r['label']:r for r in (json.loads(line) for line in path.read_text().splitlines())}
    a,b,c=records(first_log),records(second_log),records(last_log)
    assert a['mvs']['machine_mode']=='mvs' and b['aes']['machine_mode']=='aes' and c['returned']['machine_mode']=='mvs'
    assert b['aes']['frame']==a['mvs']['frame']==c['returned']['frame']==0
    assert b['absent']['status']!='Quick state loaded'
    assert b['saved']['status']==c['restored']['status'].replace('loaded','saved')=='Quick state saved'
    states=list(folder.glob('datas/states/*.rrstate'));assert len(states)==2
    return {'mvs_aes_mvs':True,'reset_each_time':True,'separate_quick_states':True,'last_mode_remembered':True}


def main():
    p=argparse.ArgumentParser();p.add_argument('exe',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();print(json.dumps(check(a.exe.resolve(),a.output.resolve())))
if __name__=='__main__':main()
