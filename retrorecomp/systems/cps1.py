"""Capcom CPS-1 conversion profile: MAME/FBNeo romsets identified by CRC."""
from pathlib import Path
from . import Capabilities, Cpu, OptionKey, SystemProfile
from .specs import Catalogues, Identify, InputLayout, LibraryLayout, PathSpec, ReportShape, SharedKnowledge


class Cps1Profile(SystemProfile):
    id = 'cps1'
    name = 'Capcom CPS-1'
    extensions = ('.zip',)
    export_folder = 'CPS-1'
    video_modes = ('arcade',)
    # Left the experimental status in 1.6.6 on the owner's decision, with the evidence in docs/QUALIFICATION.md
    # (26 sets of the perimeter converted and validated, board model compared with MAME on picture, sound and input).
    status = 'supported'
    cpus = (Cpu('m68000', 'main', 'instructions'), Cpu('z80', 'sound', 'instructions'))
    media_kinds = ('romset',)
    quick_state_family = 'rr16'
    # The standard boards keep no non-volatile memory.
    capabilities = Capabilities()
    feedback_kinds = frozenset({14, 15, 16})
    # The QSound boards (CPS-1.5) need the player's own dump of the chip's internal ROM, like a BIOS; no other board does.
    option_keys = (OptionKey('qsound_rom', signature=False, kind='path', label='qsound_rom_label'),)
    fallback_display = 'opcodes'
    default_frames = 3600
    quick_frames = 2400
    title_from_romset = True
    linux = 'witnessed'
    # The paths schema lists CPS-1 (7) before the X68000 (8); the documents list them the other way round.
    path_spec = PathSpec(order=7, sections=(('m68k', 'cps1'), ('z80', 'cps1-sound')),
                         source_bounds=(('maincpu', (0x1000, 0x400000)), ('audiocpu', (0x8000, 0x100000))),
                         required_sources=('maincpu', 'audiocpu'), hashed_sources=('maincpu', 'audiocpu'),
                         shapes=(('m68k', 'cps1', dict(roles=('maincpu',), caps={'insn': 4096},
                                                       windows=((0xff0000, 0x1000000),), contained=True,
                                                       length=(2, 16), length_align=2, offset_align=2,
                                                       address_align=2)),
                                 ('z80', 'cps1-sound', dict(roles=('audiocpu',), caps={'insn_masked': 4096},
                                                            windows=((0xd000, 0xd800),), length=(4, 4),
                                                            guard='mask'))))
    report_shape = ReportShape('cps1_conversion', 'native_analysis')
    # No box-art repository was ever chosen for the arcade board; its own catalogue names the sets.
    catalogues = Catalogues(libretro='libretro-thumbnails/MAME', screenscraper=6, thegamesdb=23, local_catalogue='assets/cps1-catalogue.json')
    # The memory window has no reader for it yet.
    library_layout = LibraryLayout(folder='cps1')
    input_layout = InputLayout(('b1', 'b2', 'b3'), ('b4', 'b5', 'b6'), None, 720, script_format='cps1',
                               script_suffix='.inputs')
    # Still the experimental tier of the shared base (schema 3 only, no schema 1 form, no site builder); see docs/CPS1.md.
    shared_knowledge = SharedKnowledge('experimental', withdrawable=True, module='cps1_knowledge')
    host_adapter = 'adapters/rrhk_cps1.c'
    stamp_groups = ('megadrive_codegen', 'megadrive_z80', 'conversion_gates', 'neogeo_codegen', 'neogeo_build', 'musashi_fixes', 'm68000_state_rules')
    # A romset ZIP whose program ROMs are in the catalogue (by CRC, never by name), or any ZIP when chosen.
    identify = Identify(path_order=20)

    def identify_path(self, path: Path, suffix: str, selected_system: str | None):
        # Arcade romsets are recognised by their program ROM CRCs, never by name.
        if suffix != '.zip' or selected_system not in (None, self.id):
            return None
        from ..cps1 import looks_like_cps1_zip
        try:
            detected = selected_system == self.id or looks_like_cps1_zip(path)
        except ValueError:
            detected = False
        return self if detected else None

    def read_rom(self, path: Path):
        from ..cps1 import read_set
        return read_set(path)

    def default_video_mode(self, path: Path) -> str:
        return 'arcade'

    def cover_titles(self, path: Path) -> tuple[str, ...]:
        # The box is filed under MAME's description of the set: the catalogue title, then the parent's (artwork.profile_cover_titles).
        from ..cps1 import cover_titles
        return cover_titles(path)

    def convert(self, path: Path, **options) -> Path:
        from ..cps1_conversion import convert
        return convert(path, **options)

    def request_identity(self, item, options: dict, settings: dict) -> None:
        # a QSound set depends on the DSP ROM it was converted with; any other set does not
        from .. import cps1_qsound
        if cps1_qsound.path_needs_dsp_rom(item.path):
            try:
                settings['bios'] = cps1_qsound.validate_dsp_rom(options.get('qsound_rom'))
            except ValueError:
                pass          # the conversion itself refuses with the reason


CPS1 = Cps1Profile()
