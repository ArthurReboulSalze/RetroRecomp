"""MSX and MSX2 profiles (experimental: see docs/MSX.md).

What it converts: an MSX1 cartridge (plain 8 KiB to 64 KiB, Konami, Konami SCC, ASCII 8 KiB or ASCII 16 KiB mapper, read from a
.rom, a .mx1 or a ZIP holding one), booted by C-BIOS 0.29a or by the player's own MSX BIOS. The cartridge and the BIOS are
translated ahead of time by the shared banked Z80 chain (retrorecomp/z80_chain.py) on the MSX's own machine description: a
region map of eight 8 KiB regions, the cartridge then the BIOS as sources, one wait state per M1 cycle, /INT read at the end of
each instruction. Code run from RAM is learned and translated with byte guards; what is left runs on the reference interpreter,
counted. The TMS9918A, the AY-3-8910, the PPI, the slots and the mappers are our own C (native/msx_machine).

The MSX2 (`msx2`) is the same chain and the same cartridges on the MSX2 board: the V9938 (with its command engine, timing approximated), the
memory mapper and the RP5C01 (native/msx_machine/msx_v9938*.c, msx_msx2.c), booted by C-BIOS 0.29a's MSX2 images or by the
player's own MSX2 main ROM and sub-ROM. Its BIOS source is one 64 KiB image (main ROM, logo page, sub-ROM), so the region map
and the generator are the MSX1's. A cartridge's bytes do not say MSX1 or MSX2: a .mx2 is the MSX2's, a .rom (or a ZIP holding
one) is when the player chose MSX2 or when it sits in a folder named msx2; any other is the MSX1's.
Not yet: disks, cassettes, FM-PAC, the SRAM mappers and the rarer ones.
"""
from __future__ import annotations

from pathlib import Path

from . import Capabilities, Cpu, OptionKey, SystemProfile
from ..z80_chain import Z80Machine, Z80RegionMap
from .specs import Catalogues, Identify, LibraryLayout, PathSpec, ReportShape

# The MSX on the banked Z80 chain: eight 8 KiB regions, each showing a bank of the cartridge (source 0) or of the BIOS
# (source 1, the 48 KiB of slot 0) or RAM; one wait state per M1 cycle; /INT read once the machine has caught up with the
# instruction; the start of each step and the reference CPU's state copies from the chain; its own generator folders.
MSX_MACHINE = Z80Machine('msx', Z80RegionMap(region_bits=13, sources=('cartridge', 'bios'), bank_values=256,
                                             scope='msx-cartridge-region-map'),
                         m1_wait=1, irq_sample='instruction_end', generator_tag='-msx', step_begin=True,
                         reference_state=True)

# 8 KiB to 2 MiB cartridges; the BIOS of slot 0: a 32 KiB main ROM, with C-BIOS's 16 KiB logo ROM.
CARTRIDGE_BOUNDS = (0x2000, 0x200000)
BIOS_BOUNDS = (0x8000, 0xC000)


class MsxProfile(SystemProfile):
    id = 'msx'
    name = 'MSX'
    extensions = ('.mx1',)
    archived_rom_limits = (('.mx1', 0x200000),)
    export_folder = 'MSX'
    video_modes = ('ntsc', 'pal')
    status = 'experimental'
    scope_note = ('MSX1 cartridges (plain, Konami, Konami SCC, ASCII 8 and ASCII 16 mappers) with C-BIOS or your own MSX BIOS; '
                  'no MSX2, disks or cassettes yet')
    # The machine has one processor; the PSG and the SCC are chips of our own C, not CPUs.
    cpus = (Cpu('z80', 'main', 'cycles'),)
    media_kinds = ('cartridge',)
    # The player's own MSX BIOS (a 32 KiB main ROM). Optional: without one the machine boots C-BIOS. The option is not part of
    # the request signature; the identity of the BIOS used is (request_identity).
    firmware = ('bios',)
    option_keys = (OptionKey('msx_bios', signature=False, kind='path', label='msx_bios_label'),)
    capabilities = Capabilities(keyboard=True)
    quick_state_family = 'msx'
    host_adapter = 'adapters/rrhk_msx.inc'
    linux = 'pending'
    # Its kind in native/runtime_feedback.h (RR_FB_MSX), reserved: the player records nothing for path sharing yet.
    feedback_kinds = frozenset({26})
    stamp_groups = ('z80_main', 'hostkit_computer')
    z80_machine = MSX_MACHINE
    path_spec = PathSpec(order=16, sections=(('z80', 'msx'),),
                         source_bounds=(('rom', CARTRIDGE_BOUNDS), ('bios', BIOS_BOUNDS)),
                         required_sources=('rom',), hashed_sources=('rom', 'bios'),
                         shapes=(('z80', 'msx', dict(roles=('rom', 'bios'), caps={'window4': 4096})),))
    report_shape = ReportShape('msx_conversion', 'msx_checks')
    catalogues = Catalogues(libretro='libretro-thumbnails/Microsoft_-_MSX')
    library_layout = LibraryLayout(folder='msx', summary_glob='*/compilation.json')
    # A .rom (or .bin) is the MSX's when its bytes hold an MSX cartridge header, asked after the five consoles that
    # recognise their own headers.
    identify = Identify(content_order=6)

    def identify_content(self, data: bytes):
        from ..msx_rom import looks_like_cartridge
        return self if looks_like_cartridge(data) else None

    def request_identity(self, item, options: dict, settings: dict) -> None:
        """The BIOS the machine boots is part of the request: the player's own image (its SHA-256), or C-BIOS (its pin)."""
        from .. import msx_cbios
        from ..msx_conversion import own_bios
        try:
            bios = own_bios(options.get('msx_bios'))
        except (OSError, ValueError):
            bios = None
        settings['msx_bios'] = bios[1] if bios is not None else 'cbios-' + msx_cbios.VERSION

    def read_rom(self, path: Path):
        from ..msx_rom import read_cartridge
        return read_cartridge(path)

    def default_video_mode(self, path: Path) -> str:
        return 'ntsc'

    def convert(self, path: Path, **options) -> Path:
        from ..msx_conversion import convert
        return convert(path, **options)


