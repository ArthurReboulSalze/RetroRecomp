"""Qualify stage-4 device vectors and the integer guest-clock/PCM ledger.

Device assertions are separate from same-board native/reference agreement.
Neither establishes complete hardware fidelity, desktop pacing or latency.
"""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.x68000_reference_check import cases,validate_trace
from tools.x68000_native_check import validate_runs

EXPECTED={'video':(21,2097151),'timing':(20,1048575),'audio':(18,262143)}

def check_ledger(rows:list[dict], report:dict)->dict:
    previous={k:0 for k in ('guest_frames','cpu_cycles','peripheral_ticks','lines','audio_pairs')}
    emitted=budget=0
    for row in rows:
        now={k:int(row[k]) for k in previous}
        if any(now[k]<previous[k] for k in previous):raise ValueError('A hardware counter moved backwards.')
        if now['guest_frames']-previous['guest_frames'] not in (0,1):raise ValueError('More than one guest frame per host step.')
        if now['cpu_cycles']!=now['peripheral_ticks']:raise ValueError('10 MHz CPU/peripheral clocks disagree.')
        emitted+=int(row['samples'])
        if now['audio_pairs']!=emitted or emitted!=now['peripheral_ticks']*44100//10000000:
            raise ValueError('PCM amount does not follow elapsed guest ticks exactly.')
        if int(row['audio_errors']) or not 0<=int(row['samples'])<=1024:raise ValueError('Invalid or truncated PCM batch.')
        if now['guest_frames']>previous['guest_frames']:
            if int(row['frame_budget']) not in (162707,180310):raise ValueError('Unexpected qualified frame budget.')
            budget+=int(row['frame_budget'])
        # The instruction ending a frame may cross its boundary; its debt must
        # carry into the following frame instead of being discarded per slice.
        if not 0<=now['cpu_cycles']-budget<=512:raise ValueError('CPU slice overshoot debt was lost or accumulated.')
        previous=now
    hardware=report.get('hardware',{})
    mapping={'frames':'guest_frames','cpu_cycles':'cpu_cycles','peripheral_ticks':'peripheral_ticks',
             'lines':'lines','audio_pairs':'audio_pairs'}
    if any(hardware.get(k)!=previous[v] for k,v in mapping.items()):raise ValueError('Report and frame ledger disagree.')
    if report.get('audio_samples')!=emitted or report.get('sample_rate')!=44100.0 or hardware.get('audio_errors')!=0:
        raise ValueError('Audio report is incomplete or changes the output format.')
    if previous['guest_frames']<len(rows)*0.9:raise ValueError('Machine skipped an unexpected number of guest frames.')
    return {'guest_frames':previous['guest_frames'],'cpu_cycles':previous['cpu_cycles'],
            'peripheral_ticks':previous['peripheral_ticks'],'audio_pairs':emitted,
            'simulated_seconds':previous['peripheral_ticks']/10000000,
            'fractional_pcm_remainder':previous['peripheral_ticks']*44100%10000000,
            'max_instruction_debt_bound':512,'no_audio_invention_or_discard':True}

def check_diagnostics(value:dict, suite:str)->dict:
    count,mask=EXPECTED[suite]
    entries=value.get('checks',value.get('cases',[]))
    if len(entries)!=count or len({x.get('name') for x in entries})!=count:
        raise ValueError('Incomplete or duplicated authored device vectors: '+suite)
    if value.get('mask',value.get('passed_mask'))!=mask or value.get('expected_mask')!=mask:
        raise ValueError('Device assertion mask failed: '+suite)
    if any(x.get('passed') is not True for x in entries):raise ValueError('Device vector failed: '+suite)
    if suite!='audio' and value.get('state_restored') is not True:raise ValueError('Diagnostic state was not restored.')
    return {'passed':True,'vectors':count,'names':[x['name'] for x in entries]}

def validate_campaign(reference:Path,native:Path)->dict:
    cpu=validate_runs(reference,native)
    output={'schema':1,'passed':False,'cpu_agreement':cpu,'runs':[],'authored_vectors_per_run':sum(x[0] for x in EXPECTED.values()),
            'reference_directory':reference.as_posix(),'native_directory':native.as_posix(),
            'limits':'Bounded device contracts and same-board CPU agreement; not complete hardware/game/latency qualification.'}
    for label,folder in (('reference',reference),('native',native)):
        for case in cases():
            path=folder/case.name
            validate_trace(path/'trace.tsv',case.frames)
            with (path/'trace.tsv').open(encoding='ascii',newline='') as f:rows=list(csv.DictReader(f,delimiter='\t'))
            report=json.loads((path/'report.json').read_text())
            ledger=check_ledger(rows,report)
            diagnostics={name:check_diagnostics(json.loads((path/(name+'-checks.json')).read_text()),name) for name in EXPECTED}
            output['runs'].append({'engine':label,'case':case.name,'ledger':ledger,'devices':diagnostics})
    output['passed']=True
    return output

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference',type=Path,required=True);p.add_argument('--native',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True);a=p.parse_args()
    if not a.report.resolve().is_relative_to((ROOT/'.build').resolve()):p.error('Private qualification reports must stay under project .build.')
    result=validate_campaign(a.reference,a.native)
    a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'host_steps_per_engine':result['cpu_agreement']['host_steps_compared'],
                      'vectors_per_run':58,'runs':len(result['runs'])}))
