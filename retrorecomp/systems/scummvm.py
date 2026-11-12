"""Adventure (ScummVM): adventure games run in ScummVM, one executable per game (docs/SCUMMVM.md).

A category of its own, emulated and 0 % native by design: nothing is recompiled, and nothing is meant to be. The input is a
game folder; ScummVM's own detection names the game; the runtime is the build family of the detected engine
(scummvm_build); the game's files are packed, unchanged, into the executable (scummvm_export). No game is named here.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import OptionKey, SystemProfile
from .specs import Catalogues, Identify, ReportShape


class ScummvmProfile(SystemProfile):
    id = 'scummvm'
    # Every notice of its executables (retrorecomp/notices.py): the runtime is its own program, not the player shell.
    notice_files = ('licenses/scummvm.md', 'native/scummvm/LICENSE', 'licenses/freetype.md', 'licenses/SDL2.md', 'licenses/llvm-mingw.md')
    shell_notices = False
    name = 'Adventure (ScummVM)'
    extensions = ()
    export_folder = 'ScummVM'
    video_modes = ('scummvm',)
    status = 'supported'     # the owner's decision of 7 November 2026; what that means here is written in docs/SCUMMVM.md
    scope_note = ('Emulated, 0 % native code, by design: ScummVM interprets the game. Games that need Ogg Vorbis, FLAC or '
                  'MP3 decoders (CD audio rips, compressed speech) are not supported yet.')
    emulated = 'ScummVM interprets the game; no CPU is recompiled and none will be: the native share is 0 by design.'
    accepts_folders = True
    media_kinds = ('folder',)
    title_from_romset = True
    linux = 'witnessed'   # one small game (Lure of the Temptress) from its packed exe on a Debian 13 PC, 6 November 2026 (docs/SCUMMVM.md)
    fallback_display = 'opcodes'
    option_keys = (OptionKey('scummvm_choice', kind='choice', label='scummvm_choice', hint='tip_scummvm_choice',
                             choices=tuple(range(0, 10)), default=0),
                   OptionKey('scummvm_pack', signature=False, kind='action', label='scummvm_pack', hint='tip_scummvm_pack'))
    # A folder is claimed in the stage that looks at the input itself, before any other machine (a file is never this one's).
    identify = Identify(path_order=5)
    report_shape = ReportShape('scummvm_export', 'scummvm')
    # libretro-thumbnails/ScummVM (Named_Boxarts, Named_Titles, Named_Snaps) and ScreenScraper platform 123 ("ScummVM"),
    # both checked at their source on 6 November 2026.
    catalogues = Catalogues(libretro='libretro-thumbnails/ScummVM', screenscraper=123)

    def request_identity(self, item, options: dict, settings: dict) -> None:
        """A folder is never hashed as a file: unless the player chose a cover, the item gets the cover file the shared
        cover pipeline finds for the detected title (or the converter's own picture), which freshness then hashes in
        place of the input. The reviewed cover-reference lookup is skipped for game folders (docs/SCUMMVM.md)."""
        if item.cover or not options.get('use_cover', True) or not Path(item.path).is_dir():
            return
        from ..scummvm_export import folder_cover
        item.cover = folder_cover(item.title, Path(item.path), online=options.get('online_cover', True),
                                  emit=lambda message: None)

    def identify_path(self, path: Path, suffix: str, selected_system: str | None):
        if not Path(path).is_dir():
            return None
        return self if self.claims_folder(path) else None

    def find_folders(self, root: Path, notice=None) -> list[Path]:
        """The game folders below `root`. Without the build tools (and no runtime built yet) detection cannot run: the
        discovery refuses with a sentence (FolderDiscoveryUnavailable) instead of starting a build. With them, `notice`
        receives the sentence that says a build of the detection is starting (minutes, on a first use)."""
        from ..scummvm_build import ScummvmBuildError
        from ..scummvm_export import find_game_folders
        from .registry import FolderDiscoveryUnavailable
        try:
            return find_game_folders(Path(root), (lambda: notice('scummvm_preparing')) if notice else None)
        except ScummvmBuildError as exc:        # no tools, no network, or a failed build: say which, never a dead scan
            raise FolderDiscoveryUnavailable(exc.key, str(exc)) from exc

    def run_option_action(self, name: str, step) -> str:
        """The button of an OptionKey of kind 'action', off the window's thread: `step(key, **values)` says what it is doing
        (interface string keys). Returns the key of the result; an exception's text is the failure. The only one: the pack."""
        from ..scummvm_build import prepare_pack

        def said(text: str) -> None:
            fetched = re.match(r'Téléchargement de (\S+?)(?:…| )', text)
            if fetched:
                step('tools_step_download', name=fetched.group(1))
            elif text.startswith('Mise à jour de SDL'):
                step('deps_step_sdl_update')
            elif 'SDL2' in text:
                step('deps_step_sdl')
            else:
                step('scummvm_pack_compile')
        return 'scummvm_pack_done' if prepare_pack(said) else 'scummvm_pack_ready'

    def claims_folder(self, folder: Path) -> bool:
        from ..core import ConversionError
        from ..scummvm_build import ScummvmBuildError
        from ..scummvm_export import candidates_of
        try:
            return bool(candidates_of(Path(folder)))
        except ScummvmBuildError as exc:                   # tools missing, or the detection runtime failed to build
            raise ConversionError(str(exc)) from exc       # an error on that item, not a crash

    def read_rom(self, path: Path):
        from ..core import ConversionError
        from ..scummvm_build import ScummvmBuildError
        from ..scummvm_export import ScummvmExportError, read_folder
        if not Path(path).is_dir():
            # The selection "Adventure (ScummVM)" hands every queued file here: an adventure is a folder, never one file.
            raise ConversionError(f'An adventure game is a folder, not a file: {Path(path).name}')
        try:
            return read_folder(Path(path))
        except (ScummvmBuildError, ScummvmExportError) as exc:    # an error on that item, never a crash of the scan
            raise ConversionError(str(exc)) from exc

    def default_video_mode(self, path: Path) -> str:
        return 'scummvm'

    def convert(self, path: Path, **options) -> Path:
        from ..scummvm_export import convert
        return convert(path, **options)


SCUMMVM = ScummvmProfile()
