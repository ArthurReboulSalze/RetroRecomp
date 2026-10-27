"""Capcom CPS-1 conversion profile: MAME/FBNeo romsets identified by CRC."""
from pathlib import Path
from . import Capabilities, Cpu, SystemProfile


class Cps1Profile(SystemProfile):
    id = 'cps1'
    name = 'Capcom CPS-1'
    extensions = ('.zip',)
    export_folder = 'CPS-1'
    video_modes = ('arcade',)
    # Each conversion compares native code with the interpreted reference;
    # the board model was compared with MAME on development sets only.
    status = 'experimental'
    cpus = (Cpu('m68000', 'main', 'instructions'), Cpu('z80', 'sound', 'instructions'))
    media_kinds = ('romset',)
    quick_state_family = 'rr16'
    # The standard boards keep no non-volatile memory.
    capabilities = Capabilities()
    feedback_kinds = frozenset({14, 15, 16})
    fallback_display = 'opcodes'
    default_frames = 3600
    quick_frames = 2400
    title_from_romset = True
    linux = 'pending'

    def read_rom(self, path: Path):
        from ..cps1 import read_set
        return read_set(path)

    def default_video_mode(self, path: Path) -> str:
        return 'arcade'

    def convert(self, path: Path, **options) -> Path:
        from ..cps1_conversion import convert
        return convert(path, **options)


CPS1 = Cps1Profile()
