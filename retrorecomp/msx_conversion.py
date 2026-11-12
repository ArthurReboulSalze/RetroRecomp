"""MSX conversion (experimental): an MSX1 or MSX2 cartridge and its BIOS translated by the banked Z80 chain, checked against
the reference interpreter, built into a game.

The steps: read the cartridge and guess its mapper (msx_rom.py); choose the BIOS (the player's own MSX BIOS, checked: a 32 KiB
main ROM on the MSX1, the main ROM and its 16 KiB sub-ROM on the MSX2; or C-BIOS 0.29a, pinned); generate the bodies of both and learn the code run from RAM (msx_build.learn, at most three passes) on a
route that boots, waits, presses SPACE and the trigger; run the native program and the reference on the same route and refuse
the conversion when any compared field differs (CPU, RAM, VRAM, picture of every frame, sound, PSG, banks); build the game
with the host kit; write the report (schema 2). The MSX2 adds the V9938 (with its command engine, timing approximated), the
memory mapper and the clock (msx_setup_msx2). Not yet: compressed delivery and its replay, quick states, shared paths. The
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
FRAMES = 1200
START_EVENTS = ('600:key:8:0:1', '610:key:8:0:0', '660:joy:0:2F', '670:joy:0:3F')
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


def convert(path: Path, *, title=None, output=None, msx_bios=None, frames=FRAMES, scan_level=None,
            standard_override=None, profile=None, emit=print, model='msx1', msx2_bios=None, msx2_subrom=None,
            msx2_ram=256, **unused) -> Path:
    from . import __version__, msx_build, msx_cbios
    from .core import ROOT, executable_name
    from .library import entry_lock
    from .msx_rom import read_cartridge
    from .report_schema import write_report
    from .toolchain import describe as toolchain_description
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
    bios_main, bios_logo, bios_sub = bios_image[:0x8000], bios_image[0x8000:0xC000], bios_image[0xC000:]
    probe = None
    if guess.mapper != 'plain':
        # A mapper cartridge: the static guess reads LD (nn),A stores only; a short reference run under each mapper settles
        # what the program really drives (Aleste reaches its registers through computed addresses).
        probe_work = ROOT / '.build' / 'msx' / f"{cart.sha256[:12]}-{hashlib.sha256(bios_image).hexdigest()[:8]}"
        probe_args = ['--main', str(probe_work / 'bios_main.rom')]
        with entry_lock(probe_work, timeout=1800):
            probe_work.mkdir(parents=True, exist_ok=True)
            (probe_work / 'bios_main.rom').write_bytes(bios_main)
            if bios_logo:
                (probe_work / 'bios_logo.rom').write_bytes(bios_logo)
                probe_args += ['--logo', str(probe_work / 'bios_logo.rom')]
            if msx2:
                (probe_work / 'bios_sub.rom').write_bytes(bios_sub)
                probe_args += ['--sub', str(probe_work / 'bios_sub.rom'), '--mapper-kib', str(mapper_kib)]
            try:
                reference_probe = msx_build.build_reference(probe_work, emit)
                found, details = msx_build.probe_mapper(reference_probe, cart.data, probe_args)
            except msx_build.MsxBuildError as error:
                raise ConversionError(f'MSX: {error}') from None
        probe = {'chosen': found, 'static_guess': guess.mapper, 'runs': details, 'frames': msx_build.PROBE_FRAMES}
        if found is not None and found != guess.mapper:
            emit(f'MSX: the probe runs say {found}, not {guess.mapper} (the static guess).')
            from dataclasses import replace
            guess = replace(guess, mapper=found, reason=f'{guess.reason}; probe runs: {found}')
    cartridge = msx_build.padded(cart.data, guess.mapper)
    # One work folder per cartridge and BIOS: the bodies, the learned patterns and the game are those of this pair.
    work = ROOT / '.build' / 'msx' / f"{cart.sha256[:12]}-{hashlib.sha256(bios_image).hexdigest()[:8]}"
    timings = {}
    with entry_lock(work, timeout=1800):
        work.mkdir(parents=True, exist_ok=True)
        (work / 'bios_main.rom').write_bytes(bios_main)
        bios_args = ['--main', str(work / 'bios_main.rom')]
        if bios_logo:
            (work / 'bios_logo.rom').write_bytes(bios_logo)
            bios_args += ['--logo', str(work / 'bios_logo.rom')]
        if msx2:
            (work / 'bios_sub.rom').write_bytes(bios_sub)
            bios_args += ['--sub', str(work / 'bios_sub.rom'), '--mapper-kib', str(mapper_kib)]
        route = [*bios_args, *guess.arguments(), '--frames', str(max(300, min(int(frames or FRAMES), 6000))),
                 *(w for a in WATCH for w in ('--watch', f'{a:04X}')), *(w for e in START_EVENTS for w in ('--event', e)),
                 *(['--pal'] if standard == 'pal' else [])]
        emit(f'{"MSX2" if msx2 else "MSX"}: {title}: {cart.size // 1024} KiB, {guess.mapper} mapper, '
             f'{"your own BIOS" if own else "C-BIOS " + msx_cbios.VERSION}; translating the cartridge and the BIOS.')
        phase = time.perf_counter()
        try:
            check, passes = msx_build.learn(work, cartridge, bios_image, route, emit)
        except msx_build.MsxBuildError as error:
            raise ConversionError(f'MSX: {error}') from None
        timings['translation_and_learning'] = round(time.perf_counter() - phase, 3)
        phase = time.perf_counter()
        emit('MSX: comparing the native run with the reference interpreter, field by field and frame by frame.')
        reference_exe = check.with_name(check.name.replace('msx_check', 'msx_reference'))
        native = msx_build.run(check, route, cartridge)
        reference = msx_build.run(reference_exe, route, cartridge)
        timings['reference_comparison'] = round(time.perf_counter() - phase, 3)
        differing = msx_build.differences(native, reference)
        if differing:
            names = ', '.join(sorted(differing))
            raise ConversionError(f'MSX: the native run differs from the reference ({names}); nothing was built.')
        phase = time.perf_counter()
        emit('MSX: building the game.')
        prepared = prepare_game(work, cart, cartridge, title, guess, standard, bios_image, emit, model=model,
                                mapper_kib=mapper_kib)
        try:
            executable = msx_build.build(work, ('game',), emit)['game']
        except Exception as error:  # noqa: BLE001 - the build's own log names the cause
            raise ConversionError(f'MSX: the game could not be built ({error}).') from None
        timings['game_build'] = round(time.perf_counter() - phase, 3)
    executed = native['native_steps'] + native['fallback_steps']
    native_coverage = native['fallback_steps'] == 0
    row = {'name': 'boot-and-start', 'frames': native['frames'], 'native_steps': native['native_steps'],
           'halt_steps': native['halt_steps'], 'interpreted_steps': native['fallback_steps'],
           'interpreted_cycles': native['fallback_cycles'], 'guarded_steps': native['guarded_steps'],
           'interpreter_percent': round(100 * native['fallback_steps'] / max(1, executed), 6),
           'reference_match': True, 'compared_fields': list(msx_build.COMPARED),
           'frame_trace': native['frame_trace'], 'ram_hash': native['ram_fnv'], 'vram_hash': native['vram_fnv'],
           'image_hash': native['frame_fnv'], 'pcm_hash': native['audio_fnv'], 'pcm_samples': native['audio_samples'],
           'interrupts': native['interrupts'], 'events': list(START_EVENTS)}
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
                       'learning_passes_fallback_steps': passes,
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
        'final_checks': [row],
        'native_validation': {'passed': True, 'reference_kind': 'the same machine with every instruction on the reference '
                                                                'interpreter (corrected SuperZazu, MSX wait states)',
                              'cpu_agreement': True, 'cpu_fidelity_validated': False, 'independent_cpu_oracle': False,
                              'hardware_fidelity_validated': False, 'full_game_validated': False,
                              # The game is built from the same bodies and machine as the checked program, but not run here.
                              'delivered_executable_run': False},
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
        'game_states': {'supported': False, 'reason': 'not yet on the MSX'},
        'packed_delivery': {'replayed': False, 'reason': 'the checks ran on the build executable; the packed copy that publication '
                                                         'writes (see packing) is not replayed against the reference on the MSX yet'},
        'artwork': prepared['artwork'], 'windows_metadata': prepared['windows_metadata'],
        'executable': executable_name(title), 'build_executable': str(executable), 'toolchain': toolchain_description(),
        'build_directory': str(work), 'scan_level': scan_level,
        'conversion_phases_seconds': timings, 'conversion_wall_seconds': round(time.perf_counter() - started, 3),
        'qualification_scope': {'controls': 'joystick 1 and 2, the keyboard; the route presses SPACE and trigger A',
                                'universal_zero_fallback_claim': False}}
    write_report(output / 'conversion-report.json', report)
    emit(f'MSX: {title} ready ({"no interpreter on the route played" if native_coverage else "interpreter fallback reported"}).')
    return executable


def prepare_game(work: Path, cart, cartridge: bytes, title: str, guess, standard: str, bios: bytes, emit=print, *,
                 model: str = 'msx1', mapper_kib: int = 0) -> dict:
    """The game's resources beside the project: the cartridge as the checked runs saw it (103, padded to whole banks), the BIOS
    (104), the notices (203), the identity (205), the Windows metadata and icon, and msx_game.h."""
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
    artwork = {'embedded': False, 'source': 'disabled'}
    (work / 'artwork.json').write_text(json.dumps(artwork, indent=2), encoding='utf-8')
    metadata = write_game_metadata(work, title, executable_name(title), light_phaser=False, icon=False,
                                   standard=standard, system_id=_system(model)['id'])
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
        f'#define RR_MSX_MAPPER_SEGMENTS {mapper_kib // 16}\n', encoding='utf-8', newline='\n')
    return {'artwork': artwork, 'windows_metadata': metadata}
