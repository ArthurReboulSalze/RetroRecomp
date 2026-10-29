"""Exact-input Neo Geo disk state replay. Local ROM/BIOS evidence stays private."""
import csv
import json
from pathlib import Path
from .conversion_common import check_exit, spawn
from .conversion_gates import continuation_difference, require, require_equal
from .neogeo_validation import ROUTES


def probe(exe,output,name,frames,script=None,*extra,mode=None):
    report=output/(name+'.json');trace=output/(name+'.csv')
    args=[str(exe),'--headless','--frames',str(frames),'--rtc-seed','1760000000',
          '--report',str(report),'--trace',str(trace)]
    if script:args+=['--script',str(script)]
    if mode=='aes':args+=['--aes']
    result=spawn([*args,*map(str,extra)],cwd=output,timeout=max(240,frames/60*4),capture_output=True)
    check_exit(result,lambda r:RuntimeError(f'{name}: exit {r.returncode}: {r.stderr[-2000:]!r}'))
    data=json.loads(report.read_text(encoding='utf-8'))
    with trace.open(newline='') as stream:return data,list(csv.DictReader(stream))


def reframe(original,payload):
    head=bytearray(original[:160]);head[20:24]=len(payload).to_bytes(4,'little')
    h=14695981039346656037
    for byte in payload:h=((h^byte)*1099511628211)&((1<<64)-1)
    head[24:32]=h.to_bytes(8,'little');return head+payload


def check_invalid(exe,output,state,*,workers=1,mode=None):
    original=state.read_bytes();variants={}
    for name,offset in [('rom',32),('abi',96),('system',12),('region',16),('checksum',24)]:
        bad=bytearray(original);bad[offset]^=1;variants[name]=bad
    variants['truncated']=original[:-1];variants['trailing']=original+b'x'
    variants['inner-truncated']=reframe(original,original[160:-1])
    core=int.from_bytes(original[172:176],'little')
    board=original[160+32+core+48+4]
    cart_ram_bytes=8192 if board in (4,11) else 0 # PVC protection state / BrezzaSoft battery RAM.
    # Recomputed integrity exercises validation inside the machine adapter.
    for name,offset in [('inner-magic',0),('inner-version',8),('core-signature',32),
                        ('core-region',36),('core-system',37),('palette',32+67625+cart_ram_bytes+86016),
                        ('scanline',32+67625+cart_ram_bytes+86028),('z80-im',32+core-2102+29),
                        ('cpu-stopped',32+core),('reserved',28)]:
        payload=bytearray(original[160:]);payload[offset]=255
        variants[name]=reframe(original,payload)
    if int.from_bytes(original[180:184],'little')>=64:
        for name,offset in [('board-magic',0),('board-type',4),('board-mode',5),('board-reserved',15)]:
            payload=bytearray(original[160:]);payload[32+core+48+offset]=255
            variants[name]=reframe(original,payload)
    if int.from_bytes(original[180:184],'little')>=2656:
        for name,offset in [('lspc-magic',0),('lspc-buffer',4),('lspc-reserved',20),('lspc-palette-index',35)]:
            payload=bytearray(original[160:]);payload[32+core+64+offset]=255
            variants[name]=reframe(original,payload)
    cold,expected=probe(exe,output,'cold',60,mode=mode)
    def reject(row):
        name,data=row
        bad=output/(name+'.rrstate');bad.write_bytes(data)
        result,actual=probe(exe,output,'rejected-'+name,60,None,'--load-state',bad,'--ignore-load-error',mode=mode)
        require(result['load_rejected'] and not result['state_loaded'],lambda:RuntimeError('Invalid state was accepted: '+name))
        require_equal(actual,expected,lambda:RuntimeError('State rejection changed the machine: '+name))
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(reject,variants.items()))
    missing=output/'absent'/'must-not-create.rrstate'
    result,actual=probe(exe,output,'missing',60,None,'--load-state',missing,'--ignore-load-error',mode=mode)
    require(result['load_rejected'] and actual==expected and not missing.parent.exists(),
            lambda:RuntimeError('Missing F9 mutated the machine/filesystem.'))
    return {'invalid_states_rejected':len(variants),'missing_load_is_read_only':True}


def check(exe,output,warmups=(30,2600,3300),replay=300,input_script=None,*,require_native=True,workers=1,mode=None):
    output.mkdir(parents=True,exist_ok=True)
    script=output/'play.inputs';script.write_text(Path(input_script).read_text(encoding='ascii') if input_script else ROUTES['play'][1],encoding='ascii')
    checks=[]
    checkpoints=[]
    for warmup in warmups:
        checkpoints += ['--checkpoint',warmup,output/f'frame-{warmup}.rrstate']
    continuous,a=probe(exe,output,'continuous',max(warmups)+replay,script,*checkpoints,mode=mode)
    def replay_state(warmup):
        state=output/f'frame-{warmup}.rrstate'
        restored,b=probe(exe,output,f'restored-{warmup}',replay,script,'--load-state',state,mode=mode)
        require(restored['state_loaded'] and len(b)==replay,lambda:RuntimeError('Fresh state replay did not load/complete.'))
        mismatch=continuation_difference(a,b,warmup,replay)
        if mismatch is not None:
            detail={'warmup':warmup,'first_mismatch':mismatch,
                    'continuous':a[warmup+mismatch],'restored':b[mismatch]}
            (output/'divergence.json').write_text(json.dumps(detail,indent=2));raise AssertionError(detail)
        if require_native and any(report['interpreted_'+cpu] for report in (continuous,restored) for cpu in ('68000','z80')):
            raise RuntimeError('Interpreter fallback during the strict state replay.')
        return {'warmup':warmup,'replayed_frames':replay,'fresh_process_match':True,
                       'state_bytes':state.stat().st_size}
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=workers) as pool:
        checks=list(pool.map(replay_state,warmups))
    result={'exe':str(exe),'routes':checks,'continuous_report':'continuous.json',
            **check_invalid(exe,output,output/f'frame-{warmups[-1]}.rrstate',workers=workers,mode=mode),
            'physical_latency_measured':False,'complete_game_qualified':False}
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result