MSX = MsxProfile()

# The folder names that say MSX2 for a .rom (the libraries of the frontends name their folders so).
MSX2_FOLDERS = frozenset(('msx2', 'msx 2', 'msx-2'))


class Msx2Profile(MsxProfile):
    id = 'msx2'
    name = 'MSX2'
    extensions = ('.mx2',)
    archived_rom_limits = (('.mx2', 0x200000),)
    export_folder = 'MSX2'
    scope_note = ('MSX2 cartridges (plain, Konami, Konami SCC, ASCII 8 and ASCII 16 mappers) with C-BIOS or your own MSX2 '
                  'BIOS; the V9938 with all twelve commands, timing approximated; no disks or cassettes')
    # The player's own MSX2 BIOS is two files (the main ROM and its sub-ROM), optional together; the mapper RAM's size is
    # part of the request (the machine differs).
    firmware = ('bios', 'subrom')
    option_keys = (OptionKey('msx2_bios', signature=False, kind='path', label='msx2_bios_label'),
                   OptionKey('msx2_subrom', signature=False, kind='path', label='msx2_subrom_label'),
                   OptionKey('msx2_ram', kind='choice', label='msx2_ram_label', choices=(128, 256, 512), default=256))
    quick_state_family = 'msx2'
    feedback_kinds = frozenset({27})                     # RR_FB_MSX2, reserved as the MSX's
    path_spec = PathSpec(order=17, sections=(('z80', 'msx2'),),
                         source_bounds=(('rom', CARTRIDGE_BOUNDS), ('bios', (0x10000, 0x10000))),
                         required_sources=('rom',), hashed_sources=('rom', 'bios'),
                         shapes=(('z80', 'msx2', dict(roles=('rom', 'bios'), caps={'window4': 4096})),))
    catalogues = Catalogues(libretro='libretro-thumbnails/Microsoft_-_MSX2')
    library_layout = LibraryLayout(folder='msx2', summary_glob='*/compilation.json')
    # Claimed from the path, before the MSX1's content sniff: a .mx2, or a .rom / ZIP chosen as MSX2 or found in an msx2
    # folder, when its bytes hold an MSX cartridge header.
    identify = Identify(path_order=55)

    def identify_content(self, data: bytes):
        return None

    def identify_path(self, path: Path, suffix: str, selected_system: str | None):
        if suffix == '.mx2':
            from ..systems import ConsoleMismatchError
            if selected_system and selected_system != self.id:
                raise ConsoleMismatchError('Detected MSX2; choose Automatic or MSX2.', self.id)
            return self
        if suffix not in ('.rom', '.zip'):
            return None
        if selected_system != self.id and path.parent.name.casefold() not in MSX2_FOLDERS:
            return None
        if selected_system and selected_system != self.id:
            return None
        from ..msx_rom import read_cartridge
        try:
            cartridge = read_cartridge(path)
        except (OSError, ValueError):
            return None
        if suffix == '.zip' and cartridge.member.lower().endswith('.mx1'):
            return None                                   # a .mx1 is the MSX1's, whatever its folder
        return self

    def request_identity(self, item, options: dict, settings: dict) -> None:
        """The BIOS pair the machine boots (the player's own image, its SHA-256; or C-BIOS, its pin) and the mapper RAM."""
        from .. import msx_cbios
        from ..msx_conversion import own_bios2
        try:
            bios = own_bios2(options.get('msx2_bios'), options.get('msx2_subrom'))
        except (OSError, ValueError):
            bios = None
        settings['msx2_bios'] = bios[1] if bios is not None else 'cbios-' + msx_cbios.VERSION
        settings['msx2_ram'] = int(options.get('msx2_ram') or 256)

    def convert(self, path: Path, **options) -> Path:
        from ..msx_conversion import convert
        return convert(path, model='msx2', **options)


MSX2 = Msx2Profile()
