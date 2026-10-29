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
import tempfile
import time
from . import __version__, timings
from .conversion_common import check_exit, resolve_scan_level, spawn, write_if_changed
from .conversion_gates import continuation_difference, require, require_equal, require_same_file
from .paths import ROOT, ASSETS, boxart_cache_directory
from .core import ConversionError, toolchain, run, executable_name
from .platforms import build_jobs, cmake_target_args, build_executable, target_id, sdl_install
from .toolchain import describe as toolchain_description, suffix as toolchain_suffix
from .library import atomic_json, entry_lock, file_sha256, library_root
from .report_schema import write_report
from .x68000 import (developer_available, machine, automatic_disk_changes, mouse_reads, listed_mouse,
                     MOUSE_GAME_READS)


digest = file_sha256


def compact_observations(record, ipl=None):
    """Merge exact encodings without duplicating the previous qualification.

    A fresh replay is still mandatory. Large generated blitters can contribute
    over 160,000 variants; appending the same learned list on regeneration used
    to exceed the observation-file bound despite adding no new instruction.

    With the player's `ipl`, the variants that equal its bytes become span entries (schema 2): the file then
    keeps where IPL code starts and none of its words. Without it, spans already in the record are kept as they are.
    """
    if record.get('schema') not in (1,2) or record.get('truncated') is not False:
        raise ConversionError('Incomplete X68000 observations cannot be qualified.')
    merged={}
    for row in record['variants']:
        key=(row['pc'],row['words']);hits=row.get('hits',1)
        merged[key]=max(merged.get(key,1),hits)
        if len(merged)>1048576:raise ConversionError('X68000 instruction observation bound exceeded.')
    result=dict(record)
    result['variants']=[{'pc':pc,'words':words,'hits':hits} for (pc,words),hits in sorted(merged.items())]
    if ipl is not None or record.get('spans'):
        from tools.x68000_native import fold_ipl
        try:result['variants'],spans=fold_ipl(result['variants'],ipl,record.get('spans',()))
        except ValueError as error:raise ConversionError(str(error)) from None
        result.pop('spans',None)
        if spans:result['spans']=spans;result['schema']=2
    return result


def observation_size(record):
    """Variants plus span entries: what a generation can still gain."""
    return len(record['variants'])+sum(len(span['entries']) for span in record.get('spans',()))


def extend_observations(record, extra, ipl=None):
    """Only new exact encodings justify another native generation.

    A saturated fallback capture must not lose its truncation flag when merged
    into a complete reference capture. Counts alone never add CPU coverage.
    """
    current=compact_observations(record,ipl)
    incoming=compact_observations(extra,ipl)
    if incoming.get('source_identity') not in (None,current.get('source_identity')):
        raise ConversionError('X68000 additional observations have a different source identity.')
    merged=compact_observations({**current,'variants':current['variants']+incoming['variants'],
                                 'spans':[*current.get('spans',()),*incoming.get('spans',())]},ipl)
    return merged,observation_size(merged)>observation_size(current)


# Private conversion memory. Its key is the game (X68000Input.game_key, the hash of the ordered disk set), the
# same key as the report's rom.sha256, the export's marker, the collection and the runtime feedback:
#   <library>/x68/<game>/compilation.json                          summary (Memory view, remembered mouse use)
#   <library>/x68/<game>/<machine16>/converter-observations.json   observed guest code of one machine
#   <library>/x68/<game>/<machine16>/converter-qualification.json  its receipt
# <machine16> is the start of X68000Manifest.sha256: disks + the player's IPL + font ROM + RAM size, the identity
# of the executable (states, saved data) and of the observations (they hold IPL words). Places used before 1.6.0
# (the converter folder's datas/x68000-development, the summary under the machine hash) are not read any more:
# backward compatibility is owed to the previous release only.
OBSERVATION_FILES=('converter-observations.json','converter-qualification.json')


def _read_observations(native, paths, ipl):
    """The (pc, words) of observation files, or a ConversionError that says why they cannot be read. The files
    are left as they are: a newer converter's format or the spans of another IPL are refused, never rewritten."""
    try:
        return native.observations(paths,ipl)
    except ValueError as error:
        raise ConversionError('X68000 observations cannot be read with this IPL or by this converter (a newer '
                              f'format, or spans of another IPL); they are kept unchanged: {error}') from error


