"""Content fingerprints of the inputs used by one console's exported games.

What enters a stamp is listed, never discovered: the manifest in `stamp_inputs`
names every module and file, with the consoles that own it. A file that is not
listed is ignored, a listed one that is missing is an error, so neither a stray
file on disk nor an untracked one moves a stamp. Text is hashed with normalised
line ends. This module and `stamp_inputs` define the stamps and are themselves
interface modules that no stamp hashes (see the docstring of `stamp_inputs`).
The application version is presentation metadata, not a runtime ABI version.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
from types import CodeType
from functools import lru_cache

from .stamp_inputs import (  # noqa: F401  (re-exported: the tables used to live here)
    ALL, BINARY_SUFFIXES, BUILD_MODULES, HOST_FILES, HOST_MODULES, HOST_NATIVE, HOST_PREFIXES,
    INPUTS, INTERFACE_MODULES, LEGACY_GAME_STAMPS, RAW_FILES, TEXT_SUFFIXES)
from .systems import system_ids

# Every console the converter knows: the profiles' list.
SYSTEMS = frozenset(system_ids())

# Names the algorithm in the seed of every stamp. A change of what a stamp
# hashes, or of how, must bump it (a test pins the output on a synthetic input).
STAMP_LABEL = 'v2'


def legacy_game_stamps(system):
    return tuple(LEGACY_GAME_STAMPS.get(system, ()))


def role(name):
    """'host', 'build' or 'game' for one fingerprinted input (module or file path)."""
    if name.startswith('retrorecomp.'):
        leaf = name.rsplit('.', 1)[-1]
        return 'host' if leaf in HOST_MODULES else 'build' if leaf in BUILD_MODULES else 'game'
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
    # CPS-1 code generation reuses these Neo Geo and Mega Drive modules; both
    # arcade consoles read their set ZIPs through the shared zip_sets reader.
    if name.split('.')[0] in ('neogeo_codegen', 'neogeo_z80', 'neogeo_build', 'zip_sets'):
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
    # The shared 16-bit host (and the host kit that carries it) is linked into Neo Geo and CPS-1 games too.
    if name.startswith(('console16', 'retro_console16', 'gun16', 'hostkit')):
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


def manifest_names(system=None):
    """The listed inputs (module names and file paths), all of them or one console's."""
    names = set()
    for owner, listed in INPUTS.items():
        if system is None or owner == ALL or system in owner:
            names.update(listed)
    return sorted(names)


def _module_inputs(system):
    for name in manifest_names(system):
        if not name.startswith('retrorecomp'):
            continue
        if name.rsplit('.', 1)[-1] in INTERFACE_MODULES:
            continue
        module = importlib.util.find_spec(name)
        if module is None:
            raise ValueError('Cannot find the listed compiler module: ' + name)
        path = Path(module.origin) if module.origin else None
        stat = path.stat() if path and path.is_file() else None
        yield name, _code_digest(name, stat.st_size if stat else 0, stat.st_mtime_ns if stat else 0)


def _resource_names(system):
    return [name for name in manifest_names(system) if not name.startswith('retrorecomp')]


def _file_kind(name):
    """'text' (line ends normalised) or 'raw' for one listed file."""
    suffix = PurePosixPath(name).suffix.lower()
    if name in RAW_FILES or suffix in BINARY_SUFFIXES:
        return 'raw'
    if suffix in TEXT_SUFFIXES:
        return 'text'
    raise ValueError('Unclassified stamp input type (TEXT_SUFFIXES or BINARY_SUFFIXES): ' + name)


def _normalized(data, kind):
    return data.replace(b'\r\n', b'\n') if kind == 'text' else data


def input_bytes(path, name):
    """The bytes a stamp hashes for one listed file (`name` is its manifest path)."""
    return _normalized(Path(path).read_bytes(), _file_kind(name))


@lru_cache(maxsize=2048)
def _file_digest(path, size, modified, kind):
    return hashlib.sha256(_normalized(Path(path).read_bytes(), kind)).hexdigest()


def state_native_files(system):
    """The files directly below native/ that fix one console's save-state layout or
    build signature: the listed ones it owns, nothing found on disk. Returns paths."""
    from .paths import ASSETS
    paths = []
    for name in manifest_names(system):
        if name.startswith('native/') and '/' not in name[len('native/'):]:
            path = ASSETS / name
            if not path.is_file():
                raise ValueError('Missing listed native file: ' + name)
            paths.append(path)
    return paths


def input_fingerprints(system):
    if system not in SYSTEMS:
        raise ValueError('Unknown compilation profile: ' + system)
    from .paths import ASSETS
    inputs = list(_module_inputs(system))
    for name in _resource_names(system):
        path = ASSETS / name
        if not path.is_file():
            raise ValueError('Missing listed compilation input: ' + name)
        stat = path.stat()
        inputs.append((name, _file_digest(path, stat.st_size, stat.st_mtime_ns, _file_kind(name))))
    return sorted(inputs)


def engine_stamp(system):
    value = hashlib.sha256(('console-inputs-%s:%s' % (STAMP_LABEL, system)).encode())
    for name, fingerprint in input_fingerprints(system):
        value.update(name.encode('utf-8') + b'\0' + fingerprint.encode('ascii') + b'\0')
    return value.hexdigest()


def role_stamps(system):
    """Separate stamps of one console's game-side, host and build inputs."""
    values = {part: hashlib.sha256(f'console-{part}-inputs-{STAMP_LABEL}:{system}'.encode())
              for part in ('game', 'host', 'build')}
    for name, fingerprint in input_fingerprints(system):
        values[role(name)].update(name.encode('utf-8') + b'\0' + fingerprint.encode('ascii') + b'\0')
    return {part: value.hexdigest() for part, value in values.items()}


def knowledge_stamp(system, identity):
    """A changed qualified or imported hint must invalidate the relevant export, even at 1.x."""
    if (os.environ.get('RETRO_RECOMP_LIBRARY_DIR') or os.environ.get('SMSRECOMP_LIBRARY_DIR')
            or os.environ.get('RETRO_RECOMP_BUNDLED_KNOWLEDGE') == '0'):
        return 'disabled'
    # The qualified bank is the local file written from the shared base; a
    # missing or invalid one knows nothing. Its reader is bounded, validates
    # the numeric schema and notices a replaced file by size and mtime.
    from .knowledge import imported_observations, imported_record, qualified_bank
    bank = qualified_bank().get(system, {})
    # Neo Geo keys include selected BIOS/prepared regions; the request already
    # fingerprints the BIOS. Its small bank is conservatively scoped to NG.
    record = bank if system == 'ng' else bank.get(identity, {})
    # Imported hints count too; without them the stamp is unchanged.
    imported = {} if system == 'ng' else imported_record(system, identity)
    observations = [] if system == 'ng' else imported_observations(system, identity)
    if imported or observations:
        record = {'qualified': record, 'imported': imported}
        if observations:
            record['observations'] = observations
    return hashlib.sha256(json.dumps(record, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
