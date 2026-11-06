"""Adventure (ScummVM): adventure games run in ScummVM, one executable per game (docs/SCUMMVM.md).

A category of its own, emulated and 0 % native by design: nothing is recompiled, and nothing is meant to be. The input is a
game folder; ScummVM's own detection names the game; the runtime is the build family of the detected engine
(scummvm_build); the game's files are packed, unchanged, into the executable (scummvm_export). No game is named here.
"""
from __future__ import annotations

from pathlib import Path

from . import OptionKey, SystemProfile
from .specs import Catalogues, Identify, ReportShape


class ScummvmProfile(SystemProfile):
    id = 'scummvm'
    name = 'Adventure (ScummVM)'
    extensions = ()
    export_folder = 'ScummVM'
    video_modes = ('scummvm',)
    status = 'experimental'
    scope_note = ('Emulated, 0 % native code, by design: ScummVM interprets the game. Games that need Ogg Vorbis, FLAC or '
                  'MP3 decoders (CD audio rips, compressed speech) are not supported yet.')
    emulated = 'ScummVM interprets the game; no CPU is recompiled and none will be: the native share is 0 by design.'
    accepts_folders = True
    media_kinds = ('folder',)
    title_from_romset = True
    linux = 'pending'
    fallback_display = 'opcodes'
    option_keys = (OptionKey('scummvm_choice', kind='choice', label='scummvm_choice', hint='tip_scummvm_choice',
                             choices=tuple(range(0, 10)), default=0),)
    # A folder is claimed in the stage that looks at the input itself, before any other machine (a file is never this one's).
    identify = Identify(path_order=5)
    report_shape = ReportShape('scummvm_export', 'scummvm')
    # libretro-thumbnails/ScummVM (Named_Boxarts, Named_Titles, Named_Snaps) and ScreenScraper platform 123 ("ScummVM"),
    # both checked at their source on 6 November 2026.
    catalogues = Catalogues(libretro='libretro-thumbnails/ScummVM', screenscraper=123)

    def identify_path(self, path: Path, suffix: str, selected_system: str | None):
        if not Path(path).is_dir():
            return None
        return self if self.claims_folder(path) else None

    def find_folders(self, root: Path) -> list[Path]:
        from ..scummvm_export import find_game_folders
        return find_game_folders(Path(root))

    def claims_folder(self, folder: Path) -> bool:
        from ..scummvm_export import candidates_of
        return bool(candidates_of(Path(folder)))

    def read_rom(self, path: Path):
        from ..scummvm_export import read_folder
        return read_folder(Path(path))

    def default_video_mode(self, path: Path) -> str:
        return 'scummvm'

    def convert(self, path: Path, **options) -> Path:
        from ..scummvm_export import convert
        return convert(path, **options)


SCUMMVM = ScummvmProfile()
