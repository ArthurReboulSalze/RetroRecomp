"""MSX conversion (experimental): an MSX1 or MSX2 cartridge and its BIOS translated by the banked Z80 chain, checked against
the reference interpreter, built into a game.

The steps: read the cartridge and guess its mapper (msx_rom.py); choose the BIOS (the player's own MSX BIOS, checked: a 32 KiB
main ROM on the MSX1, the main ROM and its 16 KiB sub-ROM on the MSX2; or C-BIOS 0.29a, pinned); generate the bodies of both and learn the code run from RAM (msx_build.learn, at most three passes) on a
the routes of the scan level (msx_routes: attract, play from a start chosen on the reference, long routes); run the native
program and the reference on every route and refuse the conversion when any compared field differs (CPU, RAM, VRAM, picture
of every frame, sound, PSG, banks, every frame's row); build the game with the host kit; replay the delivered (compressed)
file on every route; check quick states in a fresh process; write the report (schema 2). The MSX2 adds the V9938 (with its
command engine, timing approximated), the memory mapper and the clock (msx_setup_msx2). Not yet: shared paths. The
five measures stay apart: native code and CPU agreement with the reference are measured on the route played;
hardware fidelity, gameplay and latency are not.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

BIOS_SIZE = 0x8000
SUBROM_SIZE = 0x4000
MAPPER_KIB = (128, 256, 512)
FRAMES = 3600                    # the batch's default route length (the profile's default_frames)
LIVENESS_FIELDS = {key: key for key in ('frames', 'distinct_pictures', 'picture_changes', 'last_picture_change_frame',
                                        'audible_frames', 'last_audible_frame', 'distinct_sound_blocks', 'distinct_ram_states',
                                        'distinct_program_counters')}
WATCH = (0xFC9E, 0xFC9F)


class ConversionError(RuntimeError):
    """The conversion cannot go on; the message is for the player."""


def _main_rom(path: Path, generation: int) -> bytes:
    """A 32 KiB MSX main ROM of `generation` (byte 2Dh: 0 MSX1, 1 MSX2, 2 MSX2+, 3 turbo R)."""
    data = path.read_bytes()
    if len(data) != BIOS_SIZE:
        raise ValueError(f'{path.name}: an MSX BIOS is a 32 KiB main ROM ({len(data)} bytes here).')
    # The BIOS's first bytes are DI then JP to its start (F3 C3 xx xx), on every MSX BIOS and on C-BIOS.
    if data[0] != 0xF3 or data[1] != 0xC3:
        raise ValueError(f'{path.name}: not an MSX BIOS (it does not start with DI and a jump).')
    if data[0x2D] != generation:
        if generation == 0:
            raise ValueError(f'{path.name}: an MSX2 or later BIOS; the MSX profile converts for an MSX1 and needs an MSX1 BIOS.')
        if data[0x2D] == 0:
            raise ValueError(f'{path.name}: an MSX1 BIOS; choose it for the MSX profile, the MSX2 needs an MSX2 BIOS.')
        raise ValueError(f'{path.name}: an MSX2+ or turbo R BIOS; the MSX2 profile needs an MSX2 BIOS (no V9958 yet).')
    return data


def own_bios(path) -> tuple[bytes, str] | None:
    """The player's own MSX1 BIOS (a 32 KiB main ROM): its bytes and SHA-256, None when no path is given."""
    if not path:
        return None
    data = _main_rom(Path(path), 0)
    return data, hashlib.sha256(data).hexdigest()


def own_bios2(main, sub) -> tuple[bytes, str] | None:
    """The player's own MSX2 BIOS: its main ROM and its 16 KiB sub-ROM, as the 64 KiB BIOS source of msx_setup_msx2 (main,
    an empty logo page, sub-ROM) and its SHA-256; None when neither is given."""
    if not main and not sub:
        return None
    if not main or not sub:
        raise ValueError('An MSX2 BIOS of your own is two files: the main ROM and its sub-ROM. Choose both in Options.')
    data = _main_rom(Path(main), 1)
    sub_data = Path(sub).read_bytes()
    if len(sub_data) != SUBROM_SIZE or sub_data[:2] != b'CD':
        raise ValueError(f'{Path(sub).name}: not an MSX2 sub-ROM (16 KiB starting with "CD").')
    image = data + bytes([0xFF]) * 0x4000 + sub_data
    return image, hashlib.sha256(image).hexdigest()


