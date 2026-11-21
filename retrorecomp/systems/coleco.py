"""ColecoVision profile (experimental, developer only, in development: see docs/COLECOVISION.md).

Stages 1 to 3 of the machine: the profile recognises a cartridge (a .col, or a .bin, .rom or ZIP chosen as ColecoVision or kept in a folder
named colecovision, beginning with a header word), reads it (4 KiB to 32 KiB, plain ROM), takes the one firmware option, the player's own
BIOS, translates both, checks them against the reference interpreter and builds and delivers a game executable
(retrorecomp/coleco_conversion.py; the player is native/coleco_machine/coleco_player.c on the host kit). What it is: the ColecoVision (NTSC) with two standard controllers, translated ahead of time by the shared banked
Z80 chain (retrorecomp/z80_chain.py) on the machine's own description below (eight 8 KiB regions: the BIOS, the console's RAM, the
cartridge window; no wait state on the M1 cycle; the TMS9928A's frame interrupt wired to /NMI), with the TMS9918A of native/tms9918
and the SN76489A of native/sn76489 shared with the MSX and the SG-1000. The BIOS is the player's own (retrorecomp/coleco_bios.py): the
converted game holds it translated, for its owner only. Left out on purpose: the Super Action Controller, the roller and driving
modules, the Super Game Module, the MegaCart and other homebrew boards, the ADAM.
Measured per conversion, on the routes played only: the native share (the counted interpreter fallback) and the agreement with the
reference interpreter. Not measured: CPU fidelity against an independent oracle, hardware fidelity, gameplay validation, physical latency.
"""
from __future__ import annotations

from pathlib import Path

from . import Capabilities, Cpu, OptionKey, SimulationSource, SystemProfile
from ..z80_chain import Z80Machine, Z80RegionMap
from .specs import Catalogues, Identify, LibraryLayout, PathSpec, ReportShape

# The ColecoVision on the banked Z80 chain: eight 8 KiB regions, each showing a source or RAM. Source 0 is the cartridge (the last four
# regions, 8000h-FFFFh), source 1 the BIOS (the first region, 0000h-1FFFh); the console's 1 KiB of RAM (6000h, mirrored through
# 7FFFh) and the expansion port (2000h-5FFFh, nothing there: reads give FFh) are regions the machine's bus answers. No wait state on
# the M1 cycle; /INT is not wired (the VDP's interrupt is /NMI, an edge the machine raises); the start of each step and the
# reference CPU's state copies from the chain; its own generator folders.
COLECO_MACHINE = Z80Machine('coleco', Z80RegionMap(region_bits=13, sources=('cartridge', 'bios'), bank_values=256,
                                                   scope='coleco-cartridge-region-map'),
                            m1_wait=0, irq_sample='instruction_end', generator_tag='-cv', step_begin=True,
                            reference_state=True, nmi=True)

# 4 KiB to 32 KiB cartridges (the window 8000h-FFFFh, no bank switching); the BIOS: 8 KiB.
CARTRIDGE_BOUNDS = (0x1000, 0x8000)
BIOS_BOUNDS = (0x2000, 0x2000)

# The folder names that say ColecoVision for a .bin, a .rom or a ZIP (the libraries of the frontends name their folders so).
COLECO_FOLDERS = frozenset(('colecovision', 'coleco', 'coleco vision', 'coleco_vision'))


