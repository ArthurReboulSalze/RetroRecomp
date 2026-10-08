"""Check save/relaunch continuation on one generated NES EXE, without a window."""
import argparse
from pathlib import Path
import json
import shutil
import sys
import tempfile
import wave
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from smsrecomp.core import run, ConversionError

def check(executable: Path, frames: int=180) -> dict:
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
        run([exe,'--frames',str(frames*2),'--hash-out',folder/'full.hash',
             '--wav-out',folder/'full.wav','--quick-save',saved,
             '--quick-save-frame',str(frames-1)])
        run([exe,'--frames',str(frames),'--hash-out',folder/'resume.hash',
             '--wav-out',folder/'resume.wav','--quick-load',saved])
        full=(folder/'full.hash').read_text().splitlines()[frames:]
        resumed=(folder/'resume.hash').read_text().splitlines()
        # Trace accounting is intentionally cumulative within each process;
        # compare all remaining fields, including cycles and chip-state hash.
        assert len(full)==len(resumed)==frames
        assert all(a[a.index('mem='):]==b[b.index('mem='):] for a,b in zip(full,resumed)), 'State continuation differs'
        with wave.open(str(folder/'full.wav')) as f: pcm=f.readframes(f.getnframes())
        with wave.open(str(folder/'resume.wav')) as f: resumed_pcm=f.readframes(f.getnframes())
        assert resumed_pcm and pcm[-len(resumed_pcm):]==resumed_pcm, 'Audio continuation differs'
        damaged=bytearray(saved.read_bytes());damaged[-1]^=0x80;saved.write_bytes(damaged)
        try:
            run([exe,'--frames','1','--quick-load',saved])
        except ConversionError:
            pass
        else:
            raise AssertionError('Corrupt state was accepted')
        return {'executable':str(executable),'resumed_frames':frames,'state_bytes':len(damaged),
                'cpu_memory_hardware_match':True,'pcm_match':True,'lazy_io':True,'corruption_rejected':True}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('executables',nargs='+',type=Path)
    p.add_argument('--frames',type=int,default=180);args=p.parse_args()
    for executable in args.executables: print(json.dumps(check(executable.resolve(),args.frames)),flush=True)
