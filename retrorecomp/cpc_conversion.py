"""Amstrad CPC conversion (experimental, developer only): a disk game started from BASIC on the CPC 6128's firmware, the firmware
translated by the banked Z80 chain and the game's code learned from RAM, checked against the reference interpreter, built into a
game. MIT, Retro-Recomp.

The steps: read the disk (cpc_disk.py: DSK or EXTENDED DSK, its catalogue and the start command it implies) and the firmware
(cpc_roms.firmware_for: the player's own system ROM and AMSDOS when Options name them, checked by digest in cpc_firmware.py, else
the pinned, hash-checked fetch); write the start command the three headless programs and
the game type (cpc_build.write_boot_keys); translate the firmware and learn the code the game runs from RAM on the boot route
(cpc_build.learn, the chain's learn_passes, at most `passes` passes); run the native check and the reference on the route and
REFUSE the conversion when any compared field (cpc_build.COMPARED: the CPU, the time, the RAM, the picture, the sound, the
chips) or any frame's row differs; build the game (cpc_build.prepare_game, its resources); replay the delivered (compressed) file
headless and compare it with the reference and the native check; check quick states in a fresh process; write the report (schema
2) and put the delivered file in the output folder.

The five measures stay apart: native code (the Z80 instructions run natively and on the counted interpreter) and agreement with the
reference on the route played are measured; hardware fidelity, gameplay and physical latency are not. Today the route is the
start of the game only (the start command typed, then the frames that follow, no joystick): the report says so.
"""
from __future__ import annotations

import time
from pathlib import Path

from .core import ConversionError

FRAMES = 3600                    # the boot route's default length
LIVENESS_FIELDS = {key: key for key in ('frames', 'distinct_pictures', 'picture_changes', 'last_picture_change_frame', 'audible_frames',
                                        'last_audible_frame', 'distinct_sound_blocks', 'distinct_ram_states',
                                        'distinct_program_counters')}
NATIVE_COUNTS = ('native_steps', 'halt_steps', 'guarded_steps', 'fallback_steps', 'fallback_cycles', 'fallback_at')   # the game's equal the check's
STATE_SETTLE = 600               # frames a fresh process continues after it loaded a quick state
MIN_FRAMES = 60 + STATE_SETTLE + 60
CRTC_TYPE = 1                    # the CRTC of the board (cpc_crtc.h: type 1, the 6128's commonest)
MODEL = 'cpc6128'                # the board modelled (its firmware record names it: part of the identity)
DELIVERY_NOTE = ('a game executable is delivered (developer only, experimental): the translated firmware and the code the game ran '
                 'from RAM, with the CPC player, the host kit and the game\'s disk; the file delivered was replayed headless on the '
                 'boot route and equals the reference interpreter and the native check on every compared field and every frame row; '
                 'no player has played it, and nothing is claimed about the hardware, the gameplay or the latency')


def check_states(game: Path, folder: Path, frames: int, route_rest: list[str], expected: Path) -> dict:
    """F8 at a frame of the route, F9 in a fresh process (conversion_gates.check_quick_states): the loaded process continues the
    uninterrupted trace `expected` for STATE_SETTLE frames; damaged states (state_envelope.damaged_states) are refused and left as
    they were; a missing state is refused and creates nothing. `route_rest`: the route's options without its frame count."""
    from . import cpc_build
    from .conversion_gates import check_quick_states
    from .state_envelope import damaged_states
    folder.mkdir(parents=True, exist_ok=True)
    at = max(60, frames - STATE_SETTLE - 60)
    state = folder / 'quick.rrstate'
    state.unlink(missing_ok=True)

    def continued():
        cpc_build.run_game(game, ['--frames', str(at + 1), *route_rest, '--rows', str(folder / 'save.csv'), '--save-state',
                                  str(state), '--save-at', str(at)], folder / 'save.json')
        cpc_build.run_game(game, ['--frames', str(at + STATE_SETTLE), *route_rest, '--rows', str(folder / 'load.csv'),
                                  '--load-state', str(state)], folder / 'load.json')
        return (expected.read_text(encoding='ascii').splitlines()[1:], (folder / 'load.csv').read_text(encoding='ascii').splitlines()[1:])

    def refused(path: Path) -> bool:
        return cpc_build.game_exit_code(game, ['--frames', '1', '--load-state', str(path)]) == 4
    return check_quick_states(folder, state, machine='Amstrad CPC', route='play', at=at, settle=STATE_SETTLE, continued=continued,
                              refused=refused, damaged=damaged_states, error=ConversionError)


