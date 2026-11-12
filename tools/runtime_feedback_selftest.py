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
from retrorecomp.feedback import FORMAT_MAX_BYTES, HEADER, MAX_BYTES, RECORD, Observation, checksum, decode, encode, stage
from retrorecomp.platforms import cmake_target_args, build_executable


def version(path):
    return int.from_bytes(path.read_bytes()[8:12], 'little')


def raw_file(system, identity, version_number, count, kind, base=100000, dropped=0):
    """A hand-built file with a valid digest, whatever its version and count (the reader's rules are under test)."""
    rows = b''.join(RECORD.pack(kind, 4, 0, base + n, 0, b'\x3e\xa5\x76\0'.ljust(16, b'\0'), 0) for n in range(count))
    return HEADER.pack(b'RRFB001\0', version_number, count, dropped, system.encode().ljust(8, b'\0'),
                       identity.encode(), checksum(rows)) + rows


def main():
    work = ROOT / '.build/feedback-selftest' / uuid.uuid4().hex
    work.mkdir(parents=True)
    identity = '1' * 64
    env = os.environ.copy()
    env.pop('RETRO_RECOMP_FEEDBACK', None)

    def build(system, kind):
        """The harness compiled as `system` (the record kind it notes is `kind`); returns its installer."""
        folder = work / ('source-' + system)
        folder.mkdir()
        shutil.copy2(ROOT / 'native/runtime_feedback_checks.c', folder / 'checks.c')
        (folder / 'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.21)
project(FeedbackChecks C)
add_executable(game checks.c)
target_compile_definitions(game PRIVATE _CRT_SECURE_NO_WARNINGS RR_CHECK_KIND={kind})
''')
        stage(folder, system, identity)
        cmake, generator = toolchain()
        run([cmake, '-S', folder, '-B', folder/'build', '-G', generator, *cmake_target_args()], log=folder/'build.log')
        run([cmake, '--build', folder/'build', '--config', 'Release'], log=folder/'build.log')
        source = build_executable(folder/'build', 'game')
        def install(name):
            target = work/(system + ' ' + name)
            target.mkdir()
            exe = target/'renommé.exe'
            shutil.copy2(source, exe)
            return exe, target/'datas/fallbacks'/f'{system}-{identity}.rrfb'
        return install, (folder / 'runtime_feedback_config.h').read_text(encoding='ascii')

    def play(exe, *arguments):
        subprocess.run([exe, *arguments], check=True, env=env, capture_output=True, timeout=120)

    install, config = build('sms', 1)
    assert 'RR_FEEDBACK_LIMIT' not in config, 'The bound is written only above 4096'
    exe, path = install('sans observations')
    play(exe, 'none')
    assert not path.parents[1].exists()
    exe, path = install('écriture à la fermeture')
    process = subprocess.Popen([exe,'hold','100'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env)
    assert process.stdout.readline().strip() == b'buffered'
    assert not path.parents[1].exists(), 'Writing while playing is forbidden'
    process.communicate(b'\n', timeout=10)
    assert process.returncode == 0
    rows, dropped = decode(path.read_bytes(), 'sms', identity)
    assert len(rows) == 100 and not dropped and path.stat().st_size == 3296
    assert version(path) == 1
    before = path.stat().st_mtime_ns
    play(exe, 'write','100')
    assert path.stat().st_mtime_ns == before, 'Repeated sites must not rewrite the file'
    # Two simultaneous normal exits must merge, not overwrite one another.
    a = subprocess.Popen([exe,'hold','25','100'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,env=env)
    b = subprocess.Popen([exe,'hold','25','125'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,env=env)
    assert a.stdout.readline().strip() == b.stdout.readline().strip() == b'buffered'
    a.stdin.write(b'\n');a.stdin.flush();b.stdin.write(b'\n');b.stdin.flush()
    assert a.wait(timeout=10) == b.wait(timeout=10) == 0
    rows, _ = decode(path.read_bytes(), 'sms', identity)
    assert len(rows) == 150
    play(exe, 'write','9000')
    rows, dropped = decode(path.read_bytes(),'sms',identity)
    assert len(rows)==4096 and path.stat().st_size==MAX_BYTES and version(path)==1
    # Each record is noted twice: `dropped` counts distinct refused records (about 4904; a call count would be 9808).
    sms_dropped = dropped
    assert 4400 <= dropped <= 4904, dropped
    # A saturated journal still receives new observations in later sessions.
    play(exe, 'write','1','10000')
    rows, _ = decode(path.read_bytes(),'sms',identity)
    assert any(row.address == 10000 for row in rows)
    exe, path = install('disabled')
    play(exe, 'disabled','100')
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
    play(exe, 'write','100')
    assert not path.exists() and ini.stat().st_mtime_ns==before, 'OFF must survive relaunch without rewriting settings'
    play(exe, 'toggle-on','1')
    assert len(decode(path.read_bytes(),'sms',identity)[0])==1
    play(exe, 'write','1','100')
    assert len(decode(path.read_bytes(),'sms',identity)[0])==2, 'ON must survive relaunch'
    # A version 2 file of 5000 records read by the 4096 build: the C reader accepts the shape (version 2, count above 4096,
    # up to the format cap) whatever the build's bound, merges it after this session's records, keeps 4096 and counts
    # the distinct rows left out. A valid digest, so only the shape rules are exercised.
    exe, path = install('version 2 beyond the bound')
    path.parent.mkdir(parents=True)
    path.write_bytes(raw_file('sms', identity, 2, 5000, 1))
    play(exe, 'write','10','700000')
    rows, dropped = decode(path.read_bytes(),'sms',identity)
    assert len(rows) == 4096 and version(path) == 1 and path.stat().st_size == MAX_BYTES, (len(rows), version(path))
    assert [row.address for row in rows[:10]] == list(range(700000, 700010)), 'This session first'
    assert [row.address for row in rows[10:]] == list(range(100000, 100000 + 4086)), 'then the old file in file order'
    assert 850 <= dropped <= 914, dropped  # 5000 + 10 - 4096 = 914 distinct records left out (a lower bound)
    sms_v2_dropped = dropped

    # The Mega Drive: a bound of 65536, version 2 above 4096 records (the same harness staged as md, kind 5).
    md_install, md_config = build('md', 5)
    assert '#define RR_FEEDBACK_LIMIT 65536u\n' in md_config
    exe, path = md_install('five thousand')
    play(exe, 'write','5000')
    rows, dropped = decode(path.read_bytes(),'md',identity)
    assert (len(rows), dropped, version(path)) == (5000, 0, 2)
    assert path.stat().st_size == HEADER.size + 5000 * RECORD.size == 160096
    before = path.stat().st_mtime_ns
    play(exe, 'write','5000')
    assert path.stat().st_mtime_ns == before, 'A version 2 file is not rewritten for the same sites either'
    # A version 1 file from an older game (a call count in `dropped`) is read as zero; this session's records come first.
    exe, path = md_install('old file')
    path.parent.mkdir(parents=True)
    older = [Observation(5, 100000 + n, 0, b'\x3e\xa5\x76\0') for n in range(4096)]
    path.write_bytes(encode(older, 'md', identity, 3000000))
    assert version(path) == 1 and decode(path.read_bytes(), 'md', identity)[1] == 3000000
    play(exe, 'write','5000')
    rows, dropped = decode(path.read_bytes(),'md',identity)
    assert len(rows) == 9096 and version(path) == 2 and dropped == 0, (len(rows), dropped)
    assert [row.address for row in rows[:5000]] == list(range(5000)), 'This session first, the old file after'
    # The refused count: a full record counts the distinct records it left out.
    exe, path = md_install('full')
    play(exe, 'write','70000')
    rows, dropped = decode(path.read_bytes(),'md',identity)
    assert len(rows) == 65536 and path.stat().st_size == 2097248 == FORMAT_MAX_BYTES and version(path) == 2
    assert 4000 <= dropped <= 4464, dropped
    md_dropped = dropped
    play(exe, 'write','1','200000')
    rows, dropped = decode(path.read_bytes(),'md',identity)
    assert len(rows) == 65536 and any(row.address == 200000 for row in rows) and dropped >= md_dropped
    # Two exits together on a 4000-record file: the union, one valid version 2 file.
    exe, path = md_install('concurrency')
    play(exe, 'write','4000')
    assert version(path) == 1
    a = subprocess.Popen([exe,'hold','3000','3000'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,env=env)
    b = subprocess.Popen([exe,'hold','3000','5000'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,env=env)
    assert a.stdout.readline().strip() == b.stdout.readline().strip() == b'buffered'
    a.stdin.write(b'\n');a.stdin.flush();b.stdin.write(b'\n');b.stdin.flush()
    assert a.wait(timeout=30) == b.wait(timeout=30) == 0
    rows, _ = decode(path.read_bytes(),'md',identity)
    assert {row.address for row in rows} == set(range(8000)) and len(rows) == 8000 and version(path) == 2
    # Damage: a file cut by one record, then one with a flipped byte, is replaced by the next session, never merged.
    data = path.read_bytes()
    path.write_bytes(data[:-RECORD.size])
    play(exe, 'write','7','500000')
    rows, _ = decode(path.read_bytes(),'md',identity)
    assert [row.address for row in rows] == list(range(500000, 500007)) and version(path) == 1
    play(exe, 'write','5000')
    assert version(path) == 2
    data = bytearray(path.read_bytes())
    data[HEADER.size + 1000 * RECORD.size + 12] ^= 0xff
    path.write_bytes(bytes(data))
    play(exe, 'write','3','600000')
    rows, _ = decode(path.read_bytes(),'md',identity)
    assert [row.address for row in rows] == [600000, 600001, 600002]
    # The canonical form: a version 2 file of 4000 records, or a version 1 file of 5000, is not a valid file;
    # the game replaces it with this session's records and never merges it (digest, system and identity are valid).
    exe, path = md_install('version 2 with 4000')
    path.parent.mkdir(parents=True)
    path.write_bytes(raw_file('md', identity, 2, 4000, 5))
    play(exe, 'write','10','700000')
    rows, dropped = decode(path.read_bytes(),'md',identity)
    assert [row.address for row in rows] == list(range(700000, 700010)) and version(path) == 1 and dropped == 0
    exe, path = md_install('version 1 with 5000')
    path.parent.mkdir(parents=True)
    path.write_bytes(raw_file('md', identity, 1, 5000, 5))
    play(exe, 'write','10','700000')
    rows, dropped = decode(path.read_bytes(),'md',identity)
    assert [row.address for row in rows] == list(range(700000, 700010)) and version(path) == 1 and dropped == 0
    result = {'passed':True, 'no_io_before_exit':True, 'no_empty_directories':True,
        'unicode_paths':True, 'concurrent_merge':True, 'deduplicated_without_rewrite':True,
        'max_bytes_per_game':MAX_BYTES, 'bytes_for_100_sites':3296,
        'F12_capture_only_toggle':True,'F12_persisted_on_shutdown':True,
        'sms_refused_records':sms_dropped, 'md_max_bytes_per_game':FORMAT_MAX_BYTES,
        'md_version_2_above_4096':True, 'md_refused_records':md_dropped,
        'md_old_file_dropped_read_as_zero':True, 'md_concurrent_union':True, 'md_damaged_file_replaced':True,
        'sms_version_2_file_merged_and_cut_to_4096':True, 'sms_version_2_file_refused_records':sms_v2_dropped,
        'md_non_canonical_files_replaced':True}
    (work/'results.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result))
    print(work)


if __name__ == '__main__':
    main()
