"""ZX Spectrum conversion (docs/ZX_SPECTRUM.md), step 1 stage 2 in progress.

`convert` reads the snapshot and the ROM (retrorecomp/zxs_roms.py: the player's own, or the pinned Amstrad images), chooses how the
play route starts on the reference interpreter (route_start, zxs_routes), translates the ROM and learns the code the snapshot runs
from RAM (zxs_build.learn), then compares every native route with the reference, field by field and frame by frame, and refuses the
conversion on any difference. The game, its delivered file and its quick states come with the player (`deliver_game`, not wired yet:
the conversion stops there). The report goes through the common builder; it states the hardware limits (no ULA contention, no
floating bus, the border drawn per line) and keeps the five measures apart.

The route (the maintainer's choice of 21 November 2026, route A): the shared banked Z80 chain the Master System and the MSX
use (smsggrecomp and z80-recomp-core, pinned; superzazu/z80 as the counted fallback's reference interpreter), and our own
MIT C for the rest, written from floooh/chips (zlib) and Clock Signal (MIT) as references only. No GPL part goes into a game.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .core import ConversionError
from .platforms import target_id
from .report_schema import write_report
from .zxs_snapshot import read_snapshot


def skeleton_report(source, scenarios, level='standard') -> dict:
    """The writer's own keys for a conversion that ran `scenarios` (name, frames, native cycles, interpreted cycles).

    The marker key of this shape is ``zxs_checks``. Nothing here is measured: the real writer replaces the numbers with
    the ones its reference run produced. The five measures stay apart and unclaimed."""
    checks = [{'scenario': name, 'frames': frames, 'native_cycles': native, 'interpreted_cycles': interpreted,
               'interpreter_percent': 100 * interpreted / max(1, native + interpreted), 'reference_match': None}
              for name, frames, native, interpreted in scenarios]
    return {'tool': 'Retro-Recomp', 'version': __version__, 'created_utc': datetime.now(timezone.utc).isoformat(),
            'system': {'id': 'zxs', 'name': 'ZX Spectrum', 'model': source.model}, 'status': 'experimental',
            'target': target_id(), 'rom': source.metadata(), 'scan_level': level,
            'native_validation': {'passed': None, 'scope': 'step 1 skeleton: nothing was compared',
                                  'cpu_fidelity_validated': False, 'independent_cpu_oracle': False},
            'native_coverage': 'not measured', 'final_checks': checks, 'zxs_checks': checks,
            'game_states': {'supported': False, 'save_key': 'F8', 'load_key': 'F9', 'fresh_process_verified': False},
            'hardware_accuracy_validated': False, 'full_game_validated': False, 'latency_ms': None,
            # A hardware-fidelity limit every report states until the contention stage lands (docs/ZX_SPECTRUM.md, section 4).
            'hardware_limits': ['ULA memory contention is not modelled: every instruction takes its plain Z80 time']}


def write_skeleton_report(path, source, scenarios, level='standard') -> dict:
    return write_report(path, skeleton_report(source, scenarios, level))


def developer_available() -> bool:
    """True when this installation carries the ZX Spectrum converter files. Nothing converts yet, so none does."""
    return False


# ---- the conversion (step 1, stage 2) ------------------------------------------------------------------------------------------
FRAMES = 3600                    # the batch's default route length (the profile's default_frames)
LIVENESS_FIELDS = {key: key for key in ('frames', 'distinct_pictures', 'picture_changes', 'last_picture_change_frame',
                                        'audible_frames', 'last_audible_frame', 'distinct_sound_blocks', 'distinct_ram_states',
                                        'distinct_program_counters')}
CONTENTION = 'not modelled: every instruction takes its plain Z80 time (docs/ZX_SPECTRUM.md, section 4)'


def hardware_devices(snapshot) -> list:
    """The machine's devices as the common report lists them: what is modelled, by whom, and what is not."""
    devices = [{'id': 'ula', 'kind': 'video_unit', 'mode': 'c_model', 'model': 'our own C, line by line (border per line); '
                f'contention {CONTENTION}; floating bus not modelled'},
               {'id': 'beeper', 'kind': 'sound_unit', 'mode': 'c_model', 'model': 'port FEh bit 4, box-filtered to 44.1 kHz'},
               {'id': 'keyboard', 'kind': 'input', 'mode': 'c_model', 'model': 'the eight half-rows of port FEh'}]
    if snapshot.model == '128k':
        devices.append({'id': 'ay-3-8910', 'kind': 'sound_unit', 'mode': 'c_model',
                        'model': 'the shared chip (native/ay38910) at the CPU clock / 2, mixed with the beeper (levels stated, not measured)'})
        devices.append({'id': 'paging', 'kind': 'memory_mapper', 'mode': 'c_model', 'model': 'port 7FFDh: RAM bank, screen, ROM, lock'})
    if snapshot.joystick == 'kempston':
        devices.append({'id': 'kempston', 'kind': 'input', 'mode': 'c_model', 'model': 'port 1Fh'})
    return devices


