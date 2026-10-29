"""Separate 16-bit standard-cartridge profiles, with circuit-specific support gates."""
from pathlib import Path
from . import Capabilities, Cpu, OptionKey, SystemProfile
from .specs import (CARTRIDGE_BOUNDS, Catalogues, Identify, InputLayout, LibraryLayout, PathSpec, ReportShape,
                    SharedKnowledge)


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
    path_spec = PathSpec(order=4, sections=(('m68k', 'md'), ('z80', 'md-sound')),
                         source_bounds=(('rom', CARTRIDGE_BOUNDS),), required_sources=('rom',),
                         shapes=(('m68k', 'md', dict(roles=('rom',), caps={'phys': 65536, 'insn': 2048},
                                                     entry_align=2, entry_min=0x200, entry_tail=8,
                                                     windows=((0xe00000, 0x1000000),), contained=True,
                                                     length=(2, 16), length_align=2, address_align=2)),
                                 ('z80', 'md-sound', dict(roles=('rom',), caps={'insn': 32768},
                                                          windows=((0, 0x4000), (0x8000, 0x10000)),
                                                          length=(4, 4), guard='derived'))))
    report_shape = ReportShape('console16', 'native_percentage')
    catalogues = Catalogues(libretro='libretro-thumbnails/Sega_-_Mega_Drive_-_Genesis', screenscraper=1,
                            thegamesdb=18, wikidata=('Q10676',), cover_references=True)
    library_layout = LibraryLayout(folder='md', summary_glob='*/native-entries.json')
    input_layout = InputLayout(('a', 'b', 'c'), ('x', 'y', 'z'), None, 240, script_format='console16')
    shared_knowledge = SharedKnowledge('stable', site_builder=True)
    host_adapter = 'adapters/rrhk_md.c'
    stamp_groups = ('megadrive_codegen', 'megadrive_z80', 'md_prefetch', 'guns16')
    identify = Identify(content_order=2)

    def identify_content(self, data: bytes):
        from ..cartridge16 import is_megadrive
        return self if is_megadrive(data) else None

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
    path_spec = PathSpec(order=5, sections=(('w65c816', 'snes'), ('spc700', 'snes')),
                         source_bounds=(('rom', CARTRIDGE_BOUNDS),), required_sources=('rom',),
                         shapes=(('w65c816', 'snes', dict(roles=('rom',), caps={'insn': 16384, 'opcode_ptr': 16384},
                                                          windows=((0, 0x1000000),), length=(4, 4), guard='first')),
                                 ('spc700', 'snes', dict(roles=('rom',),
                                                         caps={'spc_refs': 262144, 'spc_ranges': 262144,
                                                               'spc_bitmaps': 262144, 'spc_deltas': 262144},
                                                         windows=((0, 0xf0), (0x100, 0x10000)), guard='first',
                                                         budget=262144))))
    report_shape = ReportShape('console16', 'native_percentage')
    catalogues = Catalogues(libretro='libretro-thumbnails/Nintendo_-_Super_Nintendo_Entertainment_System',
                            screenscraper=4, thegamesdb=6, wikidata=('Q183259',), cover_references=True)
    library_layout = LibraryLayout(folder='snes', summary_glob='*/native-ram.json')
    input_layout = InputLayout(('a', 'b', 'x', 'y'), ('l', 'r'), 'select', 240, script_format='console16')
    shared_knowledge = SharedKnowledge('stable', site_builder=True)
    host_adapter = 'adapters/rrhk_snes.c'
    stamp_groups = ('guns16',)
    identify = Identify(content_order=4)

    def identify_content(self, data: bytes):
        from ..cartridge16 import snes_header
        # A copier header of 512 bytes may precede the image.
        offset = 512 if len(data) % 16384 == 512 else 0
        return self if snes_header(data[offset:]) is not None else None

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
