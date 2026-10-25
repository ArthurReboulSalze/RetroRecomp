"""Add qualified, BIOS-scoped numeric Neo Geo hints to the ROM-free snapshot."""
import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from retrorecomp.knowledge import load,validate_payload,MAX_BYTES
from retrorecomp.neogeo_knowledge import context,numeric_record,FIELDS,IDENTITY_FIELDS,validate_record,expanded_record,compact_record
from retrorecomp.neogeo import parse_neo
from retrorecomp.neogeo_build import GEOLITH_REV,LITHOGEN_REV


def qualified_record(report: dict):
    validation=report.get('native_validation',{})
    checks=report.get('final_checks',[])
    states=report.get('game_states',{}).get('validation',{})
    ordinary=report.get('ordinary_saves',{}).get('validation',{})
    if (report.get('system',{}).get('id')!='ng' or not validation.get('passed') or
        not validation.get('packed_reference_match') or not validation.get('reference_before_learning') or
        not checks or any(not c.get('reference_match') or c.get('interpreted_opcodes',1) or
                         c.get('audio_interpreted_opcodes',1) or not c.get('native_entries') or
                         not c.get('audio_native_opcodes') for c in checks) or
        len(states.get('routes',[]))!=3 or any(not r.get('fresh_process_match') or r.get('replayed_frames',0)<300
                                              for r in states.get('routes',[])) or
        states.get('invalid_states_rejected',0)<26 or not states.get('missing_load_is_read_only') or
        not ordinary.get('idle_launch_creates_nothing') or
        ordinary.get('native_main_fallback',1) or ordinary.get('native_sound_fallback',1) or
        not (ordinary.get('fresh_process_match') or ordinary.get('no_memory_change_on_route'))):
        raise ValueError('Neo Geo reference/packed/state qualification is incomplete.')
    compiler=report['compiler']
    if compiler['revision']!=GEOLITH_REV or compiler['loader_revision']!=LITHOGEN_REV:
        raise ValueError('Neo Geo qualification uses other tool revisions.')
    executable=Path(report['build_executable']).resolve()
    project=(Path(report['build_directory']).resolve() if report.get('build_directory') else
             executable.parents[2 if executable.suffix.casefold()=='.exe' else 1])
    if not project.is_dir():
        raise ValueError('The Neo Geo build folder was removed after publication; convert again with '
                         '--keep-build (or RETRO_RECOMP_KEEP_BUILD=1) to qualify its hints.')
    from retrorecomp.neogeo_build import aes_available
    expected_aes=aes_available(project)
    if report.get('runtime_modes',{}).get('aes_available') is not expected_aes:
        raise ValueError('Neo Geo machine qualification differs from the verified cartridge/BIOS.')
    if expected_aes:
        aes=report['game_states']['validation'].get('aes',{})
        memory=report['ordinary_saves']['validation'].get('aes',{})
        if (len(aes.get('routes',[]))!=2 or aes.get('invalid_states_rejected',0)<26 or
            not aes.get('missing_load_is_read_only') or
            any(not r.get('fresh_process_match') or r.get('replayed_frames',0)<300 for r in aes.get('routes',[])) or
            not memory.get('idle_launch_creates_nothing') or memory.get('native_main_fallback',1) or
            memory.get('native_sound_fallback',1) or not (memory.get('fresh_process_match') or memory.get('no_memory_change_on_route'))):
            raise ValueError('Neo Geo AES qualification is incomplete.')
        for route in aes['routes']:
            for phase in ('continuous','restored'):
                filename='continuous.json' if phase=='continuous' and aes.get('continuous_report')=='continuous.json' else f"{phase}-{route['warmup']}.json"
                replay=json.loads((project/'aes-state-checks'/filename).read_text(encoding='utf-8'))
                if replay.get('interpreted_68000',1) or replay.get('interpreted_z80',1):
                    raise ValueError('Neo Geo AES replay still uses fallback; keep its hints private.')
    for route in states['routes']:
        for phase in ('continuous','restored'):
            path=project/'state-checks'/f"{phase}-{route['warmup']}.json"
            if phase=='continuous' and states.get('continuous_report')=='continuous.json':
                path=project/'state-checks/continuous.json'
            replay=json.loads(path.read_text(encoding='utf-8'))
            if replay.get('interpreted_68000',1) or replay.get('interpreted_z80',1):
                raise ValueError('Neo Geo state replay still uses fallback; keep its hints private.')
    candidate=project/'packed-game.exe'
    if hashlib.sha256(candidate.read_bytes()).hexdigest()!=report['packed_candidate_sha256']:
        raise ValueError('Qualified Neo Geo packed candidate changed.')
    if parse_neo(project/'cartridge.neo').sha256!=report['prepared_cartridge']['sha256']:
        raise ValueError('Qualified Neo Geo cartridge regions changed.')
    identity,current,_=context(project)
    if identity!=report['knowledge']['identity'] or current['bios']!=report['bios']['sha256']:
        raise ValueError('Qualified Neo Geo BIOS identity changed.')
    # Fresh source observations only. The additive private memory may contain
    # more historical entries; it cannot waive this qualification gate.
    return numeric_record(project)


