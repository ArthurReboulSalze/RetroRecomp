"""ZX Spectrum profile (experimental, in development: see docs/ZX_SPECTRUM.md).

Step 1, stage 1 of the machine: the profile, the snapshot reader, the ROM pin and the report writer exist; nothing converts.
The machine is a developer-only profile until it does (as the Game Boy Advance was): the window and the batch do not list
it, and a `.z80` or `.sna` file says so instead of being called an unknown console.

What it will convert: snapshots of the 16K, 48K and 128K (and the +2, a 128K with another menu ROM), `.z80` versions 1 to 3
and `.sna`, from a file or a ZIP holding one; on the shared banked Z80 chain the Master System and the MSX use, with the ULA,
the beeper, the 128K paging and the AY-3-8910 in our own C. Not yet: tapes, the +2A and +3, disks, the Interface 1.
"""
from __future__ import annotations

from pathlib import Path

from . import (Capabilities, ConsoleMismatchError, Cpu, OptionKey, SimulationSource, SystemProfile,
               UnsupportedConsoleError)
from ..z80_chain import Z80Machine, Z80RegionMap
from .specs import Catalogues, Identify, LibraryLayout, PathSpec, ReportShape

# The Spectrum on the banked Z80 chain: four 16 KiB regions, the ROM (16 KiB, or the 128K's two banks) as the one translated source
# at 0000h and RAM above (the snapshot's code runs from RAM: it is learned and translated with byte guards); no wait state (the
# ULA's contention is not modelled); /INT read once the machine has caught up with the instruction; 16-bit ports (the keyboard's
# half-rows, the 128K's paging and AY are decoded by the high byte); the registers are the snapshot's (not the reset values);
# its own generator folders.
ZXS_MACHINE = Z80Machine('zxs', Z80RegionMap(region_bits=14, sources=('rom',), bank_values=2, scope='zx-spectrum-rom-region-map'),
                         irq_sample='instruction_end', generator_tag='-zxs', step_begin=True, reference_state=True,
                         port_bits=16, reset_registers=False)

# The sources of a game: the snapshot (its RAM, where almost all the code lives) and the ROM (16 KiB on the 48K, the 128K's
# two banks as 32 KiB). A snapshot is 16 KiB of RAM plus a header at the least, 128 KiB plus headers at the most.
SNAPSHOT_BOUNDS = (0x401B, 0x30000)
ROM_BOUNDS = (0x4000, 0x8000)