def _bios_files(work: Path, bios_image: bytes, msx2: bool, mapper_kib: int) -> list[str]:
    """The BIOS source written beside the work (main ROM, logo page when there is one, MSX2 sub-ROM) and the runners'
    options for it."""
    (work / 'bios_main.rom').write_bytes(bios_image[:0x8000])
    args = ['--main', str(work / 'bios_main.rom')]
    if len(bios_image) > 0x8000:
        (work / 'bios_logo.rom').write_bytes(bios_image[0x8000:0xC000])
        args += ['--logo', str(work / 'bios_logo.rom')]
    if msx2:
        (work / 'bios_sub.rom').write_bytes(bios_image[0xC000:])
        args += ['--sub', str(work / 'bios_sub.rom'), '--mapper-kib', str(mapper_kib)]
    return args


def _c_string(text: str) -> str:
    """A C string literal of `text` as UTF-8 bytes (octal escapes for everything outside printable ASCII)."""
    out = []
    for byte in text.encode('utf-8'):
        char = chr(byte)
        out.append('\\' + char if char in '"\\' else char if 32 <= byte < 127 and char != '?' else f'\\{byte:03o}')
    return '"' + ''.join(out) + '"'


def _system(model: str) -> dict:
    from .systems import get_profile
    profile = get_profile('msx2' if model == 'msx2' else 'msx')
    return {'id': profile.id, 'name': profile.name}


def _basic_only(data: bytes) -> bool:
    """A cartridge whose header has no INIT and a TEXT pointer: an MSX-BASIC program, which C-BIOS cannot run."""
    for offset in (0, 0x4000):
        if data[offset:offset + 2] == b'AB':
            init = int.from_bytes(data[offset + 2:offset + 4], 'little')
            text = int.from_bytes(data[offset + 8:offset + 10], 'little')
            return init == 0 and text != 0
    return False


