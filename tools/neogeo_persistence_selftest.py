"""Fresh-process ordinary-save checks, entirely authored memory and local IO."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from retrorecomp.neogeo_build import prepare_project
from retrorecomp.core import run,toolchain


def check(output: Path):
    output=output.resolve();output.mkdir(parents=True,exist_ok=True)
    project=output/'build-project';prepare_project(project)
    (project/'retro16_state_config.h').write_text('#define RR16_STATE_ROM "'+'a'*64+'"\n',encoding='ascii')
    with (project/'CMakeLists.txt').open('a',encoding='utf-8') as file:
        file.write(f'\nadd_executable(persistence_checks "{ROOT.as_posix()}/native/neogeo_persistence_checks.c" neogeo_persistence.c)\n'
                   'target_link_libraries(persistence_checks PRIVATE ng_hardware)\n')
    cmake,generator=toolchain()
    run([cmake,'-S',project,'-B',project/'build','-G',generator,'-A','x64'],log=project/'build.log')
    run([cmake,'--build',project/'build','--config','Release','--target','persistence_checks','--parallel','4'],log=project/'build.log')
    folder=output/('fresh Été-'+uuid.uuid4().hex[:8]);folder.mkdir()
    exe=folder/'checks.exe';shutil.copy2(project/'build/Release/persistence_checks.exe',exe)
    saved=folder/'datas/saves'/('NeoGeo-'+'a'*64+'.rrsave')
    if saved.exists():saved.unlink()
    checks=0
    def launch(mode,binary=exe):
        nonlocal checks
        result=subprocess.run([str(binary),mode],capture_output=True,timeout=20)
        if result.returncode:raise RuntimeError(f'{mode}: {result.returncode} {result.stderr[-1500:]!r}')
        row=json.loads(result.stdout);checks+=row['checks'];return row
    launch('idle');launch('disabled')
    # On the first run even the parent folders must remain absent.
    if (folder/'datas').exists():raise RuntimeError('Idle synthetic launch created datas.')
    launch('save');original=saved.read_bytes();mtime=saved.stat().st_mtime_ns
    if len(original)!=67712:raise RuntimeError('Unexpected save size.')
    launch('load');launch('unchanged')
    if saved.read_bytes()!=original or saved.stat().st_mtime_ns!=mtime:raise RuntimeError('Unchanged save rewritten.')
    renamed=folder/'renamed game.exe';shutil.copy2(exe,renamed);launch('load',renamed)
    launch('state');state_version=saved.read_bytes()
    if state_version[128+512]!=99:raise RuntimeError('Explicit snapshot was not persisted.')
    corruptions=[b'',state_version[:127],state_version[:-1],state_version+b'x']
    for offset in (0,8,12,16,20,24,32,96,100,104,127,128,65000):
        bad=bytearray(state_version);bad[offset]^=255;corruptions.append(bytes(bad))
    for bad in corruptions:
        saved.write_bytes(bad);launch('invalid')
        if saved.read_bytes()!=bad:raise RuntimeError('Rejected save was overwritten.')
    saved.write_bytes(state_version);launch('conflict')
    if saved.read_bytes()[128+512]!=88:raise RuntimeError('Concurrent save lost.')
    if list(saved.parent.glob('*.tmp')):raise RuntimeError('Temporary file left behind.')
    summary={'passed':True,'rom_free':True,'synthetic_checks':checks,'fresh_process_load':True,
        'invalid_files_rejected':len(corruptions),'idle_launch_creates_nothing':True,
        'unchanged_file_not_rewritten':True,'rename_preserves_identity':True,
        'explicit_state_persisted':True,'concurrent_update_preserved':True,'bytes':67712}
    (output/'result.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,default=ROOT/'.build/neogeo-persistence-selftest')
    print(json.dumps(check(parser.parse_args().output),indent=2))
