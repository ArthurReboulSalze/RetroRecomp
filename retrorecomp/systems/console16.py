"""Separate 16-bit standard-cartridge profiles, with circuit-specific support gates."""
from pathlib import Path
from . import Capabilities, Cpu, OptionKey, SystemProfile


class MegaDriveProfile(SystemProfile):
    id = 'md'
    name = 'Mega Drive'
    extensions = ('.md', '.gen')
    export_folder = 'Mega Drive'
    video_modes = ('ntsc', 'pal')
    cpus = (Cpu('m68000', 'main', 'instructions'), Cpu('z80', 'sound', 'cycles'))
    quick_state_family = 'rr16'
    capabilities = Capabilities(guns=('menacer', 'justifier'), battery=True)
    feedback_kinds = frozenset({5, 6, 7})
    fallback_display = 'opcodes'
    default_frames = 3600
    quick_frames = 1200
    option_keys = (OptionKey('md_advanced_scan'),)

    def read_rom(self, path: Path):
        from ..cartridge16 import read_megadrive_rom
        return read_megadrive_rom(path)

    def default_video_mode(self, path: Path) -> str:
        rom = self.read_rom(path)
        standard = rom.standard
        if standard == 'unknown':
            from ..megadrive import region_mask
            mask = region_mask(rom)
            if mask:
                return 'ntsc' if mask & 5 else 'pal'
        return 'ntsc' if standard == 'multi' else standard

    def convert(self, path: Path, **options) -> Path:
        from ..console16 import convert16
        return convert16(path, system_id=self.id, **options)


class SnesProfile(SystemProfile):
    id = 'snes'
    name = 'Super Nintendo'
    extensions = ('.sfc', '.smc')
    export_folder = 'Super Nintendo'
    video_modes = ('ntsc', 'pal')
    cpus = (Cpu('65816', 'main', 'instructions'), Cpu('spc700', 'sound', 'instructions'))
    # Circuits counted apart from the CPUs (snes_chips.py).
    cartridge_devices = ('superfx', 'dsp1', 'cx4')
    quick_state_family = 'rr16'
    capabilities = Capabilities(guns=('super_scope',), battery=True)
    feedback_kinds = frozenset({8, 9})
    fallback_display = 'opcodes'
    default_frames = 1200
    quick_frames = 1200
    option_keys = (OptionKey('md_advanced_scan'),)

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
