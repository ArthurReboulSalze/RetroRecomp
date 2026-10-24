"""Content fingerprints of the inputs used by one console's exported games.

Unknown source files remain shared dependencies. Only known interface modules
and other consoles are excluded; a new backend helper therefore fails closed.
The application version is presentation metadata, not a runtime ABI version.
"""
import hashlib
import importlib.util
import json
import os
import pkgutil
from pathlib import Path
from types import CodeType
from functools import lru_cache

SYSTEMS = frozenset(('sms', 'gg', 'gb', 'nes', 'md', 'snes', 'ng', 'x68', 'cps1'))
INTERFACE_MODULES = frozenset(('__init__', 'gui', 'i18n', 'ui_fonts', 'tooltips',
                               'dropfiles', 'updater', 'linux_desktop', 'queue_state',
                               'credits_demo', 'credits_music', 'dialogs',
                               'compiled_games', 'compiled_games_view', 'memory_view',
                               'game_details','game_metadata','game_card_view','rom_sources',
                               # Sharing discoveries never runs during a conversion.
                               'knowledge_build','knowledge_exchange','online'))


# Host (the player shell) versus game: see docs/UPGRADES.md. Host inputs draw
# the window, menus, options, bindings, on-screen text, fonts, filters, icons
# and notices, play sound out, and save preferences. The headless runs that
# discover and validate a game's code never use them; those go through each
# console's entry (launcher, main, runner), which stays on the game side. A
# change limited to host inputs upgrades an export without rediscovery.
# Everything not listed is game-side, so an unclassified input fails closed.
HOST_MODULES = frozenset((
    # Embedded artwork, box icons and Windows executable information.
    'artwork', 'cover_keyring', 'cover_references', 'cover_settings', 'cover_sources',
    'cover_titles', 'metadata', 'languages',
    # Placing the finished EXE beside the others.
    'publishing', 'windows',
    # Converter-only shells.
    'branding', 'player_gamepad',
    # Player shells written as patches: Game Boy platform window, menus,
    # sound output and input; Mega Drive sound delivery.
    'gameboy_host', 'gameboy_timing', 'megadrive_audio'))
HOST_NATIVE = frozenset((
    # Paths below native/. Shared menu core, identical on every machine.
    'retro_menu.c', 'retro_menu.h', 'game_options.h', 'game_options_checks.c',
    'autofire.h', 'retro_keyboard.h',
    # On-screen text and fonts.
    'runtime_catalog.inc', 'runtime_i18n.h', 'language_checks.c', 'font6x10.h', 'font10x20.h',
    # Presentation filters, display settings and the window icon.
    'scale2x.h', 'scanlines.h', 'scanline_sdl.h', 'xbr_filter.h', 'xbr_sdl.h', 'xbr_checks.c',
    'display_settings.h', 'display_settings_checks.c', 'icon.c', 'icon.h', 'icon_checks.c',
    # Sound output after each machine's emulated mixer.
    'audio_filter.h', 'audio_cushion.h', 'audio_output.inc', 'audio_checks.c',
    'gb_audio_output.inc', 'nes_audio_output.inc', 'nes_audio_checks.c',
    'md_audio_loop.inc', 'md_audio_resample.inc',
    # Converter-only controller bridge (never linked into games).
    'player_gamepad.c',
    # Each machine family's shell: Master System / Game Gear, Game Boy, NES,
    # the 16-bit consoles (Mega Drive, SNES, Neo Geo, CPS-1) and X68000.
    'host.c', 'ui.c', 'ui.h', 'controls.c', 'controls.h',
    'gb_menu.inc', 'gb_input_refresh.inc',
    'nes_host_ui.c', 'console16_host_ui.c', 'neogeo_ui_test.c',
    'x68000_reference/player_ui.inc'))
HOST_FILES = frozenset(('THIRD_PARTY_NOTICES.md',))
HOST_PREFIXES = ('licenses/', 'assets/Retro-Recomp-icon-', 'assets/Retro-Recomp.ico',
                 'assets/tag-shooting.png')


def role(name):
    """'host' or 'game' for one fingerprinted input (module or file path)."""
    if name.startswith('retrorecomp.'):
        return 'host' if name.rsplit('.', 1)[-1] in HOST_MODULES else 'game'
    if name.startswith('native/'):
        return 'host' if name[len('native/'):] in HOST_NATIVE else 'game'
    if name in HOST_FILES or name.startswith(HOST_PREFIXES):
        return 'host'
    return 'game'


