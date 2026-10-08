from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
from smsrecomp.core import ConversionError, convert, dependencies, read_rom
from smsrecomp.library import GameMemory, list_games, library_root
from smsrecomp.paths import ROOT, save_game_language, games_root
from smsrecomp.i18n import log_text
from smsrecomp.batch import identify, convert_batch, system_output
from smsrecomp.systems import MASTER_SYSTEM, discover_roms, profile_for_path


def main() -> int:
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
        from smsrecomp import __version__

        return 0 if __version__ == sys.argv[2] else 1
    if len(sys.argv) == 4 and sys.argv[1] == '_apply-update':
        from smsrecomp.updater import apply_update

        return apply_update(Path(sys.argv[2]), sys.argv[3])
    if len(sys.argv) == 5 and sys.argv[1] == '_finish-update':
        from smsrecomp.updater import finish_update
        from smsrecomp.gui import launch

        try:
            error = finish_update(Path(sys.argv[2]), sys.argv[3], int(sys.argv[4]))
        except Exception as exc:
            error = str(exc)
        launch(update_error=error)
        return 0
    if len(sys.argv) == 4 and sys.argv[1] == '_install-pending':
        from smsrecomp.publishing import install_pending
        return install_pending(Path(sys.argv[2]), sys.argv[3])
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Retro-Recomp: multi-console ROM → Windows x64 executable.")
    sub = parser.add_subparsers(dest="command")
    build = sub.add_parser("convert", help="Convert a ROM into a standalone executable.")
    build.add_argument("rom", type=Path)
    build.add_argument("--language", choices=("en", "fr"), default="en", help="Converter and game language (default: English).")
    build.add_argument("--title")
    build.add_argument("--output", type=Path)
    build.add_argument("--system", choices=("auto", "sms", "gg", "gb", "nes", "md", "snes"), default="auto",
        help="Automatic console detection or an explicit choice for ambiguous .bin/.rom dumps.")
    build.add_argument("--profile", type=Path)
    build.add_argument("--video-standard", choices=("auto", *MASTER_SYSTEM.video_modes, "dmg"), default="auto",
        help="Console timing; Game Gear uses NTSC, Game Boy uses DMG.")
    build.add_argument("--passes", type=int, default=3,
        help="Build/test/learn pass limit (1–10, default 3).")
    build.add_argument("--frames", type=int, default=1200)
    build.add_argument("--gb-deep-validation", action=argparse.BooleanOptionalAction, default=True,
        help="Extra Game Boy CPU checks during play (default: on; use --no-gb-deep-validation for a faster check). Native discovery is unchanged.")
    build.add_argument('--md-advanced-scan', action=argparse.BooleanOptionalAction, default=False,
        help='Add a longer Mega Drive input replay and reference checks to each learning pass (default: off).')
    build.add_argument("--backend", choices=("functions", "banked"), default="banked",
        help="banked (default): extended native ROM coverage and learned RAM variants, Sega mapper.")
    covers = build.add_mutually_exclusive_group()
    covers.add_argument("--cover", type=Path, help="Choose an icon image; takes priority over BoxArt.")
    covers.add_argument("--no-cover", action="store_true", help="Build without box art icons.")
    build.add_argument("--boxart-dir", type=Path, help="Box art folder (default: BoxArt beside Retro-Recomp.exe).")
    build.add_argument("--no-online-cover", action="store_true", help="Use local box art only, without network access.")
    build.add_argument("--no-icon-tags", action="store_true", help="Keep box art icons without automatic peripheral badges.")
    batch = sub.add_parser("batch", help="Convert several ROMs to a shared games folder.")
    batch.add_argument("roms", type=Path, nargs="*")
    batch.add_argument("--language", choices=("en", "fr"), default="en", help="Converter and game language (default: English).")
    batch.add_argument("--rom-dir", type=Path, action="append", default=[],
        help="Add a mixed ROM folder recursively; repeat this option for more folders.")
    batch.add_argument("--system", choices=("auto", "sms", "gg", "gb", "nes", "md", "snes"), default="auto")
    batch.add_argument("--output", type=Path, default=games_root(),
        help="Games root (default: Games beside the converter). Console folders are added automatically.")
    batch.add_argument("--backend", choices=("functions", "banked"), default="banked")
    batch.add_argument("--passes", type=int, default=3)
    batch.add_argument("--frames", type=int, default=3600)
    batch.add_argument("--jobs", type=int, default=3,
        help="Concurrent game conversions across all console profiles (1–8, default 3).")
    batch.add_argument("--no-overwrite", action="store_true",
        help="Skip an already generated game instead of regenerating it.")
    batch.add_argument("--gb-deep-validation", action=argparse.BooleanOptionalAction, default=True,
        help="Extra Game Boy CPU checks during play (default: on; use --no-gb-deep-validation for a faster check). Ignored for other consoles.")
    batch.add_argument('--md-advanced-scan', action=argparse.BooleanOptionalAction, default=False,
        help='Extra Mega Drive coverage scan (default: off); ignored for other consoles.')
    batch.add_argument("--video-standard", choices=("auto", *MASTER_SYSTEM.video_modes, "dmg"), default="auto",
        help="Override console timing for this batch; auto resolves each ROM separately.")
    batch.add_argument("--boxart-dir", type=Path)
    batch.add_argument("--no-cover", action="store_true")
    batch.add_argument("--no-online-cover", action="store_true")
    batch.add_argument("--no-icon-tags", action="store_true", help="Keep box art icons without automatic peripheral badges.")
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
            from smsrecomp.gui import launch
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
            from smsrecomp.gameboy import _dependencies
            _dependencies(print)
            from smsrecomp.nes import _dependencies as nes_dependencies
            nes_dependencies(print)
        elif args.command == "memory":
            if args.rom:
                system = profile_for_path(args.rom)
                if system.id in ('md', 'snes'):
                    if args.import_manifest:
                        raise ConversionError('16-bit proofs do not import Z80 observation manifests.')
                    from smsrecomp.console16 import qualified_rom, REPOSITORIES
                    rom = qualified_rom(args.rom, system.id)
                    from smsrecomp import megadrive, supernintendo
                    entries = megadrive.read_entries(rom) if system.id == 'md' else set()
                    ram = (megadrive.read_ram_variants(rom) if system.id == 'md' else
                           supernintendo.read_ram_variants(rom))
                    record = (megadrive.memory_file(rom) if system.id == 'md' else
                              supernintendo.memory_file(rom))
                    if system.id == 'snes':
                        from smsrecomp import snes_spc
                        masks = snes_spc.read_masks(rom)
                        sound_record = snes_spc.memory_file(rom)
                        sound = {'cpu': 'SPC700', 'guarded_opcode_variants': sum(value.bit_count() for value in masks),
                                 'library_bytes': sound_record.stat().st_size if sound_record.is_file() else 0}
                    else:
                        from smsrecomp import megadrive_z80
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
                    from smsrecomp.gameboy import memory_summary
                    print(json.dumps(memory_summary(system.read_rom(args.rom)), indent=2, ensure_ascii=False))
                    return 0
                if system.id == 'nes':
                    if args.import_manifest:
                        raise ConversionError("NES uses ROM-specific cycle traces, not Sega observation manifests.")
                    from smsrecomp.nes import memory_summary
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
                from smsrecomp.gameboy import list_memory
                from smsrecomp.nes import list_memory as list_nes_memory
                print(json.dumps({"directory": str(library_root()), "games": list_games(),
                    "game_boy_traces": list_memory(), "nes_cycle_traces": list_nes_memory()},
                    indent=2, ensure_ascii=False))
        elif args.command in ("convert", "batch"):
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
                paths = list(dict.fromkeys(p.resolve() for p in paths))
                if not paths:
                    parser.error("Add ROMs or a folder with --rom-dir.")
                record = convert_batch([identify(p, None if args.system == 'auto' else args.system)
                                        for p in paths], args.output,
                    jobs=args.jobs, overwrite=not args.no_overwrite,
                    passes=args.passes, frames=args.frames,
                    backend=args.backend, language=args.language,
                    boxart_dir=args.boxart_dir, online_cover=not args.no_online_cover, use_cover=not args.no_cover,
                    icon_tags=not args.no_icon_tags, gb_deep_validation=args.gb_deep_validation,
                    md_advanced_scan=args.md_advanced_scan,
                    standard_override=None if args.video_standard == 'auto' else args.video_standard)
                for game_output in {system_output(args.output, game['system']) for game in record['games']
                                    if game['status'] == 'success'}:
                    save_game_language(game_output, args.language)
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
                    gb_deep_validation=args.gb_deep_validation,
                    md_advanced_scan=args.md_advanced_scan,
                    standard_override=None if args.video_standard == 'auto' else args.video_standard)
                result = record['games'][0]
                if result['status'] != 'success':
                    raise ConversionError(result['message'])
                save_game_language(Path(result['executable']).parent, args.language)
        return 0
    except (ConversionError, OSError, TimeoutError, ValueError) as exc:
        print("Retro-Recomp: " + log_text(str(exc), getattr(args, "language", "en")), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
