"""Real packed-game ordinary saves, independent of snapshots and user files."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from .core import ConversionError


def check(executable: Path,project: Path,*,frames=7200,script: Path | None=None) -> dict:
    destination=project/'ordinary-save-checks';destination.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='game-',dir=destination) as temp:
        folder=Path(temp);binary=folder/'game.exe';shutil.copy2(executable,binary)
        def probe(label,frames,script=None):
            report=destination/(label+'.json')
            args=[str(binary),'--headless','--frames',str(frames),'--persistent-memory',
                  '--rtc-seed','1760000000','--report',str(report)]
            if script:args+=['--script',str(script)]
            run=subprocess.run(args,capture_output=True,timeout=240)
            if run.returncode:raise ConversionError(f'Neo Geo ordinary save {label} failed ({run.returncode}).')
            data=json.loads(report.read_text(encoding='utf-8'))
            return data
        idle=probe('idle',180)
        if (folder/'datas').exists():raise ConversionError('Neo Geo idle launch created persistent data.')
        played=probe('played',frames,script or project/'native-discovery/play.inputs')
        memory=played['persistent_memory'];files=list(folder.glob('datas/saves/*.rrsave'))
        if memory['blocked']:raise ConversionError('Neo Geo ordinary-save validation was blocked.')
        result={'idle_launch_creates_nothing':True,'meaningful_guest_changes_saved':memory['saved'],
                'validation_frames':frames,'native_main_fallback':played['interpreted_68000'],
                'native_sound_fallback':played['interpreted_z80'],'fresh_process_match':False}
        if memory['saved']:
            if len(files)!=1 or files[0].stat().st_size!=67712:raise ConversionError('Neo Geo ordinary save has an invalid size.')
            original=files[0].read_bytes();mtime=files[0].stat().st_mtime_ns
            reopened=probe('reopened',1)['persistent_memory']
            if (not reopened['loaded'] or reopened['initial_nvram_hash']!=memory['nvram_hash'] or
                reopened['initial_card_hash']!=memory['card_hash'] or files[0].read_bytes()!=original or
                files[0].stat().st_mtime_ns!=mtime):raise ConversionError('Neo Geo ordinary save did not survive a fresh process.')
            result.update(fresh_process_match=True,bytes=len(original),
                card_changed=played['persistent_memory']['initial_card_hash']!=memory['card_hash'])
        elif files:raise ConversionError('Neo Geo unchanged memory unexpectedly created a save.')
        else:result['no_memory_change_on_route']=True
    (destination/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8');return result
