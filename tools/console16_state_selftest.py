"""Fresh-process replay and invalid-file checks for F8/F9 disk snapshots."""
import argparse
import csv
import json
from pathlib import Path
import subprocess
import tempfile

GUEST_FIELDS = ('cpu_hash','ram_hash','vram_hash','cram_hash','vsram_hash',
                'vdp_register_hash','z80_ram_hash','z80_cpu_hash','ym_timer_hash',
                'cpu_cycles','master_cycles','cpu_pc','cpu_sr','cpu_usp','cpu_ssp',
                'cpu_stopped','oam_hash','high_oam_hash','apu_ram_hash','apu_cycles')

def run(exe, output, name, frames, *args):
    report=output/(name+'.json'); trace=output/(name+'.csv')
    command=[str(exe),'--frames',str(frames),'--report',str(report),'--trace',str(trace),*map(str,args)]
    result=subprocess.run(command,capture_output=True,text=True,timeout=300)
    if result.returncode:
        raise RuntimeError(f'{name}: exit {result.returncode}\n{result.stderr[-3000:]}')
    with trace.open(newline='') as file: rows=list(csv.DictReader(file))
    return json.loads(report.read_text()),rows

def check(exe,output,warmup,replay):
    output.mkdir(parents=True,exist_ok=True)
    total=warmup+replay
    script=output/'input.txt'
    # Real menu inputs and changing controls exercise stateful port latches.
    md='md-' in str(exe.parent.parent.parent).lower()
    start=128 if md else 8; right=8 if md else 128; fire=16 if md else 1
    events={0:0}
    for f in (180,300,480,550,660,720):
        if f<total: events[f]=start
        if f+2<total: events[f+2]=0
    for f in range(800,total,30): events[f]=right|(fire if f%90==0 else 0)
    script.write_text(''.join(f'{f} {p} 0\n' for f,p in sorted(events.items())),encoding='ascii')
    baseline,rows=run(exe,output,'baseline',total,'--play','--input-script',script)
    state=output/'saved.rrstate'
    prefix_script=output/'prefix-input.txt'
    prefix_script.write_text(''.join(f'{f} {p} 0\n' for f,p in sorted(events.items()) if f<warmup),encoding='ascii')
    run(exe,output,'prefix',warmup,'--play','--input-script',prefix_script,'--save-state',state)
    restored,future=run(exe,output,'restored',replay,'--play','--input-script',script,
                        '--frame-offset',warmup,'--load-state',state)
    columns=[key for key in rows[0] if key not in ('native','interpreted')]
    mismatch=next((n for n,(a,b) in enumerate(zip(rows[warmup:],future))
                   if any(a[k]!=b[k] for k in columns)),None)
    differing=[key for key in GUEST_FIELDS if key in baseline and baseline[key]!=restored[key]]
    if mismatch is not None or differing:
        detail={'first_replay_mismatch':mismatch,'final_guest_differences':differing}
        if mismatch is not None:
            detail['frame_fields']={k:[rows[warmup+mismatch][k],future[mismatch][k]]
                                    for k in columns if rows[warmup+mismatch][k]!=future[mismatch][k]}
        (output/'divergence.json').write_text(json.dumps(detail,indent=2))
        raise AssertionError(detail)
    # Truncation, a wrong ROM, altered data and trailing bytes leave the guest
    # unchanged. F9 on a missing file must not create its parent directories.
    original=state.read_bytes()
    invalid=[original[:-1],original[:32]+bytes([original[32]^1])+original[33:],
             original[:-1]+bytes([original[-1]^1]),original+b'x']
    for offset in (12,16,96):
        invalid.append(original[:offset]+bytes([original[offset]^1])+original[offset+1:])
    # Valid outer integrity with a truncated inner machine payload exercises
    # transactional restore, rather than only the file header rejection.
    def reframed(payload):
        header=bytearray(original[:160]); header[20:24]=len(payload).to_bytes(4,'little')
        h=14695981039346656037
        for byte in payload: h=((h^byte)*1099511628211)&((1<<64)-1)
        header[24:32]=h.to_bytes(8,'little')
        return header+payload
    invalid.append(reframed(original[160:-1]))
    cold,cold_rows=run(exe,output,'cold',replay)
    for i,payload in enumerate(invalid):
        bad=output/f'bad-{i}.rrstate'; bad.write_bytes(payload)
        report,trace=run(exe,output,f'rejected-{i}',replay,'--load-state',bad,'--ignore-load-error')
        assert all(report.get(k)==cold.get(k) for k in GUEST_FIELDS)
        assert trace==cold_rows
    missing=output/'absent'/'never-created.rrstate'
    run(exe,output,'missing',replay,'--load-state',missing,'--ignore-load-error')
    assert not missing.parent.exists()
    result={'exe':str(exe),'warmup':warmup,'replay':replay,'state_bytes':len(original),
            'fresh_process_video_audio_cpu_match':True,'invalid_files_rejected':len(invalid),
            'missing_load_is_read_only':True}
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

def main():
    p=argparse.ArgumentParser(); p.add_argument('exe',type=Path); p.add_argument('--output',type=Path)
    p.add_argument('--warmup',type=int,default=1200); p.add_argument('--replay',type=int,default=300)
    a=p.parse_args()
    if a.output: print(json.dumps(check(a.exe.resolve(),a.output.resolve(),a.warmup,a.replay)))
    else:
        with tempfile.TemporaryDirectory() as temp:
            print(json.dumps(check(a.exe.resolve(),Path(temp),a.warmup,a.replay)))
if __name__=='__main__': main()
