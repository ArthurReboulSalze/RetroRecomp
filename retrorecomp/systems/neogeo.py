"""Neo Geo conversion profile with explicitly selected, verified firmware."""
from pathlib import Path
from . import SystemProfile


class NeoGeoProfile(SystemProfile):
    id = 'ng'
    name = 'Neo Geo'
    extensions = ('.neo',)
    export_folder = 'Neo Geo'
    video_modes = ('mvs',)
    # Supported cartridge scope; reference agreement is not universal fidelity.
    experimental = False

    def read_rom(self, path: Path):
        from ..neogeo import read_set
        return read_set(path)

    def default_video_mode(self, path: Path) -> str:
        return 'mvs'

    def convert(self, path: Path, **options) -> Path:
        from ..neogeo_conversion import convert
        return convert(path, **options)


NEOGEO = NeoGeoProfile()