class ColecoProfile(SystemProfile):
    id = 'coleco'
    name = 'ColecoVision'
    extensions = ('.col',)
    archived_rom_limits = (('.col', 0x8000),)
    export_folder = 'ColecoVision'
    video_modes = ('ntsc', 'pal')
    status = 'experimental'
    # Stages 1 to 3: it identifies files and converts cartridges for developers. Offered by installations that carry its profile, as the X68000 is.
    developer_only = True
    linux = 'pending'
    scope_note = ('ColecoVision cartridges of 4 to 32 KiB, plain ROM only, with your own BIOS (never shipped); in development, converts for developers only (no player is offered it yet, no game has been played); '
                  'two standard controllers with their keypads; no Super Action Controller, roller or driving module, Super Game Module, MegaCart or other boards, no ADAM')
    # The machine has one processor; the sound chip and the video chip are chips of our own C, not CPUs.
    cpus = (Cpu('z80', 'main', 'cycles'),)
    media_kinds = ('cartridge',)
    capabilities = Capabilities()          # two controllers (stick, two fire buttons, a keypad): no Pause button, no keyboard, no mouse, no disk
    quick_state_family = 'coleco'
    netplay_session = False                # a later step of the machine
    host_adapter = 'adapters/rrhk_coleco.inc'
    # No record kind of its own yet (native/runtime_feedback.h): nothing is recorded for path sharing before the conversion exists.
    feedback_kinds = frozenset()
    # The third-party components its games will compile in (retrorecomp/notices.py; the player shell's are added): the banked Z80
    # chain's generator and core, the corrected reference interpreter of the counted fallback. The BIOS is the player's own: no notice.
    notice_files = ('licenses/smsggrecomp.md', 'licenses/z80-recomp-core.md', 'licenses/superzazu-z80.md')
    stamp_groups = ('z80_main', 'z80_chain_glue', 'tms9918', 'sn76489', 'audio_box', 'z80_chain_state', 'state_file', 'hostkit_keypad', 'conversion_gates')
    firmware = ('bios',)
    option_keys = (OptionKey('coleco_bios', signature=False, kind='path', label='coleco_bios_label'),)
    # The per-game generated files of the simulation identity (retrorecomp/simulation_identity.py), below the build project: the
    # chain's generated sources, which every machine on the banked Z80 chain has. The machine's own loop and game header are added
    # with its conversion.
    simulation_sources = (SimulationSource('generated/game_banked_index.c'),
                          SimulationSource('generated/game_banked_ops_*.c'),
                          SimulationSource('generated/game_banked.h'),)
    z80_machine = COLECO_MACHINE
    path_spec = PathSpec(order=24, sections=(('z80', 'coleco'),),
                         source_bounds=(('rom', CARTRIDGE_BOUNDS), ('bios', BIOS_BOUNDS)),
                         required_sources=('rom',), hashed_sources=('rom', 'bios'),
                         shapes=(('z80', 'coleco', dict(roles=('rom', 'bios'), caps={'window4': 4096})),))
    report_shape = ReportShape('coleco_conversion', 'coleco_checks')
    catalogues = Catalogues(libretro='libretro-thumbnails/Coleco_-_ColecoVision', screenscraper=48, thegamesdb=31, igdb='colecovision')
    library_layout = LibraryLayout(folder='coleco', summary_glob='*/compilation.json')
    # A .col is the ColecoVision's whatever its bytes; a .bin, .rom or ZIP only when the player chose ColecoVision or it sits in a
    # folder named colecovision, and only if it begins with a header word. Asked last: it steals no file another machine recognises.
    identify = Identify(path_order=67)

    def identify_path(self, path: Path, suffix: str, selected_system: str | None):
        from ..coleco_rom import read_cartridge
        if suffix == '.col':
            if selected_system and selected_system != self.id:
                from ..systems import ConsoleMismatchError
                raise ConsoleMismatchError('Detected ColecoVision; choose Automatic or ColecoVision.', self.id)
            return self
        if suffix not in ('.bin', '.rom', '.zip'):
            return None
        if selected_system and selected_system != self.id:
            return None
        if suffix == '.zip':
            import zipfile
            try:                                          # names only, unless the ZIP is chosen or in a colecovision folder
                with zipfile.ZipFile(path) as bundle:
                    names = [name.lower() for name in bundle.namelist()]
            except (OSError, zipfile.BadZipFile):
                return None
            if sum(name.endswith('.col') for name in names) == 1 and not any(
                    name.endswith(('.bin', '.rom')) for name in names):
                return self                               # one .col member: the ColecoVision's, whatever the folder
        if selected_system != self.id and path.parent.name.casefold() not in COLECO_FOLDERS:
            return None
        try:
            read_cartridge(path, require_header=True)     # the size, one cartridge in a ZIP, and the header word, checked
        except (OSError, ValueError):
            return None
        return self

    def request_identity(self, item, options: dict, settings: dict) -> None:
        """The BIOS the machine boots is part of the request: the player's own image (its SHA-256), 'missing' when there is none."""
        from ..coleco_bios import bios_identity
        settings['coleco_bios'] = bios_identity(options.get('coleco_bios'))

    def read_rom(self, path: Path):
        from ..coleco_rom import read_cartridge
        return read_cartridge(path)

    def default_video_mode(self, path: Path) -> str:
        return 'ntsc'

    def convert(self, path: Path, **options) -> Path:
        from ..coleco_conversion import convert
        return convert(path, **options)


COLECO = ColecoProfile()
