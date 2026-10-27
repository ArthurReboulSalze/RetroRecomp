"""Sharp X68000 profile (experimental: see docs/X68000.md)."""
from pathlib import Path
from . import Capabilities, Cpu, OptionKey, SystemProfile


class X68000Profile(SystemProfile):
    id = 'x68'
    name = 'Sharp X68000'
    extensions = ('.dim', '.xdf', '.m3u')
    export_folder = 'Sharp X68000'
    video_modes = ('native',)
    status = 'experimental'
    cpus = (Cpu('m68000', 'main', 'instructions'),)
    media_kinds = ('disk',)
    firmware = ('ipl', 'cgrom')
    quick_state_family = 'x68k'
    capabilities = Capabilities(mouse=True, keyboard=True, disks=True)
    feedback_kinds = frozenset({13})
    default_frames = 4000
    quick_frames = 4000
    # The result summary has no opcode line for this console yet (fallback_display
    # stays 'cycles'): the GUI prints the cycle form, as it always did.
    option_keys = (OptionKey('x68_ipl'), OptionKey('x68_cgrom'), OptionKey('x68_ram'))

    def read_rom(self, path: Path):
        from ..x68000 import read_input
        return read_input(path)

    def default_video_mode(self, path): return 'native'

    def convert(self, path, **options):
        from ..x68000_conversion import convert
        return convert(path, **options)

    def request_identity(self, item, options: dict, settings: dict) -> None:
        from ..x68000 import machine
        from ..x68000_conversion import sdk_stamp
        _, manifest = machine(item.path, options.get('x68_ipl'), options.get('x68_cgrom'), options.get('x68_ram', 2))
        settings['machine_identity'] = manifest.sha256
        settings['x68_sdk'] = sdk_stamp('game')
        settings.pop('x68_ipl', None); settings.pop('x68_cgrom', None)


X68000 = X68000Profile()
