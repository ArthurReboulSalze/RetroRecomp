"""Neo Geo conversion profile with explicitly selected, verified firmware."""
from pathlib import Path
from . import Capabilities, ConsoleMismatchError, Cpu, OptionKey, SystemProfile
from .specs import Catalogues, Identify, InputLayout, LibraryLayout, PathSpec, ReportShape, SharedKnowledge


class NeoGeoProfile(SystemProfile):
    id = 'ng'
    name = 'Neo Geo'
    extensions = ('.neo',)
    export_folder = 'Neo Geo'
    video_modes = ('mvs',)
    # Supported cartridge scope; reference agreement is not universal fidelity.
    status = 'supported'
    cpus = (Cpu('m68000', 'main', 'instructions'), Cpu('z80', 'sound', 'instructions'))
    media_kinds = ('cartridge', 'romset')
    firmware = ('bios',)
    quick_state_family = 'rr16'
    capabilities = Capabilities(battery=True)
    feedback_kinds = frozenset({10, 11, 12})
    fallback_display = 'opcodes'
    # A ZIP set has no key in the banks until a conversion prepared its cartridge.
    knowledge_identity_after_conversion = True
    default_frames = 3600
    quick_frames = 3600
    title_from_romset = True
    # ng_bios names the firmware, whose verified identity enters the request
    # (request_identity); ng_parallel_games only sizes the conversion.
    option_keys = (OptionKey('ng_bios', signature=False, kind='path', label='ng_bios_label'),
                   OptionKey('ng_qualification_routes', kind='plan'),
                   OptionKey('ng_parallel_games', signature=False, kind='count', default=1))
    parallel_games_option = 'ng_parallel_games'
    path_spec = PathSpec(
        order=6, sections=(('m68k', 'ng'), ('z80', 'ng-sound')),
        source_bounds=(('cart', (4096, 512 << 20)), ('p', (512, 16 << 20)), ('bios', (0x20000, 0x20000)),
                       ('m1', (0x10000, 512 << 10)), ('sm1', (0x20000, 0x20000))),
        required_sources=('cart', 'p', 'bios', 'm1', 'sm1'), hashed_sources=('cart', 'bios'),
        shapes=(('m68k', 'ng', dict(roles=('p', 'bios'), caps={'phys': 262144, 'phys_deltas': 2, 'insn': 4096},
                                    entry_align=2, entry_tail=2, windows=((0x100000, 0x110000),), contained=True,
                                    address_base=0x100000, length=(2, 16), length_align=2, offset_align=2,
                                    address_align=2)),
                ('z80', 'ng-sound', dict(roles=('m1', 'sm1'), caps={'insn_masked': 32768},
                                         windows=((0xf800, 0x10000),), length=(4, 4), guard='mask'))))
    report_shape = ReportShape('neogeo_conversion', 'prepared_cartridge')
    catalogues = Catalogues(libretro='libretro-thumbnails/SNK_-_Neo_Geo',
                            wikidata=('Q1054350', 'Q3338058', 'Q64428080'), cover_references=True,
                            local_catalogue='assets/neogeo-catalogue.json')
    library_layout = LibraryLayout(folder='ng', summary_glob='*/compilation.json')
    input_layout = InputLayout(('a', 'b', 'c', 'd'), (), None, 2400, script_format='neogeo',
                               script_suffix='.inputs')
    shared_knowledge = SharedKnowledge('stable')
    host_adapter = 'adapters/rrhk_ng.c'
    stamp_groups = ('conversion_gates', 'neogeo_codegen', 'neogeo_build', 'neogeo_native')
    # A .neo container, or a ZIP whose members are named like a cartridge set (program, sprites, sound).
    identify = Identify(path_order=30)

    def identify_path(self, path: Path, suffix: str, selected_system: str | None):
        if suffix not in ('.neo', '.zip'):
            return None
        from ..neogeo import looks_like_neogeo_zip, parse_neo
        detected = suffix == '.neo' or selected_system == self.id or looks_like_neogeo_zip(path)
        if not detected:
            return None
        if suffix == '.neo': parse_neo(path)
        if selected_system and selected_system != self.id:
            raise ConsoleMismatchError('Detected Neo Geo; choose Automatic or Neo Geo.', self.id)
        return self

    def read_rom(self, path: Path):
        from ..neogeo import read_set
        return read_set(path)

    def default_video_mode(self, path: Path) -> str:
        return 'mvs'

    def convert(self, path: Path, **options) -> Path:
        from ..neogeo_conversion import convert
        return convert(path, **options)

    def request_identity(self, item, options: dict, settings: dict) -> None:
        from ..neogeo import validate_bios
        from ..paths import selected_bios_path
        settings['bios'] = validate_bios(selected_bios_path(options.get('ng_bios') or options.get('bios')))

    def knowledge_identity(self, item, settings: dict) -> str:
        # key(prepared cartridge, BIOS): a ZIP set not prepared yet has none, and so no record.
        from ..neogeo_knowledge import shared_identity
        bios = settings.get('bios')
        sha = bios.get('sha256') if isinstance(bios, dict) else None
        return (shared_identity(item.path, item.sha256, sha) if sha else None) or item.sha256


NEOGEO = NeoGeoProfile()
