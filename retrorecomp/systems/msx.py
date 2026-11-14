"""MSX and MSX2 profiles (experimental: see docs/MSX.md).

What it converts: an MSX1 cartridge (plain 8 KiB to 64 KiB, Konami, Konami SCC, ASCII 8 KiB or ASCII 16 KiB mapper, read from a
.rom, a .mx1 or a ZIP holding one), booted by C-BIOS 0.29a or by the player's own MSX BIOS. The cartridge and the BIOS are
translated ahead of time by the shared banked Z80 chain (retrorecomp/z80_chain.py) on the MSX's own machine description: a
region map of eight 8 KiB regions, the cartridge then the BIOS as sources, one wait state per M1 cycle, /INT read at the end of
each instruction. Code run from RAM is learned and translated with byte guards; what is left runs on the reference interpreter,
counted. The TMS9918A, the AY-3-8910, the Konami SCC, the PPI, the slots and the mappers are our own C (native/msx_machine).

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
                  'MSX2 cartridges are the MSX2 profile; no disks or cassettes yet')
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
    linux = 'witnessed'   # Nemesis (MSX1) and Metal Gear (MSX2) converted headless on a Debian 13 PC, 12 November 2026: same report fields as Windows, quick states pass; not played in a window there
    # Its kind in native/runtime_feedback.h (RR_FB_MSX), reserved: nothing is recorded for path sharing, which the MSX declines (docs/MSX.md, section 7).
    feedback_kinds = frozenset({26})
    # The third-party components compiled into its games (retrorecomp/notices.py; the player shell's are added): the banked
    # Z80 chain's generator and core, the corrected reference interpreter of the counted fallback; C-BIOS only in a game that
    # boots it (no MSX BIOS of the player's own).
    notice_files = ('licenses/smsggrecomp.md', 'licenses/z80-recomp-core.md', 'licenses/superzazu-z80.md')
    optional_notice_files = ('licenses/cbios.md',)
    stamp_groups = ('z80_main', 'hostkit_computer', 'conversion_gates')  # the gates: packed replay, liveness, quick states
    z80_machine = MSX_MACHINE
    path_spec = PathSpec(order=16, sections=(('z80', 'msx'),),
                         source_bounds=(('rom', CARTRIDGE_BOUNDS), ('bios', BIOS_BOUNDS)),
                         required_sources=('rom',), hashed_sources=('rom', 'bios'),
                         shapes=(('z80', 'msx', dict(roles=('rom', 'bios'), caps={'window4': 4096})),))
    report_shape = ReportShape('msx_conversion', 'msx_checks')
    catalogues = Catalogues(libretro='libretro-thumbnails/Microsoft_-_MSX', screenscraper=113, thegamesdb=4929)
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
                  'BIOS; the V9938 with all twelve commands, timing approximated; no disks or cassettes; the battery memory of the clock '
                  'is not kept between runs')
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
    catalogues = Catalogues(libretro='libretro-thumbnails/Microsoft_-_MSX2', screenscraper=116, thegamesdb=4929)
    library_layout = LibraryLayout(folder='msx2', summary_glob='*/compilation.json')
    # Claimed from the path, before the MSX1's content sniff: a .mx2, or a .rom / ZIP chosen as MSX2 or found in an msx2
    # folder, when its bytes hold an MSX cartridge header.
    identify = Identify(path_order=55)

    def identify_content(self, data: bytes):
        return None

    def identify_path(self, path: Path, suffix: str, selected_system: str | None):
        # Reached when the MSX2+ (identified first) left the file: a .mx2 or ZIP in an msx2 folder, or MSX2 chosen.
        if suffix == '.mx2':
            from ..systems import ConsoleMismatchError
            if selected_system and selected_system not in (self.id, 'msx2plus'):
                raise ConsoleMismatchError('Detected MSX2; choose Automatic, MSX2 or MSX2+.', self.id)
            _decided(path, 'chosen in the menu' if selected_system == self.id else 'msx2 folder')
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
        _decided(path, 'chosen in the menu' if selected_system == self.id else 'msx2 folder')
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


# The folder names that say MSX2+ for a .rom or a ZIP.
MSX2PLUS_FOLDERS = frozenset(('msx2+', 'msx2plus', 'msx2p', 'msx 2+', 'msx2 plus', 'msx-2+'))
# Which hint decided between the MSX2 and the MSX2+ for each file identified in this process (the conversion logs it).
DECIDED: dict[str, str] = {}


def _decided(path: Path, hint: str) -> None:
    DECIDED[str(Path(path).resolve())] = hint


def decided(path: Path) -> str | None:
    """The hint that sent this file to the MSX2 or the MSX2+ ('msx2+ folder', 'chosen in the menu', ...), None if unknown."""
    return DECIDED.get(str(Path(path).resolve()))


class Msx2PlusProfile(Msx2Profile):
    """The MSX2+ (experimental since 1.7.4): the MSX2's board with the V9958 (YJK and YAE modes, the horizontal scroll) and the
    port F4h, booted by C-BIOS 0.29a's MSX2+ images or by the player's own MSX2+ BIOS pair. Cartridges, and disk games with the
    player's own BIOS pair and disk ROM; MSX-MUSIC and the kanji ROM are not converted yet (docs/MSX.md)."""
    id = 'msx2plus'
    name = 'MSX2+'
    # A .mx2 with no other hint and a .rom or ZIP chosen or in an msx2+ folder (identify_path below); a .dsk, or an M3U of
    # them (rom_sources.disk_sets groups "(Disk n of m)" files into one, marked with this machine).
    extensions = ('.mx2', '.dsk')
    archived_rom_limits = (('.mx2', 0x200000),)
    disk_set = (('.dsk',), 'msx2plus-sets')
    # The MSX2's catalogues (there is no MSX2+ folder in libretro-thumbnails), with the reviewed references of
    # assets/cover-references.json for the titles they name otherwise.
    catalogues = Catalogues(libretro='libretro-thumbnails/Microsoft_-_MSX2', screenscraper=116, thegamesdb=4929,
                            cover_references=True)
    media_kinds = ('cartridge', 'disk')
    export_folder = 'MSX2+'
    scope_note = ('MSX2+ cartridges (plain, Konami, Konami SCC, ASCII 8 and ASCII 16 mappers) with C-BIOS or your own MSX2+ '
                  'BIOS; the V9958 with YJK and the horizontal scroll; disk games with your own BIOS and disk ROM; no MSX-MUSIC '
                  'or kanji yet')
    option_keys = (OptionKey('msx2plus_bios', signature=False, kind='path', label='msx2plus_bios_label'),
                   OptionKey('msx2plus_subrom', signature=False, kind='path', label='msx2plus_subrom_label'),
                   OptionKey('msx2plus_ram', kind='choice', label='msx2plus_ram_label', choices=(128, 256, 512), default=256),
                   OptionKey('msx2plus_diskrom', signature=False, kind='path', label='msx2plus_diskrom_label'))
    quick_state_family = 'msx2plus'
    feedback_kinds = frozenset({27})       # RR_FB_MSX2, shared as the Master System and Game Gear share theirs: one record format
    path_spec = PathSpec(order=18, sections=(('z80', 'msx2plus'),),
                         source_bounds=(('rom', CARTRIDGE_BOUNDS), ('bios', (0x10000, 0x14000))),
                         required_sources=('rom',), hashed_sources=('rom', 'bios'),
                         shapes=(('z80', 'msx2plus', dict(roles=('rom', 'bios'), caps={'window4': 4096})),))
    library_layout = LibraryLayout(folder='msx2plus', summary_glob='*/compilation.json')
    identify = Identify(path_order=7)        # before the X68000, which takes every other M3U

    def identify_path(self, path: Path, suffix: str, selected_system: str | None):
        """MSX2 or MSX2+ (Arthur, 13 November 2026). A file in an msx2 folder, or with MSX2 chosen, is left to the MSX2; one in an
        msx2+ folder, or with MSX2+ chosen, is the MSX2+'s; a file known to be at least MSX2 with nothing saying which (a .mx2,
        or a ZIP holding one, outside those folders) is the MSX2+'s, which runs nearly every MSX2 game while the reverse is
        false. A plain .rom with no hint is not taken: it goes where it went before (the MSX1's content check)."""
        if suffix in ('.m3u', '.dsk'):
            if suffix == '.m3u':
                from ..rom_sources import playlist_owner
                if playlist_owner(path) != self.id:
                    return None                    # the X68000's, or nobody's: left to the next profile
            if selected_system and selected_system != self.id:
                from ..systems import ConsoleMismatchError
                raise ConsoleMismatchError('Detected MSX2+ disks; choose Automatic or MSX2+.', self.id)
            _decided(path, 'chosen in the menu' if selected_system == self.id else
                     'disk set' if suffix == '.m3u' else 'disk image')
            return self
        if selected_system and selected_system != self.id:
            return None
        folder = path.parent.name.casefold()
        chosen = selected_system == self.id
        if not chosen and folder in MSX2_FOLDERS:
            return None
        if suffix == '.mx2':
            _decided(path, 'chosen in the menu' if chosen else 'msx2+ folder' if folder in MSX2PLUS_FOLDERS
                     else 'in doubt between MSX2 and MSX2+: MSX2+')
            return self
        if suffix not in ('.rom', '.zip'):
            return None
        if not chosen and folder not in MSX2PLUS_FOLDERS:
            if suffix != '.zip':
                return None
            import zipfile
            try:                                          # names only: a ZIP of another machine is never read here
                with zipfile.ZipFile(path) as bundle:
                    if not any(name.lower().endswith('.mx2') for name in bundle.namelist()):
                        return None
            except (OSError, zipfile.BadZipFile):
                return None
        from ..msx_rom import read_cartridge
        try:
            cartridge = read_cartridge(path)             # the MSX cartridge header, checked
        except (OSError, ValueError):
            return None
        member = cartridge.member.lower() if suffix == '.zip' else ''
        if member.endswith('.mx1'):
            return None                                   # a .mx1 is the MSX1's, whatever its folder
        if chosen or folder in MSX2PLUS_FOLDERS:
            _decided(path, 'chosen in the menu' if chosen else 'msx2+ folder')
            return self
        if member.endswith('.mx2'):
            _decided(path, 'in doubt between MSX2 and MSX2+: MSX2+')
            return self
        return None                                       # a ZIP with no hint: left as before

    def read_rom(self, path: Path):
        if path.suffix.casefold() in ('.dsk', '.m3u'):
            from ..msx_disk import read_disks
            return read_disks(path)
        return super().read_rom(path)

    def request_identity(self, item, options: dict, settings: dict) -> None:
        """The BIOS pair the machine boots (the player's own MSX2+ image, its SHA-256; or C-BIOS, its pin) and the mapper RAM."""
        from .. import msx_cbios
        from ..msx_conversion import own_bios2
        try:
            bios = own_bios2(options.get('msx2plus_bios'), options.get('msx2plus_subrom'), 2)
        except (OSError, ValueError):
            bios = None
        settings['msx2plus_bios'] = bios[1] if bios is not None else 'cbios-' + msx_cbios.VERSION
        settings['msx2plus_ram'] = int(options.get('msx2plus_ram') or 256)
        if options.get('msx2plus_diskrom'):
            import hashlib
            try:
                settings['msx2plus_diskrom'] = hashlib.sha256(Path(options['msx2plus_diskrom']).read_bytes()).hexdigest()
            except OSError:
                pass

    def convert(self, path: Path, **options) -> Path:
        from ..msx_conversion import convert
        options['msx2_bios'] = options.pop('msx2plus_bios', None)
        options['msx2_subrom'] = options.pop('msx2plus_subrom', None)
        options['msx2_ram'] = options.pop('msx2plus_ram', None) or 256
        options['msx2_diskrom'] = options.pop('msx2plus_diskrom', None)
        return convert(path, model='msx2plus', **options)


MSX2PLUS = Msx2PlusProfile()