def merge_qualified(identity,previous,current):
    """Keep earlier verified observations only for the same prepared inputs/pins.

    This accepts records from the validated shared snapshot, never the private
    raw library. New entries still come exclusively through qualified_record.
    """
    validate_record(identity,current)
    if previous is None:return current
    validate_record(identity,previous)
    if any(previous[field]!=current[field] for field in IDENTITY_FIELDS):return current
    previous=expanded_record(identity,previous);current=expanded_record(identity,current)
    merged=copy.deepcopy(current)
    for field in FIELDS:
        merged[field]=[list(row) for row in sorted(set(map(tuple,previous[field]+current[field])))]
    validate_record(identity,merged)
    return merged


def build(reports: Path,base: Path,output: Path):
    payload=copy.deepcopy(load(base));before=copy.deepcopy(payload['consoles'])
    records=payload['consoles'].setdefault('ng',{});added=[]
    for path in sorted(reports.rglob('conversion-report.json')):
        report=json.loads(path.read_text(encoding='utf-8'))
        if report.get('system',{}).get('id')!='ng':continue
        identity,record=qualified_record(report)
        records[identity]=merge_qualified(identity,records.get(identity),record);added.append(identity)
    if not added:raise ValueError('No qualified Neo Geo conversions found.')
    # Store exact numeric roots as deltas, retaining every qualified observation.
    # Expansion is bounded and validated before any consumer reconstructs guards.
    for identity,record in list(records.items()):
        packed=compact_record(identity,record)
        if expanded_record(identity,packed)!=expanded_record(identity,record):
            raise ValueError('Neo Geo compact knowledge changed its observations.')
        records[identity]=packed
    validate_payload(payload)
    if any(payload['consoles'][name]!=data for name,data in before.items() if name!='ng'):
        raise ValueError('Another console changed while adding Neo Geo knowledge.')
    raw=json.dumps(payload,sort_keys=True,separators=(',',':')).encode('ascii')
    if len(raw)>MAX_BYTES:raise ValueError('Shared compilation knowledge exceeds its bounded budget.')
    packed=gzip.compress(raw,compresslevel=9,mtime=0)
    output.parent.mkdir(parents=True,exist_ok=True);temporary=output.with_suffix(output.suffix+'.tmp')
    temporary.write_bytes(packed);temporary.replace(output);load.cache_clear()
    return {'rom_free':True,'qualified_ng_records':len(records),'refreshed':len(set(added)),
        'other_consoles_unchanged':True,'raw_bytes':len(raw),'gzip_bytes':len(packed),
        'sha256':hashlib.sha256(packed).hexdigest(),'consoles':{k:len(v) for k,v in payload['consoles'].items()}}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reports',type=Path,required=True)
    parser.add_argument('--base',type=Path,default=ROOT/'assets/compilation-knowledge.json.gz')
    parser.add_argument('--output',type=Path,default=ROOT/'assets/compilation-knowledge.json.gz')
    args=parser.parse_args();print(json.dumps(build(args.reports,args.base,args.output),indent=2))