def convert(path: Path, *, title=None, output=None, cover=None, use_cover=True, online_cover=True, boxart_dir=None,
            zxs_rom48=None, zxs_rom128=None, frames=FRAMES, passes=3, scan_level=None, profile=None, emit=print,
            **unused) -> Path:
    import hashlib
    import json
    import time
    from . import __version__, route_start, zxs_build, zxs_roms, zxs_routes
    from .conversion_common import check_run_budget, resolve_scan_level
    from .core import ROOT, executable_name
    from .delivery_evidence import liveness_summary, replay_routes, report_fields, require_moving_picture
    from .library import entry_lock
    from .toolchain import describe as toolchain_description
    started = time.perf_counter()
    if profile is not None:
        raise ConversionError('ZX Spectrum snapshots are read from their content; TOML cartridge profiles do not apply.')
    try:
        snapshot = read_snapshot(path)
        rom = zxs_roms.rom_for(snapshot.model, {'zxs_rom48': zxs_rom48, 'zxs_rom128': zxs_rom128}, emit)
    except (OSError, ValueError) as error:
        raise ConversionError(str(error)) from None
    title = title or Path(path).stem
    if any(ord(c) < 32 for c in title) or len(title) > 160:
        raise ConversionError('Invalid ZX Spectrum game title.')
    if output is None:
        from .paths import games_directory
        output = games_directory(system_id='zxs') / 'datas/reports' / snapshot.sha256
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    image = zxs_build.zxs_image(snapshot)
    work = ROOT / '.build' / 'zxs' / f'{snapshot.sha256[:12]}-{rom.sha256[:8]}'
    level = resolve_scan_level(scan_level)
    frames, passes = int(frames or FRAMES), int(passes or 3)
    check_run_budget(passes, frames, 'ZX Spectrum: a conversion runs 1 to 10 learning passes on routes of 1 to 10,000 frames.')
    timings = {}
    with entry_lock(work, timeout=1800):
        work.mkdir(parents=True, exist_ok=True)
        rom_path = work / 'rom.bin'
        zxs_build.write_rom(rom_path, rom.data)
        folder = work / 'routes'
        folder.mkdir(parents=True, exist_ok=True)
        try:
            zxs_build.generate(work, rom.data, emit)
            zxs_build.stage_sources(work)
            reference_exe = zxs_build.build(work, ('zxs_reference',), emit)['zxs_reference']
        except zxs_build.ZxsBuildError as error:
            raise ConversionError(f'ZX Spectrum: {error}') from None

        def options(name: str, count: int, text: str) -> list[str]:
            """A route's options for every program (the check, the reference, the game): its length, its script."""
            script = folder / f'{name}.inputs'
            if not script.is_file() or script.read_text(encoding='ascii') != text:
                script.write_text(text, encoding='ascii', newline='\n')
            return ['--frames', str(count), '--script', str(script)]

        def reference_rows(name: str, count: int, text: str) -> tuple[dict, Path]:
            rows = folder / f'{name}-reference.csv'
            return zxs_build.run(reference_exe, rom_path, image, [*options(name, count, text), '--rows', str(rows)]), rows

        # The start (route_start, as the MSX): each variant played on the reference against the route without input.
        phase = time.perf_counter()
        play_frames = max(frames, zxs_routes.PLAY_FRAMES)
        seed = zxs_routes.route_seed(snapshot.sha256, 'play')
        variants = zxs_routes.candidates(play_frames)
        emit(f'ZX Spectrum: choosing how the play route starts ({len(variants)} variants on the reference).')
        try:
            played = replay_routes(
                [('baseline', None), *((f'start-{zxs_routes.variant_name(v)}', v) for v in variants)],
                lambda row: reference_rows(row[0], play_frames, '' if row[1] is None else
                                           zxs_routes.script(zxs_routes.events(play_frames, seed, row[1], snapshot.joystick))),
                workers=4)
        except zxs_build.ZxsBuildError as error:
            raise ConversionError(f'ZX Spectrum: {error}') from None

        def pictures(rows: Path) -> dict:
            return {row.frame: row.picture for row in zxs_build.frame_rows(rows)}
        baseline = pictures(played[0][1])
        results = {}
        for variant, (_result, rows) in zip(variants, played[1:]):
            mine = pictures(rows)
            results[variant] = {'liveness': report_fields(liveness_summary(zxs_build.frame_rows(rows)), LIVENESS_FIELDS),
                                'divergence': route_start.divergence(mine, baseline),
                                'reach': route_start.reach(mine, baseline, zxs_routes.walk_start(variant[0]),
                                                           zxs_routes.QUIET_WALK)}
        chosen = route_start.choose_start(results, play_frames, zxs_routes.variant_order)
        start_record = {'presses': chosen[0], 'key': chosen[1],
                        'rule': 'alive until the last 120 frames, then most pictures the walk reached that no input showed, '
                                'then most frames the input changed, then the fewest presses',
                        'variants': {zxs_routes.variant_name(v): r for v, r in results.items()}}
        emit(f'ZX Spectrum: the play route starts with {zxs_routes.variant_name(chosen)}.')
        routes = zxs_routes.routes(snapshot.sha256, frames=frames, level=level, variant=chosen, joystick=snapshot.joystick)
        timings['start_choice'] = round(time.perf_counter() - phase, 3)

        emit(f'ZX Spectrum: {title}: {snapshot.hardware} snapshot, ROM {rom.origin}; translating the ROM, learning the RAM code on '
             f'{len(routes)} route(s) ({", ".join(name for name, _, _ in routes)}).')
        phase = time.perf_counter()
        try:
            check, pass_counts = zxs_build.learn(work, rom.data, image, [options(*route) for route in routes], emit,
                                                 passes=passes)
        except zxs_build.ZxsBuildError as error:
            raise ConversionError(f'ZX Spectrum: {error}') from None
        timings['translation_and_learning'] = round(time.perf_counter() - phase, 3)
        phase = time.perf_counter()
        emit('ZX Spectrum: comparing the native runs with the reference interpreter, field by field and frame by frame.')

        def compare(route):
            name = route[0]
            rows_native = folder / f'{name}-native.csv'
            native = zxs_build.run(check, rom_path, image, [*options(*route), '--rows', str(rows_native)])
            reference, rows_reference = reference_rows(*route)
            differing = zxs_build.differences(native, reference)
            if rows_native.read_bytes() != rows_reference.read_bytes():
                differing['frame_rows'] = ('native', 'reference')
            return native, reference, rows_reference, differing
        try:
            compared = dict(zip((route[0] for route in routes), replay_routes(routes, compare, workers=2)))
        except zxs_build.ZxsBuildError as error:
            raise ConversionError(f'ZX Spectrum: {error}') from None
        timings['reference_comparison'] = round(time.perf_counter() - phase, 3)
        for name, (_native, _reference, _rows, differing) in compared.items():
            if differing:
                raise ConversionError(f'ZX Spectrum: on the {name} route the native run differs from the reference '
                                      f'({", ".join(sorted(differing))}); nothing was built.')
        liveness = {name: liveness_summary(zxs_build.frame_rows(rows)) for name, (_, _, rows, _) in compared.items()}
        for name, record in liveness.items():
            if name != 'attract':
                require_moving_picture(record, lambda name=name: ConversionError(
                    f'ZX Spectrum: {title}: the picture never changes on the {name} route; nothing was built.'))
        game = deliver_game(work, snapshot, rom, image, title, routes, options, compared, emit, timings,
                            presentation={'rom_path': Path(path), 'cover': Path(cover) if cover else None,
                                          'use_cover': use_cover, 'online_cover': online_cover, 'boxart_dir': boxart_dir})
    final_checks = []
    for name, count, text in routes:
        native = compared[name][0]
        executed = native['native_steps'] + native['fallback_steps']
        final_checks.append({
            'name': name, 'scenario': name, 'frames': native['frames'],
            'script_sha256': hashlib.sha256(text.encode('ascii')).hexdigest(), 'script_events': len(text.splitlines()),
            'native_steps': native['native_steps'], 'halt_steps': native['halt_steps'],
            'interpreted_steps': native['fallback_steps'], 'interpreted_cycles': native['fallback_cycles'],
            'guarded_steps': native['guarded_steps'],
            # The same counts under the names the common report reads (report_schema._main_scenario): Z80 instructions.
            'native_entries': native['native_steps'], 'interpreted_opcodes': native['fallback_steps'],
            'interpreter_cycles': native['fallback_cycles'],
            'interpreter_percent': round(100 * native['fallback_steps'] / max(1, executed), 6),
            'reference_match': True, 'compared_fields': list(zxs_build.COMPARED),
            'frame_trace': native['frame_trace'], 'ram_hash': native['ram_fnv'], 'image_hash': native['frame_fnv'],
            'pcm_hash': native['audio_fnv'], 'pcm_samples': native['audio_samples'], 'interrupts': native['interrupts'],
            'frame_rows_equal': True, 'liveness': report_fields(liveness[name], LIVENESS_FIELDS)})
    report = {'tool': 'Retro-Recomp', 'version': __version__,
              'system': {'id': 'zxs', 'name': 'ZX Spectrum', 'model': snapshot.model}, 'status': 'experimental',
              'rom': {**snapshot.metadata(), 'file': Path(path).name}, 'converted': True,
              'compiler': {'engine': 'the banked Z80 chain (retrorecomp/z80_chain.py), machine "zxs"',
                           'native_cpu': 'every instruction position of the Spectrum ROM translated ahead of time; the code the '
                                         'snapshot runs from RAM learned and translated with byte guards'},
              'zxs_checks': {'machine': snapshot.hardware, 'model': snapshot.model, 'joystick': snapshot.joystick,
                             'rom': {'origin': rom.origin, 'sha256': rom.sha256,
                                     'source': None if rom.origin == 'player' else
                                     f'{zxs_roms.SOURCE_REPOSITORY} at {zxs_roms.SOURCE_COMMIT} (Amstrad\'s permission for emulators)'},
                             'learning_passes_fallback_steps': pass_counts,
                             'learned_patterns': len((work / 'native.patterns').read_text(encoding='utf-8').split())
                             if (work / 'native.patterns').is_file() else 0,
                             'contention': CONTENTION},
              'final_checks': final_checks, 'scan_level': level, 'route_start': start_record,
              'hardware_devices': hardware_devices(snapshot),
              'hardware_limits': ['ULA memory contention is not modelled: every instruction takes its plain Z80 time',
                                  'the floating bus is not modelled: an unused port reads FFh',
                                  'border changes within a line are drawn at the line\'s end'],
              'route_warnings': route_warnings(final_checks),
              'ordinary_saves': {'supported': False, 'reason': 'the ZX Spectrum has no battery save', 'scope': None,
                                 'path': None, 'validation': None},
              'sound_routes': {name: bool(record['audible_frames']) for name, record in liveness.items()},
              'native_validation': {'passed': True, 'reference_kind': 'the same machine with every instruction on the reference '
                                                                      'interpreter (corrected SuperZazu, 16-bit ports)',
                                    'cpu_agreement': True, 'cpu_fidelity_validated': False, 'independent_cpu_oracle': False,
                                    'hardware_fidelity_validated': False, 'full_game_validated': False,
                                    'sound_heard': any(record['audible_frames'] for record in liveness.values()),
                                    **game['validation_fields']},
              **game['report_fields'],
              'native_coverage': all(row['interpreted_steps'] == 0 for row in final_checks),
              'video_model': {'chip': 'the ULA (our own C, line by line)', 'standard': 'pal', 'display_aspect': '4:3'},
              'audio_cpu': None,
              'audio_model': {'kind': 'the beeper' + (' and the AY-3-8910 (the shared chip)' if snapshot.model == '128k' else '')
                                      + '; levels stated, not validated', 'rate': 44100, 'channels': 1},
              'counter_unit': 'cycles', 'physical_latency_measured': False, 'latency_ms': None,
              'hardware_accuracy_validated': False, 'full_game_validated': False,
              'game_states': game['game_states'],
              'artwork': game['artwork'], 'windows_metadata': game['windows_metadata'],
              'executable': executable_name(title), 'build_executable': str(game['executable']),
              'toolchain': toolchain_description(), 'build_directory': str(work),
              'conversion_phases_seconds': timings, 'conversion_wall_seconds': round(time.perf_counter() - started, 3),
              'qualification_scope': {'controls': 'pad 1 on the controls the snapshot was saved for (cursor keys, Kempston or '
                                                  'Sinclair Interface 2), and ENTER, SPACE, 0 and 1',
                                      'universal_zero_fallback_claim': False}}
    write_report(output / 'conversion-report.json', report)
    return Path(game['executable'])


def route_warnings(final_checks: list) -> list:
    """The routes whose picture stopped changing early, in words (the Master System's rule, shared by import)."""
    from .sega_evidence import route_warnings as words
    return words(final_checks)


def deliver_game(work, snapshot, rom, image, title, routes, options, compared, emit, timings, presentation) -> dict:
    """The game, its delivered (compressed) file replayed against the reference, its quick states: the player's part of the
    conversion (native/zxs_machine/zxs_player.c, native/hostkit/adapters/rrhk_zxs.inc). Not wired yet: the conversion stops here."""
    raise ConversionError('ZX Spectrum: the native runs equal the reference; the player is not built yet (step 1, stage 2 in '
                          'progress), so nothing is delivered.')
