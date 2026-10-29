"""Check save/relaunch continuation on one generated NES EXE, without a window."""
import argparse
from pathlib import Path
import json
import shutil
import sys
import tempfile
import wave
import hashlib
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from retrorecomp.core import run, ConversionError

def resume_input(source: Path, start: int, target: Path) -> Path:
    """Replay held keys and future events after a fresh-process quick load."""
    held={1:'-',2:'-'}; events=[]; previous=-1
    for line in source.read_text(encoding='ascii').splitlines():
        if not line.strip() or line.lstrip().startswith('#'): continue
        fields=line.split(maxsplit=1); frame=int(fields[0])
        if frame<previous or frame<0: raise ValueError('Input events must be sorted and nonnegative')
        previous=frame; keys=fields[1] if len(fields)>1 else '-'
        port=2 if keys.startswith('2:') else 1
        if keys.startswith(('1:','2:')): keys=keys[2:]
        if frame<start: held[port]=keys
        else: events.append((frame-start,port,keys))
    target.write_text(''.join(f'{frame} {port}:{keys}\n'
        for frame,port,keys in [(0,p,k) for p,k in held.items()]+events),encoding='ascii')
    return target

def check(executable: Path, frames: int=180, *, save_after: int | None=None,
          script: Path | None=None) -> dict:
    save_after=frames if save_after is None else save_after
    if frames<1 or save_after<1: raise ValueError('Save and continuation frame counts must be positive')
    with tempfile.TemporaryDirectory(prefix='retro-nes-state-') as tmp:
        folder=Path(tmp); exe=folder/'game.exe'; shutil.copy2(executable,exe)
        # Ordinary startup/shutdown and a missing load must remain read-only.
        run([exe,'--frames','1'])
        assert list(folder.iterdir())==[exe], 'Startup created files'
        try:
            run([exe,'--frames','1','--quick-load',folder/'datas/states/missing.rrstate'])
        except ConversionError:
            pass
        else:
            raise AssertionError('Missing state was accepted')
        assert list(folder.iterdir())==[exe], 'Missing load created files'
        saved=folder/'datas/states/fixture.rrstate'
        full_input=['--input',script] if script else []
        resumed_input=['--input',resume_input(script,save_after,folder/'resume.input')] if script else []
        run([exe,'--frames',str(save_after+frames),'--hash-out',folder/'full.hash',
             '--wav-out',folder/'full.wav','--quick-save',saved,
             '--quick-save-frame',str(save_after-1),*full_input])
        # Every byte of a state is defined: the same run saved by a second process gives the same file.
        again=folder/'datas/states/again.rrstate'
        run([exe,'--frames',str(save_after+frames),'--hash-out',folder/'again.hash','--wav-out',folder/'again.wav',
             '--quick-save',again,'--quick-save-frame',str(save_after-1),*full_input])
        assert again.read_bytes()==saved.read_bytes(), 'Two saves of one run differ'
        run([exe,'--frames',str(frames),'--hash-out',folder/'resume.hash',
             '--wav-out',folder/'resume.wav','--quick-load',saved,*resumed_input])
        full=(folder/'full.hash').read_text().splitlines()[save_after:]
        resumed=(folder/'resume.hash').read_text().splitlines()
        # Trace accounting is intentionally cumulative within each process;
        # compare all remaining fields, including cycles and chip-state hash.
        assert len(full)==len(resumed)==frames
        assert all(a[a.index('mem='):]==b[b.index('mem='):] for a,b in zip(full,resumed)), 'State continuation differs'
        with wave.open(str(folder/'full.wav')) as f: pcm=f.readframes(f.getnframes())
        with wave.open(str(folder/'resume.wav')) as f: resumed_pcm=f.readframes(f.getnframes())
        assert resumed_pcm and pcm[-len(resumed_pcm):]==resumed_pcm, 'Audio continuation differs'
        original=saved.read_bytes(); digest=hashlib.sha256(original).hexdigest()
        # Header fields are not covered by the payload CRC: check their own
        # identity gate as well as payload corruption and a truncated file.
        for name,offset in [('magic',0),('abi',8),('rom',73),('region',148),('payload',len(original)-1),('truncated',None)]:
            damaged=bytearray(original)
            if offset is None: damaged=damaged[:-1]
            else: damaged[offset]^=0x80
            rejected=folder/f'{name}.rrstate'; rejected.write_bytes(damaged)
            try:
                run([exe,'--frames','1','--quick-load',rejected])
            except ConversionError:
                pass
            else:
                raise AssertionError(f'{name} state was accepted')
            assert rejected.read_bytes()==damaged, 'Failed load rewrote the rejected file'
            assert hashlib.sha256(saved.read_bytes()).hexdigest()==digest, 'Failed load rewrote the valid state'
        return {'executable':str(executable),'saved_after_frames':save_after,
                'input_sha256':hashlib.sha256(script.read_bytes()).hexdigest() if script else None,
                'resumed_frames':frames,'state_bytes':len(original),'rejected_state_cases':6,
                'two_saves_identical':True,'cpu_memory_hardware_match':True,'pcm_match':True,'lazy_io':True,'corruption_rejected':True}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('executables',nargs='+',type=Path)
    p.add_argument('--frames',type=int,default=180)
    p.add_argument('--save-after',type=int);p.add_argument('--input',type=Path);args=p.parse_args()
    for executable in args.executables:
        print(json.dumps(check(executable.resolve(),args.frames,save_after=args.save_after,script=args.input)),flush=True)