def game_entry(source):
    return library_root('x68')/source.game_key


def machine_memory(source, manifest):
    return game_entry(source)/manifest.sha256[:16]


def _copy_file(source, target):
    # Durable like atomic_json: the bytes reach the disk before the name does, so a power cut never leaves a
    # complete-looking but empty copy, and Windows readers or scanners holding the target are waited for.
    target.parent.mkdir(parents=True,exist_ok=True)
    descriptor,name=tempfile.mkstemp(prefix=target.name+'.',suffix='.tmp',dir=target.parent)
    try:
        with os.fdopen(descriptor,'wb') as out, open(source,'rb') as data:
            shutil.copyfileobj(data,out,1024*1024)
            out.flush();os.fsync(out.fileno())
        deadline=time.monotonic()+2
        while True:
            try:
                os.replace(name,target);break
            except PermissionError as error:
                if getattr(error,'winerror',None) not in (5,32,33) or time.monotonic()>=deadline:raise
                time.sleep(0.05)
    finally:
        if os.path.exists(name):os.unlink(name)


def reusable_observations(folder, manifest, names=OBSERVATION_FILES):
    """The observation file of `folder` when its receipt names this machine and this very file, else None.

    The receipt's `sdk` stamp is stored and deliberately not compared: observations are facts about the guest
    program (addresses and instruction words), never trusted without the fresh comparison every conversion
    runs, and a stamp check would discard them at each engine change for no gain in soundness."""
    previous=folder/names[0];proof=folder/names[1]
    if not previous.is_file() or not proof.is_file():return None
    try:receipt=json.loads(proof.read_text())
    except (OSError,ValueError):return None
    if (isinstance(receipt,dict) and receipt.get('source_identity')==manifest.sha256
            and receipt.get('observations_sha256')==digest(previous)):return previous
    return None


HISSORII_REPOSITORY='https://github.com/hissorii/px68k.git'
# Generators the SDK stamp covers; bundled as data beside their modules. The stamp reads them through the
# manifest (retrorecomp/stamp_inputs.py lists them as 'tools/<name>' for the X68000), with the shared 68000
# sources and code generators the SDK copies into every X68000 CPU.
SDK_TOOLS=('x68000_native.py','x68000_reference.py','x68000_reference_check.py','x68000_base74.py',
           'x68000_state_hardware.py')


def sdk_stamp(part=None):
    """The SDK build identity; part='game' leaves out the player shell
    (rrhk_x68k.inc and host inputs), for upgrades without rediscovery.

    Every file of the SDK comes from the listed X68000 inputs (one explicit manifest, text with normalised
    line ends): nothing is globbed from native/x68000_* and a missing file is an error. The machine base
    (RR_X68000_MACHINE_BASE, checked to be hissorii or current) is the only other input."""
    from .compilation_inputs import engine_stamp, role_stamps
    from tools.x68000_native import MACHINE_BASE
    value=hashlib.sha256(b'x68000-sdk-v2\0')
    value.update((role_stamps('x68')['game'] if part=='game' else engine_stamp('x68')).encode())
    value.update(b'\0machine-base\0'+MACHINE_BASE.encode())
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
    # The player's feedback file is the game's (the disk set), not the machine's: players with another IPL or
    # font ROM then record for, and later share, the same game. Saves and states keep the machine identity above.
    (project/'runtime_feedback_config.h').write_text(
        '#define RR_FEEDBACK_SYSTEM "x68"\n#define RR_FEEDBACK_IDENTITY "'+source.game_key+'"\n',encoding='ascii')
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
        write_if_changed(target/source.relative_to(ASSETS), source.read_bytes())
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
    with timings.phase('reference_runs' if any(job[4].get('reference') for job in jobs) else 'native_runs'):
        if workers<=1 or len(jobs)<=1:
            return [replay(binary,folder,frames,events,**options) for binary,folder,frames,events,options in jobs]
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=workers,thread_name_prefix='x68000-route') as pool:
            futures=[pool.submit(replay,binary,folder,frames,events,**options)
                     for binary,folder,frames,events,options in jobs]
            return [future.result() for future in futures]


