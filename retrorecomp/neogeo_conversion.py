"""Neo Geo native conversion through the shared batch/export contract.

BIOS selection, reference comparison, packed replay and state checks precede
replacement of an existing export. Private probe data never enter game folders.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time

from . import __version__
from .core import executable_name, ConversionError
from .library import atomic_json
from .neogeo import read_set, validate_bios
from .neogeo_build import convert_reference, GEOLITH_REV, LITHOGEN_REV, aes_available, aes_compatible, probe_failure
from .neogeo_validation import extended_routes, compare, route_arguments
from .paths import selected_bios_path
from .toolchain import describe as toolchain_description


def check_routes(executable: Path, project: Path, set_name: str, qualification=None, *, workers=1) -> list[dict]:
    """Recheck the packed candidate against its fresh pre-learning reference."""
    directory = project / 'packed-checks'
    directory.mkdir(exist_ok=True)
    checked = []
    def verify(row):
        name, (frames, _) = row
        report = directory / (name + '.json')
        script = project / 'native-discovery' / (name + '.inputs')
        run = subprocess.run([str(executable), '--headless', *route_arguments(name), '--frames', str(frames),
            '--script', str(script), '--rtc-seed', '1760000000', '--report', str(report)],
            capture_output=True, timeout=max(240,frames/60*4))
        if run.returncode:
            raise ConversionError(str(probe_failure('packed '+name, run)))
        native = json.loads(report.read_text(encoding='utf-8'))
        reference = json.loads((project / 'native-discovery' / (name + '-reference.json')).read_text(encoding='utf-8'))
        compare(native, reference, require_native=False)
        if not native['nonzero_samples'] or native['nonuniform_frames'] < frames // 2:
            raise ConversionError('Neo Geo validation produced no usable image/audio.')
        return {'name': name, 'frames': frames, 'native_entries': native['native_68000'],
            'interpreted_opcodes': native['interpreted_68000'],
            'audio_native_opcodes': native['native_z80'], 'audio_interpreted_opcodes': native['interpreted_z80'],
            'interpreter_percent': round(100*native['interpreted_68000']/max(1,native['native_68000']+native['interpreted_68000']),6),
            'reference_match': True, 'cpu_hash': native['cpu_hash'], 'ram_hash': native['ram_hash'],
            'hardware_hash': native['extended_hardware_hash'], 'z80_hash': native['z80_hash'],
            'image_hash': native['image_hash'], 'pcm_hash': native['pcm_hash']}
    from concurrent.futures import ThreadPoolExecutor
    routes = extended_routes(set_name,qualification,aes=aes_available(project))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        checked = list(pool.map(verify,routes.items()))
    return checked


def convert(path: Path, *, ng_bios=None, bios=None, title=None, output=None, cover=None,
            use_cover=True, online_cover=True, boxart_dir=None, icon_tags=True,
            language='en', passes=3, frames=3600, backend='banked', standard_override=None,
            publish_result=True, profile=None, ng_qualification_routes=None, ng_parallel_games=1,
            scan_level=None, emit=print) -> Path:
    started=time.perf_counter()
    workers=max(1,min(4,8//max(1,ng_parallel_games)))
    from .scan_levels import LEVELS, neogeo_budget
    level=scan_level or 'standard'
    if level not in LEVELS:raise ConversionError(f'Unknown scan level: {level!r}.')
    scan=neogeo_budget(level)
    timings={}
    firmware=selected_bios_path(ng_bios or bios)
    if firmware is None:
        raise ConversionError('Select your BIOS archive in Options → Neo Geo before converting.')
    bios_info=validate_bios(firmware)
    if profile is not None:
        raise ConversionError('Neo Geo identifies cartridge layouts by CRC; Sega TOML profiles do not apply.')
    if standard_override not in (None, 'mvs'):
        raise ConversionError('Neo Geo currently uses the qualified MVS Europe profile.')
    game=read_set(path)
    title=title or game.title
    if scan['route_count']:
        # Extended and thorough add credited pseudo-random routes to the
        # qualification routes of this set, as developer extra routes: same
        # validation, fallback stays reported rather than fatal.
        from .random_routes import long_routes as pseudo_random_routes, neogeo_script
        plans=dict(ng_qualification_routes or {})
        extra=dict(plans.get(game.set_name,{}))
        for route in pseudo_random_routes('ng',game.sha256,count=scan['route_count'],frames=scan['route_frames']):
            extra.setdefault(route.name,(route.frames,neogeo_script(route)))
        plans[game.set_name]=extra
        ng_qualification_routes=plans
        emit(f'Neo Geo scan level {level}: {scan["route_count"]} reproducible pseudo-random routes of '
             f'{scan["route_frames"]} frames, with a credit, join the qualification routes.')
    presentation={'rom_path':path,'export_identity':game.sha256,'cover':cover,
        'use_cover':use_cover,'online_cover':online_cover,'boxart_dir':boxart_dir,'emit':emit,
        'feedback_output':output}
    executable=convert_reference(path,bios=firmware,set_name=game.set_name if path.suffix.casefold()!='.neo' else None,
        native=True,title=title,presentation=presentation,pack=False,emit=emit,qualification=ng_qualification_routes,
        validation_workers=workers,defer_to_packed=True)
    timings['prepare_translate_build_and_compare']=round(time.perf_counter()-started,3)
    phase=time.perf_counter()
    import os
    project=executable.parents[2 if os.name == 'nt' and executable.parent.name == 'Release' else 1]
    manifest=json.loads((project/'input.json').read_text(encoding='utf-8'))
    if manifest['bios']['sha256']!=bios_info['sha256'] or manifest['source']['sha256']!=game.sha256:
        raise ConversionError('Neo Geo cartridge or BIOS changed during conversion; add the files again.')
    console_capable=aes_compatible(project/'cartridge.neo')
    console_available='aes' in bios_info and console_capable
    if not console_capable:emit('Neo Geo: Arcade Only; AES is not a supported machine for this cartridge.')
    from .packing import compact_executable
    packed=project/'packed-game.exe'
    shutil.copy2(executable,packed)
    compact_executable(packed)
    timings['executable_compression']=round(time.perf_counter()-phase,3);phase=time.perf_counter()
    emit('Neo Geo: comparing the compressed executable with the fresh reference.')
    checks=check_routes(packed,project,game.set_name,ng_qualification_routes,workers=workers)
    # The delivered, compressed executable is the native candidate. Compare
    # every route once against the fresh reference; an earlier uncompressed
    # replay of identical CPU code adds no coverage. Until this gate passes,
    # the build receipt remains explicitly unqualified.
    validation=json.loads((project/'native-validation.json').read_text(encoding='utf-8'))
    validation.update(passed=True,awaiting_packed_validation=False,validated_candidate='packed',
        packed_sha256=hashlib.sha256(packed.read_bytes()).hexdigest(),
        routes=[{'route':row['name'],'frames':row['frames'],'passed':True,
                 'main_native':row['native_entries'],'main_fallback':row['interpreted_opcodes'],
                 'sound_native':row['audio_native_opcodes'],'sound_fallback':row['audio_interpreted_opcodes']}
                for row in checks])
    atomic_json(project/'native-validation.json',validation)
    timings['packed_replays']=round(time.perf_counter()-phase,3);phase=time.perf_counter()
    from .neogeo_state_checks import check as check_states
    warmups=(30,3300,7000) if game.set_name=='nam1975' else (30,4500,6000)
    state_script=project/'native-discovery'/('card-save.inputs' if game.set_name=='nam1975' else 'play.inputs')
    extra=(ng_qualification_routes or {}).get(game.set_name,{})
    if extra:
        longest,(count,_)=max(extra.items(),key=lambda row:row[1][0])
        warmups=(30,4500,count-600)
        state_script=project/'native-discovery'/(longest+'.inputs')
    emit('Neo Geo: checking F8/F9 in fresh processes and rejecting invalid states.')
    from concurrent.futures import ThreadPoolExecutor
    mode_jobs=min(workers,2) if console_available else 1
    with ThreadPoolExecutor(max_workers=mode_jobs) as pool:
        mvs=pool.submit(check_states,packed,project/'state-checks',warmups=warmups,
            input_script=state_script,require_native=False,workers=max(1,workers//mode_jobs))
        aes=pool.submit(check_states,packed,project/'aes-state-checks',warmups=(30,4500),
            input_script=project/'native-discovery/aes-play.inputs',require_native=False,
            workers=max(1,workers//mode_jobs),mode='aes') if console_available else None
        states=mvs.result()
        if aes:states['aes']=aes.result()
    timings['state_checks']=round(time.perf_counter()-phase,3);phase=time.perf_counter()
    from .neogeo_persistence_checks import check as check_memory
    emit('Neo Geo: checking ordinary scores/card persistence without F8/F9.')
    with ThreadPoolExecutor(max_workers=mode_jobs) as pool:
        mvs=pool.submit(check_memory,packed,project,frames=13800 if game.set_name=='nam1975' else 7200,script=state_script)
        aes=pool.submit(check_memory,packed,project,frames=7200,
            script=project/'native-discovery/aes-play.inputs',mode='aes') if console_available else None
        ordinary=mvs.result()
        if aes:ordinary['aes']=aes.result()
    timings['ordinary_saves']=round(time.perf_counter()-phase,3)
    from .metadata import game_metadata
    from .neogeo_knowledge import remember
    memory=remember(project,checks,states,title=title,source=game.metadata())
    from .systems.neogeo import NEOGEO
    native_coverage=all(not row['interpreted_opcodes'] and not row['audio_interpreted_opcodes'] for row in checks)
    report={'tool':'Retro-Recomp','version':__version__,
        'status':'completed' if not NEOGEO.experimental and native_coverage else 'experimental',
        'created_utc':datetime.now(timezone.utc).isoformat(),'system':{'id':'ng','name':'Neo Geo'},
        'rom':game.metadata(),'prepared_cartridge':manifest['prepared'],'bios':bios_info,
        'compiler':{'repository':'libretro/geolith-libretro','revision':GEOLITH_REV,
                    'loader_revision':LITHOGEN_REV,'native_cpu':'shared 68000 and guarded Z80'},
        'final_checks':checks,'native_validation':{'passed':True,'packed_reference_match':True,
            'reference_before_learning':True,'reference_kind':'internal Geolith hardware family',
            'cpu_agreement':True,'hardware_fidelity_validated':False,'full_game_validated':False},
        'video_model':{'standard':'mvs','region':'eu','visible_pixels':[320,224],'hz':59.185606},
        'audio_cpu':'Z80','counter_unit':'retired instructions','runtime_learning':True,
        'runtime_feedback':json.loads((project/'runtime-feedback-use.json').read_text(encoding='utf-8')),
        'physical_latency_measured':False,'game_states':{'supported':True,'save_key':'F8','load_key':'F9',
            'compatibility':'exact cartridge regions, selected BIOS, MVS Europe and runtime ABI','validation':states},
        'ordinary_saves':{'supported':True,'scope':'game-scoped MVS NVRAM and writable memory card',
            'path':'datas/saves/NeoGeo-<exact-cart-and-BIOS-key>.rrsave','validation':ordinary},
        'knowledge':{**memory,'use':json.loads((project/'knowledge-use.json').read_text(encoding='utf-8'))},
        'artwork':json.loads((project/'artwork.json').read_text(encoding='utf-8')),
        'windows_metadata':game_metadata(title,False,standard='mvs',system_id='ng'),
        'executable':executable_name(title),'build_executable':str(executable),'toolchain':toolchain_description(),
        'build_directory':str(project),
        'packed_candidate_sha256':hashlib.sha256(packed.read_bytes()).hexdigest(),
        'conversion_wall_seconds':round(time.perf_counter()-started,3)}
    report['conversion_phases_seconds']=timings
    report['validation_workers']=workers
    report['runtime_modes']={'default':'mvs','aes_available':console_available,
        'arcade_only':not console_capable,'aes_bios_present':'aes' in bios_info,'switch_key':'F11',
        'switch_restarts_game':console_available,'enhanced_default':True}
    report['scan_level']=level
    report['qualification_scope']={'system':'MVS','region':'Europe','bios':'four verified user-supplied components',
        'controls':'ordinary two-player joysticks' if manifest['prepared'].get('ngh')!=0x236 else 'MVS trackball mapping not yet qualified',
        'native_board_families':['standard','LINKABLE','CT0','KOF98','SMA','MSLUGX','PVC'],
        'hardware_specification_checks':136,'independent_game_hardware_implementation':False,
        'electrical_bus_phases_qualified':False,'universal_zero_fallback_claim':False}
    report['qualification_extra_routes']={name:{'frames':count,'script_sha256':hashlib.sha256(text.encode('ascii')).hexdigest()}
        for name,(count,text) in (ng_qualification_routes or {}).get(game.set_name,{}).items()}
    if output is None:
        from .paths import games_directory
        output=games_directory(system_id='ng')/'datas/reports'/game.sha256
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    atomic_json(output/'conversion-report.json',report)
    return executable
