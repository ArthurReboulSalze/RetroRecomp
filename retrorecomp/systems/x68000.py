"""Sharp X68000 profile (experimental: see docs/X68000.md)."""
from pathlib import Path
from . import SystemProfile


class X68000Profile(SystemProfile):
    id = 'x68'
    name = 'Sharp X68000'
    extensions = ('.dim', '.xdf', '.m3u')
    export_folder = 'Sharp X68000'
    video_modes = ('native',)
    experimental = True

    def read_rom(self, path: Path):
        from ..x68000 import read_input
        return read_input(path)

    def default_video_mode(self, path): return 'native'

    def convert(self, path, **options):
        from ..x68000_conversion import convert
        return convert(path, **options)


X68000 = X68000Profile()
