from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
from smsrecomp.core import ConversionError, convert, dependencies, read_rom
from smsrecomp.library import GameMemory, list_games, library_root
from smsrecomp.paths import ROOT, save_game_language, games_directory
from smsrecomp.i18n import log_text
from smsrecomp.batch import identify, convert_batch
from smsrecomp.systems import MASTER_SYSTEM, profile_for_path


def main() -> int:
    if len(sys.argv) == 4 and sys.argv[1] == '_install-pending':
        from smsrecomp.publishing import install_pending
        return install_pending(Path(sys.argv[2]), sys.argv[3])
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Retro-Recomp: Master System ROM → Windows x64 executable.")
    sub = parser.add_subparsers(dest="command")
    build = sub.add_parser("convert", help="Convert a ROM into a standalone executable.")
    build.add_argument("rom", type=Path)
    build.add_argument("--language", choices=("en", "fr"), default="en", help="Converter and game language (default: English).")
    build.add_argument("--title")
    build.add_argument("--output", type=Path)
    build.add_argument("--profile", type=Path)
    build.add_argument("--video-standard", choices=("auto", *MASTER_SYSTEM.video_modes), default="auto",
        help="Master System console timing; auto uses the saved ROM choice or filename proposal.")
    build.add_argument("--passes", type=int, default=3,
        help="Build/test/learn pass limit (1–10, default 3).")
    build.add_argument("--frames", type=int, default=1200)
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
    batch.add_argument("--rom-dir", type=Path, help="Add .sms ROMs from a folder and its subfolders.")
    batch.add_argument("--output", type=Path, default=games_directory())
    batch.add_argument("--backend", choices=("functions", "banked"), default="banked")
    batch.add_argument("--passes", type=int, default=3)
    batch.add_argument("--frames", type=int, default=3600)
    batch.add_argument("--video-standard", choices=("auto", *MASTER_SYSTEM.video_modes), default="auto",
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
                "video_default_source": "filename_only"}, indent=2, ensure_ascii=False))
        elif args.command == "setup":
            dependencies()
        elif args.command == "memory":
            if args.rom:
                game = GameMemory(read_rom(args.rom))
                if args.import_manifest:
                    print(json.dumps(game.import_manifest(args.import_manifest), indent=2))
                print(json.dumps(game.summary(), indent=2, ensure_ascii=False))
            else:
                if args.import_manifest:
                    parser.error("Provide a ROM to verify imported observations.")
                print(json.dumps({"directory": str(library_root()), "games": list_games()}, indent=2, ensure_ascii=False))
        elif args.command in ("convert", "batch"):
            if not 1 <= args.passes <= 10 or not 1 <= args.frames <= 10000:
                parser.error("--passes must be 1–10; --frames must be 1–10000.")
            if args.command == "batch":
                paths = list(args.roms)
                if args.rom_dir:
                    if not args.rom_dir.is_dir():
                        parser.error("--rom-dir must refer to an existing folder.")
                    paths.extend(sorted(p for p in args.rom_dir.rglob("*") if p.is_file() and p.suffix.lower() == ".sms"))
                paths = list(dict.fromkeys(p.resolve() for p in paths))
                if not paths:
                    parser.error("Add ROMs or a folder with --rom-dir.")
                record = convert_batch([identify(p) for p in paths], args.output,
                    passes=args.passes, frames=args.frames, backend=args.backend, language=args.language,
                    boxart_dir=args.boxart_dir, online_cover=not args.no_online_cover, use_cover=not args.no_cover,
                    icon_tags=not args.no_icon_tags,
                    standard_override=None if args.video_standard == 'auto' else args.video_standard)
                save_game_language(args.output, args.language)
                print(json.dumps(record, indent=2, ensure_ascii=False))
                return 1 if record["failed"] else 0
            else:
                executable = convert(args.rom, title=args.title, output=args.output, profile=args.profile,
                        passes=args.passes, frames=args.frames, backend=args.backend, language=args.language,
                        cover=args.cover, boxart_dir=args.boxart_dir, online_cover=not args.no_online_cover,
                        use_cover=not args.no_cover, icon_tags=not args.no_icon_tags,
                        standard_override=None if args.video_standard == 'auto' else args.video_standard)
                save_game_language(executable.parent, args.language)
        return 0
    except (ConversionError, OSError, TimeoutError, ValueError) as exc:
        print("Retro-Recomp: " + log_text(str(exc), getattr(args, "language", "en")), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
