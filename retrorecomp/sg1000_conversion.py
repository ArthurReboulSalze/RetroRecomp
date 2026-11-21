"""SG-1000 conversion (experimental, developer only): a cartridge translated by the banked Z80 chain, checked against the reference
interpreter. MIT, Retro-Recomp.

The steps: read the cartridge (sg1000_rom.py, plain ROM of 2 to 48 KiB); choose how the `play` route starts on the reference
(sg1000_routes, route_start); translate the cartridge and learn the code run from RAM on the routes of the scan level (sg1000_build.learn,
at most `passes` passes); run the native check and the reference on every route and REFUSE the conversion when any compared field differs
(CPU, RAM, VRAM, the picture of every frame, sound, PSG) or any frame's row differs; write the report (schema 2).

Not in this stage: the game executable (the player and its host-kit adapter come next). When the checks pass the report is written and
the work folder returned; the report says that nothing was delivered. The five measures stay apart: native code (the Z80 instructions run
natively and on the counted interpreter, in instructions and in cycles) and agreement with the reference on the routes played are
measured; hardware fidelity, gameplay and physical latency are not.
"""
from __future__ import annotations

import re
import time
from pathlib import Path

from .core import ConversionError

FRAMES = 3600                    # the batch's default route length (the profile's default_frames)
LIVENESS_FIELDS = {key: key for key in ('frames', 'distinct_pictures', 'picture_changes', 'last_picture_change_frame', 'audible_frames',
                                        'last_audible_frame', 'distinct_sound_blocks', 'distinct_ram_states',
                                        'distinct_program_counters')}
WATCH = (0xC000, 0xC001)         # the first RAM bytes: what a program keeps there is compared too
PAL_TAGS = re.compile(r'\((?:[^)]*[ ,])?(?:Europe|Australia|PAL)\b[^)]*\)', re.I)
NOT_DELIVERED = ('no game executable is delivered by this stage: the SG-1000 player and its host-kit adapter are not written yet; the '
                 'checks below are those of the translated cartridge run headless against the reference interpreter')


def proposed_standard(name: str) -> str:
    """'pal' for a file name labelled Europe, Australia or PAL (as the dumps of the common sets are), else 'ntsc'."""
    return 'pal' if PAL_TAGS.search(name) else 'ntsc'


def hardware_devices() -> list:
    """The `hardware_devices` of the common report: the video and the sound chip, C models of the runtime with no counter of their own."""
    common = {'translated_from_rom': False, 'hardware_fidelity_validated': False}
    return [{'id': 'tms9918a', 'kind': 'video_unit', 'mode': 'c_model',
             'details': {'display': 'line by line', 'interpreter': 'none: the video chip is C code in the runtime, not a CPU with a program',
                         **common}},
            {'id': 'sn76489a', 'kind': 'audio_unit', 'mode': 'c_model',
             'details': {'mixing_levels': 'stated, not validated',
                         'interpreter': 'none: the sound chip is C code in the runtime', **common}}]


