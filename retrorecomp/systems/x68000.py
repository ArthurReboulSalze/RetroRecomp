"""Sharp X68000 profile (experimental: see docs/X68000.md)."""
from pathlib import Path
from . import Capabilities, ConsoleMismatchError, Cpu, OptionKey, SystemProfile, UnsupportedConsoleError
from .specs import Catalogues, Identify, LibraryLayout, PathSpec, ReportShape


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
    # Checks count interpreted 68000 opcodes and the result summary carries
    # them, so the summary line reads like the other opcode consoles.
    fallback_display = 'opcodes'
    option_keys = (OptionKey('x68_ipl', kind='path', label='x68_ipl'),
                   OptionKey('x68_cgrom', kind='path', label='x68_cgrom'),
                   OptionKey('x68_ram', kind='choice', label='RAM (MiB)', choices=(2, 4), default=2))
    developer_only = True
    path_spec = PathSpec(order=8, sections=(('m68k', 'x68'),),
                         source_bounds=(('ipl', (1, 1 << 20)), ('disk', (1, 1 << 30))))
    report_shape = ReportShape('x68000_conversion', 'exploration_checks')
    catalogues = Catalogues(libretro='libretro-thumbnails/Sharp_-_X68000', cover_references=True)
    library_layout = LibraryLayout(folder='x68', summary_glob='*/compilation.json')
    # No pad layout for the random routes: it plays routes of its own (x68000_scan.long_routes).
    # Disk images and playlists are claimed by their extension, whatever their bytes.
    identify = Identify(path_order=10)

    def available(self) -> bool:
        from ..x68000 import developer_available
        return developer_available()

    def identify_path(self, path: Path, suffix: str, selected_system: str | None):
        if suffix not in self.extensions:
            return None
        if not self.available():
            raise UnsupportedConsoleError(
                'The experimental Sharp X68000 profile is unavailable in this installation.')
        if selected_system and selected_system != self.id:
            raise ConsoleMismatchError('Detected Sharp X68000; choose Automatic or Sharp X68000.', self.id)
        return self

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