def check_disk_copies(game: Path, folder: Path, frames: int, route_rest: list[str]) -> dict:
    """What the game writes on drive A, kept in the copy beside it (here --disk-copies), in fresh processes of the delivered file:
    the route played with no copy leaves a copy exactly when the game wrote on its disk, and a new process starts from that copy;
    a copy of the wrong size is not read (the embedded disk is used) and is left as it was (the fresh processes run 30 frames,
    before the start command is typed: no game code runs, nothing is written). The embedded disk never changes.
    `route_rest`: the route's options without its frame count. The MSX2+'s check (msx_conversion.check_disks) on the CPC's
    single drive and its report's disk_start_fnv and disk_fnv (drive A's bytes when the run began, its copy read, and at the end)."""
    import shutil
    from . import cpc_build
    from .conversion_gates import require

    def failure(text: str):
        return lambda: ConversionError(f'Amstrad CPC disk: {text}')

    def run(label: str, count: int, rest: list[str], copies: Path) -> dict:
        return cpc_build.run_game(game, ['--frames', str(count), *rest, '--disk-copies', str(copies)], folder / f'{label}.json')
    shutil.rmtree(folder, ignore_errors=True)      # the build folder is reused: no copy of an earlier conversion may be read
    copies = folder / 'copies'
    copies.mkdir(parents=True)
    played = run('route', frames, route_rest, copies)
    start_fnv = played['disk_start_fnv']            # no copy yet: the embedded disk
    wrote = played['disk_fnv'] != start_fnv
    written = sorted(path.name for path in copies.glob('disk-*.dsk'))
    require(bool(written) == wrote, failure('the copy does not follow what the game wrote on the route.'))
    if wrote:
        again = run('again', 30, [], copies)
        require(again['disk_start_fnv'] == played['disk_fnv'],
                failure('what the game wrote did not come back in a fresh process.'))
    damaged = folder / 'damaged'
    damaged.mkdir()
    (damaged / 'disk-1.dsk').write_bytes(b'not a disk')
    blank = run('damaged', 30, [], damaged)
    require(blank['disk_start_fnv'] == start_fnv and (damaged / 'disk-1.dsk').read_bytes() == b'not a disk',
            failure('a copy of the wrong size was read, or changed.'))
    return {'route': 'play', 'game_wrote': wrote, 'copies_written': written, 'written_data_survives_a_fresh_process': wrote or None,
            'wrong_size_copy_ignored_and_kept': True, 'embedded_disk_unchanged': True}


def hardware_devices() -> list:
    """The `hardware_devices` of the common report: the picture, the sound chip and the disk controller, C models of the runtime with no
    counter of their own."""
    common = {'translated_from_rom': False, 'hardware_fidelity_validated': False}
    return [{'id': 'cpc_gate_array_crtc', 'kind': 'video_unit', 'mode': 'c_model',
             'details': {'display': 'the CRTC 6845 and the Gate Array, character by character',
                         'interpreter': 'none: C code in the runtime, not a CPU with a program', **common}},
            {'id': 'ay38910', 'kind': 'audio_unit', 'mode': 'c_model',
             'details': {'mixing_levels': 'stated, not validated', 'interpreter': 'none: the shared AY C model', **common}},
            {'id': 'upd765', 'kind': 'storage_unit', 'mode': 'c_model',
             'details': {'media': 'DSK / EXTENDED DSK', 'interpreter': 'none: our own uPD765 C model', **common}}]


def firmware_pair(options: dict, emit=print) -> tuple[bytes, bytes, dict]:
    """The system ROM and AMSDOS a conversion runs on (cpc_roms.firmware_for: the player's own file for each option that names one,
    checked by digest, else the pinned, hash-checked fetch), and what the report says of them. A development check may pass
    `firmware` (two byte strings: authored programs in their place), recorded as such."""
    given = options.get('firmware')
    if given is not None:
        system, amsdos = given
        return system, amsdos, {'cpc_system': 'authored (development check)', 'cpc_amsdos': 'authored (development check)'}
    from .cpc_roms import firmware_for
    try:
        found = firmware_for(options, emit)
    except (OSError, ValueError) as error:
        raise ConversionError(str(error)) from None
    return found.system, found.amsdos, found.record


