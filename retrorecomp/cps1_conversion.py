"""Capcom CPS-1 and CPS-2 native conversion through the shared batch/export contract (`family`).

Every route runs twice in the same build: once with every instruction forced
through the reference interpreters (the fresh reference) and once with the
translated 68000/Z80 code. Their per-frame CPU, RAM, image and PCM traces must
be identical, before and after compression, and quick states must continue
the saved timeline in a fresh process. Interpreted instructions that remain
are counted and reported; RAM code they ran becomes guarded native code in
the next pass. Nothing is written beside the ROMs.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import time

from . import __version__, path_profiles, timings as stages
from .conversion_common import check_exit, resolve_scan_level, spawn
from .conversion_gates import continuation_difference, require, require_same_file
from .core import ConversionError, executable_name
from .delivery_evidence import (FrameRow, deliver_packed, liveness_summary, replay_packed, report_fields,
                                require_moving_picture, same_trace, silent_hash, silent_sound_hash)
from .library import atomic_json, entry_lock, file_sha256
from .report_schema import write_report
from .paths import ROOT
from .toolchain import describe as toolchain_description

STATE_SETTLE = 600   # frames continued after a quick state is loaded
# The report keys of a route's liveness, from the common record of delivery_evidence (the names CPS-1 has always written).
LIVENESS_FIELDS = {'frames': 'frames', 'distinct_pictures': 'distinct_pictures', 'picture_changes': 'picture_changes',
                   'last_picture_change_frame': 'last_picture_change_frame', 'audible_frames': 'audible_frames',
                   'last_audible_frame': 'last_audible_frame'}


def trace_rows(trace: Path):
    """The per-frame rows of a route's trace (frame, cpu, ram, image, sound, samples) for `delivery_evidence`.

    A frame is audible when its sound hash is not the hash of silence for its number of samples."""
    for line in trace.read_text(encoding='ascii').splitlines():
        fields = line.split(',')
        if len(fields) != 6 or not fields[0].isdigit():   # the first line names the columns
            continue
        frame, image, sound, samples = int(fields[0]), fields[3], fields[4], int(fields[5])
        yield FrameRow(frame, image, sound=sound, audible=sound != silent_hash(samples))


def route_liveness(trace: Path) -> dict:
    """Picture and sound activity of one route, read from its per-frame trace (frame, cpu, ram, image, sound, samples).

    A picture change is a frame whose image hash differs from the previous frame's; a frame is audible when its sound hash
    is not the hash of silence. This is evidence that the route reached a moving picture and sound (gate G8), nothing
    more: it says nothing about what the picture shows or about play. The counting is `delivery_evidence.liveness_summary`."""
    return report_fields(liveness_summary(trace_rows(trace)), LIVENESS_FIELDS)


def routes(identity: str, *, frames: int, level: str, six_buttons: bool) -> list[tuple[str, int, str]]:
    """(name, frames, script): attract, a credited play route, then long routes."""
    # The CPS-2 plays the CPS-1's routes (the same pad, the same credit rule): random_routes.py is shared by every console and names only the CPS-1.
    from .random_routes import long_route, long_routes, cps1_script
    from .scan_levels import cps1_budget
    budget = cps1_budget(level)
    play = replace(long_route('cps1', identity, 1000, frames=max(frames, 1800), six_buttons=six_buttons), name='play')
    rows = [('attract', frames, '0 000 000\n')] if budget['attract'] else []
    rows.append(('play', play.frames, cps1_script(play)))
    for route in long_routes('cps1', identity, count=budget['route_count'], frames=budget['route_frames'],
                             six_buttons=six_buttons):
        rows.append((route.name, route.frames, cps1_script(route)))
    return rows


def run(executable: Path, folder: Path, name: str, frames: int, script: Path, *extra: str,
        ends_at: int | None = None, label: str = 'CPS-1') -> dict:
    report, trace = folder / (name + '.json'), folder / (name + '.csv')
    completed = spawn([str(executable), '--headless', '--frames', str(frames), '--script', str(script),
                       '--trace', str(trace), '--report', str(report), *extra],
                      cwd=folder, timeout=max(300, frames // 20), capture_output=True, text=True)

    def failure(result):
        detail = (result.stderr or result.stdout).strip().splitlines()[-1:] or ['no output']
        return ConversionError(f'{label} {name} run failed ({result.returncode}): {detail[0]}')
    check_exit(completed, failure)
    result = json.loads(report.read_text(encoding='utf-8'))
    if result['frames'] != (frames if ends_at is None else ends_at) or result['save_failed']:
        raise ConversionError(f'{label} {name} run ended early or could not save its state.')
    result['trace'] = trace
    return result


def merge(observations: dict, fallback: dict) -> bool:
    """Add newly observed work-RAM/Z80-RAM code; True when anything was new."""
    changed = False
    for key, fields in (('m68k_ram', ('offset', 'words')), ('m68k_gfx', ('offset', 'words')),
                       ('z80_ram', ('address', 'bytes'))):
        known = {tuple(row[f] for f in fields) for row in observations.setdefault(key, [])}
        for row in fallback.get(key, ()):
            item = tuple(row[f] for f in fields)
            if item not in known:
                known.add(item); observations[key].append({f: row[f] for f in fields}); changed = True
    return changed


def learned(identity: str, memory: Path) -> dict:
    """The private observations of earlier conversions of this exact set: work-RAM and sound-RAM code that
    this player's native runs met and could not cover. Raw words, so they never leave the library; the shared
    paths are numbers made apart (`cps1_knowledge`, from the fresh reference runs)."""
    observations = {'m68k_ram': [], 'm68k_gfx': [], 'z80_ram': []}
    previous = memory / 'observations.json'
    if previous.is_file():
        try:
            merge(observations, json.loads(previous.read_text(encoding='utf-8')))
        except (OSError, ValueError, KeyError, TypeError):
            pass
    return observations


def feedback_rows(identity: str, system: str = 'cps1') -> dict:
    """The player's opt-in gameplay feedback (kinds 15 and 16) as build hints. They have no provenance: they are
    used by this conversion, which checks the native code against the fresh reference, but never written into
    the library's observations and never shared. Kind 14 (a ROM instruction left interpreted) is not read: the
    program ROM is swept whole, so there is nothing a path could add (see `cps1_knowledge`)."""
    from .feedback import records
    shift = 3 if system == 'cps2' else 0       # the CPS-2's record kinds are the CPS-1's plus three (native/cps1_machine.c, FB_KIND)
    return {'m68k_ram': [{'offset': r.address, 'words': r.data.hex()} for r in records(system, identity, 15 + shift)
                         if not r.address & 1 and r.address < 0x10000 and len(r.data) % 2 == 0],
            'z80_ram': [{'address': r.address, 'bytes': r.data.hex()} for r in records(system, identity, 16 + shift)
                        if 0xd000 <= r.address < 0xd800 and len(r.data) == 4]}


def fresh_observations(reference: dict) -> dict:
    """The work-RAM and sound-RAM code the fresh reference runs of this conversion executed (every instruction
    interpreted, before anything was learned): the one source of what is promoted to a shared path."""
    rows = {'m68k_ram': [], 'm68k_gfx': [], 'z80_ram': []}
    for result in reference.values():
        merge(rows, result.get('fallback') or {})
    return rows


def check_states(executable: Path, folder: Path, name: str, frames: int, script: Path, expected: Path, label: str = 'CPS-1') -> dict:
    """F8 at a frame, F9 in a fresh process: the continued timeline must match."""
    at = max(60, frames - STATE_SETTLE - 60)
    state = folder / 'quick.rrstate'
    run(executable, folder, 'save', at + 1, script, '--save-state', str(state), '--save-at', str(at), label=label)
    run(executable, folder, 'load', STATE_SETTLE, script, '--load-state', str(state), ends_at=at + STATE_SETTLE, label=label)
    rows = expected.read_text(encoding='ascii').splitlines()[1:]
    resumed = (folder / 'load.csv').read_text(encoding='ascii').splitlines()[1:]
    require(continuation_difference(rows, resumed, at, STATE_SETTLE) is None,
            lambda: ConversionError(f'{label} F9 continuation differs from its saved timeline; existing export preserved.'))
    invalid = folder / 'invalid.rrstate'
    invalid.write_bytes(state.read_bytes()[:-17])
    rejected = spawn([str(executable), '--headless', '--frames', '1', '--load-state', str(invalid)],
                     cwd=folder, timeout=120, capture_output=True)
    require(rejected.returncode == 4, lambda: ConversionError(f'{label} accepted a truncated quick state.'))
    return {'route': name, 'saved_at': at, 'continued_frames': STATE_SETTLE, 'fresh_process_match': True,
            'truncated_state_rejected': True, 'state_bytes': state.stat().st_size}


def write_notices(project: Path, family: str) -> None:
    """The game's notices (resource 203), from the shared builder (notices.py): the files the profile declares, then what only
    the pinned Geolith sources carry. Written over the text `cps1_build.prepare_game` leaves, before the build reads the file.
    That older assembly (`cps1_build.NOTICE_FILES`) stays in place because `cps1_build.py` is a pinned generator source
    (`cps1_knowledge.GENERATOR_REVISION`): a notice is no reason to make the qualified CPS paths wait again. It is to be deleted
    with the next generator revision. The resource script does not track the files it names, so it is touched when the text
    it must carry is new for this project."""
    from .conversion_common import write_if_changed
    from .cps1_build import sources
    from .notices import notice_text
    geolith, _ = sources()
    extra = [('m68k/readme.txt', (geolith / 'src/m68k/readme.txt').read_text(encoding='utf-8'))]
    extra += [(file.name, file.read_text(encoding='utf-8').split('*/', 1)[0] + '*/')
              for file in (geolith / 'src/z80/z80.c', geolith / 'deps/miniz/miniz.c')]
    data = notice_text(family, extra=extra).replace('\n', os.linesep).encode('utf-8')
    (project / 'notices.txt').write_bytes(data)
    if write_if_changed(project / 'notices.sha256', hashlib.sha256(data).hexdigest().encode('ascii')) and (project / 'content.rc').is_file():
        (project / 'content.rc').touch()


def audio_model(dsp_rom: bytes | None) -> dict:
    """The sound of the board. On a QSound board the DSP16 is not run: a high-level model of it stands in, written from the disassembled
    program (MAME's qsoundhle.cpp), so the DSP16 is not executed (`executed: false`, and no figure that could be mistaken for a zero count
    of a processor that runs); what the model reads is the player's own dump of the chip's internal ROM, identified here by its hash."""
    if dsp_rom is None:
        return {'chips': ['YM2151 (ymfm)', 'OKI MSM6295'], 'rate': 3579545 // 64}
    return {'chips': ['QSound (DL-1425), high-level model of its DSP16'], 'rate': 24038, 'channels': 2,
            'dsp16': {'model': 'hle', 'executed': False,
                      'source': "MAME's qsoundhle.cpp (BSD-3-Clause), written from the disassembled DSP program",
                      'internal_rom_sha256': hashlib.sha256(dsp_rom).hexdigest(), 'internal_rom_bytes': len(dsp_rom),
                      'comparison_with_mame': "MAME 0.289 runs the same high-level model by default: agreement with it says nothing about the "
                                              'hardware or about a run of the DSP16 program'}}


def ordinary_saves(dsp_rom: bytes | None, family: str = 'cps1') -> dict:
    if family == 'cps2':
        return {'supported': True, 'memory': '93C46 serial EEPROM, 128 bytes (16-bit words)', 'file': 'datas/saves/CPS1-<sha256 of the romset>.rrsave',   # the prefix is the board model's, the hash the romset's
                'interactive_play_only': True}
    if dsp_rom is None:
        return {'supported': False, 'reason': 'standard CPS-1 boards keep no non-volatile memory'}
    return {'supported': True, 'memory': '93C46 serial EEPROM, 128 bytes', 'file': 'datas/saves/CPS1-<sha256 of the romset>.rrsave',
            'interactive_play_only': True}


def knowledge_block(record: dict, promotion: dict, hints_used: dict, board_tier: str = 'supported', family: str = 'cps1') -> dict:
    """The report's `knowledge` section. `shared` says whether CPS-1 is in the sharing at all
    (`path_profiles.EXPERIMENTAL_SHARED`), not that this conversion shared anything."""
    from . import cps1_knowledge
    from .systems import get_profile
    return {
        'machine_status': get_profile(family).status, 'shared': family in path_profiles.SHARED_SYSTEMS and board_tier == 'supported',
        'record_format': cps1_knowledge.FORMAT,
        'cores': cps1_knowledge.engine(family), 'record_sha256': cps1_knowledge.record_digest(record),
        'paths': promotion['paths'], 'promotion': {key: promotion[key] for key in ('m68k_ram', 'm68k_gfx', 'z80_ram', 'truncated')},
        'source': 'fresh reference runs of this conversion', 'use': dict(hints_used),
        'raw_ram_words_stored': False, 'fresh_validation_required': True}


def convert(path: Path, *, title=None, output=None, cover=None, use_cover=True, online_cover=True,
            boxart_dir=None, passes=3, frames=3600, scan_level=None, standard_override=None, profile=None,
            qsound_rom=None, emit=print, family='cps1', **unused) -> Path:
    started = time.perf_counter()
    if family not in ('cps1', 'cps2'):
        raise ConversionError(f'Unknown Capcom board family {family!r}.')
    cps2 = family == 'cps2'
    label = 'CPS-2' if cps2 else 'CPS-1'
    if cps2:
        from .cps2 import read_set
        from . import cps2_catalogue as cps1_catalogue
    else:
        from .cps1 import read_set
        from . import cps1_catalogue
    from .cps1_build import prepare_game, build_game, player_count, YMFM_REVISION
    from .neogeo_build import GEOLITH_REV as GEOLITH_REVISION
    MAME_REVISION = cps1_catalogue.catalogue()['source']['revision']
    level = resolve_scan_level(scan_level)
    if standard_override not in (None, 'arcade', 'auto'):
        raise ConversionError(f'{label} timing follows its board (59.637 Hz); PAL/NTSC overrides do not apply.')
    if profile is not None:
        raise ConversionError(f'{label} identifies romsets by CRC; TOML cartridge profiles do not apply.')
    game_set = read_set(Path(path))
    if not game_set.supported:
        raise ConversionError(f'{label} set {game_set.set_name} is not supported yet: {game_set.reason}')
    game = cps1_catalogue.by_set()[game_set.set_name]
    if (game['machine'] == 'cps2') != cps2:
        raise ConversionError(f'{label} set {game_set.set_name} is a {game["machine"]} board.')
    # A QSound board needs the chip's own ROM, which only the player has: refused with its reason when it is not there.
    from . import cps1_qsound
    dsp_rom = None
    if cps2 or cps1_qsound.needs_dsp_rom(game):
        try:
            dsp_rom = cps1_qsound.internal_rom(qsound_rom)
        except ValueError as error:
            raise ConversionError(f'{"CPS-2" if cps2 else "CPS-1.5"} set {game_set.set_name} needs the QSound DSP ROM (dl-1425.bin, CRC d6cf5ef5), which is your own '
                                  f'dump and is never shipped or downloaded: select it in Options or give --qsound-rom. {error}') from error
    title = title or game_set.title
    if any(ord(c) < 32 for c in title) or len(title) > 160:
        raise ConversionError(f'Invalid {label} game title.')
    if output is None:
        from .paths import games_directory
        output = games_directory(system_id=family) / 'datas/reports' / game_set.sha256
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    from .feedback import ingest
    from .library import library_root
    feedback = ingest(family, game_set.sha256, output, emit=emit)
    memory = library_root(family) / game_set.sha256
    observations = learned(game_set.sha256, memory)
    from . import cps1_knowledge, knowledge
    from .systems import get_profile
    profile_of_family = get_profile(family)
    hints_used = {}

    def shared_hints(board):
        """Rows rebuilt from the shared and library records for the player's own images (build input only)."""
        images = cps1_knowledge.images_from_board(board, game, family)
        # A board of the experimental tier takes nothing from the shared base and gives nothing to it (docs/CPS1.md).
        local = game_set.tier != 'supported'
        rows, info = cps1_knowledge.shared_rows(
            game_set.sha256, images, qualified=None if local else knowledge.qualified_game(family, game_set.sha256),
            imported=None if local else knowledge.imported_game(family, game_set.sha256),
            library=cps1_knowledge.library_record(game_set.sha256, family), system=family)
        merge(rows, feedback_rows(game_set.sha256, family))
        hints_used.update(info)
        return rows
    six = any(name in ('button4', 'button5', 'button6') for port in game['inputs'].values()
              for _, name, _ in port.get('inputs', ()))
    plan = routes(game_set.sha256, frames=max(600, min(int(frames or 3600), 10000)), level=level, six_buttons=six)
    workers = max(1, min(4, os.cpu_count() or 1))
    timings = {}
    work = ROOT / '.build' / family / f'{game_set.set_name}-{game_set.sha256[:12]}'
    with entry_lock(work, timeout=1800):
        project, checks = work / 'native', work / 'checks'
        shutil.rmtree(checks, ignore_errors=True)
        scripts = {}
        for name, count, text in plan:
            scripts[name] = checks / 'inputs' / (name + '.inputs')
            scripts[name].parent.mkdir(parents=True, exist_ok=True)
            scripts[name].write_text(text, encoding='ascii', newline='\n')
        emit(f'{label} {game_set.set_name}: scan level {level}, routes ' +
             ', '.join(f'{name} ({count} frames)' for name, count, _ in plan) + '.')
        presentation = {'rom_path': Path(path), 'cover': Path(cover) if cover else None, 'use_cover': use_cover,
                        'online_cover': online_cover, 'boxart_dir': boxart_dir, 'emit': emit}
        reference, results, prepared = {}, {}, None
        attempts = max(1, min(int(passes or 1), 10))
        for attempt in range(attempts):
            stages.begin_pass(attempt + 1)
            phase = time.perf_counter()
            emit(f'{label}: translating the 68000 program and Z80 sound code (pass {attempt + 1}).')
            with stages.phase('code_generation'):
                prepared = prepare_game(project, game_set, game, title=title, observations=observations,
                                        presentation=presentation, hints=shared_hints, dsp_rom=dsp_rom)
                write_notices(project, getattr(game_set, 'system_id', family))
            with stages.phase('compile'):
                executable = build_game(project)
            timings[f'translate_and_build_{attempt + 1}'] = round(time.perf_counter() - phase, 3)
            phase = time.perf_counter()
            candidate = checks / f'pass-{attempt + 1}' / executable.name
            candidate.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(executable, candidate)
            jobs = []
            if not reference:
                emit(f'{label}: fresh reference runs (every instruction interpreted).')
                jobs += [('reference', name, count) for name, count, _ in plan]
            jobs += [('native', name, count) for name, count, _ in plan]
            # The reference and native replays share one pool: their wall time is not told apart.
            with stages.phase('native_runs' if reference else 'reference_and_native_runs'), \
                    ThreadPoolExecutor(max_workers=workers) as pool:
                done = list(pool.map(lambda job: (job, run(candidate, checks / job[0] / f'pass-{attempt + 1}', job[1], job[2],
                                                          scripts[job[1]], *(['--reference'] if job[0] == 'reference' else []), label=label)),
                                     jobs))
            for (kind, name, _), result in done:
                (reference if kind == 'reference' else results)[name] = result
            for name, count, _ in plan:
                require_same_file(results[name]['trace'], reference[name]['trace'], lambda: ConversionError(
                    f'{label} {name}: native and reference CPU/RAM/image/PCM traces differ; existing export preserved.'))
                if not results[name]['nonuniform_frames']:
                    raise ConversionError(f'{label} {name}: no picture was produced.')
                require_moving_picture(route_liveness(Path(results[name]['trace'])), lambda: ConversionError(
                    f'{label} {name}: the picture never changed during the route; the game is stuck.'))
            timings[f'routes_{attempt + 1}'] = round(time.perf_counter() - phase, 3)
            fallback = sum(results[name]['interpreted_68000'] + results[name]['interpreted_z80'] for name, _, _ in plan)
            if not fallback:
                break
            progress = False
            for name, _, _ in plan:
                progress = merge(observations, results[name]['fallback']) or progress
            if not progress or attempt + 1 == attempts:
                emit(f'{label}: {fallback} interpreted instructions remain; they stay counted and reported.')
                break
            emit(f'{label}: {fallback} interpreted instructions observed; extending guarded native code.')
        stages.end_passes()
        if not any(results[name]['nonzero_samples'] for name, _, _ in plan):
            raise ConversionError(f'{label} validation produced no sound on any route.')
        phase = time.perf_counter()
        packed = project / 'packed-game.exe' if os.name == 'nt' else project / 'packed-game'
        delivered = deliver_packed(executable, packed, label, emit)
        with stages.phase('packed_replays'):
            final = {row[0]: result for row, result in zip(plan, replay_packed(
                delivered, plan, lambda row: run(packed, checks / 'packed', row[0], row[1], scripts[row[0]], label=label),
                same=lambda row, result: same_trace(result['trace'], reference[row[0]]['trace']),
                mismatch=lambda row: ConversionError(f'{label} {row[0]}: compressed executable differs from the reference.'),
                workers=workers))}
        timings['packed_replays'] = round(time.perf_counter() - phase, 3)
        phase = time.perf_counter()
        emit(f'{label}: checking F8/F9 in a fresh process and rejecting an invalid state.')
        play = next(row for row in plan if row[0] == 'play')
        with stages.phase('state_checks'):
            states = check_states(packed, checks / 'states', 'play', play[1], scripts['play'], final['play']['trace'], label)
        timings['state_checks'] = round(time.perf_counter() - phase, 3)
        # The shared path record: numbers about this romset's own images, made only from the fresh reference
        # runs of this conversion (every check above passed), never from feedback rows or from the hints
        # it was offered. What cannot be tied to a ROM stays private (counted below).
        from .cps1_codegen import ram_instruction_lengths
        fresh = fresh_observations(reference)
        images = cps1_knowledge.images_from_board(project / 'board', game, family)
        record, promotion = cps1_knowledge.promote(
            game_set.sha256, images, fresh, lambda windows: ram_instruction_lengths(project, windows),
            previous=cps1_knowledge.library_record(game_set.sha256, family), system=family)
        memory.mkdir(parents=True, exist_ok=True)
        atomic_json(memory / 'observations.json', observations)
        atomic_json(memory / 'compilation.json', {
            'schema': 1, 'system': family, 'title': title, 'set': game_set.set_name, 'source_identity': game_set.sha256,
            'guarded_ram_variants': len(observations['m68k_ram']), 'guarded_gfx_variants': len(observations['m68k_gfx']),
            'guarded_z80_ram_variants': len(observations['z80_ram']),
            'fresh_reference_passed': True, 'version': __version__,
            # The schema 3 record the base shares (numbers only), and where it came from.
            'record': record, 'record_format': cps1_knowledge.FORMAT, 'cores': cps1_knowledge.engine(family),
            'record_source': 'fresh reference runs', 'record_counts': promotion})
    checks_rows = []
    for name, count, text in plan:
        native = final[name]
        main = native['native_68000'] + native['interpreted_68000']
        checks_rows.append({'name': name, 'frames': count, 'native_entries': native['native_68000'],
            'interpreted_opcodes': native['interpreted_68000'], 'audio_native_opcodes': native['native_z80'],
            'audio_interpreted_opcodes': native['interpreted_z80'],
            'interpreter_percent': round(100 * native['interpreted_68000'] / max(1, main), 6),
            'reference_match': True, 'cpu_hash': native['cpu_hash'], 'ram_hash': native['ram_hash'],
            'image_hash': native['image_hash'], 'pcm_hash': native['pcm_hash'],
            'nonzero_samples': native['nonzero_samples'], 'liveness': route_liveness(Path(native['trace'])),
            'trace_sha256': file_sha256(native['trace']),
            'script_sha256': hashlib.sha256(text.encode('ascii')).hexdigest()})
    native_coverage = all(not row['interpreted_opcodes'] and not row['audio_interpreted_opcodes'] for row in checks_rows)
    board_tier = game_set.tier
    analysis = prepared['analysis']
    report = {'tool': 'Retro-Recomp', 'version': __version__,
        # The machine is supported; a board of the experimental tier (the QSound boards of the CPS-1.5, a catalogue column)
        # reports `experimental` whatever its coverage.
        'status': 'completed' if not profile_of_family.experimental and board_tier == 'supported' and native_coverage else 'experimental',
        'board_tier': board_tier,
        'created_utc': datetime.now(timezone.utc).isoformat(), 'system': {'id': family, 'name': profile_of_family.name},
        'rom': game_set.metadata(),
        'compiler': {'board': f'Retro-Recomp {label} board adapted from MAME (BSD-3-Clause)', 'mame_revision': MAME_REVISION,
                     'cpu_cores_revision': GEOLITH_REVISION, 'ymfm_revision': YMFM_REVISION,
                     'native_cpu': 'guarded 68000 (static sweep of the program ROM) and guarded Z80 at every byte'},
        'native_analysis': {'m68000': {k: analysis['m68000'].get(k) for k in ('decoded', 'translated_rom_positions',
                                                                              'guarded_ram_variants')},
                            'z80': {k: v for k, v in analysis['z80'].items() if isinstance(v, (int, str))}},
        'final_checks': checks_rows,
        'native_validation': {'passed': True, **delivered.validation_fields(), 'reference_before_learning': True,
            'reference_kind': 'same board model with every instruction interpreted (Musashi, Z80 core)',
            'cpu_agreement': True, 'hardware_fidelity_validated': False, 'full_game_validated': False,
            'mame_comparison': 'board model compared with MAME on development sets only; not per conversion'},
        'native_coverage': native_coverage,
        'video_model': {'standard': 'arcade', 'visible_pixels': [384, 224], 'hz': 8000000 / (512 * 262),
                        'rotation': game_set.rotation, 'display_aspect': '3:4' if game_set.rotation else '4:3'},
        'audio_cpu': 'Z80', 'audio_model': audio_model(dsp_rom),
        'counter_unit': 'retired instructions', 'runtime_learning': True, 'runtime_feedback': feedback,
        'physical_latency_measured': False, 'latency_ms': None,
        'game_states': {'supported': True, 'save_key': 'F8', 'load_key': 'F9',
                        'compatibility': 'exact romset, board model and runtime ABI', 'validation': states},
        'ordinary_saves': ordinary_saves(dsp_rom, family),
        'artwork': prepared['artwork'], 'windows_metadata': prepared['windows_metadata'],
        'executable': executable_name(title), 'build_executable': str(executable), 'toolchain': toolchain_description(), 'build_directory': str(project),
        **delivered.report_fields(), 'scan_level': level, 'validation_workers': workers,
        'conversion_phases_seconds': timings, 'conversion_wall_seconds': round(time.perf_counter() - started, 3),
        'knowledge': knowledge_block(record, promotion, hints_used, board_tier, family),
        'qualification_scope': {
            'controls': f'players 1 to {player_count(game)}: joystick, up to six buttons, Start, coin; '
                        'validation routes drive players 1 and 2',
            'dip_switches': ("the board has none: its settings are in the game's test menu, opened by the service switch of the F2 switch page" if cps2
                             else 'catalogue defaults during validation; adjustable in play (F2)'),
            'universal_zero_fallback_claim': False}}
    write_report(output / 'conversion-report.json', report)
    emit(f'{label}: {title} ready ({"no interpreter on the routes played" if native_coverage else "interpreter fallback reported"}).')
    # Publishing compacts this same build again (UPX is deterministic).
    return executable