def convert(path: Path, *, title=None, output=None, cover=None, use_cover=True, online_cover=True, boxart_dir=None,
            msx_bios=None, frames=FRAMES, passes=3, scan_level=None,
            standard_override=None, profile=None, emit=print, model='msx1', msx2_bios=None, msx2_subrom=None,
            msx2_ram=256, **unused) -> Path:
    from . import __version__, msx_build, msx_cbios
    from .core import ROOT, executable_name
    from .library import entry_lock
    from .msx_rom import read_cartridge
    from .report_schema import write_report
    from .toolchain import describe as toolchain_description
    from . import msx_routes, route_start
    from .conversion_common import check_run_budget, resolve_scan_level
    from .delivery_evidence import (deliver_packed, liveness_summary, replay_packed, replay_routes, report_fields,
                                    require_moving_picture, same_trace)
    started = time.perf_counter()
    if profile is not None:
        raise ConversionError('MSX cartridges are read from their content; TOML cartridge profiles do not apply.')
    try:
        cart = read_cartridge(path)
    except (OSError, ValueError) as error:
        raise ConversionError(str(error)) from None
    guess = cart.guess
    if guess.mapper is None:
        raise ConversionError(f'{Path(path).name}: its mapper could not be recognised ({guess.reason}). '
                              'The MSX profile reads plain, Konami, Konami SCC, ASCII 8 and ASCII 16 cartridges.')
    standard = 'pal' if standard_override == 'pal' else 'ntsc'
    msx2 = model == 'msx2'
    try:
        own = own_bios2(msx2_bios, msx2_subrom) if msx2 else own_bios(msx_bios)
    except (OSError, ValueError) as error:
        raise ConversionError(str(error)) from None
    mapper_kib = int(msx2_ram or 256) if msx2 else 0
    if msx2 and mapper_kib not in MAPPER_KIB:
        raise ConversionError(f'MSX2: the mapper RAM is {", ".join(map(str, MAPPER_KIB))} KiB, not {mapper_kib}.')
    if own is None and _basic_only(cart.data):
        raise ConversionError(f'{Path(path).name} is an MSX-BASIC cartridge: C-BIOS has no BASIC. Choose your own MSX BIOS '
                              'in Options to convert it.')
    title = title or Path(path).stem
    if any(ord(c) < 32 for c in title) or len(title) > 160:
        raise ConversionError('Invalid MSX game title.')
    if output is None:
        from .paths import games_directory
        output = games_directory(system_id=_system(model)['id']) / 'datas/reports' / cart.sha256
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    # The BIOS source: main ROM, logo page (FFh with an own BIOS on the MSX2, absent on the MSX1), then the MSX2 sub-ROM.
    if own is not None:
        bios_image, bios_source = own[0], {'kind': 'own', 'sha256': own[1]}
    else:
        bios_image = msx_cbios.image(standard, emit, model='msx2' if msx2 else 'msx1')
        bios_source = {'kind': 'c-bios', 'version': msx_cbios.VERSION, 'sha256': hashlib.sha256(bios_image).hexdigest()}
    # One work folder per cartridge and BIOS: the probe, the bodies, the learned patterns and the game are those of this pair.
    work = ROOT / '.build' / 'msx' / f"{cart.sha256[:12]}-{hashlib.sha256(bios_image).hexdigest()[:8]}"
    timings = {}
    probe = reference_probe = None
    standard_args = ['--pal'] if standard == 'pal' else []
    with entry_lock(work, timeout=1800):
        work.mkdir(parents=True, exist_ok=True)
        bios_args = _bios_files(work, bios_image, msx2, mapper_kib)
        if guess.mapper != 'plain':
            # A mapper cartridge: the static guess reads LD (nn),A stores only; short reference runs under each mapper
            # settle what the program really drives (msx_build.probe_mapper).
            try:
                reference_probe = msx_build.build_reference(work, emit)
                found, details = msx_build.probe_mapper(reference_probe, cart.data, [*bios_args, *standard_args], guess.mapper)
            except msx_build.MsxBuildError as error:
                raise ConversionError(f'MSX: {error}') from None
            probe = {'chosen': found, 'static_guess': guess.mapper, 'runs': details, 'frames': msx_build.PROBE_FRAMES}
            if found is not None and found != guess.mapper:
                emit(f'MSX: the probe runs say {found}, not {guess.mapper} (the static guess).')
                from dataclasses import replace
                guess = replace(guess, mapper=found, reason=f'{guess.reason}; probe runs: {found}')
                (work / 'native.patterns').unlink(missing_ok=True)      # learned under the other mapper
        cartridge = msx_build.padded(cart.data, guess.mapper)
        level = resolve_scan_level(scan_level)
        frames, passes = int(frames or FRAMES), int(passes or 3)
        check_run_budget(passes, frames, 'MSX: a conversion runs 1 to 10 learning passes on routes of 1 to 10,000 frames.')
        machine_args = [*bios_args, *guess.arguments(), *standard_args]
        watch = [w for a in WATCH for w in ('--watch', f'{a:04X}')]
        folder = work / 'routes'
        folder.mkdir(parents=True, exist_ok=True)
        reference_exe = reference_probe or msx_build.build_reference(work, emit)

        def options(name: str, count: int, text: str) -> list[str]:
            """A route's options for every program (the check, the reference, the game): its length, its script."""
            script = folder / f'{name}.inputs'
            if not script.is_file() or script.read_text(encoding='ascii') != text:
                script.write_text(text, encoding='ascii', newline='\n')
            return ['--frames', str(count), *watch, '--script', str(script)]

        def reference_rows(name: str, count: int, text: str) -> tuple[dict, Path]:
            rows = folder / f'{name}-reference.csv'
            return msx_build.run(reference_exe, [*machine_args, *options(name, count, text), '--rows', str(rows)], cartridge), rows

        # The start (route_start, as the PC Engine): each variant played on the reference against the route without input.
        phase = time.perf_counter()
        play_frames = max(frames, msx_routes.PLAY_FRAMES)
        seed = msx_routes.route_seed(cart.sha256, 'play')
        variants = msx_routes.candidates(play_frames)
        emit(f'MSX: choosing how the play route starts ({len(variants)} variants on the reference).')
        try:
            played = replay_routes([('baseline', None), *((f'start-{msx_routes.variant_name(v)}', v) for v in variants)],
                                   lambda row: reference_rows(row[0], play_frames, '' if row[1] is None else
                                                              msx_routes.script(msx_routes.events(play_frames, seed, row[1]))),
                                   workers=4)
        except msx_build.MsxBuildError as error:
            raise ConversionError(f'MSX: {error}') from None

        def pictures(rows: Path) -> dict:
            return {row.frame: row.picture for row in msx_build.frame_rows(rows)}
        baseline = pictures(played[0][1])
        results = {}
        for variant, (_result, rows) in zip(variants, played[1:]):
            mine = pictures(rows)
            results[variant] = {'liveness': report_fields(liveness_summary(msx_build.frame_rows(rows)), LIVENESS_FIELDS),
                                'divergence': route_start.divergence(mine, baseline),
                                'reach': route_start.reach(mine, baseline, msx_routes.walk_start(msx_routes.presses_of(variant)),
                                                           msx_routes.QUIET_WALK)}
        chosen = route_start.choose_start(results, play_frames, msx_routes.variant_order)
        start_record = {'presses': msx_routes.presses_of(chosen), 'confirm': chosen[1] if isinstance(chosen, tuple) else None,
                        'rule': 'alive until the last 120 frames, then most pictures the walk reached that no input showed, '
                                'then most frames the input changed, then the fewest presses',
                        'variants': {msx_routes.variant_name(v): r for v, r in results.items()}}
        emit(f'MSX: the play route starts with {msx_routes.variant_name(chosen)} press(es) of fire'
             f'{" and RETURN" if isinstance(chosen, tuple) else ""}.')
        routes = msx_routes.routes(cart.sha256, frames=frames, level=level, variant=chosen)
        timings['start_choice'] = round(time.perf_counter() - phase, 3)

        emit(f'{"MSX2" if msx2 else "MSX"}: {title}: {cart.size // 1024} KiB, {guess.mapper} mapper, '
             f'{"your own BIOS" if own else "C-BIOS " + msx_cbios.VERSION}; translating the cartridge and the BIOS, learning on '
             f'{len(routes)} route(s) ({", ".join(name for name, _, _ in routes)}).')
        phase = time.perf_counter()
        try:
            check, pass_counts = msx_build.learn(work, cartridge, bios_image,
                                                 [[*machine_args, *options(*route)] for route in routes], emit,
                                                 passes=passes, workers=2)
        except msx_build.MsxBuildError as error:
            raise ConversionError(f'MSX: {error}') from None
        timings['translation_and_learning'] = round(time.perf_counter() - phase, 3)
        phase = time.perf_counter()
        emit('MSX: comparing the native runs with the reference interpreter, field by field and frame by frame.')

        def compare(route):
            name = route[0]
            rows_native = folder / f'{name}-native.csv'
            native = msx_build.run(check, [*machine_args, *options(*route), '--rows', str(rows_native)], cartridge)
            reference, rows_reference = reference_rows(*route)
            differing = msx_build.differences(native, reference)
            if rows_native.read_bytes() != rows_reference.read_bytes():
                differing['frame_rows'] = ('native', 'reference')
            return native, reference, rows_reference, differing
        try:
            compared = dict(zip((route[0] for route in routes), replay_routes(routes, compare, workers=2)))
        except msx_build.MsxBuildError as error:
            raise ConversionError(f'MSX: {error}') from None
        timings['reference_comparison'] = round(time.perf_counter() - phase, 3)
        for name, (_native, _reference, _rows, differing) in compared.items():
            if differing:
                raise ConversionError(f'MSX: on the {name} route the native run differs from the reference '
                                      f'({", ".join(sorted(differing))}); nothing was built.')
        liveness = {name: liveness_summary(msx_build.frame_rows(rows)) for name, (_, _, rows, _) in compared.items()}
        for name, record in liveness.items():
            if name != 'attract':
                require_moving_picture(record, lambda name=name: ConversionError(
                    f'MSX: {title}: the picture never changes on the {name} route; nothing was built.'))
        phase = time.perf_counter()
        emit('MSX: building the game.')
        presentation = {'rom_path': Path(path), 'cover': Path(cover) if cover else None, 'use_cover': use_cover,
                        'online_cover': online_cover, 'boxart_dir': boxart_dir}
        prepared = prepare_game(work, cart, cartridge, title, guess, standard, bios_image, emit, model=model,
                                mapper_kib=mapper_kib, presentation=presentation)
        try:
            executable = msx_build.build(work, ('game',), emit)['game']
        except Exception as error:  # noqa: BLE001 - the build's own log names the cause
            raise ConversionError(f'MSX: the game could not be built ({error}).') from None
        timings['game_build'] = round(time.perf_counter() - phase, 3)
        # The delivered file (G5): the compressed copy the player receives, replayed headless on every route and compared
        # with the fresh reference (report and every frame's row); delivery_evidence falls back to the build if UPX fails.
        phase = time.perf_counter()
        delivered = deliver_packed(executable, work / ('packed-' + executable.name), 'MSX2' if msx2 else 'MSX', emit)

        def replay(route):
            name = route[0]
            return msx_build.run_game(delivered.path, [*options(*route), '--rows', str(folder / f'{name}-packed.csv')],
                                      folder / f'{name}-packed.json')

        def same(route, result):
            name = route[0]
            return (not msx_build.differences(result, compared[name][1])
                    and same_trace(folder / f'{name}-packed.csv', compared[name][2]))

        try:
            replay_packed(delivered, routes, replay, same=same, workers=3, mismatch=lambda route: ConversionError(
                f'MSX: the delivered (compressed) game differs from the reference on the {route[0]} route; nothing was published.'))
        except msx_build.MsxBuildError as error:
            raise ConversionError(f'MSX: {error}') from None
        timings['packed_replay'] = round(time.perf_counter() - phase, 3)
        # Quick states (G6) on the delivered file: saved near the play route's end, continued by a fresh process.
        phase = time.perf_counter()
        emit('MSX: checking quick states in a fresh process.')
        play = next(route for route in routes if route[0] == 'play')
        try:
            states = check_states(delivered.path, work / 'states', 'play', play[1], options(*play)[2:],
                                  folder / 'play-packed.csv')
        except msx_build.MsxBuildError as error:
            raise ConversionError(f'MSX: {error}') from None
        timings['quick_states'] = round(time.perf_counter() - phase, 3)
    final_checks = []
    for name, count, text in routes:
        native = compared[name][0]
        executed = native['native_steps'] + native['fallback_steps']
        final_checks.append({
            'name': name, 'frames': native['frames'], 'script_sha256': hashlib.sha256(text.encode('ascii')).hexdigest(),
            'script_events': len(text.splitlines()), 'native_steps': native['native_steps'],
            'halt_steps': native['halt_steps'], 'interpreted_steps': native['fallback_steps'],
            'interpreted_cycles': native['fallback_cycles'], 'guarded_steps': native['guarded_steps'],
            'interpreter_percent': round(100 * native['fallback_steps'] / max(1, executed), 6),
            'reference_match': True, 'compared_fields': list(msx_build.COMPARED),
            'frame_trace': native['frame_trace'], 'ram_hash': native['ram_fnv'], 'vram_hash': native['vram_fnv'],
            'image_hash': native['frame_fnv'], 'pcm_hash': native['audio_fnv'], 'pcm_samples': native['audio_samples'],
            'interrupts': native['interrupts'], 'frame_rows_equal': True, 'packed_rows_equal': True,
            'liveness': report_fields(liveness[name], LIVENESS_FIELDS)})
    native = compared['play'][0]
    native_coverage = all(row['interpreted_steps'] == 0 for row in final_checks)
    report = {'tool': 'Retro-Recomp', 'version': __version__, 'created_utc': datetime.now(timezone.utc).isoformat(),
        'system': _system(model), 'rom': {'sha256': cart.sha256, 'bytes': cart.size, 'file': Path(path).name},
        'converted': True,
        'compiler': {'engine': 'the banked Z80 chain (retrorecomp/z80_chain.py), machine "msx"',
                     'native_cpu': 'every instruction position of the cartridge and of the BIOS translated ahead of time; '
                                   'code run from RAM learned and translated with byte guards'},
        'msx_checks': {'machine': 'MSX2' if msx2 else 'MSX1', 'mapper': guess.mapper, 'mapper_reason': guess.reason,
                       'mapper_candidates': list(guess.candidates), 'cartridge_base': f'{guess.base:04X}',
                       'mirrored': guess.mirrored, 'bios': bios_source, 'standard': standard,
                       'mapper_probe': probe,
                       'learning_passes_fallback_steps': pass_counts,
                       'learned_patterns': len((work / 'native.patterns').read_text(encoding='utf-8').split())
                       if (work / 'native.patterns').is_file() else 0,
                       **({'mapper_ram_kib': mapper_kib, 'rtc': 'RP5C01 started on Saturday 2000-01-01 12:00:00, machine time only',
                           'v9938_commands_started': (native.get('v9938') or {}).get('cmd_writes', 0),
                           'v9938_commands_by_kind': dict(zip(('stop', 'stop1', 'stop2', 'stop3', 'point', 'pset', 'srch', 'line', 'lmmv',
                                                               'lmmm', 'lmcm', 'lmmc', 'hmmv', 'hmmm', 'ymmm', 'hmmc'),
                                                              ((native.get('v9938') or {}).get('engine') or [0] * 24)[8:24])),
                           'v9938_command_timing': 'approximated: an average cost per byte or dot in three classes, no access slots',
                           'lines_per_frame': (native.get('v9938') or {}).get('lines_per_frame'),
                           'lines': (native.get('v9938') or {}).get('lines')} if msx2 else {})},
        'final_checks': final_checks, 'scan_level': level, 'route_start': start_record,
        'sound_routes': {name: bool(record['audible_frames']) for name, record in liveness.items()},
        'native_validation': {'passed': True, 'reference_kind': 'the same machine with every instruction on the reference '
                                                                'interpreter (corrected SuperZazu, MSX wait states)',
                              'cpu_agreement': True, 'cpu_fidelity_validated': False, 'independent_cpu_oracle': False,
                              'hardware_fidelity_validated': False, 'full_game_validated': False,
                              'sound_heard': any(record['audible_frames'] for record in liveness.values()),
                              **delivered.validation_fields()},
        **delivered.report_fields(), 'delivered_file': delivered.kind,
        'native_coverage': native_coverage,
        'video_model': {'chip': 'V9938 (our own C, line by line; commands: all twelve, timing approximated)' if msx2 else
                                'TMS9918A (our own C, line by line)',
                        'standard': 'decided by your own MSX2 BIOS (R#9)' if msx2 and own is not None else standard,
                        'display_aspect': '4:3'},
        'audio_cpu': None,
        'audio_model': {'kind': 'AY-3-8910, key click and Konami SCC (our own C); mixing levels stated, not validated',
                        'rate': 44100, 'channels': 1},
        'counter_unit': 'cycles', 'physical_latency_measured': False, 'latency_ms': None,
        'hardware_accuracy_validated': False, 'full_game_validated': False,
        'game_states': {'supported': True, 'save_key': 'F8', 'load_key': 'F9',
                        'schema': 'RRMSX2-STATE-1' if msx2 else 'RRMSX-STATE-1',
                        'compatibility': 'the exact cartridge, BIOS, options and build',
                        'fresh_process_verified': True, 'validation': states},
        'artwork': prepared['artwork'], 'windows_metadata': prepared['windows_metadata'],
        'executable': executable_name(title), 'build_executable': str(executable), 'toolchain': toolchain_description(),
        'build_directory': str(work),
        'conversion_phases_seconds': timings, 'conversion_wall_seconds': round(time.perf_counter() - started, 3),
        'qualification_scope': {'controls': 'joystick 1 and the keyboard as the default mapping drives them: directions on '
                                            'the joystick and the cursor keys, fire on trigger A and SPACE, RETURN, 1 and 2',
                                'universal_zero_fallback_claim': False}}
    write_report(output / 'conversion-report.json', report)
    emit(f'MSX: {title} ready ({"no interpreter on the routes played" if native_coverage else "interpreter fallback reported"}).')
    return executable


