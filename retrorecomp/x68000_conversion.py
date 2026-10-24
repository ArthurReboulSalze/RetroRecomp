"""Private local X68000 conversion: fresh discovery, guarded AOT and packed replay.

No observation waives a comparison. Only per-game builds contain private input
bytes; the public converter resources and knowledge bank are never extended.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from . import __version__
from .paths import ROOT, ASSETS, boxart_cache_directory
from .core import ConversionError, toolchain, run, executable_name
from .platforms import build_jobs, cmake_target_args, build_executable, target_id, sdl_install
from .toolchain import describe as toolchain_description, suffix as toolchain_suffix
from .library import atomic_json, entry_lock
from .x68000 import (developer_available, machine, automatic_disk_changes, mouse_reads, listed_mouse,
                     MOUSE_GAME_READS)


def digest(path):
    with Path(path).open('rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()


def compact_observations(record):
    """Merge exact encodings without duplicating the previous qualification.

    A fresh replay is still mandatory. Large generated blitters can contribute
    over 160,000 variants; appending the same learned list on regeneration used
    to exceed the observation-file bound despite adding no new instruction.
    """
    if record.get('schema')!=1 or record.get('truncated') is not False:
        raise ConversionError('Incomplete X68000 observations cannot be qualified.')
    merged={}
    for row in record['variants']:
        key=(row['pc'],row['words']);hits=row.get('hits',1)
        merged[key]=max(merged.get(key,1),hits)
        if len(merged)>1048576:raise ConversionError('X68000 instruction observation bound exceeded.')
    result=dict(record)
    result['variants']=[{'pc':pc,'words':words,'hits':hits} for (pc,words),hits in sorted(merged.items())]
    return result


def extend_observations(record, extra):
    """Only new exact encodings justify another native generation.

    A saturated fallback capture must not lose its truncation flag when merged
    into a complete reference capture. Counts alone never add CPU coverage.
    """
    current=compact_observations(record)
    incoming=compact_observations(extra)
    if incoming.get('source_identity') not in (None,current.get('source_identity')):
        raise ConversionError('X68000 additional observations have a different source identity.')
    merged=compact_observations({**current,'variants':current['variants']+incoming['variants']})
    return merged,len(merged['variants'])>len(current['variants'])


HISSORII_REPOSITORY='https://github.com/hissorii/px68k.git'
# Generators hashed into the SDK stamp; bundled as data beside their modules.
SDK_TOOLS=('x68000_native.py','x68000_reference.py','x68000_reference_check.py','x68000_base74.py',
           'x68000_state_hardware.py')


def sdk_stamp(part=None):
    """The SDK build identity; part='game' leaves out the player shell
    (player_ui.inc and host inputs), for upgrades without rediscovery."""
    files = [*sorted((ASSETS/'native/x68000_reference').glob('*')), *sorted((ASSETS/'native/x68000_native').glob('*')),
             *(ASSETS/'tools'/name for name in SDK_TOOLS),
             *sorted(p for p in (ASSETS/'native/x68000_machine').rglob('*') if p.is_file()),
             ASSETS/'retrorecomp/m68000_semantics.py',ASSETS/'retrorecomp/neogeo_codegen.py',
             ASSETS/'retrorecomp/megadrive_codegen.py',
             # Shared 68000 sources the generator copies into every X68000 CPU.
             ASSETS/'native/neogeo_native.h',ASSETS/'native/neogeo_native.c',ASSETS/'native/md_prefetch.inc']
    from .compilation_inputs import engine_stamp, role, role_stamps
    value=hashlib.sha256()
    for path in files:
        name=path.relative_to(ASSETS).as_posix()
        if part=='game' and role(name)=='host':continue
        if path.is_file():value.update(str(path.relative_to(ASSETS)).encode()+b'\0'+path.read_bytes())
    value.update((role_stamps('x68')['game'] if part=='game' else engine_stamp('x68')).encode())
    from tools.x68000_native import MACHINE_BASE
    value.update(b'machine-base\0'+MACHINE_BASE.encode())
    return value.hexdigest()


def payload(project, source, manifest, title, artwork, mouse_game=False):
    """Generate private resources. No user path becomes executable source code."""
    from .metadata import write_game_metadata
    from .resources import embed_resources
    project.mkdir(parents=True,exist_ok=True)
    files=[];resources={}
    # PE resources remain readable after the normal UPX publishing step, so
    # moving an EXE without its report does not lose collection ownership.
    marker=b'[Retro-Recomp]\0'+source.sha256.encode()+b'\0'
    branding=project/'export-marker.bin';branding.write_bytes(marker);resources[299]=branding
    def add(name, content, writable=False):
        identifier=300+len(files);path=project/('blob-%03d.bin'%identifier)
        path.write_bytes(content);resources[identifier]=path
        files.append((name,identifier,int(writable)))
    names=[]
    for n,disk in enumerate(manifest.media):
        name=f'disk-{n+1:02}.{disk.format}';names.append(name)
        add('media/'+name,disk.path.read_bytes(),True)
    add('media/game.m3u',('\n'.join(names)+'\n').encode())
    add('system/keropi/iplrom.dat',manifest.firmware.ipl.path.read_bytes())
    add('system/keropi/cgrom.dat',manifest.firmware.cgrom.path.read_bytes())
    manifest.verify_sources()
    declarations=['#ifndef RR_X68000_PAYLOAD_CONFIG','#define RR_X68000_PAYLOAD_CONFIG',
       '#include "media_session.h"',
       '#define RR_X68K_GAME_TITLE '+json.dumps(title,ensure_ascii=True),
       '#define RR_X68K_SOURCE_IDENTITY '+json.dumps(manifest.sha256),
       '#define RR_X68K_RAM_MIB '+str(manifest.config.ram_bytes//(1024*1024)),
       '#define RR_X68K_MOUSE_GAME '+str(int(mouse_game)),
       'typedef struct {const char *path;unsigned resource;int writable;} RrX68kPayloadFile;',
       'static const RrX68kPayloadFile rr_x68k_files[]={']
    declarations += ['{'+json.dumps(name)+f',{identifier},{writable}'+'},' for name,identifier,writable in files]
    declarations+=['};','#define RR_X68K_FILE_COUNT (sizeof(rr_x68k_files)/sizeof(rr_x68k_files[0]))',
       'static const volatile unsigned char rr_x68k_export_marker[]={'+','.join(str(c) for c in b'[Retro-Recomp]\0'+source.sha256.encode()+b'\0')+'};']
    declarations+=['#define RR_X68K_AUTO_DISK '+str(int(automatic_disk_changes(source))),'#endif']
    (project/'x68000_payload.h').write_text('\n'.join(declarations)+'\n',encoding='utf-8')
    (project/'runtime_feedback_config.h').write_text(
        '#define RR_FEEDBACK_SYSTEM "x68"\n#define RR_FEEDBACK_IDENTITY "'+manifest.sha256+'"\n',encoding='ascii')
    if not (project/'game.ico').is_file():shutil.copy2(ASSETS/'assets/Retro-Recomp.ico',project/'game.ico')
    metadata=write_game_metadata(project,title,executable_name(title),light_phaser=False,icon=True,standard='native',system_id='x68')
    (project/'game_metadata.rc').write_bytes((project/'game_resources.rc').read_bytes())
    if os.name=='nt':
        lines=['#pragma code_page(65001)']
        lines += [f'{identifier} RCDATA '+json.dumps(path.as_posix(),ensure_ascii=False) for identifier,path in resources.items()]
        (project/'game_resources.rc').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    else:embed_resources(project,resources)
    return metadata


def sdk_tree(base):
    """Bundled sources in a stable workspace folder.

    A packaged converter extracts its files to a new temporary folder on every
    launch; CMake caches must never point there, or a later conversion of the
    same game fails. Files are rewritten only when their bytes change.
    """
    if ASSETS.resolve() == ROOT.resolve():
        return ASSETS
    target = base/'sdk'
    sources = [*(ASSETS/'native').rglob('*'), *(ASSETS/'tools').glob('x68000_*.py'),
               *(ASSETS/'licenses').glob('*.md'), ASSETS/'LICENSE']
    for source in sources:
        if not source.is_file():
            continue
        destination = target/source.relative_to(ASSETS)
        data = source.read_bytes()
        if not destination.is_file() or destination.read_bytes() != data:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
    return target


def machine_sources(base, emit):
    """Pinned machine sources, fetched like the other profiles, and the 74ddbb3 tree.

    Returns CMake settings. The tree is generated here, in the converter's own
    Python, so a packaged application needs no separate interpreter.
    """
    from .console16 import dependencies16
    from .neogeo_build import pinned_dependency, GEOLITH_REV
    from tools.x68000_reference import HISSORII_REV
    from tools.x68000_base74 import generate as generate_machine
    dependencies16('md', emit)  # SDL and the shared 68000 instruction work
    emit('X68000: checking pinned machine sources (hissorii/px68k, Geolith).')
    geolith = pinned_dependency('geolith-libretro', 'https://github.com/libretro/geolith-libretro.git', GEOLITH_REV)
    hissorii = pinned_dependency('px68k-hissorii', HISSORII_REPOSITORY, HISSORII_REV)
    tree = base/'machine-74ddbb3'
    with entry_lock(base/'machine-lock', timeout=1800):
        if not (tree/'ready.json').is_file():
            receipt = generate_machine(hissorii, hissorii, tree, geolith)
            atomic_json(tree/'ready.json', {'files': len(receipt['files']), 'base_commit': receipt['base_commit']})
    return (f'-DRR_X68000_B74_TREE={tree.as_posix()}', f'-DRR_GEOLITH_DIR={geolith.as_posix()}',
            f'-DRR_B74_SOURCE={hissorii.as_posix()}', f'-DRR_X68000_TOOL_STAMP={sdk_stamp()}')


def build_player(work, payload_dir, *, emit, machine=(), sdk=ASSETS):
    from tools.x68000_native import MACHINE_BASE, fresh_cache
    cmake,generator=toolchain();build=work/'build'
    fresh_cache(build,sdk/'native/x68000_native')
    run([cmake,'-S',sdk/'native/x68000_native','-B',build,'-G',generator,*cmake_target_args(),
         f'-DPX68K_DIR={(ROOT/".deps/px68k-reference").as_posix()}',
         f'-DCMAKE_PREFIX_PATH={sdl_install().as_posix()}',
         f'-DRR_X68000_GENERATED={work.as_posix()}',f'-DRR_X68000_PAYLOAD_DIR={payload_dir.as_posix()}',
         f'-DRR_X68000_MACHINE_BASE={MACHINE_BASE}',*machine,
         f'-DRR_RECOMP_VERSION={__version__}'],log=work/'build.log')
    emit('X68000: compiling the guarded CPU and linked player.')
    run([cmake,'--build',build,'--config','Release','--parallel',build_jobs()],log=work/'build.log')
    return build_executable(build/'reference','RetroRecomp-X68000-Native')


def route_workers(routes):
    """Replays this game may run at once: its share of the host CPUs (see
    platforms.compilation_budget), never more than its routes."""
    from .platforms import game_cpu_share
    return max(1,min(int(routes),game_cpu_share()))


def run_routes(jobs, workers):
    """Replay independent routes side by side; results keep the input order
    and the first failure is raised as the sequential loop would have."""
    jobs=list(jobs)
    if workers<=1 or len(jobs)<=1:
        return [replay(binary,folder,frames,events,**options) for binary,folder,frames,events,options in jobs]
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=workers,thread_name_prefix='x68000-route') as pool:
        futures=[pool.submit(replay,binary,folder,frames,events,**options)
                 for binary,folder,frames,events,options in jobs]
        return [future.result() for future in futures]


def replay(binary, folder, frames, events, *, reference=False, observe=False, extra=()):
    from tools.x68000_reference_check import validate_trace
    folder.mkdir(parents=True,exist_ok=True)
    args=[str(binary),'--headless','--frames',str(frames),'--report',str(folder/'result.json'),
          '--trace',str(folder/'trace.tsv'),'--capture',str(folder/'frame.ppm'),'--input-events',str(events)]
    if reference:args+=['--reference-cpu']
    if observe:args+=['--observations',str(folder/'observations.json')]
    args+=list(map(str,extra))
    with (folder/'stdout.log').open('wb') as out,(folder/'stderr.log').open('wb') as err:
        # No console window per validation run in the windowed converter.
        result=subprocess.run(args,stdout=out,stderr=err,timeout=max(360,frames//3),
                              creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    if result.returncode:
        raise ConversionError('X68000 replay failed: '+(folder/'stderr.log').read_text(errors='replace')[-2000:])
    report=json.loads((folder/'result.json').read_text());validate_trace(folder/'trace.tsv',frames)
    if report.get('core_error') or report['frames']!=frames or report['hardware']['audio_errors']:
        raise ConversionError('X68000 validation returned an incomplete/error run.')
    return report


def convert(path, *, x68_ipl=None,x68_cgrom=None,x68_ram=2,title=None,output=None,cover=None,
            use_cover=True,online_cover=True,passes=3,frames=4000,scan_level=None,emit=print,
            qualification_events=None,**unused):
    if not developer_available():raise ConversionError('The X68000 converter files are missing from this installation.')
    from .scan_levels import LEVELS, x68000_budget
    level=scan_level or 'standard'
    if level not in LEVELS:raise ConversionError(f'Unknown scan level: {level!r}.')
    scan=x68000_budget(level)
    if unused.get('standard_override') not in (None,'native','auto'):
        raise ConversionError('X68000 timing follows its CRTC; PAL/NTSC overrides do not apply.')
    source,manifest=machine(path,x68_ipl,x68_cgrom,x68_ram)
    title=title or source.title
    if any(ord(c)<32 for c in title) or len(title)>160:raise ConversionError('Invalid X68000 game title.')
    # Workspace paths (.deps, .build) follow ROOT; bundled sources stay in ASSETS.
    from tools import x68000_native as native, x68000_reference as reference
    from tools.x68000_reference_check import cases
    native.ROOT=reference.ROOT=ROOT
    # MSBuild's file tracker still has short-path limits even when Python and
    # Windows support long paths. Full identities stay in the receipts.
    stamp=sdk_stamp();base=ROOT/'.build/x68'/(('win'+toolchain_suffix()) if os.name=='nt' else 'linux')/stamp[:12]
    base.mkdir(parents=True,exist_ok=True)
    if not output:
        from .paths import games_directory
        output=games_directory(system_id='x68')/'datas/reports'/source.sha256
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    emit('X68000: verifying exact disks, IPL, font ROM and machine settings.')
    from .feedback import ingest, records
    feedback=ingest('x68',manifest.sha256,output,emit=emit)
    sdk=native.SDK=sdk_tree(base)
    machine_settings=machine_sources(base,emit)
    with entry_lock(base/'discovery-lock',timeout=1800):
        common=base/'discovery';ready=common/'ready.json'
        generic=Path(json.loads(ready.read_text())['executable']) if ready.exists() else None
        if not generic or not generic.is_file():
            native.generate(common,[],ROOT/'.deps/px68k-reference')
            generic=native.build(common,ROOT/'.deps/px68k-reference',sdl_install(),int(build_jobs()),
                                 extra=machine_settings)
            atomic_json(ready,{'executable':str(generic),'sdk':stamp})
    work=base/manifest.sha256[:16]
    with entry_lock(work/'lock',timeout=1800):
        import tempfile
        # These are independent cold boots. Reusing a previous replay's SRAM
        # or writable disk copies would compare different starting machines.
        checks=Path(tempfile.mkdtemp(prefix='qa-',dir=work))
        count=max(4000,min(int(frames),10000))
        event_file=work/'inputs.tsv'
        events=cases()[2].events if qualification_events is None else tuple(qualification_events)
        if len(events)>4096 or any(len(e)!=5 or type(e[0]) is not int or type(e[1]) is not int or
            not 0<=e[0]<e[1]<=count or e[2] not in ('key','joy','joy2','mouse') or
            type(e[3]) is not int or not 0<=e[3]<(320 if e[2]=='key' else 4 if e[2]=='mouse' else 16) or
            type(e[4]) is not int or (not -32768<=e[4]<=32767 if e[2]=='mouse' else e[4] not in (0,1)) for e in events):
            raise ConversionError('Invalid bounded X68000 qualification inputs.')
        event_file.write_text(''.join(' '.join(map(str,event))+'\n' for event in events),encoding='ascii')
        # Every conversion starts with an unlearned, fresh CPU reference.
        probe=work/'reference'
        if probe.exists():
            import tempfile
            probe=Path(tempfile.mkdtemp(prefix='reference-',dir=work))
        executable=reference.prepare_bundle(probe,list(source.disks),manifest.firmware.ipl.path,manifest.firmware.cgrom.path,generic,title=title,ram_mib=x68_ram)
        emit('X68000: fresh reference and discovery of RAM/IPL code.')
        rule_args=['--auto-disk'] if automatic_disk_changes(source) else []
        expected=replay(executable,checks/'reference',count,event_file,reference=True,observe=True,extra=rule_args)
        observations=json.loads((checks/'reference/observations.json').read_text());observations['source_identity']=manifest.sha256
        from .x68000_scan import exploration_routes, long_routes
        from .library import library_root
        summary=library_root('x68')/manifest.sha256/'compilation.json'
        try:remembered=json.loads(summary.read_text()).get('mouse_controls') is True
        except (OSError,ValueError,AttributeError):remembered=False
        # A reviewed exact set follows the mouse list. Other sets are found by
        # their own code: loaded code that reads the mouse lengthens the mouse
        # route, and at least MOUSE_GAME_READS reads executed on fresh routes
        # turn on the player's mouse controls. A game confirmed by an earlier
        # conversion of the same exact set keeps them in a shorter scan.
        listed=listed_mouse(source)
        mouse_code,mouse_calls=mouse_reads(observations)
        mouse_route=listed if listed is not None else mouse_code or remembered
        # The scan level chooses the discovery routes: quick keeps the main
        # route only, standard adds mouse and keyboard exploration, extended
        # one 18,000-frame pseudo-random route, thorough the three 36,000-frame
        # routes that qualified the library. Every level keeps the fresh
        # native/reference comparison on each route it runs.
        routes=tuple(exploration_routes(count,mouse_controls=mouse_route)) if scan['exploration'] else ()
        if scan['long_count']:
            routes+=tuple(long_routes(manifest.sha256,mouse_controls=mouse_route,
                                      count=scan['long_count'],frames=scan['long_frames']))
        emit(f'X68000 scan level {level}: {len(routes)} exploration routes besides the main route.')
        # Every route is an independent cold boot in its own folder, so the
        # replays run side by side within this game's share of the host CPUs
        # (the same budget as its compiler jobs). Observations are merged in
        # route order afterwards, exactly as the sequential loop did.
        workers=route_workers(len(routes))
        extra_routes=[]
        for route in routes:
            folder=checks/('reference-'+route.name)
            ref=reference.prepare_bundle(folder,list(source.disks),manifest.firmware.ipl.path,
                manifest.firmware.cgrom.path,generic,title=title,ram_mib=x68_ram)
            inputs=folder/'inputs.tsv'
            inputs.write_text(''.join(' '.join(map(str,e))+'\n' for e in route.events),encoding='ascii')
            emit('X68000: independent '+route.name+' exploration ('+str(route.frames)+' frames).')
            extra_routes.append((route,folder,inputs,ref))
        if workers>1:
            emit(f'X68000: replaying {len(routes)} exploration routes, {workers} at a time.')
        run_routes(((ref,folder,route.frames,inputs,dict(reference=True,observe=True,extra=rule_args))
                    for route,folder,inputs,ref in extra_routes),workers)
        for route,folder,inputs,_ in extra_routes:
            more=json.loads((folder/'observations.json').read_text())
            mouse_calls+=mouse_reads(more)[1]
            observations,_=extend_observations(observations,more)
        mouse_game=listed if listed is not None else mouse_calls>=MOUSE_GAME_READS or remembered
        emit('X68000: mouse controls '+('on' if mouse_game else 'off')+
             (' (reviewed list)' if listed is not None else '')+
             f'; {mouse_calls} mouse reads on fresh routes.')
        extra_routes=[(route,folder,inputs) for route,folder,inputs,_ in extra_routes]
        # Exact-input observations improve discovery, never waive the fresh
        # independent comparison above or the standalone replay below.
        memory=ROOT/'datas/x68000-development'/manifest.sha256
        for record_name,proof_name in (('observations.json','qualification.json'),
                                       ('converter-observations.json','converter-qualification.json')):
            previous=memory/record_name;proof=memory/proof_name
            if not previous.is_file() or not proof.is_file():continue
            receipt=json.loads(proof.read_text())
            if receipt.get('source_identity')==manifest.sha256 and receipt.get('observations_sha256')==digest(previous):
                observations['variants'] += [{'pc':pc,'words':words,'hits':1} for pc,words in native.observations([previous])]
        for row in records('x68',manifest.sha256,13):
            end=row.address+len(row.data)
            if (not row.address&1 and 2<=len(row.data)<=16 and len(row.data)%2==0
                    and (0<=row.address<end<=0xc00000 or 0xe00000<=row.address<end<=0xe80000 or
                         0xea0000<=row.address<end<=0xea2000 or 0xfc0000<=row.address<end<=0x1000000)):
                observations['variants'].append({'pc':row.address,'words':row.data.hex(),'hits':1})
        observations=compact_observations(observations)
        observation=work/'discovered.json';atomic_json(observation,observations)
        project=work/'native';payload_dir=work/'payload';payload_dir.mkdir(parents=True,exist_ok=True)
        from .artwork import prepare_icon
        artwork={'embedded':False,'source':'missing','online_enabled':False}
        artwork=prepare_icon(payload_dir,source.path,title,payload_dir,explicit=Path(cover) if cover else None,
            online=online_cover,enabled=use_cover,system_id='x68',cache_directory=boxart_cache_directory('x68'),emit=emit)
        metadata=payload(payload_dir,source,manifest,title,artwork,mouse_game)
        candidate=None;actual=None;generation=None
        for attempt in range(max(1,min(int(passes),10))):
            generation=native.generate(project,native.observations([observation]),ROOT/'.deps/px68k-reference',native.source_receipts([observation]))
            candidate=build_player(project,payload_dir,emit=emit,machine=machine_settings,sdk=sdk)
            # Run copied alone, with only its own embedded immutable inputs.
            run_dir=checks/f'native-{attempt+1}';run_dir.mkdir(parents=True,exist_ok=True)
            exported=run_dir/candidate.name;shutil.copy2(candidate,exported)
            if os.name!='nt':exported.chmod(0o755)
            emit('X68000: comparing the standalone export with the fresh reference.')
            state_frame=count-800
            actual=replay(exported,run_dir,count,event_file,observe=True,extra=['--state-save-at',str(state_frame)])
            if (run_dir/'trace.tsv').read_bytes()!=(checks/'reference/trace.tsv').read_bytes():
                raise ConversionError('X68000 native/reference CPU, memory, image or PCM diverged; existing export preserved.')
            if not actual['nonzero_samples'] or not actual['nonblack_frames']:
                raise ConversionError('X68000 validation did not produce usable picture and PCM.')
            fallback=actual['reference_ram']+actual['reference_ipl']
            additional=[]
            prepared=[]
            for route,ref_folder,inputs in extra_routes:
                folder=run_dir/route.name;folder.mkdir()
                target=folder/candidate.name;shutil.copy2(candidate,target)
                if os.name!='nt':target.chmod(0o755)
                prepared.append((route,ref_folder,folder,target,inputs))
            results=run_routes(((target,folder,route.frames,inputs,dict(observe=True))
                                for route,ref_folder,folder,target,inputs in prepared),workers)
            for (route,ref_folder,folder,target,inputs),result in zip(prepared,results):
                if (folder/'trace.tsv').read_bytes()!=(ref_folder/'trace.tsv').read_bytes():
                    raise ConversionError('X68000 '+route.name+' native/reference trace diverged; existing export preserved.')
                fallback+=result['reference_ram']+result['reference_ipl']
                additional.append((route,folder,result))
            if not fallback:break
            emit(f'X68000: {fallback} fallback instructions observed; extending guarded code coverage.')
            more=json.loads((run_dir/'observations.json').read_text())
            observations,progress=extend_observations(observations,more)
            for route,folder,result in additional:
                observations,changed=extend_observations(observations,json.loads((folder/'observations.json').read_text()))
                progress=progress or changed
            if not progress:
                emit('X68000: no new guarded encodings; remaining interpreter use stays reported.')
                break
            atomic_json(observation,observations)
        # Snapshot loading is checked in a genuinely fresh standalone process.
        restart=checks/'restart';restart.mkdir(exist_ok=True);fresh=restart/candidate.name;shutil.copy2(candidate,fresh)
        if os.name!='nt':fresh.chmod(0o755)
        resumed=replay(fresh,restart,400,event_file,extra=['--state-load-start','--state-slot',next((checks/f'native-{attempt+1}'/'datas/games').glob('x68-*'))/'quick.rrstate'])
        rows=(run_dir/'trace.tsv').read_text().splitlines();rest=(restart/'trace.tsv').read_text().splitlines()
        if any(a.split('\t')[1:]!=b.split('\t')[1:] for a,b in zip(rest[2:],rows[state_frame+2:state_frame+401])):
            raise ConversionError('X68000 F9 continuation differs from its saved timeline.')
        # Also exercise an early floppy DMA, before the game loop. A missing
        # CPU reset latch used to change one transfer byte after a cold F9.
        boot=checks/'boot';boot.mkdir();boot_exe=boot/candidate.name;shutil.copy2(candidate,boot_exe)
        replay(boot_exe,boot,200,event_file,extra=['--state-save-at','120'])
        boot_rows=(boot/'trace.tsv').read_text().splitlines()
        if boot_rows!=(checks/'reference/trace.tsv').read_text().splitlines()[:201]:
            raise ConversionError('X68000 early boot differs from the fresh reference.')
        boot_restart=checks/'boot-restart';boot_restart.mkdir();boot_exe=boot_restart/candidate.name;shutil.copy2(candidate,boot_exe)
        boot_slot=next((boot/'datas/games').glob('*/quick.rrstate'))
        replay(boot_exe,boot_restart,40,event_file,extra=['--state-load-start','--state-slot',boot_slot])
        boot_rest=(boot_restart/'trace.tsv').read_text().splitlines()
        if any(a.split('\t')[1:]!=b.split('\t')[1:] for a,b in zip(boot_rest[2:],boot_rows[122:161])):
            raise ConversionError('X68000 early floppy DMA changes after F9.')
        manifest.verify_sources()
        total=actual['native_ram']+actual['native_ipl']+actual['reference_ram']+actual['reference_ipl']
        fallback=actual['reference_ram']+actual['reference_ipl']
        check={'frames':count,'native_entries':total-fallback,'interpreted_opcodes':fallback,
               'interpreter_percent':100*fallback/max(1,total),'reference_match':True,'state_restart_match':True,
               'state_frame':state_frame,'boot_frames':200,'boot_state_restart_match':True}
        exploration_checks=[]
        for route,folder,result in additional:
            native_count=result['native_ram']+result['native_ipl']
            interpreted=result['reference_ram']+result['reference_ipl']
            exploration_checks.append({'route':route.name,'frames':route.frames,'native_entries':native_count,
                'interpreted_opcodes':interpreted,'interpreter_percent':100*interpreted/max(1,native_count+interpreted),
                'reference_match':True,'trace_sha256':digest(folder/'trace.tsv'),
                'automatic_disk_changes':result.get('automatic_disk_changes',0),
                'media_events':result.get('media_events',[])})
        report={'tool':'Retro-Recomp','version':__version__,'created_utc':datetime.now(timezone.utc).isoformat(),
          'system':{'id':'x68','name':'Sharp X68000'},'status':'experimental','private_development_only':False,
          'target':target_id(),'rom':source.metadata(),'machine':manifest.local_record(),'source_identity':manifest.sha256,'qualification_directory':str(checks),
          'source_rom':str(source.path),'executable':executable_name(title),'build_executable':str(candidate),'toolchain':toolchain_description(),
          'embedded_rom':True,'static_sdl':True,'linked_machine_runtime':True,'no_external_firmware_required_after_export':True,
          'native_validation':{'passed':True,'scope':'fresh same-machine CPU/RAM/video/PCM reference; bounded joystick, mouse and keyboard routes','generation':generation},
          'native_coverage':'observed exact RAM/text-VRAM/SCSI-ROM/IPL encodings with live word guards','final_checks':[check,*exploration_checks],
          'qualification_inputs_sha256':digest(event_file),'automatic_disk_requests':automatic_disk_changes(source),
          'exploration_checks':exploration_checks,'scan_level':level,
          'mouse_controls':{'enabled':mouse_game,'listed':listed,'mouse_reads':mouse_calls,
                            'mouse_code_loaded':mouse_code,'remembered':remembered},
          'automatic_disk_changes_observed':actual.get('automatic_disk_changes',0),
          'media_events':actual.get('media_events',[]),
          'reference_vdp_trace_match':True,'runtime_feedback':feedback,'artwork':artwork,'windows_metadata':metadata,
          'game_states':{'supported':True,'save_key':'F8','load_key':'F9','fresh_process_verified':True},
          'video_model':{'standard':'native','frameskip':False,'fps':actual['fps']},
          'runtime_data':{'directory':'datas','shared_config':'datas/Retro-Recomp.ini','game_directory':'datas/games/x68-'+manifest.sha256},
          'hardware_accuracy_validated':False,'full_game_validated':False,'latency_ms':None}
        atomic_json(output/'conversion-report.json',report)
        memory.mkdir(parents=True,exist_ok=True)
        shutil.copy2(observation,memory/'converter-observations.json')
        atomic_json(memory/'converter-qualification.json',{'schema':1,'private_only':True,'source_identity':manifest.sha256,
                    'check':check,'sdk':stamp,'observations_sha256':digest(observation)})
        summary.parent.mkdir(parents=True,exist_ok=True)
        atomic_json(summary,{
            'schema':1,'title':title,'system':'x68','source_identity':manifest.sha256,
            'rom_sha256':source.sha256,'guarded_variants':len(native.observations([observation])),
            'private_development_only':True,'fresh_reference_passed':True,
            # Only observed reads are remembered, never the reviewed list's choice.
            'mouse_controls':mouse_calls>=MOUSE_GAME_READS or remembered})
        emit('X68000: validated standalone player ready (experimental profile).')
        return candidate
