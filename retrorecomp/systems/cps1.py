"""Capcom CPS-1 conversion profile: MAME/FBNeo romsets identified by CRC."""
from pathlib import Path
from . import SystemProfile


class Cps1Profile(SystemProfile):
    id = 'cps1'
    name = 'Capcom CPS-1'
    extensions = ('.zip',)
    export_folder = 'CPS-1'
    video_modes = ('arcade',)
    # Board model and native code are compared with the internal reference
    # only; the board itself has been compared with MAME on two games.
    experimental = True

    def read_rom(self, path: Path):
        from ..cps1 import read_set
        return read_set(path)

    def default_video_mode(self, path: Path) -> str:
        return 'arcade'

    def convert(self, path: Path, **options) -> Path:
        from ..cps1_conversion import convert
        return convert(path, **options)


CPS1 = Cps1Profile()