def convert(path: Path, *, title=None, output=None, frames=FRAMES, passes=3, scan_level=None, standard_override=None, emit=print,
            **unused) -> Path:
    import hashlib
    from . import __version__, route_start, sg1000_build, sg1000_routes
    from .conversion_common import check_run_budget, resolve_scan_level
    from .core import ROOT
    from .delivery_evidence import liveness_summary, replay_routes, report_fields, require_moving_picture
    from .library import entry_lock
    from .report_schema import write_report
    from .sega_evidence import route_warnings
    from .sg1000_rom import read_cartridge
    from .toolchain import describe as toolchain_description
    started = time.perf_counter()
    try:
        cart = read_cartridge(path)
    except (OSError, ValueError) as error:
        raise ConversionError(str(error)) from None
    title = title or Path(path).stem
    if any(ord(c) < 32 for c in title) or len(title) > 160:
        raise ConversionError('Invalid SG-1000 game title.')
    standard = standard_override if standard_override in ('pal', 'ntsc') else proposed_standard(Path(path).name)
    level = resolve_scan_level(scan_level)
    frames, passes = int(frames or FRAMES), int(passes or 3)
    check_run_budget(passes, frames, 'SG-1000: a conversion runs 1 to 10 learning passes on routes of 1 to 10,000 frames.')
    if output is None:
        from .paths import games_directory
        output = games_directory(system_id='sg1000') / 'datas/reports' / cart.sha256
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    cartridge = sg1000_build.padded(cart.data)
    work = ROOT / '.build' / 'sg1000' / cart.sha256[:12]
    machine_args = ['--pal'] if standard == 'pal' else []
    watch = [w for a in WATCH for w in ('--watch', f'{a:04X}')]
    timings = {}
    try:
        with entry_lock(work, timeout=1800):
            folder = work / 'routes'
            folder.mkdir(parents=True, exist_ok=True)

            def options(name: str, count: int, text: str) -> list[str]:
                """A route's options for both programs: its length, its script."""
                script = folder / f'{name}.inputs'
                if not script.is_file() or script.read_text(encoding='ascii') != text:
                    script.write_text(text, encoding='ascii', newline='\n')
                return ['--frames', str(count), *watch, '--script', str(script)]

            def reference_rows(name: str, count: int, text: str) -> tuple[dict, Path]:
                rows = folder / f'{name}-reference.csv'
                return sg1000_build.run(reference_exe, [*machine_args, *options(name, count, text), '--rows', str(rows)], cartridge), rows

            # The start (route_start, as the MSX): each variant played on the reference against the route without input.
            phase = time.perf_counter()
            emit('SG-1000: building the reference interpreter.')
            reference_exe = sg1000_build.build_reference(work, emit)
            play_frames = max(frames, sg1000_routes.PLAY_FRAMES)
            seed = sg1000_routes.route_seed(cart.sha256, 'play')
            variants = sg1000_routes.candidates(play_frames)
            emit(f'SG-1000: choosing how the play route starts ({len(variants)} variants on the reference).')
            played = replay_routes([('baseline', None), *((f'start-{sg1000_routes.variant_name(v)}', v) for v in variants)],
                                   lambda row: reference_rows(row[0], play_frames, '' if row[1] is None else
                                                              sg1000_routes.script(sg1000_routes.events(play_frames, seed, row[1]))),
                                   workers=4)

            def pictures(rows: Path) -> dict:
                return {row.frame: row.picture for row in sg1000_build.frame_rows(rows)}
            baseline = pictures(played[0][1])
            results = {}
            for variant, (_result, rows) in zip(variants, played[1:]):
                mine = pictures(rows)
                results[variant] = {'liveness': report_fields(liveness_summary(sg1000_build.frame_rows(rows)), LIVENESS_FIELDS),
                                    'divergence': route_start.divergence(mine, baseline),
                                    'reach': route_start.reach(mine, baseline, sg1000_routes.walk_start(variant[1]),
                                                               sg1000_routes.QUIET_WALK)}
            chosen = route_start.choose_start(results, play_frames, sg1000_routes.variant_order)
            start_record = {'buttons': sg1000_routes.variant_name(chosen), 'presses': chosen[1],
                            'rule': 'alive until the last 120 frames, then most pictures the walk reached that no input showed, '
                                    'then most frames the input changed, then the fewest presses',
                            'variants': {sg1000_routes.variant_name(v): r for v, r in results.items()}}
            emit(f'SG-1000: the play route starts with button(s) {start_record["buttons"].split("x")[0]}, {chosen[1]} press(es).')
            routes = sg1000_routes.routes(cart.sha256, frames=frames, level=level, variant=chosen)
            timings['start_choice'] = round(time.perf_counter() - phase, 3)

            emit(f'SG-1000: {title}: {cart.size // 1024} KiB, {standard.upper()}; translating the cartridge, learning on '
                 f'{len(routes)} route(s) ({", ".join(name for name, _, _ in routes)}).')
            phase = time.perf_counter()
            check, pass_counts = sg1000_build.learn(work, cartridge, [[*machine_args, *options(*route)] for route in routes], emit,
                                                    passes=passes, workers=2)
            timings['translation_and_learning'] = round(time.perf_counter() - phase, 3)
            phase = time.perf_counter()
            emit('SG-1000: comparing the native runs with the reference interpreter, field by field and frame by frame.')

            def compare(route):
                name = route[0]
                rows_native = folder / f'{name}-native.csv'
                native = sg1000_build.run(check, [*machine_args, *options(*route), '--rows', str(rows_native)], cartridge)
                reference, rows_reference = reference_rows(*route)
                differing = sg1000_build.differences(native, reference)
                if rows_native.read_bytes() != rows_reference.read_bytes():
                    differing['frame_rows'] = ('native', 'reference')
                return native, reference, rows_reference, differing
            compared = dict(zip((route[0] for route in routes), replay_routes(routes, compare, workers=2)))
            timings['reference_comparison'] = round(time.perf_counter() - phase, 3)
            for name, (_native, _reference, _rows, differing) in compared.items():
                if differing:
                    raise ConversionError(f'SG-1000: on the {name} route the native run differs from the reference '
                                          f'({", ".join(sorted(differing))}); nothing was written.')
            liveness = {name: liveness_summary(sg1000_build.frame_rows(rows)) for name, (_, _, rows, _) in compared.items()}
            for name, record in liveness.items():
                if name != 'attract':
                    require_moving_picture(record, lambda name=name: ConversionError(
                        f'SG-1000: {title}: the picture never changes on the {name} route; nothing was written.'))
            learned = work / 'native.patterns'
            learned_patterns = len(learned.read_text(encoding='utf-8').split()) if learned.is_file() else 0
    except sg1000_build.Sg1000BuildError as error:
        raise ConversionError(f'SG-1000: {error}') from None
    final_checks = []
    for name, count, text in routes:
        native = compared[name][0]
        executed = native['native_steps'] + native['fallback_steps']
        final_checks.append({
            'name': name, 'scenario': name, 'frames': native['frames'], 'script_sha256': hashlib.sha256(text.encode('ascii')).hexdigest(),
            'script_events': len(text.splitlines()), 'native_steps': native['native_steps'], 'halt_steps': native['halt_steps'],
            'interpreted_steps': native['fallback_steps'], 'interpreted_cycles': native['fallback_cycles'],
            'guarded_steps': native['guarded_steps'], 'fallback_at': native['fallback_at'],
            # The same counts under the names the common report reads (report_schema._main_scenario): Z80 instructions and cycles.
            'native_entries': native['native_steps'], 'interpreted_opcodes': native['fallback_steps'],
            'interpreter_cycles': native['fallback_cycles'],
            'interpreter_percent': round(100 * native['fallback_steps'] / max(1, executed), 6),
            'reference_match': True, 'compared_fields': list(sg1000_build.COMPARED),
            'frame_trace': native['frame_trace'], 'ram_hash': native['ram_fnv'], 'vram_hash': native['vram_fnv'],
            'image_hash': native['frame_fnv'], 'pcm_hash': native['audio_fnv'], 'pcm_samples': native['audio_samples'],
            'interrupts': native['interrupts'], 'frame_rows_equal': True, 'liveness': report_fields(liveness[name], LIVENESS_FIELDS)})
    report = {'tool': 'Retro-Recomp', 'version': __version__, 'system': {'id': 'sg1000', 'name': 'SG-1000'},
              'rom': {'sha256': cart.sha256, 'bytes': cart.size, 'file': Path(path).name}, 'converted': True,
              'compiler': {'engine': 'the banked Z80 chain (retrorecomp/z80_chain.py), machine "sg1000"',
                           'native_cpu': 'every instruction position of the cartridge translated ahead of time; code run from RAM '
                                         'learned and translated with byte guards'},
              'sg1000_checks': {'machine': 'SG-1000', 'cartridge_bytes': cart.size, 'padded_bytes': len(cartridge),
                                'mapper': 'none: plain ROM mirrored to 48 KiB', 'standard': standard, 'bios': None,
                                'learning_passes_fallback_steps': pass_counts, 'learned_patterns': learned_patterns,
                                'delivered': False, 'delivery_note': NOT_DELIVERED},
              'final_checks': final_checks, 'scan_level': level, 'route_start': start_record, 'hardware_devices': hardware_devices(),
              'route_warnings': route_warnings(final_checks),
              'sound_routes': {name: bool(record['audible_frames']) for name, record in liveness.items()},
              'native_validation': {'passed': True, 'reference_kind': 'the same machine with every instruction on the reference '
                                                                      'interpreter (corrected SuperZazu, no wait state, /INT and /NMI)',
                                    'cpu_agreement': True, 'cpu_fidelity_validated': False, 'independent_cpu_oracle': False,
                                    'hardware_fidelity_validated': False, 'full_game_validated': False,
                                    'sound_heard': any(record['audible_frames'] for record in liveness.values())},
              'delivered_file': None, 'native_coverage': all(row['interpreted_steps'] == 0 for row in final_checks),
              'video_model': {'chip': 'TMS9918A (our own C, line by line, shared with the MSX)', 'standard': standard,
                              'display_aspect': '4:3'},
              'audio_cpu': None, 'audio_model': {'kind': 'SN76489A (our own C); mixing levels stated, not validated', 'rate': 44100,
                                                 'channels': 1},
              'counter_unit': 'cycles', 'physical_latency_measured': False, 'latency_ms': None, 'hardware_accuracy_validated': False,
              'full_game_validated': False, 'executable': None, 'build_executable': None, 'toolchain': toolchain_description(),
              'build_directory': str(work), 'conversion_phases_seconds': timings,
              'conversion_wall_seconds': round(time.perf_counter() - started, 3),
              'qualification_scope': {'controls': 'pad 1 (the D-pad and buttons 1 and 2); the Pause button is only pressed by an '
                                                  'authored test', 'universal_zero_fallback_claim': False}}
    write_report(output / 'conversion-report.json', report)
    emit(f'SG-1000: {title}: checks passed ({"no interpreter on the routes played" if report["native_coverage"] else "interpreter fallback reported"}); '
         'no executable was delivered (the player is not written yet).')
    return output
