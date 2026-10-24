"""Neo Geo native/reference qualification with user-built private inputs.

Matches the original Geolith CPU control calls against our adapter. This is
integration validation within one hardware family, not hardware accuracy proof.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from retrorecomp.platforms import build_executable, cmake_target_args, sdl_install
from retrorecomp.core import run,toolchain
from retrorecomp.neogeo_build import prepare_project
from retrorecomp.neogeo_validation import FIELDS, qualification_routes, compare

def check_presentation(executable: Path,output: Path,summary: dict,frames=600):
    env=os.environ.copy();env.update(SDL_VIDEODRIVER='dummy',SDL_AUDIODRIVER='dummy')
    report=output/'sdl-dummy.json';start=time.monotonic()
    result=subprocess.run([str(executable),'--frames',str(frames),'--report',str(report)],env=env,capture_output=True,timeout=max(45,frames/59+30))
    if result.returncode:raise RuntimeError(f'SDL: exit {result.returncode}, {result.stderr[-2000:]!r}')
    data=json.loads(report.read_text(encoding='utf-8'))
    summary['sdl_dummy']={'frames':frames,'process_seconds':time.monotonic()-start,
        'loop_seconds':data['loop_wall_seconds'],'expected_seconds':frames/59.185606,
        'audio_empty_queue_frames':data['audio_empty_queue_frames'],
        'audio_queue_peak_bytes':data.get('audio_queue_peak_bytes'),
        'dummy_clock_is_not_calibrated':True}
    if data['frames']!=frames or not data['pcm_samples'] or data['interpreted_68000'] or data['interpreted_z80']:
        raise RuntimeError('Missing SDL guest audio output.')
    summary['sdl_dummy']['nonzero_samples']=data['nonzero_samples']
    if not data['nonzero_samples']:
        # Some cartridges intentionally remain silent during the BIOS/intro.
        # Keep the cold measurement and also require actual sound through SDL
        # on the already compared controller route after startup.
        state=output/'sdl-active-start.rrstate';warmup=output/'sdl-active-warmup.json'
        script=output/'play.inputs'
        result=subprocess.run([str(executable),'--headless','--frames','4500','--script',str(script),
            '--rtc-seed','1760000000','--report',str(warmup),'--save-state',str(state),'--save-at','4500'],
            capture_output=True,timeout=120)
        if result.returncode or not state.exists():raise RuntimeError('Missing settled SDL state.')
        warm=json.loads(warmup.read_text(encoding='utf-8'))
        if warm['interpreted_68000'] or warm['interpreted_z80']:raise RuntimeError('Fallback before settled SDL check.')
        report=output/'sdl-active.json'
        result=subprocess.run([str(executable),'--frames',str(frames),'--load-state',str(state),'--report',str(report)],
                              env=env,capture_output=True,timeout=max(45,frames/59+30))
        if result.returncode:raise RuntimeError(f'Settled SDL: exit {result.returncode}')
        active=json.loads(report.read_text(encoding='utf-8'))
        if (active['frames']!=4500+frames or not active['state_loaded'] or not active['nonzero_samples'] or
            active['interpreted_68000'] or active['interpreted_z80']):
            raise RuntimeError('Missing settled SDL audio output or native coverage.')
        summary['sdl_active']={'warmup_frames':4500,'frames':frames,'frame_index':active['frames'],'state_loaded':True,
            'nonzero_samples':active['nonzero_samples'],'audio_queue_peak_bytes':active['audio_queue_peak_bytes'],
            'audio_empty_queue_frames':active['audio_empty_queue_frames'],
            'loop_seconds':active['loop_wall_seconds'],'cold_start_silence_retained':True,
            'dummy_clock_is_not_calibrated':True}
    env['RETRORECOMP_HOST_TEST_NO_AUDIO']='1'
    report=output/'sdl-video-clock.json'
    result=subprocess.run([str(executable),'--frames',str(frames),'--report',str(report)],env=env,capture_output=True,timeout=max(45,frames/59+30))
    if result.returncode:raise RuntimeError(f'SDL video clock: exit {result.returncode}')
    data=json.loads(report.read_text(encoding='utf-8'))
    summary['sdl_video_clock']={'frames':frames,'loop_seconds':data['loop_wall_seconds'],
        'expected_seconds':frames/59.185606,'guest_pcm_samples':data['pcm_samples'],'device_clock_disabled':True}
    if abs(data['loop_wall_seconds']-frames/59.185606)>0.5:
        raise RuntimeError('Unexpected presentation cadence with dummy devices.')

def check(executable: Path,project: Path,output: Path,*,presentation_frames=600):
    output.mkdir(parents=True,exist_ok=True)
    original_sha=hashlib.sha256(executable.read_bytes()).hexdigest()
    manifest=json.loads((project/'input.json').read_text(encoding='utf-8'))
    set_name=manifest['source']['set'];routes=qualification_routes(set_name)
    plain=output/'plain-reference'
    prepare_project(plain,content=project/'cartridge.neo',bios=project/'bios.zip',title=manifest['prepared']['title'])
    cmake,generator=toolchain()
    run([cmake,'-S',plain,'-B',plain/'build','-G',generator,*cmake_target_args(),
         '-DRR_NG_PLAIN_REFERENCE=ON',f'-DCMAKE_PREFIX_PATH={sdl_install().as_posix()}'],log=plain/'build.log')
    run([cmake,'--build',plain/'build','--config','Release','--target','game','--parallel','4'],log=plain/'build.log')
    # Real input masks only: no guest-memory patching or function overrides.
    summary={'set':set_name,'input_identity':manifest['identity'],'routes':[],
             'plain_reference_scope':__doc__.strip(),'physical_latency_measured':False}
    for name,(frames,text) in routes.items():
        script=output/(name+'.inputs');script.write_text(text,encoding='ascii')
        reports=[]
        for label,binary in (('adapter',executable),('plain',build_executable(plain / 'build', 'game'))):
            report=output/f'{name}-{label}.json'
            arguments=[str(binary),'--headless','--frames',str(frames),'--script',str(script),'--report',str(report),
                       '--rtc-seed','1760000000']
            if label=='adapter':
                captures=output/(name+'-captures');captures.mkdir(exist_ok=True)
                arguments+=['--capture',str(captures),'--capture-every','300','--pcm',str(output/(name+'.pcm'))]
            completed=subprocess.run(arguments,capture_output=True,timeout=120)
            if completed.returncode:raise RuntimeError(f'{label}: exit {completed.returncode}, {completed.stderr[-2000:]!r}')
            reports.append(json.loads(report.read_text(encoding='utf-8')))
        differences=compare(reports[0],reports[1])
        for key in ('extended_cpu_hash','extended_hardware_hash'):
            if key in reports[0] and key in reports[1] and reports[0][key]!=reports[1][key]:
                raise RuntimeError('Neo Geo extended state mismatch: '+key)
        if not reports[0]['nonzero_samples'] or reports[0]['nonuniform_frames']<frames//2:
            raise RuntimeError('Missing image/audio output on the tested route.')
        row={'route':name,'frames':frames,'differences':differences,'passed':True,
             'main_native_instructions':reports[0]['native_68000'],
             'sound_native_instructions':reports[0]['native_z80'],
             'main_fallback':reports[0]['interpreted_68000'],'sound_fallback':reports[0]['interpreted_z80'],
             'bios_instructions':reports[0]['bios_instructions'],'m1_instructions':reports[0]['m1_instructions'],
             'sm1_instructions':reports[0]['sm1_instructions'],
             'native_bus_wait_events':reports[0]['bus_wait_clocks'],
             # Original CPU control calls bypass the adapter's wait counter;
             # its zero value cannot be presented as a no-wait measurement.
             'reference_bus_wait_events':None,'plain_reference_bus_counter_instrumented':False,
             'cpu_last_slice':{'native':[reports[0].get('cpu_slice_initial'),reports[0].get('cpu_slice_remaining')],
                              'reference':[reports[1].get('cpu_slice_initial'),reports[1].get('cpu_slice_remaining')],
                              'retired_clocks':reports[0].get('cpu_slice_clocks'),
                              'raw_counters_overwritten_at_next_execute':True},
             'bus_phase_accuracy_qualified':False}
        summary['routes'].append(row);print(json.dumps(row),flush=True)
    (output/'route-checks.json').write_text(json.dumps({**summary,'passed':False,'presentation_pending':True,
        'exe_sha256':original_sha},indent=2),encoding='utf-8')
    check_presentation(executable,output,summary,presentation_frames)
    if hashlib.sha256(executable.read_bytes()).hexdigest()!=original_sha:
        raise RuntimeError('Prototype executable changed during qualification.')
    summary.update(passed=True,exe_bytes=executable.stat().st_size,exe_sha256=original_sha)
    (output/'qualification.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    return summary

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('executable',type=Path);parser.add_argument('--project',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--presentation-frames',type=int,default=600)
    args=parser.parse_args()
    if not 600<=args.presentation_frames<=36000:parser.error('Presentation check accepts 600..36000 frames.')
    print(json.dumps(check(args.executable.resolve(),args.project.resolve(),args.output.resolve(),
                          presentation_frames=args.presentation_frames),indent=2))

if __name__=='__main__':main()