class ZxSpectrumProfile(SystemProfile):
    id = 'zxs'
    name = 'ZX Spectrum'
    extensions = ('.z80', '.sna')
    archived_rom_limits = (('.z80', 0x30000), ('.sna', 0x30000))
    export_folder = 'ZX Spectrum'
    # The 48K runs 69,888 T-states a frame and the 128K 70,908, both close to 50 Hz: the machine had no 60 Hz model.
    video_modes = ('pal',)
    status = 'experimental'
    # The per-game generated files of the simulation identity (retrorecomp/simulation_identity.py): the translated code the
    # shared banked Z80 chain writes, as on the MSX; the machine's own files join them with its conversion.
    simulation_sources = (SimulationSource('generated/game_banked_index.c'), SimulationSource('generated/game_banked_ops_*.c'),
                          SimulationSource('generated/game_banked.h'), SimulationSource('zxs_banked_loop.inc'))
    linux = 'witnessed'
    scope_note = ('ZX Spectrum 16K, 48K and 128K snapshots (.z80, .sna), in development: identified, not converted yet; '
                  'no tapes, +2A, +3 or disks')
    # One processor; the ULA, the beeper and the AY-3-8910 are chips of our own C, not CPUs.
    cpus = (Cpu('z80', 'main', 'cycles'),)
    media_kinds = ('snapshot',)
    # The ROMs (Amstrad's, under its 1999 permission for emulators): fetched from a pinned source by default
    # (retrorecomp/zxs_roms.py); the player's own, checked by its SHA-256, when an option names one. Not part of the request
    # signature: the ROM image's identity is (request_identity).
    firmware = ('rom48', 'rom128')
    option_keys = (OptionKey('zxs_rom48', signature=False, kind='path', label='zxs_rom48_label'),
                   OptionKey('zxs_rom128', signature=False, kind='path', label='zxs_rom128_label'))
    capabilities = Capabilities(keyboard=True)
    quick_state_family = 'zxs'
    # The player's window on the host kit (a computer adapter, as the MSX's); no multiplayer hooks yet (step 3).
    host_adapter = 'adapters/rrhk_zxs.inc'
    # No runtime-feedback kind yet: nothing is recorded. The lead reserves the new machines' kinds in native/runtime_feedback.h in
    # one change (28 for this machine), with the release that first needs one, so that every machine's stamp moves once
    # (tests/test_machine_registry.py, DECLINED['feedback_kind']).
    feedback_kinds = frozenset()
    fallback_display = 'cycles'
    # The banked Z80 chain's generator and core, the counted fallback's reference interpreter, and the ROMs' permission notice
    # (every game holds a Spectrum ROM, the player's own or the pinned one).
    notice_files = ('licenses/smsggrecomp.md', 'licenses/z80-recomp-core.md', 'licenses/superzazu-z80.md',
                    'licenses/zx-spectrum-roms.md')
    developer_only = True
    # The shared groups its game is built from: the banked Z80 chain and its glue, the AY-3-8910 of the 128K (native/ay38910), the
    # computers' side of the host kit (rrhk_computer.inc, which its adapter includes).
    stamp_groups = ('z80_main', 'z80_chain_glue', 'ay38910', 'audio_box', 'z80_chain_state', 'state_file', 'hostkit_computer')
    z80_machine = ZXS_MACHINE
    path_spec = PathSpec(order=20, sections=(('z80', 'zxs'),),
                         source_bounds=(('snapshot', SNAPSHOT_BOUNDS), ('rom', ROM_BOUNDS)),
                         required_sources=('snapshot',), hashed_sources=('snapshot', 'rom'),
                         shapes=(('z80', 'zxs', dict(roles=('snapshot', 'rom'), caps={'window4': 4096})),))
    report_shape = ReportShape('zxs_conversion', 'zxs_checks')
    # ScreenScraper 76 and TheGamesDB 4913 read on their platform pages on 21 November 2026; IGDB's slug of the platform.
    catalogues = Catalogues(libretro='libretro-thumbnails/Sinclair_-_ZX_Spectrum', screenscraper=76, thegamesdb=4913, igdb='zxs')
    library_layout = LibraryLayout(folder='zxs', summary_glob='*/compilation.json')
    # A snapshot is claimed by its extension, or a ZIP by the one snapshot it holds (its names only), before the ZIP is opened.
    identify = Identify(path_order=65)

    def available(self) -> bool:
        from ..zxs_conversion import developer_available
        return developer_available()

    def identify_path(self, path: Path, suffix: str, selected_system: str | None):
        if suffix == '.zip':
            from ..zxs_snapshot import zip_holds_snapshot
            if not zip_holds_snapshot(path):
                return None
        elif suffix not in self.extensions:
            return None
        if not self.available():
            raise UnsupportedConsoleError('The experimental ZX Spectrum profile is unavailable in this installation.')
        if selected_system and selected_system != self.id:
            raise ConsoleMismatchError('Detected ZX Spectrum; choose Automatic or ZX Spectrum.', self.id)
        return self

    def read_rom(self, path: Path):
        from ..zxs_snapshot import read_snapshot
        return read_snapshot(path)

    def default_video_mode(self, path: Path) -> str:
        return 'pal'

    def convert(self, path: Path, **options) -> Path:
        from ..zxs_conversion import convert
        return convert(path, **options)

    def request_identity(self, item, options: dict, settings: dict) -> None:
        """The ROM image the snapshot's model runs on (its SHA-256: the player's own and the pinned one are equal)."""
        from ..zxs_roms import rom_identity
        from ..zxs_snapshot import read_snapshot
        try:
            model = read_snapshot(item.path).model
        except (OSError, ValueError):
            model = '48k'
        option = 'zxs_rom128' if model == '128k' else 'zxs_rom48'
        settings['zx_rom'] = rom_identity(options.get(option), model)
        settings.pop('zxs_rom48', None)
        settings.pop('zxs_rom128', None)


ZX_SPECTRUM = ZxSpectrumProfile()
