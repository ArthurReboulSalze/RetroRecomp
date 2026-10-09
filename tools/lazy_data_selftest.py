"""Prove side-effect-free game startup and demand-driven config/state storage."""
import configparser
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from smsrecomp.core import ROOT, ASSETS, dependencies, read_rom, default_config, prepare_runtime, run

def files(directory):
    return {p.relative_to(directory).as_posix(): p.read_bytes() for p in directory.rglob('*') if p.is_file()}

def main():
    directory = ROOT / '.build/lazy-data-selftest'; directory.mkdir(parents=True, exist_ok=True)
    data = bytes(8192); rom_path = directory / 'authored.sms'; rom_path.write_bytes(data)
    rom = read_rom(rom_path)
    (directory / 'rom.sms').write_bytes(data)
    (directory / 'game.toml').write_text(default_config(rom), encoding='utf-8')
    (directory / 'dispatch_manifest.txt').write_text('', encoding='utf-8')
    engine, sdl, cmake, generator = dependencies()
    prepare_runtime(directory, rom, 'Authored lazy data fixture', engine)
    log = directory / 'build.log'
    run([ROOT / '.deps/recompiler-build/Release/SmsRecomp.exe', '--game', directory / 'game.toml', '--banked-step'], log=log)
    # Keep the fixture's staged source separate from an active batch build.
    source = directory / 'native-source'; source.mkdir(parents=True, exist_ok=True)
    for file in (ASSETS / 'native').iterdir():
        if file.is_file(): shutil.copy2(file, source / file.name)
    build = directory / 'build-isolated'
    run([cmake, '-S', source, '-B', build, '-G', generator, '-A', 'x64',
         f'-DENGINE_DIR={engine.as_posix()}', f'-DGAME_DIR={directory.as_posix()}',
         '-DGAME_NAME=AuthoredLazy', f'-DCMAKE_PREFIX_PATH={sdl.as_posix()}',
         '-DSMSRECOMP_BANKED_AOT=ON', '-DSMSRECOMP_LAZY_DATA_CHECKS=ON'], log=log)
    run([cmake, '--build', build, '--config', 'Release', '--target', 'AuthoredLazy',
         'smsrecomp_lazy_data_checks', '--parallel', '4'], log=log)
    env = os.environ.copy()
    for key in ('RETRO_RECOMP_LEARNING','SMSRECOMP_LIBRARY_DIR','RETRO_RECOMP_LIBRARY_DIR','SMSRECOMP_STRICT'):
        env.pop(key,None)
    outputs=[]
    with tempfile.TemporaryDirectory(prefix='jeux partagés-', dir=directory) as temporary:
        work=Path(temporary); elsewhere=work/'ailleurs';elsewhere.mkdir()
        def launch(exe,args,environment=None):
            p=subprocess.run([str(exe),*args],cwd=elsewhere,env=environment or env,
                capture_output=True,text=True,timeout=30,creationflags=subprocess.CREATE_NO_WINDOW)
            outputs.append(p.stdout+p.stderr)
            (directory/'checks.log').write_text('\n'.join(outputs),encoding='utf-8')
            assert p.returncode==0,outputs[-1]
        results={}
        for mode in ('read','legacy','legacy_edit','existing','config','save','learn'):
            root=work/mode;root.mkdir();exe=root/'renamed.exe'
            shutil.copy2(build/'Release/smsrecomp_lazy_data_checks.exe',exe)
            if mode in ('legacy','legacy_edit'):
                (root/'SMSRecomp.ini').write_text('[Clavier]\nbouton1=C\n[Video]\nfiltre=3\nmasquer_bord_gauche=0\n[ClavierJ2]\nhaut=I\nbas=K\ngauche=J\ndroite=L\nbouton1=N\nbouton2=M\nselect=Keypad 4\n',encoding='ascii')
            if mode=='existing':
                (root/'datas').mkdir();(root/'datas/Retro-Recomp.ini').write_text('[Clavier]\nbouton1=C\n[Video]\nfiltre=3\nmasquer_bord_gauche=0\n[ClavierJ2]\nselect=Keypad 4\n',encoding='ascii')
            before=files(root);test_env=env.copy()
            if mode=='learn':test_env['RETRO_RECOMP_LEARNING']='1'
            launch(exe,[mode],test_env);after=files(root)
            if mode in ('read','legacy','existing'):assert after==before,(mode,list(after))
            elif mode in ('config','legacy_edit'):
                assert set(after)-set(before)=={'datas/Retro-Recomp.ini'}
                if mode=='legacy_edit':
                    assert after['SMSRecomp.ini']==before['SMSRecomp.ini']
                    config=configparser.ConfigParser();config.read_string(after['datas/Retro-Recomp.ini'].decode('ascii'))
                    assert config['ClavierJ2']['bouton2']=='M' and config['Video']['masquer_bord_gauche']=='0'
            elif mode=='save':
                created=set(after)-set(before);assert len(created)==1 and next(iter(created)).endswith('-quicksave.state'),created
            else:
                created=set(after)-set(before)
                assert {Path(p).name for p in created}=={'entry.lock','observations.log','native.patterns'},created
                assert all(p.startswith('datas/library/') for p in created)
            results[mode]=sorted(set(after)-set(before))
        # The converter's per-scenario library can exceed MAX_PATH for long
        # game titles. Check the real C writer, not just Python file access.
        root=work/'long-learning';root.mkdir();exe=root/'renamed.exe'
        shutil.copy2(build/'Release/smsrecomp_lazy_data_checks.exe',exe)
        library=root/('mémoire-'+('a'*90))/('sondes-'+('b'*90))
        assert len(str(library)) > 260
        probe_env=env.copy();probe_env['RETRO_RECOMP_LEARNING']='1'
        probe_env['RETRO_RECOMP_LIBRARY_DIR']=str(library)
        launch(exe,['learn'],probe_env)
        created=files(library)
        assert {Path(p).name for p in created}=={'entry.lock','observations.log','native.patterns'},created
        results['long_unicode_learning']={'root_characters':len(str(library)),
                                         'files':sorted(created)}
        # Exercise the real shipped launcher, normal headless boot and explicit --log.
        root=work/'standalone';root.mkdir();exe=root/'game.exe';shutil.copy2(build/'Release/AuthoredLazy.exe',exe)
        before=files(root);launch(exe,['--headless','--frames','2','--mute']);assert files(root)==before
        diagnostic=root/'requested.log';launch(exe,['--headless','--frames','2','--mute','--log',str(diagnostic)])
        assert set(files(root))-set(before)=={'requested.log'} and '[exec]' in diagnostic.read_text()
        results['standalone_boot']=[];results['explicit_diagnostics']=['requested.log']
        assert list(elsewhere.iterdir())==[]
    proof={'passed':True,'commercial_rom_used':False,'visual_review_performed':False,
           'cases':results,'runtime_learning':False,'converter_learning_opt_in_verified':True}
    (directory/'verification.json').write_text(json.dumps(proof,indent=2),encoding='utf-8')
    print('PASS: startup, missing F9, existing/legacy configs and actual fallback create no files; only explicit config/F8/log writes persist; converter learning still works when opted in.')

if __name__=='__main__':main()
