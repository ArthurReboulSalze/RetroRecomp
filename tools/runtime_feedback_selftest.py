"""Compile and exercise actual exit-only Windows recorder, without any ROM."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp.core import run, toolchain
from retrorecomp.feedback import MAX_BYTES, decode, stage
from retrorecomp.platforms import cmake_target_args, build_executable


def main():
    work = ROOT / '.build/feedback-selftest' / uuid.uuid4().hex
    work.mkdir(parents=True)
    shutil.copy2(ROOT / 'native/runtime_feedback_checks.c', work / 'checks.c')
    (work / 'CMakeLists.txt').write_text('''cmake_minimum_required(VERSION 3.21)
project(FeedbackChecks C)
add_executable(game checks.c)
target_compile_definitions(game PRIVATE _CRT_SECURE_NO_WARNINGS)
''')
    identity = '1' * 64
    stage(work, 'sms', identity)
    cmake, generator = toolchain()
    run([cmake, '-S', work, '-B', work/'build', '-G', generator, *cmake_target_args()], log=work/'build.log')
    run([cmake, '--build', work/'build', '--config', 'Release'], log=work/'build.log')
    source = build_executable(work/'build', 'game')
    def install(name):
        folder = work/name
        folder.mkdir()
        exe = folder/'renommé.exe'
        shutil.copy2(source, exe)
        return exe, folder/'datas/fallbacks'/f'sms-{identity}.rrfb'
    env = os.environ.copy()
    env.pop('RETRO_RECOMP_FEEDBACK', None)
    exe, path = install('sans observations')
    subprocess.run([exe, 'none'], check=True, env=env, capture_output=True)
    assert not path.parents[1].exists()
    exe, path = install('écriture à la fermeture')
    process = subprocess.Popen([exe,'hold','100'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env)
    assert process.stdout.readline().strip() == b'buffered'
    assert not path.parents[1].exists(), 'Writing while playing is forbidden'
    process.communicate(b'\n', timeout=10)
    assert process.returncode == 0
    rows, dropped = decode(path.read_bytes(), 'sms', identity)
    assert len(rows) == 100 and not dropped and path.stat().st_size == 3296
    before = path.stat().st_mtime_ns
    subprocess.run([exe, 'write','100'], check=True, env=env, capture_output=True)
    assert path.stat().st_mtime_ns == before, 'Repeated sites must not rewrite the file'
    # Two simultaneous normal exits must merge, not overwrite one another.
    a = subprocess.Popen([exe,'hold','25','100'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,env=env)
    b = subprocess.Popen([exe,'hold','25','125'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,env=env)
    assert a.stdout.readline().strip() == b.stdout.readline().strip() == b'buffered'
    a.stdin.write(b'\n');a.stdin.flush();b.stdin.write(b'\n');b.stdin.flush()
    assert a.wait(timeout=10) == b.wait(timeout=10) == 0
    rows, _ = decode(path.read_bytes(), 'sms', identity)
    assert len(rows) == 150
    subprocess.run([exe,'write','9000'], check=True, env=env, capture_output=True)
    rows, dropped = decode(path.read_bytes(),'sms',identity)
    assert len(rows)==4096 and dropped and path.stat().st_size==MAX_BYTES
    # A saturated journal still receives new observations in later sessions.
    subprocess.run([exe,'write','1','10000'], check=True, env=env,capture_output=True)
    rows, _ = decode(path.read_bytes(),'sms',identity)
    assert any(row.address == 10000 for row in rows)
    exe, path = install('disabled')
    subprocess.run([exe,'disabled','100'], check=True,env=env,capture_output=True)
    assert not path.parents[1].exists()
    exe,path=install('F12 preference')
    p=subprocess.Popen([exe,'hold-off','100'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,env=env)
    assert p.stdout.readline().strip()==b'buffered'
    assert not path.parents[1].exists(), 'F12 must not write during gameplay either'
    p.communicate(b'\n',timeout=10);assert p.returncode==0
    assert not path.exists()
    ini=exe.parent/'datas/Retro-Recomp.ini'
    assert ini.is_file()
    before=ini.stat().st_mtime_ns
    subprocess.run([exe,'write','100'],check=True,env=env,capture_output=True)
    assert not path.exists() and ini.stat().st_mtime_ns==before, 'OFF must survive relaunch without rewriting settings'
    subprocess.run([exe,'toggle-on','1'],check=True,env=env,capture_output=True)
    assert len(decode(path.read_bytes(),'sms',identity)[0])==1
    subprocess.run([exe,'write','1','100'],check=True,env=env,capture_output=True)
    assert len(decode(path.read_bytes(),'sms',identity)[0])==2, 'ON must survive relaunch'
    result = {'passed':True, 'no_io_before_exit':True, 'no_empty_directories':True,
        'unicode_paths':True, 'concurrent_merge':True, 'deduplicated_without_rewrite':True,
        'max_bytes_per_game':MAX_BYTES, 'bytes_for_100_sites':3296,
        'F12_capture_only_toggle':True,'F12_persisted_on_shutdown':True}
    (work/'results.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result))
    print(work)


if __name__ == '__main__':
    main()
