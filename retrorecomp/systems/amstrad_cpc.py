"""Amstrad CPC profile (from 21 November 2026; supported from 27 November 2026, on the owner's G14: see docs/AMSTRAD_CPC.md).

What it converts: a CPC 6128 disk game (a DSK or EXTENDED DSK image, or a ZIP holding one), started from BASIC by the
command its catalogue gives (retrorecomp/cpc_disk.py), on the CPC 6128's firmware: the 32 KiB system ROM (the OS and
Locomotive BASIC) and the 16 KiB AMSDOS ROM, the player's own (recognised by their public digests) or fetched from a pinned
source, never in the repository or the installer. The Z80 runs on the
shared banked Z80 chain of the Master System and the MSX, its time rounded to the Gate Array's microsecond; the Gate Array,
the CRTC 6845, the PPI 8255 with the keyboard and the uPD765 floppy controller are our own C (native/cpc_machine,
native/upd765), the AY-3-8912 the shared module of the MSX and the ZX Spectrum.

The profile identifies a CPC disk (its signature, before the MSX2+ which takes every other .dsk), and its conversion
(retrorecomp/cpc_conversion.py) runs the boot and play routes on the chain, in every installation. When the player gives no
firmware, the converter fetches the pinned files (retrorecomp/cpc_roms.py).
Not planned for this profile: tapes (.cdt), snapshots (.sna), the Plus range and the GX4000 (their ASIC, .cpr cartridges).
"""
from __future__ import annotations

from pathlib import Path

from . import Capabilities, ConsoleMismatchError, Cpu, OptionKey, SimulationSource, SystemProfile
from ..cpc_timing import z80_costs
from ..z80_chain import Z80Machine, Z80RegionMap
from .specs import Catalogues, Identify, LibraryLayout, PathSpec, ReportShape

# The CPC on the banked Z80 chain: four 16 KiB regions, each showing RAM, the system ROM (source 0: bank 0 the OS below 4000h,
# bank 1 BASIC at C000h) or AMSDOS (source 1, the upper ROM 7) as the Gate Array and the upper ROM number say; no M1 wait state
# of its own, every instruction in whole microseconds instead (retrorecomp/cpc_timing.py); /INT read once the machine has caught
# up with the instruction; the start of each step and the reference CPU's state copies from the chain; its own generator
# folders; the full 16-bit port (port_bits 16: the CPC decodes its devices from the high byte). The game's own code runs from
# RAM: learned with byte guards, kept as offsets in the disk.
CPC_MACHINE = Z80Machine('cpc', Z80RegionMap(region_bits=14, sources=('system', 'amsdos'), bank_values=2,
                                             scope='cpc-firmware-region-map'),
                         m1_wait=0, irq_sample='instruction_end', generator_tag='-cpc', step_begin=True,
                         reference_state=True, costs=z80_costs(), port_bits=16)

# A CPC disk image: the smallest one holds a single 256-byte disk block and one track; the largest a 3.5" drive's 84
# double-sided tracks (retrorecomp/cpc_disk.py, MAX_IMAGE).
DISK_BOUNDS = (512, 2 * 1024 * 1024)
# The player's firmware: the system ROM (OS + BASIC, 32 KiB) and AMSDOS (16 KiB).
SYSTEM_BOUNDS = (0x8000, 0x8000)
AMSDOS_BOUNDS = (0x4000, 0x4000)


