"""Neo Geo conversion profile with explicitly selected, verified firmware."""
from pathlib import Path
from . import Capabilities, Cpu, OptionKey, SystemProfile


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
    option_keys = (OptionKey('ng_bios', signature=False), OptionKey('ng_qualification_routes'),
                   OptionKey('ng_parallel_games', signature=False))
    parallel_games_option = 'ng_parallel_games'

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