def owners(name):
    """Return the narrowest known scope, keeping unclassified inputs shared."""
    name = Path(name).name.lower()
    if name.startswith(('x68000', 'x68k_')):
        return frozenset(('x68',))
    if name.startswith(('gameboy', 'game_boy', 'gb_', 'retro_gb')):
        return frozenset(('gb',))
    # CPS-1 code generation reuses these Neo Geo and Mega Drive modules.
    if name.split('.')[0] in ('neogeo_codegen', 'neogeo_z80', 'neogeo_build'):
        return frozenset(('ng', 'cps1'))
    if name.split('.')[0] in ('megadrive_codegen', 'megadrive_z80'):
        return frozenset(('md', 'cps1'))
    if name.startswith(('neogeo', 'ng_')):
        return frozenset(('ng',))
    if name.startswith('cps1'):
        return frozenset(('cps1',))
    if name.startswith(('supernintendo', 'snes_', 'retro_snes')):
        return frozenset(('snes',))
    if name.startswith(('megadrive', 'md_', 'retro_md')):
        return frozenset(('md',))
    if name.startswith(('nes_', 'retro_nes')) or name in ('nes', 'nes.py'):
        return frozenset(('nes',))
    if name.startswith('m68000'):
        return frozenset(('md', 'ng', 'x68', 'cps1'))
    # The shared 16-bit host is linked into Neo Geo and CPS-1 games too.
    if name.startswith(('console16', 'retro_console16', 'gun16')):
        return frozenset(('md', 'snes', 'ng', 'cps1'))
    if name.startswith('guns16'):
        return frozenset(('md', 'snes'))
    if name.startswith(('master_system', 'game_gear')) or name in ('cpu', 'cpu.py', 'validation', 'validation.py'):
        return frozenset(('sms', 'gg'))
    return SYSTEMS


def _portable_code(value):
    if isinstance(value, CodeType):
        return value.replace(co_filename='', co_consts=tuple(_portable_code(c) for c in value.co_consts))
    return value


def _constant_key(value):
    """Canonical bytecode constants, independent of marshal reference flags.

    Frozen loaders and source compiles can intern equal objects differently.
    Frozenset iteration also depends on the process hash seed. Neither is a
    change to the generated game's compiler inputs.
    """
    if isinstance(value, CodeType):
        fields=('co_argcount','co_posonlyargcount','co_kwonlyargcount','co_nlocals',
                'co_stacksize','co_flags','co_code','co_consts','co_names',
                'co_varnames','co_freevars','co_cellvars','co_name','co_qualname',
                'co_firstlineno','co_linetable','co_exceptiontable')
        return ['code', [[field,_constant_key(getattr(value,field))] for field in fields]]
    if isinstance(value, tuple):return ['tuple',[_constant_key(item) for item in value]]
    if isinstance(value, frozenset):
        entries=[_constant_key(item) for item in value]
        return ['frozenset', sorted(entries,key=lambda item:json.dumps(item,ensure_ascii=True))]
    if isinstance(value, bytes):return ['bytes',value.hex()]
    if isinstance(value, float):return ['float',value.hex()]
    if isinstance(value, complex):return ['complex',value.real.hex(),value.imag.hex()]
    if isinstance(value, slice):return ['slice',_constant_key(value.start),_constant_key(value.stop),_constant_key(value.step)]
    if value is Ellipsis:return ['ellipsis']
    if value is None or type(value) in (str,int,bool):return [type(value).__name__,value]
    raise ValueError('Unsupported compiler bytecode constant: '+type(value).__name__)


def code_fingerprint(code):
    return hashlib.sha256(json.dumps(_constant_key(code),ensure_ascii=True,
                                    separators=(',',':')).encode('ascii')).hexdigest()


@lru_cache(maxsize=512)
def _code_digest(name, size, modified):
    spec = importlib.util.find_spec(name)
    path = Path(spec.origin) if spec and spec.origin else None
    # A source file can change twice within a pyc timestamp's one-second
    # granularity. Compile the source bytes directly rather than trust pyc.
    if path and path.is_file() and path.suffix == '.py':
        code = compile(path.read_bytes(), '', 'exec', dont_inherit=True, optimize=0)
    else:
        code = spec.loader.get_code(name) if spec and hasattr(spec.loader, 'get_code') else None
    if not isinstance(code, CodeType):
        raise ValueError('Cannot fingerprint the compiler module: ' + name)
    return code_fingerprint(code)


def _module_inputs(system):
    for package in ('retrorecomp', 'retrorecomp.systems'):
        spec = importlib.util.find_spec(package)
        names = {m.name for m in pkgutil.iter_modules(spec.submodule_search_locations, package + '.')}
        # Frozen package finders must enumerate their modules too. Never keep
        # exports current on the strength of an empty/partial source glob.
        required = package + ('.core' if package == 'retrorecomp' else '.master_system')
        if required not in names:
            raise ValueError('Cannot enumerate the bundled compiler package: ' + package)
        if package != 'retrorecomp':
            names.add(package)
        for name in sorted(names):
            leaf = name.rsplit('.', 1)[-1]
            if leaf in INTERFACE_MODULES or system not in owners(leaf):
                continue
            module = importlib.util.find_spec(name)
            path = Path(module.origin) if module and module.origin else None
            stat = path.stat() if path and path.is_file() else None
            yield name, _code_digest(name, stat.st_size if stat else 0, stat.st_mtime_ns if stat else 0)


