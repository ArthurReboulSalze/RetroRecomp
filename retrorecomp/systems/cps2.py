"""Capcom CPS-2 conversion profile (experimental: see docs/CPS2.md).

The board is the CPS-1's with an encrypted 68000 program, an object chip of its own, raster interrupts and the QSound sound board, so
the profile reuses the CPS-1 pipeline (`cps1_conversion` with its `family='cps2'`), the common host kit adapter and the shared path
shapes. The key of a set is a file of the player's own romset; the QSound DSP ROM is the player's own dump, as for the CPS-1.5.
"""
from pathlib import Path
from . import Capabilities, Cpu, OptionKey, SystemProfile
from .specs import Catalogues, Identify, InputLayout, LibraryLayout, PathSpec, ReportShape


class Cps2Profile(SystemProfile):
    id = 'cps2'
    name = 'Capcom CPS-2'
    extensions = ('.zip',)
    export_folder = 'CPS-2'
    video_modes = ('arcade',)
    status = 'experimental'
    cpus = (Cpu('m68000', 'main', 'instructions'), Cpu('z80', 'sound', 'instructions'))
    media_kinds = ('romset',)
    quick_state_family = 'rr16'
    # The 93C46 EEPROM keeps the board's settings and the high scores: a save file per romset, as the QSound boards of the CPS-1.
    capabilities = Capabilities()
    # The record kinds of the CPS-1 (14 to 16: ROM, RAM and Z80 code left interpreted) shifted by three: `FB_KIND` in native/cps1_machine.c.
    feedback_kinds = frozenset({17, 18, 19})
    # Every CPS-2 board carries the QSound chip (or its own sound for the few boards without it, out of the first scope).
    option_keys = (OptionKey('qsound_rom', signature=False, kind='path', label='qsound_rom_label'),)
    fallback_display = 'opcodes'
    default_frames = 3600
    quick_frames = 2400
    title_from_romset = True
    # Not converted or played on Linux yet.
    linux = 'pending'
    # Open to players as an experimental machine in 1.6.9 (the owner's decision of 5 November 2026); supported in a later release.
    # The paths schema lists it after the X68000; its sources are the decrypted program (the image the code is translated from) and the
    # sound program. Nothing is shared with other players yet: the machine is not in the shared base.
    path_spec = PathSpec(order=9, sections=(('m68k', 'cps2'), ('z80', 'cps2-sound')),
                         source_bounds=(('maincpu', (0x1000, 0x400000)), ('audiocpu', (0x8000, 0x100000))),
                         required_sources=('maincpu', 'audiocpu'), hashed_sources=('maincpu', 'audiocpu'),
                         shapes=(('m68k', 'cps2', dict(roles=('maincpu',), caps={'insn': 4096},
                                                       windows=((0xff0000, 0x1000000),), contained=True,
                                                       length=(2, 16), length_align=2, offset_align=2,
                                                       address_align=2)),
                                 ('z80', 'cps2-sound', dict(roles=('audiocpu',), caps={'insn_masked': 4096},
                                                            windows=((0xd000, 0xd800),), length=(4, 4),
                                                            guard='mask'))))
    report_shape = ReportShape('cps1_conversion', 'native_analysis')
    catalogues = Catalogues(local_catalogue='assets/cps2-catalogue.json')
    library_layout = LibraryLayout(folder='cps2')
    input_layout = InputLayout(('b1', 'b2', 'b3'), ('b4', 'b5', 'b6'), None, 720, script_format='cps1',
                               script_suffix='.inputs')
    host_adapter = 'adapters/rrhk_cps1.c'
    stamp_groups = ('megadrive_codegen', 'megadrive_z80', 'conversion_gates', 'neogeo_codegen', 'neogeo_build', 'musashi_fixes', 'm68000_state_rules')
    # A romset ZIP whose program ROMs are in the CPS-2 catalogue (by CRC, never by name), or any ZIP when chosen.
    identify = Identify(path_order=25)

    def identify_path(self, path: Path, suffix: str, selected_system: str | None):
        if suffix != '.zip' or selected_system not in (None, self.id):
            return None
        from ..cps2 import looks_like_cps2_zip
        try:
            detected = selected_system == self.id or looks_like_cps2_zip(path)
        except ValueError:
            detected = False
        return self if detected else None

    def read_rom(self, path: Path):
        from ..cps2 import read_set
        return read_set(path)

    def default_video_mode(self, path: Path) -> str:
        return 'arcade'

    def convert(self, path: Path, **options) -> Path:
        from ..cps1_conversion import convert
        return convert(path, family='cps2', **options)

    def request_identity(self, item, options: dict, settings: dict) -> None:
        # every CPS-2 set depends on the DSP ROM it was converted with
        from .. import cps1_qsound
        try:
            settings['bios'] = cps1_qsound.validate_dsp_rom(options.get('qsound_rom'))
        except ValueError:
            pass          # the conversion itself refuses with the reason


CPS2 = Cps2Profile()
