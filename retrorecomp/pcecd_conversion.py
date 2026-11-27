"""PC Engine CD conversion (experimental; docs/PC_ENGINE_CD.md). Retro-Recomp's own code, MIT.

The conversion of a disc is the PC Engine's (retrorecomp/pce_conversion.py) with a disc and the player's System Card in place of a HuCard: every route runs
twice in the same build of the game, once with every instruction forced through the engine's interpreter (`--reference`, the fresh reference) and once with
the guarded native module, and their per-frame CPU, work RAM, picture and PCM traces must be identical. The native module comes from what the runs observed:
the System Card's own code as it executes and every RAM overlay the game loads from the disc (the engine's code capture, which keys a code identity by its
address, the eight bank registers and its bytes). The instructions the routes never ran stay on the interpreter, counted and reported.

The runs read the disc in place (`--disc`, `--disc-sha256`): nothing is copied per pass. The delivered game is the last build with the disc appended and its
trailer (native/pcecd_pack.h), published as built (a compressed copy would move the bytes the program reads), and the routes are played once more on it.
Nothing is written beside the player's files.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import time

from . import __version__, pcecd
from .core import ConversionError
from .platforms import target_id
from .report_schema import write_report

NOT_YET = 'The PC Engine CD converter files are missing from this installation.'


def _system() -> dict:
    from .systems import get_profile
    profile = get_profile('pcecd')
    return {'id': profile.id, 'name': profile.name, 'status': profile.status}


def convert(path, *, title=None, output=None, cover=None, use_cover=True, online_cover=True, boxart_dir=None, passes=3, frames=3600, scan_level=None,
            standard_override=None, profile=None, pcecd_system_card=None, pcecd_unknown='nec-invalid', pcecd_region='usa', pcecd_ram='super', emit=print,
            **unused) -> Path:
    from .systems.pc_engine_cd import PC_ENGINE_CD
    item = pcecd.read_input(path)
    if not PC_ENGINE_CD.available():
        raise ConversionError(NOT_YET)
    card = pcecd.card_for(item, pcecd_system_card)
    if card is None:
        raise ConversionError('The PC Engine CD needs your own System Card: choose it in Options (a file or a folder; it is checked by its hash and never '
                              'shipped).')
    started = time.perf_counter()
    from . import pce_build, pce_conversion as hu, pcecd_build, pcecd_routes, timings as stages
    from .conversion_common import resolve_scan_level
    from .conversion_gates import require_same_file
    from .core import executable_name
    from .delivery_evidence import deliver_packed, replay_packed, require_moving_picture, same_trace
    from .library import entry_lock, file_sha256
    from .packing import refuse_compression
    from .paths import ROOT
    from .toolchain import describe as toolchain_description
    level = resolve_scan_level(scan_level)
    if standard_override not in (None, 'ntsc', 'auto'):
        raise ConversionError('The PC Engine CD profile is NTSC only.')
    if profile is not None:
        raise ConversionError('PC Engine CD discs are read from their content; TOML cartridge profiles do not apply.')
    if pcecd_region not in ('usa', 'japan') or pcecd_ram not in ('super', 'standard'):
        raise ConversionError('The PC Engine CD options are region usa or japan and RAM super or standard.')
    title = title or item.title
    if any(ord(c) < 32 for c in title) or len(title) > 160:
        raise ConversionError('Invalid PC Engine CD game title.')
    if output is None:
        from .paths import games_directory
        output = games_directory(system_id='pcecd') / 'datas/reports' / item.sha256
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    from .feedback import ingest
    feedback = ingest('pcecd', item.sha256, output, emit=emit)
    plan_frames = max(600, min(int(frames or 3600), 10000))
    plan = hu.routes(item.sha256, frames=plan_frames, level=level)
    route_start = None
    timings = {}
    styled = {}          # long route name -> the style of its input (pcecd_routes), once the styles have been scored
    start_choice = {'presses': 3, 'confirm': False}

    def apply_styles(rows_):
        # the script of a styled long route is its style's (seeded as the route is); the other routes keep the walk's
        return [(name, count, pcecd_routes.script(styled[name], count, hu.route_seed(item.sha256, name), start_choice['presses'], start_choice['confirm'])
                 if name in styled else text) for name, count, text in rows_]
    # Short folders, as the PC Engine's: the engine names its module's object library after a 64-digit hash.
    work = ROOT / '.build' / 'pcecd' / item.sha256[:12]
    with entry_lock(work, timeout=1800):
        project, checks = work / 'n', work / 'checks'
        image = item.path
        if item.identity.container == 'cue':
            # A CUE sheet and its images become one file the game holds (the sheet's own sector numbering, nothing converted): the runs read it and the game gets it.
            from . import pcecd_disc
            try:
                image = pcecd_disc.write_pack(item.path, work / ('disc' + pcecd_disc.PACK_SUFFIX))
            except (pcecd_disc.DiscError, OSError) as error:
                raise ConversionError(f'The CUE sheet cannot be packed: {error}') from None
        disc_args = ('--disc', str(image), '--disc-sha256', item.sha256)
        shutil.rmtree(checks, ignore_errors=True)
        scripts = {}
        for name, count, text in plan:
            scripts[name] = checks / 'inputs' / (name + '.inputs')
            scripts[name].parent.mkdir(parents=True, exist_ok=True)
            scripts[name].write_text(text, encoding='ascii', newline='\n')
        emit(f'PC Engine CD: scan level {level}, routes ' + ', '.join(f'{name} ({count} frames)' for name, count, _ in plan) + '.')
        presentation = {'rom_path': Path(path), 'cover': Path(cover) if cover else None, 'use_cover': use_cover, 'online_cover': online_cover,
                        'boxart_dir': boxart_dir, 'emit': emit}
        pce_build.ensure_engine(emit)
        pcecd_build.ensure_libchdr(emit)
        reference, results, captures, module, prepared = {}, {}, [], None, None
        emitted, skipped_captures, capture_counts = None, 0, {}
        attempts = max(1, min(int(passes or 1), 10))
        for attempt in range(attempts):
            stages.begin_pass(attempt + 1)
            phase = time.perf_counter()
            emit(f'PC Engine CD: building the game (pass {attempt + 1}, {"everything interpreted" if module is None else "with the guarded native module"}).')
            with stages.phase('code_generation'):
                prepared = pcecd_build.prepare_game(project, item, card, title=title, module=module, presentation=presentation, players=pcecd.players_of(item),
                                                    super_ram=pcecd_ram == 'super', region_japan=pcecd_region == 'japan', unknown=pcecd_unknown)
            with stages.phase('compile'):
                executable = pce_build.build_game(project, emit)
            timings[f'translate_and_build_{attempt + 1}'] = round(time.perf_counter() - phase, 3)
            phase = time.perf_counter()
            candidate = checks / f'pass-{attempt + 1}' / executable.name
            candidate.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(executable, candidate)
            with stages.phase('reference_and_native_runs'):
                if not reference:
                    emit('PC Engine CD: fresh reference runs (every instruction interpreted).')
                    play_count = next(count for name, count, _ in plan if name == 'play')
                    baseline = checks / 'inputs' / 'play-start0.inputs'
                    baseline.write_text(hu._script([]), encoding='ascii', newline='\n')
                    variants = {0: hu.run(candidate, checks / 'reference', 'play-start0', play_count, baseline, '--reference', *disc_args)}
                    for variant in [*hu.start_candidates(play_count), *hu.confirm_candidates(play_count)]:
                        label = hu.variant_name(variant).replace('+', 'i')
                        script = checks / 'inputs' / f'play-start{label}.inputs'
                        script.write_text(hu._script(hu.play_rows(play_count, int(item.sha256[:8], 16), hu.variant_presses(variant), (), isinstance(variant, tuple))),
                                          encoding='ascii', newline='\n')
                        variants[variant] = hu.run(candidate, checks / 'reference', f'play-start{label}', play_count, script, '--reference', *disc_args)
                    start = {variant: {'liveness': hu.route_liveness(Path(result['trace'])),
                                       'divergence': hu.divergence(result['trace'], variants[0]['trace']),
                                       'reach': hu.reach(result['trace'], variants[0]['trace'], hu.walk_start(hu.variant_presses(variant)))}
                             for variant, result in variants.items() if variant}
                    chosen = hu.choose_start(start, play_count)
                    presses, confirm = hu.variant_presses(chosen), isinstance(chosen, tuple)
                    route_start = {'run_presses': presses, 'confirm': 'I' if confirm else None,
                                   'variants': {hu.variant_name(k): v for k, v in start.items()},
                                   'rule': 'alive until the last 120 frames, then most pictures the walk reached that no input never showed', 'repairs': {}}
                    emit(f'PC Engine CD: play route starts with Run pressed {presses} time(s)' + (', each followed by I' if confirm else '') +
                         f' ({start[chosen]["reach"]} pictures reached that no input never showed).')
                    plan = hu.routes(item.sha256, frames=plan_frames, level=level, presses=presses, confirm=confirm)
                    start_choice.update(presses=presses, confirm=confirm)
                    # The long routes play the styles that made the game run the most different code (docs/PC_ENGINE_CD.md, route depth): each style is played on the
                    # observing build for a few thousand frames and scored by the code identities its capture holds.
                    if level != 'quick':
                        explored = pcecd_routes.explore(candidate, checks, item.sha256, presses, confirm, disc_args, emit)
                        route_start['exploration'] = explored
                        styled.update(zip([name for name, _, _ in plan if name.startswith('long-')], [row['style'] for row in explored]))
                    plan = apply_styles(plan)
                    for name, count, text in plan:
                        scripts[name].write_text(text, encoding='ascii', newline='\n')
                    for name, count, _ in plan:
                        if name == 'attract' and count == play_count and scripts[name].read_text() == baseline.read_text():
                            reference[name] = variants[0]
                        elif name in styled:
                            reference[name] = hu.run(candidate, checks / 'reference', name, count, scripts[name], '--reference', *disc_args)
                        else:
                            reference[name] = (variants[chosen] if name == 'play' else
                                               hu.run(candidate, checks / 'reference', name, count, scripts[name], '--reference', *disc_args))
                            repaired, reference[name] = hu.repair_route(
                                name, count, hu.route_seed(item.sha256, name), presses, checks / 'inputs', reference[name],
                                lambda trial, frames_, script: hu.run(candidate, checks / 'reference', trial, frames_, script, '--reference', *disc_args),
                                emit, confirm)
                            if repaired:
                                route_start['repairs'][name] = repaired
                                scripts[name].write_text(hu._script(hu.play_rows(count, hu.route_seed(item.sha256, name), presses, repaired, confirm)),
                                                         encoding='ascii', newline='\n')
                    if route_start['repairs']:
                        plan = apply_styles(hu.routes(item.sha256, frames=plan_frames, level=level, presses=presses, repairs=route_start['repairs'], confirm=confirm))
                for name, count, _ in plan:
                    # A disc loads code as it plays: the captures use the engine's larger format from the start.
                    capture = checks / 'native' / f'pass-{attempt + 1}' / (name + '-capture.jsonl')
                    capture.parent.mkdir(parents=True, exist_ok=True)
                    results[name] = hu.run(candidate, capture.parent, name, count, scripts[name], '--code-capture', str(capture),
                                           '--capture-limit', str(hu.EXTENDED_CAPTURE_LIMIT), *disc_args)
                    results[name]['capture'], results[name]['capture_frames'] = capture, count
                    capture_counts[name] = {'format': 'extended', 'identities': results[name].get('capture_identities'),
                                            'dropped': results[name].get('capture_dropped')}
                    if results[name].get('capture_dropped'):
                        results[name]['capture'], results[name]['capture_frames'] = hu.complete_prefix(
                            candidate, capture.parent, name, scripts[name], {**results[name], 'frames': count}, emit, disc_args)
                        capture_counts[name]['complete_frames'] = results[name]['capture_frames']
            for name, _, _ in plan:
                require_same_file(results[name]['trace'], reference[name]['trace'], lambda: ConversionError(
                    f'PC Engine CD {name}: native and reference CPU/RAM/picture/PCM traces differ; existing export preserved.'))
                if not results[name]['nonuniform_frames']:
                    raise ConversionError(f'PC Engine CD {name}: no picture was produced.')
                require_moving_picture(hu.route_liveness(Path(results[name]['trace'])), lambda: ConversionError(
                    f'PC Engine CD {name}: the picture never changed during the route; the game is stuck.'))
            timings[f'routes_{attempt + 1}'] = round(time.perf_counter() - phase, 3)
            fallback = sum(results[name]['interpreted_instructions'] for name, _, _ in plan)
            if not fallback:
                break
            order = sorted(plan, key=lambda row: row[0] != 'play')
            captures += [results[name]['capture'] for name, _, _ in order if results[name]['capture'] and hu.observed(results[name]['capture'])]
            if attempt + 1 == attempts or not captures:
                emit(f'PC Engine CD: {fallback} interpreted instructions remain; they stay counted and reported.')
                break
            emit(f'PC Engine CD: {fallback} interpreted instructions observed; emitting guarded native code.')
            with stages.phase('code_generation'):
                new_module = work / f'module-{attempt + 1}'
                shutil.rmtree(new_module, ignore_errors=True)
                history = work / f'history-{attempt + 1}'
                shutil.rmtree(history, ignore_errors=True)
                captures, skipped, _identities = hu.fitting_captures(captures)
                skipped_captures += len(skipped)
                index = pce_build.compose_history(captures, history, hu.EXTENDED_CAPTURE_LIMIT)
                manifest = pce_build.emit_history_module(index, new_module)
            emit(f'PC Engine CD: {manifest.get("native_instructions_emitted", 0)} instructions in {manifest.get("native_contexts", 0)} bank contexts emitted'
                 + (f' ({len(skipped)} capture(s) left out: the engine bounds the identities of a module).' if skipped else '.'))
            if manifest.get('native_instructions_emitted') == emitted:
                emit('PC Engine CD: nothing new fits in the module; the remaining interpreted instructions stay counted.')
                break
            module, emitted = new_module, manifest.get('native_instructions_emitted')
        stages.end_passes()
        if not any(results[name]['nonzero_samples'] for name, _, _ in plan):
            emit('PC Engine CD: no route produced sound (reported, not refused).')
        # The delivered game: the last build with the disc appended, published as built.
        phase = time.perf_counter()
        delivered_exe = project / ('game-with-disc.exe' if os.name == 'nt' else 'game-with-disc')
        shutil.copy2(executable, delivered_exe)
        pcecd_build.append_disc(delivered_exe, image, item.sha256)
        refuse_compression(file_sha256(delivered_exe), 'A PC Engine CD game carries its disc after the program: it is published as built, uncompressed '
                                                       '(a compressed copy would move the bytes the program reads).')
        packed = project / ('packed-game.exe' if os.name == 'nt' else 'packed-game')
        delivered = deliver_packed(delivered_exe, packed, 'PC Engine CD', emit)
        with stages.phase('packed_replays'):
            final = {row[0]: result for row, result in zip(plan, replay_packed(
                delivered, plan, lambda row: hu.run(packed, checks / 'packed', row[0], row[1], scripts[row[0]]),
                same=lambda row, result: same_trace(result['trace'], reference[row[0]]['trace']),
                mismatch=lambda row: ConversionError(f'PC Engine CD {row[0]}: the delivered game differs from the reference.')))}
        timings['packed_replays'] = round(time.perf_counter() - phase, 3)
        phase = time.perf_counter()
        emit('PC Engine CD: checking F8/F9 in a fresh process and rejecting an invalid state.')
        play = next(row for row in plan if row[0] == 'play')
        with stages.phase('state_checks'):
            states = hu.check_states(packed, checks / 'states', 'play', play[1], scripts['play'], final['play']['trace'])
        timings['state_checks'] = round(time.perf_counter() - phase, 3)
        phase = time.perf_counter()
        emit('PC Engine CD: checking the Backup RAM file in fresh processes and setting damaged files aside.')
        with stages.phase('state_checks'):
            backup = hu.check_backup(packed, checks / 'backup', play[1], scripts['play'], item.sha256, formatted=bytes(hu.BACKUP_BYTES))
        timings['backup_checks'] = round(time.perf_counter() - phase, 3)
    checks_rows = []
    for name, count, text in plan:
        native = final[name]
        total = native['native_instructions'] + native['interpreted_instructions']
        checks_rows.append({'name': name, 'frames': count, 'style': styled.get(name, 'none' if name == 'attract' else 'walk'), 'native_entries': native['native_instructions'],
                            'interpreted_opcodes': native['interpreted_instructions'], 'guard_misses': native['guard_misses'],
                            'interpreter_percent': round(100 * native['interpreted_instructions'] / max(1, total), 6), 'reference_match': True,
                            'cpu_hash': native['cpu_hash'], 'ram_hash': native['ram_hash'], 'image_hash': native['image_hash'], 'pcm_hash': native['pcm_hash'],
                            'nonzero_samples': native['nonzero_samples'], 'cropped_frames': native['cropped_frames'], 'backup_hash': native['backup_hash'],
                            'backup_written': native['backup_hash'] != native['backup_start_hash'],
                            'liveness': hu.route_liveness(Path(native['trace'])), 'trace_sha256': file_sha256(native['trace']),
                            'script_sha256': hashlib.sha256(text.encode('ascii')).hexdigest()})
    native_coverage = all(not row['interpreted_opcodes'] for row in checks_rows)
    manifest = json.loads((module / 'module.json').read_text(encoding='utf-8')) if module else {}
    report = {'tool': 'Retro-Recomp', 'version': __version__, 'created_utc': datetime.now(timezone.utc).isoformat(), 'system': _system(), 'target': target_id(),
              'rom': item.metadata(), 'converted': True,
              'disc': {'container': item.identity.container, 'title': item.identity.title, 'carried': 'appended to the executable and read in place',
                       'ipl': item.identity.metadata()['ipl']},
              'firmware': {'system_card': card.metadata() | {'carried': 'embedded in the executable (resource 103); never shipped by Retro-Recomp'}},
              # The lobby compares a firmware only when the report names it at the top level with a sha256 (netplay/lobby_check.FIRMWARE_KEYS): two players
              # with another System Card are refused before the launch, with the reason « firmware ». Same record as firmware.system_card.
              'bios': card.metadata() | {'kind': 'player'},
              'compiler': {'engine': hu.ENGINE_REPO, 'engine_revision': hu.ENGINE_REV, 'runtime_abi': hu.ENGINE_ABI, 'disc_reader': 'libchdr (BSD-3-Clause), linked statically',
                           'native_cpu': 'guarded HuC6280 instructions emitted from observed runs (full MPR context, physical fetch addresses and exact bytes '
                                         'checked before each one), the System Card\'s and the code the disc loads'},
              'disc_checks': {'ram_profile': pcecd_ram, 'region': pcecd_region, 'unknown_cd_commands': pcecd_unknown,
                              'native_instructions_emitted': manifest.get('native_instructions_emitted', 0),
                              'native_contexts': manifest.get('native_contexts', 0), 'translation_units': len(manifest.get('translation_units', ())),
                              'observation_sources': len(captures), 'captures_left_out': skipped_captures,
                              'capture_frames': {name: results[name].get('capture_frames') for name, _, _ in plan}},
              'final_checks': checks_rows,
              'native_validation': {'passed': True, **delivered.validation_fields(), 'reference_before_learning': True,
                                    'reference_kind': 'the same build with every instruction through the engine\'s interpreter', 'cpu_agreement': True,
                                    'cpu_fidelity_validated': False, 'independent_cpu_oracle': False, 'hardware_fidelity_validated': False,
                                    'full_game_validated': False},
              'native_coverage': native_coverage,
              'video_model': {'standard': 'ntsc', 'master_ticks_per_frame': 1365 * 262, 'display_aspect': '4:3'},
              'audio_cpu': None, 'audio_model': {'kind': 'PSG, ADPCM and CD audio mixed by the engine', 'rate': 44100, 'channels': 2},
              'counter_unit': 'retired instructions', 'runtime_learning': False, 'runtime_feedback': feedback,
              'physical_latency_measured': False, 'latency_ms': None, 'hardware_accuracy_validated': False, 'full_game_validated': False,
              'game_states': {'supported': True, 'save_key': 'F8', 'load_key': 'F9', 'compatibility': 'exact disc, engine revision and bridge sources',
                              'validation': states},
              'backup_ram': {'supported': True, 'bytes': hu.BACKUP_BYTES, 'file': 'datas/saves/<game>-<disc>.rrsram',
                             'compatibility': 'exact disc; survives a rebuild of the game', 'model': 'the System Card\'s backup memory (2 KiB at bank $F7, locked until a game asks)',
                             'formatted_without_a_save': 'blank: the System Card formats it when a game asks', 'validation': backup},
              'artwork': prepared['artwork'], 'windows_metadata': prepared['windows_metadata'], 'executable': executable_name(title),
              'build_executable': str(delivered_exe), 'toolchain': toolchain_description(), 'build_directory': str(project), **delivered.report_fields(),
              'scan_level': level, 'conversion_phases_seconds': timings, 'conversion_wall_seconds': round(time.perf_counter() - started, 3),
              'route_start': route_start, 'capture_counts': capture_counts,
              'qualification_scope': {'controls': f'{prepared["pad_buttons"]}-button pads, players 1 to {prepared["players"]}; the validation routes drive player 1',
                                      'universal_zero_fallback_claim': False}}
    write_report(output / 'conversion-report.json', report)
    from .library import atomic_json, library_root
    summary = library_root('pcecd') / item.sha256 / 'compilation.json'
    summary.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(summary, {'schema': 1, 'title': title, 'system': 'pcecd', 'game': item.sha256, 'rom_sha256': item.sha256, 'private_development_only': True,
                          'fresh_reference_passed': True, 'record': None, 'record_source': 'none: no path is shared or recorded for a disc yet'})
    emit(f'PC Engine CD: {title} ready ({"no interpreter on the routes played" if native_coverage else "interpreter fallback reported"}).')
    return delivered_exe
