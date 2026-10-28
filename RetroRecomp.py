from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys
from retrorecomp.platforms import restore_system_library_path
restore_system_library_path()
from retrorecomp.core import ConversionError, convert, dependencies, read_rom
from retrorecomp.library import GameMemory, list_games, library_root
from retrorecomp.paths import ROOT, save_game_language, games_root, load_preferences, console_options
from retrorecomp.i18n import log_text
from retrorecomp.batch import identify, convert_batch, system_output
from retrorecomp.systems import MASTER_SYSTEM, available_profiles, discover_roms, profile_for_path
PROFILES = available_profiles()

# What `--help` says of the options the machines declare (OptionKey in systems/<machine>.py). The command line
# builds one flag per option from the profiles; these texts keep the words of the existing flags, and a
# machine added later gets a generic line until it has its own here.
_PATH_HELP = {
    'ng_bios': 'User-supplied Neo Geo BIOS ZIP; otherwise use the path saved in Options.',
    'x68_ipl': 'X68000: your own IPL ROM.',
    'x68_cgrom': 'X68000: your own font ROM (CGROM).',
    'x68_ram': 'X68000 RAM in MiB.',
}
_FLAG_HELP = {
    'convert': {
        'gb_deep_validation': 'Extra Game Boy CPU checks during play (default: on; use --no-gb-deep-validation for a '
                              'faster check). Native discovery is unchanged.',
        'md_advanced_scan': 'Mega Drive / Super Nintendo: add a 24,000-frame attract test, reproducible pseudo-random play '
                            'routes and, on Mega Drive, the authored replays, with reference checks on each learning pass (default: off).',
        'nes_advanced_scan': 'Add NES menu/dialogue/varied-input replays with complete reference CPU/image/audio checks (default: off).',
    },
    'batch': {
        'gb_deep_validation': 'Extra Game Boy CPU checks during play (default: on; use --no-gb-deep-validation for a '
                              'faster check). Ignored for other consoles.',
        'md_advanced_scan': 'Extra Mega Drive / Super Nintendo coverage scan (default: off); ignored for other consoles.',
        'nes_advanced_scan': 'Extra NES menu/dialogue/varied-input coverage and reference checks (default: off); ignored for other consoles.',
    },
}


def _option_flag(key) -> str:
    return '--' + key.name.replace('_', '-')


def add_machine_options(command, *, developer: bool | None = None) -> None:
    """The firmware paths and choices every machine declares, as `--<id>-<firmware>` flags.

    ``developer`` keeps the options of the machines every installation carries (False) or of the developer-only
    ones (True); None adds all of them, in registration order."""
    for profile, key in console_options('path', 'choice'):
        if developer is not None and profile.developer_only != developer:
            continue
        help_text = _PATH_HELP.get(key.name, f'{profile.name}: {key.label or key.name}.')
        if key.kind == 'path':
            command.add_argument(_option_flag(key), type=Path, help=help_text)
        else:
            command.add_argument(_option_flag(key), type=type(key.choices[0]), choices=key.choices, default=None,
                                 help=help_text)


def machine_switches() -> list:
    """The on/off options of the machines, by name (`--gb-deep-validation` / `--no-gb-deep-validation`)."""
    return sorted(console_options('flag'), key=lambda pair: pair[1].name)


def add_machine_switches(command, name: str) -> None:
    for profile, key in machine_switches():
        generic = f'{profile.name}: {key.name.replace("_", " ")} (default: {"on" if key.default else "off"}).'
        command.add_argument(_option_flag(key), action=argparse.BooleanOptionalAction, default=bool(key.default),
                             help=_FLAG_HELP[name].get(key.name, generic))


def switch_keywords(args) -> dict:
    """The machines' on/off options as `convert_batch` keywords."""
    return {key.name: getattr(args, key.name) for _, key in machine_switches()}


