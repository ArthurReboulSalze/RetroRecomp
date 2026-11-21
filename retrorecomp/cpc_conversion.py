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
NATIVE_COUNTS = ('native_steps', 'fallback_steps')   # the delivered game's equal the check's
STATE_SETTLE = 600               # frames a fresh process continues after it loaded a quick state
MIN_FRAMES = 60 + STATE_SETTLE + 60
CRTC_TYPE = 1                    # the CRTC of the board (cpc_crtc.h: type 1, the 6128's commonest)
MODEL = 'cpc6128'                # the board modelled (its firmware record names it: part of the identity)
DELIVERY_NOTE = ('a game executable is delivered (developer only, experimental): the translated firmware and the code the game ran '
                 'from RAM, with the CPC player, the host kit and the game\'s disk; the file delivered was replayed headless on the '
                 'boot route and equals the reference interpreter and the native check on every compared field and every frame row; '
                 'no player has played it, and nothing is claimed about the hardware, the gameplay or the latency')


def check_states(game: Path, folder: Path, frames: int, expected: Path) -> dict:
    """F8 at a frame of the route, F9 in a fresh process (conversion_gates.check_quick_states): the loaded process continues the
    uninterrupted trace `expected` for STATE_SETTLE frames; damaged states (state_envelope.damaged_states) are refused and left as
    they were; a missing state is refused and creates nothing."""
    from . import cpc_build
    from .conversion_gates import check_quick_states
    from .state_envelope import damaged_states
    folder.mkdir(parents=True, exist_ok=True)
    at = max(60, frames - STATE_SETTLE - 60)
    state = folder / 'quick.rrstate'
    state.unlink(missing_ok=True)

    def continued():
        cpc_build.run_game(game, ['--frames', str(at + 1), '--rows', str(folder / 'save.csv'), '--save-state', str(state),
                                  '--save-at', str(at)], folder / 'save.json')
        cpc_build.run_game(game, ['--frames', str(at + STATE_SETTLE), '--rows', str(folder / 'load.csv'), '--load-state',
                                  str(state)], folder / 'load.json')
        return (expected.read_text(encoding='ascii').splitlines()[1:], (folder / 'load.csv').read_text(encoding='ascii').splitlines()[1:])

    def refused(path: Path) -> bool:
        return cpc_build.game_exit_code(game, ['--frames', '1', '--load-state', str(path)]) == 4
    return check_quick_states(folder, state, machine='Amstrad CPC', route='boot', at=at, settle=STATE_SETTLE, continued=continued,
                              refused=refused, damaged=damaged_states, error=ConversionError)


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
    from . import __version__, cpc_build, cpc_keys
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
            route = ['--frames', str(frames)]

            emit(f'Amstrad CPC: {title}: {disk.size // 1024} KiB disk, starts with {disk.run_command}; translating the firmware, '
                 f'learning on the boot route ({frames} frames).')
            phase = time.perf_counter()
            check, pass_counts = cpc_build.learn(work, system, amsdos, [[*machine_args, *route]], emit, passes=passes)
            timings['translation_and_learning'] = round(time.perf_counter() - phase, 3)
            from .platforms import build_executable
            reference_exe = build_executable(work / 'build', 'cpc_reference')

            phase = time.perf_counter()
            emit('Amstrad CPC: comparing the native run with the reference interpreter, field by field and frame by frame.')
            native = cpc_build.run(check, [*machine_args, *route, '--rows', str(folder / 'boot-native.csv')])
            reference = cpc_build.run(reference_exe, [*machine_args, *route, '--rows', str(folder / 'boot-reference.csv')])
            differing = cpc_build.differences(native, reference)
            if (folder / 'boot-native.csv').read_bytes() != (folder / 'boot-reference.csv').read_bytes():
                differing['frame_rows'] = ('native', 'reference')
            timings['reference_comparison'] = round(time.perf_counter() - phase, 3)
            if differing:
                raise ConversionError(f'Amstrad CPC: on the boot route the native run differs from the reference '
                                      f'({", ".join(sorted(differing))}); nothing was written.')
            liveness = liveness_summary(cpc_build.frame_rows(folder / 'boot-reference.csv'))
            require_moving_picture(liveness, lambda: ConversionError(
                f'Amstrad CPC: {title}: the picture never changes on the boot route; nothing was written.'))
            learned = work / 'native.patterns'
            learned_patterns = len(learned.read_text(encoding='utf-8').split()) if learned.is_file() else 0

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

            def replay(_route):
                return cpc_build.run_game(delivered.path, [*route, '--rows', str(folder / 'boot-packed.csv')], folder / 'boot-packed.json')

            def same(_route, result):
                return (not cpc_build.differences(result, reference) and all(result.get(key) == native.get(key) for key in NATIVE_COUNTS)
                        and same_trace(folder / 'boot-packed.csv', folder / 'boot-reference.csv'))
            replay_packed(delivered, [('boot',)], replay, same=same, workers=1, mismatch=lambda _route: ConversionError(
                'Amstrad CPC: the delivered (compressed) game differs from the reference on the boot route; nothing was published.'))
            timings['packed_replay'] = round(time.perf_counter() - phase, 3)
            phase = time.perf_counter()
            emit('Amstrad CPC: checking quick states in a fresh process.')
            states = check_states(delivered.path, work / 'states', frames, folder / 'boot-packed.csv')
            timings['quick_states'] = round(time.perf_counter() - phase, 3)
    except cpc_build.CpcBuildError as error:
        raise ConversionError(f'Amstrad CPC: {error}') from None
    executed = native['native_steps'] + native['fallback_steps']
    final_checks = [{
        'name': 'boot', 'scenario': 'boot', 'frames': native['frames'],
        'script_sha256': hashlib.sha256(start.encode('ascii')).hexdigest(), 'script_events': len(start),
        'native_steps': native['native_steps'], 'interpreted_steps': native['fallback_steps'],
        # The same counts under the names the common report reads (report_schema._main_scenario): Z80 instructions.
        'native_entries': native['native_steps'], 'interpreted_opcodes': native['fallback_steps'],
        'interpreter_percent': round(100 * native['fallback_steps'] / max(1, executed), 6),
        'reference_match': True, 'compared_fields': list(cpc_build.COMPARED),
        'ram_hash': native['ram_fnv'], 'image_hash': native['picture_fnv'], 'pcm_hash': native['audio_fnv'],
        'pcm_samples': native['audio_samples'], 'interrupts': native['interrupts'], 'frame_rows_equal': True,
        'packed_rows_equal': True, 'liveness': report_fields(liveness, LIVENESS_FIELDS)}]
    report = {'tool': 'Retro-Recomp', 'version': __version__, 'system': {'id': 'cpc', 'name': 'Amstrad CPC'},
              'rom': {'sha256': disk.sha256, 'bytes': disk.size, 'file': Path(path).name}, 'converted': True,
              'firmware': firmware_identity(system, amsdos, firmware_record),
              'compiler': {'engine': 'the banked Z80 chain (retrorecomp/z80_chain.py), machine "cpc"',
                           'native_cpu': 'every instruction position of the system ROM and AMSDOS translated ahead of time; code '
                                         'run from RAM (the game, loaded from its disk) learned and translated with byte guards'},
              'cpc_checks': {'machine': 'Amstrad CPC 6128', 'disk': disk.features(), 'run_command': disk.run_command,
                             'boot_keys_from_frame': cpc_keys.BOOT_FRAME, 'firmware': firmware_record, 'crtc_type': CRTC_TYPE,
                             'learning_passes_fallback_steps': pass_counts, 'learned_patterns': learned_patterns,
                             'delivered': True, 'delivery_note': DELIVERY_NOTE},
              'final_checks': final_checks, 'scan_level': level, 'hardware_devices': hardware_devices(),
              'sound_routes': {'boot': bool(liveness['audible_frames'])},
              'native_validation': {'passed': True, 'reference_kind': 'the same machine with every instruction on the reference '
                                                                      'interpreter (corrected SuperZazu, the CPC\'s costs, 16-bit ports)',
                                    'cpu_agreement': True, 'cpu_fidelity_validated': False, 'independent_cpu_oracle': False,
                                    'hardware_fidelity_validated': False, 'full_game_validated': False,
                                    'sound_heard': bool(liveness['audible_frames']), **delivered.validation_fields()},
              **delivered.report_fields(), 'delivered_file': delivered.kind,
              'native_coverage': native['fallback_steps'] == 0,
              'video_model': {'chip': 'CRTC 6845 type 1 and the Gate Array (our own C)', 'standard': 'pal', 'display_aspect': '4:3'},
              'audio_cpu': None, 'audio_model': {'kind': 'AY-3-8912 (the shared C model); mixing levels stated, not validated',
                                                 'rate': 44100, 'channels': 2},
              'counter_unit': 'instructions', 'physical_latency_measured': False, 'latency_ms': None,
              'hardware_accuracy_validated': False, 'full_game_validated': False,
              'game_states': {'supported': True, 'save_key': 'F8', 'load_key': 'F9', 'schema': 'RRCPCST-1',
                              'layout': cpc_build.STATE_LAYOUT, 'compatibility': 'the exact disk, firmware, CRTC and build',
                              'fresh_process_verified': True, 'validation': states},
              'notices': {'files': list(notice_files('cpc')), 'embedded_resource': 203},
              'artwork': prepared['artwork'], 'windows_metadata': prepared['windows_metadata'],
              'executable': executable_name(title), 'build_executable': str(executable), 'toolchain': toolchain_description(),
              'build_directory': str(work), 'conversion_phases_seconds': timings,
              'conversion_wall_seconds': round(time.perf_counter() - started, 3),
              'qualification_scope': {'routes': 'the boot route only: the start command typed, then the frames that follow, no '
                                                'joystick', 'universal_zero_fallback_claim': False}}
    write_report(output / 'conversion-report.json', report)
    file = output / executable_name(title)
    shutil.copy2(delivered.path, file)
    emit(f'Amstrad CPC: {title} ready ({"no interpreter on the route played" if report["native_coverage"] else "interpreter fallback reported"}).')
    return file