def firmware_identity(system: bytes, amsdos: bytes, record: dict) -> dict:
    """The report's top-level `firmware` record (retrorecomp/netplay/lobby_check.py FIRMWARE_KEYS), as the multiplayer specialist
    asked on 21 Nov 2026: one SHA-256 over the OS, BASIC and AMSDOS in that order (the set the lobby compares, so a room refuses two
    seats on different firmware before the match), the model, and each ROM's own SHA-256 and origin for the people reading."""
    import hashlib
    roms = []
    for name, data, key in (('os', system[:0x4000], 'cpc_system'), ('basic', system[0x4000:], 'cpc_system'),
                            ('amsdos', amsdos, 'cpc_amsdos')):
        given = record.get(key)
        roms.append({'name': name, 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data),
                     'origin': given.get('origin', 'player') if isinstance(given, dict) else str(given)})
    return {'sha256': hashlib.sha256(system + amsdos).hexdigest(), 'model': MODEL, 'roms': roms}


def convert(path: Path, *, title=None, output=None, cover=None, use_cover=True, online_cover=True, boxart_dir=None, frames=FRAMES,
            passes=3, scan_level=None, emit=print, **options) -> Path:
    """Convert and deliver the disk at `path`; the delivered game (also copied into `output`) is returned, the report is
    `output/conversion-report.json`. Nothing is written to `output` when a check refuses the conversion."""
    import hashlib
    import shutil
    from . import __version__, z80_chain_build, cpc_build, cpc_keys, cpc_routes
    from .z80_chain_build import write_if_changed as write
    from .conversion_common import check_run_budget, resolve_scan_level
    from .core import ROOT, executable_name
    from .cpc_disk import read_disk
    from .delivery_evidence import deliver_packed, liveness_summary, replay_packed, report_fields, require_moving_picture, same_trace
    from .library import entry_lock
    from .notices import notice_files
    from .report_schema import write_report
    from .toolchain import describe as toolchain_description
    started = time.perf_counter()
    try:
        disk = read_disk(path)
    except (OSError, ValueError) as error:
        raise ConversionError(str(error)) from None
    if not disk.run_command:
        names = ', '.join(disk.candidates) or 'none'
        raise ConversionError(f'Amstrad CPC: {Path(path).name}: the disk does not say which program starts the game '
                              f'(programs: {names}); nothing was written.')
    title = title or disk.title
    if any(ord(c) < 32 for c in title) or len(title) > 160:
        raise ConversionError('Invalid Amstrad CPC game title.')
    system, amsdos, firmware_record = firmware_pair(options, emit)
    level = resolve_scan_level(scan_level)
    frames, passes = int(frames or FRAMES), int(passes or 3)
    check_run_budget(passes, frames, 'Amstrad CPC: a conversion runs 1 to 10 learning passes on a route of 1 to 10,000 frames.')
    if frames < MIN_FRAMES:                      # the quick-state check saves at least 60 frames in and continues STATE_SETTLE
        raise ConversionError(f'Amstrad CPC: the boot route needs at least {MIN_FRAMES} frames.')
    if output is None:
        from .paths import games_directory
        output = games_directory(system_id='cpc') / 'datas/reports' / disk.sha256
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    work = ROOT / '.build' / 'cpc' / disk.sha256[:12]
    start = cpc_keys.start_text(disk.run_command)
    timings = {}
    try:
        with entry_lock(work, timeout=1800):
            work.mkdir(parents=True, exist_ok=True)
            write(work / 'run-system.rom', system)
            write(work / 'run-amsdos.rom', amsdos)
            write(work / 'run-disk.dsk', disk.data)
            cpc_build.write_boot_keys(work, start)
            folder = work / 'routes'
            folder.mkdir(parents=True, exist_ok=True)
            machine_args = ['--system', str(work / 'run-system.rom'), '--amsdos', str(work / 'run-amsdos.rom'), '--disk',
                            str(work / 'run-disk.dsk'), '--crtc', str(CRTC_TYPE)]
            play_script = folder / 'play.inputs'
            play_text = cpc_routes.script(cpc_routes.play_events(frames, disk.sha256))
            if not play_script.is_file() or play_script.read_text(encoding='ascii') != play_text:
                play_script.write_text(play_text, encoding='ascii', newline='\n')
            # (name, the options of the three programs, the script's text): boot plays nothing after the start command; play
            # presses the title screens' keys and moves the joystick (cpc_routes).
            routes = [('boot', ['--frames', str(frames)], ''),
                      ('play', ['--frames', str(frames), '--script', str(play_script)], play_text)]

            emit(f'Amstrad CPC: {title}: {disk.size // 1024} KiB disk, starts with {disk.run_command}; translating the firmware, '
                 f'learning on the boot and play routes ({frames} frames each).')
            phase = time.perf_counter()
            check, pass_counts = cpc_build.learn(work, system, amsdos, [[*machine_args, *options] for _, options, _ in routes], emit,
                                                 passes=passes)
            timings['translation_and_learning'] = round(time.perf_counter() - phase, 3)
            from .platforms import build_executable
            reference_exe = build_executable(work / 'build', 'cpc_reference')

            phase = time.perf_counter()
            emit('Amstrad CPC: comparing the native run with the reference interpreter, field by field and frame by frame.')
            compared, liveness = {}, {}
            for name, options, _text in routes:
                native = cpc_build.run(check, [*machine_args, *options, '--rows', str(folder / f'{name}-native.csv')])
                reference = cpc_build.run(reference_exe, [*machine_args, *options, '--rows', str(folder / f'{name}-reference.csv')])
                differing = cpc_build.differences(native, reference)
                if (folder / f'{name}-native.csv').read_bytes() != (folder / f'{name}-reference.csv').read_bytes():
                    differing['frame_rows'] = ('native', 'reference')
                if differing:
                    raise ConversionError(f'Amstrad CPC: on the {name} route the native run differs from the reference '
                                          f'({", ".join(sorted(differing))}); nothing was written.')
                compared[name] = (native, reference)
                liveness[name] = liveness_summary(cpc_build.frame_rows(folder / f'{name}-reference.csv'))
            timings['reference_comparison'] = round(time.perf_counter() - phase, 3)
            require_moving_picture(liveness['play'], lambda: ConversionError(
                f'Amstrad CPC: {title}: the picture never changes on the play route; nothing was written.'))
            learning = z80_chain_build.learning_record(work)

            phase = time.perf_counter()
            emit('Amstrad CPC: building the game.')
            presentation = {'rom_path': Path(path), 'cover': Path(cover) if cover else None, 'use_cover': use_cover,
                            'online_cover': online_cover, 'boxart_dir': boxart_dir}
            cpc_build.stage_sources(work, game=True)
            prepared = cpc_build.prepare_game(work, title, disk.sha256, [disk.data], system, amsdos, start, crtc=CRTC_TYPE,
                                              presentation=presentation, emit=emit)
            try:
                executable = cpc_build.build(work, ('game',), emit)['game']
            except cpc_build.CpcBuildError as error:
                raise ConversionError(f'Amstrad CPC: the game could not be built ({error}).') from None
            timings['game_build'] = round(time.perf_counter() - phase, 3)

            # The delivered file: the compressed copy the player receives, replayed headless on the route and compared with the
            # reference (every compared field and every frame row) and with the native check (its native and interpreted steps).
            phase = time.perf_counter()
            delivered = deliver_packed(executable, work / ('packed-' + executable.name), 'Amstrad CPC', emit)

            def replay(route):
                name, options, _text = route
                return cpc_build.run_game(delivered.path, [*options, '--rows', str(folder / f'{name}-packed.csv')],
                                          folder / f'{name}-packed.json')

            def same(route, result):
                name = route[0]
                native, reference = compared[name]
                return (not cpc_build.differences(result, reference) and all(result.get(key) == native.get(key) for key in NATIVE_COUNTS)
                        and same_trace(folder / f'{name}-packed.csv', folder / f'{name}-reference.csv'))
            replay_packed(delivered, routes, replay, same=same, workers=2, mismatch=lambda route: ConversionError(
                f'Amstrad CPC: the delivered (compressed) game differs from the reference on the {route[0]} route; nothing was '
                'published.'))
            timings['packed_replay'] = round(time.perf_counter() - phase, 3)
            phase = time.perf_counter()
            emit('Amstrad CPC: checking quick states in a fresh process.')
            states = check_states(delivered.path, work / 'states', frames, routes[1][1][2:], folder / 'play-packed.csv')
            timings['quick_states'] = round(time.perf_counter() - phase, 3)
            phase = time.perf_counter()
            emit('Amstrad CPC: checking what the game writes on its disk, in fresh processes.')
            disk_writes = check_disk_copies(delivered.path, work / 'disk-copies', frames, routes[1][1][2:])
            timings['disk_copies'] = round(time.perf_counter() - phase, 3)
    except cpc_build.CpcBuildError as error:
        raise ConversionError(f'Amstrad CPC: {error}') from None
    final_checks = []
    for name, _options, text in routes:
        native = compared[name][0]
        executed = native['native_steps'] + native['fallback_steps']
        final_checks.append({
            'name': name, 'scenario': name, 'frames': native['frames'],
            'script_sha256': hashlib.sha256((start + text).encode('ascii')).hexdigest(), 'script_events': len(text.splitlines()),
            'native_steps': native['native_steps'], 'halt_steps': native['halt_steps'], 'guarded_steps': native['guarded_steps'],
            'interpreted_steps': native['fallback_steps'], 'interpreted_cycles': native['fallback_cycles'],
            'fallback_at': native['fallback_at'],
            # The same counts under the names the common report reads (report_schema._main_scenario): Z80 instructions.
            'native_entries': native['native_steps'], 'interpreted_opcodes': native['fallback_steps'],
            'interpreter_cycles': native['fallback_cycles'],
            'interpreter_percent': round(100 * native['fallback_steps'] / max(1, executed), 6),
            'reference_match': True, 'compared_fields': list(cpc_build.COMPARED),
            'ram_hash': native['ram_fnv'], 'image_hash': native['picture_fnv'], 'pcm_hash': native['audio_fnv'],
            'pcm_samples': native['audio_samples'], 'interrupts': native['interrupts'], 'frame_rows_equal': True,
            'packed_rows_equal': True, 'liveness': report_fields(liveness[name], LIVENESS_FIELDS)})
    report = {'tool': 'Retro-Recomp', 'version': __version__, 'system': {'id': 'cpc', 'name': 'Amstrad CPC'},
              'rom': {'sha256': disk.sha256, 'bytes': disk.size, 'file': Path(path).name}, 'converted': True,
              'firmware': firmware_identity(system, amsdos, firmware_record),
              'compiler': {'engine': 'the banked Z80 chain (retrorecomp/z80_chain.py), machine "cpc"',
                           'native_cpu': 'every instruction position of the system ROM and AMSDOS translated ahead of time; code '
                                         'run from RAM (the game, loaded from its disk) learned and translated with byte guards'},
              'cpc_checks': {'machine': 'Amstrad CPC 6128', 'disk': disk.features(), 'run_command': disk.run_command,
                             'boot_keys_from_frame': cpc_keys.BOOT_FRAME, 'firmware': firmware_record, 'crtc_type': CRTC_TYPE,
                             'learning_passes_fallback_steps': pass_counts, **learning,
                             'delivered': True, 'delivery_note': DELIVERY_NOTE},
              'final_checks': final_checks, 'scan_level': level, 'hardware_devices': hardware_devices(),
              'sound_routes': {name: bool(record['audible_frames']) for name, record in liveness.items()},
              'native_validation': {'passed': True, 'reference_kind': 'the same machine with every instruction on the reference '
                                                                      'interpreter (corrected SuperZazu, the CPC\'s costs, 16-bit ports)',
                                    'cpu_agreement': True, 'cpu_fidelity_validated': False, 'independent_cpu_oracle': False,
                                    'hardware_fidelity_validated': False, 'full_game_validated': False,
                                    'sound_heard': any(record['audible_frames'] for record in liveness.values()),
                                    **delivered.validation_fields()},
              **delivered.report_fields(), 'delivered_file': delivered.kind,
              'native_coverage': all(check['interpreted_steps'] == 0 for check in final_checks),
              'video_model': {'chip': 'CRTC 6845 type 1 and the Gate Array (our own C)', 'standard': 'pal', 'display_aspect': '4:3'},
              'audio_cpu': None, 'audio_model': {'kind': 'AY-3-8912 (the shared C model); mixing levels stated, not validated',
                                                 'rate': 44100, 'channels': 2},
              'counter_unit': 'instructions', 'physical_latency_measured': False, 'latency_ms': None,
              'hardware_accuracy_validated': False, 'full_game_validated': False,
              'game_states': {'supported': True, 'save_key': 'F8', 'load_key': 'F9', 'schema': 'RRCPCST-1',
                              'layout': cpc_build.STATE_LAYOUT, 'compatibility': 'the exact disk, firmware, CRTC and build',
                              'fresh_process_verified': True, 'validation': states},
              'disk_writes': disk_writes,
              'notices': {'files': list(notice_files('cpc')), 'embedded_resource': 203},
              'artwork': prepared['artwork'], 'windows_metadata': prepared['windows_metadata'],
              'executable': executable_name(title), 'build_executable': str(executable), 'toolchain': toolchain_description(),
              'build_directory': str(work), 'conversion_phases_seconds': timings,
              'conversion_wall_seconds': round(time.perf_counter() - started, 3),
              'qualification_scope': {'routes': 'boot (the start command typed, then nothing) and play (from frame '
                                                f'{cpc_routes.PLAY_FROM}: title-screen keys, then the joystick at random, seeded by '
                                                'the disk)', 'universal_zero_fallback_claim': False}}
    write_report(output / 'conversion-report.json', report)
    file = output / executable_name(title)
    shutil.copy2(delivered.path, file)
    emit(f'Amstrad CPC: {title} ready ({"no interpreter on the routes played" if report["native_coverage"] else "interpreter fallback reported"}).')
    return file
