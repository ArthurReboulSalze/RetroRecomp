"""Replay already-qualified packed exports and retain private visual evidence."""
from pathlib import Path
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import hashlib
import json
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from smsrecomp.neogeo_validation import compare, route_arguments


def replay(path,root):
    report=json.loads(path.read_text(encoding='utf-8'))
    project=Path(report['build_executable']).resolve().parents[2]
    binary=Path(report['published_directory'])/report['executable']
    digest=hashlib.sha256(binary.read_bytes()).hexdigest()
    if digest!=report['packed_candidate_sha256']:raise ValueError('Published candidate changed: '+report['executable'])
    name=report['rom']['set'];directory=root/name;directory.mkdir(parents=True,exist_ok=True)
    extras=report.get('qualification_extra_routes',{})
    route=max(extras,key=lambda name:extras[name]['frames']) if extras else 'play'
    frames=next(r['frames'] for r in report['final_checks'] if r['name']==route)
    captures=directory/route;captures.mkdir(exist_ok=True)
    out=directory/(route+'.json');script=project/'native-discovery'/(route+'.inputs')
    result=subprocess.run([str(binary),'--headless',*route_arguments(route),'--frames',str(frames),'--script',str(script),
        '--rtc-seed','1760000000','--report',str(out),'--capture',str(captures),'--capture-every','900'],
        capture_output=True,timeout=max(300,frames/60*4))
    if result.returncode:raise RuntimeError(f'{name} capture replay failed: {result.returncode}')
    actual=json.loads(out.read_text(encoding='utf-8'))
    expected=json.loads((project/'packed-checks'/(route+'.json')).read_text(encoding='utf-8'))
    compare(actual,expected,require_native=True)
    row={'set':name,'title':report['rom']['title'],'frames':frames,'route':route,'matched':True,
         'exe_sha256':digest,'main_fallback':actual['interpreted_68000'],'sound_fallback':actual['interpreted_z80'],
         'captures':str(captures),'native_main':actual['native_68000'],'native_sound':actual['native_z80'],
         'audio_nonzero':actual['nonzero_samples'],'audio_clipped':actual['clipped_samples'],
         'resets':actual['resets']}
    print(json.dumps(row),flush=True);return row


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--reports',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--sets',nargs='+')
    p.add_argument('--jobs',type=int,choices=range(1,9),default=8)
    a=p.parse_args();root=a.output.resolve();root.mkdir(parents=True,exist_ok=True)
    paths=[path for path in a.reports.rglob('conversion-report.json')
           if not a.sets or json.loads(path.read_text(encoding='utf-8'))['rom']['set'] in a.sets]
    rows=[]
    with ThreadPoolExecutor(max_workers=a.jobs) as pool:
        pending=[pool.submit(replay,path,root) for path in paths]
        for result in as_completed(pending):rows.append(result.result())
    (root/'replay-results.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')


if __name__=='__main__':main()