class AmstradCpcProfile(SystemProfile):
    id = 'cpc'
    name = 'Amstrad CPC'
    extensions = ('.dsk',)
    export_folder = 'Amstrad CPC'
    video_modes = ('pal',)
    status = 'supported'
    linux = 'witnessed'
    scope_note = ('Amstrad CPC 6128 disk games (DSK and extended DSK images, or a ZIP holding one), on the 6128\'s firmware '
                  'fetched once from a pinned source or on your own system ROM and AMSDOS ROM')
    cpus = (Cpu('z80', 'main', 'cycles'),)
    media_kinds = ('disk',)
    # The player's own firmware, both needed (no free replacement exists): the 6128's system ROM and AMSDOS. Not part of the
    # request signature; the identity of the files used is (request_identity).
    firmware = ('system', 'amsdos')
    option_keys = (OptionKey('cpc_system', signature=False, kind='path', label='cpc_system_label'),
                   OptionKey('cpc_amsdos', signature=False, kind='path', label='cpc_amsdos_label'))
    capabilities = Capabilities(keyboard=True, disks=True)
    quick_state_family = 'cpc'
    # RR_FB_CPC in native/runtime_feedback.h, reserved with the other new machines' in one change (1.10.0). Nothing is recorded
    # under it yet: the game never starts the recorder, as on the MSX.
    feedback_kinds = frozenset({31})
    # Multiplayer (docs/HOST_KIT.md 2.5, the multiplayer checklist of 21 Nov 2026): rollback on the game's own snapshots, two seats
    # (joystick 1 on keyboard row 9, joystick 2 on row 6), the host typing for everyone, the host's disk A as the match's save.
    netplay_session = True
    netplay_seats = 2
    netplay_rollback = True
    z80_machine = CPC_MACHINE

    @staticmethod
    def z80_vector_tstates(trace) -> int:
        """The T-states of one instruction on a CPC from its Z80 bus trace (one 'rwmi' flag string per T-state): what
        tools/banked_vector_selftest.py expects of each vector, the CPC's bus rule applied to that vector alone, not the table."""
        from ..cpc_timing import cpc_nops
        return 4 * cpc_nops(trace)

    # The components its games are to compile: the banked Z80 chain's generator and core, and the reference interpreter of
    # the counted fallback (the MSX's three).
    notice_files = ('licenses/smsggrecomp.md', 'licenses/z80-recomp-core.md', 'licenses/superzazu-z80.md',
                    'licenses/amstrad-cpc-roms.md')
    # The chain's generated files (retrorecomp/simulation_identity.py); the machine's own loop file joins with it.
    simulation_sources = (SimulationSource('generated/game_banked_index.c'),
                          SimulationSource('generated/game_banked_ops_*.c'),
                          SimulationSource('generated/game_banked.h'))
    # What its game is built from beside its own files: the banked Z80 chain and its shared glue, the shared AY-3-8910 and the
    # box filter, the computer side of the host kit; the gates join with the conversion loop.
    stamp_groups = ('z80_main', 'z80_chain_glue', 'z80_chain_state', 'state_file', 'ay38910', 'audio_box', 'disk_copies', 'conversion_gates',
                    'hostkit_computer', 'hostkit_text')
    # The player shell is the host kit through the CPC's adapter (on rrhk_computer.inc, as the MSX's).
    host_adapter = 'adapters/rrhk_cpc.inc'
    # The RAM windows a conversion will learn, kept as offsets in the disk (the MSX2+ disks' mechanism); the firmware as the
    # second source.
    # order: the next free place in the schema's dense list (the ZX Spectrum took 20).
    path_spec = PathSpec(order=25, sections=(('z80', 'cpc'),),
                         source_bounds=(('disk', DISK_BOUNDS), ('system', SYSTEM_BOUNDS), ('amsdos', AMSDOS_BOUNDS)),
                         required_sources=('disk', 'system'), hashed_sources=('disk', 'system', 'amsdos'),
                         shapes=(('z80', 'cpc', dict(roles=('disk', 'system', 'amsdos'), caps={'window4': 4096})),))
    report_shape = ReportShape('cpc_conversion', 'cpc_checks')
    # Cover services' platforms: ScreenScraper 65 (« Amstrad : CPC » in its system list), TheGamesDB 4914, IGDB acpc (21 Nov 2026).
    catalogues = Catalogues(libretro='libretro-thumbnails/Amstrad_-_CPC', screenscraper=65, thegamesdb=4914, igdb='acpc')
    library_layout = LibraryLayout(folder='cpc', summary_glob='*/compilation.json')
    # A .dsk is the CPC's when it carries the CPCEMU signature ("MV - CPC" or "EXTENDED"), and a ZIP when its one .dsk does:
    # asked before the MSX2+, which takes every other .dsk (raw MSX images have no signature).
    identify = Identify(path_order=6)

    def identify_path(self, path: Path, suffix: str, selected_system: str | None):
        if suffix not in ('.dsk', '.zip'):
            return None
        from ..cpc_disk import looks_like_cpc
        if not looks_like_cpc(path):
            return None
        if selected_system and selected_system != self.id:
            if suffix == '.zip':
                return None             # a ZIP chosen for another machine is left to it
            raise ConsoleMismatchError('Detected an Amstrad CPC disk; choose Automatic or Amstrad CPC.', self.id)
        return self

    def read_rom(self, path: Path):
        from ..cpc_disk import read_disk
        return read_disk(path)

    def request_identity(self, item, options: dict, settings: dict) -> None:
        """The firmware the machine boots: the SHA-256 of each file the player gave."""
        import hashlib
        for key in ('cpc_system', 'cpc_amsdos'):
            if options.get(key):
                try:
                    settings[key] = hashlib.sha256(Path(options[key]).read_bytes()).hexdigest()
                except OSError:
                    pass

    def default_video_mode(self, path: Path) -> str:
        return 'pal'

    def convert(self, path: Path, **options) -> Path:
        """The conversion (retrorecomp/cpc_conversion.py)."""
        from ..cpc_conversion import convert
        return convert(path, **options)


AMSTRAD_CPC = AmstradCpcProfile()