def machine_keywords(args) -> dict:
    """The firmware paths and choices as `convert_batch` keywords: the flag, else the value saved in Options."""
    saved = load_preferences()
    values = {}
    for _, key in console_options('path', 'choice'):
        given = getattr(args, key.name)
        if key.kind == 'path':
            values[key.name] = given.expanduser().resolve() if given else saved.get(key.name)
        else:
            values[key.name] = given or saved.get(key.name, key.default)
    return values


def main() -> int:
    # The packaged converter shows a start-up picture while it unpacks; the
    # converters it starts itself (bridges, update checks) must not.
    os.environ.setdefault('PYINSTALLER_SUPPRESS_SPLASH_SCREEN', '1')
    if len(sys.argv)==3 and sys.argv[1] in ('_compilation-stamps','_compilation-inputs'):
        # Package qualification only: no ROM access, GUI or compiler launch.
        from retrorecomp.compilation_inputs import engine_stamp,input_fingerprints
        from retrorecomp.library import atomic_json
        describe=input_fingerprints if sys.argv[1]=='_compilation-inputs' else engine_stamp
        from retrorecomp.systems import system_ids
        atomic_json(Path(sys.argv[2]),{s:describe(s) for s in system_ids()})
        return 0
    if sys.argv[1:] == ['_install-launcher'] and sys.platform == 'linux':
        from retrorecomp.linux_desktop import publish_converter_launcher
        publish_converter_launcher()
        return 0
    if len(sys.argv) >= 3 and sys.argv[1] == '_snes-generate':
        import runpy
        engine = Path(sys.argv[2]).resolve()
        bridge = engine / 'snesrecomp_cli.py'
        sys.path.insert(0, str(engine))
        sys.argv = [str(bridge), *sys.argv[3:]]
        # This upstream bridge resolves sources through _MEIPASS when frozen.
        # Our pinned sources live in .deps, outside the converter bundle.
        bundle = getattr(sys, '_MEIPASS', None)
        if bundle is not None:
            del sys._MEIPASS
        old_stdout, old_stderr = sys.stdout, sys.stderr
        child_log = None
        if old_stdout is None or old_stderr is None:
            directory = ROOT / '.build'
            directory.mkdir(parents=True, exist_ok=True)
            child_log = (directory / 'snes-generator-child.log').open('w', encoding='utf-8')
            if old_stdout is None:
                sys.stdout = child_log
            if old_stderr is None:
                sys.stderr = child_log
        try:
            runpy.run_path(str(bridge), run_name='__main__')
        except Exception as error:
            import traceback
            traceback.print_exc(file=sys.stderr)
            return 1
        finally:
            if bundle is not None:
                sys._MEIPASS = bundle
            sys.stdout, sys.stderr = old_stdout, old_stderr
            if child_log is not None:
                child_log.close()
        return 0
    if len(sys.argv) >= 3 and sys.argv[1] == '_nes-prepare-project':
        # A frozen converter is not a Python command-line interpreter. Run the
        # pinned bridge in this dedicated child so parallel games do not share
        # argparse/sys.argv state, and no installed Python is required.
        import runpy

        bridge = Path(sys.argv[2]) / 'tools/cyc/prepare_project.py'
        sys.argv = [str(bridge), *sys.argv[3:]]
        try:
            runpy.run_path(str(bridge), run_name='__main__')
        except Exception as exc:
            if sys.stderr is not None:
                print(str(exc), file=sys.stderr)
            return 1
        return 0
    if len(sys.argv) == 3 and sys.argv[1] == '_verify-update':
        from retrorecomp import __version__

        return 0 if __version__ == sys.argv[2] else 1
    if len(sys.argv) == 4 and sys.argv[1] == '_apply-update':
        from retrorecomp.updater import apply_update

        return apply_update(Path(sys.argv[2]), sys.argv[3])
    if len(sys.argv) == 5 and sys.argv[1] == '_finish-update':
        from retrorecomp.updater import finish_update
        from retrorecomp.gui import launch

        try:
            error = finish_update(Path(sys.argv[2]), sys.argv[3], int(sys.argv[4]))
        except Exception as exc:
            error = str(exc)
        launch(update_error=error)
        return 0
    if len(sys.argv) == 4 and sys.argv[1] == '_install-pending':
        from retrorecomp.publishing import install_pending
        return install_pending(Path(sys.argv[2]), sys.argv[3])
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Retro-Recomp: multi-console ROM → local native executable.")
    sub = parser.add_subparsers(dest="command")
    build = sub.add_parser("convert", help="Convert a ROM into a standalone executable.")
    build.add_argument("rom", type=Path)
    build.add_argument("--language", choices=("en", "fr", "it", "es", "de", "zh", "ja", "ru"), default="en", help="Converter and game language (default: English).")
    build.add_argument("--title")
    build.add_argument("--output", type=Path)
    build.add_argument("--system", choices=('auto',*(p.id for p in PROFILES)), default="auto",
        help="Automatic console detection or an explicit choice for ambiguous .bin/.rom dumps.")
    build.add_argument("--profile", type=Path)
    add_machine_options(build, developer=False)
    build.add_argument("--video-standard", choices=("auto", *MASTER_SYSTEM.video_modes, "dmg", "mvs"), default="auto",
        help="Console timing; Game Gear uses NTSC, Game Boy uses DMG.")
    build.add_argument("--passes", type=int, default=3,
        help="Build/test/learn pass limit (1–10, default 3).")
    build.add_argument("--frames", type=int, default=1200)
    add_machine_switches(build, 'convert')
    build.add_argument('--scan-level', choices=('quick', 'standard', 'extended', 'thorough'),
        help='Discovery scan level for every console (default: the per-console level saved in Options, '
             'else standard; --md-advanced-scan means thorough and --nes-advanced-scan extended).')
    build.add_argument("--backend", choices=("functions", "banked"), default="banked",
        help="banked (default): extended native ROM coverage and learned RAM variants, Sega mapper.")
    covers = build.add_mutually_exclusive_group()
    covers.add_argument("--cover", type=Path, help="Choose an icon image; takes priority over BoxArt.")
    covers.add_argument("--no-cover", action="store_true", help="Build without box art icons.")
    build.add_argument("--boxart-dir", type=Path, help="Box art folder (default: BoxArt beside Retro-Recomp.exe).")
    build.add_argument("--no-online-cover", action="store_true", help="Use local box art only, without network access.")
    build.add_argument("--no-icon-tags", action="store_true", help="Keep box art icons without automatic peripheral badges.")
    build.add_argument("--keep-build", action="store_true", help="Keep each game's build folder under .build after publication (developer checks read it); also RETRO_RECOMP_KEEP_BUILD=1.")
    add_machine_options(build, developer=True)
    batch = sub.add_parser("batch", help="Convert several ROMs to a shared games folder.")
    batch.add_argument("roms", type=Path, nargs="*")
    batch.add_argument("--language", choices=("en", "fr", "it", "es", "de", "zh", "ja", "ru"), default="en", help="Converter and game language (default: English).")
    batch.add_argument("--rom-dir", type=Path, action="append", default=[],
        help="Add a mixed ROM folder recursively; repeat this option for more folders.")
    batch.add_argument("--system", choices=('auto',*(p.id for p in PROFILES)), default="auto")
    add_machine_options(batch)
    batch.add_argument("--output", type=Path, default=games_root(),
        help="Games root (default: Games beside the converter). Console folders are added automatically.")
    batch.add_argument("--backend", choices=("functions", "banked"), default="banked")
    batch.add_argument("--passes", type=int, default=3)
    batch.add_argument("--frames", type=int, default=3600)
    batch.add_argument("--jobs", type=int, default=3 if os.name == 'nt' else 1,
        help="Concurrent game conversions (1–8, default 3 on Windows, 1 on Linux).")
    batch.add_argument("--no-overwrite", action="store_true",
        help="Skip an already generated game instead of regenerating it.")
    batch.add_argument('--force', action='store_true', help='Regenerate even if an export is up to date (still respects --no-overwrite).')
    add_machine_switches(batch, 'batch')
    batch.add_argument('--scan-level', choices=('quick', 'standard', 'extended', 'thorough'),
        help='Discovery scan level for every console in the batch (default: the per-console levels saved in Options).')
    batch.add_argument("--video-standard", choices=("auto", *MASTER_SYSTEM.video_modes, "dmg", "mvs"), default="auto",
        help="Override console timing for this batch; auto resolves each ROM separately.")
    batch.add_argument("--boxart-dir", type=Path)
    batch.add_argument("--no-cover", action="store_true")
    batch.add_argument("--no-online-cover", action="store_true")
    batch.add_argument('--shared-base', action=argparse.BooleanOptionalAction, default=None,
        help="Bring the shared base up to date before the batch (default: the option saved in Options). Its qualified "
             "paths apply either way, so a known game takes the quick check instead of a discovery.")
    batch.add_argument("--no-icon-tags", action="store_true", help="Keep box art icons without automatic peripheral badges.")
    batch.add_argument("--keep-build", action="store_true", help="Keep each game's build folder under .build after publication (developer checks read it); also RETRO_RECOMP_KEEP_BUILD=1.")
    inspect = sub.add_parser("inspect", help="Identify a ROM without modifying it.")
    inspect.add_argument("rom", type=Path)
    sub.add_parser("setup", help="Prepare dependencies and compiler.")
    sub.add_parser("gui", help="Open the graphical interface.")
    memory = sub.add_parser("memory", help="Show game memory or import verified observations.")
    memory.add_argument("rom", type=Path, nargs="?")
    memory.add_argument("--import-manifest", type=Path)
    args = parser.parse_args()
    try:
        if args.command in (None, "gui"):
            from retrorecomp.gui import launch
            launch()
        elif args.command == "inspect":
            system = profile_for_path(args.rom)
            rom = system.read_rom(args.rom)
            print(json.dumps({**rom.metadata(), "system": system.id,
                "video_default": system.default_video_mode(args.rom),
                "video_default_source": "cartridge_header" if system.id in ('md', 'snes') else
                    "filename_only" if system.id == 'sms' else "console_fixed"},
                indent=2, ensure_ascii=False))
        elif args.command == "setup":
            dependencies()
            if os.name == 'nt':
                from retrorecomp.gameboy import _dependencies
                _dependencies(print)
                from retrorecomp.nes import _dependencies as nes_dependencies
                nes_dependencies(print)
        elif args.command == "memory":
            if args.rom:
                system = profile_for_path(args.rom)
                if system.id=='ng':
                    if args.import_manifest:
                        raise ConversionError('Neo Geo uses BIOS-scoped numeric memory, not Sega observation manifests.')
                    from retrorecomp.neogeo_knowledge import list_memory as ng_memory
                    rom=system.read_rom(args.rom)
                    print(json.dumps({'console':'ng','rom_sha256':rom.sha256,
                        'memories':[r for r in ng_memory() if r.get('source_sha256')==rom.sha256],
                        'runtime_learning':False},indent=2))
                    return 0
                if system.id in ('md', 'snes'):
                    if args.import_manifest:
                        raise ConversionError('16-bit proofs do not import Z80 observation manifests.')
                    from retrorecomp.console16 import conversion_rom, REPOSITORIES
                    rom = conversion_rom(args.rom, system.id)
                    from retrorecomp import megadrive, supernintendo
                    entries = megadrive.read_entries(rom) if system.id == 'md' else set()
                    ram = (megadrive.read_ram_variants(rom) if system.id == 'md' else
                           supernintendo.read_ram_variants(rom))
                    record = (megadrive.memory_file(rom) if system.id == 'md' else
                              supernintendo.memory_file(rom))
                    if system.id == 'snes':
                        from retrorecomp import snes_spc
                        masks = snes_spc.read_masks(rom)
                        sound_record = snes_spc.memory_file(rom)
                        sound = {'cpu': 'SPC700', 'guarded_opcode_variants': sum(value.bit_count() for value in masks),
                                 'library_bytes': sound_record.stat().st_size if sound_record.is_file() else 0}
                    else:
                        from retrorecomp import megadrive_z80
                        sound_record = megadrive_z80.memory_file(rom)
                        sound = {'cpu': 'Z80', 'guarded_opcode_variants': len(megadrive_z80.read_variants(rom)),
                                 'library_bytes': sound_record.stat().st_size if sound_record.is_file() else 0}
                    print(json.dumps({'system': system.id, 'sha256': rom.sha256,
                        'engine_revision': REPOSITORIES[system.id][1],
                        'analysis': 'instruction AOT and exact-ROM converter observations',
                        'rom_entries': len(entries), 'ram_variants': len(ram),
                        'library_bytes': record.stat().st_size if record.is_file() else 0,
                        'sound_cpu': sound,
                        'runtime_learning': False}, indent=2))
                    return 0
                if system.id == 'gb':
                    if args.import_manifest:
                        raise ConversionError("Game Boy uses verified entry traces, not Sega observation manifests.")
                    from retrorecomp.gameboy import memory_summary
                    print(json.dumps(memory_summary(system.read_rom(args.rom)), indent=2, ensure_ascii=False))
                    return 0
                if system.id == 'x68':
                    if args.import_manifest:
                        raise ConversionError('X68000 observations require exact media/firmware identity and fresh validation.')
                    from retrorecomp.compiled_games import read_json
                    rom=system.read_rom(args.rom)
                    profiles=[read_json(p) for p in library_root('x68').glob('*/compilation.json')]
                    print(json.dumps({'system':'x68','sha256':rom.sha256,
                        'profiles':[p for p in profiles if p.get('rom_sha256')==rom.sha256]},indent=2))
                    return 0
                if system.id == 'nes':
                    if args.import_manifest:
                        raise ConversionError("NES uses ROM-specific cycle traces, not Sega observation manifests.")
                    from retrorecomp.nes import memory_summary
                    print(json.dumps(memory_summary(system.read_rom(args.rom)), indent=2, ensure_ascii=False))
                    return 0
                game = GameMemory(system.read_rom(args.rom),
                    library_root(system.id) if system.id != 'sms' else None)
                if args.import_manifest:
                    print(json.dumps(game.import_manifest(args.import_manifest), indent=2))
                print(json.dumps(game.summary(), indent=2, ensure_ascii=False))
            else:
                if args.import_manifest:
                    parser.error("Provide a ROM to verify imported observations.")
                from retrorecomp.gameboy import list_memory
                from retrorecomp.nes import list_memory as list_nes_memory
                from retrorecomp.neogeo_knowledge import list_memory as list_ng_memory
                print(json.dumps({"directory": str(library_root()), "games": list_games(),
                    "game_boy_traces": list_memory(), "nes_cycle_traces": list_nes_memory(),
                    'neo_geo_memories':list_ng_memory()},
                    indent=2, ensure_ascii=False))
        elif args.command in ("convert", "batch"):
            if args.keep_build:
                from retrorecomp.build_cleanup import KEEP_VARIABLE
                os.environ[KEEP_VARIABLE] = '1'
            if not 1 <= args.passes <= 10 or not 1 <= args.frames <= 10000:
                parser.error("--passes must be 1–10; --frames must be 1–10000.")
            if args.command == 'batch' and not 1 <= args.jobs <= 8:
                parser.error("--jobs must be 1–8.")
            if args.command == "batch":
                paths = []
                for source in [*args.roms, *args.rom_dir]:
                    if source.is_dir():
                        paths.extend(discover_roms(source))
                    else:
                        paths.append(source)
                # Each multi-disk X68000 game is converted once, as a playlist.
                from retrorecomp.rom_sources import disk_sets
                from retrorecomp.i18n import tr
                sets = disk_sets(paths)
                if sets.grouped:
                    print(tr('x68_sets_grouped', args.language, count=sets.grouped), file=sys.stderr)
                for title, missing, total in sets.incomplete:
                    print(tr('x68_set_incomplete', args.language, title=title,
                             missing=', '.join(map(str, missing)), total=total), file=sys.stderr)
                paths = list(dict.fromkeys(p.resolve() for p in sets.paths))
                if not paths:
                    parser.error("Add ROMs or a folder with --rom-dir.")
                items = [identify(p, None if args.system == 'auto' else args.system) for p in paths]
                machine = machine_keywords(args)
                # The only firmware the shared base's keys depend on: the Neo Geo BIOS (shared_batch.rom_keys).
                ng_bios = machine.get('ng_bios')
                # The shared base, as the window applies it: its qualified paths let a known game take the
                # quick check; with the option on it is first brought up to date (at most once a day).
                from retrorecomp import shared_batch, online
                use_shared = (args.shared_base if args.shared_base is not None
                              else load_preferences().get('use_shared_base', True) is not False)
                keys = shared_batch.rom_keys([(item.system, item.sha256, item.path) for item in items
                                              if item.system and item.sha256 and not item.error], ng_bios)
                outcome = shared_batch.prepare(keys, use_shared)
                def problem(error):
                    if isinstance(error, online.ServiceConnectionError):
                        return tr('online_unreachable', args.language)
                    return getattr(error, 'reason', '') or str(error) or type(error).__name__
                say = lambda key, **values: tr(key, args.language, **values)
                for kind, text in shared_batch.base_lines(outcome['base'], outcome['summary'], outcome['error'],
                                                          say, problem):
                    if kind == 'log':
                        print(text, file=sys.stderr)
                if outcome['error'] is not None:
                    print(say('shared_unavailable', error=problem(outcome['error'])), file=sys.stderr)
                shared_batch.start_source(lambda more: shared_batch.prepare(more, use_shared), keys,
                                          {item.system for item in items})
                try:
                    record = convert_batch(items, args.output, shared_paths=outcome['paths'],
                        jobs=args.jobs, overwrite=not args.no_overwrite, force=args.force,
                        passes=args.passes, frames=args.frames,
                        backend=args.backend, language=args.language,
                        boxart_dir=args.boxart_dir, online_cover=not args.no_online_cover, use_cover=not args.no_cover,
                        icon_tags=not args.no_icon_tags, **switch_keywords(args),
                        scan_level=args.scan_level, console_scan=load_preferences().get('console_scan'),
                        **machine,
                        standard_override=None if args.video_standard == 'auto' else args.video_standard)
                finally:
                    shared_batch.stop_source()
                shared_batch.forget_rejected(outcome['paths'], record['games'])
                for game_output in {system_output(args.output, game['system']) for game in record['games']
                                    if game['status'] == 'success'}:
                    save_game_language(game_output, args.language)
                minutes, seconds = divmod(int(record.get('elapsed_seconds') or 0), 60)
                print(f"Retro-Recomp: batch finished in {minutes} min {seconds} s: "
                      f"{record['succeeded']}/{record['requested']} ready, {record['failed']} errors, "
                      f"{record['current'] + record['existing']} unchanged, {record['pending']} not started.",
                      file=sys.stderr)
                print(json.dumps(record, indent=2, ensure_ascii=False))
                return 1 if record["failed"] else 0
            else:
                item = identify(args.rom, None if args.system == 'auto' else args.system)
                if args.title:
                    item.title = args.title
                item.cover = args.cover
                record = convert_batch([item], args.output or games_root(), profile=args.profile,
                    passes=args.passes, frames=args.frames, backend=args.backend, language=args.language,
                    boxart_dir=args.boxart_dir, online_cover=not args.no_online_cover,
                    use_cover=not args.no_cover, icon_tags=not args.no_icon_tags,
                    **switch_keywords(args),
                    scan_level=args.scan_level, console_scan=load_preferences().get('console_scan'),
                    **machine_keywords(args),
                    standard_override=None if args.video_standard == 'auto' else args.video_standard)
                result = record['games'][0]
                if result['status'] not in ('success', 'current'):
                    raise ConversionError(result['message'])
                save_game_language(Path(result['executable']).parent, args.language)
        return 0
    except (ConversionError, OSError, TimeoutError, ValueError) as exc:
        print("Retro-Recomp: " + log_text(str(exc), getattr(args, "language", "en")), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
