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
    if len(sys.argv) == 4 and sys.argv[1] == '_install-pending':
        from smsrecomp.publishing import install_pending
        return install_pending(Path(sys.argv[2]), sys.argv[3])
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Retro-Recomp: Master System / Game Gear / Game Boy / NES ROM → Windows x64 executable.")
    sub = parser.add_subparsers(dest="command")
    build = sub.add_parser("convert", help="Convert a ROM into a standalone executable.")
    build.add_argument("rom", type=Path)
    build.add_argument("--language", choices=("en", "fr"), default="en", help="Converter and game language (default: English).")
    build.add_argument("--title")
    build.add_argument("--output", type=Path)
    build.add_argument("--system", choices=("auto", "sms", "gg", "gb", "nes"), default="auto",
        help="Automatic console detection or an explicit choice for ambiguous .bin/.rom dumps.")
    build.add_argument("--profile", type=Path)
    build.add_argument("--video-standard", choices=("auto", *MASTER_SYSTEM.video_modes, "dmg"), default="auto",
        help="Console timing; Game Gear uses NTSC, Game Boy uses DMG.")
    build.add_argument("--passes", type=int, default=3,
        help="Build/test/learn pass limit (1–10, default 3).")
    build.add_argument("--frames", type=int, default=1200)
    build.add_argument("--gb-deep-validation", action="store_true",
        help="Extra Game Boy CPU checks during play; can add several minutes per game. Native discovery is unchanged.")
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
    batch.add_argument("--system", choices=("auto", "sms", "gg", "gb", "nes"), default="auto")
    batch.add_argument("--output", type=Path, default=games_root(),
        help="Games root (default: Games beside the converter). Console folders are added automatically.")
    batch.add_argument("--backend", choices=("functions", "banked"), default="banked")
    batch.add_argument("--passes", type=int, default=3)
    batch.add_argument("--frames", type=int, default=3600)
    batch.add_argument("--gb-deep-validation", action="store_true",
        help="Extra Game Boy CPU checks during play; can add several minutes per game. Ignored for other consoles.")
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
                "video_default_source": "filename_only" if system.id == 'sms' else "console_fixed"},
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
                    passes=args.passes, frames=args.frames, backend=args.backend, language=args.language,
                    boxart_dir=args.boxart_dir, online_cover=not args.no_online_cover, use_cover=not args.no_cover,
                    icon_tags=not args.no_icon_tags, gb_deep_validation=args.gb_deep_validation,
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
