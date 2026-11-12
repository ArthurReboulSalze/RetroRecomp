"""Nintendo 64 profile (experimental: see docs/NINTENDO_64.md).

The machine is listed when the installation carries the converter's own files (`available()`); an N64 image is refused with a
sentence otherwise.

What it converts: a cartridge image (any byte order: .z64, .v64, .n64, or a .rom whose content is an N64 image), run on Mupen64Plus
(GPL-2.0-or-later, the libretro core "Mupen64Plus-Next", pinned) with the ParaLLEl-RDP renderer (MIT, Vulkan) behind our own MIT glue
and the LLE ParaLLEl-RSP. The VR4300 instructions the conversion sees running become guarded native blocks: C that calls the core's
own instruction handlers with constant opcodes (no fetch, no decode, blocks chained), keyed by address and code identity; the rest
runs, counted, on the core's interpreter. The game executable is GPL-3.0 as a whole and holds no noncommercial code. Not yet: the
64DD, the Transfer Pak, the VRU, TLB-mapped code as native blocks, a game played on Linux.
"""
from pathlib import Path

from . import Capabilities, ConsoleMismatchError, Cpu, SystemProfile, UnsupportedConsoleError
from .specs import Catalogues, Identify, LibraryLayout, PathSpec, ReportShape

# Where native blocks may start: KSEG0 view of RDRAM (8 MiB with the Expansion Pak).
APERTURES = ((0x80000000, 0x80800000),)


class Nintendo64Profile(SystemProfile):
    id = 'n64'
    # The third-party components compiled into its games (retrorecomp/notices.py); the player shell's are added.
    notice_files = ('licenses/mupen64plus-next.md',)
    name = 'Nintendo 64'
    extensions = ('.z64', '.v64', '.n64')
    export_folder = 'Nintendo 64'
    video_modes = ('ntsc', 'pal')
    status = 'experimental'
    scope_note = 'Nintendo 64 cartridges (NTSC, PAL), Vulkan renderer, no 64DD'
    cpus = (Cpu('vr4300', 'main', 'instructions'),)
    media_kinds = ('cartridge',)
    firmware = ()
    quick_state_family = 'n64'
    capabilities = Capabilities(battery=True)
    linux = 'witnessed'   # two games converted headless on a Debian 13 PC, traces equal to Windows', a state resumed; not played there
    feedback_kinds = frozenset({25})
    default_frames = 3600
    quick_frames = 3600
    fallback_display = 'opcodes'
    stamp_groups = ('conversion_gates',)
    path_spec = PathSpec(order=15, sections=(('vr4300', 'n64'),),
                         source_bounds=(('cart', (0x101000, 64 * 1024 * 1024)),),
                         shapes=(('vr4300', 'n64', dict(roles=('cart',), caps={'insn': 262144, 'span': 65536},
                                                        windows=APERTURES, contained=True, length=(4, 4), length_align=4,
                                                        offset_align=4, address_align=4, span_max=1 << 23)),))
    report_shape = ReportShape('n64_conversion', 'cartridge')
    library_layout = LibraryLayout(folder='n64', summary_glob='*/compilation.json')
    catalogues = Catalogues(libretro='libretro-thumbnails/Nintendo_-_Nintendo_64')
    # A cartridge image is recognised by its first word (three byte orders) and its boot entry point, never by the extension alone.
    identify = Identify(path_order=45)

    def available(self) -> bool:
        from ..n64 import converter_available
        return converter_available()

    def identify_path(self, path: Path, suffix: str, selected_system: str | None):
        from ..n64 import CONTENT_EXTENSIONS, recognise
        if suffix not in self.extensions and suffix not in CONTENT_EXTENSIONS:
            return None
        if not recognise(path):
            return None
        if not self.available():
            raise UnsupportedConsoleError('The experimental Nintendo 64 profile is unavailable in this installation.')
        if selected_system and selected_system != self.id:
            raise ConsoleMismatchError('Detected Nintendo 64; choose Automatic or Nintendo 64.', self.id)
        return self

    def read_rom(self, path: Path):
        from ..n64 import read_input
        return read_input(path)

    def default_video_mode(self, path):
        from ..n64 import video_mode
        return video_mode(path)

    def convert(self, path, **options):
        from ..n64_conversion import convert
        return convert(path, **options)


NINTENDO_64 = Nintendo64Profile()
