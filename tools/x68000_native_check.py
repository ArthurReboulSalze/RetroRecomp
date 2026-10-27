"""Check private step-3 pairs without waiving a reference/trace gate.

These compare CPU execution on the SAME X68000 hardware implementation.
They do not independently establish hardware fidelity, full-game compatibility,
desktop frame pacing, sound-device quality, or physical latency.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.x68000_reference_check import cases,validate_trace,compare_traces


def validate_pair(reference:dict,native:dict,frames:int)->dict:
    if reference.get('mode')!='interpreted-reference' or reference.get('native_cpu') is not False:
        raise ValueError('An independently run interpreted reference is required.')
    if native.get('mode')!='guarded-native-prototype' or native.get('native_cpu') is not True:
        raise ValueError('The native path was not actually exercised.')
    for item in (reference,native):
        if item.get('frames')!=frames or item.get('core_error') is not False or item.get('ram_mib')!=2 or item.get('cpu_mhz')!=10:
            raise ValueError('Incomplete or incompatible machine run.')
        for name in ('native_ram','native_ipl','reference_ram','reference_ipl'):
            if type(item.get(name)) is not int or item[name]<0:raise ValueError('Missing instruction counters.')
    if reference['native_ram'] or reference['native_ipl'] or native['reference_ram'] or native['reference_ipl']:
        raise ValueError('Reference used AOT or qualified native run used an interpreter fallback.')
    for region in ('ram','ipl'):
        if native['native_'+region]!=reference['reference_'+region] or native['native_'+region]<=0:
            raise ValueError('Instruction counts do not agree in every region.')
    excluded={'mode','native_cpu','wall_seconds','native_ram','native_ipl','reference_ram','reference_ipl'}
    a={k:v for k,v in reference.items() if k not in excluded}
    b={k:v for k,v in native.items() if k not in excluded}
    if a!=b:raise ValueError('CPU, RAM, video, PCM or machine timing report differs.')
    return {'native_ram':native['native_ram'],'native_ipl':native['native_ipl'],
            'interpreted_instructions':0,'report_equal':True}


def validate_runs(reference:Path,native:Path)->dict:
    result={'schema':1,'passed':False,'native_cpu':True,'cases':[],
            'limits':'Same-machine CPU comparison only; no complete-game, independent hardware or physical latency claim.'}
    identities=set()
    for case in cases():
        a=reference/case.name;b=native/case.name
        read=lambda p:json.loads(p.read_text(encoding='utf-8'))
        ref,actual=read(a/'report.json'),read(b/'report.json')
        pair=validate_pair(ref,actual,case.frames)
        for directory in (a,b):validate_trace(directory/'trace.tsv',case.frames)
        trace=compare_traces(a/'trace.tsv',b/'trace.tsv')
        if not trace['identical']:raise ValueError(f'Unmasked CPU/RAM/video/PCM trace difference: {case.name}')
        if (a/'capture.ppm').read_bytes()!=(b/'capture.ppm').read_bytes():raise ValueError('Final capture differs.')
        guards=read(b/'guard-checks.json')
        if guards!={'passed':True,'checks':1048575,'expected':1048575}:raise ValueError('The 20 authored CPU/guard checks did not all pass.')
        source_a,source_b=read(a/'datas/source-manifest.json'),read(b/'datas/source-manifest.json')
        if source_a.get('sha256')!=source_b.get('sha256'):raise ValueError('Source media/firmware/configuration differs.')
        identities.add(source_a['sha256'])
        if case.name.startswith('gameplay') and actual.get('nonzero_samples',0)<=0:raise ValueError('Gameplay PCM is silent.')
        result['cases'].append({'name':case.name,**pair,'trace':trace,'guard_checks':guards,
            'source_identity':source_a['sha256'],'capture_equal':True})
    replay=compare_traces(native/'gameplay-a/trace.tsv',native/'gameplay-b/trace.tsv')
    if not replay['identical']:raise ValueError('Fresh native replay does not agree.')
    result.update(passed=True,host_steps_compared=sum(c.frames for c in cases()),
        source_identities=sorted(identities),replay=replay)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference',type=Path,required=True);p.add_argument('--native',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True);a=p.parse_args()
    report=a.report.resolve()
    if not report.is_relative_to((ROOT/'.build').resolve()):p.error('Private reports must stay in project .build.')
    result=validate_runs(a.reference,a.native)
    report.parent.mkdir(parents=True,exist_ok=True)
    report.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'host_steps_compared':result['host_steps_compared'],
        'interpreted_instructions':0,'native_instructions':sum(x['native_ram']+x['native_ipl'] for x in result['cases'])}))

if __name__=='__main__':main()
