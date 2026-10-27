"""Fresh-process replay and invalid-file checks for F8/F9 disk snapshots."""
import argparse
import json
import sys
from pathlib import Path
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tools/, also when imported as tools.<name>
from state_checks import (GUEST_FIELDS, controls_before, controls_text, first_trace_mismatch,
                          guest_differences, parse_two_player_script, route_controls,
                          run_report_trace as run)

def check(exe,output,warmup,replay,*,input_script=None):
    output.mkdir(parents=True,exist_ok=True)
    total=warmup+replay
    script=output/'input.txt'
    # Real menu inputs and changing controls exercise stateful port latches.
    identified,_=run(exe,output,'identify',1)
    md='console_version' in identified
    events=route_controls(total,md=md)
    if input_script is None:
        controls=events
    else:
        controls=parse_two_player_script(input_script,total)
    script.write_text(controls_text(controls),encoding='ascii')
    baseline,rows=run(exe,output,'baseline',total,'--play','--input-script',script)
    state=output/'saved.rrstate'
    prefix_script=output/'prefix-input.txt'
    prefix_script.write_text(controls_text(controls_before(controls,warmup)),encoding='ascii')
    run(exe,output,'prefix',warmup,'--play','--input-script',prefix_script,'--save-state',state)
    restored,future=run(exe,output,'restored',replay,'--play','--input-script',script,
                        '--frame-offset',warmup,'--load-state',state)
    columns=[key for key in rows[0] if key not in ('native','interpreted')]
    mismatch=first_trace_mismatch(rows[warmup:],future,columns)
    differing=guest_differences(baseline,restored)
    if mismatch is not None or differing:
        detail={'first_replay_mismatch':mismatch,'final_guest_differences':differing}
        if mismatch is not None:
            detail['frame_fields']={k:[rows[warmup+mismatch][k],future[mismatch][k]]
                                    for k in columns if rows[warmup+mismatch][k]!=future[mismatch][k]}
        (output/'divergence.json').write_text(json.dumps(detail,indent=2))
        raise AssertionError(detail)
    rejected=check_invalid_files(exe,output,state,replay)
    result={'exe':str(exe),'warmup':warmup,'replay':replay,
            'fresh_process_video_audio_cpu_match':True,**rejected}
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def check_invalid_files(exe,output,state,replay):
    """Reuse a qualified state without replaying an unrelated input route."""
    output.mkdir(parents=True,exist_ok=True)
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
    return {'state_bytes':len(original),'invalid_files_rejected':len(invalid),
            'missing_load_is_read_only':True}

def main():
    p=argparse.ArgumentParser(); p.add_argument('exe',type=Path); p.add_argument('--output',type=Path)
    p.add_argument('--warmup',type=int,default=1200); p.add_argument('--replay',type=int,default=300)
    p.add_argument('--input-script',type=Path,help='Use the same guided gameplay route before and after the saved state.')
    a=p.parse_args()
    if a.output: print(json.dumps(check(a.exe.resolve(),a.output.resolve(),a.warmup,a.replay,input_script=a.input_script)))
    else:
        with tempfile.TemporaryDirectory() as temp:
            print(json.dumps(check(a.exe.resolve(),Path(temp),a.warmup,a.replay,input_script=a.input_script)))
if __name__=='__main__': main()