STATE_LAYOUT = 'msx-state-2'     # raised whenever msx_state.c or msx_state_file.inc writes another body (2: R#18 per line)
STATE_SETTLE = 600               # frames a fresh process continues after it loaded a quick state


def damaged_states(state: bytes) -> dict[str, bytes]:
    """Damaged copies of a quick state (state_envelope.h: magic 0, schema 8, machine 12, identity 16, length 80, CRC 84;
    then the build binding 88 and the payload), by what is wrong with them: the game must refuse every one (exit 4)."""
    def flipped(offset: int) -> bytes:
        data = bytearray(state)
        data[offset] ^= 0x80
        return bytes(data)
    return {'empty': b'', 'header-cut': state[:40], 'one-byte-short': state[:-1], 'body-cut': state[:len(state) // 2],
            'magic': flipped(0), 'schema': flipped(8), 'machine': flipped(12), 'identity': flipped(16), 'length': flipped(80),
            'crc': flipped(84), 'binding': flipped(88), 'payload': flipped(len(state) - 1),
            'not-a-state': b'not a state.' * 4096}


def check_states(game: Path, folder: Path, name: str, frames: int, route_rest: list[str], expected: Path) -> dict:
    """F8 at a frame of the route, F9 in a fresh process (conversion_gates.check_quick_states, as the PC Engine): the loaded
    process continues the uninterrupted trace `expected` for STATE_SETTLE frames; damaged states are refused and left as they
    were; a missing state is refused and creates nothing. `route_rest`: the route's options without its frame count."""
    from . import msx_build
    from .conversion_gates import check_quick_states
    folder.mkdir(parents=True, exist_ok=True)
    at = max(60, frames - STATE_SETTLE - 60)
    state = folder / 'quick.rrstate'
    state.unlink(missing_ok=True)

    def continued():
        msx_build.run_game(game, ['--frames', str(at + 1), *route_rest, '--rows', str(folder / 'save.csv'),
                                  '--save-state', str(state), '--save-at', str(at)], folder / 'save.json')
        msx_build.run_game(game, ['--frames', str(at + STATE_SETTLE), *route_rest, '--rows', str(folder / 'load.csv'),
                                  '--load-state', str(state)], folder / 'load.json')
        return (expected.read_text(encoding='ascii').splitlines()[1:],
                (folder / 'load.csv').read_text(encoding='ascii').splitlines()[1:])

    def refused(path: Path) -> bool:
        return msx_build.game_exit_code(game, ['--frames', '1', '--load-state', str(path)]) == 4
    return check_quick_states(folder, state, machine='MSX', route=name, at=at, settle=STATE_SETTLE, continued=continued,
                              refused=refused, damaged=damaged_states, error=ConversionError)


def state_binding(bios: bytes, guess, standard: str, model: str, mapper_kib: int) -> bytes:
    """The quick state's build binding (RR_MSX_STATE_ABI, 32 bytes): a state of another layout, BIOS, mapper, cartridge base,
    mirror, standard, model or RAM size is refused as incompatible."""
    text = '\n'.join([STATE_LAYOUT, hashlib.sha256(bios).hexdigest(), guess.mapper, f'{guess.base:04X}',
                      str(int(guess.mirrored)), standard, model, str(mapper_kib)])
    return hashlib.sha256(text.encode('ascii')).digest()


def prepare_game(work: Path, cart, cartridge: bytes, title: str, guess, standard: str, bios: bytes, emit=print, *,
                 model: str = 'msx1', mapper_kib: int = 0, presentation: dict | None = None) -> dict:
    """The game's resources beside the project: the cartridge as the checked runs saw it (103, padded to whole banks), the BIOS
    (104), the notices (203), the identity (205), the Windows metadata and icon, and msx_game.h. `presentation` (the
    player's cover options: rom_path, cover, use_cover, online_cover, boxart_dir) gives the icon its cover, found as on the
    other machines (artwork.prepare_icon: an explicit file, the BoxArt folder, then the online catalogues of the profile)."""
    from .core import ASSETS, executable_name
    from .metadata import write_game_metadata
    from .resources import embed_resources
    _write_bytes = lambda path, data: path.write_bytes(data) if not path.is_file() or path.read_bytes() != data else None
    _write_bytes(work / 'cartridge.rom', cartridge)
    _write_bytes(work / 'slot0.rom', bios)
    notices = [(ASSETS / name).read_text(encoding='utf-8') for name in
               ('LICENSE', 'licenses/SDL2.md', 'licenses/xbr.md', 'licenses/Noto.md', 'licenses/llvm-mingw.md',
                'licenses/superzazu-z80.md', 'licenses/cbios.md') if (ASSETS / name).is_file()]
    _write_bytes(work / 'notices.txt', '\n\n'.join(notices).encode('utf-8'))
    _write_bytes(work / 'runtime_feedback_config.h',
                 f'#define RR_FEEDBACK_SYSTEM "{_system(model)['id']}"\n#define RR_FEEDBACK_IDENTITY "{cart.sha256}"\n'.encode('ascii'))
    _write_bytes(work / 'export-identity.bin', b'[Retro-Recomp]\0' + cart.sha256.encode('ascii') + b'\0')
    system_id = _system(model)['id']
    artwork = {'embedded': False, 'source': 'disabled'}
    if presentation is not None:
        from .artwork import prepare_icon
        from .core import ROOT
        from .paths import boxart_cache_directory
        artwork = prepare_icon(work, presentation['rom_path'], title, presentation.get('boxart_dir') or ROOT / 'BoxArt',
                               explicit=presentation.get('cover'), online=presentation.get('online_cover', True),
                               enabled=presentation.get('use_cover', True), cache_directory=boxart_cache_directory(system_id),
                               system_id=system_id, emit=emit)
    (work / 'artwork.json').write_text(json.dumps(artwork, indent=2), encoding='utf-8')
    metadata = write_game_metadata(work, title, executable_name(title), light_phaser=False, icon=bool(artwork['embedded']),
                                   standard=standard, system_id=system_id)
    (work / 'content.rc').write_text('#pragma code_page(65001)\n103 RCDATA "cartridge.rom"\n104 RCDATA "slot0.rom"\n'
                                     '203 RCDATA "notices.txt"\n205 RCDATA "export-identity.bin"\n#include "game_resources.rc"\n',
                                     encoding='utf-8', newline='\n')
    embed_resources(work, {103: work / 'cartridge.rom', 104: work / 'slot0.rom', 203: work / 'notices.txt',
                           205: work / 'export-identity.bin'})
    mappers = {'plain': 'MSX_MAPPER_PLAIN', 'konami': 'MSX_MAPPER_KONAMI', 'konami-scc': 'MSX_MAPPER_KONAMI_SCC',
               'ascii8': 'MSX_MAPPER_ASCII8', 'ascii16': 'MSX_MAPPER_ASCII16'}
    (work / 'msx_game.h').write_text('#pragma once\n'
        f'#define RR_MSX_TITLE {_c_string(title)}\n#define RR_MSX_IDENTITY "{cart.sha256}"\n'
        f'#define RR_MSX_MAPPER {mappers[guess.mapper]}\n'
        f'#define RR_MSX_CART_BASE 0x{guess.base:04X}\n#define RR_MSX_MIRRORED {int(guess.mirrored)}\n'
        f'#define RR_MSX_PAL {int(standard == "pal")}\n#define RR_MSX_MODEL {2 if model == "msx2" else 1}\n'
        f'#define RR_MSX_MAPPER_SEGMENTS {mapper_kib // 16}\n'
        f'#define RR_MSX_STATE_ABI {{{", ".join(f"0x{b:02X}" for b in state_binding(bios, guess, standard, model, mapper_kib))}}}\n',
        encoding='utf-8', newline='\n')
    return {'artwork': artwork, 'windows_metadata': metadata}