def continues(timeline, resumed, saved_at, frames):
    """Whether a fresh process that loaded the state saved at frame `saved_at` continues the timeline it was saved from.

    `timeline` and `resumed` are the lines of the two traces (a header line, then one line per frame); `resumed` ran
    `frames` frames, frame 0 being the load itself. Its frames 1 to `frames - 1` must equal the frames that follow
    `saved_at` in the timeline, the frame number (the first column) apart: a resumed process counts from zero. Both
    traces went through validate_trace, so they have the rows this expects.
    """
    columns = lambda lines: [line.split('\t')[1:] for line in lines]
    return continuation_difference(columns(timeline), columns(resumed[2:]), saved_at + 2, frames - 1) is None


def replay(binary, folder, frames, events, *, reference=False, observe=False, extra=()):
    from tools.x68000_reference_check import validate_trace
    folder.mkdir(parents=True,exist_ok=True)
    args=[str(binary),'--headless','--frames',str(frames),'--report',str(folder/'result.json'),
          '--trace',str(folder/'trace.tsv'),'--capture',str(folder/'frame.ppm'),'--input-events',str(events)]
    if reference:args+=['--reference-cpu']
    if observe:args+=['--observations',str(folder/'observations.json')]
    args+=list(map(str,extra))
    with (folder/'stdout.log').open('wb') as out,(folder/'stderr.log').open('wb') as err:
        # No console window per validation run in the windowed converter (spawn).
        result=spawn(args,cwd=folder,timeout=max(360,frames//3),stdout=out,stderr=err)
    check_exit(result,lambda _:ConversionError('X68000 replay failed: '+(folder/'stderr.log').read_text(encoding='utf-8',errors='replace')[-2000:]))
    report=json.loads((folder/'result.json').read_text());validate_trace(folder/'trace.tsv',frames)
    if report.get('core_error') or report['frames']!=frames or report['hardware']['audio_errors']:
        raise ConversionError('X68000 validation returned an incomplete/error run.')
    return report


def convert(path, *, x68_ipl=None,x68_cgrom=None,x68_ram=2,title=None,output=None,cover=None,
            use_cover=True,online_cover=True,passes=3,frames=4000,scan_level=None,emit=print,
            qualification_events=None,**unused):
    if not developer_available():raise ConversionError('The X68000 converter files are missing from this installation.')
    started=time.perf_counter()
    from .scan_levels import x68000_budget
    level=resolve_scan_level(scan_level)
    scan=x68000_budget(level)
    if unused.get('standard_override') not in (None,'native','auto'):
        raise ConversionError('X68000 timing follows its CRTC; PAL/NTSC overrides do not apply.')
    source,manifest=machine(path,x68_ipl,x68_cgrom,x68_ram)
    # The player's own IPL: observed IPL code is kept as span entries over these bytes, never as words.
    ipl=manifest.firmware.ipl.path.read_bytes()
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
    # Feedback belongs to the game. Exports of 1.5 and earlier recorded it under the machine hash: still read.
    feedback=ingest('x68',source.game_key,output,emit=emit)
    sdk=native.SDK=sdk_tree(base)
    machine_settings=machine_sources(base,emit)
    with entry_lock(base/'discovery-lock',timeout=1800):
        common=base/'discovery';ready=common/'ready.json'
        generic=Path(json.loads(ready.read_text())['executable']) if ready.exists() else None
        if not generic or not generic.is_file():
            with timings.phase('code_generation'):
                native.generate(common,[],ROOT/'.deps/px68k-reference')
            with timings.phase('compile'):
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
        with timings.phase('reference_runs'):
            expected=replay(executable,checks/'reference',count,event_file,reference=True,observe=True,extra=rule_args)
        observations=json.loads((checks/'reference/observations.json').read_text());observations['source_identity']=manifest.sha256
        from .x68000_scan import exploration_routes, long_routes
        summary=game_entry(source)/'compilation.json'
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
            observations,_=extend_observations(observations,more,ipl)
        mouse_game=listed if listed is not None else mouse_calls>=MOUSE_GAME_READS or remembered
        emit('X68000: mouse controls '+('on' if mouse_game else 'off')+
             (' (reviewed list)' if listed is not None else '')+
             f'; {mouse_calls} mouse reads on fresh routes.')
        extra_routes=[(route,folder,inputs) for route,folder,inputs,_ in extra_routes]
        # Exact-input observations improve discovery, never waive the fresh
        # independent comparison above or the standalone replay below.
        memory=machine_memory(source,manifest)
        previous=reusable_observations(memory,manifest,OBSERVATION_FILES)
        if previous:
            observations['variants'] += [{'pc':pc,'words':words,'hits':1} for pc,words in _read_observations(native,[previous],ipl)]
        for row in records('x68',source.game_key,13):
            end=row.address+len(row.data)
            if (not row.address&1 and 2<=len(row.data)<=16 and len(row.data)%2==0
                    and (0<=row.address<end<=0xc00000 or 0xe00000<=row.address<end<=0xe80000 or
                         0xea0000<=row.address<end<=0xea2000 or 0xfc0000<=row.address<end<=0x1000000)):
                observations['variants'].append({'pc':row.address,'words':row.data.hex(),'hits':1})
        observations=compact_observations(observations,ipl)
        observation=work/'discovered.json';atomic_json(observation,observations)
        project=work/'native';payload_dir=work/'payload';payload_dir.mkdir(parents=True,exist_ok=True)
        from .artwork import prepare_icon
        artwork={'embedded':False,'source':'missing','online_enabled':False}
        artwork=prepare_icon(payload_dir,source.path,title,payload_dir,explicit=Path(cover) if cover else None,
            online=online_cover,enabled=use_cover,system_id='x68',cache_directory=boxart_cache_directory('x68'),emit=emit)
        metadata=payload(payload_dir,source,manifest,title,artwork,mouse_game)
        candidate=None;actual=None;generation=None
        for attempt in range(max(1,min(int(passes),10))):
            timings.begin_pass(attempt+1)
            with timings.phase('code_generation'):
                generation=native.generate(project,_read_observations(native,[observation],ipl),ROOT/'.deps/px68k-reference',native.source_receipts([observation]))
            with timings.phase('compile'):
                candidate=build_player(project,payload_dir,emit=emit,machine=machine_settings,sdk=sdk)
            # Run copied alone, with only its own embedded immutable inputs.
            run_dir=checks/f'native-{attempt+1}';run_dir.mkdir(parents=True,exist_ok=True)
            exported=run_dir/candidate.name;shutil.copy2(candidate,exported)
            if os.name!='nt':exported.chmod(0o755)
            emit('X68000: comparing the standalone export with the fresh reference.')
            state_frame=count-800
            with timings.phase('native_runs'):
                actual=replay(exported,run_dir,count,event_file,observe=True,extra=['--state-save-at',str(state_frame)])
            require_same_file(run_dir/'trace.tsv',checks/'reference/trace.tsv',
                lambda:ConversionError('X68000 native/reference CPU, memory, image or PCM diverged; existing export preserved.'))
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
                require_same_file(folder/'trace.tsv',ref_folder/'trace.tsv',
                    lambda:ConversionError('X68000 '+route.name+' native/reference trace diverged; existing export preserved.'))
                fallback+=result['reference_ram']+result['reference_ipl']
                additional.append((route,folder,result))
            if not fallback:break
            emit(f'X68000: {fallback} fallback instructions observed; extending guarded code coverage.')
            more=json.loads((run_dir/'observations.json').read_text())
            observations,progress=extend_observations(observations,more,ipl)
            for route,folder,result in additional:
                observations,changed=extend_observations(observations,json.loads((folder/'observations.json').read_text()),ipl)
                progress=progress or changed
            if not progress:
                emit('X68000: no new guarded encodings; remaining interpreter use stays reported.')
                break
            atomic_json(observation,observations)
        timings.end_passes()
        # Snapshot loading is checked in a genuinely fresh standalone process.
        restart=checks/'restart';restart.mkdir(exist_ok=True);fresh=restart/candidate.name;shutil.copy2(candidate,fresh)
        if os.name!='nt':fresh.chmod(0o755)
        with timings.phase('state_checks'):
            resumed=replay(fresh,restart,400,event_file,extra=['--state-load-start','--state-slot',next((checks/f'native-{attempt+1}'/'datas/games').glob('x68-*'))/'quick.rrstate'])
        rows=(run_dir/'trace.tsv').read_text().splitlines();rest=(restart/'trace.tsv').read_text().splitlines()
        require(continues(rows,rest,state_frame,400),lambda:ConversionError('X68000 F9 continuation differs from its saved timeline.'))
        # Also exercise an early floppy DMA, before the game loop. A missing
        # CPU reset latch used to change one transfer byte after a cold F9.
        boot=checks/'boot';boot.mkdir();boot_exe=boot/candidate.name;shutil.copy2(candidate,boot_exe)
        with timings.phase('state_checks'):
            replay(boot_exe,boot,200,event_file,extra=['--state-save-at','120'])
        boot_rows=(boot/'trace.tsv').read_text().splitlines()
        require_equal(boot_rows,(checks/'reference/trace.tsv').read_text().splitlines()[:201],
                      lambda:ConversionError('X68000 early boot differs from the fresh reference.'))
        boot_restart=checks/'boot-restart';boot_restart.mkdir();boot_exe=boot_restart/candidate.name;shutil.copy2(candidate,boot_exe)
        boot_slot=next((boot/'datas/games').glob('*/quick.rrstate'))
        with timings.phase('state_checks'):
            replay(boot_exe,boot_restart,40,event_file,extra=['--state-load-start','--state-slot',boot_slot])
        boot_rest=(boot_restart/'trace.tsv').read_text().splitlines()
        require(continues(boot_rows,boot_rest,120,40),lambda:ConversionError('X68000 early floppy DMA changes after F9.'))
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
          # Null, like the shapes that run no VDP comparison: the key was a constant True that compared nothing.
          'reference_vdp_trace_match':None,'runtime_feedback':feedback,'artwork':artwork,'windows_metadata':metadata,
          'game_states':{'supported':True,'save_key':'F8','load_key':'F9','fresh_process_verified':True},
          'video_model':{'standard':'native','frameskip':False,'fps':actual['fps']},
          'runtime_data':{'directory':'datas','shared_config':'datas/Retro-Recomp.ini','game_directory':'datas/games/x68-'+manifest.sha256},
          'hardware_accuracy_validated':False,'full_game_validated':False,'latency_ms':None,
          'conversion_wall_seconds':round(time.perf_counter()-started,3)}
        write_report(output/'conversion-report.json',report)
        # Written in the library, whatever folder the earlier ones were read from (that one is left as it is).
        memory=machine_memory(source,manifest)
        with entry_lock(memory,timeout=1800):
            _copy_file(observation,memory/OBSERVATION_FILES[0])
            atomic_json(memory/OBSERVATION_FILES[1],{'schema':1,'private_only':True,'source_identity':manifest.sha256,
                        'game':source.game_key,'check':check,'sdk':stamp,'observations_sha256':digest(observation)})
        summary.parent.mkdir(parents=True,exist_ok=True)
        # Two machines of one game share this summary: written under the game's lock, keeping a mouse use that
        # the other machine remembered meanwhile.
        with entry_lock(summary.parent,timeout=1800):
            try:
                current=json.loads(summary.read_text(encoding='utf-8'))
                remembered=remembered or (isinstance(current,dict) and current.get('mouse_controls') is True)
            except (OSError,ValueError):
                pass
            atomic_json(summary,{
                'schema':1,'title':title,'system':'x68','game':source.game_key,'source_identity':manifest.sha256,
                'rom_sha256':source.sha256,'guarded_variants':len(native.observations([observation],ipl)),
                'private_development_only':True,'fresh_reference_passed':True,
                # Only observed reads are remembered, never the reviewed list's choice.
                'mouse_controls':mouse_calls>=MOUSE_GAME_READS or remembered})
        emit('X68000: validated standalone player ready (experimental profile).')
        return candidate
