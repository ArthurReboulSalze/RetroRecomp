"""Separate experimental 16-bit profiles; conversion remains ROM-qualified."""
from pathlib import Path
from . import SystemProfile


class MegaDriveProfile(SystemProfile):
    id = 'md'
    name = 'Mega Drive'
    extensions = ('.md', '.gen')
    export_folder = 'Mega Drive'
    video_modes = ('ntsc',)

    def read_rom(self, path: Path):
        from ..cartridge16 import read_megadrive_rom
        return read_megadrive_rom(path)

    def default_video_mode(self, path: Path) -> str:
        standard = self.read_rom(path).standard
        return 'ntsc' if standard == 'multi' else standard

    def convert(self, path: Path, **options) -> Path:
        from ..console16 import convert16
        return convert16(path, system_id=self.id, **options)


class SnesProfile(SystemProfile):
    id = 'snes'
    name = 'Super Nintendo'
    extensions = ('.sfc', '.smc')
    export_folder = 'Super Nintendo'
    video_modes = ('ntsc',)

    def read_rom(self, path: Path):
        from ..cartridge16 import read_snes_rom
        return read_snes_rom(path)

    def default_video_mode(self, path: Path) -> str:
        return self.read_rom(path).standard

    def convert(self, path: Path, **options) -> Path:
        from ..console16 import convert16
        return convert16(path, system_id=self.id, **options)


MEGA_DRIVE = MegaDriveProfile()
SUPER_NINTENDO = SnesProfile()