def _resource_paths(root, system):
    for path in (root / 'native').rglob('*'):
        if path.relative_to(root / 'native').parts[0].startswith('x68000') and system != 'x68':
            continue
        if path.is_file() and system in owners(path.name):
            yield path
    for folder in ('assets', 'profiles', 'licenses'):
        for path in (root / folder).rglob('*'):
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            if relative.startswith('assets/tools/') or relative.startswith('assets/locales/') or relative.startswith('assets/credits/'):
                continue
            if path.name in ('compilation-knowledge.json.gz', 'cover-references.json',
                    'font-coverage.json', 'Retro-Recomp-banner.png', 'Retro-Recomp-consoles.png',
                    'Retro-Recomp-logo.png', 'RetroRecomp-UI-JP.otf', 'RetroRecomp-UI-SC.otf'):
                continue
            # Converter-only pictures (the leaderboard's trophy and gems).
            if path.name.startswith('board-'):
                continue
            if path.name == 'neogeo-catalogue.json' and system != 'ng':
                continue
            if path.name.startswith('cps1') and system not in owners(path.name):
                continue
            # The UPX source archive is downloadable legal material, not an
            # exported game's embedded notice or a compiler input.
            if folder == 'licenses' and path.suffix not in ('.md', '.txt'):
                continue
            if folder == 'profiles' and system not in ('sms', 'gg'):
                continue
            yield path
    if (root / 'THIRD_PARTY_NOTICES.md').is_file():
        yield root / 'THIRD_PARTY_NOTICES.md'


def input_fingerprints(system):
    if system not in SYSTEMS:
        raise ValueError('Unknown compilation profile: ' + system)
    from .paths import ASSETS
    from .freshness import _input_hash
    inputs = list(_module_inputs(system))
    for path in _resource_paths(ASSETS, system):
        stat = path.stat()
        inputs.append((path.relative_to(ASSETS).as_posix(),
                       _input_hash(path, stat.st_size, stat.st_mtime_ns)))
    return sorted(inputs)


def engine_stamp(system):
    value = hashlib.sha256(('console-inputs-v1:' + system).encode())
    for name, fingerprint in input_fingerprints(system):
        value.update(name.encode('utf-8') + b'\0' + fingerprint.encode('ascii') + b'\0')
    return value.hexdigest()


def role_stamps(system):
    """Separate stamps of one console's game-side and host inputs."""
    values = {part: hashlib.sha256(f'console-{part}-inputs-v1:{system}'.encode()) for part in ('game', 'host')}
    for name, fingerprint in input_fingerprints(system):
        values[role(name)].update(name.encode('utf-8') + b'\0' + fingerprint.encode('ascii') + b'\0')
    return {part: value.hexdigest() for part, value in values.items()}


def knowledge_stamp(system, identity):
    """A new cartridge hint must invalidate the relevant export, even at 1.x."""
    from .knowledge import RESOURCE
    from .paths import ASSETS
    if (os.environ.get('RETRO_RECOMP_LIBRARY_DIR') or os.environ.get('SMSRECOMP_LIBRARY_DIR')
            or os.environ.get('RETRO_RECOMP_BUNDLED_KNOWLEDGE') == '0'):
        return 'disabled'
    path = ASSETS / RESOURCE
    if not path.is_file():
        return 'absent'
    # load() is bounded and validates the numeric schema. Its cache is keyed
    # by a stat-qualified helper so development replacements are noticed.
    stat = path.stat()
    bank = _knowledge_bank(path, stat.st_size, stat.st_mtime_ns).get(system, {})
    # Neo Geo keys include selected BIOS/prepared regions; the request already
    # fingerprints the BIOS. Its small bank is conservatively scoped to NG.
    record = bank if system == 'ng' else bank.get(identity, {})
    # Imported hints count too; without them the stamp is unchanged.
    from .knowledge import imported_observations, imported_record
    imported = {} if system == 'ng' else imported_record(system, identity)
    observations = [] if system == 'ng' else imported_observations(system, identity)
    if imported or observations:
        record = {'bundled': record, 'imported': imported}
        if observations:
            record['observations'] = observations
    return hashlib.sha256(json.dumps(record, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


@lru_cache(maxsize=4)
def _knowledge_bank(path, size, modified):
    from .knowledge import load
    load.cache_clear()
    return load(path)['consoles']
