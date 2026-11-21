"""Sega SG-1000 profile (experimental, developer only, in development: see docs/SG1000.md).

Stages 1 to 3 of the machine: the profile recognises a cartridge (a .sg, or a .bin, .rom or ZIP chosen as SG-1000 or kept in a folder named
sg1000), reads it (2 KiB to 48 KiB, plain ROM), translates it, checks it against the reference interpreter and builds and delivers a game
executable (retrorecomp/sg1000_conversion.py; the player is native/sg1000_machine/sg1000_player.c on the host kit). What it is: the SG-1000 and SG-1000 II cartridges, translated ahead of time by the shared banked Z80 chain
(retrorecomp/z80_chain.py) on the machine's own description below (eight 8 KiB regions of the cartridge space, no wait state on the M1
cycle, /INT read at the end of each instruction, the /NMI pin of the Pause button), with the TMS9918A of native/tms9918 shared with the
MSX. Left out on purpose: the SC-3000 (keyboard, BASIC, cassette) and the peripherals and boards of docs/SG1000.md.
Measured per conversion, on the routes played only: the native share (the counted interpreter fallback) and the agreement with the reference
interpreter. Not measured: CPU fidelity against an independent oracle, hardware fidelity, gameplay validation, physical latency.
"""
from __future__ import annotations

from pathlib import Path

from . import Capabilities, Cpu, SimulationSource, SystemProfile
from ..z80_chain import Z80Machine, Z80RegionMap
from .specs import Catalogues, Identify, LibraryLayout, PathSpec, ReportShape

# The SG-1000 on the banked Z80 chain: eight 8 KiB regions, each showing the cartridge (source 0) or RAM; no wait state on the M1
# cycle; /INT read once the machine has caught up with the instruction; the /NMI pin (the Pause button); the start of each step and
# the reference CPU's state copies from the chain; its own generator folders. The region map is the cartridge space of 48 KiB; the
# cartridge RAM of The Castle (the one cartridge with its own RAM in the library studied) is a later stage's.
SG1000_MACHINE = Z80Machine('sg1000', Z80RegionMap(region_bits=13, sources=('cartridge',), bank_values=256,
                                                   scope='sg1000-cartridge-region-map'),
                            m1_wait=0, irq_sample='instruction_end', generator_tag='-sg', step_begin=True,
                            reference_state=True, nmi=True)

# 2 KiB to 48 KiB cartridges (the cartridge space 0000h-BFFFh, no bank switching).
CARTRIDGE_BOUNDS = (0x800, 0xC000)

# The folder names that say SG-1000 for a .bin, a .rom or a ZIP (the libraries of the frontends name their folders so).
SG1000_FOLDERS = frozenset(('sg1000', 'sg-1000', 'sg_1000'))


class Sg1000Profile(SystemProfile):
    id = 'sg1000'
    name = 'SG-1000'
    extensions = ('.sg',)
    archived_rom_limits = (('.sg', 0xC000),)
    export_folder = 'SG-1000'
    video_modes = ('ntsc', 'pal')
    status = 'experimental'
    # Stages 1 to 3: it identifies files and converts cartridges for developers. Offered by installations that carry its profile, as the X68000 is.
    developer_only = True
    linux = 'pending'
    scope_note = ('SG-1000 and SG-1000 II cartridges of 2 to 48 KiB, plain ROM only; in development, converts for developers only (no player is offered it yet, no game has been played); '
                  'no SC-3000 (keyboard, BASIC, cassette), no Othello Multivision, Terebi Oekaki, Dahjee or other peripherals or boards')
    # The machine has one processor; the sound chip and the video chip are chips of our own C, not CPUs.
    cpus = (Cpu('z80', 'main', 'cycles'),)
    media_kinds = ('cartridge',)
    capabilities = Capabilities()          # two pads and the Pause button: no keyboard, no mouse, no disk
    quick_state_family = 'sg1000'
    netplay_session = False                # stage 3 of the machine
    host_adapter = 'adapters/rrhk_sg1000.inc'
    # No record kind of its own yet (native/runtime_feedback.h): nothing is recorded for path sharing before the conversion exists.
    feedback_kinds = frozenset()
    # The third-party components its games will compile in (retrorecomp/notices.py; the player shell's are added): the banked Z80
    # chain's generator and core, the corrected reference interpreter of the counted fallback. No BIOS: nothing else.
    notice_files = ('licenses/smsggrecomp.md', 'licenses/z80-recomp-core.md', 'licenses/superzazu-z80.md')
    stamp_groups = ('z80_main', 'z80_chain_glue', 'tms9918', 'sn76489', 'audio_box', 'conversion_gates')
    # The per-game generated files of the simulation identity (retrorecomp/simulation_identity.py), below the build project: the
    # chain's generated sources, which every machine on the banked Z80 chain has. The machine's own loop and game header are added
    # with its conversion.
    simulation_sources = (SimulationSource('generated/game_banked_index.c'),
                          SimulationSource('generated/game_banked_ops_*.c'),
                          SimulationSource('generated/game_banked.h'),)
    z80_machine = SG1000_MACHINE
    path_spec = PathSpec(order=21, sections=(('z80', 'sg1000'),),
                         source_bounds=(('rom', CARTRIDGE_BOUNDS),),
                         required_sources=('rom',), hashed_sources=('rom',),
                         shapes=(('z80', 'sg1000', dict(roles=('rom',), caps={'window4': 4096})),))
    report_shape = ReportShape('sg1000_conversion', 'sg1000_checks')
    catalogues = Catalogues(libretro='libretro-thumbnails/Sega_-_SG-1000', screenscraper=109, thegamesdb=4949, igdb='sg1000')
    library_layout = LibraryLayout(folder='sg1000', summary_glob='*/compilation.json')
    # A .sg is the SG-1000's whatever its bytes (a cartridge has no header to look at); a .bin, .rom or ZIP only when the player chose
    # SG-1000 or it sits in a folder named sg1000. Asked last: it steals no file another machine recognises.
    identify = Identify(path_order=66)

    def identify_path(self, path: Path, suffix: str, selected_system: str | None):
        from ..sg1000_rom import read_cartridge
        if suffix == '.sg':
            if selected_system and selected_system != self.id:
                from ..systems import ConsoleMismatchError
                raise ConsoleMismatchError('Detected SG-1000; choose Automatic or SG-1000.', self.id)
            return self
        if suffix not in ('.bin', '.rom', '.zip'):
            return None
        if selected_system and selected_system != self.id:
            return None
        if suffix == '.zip':
            import zipfile
            try:                                          # names only, unless the ZIP is chosen or in an sg1000 folder
                with zipfile.ZipFile(path) as bundle:
                    names = [name.lower() for name in bundle.namelist()]
            except (OSError, zipfile.BadZipFile):
                return None
            if sum(name.endswith('.sg') for name in names) == 1 and not any(
                    name.endswith(('.bin', '.rom')) for name in names):
                return self                               # one .sg member: the SG-1000's, whatever the folder
        if selected_system != self.id and path.parent.name.casefold() not in SG1000_FOLDERS:
            return None
        try:
            read_cartridge(path)                          # the size, and one cartridge in a ZIP, checked
        except (OSError, ValueError):
            return None
        return self

    def read_rom(self, path: Path):
        from ..sg1000_rom import read_cartridge
        return read_cartridge(path)

    def default_video_mode(self, path: Path) -> str:
        return 'ntsc'

    def convert(self, path: Path, **options) -> Path:
        from ..sg1000_conversion import convert
        return convert(path, **options)


SG1000 = Sg1000Profile()
